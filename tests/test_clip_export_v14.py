import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from kryonyx.clip_export import completed_clip, copy_atomic
from kryonyx.main import DesktopApi

class ClipExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.sid = 'a' * 24
        self.folder = self.root / self.sid
        self.folder.mkdir()
        self.data = dict(container='mp4', video_id='TESTVIDEO01', height=720,
                         sources={'video': {'complete': True}})
        self.source = self.folder / 'video.bin'
        self.source.write_bytes(b'original bytes\x00\xff')
        self.persist()
    def persist(self):
        (self.folder / 'metadata.json').write_text(json.dumps(self.data))
    def test_combined_and_muxed(self):
        source, name = completed_clip(self.root, self.sid)
        self.assertEqual(source, self.source)
        self.assertTrue(name.endswith('-720p.mp4'))
        self.data['sources']['audio'] = {'complete': True}
        self.persist()
        with self.assertRaises(ValueError): completed_clip(self.root, self.sid)
        muxed = self.folder / 'clip.mp4'; muxed.write_bytes(b'muxed')
        self.assertEqual(completed_clip(self.root, self.sid)[0], muxed)
    def test_invalid_and_incomplete(self):
        for bad in ('../test', '', None, 'b'*25):
            with self.assertRaises(ValueError): completed_clip(self.root, bad)
        self.data['sources']['video']['complete'] = False; self.persist()
        with self.assertRaises(ValueError): completed_clip(self.root, self.sid)
    def test_symlink_rejected(self):
        self.source.unlink(); external = self.root / 'private'; external.write_bytes(b'no')
        self.source.symlink_to(external)
        with self.assertRaises(ValueError): completed_clip(self.root, self.sid)
    def test_exact_copy_and_atomic_failure(self):
        dest = self.root / 'chosen.mp4'; dest.write_bytes(b'old')
        copy_atomic(self.source, dest)
        self.assertEqual(dest.read_bytes(), self.source.read_bytes())
        dest.write_bytes(b'old')
        with patch('kryonyx.clip_export.shutil.copyfileobj', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): copy_atomic(self.source, dest)
        self.assertEqual(dest.read_bytes(), b'old')
        self.assertEqual(list(self.root.glob('.kryonyx-export-*')), [])
    def test_native_dialog_cancel_and_save(self):
        from types import SimpleNamespace
        api = DesktopApi.__new__(DesktopApi)
        target = self.root / 'chosen.webm'
        selected = [str(target)]
        api._window = SimpleNamespace(create_file_dialog=lambda *a, **k: selected)
        module = SimpleNamespace(FileDialog=SimpleNamespace(SAVE=99))
        with patch.dict('sys.modules', {'webview': module}), patch('kryonyx.clipstream.root', return_value=self.root):
            self.assertEqual(api.save_clip(self.sid), {'saved': True})
            self.assertEqual(target.read_bytes(), self.source.read_bytes())
            selected.clear()
            self.assertEqual(api.save_clip(self.sid), {'cancelled': True})
            self.assertIn('error', api.save_clip('../private'))

if __name__ == '__main__': unittest.main()
