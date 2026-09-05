"""Task041 mode-preparation worker for a fresh exact-side packet.

This module deliberately stops after the selected-mode packet has been
written.  It does not assemble local systems, factors, global FGMRES, or
recovery objects.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import time
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.task034_wsl_resources import resource_authority_sample
from benchmarks.task039_v4_selected_mode_packet import (
    TASK041_SELECTED_MODE_IDENTITY_SCHEMA,
    TASK041_SHORTWAVE_SELECTED_MODE_IDENTITY_SCHEMA,
    task041_selected_mode_scope,
    task041_shortwave_selected_mode_scope,
)
from src.io.input_validation import (
    TASK041_SHORTWAVE_MPI_SIZE,
    load_and_resolve,
    simulation_config_3d_from_normalized,
    task041_profile_errors,
    task041_shortwave_case,
    task041_shortwave_profile_errors,
)
from src.io.resolved_config import resolved_config_sha256
from src.solvers.hybrid_interface_basis import canonical_mode_keys_sha256

TASK041_MODE_PREP_SCHEMA = "task041.exact_side.mode_prep.v1"
TASK041_MODE_PREP_PROFILE = "task041_5nm_exact_side_hybrid_iterative"
TASK041_MODE_PREP_PHASE = "mode-prep"
TASK041_CONSUMER_SCHEMA = "task041.exact_side.consumer.v1"
TASK041_CONSUMER_PROFILE = "task041_5nm_exact_side_hybrid_iterative_consumer"
TASK041_SHORTWAVE_CONSUMER_SCHEMA = "task041.exact_side.consumer.v2"
TASK041_SHORTWAVE_CONSUMER_PROFILE = (
    "task041_3nm_exact_side_hybrid_iterative_consumer"
)
TASK041_CONSUMER_PHASE = "consumer"
TASK041_INPUT = "input/official/task041/5nm_p6h4_m480_mpi1.dat"
TASK041_WARNING_MEMORY_BYTES = 192 * 2**30
TASK041_HARD_MEMORY_BYTES = 256 * 2**30
TASK041_MIN_MEMAVAILABLE_BYTES = 384 * 2**30
TASK041_TIMEOUT_SECONDS = 172800
TASK041_MARKER_SEQUENCE = (
    "preflight_begin",
    "qep_begin",
    "qep_ready",
    "packet_written",
    "cleanup_complete",
)
TASK041_CONSUMER_MARKER_SEQUENCE = (
    "preflight_begin",
    "input_validated",
    "packet_identity_validated",
    "packet_manifest_validated",
    "system_setup_stage",
    "system_ready",
    "bottom_F_ready",
    "bottom_factor_setup_begin",
    "bottom_factor_ready",
    "bottom_woodbury_ready",
    "bottom_construction_cleanup",
    "top_F_ready",
    "top_factor_setup_begin",
    "top_factor_ready",
    "top_woodbury_ready",
    "top_construction_cleanup",
    "both_side_actions_ready",
    "modal_schur_build_begin",
    "modal_schur_ready",
    "outer_ksp_setup_ready",
    "outer_setup_probe_ksp_released",
    "outer_solve_begin",
    "solve_started",
    "outer_solve_progress",
    "solution_snapshot_created",
    "solution_snapshot",
    "outer_solve_ready",
    "solve_complete",
    "true_residual_complete",
    "minimal_recovery_packet_saved",
    "outer_ksp_destroyed",
    "bottom_top_factors_destroyed",
    "large_matrices_destroyed",
    "outer_solve_objects_cleanup",
    "rss_drop_confirmed",
    "recovery_physics_begin",
    "recovery_started",
    "recovery_stage",
    "recovery_physics_end",
    "recovery_complete",
    "solution_snapshot_destroyed",
    "authority_validated",
    "official_outputs_written",
    "all_setup_objects_cleanup",
    "final_cleanup_complete",
)
TASK041_CONSUMER_SAMPLE_COLUMNS = (0, 1, 240, 267, 479, 480, 481, 720, 746, 959)
TASK041_CONSUMER_SAMPLE_ROLES = {
    "0": [
        "selection_order_head",
        "high_priority_proxy",
        "bottom_positive_unattenuated",
    ],
    "1": ["first_group_neighbor", "bottom_positive_unattenuated"],
    "240": ["interior_selection_order", "bottom_positive_unattenuated"],
    "267": ["basis_l2_norm_proxy", "bottom_positive_unattenuated"],
    "479": [
        "selection_order_tail",
        "high_abs_beta_proxy",
        "bottom_positive_unattenuated",
    ],
    "480": [
        "selection_order_head",
        "high_priority_proxy",
        "top_negative_unattenuated",
    ],
    "481": ["first_group_neighbor", "top_negative_unattenuated"],
    "720": ["interior_selection_order", "top_negative_unattenuated"],
    "746": ["basis_l2_norm_proxy", "top_negative_unattenuated"],
    "959": [
        "selection_order_tail",
        "high_abs_beta_proxy",
        "top_negative_unattenuated",
    ],
}
TASK041_CONSUMER_SAMPLE_CONTRACT_SHA256 = (
    "8d73d77a47fe0aa614e231eaac1f939eb28cca5b01c024c70fd518a3a592f082"
)


class Task041ModePrepError(RuntimeError):
    """A fail-closed identity or mode-preparation error."""


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    return value


def _valid_sha(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and value == value.lower()
        and all(char in "0123456789abcdef" for char in value)
    )


def _module_path(name: str) -> str | None:
    spec = importlib.util.find_spec(name)
    if spec is None:
        return None
    if spec.origin not in (None, "built-in"):
        return str(Path(spec.origin).resolve())
    if spec.submodule_search_locations:
        return str(Path(next(iter(spec.submodule_search_locations))).resolve())
    return None


def _environment_snapshot() -> dict[str, Any]:
    executable_entry = Path(os.path.abspath(sys.executable))
    executable_target = executable_entry.resolve()
    prefix = Path(sys.prefix).resolve()
    repo_root = Path(__file__).resolve().parents[1]
    repo_venv = repo_root / ".venv"
    repo_venv_resolved = repo_venv.resolve()
    packages = {
        name: _module_path(name)
        for name in ("basix", "dolfinx", "mpi4py", "petsc4py", "slepc4py")
    }
    thread_names = (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    )
    threads = {name: os.environ.get(name) for name in thread_names}
    scalar_type = str(np.dtype(PETSc.ScalarType))
    int_type = str(np.dtype(PETSc.IntType))
    snapshot = {
        "marker": os.environ.get("MYFENICS_NATIVE_COMPLEX_ENV"),
        "python": str(executable_entry),
        "python_resolved_target": str(executable_target),
        "sys_prefix": str(prefix),
        "petsc_scalar_type": scalar_type,
        "petsc_int_type": int_type,
        "packages": packages,
        "threads": threads,
    }
    failures: list[str] = []
    if snapshot["marker"] != "1":
        failures.append("MYFENICS_NATIVE_COMPLEX_ENV must be 1")
    if repo_venv not in executable_entry.parents:
        failures.append("sys.executable entry is outside repository .venv")
    if prefix != repo_venv_resolved:
        failures.append("sys.prefix does not resolve to repository .venv")
    if scalar_type != "complex128":
        failures.append(f"PETSc scalar type is {scalar_type!r}, not complex128")
    if int_type != "int32":
        failures.append(f"PETSc IntType is {int_type!r}, not int32")
    if any(value != "1" for value in threads.values()):
        failures.append("all Task041 thread controls must equal 1")
    if failures:
        raise Task041ModePrepError("; ".join(failures))
    return snapshot


def task041_inner_mpi_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """Prepare a copied environment for a future inner MPI process."""

    thread_names = (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    )
    cleaned = {
        key: value
        for key, value in environment.items()
        if not (
            key in {"OMPI", "PMIX", "PMI"}
            or key.startswith(("OMPI_", "PMIX_", "PMI_"))
            or key in {"DISPLAY", "XAUTHORITY"}
        )
    }
    cleaned.update({name: "1" for name in thread_names})
    return cleaned


def _inventory_from_payload(normalized: Mapping[str, Any]) -> tuple[list[Any], int]:
    inventory = normalized["derived"]["external_mode_inventory"]
    if not isinstance(inventory, Mapping):
        raise Task041ModePrepError("external_mode_inventory is not a mapping")
    keys = inventory["keys"]
    count = inventory["count"]
    if type(count) is not int or count <= 0:
        raise Task041ModePrepError("external_mode_inventory.count must be a positive int")
    if not isinstance(keys, list) or len(keys) != count:
        raise Task041ModePrepError("external_mode_inventory.keys/count mismatch")
    if any(not isinstance(key, Mapping) for key in keys):
        raise Task041ModePrepError("external_mode_inventory.keys must contain mappings")
    return [_jsonable(key) for key in keys], count


def _task041_canonical_mode_keys_sha256(keys: Sequence[Any]) -> str:
    """Hash Task041 external keys in explicit physical canonical order."""

    physical_keys: list[tuple[tuple[int, int, int, int], Any]] = []
    side_order = {"bottom": 0, "top": 1}
    polarization_order = {"p": 0, "s": 1}
    for index, raw_key in enumerate(keys):
        key = _jsonable(raw_key)
        if not isinstance(key, Mapping):
            raise Task041ModePrepError(
                f"external key {index} must be a mapping"
            )
        side = key.get("side")
        if not isinstance(side, str) or side not in side_order:
            raise Task041ModePrepError(
                f"external key {index} side must be 'bottom' or 'top'"
            )
        m = key.get("m")
        if type(m) is not int:
            raise Task041ModePrepError(
                f"external key {index} m must be an integer"
            )
        n = key.get("n")
        if type(n) is not int:
            raise Task041ModePrepError(
                f"external key {index} n must be an integer"
            )
        polarization = key.get("polarization")
        if not isinstance(polarization, str) or polarization not in polarization_order:
            raise Task041ModePrepError(
                f"external key {index} polarization must be 'p' or 's'"
            )
        physical_keys.append(
            (
                (
                    side_order[side],
                    m,
                    n,
                    polarization_order[polarization],
                ),
                key,
            )
        )
    ordered = [key for _, key in sorted(physical_keys, key=lambda item: item[0])]
    return canonical_mode_keys_sha256(ordered)


def _requested_mode_count(normalized: Mapping[str, Any]) -> int:
    value = normalized["method"]["requested_modes_per_direction"]
    if type(value) is not int or value < 2:
        raise Task041ModePrepError("requested_modes_per_direction must be an int >= 2")
    return value


def _task041_mesh_identity() -> dict[str, Any]:
    return {
        "cell_type": "hexahedron",
        "kind": "full3d_uniform_cg",
        "mesh_target_nm": 4.0,
        "nedelec_degree": 6,
        "spacing_mode": "boundary_fitted",
    }


def build_task041_shortwave_packet_identity(
    specification: Any,
    normalized: Mapping[str, Any],
    source_sha: str,
    resolved_sha: str,
) -> dict[str, Any]:
    """Recompute the v2 packet identity for the two approved 3 nm cases."""

    case = task041_shortwave_case(normalized.get("model_id", ""))
    if case is None:
        raise Task041ModePrepError(
            "Task41 shortwave identity requires a validated M800 or M1200 model_id"
        )
    profile_failures = tuple(task041_shortwave_profile_errors(normalized))
    if profile_failures:
        detail = "; ".join(f"{field}: {message}" for field, message in profile_failures)
        raise Task041ModePrepError("Task41 shortwave profile rejected: " + detail)
    if not _valid_sha(source_sha, 40):
        raise Task041ModePrepError("source_sha must be a lowercase 40-character SHA")
    if not _valid_sha(resolved_sha, 64):
        raise Task041ModePrepError("resolved_sha must be a lowercase 64-character SHA")
    keys, count = _inventory_from_payload(normalized)
    mode_count = _requested_mode_count(normalized)
    input_sha = str(specification.input_sha256)
    physical_sha = str(specification.physical_model_sha256)
    if not _valid_sha(input_sha, 64) or not _valid_sha(physical_sha, 64):
        raise Task041ModePrepError("input and physical identities must be lowercase SHA256")
    mpi_size = int(normalized["execution"]["mpi_size"])
    identity = {
        "schema": TASK041_SHORTWAVE_SELECTED_MODE_IDENTITY_SCHEMA,
        "scope": task041_shortwave_selected_mode_scope(mode_count, mpi_size),
        "source_sha": source_sha,
        "input_sha256": input_sha,
        "resolved_sha256": resolved_sha,
        "physical_sha256": physical_sha,
        "wavelength_nm": normalized["incidence"]["wavelength_nm"],
        "model_id": normalized["model_id"],
        "run_id": normalized["run_id"],
        "mesh": {
            "cell_type": normalized["discretization"]["mesh_cell_type"],
            "kind": normalized["method"]["propagation_model"],
            "mesh_target_nm": normalized["discretization"]["mesh_target_nm"],
            "nedelec_degree": normalized["discretization"]["nedelec_degree"],
            "spacing_mode": normalized["discretization"]["mesh_spacing_mode"],
        },
        "mode_count": mode_count,
        "mpi_size": mpi_size,
        "requested_modes_per_direction": mode_count,
        "dtn_order_policy": normalized["boundary"]["dtn_order_policy"],
        "external_keys": {"count": count, "sha256": _task041_canonical_mode_keys_sha256(keys)},
        "cross_section_partition": "input_contiguous_v1",
    }
    return identity


def build_task041_packet_identity(
    specification: Any,
    normalized: Mapping[str, Any],
    source_sha: str,
    resolved_sha: str,
) -> dict[str, Any]:
    """Recompute the complete packet identity from the validated payload."""

    profile_failures = tuple(task041_profile_errors(normalized))
    if profile_failures:
        detail = "; ".join(f"{field}: {message}" for field, message in profile_failures)
        raise Task041ModePrepError("Task041 profile rejected: " + detail)
    if not _valid_sha(source_sha, 40):
        raise Task041ModePrepError("source_sha must be a lowercase 40-character SHA")
    if not _valid_sha(resolved_sha, 64):
        raise Task041ModePrepError("resolved_sha must be a lowercase 64-character SHA")
    keys, count = _inventory_from_payload(normalized)
    mode_count = _requested_mode_count(normalized)
    input_sha = str(specification.input_sha256)
    physical_sha = str(specification.physical_model_sha256)
    if not _valid_sha(input_sha, 64) or not _valid_sha(physical_sha, 64):
        raise Task041ModePrepError("input and physical identities must be lowercase SHA256")
    external_key_sha = _task041_canonical_mode_keys_sha256(keys)
    expected_model = (
        "task041_5nm_exact_side_hybrid_iterative_p6h4_"
        f"m{mode_count}"
    )
    expected_run = f"task041_5nm_p6h4_m{mode_count}_mpi1"
    identity = {
        "schema": TASK041_SELECTED_MODE_IDENTITY_SCHEMA,
        "scope": task041_selected_mode_scope(mode_count, 1),
        "source_sha": source_sha,
        "input_sha256": input_sha,
        "resolved_sha256": resolved_sha,
        "physical_sha256": physical_sha,
        "wavelength_nm": 5.0,
        "model_id": expected_model,
        "run_id": expected_run,
        "mesh": _task041_mesh_identity(),
        "mode_count": mode_count,
        "mpi_size": 1,
        "external_keys": {"count": count, "sha256": external_key_sha},
    }
    if normalized["model_id"] != expected_model:
        raise Task041ModePrepError("validated model_id does not match recomputed identity")
    if normalized["run_id"] != expected_run:
        raise Task041ModePrepError("validated run_id does not match recomputed identity")
    return identity


def build_task041_mode_prep_command(
    python_executable: str | Path,
    input_path: str | Path,
    run_directory: str | Path,
    source_sha: str,
) -> list[str]:
    """Return the required fresh MPI1 worker command, without launching it."""

    return [
        "mpiexec",
        "-n",
        "1",
        str(python_executable),
        "-m",
        "benchmarks.task041_exact_side_workflow",
        "--worker",
        "--phase",
        TASK041_MODE_PREP_PHASE,
        "--input",
        str(input_path),
        "--run-directory",
        str(run_directory),
        "--source-sha",
        source_sha,
    ]


def build_task041_shortwave_mode_prep_command(
    python_executable: str | Path,
    specification: Any,
    run_directory: str | Path,
    source_sha: str,
) -> list[str]:
    """Build the opt-in MPI8 producer command from one resolved specification."""

    normalized = specification.as_jsonable()
    profile_failures = tuple(task041_shortwave_profile_errors(normalized))
    if profile_failures:
        detail = "; ".join(f"{field}: {message}" for field, message in profile_failures)
        raise Task041ModePrepError(
            "Task41 shortwave profile rejected: " + detail
        )
    input_path = Path(specification.source_path)
    mpi_size = normalized["execution"]["mpi_size"]
    if type(mpi_size) is not int or mpi_size != TASK041_SHORTWAVE_MPI_SIZE:
        raise Task041ModePrepError(
            "Task41 shortwave command requires validated MPI8 execution"
        )
    return [
        "mpiexec",
        "-n",
        str(mpi_size),
        "--bind-to",
        "cpu-list:ordered",
        "--cpu-list",
        "0-7",
        "--report-bindings",
        str(python_executable),
        "-m",
        "benchmarks.task041_exact_side_workflow",
        "--worker",
        "--phase",
        TASK041_MODE_PREP_PHASE,
        "--input",
        str(input_path),
        "--run-directory",
        str(run_directory),
        "--source-sha",
        source_sha,
    ]


def _resource_snapshot() -> dict[str, Any]:
    return _jsonable(resource_authority_sample(os.getpid()))


def _memavailable_bytes() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise Task041ModePrepError("/proc/meminfo has no MemAvailable")


def _check_resource(sample: Mapping[str, Any], started: float) -> None:
    memory_authority = sample.get("memory_authority_bytes")
    if not isinstance(memory_authority, (int, float, np.integer, np.floating)):
        raise Task041ModePrepError("resource sample lacks memory_authority_bytes")
    if float(memory_authority) >= TASK041_HARD_MEMORY_BYTES:
        raise Task041ModePrepError("Task041 hard RSS limit reached")
    if sample.get("job_no_swap") is not True:
        raise Task041ModePrepError("Task041 swap limit reached")
    if time.monotonic() - started >= TASK041_TIMEOUT_SECONDS:
        raise Task041ModePrepError("Task041 mode-prep timeout reached")


def _process_tree_rss(sample: Mapping[str, Any]) -> int | None:
    process_tree = sample.get("process_tree")
    if not isinstance(process_tree, Mapping):
        return None
    value = process_tree.get("rss_bytes")
    if isinstance(value, bool) or not isinstance(
        value, (int, float, np.integer, np.floating)
    ):
        return None
    return int(value)


def _memory_authority(sample: Mapping[str, Any]) -> int | None:
    value = sample.get("memory_authority_bytes")
    if isinstance(value, bool) or not isinstance(
        value, (int, float, np.integer, np.floating)
    ):
        return None
    return int(value)


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(_jsonable(payload), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_marker(
    root: Path,
    started: float,
    stage: str,
    *,
    environment: Mapping[str, Any],
    detail: Mapping[str, Any],
    comm: Any,
    schema: str = TASK041_MODE_PREP_SCHEMA,
    marker_sequence: Sequence[str] = TASK041_MARKER_SEQUENCE,
) -> dict[str, Any]:
    resource = _resource_snapshot()
    _check_resource(resource, started)
    marker = {
        "schema": schema,
        "stage": stage,
        "sequence_index": marker_sequence.index(stage),
        "wall_seconds": time.monotonic() - started,
        "environment": _jsonable(environment),
        "limits": {
            "warning_memory_bytes": TASK041_WARNING_MEMORY_BYTES,
            "hard_memory_bytes": TASK041_HARD_MEMORY_BYTES,
            "min_memavailable_bytes": TASK041_MIN_MEMAVAILABLE_BYTES,
            "timeout_seconds": TASK041_TIMEOUT_SECONDS,
        },
        "resource": resource,
        "detail": _jsonable(detail),
    }
    if comm.rank == 0:
        with (root / "markers.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(marker, sort_keys=True) + "\n")
    comm.Barrier()
    return marker


def _producer_argv(
    packet_directory: Path,
    identity_path: Path,
    output_path: Path,
    source_sha: str,
    mode_count: int,
    *,
    mesh_target_nm: float = 4.0,
    degree: int = 6,
) -> list[str]:
    mesh_token = f"{float(mesh_target_nm):g}"
    degree_token = str(degree)
    return [
        "--output",
        str(output_path),
        "--h-nm",
        mesh_token,
        "--degree",
        degree_token,
        "--modal-h-nm",
        mesh_token,
        "--modal-degree",
        degree_token,
        "--internal-propagation-model",
        "full3d_uniform_cg",
        "--internal-traction-model",
        "full3d_one_cell_exact_schur",
        "--stage4-full3d-assembly-backend",
        "assembly_time_static_condensed",
        "--incident-grazing-deg",
        "1",
        "--polarization-kind",
        "s",
        "--requested-modes",
        str(mode_count),
        "--candidate-modes",
        str(2 * mode_count),
        "--solver-path",
        "augmented",
        "--retained-subspace-dual-rotation",
        "--selected-mode-packet-producer-dir",
        str(packet_directory),
        "--selected-mode-packet-identity-json",
        str(identity_path),
        "--verified-clean-sha",
        source_sha,
    ]


def run_task041_mode_prep(
    *,
    input_path: str | Path,
    run_directory: str | Path,
    source_sha: str,
    comm: Any = MPI.COMM_WORLD,
) -> dict[str, Any]:
    """Run only the Task041 selected-mode producer and controlled stop."""

    if comm.size != 1:
        raise Task041ModePrepError("Task041 mode-prep requires MPI.COMM_WORLD size 1")
    if not _valid_sha(source_sha, 40):
        raise Task041ModePrepError("source_sha must be a lowercase 40-character SHA")
    root = Path(run_directory).resolve()
    if root.exists():
        raise FileExistsError(f"Task041 run directory already exists: {root}")
    root.mkdir(parents=True)
    started = time.monotonic()
    result: dict[str, Any] = {
        "schema": TASK041_MODE_PREP_SCHEMA,
        "profile": TASK041_MODE_PREP_PROFILE,
        "phase": TASK041_MODE_PREP_PHASE,
        "input": str(Path(input_path).resolve()),
        "run_directory": str(root),
        "source_sha": source_sha,
        "status": "IMPLEMENTATION_FAILURE",
        "classification": "IMPLEMENTATION_FAILURE",
        "official_rta": {"status": "not_run"},
        "limits": {
            "warning_memory_bytes": TASK041_WARNING_MEMORY_BYTES,
            "hard_memory_bytes": TASK041_HARD_MEMORY_BYTES,
            "min_memavailable_bytes": TASK041_MIN_MEMAVAILABLE_BYTES,
            "timeout_seconds": TASK041_TIMEOUT_SECONDS,
        },
        "producer_scope": {
            "local_systems": "not_run",
            "coupling": "not_run",
            "factor": "not_run",
            "solve": "not_run",
            "recovery": "not_run",
        },
        "counts": {
            "local_systems": 0,
            "coupling": 0,
            "factor": 0,
            "solve": 0,
            "recovery": 0,
        },
        "lifecycle": {
            "local_systems_created": False,
            "coupling_created": False,
            "factor_created": False,
            "solver_created": False,
            "recovery_created": False,
        },
    }
    environment: dict[str, Any] = {}
    error: BaseException | None = None
    try:
        environment = _environment_snapshot()
        result["environment"] = environment
        _write_marker(
            root,
            started,
            "preflight_begin",
            environment=environment,
            detail={"mpi_size": comm.size, "input": str(input_path)},
            comm=comm,
        )
        available = _memavailable_bytes()
        if available < TASK041_MIN_MEMAVAILABLE_BYTES:
            raise Task041ModePrepError("MemAvailable is below the Task041 preflight floor")
        result["memavailable_bytes"] = available
        specification = load_and_resolve(input_path)
        normalized = specification.as_jsonable()
        resolved_sha = resolved_config_sha256(specification)
        cfg = simulation_config_3d_from_normalized(normalized)
        identity = build_task041_packet_identity(
            specification, normalized, source_sha, resolved_sha
        )
        recomputed_identity = build_task041_packet_identity(
            specification, normalized, source_sha, resolved_sha
        )
        if identity != recomputed_identity:
            raise Task041ModePrepError("Task041 identity recomputation mismatch")
        result["identity"] = identity
        identity_path = root / "packet_identity.json"
        _write_json(identity_path, identity)
        mode_count = identity["mode_count"]
        packet_directory = root / "selected_mode_packet"
        producer_output = root / "producer_summary.json"
        _write_marker(
            root,
            started,
            "qep_begin",
            environment=environment,
            detail={"qep": "selection_only", "mode_count": mode_count},
            comm=comm,
        )
        from benchmarks.run_task032_phase6_augmented import main as producer_main

        producer_record = producer_main(
            _producer_argv(
                packet_directory,
                identity_path,
                producer_output,
                source_sha,
                mode_count,
            ),
            config_override=cfg,
            canonical_export_prefix="task041_mode_prep",
            task039_stage_marker_path=root / "producer_markers.jsonl",
            task041_mode_prep=True,
        )
        if not isinstance(producer_record, Mapping):
            raise Task041ModePrepError("producer did not return a mapping record")
        if producer_record.get("task041_mode_prep") is not True:
            raise Task041ModePrepError("producer did not report Task041 mode-prep")
        if any(
            producer_record.get(name) not in {"not_run", "not_created"}
            for name in ("local_systems", "coupling", "factor", "solve", "recovery")
        ):
            raise Task041ModePrepError("producer crossed the mode-prep stop boundary")
        manifest_path = packet_directory / "manifest.json"
        if not manifest_path.is_file():
            raise Task041ModePrepError("selected-mode packet manifest was not written")
        result["producer"] = _jsonable(producer_record)
        result["packet"] = {
            "directory": str(packet_directory),
            "manifest": str(manifest_path),
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        }
        _write_marker(
            root,
            started,
            "qep_ready",
            environment=environment,
            detail={"producer_status": producer_record.get("status")},
            comm=comm,
        )
        _write_marker(
            root,
            started,
            "packet_written",
            environment=environment,
            detail=result["packet"],
            comm=comm,
        )
        result["status"] = "controlled_stop_packet_written"
        result["classification"] = "TASK041_MODE_PREP_PACKET_READY"
    except Exception as exc:  # noqa: BLE001 - record failure before re-raising
        error = exc
        result["status"] = "IMPLEMENTATION_FAILURE"
        result["classification"] = "IMPLEMENTATION_FAILURE"
        result["error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        result["wall_seconds"] = time.monotonic() - started
        result["environment"] = environment
        try:
            _write_marker(
                root,
                started,
                "cleanup_complete",
                environment=environment,
                detail={
                    "status": result["status"],
                    "classification": result["classification"],
                    "local_systems": "not_created",
                    "coupling": "not_created",
                    "factor": "not_created",
                    "solve": "not_created",
                    "recovery": "not_created",
                },
                comm=comm,
            )
            result["cleanup"] = {"producer_scope_released": True}
        except Exception as cleanup_error:  # noqa: BLE001 - preserve cleanup evidence
            result["cleanup"] = {
                "producer_scope_released": False,
                "error": {
                    "type": type(cleanup_error).__name__,
                    "message": str(cleanup_error),
                },
            }
            if error is None:
                error = cleanup_error
                result["status"] = "IMPLEMENTATION_FAILURE"
                result["classification"] = "IMPLEMENTATION_FAILURE"
                result["error"] = {
                    "type": type(cleanup_error).__name__,
                    "message": str(cleanup_error),
                }
        _write_json(root / "mode_prep_summary.json", result)
    if error is not None:
        raise error
    return result


def build_task041_consumer_command(
    python_executable: str | Path,
    input_path: str | Path,
    packet_manifest: str | Path,
    packet_identity: str | Path,
    packet_manifest_sha256: str,
    run_directory: str | Path,
    source_sha: str,
) -> list[str]:
    """Return the fresh MPI1 consumer command for a producer packet."""

    return [
        "mpiexec",
        "-n",
        "1",
        str(python_executable),
        "-m",
        "benchmarks.task041_exact_side_workflow",
        "--worker",
        "--phase",
        TASK041_CONSUMER_PHASE,
        "--input",
        str(input_path),
        "--packet-manifest",
        str(packet_manifest),
        "--packet-identity",
        str(packet_identity),
        "--packet-manifest-sha256",
        packet_manifest_sha256,
        "--run-directory",
        str(run_directory),
        "--source-sha",
        source_sha,
    ]


def build_task041_shortwave_consumer_command(
    python_executable: str | Path,
    specification: Any,
    packet_manifest: str | Path,
    packet_identity: str | Path,
    packet_manifest_sha256: str,
    run_directory: str | Path,
    source_sha: str,
) -> list[str]:
    """Return the fresh MPI8 shortwave consumer command for a packet."""

    normalized = specification.as_jsonable()
    profile_failures = tuple(task041_shortwave_profile_errors(normalized))
    if profile_failures:
        detail = "; ".join(f"{field}: {message}" for field, message in profile_failures)
        raise Task041ModePrepError("Task41 shortwave profile rejected: " + detail)
    mpi_size = normalized["execution"]["mpi_size"]
    if type(mpi_size) is not int or mpi_size != TASK041_SHORTWAVE_MPI_SIZE:
        raise Task041ModePrepError(
            "Task41 shortwave consumer command requires validated MPI8 execution"
        )
    input_path = Path(specification.source_path)
    return [
        "mpiexec",
        "-n",
        str(mpi_size),
        "--bind-to",
        "cpu-list:ordered",
        "--cpu-list",
        "0-7",
        "--report-bindings",
        str(python_executable),
        "-m",
        "benchmarks.task041_exact_side_workflow",
        "--worker",
        "--phase",
        TASK041_CONSUMER_PHASE,
        "--input",
        str(input_path),
        "--packet-manifest",
        str(packet_manifest),
        "--packet-identity",
        str(packet_identity),
        "--packet-manifest-sha256",
        packet_manifest_sha256,
        "--run-directory",
        str(run_directory),
        "--source-sha",
        source_sha,
    ]


def _task041_consumer_packet_binding(
    contract_sha256: str,
    identity: Mapping[str, Any],
    manifest_sha256: str,
) -> dict[str, Any]:
    identity_json = json.dumps(
        _jsonable(identity), sort_keys=True, separators=(",", ":")
    )
    identity_sha256 = hashlib.sha256(identity_json.encode("utf-8")).hexdigest()
    payload = {
        "binding_semantics": "path_neutral_identity_and_manifest",
        "sampled_column_contract_sha256": contract_sha256,
        "packet_identity_canonical_json": identity_json,
        "packet_identity_sha256": identity_sha256,
        "packet_manifest_sha256": manifest_sha256,
    }
    binding_sha256 = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {**payload, "binding_sha256": binding_sha256}


def task041_consumer_iterative_config() -> Any:
    """Return the fixed Task041 outer FGMRES configuration."""

    from src.solvers.hybrid_fem_modal_block_ldu import HybridBlockLduIterativeConfig

    return HybridBlockLduIterativeConfig(
        ksp_type="fgmres",
        restart=90,
        max_it=4000,
        threshold=5.0e-9,
        initial_guess="zero",
        fixed_preconditioner=False,
    )


def _task041_consumer_profile() -> Any:
    from src.runners.task039_hybrid_iterative import (
        make_task039_hybrid_iterative_profile,
    )

    return replace(
        make_task039_hybrid_iterative_profile(480, 8, mesh_target_nm=4.0),
        profile_id=TASK041_CONSUMER_PROFILE,
        record_schema=TASK041_CONSUMER_SCHEMA,
        qualification_schema=TASK041_CONSUMER_SCHEMA,
        mpi_size=1,
    )


def _task041_shortwave_consumer_profile(specification: Any) -> Any:
    normalized = specification.as_jsonable()
    case = task041_shortwave_case(str(normalized.get("model_id", "")))
    if case is None:
        raise Task041ModePrepError(
            "Task41 shortwave consumer requires an approved M800 or M1200 case"
        )
    profile_failures = tuple(task041_shortwave_profile_errors(normalized))
    if profile_failures:
        detail = "; ".join(f"{field}: {message}" for field, message in profile_failures)
        raise Task041ModePrepError("Task41 shortwave profile rejected: " + detail)
    incidence = normalized["incidence"]
    discretization = normalized["discretization"]
    method = normalized["method"]
    execution = normalized["execution"]
    return replace(
        _task041_consumer_profile(),
        profile_id=TASK041_SHORTWAVE_CONSUMER_PROFILE,
        record_schema=TASK041_SHORTWAVE_CONSUMER_SCHEMA,
        qualification_schema=TASK041_SHORTWAVE_CONSUMER_SCHEMA,
        wavelength_nm=incidence["wavelength_nm"],
        requested_modes=method["requested_modes_per_direction"],
        candidate_modes=2 * method["requested_modes_per_direction"],
        mpi_size=execution["mpi_size"],
        h_nm=discretization["mesh_target_nm"],
        modal_h_nm=discretization["mesh_target_nm"],
    )


def _task041_consumer_sampled_column_contract(
    identity: Mapping[str, Any],
    manifest_path: Path,
    manifest_sha256: str,
) -> dict[str, Any]:
    """Bind the fixed v1 or shortwave v2 sampled roles to a fresh manifest."""

    identity_schema = identity.get("schema")
    if identity_schema == TASK041_SHORTWAVE_SELECTED_MODE_IDENTITY_SCHEMA:
        mode_count = identity.get("mode_count")
        if type(mode_count) is not int or mode_count not in (800, 1200):
            raise Task041ModePrepError(
                "Task041 shortwave sampled contract requires M800 or M1200"
            )
        if (
            type(identity.get("mpi_size")) is not int
            or identity.get("mpi_size") != TASK041_SHORTWAVE_MPI_SIZE
        ):
            raise Task041ModePrepError(
                "Task041 shortwave sampled contract requires MPI8"
            )
        if identity.get("scope") != task041_shortwave_selected_mode_scope(
            mode_count, TASK041_SHORTWAVE_MPI_SIZE
        ):
            raise Task041ModePrepError(
                "Task041 shortwave sampled contract scope does not match M/MPI"
            )
        if identity.get("cross_section_partition") != "input_contiguous_v1":
            raise Task041ModePrepError(
                "Task041 shortwave sampled contract requires input_contiguous_v1"
            )
        offsets = (0, 1, mode_count // 2, mode_count - 1)
        columns = [*offsets, *(mode_count + offset for offset in offsets)]
        roles = {
            str(offsets[0]): [
                "head",
                "high_priority",
                "bottom_positive_unattenuated",
            ],
            str(offsets[1]): [
                "first_group_neighbor",
                "bottom_positive_unattenuated",
            ],
            str(offsets[2]): [
                "interior_midpoint",
                "bottom_positive_unattenuated",
            ],
            str(offsets[3]): [
                "tail",
                "high_abs_beta",
                "bottom_positive_unattenuated",
            ],
            str(mode_count + offsets[0]): [
                "head",
                "high_priority",
                "top_negative_unattenuated",
            ],
            str(mode_count + offsets[1]): [
                "first_group_neighbor",
                "top_negative_unattenuated",
            ],
            str(mode_count + offsets[2]): [
                "interior_midpoint",
                "top_negative_unattenuated",
            ],
            str(mode_count + offsets[3]): [
                "tail",
                "high_abs_beta",
                "top_negative_unattenuated",
            ],
        }
        contract = {
            "columns": columns,
            "mode_count_per_direction": mode_count,
            "roles": roles,
        }
        expected_contract_sha256 = None
    else:
        if identity_schema not in (None, TASK041_SELECTED_MODE_IDENTITY_SCHEMA):
            raise Task041ModePrepError(
                "Task041 consumer sampled contract has an unsupported identity schema"
            )
        if int(identity.get("mode_count", -1)) != 480 or int(
            identity.get("mpi_size", -1)
        ) != 1:
            raise Task041ModePrepError("Task041 consumer sampled contract requires M480/MPI1")
        contract = {
            "columns": list(TASK041_CONSUMER_SAMPLE_COLUMNS),
            "mode_count_per_direction": 480,
            "roles": {
                key: list(value) for key, value in TASK041_CONSUMER_SAMPLE_ROLES.items()
            },
        }
        expected_contract_sha256 = TASK041_CONSUMER_SAMPLE_CONTRACT_SHA256
    if not manifest_path.is_file() or not _valid_sha(manifest_sha256, 64):
        raise Task041ModePrepError("Task041 consumer packet manifest is not available")
    actual_manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if actual_manifest_sha != manifest_sha256:
        raise Task041ModePrepError("Task041 consumer packet manifest hash mismatch")
    actual_contract_sha = hashlib.sha256(
        json.dumps(contract, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if (
        expected_contract_sha256 is not None
        and actual_contract_sha != expected_contract_sha256
    ):
        raise Task041ModePrepError("Task041 sampled column contract drifted")
    binding = _task041_consumer_packet_binding(
        actual_contract_sha, identity, manifest_sha256
    )
    binding_check = hashlib.sha256(
        json.dumps(
            {
                key: binding[key]
                for key in (
                    "binding_semantics",
                    "sampled_column_contract_sha256",
                    "packet_identity_canonical_json",
                    "packet_identity_sha256",
                    "packet_manifest_sha256",
                )
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if binding_check != binding["binding_sha256"]:
        raise Task041ModePrepError("Task041 fresh packet binding hash is not reproducible")
    return {
        **contract,
        "sha256": actual_contract_sha,
        "manifest_path": str(manifest_path),
        "fresh_packet_binding": binding,
    }


def _task041_finite_le(value: Any, limit: float) -> bool:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    return bool(np.isfinite(number) and number >= 0.0 and number <= limit)


def _task041_consumer_authority_gate(
    authority_path: Path,
    formal_result: Mapping[str, Any],
    recomputed_identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Recompute the Task041 observable gates from the fresh authority."""

    if not authority_path.is_file():
        raise Task041ModePrepError("Task041 consumer authority was not written")
    authority = json.loads(authority_path.read_text(encoding="utf-8"))
    if not isinstance(authority, Mapping):
        raise Task041ModePrepError("Task041 consumer authority is not a mapping")
    authority_inventory = authority.get("external_mode_inventory")
    authority_keys = (
        authority_inventory.get("keys")
        if isinstance(authority_inventory, Mapping)
        else None
    )
    authority_external_keys = None
    if isinstance(authority_keys, list):
        authority_external_keys = {
            "count": len(authority_keys),
            "sha256": _task041_canonical_mode_keys_sha256(authority_keys),
        }
    identity_external_keys = recomputed_identity.get("external_keys")
    external_key_binding_pass = bool(
        isinstance(authority_external_keys, Mapping)
        and isinstance(identity_external_keys, Mapping)
        and dict(authority_external_keys) == dict(identity_external_keys)
    )
    authority_identity = {
        "source_sha": authority.get("source_sha")
        == recomputed_identity.get("source_sha"),
        "physical_model_sha256": authority.get("physical_model_sha256")
        == recomputed_identity.get("physical_sha256"),
        "model_id": authority.get("model_id") == recomputed_identity.get("model_id"),
        "mpi_size": type(authority.get("mpi_size")) is int
        and authority.get("mpi_size") == 1
        and recomputed_identity.get("mpi_size") == 1,
        "requested_modes": type(authority.get("requested_modes")) is int
        and authority.get("requested_modes") == 480
        and recomputed_identity.get("mode_count") == 480,
    }
    authority_identity["pass"] = all(authority_identity.values())
    solve = formal_result.get("solve")
    recovery = formal_result.get("recovery")
    if not isinstance(solve, Mapping) or not isinstance(recovery, Mapping):
        raise Task041ModePrepError("Task041 consumer formal result is incomplete")
    postsolve = solve.get("postsolve")
    if not isinstance(postsolve, Mapping):
        raise Task041ModePrepError("Task041 consumer postsolve audit is missing")
    residual_names = (
        "reported_relative_residual",
        "global_true_relative_residual",
        "bottom_true_relative_residual",
        "top_true_relative_residual",
        "modal_true_relative_residual",
    )
    residuals = {name: postsolve.get(name) for name in residual_names}
    residual_pass = all(_task041_finite_le(value, 5.0e-9) for value in residuals.values())
    reason = int(solve.get("converged_reason", -1))
    recovery_pass = recovery.get("pass") is True
    recovery_physics_pass = recovery.get("physics_pass") is True
    recovery_contract_pass = recovery.get("recovery_pass") is True
    recovery_reports = recovery.get("reports")
    external_q_residuals = {
        side: (
            recovery_reports[side]["external_q"].get("auxiliary_relative_residual")
            if isinstance(recovery_reports, Mapping)
            and isinstance(recovery_reports.get(side), Mapping)
            and isinstance(recovery_reports[side].get("external_q"), Mapping)
            else None
        )
        for side in ("bottom", "top")
    }
    external_q_pass = all(
        _task041_finite_le(value, 1.0e-10)
        for value in external_q_residuals.values()
    )
    traction = authority.get("traction", {})
    observables = authority.get("observables", {})
    traction_pass = bool(
        isinstance(traction, Mapping)
        and all(
            isinstance(traction.get(side), Mapping)
            and _task041_finite_le(traction[side].get("relative_residual"), 1.0e-8)
            for side in ("bottom", "top")
        )
    )
    closure_pass = _task041_finite_le(authority.get("closure"), 1.0e-5)
    try:
        balance_delta = abs(
            float(observables.get("A_balance"))
            - float(observables.get("A_volume"))
        )
    except (AttributeError, TypeError, ValueError):
        balance_delta = None
    balance_pass = bool(
        balance_delta is not None
        and _task041_finite_le(balance_delta, 1.0e-5)
    )
    projection_pass = _task041_finite_le(
        authority.get("interface_projection"), 1.0e-8
    )
    canonical = authority.get("canonical")
    canonical_present = bool(
        isinstance(canonical, Mapping)
        and all(
            isinstance(canonical.get(side), Mapping)
            and isinstance(canonical[side].get("roles"), Mapping)
            and set(canonical[side]["roles"]) == {"active_trace", "full_fe"}
            and all(
                isinstance(role, Mapping) and role.get("pass") is True
                for role in canonical[side]["roles"].values()
            )
            for side in ("bottom", "top")
        )
    )
    grid_payload = authority.get("grid_payload")
    grid_arrays = (
        grid_payload.get("arrays") if isinstance(grid_payload, Mapping) else None
    )
    grid_eh_pass = bool(
        isinstance(grid_arrays, Mapping)
        and all(
            isinstance(grid_arrays.get(name), Mapping)
            and isinstance(grid_arrays[name].get("shape"), list)
            and type(grid_arrays[name].get("bytes")) is int
            and grid_arrays[name]["bytes"] >= 0
            and _valid_sha(grid_arrays[name].get("sha256"), 64)
            for name in ("E_V_per_m", "H_A_per_m")
        )
    )
    external_orders = authority.get("external_orders")
    external_channels_pass = bool(
        isinstance(external_orders, list)
        and external_orders
        and all(
            isinstance(row, Mapping)
            and row.get("side") in {"bottom", "top"}
            and type(row.get("m")) is int
            and type(row.get("n")) is int
            and row.get("polarization") in {"s", "p"}
            for row in external_orders
        )
    )
    inventory_key_tokens = (
        [
            json.dumps(key, sort_keys=True, separators=(",", ":"))
            for key in authority_keys
        ]
        if isinstance(authority_keys, list)
        and all(isinstance(key, Mapping) for key in authority_keys)
        else []
    )
    order_key_tokens = (
        [
            json.dumps(
                {
                    key: row[key]
                    for key in ("side", "m", "n", "polarization")
                },
                sort_keys=True,
                separators=(",", ":"),
            )
            for row in external_orders
            if isinstance(row, Mapping)
            and all(key in row for key in ("side", "m", "n", "polarization"))
        ]
        if isinstance(external_orders, list)
        else []
    )
    external_orders_key_binding_pass = bool(
        external_channels_pass
        and isinstance(authority_keys, list)
        and len(inventory_key_tokens) == len(authority_keys)
        and len(order_key_tokens) == len(external_orders)
        and len(inventory_key_tokens) == len(set(inventory_key_tokens))
        and len(order_key_tokens) == len(set(order_key_tokens))
        and set(order_key_tokens) == set(inventory_key_tokens)
    )
    rta_values = {
        "R": observables.get("R_total")
        if isinstance(observables, Mapping)
        else None,
        "T": observables.get("T_total")
        if isinstance(observables, Mapping)
        else None,
        "A": observables.get("A_balance")
        if isinstance(observables, Mapping)
        else None,
        "A_volume": observables.get("A_volume")
        if isinstance(observables, Mapping)
        else None,
    }
    rta_pass = bool(
        all(
            isinstance(value, (int, float, np.integer, np.floating))
            and np.isfinite(float(value))
            for value in rta_values.values()
        )
    )
    gates = {
        "five_true_residuals": residuals,
        "five_true_residuals_pass": residual_pass,
        "ksp_reason": reason,
        "ksp_reason_pass": reason > 0,
        "recovery_pass": recovery_pass,
        "recovery_physics_pass": recovery_physics_pass,
        "recovery_contract_pass": recovery_contract_pass,
        "external_q_residuals": external_q_residuals,
        "external_q_pass": external_q_pass,
        "interface_projection": authority.get("interface_projection"),
        "interface_projection_pass": projection_pass,
        "traction_pass": traction_pass,
        "closure": authority.get("closure"),
        "closure_pass": closure_pass,
        "A_balance": observables.get("A_balance")
        if isinstance(observables, Mapping)
        else None,
        "A_volume": observables.get("A_volume")
        if isinstance(observables, Mapping)
        else None,
        "A_balance_minus_A_volume_pass": balance_pass,
        "grid_E_H_evidence_pass": grid_eh_pass,
        "external_diffraction_channels_pass": external_channels_pass,
        "authority_identity": authority_identity,
        "authority_external_keys": authority_external_keys,
        "identity_external_keys": identity_external_keys,
        "external_key_binding_pass": external_key_binding_pass,
        "external_orders_key_binding_pass": external_orders_key_binding_pass,
        "canonical_authority_present": canonical_present,
        "official_rta": {
            "status": "measured" if rta_pass else "not_available",
            **rta_values,
        },
        "integrated_checker": formal_result.get("recovery", {}).get(
            "integrated_checker", "not_used"
        ),
    }
    gates["pass"] = bool(
        residual_pass
        and reason > 0
        and recovery_pass
        and recovery_physics_pass
        and recovery_contract_pass
        and external_q_pass
        and projection_pass
        and traction_pass
        and closure_pass
        and grid_eh_pass
        and external_channels_pass
        and authority_identity["pass"]
        and external_key_binding_pass
        and external_orders_key_binding_pass
        and balance_pass
        and canonical_present
        and rta_pass
    )
    return gates


def run_task041_consumer(
    *,
    input_path: str | Path,
    packet_manifest: str | Path,
    packet_identity: str | Path,
    packet_manifest_sha256: str,
    run_directory: str | Path,
    source_sha: str,
    comm: Any = MPI.COMM_WORLD,
) -> dict[str, Any]:
    """Consume one fresh Task041 packet through the reviewed exact-side path."""

    if comm.size != 1:
        raise Task041ModePrepError("Task041 consumer requires MPI.COMM_WORLD size 1")
    if not _valid_sha(source_sha, 40):
        raise Task041ModePrepError("source_sha must be a lowercase 40-character SHA")
    if not _valid_sha(packet_manifest_sha256, 64):
        raise Task041ModePrepError("packet manifest SHA must be a lowercase SHA256")
    root = Path(run_directory).resolve()
    if root.exists():
        raise FileExistsError(f"Task041 run directory already exists: {root}")
    root.mkdir(parents=True)
    started = time.monotonic()
    result: dict[str, Any] = {
        "schema": TASK041_CONSUMER_SCHEMA,
        "profile": TASK041_CONSUMER_PROFILE,
        "phase": TASK041_CONSUMER_PHASE,
        "input": str(Path(input_path).resolve()),
        "run_directory": str(root),
        "source_sha": source_sha,
        "status": "IMPLEMENTATION_FAILURE",
        "classification": "IMPLEMENTATION_FAILURE",
        "official_rta": {"status": "not_run"},
        "limits": {
            "warning_memory_bytes": TASK041_WARNING_MEMORY_BYTES,
            "hard_memory_bytes": TASK041_HARD_MEMORY_BYTES,
            "min_memavailable_bytes": TASK041_MIN_MEMAVAILABLE_BYTES,
            "timeout_seconds": TASK041_TIMEOUT_SECONDS,
        },
        "consumer_scope": {
            "local_systems": "not_run",
            "coupling": "not_run",
            "factor": "not_run",
            "solve": "not_run",
            "recovery": "not_run",
        },
        "not_used": {
            "v6_profile": False,
            "exact_spool_root": False,
            "old_mpi8_packet_loader": False,
            "task040_pc": False,
            "direct_fallback": False,
            "integrated_checker": False,
        },
        "fallback_counts": {
            "qep": 0,
            "factor": 0,
            "global_direct": 0,
            "global_coarse": 0,
            "recovery": 0,
        },
    }
    environment: dict[str, Any] = {}
    marker_records: list[dict[str, Any]] = []
    factor_events: dict[str, list[dict[str, Any]]] = {"bottom": [], "top": []}
    setup = None
    cleanup_release: dict[str, Any] = {"status": "not_run"}
    release_audit: dict[str, Any] = {}
    error: BaseException | None = None
    current_stage = "consumer_preflight"
    recovery_markers_started = False

    def emit(stage: str, detail: Mapping[str, Any] | None = None) -> None:
        marker = _write_marker(
            root,
            started,
            stage,
            environment=environment,
            detail={} if detail is None else detail,
            comm=comm,
            schema=TASK041_CONSUMER_SCHEMA,
            marker_sequence=TASK041_CONSUMER_MARKER_SEQUENCE,
        )
        marker_records.append(marker)

    def callback(stage: str, detail: Mapping[str, Any]) -> None:
        nonlocal current_stage, recovery_markers_started
        current_stage = stage
        if stage == "recovery_physics_begin":
            recovery_markers_started = True
        if stage in {"bottom_factor_ready", "top_factor_ready"}:
            side = stage.split("_", 1)[0]
            factor_events[side].append(dict(detail))
        if stage in TASK041_CONSUMER_MARKER_SEQUENCE:
            emit(stage, detail)
        elif recovery_markers_started:
            emit("recovery_stage", {"name": stage, "detail": detail})
        else:
            emit("system_setup_stage", {"name": stage, "detail": detail})
        if stage == "outer_solve_begin":
            emit("solve_started", {"source": "Task041 outer solve"})
        elif stage == "solution_snapshot_created":
            emit("solution_snapshot", {"source": "retained outer solution"})
        elif stage == "outer_solve_ready":
            solve_report = detail.get("solve_report", detail)
            emit("solve_complete", {"solve": solve_report})
            emit("true_residual_complete", {"solve": solve_report})
            snapshot_path = root / "minimal_recovery_packet.json"
            _write_json(
                snapshot_path,
                {
                    "schema": "task041.exact_side.minimal_recovery_packet.v1",
                    "status": "manifest_only",
                    "source": "retained_solution_snapshot",
                    "snapshot_location": "process_memory",
                    "snapshot_lifetime": "until_recovery_consumes_it",
                    "consumed_by": "run_v3_7_recovery_runner",
                    "json_contains_solution": False,
                    "solve_report_status": solve_report.get("status"),
                },
            )
            emit(
                "minimal_recovery_packet_saved",
                {
                    "path": str(snapshot_path),
                    "kind": "manifest_only",
                    "snapshot_location": "process_memory",
                    "consumed_by": "run_v3_7_recovery_runner",
                    "json_contains_solution": False,
                },
            )
        elif stage == "outer_solve_objects_cleanup":
            pending_release = release_audit.get("release")
            if isinstance(pending_release, Mapping):
                emit("rss_drop_confirmed", pending_release["rss_drop"])
                release_audit["rss_marker_emitted"] = True
        elif stage == "recovery_physics_begin":
            emit("recovery_started", {"source": "run_v3_7_recovery_runner"})
        elif stage == "recovery_physics_end":
            emit("recovery_complete", {"source": "run_v3_7_recovery_runner"})

    try:
        environment = _environment_snapshot()
        result["environment"] = environment
        emit("preflight_begin", {"mpi_size": comm.size})
        available = _memavailable_bytes()
        if available < TASK041_MIN_MEMAVAILABLE_BYTES:
            raise Task041ModePrepError("MemAvailable is below the Task041 preflight floor")
        result["memavailable_bytes"] = available
        specification = load_and_resolve(input_path)
        normalized = specification.as_jsonable()
        profile_failures = tuple(task041_profile_errors(normalized))
        if profile_failures:
            raise Task041ModePrepError(
                "Task041 profile rejected: "
                + "; ".join(f"{field}: {message}" for field, message in profile_failures)
            )
        resolved_sha = resolved_config_sha256(specification)
        identity_path = Path(packet_identity).resolve()
        manifest_path = Path(packet_manifest).resolve()
        disk_identity = json.loads(identity_path.read_text(encoding="utf-8"))
        if not isinstance(disk_identity, Mapping):
            raise Task041ModePrepError("Task041 packet identity is not a mapping")
        recomputed_identity = build_task041_packet_identity(
            specification, normalized, source_sha, resolved_sha
        )
        if dict(disk_identity) != recomputed_identity:
            raise Task041ModePrepError("Task041 consumer packet identity recomputation mismatch")
        if recomputed_identity["mode_count"] != 480 or recomputed_identity["mpi_size"] != 1:
            raise Task041ModePrepError("Task041 consumer accepts only M480/MPI1")
        emit("input_validated", {"identity": recomputed_identity})
        emit("packet_identity_validated", {"path": str(identity_path)})
        sampled_contract = _task041_consumer_sampled_column_contract(
            recomputed_identity, manifest_path, packet_manifest_sha256
        )
        emit(
            "packet_manifest_validated",
            {
                "manifest": str(manifest_path),
                "manifest_sha256": packet_manifest_sha256,
                "sampled_column_contract_sha256": sampled_contract["sha256"],
            },
        )
        cfg = simulation_config_3d_from_normalized(normalized)
        modal_cfg = deepcopy(cfg)
        profile = _task041_consumer_profile()
        iterative_config = task041_consumer_iterative_config()
        producer = {
            "producer_source_sha": source_sha,
            "consumer_source_sha": source_sha,
            "physical_model_sha256": str(specification.physical_model_sha256),
            "consumer_model_id": recomputed_identity["model_id"],
            "requested_modes": 480,
            "mpi_size": 1,
            "task041_scope": recomputed_identity["scope"],
            "qualification_scope": "task041_5nm_p6h4_m480_mpi1",
            "qualification_method": "task041_exact_side_full_formal",
            "canonical_authority": True,
        }
        result["identity"] = recomputed_identity
        result["profile_config"] = _jsonable(asdict(profile))
        result["outer_config"] = _jsonable(asdict(iterative_config))
        result["packet"] = {
            "manifest": str(manifest_path),
            "manifest_sha256": packet_manifest_sha256,
            "identity": str(identity_path),
            "sampled_column_contract": sampled_contract,
        }

        from benchmarks.run_task037b_hybrid_iterative import build_frozen_m10_setup
        from benchmarks.task039_v3_7_orchestration import (
            _run_v7_h4_exact_side_full_formal,
            run_v3_7_recovery_runner,
            run_v5_h4_exact_side_setup_only,
        )

        current_stage = "system_setup"
        setup = build_frozen_m10_setup(
            comm=comm,
            log=None,
            profile=profile,
            cfg_override=cfg,
            modal_cfg_override=modal_cfg,
            exact_one_cell_work_dir=root / "numerical_output" / "exact_one_cell",
            detail_stage_callback=callback,
            selected_mode_packet_manifest=manifest_path,
            selected_mode_packet_identity=recomputed_identity,
            selected_mode_packet_manifest_sha256=packet_manifest_sha256,
        )
        qep_release = dict(setup.qep_release)
        if qep_release.get("qep_calls") != 0 or qep_release.get(
            "consumer_qep_required"
        ) is not False:
            raise Task041ModePrepError("Task041 consumer packet path crossed the QEP boundary")
        emit(
            "system_ready",
            {
                "qep_release": qep_release,
                "exact_one_cell_work_dir": str(
                    root / "numerical_output" / "exact_one_cell"
                ),
                "task040_pc": False,
            },
        )
        layout = __import__(
            "src.solvers.hybrid_fem_modal_augmented_direct",
            fromlist=["HybridAugmentedLayout"],
        ).HybridAugmentedLayout.build(
            setup.bottom,
            setup.top,
            setup.coupling.internal_unknown_count,
        )

        def recovery_runner(
            recovery_setup: Any,
            recovery_layout: Any,
            snapshot: Any,
            recovery_directory: Path,
            recovery_producer: Mapping[str, Any],
        ) -> Mapping[str, Any]:
            nonlocal current_stage
            current_stage = "recovery_physics"
            return run_v3_7_recovery_runner(
                recovery_setup,
                recovery_layout,
                snapshot,
                recovery_directory,
                recovery_producer,
                run_integrated_checker=False,
            )

        def full_formal_runner(**kwargs: Any) -> Mapping[str, Any]:
            base_release = kwargs.pop("release_before_recovery")

            def release_before_recovery() -> Mapping[str, Any]:
                nonlocal current_stage
                current_stage = "outer_solve_objects_cleanup"
                release = dict(base_release())
                before_rss_values = [
                    _process_tree_rss(marker.get("resource", {}))
                    for marker in marker_records
                    if _process_tree_rss(marker.get("resource", {})) is not None
                ]
                before_memory_values = [
                    _memory_authority(marker.get("resource", {}))
                    for marker in marker_records
                    if _memory_authority(marker.get("resource", {})) is not None
                ]
                after_sample = _resource_snapshot()
                _check_resource(after_sample, started)
                after_rss = _process_tree_rss(after_sample)
                after_memory_authority = _memory_authority(after_sample)
                before_rss = max(before_rss_values, default=None)
                before_memory_authority = max(before_memory_values, default=None)
                if before_rss is None or after_rss is None:
                    drop_pass = False
                else:
                    drop_pass = bool(after_rss < before_rss)
                release["rss_drop"] = {
                    "rss_measurement": "process_tree.rss_bytes",
                    "before_high_water_rss_bytes": before_rss,
                    "after_cleanup_rss_bytes": after_rss,
                    "before_high_water_memory_authority_bytes": before_memory_authority,
                    "after_cleanup_memory_authority_bytes": after_memory_authority,
                    "pass": drop_pass,
                }
                release_audit["release"] = release
                emit(
                    "outer_ksp_destroyed",
                    {"destroyed": True, "source": "iterative.release"},
                )
                emit(
                    "bottom_top_factors_destroyed",
                    {
                        "factor_count_after_cleanup": release.get(
                            "factor_count_after_cleanup"
                        ),
                        "pass": release.get("factor_cleanup_pass"),
                    },
                )
                emit(
                    "large_matrices_destroyed",
                    {"pass": release.get("component_cleanup_pass")},
                )
                return release

            return _run_v7_h4_exact_side_full_formal(
                recovery_runner=recovery_runner,
                producer={**producer, "_stage_callback": callback},
                run_directory=root,
                iterative_config=iterative_config,
                release_before_recovery=release_before_recovery,
                **kwargs,
            )

        current_stage = "factor_setup"
        setup_result = run_v5_h4_exact_side_setup_only(
            setup,
            layout,
            comm=comm,
            marker_callback=callback,
            qualification_scope="task039_v4_p6h4_m480_1deg_s",
            sampled_column_contract=sampled_contract,
            v6_profile=False,
            exact_spool_root=None,
            packet_identity=recomputed_identity,
            packet_manifest_sha256=packet_manifest_sha256,
            full_formal_runner=full_formal_runner,
            outer_probe_config=iterative_config,
        )
        formal_result = setup_result.get("full_formal")
        if not isinstance(formal_result, Mapping):
            raise Task041ModePrepError("Task041 consumer did not return full-formal result")
        formal_solve = formal_result.get("solve")
        formal_recovery = formal_result.get("recovery")
        formal_numerical_failure = bool(
            isinstance(formal_solve, Mapping) and formal_solve.get("pass") is False
        ) or bool(
            isinstance(formal_recovery, Mapping)
            and formal_recovery.get("pass") is False
        )
        formal_lifecycle_failure = (
            formal_result.get("status") == "full_formal_lifecycle_failure"
        )
        formal_short_circuit = formal_numerical_failure or formal_lifecycle_failure
        authority_value = formal_result.get("authority_path")
        authority_path = (
            Path(authority_value).resolve()
            if authority_value
            else None
        )
        if formal_short_circuit:
            gates = {
                "pass": False,
                "status": (
                    "not_run_due_to_formal_numerical_failure"
                    if formal_numerical_failure
                    else "not_run_due_to_formal_lifecycle_failure"
                ),
                "authority_available": authority_path is not None
                and authority_path.is_file(),
            }
        else:
            if authority_path is None:
                raise Task041ModePrepError("Task041 consumer authority path is missing")
            current_stage = "authority_validation"
            gates = _task041_consumer_authority_gate(
                authority_path, formal_result, recomputed_identity
            )
            emit("authority_validated", {"gates": gates, "path": str(authority_path)})
        result["setup"] = _jsonable(setup_result)
        result["formal"] = _jsonable(formal_result)
        result["gates"] = gates
        if authority_path is not None:
            result["authority_path"] = str(authority_path)
        result["consumer_scope"] = {
            "local_systems": "created_and_released",
            "coupling": "created_and_released",
            "factor": "local_exact_side_only",
            "solve": "right_fgmres",
            "recovery": "run_v3_7_recovery_runner",
        }
        result["matrix_inventory"] = {
            "qep_calls": qep_release["qep_calls"],
            "consumer_qep_required": qep_release["consumer_qep_required"],
            "global_direct_factor_count": 0,
            "global_coarse_factor_count": 0,
            "task040_pc": False,
            "direct_fallback": False,
            "old_mpi8_packet_loader": False,
        }
        if gates["pass"] is not True:
            if formal_numerical_failure:
                result["status"] = str(
                    formal_result.get("status", "full_formal_numerical_failure")
                )
                result["classification"] = "TASK041_CONSUMER_NUMERICAL_FAILURE"
            elif formal_lifecycle_failure:
                result["status"] = str(formal_result["status"])
                result["classification"] = "TASK041_CONSUMER_LIFECYCLE_FAILURE"
            else:
                result["status"] = "task041_consumer_formal_failure"
                result["classification"] = "TASK041_CONSUMER_GATE_FAILURE"
        else:
            result["status"] = "task041_consumer_completed"
            result["classification"] = "TASK041_CONSUMER_PASS"
        if formal_short_circuit:
            result["official_rta"] = {
                "status": "not_available_due_to_formal_failure"
            }
        else:
            result["official_rta"] = dict(gates["official_rta"])
            if gates["pass"] is not True and result["official_rta"]["status"] == "measured":
                result["official_rta"]["status"] = "measured_candidate"
        emit(
            "official_outputs_written",
            {"status": result["status"], "official_rta": result["official_rta"]},
        )
    except Exception as exc:  # noqa: BLE001 - preserve worker failure evidence
        error = exc
        result["status"] = "IMPLEMENTATION_FAILURE"
        result["classification"] = (
            "TASK041_CONSUMER_STAGE_FAILURE"
            if current_stage
            in {
                "system_setup",
                "factor_setup",
                "recovery_physics",
                "outer_solve_objects_cleanup",
            }
            else "IMPLEMENTATION_FAILURE"
        )
        result["failure_stage"] = current_stage
        result["error"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "stage": current_stage,
        }
    finally:
        current_stage = "final_cleanup"
        try:
            from benchmarks.run_task037b_hybrid_iterative import (
                release_frozen_m10_objects,
            )

            cleanup_release = release_frozen_m10_objects(setup, None, comm)
        except Exception as cleanup_error:  # noqa: BLE001 - retain cleanup attempt
            cleanup_release = {
                "pass": False,
                "error": {
                    "type": type(cleanup_error).__name__,
                    "message": str(cleanup_error),
                },
            }
            if error is None:
                error = cleanup_error
                result["status"] = "IMPLEMENTATION_FAILURE"
                result["classification"] = "TASK041_CONSUMER_LIFECYCLE_FAILURE"
                result["failure_stage"] = current_stage
                result["error"] = {
                    "type": type(cleanup_error).__name__,
                    "message": str(cleanup_error),
                    "stage": current_stage,
                }
        result["lifecycle"] = {
            "setup_created": setup is not None,
            "setup_released": bool(cleanup_release.get("pass") is True),
            "packet_setup_release": cleanup_release,
            "outer_release": release_audit.get("release", {"status": "not_run"}),
            "rss_drop_pass": bool(
                release_audit.get("release", {})
                .get("rss_drop", {})
                .get("pass")
                is True
            ),
            "rss_marker_emitted": bool(release_audit.get("rss_marker_emitted")),
            "qep_calls": result.get("matrix_inventory", {}).get("qep_calls", 0),
            "factor_count_after_cleanup": result.get("formal", {})
            .get("release_before_recovery", {})
            .get("factor_count_after_cleanup"),
        }
        result["cleanup"] = cleanup_release
        result["factor_inventory"] = {
            "schema": "task041.exact_side.factor_inventory.v1",
            "source": "consumer factor_ready marker INFOG/RINFOG/Mat diagnostics",
            "bottom": factor_events["bottom"],
            "top": factor_events["top"],
            "not_used": {
                "global_direct": 0,
                "global_coarse": 0,
                "ooc": 0,
            },
        }
        try:
            emit(
                "all_setup_objects_cleanup",
                {"cleanup": cleanup_release},
            )
            emit(
                "final_cleanup_complete",
                {
                    "status": result["status"],
                    "classification": result["classification"],
                    "cleanup": cleanup_release,
                },
            )
        except Exception as cleanup_marker_error:  # noqa: BLE001 - preserve evidence
            if error is None:
                error = cleanup_marker_error
                result["status"] = "IMPLEMENTATION_FAILURE"
                result["classification"] = "TASK041_CONSUMER_LIFECYCLE_FAILURE"
                result["failure_stage"] = current_stage
                result["error"] = {
                    "type": type(cleanup_marker_error).__name__,
                    "message": str(cleanup_marker_error),
                    "stage": current_stage,
                }
        result["wall_seconds"] = time.monotonic() - started
        result["markers"] = {
            "sequence": list(TASK041_CONSUMER_MARKER_SEQUENCE),
            "observed": [marker["stage"] for marker in marker_records],
            "count": len(marker_records),
        }
        _write_json(root / "factor_inventory.json", result["factor_inventory"])
        _write_json(root / "consumer_summary.json", result)
    if error is not None:
        raise error
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", required=True)
    parser.add_argument(
        "--phase",
        choices=(TASK041_MODE_PREP_PHASE, TASK041_CONSUMER_PHASE),
        required=True,
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--packet-manifest")
    parser.add_argument("--packet-identity")
    parser.add_argument("--packet-manifest-sha256")
    return parser


def main(argv: Sequence[str] | None = None) -> dict[str, Any]:
    args = _parser().parse_args(argv)
    if not args.worker:
        raise Task041ModePrepError("Task041 requires a private worker")
    if args.phase == TASK041_MODE_PREP_PHASE:
        return run_task041_mode_prep(
            input_path=args.input,
            run_directory=args.run_directory,
            source_sha=args.source_sha,
        )
    if not all(
        value is not None
        for value in (
            args.packet_manifest,
            args.packet_identity,
            args.packet_manifest_sha256,
        )
    ):
        raise Task041ModePrepError("Task041 consumer requires packet identity and manifest")
    return run_task041_consumer(
        input_path=args.input,
        packet_manifest=args.packet_manifest,
        packet_identity=args.packet_identity,
        packet_manifest_sha256=args.packet_manifest_sha256,
        run_directory=args.run_directory,
        source_sha=args.source_sha,
    )


if __name__ == "__main__":
    main()
