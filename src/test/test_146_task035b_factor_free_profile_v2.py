from __future__ import annotations

from copy import deepcopy
import unittest

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from benchmarks.run_task035b_condensed_iterative import (
    _classify_screen,
    _dry_run_plan,
    _iterative_config,
    _parse_args,
)
from src.common.config_3d import target_stage4_config
from src.solvers.condensed_iterative_profiles import (
    PHYSICS_AWARE_PROFILE,
    SUPPORTED_CONDENSED_ITERATIVE_PROFILES,
    build_diagonal_lifted_dtn_trace_basis,
    condensed_iterative_profile_contract,
)
from src.solvers.dtn_port_3d import _solve_augmented_system


def _passing_physics_aware_evidence() -> dict:
    coarse_dimension = 80
    coarse_entries = coarse_dimension * coarse_dimension
    coarse_bytes = coarse_entries * 16
    coarse_semantics = (
        "small replicated SciPy complex LU; not a global fine sparse factor"
    )
    return {
        "summary_available": True,
        "profile": PHYSICS_AWARE_PROFILE,
        "mpi_size": 8,
        "configured_programmatically": True,
        "raw_petsc_options_used_for_iterative_configuration": False,
        "assembled_reduced_operator": True,
        "matrix_free": False,
        "global_direct_factor_nnz": 0,
        "mumps_symbolic_or_numeric_created": False,
        "residual_history_final_to_initial": 1.0e-4,
        "terminal_explicit_reduced_relative_residual": 1.0e-4,
        "full_recovered_true_residual": 1.0e-10,
        "mesh_cell_type": "hexahedron",
        "h_nm": 15.0,
        "trace_degree": 5,
        "interior_degree": 6,
        "mesh_cells_resolved": [6, 2, 10],
        "num_mesh_cells": 120,
        "full3d_equivalent_dofs": 74890,
        "matrix_rows": 16880,
        "ordinary_default_changed": False,
        "ksp_converged": True,
        "typed_profile_contract": condensed_iterative_profile_contract(
            PHYSICS_AWARE_PROFILE
        ),
        "physics_aware_preconditioner": {
            "coarse_dimension": coarse_dimension,
            "coarse_rank": coarse_dimension,
            "coarse_dense_lu_active": True,
            "coarse_dense_matrix_entries": coarse_entries,
            "coarse_dense_matrix_bytes": coarse_bytes,
            "strictly_factorless_preconditioner": False,
            "strictly_factorless_reason": (
                "the small dense Galerkin coarse LU is retained"
            ),
            "fine_operator_factor_free": True,
            "global_fine_sparse_factor_nnz": 0,
            "mumps_symbolic_or_numeric_created": False,
        },
        "factor_inventory": {
            "global_direct_factor_nnz": 0,
            "global_fine_sparse_factor_nnz": 0,
            "mumps_symbolic_or_numeric_created": False,
            "coarse_dense_lu_active": True,
            "coarse_dense_matrix_entries": coarse_entries,
            "coarse_dense_matrix_bytes": coarse_bytes,
            "coarse_dense_lu_storage_semantics": coarse_semantics,
            "fine_operator_factor_free": True,
            "strictly_factorless_preconditioner": False,
        },
    }


def _passing_telemetry() -> dict:
    return {
        "observed_worker_rank_count": 8,
        "max_process_tree_swap_mb": 0.0,
        "max_worker_rank_smaps_swap_sum_mb": 0.0,
    }


def _classify_physics_evidence(evidence: dict) -> dict:
    return _classify_screen(
        evidence,
        _passing_telemetry(),
        expected_profile=PHYSICS_AWARE_PROFILE,
        expected_mpi_size=8,
        return_code=0,
        terminated_for_memory=False,
        terminated_for_timeout=False,
        telemetry_readable=True,
    )


def _block_matrix() -> tuple[PETSc.Mat, np.ndarray]:
    values = np.asarray(
        [
            [5.0, -1.0, 0.0, 0.0, 0.3 + 0.1j, 0.0],
            [-1.0, 5.0, -1.0, 0.0, 0.0, 0.2 - 0.2j],
            [0.0, -1.0, 5.0, -1.0, 0.1, 0.0],
            [0.0, 0.0, -1.0, 5.0, 0.0, 0.25j],
            [0.2 - 0.1j, 0.0, 0.1, 0.0, 1.0, 0.0],
            [0.0, 0.15 + 0.05j, 0.0, -0.2j, 0.0, 1.2],
        ],
        dtype=np.complex128,
    )
    matrix = PETSc.Mat().createAIJ(
        [6, 6],
        nnz=5,
        comm=PETSc.COMM_SELF,
    )
    for row in range(6):
        columns = np.flatnonzero(values[row]).astype(PETSc.IntType)
        matrix.setValues(row, columns, values[row, columns])
    matrix.assemble()
    return matrix, values


def _distributed_block_matrix() -> PETSc.Mat:
    _serial, values = _block_matrix()
    _serial.destroy()
    matrix = PETSc.Mat().createAIJ(
        [6, 6],
        nnz=(5, 5),
        comm=PETSc.COMM_WORLD,
    )
    row_start, row_end = matrix.getOwnershipRange()
    for row in range(row_start, row_end):
        columns = np.flatnonzero(values[row]).astype(PETSc.IntType)
        matrix.setValues(row, columns, values[row, columns])
    matrix.assemble()
    return matrix


class Task035bFactorFreeProfileV2Tests(unittest.TestCase):
    def test_screen_requires_the_complete_physics_aware_provenance(self) -> None:
        result = _classify_physics_evidence(
            _passing_physics_aware_evidence()
        )
        self.assertTrue(result["formal_iterative_screen_pass"])
        self.assertEqual(
            result["status"],
            "actual_factor_free_iterative_screen_pass",
        )

    def test_missing_or_tampered_physics_contract_fails_closed(self) -> None:
        cases = {}

        missing = _passing_physics_aware_evidence()
        missing.pop("typed_profile_contract")
        cases["missing_contract"] = (
            missing,
            "typed_profile_contract_present",
        )

        raw_options = _passing_physics_aware_evidence()
        raw_options["typed_profile_contract"][
            "raw_petsc_options_accepted"
        ] = True
        cases["raw_options_tampered"] = (
            raw_options,
            "typed_profile_contract_rejects_raw_options",
        )

        wrong_profile = _passing_physics_aware_evidence()
        wrong_profile["typed_profile_contract"]["name"] = "gmres_jacobi"
        cases["profile_name_tampered"] = (
            wrong_profile,
            "typed_profile_contract_name",
        )

        rank_deficient = _passing_physics_aware_evidence()
        rank_deficient["physics_aware_preconditioner"][
            "coarse_rank"
        ] = 79
        cases["rank_deficient_coarse"] = (
            rank_deficient,
            "physics_aware_coarse_full_rank",
        )

        missing_bytes = _passing_physics_aware_evidence()
        missing_bytes["physics_aware_preconditioner"].pop(
            "coarse_dense_matrix_bytes"
        )
        cases["missing_dense_coarse_bytes"] = (
            missing_bytes,
            "physics_aware_dense_coarse_bytes_consistent",
        )

        inventory_mismatch = _passing_physics_aware_evidence()
        inventory_mismatch["factor_inventory"][
            "coarse_dense_matrix_bytes"
        ] += 16
        cases["inventory_mismatch"] = (
            inventory_mismatch,
            "factor_inventory_dense_coarse_bytes_match",
        )

        for label, (evidence, expected_failure) in cases.items():
            with self.subTest(label=label):
                result = _classify_physics_evidence(
                    deepcopy(evidence)
                )
                self.assertFalse(
                    result["formal_iterative_screen_pass"]
                )
                self.assertTrue(result["evidence_valid"])
                self.assertEqual(
                    result["status"],
                    "controlled_negative_iterative_screen_failed",
                )
                self.assertIn(expected_failure, result["failures"])

    def test_typed_profile_is_opt_in_not_run_and_not_raw_options(self) -> None:
        self.assertIn(
            PHYSICS_AWARE_PROFILE,
            SUPPORTED_CONDENSED_ITERATIVE_PROFILES,
        )
        contract = condensed_iterative_profile_contract(
            PHYSICS_AWARE_PROFILE
        )
        self.assertEqual(
            contract["evidence_status"],
            "not_run_requires_formal_discriminator",
        )
        self.assertEqual(contract["ksp_type"], "fgmres")
        self.assertEqual(contract["relative_tolerance"], 1.0e-10)
        self.assertFalse(contract["raw_petsc_options_accepted"])
        self.assertFalse(contract["ordinary_default_changed"])

        args = _parse_args(
            [
                "--execute-pde",
                "--profile",
                PHYSICS_AWARE_PROFILE,
            ]
        )
        cfg = _iterative_config(args.profile, h_nm=15.0)
        self.assertEqual(
            cfg.stage4_condensed_iterative_profile,
            PHYSICS_AWARE_PROFILE,
        )
        self.assertEqual(cfg.petsc_extra_options, {})
        self.assertIsNone(
            target_stage4_config(
                degree=6,
                h_nm=15.0,
            ).stage4_condensed_iterative_profile
        )

    def test_dry_plan_preserves_old_negatives_and_marks_new_not_run(
        self,
    ) -> None:
        args = _parse_args(["--profile", PHYSICS_AWARE_PROFILE])
        plan = _dry_run_plan(args)
        self.assertFalse(plan["pde_started"])
        self.assertEqual(
            plan["profile_evidence_status"]["gmres_jacobi"],
            "closed_controlled_negative",
        )
        self.assertEqual(
            plan["profile_evidence_status"]["fgmres_asm_ilu"],
            "closed_controlled_negative",
        )
        self.assertEqual(
            plan["physics_aware_discriminator"]["status"],
            "not_run",
        )
        self.assertTrue(
            plan["physics_aware_discriminator"][
                "small_dense_coarse_factor_reported_separately"
            ]
        )

    def test_basis_is_the_normalized_diagonal_lift_of_physical_dtn_columns(
        self,
    ) -> None:
        matrix, values = _block_matrix()
        try:
            basis, audit = build_diagonal_lifted_dtn_trace_basis(
                matrix,
                trace_rows=4,
                dtn_auxiliary_rows=2,
            )
            self.assertEqual(audit["basis_dimension"], 2)
            self.assertEqual(audit["trace_coupling_nnz"], 4)
            self.assertEqual(audit["basis_nnz"], 6)
            self.assertLess(
                audit["basis_normalization_max_abs_error"],
                1.0e-14,
            )
            for mode, vector in enumerate(basis):
                dense = np.zeros(6, dtype=np.complex128)
                dense[vector.indices] = vector.values
                expected = np.zeros(6, dtype=np.complex128)
                expected[:4] = (
                    -values[:4, 4 + mode]
                    / np.diag(values)[:4]
                )
                expected[4 + mode] = 1.0
                expected /= np.linalg.norm(expected)
                np.testing.assert_allclose(
                    dense,
                    expected,
                    rtol=1.0e-14,
                    atol=1.0e-14,
                )
        finally:
            matrix.destroy()

    def test_coupled_zero_trace_diagonal_fails_closed(self) -> None:
        matrix = PETSc.Mat().createAIJ(
            [3, 3],
            nnz=2,
            comm=PETSc.COMM_SELF,
        )
        try:
            matrix.setValue(0, 2, 1.0)
            matrix.setValue(1, 1, 2.0)
            matrix.setValue(2, 2, 1.0)
            matrix.assemble()
            with self.assertRaisesRegex(
                RuntimeError,
                "singular/near-zero",
            ):
                build_diagonal_lifted_dtn_trace_basis(
                    matrix,
                    trace_rows=2,
                    dtn_auxiliary_rows=1,
                )
        finally:
            matrix.destroy()

    def test_serial_profile_solves_without_a_global_sparse_factor(
        self,
    ) -> None:
        matrix, _ = _block_matrix()
        rhs = PETSc.Vec().createSeq(6, comm=PETSc.COMM_SELF)
        x = None
        ksp = None
        try:
            rhs.setValues(
                np.arange(6, dtype=PETSc.IntType),
                np.arange(1, 7, dtype=PETSc.ScalarType),
            )
            rhs.assemble()
            x, ksp, telemetry = _solve_augmented_system(
                matrix,
                rhs,
                {},
                "task035b_dtn_trace_deflation_test_",
                comm=MPI.COMM_SELF,
                dofs=6,
                constraints=0,
                iterative_profile=PHYSICS_AWARE_PROFILE,
                dtn_auxiliary_rows=2,
            )
            audit = telemetry["condensed_iterative"]
            inventory = telemetry["factor_inventory"]
            physics = audit["physics_aware_preconditioner"]
            self.assertEqual(ksp.getType(), "fgmres")
            self.assertEqual(ksp.getPC().getType(), "python")
            self.assertLess(
                audit["terminal_explicit_reduced_relative_residual"],
                1.0e-12,
            )
            self.assertEqual(inventory["global_direct_factor_nnz"], 0)
            self.assertEqual(
                inventory["global_fine_sparse_factor_nnz"],
                0,
            )
            self.assertFalse(
                inventory["mumps_symbolic_or_numeric_created"]
            )
            self.assertFalse(inventory["local_subdomain_ilu_active"])
            self.assertTrue(inventory["coarse_dense_lu_active"])
            self.assertTrue(physics["fine_operator_factor_free"])
            self.assertFalse(
                physics["strictly_factorless_preconditioner"]
            )
            self.assertEqual(physics["coarse_dimension"], 2)
            self.assertEqual(physics["coarse_rank"], 2)
            self.assertEqual(
                inventory["coarse_dense_matrix_bytes"],
                physics["coarse_dense_matrix_bytes"],
            )
            self.assertTrue(
                inventory["coarse_dense_lu_storage_semantics"]
            )
            self.assertGreater(
                physics["preconditioner_apply_count"],
                0,
            )
        finally:
            if ksp is not None:
                ksp.destroy()
            if x is not None:
                x.destroy()
            rhs.destroy()
            matrix.destroy()

    def test_distributed_profile_preserves_the_same_factor_contract(
        self,
    ) -> None:
        matrix = _distributed_block_matrix()
        rhs = matrix.createVecRight()
        x = None
        ksp = None
        try:
            row_start, row_end = rhs.getOwnershipRange()
            rows = np.arange(
                row_start,
                row_end,
                dtype=PETSc.IntType,
            )
            rhs.setValues(
                rows,
                np.asarray(rows + 1, dtype=PETSc.ScalarType),
            )
            rhs.assemble()
            x, ksp, telemetry = _solve_augmented_system(
                matrix,
                rhs,
                {},
                "task035b_dtn_trace_deflation_mpi_test_",
                comm=MPI.COMM_WORLD,
                dofs=6,
                constraints=0,
                iterative_profile=PHYSICS_AWARE_PROFILE,
                dtn_auxiliary_rows=2,
            )
            audit = telemetry["condensed_iterative"]
            self.assertLess(
                audit["terminal_explicit_reduced_relative_residual"],
                1.0e-12,
            )
            self.assertEqual(
                telemetry["factor_inventory"][
                    "global_direct_factor_nnz"
                ],
                0,
            )
            self.assertEqual(
                audit["physics_aware_preconditioner"][
                    "coarse_dimension"
                ],
                2,
            )
        finally:
            if ksp is not None:
                ksp.destroy()
            if x is not None:
                x.destroy()
            rhs.destroy()
            matrix.destroy()


if __name__ == "__main__":
    unittest.main()
