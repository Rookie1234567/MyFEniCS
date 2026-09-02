"""Task040 h10 physical bare-F external-source fixed-LOR pilot."""

from __future__ import annotations

import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hcurl_fixed_lor_cell_bridge import (
    build_fixed_p6_lor_cell_bridge,
)
from src.solvers.hcurl_fixed_lor_positive_screen import (
    _create_counted_action,
    _explicit_true_residual,
    _json_value,
    _marker,
    _run_fixed_right_fgmres,
    _sha256,
)
from src.solvers.hcurl_fixed_lor_trace_service import (
    build_fixed_lor_trace_service,
)
from src.solvers.hybrid_bare_f_authority import (
    assemble_current_bare_f_authority_system,
    build_current_bare_f_rhs,
    canonical_layout_tokens,
    canonical_packets_for_vector,
    canonical_to_current_roundtrip_relative,
    vector_identity,
)
from src.solvers.hybrid_source_canonical_bridge import (
    _global_key_digest,
    _global_pair_digest,
)

V9_E_LOR_BARE_F_EXTERNAL_ONLY_FLAG = "--v9-e-lor-bare-f-external-only"
V9_E_LOR_BARE_F_EXTERNAL_ONLY_METHOD = "task040_v9_e_lor_bare_f_external_only"
V9_E_LOR_BARE_F_EXTERNAL_ONLY_SCHEMA = "task040.v9_e.lor_bare_f_external_only.v1"
V9_E_LOR_BARE_F_EXTERNAL_ONLY_PROFILE_ID = (
    "task040.v9_e.lor.bare_f_external_only.v1"
)
V9_E_LOR_BARE_F_EXTERNAL_ONLY_HARD_STOP_BYTES = 45 * 2**30
V9_E_LOR_BARE_F_EXTERNAL_ONLY_TIMEOUT_SECONDS = 21600
V9_E_LOR_BARE_F_EXTERNAL_ONLY_MPI_SIZE = 8
V9_E_LOR_BARE_F_EXTERNAL_ONLY_INPUT = (
    "input/official/task039/5nm_p6h10_full3d_direct_mpi8.dat"
)
V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE = (
    "v9_e_lor_bare_f_external_preflight",
    "v9_e_lor_bare_f_external_system_ready",
    "v9_e_lor_bare_f_external_action_ready",
    "v9_e_lor_bare_f_external_source_canonical_ready",
    "v9_e_lor_bare_f_external_bridge_begin",
    "v9_e_lor_bare_f_external_bridge_ready",
    "v9_e_lor_bare_f_external_service_ready",
    "v9_e_lor_bare_f_external_rhs_ready",
    "v9_e_lor_bare_f_external_solve_begin",
    "v9_e_lor_bare_f_external_checkpoint",
    "v9_e_lor_bare_f_external_solve_end",
    "v9_e_lor_bare_f_external_explicit_residual",
    "v9_e_lor_bare_f_external_classification",
    "v9_e_lor_bare_f_external_cleanup_complete",
)
V9_E_LOR_BARE_F_EXTERNAL_POSITIVE = "V9_E_LOR_BARE_F_EXTERNAL_POSITIVE"
V9_E_LOR_BARE_F_EXTERNAL_NUMERICAL_NO_SIGNAL = (
    "V9_E_LOR_BARE_F_EXTERNAL_NUMERICAL_NO_SIGNAL"
)
V9_E_LOR_BARE_F_EXTERNAL_RESOURCE_UNAVAILABLE = (
    "V9_E_LOR_BARE_F_EXTERNAL_RESOURCE_UNAVAILABLE"
)
V9_E_LOR_BARE_F_EXTERNAL_IMPLEMENTATION_FAILURE = (
    "V9_E_LOR_BARE_F_EXTERNAL_IMPLEMENTATION_FAILURE"
)

__all__ = [
    "V9_E_LOR_BARE_F_EXTERNAL_IMPLEMENTATION_FAILURE",
    "V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE",
    "V9_E_LOR_BARE_F_EXTERNAL_NUMERICAL_NO_SIGNAL",
    "V9_E_LOR_BARE_F_EXTERNAL_ONLY_FLAG",
    "V9_E_LOR_BARE_F_EXTERNAL_ONLY_HARD_STOP_BYTES",
    "V9_E_LOR_BARE_F_EXTERNAL_ONLY_INPUT",
    "V9_E_LOR_BARE_F_EXTERNAL_ONLY_METHOD",
    "V9_E_LOR_BARE_F_EXTERNAL_ONLY_MPI_SIZE",
    "V9_E_LOR_BARE_F_EXTERNAL_ONLY_PROFILE_ID",
    "V9_E_LOR_BARE_F_EXTERNAL_ONLY_SCHEMA",
    "V9_E_LOR_BARE_F_EXTERNAL_ONLY_TIMEOUT_SECONDS",
    "V9_E_LOR_BARE_F_EXTERNAL_POSITIVE",
    "V9_E_LOR_BARE_F_EXTERNAL_RESOURCE_UNAVAILABLE",
    "run_v9_e_lor_bare_f_external_only",
]


def _validate_input(input_path: str | Path, input_sha256: str) -> Path:
    repo = Path(__file__).resolve().parents[2]
    resolved = Path(input_path).resolve()
    expected = (repo / V9_E_LOR_BARE_F_EXTERNAL_ONLY_INPUT).resolve()
    if resolved != expected:
        raise ValueError("the bare-F external pilot requires the official h10 input")
    if _sha256(resolved) != str(input_sha256):
        raise ValueError("the supplied input_sha256 does not match the input")
    return resolved


def _build_bridges(condensed: Any) -> dict[tuple[Any, ...], Any]:
    retained = condensed.retained_local_schur_by_class
    comm = condensed.comm
    none_count = comm.allreduce(int(retained is None), op=MPI.SUM)
    global_class_count = comm.allreduce(
        int(retained is not None and bool(retained)), op=MPI.SUM
    )
    if none_count:
        raise RuntimeError("retained Schur classes are unavailable on a rank")
    if global_class_count == 0:
        raise RuntimeError("the physical system has no retained Schur classes")
    bridges: dict[tuple[Any, ...], Any] = {}
    try:
        for class_key in retained:
            if len(class_key) != 5:
                raise RuntimeError(
                    "retained class key is not (tag,wx,wy,wz,cell_info)"
                )
            _tag, wx, wy, wz, cell_info = class_key
            bridge = build_fixed_p6_lor_cell_bridge(
                (float(wx), float(wy), float(wz)),
                curl_coefficient=1.0 + 0.0j,
                mass_coefficient=1.0 + 0.0j,
                cell_info=int(cell_info),
            )
            if not bridge.audit.get("pass", False):
                bridge.destroy()
                raise RuntimeError("a fixed positive bridge failed its audit")
            bridges[class_key] = bridge
    except Exception:
        for bridge in bridges.values():
            bridge.destroy()
        raise
    return bridges


def _bridge_bytes(bridges: Mapping[Any, Any]) -> tuple[int, int]:
    retained = transient = 0
    for bridge in bridges.values():
        lifecycle = bridge.audit["lifecycle"]
        retained += int(lifecycle["retained_trace_bridge_bytes"])
        transient += int(lifecycle["selected_transient_array_bytes_not_peak"])
    return retained, transient


def _service_bytes(audit: Mapping[str, Any]) -> tuple[int, int, int]:
    factor = int(audit["retained_numpy_factor_map_bytes_not_peak"])
    work = int(audit["retained_work_vector_payload_bytes_not_peak"])
    return factor, work, factor + work


def run_v9_e_lor_bare_f_external_only(
    *,
    cfg: Any,
    profile: Any,
    comm: MPI.Intracomm,
    input_path: str | Path,
    run_directory: str | Path,
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    external_mode_authority: Mapping[str, Any],
    external_mode_current_resolved_config_sha256: str,
    marker_callback: Callable[[str, Mapping[str, Any]], None] | None,
    resource_callback: Callable[[], Mapping[str, Any]],
    watchdog_enabled: bool,
    bottom_route_only: bool,
    watchdog_hard_stop_bytes: int,
) -> dict[str, Any]:
    import time

    started = time.monotonic()
    input_file = _validate_input(input_path, input_sha256)
    if comm.size != V9_E_LOR_BARE_F_EXTERNAL_ONLY_MPI_SIZE:
        raise ValueError("the bare-F external pilot requires MPI8")
    if not watchdog_enabled or not bottom_route_only:
        raise ValueError("the bare-F external pilot requires watchdog bottom mode")
    if int(watchdog_hard_stop_bytes) != V9_E_LOR_BARE_F_EXTERNAL_ONLY_HARD_STOP_BYTES:
        raise ValueError("the bare-F external pilot requires the 45 GiB hard stop")
    run_path = Path(run_directory)
    run_path.mkdir(parents=True, exist_ok=True)
    lifecycle: dict[str, Any] = {
        "ksp_destroyed": False,
        "pc_context_destroyed_after_ksp_destroy": False,
        "system_destroyed": False,
        "service_destroyed": False,
        "bridges_destroyed": False,
        "counted_action_destroyed": False,
        "static_action_destroyed": False,
        "condensed_destroyed": False,
        "mpc_destroyed": "not_applicable",
        "mpc_destroy_hook": "unavailable",
        "mpc_release_semantics": "scope_release_no_destroy_hook",
        "destroyable_objects_cleanup_complete": False,
        "cleanup_complete": False,
    }
    result: dict[str, Any] = {
        "schema": V9_E_LOR_BARE_F_EXTERNAL_ONLY_SCHEMA,
        "method": V9_E_LOR_BARE_F_EXTERNAL_ONLY_METHOD,
        "profile_id": V9_E_LOR_BARE_F_EXTERNAL_ONLY_PROFILE_ID,
        "route": "V9_E_LOR_BARE_F_EXTERNAL",
        "input": str(input_file),
        "input_sha256": str(input_sha256),
        "physical_model_sha256": str(physical_model_sha256),
        "source_sha": str(source_sha),
        "scalar_type": str(np.dtype(PETSc.ScalarType)),
        "int_type": str(PETSc.IntType),
        "additional_absorbing_shift": 0.0,
        "operator_binding": "preconditioner_only",
        "operator": "P_plus_curlcurl_plus_mass",
        "curl_coefficient": [1.0, 0.0],
        "mass_coefficient": [1.0, 0.0],
        "role": "right_preconditioner_not_physical_operator",
        "scan": False,
        "official_rta": {"status": "not_run"},
        "external_mode_authority_binding": {
            "authority_bound": True,
            "authority_file_path": str(
                external_mode_authority["authority_file_path"]
            ),
            "authority_file_sha256": str(
                external_mode_authority["authority_file_sha256"]
            ),
            "inventory_canonical_sha256": str(
                external_mode_authority["inventory_canonical_sha256"]
            ),
            "source_path": str(external_mode_authority["source_path"]),
            "full_count": int(external_mode_authority["full_count"]),
            "bottom_count": int(external_mode_authority["bottom_count"]),
            "canonical_key_list_sha256": str(
                external_mode_authority["canonical_key_list_sha256"]
            ),
            "resolved_mode_metadata_sha256": str(
                external_mode_authority["resolved_mode_metadata_sha256"]
            ),
            "legacy_beta_metadata_sha256": str(
                external_mode_authority["legacy_beta_metadata_sha256"]
            ),
            "legacy_beta_metadata_schema": str(
                external_mode_authority["legacy_beta_metadata_schema"]
            ),
            "input_sha256": str(input_sha256),
            "physical_model_sha256": str(physical_model_sha256),
            "resolved_config_sha256": str(
                external_mode_current_resolved_config_sha256
            ),
        },
        "lifecycle": lifecycle,
    }
    system = None
    bridges: dict[tuple[Any, ...], Any] = {}
    service = None
    counted_action = counted_context = None
    rhs = solution = None
    try:
        _marker(
            V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE[0],
            marker_callback,
            comm,
            started,
            resource_callback,
            method=V9_E_LOR_BARE_F_EXTERNAL_ONLY_METHOD,
        )
        system = assemble_current_bare_f_authority_system(
            cfg,
            side="bottom",
            bottom_interface_z_nm=profile.bottom_interface_nm,
            top_interface_z_nm=profile.top_interface_nm,
            source_work_directory=run_path / "source_work",
            comm=comm,
            action_only=True,
            external_mode_authority=external_mode_authority,
            external_mode_current_resolved_config_sha256=(
                external_mode_current_resolved_config_sha256
            ),
        )
        inventory = system.construction_inventory
        build_audit = system.condensed.build_audit
        if system.F.getType().lower() != "python":
            raise RuntimeError("bare-F pilot did not build a Python action")
        if not inventory["action_only"] or inventory["global_F_materialized"]:
            raise RuntimeError("bare-F pilot did not remain action-only")
        if system.condensed.matrix is not None:
            raise RuntimeError("action-only pilot unexpectedly materialized F")
        for key in ("matrix_materialized", "global_active_F_allocated"):
            if build_audit[key] is not False:
                raise RuntimeError(f"action-only audit failed for {key}")
        if system.dtn_objects_constructed != {"C": 0, "D": 0, "H": 0}:
            raise RuntimeError("bare-F pilot constructed a DtN block")
        for key in (
            "qep_calls",
            "global_factor_count",
            "global_direct_factor_count",
            "global_coarse_factor_count",
        ):
            if key in inventory and int(inventory[key]) != 0:
                raise RuntimeError(f"forbidden construction inventory entry: {key}")
        if inventory.get("physical_dtn_operator_constructed", False):
            raise RuntimeError("bare-F pilot constructed a physical DtN operator")
        result.update(
            {
                "construction_inventory": _json_value(inventory),
                "active_rows": int(system.active_rows),
                "appended_rows": int(system.condensed.appended_rows),
                "dtn_objects_constructed": dict(system.dtn_objects_constructed),
                "global_high_order_aij": False,
                "global_factor_count": 0,
                "global_coarse_factor_count": 0,
                "physical_dtn_used": False,
            }
        )
        _marker(
            V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE[1],
            marker_callback,
            comm,
            started,
            resource_callback,
            active_rows=int(system.active_rows),
            appended_rows=int(system.condensed.appended_rows),
            physical_dtn_used=False,
        )
        _marker(
            V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE[2],
            marker_callback,
            comm,
            started,
            resource_callback,
            operator_identity=inventory["operator_identity"],
            global_F_materialized=False,
        )
        tokens, layout_hash, layout_audit = canonical_layout_tokens(system)
        rhs, source_metadata = build_current_bare_f_rhs(
            system, "external_dtn_coupling"
        )
        source_tokens, source_values, source_audit = canonical_packets_for_vector(
            system, rhs
        )
        if source_tokens != tokens:
            raise RuntimeError("external source and active layout keys differ")
        if source_metadata.get("source") != (
            "current_external_minimal_surface_components"
        ):
            raise RuntimeError("unexpected external source builder")
        if source_metadata.get("full_C_materialized") is not False:
            raise RuntimeError("external source materialized full C")
        if (
            "raw_global_row_remap" not in source_metadata
            or source_metadata["raw_global_row_remap"] is not False
        ):
            raise RuntimeError("external source raw-row remap evidence is invalid")
        matrix_objects = source_metadata.get("matrix_objects")
        if not isinstance(matrix_objects, Mapping) or any(
            int(matrix_objects.get(name, -1)) != 0 for name in ("C", "D", "H")
        ):
            raise RuntimeError("external source constructed forbidden matrix objects")
        roundtrip = canonical_to_current_roundtrip_relative(
            system, source_tokens, source_values, rhs
        )
        if not np.isfinite(roundtrip) or roundtrip > 1.0e-12:
            raise RuntimeError("external source canonical round-trip failed")
        canonical_pairs = list(
            zip(source_tokens, source_values.tolist(), strict=True)
        )
        canonical_key_digest = _global_key_digest(comm, source_tokens)
        canonical_pair_digest = _global_pair_digest(
            comm, canonical_pairs, label="external_dtn_coupling"
        )
        if canonical_key_digest != layout_hash:
            raise RuntimeError("canonical key digest differs from active layout hash")
        source_identity = vector_identity(
            system,
            source_tokens,
            source_values,
            layout_hash,
            owner_values=np.array(
                rhs.getArray(readonly=True), dtype=np.complex128, copy=True
            ),
            canonical_roundtrip_relative=roundtrip,
        )
        source_norm = float(rhs.norm())
        if not np.isfinite(source_norm) or source_norm <= 0.0:
            raise RuntimeError("external source is zero or non-finite")
        if not np.isfinite(source_values).all():
            raise RuntimeError("external source packets are non-finite")
        result["source"] = {
            "label": "external_dtn_coupling",
            "metadata": _json_value(source_metadata),
            "layout_hash": layout_hash,
            "layout_audit": _json_value(layout_audit),
            "packet_audit": _json_value(source_audit),
            "identity": _json_value(source_identity),
            "canonical_key_digest": canonical_key_digest,
            "canonical_value_pair_digest": canonical_pair_digest,
            "roundtrip_relative": float(roundtrip),
            "raw_global_row_remap": False,
            "raw_global_row_remap_evidence": (
                "current_external_minimal_surface_components plus canonical extraction"
            ),
            "norm": source_norm,
            "finite": True,
        }
        result["construction_inventory"] = _json_value(
            system.construction_inventory
        )
        _marker(
            V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE[3],
            marker_callback,
            comm,
            started,
            resource_callback,
            canonical_layout_sha256=layout_hash,
            source_roundtrip_relative=float(roundtrip),
            source_norm=source_norm,
        )
        _marker(
            V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE[4],
            marker_callback,
            comm,
            started,
            resource_callback,
            source="external_dtn_coupling",
        )
        bridges = _build_bridges(system.condensed)
        retained_bridge, transient_bridge = _bridge_bytes(bridges)
        bridge_count = len(bridges)
        result["bridges"] = {
            "class_inventory": [
                {
                    "tag": int(class_key[0]),
                    "widths": [float(value) for value in class_key[1:4]],
                    "cell_info": int(class_key[4]),
                }
                for class_key in bridges
            ],
            "class_count_local": bridge_count,
            "class_count_global": int(comm.allreduce(bridge_count, op=MPI.SUM)),
            "retained_bytes_local": retained_bridge,
            "transient_bytes_local_not_peak": transient_bridge,
            "retained_bytes_rank_sum": int(
                comm.allreduce(retained_bridge, op=MPI.SUM)
            ),
            "transient_bytes_rank_sum_not_peak": int(
                comm.allreduce(transient_bridge, op=MPI.SUM)
            ),
        }
        _marker(
            V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE[5],
            marker_callback,
            comm,
            started,
            resource_callback,
            bridge_count_global=result["bridges"]["class_count_global"],
            bridge_retained_bytes_rank_sum=result["bridges"][
                "retained_bytes_rank_sum"
            ],
        )
        service = build_fixed_lor_trace_service(
            system.condensed,
            bridges,
            operator_binding="preconditioner_only",
        )
        service_audit = service.audit
        if service_audit["operator_binding"] != "preconditioner_only":
            raise RuntimeError("service binding is not preconditioner_only")
        if service_audit["production_bridge_identity_required"]:
            raise RuntimeError("preconditioner-only service required identity")
        if service_audit["production_bridge_identity_applied"]:
            raise RuntimeError("preconditioner-only service applied identity Gate")
        if service_audit["production_bridge_identity_passed"] is not None:
            raise RuntimeError("preconditioner-only identity result was not null")
        if not service_audit["production_bridge_comparison_computed"]:
            raise RuntimeError("production/bridge comparison was not computed")
        max_factor_rows = int(
            comm.allreduce(int(service_audit["max_local_factor_rows"]), op=MPI.MAX)
        )
        if max_factor_rows > 432:
            raise RuntimeError("a fixed-LOR factor exceeds 432 rows")
        factor_local, work_local, pc_local = _service_bytes(service_audit)
        factor_rank_sum = int(comm.allreduce(factor_local, op=MPI.SUM))
        work_rank_sum = int(comm.allreduce(work_local, op=MPI.SUM))
        pc_rank_sum = factor_rank_sum + work_rank_sum
        result["service_audit"] = _json_value(service_audit)
        result["service_memory"] = {
            "factor_payload_local": factor_local,
            "work_payload_local": work_local,
            "pc_retained_bytes_local": pc_local,
            "factor_payload_rank_sum": factor_rank_sum,
            "work_payload_rank_sum": work_rank_sum,
            "pc_retained_bytes_rank_sum": pc_rank_sum,
            "max_local_factor_rows_global": max_factor_rows,
        }
        result["structure_factor_inventory"] = {
            "full_side_factor_count": 0,
            "full_cross_factor_count": 0,
            "global_direct_factor_count": 0,
            "global_coarse_factor_count": 0,
            "global_F": False,
            "global_AIJ": False,
            "max_local_rows": max_factor_rows,
            "numeric_allgather": False,
            "full_basis_replication": False,
            "physical_dtn_rebuilt": False,
        }
        _marker(
            V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE[6],
            marker_callback,
            comm,
            started,
            resource_callback,
            operator_binding="preconditioner_only",
            operator="P_plus_curlcurl_plus_mass",
            curl_coefficient=[1.0, 0.0],
            mass_coefficient=[1.0, 0.0],
            additional_absorbing_shift=0.0,
            role="right_preconditioner_not_physical_operator",
            scan=False,
            pc_retained_bytes_rank_sum=pc_rank_sum,
            max_local_factor_rows=max_factor_rows,
        )
        for bridge in bridges.values():
            bridge.destroy()
        lifecycle["bridges_destroyed"] = all(
            bool(bridge.destroyed) for bridge in bridges.values()
        )
        bridges.clear()
        counted_action, counted_context = _create_counted_action(system.F)
        _marker(
            V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE[7],
            marker_callback,
            comm,
            started,
            resource_callback,
            source_norm=source_norm,
        )

        def checkpoint(iteration: int, residual: float) -> None:
            _marker(
                V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE[9],
                marker_callback,
                comm,
                started,
                resource_callback,
                iteration=int(iteration),
                reported_recurrence_residual=float(residual),
                explicit_true_residual=False,
                counted_action=counted_context,
                service=service,
            )

        _marker(
            V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE[8],
            marker_callback,
            comm,
            started,
            resource_callback,
            counted_action=counted_context,
            service=service,
        )
        solution, ksp_diagnostics = _run_fixed_right_fgmres(
            counted_action,
            rhs,
            service,
            checkpoint_callback=checkpoint,
        )
        result["ksp"] = _json_value(ksp_diagnostics)
        lifecycle["ksp_destroyed"] = bool(ksp_diagnostics["ksp_destroyed"])
        lifecycle["pc_context_destroyed_after_ksp_destroy"] = bool(
            ksp_diagnostics["pc_context_destroyed_after_ksp_destroy"]
        )
        _marker(
            V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE[10],
            marker_callback,
            comm,
            started,
            resource_callback,
            reason=int(ksp_diagnostics["reason"]),
            iterations=int(ksp_diagnostics["iterations"]),
            counted_action=counted_context,
            service=service,
        )
        residual = _explicit_true_residual(counted_action, solution, rhs)
        finite = bool(np.isfinite(residual))
        reason = int(ksp_diagnostics["reason"])
        iterations = int(ksp_diagnostics["iterations"])
        passed = bool(finite and iterations <= 256 and residual <= 1.0e-3)
        result.update(
            {
                "explicit_true_residual": float(residual),
                "explicit_true_residual_finite": finite,
                "external_residual_gate": passed,
                "general_residual_gate": bool(
                    finite and iterations <= 256 and residual <= 1.0e-2
                ),
                "iterations_within_fixed_limit": bool(iterations <= 256),
                "final_action_apply_count": int(counted_context.apply_count),
                "service_pc_apply_count": int(service.audit["apply_count"]),
                "rhs_norm": source_norm,
                "solution_norm": float(solution.norm()),
            }
        )
        _marker(
            V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE[11],
            marker_callback,
            comm,
            started,
            resource_callback,
            explicit_true_residual=float(residual),
            finite=finite,
            counted_action=counted_context,
            service=service,
        )
        result["classification"] = (
            V9_E_LOR_BARE_F_EXTERNAL_POSITIVE
            if passed
            else V9_E_LOR_BARE_F_EXTERNAL_NUMERICAL_NO_SIGNAL
        )
        result["status"] = result["classification"]
        _marker(
            V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE[12],
            marker_callback,
            comm,
            started,
            resource_callback,
            status=result["status"],
            classification=result["classification"],
            external_residual_gate=passed,
            general_residual_gate=result["general_residual_gate"],
            reason=reason,
            iterations=iterations,
            counted_action=counted_context,
            service=service,
        )
        return result
    except Exception as exc:
        result["classification"] = V9_E_LOR_BARE_F_EXTERNAL_IMPLEMENTATION_FAILURE
        result["status"] = V9_E_LOR_BARE_F_EXTERNAL_IMPLEMENTATION_FAILURE
        result["failure"] = {
            "type": type(exc).__name__,
            "message": str(exc),
            "classification": V9_E_LOR_BARE_F_EXTERNAL_IMPLEMENTATION_FAILURE,
        }
        raise
    finally:
        active_exception = sys.exc_info()[1]
        cleanup_errors: list[Exception] = []

        def destroy_one(obj: Any) -> None:
            if obj is None:
                return
            try:
                obj.destroy()
            except Exception as exc:  # noqa: BLE001  # continue remaining cleanup
                cleanup_errors.append(exc)

        destroy_one(solution)
        destroy_one(rhs)
        if service is not None:
            destroy_one(service)
            lifecycle["service_destroyed"] = bool(service.destroyed)
            result["service_audit"] = _json_value(service.audit)
        for bridge in tuple(bridges.values()):
            destroy_one(bridge)
        lifecycle["bridges_destroyed"] = all(
            bool(bridge.destroyed) for bridge in bridges.values()
        )
        bridges.clear()
        destroy_one(counted_action)
        if counted_context is not None:
            destroy_one(counted_context)
            lifecycle["counted_action_destroyed"] = bool(counted_context.destroyed)
        if system is not None:
            static_context = system.static_context
            condensed = system.condensed
            mpc = getattr(system.floquet_data, "mpc", None)
            mpc_destroy_hook = callable(getattr(mpc, "destroy", None))
            system_errors_before = len(cleanup_errors)
            destroy_one(system)
            system_destroyed = len(cleanup_errors) == system_errors_before
            lifecycle["system_destroyed"] = system_destroyed
            lifecycle["static_action_destroyed"] = bool(
                static_context is not None and static_context._destroyed
            )
            lifecycle["condensed_destroyed"] = bool(condensed._destroyed)
            lifecycle["mpc_destroy_hook"] = (
                "available" if mpc_destroy_hook else "unavailable"
            )
            lifecycle["mpc_destroyed"] = (
                True
                if system_destroyed and mpc_destroy_hook
                else "not_applicable"
                if not mpc_destroy_hook
                else False
            )
            lifecycle["mpc_release_semantics"] = (
                "explicit_destroy"
                if mpc_destroy_hook
                else "scope_release_no_destroy_hook"
            )
        lifecycle["destroyable_objects_cleanup_complete"] = all(
            lifecycle[key]
            for key in (
                "ksp_destroyed",
                "pc_context_destroyed_after_ksp_destroy",
                "system_destroyed",
                "service_destroyed",
                "bridges_destroyed",
                "counted_action_destroyed",
                "static_action_destroyed",
                "condensed_destroyed",
            )
        )
        if cleanup_errors:
            cleanup_error = cleanup_errors[0]
            result["cleanup_failure"] = {
                "type": type(cleanup_error).__name__,
                "message": str(cleanup_error),
                "classification": V9_E_LOR_BARE_F_EXTERNAL_IMPLEMENTATION_FAILURE,
            }
            if active_exception is None:
                result["classification"] = (
                    V9_E_LOR_BARE_F_EXTERNAL_IMPLEMENTATION_FAILURE
                )
                result["status"] = result["classification"]
        lifecycle["cleanup_complete"] = bool(
            lifecycle["destroyable_objects_cleanup_complete"]
            and (
                lifecycle["mpc_destroyed"] is True
                or (
                    lifecycle["mpc_destroyed"] == "not_applicable"
                    and lifecycle["mpc_destroy_hook"] == "unavailable"
                )
            )
        )
        result["wall_seconds"] = float(__import__("time").monotonic() - started)
        result["lifecycle"] = lifecycle
        try:
            _marker(
                V9_E_LOR_BARE_F_EXTERNAL_MARKER_SEQUENCE[13],
                marker_callback,
                comm,
                started,
                resource_callback,
                status=result.get(
                    "status", V9_E_LOR_BARE_F_EXTERNAL_IMPLEMENTATION_FAILURE
                ),
                classification=result.get(
                    "classification",
                    V9_E_LOR_BARE_F_EXTERNAL_IMPLEMENTATION_FAILURE,
                ),
                lifecycle=_json_value(lifecycle),
                counted_action=counted_context,
                service=service,
            )
        except Exception as exc:
            result["cleanup_marker_failure"] = {
                "type": type(exc).__name__,
                "message": str(exc),
                "classification": V9_E_LOR_BARE_F_EXTERNAL_IMPLEMENTATION_FAILURE,
            }
            if active_exception is None:
                result["classification"] = (
                    V9_E_LOR_BARE_F_EXTERNAL_IMPLEMENTATION_FAILURE
                )
                result["status"] = result["classification"]
            if active_exception is None and not cleanup_errors:
                raise
        if active_exception is None and cleanup_errors:
            raise cleanup_errors[0]
