from __future__ import annotations

import inspect
from types import SimpleNamespace
import unittest

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.modes.mode_classification import (
    NoAdmissibleLeftPairError,
    _batched_left_dots,
    _identity_error_metrics,
    _joint_left_basis_inverse,
    _near_degenerate_partition_audit,
    _qep_overlap,
    _qep_overlap_matrix,
    _require_admissible_left_pairs,
    _task036_scalar_stage4_partition_repair_candidate,
    build_biorthogonal_mode_basis,
    build_scalar_stage4_reciprocal_negative_basis,
    classify_mode_branch,
    pair_reciprocal_mode_bases,
    select_passive_direction_modes,
    track_mode_bases,
)
from src.modes.quadratic_beta_eigenproblem import (
    analytic_homogeneous_beta,
    assemble_quadratic_beta_operators,
    solve_quadratic_beta_modes,
)
from src.modes.stable_propagation import (
    build_two_sided_propagation,
    diagnose_reciprocity_and_passivity,
)


class Task032ModeClassificationTests(unittest.TestCase):
    @staticmethod
    def _build_air_basis(*, theta_deg: float, requested_modes: int):
        cfg = target_stage4_config(degree=2, h_nm=10.0)
        cfg.incident_theta_deg = float(theta_deg)
        cross_section = build_matching_cross_section(cfg, "air")
        spaces = build_cross_section_spaces(cross_section, transverse_degree=2)
        operators = assemble_quadratic_beta_operators(cfg, cross_section, spaces)
        target = analytic_homogeneous_beta(cfg, cfg.n_air)
        right_modes, _ = solve_quadratic_beta_modes(
            operators,
            target=target,
            requested_modes=requested_modes,
        )
        basis = build_biorthogonal_mode_basis(
            cfg,
            cross_section,
            spaces,
            operators,
            right_modes,
            adjoint_target=np.conj(target),
            requested_left_modes=requested_modes,
        )
        return cfg, cross_section, spaces, operators, target, basis

    def test_branch_rules_cover_flux_evanescent_and_cutoff(self):
        self.assertEqual(
            classify_mode_branch(1.0 + 0.01j, 2.0, 1.0e-8, 1.0e-10),
            ("lossy_propagating", "forward", "poynting_flux", True),
        )
        self.assertEqual(
            classify_mode_branch(-1.0 - 0.01j, -2.0, 1.0e-8, 1.0e-10),
            ("lossy_propagating", "backward", "poynting_flux", True),
        )
        self.assertEqual(
            classify_mode_branch(0.0 + 0.4j, 0.0, 1.0e-8, 1.0e-10),
            ("evanescent", "forward", "positive_imag_beta_decay", True),
        )
        self.assertEqual(
            classify_mode_branch(0.0 - 0.4j, 0.0, 1.0e-8, 1.0e-10),
            ("evanescent", "backward", "negative_imag_beta_decay", True),
        )
        self.assertEqual(
            classify_mode_branch(0.0 + 0.0j, 0.0, 1.0e-8, 1.0e-10),
            (
                "cutoff_or_near_zero_flux",
                "ambiguous",
                "near_zero_flux_and_beta_imag",
                False,
            ),
        )

    def test_left_pair_admissibility_fails_closed_before_normalization(self):
        _require_admissible_left_pairs(
            (6.6e-12, 1.0e-7), maximum_relative_error=1.0e-7
        )
        for errors in ((6.6e-12, 1.310935), (float("nan"),), (float("inf"),)):
            with self.subTest(errors=errors):
                with self.assertRaisesRegex(
                    NoAdmissibleLeftPairError,
                    "no admissible conjugate partner",
                ):
                    _require_admissible_left_pairs(
                        errors, maximum_relative_error=1.0e-7
                    )
        with self.assertRaisesRegex(ValueError, "finite and non-negative"):
            _require_admissible_left_pairs(
                (0.0,), maximum_relative_error=float("nan")
            )

    def test_identity_error_metrics_separate_entry_and_matrix_norms(self):
        matrix = np.eye(3, dtype=np.complex128)
        matrix[0, 1:] = 4.0e-7
        infinity_norm, max_entry = _identity_error_metrics(matrix)
        self.assertAlmostEqual(infinity_norm, 8.0e-7)
        self.assertAlmostEqual(max_entry, 4.0e-7)
        with self.assertRaisesRegex(ValueError, "must be square"):
            _identity_error_metrics(np.ones((2, 3), dtype=np.complex128))

    def test_partition_audit_distinguishes_near_and_generic_cross_block(self):
        overlap = np.eye(2, dtype=np.complex128)
        overlap[0, 1] = 1.0381411855660379e-6
        near = _near_degenerate_partition_audit(
            (
                0.00022773153728096115 + 0.5908874967756957j,
                0.00022742745503172594 + 0.5908881315892522j,
            ),
            ((0,), (1,)),
            overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
            directions=("forward", "forward"),
        )
        self.assertFalse(near["pass"])
        self.assertEqual(
            near["status"],
            "near_degenerate_block_partition_split",
        )
        self.assertTrue(
            near["worst_cross_block_is_near_degenerate_candidate"]
        )
        self.assertEqual(
            near["worst_cross_block_directions"],
            ["forward", "forward"],
        )
        self.assertEqual(near["group_members"], [[0], [1]])
        self.assertEqual(
            near["worst_cross_block_group_members"],
            [[0], [1]],
        )
        self.assertGreater(
            near["biorthogonality_identity_row_norm"],
            1.0e-6,
        )

        separated = _near_degenerate_partition_audit(
            (0.0 + 0.1j, 0.0 + 0.9j),
            ((0,), (1,)),
            overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
            directions=("forward", "forward"),
        )
        self.assertFalse(separated["pass"])
        self.assertEqual(
            separated["status"],
            "cross_block_biorthogonality_failure",
        )
        self.assertFalse(
            separated["worst_cross_block_is_near_degenerate_candidate"]
        )

    def test_partition_audit_enforces_full_identity_row_norm_gate(self):
        overlap = np.eye(3, dtype=np.complex128)
        overlap[0, 1:] = 6.0e-7
        audit = _near_degenerate_partition_audit(
            (0.1 + 0.2j, 0.1 + 0.200001j, 0.1 + 0.200002j),
            ((0,), (1,), (2,)),
            overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
            directions=("forward",) * 3,
        )
        self.assertLess(audit["max_cross_block_overlap"], 1.0e-6)
        self.assertTrue(
            audit["max_cross_block_overlap_within_tolerance"]
        )
        self.assertGreater(
            audit["biorthogonality_identity_row_norm"],
            1.0e-6,
        )
        self.assertFalse(
            audit["biorthogonality_identity_row_norm_within_tolerance"]
        )
        self.assertFalse(audit["pass"])

    def test_task036_partition_repair_policy_is_bounded_and_opt_in(self):
        parameter = inspect.signature(
            build_biorthogonal_mode_basis
        ).parameters["task036_scalar_stage4_partition_repair"]
        self.assertIs(parameter.default, False)

        scalar_stage4 = SimpleNamespace(
            material_kind="stage4_xy",
            epsilon_r=SimpleNamespace(ufl_shape=()),
        )
        groups = ((0, 1), (2, 3))
        overlap = np.eye(4, dtype=np.complex128)
        overlap[1, 2] = 2.0e-6
        audit = _near_degenerate_partition_audit(
            (
                0.5 + 0.1j,
                0.5 + 0.1j,
                0.5 + 0.100001j,
                0.5 + 0.100001j,
            ),
            groups,
            overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
            directions=("forward",) * 4,
        )
        merged, provenance = (
            _task036_scalar_stage4_partition_repair_candidate(
                scalar_stage4,
                groups,
                audit,
                betas=(
                    0.5 + 0.1j,
                    0.5 + 0.1j,
                    0.5 + 0.100001j,
                    0.5 + 0.100001j,
                ),
                directions=("forward",) * 4,
                biorthogonality=overlap,
                near_degenerate_tolerance=1.0e-6,
                block_rotation_tolerance=1.0e-6,
                maximum_overlap_condition=1.0e12,
            )
        )
        self.assertEqual(merged, ((0, 1, 2, 3),))
        self.assertTrue(provenance["eligible"])
        self.assertEqual(provenance["maximum_attempts"], 1)
        self.assertEqual(provenance["maximum_union_size"], 8)
        self.assertEqual(provenance["component_count"], 1)

        for cross_section, changed_directions, expected_reason in (
            (
                SimpleNamespace(
                    material_kind="air",
                    epsilon_r=SimpleNamespace(ufl_shape=()),
                ),
                ("forward",) * 4,
                "not_scalar_stage4_xy",
            ),
            (
                scalar_stage4,
                ("forward", "forward", "backward", "backward"),
                "row_norm_failure_not_explained_by_near_cross_blocks",
            ),
        ):
            with self.subTest(reason=expected_reason):
                rejected, rejected_provenance = (
                    _task036_scalar_stage4_partition_repair_candidate(
                        cross_section,
                        groups,
                        audit,
                        betas=(
                            0.5 + 0.1j,
                            0.5 + 0.1j,
                            0.5 + 0.100001j,
                            0.5 + 0.100001j,
                        ),
                        directions=changed_directions,
                        biorthogonality=overlap,
                        near_degenerate_tolerance=1.0e-6,
                        block_rotation_tolerance=1.0e-6,
                        maximum_overlap_condition=1.0e12,
                    )
                )
                self.assertIsNone(rejected)
                self.assertEqual(
                    rejected_provenance["reason"],
                    expected_reason,
                )

        oversized, oversized_provenance = (
            _task036_scalar_stage4_partition_repair_candidate(
                scalar_stage4,
                ((0, 1, 2, 3, 4), (5, 6, 7, 8)),
                {**audit, "pass": False},
                betas=tuple(0.5 + index * 1.0e-8j for index in range(9)),
                directions=("forward",) * 9,
                biorthogonality=(
                    np.eye(9, dtype=np.complex128)
                    + np.diag([2.0e-6] * 4, k=5)
                ),
                near_degenerate_tolerance=1.0e-6,
                block_rotation_tolerance=1.0e-6,
                maximum_overlap_condition=1.0e12,
            )
        )
        self.assertIsNone(oversized)
        self.assertEqual(
            oversized_provenance["reason"],
            "connected_component_exceeds_bounded_size",
        )

    def test_task036_partition_repair_plans_all_connected_components(self):
        scalar_stage4 = SimpleNamespace(
            material_kind="stage4_xy",
            epsilon_r=SimpleNamespace(ufl_shape=()),
        )
        groups = ((0, 1), (2, 3), (4, 5), (6, 7))
        betas = (
            0.5 + 0.1j,
            0.5 + 0.1j,
            0.5 + 0.100001j,
            0.5 + 0.100001j,
            0.7 + 0.2j,
            0.7 + 0.2j,
            0.7 + 0.200001j,
            0.7 + 0.200001j,
        )
        overlap = np.eye(8, dtype=np.complex128)
        overlap[1, 2] = 2.0e-6
        overlap[5, 6] = 3.0e-6
        audit = _near_degenerate_partition_audit(
            betas,
            groups,
            overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
            directions=("forward",) * 4 + ("backward",) * 4,
        )
        components, provenance = (
            _task036_scalar_stage4_partition_repair_candidate(
                scalar_stage4,
                groups,
                audit,
                betas=betas,
                directions=("forward",) * 4 + ("backward",) * 4,
                biorthogonality=overlap,
                near_degenerate_tolerance=1.0e-6,
                block_rotation_tolerance=1.0e-6,
                maximum_overlap_condition=1.0e12,
            )
        )
        self.assertEqual(
            components,
            ((0, 1, 2, 3), (4, 5, 6, 7)),
        )
        self.assertEqual(provenance["component_count"], 2)
        self.assertEqual(provenance["edge_count"], 2)

        transitive_overlap = np.eye(3, dtype=np.complex128)
        transitive_overlap[0, 1] = 2.0e-6
        transitive_overlap[1, 2] = 2.0e-6
        transitive_betas = (
            0.5 + 0.1j,
            0.5 + 0.100001j,
            0.5 + 0.100002j,
        )
        transitive_audit = _near_degenerate_partition_audit(
            transitive_betas,
            ((0,), (1,), (2,)),
            transitive_overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
            directions=("forward",) * 3,
        )
        transitive, _ = _task036_scalar_stage4_partition_repair_candidate(
            scalar_stage4,
            ((0,), (1,), (2,)),
            transitive_audit,
            betas=transitive_betas,
            directions=("forward",) * 3,
            biorthogonality=transitive_overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
            maximum_overlap_condition=1.0e12,
        )
        self.assertEqual(transitive, ((0, 1, 2),))

        subthreshold_overlap = np.eye(5, dtype=np.complex128)
        subthreshold_overlap[0, 1] = 6.0e-7
        subthreshold_overlap[0, 2] = 6.0e-7
        subthreshold_overlap[0, 3] = 6.0e-7
        subthreshold_overlap[4, 3] = 2.0e-7
        subthreshold_betas = (
            0.5 + 0.1j,
            0.5 + 0.100001j,
            0.5 + 0.100002j,
            0.5 + 0.100003j,
            0.7 + 0.2j,
        )
        subthreshold_audit = _near_degenerate_partition_audit(
            subthreshold_betas,
            ((0,), (1,), (2,), (3,), (4,)),
            subthreshold_overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
            directions=("forward",) * 5,
        )
        self.assertTrue(
            subthreshold_audit[
                "max_cross_block_overlap_within_tolerance"
            ]
        )
        self.assertFalse(
            subthreshold_audit[
                "biorthogonality_identity_row_norm_within_tolerance"
            ]
        )
        subthreshold, provenance = (
            _task036_scalar_stage4_partition_repair_candidate(
                scalar_stage4,
                ((0,), (1,), (2,), (3,), (4,)),
                subthreshold_audit,
                betas=subthreshold_betas,
                directions=("forward",) * 5,
                biorthogonality=subthreshold_overlap,
                near_degenerate_tolerance=1.0e-6,
                block_rotation_tolerance=1.0e-6,
                maximum_overlap_condition=1.0e12,
            )
        )
        self.assertEqual(subthreshold, ((0, 1, 2),))
        self.assertEqual(
            provenance["full_row_norm_failure_seed_group_ids"],
            [0],
        )
        self.assertEqual(
            provenance["row_failure_plans"][0][
                "selected_partner_group_ids"
            ],
            [1, 2],
        )
        self.assertLess(provenance["connected_edge_noise_floor"], 1.0e-10)

        a001_overlap = np.eye(4, dtype=np.complex128)
        a001_overlap[2, 0] = 9.328995705e-7
        a001_overlap[2, 1] = 9.328995705e-7
        a001_betas = (
            0.5 + 0.1000000j,
            0.5 + 0.1000000j,
            0.5 + 0.1000036j,
            0.5 + 0.1000036j,
        )
        a001_audit = _near_degenerate_partition_audit(
            a001_betas,
            ((0, 1), (2, 3)),
            a001_overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
            directions=("forward",) * 4,
        )
        self.assertLess(a001_audit["max_cross_block_overlap"], 1.0e-6)
        self.assertGreater(
            a001_audit["biorthogonality_identity_row_norm"],
            1.0e-6,
        )
        a001_component, _ = (
            _task036_scalar_stage4_partition_repair_candidate(
                scalar_stage4,
                ((0, 1), (2, 3)),
                a001_audit,
                betas=a001_betas,
                directions=("forward",) * 4,
                biorthogonality=a001_overlap,
                near_degenerate_tolerance=1.0e-6,
                block_rotation_tolerance=1.0e-6,
                maximum_overlap_condition=1.0e12,
            )
        )
        self.assertEqual(a001_component, ((0, 1, 2, 3),))

    def test_task036_partition_repair_plans_same_group_refinement(self):
        scalar_stage4 = SimpleNamespace(
            material_kind="stage4_xy",
            epsilon_r=SimpleNamespace(ufl_shape=()),
        )
        groups = ((0, 1, 2, 3), (4, 5))
        betas = (
            0.5 + 0.1000000j,
            0.5 + 0.1000001j,
            0.5 + 0.1000002j,
            0.5 + 0.1000003j,
            0.9 + 0.2j,
            0.9 + 0.2000001j,
        )
        overlap = np.eye(6, dtype=np.complex128)
        overlap[0, 1] = 2.0e-6
        overlap[3, 2] = -1.5e-6j
        audit = _near_degenerate_partition_audit(
            betas,
            groups,
            overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
            directions=("forward",) * 6,
        )

        components, provenance = _task036_scalar_stage4_partition_repair_candidate(
            scalar_stage4,
            groups,
            audit,
            betas=betas,
            directions=("forward",) * 6,
            biorthogonality=overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
            maximum_overlap_condition=1.0e12,
            initial_group_overlap_conditions=(7.25, 1.0),
        )

        self.assertEqual(components, ((0, 1, 2, 3),))
        self.assertTrue(provenance["eligible"])
        self.assertEqual(provenance["maximum_attempts"], 1)
        self.assertEqual(
            provenance["same_group_refinement_group_ids"],
            [0],
        )
        self.assertEqual(
            provenance["same_group_refinement_component_count"],
            1,
        )
        self.assertEqual(
            provenance["components"][0]["component_kind"],
            "same_group_refinement",
        )
        self.assertEqual(
            provenance["components"][0]["source_group_initial_raw_overlap_conditions"],
            [7.25],
        )
        diagnostics = provenance["group_condition_diagnostics"]
        self.assertEqual(diagnostics[0]["group_members"], [0, 1, 2, 3])
        self.assertEqual(
            diagnostics[0]["initial_raw_overlap_condition"],
            7.25,
        )
        for row_plan in provenance["row_failure_plans"]:
            self.assertTrue(row_plan["same_group_refinement_sufficient"])
            self.assertGreater(
                row_plan["within_group_row_error"],
                row_plan["required_reduction"],
            )
            self.assertEqual(
                row_plan["eligible_near_cross_row_error"],
                0.0,
            )
            self.assertEqual(row_plan["far_cross_row_error"], 0.0)
            self.assertLessEqual(
                row_plan["row_error_decomposition_closure"],
                1.0e-20,
            )

    def test_task036_same_group_refinement_rejects_far_cross_budget(self):
        scalar_stage4 = SimpleNamespace(
            material_kind="stage4_xy",
            epsilon_r=SimpleNamespace(ufl_shape=()),
        )
        groups = ((0, 1), (2, 3))
        betas = (
            0.5 + 0.1j,
            0.5 + 0.1000001j,
            0.9 + 0.2j,
            0.9 + 0.2000001j,
        )
        overlap = np.eye(4, dtype=np.complex128)
        overlap[0, 1] = 8.0e-7
        overlap[0, 2] = 1.2e-6
        audit = _near_degenerate_partition_audit(
            betas,
            groups,
            overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
            directions=("forward",) * 4,
        )

        components, provenance = _task036_scalar_stage4_partition_repair_candidate(
            scalar_stage4,
            groups,
            audit,
            betas=betas,
            directions=("forward",) * 4,
            biorthogonality=overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
            maximum_overlap_condition=1.0e12,
        )

        self.assertIsNone(components)
        self.assertEqual(
            provenance["reason"],
            "row_norm_failure_not_explained_by_near_cross_blocks",
        )
        row_plan = provenance["unexplained_row_failures"][0]
        self.assertAlmostEqual(
            row_plan["within_group_row_error"],
            8.0e-7,
        )
        self.assertEqual(row_plan["eligible_near_cross_row_error"], 0.0)
        self.assertAlmostEqual(row_plan["far_cross_row_error"], 1.2e-6)
        self.assertEqual(
            row_plan["unexplained_reason"],
            "far_cross_row_budget_exceeds_tolerance",
        )

    def test_task036_partition_repair_plans_cross_and_self_once(self):
        scalar_stage4 = SimpleNamespace(
            material_kind="stage4_xy",
            epsilon_r=SimpleNamespace(ufl_shape=()),
        )
        groups = ((0, 1), (2, 3), (4, 5, 6, 7))
        betas = (
            0.5 + 0.100000j,
            0.5 + 0.100000j,
            0.5 + 0.100001j,
            0.5 + 0.100001j,
            0.9 + 0.2000000j,
            0.9 + 0.2000001j,
            0.9 + 0.2000002j,
            0.9 + 0.2000003j,
        )
        overlap = np.eye(8, dtype=np.complex128)
        overlap[1, 2] = 2.0e-6
        overlap[4, 5] = 2.5e-6
        audit = _near_degenerate_partition_audit(
            betas,
            groups,
            overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
            directions=("forward",) * 8,
        )

        components, provenance = _task036_scalar_stage4_partition_repair_candidate(
            scalar_stage4,
            groups,
            audit,
            betas=betas,
            directions=("forward",) * 8,
            biorthogonality=overlap,
            near_degenerate_tolerance=1.0e-6,
            block_rotation_tolerance=1.0e-6,
            maximum_overlap_condition=1.0e12,
        )

        self.assertEqual(
            components,
            ((0, 1, 2, 3), (4, 5, 6, 7)),
        )
        self.assertEqual(provenance["component_count"], 2)
        self.assertEqual(
            [component["component_kind"] for component in provenance["components"]],
            [
                "connected_near_beta_groups",
                "same_group_refinement",
            ],
        )
        self.assertEqual(
            provenance["same_group_refinement_component_count"],
            1,
        )

    def test_task036_joint_left_inverse_repairs_selected_block(self):
        overlap = np.eye(4, dtype=np.complex128)
        overlap[0, 2] = 2.0e-6 + 3.0e-7j
        overlap[3, 1] = -3.0e-6j
        left_reduced: list[PETSc.Vec] = []
        left_full: list[PETSc.Vec] = []
        for row in overlap:
            reduced = PETSc.Vec().createSeq(4, comm=PETSc.COMM_SELF)
            reduced.getArray()[:] = np.conj(row)
            reduced.assemble()
            full = reduced.duplicate()
            reduced.copy(full)
            left_reduced.append(reduced)
            left_full.append(full)
        try:
            condition = _joint_left_basis_inverse(
                left_reduced,
                left_full,
                (0, 1, 2, 3),
                overlap,
                maximum_overlap_condition=1.0e12,
            )
            self.assertTrue(np.isfinite(condition))
            repaired = np.asarray(
                [
                    np.conj(vector.getArray(readonly=True))
                    for vector in left_reduced
                ],
                dtype=np.complex128,
            )
            np.testing.assert_allclose(
                repaired,
                np.eye(4, dtype=np.complex128),
                rtol=1.0e-13,
                atol=1.0e-13,
            )
            for reduced, full in zip(left_reduced, left_full):
                np.testing.assert_allclose(
                    full.getArray(readonly=True),
                    reduced.getArray(readonly=True),
                    rtol=0.0,
                    atol=0.0,
                )
        finally:
            for vector in left_reduced + left_full:
                vector.destroy()

    def test_task036_joint_left_inverse_repairs_two_disjoint_components(self):
        overlap = np.eye(8, dtype=np.complex128)
        overlap[0, 2] = 2.0e-6 + 3.0e-7j
        overlap[3, 1] = -3.0e-6j
        overlap[4, 6] = -2.5e-6
        overlap[7, 5] = 1.5e-6j
        left_reduced: list[PETSc.Vec] = []
        left_full: list[PETSc.Vec] = []
        for row in overlap:
            reduced = PETSc.Vec().createSeq(8, comm=PETSc.COMM_SELF)
            reduced.getArray()[:] = np.conj(row)
            reduced.assemble()
            full = reduced.duplicate()
            reduced.copy(full)
            left_reduced.append(reduced)
            left_full.append(full)
        try:
            for component in ((0, 1, 2, 3), (4, 5, 6, 7)):
                _joint_left_basis_inverse(
                    left_reduced,
                    left_full,
                    component,
                    overlap[np.ix_(component, component)],
                    maximum_overlap_condition=1.0e12,
                )
            repaired = np.asarray(
                [
                    np.conj(vector.getArray(readonly=True))
                    for vector in left_reduced
                ],
                dtype=np.complex128,
            )
            np.testing.assert_allclose(
                repaired,
                np.eye(8, dtype=np.complex128),
                rtol=1.0e-13,
                atol=1.0e-13,
            )
            self.assertLessEqual(
                _identity_error_metrics(repaired)[0],
                1.0e-12,
            )
        finally:
            for vector in left_reduced + left_full:
                vector.destroy()

    def test_task036_joint_left_inverse_solves_admissible_condition(self):
        overlap = np.asarray(
            [
                [1.0, 1.0],
                [1.0, 1.0 + 1.0e-8],
            ],
            dtype=np.complex128,
        )
        left_reduced: list[PETSc.Vec] = []
        left_full: list[PETSc.Vec] = []
        for row in overlap:
            reduced = PETSc.Vec().createSeq(2, comm=PETSc.COMM_SELF)
            reduced.getArray()[:] = np.conj(row)
            reduced.assemble()
            full = reduced.duplicate()
            reduced.copy(full)
            left_reduced.append(reduced)
            left_full.append(full)
        try:
            condition = _joint_left_basis_inverse(
                left_reduced,
                left_full,
                (0, 1),
                overlap,
                maximum_overlap_condition=1.0e9,
            )
            self.assertGreater(condition, 1.0e8)
            self.assertLess(condition, 1.0e9)
            repaired = np.asarray(
                [np.conj(vector.getArray(readonly=True)) for vector in left_reduced],
                dtype=np.complex128,
            )
            self.assertLessEqual(
                _identity_error_metrics(repaired)[0],
                1.0e-6,
            )
        finally:
            for vector in left_reduced + left_full:
                vector.destroy()

    def test_task036_joint_left_inverse_rejects_bad_condition(self):
        singular = np.asarray(
            [[1.0, 1.0], [1.0, 1.0]],
            dtype=np.complex128,
        )
        left_reduced = [
            PETSc.Vec().createSeq(2, comm=PETSc.COMM_SELF)
            for _ in range(2)
        ]
        left_full = [vector.duplicate() for vector in left_reduced]
        try:
            with self.assertRaisesRegex(
                RuntimeError,
                "singular or ill-conditioned",
            ):
                _joint_left_basis_inverse(
                    left_reduced,
                    left_full,
                    (0, 1),
                    singular,
                    maximum_overlap_condition=1.0e12,
                )
        finally:
            for vector in left_reduced + left_full:
                vector.destroy()

    def test_batched_left_dots_preserve_cancelling_remainder(self):
        comm = MPI.COMM_WORLD
        action = PETSc.Vec().createMPI(
            (3, 3 * comm.size),
            comm=comm,
        )
        left = action.duplicate()
        try:
            action_local = action.getArray()
            left_local = left.getArray()
            action_local[:] = np.asarray(
                [1.0e16, 1.0, -1.0e16],
                dtype=PETSc.ScalarType,
            )
            left_local[:] = PETSc.ScalarType(1.0)
            action.assemble()
            left.assemble()

            values = _batched_left_dots(action, [left])

            np.testing.assert_array_equal(
                values,
                np.asarray([complex(comm.size)], dtype=np.complex128),
            )
        finally:
            action.destroy()
            left.destroy()

    def test_batched_qep_overlap_matches_elementwise_definition(self):
        cfg = target_stage4_config(degree=2, h_nm=10.0)
        cross_section = build_matching_cross_section(cfg, "air")
        spaces = build_cross_section_spaces(cross_section, transverse_degree=2)
        operators = assemble_quadratic_beta_operators(cfg, cross_section, spaces)
        target = analytic_homogeneous_beta(cfg, cfg.n_air)
        modes, _ = solve_quadratic_beta_modes(
            operators, target=target, requested_modes=2
        )
        try:
            betas = [complex(mode.beta) for mode in modes]
            vectors = [mode.right_reduced for mode in modes]
            batched = _qep_overlap_matrix(
                operators, betas, betas, vectors, vectors
            )
            elementwise = np.asarray(
                [
                    [
                        _qep_overlap(operators, left, beta_left, right, beta_right)
                        for beta_right, right in zip(betas, vectors)
                    ]
                    for beta_left, left in zip(betas, vectors)
                ],
                dtype=np.complex128,
            )
            np.testing.assert_allclose(batched, elementwise, rtol=1.0e-12, atol=1.0e-12)
        finally:
            for mode in modes:
                mode.destroy()
            operators.destroy()

    def test_wide_candidate_pool_filters_reciprocal_and_growing_branches(self):
        class Candidate:
            def __init__(self, beta: complex, flux: float):
                self.beta = beta
                self.right_full = self
                self.flux = flux
                self.destroyed = False

            def destroy(self):
                self.destroyed = True

        class Evaluator:
            @staticmethod
            def evaluate(vector, _beta):
                return vector.flux

        candidates = [
            Candidate(0.5 + 0.01j, +1.0),
            Candidate(-0.5 - 0.01j, -1.0),
            Candidate(0.0 + 0.4j, 0.0),
            Candidate(0.0 - 0.4j, 0.0),
            Candidate(0.7 + 0.02j, +0.5),
        ]
        selected, report = select_passive_direction_modes(
            candidates,
            desired_direction="forward",
            requested_modes=2,
            poynting_evaluator=Evaluator(),
        )
        try:
            self.assertEqual(selected, [candidates[0], candidates[2]])
            self.assertEqual(report.candidate_modes, 5)
            self.assertEqual(report.selected_modes, 2)
            self.assertEqual(report.direction_counts["forward"], 3)
            self.assertEqual(report.direction_counts["backward"], 2)
            self.assertEqual(report.selected_candidate_indices, (0, 2))
            self.assertFalse(candidates[0].destroyed)
            self.assertFalse(candidates[2].destroyed)
            self.assertTrue(candidates[1].destroyed)
            self.assertTrue(candidates[3].destroyed)
            self.assertTrue(candidates[4].destroyed)
        finally:
            for mode in selected:
                mode.destroy()

    def test_numerical_infinity_roots_are_rejected_before_flux_classification(self):
        class Candidate:
            def __init__(self, beta: complex, flux: float):
                self.beta = beta
                self.right_full = self
                self.flux = flux
                self.destroyed = False

            def destroy(self):
                self.destroyed = True

        class Evaluator:
            @staticmethod
            def evaluate(vector, _beta):
                return vector.flux

        finite = Candidate(0.1 + 0.9j, 0.0)
        numerical_infinity = Candidate(1.1e7 + 2.0e6j, 1.0e30)
        selected, report = select_passive_direction_modes(
            [finite, numerical_infinity],
            desired_direction="forward",
            requested_modes=2,
            poynting_evaluator=Evaluator(),
            maximum_abs_beta=2.0e3,
        )
        try:
            self.assertEqual(selected, [finite])
            self.assertEqual(report.finite_candidate_count, 1)
            self.assertEqual(report.numerically_infinite_candidate_count, 1)
            self.assertEqual(
                report.first_rejected_numerical_infinity_beta,
                numerical_infinity.beta,
            )
            self.assertTrue(numerical_infinity.destroyed)
        finally:
            for mode in selected:
                mode.destroy()

    def test_air_modes_use_poynting_and_adjoint_qep_biorthogonality(self):
        cfg = target_stage4_config(degree=2, h_nm=10.0)
        cross_section = build_matching_cross_section(cfg, "air")
        spaces = build_cross_section_spaces(cross_section, transverse_degree=2)
        operators = assemble_quadratic_beta_operators(cfg, cross_section, spaces)
        target = analytic_homogeneous_beta(cfg, cfg.n_air)
        positive_right, _ = solve_quadratic_beta_modes(
            operators, target=target, requested_modes=2
        )
        negative_right = None
        if MPI.COMM_WORLD.size == 1:
            negative_right, _ = solve_quadratic_beta_modes(
                operators, target=-target, requested_modes=2
            )
        positive = build_biorthogonal_mode_basis(
            cfg,
            cross_section,
            spaces,
            operators,
            positive_right,
            adjoint_target=np.conj(target),
            requested_left_modes=2,
        )
        negative = None
        if negative_right is not None:
            negative = build_biorthogonal_mode_basis(
                cfg,
                cross_section,
                spaces,
                operators,
                negative_right,
                adjoint_target=-np.conj(target),
                requested_left_modes=2,
            )
        try:
            self.assertEqual(len(positive.modes), 2)
            self.assertFalse(positive.full_vector_gathered)
            self.assertLess(positive.max_identity_error, 1.0e-8)
            self.assertLess(positive.max_entry_identity_error, 1.0e-8)
            self.assertTrue(any(len(group.indices) == 2 for group in positive.groups))
            self.assertTrue(
                all(
                    len(group.indices) == 1
                    or group.normalization_method
                    == "near_degenerate_block_inverse"
                    for group in positive.groups
                )
            )
            for mode in positive.modes:
                self.assertEqual(mode.direction, "forward")
                self.assertEqual(mode.classification_basis, "poynting_flux")
                self.assertTrue(mode.passive_branch_valid)
                self.assertAlmostEqual(
                    mode.poynting_z_after_normalization, 1.0, places=9
                )
                self.assertLess(mode.left_polynomial_relative_residual, 1.0e-8)
                self.assertLess(abs(mode.qprime_overlap_after - 1.0), 1.0e-8)
                self.assertFalse(mode.left_ownership.gathered_to_root)
                self.assertEqual(
                    MPI.COMM_WORLD.allreduce(
                        mode.left_ownership.reduced_local_size, op=MPI.SUM
                    ),
                    operators.reduced_shape[0],
                )
                self.assertEqual(
                    MPI.COMM_WORLD.allreduce(
                        mode.left_ownership.full_local_size, op=MPI.SUM
                    ),
                    operators.full_shape[0],
                )
            if negative is not None:
                self.assertEqual(len(negative.modes), 2)
                self.assertLess(negative.max_identity_error, 1.0e-8)
                self.assertLess(negative.max_entry_identity_error, 1.0e-8)
                for mode in negative.modes:
                    self.assertEqual(mode.direction, "backward")
                    self.assertTrue(mode.passive_branch_valid)
                    self.assertAlmostEqual(
                        mode.poynting_z_after_normalization, -1.0, places=9
                    )
                    self.assertLess(mode.left_polynomial_relative_residual, 1.0e-8)

                pairs = pair_reciprocal_mode_bases(operators, positive, negative)
                self.assertEqual(len(pairs), 2)
                for pair in pairs:
                    self.assertLess(pair.relative_beta_error, 1.0e-8)
                    self.assertGreater(pair.electric_mass_overlap, 0.5)
                    self.assertTrue(pair.opposite_direction)
                    self.assertTrue(pair.passive_branches_valid)

                propagation = build_two_sided_propagation(
                    [*positive.modes, *negative.modes], 100.0
                )
                propagation_report = diagnose_reciprocity_and_passivity(propagation)
                self.assertTrue(propagation.passivity_valid)
                self.assertTrue(propagation_report.reciprocity_valid)
                self.assertLessEqual(propagation.max_factor_magnitude, 1.0)
                self.assertEqual(propagation.stored_complex_scalars, 4)
        finally:
            positive.destroy()
            if negative is not None:
                negative.destroy()
            operators.destroy()

    @unittest.skipIf(
        MPI.COMM_WORLD.size > 1,
        "analytic reciprocal construction uses a serial small-space contract",
    )
    def test_scalar_stage4_reciprocal_basis_recomputes_all_gates(self):
        cfg = target_stage4_config(degree=1, h_nm=100.0)
        cross_section = build_matching_cross_section(cfg, "stage4_xy")
        spaces = build_cross_section_spaces(
            cross_section, transverse_degree=1
        )
        operators = assemble_quadratic_beta_operators(
            cfg, cross_section, spaces
        )
        target = analytic_homogeneous_beta(cfg, cfg.n_air)
        right_modes, _ = solve_quadratic_beta_modes(
            operators, target=target, requested_modes=2
        )
        positive = build_biorthogonal_mode_basis(
            cfg,
            cross_section,
            spaces,
            operators,
            right_modes,
            adjoint_target=np.conj(target),
            requested_left_modes=2,
            task036_scalar_stage4_partition_repair=True,
        )
        negative = None
        try:
            negative = build_scalar_stage4_reciprocal_negative_basis(
                cfg, cross_section, spaces, operators, positive
            )
            self.assertEqual(
                negative.basis_origin,
                "analytic_scalar_stage4_reciprocal",
            )
            self.assertEqual(
                negative.adjoint_solver_report.target,
                -positive.adjoint_solver_report.target,
            )
            self.assertFalse(
                negative.basis_construction_audit[
                    "negative_independent_qep_solve_performed"
                ]
            )
            self.assertTrue(
                negative.basis_construction_audit[
                    "all_residual_flux_qprime_recomputed"
                ]
            )
            self.assertLessEqual(negative.max_identity_error, 1.0e-6)
            self.assertTrue(negative.near_degenerate_partition_audit["pass"])
            self.assertLessEqual(
                max(
                    negative.basis_construction_audit[
                        "right_constraint_reconstruction_relative_errors"
                    ]
                ),
                1.0e-12,
            )
            self.assertLessEqual(
                max(
                    negative.basis_construction_audit[
                        "left_constraint_reconstruction_relative_errors"
                    ]
                ),
                1.0e-12,
            )
            for plus, minus in zip(positive.modes, negative.modes):
                self.assertEqual(minus.beta, -plus.beta)
                self.assertEqual(minus.direction, "backward")
                self.assertTrue(minus.passive_branch_valid)
                self.assertLess(
                    minus.right.polynomial_relative_residual, 1.0e-8
                )
                self.assertLess(
                    minus.left_polynomial_relative_residual, 1.0e-8
                )
                self.assertLess(abs(minus.qprime_overlap_after - 1.0), 1.0e-6)
        finally:
            if negative is not None:
                negative.destroy()
            positive.destroy()
            operators.destroy()

    @unittest.skipIf(
        MPI.COMM_WORLD.size > 1,
        "lossy branch is covered by the formal MPI benchmark",
    )
    def test_lossy_modes_use_complex_adjoint_branch(self):
        cfg = target_stage4_config(degree=2, h_nm=10.0)
        cross_section = build_matching_cross_section(cfg, "lossy_homogeneous")
        spaces = build_cross_section_spaces(cross_section, transverse_degree=2)
        operators = assemble_quadratic_beta_operators(cfg, cross_section, spaces)
        target = analytic_homogeneous_beta(cfg, cfg.n_grating)
        right_modes, _ = solve_quadratic_beta_modes(
            operators, target=target, requested_modes=2
        )
        basis = build_biorthogonal_mode_basis(
            cfg,
            cross_section,
            spaces,
            operators,
            right_modes,
            adjoint_target=np.conj(target),
            requested_left_modes=2,
        )
        try:
            self.assertLess(basis.max_identity_error, 1.0e-7)
            self.assertLess(basis.max_entry_identity_error, 1.0e-7)
            for mode in basis.modes:
                self.assertGreater(mode.beta.imag, 0.0)
                self.assertEqual(mode.kind, "lossy_propagating")
                self.assertEqual(mode.direction, "forward")
                self.assertTrue(mode.passive_branch_valid)
                self.assertAlmostEqual(
                    mode.poynting_z_after_normalization, 1.0, places=8
                )
                self.assertLess(mode.left_polynomial_relative_residual, 1.0e-8)
        finally:
            basis.destroy()
            operators.destroy()

    @unittest.skipIf(
        MPI.COMM_WORLD.size > 1,
        "adjacent-parameter tracking is a serial small-dense contract",
    )
    def test_overlap_tracking_handles_angle_change_and_mode_count_change(self):
        _, _, _, operators_previous, _, previous = self._build_air_basis(
            theta_deg=80.0, requested_modes=2
        )
        _, _, _, operators_current, _, current = self._build_air_basis(
            theta_deg=79.8, requested_modes=3
        )
        try:
            report = track_mode_bases(operators_current, previous, current)
            self.assertEqual(len(report.matches), 2)
            self.assertEqual(report.unmatched_previous, ())
            self.assertGreaterEqual(len(report.unmatched_current), 1)
            self.assertTrue(all(match.overlap > 0.5 for match in report.matches))
            self.assertTrue(report.subspaces)
            self.assertLess(report.subspaces[0].max_principal_angle_rad, 0.2)
        finally:
            previous.destroy()
            current.destroy()
            operators_previous.destroy()
            operators_current.destroy()


if __name__ == "__main__":
    unittest.main()
