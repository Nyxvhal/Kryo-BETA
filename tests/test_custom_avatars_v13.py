import io, json, tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image, PngImagePlugin
from kryonyx import avatars, avatarshop, custom_avatars as custom

def picture(fmt='PNG', size=(700,400)):
    b=io.BytesIO();im=Image.new('RGB',size,(34,180,205))
    info=PngImagePlugin.PngInfo();info.add_text('private-comment','remove me')
    im.save(b,format=fmt,**({'pnginfo':info} if fmt=='PNG' else {}));return b.getvalue()

class CustomAvatarTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.p1=patch.object(avatars,'data_dir',return_value=self.tmp.name);self.p1.start()
        self.p2=patch.object(avatarshop,'cache_dir',return_value=self.tmp.name);self.p2.start()
    def tearDown(self):
        self.p1.stop();self.p2.stop();self.tmp.cleanup()
    def create(self,fmt='PNG',name='Radio <Play>'):
        return custom.create(self.root,picture(fmt),name)
    def test_three_formats_normalize_strip_metadata(self):
        for fmt in ['PNG','JPEG','WEBP']:
            with self.subTest(fmt=fmt):
                item=self.create(fmt)
                im=Image.open(custom.asset(self.root,item['id']));self.assertEqual(im.size,(512,512));self.assertNotIn('private-comment',im.info)
                self.assertEqual(Image.open(custom.asset(self.root,item['id'],'thumb.png')).size,(128,128))
                self.assertTrue(custom.asset(self.root,item['id'],'icon.ico').stat().st_size>0)
    def test_catalog_selection_and_reloaded_catalog_persist(self):
        n=len(avatars.catalog());item=self.create();avatars.choose(item['id'])
        self.assertEqual(avatars.current(),item['id']);self.assertEqual(len(avatars.catalog()),n+1)
        self.assertEqual(avatars.web_icon(),str(custom.asset(self.root,item['id'])))
        self.assertEqual(Path(avatars.active_icon()).read_bytes(),custom.asset(self.root,item['id'],'icon.ico').read_bytes())
        with patch.object(avatars,'_catalog',None):self.assertEqual(avatars.current(),item['id'])
    def test_download_and_custom_pack(self):
        item=self.create();self.assertEqual(avatarshop.asset(item['id']),custom.asset(self.root,item['id']))
        with zipfile.ZipFile(avatarshop.pack('custom')) as z:
            self.assertEqual(json.loads(z.read('manifest.json'))[0]['name'],'Radio <Play>')
            self.assertIn('custom/png/'+item['id']+'.png',z.namelist())
        with self.assertRaises(ValueError):avatarshop.asset(item['id'],'svg')
    def test_delete_only_custom(self):
        item=self.create();custom.remove(self.root,item['id']);self.assertIsNone(avatars.by_id(item['id']))
        for aid in [avatars.DEFAULT_AVATAR,'../avatar.json','custom-../../a','',None]:
            with self.assertRaises(ValueError):custom.remove(self.root,aid)
    def test_payload_limits_and_bad_images(self):
        for payload in [b'',b'bad',b'<svg/>',b'a'*(custom.MAX_BYTES+1)]:
            with self.assertRaises(ValueError):custom.create(self.root,payload,'Test')
        for size in [(15,50),(8193,16)]:
            with self.assertRaises(ValueError):custom.create(self.root,picture(size=size),'Test')
    def test_names_never_paths(self):
        item=self.create(name='../../x <script> & Play');self.assertTrue(item['id'].startswith('custom-'))
        self.assertEqual(item['name'],'../../x <script> & Play');self.assertFalse((self.root/'x').exists())
        for name in ['','  ','x'*81]:
            with self.assertRaises(ValueError):self.create(name=name)
    def test_animated_image_rejected(self):
        b=io.BytesIO();frames=[Image.new('RGBA',(40,40),c) for c in ['red','blue']]
        frames[0].save(b,format='PNG',save_all=True,append_images=frames[1:],duration=80,loop=0)
        with self.assertRaises(ValueError):custom.create(self.root,b.getvalue(),'Animated')
    def test_cap_and_symlink_protection(self):
        with patch.object(custom,'MAX_ITEMS',1):
            self.create()
            with self.assertRaises(ValueError):self.create()
        outside=self.root/'outside';outside.mkdir();(outside/'keep').write_text('safe')
        aid='custom-'+'f'*32
        try:(custom.folder(self.root)/aid).symlink_to(outside,target_is_directory=True)
        except OSError:self.skipTest('Creating symlinks requires elevated permissions on this platform')
        with self.assertRaises(ValueError):custom.remove(self.root,aid)
        self.assertTrue((outside/'keep').exists());self.assertEqual(len(custom.catalog(self.root)),1)


class ReleaseConfigurationTests(unittest.TestCase):
    def test_single_i18n_script_and_release_version(self):
        root=Path(__file__).resolve().parents[1]
        html=(root/'kryonyx/web/index.html').read_text(encoding='utf-8')
        self.assertEqual(html.count('/js/i18n-v13.js?'),1)
        # Source revisions now have release notes; an empty file is no longer the release contract.
        self.assertRegex((root/'CHANGELOG.md').read_text(encoding='utf-8'), r'^# Source revision v[0-9]+')
        from kryonyx import __version__
        self.assertEqual(__version__,'1.0.0')

if __name__=='__main__':unittest.main()
