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
GATE_CD_EXECUTION_PROFILES = frozenset(
    {GATE_CD_FORMAL_PROFILE, GATE_CD_PARALLEL32_PROFILE}
)
GATE_CD_PARALLEL32_WORKERS = 32
GATE_CD_SCOPE_SCHEMA = "task40.gate_cd_formal_exact_execution_scope.v1"
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
        if profile == GATE_CD_PARALLEL32_PROFILE
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
            and cpu.get("avoid_active_solver_affinity_overlap") is not True
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
    return scope, path, digest


def _choose_cpu_reservation(
    sample_seconds: float,
    proc_root: str | Path,
    *,
    worker_count: int = 1,
) -> dict:
    # Reuse the already reviewed dynamic sampler, preserving its CPU-load,
    # affinity observation, distinct-core, and non-exclusive semantics.
    from .task40_d07c_g5_join import _core, choose_g5_cpu_reservation

    sampled = choose_g5_cpu_reservation(
        sample_seconds=float(sample_seconds), proc_root=proc_root
    )
    if worker_count == GATE_CD_PARALLEL32_WORKERS:
        candidates = list(sampled.get("candidate_topology_and_load", ()))
        neighbor_observation = sampled.get("neighbor_observation", {})
        active_solver_cpus = {
            int(cpu)
            for row in neighbor_observation.get("processes", ())
            if row.get("solver_role_observation")
            for cpu in row.get("affinity", ())
        }
        active_solver_cores = {
            tuple(_core(cpu)) for cpu in active_solver_cpus
        }
        eligible = [
            row for row in candidates
            if (int(row["package"]), int(row["core"])) not in active_solver_cores
        ]
        eligible.sort(key=lambda row: (
            float(row["sampled_utilization"]),
            bool(row["heavy_neighbor_affinity_overlap"]),
            int(row["cpu"]),
        ))
        if len(eligible) < GATE_CD_PARALLEL32_WORKERS + 1:
            raise InputError(
                "Gate-CD N14 admission needs 32 distinct worker cores plus one "
                "supervisor core after excluding active solver affinities"
            )
        selected = eligible[: GATE_CD_PARALLEL32_WORKERS + 1]
        supervisor_cpu = int(selected[0]["cpu"])
        worker_cpus = [int(row["cpu"]) for row in selected[1:]]
        if len(set(worker_cpus)) != GATE_CD_PARALLEL32_WORKERS:
            raise InputError("Gate-CD N14 dynamic CPU admission returned duplicate workers")
        return {
            **sampled,
            "policy": "sampled_low_load_distinct_physical_cores_v1",
            "worker_count": GATE_CD_PARALLEL32_WORKERS,
            "supervisor_cpu": supervisor_cpu,
            "worker_cpu": worker_cpus[0],
            "worker_cpus": worker_cpus,
            "selected_topology": selected,
            "excluded_active_solver_cpus": sorted(active_solver_cpus),
            "excluded_active_solver_cores": [
                list(core) for core in sorted(active_solver_cores)
            ],
            "active_solver_affinity_avoidance": True,
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
