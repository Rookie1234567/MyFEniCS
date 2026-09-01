# MPI collective/callback/cleanup catches synchronize third-party exceptions across ranks.
# ruff: noqa: BLE001
"""Formal S3b J1 baseline and B1 candidate lifecycle cores.

This module owns the frozen bottom-side formal sequence and the short-lived B1
candidate construction context.  Numerical building blocks remain in their
existing solver modules; returned inventories are intentionally JSON-able so a
later runner can persist them without this core writing files itself.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from time import perf_counter
from types import SimpleNamespace
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from ..geometry.hybrid_local_mesh import build_hybrid_local_mesh
from .floquet_background_hcurl_block_service import (
    build_bounded_harmonic_packet,
    canonical_layout_hash,
    create_bounded_harmonic_service,
)
from .floquet_background_hcurl_block_transform import (
    build_hybrid_local_action_bloch_layout,
    create_active_trace_bloch_transforms,
)
from .floquet_background_hcurl_s3_pilot import (
    S3B_CONDITIONAL_PASS,
    S3B_EXPECTED_ACTIVE_ROWS,
    S3B_EXPECTED_CANONICAL_TRACE_ROWS,
    S3B_EXPECTED_FLOQUET_SLAVE_ROWS,
    S3B_EXPECTED_MODE_COUNT,
    S3B_EXPECTED_ROWS_PER_MODE,
    S3B_EXTERNAL_SOURCE_COLUMN,
    S3B_EXTERNAL_SOURCE_LABEL,
    S3B_EXTERNAL_SOURCE_SEED,
    S3B_EXTERNAL_SOURCE_SIGN,
    S3B_FGMRES_INITIAL_MAX_IT,
    S3B_FGMRES_RESTART,
    S3B_MAX_LOCAL_ROWS,
    S3B_MPI_SIZE,
    S3B_NEXT_FIVE_SOURCE_BOTTOM,
    S3B_RSS_HARD_BYTES,
    S3B_SWAP_LIMIT_BYTES,
    S3B_WALL_CAP_SECONDS,
    S3CurrentLayoutSourceFactory,
    S3FixedRightFgmres,
    adjudicate_s3_b1_conditional_gate,
    adjudicate_s3_b1_final_five_source_bare_f_gate,
    adjudicate_s3_b1_initial_gate,
    audit_s3_preconditioner_one_apply,
    build_s3_b1_background_config,
    build_s3_external_dtn_source,
    build_s3_j1_baseline_action,
)
from .hybrid_local_dtn_action import assemble_hybrid_local_dtn_action_system

__all__ = (
    "S3B1CandidateContext",
    "build_s3_b1_candidate_context",
    "compare_s3_candidate_source_to_baseline",
    "run_s3_j1_baseline_formal",
    "validate_s3_j1_baseline_manifest",
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, np.ndarray):
        return [_jsonable(item) for item in value.tolist()]
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (np.integer, int)) and not isinstance(value, bool):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


def _is_lower_sha256(value: Any) -> bool:
    return bool(
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _error_packet(comm: Any, exception: Exception | None) -> dict[str, Any] | None:
    if exception is None:
        return None
    return {
        "rank": int(comm.rank),
        "type": type(exception).__name__,
        "message": str(exception),
    }


def _raise_collective_error(
    comm: Any,
    stage: str,
    exception: Exception | None,
) -> None:
    packets = comm.allgather(_error_packet(comm, exception))
    first = next((packet for packet in packets if packet is not None), None)
    if first is None:
        return
    error = RuntimeError(
        f"S3b J1 formal {stage} failed on rank {int(first['rank'])} "
        f"{first['type']}: {first['message']}"
    )
    if exception is not None:
        raise error from exception
    raise error


def _resource_number(
    resource: Mapping[str, Any],
    keys: tuple[str, ...],
    *,
    gib_keys: tuple[str, ...] = (),
) -> float:
    for key in keys:
        if key in resource:
            try:
                return float(resource[key])
            except (TypeError, ValueError, OverflowError):
                return math.nan
    for key in gib_keys:
        if key in resource:
            try:
                return float(resource[key]) * 2**30
            except (TypeError, ValueError, OverflowError):
                return math.nan
    return math.nan


def _action_count(action: Any, key: str = "apply_count") -> int | None:
    if action is None:
        return None
    diagnostics = None
    try:
        diagnostics = action.diagnostics
        if callable(diagnostics):
            diagnostics = diagnostics()
    except Exception:
        diagnostics = None
    if isinstance(diagnostics, Mapping):
        value = diagnostics.get(key)
        if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
            return int(value)
    try:
        value = getattr(action, key)
    except Exception:
        return None
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        return int(value)
    return None


def _operator_shape(operator: PETSc.Mat) -> tuple[int, int]:
    return tuple(int(value) for value in operator.getSize())


def _layer_factor_row_stats(
    diagnostics: Mapping[str, Any] | None, comm: Any
) -> dict[str, Any]:
    records = diagnostics.get("layer_factors", []) if isinstance(diagnostics, Mapping) else []
    global_rows: list[int] = []
    local_rows: list[int] = []
    for record in records if isinstance(records, (tuple, list)) else ():
        if not isinstance(record, Mapping):
            continue
        try:
            global_rows.append(int(record["rows_global"]))
            local_rows.append(int(record["rows_owned_local"]))
        except (KeyError, TypeError, ValueError):
            continue
    local_max = max(local_rows, default=0)
    max_local_rows = int(comm.allreduce(local_max, op=MPI.MAX))
    max_global_rows = int(
        comm.allreduce(max(global_rows, default=0), op=MPI.MAX)
    )
    return {
        "factor_count": len(global_rows),
        "max_global_rows": max_global_rows,
        "max_local_rows": max_local_rows,
        "global_rows_ready": global_rows,
        "local_rows_ready_on_rank": local_rows,
    }


def _collective_progress(
    comm: Any,
    callback: Any,
    stage: str,
    payload: Mapping[str, Any] | None = None,
) -> None:
    """Invoke one progress callback on every rank and propagate failures."""

    if callback is None:
        return
    local_exception = None
    try:
        callback(_jsonable({"stage": stage, **dict(payload or {})}))
    except Exception as exc:
        local_exception = exc
    packets = comm.allgather(_error_packet(comm, local_exception))
    first = next((packet for packet in packets if packet is not None), None)
    if first is None:
        return
    error = RuntimeError(
        f"S3b candidate progress {stage} failed on rank "
        f"{int(first['rank'])} {first['type']}: {first['message']}"
    )
    if local_exception is not None:
        raise error from local_exception
    raise error


def _layout_request_from_fine_action(system: Any) -> Any:
    """Adapt an action system to the existing dynamic layout builder."""

    return SimpleNamespace(
        V=system.V,
        static_condensation=system.static_condensation,
        A=system.fine_action,
        floquet_data=system.floquet_data,
        cfg=system.cfg,
        n_external_aux=system.n_external_aux,
    )


def _clear_packet_factor_arrays(packet: Any) -> None:
    if packet is None:
        return
    for factor in packet.blocks:
        if isinstance(factor, dict):
            factor["lu"] = None
            factor["pivots"] = None


class S3B1CandidateContext:
    """Target-side B1 harmonic service with explicit background lifetimes."""

    def __init__(
        self,
        *,
        comm: Any,
        progress_callback: Any,
        target_system: Any,
        target_transforms: Any,
        service: Any,
        packet: Any,
        ready_inventory: Mapping[str, Any],
    ) -> None:
        self._comm = comm
        self._progress_callback = progress_callback
        self._target_system = target_system
        self._target_transforms = target_transforms
        self._service = service
        self._packet = packet
        self._ready_inventory = deepcopy(_jsonable(dict(ready_inventory)))
        self._after_cleanup_inventory: dict[str, Any] | None = None
        self._cleanup_errors: list[dict[str, Any]] = []
        self._destroyed = False

    @property
    def target_system(self) -> Any:
        return self._target_system

    @property
    def target_transforms(self) -> Any:
        return self._target_transforms

    @property
    def service(self) -> Any:
        return self._service

    @property
    def packet(self) -> Any:
        return self._packet

    @property
    def target_operator(self) -> Any:
        if self._target_system is None:
            return None
        return self._target_system.fine_action

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "destroyed": bool(self._destroyed),
            "ready_inventory": deepcopy(self._ready_inventory),
            "after_cleanup_inventory": deepcopy(self._after_cleanup_inventory),
            "cleanup_errors": deepcopy(self._cleanup_errors),
        }

    @property
    def ready_inventory(self) -> dict[str, Any]:
        return deepcopy(self._ready_inventory)

    @property
    def after_cleanup_inventory(self) -> dict[str, Any] | None:
        return deepcopy(self._after_cleanup_inventory)

    @property
    def destroyed(self) -> bool:
        return self._destroyed

    def destroy(self) -> None:
        """Destroy target resources in the fixed service/QT/system order."""

        if self._destroyed:
            return
        local_errors: list[dict[str, Any]] = []

        def progress(stage: str, payload: Mapping[str, Any] | None = None) -> None:
            try:
                _collective_progress(
                    self._comm,
                    self._progress_callback,
                    stage,
                    payload,
                )
            except Exception as exc:
                local_errors.append(
                    {
                        "stage": stage,
                        "rank": int(self._comm.rank),
                        "type": type(exc).__name__,
                        "message": str(exc),
                    }
                )

        def destroy_one(name: str, obj: Any) -> None:
            progress(f"candidate_{name}_destroy_begin")
            if obj is not None:
                try:
                    obj.destroy()
                except Exception as exc:
                    local_errors.append(
                        {
                            "object": name,
                            "rank": int(self._comm.rank),
                            "type": type(exc).__name__,
                            "message": str(exc),
                        }
                    )
            progress(f"candidate_{name}_destroyed")

        service = self._service
        transforms = self._target_transforms
        system = self._target_system
        packet = self._packet
        destroy_one("service", service)
        destroy_one("target_transforms", transforms)
        destroy_one("target_system", system)
        progress("candidate_packet_arrays_clear_begin")
        try:
            _clear_packet_factor_arrays(packet)
        except Exception as exc:
            local_errors.append(
                {
                    "object": "packet_arrays",
                    "rank": int(self._comm.rank),
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
            )
        packet_cleared = True
        if packet is not None:
            packet_cleared = all(
                not isinstance(factor, dict)
                or (factor.get("lu") is None and factor.get("pivots") is None)
                for factor in packet.blocks
            )
        progress(
            "candidate_packet_arrays_cleared",
            {"packet_arrays_cleared": bool(packet_cleared)},
        )
        self._service = None
        self._target_transforms = None
        self._target_system = None
        self._packet = None

        error_packets = self._comm.allgather(local_errors)
        cleanup_errors = [
            item
            for packet_group in error_packets
            for item in packet_group
        ]
        self._cleanup_errors = cleanup_errors
        service_failed = any(
            isinstance(item, Mapping) and item.get("object") == "service"
            for item in cleanup_errors
        )
        transforms_failed = any(
            isinstance(item, Mapping) and item.get("object") == "target_transforms"
            for item in cleanup_errors
        )
        system_failed = any(
            isinstance(item, Mapping) and item.get("object") == "target_system"
            for item in cleanup_errors
        )
        packet_failed = any(
            isinstance(item, Mapping) and item.get("object") == "packet_arrays"
            for item in cleanup_errors
        ) or not packet_cleared
        after = deepcopy(self._ready_inventory)
        after.update(
            {
                "factor_count_after_cleanup": (
                    0 if not service_failed and not packet_failed else None
                ),
                "owner_local_factor_count_after_cleanup": (
                    0 if not service_failed and not packet_failed else None
                ),
                "full_side_exact_factor_count": 0,
                "full_cross_section_factor_count": 0,
                "global_direct_factor_count": 0,
                "global_coarse_factor_count": 0,
                "target_service_destroyed": not service_failed,
                "target_transforms_destroyed": not transforms_failed,
                "target_system_destroyed": not system_failed,
                "packet_arrays_cleared": not packet_failed,
                "cleanup_errors": cleanup_errors,
            }
        )
        self._after_cleanup_inventory = after
        progress(
            "candidate_cleanup_complete",
            {
                "after_cleanup_inventory": after,
                "cleanup_errors": cleanup_errors,
            },
        )
        final_error_packets = self._comm.allgather(local_errors)
        cleanup_errors = [
            item
            for packet_group in final_error_packets
            for item in packet_group
        ]
        self._cleanup_errors = cleanup_errors
        after["cleanup_errors"] = cleanup_errors
        self._after_cleanup_inventory = after
        self._destroyed = True
        if cleanup_errors:
            first = cleanup_errors[0]
            raise RuntimeError(
                "S3b candidate cleanup failed on rank "
                f"{int(first.get('rank', 0))} "
                f"{first.get('type', 'RuntimeError')}: "
                f"{first.get('message', 'cleanup failed')}"
            )


def build_s3_b1_candidate_context(
    cfg: Any,
    profile: Any,
    *,
    comm: Any = MPI.COMM_WORLD,
    progress_callback: Any | None = None,
) -> S3B1CandidateContext:
    """Build the fixed B1 target context using a short-lived background."""

    if int(comm.size) != S3B_MPI_SIZE:
        raise ValueError(
            f"S3b B1 candidate requires MPI size {S3B_MPI_SIZE}, got {comm.size}"
        )
    progress_validity = comm.allgather(
        {
            "rank": int(comm.rank),
            "is_none": progress_callback is None,
            "callable": callable(progress_callback),
        }
    )
    all_none = all(packet["is_none"] for packet in progress_validity)
    all_callable = all(packet["callable"] for packet in progress_validity)
    if not (all_none or all_callable):
        invalid_progress = next(
            (packet for packet in progress_validity if not packet["is_none"]),
            progress_validity[0],
        )
        raise TypeError(
            "S3b B1 candidate progress_callback must be all-None or "
            "all-callable across MPI ranks; "
            f"first differing rank {int(invalid_progress['rank'])}"
        )

    background_cfg, background_audit = build_s3_b1_background_config(cfg)
    if float(background_audit.get("additional_absorbing_shift", 0.0)) != 0.0:
        raise RuntimeError("S3b B1 background additional absorbing shift must be zero")

    target_mesh = None
    background_system = None
    background_transforms = None
    background_layout = None
    packet = None
    target_system = None
    target_layout = None
    target_transforms = None
    service = None
    local_cleanup_errors: list[dict[str, Any]] = []

    def progress(stage: str, payload: Mapping[str, Any] | None = None) -> None:
        _collective_progress(comm, progress_callback, stage, payload)

    def assemble(system_cfg: Any) -> Any:
        return assemble_hybrid_local_dtn_action_system(
            system_cfg,
            "bottom",
            bottom_interface_z_nm=profile.bottom_interface_nm,
            top_interface_z_nm=profile.top_interface_nm,
            local_mesh_override=target_mesh,
            comm=comm,
            log=None,
        )

    def destroy_failed(name: str, obj: Any) -> None:
        if obj is None:
            return
        try:
            obj.destroy()
        except Exception as exc:
            local_cleanup_errors.append(
                {
                    "object": name,
                    "rank": int(comm.rank),
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
            )

    def destroy_collective(name: str, obj: Any) -> None:
        local_exception = None
        if obj is not None:
            try:
                obj.destroy()
            except Exception as exc:
                local_exception = exc
        packets = comm.allgather(_error_packet(comm, local_exception))
        first = next((packet for packet in packets if packet is not None), None)
        if first is not None:
            raise RuntimeError(
                f"S3b B1 candidate {name} destroy failed on rank "
                f"{int(first['rank'])} {first['type']}: {first['message']}"
            )

    try:
        progress("candidate_mesh_build_begin", {"side": "bottom"})
        target_mesh = build_hybrid_local_mesh(
            cfg,
            "bottom",
            bottom_interface_z_nm=profile.bottom_interface_nm,
            top_interface_z_nm=profile.top_interface_nm,
            comm=comm,
        )
        progress(
            "candidate_mesh_ready",
            {
                "side": "bottom",
                "mesh_cells": list(target_mesh.mesh_cells),
                "mesh_built_once": True,
            },
        )

        progress(
            "candidate_background_system_build_begin",
            {
                "side": "bottom",
                "material_model": background_audit.get("material_model"),
            },
        )
        background_system = assemble(background_cfg)
        if background_system.local_mesh is not target_mesh:
            raise RuntimeError(
                "S3b B1 background system did not retain the single target mesh"
            )
        if not isinstance(background_system.fine_action, PETSc.Mat):
            raise TypeError("S3b B1 background requires fine_action PETSc Mat")
        if tuple(map(int, background_system.fine_action.getSize())) != (
            S3B_EXPECTED_ACTIVE_ROWS,
            S3B_EXPECTED_ACTIVE_ROWS,
        ):
            raise ValueError("S3b B1 background fine_action size differs from 8424")
        progress(
            "candidate_background_system_ready",
            {
                "active_rows": int(background_system.fine_action.getSize()[0]),
                "operator_identity": "background_system.fine_action",
                "shared_mesh_identity": True,
                "additional_absorbing_shift": 0.0,
            },
        )

        background_layout = build_hybrid_local_action_bloch_layout(
            _layout_request_from_fine_action(background_system)
        )
        if background_layout.phase_model != "topological_orbit_dft_approximation":
            raise RuntimeError("S3b B1 requires the topological-orbit phase model")
        if (
            background_layout.active_rows != S3B_EXPECTED_ACTIVE_ROWS
            or background_layout.nx * background_layout.ny != S3B_EXPECTED_MODE_COUNT
            or background_layout.rows_per_harmonic != S3B_EXPECTED_ROWS_PER_MODE
        ):
            raise RuntimeError("S3b B1 background layout does not match fixed modal rows")
        background_layout_hash = canonical_layout_hash(background_layout)
        progress(
            "candidate_background_layout_ready",
            {
                "layout_hash": background_layout_hash,
                "phase_model": background_layout.phase_model,
                "active_rows": int(background_layout.active_rows),
                "mode_count": int(background_layout.nx * background_layout.ny),
                "rows_per_mode": int(background_layout.rows_per_harmonic),
                "layout_block_count": len(background_layout.blocks),
            },
        )

        background_transforms = create_active_trace_bloch_transforms(background_layout)
        progress(
            "candidate_background_qt_ready",
            {
                "layout_hash": background_layout_hash,
                "q_identity": "background_transforms.q",
                "t_identity": "background_transforms.t",
            },
        )

        def background_factor_progress(payload: Mapping[str, Any]) -> None:
            progress("candidate_background_factor_ready", payload)

        packet = build_bounded_harmonic_packet(
            SimpleNamespace(A=background_system.fine_action),
            background_transforms,
            require_exact_block_diagonal=False,
            progress_callback=background_factor_progress,
        )
        packet_audit = packet.setup_audit
        if packet.layout_hash != background_layout_hash:
            raise RuntimeError("S3b B1 background packet layout hash differs")
        if complex(packet.additional_absorbing_shift) != 0.0j:
            raise RuntimeError("S3b B1 packet additional absorbing shift is nonzero")
        if (
            packet_audit.get("additional_absorbing_shift") != 0.0
            or packet_audit.get("require_exact_block_diagonal") is not False
            or packet_audit.get("dropped_coupling") is not True
            or packet_audit.get("background_mode_count") != S3B_EXPECTED_MODE_COUNT
            or packet_audit.get("block_rows")
            != [S3B_EXPECTED_ROWS_PER_MODE] * S3B_EXPECTED_MODE_COUNT
            or packet_audit.get("factor_count_global") != S3B_EXPECTED_MODE_COUNT
            or packet_audit.get("max_local_rows") != S3B_EXPECTED_ROWS_PER_MODE
            or packet_audit.get("max_local_rows") > S3B_MAX_LOCAL_ROWS
        ):
            raise RuntimeError("S3b B1 background packet audit differs from fixed contract")
        progress(
            "candidate_background_packet_ready",
            {
                "layout_hash": packet.layout_hash,
                "mode_count": int(packet_audit["background_mode_count"]),
                "rows_per_mode": int(S3B_EXPECTED_ROWS_PER_MODE),
                "factor_count_global": int(packet_audit["factor_count_global"]),
                "max_local_rows": int(packet_audit["max_local_rows"]),
                "phase_model": background_layout.phase_model,
                "dropped_coupling": True,
                "exact_physical_fft": False,
                "numeric_vector_value_allgather": False,
                "fe_sized_topology_coordinate_metadata_allgather": True,
                "replicated_layout_metadata": True,
                "full_basis_per_rank_replication": False,
                "final_production_structure_gate_passed": False,
                "final_production_structure_gate_reason": (
                    "FE-sized topology/coordinate metadata allgather remains; "
                    "pilot structure evidence only, productionization deferred "
                    "unless numerical positive"
                ),
                "off_block_audit": packet_audit.get("block_off_block_audit", []),
                "additional_absorbing_shift": 0.0,
            },
        )

        destroy_collective("background_transforms", background_transforms)
        background_transforms = None
        destroy_collective("background_system", background_system)
        background_system = None
        background_layout = None
        progress(
            "candidate_background_destroyed",
            {
                "background_transforms_destroyed": True,
                "background_system_destroyed": True,
                "background_references_released": True,
                "packet_petsc_retained": False,
            },
        )

        progress("candidate_target_system_build_begin", {"side": "bottom"})
        target_system = assemble(cfg)
        if target_system.local_mesh is not target_mesh:
            raise RuntimeError(
                "S3b B1 target system did not retain the single target mesh"
            )
        if not isinstance(target_system.fine_action, PETSc.Mat):
            raise TypeError("S3b B1 target requires fine_action PETSc Mat")
        if tuple(map(int, target_system.fine_action.getSize())) != (
            S3B_EXPECTED_ACTIVE_ROWS,
            S3B_EXPECTED_ACTIVE_ROWS,
        ):
            raise ValueError("S3b B1 target fine_action size differs from 8424")
        progress(
            "candidate_target_system_ready",
            {
                "active_rows": int(target_system.fine_action.getSize()[0]),
                "operator_identity": "target_system.fine_action",
                "shared_mesh_identity": True,
                "background_co_resident": False,
            },
        )
        target_layout = build_hybrid_local_action_bloch_layout(
            _layout_request_from_fine_action(target_system)
        )
        if target_layout.phase_model != "topological_orbit_dft_approximation":
            raise RuntimeError("S3b B1 target phase model differs from fixed contract")
        target_layout_hash = canonical_layout_hash(target_layout)
        if target_layout_hash != packet.layout_hash:
            raise RuntimeError("S3b B1 target layout hash differs from background packet")
        if (
            target_layout.active_rows != S3B_EXPECTED_ACTIVE_ROWS
            or target_layout.nx * target_layout.ny != S3B_EXPECTED_MODE_COUNT
            or target_layout.rows_per_harmonic != S3B_EXPECTED_ROWS_PER_MODE
        ):
            raise RuntimeError("S3b B1 target layout does not match fixed modal rows")
        progress(
            "candidate_target_layout_ready",
            {
                "layout_hash": target_layout_hash,
                "phase_model": target_layout.phase_model,
                "active_rows": int(target_layout.active_rows),
                "mode_count": int(target_layout.nx * target_layout.ny),
                "rows_per_mode": int(target_layout.rows_per_harmonic),
                "layout_block_count": len(target_layout.blocks),
                "layout_hash_matches_packet": True,
            },
        )
        if target_layout.active_rows != (
            S3B_EXPECTED_MODE_COUNT * S3B_EXPECTED_ROWS_PER_MODE
        ):
            raise RuntimeError("S3b B1 target rows do not equal 18 times 468")
        target_transforms = create_active_trace_bloch_transforms(target_layout)
        progress(
            "candidate_target_qt_ready",
            {
                "layout_hash": target_layout_hash,
                "q_identity": "target_transforms.q",
                "t_identity": "target_transforms.t",
            },
        )
        service = create_bounded_harmonic_service(packet, target_transforms)
        service_apply_count = _action_count(service)
        if service_apply_count != 0:
            raise RuntimeError(
                "S3b B1 target service apply_count must start at zero"
            )
        progress(
            "candidate_target_service_ready",
            {
                "layout_hash": target_layout_hash,
                "owner_local_factor_count_global": int(
                    packet_audit["factor_count_global"]
                ),
                "owner_local_factor_count_local": int(
                    packet_audit["factor_count_local"]
                ),
                "factor_count_ready": int(packet_audit["factor_count_global"]),
                "max_local_rows": int(packet_audit["max_local_rows"]),
                "service_apply_count": service_apply_count,
            },
        )

        ready_inventory = {
            "side": "bottom",
            "mpi_size": int(comm.size),
            "active_rows": int(target_layout.active_rows),
            "mode_count": int(target_layout.nx * target_layout.ny),
            "rows_per_mode": int(target_layout.rows_per_harmonic),
            "rows_identity": "8424=18*468",
            "max_local_rows": int(packet_audit["max_local_rows"]),
            "max_local_rows_limit": int(S3B_MAX_LOCAL_ROWS),
            "layout_hash": target_layout_hash,
            "background_layout_hash": packet.layout_hash,
            "layout_block_count": len(target_layout.blocks),
            "harmonic_block_count": int(target_layout.nx * target_layout.ny),
            "phase_model": target_layout.phase_model,
            "exact_physical_fft": False,
            "numeric_vector_value_allgather": False,
            "fe_sized_topology_coordinate_metadata_allgather": True,
            "replicated_layout_metadata": True,
            "full_basis_per_rank_replication": False,
            "final_production_structure_gate_passed": False,
            "final_production_structure_gate_reason": (
                "FE-sized topology/coordinate metadata allgather remains; "
                "pilot structure evidence only, productionization deferred "
                "unless numerical positive"
            ),
            "background_material_audit": background_audit,
            "packet_setup_audit": packet_audit,
            "dropped_coupling": bool(packet_audit["dropped_coupling"]),
            "off_block_audit": packet_audit.get("block_off_block_audit", []),
            "additional_absorbing_shift": 0.0,
            "factor_count_ready": int(packet_audit["factor_count_global"]),
            "owner_local_factor_count_ready": int(packet_audit["factor_count_global"]),
            "owner_local_factor_count_local": int(packet_audit["factor_count_local"]),
            "full_side_exact_factor_count": 0,
            "full_cross_section_factor_count": 0,
            "global_direct_factor_count": 0,
            "global_coarse_factor_count": 0,
            "candidate_max_local_rows_gate": "passed",
            "background_target_shared_mesh_identity": True,
            "background_mesh_identity": True,
            "target_mesh_identity": True,
            "mesh_build_count": 1,
            "background_system_destroyed": True,
            "background_transforms_destroyed": True,
            "background_co_resident": False,
            "target_operator_identity": "target_system.fine_action",
            "target_operator_borrowed": True,
            "target_system_ready": True,
            "target_transforms_ready": True,
            "target_service_ready": True,
            "service_apply_count": service_apply_count,
            "packet_ready": True,
        }
        context = S3B1CandidateContext(
            comm=comm,
            progress_callback=progress_callback,
            target_system=target_system,
            target_transforms=target_transforms,
            service=service,
            packet=packet,
            ready_inventory=ready_inventory,
        )
        target_mesh = None
        target_system = None
        target_transforms = None
        service = None
        packet = None
        return context
    except Exception as exc:
        destroy_failed("service", service)
        destroy_failed("target_transforms", target_transforms)
        destroy_failed("target_system", target_system)
        try:
            _clear_packet_factor_arrays(packet)
        except Exception as cleanup_exc:
            local_cleanup_errors.append(
                {
                    "object": "packet_arrays",
                    "rank": int(comm.rank),
                    "type": type(cleanup_exc).__name__,
                    "message": str(cleanup_exc),
                }
            )
        destroy_failed("background_transforms", background_transforms)
        destroy_failed("background_system", background_system)
        target_mesh = None
        cleanup_packets = comm.allgather(local_cleanup_errors)
        cleanup_errors = [
            item
            for packet_group in cleanup_packets
            for item in packet_group
        ]
        exception_packets = comm.allgather(_error_packet(comm, exc))
        first_exception = next(
            (item for item in exception_packets if item is not None),
            None,
        )
        if first_exception is None:
            first_exception = {
                "rank": int(comm.rank),
                "type": type(exc).__name__,
                "message": str(exc),
            }
        cleanup_suffix = (
            f"; cleanup errors={cleanup_errors}" if cleanup_errors else ""
        )
        error = RuntimeError(
            "S3b B1 candidate construction failed on rank "
            f"{int(first_exception['rank'])} {first_exception['type']}: "
            f"{first_exception['message']}{cleanup_suffix}"
        )
        raise error from exc


def validate_s3_j1_baseline_manifest(
    manifest: Mapping[str, Any],
    expected_manifest_sha256: str,
    observed_manifest_sha256: str,
    *,
    source_sha: str,
    input_path: Any,
    input_sha256: str,
    physical_model_sha256: str,
) -> dict[str, Any]:
    """Validate one direct J1 baseline mapping against frozen provenance."""

    def require(condition: bool, message: str) -> None:
        if not condition:
            raise ValueError(f"S3b J1 baseline manifest invalid: {message}")

    require(isinstance(manifest, Mapping), "manifest must be a direct mapping")
    require(
        "result" not in manifest and "manifest" not in manifest,
        "wrapper mappings are not accepted",
    )
    require(
        _is_lower_sha256(expected_manifest_sha256),
        "expected manifest SHA must be lowercase 64-hex",
    )
    require(
        _is_lower_sha256(observed_manifest_sha256),
        "observed manifest SHA must be lowercase 64-hex",
    )
    require(
        expected_manifest_sha256 == observed_manifest_sha256,
        "expected and observed manifest SHA differ",
    )
    require(
        manifest.get("schema") == "task040.v9_e.s3b_j1_baseline_formal.v1",
        "schema is not the direct J1 baseline schema",
    )
    require(
        manifest.get("method") == "task040_v9_e_s3b_j1_baseline_formal",
        "method is not the fixed J1 baseline method",
    )
    require(manifest.get("route") == "V9_E_S3B", "route is not V9_E_S3B")
    require(
        manifest.get("classification") == "S3B_J1_BASELINE_MEASURED",
        "classification is not measured",
    )
    require(manifest.get("baseline_only") is True, "baseline_only must be true")

    provenance = manifest.get("provenance")
    require(isinstance(provenance, Mapping), "provenance must be a mapping")
    expected_provenance = {
        "source_sha": str(source_sha),
        "input_path": str(input_path),
        "input_sha256": str(input_sha256),
        "physical_model_sha256": str(physical_model_sha256),
        "mpi_size": S3B_MPI_SIZE,
        "threads": 1,
        "side": "bottom",
        "operator_identity": "system.fine_action",
        "full_A_used": False,
        "qep_calls": 0,
    }
    for key, expected in expected_provenance.items():
        require(provenance.get(key) == expected, f"provenance.{key} mismatch")

    fixed_contract = manifest.get("fixed_contract")
    require(isinstance(fixed_contract, Mapping), "fixed_contract must be a mapping")
    expected_contract = {
        "active_rows": S3B_EXPECTED_ACTIVE_ROWS,
        "source_label": S3B_EXTERNAL_SOURCE_LABEL,
        "source_seed": S3B_EXTERNAL_SOURCE_SEED,
        "source_column": S3B_EXTERNAL_SOURCE_COLUMN,
        "source_sign": S3B_EXTERNAL_SOURCE_SIGN,
        "fgmres_restart": S3B_FGMRES_RESTART,
        "fgmres_initial_max_it": S3B_FGMRES_INITIAL_MAX_IT,
        "rss_hard_bytes": S3B_RSS_HARD_BYTES,
        "swap_limit_bytes": S3B_SWAP_LIMIT_BYTES,
        "wall_cap_seconds": S3B_WALL_CAP_SECONDS,
    }
    for key, expected in expected_contract.items():
        require(fixed_contract.get(key) == expected, f"fixed_contract.{key} mismatch")

    source = manifest.get("source")
    require(isinstance(source, Mapping), "source must be a direct audit mapping")
    require(
        source.get("label") == S3B_EXTERNAL_SOURCE_LABEL,
        "source label mismatch",
    )
    require(source.get("seed") == S3B_EXTERNAL_SOURCE_SEED, "source seed mismatch")
    require(
        source.get("column") == S3B_EXTERNAL_SOURCE_COLUMN,
        "source column mismatch",
    )
    require(
        source.get("resolved_column") == S3B_EXTERNAL_SOURCE_COLUMN,
        "source resolved column mismatch",
    )
    require(source.get("sign") == S3B_EXTERNAL_SOURCE_SIGN, "source sign mismatch")
    require(
        source.get("canonical_key_count") == S3B_EXPECTED_CANONICAL_TRACE_ROWS,
        "source canonical key count mismatch",
    )
    source_row_counts = {
        "active_row_count": S3B_EXPECTED_ACTIVE_ROWS,
        "canonical_trace_row_count": S3B_EXPECTED_CANONICAL_TRACE_ROWS,
        "floquet_slave_row_count": S3B_EXPECTED_FLOQUET_SLAVE_ROWS,
    }
    for key, expected in source_row_counts.items():
        require(source.get(key) == expected, f"source {key} mismatch")
    require(
        source["canonical_trace_row_count"]
        == source["active_row_count"] + source["floquet_slave_row_count"],
        "source row counts do not close",
    )
    extractor_audit = source.get("canonical_extractor_audit")
    require(
        isinstance(extractor_audit, Mapping),
        "source canonical extractor audit must be a mapping",
    )
    require(
        extractor_audit.get("global_packet_count")
        == S3B_EXPECTED_CANONICAL_TRACE_ROWS,
        "source canonical extractor packet count mismatch",
    )
    source_hash_keys = (
        "canonical_key_set_sha256",
        "canonical_value_sha256",
        "source_definition_sha256",
        "source_canonical_identity_sha256",
    )
    source_hashes: dict[str, str] = {}
    for key in source_hash_keys:
        value = source.get(key)
        require(_is_lower_sha256(value), f"source.{key} is not lowercase 64-hex")
        source_hashes[key] = value
    try:
        source_norm = float(source["source_norm"])
    except (KeyError, TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            "S3b J1 baseline manifest invalid: source_norm is not numeric"
        ) from exc
    require(
        math.isfinite(source_norm) and source_norm > 0.0,
        "source_norm must be finite and positive",
    )
    require(source.get("source_finite") is True, "source_finite must be true")
    require(source.get("source_nonzero") is True, "source_nonzero must be true")
    require(
        source.get("resolved_column") == S3B_EXTERNAL_SOURCE_COLUMN,
        "source resolved_column must be 177",
    )
    require(
        source.get("sign_application_count") == 1,
        "source sign_application_count must be one",
    )
    require(
        source.get("extra_sign_applied") is False,
        "source extra_sign_applied must be false",
    )
    require(
        source.get("additional_sign_scale") == 1.0,
        "source additional_sign_scale must be one",
    )
    require(
        source.get("sign_embedded_in")
        == "current_DtnBlockAssembler_C_traction_values",
        "source sign_embedded_in mismatch",
    )
    require(
        source.get("raw_global_row_remap") is False,
        "source raw_global_row_remap must be false",
    )
    require(
        source.get("numeric_allgather") is False,
        "source numeric vector allgather must be false",
    )
    require(
        source.get("full_vector_replication") is False,
        "source full-vector replication must be false",
    )

    fgmres = manifest.get("fgmres")
    require(isinstance(fgmres, Mapping), "fgmres must be a mapping")
    require(fgmres.get("checkpoint_complete") is True, "checkpoint_complete must be true")
    require(fgmres.get("finite") is True, "fgmres finite must be true")
    require(fgmres.get("breakdown") is False, "fgmres breakdown must be false")
    require(fgmres.get("iterations") == S3B_FGMRES_INITIAL_MAX_IT, "iterations must be 64")
    require(fgmres.get("setup_count") == 1, "setup_count must be one")
    require(fgmres.get("setup_reused") is False, "initial setup_reused must be false")
    checkpoints = fgmres.get("checkpoints")
    require(isinstance(checkpoints, Mapping), "fgmres checkpoints must be a mapping")
    for iteration in (8, 16, 32, 64):
        checkpoint = checkpoints.get(str(iteration))
        require(
            isinstance(checkpoint, Mapping),
            f"checkpoint {iteration} is missing",
        )
        for key in ("true_residual_absolute", "true_residual_relative"):
            try:
                residual = float(checkpoint[key])
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise ValueError(
                    "S3b J1 baseline manifest invalid: "
                    f"checkpoint {iteration} {key} is not numeric"
                ) from exc
            require(
                math.isfinite(residual) and residual >= 0.0,
                f"checkpoint {iteration} {key} is not finite/nonnegative",
            )
        require(
            checkpoint.get("finite") is True,
            f"checkpoint {iteration} finite must be true",
        )

    j1 = manifest.get("j1")
    require(isinstance(j1, Mapping), "j1 must be a mapping")
    r64 = j1.get("r64")
    checkpoint_r64 = checkpoints["64"]["true_residual_relative"]
    try:
        r64_value = float(r64)
        checkpoint_r64_value = float(checkpoint_r64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(
            "S3b J1 baseline manifest invalid: r64 is not numeric"
        ) from exc
    require(
        math.isfinite(r64_value) and r64_value >= 0.0,
        "j1.r64 must be finite and nonnegative",
    )
    require(r64 == checkpoint_r64, "j1.r64 must exactly equal checkpoint 64 relative residual")
    require(
        r64_value == checkpoint_r64_value,
        "j1.r64 numeric value differs from checkpoint 64",
    )

    structure = manifest.get("structure")
    require(isinstance(structure, Mapping), "structure must be a mapping")
    require(
        structure.get("j1_layer_factor_count_ready") == 6,
        "J1 ready factor count must be six",
    )
    require(
        structure.get("j1_layer_factor_count_after_cleanup") == 0,
        "J1 after-cleanup factor count must be zero",
    )
    require(
        structure.get("full_cross_section_factor_count_ready") == 6,
        "full-cross-section ready factor count must be six",
    )
    require(
        structure.get("full_cross_section_factor_count_after_cleanup") == 0,
        "full-cross-section after-cleanup factor count must be zero",
    )
    require(
        structure.get("candidate_max_local_rows_gate_status") == "not_applicable",
        "candidate max-local-rows Gate must be not applicable",
    )

    require(
        manifest.get("source_norm") == source.get("source_norm"),
        "top-level source_norm does not bind to source audit",
    )
    require(
        manifest.get("source_canonical_key_set_sha256")
        == source.get("canonical_key_set_sha256"),
        "top-level canonical key hash does not bind to source audit",
    )
    require(
        manifest.get("source_canonical_value_sha256")
        == source.get("canonical_value_sha256"),
        "top-level canonical value hash does not bind to source audit",
    )
    return _jsonable(
        {
            "validated": True,
            "manifest_sha256": observed_manifest_sha256,
            "expected_manifest_sha256": expected_manifest_sha256,
            "observed_manifest_sha256": observed_manifest_sha256,
            "schema": manifest["schema"],
            "method": manifest["method"],
            "route": manifest["route"],
            "j1_r64": r64,
            "source_norm": source_norm,
            "active_row_count": source_row_counts["active_row_count"],
            "canonical_trace_row_count": source_row_counts[
                "canonical_trace_row_count"
            ],
            "floquet_slave_row_count": source_row_counts[
                "floquet_slave_row_count"
            ],
            "source_canonical_key_set_sha256": source_hashes[
                "canonical_key_set_sha256"
            ],
            "source_canonical_value_sha256": source_hashes[
                "canonical_value_sha256"
            ],
            "source_definition_sha256": source_hashes["source_definition_sha256"],
            "source_canonical_identity_sha256": source_hashes[
                "source_canonical_identity_sha256"
            ],
            "source": dict(source),
            "provenance": dict(provenance),
            "fixed_contract": dict(fixed_contract),
            "source_pass": True,
            "provenance_pass": True,
            "factor_bindings_pass": True,
        }
    )


def compare_s3_candidate_source_to_baseline(
    candidate_source_audit: Mapping[str, Any],
    validated_baseline: Mapping[str, Any],
    *,
    relative_tolerance: float = 1.0e-12,
) -> dict[str, Any]:
    """Compare a direct candidate source audit with a validated baseline."""

    if relative_tolerance != 1.0e-12:
        raise ValueError("relative_tolerance is fixed at 1e-12")
    if not isinstance(candidate_source_audit, Mapping):
        raise TypeError("candidate_source_audit must be a direct mapping")
    if not isinstance(validated_baseline, Mapping):
        raise TypeError("validated_baseline must be a mapping")
    if validated_baseline.get("validated") is not True:
        raise ValueError("validated_baseline must have validated=true")
    if "source" not in validated_baseline:
        raise ValueError("validated_baseline lacks its validated source audit")
    baseline_source = validated_baseline["source"]
    if not isinstance(baseline_source, Mapping):
        raise TypeError("validated_baseline source must be a mapping")

    checks: dict[str, bool] = {}
    fixed_identity = {
        "label": S3B_EXTERNAL_SOURCE_LABEL,
        "seed": S3B_EXTERNAL_SOURCE_SEED,
        "column": S3B_EXTERNAL_SOURCE_COLUMN,
        "resolved_column": S3B_EXTERNAL_SOURCE_COLUMN,
        "sign": S3B_EXTERNAL_SOURCE_SIGN,
    }
    for key, expected in fixed_identity.items():
        checks[f"{key}_matches_baseline_and_fixed"] = bool(
            candidate_source_audit.get(key) == baseline_source.get(key)
            and candidate_source_audit.get(key) == expected
        )
    fixed_flags = {
        "sign_application_count": 1,
        "extra_sign_applied": False,
        "raw_global_row_remap": False,
        "additional_sign_scale": 1.0,
        "sign_embedded_in": "current_DtnBlockAssembler_C_traction_values",
    }
    for key, expected in fixed_flags.items():
        checks[f"{key}_matches_baseline_and_fixed"] = bool(
            candidate_source_audit.get(key) == baseline_source.get(key)
            and candidate_source_audit.get(key) == expected
        )
    checks["source_finite_true"] = candidate_source_audit.get("source_finite") is True
    checks["source_nonzero_true"] = candidate_source_audit.get("source_nonzero") is True
    for key in (
        "canonical_key_set_sha256",
        "canonical_value_sha256",
        "source_definition_sha256",
        "source_canonical_identity_sha256",
    ):
        checks[f"{key}_matches_baseline"] = bool(
            _is_lower_sha256(candidate_source_audit.get(key))
            and candidate_source_audit.get(key) == baseline_source.get(key)
        )
    checks["canonical_key_count_matches_baseline_and_fixed"] = bool(
        candidate_source_audit.get("canonical_key_count")
        == baseline_source.get("canonical_key_count")
        == S3B_EXPECTED_CANONICAL_TRACE_ROWS
    )
    for key, expected in (
        ("active_row_count", S3B_EXPECTED_ACTIVE_ROWS),
        ("canonical_trace_row_count", S3B_EXPECTED_CANONICAL_TRACE_ROWS),
        ("floquet_slave_row_count", S3B_EXPECTED_FLOQUET_SLAVE_ROWS),
    ):
        checks[f"{key}_matches_baseline_and_fixed"] = bool(
            candidate_source_audit.get(key) == baseline_source.get(key) == expected
        )
    checks["numeric_vector_value_allgather_false"] = (
        candidate_source_audit.get("numeric_allgather") is False
    )
    checks["full_vector_replication_false"] = (
        candidate_source_audit.get("full_vector_replication") is False
    )

    try:
        candidate_norm = float(candidate_source_audit["source_norm"])
        baseline_norm = float(
            validated_baseline.get("source_norm", baseline_source["source_norm"])
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        candidate_norm = math.nan
        baseline_norm = math.nan
    checks["candidate_source_norm_finite_nonzero"] = bool(
        math.isfinite(candidate_norm) and candidate_norm > 0.0
    )
    checks["baseline_source_norm_finite_nonzero"] = bool(
        math.isfinite(baseline_norm) and baseline_norm > 0.0
    )
    if math.isfinite(candidate_norm) and math.isfinite(baseline_norm):
        relative_error = abs(candidate_norm - baseline_norm) / max(
            abs(baseline_norm), np.finfo(float).tiny
        )
    else:
        relative_error = math.inf
    checks["source_norm_relative_error_within_1e-12"] = bool(
        math.isfinite(relative_error) and relative_error <= 1.0e-12
    )

    return _jsonable(
        {
            "pass": all(checks.values()),
            "checks": checks,
            "relative_norm_error": relative_error,
            "candidate_source_norm": candidate_norm,
            "baseline_source_norm": baseline_norm,
        }
    )


def _qualify_s3_b1_remaining_sources(
    operator: PETSc.Mat,
    service: Any,
    source_factory: S3CurrentLayoutSourceFactory,
    external_conditional_outcome: Mapping[str, Any],
    external_conditional_gate: Mapping[str, Any],
    *,
    marker_callback: Any,
) -> dict[str, Any]:
    """Qualify the four non-external V5 sources on one borrowed service."""

    comm = operator.getComm().tompi4py()
    local_exception = None
    try:
        if not callable(marker_callback):
            raise TypeError("four-source marker_callback must be callable on every rank")
        if not isinstance(external_conditional_outcome, Mapping) or not isinstance(
            external_conditional_gate, Mapping
        ):
            raise TypeError("four-source Gate inputs must be mappings")
        if (
            external_conditional_gate.get("classification") != S3B_CONDITIONAL_PASS
            or external_conditional_gate.get("positive") is not True
            or external_conditional_gate.get("next_stage") != S3B_NEXT_FIVE_SOURCE_BOTTOM
        ):
            raise ValueError("four-source qualification requires the passed five-source Gate")
    except Exception as exc:
        local_exception = exc
    _raise_collective_error(
        comm, "four-source qualification precondition", local_exception
    )

    from .hybrid_bare_f_authority import V5_BARE_F_SOURCE_LABELS

    source_labels = tuple(str(label) for label in V5_BARE_F_SOURCE_LABELS)
    remaining_labels = tuple(label for label in source_labels if label != S3B_EXTERNAL_SOURCE_LABEL)

    def gate_outcome(result: Mapping[str, Any]) -> dict[str, Any]:
        return {
            key: result.get(key)
            for key in (
                "postsolve",
                "finite",
                "checkpoint_complete",
                "breakdown",
                "happy_breakdown",
            )
        }

    def emit(stage: str, payload: Mapping[str, Any] | None = None) -> None:
        marker_callback(stage, _jsonable(dict(payload or {})))

    service_apply_before = _action_count(service)
    source_audits: dict[str, Any] = {}
    source_outcomes: dict[str, Any] = dict.fromkeys(source_labels)
    source_outcomes[S3B_EXTERNAL_SOURCE_LABEL] = gate_outcome(external_conditional_outcome)
    per_source: dict[str, dict[str, Any]] = {}
    emit("s3b_b1_four_source_begin", {"source_order": list(source_labels)})

    for label in remaining_labels:
        source = solver = None
        source_audit = initial = conditional = None
        setup_count = None
        full_initial = source_destroyed = solver_destroyed = False
        try:
            emit(f"s3b_b1_four_source_{label}_begin", {"label": label})
            source, source_audit = source_factory.build(label)
            source_audits[label] = _jsonable(source_audit)
            emit(
                f"s3b_b1_four_source_{label}_ready",
                {"label": label, "source_audit": source_audit},
            )

            solver = S3FixedRightFgmres(operator, service)
            setup_count = int(solver.diagnostics["setup_count"])
            if setup_count != 1:
                raise RuntimeError(f"four-source solver setup count is not one for {label}")
            emit(
                f"s3b_b1_four_source_{label}_fgmres_setup",
                {
                    "label": label,
                    "setup_count": setup_count,
                    "service_setup_reused": True,
                    "ksp_reused": False,
                },
            )

            def checkpoint_callback(
                row: Mapping[str, Any], _label: str = label
            ) -> None:
                emit(
                    f"s3b_b1_four_source_{_label}_r{int(row['iteration'])}",
                    {"label": _label, "checkpoint": row},
                )

            initial = solver.solve_initial(
                source, label, checkpoint_callback=checkpoint_callback
            )
            full_initial = bool(
                initial.get("iterations") == S3B_FGMRES_INITIAL_MAX_IT
                and initial.get("checkpoint_complete") is True
                and initial.get("finite") is True
                and initial.get("breakdown") is False
            )
            if full_initial:
                conditional = solver.solve_conditional_to_256(
                    source,
                    label,
                    initial_gate=None,
                    checkpoint_callback=checkpoint_callback,
                    fixed_five_source_qualification=True,
                )
                if (
                    conditional.get("fixed_five_source_qualification") is not True
                    or conditional.get("setup_count") != 1
                    or conditional.get("setup_reused") is not True
                ):
                    raise RuntimeError(
                        f"four-source fixed continuation contract failed for {label}"
                    )
            final_result = conditional if conditional is not None else initial
            if not isinstance(final_result, Mapping):
                raise TypeError(f"four-source solve returned no result for {label}")
            source_outcomes[label] = gate_outcome(final_result)
            emit(
                f"s3b_b1_four_source_{label}_solve_end",
                {
                    "label": label,
                    "leg": "conditional" if conditional is not None else "initial",
                    "full_initial": full_initial,
                    "early_happy": bool(
                        initial.get("happy_breakdown") is True
                        and int(
                            initial.get("iterations", S3B_FGMRES_INITIAL_MAX_IT)
                        )
                        < S3B_FGMRES_INITIAL_MAX_IT
                    ),
                },
            )
        finally:
            cleanup_messages: list[str] = []
            for name, obj in (("solver", solver), ("source", source)):
                if obj is None:
                    continue
                try:
                    obj.destroy()
                    if name == "solver":
                        solver_destroyed = True
                    else:
                        source_destroyed = True
                except Exception as exc:
                    cleanup_messages.append(f"{name}: {type(exc).__name__}: {exc}")
            _raise_collective_error(
                comm,
                f"four-source {label} cleanup",
                RuntimeError("; ".join(cleanup_messages)) if cleanup_messages else None,
            )
            per_source[label] = {
                "initial": _jsonable(initial),
                "conditional": _jsonable(conditional),
                "continuation_attempted": conditional is not None,
                "setup_count": setup_count,
                "setup_reused": conditional is not None and conditional.get("setup_reused") is True,
                "service_setup_reused": True,
                "ksp_reused": False,
                "solver_destroyed": solver_destroyed,
                "source_destroyed": source_destroyed,
            }
            emit(
                f"s3b_b1_four_source_{label}_cleanup",
                {
                    "label": label,
                    "solver_destroyed": solver_destroyed,
                    "source_destroyed": source_destroyed,
                },
            )

    if any(value is None for value in source_outcomes.values()):
        raise RuntimeError("four-source qualification left a V5 source outcome unset")
    final_gate = adjudicate_s3_b1_final_five_source_bare_f_gate(
        source_outcomes, resource_ok=True
    )
    emit(
        "s3b_b1_four_source_final_gate",
        {"final_gate": final_gate},
    )
    service_apply_after = _action_count(service)
    service_apply_delta = (
        service_apply_after - service_apply_before
        if service_apply_before is not None and service_apply_after is not None
        else None
    )
    return _jsonable(
        {
            "external_conditional_gate": external_conditional_gate,
            "source_order": list(source_labels),
            "source_audits": source_audits,
            "source_outcomes": source_outcomes,
            "per_source": per_source,
            "final_gate": final_gate,
            "classification": final_gate["classification"],
            "positive": final_gate["positive"],
            "next_stage": final_gate["next_stage"],
            "service_apply_count_before": service_apply_before,
            "service_apply_count_after": service_apply_after,
            "service_apply_count_delta": service_apply_delta,
            "operator_borrowed": True,
            "service_borrowed": True,
            "factory_released": False,
        }
    )


def _run_s3_b1_candidate_external_core(
    cfg: Any,
    profile: Any,
    *,
    comm: Any,
    source_sha: str,
    input_path: Any,
    input_sha256: str,
    physical_model_sha256: str,
    validated_baseline: Mapping[str, Any],
    marker_callback: Any,
    resource_callback: Any,
    source_work_directory: str | Path | None = None,
    selected_mode_provider: Any | None = None,
) -> dict[str, Any]:
    """Run the internal B1 external core with conditional five-source continuation."""

    if int(comm.size) != S3B_MPI_SIZE:
        raise ValueError(
            f"S3b B1 external core requires MPI size {S3B_MPI_SIZE}, got {comm.size}"
        )
    marker_validity = comm.allgather(
        {
            "rank": int(comm.rank),
            "valid": (
                callable(marker_callback)
                if int(comm.rank) == 0
                else marker_callback is None or callable(marker_callback)
            ),
        }
    )
    invalid_marker = next(
        (packet for packet in marker_validity if not packet["valid"]),
        None,
    )
    if invalid_marker is not None:
        raise TypeError(
            "S3b B1 external core marker_callback contract failed on rank "
            f"{int(invalid_marker['rank'])}"
        )
    resource_validity = comm.allgather(
        {
            "rank": int(comm.rank),
            "valid": bool(callable(resource_callback)),
        }
    )
    invalid_resource = next(
        (packet for packet in resource_validity if not packet["valid"]),
        None,
    )
    if invalid_resource is not None:
        raise TypeError(
            "S3b B1 external core resource_callback must be callable on every rank; "
            f"invalid rank {int(invalid_resource['rank'])}"
        )

    baseline_error = None
    try:
        if not isinstance(validated_baseline, Mapping):
            raise TypeError("validated_baseline must be a mapping")
        if validated_baseline.get("validated") is not True:
            raise ValueError("validated_baseline must have validated=true")
        baseline_provenance = validated_baseline.get("provenance")
        if not isinstance(baseline_provenance, Mapping):
            raise TypeError("validated_baseline provenance is missing")
        expected_binding = {
            "source_sha": str(source_sha),
            "input_path": str(input_path),
            "input_sha256": str(input_sha256),
            "physical_model_sha256": str(physical_model_sha256),
        }
        for key, expected in expected_binding.items():
            if baseline_provenance.get(key) != expected:
                raise ValueError(
                    f"validated_baseline provenance.{key} differs from current input"
                )
    except Exception as exc:
        baseline_error = exc
    _raise_collective_error(comm, "validated baseline binding", baseline_error)

    formal_started = perf_counter()
    marker_state: dict[str, Any] = {
        "resource_stop": False,
        "markers": [],
        "last_resource": None,
    }
    context = None
    operator = None
    service = None
    source = None
    solver = None
    source_factory = None
    source_factory_snapshot = source_factory_release = None
    five_source_attempted = five_source_completed = False
    five_source_result: dict[str, Any] = {}
    candidate_source_audit: dict[str, Any] = {}
    candidate_comparison: dict[str, Any] = {}
    one_apply: dict[str, Any] = {}
    initial: dict[str, Any] = {}
    conditional: dict[str, Any] = {}
    initial_gate: dict[str, Any] = {}
    conditional_gate: dict[str, Any] = {}
    formal_exception: Exception | None = None
    initial_positive = False
    conditional_attempted = False
    conditional_positive = False
    baseline_identity_keys = (
        "manifest_sha256",
        "j1_r64",
        "source_norm",
        "source_canonical_key_set_sha256",
        "source_canonical_value_sha256",
        "source_definition_sha256",
        "source_canonical_identity_sha256",
        "source_sha",
        "input_path",
        "input_sha256",
        "physical_model_sha256",
    )
    baseline_identity = {
        key: (
            baseline_provenance.get(key)
            if key in {
                "source_sha",
                "input_path",
                "input_sha256",
                "physical_model_sha256",
            }
            else validated_baseline.get(key)
        )
        for key in baseline_identity_keys
    }
    baseline_identity_packets = comm.allgather(baseline_identity)
    if any(packet != baseline_identity_packets[0] for packet in baseline_identity_packets[1:]):
        raise RuntimeError("validated baseline identity differs across MPI ranks")
    cleanup_marker_error: Exception | None = None
    cleanup_errors: list[dict[str, Any]] = []

    def current_apply_counts() -> tuple[int, int]:
        pc_count = _action_count(solver, "pc_apply_count")
        service_count = _action_count(service)
        return (
            0 if pc_count is None else pc_count,
            0 if service_count is None else service_count,
        )

    def mark(stage: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        local_exception = None
        local_resource: Mapping[str, Any] | None = None
        try:
            returned = resource_callback()
            if not isinstance(returned, Mapping):
                raise TypeError("resource_callback must return a mapping")
            local_resource = returned
        except Exception as exc:
            local_exception = exc
        resource_packets = comm.allgather(
            {
                "rank": int(comm.rank),
                "error": _error_packet(comm, local_exception),
                "rss": (
                    math.nan
                    if local_resource is None
                    else _resource_number(
                        local_resource,
                        ("rss_bytes", "peak_rss_bytes", "process_tree_rss_bytes"),
                        gib_keys=("rss_gib", "peak_rss_gib"),
                    )
                ),
                "swap": (
                    math.nan
                    if local_resource is None
                    else _resource_number(
                        local_resource,
                        ("swap_bytes", "peak_swap_bytes", "process_tree_swap_bytes"),
                        gib_keys=("swap_gib", "peak_swap_gib"),
                    )
                ),
            }
        )
        first_resource_error = next(
            (packet["error"] for packet in resource_packets if packet["error"]),
            None,
        )
        if first_resource_error is not None:
            error = RuntimeError(
                "S3b B1 external core resource callback failed on rank "
                f"{int(first_resource_error['rank'])} "
                f"{first_resource_error['type']}: {first_resource_error['message']}"
            )
            if local_exception is not None:
                raise error from local_exception
            raise error
        rss_values = [float(packet["rss"]) for packet in resource_packets]
        swap_values = [float(packet["swap"]) for packet in resource_packets]
        rss_ok = all(math.isfinite(value) and value >= 0.0 for value in rss_values)
        swap_ok = all(math.isfinite(value) and value >= 0.0 for value in swap_values)
        rss_max = max(rss_values) if rss_ok else math.nan
        swap_max = max(swap_values) if swap_ok else math.nan
        elapsed_wall = float(
            comm.allreduce(perf_counter() - formal_started, op=MPI.MAX)
        )
        pc_count, service_count = current_apply_counts()
        pc_max = int(comm.allreduce(pc_count, op=MPI.MAX))
        service_max = int(comm.allreduce(service_count, op=MPI.MAX))
        marker_payload = dict(payload or {})
        marker_payload.update(
            {
                "elapsed_wall_seconds": elapsed_wall,
                "wall_seconds": elapsed_wall,
                "rss_bytes": int(rss_max) if math.isfinite(rss_max) else None,
                "swap_bytes": int(swap_max) if math.isfinite(swap_max) else None,
                "pc_apply_count": pc_max,
                "service_apply_count": service_max,
                "apply_count": max(pc_max, service_max),
            }
        )
        marker_state["last_resource"] = {
            "elapsed_wall_seconds": elapsed_wall,
            "rss_bytes": marker_payload["rss_bytes"],
            "swap_bytes": marker_payload["swap_bytes"],
            "pc_apply_count": pc_max,
            "service_apply_count": service_max,
        }
        failures: list[str] = []
        if not rss_ok or rss_max >= S3B_RSS_HARD_BYTES:
            failures.append("rss_hard_limit" if rss_ok else "rss_unavailable")
        if not swap_ok or swap_max != S3B_SWAP_LIMIT_BYTES:
            failures.append("swap_nonzero" if swap_ok else "swap_unavailable")
        if not math.isfinite(elapsed_wall) or elapsed_wall >= S3B_WALL_CAP_SECONDS:
            failures.append("wall_cap")
        failures = sorted(set(failures))
        if failures:
            marker_state["resource_stop"] = True
            stop_payload = {
                **marker_payload,
                "attempted_stage": stage,
                "resource_gate": "failed",
                "resource_failure": failures,
                "rss_hard_bytes": int(S3B_RSS_HARD_BYTES),
                "swap_limit_bytes": int(S3B_SWAP_LIMIT_BYTES),
                "wall_cap_seconds": int(S3B_WALL_CAP_SECONDS),
            }
            callback_exception = None
            if comm.rank == 0:
                try:
                    marker_callback("s3b_b1_resource_stop", _jsonable(stop_payload))
                except Exception as exc:
                    callback_exception = exc
            callback_packets = comm.allgather(
                _error_packet(comm, callback_exception)
            )
            first_callback_error = next(
                (packet for packet in callback_packets if packet is not None),
                None,
            )
            if first_callback_error is not None:
                raise RuntimeError(
                    "S3b B1 resource-stop marker failed on rank "
                    f"{int(first_callback_error['rank'])} "
                    f"{first_callback_error['type']}: "
                    f"{first_callback_error['message']}"
                )
            raise RuntimeError(
                "S3b B1 external core resource Gate stopped at "
                f"{stage}: {', '.join(failures)}"
            )
        callback_exception = None
        if comm.rank == 0:
            try:
                marker_callback(stage, _jsonable(marker_payload))
            except Exception as exc:
                callback_exception = exc
        callback_packets = comm.allgather(_error_packet(comm, callback_exception))
        first_callback_error = next(
            (packet for packet in callback_packets if packet is not None),
            None,
        )
        if first_callback_error is not None:
            error = RuntimeError(
                f"S3b B1 marker {stage} failed on rank "
                f"{int(first_callback_error['rank'])} "
                f"{first_callback_error['type']}: {first_callback_error['message']}"
            )
            if callback_exception is not None:
                raise error from callback_exception
            raise error
        marker_state["markers"].append(stage)
        return marker_payload

    def context_progress(event: Mapping[str, Any]) -> None:
        if not isinstance(event, Mapping) or not isinstance(event.get("stage"), str):
            raise TypeError("candidate context progress must contain a stage")
        stage = event["stage"]
        payload = {key: value for key, value in event.items() if key != "stage"}
        mark(stage, payload)

    def destroy_collective(name: str, obj: Any) -> None:
        local_exception = None
        if obj is not None:
            try:
                obj.destroy()
            except Exception as exc:
                local_exception = exc
        packets = comm.allgather(_error_packet(comm, local_exception))
        cleanup_errors.extend(
            {
                "object": name,
                "rank": int(packet["rank"]),
                "type": packet["type"],
                "message": packet["message"],
            }
            for packet in packets
            if packet is not None
        )

    def snapshot_and_release_source_factory_collective() -> None:
        nonlocal source_factory_snapshot, source_factory_release
        snapshot_exception = release_exception = None
        if source_factory is not None:
            try:
                source_inventory = source_factory.source_inventory
                source_counts = source_inventory["source_build_counts"]
                external_build_count = source_counts.get(S3B_EXTERNAL_SOURCE_LABEL)
                source_factory_snapshot = _jsonable(
                    {
                        "construction_inventory": deepcopy(
                            source_factory.construction_inventory
                        ),
                        "source_inventory": deepcopy(source_inventory),
                        "external_source_reused": external_build_count == 0,
                        "external_source_build_count": external_build_count,
                    }
                )
            except Exception as exc:
                snapshot_exception = exc
            try:
                source_factory_release = source_factory.release()
            except Exception as exc:
                release_exception = exc
        packets = comm.allgather(
            {
                "snapshot": _error_packet(comm, snapshot_exception),
                "release": _error_packet(comm, release_exception),
            }
        )
        cleanup_errors.extend(
            {"object": name, **packet[key]}
            for packet in packets
            for key, name in (
                ("snapshot", "source_factory_snapshot"),
                ("release", "source_factory"),
            )
            if packet[key] is not None
        )

    try:
        mark(
            "s3b_b1_baseline_validated",
            {
                "baseline_manifest_sha256": validated_baseline.get("manifest_sha256"),
                "baseline_j1_r64": validated_baseline.get("j1_r64"),
                "baseline_validated": True,
            },
        )
        context = build_s3_b1_candidate_context(
            cfg,
            profile,
            comm=comm,
            progress_callback=context_progress,
        )
        operator = context.target_operator
        service = context.service
        if not isinstance(operator, PETSc.Mat) or service is None:
            raise RuntimeError("S3b B1 candidate context has no target operator/service")
        ready_inventory = context.ready_inventory
        mark("s3b_b1_context_ready", {"ready_inventory": ready_inventory})

        source, candidate_source_audit = build_s3_external_dtn_source(
            context.target_system
        )
        candidate_comparison = compare_s3_candidate_source_to_baseline(
            candidate_source_audit,
            validated_baseline,
            relative_tolerance=1.0e-12,
        )
        comparison_packets = comm.allgather(
            {
                "rank": int(comm.rank),
                "pass": candidate_comparison.get("pass") is True,
                "failed_checks": [
                    key
                    for key, value in candidate_comparison.get("checks", {}).items()
                    if value is not True
                ],
            }
        )
        comparison_collective_pass = all(
            packet.get("pass") is True for packet in comparison_packets
        )
        candidate_comparison["collective_pass"] = comparison_collective_pass
        candidate_comparison["rank_summaries"] = comparison_packets
        if comparison_collective_pass:
            mark(
                "s3b_b1_source_ready",
                {
                    "source": candidate_source_audit,
                    "comparison": candidate_comparison,
                },
            )
        else:
            mark(
                "s3b_b1_source_identity_failure",
                {
                    "comparison": candidate_comparison,
                    "rank_summaries": comparison_packets,
                },
            )
            raise RuntimeError("S3b B1 candidate source identity comparison failed")

        mark(
            "s3b_b1_one_apply_begin",
            {
                "operator_identity": "target_system.fine_action",
                "service_identity": "target_bounded_harmonic_service",
            },
        )
        one_apply = audit_s3_preconditioner_one_apply(
            operator,
            source,
            service,
            S3B_EXTERNAL_SOURCE_LABEL,
        )
        if one_apply.get("operator_matvec_count") != 1:
            raise RuntimeError("S3b B1 one-apply audit did not perform one operator matvec")
        if one_apply.get("action_apply_count_exactly_one") is not True:
            raise RuntimeError("S3b B1 one-apply audit did not prove one service apply")
        mark("s3b_b1_one_apply_end", {"one_apply": one_apply})

        solver = S3FixedRightFgmres(operator, service)
        if solver.diagnostics.get("setup_count") != 1:
            raise RuntimeError("S3b B1 FGMRES setup count is not one")
        mark(
            "s3b_b1_fgmres_setup",
            {
                "setup_count": int(solver.diagnostics["setup_count"]),
                "restart": int(S3B_FGMRES_RESTART),
                "max_it": int(S3B_FGMRES_INITIAL_MAX_IT),
                "solver": solver.diagnostics,
            },
        )

        def checkpoint_callback(row: Mapping[str, Any]) -> None:
            iteration = int(row["iteration"])
            stage = "s3b_b1_r0" if iteration == 0 else f"s3b_b1_r{iteration}"
            mark(stage, {"checkpoint": row})

        initial = solver.solve_initial(
            source,
            S3B_EXTERNAL_SOURCE_LABEL,
            checkpoint_callback=checkpoint_callback,
        )
        mark("s3b_b1_solve_end", {"leg": "initial", "fgmres": initial})
        initial_checkpoints = initial.get("checkpoints", {})
        if not isinstance(initial_checkpoints, Mapping):
            initial_checkpoints = {}
        initial_checkpoint64 = initial_checkpoints.get("64")
        candidate_r64 = None
        if isinstance(initial_checkpoint64, Mapping):
            try:
                candidate_r64 = float(initial_checkpoint64["true_residual_relative"])
            except (KeyError, TypeError, ValueError, OverflowError):
                candidate_r64 = None
        initial_gate = adjudicate_s3_b1_initial_gate(
            float(validated_baseline["j1_r64"]),
            candidate_r64,
            finite=initial.get("finite") is True,
            breakdown=initial.get("breakdown") is True,
            resource_ok=True,
        )
        if "classification" not in initial_gate or "next_stage" not in initial_gate:
            raise RuntimeError("S3b B1 initial Gate result lacks classification/next_stage")
        mark("s3b_b1_initial_gate", {"gate": initial_gate})
        initial_positive = initial_gate.get("positive") is True
        conditional_positive = False
        if initial_positive:
            conditional_attempted = True
            conditional = solver.solve_conditional_to_256(
                source,
                S3B_EXTERNAL_SOURCE_LABEL,
                initial_gate=initial_gate,
                checkpoint_callback=checkpoint_callback,
            )
            if (
                conditional.get("setup_count") != 1
                or conditional.get("setup_reused") is not True
            ):
                raise RuntimeError(
                    "S3b B1 conditional solve did not reuse the fixed setup"
            )
            mark("s3b_b1_solve_end", {"leg": "conditional", "fgmres": conditional})
            conditional_checkpoints = conditional.get("checkpoints", {})
            if not isinstance(conditional_checkpoints, Mapping):
                conditional_checkpoints = {}
            conditional_checkpoint256 = conditional_checkpoints.get("256")
            candidate_r256 = None
            if isinstance(conditional_checkpoint256, Mapping):
                try:
                    candidate_r256 = float(
                        conditional_checkpoint256["true_residual_relative"]
                    )
                except (KeyError, TypeError, ValueError, OverflowError):
                    candidate_r256 = None
            conditional_gate = adjudicate_s3_b1_conditional_gate(
                candidate_r256,
                finite=conditional.get("finite") is True,
                resource_ok=True,
            )
            if (
                "classification" not in conditional_gate
                or "next_stage" not in conditional_gate
            ):
                raise RuntimeError(
                    "S3b B1 conditional Gate result lacks classification/next_stage"
                )
            mark("s3b_b1_conditional_gate", {"gate": conditional_gate})
            conditional_positive = conditional_gate.get("positive") is True
            if (
                conditional_positive
                and conditional_gate["next_stage"] != S3B_NEXT_FIVE_SOURCE_BOTTOM
            ):
                raise RuntimeError(
                    "S3b B1 conditional pass has an unexpected next stage"
                )
            if conditional_positive:
                five_source_attempted = True
                source_factory = S3CurrentLayoutSourceFactory(
                    context.target_system,
                    source_work_directory=source_work_directory,
                    selected_mode_provider=selected_mode_provider,
                )
                source_counts = source_factory.source_inventory["source_build_counts"]
                if source_counts.get(S3B_EXTERNAL_SOURCE_LABEL) != 0:
                    raise RuntimeError(
                        "S3b source factory unexpectedly rebuilt the external source"
                    )
                mark(
                    "s3b_b1_source_factory_ready",
                    {
                        "source_factory": {
                            "external_source_reused": True,
                            "external_source_build_count": 0,
                        }
                    },
                )
                five_source_result = _qualify_s3_b1_remaining_sources(
                    operator, service, source_factory, conditional, conditional_gate,
                    marker_callback=mark,
                )
                if (
                    not isinstance(five_source_result, Mapping)
                    or not isinstance(five_source_result.get("final_gate"), Mapping)
                    or source_counts.get(S3B_EXTERNAL_SOURCE_LABEL) != 0
                ):
                    raise RuntimeError("S3b five-source helper/count contract failed")
                five_source_completed = True
    except Exception as exc:
        formal_exception = exc
    finally:
        try:
            if not marker_state["resource_stop"]:
                mark(
                    "s3b_b1_cleanup_begin",
                    {
                        "solver_present": solver is not None,
                        "source_present": source is not None,
                        "context_present": context is not None,
                    },
                )
        except Exception as exc:
            cleanup_marker_error = exc
        solver_before_destroy = (
            _jsonable(solver.diagnostics) if solver is not None else None
        )
        service_apply_count_before_cleanup = _action_count(service)
        destroy_collective("solver", solver)
        destroy_collective("source", source)
        snapshot_and_release_source_factory_collective()
        destroy_collective("context", context)
        solver_after_destroy = (
            _jsonable(solver.diagnostics) if solver is not None else None
        )
        service_apply_count_after_cleanup = _action_count(service)
        context_after_cleanup = (
            context.after_cleanup_inventory if context is not None else None
        )
        source_destroyed = bool(
            source is not None
            and not any(
                isinstance(item, Mapping) and item.get("object") == "source"
                for item in cleanup_errors
            )
        )
        solver_vectors_ready = 3 if solver_before_destroy is not None else 0
        solver_vectors_after_cleanup = (
            0
            if solver_before_destroy is not None
            and not any(
                isinstance(item, Mapping) and item.get("object") == "solver"
                for item in cleanup_errors
            )
            else None
        )
        if not marker_state["resource_stop"]:
            try:
                mark(
                    "s3b_b1_cleanup_complete",
                    {
                        "solver_before_destroy": solver_before_destroy,
                        "solver_after_destroy": solver_after_destroy,
                        "source_factory_created": source_factory is not None,
                        "source_factory_release": source_factory_release,
                        "five_source_attempted": five_source_attempted,
                        "five_source_completed": five_source_completed,
                        "context_after_cleanup": context_after_cleanup,
                        "cleanup_errors": cleanup_errors,
                        "source_destroyed": source_destroyed,
                        "solver_vectors_ready": solver_vectors_ready,
                        "solver_vectors_after_cleanup": solver_vectors_after_cleanup,
                        "service_apply_count_before_cleanup": (
                            service_apply_count_before_cleanup
                        ),
                        "service_apply_count_after_cleanup": (
                            service_apply_count_after_cleanup
                        ),
                    },
                )
            except Exception as exc:
                cleanup_marker_error = exc

    final_error_packets = comm.allgather(
        _error_packet(comm, cleanup_marker_error or formal_exception)
    )
    formal_exception_identity = next(
        (packet for packet in final_error_packets if packet is not None),
        None,
    )
    if formal_exception_identity is None and cleanup_errors:
        first_cleanup_error = cleanup_errors[0]
        formal_exception_identity = {
            "rank": int(first_cleanup_error.get("rank", 0)),
            "type": str(first_cleanup_error.get("type", "RuntimeError")),
            "message": str(first_cleanup_error.get("message", "cleanup failed")),
        }
    if formal_exception_identity is not None:
        formal_exception = RuntimeError(
            "S3b B1 external core failed on rank "
            f"{int(formal_exception_identity['rank'])} "
            f"{formal_exception_identity['type']}: "
            f"{formal_exception_identity['message']}"
        )
    if marker_state["resource_stop"]:
        if formal_exception is not None:
            raise formal_exception
        raise RuntimeError("S3b B1 external core stopped by resource Gate")

    final_gate = (
        five_source_result.get("final_gate")
        if five_source_completed
        else conditional_gate
        if conditional_attempted
        else initial_gate
    )
    positive = False
    if formal_exception is not None:
        classification = "S3B_B1_EXTERNAL_CORE_IMPLEMENTATION_FAILURE"
        next_stage = None
    else:
        try:
            classification = str(final_gate["classification"])
            next_stage = final_gate["next_stage"]
            positive = final_gate["positive"] is True
        except (KeyError, TypeError) as exc:
            classification = "S3B_B1_EXTERNAL_CORE_IMPLEMENTATION_FAILURE"
            next_stage = None
            positive = False
            formal_exception_identity = {
                "rank": int(comm.rank),
                "type": type(exc).__name__,
                "message": str(exc),
            }
    if formal_exception is not None:
        next_stage = None
    ready_inventory = context.ready_inventory if context is not None else None
    after_cleanup_inventory = (
        context.after_cleanup_inventory if context is not None else None
    )
    operator_borrowed_by_solver = bool(operator is not None and solver is not None)
    operator_destroyed_with_owning_system = bool(
        isinstance(after_cleanup_inventory, Mapping)
        and after_cleanup_inventory.get("target_system_destroyed") is True
    )
    return _jsonable(
        {
            "schema": "task040.v9_e.s3b_b1_external_core.v1",
            "method": "task040_v9_e_s3b_b1_external_core",
            "route": "V9_E_S3B",
            "classification": classification,
            "positive": bool(positive) if formal_exception is None else False,
            "external_core_not_standalone_formal": True,
            "next_stage": next_stage,
            "five_source_continuation_required": bool(conditional_positive),
            "conditional_attempted": bool(conditional_attempted),
            "five_source_attempted": bool(five_source_attempted),
            "five_source_completed": bool(five_source_completed),
            "five_source_result": five_source_result,
            "source_factory": {
                "created": source_factory is not None,
                "construction_snapshot": source_factory_snapshot,
                "release": source_factory_release,
                "external_source_reused": (
                    source_factory_snapshot.get("external_source_reused")
                    if isinstance(source_factory_snapshot, Mapping)
                    else None
                ),
            },
            "provenance": {
                "source_sha": str(source_sha),
                "input_path": str(input_path),
                "input_sha256": str(input_sha256),
                "physical_model_sha256": str(physical_model_sha256),
                "mpi_size": int(comm.size),
                "threads": 1,
                "side": "bottom",
                "operator_identity": "target_system.fine_action",
                "full_A_used": False,
                "qep_calls": 0,
            },
            "validated_baseline": {
                "validated": validated_baseline.get("validated") is True,
                "manifest_sha256": validated_baseline.get("manifest_sha256"),
                "j1_r64": validated_baseline.get("j1_r64"),
                "source_norm": validated_baseline.get("source_norm"),
                "source_canonical_key_set_sha256": validated_baseline.get(
                    "source_canonical_key_set_sha256"
                ),
                "source_canonical_value_sha256": validated_baseline.get(
                    "source_canonical_value_sha256"
                ),
                "source_definition_sha256": validated_baseline.get(
                    "source_definition_sha256"
                ),
                "source_canonical_identity_sha256": validated_baseline.get(
                    "source_canonical_identity_sha256"
                ),
            },
            "candidate_source": candidate_source_audit,
            "candidate_source_comparison": candidate_comparison,
            "one_apply": one_apply,
            "initial": initial,
            "conditional": conditional,
            "initial_gate": initial_gate,
            "conditional_gate": conditional_gate,
            "context": {
                "ready_inventory": ready_inventory,
                "after_cleanup_inventory": after_cleanup_inventory,
            },
            "lifecycle": {
                "factor_count_ready": (
                    ready_inventory.get("factor_count_ready")
                    if isinstance(ready_inventory, Mapping)
                    else None
                ),
                "factor_count_after_cleanup": (
                    after_cleanup_inventory.get("factor_count_after_cleanup")
                    if isinstance(after_cleanup_inventory, Mapping)
                    else None
                ),
                "full_side_exact_factor_count": 0,
                "full_cross_section_factor_count": 0,
                "global_direct_factor_count": 0,
                "global_coarse_factor_count": 0,
                "solver_vectors_ready": solver_vectors_ready,
                "solver_vectors_after_cleanup": solver_vectors_after_cleanup,
                "solver_diagnostics_before_destroy": solver_before_destroy,
                "solver_diagnostics_after_destroy": solver_after_destroy,
                "source_destroyed": source_destroyed,
                "operator_borrowed_by_solver": operator_borrowed_by_solver,
                "operator_destroyed_with_owning_system": (
                    operator_destroyed_with_owning_system
                ),
                "service_apply_count_before_cleanup": (
                    service_apply_count_before_cleanup
                ),
                "service_apply_count_after_cleanup": service_apply_count_after_cleanup,
            },
            "resources": marker_state["last_resource"],
            "markers": list(marker_state["markers"]),
            "cleanup_errors": cleanup_errors,
            "formal_exception_identity": formal_exception_identity,
            "error": formal_exception_identity,
        }
    )


def run_s3_j1_baseline_formal(
    cfg: Any,
    profile: Any,
    *,
    comm: Any,
    source_sha: str,
    input_path: Any,
    input_sha256: str,
    physical_model_sha256: str,
    marker_callback: Any,
    resource_callback: Any,
) -> dict[str, Any]:
    """Run the fixed bottom/J1 S3b baseline and return a JSON-able record."""

    if int(comm.size) != S3B_MPI_SIZE:
        raise ValueError(
            f"S3b J1 formal requires MPI size {S3B_MPI_SIZE}, got {comm.size}"
        )
    marker_valid = (
        callable(marker_callback)
        if int(comm.rank) == 0
        else marker_callback is None or callable(marker_callback)
    )
    marker_validity = comm.allgather(
        {
            "rank": int(comm.rank),
            "valid": bool(marker_valid),
        }
    )
    invalid_marker = next(
        (packet for packet in marker_validity if not packet["valid"]),
        None,
    )
    if invalid_marker is not None:
        raise TypeError(
            "S3b J1 formal marker_callback contract failed on rank "
            f"{int(invalid_marker['rank'])}: rank zero requires a callable; "
            "non-root ranks require None or a callable"
        )
    resource_validity = comm.allgather(
        {
            "rank": int(comm.rank),
            "valid": bool(callable(resource_callback)),
        }
    )
    invalid_resource = next(
        (packet for packet in resource_validity if not packet["valid"]),
        None,
    )
    if invalid_resource is not None:
        raise TypeError(
            "S3b J1 formal resource_callback must be callable on every rank; "
            f"invalid rank {int(invalid_resource['rank'])}"
        )

    formal_started = perf_counter()
    marker_state: dict[str, Any] = {
        "resource_stop": False,
        "markers": [],
        "last_resource": None,
    }
    system = None
    source = None
    j1_action = None
    solver = None
    operator = None
    source_audit: dict[str, Any] = {}
    j1_audit: dict[str, Any] = {}
    one_apply: dict[str, Any] = {}
    fgmres: dict[str, Any] = {}
    formal_exception: Exception | None = None
    cleanup_errors: list[dict[str, Any]] = []
    cleanup_marker_error: Exception | None = None
    formal_exception_identity: dict[str, Any] | None = None

    def current_apply_counts() -> tuple[int, int]:
        pc_count = _action_count(solver, "pc_apply_count")
        action_count = _action_count(j1_action)
        return (0 if pc_count is None else pc_count, 0 if action_count is None else action_count)

    def mark(stage: str, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
        """Call a file marker only on rank zero after a collective resource Gate."""

        local_exception = None
        local_resource: Mapping[str, Any] | None = None
        try:
            returned = resource_callback()
            if not isinstance(returned, Mapping):
                raise TypeError("resource_callback must return a mapping")
            local_resource = returned
        except Exception as exc:
            local_exception = exc
        resource_packets = comm.allgather(
            {
                "rank": int(comm.rank),
                "error": _error_packet(comm, local_exception),
                "rss": (
                    math.nan
                    if local_resource is None
                    else _resource_number(
                        local_resource,
                        ("rss_bytes", "peak_rss_bytes", "process_tree_rss_bytes"),
                        gib_keys=("rss_gib", "peak_rss_gib"),
                    )
                ),
                "swap": (
                    math.nan
                    if local_resource is None
                    else _resource_number(
                        local_resource,
                        ("swap_bytes", "peak_swap_bytes", "process_tree_swap_bytes"),
                        gib_keys=("swap_gib", "peak_swap_gib"),
                    )
                ),
            }
        )
        first_resource_error = next(
            (
                packet["error"]
                for packet in resource_packets
                if packet["error"] is not None
            ),
            None,
        )
        if first_resource_error is not None:
            error = RuntimeError(
                "S3b J1 formal resource callback failed on rank "
                f"{int(first_resource_error['rank'])} "
                f"{first_resource_error['type']}: "
                f"{first_resource_error['message']}"
            )
            if local_exception is not None:
                raise error from local_exception
            raise error

        local_rss = float(resource_packets[comm.rank]["rss"])
        local_swap = float(resource_packets[comm.rank]["swap"])
        rss_valid = bool(math.isfinite(local_rss) and local_rss >= 0.0)
        swap_valid = bool(math.isfinite(local_swap) and local_swap >= 0.0)
        rss_max = float(
            comm.allreduce(local_rss if rss_valid else -math.inf, op=MPI.MAX)
        )
        swap_max = float(
            comm.allreduce(local_swap if swap_valid else -math.inf, op=MPI.MAX)
        )
        elapsed_wall = float(
            comm.allreduce(perf_counter() - formal_started, op=MPI.MAX)
        )
        pc_count, action_count = current_apply_counts()
        pc_max = int(comm.allreduce(pc_count, op=MPI.MAX))
        action_max = int(comm.allreduce(action_count, op=MPI.MAX))
        marker_payload = dict(payload or {})
        marker_payload.update(
            {
                "elapsed_wall_seconds": elapsed_wall,
                "wall_seconds": elapsed_wall,
                "rss_bytes": int(rss_max) if math.isfinite(rss_max) else None,
                "swap_bytes": int(swap_max) if math.isfinite(swap_max) else None,
                "pc_apply_count": pc_max,
                "action_apply_count": action_max,
                "apply_count": max(pc_max, action_max),
            }
        )
        marker_state["last_resource"] = {
            "elapsed_wall_seconds": elapsed_wall,
            "rss_bytes": marker_payload["rss_bytes"],
            "swap_bytes": marker_payload["swap_bytes"],
            "pc_apply_count": pc_max,
            "action_apply_count": action_max,
        }
        resource_failure: list[str] = []
        if not rss_valid or not math.isfinite(rss_max):
            resource_failure.append("rss_unavailable")
        elif rss_max >= S3B_RSS_HARD_BYTES:
            resource_failure.append("rss_hard_limit")
        if not swap_valid or not math.isfinite(swap_max):
            resource_failure.append("swap_unavailable")
        elif swap_max != S3B_SWAP_LIMIT_BYTES:
            resource_failure.append("swap_nonzero")
        if not math.isfinite(elapsed_wall) or elapsed_wall >= S3B_WALL_CAP_SECONDS:
            resource_failure.append("wall_cap")
        failures = comm.allgather(tuple(resource_failure))
        all_failures = sorted({item for group in failures for item in group})
        if all_failures:
            marker_state["resource_stop"] = True
            stop_payload = {
                **marker_payload,
                "attempted_stage": stage,
                "resource_gate": "failed",
                "resource_failure": all_failures,
                "rss_hard_bytes": int(S3B_RSS_HARD_BYTES),
                "swap_limit_bytes": int(S3B_SWAP_LIMIT_BYTES),
                "wall_cap_seconds": int(S3B_WALL_CAP_SECONDS),
            }
            callback_exception = None
            if comm.rank == 0:
                try:
                    marker_callback("s3b_j1_resource_stop", _jsonable(stop_payload))
                except Exception as exc:
                    callback_exception = exc
            callback_packets = comm.allgather(
                _error_packet(comm, callback_exception)
            )
            first_callback_error = next(
                (packet for packet in callback_packets if packet is not None),
                None,
            )
            if first_callback_error is not None:
                raise RuntimeError(
                    "S3b J1 formal resource-stop marker failed on rank "
                    f"{int(first_callback_error['rank'])} "
                    f"{first_callback_error['type']}: "
                    f"{first_callback_error['message']}"
                )
            raise RuntimeError(
                "S3b J1 formal resource Gate stopped at "
                f"{stage}: {', '.join(all_failures)}"
            )

        callback_exception = None
        if comm.rank == 0:
            try:
                marker_callback(stage, _jsonable(marker_payload))
            except Exception as exc:
                callback_exception = exc
        callback_packets = comm.allgather(_error_packet(comm, callback_exception))
        first_callback_error = next(
            (packet for packet in callback_packets if packet is not None),
            None,
        )
        if first_callback_error is not None:
            error = RuntimeError(
                f"S3b J1 formal marker {stage} failed on rank "
                f"{int(first_callback_error['rank'])} "
                f"{first_callback_error['type']}: "
                f"{first_callback_error['message']}"
            )
            if callback_exception is not None:
                raise error from callback_exception
            raise error
        marker_state["markers"].append(stage)
        return marker_payload

    try:
        mark(
            "s3b_j1_system_begin",
            {
                "route": "V9_E_S3B",
                "side": "bottom",
                "mpi_size": int(comm.size),
                "active_rows_expected": int(S3B_EXPECTED_ACTIVE_ROWS),
                "source_label": S3B_EXTERNAL_SOURCE_LABEL,
                "source_seed": int(S3B_EXTERNAL_SOURCE_SEED),
                "source_column": int(S3B_EXTERNAL_SOURCE_COLUMN),
                "source_sign": float(S3B_EXTERNAL_SOURCE_SIGN),
            },
        )
        system = assemble_hybrid_local_dtn_action_system(
            cfg,
            "bottom",
            bottom_interface_z_nm=profile.bottom_interface_nm,
            top_interface_z_nm=profile.top_interface_nm,
            comm=comm,
            log=None,
        )
        operator = getattr(system, "fine_action", None)
        if not isinstance(operator, PETSc.Mat):
            raise TypeError("S3b J1 formal requires system.fine_action as PETSc Mat")
        if _operator_shape(operator) != (
            S3B_EXPECTED_ACTIVE_ROWS,
            S3B_EXPECTED_ACTIVE_ROWS,
        ):
            raise ValueError(
                "S3b J1 formal fine_action shape differs from fixed active rows: "
                f"{_operator_shape(operator)}"
            )
        mark(
            "s3b_j1_system_ready",
            {
                "operator_identity": "system.fine_action",
                "operator_shape": list(_operator_shape(operator)),
                "operator_borrowed_by_solver": True,
                "full_A_used": False,
                "qep_calls": 0,
            },
        )

        source, source_audit = build_s3_external_dtn_source(system)
        if int(source.getSize()) != S3B_EXPECTED_ACTIVE_ROWS:
            raise ValueError("S3b J1 source size differs from fixed active rows")
        if (
            source_audit.get("label") != S3B_EXTERNAL_SOURCE_LABEL
            or source_audit.get("seed") != S3B_EXTERNAL_SOURCE_SEED
            or source_audit.get("column") != S3B_EXTERNAL_SOURCE_COLUMN
            or source_audit.get("sign") != S3B_EXTERNAL_SOURCE_SIGN
        ):
            raise RuntimeError("S3b J1 source audit differs from frozen source identity")
        mark(
            "s3b_j1_source_ready",
            {
                "source_identity": _jsonable(source_audit),
                "source_norm": source_audit.get("source_norm"),
                "source_canonical_key_count": source_audit.get("canonical_key_count"),
                "source_canonical_key_set_sha256": source_audit.get(
                    "canonical_key_set_sha256"
                ),
                "source_canonical_value_sha256": source_audit.get(
                    "canonical_value_sha256"
                ),
                "numeric_allgather": False,
                "full_vector_replication": False,
            },
        )

        j1_action, j1_audit = build_s3_j1_baseline_action(
            system,
            progress_callback=mark,
        )
        mark(
            "s3b_j1_one_apply_begin",
            {
                "operator_identity": "system.fine_action",
                "action_identity": "J1_layer_sweep",
                "operator_matvec_count_expected": 1,
            },
        )
        one_apply = audit_s3_preconditioner_one_apply(
            operator,
            source,
            j1_action,
            S3B_EXTERNAL_SOURCE_LABEL,
        )
        if one_apply.get("operator_matvec_count") != 1:
            raise RuntimeError("S3b J1 one-apply audit did not perform exactly one matvec")
        if one_apply.get("action_apply_count_exactly_one") is False:
            raise RuntimeError("S3b J1 one-apply action count was not exactly one")
        mark("s3b_j1_one_apply_end", {"one_apply": _jsonable(one_apply)})

        solver = S3FixedRightFgmres(operator, j1_action)
        mark(
            "s3b_j1_fgmres_setup",
            {
                "solver": _jsonable(solver.diagnostics),
                "setup_count": int(solver.diagnostics["setup_count"]),
                "restart": int(S3B_FGMRES_RESTART),
                "max_it": int(S3B_FGMRES_INITIAL_MAX_IT),
            },
        )

        def checkpoint_callback(row: Mapping[str, Any]) -> None:
            iteration = int(row["iteration"])
            stage = "s3b_j1_r0" if iteration == 0 else f"s3b_j1_r{iteration}"
            mark(
                stage,
                {
                    "checkpoint": _jsonable(row),
                    "checkpoint_kind": row.get("checkpoint_kind"),
                },
            )

        fgmres = solver.solve_initial(
            source,
            S3B_EXTERNAL_SOURCE_LABEL,
            checkpoint_callback=checkpoint_callback,
        )
        mark("s3b_j1_solve_end", {"fgmres": _jsonable(fgmres)})
    except Exception as exc:
        formal_exception = exc

    solver_before_destroy = _jsonable(solver.diagnostics) if solver is not None else None
    action_before_destroy = (
        _jsonable(j1_action.diagnostics) if j1_action is not None else None
    )
    for name, obj in (
        ("solver", solver),
        ("source", source),
        ("j1_action", j1_action),
        ("system", system),
    ):
        if obj is None:
            continue
        try:
            obj.destroy()
        except Exception as exc:
            cleanup_errors.append(
                {
                    "object": name,
                    "rank": int(comm.rank),
                    "type": type(exc).__name__,
                    "message": str(exc),
                }
            )
    solver_after_destroy = _jsonable(solver.diagnostics) if solver is not None else None
    action_after_destroy = (
        _jsonable(j1_action.diagnostics) if j1_action is not None else None
    )
    cleanup_error_packets = comm.allgather(cleanup_errors)
    cleanup_errors = [
        item
        for packet_group in cleanup_error_packets
        for item in packet_group
    ]
    system_cleanup_error = any(
        isinstance(item, Mapping) and item.get("object") == "system"
        for item in cleanup_errors
    )
    operator_borrowed_by_solver = bool(operator is not None and solver is not None)
    operator_destroyed_with_owning_system = bool(
        system is not None and not system_cleanup_error
    )
    ready_layer_row_stats = _layer_factor_row_stats(action_before_destroy, comm)
    ready_layer_factor_count = int(ready_layer_row_stats["factor_count"])
    layer_factor_cleanup_error = any(
        isinstance(item, Mapping) and item.get("object") == "j1_action"
        for item in cleanup_errors
    )
    solver_cleanup_error = any(
        isinstance(item, Mapping) and item.get("object") == "solver"
        for item in cleanup_errors
    )
    source_cleanup_error = any(
        isinstance(item, Mapping) and item.get("object") == "source"
        for item in cleanup_errors
    )
    solver_vectors_ready = 3 if solver_before_destroy is not None else 0
    solver_vectors_after_cleanup = (
        0 if solver_before_destroy is not None and not solver_cleanup_error else None
    )
    layer_factors_after_cleanup = (
        0 if action_before_destroy is not None and not layer_factor_cleanup_error else None
    )
    source_destroyed = bool(source is not None and not source_cleanup_error)
    if not marker_state["resource_stop"]:
        try:
            mark(
                "s3b_j1_cleanup_complete",
                {
                    "cleanup_errors": _jsonable(cleanup_errors),
                    "solver_before_destroy": solver_before_destroy,
                    "solver_after_destroy": solver_after_destroy,
                    "action_before_destroy": action_before_destroy,
                    "action_after_destroy": action_after_destroy,
                    "operator_borrowed_by_solver": operator_borrowed_by_solver,
                    "operator_destroyed_with_owning_system": (
                        operator_destroyed_with_owning_system
                    ),
                    "j1_layer_factor_count_ready": ready_layer_factor_count,
                    "j1_layer_factor_count_after_cleanup": layer_factors_after_cleanup,
                    "solver_vectors_owned_ready": solver_vectors_ready,
                    "solver_vectors_owned_after_cleanup": solver_vectors_after_cleanup,
                },
            )
        except Exception as exc:
            cleanup_marker_error = exc

    formal_error_packets = comm.allgather(
        _error_packet(comm, cleanup_marker_error or formal_exception)
    )
    formal_exception_identity = next(
        (packet for packet in formal_error_packets if packet is not None),
        None,
    )
    if formal_exception_identity is None and cleanup_errors:
        first_cleanup_error = cleanup_errors[0]
        formal_exception_identity = {
            "rank": int(first_cleanup_error.get("rank", 0)),
            "type": str(first_cleanup_error.get("type", "RuntimeError")),
            "message": str(first_cleanup_error.get("message", "cleanup failed")),
        }
    if formal_exception_identity is not None:
        formal_exception = RuntimeError(
            "S3b J1 formal failed on rank "
            f"{int(formal_exception_identity['rank'])} "
            f"{formal_exception_identity['type']}: "
            f"{formal_exception_identity['message']}"
        )

    if marker_state["resource_stop"]:
        if formal_exception is not None:
            raise formal_exception
        raise RuntimeError("S3b J1 formal stopped by resource Gate")

    checkpoints = fgmres.get("checkpoints", {}) if isinstance(fgmres, Mapping) else {}
    complete_finite = bool(
        isinstance(fgmres, Mapping)
        and fgmres.get("checkpoint_complete") is True
        and fgmres.get("finite") is True
        and isinstance(checkpoints, Mapping)
        and all(str(index) in checkpoints for index in (8, 16, 32, 64))
    )
    if formal_exception is not None:
        classification = "S3B_J1_BASELINE_IMPLEMENTATION_FAILURE"
    elif complete_finite:
        classification = "S3B_J1_BASELINE_MEASURED"
    else:
        classification = "S3B_J1_BASELINE_UNSTABLE"
    r64 = (
        checkpoints.get("64", {}).get("true_residual_relative")
        if isinstance(checkpoints, Mapping)
        else None
    )
    return _jsonable(
        {
            "schema": "task040.v9_e.s3b_j1_baseline_formal.v1",
            "method": "task040_v9_e_s3b_j1_baseline_formal",
            "route": "V9_E_S3B",
            "classification": classification,
            "positive": False,
            "baseline_only": True,
            "threshold_classification_applied": False,
            "provenance": {
                "source_sha": str(source_sha),
                "input_path": str(input_path),
                "input_sha256": str(input_sha256),
                "physical_model_sha256": str(physical_model_sha256),
                "mpi_size": int(comm.size),
                "threads": 1,
                "side": "bottom",
                "operator_identity": "system.fine_action",
                "full_A_used": False,
                "qep_calls": 0,
            },
            "fixed_contract": {
                "active_rows": int(S3B_EXPECTED_ACTIVE_ROWS),
                "source_label": S3B_EXTERNAL_SOURCE_LABEL,
                "source_seed": int(S3B_EXTERNAL_SOURCE_SEED),
                "source_column": int(S3B_EXTERNAL_SOURCE_COLUMN),
                "source_sign": float(S3B_EXTERNAL_SOURCE_SIGN),
                "fgmres_restart": int(S3B_FGMRES_RESTART),
                "fgmres_initial_max_it": int(S3B_FGMRES_INITIAL_MAX_IT),
                "rss_hard_bytes": int(S3B_RSS_HARD_BYTES),
                "swap_limit_bytes": int(S3B_SWAP_LIMIT_BYTES),
                "wall_cap_seconds": int(S3B_WALL_CAP_SECONDS),
            },
            "source": source_audit,
            "source_norm": source_audit.get("source_norm"),
            "source_canonical_key_set_sha256": source_audit.get(
                "canonical_key_set_sha256"
            ),
            "source_canonical_value_sha256": source_audit.get(
                "canonical_value_sha256"
            ),
            "one_apply": one_apply,
            "fgmres": fgmres,
            "j1": {
                "audit": j1_audit,
                "r64": r64,
                "ready_diagnostics": j1_audit.get("ready_diagnostics"),
            },
            "factor_lifecycle": {
                "j1_layer_factor_count": ready_layer_factor_count,
                "j1_layer_factor_count_ready": ready_layer_factor_count,
                "j1_layer_factor_count_after_cleanup": layer_factors_after_cleanup,
                "full_cross_section_factor_count_ready": ready_layer_factor_count,
                "full_cross_section_factor_count_after_cleanup": (
                    layer_factors_after_cleanup
                ),
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "global_coarse_factor_count": 0,
                "ready_layer_row_stats": ready_layer_row_stats,
                "ready_diagnostics": action_before_destroy,
                "after_cleanup_diagnostics": action_after_destroy,
            },
            "vector_lifecycle": {
                "solver_vectors_owned": solver_vectors_ready,
                "solver_vectors_owned_ready": solver_vectors_ready,
                "solver_vectors_owned_after_cleanup": solver_vectors_after_cleanup,
                "solver_diagnostics_before_destroy": solver_before_destroy,
                "solver_diagnostics_after_destroy": solver_after_destroy,
                "source_destroyed": source_destroyed,
                "operator_borrowed_by_solver": operator_borrowed_by_solver,
                "operator_destroyed_with_owning_system": (
                    operator_destroyed_with_owning_system
                ),
            },
            "structure": {
                "j1_layer_factor_count": ready_layer_factor_count,
                "j1_layer_factor_count_ready": ready_layer_factor_count,
                "j1_layer_factor_count_after_cleanup": layer_factors_after_cleanup,
                "full_cross_section_factor_count_ready": ready_layer_factor_count,
                "full_cross_section_factor_count_after_cleanup": (
                    layer_factors_after_cleanup
                ),
                "layer_factor_row_stats": ready_layer_row_stats,
                "candidate_max_local_rows_gate": "not_applicable_to_j1_baseline",
                "candidate_max_local_rows_gate_status": "not_applicable",
                "candidate_max_local_rows_gate_limit": 1024,
                "candidate_max_local_rows_gate_passed": False,
                "full_side_exact_factor_count": 0,
                "global_direct_factor_count": 0,
                "global_coarse_factor_count": 0,
                "fe_numeric_allgather": False,
                "numeric_allgather": False,
                "full_basis_per_rank_replication": False,
                "layer_label_build": {
                    "label_dtype": "int32",
                    "collective": (
                        "FE-sized integer layer-label minimum reduction and replication"
                    ),
                    "mapping_source": (
                        j1_audit.get("mapping_metadata", {}).get("mapping_source")
                        if isinstance(j1_audit.get("mapping_metadata"), Mapping)
                        else None
                    ),
                    "fe_sized_int_label_reduction_replication": True,
                    "numeric_allgather": False,
                },
            },
            "resources": marker_state["last_resource"],
            "markers": list(marker_state["markers"]),
            "cleanup_errors": cleanup_errors,
            "formal_exception_identity": formal_exception_identity,
            "error": (
                formal_exception_identity
            ),
        }
    )
