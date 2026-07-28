from __future__ import annotations

import argparse
import csv
import hashlib
import math
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from benchmarks.task034_wsl_resources import (
    cgroup_snapshot,
    effective_memory_limit,
    vmstat_swap_pages,
)
from benchmarks.task035c_p6_h10_gates import (
    TASK035C_P6_H10_BACKENDS,
    TASK035C_P6_H10_MPI_SIZES,
    task035c_p6_h10_preflight_authority_gate,
    valid_hex_digest,
)
from benchmarks.task035d_case097_gates import (
    TASK035D_CASE097_BACKEND,
    TASK035D_COMBINED_HP_PLAN_NAME,
    TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME,
    TASK035D_LEFT_GRATING_TOP_PLAN_NAME,
    TASK035D_LOCAL_H_PLAN_FILE_SHA256,
    TASK035D_LOCAL_H_PLAN_NAME,
    task035d_case097_combined_hp_plan_authority_gate,
    task035d_case097_combined_hp_solver_gate,
    task035d_case097_hp_factorial_bridge_plan_authority_gate,
    task035d_case097_hp_factorial_bridge_solver_gate,
    task035d_case097_left_grating_top_plan_authority_gate,
    task035d_case097_left_grating_top_solver_gate,
    task035d_case097_local_h_plan_authority_gate,
    task035d_case097_local_h_solver_gate,
    task035d_case097_plan_authority_gate,
    task035d_case097_sidewall_guard_plan_authority_gate,
    task035d_case097_sidewall_guard_solver_gate,
    task035d_case097_t30_solver_gate,
)
from benchmarks.task035d_selective_face_case097_gates import (
    TASK035D_SELECTIVE_FACE_PLAN_NAME,
    task035d_case097_selective_face_plan_authority_gate,
    task035d_case097_selective_face_solver_gate,
)
from benchmarks.task035d_selective_face_dwr_checker import (
    load_selective_face_coarse_endpoint,
    task035d_selective_face_dwr_report_gate,
)
from benchmarks.task035d_selective_face_snapshot_gate import (
    task035d_selective_face_coarse_snapshot_gate,
)
from benchmarks.task035d_nested_p_snapshot_gate import (
    task035d_coarse_snapshot_artifact_gate,
)
from benchmarks.task035d_nested_p_dwr_checker import (
    task035d_nested_p_dwr_report_gate,
)
from benchmarks.run_direct_memory_forensics import (
    TIMELINE_FIELDS,
    _add_cpu_core_equivalents,
    _historical_peak_upper_bound,
    _read_progress_events,
    _sample,
    _source_provenance,
    _stage_peaks,
)
from src.adaptivity.blind_controller.contracts import (
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_ROOT = (
    ROOT / "benchmarks" / "artifacts" / "cases" / "091" / "task033_full3d"
)
REFERENCE_PLANES_NM = (10.0, 30.0, 60.0, 90.0, 110.0)
GIB = 1024**3
_PARENT_LAUNCH_TOKEN_ENV = "MYFENICS_WATCHDOG_PARENT_TOKEN"
TASK035D_LOCAL_H_CANDIDATES = {
    TASK035D_LOCAL_H_PLAN_NAME,
    TASK035D_COMBINED_HP_PLAN_NAME,
    TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME,
    TASK035D_LEFT_GRATING_TOP_PLAN_NAME,
    TASK035D_SELECTIVE_FACE_PLAN_NAME,
}
TASK035D_NESTED_P_PHASES = {
    "coarse-snapshot",
    "enriched-evaluate",
}
TASK035D_SELECTIVE_FACE_PHASES = {
    "coarse-snapshot",
    "enriched-evaluate",
}
TASK035E_REFERENCE_H_NM = frozenset({10.0, 7.5, 5.0})
TASK035E_REFERENCE_BACKEND = "assembly_time_static_condensed"
TASK035E_REFERENCE_MPI_SIZE = 8
TASK035E_REFERENCE_MINIMUM_HEADROOM_FRACTION = 0.20
TASK035E_REFERENCE_TOTAL_MEMORY_CAP_FRACTION = 0.80
TASK035E_REFERENCE_RESOURCE_AUTHORITY_SCHEMA = (
    "task035e.reference-resource-authority.v1"
)
TASK035E_H5_FACTORIZATION_AUTHORITY_SCHEMA = (
    "task035e.h5-factorization-launch-authority.v1"
)
TASK035E_H5_FACTORIZATION_AUTHORITY_VALIDITY_SECONDS = 15 * 60
TASK035E_BLIND_CANDIDATE_BACKEND = (
    "assembly_time_variable_p_condensed"
)
TASK035E_BLIND_CANDIDATE_H_NM = frozenset({20.0, 15.0})
TASK035E_BLIND_CANDIDATE_MPI_SIZE = 8
TASK035E_BLIND_CANDIDATE_MEMORY_CAP_BYTES = 11 * GIB
TASK035E_INTERNAL_PROBE_SCHEMA = "task035e.internal-probe-launch.v1"
TASK035E_INTERNAL_PROBE_KINDS = frozenset(
    {"algebraic", "dtn", "postprocess", "serial_mpi1"}
)
TASK035E_BLIND_CANDIDATE_PLAN_SCHEMA = (
    "task035e.stage4-multilevel-local-h-refinement-plan.v1"
)
TASK035E_BLIND_CANDIDATE_AUTHORITY_SCHEMA = (
    "task035e.blind-current-solve-authority.v1"
)
TASK035E_BLIND_INITIAL_PROVENANCE_SCHEMA = (
    "task035e.blind-initial-provenance.v1"
)
TASK035E_BLIND_TRANSITION_PROVENANCE_SCHEMA = (
    "task035e.blind-solver-plan-transition.v2"
)
TASK035E_CURRENT_SNAPSHOT_SCHEMA = (
    "task035e.multigoal-current-live-snapshot.v1"
)
TASK035E_SHADOW_EVALUATION_SCHEMA = (
    "task035e.live-shadow-evaluation.v1"
)
TASK035E_TRIAL_ID_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}"
)
TASK035E_FORBIDDEN_INPUT_PATH_PARTS = frozenset(
    {
        "reference_certifier",
        "hidden_auditor",
        "sealed_reference",
        "sealed-reference",
    }
)
TASK035E_TRANSITION_ACTION_SCHEMA = "task035e.hp-transition-action.v2"
TASK035E_TRANSITION_ACTION_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "action_id",
        "kind",
        "cycle_index",
        "source_sha",
        "algorithm_sha256",
        "from_state_sha256",
        "root_catalog_sha256",
        "from_leaf_catalog_sha256",
        "from_cell_degree_plan_sha256",
        "from_forest_geometry_sha256",
        "from_degree_plan_sha256",
        "stage_prefix_length",
        "stage_prefix_sha256",
        "requested_split_keys",
        "degree_deltas",
        "canonical_target_ids",
        "maximum_level",
        "expected_removed_leaf_keys",
        "expected_added_leaf_keys",
        "expected_net_added_leaf_count",
        "expected_next_leaf_catalog_sha256",
        "expected_next_cell_degree_plan_sha256",
        "expected_next_forest_geometry_sha256",
        "expected_next_degree_plan_sha256",
        "action_identity_sha256",
        "action_sha256",
    }
)
TASK035E_TRANSITION_PROVENANCE_FIELDS = frozenset(
    {
        "schema_version",
        "status",
        "source_sha",
        "algorithm_sha256",
        "cycle_index",
        "previous_plan_content_sha256",
        "previous_plan_canonical_solver_content_sha256",
        "from_state_sha256",
        "transition_action_sha256",
        "transition_action_id",
        "transition_action_kind",
        "transition_action_cycle_index",
        "transition_action_source_sha",
        "transition_action_target_ids",
        "next_state_sha256",
        "stage_action_sha256s",
        "next_stage_prefix_sha256",
        "from_leaf_catalog_sha256",
        "from_cell_degree_plan_sha256",
        "next_leaf_catalog_sha256",
        "next_cell_degree_plan_sha256",
        "goal_values_embedded",
        "dwr_values_embedded",
        "evaluator_inputs_consumed",
        "ordinary_default_changed",
        "next_plan_canonical_solver_content_sha256",
        "transition_provenance_sha256",
    }
)


def _canonical_json_value(value: Any) -> Any:
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_json_value(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_canonical_json_value(item) for item in value]
    return value


def _canonical_json_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        _canonical_json_value(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _write_task035e_private_json_atomic(
    path: Path,
    payload: Mapping[str, Any],
) -> None:
    """Atomically publish one final mode-0600 Task035e JSON record."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            stream.write(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    indent=2,
                    allow_nan=False,
                )
                + "\n"
            )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        path.chmod(0o600)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _task035e_namespaced_json_sha256(
    payload: Any,
    *,
    namespace: str,
) -> str:
    encoded = json.dumps(
        _canonical_json_value(payload),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    digest.update(encoded)
    return digest.hexdigest()


def _task035e_safe_namespaced_json_sha256(
    payload: Any,
    *,
    namespace: str,
) -> str | None:
    try:
        return _task035e_namespaced_json_sha256(
            payload,
            namespace=namespace,
        )
    except (TypeError, ValueError):
        return None


def _reject_nonfinite_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON constant {value}")


def _reject_duplicate_json_object(
    pairs: list[tuple[str, Any]],
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in pairs:
        if key in payload:
            raise ValueError(f"duplicate JSON object key {key!r}")
        payload[key] = value
    return payload


def _task035e_strict_json_loads(text: str) -> Any:
    return json.loads(
        text,
        parse_constant=_reject_nonfinite_json_constant,
        object_pairs_hook=_reject_duplicate_json_object,
    )


def _task035e_private_regular_input_path(
    path: Path,
    *,
    label: str,
) -> Path:
    unresolved = (
        path if path.is_absolute() else ROOT / path
    ).expanduser()
    resolved = unresolved.resolve()
    if (
        unresolved.is_symlink()
        or not resolved.is_file()
        or (resolved.stat().st_mode & 0o777) != 0o600
        or {
            part.lower()
            for part in resolved.parts
        }.intersection(TASK035E_FORBIDDEN_INPUT_PATH_PARTS)
    ):
        raise SystemExit(
            f"Task035e {label} must be a non-symlink regular file with "
            "mode 0600 outside every evaluator/reference path."
        )
    return resolved


def _task035e_blind_candidate_config_sha256(
    config: Mapping[str, Any],
) -> str:
    """Match the isolated candidate-output adapter's config identity."""

    return _canonical_json_sha256(
        {
            "schema_version": "task035e.blind-current-config.v1",
            "config": config,
        }
    )


def _task035e_blind_candidate_authority(
    args: argparse.Namespace,
    solver_summary: Mapping[str, Any],
    *,
    source_sha: str,
    qualified: bool,
) -> dict[str, Any] | None:
    """Expose the closed adapter authority only after every gate passes."""

    if (
        not args.task035e_blind_candidate_gate
        or not qualified
        or args.task035e_internal_probe_kind is not None
    ):
        return None
    config = solver_summary.get("config")
    if not isinstance(config, Mapping):
        return None
    output_roles = {
        "current": "blind_current_solve",
        "p-shadow": "blind_p_shadow_solve",
        "h-shadow": "blind_h_shadow_solve",
    }
    output_role = output_roles.get(args.task035e_blind_output_role)
    if output_role is None:
        return None
    return {
        "schema_version": TASK035E_BLIND_CANDIDATE_AUTHORITY_SCHEMA,
        "selected": True,
        "output_role": output_role,
        "trial_id": str(args.task035e_blind_trial_id),
        "cycle_index": int(args.task035e_blind_cycle_index),
        "source_sha": source_sha,
        "config_sha256": _task035e_blind_candidate_config_sha256(config),
    }


def _task035e_internal_probe_authority(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    """Describe the one narrow internal-budget perturbation at launch."""

    kind = args.task035e_internal_probe_kind
    if kind is None:
        return None
    overrides: dict[str, Any] = {}
    if kind == "dtn":
        overrides = {
            "stage4_dtn_order_policy": "manual",
            "diffraction_order_max_m": int(
                args.task035e_probe_dtn_max_m
            ),
            "diffraction_order_max_n": int(
                args.task035e_probe_dtn_max_n
            ),
        }
    elif kind == "postprocess":
        overrides = {
            "stage4_dtn_quadrature_degree": int(
                args.task035e_probe_surface_quadrature_degree
            )
        }
    return {
        "schema_version": TASK035E_INTERNAL_PROBE_SCHEMA,
        "selected": True,
        "kind": str(kind),
        "mpi_size": int(args.mpi_size),
        "trial_id": str(args.task035e_blind_trial_id),
        "cycle_index": int(args.task035e_blind_cycle_index),
        "output_role": "current",
        "plan_file_sha256": (
            args.stage4_local_h_refinement_plan_sha256
        ),
        "current_snapshot_file_sha256": (
            args.task035e_current_snapshot_manifest_sha256
        ),
        "config_overrides": overrides,
        "ordinary_default_changed": False,
    }


def _task035e_internal_probe_success_status(
    args: argparse.Namespace,
    *,
    qualified: bool,
) -> str | None:
    """Keep diagnostic probes outside the blind-candidate success class."""

    kind = args.task035e_internal_probe_kind
    if (
        not qualified
        or args.run_kind != "full-solve"
        or kind not in TASK035E_INTERNAL_PROBE_KINDS
    ):
        return None
    if kind == "serial_mpi1":
        return "task035e_internal_probe_serial_mpi1_pass"
    return "task035e_internal_probe_mpi8_pass"


def _validate_task035e_formal_runtime(
    *,
    require_private_worker_tmp: bool,
) -> dict[str, Any]:
    """Fail closed before a formal Task035e MPI launch on ABI drift."""

    if os.name != "posix" or sys.platform != "linux":
        raise SystemExit("Task035e formal execution requires Linux/WSL.")
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        raise SystemExit(
            "Task035e formal execution requires "
            "scripts/activate_myfenics_wsl.sh."
        )
    expected_python = Path(
        os.path.abspath(ROOT / ".venv" / "bin" / "python")
    )
    actual_python = Path(os.path.abspath(sys.executable))
    if actual_python != expected_python:
        raise SystemExit(
            "Task035e formal execution requires the repository .venv Python."
        )

    import numpy as np
    import dolfinx
    import mpi4py
    import petsc4py
    from petsc4py import PETSc

    if np.dtype(PETSc.ScalarType) != np.dtype(np.complex128):
        raise SystemExit("Task035e formal PETSc.ScalarType must be complex128.")
    if np.dtype(PETSc.IntType) != np.dtype(np.int32):
        raise SystemExit("Task035e formal PETSc.IntType must be int32.")

    module_paths: dict[str, str] = {}
    for name, module in (
        ("petsc4py", petsc4py),
        ("mpi4py", mpi4py),
        ("dolfinx", dolfinx),
    ):
        raw_path = getattr(module, "__file__", None)
        if not isinstance(raw_path, str):
            raise SystemExit(f"Task035e {name} module path is unreadable.")
        path = Path(raw_path).resolve()
        if not path.is_absolute() or path.as_posix().startswith("/mnt/"):
            raise SystemExit(
                f"Task035e {name} must come from the Linux ABI stack."
            )
        module_paths[name] = path.as_posix()

    tmp_paths: dict[str, str] = {}
    for name in ("TMPDIR", "TMP", "TEMP"):
        value = os.environ.get(name)
        if require_private_worker_tmp and value != "/tmp":
            raise SystemExit(
                f"Task035e formal worker {name} must be exactly /tmp."
            )
        if value is not None:
            tmp_paths[name] = value
    if not Path("/tmp").is_dir() or not os.access(
        "/tmp",
        os.W_OK | os.X_OK,
    ):
        raise SystemExit("Task035e formal worker requires writable /tmp.")

    return {
        "schema_version": "task035e.formal-wsl-runtime.v1",
        "qualified_activation": True,
        "python_executable": actual_python.as_posix(),
        "petsc_scalar_type": np.dtype(PETSc.ScalarType).name,
        "petsc_int_type": np.dtype(PETSc.IntType).name,
        "module_paths": module_paths,
        "temporary_paths": tmp_paths,
        "private_worker_tmp_required": require_private_worker_tmp,
    }


def _task035e_reference_config_authority(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    """Return one run-kind-neutral configuration identity for the p6 sequence."""

    if not args.task035e_reference_certifier_gate:
        return None
    normalized = replace(
        _full3d_config(args),
        matrix_diagnostics_assemble_only=False,
        matrix_diagnostics_factorization_only=False,
        stage4_static_condensed_resource_only_assembly=False,
        full3d_reference_export=True,
        full3d_reference_plane_z=REFERENCE_PLANES_NM,
        unique_output=False,
    )
    payload = {
        "schema_version": "task035e.reference-config-authority.v1",
        "mpi_size": int(args.mpi_size),
        "config": normalized.as_jsonable(),
    }
    return {
        "schema_version": payload["schema_version"],
        "sha256": _canonical_json_sha256(payload),
        "payload": _canonical_json_value(payload),
    }


def _task035e_reference_resource_policy(
    memory_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the fail-closed memory envelope fixed by the Task035e task book."""

    total = memory_snapshot.get("wsl_total_bytes")
    available = memory_snapshot.get("host_available_bytes")
    readable = bool(
        isinstance(total, int)
        and not isinstance(total, bool)
        and total > 0
        and isinstance(available, int)
        and not isinstance(available, bool)
        and available >= 0
    )
    if not readable:
        return {
            "schema_version": "task035e.reference-resource-policy.v1",
            "pass": False,
            "failure": "initial_memory_authority_unreadable",
            "mem_total_bytes": total,
            "mem_available_start_bytes": available,
            "minimum_headroom_fraction": (
                TASK035E_REFERENCE_MINIMUM_HEADROOM_FRACTION
            ),
            "total_memory_cap_fraction": (
                TASK035E_REFERENCE_TOTAL_MEMORY_CAP_FRACTION
            ),
            "headroom_floor_bytes": None,
            "total_fraction_cap_bytes": None,
            "available_minus_headroom_bytes": None,
            "effective_job_cap_bytes": None,
        }
    total_bytes = int(total)
    available_bytes = int(available)
    headroom_floor = int(
        TASK035E_REFERENCE_MINIMUM_HEADROOM_FRACTION * total_bytes
    )
    total_fraction_cap = int(
        TASK035E_REFERENCE_TOTAL_MEMORY_CAP_FRACTION * total_bytes
    )
    available_minus_headroom = available_bytes - headroom_floor
    effective_job_cap = min(total_fraction_cap, available_minus_headroom)
    pass_gate = bool(
        available_bytes >= headroom_floor and effective_job_cap > 0
    )
    return {
        "schema_version": "task035e.reference-resource-policy.v1",
        "pass": pass_gate,
        "failure": None if pass_gate else "initial_headroom_below_20_percent",
        "mem_total_bytes": total_bytes,
        "mem_available_start_bytes": available_bytes,
        "minimum_headroom_fraction": (
            TASK035E_REFERENCE_MINIMUM_HEADROOM_FRACTION
        ),
        "total_memory_cap_fraction": (
            TASK035E_REFERENCE_TOTAL_MEMORY_CAP_FRACTION
        ),
        "headroom_floor_bytes": headroom_floor,
        "total_fraction_cap_bytes": total_fraction_cap,
        "available_minus_headroom_bytes": available_minus_headroom,
        "effective_job_cap_bytes": effective_job_cap,
        "formula": (
            "min(0.8*MemTotal, MemAvailable_start-0.2*MemTotal)"
        ),
    }


def _task035e_blind_candidate_resource_policy(
    memory_snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    """Bound a blind solve by both live headroom and the fixed 11 GiB cap."""

    base = _task035e_reference_resource_policy(memory_snapshot)
    dynamic_cap = base.get("effective_job_cap_bytes")
    effective_cap = (
        min(
            int(dynamic_cap),
            TASK035E_BLIND_CANDIDATE_MEMORY_CAP_BYTES,
        )
        if isinstance(dynamic_cap, int) and not isinstance(dynamic_cap, bool)
        else None
    )
    return {
        **base,
        "schema_version": "task035e.blind-candidate-resource-policy.v1",
        "pass": bool(base.get("pass") is True and effective_cap is not None),
        "task035e_candidate_cap_bytes": (
            TASK035E_BLIND_CANDIDATE_MEMORY_CAP_BYTES
        ),
        "dynamic_headroom_cap_bytes": dynamic_cap,
        "effective_job_cap_bytes": effective_cap,
        "formula": (
            "min(11GiB, 0.8*MemTotal, "
            "MemAvailable_start-0.2*MemTotal)"
        ),
    }


def _apply_task035e_reference_dynamic_cap(
    args: argparse.Namespace,
    memory_snapshot: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Apply the Task035e cap once without permitting a looser override."""

    if not (
        args.task035e_reference_certifier_gate
        or args.task035e_blind_candidate_gate
    ):
        return None
    policy = (
        _task035e_blind_candidate_resource_policy(memory_snapshot)
        if args.task035e_blind_candidate_gate
        else _task035e_reference_resource_policy(memory_snapshot)
    )
    if policy["pass"] is not True:
        raise SystemExit(
            "Task035e formal preflight controlled resource stop: "
            f"{policy['failure']}"
        )
    cap_gib = float(policy["effective_job_cap_bytes"]) / GIB
    if (
        args.terminate_gib is not None
        and not math.isclose(
            float(args.terminate_gib),
            cap_gib,
            rel_tol=0.0,
            abs_tol=1.0 / GIB,
        )
    ):
        raise SystemExit(
            "Task035e termination cap is fixed by the selected formal "
            "resource policy; "
            "do not override --terminate-gib."
        )
    args.terminate_gib = cap_gib
    if args.warning_gib is None:
        args.warning_gib = 0.8 * cap_gib
    return policy


def _task035e_reference_resource_decision(
    row: Mapping[str, Any],
    *,
    mem_available_bytes: int | None,
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate one live sample, with nonzero swap taking first priority."""

    process_tree_mb = row.get("mpi_process_tree_rss_mb")
    process_tree_swap_mb = row.get("mpi_process_tree_swap_mb")
    dedicated = row.get("job_cgroup_dedicated") is True
    cgroup_mb = row.get("container_cgroup_current_mb") if dedicated else 0.0
    cgroup_swap_mb = (
        row.get("container_swap_current_mb") if dedicated else 0.0
    )
    numeric_swap_values = [
        float(value)
        for value in (process_tree_swap_mb, cgroup_swap_mb)
        if isinstance(value, (int, float)) and not isinstance(value, bool)
    ]
    numeric_authority = all(
        isinstance(value, (int, float)) and not isinstance(value, bool)
        for value in (
            process_tree_mb,
            process_tree_swap_mb,
            cgroup_mb,
            cgroup_swap_mb,
        )
    )
    job_authority_bytes = (
        None
        if not numeric_authority
        else int(max(float(process_tree_mb), float(cgroup_mb)) * 1024**2)
    )
    swap_bytes = (
        int(max(numeric_swap_values) * 1024**2)
        if numeric_swap_values
        else None
    )
    headroom_floor = policy.get("headroom_floor_bytes")
    effective_job_cap = policy.get("effective_job_cap_bytes")
    reason = None
    if isinstance(swap_bytes, int) and swap_bytes > 0:
        reason = "nonzero_swap"
    elif (
        not numeric_authority
        or not isinstance(mem_available_bytes, int)
        or isinstance(mem_available_bytes, bool)
        or not isinstance(headroom_floor, int)
        or not isinstance(effective_job_cap, int)
    ):
        reason = "live_resource_authority_unreadable"
    elif mem_available_bytes < headroom_floor:
        reason = "memavailable_below_20_percent"
    elif (
        isinstance(job_authority_bytes, int)
        and job_authority_bytes >= effective_job_cap
    ):
        reason = "effective_job_cap_reached"
    return {
        "stop": reason is not None,
        "reason": reason,
        "mem_available_bytes": mem_available_bytes,
        "job_memory_authority_bytes": job_authority_bytes,
        "swap_authority_bytes": swap_bytes,
        "headroom_floor_bytes": headroom_floor,
        "effective_job_cap_bytes": effective_job_cap,
    }


def _task035e_reference_resource_summary(
    *,
    policy: Mapping[str, Any],
    samples: list[Mapping[str, Any]],
    stop_reason: str | None,
) -> dict[str, Any]:
    available_values = [
        int(sample["mem_available_bytes"])
        for sample in samples
        if isinstance(sample.get("mem_available_bytes"), int)
        and not isinstance(sample.get("mem_available_bytes"), bool)
    ]
    memory_values = [
        int(sample["job_memory_authority_bytes"])
        for sample in samples
        if isinstance(sample.get("job_memory_authority_bytes"), int)
        and not isinstance(sample.get("job_memory_authority_bytes"), bool)
    ]
    swap_values = [
        int(sample["swap_authority_bytes"])
        for sample in samples
        if isinstance(sample.get("swap_authority_bytes"), int)
        and not isinstance(sample.get("swap_authority_bytes"), bool)
    ]
    headroom_floor = policy.get("headroom_floor_bytes")
    cap = policy.get("effective_job_cap_bytes")
    minimum_available = min(available_values) if available_values else None
    maximum_memory = max(memory_values) if memory_values else None
    maximum_swap = max(swap_values) if swap_values else None
    pass_gate = bool(
        policy.get("pass") is True
        and samples
        and stop_reason is None
        and isinstance(minimum_available, int)
        and isinstance(headroom_floor, int)
        and minimum_available >= headroom_floor
        and isinstance(maximum_memory, int)
        and isinstance(cap, int)
        and maximum_memory < cap
        and maximum_swap == 0
    )
    return {
        "schema_version": "task035e.reference-live-resource-gate.v1",
        "pass": pass_gate,
        "controlled_resource_stop": stop_reason is not None,
        "stop_reason": stop_reason,
        "sample_count": len(samples),
        "minimum_mem_available_bytes": minimum_available,
        "maximum_job_memory_authority_bytes": maximum_memory,
        "maximum_swap_authority_bytes": maximum_swap,
        "zero_swap_every_sample": maximum_swap == 0,
        "minimum_headroom_20_percent_preserved": bool(
            isinstance(minimum_available, int)
            and isinstance(headroom_floor, int)
            and minimum_available >= headroom_floor
        ),
        "effective_job_cap_respected": bool(
            isinstance(maximum_memory, int)
            and isinstance(cap, int)
            and maximum_memory < cap
        ),
        "policy": dict(policy),
    }


def _task035e_blind_candidate_resource_summary(
    *,
    policy: Mapping[str, Any],
    samples: list[Mapping[str, Any]],
    stop_reason: str | None,
) -> dict[str, Any]:
    summary = _task035e_reference_resource_summary(
        policy=policy,
        samples=samples,
        stop_reason=stop_reason,
    )
    summary["schema_version"] = (
        "task035e.blind-candidate-live-resource-gate.v1"
    )
    summary["task035e_candidate_cap_bytes"] = (
        TASK035E_BLIND_CANDIDATE_MEMORY_CAP_BYTES
    )
    summary["memory_cap_at_most_11_gib"] = bool(
        isinstance(policy.get("effective_job_cap_bytes"), int)
        and policy["effective_job_cap_bytes"]
        <= TASK035E_BLIND_CANDIDATE_MEMORY_CAP_BYTES
    )
    summary["pass"] = bool(
        summary["pass"] and summary["memory_cap_at_most_11_gib"]
    )
    return summary


def _task035e_reference_resource_authority_gate(
    payload: Mapping[str, Any] | None,
    *,
    expected_sha256: str | None,
    observed_sha256: str | None,
    expected_source_sha: str | None,
    expected_config_sha256: str | None,
    expected_h_nm: float,
) -> dict[str, Any]:
    """Qualify one prior Task035e assembly run as resource-only authority."""

    record = payload if isinstance(payload, Mapping) else {}
    source = record.get("source")
    source = source if isinstance(source, Mapping) else {}
    task035e = record.get("task035e_reference_certifier")
    task035e = task035e if isinstance(task035e, Mapping) else {}
    config_authority = task035e.get("config_authority")
    config_authority = (
        config_authority if isinstance(config_authority, Mapping) else {}
    )
    live_gate = task035e.get("live_resource_gate")
    live_gate = live_gate if isinstance(live_gate, Mapping) else {}
    policy = live_gate.get("policy")
    policy = policy if isinstance(policy, Mapping) else {}
    qualification = record.get("qualification")
    qualification = (
        qualification if isinstance(qualification, Mapping) else {}
    )
    calibration = record.get("calibration")
    calibration = calibration if isinstance(calibration, Mapping) else {}
    environment_before = record.get("environment_before")
    environment_before = (
        environment_before if isinstance(environment_before, Mapping) else {}
    )
    total = environment_before.get("wsl_total_bytes")
    available = environment_before.get("host_available_bytes")
    expected_policy = _task035e_reference_resource_policy(environment_before)
    cap = policy.get("effective_job_cap_bytes")
    maximum_memory = live_gate.get("maximum_job_memory_authority_bytes")
    checks = {
        "object_present": bool(record),
        "record_hash_expected_valid": valid_hex_digest(expected_sha256, 64),
        "record_hash_observed_valid": valid_hex_digest(observed_sha256, 64),
        "record_hash_matches_expected": expected_sha256 == observed_sha256,
        "schema_identity": (
            record.get("schema_version") == "task033.full3d-watchdog.v1"
            and record.get("benchmark_id")
            == "task033_target_full3d_watchdog"
        ),
        "task035e_gate_selected": (
            task035e.get("schema_version")
            == TASK035E_REFERENCE_RESOURCE_AUTHORITY_SCHEMA
            and task035e.get("selected") is True
        ),
        "resource_only_not_physics": (
            record.get("run_kind") == "assembly-only"
            and record.get("status")
            == "task035e_reference_assembly_resource_pass"
            and task035e.get("credit") == "resource_only_not_physics"
        ),
        "same_clean_source": (
            valid_hex_digest(expected_source_sha, 40)
            and source.get("commit_sha") == expected_source_sha
            and source.get("head_after_sha") == expected_source_sha
            and source.get("tracked_source_dirty") is False
            and source.get("stable_and_clean_after") is True
        ),
        "same_config_authority": (
            valid_hex_digest(expected_config_sha256, 64)
            and config_authority.get("sha256") == expected_config_sha256
        ),
        "same_fixed_reference_scope": (
            record.get("degree") == 6
            and isinstance(record.get("h_nm"), (int, float))
            and math.isclose(float(record["h_nm"]), float(expected_h_nm))
            and record.get("polarization_kind") == "s"
            and record.get("mpi_size") == TASK035E_REFERENCE_MPI_SIZE
            and record.get("profile") == "default"
            and record.get("stage4_full3d_assembly_backend_requested")
            == TASK035E_REFERENCE_BACKEND
            and record.get("stage4_full3d_assembly_backend_actual")
            == TASK035E_REFERENCE_BACKEND
        ),
        "positive_assembly_rows_and_nnz": (
            isinstance(calibration.get("exact_rows"), (int, float))
            and not isinstance(calibration.get("exact_rows"), bool)
            and float(calibration["exact_rows"]) > 0.0
            and isinstance(
                calibration.get("exact_assembled_nnz"),
                (int, float),
            )
            and not isinstance(
                calibration.get("exact_assembled_nnz"),
                bool,
            )
            and float(calibration["exact_assembled_nnz"]) > 0.0
        ),
        "starting_resource_snapshot_bound": (
            isinstance(total, int)
            and total > 0
            and isinstance(available, int)
            and available >= 0
            and policy.get("mem_total_bytes") == total
            and policy.get("mem_available_start_bytes") == available
        ),
        "dynamic_cap_exact": (
            expected_policy.get("pass") is True
            and policy.get("formula")
            == "min(0.8*MemTotal, MemAvailable_start-0.2*MemTotal)"
            and policy.get("minimum_headroom_fraction")
            == TASK035E_REFERENCE_MINIMUM_HEADROOM_FRACTION
            and policy.get("total_memory_cap_fraction")
            == TASK035E_REFERENCE_TOTAL_MEMORY_CAP_FRACTION
            and cap == expected_policy.get("effective_job_cap_bytes")
        ),
        "live_gate_passed": (
            live_gate.get("pass") is True
            and live_gate.get("controlled_resource_stop") is False
            and live_gate.get("stop_reason") is None
            and live_gate.get("minimum_headroom_20_percent_preserved") is True
            and live_gate.get("effective_job_cap_respected") is True
        ),
        "zero_swap": (
            record.get("no_swap") is True
            and live_gate.get("zero_swap_every_sample") is True
            and live_gate.get("maximum_swap_authority_bytes") == 0
        ),
        "maximum_memory_below_dynamic_cap": (
            isinstance(maximum_memory, int)
            and isinstance(cap, int)
            and maximum_memory < cap
        ),
        "assembly_qualification_passed": (
            qualification.get("pass") is True
            and qualification.get("failures") == []
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "task035e.reference-resource-authority-gate.v1",
        "pass": not failures,
        "role": "assembly_resource_only_not_physics_authority",
        "expected_sha256": expected_sha256,
        "observed_sha256": observed_sha256,
        "checks": checks,
        "failures": failures,
    }


def _task035e_h5_factorization_authority_gate(
    payload: Mapping[str, Any] | None,
    *,
    expected_file_sha256: str | None,
    observed_file_sha256: str | None,
    expected_assembly_sha256: str | None,
    expected_source_sha: str | None,
    expected_config_sha256: str | None,
    now_utc: datetime | None = None,
) -> dict[str, Any]:
    """Validate one short-lived h5 MUMPS factorization launch decision."""

    record = payload if isinstance(payload, Mapping) else {}
    decision = record.get("payload")
    decision = decision if isinstance(decision, Mapping) else {}
    target = decision.get("target")
    target = target if isinstance(target, Mapping) else {}
    campaign = decision.get("campaign_identity")
    campaign = campaign if isinstance(campaign, Mapping) else {}
    identity_checks = decision.get("identity_checks")
    identity_checks = (
        identity_checks if isinstance(identity_checks, Mapping) else {}
    )
    input_records = decision.get("input_records")
    input_records = (
        input_records if isinstance(input_records, Mapping) else {}
    )
    gate = decision.get("gate")
    gate = gate if isinstance(gate, Mapping) else {}
    prediction = decision.get("prediction")
    prediction = prediction if isinstance(prediction, Mapping) else {}
    peak_interval = prediction.get("solver_peak_bytes_interval")
    peak_interval = (
        peak_interval if isinstance(peak_interval, Mapping) else {}
    )
    live_memory = decision.get("live_memory")
    live_memory = (
        live_memory if isinstance(live_memory, Mapping) else {}
    )
    issued_at = None
    expires_at = None
    try:
        issued_at = datetime.fromisoformat(str(decision.get("issued_at_utc")))
        expires_at = datetime.fromisoformat(str(decision.get("expires_at_utc")))
        if issued_at.tzinfo is None or expires_at.tzinfo is None:
            issued_at = None
            expires_at = None
    except ValueError:
        issued_at = None
        expires_at = None
    now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if issued_at is not None:
        issued_at = issued_at.astimezone(timezone.utc)
    if expires_at is not None:
        expires_at = expires_at.astimezone(timezone.utc)
    input_rows = {
        name: (
            input_records.get(name)
            if isinstance(input_records.get(name), Mapping)
            else {}
        )
        for name in ("h10_full", "h7p5_full", "h5_assembly")
    }
    input_hashes_exact = bool(
        set(input_records) == set(input_rows)
        and all(
            valid_hex_digest(row.get("expected_sha256"), 64)
            and row.get("observed_sha256") == row.get("expected_sha256")
            for row in input_rows.values()
        )
    )
    predicted_upper = peak_interval.get("upper")
    live_cap = live_memory.get("effective_job_cap_bytes")
    outer_payload_sha256 = (
        _canonical_json_sha256(decision) if decision else None
    )
    checks = {
        "file_hash_expected_valid": valid_hex_digest(
            expected_file_sha256,
            64,
        ),
        "file_hash_observed_valid": valid_hex_digest(
            observed_file_sha256,
            64,
        ),
        "file_hash_matches_expected": (
            expected_file_sha256 == observed_file_sha256
        ),
        "closed_outer_schema": (
            set(record) == {"schema_version", "sha256", "payload"}
            and record.get("schema_version")
            == TASK035E_H5_FACTORIZATION_AUTHORITY_SCHEMA
        ),
        "closed_payload_schema": (
            set(decision)
            == {
                "schema_version",
                "authority_role",
                "credit",
                "issued_at_utc",
                "expires_at_utc",
                "validity_seconds",
                "campaign_identity",
                "target",
                "input_records",
                "identity_checks",
                "prediction",
                "live_memory",
                "gate",
            }
            and decision.get("schema_version")
            == TASK035E_H5_FACTORIZATION_AUTHORITY_SCHEMA
        ),
        "payload_self_hash": (
            valid_hex_digest(record.get("sha256"), 64)
            and record.get("sha256") == outer_payload_sha256
        ),
        "resource_only_role": (
            decision.get("authority_role")
            == "resource_launch_decision_only"
            and decision.get("credit")
            == "no_pde_no_accuracy_no_reference_qualification_credit"
        ),
        "target_exact": (
            target
            == {
                "degree": 6,
                "h_nm": 5.0,
                "run_kind_to_authorize": "full-solve",
                "factor_solver": "mumps",
                "mpi_size": 8,
                "assembly_backend": TASK035E_REFERENCE_BACKEND,
                "profile": "default",
            }
        ),
        "campaign_source": (
            valid_hex_digest(expected_source_sha, 40)
            and campaign.get("source_sha") == expected_source_sha
        ),
        "campaign_h5_config": (
            valid_hex_digest(expected_config_sha256, 64)
            and campaign.get("h5_config_authority_sha256")
            == expected_config_sha256
        ),
        "campaign_physical_config": valid_hex_digest(
            campaign.get("physical_config_sha256"),
            64,
        ),
        "campaign_identity_checks": (
            identity_checks
            == {
                "same_clean_source": True,
                "same_physical_config_except_mesh_h": True,
            }
        ),
        "input_hashes_exact": input_hashes_exact,
        "same_h5_assembly_authority": (
            valid_hex_digest(expected_assembly_sha256, 64)
            and input_rows["h5_assembly"].get("expected_sha256")
            == expected_assembly_sha256
        ),
        "allow_gate": (
            gate.get("launch_allowed") is True
            and gate.get("predicted_upper_below_dynamic_cap") is True
            and gate.get("zero_swap_at_decision") is True
            and gate.get("minimum_20_percent_headroom_available") is True
            and gate.get("failures") == []
            and gate.get("deny_is_controlled_resource_stop") is False
        ),
        "prediction_below_decision_cap": (
            isinstance(predicted_upper, int)
            and not isinstance(predicted_upper, bool)
            and isinstance(live_cap, int)
            and not isinstance(live_cap, bool)
            and predicted_upper < live_cap
        ),
        "zero_swap_snapshot": live_memory.get("swap_used_bytes") == 0,
        "validity_window_exact": (
            decision.get("validity_seconds")
            == TASK035E_H5_FACTORIZATION_AUTHORITY_VALIDITY_SECONDS
            and issued_at is not None
            and expires_at is not None
            and (
                expires_at - issued_at
            ).total_seconds()
            == TASK035E_H5_FACTORIZATION_AUTHORITY_VALIDITY_SECONDS
        ),
        "fresh_at_launch": (
            issued_at is not None
            and expires_at is not None
            and issued_at <= now <= expires_at
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "task035e.h5-factorization-authority-gate.v1",
        "pass": not failures,
        "role": "short_lived_h5_factorization_launch_authority",
        "expected_file_sha256": expected_file_sha256,
        "observed_file_sha256": observed_file_sha256,
        "payload_sha256": record.get("sha256"),
        "checked_at_utc": now.isoformat(),
        "expires_at_utc": (
            None if expires_at is None else expires_at.isoformat()
        ),
        "checks": checks,
        "failures": failures,
    }


def _task035e_blind_candidate_plan_gate(
    payload: Mapping[str, Any] | None,
    *,
    expected_file_sha256: str | None,
    observed_file_sha256: str | None,
    expected_h_nm: float,
    config: Any,
    expected_source_sha: str | None = None,
    expected_cycle_index: int | None = None,
    expected_output_role: str | None = None,
    current_snapshot_binding: Mapping[str, Any] | None = None,
    transition_action: Mapping[str, Any] | None = None,
    internal_probe_kind: str | None = None,
) -> dict[str, Any]:
    """Rebuild and qualify one complete Task035e multilevel h/p plan."""

    from src.adaptivity.stage4_local_h import (
        stage4_multilevel_local_h_refinement_plan_payload,
    )
    from src.adaptivity.task035e_initial_space import (
        build_task035e_initial_space_plan,
    )
    from src.adaptivity.task035e_plan_transition import (
        build_next_solver_plan,
        canonical_solver_content_sha256,
        rebuild_hp_transition_state_from_solver_plan,
    )

    plan = payload if isinstance(payload, Mapping) else {}
    stage_rows = plan.get("refinement_stages")
    degree_rows = plan.get("cell_interior_degrees")
    rebuild_error = None
    rebuilt: Mapping[str, Any] | None = None
    degrees: list[int] = []
    try:
        if not isinstance(stage_rows, list):
            raise ValueError("refinement_stages must be an array")
        stages = []
        for stage in stage_rows:
            if not isinstance(stage, Mapping):
                raise ValueError("one refinement stage is not an object")
            marked = stage.get("marked_leaves")
            if not isinstance(marked, list):
                raise ValueError("one refinement stage lacks marked leaves")
            stages.append(
                tuple(
                    (
                        *tuple(float(value) for value in row["lower"]),
                        *tuple(float(value) for value in row["upper"]),
                    )
                    for row in marked
                )
            )
        if not isinstance(degree_rows, list) or not degree_rows:
            raise ValueError("cell_interior_degrees must be nonempty")
        overrides = {}
        for row in degree_rows:
            if not isinstance(row, Mapping):
                raise ValueError("one cell-degree row is not an object")
            box = (
                *tuple(round(float(value), 12) for value in row["lower"]),
                *tuple(round(float(value), 12) for value in row["upper"]),
            )
            if len(box) != 6 or box in overrides:
                raise ValueError("cell-degree leaf boxes are malformed or duplicated")
            degree = int(row["degree"])
            overrides[box] = degree
            degrees.append(degree)
        provenance = plan.get("provenance")
        if not isinstance(provenance, Mapping):
            raise ValueError("plan provenance must be an object")
        rebuilt = stage4_multilevel_local_h_refinement_plan_payload(
            config,
            stages,
            comm_size=TASK035E_BLIND_CANDIDATE_MPI_SIZE,
            trace_degree=int(plan.get("trace_degree", -1)),
            cell_interior_degree=int(
                plan.get("cell_interior_degree", -1)
            ),
            provenance=provenance,
            cell_interior_degree_overrides=overrides,
            variable_trace_from_cell_degrees=True,
        )
    except (KeyError, TypeError, ValueError) as exc:
        rebuild_error = str(exc)
    multilevel = plan.get("multilevel_audit")
    multilevel = multilevel if isinstance(multilevel, Mapping) else {}
    leaf_levels = multilevel.get("leaf_level_counts")
    leaf_levels = leaf_levels if isinstance(leaf_levels, Mapping) else {}
    expected_forest = plan.get("expected_forest")
    expected_forest = (
        expected_forest if isinstance(expected_forest, Mapping) else {}
    )
    provenance = plan.get("provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    provenance_schema = provenance.get("schema_version")
    output_role = str(expected_output_role or "")
    requested_cycle = expected_cycle_index
    expected_plan_cycle = (
        None
        if requested_cycle is None
        else requested_cycle
        if internal_probe_kind is not None
        else requested_cycle + (0 if output_role == "current" else 1)
    )
    initial_provenance = (
        output_role == "current"
        and expected_plan_cycle == 0
        and provenance_schema == TASK035E_BLIND_INITIAL_PROVENANCE_SCHEMA
        and provenance.get("cycle_index") is None
    )
    initial_rebuild_error = None
    deterministic_initial_plan: Mapping[str, Any] | None = None
    if output_role == "current" and expected_plan_cycle == 0:
        try:
            initial_path_id = (
                "A"
                if math.isclose(float(expected_h_nm), 20.0)
                else "B"
            )
            deterministic_initial_plan = (
                build_task035e_initial_space_plan(
                    config,
                    path_id=initial_path_id,
                    source_sha=str(expected_source_sha),
                    comm_size=TASK035E_BLIND_CANDIDATE_MPI_SIZE,
                ).plan_payload()
            )
        except (RuntimeError, TypeError, ValueError) as exc:
            initial_rebuild_error = str(exc)
    transition_provenance = (
        provenance_schema == TASK035E_BLIND_TRANSITION_PROVENANCE_SCHEMA
        and provenance.get("status")
        == "blind_solver_plan_transition_closed"
        and type(provenance.get("cycle_index")) is int
        and provenance.get("cycle_index") == expected_plan_cycle
    )
    provenance_unsigned = dict(provenance)
    if initial_provenance:
        stored_provenance_sha = provenance_unsigned.pop(
            "provenance_sha256",
            None,
        )
    else:
        stored_provenance_sha = provenance_unsigned.pop(
            "transition_provenance_sha256",
            None,
        )
    provenance_self_hash = (
        valid_hex_digest(stored_provenance_sha, 64)
        and _canonical_json_sha256(provenance_unsigned)
        == stored_provenance_sha
    )
    transition_kind = provenance.get("transition_action_kind")
    expected_transition_kind = {
        "p-shadow": "p-up",
        "h-shadow": "h-refine",
    }.get(output_role)
    current_plan_payload = (
        current_snapshot_binding.get("plan_payload")
        if isinstance(current_snapshot_binding, Mapping)
        else None
    )
    current_plan_identity = (
        current_snapshot_binding.get("plan_identity")
        if isinstance(current_snapshot_binding, Mapping)
        else None
    )
    action = (
        transition_action
        if isinstance(transition_action, Mapping)
        else {}
    )
    current_plan_payload = (
        current_plan_payload
        if isinstance(current_plan_payload, Mapping)
        else {}
    )
    current_plan_identity = (
        current_plan_identity
        if isinstance(current_plan_identity, Mapping)
        else {}
    )
    probe_same_plan = bool(
        internal_probe_kind in TASK035E_INTERNAL_PROBE_KINDS
        and output_role == "current"
        and requested_cycle is not None
        and current_snapshot_binding is not None
        and current_snapshot_binding.get("snapshot_cycle_index")
        == requested_cycle
        and bool(current_plan_payload)
        and current_plan_payload == plan
        and current_plan_identity.get("file_sha256")
        == expected_file_sha256
        and expected_file_sha256 == observed_file_sha256
        and current_plan_identity.get("forest_leaf_catalog_sha256")
        == expected_forest.get("leaf_catalog_sha256")
        and current_plan_identity.get("cell_degree_plan_sha256")
        == plan.get("cell_interior_degree_plan_sha256")
    )
    shadow_current_link = (
        initial_provenance
        or probe_same_plan
        or (
            bool(current_plan_payload)
            and provenance.get("previous_plan_content_sha256")
            == _canonical_json_sha256(current_plan_payload)
            and provenance.get(
                "previous_plan_canonical_solver_content_sha256"
            )
            == canonical_solver_content_sha256(current_plan_payload)
            and provenance.get("from_leaf_catalog_sha256")
            == current_plan_identity.get(
                "forest_leaf_catalog_sha256"
            )
            and provenance.get("from_cell_degree_plan_sha256")
            == current_plan_identity.get(
                "cell_degree_plan_sha256"
            )
        )
    )
    transition_rebuild_error = None
    replayed_transition_plan: Mapping[str, Any] | None = None
    if transition_provenance:
        try:
            previous_state = (
                rebuild_hp_transition_state_from_solver_plan(
                    config,
                    current_plan=current_plan_payload,
                    comm_size=TASK035E_BLIND_CANDIDATE_MPI_SIZE,
                )
            )
            replayed_transition_plan = build_next_solver_plan(
                config,
                current_plan=current_plan_payload,
                state=previous_state,
                action=action,
                comm_size=TASK035E_BLIND_CANDIDATE_MPI_SIZE,
            ).plan_payload
        except (KeyError, RuntimeError, TypeError, ValueError) as exc:
            transition_rebuild_error = str(exc)
    degree_counts = {
        f"p{degree}": sum(value == degree for value in degrees)
        for degree in (4, 5, 6)
    }
    checks = {
        "file_hash_expected_valid": valid_hex_digest(
            expected_file_sha256,
            64,
        ),
        "file_hash_observed_valid": valid_hex_digest(
            observed_file_sha256,
            64,
        ),
        "file_hash_matches_expected": (
            expected_file_sha256 == observed_file_sha256
        ),
        "schema_identity": (
            plan.get("schema_version")
            == TASK035E_BLIND_CANDIDATE_PLAN_SCHEMA
            and plan.get("status")
            == "stage4_balanced_multilevel_local_h_plan"
        ),
        "path_root_identity": (
            float(expected_h_nm) in TASK035E_BLIND_CANDIDATE_H_NM
            and isinstance(plan.get("base_config"), Mapping)
            and math.isclose(
                float(plan["base_config"].get("mesh_target_size", -1.0)),
                float(expected_h_nm),
            )
        ),
        "p6_container": (
            plan.get("cell_interior_degree") == 6
            and plan.get("trace_degree") == 4
        ),
        "cell_driven_variable_trace": (
            plan.get("variable_trace_from_cell_degrees") is True
            and not plan.get("selected_p6_face_geometry_keys")
        ),
        "complete_variable_p_leaf_inventory": (
            len(set(degrees)) >= 2
            and set(degrees).issubset({4, 5, 6})
            and len(degrees)
            == expected_forest.get("leaf_cell_count")
            and sum(degree_counts.values()) == len(degrees)
        ),
        "valid_incremental_multilevel_mesh": (
            plan.get("maximum_level") == 2
            and multilevel.get("actual_maximum_level") in {1, 2}
            and (
                (
                    multilevel.get("actual_maximum_level") == 1
                    and multilevel.get("true_multilevel") is False
                    and set(leaf_levels) == {"0", "1"}
                )
                or (
                    multilevel.get("actual_maximum_level") == 2
                    and multilevel.get("true_multilevel") is True
                    and set(leaf_levels) == {"0", "1", "2"}
                )
            )
            and all(
                isinstance(value, int) and value > 0
                for value in leaf_levels.values()
            )
            and multilevel.get("strong_2_to_1_balance") is True
            and multilevel.get("spatially_separated_user_patches") is True
        ),
        "periodic_material_contract": (
            plan.get("periodic_axes") == ["x", "y"]
            and plan.get("protect_material_interfaces") is True
        ),
        "ordinary_default_unchanged": (
            plan.get("ordinary_default_changed") is False
        ),
        "provenance_request_bound": (
            expected_source_sha is not None
            and requested_cycle is not None
            and output_role in {"current", "p-shadow", "h-shadow"}
            and provenance.get("source_sha") == expected_source_sha
            and (initial_provenance or transition_provenance)
        ),
        "deterministic_initial_plan_replayed": (
            expected_plan_cycle != 0
            or output_role != "current"
            or (
                initial_rebuild_error is None
                and deterministic_initial_plan == plan
                and plan.get("refinement_stage_count") == 1
                and multilevel.get("actual_maximum_level") == 1
                and degree_counts["p4"] > 0
                and degree_counts["p5"] > 0
                and degree_counts["p6"] == 0
            )
        ),
        "provenance_self_hash": provenance_self_hash,
        "transition_provenance_exact_fields": (
            initial_provenance
            or set(provenance)
            == TASK035E_TRANSITION_PROVENANCE_FIELDS
        ),
        "transition_action_bound": (
            initial_provenance
            or probe_same_plan
            or (
                transition_provenance
                and provenance.get("transition_action_cycle_index")
                == expected_plan_cycle
                and provenance.get("transition_action_source_sha")
                == expected_source_sha
                and valid_hex_digest(
                    provenance.get("transition_action_sha256"),
                    64,
                )
                and isinstance(
                    provenance.get("transition_action_id"),
                    str,
                )
                and bool(provenance.get("transition_action_id"))
                and (
                    expected_transition_kind is None
                    or transition_kind == expected_transition_kind
                )
                and bool(action)
                and provenance.get("transition_action_sha256")
                == action.get("action_sha256")
                and provenance.get("transition_action_id")
                == action.get("action_id")
                and provenance.get("transition_action_kind")
                == action.get("kind")
                and provenance.get("transition_action_cycle_index")
                == action.get("cycle_index")
                and provenance.get("transition_action_source_sha")
                == action.get("source_sha")
                and provenance.get("transition_action_target_ids")
                == action.get("canonical_target_ids")
                and provenance.get("from_state_sha256")
                == action.get("from_state_sha256")
            )
        ),
        "transition_next_plan_bound": (
            initial_provenance
            or probe_same_plan
            or (
                provenance.get("next_leaf_catalog_sha256")
                == expected_forest.get("leaf_catalog_sha256")
                and provenance.get("next_cell_degree_plan_sha256")
                == plan.get("cell_interior_degree_plan_sha256")
                and provenance.get("from_leaf_catalog_sha256")
                == action.get("from_leaf_catalog_sha256")
                and provenance.get("from_cell_degree_plan_sha256")
                == action.get("from_cell_degree_plan_sha256")
                and provenance.get(
                    "next_plan_canonical_solver_content_sha256"
                )
                == canonical_solver_content_sha256(plan)
            )
        ),
        "p_keep_solver_content_unchanged": (
            initial_provenance
            or probe_same_plan
            or transition_kind != "p-keep"
            or (
                output_role == "current"
                and bool(current_plan_payload)
                and provenance.get(
                    "previous_plan_canonical_solver_content_sha256"
                )
                == canonical_solver_content_sha256(current_plan_payload)
                and provenance.get(
                    "next_plan_canonical_solver_content_sha256"
                )
                == canonical_solver_content_sha256(plan)
                and canonical_solver_content_sha256(plan)
                == canonical_solver_content_sha256(current_plan_payload)
            )
        ),
        "shadow_current_plan_bound": shadow_current_link,
        "internal_probe_same_plan_snapshot_bound": (
            internal_probe_kind is None or probe_same_plan
        ),
        "transition_plan_replayed": (
            initial_provenance
            or probe_same_plan
            or (
                transition_rebuild_error is None
                and replayed_transition_plan == plan
            )
        ),
        "blind_inputs_not_embedded": (
            initial_provenance
            or probe_same_plan
            or (
                provenance.get("goal_values_embedded") is False
                and provenance.get("dwr_values_embedded") is False
                and provenance.get("evaluator_inputs_consumed") is False
                and provenance.get("ordinary_default_changed") is False
            )
        ),
        "canonical_rebuild_exact": (
            rebuild_error is None and rebuilt == plan
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": (
            "task035e.blind-multilevel-plan-authority-gate.v1"
        ),
        "pass": not failures,
        "role": "blind_candidate_multilevel_hp_plan_only",
        "path_id": (
            "path_a"
            if math.isclose(float(expected_h_nm), 20.0)
            else "path_b"
        ),
        "expected_file_sha256": expected_file_sha256,
        "observed_file_sha256": observed_file_sha256,
        "degree_counts": degree_counts,
        "leaf_cell_count": expected_forest.get("leaf_cell_count"),
        "base_config_identity_sha256": (
            plan.get("base_config", {}).get("identity_sha256")
            if isinstance(plan.get("base_config"), Mapping)
            else None
        ),
        "provenance": {
            "schema_version": provenance_schema,
            "source_sha": provenance.get("source_sha"),
            "requested_cycle_index": requested_cycle,
            "expected_plan_cycle_index": expected_plan_cycle,
            "observed_plan_cycle_index": provenance.get("cycle_index"),
            "output_role": output_role,
            "internal_probe_kind": internal_probe_kind,
            "transition_action_kind": transition_kind,
            "transition_action_sha256": provenance.get(
                "transition_action_sha256"
            ),
        },
        "rebuild_error": rebuild_error,
        "initial_rebuild_error": initial_rebuild_error,
        "transition_rebuild_error": transition_rebuild_error,
        "checks": checks,
        "failures": failures,
    }


def _read_int_or_max(path: Path) -> tuple[int | None, str]:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None, "unreadable"
    if text == "max":
        return None, "unbounded"
    try:
        return int(text), "finite"
    except ValueError:
        return None, "unreadable"


def _read_int(path: Path) -> int | None:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def _host_available_bytes() -> int | None:
    try:
        lines = Path("/proc/meminfo").read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        if line.startswith("MemAvailable:"):
            try:
                return int(line.split()[1]) * 1024
            except (IndexError, ValueError):
                return None
    return None


def _resource_snapshot() -> dict[str, Any]:
    cgroup = cgroup_snapshot()
    memory = effective_memory_limit()
    swap = vmstat_swap_pages()
    memory_max = cgroup.get("memory_limit_bytes")
    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "cgroup_path": cgroup.get("path"),
        "cgroup_is_dedicated_job_authority": cgroup.get("dedicated_job_cgroup", False),
        "cgroup_memory_max_bytes": memory_max,
        "cgroup_memory_max_state": (
            "finite" if isinstance(memory_max, int) else "unbounded_or_unreadable"
        ),
        "cgroup_swap_max_bytes": None,
        "cgroup_swap_max_state": "not_used_as_limit",
        "cgroup_memory_current_bytes": cgroup.get("memory_current_bytes"),
        "cgroup_swap_current_bytes": cgroup.get("swap_current_bytes"),
        "host_available_bytes": memory.get("mem_available_bytes"),
        "wsl_total_bytes": memory.get("mem_total_bytes"),
        "task034_effective_limit": memory,
        "wsl_vm_global_swap_diagnostic": swap,
    }


def _sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _finite_number_le(value: Any, limit: float) -> bool:
    return bool(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
        and 0.0 <= float(value) <= float(limit)
    )


def _task035d_selective_face_controlled_negative(
    payload: Any,
    *,
    report_sha256: str | None,
) -> bool:
    if not isinstance(payload, Mapping):
        return False
    negative_statuses = {
        "controlled_negative_cross_trace_galerkin_failure",
        "controlled_negative_enriched_primal_residual",
        "controlled_negative_unit_adjoint_exception",
        "controlled_negative_unit_adjoint_incomplete",
        "selective_face_cross_trace_live_dwr_fail",
    }
    status = payload.get("status")
    identity = payload.get("identity_checks")
    endpoint_authorities = payload.get("endpoint_identity_authorities")
    endpoint_fields = {
        "source_sha",
        "mesh_sha256",
        "normalized_config_sha256",
        "ordered_modes_sha256",
        "cell_interior_degree_sha256",
        "incident_projections_sha256",
        "auxiliary_coordinate_scales_sha256",
    }
    coarse_endpoint = (
        endpoint_authorities.get("coarse")
        if isinstance(endpoint_authorities, Mapping)
        else None
    )
    enriched_endpoint = (
        endpoint_authorities.get("enriched")
        if isinstance(endpoint_authorities, Mapping)
        else None
    )
    transfer = payload.get("root_transfer")
    galerkin = payload.get("galerkin_audit")
    common_evidence = bool(
        valid_hex_digest(report_sha256, 64)
        and payload.get("schema_version")
        == "task035d.selective-face-cross-trace-dwr.v1"
        and payload.get("pass") is False
        and payload.get("controlled_negative") is True
        and payload.get("ordinary_default_changed") is False
        and status in negative_statuses
        and isinstance(identity, Mapping)
        and set(identity)
        == {
            "same_source_sha",
            "same_mesh",
            "same_normalized_config",
            "same_ordered_modes",
            "same_cell_interior_degree_map",
            "same_incident_projections",
            "same_auxiliary_coordinate_scales",
        }
        and all(value is True for value in identity.values())
        and isinstance(endpoint_authorities, Mapping)
        and endpoint_authorities.get("schema_version")
        == "task035d.selective-face-endpoint-identities.v1"
        and isinstance(coarse_endpoint, Mapping)
        and isinstance(enriched_endpoint, Mapping)
        and set(coarse_endpoint) == endpoint_fields
        and set(enriched_endpoint) == endpoint_fields
        and coarse_endpoint == enriched_endpoint
        and valid_hex_digest(coarse_endpoint.get("source_sha"), 40)
        and all(
            valid_hex_digest(coarse_endpoint.get(name), 64)
            for name in endpoint_fields - {"source_sha"}
        )
        and isinstance(transfer, Mapping)
        and transfer.get("schema_version")
        in {
            "task035d.selective-face-physical-root-transfer.v1",
            "task035d.selective-face-physical-root-transfer.v2",
        }
        and transfer.get("pass") is True
        and isinstance(galerkin, Mapping)
        and galerkin.get("schema_version")
        == "task035d.selective-face-cross-trace-galerkin-audit.v1"
    )
    if not common_evidence:
        return False
    if status == "controlled_negative_cross_trace_galerkin_failure":
        return bool(
            payload.get("failure_stage") == "cross_trace_galerkin_before_adjoints"
            and galerkin.get("pass") is False
        )
    if status == "controlled_negative_enriched_primal_residual":
        residual = payload.get("enriched_primal_residual_gate")
        return bool(
            payload.get("failure_stage") == "enriched_primal_residual_before_adjoints"
            and galerkin.get("pass") is True
            and isinstance(residual, Mapping)
            and residual.get("schema_version") == "task035d.primal-residual-gate.v1"
            and residual.get("pass") is False
        )
    if status == "controlled_negative_unit_adjoint_exception":
        residual = payload.get("enriched_primal_residual_gate")
        errors = payload.get("errors")
        completed = payload.get("completed_unit_channel_pairing_count")
        return bool(
            payload.get("failure_stage") == "unit_channel_adjoint_basis"
            and galerkin.get("pass") is True
            and isinstance(residual, Mapping)
            and residual.get("schema_version") == "task035d.primal-residual-gate.v1"
            and residual.get("pass") is True
            and isinstance(errors, list)
            and bool(errors)
            and all(
                isinstance(row, Mapping)
                and isinstance(row.get("rank"), int)
                and isinstance(row.get("exception_type"), str)
                and isinstance(row.get("message"), str)
                for row in errors
            )
            and isinstance(completed, int)
            and not isinstance(completed, bool)
            and 0 <= completed <= 12
        )
    if status == "controlled_negative_unit_adjoint_incomplete":
        residual = payload.get("enriched_primal_residual_gate")
        basis = payload.get("unit_channel_adjoint_basis")
        observed = payload.get("observed_unit_pairing_labels")
        expected = payload.get("expected_unit_pairing_labels")
        return bool(
            payload.get("failure_stage") == "unit_channel_adjoint_basis_gate"
            and galerkin.get("pass") is True
            and isinstance(residual, Mapping)
            and residual.get("schema_version") == "task035d.primal-residual-gate.v1"
            and residual.get("pass") is True
            and isinstance(basis, Mapping)
            and basis.get("schema_version")
            == "task035d.actual-dtn-unit-channel-adjoint-basis.v2"
            and isinstance(observed, list)
            and isinstance(expected, list)
            and len(expected) == 12
        )
    primal = payload.get("primal_endpoints")
    basis = payload.get("unit_channel_adjoint_basis")
    goals = payload.get("goal_dwr")
    marking = payload.get("selected_face_multigoal_marking")
    return bool(
        status == "selective_face_cross_trace_live_dwr_fail"
        and payload.get("canonical") is False
        and payload.get("production_qualified") is False
        and payload.get("same_trace_only") is False
        and payload.get("actual_cross_trace_primal_prolongation_used") is True
        and isinstance(payload.get("coarse_snapshot"), Mapping)
        and isinstance(payload.get("enriched_candidate"), Mapping)
        and galerkin.get("pass") is True
        and isinstance(primal, Mapping)
        and isinstance(primal.get("coarse_residual_gate"), Mapping)
        and primal["coarse_residual_gate"].get("pass") is True
        and isinstance(primal.get("enriched_residual_gate"), Mapping)
        and primal["enriched_residual_gate"].get("pass") is True
        and isinstance(payload.get("significant_channel_authority"), Mapping)
        and isinstance(basis, Mapping)
        and basis.get("schema_version")
        == "task035d.actual-dtn-unit-channel-adjoint-basis.v2"
        and basis.get("pass") is True
        and isinstance(goals, Mapping)
        and goals.get("schema_version") == "task035d.selective-face-live-36-goal-dwr.v1"
        and goals.get("pass") is False
        and goals.get("requested_real_goal_count") == 36
        and isinstance(goals.get("goals"), Mapping)
        and len(goals["goals"]) == 36
        and isinstance(marking, Mapping)
        and marking.get("face_count") == 10
        and isinstance(marking.get("ranked_faces"), list)
        and len(marking["ranked_faces"]) == 10
        and isinstance(payload.get("formal_boundary"), Mapping)
    )


def _path_from_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def _full3d_config(args: argparse.Namespace):
    from src.common.config_3d import target_stage4_config

    cfg = target_stage4_config(degree=args.degree, h_nm=args.h_nm)
    full_solve = args.run_kind == "full-solve"
    factorization_only = args.run_kind == "factorization-only"
    probe_kind = args.task035e_internal_probe_kind
    return replace(
        cfg,
        polarization_kind=args.polarization_kind,
        custom_polarization=None,
        stage4_full3d_assembly_backend=(args.stage4_full3d_assembly_backend),
        stage4_dtn_order_policy=(
            "manual" if probe_kind == "dtn" else cfg.stage4_dtn_order_policy
        ),
        diffraction_order_max_m=(
            args.task035e_probe_dtn_max_m
            if probe_kind == "dtn"
            else cfg.diffraction_order_max_m
        ),
        diffraction_order_max_n=(
            args.task035e_probe_dtn_max_n
            if probe_kind == "dtn"
            else cfg.diffraction_order_max_n
        ),
        stage4_dtn_quadrature_degree=(
            args.task035e_probe_surface_quadrature_degree
            if probe_kind == "postprocess"
            else cfg.stage4_dtn_quadrature_degree
        ),
        stage4_raw_tensor_cache_directory=(
            str(args.stage4_raw_tensor_cache_directory)
            if args.stage4_raw_tensor_cache
            else None
        ),
        stage4_raw_tensor_cache_namespace=(
            f"git-{args.verified_clean_sha}"
            if args.stage4_raw_tensor_cache
            else None
        ),
        stage4_variable_p_cell_degree_plan=(
            None
            if args.stage4_variable_p_cell_degree_plan is None
            else str(args.stage4_variable_p_cell_degree_plan)
        ),
        stage4_local_h_refinement_plan=(
            None
            if args.stage4_local_h_refinement_plan is None
            else str(args.stage4_local_h_refinement_plan)
        ),
        direct_release_base_after_augmentation=bool(args.task035d_case097_gate),
        direct_release_solver_before_postprocess=bool(args.task035d_case097_gate),
        petsc_direct_solver_profile=args.profile,
        petsc_extra_options={
            **cfg.petsc_extra_options,
            **({"mat_mumps_icntl_14": 100} if args.task035d_case097_gate else {}),
        },
        matrix_diagnostics_assemble_only=args.run_kind == "assembly-only",
        matrix_diagnostics_factorization_only=factorization_only,
        stage4_static_condensed_resource_only_assembly=bool(
            args.task035e_reference_certifier_gate
            and args.run_kind == "assembly-only"
        ),
        full3d_reference_export=full_solve,
        full3d_reference_plane_z=REFERENCE_PLANES_NM if full_solve else (),
        full3d_reference_sample_count_x=40,
        full3d_reference_sample_count_y=20,
        unique_output=False,
    )


def _worker_launch_contract(args: argparse.Namespace) -> dict[str, Any]:
    task035e_config = _task035e_reference_config_authority(args)
    return {
        "degree": int(args.degree),
        "h_nm": float(args.h_nm),
        "polarization_kind": str(args.polarization_kind),
        "run_kind": str(args.run_kind),
        "mpi_size": int(args.mpi_size),
        "profile": str(args.profile),
        "run_dir": str(Path(args.run_dir).resolve()),
        "stage4_full3d_assembly_backend": str(args.stage4_full3d_assembly_backend),
        "stage4_raw_tensor_cache": bool(args.stage4_raw_tensor_cache),
        "stage4_raw_tensor_cache_directory": (
            None
            if args.stage4_raw_tensor_cache_directory is None
            else str(args.stage4_raw_tensor_cache_directory)
        ),
        "stage4_raw_tensor_cache_namespace": (
            f"git-{args.verified_clean_sha}"
            if args.stage4_raw_tensor_cache
            else None
        ),
        "task035d_case097_gate": bool(args.task035d_case097_gate),
        "task035d_candidate_id": str(args.task035d_candidate_id),
        "task035d_nested_p_dwr_phase": args.task035d_nested_p_dwr_phase,
        "task035d_selective_face_dwr_phase": (args.task035d_selective_face_dwr_phase),
        "task035d_plan_authority_sha256": (args.task035d_plan_authority_sha256),
        "task035d_significant_channel_authority_sha256": (
            args.task035d_significant_channel_authority_sha256
        ),
        "task035d_coarse_snapshot_manifest_sha256": (
            args.task035d_coarse_snapshot_manifest_sha256
        ),
        "task035d_selective_face_coarse_manifest_sha256": (
            args.task035d_selective_face_coarse_manifest_sha256
        ),
        "task035e_reference_certifier_gate": bool(
            args.task035e_reference_certifier_gate
        ),
        "task035e_reference_config_authority_sha256": (
            None if task035e_config is None else task035e_config["sha256"]
        ),
        "task035e_reference_resource_authority_sha256": (
            args.task035e_reference_resource_authority_sha256
        ),
        "task035e_h5_factorization_authority_sha256": (
            args.task035e_h5_factorization_authority_sha256
        ),
        "task035e_blind_candidate_gate": bool(
            args.task035e_blind_candidate_gate
        ),
        "task035e_internal_probe": _task035e_internal_probe_authority(args),
        "task035e_blind_trial_id": args.task035e_blind_trial_id,
        "task035e_blind_cycle_index": args.task035e_blind_cycle_index,
        "task035e_blind_output_role": args.task035e_blind_output_role,
        "task035e_blind_plan_sha256": (
            args.stage4_local_h_refinement_plan_sha256
            if args.task035e_blind_candidate_gate
            else None
        ),
        "task035e_current_snapshot_manifest_sha256": (
            args.task035e_current_snapshot_manifest_sha256
            if args.task035e_blind_candidate_gate
            else None
        ),
        "task035e_transition_action_sha256": (
            args.task035e_transition_action_sha256
            if args.task035e_blind_candidate_gate
            else None
        ),
        "task035e_dynamic_termination_bytes": (
            None
            if not (
                args.task035e_reference_certifier_gate
                or args.task035e_blind_candidate_gate
            )
            or args.terminate_gib is None
            else int(round(float(args.terminate_gib) * GIB))
        ),
        "verified_clean_sha": args.verified_clean_sha,
    }


def _linux_process_identity(pid: int) -> dict[str, int]:
    try:
        stat = Path(f"/proc/{int(pid)}/stat").read_text(encoding="utf-8")
        suffix = stat[stat.rindex(")") + 2 :].split()
        return {
            "pid": int(pid),
            "parent_pid": int(suffix[1]),
            "start_time_ticks": int(suffix[19]),
        }
    except (IndexError, OSError, TypeError, ValueError) as exc:
        raise RuntimeError(
            f"Linux process identity is unreadable for pid {pid}: {exc}"
        ) from exc


def _linux_process_ancestor_pids(pid: int) -> set[int]:
    ancestors: set[int] = set()
    cursor = int(pid)
    for _ in range(128):
        identity = _linux_process_identity(cursor)
        parent = identity["parent_pid"]
        if parent <= 0 or parent == cursor:
            break
        if parent in ancestors:
            raise RuntimeError("Linux process ancestry contains a cycle")
        ancestors.add(parent)
        cursor = parent
    return ancestors


def _validate_worker_parent_launch(args: argparse.Namespace) -> None:
    descriptor_path = args.parent_launch_descriptor
    expected_sha = args.parent_launch_descriptor_sha256
    token = os.environ.get(_PARENT_LAUNCH_TOKEN_ENV)
    if (
        descriptor_path is None
        or not valid_hex_digest(expected_sha, 64)
        or not isinstance(token, str)
        or len(token) < 32
    ):
        raise SystemExit(
            "--worker is internal to the resource watchdog and requires "
            "one process-bound parent launch lease."
        )
    descriptor_path = descriptor_path.resolve()
    run_dir = Path(args.run_dir).resolve()
    if (
        descriptor_path.parent != run_dir
        or descriptor_path.name != "parent_launch_descriptor.json"
        or _sha256(descriptor_path) != expected_sha
    ):
        raise SystemExit("worker parent-launch descriptor identity failed.")
    try:
        payload = json.loads(descriptor_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"worker parent-launch descriptor is unreadable: {exc}"
        ) from exc
    token_sha256 = hashlib.sha256(token.encode("ascii")).hexdigest()
    parent_process = (
        payload.get("parent_process") if isinstance(payload, Mapping) else None
    )
    try:
        parent_identity = (
            _linux_process_identity(int(parent_process["pid"]))
            if isinstance(parent_process, Mapping)
            else {}
        )
        ancestors = _linux_process_ancestor_pids(os.getpid())
    except (KeyError, RuntimeError, TypeError, ValueError) as exc:
        raise SystemExit(f"worker parent-launch process lease failed: {exc}") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema_version") != "task033.watchdog-parent-launch.v1"
        or payload.get("token_sha256") != token_sha256
        or payload.get("worker_contract") != _worker_launch_contract(args)
        or not isinstance(parent_process, Mapping)
        or parent_process.get("role") != "resource_watchdog_parent"
        or parent_process.get("pid") not in ancestors
        or parent_identity.get("start_time_ticks")
        != parent_process.get("start_time_ticks")
    ):
        raise SystemExit("worker parent-launch descriptor contract failed.")


def _revalidate_task035d_worker_inputs(args: argparse.Namespace) -> None:
    if not args.task035d_case097_gate:
        return
    _validate_task035d_case097_plan(args)
    _validate_task035d_nested_p_inputs(args)
    _validate_task035d_selective_face_inputs(args)
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
    ).strip()
    if head != args.verified_clean_sha or status:
        raise SystemExit(
            "Task035d worker source identity is not the clean parent-qualified commit."
        )


def _revalidate_task035e_worker_inputs(args: argparse.Namespace) -> None:
    if not (
        args.task035e_reference_certifier_gate
        or args.task035e_blind_candidate_gate
    ):
        return
    if args.task035e_reference_certifier_gate:
        _validate_task035e_reference_resource_authority(args)
        _validate_task035e_h5_factorization_authority(args)
    else:
        _validate_task035e_blind_candidate_plan(args)
        _validate_task035e_current_snapshot_input(args)
        configured_cap = (
            None
            if args.terminate_gib is None
            else int(round(float(args.terminate_gib) * GIB))
        )
        if (
            not isinstance(configured_cap, int)
            or configured_cap <= 0
            or configured_cap
            > TASK035E_BLIND_CANDIDATE_MEMORY_CAP_BYTES
        ):
            raise SystemExit(
                "Task035e blind worker dynamic cap is absent or exceeds "
                "11 GiB."
            )
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
    ).strip()
    status = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
    ).strip()
    if head != args.verified_clean_sha or status:
        raise SystemExit(
            "Task035e formal worker source identity is not the actually clean "
            "parent-qualified commit."
        )


def _worker(args: argparse.Namespace) -> int:
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import (
        run_stage4b_block_grating_3d_case,
    )

    observer = None
    retain_local_schur = False
    if (
        args.task035e_blind_candidate_gate
        and args.task035e_internal_probe_kind != "serial_mpi1"
    ):
        common = {
            "source_sha": args.verified_clean_sha,
            "trial_id": args.task035e_blind_trial_id,
            "cycle_index": args.task035e_blind_cycle_index,
        }
        if args.task035e_blind_output_role == "current":
            from src.adaptivity.task035e_multigoal_snapshot import (
                build_task035e_multigoal_snapshot_observer,
            )

            observer = build_task035e_multigoal_snapshot_observer(
                artifact_directory=(
                    args.run_dir / "task035e_current_snapshot"
                ),
                expected_plan_sha256=(
                    args.stage4_local_h_refinement_plan_sha256
                ),
                **common,
            )
        else:
            from src.adaptivity.task035e_shadow_observer import (
                build_task035e_shadow_evaluation_observer,
            )

            role = str(args.task035e_blind_output_role)
            observer = build_task035e_shadow_evaluation_observer(
                current_snapshot_manifest=(
                    args.task035e_current_snapshot_manifest
                ),
                current_snapshot_manifest_sha256=(
                    args.task035e_current_snapshot_manifest_sha256
                ),
                artifact_path=(
                    args.run_dir
                    / f"task035e_{role.replace('-', '_')}_evaluation.json"
                ),
                expected_shadow_plan_sha256=(
                    args.stage4_local_h_refinement_plan_sha256
                ),
                shadow_kind=role,
                **common,
            )
    elif args.task035d_nested_p_dwr_phase is not None:
        from src.adaptivity.variable_p_nested_dwr import (
            build_variable_p_nested_coarse_snapshot_observer,
            build_variable_p_nested_enriched_evaluator_observer,
        )

        common = {
            "candidate_id": args.task035d_candidate_id,
            "expected_plan_sha256": (args.stage4_local_h_refinement_plan_sha256),
            "source_sha": args.verified_clean_sha,
            "significant_channel_authority_path": (
                args.task035d_significant_channel_authority
            ),
            "significant_channel_authority_sha256": (
                args.task035d_significant_channel_authority_sha256
            ),
        }
        if args.task035d_nested_p_dwr_phase == "coarse-snapshot":
            observer = build_variable_p_nested_coarse_snapshot_observer(
                artifact_directory=(args.run_dir / "nested_p_snapshot"),
                **common,
            )
        else:
            observer = build_variable_p_nested_enriched_evaluator_observer(
                coarse_manifest_path=(args.task035d_coarse_snapshot_manifest),
                coarse_manifest_sha256=(args.task035d_coarse_snapshot_manifest_sha256),
                artifact_path=(args.run_dir / "nested_p_dwr_report.json"),
                **common,
            )
        retain_local_schur = True
    elif args.task035d_selective_face_dwr_phase is not None:
        from src.adaptivity.variable_p_selective_face_dwr import (
            build_selective_face_coarse_snapshot_observer,
            build_selective_face_enriched_evaluator_observer,
        )

        common = {
            "candidate_id": args.task035d_candidate_id,
            "expected_plan_sha256": (args.stage4_local_h_refinement_plan_sha256),
            "source_sha": args.verified_clean_sha,
            "significant_channel_authority_path": (
                args.task035d_significant_channel_authority
            ),
            "significant_channel_authority_sha256": (
                args.task035d_significant_channel_authority_sha256
            ),
        }
        if args.task035d_selective_face_dwr_phase == "coarse-snapshot":
            observer = build_selective_face_coarse_snapshot_observer(
                artifact_directory=(args.run_dir / "selective_face_snapshot"),
                **common,
            )
        else:
            observer = build_selective_face_enriched_evaluator_observer(
                coarse_manifest_path=(args.task035d_selective_face_coarse_manifest),
                coarse_manifest_sha256=(
                    args.task035d_selective_face_coarse_manifest_sha256
                ),
                artifact_path=(args.run_dir / "selective_face_dwr_report.json"),
                **common,
            )
    run_stage4b_block_grating_3d_case(
        _full3d_config(args),
        args.run_dir,
        variable_p_live_observer=observer,
        variable_p_retain_local_schur_for_research=(retain_local_schur),
    )
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Task33/34 p2/p3/p4 target full3D assembly calibration and "
            "controlled direct-reference watchdog."
        )
    )
    parser.add_argument("--degree", type=int, choices=(2, 3, 4, 6), required=True)
    parser.add_argument(
        "--h-nm",
        type=float,
        choices=(20.0, 15.0, 10.0, 7.5, 5.0, 3.0, 2.0, 1.0),
        default=5.0,
    )
    parser.add_argument(
        "--polarization-kind",
        choices=("s", "p"),
        default="s",
    )
    parser.add_argument(
        "--run-kind",
        choices=("assembly-only", "factorization-only", "full-solve"),
        default="assembly-only",
    )
    parser.add_argument("--mpi-size", type=int, default=4)
    parser.add_argument(
        "--profile",
        choices=("default", "mumps_ooc", "mumps_blr"),
        default="default",
    )
    parser.add_argument(
        "--stage4-full3d-assembly-backend",
        choices=(
            "standard_full",
            "assembly_time_static_condensed",
            TASK035D_CASE097_BACKEND,
        ),
        default="standard_full",
    )
    parser.add_argument(
        "--stage4-raw-tensor-cache",
        action="store_true",
        help=(
            "Explicitly enable the SHA/ABI-bound, write-once persistent raw "
            "cell-tensor cache for a qualified Task035e assembly-time run."
        ),
    )
    parser.add_argument(
        "--stage4-raw-tensor-cache-directory",
        type=Path,
        help=(
            "Optional absolute Linux cache path. With "
            "--stage4-raw-tensor-cache omitted, this option is rejected. "
            "The default is a shared cache below --artifact-root."
        ),
    )
    parser.add_argument("--stage4-variable-p-cell-degree-plan", type=Path)
    parser.add_argument("--stage4-variable-p-cell-degree-plan-sha256")
    parser.add_argument("--stage4-local-h-refinement-plan", type=Path)
    parser.add_argument("--stage4-local-h-refinement-plan-sha256")
    parser.add_argument(
        "--task035c-p6-h10-gate",
        action="store_true",
        help=(
            "Explicitly open only the Task035c fixed-rectangular p6/h10 "
            "Full3D authority path. Ordinary p2/p3/p4 behavior is unchanged."
        ),
    )
    parser.add_argument("--task035c-p6-preflight-authority", type=Path)
    parser.add_argument("--task035c-p6-preflight-sha256")
    parser.add_argument(
        "--task035e-reference-certifier-gate",
        action="store_true",
        help=(
            "Explicitly open only the Task035e fixed-rectangular p6 "
            "h10/h7.5/h5 MPI8 static-condensed reference-certifier path. "
            "Ordinary behavior remains unchanged."
        ),
    )
    parser.add_argument(
        "--task035e-reference-resource-authority",
        type=Path,
        help=(
            "Hash-bound Task035e assembly-only resource authority required "
            "before a reference-certifier full solve."
        ),
    )
    parser.add_argument("--task035e-reference-resource-authority-sha256")
    parser.add_argument(
        "--task035e-h5-factorization-authority",
        type=Path,
        help=(
            "Short-lived self-hashed ALLOW authority additionally required "
            "before the Task035e p6/h5 full solve enters MUMPS."
        ),
    )
    parser.add_argument("--task035e-h5-factorization-authority-sha256")
    parser.add_argument(
        "--task035e-blind-candidate-gate",
        action="store_true",
        help=(
            "Explicitly open one Task035e Path A h20 or Path B h15 "
            "multilevel local-h/p blind current solve. This path cannot "
            "consume reference or hidden-auditor evidence."
        ),
    )
    parser.add_argument(
        "--task035e-internal-probe-kind",
        choices=tuple(sorted(TASK035E_INTERNAL_PROBE_KINDS)),
        help=(
            "Narrow Task035e same-plan internal-budget probe. Algebraic, DtN "
            "and postprocess probes remain MPI8; serial_mpi1 is the only "
            "permitted MPI1 diagnostic."
        ),
    )
    parser.add_argument("--task035e-probe-dtn-max-m", type=int)
    parser.add_argument("--task035e-probe-dtn-max-n", type=int)
    parser.add_argument(
        "--task035e-probe-surface-quadrature-degree",
        type=int,
    )
    parser.add_argument("--task035e-blind-trial-id")
    parser.add_argument("--task035e-blind-cycle-index", type=int)
    parser.add_argument(
        "--task035e-blind-output-role",
        choices=("current", "p-shadow", "h-shadow"),
        help=(
            "Closed role of the Task035e blind solve. Shadow records cannot "
            "be adapted or frozen as current-candidate output."
        ),
    )
    parser.add_argument(
        "--task035e-current-snapshot-manifest",
        type=Path,
        help=(
            "Immutable MPI8 prior/current-state snapshot required by every "
            "Task035e transition solve: the previous cycle for current, or "
            "the same cycle for p-shadow/h-shadow."
        ),
    )
    parser.add_argument(
        "--task035e-current-snapshot-manifest-sha256",
        help=(
            "Expected byte SHA-256 of the Task035e current snapshot "
            "manifest."
        ),
    )
    parser.add_argument(
        "--task035e-transition-action",
        type=Path,
        help=(
            "Immutable blind-controller h/p transition action required by "
            "every non-initial Task035e current or shadow plan."
        ),
    )
    parser.add_argument(
        "--task035e-transition-action-sha256",
        help="Expected byte SHA-256 of the Task035e transition action.",
    )
    parser.add_argument(
        "--task035d-case097-gate",
        action="store_true",
        help=(
            "Explicitly open one frozen Task035d Case097 variable-p or "
            "balanced local-h MPI8 candidate. This grants no physical "
            "accuracy credit."
        ),
    )
    parser.add_argument(
        "--task035d-candidate-id",
        choices=(
            "t30",
            "sidewall_z0_guard_v1",
            TASK035D_LOCAL_H_PLAN_NAME,
            TASK035D_COMBINED_HP_PLAN_NAME,
            TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME,
            TASK035D_LEFT_GRATING_TOP_PLAN_NAME,
            TASK035D_SELECTIVE_FACE_PLAN_NAME,
        ),
        default="t30",
    )
    parser.add_argument("--task035d-plan-authority", type=Path)
    parser.add_argument("--task035d-plan-authority-sha256")
    parser.add_argument(
        "--task035d-nested-p-dwr-phase",
        choices=tuple(sorted(TASK035D_NESTED_P_PHASES)),
        help=(
            "Explicitly add the same-trace nested-p coarse snapshot or "
            "enriched DWR live observer to one qualified Case097 MPI8 run."
        ),
    )
    parser.add_argument(
        "--task035d-selective-face-dwr-phase",
        choices=tuple(sorted(TASK035D_SELECTIVE_FACE_PHASES)),
        help=(
            "Explicitly add the true cross-trace selective-face coarse "
            "snapshot or enriched DWR observer to one qualified MPI8 run."
        ),
    )
    parser.add_argument(
        "--task035d-significant-channel-authority",
        type=Path,
    )
    parser.add_argument(
        "--task035d-significant-channel-authority-sha256",
    )
    parser.add_argument(
        "--task035d-nested-p-pair-authority",
        type=Path,
    )
    parser.add_argument(
        "--task035d-nested-p-pair-authority-sha256",
    )
    parser.add_argument(
        "--task035d-coarse-snapshot-manifest",
        type=Path,
    )
    parser.add_argument(
        "--task035d-coarse-snapshot-manifest-sha256",
    )
    parser.add_argument(
        "--task035d-selective-face-coarse-manifest",
        type=Path,
    )
    parser.add_argument(
        "--task035d-selective-face-coarse-manifest-sha256",
    )
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    parser.add_argument("--run-dir", type=Path)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--poll-interval", type=float, default=0.25)
    parser.add_argument("--warning-gib", type=float)
    parser.add_argument("--terminate-gib", type=float)
    parser.add_argument("--timeout-seconds", type=float, default=7200.0)
    parser.add_argument(
        "--allow-swap",
        action="store_true",
        help=(
            "Permit a full solve to use cgroup swap. The combined memory+swap "
            "authority remains bounded by --terminate-gib."
        ),
    )
    parser.add_argument(
        "--p3-gate-record",
        type=Path,
        help=(
            "Required for degree 4. Must prove a successful p3/h5 full solve "
            "with zero swap and memory authority below 10 GiB."
        ),
    )
    parser.add_argument(
        "--p4-trace-record",
        type=Path,
        help=(
            "Required for degree 4. Must be the passing MPI1/MPI4 p4 "
            "four-mode matched-trace aggregate."
        ),
    )
    parser.add_argument(
        "--task034-p4-h3-added-point",
        action="store_true",
        help=(
            "Explicit Task034 user-added p4/h3 path. It retains the same-h "
            "p3 full-solve and current-SHA p4 trace prerequisites, but uses "
            "the live Task034 warning threshold instead of Task033's fixed "
            "10 GiB p3 cap."
        ),
    )
    parser.add_argument(
        "--verified-clean-sha",
        default=os.environ.get("TASK033_VERIFIED_CLEAN_SHA"),
    )
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--parent-launch-descriptor", type=Path)
    parser.add_argument("--parent-launch-descriptor-sha256")
    args = parser.parse_args(argv)
    if args.stage4_raw_tensor_cache:
        if not (
            args.task035e_reference_certifier_gate
            or args.task035e_blind_candidate_gate
        ):
            parser.error(
                "--stage4-raw-tensor-cache is restricted to one explicitly "
                "qualified Task035e reference or blind-candidate run."
            )
        if not valid_hex_digest(args.verified_clean_sha, 40):
            parser.error(
                "--stage4-raw-tensor-cache requires --verified-clean-sha; "
                "the cache namespace is bound to that clean source identity."
            )
        cache_directory = (
            args.stage4_raw_tensor_cache_directory
            if args.stage4_raw_tensor_cache_directory is not None
            else args.artifact_root / "task035e_raw_tensor_cache"
        ).expanduser()
        if not cache_directory.is_absolute():
            cache_directory = (ROOT / cache_directory).resolve()
        else:
            cache_directory = cache_directory.resolve()
        cache_text = cache_directory.as_posix()
        if cache_text == "/mnt" or cache_text.startswith("/mnt/"):
            parser.error(
                "--stage4-raw-tensor-cache-directory must be on the WSL "
                "Linux filesystem, never /mnt/c or another /mnt mount."
            )
        args.stage4_raw_tensor_cache_directory = cache_directory
    elif args.stage4_raw_tensor_cache_directory is not None:
        parser.error(
            "--stage4-raw-tensor-cache-directory requires the explicit "
            "--stage4-raw-tensor-cache opt-in."
        )
    allowed_h_by_degree = {
        2: {5.0, 3.0, 2.0, 1.0},
        3: {10.0, 7.5, 5.0, 3.0, 2.0},
        4: {10.0, 7.5, 5.0, 3.0},
        6: {15.0, 10.0, 7.5, 5.0},
    }
    task035e_blind_h20 = bool(
        args.task035e_blind_candidate_gate
        and args.degree == 6
        and math.isclose(args.h_nm, 20.0)
    )
    if (
        args.h_nm not in allowed_h_by_degree[args.degree]
        and not task035e_blind_h20
    ):
        parser.error(
            f"Task034 p{args.degree}/h{args.h_nm:g} is outside the "
            "fixed-geometry candidate matrix."
        )
    if args.task034_p4_h3_added_point and not (
        args.degree == 4 and math.isclose(args.h_nm, 3.0)
    ):
        parser.error("--task034-p4-h3-added-point is restricted to p4/h3.")
    selected_p6_gate_count = sum(
        (
            bool(args.task035c_p6_h10_gate),
            bool(args.task035d_case097_gate),
            bool(args.task035e_reference_certifier_gate),
            bool(args.task035e_blind_candidate_gate),
        )
    )
    if args.degree == 6 and selected_p6_gate_count != 1:
        parser.error(
            "p6 is fail-closed; select exactly one scoped Task035c, "
            "Task035d, Task035e reference, or Task035e blind-candidate gate."
        )
    if args.degree != 6 and selected_p6_gate_count:
        parser.error("Task035c/Task035d/Task035e p6 gates require --degree 6.")
    if args.task035c_p6_h10_gate:
        scoped = bool(
            args.degree == 6
            and math.isclose(args.h_nm, 10.0)
            and args.polarization_kind == "s"
            and args.run_kind == "full-solve"
            and args.mpi_size in TASK035C_P6_H10_MPI_SIZES
            and args.profile == "default"
            and args.stage4_full3d_assembly_backend in TASK035C_P6_H10_BACKENDS
            and not args.allow_swap
            and args.task035c_p6_preflight_authority is not None
            and valid_hex_digest(args.task035c_p6_preflight_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and args.p3_gate_record is None
            and args.p4_trace_record is None
            and not args.task034_p4_h3_added_point
        )
        if not scoped:
            parser.error(
                "--task035c-p6-h10-gate is restricted to a clean-source, "
                "no-swap, default-profile fixed rectangular p6/h10 S-polarized "
                "full solve on MPI1/2/4/8 with standard_full or "
                "assembly_time_static_condensed and a hash-bound historical "
                "preflight authority."
            )
    elif (
        args.task035c_p6_preflight_authority is not None
        or args.task035c_p6_preflight_sha256 is not None
    ):
        parser.error(
            "Task035c p6 preflight authority arguments require --task035c-p6-h10-gate."
        )
    task035e_resource_authority_provided = (
        args.task035e_reference_resource_authority is not None
        or args.task035e_reference_resource_authority_sha256 is not None
    )
    task035e_h5_factor_authority_provided = (
        args.task035e_h5_factorization_authority is not None
        or args.task035e_h5_factorization_authority_sha256 is not None
    )
    if args.task035e_reference_certifier_gate:
        full_solve = args.run_kind == "full-solve"
        assembly_only = args.run_kind == "assembly-only"
        h5_full_solve = bool(
            full_solve and math.isclose(float(args.h_nm), 5.0)
        )
        authority_scope = bool(
            (
                args.task035e_reference_resource_authority is not None
                and valid_hex_digest(
                    args.task035e_reference_resource_authority_sha256,
                    64,
                )
            )
            if full_solve
            else (
                args.task035e_reference_resource_authority is None
                and args.task035e_reference_resource_authority_sha256 is None
            )
        )
        h5_factor_authority_scope = bool(
            (
                args.task035e_h5_factorization_authority is not None
                and valid_hex_digest(
                    args.task035e_h5_factorization_authority_sha256,
                    64,
                )
            )
            if h5_full_solve
            else (
                args.task035e_h5_factorization_authority is None
                and args.task035e_h5_factorization_authority_sha256 is None
            )
        )
        scoped = bool(
            args.degree == 6
            and args.h_nm in TASK035E_REFERENCE_H_NM
            and args.polarization_kind == "s"
            and (assembly_only or full_solve)
            and args.mpi_size == TASK035E_REFERENCE_MPI_SIZE
            and args.profile == "default"
            and args.stage4_full3d_assembly_backend
            == TASK035E_REFERENCE_BACKEND
            and not args.allow_swap
            and authority_scope
            and h5_factor_authority_scope
            and valid_hex_digest(args.verified_clean_sha, 40)
            and not args.task035c_p6_h10_gate
            and not args.task035d_case097_gate
            and args.task035c_p6_preflight_authority is None
            and args.task035c_p6_preflight_sha256 is None
            and args.p3_gate_record is None
            and args.p4_trace_record is None
            and not args.task034_p4_h3_added_point
            and args.stage4_variable_p_cell_degree_plan is None
            and args.stage4_variable_p_cell_degree_plan_sha256 is None
            and args.stage4_local_h_refinement_plan is None
            and args.stage4_local_h_refinement_plan_sha256 is None
        )
        if not scoped:
            parser.error(
                "--task035e-reference-certifier-gate is restricted to the "
                "clean-source fixed rectangular p6 h10/h7.5/h5, S-polarized, "
                "MPI8, direct default-profile MUMPS path using "
                "assembly_time_static_condensed. Only assembly-only or "
                "full-solve is allowed; full-solve requires one hash-bound "
                "Task035e assembly resource authority, and h5 full-solve "
                "additionally requires a short-lived factorization ALLOW "
                "authority."
            )
    elif (
        task035e_resource_authority_provided
        or task035e_h5_factor_authority_provided
    ):
        parser.error(
            "Task035e authority arguments require "
            "--task035e-reference-certifier-gate."
        )
    task035e_internal_probe = (
        args.task035e_internal_probe_kind is not None
    )
    task035e_probe_parameter_provided = bool(
        args.task035e_probe_dtn_max_m is not None
        or args.task035e_probe_dtn_max_n is not None
        or args.task035e_probe_surface_quadrature_degree is not None
    )
    if task035e_internal_probe:
        kind = str(args.task035e_internal_probe_kind)
        dtn_parameters = bool(
            type(args.task035e_probe_dtn_max_m) is int
            and args.task035e_probe_dtn_max_m >= 0
            and type(args.task035e_probe_dtn_max_n) is int
            and args.task035e_probe_dtn_max_n >= 0
        )
        quadrature_parameter = bool(
            type(args.task035e_probe_surface_quadrature_degree) is int
            and args.task035e_probe_surface_quadrature_degree >= 1
        )
        scoped_probe = bool(
            args.task035e_blind_candidate_gate
            and args.task035e_blind_output_role == "current"
            and args.run_kind == "full-solve"
            and (
                args.mpi_size == 1
                if kind == "serial_mpi1"
                else args.mpi_size == TASK035E_BLIND_CANDIDATE_MPI_SIZE
            )
            and (
                dtn_parameters
                if kind == "dtn"
                else (
                    args.task035e_probe_dtn_max_m is None
                    and args.task035e_probe_dtn_max_n is None
                )
            )
            and (
                quadrature_parameter
                if kind == "postprocess"
                else (
                    args.task035e_probe_surface_quadrature_degree
                    is None
                )
            )
            and args.task035e_current_snapshot_manifest is not None
            and valid_hex_digest(
                args.task035e_current_snapshot_manifest_sha256,
                64,
            )
            and args.task035e_transition_action is None
            and args.task035e_transition_action_sha256 is None
        )
        if not scoped_probe:
            parser.error(
                "--task035e-internal-probe-kind requires the Task035e blind "
                "current full-solve gate, a hash-bound same-cycle MPI8 current "
                "snapshot, no transition action, and MPI8 except for the "
                "explicit serial_mpi1 diagnostic. Only dtn accepts nonnegative "
                "max-m/max-n; only postprocess accepts a positive surface "
                "quadrature degree."
            )
    elif task035e_probe_parameter_provided:
        parser.error(
            "Task035e probe parameters require "
            "--task035e-internal-probe-kind."
        )
    task035e_blind_metadata_provided = bool(
        task035e_internal_probe
        or task035e_probe_parameter_provided
        or args.task035e_blind_trial_id is not None
        or args.task035e_blind_cycle_index is not None
        or args.task035e_blind_output_role is not None
        or args.task035e_current_snapshot_manifest is not None
        or args.task035e_current_snapshot_manifest_sha256 is not None
        or args.task035e_transition_action is not None
        or args.task035e_transition_action_sha256 is not None
    )
    if args.task035e_blind_candidate_gate:
        task035e_initial_current = bool(
            args.task035e_blind_output_role == "current"
            and args.task035e_blind_cycle_index == 0
            and not task035e_internal_probe
        )
        scoped = bool(
            args.degree == 6
            and args.h_nm in TASK035E_BLIND_CANDIDATE_H_NM
            and args.polarization_kind == "s"
            and args.run_kind == "full-solve"
            and (
                args.mpi_size == 1
                if args.task035e_internal_probe_kind == "serial_mpi1"
                else args.mpi_size == TASK035E_BLIND_CANDIDATE_MPI_SIZE
            )
            and args.profile == "default"
            and args.stage4_full3d_assembly_backend
            == TASK035E_BLIND_CANDIDATE_BACKEND
            and not args.allow_swap
            and args.stage4_local_h_refinement_plan is not None
            and valid_hex_digest(
                args.stage4_local_h_refinement_plan_sha256,
                64,
            )
            and args.stage4_variable_p_cell_degree_plan is None
            and args.stage4_variable_p_cell_degree_plan_sha256 is None
            and isinstance(args.task035e_blind_trial_id, str)
            and TASK035E_TRIAL_ID_RE.fullmatch(
                args.task035e_blind_trial_id
            )
            is not None
            and isinstance(args.task035e_blind_cycle_index, int)
            and not isinstance(args.task035e_blind_cycle_index, bool)
            and 0 <= args.task035e_blind_cycle_index <= 5
            and args.task035e_blind_output_role
            in {"current", "p-shadow", "h-shadow"}
            and (
                args.task035e_blind_output_role == "current"
                or args.task035e_blind_cycle_index <= 4
            )
            and (
                (
                    args.task035e_current_snapshot_manifest is None
                    and args.task035e_current_snapshot_manifest_sha256
                    is None
                    and args.task035e_transition_action is None
                    and args.task035e_transition_action_sha256 is None
                )
                if task035e_initial_current
                else (
                    args.task035e_current_snapshot_manifest is not None
                    and valid_hex_digest(
                        (
                            args
                            .task035e_current_snapshot_manifest_sha256
                        ),
                        64,
                    )
                    and args.task035e_transition_action is None
                    and args.task035e_transition_action_sha256 is None
                )
                if task035e_internal_probe
                else (
                    args.task035e_current_snapshot_manifest is not None
                    and valid_hex_digest(
                        (
                            args
                            .task035e_current_snapshot_manifest_sha256
                        ),
                        64,
                    )
                    and args.task035e_transition_action is not None
                    and valid_hex_digest(
                        args.task035e_transition_action_sha256,
                        64,
                    )
                )
            )
            and valid_hex_digest(args.verified_clean_sha, 40)
            and not args.task035c_p6_h10_gate
            and not args.task035d_case097_gate
            and not args.task035e_reference_certifier_gate
            and args.task035c_p6_preflight_authority is None
            and args.task035c_p6_preflight_sha256 is None
            and args.task035d_plan_authority is None
            and args.task035d_plan_authority_sha256 is None
            and args.task035d_candidate_id == "t30"
            and args.task035d_nested_p_dwr_phase is None
            and args.task035d_selective_face_dwr_phase is None
            and args.task035d_significant_channel_authority is None
            and args.task035d_significant_channel_authority_sha256 is None
            and args.task035d_nested_p_pair_authority is None
            and args.task035d_nested_p_pair_authority_sha256 is None
            and args.task035d_coarse_snapshot_manifest is None
            and args.task035d_coarse_snapshot_manifest_sha256 is None
            and args.task035d_selective_face_coarse_manifest is None
            and args.task035d_selective_face_coarse_manifest_sha256 is None
            and not task035e_resource_authority_provided
            and not task035e_h5_factor_authority_provided
            and args.p3_gate_record is None
            and args.p4_trace_record is None
            and not args.task034_p4_h3_added_point
        )
        if not scoped:
            parser.error(
                "--task035e-blind-candidate-gate is restricted to one "
                "clean-source, no-swap p6 h20 Path A or h15 Path B, "
                "S-polarized MPI8 full solve (or the explicit final MPI1 "
                "same-plan diagnostic) using default direct MUMPS, "
                "assembly_time_variable_p_condensed, a hash-bound Task035e "
                "multilevel local-h plan, and cycle metadata. Reference, "
                "hidden, Task035c, and Task035d inputs are forbidden."
            )
    elif task035e_blind_metadata_provided:
        parser.error(
            "Task035e blind trial metadata requires "
            "--task035e-blind-candidate-gate."
        )
    if args.task035d_case097_gate:
        local_h_candidate = args.task035d_candidate_id in TASK035D_LOCAL_H_CANDIDATES
        plan_scope = (
            args.stage4_variable_p_cell_degree_plan is None
            and args.stage4_variable_p_cell_degree_plan_sha256 is None
            and args.stage4_local_h_refinement_plan is not None
            and valid_hex_digest(
                args.stage4_local_h_refinement_plan_sha256,
                64,
            )
            if local_h_candidate
            else (
                args.stage4_variable_p_cell_degree_plan is not None
                and valid_hex_digest(
                    args.stage4_variable_p_cell_degree_plan_sha256,
                    64,
                )
                and args.stage4_local_h_refinement_plan is None
                and args.stage4_local_h_refinement_plan_sha256 is None
            )
        )
        scoped = bool(
            args.degree == 6
            and math.isclose(
                args.h_nm,
                15.0 if local_h_candidate else 10.0,
            )
            and args.polarization_kind == "s"
            and args.run_kind == "full-solve"
            and args.mpi_size == 8
            and args.profile == "default"
            and args.stage4_full3d_assembly_backend == TASK035D_CASE097_BACKEND
            and not args.allow_swap
            and plan_scope
            and args.task035d_plan_authority is not None
            and valid_hex_digest(args.task035d_plan_authority_sha256, 64)
            and valid_hex_digest(args.verified_clean_sha, 40)
            and not args.task035c_p6_h10_gate
            and args.task035c_p6_preflight_authority is None
            and args.task035c_p6_preflight_sha256 is None
            and args.p3_gate_record is None
            and args.p4_trace_record is None
            and not args.task034_p4_h3_added_point
        )
        if not scoped:
            parser.error(
                "--task035d-case097-gate is restricted to a clean-source, "
                "no-swap, default-profile fixed rectangular p6/h10 "
                "variable-p or p6/h15 balanced local-h S-polarized full "
                "solve on MPI8 using assembly_time_variable_p_condensed "
                "with one tracked, hash-bound candidate plan and MPI8 "
                "plan authority."
            )
        nested_phase = args.task035d_nested_p_dwr_phase
        selective_phase = args.task035d_selective_face_dwr_phase
        if nested_phase is not None and selective_phase is not None:
            parser.error(
                "Task035d same-trace nested-p and cross-trace "
                "selective-face observers are mutually exclusive."
            )
        if nested_phase is not None:
            expected_candidate = (
                TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME
                if nested_phase == "coarse-snapshot"
                else TASK035D_LOCAL_H_PLAN_NAME
            )
            nested_scope = bool(
                args.task035d_candidate_id == expected_candidate
                and args.task035d_significant_channel_authority is not None
                and valid_hex_digest(
                    args.task035d_significant_channel_authority_sha256,
                    64,
                )
                and args.task035d_nested_p_pair_authority is not None
                and valid_hex_digest(
                    args.task035d_nested_p_pair_authority_sha256,
                    64,
                )
                and (
                    (
                        args.task035d_coarse_snapshot_manifest is None
                        and args.task035d_coarse_snapshot_manifest_sha256 is None
                    )
                    if nested_phase == "coarse-snapshot"
                    else (
                        args.task035d_coarse_snapshot_manifest is not None
                        and valid_hex_digest(
                            args.task035d_coarse_snapshot_manifest_sha256,
                            64,
                        )
                    )
                )
            )
            if not nested_scope:
                parser.error(
                    "Task035d nested-p DWR is restricted to the frozen "
                    "remote-p5-interior coarse B snapshot followed by the "
                    "all-p6-interior enriched A evaluation, with one "
                    "hash-bound A/B pair authority, significant-channel "
                    "authority, and coarse manifest."
                )
        elif selective_phase is not None:
            expected_candidate = (
                TASK035D_LOCAL_H_PLAN_NAME
                if selective_phase == "coarse-snapshot"
                else TASK035D_SELECTIVE_FACE_PLAN_NAME
            )
            selective_scope = bool(
                args.task035d_candidate_id == expected_candidate
                and args.task035d_significant_channel_authority is not None
                and valid_hex_digest(
                    args.task035d_significant_channel_authority_sha256,
                    64,
                )
                and args.task035d_nested_p_pair_authority is None
                and args.task035d_nested_p_pair_authority_sha256 is None
                and args.task035d_coarse_snapshot_manifest is None
                and args.task035d_coarse_snapshot_manifest_sha256 is None
                and (
                    (
                        args.task035d_selective_face_coarse_manifest is None
                        and (args.task035d_selective_face_coarse_manifest_sha256)
                        is None
                    )
                    if selective_phase == "coarse-snapshot"
                    else (
                        args.task035d_selective_face_coarse_manifest is not None
                        and valid_hex_digest(
                            (args.task035d_selective_face_coarse_manifest_sha256),
                            64,
                        )
                    )
                )
            )
            if not selective_scope:
                parser.error(
                    "Task035d selective-face DWR is restricted to the "
                    "frozen h15 p5-trace coarse snapshot followed by the "
                    "ten-face enriched candidate, with one hash-bound "
                    "significant-channel authority and coarse manifest."
                )
        elif any(
            value is not None
            for value in (
                args.task035d_significant_channel_authority,
                args.task035d_significant_channel_authority_sha256,
                args.task035d_nested_p_pair_authority,
                args.task035d_nested_p_pair_authority_sha256,
                args.task035d_coarse_snapshot_manifest,
                args.task035d_coarse_snapshot_manifest_sha256,
                args.task035d_selective_face_coarse_manifest,
                args.task035d_selective_face_coarse_manifest_sha256,
            )
        ):
            parser.error(
                "Task035d DWR authority arguments require one explicit "
                "nested-p or selective-face DWR phase."
            )
    elif not args.task035e_blind_candidate_gate and (
        args.task035d_plan_authority is not None
        or args.task035d_plan_authority_sha256 is not None
        or args.stage4_variable_p_cell_degree_plan is not None
        or args.stage4_variable_p_cell_degree_plan_sha256 is not None
        or args.stage4_local_h_refinement_plan is not None
        or args.stage4_local_h_refinement_plan_sha256 is not None
        or args.stage4_full3d_assembly_backend == TASK035D_CASE097_BACKEND
        or args.task035d_candidate_id != "t30"
        or args.task035d_nested_p_dwr_phase is not None
        or args.task035d_selective_face_dwr_phase is not None
        or args.task035d_significant_channel_authority is not None
        or args.task035d_significant_channel_authority_sha256 is not None
        or args.task035d_nested_p_pair_authority is not None
        or args.task035d_nested_p_pair_authority_sha256 is not None
        or args.task035d_coarse_snapshot_manifest is not None
        or args.task035d_coarse_snapshot_manifest_sha256 is not None
        or args.task035d_selective_face_coarse_manifest is not None
        or args.task035d_selective_face_coarse_manifest_sha256 is not None
    ):
        parser.error("Task035d variable-p arguments require --task035d-case097-gate.")
    if (
        args.stage4_full3d_assembly_backend
        in {
            "assembly_time_static_condensed",
            TASK035D_CASE097_BACKEND,
        }
        and args.run_kind != "full-solve"
        and not (
            args.task035e_reference_certifier_gate
            and args.run_kind == "assembly-only"
            and args.stage4_full3d_assembly_backend
            == TASK035E_REFERENCE_BACKEND
        )
    ):
        parser.error(
            "assembly-time condensed backends require --run-kind full-solve "
            "for mandatory recovery and explicit residual."
        )
    if not args.worker and (
        args.parent_launch_descriptor is not None
        or args.parent_launch_descriptor_sha256 is not None
    ):
        parser.error("parent-launch descriptor options are internal worker arguments.")
    return args


def _validate_task035c_p6_preflight(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    if not args.task035c_p6_h10_gate:
        return None
    path = args.task035c_p6_preflight_authority
    if path is None:
        raise SystemExit("Task035c p6/h10 preflight authority path is required.")
    path = path if path.is_absolute() else ROOT / path
    path = path.resolve()
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Task035c p6/h10 preflight authority is unreadable: {exc}"
        ) from exc
    try:
        relative = path.relative_to(ROOT).as_posix()
    except ValueError:
        relative = None
    tracked = bool(
        relative is not None
        and subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )
    gate = task035c_p6_h10_preflight_authority_gate(
        record if isinstance(record, dict) else None,
        expected_sha256=args.task035c_p6_preflight_sha256,
        observed_sha256=_sha256(path),
        authority_is_tracked=tracked,
    )
    gate["path"] = _path_from_root(path)
    if not gate["pass"]:
        raise SystemExit(
            f"Task035c p6/h10 preflight authority failed: {gate['failures']}"
        )
    return gate


def _validate_task035e_reference_resource_authority(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    if (
        not args.task035e_reference_certifier_gate
        or args.run_kind != "full-solve"
    ):
        return None
    path = args.task035e_reference_resource_authority
    if path is None:
        raise SystemExit(
            "Task035e full solve requires an assembly resource authority."
        )
    path = (path if path.is_absolute() else ROOT / path).resolve()
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Task035e assembly resource authority is unreadable: {exc}"
        ) from exc
    config_authority = _task035e_reference_config_authority(args)
    gate = _task035e_reference_resource_authority_gate(
        record if isinstance(record, Mapping) else None,
        expected_sha256=(
            args.task035e_reference_resource_authority_sha256
        ),
        observed_sha256=_sha256(path),
        expected_source_sha=args.verified_clean_sha,
        expected_config_sha256=(
            None
            if config_authority is None
            else str(config_authority["sha256"])
        ),
        expected_h_nm=float(args.h_nm),
    )
    gate["path"] = _path_from_root(path)
    if not gate["pass"]:
        raise SystemExit(
            "Task035e assembly resource authority failed: "
            f"{gate['failures']}"
        )
    args.task035e_reference_resource_authority = path
    return gate


def _validate_task035e_h5_factorization_authority(
    args: argparse.Namespace,
    *,
    now_utc: datetime | None = None,
) -> dict[str, Any] | None:
    if (
        not args.task035e_reference_certifier_gate
        or args.run_kind != "full-solve"
        or not math.isclose(float(args.h_nm), 5.0)
    ):
        return None
    path = args.task035e_h5_factorization_authority
    if path is None:
        raise SystemExit(
            "Task035e h5 full solve requires a factorization ALLOW authority."
        )
    path = (path if path.is_absolute() else ROOT / path).resolve()
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Task035e h5 factorization authority is unreadable: {exc}"
        ) from exc
    config_authority = _task035e_reference_config_authority(args)
    gate = _task035e_h5_factorization_authority_gate(
        record if isinstance(record, Mapping) else None,
        expected_file_sha256=(
            args.task035e_h5_factorization_authority_sha256
        ),
        observed_file_sha256=_sha256(path),
        expected_assembly_sha256=(
            args.task035e_reference_resource_authority_sha256
        ),
        expected_source_sha=args.verified_clean_sha,
        expected_config_sha256=(
            None
            if config_authority is None
            else str(config_authority["sha256"])
        ),
        now_utc=now_utc,
    )
    gate["path"] = _path_from_root(path)
    if not gate["pass"]:
        raise SystemExit(
            "Task035e h5 factorization authority failed: "
            f"{gate['failures']}"
        )
    args.task035e_h5_factorization_authority = path
    return gate


def _task035e_snapshot_shard_path(
    manifest_path: Path,
    shard_value: Any,
    *,
    rank: int,
) -> Path | None:
    """Resolve one canonical shard basename beside its manifest.

    Snapshot manifests deliberately store shard basenames instead of absolute
    paths.  Resolve that contract relative to the manifest while rejecting
    absolute paths, traversal, nested paths, non-canonical rank names, and
    symlinks.
    """

    if not isinstance(shard_value, str):
        return None
    relative = Path(shard_value)
    expected_name = f"rank{rank:04d}.npz"
    if (
        not shard_value
        or relative.is_absolute()
        or relative.name != shard_value
        or shard_value != expected_name
    ):
        return None
    directory = manifest_path.expanduser().resolve().parent
    unresolved = directory / relative
    if unresolved.is_symlink():
        return None
    resolved = unresolved.resolve()
    if resolved.parent != directory:
        return None
    return resolved


def _task035e_current_snapshot_launch_binding(
    args: argparse.Namespace,
    *,
    verify_shards: bool = True,
) -> tuple[Path, Mapping[str, Any], dict[str, Any], dict[str, bool]]:
    path = args.task035e_current_snapshot_manifest
    expected_sha = args.task035e_current_snapshot_manifest_sha256
    if path is None or not valid_hex_digest(expected_sha, 64):
        raise SystemExit(
            "Task035e p/h-shadow requires a hash-bound current snapshot "
            "manifest."
        )
    resolved = _task035e_private_regular_input_path(
        path,
        label="current snapshot",
    )
    if _sha256(resolved) != expected_sha:
        raise SystemExit(
            "Task035e current snapshot file SHA-256 differs from the "
            "launch authority."
        )
    try:
        payload = _task035e_strict_json_loads(
            resolved.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(
            f"Task035e current snapshot is unreadable: {exc}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise SystemExit("Task035e current snapshot is not a JSON object.")

    unsigned_manifest = dict(payload)
    stored_payload_sha = unsigned_manifest.pop(
        "manifest_payload_sha256",
        None,
    )
    plan_identity = payload.get("plan_identity")
    plan_identity = (
        plan_identity if isinstance(plan_identity, Mapping) else {}
    )
    plan_path_value = plan_identity.get("path")
    plan_path_input = (
        Path(plan_path_value).expanduser()
        if isinstance(plan_path_value, str)
        else None
    )
    plan_path = (
        plan_path_input.resolve()
        if plan_path_input is not None
        else None
    )
    plan_payload: Mapping[str, Any] = {}
    plan_path_qualified = bool(
        plan_path is not None
        and plan_path_input is not None
        and not plan_path_input.is_symlink()
        and plan_path.is_file()
        and (plan_path.stat().st_mode & 0o777) == 0o600
        and not {
            part.lower()
            for part in plan_path.parts
        }.intersection(TASK035E_FORBIDDEN_INPUT_PATH_PARTS)
    )
    if plan_path_qualified:
        try:
            loaded_plan = _task035e_strict_json_loads(
                plan_path.read_text(encoding="utf-8")
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            ValueError,
        ):
            loaded_plan = {}
        if isinstance(loaded_plan, Mapping):
            plan_payload = loaded_plan
    plan_provenance = plan_payload.get("provenance")
    plan_provenance = (
        plan_provenance
        if isinstance(plan_provenance, Mapping)
        else {}
    )
    plan_cycle = plan_provenance.get("cycle_index")
    requested_cycle = args.task035e_blind_cycle_index
    expected_snapshot_cycle = (
        requested_cycle
        if args.task035e_internal_probe_kind is not None
        else requested_cycle - 1
        if args.task035e_blind_output_role == "current"
        else requested_cycle
    )
    plan_cycle_bound = (
        (
            expected_snapshot_cycle == 0
            and plan_cycle is None
            and plan_provenance.get("schema_version")
            == TASK035E_BLIND_INITIAL_PROVENANCE_SCHEMA
        )
        or (
            type(plan_cycle) is int
            and plan_cycle == expected_snapshot_cycle
            and plan_provenance.get("schema_version")
            == TASK035E_BLIND_TRANSITION_PROVENANCE_SCHEMA
        )
    )
    shard_rows = payload.get("shards")
    shard_rows = shard_rows if isinstance(shard_rows, list) else []
    shard_checks = []
    shard_ranks = []
    for row in shard_rows if verify_shards else ():
        if not isinstance(row, Mapping):
            shard_checks.append(False)
            continue
        try:
            shard_rank = int(row.get("rank", -1))
        except (TypeError, ValueError):
            shard_rank = -1
        shard_path = _task035e_snapshot_shard_path(
            resolved,
            row.get("path"),
            rank=shard_rank,
        )
        shard_ranks.append(shard_rank)
        shard_checks.append(
            bool(
                shard_path is not None
                and shard_path.is_file()
                and (shard_path.stat().st_mode & 0o777) == 0o600
                and shard_path.stat().st_size == row.get("bytes")
                and _sha256(shard_path) == row.get("file_sha256")
            )
        )
    capability = payload.get("capability_credit")
    capability = capability if isinstance(capability, Mapping) else {}
    checks = {
        "schema": (
            payload.get("schema_version")
            == TASK035E_CURRENT_SNAPSHOT_SCHEMA
        ),
        "status": (
            payload.get("status")
            == "multigoal_current_live_snapshot_pass"
            and payload.get("pass") is True
        ),
        "role": payload.get("role") == "current_blind_state",
        "source": payload.get("source_sha") == args.verified_clean_sha,
        "trial": payload.get("trial_id") == args.task035e_blind_trial_id,
        "cycle": payload.get("cycle_index") == expected_snapshot_cycle,
        "mpi8": (
            payload.get("mpi_size") == 8
            and payload.get("formal_mpi8_qualified") is True
        ),
        "manifest_self_hash": (
            valid_hex_digest(stored_payload_sha, 64)
            and _task035e_namespaced_json_sha256(
                unsigned_manifest,
                namespace="task035e.multigoal-current-manifest.v1",
            )
            == stored_payload_sha
        ),
        "plan_file_hash_bound": (
            plan_path_qualified
            and _sha256(plan_path) == plan_identity.get("file_sha256")
        ),
        "plan_payload_hash_bound": (
            bool(plan_payload)
            and _task035e_namespaced_json_sha256(
                plan_payload,
                namespace="task035e.executed-plan-payload.v1",
            )
            == plan_identity.get("payload_sha256")
        ),
        "plan_source_cycle_bound": (
            plan_provenance.get("source_sha")
            == args.verified_clean_sha
            and plan_cycle_bound
        ),
        "plan_forest_degree_bound": (
            valid_hex_digest(
                plan_identity.get("forest_leaf_catalog_sha256"),
                64,
            )
            and valid_hex_digest(
                plan_identity.get("cell_degree_plan_sha256"),
                64,
            )
            and plan_payload.get("expected_forest", {}).get(
                "leaf_catalog_sha256"
            )
            == plan_identity.get("forest_leaf_catalog_sha256")
            and plan_payload.get(
                "cell_interior_degree_plan_sha256"
            )
            == plan_identity.get("cell_degree_plan_sha256")
        ),
        "eight_rank_shards_hash_bound": (
            not verify_shards
            or (
                len(shard_rows) == 8
                and shard_ranks == list(range(8))
                and all(shard_checks)
            )
        ),
        "no_reference_credit": (
            capability.get("current_primal_snapshot_complete") is True
            and capability.get("accuracy_credit") is False
            and payload.get("ordinary_default_changed") is False
        ),
    }
    binding = {
        "plan_identity": dict(plan_identity),
        "plan_payload": dict(plan_payload),
        "snapshot_cycle_index": expected_snapshot_cycle,
    }
    return resolved, payload, binding, checks


def _validate_task035e_transition_action_input(
    args: argparse.Namespace,
    *,
    current_snapshot_binding: Mapping[str, Any],
    target_plan: Mapping[str, Any],
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    path = args.task035e_transition_action
    expected_file_sha = args.task035e_transition_action_sha256
    if path is None or not valid_hex_digest(expected_file_sha, 64):
        raise SystemExit(
            "Task035e transition solve requires a hash-bound h/p action."
        )
    resolved = _task035e_private_regular_input_path(
        path,
        label="transition action",
    )
    if _sha256(resolved) != expected_file_sha:
        raise SystemExit(
            "Task035e transition action file SHA-256 differs from the "
            "launch authority."
        )
    try:
        payload = _task035e_strict_json_loads(
            resolved.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(
            f"Task035e transition action is unreadable: {exc}"
        ) from exc
    action = payload if isinstance(payload, Mapping) else {}
    action_unsigned = dict(action)
    stored_action_sha = action_unsigned.pop("action_sha256", None)
    identity = {
        "action_id": action.get("action_id"),
        "kind": action.get("kind"),
        "cycle_index": action.get("cycle_index"),
        "source_sha": action.get("source_sha"),
        "algorithm_sha256": action.get("algorithm_sha256"),
        "canonical_target_ids": action.get("canonical_target_ids"),
    }
    current_identity = current_snapshot_binding.get("plan_identity")
    current_identity = (
        current_identity
        if isinstance(current_identity, Mapping)
        else {}
    )
    expected_forest = target_plan.get("expected_forest")
    expected_forest = (
        expected_forest
        if isinstance(expected_forest, Mapping)
        else {}
    )
    role = str(args.task035e_blind_output_role)
    expected_action_cycle = int(args.task035e_blind_cycle_index) + (
        0 if role == "current" else 1
    )
    expected_kind = {
        "p-shadow": "p-up",
        "h-shadow": "h-refine",
    }.get(role)
    action_kind = action.get("kind")
    p_keep = action_kind == "p-keep"
    checks = {
        "exact_schema": (
            set(action) == TASK035E_TRANSITION_ACTION_FIELDS
            and action.get("schema_version")
            == TASK035E_TRANSITION_ACTION_SCHEMA
            and action.get("status") == "hp_transition_action_closed"
        ),
        "action_self_hash": (
            valid_hex_digest(stored_action_sha, 64)
            and _canonical_json_sha256(action_unsigned)
            == stored_action_sha
        ),
        "action_identity_hash": (
            valid_hex_digest(action.get("action_identity_sha256"), 64)
            and _canonical_json_sha256(identity)
            == action.get("action_identity_sha256")
        ),
        "source_cycle_role": (
            action.get("source_sha") == args.verified_clean_sha
            and action.get("cycle_index") == expected_action_cycle
            and action_kind in {
                "p-up",
                "p-down",
                "p-keep",
                "h-refine",
            }
            and (
                expected_kind is None
                or action_kind == expected_kind
            )
        ),
        "p_keep_current_role_only": (
            not p_keep or role == "current"
        ),
        "current_plan_bound": (
            action.get("from_leaf_catalog_sha256")
            == current_identity.get("forest_leaf_catalog_sha256")
            and action.get("from_cell_degree_plan_sha256")
            == current_identity.get("cell_degree_plan_sha256")
            and action.get("stage_prefix_length")
            == current_snapshot_binding.get("snapshot_cycle_index")
        ),
        "target_plan_bound": (
            action.get("expected_next_leaf_catalog_sha256")
            == expected_forest.get("leaf_catalog_sha256")
            and action.get("expected_next_cell_degree_plan_sha256")
            == target_plan.get("cell_interior_degree_plan_sha256")
        ),
        "target_inventory_nonempty": (
            action.get("canonical_target_ids") == []
            if p_keep
            else (
                isinstance(action.get("canonical_target_ids"), list)
                and bool(action.get("canonical_target_ids"))
                and all(
                    isinstance(value, str) and bool(value)
                    for value in action.get("canonical_target_ids", ())
                )
            )
        ),
        "p_keep_empty_action": (
            not p_keep
            or (
                action.get("canonical_target_ids") == []
                and action.get("requested_split_keys") == []
                and action.get("degree_deltas") == []
                and action.get("maximum_level") is None
                and action.get("expected_removed_leaf_keys") == []
                and action.get("expected_added_leaf_keys") == []
                and action.get("expected_net_added_leaf_count") == 0
            )
        ),
        "p_keep_execution_identities_unchanged": (
            not p_keep
            or (
                action.get("from_leaf_catalog_sha256")
                == action.get("expected_next_leaf_catalog_sha256")
                and action.get("from_cell_degree_plan_sha256")
                == action.get(
                    "expected_next_cell_degree_plan_sha256"
                )
                and action.get("from_forest_geometry_sha256")
                == action.get(
                    "expected_next_forest_geometry_sha256"
                )
                and action.get("from_degree_plan_sha256")
                == action.get("expected_next_degree_plan_sha256")
            )
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    gate = {
        "schema_version": "task035e.transition-action-launch-gate.v1",
        "pass": not failures,
        "path": _path_from_root(resolved),
        "file_sha256": expected_file_sha,
        "action_sha256": stored_action_sha,
        "action_identity_sha256": action.get("action_identity_sha256"),
        "checks": checks,
        "failures": failures,
    }
    if failures:
        raise SystemExit(
            "Task035e transition action failed launch qualification: "
            f"{failures}"
        )
    args.task035e_transition_action = resolved
    return action, gate


def _validate_task035e_blind_candidate_plan(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    if not args.task035e_blind_candidate_gate:
        return None
    path = args.stage4_local_h_refinement_plan
    if path is None:
        raise SystemExit("Task035e blind candidate requires a local-h/p plan.")
    path = _task035e_private_regular_input_path(
        path,
        label="blind candidate plan",
    )
    try:
        payload = _task035e_strict_json_loads(
            path.read_text(encoding="utf-8")
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise SystemExit(
            f"Task035e blind candidate plan is unreadable: {exc}"
        ) from exc
    current_binding = None
    transition_action = None
    transition_action_gate = None
    internal_probe = args.task035e_internal_probe_kind is not None
    if internal_probe or not (
        args.task035e_blind_output_role == "current"
        and args.task035e_blind_cycle_index == 0
    ):
        _snapshot_path, _snapshot, current_binding, snapshot_checks = (
            _task035e_current_snapshot_launch_binding(
                args,
                verify_shards=False,
            )
        )
        if not all(snapshot_checks.values()):
            raise SystemExit(
                "Task035e current snapshot launch checks failed before "
                "shadow-plan qualification: "
                f"{[name for name, passed in snapshot_checks.items() if not passed]}"
            )
        if not internal_probe:
            transition_action, transition_action_gate = (
                _validate_task035e_transition_action_input(
                    args,
                    current_snapshot_binding=current_binding,
                    target_plan=(
                        payload if isinstance(payload, Mapping) else {}
                    ),
                )
            )
    gate = _task035e_blind_candidate_plan_gate(
        payload if isinstance(payload, Mapping) else None,
        expected_file_sha256=(
            args.stage4_local_h_refinement_plan_sha256
        ),
        observed_file_sha256=_sha256(path),
        expected_h_nm=float(args.h_nm),
        config=_full3d_config(args),
        expected_source_sha=args.verified_clean_sha,
        expected_cycle_index=args.task035e_blind_cycle_index,
        expected_output_role=args.task035e_blind_output_role,
        current_snapshot_binding=current_binding,
        transition_action=transition_action,
        internal_probe_kind=args.task035e_internal_probe_kind,
    )
    gate["transition_action_gate"] = transition_action_gate
    gate["path"] = _path_from_root(path)
    if not gate["pass"]:
        raise SystemExit(
            "Task035e blind candidate plan failed: "
            f"{gate['failures']}; rebuild_error={gate['rebuild_error']!r}"
        )
    args.stage4_local_h_refinement_plan = path
    return gate


def _validate_task035e_current_snapshot_input(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    """Validate the immutable current snapshot before a shadow launch."""

    if (
        not args.task035e_blind_candidate_gate
        or (
            args.task035e_blind_output_role == "current"
            and args.task035e_blind_cycle_index == 0
            and args.task035e_internal_probe_kind is None
        )
    ):
        return None
    expected_sha = args.task035e_current_snapshot_manifest_sha256
    resolved, _payload, _binding, checks = (
        _task035e_current_snapshot_launch_binding(
            args,
            verify_shards=not bool(args.worker),
        )
    )
    if not all(checks.values()):
        raise SystemExit(
            "Task035e current snapshot launch checks failed: "
            f"{[name for name, passed in checks.items() if not passed]}"
        )
    args.task035e_current_snapshot_manifest = resolved
    return {
        "schema_version": "task035e.current-snapshot-launch-gate.v1",
        "pass": True,
        "path": _path_from_root(resolved),
        "sha256": expected_sha,
        "checks": checks,
    }


def _validate_task035d_case097_plan(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    if not args.task035d_case097_gate:
        return None
    local_h_candidate = args.task035d_candidate_id in TASK035D_LOCAL_H_CANDIDATES
    plan_path = (
        args.stage4_local_h_refinement_plan
        if local_h_candidate
        else args.stage4_variable_p_cell_degree_plan
    )
    authority_path = args.task035d_plan_authority
    if plan_path is None or authority_path is None:
        raise SystemExit("Task035d Case097 plan and MPI8 authority paths are required.")
    plan_path = (plan_path if plan_path.is_absolute() else ROOT / plan_path).resolve()
    authority_path = (
        authority_path if authority_path.is_absolute() else ROOT / authority_path
    ).resolve()
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Task035d Case097 launch authority is unreadable: {exc}"
        ) from exc

    def tracked(path: Path) -> tuple[bool, str | None]:
        try:
            relative = path.relative_to(ROOT).as_posix()
        except ValueError:
            return False, None
        result = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", relative],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return result.returncode == 0, relative

    plan_tracked, plan_relative = tracked(plan_path)
    authority_tracked, authority_relative = tracked(authority_path)
    if args.task035d_candidate_id == TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME:
        gate_builder = task035d_case097_hp_factorial_bridge_plan_authority_gate
    elif args.task035d_candidate_id == TASK035D_LEFT_GRATING_TOP_PLAN_NAME:
        gate_builder = task035d_case097_left_grating_top_plan_authority_gate
    elif args.task035d_candidate_id == TASK035D_COMBINED_HP_PLAN_NAME:
        gate_builder = task035d_case097_combined_hp_plan_authority_gate
    elif args.task035d_candidate_id == TASK035D_SELECTIVE_FACE_PLAN_NAME:
        gate_builder = task035d_case097_selective_face_plan_authority_gate
    elif local_h_candidate:
        gate_builder = task035d_case097_local_h_plan_authority_gate
    elif args.task035d_candidate_id == "sidewall_z0_guard_v1":
        gate_builder = task035d_case097_sidewall_guard_plan_authority_gate
    else:
        gate_builder = task035d_case097_plan_authority_gate
    gate = gate_builder(
        plan if isinstance(plan, dict) else None,
        authority if isinstance(authority, dict) else None,
        expected_plan_file_sha256=(
            args.stage4_local_h_refinement_plan_sha256
            if local_h_candidate
            else args.stage4_variable_p_cell_degree_plan_sha256
        ),
        observed_plan_file_sha256=_sha256(plan_path),
        expected_authority_sha256=args.task035d_plan_authority_sha256,
        observed_authority_sha256=_sha256(authority_path),
        plan_is_tracked=plan_tracked,
        authority_is_tracked=authority_tracked,
        plan_path_from_root=plan_relative,
        authority_path_from_root=authority_relative,
    )
    gate["plan_path"] = _path_from_root(plan_path)
    gate["authority_path"] = _path_from_root(authority_path)
    gate["authority_path_from_root"] = authority_relative
    if not gate["pass"]:
        raise SystemExit(
            f"Task035d Case097 {args.task035d_candidate_id} launch "
            "authority failed: "
            f"{gate['failures']}"
        )
    if local_h_candidate:
        args.stage4_local_h_refinement_plan = plan_path
    else:
        args.stage4_variable_p_cell_degree_plan = plan_path
    args.task035d_plan_authority = authority_path
    return gate


def _validate_task035d_nested_p_inputs(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    phase = args.task035d_nested_p_dwr_phase
    if phase is None:
        return None
    pair_path = args.task035d_nested_p_pair_authority
    if pair_path is None:
        raise SystemExit("Task035d nested-p A/B pair authority is required.")
    pair_path = (pair_path if pair_path.is_absolute() else ROOT / pair_path).resolve()
    try:
        pair_authority = json.loads(pair_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Task035d nested-p pair authority is unreadable: {exc}"
        ) from exc
    if not isinstance(pair_authority, dict):
        pair_authority = {}
    try:
        pair_relative = pair_path.relative_to(ROOT).as_posix()
    except ValueError:
        pair_relative = None
    pair_tracked = bool(
        pair_relative is not None
        and subprocess.run(
            [
                "git",
                "ls-files",
                "--error-unmatch",
                "--",
                pair_relative,
            ],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )
    pair_sha = _sha256(pair_path)

    def load_pair_reference(
        entry: dict[str, Any],
        field: str,
    ) -> tuple[dict[str, Any] | None, dict[str, bool]]:
        reference = entry.get(field, {})
        raw_path = reference.get("path")
        expected_sha = reference.get("sha256")
        payload = None
        reference_path = None
        within_root = False
        tracked = False
        readable = False
        sha_matches = False
        if isinstance(raw_path, str):
            reference_path = (ROOT / raw_path).resolve()
            try:
                relative = reference_path.relative_to(ROOT).as_posix()
                within_root = True
            except ValueError:
                relative = None
            if within_root:
                tracked = (
                    subprocess.run(
                        [
                            "git",
                            "ls-files",
                            "--error-unmatch",
                            "--",
                            str(relative),
                        ],
                        cwd=ROOT,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False,
                    ).returncode
                    == 0
                )
                try:
                    payload = json.loads(reference_path.read_text(encoding="utf-8"))
                    readable = isinstance(payload, dict)
                except (OSError, json.JSONDecodeError):
                    payload = None
                sha_matches = bool(
                    readable
                    and isinstance(expected_sha, str)
                    and _sha256(reference_path) == expected_sha
                )
        return payload, {
            "within_root": within_root,
            "tracked": tracked,
            "readable": readable,
            "sha256": sha_matches,
        }

    pair_reference_payloads: dict[str, dict[str, Any] | None] = {}
    pair_reference_checks: dict[str, dict[str, bool]] = {}
    for role_name, role in (
        ("coarse_B", pair_authority.get("coarse_B", {})),
        ("enriched_A", pair_authority.get("enriched_A", {})),
    ):
        role = role if isinstance(role, dict) else {}
        for field in ("plan", "mpi8_launch_authority"):
            payload, checks = load_pair_reference(role, field)
            key = f"{role_name}_{field}"
            pair_reference_payloads[key] = payload
            pair_reference_checks[key] = checks

    authority_path = args.task035d_significant_channel_authority
    if authority_path is None:
        raise SystemExit("Task035d nested-p significant-channel authority is required.")
    authority_path = (
        authority_path if authority_path.is_absolute() else ROOT / authority_path
    ).resolve()
    try:
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"Task035d nested-p significant-channel authority is unreadable: {exc}"
        ) from exc
    try:
        authority_relative = authority_path.relative_to(ROOT).as_posix()
    except ValueError:
        authority_relative = None
    authority_tracked = bool(
        authority_relative is not None
        and subprocess.run(
            [
                "git",
                "ls-files",
                "--error-unmatch",
                "--",
                authority_relative,
            ],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )
    authority_sha = _sha256(authority_path)
    authority_checks = {
        "tracked": authority_tracked,
        "sha256": (authority_sha == args.task035d_significant_channel_authority_sha256),
        "schema": (
            authority.get("schema_version")
            == "task035b.significant-channel-reference.v1"
        ),
        "pass": authority.get("pass") is True,
        "twelve_channels": (
            authority.get("significant_channel_selection", {}).get("channel_count")
            == 12
            and len(authority.get("channels", ())) == 12
        ),
    }
    failures = [
        f"significant_channel_{name}"
        for name, passed in authority_checks.items()
        if not passed
    ]
    coarse_pair = pair_authority.get("coarse_B", {})
    coarse_pair = coarse_pair if isinstance(coarse_pair, dict) else {}
    enriched_pair = pair_authority.get("enriched_A", {})
    enriched_pair = enriched_pair if isinstance(enriched_pair, dict) else {}
    common_pair = pair_authority.get("frozen_common_identity", {})
    common_pair = common_pair if isinstance(common_pair, dict) else {}
    formal_contract = pair_authority.get("formal_run_contract", {})
    formal_contract = formal_contract if isinstance(formal_contract, dict) else {}
    stable_identity_keys = (
        "base_config_identity_sha256",
        "leaf_catalog_sha256",
        "hanging_face_catalog_sha256",
        "carrier_connectivity_sha256",
        "material_catalog_sha256",
        "physical_facet_catalog_sha256",
        "physical_authority_sha256",
        "flattened_graph_sha256",
        "canonical_cell_graph_sha256",
    )
    common_stable_identity_matches = all(
        all(
            payload is not None
            and payload.get("stable_identity", {}).get(key) == common_pair.get(key)
            for payload in (
                pair_reference_payloads["coarse_B_mpi8_launch_authority"],
                pair_reference_payloads["enriched_A_mpi8_launch_authority"],
            )
        )
        for key in stable_identity_keys
    )
    common_root_identity_matches = all(
        payload is not None
        and payload.get("root_cell_box_catalog_sha256")
        == common_pair.get("root_cell_box_catalog_sha256")
        and payload.get("expected_forest", {}).get("root_catalog_sha256")
        == common_pair.get("root_catalog_sha256")
        for payload in (
            pair_reference_payloads["coarse_B_plan"],
            pair_reference_payloads["enriched_A_plan"],
        )
    )
    active_pair = coarse_pair if phase == "coarse-snapshot" else enriched_pair
    expected_candidate = (
        TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME
        if phase == "coarse-snapshot"
        else TASK035D_LOCAL_H_PLAN_NAME
    )
    pair_checks = {
        "tracked": pair_tracked,
        "sha256": (pair_sha == args.task035d_nested_p_pair_authority_sha256),
        "schema": (
            pair_authority.get("schema_version")
            == "task035d.same-trace-nested-p-pair-authority.v1"
        ),
        "pass": pair_authority.get("pass") is True,
        "same_trace_only": (
            pair_authority.get("scope", {}).get("same_trace_only") is True
            and pair_authority.get("scope", {}).get("cross_trace_primal_prolongation")
            is False
            and pair_authority.get("scope", {}).get("dense_local_schur_persistence")
            is False
        ),
        "mpi8": (pair_authority.get("scope", {}).get("mpi_size") == 8),
        "referenced_files": all(
            all(checks.values()) for checks in pair_reference_checks.values()
        ),
        "common_stable_identity": common_stable_identity_matches,
        "common_root_identity": common_root_identity_matches,
        "coarse_candidate": (
            coarse_pair.get("candidate_id") == TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME
        ),
        "enriched_candidate": (
            enriched_pair.get("candidate_id") == TASK035D_LOCAL_H_PLAN_NAME
        ),
        "coarse_degree_and_dof_contract": (
            coarse_pair.get("cell_interior_degree_counts") == {"p5": 32, "p6": 102}
            and coarse_pair.get("actual_full3d_equivalent_active_fe_dofs") == 76_205
            and coarse_pair.get("reduced_trace_plus_auxiliary_rows") == 18_470
        ),
        "enriched_degree_and_dof_contract": (
            enriched_pair.get("cell_interior_degree_counts") == {"p5": 0, "p6": 134}
            and enriched_pair.get("actual_full3d_equivalent_active_fe_dofs") == 82_925
            and enriched_pair.get("reduced_trace_plus_auxiliary_rows") == 18_470
        ),
        "active_candidate": (
            active_pair.get("candidate_id")
            == expected_candidate
            == args.task035d_candidate_id
        ),
        "active_plan": (
            active_pair.get("plan", {}).get("sha256")
            == args.stage4_local_h_refinement_plan_sha256
        ),
        "active_launch_authority": (
            active_pair.get("mpi8_launch_authority", {}).get("sha256")
            == args.task035d_plan_authority_sha256
        ),
        "common_rows": (
            common_pair.get("leaf_cell_count") == 134
            and common_pair.get("trace_degree") == 5
            and common_pair.get("raw_trace_rows") == 23_875
            and common_pair.get("independent_trace_rows") == 18_390
            and common_pair.get("auxiliary_rows") == 80
            and common_pair.get("reduced_rows") == 18_470
        ),
        "same_channel_authority": (
            pair_authority.get("significant_channel_authority", {}).get("sha256")
            == authority_sha
        ),
        "formal_residual_contract": (
            formal_contract.get("coarse_full_explicit_true_residual_max") == 1.0e-9
            and formal_contract.get("enriched_full_explicit_true_residual_max")
            == 1.0e-9
            and formal_contract.get("unit_channel_adjoint_relative_residual_max")
            == 1.0e-9
        ),
        "formal_goal_contract": (
            formal_contract.get("unit_channel_adjoint_solve_count") == 12
            and formal_contract.get("all_36_signed_goal_closures_required") is True
            and formal_contract.get(
                "trace_only_functional_roundoff_must_pass_"
                "recorded_scale_aware_threshold"
            )
            is True
            and formal_contract.get(
                "trace_only_external_operator_content_sha_match_required"
            )
            is True
            and formal_contract.get(
                "trace_only_external_rhs_content_sha_match_required"
            )
            is True
            and formal_contract.get(
                "external_delta_may_be_derived_from_complete_minus_cell"
            )
            is False
            and formal_contract.get("unexplained_residual_may_be_added_back") is False
            and formal_contract.get("absolute_indicator_sum_may_close_goals") is False
        ),
    }
    failures.extend(
        f"pair_authority_{name}" for name, passed in pair_checks.items() if not passed
    )
    snapshot_gate = None
    if phase == "enriched-evaluate":
        snapshot_path = args.task035d_coarse_snapshot_manifest
        if snapshot_path is None:
            raise SystemExit(
                "Task035d enriched nested-p DWR requires a coarse manifest."
            )
        snapshot_path = (
            snapshot_path if snapshot_path.is_absolute() else ROOT / snapshot_path
        ).resolve()
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(f"Task035d coarse snapshot is unreadable: {exc}") from exc
        if not isinstance(snapshot, dict):
            snapshot = {}
        snapshot_artifact_gate = task035d_coarse_snapshot_artifact_gate(
            snapshot_path,
            snapshot,
            expected_mpi_size=8,
            expected_cell_count=134,
        )
        snapshot_checks = {
            "sha256": (
                _sha256(snapshot_path) == args.task035d_coarse_snapshot_manifest_sha256
            ),
            "schema": (
                snapshot.get("schema_version")
                == "task035d.variable-p-nested-coarse-snapshot.v1"
            ),
            "pass": snapshot.get("pass") is True,
            "role": snapshot.get("role") == "coarse_B",
            "candidate": (
                snapshot.get("candidate", {}).get("candidate_id")
                == TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME
            ),
            "candidate_plan": (
                snapshot.get("candidate", {}).get("plan_file_sha256")
                == coarse_pair.get("plan", {}).get("sha256")
            ),
            "candidate_degree_counts": (
                snapshot.get("candidate", {}).get("cell_interior_degree_counts")
                == {"5": 32, "6": 102}
            ),
            "candidate_dofs": (
                snapshot.get("candidate", {}).get(
                    "actual_full3d_equivalent_active_fe_dofs"
                )
                == 76_205
            ),
            "source": (
                snapshot.get("candidate", {}).get("source_sha")
                == args.verified_clean_sha
            ),
            "mpi8": (snapshot.get("same_trace_identity", {}).get("mpi_size") == 8),
            "trace_rows": (
                snapshot.get("same_trace_identity", {}).get("independent_trace_rows")
                == 18_390
            ),
            "matrix_rows": (
                snapshot.get("same_trace_identity", {}).get("matrix_rows") == 18_470
            ),
            "auxiliary_rows": (
                snapshot.get("same_trace_identity", {}).get("auxiliary_rows") == 80
            ),
            "same_channel_authority": (
                snapshot.get(
                    "significant_channel_authority",
                    {},
                ).get("sha256")
                == authority_sha
            ),
            "all_shards_preflight": (snapshot_artifact_gate["pass"] is True),
            "trace_only_port_operator_content": (
                snapshot.get("port_operator_audit", {}).get("pass") is True
                and all(
                    snapshot.get("port_operator_audit", {}).get("checks", {}).values()
                )
                and isinstance(
                    snapshot.get("port_operator_audit", {}).get(
                        "removed_active_interior_over_threshold_max"
                    ),
                    (int, float),
                )
                and 0.0
                <= float(
                    snapshot["port_operator_audit"][
                        "removed_active_interior_over_threshold_max"
                    ]
                )
                <= 1.0
                and isinstance(
                    snapshot.get("port_operator_audit", {}).get(
                        "external_operator_content_sha256"
                    ),
                    str,
                )
                and len(
                    snapshot["port_operator_audit"]["external_operator_content_sha256"]
                )
                == 64
                and isinstance(
                    snapshot.get("port_operator_audit", {}).get(
                        "external_rhs_content_sha256"
                    ),
                    str,
                )
                and len(snapshot["port_operator_audit"]["external_rhs_content_sha256"])
                == 64
            ),
            "primal_residual_gate": (
                snapshot.get("primal_residual_gate", {}).get("pass") is True
                and all(
                    snapshot.get("primal_residual_gate", {}).get("checks", {}).values()
                )
                and isinstance(
                    snapshot.get("vector_identity", {}).get("relative_residual"),
                    (int, float),
                )
                and float(snapshot["vector_identity"]["relative_residual"]) <= 1.0e-9
                and isinstance(
                    snapshot.get("full_active_residual", {}).get(
                        "linear_system_relative_residual"
                    ),
                    (int, float),
                )
                and float(
                    snapshot["full_active_residual"]["linear_system_relative_residual"]
                )
                <= 1.0e-9
            ),
        }
        failures.extend(
            f"coarse_snapshot_{name}"
            for name, passed in snapshot_checks.items()
            if not passed
        )
        snapshot_gate = {
            "path": _path_from_root(snapshot_path),
            "sha256": _sha256(snapshot_path),
            "checks": snapshot_checks,
            "artifact_gate": snapshot_artifact_gate,
        }
        args.task035d_coarse_snapshot_manifest = snapshot_path
    args.task035d_significant_channel_authority = authority_path
    args.task035d_nested_p_pair_authority = pair_path
    gate = {
        "schema_version": "task035d.nested-p-launch-gate.v1",
        "phase": phase,
        "pass": not failures,
        "failures": failures,
        "significant_channel_authority": {
            "path": _path_from_root(authority_path),
            "sha256": authority_sha,
            "checks": authority_checks,
        },
        "nested_p_pair_authority": {
            "path": _path_from_root(pair_path),
            "sha256": pair_sha,
            "checks": pair_checks,
            "referenced_file_checks": pair_reference_checks,
        },
        "coarse_snapshot": snapshot_gate,
        "same_trace_only": True,
        "cross_trace_primal_prolongation": False,
    }
    if failures:
        raise SystemExit(f"Task035d nested-p launch inputs failed: {failures}")
    return gate


def _validate_task035d_selective_face_inputs(
    args: argparse.Namespace,
) -> dict[str, Any] | None:
    """Validate the cross-trace endpoint pair without same-trace shortcuts."""

    phase = args.task035d_selective_face_dwr_phase
    if phase is None:
        return None
    authority_path = args.task035d_significant_channel_authority
    if authority_path is None:
        raise SystemExit(
            "Task035d selective-face significant-channel authority is required."
        )
    authority_path = (
        authority_path if authority_path.is_absolute() else ROOT / authority_path
    ).resolve()
    try:
        authority = json.loads(authority_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            "Task035d selective-face significant-channel authority is "
            f"unreadable: {exc}"
        ) from exc
    if not isinstance(authority, dict):
        raise SystemExit(
            "Task035d selective-face significant-channel authority must be "
            "one JSON object."
        )
    try:
        authority_relative = authority_path.relative_to(ROOT).as_posix()
    except ValueError:
        authority_relative = None
    authority_tracked = bool(
        authority_relative is not None
        and subprocess.run(
            [
                "git",
                "ls-files",
                "--error-unmatch",
                "--",
                authority_relative,
            ],
            cwd=ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        ).returncode
        == 0
    )
    authority_sha = _sha256(authority_path)
    authority_checks = {
        "tracked": authority_tracked,
        "sha256": (authority_sha == args.task035d_significant_channel_authority_sha256),
        "schema": (
            authority.get("schema_version")
            == "task035b.significant-channel-reference.v1"
        ),
        "pass": authority.get("pass") is True,
        "twelve_channels": (
            authority.get("significant_channel_selection", {}).get("channel_count")
            == 12
            and len(authority.get("channels", ())) == 12
        ),
    }
    failures = [
        f"significant_channel_{name}"
        for name, passed in authority_checks.items()
        if not passed
    ]
    snapshot_gate = None
    if phase == "enriched-evaluate":
        snapshot_path = args.task035d_selective_face_coarse_manifest
        if snapshot_path is None:
            raise SystemExit(
                "Task035d selective-face enriched phase requires the coarse manifest."
            )
        snapshot_path = (
            snapshot_path if snapshot_path.is_absolute() else ROOT / snapshot_path
        ).resolve()
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SystemExit(
                f"Task035d selective-face coarse manifest is unreadable: {exc}"
            ) from exc
        if not isinstance(snapshot, dict):
            raise SystemExit(
                "Task035d selective-face coarse manifest must be one JSON object."
            )
        arrays_path = snapshot_path.parent / str(
            snapshot.get("arrays", {}).get("path", "")
        )
        observed_arrays_sha = (
            _sha256(arrays_path)
            if arrays_path.parent == snapshot_path.parent and arrays_path.is_file()
            else None
        )
        snapshot_artifact_gate = task035d_selective_face_coarse_snapshot_gate(
            snapshot,
            expected_source_sha=str(args.verified_clean_sha),
            expected_plan_sha256=(TASK035D_LOCAL_H_PLAN_FILE_SHA256),
            expected_significant_channel_authority_sha256=(
                str(args.task035d_significant_channel_authority_sha256)
            ),
            observed_arrays_sha256=observed_arrays_sha,
        )
        snapshot_checks = {
            "provided_manifest_sha256": (
                _sha256(snapshot_path)
                == args.task035d_selective_face_coarse_manifest_sha256
            ),
            "artifact_gate": snapshot_artifact_gate["pass"] is True,
        }
        failures.extend(
            f"coarse_snapshot_{name}"
            for name, passed in snapshot_checks.items()
            if not passed
        )
        snapshot_gate = {
            "path": _path_from_root(snapshot_path),
            "sha256": _sha256(snapshot_path),
            "arrays_path": _path_from_root(arrays_path),
            "arrays_sha256": observed_arrays_sha,
            "checks": snapshot_checks,
            "artifact_gate": snapshot_artifact_gate,
        }
        args.task035d_selective_face_coarse_manifest = snapshot_path
    args.task035d_significant_channel_authority = authority_path
    gate_checks = {
        "significant_channel_authority": (
            bool(authority_checks)
            and all(value is True for value in authority_checks.values())
        ),
        "phase_endpoint_scope": (
            (
                phase == "coarse-snapshot"
                and args.task035d_candidate_id == TASK035D_LOCAL_H_PLAN_NAME
            )
            or (
                phase == "enriched-evaluate"
                and args.task035d_candidate_id == TASK035D_SELECTIVE_FACE_PLAN_NAME
            )
        ),
        "coarse_snapshot": (
            snapshot_gate is None
            if phase == "coarse-snapshot"
            else bool(
                snapshot_gate
                and snapshot_gate["checks"]["provided_manifest_sha256"] is True
                and snapshot_gate["checks"]["artifact_gate"] is True
            )
        ),
        "cross_trace_without_dense_schur": True,
    }
    failures.extend(name for name, passed in gate_checks.items() if not passed)
    failures = list(dict.fromkeys(failures))
    gate = {
        "schema_version": ("task035d.selective-face-cross-trace-launch-gate.v1"),
        "phase": phase,
        "pass": not failures,
        "checks": gate_checks,
        "failures": failures,
        "significant_channel_authority": {
            "path": _path_from_root(authority_path),
            "sha256": authority_sha,
            "checks": authority_checks,
        },
        "coarse_snapshot": snapshot_gate,
        "same_trace_only": False,
        "cross_trace_primal_prolongation": True,
        "dense_local_schur_persistence": False,
    }
    if failures:
        raise SystemExit(f"Task035d selective-face launch inputs failed: {failures}")
    return gate


def _validate_p4_gate(args: argparse.Namespace) -> dict[str, Any] | None:
    if args.degree != 4:
        return None
    if args.p3_gate_record is None:
        raise SystemExit("p4 is locked: --p3-gate-record is required.")
    if args.p4_trace_record is None:
        raise SystemExit("p4 is locked: --p4-trace-record is required.")
    path = (
        args.p3_gate_record
        if args.p3_gate_record.is_absolute()
        else ROOT / args.p3_gate_record
    )
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"p4 is locked: cannot read p3 gate record: {exc}") from exc
    resource = record.get("resource_authority") or {}
    memory = resource.get("memory_authority_gib")
    workstation_h3 = bool(args.task034_p4_h3_added_point)
    memory_threshold_gib = (
        float(args.warning_gib)
        if workstation_h3 and isinstance(args.warning_gib, (int, float))
        else 10.0
    )
    memory_gate_name = (
        "memory_below_live_task034_warning" if workstation_h3 else "memory_below_10_gib"
    )
    checks = {
        "p3_degree": record.get("degree") == 3,
        "same_h": float(record.get("h_nm", -1.0)) == args.h_nm,
        "full_solve": record.get("run_kind") == "full-solve",
        "reference_pass": record.get("status") == "full3d_reference_pass",
        "no_swap": record.get("no_swap") is True,
        memory_gate_name: isinstance(memory, (int, float))
        and float(memory) < memory_threshold_gib,
    }
    failures = [name for name, passed in checks.items() if not passed]
    if failures:
        raise SystemExit(f"p4 is locked; failed p3 gates: {failures}")
    trace_path = (
        args.p4_trace_record
        if args.p4_trace_record.is_absolute()
        else ROOT / args.p4_trace_record
    )
    try:
        trace_record = json.loads(trace_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(
            f"p4 is locked: cannot read four-mode trace record: {exc}"
        ) from exc
    trace_gates = trace_record.get("gates") or {}
    trace_checks = {
        "record_type": (
            trace_record.get("record_type") == "p4_four_mode_matched_trace_aggregate"
        ),
        "status": (trace_record.get("status") == "p4_four_mode_matched_trace_pass"),
        "four_mode_trace_pass": (trace_gates.get("p4_four_mode_matched_trace") is True),
        "mpi_identity_pass": (trace_gates.get("mpi1_mpi4_compact_identity") is True),
        "same_current_source": (
            trace_record.get("source_commit_sha") == args.verified_clean_sha
        ),
    }
    trace_failures = [name for name, passed in trace_checks.items() if not passed]
    if trace_failures:
        raise SystemExit(
            f"p4 is locked; failed four-mode trace gates: {trace_failures}"
        )
    return {
        "p3": {
            "path": _path_from_root(path),
            "sha256": _sha256(path),
            "checks": checks,
        },
        "p4_four_mode_trace": {
            "path": _path_from_root(trace_path),
            "sha256": _sha256(trace_path),
            "checks": trace_checks,
        },
        "task034_p4_h3_added_point": workstation_h3,
        "p3_memory_threshold_gib": memory_threshold_gib,
        "pass": True,
    }


def _sampler_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    def maximum(name: str) -> float | None:
        values = [
            float(row[name]) for row in rows if isinstance(row.get(name), (int, float))
        ]
        return max(values) if values else None

    def delta(name: str) -> int | None:
        values = [
            int(row[name]) for row in rows if isinstance(row.get(name), (int, float))
        ]
        return max(values) - min(values) if values else None

    worker_mb = maximum("worker_rank_rss_sum_mb")
    worker_pss_mb = maximum("worker_rank_pss_sum_mb")
    worker_uss_mb = maximum("worker_rank_uss_sum_mb")
    worker_shared_mb = maximum("worker_rank_shared_sum_mb")
    worker_smaps_swap_mb = maximum("worker_rank_smaps_swap_sum_mb")
    process_tree_mb = maximum("mpi_process_tree_rss_mb")
    process_tree_swap_mb = maximum("mpi_process_tree_swap_mb")
    dedicated_rows = [row for row in rows if row.get("job_cgroup_dedicated") is True]
    observed_cgroup_current_mb = maximum("container_cgroup_current_mb")
    observed_cgroup_swap_mb = maximum("container_swap_current_mb")
    dedicated_cgroup_values = [
        float(row["container_cgroup_current_mb"])
        for row in dedicated_rows
        if isinstance(row.get("container_cgroup_current_mb"), (int, float))
    ]
    dedicated_swap_values = [
        float(row["container_swap_current_mb"])
        for row in dedicated_rows
        if isinstance(row.get("container_swap_current_mb"), (int, float))
    ]
    cgroup_mb = max(dedicated_cgroup_values) if dedicated_cgroup_values else None
    swap_mb = max(dedicated_swap_values) if dedicated_swap_values else None
    cgroup_peak_mb = maximum("container_cgroup_peak_mb")
    memory_authority_mb = (
        None
        if process_tree_mb is None
        else max(process_tree_mb, float(cgroup_mb or 0.0))
    )
    combined_authority_mb = memory_authority_mb
    worker_rank_counts: list[int] = []
    per_rank_smaps_peaks: dict[str, dict[str, float]] = {}
    per_rank_rss_peaks: dict[str, float] = {}
    fully_readable_mpi8_smaps_sample_count = 0
    for row in rows:
        try:
            workers = json.loads(str(row.get("worker_rank_rss_mb_json", "[]")))
        except json.JSONDecodeError:
            continue
        if isinstance(workers, list):
            worker_rank_counts.append(len(workers))
            for worker in workers:
                if not isinstance(worker, dict):
                    continue
                rank = worker.get("rank")
                rss = worker.get("rss_mb")
                if isinstance(rank, int) and isinstance(rss, (int, float)):
                    key = str(rank)
                    per_rank_rss_peaks[key] = max(
                        per_rank_rss_peaks.get(key, 0.0),
                        float(rss),
                    )
        try:
            smaps = json.loads(str(row.get("worker_rank_smaps_rollup_json", "[]")))
        except json.JSONDecodeError:
            continue
        if not isinstance(smaps, list):
            continue
        smaps_ranks = {
            worker.get("rank")
            for worker in smaps
            if isinstance(worker, dict) and isinstance(worker.get("rank"), int)
        }
        if row.get("worker_rank_smaps_readable_count") == 8 and smaps_ranks == set(
            range(8)
        ):
            fully_readable_mpi8_smaps_sample_count += 1
        for worker in smaps:
            if not isinstance(worker, dict) or not isinstance(
                worker.get("rank"),
                int,
            ):
                continue
            key = str(worker["rank"])
            peaks = per_rank_smaps_peaks.setdefault(key, {})
            for name in (
                "rss_mb",
                "pss_mb",
                "uss_mb",
                "shared_mb",
                "anonymous_mb",
                "swap_mb",
                "swap_pss_mb",
            ):
                value = worker.get(name)
                if isinstance(value, (int, float)):
                    peaks[name] = max(
                        peaks.get(name, 0.0),
                        float(value),
                    )
    return {
        "poll_interval_seconds": None,
        "sample_count": len(rows),
        "max_simultaneous_worker_rss_mb": worker_mb,
        "max_simultaneous_worker_pss_mb": worker_pss_mb,
        "max_simultaneous_worker_uss_mb": worker_uss_mb,
        "max_simultaneous_worker_shared_mb": worker_shared_mb,
        "max_simultaneous_worker_smaps_swap_mb": worker_smaps_swap_mb,
        "per_rank_rss_peak_mb": per_rank_rss_peaks,
        "per_rank_smaps_rollup_peak_mb": per_rank_smaps_peaks,
        "max_worker_rank_smaps_readable_count": maximum(
            "worker_rank_smaps_readable_count"
        ),
        "fully_readable_mpi8_smaps_sample_count": (
            fully_readable_mpi8_smaps_sample_count
        ),
        "max_process_tree_rss_mb": process_tree_mb,
        "max_process_tree_swap_mb": process_tree_swap_mb,
        "dedicated_job_cgroup_observed": bool(dedicated_rows),
        "max_container_cgroup_current_mb": cgroup_mb,
        "max_container_cgroup_peak_mb": cgroup_peak_mb,
        "max_container_swap_current_mb": swap_mb,
        "max_container_cgroup_current_observed_mb": (observed_cgroup_current_mb),
        "max_container_swap_current_observed_mb": observed_cgroup_swap_mb,
        "memory_authority_mb": memory_authority_mb,
        "memory_authority_gib": (
            None if memory_authority_mb is None else memory_authority_mb / 1024.0
        ),
        "combined_memory_swap_authority_mb": combined_authority_mb,
        "combined_memory_swap_authority_gib": (
            None if combined_authority_mb is None else combined_authority_mb / 1024.0
        ),
        "max_observed_worker_rank_count": (
            max(worker_rank_counts) if worker_rank_counts else 0
        ),
        "pswpin_delta_pages": delta("wsl_pswpin_pages"),
        "pswpout_delta_pages": delta("wsl_pswpout_pages"),
        "stage_peaks": _stage_peaks(rows) if rows else [],
    }


def _factorization_stage_seen(events: list[dict[str, Any]]) -> bool:
    return any(
        str(event.get("stage"))
        in {
            "before_ksp_setup",
            "after_ksp_setup_factorized",
            "before_ksp_solve",
            "after_ksp_solve",
        }
        for event in events
    )


def _solve_stage_seen(events: list[dict[str, Any]]) -> bool:
    return any(
        str(event.get("stage"))
        in {
            "stage4_dtn_augmented_solve",
            "before_ksp_solve",
            "during_ksp_solve_peak",
            "after_ksp_solve",
        }
        for event in events
    )


def _task035e_blind_candidate_solver_gate(
    args: argparse.Namespace,
    solver_summary: Mapping[str, Any],
    *,
    plan_gate: Mapping[str, Any] | None,
    live_resource_gate: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Qualify only the actual multilevel variable-trace candidate solve."""

    petsc = solver_summary.get("linear_solve_petsc_options")
    petsc = petsc if isinstance(petsc, Mapping) else {}
    local_h = solver_summary.get("stage4_local_h_constraint_audit")
    local_h = local_h if isinstance(local_h, Mapping) else {}
    mesh = local_h.get("mesh")
    mesh = mesh if isinstance(mesh, Mapping) else {}
    degree_plan = local_h.get("degree_plan")
    degree_plan = (
        degree_plan if isinstance(degree_plan, Mapping) else {}
    )
    degree_counts = degree_plan.get("cell_degree_counts")
    degree_counts = (
        degree_counts if isinstance(degree_counts, Mapping) else {}
    )
    physical_trace = local_h.get("physical_trace")
    physical_trace = (
        physical_trace if isinstance(physical_trace, Mapping) else {}
    )
    trace_constraints = local_h.get("trace_constraints")
    trace_constraints = (
        trace_constraints if isinstance(trace_constraints, Mapping) else {}
    )
    checks = {
        "launch_plan_gate": bool(
            plan_gate is not None and plan_gate.get("pass") is True
        ),
        "variable_p_backend_actual": (
            solver_summary.get("stage4_full3d_assembly_backend_actual")
            == TASK035E_BLIND_CANDIDATE_BACKEND
            and solver_summary.get("stage4_variable_p_active") is True
            and solver_summary.get("stage4_local_h_active") is True
            and solver_summary.get(
                "stage4_assembly_time_cell_static_condensation"
            )
            is True
        ),
        "multilevel_plan_executed": (
            local_h.get("schema_version")
            == "task035e.stage4-multilevel-local-hp-reduction-authority.v1"
            and local_h.get("status")
            == "stage4_local_h_reduction_authority_pass"
            and local_h.get("pass") is True
            and mesh.get("schema_version")
            == "task035e.stage4-multilevel-local-h-mesh.v1"
            and mesh.get("maximum_level") in {1, 2}
            and mesh.get("true_multilevel")
            is (mesh.get("maximum_level") == 2)
            and mesh.get("plan_file_sha256")
            == args.stage4_local_h_refinement_plan_sha256
        ),
        "complete_variable_p_leaf_map_executed": (
            local_h.get("variable_trace_from_cell_degrees") is True
            and degree_plan.get("schema_version")
            == "task035e.local-h-variable-exact-sequence-plan.v1"
            and degree_plan.get(
                "cell_driven_variable_trace_component_complete"
            )
            is True
            and all(
                isinstance(degree_counts.get(f"p{degree}"), int)
                and degree_counts[f"p{degree}"] >= 0
                for degree in (4, 5, 6)
            )
            and sum(
                degree_counts[f"p{degree}"] > 0
                for degree in (4, 5, 6)
            )
            >= 2
            and physical_trace.get("variable_trace_opt_in") is True
            and len(
                set(physical_trace.get("trace_degree_values", ()))
            )
            >= 2
            and set(
                physical_trace.get("trace_degree_values", ())
            ).issubset({4, 5, 6})
        ),
        "periodic_hanging_trace_executed": (
            trace_constraints.get("pass") is True
            and trace_constraints.get("local_variable_trace_implemented")
            is True
            and trace_constraints.get("selective_trace_action")
            == "cell_driven_p4_p5_p6_exact_sequence_trace"
            and set(trace_constraints.get("constraint_kinds", ()))
            == {"floquet", "hanging"}
        ),
        "default_direct_mumps": (
            solver_summary.get("petsc_direct_solver_profile") == "default"
            and solver_summary.get("linear_solve_method") == "direct_lu"
            and solver_summary.get("selected_parallel_lu_solver_type")
            == "mumps"
            and solver_summary.get("actual_ksp_type") == "preonly"
            and solver_summary.get("actual_pc_type") == "lu"
            and solver_summary.get("actual_pc_factor_solver_type") == "mumps"
            and petsc.get("ksp_type") == "preonly"
            and petsc.get("pc_type") == "lu"
            and petsc.get("pc_factor_mat_solver_type") == "mumps"
            and not any(
                str(name).startswith("mat_mumps_icntl_")
                for name in petsc
            )
        ),
        "live_resource_gate_at_most_11_gib": bool(
            live_resource_gate is not None
            and live_resource_gate.get("pass") is True
            and live_resource_gate.get("memory_cap_at_most_11_gib") is True
            and live_resource_gate.get("maximum_swap_authority_bytes") == 0
        ),
    }
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "task035e.blind-candidate-solver-gate.v1",
        "pass": not failures,
        "checks": checks,
        "failures": failures,
    }


def _task035e_blind_live_role_evidence_gate(
    args: argparse.Namespace,
    *,
    evidence_path: Path,
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Independently replay the live current/shadow evidence authority."""

    evidence = payload if isinstance(payload, Mapping) else {}
    role = str(args.task035e_blind_output_role)
    common_checks = {
        "file_mode_0600": (
            evidence_path.is_file()
            and (evidence_path.stat().st_mode & 0o777) == 0o600
        ),
        "source_trial_cycle_mpi8": (
            evidence.get("source_sha") == args.verified_clean_sha
            and evidence.get("trial_id") == args.task035e_blind_trial_id
            and evidence.get("cycle_index")
            == args.task035e_blind_cycle_index
            and evidence.get("mpi_size") == 8
            and evidence.get("formal_mpi8_qualified") is True
        ),
        "ordinary_default_unchanged": (
            evidence.get("ordinary_default_changed") is False
        ),
    }
    role_checks: dict[str, bool]
    details: dict[str, Any] = {"role": role}
    if role == "current":
        unsigned = dict(evidence)
        stored_payload_sha = unsigned.pop(
            "manifest_payload_sha256",
            None,
        )
        plan = evidence.get("plan_identity")
        plan = plan if isinstance(plan, Mapping) else {}
        capability = evidence.get("capability_credit")
        capability = (
            capability if isinstance(capability, Mapping) else {}
        )
        shard_rows = evidence.get("shards")
        shard_rows = shard_rows if isinstance(shard_rows, list) else []
        shard_checks = []
        shard_ranks = []
        for row in shard_rows:
            if not isinstance(row, Mapping):
                shard_checks.append(False)
                continue
            try:
                shard_rank = int(row.get("rank", -1))
            except (TypeError, ValueError):
                shard_rank = -1
            shard_path = _task035e_snapshot_shard_path(
                evidence_path,
                row.get("path"),
                rank=shard_rank,
            )
            shard_ranks.append(shard_rank)
            shard_checks.append(
                bool(
                    shard_path is not None
                    and shard_path.is_file()
                    and (shard_path.stat().st_mode & 0o777) == 0o600
                    and shard_path.stat().st_size == row.get("bytes")
                    and _sha256(shard_path) == row.get("file_sha256")
                )
            )
        role_checks = {
            "schema_status_role": (
                evidence.get("schema_version")
                == TASK035E_CURRENT_SNAPSHOT_SCHEMA
                and evidence.get("status")
                == "multigoal_current_live_snapshot_pass"
                and evidence.get("pass") is True
                and evidence.get("role") == "current_blind_state"
            ),
            "payload_self_hash": (
                valid_hex_digest(stored_payload_sha, 64)
                and _task035e_safe_namespaced_json_sha256(
                    unsigned,
                    namespace="task035e.multigoal-current-manifest.v1",
                )
                == stored_payload_sha
            ),
            "executed_plan_bound": (
                plan.get("file_sha256")
                == args.stage4_local_h_refinement_plan_sha256
                and valid_hex_digest(plan.get("payload_sha256"), 64)
                and valid_hex_digest(
                    plan.get("forest_leaf_catalog_sha256"),
                    64,
                )
                and valid_hex_digest(
                    plan.get("cell_degree_plan_sha256"),
                    64,
                )
            ),
            "eight_snapshot_shards_hash_bound": (
                len(shard_rows) == 8
                and shard_ranks == list(range(8))
                and all(shard_checks)
            ),
            "capability_not_overclaimed": (
                capability.get("current_primal_snapshot_complete") is True
                and all(
                    capability.get(name) is False
                    for name in (
                        "multi_goal_adjoint_complete",
                        "dwr_complete",
                        "local_h_transfer_complete",
                        "shadow_effectivity_complete",
                        "accuracy_credit",
                    )
                )
            ),
        }
        details["payload_sha256"] = stored_payload_sha
    else:
        unsigned = dict(evidence)
        stored_payload_sha = unsigned.pop("payload_sha256", None)
        current_snapshot = evidence.get("current_snapshot")
        current_snapshot = (
            current_snapshot
            if isinstance(current_snapshot, Mapping)
            else {}
        )
        gradient = evidence.get("goal_gradient_inventory")
        gradient = gradient if isinstance(gradient, Mapping) else {}
        gradient_unsigned = dict(gradient)
        gradient_sha = gradient_unsigned.pop(
            "gradient_inventory_sha256",
            None,
        )
        actual = evidence.get("actual_dwr")
        actual = actual if isinstance(actual, Mapping) else {}
        actual_unsigned = dict(actual)
        actual_report_sha = actual_unsigned.pop("report_sha256", None)
        implementation = actual.get("implementation_identity")
        implementation = (
            implementation if isinstance(implementation, Mapping) else {}
        )
        implementation_unsigned = dict(implementation)
        implementation_sha = implementation_unsigned.pop(
            "implementation_sha256",
            None,
        )
        aggregate = actual.get("aggregate_identities")
        aggregate = aggregate if isinstance(aggregate, Mapping) else {}
        shadow_plan_identity = actual.get("shadow_plan_identity")
        shadow_plan_identity = (
            shadow_plan_identity
            if isinstance(shadow_plan_identity, Mapping)
            else {}
        )
        goal_inventory = actual.get("goal_inventory")
        goal_inventory = (
            goal_inventory
            if isinstance(goal_inventory, Mapping)
            else {}
        )
        layout_identity = actual.get("layout_identity")
        layout_identity = (
            layout_identity
            if isinstance(layout_identity, Mapping)
            else {}
        )
        operator_identity = actual.get("operator_identity")
        operator_identity = (
            operator_identity
            if isinstance(operator_identity, Mapping)
            else {}
        )
        enriched_residual = actual.get("enriched_current_residual")
        enriched_residual = (
            enriched_residual
            if isinstance(enriched_residual, Mapping)
            else {}
        )
        actual_goals = actual.get("goals")
        actual_goals = actual_goals if isinstance(actual_goals, list) else []
        signed = evidence.get("signed_dwr_delta")
        signed = signed if isinstance(signed, Mapping) else {}
        capability = evidence.get("capability_credit")
        capability = (
            capability if isinstance(capability, Mapping) else {}
        )
        rank_audits = evidence.get("rank_pipeline_audits")
        rank_audits = (
            rank_audits if isinstance(rank_audits, list) else []
        )
        rank_rows_valid = bool(
            len(rank_audits) == 8
            and all(
                isinstance(row, Mapping)
                and row.get("rank") == rank
                and all(
                    isinstance(row.get(name), Mapping)
                    and row[name].get("pass") is True
                    for name in (
                        "transfer",
                        "projection",
                        "primal_extraction",
                    )
                )
                for rank, row in enumerate(rank_audits)
            )
        )
        expected_adjoint_system_sha = (
            _task035e_safe_namespaced_json_sha256(
                {
                    "shadow_plan_identity": shadow_plan_identity,
                    "layout_identity": layout_identity,
                    "operator_identity": operator_identity,
                },
                namespace="task035e.actual-dwr-adjoint-system.v1",
            )
        )
        expected_module_sha = _sha256(
            ROOT / "src" / "adaptivity" / "task035e_actual_dwr.py"
        )
        role_checks = {
            "schema_status_role": (
                evidence.get("schema_version")
                == TASK035E_SHADOW_EVALUATION_SCHEMA
                and evidence.get("status")
                == "live_shadow_59_goal_actual_dwr_pass"
                and evidence.get("pass") is True
                and evidence.get("shadow_kind") == role
            ),
            "payload_self_hash": (
                valid_hex_digest(stored_payload_sha, 64)
                and _task035e_safe_namespaced_json_sha256(
                    unsigned,
                    namespace="task035e.live-shadow-evaluation-payload.v1",
                )
                == stored_payload_sha
            ),
            "current_snapshot_bound": (
                current_snapshot.get("manifest_file_sha256")
                == args.task035e_current_snapshot_manifest_sha256
                and valid_hex_digest(
                    current_snapshot.get("manifest_payload_sha256"),
                    64,
                )
                and valid_hex_digest(
                    current_snapshot.get("current_plan_file_sha256"),
                    64,
                )
            ),
            "shadow_plan_bound": (
                evidence.get("shadow_plan_file_sha256")
                == args.stage4_local_h_refinement_plan_sha256
                and actual.get("shadow_kind") == role
                and shadow_plan_identity.get("file_sha256")
                == args.stage4_local_h_refinement_plan_sha256
            ),
            "formal_goal_inventory_bound": (
                evidence.get("formal_goal_count") == len(FORMAL_GOAL_IDS)
                and evidence.get("formal_goal_inventory_sha256")
                == FORMAL_GOAL_INVENTORY_SHA256
                and gradient.get("formal_goal_count")
                == len(FORMAL_GOAL_IDS)
                and gradient.get("formal_goal_inventory_sha256")
                == FORMAL_GOAL_INVENTORY_SHA256
                and goal_inventory.get("ordered_goal_ids")
                == list(FORMAL_GOAL_IDS)
                and len(signed) == len(FORMAL_GOAL_IDS)
                and set(signed) == set(FORMAL_GOAL_IDS)
            ),
            "gradient_inventory_replayed": (
                gradient.get("schema_version")
                == "task035e.formal-59-goal-live-gradients.v1"
                and
                gradient.get("status")
                == "formal_59_goal_live_gradients_pass"
                and gradient.get("pass") is True
                and valid_hex_digest(gradient_sha, 64)
                and _task035e_safe_namespaced_json_sha256(
                    gradient_unsigned,
                    namespace="task035e.formal-gradient-inventory.v1",
                )
                == gradient_sha
            ),
            "actual_dwr_report_replayed": (
                actual.get("schema_version")
                == "task035e.actual-live-shadow-dwr.v1"
                and actual.get("status") == "actual_live_shadow_dwr_pass"
                and actual.get("pass") is True
                and actual.get("source_sha") == args.verified_clean_sha
                and goal_inventory.get("formal_goal_count")
                == len(FORMAL_GOAL_IDS)
                and goal_inventory.get("formal_goal_inventory_sha256")
                == FORMAL_GOAL_INVENTORY_SHA256
                and valid_hex_digest(actual_report_sha, 64)
                and _task035e_safe_namespaced_json_sha256(
                    actual_unsigned,
                    namespace="task035e.actual-live-shadow-dwr-report.v1",
                )
                == actual_report_sha
                and len(actual_goals) == len(FORMAL_GOAL_IDS)
                and tuple(
                    row.get("goal_id")
                    for row in actual_goals
                    if isinstance(row, Mapping)
                )
                == FORMAL_GOAL_IDS
                and all(
                    isinstance(row, Mapping)
                    and valid_hex_digest(
                        row.get("goal_evidence_sha256"),
                        64,
                    )
                    and _task035e_safe_namespaced_json_sha256(
                        {
                            key: value
                            for key, value in row.items()
                            if key != "goal_evidence_sha256"
                        },
                        namespace="task035e.actual-dwr.per-goal.v1",
                    )
                    == row.get("goal_evidence_sha256")
                    and isinstance(
                        signed.get(row.get("goal_id")),
                        (int, float),
                    )
                    and not isinstance(
                        signed.get(row.get("goal_id")),
                        bool,
                    )
                    and math.isfinite(
                        float(signed[row.get("goal_id")])
                    )
                    and signed[row.get("goal_id")]
                    == row.get("signed_eta_real_zH_r")
                    for row in actual_goals
                )
            ),
            "actual_dwr_implementation_bound": (
                implementation.get("schema_version")
                == "task035e.actual-dwr-implementation-identity.v1"
                and implementation.get("module_file_sha256")
                == expected_module_sha
                and valid_hex_digest(implementation_sha, 64)
                and _task035e_safe_namespaced_json_sha256(
                    implementation_unsigned,
                    namespace="task035e.actual-dwr-implementation.v1",
                )
                == implementation_sha
                and aggregate.get("implementation_sha256")
                == implementation_sha
                and aggregate.get("primal_residual_sha256")
                == enriched_residual.get("partition_bound_sha256")
                and valid_hex_digest(
                    enriched_residual.get("partition_bound_sha256"),
                    64,
                )
                and aggregate.get("adjoint_system_sha256")
                == expected_adjoint_system_sha
            ),
            "rank_pipeline_and_capability": (
                rank_rows_valid
                and evidence.get("rank_pipeline_catalog_sha256")
                == _task035e_safe_namespaced_json_sha256(
                    rank_audits,
                    namespace="task035e.shadow-pipeline-rank-catalog.v1",
                )
                and set(capability)
                == {
                    "current_primal_snapshot_complete",
                    "current_to_shadow_injection_complete",
                    "local_h_transfer_complete",
                    "formal_59_goal_gradient_construction_complete",
                    "actual_enriched_residual_complete",
                    "actual_59_goal_adjoint_complete",
                    "actual_signed_dwr_complete",
                    "shadow_endpoint_effectivity_complete",
                    "accuracy_credit",
                }
                and capability.get("current_primal_snapshot_complete")
                is True
                and capability.get("current_to_shadow_injection_complete")
                is True
                and capability.get("local_h_transfer_complete")
                is (role == "h-shadow")
                and capability.get(
                    "formal_59_goal_gradient_construction_complete"
                )
                is True
                and capability.get("actual_enriched_residual_complete")
                is True
                and capability.get("actual_59_goal_adjoint_complete")
                is True
                and capability.get("actual_signed_dwr_complete") is True
                and capability.get("shadow_endpoint_effectivity_complete")
                is False
                and capability.get("accuracy_credit") is False
                and evidence.get("hidden_reference_consumed") is False
                and evidence.get("endpoint_delta_used_as_dwr") is False
            ),
        }
        details.update(
            {
                "payload_sha256": stored_payload_sha,
                "gradient_inventory_sha256": gradient_sha,
                "actual_dwr_report_sha256": actual_report_sha,
                "actual_dwr_implementation_sha256": implementation_sha,
            }
        )
    checks = {**common_checks, **role_checks}
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "schema_version": "task035e.blind-live-role-evidence-gate.v1",
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "details": details,
    }


def _qualify(
    *,
    args: argparse.Namespace,
    solver_summary: dict[str, Any],
    events: list[dict[str, Any]],
    return_code: int,
    terminated_for_memory: bool,
    terminated_for_timeout: bool,
    terminated_for_authority_unreadable: bool,
    no_swap: bool,
    observed_worker_rank_count: int | None = None,
    resource_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    matrix = solver_summary.get("matrix_stats") or {}
    common = {
        "process_completed": return_code == 0,
        "not_terminated_for_memory": not terminated_for_memory,
        "not_terminated_for_timeout": not terminated_for_timeout,
        "live_authority_readable": not terminated_for_authority_unreadable,
        "all_expected_mpi_ranks_observed": (
            observed_worker_rank_count is None
            or observed_worker_rank_count == args.mpi_size
        ),
        "exact_positive_rows": (
            isinstance(matrix.get("matrix_rows"), (int, float))
            and float(matrix["matrix_rows"]) > 0.0
        ),
        "exact_positive_assembled_nnz": (
            isinstance(matrix.get("matrix_nnz_used"), (int, float))
            and float(matrix["matrix_nnz_used"]) > 0.0
        ),
        "polarization_identity": (
            solver_summary.get("polarization_kind") == args.polarization_kind
        ),
    }
    if args.run_kind == "assembly-only":
        checks = {
            **common,
            "diagnostic_assemble_only_status": (
                solver_summary.get("case_status") == "diagnostic_assemble_only"
            ),
            "assemble_only_flag": (
                solver_summary.get("matrix_diagnostics_assemble_only") is True
            ),
            "no_factorization_or_solve_stage": not _factorization_stage_seen(events),
            "ksp_iterations_zero": solver_summary.get("ksp_iterations") == 0,
            "no_swap": no_swap,
        }
    elif args.run_kind == "factorization-only":
        factor_inventory = solver_summary.get("stage4_dtn_factor_inventory")
        checks = {
            **common,
            "diagnostic_factorization_only_status": (
                solver_summary.get("case_status") == "diagnostic_factorization_only"
            ),
            "assemble_only_false": (
                solver_summary.get("matrix_diagnostics_assemble_only") is False
            ),
            "factorization_only_flag": (
                solver_summary.get("matrix_diagnostics_factorization_only") is True
            ),
            "factorization_stage_seen": _factorization_stage_seen(events),
            "solve_stage_not_seen": not _solve_stage_seen(events),
            "factor_inventory_recorded": isinstance(factor_inventory, dict),
            "ksp_iterations_zero": solver_summary.get("ksp_iterations") == 0,
            "official_result_false": solver_summary.get("official_result") is False,
            "no_swap": no_swap,
        }
    else:
        residual = solver_summary.get("linear_system_relative_residual")
        checks = {
            **common,
            "completed_status": solver_summary.get("case_status") == "completed",
            "official_result": solver_summary.get("official_result") is True,
            "assemble_only_false": (
                solver_summary.get("matrix_diagnostics_assemble_only") is False
            ),
            "factorization_only_false": (
                solver_summary.get("matrix_diagnostics_factorization_only") is False
            ),
            "ksp_converged": solver_summary.get("ksp_converged") is True,
            "true_residual_le_1e-9": _finite_number_le(
                residual,
                1.0e-9,
            ),
            "reference_exported": (
                solver_summary.get("full3d_reference_exported") is True
            ),
            "swap_policy_satisfied": args.allow_swap or no_swap,
        }
    task035d_solver_gate = None
    if args.task035d_case097_gate:
        if args.task035d_candidate_id == TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME:
            solver_gate_builder = task035d_case097_hp_factorial_bridge_solver_gate
        elif args.task035d_candidate_id == TASK035D_LEFT_GRATING_TOP_PLAN_NAME:
            solver_gate_builder = task035d_case097_left_grating_top_solver_gate
        elif args.task035d_candidate_id == TASK035D_COMBINED_HP_PLAN_NAME:
            solver_gate_builder = task035d_case097_combined_hp_solver_gate
        elif args.task035d_candidate_id == TASK035D_SELECTIVE_FACE_PLAN_NAME:
            solver_gate_builder = task035d_case097_selective_face_solver_gate
        elif args.task035d_candidate_id == TASK035D_LOCAL_H_PLAN_NAME:
            solver_gate_builder = task035d_case097_local_h_solver_gate
        elif args.task035d_candidate_id == "sidewall_z0_guard_v1":
            solver_gate_builder = task035d_case097_sidewall_guard_solver_gate
        else:
            solver_gate_builder = task035d_case097_t30_solver_gate
        task035d_solver_gate = solver_gate_builder(solver_summary)
        checks.update(
            {
                f"task035d_solver_{name}": bool(passed)
                for name, passed in task035d_solver_gate["checks"].items()
            }
        )
        resource = resource_summary if isinstance(resource_summary, dict) else {}
        per_rank_smaps = resource.get("per_rank_smaps_rollup_peak_mb")
        per_rank_smaps = per_rank_smaps if isinstance(per_rank_smaps, dict) else {}
        expected_ranks = {str(rank) for rank in range(8)}
        checks.update(
            {
                "task035d_all_rank_smaps_readable": (
                    resource.get("max_worker_rank_smaps_readable_count") == 8.0
                    and isinstance(
                        resource.get("fully_readable_mpi8_smaps_sample_count"),
                        (int, float),
                    )
                    and float(resource["fully_readable_mpi8_smaps_sample_count"]) > 0.0
                    and set(per_rank_smaps) == expected_ranks
                ),
                "task035d_pss_uss_peaks_recorded": (
                    isinstance(
                        resource.get("max_simultaneous_worker_pss_mb"),
                        (int, float),
                    )
                    and float(resource["max_simultaneous_worker_pss_mb"]) > 0.0
                    and isinstance(
                        resource.get("max_simultaneous_worker_uss_mb"),
                        (int, float),
                    )
                    and float(resource["max_simultaneous_worker_uss_mb"]) > 0.0
                    and all(
                        isinstance(values, dict)
                        and isinstance(values.get("pss_mb"), (int, float))
                        and isinstance(values.get("uss_mb"), (int, float))
                        for values in per_rank_smaps.values()
                    )
                ),
                "task035d_cgroup_ledger_recorded": (
                    isinstance(
                        resource.get("max_container_cgroup_current_observed_mb"),
                        (int, float),
                    )
                    and isinstance(
                        resource.get("max_container_cgroup_peak_mb"),
                        (int, float),
                    )
                ),
                "task035d_zero_swap": no_swap,
            }
        )
    failures = [name for name, passed in checks.items() if not passed]
    return {
        "pass": not failures,
        "checks": checks,
        "failures": failures,
        "task035d_case097_solver_gate": task035d_solver_gate,
    }


def _terminate(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    used_process_group = False
    if os.name == "posix":
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            used_process_group = True
        except OSError:
            used_process_group = False
    if not used_process_group:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if used_process_group:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except OSError:
                process.kill()
        else:
            process.kill()
        process.wait(timeout=10)


def _worker_command(args: argparse.Namespace, run_dir: Path) -> list[str]:
    command = [
        "mpiexec",
        "-n",
        str(args.mpi_size),
        sys.executable,
        "-m",
        "benchmarks.run_task033_full3d_watchdog",
        "--worker",
        "--degree",
        str(args.degree),
        "--h-nm",
        str(args.h_nm),
        "--polarization-kind",
        args.polarization_kind,
        "--run-kind",
        args.run_kind,
        "--mpi-size",
        str(args.mpi_size),
        "--profile",
        args.profile,
        "--stage4-full3d-assembly-backend",
        args.stage4_full3d_assembly_backend,
        "--run-dir",
        str(run_dir),
    ]
    if args.stage4_raw_tensor_cache:
        command.extend(
            (
                "--stage4-raw-tensor-cache",
                "--stage4-raw-tensor-cache-directory",
                str(args.stage4_raw_tensor_cache_directory),
            )
        )
    if args.warning_gib is not None:
        command.extend(("--warning-gib", str(args.warning_gib)))
    if args.terminate_gib is not None:
        command.extend(("--terminate-gib", str(args.terminate_gib)))
    if args.task035e_reference_certifier_gate:
        command.append("--task035e-reference-certifier-gate")
        if args.task035e_reference_resource_authority is not None:
            command.extend(
                (
                    "--task035e-reference-resource-authority",
                    str(args.task035e_reference_resource_authority),
                    "--task035e-reference-resource-authority-sha256",
                    str(
                        args.task035e_reference_resource_authority_sha256
                    ),
                )
            )
        if args.task035e_h5_factorization_authority is not None:
            command.extend(
                (
                    "--task035e-h5-factorization-authority",
                    str(args.task035e_h5_factorization_authority),
                    "--task035e-h5-factorization-authority-sha256",
                    str(
                        args.task035e_h5_factorization_authority_sha256
                    ),
                )
            )
        command.extend(
            (
                "--verified-clean-sha",
                str(args.verified_clean_sha),
            )
        )
    if args.task035e_blind_candidate_gate:
        command.extend(
            (
                "--task035e-blind-candidate-gate",
                "--task035e-blind-trial-id",
                str(args.task035e_blind_trial_id),
                "--task035e-blind-cycle-index",
                str(args.task035e_blind_cycle_index),
                "--task035e-blind-output-role",
                str(args.task035e_blind_output_role),
                "--stage4-local-h-refinement-plan",
                str(args.stage4_local_h_refinement_plan),
                "--stage4-local-h-refinement-plan-sha256",
                str(args.stage4_local_h_refinement_plan_sha256),
                "--verified-clean-sha",
                str(args.verified_clean_sha),
            )
        )
        if args.task035e_internal_probe_kind is not None:
            command.extend(
                (
                    "--task035e-internal-probe-kind",
                    str(args.task035e_internal_probe_kind),
                )
            )
            if args.task035e_internal_probe_kind == "dtn":
                command.extend(
                    (
                        "--task035e-probe-dtn-max-m",
                        str(args.task035e_probe_dtn_max_m),
                        "--task035e-probe-dtn-max-n",
                        str(args.task035e_probe_dtn_max_n),
                    )
                )
            elif args.task035e_internal_probe_kind == "postprocess":
                command.extend(
                    (
                        "--task035e-probe-surface-quadrature-degree",
                        str(
                            args
                            .task035e_probe_surface_quadrature_degree
                        ),
                    )
                )
        if not (
            args.task035e_blind_output_role == "current"
            and args.task035e_blind_cycle_index == 0
            and args.task035e_internal_probe_kind is None
        ):
            command.extend(
                (
                    "--task035e-current-snapshot-manifest",
                    str(args.task035e_current_snapshot_manifest),
                    "--task035e-current-snapshot-manifest-sha256",
                    str(
                        args.task035e_current_snapshot_manifest_sha256
                    ),
                )
            )
            if args.task035e_internal_probe_kind is None:
                command.extend(
                    (
                        "--task035e-transition-action",
                        str(args.task035e_transition_action),
                        "--task035e-transition-action-sha256",
                        str(args.task035e_transition_action_sha256),
                    )
                )
    if args.task035c_p6_h10_gate:
        command.extend(
            (
                "--task035c-p6-h10-gate",
                "--task035c-p6-preflight-authority",
                str(args.task035c_p6_preflight_authority),
                "--task035c-p6-preflight-sha256",
                str(args.task035c_p6_preflight_sha256),
                "--verified-clean-sha",
                str(args.verified_clean_sha),
            )
        )
    if args.task035d_case097_gate:
        plan_options = (
            (
                "--stage4-local-h-refinement-plan",
                str(args.stage4_local_h_refinement_plan),
                "--stage4-local-h-refinement-plan-sha256",
                str(args.stage4_local_h_refinement_plan_sha256),
            )
            if args.task035d_candidate_id in TASK035D_LOCAL_H_CANDIDATES
            else (
                "--stage4-variable-p-cell-degree-plan",
                str(args.stage4_variable_p_cell_degree_plan),
                "--stage4-variable-p-cell-degree-plan-sha256",
                str(args.stage4_variable_p_cell_degree_plan_sha256),
            )
        )
        command.extend(
            (
                "--task035d-case097-gate",
                "--task035d-candidate-id",
                str(args.task035d_candidate_id),
                *plan_options,
                "--task035d-plan-authority",
                str(args.task035d_plan_authority),
                "--task035d-plan-authority-sha256",
                str(args.task035d_plan_authority_sha256),
                "--verified-clean-sha",
                str(args.verified_clean_sha),
            )
        )
        if args.task035d_nested_p_dwr_phase is not None:
            command.extend(
                (
                    "--task035d-nested-p-dwr-phase",
                    str(args.task035d_nested_p_dwr_phase),
                    "--task035d-significant-channel-authority",
                    str(args.task035d_significant_channel_authority),
                    "--task035d-significant-channel-authority-sha256",
                    str(args.task035d_significant_channel_authority_sha256),
                    "--task035d-nested-p-pair-authority",
                    str(args.task035d_nested_p_pair_authority),
                    "--task035d-nested-p-pair-authority-sha256",
                    str(args.task035d_nested_p_pair_authority_sha256),
                )
            )
            if args.task035d_nested_p_dwr_phase == "enriched-evaluate":
                command.extend(
                    (
                        "--task035d-coarse-snapshot-manifest",
                        str(args.task035d_coarse_snapshot_manifest),
                        "--task035d-coarse-snapshot-manifest-sha256",
                        str(args.task035d_coarse_snapshot_manifest_sha256),
                    )
                )
        elif args.task035d_selective_face_dwr_phase is not None:
            command.extend(
                (
                    "--task035d-selective-face-dwr-phase",
                    str(args.task035d_selective_face_dwr_phase),
                    "--task035d-significant-channel-authority",
                    str(args.task035d_significant_channel_authority),
                    "--task035d-significant-channel-authority-sha256",
                    str(args.task035d_significant_channel_authority_sha256),
                )
            )
            if args.task035d_selective_face_dwr_phase == "enriched-evaluate":
                command.extend(
                    (
                        "--task035d-selective-face-coarse-manifest",
                        str(args.task035d_selective_face_coarse_manifest),
                        ("--task035d-selective-face-coarse-manifest-sha256"),
                        str(args.task035d_selective_face_coarse_manifest_sha256),
                    )
                )
    if (
        args.parent_launch_descriptor is not None
        and args.parent_launch_descriptor_sha256 is not None
    ):
        command.extend(
            (
                "--parent-launch-descriptor",
                str(args.parent_launch_descriptor),
                "--parent-launch-descriptor-sha256",
                str(args.parent_launch_descriptor_sha256),
            )
        )
    return command


def _run_parent(args: argparse.Namespace) -> int:
    task035e_formal = bool(
        args.task035e_reference_certifier_gate
        or args.task035e_blind_candidate_gate
    )
    task035e_formal_runtime = (
        _validate_task035e_formal_runtime(
            require_private_worker_tmp=False,
        )
        if task035e_formal
        else None
    )
    if args.mpi_size < 1:
        raise SystemExit("--mpi-size must be positive.")
    if args.poll_interval < 0.05:
        raise SystemExit("--poll-interval must be at least 0.05 seconds.")
    effective = effective_memory_limit()
    if effective["effective_limit_bytes"] is None:
        raise SystemExit("Task034 effective WSL memory limit is unreadable.")
    environment_before = _resource_snapshot()
    if environment_before["host_available_bytes"] is None:
        raise SystemExit("Readable WSL MemAvailable is required.")
    if environment_before["wsl_total_bytes"] is None:
        raise SystemExit("Readable WSL MemTotal is required.")
    task035e_resource_policy = _apply_task035e_reference_dynamic_cap(
        args,
        environment_before,
    )
    if task035e_resource_policy is None:
        if args.warning_gib is None:
            args.warning_gib = float(effective["warning_bytes"]) / GIB
        if args.terminate_gib is None:
            args.terminate_gib = float(effective["termination_bytes"]) / GIB
    if args.warning_gib <= 0 or args.terminate_gib <= args.warning_gib:
        raise SystemExit("Require 0 < warning-gib < terminate-gib.")
    if args.timeout_seconds <= 0:
        raise SystemExit("--timeout-seconds must be positive.")
    if args.run_kind != "full-solve" and args.allow_swap:
        raise SystemExit(
            "assembly-only and factorization-only calibration forbid --allow-swap."
        )
    p4_gate = _validate_p4_gate(args)
    task035c_p6_gate = _validate_task035c_p6_preflight(args)
    task035e_resource_authority_gate = (
        _validate_task035e_reference_resource_authority(args)
    )
    task035e_h5_factorization_authority_gate = (
        _validate_task035e_h5_factorization_authority(args)
    )
    task035e_blind_candidate_plan_gate = (
        _validate_task035e_blind_candidate_plan(args)
    )
    task035e_current_snapshot_gate = (
        _validate_task035e_current_snapshot_input(args)
    )
    task035d_case097_gate = _validate_task035d_case097_plan(args)
    task035d_nested_p_gate = _validate_task035d_nested_p_inputs(args)
    task035d_selective_face_gate = _validate_task035d_selective_face_inputs(args)
    source_before = _source_provenance(args)
    if (
        args.task035d_case097_gate
        or args.task035e_reference_certifier_gate
        or args.task035e_blind_candidate_gate
    ):
        formal_status_before = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=ROOT,
            text=True,
        ).strip()
        if formal_status_before:
            raise SystemExit(
                "Task035d/Task035e formal PDE requires an actually clean "
                "source tree; "
                "commit the runner/checker and evidence before launch."
            )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = (
        args.run_dir
        or args.artifact_root
        / f"p{args.degree}_h{args.h_nm:g}_pol{args.polarization_kind}_{args.run_kind}_mpi{args.mpi_size}_{timestamp}"
    ).resolve()
    run_dir.mkdir(parents=True, exist_ok=False)
    if task035e_formal:
        run_dir.chmod(0o700)
    args.run_dir = run_dir
    parent_launch_token = secrets.token_hex(32)
    parent_launch_descriptor = run_dir / "parent_launch_descriptor.json"
    parent_launch_payload = {
        "schema_version": "task033.watchdog-parent-launch.v1",
        "token_sha256": hashlib.sha256(parent_launch_token.encode("ascii")).hexdigest(),
        "parent_process": {
            **_linux_process_identity(os.getpid()),
            "role": "resource_watchdog_parent",
        },
        "worker_contract": _worker_launch_contract(args),
    }
    if (
        args.task035e_reference_certifier_gate
        or args.task035e_blind_candidate_gate
    ):
        _write_task035e_private_json_atomic(
            parent_launch_descriptor,
            parent_launch_payload,
        )
    else:
        parent_launch_descriptor.write_text(
            json.dumps(
                parent_launch_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n",
            encoding="utf-8",
        )
    args.parent_launch_descriptor = parent_launch_descriptor
    args.parent_launch_descriptor_sha256 = _sha256(parent_launch_descriptor)
    progress_path = run_dir / "progress_3d.jsonl"
    timeline_path = run_dir / "memory_timeline.csv"
    stdout_path = run_dir / "worker_stdout.txt"
    command = _worker_command(args, run_dir)
    environment = os.environ.copy()
    environment.update(
        {
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1",
            _PARENT_LAUNCH_TOKEN_ENV: parent_launch_token,
        }
    )
    if task035e_formal:
        environment.update(
            {
                "TMPDIR": "/tmp",
                "TMP": "/tmp",
                "TEMP": "/tmp",
            }
        )
    rows: list[dict[str, Any]] = []
    task035e_resource_samples: list[dict[str, Any]] = []
    started = time.perf_counter()
    warning_triggered = False
    terminated_for_memory = False
    terminated_for_timeout = False
    terminated_for_authority_unreadable = False
    task035e_resource_stop_reason: str | None = None
    with stdout_path.open("x", encoding="utf-8") as stdout:
        if task035e_formal:
            stdout_path.chmod(0o600)
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdout=stdout,
            stderr=subprocess.STDOUT,
            text=True,
            env=environment,
            start_new_session=os.name == "posix",
            umask=0o077 if task035e_formal else -1,
        )
        previous: dict[str, Any] | None = None
        while True:
            elapsed = time.perf_counter() - started
            row = _sample(process.pid, progress_path, elapsed)
            _add_cpu_core_equivalents(row, previous)
            previous = row
            rows.append(row)
            task035e_decision = None
            if task035e_resource_policy is not None:
                task035e_decision = _task035e_reference_resource_decision(
                    row,
                    mem_available_bytes=_host_available_bytes(),
                    policy=task035e_resource_policy,
                )
                task035e_resource_samples.append(
                    {
                        "timestamp_utc": row.get("timestamp_utc"),
                        "elapsed_seconds": row.get("elapsed_seconds"),
                        "stage": row.get("stage"),
                        **task035e_decision,
                    }
                )
            process_tree_mb = row.get("mpi_process_tree_rss_mb")
            process_tree_swap_mb = row.get("mpi_process_tree_swap_mb")
            cgroup_mb = (
                row.get("container_cgroup_current_mb")
                if row.get("job_cgroup_dedicated") is True
                else 0.0
            )
            cgroup_swap_mb = (
                row.get("container_swap_current_mb")
                if row.get("job_cgroup_dedicated") is True
                else 0.0
            )
            authority_readable = all(
                isinstance(value, (int, float))
                for value in (
                    process_tree_mb,
                    process_tree_swap_mb,
                    cgroup_mb,
                    cgroup_swap_mb,
                )
            )
            authority_gib = (
                None
                if not authority_readable
                else max(float(process_tree_mb), float(cgroup_mb)) / 1024.0
            )
            if authority_gib is not None:
                warning_triggered |= authority_gib >= args.warning_gib
            if (
                task035e_decision is not None
                and task035e_decision["stop"] is True
                and task035e_resource_stop_reason is None
            ):
                task035e_resource_stop_reason = str(
                    task035e_decision["reason"]
                )
                terminated_for_memory = True
                if process.poll() is None:
                    _terminate(process)
            elif process.poll() is None and not authority_readable:
                terminated_for_authority_unreadable = True
                _terminate(process)
            elif (
                process.poll() is None
                and authority_gib is not None
                and authority_gib >= args.terminate_gib
            ):
                terminated_for_memory = True
                _terminate(process)
            elif process.poll() is None and elapsed >= args.timeout_seconds:
                terminated_for_timeout = True
                _terminate(process)
            if process.poll() is not None:
                break
            time.sleep(args.poll_interval)
        return_code = int(process.returncode or 0)

    with timeline_path.open("x", encoding="utf-8", newline="") as stream:
        if task035e_formal:
            timeline_path.chmod(0o600)
        writer = csv.DictWriter(stream, fieldnames=TIMELINE_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    task035e_resource_timeline_path = (
        run_dir
        / (
            "task035e_blind_candidate_resource_timeline.jsonl"
            if args.task035e_blind_candidate_gate
            else "task035e_reference_resource_timeline.jsonl"
        )
    )
    if task035e_resource_policy is not None:
        task035e_resource_timeline_path.write_text(
            "".join(
                json.dumps(
                    sample,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n"
                for sample in task035e_resource_samples
            ),
            encoding="utf-8",
        )
        if task035e_formal:
            task035e_resource_timeline_path.chmod(0o600)
    solver_path = run_dir / "run_summary.json"
    solver_summary = (
        json.loads(solver_path.read_text(encoding="utf-8"))
        if solver_path.is_file()
        else {}
    )
    dtn_orders_path = run_dir / "dtn_port_diffraction_orders_3d.json"
    volume_absorption_path = run_dir / "volume_absorption.json"
    reference_metadata_path = run_dir / "full3d_reference_samples.json"
    field_shard_paths = [
        run_dir / f"fields_3d_for_paraview_rank{rank:04d}.vtu"
        for rank in range(args.mpi_size)
    ]
    field_shard_authority = [
        {
            "rank": rank,
            "path": _path_from_root(path),
            "sha256": _sha256(path),
        }
        for rank, path in enumerate(field_shard_paths)
    ]
    events = _read_progress_events(progress_path)
    sampler = _sampler_summary(rows)
    sampler["poll_interval_seconds"] = args.poll_interval
    task035e_live_resource_gate = (
        (
            _task035e_blind_candidate_resource_summary(
                policy=task035e_resource_policy,
                samples=task035e_resource_samples,
                stop_reason=task035e_resource_stop_reason,
            )
            if args.task035e_blind_candidate_gate
            else _task035e_reference_resource_summary(
                policy=task035e_resource_policy,
                samples=task035e_resource_samples,
                stop_reason=task035e_resource_stop_reason,
            )
        )
        if task035e_resource_policy is not None
        else None
    )
    no_swap = bool(
        sampler["max_process_tree_swap_mb"] == 0.0
        and (
            not sampler["dedicated_job_cgroup_observed"]
            or sampler["max_container_swap_current_mb"] == 0.0
        )
    )
    qualification = _qualify(
        args=args,
        solver_summary=solver_summary,
        events=events,
        return_code=return_code,
        terminated_for_memory=terminated_for_memory,
        terminated_for_timeout=terminated_for_timeout,
        terminated_for_authority_unreadable=terminated_for_authority_unreadable,
        no_swap=no_swap,
        observed_worker_rank_count=sampler["max_observed_worker_rank_count"],
        resource_summary=sampler,
    )
    task035e_config_authority = _task035e_reference_config_authority(args)
    task035e_lifecycle_authority = None
    if args.task035e_reference_certifier_gate:
        solver_config = solver_summary.get("config")
        solver_config = (
            solver_config if isinstance(solver_config, Mapping) else {}
        )
        petsc_options = solver_summary.get("linear_solve_petsc_options")
        petsc_options = (
            petsc_options if isinstance(petsc_options, Mapping) else {}
        )
        task035e_lifecycle_payload = {
            "schema_version": "task035e.reference-lifecycle-authority.v1",
            "comparison_anchor": "Task035c p6/h10 Full3D static MPI8",
            "assembly_backend": TASK035E_REFERENCE_BACKEND,
            "petsc_direct_solver_profile": "default",
            "selected_parallel_lu_solver_type": "mumps",
            "petsc_extra_options": {},
            "mumps_icntl_overrides": {},
            "direct_release_base_after_augmentation": False,
            "direct_release_solver_before_postprocess": False,
            "full3d_reference_plane_z_nm": list(REFERENCE_PLANES_NM),
            "full3d_reference_sample_count_x": 40,
            "full3d_reference_sample_count_y": 20,
        }
        lifecycle_checks = {
            "static_backend_actual": (
                solver_summary.get("stage4_full3d_assembly_backend_actual")
                == TASK035E_REFERENCE_BACKEND
            ),
            "default_direct_profile": (
                solver_summary.get("petsc_direct_solver_profile")
                == "default"
            ),
            "direct_mumps_selected": (
                solver_summary.get("selected_parallel_lu_solver_type")
                == "mumps"
                and petsc_options.get("pc_factor_mat_solver_type")
                == "mumps"
                and petsc_options.get("ksp_type") == "preonly"
                and petsc_options.get("pc_type") == "lu"
            ),
            "no_mumps_icntl_drift": not any(
                str(name).startswith("mat_mumps_icntl_")
                for name in petsc_options
            ),
            "task035c_lifecycle_match": (
                solver_config.get(
                    "direct_release_base_after_augmentation"
                )
                is False
                and solver_summary.get(
                    "direct_release_solver_before_postprocess"
                )
                is False
                and solver_config.get("petsc_extra_options") == {}
            ),
            "live_resource_gate": bool(
                isinstance(task035e_live_resource_gate, Mapping)
                and task035e_live_resource_gate.get("pass") is True
            ),
            "assembly_resource_authority": (
                task035e_resource_authority_gate is None
                if args.run_kind == "assembly-only"
                else bool(
                    task035e_resource_authority_gate
                    and task035e_resource_authority_gate.get("pass") is True
                )
            ),
            "h5_factorization_authority": (
                bool(
                    task035e_h5_factorization_authority_gate
                    and task035e_h5_factorization_authority_gate.get("pass")
                    is True
                )
                if (
                    args.run_kind == "full-solve"
                    and math.isclose(float(args.h_nm), 5.0)
                )
                else task035e_h5_factorization_authority_gate is None
            ),
        }
        task035e_lifecycle_authority = {
            **task035e_lifecycle_payload,
            "sha256": _canonical_json_sha256(task035e_lifecycle_payload),
            "checks": lifecycle_checks,
            "pass": all(lifecycle_checks.values()),
        }
        qualification["checks"].update(
            {
                f"task035e_{name}": passed
                for name, passed in lifecycle_checks.items()
            }
        )
        qualification["failures"].extend(
            f"task035e_{name}"
            for name, passed in lifecycle_checks.items()
            if not passed
        )
        qualification["failures"] = list(
            dict.fromkeys(qualification["failures"])
        )
        qualification["pass"] = not qualification["failures"]
    task035e_blind_candidate_solver_gate = None
    task035e_blind_candidate_artifact_gate = None
    if args.task035e_blind_candidate_gate:
        serial_probe = (
            args.task035e_internal_probe_kind == "serial_mpi1"
        )
        task035e_blind_candidate_solver_gate = (
            _task035e_blind_candidate_solver_gate(
                args,
                solver_summary,
                plan_gate=task035e_blind_candidate_plan_gate,
                live_resource_gate=task035e_live_resource_gate,
            )
        )
        try:
            reference_metadata = json.loads(
                reference_metadata_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            reference_metadata = {}
        if not isinstance(reference_metadata, Mapping):
            reference_metadata = {}
        archive_name = reference_metadata.get("archive")
        archive_path = (
            reference_metadata_path.parent / str(archive_name)
            if (
                isinstance(archive_name, str)
                and Path(archive_name).name == archive_name
            )
            else None
        )
        live_role = str(args.task035e_blind_output_role)
        live_evidence_path = (
            args.run_dir / "task035e_current_snapshot" / "manifest.json"
            if live_role == "current"
            else args.run_dir
            / f"task035e_{live_role.replace('-', '_')}_evaluation.json"
        )
        try:
            live_evidence = (
                {}
                if serial_probe
                else _task035e_strict_json_loads(
                    live_evidence_path.read_text(encoding="utf-8")
                )
            )
        except (
            OSError,
            UnicodeError,
            json.JSONDecodeError,
            ValueError,
        ):
            live_evidence = {}
        if not isinstance(live_evidence, Mapping):
            live_evidence = {}
        live_evidence_hash = (
            _sha256(live_evidence_path)
            if not serial_probe and live_evidence_path.is_file()
            else None
        )
        live_evidence_gate = (
            {
                "schema_version": (
                    "task035e.blind-live-role-evidence-gate.v1"
                ),
                "pass": True,
                "checks": {
                    "serial_probe_live_snapshot_not_claimed": True
                },
                "failures": [],
                "details": {"role": "serial_mpi1_diagnostic"},
            }
            if serial_probe
            else _task035e_blind_live_role_evidence_gate(
                args,
                evidence_path=live_evidence_path,
                payload=live_evidence,
            )
        )
        live_evidence_pass = bool(
            live_evidence_gate["pass"] is True
            and (serial_probe or live_evidence_hash is not None)
        )
        artifact_checks = {
            "solver_summary_hash_bound": _sha256(solver_path) is not None,
            "timeline_hash_bound": _sha256(timeline_path) is not None,
            "progress_hash_bound": _sha256(progress_path) is not None,
            "stdout_hash_bound": _sha256(stdout_path) is not None,
            "dtn_orders_hash_bound": _sha256(dtn_orders_path) is not None,
            "volume_absorption_hash_bound": (
                _sha256(volume_absorption_path) is not None
            ),
            "reference_metadata_hash_bound": (
                _sha256(reference_metadata_path) is not None
            ),
            "reference_sample_archive_hash_bound": (
                archive_path is not None
                and _sha256(archive_path)
                == reference_metadata.get("archive_sha256")
            ),
        }
        if serial_probe:
            artifact_checks.update(
                {
                    "one_field_shard_hash_bound": (
                        len(field_shard_authority) == 1
                        and all(
                            row["sha256"] is not None
                            for row in field_shard_authority
                        )
                    ),
                    "serial_probe_does_not_claim_live_snapshot": (
                        not live_evidence_path.exists()
                        and live_evidence_hash is None
                    ),
                    "serial_probe_scope": args.mpi_size == 1,
                }
            )
        else:
            artifact_checks.update(
                {
                    "eight_field_shards_hash_bound": (
                        len(field_shard_authority) == 8
                        and all(
                            row["sha256"] is not None
                            for row in field_shard_authority
                        )
                    ),
                    "blind_live_role_evidence_hash_bound": (
                        live_evidence_pass
                    ),
                    "mpi8_candidate_or_probe_scope": (
                        args.mpi_size == 8
                    ),
                }
            )
        task035e_blind_candidate_artifact_gate = {
            "schema_version": (
                "task035e.blind-candidate-artifact-gate.v1"
            ),
            "pass": all(artifact_checks.values()),
            "checks": artifact_checks,
            "failures": [
                name
                for name, passed in artifact_checks.items()
                if not passed
            ],
            "reference_sample_archive": (
                None
                if archive_path is None
                else {
                    "path": _path_from_root(archive_path),
                    "sha256": _sha256(archive_path),
                }
            ),
            "blind_live_role_evidence": {
                "role": live_role,
                "path": _path_from_root(live_evidence_path),
                "sha256": live_evidence_hash,
                "schema_version": live_evidence.get(
                    "schema_version"
                ),
                "status": live_evidence.get("status"),
                "independent_gate": live_evidence_gate,
            },
        }
        qualification["checks"].update(
            {
                f"task035e_blind_solver_{name}": passed
                for name, passed in (
                    task035e_blind_candidate_solver_gate["checks"]
                ).items()
            }
        )
        qualification["checks"].update(
            {
                f"task035e_blind_artifact_{name}": passed
                for name, passed in artifact_checks.items()
            }
        )
        qualification["failures"].extend(
            name
            for name, passed in qualification["checks"].items()
            if name.startswith("task035e_blind_") and not passed
        )
        qualification["failures"] = list(
            dict.fromkeys(qualification["failures"])
        )
        qualification["pass"] = not qualification["failures"]
    task035d_nested_p_evidence = None
    task035d_selective_face_evidence = None
    task035d_selective_face_controlled_negative = False
    if args.task035d_case097_gate:
        raw_artifact_checks = {
            "task035d_solver_summary_hash_bound": (_sha256(solver_path) is not None),
            "task035d_timeline_hash_bound": (_sha256(timeline_path) is not None),
            "task035d_progress_hash_bound": (_sha256(progress_path) is not None),
            "task035d_stdout_hash_bound": (_sha256(stdout_path) is not None),
            "task035d_dtn_orders_hash_bound": (_sha256(dtn_orders_path) is not None),
            "task035d_eight_field_shards_hash_bound": (
                len(field_shard_authority) == 8
                and all(
                    authority["sha256"] is not None
                    for authority in field_shard_authority
                )
            ),
        }
        if args.task035d_nested_p_dwr_phase == "coarse-snapshot":
            nested_path = run_dir / "nested_p_snapshot" / "manifest.json"
            try:
                nested_payload = json.loads(nested_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                nested_payload = {}
            if not isinstance(nested_payload, dict):
                nested_payload = {}
            nested_shards = nested_payload.get("shards", ())
            nested_primal_gate = nested_payload.get("primal_residual_gate", {})
            nested_candidate = nested_payload.get("candidate", {})
            nested_trace = nested_payload.get("same_trace_identity", {})
            nested_checks = {
                "task035d_nested_p_coarse_manifest": (
                    _sha256(nested_path) is not None
                    and nested_payload.get("schema_version")
                    == ("task035d.variable-p-nested-coarse-snapshot.v1")
                    and nested_payload.get("pass") is True
                    and nested_payload.get("role") == "coarse_B"
                ),
                "task035d_nested_p_coarse_source": (
                    nested_candidate.get("source_sha") == args.verified_clean_sha
                ),
                "task035d_nested_p_coarse_candidate": (
                    nested_candidate.get("candidate_id")
                    == TASK035D_HP_FACTORIAL_BRIDGE_PLAN_NAME
                    and nested_candidate.get("plan_file_sha256")
                    == args.stage4_local_h_refinement_plan_sha256
                    and nested_candidate.get("cell_interior_degree_counts")
                    == {"5": 32, "6": 102}
                    and nested_candidate.get("actual_full3d_equivalent_active_fe_dofs")
                    == 76_205
                ),
                "task035d_nested_p_coarse_trace_identity": (
                    nested_trace.get("mpi_size") == 8
                    and nested_trace.get("independent_trace_rows") == 18_390
                    and nested_trace.get("auxiliary_rows") == 80
                    and nested_trace.get("matrix_rows") == 18_470
                ),
                "task035d_nested_p_coarse_channel_authority": (
                    nested_payload.get("significant_channel_authority", {}).get(
                        "sha256"
                    )
                    == args.task035d_significant_channel_authority_sha256
                ),
                "task035d_nested_p_coarse_port_content": (
                    nested_payload.get("port_operator_audit", {}).get("pass") is True
                    and isinstance(
                        nested_payload.get("port_operator_audit", {}).get(
                            "external_operator_content_sha256"
                        ),
                        str,
                    )
                    and isinstance(
                        nested_payload.get("port_operator_audit", {}).get(
                            "external_rhs_content_sha256"
                        ),
                        str,
                    )
                ),
                "task035d_nested_p_coarse_primal_residual": (
                    nested_primal_gate.get("pass") is True
                    and len(nested_primal_gate.get("checks", {})) == 4
                    and all(nested_primal_gate.get("checks", {}).values())
                    and _finite_number_le(
                        nested_payload.get("vector_identity", {}).get(
                            "relative_residual"
                        ),
                        1.0e-9,
                    )
                    and _finite_number_le(
                        nested_payload.get("full_active_residual", {}).get(
                            "linear_system_relative_residual"
                        ),
                        1.0e-9,
                    )
                ),
                "task035d_nested_p_eight_hash_bound_shards": (
                    len(nested_shards) == 8
                    and all(
                        _sha256(nested_path.parent / str(shard["path"]))
                        == shard.get("sha256")
                        for shard in nested_shards
                    )
                ),
            }
            task035d_nested_p_evidence = {
                "phase": "coarse-snapshot",
                "path": _path_from_root(nested_path),
                "sha256": _sha256(nested_path),
                "payload": nested_payload,
            }
            raw_artifact_checks.update(nested_checks)
        elif args.task035d_nested_p_dwr_phase == "enriched-evaluate":
            nested_path = run_dir / "nested_p_dwr_report.json"
            try:
                nested_payload = json.loads(nested_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                nested_payload = {}
            if not isinstance(nested_payload, dict):
                nested_payload = {}
            goal_dwr = nested_payload.get("goal_dwr", {})
            basis = nested_payload.get(
                "unit_channel_adjoint_basis",
                {},
            )
            primal_endpoints = nested_payload.get("primal_endpoints", {})
            coarse_endpoint_gate = primal_endpoints.get("coarse_residual_gate", {})
            enriched_endpoint_gate = primal_endpoints.get("enriched_residual_gate", {})
            basis_channels = basis.get("channels", {})
            basis_goals = basis.get("goals", {})
            try:
                channel_authority_payload = json.loads(
                    args.task035d_significant_channel_authority.read_text(
                        encoding="utf-8"
                    )
                )
            except (OSError, json.JSONDecodeError):
                channel_authority_payload = {}
            independent_checker_gate = task035d_nested_p_dwr_report_gate(
                nested_payload,
                channel_authority_payload,
            )
            nested_checks = {
                "task035d_nested_p_dwr_report": (
                    _sha256(nested_path) is not None
                    and nested_payload.get("schema_version")
                    == "task035d.variable-p-nested-live-dwr.v1"
                    and nested_payload.get("pass") is True
                ),
                "task035d_nested_p_endpoint_identity": (
                    nested_payload.get("enriched_candidate", {}).get("candidate_id")
                    == TASK035D_LOCAL_H_PLAN_NAME
                    and nested_payload.get("enriched_candidate", {}).get("source_sha")
                    == args.verified_clean_sha
                    and nested_payload.get("enriched_candidate", {}).get(
                        "plan_file_sha256"
                    )
                    == args.stage4_local_h_refinement_plan_sha256
                    and nested_payload.get("coarse_snapshot", {}).get("manifest_sha256")
                    == args.task035d_coarse_snapshot_manifest_sha256
                    and nested_payload.get("significant_channel_authority", {}).get(
                        "sha256"
                    )
                    == args.task035d_significant_channel_authority_sha256
                ),
                "task035d_nested_p_primal_endpoint_residuals": (
                    coarse_endpoint_gate.get("pass") is True
                    and enriched_endpoint_gate.get("pass") is True
                    and all(coarse_endpoint_gate.get("checks", {}).values())
                    and all(enriched_endpoint_gate.get("checks", {}).values())
                    and _finite_number_le(
                        primal_endpoints.get("coarse_relative_residual"),
                        1.0e-9,
                    )
                    and _finite_number_le(
                        primal_endpoints.get("enriched_relative_residual"),
                        1.0e-9,
                    )
                ),
                "task035d_nested_p_residual_partition": (
                    nested_payload.get("residual_partition", {}).get("pass") is True
                ),
                "task035d_nested_p_twelve_unit_adjoints": (
                    basis.get("pass") is True
                    and basis.get("unit_adjoint_solve_count") == 12
                    and basis.get("physical_channel_count") == 12
                    and len(basis_channels) == 12
                    and all(
                        channel.get("pass") is True
                        and _finite_number_le(
                            channel.get("adjoint_residual", {}).get(
                                "relative_residual"
                            ),
                            1.0e-9,
                        )
                        for channel in basis_channels.values()
                    )
                ),
                "task035d_nested_p_36_goal_closure": (
                    goal_dwr.get("pass") is True
                    and goal_dwr.get("passed_real_goal_count") == 36
                    and goal_dwr.get("power_goal_pass_count") == 12
                    and goal_dwr.get("complex_amplitude_component_goal_pass_count")
                    == 24
                    and len(goal_dwr.get("goals", {})) == 36
                    and all(
                        goal.get("pass") is True
                        for goal in goal_dwr.get("goals", {}).values()
                    )
                    and len(basis_goals) == 36
                    and all(
                        goal.get("pass") is True
                        and _finite_number_le(
                            goal.get("scaled_adjoint_residual", {}).get(
                                "relative_residual"
                            ),
                            1.0e-9,
                        )
                        for goal in basis_goals.values()
                    )
                    and nested_payload.get("significant_channel_authority", {}).get(
                        "selected_goal_set_complete_by_frozen_authority"
                    )
                    is True
                ),
                "task035d_nested_p_same_trace_only": (
                    nested_payload.get("same_trace_only") is True
                    and nested_payload.get("cross_trace_primal_prolongation_used")
                    is False
                ),
                "task035d_nested_p_independent_checker": (
                    independent_checker_gate["pass"] is True
                ),
            }
            task035d_nested_p_evidence = {
                "phase": "enriched-evaluate",
                "path": _path_from_root(nested_path),
                "sha256": _sha256(nested_path),
                "payload": nested_payload,
                "independent_checker": independent_checker_gate,
            }
            raw_artifact_checks.update(nested_checks)
        if args.task035d_selective_face_dwr_phase == "coarse-snapshot":
            selective_path = run_dir / "selective_face_snapshot" / "manifest.json"
            try:
                selective_payload = json.loads(
                    selective_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                selective_payload = {}
            if not isinstance(selective_payload, dict):
                selective_payload = {}
            arrays_path = selective_path.parent / str(
                selective_payload.get("arrays", {}).get("path", "")
            )
            arrays_sha = (
                _sha256(arrays_path)
                if arrays_path.parent == selective_path.parent and arrays_path.is_file()
                else None
            )
            selective_gate = task035d_selective_face_coarse_snapshot_gate(
                selective_payload,
                expected_source_sha=str(args.verified_clean_sha),
                expected_plan_sha256=(TASK035D_LOCAL_H_PLAN_FILE_SHA256),
                expected_significant_channel_authority_sha256=(
                    str(args.task035d_significant_channel_authority_sha256)
                ),
                observed_arrays_sha256=arrays_sha,
            )
            selective_checks = {
                "task035d_selective_face_coarse_manifest": (
                    _sha256(selective_path) is not None
                ),
                "task035d_selective_face_coarse_arrays": (arrays_sha is not None),
                "task035d_selective_face_coarse_independent_gate": (
                    selective_gate["pass"] is True
                ),
            }
            task035d_selective_face_evidence = {
                "phase": "coarse-snapshot",
                "path": _path_from_root(selective_path),
                "sha256": _sha256(selective_path),
                "arrays_path": _path_from_root(arrays_path),
                "arrays_sha256": arrays_sha,
                "payload": selective_payload,
                "independent_checker": selective_gate,
            }
            raw_artifact_checks.update(selective_checks)
        elif args.task035d_selective_face_dwr_phase == "enriched-evaluate":
            selective_path = run_dir / "selective_face_dwr_report.json"
            try:
                selective_payload = json.loads(
                    selective_path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                selective_payload = {}
            if not isinstance(selective_payload, dict):
                selective_payload = {}
            try:
                selective_authority_payload = json.loads(
                    args.task035d_significant_channel_authority.read_text(
                        encoding="utf-8"
                    )
                )
            except (AttributeError, OSError, json.JSONDecodeError):
                selective_authority_payload = {}
            if not isinstance(selective_authority_payload, dict):
                selective_authority_payload = {}
            try:
                selective_coarse_endpoint = load_selective_face_coarse_endpoint(
                    args.task035d_selective_face_coarse_manifest,
                    expected_manifest_sha256=str(
                        args.task035d_selective_face_coarse_manifest_sha256
                    ),
                )
            except (OSError, TypeError, ValueError):
                selective_coarse_endpoint = {}
            selective_gate = task035d_selective_face_dwr_report_gate(
                selective_payload,
                selective_authority_payload,
                selective_coarse_endpoint,
                expected_source_sha=str(args.verified_clean_sha),
                expected_coarse_plan_sha256=(TASK035D_LOCAL_H_PLAN_FILE_SHA256),
                expected_enriched_plan_sha256=str(
                    args.stage4_local_h_refinement_plan_sha256
                ),
                expected_coarse_manifest_sha256=str(
                    args.task035d_selective_face_coarse_manifest_sha256
                ),
                expected_significant_channel_authority_sha256=str(
                    args.task035d_significant_channel_authority_sha256
                ),
            )
            task035d_selective_face_controlled_negative = (
                _task035d_selective_face_controlled_negative(
                    selective_payload,
                    report_sha256=_sha256(selective_path),
                )
            )
            selective_checks = {
                "task035d_selective_face_dwr_report": (
                    _sha256(selective_path) is not None
                ),
                "task035d_selective_face_dwr_independent_checker": (
                    selective_gate["pass"] is True
                ),
            }
            task035d_selective_face_evidence = {
                "phase": "enriched-evaluate",
                "path": _path_from_root(selective_path),
                "sha256": _sha256(selective_path),
                "payload": selective_payload,
                "independent_checker": selective_gate,
            }
            raw_artifact_checks.update(selective_checks)
        qualification["checks"].update(raw_artifact_checks)
        qualification["failures"].extend(
            name for name, passed in raw_artifact_checks.items() if not passed
        )
        qualification["pass"] = not qualification["failures"]
    source_head_after = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    source_status_after = subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=ROOT,
        text=True,
    ).strip()
    source_stable = bool(
        source_head_after == source_before["commit_sha"] and not source_status_after
    )
    qualification["checks"]["source_stable_and_clean_after"] = source_stable
    if not source_stable:
        qualification["failures"].append("source_stable_and_clean_after")
        qualification["pass"] = False
    task035e_internal_probe_status = (
        _task035e_internal_probe_success_status(
            args,
            qualified=bool(qualification["pass"]),
        )
    )
    status = (
        "controlled_resource_stop"
        if (
            (
                args.task035e_reference_certifier_gate
                or args.task035e_blind_candidate_gate
            )
            and isinstance(task035e_live_resource_gate, Mapping)
            and task035e_live_resource_gate.get("controlled_resource_stop")
            is True
        )
        else task035e_internal_probe_status
        if task035e_internal_probe_status is not None
        else "task035e_blind_candidate_full_solve_pass"
        if (
            qualification["pass"]
            and args.task035e_blind_candidate_gate
            and args.run_kind == "full-solve"
        )
        else "task035e_reference_assembly_resource_pass"
        if (
            qualification["pass"]
            and args.task035e_reference_certifier_gate
            and args.run_kind == "assembly-only"
        )
        else "task035e_reference_full_solve_pass"
        if (
            qualification["pass"]
            and args.task035e_reference_certifier_gate
            and args.run_kind == "full-solve"
        )
        else "assembly_calibration_pass"
        if qualification["pass"] and args.run_kind == "assembly-only"
        else "factorization_calibration_pass"
        if qualification["pass"] and args.run_kind == "factorization-only"
        else "task035d_nested_p_coarse_snapshot_pass"
        if (
            qualification["pass"]
            and args.task035d_nested_p_dwr_phase == "coarse-snapshot"
        )
        else "task035d_nested_p_live_dwr_pass"
        if (
            qualification["pass"]
            and args.task035d_nested_p_dwr_phase == "enriched-evaluate"
        )
        else "task035d_selective_face_coarse_snapshot_pass"
        if (
            qualification["pass"]
            and args.task035d_selective_face_dwr_phase == "coarse-snapshot"
        )
        else "task035d_selective_face_live_dwr_pass"
        if (
            qualification["pass"]
            and args.task035d_selective_face_dwr_phase == "enriched-evaluate"
        )
        else "task035d_selective_face_live_dwr_controlled_negative"
        if (
            args.task035d_selective_face_dwr_phase == "enriched-evaluate"
            and task035d_selective_face_controlled_negative
        )
        else "task035d_candidate_numerical_pass"
        if qualification["pass"] and args.task035d_case097_gate
        else "full3d_reference_pass"
        if qualification["pass"]
        else "formal_not_pass"
    )
    matrix = solver_summary.get("matrix_stats") or {}
    task035e_blind_candidate_authority_record = (
        _task035e_blind_candidate_authority(
            args,
            solver_summary,
            source_sha=str(source_before["commit_sha"]),
            qualified=(
                status == "task035e_blind_candidate_full_solve_pass"
            ),
        )
    )
    record = {
        "schema_version": "task033.full3d-watchdog.v1",
        "benchmark_id": "task033_target_full3d_watchdog",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "degree": args.degree,
        "h_nm": args.h_nm,
        "polarization_kind": args.polarization_kind,
        "run_kind": args.run_kind,
        "mpi_size": args.mpi_size,
        "profile": args.profile,
        "stage4_full3d_assembly_backend_requested": (
            args.stage4_full3d_assembly_backend
        ),
        "stage4_full3d_assembly_backend_actual": solver_summary.get(
            "stage4_full3d_assembly_backend_actual"
        ),
        "stage4_raw_tensor_cache_request": {
            "enabled": bool(args.stage4_raw_tensor_cache),
            "directory": (
                None
                if args.stage4_raw_tensor_cache_directory is None
                else str(args.stage4_raw_tensor_cache_directory)
            ),
            "namespace": (
                f"git-{args.verified_clean_sha}"
                if args.stage4_raw_tensor_cache
                else None
            ),
            "ordinary_default_changed": False,
            "numerical_identity_changed": False,
        },
        "command": command,
        "parent_launch_descriptor": {
            "path": _path_from_root(parent_launch_descriptor),
            "sha256": args.parent_launch_descriptor_sha256,
            "payload": parent_launch_payload,
            "secret_token_persisted": False,
        },
        "source": {
            **source_before,
            "branch": subprocess.check_output(
                ["git", "branch", "--show-current"], cwd=ROOT, text=True
            ).strip(),
            "head_after_sha": source_head_after,
            "status_after": source_status_after,
            "stable_and_clean_after": source_stable,
        },
        "p4_prerequisite_gate": p4_gate,
        "task035c_p6_h10_preflight_gate": task035c_p6_gate,
        "task035e_reference_certifier": (
            {
                "schema_version": (
                    TASK035E_REFERENCE_RESOURCE_AUTHORITY_SCHEMA
                ),
                "selected": True,
                "credit": (
                    "resource_only_not_physics"
                    if args.run_kind == "assembly-only"
                    else "reference_physics_pending_hidden_certifier"
                ),
                "config_authority": task035e_config_authority,
                "lifecycle_authority": task035e_lifecycle_authority,
                "resource_authority_gate": (
                    task035e_resource_authority_gate
                ),
                "h5_factorization_authority_gate": (
                    task035e_h5_factorization_authority_gate
                ),
                "live_resource_gate": task035e_live_resource_gate,
                "resource_timeline": {
                    "path": _path_from_root(
                        task035e_resource_timeline_path
                    ),
                    "sha256": _sha256(
                        task035e_resource_timeline_path
                    ),
                },
            }
            if args.task035e_reference_certifier_gate
            else None
        ),
        "task035e_blind_candidate": (
            task035e_blind_candidate_authority_record
        ),
        "task035e_internal_probe": (
            _task035e_internal_probe_authority(args)
        ),
        "task035e_blind_candidate_launch_gate": (
            {
                "schema_version": (
                    "task035e.blind-candidate-launch-gate.v1"
                ),
                "selected": True,
                "path_id": (
                    "path_a"
                    if math.isclose(float(args.h_nm), 20.0)
                    else "path_b"
                ),
                "plan": task035e_blind_candidate_plan_gate,
                "current_snapshot": task035e_current_snapshot_gate,
                "solver": task035e_blind_candidate_solver_gate,
                "artifacts": task035e_blind_candidate_artifact_gate,
                "resource_policy": task035e_resource_policy,
                "live_resource_gate": task035e_live_resource_gate,
            }
            if args.task035e_blind_candidate_gate
            else None
        ),
        "task035d_case097_launch_gate": task035d_case097_gate,
        "task035d_nested_p_launch_gate": task035d_nested_p_gate,
        "task035d_selective_face_launch_gate": (task035d_selective_face_gate),
        "task035d_candidate_id": (
            args.task035d_candidate_id if args.task035d_case097_gate else None
        ),
        "task035d_accuracy_credit": (
            "pending_independent_12_channel_and_field_checker"
            if args.task035d_case097_gate
            else None
        ),
        "task035d_nested_p_dwr_phase": (args.task035d_nested_p_dwr_phase),
        "task035d_nested_p_evidence": task035d_nested_p_evidence,
        "task035d_selective_face_dwr_phase": (args.task035d_selective_face_dwr_phase),
        "task035d_selective_face_evidence": (task035d_selective_face_evidence),
        "resource_policy": {
            "swap_allowed": args.allow_swap,
            "warning_gib": args.warning_gib,
            "termination_gib": args.terminate_gib,
            "termination_authority": (
                "max(process-tree RSS, dedicated job cgroup memory.current when present)"
            ),
            "timeout_seconds": args.timeout_seconds,
            "formal_no_swap_authority": "process-tree VmSwap plus dedicated job cgroup swap",
            "wsl_global_pswp_role": "diagnostic_only",
            "mumps_ooc_role": "explicit_scratch_profile_not_linux_swap",
            "effective_limit": effective,
            "task035e_dynamic_policy": task035e_resource_policy,
        },
        "environment_before": environment_before,
        "environment_after": _resource_snapshot(),
        "task035e_formal_runtime": task035e_formal_runtime,
        "warning_triggered": warning_triggered,
        "terminated_for_memory": terminated_for_memory,
        "terminated_for_timeout": terminated_for_timeout,
        "terminated_for_authority_unreadable": (terminated_for_authority_unreadable),
        "controlled_resource_stop": (
            (
                args.task035e_reference_certifier_gate
                or args.task035e_blind_candidate_gate
            )
            and task035e_resource_stop_reason is not None
        ),
        "controlled_resource_stop_reason": task035e_resource_stop_reason,
        "no_swap": no_swap,
        "resource_authority": sampler,
        "calibration": {
            "exact_rows": matrix.get("matrix_rows"),
            "exact_assembled_nnz": matrix.get("matrix_nnz_used"),
            "matrix_petsc_memory_bytes": matrix.get("matrix_memory_bytes"),
            "matrix_payload_estimate_bytes": matrix.get("matrix_memory_estimate_bytes"),
            "num_nedelec_dofs": solver_summary.get("num_nedelec_dofs"),
            "num_auxiliary_dofs": solver_summary.get("stage4_dtn_num_auxiliary_dofs"),
            "floquet_constraint_rows": solver_summary.get("floquet_num_constraints"),
            "floquet_constraint_raw_map_nnz": solver_summary.get("floquet_raw_map_nnz"),
            "floquet_constraint_timings_seconds": solver_summary.get(
                "floquet_constraint_timings_seconds"
            ),
            "floquet_created_dense_boundary_square": solver_summary.get(
                "floquet_created_dense_boundary_square"
            ),
            "dtn_auxiliary_block_stats": solver_summary.get(
                "stage4_dtn_auxiliary_block_stats"
            ),
            "explicit_chac_constructed": solver_summary.get(
                "explicit_chac_constructed"
            ),
            "factorization_or_solve_stage_seen": _factorization_stage_seen(events),
        },
        "matrix_inventory": {
            "base": solver_summary.get("stage4_dtn_base_matrix_stats"),
            "augmented": solver_summary.get(
                "stage4_dtn_augmented_matrix_stats_after_finalize"
            ),
            "final": matrix,
            "constraint_transform": solver_summary.get("constraint_matrix_transform"),
        },
        "timings_seconds": solver_summary.get("timings_seconds"),
        "historical_peak_upper_bound_mb": _historical_peak_upper_bound(
            events, solver_summary
        ),
        "qualification": qualification,
        "return_code": return_code,
        "solver_summary_sha256": _sha256(solver_path),
        "timeline_sha256": _sha256(timeline_path),
        "progress_sha256": _sha256(progress_path),
        "stdout_sha256": _sha256(stdout_path),
        "dtn_orders_sha256": _sha256(dtn_orders_path),
        "volume_absorption_sha256": _sha256(volume_absorption_path),
        "reference_metadata_sha256": _sha256(reference_metadata_path),
        "field_shard_authority": field_shard_authority,
        "raw_evidence": {
            "run_directory": _path_from_root(run_dir),
            "solver_summary": _path_from_root(solver_path),
            "timeline": _path_from_root(timeline_path),
            "progress": _path_from_root(progress_path),
            "stdout": _path_from_root(stdout_path),
            "dtn_orders": _path_from_root(dtn_orders_path),
            "volume_absorption": _path_from_root(volume_absorption_path),
            "reference_metadata": _path_from_root(reference_metadata_path),
            "field_shards": field_shard_authority,
        },
        "solver_summary": solver_summary,
    }
    record_path = args.record or (run_dir / "watchdog_summary.json")
    if not record_path.is_absolute():
        record_path = ROOT / record_path
    record_path.parent.mkdir(parents=True, exist_ok=True)
    if (
        args.task035e_reference_certifier_gate
        or args.task035e_blind_candidate_gate
    ):
        _write_task035e_private_json_atomic(record_path, record)
    else:
        record_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(
        json.dumps(
            {
                "status": status,
                "degree": args.degree,
                "h_nm": args.h_nm,
                "polarization_kind": args.polarization_kind,
                "run_kind": args.run_kind,
                "memory_authority_gib": sampler["memory_authority_gib"],
                "combined_memory_swap_authority_gib": sampler[
                    "combined_memory_swap_authority_gib"
                ],
                "no_swap": no_swap,
                "record": _path_from_root(record_path),
                "failures": qualification["failures"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if qualification["pass"] else 2


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.worker:
        if args.run_dir is None:
            raise SystemExit("--worker requires --run-dir.")
        if (
            args.task035e_reference_certifier_gate
            or args.task035e_blind_candidate_gate
        ):
            _validate_task035e_formal_runtime(
                require_private_worker_tmp=True,
            )
        _validate_worker_parent_launch(args)
        _revalidate_task035d_worker_inputs(args)
        _revalidate_task035e_worker_inputs(args)
        return _worker(args)
    return _run_parent(args)


if __name__ == "__main__":
    raise SystemExit(main())
