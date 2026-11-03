"""Exact one-shot Gate-CD execution lease and host-scope identity checks.

Host memory-floor and observational-neighbor admission is delegated to the
already-reviewed Task40 production guard. Gate-CD only adds an exact profile /
run scope, per-attempt lease/cache, and sampled dynamic CPU reservation; it does
not acquire the legacy canonical exclusive heavy lock.
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

GATE_CD_FORMAL_PROFILE = "task40_gate_cd_0p7_mapped_m8n64_p6_direct_v1"
GATE_CD_PARALLEL32_PROFILE = (
    "task40_gate_cd_0p7_mapped_m8n14_p6_direct_parallel32_v1"
)
GATE_CD_M8N6_PROFILE = "task40_gate_cd_0p7_mapped_m8n6_p6_direct_v1"
GATE_CD_M8N2_PROFILE = "task40_gate_cd_0p7_mapped_m8n2_p6_direct_v1"
GATE_CD_FIN0_STI_Z10_M8N2_PROFILE = (
    "task40_gate_cd_fin0_sti_z10_m8n2_p6_direct_v1"
)
GATE_CD_PARALLEL32_PROFILES = frozenset(
    {
        GATE_CD_PARALLEL32_PROFILE,
        GATE_CD_M8N6_PROFILE,
        GATE_CD_M8N2_PROFILE,
        GATE_CD_FIN0_STI_Z10_M8N2_PROFILE,
    }
)
GATE_CD_EXECUTION_PROFILES = frozenset(
    {
        GATE_CD_FORMAL_PROFILE,
        GATE_CD_PARALLEL32_PROFILE,
        GATE_CD_M8N6_PROFILE,
        GATE_CD_M8N2_PROFILE,
        GATE_CD_FIN0_STI_Z10_M8N2_PROFILE,
    }
)
GATE_CD_PARALLEL32_WORKERS = 32
GATE_CD_SCOPE_SCHEMA = "task40.gate_cd_formal_exact_execution_scope.v2"
GATE_CD_RAW_POOL_SCHEDULER_POLICY = "task40_shared_parallel32_raw_tensor_pool_v1"
GATE_CD_RAW_POOL_LOCK_PATH = "/tmp/task40_gate_cd_parallel32_raw_tensor_pool.lock"
GATE_CD_SCOPE_PATH_ENV = "TASK40_GATE_CD_SCOPE_PATH"
GATE_CD_SCOPE_SHA_ENV = "TASK40_GATE_CD_SCOPE_SHA256"
GATE_CD_SUBMISSION_MODE_ENV = "TASK40_GATE_CD_SUBMISSION_MODE"
GATE_CD_LOCK_DIRECTORY_ENV = "TASK40_GATE_CD_LOCK_DIRECTORY"
GATE_CD_ATTEMPT_CACHE_ENV = "TASK40_GATE_CD_ATTEMPT_CACHE_ROOT"
_ATTEMPT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{5,63}$")
_REQUIRED_IDENTITY_KEYS = {
    "profile_identity", "run_id", "input_path", "input_sha256",
    "physical_model_sha256", "resolved_config_sha256",
    "resolved_output_parent_absolute", "source_commit", "direct_route_contract",
}


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       allow_nan=False) + "\n").encode()


def _case_key(profile: str, run_id: str) -> str:
    return hashlib.sha256(f"{profile}\0{run_id}".encode()).hexdigest()[:24]


def _runtime_paths(profile: str, run_id: str, attempt_id: str,
                   lock_directory: str | Path) -> dict[str, str]:
    root = Path(lock_directory).resolve()
    key = _case_key(profile, run_id)
    cache = root / f"task40_gate_cd_formal_attempt_{attempt_id}"
    return {
        "lock_directory": str(root),
        "member_lock": str(root / f"task40_gate_cd_{key}.member.lock"),
        "one_shot_reservation": str(root / f"task40_gate_cd_{key}_{attempt_id}.submitted.json"),
        "attempt_cache_root": str(cache),
    }


def _validate_exact_identity(actual: object, expected: dict | None,
                             profile: str, run_id: str) -> dict:
    if not isinstance(actual, dict) or not isinstance(expected, dict):
        raise InputError("Gate-CD exact scope requires the resolved standard-launch identity")
    if set(expected) != _REQUIRED_IDENTITY_KEYS:
        raise InputError("Gate-CD expected identity fields differ from the reviewed schema")
    if actual != expected:
        differing = sorted(key for key in set(actual) | set(expected)
                           if actual.get(key) != expected.get(key))
        raise InputError(f"Gate-CD execution scope identity mismatch at {differing}")
    if actual.get("profile_identity") != profile or actual.get("run_id") != run_id:
        raise InputError("Gate-CD exact scope does not bind this profile/run")
    for key in ("input_sha256", "physical_model_sha256", "resolved_config_sha256"):
        value = actual.get(key)
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value):
            raise InputError(f"Gate-CD exact identity has an invalid {key}")
    source_commit = actual.get("source_commit")
    if not isinstance(source_commit, str) or not re.fullmatch(r"[0-9a-f]{40}(?:[0-9a-f]{24})?", source_commit):
        raise InputError("Gate-CD exact identity has an invalid source_commit")
    return actual


def _validate_gate_cd_scope(scope_path: str | Path, expected_sha256: str,
                            *, profile: str, run_id: str,
                            expected_identity: dict | None,
                            lock_directory: str | Path = "/tmp") -> tuple[dict, Path, str]:
    if profile not in GATE_CD_EXECUTION_PROFILES or run_id != profile:
        raise InputError("Gate-CD formal scope is restricted to an exact reviewed profile/run")
    path = Path(scope_path).resolve()
    try:
        raw = path.read_bytes()
        scope = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise InputError(f"Gate-CD exact scope is unreadable: {exc}") from exc
    digest = _sha(raw)
    if digest != str(expected_sha256).lower():
        raise InputError("Gate-CD exact scope SHA256 mismatch")
    if scope.get("schema") != GATE_CD_SCOPE_SCHEMA:
        raise InputError("Gate-CD exact scope schema is unsupported")
    identity = _validate_exact_identity(
        scope.get("identity"), expected_identity, profile, run_id
    )
    readiness = scope.get("formal_route_readiness")
    if not isinstance(readiness, dict) or readiness.get("launchable") is not True:
        raise InputError("Gate-CD formal route readiness is not launchable")
    contract = identity["direct_route_contract"]
    if not isinstance(contract, dict) or contract.get("full_dtn_status") != "FULL_DTN_NOT_VERIFIED":
        raise InputError("Gate-CD direct-route identity lost the finite-DTN limitation")
    resources = scope.get("resource_contract")
    if not isinstance(resources, dict) or (
        resources.get("policy") != "host_available_floor_v1"
        or resources.get("minimum_available_bytes") != 64 * 1024**3
        or resources.get("rss_hard_limit_bytes") is not None
        or resources.get("swap_policy") != "observe_only"
        or resources.get("stop_on_global_swap") is not False
        or resources.get("pss_sampling_policy") != "disabled_by_profile"
        or resources.get("uss_sampling_policy") != "disabled_by_profile"
        or resources.get("time_limit_mode") != "none"
    ):
        raise InputError("Gate-CD scope changes the 64 GiB/no-RSS-cap host-floor contract")
    cpu = scope.get("cpu_policy")
    required_worker_count = (
        GATE_CD_PARALLEL32_WORKERS
        if profile in GATE_CD_PARALLEL32_PROFILES
        else 1
    )
    observed_worker_count = (
        cpu.get("worker_count", required_worker_count)
        if isinstance(cpu, dict)
        else None
    )
    if not isinstance(cpu, dict) or (
        cpu.get("selection") != "sampled_low_load_distinct_physical_cores_v1"
        or float(cpu.get("sample_seconds", 0)) < 1.0
        or cpu.get("busy_fallback_allowed") is not True
        or cpu.get("exclusive_cpu_ownership") is not False
        or type(observed_worker_count) is not int
        or observed_worker_count != required_worker_count
        or (
            required_worker_count == GATE_CD_PARALLEL32_WORKERS
            and cpu.get("avoid_observed_active_solver_cores_when_capacity_allows") is not True
        )
    ):
        raise InputError("Gate-CD scope lacks its reviewed dynamic shared-CPU policy")
    attempt_id = scope.get("attempt_id")
    if not isinstance(attempt_id, str) or not _ATTEMPT_RE.fullmatch(attempt_id):
        raise InputError("Gate-CD scope has an invalid one-shot attempt id")
    if scope.get("runtime_paths") != _runtime_paths(
        profile, run_id, attempt_id, lock_directory
    ):
        raise InputError("Gate-CD runtime lock/cache paths differ from this exact attempt")
    neighbors = scope.get("parallel_neighbors")
    if not isinstance(neighbors, dict) or (
        neighbors.get("policy") != "gate_cd_observational_neighbors_v1"
        or neighbors.get("solver_candidates_block_admission") is not False
        or neighbors.get("unknown_solver_candidates_block_admission") is not False
        or neighbors.get("large_process_candidates_block_admission") is not False
        or neighbors.get("neighbors_modified") is not False
    ):
        raise InputError("Gate-CD scope must keep parallel processes observational, not blocking")
    raw_pool = scope.get("raw_tensor_pool_scheduler")
    if profile in GATE_CD_PARALLEL32_PROFILES:
        if not isinstance(raw_pool, dict) or raw_pool != {
            "policy": GATE_CD_RAW_POOL_SCHEDULER_POLICY,
            "lock_path": GATE_CD_RAW_POOL_LOCK_PATH,
            "serialized_region": "raw_tensor_execution.run_batch_only",
            "whole_run_serialization": False,
        }:
            raise InputError(
                "Gate-CD parallel32 scope lacks the shared raw tensor pool scheduler"
            )
    elif raw_pool is not None:
        raise InputError("serial Gate-CD profile must not request a parallel raw pool lock")
    return scope, path, digest


def _solver_thread_snapshot(proc_root: str | Path) -> dict:
    """Read solver-role processes and descendants with PID/start-tick identity."""
    root = Path(proc_root)
    process_rows = {}
    unreadable = 0
    for proc in root.glob("[0-9]*"):
        if not proc.name.isdigit():
            continue
        pid = int(proc.name)
        try:
            raw = (proc / "stat").read_text()
            fields = raw[raw.rfind(")") + 2 :].split()
            argv = [
                value.decode("utf-8", "replace")
                for value in (proc / "cmdline").read_bytes().split(bytes([0])) if value
            ]
            modules = [
                value for value in argv
                if value.startswith("src.runners.task038_")
            ]
            executable = Path(argv[0]).name if argv else ""
            if any(value.endswith("scripts/run_case.py") for value in argv):
                role = "run_case"
            elif executable in {"mpiexec", "mpirun"} and modules:
                role = "mpi"
            elif modules:
                role = modules[0].removeprefix("src.runners.")
            else:
                role = None
            cgroup = None
            try:
                for line in (proc / "cgroup").read_text().splitlines():
                    parts = line.split(":", 2)
                    if len(parts) == 3 and parts[0] == "0":
                        cgroup = parts[2]
                        break
            except OSError:
                pass
            try:
                cwd = str((proc / "cwd").resolve())
            except OSError:
                cwd = None
            try:
                affinity = sorted(os.sched_getaffinity(pid))
            except (OSError, ProcessLookupError, PermissionError):
                affinity = None
            process_rows[pid] = {
                "pid": pid,
                "start_ticks": int(fields[19]),
                "ppid": int(fields[1]),
                "state": fields[0],
                "role": role,
                "argv": argv,
                "cwd": cwd,
                "cgroup_path": cgroup,
                "affinity": affinity,
            }
        except (OSError, ValueError, IndexError, ProcessLookupError, PermissionError):
            unreadable += 1
    roots = {pid for pid, row in process_rows.items() if row["role"] is not None}
    tree = set(roots)
    changed = True
    while changed:
        changed = False
        for pid, row in process_rows.items():
            if pid not in tree and row["ppid"] in tree:
                tree.add(pid)
                changed = True
    selected = {pid: process_rows[pid] for pid in sorted(tree) if pid in process_rows}
    threads = {}
    thread_unreadable = 0
    for pid, row in selected.items():
        task_path = root / str(pid) / "task"
        try:
            tids = sorted(int(path.name) for path in task_path.iterdir() if path.name.isdigit())
        except OSError:
            tids = [pid]
        for tid in tids:
            try:
                stat_path = task_path / str(tid) / "stat"
                raw = stat_path.read_text()
                fields = raw[raw.rfind(")") + 2 :].split()
                threads[(pid, row["start_ticks"], tid)] = {
                    "cpu_ticks": int(fields[11]) + int(fields[12]),
                    "last_cpu": int(fields[36]),
                    "state": fields[0],
                    "role": row["role"],
                }
            except (OSError, ValueError, IndexError, ProcessLookupError):
                thread_unreadable += 1
    return {
        "captured_utc_epoch_ns": time.time_ns(),
        "solver_processes": list(selected.values()),
        "threads": threads,
        "unreadable_process_count": unreadable,
        "unreadable_thread_count": thread_unreadable,
        "processes_modified": False,
    }


def _active_solver_cpu_ids(before: dict, after: dict) -> tuple[set[int], dict]:
    before_threads = before.get("threads", {})
    after_threads = after.get("threads", {})
    active_cpu_ids = set()
    active_threads = []
    all_keys = set(before_threads) | set(after_threads)
    for key in sorted(all_keys):
        first = before_threads.get(key)
        last = after_threads.get(key)
        appeared_or_vanished = first is None or last is None
        tick_delta = (
            None if first is None or last is None
            else int(last["cpu_ticks"]) - int(first["cpu_ticks"])
        )
        is_active = appeared_or_vanished or (tick_delta is not None and tick_delta > 0) or (
            (first is not None and first["state"] == "R")
            or (last is not None and last["state"] == "R")
        )
        if not is_active:
            continue
        cpus = sorted({
            int(item["last_cpu"])
            for item in (first, last)
            if item is not None and int(item["last_cpu"]) >= 0
        })
        active_cpu_ids.update(cpus)
        active_threads.append({
            "pid": key[0],
            "start_ticks": key[1],
            "tid": key[2],
            "tick_delta": tick_delta,
            "appeared_or_vanished_during_sample": appeared_or_vanished,
            "last_cpu_ids_observed": cpus,
            "state_before": None if first is None else first["state"],
            "state_after": None if last is None else last["state"],
            "role": (last or first or {}).get("role"),
        })
    return active_cpu_ids, {
        "policy": "solver_tree_thread_ticks_last_cpu_endpoint_v1",
        "sampled_process_count_before": len(before.get("solver_processes", ())),
        "sampled_process_count_after": len(after.get("solver_processes", ())),
        "sampled_thread_count_before": len(before_threads),
        "sampled_thread_count_after": len(after_threads),
        "active_thread_count": len(active_threads),
        "active_cpu_ids": sorted(active_cpu_ids),
        "active_threads": active_threads,
        "solver_processes_before": before.get("solver_processes", ()),
        "solver_processes_after": after.get("solver_processes", ()),
        "unreadable_process_count_before": before.get("unreadable_process_count", 0),
        "unreadable_process_count_after": after.get("unreadable_process_count", 0),
        "unreadable_thread_count_before": before.get("unreadable_thread_count", 0),
        "unreadable_thread_count_after": after.get("unreadable_thread_count", 0),
        "last_cpu_is_endpoint_observation_not_full_cpu_history": True,
    }


def _choose_cpu_reservation(
    sample_seconds: float,
    proc_root: str | Path,
    *,
    worker_count: int = 1,
) -> dict:
    # Reuse the reviewed host-load sampler; add a per-thread sample over that
    # same bounded window. Affinity masks remain observational, never a claim
    # of exclusive CPU ownership.
    from .task40_d07c_g5_join import _core, choose_g5_cpu_reservation

    before = _solver_thread_snapshot(proc_root) if worker_count == GATE_CD_PARALLEL32_WORKERS else None
    sampled = choose_g5_cpu_reservation(
        sample_seconds=float(sample_seconds), proc_root=proc_root
    )
    if worker_count == GATE_CD_PARALLEL32_WORKERS:
        after = _solver_thread_snapshot(proc_root)
        active_solver_cpus, activity = _active_solver_cpu_ids(before or {}, after)
        active_solver_cores = {tuple(_core(cpu)) for cpu in active_solver_cpus}
        candidates = list(sampled.get("candidate_topology_and_load", ()))
        nonactive = [
            row for row in candidates
            if (int(row["package"]), int(row["core"])) not in active_solver_cores
        ]
        nonactive.sort(key=lambda row: (
            float(row["sampled_utilization"]),
            bool(row["heavy_neighbor_affinity_overlap"]),
            int(row["cpu"]),
        ))
        all_sorted = sorted(candidates, key=lambda row: (
            (int(row["package"]), int(row["core"])) in active_solver_cores,
            float(row["sampled_utilization"]),
            bool(row["heavy_neighbor_affinity_overlap"]),
            int(row["cpu"]),
        ))
        if len(candidates) < GATE_CD_PARALLEL32_WORKERS + 1:
            raise InputError(
                "Gate-CD parallel32 admission needs 32 distinct worker cores plus one supervisor core"
            )
        selected = (
            nonactive[: GATE_CD_PARALLEL32_WORKERS + 1]
            if len(nonactive) >= GATE_CD_PARALLEL32_WORKERS + 1
            else all_sorted[: GATE_CD_PARALLEL32_WORKERS + 1]
        )
        supervisor_cpu = int(selected[0]["cpu"])
        worker_cpus = [int(row["cpu"]) for row in selected[1:]]
        if len(set(worker_cpus)) != GATE_CD_PARALLEL32_WORKERS:
            raise InputError("Gate-CD parallel32 dynamic CPU admission returned duplicate workers")
        selected_active_cores = sorted({
            (int(row["package"]), int(row["core"]))
            for row in selected
            if (int(row["package"]), int(row["core"])) in active_solver_cores
        })
        neighbor_observation = sampled.get("neighbor_observation", {})
        solver_affinity_cpus = {
            int(cpu)
            for row in neighbor_observation.get("processes", ())
            if row.get("solver_role_observation")
            for cpu in row.get("affinity", ())
        }
        return {
            **sampled,
            "policy": "sampled_low_load_distinct_physical_cores_v1",
            "worker_count": GATE_CD_PARALLEL32_WORKERS,
            "supervisor_cpu": supervisor_cpu,
            "worker_cpu": worker_cpus[0],
            "worker_cpus": worker_cpus,
            "selected_topology": selected,
            "observed_active_solver_cpus": sorted(active_solver_cpus),
            "observed_active_solver_cores": [list(core) for core in sorted(active_solver_cores)],
            "selected_observed_active_solver_cores": [list(core) for core in selected_active_cores],
            "avoidance_fallback_used": bool(selected_active_cores),
            "active_solver_core_avoidance_when_capacity_allows": True,
            "active_solver_thread_sample": activity,
            "selected_solver_affinity_overlap_observed_only": sorted(
                set(worker_cpus + [supervisor_cpu]) & solver_affinity_cpus
            ),
            "exclusive_cpu_ownership": False,
        }
    if worker_count != 1:
        raise InputError("Gate-CD formal admission received an unsupported worker count")
    return {
        **sampled,
        "worker_count": 1,
        "worker_cpus": [int(sampled["worker_cpu"])],
        "route": "gate_cd_formal_dynamic_cpu_adapter_to_reviewed_task40_sampler",
        "exclusive_cpu_ownership": False,
    }


class GateCDRuntimeLease:
    def __init__(self, scope: dict, scope_path: Path, scope_sha256: str,
                 member_stream, member_path: Path, reservation_path: Path,
                 cpu_reservation: dict, cache_root: Path, submission_mode: str):
        self.scope, self.scope_path, self.scope_sha256 = scope, scope_path, scope_sha256
        self.member_stream, self.member_path = member_stream, member_path
        self.reservation_path, self.cpu_reservation = reservation_path, cpu_reservation
        self.cache_root, self.submission_mode = cache_root, submission_mode
        self._committed = False

    def summary(self) -> dict:
        profile = self.scope["identity"]["profile_identity"]
        return {
            "policy": "gate_cd_exact_one_shot_host_floor_v1",
            "profile_identity": profile,
            "run_id": profile,
            "attempt_id": self.scope["attempt_id"],
            "scope_path": str(self.scope_path),
            "scope_sha256": self.scope_sha256,
            "case_lock_path": str(self.member_path),
            "one_shot_reservation_path": str(self.reservation_path),
            "submission_mode": self.submission_mode,
            "cpu_reservation": self.cpu_reservation,
            "attempt_cache_root": str(self.cache_root),
            "canonical_heavy_lock_touched": False,
            "neighbors_modified": False,
        }

    def prepare_attempt_cache(self) -> dict[str, Path]:
        if self.submission_mode != "runtime":
            raise InputError("Gate-CD caches are created only for the runtime one-shot")
        root = self.cache_root
        root.mkdir(mode=0o700, parents=False, exist_ok=False)
        dirs = {"root": root}
        for name in ("tmp", "xdg", "pycache", "mpl"):
            path = root / name
            path.mkdir(mode=0o700)
            dirs[name] = path
        if self.scope["cpu_policy"].get("worker_count") == GATE_CD_PARALLEL32_WORKERS:
            for name in ("tensor", "carrier"):
                path = root / name
                path.mkdir(mode=0o700)
                dirs[name] = path
        if any(path.is_symlink() for path in dirs.values()):
            raise InputError("Gate-CD attempt cache paths must not be symlinks")
        return dirs

    def commit_runtime_submission(self) -> None:
        if self.submission_mode != "runtime":
            return
        if self._committed:
            raise InputError("Gate-CD one-shot lease was already committed")
        payload = {
            "schema": "task40.gate_cd.formal_one_shot_submission.v1",
            "profile_identity": self.scope["identity"]["profile_identity"],
            "run_id": self.scope["identity"]["run_id"],
            "attempt_id": self.scope["attempt_id"],
            "scope_sha256": self.scope_sha256,
            "cpu_reservation": self.cpu_reservation,
            "committed_utc_epoch_ns": time.time_ns(),
            "submission_mode": self.submission_mode,
        }
        raw = _json_bytes(payload)
        try:
            fd = os.open(self.reservation_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError as exc:
            raise InputError("Gate-CD attempt was already submitted; no retry") from exc
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        self._committed = True


@contextmanager
def gate_cd_runtime_lease(profile: str, run_id: str, *, scope_path: str | Path,
                          scope_sha256: str, expected_identity: dict,
                          submission_mode: str = "runtime", lock_directory: str | Path = "/tmp",
                          proc_root: str | Path = "/proc",
                          cpu_selector=_choose_cpu_reservation):
    if submission_mode not in {"fresh_check", "runtime"}:
        raise InputError("Gate-CD submission mode is unsupported")
    scope, path, digest = _validate_gate_cd_scope(
        scope_path, scope_sha256, profile=profile, run_id=run_id,
        expected_identity=expected_identity, lock_directory=lock_directory,
    )
    paths = scope["runtime_paths"]
    lock_path = Path(paths["member_lock"])
    reservation_path = Path(paths["one_shot_reservation"])
    cache_root = Path(paths["attempt_cache_root"])
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if reservation_path.exists():
        raise InputError("Gate-CD one-shot reservation already exists; no retry")
    if cache_root.exists() or cache_root.is_symlink():
        raise InputError("Gate-CD attempt cache path already exists")
    member = lock_path.open("a")
    try:
        try:
            fcntl.flock(member.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise InputError("Gate-CD exact profile/run lease is already held") from exc
        if reservation_path.exists():
            raise InputError("Gate-CD one-shot reservation appeared during admission")
        worker_count = int(scope["cpu_policy"].get("worker_count", 1))
        if worker_count == 1:
            reservation = cpu_selector(
                float(scope["cpu_policy"]["sample_seconds"]), proc_root
            )
        else:
            reservation = cpu_selector(
                float(scope["cpu_policy"]["sample_seconds"]),
                proc_root,
                worker_count=worker_count,
            )
        cpus = reservation.get("worker_cpus", ())
        supervisor_cpu = reservation.get("supervisor_cpu")
        if (
            len(cpus) != worker_count
            or len(set(map(int, cpus))) != worker_count
            or type(supervisor_cpu) is not int
            or supervisor_cpu in set(map(int, cpus))
        ):
            raise InputError("Gate-CD CPU lease does not match the exact worker count")
        lease = GateCDRuntimeLease(
            scope, path, digest, member, lock_path, reservation_path,
            reservation, cache_root, submission_mode,
        )
        yield lease
    finally:
        try:
            fcntl.flock(member.fileno(), fcntl.LOCK_UN)
        finally:
            member.close()
