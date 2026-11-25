"""v71 setup bridge: update detection, free space, polite close, log progress, error mapping."""
import importlib.util
import os
from pathlib import Path
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('installer71', ROOT / 'installer/bootstrap.py')
inst = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inst)
MB = 1024 * 1024


def fake_run(code):
    return patch.object(inst.subprocess, 'run', return_value=SimpleNamespace(returncode=code))


class SurfaceTests(unittest.TestCase):
    def test_page_sees_only_methods_and_plain_values(self):
        # pywebview exposes public attributes of js_api recursively: no window/paths/locks.
        api = inst.Installer()
        for name in dir(api):
            if name.startswith('_'):
                continue
            value = getattr(api, name)
            self.assertTrue(callable(value) or isinstance(value, (str, dict, int, type(None))), name)
        for hidden in ('window', 'log_path', 'pack', 'prev', 'lock'):
            self.assertFalse(hasattr(api, hidden), hidden)
        self.assertTrue({'info', 'space', 'running', 'browse', 'install', 'status', 'open_log', 'finish', 'close'} <= set(dir(api)))

    def test_info_reports_version_space_and_no_previous_off_windows(self):
        info = inst.Installer().info()
        self.assertTrue(info['version'])
        self.assertIsNone(info['previous'])
        self.assertIsNone(info['tasks'])
        self.assertEqual(set(info['space']), {'need', 'free', 'ok'})
        self.assertFalse(info['running'])

    def test_previous_install_prefills_folder_version_and_options(self):
        prev = {'path': 'C:\\Apps\\Kryonyx', 'version': '0.9.0', 'tasks': 'desktopicon'}
        with patch.object(inst, '_previous', return_value=prev):
            api = inst.Installer()
        self.assertEqual(api.destination, 'C:\\Apps\\Kryonyx')
        info = api.info()
        self.assertEqual(info['previous'], {'path': 'C:\\Apps\\Kryonyx', 'version': '0.9.0'})
        self.assertEqual(info['tasks'], {'desktop': True, 'autostart': False})
        with patch.object(inst, '_previous', return_value={**prev, 'tasks': 'autostart, desktopicon'}):
            self.assertEqual(inst.Installer().info()['tasks'], {'desktop': True, 'autostart': True})
        with patch.object(inst, '_previous', return_value={**prev, 'tasks': None}):
            self.assertIsNone(inst.Installer().info()['tasks'])

    def test_payload_manifest_is_read_defensively(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'installer').mkdir()
            manifest = Path(tmp) / 'installer' / 'payload.json'
            with patch.object(inst, 'ROOT', Path(tmp)):
                self.assertEqual(inst._payload(), {})
                manifest.write_text('\ufeff{"version": "1.2.3", "files": 10, "bytes": 2048, "extra": 1}', encoding='utf-8')
                self.assertEqual(inst._payload(), {'version': '1.2.3', 'files': 10, 'bytes': 2048})
                manifest.write_text('[1, 2]', encoding='utf-8')
                self.assertEqual(inst._payload(), {})
                manifest.write_text('{broken', encoding='utf-8')
                self.assertEqual(inst._payload(), {})

    def test_engine_name_follows_the_built_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'dist').mkdir()
            with patch.object(inst, 'ROOT', Path(tmp)):
                self.assertEqual(inst._engine().name, 'Kryo-1.0.0-engine.exe')
                (Path(tmp) / 'dist' / 'Kryo-1.2.0-engine.exe').write_bytes(b'')
                self.assertEqual(inst._engine().name, 'Kryo-1.2.0-engine.exe')


class SpaceTests(unittest.TestCase):
    def setUp(self):
        self.api = inst.Installer()
        self.api._pack = {'files': 100, 'bytes': 100 * MB}
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_low_space_blocks_and_enough_space_passes(self):
        with patch.object(inst.shutil, 'disk_usage', return_value=SimpleNamespace(free=120 * MB)):
            low = self.api.space(self.tmp.name)
        self.assertEqual(low, {'need': 100 * MB, 'free': 120 * MB, 'ok': False})
        with patch.object(inst.shutil, 'disk_usage', return_value=SimpleNamespace(free=10 * 1024 * MB)):
            self.assertTrue(self.api.space(self.tmp.name)['ok'])

    def test_unknown_payload_never_blocks(self):
        self.api._pack = {}
        with patch.object(inst.shutil, 'disk_usage', return_value=SimpleNamespace(free=1)):
            result = self.api.space(self.tmp.name)
        self.assertIsNone(result['need'])
        self.assertTrue(result['ok'])

    def test_missing_folder_uses_nearest_existing_parent(self):
        target = Path(self.tmp.name) / 'not' / 'yet' / 'there'
        with patch.object(inst.shutil, 'disk_usage', return_value=SimpleNamespace(free=5 * 1024 * MB)) as usage:
            self.assertTrue(self.api.space(str(target))['ok'])
        self.assertEqual(usage.call_args.args[0], self.tmp.name)

    def test_update_in_place_only_needs_the_difference(self):
        self.api._prev = {'path': self.tmp.name, 'version': '1.0.0', 'tasks': ''}
        with patch.object(inst, '_folder_size', return_value=90 * MB) as size, \
             patch.object(inst.shutil, 'disk_usage', return_value=SimpleNamespace(free=120 * MB)):
            first = self.api.space(self.tmp.name)
            self.api.space(self.tmp.name)
        self.assertEqual(first['need'], 10 * MB)
        self.assertTrue(first['ok'])
        self.assertEqual(size.call_count, 1)   # measured once, then cached
        with patch.object(inst.shutil, 'disk_usage', return_value=SimpleNamespace(free=120 * MB)):
            other = self.api.space(str(Path(self.tmp.name) / 'elsewhere'))
        self.assertEqual(other['need'], 100 * MB)


class FolderTests(unittest.TestCase):
    def test_busy_folder_gets_own_subfolder(self):
        api = inst.Installer()
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            empty = base / 'empty'
            empty.mkdir()
            self.assertEqual(api._suggest(empty), empty)
            busy = base / 'busy'
            busy.mkdir()
            (busy / 'other.txt').write_text('x')
            self.assertEqual(api._suggest(busy), busy / 'Kryo')
            named = base / 'Kryonyx Music'
            named.mkdir()
            (named / 'x').write_text('x')
            self.assertEqual(api._suggest(named), named)
            existing = base / 'old'
            existing.mkdir()
            (existing / inst.APP_EXE).write_bytes(b'')
            self.assertEqual(api._suggest(existing), existing)

    def test_install_validates_folder_before_touching_anything(self):
        api = inst.Installer()
        api._pack = {'files': 10, 'bytes': 100 * MB}
        with patch.object(inst, 'WINDOWS', True), patch.object(inst.threading, 'Thread') as thread:
            self.assertEqual(api.install('relative\\folder', True, False, True)['error'], 'path')
            self.assertEqual(api.install('/tmp/a"b', True, False, True)['error'], 'path')
            self.assertEqual(api.install('/' + 'x' * 230, True, False, True)['error'], 'path')
            self.assertEqual(api.install('/', True, False, True)['error'], 'root')
            with tempfile.TemporaryDirectory() as tmp:
                with patch.object(inst.shutil, 'disk_usage', return_value=SimpleNamespace(free=MB)):
                    low = api.install(tmp, True, False, True)
                self.assertEqual(low, {'ok': False, 'error': 'space', 'need': 100 * MB, 'free': MB})
                with patch.object(inst.shutil, 'disk_usage', return_value=SimpleNamespace(free=10 * 1024 * MB)):
                    self.assertEqual(api.install(tmp, True, False, True), {'ok': True})
            thread.assert_called_once()
        self.assertEqual(api.state['phase'], 'installing')
        self.assertEqual(api.state['total'], 10)
        self.assertEqual(api.state['files'], 0)
        self.assertIsNone(api.state['progress'])

    def test_off_windows_never_starts_the_engine(self):
        api = inst.Installer()
        with patch.object(inst.threading, 'Thread') as thread:
            self.assertEqual(api.install(tempfile.gettempdir(), True, False, True)['error'], 'windows')
        thread.assert_not_called()


class EngineTests(unittest.TestCase):
    def test_engine_arguments_close_apps_and_write_a_log(self):
        api = inst.Installer()
        api.destination = 'C:\\Kryonyx'
        with fake_run(0) as run:
            api._run(True, False)
        args, kwargs = run.call_args.args[0], run.call_args.kwargs
        for flag in ('/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART', '/SP-', '/CURRENTUSER',
                     '/CLOSEAPPLICATIONS', '/NORESTARTAPPLICATIONS', '/DIR=C:\\Kryonyx', '/TASKS=desktopicon'):
            self.assertIn(flag, args)
        self.assertTrue(any(a.startswith('/LOG=') and a.endswith('.log') for a in args))
        self.assertIn('creationflags', kwargs)
        self.assertNotIn('shell', kwargs)
        self.assertEqual(api.status()['phase'], 'done')
        self.assertEqual(api.status()['progress'], 1.0)

    def test_exit_codes_become_specific_errors(self):
        for code, key in {1: 'init', 2: 'cancelled', 3: 'fatal', 4: 'fatal', 5: 'locked', 6: 'cancelled',
                          7: 'prepare', 8: 'reboot', 99: 'engine', -1: 'engine'}.items():
            api = inst.Installer()
            with fake_run(code):
                api._run(False, False)
            state = api.status()
            self.assertEqual((state['phase'], state['error'], state['code']), ('error', key, code), code)
            self.assertFalse(api.finish(True))

    def test_missing_engine_is_reported(self):
        api = inst.Installer()
        with patch.object(inst.subprocess, 'run', side_effect=FileNotFoundError('engine')):
            api._run(False, False)
        self.assertEqual(api.status()['error'], 'missing')

    def test_running_app_that_will_not_close_stops_before_the_engine(self):
        api = inst.Installer()
        with patch.object(inst, 'WINDOWS', True), patch.object(inst, '_close_running', return_value=False), fake_run(0) as run:
            api._run(True, False)
        run.assert_not_called()
        self.assertEqual(api.status()['error'], 'running')

    def test_close_running_asks_politely(self):
        with patch.object(inst, '_running', side_effect=[True, True, False]), \
             patch.object(inst, '_running_name', side_effect=lambda name: name == inst.APP_EXE), \
             patch.object(inst.time, 'sleep'), fake_run(0) as run:
            self.assertTrue(inst._close_running(timeout=5))
        args = run.call_args.args[0]
        self.assertEqual(args[:3], ['taskkill', '/IM', inst.APP_EXE])
        self.assertNotIn('/F', args)
        with patch.object(inst, '_running', return_value=False), fake_run(0) as run:
            self.assertTrue(inst._close_running())
        run.assert_not_called()

    def test_finish_launches_with_a_clean_environment(self):
        api = inst.Installer()
        api.state = {'phase': 'done', 'error': '', 'code': 0}
        api.destination = tempfile.gettempdir()
        api._window = MagicMock()
        with patch.dict(os.environ, {'_PYI_APPLICATION_HOME_DIR': 'x', '_MEIPASS2': 'y', 'KEEP71': '1'}), \
             patch.object(inst.subprocess, 'Popen') as popen:
            self.assertTrue(api.finish(True))
        kwargs = popen.call_args.kwargs
        self.assertEqual(kwargs['cwd'], api.destination)
        self.assertEqual(kwargs['env']['KEEP71'], '1')
        self.assertEqual(kwargs['env']['PYINSTALLER_RESET_ENVIRONMENT'], '1')
        self.assertFalse(any(k.startswith(('_PYI_', '_MEIPASS')) for k in kwargs['env']))
        api._window.destroy.assert_called_once()

    def test_open_log_needs_windows_and_a_log(self):
        api = inst.Installer()
        self.assertFalse(api.open_log())


class LogProgressTests(unittest.TestCase):
    def watch(self, total, lines):
        api = inst.Installer()
        api._pack = {'files': total} if total else {}
        with tempfile.TemporaryDirectory() as tmp:
            api._log_path = Path(tmp) / 'setup.log'
            stop = threading.Event()
            worker = threading.Thread(target=api._watch, args=(stop,), daemon=True)
            worker.start()
            with open(api._log_path, 'w', encoding='utf-8') as fh:
                for line in lines:
                    fh.write('2025-01-01 10:00:00.000   ' + line + '\n')
                    fh.flush()
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and api.state.get('files', 0) < min(total or 99, lines.count('-- File entry --')):
                time.sleep(0.05)
            time.sleep(0.4)
            stop.set()
            worker.join(2)
        return api.state

    def test_file_entries_drive_real_progress(self):
        state = self.watch(4, ['Starting the installation process.', '-- File entry --', 'Dest filename: a',
                               '-- File entry --', '-- File entry --', 'Successfully installed the file.'])
        self.assertEqual(state['files'], 3)
        self.assertEqual(state['progress'], 0.75)
        self.assertEqual(state['step'], 'copy')

    def test_progress_never_claims_done_early(self):
        state = self.watch(2, ['-- File entry --'] * 5 + ['-- Icon entry --'])
        self.assertEqual(state['files'], 2)
        self.assertEqual(state['progress'], 0.99)
        self.assertEqual(state['step'], 'shortcuts')

    def test_without_manifest_progress_stays_indeterminate(self):
        state = self.watch(0, ['Shutting down applications using our files.', '-- File entry --'])
        self.assertNotIn('progress', state)
        self.assertEqual(state['files'], 1)
        self.assertEqual(state['step'], 'copy')


class BuildFilesTests(unittest.TestCase):
    def test_inno_script_update_rules(self):
        iss = (ROOT / 'build/installer.iss').read_text(encoding='utf-8-sig')
        for needle in ('#ifndef AppVersion', 'CloseApplications=yes', 'RestartApplications=no', '*.pyd',
                       '[InstallDelete]', 'Name: "{app}\\_internal"', 'Tasks: not desktopicon', 'Tasks: not autostart',
                       'VersionInfoVersion={#AppVersion}', 'AppId={{8F3D2A61-6C4E-4C9B-9E2A-5B1C7D0A9E11}'):
            self.assertIn(needle, iss)
        self.assertNotIn('{localappdata}\\KryonyxMusic', iss.split('[InstallDelete]')[1].split('[Files]')[0])

    def test_build_script_shares_one_version_and_bundles_the_manifest(self):
        ps1 = (ROOT / 'build/build_windows.ps1').read_text(encoding='utf-8-sig')
        for needle in ('"/DAppVersion=$appVersion"', "build\\payload.json;installer", '$engine;dist',
                       'Kryo-$appVersion-setup', 'Test-Path $engine'):
            self.assertIn(needle, ps1)
        self.assertNotIn('KryonyxMusic-1.0.0-setup', ps1)

    def test_wizard_is_self_contained(self):
        html = (ROOT / 'installer/wizard.html').read_text(encoding='utf-8')
        self.assertNotIn('<script src', html)
        self.assertNotIn('<link', html)
        self.assertNotRegex(html, r'url\((?!data:)["\']?https?:')
        for key in ('locked', 'cancelled', 'running', 'space', 'engine', 'missing'):
            self.assertIn(key + ':', html)


if __name__ == '__main__':
    unittest.main()
