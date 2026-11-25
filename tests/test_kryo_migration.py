import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from kryonyx.paths import _migrate_brand_data

class BrandMigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.old = self.root / 'KryonyxMusic'
        self.new = self.root / 'Kryo'
        (self.old / 'devices' / 'test').mkdir(parents=True)
        (self.old / 'devices' / 'test' / 'kryonyx.db').write_bytes(b'old data')
        (self.old / 'settings.json').write_text('settings')
    def test_copy_preserves_source_and_multiple_files(self):
        self.assertTrue(_migrate_brand_data(str(self.old), str(self.new)))
        self.assertEqual((self.new / 'devices/test/kryonyx.db').read_bytes(), b'old data')
        self.assertEqual((self.old / 'devices/test/kryonyx.db').read_bytes(), b'old data')
        self.assertEqual((self.new / 'settings.json').read_text(), 'settings')
    def test_existing_destination_is_not_merged(self):
        self.new.mkdir()
        (self.new / 'settings.json').write_text('new')
        self.assertFalse(_migrate_brand_data(str(self.old), str(self.new)))
        self.assertEqual((self.new / 'settings.json').read_text(), 'new')
    def test_failure_cleans_staging_and_retains_original(self):
        with patch('kryonyx.paths.shutil.copytree', side_effect=OSError('disk full')):
            with self.assertRaises(OSError): _migrate_brand_data(str(self.old), str(self.new))
        self.assertFalse(self.new.exists())
        self.assertTrue((self.old / 'settings.json').exists())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ['KryonyxMusic'])
    def test_active_journal_prevents_copy(self):
        (self.old / 'devices/test/kryonyx.db-wal').write_bytes(b'uncheckpointed')
        with self.assertRaises(OSError): _migrate_brand_data(str(self.old), str(self.new))
        self.assertFalse(self.new.exists())
    def test_symlink_rejected(self):
        try: (self.old / 'link').symlink_to(self.old / 'settings.json')
        except (OSError, NotImplementedError): self.skipTest('symlinks unavailable')
        with self.assertRaises(OSError): _migrate_brand_data(str(self.old), str(self.new))
        self.assertFalse(self.new.exists())
    def test_verification_mismatch_refuses_to_publish(self):
        from kryonyx import paths
        real = paths._snapshot_tree
        calls = 0
        def mismatch(root):
            nonlocal calls
            calls += 1
            result = real(root)
            if calls == 2:
                result['settings.json'] = ('file', 99, 'wrong')
            return result
        with patch('kryonyx.paths._snapshot_tree', side_effect=mismatch):
            with self.assertRaises(OSError): _migrate_brand_data(str(self.old), str(self.new))
        self.assertFalse(self.new.exists())
        self.assertTrue((self.old / 'settings.json').exists())
