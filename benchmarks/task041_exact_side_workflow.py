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
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.task034_wsl_resources import resource_authority_sample
from benchmarks.task039_v4_selected_mode_packet import (
    TASK041_SELECTED_MODE_IDENTITY_SCHEMA,
    task041_selected_mode_scope,
)
from src.io.input_validation import (
    load_and_resolve,
    simulation_config_3d_from_normalized,
    task041_profile_errors,
)
from src.io.resolved_config import resolved_config_sha256
from src.solvers.hybrid_interface_basis import canonical_mode_keys_sha256

TASK041_MODE_PREP_SCHEMA = "task041.exact_side.mode_prep.v1"
TASK041_MODE_PREP_PROFILE = "task041_5nm_exact_side_hybrid_iterative"
TASK041_MODE_PREP_PHASE = "mode-prep"
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
    external_key_sha = canonical_mode_keys_sha256(keys)
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


def _resource_value(sample: Any, key: str) -> int | None:
    if isinstance(sample, Mapping):
        if key in sample and isinstance(sample[key], (int, float, np.integer)):
            return int(sample[key])
        for value in sample.values():
            found = _resource_value(value, key)
            if found is not None:
                return found
    if isinstance(sample, Sequence) and not isinstance(sample, (str, bytes)):
        for value in sample:
            found = _resource_value(value, key)
            if found is not None:
                return found
    return None


def _resource_snapshot() -> dict[str, Any]:
    return _jsonable(resource_authority_sample(os.getpid()))


def _memavailable_bytes() -> int:
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) * 1024
    raise Task041ModePrepError("/proc/meminfo has no MemAvailable")


def _check_resource(sample: Mapping[str, Any], started: float) -> None:
    rss = _resource_value(sample, "rss_bytes")
    swap = _resource_value(sample, "swap_bytes")
    if rss is not None and rss >= TASK041_HARD_MEMORY_BYTES:
        raise Task041ModePrepError("Task041 hard RSS limit reached")
    if swap is not None and swap != 0:
        raise Task041ModePrepError("Task041 swap limit reached")
    if time.monotonic() - started >= TASK041_TIMEOUT_SECONDS:
        raise Task041ModePrepError("Task041 mode-prep timeout reached")


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
) -> dict[str, Any]:
    resource = _resource_snapshot()
    _check_resource(resource, started)
    marker = {
        "schema": TASK041_MODE_PREP_SCHEMA,
        "stage": stage,
        "sequence_index": TASK041_MARKER_SEQUENCE.index(stage),
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
) -> list[str]:
    return [
        "--output",
        str(output_path),
        "--h-nm",
        "4",
        "--degree",
        "6",
        "--modal-h-nm",
        "4",
        "--modal-degree",
        "6",
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", action="store_true", required=True)
    parser.add_argument("--phase", choices=(TASK041_MODE_PREP_PHASE,), required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--run-directory", required=True)
    parser.add_argument("--source-sha", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> dict[str, Any]:
    args = _parser().parse_args(argv)
    if not args.worker or args.phase != TASK041_MODE_PREP_PHASE:
        raise Task041ModePrepError("Task041 requires the private mode-prep worker")
    return run_task041_mode_prep(
        input_path=args.input,
        run_directory=args.run_directory,
        source_sha=args.source_sha,
    )


if __name__ == "__main__":
    main()
