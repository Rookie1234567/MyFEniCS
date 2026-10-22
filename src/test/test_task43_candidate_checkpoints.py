from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from benchmarks.task43_hp_adaptivity.candidate_checkpoints import (
    write_pre_validation_checkpoint,
)


class Task43PreValidationCheckpointTests(unittest.TestCase):
    def test_writes_atomic_hash_bound_nonofficial_npz_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "checkpoint.npz"
            arrays = {
                "electric_coefficients": np.asarray(
                    [1.0 + 2.0j, 3.0 - 4.0j], dtype=np.complex128
                ),
                "cell_ids": np.asarray([11, 12], dtype=np.int64),
            }
            result = write_pre_validation_checkpoint(
                path,
                arrays,
                identity={"case_id": "fixture", "source_sha256": "abc"},
            )

            self.assertTrue(path.is_file())
            sidecar = path.with_suffix(".json")
            self.assertTrue(sidecar.is_file())
            record = json.loads(sidecar.read_text(encoding="utf-8"))
            self.assertEqual(result["npz_sha256"], record["npz_sha256"])
            self.assertFalse(record["official_result"])
            self.assertEqual(record["independent_A6"], "not_run_at_checkpoint_time")
            self.assertEqual(record["field_capture"], "not_run_at_checkpoint_time")
            with np.load(path, allow_pickle=False) as loaded:
                np.testing.assert_array_equal(
                    loaded["electric_coefficients"], arrays["electric_coefficients"]
                )
                np.testing.assert_array_equal(loaded["cell_ids"], arrays["cell_ids"])
            self.assertEqual(
                list(Path(temporary).glob(".*.tmp")),
                [],
            )
            with self.assertRaises(FileExistsError):
                write_pre_validation_checkpoint(
                    path,
                    arrays,
                    identity={"case_id": "second-write"},
                )


if __name__ == "__main__":
    unittest.main()
