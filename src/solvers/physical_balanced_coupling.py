"""Minimal BAL_H coarse/fine coupling over caller-supplied actions.

The class in this module only composes already-built actions.  It does not
assemble a finite-element operator, create a factor, or know about a
reference field.  A callback returns a new vector owned by this apply, while
the input and the action objects remain borrowed.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import numpy as np


BALANCED_ROUTE = "BAL_H"
BALANCE_LIMIT = 1.0e-8

__all__ = (
    "BALANCED_ROUTE",
    "BALANCE_LIMIT",
    "BalancedConstraintRejected",
    "PhysicalBalancedCoupling",
)


class BalancedConstraintRejected(RuntimeError):
    """The coarse residual was not balanced in the supplied dual space."""

    def __init__(self, facts: dict[str, Any]) -> None:
        self.facts = facts
        super().__init__(f"{type(self).__name__}: {facts}")


def _copy(value: Any) -> Any:
    duplicate = getattr(value, "duplicate", None)
    if callable(duplicate):
        result = duplicate()
        copy_method = getattr(value, "copy", None)
        if not callable(copy_method):
            raise TypeError("owned vector requires a copy operation")
        copy_method(result)
        return result
    return np.array(value, copy=True)


def _destroy(value: Any) -> None:
    destroy = getattr(value, "destroy", None)
    if callable(destroy):
        destroy()


def _norm(value: Any) -> float:
    norm_method = getattr(value, "norm", None)
    result = float(norm_method()) if callable(norm_method) else float(np.linalg.norm(value))
    if not np.isfinite(result):
        raise RuntimeError("BAL_H vector is non-finite")
    return result


def _axpy(target: Any, alpha: complex, source: Any) -> None:
    axpy = getattr(target, "axpy", None)
    if callable(axpy):
        axpy(alpha, source)
    else:
        np.asarray(target)[:] += alpha * np.asarray(source)


class _OwnedVectors:
    """Track vectors created during one apply and release them on exit."""

    def __init__(self) -> None:
        self._values: dict[int, Any] = {}
        self.peak = 0

    def take(self, value: Any) -> Any:
        if value is None or id(value) in self._values:
            raise TypeError("BAL_H callback must return a fresh owned vector")
        self._values[id(value)] = value
        self.peak = max(self.peak, len(self._values))
        _norm(value)
        return value

    def copy(self, value: Any) -> Any:
        return self.take(_copy(value))

    def drop(self, value: Any) -> None:
        owned = self._values.pop(id(value))
        _destroy(owned)

    def release(self, value: Any) -> Any:
        return self._values.pop(id(value))

    def close(self) -> None:
        for value in list(self._values.values()):
            self.drop(value)


class PhysicalBalancedCoupling:
    """Apply the fixed V5 BAL_H action.

    For a source ``r``, ``coarse`` is ``Q``, ``action`` is ``A6``, ``smoother``
    is ``H6`` and ``restriction`` is the dual ``P^H`` operation.  The exact
    order is::

        zc = Q(r)
        rc = r - A6(zc)
        s = H6(rc)
        z = zc + s - Q(A6(s))

    The callbacks must return fresh caller-owned vectors.  The returned ``z``
    remains owned by the caller; all other vectors created by ``apply`` are
    released before it returns or raises.
    """

    route = BALANCED_ROUTE

    def __init__(
        self,
        action: Callable[[Any], Any],
        coarse: Callable[[Any], Any],
        smoother: Callable[[Any], Any],
        restriction: Callable[[Any], Any],
        *,
        checkpoint: Callable[[], None] | None = None,
    ) -> None:
        self.A = action
        self.Q = coarse
        self.H6 = smoother
        self.PH = restriction
        self.checkpoint = checkpoint or (lambda: None)
        self.apply_count = 0
        self.attempted = 0
        self.last_apply_facts: dict[str, Any] = {}

    def apply(self, source: Any) -> Any:
        vectors = _OwnedVectors()
        self.attempted += 1
        counts = {"Q": 0, "H6": 0, "A6": 0, "PH_audit": 0}
        operation_seconds = {name: 0.0 for name in ("Q", "H6", "A6")}
        facts: dict[str, Any] = {
            "route": self.route,
            "status": "STARTED",
            "counts": counts,
            "operation_seconds": operation_seconds,
            "balance_limit": BALANCE_LIMIT,
        }
        self.last_apply_facts = facts

        def call(name: str, function: Callable[[Any], Any], value: Any) -> Any:
            self.checkpoint()
            counts[name] += 1
            started = time.perf_counter()
            result: Any = None
            try:
                result = function(value)
            finally:
                operation_seconds[name] += time.perf_counter() - started
            if result is None or result is value or result is source:
                raise TypeError(
                    f"BAL_H {name} callback must return a fresh owned vector"
                )
            return vectors.take(result)

        def balance(residual: Any, leading: Any) -> dict[str, float]:
            counts["PH_audit"] += 2
            leading_dual = self.PH(leading)
            try:
                residual_dual = self.PH(residual)
                try:
                    numerator = _norm(residual_dual)
                    operation_scale = _norm(leading_dual)
                    _axpy(leading_dual, -1.0, residual_dual)
                    operation_scale += _norm(leading_dual)
                    relative = numerator / max(
                        operation_scale, np.finfo(float).tiny
                    )
                    audit = {
                        "norm": numerator,
                        "operation_scale": operation_scale,
                        "relative": relative,
                        "limit": BALANCE_LIMIT,
                    }
                    if not np.isfinite(relative) or relative > BALANCE_LIMIT:
                        raise BalancedConstraintRejected(audit)
                    return audit
                finally:
                    _destroy(residual_dual)
            finally:
                _destroy(leading_dual)

        try:
            _norm(source)
            zc = call("Q", self.Q, source)
            azc = call("A6", self.A, zc)
            rc = vectors.copy(source)
            _axpy(rc, -1.0, azc)
            facts["initial"] = {
                "source_norm": _norm(source),
                "zc_norm": _norm(zc),
                "Azc_norm": _norm(azc),
                "rc_norm": _norm(rc),
                "balance": balance(rc, source),
            }
            vectors.drop(azc)

            s = call("H6", self.H6, rc)
            As = call("A6", self.A, s)
            t = call("Q", self.Q, As)
            feedback = vectors.copy(rc)
            _axpy(feedback, -1.0, As)
            before_residual_norm = _norm(feedback)
            vectors.drop(feedback)
            z = vectors.copy(zc)
            _axpy(z, 1.0, s)
            before_feedback_norm = _norm(z)
            _axpy(z, -1.0, t)
            facts["feedback"] = {
                "s_norm": _norm(s),
                "As_norm": _norm(As),
                "QAs_norm": _norm(t),
                "before_residual_norm": before_residual_norm,
                "before_field_norm": before_feedback_norm,
                "after_field_norm": _norm(z),
            }
            vectors.drop(As)
            vectors.drop(t)
            facts["status"] = "BALANCED_ACTION_COMPLETED"
            self.apply_count += 1
            facts["apply_count"] = self.apply_count
            return vectors.release(z)
        except BaseException as exc:
            facts.update(
                status="ACTION_FAILED",
                exception_type=type(exc).__name__,
                exception=str(exc),
            )
            raise
        finally:
            facts["peak_new_vectors"] = vectors.peak
            facts["live_before_cleanup"] = len(vectors._values)
            vectors.close()
            facts["live_after_cleanup"] = len(vectors._values)
