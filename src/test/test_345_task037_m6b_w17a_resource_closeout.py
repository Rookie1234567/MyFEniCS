"""Focused pure contracts for the W17A formal resource closeout."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks import run_task037_extra_m6b as runner
from src.solvers import hcurl_m6b_w16_global_shifted_inner_pc as core
from src.solvers.hcurl_h2b_m5_coercive import _array_sha256
from src.solvers.persistent_residual_one_vector import (
    repeat_rank_one_projection,
)
from src.test.test_343_task037_m6b_w17a_global_physical_shifted import (
    _w17a_summary,
)


EXPECTED_SOURCE_SHA = "a" * 40
FACTOR_SOURCE_SHA = "d98254fecddc41940f50f72753ec9f0f80407793"


def _source() -> dict[str, object]:
    return {
        "source_commit_full_sha": EXPECTED_SOURCE_SHA,
        "tracked_source_dirty": False,
        "source_worktree_dirty": False,
        "nonignored_untracked_paths": [],
        "worktree_status_porcelain": [],
        "git_error": None,
    }


def _materialization() -> dict[str, bool]:
    return {
        "global_constraint_matrix": False,
        "global_matrix": False,
        "patch_matrices": False,
        "per_cell_factor": False,
        "schur": False,
        "slab_factor": False,
        "static_condensation": False,
        "trace_slab": False,
    }


def _shifted(count: int) -> dict[str, object]:
    return {
        "apply_count": count,
        "global_matrix_materialized": False,
        "global_constraint_matrix_materialized": False,
        "global_condensed_schur_materialized": False,
        "cell_schur_matrix_materialized": False,
        "slab_matrix_materialized": False,
        "retained_dense_cell_tensor_count": 0,
        "dense_cell_tensor_materialized_per_apply": False,
        "cell_schur_matrix_nnz": 0,
        "slab_matrix_nnz": 0,
        "explicit_C_materialized_count": 0,
        "explicit_D_materialized_count": 0,
        "factor_count": 0,
        "ksp_created": False,
        "ordinary_default_changed": False,
        "materialization_identity": _materialization(),
    }


def _outer(count: int) -> dict[str, object]:
    return {
        "apply_count": count,
        "matrix_type": "python_action_only",
        "global_matrix": False,
        "augmented_matrix": False,
        "static_condensation": False,
        "trace_slab": False,
        "explicit_C_materialized_count": 0,
        "explicit_D_materialized_count": 0,
    }


def _dtn(count: int) -> dict[str, object]:
    return {
        "apply_count": count,
        "mode_count": 80,
        "fine_space": "uncondensed_fullspace",
        "ordinary_default": False,
        "condensation": False,
        "static_condensed_operator_used": False,
        "trace_slab_pc_used": False,
        "global_matrix_materialized": False,
        "augmented_matrix_materialized": False,
        "explicit_C_materialized_count": 0,
        "explicit_D_materialized_count": 0,
        "fe_sized_allgather": False,
        "modal_allreduce_count_per_apply": 1,
        "modal_allreduce_count_per_hermitian_apply": 1,
    }


def _physical() -> dict[str, object]:
    return {
        **_shifted(2),
        "apply_count": 2,
    }


def _bridge(count: int) -> dict[str, object]:
    return {
        "forward_apply_count": count,
        "fixed_work_vectors": 2,
        "per_apply_vec_creation": 0,
    }


def _action_audit(factor_audit: dict[str, int]) -> dict[str, object]:
    local_pc = {
        "beta": 1.0,
        "unique_factor_count": 84,
        "fine_space": "uncondensed_fullspace",
        "ordinary_default_changed": False,
        "materialization_identity": _materialization(),
    }
    factor_store = {
        "beta": 1.0,
        "factor_count": 84,
        "factor_payload_bytes": factor_audit["factor_payload_bytes"],
        "retained_total_bytes": factor_audit["retained_total_bytes"],
        "ordinary_default_changed": False,
        "materialization_identity": _materialization(),
    }
    shifted_final = _shifted(166)
    dtn_final = _dtn(88)
    return {
        "retained_authority_vector_roles": ["w7_target_residual"],
        "lifecycle_events": [
            "dtn_constructed",
            "auxiliary_constructed",
            "auxiliary_run_1",
            "auxiliary_run_2",
            "auxiliary_released",
            "physical_constructed",
            "physical_apply_1",
            "physical_apply_2",
            "physical_released",
            "dtn_released",
        ],
        "global_auxiliary_action_count": 86,
        "global_shifted_action_count": 86,
        "local_pc_apply_count": 80,
        "local_exact_shifted_volume_action_count": 80,
        "shifted_action_total_count": 166,
        "shifted_action_count": 166,
        "auxiliary_dtn_action_count": 86,
        "physical_volume_action_count": 2,
        "physical_dtn_action_count": 2,
        "total_dtn_action_count": 88,
        "physical_action_count": 2,
        "auxiliary_construction": {
            "shifted_action": _shifted(0),
            "local_pc": local_pc,
            "factor_store": factor_store,
        },
        "auxiliary_final_counts": {
            "outer": _outer(86),
            "dtn": _dtn(86),
            "bridge": _bridge(86),
            "shifted_action": shifted_final,
            "shifted_action_audit": shifted_final,
            "global_shifted_action_count": 86,
            "local_pc_apply_count": 80,
            "local_exact_shifted_volume_action_count": 80,
            "shifted_action_total_count": 166,
        },
        "physical_instances": [
            {
                "physical": _physical(),
                "outer": _outer(2),
                "dtn": dtn_final,
                "bridge": _bridge(2),
            }
        ],
    }


def _write_array(path: Path, values: np.ndarray) -> dict[str, object]:
    values = np.ascontiguousarray(values, dtype=np.complex128)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, values, allow_pickle=False)
    return {
        "path": str(path.resolve()),
        "bytes": int(path.stat().st_size),
        "file_sha256": runner._sha256_file(path),
        "array_sha256": _array_sha256(values),
        "shape": list(values.shape),
        "dtype": "complex128",
    }


def _write_sparse(path: Path, size: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.truncate(size)


def _timeline(path: Path, peak: int = 1000) -> dict[str, object]:
    record = {
        "phase": runner.M6B_W17A_PHASE,
        "rss_bytes": peak,
        "swap_bytes": 0,
        "compiler_descendant_pids": [],
    }
    path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    return runner._m6b_w8a_timeline_valid(
        path, phase=runner.M6B_W17A_PHASE
    )


@pytest.fixture
def formal_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import benchmarks.run_task037_extra_h2b as h2b

    monkeypatch.setattr(core, "W16A_VECTOR_BYTES", 16)
    monkeypatch.setattr(core, "W16A_SCRATCH_PER_RUN_BYTES", 41 * 16)
    raw_dir = tmp_path / "raw"
    watchdog_dir = tmp_path / "watchdog"
    raw_dir.mkdir()
    watchdog_dir.mkdir()
    factor_path = tmp_path / "factor" / "manifest.json"
    factor_audit = {
        "factor_count": 84,
        "factor_payload_bytes": 123,
        "retained_total_bytes": 456,
    }
    factor_path.parent.mkdir()
    factor_path.write_text(
        json.dumps({"audit": factor_audit}), encoding="utf-8"
    )
    factor = {
        "path": str(factor_path.resolve()),
        "present": True,
        "bytes": int(factor_path.stat().st_size),
        "sha256": "b" * 64,
        "source_commit_full_sha": FACTOR_SOURCE_SHA,
        "beta": 1.0,
        "audit": {
            "cell_count": 252,
            **factor_audit,
            "factor_order": 882,
        },
        "factor_compiler": {"version_line": "fixture"},
    }
    residual = np.asarray([1.0 + 0.5j, 2.0 - 0.25j], dtype=np.complex128)
    w7 = {
        "compact": {
            "path": str(tmp_path / "w7.json"),
            "file_sha256": "c" * 64,
            "producer_source_sha": runner.M6B_W8A_W7_SOURCE_SHA,
        },
        "raw_dir": str(tmp_path / "w7_raw"),
        "residual": residual,
        "residual_artifact": {
            "path": "m6b_iter400_residual.npy",
            "bytes": int(residual.nbytes),
            "file_sha256": "d" * 64,
            "array_sha256": _array_sha256(residual),
        },
    }
    source = _source()
    monkeypatch.setattr(
        runner,
        "_m6b_w9a_load_w7",
        lambda *_paths: {
            **deepcopy(w7),
            "residual": np.array(residual, copy=True),
        },
    )
    monkeypatch.setattr(
        runner,
        "_m6b_w16a_factor_authority",
        lambda _path: deepcopy(factor),
    )
    monkeypatch.setattr(runner, "_m6b_w16a_jit_valid", lambda *_args: True)
    monkeypatch.setattr(runner, "_m6b_w6a_source_valid", lambda _value: True)
    monkeypatch.setattr(
        runner, "_m6b_w6a_runtime_valid", lambda *_args, **_kwargs: True
    )
    monkeypatch.setattr(runner, "_m6b_expected_p6", lambda _value: True)
    monkeypatch.setattr(h2b, "_light_source", lambda: deepcopy(source))

    summary = _w17a_summary()
    summary["schema"] = runner.M6B_W17A_SCHEMA
    summary["phase"] = runner.M6B_W17A_PHASE
    summary["authority"] = {
        "w7": deepcopy(w7["compact"]),
        "w7_raw_dir": w7["raw_dir"],
        "w7_residual_artifact": deepcopy(w7["residual_artifact"]),
        "factor_manifest": deepcopy(factor),
    }
    summary["scope"] = runner._m6b_w17a_scope()
    summary["p6"] = {"fixture": True}
    summary["runtime_identity"] = {
        "compiler": deepcopy(factor["factor_compiler"])
    }
    summary["jit_cache"] = {"fixture": True}
    summary["source_at_start"] = deepcopy(source)
    summary["source_at_end"] = deepcopy(source)
    summary["error"] = None
    summary["status"] = "action_gate_pass"
    summary["classification"] = "W17A_GLOBAL_PHYSICAL_SHIFTED_PASS"
    summary["w17a_pass"] = True
    summary["formal_pass"] = False
    summary["pde_pass"] = False
    summary["official_rta"] = False
    summary["w17b_locked"] = True
    summary["w17b_action_candidate"] = True
    summary["predicted_live_set"] = runner._m6b_w17a_predicted_live_set()
    summary["residual"] = {
        "role": "untouched_W7_cumulative400_full_explicit_residual",
        "authority": deepcopy(w7["compact"]),
        "artifact": deepcopy(w7["residual_artifact"]),
    }

    p_values = [
        np.asarray([0.3 + 0.1j, -0.2 + 0.4j], dtype=np.complex128),
        np.asarray([0.3 + 0.1j, -0.2 + 0.4j], dtype=np.complex128),
    ]
    z_values = [
        np.asarray([0.25 - 0.5j, -0.75 + 0.125j], dtype=np.complex128),
        np.asarray([0.25 - 0.5j, -0.75 + 0.125j], dtype=np.complex128),
    ]
    audits = summary["inner_audits"]
    for index, (audit, z_value) in enumerate(zip(audits, z_values), 1):
        z_record = _write_array(raw_dir / f"w17a_z{index}.npy", z_value)
        audit["solution_artifact"] = z_record
        audit["solution_sha256"] = z_record["array_sha256"]
        audit["scratch_paths"] = {}
        for cycle in (20, 40):
            cycle_paths = {}
            for role in ("v", "z"):
                path = raw_dir / "scratch" / f"run{index}" / f"cycle{cycle}" / f"{role}_basis.bin"
                basis = audit[f"cycle{cycle}"][f"{role}_basis"]
                _write_sparse(path, basis["allocated_bytes"])
                cycle_paths[f"{role}_basis"] = str(path.resolve())
            audit[f"cycle{cycle}"]["scratch_paths"] = cycle_paths
            audit["scratch_paths"][f"cycle{cycle}"] = cycle_paths
    p_records = {
        f"p{index}": _write_array(raw_dir / f"w17a_p{index}.npy", p_value)
        for index, p_value in enumerate(p_values, 1)
    }
    summary["artifacts"] = {
        "z": [audit["solution_artifact"] for audit in audits],
        "p": p_records,
    }
    summary["z_identity"].update(
        {
            "first_sha256": audits[0]["solution_sha256"],
            "second_sha256": audits[1]["solution_sha256"],
        }
    )
    summary["p_identity"].update(
        {
            "first_sha256": p_records["p1"]["array_sha256"],
            "second_sha256": p_records["p2"]["array_sha256"],
        }
    )
    summary["measurements"] = [
        repeat_rank_one_projection(
            residual,
            p_value,
            block_size=runner.M6B_W11A_BLOCK_SIZE,
            schema=runner.M6B_W17A_SCHEMA,
        )
        for p_value in p_values
    ]
    action = _action_audit(factor_audit)
    summary["action_audit"] = action
    summary["core"] = deepcopy(summary)
    summary["core"].pop("core", None)
    core_report = core.evaluate_w17a_global_physical_shifted_gate(
        summary["core"]
    )
    checks = dict(core_report["checks"])
    checks.update(source=True, cache=True, execution=True)
    summary["core"]["checks"] = deepcopy(checks)
    summary["checks"] = deepcopy(checks)

    progress_path = raw_dir / runner.M6B_W17A_PROGRESS_FILENAME
    progress_path.write_text(
        "".join(
            json.dumps(
                {
                    "schema": f"{runner.M6B_W17A_SCHEMA}.progress.v1",
                    "phase": runner.M6B_W17A_PHASE,
                    "event": event,
                }
            )
            + "\n"
            for event in runner.M6B_W17A_EVENTS
        ),
        encoding="utf-8",
    )
    summary_path = raw_dir / runner.M6B_W17A_SUMMARY_FILENAME
    summary_path.write_text(
        json.dumps(runner._attach_evidence(summary), sort_keys=True),
        encoding="utf-8",
    )

    timeline_path = (
        watchdog_dir / f"{runner.M6B_W17A_PHASE}_timeline.jsonl"
    )
    timeline = _timeline(timeline_path)
    (watchdog_dir / f"{runner.M6B_W17A_PHASE}_stdout.txt").write_text(
        "fixture\n", encoding="utf-8"
    )
    (watchdog_dir / f"{runner.M6B_W17A_PHASE}_root_pid.json").write_text(
        '{"pid": 1}\n', encoding="utf-8"
    )
    watchdog = {
        "schema": runner.M6B_W17A_WATCHDOG_SCHEMA,
        "phase": runner.M6B_W17A_PHASE,
        "status": "measurement_complete",
        "process": {
            "return_code": 0,
            "termination": None,
            "peak_rss_bytes": 1000,
            "swap_bytes": 0,
        },
        "drain": {"gone": True},
        "source_at_start": deepcopy(source),
        "source_at_end": deepcopy(source),
        "source_end_clean": True,
        "resource_limits": {
            "timeout_seconds": runner.M6B_W17A_TIMEOUT_SECONDS,
            "watchdog_rss_bytes": runner.M6B_W17A_WATCHDOG_RSS_LIMIT_BYTES,
            "completion_peak_rss_bytes": runner.M6B_W17A_FORMAL_RSS_LIMIT_BYTES,
            "swap_bytes": runner.M6B_SWAP_LIMIT_BYTES,
        },
        "raw_dir": str(raw_dir.resolve()),
        "watchdog_dir": str(watchdog_dir.resolve()),
        "command": runner._m6b_w17a_worker_command(
            raw_dir,
            runner.ROOT / runner.M6B_W8A_W7_COMPACT_RELATIVE_PATH,
            runner.ROOT / runner.M6B_W16A_W7_RAW_RELATIVE_PATH,
            runner.ROOT / runner.M6B_W16A_SHIFTED_FACTOR_MANIFEST_RELATIVE_PATH,
            runner.ROOT / runner.M6B_W16A_JIT_RELATIVE_PATH,
            EXPECTED_SOURCE_SHA,
        ),
        "timeline": timeline,
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
        "w17b_unlocked": False,
        "w17b_locked": True,
    }
    watchdog["artifact_inventory"] = {
        "raw": runner._m6b_w16a_raw_artifacts(raw_dir, mode="w17a"),
        "watchdog": runner._m6b_w16a_watchdog_artifacts(
            watchdog_dir, mode="w17a"
        ),
    }
    watchdog["worker_summary"] = watchdog["artifact_inventory"]["raw"][0]
    watchdog_path = watchdog_dir / runner.M6B_W17A_WATCHDOG_SUMMARY_FILENAME
    watchdog_path.write_text(
        json.dumps(runner._attach_evidence(watchdog), sort_keys=True),
        encoding="utf-8",
    )
    return {
        "raw": raw_dir,
        "watchdog": watchdog_dir,
        "watchdog_summary": watchdog_path,
        "summary": summary,
    }


def _refresh_fixture(fixture: dict[str, object]) -> None:
    raw_dir = fixture["raw"]
    watchdog_dir = fixture["watchdog"]
    summary_path = raw_dir / runner.M6B_W17A_SUMMARY_FILENAME
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary_path.write_text(
        json.dumps(runner._attach_evidence(summary), sort_keys=True),
        encoding="utf-8",
    )
    watchdog_path = fixture["watchdog_summary"]
    watchdog = json.loads(watchdog_path.read_text(encoding="utf-8"))
    timeline_path = watchdog_dir / f"{runner.M6B_W17A_PHASE}_timeline.jsonl"
    watchdog["timeline"] = runner._m6b_w8a_timeline_valid(
        timeline_path, phase=runner.M6B_W17A_PHASE
    )
    watchdog["artifact_inventory"] = {
        "raw": runner._m6b_w16a_raw_artifacts(raw_dir, mode="w17a"),
        "watchdog": runner._m6b_w16a_watchdog_artifacts(
            watchdog_dir, mode="w17a"
        ),
    }
    watchdog["worker_summary"] = watchdog["artifact_inventory"]["raw"][0]
    watchdog_path.write_text(
        json.dumps(runner._attach_evidence(watchdog), sort_keys=True),
        encoding="utf-8",
    )


def test_w17a_command_progress_and_inventory() -> None:
    command = runner._m6b_w17a_worker_command(
        Path("/tmp/raw"),
        Path("/tmp/w7.json"),
        Path("/tmp/w7_raw"),
        Path("/tmp/factor.json"),
        Path("/tmp/jit"),
        EXPECTED_SOURCE_SHA,
    )
    assert command[3] == "m6b-w17a-global-physical-shifted-diagnostic"
    assert runner.M6B_W17A_EVENTS[-1] == "summary_ready"
    assert len(runner._m6b_w16a_raw_artifacts(Path("/tmp"), mode="w17a")) == 14
    assert len(runner._m6b_w16a_watchdog_artifacts(Path("/tmp"), mode="w17a")) == 3


def test_w17a_formal_pass_and_compact_writer(formal_fixture, tmp_path: Path) -> None:
    fixture = formal_fixture
    gate = runner._m6b_w17a_formal_gate(
        fixture["raw"], fixture["watchdog_summary"], EXPECTED_SOURCE_SHA
    )
    assert gate["pass"] is True, gate["checks"]
    output = tmp_path / "closeout.json"
    assert (
        runner._run_m6b_w17a_check(
            fixture["raw"],
            fixture["watchdog_summary"],
            output,
            EXPECTED_SOURCE_SHA,
        )
        == 0
    )
    record = json.loads(output.read_text(encoding="utf-8"))
    assert record["w17b_unlocked"] is True
    assert record["w17b_locked"] is False
    assert "records" not in record["timeline"]
    assert "artifact_hashes" in record["vector_evidence"]
    with pytest.raises(FileExistsError):
        runner._run_m6b_w17a_check(
            fixture["raw"],
            fixture["watchdog_summary"],
            output,
            EXPECTED_SOURCE_SHA,
        )


def test_w17a_numeric_only_classification(formal_fixture) -> None:
    fixture = formal_fixture
    summary_path = fixture["raw"] / runner.M6B_W17A_SUMMARY_FILENAME
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    for audit in summary["core"]["inner_audits"]:
        audit["final_relative_residual"] = 0.010001
        audit["cycle40_relative_residual"] = 0.010001
    report = core.evaluate_w17a_global_physical_shifted_gate(summary["core"])
    checks = dict(report["checks"])
    checks.update(source=True, cache=True, execution=True)
    summary["core"]["checks"] = checks
    summary["checks"] = deepcopy(checks)
    summary.update(
        status="gate_failed",
        classification="W17A_GLOBAL_PHYSICAL_SHIFTED_NUMERIC_FAIL",
        w17a_pass=False,
        w17b_action_candidate=False,
    )
    summary_path.write_text(
        json.dumps(runner._attach_evidence(summary), sort_keys=True),
        encoding="utf-8",
    )
    watchdog_path = fixture["watchdog_summary"]
    watchdog = json.loads(watchdog_path.read_text(encoding="utf-8"))
    watchdog["status"] = "gate_failed"
    watchdog["process"]["return_code"] = 1
    watchdog_path.write_text(
        json.dumps(runner._attach_evidence(watchdog), sort_keys=True),
        encoding="utf-8",
    )
    _refresh_fixture(fixture)
    gate = runner._m6b_w17a_formal_gate(
        fixture["raw"], fixture["watchdog_summary"], EXPECTED_SOURCE_SHA
    )
    assert gate["classification"] == "W17A_GLOBAL_PHYSICAL_SHIFTED_NUMERIC_FAIL"
    assert gate["checks"]["worker_action_gate"] is False
    assert all(
        value is True
        for name, value in gate["checks"].items()
        if name != "worker_action_gate"
    )


@pytest.mark.parametrize(
    "tamper,expected_check",
    [
        ("measurement", "vector_evidence"),
        ("solution_hash", "vector_evidence"),
        ("array_hash", "vector_evidence"),
        ("file_hash", "vector_evidence"),
        ("dtn", "action_audit"),
        ("dtn_static", "action_audit"),
        ("materialization", "action_audit"),
        ("scratch", "scratch"),
        ("scratch_size", "scratch"),
        ("progress", "progress"),
        ("peak", "resource"),
        ("swap", "resource"),
        ("compiler", "resource"),
        ("termination", "resource"),
        ("watchdog_evidence", "watchdog_evidence"),
        ("summary_checks", "worker_evidence"),
    ],
)
def test_w17a_formal_gate_tamper_cases(
    formal_fixture, tamper: str, expected_check: str
) -> None:
    fixture = formal_fixture
    summary_path = fixture["raw"] / runner.M6B_W17A_SUMMARY_FILENAME
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    watchdog_path = fixture["watchdog_summary"]
    watchdog = json.loads(watchdog_path.read_text(encoding="utf-8"))
    if tamper == "measurement":
        summary["core"]["measurements"][0]["rho"] += 0.001
    elif tamper == "solution_hash":
        summary["core"]["inner_audits"][0]["solution_sha256"] = "f" * 64
    elif tamper == "array_hash":
        summary["core"]["artifacts"]["z"][0]["array_sha256"] = "e" * 64
    elif tamper == "file_hash":
        summary["core"]["artifacts"]["z"][0]["file_sha256"] = "e" * 64
    elif tamper == "dtn":
        summary["action_audit"]["physical_instances"][0]["dtn"]["apply_count"] = 87
        summary["core"]["action_audit"] = deepcopy(summary["action_audit"])
    elif tamper == "dtn_static":
        summary["action_audit"]["auxiliary_final_counts"]["dtn"][
            "ordinary_default"
        ] = True
        summary["core"]["action_audit"] = deepcopy(summary["action_audit"])
    elif tamper == "materialization":
        summary["action_audit"]["auxiliary_construction"]["local_pc"][
            "materialization_identity"
        ] = {}
        summary["core"]["action_audit"] = deepcopy(summary["action_audit"])
    elif tamper == "scratch":
        audit = summary["core"]["inner_audits"][0]
        audit["scratch_paths"]["cycle20"]["v_basis"] = "/outside/v_basis.bin"
    elif tamper == "scratch_size":
        audit = summary["core"]["inner_audits"][0]
        path = Path(audit["cycle20"]["scratch_paths"]["v_basis"])
        with path.open("wb") as stream:
            stream.truncate(1)
    elif tamper == "progress":
        progress_path = fixture["raw"] / runner.M6B_W17A_PROGRESS_FILENAME
        lines = progress_path.read_text(encoding="utf-8").splitlines()
        lines[0] = lines[0].replace("authority_validated", "wrong")
        progress_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    elif tamper == "peak":
        watchdog["process"]["peak_rss_bytes"] = runner.M6B_W17A_FORMAL_RSS_LIMIT_BYTES
        timeline_path = fixture["watchdog"] / f"{runner.M6B_W17A_PHASE}_timeline.jsonl"
        _timeline(timeline_path, runner.M6B_W17A_FORMAL_RSS_LIMIT_BYTES)
    elif tamper == "swap":
        watchdog["process"]["swap_bytes"] = 1
    elif tamper == "compiler":
        timeline_path = fixture["watchdog"] / f"{runner.M6B_W17A_PHASE}_timeline.jsonl"
        record = {
            "phase": runner.M6B_W17A_PHASE,
            "rss_bytes": 1000,
            "swap_bytes": 0,
            "compiler_descendant_pids": [7],
        }
        timeline_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    elif tamper == "termination":
        watchdog["process"]["termination"] = "rss_limit"
    elif tamper == "watchdog_evidence":
        watchdog["evidence_sha256"] = "0" * 64
    else:
        summary["checks"].pop("execution")
    summary_path.write_text(
        json.dumps(runner._attach_evidence(summary), sort_keys=True),
        encoding="utf-8",
    )
    watchdog_path.write_text(
        json.dumps(runner._attach_evidence(watchdog), sort_keys=True),
        encoding="utf-8",
    )
    _refresh_fixture(fixture)
    if tamper == "watchdog_evidence":
        broken = json.loads(
            fixture["watchdog_summary"].read_text(encoding="utf-8")
        )
        broken["evidence_sha256"] = "0" * 64
        fixture["watchdog_summary"].write_text(
            json.dumps(broken, sort_keys=True), encoding="utf-8"
        )
    gate = runner._m6b_w17a_formal_gate(
        fixture["raw"], fixture["watchdog_summary"], EXPECTED_SOURCE_SHA
    )
    assert gate["pass"] is False
    assert gate["checks"][expected_check] is False
    if tamper in {"peak", "swap", "compiler", "termination"}:
        assert gate["classification"] == "W17A_RESOURCE_FAIL"
    if tamper in {"watchdog_evidence", "summary_checks"}:
        assert gate["classification"] == "W17A_EXECUTION_OR_EVIDENCE_FAIL"


def test_w17a_malformed_summary_fails_closed(formal_fixture) -> None:
    summary_path = formal_fixture["raw"] / runner.M6B_W17A_SUMMARY_FILENAME
    summary_path.write_text("{ malformed", encoding="utf-8")
    gate = runner._m6b_w17a_formal_gate(
        formal_fixture["raw"],
        formal_fixture["watchdog_summary"],
        EXPECTED_SOURCE_SHA,
    )
    assert gate["pass"] is False
    assert gate["classification"] == "W17A_EXECUTION_OR_EVIDENCE_FAIL"


def test_w17a_watchdog_and_check_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        runner,
        "_run_m6b_w17a_watchdog",
        lambda *_args: calls.append("watchdog") or 0,
    )
    monkeypatch.setattr(
        runner,
        "_run_m6b_w17a_check",
        lambda *_args: calls.append("check") or 0,
    )
    assert runner.main(
        [
            "m6b-w17a-watchdog",
            "--run-dir",
            "/tmp/raw",
            "--watchdog-dir",
            "/tmp/watchdog",
            "--w7-compact",
            "/tmp/w7.json",
            "--w7-raw-dir",
            "/tmp/w7raw",
            "--shifted-factor-manifest",
            "/tmp/factor.json",
            "--jit-cache-source",
            "/tmp/jit",
            "--expected-source-sha",
            EXPECTED_SOURCE_SHA,
        ]
    ) == 0
    assert runner.main(
        [
            "m6b-w17a-check",
            "--raw-dir",
            "/tmp/raw",
            "--watchdog-summary",
            "/tmp/watchdog/w17a_watchdog_summary.json",
            "--output",
            "/tmp/out.json",
            "--expected-source-sha",
            EXPECTED_SOURCE_SHA,
        ]
    ) == 0
    assert calls == ["watchdog", "check"]
