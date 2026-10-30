import json

from scripts.task44_native_service import _atomic_write_json
from scripts.task44_service_startup import classify_service_startup

UNIT = "task44-sample-smoke2.service"
CAP_BYTES = 128 * 1024**3
CPUS = [8]


def _identity():
    return {
        "service_unit": UNIT,
        "active_state": "active",
        "main_pid": 1234,
        "main_pid_start_ticks": 5678,
        "invocation_id": "invocation-1",
        "control_group": "/user.slice/task44-sample-smoke2.service",
        "memory_max_bytes": CAP_BYTES,
        "memory_swap_max_bytes": 0,
        "restart": "no",
        "kill_mode": "control-group",
        "cpu_affinity": CPUS,
        "actual_process_cpu_affinity": CPUS,
    }


def _summary(identity):
    return {
        "classification": "COMPLETED",
        "task44_service": {
            "service_unit": UNIT,
            "service_gate_start": {
                "stop": False,
                "failures": [],
                "service": {
                    "unit": UNIT,
                    "main_pid": identity["main_pid"],
                    "invocation_id": identity["invocation_id"],
                    "control_group": identity["control_group"],
                    "memory_max_bytes": CAP_BYTES,
                    "cgroup_memory_max_bytes": CAP_BYTES,
                    "swap_max_bytes": 0,
                    "cgroup_swap_max_bytes": 0,
                    "swap_current_bytes": 0,
                    "cpu_affinity": "8",
                }
            },
        },
    }


def test_active_without_identity_remains_startup_pending():
    assert classify_service_startup(
        "active", None, None, unit=UNIT, cap_bytes=CAP_BYTES, cpu_affinity=CPUS
    ) == "startup_pending"


def test_active_with_valid_identity_is_ready_for_live_verification():
    assert classify_service_startup(
        "active", _identity(), None, unit=UNIT, cap_bytes=CAP_BYTES, cpu_affinity=CPUS
    ) == "active_identity_ready"


def test_active_to_completed_race_uses_matching_persisted_invocation():
    identity = _identity()
    assert classify_service_startup(
        "inactive", identity, _summary(identity),
        unit=UNIT, cap_bytes=CAP_BYTES, cpu_affinity=CPUS,
    ) == "completed"


def test_completed_summary_from_another_invocation_is_rejected():
    identity = _identity()
    summary = _summary(identity)
    summary["task44_service"]["service_gate_start"]["service"]["invocation_id"] = "other"
    assert classify_service_startup(
        "inactive", identity, summary,
        unit=UNIT, cap_bytes=CAP_BYTES, cpu_affinity=CPUS,
    ) == "failed"


def test_live_identity_with_wrong_process_affinity_is_invalid():
    identity = _identity()
    identity["actual_process_cpu_affinity"] = [9]
    assert classify_service_startup(
        "active", identity, None, unit=UNIT, cap_bytes=CAP_BYTES, cpu_affinity=CPUS
    ) == "identity_invalid"


def test_completed_receipt_survives_systemd_unit_collection():
    identity = _identity()
    assert classify_service_startup(
        "", identity, _summary(identity),
        unit=UNIT, cap_bytes=CAP_BYTES, cpu_affinity=CPUS,
    ) == "completed"


def test_service_receipt_is_published_as_complete_json(tmp_path):
    path = tmp_path / "service_identity.json"
    _atomic_write_json(path, {"status": "ready"})
    assert json.loads(path.read_text(encoding="utf-8")) == {"status": "ready"}
    assert [entry.name for entry in tmp_path.iterdir()] == ["service_identity.json"]
