"""Isolated optional ML process. No audio engine, HTTP listener or app imports.

Protocol: one JSON request on stdin, newline-delimited JSON progress on stdout.
Heavy packages are imported only here, never in the playback process.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import uuid
from . import lyrics, karaoke_quality

MODELS = {'tiny','base','small','medium','large-v3','large-v3-turbo'}
LANGUAGES = {'en','ru','ja','ko','zh','es','de','fr','auto'}


def emit(stage, **values):
    print(json.dumps({'stage':stage,**values}, ensure_ascii=False),flush=True)


def probe():
    result={'cpu':True,'cuda':False,'faster_whisper':bool(importlib.util.find_spec('faster_whisper')),
            'stable_ts':bool(importlib.util.find_spec('stable_whisper')),
            'demucs':bool(importlib.util.find_spec('demucs')),'python':sys.version.split()[0]}
    try:
        import ctranslate2
        result['cuda']=ctranslate2.get_cuda_device_count()>0
    except Exception: pass
    try:
        import torch
        result['torch_cuda']=torch.cuda.is_available()
    except Exception: result['torch_cuda']=False
    return result


def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def atomic_json(path,doc):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    tmp.write_text(json.dumps(doc,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(tmp,path)


def document_from_segments(segments,language,duration,metadata):
    rows=[]
    for segment in segments:
        words=[]
        for w in segment.get('words',[]):
            if w.get('start') is None or w.get('end') is None: continue
            text=w.get('word',w.get('text',''))
            if not str(text).strip():continue
            a,b=max(0,float(w['start'])),max(0,float(w['end']))
            if b<a: continue
            item={'text':str(text),'start':a,'end':b}
            c=w.get('probability',w.get('confidence'))
            if c is not None:item['confidence']=max(0,min(1,float(c)))
            words.append(item)
        if not words: continue
        # Keep the engine's token boundaries (including CJK). Never split timed
        # words into fake syllables. Leading whitespace is intentional.
        rows.append({'text':''.join(w['text'] for w in words).strip(),
                     'start':min(w['start'] for w in words),'end':max(w['end'] for w in words),
                     'words':words})
    if not rows:raise ValueError('No aligned vocals found; use LRC/plain fallback')
    rows.sort(key=lambda r:r['start'])
    sections=[];at=0
    for row in rows:
        if row['start']-at >= 2:sections.append({'type':'instrumental','start':at,'end':row['start'],'estimated':True})
        at=max(at,row['end'])
    if duration and duration-at>=2:sections.append({'type':'instrumental','start':at,'end':duration,'estimated':True})
    return lyrics.karaoke_document({'version':2,'language':language,'duration':duration,
        'lines':rows,'sections':sections,'alignment':metadata})


def run_job(request):
    source=Path(request['audio']).resolve()
    if not source.is_file():raise ValueError('Audio file is not available')
    model_name=request.get('model','small')
    if model_name not in MODELS:raise ValueError('Unsupported model')
    language=request.get('language','auto')
    if language not in LANGUAGES:raise ValueError('Unsupported language code')
    ref=request.get('reference','').strip()
    engine=request.get('engine','auto')
    if engine not in ('auto','faster-whisper','stable-ts'):raise ValueError('Unsupported engine')
    if ref and engine=='faster-whisper':raise ValueError('Reference lyrics require stable-ts forced alignment; recognition is not alignment')
    engine='stable-ts' if ref or engine=='stable-ts' else 'faster-whisper'
    opts={'model':model_name,'language':language,'separate':bool(request.get('separate')),
          'device':request.get('device','auto'),'refine':bool(request.get('refine'))}
    identity={'audio_sha256':digest(source),'reference_sha256':hashlib.sha256(ref.encode()).hexdigest(),
              'engine':engine,'pipeline':4,'options':opts}
    key=hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()
    output=Path(request['cache'])/(key+'.karaoke.json')
    if output.exists() and not request.get('force'):
        try:
            doc=lyrics.karaoke_document(json.loads(output.read_text(encoding='utf-8')))
            if doc.get('source_fingerprint')==identity:
                emit('done',cached=True,result=str(output),key=key);return doc
        except (ValueError,OSError):pass
    emit('hardware'); hw=probe()
    desired=request.get('device','auto')
    if desired not in ('auto','cpu','cuda'):raise ValueError('Unsupported device')
    available=hw['torch_cuda'] if engine=='stable-ts' else hw['cuda']
    device='cuda' if desired!='cpu' and available else 'cpu'
    fallback_reason='CUDA unavailable' if desired=='cuda' and device=='cpu' else ''
    with tempfile.TemporaryDirectory(prefix='kry-karaoke-') as tmp:
        audio=str(source)
        if request.get('separate'):
            if not hw['demucs']:raise ValueError('Vocal separation requires optional demucs package')
            emit('separating')
            command=[sys.executable,'-m','demucs','--two-stems=vocals','-n','htdemucs','-d',device,'-j','1','-o',tmp,audio]
            res=subprocess.run(command,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,timeout=3600)
            if res.returncode:raise ValueError('Vocal separation failed; try without separation')
            vocals=list(Path(tmp).glob('**/vocals.wav'))
            if not vocals:raise ValueError('Separation produced no vocal stem')
            audio=str(vocals[0])
        emit('loading-model',engine=engine,device=device)
        try:
            segments,detected,duration=_infer(audio,ref,engine,model_name,language,device)
        except (RuntimeError,OSError) as exc:
            if device!='cuda':raise
            # CUDA drivers/libraries may be missing even after a successful probe.
            fallback_reason=str(exc)[:200];device='cpu'
            emit('cpu-fallback',reason=fallback_reason)
            segments,detected,duration=_infer(audio,ref,engine,model_name,language,device)
        refinement='not-requested'; refinement_reason=''
        if not ref and engine=='faster-whisper' and request.get('refine'):
            refinement='unavailable'
            if hw.get('stable_ts'):
                draft='\n'.join(''.join(w.get('word',w.get('text','')) for w in s.get('words',[])).strip() for s in segments)
                emit('refining')
                align_device='cuda' if desired!='cpu' and hw.get('torch_cuda') else 'cpu'
                try:
                    try: aligned,_,_= _infer(audio,draft,'stable-ts',model_name,detected,align_device)
                    except (RuntimeError,OSError):
                        if align_device!='cuda':raise
                        aligned,_,_= _infer(audio,draft,'stable-ts',model_name,detected,'cpu')
                    candidate=document_from_segments(aligned,detected,duration,{})
                    if not karaoke_quality.reference_matches(candidate,draft):
                        raise ValueError('Refinement lost transcript words')
                    segments=aligned; refinement='applied'
                except Exception as exc:
                    refinement='failed';refinement_reason=str(exc)[:200]
                    emit('refinement-skipped',reason=refinement_reason)
            else:
                refinement_reason='Install requirements-karaoke-align.txt to refine word timing'
                emit('refinement-skipped',reason=refinement_reason)
        if not ref:
            segments=karaoke_quality.readable_segments(segments)
        emit('saving')
        doc=document_from_segments(segments,detected,duration,{'engine':engine,'model':model_name,
             'device':device,'forced':bool(ref),'syllables':'not-generated','fallback_reason':fallback_reason,
             'refinement':refinement,'refinement_reason':refinement_reason})
        if ref and not karaoke_quality.reference_matches(doc,ref):
            raise ValueError('Alignment did not preserve every reference word. No result was applied; check lyrics/language or try a larger model.')
        doc['quality']=karaoke_quality.assess(doc)
        doc['source_fingerprint']=identity
        atomic_json(output,doc)
        emit('done',cached=False,result=str(output),key=key)
        return doc


def _infer(audio,ref,engine,model,language,device):
    # Decode through FFmpeg, avoiding the faster-whisper/PyAV metadata_errors
    # incompatibility on newer PyAV releases. Only the isolated worker decodes.
    import numpy as np
    executable=shutil.which('ffmpeg')
    if not executable:
        try:
            import imageio_ffmpeg
            executable=imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError as e:raise ValueError('Install FFmpeg or imageio-ffmpeg in the worker') from e
    decoded=subprocess.run([executable,'-v','error','-i',audio,'-vn','-ac','1','-ar','16000',
                '-t','3601','-f','f32le','pipe:1'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=300)
    if decoded.returncode:raise ValueError('FFmpeg could not decode this audio file')
    waveform=np.frombuffer(decoded.stdout,dtype=np.float32).copy()
    duration=len(waveform)/16000
    if duration>3600:raise ValueError('Processing is limited to one hour per file')
    if duration<.1:raise ValueError('Audio is too short')
    if engine=='faster-whisper':
        try:from faster_whisper import WhisperModel
        except ImportError as e:raise ValueError('Install requirements-karaoke.txt in the worker environment') from e
        recognizer=WhisperModel(model,device=device,compute_type='float16' if device=='cuda' else 'int8',cpu_threads=max(1,min(4,(os.cpu_count() or 2)-1)),num_workers=1)
        emit('recognizing')
        iterator,info=recognizer.transcribe(waveform,language=None if language=='auto' else language,
                   word_timestamps=True,beam_size=5,vad_filter=False,condition_on_previous_text=False)
        segments=[]
        for segment in iterator:
            segments.append({'start':segment.start,'end':segment.end,'text':segment.text,
                'words':[{'word':w.word,'start':w.start,'end':w.end,'probability':w.probability} for w in (segment.words or [])]})
            emit('recognizing',processed_seconds=segment.end,total_seconds=info.duration)
        return segments,info.language,float(info.duration)
    try:
        import stable_whisper
        import torch
    except ImportError as e:raise ValueError('Install requirements-karaoke-align.txt for reference alignment') from e
    torch.set_num_threads(max(1,min(4,(os.cpu_count() or 2)-1)))
    # stable-ts forced alignment uses Whisper attention, not initial_prompt.
    # It works locally with the multilingual Whisper vocabulary on CPU/CUDA.
    recognizer=stable_whisper.load_model(model,device=device)
    if ref:
        if language=='auto':
            emit('detecting-language')
            detection=recognizer.transcribe(waveform,verbose=False,word_timestamps=True)
            language=detection.language
        emit('aligning')
        result=recognizer.align(waveform,ref,language=language,original_split=True,verbose=False)
    else:
        emit('recognizing')
        result=recognizer.transcribe(waveform,language=None if language=='auto' else language,verbose=False,word_timestamps=True)
    if result is None:raise ValueError('Forced alignment returned no result')
    data=result.to_dict()
    # align() doesn't always provide duration; decode just once for that case.
    return data.get('segments',[]),data.get('language') or language,duration


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stdin,'reconfigure'):sys.stdin.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser();parser.add_argument('--probe',action='store_true');args=parser.parse_args()
    if args.probe:
        print(json.dumps(probe()));return
    try:run_job(json.loads(sys.stdin.readline()))
    except Exception as e:
        emit('error',error=f'{type(e).__name__}: {e}')
        raise SystemExit(1)

if __name__=='__main__':main()
