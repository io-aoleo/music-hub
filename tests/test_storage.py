import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from storage import MusicStorage

class StorageTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'music';self.root.mkdir();self.storage=MusicStorage(self.root)
    def test_subdirectory_creation_and_write_probe(self):
        self.storage.check('/music/华语',create=True)
        listing=self.storage.browse('/music')
        self.assertTrue(listing['writable']);self.assertEqual(listing['directories'][0]['path'],'/music/华语')
        self.assertFalse(any(x.name.startswith('.music-hub') for x in self.root.iterdir()))
    def test_paths_outside_mount_rejected(self):
        for path in ['/tmp','/music/../tmp','/music2','/music\\bad','',None]:
            with self.assertRaises(ValueError):self.storage.check(path)
    def test_permission_error_is_actionable(self):
        with patch('storage.tempfile.TemporaryFile',side_effect=PermissionError):
            result=self.storage.browse('/music')
        self.assertFalse(result['writable']);self.assertIn('UID 1000',result['error'])
    def test_symlink_escape(self):
        outside=Path(self.temp.name)/'outside';outside.mkdir()
        try:(self.root/'escape').symlink_to(outside,target_is_directory=True)
        except OSError:self.skipTest('symlink permission unavailable')
        with self.assertRaises(ValueError):self.storage.check('/music/escape')
        self.assertEqual(self.storage.browse('/music')['directories'],[])
