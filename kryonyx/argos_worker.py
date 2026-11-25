"""One offline Argos translation job over stdin/stdout; never serves a network port."""
import json
import os
import socket
import sys

# Set before importing Argos. 1.11.0 does not implement NONE; MiniSBD must
# be warmed up by setup while online. Disable all outbound connections here.
os.environ['ARGOS_CHUNK_TYPE'] = 'MINISBD'
os.environ['ARGOS_DEVICE_TYPE'] = 'cpu'
os.environ.setdefault('OMP_NUM_THREADS', '2')
def offline(*args, **kwargs):
    raise OSError('Network disabled in offline translation worker')
socket.socket.connect = offline
socket.socket.connect_ex = offline
socket.create_connection = offline

def detect_source(lines):
    # Short or ambiguous snippets are unsafe to guess. Detection is local and
    # uses the whole song (not only lines selected for retry).
    import langdetect
    text = ' '.join(dict.fromkeys(line.strip() for line in lines if line.strip()))[:12000]
    if sum(ch.isalpha() for ch in text) < 30:
        raise ValueError('Text is too short to detect language; choose the original language manually.')
    langdetect.DetectorFactory.seed = 0
    candidates = langdetect.detect_langs(text)
    if not candidates or candidates[0].prob < 0.85:
        raise ValueError('Language detection is uncertain; choose the original language manually.')
    code = candidates[0].lang
    return 'zh' if code in ('zh-cn', 'zh-tw') else code

def main():
    req = json.load(sys.stdin)
    source = detect_source(req.get('context') or req['lines']) if req['source'] == 'auto' else req['source']
    source = 'zh' if source == 'zh-CN' else source
    target = 'zh' if req['target'] == 'zh-CN' else req['target']
    if source == target:
        raise ValueError('The detected original language matches the target. Choose a different target.')
    import argostranslate.translate as translate
    langs = {language.code: language for language in translate.get_installed_languages()}
    if source not in langs or target not in langs:
        raise ValueError('Missing Argos model for %s → %s. Run setup-translate first.' % (source, target))
    engine = langs[source].get_translation(langs[target])
    if engine is None:
        raise ValueError('Missing Argos route %s → %s. Install the required model(s).' % (source, target))
    cache, rows = {}, []
    for index, line in enumerate(req['lines']):
        if not line.strip():
            rows.append({'index':index,'original':line,'translation':'','status':'empty'})
            continue
        try:
            if line not in cache:
                # A lyric line is translated independently to preserve positions.
                value = engine.translate(line).strip()
                if not value or '\n' in value or '\r' in value:
                    raise ValueError('Argos returned an empty or multiline translation')
                cache[line] = value
            rows.append({'index':index,'original':line,'translation':cache[line],'status':'ok'})
        except Exception as exc:
            # Missing MiniSBD is a setup error, not a failed individual lyric line.
            if 'Network disabled' in str(exc): raise
            rows.append({'index':index,'original':line,'translation':'','status':'error','error_code':'line_failed'})
    return {'source': 'zh-CN' if source == 'zh' else source, 'results':rows}

if __name__ == '__main__':
    try:
        print(json.dumps(main(), ensure_ascii=False), flush=True)
    except Exception as exc:
        print(json.dumps({'error':str(exc) or type(exc).__name__}, ensure_ascii=False), flush=True)
        sys.exit(1)
