"""Route C online right-FGMRES and harmonic-Ritz direction sampling.

Route C is a research-only fallback for a current explicit operator.  It runs
one continuous restarted right-FGMRES solve per authorized source.  The
Arnoldi basis stays owner-local, and at every restart the smallest harmonic
Ritz directions are returned to the caller for distributed persistence.  No
Maxwell assembly, exact factor, or numeric MPI allgather is performed here.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping, Sequence
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc


ROUTE_C_LABELS = ("external_dtn_coupling", "fixed_random_repeat_0")
ROUTE_C_CHECKPOINTS = (16, 32, 64, 128)
ROUTE_C_CONDITIONAL_CHECKPOINT = 256
ROUTE_C_RESTART = 32
ROUTE_C_MAX_RITZ_VALUES = 8
ROUTE_C_SHARED_DIRECTION_THRESHOLD = 0.90
ROUTE_C_INTERFACE_COMPONENTS = ("lower", "upper", "joint")
ROUTE_C_GAMMA_COMPONENTS = ("lower", "upper")
ROUTE_C_EARLY_CONVERGENCE_THRESHOLD = 1.0e-10

__all__ = (
    "ROUTE_C_CHECKPOINTS",
    "ROUTE_C_CONDITIONAL_CHECKPOINT",
    "ROUTE_C_LABELS",
    "ROUTE_C_MAX_RITZ_VALUES",
    "ROUTE_C_RESTART",
    "ROUTE_C_SHARED_DIRECTION_THRESHOLD",
    "ROUTE_C_INTERFACE_COMPONENTS",
    "ROUTE_C_GAMMA_COMPONENTS",
    "ROUTE_C_EARLY_CONVERGENCE_THRESHOLD",
    "RouteCCollectiveCallbackError",
    "classify_route_c_signal",
    "run_route_c_online_fgmres",
)


class RouteCCollectiveCallbackError(RuntimeError):
    """A callback failed on one or more ranks and all ranks were notified."""


class _IdentityRightPreconditioner:
    """Identity action retained only for an explicitly marked unit test."""

    def __init__(self) -> None:
        self.apply_count = 0

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        source.copy(target)
        self.apply_count += 1


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float, np.integer, np.floating)) and bool(
        np.isfinite(float(value))
    )


def _decade_drop(r64: Any, r128: Any) -> float | None:
    if not (_finite_number(r64) and _finite_number(r128)):
        return None
    r64 = float(r64)
    r128 = float(r128)
    if r64 <= 0.0 or r128 <= 0.0:
        return None
    return float(np.log10(r64 / r128))


def classify_route_c_signal(
    records: Mapping[str, Mapping[str, Any]],
    *,
    shared_slow_direction_count: int = 0,
) -> dict[str, Any]:
    """Classify Route C from all authorized sources at the 128 checkpoint.

    ``ROUTE_C_MIXED_SIGNAL`` is a terminal diagnostic for this source family:
    inconsistent source/generalization evidence is never promoted to a
    positive signal or silently continued into another family.
    """

    labels = tuple(records)
    per_label: dict[str, dict[str, Any]] = {}
    for label in labels:
        checkpoints = records[label].get("checkpoints", {})
        r64 = checkpoints.get("64", {}).get("true_residual_relative")
        r128 = checkpoints.get("128", {}).get("true_residual_relative")
        drop = _decade_drop(r64, r128)
        per_label[label] = {
            "r64": r64,
            "r128": r128,
            "final_iteration": int(records[label].get("final_iteration", 128)),
            "final_true_residual_relative": records[label].get(
                "final_true_residual_relative"
            ),
            "decade_drop_64_to_128": drop,
            "finite": _finite_number(r64) and _finite_number(r128),
            "early_converged": bool(
                records[label].get("stopped_at_happy_breakdown") is True
                and int(records[label].get("final_iteration", 128)) < 128
                and _finite_number(
                    records[label].get("final_true_residual_relative")
                )
                and float(records[label]["final_true_residual_relative"])
                <= ROUTE_C_EARLY_CONVERGENCE_THRESHOLD
            ),
            "strong": bool(
                (_finite_number(r128) and float(r128) <= 0.5)
                or (drop is not None and drop >= 0.25)
                or (
                    records[label].get("stopped_at_happy_breakdown") is True
                    and int(records[label].get("final_iteration", 128)) < 128
                    and _finite_number(
                        records[label].get("final_true_residual_relative")
                    )
                    and float(records[label]["final_true_residual_relative"])
                    <= ROUTE_C_EARLY_CONVERGENCE_THRESHOLD
                )
            ),
            "weak": bool(
                (_finite_number(r128) and float(r128) <= 0.8)
                or (drop is not None and drop >= 0.10)
                or (
                    records[label].get("stopped_at_happy_breakdown") is True
                    and int(records[label].get("final_iteration", 128)) < 128
                    and _finite_number(
                        records[label].get("final_true_residual_relative")
                    )
                    and float(records[label]["final_true_residual_relative"])
                    <= ROUTE_C_EARLY_CONVERGENCE_THRESHOLD
                )
            ),
            "no_signal": bool(
                _finite_number(r128)
                and float(r128) > 0.9
                and (drop is None or drop < 0.05)
                and not (
                    records[label].get("stopped_at_happy_breakdown") is True
                    and int(records[label].get("final_iteration", 128)) < 128
                    and _finite_number(
                        records[label].get("final_true_residual_relative")
                    )
                    and float(records[label]["final_true_residual_relative"])
                    <= ROUTE_C_EARLY_CONVERGENCE_THRESHOLD
                )
            ),
        }
    strong = bool(labels) and all(item["strong"] for item in per_label.values())
    weak = bool(labels) and all(item["weak"] for item in per_label.values())
    shared = int(shared_slow_direction_count) > 0
    no_signal = bool(labels) and all(item["no_signal"] for item in per_label.values()) and not shared
    if strong:
        classification = "ROUTE_C_STRONG_SIGNAL"
    elif weak or shared:
        classification = "ROUTE_C_WEAK_POSITIVE_SIGNAL"
    elif no_signal:
        classification = "ROUTE_C_NO_SIGNAL"
    else:
        classification = "ROUTE_C_MIXED_SIGNAL"
    inconsistent = classification == "ROUTE_C_MIXED_SIGNAL"
    positive = classification in {
        "ROUTE_C_STRONG_SIGNAL",
        "ROUTE_C_WEAK_POSITIVE_SIGNAL",
    }
    next_action = (
        "bounded_online_rank_screen"
        if positive
        else "stop_current_coupled_response_family"
        if classification == "ROUTE_C_NO_SIGNAL"
        else "stop_by_inconsistent_generalization_gate"
    )
    return {
        "classification": classification,
        "terminal": not positive,
        "next_action": next_action,
        "mixed_signal_next_action": (
            "stop_by_inconsistent_generalization_gate"
            if inconsistent
            else None
        ),
        "inconsistent_generalization_gate": inconsistent,
        "per_label": per_label,
        "shared_slow_direction_count": int(shared_slow_direction_count),
        "strong": bool(strong and not inconsistent),
        "weak_positive": bool((weak or shared) and not inconsistent),
        "no_signal": no_signal,
    }


def _least_squares(hessenberg: np.ndarray, rhs: np.ndarray) -> np.ndarray:
    """Solve the small Arnoldi least-squares problem with an SVD backend."""

    values, _singular_values, _rank, _ = np.linalg.lstsq(
        np.asarray(hessenberg, dtype=np.complex128),
        np.asarray(rhs, dtype=np.complex128),
        rcond=None,
    )
    return np.asarray(values, dtype=np.complex128)


def _harmonic_ritz(
    hessenberg: np.ndarray,
) -> list[tuple[complex, float, np.ndarray]]:
    """Return up to eight harmonic Ritz values, estimates, and coefficients.

    The correction uses the standard harmonic projected operator.  Its only
    dense operations are on the at-most-32 Arnoldi Hessenberg block; full
    vectors remain distributed PETSc Vec objects.
    """

    hessenberg = np.asarray(hessenberg, dtype=np.complex128)
    m = int(hessenberg.shape[1])
    if hessenberg.shape != (m + 1, m) or m == 0:
        return []
    h_small = hessenberg[:m, :m]
    last = float(abs(hessenberg[m, m - 1]))
    edge = np.zeros(m, dtype=np.complex128)
    edge[-1] = 1.0
    try:
        correction_column = np.linalg.solve(h_small.conj().T, edge)
    except np.linalg.LinAlgError:
        correction_column = np.linalg.pinv(h_small.conj().T) @ edge
    projected = h_small + (last**2) * np.outer(correction_column, edge)
    eigenvalues, eigenvectors = np.linalg.eig(projected)
    order = np.argsort(np.abs(eigenvalues))[:ROUTE_C_MAX_RITZ_VALUES]
    result: list[tuple[complex, float, np.ndarray]] = []
    for index in order:
        coefficients = np.asarray(eigenvectors[:, index], dtype=np.complex128)
        norm = float(np.linalg.norm(coefficients))
        if norm <= 1.0e-30 or not np.isfinite(norm):
            continue
        coefficients /= norm
        extended_coefficients = np.r_[coefficients, 0.0 + 0.0j]
        estimate = float(
            np.linalg.norm(
                hessenberg @ coefficients
                - eigenvalues[index] * extended_coefficients
            )
            / max(float(np.linalg.norm(coefficients)), 1.0e-30)
        )
        result.append((complex(eigenvalues[index]), estimate, coefficients))
    return result


def _resource_allows_conditional_256(resource: Mapping[str, Any]) -> bool:
    rss = resource.get("rss_bytes")
    swap = resource.get("swap_bytes")
    wall = resource.get("wall_observation")
    if not (
        _finite_number(rss)
        and _finite_number(swap)
        and isinstance(wall, Mapping)
    ):
        return False
    budget = wall.get("budget_seconds")
    elapsed = wall.get("elapsed_seconds")
    remaining = wall.get("remaining_seconds")
    predicted_remaining = wall.get("predicted_remaining_seconds")
    predicted_total = wall.get("predicted_total_seconds")
    if not all(
        _finite_number(value)
        for value in (
            budget,
            elapsed,
            remaining,
            predicted_remaining,
            predicted_total,
        )
    ):
        return False
    budget = float(budget)
    elapsed = float(elapsed)
    remaining = float(remaining)
    predicted_remaining = float(predicted_remaining)
    predicted_total = float(predicted_total)
    tolerance = max(1.0e-6, 1.0e-9 * abs(budget))
    return bool(
        resource.get("pass") is True
        and resource.get("wall_controlled") is True
        and wall.get("pass") is True
        and np.isclose(budget, 21600.0, rtol=0.0, atol=tolerance)
        and elapsed >= 0.0
        and remaining > 0.0
        and np.isclose(
            remaining,
            budget - elapsed,
            rtol=1.0e-9,
            atol=tolerance,
        )
        and predicted_remaining >= 0.0
        and np.isclose(
            predicted_total,
            elapsed + predicted_remaining,
            rtol=1.0e-9,
            atol=tolerance,
        )
        and predicted_total <= budget + tolerance
        and float(rss) >= 0.0
        and int(float(rss)) < 45 * 2**30
        and float(swap) == 0.0
    )


def _collective_callback(
    comm: MPI.Comm,
    callback: Callable[..., Any],
    stage: str,
    *args: Any,
) -> Any:
    """Run a callback and propagate rank-local exceptions before continuing.

    The callback result itself is deliberately kept rank-local.  Only a small
    success/error envelope is exchanged, so this helper never gathers a PETSc
    vector or other numeric payload.
    """

    value: Any = None
    error: dict[str, str] | None = None
    try:
        value = callback(*args)
    except Exception as exc:  # noqa: BLE001 - preserve callback root details
        error = {"type": type(exc).__name__, "message": str(exc)}
    envelopes = comm.allgather({"rank": int(comm.rank), "error": error})
    failures = [
        {
            "rank": int(item["rank"]),
            "type": item["error"]["type"],
            "message": item["error"]["message"],
        }
        for item in envelopes
        if item.get("error") is not None
    ]
    if failures:
        raise RouteCCollectiveCallbackError(
            f"Route C {stage} callback failed collectively: {failures}"
        )
    return value


def _collective_resource_observation(
    comm: MPI.Comm,
    callback: Callable[[], Mapping[str, Any]] | None,
) -> dict[str, Any]:
    """Collect small per-rank resource observations and derive one gate."""

    if callback is None:
        return {
            "status": "not_provided",
            "pass": False,
            "collective_pass": False,
            "wall_controlled": False,
            "rank_observations": [],
        }
    value: dict[str, Any] = {}
    error: dict[str, str] | None = None
    try:
        value = dict(callback())
    except Exception as exc:  # noqa: BLE001 - propagate implementation root
        error = {"type": type(exc).__name__, "message": str(exc)}
    envelope = comm.allgather(
        {"rank": int(comm.rank), "value": value, "error": error}
    )
    failures = [
        {
            "rank": int(item["rank"]),
            "type": item["error"]["type"],
            "message": item["error"]["message"],
        }
        for item in envelope
        if item.get("error") is not None
    ]
    if failures:
        raise RouteCCollectiveCallbackError(
            f"Route C resource callback failed collectively: {failures}"
        )
    observations = [dict(item["value"]) for item in envelope]
    rank_pass = [item.get("pass") is True for item in observations]
    wall_pass = [
        item.get("wall_controlled") is True
        and isinstance(item.get("wall_observation"), Mapping)
        and item["wall_observation"].get("pass") is True
        for item in observations
    ]
    rss_values = [item.get("rss_bytes") for item in observations]
    swap_values = [item.get("swap_bytes") for item in observations]
    finite_rss = all(_finite_number(item) for item in rss_values)
    finite_swap = all(_finite_number(item) for item in swap_values)
    aggregate = dict(value)
    aggregate.update(
        {
            "rank_observations": observations,
            "rank_count": len(observations),
            "rss_bytes": max((int(float(item)) for item in rss_values), default=None)
            if finite_rss
            else None,
            "swap_bytes": max((int(float(item)) for item in swap_values), default=None)
            if finite_swap
            else None,
            "wall_controlled": all(wall_pass),
            "collective_pass": bool(
                all(rank_pass) and all(wall_pass) and finite_rss and finite_swap
            ),
        }
    )
    aggregate["pass"] = bool(aggregate["collective_pass"])
    return aggregate


def _require_mapping(value: Any) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Route C callback must return a mapping")
    return value


def run_route_c_online_fgmres(
    operator: PETSc.Mat,
    rhs_by_label: Mapping[str, PETSc.Vec],
    right_preconditioner: Any | None = None,
    *,
    labels: Sequence[str] = ROUTE_C_LABELS,
    allow_identity_test_only: bool = False,
    resource_callback: Callable[[], Mapping[str, Any]] | None = None,
    interface_residual_callback: Callable[
        [PETSc.Vec, PETSc.Vec, int], Mapping[str, Any]
    ]
    | None = None,
    interface_direction_callback: Callable[
        [str, int, int, PETSc.Vec, PETSc.Vec, Mapping[str, Any]],
        Mapping[str, Any],
    ]
    | None = None,
    checkpoint_callback: Callable[[Mapping[str, Any]], None] | None = None,
    basis_callback: Callable[
        [str, int, int, PETSc.Vec, PETSc.Vec, Mapping[str, Any]],
        Mapping[str, Any],
    ]
    | None = None,
) -> dict[str, Any]:
    """Run continuous restarted right-FGMRES for the two Route C sources.

    The implementation is an explicit distributed Arnoldi loop.  Each
    restart continues from the previous solution; it is not a fresh solve.
    ``basis_callback`` is given normalized owner-local harmonic Ritz vectors
    and may persist them without any FE-sized allgather.  Interface slow
    directions are obtained only through ``interface_direction_callback``;
    the residual-trace callback is never reused as a direction projection.
    """

    if not isinstance(operator, PETSc.Mat):
        raise TypeError("Route C requires an explicit PETSc matrix")
    labels = tuple(str(label) for label in labels)
    if labels != ROUTE_C_LABELS:
        raise ValueError("Route C labels must be external plus fixed_random_repeat_0")
    if tuple(rhs_by_label) != labels:
        raise ValueError("Route C RHS labels are not in the frozen order")
    rows, cols = map(int, operator.getSize())
    if rows != cols or any(
        not isinstance(rhs_by_label[label], PETSc.Vec)
        or int(rhs_by_label[label].getSize()) != rows
        for label in labels
    ):
        raise ValueError("Route C RHS/operator layout is invalid")
    action = right_preconditioner
    identity_test_only = action is None
    if identity_test_only:
        if not allow_identity_test_only:
            raise ValueError("Route C formal screen requires a nonidentity current PC")
        action = _IdentityRightPreconditioner()
    if not callable(getattr(action, "apply", None)):
        raise TypeError("Route C right preconditioner must expose apply")
    if not identity_test_only and (
        interface_residual_callback is None
        or interface_direction_callback is None
        or basis_callback is None
    ):
        raise ValueError(
            "Route C formal screening requires interface residual, projection, "
            "and owner-row basis persistence callbacks"
        )

    comm = operator.getComm().tompi4py()
    records: dict[str, dict[str, Any]] = {}
    direction_records: dict[str, list[dict[str, Any]]] = {}
    direction_vectors: dict[
        str, list[tuple[int, int, dict[str, dict[str, Any]]]]
    ] = {}
    started = time.perf_counter()
    total_apply_count = 0
    total_restart_count = 0
    numeric_allgather_count = 0
    callback_collective_count = 0
    resource_collective_count = 0
    basis_replication_observations: list[bool] = []
    projection_audit_observations: list[bool] = []
    persistence_audit_observations: list[bool] = []
    interface_trace_observations: list[bool] = []

    def callback_call(callback: Callable[..., Any], stage: str, *args: Any) -> Any:
        nonlocal callback_collective_count
        callback_collective_count += 1
        return _collective_callback(comm, callback, stage, *args)

    def true_residual_row(
        label: str,
        rhs: PETSc.Vec,
        residual: PETSc.Vec,
        solution: PETSc.Vec,
        rhs_norm: float,
        iteration: int,
        reported: float,
    ) -> dict[str, Any]:
        residual.set(0.0)
        operator.mult(solution, residual)
        residual.scale(PETSc.ScalarType(-1.0))
        residual.axpy(PETSc.ScalarType(1.0), rhs)
        norm = float(residual.norm())
        value = norm / max(rhs_norm, 1.0e-30)
        return {
            "label": label,
            "iteration": int(iteration),
            "phase": "continuous",
            "restart": ROUTE_C_RESTART,
            "reported_relative_residual": float(reported),
            "true_residual_relative": float(value),
            "true_residual_norm": norm,
            "finite": bool(
                np.isfinite(float(reported))
                and np.isfinite(norm)
                and np.isfinite(value)
            ),
            "continuous": True,
            "interface_residual_trace": (
                {}
                if interface_residual_callback is None
                else dict(
                    callback_call(
                        interface_residual_callback,
                        "interface_residual",
                        residual,
                        rhs,
                        int(iteration),
                    )
                )
            ),
        }

    def add_direction_records(
        label: str,
        restart: int,
        iteration: int,
        basis: Sequence[PETSc.Vec],
        preconditioned: Sequence[PETSc.Vec],
        hessenberg: np.ndarray,
        orthogonality_error: float,
        arnoldi_relation_residual: float,
    ) -> None:
        values = _harmonic_ritz(hessenberg)
        records_for_restart: list[dict[str, Any]] = []
        for direction_index, (value, estimate, coefficients) in enumerate(values):
            direction = basis[0].duplicate()
            response_direction: PETSc.Vec | None = None
            try:
                direction.set(0.0)
                for coefficient, vector in zip(coefficients, basis, strict=True):
                    direction.axpy(PETSc.ScalarType(coefficient), vector)
                norm = float(direction.norm())
                if norm <= 1.0e-30 or not np.isfinite(norm):
                    continue
                direction.scale(PETSc.ScalarType(1.0 / norm))
                action_direction = preconditioned[0].duplicate()
                unscaled_direction = basis[0].duplicate()
                action_image: PETSc.Vec | None = None
                action_direction.set(0.0)
                unscaled_direction.set(0.0)
                try:
                    for coefficient, vector, transformed in zip(
                        coefficients, basis, preconditioned, strict=True
                    ):
                        unscaled_direction.axpy(
                            PETSc.ScalarType(coefficient), vector
                        )
                        action_direction.axpy(
                            PETSc.ScalarType(coefficient), transformed
                        )
                    action_image = operator.createVecLeft()
                    operator.mult(action_direction, action_image)
                    image_norm = float(action_image.norm())
                    action_image.axpy(
                        PETSc.ScalarType(-value), unscaled_direction
                    )
                    full_action_residual = float(action_image.norm()) / max(
                        image_norm, 1.0e-30
                    )
                    response_norm = float(action_direction.norm())
                    if response_norm <= 1.0e-30 or not np.isfinite(response_norm):
                        raise ValueError(
                            "Route C preconditioned response direction is zero or nonfinite"
                        )
                    response_direction = action_direction.copy()
                    response_direction.scale(PETSc.ScalarType(1.0 / response_norm))
                finally:
                    if action_image is not None:
                        action_image.destroy()
                    action_direction.destroy()
                    unscaled_direction.destroy()
                projection_audit: dict[str, Any] = {"status": "not_provided"}
                projections: dict[str, dict[str, Any]] = {}
                if interface_direction_callback is not None:
                    projection_payload = callback_call(
                        interface_direction_callback,
                        "interface_direction",
                        label,
                        int(restart),
                        int(direction_index),
                        direction,
                        response_direction,
                        {
                            "ritz_value": [float(value.real), float(value.imag)],
                            "ritz_residual_estimate": float(estimate),
                            "residual_direction_kind": "V_y",
                            "preconditioned_response_direction_kind": "Z_y",
                        },
                    )

                    def validate_projection_payload(
                        payload: Any,
                    ) -> Mapping[str, Any]:
                        if not isinstance(payload, Mapping):
                            raise ValueError(
                                "Route C interface direction projection must be a mapping"
                            )
                        if "joint" in payload:
                            raise ValueError(
                                "Route C joint Gamma projection must be derived from lower/upper"
                            )
                        missing = [
                            component
                            for component in ROUTE_C_GAMMA_COMPONENTS
                            if not isinstance(payload.get(component), Mapping)
                        ]
                        if missing:
                            raise ValueError(
                                "Route C interface direction projection is missing "
                                f"compact Gamma components: {missing}"
                            )
                        compact: dict[str, dict[str, Any]] = {}
                        for component in ROUTE_C_GAMMA_COMPONENTS:
                            shard = payload[component]
                            try:
                                values = np.asarray(
                                    shard["values"], dtype=np.complex128
                                )
                                positions = np.asarray(
                                    shard["canonical_positions"], dtype=np.int64
                                )
                            except (KeyError, TypeError, ValueError) as exc:
                                raise ValueError(
                                    f"Route C {component} Gamma shard is malformed"
                                ) from exc
                            if values.ndim != 1 or positions.ndim != 1:
                                raise ValueError(
                                    f"Route C {component} Gamma shard must be one-dimensional"
                                )
                            if len(values) != len(positions):
                                raise ValueError(
                                    f"Route C {component} Gamma values/positions mismatch"
                                )
                            if len(np.unique(positions)) != len(positions):
                                raise ValueError(
                                    f"Route C {component} Gamma positions are not unique"
                                )
                            if not np.isfinite(values).all() or np.any(positions < 0):
                                raise ValueError(
                                    f"Route C {component} Gamma shard is invalid"
                                )
                            compact[component] = {
                                "values": np.array(values, copy=True),
                                "canonical_positions": np.array(
                                    positions, copy=True
                                ),
                                "canonical_key_count": shard.get(
                                    "canonical_key_count"
                                ),
                                "canonical_key_order_sha256": shard.get(
                                    "canonical_key_order_sha256"
                                ),
                            }
                        audit = payload.get("audit")
                        if not isinstance(audit, Mapping):
                            raise ValueError(
                                "Route C interface projection must include an audit mapping"
                            )
                        if audit.get("status") != "pass":
                            raise ValueError(
                                "Route C interface projection audit did not pass"
                            )
                        if audit.get("replicated") is not False:
                            raise ValueError(
                                "Route C interface projection must be owner-local"
                            )
                        if not identity_test_only:
                            if audit.get("source_direction") != (
                                "preconditioned_response_direction_Z_y"
                            ):
                                raise ValueError(
                                    "Route C interface projection must use Z_y"
                                )
                            canonical_trace = audit.get("canonical_interface_trace")
                            if not isinstance(canonical_trace, Mapping):
                                raise ValueError(
                                    "Route C projection must persist canonical interface trace"
                                )
                            if set(canonical_trace) != set(ROUTE_C_GAMMA_COMPONENTS):
                                raise ValueError(
                                    "Route C canonical interface trace components are incomplete"
                                )
                        return {**payload, **compact}

                    projection_payload = callback_call(
                        validate_projection_payload,
                        "interface_direction_contract",
                        projection_payload,
                    )
                    projections = {
                        component: projection_payload[component]
                        for component in ROUTE_C_GAMMA_COMPONENTS
                    }
                    projection_audit = {
                        "status": "pass",
                        "replicated": bool(
                            projection_payload["audit"].get("replicated", False)
                        ),
                        "audit": dict(projection_payload["audit"]),
                        "components": {
                            component: {
                                "owner_local": True,
                                "local_size": len(projections[component]["values"]),
                                "canonical_position_count": len(
                                    projections[component]["canonical_positions"]
                                ),
                                "canonical_key_count": projections[component].get(
                                    "canonical_key_count"
                                ),
                                "canonical_key_order_sha256": projections[
                                    component
                                ].get("canonical_key_order_sha256"),
                            }
                            for component in ROUTE_C_GAMMA_COMPONENTS
                        },
                    }
                    projection_audit_observations.append(True)
                metadata: dict[str, Any] = {
                    "label": label,
                    "restart": int(restart),
                    "iteration": int(iteration),
                    "direction_index": int(direction_index),
                    "kind": "owner_row_harmonic_ritz_direction",
                    "harmonic_projected_equation": "A Z_y ~= theta V_y",
                    "ritz_value": [float(value.real), float(value.imag)],
                    "ritz_residual_estimate": float(estimate),
                    "owner_local": True,
                    "numeric_allgather": False,
                    "direction_mapping": {
                        "residual_space": "residual_direction_V_y",
                        "response_space": "preconditioned_response_direction_Z_y",
                        "map": "Z_y=sum_j y_j z_j with z_j=M_current^{-1} V_j",
                        "coarse_reconstruction_space": (
                            "preconditioned_response_direction_Z_y"
                        ),
                    },
                    "interface_direction_projection": projection_audit,
                    "full_action_residual_relative": float(full_action_residual),
                    "orthogonality_error": float(orthogonality_error),
                    "arnoldi_relation_residual": float(arnoldi_relation_residual),
                    "residual_direction": {
                        "kind": "residual_space_V_y",
                        "normalized": True,
                        "global_size": int(direction.getSize()),
                        "ownership_range": list(
                            map(int, direction.getOwnershipRange())
                        ),
                    },
                    "preconditioned_response_direction": {
                        "kind": "response_space_Z_y",
                        "normalized": True,
                        "global_size": int(response_direction.getSize()),
                        "ownership_range": list(
                            map(int, response_direction.getOwnershipRange())
                        ),
                    },
                }
                if basis_callback is not None:
                    persistence_payload = callback_call(
                        basis_callback,
                        "basis",
                        label,
                        int(restart),
                        int(direction_index),
                        direction,
                        response_direction,
                        metadata,
                    )
                    persistence_payload = callback_call(
                        _require_mapping,
                        "basis_contract",
                        persistence_payload,
                    )
                    metadata["persistence"] = dict(persistence_payload)
                    persistence = metadata["persistence"]
                    if not identity_test_only:
                        if persistence.get("status") != "pass":
                            raise ValueError(
                                "Route C basis persistence audit did not pass"
                            )
                        if persistence.get("replicated") is not False:
                            raise ValueError(
                                "Route C basis persistence must be owner-local"
                            )
                        for name in (
                            "residual_direction",
                            "preconditioned_response_direction",
                            "canonical_interface_trace",
                        ):
                            if not isinstance(persistence.get(name), Mapping):
                                raise ValueError(
                                    "Route C basis persistence must record " + name
                                )
                        trace = persistence["canonical_interface_trace"]
                        if trace.get("direction_space") != (
                            "preconditioned_response_direction_Z_y"
                        ):
                            raise ValueError(
                                "Route C canonical interface trace must be from Z_y"
                            )
                        if set(trace.get("components", {})) != set(
                            ROUTE_C_GAMMA_COMPONENTS
                        ):
                            raise ValueError(
                                "Route C canonical interface trace components are incomplete"
                            )
                    persistence_audit_observations.append(
                        persistence.get("status") == "pass"
                        and persistence.get("replicated") is False
                    )
                    interface_trace_observations.append(
                        isinstance(
                            persistence.get("canonical_interface_trace"), Mapping
                        )
                        and persistence.get("canonical_interface_trace", {}).get(
                            "direction_space"
                        )
                        == "preconditioned_response_direction_Z_y"
                    )
                    if "replicated" in metadata["persistence"]:
                        basis_replication_observations.append(
                            bool(metadata["persistence"]["replicated"])
                        )
                records_for_restart.append(metadata)
                direction_vectors.setdefault(label, []).append(
                    (int(restart), int(direction_index), projections)
                )
            finally:
                direction.destroy()
                if response_direction is not None:
                    response_direction.destroy()
        direction_records.setdefault(label, []).append(
            {
                "restart": int(restart),
                "iteration": int(iteration),
                "direction_count": len(records_for_restart),
                "orthogonality_error": float(orthogonality_error),
                "arnoldi_relation_residual": float(arnoldi_relation_residual),
                "directions": records_for_restart,
            }
        )

    try:
        for label in labels:
            rhs = rhs_by_label[label]
            rhs_norm = float(rhs.norm())
            local_finite = bool(np.all(np.isfinite(rhs.array_r)))
            if not bool(comm.allreduce(local_finite, op=MPI.LAND)):
                raise ValueError(f"Route C RHS {label} is nonfinite")
            if not np.isfinite(rhs_norm) or rhs_norm <= 1.0e-30:
                raise ValueError(f"Route C RHS {label} is zero or nonfinite")
            x = operator.createVecRight()
            residual = operator.createVecLeft()
            x.set(0.0)
            rhs.copy(residual)
            label_directions = direction_records.setdefault(label, [])
            records[label] = {
                "label": label,
                "restart": ROUTE_C_RESTART,
                "continuous_right_fgmres": True,
                "max_it": ROUTE_C_CONDITIONAL_CHECKPOINT,
                "zero_initial_guess": True,
                "zero_initial_guess_count": 1,
                "checkpoints": {
                    "0": {
                        "label": label,
                        "iteration": 0,
                        "phase": "continuous",
                        "restart": ROUTE_C_RESTART,
                        "reported_relative_residual": 1.0,
                        "true_residual_relative": 1.0,
                        "finite": True,
                        "continuous": True,
                    }
                },
                "reported_residual_history": [],
                "checkpoint_callback_count": 0,
            }
            try:
                total_iterations = 0
                authorized_max = ROUTE_C_RESTART * 4
                conditional_256 = False
                resource_at_128: dict[str, Any] | None = None
                stopped_at_happy_breakdown = False
                while total_iterations < authorized_max:
                    restart_number = len(label_directions) + 1
                    total_restart_count += 1
                    beta = float(residual.norm())
                    if not np.isfinite(beta) or beta <= 1.0e-30:
                        break
                    v0 = residual.copy()
                    v0.scale(PETSc.ScalarType(1.0 / beta))
                    basis = [v0]
                    preconditioned: list[PETSc.Vec] = []
                    hessenberg = np.zeros(
                        (ROUTE_C_RESTART + 1, ROUTE_C_RESTART),
                        dtype=np.complex128,
                    )
                    base_solution = x.copy()
                    cycle_steps = min(
                        ROUTE_C_RESTART,
                        authorized_max - total_iterations,
                    )
                    actual_steps = 0
                    orthogonality_error = 0.0
                    arnoldi_relation_residual = 0.0
                    try:
                        for step in range(cycle_steps):
                            z = operator.createVecRight()
                            action.apply(basis[step], z)
                            total_apply_count += 1
                            preconditioned.append(z)
                            work = operator.createVecLeft()
                            raw_image = None
                            next_direction = None
                            try:
                                operator.mult(z, work)
                                raw_image = work.copy()
                                for _sweep in range(2):
                                    for index, direction in enumerate(basis):
                                        coefficient = direction.dot(work)
                                        hessenberg[index, step] += coefficient
                                        work.axpy(
                                            PETSc.ScalarType(-coefficient), direction
                                        )
                                next_norm = float(work.norm())
                                hessenberg[step + 1, step] = next_norm
                                if next_norm > 1.0e-30:
                                    next_direction = work.copy()
                                    next_direction.scale(
                                        PETSc.ScalarType(1.0 / next_norm)
                                    )
                                    orthogonality_error = max(
                                        orthogonality_error,
                                        max(
                                            (
                                                float(
                                                    abs(
                                                        direction.dot(
                                                            next_direction
                                                        )
                                                    )
                                                )
                                                for direction in basis
                                            ),
                                            default=0.0,
                                        ),
                                    )
                                    relation = raw_image.copy()
                                    try:
                                        for index, direction in enumerate(basis):
                                            relation.axpy(
                                                PETSc.ScalarType(
                                                    -hessenberg[index, step]
                                                ),
                                                direction,
                                            )
                                        relation.axpy(
                                            PETSc.ScalarType(-next_norm),
                                            next_direction,
                                        )
                                        raw_norm = float(raw_image.norm())
                                        arnoldi_relation_residual = max(
                                            arnoldi_relation_residual,
                                            float(relation.norm())
                                            / max(raw_norm, 1.0e-30),
                                        )
                                    finally:
                                        relation.destroy()
                                    basis.append(next_direction)
                                    next_direction = None
                            finally:
                                if next_direction is not None:
                                    next_direction.destroy()
                                if raw_image is not None:
                                    raw_image.destroy()
                                work.destroy()
                            actual_steps = step + 1
                            small_h = hessenberg[: step + 2, : step + 1]
                            least_squares_rhs = np.zeros(
                                step + 2, dtype=np.complex128
                            )
                            least_squares_rhs[0] = beta
                            coefficients = _least_squares(
                                small_h, least_squares_rhs
                            )
                            trial = base_solution.copy()
                            try:
                                for coefficient, vector in zip(
                                    coefficients, preconditioned, strict=True
                                ):
                                    trial.axpy(
                                        PETSc.ScalarType(coefficient), vector
                                    )
                                iteration = total_iterations + step + 1
                                reported = float(
                                    np.linalg.norm(
                                        least_squares_rhs - small_h @ coefficients
                                    )
                                ) / max(rhs_norm, 1.0e-30)
                                records[label]["reported_residual_history"].append(
                                    {
                                        "iteration": int(iteration),
                                        "relative_residual": reported,
                                    }
                                )
                                checkpoints = records[label]["checkpoints"]
                                if (
                                    (
                                        iteration in ROUTE_C_CHECKPOINTS
                                        or iteration == ROUTE_C_CONDITIONAL_CHECKPOINT
                                    )
                                    and str(iteration) not in checkpoints
                                ):
                                    row = true_residual_row(
                                        label,
                                        rhs,
                                        residual,
                                        trial,
                                        rhs_norm,
                                        iteration,
                                        reported,
                                    )
                                    checkpoints[str(iteration)] = row
                                    if checkpoint_callback is not None:
                                        callback_call(
                                            checkpoint_callback,
                                            "checkpoint",
                                            row,
                                        )
                                    records[label]["checkpoint_callback_count"] += 1
                            finally:
                                trial.destroy()
                            if next_norm <= 1.0e-30:
                                break
                        if actual_steps == 0:
                            break
                        coefficients = _least_squares(
                            hessenberg[: actual_steps + 1, :actual_steps],
                            np.r_[
                                beta,
                                np.zeros(actual_steps, dtype=np.complex128),
                            ],
                        )
                        base_solution.copy(x)
                        for coefficient, vector in zip(
                            coefficients, preconditioned, strict=True
                        ):
                            x.axpy(PETSc.ScalarType(coefficient), vector)
                        total_iterations += actual_steps
                        residual.set(0.0)
                        operator.mult(x, residual)
                        residual.scale(PETSc.ScalarType(-1.0))
                        residual.axpy(PETSc.ScalarType(1.0), rhs)
                        add_direction_records(
                            label,
                            restart_number,
                            total_iterations,
                            basis[:actual_steps],
                            preconditioned,
                            hessenberg[: actual_steps + 1, :actual_steps],
                            orthogonality_error,
                            arnoldi_relation_residual,
                        )
                        if total_iterations >= 128 and authorized_max == 128:
                            row = records[label]["checkpoints"].get("128", {})
                            r64 = records[label]["checkpoints"].get("64", {}).get(
                                "true_residual_relative"
                            )
                            r128 = row.get("true_residual_relative")
                            trend = bool(
                                _finite_number(r128)
                                and (
                                    float(r128) <= 0.8
                                    or (
                                        _decade_drop(r64, r128) is not None
                                        and _decade_drop(r64, r128) >= 0.05
                                    )
                                )
                            )
                            resource_at_128 = _collective_resource_observation(
                                comm, resource_callback
                            )
                            resource_collective_count += 1
                            resource_at_128["checkpoint"] = 128
                            conditional_256 = bool(
                                row.get("finite") is True
                                and trend
                                and _resource_allows_conditional_256(resource_at_128)
                            )
                            if not conditional_256:
                                break
                            authorized_max = ROUTE_C_CONDITIONAL_CHECKPOINT
                        if actual_steps < cycle_steps:
                            stopped_at_happy_breakdown = True
                            break
                    finally:
                        for vector in basis:
                            vector.destroy()
                        for vector in preconditioned:
                            vector.destroy()
                        base_solution.destroy()
                final_norm = float(residual.norm())
                final_relative = final_norm / max(rhs_norm, 1.0e-30)
                records[label].update(
                    {
                        "direction_records": label_directions,
                        "missing_checkpoints": [
                            str(index)
                            for index in ROUTE_C_CHECKPOINTS
                            if str(index) not in records[label]["checkpoints"]
                        ],
                        "missing_conditional_checkpoint": bool(
                            str(ROUTE_C_CONDITIONAL_CHECKPOINT)
                            not in records[label]["checkpoints"]
                        ),
                        "conditional_256_authorized": conditional_256,
                        "conditional_256_completed": bool(
                            conditional_256
                            and total_iterations >= 256
                            and str(ROUTE_C_CONDITIONAL_CHECKPOINT)
                            in records[label]["checkpoints"]
                        ),
                        "authorized_max": int(authorized_max),
                        "resource_at_128": resource_at_128,
                        "iterations": int(total_iterations),
                        "final_iteration": int(total_iterations),
                        "final_true_residual_norm": final_norm,
                        "final_true_residual_relative": final_relative,
                        "continuous_restart_count": len(label_directions),
                        "stopped_at_happy_breakdown": stopped_at_happy_breakdown,
                    }
                )
            finally:
                residual.destroy()
                x.destroy()
    except Exception:
        raise
    shared_matches: list[dict[str, Any]] = []
    first_directions = direction_vectors.get(labels[0], [])
    second_directions = direction_vectors.get(labels[1], [])
    for first_restart, first_index, first in first_directions:
        for second_restart, second_index, second in second_directions:
            for component in ROUTE_C_INTERFACE_COMPONENTS:
                if any(
                    name not in first or name not in second
                    for name in ROUTE_C_GAMMA_COMPONENTS
                ):
                    continue
                if component == "joint":
                    first_norm_sq = sum(
                        float(np.vdot(first[name]["values"], first[name]["values"]).real)
                        for name in ROUTE_C_GAMMA_COMPONENTS
                    )
                    second_norm_sq = sum(
                        float(np.vdot(second[name]["values"], second[name]["values"]).real)
                        for name in ROUTE_C_GAMMA_COMPONENTS
                    )
                    local_inner = sum(
                        np.vdot(first[name]["values"], second[name]["values"])
                        for name in ROUTE_C_GAMMA_COMPONENTS
                    )
                else:
                    first_shard = first[component]
                    second_shard = second[component]
                    if not np.array_equal(
                        first_shard["canonical_positions"],
                        second_shard["canonical_positions"],
                    ):
                        raise ValueError(
                            "Route C shared Gamma shards have different canonical positions"
                        )
                    first_norm_sq = float(
                        np.vdot(
                            first_shard["values"], first_shard["values"]
                        ).real
                    )
                    second_norm_sq = float(
                        np.vdot(
                            second_shard["values"], second_shard["values"]
                        ).real
                    )
                    local_inner = np.vdot(
                        first_shard["values"], second_shard["values"]
                    )
                first_norm = float(
                    np.sqrt(comm.allreduce(first_norm_sq, op=MPI.SUM))
                )
                second_norm = float(
                    np.sqrt(comm.allreduce(second_norm_sq, op=MPI.SUM))
                )
                if first_norm <= 0.0 or second_norm <= 0.0:
                    continue
                correlation = float(abs(comm.allreduce(local_inner, op=MPI.SUM))) / (
                    first_norm * second_norm
                )
                if correlation >= ROUTE_C_SHARED_DIRECTION_THRESHOLD:
                    shared_matches.append(
                        {
                            "component": component,
                            "left_restart": first_restart,
                            "left_direction": first_index,
                            "right_restart": second_restart,
                            "right_direction": second_index,
                            "normalized_correlation": correlation,
                        }
                    )
    stable_components: list[str] = []
    stable_component_pairs: dict[str, set[tuple[int, int]]] = {}
    for component in ROUTE_C_INTERFACE_COMPONENTS:
        pairs = {
            (item["left_restart"], item["right_restart"])
            for item in shared_matches
            if item["component"] == component
        }
        left_restarts = {pair[0] for pair in pairs}
        right_restarts = {pair[1] for pair in pairs}
        if len(pairs) >= 2 and len(left_restarts) >= 2 and len(right_restarts) >= 2:
            stable_components.append(component)
            stable_component_pairs[component] = pairs
    stable_restart_pairs = set().union(*stable_component_pairs.values()) if stable_component_pairs else set()
    stable_matches = [
        item for item in shared_matches if item["component"] in stable_components
    ]
    shared_count = len(stable_matches)
    signal = classify_route_c_signal(
        records,
        shared_slow_direction_count=shared_count,
    )
    aggregate_256_authorized = all(
        records[label].get("conditional_256_authorized") is True for label in labels
    )
    aggregate_256_completed = all(
        records[label].get("conditional_256_completed") is True for label in labels
    )
    direction_audit_gate = {
        "interface_projection_observed": bool(projection_audit_observations),
        "basis_persistence_observed": bool(persistence_audit_observations),
        "canonical_interface_trace_observed": bool(interface_trace_observations),
        "interface_projection_all_pass": bool(projection_audit_observations)
        and all(projection_audit_observations),
        "basis_persistence_all_pass": bool(persistence_audit_observations)
        and all(persistence_audit_observations),
        "canonical_interface_trace_all_pass": bool(interface_trace_observations)
        and all(interface_trace_observations),
        "replicated": bool(basis_replication_observations)
        and any(basis_replication_observations),
    }
    direction_audit_gate["pass"] = bool(
        direction_audit_gate["interface_projection_observed"]
        and direction_audit_gate["basis_persistence_observed"]
        and direction_audit_gate["canonical_interface_trace_observed"]
        and direction_audit_gate["interface_projection_all_pass"]
        and direction_audit_gate["basis_persistence_all_pass"]
        and direction_audit_gate["canonical_interface_trace_all_pass"]
        and direction_audit_gate["replicated"] is False
    )
    return {
        "schema": "task040.v5.route_c.online_long_fgmres.v1",
        "labels": list(labels),
        "restart": ROUTE_C_RESTART,
        "continuous_right_fgmres": True,
        "checkpoints": list(ROUTE_C_CHECKPOINTS),
        "conditional_checkpoint": ROUTE_C_CONDITIONAL_CHECKPOINT,
        "max_harmonic_ritz_directions_per_restart": ROUTE_C_MAX_RITZ_VALUES,
        "records": records,
        "direction_records": direction_records,
        "shared_slow_directions": {
            "count": int(shared_count),
            "stable_restart_pair_count": len(stable_restart_pairs),
            "stable_components": stable_components,
            "stable_component_restart_pairs": {
                component: [list(pair) for pair in sorted(pairs)]
                for component, pairs in stable_component_pairs.items()
            },
            "threshold": ROUTE_C_SHARED_DIRECTION_THRESHOLD,
            "matches": shared_matches,
            "stability_rule": (
                "at_least_two_distinct_restart_pairs_and_two_restarts_per_source"
            ),
            "direction_space": "preconditioned_response_direction_Z_y",
            "interface_trace": "canonical_interface_response_trace",
        },
        "direction_audit_gate": direction_audit_gate,
        "signal": signal,
        "conditional_256_gate": {
            "per_source": {
                label: {
                    "authorized": bool(
                        records[label].get("conditional_256_authorized")
                    ),
                    "final_iteration": int(records[label]["final_iteration"]),
                    "completed": bool(
                        records[label].get("conditional_256_completed")
                    ),
                }
                for label in labels
            },
            "authorized_pass": aggregate_256_authorized,
            "aggregate_pass": aggregate_256_completed,
            "aggregate_completed": aggregate_256_completed,
        },
        "right_preconditioner": {
            "identity_test_only": identity_test_only,
            "kind": type(action).__name__,
        },
        "setup_count": 1,
        "pc_setup_count": 1,
        "continuous_source_solve_count": len(labels),
        "right_pc_apply_count": int(total_apply_count),
        "restart_count": int(total_restart_count),
        "numeric_collective_inventory": {
            "fe_sized_numeric_allgather_count": int(numeric_allgather_count),
            "control_metadata_collective_count": int(
                callback_collective_count + resource_collective_count
            ),
            "owner_row_direction_callbacks": sum(
                sum(item["direction_count"] for item in entries)
                for entries in direction_records.values()
            ),
            "callback_collective_count": int(callback_collective_count),
            "owner_row_basis_replication_observed": bool(
                basis_replication_observations
            ),
            "owner_row_basis_replicated": (
                any(basis_replication_observations)
                if basis_replication_observations
                else None
            ),
        },
        "wall_seconds": float(time.perf_counter() - started),
        "research_only": True,
        "exact_output_vectors_consumed": 0,
        "full_side_exact_factor_count": 0,
        "global_direct_factor_count": 0,
    }
