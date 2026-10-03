"""The V5 supervisor holds incomplete Gx784 records before budget or workers."""

from __future__ import annotations

import builtins
import json
from pathlib import Path
import subprocess
import sys

import pytest

from benchmarks import run_task40_v5_postprocess_service as service


PROFILE = "task40extra_0p7nm_p6trace_p4_reference_metric_v2"
RUN_ID = "task40extra_0p7nm_nonseparable_gx784_review_v5_v1"


def _case_root(tmp_path: Path, worker_summary: dict) -> Path:
    root = tmp_path / "gx784"
    root.mkdir()
    manifest = {
        "run_id": RUN_ID,
        "source_sha": "a" * 40,
        "physical_model_sha256": "b" * 64,
        "status": "finished",
        "result_classification": worker_summary.get(
            "result_classification", "WORKER_FAILED"
        ),
        "exit_status": 4,
    }
    (root / "run_manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8"
    )
    (root / "run_summary.json").write_text(
        json.dumps(
            {
                "run_id": RUN_ID,
                "status": manifest["status"],
                "result_classification": manifest["result_classification"],
                "exit_status": manifest["exit_status"],
            }
        ),
        encoding="utf-8",
    )
    worker_summary = {
        "schema": "task40extra.nonseparable-0p7nm.p6q4.worker-summary.v1",
        "source_sha": manifest["source_sha"],
        "profile": PROFILE,
        "status": "FAILED",
        "result_classification": manifest["result_classification"],
        **worker_summary,
    }
    (root / service.WORKER_SUMMARY_NAME).write_text(
        json.dumps(worker_summary), encoding="utf-8"
    )
    return root


def _passing_solver_summary() -> dict:
    final = 5.0e-7
    return {
        "final_residual": {"explicit_relative_residual": final},
        "post_release_final_residual": {
            "explicit_relative_residual": final,
            "release_facts": {
                "p6": {"released_after_final_residual": True},
                "p4": {"released_after_final_residual": True},
            },
        },
        "gates": {
            "independent_final_explicit_relative_residual": final,
            "post_release_final_explicit_relative_residual": final,
            "post_release_residual_gate": True,
            "authority_limited_checks_pass": True,
        },
        "release_after_final_residual": True,
        "x2_retained_final": {
            "complete_field_saved": True,
            "saved_before_field_evaluation": True,
            "residuals": {
                "native_identity_relative": 3.0e-11,
                "internal_residual_relative": 4.0e-12,
                "schur_port_identity_relative": 2.0e-12,
                "port_residual_relative": 3.0e-12,
                "strict_zero_slave_storage": True,
            },
        },
    }


def _block_heavy_parent_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__
    blocked = {
        "src.runners.task038_launcher",
        "benchmarks.subreaper_watchdog",
        "benchmarks.postprocess_task40_p1_saved_fields_common_subcells",
        "src.postprocessing.task40_saved_field_h_comparison",
    }

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name in blocked:
            raise AssertionError(f"early-held path imported {name}")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)


@pytest.mark.parametrize(
    ("worker", "expected_classification", "expected_field_checked"),
    [
        (
            {"result_classification": "WORKER_FAILED", "error": {"type": "ValueError"}},
            "solver_or_recovery_gate_not_passed_comparison_held",
            False,
        ),
        (
            {
                "result_classification": "worker_exit0",
                **_passing_solver_summary(),
            },
            "saved_field_archive_missing_or_hash_mismatch_comparison_held",
            False,
        ),
    ],
)
def test_failed_solver_or_missing_saved_field_holds_before_budget_and_supervisor(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    worker: dict,
    expected_classification: str,
    expected_field_checked: bool,
):
    root = _case_root(tmp_path, worker)
    monkeypatch.setattr(
        service, "_git_facts", lambda: ("task40extra_0p7nm_engineering", "c" * 40)
    )
    _block_heavy_parent_imports(monkeypatch)

    record = service._run(root, None)

    assert record["status"] == "POSTPROCESS_HELD_BEFORE_WORKER"
    assert record["worker_started"] is False
    assert record["budget_reserved"] is False
    assert record["watchdog_summary"] is None
    assert record["preflight"]["field_artifact_preflight"]["checked"] is expected_field_checked
    checked = record["checker_record"]
    assert checked["classification"] == expected_classification
    assert checked["comparison_status"] == "held"
    assert not (root / "postprocess_v5" / "attempt1").exists()
    assert Path(record["comparison_path"]).is_file()
    assert Path(record["checker_path"]).is_file()


def test_supervisor_and_worker_modules_import_without_numerical_stack():
    code = """
import sys
import benchmarks.run_task40_v5_postprocess_service
import benchmarks.postprocess_task40_review_v5_gx784
heavy = [name for name in sys.modules if name == 'numpy' or name.startswith(('mpi4py', 'petsc4py', 'slepc4py', 'dolfinx', 'basix'))]
assert not heavy, heavy
"""
    subprocess.run(
        [sys.executable, "-c", code],
        check=True,
        capture_output=True,
        text=True,
    )


def test_supervisor_clock_and_watchdog_policy_are_available_on_ready_path():
    sample = service.clock_sample()
    assert sample["monotonic"] > 0
    assert sample["boottime"] is None or sample["boottime"] > 0
    checks = service._watchdog_checks(
        {"memory_policy": service.PHYSICAL_MEMORY_PRESSURE_POLICY}, {}
    )
    assert checks["physical_memory_pressure_policy"] is True


def test_subreaper_still_rejects_parent_with_existing_children(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    from benchmarks import subreaper_watchdog

    monkeypatch.setattr(subreaper_watchdog, "_children", lambda: {12345: (1, 1)})
    with pytest.raises(RuntimeError, match="dedicated parent with no existing children"):
        subreaper_watchdog.supervise(
            [sys.executable, "-c", "pass"],
            tmp_path / "unused-watchdog",
            wall_seconds=1.0,
        )
    assert not (tmp_path / "unused-watchdog").exists()
