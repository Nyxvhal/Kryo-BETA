"""v73: research prototypes behind docs/AI_NCNN_MIGRATION_PLAN.md (not used by the player)."""
import hashlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parents[1] / 'research' / 'ai-ncnn'
_SKIP_REASON = 'research/ai-ncnn prototypes are not in this repository'


def load(name):
    spec = importlib.util.spec_from_file_location('ncnn_' + name, HERE / (name + '.py'))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


zip_range = load('zip_range') if HERE.is_dir() else None


def make_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as z:
        z.writestr(zipfile.ZipInfo('pkg/engine.exe'), os.urandom(70000), compress_type=zipfile.ZIP_STORED)
        z.writestr('pkg/models/m.bin', b'weights' * 50000, compress_type=zipfile.ZIP_DEFLATED)
        z.writestr('pkg/models/m.param', b'7767517\n1 1\nInput data 0 1 data\n', compress_type=zipfile.ZIP_DEFLATED)
        z.writestr('pkg/empty.txt', b'', compress_type=zipfile.ZIP_DEFLATED)
        z.writestr('pkg/big-unused.bin', os.urandom(300000), compress_type=zipfile.ZIP_STORED)
    return buf.getvalue()


class Server:
    """Serves one blob; `ranges=False` imitates a server that ignores Range."""
    def __init__(self, blob, ranges=True):
        outer = self; self.blob = blob; self.ranges = ranges; self.sent = 0

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_GET(self):
                rng = self.headers.get('Range', '')
                m = re.fullmatch(r'bytes=(\d+)-(\d+)', rng)
                if outer.ranges and m:
                    a, b = int(m[1]), min(int(m[2]), len(outer.blob) - 1)
                    body = outer.blob[a:b + 1]
                    self.send_response(206); self.send_header('Content-Range', 'bytes %d-%d/%d' % (a, b, len(outer.blob)))
                else:
                    body = outer.blob; self.send_response(200)
                self.send_header('Content-Length', str(len(body))); self.end_headers()
                self.wfile.write(body); outer.sent += len(body)

        self.httpd = ThreadingHTTPServer(('127.0.0.1', 0), H)
        self.url = 'http://127.0.0.1:%d/a.zip' % self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown(); self.httpd.server_close()


@unittest.skipUnless(HERE.is_dir(), _SKIP_REASON)
class ZipRangeTest(unittest.TestCase):
    def setUp(self):
        self.blob = make_zip(); self.srv = Server(self.blob); self.tmp = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.srv.close(); self.tmp.cleanup()

    def test_lists_members_from_the_tail_only(self):
        z = zip_range.RemoteZip(self.srv.url)
        self.assertEqual(z.size, len(self.blob))
        self.assertEqual(set(z.entries), {'pkg/engine.exe', 'pkg/models/m.bin', 'pkg/models/m.param', 'pkg/empty.txt',
                                          'pkg/big-unused.bin'})

    def test_extracts_selected_members_with_checksums(self):
        z = zip_range.RemoteZip(self.srv.url)
        with zipfile.ZipFile(io.BytesIO(self.blob)) as ref:
            for name in ('pkg/engine.exe', 'pkg/models/m.bin', 'pkg/models/m.param', 'pkg/empty.txt'):
                target = os.path.join(self.tmp.name, name)
                got = z.extract(name, target)
                data = ref.read(name)
                self.assertEqual(Path(target).read_bytes(), data)
                self.assertEqual(got['sha256'], hashlib.sha256(data).hexdigest())
                self.assertEqual(got['size'], len(data))
        # the 300 KB member nobody asked for was not transferred (at most the
        # 64 KB tail read that finds the central directory overlaps it)
        self.assertLess(self.srv.sent, len(self.blob) - 300000 + 65557 + 1024)

    def test_refuses_a_server_without_range_support(self):
        self.srv.close(); self.srv = Server(self.blob, ranges=False)
        with self.assertRaises(zip_range.RangeNotSupported):
            zip_range.RemoteZip(self.srv.url)

    def test_corrupt_member_leaves_no_file(self):
        z = zip_range.RemoteZip(self.srv.url)
        z.entries['pkg/models/m.bin']['crc'] ^= 1
        target = os.path.join(self.tmp.name, 'm.bin')
        with self.assertRaises(ValueError):
            z.extract('pkg/models/m.bin', target)
        self.assertFalse(os.path.exists(target)); self.assertFalse(os.path.exists(target + '.part'))


@unittest.skipUnless(HERE.is_dir(), _SKIP_REASON)
class VulkanProbeTest(unittest.TestCase):
    def test_probe_runs_in_a_child_and_answers_json(self):
        env = dict(os.environ)
        out = subprocess.run([sys.executable, str(HERE / 'vulkan_probe.py')], capture_output=True, text=True,
                             timeout=60, env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        info = json.loads(out.stdout)
        self.assertIn(info['verdict'], ('ok', 'software', 'no-device', 'no-vulkan'))
        if info['loader'] is None:
            self.assertEqual(info['verdict'], 'no-vulkan'); self.assertTrue(info['error'])
        if info['verdict'] in ('ok', 'software'):
            self.assertIsNotNone(info['best']); self.assertTrue(info['devices'][info['best']]['compute'])

    def test_broken_driver_is_reported_not_raised(self):
        env = dict(os.environ, VK_ICD_FILENAMES='/nonexistent/icd.json', VK_DRIVER_FILES='/nonexistent/icd.json')
        out = subprocess.run([sys.executable, str(HERE / 'vulkan_probe.py')], capture_output=True, text=True,
                             timeout=60, env=env)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn(json.loads(out.stdout)['verdict'], ('no-vulkan', 'no-device'))


@unittest.skipUnless(HERE.is_dir(), _SKIP_REASON)
class ManifestDraftTest(unittest.TestCase):
    def test_every_pinned_file_has_size_and_sha256(self):
        m = json.loads((HERE / 'manifest.draft.json').read_text())
        for eid, eng in m['engines'].items():
            for plat in ('windows-x64', 'linux-x64'):
                for f in eng[plat]['files']:
                    self.assertGreater(f['size'], 0); self.assertRegex(f['sha256'], r'^[0-9a-f]{64}$')
                    self.assertTrue(eng[plat]['archive'].startswith('https://github.com/'))
        for mid, model in m['models'].items():
            self.assertIn(model['engine'], m['engines']); self.assertTrue(model['license'])
            for f in model['files']:
                self.assertRegex(f['sha256'], r'^[0-9a-f]{64}$')
        for feature, ids in m['needs'].items():
            for i in ids:
                self.assertTrue(i in m['engines'] or i in m['models'], (feature, i))
        # The whole point: small downloads instead of a multi-gigabyte PyTorch.
        self.assertLess(max(m['download_mb_windows'].values()), 64)


if __name__ == '__main__':
    unittest.main()
