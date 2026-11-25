"""Rebuild user-provided brand exports + original 24px UI icon system. Offline."""
from pathlib import Path
import json,re,base64,hashlib,subprocess,tempfile
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
A=ROOT/'assets/brand-v60';im=Image.open(A/'Kryo.png').convert('RGBA')
sizes=[(n,n) for n in (16,20,24,32,40,48,64,128,256)]
for p in ('build/icon.ico','kryonyx/web/favicon.ico','kryonyx/icons/kryonyx-core.ico'):
 im.save(ROOT/p,format='ICO',sizes=sizes)
for p,n in [('build/icon-1024.png',1024),('kryonyx/web/icon.png',256),('kryonyx/web/img/avatars/kryonyx-core.png',512)]:
 im.resize((n,n),Image.Resampling.LANCZOS).save(ROOT/p)
im.resize((128,128),Image.Resampling.LANCZOS).save(ROOT/'kryonyx/web/img/avatars/thumbs/kryonyx-core.webp',lossless=True)
icons=json.loads((A/'icons.json').read_text());group=lambda s:'<g fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'+s+'</g>'
html=ROOT/'kryonyx/web/index.html';text=html.read_text()
for key,paths in icons.items():
 replacement='<symbol id="i-'+key+'" viewBox="0 0 24 24" data-kryo60="'+key+'">'+group(paths)+'</symbol>'
 text,n=re.subn(r'<symbol id="i-'+re.escape(key)+r'"[^>]*>.*?</symbol>',lambda _:replacement,text,flags=re.S)
 assert n==1,(key,n)
html.write_text(text)
# Same paths in clip controls and globally shared symbols. No separate hand-drawn set.
js="""/* Original Kryonyx v60: 24px, optical safe area, consistent 1.75px strokes. */
'use strict';
const KryoIcons60={paths:PATHS,aliases:{settings:'gear',full:'expand',volume:'vol',theater:'youtube',cc:'lyrics'},create(name){name=this.aliases[name]||name;const s=document.createElementNS('http://www.w3.org/2000/svg','svg');s.setAttribute('viewBox','0 0 24 24');s.setAttribute('aria-hidden','true');s.dataset.kryo60=name;s.innerHTML='<g fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">'+(this.paths[name]||this.paths.note)+'</g>';return s}};
""".replace('PATHS',json.dumps(icons,separators=(',',':')))
(ROOT/'kryonyx/web/js/brand-icons-v60.js').write_text(js)
# Standalone sources, useful for auditing and native taskbar exports.
folder=A/'icons';folder.mkdir(exist_ok=True)
for name,paths in icons.items():
 svg='<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" color="white">'+group(paths)+'</svg>'
 (folder/(name+'.svg')).write_text(svg)
 if name in ('prev','play','pause','next'):
  with tempfile.TemporaryDirectory() as d:
   png=Path(d)/'icon.png';subprocess.run(['magick','-background','none','-density','768',str(folder/(name+'.svg')),'-resize','256x256',str(png)],check=True)
   Image.open(png).convert('RGBA').save(ROOT/'kryonyx/icons/media'/f'{name}.ico',format='ICO',sizes=sizes)
# Installer is loaded as inline HTML: embed, do not rely on relative filesystem URLs.
p=ROOT/'installer/wizard.html';s=p.read_text();data=base64.b64encode((ROOT/'kryonyx/web/icon.png').read_bytes()).decode()
s=re.sub(r'<span class="logo">.*?</span>',lambda _:'<img class="logo" alt="Kryonyx" width="40" height="40" src="data:image/png;base64,'+data+'">',s,count=1)
p.write_text(s)
print('BRAND60_BUILT',len(icons),'icons; logo',hashlib.sha256((A/'Kryo.png').read_bytes()).hexdigest())
