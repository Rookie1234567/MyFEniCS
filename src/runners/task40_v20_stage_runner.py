"""Task40 V20 case routing and bounded original-size preflight stages."""

from __future__ import annotations

from collections.abc import Mapping
import json
import os
from pathlib import Path
import resource
import sys
from typing import Any

import numpy as np


V20_STAGE_NAMES = (
    "preflight",
    "geometry_inventory",
    "local_port_components",
    "build_and_symbolic",
    "one_q_numeric",
    "full",
)
V20_TARGET_Q0 = 0
V20_TARGET_FULL_FIELD_QUALIFIED = False


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, complex):
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"V20 stage evidence cannot encode {type(value).__name__}")


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    encoded = json.dumps(
        value, sort_keys=True, indent=2, allow_nan=False, default=_json_default
    ).encode("utf-8") + b"\n"
    with temporary.open("wb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _resource_snapshot() -> dict[str, Any]:
    available = None
    total = None
    swap_total = None
    swap_free = None
    try:
        facts = {}
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            key, raw = line.split(":", 1)
            if key in {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}:
                facts[key] = int(raw.split()[0]) * 1024
        total = facts.get("MemTotal")
        available = facts.get("MemAvailable")
        swap_total = facts.get("SwapTotal")
        swap_free = facts.get("SwapFree")
    except (OSError, ValueError):
        pass
    try:
        from benchmarks.task034_wsl_resources import cgroup_snapshot

        cgroup = cgroup_snapshot("self")
        cgroup["sample_scope"] = (
            "current process cgroup; task-specific only when dedicated_job_cgroup is true"
        )
    except (ImportError, OSError, ValueError) as error:
        cgroup = {
            "path": None,
            "readable": False,
            "dedicated_job_cgroup": False,
            "memory_current_bytes": None,
            "memory_peak_bytes": None,
            "memory_limit_bytes": None,
            "swap_current_bytes": None,
            "sample_scope": "UNKNOWN: current process cgroup provider failed",
            "error": {"type": type(error).__name__, "message": str(error)},
        }
    return {
        "host_memory_total_bytes": total,
        "host_memory_available_bytes": available,
        "host_swap_total_bytes": swap_total,
        "host_swap_free_bytes": swap_free,
        "process_max_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024,
        "current_process_cgroup": cgroup,
        "scope": (
            "instant host sample plus current-process cgroup sample and process historical max RSS; "
            "cgroup values are task-specific only for a dedicated job cgroup and are not a "
            "simultaneous process-tree peak"
        ),
    }


def _exact_case(resolved: Mapping[str, Any]) -> tuple[str, str]:
    from src.geometry.task40_nonseparable_plan import TASK40_COMPARISON_GROUP
    from src.solvers.task40_v20_registry import task40_v20_case

    solver = resolved.get("solver", {})
    execution = resolved.get("execution", {})
    profile = solver.get("preconditioner")
    run_id = resolved.get("run_id")
    try:
        case = task40_v20_case(profile=str(profile))
    except ValueError:
        case = None
    if (
        case is None
        or run_id != case.run_id
        or resolved.get("comparison_group") != TASK40_COMPARISON_GROUP
        or resolved.get("method", {}).get("kind") != "full3d_iterative"
        or solver.get("task40_reference_pc_strategy")
        != "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15"
        or solver.get("task40_q_assembly_strategy") != "ROW_TILE_BOUNDED_CSR_V17"
        or solver.get("task40_factor_lifecycle_strategy") != "ONE_Q_REFACTOR_V19"
        or execution.get("task40_execution_stop_stage") not in case.allowed_stop_stages
        or resolved.get("derived", {}).get("physical_intermediate_profile", {}).get(
            "identity"
        )
        != profile
    ):
        raise ValueError("Task40 V20 stage adapter requires an exact reviewed case/profile route")
    return str(profile), str(case.mesh_id)


def _preflight(
    resolved: Mapping[str, Any], *, source_sha: str, profile: str, mesh_id: str
) -> tuple[dict[str, Any], tuple[Any, ...] | None, tuple[Mapping[str, Any], ...] | None]:
    from mpi4py import MPI
    from petsc4py import PETSc

    from src.io.physical_intermediate_profile import profile_facts
    from src.solvers.task40_v20_mode_inventory import load_v20_target_mode_inventory

    provenance = resolved.get("provenance", {})
    if (
        not isinstance(source_sha, str)
        or len(source_sha) != 40
        or any(char not in "0123456789abcdef" for char in source_sha.lower())
        or not isinstance(provenance, Mapping)
        or len(str(provenance.get("input_sha256", ""))) != 64
        or len(str(provenance.get("physical_model_sha256", ""))) != 64
    ):
        raise ValueError("V20 preflight requires complete source/input/physical-model identities")
    if (
        os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1"
        or MPI.COMM_WORLD.size != 1
        or np.dtype(PETSc.ScalarType) != np.dtype(np.complex128)
        or np.dtype(PETSc.IntType) != np.dtype(np.int32)
    ):
        raise RuntimeError("V20 preflight requires qualified WSL MPI1 complex128/int32 ABI")
    inventory = profile_facts(profile)
    if (
        inventory.get("run_id") != resolved.get("run_id")
        or inventory.get("gates", {}).get("task40_mesh_id") != mesh_id
        or inventory.get("periodic_inventory", {}).get("global_cell_axes")
        != resolved.get("discretization", {}).get("mesh_axis_cell_counts")
    ):
        raise ValueError("V20 profile inventory differs from the resolved target geometry/case")
    mode_facts = None
    modes = rows = None
    if mesh_id == "TARGET_ORIGINAL_NY8":
        modes, rows, _mode_sha, mode_facts = load_v20_target_mode_inventory(resolved)
    environment = {
        "qualified_activation": os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION"),
        "python_executable": sys.executable,
        "petsc_scalar_type": str(PETSc.ScalarType),
        "petsc_int_type": str(PETSc.IntType),
        "mpi_library": MPI.Get_library_version().splitlines()[0],
        "mpi_size": MPI.COMM_WORLD.size,
    }
    return (
        {
            "schema": "task40extra.review_v20_stage_preflight.v1",
            "source_sha": source_sha,
            "input_path": provenance.get("source_path"),
            "input_sha256": provenance.get("input_sha256"),
            "physical_model_sha256": provenance.get("physical_model_sha256"),
            "case_profile": profile,
            "run_id": resolved.get("run_id"),
            "mesh_id": mesh_id,
            "solver_stage": resolved.get("solver", {}).get("stage"),
            "stop_stage": resolved.get("execution", {}).get(
                "task40_execution_stop_stage"
            ),
            "abi": environment,
            "resources": _resource_snapshot(),
            "profile_inventory": inventory,
            "target_mode_inventory": mode_facts,
            "passed": True,
        },
        modes,
        rows,
    )


def _controlled_stop(
    output_directory: Path,
    *,
    preflight: Mapping[str, Any],
    requested_stage: str,
    completed_stages: list[str],
    reason: str,
    additional: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    receipt = {
        "schema": "task40extra.review_v20_partial_result.v1",
        "status": "controlled_stop",
        "classification": "CONTROLLED_STOP",
        "run_id": preflight.get("run_id"),
        "profile": preflight.get("case_profile"),
        "source_sha": preflight.get("source_sha"),
        "input_sha256": preflight.get("input_sha256"),
        "physical_model_sha256": preflight.get("physical_model_sha256"),
        "requested_stop_stage": requested_stage,
        "completed_stages": completed_stages,
        "official_result": False,
        "not_run": [
            "target global p6 FE/MPC",
            "all-q CSR and symbolic/numeric factors",
            "target PDE/full field",
            "R/T/A precision qualification",
        ],
        "reason": reason,
        "outer_budget": "not charged by this adapter; the launcher/watchdog owns campaign accounting",
        **dict(additional or {}),
    }
    _write_json(output_directory / "v20_partial_result.json", receipt)
    return {
        "passed": True,
        "errors": [],
        "official_result": False,
        "status": "controlled_stop",
        "summary": receipt,
        "numerical_output_directory": str(output_directory),
    }


def run_task40_v20_stage(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    source_sha: str,
) -> dict[str, Any]:
    """Run only the explicitly selected V20 stage, failing closed at each gate."""

    profile, mesh_id = _exact_case(resolved_payload)
    stop_stage = str(resolved_payload["execution"]["task40_execution_stop_stage"])
    output_directory = Path(run_directory).resolve()
    output_directory.mkdir(parents=True, exist_ok=True)
    preflight, modes, mode_rows = _preflight(
        resolved_payload, source_sha=source_sha, profile=profile, mesh_id=mesh_id
    )
    _write_json(output_directory / "v20_stage_preflight.json", preflight)
    completed = ["preflight"]

    if mesh_id == "TARGET_ORIGINAL_NY8" and stop_stage == "full":
        return _controlled_stop(
            output_directory,
            preflight=preflight,
            requested_stage=stop_stage,
            completed_stages=completed,
            reason="TARGET_SOLVER_NOT_QUALIFIED: original-size mapping, all-q/operator, recovery, and full-field gates remain open",
            additional={
                "full_field_release_allowed": False,
                "qualification_blockers": [
                    "actual target primal/dual mapping",
                    "all-q coverage and native operator witnesses",
                    "target recovery and original A6 residual",
                    "physical output and independent checker",
                ],
            },
        )

    if mesh_id == "TARGET_ORIGINAL_NY8" and stop_stage in {
        "build_and_symbolic",
        "one_q_numeric",
    } and not bool(resolved_payload["execution"].get("task40_target_heavy_authorized")):
        return _controlled_stop(
            output_directory,
            preflight=preflight,
            requested_stage=stop_stage,
            completed_stages=completed,
            reason="TARGET_HEAVY_NOT_AUTHORIZED_IN_THIS_NOTEBOOK_EXECUTION; stage is registered and its worker route is available after explicit resource authorization",
            additional={
                "production_worker_route": "src.runners.task40_v10_worker.run_task40_v10_p6_reference_worker",
                "target_heavy_authorized": False,
                "full_field_release_allowed": False,
                "resource_sample": preflight["resources"],
            },
        )

    geometry_facts = None
    mesh_data = cfg = classes = None
    if mesh_id == "TARGET_ORIGINAL_NY8" and stop_stage in {
        "geometry_inventory",
        "local_port_components",
        "build_and_symbolic",
        "one_q_numeric",
    }:
        from src.geometry.task40_v20_geometry import build_v20_geometry_inventory

        geometry_facts, mesh_data, cfg, classes = build_v20_geometry_inventory(
            resolved_payload, output_directory
        )
        _write_json(output_directory / "v20_geometry_inventory.json", geometry_facts)
        completed.append("geometry_inventory")

    local_facts = None
    if mesh_id == "TARGET_ORIGINAL_NY8" and stop_stage in {
        "local_port_components",
        "build_and_symbolic",
        "one_q_numeric",
    }:
        if modes is None or mode_rows is None:
            raise RuntimeError("target V20 local/port stage requires the frozen AUTO mode table")
        from src.solvers.task40_v20_local_components import run_v20_local_port_components

        local_facts = run_v20_local_port_components(
            resolved_payload,
            output_directory,
            mesh_data=mesh_data,
            cfg=cfg,
            geometry_facts=geometry_facts,
            classes=classes,
            mode_rows=mode_rows,
            resource_sample=_resource_snapshot,
        )
        _write_json(output_directory / "v20_local_port_components.json", local_facts)
        completed.append("local_port_components")
        if local_facts.get("status") != "PASS":
            receipt = {
                "schema": "task40extra.review_v20_partial_result.v1",
                "status": "failed",
                "classification": "LOCAL_COMPONENT_GATE_FAILED",
                "run_id": preflight["run_id"],
                "profile": profile,
                "source_sha": source_sha,
                "input_sha256": preflight["input_sha256"],
                "physical_model_sha256": preflight["physical_model_sha256"],
                "requested_stop_stage": stop_stage,
                "completed_stages": completed,
                "official_result": False,
                "not_run": ["all-q CSR/symbolic", "one-q numeric", "full field"],
                "local_port_components": local_facts,
            }
            _write_json(output_directory / "v20_partial_result.json", receipt)
            return {
                "passed": False,
                "errors": ["V20 original-size local/port component gate failed"],
                "official_result": False,
                "status": "failed",
                "summary": receipt,
                "numerical_output_directory": str(output_directory),
            }

    if stop_stage in {"build_and_symbolic", "one_q_numeric"}:
        from src.runners.task40_v10_worker import run_task40_v10_p6_reference_worker

        return run_task40_v10_p6_reference_worker(
            resolved_payload,
            output_directory,
            source_sha=source_sha,
            profile_identity=profile,
            share_transform_bank=True,
            stop_after_stage=stop_stage,
        )

    if profile.endswith("_e2_reference_v1") and stop_stage == "full":
        from src.runners.task40_v10_worker import run_task40_v10_p6_reference_worker

        return run_task40_v10_p6_reference_worker(
            resolved_payload,
            output_directory,
            source_sha=source_sha,
            profile_identity=profile,
            share_transform_bank=True,
        )

    receipt = {
        "schema": "task40extra.review_v20_partial_result.v1",
        "status": "controlled_stop",
        "classification": "CONTROLLED_STOP_AT_REQUESTED_STAGE",
        "run_id": preflight["run_id"],
        "profile": profile,
        "source_sha": source_sha,
        "input_sha256": preflight["input_sha256"],
        "physical_model_sha256": preflight["physical_model_sha256"],
        "requested_stop_stage": stop_stage,
        "completed_stages": completed,
        "official_result": False,
        "not_run": [
            name for name in V20_STAGE_NAMES if name not in completed
        ],
        "geometry_inventory": geometry_facts,
        "local_port_components": local_facts,
        "full_field_release_allowed": False,
        "resources": _resource_snapshot(),
    }
    _write_json(output_directory / "v20_partial_result.json", receipt)
    return {
        "passed": True,
        "errors": [],
        "official_result": False,
        "status": "controlled_stop",
        "summary": receipt,
        "numerical_output_directory": str(output_directory),
    }


__all__ = ["run_task40_v20_stage", "V20_STAGE_NAMES", "V20_TARGET_Q0"]
