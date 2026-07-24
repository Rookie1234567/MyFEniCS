from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np
from basix.ufl import element
from mpi4py import MPI
from dolfinx import default_real_type, fem, mesh

from src.adaptivity.cell_indicator_snapshot import (
    build_cell_indicator_snapshot,
    validate_cell_indicator_snapshot,
)
from src.adaptivity.hp_smoothness_classifier import (
    classify_hp_correction_decay,
    classify_hp_signals_v3,
)
from src.adaptivity.global_two_level_r5 import (
    localize_p6_hcurl_projection_signals,
)
from src.adaptivity.multigoal_hp_classifier import (
    build_cell_geometry_priors,
    classify_multigoal_hp_candidates,
    upgrade_multigoal_hp_classifier_v3,
)
from src.common.config_3d import target_stage4_config
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.geometry.tetra_mesh_audit import (
    canonical_owned_cell_ids,
    geometry_key_sha256,
)
from benchmarks.task035b_hp_classifier import build_hp_classifier_record
from benchmarks.task035b_hp_competition import (
    build_actual_hp_competition_record,
)


class Task035HpSmoothnessClassifierTests(unittest.TestCase):
    def test_actual_target_v3_uses_projection_signals_fail_closed(
        self,
    ) -> None:
        root = Path(__file__).resolve().parents[2]
        records = (
            root
            / (
                "benchmarks/cases/095_high_order_local_hp_"
                "resource_envelope/records"
            )
        )
        v2 = json.loads(
            (
                records
                / "same_mesh_p4_p5_p6_multigoal_hp_classifier_v2.json"
            ).read_text(encoding="utf-8")
        )
        projection = json.loads(
            (
                records
                / "global_hexa_p5_p6_h10_projection_signals_mpi8.json"
            ).read_text(encoding="utf-8")
        )
        competition = json.loads(
            (
                records
                / "actual_sequential_h_vs_p_competition_mpi8.json"
            ).read_text(encoding="utf-8")
        )
        report = upgrade_multigoal_hp_classifier_v3(
            v2,
            projection,
            competition,
        )
        self.assertTrue(report["pass"])
        self.assertFalse(report["production_qualified"])
        self.assertEqual(
            report["action_counts"],
            {
                "p_down_candidate": 0,
                "p_keep_candidate": 150,
                "p_up_candidate": 102,
                "h_refine_candidate": 0,
                "undetermined": 0,
            },
        )
        self.assertEqual(
            report["actual_target_signal_summary"][
                "physically_resolved_cell_count"
            ],
            252,
        )
        self.assertTrue(report["periodic_decision_audit"]["pass"])
        self.assertIn(
            "actual_same_patch_local_h_vs_p_cost_normalized_competition",
            report["missing_required_signals"],
        )
        self.assertEqual(
            report["signal_coverage"]["coefficient_decay"],
            "actual_same_mesh_diagnostic_only_not_physical_gram",
        )

        projection["R5"]["p6_local_hp_signals"]["snapshots"][
            "shell_p5_energy"
        ]["canonical_ids_and_values_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "content validation"):
            upgrade_multigoal_hp_classifier_v3(
                v2,
                projection,
                competition,
            )

    def test_v3_fault_table_is_conservative_and_resolution_aware(
        self,
    ) -> None:
        ids = np.arange(6, dtype=np.int64)
        report = classify_hp_signals_v3(
            ids,
            np.array([0.10, np.nan, 0.75, 0.65, 0.01, 0.10]),
            np.array([0.024, 0.0, 0.705, 0.586, 0.0, 0.10]),
            np.array([True, False, True, True, True, True]),
            np.array([0.022, 0.0, 0.622, 0.454, 0.0, 0.10]),
            np.array([True, False, True, True, True, True]),
            np.array([0.0103, 0.0, 0.188, 0.0636, 0.964, 0.20]),
            np.array(
                [0.00030, 0.0, 0.121, 0.0365, 3.1e-15, 0.02]
            ),
            ids.tolist(),
            base_actions=["p_keep_candidate"] * len(ids),
            material_interface=np.array(
                [False, True, True, False, False, True]
            ),
            corner_or_edge=np.array(
                [False, False, False, True, False, False]
            ),
            periodic_mate_groups=[],
            phase_resolution_ratio=np.array(
                [0.2, 0.2, 0.2, 0.2, 4.0 * np.pi / 7.0, 0.2]
            ),
        )
        self.assertEqual(
            [row["action"] for row in report["decisions"]],
            [
                "p_up_candidate",
                "p_keep_candidate",
                "h_refine_candidate",
                "h_refine_candidate",
                "undetermined",
                "p_up_candidate",
            ],
        )
        self.assertEqual(
            report["decisions"][4]["reason"],
            "independent resolution gate failed",
        )
        self.assertIn(
            "raw_cell_coefficient_shell_decay",
            report["advisory_signals"],
        )
        self.assertFalse(report["production_qualified"])

    def test_v3_periodic_components_aggregate_before_decision(
        self,
    ) -> None:
        ids = np.arange(4, dtype=np.int64)
        report = classify_hp_signals_v3(
            ids,
            np.array([0.2, 0.2, 0.8, 0.2]),
            np.array([0.2, 0.2, 0.8, 0.2]),
            np.ones(4, dtype=bool),
            np.array([0.2, 0.2, 0.2, 0.2]),
            np.ones(4, dtype=bool),
            np.full(4, 0.2),
            np.array([0.04, 0.04, 0.16, 0.04]),
            [0],
            base_actions=["p_keep_candidate"] * 4,
            material_interface=np.zeros(4, dtype=bool),
            corner_or_edge=np.zeros(4, dtype=bool),
            periodic_mate_groups=[
                {"min_cell_id": 0, "max_cell_id": 1},
                {"min_cell_id": 1, "max_cell_id": 2},
            ],
            phase_resolution_ratio=np.full(4, 0.2),
        )
        self.assertEqual(
            [row["action"] for row in report["decisions"]],
            [
                "h_refine_candidate",
                "h_refine_candidate",
                "h_refine_candidate",
                "p_keep_candidate",
            ],
        )
        self.assertEqual(
            [
                row["periodic_component_id"]
                for row in report["decisions"][:3]
            ],
            [0, 0, 0],
        )
        self.assertEqual(len(report["decision_identity_sha256"]), 64)

    def test_actual_sequential_h_vs_p_competition_is_fail_closed(
        self,
    ) -> None:
        root = Path(__file__).resolve().parents[2]
        records = (
            root
            / "benchmarks/cases/094_hcurl_goal_oriented_adaptivity/records"
        )
        dwr = json.loads(
            (
                records
                / (
                    "actual_dwr_r_adaptive_tetra_p4_p5_h50_theta0p4_"
                    "cycle1_full_periodic_closure_mpi8.json"
                )
            ).read_text(encoding="utf-8")
        )
        p_up = json.loads(
            (
                records
                / "actual_hp_budget_theta0p4_tetra_p5_p6_h50_mpi8.json"
            ).read_text(encoding="utf-8")
        )
        report = build_actual_hp_competition_record(dwr, p_up)
        self.assertTrue(report["pass"])
        self.assertFalse(report["head_to_head_same_origin"])
        self.assertFalse(report["same_patch"])
        self.assertFalse(report["cell_decision_authority"])
        self.assertFalse(
            report["engineering_gate"]["final_dof_target_pass"]
        )
        self.assertTrue(
            report["engineering_gate"]["final_vector_control_pass"]
        )
        self.assertFalse(
            report["engineering_gate"]["final_strict_R_control_pass"]
        )
        self.assertEqual(
            report["cost_normalized_conclusion"][
                "R_T_A_volume_l2_dof_efficiency_preference"
            ],
            "one_local_h_at_p5",
        )
        self.assertEqual(
            report["cost_normalized_conclusion"][
                "strict_R_total_dof_efficiency_preference"
            ],
            "fixed_mesh_global_p5_to_p6",
        )

        p_up["common_mesh_identity"]["cell_tag_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "mesh identity mismatch"):
            build_actual_hp_competition_record(dwr, p_up)

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
        p5_field.interpolate(
            lambda x: np.vstack(
                (
                    x[1] ** 4 + 0.2 * x[2] ** 5,
                    x[0] ** 3 - x[2],
                    x[0] * x[1],
                )
            )
        )
        p5_field.x.scatter_forward()
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
        self.assertLess(
            report["p5_roundtrip_relative_coefficient_error"],
            1.0e-12,
        )
        self.assertTrue(all(report["qualification_checks"].values()))
        self.assertEqual(
            report["element_contract"]["family"],
            "N1E",
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

    def test_projection_fault_fields_expose_slow_and_alias_lanes(
        self,
    ) -> None:
        def signals(
            msh: mesh.Mesh,
            expression,
        ) -> dict:
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
            p6_field.interpolate(expression)
            p6_field.x.scatter_forward()
            return localize_p6_hcurl_projection_signals(
                p5_field,
                p6_field,
            )

        one_cell = mesh.create_unit_cube(
            MPI.COMM_SELF,
            1,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
        )
        corner = signals(
            one_cell,
            lambda x: np.vstack(
                (
                    np.zeros(x.shape[1]),
                    (x[0] ** 2 + x[1] ** 2) ** (1.0 / 3.0),
                    np.zeros(x.shape[1]),
                )
            ),
        )
        corner_snapshots = corner["snapshots"]
        corner_hierarchical = corner_snapshots[
            "hierarchical_decay_ratio"
        ]["indicator_values"][0]
        corner_defect_decay = (
            corner_snapshots["p5_relative_projection_defect"][
                "indicator_values"
            ][0]
            / corner_snapshots["p4_relative_projection_defect"][
                "indicator_values"
            ][0]
        )
        self.assertGreater(corner_hierarchical, 0.55)
        self.assertGreater(corner_defect_decay, 0.55)
        self.assertLess(
            corner_snapshots["coefficient_decay_ratio"][
                "indicator_values"
            ][0],
            0.55,
        )

        high_frequency = signals(
            one_cell,
            lambda x: np.vstack(
                (
                    np.zeros(x.shape[1]),
                    np.sin(4.0 * np.pi * x[0]),
                    np.zeros(x.shape[1]),
                )
            ),
        )
        high_frequency_snapshots = high_frequency["snapshots"]
        self.assertLess(
            high_frequency_snapshots["hierarchical_decay_ratio"][
                "indicator_values"
            ][0],
            0.35,
        )
        self.assertGreater(
            high_frequency_snapshots["p4_relative_projection_defect"][
                "indicator_values"
            ][0],
            0.5,
        )

        two_cells = mesh.create_unit_cube(
            MPI.COMM_SELF,
            2,
            1,
            1,
            cell_type=mesh.CellType.hexahedron,
        )
        normal_jump = signals(
            two_cells,
            lambda x: np.vstack(
                (
                    np.where(x[0] < 0.5, 1.0, 2.0),
                    np.zeros(x.shape[1]),
                    np.zeros(x.shape[1]),
                )
            ),
        )
        self.assertEqual(
            normal_jump["snapshots"]["hierarchical_decay_resolved"][
                "indicator_values"
            ],
            [0.0, 0.0],
        )

        interface_low_regularity = signals(
            two_cells,
            lambda x: np.vstack(
                (
                    np.zeros(x.shape[1]),
                    np.abs(x[0] - 0.5) ** (2.0 / 3.0),
                    np.zeros(x.shape[1]),
                )
            ),
        )
        self.assertTrue(
            all(
                value > 0.55
                for value in interface_low_regularity["snapshots"][
                    "hierarchical_decay_ratio"
                ]["indicator_values"]
            )
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
        self.assertEqual(
            report["partition_independence_scope"],
            (
                "canonical_cell_id_ordering_only; floating values are not "
                "claimed byte-identical across MPI partition counts"
            ),
        )
        self.assertFalse(report["floating_values_bitwise_mpi_invariant"])
        self.assertTrue(
            all(
                validate_cell_indicator_snapshot(
                    report,
                    expected_mesh_geometry_sha256="a" * 64,
                    expected_cell_count=comm.size * 2,
                ).values()
            )
        )

        if comm.size > 1:
            invalid_values = local_values.copy()
            if comm.rank == 1:
                invalid_values[0] = np.nan
            with self.assertRaisesRegex(
                ValueError,
                "rank 1: indicator values are not finite",
            ):
                build_cell_indicator_snapshot(
                    comm,
                    local_ids,
                    invalid_values,
                    indicator_name="rank_local_failure_fixture",
                    mesh_geometry_sha256="a" * 64,
                )

        mpi_identity = classify_hp_signals_v3(
            np.arange(2, dtype=np.int64),
            np.array([0.2, 0.8]),
            np.array([0.2, 0.8]),
            np.ones(2, dtype=bool),
            np.array([0.2, 0.2]),
            np.ones(2, dtype=bool),
            np.array([0.2, 0.2]),
            np.array([0.04, 0.16]),
            [0],
            base_actions=["p_keep_candidate", "p_keep_candidate"],
            material_interface=np.zeros(2, dtype=bool),
            corner_or_edge=np.zeros(2, dtype=bool),
            periodic_mate_groups=[
                {"min_cell_id": 0, "max_cell_id": 1},
            ],
            phase_resolution_ratio=np.full(2, 0.2),
        )
        hashes = comm.allgather(
            mpi_identity["decision_identity_sha256"]
        )
        self.assertEqual(len(set(hashes)), 1)
        self.assertEqual(
            [
                row["action"] for row in mpi_identity["decisions"]
            ],
            ["h_refine_candidate", "h_refine_candidate"],
        )

    def test_p6_projection_rejects_non_hcurl_contract(self) -> None:
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
                "Lagrange",
                msh.basix_cell(),
                5,
                shape=(3,),
                dtype=default_real_type,
            ),
        )
        p6_space = fem.functionspace(
            msh,
            element(
                "Lagrange",
                msh.basix_cell(),
                6,
                shape=(3,),
                dtype=default_real_type,
            ),
        )
        with self.assertRaisesRegex(ValueError, "family is not N1E"):
            localize_p6_hcurl_projection_signals(
                fem.Function(p5_space),
                fem.Function(p6_space),
            )

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
