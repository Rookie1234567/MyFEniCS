from __future__ import annotations

from copy import deepcopy
import inspect
import json
from pathlib import Path
import shutil

import numpy as np
import pytest

import benchmarks.run_task037_extra_m6b as runner
from src.solvers.hcurl_m6b_w16_global_shifted_inner_pc import (
    W16A_SCRATCH_TWO_RUN_TOTAL_BYTES,
    W16R_ADDITIONAL_STEPS,
    W16R_GLOBAL_ACTION_COUNT_PER_RUN,
    W16R_INNER_SCHEMA,
    W16R_SCHEMA,
    evaluate_w16r_restart20_gate,
    run_w16a_fixed20,
    run_w16r_fixed20,
)
from src.solvers.persistent_residual_one_vector import repeat_rank_one_projection
from src.test.test_338_task037_m6b_w16_global_shifted_inner import (
    _synthetic_summary,
)
from src.test.test_340_task037_m6b_w16a_resource_closeout import (
    formal_fixture as _w16a_formal_fixture,
)


EXPECTED_SHA = "a" * 40


def _w16r_summary() -> dict:
    summary = deepcopy(_synthetic_summary())
    summary["schema"] = W16R_SCHEMA
    summary["restart_authority"] = {
        "compact_path": "m6b_w16a_d5460ef_formal_resource_closeout_v1.json",
        "compact_file_sha256": "a" * 64,
        "compact_evidence_sha256": "b" * 64,
        "raw_dir": "m6b_w16a_d5460ef_formal_run1",
        "raw_summary_sha256": "c" * 64,
        "raw_summary_bytes": 123,
        "z20_sha256": "d" * 64,
        "initial_solution_provided": True,
        "initial_solution_role": "W16A_run1_run2_z20",
        "w16a_numeric_fail_only_worker_action_gate": True,
    }
    for audit in summary["inner_audits"]:
        audit["action_count"] = 22
        audit["initial_action_count"] = 1
        audit["initial_solution_provided"] = True
    for record in summary["inner_records"]:
        record.update(
            {
                "schema": W16R_INNER_SCHEMA,
                "algorithm": "fgmres_right_shifted_beta1_restart20",
                "action_count": 22,
                "initial_action_count": 1,
                "initial_solution_provided": True,
                "initial_solution_sha256": "d" * 64,
                "initial_cumulative_iteration": 20,
                "additional_iterations": 20,
                "cumulative_iteration": 40,
            }
        )
    for measurement in summary["measurements"]:
        measurement["schema"] = W16R_SCHEMA
    summary["z40_identity"] = summary.pop("z_identity")
    summary["action_audit"].update(
        {
            "global_shifted_action_count": 44,
            "shifted_action_total_count": 84,
        }
    )
    summary["prediction"] = runner._m6b_w16r_predicted_live_set()
    return summary


def _convert_formal_fixture_to_w16r(fixture, monkeypatch):
    raw_dir = fixture["raw"]
    watchdog_dir = fixture["watchdog"]
    summary = deepcopy(fixture["summary"])
    core = summary["core"]
    solution_path = raw_dir / "inner_checkpoints" / "run1" / "m6b_iter20_solution.npy"
    solution = np.load(solution_path, allow_pickle=False)
    solution_sha = runner._m6b_w6a_w5_legacy_raw_array_sha256(solution)
    rhs_sha = core["artifacts"]["inner_checkpoints"][0]["artifacts"]["rhs"][
        "array_sha256"
    ]
    residual_sha = core["artifacts"]["inner_checkpoints"][0]["artifacts"][
        "residual"
    ]["array_sha256"]
    old_summary_artifact = runner._artifact(
        raw_dir, runner.M6B_W16A_SUMMARY_FILENAME
    )
    restart_metadata = {
        "compact_path": str((raw_dir.parent / "frozen_w16a.json").resolve()),
        "compact_file_sha256": "a" * 64,
        "compact_evidence_sha256": "b" * 64,
        "raw_dir": str(raw_dir.resolve()),
        "raw_summary_path": str(
            (raw_dir / runner.M6B_W16A_SUMMARY_FILENAME).resolve()
        ),
        "raw_summary_sha256": old_summary_artifact["sha256"],
        "raw_summary_bytes": old_summary_artifact["bytes"],
        "z20_sha256": solution_sha,
        "rhs_sha256": rhs_sha,
        "residual_sha256": residual_sha,
        "source_sha": EXPECTED_SHA,
        "initial_solution_provided": True,
        "initial_solution_role": "W16A_run1_run2_z20",
        "w16a_numeric_fail_only_worker_action_gate": True,
    }

    for artifact_container in (summary["artifacts"], core["artifacts"]):
        physical = artifact_container["physical_action_outputs"]
        for name, descriptor in physical.items():
            old_path = Path(descriptor["path"])
            new_path = old_path.with_name(f"w16r_physical_{name}.npy")
            shutil.copy2(old_path, new_path)
            descriptor["path"] = str(new_path.resolve())

    for audit in core["inner_audits"]:
        audit.update(
            {
                "action_count": 22,
                "initial_action_count": 1,
                "initial_solution_provided": True,
            }
        )
    for record in core["inner_records"]:
        record.update(
            {
                "schema": W16R_INNER_SCHEMA,
                "algorithm": "fgmres_right_shifted_beta1_restart20",
                "action_count": 22,
                "initial_action_count": 1,
                "initial_solution_provided": True,
                "initial_solution_sha256": solution_sha,
                "solution_sha256": solution_sha,
                "initial_cumulative_iteration": 20,
                "additional_iterations": 20,
                "cumulative_iteration": 40,
            }
        )
    z_identity = core.pop("z_identity")
    z_identity.update(
        {"first_sha256": solution_sha, "second_sha256": solution_sha}
    )
    core["z40_identity"] = z_identity
    physical = core["artifacts"]["physical_action_outputs"]
    p1 = np.load(Path(physical["p1"]["path"]), allow_pickle=False)
    p_sha = runner._m6b_w6a_w5_legacy_raw_array_sha256(p1)
    core["p_identity"].update(
        {"first_sha256": p_sha, "second_sha256": p_sha, "sha256_equal": True}
    )
    rhs = np.load(
        raw_dir / "inner_checkpoints" / "run1" / "m6b_iter20_rhs.npy",
        allow_pickle=False,
    )
    core["measurements"] = [
        repeat_rank_one_projection(
            rhs,
            p1,
            block_size=runner.M6B_W11A_BLOCK_SIZE,
            schema=runner.M6B_W16R_SCHEMA,
        )
        for _ in (1, 2)
    ]
    core["schema"] = runner.M6B_W16R_SCHEMA
    core["restart_authority"] = deepcopy(restart_metadata)
    core["action_audit"].update(
        {
            "retained_authority_vector_roles": [
                "w7_target_residual",
                "w16a_z20_restart_authority",
            ],
            "global_shifted_action_count": 44,
            "shifted_action_total_count": 84,
            "auxiliary_final_counts": {
                **core["action_audit"]["auxiliary_final_counts"],
                "global_shifted_action_count": 44,
                "shifted_action_total_count": 84,
                "shifted_action_audit": {"apply_count": 84},
            },
        }
    )
    core["prediction"] = runner._m6b_w16r_predicted_live_set()
    summary["core"] = core
    summary["schema"] = runner.M6B_W16R_SCHEMA
    summary["phase"] = runner.M6B_W16R_PHASE
    summary["status"] = "action_gate_pass"
    summary["classification"] = "W16R_RESTART20_PASS"
    summary.pop("w16a_pass", None)
    summary["w16r_pass"] = True
    summary["w16b_locked"] = True
    summary["w16b_action_candidate"] = True
    summary["scope"] = runner._m6b_w16r_scope()
    summary["predicted_live_set"] = runner._m6b_w16r_predicted_live_set()
    summary["action_audit"] = deepcopy(core["action_audit"])
    summary["architecture"] = deepcopy(core["architecture"])
    summary["authority"]["w16a_restart"] = deepcopy(restart_metadata)
    summary["checks"] = {}
    summary["error"] = None
    raw_progress = raw_dir / runner.M6B_W16R_PROGRESS_FILENAME
    raw_progress.write_text(
        "".join(
            json.dumps(
                {
                    "schema": f"{runner.M6B_W16R_SCHEMA}.progress.v1",
                    "phase": runner.M6B_W16R_PHASE,
                    "event": event,
                    "elapsed_wall_seconds": float(index),
                    **(
                        {"w16a_restart": restart_metadata}
                        if event in {"authority_validated", "summary_ready"}
                        else {}
                    ),
                },
                sort_keys=True,
            )
            + "\n"
            for index, event in enumerate(runner.M6B_W16R_EVENTS)
        ),
        encoding="utf-8",
    )
    raw_summary_path = raw_dir / runner.M6B_W16R_SUMMARY_FILENAME
    runner._write_json(raw_summary_path, runner._attach_evidence(summary))

    old_watchdog = runner._read_json(fixture["watchdog_summary"])
    timeline_path = watchdog_dir / f"{runner.M6B_W16R_PHASE}_timeline.jsonl"
    timeline_path.write_text(
        json.dumps(
            {
                "phase": runner.M6B_W16R_PHASE,
                "rss_bytes": 100,
                "swap_bytes": 0,
                "compiler_descendant_pids": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (watchdog_dir / f"{runner.M6B_W16R_PHASE}_stdout.txt").write_text("ok\n")
    (watchdog_dir / f"{runner.M6B_W16R_PHASE}_root_pid.json").write_text("{}\n")
    timeline = runner._m6b_w8a_timeline_valid(
        timeline_path, phase=runner.M6B_W16R_PHASE
    )
    watchdog = {
        **old_watchdog,
        "schema": runner.M6B_W16R_WATCHDOG_SCHEMA,
        "phase": runner.M6B_W16R_PHASE,
        "status": "measurement_complete",
        "raw_dir": str(raw_dir.resolve()),
        "watchdog_dir": str(watchdog_dir.resolve()),
        "command": runner._m6b_w16r_worker_command(
            raw_dir,
            runner.ROOT / runner.M6B_W8A_W7_COMPACT_RELATIVE_PATH,
            runner.ROOT / runner.M6B_W16A_W7_RAW_RELATIVE_PATH,
            runner.ROOT / runner.M6B_W16A_SHIFTED_FACTOR_MANIFEST_RELATIVE_PATH,
            runner.ROOT / runner.M6B_W16A_JIT_RELATIVE_PATH,
            runner.ROOT / runner.M6B_W16R_W16A_COMPACT_RELATIVE_PATH,
            runner.ROOT / runner.M6B_W16R_W16A_RAW_RELATIVE_PATH,
            EXPECTED_SHA,
        ),
        "resource_limits": {
            "timeout_seconds": runner.M6B_W16R_TIMEOUT_SECONDS,
            "watchdog_rss_bytes": runner.M6B_W16R_WATCHDOG_RSS_LIMIT_BYTES,
            "completion_peak_rss_bytes": runner.M6B_W16R_FORMAL_RSS_LIMIT_BYTES,
            "swap_bytes": runner.M6B_SWAP_LIMIT_BYTES,
        },
        "artifact_inventory": {
            "raw": runner._m6b_w16a_raw_artifacts(raw_dir, mode="w16r"),
            "watchdog": runner._m6b_w16a_watchdog_artifacts(
                watchdog_dir, mode="w16r"
            ),
        },
        "worker_summary": runner._artifact(raw_dir, runner.M6B_W16R_SUMMARY_FILENAME),
        "timeline": timeline,
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
        "w16b_unlocked": False,
        "w16a_restart_authority": deepcopy(restart_metadata),
    }
    watchdog_path = watchdog_dir / runner.M6B_W16R_WATCHDOG_SUMMARY_FILENAME
    runner._write_json(watchdog_path, runner._attach_evidence(watchdog))
    monkeypatch.setattr(
        runner,
        "_m6b_w16r_w16a_authority",
        lambda *_paths: {
            **deepcopy(restart_metadata),
            "z20": np.array(solution, copy=True),
        },
    )
    return {
        "raw": raw_dir,
        "watchdog": watchdog_dir,
        "watchdog_summary": watchdog_path,
        "summary": summary,
        "restart_metadata": restart_metadata,
    }


@pytest.fixture
def w16r_formal_fixture(tmp_path, monkeypatch):
    fixture = _w16a_formal_fixture.__wrapped__(tmp_path, monkeypatch)
    return _convert_formal_fixture_to_w16r(fixture, monkeypatch)


def _array_descriptor(path: Path, array: np.ndarray) -> dict:
    return {
        "path": str(path.resolve()),
        "bytes": int(path.stat().st_size),
        "sha256": runner._sha256_file(path),
        "array_sha256": runner._m6b_w6a_w5_legacy_raw_array_sha256(array),
        "shape": list(array.shape),
        "dtype": "complex128",
    }


def _refresh_w16r_fixture(fixture, summary, *, return_code=0, status=None):
    raw_dir = fixture["raw"]
    runner._write_json(
        raw_dir / runner.M6B_W16R_SUMMARY_FILENAME,
        runner._attach_evidence(summary),
    )
    watchdog_path = fixture["watchdog_summary"]
    watchdog = runner._read_json(watchdog_path)
    worker_summary = runner._artifact(raw_dir, runner.M6B_W16R_SUMMARY_FILENAME)
    watchdog["worker_summary"] = worker_summary
    watchdog["artifact_inventory"]["raw"][0] = worker_summary
    watchdog["process"]["return_code"] = return_code
    if status is not None:
        watchdog["status"] = status
    runner._write_json(watchdog_path, runner._attach_evidence(watchdog))


def test_w16r_fixed20_uses_initial_solution_and_repeats(tmp_path):
    rows = 24
    diagonal = np.asarray(
        [1.2 + 0.07 * index + 0.03j * (index + 1) for index in range(rows)],
        dtype=np.complex128,
    )
    rhs = np.asarray(
        [1.0 + 0.1 * index + 1j * (0.3 - 0.02 * index) for index in range(rows)],
        dtype=np.complex128,
    )
    initial = np.asarray(
        [0.1 - 0.02j * (index + 1) for index in range(rows)],
        dtype=np.complex128,
    )

    def action(values):
        return np.asarray(diagonal * values, dtype=np.complex128)

    def pc(values):
        return np.asarray((0.71 - 0.08j) * values, dtype=np.complex128)

    results = [
        run_w16r_fixed20(
            action,
            pc,
            rhs,
            initial,
            tmp_path / f"restart-{index}",
            observer=lambda _event: None,
        )
        for index in (1, 2)
    ]
    for result in results:
        assert result.iterations == W16R_ADDITIONAL_STEPS == 20
        assert result.audit["action_count"] == W16R_GLOBAL_ACTION_COUNT_PER_RUN
        assert result.audit["pc_count"] == 20
        assert result.audit["initial_action_count"] == 1
        assert result.audit["initial_solution_provided"] is True
        assert result.audit["checkpoint_iterations"] == [20]
        assert result.audit["checkpoint_set_complete"] is True
        assert result.audit["scratch_bytes"] == 41 * rhs.nbytes
        assert result.solution.dtype == np.dtype(np.complex128)
        assert np.all(np.isfinite(result.solution))
    assert np.array_equal(results[0].solution, results[1].solution)
    assert results[0].audit["scratch_paths"] != results[1].audit["scratch_paths"]
    assert np.array_equal(action(results[0].solution), action(results[1].solution))

    zero_start = np.zeros_like(rhs)
    zero_result = run_w16a_fixed20(
        action,
        pc,
        rhs,
        tmp_path / "zero-start",
        observer=lambda _event: None,
    )
    zero_initial_residual = (
        np.linalg.norm(rhs - action(zero_start)) / np.linalg.norm(rhs)
    )
    restart_initial_residual = (
        np.linalg.norm(rhs - action(initial)) / np.linalg.norm(rhs)
    )
    assert not np.isclose(zero_initial_residual, restart_initial_residual)
    assert not np.array_equal(results[0].solution, zero_result.solution)


def test_w16r_evaluator_requires_restart_identity_and_cumulative_steps():
    report = evaluate_w16r_restart20_gate(_w16r_summary())
    assert report["pass"] is True
    assert all(report["checks"].values())

    for field, value in (
        ("initial_solution_sha256", "0" * 64),
        ("initial_cumulative_iteration", 19),
        ("additional_iterations", 21),
        ("cumulative_iteration", 39),
    ):
        summary = _w16r_summary()
        summary["inner_records"][1][field] = value
        tampered = evaluate_w16r_restart20_gate(summary)
        assert tampered["pass"] is False
        assert tampered["checks"]["inner_records"] is False


@pytest.mark.parametrize(
    "tamper", ["second_audit", "scratch_path", "prediction", "measurement_schema"]
)
def test_w16r_evaluator_fail_closed_for_second_cycle_or_prediction(tamper):
    summary = _w16r_summary()
    if tamper == "second_audit":
        summary["inner_audits"][1]["pc_count"] = 19
    elif tamper == "scratch_path":
        summary["inner_audits"][1]["scratch_paths"]["v_basis"] = (
            summary["inner_audits"][0]["scratch_paths"]["v_basis"]
        )
    else:
        if tamper == "prediction":
            summary["prediction"]["two_run_scratch_bytes"] = (
                W16A_SCRATCH_TWO_RUN_TOTAL_BYTES - 1
            )
        else:
            summary["measurements"][0]["schema"] = runner.M6B_W16A_SCHEMA
    report = evaluate_w16r_restart20_gate(summary)
    assert report["pass"] is False
    expected_check = (
        "inner_audits"
        if tamper in {"second_audit", "scratch_path"}
        else "prediction"
        if tamper == "prediction"
        else "measurements"
    )
    assert report["checks"][expected_check] is False


def test_w16a_legacy_record_without_initial_fields_remains_accepted():
    summary = _synthetic_summary()
    from src.solvers.hcurl_m6b_w16_global_shifted_inner_pc import (
        _fixed20_inner_audit,
        _fixed20_record,
    )

    assert "initial_solution_provided" not in summary["inner_records"][0]
    assert _fixed20_record(summary["inner_records"][0]) is True
    assert _fixed20_inner_audit(summary["inner_audits"][0]) is True


def test_w16r_command_scope_and_single_owned_restart_vector_contract():
    command = runner._m6b_w16r_worker_command(
        Path("raw"),
        Path("w7.json"),
        Path("w7-raw"),
        Path("factor/manifest.json"),
        Path("jit"),
        Path("w16a.json"),
        Path("w16a-raw"),
        "e" * 40,
    )
    assert "m6b-w16r-restart20-diagnostic" in command
    assert command[command.index("--w16a-compact") + 1].endswith("w16a.json")
    assert command[command.index("--w16a-raw-dir") + 1].endswith("w16a-raw")
    scope = runner._m6b_w16r_scope()
    assert scope["zero_start_for_additional_cycle"] is False
    assert scope["fresh_initial_action"] is True
    assert scope["fresh_initial_residual"] is True
    source = inspect.getsource(runner._run_m6b_w16a_diagnostic)
    assert "restart_z20 = restart_authority.pop(\"z20\")" in source
    assert 'np.array(restart_authority["z20"]' not in source


def test_w16r_parser_requires_frozen_restart_inputs():
    args = runner._parser().parse_args(
        [
            "m6b-w16r-restart20-diagnostic",
            "--run-dir",
            "raw",
            "--w7-compact",
            "w7.json",
            "--w7-raw-dir",
            "w7-raw",
            "--shifted-factor-manifest",
            "factor.json",
            "--jit-cache-source",
            "jit",
            "--w16a-compact",
            "w16a.json",
            "--w16a-raw-dir",
            "w16a-raw",
            "--expected-source-sha",
            "e" * 40,
        ]
    )
    assert args.command == "m6b-w16r-restart20-diagnostic"
    assert args.w16a_compact == "w16a.json"
    assert args.w16a_raw_dir == "w16a-raw"
    watchdog = runner._parser().parse_args(
        [
            "m6b-w16r-watchdog",
            "--run-dir",
            "raw",
            "--watchdog-dir",
            "watchdog",
            "--w7-compact",
            "w7.json",
            "--w7-raw-dir",
            "w7-raw",
            "--shifted-factor-manifest",
            "factor.json",
            "--jit-cache-source",
            "jit",
            "--w16a-compact",
            "w16a.json",
            "--w16a-raw-dir",
            "w16a-raw",
            "--expected-source-sha",
            "e" * 40,
        ]
    )
    check = runner._parser().parse_args(
        [
            "m6b-w16r-check",
            "--raw-dir",
            "raw",
            "--watchdog-summary",
            "watchdog/w16r_watchdog_summary.json",
            "--output",
            "out.json",
            "--expected-source-sha",
            "e" * 40,
        ]
    )
    assert watchdog.command == "m6b-w16r-watchdog"
    assert check.command == "m6b-w16r-check"


def test_w16r_authority_rejects_alternate_raw_path(tmp_path):
    compact = runner.ROOT / runner.M6B_W16R_W16A_COMPACT_RELATIVE_PATH
    with pytest.raises(ValueError, match="raw path"):
        runner._m6b_w16r_w16a_authority(compact, tmp_path / "alternate-w16a-raw")


def test_w16r_formal_gate_passes_and_only_checker_unlocks(w16r_formal_fixture):
    progress = [
        json.loads(line)
        for line in (
            w16r_formal_fixture["raw"] / runner.M6B_W16R_PROGRESS_FILENAME
        ).read_text(encoding="utf-8").splitlines()
    ]
    assert progress[0]["w16a_restart"] == w16r_formal_fixture["restart_metadata"]
    assert progress[-1]["w16a_restart"] == w16r_formal_fixture["restart_metadata"]
    report = runner._m6b_w16r_formal_gate(
        w16r_formal_fixture["raw"],
        w16r_formal_fixture["watchdog_summary"],
        EXPECTED_SHA,
    )
    assert report["pass"] is True
    assert report["classification"] == "W16R_FORMAL_ACTION_GATE_PASS"
    assert all(report["checks"].values())
    output = w16r_formal_fixture["raw"].parent / "w16r_closeout.json"
    assert (
        runner._run_m6b_w16r_check(
            w16r_formal_fixture["raw"],
            w16r_formal_fixture["watchdog_summary"],
            output,
            EXPECTED_SHA,
        )
        == 0
    )
    compact = runner._read_json(output)
    assert compact["w16b_unlocked"] is True
    assert compact["w16b_locked"] is False
    assert compact["formal_pass"] is True
    assert compact["pde_pass"] is False
    assert compact["official_rta"] is False
    assert "records" not in compact["timeline"]


def test_w16r_formal_gate_numeric_fail_keeps_execution_evidence_closed(
    w16r_formal_fixture,
):
    summary = deepcopy(w16r_formal_fixture["summary"])
    rhs = np.load(
        w16r_formal_fixture["raw"]
        / "inner_checkpoints"
        / "run1"
        / "m6b_iter20_rhs.npy",
        allow_pickle=False,
    )
    failing_direction = np.asarray(
        [-np.conjugate(rhs[1]), np.conjugate(rhs[0])], dtype=np.complex128
    )
    physical = summary["core"]["artifacts"]["physical_action_outputs"]
    for name in ("p1", "p2"):
        path = Path(physical[name]["path"])
        np.save(path, failing_direction, allow_pickle=False)
        physical[name] = _array_descriptor(path, failing_direction)
    summary["artifacts"]["physical_action_outputs"] = deepcopy(physical)
    failing_sha = runner._m6b_w6a_w5_legacy_raw_array_sha256(failing_direction)
    summary["core"]["p_identity"].update(
        {"first_sha256": failing_sha, "second_sha256": failing_sha}
    )
    summary["core"]["measurements"] = [
        repeat_rank_one_projection(
            rhs,
            failing_direction,
            block_size=runner.M6B_W11A_BLOCK_SIZE,
            schema=runner.M6B_W16R_SCHEMA,
        )
        for _ in (1, 2)
    ]
    summary["status"] = "gate_failed"
    summary["classification"] = "W16R_RESTART20_NUMERIC_FAIL"
    summary["w16r_pass"] = False
    summary["w16b_action_candidate"] = False
    _refresh_w16r_fixture(
        w16r_formal_fixture,
        summary,
        return_code=1,
        status="gate_failed",
    )
    report = runner._m6b_w16r_formal_gate(
        w16r_formal_fixture["raw"],
        w16r_formal_fixture["watchdog_summary"],
        EXPECTED_SHA,
    )
    assert report["classification"] == "W16R_RESTART20_NUMERIC_FAIL"
    assert report["checks"]["worker_action_gate"] is False
    assert all(
        report["checks"][name]
        for name in report["checks"]
        if name != "worker_action_gate"
    )
    assert report["checks"]["execution_semantics"] is True


def test_w16r_formal_gate_resource_failure_is_distinct(w16r_formal_fixture):
    watchdog_path = w16r_formal_fixture["watchdog_summary"]
    watchdog = runner._read_json(watchdog_path)
    limit = runner.M6B_W16R_FORMAL_RSS_LIMIT_BYTES
    watchdog["process"]["peak_rss_bytes"] = limit
    timeline_path = (
        w16r_formal_fixture["watchdog"] / f"{runner.M6B_W16R_PHASE}_timeline.jsonl"
    )
    timeline_path.write_text(
        json.dumps(
            {
                "phase": runner.M6B_W16R_PHASE,
                "rss_bytes": limit,
                "swap_bytes": 0,
                "compiler_descendant_pids": [],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    watchdog["timeline"] = runner._m6b_w8a_timeline_valid(
        timeline_path, phase=runner.M6B_W16R_PHASE
    )
    watchdog["artifact_inventory"]["watchdog"][0] = runner._artifact(
        w16r_formal_fixture["watchdog"],
        f"{runner.M6B_W16R_PHASE}_timeline.jsonl",
    )
    runner._write_json(watchdog_path, runner._attach_evidence(watchdog))
    report = runner._m6b_w16r_formal_gate(
        w16r_formal_fixture["raw"], watchdog_path, EXPECTED_SHA
    )
    assert report["classification"] == "W16R_RESOURCE_FAIL"
    assert report["checks"]["resource"] is False


@pytest.mark.parametrize("tamper", ["restart", "z40", "p", "checkpoint"])
def test_w16r_formal_gate_authority_and_vector_tamper_fail_closed(
    w16r_formal_fixture, tamper
):
    summary = deepcopy(w16r_formal_fixture["summary"])
    if tamper == "restart":
        summary["core"]["restart_authority"]["rhs_sha256"] = "0" * 64
    elif tamper == "z40":
        summary["core"]["z40_identity"]["first_sha256"] = "0" * 64
    elif tamper == "p":
        summary["core"]["p_identity"]["first_sha256"] = "0" * 64
    else:
        summary["core"]["artifacts"]["inner_checkpoints"][0]["artifacts"][
            "solution"
        ]["array_sha256"] = "0" * 64
    _refresh_w16r_fixture(w16r_formal_fixture, summary)
    report = runner._m6b_w16r_formal_gate(
        w16r_formal_fixture["raw"],
        w16r_formal_fixture["watchdog_summary"],
        EXPECTED_SHA,
    )
    assert report["pass"] is False
    assert report["classification"] == "W16R_EXECUTION_OR_EVIDENCE_FAIL"
    assert not all(report["checks"].values())
    if tamper == "restart":
        assert report["checks"]["restart_authority"] is False
    elif tamper == "checkpoint":
        assert report["checks"]["artifacts"] is False
    else:
        assert report["checks"]["vector_evidence"] is False
