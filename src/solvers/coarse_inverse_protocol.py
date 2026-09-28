"""Independent strict-return contract; no factor, solver or FE construction.

An iterative backend must supply a complete cumulative FE/port state. Independent
witnesses recompute the original equation, port closure and interior recovery.
This module deliberately does not implement or impersonate P4RefinementLedger.
Factor declarations are admission checks, not evidence of a deployed backend's
actual allocations. F1/F4 must bind them to construction/lifecycle telemetry.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np

TOLERANCE = 1.0e-10
RESTART = 32
MAX_ITERATIONS = 256
FACTOR_BYTES_LIMIT = 512 * 2**20
REPRESENTATION_BYTES_LIMIT = 512 * 2**20


def _vector(value: np.ndarray, name: str) -> np.ndarray:
    value = np.asarray(value)
    if value.ndim != 1 or value.dtype != np.complex128:
        raise ValueError(f"{name} must be a complex128 vector")
    if not np.isfinite(value).all():
        raise ValueError(f"{name} is nonfinite")
    owned = value.copy()
    owned.flags.writeable = False
    return owned


def _norm(value: np.ndarray) -> float:
    # Preserve relative tests for tiny phase/amplitude-scaled RHS.
    largest = float(np.max(np.abs(value), initial=0.0))
    result = largest * float(np.linalg.norm(value / largest)) if largest else 0.0
    if not np.isfinite(result):
        raise ValueError("nonfinite vector norm")
    return result


@dataclass(frozen=True)
class CoarseRHS:
    fe: np.ndarray
    port: np.ndarray

    def __post_init__(self):
        object.__setattr__(self, "fe", _vector(self.fe, "FE RHS"))
        object.__setattr__(self, "port", _vector(self.port, "port RHS"))


@dataclass(frozen=True)
class CoarseState:
    fe: np.ndarray
    port: np.ndarray

    def __post_init__(self):
        object.__setattr__(self, "fe", _vector(self.fe, "FE state"))
        object.__setattr__(self, "port", _vector(self.port, "cumulative port state"))


@dataclass(frozen=True)
class FactorDeclaration:
    scope: str
    rows: int
    payload_bytes: int

    def __post_init__(self):
        if self.scope not in ("cell", "patch", "bottom"):
            raise ValueError(
                "global p4 factors and undeclared factor scopes are forbidden"
            )
        cap = 2048 if self.scope == "bottom" else 6000
        if type(self.rows) is not int or not 0 < self.rows <= cap:
            raise ValueError("factor row limit exceeded")
        if type(self.payload_bytes) is not int or self.payload_bytes < 0:
            raise ValueError("invalid factor bytes")


@dataclass(frozen=True)
class InversePlan:
    operator_sha256: str
    factors: tuple[FactorDeclaration, ...] = ()
    representation_bytes: int = 0

    def __post_init__(self):
        if len(self.operator_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in self.operator_sha256
        ):
            raise ValueError("complete operator SHA256 is required")
        if not isinstance(self.factors, tuple) or any(
            not isinstance(f, FactorDeclaration) for f in self.factors
        ):
            raise TypeError("factor declarations must be a frozen tuple")
        if sum(f.payload_bytes for f in self.factors) > FACTOR_BYTES_LIMIT:
            raise ValueError("total factor payload exceeds 512 MiB")
        if (
            type(self.representation_bytes) is not int
            or not 0 <= self.representation_bytes <= REPRESENTATION_BYTES_LIMIT
        ):
            raise ValueError("basis/mapping/online buffers exceed 512 MiB")


@dataclass(frozen=True)
class IterationReport:
    iterations: int
    restart: int = RESTART
    pc_side: str = "right"
    zero_start: bool = True


class IterativeBackend(Protocol):
    plan: InversePlan

    def solve(self, rhs: CoarseRHS) -> tuple[CoarseState, IterationReport]: ...


@dataclass(frozen=True)
class ResidualWitness:
    residual: np.ndarray
    scale: float

    def relative(self) -> float:
        numerator = _norm(_vector(self.residual, "witness residual"))
        scale = float(self.scale)
        if not np.isfinite(scale) or scale < 0.0:
            raise ValueError("witness scale must be finite and nonnegative")
        return (
            numerator / scale if scale else (0.0 if numerator == 0.0 else float("inf"))
        )


class CoarseReturnRejected(RuntimeError):
    def __init__(self, audit):
        self.audit = audit
        super().__init__(f"strict coarse return rejected: {audit.get('reason')}")


class StrictCoarseReturn:
    """Fail closed on full independent witnesses, even if the backend says pass.

    original_a4 must return the full native A4 residual, including the effective
    RHS for a nonzero port load. port_closure and recovery must independently
    evaluate cumulative port and interior states against the same original RHS.
    Witnesses share the existing exact action; no private CSR is requested.
    """

    def __init__(
        self,
        backend: IterativeBackend,
        *,
        witness_operator_sha256: str,
        original_a4: Callable[[CoarseState, CoarseRHS], ResidualWitness],
        port_closure: Callable[[CoarseState, CoarseRHS], ResidualWitness],
        recovery: Callable[[CoarseState, CoarseRHS], ResidualWitness],
        slave_dofs: tuple[int, ...],
        failure_sink=None,
    ):
        if not isinstance(backend.plan, InversePlan):
            raise TypeError("validated inverse plan is required before construction")
        if backend.plan.operator_sha256 != witness_operator_sha256:
            raise ValueError(
                "candidate and original witness operator identities differ"
            )
        if not all(
            callable(f) for f in (original_a4, port_closure, recovery, backend.solve)
        ):
            raise TypeError("all independent checks and backend.solve are mandatory")
        if (
            not isinstance(slave_dofs, tuple)
            or any(type(i) is not int or i < 0 for i in slave_dofs)
            or len(set(slave_dofs)) != len(slave_dofs)
        ):
            raise ValueError("slave DOFs must be distinct nonnegative integers")
        self.backend = backend
        self.plan = backend.plan
        self.witnesses = {
            "original_a4": original_a4,
            "port_closure": port_closure,
            "recovery": recovery,
        }
        self.slaves = np.asarray(slave_dofs, dtype=np.int64)
        self.failure_sink = failure_sink
        self.calls = 0
        self.last_audit = {}

    def solve(self, rhs: CoarseRHS) -> CoarseState:
        self.calls += 1
        state = None
        audit = {
            "status": "COARSE_INVERSE_NOT_QUALIFIED",
            "call": self.calls,
            "operator_sha256": self.plan.operator_sha256,
            "tolerance": TOLERANCE,
            "backend_called": False,
            "checks": {},
        }
        self.last_audit = audit
        try:
            if self.backend.plan != self.plan:
                raise ValueError("inverse plan changed after admission")
            if not isinstance(rhs, CoarseRHS) or rhs.fe.size == 0:
                raise ValueError("nonempty complete CoarseRHS is required")
            if self.slaves.size and self.slaves.max() >= rhs.fe.size:
                raise ValueError("slave DOF outside FE storage")
            if np.any(rhs.fe[self.slaves] != 0.0):
                raise ValueError("RHS violates exact slave-zero storage")
            zero = not np.any(rhs.fe) and not np.any(rhs.port)
            if zero:
                state = CoarseState(np.zeros_like(rhs.fe), np.zeros_like(rhs.port))
                report = IterationReport(iterations=0)
            else:
                audit["backend_called"] = True
                state, report = self.backend.solve(rhs)
            if (
                not isinstance(report, IterationReport)
                or type(report.iterations) is not int
                or not 0 <= report.iterations <= MAX_ITERATIONS
                or report.restart != RESTART
                or report.pc_side != "right"
                or report.zero_start is not True
            ):
                raise ValueError(
                    "expected zero-start right FGMRES32 with at most 256 steps"
                )
            if not isinstance(state, CoarseState):
                raise TypeError("backend must return a complete CoarseState")
            if state.fe.shape != rhs.fe.shape or state.port.shape != rhs.port.shape:
                raise ValueError("returned FE/port shape mismatch")
            if np.any(state.fe[self.slaves] != 0.0):
                raise ValueError("returned state violates exact slave-zero storage")
            if zero and (np.any(state.fe) or np.any(state.port)):
                raise ValueError("zero RHS requires an exact zero state")
            audit["iterations"] = report.iterations
            audit["zero_rhs"] = zero
            for name, witness in self.witnesses.items():
                measured = witness(state, rhs)
                if not isinstance(measured, ResidualWitness):
                    raise TypeError(
                        f"{name} must supply a quantitative residual witness"
                    )
                relative = measured.relative()
                audit["checks"][name] = relative
                if not np.isfinite(relative) or relative > TOLERANCE:
                    raise ValueError(f"{name} residual exceeds 1e-10")
            audit["status"] = "STRICT_RETURN_CHECK_PASS"
            return state
        except Exception as exc:
            audit["reason"] = str(exc)
            audit["error_type"] = type(exc).__name__
            if self.failure_sink is not None:
                try:
                    self.failure_sink(
                        {"audit": audit.copy(), "rhs": rhs, "state": state}
                    )
                except Exception as sink_error:  # noqa: BLE001 - retain the original rejection on sink errors.
                    audit["failure_sink_error"] = str(sink_error)
            raise CoarseReturnRejected(audit) from exc
