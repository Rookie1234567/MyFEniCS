"""Exact D07C memory-floor admission for reviewed observational execution.

This module deliberately does not acquire or inspect the canonical heavy lock.
It is reachable only for the exact G5 or G6 profile/run and a hash-bound
attempt scope. Other Task40 profiles retain their existing exclusive/admission
paths. The G5 and G6 scopes, locks, caches, and one-shot markers are distinct.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import time
from contextlib import contextmanager
from pathlib import Path

from src.io.input_loader import InputError

G5_PROFILE = "task40para_phi90_0p7_D07C_G5_M8_N64_p6_direct_v1"
G5_RUN_ID = G5_PROFILE
G5_SCOPE_SCHEMA = "task40.d07c_g5_memory_floor_observational_neighbors.v1"
G5_SCOPE_PATH_ENV = "TASK40_D07C_G5_SCOPE_PATH"
G5_SCOPE_SHA_ENV = "TASK40_D07C_G5_SCOPE_SHA256"
G5_SUBMISSION_MODE_ENV = "TASK40_D07C_G5_SUBMISSION_MODE"
G6_PROFILE = "task40para_phi90_0p7_D07C_G6_M8_N64_p6_direct_v1"
G6_RUN_ID = G6_PROFILE
G6_SCOPE_SCHEMA = "task40.d07c_g6_memory_floor_observational_neighbors.v1"
G6_SCOPE_PATH_ENV = "TASK40_D07C_G6_SCOPE_PATH"
G6_SCOPE_SHA_ENV = "TASK40_D07C_G6_SCOPE_SHA256"
G6_SUBMISSION_MODE_ENV = "TASK40_D07C_G6_SUBMISSION_MODE"
G6_N32_PROFILE = "task40para_phi90_0p7_D07C_G6_M8_N32_p6_direct_v1"
G6_N14_PROFILE = "task40para_phi90_0p7_D07C_G6_M8_N14_p6_direct_v1"
G6_MODAL_TRUNCATION_PROFILES = frozenset({G6_N32_PROFILE, G6_N14_PROFILE})
G6_SCOPED_PROFILES = frozenset({G6_PROFILE, *G6_MODAL_TRUNCATION_PROFILES})
_ATTEMPT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{5,63}$")
_LIVE_STATES = {"R", "S", "D", "T", "t", "K", "W", "P"}

_CASE_SPECS = {
    G5_PROFILE: {
        "case": "G5", "run_id": G5_RUN_ID, "schema": G5_SCOPE_SCHEMA,
        "policy": "g5_scoped_observational_neighbors_v1",
    },
    G6_PROFILE: {
        "case": "G6", "run_id": G6_RUN_ID, "schema": G6_SCOPE_SCHEMA,
        "policy": "g6_scoped_observational_neighbors_v1",
    },
    G6_N32_PROFILE: {
        "case": "G6_M8_N32", "run_id": G6_N32_PROFILE,
        "schema": "task40.d07c_g6_n32_memory_floor_observational_neighbors.v1",
        "policy": "g6_scoped_observational_neighbors_v1",
    },
    G6_N14_PROFILE: {
        "case": "G6_M8_N14", "run_id": G6_N14_PROFILE,
        "schema": "task40.d07c_g6_n14_memory_floor_observational_neighbors.v1",
        "policy": "g6_scoped_observational_neighbors_v1",
    },
}


def g6_case_for_profile(profile: str) -> str:
    if str(profile) not in G6_SCOPED_PROFILES:
        raise InputError("G6 observational admission requires an exact G6 profile")
    return _CASE_SPECS[str(profile)]["case"]


def _case_spec(profile: str, run_id: str) -> dict:
    spec = _CASE_SPECS.get(str(profile))
    if spec is None or (str(profile), str(run_id)) != (str(profile), spec["run_id"]):
        raise InputError("D07C observational admission requires an exact profile/run")
    return spec


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _case_lock_paths(profile: str, run_id: str, directory: Path) -> tuple[Path, Path]:
    spec = _case_spec(profile, run_id)
    identity = hashlib.sha256(f"{profile}\0{run_id}".encode()).hexdigest()[:20]
    prefix = f"task40_d07c_{spec['case'].lower()}_{identity}"
    return directory / f"{prefix}.member.lock", directory / f"{prefix}.submitted.json"


def _attempt_cache_root(attempt_id: str, profile: str = G5_PROFILE) -> Path:
    if not _ATTEMPT_RE.fullmatch(attempt_id):
        raise InputError("D07C authorization has an invalid attempt id")
    spec = _CASE_SPECS.get(str(profile))
    if spec is None:
        raise InputError("D07C attempt cache requires the exact G5 or G6 profile")
    return Path("/tmp") / f"task40_d07c_{spec['case'].lower()}_attempt_{attempt_id}"


def load_observational_scope(
    scope_path: str | Path,
    expected_sha256: str,
    *,
    profile: str,
    run_id: str,
    expected_identity: dict | None = None,
    lock_directory: str | Path = "/tmp",
) -> dict:
    """Read one exact D07C case scope and compare supplied identity fields."""
    spec = _case_spec(profile, run_id)
    case = spec["case"]
    path = Path(scope_path).resolve()
    try:
        raw = path.read_bytes()
        scope = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f"{case} scope is unreadable: {exc}") from exc
    digest = hashlib.sha256(raw).hexdigest()
    if digest != str(expected_sha256).lower():
        raise InputError(f"{case} scope SHA256 mismatch")
    if scope.get("schema") != spec["schema"]:
        raise InputError(f"{case} scope schema is unsupported")
    identity = scope.get("identity", {})
    if identity.get("profile_identity") != profile or identity.get("run_id") != run_id:
        raise InputError(f"{case} scope does not bind the exact profile/run")
    if expected_identity is not None:
        for key, expected in expected_identity.items():
            if identity.get(key) != expected:
                raise InputError(f"{case} scope identity differs at {key}")
    resources = scope.get("resource_contract", {})
    if (
        resources.get("mode") != "host_available_floor_v1"
        or resources.get("minimum_available_bytes") != 64 * 1024**3
        or resources.get("rss_hard_limit_bytes") is not None
        or resources.get("swap_policy") != "observe_only"
        or resources.get("stop_on_global_swap") is not False
        or resources.get("pss_uss_sampling") != "disabled"
    ):
        raise InputError(f"{case} scope changes the reviewed 64 GiB/no-RSS-cap contract")
    parallel = scope.get("neighbor_policy", {})
    if (
        parallel.get("policy") != spec["policy"]
        or parallel.get("neighbors_block_admission") is not False
        or parallel.get("unknown_solver_candidates_block_admission") is not False
        or parallel.get("large_process_candidates_block_admission") is not False
        or parallel.get("neighbors_modified") is not False
    ):
        raise InputError(f"{case} scope lacks the exact observational-neighbor authorization")
    policy = scope.get("cpu_policy", {})
    if (
        policy.get("selection") != "sampled_low_load_distinct_physical_cores_v1"
        or policy.get("sample_seconds") != 1.5
        or policy.get("busy_fallback_allowed") is not True
        or policy.get("exclusive_cpu_ownership") is not False
    ):
        raise InputError(f"{case} scope CPU policy differs from the reviewed dynamic reservation")
    paths = scope.get("runtime_paths", {})
    attempt_id = scope.get("attempt_id")
    if not isinstance(attempt_id, str) or not _ATTEMPT_RE.fullmatch(attempt_id):
        raise InputError(f"{case} authorization has an invalid attempt id")
    member, reservation = _case_lock_paths(profile, run_id, Path(lock_directory))
    cache_root = _attempt_cache_root(attempt_id, profile)
    if paths.get("member_lock") != str(member) or paths.get("one_shot_reservation") != str(reservation):
        raise InputError(f"{case} case-level lock paths differ from its exact profile/run identity")
    if paths.get("attempt_cache_root") != str(cache_root):
        raise InputError(f"{case} scope cache root differs from its exact attempt id")
    return scope


def load_g5_scope(scope_path, expected_sha256, **kwargs) -> dict:
    if str(kwargs.get("profile")) != G5_PROFILE:
        raise InputError("G5 observational admission is restricted to the exact profile/run")
    return load_observational_scope(scope_path, expected_sha256, **kwargs)


def load_g6_scope(scope_path, expected_sha256, **kwargs) -> dict:
    if str(kwargs.get("profile")) not in G6_SCOPED_PROFILES:
        raise InputError("G6 observational admission is restricted to exact G6 profiles/runs")
    return load_observational_scope(scope_path, expected_sha256, **kwargs)


def _core(cpu: int) -> tuple[int, int]:
    topology = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology")
    return (
        int((topology / "physical_package_id").read_text()),
        int((topology / "core_id").read_text()),
    )


def _siblings(cpu: int) -> set[int]:
    raw = Path(f"/sys/devices/system/cpu/cpu{cpu}/topology/thread_siblings_list").read_text()
    result: set[int] = set()
    for item in raw.strip().split(","):
        limits = item.split("-", 1)
        result.update(range(int(limits[0]), int(limits[-1]) + 1))
    return result


def _cpu_ticks(proc_root: str | Path = "/proc") -> dict[int, tuple[int, int]]:
    result = {}
    for line in (Path(proc_root) / "stat").read_text().splitlines():
        fields = line.split()
        if fields and fields[0].startswith("cpu") and fields[0][3:].isdigit():
            values = [int(value) for value in fields[1:]]
            result[int(fields[0][3:])] = (
                sum(values), values[3] + (values[4] if len(values) > 4 else 0)
            )
    return result


def _observe_process_affinities(proc_root: str | Path = "/proc") -> dict:
    root = Path(proc_root)
    ancestors = {os.getpid()}
    parent = os.getpid()
    while parent > 1:
        try:
            fields = (root / str(parent) / "stat").read_text().rsplit(")", 1)[1].split()
            parent = int(fields[1])
        except (OSError, ValueError, IndexError):
            break
        if parent > 1:
            ancestors.add(parent)
    rows = []
    unreadable = 0
    for proc in root.glob("[0-9]*"):
        try:
            pid = int(proc.name)
            if pid in ancestors:
                continue
            stat = (proc / "stat").read_text().rsplit(")", 1)[1].split()
            if stat[0] in {"Z", "X"}:
                continue
            status = dict(line.split(":", 1) for line in (proc / "status").read_text().splitlines())
            rss = int(status.get("VmRSS", "0").split()[0]) * 1024
            argv = [x.decode("utf-8", "replace") for x in
                    (proc / "cmdline").read_bytes().split(b"\0") if x]
            affinity = sorted(os.sched_getaffinity(pid))
            is_solver = any(
                token.endswith("scripts/run_case.py")
                or token == "src.runners.task038_input_worker"
                or token == "src.runners.task038_launcher"
                for token in argv
            )
            if rss >= 1_000_000_000 or is_solver:
                rows.append({
                    "pid": pid,
                    "start_ticks": int(stat[19]),
                    "ppid": int(stat[1]),
                    "rss_bytes": rss,
                    "affinity": affinity,
                    "argv": argv,
                    "solver_role_observation": is_solver,
                })
        except (OSError, ValueError, IndexError, KeyError, ProcessLookupError, PermissionError):
            unreadable += 1
    return {
        "observed_utc_epoch_ns": time.time_ns(),
        "scope": "read_only_cpu_affinity_observation",
        "processes": rows,
        "unreadable_process_count": unreadable,
        "processes_modified": False,
    }


def choose_g5_cpu_reservation(*, sample_seconds: float = 1.5, proc_root: str | Path = "/proc") -> dict:
    """Prefer low-load physical cores, avoid heavy-neighbor cores where practical."""
    allowed = sorted(os.sched_getaffinity(0))
    if len(allowed) < 2:
        raise InputError("G5 dynamic CPU reservation needs two CPUs in the current allowed affinity")
    observation = _observe_process_affinities(proc_root)
    heavy_cores: set[tuple[int, int]] = set()
    for row in observation["processes"]:
        for cpu in row["affinity"]:
            try:
                heavy_cores.add(_core(cpu))
            except (OSError, ValueError):
                continue
    before = _cpu_ticks(proc_root)
    time.sleep(max(0.0, float(sample_seconds)))
    after = _cpu_ticks(proc_root)
    candidates = []
    seen = set()
    for cpu in allowed:
        try:
            core = _core(cpu)
            siblings = sorted(_siblings(cpu))
        except (OSError, ValueError):
            continue
        if core in seen:
            continue
        seen.add(core)
        old, new = before.get(cpu), after.get(cpu)
        delta_total = None if old is None or new is None else new[0] - old[0]
        delta_idle = None if old is None or new is None else new[1] - old[1]
        utilization = (
            1.0 if delta_total is None or delta_total <= 0 or delta_idle is None
            else max(0.0, min(1.0, 1.0 - delta_idle / delta_total))
        )
        candidates.append({
            "cpu": cpu,
            "package": core[0],
            "core": core[1],
            "sampled_utilization": utilization,
            "heavy_neighbor_affinity_overlap": core in heavy_cores,
            "thread_siblings": siblings,
        })
    candidates.sort(key=lambda row: (
        row["heavy_neighbor_affinity_overlap"], row["sampled_utilization"], row["cpu"]
    ))
    if len(candidates) < 2:
        raise InputError("G5 dynamic CPU reservation lacks two distinct physical cores")
    chosen = candidates[:2]
    return {
        "policy": "sampled_low_load_distinct_physical_cores_v1",
        "sample_seconds": float(sample_seconds),
        "supervisor_cpu": chosen[0]["cpu"],
        "worker_cpu": chosen[1]["cpu"],
        "selected_topology": chosen,
        "candidate_topology_and_load": candidates,
        "allowed_affinity_at_selection": allowed,
        "observed_heavy_neighbor_cores": [list(core) for core in sorted(heavy_cores)],
        "heavy_neighbor_affinity_avoidance": "preferred_when_possible_busy_fallback_allowed",
        "exclusive_cpu_ownership": False,
        "neighbor_observation": observation,
    }


def choose_g6_cpu_reservation(*, sample_seconds: float = 1.5, proc_root: str | Path = "/proc") -> dict:
    """Use the same dynamic, non-exclusive two-core sampler for exact G6."""
    return choose_g5_cpu_reservation(sample_seconds=sample_seconds, proc_root=proc_root)


class G5RuntimeLease:
    def __init__(self, scope: dict, scope_path: Path, scope_sha256: str,
                 member_stream, member_path: Path, reservation_path: Path,
                 cpu_reservation: dict, submission_mode: str, *, profile: str = G5_PROFILE):
        self.profile = profile
        self.case = _CASE_SPECS[profile]["case"]
        self.scope = scope
        self.scope_path = scope_path
        self.scope_sha256 = scope_sha256
        self.member_stream = member_stream
        self.member_path = member_path
        self.reservation_path = reservation_path
        self.cpu_reservation = cpu_reservation
        self.submission_mode = submission_mode
        self._committed = False

    def summary(self) -> dict:
        return {
            "policy": f"{self.case.lower()}_memory_floor_with_observational_neighbors",
            "lock_scope": "case_level_profile_run_identity",
            "scope_path": str(self.scope_path),
            "scope_sha256": self.scope_sha256,
            "attempt_id": self.scope["attempt_id"],
            "reservation_scope": "case_level_profile_run_identity",
            "member_lock_path": str(self.member_path),
            "one_shot_reservation_path": str(self.reservation_path),
            "submission_mode": self.submission_mode,
            "cpu_reservation": self.cpu_reservation,
            "canonical_heavy_lock_touched": False,
            "neighbors_modified": False,
        }

    def commit_runtime_submission(self) -> None:
        if self.submission_mode != "runtime":
            return
        if self._committed:
            raise InputError(f"{self.case} runtime reservation was already committed")
        payload = {
            "schema": f"task40.d07c.{self.case.lower()}_one_shot_submission.v1",
            "profile_identity": self.profile,
            "run_id": self.profile,
            "attempt_id": self.scope["attempt_id"],
            "scope_sha256": self.scope_sha256,
            "cpu_reservation": self.cpu_reservation,
            "committed_utc_epoch_ns": time.time_ns(),
            "submission_mode": self.submission_mode,
        }
        raw = (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()
        try:
            fd = os.open(self.reservation_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise InputError(f"{self.case} one-shot reservation already exists; no retry") from exc
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        self._committed = True


@contextmanager
def _runtime_lease(
    *,
    profile: str,
    run_id: str,
    scope_path: str | Path,
    scope_sha256: str,
    expected_identity: dict | None,
    submission_mode: str,
    lock_directory: str | Path,
    proc_root: str | Path,
):
    spec = _case_spec(profile, run_id)
    case = spec["case"]
    if submission_mode not in {"fresh_check", "runtime"}:
        raise InputError(f"{case} submission mode is unsupported")
    lock_dir = Path(lock_directory)
    scope_file = Path(scope_path).resolve()
    scope = load_observational_scope(
        scope_file, scope_sha256, profile=profile, run_id=run_id,
        expected_identity=expected_identity, lock_directory=lock_dir,
    )
    member_path, reservation_path = _case_lock_paths(profile, run_id, lock_dir)
    member = member_path.open("a")
    try:
        try:
            fcntl.flock(member.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise InputError(f"{case} case-level member lock is held; no launch") from exc
        if reservation_path.exists():
            raise InputError(f"{case} one-shot reservation already exists; no retry")
        reservation_factory = (
            choose_g5_cpu_reservation if spec["case"] == "G5"
            else choose_g6_cpu_reservation
        )
        reservation = reservation_factory(proc_root=proc_root)
        lease = G5RuntimeLease(
            scope, scope_file, str(scope_sha256).lower(), member,
            member_path, reservation_path, reservation, submission_mode,
            profile=profile,
        )
        yield lease
    finally:
        try:
            fcntl.flock(member.fileno(), fcntl.LOCK_UN)
        finally:
            member.close()


@contextmanager
def g5_runtime_lease(
    profile: str,
    run_id: str,
    *,
    scope_path: str | Path,
    scope_sha256: str,
    expected_identity: dict | None = None,
    submission_mode: str = "runtime",
    lock_directory: str | Path = "/tmp",
    proc_root: str | Path = "/proc",
):
    if str(profile) != G5_PROFILE:
        raise InputError("G5 runtime lease is restricted to the exact G5 profile")
    with _runtime_lease(
        profile=profile, run_id=run_id, scope_path=scope_path,
        scope_sha256=scope_sha256, expected_identity=expected_identity,
        submission_mode=submission_mode, lock_directory=lock_directory,
        proc_root=proc_root,
    ) as lease:
        yield lease


@contextmanager
def g6_runtime_lease(
    profile: str,
    run_id: str,
    *,
    scope_path: str | Path,
    scope_sha256: str,
    expected_identity: dict | None = None,
    submission_mode: str = "runtime",
    lock_directory: str | Path = "/tmp",
    proc_root: str | Path = "/proc",
):
    if str(profile) not in G6_SCOPED_PROFILES:
        raise InputError("G6 runtime lease is restricted to exact G6 profiles")
    with _runtime_lease(
        profile=profile, run_id=run_id, scope_path=scope_path,
        scope_sha256=scope_sha256, expected_identity=expected_identity,
        submission_mode=submission_mode, lock_directory=lock_directory,
        proc_root=proc_root,
    ) as lease:
        yield lease


__all__ = [
    "G5_PROFILE",
    "G5_RUN_ID",
    "G5_SCOPE_PATH_ENV",
    "G5_SCOPE_SCHEMA",
    "G5_SCOPE_SHA_ENV",
    "G5_SUBMISSION_MODE_ENV",
    "G6_PROFILE",
    "G6_RUN_ID",
    "G6_N32_PROFILE",
    "G6_N14_PROFILE",
    "G6_MODAL_TRUNCATION_PROFILES",
    "G6_SCOPED_PROFILES",
    "G6_SCOPE_PATH_ENV",
    "G6_SCOPE_SCHEMA",
    "G6_SCOPE_SHA_ENV",
    "G6_SUBMISSION_MODE_ENV",
    "G5RuntimeLease",
    "choose_g5_cpu_reservation",
    "choose_g6_cpu_reservation",
    "g5_runtime_lease",
    "g6_runtime_lease",
    "g6_case_for_profile",
    "load_g5_scope",
    "load_g6_scope",
    "load_observational_scope",
]
