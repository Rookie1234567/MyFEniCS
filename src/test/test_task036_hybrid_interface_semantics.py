from __future__ import annotations

from types import SimpleNamespace
from unittest import mock
import unittest

import numpy as np

from benchmarks.task032_final_gates import (
    _all_formal_true,
    _exact_traction_gate,
)
from src.postprocessing import hybrid_field_reconstruction as reconstruction
from src.postprocessing.hybrid_field_reconstruction import (
    ModalFieldReconstructor,
    ModalPlaneSamples,
    _validated_traction_beta_pair,
    interface_field_continuity,
)
from src.solvers import hybrid_static_field_recovery as static_recovery
from src.solvers.hybrid_fem_modal_augmented_direct import (
    _fe_traction_equilibrium_diagnostics,
)
from src.solvers.hybrid_status import hybrid_p_disposition


class Task036HybridInterfaceSemanticsTests(unittest.TestCase):
    def test_current_exact_traction_gate_requires_both_finite_sides(self) -> None:
        legacy = {
            "schema_version": 1,
            "metadata": {"commit_sha": "735774473e54415ab5393f2d2cbc9c8d7d2a24e6"},
        }
        self.assertEqual(
            _exact_traction_gate(legacy, [None, None], 1.0e-8),
            (False, "missing_exact_variational_conormal_dual"),
        )
        self.assertEqual(
            _exact_traction_gate(
                legacy,
                [None, None],
                1.0e-8,
                allow_frozen_legacy_record=True,
            ),
            (True, "legacy_sha_bound_record_predating_exact_dual"),
        )
        for values in (
            [1.0e-9, None],
            [None, 1.0e-9],
            [1.0e-9],
        ):
            self.assertFalse(_exact_traction_gate({}, values, 1.0e-8)[0])
        self.assertTrue(_exact_traction_gate({}, [1.0e-9, 2.0e-9], 1.0e-8)[0])
        self.assertFalse(_exact_traction_gate({}, [1.0e-9, np.nan], 1.0e-8)[0])

    def test_sampled_diagnostic_cannot_qualify_formal_gate(self) -> None:
        self.assertTrue(
            _all_formal_true(
                {
                    "assembled_exact_dual": True,
                    "diagnostic_sampled_proxy": False,
                }
            )
        )
        self.assertFalse(
            _all_formal_true(
                {
                    "assembled_exact_dual": False,
                    "diagnostic_sampled_proxy": True,
                }
            )
        )

    def test_traction_beta_pair_shape_and_finiteness_fail_closed(self) -> None:
        valid = np.asarray([1.0 + 2.0j, 3.0 + 4.0j])
        positive, negative = _validated_traction_beta_pair(valid, -valid, 2)
        np.testing.assert_array_equal(positive, valid)
        np.testing.assert_array_equal(negative, -valid)
        for positive_values, negative_values in (
            (None, valid),
            (valid, None),
            (None, None),
            (valid[:1], valid),
            (valid, np.asarray([np.inf, 1.0])),
        ):
            with self.subTest(
                positive=positive_values,
                negative=negative_values,
            ):
                with self.assertRaises(ValueError):
                    _validated_traction_beta_pair(
                        positive_values,
                        negative_values,
                        2,
                    )

    def test_e_uses_propagation_beta_and_h_exposes_traction_beta(self) -> None:
        reconstructor = object.__new__(ModalFieldReconstructor)
        reconstructor.positive = SimpleNamespace(modes=(object(),))
        reconstructor.negative = SimpleNamespace(modes=(object(),))
        reconstructor.bottom_z_nm = 0.0
        reconstructor.top_z_nm = 10.0
        reconstructor._positive_propagation_beta = np.asarray([0.2 + 0.0j])
        reconstructor._negative_propagation_beta = np.asarray([-0.3 + 0.0j])
        reconstructor._positive_traction_beta = np.asarray([7.0 + 0.1j])
        reconstructor._negative_traction_beta = np.asarray([-8.0 + 0.2j])

        modal = np.asarray([2.0 + 0.0j, 3.0 + 0.0j])
        coefficients = reconstructor.coefficients_at_z(modal, 4.0)
        expected = np.asarray(
            [
                2.0 * np.exp(1j * 0.2 * 4.0),
                3.0 * np.exp(1j * -0.3 * (4.0 - 10.0)),
            ]
        )
        np.testing.assert_allclose(coefficients, expected)
        np.testing.assert_array_equal(
            reconstructor._magnetic_traction_betas(),
            np.asarray([7.0 + 0.1j, -8.0 + 0.2j]),
        )

    def test_static_reassembly_passes_selected_beta_override(self) -> None:
        system = SimpleNamespace(
            side="bottom",
            local_mesh=SimpleNamespace(local_interface_outward_normal_sign=-1),
        )
        coupling = SimpleNamespace(
            mode_count_per_direction=1,
            propagation=SimpleNamespace(
                forward=SimpleNamespace(factors=np.asarray([0.4])),
                backward=SimpleNamespace(factors=np.asarray([0.5])),
            ),
            positive_basis=SimpleNamespace(modes=("positive-mode",)),
            negative_basis=SimpleNamespace(modes=("negative-mode",)),
            positive_traction_beta_per_nm=(7.0 + 0.25j,),
            negative_traction_beta_per_nm=(-8.0 + 0.5j,),
            spaces=object(),
        )
        evaluator = mock.Mock()
        evaluator.evaluate.side_effect = ("positive-traction", "negative-traction")
        vectors = (mock.Mock(), mock.Mock())
        surface = mock.Mock()
        surface.assemble_full_vector.side_effect = (
            (vectors[0], 2),
            (vectors[1], 3),
        )
        full_rhs = mock.Mock()
        with (
            mock.patch.object(
                static_recovery,
                "_ReusableModeTractionEvaluator",
                return_value=evaluator,
            ),
            mock.patch.object(
                static_recovery,
                "_ReusableInterfaceSurfaceLoad",
                return_value=surface,
            ),
        ):
            audit = static_recovery._add_internal_tractions(
                system,
                coupling,
                np.asarray([2.0, 3.0], dtype=np.complex128),
                full_rhs,
            )

        self.assertEqual(
            [
                call.kwargs["beta_override"]
                for call in evaluator.evaluate.call_args_list
            ],
            [7.0 + 0.25j, -8.0 + 0.5j],
        )
        self.assertEqual(
            audit["traction_beta_source"],
            "coupling_selected_traction_beta_per_nm",
        )

    def test_sampled_interface_quantity_is_diagnostic_only(self) -> None:
        systems = (
            SimpleNamespace(
                local_mesh=SimpleNamespace(
                    interface_z_nm=10.0,
                    mesh_data=object(),
                )
            ),
            SimpleNamespace(
                local_mesh=SimpleNamespace(
                    interface_z_nm=110.0,
                    mesh_data=object(),
                )
            ),
        )
        samples = ModalPlaneSamples(
            x_nm=np.asarray([1.0]),
            y_nm=np.asarray([2.0]),
            z_nm=np.asarray([10.0, 110.0]),
            electric_V_per_m=np.zeros((2, 1, 1, 3), dtype=np.complex128),
            magnetic_A_per_m=np.zeros((2, 1, 1, 3), dtype=np.complex128),
        )
        with (
            mock.patch.object(
                reconstruction,
                "assign_local_total_electric_field",
                return_value=object(),
            ),
            mock.patch.object(
                reconstruction,
                "local_magnetic_field_A_per_m",
                return_value=object(),
            ),
            mock.patch.object(
                reconstruction,
                "_sample_distributed_function",
                return_value=np.zeros((1, 3), dtype=np.complex128),
            ),
        ):
            report = interface_field_continuity(
                SimpleNamespace(electric_field_scale_V_per_m=1.0),
                systems[0],
                systems[1],
                object(),
                object(),
                samples,
            )
        for side in ("bottom", "top"):
            self.assertNotIn("magnetic_tangential", report[side])
            proxy = report[side]["traction_density_l2_proxy"]
            self.assertTrue(proxy["diagnostic_only"])
            self.assertFalse(proxy["formal_gate"])

    def test_exact_dual_diagnostics_expose_balance_scale_components(self) -> None:
        residual = mock.Mock()
        residual.norm.side_effect = (5.0, 0.1)
        rhs = mock.Mock()
        rhs.norm.return_value = 4.0
        positive = mock.Mock()
        positive.norm.return_value = 3.0
        negative = mock.Mock()
        negative.norm.return_value = 2.0
        local_system = SimpleNamespace(
            A=SimpleNamespace(
                createVecLeft=mock.Mock(return_value=residual),
                mult=mock.Mock(),
            ),
            b=rhs,
        )
        with mock.patch(
            "src.solvers.hybrid_fem_modal_augmented_direct._modal_action",
            side_effect=(positive, negative),
        ):
            report = _fe_traction_equilibrium_diagnostics(
                local_system,
                mock.Mock(),
                mock.Mock(),
                np.asarray([1.0]),
                mock.Mock(),
                np.asarray([1.0]),
            )
        self.assertEqual(
            report["method"],
            "exact_variational_conormal_functional_dual",
        )
        self.assertAlmostEqual(report["relative_dual"], 0.02)
        self.assertEqual(report["local_operator_action_norm"], 5.0)
        self.assertEqual(report["local_rhs_norm"], 4.0)
        self.assertEqual(report["positive_modal_traction_load_norm"], 3.0)
        self.assertEqual(report["negative_modal_traction_load_norm"], 2.0)

    def test_hybrid_p_never_qualifies_or_counts_full3d_fallback(self) -> None:
        common = {
            "full3d_physical_solution_exists": True,
            "interface_closure_pass": True,
            "diagnostic_projection_bug": False,
        }
        for rank in (False, None, True):
            report = hybrid_p_disposition(
                "p",
                modal_rank_sufficient=rank,
                **common,
            )
            self.assertFalse(report["hybrid_p_production_qualified"])
            self.assertFalse(report["full3d_fallback_is_hybrid_success"])
        self.assertEqual(
            hybrid_p_disposition(
                "p",
                modal_rank_sufficient=False,
                **common,
            )["primary_status"],
            "hybrid_modal_rank_insufficient",
        )
        self.assertEqual(
            hybrid_p_disposition(
                "p",
                modal_rank_sufficient=True,
                full3d_physical_solution_exists=True,
                interface_closure_pass=False,
                diagnostic_projection_bug=False,
            )["primary_status"],
            "hybrid_interface_closure_failed",
        )


if __name__ == "__main__":
    unittest.main()
