"""Fail-closed fresh/systemd entry for the finite Gate-CD signed-window route.

The package binds the selected q21 and mapped-geometry cache witnesses; the
route remains a finite signed rectangle and is not full-DtN qualified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

GATE_CD_FORMAL_PROFILE = "task40_gate_cd_0p7_mapped_m8n64_p6_direct_v1"
GATE_CD_PARALLEL32_PROFILE = (
    "task40_gate_cd_0p7_mapped_m8n14_p6_direct_parallel32_v1"
)
GATE_CD_M8N6_PROFILE = "task40_gate_cd_0p7_mapped_m8n6_p6_direct_v1"
GATE_CD_M8N2_PROFILE = "task40_gate_cd_0p7_mapped_m8n2_p6_direct_v1"
GATE_CD_FIN0_STI_Z10_M8N2_PROFILE = (
    "task40_gate_cd_fin0_sti_z10_m8n2_p6_direct_v1"
)
GATE_CD_SIGNED_SUBRECTANGLE_PROFILES = frozenset(
    {
        GATE_CD_M8N6_PROFILE,
        GATE_CD_M8N2_PROFILE,
        GATE_CD_FIN0_STI_Z10_M8N2_PROFILE,
    }
)
GATE_CD_PARALLEL32_PROFILES = frozenset(
    {GATE_CD_PARALLEL32_PROFILE, *GATE_CD_SIGNED_SUBRECTANGLE_PROFILES}
)
GATE_CD_FORMAL_PROFILES = frozenset(
    {
        GATE_CD_FORMAL_PROFILE,
        GATE_CD_PARALLEL32_PROFILE,
        *GATE_CD_SIGNED_SUBRECTANGLE_PROFILES,
    }
)
GATE_CD_PARALLEL32_WORKERS = 32
from src.runners.task40_gate_cd_formal_admission import (
    GATE_CD_RAW_POOL_LOCK_PATH,
    GATE_CD_RAW_POOL_SCHEDULER_POLICY,
)

_SERVICE_PROPERTIES = {
    "Type": "exec",
    "Restart": "no",
    "RuntimeMaxSec": "infinity",
    "KillMode": "mixed",
    "TimeoutStopSec": "infinity",
}
_CAPTURE_ENV = {
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "_MYFENICS_NATIVE_QUALIFIED_ACTIVATION",
    "TASK39EXTRA_INT64_ACTIVATION",
    "TASK39EXTRA_PORD64_ACTIVATION",
    "TASK40_EXACT_CACHE_CONTRACT",
    "TASK40_EXACT_CACHE_CONTRACT_SHA256",
    "TASK40_EXACT_CACHE_WORKER_CPUS",
    "TASK40_EXACT_CACHE_ATTEMPT_ID",
    "TASK40_EXACT_CACHE_RUNTIME_TEMPLATE_SHA256",
    "TASK40_EXACT_CACHE_REUSE_MODE",
    "TASK40_EXACT_CACHE_REUSE_CONTRACT",
    "TASK40_EXACT_CACHE_REUSE_CONTRACT_SHA256",
    "TASK40_EXACT_CACHE_REUSE_HOOK_ACTIVE",
    "TASK40_GATE_CD_ATTEMPT_CACHE_ROOT",
    "PYTHONPATH",
    "TASK40_GATE_CD_PRELU_READY_PATH",
    "TASK40_GATE_CD_PRELU_RELEASE_PATH",
    "TASK40_GATE_CD_PRELU_ACCEPTED_PATH",
    "TASK40_GATE_CD_EXPECTED_UNIT",
    "TASK40_GATE_CD_ATTEMPT_ID",
    "TASK40_GATE_CD_PACKAGE_SHA256",
    "TASK40_GATE_CD_ORIGINAL272_UNIT",
    "TASK40_GATE_CD_ORIGINAL272_INVOCATION_ID",
}
_MATH_THREAD_ENV = {
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "BLIS_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
}
_GATE_CD_SIGNED_SELECTION_RESIDUE = {
    "attempt_id": "20261102T151803.010130Z",
    "source_commit": "6eeb980f5ac5f2e6ce285f7b98f95dbd9864e259",
    "service_unit": "task40-gate-cd-m8n14-p32-6eeb980f-d57fa6d1.service",
    "invocation_id": "6ed350f3cae74627b422f72940ced056",
    "journal_main_exit_status": 3,
    "journal_main_exit_text": "3/NOTIMPLEMENTED",
    "journal_unit_result": "exit-code",
    "worker_exit_status": 4,
}


def sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load_json(path: str | Path) -> dict:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected a JSON object: {path}")
    return value


def _atomic_json(path: str | Path, value: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()
    fd, temp_name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
        dir_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def _require_systemd_unit_not_loaded(unit: str, *, timeout_seconds: float = 5.0) -> str:
    """Proceed only when the user manager proves the unique unit is absent."""
    try:
        result = subprocess.run(
            ["systemctl", "--user", "show", unit, "--property=LoadState"],
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "user systemd did not answer the bounded unit-state query; "
            "cannot prove the reviewed unit is absent"
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(
            "user systemd unit-state query failed; cannot prove the reviewed unit is absent"
        )
    states = [
        line.split("=", 1)[1].strip()
        for line in result.stdout.splitlines()
        if line.startswith("LoadState=")
    ]
    if len(states) != 1 or not states[0]:
        raise RuntimeError(
            "user systemd returned no unique LoadState; cannot prove the reviewed unit is absent"
        )
    if states[0] != "not-found":
        raise ValueError(
            "the exact service unit already exists or has an unknown load state; no duplicate"
        )
    return states[0]


def _require_final_package(package: dict) -> None:
    if package.get("schema") != "task40.gate_cd.formal_package.v1":
        raise ValueError("unsupported Gate-CD final package schema")
    if package.get("execution_authorized") is not True:
        raise ValueError("draft package is not executable")
    readiness = package.get("route_readiness")
    if not isinstance(readiness, dict) or readiness.get("launchable") is not True:
        raise ValueError("Gate-CD profile is not launchable")
    quad = package.get("quadrature_contract")
    if not isinstance(quad, dict):
        raise TypeError("final quadrature contract is missing")
    if quad.get("volume_degree") not in (15, 21, 27):
        raise ValueError("selected volume degree is not a reviewed q15/q21/q27 value")
    if quad.get("surface_degree") != 81 or quad.get("surface_rule") != "default":
        raise ValueError("surface rule differs from the reviewed Gate-CD contract")
    if package.get("mapped_geometry_identity") != "mapped_exact":
        raise ValueError("mapped geometry must retain exact physical-coordinate identity")
    cache_policy = package.get("mapped_geometry_cache_policy")
    if not isinstance(cache_policy, dict):
        raise TypeError("package must bind the exact live mapped-geometry cache policy")
    normalized = package.get("translation_normalized_cache")
    if not isinstance(normalized, bool):
        raise TypeError("translation-normalized cache selection must be boolean")
    if (
        cache_policy.get("geometry_identity_policy")
        != package.get("mapped_geometry_identity")
        or cache_policy.get("mapped_geometry_translation_invariant") is not normalized
    ):
        raise ValueError("package cache identity and translation selection differ")
    if normalized and (
        cache_policy.get("translation_normalized_candidate") is not True
        or cache_policy.get("translation_equivalence_status")
        != "PASS_BOUNDED_TRANSLATION_EQUIVALENCE"
        or not isinstance(cache_policy.get("translation_equivalence_witness"), dict)
    ):
        raise ValueError(
            "translation-normalized cache requires the reviewed bounded witness"
        )
    profile = package.get("profile_identity", GATE_CD_FORMAL_PROFILE)
    if profile not in GATE_CD_FORMAL_PROFILES:
        raise ValueError("package does not name a supported exact Gate-CD profile")
    if profile in GATE_CD_PARALLEL32_PROFILES:
        execution = package.get("execution_contract")
        exact_cache = package.get("exact_cache_contract")
        if (
            not isinstance(execution, dict)
            or execution.get("mpi_size") != 1
            or execution.get("worker_cpu_count") != GATE_CD_PARALLEL32_WORKERS
            or execution.get("math_threads") != 1
            or execution.get("global_assembly") != "serial_single_mpi_rank_v1"
            or execution.get("global_lu") != "serial_single_mpi_rank_v1"
            or not isinstance(exact_cache, dict)
            or exact_cache.get("worker_count") != GATE_CD_PARALLEL32_WORKERS
            or exact_cache.get("profile_identity") != profile
            or exact_cache.get("run_id") != package.get("run_id")
            or exact_cache.get("operator_identity")
            != {"scalar": "complex128", "q": 21, "degree": 6}
            or exact_cache.get("raw_tensor_pool_scheduler") != {
                "policy": GATE_CD_RAW_POOL_SCHEDULER_POLICY,
                "lock_path": GATE_CD_RAW_POOL_LOCK_PATH,
                "serialized_region": "raw_tensor_execution.run_batch_only",
                "whole_run_serialization": False,
            }
            or package.get("full_dtn_status") != "FULL_DTN_NOT_VERIFIED"
        ):
            raise ValueError("Gate-CD M8N14 execution/cache contract is malformed")


def _validate_live_profile_contract(package: dict, facts: dict) -> None:
    options = facts.get("component_options", {})
    route = facts.get("campaign_authorization", {}).get("direct_route", {})
    quadrature = package.get("quadrature_contract", {})
    surface = options.get("surface_quadrature", {})
    volume = options.get("volume_quadrature", {})
    if (
        surface.get("degree") != quadrature.get("surface_degree")
        or surface.get("rule") != quadrature.get("surface_rule")
        or route.get("surface_quadrature_degree") != surface.get("degree")
    ):
        raise ValueError(
            "live component and campaign surface quadrature differ from the package"
        )
    if (
        volume.get("degree") != quadrature.get("volume_degree")
        or volume.get("rule") != quadrature.get("volume_rule")
        or route.get("volume_quadrature") != volume
    ):
        raise ValueError(
            "live component and campaign volume quadrature/witness differ from the package"
        )

    cache = options.get("mapped_geometry_cache_policy")
    condensed = facts.get("condensed_route", {})
    if not isinstance(cache, dict):
        raise TypeError("live profile has no mapped-geometry cache policy")
    if package.get("mapped_geometry_cache_policy") != cache:
        raise ValueError("package cache policy differs from the exact live profile facts")
    if (
        package.get("mapped_geometry_identity")
        != route.get("geometry_identity_policy")
        or route.get("mapped_geometry_cache_identity") != cache.get("identity")
        or route.get("mapped_geometry_translation_invariant")
        is not cache.get("mapped_geometry_translation_invariant")
        or condensed.get("geometry_identity_policy")
        != cache.get("geometry_identity_policy")
        or condensed.get("mapped_geometry_translation_invariant")
        is not cache.get("mapped_geometry_translation_invariant")
        or package.get("translation_normalized_cache")
        is not cache.get("mapped_geometry_translation_invariant")
    ):
        raise ValueError("live route cache identity differs from package/profile")
    if package.get("profile_identity") in GATE_CD_PARALLEL32_PROFILES:
        mode = options.get("mode_selection", {})
        operator = package.get("finite_operator", {})
        checks = {
            "active_mode_count": mode.get("expected_active_mode_count"),
            "active_mode_sha256": mode.get("expected_active_mode_sha256"),
            "active_signed_bounds_mn": mode.get("active_signed_bounds_mn"),
            "parent_mode_count": mode.get("expected_mode_count"),
            "parent_mode_sha256": mode.get("expected_mode_sha256"),
            "parent_signed_bounds_mn": mode.get("parent_signed_bounds_mn"),
            "selected_parent_indices_sha256": mode.get(
                "expected_selected_parent_indices_sha256"
            ),
            "selected_signed_keys_sha256": mode.get(
                "expected_selected_signed_keys_sha256"
            ),
            "propagating_mode_count": mode.get(
                "expected_active_propagating_count"
            ),
            "power_carrying_mode_count": mode.get(
                "expected_active_power_carrying_count"
            ),
        }
        mismatches = {
            key: {"package": operator.get(key), "profile": value}
            for key, value in checks.items()
            if operator.get(key) != value
        }
        if mismatches:
            raise ValueError(
                f"Gate-CD {mode.get('reference_mode_label')} finite operator differs "
                f"from live profile: {mismatches}"
            )
    if package.get("profile_identity") in GATE_CD_PARALLEL32_PROFILES:
        execution = package.get("execution_contract", {})
        exact_cache = package.get("exact_cache_contract", {})
        native = facts.get("native_execution", {})
        required = {
            "worker_cpu_count": 32,
            "mpi_size": 1,
            "math_threads": 1,
            "raw_tensor_execution": "exact_cache_exec_tensor_workers_v1",
            "global_assembly": "serial_single_mpi_rank_v1",
            "global_lu": "serial_single_mpi_rank_v1",
        }
        observed = {
            "worker_cpu_count": native.get("worker_cpu_count"),
            "mpi_size": native.get("mpi_size"),
            "math_threads": native.get("math_threads"),
            "raw_tensor_execution": native.get("raw_tensor_execution"),
            "lu_execution": native.get("lu_execution"),
        }
        expected_observed = {
            "worker_cpu_count": 32,
            "mpi_size": 1,
            "math_threads": 1,
            "raw_tensor_execution": "exact_cache_exec_tensor_workers_v1",
            "lu_execution": "serial_single_mpi_rank_v1",
        }
        if (
            execution != required
            or observed != expected_observed
            or exact_cache.get("worker_count") != 32
            or exact_cache.get("profile_identity") != package.get("profile_identity")
            or exact_cache.get("run_id") != package.get("run_id")
            or exact_cache.get("operator_identity")
            != {"scalar": "complex128", "q": 21, "degree": 6}
            or exact_cache.get("raw_tensor_pool_scheduler")
            != {
                "policy": GATE_CD_RAW_POOL_SCHEDULER_POLICY,
                "lock_path": GATE_CD_RAW_POOL_LOCK_PATH,
                "serialized_region": "raw_tensor_execution.run_batch_only",
                "whole_run_serialization": False,
            }
            or route.get("exact_cache_contract_required") is not True
            or route.get("raw_tensor_worker_count") != 32
            or route.get("exact_cache_source_policy")
            != "clean_commit_and_resolved_payload_hash_bound_v1"
        ):
            raise ValueError(
                "Gate-CD parallel32 package/profile execution or exact-cache identity differs"
            )


def _runtime_reservation_path(sidecar: dict) -> tuple[dict, Path, str]:
    scope_path = Path(sidecar["scope_path"]).resolve()
    raw = scope_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if digest != sidecar.get("scope_sha256"):
        raise ValueError("runtime scope changed after fresh acceptance")
    scope = json.loads(raw)
    paths = scope.get("runtime_paths")
    if not isinstance(paths, dict):
        raise TypeError("runtime scope lacks its one-shot reservation path")
    lock_directory = Path(sidecar.get("lock_directory", "")).resolve()
    if Path(paths.get("lock_directory", "")).resolve() != lock_directory:
        raise ValueError("runtime scope lock directory differs from the sidecar")
    raw_path = paths.get("one_shot_reservation")
    if not isinstance(raw_path, str) or not raw_path:
        raise ValueError("runtime one-shot reservation path is invalid")
    reservation_path = Path(raw_path).resolve()
    if reservation_path.parent != lock_directory:
        raise ValueError("runtime reservation is outside the reviewed lock directory")
    return scope, reservation_path, digest


def _wait_for_runtime_cpu_reservation(
    sidecar: dict,
    package: dict,
    *,
    timeout_seconds: float = 30.0,
    poll_seconds: float = 0.2,
) -> tuple[dict, str, str]:
    scope, path, scope_sha = _runtime_reservation_path(sidecar)
    expected_identity = scope.get("identity", {})
    if (
        expected_identity.get("profile_identity") != package.get("profile_identity")
        or expected_identity.get("run_id") != package.get("run_id")
    ):
        raise ValueError("runtime scope profile/run differs from the package")
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    while True:
        try:
            raw = path.read_bytes()
        except FileNotFoundError:
            if time.monotonic() >= deadline:
                raise TimeoutError(
                    "runtime CPU reservation was not committed after systemd submission"
                )
            time.sleep(max(0.01, float(poll_seconds)))
            continue
        try:
            reservation = json.loads(raw)
        except json.JSONDecodeError:
            if time.monotonic() >= deadline:
                raise ValueError(
                    "runtime CPU reservation stayed unreadable after bounded wait"
                )
            time.sleep(max(0.01, float(poll_seconds)))
            continue
        if (
            reservation.get("schema")
            != "task40.gate_cd.formal_one_shot_submission.v1"
            or reservation.get("profile_identity") != package.get("profile_identity")
            or reservation.get("run_id") != package.get("run_id")
            or reservation.get("attempt_id") != scope.get("attempt_id")
            or reservation.get("scope_sha256") != scope_sha
            or reservation.get("submission_mode") != "runtime"
        ):
            raise ValueError("runtime one-shot reservation identity mismatch")
        cpu = reservation.get("cpu_reservation")
        if not isinstance(cpu, dict):
            raise TypeError("runtime one-shot reservation has no CPU record")
        worker_cpus = cpu.get("worker_cpus")
        if not isinstance(worker_cpus, list) or not worker_cpus:
            worker = cpu.get("worker_cpu")
            if not isinstance(worker, int):
                raise ValueError("runtime CPU reservation has no worker CPU")
            worker_cpus = [worker]
        if any(not isinstance(value, int) or value < 0 for value in worker_cpus):
            raise ValueError("runtime worker CPU reservation is invalid")
        expected_worker_count = (
            GATE_CD_PARALLEL32_WORKERS
            if package.get("profile_identity") in GATE_CD_PARALLEL32_PROFILES
            else 1
        )
        if (
            len(worker_cpus) != expected_worker_count
            or len(set(worker_cpus)) != expected_worker_count
        ):
            raise ValueError(
                f"Gate-CD runtime lease must reserve exactly {expected_worker_count} distinct worker CPUs"
            )
        if cpu.get("worker_cpu") != worker_cpus[0]:
            raise ValueError("runtime worker_cpu and worker_cpus disagree")
        supervisor_cpu = cpu.get("supervisor_cpu")
        if not isinstance(supervisor_cpu, int) or supervisor_cpu in set(worker_cpus):
            raise ValueError("runtime supervisor/worker CPU reservation is invalid")
        if expected_worker_count == GATE_CD_PARALLEL32_WORKERS:
            topology = cpu.get("selected_topology")
            observed_active_cores = {
                tuple(int(value) for value in row)
                for row in cpu.get("observed_active_solver_cores", ())
                if isinstance(row, list) and len(row) == 2
            }
            candidate_rows = cpu.get("candidate_topology_and_load")
            if (
                cpu.get("active_solver_core_avoidance_when_capacity_allows") is not True
                or not isinstance(topology, list)
                or len(topology) != GATE_CD_PARALLEL32_WORKERS + 1
                or [int(row.get("cpu", -1)) for row in topology]
                != [supervisor_cpu, *worker_cpus]
                or not isinstance(candidate_rows, list)
            ):
                raise ValueError("Gate-CD parallel32 runtime lease lacks its sampled-core reservation proof")
            topology_cores = [
                (int(row.get("package", -1)), int(row.get("core", -1)))
                for row in topology
            ]
            candidate_cores = {
                (int(row.get("package", -1)), int(row.get("core", -1)))
                for row in candidate_rows
            }
            inactive_count = len(candidate_cores - observed_active_cores)
            fallback_required = inactive_count < GATE_CD_PARALLEL32_WORKERS + 1
            selected_active_cores = sorted(set(topology_cores) & observed_active_cores)
            reported_selected = sorted(
                tuple(int(value) for value in row)
                for row in cpu.get("selected_observed_active_solver_cores", ())
            )
            if (
                len(set(topology_cores)) != len(topology_cores)
                or type(cpu.get("avoidance_fallback_used")) is not bool
                or cpu.get("avoidance_fallback_used") is not fallback_required
                or reported_selected != selected_active_cores
                or (not fallback_required and selected_active_cores)
                or (fallback_required and not selected_active_cores)
            ):
                raise ValueError(
                    "Gate-CD parallel32 CPU selection contradicts the sampled active-core capacity"
                )
        return reservation, hashlib.sha256(raw).hexdigest(), scope_sha


def validate_package_sidecar(
    package_path: str | Path, sidecar_path: str | Path
) -> tuple[dict, dict, str, str]:
    package_path = Path(package_path).resolve()
    sidecar_path = Path(sidecar_path).resolve()
    package = _load_json(package_path)
    sidecar = _load_json(sidecar_path)
    package_sha = sha256_file(package_path)
    sidecar_sha = sha256_file(sidecar_path)
    _require_final_package(package)
    if sidecar.get("schema") != "task40.gate_cd.formal_sidecar.v1":
        raise ValueError("unsupported Gate-CD sidecar schema")
    package_profile = package.get("profile_identity", GATE_CD_FORMAL_PROFILE)
    sidecar_profile = sidecar.get("profile_identity")
    if (
        sidecar_profile is not None
        and sidecar_profile != package_profile
    ) or (
        package_profile in GATE_CD_PARALLEL32_PROFILES
        and sidecar_profile != package_profile
    ):
        raise ValueError("package/sidecar profile identity mismatch")
    if sidecar.get("package_sha256") != package_sha:
        raise ValueError("sidecar does not bind the exact package bytes")
    if sidecar.get("source_commit") != package.get("source_commit"):
        raise ValueError("package/sidecar source identity mismatch")
    if sidecar.get("input_sha256") != package.get("input_sha256"):
        raise ValueError("package/sidecar input identity mismatch")
    if sidecar.get("physical_model_sha256") != package.get("physical_model_sha256"):
        raise ValueError("package/sidecar physical identity mismatch")
    if sidecar.get("resolved_config_sha256") != package.get("resolved_config_sha256"):
        raise ValueError("package/sidecar resolved identity mismatch")
    if package.get("profile_identity") in GATE_CD_PARALLEL32_PROFILES:
        exact_cache = package.get("exact_cache_contract", {})
        template_path = Path(
            sidecar.get("exact_cache_template_path", "")
        ).resolve(strict=True)
        template_sha = sidecar.get("exact_cache_template_sha256")
        if (
            not isinstance(exact_cache, dict)
            or str(template_path) != exact_cache.get("template_path")
            or template_sha != exact_cache.get("template_sha256")
            or sha256_file(template_path) != template_sha
            or package.get("identity", {}).get("direct_route_contract", {}).get(
                "exact_cache_contract_template_sha256"
            ) != template_sha
        ):
            raise ValueError("package/sidecar exact-cache template binding mismatch")
        template = _load_json(template_path)
        if (
            template.get("source_sha") != package.get("source_commit")
            or template.get("resolved_payload_sha256")
            != package.get("resolved_payload_sha256")
            or template.get("profile_identity") != package.get("profile_identity")
            or template.get("run_id") != package.get("run_id")
            or template.get("worker_count") != GATE_CD_PARALLEL32_WORKERS
            or template.get("operator_identity")
            != {"scalar": "complex128", "q": 21, "degree": 6}
        ):
            raise ValueError("exact-cache template differs from the final case identity")
        scope_path = Path(sidecar.get("scope_path", "")).resolve(strict=True)
        scope_raw = scope_path.read_bytes()
        scope_sha = hashlib.sha256(scope_raw).hexdigest()
        if scope_sha != sidecar.get("scope_sha256"):
            raise ValueError("sidecar scope SHA256 mismatch")
        scope = json.loads(scope_raw)
        runtime_paths = scope.get("runtime_paths", {})
        if (
            scope.get("identity") != package.get("identity")
            or scope.get("attempt_id") != package.get("attempt_id")
            or scope.get("raw_tensor_pool_scheduler")
            != {
                "policy": GATE_CD_RAW_POOL_SCHEDULER_POLICY,
                "lock_path": GATE_CD_RAW_POOL_LOCK_PATH,
                "serialized_region": "raw_tensor_execution.run_batch_only",
                "whole_run_serialization": False,
            }
            or scope.get("planned_systemd_user_unit") != sidecar.get("service_unit")
            or runtime_paths.get("attempt_cache_root")
            != sidecar.get("attempt_cache_root")
            or runtime_paths.get("lock_directory") != sidecar.get("lock_directory")
            or scope.get("cpu_policy", {}).get("worker_count")
            != GATE_CD_PARALLEL32_WORKERS
        ):
            raise ValueError("Gate-CD parallel32 scope does not bind the exact package/sidecar/cache lease")
    if package.get("profile_identity") == GATE_CD_FIN0_STI_Z10_M8N2_PROFILE:
        route = package.get("identity", {}).get("direct_route_contract", {})
        contract = route.get("pre_lu_pause")
        pause = sidecar.get("pre_lu_pause")
        if not isinstance(contract, dict) or not isinstance(pause, dict):
            raise ValueError("z10 package/sidecar lacks its exact pre-LU pause contract")
        if any(pause.get(key) != value for key, value in contract.items()):
            raise ValueError("z10 sidecar pause contract differs from package identity")
        if (
            package.get("attempt_id") != sidecar.get("attempt_id")
            or pause.get("attempt_id") != package.get("attempt_id")
            or pause.get("service_unit") != sidecar.get("service_unit")
            or pause.get("package_sha256") != package_sha
            or pause.get("package_sha256") != sidecar.get("package_sha256")
        ):
            raise ValueError("z10 sidecar pause identity differs from package attempt")
        root = Path(sidecar.get("attempt_cache_root", "")).resolve()
        expected_paths = {
            "ready_path": root / "pre_lu_pause" / "ready.json",
            "release_path": root / "pre_lu_pause" / "release.json",
            "accepted_path": root / "pre_lu_pause" / "accepted.json",
        }
        observed_paths = {}
        for key, expected in expected_paths.items():
            value = pause.get(key)
            if not isinstance(value, str) or not Path(value).is_absolute():
                raise ValueError(f"z10 sidecar {key} must be absolute")
            observed_paths[key] = Path(value).resolve()
            if observed_paths[key] != expected.resolve():
                raise ValueError(f"z10 sidecar {key} differs from the attempt cache")
        if len(set(observed_paths.values())) != len(observed_paths):
            raise ValueError("z10 pre-LU pause evidence paths must be distinct")
        scope_path = Path(sidecar.get("scope_path", "")).resolve(strict=True)
        scope = _load_json(scope_path)
        if (
            scope.get("identity") != package.get("identity")
            or scope.get("attempt_id") != package.get("attempt_id")
            or scope.get("planned_systemd_user_unit") != sidecar.get("service_unit")
            or scope.get("package_sha256") != package_sha
            or scope.get("identity", {})
            .get("direct_route_contract", {})
            .get("pre_lu_pause") != contract
        ):
            raise ValueError("z10 scope does not bind package and pre-LU pause")
        reuse = package.get("verified_cache_reuse")
        sidecar_reuse = sidecar.get("verified_cache_reuse")
        if not isinstance(reuse, dict) or sidecar_reuse != reuse:
            raise ValueError("z10 package/sidecar lacks the exact verified-cache reuse contract")
        contract_path = Path(reuse.get("contract_path", ""))
        if not contract_path.is_absolute() or contract_path.is_symlink():
            raise ValueError("z10 verified-cache contract path is not absolute and regular")
        contract_raw = contract_path.read_bytes()
        if hashlib.sha256(contract_raw).hexdigest() != reuse.get("contract_sha256"):
            raise ValueError("z10 verified-cache contract SHA256 mismatch")
        reuse_contract = json.loads(contract_raw)
        if (
            reuse.get("mode") != "verified_cache_only_v1"
            or reuse.get("target_attempt_id") != package.get("attempt_id")
            or reuse.get("target_attempt_cache_root") != sidecar.get("attempt_cache_root")
            or Path(reuse_contract.get("target_attempt_cache_root", "")).resolve()
            != root
            or reuse_contract.get("target_attempt_id") != package.get("attempt_id")
            or reuse_contract.get("profile_identity") != package.get("profile_identity")
            or reuse_contract.get("run_id") != package.get("run_id")
            or reuse_contract.get("raw_tensor_count") != 7288
            or reuse_contract.get("carrier_count") != 272
            or reuse_contract.get("require_cache_hits_only") is not True
            or reuse_contract.get("allow_compute_on_miss") is not False
            or reuse_contract.get("allow_source_cache_writes") is not False
            or Path(reuse.get("hook_directory", "")).resolve()
            != Path(sidecar.get("activation_script", "")).resolve().parent
        ):
            raise ValueError("z10 verified-cache reuse contract differs from the new exact attempt")
        for key, expected in (
            ("TASK40_EXACT_CACHE_REUSE_MODE", reuse["mode"]),
            ("TASK40_EXACT_CACHE_REUSE_CONTRACT", str(contract_path.resolve())),
            ("TASK40_EXACT_CACHE_REUSE_CONTRACT_SHA256", reuse["contract_sha256"]),
        ):
            if (
                sidecar.get("service_environment", {}).get(key) != expected
                or f"--setenv={key}={expected}" not in sidecar.get("systemd_run_argv", [])
            ):
                raise ValueError(f"z10 systemd environment does not bind {key}")
    return package, sidecar, package_sha, sidecar_sha


def _git_text(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _expected_identity(
    specification,
    profile: str,
    source_commit: str,
    *,
    exact_cache_template_sha256: str | None = None,
) -> dict:
    from src.io.input_validation import _jsonable
    from src.io.native_capacity_profile import native_profile_facts
    from src.io.resolved_config import resolved_config_sha256

    direct_route = _jsonable(
        native_profile_facts(profile)["campaign_authorization"]["direct_route"]
    )
    if profile in GATE_CD_PARALLEL32_PROFILES:
        if (
            not isinstance(exact_cache_template_sha256, str)
            or len(exact_cache_template_sha256) != 64
            or any(c not in "0123456789abcdef" for c in exact_cache_template_sha256)
        ):
            raise ValueError("Gate-CD M8N14 identity requires its reviewed cache-template SHA")
        direct_route["exact_cache_contract_template_sha256"] = (
            exact_cache_template_sha256
        )
    return {
        "profile_identity": profile,
        "run_id": specification.identity.get("run_id"),
        "input_path": str(Path(specification.source_path).resolve()),
        "input_sha256": specification.input_sha256,
        "physical_model_sha256": specification.physical_model_sha256,
        "resolved_config_sha256": resolved_config_sha256(specification),
        "resolved_output_parent_absolute": str(
            specification.expected_output_parent.resolve()
        ),
        "source_commit": source_commit,
        "direct_route_contract": direct_route,
    }


def _verify_prelaunch_output_parent(
    output_parent: Path, package: dict, expected_identity: dict
) -> dict:
    """Accept empty output or the exact hash-bound prior attempts only."""
    if not output_parent.exists():
        return {"status": "empty_or_not_yet_created", "residue": None}
    if not output_parent.is_dir() or output_parent.is_symlink():
        raise ValueError("formal output parent is not a regular directory")
    children = sorted(output_parent.iterdir(), key=lambda item: item.name)
    if not children:
        return {"status": "empty", "residue": None}

    allowlist = package.get("prelaunch_output_residue_allowlist")
    if not isinstance(allowlist, dict):
        raise TypeError("formal output parent is nonempty without an exact residue allowlist")
    required_files = {
        "input_original.dat",
        "input_sha256.txt",
        "physical_model_sha256.txt",
        "resolved_config.json",
        "run_manifest.json",
        "run_summary.json",
        "source_sha.txt",
    }
    legacy_single = "attempt_id" in allowlist
    if legacy_single:
        attempts = [allowlist]
    elif (
        allowlist.get("schema")
        == "task40.gate_cd.prelaunch_output_residue_allowlist.v2"
        and isinstance(allowlist.get("attempts"), list)
    ):
        attempts = allowlist["attempts"]
    else:
        raise ValueError("prelaunch residue allowlist schema is unsupported")
    if not attempts or not all(isinstance(item, dict) for item in attempts):
        raise ValueError("prelaunch residue allowlist has no exact attempt records")
    attempt_ids = [item.get("attempt_id") for item in attempts]
    if (
        not all(isinstance(name, str) and name for name in attempt_ids)
        or len(set(attempt_ids)) != len(attempt_ids)
        or {child.name for child in children} != set(attempt_ids)
        or any(child.is_symlink() or not child.is_dir() for child in children)
    ):
        raise ValueError("formal output parent contains an unapproved attempt directory")

    reviewed_attempts: list[dict] = []
    for record in attempts:
        attempt_id = record.get("attempt_id")
        expected_directory = record.get("attempt_directory")
        prior_source = record.get("prior_source_commit")
        classification = record.get("classification", "bootstrap_only_preworker")
        expected_files = record.get("files")
        expected_directories = record.get("directories", [])
        if (
            not isinstance(expected_directory, str)
            or not isinstance(prior_source, str)
            or len(prior_source) != 40
            or not isinstance(classification, str)
            or not isinstance(expected_files, dict)
            or not isinstance(expected_directories, list)
            or not all(isinstance(item, str) and item for item in expected_directories)
        ):
            raise ValueError("prelaunch residue attempt record is incomplete")
        attempt_dir = (output_parent / attempt_id).resolve()
        if (
            expected_directory != str(attempt_dir)
            or attempt_dir.parent != output_parent.resolve()
        ):
            raise ValueError("prelaunch residue attempt path differs from its allowlist")

        expected_file_names = set(expected_files)
        expected_dir_names = set(expected_directories)
        if len(expected_dir_names) != len(expected_directories):
            raise ValueError("prelaunch residue directory allowlist has duplicates")
        if any(
            Path(name).is_absolute()
            or ".." in Path(name).parts
            or Path(name).as_posix() != name
            for name in expected_file_names | expected_dir_names
        ):
            raise ValueError("prelaunch residue contains an unsafe relative path")
        actual_file_names: set[str] = set()
        actual_dir_names: set[str] = set()
        for item in attempt_dir.rglob("*"):
            if item.is_symlink():
                raise ValueError("prelaunch residue tree contains a symlink")
            relative = item.relative_to(attempt_dir).as_posix()
            if item.is_dir():
                actual_dir_names.add(relative)
            elif item.is_file():
                actual_file_names.add(relative)
            else:
                raise ValueError("prelaunch residue tree contains a special file")
        if (
            actual_file_names != expected_file_names
            or actual_dir_names != expected_dir_names
        ):
            raise ValueError("prelaunch attempt tree has missing, extra, or unlisted entries")
        for relative, expected_hash in expected_files.items():
            if (
                not isinstance(expected_hash, str)
                or len(expected_hash) != 64
                or sha256_file(attempt_dir / relative) != expected_hash
            ):
                raise ValueError(f"prelaunch attempt file hash changed: {relative}")

        if classification == "bootstrap_only_preworker":
            if expected_file_names != required_files or expected_dir_names:
                raise ValueError("bootstrap residue must be exactly seven root files")
        elif classification in {
            "worker_failed_gate_cd_mesh_setup",
            "worker_failed_gate_cd_raw_tensor_summary",
            "worker_failed_gate_cd_pre_lu_identity",
        }:
            required_setup_files = required_files | {
                "gate_cd_runtime_environment.json",
                "p6_condensed_direct_summary.json",
                "stages.jsonl",
                "workflow_phase.json",
                "workstation_isolation.json",
                "watchdog/resources.jsonl",
                "watchdog/summary.json",
                "watchdog/worker.log",
            }
            if (
                not required_setup_files.issubset(expected_file_names)
                or "numerical_output" not in expected_dir_names
                or "watchdog" not in expected_dir_names
                or any(name.startswith("numerical_output/") for name in expected_file_names)
            ):
                raise ValueError("setup-failure residue lacks exact terminal evidence")
            if classification == "worker_failed_gate_cd_raw_tensor_summary":
                exact_raw_tensor_files = required_files | {
                    "exact_cache_runtime_contract.json",
                    "gate_cd_runtime_environment.json",
                    "p6_condensed_direct_summary.json",
                    "stages.jsonl",
                    "task40_gate-cd_m8n64_finite_parent_parent_mode_manifest.json",
                    "task40_m8n64_active_mode_manifest.json",
                    "task40_m8n64_mode_index_map.json",
                    "workflow_phase.json",
                    "workstation_isolation.json",
                    "watchdog/resources.jsonl",
                    "watchdog/summary.json",
                    "watchdog/worker.log",
                }
                if (
                    expected_file_names != exact_raw_tensor_files
                    or expected_dir_names != {"numerical_output", "watchdog"}
                ):
                    raise ValueError(
                        "raw-tensor failure residue differs from its exact terminal tree"
                    )
            elif classification == "worker_failed_gate_cd_pre_lu_identity":
                exact_pre_lu_files = required_files | {
                    "exact_cache_runtime_contract.json",
                    "gate_cd_runtime_environment.json",
                    "p6_condensed_direct_summary.json",
                    "stages.jsonl",
                    "task40_gate-cd_m8n64_finite_parent_parent_mode_manifest.json",
                    "task40_m8n64_active_mode_manifest.json",
                    "task40_m8n64_mode_index_map.json",
                    "workflow_phase.json",
                    "workstation_isolation.json",
                    "watchdog/resources.jsonl",
                    "watchdog/summary.json",
                    "watchdog/worker.log",
                }
                if (
                    expected_file_names != exact_pre_lu_files
                    or expected_dir_names != {"numerical_output", "watchdog"}
                ):
                    raise ValueError(
                        "pre-LU identity-failure residue differs from its exact terminal tree"
                    )
                run_manifest = json.loads(
                    (attempt_dir / "run_manifest.json").read_text(encoding="utf-8")
                )
                run_summary = json.loads(
                    (attempt_dir / "run_summary.json").read_text(encoding="utf-8")
                )
                workflow = json.loads(
                    (attempt_dir / "workflow_phase.json").read_text(encoding="utf-8")
                )
                stage_rows = [
                    json.loads(line)
                    for line in (attempt_dir / "stages.jsonl")
                    .read_text(encoding="utf-8")
                    .splitlines()
                ]
                matrix_rows = [
                    row
                    for row in stage_rows
                    if row.get("stage") == "p6_direct_augmented_matrix_complete"
                ]
                rhs_rows = [
                    row for row in stage_rows if row.get("stage") == "p6_direct_rhs_ready"
                ]
                symbolic_rows = [
                    row
                    for row in stage_rows
                    if row.get("stage") == "p6_mumps_symbolic_complete"
                ]
                resource = run_summary.get("resource_authority")
                matrix_facts = matrix_rows[-1].get("facts", {}) if matrix_rows else {}
                if (
                    attempt_id != "20261104T152223.701221Z"
                    or run_manifest.get("source_sha") != prior_source
                    or run_manifest.get("run_id")
                    != "task40_gate_cd_fin0_sti_z10_m8n2_p6_direct_v1"
                    or run_manifest.get("native_capacity_profile_identity")
                    != "task40_gate_cd_fin0_sti_z10_m8n2_p6_direct_v1"
                    or run_summary.get("status") != "finished"
                    or run_summary.get("exit_status") != 4
                    or run_summary.get("result_classification") != "WORKER_FAILED"
                    or not isinstance(resource, dict)
                    or resource.get("descendants_cleared") is not True
                    or resource.get("remaining_child_pids") != []
                    or workflow.get("stage")
                    != "TASK40_GATE_CD_FIN0_STI_Z10_M8N2_P6_DIRECT_M8N64_FAILED"
                    or workflow.get("facts", {}).get("failed_stage")
                    != "p6_direct_rhs_ready"
                    or workflow.get("facts", {}).get("exception_type") != "ValueError"
                    or workflow.get("facts", {}).get("exception_message")
                    != "z10 pre-LU hook requires the exact resolved identity"
                    or not rhs_rows
                    or not matrix_rows
                    or symbolic_rows
                    or matrix_facts.get("shape") != [7_689_872, 7_689_872]
                    or int(matrix_facts.get("nz_used", -1)) != 6_450_459_962
                    or Path(str(run_summary.get("output_directory", ""))).resolve()
                    != attempt_dir
                ):
                    raise ValueError(
                        "pre-LU identity-failure residue does not match its exact failed run"
                    )
        elif classification == "worker_failed_gate_cd_signed_mode_selection":
            prior_service = record.get("prior_service")
            historical = _GATE_CD_SIGNED_SELECTION_RESIDUE
            live_capture_path = Path(
                prior_service.get("live_capture_path", "")
                if isinstance(prior_service, dict)
                else ""
            )
            start_receipt_path = Path(
                prior_service.get("start_receipt_path", "")
                if isinstance(prior_service, dict)
                else ""
            )
            live_capture_sha256 = (
                prior_service.get("live_capture_sha256")
                if isinstance(prior_service, dict)
                else None
            )
            start_receipt_sha256 = (
                prior_service.get("start_receipt_sha256")
                if isinstance(prior_service, dict)
                else None
            )
            if (
                attempt_id != historical["attempt_id"]
                or prior_source != historical["source_commit"]
                or not isinstance(prior_service, dict)
                or prior_service.get("unit") != historical["service_unit"]
                or prior_service.get("invocation_id") != historical["invocation_id"]
                or prior_service.get("observed_after_gc") is not True
                or prior_service.get("active_state_after_gc") != "inactive"
                or prior_service.get("sub_state_after_gc") != "dead"
                or prior_service.get("journal_main_exit_status")
                != historical["journal_main_exit_status"]
                or prior_service.get("journal_main_exit_text")
                != historical["journal_main_exit_text"]
                or prior_service.get("journal_unit_result")
                != historical["journal_unit_result"]
                or prior_service.get("worker_exit_status")
                != historical["worker_exit_status"]
                or prior_service.get("n_restarts") != 0
                or not live_capture_path.is_absolute()
                or not start_receipt_path.is_absolute()
                or not isinstance(live_capture_sha256, str)
                or len(live_capture_sha256) != 64
                or not isinstance(start_receipt_sha256, str)
                or len(start_receipt_sha256) != 64
                or sha256_file(live_capture_path) != live_capture_sha256
                or sha256_file(start_receipt_path) != start_receipt_sha256
            ):
                raise ValueError(
                    "signed-selection residue prior systemd identity differs from the exact failed run"
                )
            required_selection_files = required_files | {
                "exact_cache_runtime_contract.json",
                "gate_cd_runtime_environment.json",
                "p6_condensed_direct_summary.json",
                "stages.jsonl",
                "task40_gate-cd_m8n64_finite_parent_parent_mode_manifest.json",
                "task40_m8n64_active_mode_manifest.json",
                "task40_m8n64_mode_index_map.json",
                "workflow_phase.json",
                "workstation_isolation.json",
                "watchdog/resources.jsonl",
                "watchdog/summary.json",
                "watchdog/worker.log",
            }
            if (
                expected_file_names != required_selection_files
                or expected_dir_names != {"numerical_output", "watchdog"}
                or any(
                    name.startswith("numerical_output/")
                    for name in expected_file_names
                )
            ):
                raise ValueError(
                    "signed-selection failure residue must match its exact file/directory set"
                )
        else:
            raise ValueError("prelaunch residue classification is unsupported")

        manifest = _load_json(attempt_dir / "run_manifest.json")
        summary = _load_json(attempt_dir / "run_summary.json")
        resolved = _load_json(attempt_dir / "resolved_config.json")
        expected_values = {
            "run_id": expected_identity["run_id"],
            "input_sha256": expected_identity["input_sha256"],
            "physical_model_sha256": expected_identity["physical_model_sha256"],
            "resolved_config_sha256": expected_identity["resolved_config_sha256"],
        }
        for key, value in expected_values.items():
            if manifest.get(key) != value:
                raise ValueError(f"prelaunch residue identity differs for {key}")
        if summary.get("run_id") != expected_identity["run_id"]:
            raise ValueError("prelaunch summary run identity differs from the formal loader")
        if (
            manifest.get("source_sha") != prior_source
            or (attempt_dir / "source_sha.txt").read_text().strip() != prior_source
            or manifest.get("native_capacity_profile_identity")
            != expected_identity["profile_identity"]
            or manifest.get("output_directory") != str(attempt_dir)
            or manifest.get("input_path") != expected_identity["input_path"]
            or summary.get("output_directory") != str(attempt_dir)
        ):
            raise ValueError("prelaunch residue source/profile/output identity mismatch")
        if (
            (attempt_dir / "input_sha256.txt").read_text().strip()
            != expected_identity["input_sha256"]
            or sha256_file(attempt_dir / "input_original.dat")
            != expected_identity["input_sha256"]
            or (attempt_dir / "physical_model_sha256.txt").read_text().strip()
            != expected_identity["physical_model_sha256"]
            or sha256_file(attempt_dir / "resolved_config.json")
            != expected_identity["resolved_config_sha256"]
        ):
            raise ValueError("prelaunch identity sidecars differ from the formal loader")
        if (
            resolved.get("run_id") != expected_identity["run_id"]
            or resolved.get("solver", {}).get("native_capacity_profile")
            != expected_identity["profile_identity"]
            or resolved.get("provenance", {}).get("input_sha256")
            != expected_identity["input_sha256"]
            or resolved.get("provenance", {}).get("physical_model_sha256")
            != expected_identity["physical_model_sha256"]
        ):
            raise ValueError("prelaunch resolved configuration identity mismatch")
        resolved_parent = Path(
            resolved.get("provenance", {}).get("expected_output_parent", "")
        )
        if not resolved_parent.is_absolute():
            resolved_parent = (REPO_ROOT / resolved_parent).resolve()
        if str(resolved_parent) != expected_identity["resolved_output_parent_absolute"]:
            raise ValueError("prelaunch resolved output-parent identity mismatch")

        if classification == "bootstrap_only_preworker":
            if (
                summary.get("status") != "launching"
                or summary.get("result_classification") != "not_run"
                or summary.get("exit_status") is not None
                or summary.get("resource_authority", {}).get("status") != "not_sampled"
            ):
                raise ValueError("bootstrap residue is not the recorded non-FE launcher failure")
        elif classification == "worker_failed_gate_cd_mesh_setup":
            workflow = _load_json(attempt_dir / "workflow_phase.json")
            direct_summary = _load_json(
                attempt_dir / "p6_condensed_direct_summary.json"
            )
            authority = summary.get("resource_authority", {})
            if (
                summary.get("status") != "finished"
                or summary.get("exit_status") != 4
                or summary.get("result_classification") != "WORKER_FAILED"
                or authority.get("classification") != "WORKER_FAILED"
                or authority.get("descendants_cleared") is not True
                or authority.get("remaining_child_pids") != []
                or workflow.get("phase") != "setup"
                or workflow.get("facts", {}).get("failed_stage")
                != "p6_direct_mesh_setup_started"
                or workflow.get("facts", {}).get("exception_type") != "ValueError"
                or workflow.get("facts", {}).get("exception_message")
                != "invalid frozen mesh input: R13 input does not identify the frozen mesh plan"
                or direct_summary.get("status") != "FAILED"
                or direct_summary.get("run_id") != expected_identity["run_id"]
                or direct_summary.get("profile") != expected_identity["profile_identity"]
                or direct_summary.get("source_sha") != prior_source
                or direct_summary.get("failed_stage") != "p6_direct_mesh_setup_started"
                or direct_summary.get("outer_ksp") != "NOT_BUILT"
                or direct_summary.get("p4_factor") != "NOT_BUILT"
                or direct_summary.get("p4_operator") != "NOT_BUILT"
            ):
                raise ValueError("mesh-setup residue is not the exact cleared pre-matrix failure")
        elif classification == "worker_failed_gate_cd_raw_tensor_summary":
            workflow = _load_json(attempt_dir / "workflow_phase.json")
            direct_summary = _load_json(
                attempt_dir / "p6_condensed_direct_summary.json"
            )
            watchdog = _load_json(attempt_dir / "watchdog/summary.json")
            authority = summary.get("resource_authority", {})
            facts = workflow.get("facts", {})
            cache = direct_summary.get("exact_cache_execution", {}).get("raw", {})
            cache_evidence = record.get("raw_tensor_cache_evidence", {})
            cache_root = Path(cache_evidence.get("root", ""))
            complete_markers = (
                list(cache_root.rglob("complete.json"))
                if cache_root.is_dir() and not cache_root.is_symlink()
                else []
            )
            tensor_payloads = (
                list(cache_root.rglob("tensor.npy"))
                if cache_root.is_dir() and not cache_root.is_symlink()
                else []
            )
            stages = [
                json.loads(line)
                for line in (attempt_dir / "stages.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            progress = [
                item.get("facts", {})
                for item in stages
                if item.get("stage") == "p6_direct_raw_tensor_class_progress"
            ]
            pool_release = stages[-2] if len(stages) >= 2 else {}
            terminal = stages[-1] if stages else {}
            expected_failure = (
                "global raw tensor evaluation failed before broadcast: rank 0: "
                "OSError: [Errno 24] Too many open files"
            )
            if (
                summary.get("status") != "finished"
                or summary.get("exit_status") != 4
                or summary.get("result_classification") != "WORKER_FAILED"
                or authority.get("classification") != "WORKER_FAILED"
                or authority.get("leader_exit_code") != 4
                or authority.get("descendants_cleared") is not True
                or authority.get("remaining_child_pids") != []
                or watchdog.get("classification") != "WORKER_FAILED"
                or watchdog.get("leader_exit_code") != 4
                or watchdog.get("descendants_cleared") is not True
                or watchdog.get("remaining_child_pids") != []
                or workflow.get("phase") != "setup"
                or facts.get("failed_stage") != "p6_direct_raw_tensor_pool_lock"
                or facts.get("exception_type") != "RuntimeError"
                or facts.get("exception_message") != expected_failure
                or direct_summary.get("status") != "FAILED"
                or direct_summary.get("failed_phase") != "setup"
                or direct_summary.get("failed_stage")
                != "p6_direct_raw_tensor_pool_lock"
                or direct_summary.get("exception_type") != "RuntimeError"
                or direct_summary.get("exception_message") != expected_failure
                or direct_summary.get("run_id") != expected_identity["run_id"]
                or direct_summary.get("profile") != expected_identity["profile_identity"]
                or direct_summary.get("source_sha") != prior_source
                or direct_summary.get("outer_ksp") != "NOT_BUILT"
                or direct_summary.get("p4_factor") != "NOT_BUILT"
                or direct_summary.get("p4_operator") != "NOT_BUILT"
                or direct_summary.get("full_dtn_status") != "FULL_DTN_NOT_VERIFIED"
                or not cache_root.is_absolute()
                or cache.get("root") != str(cache_root.resolve())
                or len(complete_markers)
                != cache_evidence.get("complete_marker_count")
                or len(tensor_payloads) != cache_evidence.get("tensor_payload_count")
                or sum(path.stat().st_size for path in tensor_payloads)
                != cache_evidence.get("tensor_payload_bytes")
                or not progress
                or max(int(item.get("done", -1)) for item in progress)
                != cache_evidence.get("complete_marker_count")
                or max(int(item.get("total", -1)) for item in progress)
                != cache_evidence.get("complete_marker_count")
                or pool_release.get("stage") != "p6_direct_raw_tensor_pool_lock"
                or pool_release.get("facts", {}).get("event_type")
                != "raw_tensor_pool_lock_released"
                or pool_release.get("facts", {}).get("batch_completed") is not True
                or pool_release.get("facts", {}).get("batch_classes")
                != cache_evidence.get("complete_marker_count")
                or terminal.get("stage")
                != "TASK40_GATE_CD_FIN0_STI_Z10_M8N2_P6_DIRECT_M8N64_FAILED"
                or terminal.get("facts", {}).get("failed_stage")
                != "p6_direct_raw_tensor_pool_lock"
                or terminal.get("facts", {}).get("exception_message")
                != expected_failure
            ):
                raise ValueError(
                    "raw-tensor residue is not the exact cleared post-cache EMFILE failure"
                )
        else:
            workflow = _load_json(attempt_dir / "workflow_phase.json")
            direct_summary = _load_json(
                attempt_dir / "p6_condensed_direct_summary.json"
            )
            watchdog = _load_json(attempt_dir / "watchdog/summary.json")
            authority = summary.get("resource_authority", {})
            facts = workflow.get("facts", {})
            mesh = direct_summary.get("mesh_evidence", {})
            mode_inventory = direct_summary.get("mode_inventory", {})
            service = record.get("prior_service")
            stages = [
                json.loads(line)
                for line in (attempt_dir / "stages.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
                if line.strip()
            ]
            stage_names = [item.get("stage") for item in stages]
            expected_stages = [
                "workflow_started",
                "p6_direct_resolved_profile_bound",
                "p6_direct_mesh_setup_started",
                "p6_direct_actual_mesh_qa_complete",
                "p6_direct_gate_cd_finite_mode_identity_complete",
                "p6_direct_mode_inventory_complete",
                "physical_mode_inventory_reused",
                "TASK40_GATE_CD_M8N14_P6_DIRECT_M8N64_FAILED",
            ]
            expected_failure = "operator selection policy is unsupported"
            if (
                not isinstance(service, dict)
                or not isinstance(service.get("unit"), str)
                or not service.get("unit", "").endswith(".service")
                or not isinstance(service.get("invocation_id"), str)
                or len(service.get("invocation_id", "")) != 32
                or any(
                    character not in "0123456789abcdef"
                    for character in service.get("invocation_id", "")
                )
                or service.get("observed_after_gc") is not True
                or service.get("active_state_after_gc") != "inactive"
                or service.get("sub_state_after_gc") != "dead"
                or service.get("journal_main_exit_status") != 3
                or service.get("journal_main_exit_text") != "3/NOTIMPLEMENTED"
                or service.get("journal_unit_result") != "exit-code"
                or service.get("worker_exit_status") != 4
                or service.get("n_restarts") != 0
                or manifest.get("status") != "finished"
                or manifest.get("exit_status") != 4
                or manifest.get("result_classification") != "WORKER_FAILED"
                or summary.get("status") != "finished"
                or summary.get("exit_status") != 4
                or summary.get("result_classification") != "WORKER_FAILED"
                or authority.get("classification") != "WORKER_FAILED"
                or authority.get("descendants_cleared") is not True
                or authority.get("remaining_child_pids") != []
                or watchdog.get("classification") != "WORKER_FAILED"
                or watchdog.get("descendants_cleared") is not True
                or watchdog.get("remaining_child_pids") != []
                or workflow.get("phase") != "setup"
                or facts.get("failed_stage") != "physical_mode_inventory_reused"
                or facts.get("exception_type") != "ValueError"
                or facts.get("exception_message") != expected_failure
                or direct_summary.get("status") != "FAILED"
                or direct_summary.get("result_classification")
                != "TASK40_GATE_CD_M8N14_P6_DIRECT_M8N64_FAILED"
                or direct_summary.get("run_id") != expected_identity["run_id"]
                or direct_summary.get("profile")
                != expected_identity["profile_identity"]
                or direct_summary.get("source_sha") != prior_source
                or direct_summary.get("failed_stage")
                != "physical_mode_inventory_reused"
                or direct_summary.get("failed_phase") != "setup"
                or direct_summary.get("exception_type") != "ValueError"
                or direct_summary.get("exception_message") != expected_failure
                or direct_summary.get("full_dtn_status")
                != "FULL_DTN_NOT_VERIFIED"
                or mode_inventory.get("active_mode_count") != 1088
                or mode_inventory.get("active_mode_sha256")
                != "333e201cd5bd368a6f1a70a02949ff3099fdb2c8f6c05e93fc419a77430be353"
                or mesh.get("status") != "PASS"
                or mesh.get("scope") != "LIVE_MAPPED_MESH_AND_P6_SPACE_NO_MATRIX_OR_FACTOR"
                or mesh.get("global_matrix_built") is not False
                or mesh.get("factor_built") is not False
                or direct_summary.get("outer_ksp") != "NOT_BUILT"
                or direct_summary.get("p4_factor") != "NOT_BUILT"
                or direct_summary.get("p4_operator") != "NOT_BUILT"
                or stage_names != expected_stages
                or stages[3].get("facts", {}).get("status") != "PASS"
                or stages[5].get("facts", {}).get("active_mode_count") != 1088
                or stages[5].get("facts", {}).get("active_mode_sha256")
                != mode_inventory.get("active_mode_sha256")
                or stages[6].get("facts", {}).get("mode_count") != 1088
                or stages[6].get("facts", {}).get("mode_sha256")
                != mode_inventory.get("active_mode_sha256")
                or stages[7].get("facts", {}).get("failed_stage")
                != "physical_mode_inventory_reused"
                or stages[7].get("facts", {}).get("exception_type")
                != "ValueError"
                or stages[7].get("facts", {}).get("exception_message")
                != expected_failure
            ):
                raise ValueError(
                    "signed-selection residue is not the exact cleared pre-carrier failure"
                )

        reviewed_attempts.append(
            {
                "attempt_id": attempt_id,
                "attempt_directory": str(attempt_dir),
                "prior_source_commit": prior_source,
                "classification": classification,
                "files": expected_files,
                "directories": sorted(expected_dir_names),
                "prior_service": record.get("prior_service"),
                "raw_tensor_cache_evidence": record.get("raw_tensor_cache_evidence"),
            }
        )
    if legacy_single:
        record = reviewed_attempts[0]
        return {
            "status": "accepted_exact_prelaunch_bootstrap_only",
            "attempt_id": record["attempt_id"],
            "attempt_directory": record["attempt_directory"],
            "prior_source_commit": record["prior_source_commit"],
            "files": record["files"],
        }
    return {
        "status": "accepted_exact_prelaunch_residue_set",
        "residues": reviewed_attempts,
    }


def fresh_acceptance(
    package_path: str | Path, sidecar_path: str | Path, output_path: str | Path
) -> dict:
    package, sidecar, package_sha, sidecar_sha = validate_package_sidecar(
        package_path, sidecar_path
    )
    root = REPO_ROOT.resolve()
    if Path.cwd().resolve() != root:
        raise ValueError("fresh check must run from the exact repository root")
    source_commit = _git_text(root, "rev-parse", "HEAD")
    if source_commit != package.get("source_commit"):
        raise ValueError("source HEAD differs from the frozen package")
    if _git_text(root, "status", "--porcelain"):
        raise ValueError("source worktree is not clean")
    for rel, expected in package.get("source_file_sha256", {}).items():
        if sha256_file(root / rel) != expected:
            raise ValueError(f"bound source file changed: {rel}")
    from src.io import load_and_resolve
    from src.io.native_capacity_profile import (
        native_capacity_profile_identity,
        native_profile_facts,
    )
    from src.runners.native_capacity import native_capacity_guard
    from src.runners.task40_gate_cd_formal_admission import (
        GATE_CD_LOCK_DIRECTORY_ENV,
        GATE_CD_SCOPE_PATH_ENV,
        GATE_CD_SCOPE_SHA_ENV,
        GATE_CD_SUBMISSION_MODE_ENV,
    )

    dat_path = Path(package["input_path"]).resolve()
    if sha256_file(dat_path) != package.get("input_sha256"):
        raise ValueError("input bytes differ from the frozen package")
    specification = load_and_resolve(dat_path)
    profile = native_capacity_profile_identity(
        specification.method.get("kind"), specification.solver
    )
    if profile not in GATE_CD_FORMAL_PROFILES or profile != package.get("profile_identity"):
        raise ValueError("resolved input is not the exact Gate-CD formal profile")
    facts = native_profile_facts(profile)
    readiness = facts.get("component_options", {}).get("route_readiness", {})
    if readiness.get("launchable") is not True:
        raise ValueError("live profile readiness is still fail-closed")
    _validate_live_profile_contract(package, facts)
    exact_cache_template_sha256 = (
        sidecar.get("exact_cache_template_sha256")
        if profile in GATE_CD_PARALLEL32_PROFILES
        else None
    )
    actual = _expected_identity(
        specification,
        profile,
        source_commit,
        exact_cache_template_sha256=exact_cache_template_sha256,
    )
    if actual != package.get("identity"):
        raise ValueError("actual standard-loader identity differs from the package")
    if actual["physical_model_sha256"] != package.get("physical_model_sha256"):
        raise ValueError("physical-model hash differs from the package")
    output_parent = Path(sidecar["expected_output_parent"]).resolve()
    if str(output_parent) != actual["resolved_output_parent_absolute"]:
        raise ValueError("sidecar output parent differs from the formal loader")
    residue = _verify_prelaunch_output_parent(output_parent, package, actual)
    if profile == GATE_CD_FIN0_STI_Z10_M8N2_PROFILE:
        for key in ("ready_path", "release_path", "accepted_path"):
            if Path(sidecar["pre_lu_pause"][key]).exists():
                raise ValueError(
                    "z10 pre-LU attempt evidence already exists; prepare a fresh attempt"
                )
    _require_systemd_unit_not_loaded(str(sidecar["service_unit"]))
    scope_path = Path(sidecar["scope_path"]).resolve()
    old_env = {
        key: os.environ.get(key)
        for key in (
            GATE_CD_SCOPE_PATH_ENV,
            GATE_CD_SCOPE_SHA_ENV,
            GATE_CD_LOCK_DIRECTORY_ENV,
            GATE_CD_SUBMISSION_MODE_ENV,
        )
    }
    os.environ[GATE_CD_SCOPE_PATH_ENV] = str(scope_path)
    os.environ[GATE_CD_SCOPE_SHA_ENV] = str(sidecar["scope_sha256"])
    os.environ[GATE_CD_LOCK_DIRECTORY_ENV] = str(sidecar["lock_directory"])
    os.environ[GATE_CD_SUBMISSION_MODE_ENV] = "fresh_check"
    try:
        with native_capacity_guard(
            profile,
            memory_policy=specification.execution.get(
                "native_memory_policy", "none"
            ),
            task_run_id=specification.identity.get("run_id"),
            submission_mode="fresh_check",
            expected_identity=actual,
        ) as (_root, isolation):
            result = {
                "schema": "task40.gate_cd.formal_fresh_receipt.v1",
                "captured_utc": datetime.now(timezone.utc).isoformat(),
                "fresh_pass": True,
                "launch_not_started": True,
                "package_sha256": package_sha,
                "sidecar_sha256": sidecar_sha,
                "source_commit": source_commit,
                "input_sha256": actual["input_sha256"],
                "physical_model_sha256": actual["physical_model_sha256"],
                "resolved_config_sha256": actual["resolved_config_sha256"],
                "run_id": actual["run_id"],
                "profile_identity": profile,
                "host_and_lease_facts": isolation,
                "no_FE_or_factor_started": True,
                "prelaunch_output_parent_review": residue,
            }
    finally:
        for key, value in old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
    _atomic_json(output_path, result)
    return result


def _validate_systemd_argv(sidecar: dict) -> list[str]:
    argv = sidecar.get("systemd_run_argv")
    unit = sidecar.get("service_unit")
    if not isinstance(argv, list) or not all(isinstance(x, str) for x in argv):
        raise ValueError("sidecar systemd_run_argv must be an exact string array")
    if not isinstance(unit, str) or not unit.endswith(".service"):
        raise ValueError("sidecar service unit is invalid")
    if argv[:3] != ["systemd-run", "--user", "--no-block"]:
        raise ValueError("only the reviewed one-shot user-systemd mode is accepted")
    if not any(x in argv for x in (f"--unit={unit}",)) and not (
        "--unit" in argv and argv[argv.index("--unit") + 1 : argv.index("--unit") + 2] == [unit]
    ):
        raise ValueError("systemd argv does not bind the unique service unit")
    for key, value in _SERVICE_PROPERTIES.items():
        if f"--property={key}={value}" not in argv:
            raise ValueError(f"systemd service property differs: {key}")
    if "--property=LimitNOFILE=65536:1048576" not in argv:
        raise ValueError("systemd service must bind the reviewed LimitNOFILE=65536:1048576")
    if len(argv) < 3 or argv[-3:-1] != ["/bin/bash", "-lc"]:
        raise ValueError("systemd argv must end in the reviewed bash -lc command")
    argv_shell_command = argv[-1]
    declared_shell_command = sidecar.get("shell_command")
    activation_script = sidecar.get("activation_script")
    shell_command = sidecar.get("shell_command")
    if declared_shell_command != argv_shell_command:
        raise ValueError("sidecar shell_command differs from the actual systemd argv")
    if "scripts/run_case.py" not in argv_shell_command:
        raise ValueError("service must call the standard run_case entry")
    if "src.runners.task038_input_worker" in argv_shell_command:
        raise ValueError("sidecar cannot bypass run_case and invoke the worker directly")
    output = sidecar.get("append_log_path")
    if not isinstance(output, str) or not Path(output).is_absolute():
        raise ValueError("systemd append log path must be absolute")
    if f"--property=StandardOutput=append:{output}" not in argv:
        raise ValueError("stdout must append to the reviewed persistent log")
    if f"--property=StandardError=append:{output}" not in argv:
        raise ValueError("stderr must append to the reviewed persistent log")
    environment = sidecar.get("service_environment")
    if not isinstance(environment, dict):
        raise TypeError("sidecar service_environment must be explicit")
    required_env = {
        "HWLOC_COMPONENTS": "-x86",
        "TASK40_GATE_CD_SCOPE_PATH": sidecar.get("scope_path"),
        "TASK40_GATE_CD_SCOPE_SHA256": sidecar.get("scope_sha256"),
        "TASK40_GATE_CD_LOCK_DIRECTORY": sidecar.get("lock_directory"),
        "TASK40_GATE_CD_SUBMISSION_MODE": "runtime",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "BLIS_NUM_THREADS": "1",
        "NUMEXPR_NUM_THREADS": "1",
    }
    for key, expected in required_env.items():
        if not isinstance(expected, str) or environment.get(key) != expected:
            raise ValueError(f"sidecar launch environment differs for {key}")
        if f"--setenv={key}={expected}" not in argv:
            raise ValueError(f"systemd argv does not pass exact environment {key}")
    if sidecar.get("profile_identity") == GATE_CD_FIN0_STI_Z10_M8N2_PROFILE:
        from src.runners.task40_gate_cd_prelu_pause import (
            PRELU_ENVIRONMENT_FIELDS,
        )

        pause = sidecar.get("pre_lu_pause")
        if not isinstance(pause, dict):
            raise ValueError("z10 sidecar lacks its pre-LU pause environment")
        pause_environment = {
            env_name: pause.get(field)
            for field, env_name in PRELU_ENVIRONMENT_FIELDS.items()
        }
        for key, expected in pause_environment.items():
            if (
                not isinstance(expected, str)
                or not expected
                or environment.get(key) != expected
                or f"--setenv={key}={expected}" not in argv
            ):
                raise ValueError(f"z10 pre-LU environment differs for {key}")
        reuse = sidecar.get("verified_cache_reuse")
        if not isinstance(reuse, dict):
            raise ValueError("z10 sidecar lacks its verified-cache reuse environment")
        for key, expected in (
            ("TASK40_EXACT_CACHE_REUSE_MODE", reuse.get("mode")),
            ("TASK40_EXACT_CACHE_REUSE_CONTRACT", reuse.get("contract_path")),
            ("TASK40_EXACT_CACHE_REUSE_CONTRACT_SHA256", reuse.get("contract_sha256")),
        ):
            if (
                not isinstance(expected, str)
                or environment.get(key) != expected
                or f"--setenv={key}={expected}" not in argv
            ):
                raise ValueError(f"z10 cache-reuse launch environment differs for {key}")
        if (
            "TASK40_EXACT_CACHE_REUSE_HOOK_ACTIVE" in environment
            or any(
                value.startswith("--setenv=TASK40_EXACT_CACHE_REUSE_HOOK_ACTIVE=")
                for value in argv
            )
        ):
            raise ValueError("cache hook active marker must be created by Python startup")
    if sidecar.get("profile_identity") in GATE_CD_PARALLEL32_PROFILES:
        scope_path = Path(sidecar.get("scope_path", "")).resolve(strict=True)
        scope = _load_json(scope_path)
        exact_env = {
            "TASK40_GATE_CD_ATTEMPT_CACHE_ROOT": sidecar.get("attempt_cache_root"),
            "TASK40_EXACT_CACHE_TEMPLATE_PATH": sidecar.get(
                "exact_cache_template_path"
            ),
            "TASK40_EXACT_CACHE_TEMPLATE_SHA256": sidecar.get(
                "exact_cache_template_sha256"
            ),
        }
        if (
            scope.get("runtime_paths", {}).get("attempt_cache_root")
            != exact_env["TASK40_GATE_CD_ATTEMPT_CACHE_ROOT"]
        ):
            raise ValueError("sidecar attempt cache root differs from its exact scope")
        for key, expected in exact_env.items():
            if (
                not isinstance(expected, str)
                or environment.get(key) != expected
                or f"--setenv={key}={expected}" not in argv
            ):
                raise ValueError(f"sidecar exact-cache launch environment differs for {key}")
    if sidecar.get("profile_identity") == GATE_CD_FIN0_STI_Z10_M8N2_PROFILE:
        reuse = sidecar.get("verified_cache_reuse")
        if not isinstance(reuse, dict):
            raise ValueError("z10 sidecar lacks its verified-cache hook directory")
        hook_directory = reuse.get("hook_directory")
        if (
            not isinstance(hook_directory, str)
            or not Path(hook_directory).is_absolute()
            or "ulimit -Sn 65536" not in argv_shell_command
            or 'test "$(ulimit -Sn)" = 65536' not in argv_shell_command
            or f"export PYTHONPATH={hook_directory}:$PYTHONPATH" not in argv_shell_command
            or "python -c" not in argv_shell_command
            or "TASK40_EXACT_CACHE_REUSE_HOOK_ACTIVE" not in argv_shell_command
            or "python -S" in argv_shell_command
            or "python -I" in argv_shell_command
        ):
            raise ValueError("z10 shell must set NOFILE and prove the cache guard is active")
        ordered_shell_markers = (
            activation_script,
            "ulimit -Sn 65536",
            'test "$(ulimit -Sn)" = 65536',
            f"export PYTHONPATH={hook_directory}:$PYTHONPATH",
            "python -c",
            "exec python scripts/run_case.py",
        )
        if [argv_shell_command.index(marker) for marker in ordered_shell_markers] != sorted(
            argv_shell_command.index(marker) for marker in ordered_shell_markers
        ):
            raise ValueError("z10 launch shell ordering differs from the reviewed cache/NOFILE gate")
    activation_env = (
        "_MYFENICS_NATIVE_QUALIFIED_ACTIVATION",
        "TASK39EXTRA_INT64_ACTIVATION",
        "TASK39EXTRA_PORD64_ACTIVATION",
    )
    for key in activation_env:
        if environment.get(key) != "1" or f"--setenv={key}=1" not in argv:
            raise ValueError(f"systemd argv lacks qualified activation marker {key}")
    if not isinstance(activation_script, str) or not Path(activation_script).is_absolute():
        raise ValueError("qualified activation script path must be absolute")
    if not isinstance(shell_command, str) or activation_script not in argv_shell_command:
        raise ValueError("service shell must source the exact qualified activation script")
    if "exec python scripts/run_case.py" not in argv_shell_command:
        raise ValueError("service shell must exec the standard run_case entry")
    return argv


def _service_properties(unit: str) -> dict[str, str]:
    names = (
        "LoadState", "ActiveState", "SubState", "MainPID", "InvocationID",
        "ControlGroup", "Result", "ExecMainCode", "ExecMainStatus", "ExecStart",
    )
    result = subprocess.run(
        ["systemctl", "--user", "show", unit, *[f"--property={x}" for x in names]],
        capture_output=True,
        text=True,
        check=True,
    )
    return dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )


def _process_identity(pid: int) -> dict | None:
    proc = Path("/proc") / str(pid)
    try:
        fields = (proc / "stat").read_text().rsplit(")", 1)[1].split()
        status = (proc / "status").read_text()
        limits = (proc / "limits").read_text()
        argv = [
            x.decode(errors="replace")
            for x in (proc / "cmdline").read_bytes().split(b"\0")
            if x
        ]
        env = {}
        for item in (proc / "environ").read_bytes().split(b"\0"):
            if b"=" not in item:
                continue
            raw_key, raw_value = item.split(b"=", 1)
            key = raw_key.decode(errors="replace")
            if key in _CAPTURE_ENV:
                env[key] = raw_value.decode(errors="replace")
        allowed = next(
            (
                x.split(":", 1)[1].strip()
                for x in status.splitlines()
                if x.startswith("Cpus_allowed_list:")
            ),
            None,
        )
        max_open_files = next(
            (
                line.split()[-3:-1]
                for line in limits.splitlines()
                if line.startswith("Max open files")
            ),
            None,
        )
        if max_open_files is None or len(max_open_files) != 2:
            raise ValueError("process has no readable Max open files limit")
        cgroup = (proc / "cgroup").read_text()
        cg_path = next(
            (x.split(":", 2)[2] for x in cgroup.splitlines() if x.count(":") >= 2),
            None,
        )
        petsc = []
        with (proc / "maps").open() as stream:
            for line in stream:
                if "libpetsc" in line and "/" in line:
                    value = line.split()[-1]
                    if value not in petsc:
                        petsc.append(value)
        numa = {"lines": 0, "interleave_0_1_vmas": 0, "default_vmas": 0}
        with (proc / "numa_maps").open() as stream:
            for line in stream:
                numa["lines"] += 1
                tokens = line.split()
                numa["interleave_0_1_vmas"] += int(
                    "interleave:0-1" in tokens
                )
                numa["default_vmas"] += int("default" in tokens)
        threads = []
        task_dir = proc / "task"
        for tid_path in sorted(
            (p for p in task_dir.iterdir() if p.name.isdigit()),
            key=lambda p: int(p.name),
        ):
            tid = int(tid_path.name)
            try:
                task_stat = (tid_path / "stat").read_text().rsplit(")", 1)[1].split()
                task_status = (tid_path / "status").read_text()
                thread_cpus = next(
                    (
                        row.split(":", 1)[1].strip()
                        for row in task_status.splitlines()
                        if row.startswith("Cpus_allowed_list:")
                    ),
                    None,
                )
                threads.append(
                    {
                        "tid": tid,
                        "start_ticks": int(task_stat[19]),
                        "state": task_stat[0],
                        "cpus_allowed_list": thread_cpus,
                    }
                )
            except (OSError, ValueError, IndexError):
                continue
        return {
            "pid": pid,
            "start_ticks": int(fields[19]),
            "state": fields[0],
            "ppid": int(fields[1]),
            "argv": argv,
            "cwd": os.readlink(proc / "cwd"),
            "cpus_allowed_list": allowed,
            "max_open_files_soft": int(max_open_files[0]),
            "max_open_files_hard": int(max_open_files[1]),
            "cgroup": cgroup,
            "cgroup_path": cg_path,
            "environment": env,
            "threads": threads,
            "numa_maps_summary": numa,
            "libpetsc_mappings": petsc,
        }
    except (OSError, ValueError, IndexError):
        return None


def capture_unit(unit: str) -> dict:
    props = _service_properties(unit)
    mainpid = int(props.get("MainPID", "0") or 0)
    cgroup = props.get("ControlGroup", "")
    cg_procs = Path("/sys/fs/cgroup") / cgroup.lstrip("/") / "cgroup.procs"
    pids = [int(x) for x in cg_procs.read_text().split()] if cgroup else []
    identities = [
        identity
        for pid in pids
        if (identity := _process_identity(pid)) is not None
    ]
    roles = {"root": [], "mpi": [], "worker": []}
    for identity in identities:
        argv = identity["argv"]
        if any(x.endswith("scripts/run_case.py") for x in argv):
            roles["root"].append(identity)
        elif any(Path(x).name in {"mpiexec", "mpirun", "orted"} for x in argv):
            roles["mpi"].append(identity)
        elif "-m" in argv and "src.runners.task038_input_worker" in argv:
            roles["worker"].append(identity)
    return {
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "unit": unit,
        "unit_properties": props,
        "main_pid_identity": _process_identity(mainpid) if mainpid else None,
        "control_group_processes": identities,
        "roles": roles,
    }


def _parse_cpu_list(value: str) -> set[int]:
    cpus: set[int] = set()
    for field in value.split(","):
        bounds = field.split("-", 1)
        if not all(part.isdecimal() for part in bounds):
            raise ValueError(f"invalid Linux CPU list: {value!r}")
        start = int(bounds[0])
        end = int(bounds[-1])
        if end < start:
            raise ValueError(f"invalid Linux CPU range: {value!r}")
        cpus.update(range(start, end + 1))
    return cpus


def _require_live_capture(
    capture: dict,
    repo_root: Path,
    expected_worker_cpus: list[int],
    math_threads: int,
    *,
    package: dict | None = None,
) -> None:
    props = capture["unit_properties"]
    root = capture["roles"]["root"]
    mpi = capture["roles"]["mpi"]
    workers = capture["roles"]["worker"]
    mainpid = int(props.get("MainPID", "0") or 0)
    if not props.get("InvocationID") or not props.get("ControlGroup"):
        raise ValueError("submitted service has no InvocationID/cgroup identity")
    if len(root) != 1 or root[0]["pid"] != mainpid or not mpi or len(workers) != 1:
        raise ValueError("service cgroup does not contain one exact root, MPI, and worker")
    if root[0]["cwd"] != str(repo_root.resolve()):
        raise ValueError("run_case root cwd differs from the frozen worktree")
    mpi_pids = {int(item["pid"]) for item in mpi}
    if root[0]["ppid"] != int(capture["main_pid_identity"]["ppid"]):
        raise ValueError("run_case parent identity differs from the captured systemd MainPID")
    if not any(item["ppid"] == mainpid for item in mpi):
        raise ValueError("MPI launcher is not a child of the run_case root")
    if not any(item["ppid"] in mpi_pids for item in workers):
        raise ValueError("worker is not a child of the observed MPI launcher")
    worker = workers[0]
    if (
        worker.get("max_open_files_soft") != 65536
        or not isinstance(worker.get("max_open_files_hard"), int)
        or worker["max_open_files_hard"] < worker["max_open_files_soft"]
    ):
        raise ValueError(
            "worker Max open files limit differs from the reviewed 65536 soft floor"
        )
    if (
        package is not None
        and package.get("profile_identity") == GATE_CD_FIN0_STI_Z10_M8N2_PROFILE
    ):
        reuse = package.get("verified_cache_reuse", {})
        environment = worker["environment"]
        expected_values = {
            "TASK40_EXACT_CACHE_REUSE_MODE": reuse.get("mode"),
            "TASK40_EXACT_CACHE_REUSE_CONTRACT": reuse.get("contract_path"),
            "TASK40_EXACT_CACHE_REUSE_CONTRACT_SHA256": reuse.get("contract_sha256"),
            "TASK40_EXACT_CACHE_REUSE_HOOK_ACTIVE": "1",
            "TASK40_GATE_CD_ATTEMPT_CACHE_ROOT": reuse.get("target_attempt_cache_root"),
        }
        if any(environment.get(key) != value for key, value in expected_values.items()):
            raise ValueError("live worker cache-only guard environment differs from the package")
        hook_directory = reuse.get("hook_directory")
        if (
            not isinstance(hook_directory, str)
            or not environment.get("PYTHONPATH", "").startswith(hook_directory + ":")
            or any(value in worker["argv"] for value in ("-S", "-I"))
        ):
            raise ValueError("live worker could bypass sitecustomize cache guard startup")
        reuse_root = Path(reuse.get("target_attempt_cache_root", ""))
        audit_path = reuse_root / "verified_cache_reuse.jsonl"
        try:
            audit = [json.loads(line) for line in audit_path.read_text().splitlines() if line]
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("live worker cache-reuse startup audit is missing or malformed") from exc
        if not any(
            item.get("event") == "python_startup_guard_installed"
            and item.get("pid") == worker.get("pid")
            and item.get("contract_sha256") == reuse.get("contract_sha256")
            for item in audit
        ):
            raise ValueError("live worker PID has no cache-only sitecustomize startup attestation")
    expected_cpu_set = set(expected_worker_cpus)
    if (
        len(expected_cpu_set) != len(expected_worker_cpus)
        or _parse_cpu_list(worker["cpus_allowed_list"]) != expected_cpu_set
    ):
        raise ValueError("worker CPU affinity differs from committed runtime CPU lease")
    if not worker["threads"] or any(
        _parse_cpu_list(row["cpus_allowed_list"]) != expected_cpu_set
        for row in worker["threads"]
    ):
        raise ValueError("worker thread CPU affinity differs from committed runtime lease")
    if len(worker["threads"]) < math_threads:
        raise ValueError("worker has fewer threads than its math-thread contract")
    if not any("pord64-overlay" in p for p in worker["libpetsc_mappings"]):
        raise ValueError("worker has not mapped the qualified PORD64 PETSc")
    if worker["numa_maps_summary"]["interleave_0_1_vmas"] < 1:
        raise ValueError("worker NUMA interleave:0-1 has not been observed")
    if worker["environment"].get("OMP_NUM_THREADS") != "1":
        raise ValueError("worker math-thread contract has not been read back")
    if any(worker["environment"].get(name) != "1" for name in _MATH_THREAD_ENV):
        raise ValueError("worker math environment differs from one-thread contract")
    if any(
        worker["environment"].get(name) != "1"
        for name in (
            "_MYFENICS_NATIVE_QUALIFIED_ACTIVATION",
            "TASK39EXTRA_INT64_ACTIVATION",
            "TASK39EXTRA_PORD64_ACTIVATION",
        )
    ):
        raise ValueError("worker qualified ABI activation markers are incomplete")
    if len(expected_worker_cpus) == GATE_CD_PARALLEL32_WORKERS:
        if not isinstance(package, dict):
            raise ValueError("Gate-CD N14 live capture needs its exact case package")
        exact = package.get("exact_cache_contract", {})
        try:
            bound_cpus = json.loads(
                worker["environment"].get("TASK40_EXACT_CACHE_WORKER_CPUS", "")
            )
        except json.JSONDecodeError as exc:
            raise ValueError("worker exact-cache CPU binding is malformed") from exc
        environment = worker["environment"]
        if (
            bound_cpus != expected_worker_cpus
            or environment.get("TASK40_EXACT_CACHE_ATTEMPT_ID")
            != package.get("attempt_id")
            or environment.get("TASK40_EXACT_CACHE_RUNTIME_TEMPLATE_SHA256")
            != exact.get("template_sha256")
        ):
            raise ValueError("worker exact-cache lease/template environment differs from package")
        contract_path = Path(
            environment.get("TASK40_EXACT_CACHE_CONTRACT", "")
        ).resolve(strict=True)
        contract_raw = contract_path.read_bytes()
        if hashlib.sha256(contract_raw).hexdigest() != environment.get(
            "TASK40_EXACT_CACHE_CONTRACT_SHA256"
        ):
            raise ValueError("worker exact-cache runtime contract hash differs")
        contract = json.loads(contract_raw)
        if (
            contract.get("worker_cpus") != expected_worker_cpus
            or contract.get("attempt_id") != package.get("attempt_id")
            or contract.get("template_sha256") != exact.get("template_sha256")
            or Path(contract.get("tensor_root", "")).resolve()
            != Path(contract.get("attempt_cache_root", "")).resolve() / "tensor"
            or Path(contract.get("carrier_root", "")).resolve()
            != Path(contract.get("attempt_cache_root", "")).resolve() / "carrier"
        ):
            raise ValueError("worker exact-cache runtime contract differs from package/lease")


def _write_once_marker(marker: Path, data: dict) -> None:
    marker.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(data, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def submit_once(
    package_path: str | Path,
    sidecar_path: str | Path,
    fresh_receipt_path: str | Path,
    review_path: str | Path,
    marker_path: str | Path,
    start_receipt_path: str | Path,
    live_receipt_path: str | Path,
    *,
    run_command=subprocess.run,
) -> dict:
    package, sidecar, package_sha, sidecar_sha = validate_package_sidecar(
        package_path, sidecar_path
    )
    review = _load_json(review_path)
    fresh = _load_json(fresh_receipt_path)
    review_bindings = review.get("bindings", review)
    review_status = review.get("decision", review.get("status"))
    if review_status != "PASS_GATE_CD_SYSTEMD_AND_FRESH":
        raise ValueError("main review is not the Gate-CD fresh/systemd PASS")
    if review_bindings.get("package_sha256") != package_sha:
        raise ValueError("main review does not bind this package")
    if review_bindings.get("sidecar_sha256") != sidecar_sha:
        raise ValueError("main review does not bind this sidecar")
    for key in (
        "source_commit",
        "input_sha256",
        "physical_model_sha256",
        "resolved_config_sha256",
    ):
        if review_bindings.get(key) != package.get(key):
            raise ValueError(f"main review does not bind {key}")
    if not fresh.get("fresh_pass") or fresh.get("launch_not_started") is not True:
        raise ValueError("a matching fresh PASS receipt is required")
    if (
        fresh.get("package_sha256") != package_sha
        or fresh.get("sidecar_sha256") != sidecar_sha
        or fresh.get("source_commit") != package.get("source_commit")
        or fresh.get("input_sha256") != package.get("input_sha256")
        or fresh.get("physical_model_sha256") != package.get("physical_model_sha256")
        or fresh.get("resolved_config_sha256")
        != package.get("resolved_config_sha256")
    ):
        raise ValueError("fresh receipt package/source identity mismatch")
    argv = _validate_systemd_argv(sidecar)
    unit = sidecar["service_unit"]
    _require_systemd_unit_not_loaded(unit)
    marker = Path(marker_path)
    _write_once_marker(
        marker,
        {
            "schema": "task40.gate_cd.formal_systemd_submission_once.v1",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "service_unit": unit,
            "package_sha256": package_sha,
            "sidecar_sha256": sidecar_sha,
            "fresh_receipt_sha256": sha256_file(fresh_receipt_path),
            "main_review_sha256": sha256_file(review_path),
            "systemd_submitted": False,
            "automatic_retry": False,
        },
    )
    completed = run_command(argv, text=True, capture_output=True, timeout=60)
    start = {
        "schema": "task40.gate_cd.formal_systemd_start_receipt.v1",
        "submitted_utc": datetime.now(timezone.utc).isoformat(),
        "service_unit": unit,
        "systemd_run_argv": argv,
        "returncode": int(completed.returncode),
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "package_sha256": package_sha,
        "sidecar_sha256": sidecar_sha,
        "source_commit": package["source_commit"],
        "automatic_retry": False,
    }
    _atomic_json(start_receipt_path, start)
    if completed.returncode != 0:
        raise RuntimeError(
            "systemd submission failed after consuming one-shot marker; no retry"
        )
    marker_data = _load_json(marker)
    marker_data["systemd_submitted"] = True
    marker_data["systemd_returncode"] = int(completed.returncode)
    _atomic_json(marker, marker_data)
    try:
        runtime_reservation, reservation_sha, scope_sha = (
            _wait_for_runtime_cpu_reservation(sidecar, package)
        )
        runtime_cpu = runtime_reservation["cpu_reservation"]
        runtime_worker_cpus = runtime_cpu.get("worker_cpus")
        if not isinstance(runtime_worker_cpus, list) or not runtime_worker_cpus:
            runtime_worker_cpus = [runtime_cpu["worker_cpu"]]
        worker_cpus = [int(cpu) for cpu in runtime_worker_cpus]
        start["runtime_cpu_reservation"] = runtime_reservation
        start["runtime_cpu_reservation_sha256"] = reservation_sha
        start["runtime_scope_sha256"] = scope_sha
        start["affinity_authority"] = (
            "committed_runtime_one_shot_reservation_not_fresh_sample"
        )
        start["cpu_exclusive_ownership"] = False
        _atomic_json(start_receipt_path, start)
    except (OSError, ValueError, TimeoutError, KeyError) as exc:
        start["live_identity_verified"] = False
        start["live_capture_error"] = str(exc)
        start["passive_capture_required"] = True
        start["submission_was_not_repeated"] = True
        _atomic_json(start_receipt_path, start)
        raise RuntimeError(
            "systemd submitted once but runtime CPU lease is not yet readable; "
            "passively inspect this unit, never resubmit"
        ) from exc
    try:
        capture = capture_unit(unit)
        if not worker_cpus:
            raise ValueError("runtime reservation does not bind selected worker CPUs")
        capture["runtime_cpu_reservation"] = runtime_reservation
        capture["runtime_cpu_reservation_sha256"] = reservation_sha
        capture["fresh_worker_affinity_sample_is_not_authoritative"] = True
        capture_arguments = (
            capture,
            REPO_ROOT,
            worker_cpus,
            int(package.get("math_threads", 1)),
        )
        if package.get("profile_identity") in GATE_CD_PARALLEL32_PROFILES:
            _require_live_capture(*capture_arguments, package=package)
        else:
            _require_live_capture(*capture_arguments)
        _atomic_json(live_receipt_path, capture)
        start["live_identity_verified"] = True
        start["live_receipt_sha256"] = sha256_file(live_receipt_path)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        start["live_identity_verified"] = False
        start["live_capture_error"] = str(exc)
        start["passive_capture_required"] = True
        _atomic_json(start_receipt_path, start)
        raise RuntimeError(
            "systemd submitted once but live capture is incomplete; passively recapture same unit, never resubmit"
        ) from exc
    _atomic_json(start_receipt_path, start)
    return start


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    fresh = sub.add_parser("fresh")
    fresh.add_argument("--package", required=True)
    fresh.add_argument("--sidecar", required=True)
    fresh.add_argument("--output", required=True)
    launch = sub.add_parser("submit")
    launch.add_argument("--package", required=True)
    launch.add_argument("--sidecar", required=True)
    launch.add_argument("--fresh-receipt", required=True)
    launch.add_argument("--main-review", required=True)
    launch.add_argument("--marker", required=True)
    launch.add_argument("--start-receipt", required=True)
    launch.add_argument("--live-receipt", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--unit", required=True)
    capture.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        if args.command == "fresh":
            result = fresh_acceptance(args.package, args.sidecar, args.output)
        elif args.command == "submit":
            result = submit_once(
                args.package,
                args.sidecar,
                args.fresh_receipt,
                args.main_review,
                args.marker,
                args.start_receipt,
                args.live_receipt,
            )
        else:
            result = capture_unit(args.unit)
            _atomic_json(args.output, result)
        print(json.dumps(result, sort_keys=True, default=str))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"Gate-CD execution helper refused/failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(_cli())
