"""Capture licences of the ACTUAL build environment, not a guessed dependency list.
Run after pip install. No private application data is read or sent anywhere.
This is an inventory, not a legal clearance or a corresponding-source offer.
"""
from __future__ import annotations
import hashlib, importlib.metadata as md, json, re, shutil, subprocess, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'licenses'/'build-environment'

def main():
    if OUT.exists():shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    build_only = {'pip', 'setuptools', 'wheel', 'pyinstaller', 'pyinstaller-hooks-contrib',
                  'altgraph', 'pefile', 'pywin32-ctypes', 'packaging', 'pytest', 'playwright',
                  'greenlet', 'pyee', 'pluggy', 'iniconfig'}
    packages=[]
    for dist in sorted(md.distributions(),key=lambda d:(d.metadata.get('Name') or '').lower()):
        name=dist.metadata.get('Name') or 'unknown';safe=re.sub(r'[^a-zA-Z0-9_.-]','_',name)
        scope='build-only' if name.lower() in build_only else 'runtime'
        target=OUT/safe;target.mkdir(exist_ok=True);files=[]
        for n,file in enumerate(dist.files or []):
            rel=Path(str(file))
            if not any(re.match(r'^(licen[cs]e|copying|notice|copyright|authors)([._-]|$)',part,re.I) for part in rel.parts):continue
            source=Path(dist.locate_file(file))
            if not source.is_file() or source.stat().st_size>4*1024*1024:continue
            destination=target/(str(n)+'-'+source.name)
            shutil.copyfile(source,destination);files.append(str(destination.relative_to(ROOT/'licenses')))
        # Metadata sometimes embeds the full licence instead of a separate file.
        licence=dist.metadata.get('License-Expression') or dist.metadata.get('License') or ''
        if licence:(target/'DECLARED-LICENSE.txt').write_text(licence,encoding='utf-8')
        packages.append({'name':name,'version':dist.version,'scope':scope,'declaredLicense':licence,'homepage':dist.metadata.get('Home-page'),'projectUrls':dist.metadata.get_all('Project-URL') or [],'licenseFiles':files,'reviewRequired':not bool(files)})
    binaries=[]
    try:
        import imageio_ffmpeg
        exe=imageio_ffmpeg.get_ffmpeg_exe()
        for flag,name in [('-version','FFmpeg-version.txt'),('-L','FFmpeg-license.txt'),('-buildconf','FFmpeg-buildconf.txt')]:
            run=subprocess.run([exe,flag],capture_output=True,text=True,timeout=40,check=True)
            (OUT/name).write_text(run.stdout+'\n'+run.stderr,encoding='utf-8')
        binaries.append({'name':'FFmpeg','sha256':hashlib.sha256(Path(exe).read_bytes()).hexdigest(),'provider':'imageio-ffmpeg','correspondingSourceReviewRequired':True})
    except (ImportError,OSError,subprocess.SubprocessError) as exc:
        raise RuntimeError('Could not inventory bundled FFmpeg: '+str(exc)) from exc
    yt=ROOT/'build/vendor/yt-dlp.exe'
    if yt.exists():
        run=subprocess.run([str(yt),'--version'],capture_output=True,text=True,timeout=40,check=True)
        binaries.append({'name':'yt-dlp.exe','version':run.stdout.strip(),'sha256':hashlib.sha256(yt.read_bytes()).hexdigest(),'binaryMayContainAdditionalThirdPartyComponents':True,'reviewRequired':True})
    else:raise RuntimeError('Download build/vendor/yt-dlp.exe before collecting licences')
    # Full upstream legal texts. URLs and hashes are saved with them.
    upstream=OUT/'upstream';upstream.mkdir()
    sources=[]
    for name,url in {
      'yt-dlp-Unlicense.txt':'https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/LICENSE',
      'FFmpeg-COPYING-LGPL-2.1.txt':'https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/COPYING.LGPLv2.1',
      'FFmpeg-COPYING-GPL-2.txt':'https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/COPYING.GPLv2',
      'FFmpeg-COPYING-GPL-3.txt':'https://raw.githubusercontent.com/FFmpeg/FFmpeg/master/COPYING.GPLv3',
      'yt-dlp-THIRD-PARTY-NOTICES.txt':'https://raw.githubusercontent.com/yt-dlp/yt-dlp/master/THIRD_PARTY_LICENSES.txt'
    }.items():
        data=urllib.request.urlopen(url,timeout=60).read()
        if len(data)<100:raise RuntimeError('Incomplete upstream licence: '+url)
        (upstream/name).write_bytes(data);sources.append({'url':url,'file':name,'sha256':hashlib.sha256(data).hexdigest()})
    report={'notice':'Exact installed packages; includes build tools that might not ship. Re-run for every build. Upstream master notices are reference copies; verify them against each shipped binary version. Inventory does not grant artwork rights or fulfil GPL corresponding-source obligations.','packages':packages,'binaries':binaries,'upstreamReferences':sources}
    (OUT/'MANIFEST.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Licences inventoried:',len(packages),'packages;',sum(p['reviewRequired'] for p in packages),'require file review.')

if __name__=='__main__':main()
