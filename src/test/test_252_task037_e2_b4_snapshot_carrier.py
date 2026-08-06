import copy
import inspect
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc
from scipy.linalg import lstsq as dense_lstsq

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
from src.solvers.static_modal_capacity_oracle import (
    build_capacity_space_solvers,
    evaluate_capacity_residual,
    materialize_sparse_columns,
    qualify_e2_capacity_audit,
)
from src.solvers.static_modal_coarse_gate import (
    OwnerLocalBasis,
    load_owner_local_basis_shard,
    save_owner_local_basis_shard,
)
from src.solvers.physical_slab_two_level import SparseCoarseVector


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
        "task037_e2_modal_capacity_gate": False,
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
        capacity_parameter = "task037_e2_capacity_live_observer"
        assert (
            capacity_parameter
            in inspect.signature(_solve_static_condensed_fgmres_core).parameters
        )
        assert (
            capacity_parameter
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
            assert capacity_parameter not in inspect.signature(wrapper).parameters
    finally:
        residual.destroy()
        solution.destroy()
        rhs.destroy()
        matrix.destroy()


def test_e2_capacity_rank_deficient_lstsq_and_five_residual_metrics():
    operator = _aij([[2.0, 0.0], [0.0, 3.0]])
    sparse_columns = (
        SparseCoarseVector(
            np.asarray([0, 1], dtype=PETSc.IntType),
            np.asarray([1.0, 0.0], dtype=PETSc.ScalarType),
            slab=0,
            eigenvalue=0.0,
            eigenpair_residual=0.0,
        ),
        SparseCoarseVector(
            np.asarray([0, 1], dtype=PETSc.IntType),
            np.asarray([0.0, 1.0], dtype=PETSc.ScalarType),
            slab=0,
            eigenvalue=0.0,
            eigenpair_residual=0.0,
        ),
    )
    z75 = materialize_sparse_columns(operator, sparse_columns)
    y75 = None
    y_m = OwnerLocalBasis.from_local_array(
        np.asarray([[1.0, 1.0], [0.0, 0.0]], dtype=np.complex128),
        global_rows=2,
        comm=MPI.COMM_SELF,
        label="YM",
        research_opt_in=True,
    )
    residual = PETSc.Vec().createSeq(2, comm=MPI.COMM_SELF)
    b4_remainder = PETSc.Vec().createSeq(2, comm=MPI.COMM_SELF)
    residual.setArray(np.asarray([1.0, 2.0], dtype=np.complex128))
    b4_remainder.setArray(np.asarray([0.5, 1.0], dtype=np.complex128))
    try:
        y75 = z75.apply(operator, label="Y75", research_opt_in=True)
        np.testing.assert_allclose(
            y75.local_matrix(),
            np.asarray([[2.0, 0.0], [0.0, 3.0]], dtype=np.complex128)
            @ z75.local_matrix(),
        )
        spaces = build_capacity_space_solvers(y75.columns, y_m.columns)
        metrics = evaluate_capacity_residual(spaces, residual, b4_remainder)
        dense_residual = residual.getArray(readonly=True).copy()
        dense_b4 = b4_remainder.getArray(readonly=True).copy()
        dense_y75 = y75.local_matrix()
        dense_ym = y_m.local_matrix()

        def dense_rho(action, vector, denominator):
            coefficients = dense_lstsq(
                action,
                vector,
                lapack_driver="gelsd",
            )[0]
            return float(
                np.linalg.norm(vector - action @ coefficients)
                / max(denominator, np.finfo(float).tiny)
            )

        assert metrics["rho_75"] == pytest.approx(
            dense_rho(dense_y75, dense_residual, np.linalg.norm(dense_residual))
        )
        assert metrics["rho_M"] == pytest.approx(
            dense_rho(dense_ym, dense_residual, np.linalg.norm(dense_residual))
        )
        assert metrics["rho_75M"] == pytest.approx(
            dense_rho(
                np.column_stack((dense_y75, dense_ym)),
                dense_residual,
                np.linalg.norm(dense_residual),
            )
        )
        assert metrics["rho_BM"] == pytest.approx(
            dense_rho(dense_ym, dense_b4, np.linalg.norm(dense_residual))
        )
        assert metrics["rho_hat_M_B"] == pytest.approx(
            dense_rho(dense_ym, dense_b4, np.linalg.norm(dense_b4))
        )
        assert spaces.y_m.audit.effective_rank == 1
        assert spaces.y_m.audit.normal_equations_used is False
        assert spaces.y_m.audit.factorization_count == 1
        assert (
            spaces.y_m.audit.root_solve_method
            == "scipy.linalg.svd(retained_pseudoinverse)"
        )
        assert all(value <= 1.0e-12 for value in metrics["repeat_error"].values())
    finally:
        b4_remainder.destroy()
        residual.destroy()
        y_m.destroy()
        if y75 is not None:
            y75.destroy()
        z75.destroy()
        operator.destroy()


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
    assert ordinary.task037_e2_modal_capacity_gate is False
    capacity_argv = [
        item
        for item in argv
        if item != "--task037-e2-b4-snapshot-carrier"
    ] + ["--task037-e2-modal-capacity-gate"]
    capacity = watchdog._parse_args(capacity_argv)
    assert capacity.task037_e2_modal_capacity_gate is True
    try:
        watchdog._parse_args([*capacity_argv, "--task037-e2-b4-snapshot-carrier"])
    except SystemExit:
        pass
    else:
        raise AssertionError("capacity and carrier flags must be exclusive")
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


def _positive_capacity_audit():
    def space(rank, count):
        return {
            "column_count": count,
            "effective_rank": rank,
            "retained_condition_number": 2.0,
            "singular_values": [2.0, 1.0],
            "factorization_count": 1,
            "root_solve_method": "scipy.linalg.svd(retained_pseudoinverse)",
        }

    samples = []
    for iteration in (0, 20, 100, 200):
        samples.append(
            {
                "iteration": iteration,
                "rho_75": 0.9,
                "rho_M": 0.5,
                "rho_75M": 0.6,
                "rho_BM": 0.4,
                "rho_hat_M_B": 0.5,
                "improvement_M": 2.0,
                "incremental_75_over_75M": 1.5,
                "repeat_error": {
                    "75D": 0.0,
                    "M120": 0.0,
                    "75D+M120": 0.0,
                    "B4+M120": 0.0,
                },
            }
        )
    return {
        "action_operator": "matrix_free_condensed_F_minus_C_Hinv_D",
        "dtn_included": True,
        "normal_equations_used": False,
        "global_A_materialized": False,
        "global_F_materialized": False,
        "same_run_live_basis": {
            "same_layout": True,
            "z_m": {
                "global_rows": 51192,
                "column_count": 240,
                "owner_local": True,
            },
            "y_m": {
                "global_rows": 51192,
                "column_count": 240,
                "owner_local": True,
            },
        },
        "action_spaces": {
            "75D": space(75, 75),
            "M120": space(180, 240),
            "75D+M120": space(180, 315),
        },
        "capacity_samples": samples,
    }


def test_e2_capacity_checker_separates_implementation_and_capacity_results():
    positive = _positive_capacity_audit()
    result = qualify_e2_capacity_audit(positive)
    assert result["pass"] is True
    assert result["classification"] == "M120_TRIAL_SPACE_HAS_COARSE_CAPACITY"

    rank_negative = copy.deepcopy(positive)
    rank_negative["action_spaces"]["M120"]["effective_rank"] = 179
    rank_result = qualify_e2_capacity_audit(rank_negative)
    assert rank_result["status"] == "implementation_failure"
    assert rank_result["classification"] == "M120_MODAL_CAPACITY_IMPLEMENTATION_FAILED"

    missing_action = copy.deepcopy(positive)
    missing_action["action_operator"] = None
    missing_result = qualify_e2_capacity_audit(missing_action)
    assert missing_result["status"] == "implementation_failure"
    assert "action_operator" in missing_result["implementation_failures"]

    capacity_negative = copy.deepcopy(positive)
    capacity_negative["capacity_samples"][2]["improvement_M"] = 1.4
    capacity_result = qualify_e2_capacity_audit(capacity_negative)
    assert capacity_result["status"] == "capacity_negative"
    assert (
        capacity_result["classification"]
        == "M120_MODAL_COARSE_INSUFFICIENT_ON_FROZEN_LATE_RESIDUALS"
    )


def test_e2_distributed_owner_local_ls_matches_root_gelsd_reference():
    comm = MPI.COMM_WORLD
    if comm.size != 2:
        pytest.skip("run this owner-local contract test with MPI2")
    local_action = (
        np.asarray([[1.0, 0.0, 1.0], [0.0, 1.0, 1.0]])
        if comm.rank == 0
        else np.asarray([[0.0, 1.0, 1.0], [1.0, 0.0, 1.0], [0.0, 1.0, 1.0]])
    )
    local_rhs = (
        np.asarray([1.0, 2.0])
        if comm.rank == 0
        else np.asarray([3.0, 4.0, 5.0])
    )
    local_rows = local_action.shape[0]
    columns = []
    for index in range(local_action.shape[1]):
        vector = PETSc.Vec().createMPI(
            (local_rows, 5),
            comm=comm,
        )
        vector.setArray(np.asarray(local_action[:, index], dtype=np.complex128))
        vector.assemble()
        columns.append(vector)
    residual = PETSc.Vec().createMPI((local_rows, 5), comm=comm)
    residual.setArray(np.asarray(local_rhs, dtype=np.complex128))
    residual.assemble()
    solver = None
    corrected = None
    try:
        solver = build_capacity_space_solvers(columns, columns).y_m
        coefficients, corrected = solver.solve(residual)
        gathered_action = comm.gather(local_action, root=0)
        gathered_rhs = comm.gather(local_rhs, root=0)
        if comm.rank == 0:
            dense_action = np.vstack(gathered_action)
            dense_rhs = np.concatenate(gathered_rhs)
            reference_coefficients, _, reference_rank, _ = dense_lstsq(
                dense_action,
                dense_rhs,
                lapack_driver="gelsd",
            )
            reference_residual = np.linalg.norm(
                dense_rhs - dense_action @ reference_coefficients
            )
        else:
            reference_coefficients = None
            reference_rank = None
            reference_residual = None
        reference_coefficients, reference_rank, reference_residual = comm.bcast(
            (reference_coefficients, reference_rank, reference_residual),
            root=0,
        )
        ok = (
            np.allclose(coefficients, reference_coefficients, rtol=1.0e-12, atol=1.0e-12)
            and solver.audit.effective_rank == reference_rank
            and abs(float(corrected.norm()) - float(reference_residual)) <= 1.0e-12
            and solver.audit.factorization_count == 1
            and solver.audit.normal_equations_used is False
        )
        assert comm.allreduce(ok, op=MPI.LAND)
    finally:
        if corrected is not None:
            corrected.destroy()
        residual.destroy()
        for vector in columns:
            vector.destroy()
