import inspect
from types import SimpleNamespace

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

import benchmarks.run_task033_full3d_watchdog as watchdog
from src.solvers.static_condensed_iterative import (
    _solve_static_condensed_fgmres_core,
    _true_residual_vector,
    solve_assembled_static_condensed_fgmres,
    solve_never_materialized_overlap0125_partition_fgmres,
    solve_never_materialized_p2_auxiliary_fgmres,
    solve_never_materialized_p2_factor_free_slab_auxiliary_fgmres,
    solve_never_materialized_p2_factor_free_slab_ras_auxiliary_fgmres,
    solve_never_materialized_static_condensed_fgmres,
)
from src.solvers.static_modal_coarse_gate import (
    OwnerLocalBasis,
    load_owner_local_basis_shard,
    save_owner_local_basis_shard,
)


def _aij(values):
    values = np.asarray(values, dtype=PETSc.ScalarType)
    matrix = PETSc.Mat().createAIJ(
        size=values.shape,
        nnz=values.shape[1],
        comm=MPI.COMM_SELF,
    )
    matrix.setUp()
    rows = np.arange(values.shape[0], dtype=PETSc.IntType)
    columns = np.arange(values.shape[1], dtype=PETSc.IntType)
    matrix.setValues(rows, columns, values)
    matrix.assemble()
    return matrix


def _e2_args(**overrides):
    values = {
        "degree": 6,
        "h_nm": 10.0,
        "polarization_kind": "s",
        "run_kind": "full-solve",
        "mpi_size": 8,
        "profile": "default",
        "stage4_full3d_assembly_backend": "assembly_time_static_condensed",
        "task035c_p6_h10_gate": True,
        "task035c_p6_preflight_authority": "authority.json",
        "task035c_p6_preflight_sha256": "a" * 64,
        "verified_clean_sha": "b" * 40,
        "allow_swap": False,
        "task037_f3_screen": 200,
        "task037_f3_full": False,
        "task037_f0_vector_observer": False,
        "task037_e0_matrix_free_dtn_gate": False,
        "task037_e1_modal_basis_gate": False,
        "task037_canonical_vector_export": False,
        "task037_f1_direct_trace_oracle": None,
        "task037_f5b_released_profile": False,
        "task037_m2c_never_materialized": True,
        "task037_m3a_overlap0125_partition": False,
        "task037_m4_p2_auxiliary": True,
        "task037_m4_factor_free_slab": True,
        "task037_m4_factor_free_local_steps": 4,
        "task037_m4_optimized_schwarz": False,
        "task037_m4_b2_long_full": False,
        "task037_m0_lifecycle_audit": False,
        "task035d_case097_gate": False,
        "task035d_nested_p_dwr_phase": None,
        "task035d_selective_face_dwr_phase": None,
        "task034_p4_h3_added_point": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_true_residual_is_b_minus_ax_and_observer_api_is_narrow():
    matrix = _aij([[2.0 + 1.0j, 0.5], [0.0, 3.0 - 0.5j]])
    rhs = PETSc.Vec().createSeq(2, comm=MPI.COMM_SELF)
    solution = PETSc.Vec().createSeq(2, comm=MPI.COMM_SELF)
    residual = PETSc.Vec().createSeq(2, comm=MPI.COMM_SELF)
    rhs.setArray(np.asarray([1.0 + 2.0j, -1.0j], dtype=np.complex128))
    solution.setArray(np.asarray([0.5 - 0.5j, 0.25 + 0.5j], dtype=np.complex128))
    try:
        _true_residual_vector(matrix, rhs, solution, residual)
        expected = rhs.getArray(readonly=True).copy()
        matrix.mult(solution, residual)
        expected -= residual.getArray(readonly=True)
        _true_residual_vector(matrix, rhs, solution, residual)
        np.testing.assert_allclose(residual.getArray(readonly=True), expected)
        parameter = "true_residual_vector_observer"
        assert (
            parameter
            in inspect.signature(_solve_static_condensed_fgmres_core).parameters
        )
        assert (
            parameter
            in inspect.signature(
                solve_never_materialized_p2_factor_free_slab_auxiliary_fgmres
            ).parameters
        )
        for wrapper in (
            solve_assembled_static_condensed_fgmres,
            solve_never_materialized_static_condensed_fgmres,
            solve_never_materialized_overlap0125_partition_fgmres,
            solve_never_materialized_p2_auxiliary_fgmres,
            solve_never_materialized_p2_factor_free_slab_ras_auxiliary_fgmres,
        ):
            assert parameter not in inspect.signature(wrapper).parameters
    finally:
        residual.destroy()
        solution.destroy()
        rhs.destroy()
        matrix.destroy()


def test_e2_admission_freezes_b4_identity_and_rejects_m3a_flag():
    positive = watchdog._task037_e2_b4_admission(_e2_args())
    assert positive["pass"] is True
    negative = watchdog._task037_e2_b4_admission(
        _e2_args(task037_m3a_overlap0125_partition=True)
    )
    assert negative["pass"] is False
    assert "m3a_overlap_partition_flag_disabled" in negative["failures"]


def test_e2_cli_parser_admits_only_the_frozen_screen(tmp_path):
    argv = [
        "--degree",
        "6",
        "--h-nm",
        "10",
        "--polarization-kind",
        "s",
        "--run-kind",
        "full-solve",
        "--mpi-size",
        "8",
        "--profile",
        "default",
        "--stage4-full3d-assembly-backend",
        "assembly_time_static_condensed",
        "--task035c-p6-h10-gate",
        "--task035c-p6-preflight-authority",
        str(tmp_path / "authority.json"),
        "--task035c-p6-preflight-sha256",
        "a" * 64,
        "--verified-clean-sha",
        "b" * 40,
        "--task037-e2-b4-snapshot-carrier",
        "--task037-f3-screen",
        "200",
        "--task037-m2c-never-materialized",
        "--task037-m4-p2-auxiliary",
        "--task037-m4-factor-free-slab",
        "--task037-m4-factor-free-local-steps",
        "4",
        "--poll-interval",
        "0.25",
        "--warning-gib",
        "10",
        "--terminate-gib",
        "14",
        "--timeout-seconds",
        "1800",
    ]
    parsed = watchdog._parse_args(argv)
    assert parsed.task037_e2_b4_snapshot_carrier is True
    ordinary = watchdog._parse_args(["--degree", "2"])
    assert ordinary.task037_e2_b4_snapshot_carrier is False
    try:
        watchdog._parse_args([*argv, "--task037-f3-screen", "100"])
    except SystemExit:
        pass
    else:
        raise AssertionError("screen 100 must fail the frozen E2 admission")


def test_e2_owner_local_four_column_shard_round_trip(tmp_path):
    values = np.asarray(
        [[1.0 + 1.0j, 2.0, 0.0, -1.0j], [0.5, 0.0, 3.0j, 1.0]],
        dtype=np.complex128,
    )
    basis = OwnerLocalBasis.from_local_array(
        values,
        global_rows=2,
        comm=MPI.COMM_SELF,
        label="B4_true_residual",
        research_opt_in=True,
    )
    try:
        manifest = save_owner_local_basis_shard(
            basis,
            tmp_path,
            source_sha="c" * 40,
            prefix="true_residual",
            research_opt_in=True,
        )
        assert manifest["column_count"] == 4
        entry = manifest["shards"][0]
        loaded = load_owner_local_basis_shard(
            entry["path"],
            expected_sha256=entry["sha256"],
        )
        np.testing.assert_array_equal(loaded["local_values"], values)
        assert loaded["source_sha"] == "c" * 40
    finally:
        basis.destroy()


def _positive_e2_audit():
    return {
        "source_sha": "b" * 40,
        "carrier_gate_pass": True,
        "owner_local": True,
        "replicated_global_vector": False,
        "solver_profile": "never_materialized_p2_factor_free_slab_auxiliary",
        "config": {
            "screen_iterations": 200,
            "restart": 90,
            "local_krylov_steps": 4,
            "overlap_fraction": 0.125,
            "partition": "partition",
            "global_A_materialized": False,
            "global_F_materialized": False,
        },
        "p6_factor_inventory": {"p6_factor_count": 0, "p6_factor_nnz": 0},
        "manifest": {
            "source_sha": "b" * 40,
            "global_rows": 51192,
            "column_count": 4,
            "shard_count": 8,
            "owner_local": True,
            "replicated_global_basis": False,
        },
        "true_residual_samples": [
            {
                "iteration": iteration,
                "relative_true_residual": float(iteration + 1),
                "core_relative_true_residual": float(iteration + 1),
                "global_rows": 51192,
            }
            for iteration in watchdog.TASK037_E2_B4_ITERATIONS
        ],
        "solver_convergence_gate": {
            "pass": False,
            "independent_of_carrier_gate": True,
        },
    }


def test_e2_checker_separates_carrier_from_solver_convergence():
    audit = _positive_e2_audit()
    result = watchdog._qualify_task037_e2_b4_snapshot(
        audit,
        solver_summary={"external_linear_solver_port": True},
        return_code=0,
        no_swap=True,
    )
    assert result["pass"] is True
    assert result["b4_solver_gate_independent"]["pass"] is False
    audit["true_residual_samples"][2]["core_relative_true_residual"] = 2.0
    negative = watchdog._qualify_task037_e2_b4_snapshot(
        audit,
        solver_summary={"external_linear_solver_port": True},
        return_code=0,
        no_swap=True,
    )
    assert negative["pass"] is False
    assert "core_scalar_identity" in negative["failures"]
