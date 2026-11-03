"""Exact-case, explicit pre-numeric pause for the Gate-CD Fin0/STI z10 run."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from typing import Any, Callable, Mapping


PROFILE_IDENTITY = "task40_gate_cd_fin0_sti_z10_m8n2_p6_direct_v1"
READY_SCHEMA = "task40.gate_cd.z10_prelu_ready.v1"
RELEASE_SCHEMA = "task40.gate_cd.z10_prelu_release.v1"
ACCEPTED_SCHEMA = "task40.gate_cd.z10_prelu_release_accepted.v1"
MINIMUM_AVAILABLE_BYTES = 64 * 1024**3
RELEASE_AUTHORIZATION = "USER_APPROVED_EXACT_CASE_AFTER_272_CLEAR_AND_MEMORY_REVIEW"
_SHA256_LENGTH = 64
PRELU_ENVIRONMENT_FIELDS = {
    "ready_path": "TASK40_GATE_CD_PRELU_READY_PATH",
    "release_path": "TASK40_GATE_CD_PRELU_RELEASE_PATH",
    "accepted_path": "TASK40_GATE_CD_PRELU_ACCEPTED_PATH",
    "service_unit": "TASK40_GATE_CD_EXPECTED_UNIT",
    "attempt_id": "TASK40_GATE_CD_ATTEMPT_ID",
    "package_sha256": "TASK40_GATE_CD_PACKAGE_SHA256",
    "original272_unit": "TASK40_GATE_CD_ORIGINAL272_UNIT",
    "original272_invocation_id": "TASK40_GATE_CD_ORIGINAL272_INVOCATION_ID",
}


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _atomic_create_json(path: Path, value: Mapping[str, Any]) -> str:
    """Durably create a new JSON file without replacing prior attempt evidence."""

    path = path.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = _canonical_bytes(value)
    fd, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)
    return _sha256(raw)


def _effective_available_bytes() -> int:
    """Return host availability capped by any finite cgroup memory headroom."""

    meminfo = Path("/proc/meminfo").read_text(encoding="ascii")
    available_kib = next(
        int(line.split()[1])
        for line in meminfo.splitlines()
        if line.startswith("MemAvailable:")
    )
    available = available_kib * 1024
    cgroups = Path("/proc/self/cgroup").read_text(encoding="ascii").splitlines()
    unified = next((line.split(":", 2)[2] for line in cgroups if line.startswith("0::")), None)
    if unified is not None:
        current = Path("/sys/fs/cgroup") / unified.lstrip("/")
        for directory in (current, *current.parents):
            limit_path = directory / "memory.max"
            usage_path = directory / "memory.current"
            if not limit_path.is_file() or not usage_path.is_file():
                continue
            limit_text = limit_path.read_text(encoding="ascii").strip()
            if limit_text == "max":
                continue
            limit = int(limit_text)
            usage = int(usage_path.read_text(encoding="ascii").strip())
            available = min(available, max(0, limit - usage))
    else:
        for line in cgroups:
            fields = line.split(":", 2)
            if len(fields) != 3 or "memory" not in fields[1].split(","):
                continue
            relative = fields[2].lstrip("/")
            current = Path("/sys/fs/cgroup/memory") / relative
            for directory in (current, *current.parents):
                limit_path = directory / "memory.limit_in_bytes"
                usage_path = directory / "memory.usage_in_bytes"
                if not limit_path.is_file() or not usage_path.is_file():
                    continue
                limit = int(limit_path.read_text(encoding="ascii").strip())
                usage = int(usage_path.read_text(encoding="ascii").strip())
                if limit < 2**60:
                    available = min(available, max(0, limit - usage))
    return int(available)


def _validate_identity(identity: Mapping[str, Any]) -> dict[str, Any]:
    required = {
        "profile_identity",
        "run_id",
        "source_commit",
        "input_sha256",
        "physical_model_sha256",
        "resolved_config_sha256",
        "package_sha256",
        "service_unit",
        "invocation_id",
        "attempt_id",
        "output_directory",
        "mesh_plan_id",
        "mesh_plan_sha256",
        "active_mode_sha256",
        "original272_unit",
        "original272_invocation_id",
        "original272_run_id",
        "original272_run_summary_path",
        "original272_run_summary_sha256",
        "original272_start_receipt_path",
        "original272_start_receipt_sha256",
    }
    value = dict(identity)
    if set(value) != required:
        raise ValueError("pre-LU identity fields differ from the reviewed exact-case schema")
    if value["profile_identity"] != PROFILE_IDENTITY or value["run_id"] != PROFILE_IDENTITY:
        raise ValueError("pre-LU hook is restricted to the exact Fin0/STI z10 M8N2 profile")
    if not isinstance(value["source_commit"], str) or len(value["source_commit"]) not in (40, 64):
        raise ValueError("pre-LU identity has an invalid source commit")
    for key in (
        "input_sha256",
        "physical_model_sha256",
        "resolved_config_sha256",
        "package_sha256",
        "mesh_plan_sha256",
        "active_mode_sha256",
        "original272_run_summary_sha256",
        "original272_start_receipt_sha256",
    ):
        digest = value[key]
        if not isinstance(digest, str) or len(digest) != _SHA256_LENGTH or any(
            ch not in "0123456789abcdef" for ch in digest
        ):
            raise ValueError(f"pre-LU identity has an invalid {key}")
    for key in (
        "service_unit",
        "invocation_id",
        "attempt_id",
        "original272_unit",
        "original272_invocation_id",
    ):
        if not isinstance(value[key], str) or not value[key]:
            raise ValueError(f"pre-LU identity is missing {key}")
    for key in (
        "output_directory",
        "original272_run_summary_path",
        "original272_start_receipt_path",
    ):
        if not Path(str(value[key])).is_absolute():
            raise ValueError(f"pre-LU {key} must be absolute")
    return value


def validate_worker_environment(
    *,
    environment: Mapping[str, str | None],
    scope_document: Mapping[str, Any],
    attempt_id: str,
    attempt_cache_root: str | Path,
) -> dict[str, str]:
    """Bind pause variables to the reviewed runtime scope and attempt lease."""

    identity = scope_document.get("identity")
    route = identity.get("direct_route_contract") if isinstance(identity, dict) else None
    contract = route.get("pre_lu_pause") if isinstance(route, dict) else None
    original = (
        contract.get("release_requires_original272")
        if isinstance(contract, dict)
        else None
    )
    package_sha256 = scope_document.get("package_sha256")
    service_unit = scope_document.get("planned_systemd_user_unit")
    if (
        not isinstance(contract, dict)
        or not isinstance(original, dict)
        or scope_document.get("attempt_id") != attempt_id
        or not isinstance(package_sha256, str)
        or len(package_sha256) != _SHA256_LENGTH
        or any(ch not in "0123456789abcdef" for ch in package_sha256)
        or not isinstance(service_unit, str)
        or not service_unit.endswith(".service")
    ):
        raise ValueError("runtime scope lacks the exact package-bound z10 pause identity")

    evidence_root = Path(attempt_cache_root).resolve() / "pre_lu_pause"
    expected = {
        "ready_path": str(evidence_root / "ready.json"),
        "release_path": str(evidence_root / "release.json"),
        "accepted_path": str(evidence_root / "accepted.json"),
        "service_unit": service_unit,
        "attempt_id": attempt_id,
        "package_sha256": package_sha256,
        "original272_unit": original.get("unit"),
        "original272_invocation_id": original.get("invocation_id"),
    }
    observed = {
        field: environment.get(env_name)
        for field, env_name in PRELU_ENVIRONMENT_FIELDS.items()
    }
    mismatched = [
        field
        for field, expected_value in expected.items()
        if not isinstance(expected_value, str)
        or not expected_value
        or observed.get(field) != expected_value
    ]
    if mismatched:
        raise ValueError(
            "runtime pre-LU environment differs from its exact scope binding at "
            f"{sorted(mismatched)}"
        )
    return {
        env_name: str(environment[env_name])
        for env_name in PRELU_ENVIRONMENT_FIELDS.values()
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"pre-LU authorization file is unreadable: {path}") from exc
    if not isinstance(value, dict):
        raise ValueError("pre-LU authorization file must be a JSON object")
    return value


def _validate_release(
    release: Mapping[str, Any],
    *,
    identity: dict[str, Any],
    identity_sha256: str,
    ready_record_sha256: str,
    release_nonce: str,
    now: datetime,
) -> dict[str, Any]:
    value = dict(release)
    if value.get("schema") != RELEASE_SCHEMA:
        raise ValueError("pre-LU release schema is unsupported")
    if value.get("authorization") != RELEASE_AUTHORIZATION:
        raise ValueError("pre-LU release lacks explicit exact-case user authorization")
    if (
        value.get("identity") != identity
        or value.get("identity_sha256") != identity_sha256
        or value.get("ready_record_sha256") != ready_record_sha256
        or value.get("release_nonce") != release_nonce
    ):
        raise ValueError("pre-LU release does not bind the ready record and exact case")
    clearance = value.get("original272_clearance")
    if not isinstance(clearance, dict) or (
        clearance.get("unit") != identity["original272_unit"]
        or clearance.get("invocation_id") != identity["original272_invocation_id"]
        or clearance.get("run_id") != identity["original272_run_id"]
        or clearance.get("run_summary_path")
        != identity["original272_run_summary_path"]
        or clearance.get("run_summary_sha256")
        != identity["original272_run_summary_sha256"]
        or clearance.get("start_receipt_path")
        != identity["original272_start_receipt_path"]
        or clearance.get("start_receipt_sha256")
        != identity["original272_start_receipt_sha256"]
        or clearance.get("exit_status") != 0
        or clearance.get("result_classification") != "worker_exit0"
        or clearance.get("run_status") != "finished"
        or clearance.get("exit_code") != 0
        or clearance.get("descendants_cleared") is not True
        or clearance.get("remaining_child_pids") != []
        or clearance.get("unit_inactive") is not True
    ):
        raise ValueError("pre-LU release lacks verified original-272 completion and clearing")
    memory = value.get("memory_review")
    if not isinstance(memory, dict):
        raise ValueError("pre-LU release lacks fresh memory-review evidence")
    available_at_review = memory.get("effective_available_bytes")
    captured = memory.get("captured_utc")
    if (
        type(available_at_review) is not int
        or available_at_review < MINIMUM_AVAILABLE_BYTES
        or type(memory.get("minimum_available_bytes")) is not int
        or memory.get("minimum_available_bytes") != MINIMUM_AVAILABLE_BYTES
        or not isinstance(captured, str)
    ):
        raise ValueError("pre-LU memory review does not satisfy the exact 64 GiB floor")
    try:
        captured_at = datetime.fromisoformat(captured.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("pre-LU memory-review timestamp is invalid") from exc
    if captured_at.tzinfo is None:
        raise ValueError("pre-LU memory-review timestamp must include a timezone")
    age = (now - captured_at.astimezone(timezone.utc)).total_seconds()
    if age < -30.0 or age > 900.0:
        raise ValueError("pre-LU memory review is stale or timestamped in the future")
    return value


def _verify_original272_clearance(identity: Mapping[str, Any]) -> dict[str, Any]:
    """Recheck the bound 272 receipts and live user-systemd/cgroup state."""

    exact = _validate_identity(identity)
    summary_path = Path(exact["original272_run_summary_path"])
    summary_raw = summary_path.read_bytes()
    summary_sha256 = _sha256(summary_raw)
    if summary_sha256 != exact["original272_run_summary_sha256"]:
        return {"verified": False, "reason": "original272_run_summary_sha_mismatch"}
    summary = _read_json(summary_path)
    resource = summary.get("resource_authority")
    if (
        summary.get("run_id") != exact["original272_run_id"]
        or summary.get("status") != "finished"
        or summary.get("exit_status") != 0
        or summary.get("result_classification") != "worker_exit0"
        or not isinstance(resource, dict)
        or resource.get("classification") != "COMPLETED"
        or resource.get("descendants_cleared") is not True
        or resource.get("remaining_child_pids") != []
    ):
        return {"verified": False, "reason": "original272_summary_not_terminal_clear"}

    start_path = Path(exact["original272_start_receipt_path"])
    start_raw = start_path.read_bytes()
    start_sha256 = _sha256(start_raw)
    if start_sha256 != exact["original272_start_receipt_sha256"]:
        return {"verified": False, "reason": "original272_start_receipt_sha_mismatch"}
    if (
        exact["original272_unit"].encode("utf-8") not in start_raw
        or exact["original272_invocation_id"].encode("ascii") not in start_raw
    ):
        return {"verified": False, "reason": "original272_start_receipt_identity_mismatch"}

    properties = (
        "LoadState,ActiveState,SubState,InvocationID,MainPID,NRestarts,Result,"
        "ExecMainCode,ExecMainStatus,ControlGroup"
    )
    try:
        process = subprocess.run(
            [
                "systemctl",
                "--user",
                "show",
                exact["original272_unit"],
                f"--property={properties}",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"verified": False, "reason": f"original272_systemd_unavailable:{exc}"}
    systemd = dict(
        line.split("=", 1)
        for line in process.stdout.splitlines()
        if "=" in line
    )
    if (
        systemd.get("ActiveState") != "inactive"
        or systemd.get("MainPID", "0") != "0"
        or systemd.get("NRestarts", "0") != "0"
        or systemd.get("InvocationID", "")
        not in ("", exact["original272_invocation_id"])
        or systemd.get("Result", "success") not in ("", "success")
        or systemd.get("ExecMainStatus", "0") not in ("", "0")
    ):
        return {
            "verified": False,
            "reason": "original272_systemd_not_inactive_success",
            "systemd": systemd,
        }
    control_group = systemd.get("ControlGroup", "")
    if control_group:
        cgroup = Path("/sys/fs/cgroup") / control_group.lstrip("/")
        events_path = cgroup / "cgroup.events"
        if events_path.exists():
            events = dict(
                line.split()
                for line in events_path.read_text(encoding="ascii").splitlines()
            )
            if events.get("populated") != "0":
                return {
                    "verified": False,
                    "reason": "original272_cgroup_still_populated",
                    "cgroup_events": events,
                }
    return {
        "verified": True,
        "systemd": systemd,
        "run_summary_sha256": summary_sha256,
        "start_receipt_sha256": start_sha256,
        "descendants_cleared": True,
        "remaining_child_pids": [],
    }


def wait_at_pre_numeric_pause(
    *,
    identity: Mapping[str, Any],
    ready_path: str | Path,
    release_path: str | Path,
    accepted_path: str | Path,
    matrix_facts: Mapping[str, Any],
    ledger: Any,
    original272_clearance_reader: Callable[
        [Mapping[str, Any]], Mapping[str, Any]
    ] = _verify_original272_clearance,
    available_bytes_reader: Callable[[], int] = _effective_available_bytes,
    sleep: Callable[[float], None] = time.sleep,
    poll_seconds: float = 1.0,
    heartbeat_seconds: float = 30.0,
) -> dict[str, Any]:
    """Persist exact readiness, then block until a matching human release arrives."""

    exact_identity = _validate_identity(identity)
    ready = Path(ready_path).resolve()
    release = Path(release_path).resolve()
    accepted = Path(accepted_path).resolve()
    if ready == release or ready == accepted or release == accepted:
        raise ValueError("pre-LU ready, release, and accepted paths must be distinct")
    if release.exists():
        raise FileExistsError("pre-LU release already exists before the ready identity")
    if ready.exists() or accepted.exists():
        raise FileExistsError("pre-LU attempt evidence already exists; use a fresh attempt")
    identity_sha256 = _sha256(_canonical_bytes(exact_identity))
    release_nonce = os.urandom(24).hex()
    ready_record = {
        "schema": READY_SCHEMA,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "identity": exact_identity,
        "identity_sha256": identity_sha256,
        "release_nonce": release_nonce,
        "matrix_facts": dict(matrix_facts),
        "required_original272_clearance": {
            "unit": exact_identity["original272_unit"],
            "invocation_id": exact_identity["original272_invocation_id"],
            "run_id": exact_identity["original272_run_id"],
            "run_summary_path": exact_identity["original272_run_summary_path"],
            "run_summary_sha256": exact_identity[
                "original272_run_summary_sha256"
            ],
            "start_receipt_path": exact_identity[
                "original272_start_receipt_path"
            ],
            "start_receipt_sha256": exact_identity[
                "original272_start_receipt_sha256"
            ],
            "exit_status": 0,
            "result_classification": "worker_exit0",
            "run_status": "finished",
            "exit_code": 0,
            "descendants_cleared": True,
            "remaining_child_pids": [],
            "unit_inactive": True,
        },
        "minimum_available_bytes": MINIMUM_AVAILABLE_BYTES,
        "ready_path": str(ready),
        "release_path": str(release),
    }
    ready_sha256 = _atomic_create_json(ready, ready_record)
    ledger.set_phase("pre_lu_pause")
    ledger.marker(
        "task40_z10_pre_lu_pause_ready",
        {
            "identity_sha256": identity_sha256,
            "ready_record_sha256": ready_sha256,
            "release_nonce": release_nonce,
            "ready_path": str(ready),
            "release_path": str(release),
            "matrix_facts": dict(matrix_facts),
            "numeric_calls": 0,
            "factor_numeric_started": False,
        },
    )

    last_heartbeat = time.monotonic()
    while True:
        if release.exists():
            release_record = _validate_release(
                _read_json(release),
                identity=exact_identity,
                identity_sha256=identity_sha256,
                ready_record_sha256=ready_sha256,
                release_nonce=release_nonce,
                now=datetime.now(timezone.utc),
            )
            clearance = dict(original272_clearance_reader(exact_identity))
            if clearance.get("verified") is not True:
                ledger.marker(
                    "task40_z10_pre_lu_pause_waiting_for_original272_clearance",
                    {
                        "identity_sha256": identity_sha256,
                        "ready_record_sha256": ready_sha256,
                        "reason": clearance.get("reason", "clearance_not_verified"),
                        "numeric_calls": 0,
                        "factor_numeric_started": False,
                    },
                )
                sleep(poll_seconds)
                continue
            effective_available = int(available_bytes_reader())
            if effective_available >= MINIMUM_AVAILABLE_BYTES:
                accepted_record = {
                    "schema": ACCEPTED_SCHEMA,
                    "accepted_utc": datetime.now(timezone.utc).isoformat(),
                    "identity_sha256": identity_sha256,
                    "ready_record_sha256": ready_sha256,
                    "release_sha256": _sha256(release.read_bytes()),
                    "effective_available_bytes_at_release": effective_available,
                    "minimum_available_bytes": MINIMUM_AVAILABLE_BYTES,
                    "numeric_calls_before_release": 0,
                }
                accepted_sha256 = _atomic_create_json(accepted, accepted_record)
                ledger.marker(
                    "task40_z10_pre_lu_pause_released",
                    {
                        **accepted_record,
                        "accepted_record_sha256": accepted_sha256,
                        "factor_numeric_started": False,
                    },
                )
                ledger.set_phase("solve")
                return {
                    "ready_record_sha256": ready_sha256,
                    "release_sha256": accepted_record["release_sha256"],
                    "accepted_record_sha256": accepted_sha256,
                    "effective_available_bytes_at_release": effective_available,
                    "authorization": release_record["authorization"],
                }
        now_monotonic = time.monotonic()
        if now_monotonic - last_heartbeat >= heartbeat_seconds:
            ledger.marker(
                "task40_z10_pre_lu_pause_waiting",
                {
                    "identity_sha256": identity_sha256,
                    "ready_record_sha256": ready_sha256,
                    "release_file_present": release.exists(),
                    "effective_available_bytes": int(available_bytes_reader()),
                    "minimum_available_bytes": MINIMUM_AVAILABLE_BYTES,
                    "numeric_calls": 0,
                    "factor_numeric_started": False,
                },
            )
            last_heartbeat = now_monotonic
        sleep(poll_seconds)
