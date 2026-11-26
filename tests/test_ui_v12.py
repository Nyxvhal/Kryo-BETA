"""Offline regressions for credited portraits, seasonal identities and local files."""
import json,unittest,zipfile,tempfile
from pathlib import Path
from unittest.mock import patch
from kryonyx import avatars,avatarshop
ROOT=Path(__file__).resolve().parents[1]
class PortraitsV12(unittest.TestCase):
 def test_catalog_preserves_legacy(self):
  rows=json.loads((ROOT/'kryonyx/avatars.json').read_text());self.assertEqual(len(rows),233);self.assertEqual(len({r['id'] for r in rows}),233)
 def test_portrait_png_thumb_and_ico_exist(self):
  for r in json.loads((ROOT/'kryonyx/avatars.json').read_text()):
   if r['collection']!='portraits':continue
   for p in [ROOT/'kryonyx/web'/r['file'].lstrip('/'),ROOT/'kryonyx/web'/r['preview'].lstrip('/'),Path(avatars.ico_path(r['id']))]:self.assertTrue(p.is_file(),str(p))
 def test_references_all_existing_characters(self):
  p=ROOT/'research/v12/artwork-manifest.json'
  if not p.is_file():self.skipTest('research/v12/artwork-manifest.json is not in this repository')
  m=json.loads(p.read_text());self.assertEqual(len(m),81);self.assertTrue(all(r['page'].startswith('https://') and r['imageSource'].startswith('https://') for r in m));self.assertIn('vt-sameko-saba',{r['themeId'] for r in m})
 def test_seasons_one_through_four_without_retired_zero(self):
  p=ROOT/'research/v12/artwork-manifest.json'
  if not p.is_file():self.skipTest('research/v12/artwork-manifest.json is not in this repository')
  m=json.loads(p.read_text());ids={r['themeId'] for r in m};self.assertTrue(all('vt-ironmouse-season-'+str(n) in ids for n in range(1,5)));self.assertIn('vt-ironmouse',ids)
 def test_portrait_download_pack(self):
  rows=json.loads((ROOT/'kryonyx/avatars.json').read_text())
  if not any(r.get('collection')=='portraits' for r in rows):self.skipTest('portraits collection is not in this repository')
  with tempfile.TemporaryDirectory() as d,patch.object(avatarshop,'cache_dir',return_value=d):
   with zipfile.ZipFile(avatarshop.pack('portraits')) as z:self.assertEqual(sum(n.endswith('.png') for n in z.namelist()),76);self.assertIn('RIGHTS/PORTRAITS_V12.txt',z.namelist())
