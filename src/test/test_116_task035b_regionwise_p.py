from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import basix
import numpy as np
import ufl
from mpi4py import MPI

from dolfinx import fem, mesh

from benchmarks.task035b_regionwise_space_audit import (
    build_regionwise_space_audit,
)
from src.adaptivity.hcurl_regionwise_p import (
    create_reduced_trace_hcurl_element,
    reduced_trace_hcurl_ufl_element,
    regionwise_interior_p_dof_budget,
)
from src.adaptivity.target_regionwise_p_candidate import (
    _complete_control_observables,
    _select_high_cells,
)
from src.common.config_3d import SimulationConfig3D
from src.solvers.common_3d_solve import _create_nedelec_space


class Task035bRegionwisePTests(unittest.TestCase):
    def test_structural_audit_reclassifies_only_non_exact_candidate(
        self,
    ) -> None:
        root = Path(__file__).resolve().parents[2]
        records = (
            root
            / "benchmarks/cases/095_high_order_local_hp_resource_envelope"
            / "records"
        )
        p4 = json.loads(
            (records / "regionwise_p4trace_p6interior_h10_mpi8.json").read_text(
                encoding="utf-8"
            )
        )
        p5 = json.loads(
            (
                records
                / "regionwise_p5trace_p4low_p6high_n62_h10_mpi8.json"
            ).read_text(encoding="utf-8")
        )
        audit = build_regionwise_space_audit(p4, p5)
        self.assertTrue(audit["pass"])
        self.assertEqual(
            audit["independent_exact_sequence_valid_accuracy_negative_count"],
            1,
        )
        self.assertFalse(audit["previous_two_negative_lane_closure_supported"])
        self.assertEqual(
            audit["candidates"]["p5_trace_p4_low_p6_high"][
                "missing_gradient_mode_count"
            ],
            66,
        )

    def test_compact_control_is_completed_from_hashable_raw_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            run_dir = Path(directory)
            (run_dir / "run_summary.json").write_text(
                json.dumps(
                    {
                        "R00_total": 0.1,
                        "R_total": 0.2,
                        "T_total": 0.3,
                    }
                ),
                encoding="utf-8",
            )
            complete, authority = _complete_control_observables(
                {"degree": 5, "R_total": 0.2, "T_total": 0.3},
                run_dir,
            )
            self.assertEqual(complete["R00_total"], 0.1)
            self.assertEqual(len(authority["run_summary_sha256"]), 64)

            with self.assertRaises(ValueError):
                _complete_control_observables(
                    {"R_total": 0.4, "T_total": 0.3},
                    run_dir,
                )

    def test_high_cell_selector_is_deterministic_eta_p5p6_ranking(self) -> None:
        actions = [
            {
                "canonical_cell_id": 7,
                "action": "p_up",
                "higher_pair_indicator": 2.0,
                "lower_pair_indicator": 3.0,
            },
            {
                "canonical_cell_id": 2,
                "action": "p_up",
                "higher_pair_indicator": 4.0,
                "lower_pair_indicator": 1.0,
            },
            {
                "canonical_cell_id": 5,
                "action": "p_up",
                "higher_pair_indicator": 2.0,
                "lower_pair_indicator": 4.0,
            },
            {
                "canonical_cell_id": 1,
                "action": "p_keep",
                "higher_pair_indicator": 10.0,
                "lower_pair_indicator": 10.0,
            },
        ]
        selected, available = _select_high_cells(actions, 2)
        self.assertEqual(available, 3)
        self.assertEqual(selected, (2, 5))
        all_selected, _ = _select_high_cells(actions, None)
        self.assertEqual(all_selected, (2, 5, 7))
        with self.assertRaises(ValueError):
            _select_high_cells(actions, 4)

    def test_formal_h10_controlled_negative_record_is_preserved(self) -> None:
        root = Path(__file__).resolve().parents[2]
        record = json.loads(
            (
                root
                / "benchmarks/cases/095_high_order_local_hp_resource_envelope"
                / "records/regionwise_p4trace_p6interior_h10_mpi8.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            record["status"], "actual_regionwise_p_controlled_negative"
        )
        self.assertTrue(record["qualification"]["pass"])
        self.assertFalse(record["candidate_accuracy_pass"])
        self.assertEqual(
            record["resource_authority"]["max_observed_worker_rank_count"], 8
        )
        self.assertEqual(record["resource_authority"]["max_process_tree_swap_mb"], 0.0)
        candidate = record["candidate"]
        self.assertLessEqual(candidate["linear_system_relative_residual"], 1.0e-9)
        self.assertEqual(candidate["matrix_stats"]["matrix_rows"], 21824)
        self.assertEqual(candidate["matrix_stats"]["matrix_nnz_used"], 8184464.0)
        cell_audit = candidate["cell_static_condensation"]
        self.assertEqual(cell_audit["active_full3d_equivalent_dofs"], 88994)
        self.assertEqual(cell_audit["regionwise_high_cell_count"], 105)
        self.assertEqual(cell_audit["regionwise_low_cell_count"], 147)
        self.assertFalse(cell_audit["full_global_matrix_allocated"])
        self.assertFalse(cell_audit["full_trace_matrix_allocated"])
        self.assertFalse(cell_audit["inactive_max_p_rows_retained_in_matrix"])
        self.assertFalse(
            record["observable_comparison"][
                "all_scalar_same_code_bands_pass"
            ]
        )
        self.assertFalse(record["diffraction_channel_comparison"]["pass"])
        self.assertFalse(record["selected_field_interface_error_gate"]["pass"])

    def test_p5_trace_n62_controlled_negative_record_is_preserved(self) -> None:
        root = Path(__file__).resolve().parents[2]
        record = json.loads(
            (
                root
                / "benchmarks/cases/095_high_order_local_hp_resource_envelope"
                / "records/regionwise_p5trace_p4low_p6high_n62_h10_mpi8.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(
            record["status"], "actual_regionwise_p_controlled_negative"
        )
        self.assertTrue(record["qualification"]["pass"])
        self.assertFalse(record["candidate_accuracy_pass"])
        self.assertEqual(
            record["resource_authority"]["max_observed_worker_rank_count"], 8
        )
        self.assertEqual(record["resource_authority"]["max_process_tree_swap_mb"], 0.0)
        candidate = record["candidate"]
        self.assertLessEqual(candidate["linear_system_relative_residual"], 1.0e-9)
        self.assertEqual(candidate["matrix_stats"]["matrix_rows"], 35000)
        self.assertEqual(candidate["matrix_stats"]["matrix_nnz_used"], 20140928.0)
        cell_audit = candidate["cell_static_condensation"]
        self.assertEqual(cell_audit["active_full3d_equivalent_dofs"], 89755)
        self.assertEqual(cell_audit["regionwise_high_cell_count"], 62)
        self.assertEqual(cell_audit["regionwise_low_cell_count"], 190)
        self.assertFalse(cell_audit["inactive_max_p_rows_retained_in_matrix"])
        self.assertFalse(
            record["observable_comparison"][
                "all_scalar_same_code_bands_pass"
            ]
        )
        self.assertFalse(record["diffraction_channel_comparison"]["pass"])
        self.assertFalse(record["selected_field_interface_error_gate"]["pass"])

    def test_formal_hexa_p4_p5_multi_goal_dwr_record_is_preserved(self) -> None:
        root = Path(__file__).resolve().parents[2]
        record = json.loads(
            (
                root
                / "benchmarks/cases/095_high_order_local_hp_resource_envelope"
                / "records/same_mesh_hexa_p4_p5_goal_dwr_h10_mpi8.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(record["status"], "target_goal_weighted_two_level_pass")
        self.assertTrue(record["qualification"]["pass"])
        self.assertEqual(record["qualification"]["failures"], [])
        self.assertEqual(
            record["source"]["commit_sha"],
            "56310afa46465ae2e0316c957cf00fd385fa0997",
        )
        self.assertTrue(record["source"]["stable_and_clean_after"])
        resource = record["resource_authority"]
        self.assertEqual(resource["max_observed_worker_rank_count"], 8)
        self.assertEqual(resource["max_process_tree_swap_mb"], 0.0)
        self.assertAlmostEqual(resource["memory_authority_gib"], 15.484783172607422)

        coarse = record["coarse"]
        enriched = record["enriched"]
        self.assertEqual((coarse["degree"], enriched["degree"]), (4, 5))
        self.assertEqual(
            (coarse["num_mesh_cells"], enriched["num_mesh_cells"]),
            (252, 252),
        )
        self.assertLessEqual(coarse["linear_system_relative_residual"], 1.0e-9)
        self.assertLessEqual(enriched["linear_system_relative_residual"], 1.0e-9)
        self.assertLessEqual(
            record["DWR"]["residual"][
                "enriched_solution_relative_residual_recomputed"
            ],
            1.0e-9,
        )

        expected_marked_counts = {
            "R00_total": 84,
            "R_total": 84,
            "T_total": 78,
        }
        for goal, expected_count in expected_marked_counts.items():
            report = record["DWR"]["goals"][goal]
            self.assertEqual(report["marking"]["count"], expected_count)
            self.assertGreaterEqual(report["marking"]["captured_fraction"], 0.5)
            self.assertAlmostEqual(report["absolute_effectivity"], 1.0, places=9)
            self.assertEqual(
                len(report["marked_canonical_cell_ids"]),
                expected_count,
            )
            self.assertEqual(
                report["cell_indicator_snapshot"]["cell_count"],
                252,
            )

        combined = record["DWR"]["combined_relative_R_T"]
        normalized = record["DWR"]["tolerance_normalized_R_T"]
        self.assertEqual(combined["marking"]["count"], 81)
        self.assertEqual(normalized["marking"]["count"], 78)
        self.assertGreaterEqual(normalized["marking"]["captured_fraction"], 0.5)
        self.assertEqual(
            normalized["normalization_authority"]["record_path"],
            "benchmarks/cases/093_fixed_geometry_ph_convergence_mpi"
            "/records/convergence_summary.json",
        )
        self.assertTrue(record["DWR"]["adjoint_qualification"]["pass"])
        self.assertEqual(
            record["DWR"]["adjoint_qualification"]["official_goals"],
            ["R00_total", "R_total", "T_total"],
        )
        self.assertEqual(record["R5_control"]["marking"]["count"], 63)
        self.assertTrue(record["R5_control"]["correction_energy"])

    def test_multigoal_hp_screening_record_is_preserved(self) -> None:
        root = Path(__file__).resolve().parents[2]
        record = json.loads(
            (
                root
                / "benchmarks/cases/095_high_order_local_hp_resource_envelope"
                / "records/same_mesh_p4_p5_p6_multigoal_hp_classifier_v2.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(record["status"], "multigoal_hp_screening_pass")
        self.assertTrue(record["pass"])
        self.assertFalse(record["production_qualified"])
        self.assertEqual(
            record["generator_source"]["verified_clean_sha"],
            "ac31b6b62cee0185214f2f44a985024393535ea0",
        )
        self.assertEqual(record["cell_count"], 252)
        self.assertEqual(record["raw_goal_important_cell_count"], 99)
        self.assertEqual(record["goal_important_cell_count"], 102)
        self.assertEqual(
            record[
                "periodic_goal_marker_closure_added_canonical_cell_ids"
            ],
            [213, 227, 241],
        )
        self.assertEqual(
            record["action_counts"],
            {
                "h_refine_candidate": 0,
                "p_down_candidate": 0,
                "p_keep_candidate": 150,
                "p_up_candidate": 102,
                "undetermined": 0,
            },
        )
        self.assertTrue(record["periodic_decision_audit"]["pass"])
        self.assertEqual(
            record["periodic_decision_audit"]["mate_group_count"],
            126,
        )
        priors = record["cell_geometry_priors"]
        self.assertEqual(
            priors["material_counts"],
            {"air": 162, "grating": 72, "substrate": 18},
        )
        self.assertEqual(priors["material_interface_cell_count"], 174)
        self.assertEqual(priors["corner_or_edge_junction_cell_count"], 18)
        self.assertEqual(
            record["signal_coverage"]["target_cell_local_projection_defect"],
            "not_available",
        )
        self.assertIn(
            "actual_local_h_vs_p_cost_normalized_competition",
            record["missing_required_signals"],
        )

    def test_p4_trace_p6_interior_custom_element_contains_p4(self) -> None:
        reduced = create_reduced_trace_hcurl_element(4, 6)
        audit = reduced.audit
        self.assertTrue(audit["pass"])
        self.assertEqual(audit["custom_dimension"], 642)
        self.assertEqual(audit["trace_dimension"], 192)
        self.assertEqual(audit["low_interior_dimension"], 108)
        self.assertEqual(audit["high_interior_dimension"], 450)
        self.assertEqual(audit["low_space_embedding_rank"], 300)
        self.assertEqual(audit["low_interior_embedding_rank"], 108)
        self.assertLess(audit["low_interior_trace_leakage_max"], 1.0e-11)
        self.assertTrue(audit["high_exact_sequence"]["pass"])
        self.assertEqual(
            audit["high_exact_sequence"]["measured_curl_nullity"],
            222,
        )
        self.assertTrue(audit["low_exact_sequence"]["pass"])
        self.assertEqual(
            audit["low_exact_sequence"]["measured_curl_nullity"],
            124,
        )
        self.assertTrue(audit["both_high_and_low_exact_sequence_pass"])
        self.assertEqual(
            audit["entity_dofs"],
            [
                [0] * 8,
                [4] * 12,
                [24] * 6,
                [450],
            ],
        )

        standard_p4 = basix.ufl.element(
            "N1curl", "hexahedron", 4
        ).basix_element
        points = np.asarray(
            (
                (0.13, 0.22, 0.31),
                (0.61, 0.47, 0.72),
                (0.89, 0.18, 0.54),
            ),
            dtype=np.float64,
        )
        rng = np.random.default_rng(20260724)
        coefficients = rng.standard_normal(standard_p4.dim)
        reduced_coefficients = reduced.low_to_reduced @ coefficients
        p4_values = np.einsum(
            "qiv,i->qv",
            standard_p4.tabulate(0, points)[0],
            coefficients,
        )
        reduced_values = np.einsum(
            "qiv,i->qv",
            reduced.element.tabulate(0, points)[0],
            reduced_coefficients,
        )
        np.testing.assert_allclose(
            reduced_values,
            p4_values,
            rtol=2.0e-12,
            atol=2.0e-12,
        )

    def test_p5_trace_p4_interior_embeds_exactly_in_p6_interior(self) -> None:
        reduced = create_reduced_trace_hcurl_element(5, 6, 4)
        audit = reduced.audit
        self.assertTrue(audit["pass"])
        self.assertEqual(audit["trace_degree"], 5)
        self.assertEqual(audit["low_interior_degree"], 4)
        self.assertEqual(audit["interior_degree"], 6)
        self.assertEqual(audit["custom_dimension"], 750)
        self.assertEqual(audit["standard_low_dimension"], 408)
        self.assertEqual(audit["trace_dimension"], 300)
        self.assertEqual(audit["low_interior_dimension"], 108)
        self.assertEqual(audit["high_interior_dimension"], 450)
        self.assertEqual(audit["low_space_embedding_rank"], 408)
        self.assertEqual(audit["low_interior_embedding_rank"], 108)
        self.assertLess(audit["low_trace_identity_error_max"], 1.0e-11)
        self.assertLess(audit["low_interior_trace_leakage_max"], 1.0e-11)
        self.assertTrue(audit["high_exact_sequence"]["pass"])
        self.assertEqual(
            audit["high_exact_sequence"]["measured_curl_nullity"],
            276,
        )
        self.assertFalse(audit["low_exact_sequence"]["pass"])
        self.assertEqual(
            audit["low_exact_sequence"][
                "expected_nonconstant_gradient_dimension"
            ],
            178,
        )
        self.assertEqual(
            audit["low_exact_sequence"]["measured_curl_nullity"],
            112,
        )
        self.assertEqual(
            audit["low_exact_sequence"]["missing_gradient_mode_count"],
            66,
        )
        self.assertFalse(audit["both_high_and_low_exact_sequence_pass"])
        self.assertEqual(
            audit["entity_dofs"],
            [
                [0] * 8,
                [5] * 12,
                [40] * 6,
                [450],
            ],
        )

        points = np.asarray(
            (
                (0.13, 0.22, 0.31),
                (0.61, 0.47, 0.72),
                (0.89, 0.18, 0.54),
            ),
            dtype=np.float64,
        )
        rng = np.random.default_rng(2026072402)
        coefficients = rng.standard_normal(reduced.low_element.dim)
        high_coefficients = reduced.low_to_reduced @ coefficients
        low_values = np.einsum(
            "qiv,i->qv",
            reduced.low_element.tabulate(0, points)[0],
            coefficients,
        )
        high_values = np.einsum(
            "qiv,i->qv",
            reduced.element.tabulate(0, points)[0],
            high_coefficients,
        )
        np.testing.assert_allclose(
            high_values,
            low_values,
            rtol=2.0e-11,
            atol=2.0e-11,
        )

    def test_two_cell_space_has_one_shared_conforming_p4_trace(self) -> None:
        comm = MPI.COMM_WORLD
        msh = mesh.create_box(
            comm,
            ((0.0, 0.0, 0.0), (2.0, 1.0, 1.0)),
            (2, 1, 1),
            cell_type=mesh.CellType.hexahedron,
        )
        reduced_element = reduced_trace_hcurl_ufl_element(4, 6)
        space = fem.functionspace(msh, reduced_element)
        standard_p6 = fem.functionspace(
            msh,
            basix.ufl.element("N1curl", "hexahedron", 6),
        )
        for dimension in (1, 2):
            msh.topology.create_entities(dimension)
        edges = int(msh.topology.index_map(1).size_global)
        faces = int(msh.topology.index_map(2).size_global)
        cells = int(msh.topology.index_map(3).size_global)
        expected = edges * 4 + faces * 24 + cells * 450
        actual = int(space.dofmap.index_map.size_global)
        self.assertEqual(actual, expected)
        self.assertEqual(cells, 2)
        self.assertEqual(actual, 1244)
        self.assertLess(actual, int(standard_p6.dofmap.index_map.size_global))
        self.assertEqual(
            2 * 642 - actual,
            4 * 4 + 24,
            "the two cells must share exactly one p4 face trace",
        )

        field = fem.Function(space)
        field.interpolate(
            lambda x: np.vstack(
                (
                    x[1] ** 2 + x[2],
                    x[0] * x[2],
                    x[0] ** 2 - x[1],
                )
            )
        )
        coordinate = ufl.SpatialCoordinate(msh)
        exact = ufl.as_vector(
            (
                coordinate[1] ** 2 + coordinate[2],
                coordinate[0] * coordinate[2],
                coordinate[0] ** 2 - coordinate[1],
            )
        )
        local_error = fem.assemble_scalar(
            fem.form(ufl.inner(field - exact, field - exact) * ufl.dx)
        )
        error = float(comm.allreduce(float(np.real(local_error)), op=MPI.SUM))
        self.assertLess(error, 1.0e-20)

    def test_config_opt_in_creates_reduced_trace_space(self) -> None:
        cfg = SimulationConfig3D(
            nedelec_degree=6,
            nedelec_trace_degree=4,
            nedelec_interior_degree=6,
        )
        self.assertTrue(cfg.nedelec_reduced_trace_enabled)
        self.assertEqual(cfg.nedelec_trace_degree_resolved, 4)
        self.assertEqual(cfg.nedelec_interior_degree_resolved, 6)
        snapshot = cfg.as_jsonable()
        self.assertEqual(snapshot["nedelec_trace_degree_resolved"], 4)
        self.assertEqual(snapshot["nedelec_interior_degree_resolved"], 6)
        self.assertTrue(snapshot["nedelec_reduced_trace_enabled"])
        self.assertEqual(
            snapshot["stage4_regionwise_low_interior_degree_resolved"],
            4,
        )

        msh = mesh.create_box(
            MPI.COMM_WORLD,
            ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)),
            (1, 1, 1),
            cell_type=mesh.CellType.hexahedron,
        )
        space = _create_nedelec_space(msh, cfg)
        self.assertEqual(space.element.space_dimension, 642)
        self.assertEqual(
            [len(dofs) for dofs in space.element.basix_element.entity_dofs[1]],
            [4] * 12,
        )
        self.assertEqual(
            [len(dofs) for dofs in space.element.basix_element.entity_dofs[2]],
            [24] * 6,
        )

        mixed_cfg = SimulationConfig3D(
            nedelec_degree=6,
            nedelec_trace_degree=5,
            nedelec_interior_degree=6,
            stage4_regionwise_low_interior_degree=4,
        )
        self.assertEqual(
            mixed_cfg.stage4_regionwise_low_interior_degree_resolved,
            4,
        )

    def test_classifier_lane_hits_task035b_90k_active_dof_gate(self) -> None:
        budget = regionwise_interior_p_dof_budget(
            global_edges=1067,
            global_faces=900,
            global_cells=252,
            high_interior_cells=105,
            trace_degree=4,
            low_interior_degree=4,
            high_interior_degree=6,
        )
        self.assertTrue(budget["pass"])
        self.assertEqual(budget["active_trace_dofs"], 25868)
        self.assertEqual(budget["active_cell_interior_dofs"], 63126)
        self.assertEqual(budget["active_full3d_equivalent_dofs"], 88994)
        self.assertFalse(budget["inactive_max_p_rows_retained_in_matrix"])

        minimum = regionwise_interior_p_dof_budget(
            global_edges=1067,
            global_faces=900,
            global_cells=252,
            high_interior_cells=62,
            trace_degree=5,
            low_interior_degree=4,
            high_interior_degree=6,
        )
        self.assertEqual(minimum["active_trace_dofs"], 41335)
        self.assertEqual(minimum["active_full3d_equivalent_dofs"], 89755)
        preferred = regionwise_interior_p_dof_budget(
            global_edges=1067,
            global_faces=900,
            global_cells=252,
            high_interior_cells=18,
            trace_degree=5,
            low_interior_degree=4,
            high_interior_degree=6,
        )
        self.assertEqual(preferred["active_full3d_equivalent_dofs"], 74707)


if __name__ == "__main__":
    unittest.main()
