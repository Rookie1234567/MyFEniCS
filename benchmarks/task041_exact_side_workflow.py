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
from collections.abc import Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks.task034_wsl_resources import resource_authority_sample
from benchmarks.task039_v4_selected_mode_packet import (
    TASK041_BALH_SELECTED_MODE_IDENTITY_SCHEMA,
    TASK041_SELECTED_MODE_IDENTITY_SCHEMA,
    TASK041_SHORTWAVE_SELECTED_MODE_IDENTITY_SCHEMA,
    task041_selected_mode_scope,
    task041_shortwave_selected_mode_scope,
)
from src.io.input_validation import (
    TASK041_BALH_MPI_SIZE,
    TASK041_MODEL_ID,
    TASK041_SHORTWAVE_MPI_SIZE,
    load_and_resolve,
    simulation_config_3d_from_normalized,
    task041_balh_case,
    task041_balh_diagnostic_output_enabled,
    task041_balh_phase_limits_for_model,
    task041_balh_profile_errors,
    task041_balh_workflow_limits,
    task041_profile_errors,
    task041_shortwave_case,
    task041_shortwave_phase_limits_for_model,
    task041_shortwave_profile_errors,
    task041_shortwave_workflow_limits,
)
from src.io.resolved_config import resolved_config_sha256
from src.solvers.full3d_lifecycle_packet import write_packet
from src.solvers.hybrid_interface_basis import canonical_mode_keys_sha256

TASK041_MODE_PREP_SCHEMA = "task041.exact_side.mode_prep.v1"
TASK041_MODE_PREP_PROFILE = "task041_5nm_exact_side_hybrid_iterative"
TASK041_MODE_PREP_PHASE = "mode-prep"
TASK041_CONSUMER_SCHEMA = "task041.exact_side.consumer.v1"
TASK041_CONSUMER_PROFILE = "task041_5nm_exact_side_hybrid_iterative_consumer"
TASK041_SHORTWAVE_MODE_PREP_PROFILE = "task041_3nm_exact_side_hybrid_iterative"
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
    "solution_checkpoint_saved",
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


def _task041_stream_array_metadata(name: str, value: Any) -> dict[str, Any]:
    """Hash one already-exposed array without materialising a second copy."""

    if not isinstance(value, np.ndarray):
        raise TypeError(f"layout array {name} is not an exposed NumPy array")
    array = value
    if array.dtype.hasobject:
        raise TypeError(f"layout array {name} has object dtype")
    digest = hashlib.sha256()
    if array.size == 0:
        # NumPy marks many zero-length strided views contiguous even when a
        # byte cast would be an invalid/meaningless path.  The empty payload
        # is still a measured value with a stable digest.
        hash_status = "measured_empty"
    elif array.flags.c_contiguous:
        view = memoryview(array).cast("B")
        try:
            for start in range(0, view.nbytes, 1 << 20):
                digest.update(view[start : start + (1 << 20)])
        finally:
            view.release()
        hash_status = "measured_contiguous"
    else:
        iterator = np.nditer(
            array,
            flags=["external_loop", "buffered"],
            op_flags=["readonly"],
            buffersize=8192,
        )
        for chunk in iterator:
            digest.update(np.asarray(chunk).tobytes(order="C"))
        hash_status = "measured_chunked_noncontiguous"
    return {
        "name": name,
        "shape": [int(item) for item in array.shape],
        "dtype": str(array.dtype),
        "nbytes": int(array.size * array.dtype.itemsize),
        "storage_nbytes": int(array.nbytes),
        "sha256": digest.hexdigest(),
        "hash_status": hash_status,
        "storage": "rank_local_existing_array",
    }


def _task041_held_object_metadata(name: str, value: Any) -> dict[str, Any]:
    """Record identity for one already-held Python/C++ wrapper."""

    if value is None:
        raise TypeError(f"required held object {name} is missing")
    record = {
        "name": name,
        "kind": type(value).__name__,
        "python_id": id(value),
    }
    cpp_object = getattr(value, "_cpp_object", None)
    if cpp_object is not None:
        record["cpp_object"] = {
            "kind": type(cpp_object).__name__,
            "python_id": id(cpp_object),
        }
    return record


def _task041_held_petsc_identity(name: str, value: Any) -> dict[str, Any]:
    """Record a real petsc4py handle without reading matrix contents."""

    if value is None:
        raise TypeError(f"required held PETSc object {name} is missing")
    handle = value.handle
    if handle is None:
        raise TypeError(f"required PETSc handle {name} is unavailable")
    return {
        "name": name,
        "kind": type(value).__name__,
        "python_id": id(value),
        "petsc_handle": int(handle),
    }


def _task041_communicator_identity(name: str, communicator: Any) -> dict[str, Any]:
    """Read rank, size, and the actual MPI communicator handle."""

    return {
        "name": name,
        "rank": int(communicator.Get_rank()),
        "size": int(communicator.Get_size()),
        "fortran_handle": int(communicator.py2f()),
    }


def _task041_mpc_layout_metadata(name: str, mpc: Any) -> dict[str, Any]:
    """Hash the exposed MPC arrays and each owned master's link array."""

    if mpc is None:
        raise TypeError(f"required MPC {name} is missing")
    coefficients, offsets = mpc.coefficients()
    slaves = np.asarray(mpc.slaves)
    links_digest = hashlib.sha256()
    link_count = 0
    for slave in slaves:
        links = np.asarray(mpc.masters.links(int(slave)))
        metadata = _task041_stream_array_metadata(
            f"{name}.masters[{int(slave)}]", links
        )
        links_digest.update(
            f"{int(slave)}:{metadata['shape']}:{metadata['dtype']}:{metadata['sha256']}".encode()
        )
        link_count += int(links.size)
    return {
        "name": name,
        "slaves": _task041_stream_array_metadata(f"{name}.slaves", slaves),
        "coefficients": _task041_stream_array_metadata(
            f"{name}.coefficients", np.asarray(coefficients)
        ),
        "offsets": _task041_stream_array_metadata(
            f"{name}.offsets", np.asarray(offsets)
        ),
        "masters_links_sha256": links_digest.hexdigest(),
        "master_link_count": link_count,
        "master_links_status": "measured_per_owned_slave",
    }


def _task041_transfer_records_metadata(transfer: Any) -> dict[str, Any]:
    """Hash the existing rank-local transfer records without retaining arrays."""

    digest = hashlib.sha256()
    field_names = (
        "fine_local",
        "fine_global",
        "coarse_local",
        "coarse_global",
        "authority",
    )
    for index, record in enumerate(transfer._records):
        for name in field_names:
            metadata = _task041_stream_array_metadata(
                f"transfer.records[{index}].{name}", record[name]
            )
            digest.update(
                f"{index}:{name}:{metadata['shape']}:{metadata['dtype']}:{metadata['sha256']}".encode()
            )
    return {
        "record_count": len(transfer._records),
        "fields": list(field_names),
        "sha256": digest.hexdigest(),
        "status": "measured_streaming_rank_local",
    }


def _task041_space_layout_metadata(name: str, space: Any) -> dict[str, Any]:
    """Capture the actual FunctionSpace/cpp-dofmap and owned map bytes."""

    if space is None:
        raise TypeError(f"required function space {name} is missing")
    cpp_space = space._cpp_object
    cpp_dofmap = cpp_space.dofmap
    dofmap_map = np.asarray(cpp_dofmap.map())
    dofmap = space.dofmap
    index_map = dofmap.index_map
    return {
        "space": {
            **_task041_held_object_metadata(name, space),
            "cpp_kind": type(cpp_space).__name__,
            "cpp_python_id": id(cpp_space),
        },
        "dofmap": {
            "backend_kind": type(cpp_dofmap).__name__,
            "map": _task041_stream_array_metadata(
                f"{name}.dofmap.list", dofmap_map
            ),
            "global_size": int(index_map.size_global),
            "local_size": int(index_map.size_local),
            "num_ghosts": int(index_map.num_ghosts),
            "block_size": int(dofmap.index_map_bs),
        },
    }


def _task041_common_failure_details(
    exception: BaseException,
    inverse: Any,
) -> tuple[str, dict[str, Any]]:
    """Keep the original C3 cause while assigning the common-mode class."""

    from src.solvers.physical_balanced_coupling import BalancedConstraintRejected
    from src.solvers.physical_balanced_side_inverse import (
        P4PhysicalResidualGateError,
    )

    cause = {
        "exception_type": type(exception).__name__,
        "exception": str(exception),
    }
    if isinstance(exception, P4PhysicalResidualGateError):
        return "NUMERICAL_GATE_FAIL", {
            "cause": cause,
            "p4_solve_audit": dict(exception.audit),
        }
    if isinstance(exception, BalancedConstraintRejected):
        return "NUMERICAL_GATE_FAIL", {
            "cause": cause,
            "balance_audit": dict(exception.facts),
        }
    coupling_failure = inverse._last_coupling_failure
    if coupling_failure is not None:
        failure = dict(coupling_failure)
        classification = failure.get("failure_classification")
        if classification in {
            "P4_PHYSICAL_RESIDUAL_GATE",
            "BALANCED_CONSTRAINT_REJECTED",
        }:
            return "NUMERICAL_GATE_FAIL", {
                "cause": cause,
                "coupling_failure": failure,
            }
        return "PAIRING_SETUP_FAILURE", {
            "cause": cause,
            "coupling_failure": failure,
        }
    classification = getattr(exception, "failure_classification", None)
    evidence = getattr(exception, "failure_evidence", None)
    if classification in {
        "PAIRING_SETUP_FAILURE",
        "NUMERICAL_GATE_FAIL",
        "ACTION_EQUIVALENCE_FAIL",
        "RESPONSE_SENSITIVITY_UNRESOLVED",
    }:
        return classification, {
            "cause": cause,
            "failure_evidence": (
                dict(evidence) if isinstance(evidence, Mapping) else {}
            ),
        }
    return "PAIRING_SETUP_FAILURE", {"cause": cause}


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


def _task041_packet_source_identity(
    consumer_source_sha: str,
    packet_producer_source_sha: str | None,
    packet_identity_source_sha: Any,
) -> dict[str, Any]:
    producer_source_sha = (
        consumer_source_sha
        if packet_producer_source_sha is None
        else packet_producer_source_sha
    )
    if packet_producer_source_sha is not None and not _valid_sha(
        packet_producer_source_sha, 40
    ):
        raise Task041ModePrepError(
            "packet_producer_source_sha must be a lowercase 40-character SHA"
        )
    if packet_identity_source_sha != producer_source_sha:
        raise Task041ModePrepError("Task041 packet identity source_sha mismatch")
    cross_source = producer_source_sha != consumer_source_sha
    return {
        "producer_source_sha": producer_source_sha,
        "consumer_source_sha": consumer_source_sha,
        "cross_source_packet_reuse": cross_source,
        "reuse_reason": (
            "implementation_failure_recovery_persistence_retry"
            if cross_source
            else "same_source_packet"
        ),
    }


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


def _task041_legacy_limits() -> dict[str, int]:
    return {
        "warning_memory_bytes": TASK041_WARNING_MEMORY_BYTES,
        "hard_memory_bytes": TASK041_HARD_MEMORY_BYTES,
        "min_memavailable_bytes": TASK041_MIN_MEMAVAILABLE_BYTES,
        "timeout_seconds": TASK041_TIMEOUT_SECONDS,
    }


def _task041_case_contract(
    normalized: Mapping[str, Any], comm_size: int, *, phase: str
) -> dict[str, Any]:
    """Validate and return the small control-plane contract for one case."""

    model_id = str(normalized.get("model_id", ""))
    if model_id == TASK041_MODEL_ID:
        failures = tuple(task041_profile_errors(normalized))
        if failures:
            detail = "; ".join(f"{field}: {message}" for field, message in failures)
            raise Task041ModePrepError("Task041 profile rejected: " + detail)
        if comm_size != 1:
            raise Task041ModePrepError("Task041 legacy case requires MPI1")
        return {
            "shortwave": False,
            "balh": False,
            "mpi_size": 1,
            "mode_count": 480,
            "mesh_target_nm": 4.0,
            "degree": 6,
            "mode_prep_profile": TASK041_MODE_PREP_PROFILE,
            "consumer_schema": TASK041_CONSUMER_SCHEMA,
            "consumer_profile": TASK041_CONSUMER_PROFILE,
            "limits": _task041_legacy_limits(),
        }

    balh_case = task041_balh_case(model_id)
    if balh_case is not None:
        failures = tuple(task041_balh_profile_errors(normalized))
        if failures:
            detail = "; ".join(f"{field}: {message}" for field, message in failures)
            raise Task041ModePrepError("Task041 side BAL_H profile rejected: " + detail)
        if comm_size != TASK041_BALH_MPI_SIZE:
            raise Task041ModePrepError("Task041 side BAL_H case requires MPI8")
        from benchmarks.task041_balh_workflow import (
            TASK041_BALH_CANDIDATE_CONSUMER_PROFILE,
            TASK041_BALH_CANDIDATE_CONSUMER_SCHEMA,
            TASK041_BALH_EXACT_CONSUMER_PROFILE,
            TASK041_BALH_EXACT_CONSUMER_SCHEMA,
            TASK041_BALH_MODE_PREP_PROFILE,
            task041_balh_transfer_optimization_profile,
        )

        route = str(balh_case["route"])
        p4_inverse_backend = str(balh_case.get("p4_inverse_backend", "full"))
        support_policy = str(balh_case.get("support_policy", "legacy"))
        if p4_inverse_backend not in {"full", "cell_condensed"}:
            raise Task041ModePrepError(
                f"unsupported Task041 p4 inverse backend: {p4_inverse_backend!r}"
            )
        if p4_inverse_backend == "cell_condensed" and support_policy != "entity_closure":
            raise Task041ModePrepError(
                "cell-condensed Task041 cases require entity_closure support policy"
            )
        return {
            "shortwave": False,
            "balh": True,
            "balh_route": route,
            "mpi_size": TASK041_BALH_MPI_SIZE,
            "mode_count": int(balh_case["mode_count"]),
            "mesh_target_nm": float(balh_case["mesh_target_nm"]),
            "degree": 6,
            "mode_prep_profile": TASK041_BALH_MODE_PREP_PROFILE,
            "consumer_schema": (
                TASK041_BALH_EXACT_CONSUMER_SCHEMA
                if route == "exact"
                else TASK041_BALH_CANDIDATE_CONSUMER_SCHEMA
            ),
            "consumer_profile": (
                TASK041_BALH_EXACT_CONSUMER_PROFILE
                if route == "exact"
                else TASK041_BALH_CANDIDATE_CONSUMER_PROFILE
            ),
            "limits": dict(task041_balh_phase_limits_for_model(model_id, phase)),
            "workflow_limits": dict(task041_balh_workflow_limits(model_id)),
            "diagnostic_output_on_unqualified": task041_balh_diagnostic_output_enabled(
                model_id
            ),
            "producer_time_stop_enforced": balh_case.get(
                "producer_time_stop_enforced", True
            ),
            "consumer_time_stop_enforced": balh_case.get(
                "consumer_time_stop_enforced", True
            ),
            "transfer_optimization_profile": (
                task041_balh_transfer_optimization_profile(model_id)
            ),
            "p4_inverse_backend": p4_inverse_backend,
            "support_policy": support_policy,
            "construction_audit": balh_case.get("construction_audit"),
        }

    failures = tuple(task041_shortwave_profile_errors(normalized))
    if failures:
        detail = "; ".join(f"{field}: {message}" for field, message in failures)
        raise Task041ModePrepError("Task41 shortwave profile rejected: " + detail)
    case = task041_shortwave_case(model_id)
    if case is None:
        raise Task041ModePrepError("Task041 case contract rejects this model_id")
    if comm_size != TASK041_SHORTWAVE_MPI_SIZE:
        raise Task041ModePrepError("Task41 shortwave case requires MPI8")
    discretization = normalized["discretization"]
    phase_limits = dict(task041_shortwave_phase_limits_for_model(model_id, phase))
    return {
        "shortwave": True,
        "balh": False,
        "mpi_size": TASK041_SHORTWAVE_MPI_SIZE,
        "mode_count": int(case["mode_count"]),
        "mesh_target_nm": discretization["mesh_target_nm"],
        "degree": discretization["nedelec_degree"],
        "mode_prep_profile": TASK041_SHORTWAVE_MODE_PREP_PROFILE,
        "consumer_schema": TASK041_SHORTWAVE_CONSUMER_SCHEMA,
        "consumer_profile": TASK041_SHORTWAVE_CONSUMER_PROFILE,
        "limits": phase_limits,
        "workflow_limits": dict(task041_shortwave_workflow_limits(model_id)),
    }


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
        "scope": task041_shortwave_selected_mode_scope(
            mode_count, mpi_size, model_id=normalized["model_id"]
        ),
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


def _check_resource(
    sample: Mapping[str, Any],
    started: float,
    limits: Mapping[str, Any] | None = None,
    *,
    enforce_time_stop: bool = True,
) -> None:
    active_limits = _task041_legacy_limits() if limits is None else limits
    memory_authority = sample.get("memory_authority_bytes")
    if not isinstance(memory_authority, (int, float, np.integer, np.floating)):
        raise Task041ModePrepError("resource sample lacks memory_authority_bytes")
    if float(memory_authority) >= active_limits["hard_memory_bytes"]:
        raise Task041ModePrepError("Task041 hard RSS limit reached")
    process_tree_rss_cap = active_limits.get("process_tree_rss_cap_bytes")
    if process_tree_rss_cap is not None:
        process_tree = sample.get("process_tree")
        process_tree_complete = bool(
            isinstance(process_tree, Mapping)
            and process_tree.get("all_status_readable") is True
        )
        process_tree_rss = (
            _process_tree_rss(sample) if process_tree_complete else None
        )
        if process_tree_rss is None:
            raise Task041ModePrepError(
                "resource sample lacks complete simultaneous process-tree RSS"
            )
        if process_tree_rss >= process_tree_rss_cap:
            raise Task041ModePrepError("Task041 process-tree RSS cap reached")
    if sample.get("job_no_swap") is not True:
        raise Task041ModePrepError("Task041 swap limit reached")
    if enforce_time_stop and time.monotonic() - started >= active_limits["timeout_seconds"]:
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


def _collective_fresh_root(run_directory: str | Path, comm: Any) -> Path:
    root = Path(run_directory).resolve()
    outcome: dict[str, Any] | None = None
    if comm.rank == 0:
        try:
            if root.exists():
                raise FileExistsError(f"Task041 run directory already exists: {root}")
            root.mkdir(parents=True)
            outcome = {"ok": True}
        except FileExistsError as exc:
            outcome = {
                "ok": False,
                "type": "FileExistsError",
                "message": str(exc),
            }
        except Exception as exc:  # noqa: BLE001 - broadcast root creation failure
            outcome = {"ok": False, "type": type(exc).__name__, "message": str(exc)}
    outcome = comm.bcast(outcome, root=0)
    comm.Barrier()
    if outcome.get("ok") is True:
        return root
    if outcome.get("type") == "FileExistsError":
        raise FileExistsError(str(outcome.get("message", root)))
    raise Task041ModePrepError(
        "Task041 run directory creation failed: "
        + str(outcome.get("message", "unknown error"))
    )


def _write_rank0_json(path: Path, payload: Mapping[str, Any], comm: Any) -> None:
    if comm.rank == 0:
        _write_json(path, payload)
    comm.Barrier()


def _write_rank_pid_affinity(
    root: Path,
    *,
    phase: str,
    source_sha: str,
    comm: Any,
) -> None:
    """Persist one small rank-to-process/affinity map at worker preflight."""

    try:
        cpu_affinity = sorted(int(cpu) for cpu in os.sched_getaffinity(0))
    except (AttributeError, OSError):
        cpu_affinity = None
    local = {
        "rank": int(comm.rank),
        "pid": int(os.getpid()),
        "cpu_affinity": cpu_affinity,
        "cpu_affinity_status": (
            "measured" if cpu_affinity is not None else "not_measured"
        ),
    }
    records = comm.gather(local, root=0)
    if comm.rank == 0:
        ordered = sorted(records or [], key=lambda row: int(row["rank"]))
        _write_json(
            root / "rank_pid_affinity.json",
            {
                "schema": "task041.rank_pid_affinity.v1",
                "phase": phase,
                "source_sha": source_sha,
                "mpi_size": int(comm.size),
                "record_count": len(ordered),
                "status": (
                    "measured"
                    if len(ordered) == int(comm.size)
                    else "partially_measured"
                ),
                "records": ordered,
            },
        )
    comm.Barrier()


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
    limits: Mapping[str, Any] | None = None,
    enforce_time_stop: bool = True,
) -> dict[str, Any]:
    active_limits = _task041_legacy_limits() if limits is None else limits
    resource = _resource_snapshot()
    _check_resource(
        resource,
        started,
        active_limits,
        enforce_time_stop=enforce_time_stop,
    )
    marker = {
        "schema": schema,
        "stage": stage,
        "sequence_index": marker_sequence.index(stage),
        "wall_seconds": time.monotonic() - started,
        "environment": _jsonable(environment),
        "limits": _jsonable(active_limits),
        "time_stop_enforced": bool(enforce_time_stop),
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

    if not _valid_sha(source_sha, 40):
        raise Task041ModePrepError("source_sha must be a lowercase 40-character SHA")
    specification = load_and_resolve(input_path)
    normalized = specification.as_jsonable()
    contract = _task041_case_contract(normalized, comm.size, phase="producer")
    root = _collective_fresh_root(run_directory, comm)
    started = time.monotonic()
    result: dict[str, Any] = {
        "schema": TASK041_MODE_PREP_SCHEMA,
        "profile": contract["mode_prep_profile"],
        "phase": TASK041_MODE_PREP_PHASE,
        "input": str(Path(input_path).resolve()),
        "run_directory": str(root),
        "source_sha": source_sha,
        "status": "IMPLEMENTATION_FAILURE",
        "classification": "IMPLEMENTATION_FAILURE",
        "official_rta": {"status": "not_run"},
        "limits": contract["limits"],
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
        if contract["balh"]:
            _write_rank_pid_affinity(
                root,
                phase=TASK041_MODE_PREP_PHASE,
                source_sha=source_sha,
                comm=comm,
            )
        _write_marker(
            root,
            started,
            "preflight_begin",
            environment=environment,
            detail={"mpi_size": comm.size, "input": str(input_path)},
            comm=comm,
            limits=contract["limits"],
        )
        available = _memavailable_bytes()
        if available < contract["limits"]["min_memavailable_bytes"]:
            raise Task041ModePrepError("MemAvailable is below the Task041 preflight floor")
        result["memavailable_bytes"] = available
        resolved_sha = resolved_config_sha256(specification)
        cfg = simulation_config_3d_from_normalized(normalized)
        if contract["balh"]:
            from benchmarks.task041_balh_workflow import (
                build_task041_balh_packet_identity,
            )

            identity_builder = build_task041_balh_packet_identity
        else:
            identity_builder = (
                build_task041_shortwave_packet_identity
                if contract["shortwave"]
                else build_task041_packet_identity
            )
        identity = identity_builder(specification, normalized, source_sha, resolved_sha)
        recomputed_identity = identity_builder(
            specification, normalized, source_sha, resolved_sha
        )
        if identity != recomputed_identity:
            raise Task041ModePrepError("Task041 identity recomputation mismatch")
        result["identity"] = identity
        identity_path = root / "packet_identity.json"
        _write_rank0_json(identity_path, identity, comm)
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
            limits=contract["limits"],
        )
        from benchmarks.run_task032_phase6_augmented import main as producer_main

        producer_args = _producer_argv(
            packet_directory,
            identity_path,
            producer_output,
            source_sha,
            mode_count,
            **(
                {
                    "mesh_target_nm": contract["mesh_target_nm"],
                    "degree": contract["degree"],
                }
                if contract["shortwave"] or contract["balh"]
                else {}
            ),
        )
        producer_record = producer_main(
            producer_args,
            config_override=cfg,
            canonical_export_prefix="task041_mode_prep",
            task039_stage_marker_path=root / "producer_markers.jsonl",
            task041_mode_prep=True,
            task041_expected_mesh_nm=contract["mesh_target_nm"],
            task041_expected_mpi_size=contract["mpi_size"],
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
            limits=contract["limits"],
        )
        _write_marker(
            root,
            started,
            "packet_written",
            environment=environment,
            detail=result["packet"],
            comm=comm,
            limits=contract["limits"],
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
                limits=contract["limits"],
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
        _write_rank0_json(root / "mode_prep_summary.json", result, comm)
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
    packet_producer_source_sha: str | None = None,
) -> list[str]:
    """Return the fresh MPI1 consumer command for a producer packet."""

    command = [
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
    if packet_producer_source_sha is not None:
        if not _valid_sha(packet_producer_source_sha, 40):
            raise Task041ModePrepError(
                "packet_producer_source_sha must be a lowercase 40-character SHA"
            )
        command.extend(["--packet-producer-source-sha", packet_producer_source_sha])
    return command


def build_task041_shortwave_consumer_command(
    python_executable: str | Path,
    specification: Any,
    packet_manifest: str | Path,
    packet_identity: str | Path,
    packet_manifest_sha256: str,
    run_directory: str | Path,
    source_sha: str,
    packet_producer_source_sha: str | None = None,
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
    command = [
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
    if packet_producer_source_sha is not None:
        if not _valid_sha(packet_producer_source_sha, 40):
            raise Task041ModePrepError(
                "packet_producer_source_sha must be a lowercase 40-character SHA"
            )
        command.extend(["--packet-producer-source-sha", packet_producer_source_sha])
    return command


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


def task041_shortwave_consumer_iterative_config() -> Any:
    """Return the effective native MPI8 shortwave GMRES configuration."""

    from src.solvers.hybrid_fem_modal_block_ldu import HybridBlockLduIterativeConfig

    return HybridBlockLduIterativeConfig(
        ksp_type="gmres",
        restart=10,
        max_it=4000,
        threshold=5.0e-9,
        initial_guess="zero",
        fixed_preconditioner=True,
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
        restart=10,
    )


def _task041_consumer_sampled_column_contract(
    identity: Mapping[str, Any],
    manifest_path: Path,
    manifest_sha256: str,
    *,
    legacy_native: bool = False,
) -> dict[str, Any]:
    """Bind the fixed v1 or shortwave v2 sampled roles to a fresh manifest."""

    identity_schema = identity.get("schema")
    if legacy_native:
        if identity_schema != "task039.v4.h4.mode-identity.v1":
            raise Task041ModePrepError(
                "legacy native sampled contract requires the approved Task039 identity"
            )
        if identity.get("mode_count") != 480 or identity.get("mpi_size") != 8:
            raise Task041ModePrepError(
                "legacy native sampled contract requires M480/MPI8"
            )
        mode_count = 480
        expected_contract_sha256 = None
        sampled_mode_schema = True
    else:
        sampled_mode_schema = identity_schema in {
        TASK041_BALH_SELECTED_MODE_IDENTITY_SCHEMA,
        TASK041_SHORTWAVE_SELECTED_MODE_IDENTITY_SCHEMA,
        }
    if not legacy_native and identity_schema == TASK041_BALH_SELECTED_MODE_IDENTITY_SCHEMA:
        case = task041_balh_case(str(identity.get("model_id", "")))
        if case is None or int(identity.get("mode_count", -1)) != int(
            case["mode_count"]
        ):
            raise Task041ModePrepError(
                "Task041 BAL_H sampled contract requires the registered M120/M480 case"
            )
        if identity.get("mpi_size") != TASK041_BALH_MPI_SIZE:
            raise Task041ModePrepError("Task041 BAL_H sampled contract requires MPI8")
        if identity.get("scope") != case["scope"]:
            raise Task041ModePrepError(
                "Task041 BAL_H sampled contract scope does not match the case"
            )
        if identity.get("cross_section_partition") != "input_contiguous_v1":
            raise Task041ModePrepError(
                "Task041 BAL_H sampled contract requires input_contiguous_v1"
            )
        mode_count = int(case["mode_count"])
        expected_contract_sha256 = None
    elif not legacy_native and identity_schema == TASK041_SHORTWAVE_SELECTED_MODE_IDENTITY_SCHEMA:
        mode_count = identity.get("mode_count")
        if type(mode_count) is not int or mode_count not in (800, 1200):
            raise Task041ModePrepError(
                "Task041 shortwave sampled contract requires M800 or M1200"
            )
        if type(identity.get("mpi_size")) is not int or identity.get(
            "mpi_size"
        ) != TASK041_SHORTWAVE_MPI_SIZE:
            raise Task041ModePrepError(
                "Task041 shortwave sampled contract requires MPI8"
            )
        if identity.get("scope") != task041_shortwave_selected_mode_scope(
            mode_count,
            TASK041_SHORTWAVE_MPI_SIZE,
            model_id=identity.get("model_id"),
        ):
            raise Task041ModePrepError(
                "Task041 shortwave sampled contract scope does not match M/MPI"
            )
        if identity.get("cross_section_partition") != "input_contiguous_v1":
            raise Task041ModePrepError(
                "Task041 shortwave sampled contract requires input_contiguous_v1"
            )
        expected_contract_sha256 = None
    elif not legacy_native:
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
    if sampled_mode_schema:
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
    expected_consumer_source_sha: str,
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
        == expected_consumer_source_sha,
        "physical_model_sha256": authority.get("physical_model_sha256")
        == recomputed_identity.get("physical_sha256"),
        "model_id": authority.get("model_id") == recomputed_identity.get("model_id"),
        "mpi_size": type(authority.get("mpi_size")) is int
        and authority.get("mpi_size") == recomputed_identity.get("mpi_size"),
        "requested_modes": type(authority.get("requested_modes")) is int
        and authority.get("requested_modes")
        == recomputed_identity.get("mode_count"),
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


def _task041_diagnostic_authority_available(
    authority_path: Path | None,
    formal_result: Mapping[str, Any],
    gates: Mapping[str, Any],
    *,
    policy_enabled: bool,
) -> bool:
    """Allow finite diagnostic output only after the structural gates pass."""

    release = formal_result.get("release_before_recovery")
    official_rta = gates.get("official_rta")
    rta_finite = bool(
        isinstance(official_rta, Mapping)
        and official_rta.get("status") == "measured"
        and all(
            isinstance(official_rta.get(name), (int, float))
            and not isinstance(official_rta.get(name), bool)
            and np.isfinite(float(official_rta[name]))
            for name in ("R", "T", "A", "A_volume")
        )
    )
    return bool(
        policy_enabled
        and authority_path is not None
        and authority_path.is_file()
        and isinstance(release, Mapping)
        and release.get("pass") is True
        and gates.get("pass") is False
        and isinstance(gates.get("authority_identity"), Mapping)
        and gates["authority_identity"].get("pass") is True
        and gates.get("grid_E_H_evidence_pass") is True
        and gates.get("external_diffraction_channels_pass") is True
        and gates.get("external_key_binding_pass") is True
        and gates.get("external_orders_key_binding_pass") is True
        and rta_finite
    )


def _merge_representative_parts(
    representative_parts: Sequence[Mapping[str, Any]],
    representative_entries: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Merge per-side representative results without changing formal output."""

    representative = dict(representative_parts[0])
    entries = [
        entry
        for part in representative_parts
        for entry in part["entries"]
    ]
    representative["entries"] = entries
    representative["expected_count"] = len(representative_entries)
    representative["completed_count"] = len(entries)
    if representative.get("comparison_mode") == "common_layout_equivalence":
        representative["apply_count"] = sum(
            part["apply_count"] for part in representative_parts
        )
    return representative


def _run_task041_balh_candidate_setup(
    setup: Any,
    layout: Any,
    *,
    comm: MPI.Intracomm,
    marker_callback: Callable[[str, Mapping[str, Any]], None],
    sampled_column_contract: Mapping[str, Any],
    qualification_scope: str,
    full_formal_runner: Callable[..., Mapping[str, Any]],
    timeout_seconds: float,
    audit_path: Path,
    elapsed_seconds: float,
    workflow_started_monotonic: float | None = None,
    failure_evidence: dict[str, Any],
    identity: Mapping[str, Any] | None = None,
    disable_time_stop: bool = False,
    detailed_timing: bool = False,
    representative_rhs_contract: Mapping[str, Any] | None = None,
    side_setup_schedule: str | None = None,
    performance_profile: str | None = None,
    transfer_optimization_profile: str | None = None,
    comparison_mode: str | None = None,
    p4_inverse_backend: str = "full",
    support_policy: str = "legacy",
    construction_audit: str | None = None,
    rank_numa_stage_callback: Callable[[str, Mapping[str, object] | None, Mapping[str, Any] | None], None] | None = None,
    rank_numa_evidence: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the finite-response BAL_H Schur and run the shared formal path."""

    from benchmarks.run_task037b_hybrid_iterative import collective_heap_cleanup
    from benchmarks.task041_balh_workflow import (
        TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE,
        TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
    )
    from src.solvers.hybrid_fem_modal_augmented_direct import (
        internal_modal_rhs_correction,
    )
    from src.solvers.hybrid_fem_modal_block_ldu import (
        create_side_balh_block_ldu_preconditioner,
    )
    from src.solvers.hybrid_fem_modal_iterative import (
        create_hybrid_assembled_block_action,
    )
    from src.solvers.hybrid_fem_modal_schur_direct import modal_coupling_action
    from src.solvers.physical_balanced_side_inverse import build_side_balanced_inverse
    from src.solvers.physical_balanced_trace_bridge import (
        inject_active_residual_to_full_p6,
    )

    side_inverses: dict[str, Any] = {}
    probe_records: dict[str, list[dict[str, Any]]] = {
        "bottom": [],
        "top": [],
    }
    representative_records: dict[str, list[dict[str, Any]]] = {
        "bottom": [],
        "top": [],
    }
    representative_context: dict[str, Mapping[str, Any] | None] = {
        "bottom": None,
        "top": None,
    }
    layout_evidence_by_side: dict[str, dict[str, Any]] = {}
    common_layout_rechecks: dict[str, list[dict[str, Any]]] = {
        "bottom": [],
        "top": [],
    }
    probe_active = {"bottom": True, "top": True}
    context = None
    operator = None
    operator_context = None
    released = False
    side_diagnostics_before: dict[str, dict[str, Any]] = {}
    side_diagnostics_after: dict[str, dict[str, Any]] = {}
    admission_audits: dict[str, Any] = {}
    sequential_side_records: dict[str, dict[str, Any]] = {}
    sequential_lifecycle_boundaries: list[dict[str, Any]] = []
    sequential_created_totals = {
        "side_inverse": 0,
        "p4_factor": 0,
        "nested_iterative_ksp": 0,
    }
    sequential_live_peaks = {
        "side_inverse": 0,
        "p4_factor": 0,
        "nested_iterative_ksp": 0,
        "owned_component": 0,
    }
    common_first_rhs_by_side: dict[str, PETSc.Vec | None] = {
        "bottom": None,
        "top": None,
    }
    common_first_entry_by_side: dict[str, Mapping[str, Any] | None] = {
        "bottom": None,
        "top": None,
    }
    variant_bindings_by_side: dict[str, dict[str, Any]] = {}
    layout_instance_ids: dict[str, str] = {}
    context_inventory_before: dict[str, Any] | None = None
    audit_path = Path(audit_path)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    helper_started = time.monotonic()
    audit_indices = {"bottom": 0, "top": 0}
    audit_phase = {"bottom": "cost_probe", "top": "cost_probe"}
    global_source: PETSc.Vec | None = None
    global_source_before: PETSc.Vec | None = None
    global_action_before: PETSc.Vec | None = None
    global_rhs_before: PETSc.Vec | None = None
    def audit_callback(side: str) -> Callable[[dict[str, Any]], None]:
        def record(audit: dict[str, Any]) -> None:
            index = audit_indices[side]
            audit_indices[side] += 1
            recorded_audit = dict(audit)
            if audit_phase[side] in {
                "representative_rhs",
                "common_layout_equivalence",
            }:
                context = representative_context[side]
                if context is not None:
                    recorded_audit.update(context)
                representative_records[side].append(recorded_audit)
            elif probe_active[side]:
                probe_records[side].append(recorded_audit)
            payload = {
                "phase": audit_phase[side],
                "side": side,
                "index": index,
                "status": recorded_audit.get("status"),
                "reason": recorded_audit.get("reason"),
                "iterations": recorded_audit.get("iterations"),
                "elapsed_seconds": recorded_audit.get("elapsed_seconds"),
                "rank": recorded_audit.get("rank"),
                "parent_wall_seconds": max(
                    0.0, time.monotonic() - helper_started
                ),
                "parent_wall_scope": "rank0_candidate_setup_helper_monotonic",
                "counts": recorded_audit.get("counts"),
                "audit": recorded_audit,
            }
            if comm.rank == 0:
                with audit_path.open("a", encoding="utf-8") as stream:
                    stream.write(
                        json.dumps(_jsonable(payload), sort_keys=True) + "\n"
                    )
                    stream.flush()

        return record

    def side_stage_event(
        side: str,
        event: str,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        if not detailed_timing and (
            side_setup_schedule != TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
        ):
            return
        marker_callback(
            "system_setup_stage",
            {
                "side": side,
                "substage": "side_construction",
                "event": str(event),
                "resource_scope": "rank_local",
                "clock": "CLOCK_MONOTONIC",
                "workflow_started_monotonic_seconds": (
                    workflow_started_monotonic
                ),
                **({} if detail is None else dict(detail)),
            },
        )

    def side_lifecycle_callback(
        side: str,
    ) -> Callable[[str, Mapping[str, Any]], None]:
        def record(event: str, detail: Mapping[str, Any]) -> None:
            side_stage_event(side, event, detail)

        return record

    def sequential_live_snapshot() -> dict[str, Any]:
        by_side: dict[str, dict[str, int]] = {}
        for active_side, inverse in side_inverses.items():
            diagnostics = inverse.diagnostics
            by_side[active_side] = {
                "p4_factor_count": int(
                    diagnostics.get("p4_factor_count", 0)
                ),
                "nested_iterative_ksp_count": int(
                    diagnostics.get("nested_iterative_ksp_count", 0)
                ),
            }
        p4_live = sum(
            values["p4_factor_count"] for values in by_side.values()
        )
        nested_live = sum(
            values["nested_iterative_ksp_count"]
            for values in by_side.values()
        )
        return {
            "by_side": by_side,
            "live_side_count": sum(
                1
                for values in by_side.values()
                if values["p4_factor_count"] > 0
                or values["nested_iterative_ksp_count"] > 0
            ),
            "live_component_counts": {
                "p4_factor": p4_live,
                "nested_iterative_ksp": nested_live,
            },
            "live_component_count_sum": p4_live + nested_live,
        }

    def sequential_boundary(
        side: str,
        event: str,
    ) -> dict[str, Any]:
        if side_setup_schedule != TASK041_SEQUENTIAL_COMPONENT_SCHEDULE:
            return {
                "side": side,
                "event": event,
                "schedule": side_setup_schedule,
                "status": "not_recorded",
            }
        if event not in {"before_build", "ready", "before_release", "released"}:
            raise ValueError(f"unsupported sequential lifecycle boundary: {event}")
        created_at_boundary: dict[str, int] | None = None
        if event == "ready":
            inverse = side_inverses.get(side)
            if inverse is None:
                raise Task041ModePrepError(
                    f"sequential BAL_H {side} ready boundary has no inverse"
                )
            diagnostics = inverse.diagnostics
            p4_created = int(diagnostics.get("p4_factor_created_count", 0))
            nested_created = int(
                diagnostics.get("nested_ksp_created_count", 0)
            )
            if p4_created != 1 or nested_created != 1:
                failure_evidence["side_lifecycle"] = {
                    "side": side,
                    "event": event,
                    "created_counts": {
                        "p4_factor": p4_created,
                        "nested_iterative_ksp": nested_created,
                    },
                }
                raise Task041ModePrepError(
                    f"sequential BAL_H {side} ready created-count contract failed"
                )
            sequential_created_totals["side_inverse"] += 1
            sequential_created_totals["p4_factor"] += p4_created
            sequential_created_totals["nested_iterative_ksp"] += nested_created
            created_at_boundary = {
                "side_inverse": 1,
                "p4_factor": p4_created,
                "nested_iterative_ksp": nested_created,
            }
        live = sequential_live_snapshot()
        sequential_live_peaks["side_inverse"] = max(
            sequential_live_peaks["side_inverse"], live["live_side_count"]
        )
        sequential_live_peaks["p4_factor"] = max(
            sequential_live_peaks["p4_factor"],
            live["live_component_counts"]["p4_factor"],
        )
        sequential_live_peaks["nested_iterative_ksp"] = max(
            sequential_live_peaks["nested_iterative_ksp"],
            live["live_component_counts"]["nested_iterative_ksp"],
        )
        sequential_live_peaks["owned_component"] = max(
            sequential_live_peaks["owned_component"],
            live["live_component_count_sum"],
        )
        record = {
            "side": side,
            "event": event,
            "schedule": side_setup_schedule,
            "clock": "CLOCK_MONOTONIC",
            "workflow_started_monotonic_seconds": workflow_started_monotonic,
            "live": live,
            "created_total": dict(sequential_created_totals),
        }
        if created_at_boundary is not None:
            record["created_at_boundary"] = created_at_boundary
        if event in {"before_build", "released"} and (
            live["live_side_count"] != 0
            or any(value != 0 for value in live["live_component_counts"].values())
        ):
            record["status"] = "invalid_overlap"
            failure_evidence["side_lifecycle"] = record
            raise Task041ModePrepError(
                f"sequential BAL_H {side} {event} requires no live side components"
            )
        if event in {"ready", "before_release"}:
            ready = live["by_side"].get(side)
            if (
                live["live_side_count"] != 1
                or ready is None
                or ready["p4_factor_count"] != 1
                or ready["nested_iterative_ksp_count"] != 1
                or len(live["by_side"]) != 1
            ):
                record["status"] = "invalid_ready_inventory"
                failure_evidence["side_lifecycle"] = record
                raise Task041ModePrepError(
                    f"sequential BAL_H {side} {event} did not expose one live p4/KSP"
                )
        record["status"] = "measured"
        sequential_lifecycle_boundaries.append(record)
        if event in {"before_build", "before_release"}:
            marker_callback(
                "system_setup_stage",
                {
                    "side": side,
                    "substage": "side_lifecycle",
                    "event": event,
                    "lifecycle_boundary": record,
                },
            )
        return record

    def build_side(side: str, system: Any) -> Any:
        marker_callback(
            f"{side}_factor_setup_begin",
            {
                "source": "build_side_balanced_inverse",
                "max_it": 128,
                "rtol": 1.0e-2,
            },
        )
        inverse = build_side_balanced_inverse(
            system,
            max_it=128,
            rtol=1.0e-2,
            audit_callback=audit_callback(side),
            detailed_timing=detailed_timing,
            record_iteration_history=(
                comparison_mode == TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE
            ),
            performance_profile=(
                transfer_optimization_profile
                if transfer_optimization_profile is not None
                else performance_profile
            ),
            p4_inverse_backend=p4_inverse_backend,
            support_policy=support_policy,
            lifecycle_callback=(
                side_lifecycle_callback(side)
                if detailed_timing
                or side_setup_schedule == TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
                else None
            ),
        )
        side_inverses[side] = inverse
        if comparison_mode == TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE:
            layout_instance_id = shared_layout_instance_id(side)
            layout_evidence_by_side[side] = capture_layout(
                side,
                inverse,
                write=True,
                layout_instance_id=layout_instance_id,
            )
        side_diagnostics_before[side] = dict(inverse.diagnostics)
        p4_diagnostics = side_diagnostics_before[side].get("p4_factor")
        if construction_audit is not None:
            if not isinstance(p4_diagnostics, Mapping):
                raise Task041ModePrepError(
                    f"{side} p4 factor diagnostics are unavailable for backend audit"
                )
            actual_backend = {
                "task041.h1c.p4_exact_factor.v1": "full",
                "task041.h1c.p4_condensed_exact_factor.v1": "cell_condensed",
            }.get(p4_diagnostics.get("schema"))
            owner_transfer = inverse._owner_transfer
            owner_audit = dict(owner_transfer.audit)
            local_transfer_audit = dict(owner_transfer.local_transfer.audit)
            actual_support_policy = owner_audit.get("support_policy")
            actual_construction = (
                "reference_entity_trace_v1"
                if local_transfer_audit.get("reference_entity_trace_v1") is True
                else None
            )
            if actual_backend != p4_inverse_backend:
                raise Task041ModePrepError(
                    f"{side} requested p4 backend {p4_inverse_backend!r}, "
                    f"actual factor schema resolved to {actual_backend!r}"
                )
            if actual_support_policy != support_policy:
                raise Task041ModePrepError(
                    f"{side} requested support policy {support_policy!r}, "
                    f"actual owner policy is {actual_support_policy!r}"
                )
            if (
                p4_inverse_backend == "cell_condensed"
                and actual_construction != "reference_entity_trace_v1"
            ):
                raise Task041ModePrepError(
                    f"{side} cell-condensed transfer lacks reference_entity_trace_v1"
                )
            side_diagnostics_before[side]["task041_backend_contract"] = {
                "requested_backend": p4_inverse_backend,
                "actual_backend": actual_backend,
                "requested_support_policy": support_policy,
                "actual_support_policy": actual_support_policy,
                "requested_construction_audit": construction_audit,
                "actual_construction_audit": actual_construction,
                "factor_schema": p4_diagnostics.get("schema"),
                "factor_rows": {
                    key: p4_diagnostics.get(key)
                    for key in (
                        "full_storage_rows",
                        "active_trace_rows",
                        "interior_rows",
                        "port_rows",
                        "retained_matrix_rows",
                    )
                },
            }
        if rank_numa_stage_callback is not None:
            transfer = inverse._owner_transfer
            rank_numa_stage_callback(
                "p4_ready",
                {
                    "coarse_work": transfer._coarse_work.x.array,
                    "fine_work": transfer._fine_work.x.array,
                },
                {
                    "side": side,
                    "p4_factor": {
                        key: p4_diagnostics.get(key)
                        for key in (
                            "schema",
                            "full_storage_rows",
                            "active_trace_rows",
                            "interior_rows",
                            "port_rows",
                            "retained_matrix_rows",
                        )
                    },
                },
            )
        lifecycle_boundary = None
        if side_setup_schedule == TASK041_SEQUENTIAL_COMPONENT_SCHEDULE:
            lifecycle_boundary = sequential_boundary(
                side,
                "ready",
            )
        marker_callback(
            f"{side}_F_ready",
            {"source": "build_fullspace_physical_dtn_action"},
        )
        marker_callback(
            f"{side}_factor_ready",
            {
                "source": "build_side_balanced_inverse",
                "diagnostics": side_diagnostics_before[side],
                **(
                    {}
                    if lifecycle_boundary is None
                    else {"lifecycle_boundary": lifecycle_boundary}
                ),
            },
        )
        marker_callback(
            f"{side}_woodbury_ready",
            {
                "source": "BAL_H_side_inverse",
                "qualification_method": (
                    "task041_balh_side_inverse_response_fgmres32"
                ),
            },
        )
        return inverse

    def copy_vector(source: PETSc.Vec) -> PETSc.Vec:
        target = source.duplicate()
        source.copy(target)
        return target

    def fill_global_source(vector: PETSc.Vec) -> None:
        first, last = (int(value) for value in vector.getOwnershipRange())
        global_ids = np.arange(first, last, dtype=np.int64)
        vector.getArray()[:] = (
            0.21875
            + 0.0078125 * (global_ids % 17)
            + 1j * (0.09375 + 0.00390625 * (global_ids % 19))
        ).astype(PETSc.ScalarType)
        vector.assemble()

    def vector_difference_norm(left: PETSc.Vec, right: PETSc.Vec) -> float:
        difference = left.duplicate()
        try:
            left.copy(difference)
            difference.axpy(PETSc.ScalarType(-1.0), right)
            return float(difference.norm())
        finally:
            difference.destroy()

    def _raise_common_error(
        message: str,
        classification: str,
        evidence: Mapping[str, Any] | None = None,
    ) -> None:
        error = Task041ModePrepError(message)
        error.failure_classification = classification
        if evidence is not None:
            error.failure_evidence = dict(evidence)
        raise error

    def _common_failure_details(
        exception: BaseException,
        inverse: Any,
    ) -> tuple[str, dict[str, Any]]:
        return _task041_common_failure_details(exception, inverse)

    def shared_layout_instance_id(side: str) -> str:
        existing = layout_instance_ids.get(side)
        if existing is not None:
            return existing
        candidate = None
        if comm.rank == 0:
            seed = (
                f"{audit_path.resolve()}|{side}|"
                "task041.common_layout_equivalence.layout.v1"
            )
            candidate = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        candidate = comm.bcast(candidate, root=0)
        if not isinstance(candidate, str) or not candidate:
            raise Task041ModePrepError(
                f"common-layout {side} instance id was not broadcast"
            )
        layout_instance_ids[side] = candidate
        return candidate

    def variant_binding(side: str, transfer: Any) -> dict[str, Any]:
        raw = transfer.audit.get("variant_bindings")
        if not isinstance(raw, Mapping):
            raise Task041ModePrepError(
                f"common-layout {side} has no transfer variant binding"
            )
        source_module = raw.get("source_module")
        if source_module != transfer.__class__.__module__:
            raise Task041ModePrepError(
                f"common-layout {side} variant source module is not live transfer"
            )
        variants = {
            name: raw.get(name)
            for name in ("legacy", "optimized")
        }
        if any(not isinstance(value, Mapping) for value in variants.values()):
            raise Task041ModePrepError(
                f"common-layout {side} variant function binding is incomplete"
            )
        source_sha = (
            identity.get("source_sha")
            if isinstance(identity, Mapping)
            else None
        )
        if not isinstance(source_sha, str) or len(source_sha) != 40:
            raise Task041ModePrepError(
                f"common-layout {side} runtime source identity is missing"
            )
        return {
            "source_module": str(source_module),
            "source_sha": source_sha,
            "variants": {
                name: dict(value) for name, value in variants.items()
            },
        }

    def capture_layout(
        side: str,
        inverse: Any,
        *,
        write: bool,
        layout_instance_id: str | None = None,
    ) -> dict[str, Any]:
        local: dict[str, Any] | None = None
        local_error: str | None = None

        try:
            transfer = inverse._owner_transfer
            if (
                comparison_mode == TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE
                and side not in variant_bindings_by_side
            ):
                variant_bindings_by_side[side] = variant_binding(side, transfer)
            condensed = inverse._condensed
            side_system = getattr(setup, side)
            operator = inverse.operator
            diagnostics = inverse.diagnostics
            fine_space = transfer.fine_space
            coarse_space = transfer.coarse_space
            side_space = side_system.V
            mesh = fine_space.mesh
            topology = mesh.topology
            topology.create_entity_permutations()
            fine_index_map = fine_space.dofmap.index_map
            coarse_index_map = coarse_space.dofmap.index_map
            outer_communicator = {
                "rank": int(comm.rank),
                "size": int(comm.size),
                "fortran_handle": int(comm.py2f()),
            }
            transfer_comm = transfer.comm
            side_operator_comm = operator.getComm().tompi4py()
            inverse_comm = inverse._comm

            communicators = {
                "outer": outer_communicator,
                "transfer": _task041_communicator_identity(
                    "transfer.comm", transfer_comm
                ),
                "side_operator": _task041_communicator_identity(
                    "side.A.getComm().tompi4py()", side_operator_comm
                ),
                "inverse": _task041_communicator_identity(
                    "inverse._comm", inverse_comm
                ),
                "compare": {
                    "outer_transfer": int(
                        MPI.Comm.Compare(comm, transfer_comm)
                    ),
                    "transfer_side_operator": int(
                        MPI.Comm.Compare(transfer_comm, side_operator_comm)
                    ),
                    "side_operator_inverse": int(
                        MPI.Comm.Compare(side_operator_comm, inverse_comm)
                    ),
                },
            }
            fine_ownership = [
                list(map(int, item)) for item in transfer.fine_ranges
            ]
            coarse_ownership = [
                list(map(int, item)) for item in transfer.coarse_ranges
            ]
            spaces = {
                "side_p6": _task041_space_layout_metadata(
                    "side_system.V", side_space
                ),
                "transfer_fine_p6": _task041_space_layout_metadata(
                    "transfer.fine_space", fine_space
                ),
                "transfer_coarse_p4": _task041_space_layout_metadata(
                    "transfer.coarse_space", coarse_space
                ),
            }
            p4 = inverse._p4_factor
            p4_factor = p4.factor
            factor_ksp = p4_factor.ksp
            p4_factor_ksp = (
                _task041_held_petsc_identity("p4.factor.ksp", factor_ksp)
                if factor_ksp is not None
                else {
                    "name": "p4.factor.ksp",
                    "kind": "PETSc.KSP",
                    "live": False,
                    "handle": None,
                    "reason": "factor_only_storage",
                }
            )
            factor_matrix = p4_factor.factor_matrix
            local = {
                "rank": int(comm.rank),
                "layout_instance_id": (
                    layout_instance_id or layout_instance_ids.get(side)
                ),
                "ownership_range": [
                    int(value) for value in operator.getOwnershipRange()
                ],
                "operator_global_shape": [
                    int(value) for value in operator.getSize()
                ],
                "operator_identity": _task041_held_petsc_identity(
                    "side.A", operator
                ),
                "communicator": outer_communicator,
                "communicators": communicators,
                "ownership": {
                    "operator": [
                        int(value) for value in operator.getOwnershipRange()
                    ],
                    "fine": fine_ownership,
                    "coarse": coarse_ownership,
                    "side_A_global_size": int(operator.getSize()[0]),
                },
                "held_objects": {
                    "side_A": _task041_held_petsc_identity("side.A", operator),
                    "side_inverse": _task041_held_object_metadata(
                        "side_inverse", inverse
                    ),
                    "full_action": _task041_held_object_metadata(
                        "adapter.full_action", inverse._full_action
                    ),
                    "p4_physical_action": _task041_held_object_metadata(
                        "p4.physical_action", p4.physical_action
                    ),
                    "p4_factor": _task041_held_object_metadata("p4_factor", p4),
                    "research_factor": _task041_held_object_metadata(
                        "p4.factor", p4_factor
                    ),
                    "p4_matrix": _task041_held_petsc_identity(
                        "p4.matrix", p4.matrix
                    ),
                    "p4_factor_ksp": p4_factor_ksp,
                    "p4_factor_matrix": (
                        _task041_held_petsc_identity(
                            "p4.factor.factor_matrix", factor_matrix
                        )
                        if factor_matrix is not None
                        else {
                            "name": "p4.factor.factor_matrix",
                            "kind": "PETSc.Mat",
                            "live": False,
                            "handle": None,
                        }
                    ),
                    "nested_ksp": _task041_held_petsc_identity(
                        "adapter.nested_ksp", inverse._ksp
                    ),
                    "h6": _task041_held_object_metadata(
                        "adapter.h6", inverse._h6
                    ),
                    "h6_matrix": _task041_held_petsc_identity(
                        "adapter.h6.matrix", inverse._h6.matrix
                    ),
                    "mesh": _task041_held_object_metadata("mesh", mesh),
                    "side_system": _task041_held_object_metadata(
                        "side_system", side_system
                    ),
                },
                "live_diagnostics": {
                    "side_inverse_live": int(not diagnostics["destroyed"]),
                    "side_inverse_destroyed": bool(diagnostics["destroyed"]),
                    "p4_factor_count": int(diagnostics["p4_factor_count"]),
                    "nested_iterative_ksp_count": int(
                        diagnostics["nested_iterative_ksp_count"]
                    ),
                    "p4_factor_created_count": int(
                        diagnostics["p4_factor_created_count"]
                    ),
                    "nested_ksp_created_count": int(
                        diagnostics["nested_ksp_created_count"]
                    ),
                },
                "transfer_identity": {
                    "schema": transfer.audit["schema"],
                    "fine_global_rows": transfer.audit["fine_global_rows"],
                    "coarse_global_rows": transfer.audit["coarse_global_rows"],
                    "fine_owned_cells": transfer.audit["fine_owned_cells"],
                    "owner_row_authority": transfer.audit["owner_row_authority"],
                    "fine_space_degree": int(
                        fine_space.element.basix_element.degree
                    ),
                    "coarse_space_degree": int(
                        coarse_space.element.basix_element.degree
                    ),
                },
                "variant_binding": variant_bindings_by_side.get(side),
                "dofmaps": {
                    "fine": {
                        "global_size": int(fine_index_map.size_global),
                        "local_size": int(fine_index_map.size_local),
                        "num_ghosts": int(fine_index_map.num_ghosts),
                        "block_size": int(fine_space.dofmap.index_map_bs),
                    },
                    "coarse": {
                        "global_size": int(coarse_index_map.size_global),
                        "local_size": int(coarse_index_map.size_local),
                        "num_ghosts": int(coarse_index_map.num_ghosts),
                        "block_size": int(coarse_space.dofmap.index_map_bs),
                    },
                    "spaces": spaces,
                    "cell_records": _task041_transfer_records_metadata(transfer),
                },
                "mesh_layout": {
                    "geometry": _task041_stream_array_metadata(
                        "mesh.geometry.x", np.asarray(mesh.geometry.x)
                    ),
                    "geometry_dofmap": _task041_stream_array_metadata(
                        "mesh.geometry.dofmap", np.asarray(mesh.geometry.dofmap)
                    ),
                    "cell_permutation_info": _task041_stream_array_metadata(
                        "mesh.topology.cell_permutation_info",
                        np.asarray(topology.get_cell_permutation_info()),
                    ),
                    "topology_dimension": int(topology.dim),
                },
                "mpc_layout": {
                    "objects": {
                        "fine": _task041_held_object_metadata(
                            "fine_floquet.mpc", transfer.fine_floquet.mpc
                        ),
                        "coarse": _task041_held_object_metadata(
                            "coarse_floquet.mpc", transfer.coarse_floquet.mpc
                        ),
                    },
                    "communicator_source": (
                        "MPC communicator is not directly exposed; use the captured "
                        "fine/coarse space and mesh association with transfer.comm"
                    ),
                    "fine": _task041_mpc_layout_metadata(
                        "fine_floquet.mpc", transfer.fine_floquet.mpc
                    ),
                    "coarse": _task041_mpc_layout_metadata(
                        "coarse_floquet.mpc", transfer.coarse_floquet.mpc
                    ),
                },
                "layout_arrays": [
                    _task041_stream_array_metadata(
                        "fine_owned_slaves", transfer._fine_slaves
                    ),
                    _task041_stream_array_metadata(
                        "coarse_owned_slaves", transfer._coarse_slaves
                    ),
                    _task041_stream_array_metadata(
                        "owned_active_original_dofs",
                        condensed.trace_constraints.owned_active_original_dofs,
                    ),
                    _task041_stream_array_metadata(
                        "coarse_mpc_slaves", transfer._coarse_mpc_slaves
                    ),
                    _task041_stream_array_metadata(
                        "dual_flat_slaves", transfer._dual_flat_slaves
                    ),
                    _task041_stream_array_metadata(
                        "dual_flat_masters", transfer._dual_flat_masters
                    ),
                    _task041_stream_array_metadata(
                        "dual_conjugated_coefficients",
                        transfer._dual_conjugated_coefficients,
                    ),
                ],
                "transfer_communicator": communicators["transfer"],
            }
        except Exception as exc:  # noqa: BLE001 - synchronize all rank evidence
            local_error = f"{type(exc).__name__}: {exc}"
        gathered = comm.allgather({"local": local, "error": local_error})
        errors = [
            f"rank_{rank}:{row['error']}"
            for rank, row in enumerate(gathered)
            if row.get("error") is not None
        ]
        if errors:
            failure = {"side": side, "errors": errors}
            failure_evidence.setdefault("common_layout_equivalence", {})[
                side
            ] = failure
            _raise_common_error(
                f"common-layout {side} evidence is incomplete",
                "PAIRING_SETUP_FAILURE",
                failure,
            )
        by_rank = sorted(
            [row["local"] for row in gathered], key=lambda row: int(row["rank"])
        )
        canonical = json.dumps(
            _jsonable(by_rank), sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        payload = {
            "schema": "task041.common_layout_equivalence.layout.v1",
            "side": side,
            "comm_size": int(comm.size),
            "layout_instance_id": (
                layout_instance_id or layout_instance_ids.get(side)
            ),
            "layout_identity_sha256": hashlib.sha256(canonical).hexdigest(),
            "by_rank": by_rank,
            "ownership_semantics": "rank-local existing PETSc ownership; no full-vector gather",
        }
        if write:
            layout_root = audit_path.with_name("common_layout_equivalence")
            if comm.rank == 0:
                layout_root.mkdir(parents=True, exist_ok=True)
            comm.Barrier()
            _write_rank0_json(
                layout_root / f"{side}_layout.json",
                payload,
                comm,
            )
        return payload

    def common_vector_inventory(
        vectors: Mapping[str, PETSc.Vec],
    ) -> list[dict[str, Any]]:
        inventory = []
        for name, vector in vectors.items():
            values = np.asarray(vector.getArray(readonly=True))
            inventory.append(
                {
                    "name": name,
                    "owned_entries": int(values.size),
                    "dtype": str(values.dtype),
                    "payload_bytes": int(values.size * values.dtype.itemsize),
                    "payload_status": "derived",
                    "scope": "rank_local_PETSc_Vec_owned_view",
                    "native_workspace_bytes": "unknown",
                }
            )
        return inventory

    def common_stage_marker(
        event: str,
        entry_value: Mapping[str, Any],
        *,
        group: str,
        variant: str | None = None,
        vectors: Mapping[str, PETSc.Vec] | None = None,
        **detail: Any,
    ) -> None:
        marker_callback(
            "system_setup_stage",
            {
                "side": str(entry_value["side"]),
                "substage": "common_layout_equivalence",
                "group": group,
                "event": event,
                "ordinal": int(entry_value["ordinal"]),
                "audit_index": int(entry_value["audit_index"]),
                "formal_column": int(entry_value["formal_column"]),
                "variant": variant,
                "clock": "CLOCK_MONOTONIC",
                "workflow_started_monotonic_seconds": (
                    workflow_started_monotonic
                ),
                "payload_inventory": common_vector_inventory(vectors or {}),
                **detail,
            },
        )

    def common_pc_action_check(
        side: str,
        inverse: Any,
        rhs: PETSc.Vec,
        entry: Mapping[str, Any],
    ) -> dict[str, Any]:
        owner = inverse._owner_transfer
        p4_source: PETSc.Vec | None = None
        full_rhs: PETSc.Vec | None = None

        def owned_sha(name: str, vector: PETSc.Vec) -> str:
            array = np.asarray(vector.getArray(readonly=True))
            return str(_task041_stream_array_metadata(name, array)["sha256"])

        def input_hashes(
            stage: str, vectors: Mapping[str, PETSc.Vec]
        ) -> dict[str, str]:
            return {
                name: owned_sha(f"{side}.{stage}.{name}", vector)
                for name, vector in vectors.items()
            }

        def persist_c3_failure(
            entry_value: Mapping[str, Any],
            classification: str,
            evidence: Mapping[str, Any],
        ) -> None:
            payload = {
                "schema": "task041.common_layout_equivalence.c3_failure.v1",
                "side": side,
                "entry": {
                    "ordinal": int(entry_value["ordinal"]),
                    "audit_index": int(entry_value["audit_index"]),
                    "formal_column": int(entry_value["formal_column"]),
                },
                "failure_classification": classification,
                "evidence": _jsonable(dict(evidence)),
            }
            failure_evidence.setdefault(
                "common_layout_equivalence", {}
            ).setdefault("c3", []).append(payload)
            if comm.rank == 0:
                with audit_path.with_name(
                    "common_layout_equivalence_c3_failures.jsonl"
                ).open("a", encoding="utf-8") as stream:
                    stream.write(
                        json.dumps(_jsonable(payload), sort_keys=True) + "\n"
                    )
                    stream.flush()
            comm.Barrier()

        def last_action_facts() -> dict[str, Any]:
            return {
                "coupling_last_apply_facts": _jsonable(
                    dict(inverse._coupling.last_apply_facts)
                ),
                "p4_last_solve": _jsonable(
                    dict(inverse._p4_factor.diagnostics["last_solve"])
                ),
                "scope": "last_C3_action_only",
            }

        def apply_pc() -> PETSc.Vec:
            target = inverse.operator.createVecLeft()
            try:
                inverse._apply_balanced_pc(rhs, target)
                return target
            except BaseException:
                target.destroy()
                raise

        def apply_variant(
            group: str,
            variant: str,
            apply_action: Callable[[], PETSc.Vec],
            inputs: Mapping[str, PETSc.Vec],
        ) -> tuple[
            PETSc.Vec,
            dict[str, str],
            dict[str, str],
            bool,
            dict[str, Any] | None,
        ]:
            before = input_hashes(f"{group}.{variant}.before", inputs)
            common_stage_marker(
                "variant_apply_begin",
                entry,
                group=f"C3_{group}",
                variant=variant,
                vectors=inputs,
            )
            output: PETSc.Vec | None = None
            local_error: dict[str, Any] | None = None
            try:
                with inverse.variant_context(variant):
                    output = apply_action()
            except Exception as exc:  # noqa: BLE001 - preserve rank-local apply cause
                classification, failure_details = _common_failure_details(
                    exc, inverse
                )
                local_error = {
                    "type": type(exc).__name__,
                    "message": str(exc),
                    "classification": classification,
                    **failure_details,
                }
            any_failed = bool(
                comm.allreduce(local_error is not None, op=MPI.LOR)
            )
            errors_by_rank = comm.allgather(local_error)
            if any_failed:
                classification = (
                    "NUMERICAL_GATE_FAIL"
                    if any(
                        isinstance(error, Mapping)
                        and error.get("classification") == "NUMERICAL_GATE_FAIL"
                        for error in errors_by_rank
                    )
                    else "PAIRING_SETUP_FAILURE"
                )
                evidence = {
                    "group": group,
                    "variant": variant,
                    "errors_by_rank": errors_by_rank,
                    "input_before": before,
                }
                if output is not None:
                    output.destroy()
                common_stage_marker(
                    "variant_apply_end",
                    entry,
                    group=f"C3_{group}",
                    variant=variant,
                    vectors=inputs,
                    status="failed",
                    failure_classification=classification,
                )
                persist_c3_failure(entry, classification, evidence)
                _raise_common_error(
                    f"C3 {side} {group}/{variant} apply failed",
                    classification,
                    evidence,
                )
            action_facts: dict[str, Any] | None = None
            facts_error: dict[str, Any] | None = None
            if group == "PC":
                try:
                    action_facts = last_action_facts()
                except Exception as exc:  # noqa: BLE001 - preserve live getter cause
                    facts_error = {
                        "type": type(exc).__name__,
                        "message": str(exc),
                        "classification": "PAIRING_SETUP_FAILURE",
                    }
            facts_failed = bool(
                comm.allreduce(facts_error is not None, op=MPI.LOR)
            )
            if facts_failed:
                facts_by_rank = comm.allgather(facts_error)
                evidence = {
                    "group": group,
                    "variant": variant,
                    "errors_by_rank": facts_by_rank,
                    "input_before": before,
                }
                if output is not None:
                    output.destroy()
                common_stage_marker(
                    "variant_apply_end",
                    entry,
                    group=f"C3_{group}",
                    variant=variant,
                    vectors=inputs,
                    status="failed",
                    failure_classification="PAIRING_SETUP_FAILURE",
                )
                persist_c3_failure(entry, "PAIRING_SETUP_FAILURE", evidence)
                _raise_common_error(
                    f"C3 {side} {group}/{variant} facts are incomplete",
                    "PAIRING_SETUP_FAILURE",
                    evidence,
                )
            if output is None:
                _raise_common_error(
                    f"C3 {side} {group}/{variant} returned no output",
                    "PAIRING_SETUP_FAILURE",
                )
            after = input_hashes(f"{group}.{variant}.after", inputs)
            unchanged = bool(
                comm.allreduce(
                    all(before[key] == after[key] for key in before),
                    op=MPI.LAND,
                )
            )
            common_stage_marker(
                "variant_apply_end",
                entry,
                group=f"C3_{group}",
                variant=variant,
                vectors={**inputs, "output": output},
                status="measured" if unchanged else "input_changed",
                input_unchanged=unchanged,
            )
            if not unchanged:
                evidence = {
                    "group": group,
                    "variant": variant,
                    "input_before": before,
                    "input_after": after,
                    "input_unchanged": unchanged,
                    "audit": dict(inverse.diagnostics.get("last_apply", {})),
                }
                output.destroy()
                persist_c3_failure(entry, "PAIRING_SETUP_FAILURE", evidence)
                _raise_common_error(
                    f"C3 {side} {group}/{variant} changed its input",
                    "PAIRING_SETUP_FAILURE",
                    evidence,
                )
            return output, before, after, unchanged, action_facts

        def action_pair(
            name: str,
            apply_action: Callable[[], PETSc.Vec],
            threshold: float,
            inputs: Mapping[str, PETSc.Vec],
        ) -> dict[str, Any]:
            legacy_output: PETSc.Vec | None = None
            optimized_output: PETSc.Vec | None = None
            input_records: dict[str, dict[str, Any]] = {}
            group_status = "failed"
            common_stage_marker(
                "begin",
                entry,
                group=f"C3_{name}",
                vectors=inputs,
            )
            try:
                (
                    legacy_output,
                    legacy_before,
                    legacy_after,
                    legacy_unchanged,
                    legacy_facts,
                ) = apply_variant(
                    name, "legacy", apply_action, inputs
                )
                input_records["legacy"] = {
                    "before": legacy_before,
                    "after": legacy_after,
                    "unchanged": legacy_unchanged,
                    **(
                        {"last_action_facts": legacy_facts}
                        if legacy_facts is not None
                        else {}
                    ),
                }
                (
                    optimized_output,
                    optimized_before,
                    optimized_after,
                    optimized_unchanged,
                    optimized_facts,
                ) = apply_variant(
                    name, "optimized", apply_action, inputs
                )
                input_records["optimized"] = {
                    "before": optimized_before,
                    "after": optimized_after,
                    "unchanged": optimized_unchanged,
                    **(
                        {"last_action_facts": optimized_facts}
                        if optimized_facts is not None
                        else {}
                    ),
                }
                difference = vector_difference_norm(
                    legacy_output, optimized_output
                )
                legacy_norm = float(legacy_output.norm())
                optimized_norm = float(optimized_output.norm())
                denominator = max(legacy_norm, optimized_norm)
                relative = (
                    difference / denominator
                    if denominator > 0.0
                    else (0.0 if difference == 0.0 else None)
                )
                local_finite = bool(
                    np.isfinite(difference)
                    and np.isfinite(legacy_norm)
                    and np.isfinite(optimized_norm)
                    and np.all(
                        np.isfinite(legacy_output.getArray(readonly=True))
                    )
                    and np.all(
                        np.isfinite(optimized_output.getArray(readonly=True))
                    )
                )
                finite = bool(comm.allreduce(local_finite, op=MPI.LAND))
                result = {
                    "name": name,
                    "absolute": float(difference),
                    "relative": relative,
                    "legacy_norm": legacy_norm,
                    "optimized_norm": optimized_norm,
                    "threshold": threshold,
                    "input_hashes": input_records,
                    "input_unchanged": bool(
                        all(
                            record["unchanged"]
                            for record in input_records.values()
                        )
                    ),
                    "finite": finite,
                }
                local_pass = bool(
                    finite
                    and relative is not None
                    and relative <= threshold
                    and all(
                        record["unchanged"]
                        for record in input_records.values()
                    )
                )
                pass_value = bool(comm.allreduce(local_pass, op=MPI.LAND))
                result["pass"] = pass_value
                if not pass_value:
                    classification = (
                        "NUMERICAL_GATE_FAIL"
                        if not finite
                        else "ACTION_EQUIVALENCE_FAIL"
                    )
                    evidence = {
                        "group": name,
                        "result": result,
                        "input_records": input_records,
                    }
                    persist_c3_failure(entry, classification, evidence)
                    _raise_common_error(
                        f"C3 {side} {name} action comparison failed",
                        classification,
                        evidence,
                    )
                group_status = "passed"
                return result
            finally:
                if optimized_output is not None:
                    optimized_output.destroy()
                if legacy_output is not None:
                    legacy_output.destroy()
                common_stage_marker(
                    "end",
                    entry,
                    group=f"C3_{name}",
                    status=group_status,
                    vectors={},
                )

        try:
            p4_source = inverse._p4_factor.physical_action.matrix.createVecRight()
            first, last = (
                int(value) for value in p4_source.getOwnershipRange()
            )
            ids = np.arange(first, last, dtype=np.int64)
            p4_source.getArray()[:] = (
                0.125
                + 0.00390625 * (ids % 17)
                + 1j * (0.0625 + 0.001953125 * (ids % 19))
            ).astype(PETSc.ScalarType)
            p4_source.getArray()[owner._coarse_slaves] = 0.0
            del ids
            p4_source.assemble()
            p_result = action_pair(
                "P",
                lambda: owner.apply_primal(p4_source),
                1.0e-11,
                {"rhs": rhs, "p4_source": p4_source},
            )
            p4_source.destroy()
            p4_source = None
            full_rhs = inverse._full_action.matrix.createVecRight()
            inject_active_residual_to_full_p6(
                inverse._condensed, rhs, full_rhs
            )
            ph_result = action_pair(
                "PH",
                lambda: owner.apply_adjoint(full_rhs),
                1.0e-11,
                {"rhs": rhs, "full_rhs": full_rhs},
            )
            full_rhs.destroy()
            full_rhs = None
            pc_result = action_pair(
                "PC",
                apply_pc,
                1.0e-8,
                {"rhs": rhs},
            )
            input_unchanged = bool(
                comm.allreduce(
                    bool(
                        p_result["input_unchanged"]
                        and ph_result["input_unchanged"]
                        and pc_result["input_unchanged"]
                    ),
                    op=MPI.LAND,
                )
            )
            finite = bool(
                comm.allreduce(
                    np.all(np.isfinite(rhs.getArray(readonly=True))),
                    op=MPI.LAND,
                )
            )
            pass_value = bool(
                finite
                and input_unchanged
                and p_result["pass"] is True
                and ph_result["pass"] is True
                and pc_result["pass"] is True
            )
            return {
                "side": side,
                "entry": {
                    "ordinal": int(entry["ordinal"]),
                    "audit_index": int(entry["audit_index"]),
                    "formal_column": int(entry["formal_column"]),
                },
                "rhs_source": "first_real_modal_rhs",
                "variants": ["legacy", "optimized"],
                "P": p_result,
                "PH": ph_result,
                "PC": pc_result,
                "input_hashes": {
                    "P": p_result["input_hashes"],
                    "PH": ph_result["input_hashes"],
                    "PC": pc_result["input_hashes"],
                },
                "rhs_unchanged": input_unchanged,
                "finite": finite,
                "pass": pass_value,
                "solve": "direct_P_PH_and_BAL_H_PC_actions_no_KSPSolve",
            }
        finally:
            if full_rhs is not None:
                full_rhs.destroy()
            if p4_source is not None:
                p4_source.destroy()

    def probe_side(side: str, inverse: Any, system: Any) -> None:
        mode_count = int(setup.coupling.mode_count_per_direction)
        owned_vectors: list[PETSc.Vec] = []
        try:
            positive_values = np.zeros(2 * mode_count, dtype=np.complex128)
            positive_values[0] = 1.0 + 0.25j
            positive_modal_rhs = modal_coupling_action(
                side, setup.coupling, positive_values
            )
            owned_vectors.append(positive_modal_rhs)

            negative_values = np.zeros(2 * mode_count, dtype=np.complex128)
            negative_values[mode_count] = -0.35 + 0.15j
            negative_modal_rhs = modal_coupling_action(
                side, setup.coupling, negative_values
            )
            owned_vectors.append(negative_modal_rhs)

            external_rhs = copy_vector(system.b)
            owned_vectors.append(external_rhs)
            general_state = system.A.createVecRight()
            owned_vectors.append(general_state)
            first, last = map(int, general_state.getOwnershipRange())
            seed_values = np.asarray(
                (
                    0.125 + 0.03125j,
                    -0.0625 + 0.09375j,
                    0.1875 - 0.046875j,
                    -0.109375 - 0.078125j,
                ),
                dtype=PETSc.ScalarType,
            )
            general_state.getArray()[:] = np.asarray(
                seed_values[
                    np.mod(
                        np.arange(first, last, dtype=np.int64), seed_values.size
                    )
                ],
                dtype=PETSc.ScalarType,
            )
            general_state.assemble()
            general_action = system.A.createVecLeft()
            owned_vectors.append(general_action)
            system.A.mult(general_state, general_action)
            general_residual = copy_vector(external_rhs)
            owned_vectors.append(general_residual)
            general_residual.axpy(
                PETSc.ScalarType(-1.0), general_action
            )
            rhs_items = (
                ("modal_traction_positive", positive_modal_rhs),
                ("modal_traction_negative", negative_modal_rhs),
                ("external_physical_rhs", external_rhs),
                ("general_residual", general_residual),
            )
            for label, rhs in rhs_items:
                record_start = len(probe_records[side])
                target = system.A.createVecLeft()
                try:
                    inverse.apply(rhs, target)
                    if (
                        rank_numa_stage_callback is not None
                        and label == "modal_traction_positive"
                    ):
                        rank_numa_stage_callback(
                            "first_response",
                            {"rhs": rhs, "target": target},
                            {
                                "side": side,
                                "label": label,
                                "last_apply": dict(
                                    inverse.diagnostics.get("last_apply", {})
                                ),
                            },
                        )
                except BaseException:
                    audit = dict(inverse.diagnostics.get("last_apply", {}))
                    marker_callback(
                        "candidate_cost_probe",
                        {"side": side, "label": label, "audit": audit},
                    )
                    raise
                finally:
                    target.destroy()
                if len(probe_records[side]) != record_start + 1:
                    raise RuntimeError(
                        f"BAL_H {side} cost probe did not receive an apply audit"
                    )
                marker_callback(
                    "candidate_cost_probe",
                    {
                        "side": side,
                        "label": label,
                        "audit": dict(probe_records[side][-1]),
                    },
                )
        finally:
            probe_active[side] = False
            for vector in owned_vectors:
                vector.destroy()

    def cost_probe_summary() -> dict[str, Any]:
        sampled_count = len(sampled_column_contract["columns"])
        internal_count = 2 * int(setup.coupling.mode_count_per_direction)
        modal_build_calls = internal_count + 2 * sampled_count

        def stats(values: list[float]) -> dict[str, Any]:
            if not values:
                return {
                    "count": 0,
                    "min_seconds": None,
                    "mean_seconds": None,
                    "max_seconds": None,
                }
            return {
                "count": len(values),
                "min_seconds": float(min(values)),
                "mean_seconds": float(sum(values) / len(values)),
                "max_seconds": float(max(values)),
            }

        side_summary: dict[str, Any] = {}
        for side, records in probe_records.items():
            nonzero_elapsed_values = [
                float(record["elapsed_seconds"])
                for record in records
                if isinstance(record.get("elapsed_seconds"), (int, float))
                and np.isfinite(float(record["elapsed_seconds"]))
                and isinstance(record.get("rhs_norm"), (int, float))
                and np.isfinite(float(record["rhs_norm"]))
                and float(record["rhs_norm"]) > 0.0
            ]
            zero_rhs_count = sum(
                1
                for record in records
                if isinstance(record.get("rhs_norm"), (int, float))
                and np.isfinite(float(record["rhs_norm"]))
                and float(record["rhs_norm"]) == 0.0
            )
            measured = stats(nonzero_elapsed_values)
            if nonzero_elapsed_values:
                estimates = {
                    "optimistic_seconds": float(
                        measured["min_seconds"] * modal_build_calls
                    ),
                    "central_seconds": float(
                        measured["mean_seconds"] * modal_build_calls
                    ),
                    "conservative_seconds": float(
                        measured["max_seconds"] * modal_build_calls
                    ),
                }
            else:
                estimates = {
                    "optimistic_seconds": None,
                    "central_seconds": None,
                    "conservative_seconds": None,
                }
            side_summary[side] = {
                "probe_call_count": len(records),
                "measured_nonzero_rhs_elapsed": measured,
                "zero_rhs_excluded_count": zero_rhs_count,
                "probe_records": [dict(record) for record in records],
                "derived_modal_schur_seconds": estimates,
            }
        optimistic_values = [
            value["derived_modal_schur_seconds"]["optimistic_seconds"]
            for value in side_summary.values()
            if value["derived_modal_schur_seconds"]["optimistic_seconds"]
            is not None
        ]
        central_values = [
            value["derived_modal_schur_seconds"]["central_seconds"]
            for value in side_summary.values()
            if value["derived_modal_schur_seconds"]["central_seconds"] is not None
        ]
        conservative_values = [
            value["derived_modal_schur_seconds"]["conservative_seconds"]
            for value in side_summary.values()
            if value["derived_modal_schur_seconds"]["conservative_seconds"]
            is not None
        ]
        all_sides_measured = len(optimistic_values) == len(side_summary)
        local_consumer_elapsed = float(elapsed_seconds) + (
            time.monotonic() - helper_started
        )
        consumer_elapsed = float(
            comm.allreduce(local_consumer_elapsed, op=MPI.MAX)
        )
        remaining_budget = max(float(timeout_seconds) - consumer_elapsed, 0.0)
        summary = {
            "status": "derived",
            "time_stop_enforced": not disable_time_stop,
            "time_stop_override": (
                "user_authorized_single_candidate_time_override"
                if disable_time_stop
                else None
            ),
            "rhs_contract": (
                "modal_traction_positive, modal_traction_negative, "
                "external_physical_rhs, general_residual"
            ),
            "side": side_summary,
            "actual_probe_call_count": sum(
                int(value["probe_call_count"]) for value in side_summary.values()
            ),
            "modal_schur_work_contract": {
                "full_column_count_per_side": internal_count,
                "sampled_column_count_per_side": sampled_count,
                "sampled_repeat_builds_per_side": 2,
                "full_builds_per_side": 1,
                "planned_inverse_calls_per_side": modal_build_calls,
                "planned_inverse_calls_total": 2 * modal_build_calls,
                "batch_size": 32,
            },
            "estimate": {
                "status": "derived" if all_sides_measured else "not_measured",
                "optimistic_seconds_total": (
                    float(sum(optimistic_values)) if all_sides_measured else None
                ),
                "central_seconds_total": (
                    float(sum(central_values)) if all_sides_measured else None
                ),
                "conservative_seconds_total": (
                    float(sum(conservative_values)) if all_sides_measured else None
                ),
                "uncertainty": {
                    "method": "nonzero probe elapsed min-to-max representative range",
                    "source": "four fixed side RHS measurements per side",
                    "strict_bounds": False,
                    "assumption": (
                        "the observed min/mean/max per-RHS costs represent the "
                        "planned modal columns and repeated builds"
                    ),
                },
            },
            "consumer_elapsed_seconds_before_modal_schur": consumer_elapsed,
            "remaining_timeout_seconds": remaining_budget,
        }
        if (
            all_sides_measured
            and not disable_time_stop
            and float(
                summary["estimate"]["optimistic_seconds_total"]
            )
            > remaining_budget
        ):
            summary["status"] = "SETUP_COST_BLOCKED"
            summary["block"] = {
                "basis": (
                    "representative optimistic estimate exceeds remaining budget"
                ),
                "optimistic_seconds_total": summary["estimate"][
                    "optimistic_seconds_total"
                ],
                "remaining_timeout_seconds": remaining_budget,
                "strict_bound": False,
            }
            _write_rank0_json(
                audit_path.with_name("candidate_setup_cost.json"), summary, comm
            )
            raise Task041ModePrepError(
                "BAL_H modal Schur setup optimistic estimate exceeds remaining phase budget"
            )
        _write_rank0_json(
            audit_path.with_name("candidate_setup_cost.json"), summary, comm
        )
        return summary

    def release_before_recovery() -> Mapping[str, Any]:
        nonlocal context, operator_context, operator, released
        nonlocal global_source, global_source_before
        nonlocal global_action_before, global_rhs_before
        context_status = "not_created"
        operator_context_status = "not_created"
        operator_status = "not_created"
        if context is not None and not bool(getattr(context, "_destroyed", False)):
            context.destroy()
            context_status = (
                "destroyed"
                if bool(getattr(context, "_destroyed", False))
                else "destroy_failed"
            )
        elif context is not None:
            context_status = "destroyed"
        context = None
        if operator_context is not None:
            operator_context.destroy()
            operator_context_status = (
                "destroyed"
                if bool(getattr(operator_context, "_destroyed", True))
                else "destroy_failed"
            )
            operator_context = None
        if operator is not None:
            operator.destroy()
            operator_status = "destroyed"
            operator = None
        for vector in (
            global_source,
            global_source_before,
            global_action_before,
            global_rhs_before,
        ):
            if vector is not None:
                vector.destroy()
        global_source = None
        global_source_before = None
        global_action_before = None
        global_rhs_before = None
        for side, rhs in common_first_rhs_by_side.items():
            if rhs is not None:
                rhs.destroy()
                common_first_rhs_by_side[side] = None
            common_first_entry_by_side[side] = None
        for side, inverse in side_inverses.items():
            inverse.destroy()
            side_diagnostics_after[side] = dict(inverse.diagnostics)
            marker_callback(
                f"{side}_construction_cleanup",
                {
                    "source": "SideBalancedInverse.destroy",
                    "diagnostics": side_diagnostics_after[side],
                    "p4_factor_count": side_diagnostics_after[side].get(
                        "p4_factor_count"
                    ),
                    "nested_iterative_ksp_count": side_diagnostics_after[side].get(
                        "nested_iterative_ksp_count"
                    ),
                },
            )
        cleanup = collective_heap_cleanup(comm)
        released = True
        factor_counts = {
            side: int(diagnostics.get("p4_factor_count", 0))
            for side, diagnostics in side_diagnostics_after.items()
        }
        objects_destroyed = bool(
            side_diagnostics_after
            and all(
                diagnostics.get("destroyed") is True
                for diagnostics in side_diagnostics_after.values()
            )
        )
        factor_cleanup_pass = bool(
            factor_counts
            and all(count == 0 for count in factor_counts.values())
        )
        component_cleanup_pass = bool(
            context_status in {"destroyed", "not_created"}
            and operator_context_status in {"destroyed", "not_created"}
            and operator_status in {"destroyed", "not_created"}
            and objects_destroyed
            and factor_cleanup_pass
            and all(
                int(diagnostics.get("nested_iterative_ksp_count", 0)) == 0
                for diagnostics in side_diagnostics_after.values()
            )
        )
        return {
            "factor_count_after_cleanup": factor_counts,
            "factor_cleanup_pass": factor_cleanup_pass,
            "actions_destroyed": objects_destroyed,
            "side_inverses_destroyed": objects_destroyed,
            "component_cleanup_pass": component_cleanup_pass,
            "component_cleanup": {
                "status": "candidate_owned_components_destroyed",
                "owned": {
                    "modal_schur_context": context_status,
                    "outer_operator_context": operator_context_status,
                    "outer_operator": operator_status,
                    "side_python_pc_and_ksp": objects_destroyed
                    and all(
                        int(diagnostics.get("nested_iterative_ksp_count", 0)) == 0
                        for diagnostics in side_diagnostics_after.values()
                    ),
                    "full_action": objects_destroyed,
                    "p4_factor": factor_cleanup_pass,
                    "h6": objects_destroyed,
                    "owner_transfer": objects_destroyed,
                },
                "borrowed_retained_for_recovery": [
                    "setup.bottom",
                    "setup.top",
                    "setup.coupling",
                    "side_systems.mesh_and_final_MPC",
                ],
            },
            "collective_heap_cleanup": cleanup,
            "side_diagnostics_after_destroy": {
                side: dict(diagnostics)
                for side, diagnostics in side_diagnostics_after.items()
            },
        }

    def admit_side(side: str) -> Mapping[str, Any]:
        inverse = side_inverses[side]
        if comparison_mode == TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE:
            first_rhs = common_first_rhs_by_side[side]
            first_entry = common_first_entry_by_side[side]
            if first_rhs is None or first_entry is None:
                raise Task041ModePrepError(
                    f"common-layout {side} first real RHS is missing"
                )
            audit = dict(inverse.admission_audit(identity=identity))
            pc_audit = common_pc_action_check(
                side, inverse, first_rhs, first_entry
            )
            audit = {
                "schema": "task041.common_layout_equivalence.admission.v1",
                "side": side,
                "admission": audit,
                "balanced_pc": pc_audit,
                "pass": bool(
                    audit.get("pass") is True
                    and pc_audit.get("pass") is True
                ),
            }
        else:
            audit = inverse.admission_audit(identity=identity)
        admission_audits[side] = audit
        partial_payload = {
            "schema": "task041.h1g2b2b.candidate_side_admission.v1",
            "identity": dict(identity) if identity is not None else {},
            "sides": dict(admission_audits),
            "pass": all(
                bool(value.get("pass"))
                for value in admission_audits.values()
                if isinstance(value, Mapping)
            ),
            "status": "partial_sequential_component",
            "side_setup_schedule": side_setup_schedule,
        }
        _write_rank0_json(
            audit_path.with_name("balh_admission_audit.json"),
            partial_payload,
            comm,
        )
        marker_callback(
            f"{side}_admission_audit",
            {"audit": audit, "pass": audit.get("pass") is True},
        )
        if audit.get("pass") is not True:
            failure_evidence["admission_audit"] = partial_payload
            raise Task041ModePrepError(
                f"BAL_H {side} admission audit failed; raw audit was persisted"
            )
        return audit

    def global_identity_check(label: str) -> dict[str, Any]:
        if (
            operator is None
            or global_source is None
            or global_source_before is None
            or global_action_before is None
            or global_rhs_before is None
        ):
            raise RuntimeError("global identity references are not available")
        global_action_after = operator.createVecLeft()
        global_rhs_after = None
        try:
            operator.mult(global_source, global_action_after)
            global_rhs_after = layout.pack(
                setup.bottom.b,
                setup.top.b,
                internal_modal_rhs_correction(setup.coupling),
            )
            action_absolute = vector_difference_norm(
                global_action_before, global_action_after
            )
            rhs_absolute = vector_difference_norm(
                global_rhs_before, global_rhs_after
            )
            source_absolute = vector_difference_norm(
                global_source_before, global_source
            )
            action_relative = action_absolute / max(
                float(global_action_before.norm()), 1.0e-30
            )
            rhs_relative = rhs_absolute / max(
                float(global_rhs_before.norm()), 1.0e-30
            )
            source_relative = source_absolute / max(
                float(global_source_before.norm()), 1.0e-30
            )
        finally:
            global_action_after.destroy()
            if global_rhs_after is not None:
                global_rhs_after.destroy()
        return {
            "label": label,
            "action_absolute": action_absolute,
            "action_relative": action_relative,
            "rhs_absolute": rhs_absolute,
            "rhs_relative": rhs_relative,
            "source_unchanged_absolute": source_absolute,
            "source_unchanged_relative": source_relative,
            "threshold": 1.0e-12,
            "pass": bool(
                action_relative <= 1.0e-12
                and rhs_relative <= 1.0e-12
                and source_relative <= 1.0e-12
            ),
        }

    def release_side(side: str) -> Mapping[str, Any]:
        inverse = side_inverses.get(side)
        if inverse is None:
            return {"status": "not_created", "side": side}
        try:
            inverse.destroy()
            diagnostics = dict(inverse.diagnostics)
        except BaseException as exc:
            failure_evidence["side_lifecycle"] = {
                "side": side,
                "event": "released",
                "status": "release_exception",
                "exception_type": type(exc).__name__,
                "exception": str(exc),
                "diagnostics": dict(inverse.diagnostics),
            }
            raise
        release_gate = {
            "destroyed": diagnostics.get("destroyed") is True,
            "p4_factor_count": diagnostics.get("p4_factor_count"),
            "nested_iterative_ksp_count": diagnostics.get(
                "nested_iterative_ksp_count"
            ),
        }
        release_gate["pass"] = bool(
            release_gate["destroyed"]
            and isinstance(release_gate["p4_factor_count"], int)
            and not isinstance(release_gate["p4_factor_count"], bool)
            and release_gate["p4_factor_count"] == 0
            and isinstance(release_gate["nested_iterative_ksp_count"], int)
            and not isinstance(
                release_gate["nested_iterative_ksp_count"], bool
            )
            and release_gate["nested_iterative_ksp_count"] == 0
        )
        if not release_gate["pass"]:
            failure_evidence["side_lifecycle"] = {
                "side": side,
                "event": "released",
                "status": "release_inventory_invalid",
                "release_gate": release_gate,
                "diagnostics": diagnostics,
            }
            raise Task041ModePrepError(
                f"sequential BAL_H {side} release inventory failed"
            )
        inverse = None
        side_inverses.pop(side, None)
        side_diagnostics_after[side] = diagnostics
        heap_cleanup = collective_heap_cleanup(comm)
        lifecycle_boundary = sequential_boundary(
            side,
            "released",
        )
        record = {
            **sequential_side_records.get(side, {}),
            "side": side,
            "status": "destroyed",
            "release_gate": release_gate,
            "heap_cleanup": heap_cleanup,
            "lifecycle_boundary": lifecycle_boundary,
        }
        sequential_side_records[side] = record
        marker_callback(
            f"{side}_construction_cleanup",
            {
                "source": "SideBalancedInverse.destroy",
                "substage": "side_construction",
                "event": "released",
                "owner": "SideBalancedInverse",
                "release_gate": release_gate,
                "lifecycle_boundary": lifecycle_boundary,
                "diagnostics": diagnostics,
            },
        )
        return record

    def representative_apply_gate(
        entry: Mapping[str, Any],
        audit: Mapping[str, Any],
        *,
        evidence_name: str = "representative_rhs",
        failure_classification_prefix: str = "REPRESENTATIVE_RHS",
    ) -> None:
        failures: list[str] = []
        reason = audit.get("reason")
        if not isinstance(reason, int) or isinstance(reason, bool) or reason <= 0:
            failures.append("reason_not_positive")
        if audit.get("ksp_positive") is not True:
            failures.append("ksp_not_positive")
        if audit.get("explicit_true_target_reached") is not True:
            failures.append("explicit_true_target_not_reached")
        relative_residual = audit.get("relative_residual")
        relative_residual_numeric = (
            isinstance(relative_residual, (int, float))
            and not isinstance(relative_residual, bool)
        )
        relative_gate_failure = bool(
            relative_residual_numeric
            and (
                not np.isfinite(relative_residual)
                or relative_residual < 0.0
                or relative_residual > 1.0e-2
            )
        )
        if (
            not relative_residual_numeric
            or relative_gate_failure
        ):
            failures.append("relative_residual_not_within_1e-2")
        rhs_norm = audit.get("rhs_norm")
        rhs_norm_valid = bool(
            isinstance(rhs_norm, (int, float))
            and not isinstance(rhs_norm, bool)
            and np.isfinite(rhs_norm)
            and rhs_norm > 0.0
        )
        if (
            not rhs_norm_valid
        ):
            failures.append("rhs_not_finite_nonzero")
        residual_norm = audit.get("residual_norm")
        residual_norm_numeric = bool(
            isinstance(residual_norm, (int, float))
            and not isinstance(residual_norm, bool)
        )
        residual_gate_failure = bool(
            residual_norm_numeric
            and (
                not np.isfinite(residual_norm)
                or residual_norm < 0.0
            )
        )
        recomputed_relative: float | None = None
        recomputed_gate_failure = False
        if (
            not residual_norm_numeric
            or residual_gate_failure
        ):
            failures.append("residual_not_finite_nonnegative")
        elif rhs_norm_valid:
            recomputed_relative = residual_norm / rhs_norm
            recomputed_gate_failure = bool(
                not np.isfinite(recomputed_relative)
                or recomputed_relative < 0.0
                or recomputed_relative > 1.0e-2
            )
            if recomputed_gate_failure:
                failures.append("recomputed_relative_residual_not_within_1e-2")
        if audit.get("ksp_max_it") != 128 or audit.get("ksp_rtol") != 1.0e-2:
            failures.append("ksp_contract_mismatch")
        counts = audit.get("counts")
        delta = counts.get("delta") if isinstance(counts, Mapping) else None
        count_nonpositive = False
        count_protocol_failure = False
        for name in ("pc", "Q", "H6", "A6", "P", "PH_audit", "p4_backsolve"):
            value = delta.get(name) if isinstance(delta, Mapping) else None
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                failures.append(f"{name}_count_missing")
                count_protocol_failure = True
            elif value == 0:
                failures.append(f"{name}_count_not_positive")
                count_nonpositive = True
        if failures:
            reason_numeric = isinstance(reason, int) and not isinstance(reason, bool)
            reason_gate_failure = bool(reason_numeric and reason <= 0)
            ksp_positive = audit.get("ksp_positive")
            explicit_target = audit.get("explicit_true_target_reached")
            contract_failure = bool(
                not reason_numeric
                or (ksp_positive is not True and ksp_positive is not False)
                or (explicit_target is not True and explicit_target is not False)
                or not rhs_norm_valid
                or (
                    "relative_residual_not_within_1e-2" in failures
                    and not relative_residual_numeric
                )
                or (
                    "residual_not_finite_nonnegative" in failures
                    and not residual_norm_numeric
                )
                or "ksp_contract_mismatch" in failures
                or count_protocol_failure
            )
            numerical_gate_failure = bool(
                not contract_failure
                and (
                    reason_gate_failure
                    or ksp_positive is False
                    or explicit_target is False
                    or relative_gate_failure
                    or residual_gate_failure
                    or recomputed_gate_failure
                    or count_nonpositive
                )
            )
            evidence = {
                "entry": dict(entry),
                "audit": _jsonable(dict(audit)),
                "failures": failures,
                "key": {
                    "ordinal": int(entry["ordinal"]),
                    "side": str(entry["side"]),
                    "branch": str(entry["branch"]),
                    "audit_index": int(entry["audit_index"]),
                    "formal_column": int(entry["formal_column"]),
                    "branch_ordinal": int(entry["branch_ordinal"]),
                },
                "actual": {
                    "reason": reason,
                    "ksp_positive": ksp_positive,
                    "explicit_true_target_reached": explicit_target,
                    "relative_residual": relative_residual,
                    "rhs_norm": rhs_norm,
                    "residual_norm": residual_norm,
                    "recomputed_relative_residual": recomputed_relative,
                },
                "limits": {
                    "relative_residual": 1.0e-2,
                    "recomputed_relative_residual": 1.0e-2,
                },
            }
            if failure_classification_prefix == "COMMON_LAYOUT_EQUIVALENCE":
                classification = (
                    "NUMERICAL_GATE_FAIL"
                    if numerical_gate_failure
                    else "PAIRING_SETUP_FAILURE"
                )
            else:
                classification = (
                    f"{failure_classification_prefix}_NUMERICAL_GATE"
                    if numerical_gate_failure
                    else f"{failure_classification_prefix}_CONTRACT_FAILURE"
                )
            evidence["failure_classification"] = classification
            failure_evidence.setdefault(evidence_name, {})[
                str(entry["ordinal"])
            ] = evidence
            error = Task041ModePrepError(
                "representative RHS apply gate failed for "
                f"ordinal {entry['ordinal']}: {', '.join(failures)}"
            )
            error.failure_classification = classification
            error.failure_evidence = dict(evidence)
            raise error

    def run_representative_rhs_probe(
        entries_override: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if representative_rhs_contract is None:
            raise RuntimeError("representative RHS contract is missing")
        entries = (
            list(representative_rhs_contract["entries"])
            if entries_override is None
            else list(entries_override)
        )
        records: list[dict[str, Any]] = []
        mode_count = int(setup.coupling.mode_count_per_direction)
        if mode_count != int(representative_rhs_contract["mode_count"]):
            raise Task041ModePrepError(
                "representative RHS mode count does not match the setup"
            )
        for entry in entries:
            side = str(entry["side"])
            branch = str(entry["branch"])
            ordinal = int(entry["ordinal"])
            formal_column = int(entry["formal_column"])
            modal = np.zeros(2 * mode_count, dtype=PETSc.ScalarType)
            modal[formal_column] = PETSc.ScalarType(1.0)
            rhs: PETSc.Vec | None = None
            response: PETSc.Vec | None = None
            rhs_array: np.ndarray | None = None
            response_array: np.ndarray | None = None
            audit_start = len(representative_records[side])
            audit_phase[side] = "representative_rhs"
            representative_context[side] = {
                "representative_ordinal": ordinal,
                "source_audit_index": int(entry["audit_index"]),
                "formal_column": formal_column,
                "branch_ordinal": int(entry["branch_ordinal"]),
            }
            try:
                rhs = modal_coupling_action(side, setup.coupling, modal)
                response = getattr(setup, side).A.createVecLeft()
                try:
                    side_inverses[side].apply(rhs, response)
                except BaseException:
                    if len(representative_records[side]) > audit_start:
                        failure_evidence.setdefault("representative_rhs", {})[
                            str(ordinal)
                        ] = {
                            "entry": dict(entry),
                            "audit": _jsonable(
                                representative_records[side][-1]
                            ),
                        }
                    raise
                if len(representative_records[side]) != audit_start + 1:
                    raise Task041ModePrepError(
                        f"representative RHS {ordinal} did not receive one apply audit"
                    )
                apply_audit = dict(representative_records[side][-1])
                representative_apply_gate(entry, apply_audit)
                ownership = tuple(int(value) for value in response.getOwnershipRange())
                shard_directory = (
                    audit_path.parent
                    / "representative_rhs"
                    / f"{ordinal:02d}_{side}_{branch}"
                )
                response_array = np.asarray(response.getArray(readonly=True))
                rhs_array = np.asarray(rhs.getArray(readonly=True))
                response_bytes = memoryview(response_array).cast("B")
                try:
                    rhs_bytes = memoryview(rhs_array).cast("B")
                    try:
                        response_sha256 = hashlib.sha256(response_bytes).hexdigest()
                        rhs_sha256 = hashlib.sha256(rhs_bytes).hexdigest()
                    finally:
                        rhs_bytes.release()
                finally:
                    response_bytes.release()
                packet = write_packet(
                    shard_directory,
                    response_array,
                    rhs_array,
                    identity={
                        "schema": "task041.representative_rhs.response_identity.v1",
                        "source_sha": identity["source_sha"],
                        "probe_manifest_sha256": representative_rhs_contract["sha256"],
                        "packet_manifest_sha256": representative_rhs_contract[
                            "packet_binding"
                        ]["packet_manifest_sha256"],
                        "ordinal": ordinal,
                        "side": side,
                        "formal_column": formal_column,
                        "branch_ordinal": int(entry["branch_ordinal"]),
                    },
                    metadata={
                        "scope": "representative_rhs",
                        "entry": dict(entry),
                        "source_function": (
                            "src/solvers/hybrid_fem_modal_schur_direct.py:"
                            "modal_coupling_action"
                        ),
                        "rhs_array_name": "rhs",
                        "response_array_name": "solution",
                        "dtype": str(
                            response_array.dtype
                        ),
                        "owned_rhs_sha256": rhs_sha256,
                        "owned_response_sha256": response_sha256,
                        "apply_audit": _jsonable(apply_audit),
                    },
                    ownership_range=ownership,
                    comm=comm,
                )
                response_manifest_path = Path(packet["manifest"])
                response_manifest = json.loads(
                    response_manifest_path.read_text(encoding="utf-8")
                )
                response_shard = next(
                    shard
                    for shard in response_manifest["shards"]
                    if int(shard["rank"]) == int(comm.rank)
                )
                local_record = {
                    "rank": int(comm.rank),
                    "ownership_range": list(ownership),
                    "local_size": int(response.getLocalSize()),
                    "dtype": str(response_array.dtype),
                    "owned_rhs_sha256": rhs_sha256,
                    "owned_response_sha256": response_sha256,
                    "packet_manifest_sha256": representative_rhs_contract[
                        "packet_binding"
                    ]["packet_manifest_sha256"],
                    "packet_shard_path": response_shard["path"],
                    "packet_shard_sha256": response_shard["sha256"],
                    "response_packet_manifest_sha256": packet["manifest_sha256"],
                }
                rank_records = comm.gather(local_record, root=0)
                record = None
                if comm.rank == 0:
                    record = {
                        "ordinal": ordinal,
                        "side": side,
                        "branch": branch,
                        "audit_index": int(entry["audit_index"]),
                        "formal_column": formal_column,
                        "branch_ordinal": int(entry["branch_ordinal"]),
                        "status": "completed",
                        "audit": _jsonable(apply_audit),
                        "artifact": packet,
                        "rank_shards": sorted(
                            rank_records or [], key=lambda row: int(row["rank"])
                        ),
                    }
                record = comm.bcast(record, root=0)
                records.append(record)
                marker_callback(
                    "system_setup_stage",
                    {
                        "name": "representative_rhs",
                        "ordinal": ordinal,
                        "side": side,
                        "formal_column": formal_column,
                        "status": "completed",
                    },
                )
            finally:
                representative_context[side] = None
                response_array = None
                rhs_array = None
                if response is not None:
                    response.destroy()
                if rhs is not None:
                    rhs.destroy()
        return {
            "scope": "representative_rhs",
            "status": "completed",
            "expected_count": len(entries),
            "completed_count": len(records),
            "entries": records,
            "source_manifest": {
                "path": representative_rhs_contract["path"],
                "sha256": representative_rhs_contract["sha256"],
                "scope": representative_rhs_contract["scope"],
            },
            "source_audit": dict(representative_rhs_contract["source_audit"]),
            "packet_binding": dict(representative_rhs_contract["packet_binding"]),
            "full_formal": "not_run",
        }

    def write_common_variant_packet(
        entry: Mapping[str, Any],
        variant: str,
        response: PETSc.Vec,
        rhs: PETSc.Vec,
        apply_audit: Mapping[str, Any],
        layout_sha: str,
        layout_epoch: str,
        rhs_before_sha: str,
        rhs_after_sha: str,
        rhs_unchanged: bool,
        *,
        diagnostic_only: bool = False,
    ) -> dict[str, Any]:
        side = str(entry["side"])
        ordinal = int(entry["ordinal"])
        branch = str(entry["branch"])
        ownership = tuple(int(value) for value in response.getOwnershipRange())
        response_array = np.asarray(response.getArray(readonly=True))
        rhs_array = np.asarray(rhs.getArray(readonly=True))
        response_view = memoryview(response_array).cast("B")
        rhs_view = memoryview(rhs_array).cast("B")
        try:
            response_sha256 = hashlib.sha256(response_view).hexdigest()
            rhs_sha256 = hashlib.sha256(rhs_view).hexdigest()
        finally:
            rhs_view.release()
            response_view.release()
        shard_directory = (
            audit_path.parent
            / "common_layout_equivalence"
            / f"{ordinal:02d}_{side}_{branch}"
            / variant
        )
        packet = write_packet(
            shard_directory,
            response_array,
            rhs_array,
            identity={
                "schema": "task041.common_layout_equivalence.response_identity.v1",
                "scope": "representative_rhs",
                "comparison_mode": "common_layout_equivalence",
                "pairing_scope": "same_live_layout",
                "run_layout_epoch": layout_epoch,
                "layout_instance_id": layout_epoch,
                "source_sha": identity["source_sha"],
                "probe_manifest_sha256": representative_rhs_contract["sha256"],
                "packet_manifest_sha256": representative_rhs_contract[
                    "packet_binding"
                ]["packet_manifest_sha256"],
                "layout_identity_sha256": layout_sha,
                "ordinal": ordinal,
                "side": side,
                "formal_column": int(entry["formal_column"]),
                "branch_ordinal": int(entry["branch_ordinal"]),
                "variant": variant,
            },
            metadata={
                "scope": "representative_rhs",
                "comparison_mode": "common_layout_equivalence",
                "pairing_scope": "same_live_layout",
                "run_layout_epoch": layout_epoch,
                "layout_instance_id": layout_epoch,
                "entry": dict(entry),
                "variant": variant,
                "source_function": (
                    "src/solvers/hybrid_fem_modal_schur_direct.py:"
                    "modal_coupling_action"
                ),
                "rhs_array_name": "rhs",
                "response_array_name": "solution",
                "dtype": str(response_array.dtype),
                "owned_rhs_sha256": rhs_sha256,
                "owned_response_sha256": response_sha256,
                "layout_identity_sha256": layout_sha,
                "apply_audit": _jsonable(dict(apply_audit)),
                "diagnostic_only": bool(diagnostic_only),
            },
            ownership_range=ownership,
            comm=comm,
            allow_nonfinite_diagnostic=diagnostic_only,
        )
        packet["diagnostic_only"] = bool(diagnostic_only)
        response_manifest_path = Path(packet["manifest"])
        response_manifest = json.loads(
            response_manifest_path.read_text(encoding="utf-8")
        )
        response_shard = next(
            shard
            for shard in response_manifest["shards"]
            if int(shard["rank"]) == int(comm.rank)
        )
        local_record = {
            "rank": int(comm.rank),
            "ownership_range": list(ownership),
            "local_size": int(response.getLocalSize()),
            "dtype": str(response_array.dtype),
            "owned_rhs_sha256": rhs_sha256,
            "owned_response_sha256": response_sha256,
            "rhs_before_sha256": rhs_before_sha,
            "rhs_after_sha256": rhs_after_sha,
            "rhs_unchanged": bool(rhs_unchanged),
            "packet_manifest_sha256": representative_rhs_contract[
                "packet_binding"
            ]["packet_manifest_sha256"],
            "packet_shard_path": response_shard["path"],
            "packet_shard_sha256": response_shard["sha256"],
            "response_packet_manifest_sha256": packet["manifest_sha256"],
        }
        rank_records = comm.gather(local_record, root=0)
        return {
            "variant": variant,
            "artifact": packet,
            "rank_shards": (
                sorted(rank_records or [], key=lambda row: int(row["rank"]))
                if comm.rank == 0
                else None
            ),
        }

    def compare_common_responses(
        side_operator: PETSc.Mat,
        rhs: PETSc.Vec,
        legacy_response: PETSc.Vec,
        optimized_response: PETSc.Vec,
        *,
        diagnostic_directory: Path,
        diagnostic_identity: Mapping[str, Any],
    ) -> dict[str, Any]:
        delta = optimized_response.duplicate()
        a_delta = side_operator.createVecLeft()
        try:
            optimized_response.copy(delta)
            delta.axpy(PETSc.ScalarType(-1.0), legacy_response)
            delta_norm = float(delta.norm())
            legacy_norm = float(legacy_response.norm())
            optimized_norm = float(optimized_response.norm())
            rhs_norm = float(rhs.norm())
            side_operator.mult(delta, a_delta)
            a_delta_norm = float(a_delta.norm())
            delta_metadata = _task041_stream_array_metadata(
                "common_layout_equivalence.response_delta",
                np.asarray(delta.getArray(readonly=True)),
            )
            action_delta_metadata = _task041_stream_array_metadata(
                "common_layout_equivalence.action_delta",
                np.asarray(a_delta.getArray(readonly=True)),
            )
            x_denominator = max(legacy_norm, optimized_norm)
            e_x = (
                delta_norm / x_denominator
                if x_denominator > 0.0
                else (0.0 if delta_norm == 0.0 else None)
            )
            e_A = (
                a_delta_norm / rhs_norm
                if rhs_norm > 0.0
                else (0.0 if a_delta_norm == 0.0 else None)
            )
            finite = bool(
                np.isfinite(
                    [
                        delta_norm,
                        legacy_norm,
                        optimized_norm,
                        rhs_norm,
                        a_delta_norm,
                    ]
                ).all()
                and (e_x is None or np.isfinite(e_x))
                and (e_A is None or np.isfinite(e_A))
                and np.all(
                    np.isfinite(delta.getArray(readonly=True))
                )
                and np.all(
                    np.isfinite(a_delta.getArray(readonly=True))
                )
            )
            finite = bool(comm.allreduce(finite, op=MPI.LAND))
            zero_solution_denominator = x_denominator == 0.0
            zero_rhs_denominator = rhs_norm == 0.0
            action_packet = write_packet(
                diagnostic_directory / "action_delta",
                np.asarray(delta.getArray(readonly=True)),
                np.asarray(a_delta.getArray(readonly=True)),
                identity={
                    **dict(diagnostic_identity),
                    "schema": (
                        "task041.common_layout_equivalence."
                        "comparison_diagnostic.v1"
                    ),
                    "kind": "response_and_action_delta",
                },
                metadata={
                    "solution_array_name": "response_delta",
                    "rhs_array_name": "action_delta",
                    "action_difference_definition": "A_s.mult(response_delta)",
                    "response_delta": delta_metadata,
                    "action_delta": action_delta_metadata,
                },
                ownership_range=tuple(
                    int(value) for value in delta.getOwnershipRange()
                ),
                comm=comm,
                allow_nonfinite_diagnostic=True,
            )
            side_operator.mult(legacy_response, a_delta)
            rhs.copy(delta)
            delta.axpy(PETSc.ScalarType(-1.0), a_delta)
            legacy_residual_norm = float(delta.norm())
            side_operator.mult(optimized_response, a_delta)
            a_delta.scale(PETSc.ScalarType(-1.0))
            a_delta.axpy(PETSc.ScalarType(1.0), rhs)
            optimized_residual_norm = float(a_delta.norm())
            residual_finite = bool(
                np.isfinite(legacy_residual_norm)
                and np.isfinite(optimized_residual_norm)
                and np.all(np.isfinite(delta.getArray(readonly=True)))
                and np.all(np.isfinite(a_delta.getArray(readonly=True)))
            )
            finite = bool(
                comm.allreduce(finite and residual_finite, op=MPI.LAND)
            )
            residual_packet = write_packet(
                diagnostic_directory / "residual_pair",
                np.asarray(delta.getArray(readonly=True)),
                np.asarray(a_delta.getArray(readonly=True)),
                identity={
                    **dict(diagnostic_identity),
                    "schema": (
                        "task041.common_layout_equivalence."
                        "comparison_diagnostic.v1"
                    ),
                    "kind": "legacy_and_optimized_residual",
                },
                metadata={
                    "solution_array_name": "legacy_residual",
                    "rhs_array_name": "optimized_residual",
                    "definition": {
                        "legacy": "b-side_A.mult(legacy_response)",
                        "optimized": "b-side_A.mult(optimized_response)",
                    },
                    "legacy_residual_norm": legacy_residual_norm,
                    "optimized_residual_norm": optimized_residual_norm,
                },
                ownership_range=tuple(
                    int(value) for value in delta.getOwnershipRange()
                ),
                comm=comm,
                allow_nonfinite_diagnostic=True,
            )
            # The residual pair is already closed on disk.  Only now reuse the
            # second scratch vector for the independently measured difference;
            # it is not the negated action difference from the first packet.
            a_delta.axpy(PETSc.ScalarType(-1.0), delta)
            residual_difference_norm = float(a_delta.norm())
            residual_denominator = max(
                legacy_residual_norm, optimized_residual_norm
            )
            residual_relative = (
                residual_difference_norm / residual_denominator
                if residual_denominator > 0.0
                else (
                    0.0 if residual_difference_norm == 0.0 else None
                )
            )
            residual_difference_finite = bool(
                np.isfinite(residual_difference_norm)
                and np.all(np.isfinite(a_delta.getArray(readonly=True)))
            )
            finite = bool(
                comm.allreduce(
                    finite and residual_difference_finite,
                    op=MPI.LAND,
                )
            )
            local_pass = bool(
                finite
                and e_x is not None
                and e_A is not None
                and e_x <= 1.0e-8
                and e_A <= 1.0e-8
            )
            pass_value = bool(comm.allreduce(local_pass, op=MPI.LAND))
            return {
                "operator_scope": "side_A",
                "delta_definition": "optimized_response - legacy_response",
                "e_x_absolute": delta_norm,
                "e_x": e_x,
                "e_A_absolute": a_delta_norm,
                "e_A": e_A,
                "response_norms": {
                    "legacy": legacy_norm,
                    "optimized": optimized_norm,
                    "denominator": x_denominator,
                },
                "rhs_norm": rhs_norm,
                "zero_solution_denominator": zero_solution_denominator,
                "zero_rhs_denominator": zero_rhs_denominator,
                "a_delta_definition": "side_A.mult(delta, scratch)",
                "diagnostic_arrays": {
                    "response_delta": delta_metadata,
                    "action_delta": action_delta_metadata,
                    "storage": {
                        "response_and_action": action_packet,
                        "residual_pair": residual_packet,
                    },
                },
                "residual_norms": {
                    "legacy": legacy_residual_norm,
                    "optimized": optimized_residual_norm,
                    "denominator": residual_denominator,
                },
                "residual_difference_norm": residual_difference_norm,
                "residual_difference_relative": residual_relative,
                "residual_difference_definition": (
                    "r_optimized-r_legacy, computed from two saved residuals"
                ),
                "diagnostic_packets": {
                    "response_and_action": action_packet,
                    "residual_pair": residual_packet,
                },
                "threshold_e_x": 1.0e-8,
                "threshold_e_A": 1.0e-8,
                "finite": finite,
                "pass": pass_value,
            }
        finally:
            a_delta.destroy()
            delta.destroy()

    def run_common_layout_equivalence_probe(
        entries_override: Sequence[Mapping[str, Any]],
        side: str,
    ) -> dict[str, Any]:
        if representative_rhs_contract is None:
            raise RuntimeError("common-layout comparison requires the RHS contract")
        entries = list(entries_override)
        if len(entries) != 4:
            raise Task041ModePrepError(
                f"common_layout_equivalence requires four {side} entries"
            )
        initial_layout = layout_evidence_by_side.get(side)
        if not isinstance(initial_layout, Mapping):
            raise Task041ModePrepError(f"common-layout {side} layout is missing")
        records: list[dict[str, Any]] = []
        mode_count = int(setup.coupling.mode_count_per_direction)
        layout_epoch = initial_layout.get("layout_instance_id")
        if not isinstance(layout_epoch, str) or not layout_epoch:
            _raise_common_error(
                f"common-layout {side} has no shared layout instance id",
                "PAIRING_SETUP_FAILURE",
            )

        def owned_rhs_sha(rhs: PETSc.Vec, stage: str) -> str:
            array = np.asarray(rhs.getArray(readonly=True))
            return str(
                _task041_stream_array_metadata(f"{side}.{stage}.rhs", array)["sha256"]
            )

        def persist_pair(record: Mapping[str, Any]) -> None:
            if comm.rank != 0:
                return
            path = audit_path.with_name(
                "common_layout_equivalence_pairs.jsonl"
            )
            with path.open("a", encoding="utf-8") as stream:
                json.dump(
                    _jsonable(dict(record)),
                    stream,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                stream.write("\n")

        for entry in entries:
            ordinal = int(entry["ordinal"])
            formal_column = int(entry["formal_column"])
            before_layout: Mapping[str, Any] | None = None
            after_layout: Mapping[str, Any] | None = None
            rhs: PETSc.Vec | None = None
            first_response: PETSc.Vec | None = None
            second_response: PETSc.Vec | None = None
            variant_records: dict[str, dict[str, Any]] = {}
            audits: dict[str, Mapping[str, Any]] = {}
            persisted = False
            diagnostic_started = False
            diagnostic_finished = False
            active_variant: str | None = None
            variant_finished = True
            try:
                common_stage_marker(
                    "pair_begin",
                    entry,
                    group="PAIR",
                )
                before_layout = capture_layout(
                    side, side_inverses[side], write=False
                )
                common_stage_marker(
                    "layout_before",
                    entry,
                    group="PAIR",
                    layout_identity_sha256=before_layout[
                        "layout_identity_sha256"
                    ],
                )
                if (
                    before_layout["layout_identity_sha256"]
                    != initial_layout["layout_identity_sha256"]
                ):
                    _raise_common_error(
                        f"common-layout {side} changed before ordinal {ordinal}",
                        "PAIRING_SETUP_FAILURE",
                        {
                            "side": side,
                            "ordinal": ordinal,
                            "before_layout": before_layout,
                            "initial_layout_sha256": initial_layout[
                                "layout_identity_sha256"
                            ],
                        },
                    )
                if ordinal == int(entries[0]["ordinal"]):
                    rhs = common_first_rhs_by_side[side]
                    if rhs is None:
                        _raise_common_error(
                            f"common-layout {side} first RHS is missing",
                            "PAIRING_SETUP_FAILURE",
                        )
                else:
                    modal = np.zeros(2 * mode_count, dtype=PETSc.ScalarType)
                    modal[formal_column] = PETSc.ScalarType(1.0)
                    rhs = modal_coupling_action(side, setup.coupling, modal)
                first_response = getattr(setup, side).A.createVecLeft()
                second_response = getattr(setup, side).A.createVecLeft()
                first_variant = "legacy" if ordinal % 2 == 0 else "optimized"
                second_variant = (
                    "optimized" if first_variant == "legacy" else "legacy"
                )
                rhs_before_sha = owned_rhs_sha(rhs, "before_apply")
                for variant, response in (
                    (first_variant, first_response),
                    (second_variant, second_response),
                ):
                    active_variant = variant
                    variant_finished = False
                    variant_rhs_before_sha = owned_rhs_sha(
                        rhs, f"before_{variant}"
                    )
                    common_stage_marker(
                        "variant_apply_begin",
                        entry,
                        group="VARIANT_APPLY",
                        variant=variant,
                        vectors={"rhs": rhs, "response": response},
                        rhs_before_sha256=variant_rhs_before_sha,
                    )
                    audit_start = len(representative_records[side])
                    audit_phase[side] = "common_layout_equivalence"
                    representative_context[side] = {
                        "comparison_mode": "common_layout_equivalence",
                        "comparison_variant": variant,
                        "representative_ordinal": ordinal,
                        "source_audit_index": int(entry["audit_index"]),
                        "formal_column": formal_column,
                        "branch_ordinal": int(entry["branch_ordinal"]),
                    }
                    try:
                        with side_inverses[side].variant_context(variant):
                            side_inverses[side].apply(rhs, response)
                    except BaseException as exc:
                        classification, failure_details = _common_failure_details(
                            exc, side_inverses[side]
                        )
                        failed_audit = (
                            dict(representative_records[side][-1])
                            if len(representative_records[side])
                            > audit_start
                            else None
                        )
                        failure_evidence = dict(failure_details)
                        failure_evidence["audit"] = _jsonable(failed_audit)
                        rhs_after_sha: str | None = None
                        rhs_unchanged = False
                        if rhs is not None:
                            try:
                                rhs_after_sha = owned_rhs_sha(
                                    rhs, f"failure_after_{variant}"
                                )
                                rhs_unchanged = bool(
                                    comm.allreduce(
                                        rhs_after_sha == rhs_before_sha,
                                        op=MPI.LAND,
                                    )
                                )
                            except Exception as hash_error:  # noqa: BLE001 - keep partial evidence
                                failure_evidence["rhs_hash_error"] = {
                                    "type": type(hash_error).__name__,
                                    "message": str(hash_error),
                                }
                        apply_record = (
                            failed_audit
                            if isinstance(failed_audit, Mapping)
                            else {
                                "status": "failed",
                                "failure_classification": classification,
                                "error": failure_evidence["cause"],
                            }
                        )
                        variant_records[variant] = {
                            "variant": variant,
                            "status": "failed",
                            "failure_classification": classification,
                            "rhs_before_sha256": variant_rhs_before_sha,
                            "rhs_after_sha256": rhs_after_sha,
                            "rhs_unchanged": rhs_unchanged,
                            "error": {
                                "type": type(exc).__name__,
                                "message": str(exc),
                            },
                            "audit": _jsonable(failed_audit),
                            "failure_evidence": _jsonable(failure_evidence),
                        }
                        try:
                            variant_records[variant]["diagnostic_packet"] = (
                                write_common_variant_packet(
                                    entry,
                                    variant,
                                    response,
                                    rhs,
                                    apply_record,
                                    str(before_layout["layout_identity_sha256"]),
                                    layout_epoch,
                                    variant_rhs_before_sha,
                                    rhs_after_sha or "",
                                    rhs_unchanged,
                                    diagnostic_only=True,
                                )
                            )
                        except Exception as packet_error:  # noqa: BLE001 - keep partial evidence
                            variant_records[variant]["diagnostic_packet_error"] = {
                                "type": type(packet_error).__name__,
                                "message": str(packet_error),
                            }
                            failure_evidence["diagnostic_packet_error"] = {
                                "type": type(packet_error).__name__,
                                "message": str(packet_error),
                            }
                        exc.failure_classification = classification
                        exc.failure_evidence = failure_evidence
                        common_stage_marker(
                            "variant_apply_end",
                            entry,
                            group="VARIANT_APPLY",
                            variant=variant,
                            vectors={"rhs": rhs, "response": response},
                            status="failed",
                            error_type=type(exc).__name__,
                            failure_classification=classification,
                        )
                        variant_finished = True
                        raise
                    if len(representative_records[side]) != audit_start + 1:
                        raise Task041ModePrepError(
                            f"common RHS {ordinal}/{variant} did not receive one apply audit"
                        )
                    rhs_after_sha = owned_rhs_sha(rhs, f"after_{variant}")
                    rhs_unchanged = bool(
                        comm.allreduce(
                            rhs_after_sha == rhs_before_sha,
                            op=MPI.LAND,
                        )
                    )
                    audit = dict(representative_records[side][-1])
                    audits[variant] = audit
                    variant_records[variant] = {
                        "variant": variant,
                        "status": "applied",
                        "rhs_before_sha256": variant_rhs_before_sha,
                        "rhs_after_sha256": rhs_after_sha,
                        "rhs_unchanged": rhs_unchanged,
                        "audit": _jsonable(audit),
                    }
                    try:
                        representative_apply_gate(
                            entry,
                            audit,
                            evidence_name="common_layout_equivalence",
                            failure_classification_prefix=(
                                "COMMON_LAYOUT_EQUIVALENCE"
                            ),
                        )
                    except Task041ModePrepError as exc:
                        classification, failure_details = _common_failure_details(
                            exc, side_inverses[side]
                        )
                        failure_packet_evidence = dict(failure_details)
                        failure_packet_evidence["audit"] = _jsonable(audit)
                        variant_records[variant].update(
                            {
                                "status": "failed",
                                "failure_classification": classification,
                                "failure_evidence": _jsonable(
                                    failure_packet_evidence
                                ),
                            }
                        )
                        try:
                            variant_records[variant]["diagnostic_packet"] = (
                                write_common_variant_packet(
                                    entry,
                                    variant,
                                    response,
                                    rhs,
                                    audit,
                                    str(before_layout["layout_identity_sha256"]),
                                    layout_epoch,
                                    variant_rhs_before_sha,
                                    rhs_after_sha,
                                    rhs_unchanged,
                                    diagnostic_only=True,
                                )
                            )
                        except Exception as packet_error:  # noqa: BLE001 - keep partial evidence
                            variant_records[variant]["diagnostic_packet_error"] = {
                                "type": type(packet_error).__name__,
                                "message": str(packet_error),
                            }
                            failure_packet_evidence["diagnostic_packet_error"] = {
                                "type": type(packet_error).__name__,
                                "message": str(packet_error),
                            }
                        exc.failure_classification = classification
                        exc.failure_evidence = failure_packet_evidence
                        raise
                    if not rhs_unchanged:
                        variant_records[variant]["status"] = "failed"
                        variant_records[variant][
                            "failure_classification"
                        ] = "PAIRING_SETUP_FAILURE"
                        _raise_common_error(
                            f"common RHS {ordinal}/{variant} changed during apply",
                            "PAIRING_SETUP_FAILURE",
                            {
                                "side": side,
                                "ordinal": ordinal,
                                "variant": variant,
                                "rhs_before_sha256": rhs_before_sha,
                                "rhs_after_sha256": rhs_after_sha,
                            },
                        )
                    variant_records[variant].update(
                        write_common_variant_packet(
                            entry,
                            variant,
                            response,
                            rhs,
                            audit,
                            str(before_layout["layout_identity_sha256"]),
                            layout_epoch,
                            variant_rhs_before_sha,
                            rhs_after_sha,
                            rhs_unchanged,
                        )
                    )
                    common_stage_marker(
                        "variant_apply_end",
                        entry,
                        group="VARIANT_APPLY",
                        variant=variant,
                        vectors={"rhs": rhs, "response": response},
                        status="measured",
                        rhs_before_sha256=variant_rhs_before_sha,
                        rhs_after_sha256=rhs_after_sha,
                        rhs_unchanged=rhs_unchanged,
                    )
                    variant_finished = True
                after_layout = capture_layout(
                    side, side_inverses[side], write=False
                )
                common_stage_marker(
                    "layout_after",
                    entry,
                    group="PAIR",
                    layout_identity_sha256=after_layout[
                        "layout_identity_sha256"
                    ],
                )
                layout_pass = (
                    after_layout["layout_identity_sha256"]
                    == before_layout["layout_identity_sha256"]
                )
                common_layout_rechecks[side].append(
                    {
                        "ordinal": ordinal,
                        "before_layout_identity_sha256": before_layout[
                            "layout_identity_sha256"
                        ],
                        "after_layout_identity_sha256": after_layout[
                            "layout_identity_sha256"
                        ],
                        "pass": layout_pass,
                    }
                )
                if not layout_pass:
                    raise Task041ModePrepError(
                        f"common-layout {side} layout changed at ordinal {ordinal}"
                    )
                legacy_response = (
                    first_response
                    if first_variant == "legacy"
                    else second_response
                )
                optimized_response = (
                    first_response
                    if first_variant == "optimized"
                    else second_response
                )
                common_stage_marker(
                    "diagnostic_begin",
                    entry,
                    group="PAIR_DIAGNOSTIC",
                    vectors={
                        "rhs": rhs,
                        "legacy_response": legacy_response,
                        "optimized_response": optimized_response,
                    },
                )
                diagnostic_started = True
                comparison = compare_common_responses(
                    side_inverses[side].operator,
                    rhs,
                    legacy_response,
                    optimized_response,
                    diagnostic_directory=(
                        audit_path.parent
                        / "common_layout_equivalence"
                        / f"{ordinal:02d}_{side}_{entry['branch']}"
                        / "comparison"
                    ),
                    diagnostic_identity={
                        "scope": "representative_rhs",
                        "comparison_mode": "common_layout_equivalence",
                        "pairing_scope": "same_live_layout",
                        "run_layout_epoch": layout_epoch,
                        "layout_instance_id": layout_epoch,
                        "source_sha": identity["source_sha"],
                        "probe_manifest_sha256": representative_rhs_contract[
                            "sha256"
                        ],
                        "packet_manifest_sha256": representative_rhs_contract[
                            "packet_binding"
                        ]["packet_manifest_sha256"],
                        "layout_identity_sha256": before_layout[
                            "layout_identity_sha256"
                        ],
                        "ordinal": ordinal,
                        "side": side,
                        "formal_column": formal_column,
                        "branch_ordinal": int(entry["branch_ordinal"]),
                    },
                )
                common_stage_marker(
                    "diagnostic_save_end",
                    entry,
                    group="PAIR_DIAGNOSTIC",
                    vectors={"rhs": rhs},
                    status="measured",
                    diagnostic_packets=comparison.get("diagnostic_packets"),
                )
                diagnostic_finished = True
                record = {
                    "ordinal": ordinal,
                    "side": side,
                    "branch": str(entry["branch"]),
                    "audit_index": int(entry["audit_index"]),
                    "formal_column": formal_column,
                    "branch_ordinal": int(entry["branch_ordinal"]),
                    "status": "completed",
                    "first_variant": first_variant,
                    "variant_order": [first_variant, second_variant],
                    "audits": _jsonable(audits),
                    "variants": variant_records,
                    "comparison": comparison,
                    "scope": "representative_rhs",
                    "comparison_mode": "common_layout_equivalence",
                    "pairing_scope": "same_live_layout",
                    "run_layout_epoch": layout_epoch,
                    "layout_instance_id": layout_epoch,
                    "layout_identity_sha256": before_layout[
                        "layout_identity_sha256"
                    ],
                    "before_layout": {
                        "layout_identity_sha256": before_layout[
                            "layout_identity_sha256"
                        ]
                    },
                    "after_layout": {
                        "layout_identity_sha256": after_layout[
                            "layout_identity_sha256"
                        ]
                    },
                    "rhs_before_sha256": rhs_before_sha,
                }
                if comparison["pass"] is not True:
                    record["status"] = "failed"
                    record["failure_classification"] = (
                        "RESPONSE_SENSITIVITY_UNRESOLVED"
                    )
                    persist_pair(record)
                    persisted = True
                    _raise_common_error(
                        f"common-layout response equivalence failed at ordinal {ordinal}",
                        "RESPONSE_SENSITIVITY_UNRESOLVED",
                        record,
                    )
                persist_pair(record)
                persisted = True
                records.append(record)
                marker_callback(
                    "system_setup_stage",
                    {
                        "name": "common_layout_equivalence",
                        "side": side,
                        "ordinal": ordinal,
                        "variant_order": [first_variant, second_variant],
                        "comparison": comparison,
                    },
                )
            except BaseException as exc:
                if active_variant is not None and not variant_finished:
                    common_stage_marker(
                        "variant_apply_end",
                        entry,
                        group="VARIANT_APPLY",
                        variant=active_variant,
                        status="failed",
                        error_type=type(exc).__name__,
                    )
                if diagnostic_started and not diagnostic_finished:
                    common_stage_marker(
                        "diagnostic_end",
                        entry,
                        group="PAIR_DIAGNOSTIC",
                        status="failed",
                        error_type=type(exc).__name__,
                    )
                if not persisted:
                    partial = {
                        "ordinal": ordinal,
                        "side": side,
                        "status": "failed",
                        "failure_classification": getattr(
                            exc,
                            "failure_classification",
                            "PAIRING_SETUP_FAILURE",
                        ),
                        "error": f"{type(exc).__name__}: {exc}",
                        "failure_evidence": _jsonable(
                            getattr(exc, "failure_evidence", {})
                        ),
                        "run_layout_epoch": layout_epoch,
                        "layout_instance_id": layout_epoch,
                        "before_layout": (
                            None
                            if before_layout is None
                            else {
                                "layout_identity_sha256": before_layout[
                                    "layout_identity_sha256"
                                ]
                            }
                        ),
                        "after_layout": (
                            None
                            if after_layout is None
                            else {
                                "layout_identity_sha256": after_layout[
                                    "layout_identity_sha256"
                                ]
                            }
                        ),
                        "audits": _jsonable(audits),
                        "variants": _jsonable(variant_records),
                    }
                    if rhs is not None:
                        partial["rhs_current_sha256"] = owned_rhs_sha(
                            rhs, "failure_current"
                        )
                    persist_pair(partial)
                raise
            finally:
                common_stage_marker(
                    "pair_end",
                    entry,
                    group="PAIR",
                    status="persisted" if persisted else "failed",
                )
                representative_context[side] = None
                if first_response is not None:
                    first_response.destroy()
                if second_response is not None:
                    second_response.destroy()
                if rhs is not None:
                    if common_first_rhs_by_side[side] is rhs:
                        common_first_rhs_by_side[side] = None
                        common_first_entry_by_side[side] = None
                    rhs.destroy()
        return {
            "scope": "representative_rhs",
            "comparison_mode": "common_layout_equivalence",
            "pairing_scope": "same_live_layout",
            "run_layout_epoch": layout_epoch,
            "layout_instance_id": layout_epoch,
            "status": "completed",
            "expected_count": len(entries),
            "completed_count": len(records),
            "apply_count": 2 * len(records),
            "entries": records,
            "source_manifest": {
                "path": representative_rhs_contract["path"],
                "sha256": representative_rhs_contract["sha256"],
                "scope": representative_rhs_contract["scope"],
            },
            "source_audit": dict(representative_rhs_contract["source_audit"]),
            "packet_binding": dict(representative_rhs_contract["packet_binding"]),
            "layout": {
                "layout_instance_id": layout_epoch,
                "identity_sha256": initial_layout["layout_identity_sha256"],
                "path": str(
                    audit_path.with_name("common_layout_equivalence")
                    / f"{side}_layout.json"
                ),
                "rechecks": list(common_layout_rechecks[side]),
            },
            "full_formal": {"status": "not_run", "reason": "comparison_mode"},
            "variant_binding": dict(variant_bindings_by_side[side]),
        }

    def representative_setup_result(
        representative: Mapping[str, Any],
        admission_payload: Mapping[str, Any],
        cleanup: Mapping[str, Any],
        *,
        schedule_summary: Mapping[str, Any] | None = None,
        comparison_mode: str | None = None,
    ) -> dict[str, Any]:
        after_diagnostics = {
            side: dict(diagnostics)
            for side, diagnostics in side_diagnostics_after.items()
        }
        p4_counts = {
            side: int(diagnostics.get("p4_factor_count", 0))
            for side, diagnostics in side_diagnostics_before.items()
        }
        nested_counts = {
            side: int(diagnostics.get("nested_iterative_ksp_count", 0))
            for side, diagnostics in side_diagnostics_before.items()
        }
        shared_inventory = {
            "p6_factor_count": 0,
            "global_direct_factor_count": 0,
            "modal_block": "representative_rhs_only",
            "approximate_preconditioner_only": True,
        }
        if schedule_summary is None:
            candidate_inventory = {
                "p4_factor_count_at_setup": sum(p4_counts.values()),
                "p4_factor_count_after_cleanup": {
                    side: int(diagnostics.get("p4_factor_count", 0))
                    for side, diagnostics in side_diagnostics_after.items()
                },
                "nested_iterative_ksp_count_at_setup": sum(
                    nested_counts.values()
                ),
                "nested_iterative_ksp_count_after_cleanup": {
                    side: int(diagnostics.get("nested_iterative_ksp_count", 0))
                    for side, diagnostics in side_diagnostics_after.items()
                },
                "component_cleanup_pass": cleanup.get(
                    "component_cleanup_pass"
                ),
            }
        else:
            candidate_inventory = dict(schedule_summary)
        candidate_inventory.update(shared_inventory)
        if schedule_summary is not None:
            candidate_inventory.update(
                {
                    "p4_factor_count_after_cleanup": {
                        side: int(diagnostics.get("p4_factor_count", 0))
                        for side, diagnostics in side_diagnostics_after.items()
                    },
                    "nested_iterative_ksp_count_after_cleanup": {
                        side: int(diagnostics.get("nested_iterative_ksp_count", 0))
                        for side, diagnostics in side_diagnostics_after.items()
                    },
                    "component_cleanup_pass": cleanup.get("component_cleanup_pass"),
                }
            )
        common_mode = comparison_mode == TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE
        result = {
            "schema": (
                "task041.side_balh.common_layout_equivalence_setup.v1"
                if common_mode
                else "task041.side_balh.representative_rhs_setup.v1"
            ),
            "status": (
                "common_layout_equivalence_completed"
                if common_mode
                else "representative_rhs_completed"
            ),
            "qualification_scope": qualification_scope,
            "qualification_method": (
                "task041_balh_side_inverse_response_fgmres32"
            ),
            "qualification": (
                "comparison_only" if common_mode else "diagnostic_component_only"
            ),
            "admission_audit": dict(admission_payload),
            "representative_rhs": (
                None
                if common_mode
                else {**dict(representative), "cleanup": dict(cleanup)}
            ),
            "common_layout_equivalence": (
                {**dict(representative), "cleanup": dict(cleanup)}
                if common_mode
                else None
            ),
            "cost_probe": {
                "status": "not_run",
                "reason": "representative_rhs_scope",
            },
            "side_rhs_audit_path": str(audit_path),
            "side_actions": {
                side: dict(diagnostics)
                for side, diagnostics in side_diagnostics_before.items()
            },
            "side_diagnostics_after_destroy": after_diagnostics,
            "candidate_inventory": candidate_inventory,
            "variant_binding": (
                {
                    side: dict(value)
                    for side, value in variant_bindings_by_side.items()
                }
                if common_mode
                else None
            ),
            "modal_schur": {
                "status": "not_run",
                "reason": "representative_rhs_scope",
            },
            "outer_ksp": {
                "status": "not_run",
                "reason": "representative_rhs_scope",
            },
            "full_formal": {
                "status": "not_run",
                "reason": "representative_rhs_scope",
                "solve": {"status": "not_run"},
                "recovery": {"status": "not_run"},
            },
        }
        if schedule_summary is not None:
            result["side_setup_schedule"] = schedule_summary[
                "side_setup_schedule"
            ]
            result["side_setup"] = dict(schedule_summary)
        if common_mode:
            result["comparison_mode"] = comparison_mode
        if rank_numa_evidence is not None:
            result["rank_numa_evidence"] = list(rank_numa_evidence)
        return result

    try:
        operator, operator_context = create_hybrid_assembled_block_action(
            setup.bottom, setup.top, setup.coupling
        )
        global_source = layout.create_vector()
        fill_global_source(global_source)
        global_source_before = copy_vector(global_source)
        global_action_before = operator.createVecLeft()
        operator.mult(global_source, global_action_before)
        global_rhs_before = layout.pack(
            setup.bottom.b,
            setup.top.b,
            internal_modal_rhs_correction(setup.coupling),
        )
        if side_setup_schedule == TASK041_SEQUENTIAL_COMPONENT_SCHEDULE:
            if representative_rhs_contract is None:
                raise Task041ModePrepError(
                    "sequential_component requires the representative RHS contract"
                )
            representative_entries = list(representative_rhs_contract["entries"])
            entries_by_side: dict[str, list[Mapping[str, Any]]] = {
                "bottom": [],
                "top": [],
            }
            for entry in representative_entries:
                side = str(entry["side"])
                if side not in entries_by_side:
                    raise Task041ModePrepError(
                        f"representative RHS entry has unsupported side: {side}"
                    )
                entries_by_side[side].append(entry)
            if any(len(entries) != 4 for entries in entries_by_side.values()):
                raise Task041ModePrepError(
                    "sequential_component requires four fixed entries per side"
                )

            global_identity_checks: dict[str, dict[str, Any]] = {}

            def require_global_identity(label: str) -> None:
                check = global_identity_check(label)
                global_identity_checks[label] = check
                marker_callback(
                    "system_setup_stage",
                    {
                        "side": label.split("_", 1)[0],
                        "substage": "global_identity",
                        "event": label,
                        "identity_check": check,
                    },
                )
                if not check["pass"]:
                    failure_evidence["global_operator_identity"] = {
                        "checks": dict(global_identity_checks),
                        "failed_at": label,
                    }
                    raise Task041ModePrepError(
                        f"global operator identity failed at {label}"
                    )

            representative_parts: list[Mapping[str, Any]] = []
            for side in ("bottom", "top"):
                require_global_identity(f"{side}_before_build")
                sequential_boundary(side, "before_build")
                build_side(side, getattr(setup, side))
                live_at_build = {
                    "p4_factor_count": int(
                        side_diagnostics_before[side].get("p4_factor_count", 0)
                    ),
                    "nested_iterative_ksp_count": int(
                        side_diagnostics_before[side].get(
                            "nested_iterative_ksp_count", 0
                        )
                    ),
                }
                if comparison_mode == TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE:
                    first_entry = entries_by_side[side][0]
                    modal = np.zeros(
                        2 * int(setup.coupling.mode_count_per_direction),
                        dtype=PETSc.ScalarType,
                    )
                    modal[int(first_entry["formal_column"])] = PETSc.ScalarType(1.0)
                    common_first_rhs_by_side[side] = modal_coupling_action(
                        side, setup.coupling, modal
                    )
                    common_first_entry_by_side[side] = first_entry
                admit_side(side)
                require_global_identity(f"{side}_after_admission")
                side_result = (
                    run_common_layout_equivalence_probe(
                        entries_by_side[side], side
                    )
                    if comparison_mode == TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE
                    else run_representative_rhs_probe(entries_by_side[side])
                )
                if side_result["completed_count"] != len(entries_by_side[side]):
                    raise Task041ModePrepError(
                        f"sequential_component {side} probe is incomplete"
                    )
                sequential_side_records[side] = {
                    "side": side,
                    "admission_pass": True,
                    "probe_expected_count": len(entries_by_side[side]),
                    "probe_completed_count": int(
                        side_result["completed_count"]
                    ),
                    "live_at_build": live_at_build,
                }
                require_global_identity(f"{side}_before_release")
                sequential_boundary(side, "before_release")
                release_side(side)
                require_global_identity(f"{side}_after_release")
                representative_parts.append(side_result)

            global_operator_identity = {
                "source": (
                    "one original assembled global operator/RHS/source checked "
                    "around each sequential side lifecycle"
                ),
                "checks": global_identity_checks,
                "threshold": 1.0e-12,
                "pass": all(
                    bool(check["pass"])
                    for check in global_identity_checks.values()
                ),
            }
            admission_payload = {
                "schema": "task041.h1g2b2b.candidate_side_admission.v1",
                "identity": dict(identity) if identity is not None else {},
                "sides": dict(admission_audits),
                "global_operator_identity": global_operator_identity,
                "side_setup_schedule": side_setup_schedule,
                "pass": bool(
                    global_operator_identity["pass"]
                    and all(
                        bool(audit.get("pass"))
                        for audit in admission_audits.values()
                    )
                ),
            }
            _write_rank0_json(
                audit_path.with_name("balh_admission_audit.json"),
                admission_payload,
                comm,
            )
            if not admission_payload["pass"]:
                failure_evidence["admission_audit"] = admission_payload
                raise Task041ModePrepError(
                    "sequential_component admission audit failed"
                )
            representative = _merge_representative_parts(
                representative_parts, representative_entries
            )
            p4_live = {
                side: int(
                    record["live_at_build"]["p4_factor_count"]
                )
                for side, record in sequential_side_records.items()
            }
            nested_live = {
                side: int(
                    record["live_at_build"]["nested_iterative_ksp_count"]
                )
                for side, record in sequential_side_records.items()
            }
            cleanup = release_before_recovery()
            schedule_summary = {
                "side_setup_schedule": side_setup_schedule,
                "order": ["bottom", "top"],
                "side_completion": dict(sequential_side_records),
                "lifecycle_boundaries": list(sequential_lifecycle_boundaries),
                "global_identity_checks": global_identity_checks,
                "p4_factor_created_total": sequential_created_totals[
                    "p4_factor"
                ],
                "nested_iterative_ksp_created_total": sequential_created_totals[
                    "nested_iterative_ksp"
                ],
                "p4_factor_count_at_setup": None,
                "nested_iterative_ksp_count_at_setup": None,
                "p4_factor_count_at_setup_by_side": p4_live,
                "nested_iterative_ksp_count_at_setup_by_side": nested_live,
                "p4_factor_simultaneously_live_peak": sequential_live_peaks[
                    "p4_factor"
                ],
                "nested_iterative_ksp_simultaneously_live_peak": sequential_live_peaks[
                    "nested_iterative_ksp"
                ],
                "total_created": sequential_created_totals["side_inverse"],
                "simultaneously_live_peak": sequential_live_peaks[
                    "side_inverse"
                ],
                "simultaneously_live_component_peak": sequential_live_peaks[
                    "owned_component"
                ],
                "side_completed_live": {
                    side: {
                        "p4_factor_count": p4_live[side],
                        "nested_iterative_ksp_count": nested_live[side],
                    }
                    for side in p4_live
                },
                "side_cleaned_live": {
                    side: {
                        "p4_factor_count": int(
                            side_diagnostics_after[side].get(
                                "p4_factor_count", 0
                            )
                        ),
                        "nested_iterative_ksp_count": int(
                            side_diagnostics_after[side].get(
                                "nested_iterative_ksp_count", 0
                            )
                        ),
                    }
                    for side in side_diagnostics_after
                },
            }
            return representative_setup_result(
                representative,
                admission_payload,
                cleanup,
                schedule_summary=schedule_summary,
                comparison_mode=comparison_mode,
            )

        for side, system in (("bottom", setup.bottom), ("top", setup.top)):
            build_side(side, system)

        for side, inverse in side_inverses.items():
            admission_audits[side] = inverse.admission_audit(identity=identity)
        admission_payload = {
            "schema": "task041.h1g2b2b.candidate_side_admission.v1",
            "identity": dict(identity) if identity is not None else {},
            "sides": admission_audits,
            "pass": all(
                bool(audit.get("pass")) for audit in admission_audits.values()
            ),
        }
        _write_rank0_json(
            audit_path.with_name("balh_admission_audit.json"),
            admission_payload,
            comm,
        )
        if not admission_payload["pass"]:
            failure_evidence["admission_audit"] = admission_payload
            raise Task041ModePrepError(
                "BAL_H side admission audit failed; raw audit was persisted"
            )
        global_identity = global_identity_check("dual_after_admission")
        admission_payload["global_operator_identity"] = global_identity
        admission_payload["pass"] = bool(
            admission_payload["pass"] and global_identity["pass"]
        )
        _write_rank0_json(
            audit_path.with_name("balh_admission_audit.json"),
            admission_payload,
            comm,
        )
        for side, audit in admission_audits.items():
            marker_callback(
                f"{side}_admission_audit",
                {"audit": audit, "pass": admission_payload["pass"]},
            )
        if not admission_payload["pass"]:
            failure_evidence["admission_audit"] = admission_payload
            raise Task041ModePrepError(
                "BAL_H admission audit failed; raw audit was persisted"
            )

        for vector in (
            global_source,
            global_source_before,
            global_action_before,
            global_rhs_before,
        ):
            if vector is not None:
                vector.destroy()
        global_source = None
        global_source_before = None
        global_action_before = None
        global_rhs_before = None

        p4_factor_counts_at_setup = {
            side: int(diagnostics.get("p4_factor_count", 0))
            for side, diagnostics in side_diagnostics_before.items()
        }
        nested_ksp_counts_at_setup = {
            side: int(diagnostics.get("nested_iterative_ksp_count", 0))
            for side, diagnostics in side_diagnostics_before.items()
        }
        if representative_rhs_contract is not None:
            marker_callback(
                "both_side_actions_ready",
                {
                    "source": "BAL_H_side_inverse_response_operators",
                    "inventory": {
                        side: dict(diagnostics)
                        for side, diagnostics in side_diagnostics_before.items()
                    },
                    "p4_factor_count": sum(p4_factor_counts_at_setup.values()),
                    "p6_factor_count": 0,
                    "global_direct_factor_count": 0,
                    "nested_iterative_ksp_count": sum(
                        nested_ksp_counts_at_setup.values()
                    ),
                    "scope": "representative_rhs",
                },
            )
            representative = run_representative_rhs_probe()
            cleanup = release_before_recovery()
            return representative_setup_result(
                representative,
                admission_payload,
                cleanup,
            )

        for side, system in (("bottom", setup.bottom), ("top", setup.top)):
            probe_side(side, side_inverses[side], system)
        cost_probe = cost_probe_summary()
        for side in audit_phase:
            audit_phase[side] = "modal_schur"

        marker_callback(
            "both_side_actions_ready",
            {
                "source": "BAL_H_side_inverse_response_operators",
                "inventory": {
                    side: dict(diagnostics)
                    for side, diagnostics in side_diagnostics_before.items()
                },
                "p4_factor_count": sum(p4_factor_counts_at_setup.values()),
                "p6_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_iterative_ksp_count": sum(nested_ksp_counts_at_setup.values()),
            },
        )
        marker_callback(
            "modal_schur_build_begin",
            {
                "source": "create_side_balh_block_ldu_preconditioner",
                "sampled_column_contract_sha256": sampled_column_contract["sha256"],
            },
        )
        context = create_side_balh_block_ldu_preconditioner(
            layout,
            setup.bottom,
            setup.top,
            setup.coupling,
            side_inverses["bottom"],
            side_inverses["top"],
            sampled_columns=sampled_column_contract["columns"],
            sampled_column_roles=sampled_column_contract["roles"],
            sampled_column_contract_sha256=sampled_column_contract["sha256"],
            marker_callback=marker_callback,
        )
        context_inventory_before = dict(context.inventory)
        marker_callback(
            "modal_schur_ready",
            {
                "source": "create_side_balh_block_ldu_preconditioner",
                "inventory": context_inventory_before,
            },
        )
        for side in audit_phase:
            audit_phase[side] = "outer"
        marker_callback(
            "outer_ksp_setup_ready",
            {
                "source": "formal_candidate_ksp_setup",
                "ksp_type": "fgmres",
                "restart": 32,
                "max_it": 2048,
                "threshold": 5.0e-9,
                "initial_guess": "zero",
                "pc_side": "right",
                "preconditioner_inventory": context_inventory_before,
                "setup_probe": False,
            },
        )
        formal_result = dict(
            full_formal_runner(
                setup=setup,
                layout=layout,
                operator=operator,
                context=context,
                comm=comm,
                marker_callback=marker_callback,
                release_before_recovery=release_before_recovery,
            )
        )
        result = {
            "schema": "task041.side_balh.candidate_setup.v1",
            "status": str(formal_result.get("status")),
            "qualification_scope": qualification_scope,
            "qualification_method": "task041_balh_side_inverse_response_fgmres32",
            "qualification": "research_only_approximate_candidate",
            "admission_audit": admission_payload,
            "cost_probe": cost_probe,
            "side_rhs_audit_path": str(audit_path),
            "side_actions": {
                side: dict(diagnostics)
                for side, diagnostics in side_diagnostics_before.items()
            },
            "side_diagnostics_after_destroy": {
                side: dict(diagnostics)
                for side, diagnostics in side_diagnostics_after.items()
            },
            "candidate_inventory": {
                "p4_factor_count_at_setup": sum(
                    p4_factor_counts_at_setup.values()
                ),
                "p4_factor_count_after_cleanup": {
                    side: int(diagnostics.get("p4_factor_count", 0))
                    for side, diagnostics in side_diagnostics_after.items()
                },
                "p6_factor_count": 0,
                "global_direct_factor_count": 0,
                "nested_iterative_ksp_count_at_setup": sum(
                    nested_ksp_counts_at_setup.values()
                ),
                "nested_iterative_ksp_count_after_cleanup": {
                    side: int(diagnostics.get("nested_iterative_ksp_count", 0))
                    for side, diagnostics in side_diagnostics_after.items()
                },
                "modal_block": "finite_nonlinear_side_inverse_response_columns",
                "approximate_preconditioner_only": True,
                "component_cleanup_pass": formal_result.get(
                    "release_before_recovery", {}
                ).get("component_cleanup_pass"),
            },
            "modal_schur": context_inventory_before.get("modal_schur")
            if context_inventory_before is not None
            else None,
            "outer_ksp": {
                "type": "fgmres",
                "restart": 32,
                "max_it": 2048,
                "threshold": 5.0e-9,
                "initial_guess": "zero",
                "pc_side": "right",
                "setup_probe": False,
            },
            "full_formal": formal_result,
        }
        if rank_numa_evidence is not None:
            result["rank_numa_evidence"] = list(rank_numa_evidence)
        return result
    except BaseException:
        for side, inverse in side_inverses.items():
            last_apply = dict(inverse.diagnostics.get("last_apply", {}))
            if last_apply.get("failure_classification") in {
                "P4_PHYSICAL_RESIDUAL_GATE",
                "BALANCED_CONSTRAINT_REJECTED",
            }:
                failure_evidence[side] = last_apply
        if not released:
            release_before_recovery()
        raise


def run_task041_consumer(
    *,
    input_path: str | Path,
    packet_manifest: str | Path,
    packet_identity: str | Path,
    packet_manifest_sha256: str,
    run_directory: str | Path,
    source_sha: str,
    packet_producer_source_sha: str | None = None,
    packet_origin: str | None = None,
    legacy_native_binding: str | Path | None = None,
    candidate: bool = False,
    comm: Any = MPI.COMM_WORLD,
    disable_time_stop: bool = False,
    performance_profile: str | None = None,
    task041_rhs_probe_manifest: str | Path | None = None,
    side_setup_schedule: str | None = None,
    comparison_mode: str | None = None,
) -> dict[str, Any]:
    """Consume one fresh Task041 packet through an exact or BAL_H side path."""

    if not _valid_sha(source_sha, 40):
        raise Task041ModePrepError("source_sha must be a lowercase 40-character SHA")
    if not _valid_sha(packet_manifest_sha256, 64):
        raise Task041ModePrepError("packet manifest SHA must be a lowercase SHA256")
    legacy_native = packet_origin == "task039.v4.h4.legacy_native"
    if (packet_origin is None) != (legacy_native_binding is None):
        raise Task041ModePrepError(
            "legacy packet origin and binding must be supplied together"
        )
    if packet_origin is not None and not legacy_native:
        raise Task041ModePrepError("unsupported Task041 packet origin")
    specification = load_and_resolve(input_path)
    normalized = specification.as_jsonable()
    contract = _task041_case_contract(normalized, comm.size, phase="consumer")
    case_time_stop_disabled = bool(
        contract["balh"]
        and contract.get("consumer_time_stop_enforced", True) is False
    )
    time_stop_disabled = bool(disable_time_stop or case_time_stop_disabled)
    time_stop_enforced = not time_stop_disabled if contract["balh"] else True
    diagnostic_output_enabled = bool(
        contract.get("diagnostic_output_on_unqualified", False)
    )
    transfer_optimization_profile = contract.get("transfer_optimization_profile")
    if candidate and not (
        contract["balh"] and contract.get("balh_route") == "balh"
    ):
        raise Task041ModePrepError(
            "Task041 candidate worker requires the registered BAL_H candidate profile"
        )
    if not candidate and contract["balh"] and contract.get("balh_route") == "balh":
        raise Task041ModePrepError(
            "Task041 BAL_H candidate profile requires the candidate worker entry point"
        )
    if contract["balh"]:
        from benchmarks.task041_balh_workflow import (
            TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
            task041_balh_time_stop_override_record,
        )

        if disable_time_stop and (
            not candidate
            or normalized["model_id"] != TASK041_BALH_5NM_CANDIDATE_MODEL_ID
        ):
            raise Task041ModePrepError(
                "time-stop override requires the 5 nm BAL_H candidate worker"
            )
    performance_contract = None
    representative_rhs_contract: Mapping[str, Any] | None = None
    if (
        (side_setup_schedule is not None or comparison_mode is not None)
        and performance_profile is None
    ):
        raise Task041ModePrepError(
            "Task041 comparison options require task041_schur_speed_v2"
        )
    if performance_profile is not None:
        if not candidate or not contract["balh"]:
            raise Task041ModePrepError(
                "task041_schur_speed_v2 requires a BAL_H candidate worker"
            )
        from benchmarks.task041_balh_workflow import (
            TASK041_REPRESENTATIVE_RHS_SCOPE,
            TASK041_SCHUR_SPEED_V2_PROFILE,
            load_task041_representative_rhs_manifest,
            task041_schur_speed_v2_contract,
        )

        if performance_profile != TASK041_SCHUR_SPEED_V2_PROFILE:
            raise Task041ModePrepError("unsupported Task041 performance profile")
        if disable_time_stop:
            raise Task041ModePrepError(
                "performance profile and time-stop override are mutually exclusive"
            )
        try:
            performance_contract = task041_schur_speed_v2_contract(
                str(normalized["model_id"]),
                scope=(
                    TASK041_REPRESENTATIVE_RHS_SCOPE
                    if task041_rhs_probe_manifest is not None
                    else None
                ),
                side_setup_schedule=side_setup_schedule,
                comparison_mode=comparison_mode,
            )
        except ValueError as exc:
            raise Task041ModePrepError(str(exc)) from exc
        if task041_rhs_probe_manifest is not None:
            if normalized["model_id"] != TASK041_BALH_5NM_CANDIDATE_MODEL_ID:
                raise Task041ModePrepError(
                    "representative RHS probe requires the 5 nm BAL_H candidate"
                )
            try:
                representative_rhs_contract = load_task041_representative_rhs_manifest(
                    task041_rhs_probe_manifest
                )
            except (OSError, TypeError, ValueError) as exc:
                raise Task041ModePrepError(
                    f"invalid representative RHS manifest: {exc}"
                ) from exc
            if (
                performance_contract["scope"]
                != representative_rhs_contract["scope"]
                or performance_contract["budget_group"]
                != representative_rhs_contract["budget"]["group"]
            ):
                raise Task041ModePrepError(
                    "representative RHS scope does not match the V2 budget contract"
                )
        elif comparison_mode is not None:
            raise Task041ModePrepError(
                "common_layout_equivalence requires the representative RHS manifest"
            )
        effective_limits = dict(contract["limits"])
        effective_limits.update(
            {
                "swap_limit_bytes": int(
                    performance_contract["swap_limit_bytes"]
                ),
                "process_tree_rss_warning_bytes": int(
                    performance_contract["warning_memory_bytes"]
                ),
                "process_tree_rss_cap_bytes": int(
                    performance_contract["memory_cap_bytes"]
                ),
                "memory_cap_source": performance_contract["memory_gate_source"],
            }
        )
        effective_limits["timeout_seconds"] = int(
            performance_contract["active_consumer_budget_seconds"]
        )
        contract = dict(contract)
        contract["limits"] = effective_limits
    if task041_rhs_probe_manifest is not None and representative_rhs_contract is None:
        raise Task041ModePrepError(
            "representative RHS probe requires task041_schur_speed_v2"
        )
    root = _collective_fresh_root(run_directory, comm)
    started = time.monotonic()
    candidate_audit_path = root / "numerical_output" / (
        "representative_rhs_audits.jsonl"
        if representative_rhs_contract is not None and comparison_mode is None
        else "common_layout_equivalence_audits.jsonl"
        if comparison_mode is not None
        else "balh_side_rhs_audits.jsonl"
    )
    result: dict[str, Any] = {
        "schema": contract["consumer_schema"],
        "profile": contract["consumer_profile"],
        "phase": TASK041_CONSUMER_PHASE,
        "input": str(Path(input_path).resolve()),
        "run_directory": str(root),
        "source_sha": source_sha,
        "status": "IMPLEMENTATION_FAILURE",
        "classification": "IMPLEMENTATION_FAILURE",
        "diagnostic_output_policy": {
            "enabled": diagnostic_output_enabled,
            "model_id": (
                normalized["model_id"] if diagnostic_output_enabled else None
            ),
            "mode": "finite_unqualified_field" if diagnostic_output_enabled else "disabled",
            "qualification_independent": diagnostic_output_enabled,
        },
        "official_rta": {"status": "not_run"},
        "limits": contract["limits"],
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
    if performance_contract is not None:
        result["performance_profile"] = performance_contract
        if side_setup_schedule is not None:
            result["side_setup_schedule"] = side_setup_schedule
        if comparison_mode is not None:
            result["comparison_mode"] = comparison_mode
    if transfer_optimization_profile is not None:
        result["transfer_optimization"] = {
            "profile": transfer_optimization_profile,
            "source": "src.solvers.physical_balanced_same_mesh_transfer",
            "scope": "candidate side owner transfer and conjugate-transpose apply",
            "high_level_performance_contract": "not_used",
        }
    if representative_rhs_contract is not None:
        result["representative_rhs_probe"] = {
            "path": representative_rhs_contract["path"],
            "sha256": representative_rhs_contract["sha256"],
            "scope": representative_rhs_contract["scope"],
            "purpose": representative_rhs_contract["purpose"],
            "budget_group": performance_contract["budget_group"],
        }
    if candidate:
        result["side_rhs_audit_path"] = str(candidate_audit_path)
    if contract["balh"]:
        if case_time_stop_disabled:
            result["time_stop_policy"] = {
                "model_id": normalized["model_id"],
                "run_id": normalized["run_id"],
                "producer_enforced": bool(
                    contract.get("producer_time_stop_enforced", True)
                ),
                "consumer_enforced": False,
                "consumer_timeout_seconds": None,
                "scope": "registered_2nm_case",
            }
        else:
            result["time_stop_override"] = (
                task041_balh_time_stop_override_record(disable_time_stop)
                | {
                    "model_id": normalized["model_id"],
                    "run_id": normalized["run_id"],
                    "source_sha": source_sha,
                    "origin": "public_worker_cli",
                }
            )
    if packet_origin is not None:
        result["packet_origin"] = packet_origin
        result["legacy_native_binding"] = str(legacy_native_binding)
    environment: dict[str, Any] = {}
    marker_records: list[dict[str, Any]] = []
    factor_events: dict[str, list[dict[str, Any]]] = {"bottom": [], "top": []}
    setup = None
    cleanup_release: dict[str, Any] = {"status": "not_run"}
    release_audit: dict[str, Any] = {}
    candidate_failure_evidence: dict[str, Any] = {}
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
            schema=contract["consumer_schema"],
            marker_sequence=TASK041_CONSUMER_MARKER_SEQUENCE,
            limits=contract["limits"],
            enforce_time_stop=time_stop_enforced,
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
            if not contract["balh"]:
                snapshot_path = root / "minimal_recovery_packet.json"
                _write_rank0_json(
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
                    comm,
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
        elif stage == "solution_checkpoint_saved":
            checkpoint = detail.get("checkpoint")
            snapshot_path = root / "minimal_recovery_packet.json"
            _write_rank0_json(
                snapshot_path,
                {
                    "schema": "task041.side_balh.minimal_recovery_packet.v2",
                    "status": (
                        checkpoint.get("qualification", "diagnostic-only")
                        if isinstance(checkpoint, Mapping)
                        else "diagnostic-only"
                    ),
                    "source": "retained_solution_owner_sharded_packet",
                    "snapshot_location": (
                        None
                        if not isinstance(checkpoint, Mapping)
                        else checkpoint.get("manifest")
                    ),
                    "snapshot_lifetime": "persistent_owner_sharded_disk_packet",
                    "consumed_by": "run_v3_7_recovery_runner",
                    "json_contains_solution": False,
                    "checkpoint": checkpoint,
                },
                comm,
            )
            emit(
                "minimal_recovery_packet_saved",
                {
                    "path": str(snapshot_path),
                    "kind": "owner_sharded_solution_packet",
                    "checkpoint": checkpoint,
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
        rank_numa_evidence: list[dict[str, Any]] = []
        rank_numa_identities: dict[int, tuple[int, int]] = {}
        rank_numa_stage_callback = None
        rank_numa_evidence_path: Path | None = None
        if (
            candidate
            and contract.get('p4_inverse_backend') == 'cell_condensed'
            and contract.get('construction_audit') == 'reference_entity_trace_v1'
        ):
            from benchmarks.task041_rank_numa import (
                append_stage_jsonl,
                collective_snapshot,
                qualification_errors,
            )
            rank_numa_evidence_path = root / "rank_numa_evidence.jsonl"

            def record_rank_numa(
                stage: str,
                arrays: Mapping[str, object] | None = None,
                detail: Mapping[str, Any] | None = None,
            ) -> None:
                local = collective_snapshot(
                    comm,
                    stage,
                    arrays,
                    include_probe=stage == 'startup',
                )
                if detail is not None:
                    local['stage_detail'] = dict(detail)
                gathered = comm.gather(local, root=0)
                payload = None
                if comm.rank == 0:
                    ordered = sorted(
                        gathered or [],
                        key=lambda item: int(item['rank']),
                    )
                    payload = {
                        'schema': 'task041.rank_numa_stage.v1',
                        'stage': str(stage),
                        'mpi_size': int(comm.size),
                        'collective_status': (
                            'measured'
                            if all(
                                item.get('collective_status') == 'measured'
                                for item in ordered
                            )
                            else 'failed'
                        ),
                        'ranks': ordered,
                    }
                payload = comm.bcast(payload, root=0)
                if not isinstance(payload, Mapping):
                    raise Task041ModePrepError(
                        f'NUMA evidence payload was not broadcast: {stage}'
                    )
                stage_errors = qualification_errors(
                    payload,
                    expected_mpi_size=8,
                    previous_identities=rank_numa_identities,
                    require_startup_probe=stage == 'startup',
                )
                all_stage_errors = comm.allgather(stage_errors)
                merged_errors = sorted(
                    {
                        str(error)
                        for rank_errors in all_stage_errors
                        for error in rank_errors
                    }
                )
                qualification = {
                    'status': 'passed' if not merged_errors else 'failed',
                    'errors': merged_errors or None,
                    'policy': 'MPI8_CPU1_8_socket0_node0',
                }
                raw_payload = dict(payload)
                payload = dict(raw_payload)
                payload['qualification'] = qualification
                rank_numa_evidence.append(payload)
                append_stage_jsonl(
                    comm,
                    rank_numa_evidence_path,
                    {
                        'schema': 'task041.rank_numa_evidence.v1',
                        'stage': str(stage),
                        'raw_payload': raw_payload,
                        'qualification': qualification,
                    },
                )
                if merged_errors:
                    raise Task041ModePrepError(
                        f'NUMA qualification failed at {stage}: '
                        + '; '.join(merged_errors)
                    )
                for item in payload['ranks']:
                    evidence = item['evidence']
                    identity = evidence['rank_identity']
                    rank_numa_identities[int(item['rank'])] = (
                        int(identity['pid']),
                        int(identity['starttime_ticks']),
                    )

            rank_numa_stage_callback = record_rank_numa
        environment = _environment_snapshot()
        result["environment"] = environment
        if contract["balh"]:
            _write_rank_pid_affinity(
                root,
                phase=TASK041_CONSUMER_PHASE,
                source_sha=source_sha,
                comm=comm,
            )
        emit("preflight_begin", {"mpi_size": comm.size})
        available = _memavailable_bytes()
        if available < contract["limits"]["min_memavailable_bytes"]:
            raise Task041ModePrepError("MemAvailable is below the Task041 preflight floor")
        result["memavailable_bytes"] = available
        resolved_sha = resolved_config_sha256(specification)
        identity_path = Path(packet_identity).resolve()
        manifest_path = Path(packet_manifest).resolve()
        disk_identity = json.loads(identity_path.read_text(encoding="utf-8"))
        if not isinstance(disk_identity, Mapping):
            raise Task041ModePrepError("Task041 packet identity is not a mapping")
        if representative_rhs_contract is not None:
            packet_binding = representative_rhs_contract["packet_binding"]
            if (
                packet_binding["packet_manifest_sha256"] != packet_manifest_sha256
                or packet_binding["packet_identity_sha256"]
                != hashlib.sha256(identity_path.read_bytes()).hexdigest()
            ):
                raise Task041ModePrepError(
                    "representative RHS probe packet binding does not match the worker packet"
                )
        source_identity = _task041_packet_source_identity(
            source_sha,
            packet_producer_source_sha,
            disk_identity.get("source_sha"),
        )
        packet_source_sha = source_identity["producer_source_sha"]
        consumer_binding: dict[str, Any] | None = None
        if contract["balh"]:
            if candidate and contract["balh_route"] != "balh":
                raise Task041ModePrepError(
                    "Task041 candidate worker received a non-candidate BAL_H profile"
                )
            if not candidate and contract["balh_route"] != "exact":
                raise Task041ModePrepError(
                    "Task041 BAL_H candidate profile requires the candidate worker entry point"
                )
            from benchmarks.task041_balh_workflow import (
                build_task041_balh_packet_identity,
                task041_balh_consumer_identity_binding,
            )

            packet_identity = dict(disk_identity)
            if legacy_native:
                from benchmarks.task041_legacy_native_packet import (
                    bind_task041_legacy_native_consumer,
                )

                consumer_binding = bind_task041_legacy_native_consumer(
                    packet_identity,
                    specification,
                    source_sha,
                    legacy_native_binding,
                )
            else:
                consumer_binding = task041_balh_consumer_identity_binding(
                    packet_identity, specification, source_sha
                )
            recomputed_identity = build_task041_balh_packet_identity(
                specification, normalized, source_sha, resolved_sha
            )
        else:
            identity_builder = (
                build_task041_shortwave_packet_identity
                if contract["shortwave"]
                else build_task041_packet_identity
            )
            recomputed_identity = identity_builder(
                specification, normalized, packet_source_sha, resolved_sha
            )
            if dict(disk_identity) != recomputed_identity:
                raise Task041ModePrepError(
                    "Task041 consumer packet identity recomputation mismatch"
                )
            packet_identity = recomputed_identity
        if (
            recomputed_identity["mode_count"] != contract["mode_count"]
            or recomputed_identity["mpi_size"] != contract["mpi_size"]
        ):
            raise Task041ModePrepError("Task041 consumer identity does not match case contract")
        emit(
            "input_validated",
            {
                "identity": recomputed_identity,
                "producer_identity": packet_identity,
                "consumer_binding": consumer_binding,
            },
        )
        emit("packet_identity_validated", {"path": str(identity_path)})
        sampled_contract = _task041_consumer_sampled_column_contract(
            packet_identity,
            manifest_path,
            packet_manifest_sha256,
            legacy_native=legacy_native,
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
        if rank_numa_stage_callback is not None:
            result['rank_numa_evidence'] = rank_numa_evidence
            result['rank_numa_evidence_path'] = str(rank_numa_evidence_path)
            rank_numa_stage_callback('startup')
        modal_cfg = deepcopy(cfg)
        if contract["balh"]:
            from benchmarks.task041_balh_workflow import (
                task041_balh_candidate_consumer_iterative_config,
                task041_balh_candidate_consumer_profile,
                task041_balh_exact_consumer_iterative_config,
                task041_balh_exact_consumer_profile,
            )

            profile = (
                task041_balh_candidate_consumer_profile(specification)
                if candidate
                else task041_balh_exact_consumer_profile(specification)
            )
            iterative_config = (
                task041_balh_candidate_consumer_iterative_config()
                if candidate
                else task041_balh_exact_consumer_iterative_config()
            )
        else:
            profile = (
                _task041_shortwave_consumer_profile(specification)
                if contract["shortwave"]
                else _task041_consumer_profile()
            )
            iterative_config = (
                task041_shortwave_consumer_iterative_config()
                if contract["shortwave"]
                else task041_consumer_iterative_config()
            )
        producer = {
            "producer_source_sha": packet_source_sha,
            "consumer_source_sha": source_sha,
            "physical_model_sha256": str(specification.physical_model_sha256),
            "consumer_model_id": recomputed_identity["model_id"],
            "requested_modes": recomputed_identity["mode_count"],
            "mpi_size": recomputed_identity["mpi_size"],
            "task041_scope": recomputed_identity["scope"],
            "qualification_scope": recomputed_identity["scope"],
            "qualification_method": (
                "task041_balh_side_inverse_response_fgmres32"
                if candidate
                else "task041_exact_side_full_formal"
            ),
            "canonical_authority": True,
            "consumer_route": "balh_candidate" if candidate else "balh_exact",
            "diagnostic_output_policy": result["diagnostic_output_policy"],
        }
        result["identity"] = recomputed_identity
        result["producer_identity"] = packet_identity
        if consumer_binding is not None:
            result["consumer_binding"] = consumer_binding
        result["source_identity"] = source_identity
        result["consumer_route"] = (
            "task041_balh_candidate" if candidate else "task041_balh_exact"
        ) if contract["balh"] else "task041_legacy"
        result["qualification_method"] = producer["qualification_method"]
        result["qualification_status"] = (
            "research_only_approximate_candidate" if candidate else "exact_side"
        )
        result["profile_config"] = _jsonable(asdict(profile))
        result["outer_config"] = _jsonable(asdict(iterative_config))
        if contract["shortwave"]:
            result["solver_provenance"] = {
                "input_declared": {
                    "ksp_type": normalized["solver"]["linear_solver"],
                    "restart": normalized["solver"]["restart"],
                },
                "effective": {
                    "ksp_type": iterative_config.ksp_type,
                    "restart": iterative_config.restart,
                },
                "source": "reused passed 5nm native MPI8 V7 actual solver",
            }
        result["packet"] = {
            "manifest": str(manifest_path),
            "manifest_sha256": packet_manifest_sha256,
            "identity": str(identity_path),
            "sampled_column_contract": sampled_contract,
        }

        from benchmarks.run_task037b_hybrid_iterative import build_frozen_m10_setup
        from benchmarks.task039_v3_7_orchestration import (
            V3_7_MATRIX_REPEAT_TOLERANCE,
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
            selected_mode_packet_identity=packet_identity,
            selected_mode_packet_manifest_sha256=packet_manifest_sha256,
            sampled_column_contract=sampled_contract,
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
                "internal_propagation": {
                    "model": normalized.get("method", {}).get("propagation_model"),
                    "target_h_nm": setup.coupling.propagation_axial_target_h_nm,
                    "actual_h_nm": setup.coupling.propagation_axial_h_nm,
                    "cell_count": setup.coupling.propagation_axial_cell_count,
                },
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

        def retained_solution_checkpoint(
            solution: PETSc.Vec,
            rhs: PETSc.Vec,
            solve_report: Mapping[str, Any],
        ) -> Mapping[str, Any]:
            ownership = tuple(int(value) for value in solution.getOwnershipRange())
            identity_value = {
                "source_sha": source_sha,
                "input_sha256": specification.input_sha256,
                "physical_model_sha256": specification.physical_model_sha256,
                "resolved_config_sha256": resolved_sha,
                "producer_source_sha": packet_source_sha,
                "producer_packet_manifest_sha256": packet_manifest_sha256,
                "producer_packet_identity_sha256": hashlib.sha256(
                    identity_path.read_bytes()
                ).hexdigest(),
                "model_id": recomputed_identity["model_id"],
                "run_id": recomputed_identity["run_id"],
                "mode_count": recomputed_identity["mode_count"],
                "mpi_size": int(comm.size),
            }
            metadata = {
                "source": "task041_balh_retained_solution",
                "input_sha256": specification.input_sha256,
                "physical_model_sha256": specification.physical_model_sha256,
                "resolved_config_sha256": resolved_sha,
                "producer_packet_manifest_sha256": packet_manifest_sha256,
                "mpi": {"size": int(comm.size)},
                "layout": {
                    "type": type(layout).__name__,
                    "global_size": int(solution.getSize()),
                    "bottom_ranges": [list(row) for row in layout.bottom_ranges],
                    "top_ranges": [list(row) for row in layout.top_ranges],
                    "combined_offsets": list(layout.combined_offsets),
                    "bottom_local_sizes": list(layout.bottom_local_sizes),
                    "top_local_sizes": list(layout.top_local_sizes),
                    "modal_count": int(layout.modal_count),
                    "modal_owner": int(layout.modal_owner),
                    "ownership": "contiguous rank-sharded PETSc ownership",
                },
                "ownership": {
                    "global_size": int(solution.getSize()),
                    "range": list(ownership),
                },
                "dtype": str(np.asarray(solution.getArray(readonly=True)).dtype),
                "residual_gate_pass": bool(solve_report.get("pass") is True),
                "solve_status": solve_report.get("status"),
                "solve_report": _jsonable(solve_report),
            }
            packet_result = write_packet(
                root / "numerical_output" / "retained_solution_packet",
                np.asarray(solution.getArray(readonly=True)).copy(),
                np.asarray(rhs.getArray(readonly=True)).copy(),
                identity=identity_value,
                metadata=metadata,
                ownership_range=ownership,
                comm=comm,
                allow_nonfinite_diagnostic=True,
            )
            packet_pass = bool(packet_result.get("pass") is True)
            residual_gate_pass = bool(solve_report.get("pass") is True)
            return {
                **packet_result,
                "residual_gate_pass": residual_gate_pass,
                "packet_pass": packet_pass,
                "qualification": (
                    "qualified-for-recovery"
                    if residual_gate_pass and packet_pass
                    else "diagnostic-only"
                ),
                "ownership_range": list(ownership),
                "global_size": int(solution.getSize()),
                "dtype": metadata["dtype"],
                "solve_report": _jsonable(solve_report),
            }

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
                _check_resource(
                    after_sample,
                    started,
                    contract["limits"],
                    enforce_time_stop=time_stop_enforced,
                )
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
                producer={
                    **producer,
                    "_stage_callback": callback,
                },
                run_directory=root,
                iterative_config=iterative_config,
                require_rss_drop=not contract["balh"],
                retained_solution_checkpoint=(
                    retained_solution_checkpoint if contract["balh"] else None
                ),
                release_before_recovery=release_before_recovery,
                allow_unqualified_diagnostic_recovery=diagnostic_output_enabled,
                **kwargs,
            )

        current_stage = "factor_setup"
        shortwave_batch_kwargs = (
            {
                "streaming_w_batch_size": 32,
                "modal_batch_size": 32,
                "early_sample_first": True,
            }
            if contract["shortwave"] or contract["balh"]
            else {}
        )
        if candidate:
            setup_result = _run_task041_balh_candidate_setup(
                setup,
                layout,
                comm=comm,
                marker_callback=callback,
                sampled_column_contract=sampled_contract,
                qualification_scope=recomputed_identity["scope"],
                full_formal_runner=full_formal_runner,
                timeout_seconds=contract["limits"]["timeout_seconds"],
                audit_path=candidate_audit_path,
                elapsed_seconds=time.monotonic() - started,
                workflow_started_monotonic=started,
                failure_evidence=candidate_failure_evidence,
                identity=recomputed_identity,
                disable_time_stop=time_stop_disabled,
                detailed_timing=(
                    performance_contract is not None
                    or contract.get("p4_inverse_backend") == "cell_condensed"
                ),
                representative_rhs_contract=representative_rhs_contract,
                side_setup_schedule=side_setup_schedule,
                comparison_mode=comparison_mode,
                performance_profile=(
                    performance_contract["profile_id"]
                    if performance_contract is not None
                    else None
                ),
                transfer_optimization_profile=transfer_optimization_profile,
                p4_inverse_backend=contract.get("p4_inverse_backend", "full"),
                support_policy=contract.get("support_policy", "legacy"),
                construction_audit=contract.get("construction_audit"),
                rank_numa_stage_callback=rank_numa_stage_callback,
                rank_numa_evidence=rank_numa_evidence,
            )
        else:
            setup_result = run_v5_h4_exact_side_setup_only(
                setup,
                layout,
                comm=comm,
                marker_callback=callback,
                qualification_scope=(
                    recomputed_identity["scope"]
                    if contract["shortwave"] or contract["balh"]
                    else "task039_v4_p6h4_m480_1deg_s"
                ),
                sampled_column_contract=sampled_contract,
                v6_profile=False,
                matrix_repeat_tolerance=(
                    V3_7_MATRIX_REPEAT_TOLERANCE
                    if contract["shortwave"] or contract["balh"]
                    else None
                ),
                **shortwave_batch_kwargs,
                exact_spool_root=None,
                packet_identity=packet_identity,
                packet_manifest_sha256=packet_manifest_sha256,
                full_formal_runner=full_formal_runner,
                outer_probe_config=iterative_config,
            )
        formal_result = setup_result.get("full_formal")
        if not isinstance(formal_result, Mapping):
            raise Task041ModePrepError("Task041 consumer did not return full-formal result")
        if representative_rhs_contract is not None:
            component_key = (
                "common_layout_equivalence"
                if comparison_mode == "common_layout_equivalence"
                else "representative_rhs"
            )
            representative = setup_result.get(component_key)
            candidate_inventory = setup_result.get("candidate_inventory")
            if not isinstance(representative, Mapping) or not isinstance(
                candidate_inventory, Mapping
            ):
                raise Task041ModePrepError(
                    "representative RHS setup did not return its component result"
                )
            result["setup"] = _jsonable(setup_result)
            result["formal"] = _jsonable(formal_result)
            result[component_key] = _jsonable(representative)
            result["gates"] = {
                "pass": False,
                "status": (
                    "not_run_common_layout_equivalence_mode"
                    if comparison_mode == "common_layout_equivalence"
                    else "not_run_representative_rhs_scope"
                ),
                "full_formal": "not_run",
                "official_rta": "not_run",
            }
            result["official_rta"] = {
                "status": "not_run",
                "reason": "representative_rhs_scope",
            }
            result["consumer_scope"] = {
                "local_systems": "created_and_released",
                "coupling": "created_and_released",
                "factor": "representative_rhs_side_inverse",
                "solve": "not_run",
                "recovery": "not_run",
            }
            result["matrix_inventory"] = {
                "qep_calls": qep_release.get("qep_calls"),
                "consumer_qep_required": qep_release.get(
                    "consumer_qep_required"
                ),
                "global_direct_factor_count": 0,
                "global_coarse_factor_count": 0,
                "p4_factor_count_at_setup": candidate_inventory.get(
                    "p4_factor_count_at_setup"
                ),
                "p4_factor_count_after_cleanup": candidate_inventory.get(
                    "p4_factor_count_after_cleanup"
                ),
                "p6_factor_count": candidate_inventory.get("p6_factor_count"),
                "nested_iterative_ksp_count_at_setup": candidate_inventory.get(
                    "nested_iterative_ksp_count_at_setup"
                ),
                "nested_iterative_ksp_count_after_cleanup": candidate_inventory.get(
                    "nested_iterative_ksp_count_after_cleanup"
                ),
                "side_setup_schedule": candidate_inventory.get(
                    "side_setup_schedule"
                ),
                "p4_factor_created_total": candidate_inventory.get(
                    "p4_factor_created_total"
                ),
                "nested_iterative_ksp_created_total": candidate_inventory.get(
                    "nested_iterative_ksp_created_total"
                ),
                "total_created": candidate_inventory.get("total_created"),
                "simultaneously_live_peak": candidate_inventory.get(
                    "simultaneously_live_peak"
                ),
                "simultaneously_live_component_peak": candidate_inventory.get(
                    "simultaneously_live_component_peak"
                ),
                "task040_pc": False,
                "direct_fallback": False,
                "old_mpi8_packet_loader": False,
                "preconditioner_identity": candidate_inventory.get("modal_block"),
                "approximate_preconditioner_only": candidate_inventory.get(
                    "approximate_preconditioner_only"
                ),
            }
            result["setup_cost_probe"] = setup_result.get("cost_probe")
            result["status"] = (
                "task041_common_layout_equivalence_completed"
                if comparison_mode == "common_layout_equivalence"
                else "task041_representative_rhs_completed"
            )
            result["classification"] = (
                "COMMON_LAYOUT_EQUIVALENCE_PASS"
                if comparison_mode == "common_layout_equivalence"
                else "TASK041_REPRESENTATIVE_RHS_COMPLETED"
            )
            emit(
                "official_outputs_written",
                {
                    "scope": component_key,
                    "status": result["status"],
                    "official_rta": result["official_rta"],
                },
            )
        else:
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
            formal_diagnostic_output = formal_result.get("diagnostic_output")
            authority_read_allowed = bool(
                not formal_short_circuit
                or (diagnostic_output_enabled and not formal_lifecycle_failure)
            )
            if (
                authority_read_allowed
                and authority_path is not None
                and authority_path.is_file()
            ):
                current_stage = "authority_validation"
                gates = _task041_consumer_authority_gate(
                    authority_path,
                    formal_result,
                    recomputed_identity,
                    expected_consumer_source_sha=source_sha,
                )
                emit("authority_validated", {"gates": gates, "path": str(authority_path)})
            elif formal_short_circuit:
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
                    raise Task041ModePrepError(
                        "Task041 consumer authority path is missing"
                    )
                raise Task041ModePrepError("Task041 consumer authority was not written")
            result["setup"] = _jsonable(setup_result)
            result["formal"] = _jsonable(formal_result)
            result["gates"] = gates
            if authority_path is not None:
                result["authority_path"] = str(authority_path)
            result["consumer_scope"] = {
                "local_systems": "created_and_released",
                "coupling": "created_and_released",
                "factor": (
                    "local_balh_side_inverse_response_schur"
                    if candidate
                    else "local_exact_side_only"
                ),
                "solve": "right_gmres" if contract["shortwave"] else "right_fgmres",
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
            if candidate:
                candidate_inventory = setup_result.get("candidate_inventory", {})
                result["matrix_inventory"].update(
                    {
                        "p4_factor_count_at_setup": candidate_inventory.get(
                            "p4_factor_count_at_setup"
                        ),
                        "p4_factor_count_after_cleanup": candidate_inventory.get(
                            "p4_factor_count_after_cleanup"
                        ),
                        "p6_factor_count": candidate_inventory.get("p6_factor_count"),
                        "nested_iterative_ksp_count_at_setup": candidate_inventory.get(
                            "nested_iterative_ksp_count_at_setup"
                        ),
                        "nested_iterative_ksp_count_after_cleanup": candidate_inventory.get(
                            "nested_iterative_ksp_count_after_cleanup"
                        ),
                        "preconditioner_identity": candidate_inventory.get(
                            "modal_block"
                        ),
                        "approximate_preconditioner_only": candidate_inventory.get(
                            "approximate_preconditioner_only"
                        ),
                    }
                )
                result["setup_cost_probe"] = setup_result.get("cost_probe")
            diagnostic_authority_available = _task041_diagnostic_authority_available(
                authority_path,
                formal_result,
                gates,
                policy_enabled=diagnostic_output_enabled,
            )
            if diagnostic_authority_available:
                result["status"] = "completed_with_diagnostics"
                result["classification"] = "DIAGNOSTIC_RESULT_AVAILABLE"
                result["workflow_status"] = "completed_with_diagnostics"
                result["qualification_status"] = "unqualified"
                result["qualification"] = {
                    "pass": False,
                    "reason": "formal_or_recovery_or_physics_gate",
                }
                diagnostic_output = (
                    dict(formal_diagnostic_output)
                    if isinstance(formal_diagnostic_output, Mapping)
                    else {}
                )
                diagnostic_output.update(
                    {
                        "result_available": True,
                        "status": "measured_diagnostic",
                        "qualification": "unqualified",
                        "source": "task041_consumer_authority_gate",
                    }
                )
                result["diagnostic_output"] = _jsonable(diagnostic_output)
            elif gates["pass"] is not True or formal_short_circuit:
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
            if diagnostic_authority_available:
                result["official_rta"] = dict(gates["official_rta"])
                result["official_rta"]["status"] = "measured_diagnostic"
                result["official_rta"]["qualified"] = False
            elif formal_short_circuit:
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
        classified_failure = getattr(exc, "failure_classification", None)
        if isinstance(classified_failure, str) and classified_failure in {
            "PAIRING_SETUP_FAILURE",
            "ACTION_EQUIVALENCE_FAIL",
            "NUMERICAL_GATE_FAIL",
            "RESPONSE_SENSITIVITY_UNRESOLVED",
        }:
            result["status"] = (
                "task041_common_layout_equivalence_failed"
                if comparison_mode == "common_layout_equivalence"
                else "task041_representative_rhs_failed"
            )
            result["classification"] = classified_failure
            failure_payload = getattr(exc, "failure_evidence", None)
            if isinstance(failure_payload, Mapping):
                result["failure_evidence"] = _jsonable(
                    dict(failure_payload)
                )
        else:
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
        preserve_common_failure = (
            comparison_mode == "common_layout_equivalence"
            and result.get("classification")
            in {
                "PAIRING_SETUP_FAILURE",
                "NUMERICAL_GATE_FAIL",
                "ACTION_EQUIVALENCE_FAIL",
                "RESPONSE_SENSITIVITY_UNRESOLVED",
            }
        )
        if candidate and candidate_failure_evidence:
            candidate_evidence = {
                "side_rhs_audits": _jsonable(candidate_failure_evidence),
            }
            if preserve_common_failure and isinstance(
                result.get("failure_evidence"), Mapping
            ):
                result["failure_evidence"] = {
                    **dict(result["failure_evidence"]),
                    **candidate_evidence,
                }
            else:
                result["failure_evidence"] = candidate_evidence
            representative_rhs_failures = candidate_failure_evidence.get(
                "representative_rhs"
            )
            representative_gate_evidence = (
                {
                    str(ordinal): evidence
                    for ordinal, evidence in representative_rhs_failures.items()
                    if isinstance(evidence, Mapping)
                    and evidence.get("failure_classification")
                    == "REPRESENTATIVE_RHS_NUMERICAL_GATE"
                }
                if isinstance(representative_rhs_failures, Mapping)
                else {}
            )
            if representative_gate_evidence and not preserve_common_failure:
                result["representative_rhs_gate"] = _jsonable(
                    representative_gate_evidence
                )
                result["status"] = (
                    "task041_consumer_representative_rhs_numerical_gate"
                )
                result["classification"] = "TASK041_CONSUMER_NUMERICAL_FAILURE"
                result["failure_scope"] = "representative_rhs"
                result["failure_gate"] = "REPRESENTATIVE_RHS_NUMERICAL_GATE"
            failure_classes = {
                str(audit.get("failure_classification"))
                for audit in candidate_failure_evidence.values()
            }
            if (
                not preserve_common_failure
                and not representative_gate_evidence
                and "P4_PHYSICAL_RESIDUAL_GATE" in failure_classes
            ):
                result["status"] = "task041_consumer_p4_gate_failure"
                result["classification"] = (
                    "TASK041_CONSUMER_P4_PHYSICAL_RESIDUAL_GATE"
                )
            elif (
                not preserve_common_failure
                and not representative_gate_evidence
                and "BALANCED_CONSTRAINT_REJECTED" in failure_classes
            ):
                result["status"] = "task041_consumer_balanced_constraint_failure"
                result["classification"] = (
                    "TASK041_CONSUMER_BALANCED_CONSTRAINT_REJECTED"
                )
        if candidate and candidate_audit_path.with_name(
            "candidate_setup_cost.json"
        ).is_file():
            cost_path = candidate_audit_path.with_name("candidate_setup_cost.json")
            cost_payload = json.loads(cost_path.read_text(encoding="utf-8"))
            if (
                isinstance(cost_payload, Mapping)
                and cost_payload.get("status") == "SETUP_COST_BLOCKED"
            ):
                result["setup_cost_probe"] = _jsonable(cost_payload)
                cost_evidence = {"cost_probe": _jsonable(cost_payload)}
                if preserve_common_failure and isinstance(
                    result.get("failure_evidence"), Mapping
                ):
                    result["failure_evidence"] = {
                        **dict(result["failure_evidence"]),
                        **cost_evidence,
                    }
                else:
                    result["failure_evidence"] = cost_evidence
                    result["status"] = "SETUP_COST_BLOCKED"
                    result["classification"] = (
                        "TASK041_CONSUMER_SETUP_COST_BLOCKED"
                    )
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
            "rss_marker_emitted": (
                bool(
                    any(
                        marker.get("stage")
                        in {"bottom_construction_cleanup", "top_construction_cleanup"}
                        for marker in marker_records
                    )
                )
                if representative_rhs_contract is not None
                else bool(release_audit.get("rss_marker_emitted"))
            ),
            "representative_rhs_cleanup_pass": (
                result.get("setup", {})
                .get("candidate_inventory", {})
                .get("component_cleanup_pass")
                if representative_rhs_contract is not None
                else None
            ),
            "qep_calls": result.get("matrix_inventory", {}).get("qep_calls", 0),
            "factor_count_after_cleanup": result.get("formal", {})
            .get("release_before_recovery", {})
            .get("factor_count_after_cleanup"),
        }
        result["cleanup"] = cleanup_release
        result["factor_inventory"] = {
            "schema": (
                "task041.side_balh.candidate_factor_inventory.v1"
                if candidate
                else "task041.exact_side.factor_inventory.v1"
            ),
            "source": (
                "candidate SideBalancedInverse and BAL_H block diagnostics"
                if candidate
                else "consumer factor_ready marker INFOG/RINFOG/Mat diagnostics"
            ),
            "bottom": factor_events["bottom"],
            "top": factor_events["top"],
            "not_used": {
                "global_direct": 0,
                "global_coarse": 0,
                "ooc": 0,
            },
        }
        if candidate:
            result["factor_inventory"]["candidate_inventory"] = _jsonable(
                result.get("setup", {}).get("candidate_inventory", {})
            )
            if candidate_failure_evidence:
                result["factor_inventory"]["failure_evidence"] = _jsonable(
                    candidate_failure_evidence
                )
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
        _write_rank0_json(root / "factor_inventory.json", result["factor_inventory"], comm)
        _write_rank0_json(root / "consumer_summary.json", result, comm)
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
    parser.add_argument("--packet-producer-source-sha")
    parser.add_argument("--packet-origin")
    parser.add_argument("--legacy-native-binding")
    return parser


def main(argv: Sequence[str] | None = None) -> dict[str, Any]:
    args = _parser().parse_args(argv)
    if not args.worker:
        raise Task041ModePrepError("Task041 requires a private worker")
    if args.phase == TASK041_MODE_PREP_PHASE:
        if args.packet_producer_source_sha is not None:
            raise Task041ModePrepError(
                "--packet-producer-source-sha is consumer-only"
            )
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
        packet_producer_source_sha=args.packet_producer_source_sha,
        packet_origin=args.packet_origin,
        legacy_native_binding=args.legacy_native_binding,
    )


if __name__ == "__main__":
    main()
