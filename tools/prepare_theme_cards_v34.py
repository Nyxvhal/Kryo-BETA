"""Rebuild gallery thumbnails from existing references. Requires Pillow. Originals are not modified."""
from pathlib import Path
from PIL import Image, ImageOps
R=Path(__file__).resolve().parents[1]
web=R/"kryonyx/web"
# Derived, local thumbnails; original source artwork and rights index stay intact.
out=web/'img/theme-cards';out.mkdir(exist_ok=True)
for p in (web/'img/theme-refs').glob('*.webp'):
 im=Image.open(p).convert('RGBA');w,h=im.size
 if h/w>1.18:
  cw=w*.86;ch=cw*.82;x=(w-cw)/2;y=h*.025
  im=im.crop((round(x),round(y),round(x+cw),round(min(h,y+ch))))
 im=ImageOps.fit(im,(560,420),method=Image.Resampling.LANCZOS,centering=(.5,.38))
 im.save(out/p.name,'WEBP',quality=92)
