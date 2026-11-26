import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from kryonyx import avatars,avatarshop
ROOT=Path(__file__).resolve().parents[1]
class CatalogV16Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items=json.loads((ROOT/'kryonyx/avatars.json').read_text())
    def test_retired_season_removed_from_assets(self):
        self.assertFalse(any(x['id']=='portrait-v12-ironmouse-season-0' for x in self.items))
        self.assertEqual(list((ROOT/'kryonyx').rglob('*season-0*')),[])
    def test_reference_only_portraits_and_monogram_order(self):
        retired=['portrait-v12-ironmouse']+[f'portrait-v12-ironmouse-season-{i}' for i in range(1,5)]
        self.assertTrue(all(r['id'] not in retired for r in self.items))
        ids=[r['id'] for r in self.items if r.get('collection')=='redesigned']
        self.assertIn('collection-001-fortnite',ids)
        self.assertEqual(len(self.items),233)
        manifest=ROOT/'research/v12/artwork-manifest.json'
        if manifest.is_file():
            refs=json.loads(manifest.read_text())
            self.assertTrue(all('vt-ironmouse-season-'+str(i) in {r['themeId'] for r in refs} for i in range(1,5)))
    def test_all_imported_hashes_and_preserved_purple_assets(self):
        imp=ROOT/'research/v16/avatar-import.json'
        if not imp.is_file():self.skipTest('research/v16/avatar-import.json is not in this repository')
        report=json.loads(imp.read_text())
        self.assertEqual(report['replaced'],528)
        for item in report['imported']:
            for typ in ('png','svg'):
                p=ROOT/'kryonyx/web/img/avatars'
                if typ=='svg':p=p/'svg'
                self.assertEqual(hashlib.sha256((p/(item['id']+'.'+typ)).read_bytes()).hexdigest(),item[typ+'_sha256'])
        for relative,digest in report['preserved_files'].items():
            path=ROOT/relative
            if path.suffix=='.ico' and not path.exists():
                # v20 deliberately removes redundant ICOs, not source artwork.
                # Verify the preserved PNG byte-for-byte and the lazy ICO contract.
                png='kryonyx/web/img/avatars/'+path.stem+'.png'
                self.assertEqual(hashlib.sha256((ROOT/png).read_bytes()).hexdigest(),report['preserved_files'][png])
                if any(item['id']==path.stem for item in self.items):
                    from PIL import Image
                    with Image.open(avatars.ico_path(path.stem)) as icon:
                        self.assertEqual(icon.format,'ICO')
                        self.assertIn((256,256),icon.ico.sizes())
                        self.assertIn((16,16),icon.ico.sizes())
                continue
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)
    def test_catalog_ids_remain_unique(self):
        self.assertEqual(len(self.items),len({x['id'] for x in self.items}))
        self.assertEqual(sum(x.get('collection')=='redesigned' for x in self.items),145)
        self.assertTrue(any(x['id']==avatars.DEFAULT_AVATAR for x in self.items))
    def test_retired_choice_migrates(self):
        with tempfile.TemporaryDirectory() as tmp,patch('kryonyx.avatars.data_dir',return_value=tmp):
            Path(tmp,'avatar.json').write_text(json.dumps({'id':'portrait-v12-ironmouse-season-0'}))
            self.assertEqual(avatars.current(),avatars.DEFAULT_AVATAR)
    def test_reference_portrait_choices_migrate_to_purple(self):
        retired=['portrait-v12-ironmouse']+[f'portrait-v12-ironmouse-season-{i}' for i in range(1,5)]
        with tempfile.TemporaryDirectory() as tmp,patch('kryonyx.avatars.data_dir',return_value=tmp):
            for aid in retired:
                Path(tmp,'avatar.json').write_text(json.dumps({'id':aid}))
                self.assertEqual(avatars.current(),avatars.DEFAULT_AVATAR)
                result=avatars.choose(aid)
                self.assertEqual(result['id'],avatars.DEFAULT_AVATAR)
                self.assertEqual(Path(tmp,'icon.ico').read_bytes(),Path(avatars.ico_path(avatars.DEFAULT_AVATAR)).read_bytes())
    def test_active_icon_refresh_preserves_choice(self):
        with tempfile.TemporaryDirectory() as tmp,patch('kryonyx.avatars.data_dir',return_value=tmp):
            aid='collection-001-fortnite';Path(tmp,'avatar.json').write_text(json.dumps({'id':aid}));Path(tmp,'icon.ico').write_bytes(b'old')
            self.assertTrue(avatars.refresh_active_icon());self.assertEqual(avatars.current(),aid)
            self.assertEqual(Path(tmp,'icon.ico').read_bytes(),Path(avatars.ico_path(aid)).read_bytes())
            self.assertFalse(avatars.refresh_active_icon())
if __name__=='__main__':unittest.main()
