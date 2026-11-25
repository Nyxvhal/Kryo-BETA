"""Offline format/API/worker tests. Real model smoke tests are separate."""
import asyncio
import copy
import json
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from kryonyx import lyrics,karaoke_jobs,karaoke_worker


def sample(text='I want to stay'):
    return {'version':2,'language':'en','lines':[{'text':text,'start':1,'end':4,
            'translation':'Я хочу остаться','words':[{'text':'I','start':1,'end':1.2},
            {'text':'want','start':1.3,'end':2,'confidence':.9},
            {'text':'to','start':2.1,'end':2.3},
            {'text':'stay','start':2.4,'end':4,'syllables':[{'text':'st','start':2.4,'end':2.5},{'text':'ay','start':2.6,'end':4}]}]}],
            'sections':[{'type':'instrumental','start':0,'end':1}],
            'custom':{'editable':True}}


class FormatTests(unittest.TestCase):
 def test_document_roundtrip_preserves_metadata(self):
  d=sample();self.assertEqual(lyrics.karaoke_document(d),d);p=lyrics.karaoke_payload(d)
  self.assertEqual(p['lines'][0]['words'][-1]['syllables'][0]['time'],2.4)
  self.assertNotIn('time',d['lines'][0]);self.assertEqual(p['lines'][0]['words'][1]['end'],2)
 def test_modified_cached_audio_invalidates_binding(self):
  with tempfile.TemporaryDirectory() as temp,patch.object(karaoke_jobs,'data_dir',return_value=temp):
   audio=Path(temp)/'a.wav';audio.write_bytes(b'original');stat=audio.stat();d=sample()
   d['source_fingerprint']={'audio_sha256':karaoke_worker.digest(audio)}
   d['binding']={'source':'audio-cache','stat':[stat.st_size,stat.st_mtime_ns]}
   karaoke_jobs.save_track('track',d)
   with patch.object(karaoke_jobs.audiocache,'find',return_value=str(audio)):
    self.assertIsNotNone(karaoke_jobs.load_track('track'))
    audio.write_bytes(b'changed');self.assertIsNone(karaoke_jobs.load_track('track'))
 def test_reject_nonfinite_negative_and_bad_bounds(self):
  for value in [-1,float('inf'),float('nan'),True]:
   d=sample();d['lines'][0]['start']=value
   with self.assertRaises(ValueError):lyrics.karaoke_document(d)
  d=sample();d['lines'][0]['words'][0]['end']=6
  with self.assertRaises(ValueError):lyrics.karaoke_document(d)
 def test_reject_nested_unbounded_syllables(self):
  d=sample();d['lines'][0]['words'][-1]['syllables'][0]['syllables']=[]
  with self.assertRaises(ValueError):lyrics.karaoke_document(d)
 def test_variants_translation_and_speaker(self):
  d=sample();d['lines'][0]['speaker']='lead';d['variants']=[{'id':'ru','language':'ru','lines':[{'text':'Привет','start':1,'end':2}]}]
  p=lyrics.karaoke_payload(d,'ru');self.assertEqual(p['language'],'ru');self.assertEqual(p['lines'][0]['text'],'Привет')
 def test_plain_empty_and_unavailable(self):
  self.assertFalse(lyrics.parse_subtitle('No timings','text.txt')['synced']);self.assertEqual(lyrics.build()['lines'],[])
 def test_lrc_fallback_marks_estimated_words(self):
  p=lyrics.parse_subtitle('[00:01.00]Привет мир\n[00:04.00]Ещё строка','song.lrc')
  self.assertTrue(p['synced']);self.assertFalse(p['words']);self.assertTrue(p['lines'][0]['words'][0]['guessed'])
 def test_enhanced_lrc_and_explicit_ends(self):
  p=lyrics.build('[00:01.00]<00:01.00>Hello <00:01.50>world')
  self.assertTrue(p['words'])
  lines=lyrics.finish([{'time':1,'end':5,'text':'Hello','words':[{'time':1,'end':1.4,'text':'Hello'}]}])
  self.assertEqual(lines[0]['words'][0]['end'],1.4)
 def test_multilingual_not_space_only(self):
  for code,text in [('en','Hello world'),('ru','Привет мир'),('ja','こんにちは世界'),('ko','안녕 세계'),('zh','你好世界'),('es','Hola mundo'),('de','Hallo Welt'),('fr','Bonjour monde')]:
   d={'version':2,'language':code,'lines':[{'text':text,'start':1,'end':4}]}
   self.assertEqual(lyrics.karaoke_payload(d)['lines'][0]['text'],text)
  self.assertEqual(lyrics.tokenize_text('你好世界'),list('你好世界'))
 def test_srt_and_basic_ttml(self):
  s='1\n00:00:01,250 --> 00:00:03,500\nHello world\n'
  self.assertEqual(lyrics.parse_subtitle(s,'a.srt')['lines'][0]['time'],1.25)
  x='<tt xmlns="http://www.w3.org/ns/ttml"><body><p begin="1s" end="4s"><span begin="0s" end="1s">Hello</span> world</p></body></tt>'
  p=lyrics.parse_subtitle(x,'a.ttml');self.assertEqual(p['lines'][0]['words'][0]['end'],2)
  with self.assertRaises(ValueError):lyrics.parse_subtitle('<!DOCTYPE tt><tt/>','a.ttml')
 def test_long_short_fast_slow_words_preserved(self):
  d={'version':2,'language':'en','lines':[{'text':'a extraordinarily slow','start':0,'end':20,'words':[{'text':'a','start':0,'end':.02},{'text':'extraordinarily','start':.03,'end':1},{'text':'slow','start':2,'end':20}]}]}
  self.assertEqual(lyrics.karaoke_payload(d)['lines'][0]['words'][0]['end'],.02)


class WorkerTests(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.audio=Path(self.tmp.name)/'a.wav';self.audio.write_bytes(b'fixture')
 def tearDown(self):self.tmp.cleanup()
 def test_content_cache_reused_and_changed_audio_invalidates(self):
  r={'audio':str(self.audio),'cache':self.tmp.name,'model':'tiny','language':'en','device':'cpu'}
  seg=[{'start':1,'end':2,'text':'Hello','words':[{'word':'Hello','start':1,'end':2}]}]
  with patch.object(karaoke_worker,'probe',return_value={'cuda':False,'torch_cuda':False}),patch.object(karaoke_worker,'_infer',return_value=(seg,'en',3)) as infer,patch.object(karaoke_worker,'emit'):
   a=karaoke_worker.run_job(r);b=karaoke_worker.run_job(r);self.assertEqual(infer.call_count,1);self.assertEqual(a,b)
   self.audio.write_bytes(b'changed');karaoke_worker.run_job(r);self.assertEqual(infer.call_count,2)
 def test_cuda_runtime_failure_falls_back_to_cpu(self):
  seg=[{'words':[{'word':'Hi','start':0,'end':1}]}]
  with patch.object(karaoke_worker,'probe',return_value={'cuda':True,'torch_cuda':True}),patch.object(karaoke_worker,'_infer',side_effect=[RuntimeError('missing CUDA library'),(seg,'en',2)]) as infer,patch.object(karaoke_worker,'emit'):
   d=karaoke_worker.run_job({'audio':str(self.audio),'cache':self.tmp.name,'model':'tiny','device':'auto'})
   self.assertEqual(d['alignment']['device'],'cpu');self.assertEqual(infer.call_args_list[0].args[-1],'cuda');self.assertEqual(infer.call_args_list[1].args[-1],'cpu')
 def test_no_gpu_reference_uses_alignment_not_prompt(self):
  seg=[{'words':[{'word':'Hi','start':0,'end':1}]}]
  with patch.object(karaoke_worker,'probe',return_value={'cuda':False,'torch_cuda':False}),patch.object(karaoke_worker,'_infer',return_value=(seg,'en',2)) as infer,patch.object(karaoke_worker,'emit'):
   d=karaoke_worker.run_job({'audio':str(self.audio),'cache':self.tmp.name,'model':'tiny','reference':'Hi','language':'en','device':'cuda'})
   self.assertEqual(infer.call_args.args[2],'stable-ts');self.assertEqual(d['alignment']['device'],'cpu')
 def test_no_vocals_fails_without_fake_times(self):
  with self.assertRaises(ValueError):karaoke_worker.document_from_segments([], 'en',10,{})
 def test_missing_separation_package_reports_error(self):
  with patch.object(karaoke_worker,'probe',return_value={'cuda':False,'torch_cuda':False,'demucs':False}),patch.object(karaoke_worker,'emit'):
   with self.assertRaisesRegex(ValueError,'demucs'):karaoke_worker.run_job({'audio':str(self.audio),'cache':self.tmp.name,'separate':True})


class APITests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  from aiohttp.test_utils import TestClient,TestServer
  from kryonyx import server
  self.tmp=tempfile.TemporaryDirectory();self.p=patch.object(karaoke_jobs,'data_dir',return_value=self.tmp.name);self.p.start()
  self.client=TestClient(TestServer(server.build_app()));await self.client.start_server()
 async def asyncTearDown(self):await self.client.close();self.p.stop();self.tmp.cleanup()
 async def test_document_priority_edit_delete_and_lrc(self):
  r=await self.client.put('/api/karaoke/document',json={'track_id':'test','document':sample()});self.assertEqual(r.status,200)
  r=await self.client.get('/api/lyrics?track_id=test');d=await r.json();self.assertTrue(d['precise']);self.assertEqual(d['lines'][0]['time'],1)
  d=sample();d['lines'][0]['words'][0]['end']=1.1
  await self.client.put('/api/karaoke/document',json={'track_id':'test','document':d})
  r=await self.client.get('/api/karaoke/document?track_id=test');self.assertEqual((await r.json())['lines'][0]['words'][0]['end'],1.1)
  await self.client.delete('/api/karaoke/document?track_id=test')
  r=await self.client.put('/api/karaoke/document',json={'track_id':'test','source':'[00:02.00]Only LRC','filename':'a.lrc'});self.assertEqual(r.status,200)
  r=await self.client.get('/api/lyrics?track_id=test');self.assertFalse((await r.json())['words'])
 async def test_invalid_json_leaves_previous_document(self):
  await self.client.put('/api/karaoke/document',json={'track_id':'test','document':sample()})
  r=await self.client.put('/api/karaoke/document',json={'track_id':'test','document':{'version':2,'lines':[{'text':'bad','start':3,'end':1}]}});self.assertEqual(r.status,400)
  self.assertEqual(karaoke_jobs.load_track('test')['lines'][0]['start'],1)
 async def test_unknown_job_and_no_cached_audio(self):
  self.assertEqual((await self.client.get('/api/karaoke/jobs/missing')).status,404)
  self.assertEqual((await self.client.post('/api/karaoke/generate',json={'track_id':'missing'})).status,400)
 async def test_cross_origin_guard(self):
  r=await self.client.put('/api/karaoke/document',json={'track_id':'t','document':sample()},headers={'Origin':'https://untrusted.example'});self.assertEqual(r.status,403)
 async def test_upload_submits_with_reference(self):
  import aiohttp
  form=aiohttp.FormData();form.add_field('audio',b'RIFFtest',filename='a.wav',content_type='audio/wav');form.add_field('reference','[00:01.00]Hello');form.add_field('reference_name','a.lrc');form.add_field('track_id','test')
  jobs=self.client.server.app['karaoke_jobs']
  with patch.object(jobs,'submit',return_value={'id':'accepted','stage':'queued'}) as submit:
   r=await self.client.post('/api/karaoke/generate',data=form);self.assertEqual(r.status,200);self.assertEqual(submit.call_args.args[0]['reference'],'Hello')
   Path(submit.call_args.args[0]['audio']).unlink()


class JobLifecycleTests(unittest.IsolatedAsyncioTestCase):
 async def test_cancel_before_worker_starts_removes_upload(self):
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'upload.wav';path.write_bytes(b'fixture')
   jobs=karaoke_jobs.Jobs();job=jobs.submit({'audio':str(path)},owned=True)
   value=await jobs.cancel(job['id'])
   self.assertEqual(value['stage'],'cancelled');self.assertFalse(path.exists());self.assertFalse(jobs.tasks)
 async def test_cancel_waiting_job_does_not_spawn_worker(self):
  jobs=karaoke_jobs.Jobs();await jobs.lock.acquire()
  with tempfile.TemporaryDirectory() as temp:
   path=Path(temp)/'upload.wav';path.write_bytes(b'fixture')
   job=jobs.submit({'audio':str(path)},owned=True);await asyncio.sleep(0)
   await jobs.cancel(job['id']);jobs.lock.release()
   self.assertFalse(path.exists());self.assertFalse(jobs.processes)

if __name__=='__main__':unittest.main()
