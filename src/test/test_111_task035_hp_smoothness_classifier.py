from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
import unittest

import numpy as np
from basix.ufl import element
from mpi4py import MPI
from dolfinx import default_real_type, fem, mesh

from src.adaptivity.cell_indicator_snapshot import (
    build_cell_indicator_snapshot,
)
from src.adaptivity.hp_smoothness_classifier import (
    classify_hp_correction_decay,
)
from src.adaptivity.global_two_level_r5 import (
    localize_p6_hcurl_projection_signals,
)
from src.adaptivity.multigoal_hp_classifier import (
    build_cell_geometry_priors,
    classify_multigoal_hp_candidates,
)
from src.common.config_3d import target_stage4_config
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.geometry.tetra_mesh_audit import (
    canonical_owned_cell_ids,
    geometry_key_sha256,
)
from benchmarks.task035b_hp_classifier import build_hp_classifier_record


class Task035HpSmoothnessClassifierTests(unittest.TestCase):
    def test_p6_projection_signals_resolve_nested_smooth_decay(
        self,
    ) -> None:
        msh = mesh.create_unit_cube(
            MPI.COMM_SELF,
            1,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
        )
        p5_space = fem.functionspace(
            msh,
            element(
                "N1curl",
                msh.basix_cell(),
                5,
                dtype=default_real_type,
            ),
        )
        p6_space = fem.functionspace(
            msh,
            element(
                "N1curl",
                msh.basix_cell(),
                6,
                dtype=default_real_type,
            ),
        )
        p5_field = fem.Function(p5_space)
        p6_field = fem.Function(p6_space)
        p6_field.interpolate(
            lambda x: np.vstack(
                (
                    x[1] ** 5 + 0.1 * x[2] ** 6,
                    x[0] ** 4 - x[2],
                    x[0] * x[1],
                )
            )
        )
        p6_field.x.scatter_forward()
        report = localize_p6_hcurl_projection_signals(
            p5_field,
            p6_field,
        )
        self.assertTrue(report["pass"])
        self.assertEqual(
            report["element_dimensions"],
            {
                "p4": 300,
                "p5": 540,
                "p6": 882,
                "shell_p5": 240,
                "shell_p6": 342,
            },
        )
        self.assertLess(
            report["reconstruction_relative_coefficient_error"],
            1.0e-12,
        )
        snapshots = report["snapshots"]
        self.assertEqual(
            set(snapshots),
            {
                "shell_p5_energy",
                "shell_p6_energy",
                "hierarchical_decay_ratio",
                "hierarchical_decay_resolved",
                "coefficient_decay_ratio",
                "coefficient_decay_resolved",
                "p4_relative_projection_defect",
                "p5_relative_projection_defect",
            },
        )
        self.assertEqual(
            snapshots["hierarchical_decay_resolved"][
                "indicator_values"
            ],
            [1.0],
        )
        self.assertLess(
            snapshots["hierarchical_decay_ratio"]["indicator_values"][0],
            0.1,
        )
        self.assertLess(
            snapshots["p5_relative_projection_defect"][
                "indicator_values"
            ][0],
            snapshots["p4_relative_projection_defect"][
                "indicator_values"
            ][0],
        )

    def test_fixed_target_cell_priors_match_formal_hexa_identity(self) -> None:
        cfg = replace(
            target_stage4_config(degree=4, h_nm=10.0),
            mesh_cell_type="hexahedron",
            unique_output=False,
        )
        with tempfile.TemporaryDirectory() as directory:
            mesh_data = build_airbox_mesh_3d(cfg, Path(directory))
            priors = build_cell_geometry_priors(mesh_data, cfg)
        self.assertTrue(priors["pass"])
        self.assertEqual(priors["cell_count"], 252)
        self.assertEqual(
            priors["mesh_geometry_sha256"],
            "b68a588e99032c9972740621bf01f15807d92d6025919bb097a53e92e75852a7",
        )
        self.assertEqual(
            priors["material_counts"],
            {"air": 162, "grating": 72, "substrate": 18},
        )
        self.assertEqual(priors["material_interface_cell_count"], 174)
        self.assertEqual(priors["corner_or_edge_junction_cell_count"], 18)
        self.assertEqual(priors["periodic_mate_group_count"], 126)
        self.assertEqual(len(priors["canonical_priors_sha256"]), 64)

    def test_multigoal_classifier_closes_periodic_goal_markers(self) -> None:
        mesh_sha256 = "b" * 64
        base = {
            "pass": True,
            "mesh_geometry_sha256": mesh_sha256,
            "cell_count": 4,
            "classifier": {
                "p_decay_ratio_threshold": 0.5,
                "local_order_actions": [
                    {
                        "canonical_cell_id": cell_id,
                        "lower_pair_indicator": 10.0,
                        "higher_pair_indicator": 2.0,
                        "higher_to_lower_ratio": 0.2,
                        "action": "p_keep",
                    }
                    for cell_id in range(4)
                ],
            },
        }

        def report(marked: list[int], values: list[float]) -> dict:
            return {
                "marked_canonical_cell_ids": marked,
                "cell_indicator_snapshot": {
                    "storage": "inline_complete_vector",
                    "mesh_geometry_sha256": mesh_sha256,
                    "canonical_cell_ids": list(range(4)),
                    "indicator_values": values,
                },
            }

        dwr = {
            "qualification": {"pass": True},
            "DWR": {
                "goals": {
                    "R00_total": report([0], [4.0, 4.0, 1.0, 1.0]),
                    "R_total": report([0], [4.0, 4.0, 1.0, 1.0]),
                    "T_total": report([2], [1.0, 1.0, 4.0, 4.0]),
                },
                "combined_relative_R_T": report(
                    [0, 2],
                    [4.0, 4.0, 4.0, 4.0],
                ),
                "tolerance_normalized_R_T": report(
                    [2],
                    [1.0, 1.0, 4.0, 4.0],
                ),
            },
            "R5_control": report([0], [4.0, 4.0, 1.0, 1.0]),
        }
        priors = {
            "pass": True,
            "mesh_geometry_sha256": mesh_sha256,
            "periodic_mate_groups": [
                {"axis": "x", "min_cell_id": 0, "max_cell_id": 1},
                {"axis": "x", "min_cell_id": 2, "max_cell_id": 3},
            ],
            "cells": [
                {
                    "canonical_cell_id": cell_id,
                    "material_tag": 1,
                    "material_name": "air",
                    "material_interface": False,
                    "material_interface_facet_count": 0,
                    "corner_or_edge_junction_prior": False,
                    "periodic_boundary_axes": ["x"],
                }
                for cell_id in range(4)
            ],
        }
        result = classify_multigoal_hp_candidates(base, dwr, priors)
        self.assertTrue(result["pass"])
        self.assertEqual(result["raw_goal_important_cell_count"], 2)
        self.assertEqual(result["goal_important_cell_count"], 4)
        self.assertEqual(
            result["periodic_goal_marker_closure_added_canonical_cell_ids"],
            [1, 3],
        )
        self.assertEqual(
            result["action_counts"],
            {
                "h_refine_candidate": 0,
                "p_down_candidate": 0,
                "p_keep_candidate": 0,
                "p_up_candidate": 4,
                "undetermined": 0,
            },
        )
        self.assertTrue(result["periodic_decision_audit"]["pass"])
        self.assertIn(
            "target_cell_local_projection_defect",
            result["missing_required_signals"],
        )

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
