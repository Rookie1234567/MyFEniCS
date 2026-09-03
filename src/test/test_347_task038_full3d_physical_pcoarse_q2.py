"""Focused raw-contract tests for the V16 Q2 reference correction lane."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks import run_task038_full3d_physical_pcoarse_q2 as runner
from benchmarks import task038_full3d_physical_pcoarse_q2_checker as checker
import src.solvers.fullspace_memory_first_krylov as krylov
import src.solvers.fullspace_same_mesh_hcurl_pmg_physical as physical
import src.solvers.fullspace_same_mesh_hcurl_pmg_runtime as runtime
import src.solvers.fullspace_same_mesh_physical_pcoarse as pcoarse


SOURCE_SHA = "b" * 40


def _source() -> dict[str, object]:
    return {
        "commit_sha": SOURCE_SHA,
        "branch": checker.BRANCH,
        "upstream": f"origin/{checker.BRANCH}",
        "upstream_sha": SOURCE_SHA,
        "ahead": 0,
        "behind": 0,
        "tracked_worktree_clean": True,
        "qualified_activation": "1",
        "python_executable": "/repo/.venv/bin/python",
        "python_prefix": "/repo/.venv",
        "input_path": "/repo/input/templates/full3d_iterative_example.dat",
        "input_sha256": checker.INPUT_SHA256,
    }


def _vector(norm: float, token: str) -> dict[str, object]:
    return {
        "norm": norm,
        "finite": True,
        "owned_slave_max": 0.0,
        "array_sha256": token * 64,
    }


def _inner() -> dict[str, object]:
    cycle = {
        "cycle_index": 0,
        "start_iteration": 0,
        "end_iteration": 20,
        "iterations": 20,
        "reason": 1,
        "initial_guess_nonzero": False,
        "reported_final_residual": 5.0e-7,
        "explicit_true_residual": 5.0e-7,
        "matvec_count": 19,
        "pc_apply_count": 20,
        "wall_seconds": 0.1,
        "resource": {
            "process_tree": {"swap_bytes": 0, "all_status_readable": True},
            "job_no_swap": True,
            "memory_authority_bytes": 100_000,
        },
        "ksp_destroyed": True,
    }
    return {
        "settings": {
            "ksp_type": "fgmres",
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "restart": 20,
            "cycle_max_it": 20,
            "max_it": 10_000,
            "start_iteration": 0,
            "residual_limit": 1.0e-6,
            "residual_replacement": True,
            "initial_guess_nonzero": False,
            "first_checkpoint_iteration": None,
            "checkpoint_interval": 20,
        },
        "cycles": [cycle],
        "iterations": 20,
        "final_true_residual": 5.0e-7,
        "matvec_count": 19,
        "pc_apply_count": 20,
        "explicit_action_count": 2,
        "ksp_destroy_count": 1,
    }


def _worker_facts(cache: Path) -> dict[str, object]:
    residual = checker.CHECKPOINT_RESIDUAL
    vectors = {
        "checkpoint_solution": _vector(1.0, "a"),
        "rhs_before": _vector(1.0, "b"),
        "rhs_after": _vector(1.0, "b"),
        "r6_before": _vector(residual, "c"),
        "r6_after": _vector(residual, "c"),
        "r6_new": _vector(residual * 0.1, "d"),
        "r3_before": _vector(1.0, "e"),
        "r3_after": _vector(1.0, "e"),
        "r3_new": _vector(0.01, "f"),
        "correction": _vector(0.2, "g"),
    }
    inner = _inner()
    operations = {
        "p6_action": {"before": 0, "after": 2, "delta": 2},
        "p3_action": {"before": 0, "after": 21, "delta": 21, "expected_from_inner": 21},
        "lower_cycle": {"before": 0, "after": 20, "delta": 20, "expected_from_inner": 20},
        "p63": {"primal": 1, "adjoint": 2},
    }
    return {
        "input_facts": {
            "template_relative_path": "input/templates/full3d_iterative_example.dat",
            "template_sha256": checker.INPUT_SHA256,
            "resolved_config_sha256": checker.RESOLVED_CONFIG_SHA256,
            "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256,
        },
        "checkpoint_authority": {
            "manifest_sha256": checker.CHECKPOINT_MANIFEST_SHA256,
            "solution_sha256": checker.CHECKPOINT_SOLUTION_SHA256,
            "source_sha": checker.CHECKPOINT_SOURCE_SHA,
        },
        "provenance": {
            "input_sha256": checker.INPUT_SHA256,
            "resolved_config_sha256": checker.RESOLVED_CONFIG_SHA256,
            "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256,
            "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256,
        },
        "architecture": {
            "p6_pre_post_smoother": False,
            "global_physical_aij": False,
            "dense_dtn": False,
            "physical_factor": False,
            "numeric_allgather": False,
            "p3_positive_pc": "setup_owned_lower_cycle",
        },
        "p63_transfer": {
            "pair_fine_to_coarse": [6, 3],
            "global_transfer_matrix": False,
            "numeric_allgather": False,
            "static_condensation": False,
        },
        "actions": {
            "p6": {
                "global_aij_materialized": False,
                "global_schur_materialized": False,
                "ksp_created": False,
                "numeric_allgather": False,
                "t4_transmission_included": False,
                "apply_count": 2,
            },
            "p3": {
                "global_aij_materialized": False,
                "global_schur_materialized": False,
                "ksp_created": False,
                "numeric_allgather": False,
                "t4_transmission_included": False,
                "apply_count": 21,
            },
        },
        "rhs": {
            "degree": 6,
            "role": "physical_maxwell_rhs",
            "mode_manifest_sha256": checker.MODE_MANIFEST_SHA256,
        },
        "vectors": vectors,
        "inner": inner,
        "checkpoint": {
            "manifest_sha256": checker.CHECKPOINT_MANIFEST_SHA256,
            "restored_shard_sha256": checker.CHECKPOINT_SOLUTION_SHA256,
            "recomputed_residual": residual,
            "reproduction_relative": 0.0,
        },
        "correction": {
            "formula": "r6_new=r6-A6*P63*e3; r3_new=P63^H*r6_new",
            "rho_ref": 0.1,
            "rho3": 0.01,
            "projected_full_constraint_residual": 0.0,
            "algebraic_owned_slave_max": 0.0,
            "finite": True,
            "upper_cycle_apply_count_before": 0,
            "upper_cycle_apply_count_after": 0,
            "upper_cycle_apply_count_delta": 0,
            "p6_smoother_apply_count": 0,
            "physical_pcycle_applied": False,
            "operation_counts": operations,
        },
        "input_unchanged": {
            "checkpoint_solution_relative": 0.0,
            "rhs_relative": 0.0,
            "r6_relative": 0.0,
            "r3_relative": 0.0,
        },
    }


def _sample(stage: str, exit_code: int | None = None) -> dict[str, object]:
    return {
        "schema": checker.PROCESS_SCHEMA,
        "stage": stage,
        "exit_code": exit_code,
        "rss_bytes": 100_000,
        "swap_bytes": 0,
        "all_status_readable": True,
        "compiler_descendant_count": 0,
    }


def _result(stage: str) -> dict[str, object]:
    return {
        "stage": stage,
        "argv": ["synthetic"],
        "returncode": 0,
        "stop_reason": None,
        "signals": [],
        "sample_count": 1,
        "peak_rss_bytes": 100_000,
        "max_swap_bytes": 0,
        "all_status_readable": True,
        "process_group_gone": True,
        "lifecycle_failure": False,
        "warning_crossed": False,
        "rss_watchdog_bytes": checker.RSS_WATCHDOG,
    }


def _empty_cache_hash(cache: Path) -> str:
    value = {"cache_dir": str(cache), "artifacts": [], "artifact_count": 0}
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(payload).hexdigest()


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n")


def _artifact(tmp_path: Path) -> Path:
    root = tmp_path / "q2"
    cache = root / "jit_cache"
    children = root / "children"
    raw = root / "raw"
    markers = root / "markers"
    for path in (cache, children, raw, markers):
        path.mkdir(parents=True)
    (cache / "form.c").write_bytes(b"q2")
    for index, group in enumerate(checker.JIT_GROUPS):
        _write(children / f"{index:02d}_{group.replace('-', '_')}.json", {})

    process_path = root / "parent_process.jsonl"
    stages = [f"precompile:{group}" for group in checker.JIT_GROUPS] + ["worker"]
    with process_path.open("w", encoding="utf-8") as stream:
        for stage in stages:
            stream.write(json.dumps(_sample(stage), separators=(",", ":")) + "\n")
            stream.write(json.dumps(_sample(stage, 0), separators=(",", ":")) + "\n")

    children_facts = []
    for index, group in enumerate(checker.JIT_GROUPS):
        item = _result(f"precompile:{group}")
        item.update({"group": group, "record": f"children/{index:02d}_{group.replace('-', '_')}.json"})
        children_facts.append(item)
    worker_result = _result("worker")
    worker_result.update(
        {
            "record_present": True,
            "record_sha256": "pending",
            "stdout_sha256": "pending",
            "stderr_sha256": "pending",
        }
    )
    stdout = root / "worker.stdout.log"
    stderr = root / "worker.stderr.log"
    stdout.write_bytes(b"")
    stderr.write_bytes(b"")
    cache_initial = {"artifact_count": 0, "manifest_sha256": _empty_cache_hash(cache)}
    cache_current = checker._cache_snapshot(cache)
    worker_facts = _worker_facts(cache)
    worker = {
        "schema": checker.WORKER_SCHEMA,
        "raw_facts_only": True,
        "source": _source(),
        "runtime": {
            "mpi_size": 1,
            "petsc_scalar_type": "complex128",
            "petsc_int_type": "int32",
            "threads": {"OMP_NUM_THREADS": "1"},
        },
        "facts": worker_facts,
        "cache": {
            "path": "jit_cache",
            "xdg_cache_home": str(cache.resolve()),
            "binding": True,
            "snapshot": cache_current,
        },
        "paths": {"cache_dir": "jit_cache", "record": "raw/worker_record.json"},
    }
    worker_path = raw / "worker_record.json"
    _write(worker_path, worker)
    worker_result["record_sha256"] = checker._sha256(worker_path)
    worker_result["stdout_sha256"] = checker._sha256(stdout)
    worker_result["stderr_sha256"] = checker._sha256(stderr)

    marker_base = {"phase": checker.PHASE, "workflow": checker.WORKFLOW, "source_sha": SOURCE_SHA, "mpi_size": 1}
    for index, name in enumerate(checker.MARKER_ORDER):
        facts = dict(marker_base)
        if name == "inner_complete":
            facts.update({
                "iterations": 20,
                "final_true_residual": 5.0e-7,
                "matvec_count": 19,
                "pc_apply_count": 20,
                "ksp_destroy_count": 1,
                "restart_workspace_destroyed": True,
            })
        marker = {"schema": checker.MARKER_SCHEMA, "name": name, "marker_index": index, "facts": facts}
        _write(markers / f"{index:03d}_{name}.json", marker)
    marker_rows = [
        {"name": name, "sha256": checker._sha256(markers / f"{index:03d}_{name}.json")}
        for index, name in enumerate(checker.MARKER_ORDER)
    ]
    marker_manifest = root / "marker_manifest.json"
    _write(marker_manifest, marker_rows)

    parent = {
        "schema": checker.PARENT_SCHEMA,
        "source": _source(),
        "workflow": checker.WORKFLOW,
        "phase": checker.PHASE,
        "expected_mpi_size": 1,
        "rss_watchdog_bytes": checker.RSS_WATCHDOG,
        "staging_rss_watchdog_bytes": checker.RSS_WATCHDOG,
        "paths": {
            "jit_cache": "jit_cache",
            "process_samples": "parent_process.jsonl",
            "worker_record": "raw/worker_record.json",
            "marker_manifest": "marker_manifest.json",
        },
        "checkpoint_authority": {
            "manifest_sha256": checker.CHECKPOINT_MANIFEST_SHA256,
            "solution_sha256": checker.CHECKPOINT_SOLUTION_SHA256,
            "source_sha": checker.CHECKPOINT_SOURCE_SHA,
        },
        "jit_groups": list(checker.JIT_GROUPS),
        "cache": {"initial": cache_initial, "before_worker": cache_current, "after_worker": cache_current},
        "children": children_facts,
        "process": {
            "sample_count": 16,
            "peak_rss_bytes": 100_000,
            "max_swap_bytes": 0,
            "all_status_readable": True,
        },
        "worker": worker_result,
        "markers": {
            "manifest_relative_path": "marker_manifest.json",
            "manifest_sha256": checker._sha256(marker_manifest),
            "names": list(checker.MARKER_ORDER),
        },
        "error": None,
    }
    parent_path = root / "parent_record.json"
    _write(parent_path, parent)
    return parent_path


def test_q2_raw_artifact_passes_and_recomputes_operation_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(checker, "_check_checkpoint", lambda: None)
    result = checker.check_artifact(_artifact(tmp_path), SOURCE_SHA)
    assert result["passed"], result
    operations = result["metrics"]["operations"]
    assert operations["p6_action"]["delta"] == 2
    assert operations["p3_action"]["delta"] == 19 + 2
    assert operations["lower_cycle"]["delta"] == 20
    assert operations["p63"] == {"primal": 1, "adjoint": 2}


@pytest.mark.parametrize(
    ("mutation", "classification"),
    (
        ("residual", "Q2_PHYSICAL_PCOARSE_REFERENCE_NUMERICAL_GATE_FAIL"),
        ("constraint", "Q2_PHYSICAL_PCOARSE_REFERENCE_NUMERICAL_GATE_FAIL"),
        ("cache", "INFRASTRUCTURE_FAILURE_RETRYABLE"),
    ),
)
def test_q2_core_mutations_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    classification: str,
) -> None:
    monkeypatch.setattr(checker, "_check_checkpoint", lambda: None)
    parent_path = _artifact(tmp_path)
    parent = json.loads(parent_path.read_text())
    if mutation in {"residual", "constraint"}:
        worker_path = parent_path.parent / "raw/worker_record.json"
        worker = json.loads(worker_path.read_text())
        if mutation == "residual":
            worker["facts"]["inner"]["final_true_residual"] = 2.0e-6
        else:
            worker["facts"]["correction"]["projected_full_constraint_residual"] = "nan"
        _write(worker_path, worker)
        parent["worker"]["record_sha256"] = checker._sha256(worker_path)
    else:
        parent["cache"]["after_worker"] = {"artifact_count": 99, "manifest_sha256": "0" * 64}
    _write(parent_path, parent)
    result = checker.check_artifact(parent_path, SOURCE_SHA)
    assert result["classification"] == classification, result
    assert result["passed"] is False


def test_q2_marker_callback_keeps_inner_history_out_of_marker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[dict[str, object]] = []

    def capture(_comm: object, _marker_dir: Path, name: str, _source_sha: str, **facts: object) -> None:
        if name == "inner_complete":
            seen.append(facts)

    monkeypatch.setattr(runner, "_worker_marker", capture)
    callback = runner._marker_callback(object(), tmp_path, SOURCE_SHA)
    callback("inner_complete", _inner())
    assert seen and "cycles" not in seen[0] and "history" not in seen[0]
    assert seen[0]["restart_workspace_destroyed"] is True


def test_q2_import_boundary_and_fixed_watchdog() -> None:
    assert runner.RSS_SOLVER_WATCHDOG == runner.RSS_STAGING_WATCHDOG == 1_950_000_000
    assert checker.CHECKPOINT_RELATIVE == Path(
        "benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/"
        "j5_full_cold_staged_v3/ee5920b9fa977a39fea7bc09cfbe155303acdb2d/"
        "checkpoints/checkpoint-1000"
    )
    assert len(checker.CHECKPOINT_MANIFEST_SHA256) == 64
    assert len(checker.CHECKPOINT_SOLUTION_SHA256) == 64
    source = Path(checker.__file__).read_text(encoding="utf-8")
    assert "petsc4py" not in source
    assert "dolfinx" not in source
    assert "mpi4py" not in source
    assert "run_task038_full3d_physical_pcoarse_q2" not in source
    assert "src.solvers" not in source
    assert sys.modules.get("petsc4py") is None or "petsc4py" not in source


def test_q2_core_reference_chain_skips_upper_cycle(monkeypatch: pytest.MonkeyPatch) -> None:
    destroyed_final: list[object] = []

    class Vec:
        def __init__(self, values: object) -> None:
            self.array = np.asarray(values, dtype=np.complex128).copy()
            self.destroyed = False

        def copy(self, target: object = None) -> object:
            if target is None:
                return Vec(self.array)
            target.array[:] = self.array
            return None

        def duplicate(self) -> object:
            return Vec(np.zeros_like(self.array))

        def axpy(self, scale: complex, other: object) -> None:
            self.array[:] += scale * other.array

        def norm(self) -> float:
            return float(np.linalg.norm(self.array))

        def getArray(self, readonly: bool = False) -> np.ndarray:
            return self.array

        def getOwnershipRange(self) -> tuple[int, int]:
            return 0, self.array.size

        def getLocalSize(self) -> int:
            return int(self.array.size)

        def getSize(self) -> int:
            return int(self.array.size)

        def destroy(self) -> None:
            assert not self.destroyed
            self.destroyed = True

    class Comm:
        rank = 0
        size = 1

        def tompi4py(self) -> object:
            return self

        def allreduce(self, value: object, op: object = None) -> object:
            return value

    class Matrix:
        def __init__(self) -> None:
            self.comm = Comm()

        def getComm(self) -> Comm:
            return self.comm

        def getSize(self) -> tuple[int, int]:
            return 2, 2

        def getLocalSize(self) -> tuple[int, int]:
            return 2, 2

        def createVecRight(self) -> Vec:
            return Vec([0.0, 0.0])

        def createVecLeft(self) -> Vec:
            return Vec([0.0, 0.0])

    class Action:
        def __init__(self) -> None:
            self.audit = {"apply_count": 0}
            self.inputs: list[np.ndarray] = []

        def apply(self, source: Vec, target: Vec) -> None:
            self.inputs.append(source.array.copy())
            target.array[:] = 2.0 * source.array
            self.audit["apply_count"] += 1

    class Transfer:
        def __init__(self) -> None:
            self.adjoint_inputs: list[np.ndarray] = []
            self.primal_inputs: list[np.ndarray] = []

        def apply_adjoint_into(self, source: Vec, target: Vec) -> None:
            self.adjoint_inputs.append(source.array.copy())
            source.copy(target)

        def apply_primal_into(self, source: Vec, target: Vec) -> None:
            self.primal_inputs.append(source.array.copy())
            source.copy(target)

    class Mpc:
        def __init__(self) -> None:
            index_map = SimpleNamespace(size_local=2)
            self.function_space = SimpleNamespace(
                dofmap=SimpleNamespace(index_map=index_map, index_map_bs=1)
            )
            self.slaves = np.array([], dtype=np.int64)

        def homogenize(self, field: object) -> None:
            return None

    class Lower:
        def __init__(self) -> None:
            self.apply_count = 0

        def apply(self, source: Vec) -> Vec:
            self.apply_count += 1
            return source.copy()

    p6_matrix = Matrix()
    p3_matrix = Matrix()
    p6_action = Action()
    p3_action = Action()
    transfer = Transfer()
    lower = Lower()
    p6_mpc = Mpc()
    p3_mpc = Mpc()
    setup = {
        "p6_shell": SimpleNamespace(matrix=p6_matrix),
        "p3_matrix": p3_matrix,
        "floquets": {
            6: SimpleNamespace(mpc=p6_mpc),
            3: SimpleNamespace(mpc=p3_mpc),
        },
        "upper_cycle": SimpleNamespace(apply_count=0),
        "lower_cycle": lower,
        "p63_owner_transfer": transfer,
    }

    def restore(_path: Path, solution: Vec, **_kwargs: object) -> dict[str, int]:
        solution.array[:] = [1.0, 2.0]
        return {"iteration": 1000}

    def build_rhs(_bundle: object) -> tuple[Vec, dict[str, int]]:
        return Vec([4.0, 6.0]), {"degree": 6}

    def fake_restart(rhs: Vec, apply_action: object, pc: object, **kwargs: object) -> dict[str, object]:
        assert kwargs["max_it"] == 10_000
        assert kwargs["residual_limit"] == 1.0e-6
        assert kwargs["start_iteration"] == 0
        assert kwargs["checkpoint_writer"] is None
        assert kwargs["first_checkpoint_iteration"] is None
        assert kwargs["checkpoint_interval"] == 20
        assert kwargs["stop_on_true_residual"] is True
        assert kwargs["ksp_type"] == "fgmres"
        assert "initial_guess_nonzero" not in kwargs
        for _ in range(5):
            value = apply_action(rhs)
            value.destroy()
        for _ in range(2):
            value = pc(rhs)
            value.destroy()
        return {
            "final_solution": Vec([0.5, 0.25]),
            "cycles": [{"cycle_index": 0}],
            "iterations": 20,
            "final_true_residual": 5.0e-7,
            "matvec_count": 3,
            "pc_apply_count": 2,
            "explicit_action_count": 2,
            "ksp_destroy_count": 1,
        }

    def destroy_inner(result: dict[str, object]) -> None:
        result["final_solution"].destroy()
        destroyed_final.append(result["final_solution"])

    class FakeX:
        def __init__(self) -> None:
            self.petsc_vec = Vec([0.0, 0.0])

        def scatter_forward(self) -> None:
            return None

    class FakeFunction:
        def __init__(self, _space: object) -> None:
            self.x = FakeX()

    from dolfinx import fem

    monkeypatch.setattr(krylov, "read_solution_checkpoint", restore)
    monkeypatch.setattr(pcoarse, "run_restart20_cycles", fake_restart)
    monkeypatch.setattr(pcoarse, "destroy_krylov_result", destroy_inner)
    monkeypatch.setattr(physical, "build_physical_rhs", build_rhs)
    monkeypatch.setattr(runtime, "_mpc_constraint_residual", lambda *_args: 0.0)
    monkeypatch.setattr(runtime, "_slave_storage_max", lambda *_args: 0.0)
    monkeypatch.setattr(fem, "Function", FakeFunction)

    result = pcoarse.solve_reference_checkpoint_correction(
        {"degree": 6, "setup": setup, "physical_action": p6_action},
        {"degree": 3, "action": p3_action},
        Path("unused"),
        {"explicit_true_residual": 0.5},
        resource_sample=None,
    )

    np.testing.assert_allclose(transfer.adjoint_inputs, [[2.0, 2.0], [1.0, 1.5]])
    np.testing.assert_allclose(transfer.primal_inputs, [[0.5, 0.25]])
    np.testing.assert_allclose(p6_action.inputs, [[1.0, 2.0], [0.5, 0.25]])
    assert p6_action.audit["apply_count"] == 2
    assert p3_action.audit["apply_count"] == 5
    assert lower.apply_count == 2
    assert setup["upper_cycle"].apply_count == 0
    assert destroyed_final and destroyed_final[0].destroyed
    assert result["correction"]["operation_counts"] == {
        "p6_action": {"before": 0, "after": 2, "delta": 2},
        "p3_action": {
            "before": 0,
            "after": 5,
            "delta": 5,
            "expected_from_inner": 5,
        },
        "lower_cycle": {
            "before": 0,
            "after": 2,
            "delta": 2,
            "expected_from_inner": 2,
        },
        "p63": {"primal": 1, "adjoint": 2},
    }
    assert result["vectors"]["r6_before"]["norm"] == pytest.approx(np.linalg.norm([2.0, 2.0]))
    assert result["vectors"]["r6_new"]["norm"] == pytest.approx(np.linalg.norm([1.0, 1.5]))
    assert result["correction"]["upper_cycle_apply_count_delta"] == 0
