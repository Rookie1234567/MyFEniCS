from __future__ import annotations

import unittest

import numpy as np
from mpi4py import MPI
from dolfinx import mesh

from src.adaptivity.cell_indicator_snapshot import (
    build_cell_indicator_snapshot,
)
from src.adaptivity.hp_smoothness_classifier import (
    classify_hp_correction_decay,
)
from src.geometry.tetra_mesh_audit import (
    canonical_owned_cell_ids,
    geometry_key_sha256,
)
from benchmarks.task035b_hp_classifier import build_hp_classifier_record


class Task035HpSmoothnessClassifierTests(unittest.TestCase):
    def test_consecutive_correction_decay_classifies_h_p_and_floor(self) -> None:
        report = classify_hp_correction_decay(
            np.array([7, 2, 5, 9]),
            np.array([10.0, 8.0, 1.0e-14, 4.0]),
            np.array([2.0, 6.0, 2.0e-14, 2.0]),
            [9, 7, 5, 2],
            p_decay_ratio_threshold=0.5,
            significance_floor_fraction=1.0e-12,
        )
        self.assertTrue(report["pass"])
        self.assertFalse(report["ordinary_default_changed"])
        self.assertEqual(
            report["counts"],
            {
                "h_candidate": 1,
                "p_candidate": 2,
                "undetermined": 1,
            },
        )
        self.assertEqual(
            [
                (entry["canonical_cell_id"], entry["decision"])
                for entry in report["decisions"]
            ],
            [
                (2, "h_candidate"),
                (5, "undetermined"),
                (7, "p_candidate"),
                (9, "p_candidate"),
            ],
        )
        self.assertEqual(report["classified_cell_count"], 3)
        self.assertAlmostEqual(report["p_candidate_fraction_of_classified"], 2.0 / 3.0)
        self.assertEqual(
            report["local_order_action_counts"],
            {
                "p_down": 0,
                "p_keep": 1,
                "p_up": 2,
                "h_refine": 1,
            },
        )

    def test_four_way_local_order_actions_cover_unmarked_cells(self) -> None:
        report = classify_hp_correction_decay(
            np.arange(6),
            np.array([10.0, 8.0, 2.0, 1.0, 1.0e-4, 1.0e-5]),
            np.array([7.0, 2.0, 1.2, 0.2, 2.0e-5, 1.0e-6]),
            [0, 1],
            p_down_indicator_fraction=1.0e-3,
        )
        self.assertEqual(
            report["local_order_action_counts"],
            {
                "p_down": 2,
                "p_keep": 2,
                "p_up": 1,
                "h_refine": 1,
            },
        )
        self.assertEqual(
            [entry["action"] for entry in report["local_order_actions"]],
            ["h_refine", "p_up", "p_keep", "p_keep", "p_down", "p_down"],
        )

    def test_complete_cell_snapshot_is_canonical_and_mpi_stable(self) -> None:
        comm = MPI.COMM_WORLD
        global_ids = np.arange(comm.size * 2, dtype=np.int64)
        local_ids = global_ids[2 * comm.rank : 2 * comm.rank + 2][::-1]
        local_values = (local_ids.astype(np.float64) + 1.0) / 10.0
        report = build_cell_indicator_snapshot(
            comm,
            local_ids,
            local_values,
            indicator_name="fixture",
            mesh_geometry_sha256="a" * 64,
        )
        self.assertEqual(report["canonical_cell_ids"], global_ids.tolist())
        np.testing.assert_allclose(
            report["indicator_values"],
            (global_ids.astype(np.float64) + 1.0) / 10.0,
        )
        self.assertEqual(report["cell_count"], comm.size * 2)
        self.assertEqual(len(report["canonical_ids_and_values_sha256"]), 64)
        self.assertTrue(report["partition_independent"])

    def test_hexa_cell_geometry_has_partition_independent_ids(self) -> None:
        comm = MPI.COMM_WORLD
        msh = mesh.create_box(
            comm,
            ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)),
            (2 * comm.size, 1, 1),
            cell_type=mesh.CellType.hexahedron,
        )
        ids, records, ordered_keys = canonical_owned_cell_ids(msh)
        self.assertEqual(len(ids), len(records))
        self.assertEqual(len(ordered_keys), 2 * comm.size)
        self.assertEqual(
            sorted(
                value
                for packet in comm.allgather(ids.tolist())
                for value in packet
            ),
            list(range(2 * comm.size)),
        )
        self.assertEqual(len(geometry_key_sha256(ordered_keys)), 64)

    def test_same_mesh_pair_record_builds_four_way_classifier(self) -> None:
        def payload(
            coarse: int,
            enriched: int,
            values: list[float],
            marked: list[int],
        ) -> dict:
            return {
                "coarse": {"degree": coarse},
                "enriched": {"degree": enriched},
                "R5": {
                    "marked_canonical_cell_ids": marked,
                    "cell_indicator_snapshot": {
                        "storage": "inline_complete_vector",
                        "mesh_geometry_sha256": "b" * 64,
                        "canonical_cell_ids": [0, 1, 2, 3],
                        "indicator_values": values,
                        "indicator_sum": sum(values),
                        "canonical_ids_and_values_sha256": (
                            str(coarse) * 64
                        ),
                    },
                },
            }

        record = build_hp_classifier_record(
            payload(4, 5, [10.0, 4.0, 0.01, 0.001], [0]),
            payload(5, 6, [8.0, 1.0, 0.001, 0.0001], [1]),
        )
        self.assertTrue(record["pass"])
        self.assertEqual(record["marked_canonical_cell_ids"], [0, 1])
        self.assertEqual(
            record["classifier"]["local_order_action_counts"],
            {
                "p_down": 2,
                "p_keep": 0,
                "p_up": 1,
                "h_refine": 1,
            },
        )

    def test_classifier_rejects_invalid_or_unaligned_inputs(self) -> None:
        with self.assertRaisesRegex(ValueError, "aligned"):
            classify_hp_correction_decay(
                np.array([1, 1]),
                np.array([1.0, 2.0]),
                np.array([0.5, 1.0]),
                [1],
            )
        with self.assertRaisesRegex(ValueError, "nonnegative"):
            classify_hp_correction_decay(
                np.array([1]),
                np.array([-1.0]),
                np.array([0.5]),
                [1],
            )
        with self.assertRaisesRegex(ValueError, "subset"):
            classify_hp_correction_decay(
                np.array([1]),
                np.array([1.0]),
                np.array([0.5]),
                [2],
            )
        with self.assertRaisesRegex(ValueError, "consecutive"):
            classify_hp_correction_decay(
                np.array([1]),
                np.array([1.0]),
                np.array([0.5]),
                [1],
                degrees=(3, 5, 6),
            )
        with self.assertRaisesRegex(ValueError, "threshold"):
            classify_hp_correction_decay(
                np.array([1]),
                np.array([1.0]),
                np.array([0.5]),
                [1],
                p_decay_ratio_threshold=1.0,
            )
        with self.assertRaisesRegex(ValueError, "p-down"):
            classify_hp_correction_decay(
                np.array([1]),
                np.array([1.0]),
                np.array([0.5]),
                [1],
                p_down_indicator_fraction=0.0,
            )


if __name__ == "__main__":
    unittest.main()
