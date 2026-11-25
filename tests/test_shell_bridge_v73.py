"""v73 optional native shell (desktop-rs): the token-protected loopback bridge.

The Rust shell starts the backend with ``--server-only`` and a random token in
KRYONYX_SHELL_TOKEN, shows the native Save As dialog itself and asks
/api/shell/save-plan and /api/shell/save to prepare and write the file.
Nothing here needs the shell, a window or the network."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aiohttp.test_utils import TestClient, TestServer

from kryonyx import audio_share, clip_export, file_exports, server, shell_bridge

TOKEN = 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0'


class Token(unittest.TestCase):
    def test_token_must_be_long_and_alphanumeric(self):
        for value, expected in (('', ''), ('short1', ''), ('x' * 31, ''), ('x' * 257, ''),
                                ('a' * 20 + '-' + 'b' * 20, ''), (TOKEN, TOKEN)):
            with patch.dict(os.environ, {shell_bridge.TOKEN_ENV: value}):
                self.assertEqual(shell_bridge.token(), expected, value)

    def test_without_a_shell_nothing_is_allowed(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop(shell_bridge.TOKEN_ENV, None)
            self.assertFalse(shell_bridge.allowed(''))
            self.assertFalse(shell_bridge.allowed(TOKEN))

    def test_header_must_match_exactly(self):
        with patch.dict(os.environ, {shell_bridge.TOKEN_ENV: TOKEN}):
            self.assertTrue(shell_bridge.allowed(TOKEN))
            self.assertFalse(shell_bridge.allowed(TOKEN[:-1]))
            self.assertFalse(shell_bridge.allowed(TOKEN + 'x'))
            self.assertFalse(shell_bridge.allowed(None))
            self.assertFalse(shell_bridge.allowed(123))
            self.assertFalse(shell_bridge.allowed('ж' * 40))

    def test_hello_names_the_app(self):
        hello = shell_bridge.hello()
        self.assertEqual(hello['app'], 'Kryo')
        for key in ('version', 'version_label', 'platform', 'data_dir', 'app_dir'):
            self.assertIn(key, hello)


class Plan(unittest.TestCase):
    def test_unknown_or_malformed_requests(self):
        with self.assertRaises(shell_bridge.BridgeError):
            shell_bridge.plan('nope', {}, 'http://127.0.0.1:1')
        with self.assertRaises(shell_bridge.BridgeError):
            shell_bridge.plan('export', ['spec'], 'http://127.0.0.1:1')

    def test_export_plan_uses_the_prepared_name(self):
        with patch.object(file_exports, 'prepare', return_value=(b'[00:01.00]hi', 'Song — Artist.lrc', '.lrc')) as prep:
            plan = shell_bridge.plan('export', {'spec': {'kind': 'lyrics'}}, 'http://127.0.0.1:8765')
        prep.assert_called_once_with({'kind': 'lyrics'}, 'http://127.0.0.1:8765')
        self.assertEqual(plan, {'name': 'Song — Artist.lrc', 'extension': '.lrc', 'filters': [['Export', ['lrc']]]})

    def test_clip_and_shared_audio_plans(self):
        with patch.object(clip_export, 'completed_clip', return_value=(Path('/x/clip.mp4'), 'Clip.mp4')):
            plan = shell_bridge.plan('clip', {'session': 'a' * 24}, 'http://127.0.0.1:1')
        self.assertEqual(plan['name'], 'Clip.mp4')
        self.assertIn(['Video', ['mp4', 'webm']], plan['filters'])
        with patch.object(audio_share, 'completed', return_value=(Path('/x/track.mp3'), 'Song.mp3')):
            plan = shell_bridge.plan('shared_audio', {'token': 'b' * 48}, 'http://127.0.0.1:1')
        self.assertEqual((plan['name'], plan['extension']), ('Song.mp3', '.mp3'))

    def test_expired_share_is_a_plain_message(self):
        with self.assertRaises(ValueError) as caught:
            shell_bridge.plan('shared_audio', {'token': 'not-a-token'}, 'http://127.0.0.1:1')
        self.assertIn('expired', str(caught.exception))


class Write(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_destination_rules(self):
        bad = ['', '   ', 'relative/name.lrc', str(self.dir / 'missing' / 'a.lrc'), 'a\x00b', None, 5]
        for path in bad:
            with self.assertRaises(shell_bridge.BridgeError, msg=repr(path)):
                shell_bridge._destination(path, '.lrc')
        with self.assertRaises(shell_bridge.BridgeError):  # a folder, not a file name
            shell_bridge._destination(str(self.dir), '')
        self.assertEqual(shell_bridge._destination(str(self.dir / 'a'), '.lrc'), self.dir / 'a.lrc')
        self.assertEqual(shell_bridge._destination(str(self.dir / 'A.LRC'), '.lrc'), self.dir / 'A.LRC')
        self.assertEqual(shell_bridge._destination(str(self.dir / 'clip.webm'), ''), self.dir / 'clip.webm')

    def test_export_is_written(self):
        with patch.object(file_exports, 'prepare', return_value=(b'lyrics', 'x.lrc', '.lrc')):
            result = shell_bridge.write('export', {'spec': {}}, str(self.dir / 'song'), 'http://127.0.0.1:1')
        self.assertEqual(result, {'saved': True, 'path': str(self.dir / 'song.lrc')})
        self.assertEqual((self.dir / 'song.lrc').read_bytes(), b'lyrics')
        self.assertEqual([p.name for p in self.dir.iterdir()], ['song.lrc'])  # no temporary files left

    def test_clip_and_shared_audio_are_copied(self):
        source = self.dir / 'cache.mp4'
        source.write_bytes(b'video' * 1000)
        with patch.object(clip_export, 'completed_clip', return_value=(source, 'Clip.mp4')):
            result = shell_bridge.write('clip', {'session': 'a' * 24}, str(self.dir / 'Mine.mp4'), 'http://127.0.0.1:1')
        self.assertTrue(result['saved'])
        self.assertEqual((self.dir / 'Mine.mp4').read_bytes(), source.read_bytes())
        mp3 = self.dir / 'track.mp3'
        mp3.write_bytes(b'ID3' + b'\0' * 100)
        with patch.object(audio_share, 'completed', return_value=(mp3, 'Song.mp3')):
            result = shell_bridge.write('shared_audio', {'token': 'b' * 48}, str(self.dir / 'Copy'), 'http://127.0.0.1:1')
        self.assertEqual(result['path'], str(self.dir / 'Copy.mp3'))
        self.assertEqual((self.dir / 'Copy.mp3').read_bytes(), mp3.read_bytes())

    def test_the_cache_file_itself_is_never_overwritten(self):
        source = self.dir / 'cache.mp4'
        source.write_bytes(b'video')
        with patch.object(clip_export, 'completed_clip', return_value=(source, 'Clip.mp4')):
            with self.assertRaises(ValueError):
                shell_bridge.write('clip', {'session': 'a' * 24}, str(source), 'http://127.0.0.1:1')
        self.assertEqual(source.read_bytes(), b'video')


class HTTP(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {shell_bridge.TOKEN_ENV: TOKEN})
        self.env.start()
        self.client = TestClient(TestServer(server.build_app()))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        self.env.stop()
        self.tmp.cleanup()

    async def call(self, method, url, token=TOKEN, **kw):
        headers = {shell_bridge.HEADER: token} if token is not None else {}
        response = await self.client.request(method, url, headers=headers, **kw)
        return response.status, await response.json()

    async def test_every_endpoint_needs_the_token(self):
        for method, url in (('GET', '/api/shell/hello'), ('POST', '/api/shell/save-plan'), ('POST', '/api/shell/save'),
                            ('POST', '/api/shell/quit')):
            for token in (None, '', 'wrong' * 8, TOKEN.lower()):
                status, body = await self.call(method, url, token=token, json={'kind': 'export', 'payload': {}})
                self.assertEqual(status, 403, (method, url, token))
                self.assertEqual(body, {'error': 'forbidden'})

    async def test_no_token_in_the_environment_closes_the_bridge(self):
        os.environ.pop(shell_bridge.TOKEN_ENV, None)
        status, _ = await self.call('GET', '/api/shell/hello')
        self.assertEqual(status, 403)

    async def test_quit_stops_the_loop_after_answering(self):
        with patch.object(server, '_shell_quit_later') as later:
            status, body = await self.call('POST', '/api/shell/quit', token=None)
            self.assertEqual(status, 403)
            later.assert_not_called()
            status, body = await self.call('POST', '/api/shell/quit', json={})
        self.assertEqual((status, body), (200, {'stopping': True}))
        later.assert_called_once()

    async def test_hello_answers_the_shell(self):
        status, body = await self.call('GET', '/api/shell/hello')
        self.assertEqual(status, 200)
        self.assertEqual(body['app'], 'Kryo')

    async def test_plan_and_save_round_trip(self):
        with patch.object(file_exports, 'prepare', return_value=(b'cover-bytes', 'Cover.png', '.png')) as prep:
            status, plan = await self.call('POST', '/api/shell/save-plan', json={'kind': 'export', 'payload': {'spec': {'kind': 'cover'}}})
            self.assertEqual(status, 200)
            self.assertEqual(plan['name'], 'Cover.png')
            status, saved = await self.call('POST', '/api/shell/save', json={'kind': 'export', 'payload': {'spec': {'kind': 'cover'}}, 'path': str(self.dir / 'Cover')})
        self.assertEqual(status, 200, saved)
        self.assertEqual(saved, {'saved': True, 'path': str(self.dir / 'Cover.png')})
        self.assertEqual((self.dir / 'Cover.png').read_bytes(), b'cover-bytes')
        base = prep.call_args.args[1]
        self.assertRegex(base, r'^http://127\.0\.0\.1:\d+$')

    async def test_errors_are_plain_messages(self):
        status, body = await self.call('POST', '/api/shell/save-plan', json={'kind': 'nope', 'payload': {}})
        self.assertEqual((status, body), (400, {'error': 'Unknown save request'}))
        status, body = await self.call('POST', '/api/shell/save', data=b'{not json')
        self.assertEqual(status, 400)
        status, body = await self.call('POST', '/api/shell/save', json=['list'])
        self.assertEqual((status, body), (400, {'error': 'bad request'}))
        with patch.object(file_exports, 'prepare', return_value=(b'x', 'a.lrc', '.lrc')):
            status, body = await self.call('POST', '/api/shell/save', json={'kind': 'export', 'payload': {'spec': {}}, 'path': 'relative.lrc'})
        self.assertEqual((status, body), (400, {'error': 'Choose where to save the file'}))
        with patch.object(file_exports, 'prepare', side_effect=OSError('disk on fire')):
            status, body = await self.call('POST', '/api/shell/save-plan', json={'kind': 'export', 'payload': {'spec': {}}})
        self.assertEqual((status, body), (400, {'error': 'Could not prepare the file'}))


if __name__ == '__main__':
    unittest.main()
