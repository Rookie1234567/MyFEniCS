from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from dolfinx import fem
from mpi4py import MPI
import numpy as np

from benchmarks.run_task036_one_cell_discrete_bloch import (
    _authority_config,
    _one_cell_config,
)
from benchmarks.task036_transfer_capacity import joint_cauchy_pairing
from benchmarks.run_task036_transfer_optimal_port_capacity import (
    _gc_projected_orthonormalize_block,
    SparsePortTransfer,
)
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.common_3d_forms import _build_variational_forms
from src.solvers.common_3d_solve import _create_nedelec_space
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.hybrid_port_metric import (
    EndpointTraceMassSelection,
    build_endpoint_trace_mass_actions,
)
from src.solvers.one_cell_discrete_bloch import identify_endpoint_active_rows


class Task036TransferCapacityDiscreteTests(unittest.TestCase):
    def test_sparse_port_transfer_bulk_primal_dual_matches_columns(self) -> None:
        transfer = SparsePortTransfer(
            source_size=4,
            target_size=3,
            rows={
                0: (
                    np.asarray([0, 2], dtype=np.int64),
                    np.asarray([1.0 + 0.2j, -0.3 + 0.1j]),
                ),
                1: (
                    np.asarray([1, 3], dtype=np.int64),
                    np.asarray([0.4 - 0.2j, 0.7 + 0.05j]),
                ),
                2: (
                    np.asarray([0, 1, 3], dtype=np.int64),
                    np.asarray([-0.2 + 0.3j, 0.6 - 0.1j, 0.15 + 0.4j]),
                ),
            },
        )
        source = np.asarray(
            [
                [0.2 + 0.1j, -0.4 + 0.3j, 0.7 - 0.2j],
                [1.0 - 0.2j, 0.5 + 0.4j, -0.1 + 0.6j],
                [-0.3 + 0.8j, 0.9 - 0.5j, 0.2 + 0.7j],
                [0.6 + 0.2j, -0.8 + 0.1j, 0.3 - 0.4j],
            ],
            dtype=np.complex128,
        )
        target_dual = np.asarray(
            [
                [0.3 - 0.2j, 0.8 + 0.1j, -0.5 + 0.4j],
                [-0.7 + 0.6j, 0.2 - 0.3j, 0.9 + 0.05j],
                [0.4 + 0.7j, -0.1 + 0.8j, 0.6 - 0.2j],
            ],
            dtype=np.complex128,
        )
        primal_bulk = transfer.primal(source)
        dual_bulk = transfer.dual(target_dual)
        primal_columns = np.column_stack(
            [transfer.primal(source[:, column]) for column in range(source.shape[1])]
        )
        dual_columns = np.column_stack(
            [
                transfer.dual(target_dual[:, column])
                for column in range(target_dual.shape[1])
            ]
        )
        np.testing.assert_allclose(primal_bulk, primal_columns, atol=1.0e-13)
        np.testing.assert_allclose(dual_bulk, dual_columns, atol=1.0e-13)
        np.testing.assert_allclose(
            np.vdot(target_dual, primal_bulk),
            np.vdot(dual_bulk, source),
            atol=1.0e-13,
        )

    def test_projected_metric_qr_preserves_complement_and_existing(self) -> None:
        metric = np.diag(np.arange(1.0, 7.0))

        def gc_action(values: np.ndarray) -> np.ndarray:
            return metric @ values

        existing = np.zeros((6, 1), dtype=np.complex128)
        existing[0, 0] = 1.0
        candidate = np.array(
            [
                [0.25 + 0.1j, -0.5 + 0.2j],
                [1.0 + 0.3j, 0.2 - 0.4j],
                [0.1 - 0.2j, 0.8 + 0.1j],
                [0.4 + 0.5j, -0.3 + 0.6j],
                [0.7 - 0.1j, 0.5 + 0.2j],
                [-0.2 + 0.4j, 0.9 - 0.3j],
            ]
        )

        def projector(values: np.ndarray) -> np.ndarray:
            return values - existing @ (
                existing.conj().T @ gc_action(values)
            )

        block = _gc_projected_orthonormalize_block(
            candidate, existing, gc_action, projector
        )
        np.testing.assert_allclose(projector(block), block, atol=1.0e-12)
        np.testing.assert_allclose(
            block.conj().T @ gc_action(block),
            np.eye(block.shape[1]),
            atol=1.0e-12,
        )
        np.testing.assert_allclose(
            existing.conj().T @ gc_action(block),
            np.zeros((1, block.shape[1])),
            atol=1.0e-12,
        )

    def test_joint_cauchy_pairing_is_hpd_and_unit_invariant(self) -> None:
        rng = np.random.default_rng(36061)
        seed = rng.standard_normal((4, 4)) + 1j * rng.standard_normal((4, 4))
        mass_nm = seed.conj().T @ seed + 0.8 * np.eye(4)
        electric = rng.standard_normal(4) + 1j * rng.standard_normal(4)
        traction = rng.standard_normal(4) + 1j * rng.standard_normal(4)
        other_electric = rng.standard_normal(4) + 1j * rng.standard_normal(4)
        other_traction = rng.standard_normal(4) + 1j * rng.standard_normal(4)
        k0_nm = 0.46542113386515455
        area_nm = 1250.0
        reference = 1.0 + 0.0j

        forward = joint_cauchy_pairing(
            electric,
            traction,
            other_electric,
            other_traction,
            mass_nm,
            k0=k0_nm,
            area=area_nm,
            electric_reference=reference,
        )
        reverse = joint_cauchy_pairing(
            other_electric,
            other_traction,
            electric,
            traction,
            mass_nm,
            k0=k0_nm,
            area=area_nm,
            electric_reference=reference,
        )
        self.assertLess(abs(forward - reverse.conjugate()), 1.0e-12)
        self.assertGreater(
            joint_cauchy_pairing(
                electric,
                traction,
                electric,
                traction,
                mass_nm,
                k0=k0_nm,
                area=area_nm,
                electric_reference=reference,
            ).real,
            0.0,
        )

        length_scale = 1.0e-9
        metric_nm = joint_cauchy_pairing(
            electric,
            traction,
            other_electric,
            other_traction,
            mass_nm,
            k0=k0_nm,
            area=area_nm,
            electric_reference=reference,
        )
        metric_m = joint_cauchy_pairing(
            length_scale * electric,
            traction,
            length_scale * other_electric,
            other_traction,
            mass_nm,
            k0=k0_nm / length_scale,
            area=length_scale**2 * area_nm,
            electric_reference=reference,
        )
        np.testing.assert_allclose(metric_m, metric_nm, rtol=1.0e-12, atol=1.0e-12)
        rho = -0.7 + 1.3j
        rescaled = joint_cauchy_pairing(
            rho * electric,
            rho * traction,
            rho * other_electric,
            rho * other_traction,
            mass_nm,
            k0=k0_nm,
            area=area_nm,
            electric_reference=rho * reference,
        )
        np.testing.assert_allclose(rescaled, metric_nm, rtol=1.0e-12, atol=1.0e-12)

    @unittest.skipUnless(
        MPI.COMM_WORLD.size == 1,
        "Task036 frozen face-mass qualification is plain serial",
    )
    def test_frozen_p5_one_cell_face_mass_is_sparse_hpd(self) -> None:
        cfg = _one_cell_config(_authority_config())
        with tempfile.TemporaryDirectory(prefix="task036-t0b-face-mass-") as tmp:
            mesh_data = build_airbox_mesh_3d(cfg, Path(tmp) / "mesh")
            V = _create_nedelec_space(mesh_data.mesh, cfg)
            floquet = build_double_floquet_mpc(V, mesh_data, cfg)
            volume_form, _ = _build_variational_forms(
                mesh_data.mesh,
                mesh_data,
                cfg,
                V,
                field_formulation="total_field_dtn_port",
            )
            condensed = build_unconstrained_assembly_time_condensation(
                fem.form(volume_form),
                V,
                mesh_data.cell_tags,
                mpc=floquet.mpc,
            )
            try:
                endpoints = identify_endpoint_active_rows(
                    V,
                    condensed,
                    left_facets=mesh_data.facet_tags.find(cfg.tags.z_min),
                    right_facets=mesh_data.facet_tags.find(cfg.tags.z_max),
                )
                self.assertEqual(len(endpoints.left_original), 1250)
                self.assertEqual(len(endpoints.right_original), 1250)
                self.assertEqual(len(endpoints.left_active), 1200)
                self.assertEqual(len(endpoints.right_active), 1200)
                actions = build_endpoint_trace_mass_actions(
                    V,
                    mesh_data,
                    condensed.trace_constraints,
                    (
                        EndpointTraceMassSelection(
                            cfg.tags.z_min,
                            endpoints.left_original,
                            endpoints.left_active,
                        ),
                        EndpointTraceMassSelection(
                            cfg.tags.z_max,
                            endpoints.right_original,
                            endpoints.right_active,
                        ),
                    ),
                )
                try:
                    for action in actions:
                        self.assertEqual(action.shape, (1200, 1200))
                        self.assertLessEqual(
                            action.hermitian_relative_defect, 1.0e-12
                        )
                        self.assertLessEqual(
                            action.constraint_action_relative_error, 1.0e-12
                        )
                        self.assertLessEqual(
                            action.solve_relative_residual, 1.0e-11
                        )
                finally:
                    for action in actions:
                        action.destroy()
            finally:
                condensed.destroy()


if __name__ == "__main__":
    unittest.main()
