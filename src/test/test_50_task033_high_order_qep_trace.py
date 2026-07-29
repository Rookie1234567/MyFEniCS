from __future__ import annotations

import math
import unittest

import numpy as np
from petsc4py import PETSc

from src.common.config_3d import target_stage4_config
from src.coupling.modal_trace_projection import ModalTraceProjection
from src.modes.cross_section_spaces import (
    build_cross_section_spaces,
    build_matching_cross_section,
)
from src.modes.mode_classification import build_biorthogonal_mode_basis
from src.modes.quadratic_beta_eigenproblem import (
    analytic_homogeneous_beta,
    assemble_quadratic_beta_operators,
    qep_quadrature_degree,
    solve_quadratic_beta_modes,
)


def _matrix_relative_difference(first: PETSc.Mat, second: PETSc.Mat) -> float:
    difference = first.copy()
    try:
        difference.axpy(
            -1.0,
            second,
            structure=PETSc.Mat.Structure.SAME_NONZERO_PATTERN,
        )
        return float(
            difference.norm(PETSc.NormType.FROBENIUS)
            / max(first.norm(PETSc.NormType.FROBENIUS), 1.0e-30)
        )
    finally:
        difference.destroy()


class Task033HighOrderQEPTraceTests(unittest.TestCase):
    def test_p3_air_beta_recovers_under_h_refinement(self) -> None:
        errors: list[float] = []
        betas: list[complex] = []
        for h_nm in (10.0, 5.0, 3.0):
            cfg = target_stage4_config(degree=3, h_nm=h_nm)
            cross_section = build_matching_cross_section(cfg, "air")
            spaces = build_cross_section_spaces(
                cross_section, transverse_degree=3
            )
            operators = assemble_quadratic_beta_operators(
                cfg, cross_section, spaces
            )
            target = analytic_homogeneous_beta(cfg, cfg.n_air)
            modes, _report = solve_quadratic_beta_modes(
                operators, target=target, requested_modes=8
            )
            try:
                selected = min(modes, key=lambda mode: abs(mode.beta - target))
                betas.append(complex(selected.beta))
                errors.append(float(abs(selected.beta - target) / abs(target)))
                self.assertLess(selected.polynomial_relative_residual, 1.0e-10)
            finally:
                for mode in modes:
                    mode.destroy()
                operators.destroy()
        self.assertTrue(
            all(later < earlier for earlier, later in zip(errors, errors[1:])),
            {"errors": errors, "betas": betas},
        )

    def test_air_p1_p4_beta_and_raised_quadrature(self) -> None:
        errors: list[float] = []
        spectra: list[tuple[int, complex, tuple[complex, ...]]] = []
        for degree in (1, 2, 3, 4):
            cfg = target_stage4_config(degree=degree, h_nm=5.0)
            cross_section = build_matching_cross_section(cfg, "air")
            spaces = build_cross_section_spaces(
                cross_section, transverse_degree=degree
            )
            operators = assemble_quadratic_beta_operators(
                cfg, cross_section, spaces
            )
            target = analytic_homogeneous_beta(cfg, cfg.n_air)
            modes, report = solve_quadratic_beta_modes(
                operators, target=target, requested_modes=8
            )
            try:
                self.assertGreater(report.converged_modes, 0)
                spectra.append(
                    (degree, target, tuple(complex(mode.beta) for mode in modes))
                )
                selected = min(modes, key=lambda mode: abs(mode.beta - target))
                error = float(abs(selected.beta - target) / abs(target))
                errors.append(error)
                self.assertTrue(math.isfinite(error))
                self.assertLess(selected.polynomial_relative_residual, 1.0e-10)
                self.assertEqual(operators.field_degree, degree)
                self.assertEqual(operators.geometry_degree, 1)
                self.assertEqual(operators.coefficient_degree, 0)
                self.assertEqual(
                    operators.quadrature_degree,
                    qep_quadrature_degree(
                        field_degree=degree,
                        geometry_degree=1,
                        coefficient_degree=0,
                    ),
                )
                self.assertLess(operators.constraints.max_probe_residual, 5.0e-12)
                self.assertEqual(
                    operators.constraints.communication_scope,
                    "distributed_hash_periodic_boundary_entities_only",
                )

                if degree == 4:
                    elevated = assemble_quadratic_beta_operators(
                        cfg,
                        cross_section,
                        spaces,
                        quadrature_degree=operators.quadrature_degree + 2,
                    )
                    try:
                        for first, second in (
                            (operators.K0, elevated.K0),
                            (operators.K1, elevated.K1),
                            (operators.K2, elevated.K2),
                            (operators.electric_mass, elevated.electric_mass),
                        ):
                            self.assertLess(
                                _matrix_relative_difference(first, second),
                                2.0e-12,
                            )
                    finally:
                        elevated.destroy()
            finally:
                for mode in modes:
                    mode.destroy()
                operators.destroy()

        self.assertTrue(
            all(later < earlier for earlier, later in zip(errors, errors[1:])),
            {"errors": errors, "spectra": spectra},
        )

    def test_p1_p4_left_right_and_trace_round_trip(self) -> None:
        for degree in (1, 2, 3, 4):
            with self.subTest(degree=degree):
                cfg = target_stage4_config(degree=degree, h_nm=10.0)
                cross_section = build_matching_cross_section(cfg, "air")
                spaces = build_cross_section_spaces(
                    cross_section, transverse_degree=degree
                )
                operators = assemble_quadratic_beta_operators(
                    cfg, cross_section, spaces
                )
                target = analytic_homogeneous_beta(cfg, cfg.n_air)
                right_modes, _report = solve_quadratic_beta_modes(
                    operators, target=target, requested_modes=2
                )
                basis = None
                projection = None
                try:
                    basis = build_biorthogonal_mode_basis(
                        cfg,
                        cross_section,
                        spaces,
                        operators,
                        right_modes,
                        adjoint_target=np.conj(target),
                        requested_left_modes=2,
                    )
                    projection = ModalTraceProjection(spaces, basis)
                    round_trip = projection.round_trip(
                        np.asarray([0.7 + 0.2j, -0.3 + 0.4j])
                    )
                    self.assertLess(
                        basis.max_entry_identity_error,
                        1.0e-6,
                    )
                    self.assertGreaterEqual(
                        basis.max_identity_error,
                        basis.max_entry_identity_error,
                    )
                    self.assertTrue(math.isfinite(basis.max_identity_error))
                    self.assertTrue(
                        all(
                            len(group.indices) == 1
                            or group.normalization_method
                            == "near_degenerate_block_inverse"
                            for group in basis.groups
                        )
                    )
                    self.assertLess(
                        max(
                            mode.left_polynomial_relative_residual
                            for mode in basis.modes
                        ),
                        1.0e-8,
                    )
                    self.assertLess(
                        max(
                            mode.right.polynomial_relative_residual
                            for mode in basis.modes
                        ),
                        1.0e-10,
                    )
                    self.assertLess(round_trip.coefficient_relative_error, 1.0e-9)
                    self.assertLess(round_trip.trace_relative_residual, 1.0e-9)
                    self.assertFalse(projection.full_vector_gathered)
                    self.assertFalse(projection.dense_interface_operator_formed)
                finally:
                    if projection is not None:
                        projection.destroy()
                    if basis is not None:
                        basis.destroy()
                    else:
                        for mode in right_modes:
                            mode.destroy()
                    operators.destroy()

    def test_p4_h2p5_near_blocks_preserve_left_residual_gate(self) -> None:
        for material_kind in ("lossy_homogeneous", "stage4_xy"):
            with self.subTest(material_kind=material_kind):
                cfg = target_stage4_config(degree=4, h_nm=2.5)
                cross_section = build_matching_cross_section(
                    cfg, material_kind
                )
                spaces = build_cross_section_spaces(
                    cross_section, transverse_degree=4
                )
                operators = assemble_quadratic_beta_operators(
                    cfg, cross_section, spaces
                )
                target_index = (
                    cfg.n_grating
                    if material_kind == "lossy_homogeneous"
                    else cfg.n_air
                )
                target = analytic_homogeneous_beta(cfg, target_index)
                right_modes, _report = solve_quadratic_beta_modes(
                    operators,
                    target=target,
                    requested_modes=8,
                )
                basis = None
                try:
                    basis = build_biorthogonal_mode_basis(
                        cfg,
                        cross_section,
                        spaces,
                        operators,
                        right_modes,
                        adjoint_target=np.conj(target),
                        requested_left_modes=16,
                    )
                    near_groups = [
                        group
                        for group in basis.groups
                        if len(group.indices) > 1
                    ]
                    self.assertTrue(near_groups)
                    self.assertTrue(
                        all(
                            group.normalization_method
                            == "near_degenerate_block_inverse"
                            for group in near_groups
                        )
                    )
                    self.assertLess(
                        max(basis.left_pair_relative_errors), 1.0e-7
                    )
                    self.assertLess(
                        basis.max_entry_identity_error, 1.0e-6
                    )
                    self.assertLess(
                        max(
                            mode.left_polynomial_relative_residual
                            for mode in basis.modes
                        ),
                        1.0e-8,
                    )
                    if material_kind == "stage4_xy":
                        self.assertGreater(
                            max(
                                group.max_relative_beta_spread
                                for group in near_groups
                            ),
                            1.0e-8,
                        )
                finally:
                    if basis is not None:
                        basis.destroy()
                    else:
                        for mode in right_modes:
                            mode.destroy()
                    operators.destroy()


if __name__ == "__main__":
    unittest.main()
