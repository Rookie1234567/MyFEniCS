"""Task44-only evidence snapshot taken before the full residual UFL action."""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

GIB = 1024**3
MIB = 1024**2
MAX_SNAPSHOT_PEAK_DELTA_BYTES = 32 * MIB
SNAPSHOT_SCHEMA = "task44.pre-full-operator-residual-diagnostic.v1"


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _sha256_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _array_identity(value: Any) -> dict[str, Any]:
    array_value = getattr(value, "array", None)
    if array_value is not None:
        value = array_value() if callable(array_value) else array_value
    array = np.asarray(value)
    digest = hashlib.sha256()
    if array.flags.c_contiguous:
        digest.update(memoryview(array).cast("B"))
    else:
        for chunk in np.nditer(
            array,
            flags=["external_loop", "buffered", "zerosize_ok"],
            op_flags=["readonly"],
            order="C",
            buffersize=65536,
        ):
            digest.update(memoryview(np.asarray(chunk)).cast("B"))
    return {
        "shape": list(array.shape),
        "dtype": str(array.dtype),
        "bytes": int(array.nbytes),
        "sha256": digest.hexdigest(),
    }


def _complex_pair(value: complex) -> list[float]:
    value = complex(value)
    return [float(value.real), float(value.imag)]


def _file_identity(run_root: Path, name: str) -> dict[str, Any]:
    path = run_root / name
    if not path.is_file():
        raise FileNotFoundError(f"Task44 residual snapshot identity file is missing: {path}")
    digest, size = _sha256_file(path)
    result: dict[str, Any] = {"path": str(path), "bytes": size, "sha256": digest}
    if name.endswith(".txt"):
        result["value"] = path.read_text(encoding="utf-8").strip()
    return result


def _mesh_array_identity(mesh_data: Any) -> dict[str, Any]:
    mesh = mesh_data.mesh
    geometry = mesh.geometry
    arrays: dict[str, Any] = {
        "geometry_coordinates": geometry.x,
        "geometry_dofmap": geometry.dofmap,
        "cell_tag_indices": mesh_data.cell_tags.indices,
        "cell_tag_values": mesh_data.cell_tags.values,
        "facet_tag_indices": mesh_data.facet_tags.indices,
        "facet_tag_values": mesh_data.facet_tags.values,
    }
    inventory = {name: _array_identity(value) for name, value in arrays.items()}
    inventory["mesh_cell_type_resolved"] = str(mesh_data.mesh_cell_type_resolved)
    inventory["mesh_cells_resolved"] = [int(value) for value in mesh_data.mesh_cells_resolved]
    inventory["mesh_identity_sha256"] = hashlib.sha256(_canonical_json(inventory)).hexdigest()
    return inventory


def _mode_identity(modes: Sequence[Any], cfg: Any) -> list[dict[str, Any]]:
    result = []
    for mode in modes:
        boundary_z = float(
            cfg.physical_z_max if mode.side == "top" else cfg.physical_z_min
        )
        phase_exponent = 1j * complex(mode.k_vector[2]) * boundary_z
        phase_log_magnitude = float(phase_exponent.real)
        phase_argument = float(phase_exponent.imag)
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            boundary_phase = complex(np.exp(phase_exponent))
        if not math.isfinite(phase_log_magnitude) or not math.isfinite(phase_argument):
            phase_status = "nonfinite_exponent"
            boundary_phase_pair = None
        elif not all(math.isfinite(value) for value in (boundary_phase.real, boundary_phase.imag)):
            phase_status = "outside_binary64_range"
            boundary_phase_pair = None
        elif boundary_phase == 0j:
            phase_status = "underflowed_to_zero"
            boundary_phase_pair = [0.0, 0.0]
        else:
            phase_status = "representable"
            boundary_phase_pair = _complex_pair(boundary_phase)
        result.append(
            {
                "key": [str(mode.side), int(mode.m), int(mode.n), str(mode.polarization)],
                "alpha": _complex_pair(mode.alpha),
                "gamma": _complex_pair(mode.gamma),
                "beta": _complex_pair(mode.beta),
                "k_vector": [_complex_pair(value) for value in mode.k_vector],
                "boundary_reference_z_nm": boundary_z,
                "global_z_phase_exponent_real": phase_log_magnitude,
                "global_z_phase_exponent_imag": phase_argument,
                "global_z_phase_log_magnitude": phase_log_magnitude,
                "global_z_boundary_phase": boundary_phase_pair,
                "global_z_boundary_phase_status": phase_status,
                "boundary_plane_phase": [1.0, 0.0],
                "propagating": bool(mode.propagating),
            }
        )
    return result


def _dof_identity(function_space: Any, reduced_solution: Any, condensed: Any) -> dict[str, Any]:
    dofmap = function_space.dofmap
    index_map = dofmap.index_map
    block_size = int(dofmap.index_map_bs)
    cell_digest = hashlib.sha256()
    cell_count = int(function_space.mesh.topology.index_map(
        function_space.mesh.topology.dim
    ).size_local)
    for cell in range(cell_count):
        cell_dofs = np.asarray(dofmap.cell_dofs(cell))
        cell_digest.update(
            _canonical_json({"cell": cell, **_array_identity(cell_dofs)})
        )
    return {
        "fe_dofs_global": int(index_map.size_global * block_size),
        "fe_dofs_local_owned": int(index_map.size_local * block_size),
        "fe_dofs_ghost": int(index_map.num_ghosts * block_size),
        "fe_dof_block_size": block_size,
        "local_cell_count": cell_count,
        "cell_dofmap_sha256": cell_digest.hexdigest(),
        "reduced_rows_global": int(reduced_solution.getSize()),
        "reduced_ownership_range": [int(value) for value in reduced_solution.getOwnershipRange()],
        "condensed_full_rows": int(condensed.full_rows),
        "condensed_trace_rows": int(condensed.trace_rows),
        "condensed_active_rows": int(condensed.active_rows),
        "condensed_appended_rows": int(condensed.appended_rows),
        "condensed_interior_rows": int(condensed.interior_rows),
        "condensed_active_interior_rows": int(condensed.active_interior_rows),
    }


def _read_task44_whole_job_memory_authority() -> dict[str, Any]:
    """Read the existing job cgroup and shared host/ancestor memory envelope."""
    from benchmarks.subreaper_watchdog import (
        PHYSICAL_MEMORY_PRESSURE_POLICY,
        memory_envelope,
    )
    from benchmarks.task034_wsl_resources import cgroup_snapshot
    from scripts.task44_native_service import HOST_RESERVE_BYTES, JOB_BUFFER_BYTES

    job = cgroup_snapshot(os.getpid())
    required_job_ints = (
        "memory_current_bytes",
        "memory_limit_bytes",
        "swap_current_bytes",
    )
    if (
        job.get("dedicated_job_cgroup") is not True
        or job.get("readable") is not True
        or any(type(job.get(key)) is not int for key in required_job_ints)
    ):
        raise RuntimeError("Task44 whole-job cgroup memory authority is unreadable")
    job_current = int(job["memory_current_bytes"])
    job_cap = int(job["memory_limit_bytes"])
    job_swap = int(job["swap_current_bytes"])
    if job_cap <= 0 or job_current < 0 or job_current > job_cap or job_swap != 0:
        raise RuntimeError("Task44 whole-job cgroup memory authority is invalid")

    task_buffer = max(JOB_BUFFER_BYTES, int(job_cap * 0.05))
    envelope = memory_envelope(
        PHYSICAL_MEMORY_PRESSURE_POLICY,
        host_reserve_bytes=HOST_RESERVE_BYTES,
        task_cgroup_reserve_bytes=task_buffer,
        require_cgroup_memory_details=True,
    )
    envelope_ints = (
        "host_mem_available_bytes",
        "reserve_bytes",
        "task_cgroup_available_bytes",
        "task_cgroup_reserve_bytes",
        "launch_cap_bytes",
    )
    if any(type(envelope.get(key)) is not int for key in envelope_ints):
        raise RuntimeError("Task44 host/ancestor memory authority is incomplete")
    cgroup_limits = envelope.get("cgroup_limits")
    if not isinstance(cgroup_limits, list) or not cgroup_limits:
        raise RuntimeError("Task44 finite cgroup ancestor inventory is unavailable")
    return {
        "status": "readable",
        "scope": "current dedicated Task44 service cgroup",
        "cgroup_path": job.get("path"),
        "whole_job_current_bytes": job_current,
        "whole_job_cap_bytes": job_cap,
        "whole_job_swap_current_bytes": job_swap,
        "warning_threshold_bytes": int(job_cap * 0.90),
        "controlled_stop_threshold_bytes": int(job_cap * 0.95),
        "host_mem_available_bytes": int(envelope["host_mem_available_bytes"]),
        "host_reserve_bytes": int(envelope["reserve_bytes"]),
        "host_headroom_after_reserve_bytes": int(
            envelope["host_mem_available_bytes"] - HOST_RESERVE_BYTES
        ),
        "task_cgroup_available_bytes": int(
            envelope["task_cgroup_available_bytes"]
        ),
        "task_cgroup_buffer_bytes": int(envelope["task_cgroup_reserve_bytes"]),
        "ancestor_headroom_after_buffer_bytes": int(
            envelope["task_cgroup_available_bytes"]
            - envelope["task_cgroup_reserve_bytes"]
        ),
        "host_and_ancestor_headroom_after_reserves_bytes": int(
            envelope["launch_cap_bytes"]
        ),
        "host_reserve_required_bytes": int(HOST_RESERVE_BYTES),
        "task_buffer_required_bytes": int(task_buffer),
        "cgroup_limits": cgroup_limits,
        "memory_policy": PHYSICAL_MEMORY_PRESSURE_POLICY,
    }


def _validate_snapshot_memory_gate(
    predicted_peak_delta_bytes: int,
    authority: Mapping[str, Any],
) -> dict[str, Any]:
    if authority.get("status") != "readable":
        raise RuntimeError("Task44 whole-job memory authority did not pass")
    required_ints = (
        "whole_job_current_bytes",
        "whole_job_cap_bytes",
        "warning_threshold_bytes",
        "controlled_stop_threshold_bytes",
        "host_headroom_after_reserve_bytes",
        "ancestor_headroom_after_buffer_bytes",
        "host_and_ancestor_headroom_after_reserves_bytes",
        "host_reserve_required_bytes",
        "task_buffer_required_bytes",
    )
    if any(type(authority.get(key)) is not int for key in required_ints):
        raise RuntimeError("Task44 whole-job memory authority fields are incomplete")
    if type(authority.get("whole_job_swap_current_bytes")) is not int or authority.get(
        "whole_job_swap_current_bytes"
    ) != 0:
        raise RuntimeError("Task44 whole-job swap authority is nonzero or unavailable")
    if int(authority["host_reserve_required_bytes"]) < 384 * GIB:
        raise RuntimeError("Task44 host reserve is below the established 384 GiB reserve")
    if int(authority["task_buffer_required_bytes"]) < 8 * GIB:
        raise RuntimeError("Task44 cgroup buffer is below the established 8 GiB buffer")
    if predicted_peak_delta_bytes < 0:
        raise ValueError("Task44 snapshot peak delta must be nonnegative")
    if predicted_peak_delta_bytes > MAX_SNAPSHOT_PEAK_DELTA_BYTES:
        raise MemoryError(
            "Task44 diagnostic snapshot predicted peak delta exceeds the 32 MiB allowance"
        )

    job_current = int(authority["whole_job_current_bytes"])
    job_cap = int(authority["whole_job_cap_bytes"])
    warning = int(authority["warning_threshold_bytes"])
    controlled_stop = int(authority["controlled_stop_threshold_bytes"])
    projected_job_peak = job_current + int(predicted_peak_delta_bytes)
    if (
        job_cap <= 0
        or job_current < 0
        or job_current > job_cap
        or warning != int(job_cap * 0.90)
        or controlled_stop != int(job_cap * 0.95)
        or warning <= 0
        or controlled_stop <= warning
        or controlled_stop > job_cap
        or int(authority["task_buffer_required_bytes"])
        < max(8 * GIB, int(job_cap * 0.05))
    ):
        raise RuntimeError("Task44 whole-job warning/stop/cap thresholds are invalid")
    if projected_job_peak > warning:
        raise MemoryError(
            "Task44 diagnostic snapshot would cross the whole-job warning threshold"
        )
    if projected_job_peak > controlled_stop:
        raise MemoryError(
            "Task44 diagnostic snapshot would cross the whole-job controlled-stop threshold"
        )
    if projected_job_peak > job_cap:
        raise MemoryError("Task44 diagnostic snapshot would cross the whole-job cap")
    reserve_headrooms = (
        int(authority["host_headroom_after_reserve_bytes"]),
        int(authority["ancestor_headroom_after_buffer_bytes"]),
        int(authority["host_and_ancestor_headroom_after_reserves_bytes"]),
    )
    if any(headroom < int(predicted_peak_delta_bytes) for headroom in reserve_headrooms):
        raise MemoryError(
            "Task44 diagnostic snapshot would cross host reserve or ancestor cgroup buffer"
        )
    return {
        "status": "pass",
        "predicted_whole_job_peak_bytes": projected_job_peak,
        "predicted_peak_delta_bytes": int(predicted_peak_delta_bytes),
        "whole_job_current_bytes": job_current,
        "whole_job_cap_bytes": job_cap,
        "warning_threshold_bytes": warning,
        "controlled_stop_threshold_bytes": controlled_stop,
        "host_headroom_after_reserve_bytes": reserve_headrooms[0],
        "ancestor_headroom_after_buffer_bytes": reserve_headrooms[1],
        "host_and_ancestor_headroom_after_reserves_bytes": reserve_headrooms[2],
        "host_reserve_required_bytes": int(authority["host_reserve_required_bytes"]),
        "task_buffer_required_bytes": int(authority["task_buffer_required_bytes"]),
        "memory_authority": dict(authority),
    }


def build_task44_residual_snapshot_identity(
    *,
    output_directory: Path,
    cfg: Any,
    mesh_data: Any,
    function_space: Any,
    floquet_data: Any,
    modes: Sequence[Any],
    reduced_solution: Any,
    condensed: Any,
) -> dict[str, Any]:
    """Hash the exact Task44 run, mesh, modes, phases and dof layout."""
    output_directory = Path(output_directory).resolve(strict=True)
    run_root = output_directory.parent
    identity_names = (
        "source_sha.txt",
        "input_sha256.txt",
        "physical_model_sha256.txt",
        "run_manifest.json",
        "resolved_config.json",
        "input_original.dat",
    )
    if all((run_root / name).is_file() for name in identity_names):
        identity_files = {
            name: _file_identity(run_root, name) for name in identity_names
        }
        run_manifest = json.loads(
            (run_root / "run_manifest.json").read_text(encoding="utf-8")
        )
        resolved_config = json.loads(
            (run_root / "resolved_config.json").read_text(encoding="utf-8")
        )
        identity_checks = {
            "source_sha_matches_run_manifest": (
                identity_files["source_sha.txt"]["value"]
                == run_manifest.get("source_sha")
            ),
            "input_sha_matches_original_input": (
                identity_files["input_sha256.txt"]["value"]
                == identity_files["input_original.dat"]["sha256"]
            ),
            "input_sha_matches_run_manifest": (
                identity_files["input_sha256.txt"]["value"]
                == run_manifest.get("input_sha256")
            ),
            "physical_model_sha_matches_run_manifest": (
                identity_files["physical_model_sha256.txt"]["value"]
                == run_manifest.get("physical_model_sha256")
            ),
            "resolved_config_sha_matches_run_manifest": (
                identity_files["resolved_config.json"]["sha256"]
                == run_manifest.get("resolved_config_sha256")
            ),
        }
        if not all(identity_checks.values()):
            raise ValueError(
                f"Task44 residual snapshot run identity mismatch: {identity_checks}"
            )
        run_identity = {
            "run_id": run_manifest.get("run_id"),
            "source_sha": run_manifest.get("source_sha"),
            "input_sha256": run_manifest.get("input_sha256"),
            "physical_model_sha256": run_manifest.get("physical_model_sha256"),
            "resolved_config_sha256": run_manifest.get("resolved_config_sha256"),
            "identity_source": "verified_run_manifest_and_identity_files",
        }
    else:
        source_sha = os.environ.get("MYFENICS_TASK44_SOURCE_SHA", "")
        run_id = os.environ.get("MYFENICS_TASK44_RUN_ID")
        input_path_text = os.environ.get("MYFENICS_TASK44_INPUT_PATH", "")
        input_sha256 = os.environ.get("MYFENICS_TASK44_INPUT_SHA256", "")
        physical_model_sha256 = os.environ.get(
            "MYFENICS_TASK44_PHYSICAL_MODEL_SHA256", ""
        )
        if not all((source_sha, input_path_text, input_sha256, physical_model_sha256)):
            raise FileNotFoundError(
                "Task44 pre-residual snapshot requires run identity files or the "
                "explicit Task44 source/input/model identity environment"
            )
        input_path = Path(input_path_text).resolve(strict=True)
        input_sha_on_disk, input_bytes = _sha256_file(input_path)
        identity_checks = {
            "source_sha_is_full_git_identity": len(source_sha) == 40
            and all(character in "0123456789abcdef" for character in source_sha.lower()),
            "input_sha_matches_input_path": input_sha_on_disk == input_sha256,
            "physical_model_sha_is_sha256": len(physical_model_sha256) == 64
            and all(
                character in "0123456789abcdef"
                for character in physical_model_sha256.lower()
            ),
        }
        if not all(identity_checks.values()):
            raise ValueError(
                f"Task44 residual snapshot external identity mismatch: {identity_checks}"
            )
        identity_files = {
            "input_original.dat": {
                "path": str(input_path),
                "bytes": input_bytes,
                "sha256": input_sha_on_disk,
            }
        }
        resolved_config = {}
        run_identity = {
            "run_id": run_id,
            "source_sha": source_sha,
            "input_sha256": input_sha256,
            "physical_model_sha256": physical_model_sha256,
            "resolved_config_sha256": None,
            "identity_source": "validated_task44_service_environment",
        }

    config_snapshot = cfg.as_jsonable()
    config_bytes = _canonical_json(config_snapshot)
    mesh_identity = _mesh_array_identity(mesh_data)
    cfg_gauge = getattr(cfg, "dtn_phase_gauge", None)
    resolved_gauge = next(
        (
            section.get("dtn_phase_gauge")
            for key in ("boundary", "method", "solver", "output")
            if isinstance((section := resolved_config.get(key)), Mapping)
            and isinstance(section.get("dtn_phase_gauge"), str)
        ),
        None,
    )
    if (
        isinstance(cfg_gauge, str)
        and isinstance(resolved_gauge, str)
        and cfg_gauge != resolved_gauge
    ):
        raise ValueError(
            "Task44 runtime and resolved input select different DtN phase gauges"
        )
    runtime_gauge_label = os.environ.get("MYFENICS_TASK44_DIAGNOSTIC_PHASE_GAUGE")
    gauge_source = (
        "SimulationConfig3D.dtn_phase_gauge"
        if isinstance(cfg_gauge, str)
        else "resolved_config.dtn_phase_gauge"
        if isinstance(resolved_gauge, str)
        else "current Task44 port-output default"
    )
    configured_solver_gauge = cfg_gauge or resolved_gauge or "global_z"
    identity = {
        "schema": SNAPSHOT_SCHEMA,
        "purpose": "preserve diagnostic inputs before matrix-free UFL residual action",
        "restartable": False,
        "official_solution": False,
        "residual_gate_pass": False,
        "output_directory": str(output_directory),
        "run_identity_files": identity_files,
        "run_identity_checks": identity_checks,
        "run_manifest_identity": run_identity,
        "runtime_config": {
            "sha256": hashlib.sha256(config_bytes).hexdigest(),
            "geometry_identity": getattr(cfg, "geometry_identity", None),
            "geometry_kind": str(cfg.geometry_kind),
            "stage_case": str(cfg.stage_case),
            "dtn_phase_gauge": str(configured_solver_gauge),
            "dtn_boundary_reference_planes": {
                "top": float(cfg.physical_z_max),
                "bottom": float(cfg.physical_z_min),
            },
            "mesh_cells_resolved": [int(value) for value in mesh_data.mesh_cells_resolved],
            "floquet_phase_x": _complex_pair(floquet_data.phase_x),
            "floquet_phase_y": _complex_pair(floquet_data.phase_y),
            "wavevector": [_complex_pair(value) for value in cfg.wavevector],
            "wavelength_nm": float(cfg.lambda0),
        },
        "mesh_identity": mesh_identity,
        "dof_identity": _dof_identity(function_space, reduced_solution, condensed),
        "mode_keys_and_phases": _mode_identity(modes, cfg),
        "phase_gauge_identity": {
            "configured_solver_output_gauge": str(configured_solver_gauge),
            "configured_gauge_source": gauge_source,
            "runtime_diagnostic_gauge_label": runtime_gauge_label,
            "recording_semantics": (
                "configuration and diagnostic selector are stored separately; "
                "per-mode global-z and boundary-plane phase definitions are recorded"
            ),
            "solver_default_when_no_gauge_is_configured": "global_z",
            "physical_port_reference": (
                "top=physical_z_max; bottom=physical_z_min"
            ),
        },
    }
    identity["identity_sha256"] = hashlib.sha256(_canonical_json(identity)).hexdigest()
    return identity


def _vec_array(vector: Any) -> tuple[np.ndarray, dict[str, Any]]:
    borrowed = np.asarray(vector.getArray(readonly=True))
    values = np.array(borrowed, copy=True, order="C")
    start, stop = vector.getOwnershipRange()
    description = {
        "global_size": int(vector.getSize()),
        "ownership_range": [int(start), int(stop)],
        "local_size": int(values.size),
        "dtype": str(values.dtype),
        "sha256": hashlib.sha256(memoryview(values).cast("B")).hexdigest(),
        "bytes": int(values.nbytes),
    }
    return values, description


def preflight_task44_residual_snapshot(
    vectors: Mapping[str, Any],
    *,
    mpi_size: int,
    include_reduced_residual: bool,
    memory_authority: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if int(mpi_size) != 1:
        raise RuntimeError("Task44 pre-residual diagnostic snapshots currently require MPI size 1")
    vector_copy_bytes = 0
    vector_sizes: dict[str, int] = {}
    for name, vector in vectors.items():
        borrowed = np.asarray(vector.getArray(readonly=True))
        expected_local = int(vector.getOwnershipRange()[1] - vector.getOwnershipRange()[0])
        if borrowed.size != expected_local:
            raise ValueError(f"Task44 snapshot vector {name} has inconsistent local ownership")
        vector_sizes[name] = int(borrowed.size * borrowed.dtype.itemsize)
        vector_copy_bytes += vector_sizes[name]
    residual_bytes = vector_sizes.get("reduced_rhs", 0) if include_reduced_residual else 0
    # The estimate includes a temporary PETSc residual Vec, its captured NumPy
    # copy, the writer's second residual copy, all four saved vectors, and
    # bounded NPZ/manifest workspace. The capture copy remains alive while the
    # writer creates its duplicate, so those lifetimes overlap.
    npz_and_manifest_workspace_bytes = MIB
    predicted_peak_delta_bytes = (
        vector_copy_bytes
        + 3 * residual_bytes
        + npz_and_manifest_workspace_bytes
    )
    authority = (
        _read_task44_whole_job_memory_authority()
        if memory_authority is None
        else dict(memory_authority)
    )
    memory_gate = _validate_snapshot_memory_gate(
        predicted_peak_delta_bytes, authority
    )
    return {
        "status": "pass",
        "mpi_size": 1,
        "vector_copy_bytes": vector_copy_bytes,
        "reduced_residual_temporary_and_copy_bytes": 3 * residual_bytes,
        "npz_and_manifest_workspace_bytes": npz_and_manifest_workspace_bytes,
        "predicted_peak_delta_bytes": predicted_peak_delta_bytes,
        "predicted_disk_bytes_upper_bound": (
            vector_copy_bytes + residual_bytes + npz_and_manifest_workspace_bytes
        ),
        "allowance_bytes": MAX_SNAPSHOT_PEAK_DELTA_BYTES,
        "whole_job_memory_gate": memory_gate,
    }


def write_task44_pre_residual_snapshot(
    *,
    identity: Mapping[str, Any],
    vectors: Mapping[str, Any],
    reduced_metrics: Mapping[str, Any],
    reduced_ax_minus_b: np.ndarray | None,
    budget: Mapping[str, Any],
) -> dict[str, Any]:
    output_directory = Path(str(identity["output_directory"])).resolve(strict=True)
    snapshot_directory = output_directory / (
        f"task44_pre_operator_residual_{time.time_ns()}_{os.getpid()}_{uuid.uuid4().hex}"
    )
    snapshot_directory.mkdir(mode=0o700, parents=False, exist_ok=False)

    arrays: dict[str, np.ndarray] = {}
    vector_facts: dict[str, Any] = {}
    for name, vector in vectors.items():
        arrays[name], vector_facts[name] = _vec_array(vector)
    if reduced_ax_minus_b is not None:
        values = np.array(reduced_ax_minus_b, copy=True, order="C")
        arrays["reduced_ax_minus_b"] = values
        vector_facts["reduced_ax_minus_b"] = {
            "global_size": int(values.size),
            "ownership_range": [0, int(values.size)],
            "local_size": int(values.size),
            "dtype": str(values.dtype),
            "sha256": hashlib.sha256(memoryview(values).cast("B")).hexdigest(),
            "bytes": int(values.nbytes),
            "semantic": "reduced_matrix @ reduced_solution - reduced_rhs",
        }

    vector_path = snapshot_directory / "vectors.npz"
    with vector_path.open("xb") as stream:
        np.savez(stream, **arrays)
        stream.flush()
        os.fsync(stream.fileno())
    vector_sha256, vector_file_bytes = _sha256_file(vector_path)

    residual_vector_status = (
        "saved"
        if "reduced_ax_minus_b" in arrays
        else "not_available_at_snapshot_entry"
    )
    manifest = {
        **dict(identity),
        "status": "snapshot_written_before_matrix_free_ufl_action",
        "restartable": False,
        "official_solution": False,
        "residual_gate_pass": False,
        "vector_payload": {
            "file": vector_path.name,
            "sha256": vector_sha256,
            "bytes": vector_file_bytes,
            "compression": "none",
            "arrays": vector_facts,
        },
        "reduced_system_residual": {
            "semantic": "reduced_matrix @ reduced_solution - reduced_rhs",
            "vector_status": residual_vector_status,
            "metrics_at_entry": dict(reduced_metrics),
        },
        "snapshot_memory_budget": dict(budget),
        "matrix_free_ufl_action_started": False,
    }
    manifest_path = snapshot_directory / "manifest.json"
    manifest_bytes = _canonical_json(manifest) + b"\n"
    with manifest_path.open("xb") as stream:
        stream.write(manifest_bytes)
        stream.flush()
        os.fsync(stream.fileno())
    manifest_sha256, _ = _sha256_file(manifest_path)
    return {
        "status": manifest["status"],
        "restartable": False,
        "official_solution": False,
        "snapshot_directory": str(snapshot_directory),
        "manifest_sha256": manifest_sha256,
        "vectors_sha256": vector_sha256,
        "vectors_bytes": vector_file_bytes,
        "predicted_peak_delta_bytes": int(
            budget["predicted_peak_delta_bytes"]
        ),
    }
