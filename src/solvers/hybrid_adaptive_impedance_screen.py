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
    "run_adaptive_impedance_stage_bc_screen",
    "run_v9_c0_explicit_coarse_oracle",
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


_STAGE_BC_INITIAL_SOURCES = (
    "external_dtn_coupling",
    "fixed_random_repeat_0",
)
_STAGE_BC_HOLDOUT_SOURCES = (
    "modal_traction_positive",
    "modal_traction_negative",
    "fixed_random_repeat_1",
)
_STAGE_BC_PLANNED_SOURCES = _STAGE_BC_INITIAL_SOURCES + _STAGE_BC_HOLDOUT_SOURCES
_STAGE_BC_ROUTE_C_R64 = {
    "external_dtn_coupling": 0.8906247440000827,
    "fixed_random_repeat_0": 1.036891675911675,
}
_STAGE_BC_POSITIVE = "ADAPTIVE_SPECTRAL_SCHWARZ_POSITIVE_AT_H4"
_STAGE_BC_NO_SIGNAL = "ADAPTIVE_SPECTRAL_SCHWARZ_NO_SIGNAL_AT_H4"
_STAGE_BC_UNSTABLE = "ADAPTIVE_SPECTRAL_SCHWARZ_UNSTABLE_AT_H4"
_STAGE_BC_INCONCLUSIVE = "ADAPTIVE_SPECTRAL_SCHWARZ_INCONCLUSIVE_AT_H4"
_STAGE_BC_RESOURCE = "ADAPTIVE_ECONOMICAL_COARSE_RESOURCE_UNAVAILABLE"
_STAGE_BC_IMPLEMENTATION_FAILURE = "V8_ADAPTIVE_STAGE_BC_IMPLEMENTATION_FAILURE"
_STAGE_BC_CHECKPOINTS = (16, 32, 64)
_V9_C0_LOCAL_BASELINE = 2.390497409724407
_V9_C0_POSITIVE = "ADAPTIVE_COARSE_CONTENT_POSITIVE_EXPLICIT_ORACLE"
_V9_C0_NO_SIGNAL = "CURRENT_160_PER_PATCH_HARMONIC_COARSE_NO_SIGNAL"
_V9_C0_RESOURCE = "ADAPTIVE_COARSE_EXPLICIT_RESOURCE_OR_TIME_UNAVAILABLE"
_V9_C0_NEXT_C1 = "V9_C1_MATRIX_FREE_GALERKIN_COARSE"
_V9_C0_NEXT_E = "V9_E_STRUCTURED_BACKGROUND_FIXED_LOR"


def _stage_bc_slope(r32: float, r64: float) -> float | None:
    if r32 == 0.0 and r64 == 0.0:
        return None
    if r32 > 0.0 and r64 == 0.0:
        return float("inf")
    if r32 == 0.0 and r64 > 0.0:
        return float("-inf")
    return float(np.log10(r32 / r64)) if r32 > 0.0 and r64 > 0.0 else None


def _stage_bc_record_usable(record: Mapping[str, Any] | None) -> bool:
    if not isinstance(record, Mapping):
        return False
    reason = record.get("ksp_reason")
    bounded = {
        int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_ITS", -3)),
        int(
            getattr(
                PETSc.KSP.ConvergedReason,
                "DIVERGED_MAX_IT",
                getattr(PETSc.KSP.ConvergedReason, "DIVERGED_ITS", -3),
            )
        ),
    }
    if (
        not isinstance(reason, (int, np.integer))
        or isinstance(reason, bool)
        or int(reason) == 0
        or (int(reason) < 0 and int(reason) not in bounded)
    ):
        return False
    checkpoints = record.get("checkpoints")
    if not isinstance(checkpoints, Mapping):
        return False
    required = (
        "reported_residual_relative",
        "reported_residual_absolute",
        "true_residual_absolute",
        "true_residual_relative",
        "rhs_norm",
        "solution_norm",
    )
    for iteration in _STAGE_BC_CHECKPOINTS:
        row = checkpoints.get(str(iteration))
        if not isinstance(row, Mapping) or row.get("finite") is not True:
            return False
        if any(
            not isinstance(row.get(name), (int, float, np.number))
            or isinstance(row.get(name), bool)
            or not np.isfinite(float(row[name]))
            or float(row[name]) < 0.0
            for name in required
        ):
            return False
    return bool(
        record.get("finite") is True
        and all(
            isinstance(record.get(name), (int, float, np.number))
            and not isinstance(record.get(name), bool)
            and np.isfinite(float(record[name]))
            and float(record[name]) >= 0.0
            for name in (
                "rhs_norm",
                "final_true_residual_absolute",
                "final_true_residual_relative",
                "solution_norm",
            )
        )
    )


def _classify_stage_bc_sources(records: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    per_source: dict[str, Any] = {}
    for label in _STAGE_BC_INITIAL_SOURCES:
        record = records.get(label)
        checkpoints = record.get("checkpoints", {}) if record else {}
        missing = [str(i) for i in _STAGE_BC_CHECKPOINTS if str(i) not in checkpoints]
        if record is not None and record.get("implementation_failure"):
            return {
                "classification": _STAGE_BC_IMPLEMENTATION_FAILURE,
                "per_source": per_source,
            }
        if record is None or missing or not _stage_bc_record_usable(record):
            return {"classification": _STAGE_BC_UNSTABLE, "per_source": per_source}
        values = {
            i: float(checkpoints[str(i)]["true_residual_relative"])
            for i in _STAGE_BC_CHECKPOINTS
        }
        if not all(np.isfinite(value) for value in values.values()):
            return {
                "classification": _STAGE_BC_UNSTABLE,
                "per_source": per_source,
            }
        slope = _stage_bc_slope(values[32], values[64])
        improvement = (
            float(_STAGE_BC_ROUTE_C_R64[label] / values[64])
            if values[64] > 0.0
            else float("inf")
        )
        per_source[label] = {
            "r16": values[16],
            "r32": values[32],
            "r64": values[64],
            "slope_log10_r32_over_r64": slope,
            "route_c_r64_baseline": _STAGE_BC_ROUTE_C_R64[label],
            "route_c_improvement_factor": improvement,
        }
    left, right = (
        per_source[_STAGE_BC_INITIAL_SOURCES[0]],
        per_source[_STAGE_BC_INITIAL_SOURCES[1]],
    )
    slopes = (left["slope_log10_r32_over_r64"], right["slope_log10_r32_over_r64"])
    positive = (
        all(value is not None and value >= 0.15 for value in slopes)
        and (
            left["r64"] <= 0.5
            and right["r64"] <= 0.5
            or left["route_c_improvement_factor"] >= 4.0
            and right["route_c_improvement_factor"] >= 4.0
        )
    )
    no_signal = (
        left["r64"] > 0.8
        and right["r64"] > 0.8
        and all(value is not None and value < 0.10 for value in slopes)
    )
    return {
        "classification": (
            _STAGE_BC_POSITIVE
            if positive
            else _STAGE_BC_NO_SIGNAL
            if no_signal
            else _STAGE_BC_INCONCLUSIVE
        ),
        "per_source": per_source,
        "positive_gate": {
            "finite": True,
            "slope": all(value is not None and value >= 0.15 for value in slopes),
            "both_r64_le_0_5": left["r64"] <= 0.5 and right["r64"] <= 0.5,
            "both_route_c_improvement_ge_4": (
                left["route_c_improvement_factor"] >= 4.0
                and right["route_c_improvement_factor"] >= 4.0
            ),
        },
    }


class _StageBCRightFGMRES:
    """One fixed right-FGMRES/KSP setup reused for every source."""

    class _PCContext:
        def __init__(self, owner: _StageBCRightFGMRES) -> None:
            self.owner = owner
            self.count = 0

        def apply(self, _pc: PETSc.PC, source: PETSc.Vec, target: PETSc.Vec) -> None:
            self.owner.right_action.apply(source, target)
            self.count += 1

        def destroy(self, _pc: PETSc.PC | None = None) -> None:
            return None

    def __init__(
        self,
        operator: PETSc.Mat,
        right_action: Any,
        *,
        max_it: int = 64,
        checkpoints: tuple[int, ...] = _STAGE_BC_CHECKPOINTS,
    ) -> None:
        if not isinstance(operator, PETSc.Mat) or not callable(
            getattr(right_action, "apply", None)
        ):
            raise TypeError("Stage-B/C FGMRES needs an operator and right action")
        if (
            not isinstance(max_it, int)
            or isinstance(max_it, bool)
            or max_it <= 0
        ):
            raise ValueError("FGMRES max_it must be a positive integer")
        if (
            not isinstance(checkpoints, tuple)
            or not checkpoints
            or any(
                not isinstance(value, int)
                or isinstance(value, bool)
                or value <= 0
                or value > max_it
                for value in checkpoints
            )
            or tuple(sorted(set(checkpoints))) != checkpoints
        ):
            raise ValueError("FGMRES checkpoints must be sorted positive integers")
        self.operator, self.right_action = operator, right_action
        self.max_it = int(max_it)
        self.checkpoints = tuple(int(value) for value in checkpoints)
        self.solution = operator.createVecRight()
        self.monitor = operator.createVecRight()
        self.residual = operator.createVecLeft()
        self.context = self._PCContext(self)
        self.ksp = PETSc.KSP().create(operator.getComm())
        self.ksp.setOperators(operator)
        self.ksp.setType(PETSc.KSP.Type.FGMRES)
        self.ksp.setPCSide(PETSc.PC.Side.RIGHT)
        self.ksp.setGMRESRestart(32)
        self.ksp.setNormType(PETSc.KSP.NormType.UNPRECONDITIONED)
        self.ksp.setInitialGuessNonzero(False)
        self.ksp.setTolerances(rtol=0.0, atol=0.0, max_it=self.max_it)
        pc = self.ksp.getPC()
        pc.setType(PETSc.PC.Type.PYTHON)
        pc.setPythonContext(self.context)
        self.ksp.setUp()
        self.destroyed = False

    def solve(
        self,
        rhs: PETSc.Vec,
        label: str,
        checkpoint_callback: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if self.destroyed:
            raise RuntimeError("Stage-B/C FGMRES is destroyed")
        rhs_norm = float(rhs.norm())
        if not np.isfinite(rhs_norm) or rhs_norm <= 1.0e-300:
            raise ValueError("Stage-B/C source norm must be finite and nonzero")
        denominator = max(rhs_norm, 1.0e-300)
        self.solution.set(0.0)
        self.monitor.set(0.0)
        self.residual.set(0.0)
        checkpoints: dict[str, dict[str, Any]] = {}
        started, apply_before = perf_counter(), self.context.count

        def check(iteration: int, reported: float, current: PETSc.Vec) -> None:
            self.residual.set(0.0)
            self.operator.mult(current, self.residual)
            self.residual.axpy(PETSc.ScalarType(-1.0), rhs)
            absolute = float(self.residual.norm())
            solution_norm = float(current.norm())
            reported_relative = float(reported)
            row = {
                "iteration": int(iteration),
                "reported_residual_relative": reported_relative,
                "reported_residual_absolute": reported_relative * denominator,
                "true_residual_absolute": absolute,
                "true_residual_relative": absolute / denominator,
                "rhs_norm": rhs_norm,
                "solution_norm": solution_norm,
                "finite": bool(
                    all(
                        np.isfinite(value)
                        for value in (
                            reported_relative,
                            reported_relative * denominator,
                            absolute,
                            absolute / denominator,
                            rhs_norm,
                            solution_norm,
                        )
                    )
                ),
                "right_pc_apply_count": self.context.count - apply_before,
            }
            checkpoints[str(iteration)] = row
            if checkpoint_callback is not None:
                checkpoint_callback(row)

        def convergence(
            current: PETSc.KSP, iteration: int, residual_norm: float
        ) -> int:
            if int(iteration) in self.checkpoints:
                returned = current.buildSolution(self.monitor)
                solution = self.monitor if returned is None else returned
                check(
                    int(iteration),
                    float(residual_norm) / denominator,
                    solution,
                )
            return 0

        self.ksp.setConvergenceTest(convergence)
        self.ksp.solve(rhs, self.solution)
        iterations = int(self.ksp.getIterationNumber())
        if iterations >= self.max_it and str(self.max_it) not in checkpoints:
            check(
                self.max_it,
                float(self.ksp.getResidualNorm()) / denominator,
                self.solution,
            )
        self.residual.set(0.0)
        self.operator.mult(self.solution, self.residual)
        self.residual.axpy(PETSc.ScalarType(-1.0), rhs)
        final_absolute = float(self.residual.norm())
        final_solution_norm = float(self.solution.norm())
        reason = int(self.ksp.getConvergedReason())
        bounded = {
            int(getattr(PETSc.KSP.ConvergedReason, "DIVERGED_ITS", -3)),
            int(
                getattr(
                    PETSc.KSP.ConvergedReason,
                    "DIVERGED_MAX_IT",
                    getattr(PETSc.KSP.ConvergedReason, "DIVERGED_ITS", -3),
                )
            ),
        }
        finite = bool(
            np.isfinite(final_absolute)
            and np.isfinite(final_solution_norm)
            and np.isfinite(rhs_norm)
            and all(
                row["finite"]
                and np.isfinite(row["reported_residual_relative"])
                and np.isfinite(row["reported_residual_absolute"])
                and np.isfinite(row["true_residual_relative"])
                and np.isfinite(row["rhs_norm"])
                and np.isfinite(row["solution_norm"])
                for row in checkpoints.values()
            )
        )
        comm = self.operator.getComm().tompi4py()
        wall_seconds = float(
            comm.allreduce(perf_counter() - started, op=MPI.MAX)
        )
        return {
            "label": label,
            "checkpoints": checkpoints,
            "rhs_norm": rhs_norm,
            "solution_norm": final_solution_norm,
            "final_true_residual_absolute": final_absolute,
            "final_true_residual_relative": final_absolute / denominator,
            "finite": finite,
            "ksp_reason": reason,
            "ksp_breakdown": bool(reason < 0 and reason not in bounded),
            "solver_failure": bool(reason == 0),
            "iterations": iterations,
            "right_pc_apply_count": self.context.count - apply_before,
            "outer_ksp_setup_reused": True,
            "restart": 32,
            "max_it": self.max_it,
            "rtol": 0.0,
            "atol": 0.0,
            "zero_initial_guess": True,
            "pc_side": "right",
            "norm_type": "unpreconditioned",
            "wall_seconds": wall_seconds,
        }

    def destroy(self) -> None:
        if self.destroyed:
            return
        self.ksp.destroy()
        self.residual.destroy()
        self.monitor.destroy()
        self.solution.destroy()
        self.destroyed = True


def _stage_bc_safe_destroy(obj: Any | None) -> bool:
    if obj is None:
        return False
    try:
        obj.destroy()
    except Exception:  # noqa: BLE001 - cleanup must remain best-effort
        return False
    return True


def _classify_v9_c0_one_apply(
    rho_coarse: float,
    *,
    rho_local: float = _V9_C0_LOCAL_BASELINE,
) -> dict[str, Any]:
    rho = float(rho_coarse)
    baseline = float(rho_local)
    finite = bool(
        np.isfinite(rho)
        and np.isfinite(baseline)
        and rho >= 0.0
        and baseline > 0.0
    )
    improvement = float(baseline / rho) if finite and rho > 0.0 else float("inf")
    if not finite:
        band = "nonfinite_or_unstable"
    elif rho <= 0.5:
        band = "strong_positive"
    elif rho <= 1.0 or improvement >= 2.0:
        band = "weak_positive"
    elif rho >= 1.5:
        band = "no_signal"
    else:
        band = "intermediate"
    classification = (
        None
        if band == "intermediate"
        else _V9_C0_NO_SIGNAL
        if band in {"nonfinite_or_unstable", "no_signal"}
        else _V9_C0_POSITIVE
    )
    return {
        "classification": classification,
        "band": band,
        "rho_local": baseline,
        "rho_coarse": rho,
        "improvement_factor": improvement,
        "needs_outer_fgmres": classification is None,
        "numerical_negative": classification == _V9_C0_NO_SIGNAL,
        "next_required_stage": (
            _V9_C0_NEXT_E
            if classification == _V9_C0_NO_SIGNAL
            else _V9_C0_NEXT_C1
            if classification == _V9_C0_POSITIVE
            else None
        ),
    }


def _classify_v9_c0_outer_result(
    initial: Mapping[str, Any],
    outer_record: Mapping[str, Any],
) -> dict[str, Any]:
    checkpoints = outer_record.get("checkpoints", {})
    row = checkpoints.get("8") if isinstance(checkpoints, Mapping) else None
    value = row.get("true_residual_relative") if isinstance(row, Mapping) else None
    r8 = float(value) if isinstance(value, (int, float, np.number)) and not isinstance(value, bool) else float("nan")
    decline = (
        float(np.log10(1.0 / r8))
        if np.isfinite(r8) and r8 > 0.0
        else float("inf")
        if r8 == 0.0
        else float("nan")
    )
    weak_positive = bool(
        outer_record.get("finite") is True
        and np.isfinite(r8)
        and r8 >= 0.0
        and (r8 <= 0.8 or decline >= 0.20)
    )
    classification = _V9_C0_POSITIVE if weak_positive else _V9_C0_NO_SIGNAL
    return {
        **dict(initial),
        "classification": classification,
        "band": "weak_positive_after_outer_8" if weak_positive else "no_signal_after_outer_8",
        "r8": r8,
        "zero_solution_relative_decline_decades": decline,
        "outer_gate": {
            "finite": outer_record.get("finite") is True,
            "r8_le_0_8": bool(np.isfinite(r8) and r8 <= 0.8),
            "zero_solution_decline_ge_0_20_decade": bool(
                np.isfinite(decline) and decline >= 0.20
            ),
        },
        "numerical_negative": classification == _V9_C0_NO_SIGNAL,
        "next_required_stage": (
            _V9_C0_NEXT_C1 if weak_positive else _V9_C0_NEXT_E
        ),
    }


class _V9C0ResourceStop(RuntimeError):
    """Internal signal for a failed live C0 resource gate."""

    def __init__(
        self,
        resource: Mapping[str, Any],
        checks: Mapping[str, Any],
        error: str,
    ) -> None:
        self.resource = dict(resource)
        self.checks = dict(checks)
        self.error = str(error)
        super().__init__(self.error)


def _v9_c0_resource_audit(
    resource_callback: Callable[[], Mapping[str, Any]] | None,
    hard_memory_bytes: int,
) -> tuple[dict[str, Any], dict[str, bool], str | None]:
    if not callable(resource_callback):
        return {}, {"callback": False}, "C0 requires a resource callback"
    raw = resource_callback()
    if not isinstance(raw, Mapping):
        return {}, {"mapping": False}, "resource callback did not return a mapping"
    resource = dict(raw)
    rss = resource.get("rss_bytes")
    wall_observation = resource.get("wall_observation")
    checks = {
        "all_status_readable": resource.get("all_status_readable") is True,
        "resource_pass": resource.get("pass") is True,
        "rss_integer_below_hard": (
            isinstance(rss, (int, np.integer))
            and not isinstance(rss, bool)
            and 0 <= int(rss) < int(hard_memory_bytes)
        ),
        "swap_zero": resource.get("swap_bytes") == 0,
        "source_nonempty": isinstance(resource.get("source"), str)
        and bool(resource.get("source")),
        "wall_pass": (
            isinstance(wall_observation, Mapping)
            and wall_observation.get("pass") is True
        ),
    }
    return resource, checks, None if all(checks.values()) else "live C0 resource gate failed"


def run_v9_c0_explicit_coarse_oracle(
    *,
    function_space: Any,
    condensed: Any,
    bare_f: PETSc.Mat,
    facet_tags: Any,
    external_facet_tag: int,
    beta: complex,
    quadrature_degree: int,
    source_builder: Callable[[str], tuple[PETSc.Vec, Mapping[str, Any]]],
    resource_callback: Callable[[], Mapping[str, Any]] | None,
    phase_callback: Callable[[str, Mapping[str, Any]], Any] | None,
    hard_memory_bytes: int,
    event_callback: Callable[[str, Mapping[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Thin public entry point for the V9-C0 explicit coarse oracle."""

    return run_adaptive_impedance_stage_bc_screen(
        function_space=function_space,
        condensed=condensed,
        bare_f=bare_f,
        facet_tags=facet_tags,
        external_facet_tag=external_facet_tag,
        beta=beta,
        quadrature_degree=quadrature_degree,
        source_builder=source_builder,
        event_callback=event_callback,
        _profile="v9_c0",
        _hard_memory_bytes=hard_memory_bytes,
        _resource_callback=resource_callback,
        _phase_callback=phase_callback,
    )


def run_adaptive_impedance_stage_bc_screen(
    *,
    function_space: Any,
    condensed: Any,
    bare_f: PETSc.Mat,
    facet_tags: Any,
    external_facet_tag: int,
    beta: complex,
    quadrature_degree: int,
    source_builder: Callable[[str], tuple[PETSc.Vec, Mapping[str, Any]]],
    event_callback: Callable[[str, Mapping[str, Any]], Any] | None = None,
    _profile: str = "ordinary",
    _hard_memory_bytes: int | None = None,
    _resource_callback: Callable[[], Mapping[str, Any]] | None = None,
    _phase_callback: Callable[[str, Mapping[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    """Run Stage-B/C on one borrowed current bottom bare-F system."""

    from .hybrid_adaptive_impedance_stage_bc import (
        build_adaptive_impedance_stage_bc_action,
    )
    from .hybrid_maxwell_harmonic_coarse import HARD_MEMORY_BYTES
    from .hybrid_maxwell_harmonic_economical import (
        prepare_economical_gamma_rhs,
        solve_prepared_economical_columns,
    )

    if not isinstance(bare_f, PETSc.Mat) or not callable(source_builder):
        raise TypeError("Stage-B/C needs a PETSc bare-F and source builder")
    if _profile not in {"ordinary", "v9_c0"}:
        raise ValueError(f"unknown Stage-B/C profile: {_profile}")
    c0 = _profile == "v9_c0"
    if c0 and (
        not isinstance(_hard_memory_bytes, (int, np.integer))
        or isinstance(_hard_memory_bytes, bool)
        or int(_hard_memory_bytes) <= 0
    ):
        raise ValueError("C0 hard_memory_bytes must be a positive integer")
    c0_hard_memory_bytes = (
        int(_hard_memory_bytes) if c0 else int(HARD_MEMORY_BYTES)
    )
    comm = bare_f.getComm().tompi4py()
    provider = preparation = local_action = harmonic_space = coarse_action = None
    outer_solver = None
    result: dict[str, Any] | None = None
    provider_destroyed = preparation_destroyed = False
    local_action_destroyed = harmonic_released = False
    harmonic_consumed = preparation_consumed = False
    prepared_rhs_released = False
    outer_solver_destroyed = coarse_action_destroyed = False
    provider_created = preparation_created = local_action_created = False
    harmonic_space_created = coarse_action_created = outer_solver_created = False
    source_destroyed_count = 0
    direct_target = direct_residual = None
    c0_phase_diagnostics: dict[str, Mapping[str, Any]] = {}
    local_factor_lifecycle: dict[str, Any] = {}
    harmonic_audit: dict[str, Any] = {}
    bare_before = _petsc_matrix_hash(bare_f)
    setup_started = perf_counter()

    def factor_lifecycle() -> dict[str, Any]:
        if local_action is None:
            return dict(local_factor_lifecycle)
        return dict(local_action.diagnostics.get("factor_lifecycle", {}))

    def local_action_apply_count() -> int:
        if local_action is None:
            return 0
        return int(local_action.diagnostics.get("apply_count", 0))

    def coarse_action_apply_count() -> int:
        if coarse_action is None:
            return 0
        return int(coarse_action.diagnostics.get("apply_count", 0))

    def compact_harmonic_audit(space: Any) -> dict[str, Any]:
        local_histogram: dict[str, int] = {}
        for record in space.local_patch_records:
            selected = int(record.columns.shape[1])
            local_histogram[str(selected)] = local_histogram.get(str(selected), 0) + 1
        histogram: dict[str, int] = {}
        for item in comm.allgather(local_histogram):
            for key, value in item.items():
                histogram[key] = histogram.get(key, 0) + int(value)
        diagnostics = space.diagnostics
        return {
            "global_patch_count": int(diagnostics["global_patch_count"]),
            "local_patch_count": int(diagnostics["local_patch_count"]),
            "global_retained_rank": int(diagnostics["global_retained_rank"]),
            "selected_mode_count_total": int(diagnostics["global_retained_rank"]),
            "selected_modes_per_patch_histogram": histogram,
            "harmonic_multi_rhs_solve_count": int(
                diagnostics["harmonic_multi_rhs_solve_count"]
            ),
            "generalized_eigenproblem": False,
            "total_coarse_dof": int(diagnostics["global_retained_rank"]),
            "eigenvalue_gaps": "not_applicable_economical_variant",
        }

    def emit_c0_phase(name: str, detail: Mapping[str, Any]) -> None:
        if not c0:
            return
        payload = dict(detail)
        resource, checks, resource_error = _v9_c0_resource_audit(
            _resource_callback, c0_hard_memory_bytes
        )
        payload.update(
            {
                "resource": resource,
                "resource_checks": checks,
                "rss_bytes": resource.get("rss_bytes"),
                "swap_bytes": resource.get("swap_bytes"),
            }
        )
        if resource_error is not None:
            payload["resource_error"] = resource_error
        c0_phase_diagnostics[name] = payload
        if _phase_callback is not None:
            _phase_callback(name, payload)
        _emit(event_callback, name, **payload)
        if resource_error is not None:
            raise _V9C0ResourceStop(resource, checks, resource_error)

    def emit_c0_event(event: str, **detail: Any) -> None:
        if c0:
            payload = {
                "factor_lifecycle": factor_lifecycle(),
                "action_apply_count": coarse_action_apply_count(),
                "local_action_apply_count": local_action_apply_count(),
                **detail,
            }
            _emit(
                event_callback,
                event,
                **payload,
            )

    try:
        provider = build_actual_hcurl_cell_tangential_mass_provider(
            function_space, condensed, quadrature_degree=int(quadrature_degree)
        )
        provider_created = True
        preparation = prepare_economical_gamma_rhs(
            function_space, condensed, provider, facet_tags, int(external_facet_tag)
        )
        preparation_created = True
        _emit(
            event_callback,
            "gamma_rhs_ready",
            patch_count=preparation.diagnostics.get("global_patch_count"),
            pc_apply_count=0,
            action_apply_count=0,
            local_action_apply_count=0,
            source=None,
            checkpoint=None,
            factor_lifecycle=factor_lifecycle(),
        )
        local_action = build_adaptive_impedance_schwarz_action(
            condensed,
            bare_f,
            raw_tangential_face_mass_by_cell=provider,
            beta=beta,
        )
        local_action_created = True
        factor_inventory = _factor_inventory(local_action.diagnostics)
        _emit(
            event_callback,
            "factor_ready",
            factor_inventory=factor_inventory,
            factor_lifecycle=factor_lifecycle(),
            pc_apply_count=0,
            action_apply_count=coarse_action_apply_count(),
            local_action_apply_count=local_action_apply_count(),
            source=None,
            checkpoint=None,
        )
        harmonic_space = solve_prepared_economical_columns(
            preparation, local_action, provider.collective_audit()
        )
        harmonic_space_created = True
        preparation_consumed = bool(getattr(preparation, "_consumed", True))
        prepared_rhs_released = bool(
            preparation.diagnostics.get("prepared_rhs_released", False)
        )
        harmonic_audit = compact_harmonic_audit(harmonic_space)
        _emit(
            event_callback,
            "harmonic_columns_ready",
            harmonic_diagnostics=harmonic_audit,
            factor_lifecycle=factor_lifecycle(),
            pc_apply_count=0,
            action_apply_count=coarse_action_apply_count(),
            local_action_apply_count=local_action_apply_count(),
            source=None,
            checkpoint=None,
        )
        local_action.release_diagnostic_matrices()
        local_factor_lifecycle = factor_lifecycle()
        if _stage_bc_safe_destroy(provider):
            provider_destroyed = True
            provider = None
        if _stage_bc_safe_destroy(preparation):
            preparation_destroyed = True
            preparation = None
        preparation_consumed = preparation_consumed or preparation_destroyed
        prepared_rhs_released = prepared_rhs_released or preparation_destroyed
        setup_wall = float(comm.allreduce(perf_counter() - setup_started, op=MPI.MAX))
        if c0:
            resource, checks, local_resource_error = _v9_c0_resource_audit(
                _resource_callback, c0_hard_memory_bytes
            )
            _emit(
                event_callback,
                "memory_preflight",
                setup_wall_seconds=setup_wall,
                resource=resource,
                resource_checks=checks,
                factor_inventory=factor_inventory,
                factor_lifecycle=factor_lifecycle(),
                pc_apply_count=0,
                action_apply_count=coarse_action_apply_count(),
                local_action_apply_count=local_action_apply_count(),
                source=None,
                checkpoint=None,
            )
            errors = comm.allgather(local_resource_error)
        else:
            resource_snapshot = _emit(
                event_callback,
                "memory_preflight",
                setup_wall_seconds=setup_wall,
                factor_inventory=factor_inventory,
                factor_lifecycle=factor_lifecycle(),
                pc_apply_count=0,
                action_apply_count=coarse_action_apply_count(),
                local_action_apply_count=local_action_apply_count(),
                source=None,
                checkpoint=None,
            )
            resource = (
                dict(resource_snapshot)
                if isinstance(resource_snapshot, Mapping)
                else {}
            )
            rss = resource.get("rss_bytes")
            checks = {
                "all_status_readable": resource.get("all_status_readable") is True,
                "resource_pass": resource.get("pass") is True,
                "rss_integer_below_hard": (
                    isinstance(rss, int)
                    and not isinstance(rss, bool)
                    and 0 <= rss < int(HARD_MEMORY_BYTES)
                ),
                "swap_zero": resource.get("swap_bytes") == 0,
                "source_nonempty": isinstance(resource.get("source"), str)
                and bool(resource.get("source")),
                "wall_pass": (
                    isinstance(resource.get("wall_observation"), Mapping)
                    and resource["wall_observation"].get("pass") is True
                ),
            }
            errors = comm.allgather(
                None if all(checks.values()) else "live baseline failed"
            )
        resource_error = next((value for value in errors if value), None)
        rss = resource.get("rss_bytes")
        if c0:
            base = {
                "schema": "task040.v9.c0.explicit_coarse_oracle.v1",
                "method": "v9_c0_explicit_coarse_oracle",
                "profile": "task040.v9.c0.explicit_coarse_only.v1",
                "formal_adjudication": False,
                "executed": True,
                "source_order": ["external_dtn_coupling"],
                "rho_local": _V9_C0_LOCAL_BASELINE,
                "hard_memory_bytes": c0_hard_memory_bytes,
                "phase_diagnostics": c0_phase_diagnostics,
                "outer_fgmres_initially": False,
                "full_side_factor_count": 0,
                "global_direct_factor_count": 0,
                "coarse_direct_factor_count": 0,
                "factor_inventory": factor_inventory,
                "harmonic_audit": harmonic_audit,
                "setup_wall_seconds": setup_wall,
                "bare_f_hash_before": bare_before,
            }
        else:
            base = {
                "schema": "task040.v8.adaptive_impedance_schwarz.stage_bc.v1",
                "method": "adaptive_impedance_stage_bc_two_source_screen",
                "profile": "task040.v8.adaptive_impedance_schwarz.stage_bc.v1",
                "pass": None,
                "formal_adjudication": False,
                "executed": True,
                "planned_source_order": list(_STAGE_BC_PLANNED_SOURCES),
                "factor_inventory": factor_inventory,
                "harmonic_audit": harmonic_audit,
                "setup_wall_seconds": setup_wall,
                "bare_f_hash_before": bare_before,
            }
        def c0_resource_result(
            resource_data: Mapping[str, Any],
            resource_checks: Mapping[str, Any],
            error: Any,
        ) -> dict[str, Any]:
            emit_c0_event(
                "classification",
                classification=_V9_C0_RESOURCE,
                next_required_stage=_V9_C0_NEXT_C1,
                numerical_negative=False,
                source=None,
                checkpoint=None,
            )
            return {
                **base,
                "status": _V9_C0_RESOURCE,
                "classification": _V9_C0_RESOURCE,
                "next_required_stage": _V9_C0_NEXT_C1,
                "numerical_negative": False,
                "resource_unavailable": True,
                "resource_error": None if error is None else str(error),
                "resource": dict(resource_data),
                "resource_checks": dict(resource_checks),
                "source_order": [],
                "executed_source_order": [],
                "one_apply": None,
                "outer_record": None,
            }

        if resource_error is not None:
            if c0:
                result = c0_resource_result(resource, checks, resource_error)
                return result
            _emit(
                event_callback,
                "classification",
                classification=_STAGE_BC_RESOURCE,
                factor_lifecycle=factor_lifecycle(),
                pc_apply_count=0,
                action_apply_count=coarse_action_apply_count(),
                local_action_apply_count=local_action_apply_count(),
                source=None,
                checkpoint=None,
            )
            result = {
                **base,
                "status": _STAGE_BC_RESOURCE,
                "classification": _STAGE_BC_RESOURCE,
                "executed_source_order": [],
                "initial_classification": None,
                "five_source_extension_status": "not_triggered",
                "no_source_or_outer_ksp": True,
                "resource_baseline": {
                    "resource": resource,
                    "checks": checks,
                    "error": str(resource_error),
                    "baseline_known": False,
                },
                "coarse_diagnostics": None,
                "allocated_object_count": {
                    "P": 0,
                    "P_H": 0,
                    "FP": 0,
                    "Ac": 0,
                    "KSP": 0,
                    "outer_KSP": 0,
                },
            }
            return result
        baseline = {
            "resource": resource,
            "checks": checks,
            "baseline_known": True,
            "current_process_tree_baseline_bytes": int(rss),
            "current_process_tree_baseline_source": str(resource["source"]),
        }
        coarse_started = perf_counter()
        coarse_kwargs = {
            "harmonic_space": harmonic_space,
            "action": local_action,
            "fine_operator": bare_f,
            "current_process_tree_baseline_bytes": int(rss),
            "current_process_tree_baseline_source": str(resource["source"]),
        }
        if c0:
            coarse_kwargs.update(
                hard_memory_bytes=c0_hard_memory_bytes,
                phase_callback=emit_c0_phase,
            )
        try:
            coarse_result = build_adaptive_impedance_stage_bc_action(**coarse_kwargs)
        except _V9C0ResourceStop as stop:
            result = c0_resource_result(stop.resource, stop.checks, stop.error)
            return result
        if coarse_result.action is not None:
            coarse_action_created = True
        coarse_wall = float(comm.allreduce(perf_counter() - coarse_started, op=MPI.MAX))
        coarse_diagnostics = dict(coarse_result.diagnostics)
        coarse_diagnostics["coarse_setup_wall_seconds"] = coarse_wall
        if coarse_result.action is not None:
            coarse_action = coarse_result.action
            harmonic_consumed = True
            harmonic_released = True
            harmonic_space = None
        _emit(
            event_callback,
            "coarse_ready",
            coarse_status=coarse_result.status,
            memory_preflight=coarse_diagnostics.get("memory_preflight"),
            coarse_diagnostics=coarse_diagnostics,
            factor_lifecycle=factor_lifecycle(),
            pc_apply_count=0,
            action_apply_count=coarse_action_apply_count(),
            local_action_apply_count=local_action_apply_count(),
            source=None,
            checkpoint=None,
        )
        base.update(
            {
                "resource_baseline": baseline,
                "coarse_diagnostics": coarse_diagnostics,
            }
        )
        if coarse_action is None:
            if c0:
                result = c0_resource_result({}, {}, coarse_result.status)
                return result
            _emit(
                event_callback,
                "classification",
                classification=_STAGE_BC_RESOURCE,
                factor_lifecycle=factor_lifecycle(),
                pc_apply_count=0,
                action_apply_count=coarse_action_apply_count(),
                local_action_apply_count=local_action_apply_count(),
                source=None,
                checkpoint=None,
            )
            result = {
                **base,
                "status": coarse_result.status,
                "classification": _STAGE_BC_RESOURCE,
                "executed_source_order": [],
                "initial_classification": None,
                "five_source_extension_status": "not_triggered",
                "no_source_or_outer_ksp": True,
                "allocated_object_count": coarse_diagnostics.get(
                    "allocated_object_count",
                    {"P": 0, "P_H": 0, "FP": 0, "Ac": 0, "KSP": 0},
                ),
            }
            return result

        if c0:
            one_resource, one_checks, one_resource_error = _v9_c0_resource_audit(
                _resource_callback, c0_hard_memory_bytes
            )
            one_errors = comm.allgather(one_resource_error)
            one_error = next((value for value in one_errors if value), None)
            emit_c0_event(
                "pre_one_apply_resource",
                resource=one_resource,
                resource_checks=one_checks,
                source=None,
                checkpoint=None,
            )
            if one_error is not None:
                result = c0_resource_result(one_resource, one_checks, one_error)
                return result

            source_audit: Mapping[str, Any] = {}
            c0_source = None
            try:
                c0_source, source_audit = source_builder("external_dtn_coupling")
                if not isinstance(c0_source, PETSc.Vec):
                    raise TypeError("C0 source builder must return a PETSc.Vec")
                source_norm = float(c0_source.norm())
                if not np.isfinite(source_norm) or source_norm <= 1.0e-300:
                    raise ValueError("C0 source norm must be finite and nonzero")
                direct_target = bare_f.createVecLeft()
                direct_residual = bare_f.createVecLeft()
                emit_c0_event(
                    "external_one_apply_begin",
                    source="external_dtn_coupling",
                    checkpoint=None,
                    source_norm=source_norm,
                )
                apply_started = perf_counter()
                coarse_action.apply(c0_source, direct_target)
                apply_wall = float(
                    comm.allreduce(perf_counter() - apply_started, op=MPI.MAX)
                )
                bare_f.mult(direct_target, direct_residual)
                direct_residual.axpy(PETSc.ScalarType(-1.0), c0_source)
                residual_norm = float(direct_residual.norm())
                target_norm = float(direct_target.norm())
                rho_coarse = residual_norm / max(source_norm, 1.0e-300)
                if not all(
                    np.isfinite(value)
                    for value in (residual_norm, target_norm, rho_coarse)
                ):
                    rho_coarse = float("nan")
                one_apply = {
                    "source": "external_dtn_coupling",
                    "source_audit": dict(source_audit),
                    "source_norm": source_norm,
                    "target_norm": target_norm,
                    "true_residual_absolute": residual_norm,
                    "true_residual_relative": rho_coarse,
                    "apply_wall_seconds": apply_wall,
                    "coarse_action_apply_count": coarse_action_apply_count(),
                    "local_action_apply_count": local_action_apply_count(),
                    "finite": bool(np.isfinite(rho_coarse)),
                }
                emit_c0_event(
                    "external_one_apply_end",
                    checkpoint="one_apply",
                    **one_apply,
                )
                initial = _classify_v9_c0_one_apply(rho_coarse)
                outer_record: dict[str, Any] | None = None
                if _stage_bc_safe_destroy(direct_target):
                    direct_target = None
                if _stage_bc_safe_destroy(direct_residual):
                    direct_residual = None
                final_signal = initial
                if initial["needs_outer_fgmres"]:
                    outer_solver = _StageBCRightFGMRES(
                        bare_f,
                        coarse_action,
                        max_it=8,
                        checkpoints=(8,),
                    )
                    outer_solver_created = True

                    def outer_checkpoint(row: Mapping[str, Any]) -> None:
                        emit_c0_event(
                            "outer_checkpoint",
                            source="external_dtn_coupling",
                            checkpoint=row.get("iteration"),
                            **dict(row),
                        )

                    outer_record = outer_solver.solve(
                        c0_source,
                        "external_dtn_coupling",
                        outer_checkpoint,
                    )
                    final_signal = _classify_v9_c0_outer_result(
                        initial, outer_record
                    )
                emit_c0_event(
                    "classification",
                    classification=final_signal["classification"],
                    next_required_stage=final_signal["next_required_stage"],
                    numerical_negative=final_signal["numerical_negative"],
                    rho_local=final_signal["rho_local"],
                    rho_coarse=final_signal["rho_coarse"],
                    improvement_factor=final_signal["improvement_factor"],
                    r8=final_signal.get("r8"),
                    zero_solution_relative_decline_decades=final_signal.get(
                        "zero_solution_relative_decline_decades"
                    ),
                )
                result = {
                    **base,
                    "status": "completed",
                    **final_signal,
                    "source_order": ["external_dtn_coupling"],
                    "executed_source_order": ["external_dtn_coupling"],
                    "classification_diagnostics": final_signal,
                    "one_apply": one_apply,
                    "outer_record": outer_record,
                    "factor_inventory": factor_inventory,
                    "harmonic_audit": harmonic_audit,
                    "source_audit": dict(source_audit),
                    "phase_diagnostics": c0_phase_diagnostics,
                }
            finally:
                if c0_source is not None:
                    c0_source.destroy()
                    source_destroyed_count += 1
            return result

        outer_solver = _StageBCRightFGMRES(bare_f, coarse_action)
        outer_solver_created = True
        records: dict[str, dict[str, Any]] = {}

        def solve_source(label: str) -> None:
            nonlocal source_destroyed_count
            source, audit = source_builder(label)
            try:
                _emit(
                    event_callback,
                    "solve_begin",
                    source=label,
                    checkpoint=None,
                    factor_lifecycle=factor_lifecycle(),
                    pc_apply_count=outer_solver.context.count,
                    action_apply_count=coarse_action_apply_count(),
                    local_action_apply_count=local_action_apply_count(),
                )
                record = outer_solver.solve(
                    source,
                    label,
                    lambda row: _emit(
                        event_callback,
                        "checkpoint",
                        source=label,
                        checkpoint=row["iteration"],
                        pc_apply_count=outer_solver.context.count,
                        action_apply_count=coarse_action_apply_count(),
                        local_action_apply_count=local_action_apply_count(),
                        factor_lifecycle=factor_lifecycle(),
                        **row,
                    ),
                )
                record["source_audit"] = dict(audit)
                records[label] = record
                _emit(
                    event_callback,
                    "solve_end",
                    source=label,
                    checkpoint=None,
                    factor_lifecycle=factor_lifecycle(),
                    pc_apply_count=outer_solver.context.count,
                    action_apply_count=coarse_action_apply_count(),
                    local_action_apply_count=local_action_apply_count(),
                    true_residual_relative=record["final_true_residual_relative"],
                    wall_seconds=record["wall_seconds"],
                )
            finally:
                source.destroy()
                source_destroyed_count += 1

        for label in _STAGE_BC_INITIAL_SOURCES:
            solve_source(label)
        initial = _classify_stage_bc_sources(records)
        initial_classification = initial["classification"]
        overall_classification = initial_classification
        executed = list(_STAGE_BC_INITIAL_SOURCES)
        extension = "not_triggered"
        if initial_classification == _STAGE_BC_POSITIVE:
            extension = "executed"
            for label in _STAGE_BC_HOLDOUT_SOURCES:
                solve_source(label)
                executed.append(label)
            if not all(
                _stage_bc_record_usable(records[label]) for label in executed
            ):
                overall_classification = _STAGE_BC_UNSTABLE
                extension = "failed_unstable"
        _emit(
            event_callback,
            "classification",
            classification=overall_classification,
            initial_classification=initial_classification,
            factor_lifecycle=factor_lifecycle(),
            pc_apply_count=outer_solver.context.count,
            action_apply_count=coarse_action_apply_count(),
            local_action_apply_count=local_action_apply_count(),
            source=None,
            checkpoint=None,
        )
        result = {
            **base,
            "status": "completed",
            "classification": overall_classification,
            "initial_classification": initial_classification,
            "executed_source_order": executed,
            "five_source_extension_status": extension,
            "source_records": records,
            "classification_diagnostics": initial,
            "no_generalized_eigen_or_dense_factor": True,
        }
        live_coarse_diagnostics = dict(coarse_action.diagnostics)
        live_coarse_diagnostics["coarse_setup_wall_seconds"] = coarse_wall
        result["coarse_diagnostics"] = live_coarse_diagnostics
    finally:
        pc_apply_count = (
            outer_solver.context.count if outer_solver is not None else 0
        )
        coarse_apply_count = coarse_action_apply_count()
        local_apply_count = local_action_apply_count()
        outer_solver_destroyed = _stage_bc_safe_destroy(outer_solver)
        coarse_action_destroyed = _stage_bc_safe_destroy(coarse_action)
        if harmonic_space is not None:
            harmonic_released = _stage_bc_safe_destroy(harmonic_space)
        local_action_destroyed = _stage_bc_safe_destroy(local_action)
        if local_action is not None:
            local_factor_lifecycle = factor_lifecycle()
        preparation_destroyed = preparation_destroyed or _stage_bc_safe_destroy(
            preparation
        )
        prepared_rhs_released = prepared_rhs_released or preparation_destroyed
        provider_destroyed = provider_destroyed or _stage_bc_safe_destroy(provider)
        if direct_target is not None and _stage_bc_safe_destroy(direct_target):
            direct_target = None
        if direct_residual is not None and _stage_bc_safe_destroy(direct_residual):
            direct_residual = None
        bare_after = _petsc_matrix_hash(bare_f)
        cleanup_complete = bool(
            (not provider_created or provider_destroyed)
            and (not preparation_created or preparation_destroyed)
            and (not local_action_created or local_action_destroyed)
            and (not harmonic_space_created or harmonic_released)
            and (not coarse_action_created or coarse_action_destroyed)
            and (not outer_solver_created or outer_solver_destroyed)
            and (not c0 or (direct_target is None and direct_residual is None))
            and bare_before == bare_after
        )
        cleanup = {
            "status": "complete" if cleanup_complete else "incomplete",
            "provider_created": provider_created,
            "preparation_created": preparation_created,
            "local_action_created": local_action_created,
            "harmonic_space_created": harmonic_space_created,
            "coarse_action_created": coarse_action_created,
            "outer_solver_created": outer_solver_created,
            "outer_solver_destroyed": outer_solver_destroyed,
            "coarse_action_destroyed": coarse_action_destroyed,
            "harmonic_space_destroyed": harmonic_released,
            "harmonic_columns_consumed": harmonic_consumed,
            "harmonic_columns_released": harmonic_released,
            "local_action_destroyed": local_action_destroyed,
            "local_factor_lifecycle_after_cleanup": local_factor_lifecycle,
            "provider_destroyed": provider_destroyed,
            "preparation_destroyed": preparation_destroyed,
            "preparation_consumed": preparation_consumed,
            "prepared_rhs_released": prepared_rhs_released,
            "source_vectors_destroyed": source_destroyed_count,
            "pc_apply_count": pc_apply_count,
            "action_apply_count": coarse_apply_count,
            "local_action_apply_count": local_apply_count,
            "bare_f_hash_before": bare_before,
            "bare_f_hash_after": bare_after,
            "bare_f_unchanged": bare_before == bare_after,
        }
        if c0:
            cleanup.update(
                {
                    "direct_work_released": (
                        direct_target is None and direct_residual is None
                    ),
                }
            )
        try:
            _emit(event_callback, "cleanup", **cleanup)
        except Exception:
            if result is not None:
                raise
        if result is not None:
            result["cleanup"] = cleanup
            if cleanup_complete is not True:
                result["status"] = "implementation_failure"
                result["classification"] = _STAGE_BC_IMPLEMENTATION_FAILURE
            if cleanup["bare_f_unchanged"] is not True:
                raise RuntimeError("Stage-B/C borrowed bare-F changed")
            if cleanup_complete is not True:
                raise RuntimeError("Stage-B/C cleanup incomplete")
    if result is None:
        raise RuntimeError("Stage-B/C screen produced no result")
    if result["cleanup"]["bare_f_unchanged"] is not True:
        raise RuntimeError("Stage-B/C borrowed bare-F changed")
    return result
