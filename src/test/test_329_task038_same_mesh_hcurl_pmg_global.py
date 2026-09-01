"""Focused contracts for the small same-mesh p3/p1 PMG candidate."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
from pathlib import Path
import textwrap
from types import SimpleNamespace

import numpy as np
import pytest
from petsc4py import PETSc

import src.solvers.fullspace_same_mesh_hcurl_pmg_global as pmg_global
from benchmarks import task038_full3d_same_mesh_hcurl_pmg_checker as checker
from benchmarks.run_task038_full3d_same_mesh_hcurl_pmg import (
    _operator_identity_authority,
    qualify_one_vcycle,
)
from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
    SameMeshHcurlPmg,
    audit_small_same_mesh_structure,
    destroy_small_same_mesh_positive_case,
)


def _diagonal(values: list[float]) -> PETSc.Mat:
    size = len(values)
    indptr = np.arange(size + 1, dtype=np.int32)
    indices = np.arange(size, dtype=np.int32)
    matrix = PETSc.Mat().createAIJ(
        [size, size],
        csr=(indptr, indices, np.asarray(values, dtype=np.complex128)),
        comm=PETSc.COMM_SELF,
    )
    matrix.assemble()
    return matrix


class _CountedSmoother:
    def __init__(self) -> None:
        self.calls = 0
        self.destroy_calls = 0

    def apply_into(self, _rhs: PETSc.Vec, target: PETSc.Vec) -> None:
        self.calls += 1
        target.set(0.0)

    def destroy(self) -> None:
        self.destroy_calls += 1


class _ExactDiagonalSolver:
    def __init__(self, diagonal: list[float]) -> None:
        self.diagonal = np.asarray(diagonal, dtype=np.complex128)
        self.calls = 0
        self.destroy_calls = 0

    def solve_lean(self, rhs: PETSc.Vec):
        self.calls += 1
        solution = rhs.duplicate()
        solution.array[:] = np.asarray(rhs.array) / self.diagonal
        return solution, {"backend": "test-exact-diagonal", "solve_count": self.calls}

    def destroy(self) -> None:
        self.destroy_calls += 1


class _OwnerTransfer:
    def __init__(self, size: int) -> None:
        index_map = SimpleNamespace(size_local=size, num_ghosts=0)
        function_space = SimpleNamespace(
            dofmap=SimpleNamespace(index_map=index_map)
        )
        mpc = SimpleNamespace(
            slaves=np.asarray([0], dtype=np.int32),
            function_space=function_space,
        )
        self.fine_floquet = SimpleNamespace(mpc=mpc)
        self.audit = {
            "pair_fine_to_coarse": [3, 1],
            "fine_global_rows": size,
            "coarse_global_rows": size,
        }
        self.primal_calls = 0
        self.adjoint_calls = 0
        self.destroy_calls = 0

    def apply_primal(self, _source, _target=None):
        raise AssertionError("allocating owner transfer must not be used")

    def apply_adjoint(self, _source, _target=None):
        raise AssertionError("allocating owner transfer must not be used")

    def apply_primal_into(self, source, target):
        self.primal_calls += 1
        source.copy(target)

    def apply_adjoint_into(self, source, target):
        self.adjoint_calls += 1
        source.copy(target)

    def destroy(self) -> None:
        self.destroy_calls += 1


@pytest.fixture
def pmg_case():
    diagonal = [2.0, 3.0, 4.0, 5.0]
    fine_matrix = _diagonal(diagonal)
    coarse_matrix = _diagonal(diagonal)
    owner = _OwnerTransfer(len(diagonal))
    smoother = _CountedSmoother()
    solver = _ExactDiagonalSolver(diagonal)
    pmg = SameMeshHcurlPmg(
        fine_matrix,
        coarse_matrix,
        owner,
        smoother=smoother,
        coarse_solver=solver,
    )
    rhs = fine_matrix.createVecRight()
    rhs.array[:] = np.asarray(
        [1.0 + 0.25j, 2.0 - 0.5j, -1.0 + 0.75j, 3.0 + 0.125j],
        dtype=np.complex128,
    )
    try:
        yield pmg, rhs, owner, smoother, solver, {"fine_matrix": fine_matrix}
    finally:
        if not pmg._destroyed:
            pmg.destroy()
        rhs.destroy()
        fine_matrix.destroy()
        coarse_matrix.destroy()


def test_small_pmg_qualification_reuses_work_and_has_independent_rhs(pmg_case):
    pmg, rhs, owner, smoother, solver, matrices = pmg_case
    before = np.asarray(rhs.array).copy()
    work_ids = tuple(id(vector) for vector in pmg.work_vectors)
    output = None
    try:
        result = qualify_one_vcycle(
            {"pmg": pmg, "rhs": rhs, "fine_matrix": matrices["fine_matrix"]}
        )
        assert result["probe_apply_count"] == 4
        assert result["finite"] is True
        assert result["input_unchanged"] is True
        assert result["each_apply_counts"] is True
        assert result["repeat_relative"] <= 1.0e-13
        assert result["linearity_relative"] <= 1.0e-12
        assert result["smoother_apply_total"] == 8
        assert result["transfer_3_1_adjoint_total"] == 4
        assert result["transfer_3_1_primal_total"] == 4
        assert result["p1_solve_total"] == 4
        assert result["p1_relative_residual_max"] <= 1.0e-11
        assert tuple(id(vector) for vector in pmg.work_vectors) == work_ids
        assert owner.primal_calls == owner.adjoint_calls == 4
        assert smoother.calls == 8
        assert solver.calls == 4
        output = pmg.apply(rhs)
        assert np.array_equal(rhs.array, before)
        assert output.array[0] == 0.0
        assert np.all(np.isfinite(np.asarray(output.array)))
        assert pmg.last_apply_facts["pre_smoother_count"] == 1
        assert pmg.last_apply_facts["post_smoother_count"] == 1
        assert pmg.last_apply_facts["p1_solve_count"] == 1
        assert pmg.last_apply_facts["owned_slave_max"] == 0.0
        assert owner.primal_calls == owner.adjoint_calls == 5
        assert smoother.calls == 10
        assert solver.calls == 5
    finally:
        if output is not None:
            output.destroy()


def test_smoother_power_seed_forwards_only_to_owned_smoother(monkeypatch):
    captured = []

    class _CapturedSmoother:
        def __init__(self, matrix, *, power_seed=None):
            captured.append((matrix, power_seed))

        def destroy(self):
            pass

    monkeypatch.setattr(pmg_global, "FixedChebyshevJacobiPETSc", _CapturedSmoother)
    fine_matrix = _diagonal([2.0, 3.0, 4.0, 5.0])
    coarse_matrix = _diagonal([2.0, 3.0, 4.0, 5.0])
    owner = _OwnerTransfer(4)
    seed = fine_matrix.createVecRight()
    seed.array[:] = (1.0 + 0.25j, 2.0 - 0.5j, 0.5 + 1.0j, -1.0j)
    seed_before = seed.array.copy()
    owned_pmg = external_pmg = None
    try:
        owned_pmg = SameMeshHcurlPmg(
            fine_matrix,
            coarse_matrix,
            owner,
            smoother_power_seed=seed,
            coarse_solver=_ExactDiagonalSolver([2.0, 3.0, 4.0, 5.0]),
        )
        assert captured == [(fine_matrix, seed)]
        np.testing.assert_array_equal(seed.array, seed_before)
        owned_pmg.destroy()
        owned_pmg = None

        external = _CountedSmoother()
        external_pmg = SameMeshHcurlPmg(
            fine_matrix,
            coarse_matrix,
            owner,
            smoother=external,
            smoother_power_seed=seed,
            coarse_solver=_ExactDiagonalSolver([2.0, 3.0, 4.0, 5.0]),
        )
        assert len(captured) == 1
        assert external_pmg.smoother is external
        np.testing.assert_array_equal(seed.array, seed_before)
    finally:
        if owned_pmg is not None:
            owned_pmg.destroy()
        if external_pmg is not None:
            external_pmg.destroy()
        seed.destroy()
        fine_matrix.destroy()
        coarse_matrix.destroy()


def test_function_and_vec_lifetimes_are_separated():
    class _Vec:
        def __init__(self):
            self.destroyed = False

        def destroy(self):
            self.destroyed = True

    source = _Vec()
    rhs = _Vec()
    case = {"source": source, "rhs": rhs}
    destroy_small_same_mesh_positive_case(case)
    assert case == {}
    assert source.destroyed is True
    assert rhs.destroyed is True
    tree = ast.parse(textwrap.dedent(inspect.getsource(audit_small_same_mesh_structure)))
    vector_loops = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Name)
        and node.target.id == "vector"
    ]
    assert vector_loops
    destroyed_names = {
        item.id
        for item in vector_loops[0].iter.elts
        if isinstance(item, ast.Name)
    }
    assert {"fine_full", "fine_algebraic"}.isdisjoint(destroyed_names)


def _watchdog_fixture(tmp_path: Path, worker_command: list[str]):
    raw = tmp_path / "watchdog.raw.jsonl"
    raw.write_text(
        json.dumps(
            {
                "authority": {
                    "process_tree": {
                        "rss_bytes": 1234,
                        "swap_bytes": 0,
                        "all_status_readable": True,
                    }
                }
            },
            allow_nan=False,
        )
        + "\n",
        encoding="utf-8",
    )
    record_path = (tmp_path / "worker_record.json").resolve()
    source_sha = "a" * 40
    compact = {
        "schema": checker.WATCHDOG_SCHEMA,
        "source_sha": source_sha,
        "worker_command": worker_command,
        "worker_record": str(record_path),
        "watchdog_raw": str(raw.resolve()),
        "raw_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
        "watchdog_rss_limit_bytes": checker.SMALL_RSS_LIMIT,
        "sample_count": 1,
        "peak_process_tree_rss_bytes": 1234,
        "max_process_tree_swap_bytes": 0,
        "all_status_readable": True,
        "returncode": 0,
        "natural_exit": True,
        "no_orphan": True,
    }
    record = {"command": worker_command, "mpi_size": 1}
    return compact, record, record_path, {"source_sha": source_sha}


def test_watchdog_direct_and_mpi2_launcher_contracts(tmp_path):
    command = ["/qualified/python", "-m", "small.worker", "--case", "p3-h50"]
    compact, record, record_path, provenance = _watchdog_fixture(tmp_path, command)
    errors: list[str] = []
    gates: list[str] = []
    checked = checker._check_watchdog(
        compact, record, record_path, provenance, 1, errors, gates
    )
    assert not errors and not gates
    assert checked["launcher_validation"] == "direct"

    mpi2_command = ["/usr/bin/mpiexec", "-n", "2", *command]
    compact["worker_command"] = mpi2_command
    record["mpi_size"] = 2
    errors, gates = [], []
    checked = checker._check_watchdog(
        compact, record, record_path, provenance, 2, errors, gates
    )
    assert not errors and not gates
    assert checked["launcher_validation"] == "mpiexec_n2"

    compact["watchdog_rss_limit_bytes"] = checker.SMALL_RSS_LIMIT - 1
    errors, gates = [], []
    checker._check_watchdog(
        compact, record, record_path, provenance, 2, errors, gates
    )
    assert any("500MB authority" in error for error in errors)
    compact["watchdog_rss_limit_bytes"] = checker.SMALL_RSS_LIMIT

    for invalid in (
        ["/usr/bin/mpirun", "-n", "2", *command],
        ["/tmp/mpiexec", "-n", "2", *command],
        ["usr/bin/mpiexec", "-n", "2", *command],
        ["/usr/bin/mpiexec", "-n", "3", *command],
    ):
        compact["worker_command"] = invalid
        errors, gates = [], []
        checker._check_watchdog(
            compact, record, record_path, provenance, 2, errors, gates
        )
        assert errors and not gates


def test_operator_identity_uses_global_not_local_slave_count():
    pmg_audit = {
        "schema": "small",
        "fine_owned_mpc_slave_count": 2,
        "fine_matrix_rows": 7,
    }
    matrix_facts = {
        name: {
            "rows": 7,
            "cols": 7,
            "global_nnz": 12,
            "finite_diagonal": True,
            "positive_diagonal": True,
        }
        for name in ("fine", "coarse")
    }
    material = {
        "cell_counts": {"air": 1},
        "positive_coefficients": {
            "air": {"mu_inverse": 1.0, "k0_squared_abs_epsilon": 1.0}
        },
        "global_cell_count": 1,
    }
    first = _operator_identity_authority(pmg_audit, matrix_facts, material, 5)
    second_audit = dict(pmg_audit, fine_owned_mpc_slave_count=3)
    second = _operator_identity_authority(second_audit, matrix_facts, material, 5)
    third = _operator_identity_authority(pmg_audit, matrix_facts, material, 6)
    assert "fine_owned_mpc_slave_count" not in first["architecture"]
    assert first["architecture"]["fine_global_owned_mpc_slave_count"] == 5
    assert checker._stable_sha(first) == checker._stable_sha(second)
    assert checker._stable_sha(first) != checker._stable_sha(third)
    record = {
        "architecture": dict(first["architecture"], fine_owned_mpc_slave_count=2),
        "matrices": {
            "same_physical_mesh": True,
            "fine": dict(matrix_facts["fine"], local_rows=7, local_cols=7),
            "coarse": dict(matrix_facts["coarse"], local_rows=7, local_cols=7),
        },
        "material": material,
    }
    provenance = {
        "operator_identity_authority": first,
        "operator_identity_sha256": checker._stable_sha(first),
        "input_identity_sha256": "input",
        "physical_model_sha256": checker._stable_sha(
            {"input_identity_sha256": "input", "coefficient_audit": {
                "cell_counts": {"air": 1},
                "positive_coefficients": material["positive_coefficients"],
                "global_cell_count": 1,
            }}
        ),
        "rank_facts": {"fine_owned_mpc_slave_count": 2},
    }
    errors: list[str] = []
    checker._check_matrix_and_identity(record, provenance, errors)
    assert errors == []
    bad_provenance = dict(
        provenance, rank_facts={"fine_owned_mpc_slave_count": 3}
    )
    errors = []
    checker._check_matrix_and_identity(record, bad_provenance, errors)
    assert any("rank-local owned-slave fact" in error for error in errors)


def test_krylov_fixed_cycle_matvec_and_pc_ledger():
    settings = {
        "ksp_type": "gmres",
        "pc_side": "right",
        "norm_type": "unpreconditioned",
        "restart": 20,
        "cycle_max_it": 20,
        "max_it": 10_000,
        "start_iteration": 0,
        "residual_limit": 1.0e-8,
        "residual_replacement": True,
        "first_checkpoint_iteration": 500,
        "checkpoint_interval": 500,
        "initial_guess_nonzero": False,
    }
    cycle0 = {
        "cycle_index": 0,
        "start_iteration": 0,
        "end_iteration": 20,
        "iterations": 20,
        "initial_guess_nonzero": False,
        "explicit_true_residual": 0.5,
        "reported_final_residual": 0.5,
        "ksp_destroyed": True,
        "matvec_count": 20,
        "pc_apply_count": 21,
        "resource": {"scope": "rank-root-diagnostic"},
        "reason": 1,
    }
    cycle1 = dict(cycle0)
    cycle1.update(
        cycle_index=1,
        start_iteration=20,
        end_iteration=30,
        iterations=10,
        initial_guess_nonzero=True,
        explicit_true_residual=0.0,
        reported_final_residual=0.0,
        matvec_count=11,
        pc_apply_count=11,
        reason=2,
    )
    krylov = {
        "settings": settings,
        "initial_true_residual": 1.0,
        "cycles": [cycle0, cycle1],
        "iterations": 30,
        "final_true_residual": 0.0,
        "reason": 2,
        "matvec_count": 31,
        "pc_apply_count": 32,
        "explicit_action_count": 3,
        "ksp_destroy_count": 2,
        "checkpoint_facts": [],
    }
    errors: list[str] = []
    gates: list[str] = []
    checker._check_krylov({"krylov": krylov}, None, errors, gates)
    assert not errors and not gates
    krylov["matvec_count"] = 32
    errors, gates = [], []
    checker._check_krylov({"krylov": krylov}, None, errors, gates)
    assert any("matvec_count" in error for error in errors)
    for missing in (False, True):
        malformed = dict(cycle1)
        if missing:
            malformed.pop("iterations")
        else:
            malformed["iterations"] = None
        bad_krylov = dict(krylov, cycles=[cycle0, malformed])
        errors, gates = [], []
        checker._check_krylov({"krylov": bad_krylov}, None, errors, gates)
        assert any("cycle interval" in error for error in errors)
