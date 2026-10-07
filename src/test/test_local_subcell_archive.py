import tempfile
import unittest
from pathlib import Path
from benchmarks.compact_local_subcell_raw import link_identical_copy


class Archive(unittest.TestCase):
    def test_exact_bytes_and_failed_keeper_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);old=root/'failed';new=root/'success';old.mkdir();new.mkdir()
            a=old/'raw.npz';b=new/'raw.npz';a.write_bytes(bytes(range(256))*5);b.write_bytes(a.read_bytes())
            before=a.stat();r=link_identical_copy(a,b)
            self.assertTrue(b.is_symlink());self.assertEqual(b.read_bytes(),a.read_bytes())
            self.assertEqual(a.stat().st_ino,before.st_ino);self.assertEqual(a.stat().st_mtime_ns,before.st_mtime_ns)
            self.assertEqual(r['bytes'],1280)
            with self.assertRaisesRegex(ValueError,'one archive'):link_identical_copy(a,b)

    def test_different_content_not_archived(self):
        with tempfile.TemporaryDirectory() as d:
            a=Path(d)/'a';b=Path(d)/'b';a.write_bytes(b'good');b.write_bytes(b'bad!')
            with self.assertRaisesRegex(ValueError,'unequal byte'):link_identical_copy(a,b)
            self.assertFalse(b.is_symlink());self.assertEqual(b.read_bytes(),b'bad!')
