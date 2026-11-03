"""No-solve contracts for the Gate-CD Fin0/STI z10 pre-LU pause."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.geometry.task40_gate_cd_mesh_plan import (
    GATE_CD_FIN0_STI_Z10_CELLS,
    GATE_CD_FIN0_STI_Z10_PROFILE_ID,
    GATE_CD_FIN0_STI_Z10_STATIC_PLAN,
    GATE_CD_P6_GLOBAL_DOFS,
    GATE_CD_STATIC_PLAN,
)
from src.io.native_capacity_profile import (
    TASK40_GATE_CD_FIN0_STI_Z10_M8N2_P6_DIRECT_PROFILE,
    native_profile_facts,
)
from src.runners import task40_gate_cd_prelu_pause as pause
from src.runners.p6_condensed_direct import _factor_same_matrix


def _identity(tmp_path: Path) -> dict:
    return {
        "profile_identity": pause.PROFILE_IDENTITY,
        "run_id": pause.PROFILE_IDENTITY,
        "source_commit": "a" * 40,
        "input_sha256": "b" * 64,
        "physical_model_sha256": "c" * 64,
        "resolved_config_sha256": "d" * 64,
        "package_sha256": "e" * 64,
        "service_unit": "task40-gcd-z10-test.service",
        "invocation_id": "f" * 32,
        "attempt_id": "z10-test-20261104",
        "output_directory": str((tmp_path / "output").resolve()),
        "mesh_plan_id": GATE_CD_FIN0_STI_Z10_PROFILE_ID,
        "mesh_plan_sha256": "1" * 64,
        "active_mode_sha256": "2" * 64,
        "original272_unit": "task40-gcd-m8n2-9bf54c110b.service",
        "original272_invocation_id": "3" * 32,
        "original272_run_id": "task40_gate_cd_0p7_mapped_m8n2_p6_direct_v1",
        "original272_run_summary_path": str(
            (tmp_path / "original272" / "run_summary.json").resolve()
        ),
        "original272_run_summary_sha256": "4" * 64,
        "original272_start_receipt_path": str(
            (tmp_path / "original272" / "start_receipt.json").resolve()
        ),
        "original272_start_receipt_sha256": "5" * 64,
    }


class _Ledger:
    def __init__(self):
        self.phases = []
        self.markers = []

    def set_phase(self, phase):
        self.phases.append(phase)

    def marker(self, stage, facts):
        self.markers.append((stage, dict(facts)))


def _write_release(path: Path, ready_path: Path, identity: dict) -> None:
    ready_raw = ready_path.read_bytes()
    ready = json.loads(ready_raw)
    clearance = ready["required_original272_clearance"]
    release = {
        "schema": pause.RELEASE_SCHEMA,
        "authorization": pause.RELEASE_AUTHORIZATION,
        "identity": identity,
        "identity_sha256": pause._sha256(pause._canonical_bytes(identity)),
        "ready_record_sha256": pause._sha256(ready_raw),
        "release_nonce": ready["release_nonce"],
        "original272_clearance": clearance,
        "memory_review": {
            "captured_utc": datetime.now(timezone.utc).isoformat(),
            "effective_available_bytes": 128 * 1024**3,
            "minimum_available_bytes": pause.MINIMUM_AVAILABLE_BYTES,
        },
    }
    path.write_bytes(pause._canonical_bytes(release))


def test_z10_mesh_and_profile_are_a_distinct_fixed_window_diagnostic():
    plan = GATE_CD_FIN0_STI_Z10_STATIC_PLAN
    assert GATE_CD_FIN0_STI_Z10_CELLS == (5, 240, 32)
    assert plan.static_facts["global_cell_count"] == 38_400
    assert plan.static_facts["global_p6_dof_rows"] > GATE_CD_P6_GLOBAL_DOFS
    inserted = [float(value) for value in plan.z if 0.0 <= value <= 50.0]
    assert inserted == [float(value) for value in range(0, 51, 5)]
    original_elsewhere = [
        float(value) for value in GATE_CD_STATIC_PLAN.z
        if value < 0.0 or value > 50.0
    ]
    z10_elsewhere = [
        float(value) for value in plan.z if value < 0.0 or value > 50.0
    ]
    assert z10_elsewhere == original_elsewhere

    facts = native_profile_facts(TASK40_GATE_CD_FIN0_STI_Z10_M8N2_P6_DIRECT_PROFILE)
    options = facts["component_options"]
    assert facts["full_dtn_status"] == "FULL_DTN_NOT_VERIFIED"
    assert options["mesh_plan_id"] == GATE_CD_FIN0_STI_Z10_PROFILE_ID
    assert options["mesh_axis_cell_counts"] == [5, 240, 32]
    assert options["expected_global_cell_count"] == 38_400
    assert facts["campaign_authorization"]["direct_route"]["pre_lu_pause"] == (
        facts["campaign_authorization"]["pre_lu_pause"]
    )


def test_factor_hook_is_after_symbolic_and_before_any_numeric_call():
    events = []

    class FakeFactor:
        symbolic_calls = 0
        numeric_calls = 0
        solve_calls = 0
        preferred_ordering = "fake-ordering"

        def symbolic(self, matrix):
            self.symbolic_calls += 1
            events.append("symbolic")

        def info(self):
            return {"symbolic_complete": self.symbolic_calls == 1}

        def numeric(self, matrix):
            events.append("numeric")
            self.numeric_calls += 1

        def refinement_settings(self):
            return {"refinement": "fake"}

        def solve(self, rhs, solution):
            events.append("solve")
            self.solve_calls += 1

    factor = FakeFactor()
    matrix = object()

    def marker(stage, _facts):
        events.append(stage)

    def pause_hook(current_factor, current_matrix):
        assert current_matrix is matrix
        assert current_factor.symbolic_calls == 1
        assert current_factor.numeric_calls == 0
        assert current_factor.solve_calls == 0
        events.append("prelu_pause")

    _factor_same_matrix(
        factor,
        matrix,
        rhs=object(),
        solution=object(),
        marker=marker,
        pre_numeric_hook=pause_hook,
    )
    assert events.index("p6_mumps_symbolic_complete") < events.index("prelu_pause")
    assert events.index("prelu_pause") < events.index("numeric")
    assert events.index("numeric") < events.index("p6_mumps_numeric_complete")
    assert factor.symbolic_calls == factor.numeric_calls == factor.solve_calls == 1


def test_pause_waits_for_exact_release_and_live_original272_clearance(tmp_path):
    identity = _identity(tmp_path)
    ready = tmp_path / "ready.json"
    release = tmp_path / "release.json"
    accepted = tmp_path / "accepted.json"
    ledger = _Ledger()

    def sleep(_seconds):
        if ready.exists() and not release.exists():
            _write_release(release, ready, identity)

    result = pause.wait_at_pre_numeric_pause(
        identity=identity,
        ready_path=ready,
        release_path=release,
        accepted_path=accepted,
        matrix_facts={"matrix_shape": [128, 128]},
        ledger=ledger,
        original272_clearance_reader=lambda _identity: {"verified": True},
        available_bytes_reader=lambda: 128 * 1024**3,
        sleep=sleep,
        heartbeat_seconds=0.0,
    )
    assert result["authorization"] == pause.RELEASE_AUTHORIZATION
    assert json.loads(accepted.read_text())["numeric_calls_before_release"] == 0
    assert ledger.phases == ["pre_lu_pause", "solve"]
    assert ledger.markers[0][0] == "task40_z10_pre_lu_pause_ready"
    assert ledger.markers[-1][0] == "task40_z10_pre_lu_pause_released"
    assert all(row[1].get("numeric_calls", 0) == 0 for row in ledger.markers)


def test_pause_does_not_release_when_original272_is_not_cleared(tmp_path):
    identity = _identity(tmp_path)
    ready = tmp_path / "ready.json"
    release = tmp_path / "release.json"
    accepted = tmp_path / "accepted.json"
    ledger = _Ledger()
    sleep_calls = 0

    class StopWaiting(Exception):
        pass

    def sleep(_seconds):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls == 1:
            _write_release(release, ready, identity)
        else:
            raise StopWaiting

    with pytest.raises(StopWaiting):
        pause.wait_at_pre_numeric_pause(
            identity=identity,
            ready_path=ready,
            release_path=release,
            accepted_path=accepted,
            matrix_facts={},
            ledger=ledger,
            original272_clearance_reader=lambda _identity: {
                "verified": False,
                "reason": "unit_still_active",
            },
            available_bytes_reader=lambda: 128 * 1024**3,
            sleep=sleep,
            heartbeat_seconds=0.0,
        )
    assert ready.exists()
    assert not accepted.exists()
    assert any(
        stage == "task40_z10_pre_lu_pause_waiting_for_original272_clearance"
        for stage, _facts in ledger.markers
    )
    assert all(row[1].get("numeric_calls", 0) == 0 for row in ledger.markers)


def test_pause_rejects_a_release_present_before_the_ready_record(tmp_path):
    identity = _identity(tmp_path)
    ready = tmp_path / "ready.json"
    release = tmp_path / "release.json"
    accepted = tmp_path / "accepted.json"
    release.write_text("{}", encoding="utf-8")
    with pytest.raises(FileExistsError, match="already exists before the ready"):
        pause.wait_at_pre_numeric_pause(
            identity=identity,
            ready_path=ready,
            release_path=release,
            accepted_path=accepted,
            matrix_facts={},
            ledger=_Ledger(),
        )


def test_live_clearance_verifier_checks_bound_receipts_and_inactive_unit(
    tmp_path, monkeypatch
):
    identity = _identity(tmp_path)
    original = tmp_path / "original272"
    original.mkdir()
    summary = {
        "run_id": identity["original272_run_id"],
        "status": "finished",
        "exit_status": 0,
        "result_classification": "worker_exit0",
        "resource_authority": {
            "classification": "COMPLETED",
            "descendants_cleared": True,
            "remaining_child_pids": [],
        },
    }
    summary_raw = pause._canonical_bytes(summary)
    summary_path = Path(identity["original272_run_summary_path"])
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_bytes(summary_raw)
    identity["original272_run_summary_sha256"] = pause._sha256(summary_raw)
    start_path = Path(identity["original272_start_receipt_path"])
    start_raw = (
        identity["original272_unit"] + "\n"
        + identity["original272_invocation_id"] + "\n"
    ).encode()
    start_path.write_bytes(start_raw)
    identity["original272_start_receipt_sha256"] = pause._sha256(start_raw)

    class Completed:
        returncode = 0
        stdout = (
            "LoadState=not-found\nActiveState=inactive\nSubState=dead\n"
            "InvocationID=\nMainPID=0\nNRestarts=0\nResult=success\n"
            "ExecMainCode=0\nExecMainStatus=0\nControlGroup=\n"
        )

    monkeypatch.setattr(pause.subprocess, "run", lambda *_args, **_kwargs: Completed())
    result = pause._verify_original272_clearance(identity)
    assert result["verified"] is True
    assert result["descendants_cleared"] is True
    assert result["remaining_child_pids"] == []


def test_worker_environment_is_bound_to_scope_package_and_attempt(tmp_path):
    identity = _identity(tmp_path)
    cache_root = tmp_path / "attempt-cache"
    original = {
        "unit": identity["original272_unit"],
        "invocation_id": identity["original272_invocation_id"],
    }
    scope = {
        "attempt_id": identity["attempt_id"],
        "planned_systemd_user_unit": identity["service_unit"],
        "package_sha256": identity["package_sha256"],
        "identity": {
            "direct_route_contract": {
                "pre_lu_pause": {"release_requires_original272": original}
            }
        },
    }
    pause_root = cache_root.resolve() / "pre_lu_pause"
    values = {
        "ready_path": str(pause_root / "ready.json"),
        "release_path": str(pause_root / "release.json"),
        "accepted_path": str(pause_root / "accepted.json"),
        "service_unit": identity["service_unit"],
        "attempt_id": identity["attempt_id"],
        "package_sha256": identity["package_sha256"],
        "original272_unit": identity["original272_unit"],
        "original272_invocation_id": identity["original272_invocation_id"],
    }
    environment = {
        env_name: values[field]
        for field, env_name in pause.PRELU_ENVIRONMENT_FIELDS.items()
    }
    assert pause.validate_worker_environment(
        environment=environment,
        scope_document=scope,
        attempt_id=identity["attempt_id"],
        attempt_cache_root=cache_root,
    ) == environment

    environment["TASK40_GATE_CD_PACKAGE_SHA256"] = "9" * 64
    with pytest.raises(ValueError, match="exact scope binding"):
        pause.validate_worker_environment(
            environment=environment,
            scope_document=scope,
            attempt_id=identity["attempt_id"],
            attempt_cache_root=cache_root,
        )
