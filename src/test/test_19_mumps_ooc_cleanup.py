import tempfile
import unittest
from pathlib import Path

from mpi4py import MPI

from src.solvers.common_3d_solve import (
    _cleanup_mumps_ooc_directory_on_success,
    _retain_mumps_ooc_directory_on_failure,
)


class MumpsOocCleanupTests(unittest.TestCase):
    def test_success_cleanup_removes_files_and_reports_removed_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            ooc_dir = Path(tmp) / "mumps_ooc_files"
            ooc_dir.mkdir()
            (ooc_dir / "factor_a").write_bytes(b"a" * 17)
            nested = ooc_dir / "nested"
            nested.mkdir()
            (nested / "factor_b").write_bytes(b"b" * 5)

            status = _cleanup_mumps_ooc_directory_on_success(
                {"mumps_ooc_tmpdir": str(ooc_dir)},
                MPI.COMM_SELF,
            )

            self.assertTrue(status["mumps_ooc_cleanup_attempted"])
            self.assertTrue(status["mumps_ooc_cleanup_success"])
            self.assertEqual(status["mumps_ooc_cleanup_removed_file_count"], 2)
            self.assertEqual(status["mumps_ooc_cleanup_removed_file_bytes"], 22)
            self.assertEqual(status["mumps_ooc_residual_file_count"], 0)
            self.assertEqual(status["mumps_ooc_residual_file_bytes"], 0)

    def test_failure_retain_keeps_files_and_reports_size(self):
        with tempfile.TemporaryDirectory() as tmp:
            ooc_dir = Path(tmp) / "mumps_ooc_files"
            ooc_dir.mkdir()
            path = ooc_dir / "factor"
            path.write_bytes(b"x" * 11)

            status = _retain_mumps_ooc_directory_on_failure({"mumps_ooc_tmpdir": str(ooc_dir)})

            self.assertFalse(status["mumps_ooc_cleanup_attempted"])
            self.assertTrue(status["mumps_ooc_retained_on_failure"])
            self.assertEqual(status["mumps_ooc_residual_file_count"], 1)
            self.assertEqual(status["mumps_ooc_residual_file_bytes"], 11)
            self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
