from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from benchmarks.run_task035b_condensed_iterative import (
    _classify_screen,
    _dry_run_plan,
    _iterative_config,
    _parse_args,
)
from src.solvers.condensed_iterative_profiles import (
    DtnTracePhysicalSlabPc,
    PHYSICAL_SLAB_DTN_PROFILE,
    condensed_iterative_profile,
    condensed_iterative_profile_contract,
    configure_condensed_iterative_outer_ksp,
    configure_physical_slab_dtn_trace_pc,
)
from src.solvers.condensed_physical_slab_partition import (
    CondensedPhysicalSlabPartition,
    build_condensed_physical_z_slab_partition,
    build_condensed_physical_z_slab_partition_from_space,
)
from src.solvers.dtn_port_3d import _solve_augmented_system
from src.solvers.physical_slab_two_level import (
    certify_fixed_linear_preconditioner,
)


_VALUES = np.asarray(
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

_ROOT = Path(__file__).resolve().parents[2]
_CAPABILITY_RECORD = (
    _ROOT
    / "benchmarks"
    / "cases"
    / "095_high_order_local_hp_resource_envelope"
    / "records"
    / "h15_physical_slab_dtn_iterative_capability_v1.json"
)


def _passing_slab_screen_evidence() -> dict:
    coarse_dimension = 80
    coarse_entries = coarse_dimension * coarse_dimension
    partition = {
        "schema_version": (
            "task035b.condensed-physical-z-slab-partition.v1"
        ),
        "capability_pass": True,
        "all_active_trace_rows_covered": True,
        "all_auxiliary_rows_covered_once_on_physical_side": True,
        "inactive_trace_rows_added": False,
        "num_physical_z_slabs": 10,
        "overlap_layers": 0.125,
        "matrix_rows": 16880,
    }
    physics = {
        "coarse_dimension": coarse_dimension,
        "coarse_rank": coarse_dimension,
        "coarse_dense_lu_active": True,
        "coarse_dense_matrix_entries": coarse_entries,
        "coarse_dense_matrix_bytes": coarse_entries * 16,
        "strictly_factorless_preconditioner": False,
        "strictly_factorless": False,
        "strictly_factorless_reason": (
            "physical z-slab ILU(0) and small dense coarse LU retained"
        ),
        "fine_operator_factor_free": True,
        "global_fine_factor_free": True,
        "no_global_sparse_direct_factor": True,
        "global_fine_sparse_factor_nnz": 0,
        "mumps_symbolic_or_numeric_created": False,
        "physical_slab_partition": partition,
        "local_subdomain_ilu_active": True,
        "local_subdomain_ilu_levels": 0,
        "local_subdomain_factor_nnz": 1234,
        "local_subdomain_factor_only_storage": True,
        "all_factor_storage_disclosed": True,
    }
    inventory = {
        "global_direct_factor_nnz": 0,
        "global_fine_sparse_factor_nnz": 0,
        "mumps_symbolic_or_numeric_created": False,
        "coarse_dense_lu_active": True,
        "coarse_dense_matrix_entries": coarse_entries,
        "coarse_dense_matrix_bytes": coarse_entries * 16,
        "coarse_dense_lu_storage_semantics": (
            "small replicated SciPy complex LU; not a global fine sparse "
            "factor"
        ),
        "fine_operator_factor_free": True,
        "strictly_factorless_preconditioner": False,
        "strictly_factorless": False,
        "global_fine_factor_free": True,
        "no_global_sparse_direct_factor": True,
        "local_subdomain_ilu_active": True,
        "local_subdomain_ilu_levels": 0,
        "local_subdomain_factor_nnz": 1234,
        "all_factor_storage_disclosed": True,
    }
    return {
        "summary_available": True,
        "profile": PHYSICAL_SLAB_DTN_PROFILE,
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
            PHYSICAL_SLAB_DTN_PROFILE
        ),
        "physics_aware_preconditioner": physics,
        "factor_inventory": inventory,
    }


def _matrix(comm) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(
        [6, 6],
        nnz=(6, 6),
        comm=comm,
    )
    row_start, row_end = matrix.getOwnershipRange()
    for row in range(row_start, row_end):
        columns = np.flatnonzero(_VALUES[row]).astype(PETSc.IntType)
        matrix.setValues(row, columns, _VALUES[row, columns])
    matrix.assemble()
    return matrix


def _global_values(vector: PETSc.Vec) -> np.ndarray:
    comm = vector.getComm().tompi4py()
    start, end = vector.getOwnershipRange()
    packet = (
        int(start),
        int(end),
        np.asarray(
            vector.getArray(readonly=True),
            dtype=PETSc.ScalarType,
        ).copy(),
    )
    result = np.empty(vector.getSize(), dtype=PETSc.ScalarType)
    for packet_start, packet_end, values in comm.allgather(packet):
        result[packet_start:packet_end] = values
    return result


def _partition(
    comm: MPI.Comm = MPI.COMM_WORLD,
) -> CondensedPhysicalSlabPartition:
    global_midpoints = np.asarray([0.5, 1.5, 2.5], dtype=np.float64)
    global_cell_dofs = (
        np.asarray([10, 11], dtype=PETSc.IntType),
        np.asarray([11, 12], dtype=PETSc.IntType),
        np.asarray([12, 13, 14], dtype=PETSc.IntType),
    )
    local_cells = [
        cell for cell in range(3) if cell % comm.size == comm.rank
    ]
    expansion = {
        10: (
            np.asarray([0], dtype=PETSc.IntType),
            np.asarray([1.0], dtype=PETSc.ScalarType),
        ),
        11: (
            np.asarray([1], dtype=PETSc.IntType),
            np.asarray([1.0], dtype=PETSc.ScalarType),
        ),
        12: (
            np.asarray([2], dtype=PETSc.IntType),
            np.asarray([1.0], dtype=PETSc.ScalarType),
        ),
        13: (
            np.asarray([3], dtype=PETSc.IntType),
            np.asarray([1.0], dtype=PETSc.ScalarType),
        ),
        # A periodic slave trace entity pulls active row zero onto the top slab.
        14: (
            np.asarray([0], dtype=PETSc.IntType),
            np.asarray([np.exp(0.2j)], dtype=PETSc.ScalarType),
        ),
    }
    return build_condensed_physical_z_slab_partition(
        comm=comm,
        owned_cell_midpoint_z=global_midpoints[local_cells],
        owned_cell_original_dofs=[
            global_cell_dofs[cell] for cell in local_cells
        ],
        expansion_by_original=expansion,
        trace_rows=4,
        dtn_side_by_aux=("bottom", "top"),
        domain_z_min=0.0,
        domain_z_max=3.0,
        num_slabs=3,
        overlap_layers=0.0,
    )


class Task035bPhysicalSlabDtnProfileTests(unittest.TestCase):
    """Qualify the physical-slab/DtN typed opt-in iterative profile."""

    def test_capability_record_is_hash_bound_and_not_formal_pde_evidence(
        self,
    ) -> None:
        record = json.loads(_CAPABILITY_RECORD.read_text())
        self.assertEqual(
            record["status"],
            "implemented_unit_qualified_formal_pde_not_run",
        )
        self.assertFalse(record["formal_pde_started"])
        self.assertFalse(record["heavy_pde_rerun"])
        self.assertFalse(record["candidate_promotion"])
        self.assertIsNone(record["source"]["implementation_commit_sha"])
        self.assertTrue(
            record["factor_semantics"]["global_fine_factor_free"]
        )
        self.assertTrue(
            record["factor_semantics"][
                "no_global_sparse_direct_factor"
            ]
        )
        self.assertFalse(
            record["factor_semantics"]["strictly_factorless"]
        )
        self.assertTrue(
            record["factor_semantics"][
                "complete_factor_inventory_required"
            ]
        )
        formal = record["qualification"]["formal_h15_mpi8_screen"]
        self.assertEqual(formal["status"], "not_run")
        self.assertIsNone(formal["formal_iterative_screen_pass"])
        for source in record["source"]["files"]:
            payload = (_ROOT / source["path"]).read_bytes()
            self.assertEqual(
                hashlib.sha256(payload).hexdigest(),
                source["sha256"],
            )

    def test_typed_profile_contract_discloses_both_factor_classes(self) -> None:
        profile = condensed_iterative_profile(PHYSICAL_SLAB_DTN_PROFILE)
        contract = condensed_iterative_profile_contract(
            PHYSICAL_SLAB_DTN_PROFILE
        )

        self.assertTrue(profile.requires_physical_slab_partition)
        self.assertEqual(profile.physical_z_slabs, 10)
        self.assertEqual(profile.physical_slab_overlap_layers, 0.125)
        self.assertEqual(profile.local_ilu_levels, 0)
        self.assertTrue(profile.factor_only_local_storage)
        self.assertTrue(
            contract["physical_slab_partition_gate"]["required"]
        )
        self.assertEqual(
            contract["physical_slab_partition_gate"][
                "schema_version_required"
            ],
            "task035b.condensed-physical-z-slab-partition.v1",
        )
        self.assertTrue(
            contract["physical_slab_partition_gate"][
                "periodic_slave_pullback_required"
            ]
        )
        self.assertFalse(
            contract["physical_slab_partition_gate"][
                "inactive_rows_allowed"
            ]
        )
        self.assertTrue(
            contract["factor_semantics"][
                "global_fine_sparse_direct_factor_required_absent"
            ]
        )
        self.assertTrue(
            contract["factor_semantics"]["global_fine_factor_free"]
        )
        self.assertTrue(
            contract["factor_semantics"][
                "no_global_sparse_direct_factor"
            ]
        )
        self.assertTrue(
            contract["factor_semantics"][
                "local_physical_slab_ilu_disclosed"
            ]
        )
        self.assertTrue(
            contract["factor_semantics"][
                "small_dense_galerkin_lu_disclosed"
            ]
        )
        self.assertFalse(
            contract["factor_semantics"][
                "strictly_factorless_preconditioner"
            ]
        )
        self.assertFalse(
            contract["factor_semantics"]["strictly_factorless"]
        )
        self.assertTrue(
            contract["factor_semantics"][
                "complete_factor_inventory_required"
            ]
        )
        self.assertFalse(contract["ordinary_default_changed"])

    def test_outer_configuration_fails_closed_without_partition(self) -> None:
        profile = condensed_iterative_profile(PHYSICAL_SLAB_DTN_PROFILE)
        ksp = PETSc.KSP().create(PETSc.COMM_SELF)
        try:
            with self.assertRaisesRegex(
                RuntimeError,
                "requires a qualified physical active-trace z-slab partition",
            ):
                configure_condensed_iterative_outer_ksp(ksp, profile)
            configure_condensed_iterative_outer_ksp(
                ksp,
                profile,
                physical_slab_partition_available=True,
            )
            self.assertEqual(ksp.getType(), "fgmres")
        finally:
            ksp.destroy()

    def test_formal_runner_exposes_only_the_typed_opt_in(self) -> None:
        args = _parse_args(
            [
                "--execute-pde",
                "--profile",
                PHYSICAL_SLAB_DTN_PROFILE,
            ]
        )
        config = _iterative_config(args.profile, h_nm=15.0)
        plan = _dry_run_plan(args)
        self.assertEqual(
            config.stage4_condensed_iterative_profile,
            PHYSICAL_SLAB_DTN_PROFILE,
        )
        self.assertEqual(config.petsc_extra_options, {})
        self.assertIn(
            PHYSICAL_SLAB_DTN_PROFILE,
            plan["supported_programmatic_profiles"],
        )
        followup = plan["physics_aware_discriminator"][
            "physical_z_slab_followup"
        ]
        self.assertEqual(
            followup["profile"],
            PHYSICAL_SLAB_DTN_PROFILE,
        )
        self.assertTrue(
            followup["local_sparse_factor_reported_separately"]
        )
        self.assertFalse(
            followup["strictly_factorless_preconditioner"]
        )
        self.assertTrue(followup["global_fine_factor_free"])
        self.assertTrue(followup["no_global_sparse_direct_factor"])
        self.assertFalse(followup["strictly_factorless"])

    def test_formal_screen_checks_partition_and_local_factor_inventory(
        self,
    ) -> None:
        telemetry = {
            "observed_worker_rank_count": 8,
            "max_process_tree_swap_mb": 0.0,
            "max_worker_rank_smaps_swap_sum_mb": 0.0,
        }

        def classify(evidence: dict) -> dict:
            return _classify_screen(
                evidence,
                telemetry,
                expected_profile=PHYSICAL_SLAB_DTN_PROFILE,
                expected_mpi_size=8,
                return_code=0,
                terminated_for_memory=False,
                terminated_for_timeout=False,
                telemetry_readable=True,
            )

        passing = classify(_passing_slab_screen_evidence())
        self.assertTrue(passing["formal_iterative_screen_pass"])
        self.assertEqual(
            passing["status"],
            "actual_global_fine_factor_free_with_disclosed_"
            "preconditioner_factors_iterative_screen_pass",
        )
        self.assertTrue(
            passing["factor_semantics"]["global_fine_factor_free"]
        )
        self.assertTrue(
            passing["factor_semantics"][
                "no_global_sparse_direct_factor"
            ]
        )
        self.assertFalse(
            passing["factor_semantics"]["strictly_factorless"]
        )
        self.assertTrue(
            passing["factor_semantics"]["complete_factor_inventory"]
        )

        missing_partition = _passing_slab_screen_evidence()
        missing_partition["physics_aware_preconditioner"].pop(
            "physical_slab_partition"
        )
        missing_result = classify(missing_partition)
        self.assertFalse(missing_result["formal_iterative_screen_pass"])
        self.assertIn(
            "physical_slab_partition_present",
            missing_result["failures"],
        )

        hidden_factor = deepcopy(_passing_slab_screen_evidence())
        hidden_factor["factor_inventory"][
            "local_subdomain_factor_nnz"
        ] = None
        hidden_result = classify(hidden_factor)
        self.assertFalse(hidden_result["formal_iterative_screen_pass"])
        self.assertIn(
            "physical_slab_factor_inventory_matches",
            hidden_result["failures"],
        )

    def test_partition_is_physical_periodic_closed_and_mpi_invariant(
        self,
    ) -> None:
        partition = _partition()
        self.assertEqual(partition.matrix_rows, 6)
        self.assertEqual(
            [rows.tolist() for rows in partition.subdomains],
            [[0, 1, 4], [1, 2], [0, 2, 3, 5]],
        )
        self.assertTrue(
            partition.audit["all_active_trace_rows_covered"]
        )
        self.assertTrue(
            partition.audit[
                "all_auxiliary_rows_covered_once_on_physical_side"
            ]
        )
        hashes = MPI.COMM_WORLD.allgather(
            partition.audit["partition_sha256"]
        )
        self.assertEqual(len(set(hashes)), 1)

    def test_partition_refuses_incomplete_active_trace_coverage(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "does not cover every active trace row",
        ):
            build_condensed_physical_z_slab_partition(
                comm=MPI.COMM_WORLD,
                owned_cell_midpoint_z=np.asarray(
                    [0.5] if MPI.COMM_WORLD.rank == 0 else [],
                    dtype=np.float64,
                ),
                owned_cell_original_dofs=(
                    [np.asarray([10], dtype=PETSc.IntType)]
                    if MPI.COMM_WORLD.rank == 0
                    else []
                ),
                expansion_by_original={
                    10: (
                        np.asarray([0], dtype=PETSc.IntType),
                        np.asarray([1.0], dtype=PETSc.ScalarType),
                    )
                },
                trace_rows=2,
                dtn_side_by_aux=("bottom", "top"),
                domain_z_min=0.0,
                domain_z_max=1.0,
                num_slabs=1,
                overlap_layers=0.0,
            )

    def test_partition_refuses_nonphysical_auxiliary_side(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "must be 'top' or 'bottom'",
        ):
            build_condensed_physical_z_slab_partition(
                comm=MPI.COMM_WORLD,
                owned_cell_midpoint_z=np.asarray([], dtype=np.float64),
                owned_cell_original_dofs=[],
                expansion_by_original={},
                trace_rows=1,
                dtn_side_by_aux=("left",),
                domain_z_min=0.0,
                domain_z_max=1.0,
                num_slabs=1,
                overlap_layers=0.0,
            )

    def test_actual_dolfinx_space_adapter_uses_active_trace_rows(self) -> None:
        msh = mesh.create_unit_cube(
            MPI.COMM_WORLD,
            1,
            1,
            2,
            cell_type=mesh.CellType.hexahedron,
        )
        function_space = fem.functionspace(
            msh,
            element(
                "N1curl",
                msh.basix_cell(),
                1,
                dtype=default_real_type,
            ),
        )
        dofmap = function_space.dofmap
        active_rows = int(
            dofmap.index_map.size_global * dofmap.index_map_bs
        )
        expansion = {
            row: (
                np.asarray([row], dtype=PETSc.IntType),
                np.asarray([1.0], dtype=PETSc.ScalarType),
            )
            for row in range(active_rows)
        }
        operator = PETSc.Mat().createAIJ(
            [active_rows + 2, active_rows + 2],
            nnz=(1, 1),
            comm=PETSc.COMM_WORLD,
        )
        operator.setUp()
        condensed = SimpleNamespace(
            matrix=operator,
            active_rows=active_rows,
            trace_constraints=SimpleNamespace(
                active_rows=active_rows,
                expansion_by_original=expansion,
            ),
        )
        try:
            partition = (
                build_condensed_physical_z_slab_partition_from_space(
                    function_space,
                    condensed,
                    dtn_side_by_aux=("bottom", "top"),
                    domain_z_min=0.0,
                    domain_z_max=1.0,
                    num_slabs=2,
                    overlap_layers=0.0,
                )
            )
            self.assertEqual(partition.trace_rows, active_rows)
            self.assertEqual(partition.matrix_rows, active_rows + 2)
            self.assertTrue(
                partition.audit["all_active_trace_rows_covered"]
            )
            self.assertEqual(
                partition.audit["row_space"],
                "active_condensed_trace_plus_physical_dtn_auxiliary",
            )
        finally:
            operator.destroy()

    def test_two_level_action_matches_serial_and_is_fixed_linear(self) -> None:
        partition = _partition()
        distributed_matrix = _matrix(PETSc.COMM_WORLD)
        distributed_pc = DtnTracePhysicalSlabPc(
            distributed_matrix,
            partition=partition,
        )
        source = distributed_matrix.createVecRight()
        target = distributed_matrix.createVecLeft()
        start, end = source.getOwnershipRange()
        source.getArray()[:] = np.asarray(
            [
                complex(
                    np.sin(0.31 * (row + 1)),
                    np.cos(0.17 * (row + 2)),
                )
                for row in range(start, end)
            ],
            dtype=PETSc.ScalarType,
        )
        try:
            distributed_pc.apply(None, source, target)
            distributed_result = _global_values(target)
            certificate = certify_fixed_linear_preconditioner(
                distributed_pc,
                source,
            )
            self.assertLess(
                certificate["linearity_relative_error"],
                1.0e-12,
            )
            self.assertLess(
                certificate["determinism_relative_error"],
                1.0e-14,
            )

            serial_matrix = _matrix(PETSc.COMM_SELF)
            serial_pc = DtnTracePhysicalSlabPc(
                serial_matrix,
                partition=partition,
            )
            serial_source = serial_matrix.createVecRight()
            serial_target = serial_matrix.createVecLeft()
            serial_source.getArray()[:] = _global_values(source)
            try:
                serial_pc.apply(None, serial_source, serial_target)
                np.testing.assert_allclose(
                    distributed_result,
                    serial_target.getArray(readonly=True),
                    rtol=2.0e-13,
                    atol=2.0e-13,
                )
            finally:
                serial_target.destroy()
                serial_source.destroy()
                serial_pc.destroy()
                serial_matrix.destroy()

            diagnostics = distributed_pc.diagnostics
            self.assertEqual(
                diagnostics["global_fine_sparse_factor_nnz"],
                0,
            )
            self.assertTrue(diagnostics["global_fine_factor_free"])
            self.assertTrue(
                diagnostics["no_global_sparse_direct_factor"]
            )
            self.assertTrue(
                diagnostics["local_subdomain_ilu_active"]
            )
            self.assertGreater(
                diagnostics["local_subdomain_factor_nnz"],
                0,
            )
            self.assertTrue(diagnostics["coarse_dense_lu_active"])
            self.assertFalse(
                diagnostics["strictly_factorless_preconditioner"]
            )
            self.assertFalse(diagnostics["strictly_factorless"])
            self.assertIn(
                "physical z-slab ILU(0)",
                diagnostics["strictly_factorless_reason"],
            )
            self.assertTrue(
                diagnostics["all_factor_storage_disclosed"]
            )
            self.assertFalse(diagnostics["ordinary_default_changed"])
        finally:
            target.destroy()
            source.destroy()
            distributed_pc.destroy()
            distributed_matrix.destroy()

    def test_typed_fgmres_profile_solves_without_a_global_factor(self) -> None:
        partition = _partition()
        operator = _matrix(PETSc.COMM_WORLD)
        rhs = operator.createVecRight()
        solution = operator.createVecRight()
        start, end = rhs.getOwnershipRange()
        rhs.getArray()[:] = np.asarray(
            [
                complex(
                    np.cos(0.23 * (row + 1)),
                    np.sin(0.19 * (row + 2)),
                )
                for row in range(start, end)
            ],
            dtype=PETSc.ScalarType,
        )
        ksp = PETSc.KSP().create(PETSc.COMM_WORLD)
        ksp.setOperators(operator)
        profile = condensed_iterative_profile(
            PHYSICAL_SLAB_DTN_PROFILE
        )
        configure_condensed_iterative_outer_ksp(
            ksp,
            profile,
            physical_slab_partition_available=True,
        )
        context = configure_physical_slab_dtn_trace_pc(
            ksp,
            operator,
            partition=partition,
        )
        residual = rhs.duplicate()
        try:
            ksp.setUp()
            ksp.solve(rhs, solution)
            operator.mult(solution, residual)
            residual.axpy(PETSc.ScalarType(-1.0), rhs)
            relative_residual = float(residual.norm()) / max(
                float(rhs.norm()),
                np.finfo(float).tiny,
            )
            self.assertGreater(ksp.getConvergedReason(), 0)
            self.assertLess(relative_residual, 1.0e-10)
            self.assertEqual(
                context.diagnostics["global_fine_sparse_factor_nnz"],
                0,
            )
            self.assertFalse(
                context.diagnostics[
                    "mumps_symbolic_or_numeric_created"
                ]
            )
        finally:
            residual.destroy()
            context.destroy()
            ksp.destroy()
            solution.destroy()
            rhs.destroy()
            operator.destroy()

    def test_dtn_solver_hook_preserves_complete_factor_inventory(self) -> None:
        partition = _partition()
        operator = _matrix(PETSc.COMM_WORLD)
        rhs = operator.createVecRight()
        start, end = rhs.getOwnershipRange()
        rhs.getArray()[:] = np.asarray(
            [
                complex(
                    np.sin(0.29 * (row + 1)),
                    np.cos(0.13 * (row + 2)),
                )
                for row in range(start, end)
            ],
            dtype=PETSc.ScalarType,
        )
        solution = None
        ksp = None
        try:
            solution, ksp, telemetry = _solve_augmented_system(
                operator,
                rhs,
                {},
                "task035b_test_zslab_dtn_",
                comm=MPI.COMM_WORLD,
                iterative_profile=PHYSICAL_SLAB_DTN_PROFILE,
                dtn_auxiliary_rows=2,
                physical_slab_partition=partition,
            )
            inventory = telemetry["factor_inventory"]
            iterative = telemetry["condensed_iterative"]
            physics = iterative["physics_aware_preconditioner"]
            self.assertEqual(inventory["global_fine_sparse_factor_nnz"], 0)
            self.assertTrue(inventory["global_fine_factor_free"])
            self.assertTrue(inventory["no_global_sparse_direct_factor"])
            self.assertTrue(inventory["local_subdomain_ilu_active"])
            self.assertGreater(inventory["local_subdomain_factor_nnz"], 0)
            self.assertTrue(inventory["coarse_dense_lu_active"])
            self.assertFalse(inventory["strictly_factorless_preconditioner"])
            self.assertFalse(inventory["strictly_factorless"])
            self.assertTrue(inventory["all_factor_storage_disclosed"])
            self.assertEqual(
                physics["physical_slab_partition"]["partition_sha256"],
                partition.audit["partition_sha256"],
            )
            self.assertEqual(
                iterative["profile"],
                PHYSICAL_SLAB_DTN_PROFILE,
            )
            self.assertGreater(ksp.getConvergedReason(), 0)
        finally:
            if ksp is not None:
                ksp.destroy()
            if solution is not None:
                solution.destroy()
            rhs.destroy()
            operator.destroy()


if __name__ == "__main__":
    unittest.main()
