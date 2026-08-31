"""Caller-neutral one-apply wrapper for the adaptive impedance pilot."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from time import perf_counter
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from .hybrid_adaptive_impedance_mass import (
    build_actual_hcurl_cell_tangential_mass_provider,
)
from .hybrid_adaptive_impedance_schwarz import (
    build_adaptive_impedance_schwarz_action,
)
from .hybrid_side_impedance import _petsc_matrix_hash

__all__ = (
    "run_adaptive_impedance_stage_a_one_apply",
    "run_adaptive_impedance_stage_b1_preflight",
)


def _emit(
    callback: Callable[[str, Mapping[str, Any]], Any] | None,
    event: str,
    **detail: Any,
) -> Any:
    if callback is None:
        return None
    return callback(event, detail)


def _factor_inventory(diagnostics: Mapping[str, Any]) -> dict[str, Any]:
    return {
        name: diagnostics.get(name)
        for name in (
            "class_count",
            "class_reuse_saved_count",
            "class_owner_by_key",
            "owner_loads",
            "factor_bytes_global",
            "factor_nnz_global",
            "rows_min",
            "rows_median",
            "rows_max",
        )
    }


def run_adaptive_impedance_stage_b1_preflight(
    *,
    function_space: Any,
    condensed: Any,
    bare_f: PETSc.Mat,
    cell_tags: Any,
    facet_tags: Any,
    external_facet_tag: int,
    beta: complex,
    quadrature_degree: int,
    event_callback: Callable[[str, Mapping[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    if not isinstance(bare_f, PETSc.Mat):
        raise TypeError("adaptive B1 needs a PETSc bare-F matrix")
    from .hybrid_maxwell_harmonic_coarse import (
        HARD_MEMORY_BYTES,
        build_stage_b1_harmonic_identity,
    )

    comm = bare_f.getComm().tompi4py()
    provider = action = None
    result: dict[str, Any] | None = None
    action_destroyed = provider_destroyed = False
    bare_hash_before = _petsc_matrix_hash(bare_f)
    setup_started = perf_counter()
    try:
        provider = build_actual_hcurl_cell_tangential_mass_provider(
            function_space, condensed, quadrature_degree=int(quadrature_degree)
        )
        action = build_adaptive_impedance_schwarz_action(
            condensed, bare_f, raw_tangential_face_mass_by_cell=provider, beta=beta
        )
        setup_wall = float(comm.allreduce(perf_counter() - setup_started, op=MPI.MAX))
        diagnostics = dict(action.diagnostics)
        factor_inventory = _factor_inventory(diagnostics)
        factor_lifecycle = dict(diagnostics.get("factor_lifecycle", {}))
        factor_resource = _emit(
            event_callback,
            "factor_ready",
            factor_inventory=factor_inventory,
            factor_lifecycle=factor_lifecycle,
            setup_wall_seconds=setup_wall,
            pc_apply_count=0,
            action_apply_count=0,
        )
        resource_error = None
        resource = dict(factor_resource) if isinstance(factor_resource, Mapping) else {}
        if not isinstance(factor_resource, Mapping):
            resource_error = "B1 factor_ready did not return live resource data"
        rss, source = resource.get("rss_bytes"), resource.get("source")
        resource_checks = {
            "all_status_readable": resource.get("all_status_readable") is True,
            "resource_pass": resource.get("pass") is True,
            "rss_nonnegative_integer": (
                isinstance(rss, int) and not isinstance(rss, bool) and rss >= 0
            ),
            "rss_below_hard_stop": (
                isinstance(rss, int)
                and not isinstance(rss, bool)
                and 0 <= rss < int(HARD_MEMORY_BYTES)
            ),
            "swap_zero": resource.get("swap_bytes") == 0,
            "source_nonempty": isinstance(source, str) and bool(source),
        }
        if resource_error is None and not all(resource_checks.values()):
            resource_error = "B1 factor_ready resource snapshot failed strict baseline gate"
        resource_errors = comm.allgather(resource_error)
        first_resource_error = next(
            (str(error) for error in resource_errors if error is not None), None
        )
        if first_resource_error is not None:
            raise RuntimeError(first_resource_error)
        baseline = {
            "resource": resource,
            "checks": resource_checks,
            "baseline_known": True,
            "current_process_tree_baseline_bytes": int(rss),
            "current_process_tree_baseline_source": str(source),
        }
        _emit(
            event_callback,
            "b1_begin",
            resource_baseline=baseline,
            factor_lifecycle=factor_lifecycle,
            pc_apply_count=0,
            action_apply_count=0,
        )
        b1_started = perf_counter()
        evidence = build_stage_b1_harmonic_identity(
            function_space,
            condensed,
            bare_f,
            action,
            provider,
            cell_tags,
            facet_tags,
            int(external_facet_tag),
            current_process_tree_baseline_bytes=int(rss),
            current_process_tree_baseline_source=str(source),
        )
        b1_wall = float(comm.allreduce(perf_counter() - b1_started, op=MPI.MAX))
        identity_pass = evidence.get("identity_pass")
        if identity_pass is not True:
            raise RuntimeError("B1 harmonic identity gate did not pass")
        memory = evidence.get("memory_preflight", {})
        allocation_allowed = bool(memory.get("allocation_allowed"))
        _emit(
            event_callback,
            "b1_end",
            factor_lifecycle=factor_lifecycle,
            pc_apply_count=0,
            action_apply_count=0,
            patch_count=evidence.get("patch_count"),
            selected_modes_per_patch_histogram=evidence.get(
                "selected_modes_per_patch_histogram"
            ),
            selected_mode_count_total=evidence.get("selected_mode_count_total"),
            identity_pass=True,
            allocation_allowed=allocation_allowed,
            projected_peak_bytes_conservative=memory.get(
                "projected_peak_bytes_conservative"
            ),
            memory_route=memory.get("route"),
        )
        result = {
            "evidence": evidence,
            "resource_baseline": baseline,
            "factor_inventory": factor_inventory,
            "setup_wall_seconds": setup_wall,
            "b1_wall_seconds": b1_wall,
            "bare_f_hash_before": bare_hash_before,
        }
    finally:
        if action is not None and not action_destroyed:
            action.destroy()
            action_destroyed = True
        factor_lifecycle_after = {}
        if action is not None:
            factor_lifecycle_after = dict(action.diagnostics.get("factor_lifecycle", {}))
        if provider is not None and not provider_destroyed:
            provider.destroy()
            provider_destroyed = True
        bare_hash_after = _petsc_matrix_hash(bare_f)
        cleanup = {
            "action_destroyed": action_destroyed,
            "provider_destroyed": provider_destroyed,
            "factor_lifecycle_after": factor_lifecycle_after,
            "bare_f_hash_before": bare_hash_before,
            "bare_f_hash_after": bare_hash_after,
            "bare_f_unchanged": bare_hash_before == bare_hash_after,
        }
        try:
            _emit(event_callback, "cleanup", **cleanup)
        except Exception:
            if result is not None:
                raise
        if result is not None:
            result["bare_f_hash_after"] = bare_hash_after
            result["cleanup"] = cleanup
            if cleanup["bare_f_unchanged"] is not True:
                raise RuntimeError("adaptive B1 borrowed bare-F changed during preflight")
    assert result is not None
    return result


def run_adaptive_impedance_stage_a_one_apply(
    *,
    function_space: Any,
    condensed: Any,
    bare_f: PETSc.Mat,
    source: PETSc.Vec,
    source_label: str,
    beta: complex,
    quadrature_degree: int,
    event_callback: Callable[[str, Mapping[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Build the exact provider and adaptive action, then apply once.

    ``bare_f`` and ``source`` are borrowed.  This function owns the provider,
    adaptive action, target, and residual, and destroys them before return.
    Events are generic so Task-specific names remain in the benchmark layer.
    """

    if not isinstance(bare_f, PETSc.Mat) or not isinstance(source, PETSc.Vec):
        raise TypeError("adaptive Stage A needs PETSc bare-F and source objects")
    comm = bare_f.getComm().tompi4py()
    provider = None
    action = None
    target = None
    residual = None
    result: dict[str, Any] | None = None
    provider_destroyed = False
    action_destroyed = False
    target_destroyed = False
    residual_destroyed = False
    bare_hash_before = _petsc_matrix_hash(bare_f)
    setup_started = perf_counter()
    try:
        provider = build_actual_hcurl_cell_tangential_mass_provider(
            function_space,
            condensed,
            quadrature_degree=int(quadrature_degree),
        )
        action = build_adaptive_impedance_schwarz_action(
            condensed,
            bare_f,
            raw_tangential_face_mass_by_cell=provider,
            beta=beta,
        )
        setup_elapsed = float(
            comm.allreduce(perf_counter() - setup_started, op=MPI.MAX)
        )
        before = dict(action.diagnostics)
        before["stage_a_setup_wall_seconds"] = setup_elapsed
        _emit(
            event_callback,
            "factor_ready",
            factor_lifecycle=dict(before.get("factor_lifecycle", {})),
            factor_inventory=_factor_inventory(before),
            setup_wall_seconds=setup_elapsed,
            pc_apply_count=0,
            action_apply_count=int(before.get("apply_count", 0)),
        )
        target = bare_f.createVecLeft()
        residual = bare_f.createVecLeft()
        source_norm = float(source.norm())
        if not np.isfinite(source_norm) or source_norm <= 0.0:
            raise ValueError("adaptive Stage A source norm must be finite and positive")
        apply_before = int(before.get("apply_count", 0))
        _emit(
            event_callback,
            "one_apply_begin",
            source=source_label,
            checkpoint=None,
            pc_apply_count=0,
            action_apply_count=apply_before,
        )
        apply_started = perf_counter()
        action.apply(source, target)
        apply_elapsed = float(
            comm.allreduce(perf_counter() - apply_started, op=MPI.MAX)
        )
        after = dict(action.diagnostics)
        apply_after = int(after.get("apply_count", 0))
        _emit(
            event_callback,
            "one_apply_end",
            source=source_label,
            checkpoint=None,
            pc_apply_count=1,
            action_apply_count=apply_after,
            apply_count_before=apply_before,
            apply_count_after=apply_after,
            apply_count_delta=apply_after - apply_before,
            apply_elapsed_seconds=apply_elapsed,
        )
        bare_f.mult(target, residual)
        residual.axpy(PETSc.ScalarType(-1.0), source)
        output_norm = float(target.norm())
        residual_norm = float(residual.norm())
        if not all(np.isfinite(value) for value in (output_norm, residual_norm)):
            raise ValueError("adaptive Stage A output or true residual is non-finite")
        true_relative = residual_norm / max(source_norm, 1.0e-300)
        ratio_summary = after.get("last_real_apply_patch_residual_summary", {})
        ratio_local = after.get("last_real_apply_patch_residual_ratios_local", {})
        local_finite = all(np.isfinite(value) for value in ratio_local.values())
        ratios_finite = bool(comm.allreduce(local_finite, op=MPI.LAND))
        gate_checks = {
            "rows_cap": int(after.get("rows_max", 0)) <= 1024,
            "ratio_count": int(ratio_summary.get("count", -1))
            == int(after.get("patch_count", -2)),
            "ratio_finite": ratios_finite,
            "ratio_median": float(ratio_summary.get("median", np.inf)) <= 0.5,
            "ratio_p90": float(ratio_summary.get("p90", np.inf)) <= 0.9,
            "pou": float(after.get("pou_error", np.inf)) <= 1.0e-12,
            "covered_active_rows": int(after.get("covered_active_rows", -1))
            == int(after.get("active_rows", -2)),
            "setup_seconds": setup_elapsed <= 3600.0,
            "one_apply_seconds": apply_elapsed <= 1200.0,
        }
        _emit(
            event_callback,
            "checkpoint",
            source=source_label,
            checkpoint="one_apply",
            pc_apply_count=1,
            action_apply_count=apply_after,
            source_norm=source_norm,
            output_norm=output_norm,
            true_residual_norm=residual_norm,
            true_residual_relative=true_relative,
            patch_residual_summary=ratio_summary,
            patch_residual_ratios_local=ratio_local,
            gate_checks=gate_checks,
        )
        action.release_diagnostic_matrices()
        after_release = dict(action.diagnostics)
        result = {
            "source_label": source_label,
            "source_norm": source_norm,
            "output_norm": output_norm,
            "true_residual_norm": residual_norm,
            "true_residual_relative": true_relative,
            "apply_elapsed_seconds": apply_elapsed,
            "setup_elapsed_seconds": setup_elapsed,
            "action_apply_count_before": apply_before,
            "action_apply_count_after": apply_after,
            "action_apply_count_delta": apply_after - apply_before,
            "bare_f_hash_before": bare_hash_before,
            "action_diagnostics_before_apply": before,
            "action_diagnostics_after_apply": after,
            "action_diagnostics_after_release": after_release,
            "patch_residual_summary": ratio_summary,
            "patch_residual_ratios_local": ratio_local,
            "gate_checks": gate_checks,
        }
    finally:
        if action is not None and not action_destroyed:
            action.destroy()
            action_destroyed = True
        if provider is not None and not provider_destroyed:
            provider.destroy()
            provider_destroyed = True
        if residual is not None:
            residual.destroy()
            residual_destroyed = True
        if target is not None:
            target.destroy()
            target_destroyed = True
        action_after_cleanup = {}
        if action is not None:
            action_after_cleanup = dict(action.diagnostics)
        bare_hash_after = _petsc_matrix_hash(bare_f)
        cleanup = {
            "result_generated": result is not None,
            "provider_destroyed": provider_destroyed,
            "action_destroyed": action_destroyed,
            "target_destroyed": target_destroyed,
            "residual_destroyed": residual_destroyed,
            "factor_lifecycle_after_cleanup": action_after_cleanup.get(
                "factor_lifecycle", {}
            ),
            "bare_f_hash_before": bare_hash_before,
            "bare_f_hash_after": bare_hash_after,
            "bare_f_unchanged": bare_hash_before == bare_hash_after,
        }
        _emit(event_callback, "cleanup", **cleanup)
        if result is not None:
            result["bare_f_hash_after"] = bare_hash_after
            result["cleanup"] = cleanup
    if result is None:
        raise RuntimeError("adaptive Stage A produced no result")
    return result
