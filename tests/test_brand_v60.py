"""Offline identity and shared icon regression checks."""
import json,re,unittest
from pathlib import Path
from PIL import Image
from kryonyx import avatars
ROOT=Path(__file__).resolve().parents[1]
class Brand60Tests(unittest.TestCase):
 def test_default_and_legacy(self):
  self.assertEqual(avatars.DEFAULT_AVATAR,'kryonyx-core')
  self.assertEqual(avatars.RENAMED['kryonyx-02-black-violet'],'kryonyx-core')
 def test_ico_multires(self):
  for f in ['build/icon.ico','kryonyx/web/favicon.ico','kryonyx/icons/kryonyx-core.ico']:
   with Image.open(ROOT/f) as im:
    self.assertTrue({(16,16),(32,32),(48,48),(256,256)}.issubset(im.ico.sizes()),f)
 def test_shared_geometry(self):
  icons=json.loads((ROOT/'docs/ICONS_V68.json').read_text())
  html=(ROOT/'kryonyx/web/index.html').read_text();js=(ROOT/'kryonyx/web/js/brand-icons-v60.js').read_text()
  source=json.loads(re.search(r'paths:(\{.*?\}),aliases:',js).group(1))
  self.assertEqual(icons,source)
  for name,paths in icons.items():
   if name=='wave':continue # Wave is created dynamically.
   self.assertIn('id="i-'+name+'"',html)
   self.assertIn(paths,html)
  self.assertIn('KryoIcons60.create(name)',(ROOT/'kryonyx/web/js/watch-v59.js').read_text())
  self.assertGreaterEqual(len(icons),50)
 def test_logo_exports(self):
  with Image.open(ROOT/'assets/brand-v60/Kryo.png') as src:
   for f in ['build/icon-1024.png','kryonyx/web/icon.png','kryonyx/web/img/avatars/kryonyx-core.png']:
    with Image.open(ROOT/f) as im:
     self.assertEqual(src.convert('RGBA').resize(im.size,Image.Resampling.LANCZOS).tobytes(),im.convert('RGBA').tobytes())
 def test_installer_embedded_logo(self):
  self.assertIn('<img class="logo"', (ROOT/'installer/wizard.html').read_text())
  self.assertIn('data:image/png;base64,', (ROOT/'installer/wizard.html').read_text())
if __name__=='__main__':unittest.main()
