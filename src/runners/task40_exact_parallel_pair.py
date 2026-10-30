"""Fail-closed admission contract for the one reviewed Task40 FE pair.

This module contains no solver code.  It validates the static pair scope,
serializes the short fresh/submission handoff, and verifies a peer's live
service/process/provenance binding before a second exact-pair member may start.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
from contextlib import ExitStack, contextmanager
from pathlib import Path

from src.io.input_loader import InputError

PAIR_ID = "task40para_phi90_g3_m8_n64__ten_layer_m7_n9_v1"
PAIR_SCOPE_RELATIVE_PATH = Path(
    "docs/task40para_phi90_multilayer5nm_exec/evidence/preflight/"
    "exact_parallel_pair_scope.json"
)
PAIR_SCOPE_SCHEMA = "task40.exact_parallel_pair_scope.v1"
LIVE_BINDING_SCHEMA = "task40.exact_parallel_pair_live_binding.v1"
PAIR_SCOPE_PATH_ENV = "TASK40_EXACT_PARALLEL_PAIR_SCOPE_PATH"
PAIR_SCOPE_SHA_ENV = "TASK40_EXACT_PARALLEL_PAIR_SCOPE_SHA256"
PAIR_BINDING_DIRECTORY_ENV = "TASK40_EXACT_PARALLEL_PAIR_BINDING_DIRECTORY"
PAIR_SCOPE_SHA256 = "4b4cc6270c16429e72eec4b6af34d4af4b535f49989e729919007d84302f74be"
PAIR_HANDSHAKE_PATH = Path(
    "/tmp/task40para_phi90_g3_m8_n64__ten_layer_m7_n9.handshake.lock"
)
PAIR_LOCK_PATH = Path(
    "/tmp/task40para_phi90_g3_m8_n64__ten_layer_m7_n9.pair.lock"
)
CANONICAL_HEAVY_LOCK_PATH = Path(
    "/home/fenics/Projects/Maxwell3D-Lab/native-capacity-heavy.lock"
)
CANONICAL_COMMON_REPOSITORY = Path(
    "/home/fenics/Projects/Maxwell3D-Lab/task-repository.git"
)

COORDINATION_SHA256 = "4b8d262f935caa91e61b07a0127a5cd07137ba5fd939d9ea9b38e2cd10deee3b"
PROPOSAL_V2_SHA256 = "7446256d20e2447f3cfc442f7289aefb5a6dadb911dea4777fbd580ba89eb57e"
INVENTORY_SHA256 = "6679c4c7fc72be55d65268fc5ff4da40eb982abbbe4e2509fcf2b0c2363f11c5"

MEMBERS = {
    "0p7nm_g3_m8_n64": {
        "profile_identity": "task40para_phi90_0p7_D07C_G3_M8_N64_p6_direct_v1",
        "run_id": "task40para_phi90_0p7_D07C_G3_M8_N64_p6_direct_v1",
        "mode_count": 4488,
        "mode_sha256": "e4cef2ecadaab2563a46592dfe31df04aa47bc113f3a69e1ac0ecd70cebf2ef0",
        "supervisor_cpu": 9,
        "worker_cpu": 24,
    },
    "5nm_ten_layer_m7_n9": {
        "profile_identity": "task40para_phi90_5_TEN_LAYER_M7_N9_p6_direct_v1",
        "run_id": "task40para_phi90_5_TEN_LAYER_M7_N9_p6_direct_v1",
        "mode_count": 1140,
        "mode_sha256": "d9116f9f4281e04594959cdad4f320d84bd6fc057f0c6aea0026f8bccc3088b0",
        "supervisor_cpu": 25,
        "worker_cpu": 26,
    },
}
PROFILE_TO_ROLE = {
    row["profile_identity"]: role for role, row in MEMBERS.items()
}
RUN_TO_ROLE = {row["run_id"]: role for role, row in MEMBERS.items()}
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")
_INVOCATION_ID = re.compile(r"^[0-9a-f]{32}$")


def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _fsync_parent_directory(path: Path) -> None:
    directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def _read_json(path: Path, label: str) -> tuple[dict, bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f"Task40 exact-pair {label} is unreadable: {exc}") from exc
    if not isinstance(value, dict):
        raise InputError(f"Task40 exact-pair {label} must contain a JSON object")
    return value, raw


def pair_scope_path(repository_root: str | Path) -> Path:
    return Path(repository_root).resolve() / PAIR_SCOPE_RELATIVE_PATH


def load_pair_scope(
    repository_root: str | Path | None = None,
    *,
    scope_path: str | Path | None = None,
    expected_sha256: str | None = None,
) -> dict:
    """Load the exact two-member scope and verify its copied review receipts."""
    configured_path = scope_path or os.environ.get(PAIR_SCOPE_PATH_ENV)
    if configured_path is None:
        if repository_root is None:
            raise InputError("Task40 exact-pair scope path is not configured")
        configured_path = pair_scope_path(repository_root)
    scope_path = Path(configured_path).resolve()
    if repository_root is None:
        if len(scope_path.parents) < 5:
            raise InputError("Task40 exact-pair scope path is outside the reviewed repository layout")
        root = scope_path.parents[4]
    else:
        root = Path(repository_root).resolve()
    scope, raw = _read_json(scope_path, "scope")
    expected_sha = expected_sha256 or os.environ.get(PAIR_SCOPE_SHA_ENV) or PAIR_SCOPE_SHA256
    if expected_sha is None:
        raise InputError("Task40 exact-pair scope SHA256 is not configured")
    if str(expected_sha).lower() != PAIR_SCOPE_SHA256.lower():
        raise InputError("Task40 exact-pair scope SHA256 differs from the source-pinned review")
    if _sha256_bytes(raw) != str(expected_sha).lower():
        raise InputError("Task40 exact-pair scope SHA256 mismatch")
    if scope.get("schema") != PAIR_SCOPE_SCHEMA or scope.get("pair_id") != PAIR_ID:
        raise InputError("Task40 exact-pair scope schema or pair id is unsupported")
    if scope.get("status") != "PAIR_SCOPE_AND_CPU_PLAN_REVIEW_PASS_NOT_FRESH_OR_PACKAGE_RELEASE":
        raise InputError("Task40 exact-pair scope has not passed its bounded scope review")
    if scope.get("max_concurrent_fe_cases") != 2:
        raise InputError("Task40 exact-pair scope must cap the window at two FE cases")

    member_rows = scope.get("members")
    if not isinstance(member_rows, list) or len(member_rows) != 2:
        raise InputError("Task40 exact-pair scope must contain exactly two members")
    observed = {
        (row.get("role"), row.get("profile_identity"), row.get("run_id"),
         row.get("mode_count"), row.get("mode_sha256"))
        for row in member_rows if isinstance(row, dict)
    }
    expected = {
        (role, data["profile_identity"], data["run_id"], data["mode_count"], data["mode_sha256"])
        for role, data in MEMBERS.items()
    }
    if observed != expected:
        raise InputError("Task40 exact-pair member identities/mode inventories differ from review")

    lock = scope.get("canonical_host_lock", {})
    if (
        lock.get("path") != str(CANONICAL_HEAVY_LOCK_PATH)
        or lock.get("pair_lock_path") != str(PAIR_LOCK_PATH)
        or lock.get("handshake_lock_path") != str(PAIR_HANDSHAKE_PATH)
        or lock.get("pair_membership_lock_mode") != "shared_nonblocking"
        or lock.get("all_non_pair_native_runs_lock_mode") != "exclusive_nonblocking"
        or lock.get("canonical_lock_must_preexist") is not True
        or lock.get("keep_canonical_lock") is not True
    ):
        raise InputError("Task40 exact-pair canonical lock contract differs from review")

    cpu = scope.get("cpu_reservation", {})
    if cpu.get("assignment_is_pair_local_not_exclusive_host_ownership") is not True:
        raise InputError("Task40 pair CPU reservations must remain pair-local")
    for role, member in MEMBERS.items():
        row = next(item for item in member_rows if item.get("role") == role)
        reservation = cpu.get("g3_m8_n64" if role.startswith("0p7") else "ten_layer_m7_n9", {})
        expected_topology = reservation.get("expected_topology")
        expected_cpus = {str(member["supervisor_cpu"]), str(member["worker_cpu"])}
        if (
            row.get("cpu_reservation_ref") != (
                "cpu_reservation.g3_m8_n64" if role.startswith("0p7")
                else "cpu_reservation.ten_layer_m7_n9"
            )
            or reservation.get("supervisor_and_mpi_cpu") != member["supervisor_cpu"]
            or reservation.get("worker_cpu") != member["worker_cpu"]
            or not isinstance(expected_topology, dict)
            or set(expected_topology) != expected_cpus
            or any(
                not isinstance(topology, dict)
                or type(topology.get("package")) is not int
                or type(topology.get("core")) is not int
                or topology.get("thread_siblings") != cpu
                for cpu, topology in expected_topology.items()
            )
            or len({
                (topology["package"], topology["core"])
                for topology in expected_topology.values()
            }) != 2
        ):
            raise InputError("Task40 exact-pair CPU reservation differs from reviewed 9/24 and 25/26")

    admission = scope.get("admission_contract", {})
    required_contract = {
        "first_member_may_start_without_peer": True,
        "first_member_must_publish_live_binding_before_handshake_release": True,
        "second_member_must_bind_exact_active_peer": True,
        "second_member_may_overlap_peer_runtime": True,
        "fresh_and_submission_handshakes_are_serialized": True,
        "pending_peer_is_not_active": True,
        "unknown_active_heavy_jobs": "reject",
        "max_pair_members_active": 2,
        "minimum_available_bytes": 64 * 1024**3,
        "fixed_rss_cap_bytes": None,
        "swap_policy": "observe_only",
        "pss_policy": "disabled_by_profile",
        "uss_policy": "disabled_by_profile",
    }
    if any(admission.get(key) != value for key, value in required_contract.items()):
        raise InputError("Task40 exact-pair admission contract is incomplete or changed")

    receipts = scope.get("reviewer_coordination", {})
    receipt_pairs = (
        (receipts.get("path"), COORDINATION_SHA256, "coordination"),
        (receipts.get("proposal_path"), PROPOSAL_V2_SHA256, "proposal v2"),
        (receipts.get("inventory_receipt_path"), INVENTORY_SHA256, "G3 inventory"),
        (
            receipts.get("canonical_lock_correction_path"),
            receipts.get("canonical_lock_correction_sha256"),
            "canonical lock path correction",
        ),
    )
    for relative, expected_sha, label in receipt_pairs:
        if not relative:
            raise InputError(f"Task40 exact-pair scope lacks the {label} receipt path")
        _, raw = _read_json(root / relative, label)
        if _sha256_bytes(raw) != expected_sha:
            raise InputError(f"Task40 exact-pair {label} receipt SHA256 mismatch")
    if receipts.get("proposal_sha256") != PROPOSAL_V2_SHA256:
        raise InputError("Task40 exact-pair scope does not bind the corrected proposal v2")
    if receipts.get("inventory_receipt_sha256") != INVENTORY_SHA256:
        raise InputError("Task40 exact-pair scope does not bind the corrected G3 inventory")
    return scope


def role_for_identity(profile_identity: str, run_id: str) -> str:
    role = PROFILE_TO_ROLE.get(str(profile_identity))
    if role is None or MEMBERS[role]["run_id"] != str(run_id):
        raise InputError("Task40 exact-pair request is outside the two reviewed identities")
    return role


def pair_role_if_member(profile_identity: str, run_id: str) -> str | None:
    """Return a reviewed pair role, rejecting a known profile with a wrong run id."""
    profile = str(profile_identity)
    if profile not in PROFILE_TO_ROLE:
        return None
    return role_for_identity(profile, str(run_id))


def validate_active_roles(active_roles: list[str], *, current_role: str) -> str:
    """Reject duplicate-role, unknown-member, and third-run fresh snapshots."""
    if current_role not in MEMBERS:
        raise InputError("Task40 exact-pair current role is unknown")
    if len(active_roles) > 1:
        raise InputError("Task40 exact-pair fresh snapshot already contains two active members")
    if len(active_roles) != len(set(active_roles)):
        raise InputError("Task40 exact-pair fresh snapshot repeats a role")
    if any(role not in MEMBERS for role in active_roles):
        raise InputError("Task40 exact-pair fresh snapshot contains an unknown active identity")
    if current_role in active_roles:
        raise InputError("Task40 exact-pair same-role duplicate launch is not authorized")
    return "first_member" if not active_roles else "second_member"


def acquire_pair_handshake(path: str | Path = PAIR_HANDSHAKE_PATH):
    """Take the short, exclusive fresh/submission lock without waiting/retrying."""
    stream = Path(path).open("a")  # noqa: SIM115 - returned stream holds the flock
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        stream.close()
        raise InputError("Task40 exact-pair fresh/submission handshake is already held") from exc
    return stream


def release_pair_handshake(stream) -> None:
    if stream is None:
        return
    try:
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    finally:
        stream.close()


def pair_member_registry_path(role: str, *, directory: str | Path = "/tmp") -> Path:
    if role not in MEMBERS:
        raise InputError("Task40 exact-pair registry role is unknown")
    return Path(directory) / f"{PAIR_ID}.{role}.live.json"


def pair_member_runtime_lock_path(role: str, *, directory: str | Path = "/tmp") -> Path:
    if role not in MEMBERS:
        raise InputError("Task40 exact-pair runtime-lock role is unknown")
    return Path(directory) / f"{PAIR_ID}.{role}.runtime.lock"


def pair_submission_receipt_path(role: str, *, directory: str | Path = "/tmp") -> Path:
    if role not in MEMBERS:
        raise InputError("Task40 exact-pair submission role is unknown")
    return Path(directory) / f"{PAIR_ID}.{role}.submitted.json"


def pair_submission_reservation_path(role: str, *, directory: str | Path = "/tmp") -> Path:
    if role not in MEMBERS:
        raise InputError("Task40 exact-pair reservation role is unknown")
    return Path(directory) / f"{PAIR_ID}.{role}.reserved.json"


class PairRuntimeLocks:
    """Held canonical/shared-pair locks plus an exclusive one-role lock."""

    def __init__(self, streams: list, role: str):
        self._streams = streams
        self.role = role

    def close(self) -> None:
        streams, self._streams = self._streams, []
        for stream in reversed(streams):
            try:
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            finally:
                stream.close()


@contextmanager
def acquire_pair_runtime_locks(
    *,
    role: str,
    canonical_lock_path: str | Path,
    directory: str | Path = "/tmp",
):
    """Join the exact pair with shared host locks and a unique role lock.

    Legacy/non-pair launches continue to take the canonical lock exclusively.
    Both reviewed pair members take it shared, allowing only those two members
    to overlap. A persistent, exclusive role lock rejects a duplicate member.
    """
    if role not in MEMBERS:
        raise InputError("Task40 exact-pair runtime role is unknown")
    canonical_path = Path(canonical_lock_path)
    if canonical_path.resolve() != CANONICAL_HEAVY_LOCK_PATH.resolve():
        raise InputError("Task40 exact-pair runtime uses a noncanonical heavy lock")
    if not canonical_path.is_file():
        raise InputError("Task40 exact-pair requires the pre-existing canonical heavy lock")
    paths_and_modes = (
        (canonical_path, "r", fcntl.LOCK_SH),
        (PAIR_LOCK_PATH, "a", fcntl.LOCK_SH),
        (pair_member_runtime_lock_path(role, directory=directory), "a", fcntl.LOCK_EX),
    )
    streams = []
    lock_set = None
    try:
        for path, mode, operation in paths_and_modes:
            stream = path.open(mode)
            try:
                fcntl.flock(stream.fileno(), operation | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                stream.close()
                raise InputError(
                    "Task40 exact-pair canonical, membership, or role lock is already held"
                ) from exc
            streams.append(stream)
        lock_set = PairRuntimeLocks(streams, role)
        yield lock_set
    finally:
        if lock_set is not None:
            lock_set.close()
        else:
            for stream in reversed(streams):
                try:
                    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
                finally:
                    stream.close()


def reserve_pair_submission_once(
    *,
    role: str,
    profile_identity: str,
    run_id: str,
    package_sha256: str,
    sidecar_sha256: str,
    service_unit: str,
    directory: str | Path = "/tmp",
) -> Path:
    """Consume the exact role before invoking systemd-run; never retry a crash."""
    expected_role = role_for_identity(profile_identity, run_id)
    if role != expected_role:
        raise InputError("Task40 exact-pair reservation role/profile/run mismatch")
    for label, value in (("package", package_sha256), ("sidecar", sidecar_sha256)):
        if not _SHA256.fullmatch(str(value or "")):
            raise InputError(f"Task40 exact-pair {label} SHA256 is invalid")
    if not isinstance(service_unit, str) or not service_unit.endswith(".service"):
        raise InputError("Task40 exact-pair reservation service unit is invalid")
    path = pair_submission_reservation_path(role, directory=directory)
    payload = {
        "schema": "task40.exact_parallel_pair_submission_reservation.v1",
        "pair_id": PAIR_ID,
        "role": role,
        "profile_identity": profile_identity,
        "run_id": run_id,
        "package_sha256": package_sha256,
        "sidecar_sha256": sidecar_sha256,
        "service_unit": service_unit,
    }
    raw = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise InputError("Task40 exact-pair member submission was already reserved") from exc
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_parent_directory(path)
    return path


@contextmanager
def acquire_pair_submission_handshake(
    *,
    role: str,
    profile_identity: str,
    run_id: str,
    scope_path: str | Path,
    scope_sha256: str,
    canonical_lock_path: str | Path,
    directory: str | Path = "/tmp",
    handshake_path: str | Path | None = None,
):
    """Serialize pair fresh/submission handshakes; never serialize FE runtime."""
    expected_role = role_for_identity(profile_identity, run_id)
    if role != expected_role:
        raise InputError("Task40 exact-pair submission role/profile/run identity mismatch")
    scope = load_pair_scope(scope_path=scope_path, expected_sha256=scope_sha256)
    if scope.get("canonical_host_lock", {}).get("path") != str(Path(canonical_lock_path).resolve()):
        raise InputError("Task40 exact-pair submission uses a different canonical heavy lock")
    if (
        pair_submission_receipt_path(role, directory=directory).exists()
        or pair_submission_reservation_path(role, directory=directory).exists()
    ):
        raise InputError("Task40 exact-pair member has already consumed its one-shot submission")
    role_lock_probe = pair_member_runtime_lock_path(role, directory=directory).open("a")
    try:
        try:
            fcntl.flock(role_lock_probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise InputError("Task40 exact-pair member role is already active") from exc
        fcntl.flock(role_lock_probe.fileno(), fcntl.LOCK_UN)
    finally:
        role_lock_probe.close()
    # Register each opened descriptor immediately.  Closing an fd releases its
    # flock even when a later acquisition fails, so every earlier lock is
    # reliably relinquished in reverse order.
    with ExitStack() as stack:
        handshake = stack.enter_context(
            Path(handshake_path or PAIR_HANDSHAKE_PATH).open("a")
        )
        try:
            fcntl.flock(handshake.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise InputError(
                "Task40 exact-pair fresh/submission handshake is already held"
            ) from exc
        canonical_path = Path(canonical_lock_path)
        if not canonical_path.is_file():
            raise InputError("Task40 exact-pair submission requires the canonical heavy lock")
        bridge = stack.enter_context(canonical_path.open("r"))
        try:
            fcntl.flock(bridge.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise InputError("canonical heavy lock is held by a non-pair native run") from exc
        membership = stack.enter_context(PAIR_LOCK_PATH.open("a"))
        try:
            fcntl.flock(membership.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise InputError("Task40 exact-pair membership lock is held") from exc
        yield {"handshake": handshake, "canonical_bridge": bridge, "membership": membership}


def record_pair_submission_once(
    *,
    role: str,
    profile_identity: str,
    run_id: str,
    package_sha256: str,
    sidecar_sha256: str,
    service_unit: str,
    submission_receipt: dict,
    directory: str | Path = "/tmp",
) -> Path:
    """Persist a one-shot submission receipt; an existing role is never reused."""
    expected_role = role_for_identity(profile_identity, run_id)
    if role != expected_role:
        raise InputError("Task40 exact-pair submission role/profile/run identity mismatch")
    for label, value in (("package", package_sha256), ("sidecar", sidecar_sha256)):
        if not _SHA256.fullmatch(str(value or "")):
            raise InputError(f"Task40 exact-pair {label} SHA256 is invalid")
    if not isinstance(service_unit, str) or not service_unit.endswith(".service"):
        raise InputError("Task40 exact-pair submission service unit is invalid")
    invocation = submission_receipt.get("invocation_id") if isinstance(submission_receipt, dict) else None
    if (
        not isinstance(submission_receipt, dict)
        or submission_receipt.get("submitted") is not True
        or submission_receipt.get("systemd_run_returncode") != 0
        or not _INVOCATION_ID.fullmatch(str(invocation or ""))
        or type(submission_receipt.get("main_pid")) is not int
        or submission_receipt["main_pid"] <= 1
    ):
        raise InputError("Task40 exact-pair one-shot receipt requires a successful exact systemd submission")
    reservation, _ = _read_json(
        pair_submission_reservation_path(role, directory=directory),
        "submission reservation",
    )
    expected_reservation = {
        "schema": "task40.exact_parallel_pair_submission_reservation.v1",
        "pair_id": PAIR_ID,
        "role": role,
        "profile_identity": profile_identity,
        "run_id": run_id,
        "package_sha256": package_sha256,
        "sidecar_sha256": sidecar_sha256,
        "service_unit": service_unit,
    }
    if reservation != expected_reservation:
        raise InputError("Task40 exact-pair submission does not match its one-shot reservation")
    path = pair_submission_receipt_path(role, directory=directory)
    payload = {
        "schema": "task40.exact_parallel_pair_submission.v1",
        "pair_id": PAIR_ID,
        "role": role,
        "profile_identity": profile_identity,
        "run_id": run_id,
        "package_sha256": package_sha256,
        "sidecar_sha256": sidecar_sha256,
        "service_unit": service_unit,
        "submission": submission_receipt,
    }
    raw = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise InputError("Task40 exact-pair member submission was already consumed") from exc
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_parent_directory(path)
    return path


def publish_live_binding_once(
    *, role: str, binding: dict, directory: str | Path = "/tmp"
) -> Path:
    """Publish the first exact live binding for a pair role without replacement."""
    if role not in MEMBERS:
        raise InputError("Task40 exact-pair live-binding role is unknown")
    member = binding.get("member", {})
    if (
        binding.get("schema") != LIVE_BINDING_SCHEMA
        or binding.get("pair_id") != PAIR_ID
        or binding.get("status") != "active"
        or member.get("role") != role
        or member.get("profile_identity") != MEMBERS[role]["profile_identity"]
        or member.get("run_id") != MEMBERS[role]["run_id"]
    ):
        raise InputError("Task40 exact-pair live binding differs from its one-shot role")
    path = pair_member_registry_path(role, directory=directory)
    raw = (json.dumps(binding, sort_keys=True, indent=2) + "\n").encode()
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise InputError("Task40 exact-pair live binding already exists; refusing overwrite") from exc
    with os.fdopen(fd, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    _fsync_parent_directory(path)
    return path


def _read_json_file_digest(path: Path, expected_sha: str, label: str) -> dict:
    record, raw = _read_json(path, label)
    if _sha256_bytes(raw) != expected_sha:
        raise InputError(f"Task40 exact-pair {label} SHA256 mismatch")
    return record


def validate_live_binding_payload(
    binding: dict,
    scope: dict,
    *,
    expected_profile: str,
    expected_run_id: str,
    forbidden_service_unit: str | None = None,
) -> dict:
    """Validate fields and static identities before touching the live host."""
    role = role_for_identity(expected_profile, expected_run_id)
    expected = MEMBERS[role]
    member = binding.get("member", {})
    if (
        binding.get("schema") != LIVE_BINDING_SCHEMA
        or binding.get("pair_id") != PAIR_ID
        or binding.get("status") != "active"
        or member.get("role") != role
        or member.get("profile_identity") != expected_profile
        or member.get("run_id") != expected_run_id
        or member.get("mode_count") != expected["mode_count"]
        or member.get("mode_sha256") != expected["mode_sha256"]
    ):
        raise InputError("Task40 exact-pair live binding has an unknown/stale member identity")

    review = binding.get("package_review", {})
    reviewed_source_sha = review.get("reviewed_source_sha")
    if (
        review.get("status") != "PASS"
        or not isinstance(review.get("record_path"), str)
        or not _SHA256.fullmatch(str(review.get("record_sha256", "")))
        or not _SOURCE_SHA.fullmatch(str(reviewed_source_sha or ""))
    ):
        raise InputError("Task40 exact-pair peer lacks a source-bound technical PASS record")
    review_record = _read_json_file_digest(
        Path(review["record_path"]), review["record_sha256"], "peer package review"
    )
    if (
        review_record.get("status") != "PASS"
        or review_record.get("profile_identity") != expected_profile
        or review_record.get("run_id") != expected_run_id
        or review_record.get("source_sha") != reviewed_source_sha
        or review_record.get("mode_count") != expected["mode_count"]
        or review_record.get("mode_sha256") != expected["mode_sha256"]
    ):
        raise InputError("Task40 exact-pair peer review record does not release this exact source")

    service = binding.get("service", {})
    unit = service.get("unit")
    invocation_id = service.get("invocation_id")
    cgroup = service.get("cgroup_path")
    if (
        not isinstance(unit, str) or not unit.endswith(".service")
        or unit == forbidden_service_unit
        or not _INVOCATION_ID.fullmatch(str(invocation_id or ""))
        or type(service.get("main_pid")) is not int or service["main_pid"] <= 1
        or type(service.get("main_start_ticks")) is not int or service["main_start_ticks"] <= 0
        or not isinstance(cgroup, str) or not cgroup.startswith("/")
        or cgroup in ("/", "/init.scope", "/system.slice")
    ):
        raise InputError("Task40 exact-pair peer service binding is incomplete or reused")

    run = binding.get("run", {})
    for key in ("input_sha256", "resolved_config_sha256", "run_manifest_sha256"):
        if not _SHA256.fullmatch(str(run.get(key, ""))):
            raise InputError(f"Task40 exact-pair peer run binding lacks valid {key}")
    if not _SHA256.fullmatch(str(run.get("physical_model_sha256", ""))):
        raise InputError("Task40 exact-pair peer run binding lacks valid physical_model_sha256")
    source_sha = run.get("source_sha")
    if source_sha != reviewed_source_sha or not _SOURCE_SHA.fullmatch(str(source_sha or "")):
        raise InputError("Task40 exact-pair peer source SHA differs from its technical PASS")
    for field in (
        "package_sha256", "sidecar_sha256", "input_sha256",
        "physical_model_sha256", "resolved_config_sha256",
    ):
        if not _SHA256.fullmatch(str(review_record.get(field, ""))):
            raise InputError(f"Task40 exact-pair peer review record lacks {field}")
    for field in ("input_sha256", "physical_model_sha256", "resolved_config_sha256"):
        if run.get(field) != review_record[field]:
            raise InputError(f"Task40 exact-pair peer {field} differs from its package review")
    run_directory = Path(str(run.get("run_directory", ""))).resolve()
    manifest_path = Path(str(run.get("run_manifest_path", ""))).resolve()
    input_path = Path(str(run.get("input_path", ""))).resolve()
    resolved_path = Path(str(run.get("resolved_config_path", ""))).resolve()
    if (
        manifest_path.parent != run_directory
        or resolved_path.parent != run_directory
        or not run.get("run_directory")
        or not run.get("input_path")
    ):
        raise InputError("Task40 exact-pair peer run files are outside their bound run directory")
    manifest, manifest_raw = _read_json(manifest_path, "peer run manifest")
    if _sha256_bytes(manifest_raw) != run["run_manifest_sha256"]:
        raise InputError("Task40 exact-pair peer run manifest changed after binding")
    try:
        input_sha = _sha256_bytes(input_path.read_bytes())
        resolved_sha = _sha256_bytes(resolved_path.read_bytes())
        source_file_sha = (run_directory / "source_sha.txt").read_text().strip()
    except OSError as exc:
        raise InputError(f"Task40 exact-pair peer provenance file is unreadable: {exc}") from exc
    if input_sha != run["input_sha256"] or resolved_sha != run["resolved_config_sha256"]:
        raise InputError("Task40 exact-pair peer input/resolved config changed after binding")
    if source_file_sha != source_sha:
        raise InputError("Task40 exact-pair peer source_sha.txt differs from its binding")
    if (
        manifest.get("run_id") != expected_run_id
        or manifest.get("native_capacity_profile_identity") != expected_profile
        or manifest.get("input_sha256") != input_sha
        or manifest.get("physical_model_sha256") != run["physical_model_sha256"]
        or manifest.get("resolved_config_sha256") != resolved_sha
        or manifest.get("source_sha") != source_sha
        or manifest.get("output_directory") != str(run_directory)
    ):
        raise InputError("Task40 exact-pair peer manifest differs from its exact member binding")

    process_rows = binding.get("processes", {})
    if set(process_rows) != {"root", "mpi", "worker"}:
        raise InputError("Task40 exact-pair peer must bind root, MPI, and worker processes")
    pids = []
    for role_name, row in process_rows.items():
        if (
            type(row.get("pid")) is not int or row["pid"] <= 1
            or type(row.get("start_ticks")) is not int or row["start_ticks"] <= 0
            or type(row.get("ppid")) is not int or row["ppid"] <= 0
            or not isinstance(row.get("cwd"), str)
            or not isinstance(row.get("argv"), list) or not row["argv"]
            or not isinstance(row.get("cgroup_path"), str)
            or not isinstance(row.get("affinity"), list) or not row["affinity"]
        ):
            raise InputError(f"Task40 exact-pair peer {role_name} process binding is incomplete")
        if row["cgroup_path"] != cgroup and not row["cgroup_path"].startswith(cgroup.rstrip("/") + "/"):
            raise InputError(f"Task40 exact-pair peer {role_name} is outside its service cgroup")
        pids.append(row["pid"])
    main_rows = [row for row in process_rows.values() if row["pid"] == service["main_pid"]]
    if main_rows:
        if main_rows[0]["start_ticks"] != service["main_start_ticks"]:
            raise InputError("Task40 exact-pair service MainPID ticks differ from its process binding")
    else:
        main_process = service.get("main_process")
        if not isinstance(main_process, dict):
            raise InputError("Task40 exact-pair peer lacks a bound systemd MainPID identity")
        required_main = {
            "pid", "start_ticks", "ppid", "cwd", "argv", "cgroup_path", "affinity"
        }
        if not required_main.issubset(main_process):
            raise InputError("Task40 exact-pair service wrapper identity is incomplete")
        if (
            main_process["pid"] != service["main_pid"]
            or main_process["start_ticks"] != service["main_start_ticks"]
            or main_process["cgroup_path"] != cgroup
            or not isinstance(main_process["argv"], list)
            or not main_process["argv"]
            or not isinstance(main_process["cwd"], str)
            or not isinstance(main_process["affinity"], list)
            or not main_process["affinity"]
        ):
            raise InputError("Task40 exact-pair service wrapper identity differs from its unit")
    if len(set(pids)) != 3:
        raise InputError("Task40 exact-pair peer repeats a root/MPI/worker PID")
    root_argv = process_rows["root"].get("argv", [])
    worker_argv = process_rows["worker"].get("argv", [])
    if str(input_path) not in root_argv:
        raise InputError("Task40 exact-pair peer root argv does not bind its exact input")
    for required in (str(resolved_path), str(manifest_path), str(run_directory)):
        if required not in worker_argv:
            raise InputError("Task40 exact-pair peer worker argv does not bind its run files")
    mpi_argv = process_rows["mpi"].get("argv", [])
    if any("src.runners.task038_input_worker" in item for item in mpi_argv):
        for required in (str(resolved_path), str(manifest_path), str(run_directory)):
            if required not in mpi_argv:
                raise InputError("Task40 exact-pair MPI argv does not bind its worker run files")

    cpu = binding.get("cpu", {})
    reservation = scope.get("cpu_reservation", {}).get(
        "g3_m8_n64" if role.startswith("0p7") else "ten_layer_m7_n9", {}
    )
    if (
        cpu.get("supervisor_cpu") != expected["supervisor_cpu"]
        or cpu.get("worker_cpu") != expected["worker_cpu"]
        or reservation.get("supervisor_and_mpi_cpu") != expected["supervisor_cpu"]
        or reservation.get("worker_cpu") != expected["worker_cpu"]
    ):
        raise InputError("Task40 exact-pair peer affinity differs from reviewed pair CPU reservation")
    if (
        expected["supervisor_cpu"] not in process_rows["root"]["affinity"]
        or expected["supervisor_cpu"] not in process_rows["mpi"]["affinity"]
        or process_rows["worker"]["affinity"] != [expected["worker_cpu"]]
    ):
        raise InputError("Task40 exact-pair process affinity does not match its pair-local CPU plan")
    activity = cpu.get("activity_sample", {})
    if (
        float(activity.get("sample_seconds", 0)) < 1.0
        or activity.get("exclusive_cpu_claim") is not False
    ):
        raise InputError("Task40 exact-pair peer lacks the bounded nonexclusive CPU activity receipt")
    thread_samples = activity.get("thread_samples")
    if not isinstance(thread_samples, list):
        raise InputError("Task40 exact-pair CPU sample lacks per-thread readback")
    by_leader = {
        (int(row.get("pid", -1)), int(row.get("tid", -1))): row
        for row in thread_samples
        if isinstance(row, dict) and row.get("status") == "sampled"
    }
    for process_role in ("root", "worker"):
        process = process_rows[process_role]
        sample = by_leader.get((process["pid"], process["pid"]))
        if (
            sample is None
            or sample.get("start_ticks") != process["start_ticks"]
            or sample.get("affinity") != process["affinity"]
            or type(sample.get("delta_cpu_ticks")) is not int
            or sample["delta_cpu_ticks"] < 0
            or type(sample.get("last_cpu_after")) is not int
        ):
            raise InputError(
                f"Task40 exact-pair CPU sample does not bind the live {process_role} leader"
            )
    return binding


def _proc_cgroup(proc_root: Path, pid: int) -> str:
    lines = (proc_root / str(pid) / "cgroup").read_text().splitlines()
    for line in lines:
        hierarchy, controllers, path = line.split(":", 2)
        if hierarchy == "0" and controllers == "":
            return path
    raise InputError(f"Task40 exact-pair PID {pid} has no unified cgroup path")


def _read_live_proc(proc_root: Path, pid: int) -> dict:
    proc = proc_root / str(int(pid))
    fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
    status = dict(
        line.split(":", 1) for line in (proc / "status").read_text().splitlines() if ":" in line
    )
    argv = [part.decode("utf-8", "replace") for part in (proc / "cmdline").read_bytes().split(b"\0") if part]
    return {
        "pid": int(pid), "state": fields[0], "ppid": int(fields[1]),
        "start_ticks": int(fields[19]), "cwd": str((proc / "cwd").resolve()),
        "argv": argv, "cgroup_path": _proc_cgroup(proc_root, int(pid)),
        "affinity": sorted(_parse_cpu_list(status.get("Cpus_allowed_list", ""))),
    }


def _parse_cpu_list(value: str) -> set[int]:
    result: set[int] = set()
    if not value:
        return result
    for part in value.strip().split(","):
        bounds = part.split("-", 1)
        start, end = int(bounds[0]), int(bounds[-1])
        result.update(range(start, end + 1))
    return result


def _is_descendant(proc_root: Path, pid: int, ancestor_pid: int) -> bool:
    current = int(pid)
    seen = set()
    while current > 1 and current not in seen:
        if current == int(ancestor_pid):
            return True
        seen.add(current)
        try:
            fields = (proc_root / str(current) / "stat").read_text().rsplit(")", 1)[1].split()
            current = int(fields[1])
        except (OSError, ValueError, IndexError):
            return False
    return False


def verify_live_binding(
    path: str | Path,
    scope: dict,
    *,
    expected_profile: str,
    expected_run_id: str,
    forbidden_service_unit: str | None = None,
    proc_root: str | Path = "/proc",
    sys_root: str | Path = "/sys",
    systemd_reader=None,
) -> dict:
    """Check peer provenance, systemd invocation, PID start times, affinity and topology."""
    binding, _ = _read_json(Path(path), "peer live binding")
    validate_live_binding_payload(
        binding, scope, expected_profile=expected_profile,
        expected_run_id=expected_run_id,
        forbidden_service_unit=forbidden_service_unit,
    )
    proc_root = Path(proc_root)
    sys_root = Path(sys_root)
    service = binding["service"]
    if systemd_reader is None:
        def systemd_reader(unit):
            completed = subprocess.run(
                ["systemctl", "--user", "show", unit,
                 "--property=InvocationID", "--property=MainPID",
                 "--property=ControlGroup", "--property=ActiveState",
                 "--property=SubState", "--no-pager"],
                capture_output=True, text=True, check=True,
            )
            return dict(line.split("=", 1) for line in completed.stdout.splitlines() if "=" in line)

    try:
        unit_state = systemd_reader(service["unit"])
    except (OSError, subprocess.CalledProcessError) as exc:
        raise InputError(f"Task40 exact-pair peer systemd unit is unreadable: {exc}") from exc
    if (
        unit_state.get("InvocationID") != service["invocation_id"]
        or int(unit_state.get("MainPID", "-1")) != service["main_pid"]
        or unit_state.get("ControlGroup") != service["cgroup_path"]
        or unit_state.get("ActiveState") != "active"
        or unit_state.get("SubState") not in ("running", "start")
    ):
        raise InputError("Task40 exact-pair peer systemd unit invocation/MainPID/cgroup changed")
    main = _read_live_proc(proc_root, service["main_pid"])
    if main["start_ticks"] != service["main_start_ticks"]:
        raise InputError("Task40 exact-pair peer systemd MainPID was reused")
    if main["cgroup_path"] != service["cgroup_path"] and not main["cgroup_path"].startswith(service["cgroup_path"].rstrip("/") + "/"):
        raise InputError("Task40 exact-pair peer MainPID left its service cgroup")
    if service["main_pid"] not in {row["pid"] for row in binding["processes"].values()}:
        expected_main = service["main_process"]
        for key in ("ppid", "cwd", "argv", "cgroup_path", "affinity"):
            if main[key] != expected_main[key]:
                raise InputError(f"Task40 exact-pair service wrapper {key} changed")

    expected = MEMBERS[role_for_identity(expected_profile, expected_run_id)]
    process_rows = binding["processes"]
    live = {}
    for role_name, row in process_rows.items():
        observed = _read_live_proc(proc_root, row["pid"])
        if observed["state"] in ("Z", "X"):
            raise InputError(f"Task40 exact-pair peer {role_name} process is no longer active")
        for key in ("start_ticks", "ppid", "cwd", "argv", "cgroup_path", "affinity"):
            if observed[key] != row[key]:
                raise InputError(f"Task40 exact-pair peer {role_name} {key} changed")
        if observed["cgroup_path"] != service["cgroup_path"] and not observed["cgroup_path"].startswith(service["cgroup_path"].rstrip("/") + "/"):
            raise InputError(f"Task40 exact-pair peer {role_name} is outside its unit cgroup")
        live[role_name] = observed
    root_pid = live["root"]["pid"]
    mpi_pid = live["mpi"]["pid"]
    worker_pid = live["worker"]["pid"]
    if not _is_descendant(proc_root, root_pid, service["main_pid"]) and root_pid != service["main_pid"]:
        raise InputError("Task40 exact-pair root is outside its systemd MainPID tree")
    if not _is_descendant(proc_root, mpi_pid, root_pid):
        raise InputError("Task40 exact-pair MPI process is outside its root runner tree")
    if not _is_descendant(proc_root, worker_pid, mpi_pid):
        raise InputError("Task40 exact-pair worker is outside its MPI process tree")
    from src.runners.reviewed_workstation_admission import _classify_task40_solver_argv

    classifications = {
        name: _classify_task40_solver_argv(row["argv"])
        for name, row in live.items()
    }
    mpi_classification = classifications["mpi"]
    if (
        classifications["root"] is None
        or classifications["root"].get("role") != "standard_run_case"
        or classifications["worker"] is None
        or classifications["worker"].get("role") != "task038_input_worker"
        or (
            mpi_classification is not None
            and (
                mpi_classification.get("kind") != "task_solver"
                or mpi_classification.get("role") != "task038_input_worker"
            )
        )
    ):
        raise InputError("Task40 exact-pair root/MPI/worker command identities differ")
    if expected["supervisor_cpu"] not in live["root"]["affinity"]:
        raise InputError("Task40 exact-pair root affinity misses its reviewed supervisor CPU")
    if expected["supervisor_cpu"] not in live["mpi"]["affinity"]:
        raise InputError("Task40 exact-pair MPI affinity misses its reviewed supervisor CPU")
    if live["worker"]["affinity"] != [expected["worker_cpu"]]:
        raise InputError("Task40 exact-pair worker affinity differs from its reviewed CPU")

    role = role_for_identity(expected_profile, expected_run_id)
    cpu_scope = scope["cpu_reservation"][
        "g3_m8_n64" if role.startswith("0p7") else "ten_layer_m7_n9"
    ]
    cpu_ids = [expected["supervisor_cpu"], expected["worker_cpu"]]
    actual_topology = {}
    for cpu_id in cpu_ids:
        topology = sys_root / f"devices/system/cpu/cpu{cpu_id}/topology"
        try:
            values = {
                "package": int((topology / "physical_package_id").read_text()),
                "core": int((topology / "core_id").read_text()),
                "thread_siblings": (topology / "thread_siblings_list").read_text().strip(),
            }
        except (OSError, ValueError) as exc:
            raise InputError(f"Task40 exact-pair CPU{cpu_id} topology is unreadable: {exc}") from exc
        actual_topology[str(cpu_id)] = values
    expected_topology = cpu_scope.get("expected_topology", {})
    if any(actual_topology.get(cpu_id) != expected_values for cpu_id, expected_values in expected_topology.items()):
        raise InputError("Task40 exact-pair CPU topology changed since the reviewed reservation")
    return {
        "binding": binding,
        "live_processes": live,
        "classifications": classifications,
        "cpu_topology_readback": actual_topology,
        "systemd_unit_readback": unit_state,
    }


def discover_peer_binding_path(current_role: str, *, directory: str | Path = "/tmp") -> Path:
    if current_role not in MEMBERS:
        raise InputError("Task40 exact-pair current role is unknown")
    peer_role = next(role for role in MEMBERS if role != current_role)
    return pair_member_registry_path(peer_role, directory=directory)


def load_peer_binding_if_present(
    current_profile: str,
    current_run_id: str,
    scope: dict,
    *,
    current_service_unit: str | None = None,
    directory: str | Path = "/tmp",
    verifier=verify_live_binding,
) -> dict | None:
    current_role = role_for_identity(current_profile, current_run_id)
    path = discover_peer_binding_path(current_role, directory=directory)
    if not path.exists():
        return None
    peer_role = next(role for role in MEMBERS if role != current_role)
    peer = MEMBERS[peer_role]
    return verifier(
        path, scope, expected_profile=peer["profile_identity"],
        expected_run_id=peer["run_id"],
        forbidden_service_unit=current_service_unit,
    )


def peer_authorized_process_nodes(verified_peer: dict | None) -> tuple[dict, dict]:
    """Return candidate and large-process identities justified by one live peer."""
    if verified_peer is None:
        return {}, {}
    classifications = verified_peer.get("classifications", {})
    live = verified_peer.get("live_processes", {})
    solver_nodes = {}
    process_nodes = {}
    if set(live) != {"root", "mpi", "worker"}:
        raise InputError("Task40 exact-pair live peer lacks root/MPI/worker identities")
    for name, row in live.items():
        pid = int(row["pid"])
        process_nodes[pid] = row
        classification = classifications.get(name)
        if classification is None:
            if name == "root" or name == "worker":
                raise InputError(f"Task40 exact-pair peer {name} is not a recognized solver role")
            continue
        if classification.get("kind") != "task_solver":
            raise InputError(f"Task40 exact-pair peer {name} has an unknown solver role")
        if name == "root" and classification.get("role") != "standard_run_case":
            raise InputError("Task40 exact-pair peer root is not the standard run_case entrypoint")
        if name in {"mpi", "worker"} and classification.get("role") != "task038_input_worker":
            raise InputError(f"Task40 exact-pair peer {name} is not the bound worker command")
        solver_nodes[pid] = {"node": row, "classification": classification}
    if not {int(live["root"]["pid"]), int(live["worker"]["pid"])}.issubset(solver_nodes):
        raise InputError("Task40 exact-pair peer does not expose both root and worker solver identities")
    return solver_nodes, process_nodes
