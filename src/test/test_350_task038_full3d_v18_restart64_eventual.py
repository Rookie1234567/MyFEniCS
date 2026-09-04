"""Focused contracts for the V18 eventual restart-64 lane."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks import run_task038_v18_restart64_eventual as runner
from benchmarks import task038_v18_restart64_eventual_checker as checker

FROZEN_MODE_MANIFEST_SHA256 = (
    "dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _array_sha(values: np.ndarray) -> str:
    return hashlib.sha256(memoryview(np.ascontiguousarray(values)).cast("B")).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _descriptor(root: Path, relative: str, values: np.ndarray) -> dict[str, object]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        np.save(stream, np.asarray(values, dtype=np.complex128), allow_pickle=False)
    values = np.asarray(values, dtype=np.complex128)
    return {
        "relative_path": relative,
        "bytes": path.stat().st_size,
        "sha256": _sha256(path),
        "array_sha256": _array_sha(values),
        "dtype": "complex128",
        "shape": [int(values.size)],
    }


def _source(source_sha: str) -> dict[str, object]:
    return {
        "commit_sha": source_sha,
        "branch": checker.BRANCH,
        "upstream": f"origin/{checker.BRANCH}",
        "upstream_sha": source_sha,
        "input_sha256": checker.INPUT_SHA256,
        "template_sha256": checker.INPUT_SHA256,
        "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256,
        "mode_manifest_sha256": FROZEN_MODE_MANIFEST_SHA256,
        "ahead": 0,
        "behind": 0,
        "tracked_worktree_clean": True,
        "qualified_activation": "1",
    }


def _stage(initial: float = 1.0e-7) -> dict[str, object]:
    cycle = {
        "start_iteration": 0,
        "end_iteration": 64,
        "iterations": 64,
        "additional_iteration": 64,
        "absolute_iteration": 1064,
        "matvec_count": 1,
        "pc_apply_count": 1,
        "reason": 1,
        "explicit_true_residual": initial,
        "ksp_destroyed": True,
        "resource": {"process_tree": {"rss_bytes": 100, "swap_bytes": 0}},
    }
    return {
        "stage": "e2",
        "phase": "e2",
        "base_offset": 0,
        "local_iterations": 64,
        "additional_iterations": 64,
        "absolute_end_iteration": 1064,
        "initial_true_residual": initial,
        "final_true_residual": initial,
        "matvec_count": 1,
        "pc_apply_count": 1,
        "explicit_action_count": 2,
        "ksp_destroy_count": 1,
        "elapsed_seconds": 0.0,
        "settings": {
            "ksp_type": "fgmres",
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "restart": 64,
            "cycle_max_it": 64,
            "max_it": 32768,
            "start_iteration": 0,
            "residual_limit": 1.0e-6,
            "residual_replacement": True,
            "initial_guess_nonzero": False,
            "first_checkpoint_iteration": None,
            "checkpoint_interval": 1024,
            "additional_iteration_origin": 0,
            "absolute_iteration_origin": 1000,
            "stage_base_offset": 0,
        },
        "cycles": [cycle],
        "checkpoint_facts": [],
        "stagnation": runner._stagnation_facts(initial, [cycle], 0),
    }


def _make_artifact(tmp_path: Path, source_sha: str = "a" * 40) -> tuple[Path, Path]:
    root = tmp_path / "artifact"
    raw = root / "raw"
    cache = root / "jit_cache"
    cache.mkdir(parents=True)
    rhs = np.asarray([1.0 + 0.0j, 0.0 + 0.0j], dtype=np.complex128)
    initial = np.zeros(2, dtype=np.complex128)
    action = np.asarray([0.9999999 + 0.0j, 0.0 + 0.0j], dtype=np.complex128)
    residual = rhs - action
    rhs_desc = _descriptor(root, "raw/same_start/rhs.npy", rhs)
    initial_desc = _descriptor(root, "raw/same_start/initial_solution.npy", initial)
    action_desc = _descriptor(root, "raw/restore/action.npy", action)
    residual_desc = _descriptor(root, "raw/restore/residual.npy", residual)
    action_first = _descriptor(root, "raw/probes/action_first.npy", action)
    action_second = _descriptor(root, "raw/probes/action_second.npy", action)
    pc_first = _descriptor(root, "raw/probes/pc_first.npy", np.zeros(2, dtype=np.complex128))
    pc_second = _descriptor(root, "raw/probes/pc_second.npy", np.zeros(2, dtype=np.complex128))
    facts = {"finite": True, "owned_slave_max": 0.0, "owned_slave_count": 0}
    probe = {
        "input_before_sha256": _array_sha(initial),
        "input_after_sha256": _array_sha(initial),
        "repeat_relative": 0.0,
        "first": action_first,
        "second": action_second,
        "dual_facts": facts,
    }
    pc_probe = {
        "input_role": "dual_residual",
        "input_before_sha256": _array_sha(residual),
        "input_after_sha256": _array_sha(residual),
        "repeat_relative": 0.0,
        "first": pc_first,
        "second": pc_second,
        "input_facts": facts,
        "primal_facts": facts,
    }
    stage = _stage()
    worker = {
        "schema": checker.WORKER_SCHEMA,
        "workflow": checker.WORKFLOW,
        "phase": "e2",
        "worker_stage": "worker",
        "source": _source(source_sha),
        "input": {"template_sha256": checker.INPUT_SHA256, "mode_manifest_sha256": FROZEN_MODE_MANIFEST_SHA256},
        "checkpoint": None,
        "rhs": {"finite": True, "owned_slave_max": 0.0, "owned_slave_count": 0},
        "same_start": {
            "rhs": rhs_desc,
            "initial_solution": initial_desc,
            "rhs_before_sha256": rhs_desc["array_sha256"],
            "rhs_after_sha256": rhs_desc["array_sha256"],
            "initial_solution_before_sha256": initial_desc["array_sha256"],
            "initial_solution_after_sha256": initial_desc["array_sha256"],
            "input_unchanged": True,
            "finite": True,
            "initial_true_residual": 1.0e-7,
        },
        "probes": {"action": probe, "pc": pc_probe},
        "restore": {
            "expected": None,
            "actual": 1.0e-7,
            "relative_difference": None,
            "relative_limit": None,
            "rhs_descriptor": rhs_desc,
            "action_descriptor": action_desc,
            "residual_descriptor": residual_desc,
            "finite": True,
        },
        "stage": stage,
        "gates": {"pre_stage": [], "classification": "E2_FRESH_PHYSICAL_NUMERICAL_PASS"},
        "architecture": {
            "physical_operator": "p6_matrix_free_split_volume_plus_streaming_dtn",
            "global_physical_aij": False,
            "global_schur": False,
            "dense_dtn": False,
            "factor": False,
            "numeric_allgather": False,
            "phase_once": True,
            "restart_basis_storage": "petsc_in_memory",
            "restart": 64,
        },
        "lifecycle": {"marker_order": list(runner.MARKER_ORDER["e2"])},
    }
    worker_path = root / "raw/worker_record.json"
    _write_json(worker_path, worker)
    child_rows = []
    for index, group in enumerate(checker.JIT_GROUPS):
        path = root / f"children/{index}.json"
        _write_json(path, {})
        child_rows.append(
            {
                "group": group,
                "stage": f"precompile:{group}",
                "record": str(path.relative_to(root)),
                "record_sha256": _sha256(path),
                "returncode": 0,
                "stop_reason": None,
                "signals": [],
                "sample_count": 1,
                "peak_rss_bytes": 100,
                "max_swap_bytes": 0,
                "all_status_readable": True,
                "process_group_gone": True,
                "lifecycle_failure": False,
                "rss_watchdog_bytes": checker.RSS_HARD,
            }
        )
    marker_names = list(runner.MARKER_ORDER["e2"])
    marker_rows = []
    for index, name in enumerate(marker_names):
        path = root / f"markers/{index:02d}_{name}.json"
        _write_json(path, {})
        marker_rows.append(
            {"name": name, "relative_path": str(path.relative_to(root)), "sha256": _sha256(path)}
        )
    marker_manifest = root / "marker_manifest.json"
    _write_json(marker_manifest, marker_rows)
    timeline = root / "parent_process.jsonl"
    lines = []
    for stage_name in [f"precompile:{group}" for group in checker.JIT_GROUPS] + ["worker"]:
        lines.append(
            json.dumps(
                {"stage": stage_name, "rss_bytes": 100, "swap_bytes": 0, "all_status_readable": True, "compiler_descendant_count": 0},
                separators=(",", ":"),
            )
        )
    timeline.write_text("\n".join(lines) + "\n", encoding="utf-8")
    parent = {
        "schema": checker.PARENT_SCHEMA,
        "workflow": checker.WORKFLOW,
        "phase": "e2",
        "source": _source(source_sha),
        "expected_mpi_size": 1,
        "resource_contract": {"warning_bytes": 1_800_000_000, "rss_watchdog_bytes": checker.RSS_HARD, "rss_hard_gate_bytes": checker.RSS_HARD, "swap_hard_gate_bytes": 0},
        "paths": {
            "process_samples": "parent_process.jsonl",
            "marker_manifest": "marker_manifest.json",
            "jit_cache": "jit_cache",
            "children": "children",
            "e0_checkpoint_preflight": None,
            "e0_checkpoint_preflight_sha256": None,
        },
        "jit_groups": list(checker.JIT_GROUPS),
        "children": child_rows,
        "worker": {
            "stage": "worker",
            "record": "raw/worker_record.json",
            "record_sha256": _sha256(worker_path),
            "returncode": 0,
            "stop_reason": None,
            "signals": [],
            "sample_count": 1,
            "peak_rss_bytes": 100,
            "max_swap_bytes": 0,
            "all_status_readable": True,
            "process_group_gone": True,
            "lifecycle_failure": False,
            "rss_watchdog_bytes": checker.RSS_HARD,
        },
        "cache": {
            "initial": checker._cache_snapshot(cache),
            "before_worker": checker._cache_snapshot(cache),
            "after_worker": checker._cache_snapshot(cache),
        },
        "process": {"sample_count": 8, "peak_rss_bytes": 100, "max_swap_bytes": 0, "all_status_readable": True},
        "markers": {"rows": marker_rows, "sha256": _sha256(marker_manifest)},
        "e0": None,
        "classification": "RAW_COMPLETE_PENDING_CHECKER",
        "error": None,
    }
    parent_path = root / "parent_record.json"
    _write_json(parent_path, parent)
    return parent_path, worker_path


def _refresh_worker_hash(parent_path: Path, worker_path: Path) -> None:
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    parent["worker"]["record_sha256"] = _sha256(worker_path)
    _write_json(parent_path, parent)


def test_eventual_iteration_identity_and_two_complete_stagnation_blocks() -> None:
    cycles = [
        {"end_iteration": 4096, "explicit_true_residual": 0.98},
        {"end_iteration": 8192, "explicit_true_residual": 0.97},
    ]
    one = runner._stagnation_facts(1.0, cycles[:1], 1024)
    two = runner._stagnation_facts(1.0, cycles, 1024)
    assert one["triggered"] is False
    assert two["triggered"] is True
    assert two["blocks"][0]["start_iteration"] == 0
    assert two["blocks"][0]["end_iteration"] == 4096
    assert two["blocks"][0]["start_additional_iteration"] == 1024
    assert two["blocks"][0]["end_additional_iteration"] == 5120
    assert two["blocks"][0]["start_absolute_iteration"] == 2024
    assert two["blocks"][0]["end_absolute_iteration"] == 6120
    assert two["blocks"][1]["start_additional_iteration"] == 5120
    assert two["blocks"][1]["end_additional_iteration"] == 9216
    assert two["blocks"][1]["start_absolute_iteration"] == 6120
    assert two["blocks"][1]["end_absolute_iteration"] == 10216


def test_eventual_stage_passes_real_start_residual_to_stop_callback(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from src.solvers import fullspace_memory_first_krylov as krylov

    observed: dict[str, object] = {}
    cycle = {"start_iteration": 0, "end_iteration": 64, "explicit_true_residual": 0.5}

    def fake_fixed(*args: object, **kwargs: object) -> dict[str, object]:
        stop = kwargs["stop_after_cycle"]
        observed["triggered_after_one_cycle"] = stop(cycle, [cycle])
        return {
            "initial_true_residual": 0.75,
            "final_true_residual": 0.5,
            "iterations": 64,
            "matvec_count": 1,
            "pc_apply_count": 1,
            "explicit_action_count": 2,
            "ksp_destroy_count": 1,
            "elapsed_seconds": 0.0,
            "settings": {"start_iteration": 0},
            "cycles": [cycle],
        }

    monkeypatch.setattr(krylov, "run_fixed_restart_cycles", fake_fixed)
    _result, facts = runner._stage_cycles(
        tmp_path / "raw",
        "e1",
        "e1",
        1024,
        31744,
        object(),
        object(),
        object(),
        object(),
        object(),
        "a" * 40,
        0.75,
    )
    assert observed["triggered_after_one_cycle"] is False
    assert facts["initial_true_residual"] == 0.75
    assert facts["stagnation"]["blocks"] == []


def test_eventual_stage_unlocks_and_restart20_remains_locked_to_old_contract() -> None:
    assert runner.stage_unlocks("E1_CHECKPOINT_CONTINUATION_PHYSICAL_NUMERICAL_PASS") == {
        "e2": True,
        "e3": False,
    }
    assert runner.stage_unlocks(
        "E1_CHECKPOINT_CONTINUATION_PHYSICAL_NUMERICAL_PASS",
        "E2_FRESH_PHYSICAL_NUMERICAL_PASS",
    )["e3"] is True
    assert runner.stage_unlocks("E1_PHYSICAL_STAGNATION") == {"e2": False, "e3": False}
    assert runner._stage_classification(
        {
            "final_true_residual": 1.0,
            "stagnation": {"triggered": False},
            "local_iterations": runner.E2_MAX_STEPS,
        },
        [],
        "e2",
    ) == "E2_FRESH_PHYSICAL_MAXIT_FAIL"


def test_eventual_checker_recomputes_raw_vectors_and_accepts_valid_numerical_result(tmp_path: Path) -> None:
    assert checker.MODE_MANIFEST_SHA256 == FROZEN_MODE_MANIFEST_SHA256
    parent_path, _worker_path = _make_artifact(tmp_path)
    result = checker.check_artifact(parent_path, "a" * 40)
    assert result["status"] == "PASS", result
    assert result["evidence_valid"] is True
    assert result["classification"] == "E2_FRESH_PHYSICAL_NUMERICAL_PASS"


def test_eventual_checker_reports_resource_as_valid_gate_not_infrastructure(tmp_path: Path) -> None:
    parent_path, worker_path = _make_artifact(tmp_path)
    worker = json.loads(worker_path.read_text(encoding="utf-8"))
    worker["stage"]["cycles"][0]["resource"]["process_tree"]["rss_bytes"] = checker.RSS_HARD
    _write_json(worker_path, worker)
    _refresh_worker_hash(parent_path, worker_path)
    result = checker.check_artifact(parent_path, "a" * 40)
    assert result["status"] == "PASS", result
    assert result["evidence_valid"] is True
    assert result["classification"] == "E2_RESOURCE_GATE_FAIL"
    assert result["errors"] == []
    assert result["metrics"]["gate_failures"]


def test_eventual_checker_rejects_source_or_raw_tamper(tmp_path: Path) -> None:
    parent_path, worker_path = _make_artifact(tmp_path)
    worker = json.loads(worker_path.read_text(encoding="utf-8"))
    worker["source"]["template_sha256"] = "bad"
    _write_json(worker_path, worker)
    _refresh_worker_hash(parent_path, worker_path)
    result = checker.check_artifact(parent_path, "a" * 40)
    assert result["status"] == "FAIL"
    assert result["evidence_valid"] is False
    assert result["classification"] == "INFRASTRUCTURE_FAILURE_RETRYABLE"


def test_eventual_checkpoint_authority_is_hash_bound_and_fail_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checkpoint = tmp_path / "checkpoint"
    checkpoint.mkdir()
    values = np.asarray([1.0 + 0.0j, 2.0 + 0.0j], dtype=np.complex128)
    shard = checkpoint / "solution_rank0.npy"
    np.save(shard, values, allow_pickle=False)
    manifest = {
        "schema": "fixed-memory-krylov.solution-checkpoint.v1",
        "iteration": 2024,
        "explicit_true_residual": checker.CHECKPOINT_EXPLICIT_RESIDUAL,
        "input_identity_sha256": checker.CHECKPOINT_INPUT_IDENTITY_SHA256,
        "operator_identity_sha256": checker.CHECKPOINT_OPERATOR_IDENTITY_SHA256,
        "physical_model_sha256": checker.PHYSICAL_MODEL_SHA256,
        "source_sha": checker.CHECKPOINT_SOURCE_SHA,
        "mpi_size": 1,
        "solution_only": True,
        "numeric_allgather": False,
        "vector_roles": ["solution"],
        "forbidden_vector_roles": ["action", "residual", "krylov_basis"],
        "ranks": [{
            "rank": 0,
            "ownership": {
                "rank": 0,
                "ownership_range": [0, 2],
                "local_size": 2,
                "global_size": 2,
            },
            "solution": {
                "relative_path": "solution_rank0.npy",
                "bytes": shard.stat().st_size,
                "sha256": _sha256(shard),
                "dtype": "complex128",
                "shape": [2],
            },
        }],
    }
    manifest_path = checkpoint / "manifest.json"
    _write_json(manifest_path, manifest)
    monkeypatch.setattr(checker, "CHECKPOINT_DIR", checkpoint)
    monkeypatch.setattr(checker, "CHECKPOINT_MANIFEST_SHA256", _sha256(manifest_path))
    monkeypatch.setattr(checker, "CHECKPOINT_SOLUTION_SHA256", _sha256(shard))
    errors: list[str] = []
    assert checker._check_checkpoint_authority(errors) is not None
    assert errors == []
    manifest["iteration"] = 2025
    _write_json(manifest_path, manifest)
    errors = []
    assert checker._check_checkpoint_authority(errors) is not None
    assert errors


def test_eventual_e0_checkpoint_preflight_blocks_jit_before_any_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    missing = runner.REPO_ROOT / "benchmarks/artifacts/task038_extra_full3d_iterative_0p7nm/_missing_e0_checkpoint_authority"
    monkeypatch.setattr(runner, "CHECKPOINT_DIR", missing)
    monkeypatch.setattr(runner, "_source_facts", lambda sha, _input: {"commit_sha": sha})
    monkeypatch.setattr(
        runner.authority_runner,
        "_run_parent_child",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("JIT child started")),
    )
    root = tmp_path / "e0-parent"
    record_path = root / "parent_record.json"
    assert runner._run_parent(root, record_path, "a" * 40, tmp_path / "input.dat", "e1") == 0
    parent = json.loads(record_path.read_text(encoding="utf-8"))
    assert parent["classification"] == "E0_BLOCKED_BY_CHECKPOINT_AUTHORITY"
    assert parent["jit_groups"] == []
    assert parent["children"] == []
    assert parent["worker"] is None
    assert parent["e0"]["valid"] is False
    assert (root / "e0_checkpoint_preflight.json").is_file()
    assert not (root / "children").exists()


def test_eventual_parent_binds_last_checker_completion_without_parent_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        runner,
        "_source_facts",
        lambda sha, _input: {
            "commit_sha": sha,
            "branch": runner.BRANCH,
            "upstream": f"origin/{runner.BRANCH}",
            "upstream_sha": sha,
        },
    )
    monkeypatch.setattr(
        runner.authority_runner,
        "_process_summary",
        lambda _path: {"sample_count": 0, "peak_rss_bytes": 0, "max_swap_bytes": 0, "all_status_readable": True},
    )
    calls: list[str] = []

    def fake_child(command: list[str], _sample: Path, stage: str, _stdout: Path, _stderr: Path, **_kwargs: object) -> dict[str, object]:
        calls.append(stage)
        if stage == "checker":
            output = Path(command[command.index("--output") + 1])
            _write_json(output, {"schema": runner.CHECKER_SCHEMA, "status": "PASS"})
        else:
            child_record = Path(command[command.index("--record") + 1])
            child_record.parent.mkdir(parents=True, exist_ok=True)
            _write_json(child_record, {})
        return {
            "returncode": 0,
            "stop_reason": None,
            "process_group_gone": True,
            "lifecycle_failure": False,
            "all_status_readable": True,
            "max_swap_bytes": 0,
            "peak_rss_bytes": 100,
            "rss_watchdog_bytes": runner.RSS_HARD,
        }

    monkeypatch.setattr(runner.authority_runner, "_run_parent_child", fake_child)
    root = tmp_path / "parent"
    record_path = root / "parent_record.json"
    assert runner._run_parent(root, record_path, "a" * 40, tmp_path / "input.dat", "e2") == 0
    assert calls == [*(f"precompile:{group}" for group in runner.JIT_GROUPS), "worker", "checker"]
    parent = json.loads(record_path.read_text(encoding="utf-8"))
    completion = json.loads((root / "completion.json").read_text(encoding="utf-8"))
    assert parent["paths"]["completion"] == "completion.json"
    assert parent["paths"]["e0_checkpoint_preflight"] is None
    assert parent["paths"]["e0_checkpoint_preflight_sha256"] is None
    assert parent["e0"] is None
    assert completion["parent_record_sha256"] == _sha256(record_path)
    assert completion["checker_sha256"] == _sha256(root / "checker.json")
    assert completion["status"] == "PASS"
    assert runner._checker_command(record_path, root / "checker.json", "a" * 40)[0] == runner.LEXICAL_PYTHON


@pytest.mark.parametrize("fault", ["lifecycle", "missing"])
def test_eventual_completion_requires_full_checker_lifecycle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    monkeypatch.setattr(
        runner,
        "_source_facts",
        lambda sha, _input: {
            "commit_sha": sha,
            "branch": runner.BRANCH,
            "upstream": f"origin/{runner.BRANCH}",
            "upstream_sha": sha,
        },
    )
    monkeypatch.setattr(
        runner.authority_runner,
        "_process_summary",
        lambda _path: {"sample_count": 0, "peak_rss_bytes": 0, "max_swap_bytes": 0, "all_status_readable": True},
    )

    def fake_child(command: list[str], _sample: Path, stage: str, _stdout: Path, _stderr: Path, **_kwargs: object) -> dict[str, object]:
        if stage == "checker" and fault != "missing":
            output = Path(command[command.index("--output") + 1])
            _write_json(output, {"schema": runner.CHECKER_SCHEMA, "status": "PASS"})
        elif stage != "checker":
            child_record = Path(command[command.index("--record") + 1])
            child_record.parent.mkdir(parents=True, exist_ok=True)
            _write_json(child_record, {})
        return {
            "returncode": 0,
            "stop_reason": None,
            "process_group_gone": True,
            "lifecycle_failure": fault == "lifecycle" and stage == "checker",
            "all_status_readable": True,
            "max_swap_bytes": 0,
            "peak_rss_bytes": 100,
            "rss_watchdog_bytes": runner.RSS_HARD,
        }

    monkeypatch.setattr(runner.authority_runner, "_run_parent_child", fake_child)
    root = tmp_path / fault
    record_path = root / "parent_record.json"
    assert runner._run_parent(root, record_path, "a" * 40, tmp_path / "input.dat", "e2") == 1
    completion = json.loads((root / "completion.json").read_text(encoding="utf-8"))
    assert completion["status"] == "FAIL"


def test_eventual_e2_unlock_requires_independent_checker_and_completion(
    tmp_path: Path,
) -> None:
    source_sha = "a" * 40
    parent_path = tmp_path / "parent_record.json"
    checker_path = tmp_path / "checker.json"
    completion_path = tmp_path / "completion.json"
    _write_json(
        parent_path,
        {
            "schema": runner.PARENT_SCHEMA,
            "workflow": runner.WORKFLOW,
            "phase": "e1",
            "source": _source(source_sha),
            "classification": "RAW_COMPLETE_PENDING_CHECKER",
            "paths": {"completion": "completion.json"},
        },
    )
    checker_result = {
        "schema": runner.CHECKER_SCHEMA,
        "status": "PASS",
        "evidence_valid": True,
        "classification": runner.E1_PASS_CLASSIFICATION,
        "errors": [],
        "record": str(parent_path),
        "record_sha256": _sha256(parent_path),
        "expected_source_sha": source_sha,
    }
    _write_json(checker_path, checker_result)
    _write_json(
        completion_path,
        {
            "schema": runner.COMPLETION_SCHEMA,
            "parent_record": parent_path.name,
            "parent_record_sha256": _sha256(parent_path),
            "checker": checker_path.name,
            "checker_sha256": _sha256(checker_path),
            "status": "PASS",
            "checker_process": {
                "returncode": 0,
                "stop_reason": None,
                "process_group_gone": True,
                "lifecycle_failure": False,
                "all_status_readable": True,
                "max_swap_bytes": 0,
                "peak_rss_bytes": 100,
                "rss_watchdog_bytes": runner.RSS_HARD,
            },
        },
    )
    assert runner._e1_checker_authority(checker_path, source_sha) is True
    checker_result["classification"] = "tampered"
    _write_json(checker_path, checker_result)
    completion = json.loads(completion_path.read_text(encoding="utf-8"))
    completion["checker_sha256"] = _sha256(checker_path)
    _write_json(completion_path, completion)
    assert runner._e1_checker_authority(checker_path, source_sha) is False


def test_eventual_pre_stage_facts_block_solve_for_invalid_inputs(
    tmp_path: Path,
) -> None:
    parent_path, worker_path = _make_artifact(tmp_path)
    worker = json.loads(worker_path.read_text(encoding="utf-8"))
    worker["probes"]["pc"]["input_before_sha256"] = "bad"
    worker["probes"]["pc"]["input_facts"]["finite"] = False
    worker["rhs"]["finite"] = False
    worker["same_start"]["finite"] = False
    worker["stage"] = None
    worker["gates"]["pre_stage"] = [
        "pc.input_unchanged",
        "pc.input_finite",
        "rhs.finite",
    ]
    worker["gates"]["classification"] = "E2_NUMERICAL_GATE_FAIL"
    _write_json(worker_path, worker)
    _refresh_worker_hash(parent_path, worker_path)
    result = checker.check_artifact(parent_path, "a" * 40)
    assert result["status"] == "PASS", result
    assert result["evidence_valid"] is True
    assert result["classification"] == "E2_NUMERICAL_GATE_FAIL"
    assert result["errors"] == []


def test_eventual_e2_parent_requires_checker_but_worker_does_not(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_sha = "a" * 40
    common = [
        "--phase",
        "e2",
        "--artifact-root",
        str(tmp_path / "root"),
        "--record",
        str(tmp_path / "root" / "parent_record.json"),
        "--source-sha",
        source_sha,
        "--input",
        str(tmp_path / "input.dat"),
        "--mpi-size",
        "1",
    ]
    monkeypatch.setattr(runner, "_e1_checker_authority", lambda *_args: False)
    with pytest.raises(RuntimeError, match="independent E1 checker"):
        runner.main([*common, "--mode", "parent"])

    authority_calls: list[tuple[object, object]] = []
    monkeypatch.setattr(
        runner,
        "_e1_checker_authority",
        lambda checker_path, expected_sha: authority_calls.append((checker_path, expected_sha)) or True,
    )
    monkeypatch.setattr(runner, "_run_parent", lambda *_args: 17)
    assert runner.main([*common, "--mode", "parent", "--e1-checker", str(tmp_path / "e1.json")]) == 17
    assert len(authority_calls) == 1

    worker_calls: list[object] = []
    monkeypatch.setattr(runner, "run_worker", lambda *args: worker_calls.append(args))
    assert runner.main([*common, "--mode", "worker"]) == 0
    assert len(authority_calls) == 1
    assert worker_calls


@pytest.mark.parametrize("stop_stage", ["jit", "worker"])
def test_eventual_resource_stop_prefix_is_valid_checker_evidence(
    tmp_path: Path, stop_stage: str
) -> None:
    parent_path, worker_path = _make_artifact(tmp_path / stop_stage)
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    root = parent_path.parent
    if stop_stage == "jit":
        child = parent["children"][0]
        child["stop_reason"] = "process_tree_rss_watchdog"
        child["returncode"] = -9
        child["peak_rss_bytes"] = checker.RSS_HARD
        child_record = root / child["record"]
        child_record.unlink()
        parent["children"] = [child]
        parent["worker"] = None
        timeline = root / parent["paths"]["process_samples"]
        timeline.write_text(
            json.dumps(
                {
                    "stage": "precompile:positive-p6",
                    "rss_bytes": checker.RSS_HARD,
                    "swap_bytes": 0,
                    "all_status_readable": True,
                    "compiler_descendant_count": 0,
                }
            )
            + "\n",
            encoding="utf-8",
        )
        parent["process"] = {
            "sample_count": 1,
            "peak_rss_bytes": checker.RSS_HARD,
            "max_swap_bytes": 0,
            "all_status_readable": True,
        }
    else:
        worker = parent["worker"]
        worker["stop_reason"] = "process_tree_rss_watchdog"
        worker["returncode"] = -9
        worker["peak_rss_bytes"] = checker.RSS_HARD
        worker_path.unlink()
        timeline = root / parent["paths"]["process_samples"]
        rows = [
            {
                "stage": f"precompile:{group}",
                "rss_bytes": 100,
                "swap_bytes": 0,
                "all_status_readable": True,
                "compiler_descendant_count": 0,
            }
            for group in checker.JIT_GROUPS
        ]
        rows.append(
            {
                "stage": "worker",
                "rss_bytes": checker.RSS_HARD,
                "swap_bytes": 0,
                "all_status_readable": True,
                "compiler_descendant_count": 0,
            }
        )
        timeline.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
        parent["process"] = {
            "sample_count": len(rows),
            "peak_rss_bytes": checker.RSS_HARD,
            "max_swap_bytes": 0,
            "all_status_readable": True,
        }
    parent["paths"]["marker_manifest"] = None
    parent["markers"] = {"rows": [], "sha256": None}
    _write_json(parent_path, parent)
    result = checker.check_artifact(parent_path, "a" * 40)
    assert result["status"] == "PASS", result
    assert result["evidence_valid"] is True
    assert result["classification"] == "E2_RESOURCE_GATE_FAIL"
    assert result["errors"] == []


@pytest.mark.parametrize("partial_iterations", [0, 32])
def test_eventual_checker_accepts_only_final_partial_or_zero_cycle(
    tmp_path: Path, partial_iterations: int
) -> None:
    parent_path, worker_path = _make_artifact(tmp_path)
    worker = json.loads(worker_path.read_text(encoding="utf-8"))
    stage = worker["stage"]
    cycle = stage["cycles"][0]
    cycle["end_iteration"] = partial_iterations
    cycle["iterations"] = partial_iterations
    cycle["additional_iteration"] = partial_iterations
    cycle["absolute_iteration"] = runner.ABSOLUTE_ORIGIN + partial_iterations
    cycle["reason"] = -5
    cycle["matvec_count"] = 0 if partial_iterations == 0 else 1
    cycle["pc_apply_count"] = 0 if partial_iterations == 0 else 1
    cycle["explicit_true_residual"] = 0.5
    stage["local_iterations"] = partial_iterations
    stage["additional_iterations"] = partial_iterations
    stage["absolute_end_iteration"] = runner.ABSOLUTE_ORIGIN + partial_iterations
    stage["final_true_residual"] = 0.5
    stage["matvec_count"] = cycle["matvec_count"]
    stage["pc_apply_count"] = cycle["pc_apply_count"]
    stage["stagnation"] = runner._stagnation_facts(stage["initial_true_residual"], [cycle], 0)
    worker["gates"]["classification"] = "E2_PHYSICAL_BREAKDOWN"
    _write_json(worker_path, worker)
    _refresh_worker_hash(parent_path, worker_path)
    result = checker.check_artifact(parent_path, "a" * 40)
    assert result["status"] == "PASS", result
    assert result["evidence_valid"] is True
    assert result["classification"] == "E2_PHYSICAL_BREAKDOWN"
    if partial_iterations == 32:
        invalid_parent, invalid_worker = _make_artifact(tmp_path / "invalid-diverged-its")
        invalid = json.loads(invalid_worker.read_text(encoding="utf-8"))
        invalid["stage"]["cycles"][0]["end_iteration"] = 32
        invalid["stage"]["cycles"][0]["iterations"] = 32
        invalid["stage"]["cycles"][0]["additional_iteration"] = 32
        invalid["stage"]["cycles"][0]["absolute_iteration"] = runner.ABSOLUTE_ORIGIN + 32
        invalid["stage"]["cycles"][0]["reason"] = checker.DIVERGED_ITS
        invalid["stage"]["local_iterations"] = 32
        invalid["stage"]["additional_iterations"] = 32
        invalid["stage"]["absolute_end_iteration"] = runner.ABSOLUTE_ORIGIN + 32
        invalid["stage"]["stagnation"] = runner._stagnation_facts(
            invalid["stage"]["initial_true_residual"], invalid["stage"]["cycles"], 0
        )
        _write_json(invalid_worker, invalid)
        _refresh_worker_hash(invalid_parent, invalid_worker)
        rejected = checker.check_artifact(invalid_parent, "a" * 40)
        assert rejected["status"] == "FAIL"
        assert rejected["evidence_valid"] is False
