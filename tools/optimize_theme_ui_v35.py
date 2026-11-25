"""Optimize raw screenshots after tests/capture_theme_ui_v35.cjs. Requires Pillow."""
from pathlib import Path
from PIL import Image
r=Path(__file__).resolve().parents[1]/'kryonyx/web/img/theme-ui'
for p in r.glob('*.png'):
    im=Image.open(p).convert('RGB').resize((880,592),Image.Resampling.LANCZOS)
    im.save(p.with_suffix('.webp'),'WEBP',quality=85)
    p.unlink()
