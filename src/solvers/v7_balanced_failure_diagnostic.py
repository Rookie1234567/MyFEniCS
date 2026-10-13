"""Opt-in, bounded evidence capture for the V7 BAL_H balance rejection.

This module records the first failed BAL_H balance and computes the reviewed
operator decomposition from already-live vectors/actions. It never changes a
solver decision or numerical threshold. No production caller enables it by
default.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

MAX_CAPTURE_BYTES = 700_000_000
CAPTURE_CHUNK_ELEMENTS = 1 << 18
NUMERICAL_BASELINE_SOURCE_SHA = "00789bd1ae41fc7bddbe47d049624eb520de888b"


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return {"array_omitted": True, "shape": list(value.shape), "dtype": str(value.dtype)}
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, float) and not np.isfinite(value):
        return {"nonfinite": repr(value)}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return repr(value)


def _atomic_json(path: Path, record: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    encoded = json.dumps(_jsonable(record), sort_keys=True, separators=(",", ":")).encode()
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=True) as stream:
            stream.write(encoded)
            stream.write(b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def _write_vector_npy(path: Path, vector: Any, expected_rows: int) -> dict[str, Any]:
    """Write a PETSc-like vector without making a full-sized host copy."""

    array = np.asarray(vector.getArray(readonly=True))
    if array.ndim != 1 or array.dtype != np.dtype(np.complex128) or not array.flags.c_contiguous:
        raise TypeError("diagnostic vectors must expose contiguous one-dimensional complex128 data")
    global_rows = int(vector.getSize())
    local_rows = int(vector.getLocalSize())
    if global_rows != expected_rows or local_rows != expected_rows or array.size != expected_rows:
        raise ValueError("diagnostic capture requires the expected MPI1 full-vector row count")
    expected_bytes = int(array.nbytes)
    if expected_bytes > MAX_CAPTURE_BYTES:
        raise ValueError("diagnostic vector exceeds the fixed per-array capture limit")

    header_buffer = io.BytesIO()
    np.lib.format.write_array_header_2_0(
        header_buffer,
        {"descr": np.lib.format.dtype_to_descr(array.dtype),
         "fortran_order": False, "shape": array.shape},
    )
    header = header_buffer.getvalue()
    raw_hash = hashlib.sha256()
    file_hash = hashlib.sha256()
    file_hash.update(header)
    partial = path.with_name(path.name + ".partial")
    finite = True
    finite_elements = 0
    fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb", closefd=True) as stream:
            stream.write(header)
            for start in range(0, array.size, CAPTURE_CHUNK_ELEMENTS):
                block = array[start:start + CAPTURE_CHUNK_ELEMENTS]
                if not bool(np.isfinite(block).all()):
                    finite = False
                finite_elements += int(block.size)
                raw = memoryview(block).cast("B")
                raw_hash.update(raw)
                file_hash.update(raw)
                stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if path.exists():
            raise FileExistsError(path)
        os.replace(partial, path)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except BaseException:
        try:
            partial.unlink()
        except FileNotFoundError:
            pass
        raise
    return {
        "filename": path.name,
        "rows": expected_rows,
        "dtype": "complex128",
        "payload_bytes": expected_bytes,
        "file_bytes": len(header) + expected_bytes,
        "finite": finite and finite_elements == expected_rows,
        "raw_payload_sha256": raw_hash.hexdigest(),
        "file_sha256": file_hash.hexdigest(),
        "written_in_bounded_chunks": True,
    }


def _copy_vector(value: Any) -> Any:
    output = value.duplicate()
    value.copy(output)
    return output


def _norm(value: Any) -> float:
    result = float(value.norm())
    if not np.isfinite(result):
        raise FloatingPointError("diagnostic vector norm is nonfinite")
    return result


def _vector_facts(value: Any) -> dict[str, Any]:
    array = np.asarray(value.getArray(readonly=True))
    finite = True
    for start in range(0, array.size, CAPTURE_CHUNK_ELEMENTS):
        if not bool(np.isfinite(array[start:start + CAPTURE_CHUNK_ELEMENTS]).all()):
            finite = False
            break
    return {
        "global_rows": int(value.getSize()),
        "local_rows": int(value.getLocalSize()),
        "dtype": str(array.dtype),
        "finite": finite,
        "norm": _norm(value),
    }


class _OwnedScratch:
    """Destroy only diagnostic-owned vectors and track their peak payload."""

    def __init__(self) -> None:
        self._vectors: dict[int, Any] = {}
        self._bytes = 0
        self.peak_bytes = 0

    def own(self, vector: Any) -> Any:
        if vector is None or id(vector) in self._vectors:
            raise TypeError("diagnostic scratch received a null or already-owned vector")
        self._vectors[id(vector)] = vector
        self._bytes += int(vector.getLocalSize()) * np.dtype(
            np.asarray(vector.getArray(readonly=True)).dtype
        ).itemsize
        self.peak_bytes = max(self.peak_bytes, self._bytes)
        return vector

    def drop(self, vector: Any) -> None:
        owned = self._vectors.pop(id(vector))
        self._bytes -= int(owned.getLocalSize()) * np.dtype(
            np.asarray(owned.getArray(readonly=True)).dtype
        ).itemsize
        owned.destroy()

    def close(self) -> None:
        for vector in list(self._vectors.values()):
            self.drop(vector)


def _ordered_sum(vectors: list[Any], owner: _OwnedScratch) -> Any:
    if not vectors:
        raise ValueError("cannot sum an empty diagnostic term list")
    result = owner.own(_copy_vector(vectors[0]))
    for vector in vectors[1:]:
        result.axpy(1.0, vector)
    return result


def _apply_bundle(bundle: Mapping[str, Any], vector: Any, owner: _OwnedScratch) -> Any:
    from src.solvers.fullspace_physical_intermediate import apply_owned

    return owner.own(apply_owned(bundle["physical_action"], vector))


def with_shared_dtn_owner(
    fast_bundle: Mapping[str, Any] | None, native_bundle: Mapping[str, Any]
) -> dict[str, Any]:
    """Expose packed fast actions with the corresponding shared native DtN owner.

    Current packed bundles provide ``physical_action`` and ``volume_action``;
    the DtN action is shared from the same degree's native bundle.
    """

    selected = dict(fast_bundle if fast_bundle is not None else native_bundle)
    for key in ("physical_action", "volume_action"):
        if key not in selected:
            raise KeyError(f"balanced diagnostic action bundle lacks {key!r}")
    if "dtn_action" not in native_bundle or native_bundle["dtn_action"] is None:
        raise KeyError("native diagnostic owner lacks a usable 'dtn_action'")
    selected["dtn_action"] = native_bundle["dtn_action"]
    return selected


def _component_facts(
    label: str, bundle: Mapping[str, Any], source: Any, full_result: Any, owner: _OwnedScratch
) -> dict[str, Any]:
    from src.solvers.fullspace_physical_intermediate import (
        BorrowedActionAdapter,
        apply_owned,
    )

    volume = owner.own(apply_owned(BorrowedActionAdapter(bundle["volume_action"]), source))
    dtn = owner.own(apply_owned(bundle["dtn_action"], source))
    composed = owner.own(_copy_vector(dtn))
    composed.axpy(1.0, volume)
    mismatch = owner.own(_copy_vector(composed))
    mismatch.axpy(-1.0, full_result)
    full_norm = _norm(full_result)
    facts = {
        "operator": label,
        "volume_norm": _norm(volume),
        "dtn_norm": _norm(dtn),
        "dtn_then_volume_sum_norm": _norm(composed),
        "reference_full_action_norm": full_norm,
        "component_sum_minus_reference_norm": _norm(mismatch),
        "component_sum_minus_reference_relative": _norm(mismatch) / max(
            full_norm, np.finfo(float).tiny
        ),
        "finite": all(_vector_facts(item)["finite"] for item in (volume, dtn, composed, mismatch)),
        "sum_order": "A_DtN_target_then_A_volume_axpy_matches_FullspacePhysicalAction",
    }
    for vector in (mismatch, composed, dtn, volume):
        owner.drop(vector)
    return facts


def _compute_decomposition(
    *, g: Any, c: Any, pc: Any, fast_u: Any, g_minus_u: Any,
    ph_g: Any, actual_ph_residual: Any,
    restrict: Any, a4_fast: Mapping[str, Any], a4_native: Mapping[str, Any],
    a6_fast: Mapping[str, Any], a6_native: Mapping[str, Any],
) -> dict[str, Any]:
    """Evaluate reviewed terms, without replacing the original BAL_H gate."""

    owner = _OwnedScratch()
    try:
        a4f_c = _apply_bundle(a4_fast, c, owner)
        a4n_c = _apply_bundle(a4_native, c, owner)
        a6n_pc = _apply_bundle(a6_native, pc, owner)
        ph_a6n = owner.own(restrict(a6n_pc))
        ph_u = owner.own(restrict(fast_u))

        r4 = owner.own(_copy_vector(ph_g))
        r4.axpy(-1.0, a4f_c)
        delta4 = owner.own(_copy_vector(a4f_c))
        delta4.axpy(-1.0, a4n_c)
        cross = owner.own(_copy_vector(a4n_c))
        cross.axpy(-1.0, ph_a6n)
        a6_difference = owner.own(_copy_vector(a6n_pc))
        a6_difference.axpy(-1.0, fast_u)
        delta6 = owner.own(restrict(a6_difference))

        terms = [r4, delta4, cross, delta6]
        formula_sum = _ordered_sum(terms, owner)
        formula_minus_actual = owner.own(_copy_vector(formula_sum))
        formula_minus_actual.axpy(-1.0, actual_ph_residual)

        ph_g_minus_phu = owner.own(_copy_vector(ph_g))
        ph_g_minus_phu.axpy(-1.0, ph_u)
        restriction_distributivity = owner.own(_copy_vector(actual_ph_residual))
        restriction_distributivity.axpy(-1.0, ph_g_minus_phu)
        delta6_distributivity = owner.own(_copy_vector(delta6))
        delta6_distributivity.axpy(-1.0, ph_a6n)
        delta6_distributivity.axpy(1.0, ph_u)

        term_norms = {
            "r4_PH_g_minus_A4_fast_c": _norm(r4),
            "delta4_A4_fast_minus_A4_native_c": _norm(delta4),
            "cross_A4_native_c_minus_PH_A6_native_Pc": _norm(cross),
            "delta6_PH_A6_native_minus_fast_Pc": _norm(delta6),
        }
        projected_p4_rows = int(ph_g.getSize())
        facts = {
            "status": "COMPUTED",
            "formula": "PHg-A4fast*c +(A4fast-A4native)c +(A4native*c-PH(A6native*Pc)) +PH(A6native*Pc-A6fast*Pc)",
            "gate_expression_preserved": "PH(g-A6fast*Pc)",
            "gate_expression_replaced": False,
            "vector_norms": {
                "g_source_p6": _norm(g), "c_coarse_p4": _norm(c),
                "Pc_prolonged_p6": _norm(pc), "u_actual_A6fastPc_p6": _norm(fast_u),
                "g_minus_u_p6": _norm(g_minus_u),
                "PH_g": _norm(ph_g), "PH_g_minus_u_actual": _norm(actual_ph_residual),
            },
            "projected_p4_rows": projected_p4_rows,
            "term_norms": term_norms,
            "formula_minus_actual_norm": _norm(formula_minus_actual),
            "formula_minus_actual_finite": _vector_facts(formula_minus_actual)["finite"],
            "restriction_distributivity_PH_g_minus_u_vs_PHg_minus_PHu_norm": _norm(
                restriction_distributivity
            ),
            "delta6_projection_distributivity_norm": _norm(delta6_distributivity),
            "A4_fast_components": _component_facts("A4_fast", a4_fast, c, a4f_c, owner),
            "A4_native_components": _component_facts("A4_native", a4_native, c, a4n_c, owner),
            "A6_native_components": _component_facts("A6_native", a6_native, pc, a6n_pc, owner),
            "A6_fast_components": _component_facts("A6_fast", a6_fast, pc, fast_u, owner),
            "diagnostic_scratch_peak_local_vector_bytes": owner.peak_bytes,
            "diagnostic_scratch_peak_includes_capture_inputs": False,
        }
        facts["all_reported_values_finite"] = _all_finite_scalars(facts)
        return facts
    finally:
        owner.close()


def _all_finite_scalars(value: Any) -> bool:
    if isinstance(value, Mapping):
        return all(_all_finite_scalars(item) for item in value.values())
    if isinstance(value, (tuple, list)):
        return all(_all_finite_scalars(item) for item in value)
    if isinstance(value, (float, np.floating)):
        return bool(np.isfinite(value))
    if isinstance(value, (int, np.integer, str, bool)) or value is None:
        return True
    return True


class V7BalancedFailureDiagnostic:
    """Bounded first-rejection capture; explicit caller activation is required."""

    def __init__(
        self,
        directory: str | Path,
        *,
        identity: Mapping[str, Any],
        p4_rows: int,
        p6_rows: int,
        diagnostic_implementation_source_sha: str | None = None,
    ) -> None:
        self.directory = Path(directory)
        self.identity = dict(identity)
        self.p4_rows = int(p4_rows)
        self.p6_rows = int(p6_rows)
        if self.p4_rows <= 0 or self.p6_rows <= 0:
            raise ValueError("diagnostic row counts must be positive")
        capture_bytes = 16 * (self.p4_rows + self.p6_rows)
        if capture_bytes > MAX_CAPTURE_BYTES:
            raise ValueError("bounded c/g diagnostic capture exceeds fixed payload limit")
        self.active = False
        self.rejection_seen = False
        self.pending_coarse = None
        self.activation_context: dict[str, Any] | None = None
        self.apply_context: dict[str, Any] | None = None
        self.balance_pass_count = 0
        self.restriction = None
        self.a4_fast = self.a4_native = self.a6_fast = self.a6_native = None
        self.facts: dict[str, Any] = {
            "schema": "task039extra.v7-balanced-failure-diagnostic.v1",
            "status": "PREPARED_NOT_ACTIVE",
            "numerical_baseline_source_sha": NUMERICAL_BASELINE_SOURCE_SHA,
            "diagnostic_implementation_source_sha": diagnostic_implementation_source_sha,
            "diagnostic_observes_first_balance_rejection_only": True,
            "diagnostic_does_not_change_outer_pc_attempt_limit": True,
            "observer_report_is_solver_qualification": False,
            "full_v7_solve_continues_if_balance_gate_passes": True,
            "numerical_gate_or_arithmetic_changed": False,
            "root_cause_proven": False,
            "captured_fields": ["failed_full_p4_coarse_c", "failed_full_p6_source_g"],
            "capture_payload_bytes_bound": capture_bytes,
            "extra_full_field_copies": 0,
            "identity": self.identity,
        }

    def configure(
        self, *, restriction: Any,
        a4_fast: Mapping[str, Any], a4_native: Mapping[str, Any],
        a6_fast: Mapping[str, Any], a6_native: Mapping[str, Any],
    ) -> None:
        if self.active or self.restriction is not None:
            raise RuntimeError("diagnostic runtime actions may be configured once before activation")
        self.restriction = restriction
        self.a4_fast, self.a4_native = a4_fast, a4_native
        self.a6_fast, self.a6_native = a6_fast, a6_native

    def activate(self, *, context: Mapping[str, Any] | None = None) -> None:
        if self.restriction is None:
            raise RuntimeError("diagnostic actions must be configured before activation")
        if self.active:
            raise RuntimeError("diagnostic can only be activated once")
        self.active = True
        self.facts["status"] = "ARMED_FIRST_BALANCE_REJECTION_OBSERVER"
        self.facts["activated_monotonic_ns"] = time.monotonic_ns()
        self.activation_context = dict(context or {})
        self.facts["activation_context"] = _jsonable(self.activation_context)

    def set_apply_context(self, context: Mapping[str, Any]) -> None:
        """Bind the next observer callback to its actual outer PC call."""

        if not self.active:
            raise RuntimeError("outer apply context cannot be set before observer activation")
        self.apply_context = dict(context)

    @property
    def capture_active(self) -> bool:
        return self.active and not self.rejection_seen

    def hold_coarse(self, vector: Any) -> bool:
        if not self.capture_active:
            return False
        if self.pending_coarse is not None:
            raise RuntimeError("diagnostic coarse vector lifecycle overlaps outer PC attempts")
        self.pending_coarse = vector
        return True

    def release_pending_coarse(self) -> None:
        vector, self.pending_coarse = self.pending_coarse, None
        if vector is not None:
            vector.destroy()

    def on_balance_pass(self, facts: Mapping[str, Any]) -> None:
        if self.capture_active:
            self.balance_pass_count += 1
            self.facts["balance_pass_count"] = self.balance_pass_count
            self.facts["last_balance_pass"] = {
                "facts": _jsonable(facts),
                "apply_context": _jsonable(self.apply_context),
            }
        self.release_pending_coarse()

    def record_unexpected_error(self, error: BaseException) -> None:
        """Retain observer/cleanup failures without replacing the solver gate."""
        self.facts.setdefault("diagnostic_secondary_errors", []).append({
            "type": type(error).__name__,
            "message": str(error),
            "does_not_replace_original_balance_rejection": True,
        })

    def on_balance_rejection(
        self, *, source: Any, actual_other: Any, residual: Any,
        primal: Any, ph_residual: Any, facts: Mapping[str, Any],
        coupling_apply_attempt: int | None = None,
        balance_gate_point: str = "BAL_H_initial_balance_before_smoother",
    ) -> None:
        """Capture/decompose without allowing diagnostics to replace gate error."""
        if not self.capture_active:
            return
        self.rejection_seen = True
        self.facts.update(
            status="BAL_H_FIRST_BALANCE_REJECTION_CAPTURED",
            failed_gate_facts=_jsonable(facts),
            failed_inputs_are_live_vectors=True,
            coarse_vector_is_captured_before_release=True,
            root_cause_proven=False,
            actual_failed_apply_context={
                "activation": _jsonable(self.activation_context),
                "outer_apply": _jsonable(self.apply_context),
                "coupling_apply_attempt": (
                    None if coupling_apply_attempt is None else int(coupling_apply_attempt)
                ),
                "balance_gate_point": str(balance_gate_point),
                "setup_qa_calls_are_excluded_from_outer_apply_ordinal": True,
            },
        )
        try:
            if self.pending_coarse is None:
                raise RuntimeError("failed BAL_H call has no retained p4 coarse vector")
            if primal is None:
                raise ValueError("failed BAL_H observer did not receive the live primal Pc")
            if int(primal.getSize()) != self.p6_rows or int(primal.getLocalSize()) != self.p6_rows:
                raise ValueError("live primal does not match expected p6 rows")
            capture_dir = self.directory / "v7_balanced_failure_diagnostic"
            capture_dir.mkdir(parents=True, exist_ok=False)
            capture_bytes = self.p4_rows * 16 + self.p6_rows * 16
            captures = {
                "c": _write_vector_npy(capture_dir / "failed_full_p4_coarse_c.npy",
                                       self.pending_coarse, self.p4_rows),
                "g": _write_vector_npy(capture_dir / "failed_full_p6_source_g.npy",
                                       source, self.p6_rows),
            }
            self.facts["captures"] = captures
            self.facts["capture_payload_bytes_actual"] = capture_bytes
            self.facts["live_vector_norms"] = {
                "g": _vector_facts(source), "c": _vector_facts(self.pending_coarse),
                "Pc": _vector_facts(primal), "u": _vector_facts(actual_other),
                "g_minus_u": _vector_facts(residual),
            }

            # The balance gate has already evaluated its original expressions.
            # Its PH(leading) work vector was mutated in-place for the scale
            # calculation; independently evaluate PH(g) here, from the same
            # live g. Use the exact live Pc from C(c), never another P(c).
            ph_g = self.restriction(source)
            try:
                if int(ph_g.getSize()) != self.p4_rows or int(ph_g.getLocalSize()) != self.p4_rows:
                    raise ValueError("independent PH(g) does not match expected p4 rows")
                self.facts["decomposition"] = _compute_decomposition(
                    g=source, c=self.pending_coarse, pc=primal, fast_u=actual_other,
                    g_minus_u=residual, ph_g=ph_g, actual_ph_residual=ph_residual,
                    restrict=self.restriction,
                    a4_fast=self.a4_fast, a4_native=self.a4_native,
                    a6_fast=self.a6_fast, a6_native=self.a6_native,
                )
            finally:
                ph_g.destroy()
            self.facts["capture_directory"] = str(capture_dir)
        except Exception as diagnostic_error:  # noqa: BLE001 - diagnostic failures must not replace BAL_H rejection.
            self.facts["diagnostic_error"] = {
                "type": type(diagnostic_error).__name__,
                "message": str(diagnostic_error),
                "does_not_replace_original_balance_rejection": True,
            }
        finally:
            self.release_pending_coarse()
            self.facts["first_rejection_only"] = True
            self.persist()

    def finish_without_rejection(self, *, reason: str) -> dict[str, Any]:
        if self.rejection_seen:
            return self.snapshot()
        if not self.active:
            self.facts.update(
                status="OBSERVER_NOT_ACTIVATED_BEFORE_OUTER_SOLVE",
                stop_reason=str(reason),
                observer_report_is_solver_qualification=False,
            )
        else:
            self.facts.update(
                status="DIAGNOSTIC_NOT_REPRODUCED",
                stop_reason=str(reason),
                observer_report_is_solver_qualification=False,
                full_v7_solve_was_not_stopped_by_observer=True,
                balance_pass_count=self.balance_pass_count,
            )
        self.release_pending_coarse()
        self.persist()
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return _jsonable(self.facts)

    def persist(self) -> None:
        _atomic_json(self.directory / "v7_balanced_failure_diagnostic.json", self.facts)

    def close(self) -> None:
        self.release_pending_coarse()
        self.active = False

