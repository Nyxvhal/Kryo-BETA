"""Deterministic native-boundary tests; not an actual Windows desktop test."""
import base64, ctypes, hashlib, json, subprocess, tempfile, threading, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from PIL import Image
from kryonyx import avatars, tray

class LiveAvatarTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.dp=patch.object(avatars,'data_dir',return_value=self.tmp.name);self.dp.start()
        self.old_callback=avatars._live_icon_callback;avatars.set_live_icon_callback(None)
    def tearDown(self):
        avatars.set_live_icon_callback(self.old_callback);self.dp.stop();self.tmp.cleanup()
    def test_selection_commits_and_uses_immutable_content_path(self):
        callback=MagicMock();avatars.set_live_icon_callback(callback)
        result=avatars.choose('collection-001-ironmouse');p=Path(result['icon'])
        source=Path(avatars.ico_path(result['id'])).read_bytes()
        self.assertEqual(p.stem,hashlib.sha256(source).hexdigest())
        self.assertEqual(p.read_bytes(),source);self.assertEqual((self.root/'icon.ico').read_bytes(),source)
        self.assertEqual(avatars.current(),result['id']);callback.assert_called_once_with(str(p))
        other=avatars.choose(avatars.DEFAULT_AVATAR)
        self.assertNotEqual(other['icon'],result['icon']);self.assertEqual(p.read_bytes(),source)
        self.assertFalse(other['shortcuts'])
    def test_missing_icon_cannot_claim_success_or_change_selection(self):
        avatars.choose(avatars.DEFAULT_AVATAR);before=(self.root/'icon.ico').read_bytes()
        with patch.object(avatars,'ico_path',return_value=str(self.root/'missing.ico')):
            with self.assertRaises(ValueError):avatars.choose('collection-001-ironmouse')
        self.assertEqual(avatars.current(),avatars.DEFAULT_AVATAR)
        self.assertEqual((self.root/'icon.ico').read_bytes(),before)
    def test_state_failure_rolls_back_active_icon(self):
        avatars.choose(avatars.DEFAULT_AVATAR);before=(self.root/'icon.ico').read_bytes();original=avatars._atomic_bytes
        def fail(path,content):
            if path.endswith('avatar.json'):raise OSError('read-only state')
            return original(path,content)
        with patch.object(avatars,'_atomic_bytes',side_effect=fail):
            with self.assertRaises(ValueError):avatars.choose('collection-001-ironmouse')
        self.assertEqual((self.root/'icon.ico').read_bytes(),before)
        self.assertEqual(avatars.current(),avatars.DEFAULT_AVATAR)
    def test_live_update_precedes_shortcut_job_and_selections_are_serial(self):
        order=[];entered=threading.Event();release=threading.Event()
        def shortcuts(icon):
            order.append(('links',icon));entered.set();release.wait(2)
            return {'updated':1,'failed':0,'skipped':0}
        with patch.object(avatars,'_windows_supported',return_value=True),patch.object(avatars,'set_window_icon',side_effect=lambda _,icon:order.append(('window',icon)) or True),patch.object(avatars,'_apply_shortcuts',side_effect=shortcuts):
            a=threading.Thread(target=avatars.choose,args=('collection-001-ironmouse',));a.start();self.assertTrue(entered.wait(2))
            b=threading.Thread(target=avatars.choose,args=(avatars.DEFAULT_AVATAR,));b.start();time.sleep(.03)
            self.assertEqual([x[0] for x in order],['window','links'])
            release.set();a.join(3);b.join(3)
        self.assertEqual([x[0] for x in order],['window','links','window','links'])
        self.assertEqual(avatars.current(),avatars.DEFAULT_AVATAR)
    def test_shortcut_payload_quotes_paths_and_validates_targets(self):
        paths=[r"C:\Users\O'Neil\Desktop\Крионикс.lnk"]
        script=avatars._shortcut_script(r"C:\Users\O'Neil\icon.ico",paths)
        data=script.split("FromBase64String('")[1].split("')")[0]
        payload=json.loads(base64.b64decode(data));self.assertEqual(payload['links'],paths)
        self.assertNotIn("O'Neil",script);self.assertIn('$p.targets -contains $target',script)
        self.assertIn("$l.Arguments.IndexOf",script)
    def test_shortcut_process_reports_actual_result(self):
        with patch.object(avatars,'_find_shortcuts',return_value=['one.lnk','two.lnk']),patch.object(avatars.subprocess,'run',return_value=SimpleNamespace(stdout='{"updated":1,"failed":1,"skipped":0}')) as run,patch.object(avatars,'_refresh_shell') as refresh:
            report=avatars._apply_shortcuts('icon.ico');self.assertEqual(report['failed'],1)
            args=run.call_args.args[0];self.assertIn('-EncodedCommand',args)
            script=base64.b64decode(args[-1]).decode('utf-16le');self.assertIn('ConvertFrom-Json',script)
            refresh.assert_called_once_with(['one.lnk','two.lnk'])
    def test_shortcut_timeout_does_not_claim_updated(self):
        with patch.object(avatars,'_find_shortcuts',return_value=['one.lnk']),patch.object(avatars.subprocess,'run',side_effect=subprocess.TimeoutExpired('powershell',20)):
            self.assertEqual(avatars._apply_shortcuts('icon.ico'),{'updated':0,'failed':1,'skipped':0})
    def test_pinned_and_onedrive_shortcut_roots(self):
        env={k:str(self.root/k) for k in ['APPDATA','ProgramData','USERPROFILE','PUBLIC','OneDrive']}
        pinned=Path(env['APPDATA'])/'Microsoft/Internet Explorer/Quick Launch/User Pinned/TaskBar';pinned.mkdir(parents=True)
        cloud=Path(env['OneDrive'])/'Desktop';cloud.mkdir(parents=True)
        common=Path(env['PUBLIC'])/'Desktop';common.mkdir(parents=True)
        for p in [pinned/'Kryonyx Music.lnk',cloud/'Крионикс.lnk',common/'Kryonyx.lnk'] :p.write_text('fixture')
        with patch.dict(avatars.os.environ,env,clear=True):
            links=avatars._find_shortcuts();self.assertEqual(len(links),3)
    def test_pointer_safe_window_api(self):
        user=MagicMock()
        with patch.object(ctypes,'WinDLL',return_value=user,create=True):avatars._win_icon_api()
        from ctypes import wintypes
        self.assertIs(user.LoadImageW.restype,wintypes.HANDLE)
        self.assertEqual(user.SendMessageTimeoutW.argtypes[:4],[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM])
    def test_window_uses_process_hwnd_not_caption_and_manages_owned_handles(self):
        hwnd=2**44+9;user=MagicMock();user.IsWindow.return_value=True;user.LoadImageW.side_effect=[2**45+i for i in range(1,7)];user.SendMessageTimeoutW.return_value=1
        with patch.object(avatars,'_windows_supported',return_value=True),patch('kryonyx.taskbar.find_main_window',return_value=hwnd),patch.object(avatars,'_win_icon_api',return_value=user),patch.dict(avatars._window_icons,{},clear=True):
            self.assertTrue(avatars.set_window_icon('Not the actual track title','one.ico'))
            self.assertTrue(all(c.args[0]==hwnd for c in user.SendMessageTimeoutW.call_args_list))
            self.assertFalse(user.DestroyIcon.called)
            self.assertTrue(avatars.set_window_icon('Another title','two.ico'))
            self.assertEqual({c.args[0] for c in user.DestroyIcon.call_args_list},{2**45+1,2**45+2})
            user.SendMessageTimeoutW.return_value=0
            self.assertFalse(avatars.set_window_icon('Third','three.ico'))
            self.assertEqual(set(avatars._window_icons[hwnd].values()),{2**45+3,2**45+4})
            self.assertEqual(len(user.DestroyIcon.call_args_list),4)
    def test_no_window_is_not_reported_as_success(self):
        with patch.object(avatars,'_windows_supported',return_value=True),patch('kryonyx.taskbar.find_main_window',return_value=0):
            self.assertFalse(avatars.set_window_icon(icon='test.ico'))
    def test_tray_requests_reload_on_its_own_thread(self):
        t=tray.Tray('Fixture',None,lambda _:None);t._hwnd=123;user=MagicMock()
        with patch.object(tray,'IS_WINDOWS',True),patch.object(tray,'user32',user,create=True):
            t.set_icon('new.ico');self.assertTrue(t._icon_dirty);user.PostMessageW.assert_called_once_with(123,tray.WM_REFRESH,0,0)
            t._hicon=111;t._own_icon=True
            with patch.object(t,'_load_icon',return_value=222),patch.object(t,'_refresh_data') as refresh:t._refresh()
            refresh.assert_called_once();self.assertEqual(t._hicon,222);user.DestroyIcon.assert_called_once_with(111)
    def test_all_catalog_images_and_icons_decode(self):
        for item in avatars.catalog():
            with self.subTest(avatar=item['id']):
                with Image.open(avatars.ico_path(item['id'])) as im:self.assertEqual(im.format,'ICO');im.load()
                with Image.open(Path(avatars.resource_dir())/'web'/item['file'].lstrip('/')) as im:im.verify()

if __name__=='__main__':unittest.main()
