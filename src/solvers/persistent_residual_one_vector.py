"""Fixed one-vector persistent-residual coarse diagnostic.

This module deliberately contains no PETSc, DOLFINx, mesh, or physical-form
construction.  The caller supplies the already qualified B0 and physical
actions.  The carrier owns only ``q``, one B0 preimage, and its physical image;
the measurement reads residuals in fixed blocks and retains scalar evidence.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
import math
from typing import Any

import numpy as np

__all__ = (
    "W11A_SCHEMA",
    "W11B_SCHEMA",
    "W11A_Q_RHO_LIMIT",
    "W11A_TARGET_RHO_LIMIT",
    "W11A_B0_20_RESIDUAL_LIMIT",
    "W11A_B0_100_RESIDUAL_LIMIT",
    "W11A_RETAINED_PAYLOAD_LIMIT_BYTES",
    "W11A_PREDICTED_LIVE_SET_LIMIT_BYTES",
    "OneVectorCoarseCarrier",
    "measure_rank_one_projection",
    "repeat_rank_one_projection",
    "run_persistent_residual_diagnostic",
    "run_w11b_fixed_200_exact_proxy",
    "validate_w11a_authorities",
    "validate_w11a_architecture",
)


W11A_SCHEMA = "task037.extra.h2b.w11a.persistent-residual-one-vector.v1"
W11B_SCHEMA = "task037.extra.h2b.w11b.fixed-200-exact-proxy.v1"
W11A_Q_RHO_LIMIT = 0.70
W11A_TARGET_RHO_LIMIT = 0.90
W11A_B0_20_RESIDUAL_LIMIT = 1.0e-3
W11A_B0_100_RESIDUAL_LIMIT = 1.0e-8
W11A_RETAINED_PAYLOAD_LIMIT_BYTES = 16 * 1024 * 1024
W11A_PREDICTED_LIVE_SET_LIMIT_BYTES = 1_500_000_000
_DEFAULT_BLOCK_SIZE = 4096
_TINY = np.finfo(float).tiny


def _vector(value: Any, name: str, *, size: int | None = None) -> np.ndarray:
    array = np.asarray(value)
    if (
        array.dtype != np.dtype(np.complex128)
        or array.ndim != 1
        or not array.flags.c_contiguous
        or (size is not None and array.size != size)
        or not np.all(np.isfinite(array))
    ):
        raise ValueError(f"W11A {name} must be a finite C-contiguous complex128 vector")
    return array


def _block_size(value: Any) -> int:
    if type(value) is not int or value <= 0:
        raise ValueError("W11A block size must be a positive integer")
    return value


def _relative(value: float, scale: float) -> float:
    return float(value / max(scale, _TINY))


def measure_rank_one_projection(
    residual: np.ndarray,
    direction: np.ndarray,
    *,
    block_size: int = _DEFAULT_BLOCK_SIZE,
) -> dict[str, Any]:
    """Measure the direct least-residual correction ``r-alpha*p`` in blocks.

    The coefficient uses ``np.vdot(p, r)``.  A second pass computes the direct
    residual norm and projection orthogonality; no corrected full vector is
    retained.  The returned ``normal_closure`` is the scale-free identity
    ``|<p,r>-alpha<p,p>|/max(|<p,r>|, |alpha<p,p>|, tiny)``.
    """

    r = _vector(residual, "residual")
    p = _vector(direction, "direction", size=r.size)
    step = _block_size(block_size)
    denominator = 0.0 + 0.0j
    numerator = 0.0 + 0.0j
    residual_norm_squared = float(np.vdot(r, r).real)
    direction_norm_squared = float(np.vdot(p, p).real)
    for start in range(0, r.size, step):
        stop = min(start + step, r.size)
        p_block = p[start:stop]
        r_block = r[start:stop]
        denominator += np.vdot(p_block, p_block)
        numerator += np.vdot(p_block, r_block)
    if (
        not math.isfinite(denominator.real)
        or not math.isfinite(denominator.imag)
        or abs(denominator.imag) > 1.0e-13 * max(1.0, abs(denominator.real))
        or denominator.real <= _TINY
        or not math.isfinite(numerator.real)
        or not math.isfinite(numerator.imag)
        or not math.isfinite(residual_norm_squared)
        or not math.isfinite(direction_norm_squared)
        or residual_norm_squared <= _TINY
    ):
        raise ValueError("W11A rank-one denominator or vector norm is invalid")
    alpha = numerator / denominator
    remainder_norm_squared = 0.0
    direction_remainder = 0.0 + 0.0j
    for start in range(0, r.size, step):
        stop = min(start + step, r.size)
        remainder = r[start:stop] - alpha * p[start:stop]
        remainder_norm_squared += float(np.vdot(remainder, remainder).real)
        direction_remainder += np.vdot(p[start:stop], remainder)
    if not (
        math.isfinite(remainder_norm_squared)
        and remainder_norm_squared >= -1.0e-12 * max(1.0, residual_norm_squared)
        and np.isfinite(direction_remainder.real)
        and np.isfinite(direction_remainder.imag)
    ):
        raise FloatingPointError("W11A direct residual is non-finite")
    remainder_norm_squared = max(remainder_norm_squared, 0.0)
    rho = math.sqrt(remainder_norm_squared / residual_norm_squared)
    orthogonality = _relative(
        abs(direction_remainder),
        math.sqrt(direction_norm_squared * max(remainder_norm_squared, _TINY)),
    )
    normal_closure = _relative(
        abs(numerator - alpha * denominator),
        max(abs(numerator), abs(alpha * denominator)),
    )
    values = (alpha, denominator, numerator, rho, orthogonality, normal_closure)
    if not all(np.isfinite(value.real) and np.isfinite(value.imag) for value in values[:3]):
        raise FloatingPointError("W11A rank-one scalar evidence is non-finite")
    if not all(math.isfinite(float(value)) for value in values[3:]):
        raise FloatingPointError("W11A rank-one measurement is non-finite")
    return {
        "schema": W11A_SCHEMA,
        "alpha": [float(alpha.real), float(alpha.imag)],
        "denominator": float(denominator.real),
        "numerator": [float(numerator.real), float(numerator.imag)],
        "residual_norm": math.sqrt(residual_norm_squared),
        "corrected_residual_norm": math.sqrt(remainder_norm_squared),
        "rho": float(rho),
        "projection_orthogonality": float(orthogonality),
        "normal_closure": float(normal_closure),
        "finite": True,
        "block_size": step,
        "block_count": int((r.size + step - 1) // step),
    }


def repeat_rank_one_projection(
    residual: np.ndarray,
    direction: np.ndarray,
    *,
    block_size: int = _DEFAULT_BLOCK_SIZE,
    schema: str = W11A_SCHEMA,
) -> dict[str, Any]:
    """Run the fixed direct measurement twice and retain scalar repeat evidence."""

    first = measure_rank_one_projection(residual, direction, block_size=block_size)
    second = measure_rank_one_projection(residual, direction, block_size=block_size)
    repeat_exact = bool(first == second)
    result = dict(first)
    result["repeat"] = {
        "rho": second["rho"],
        "alpha": list(second["alpha"]),
        "normal_closure": second["normal_closure"],
        "projection_orthogonality": second["projection_orthogonality"],
        "repeat_exact": repeat_exact,
        "passes": 2,
    }
    result["repeat_exact"] = repeat_exact
    if schema != W11A_SCHEMA:
        result["schema"] = schema
    return result


class OneVectorCoarseCarrier:
    """A retained ``q -> z -> p`` one-vector coarse carrier."""

    def __init__(
        self,
        q: np.ndarray,
        preimage: np.ndarray,
        image: np.ndarray,
        *,
        level: str,
        counters: Mapping[str, Any],
        architecture: Mapping[str, Any],
        predicted_live_set_bytes: int,
        block_size: int = _DEFAULT_BLOCK_SIZE,
        schema: str = W11A_SCHEMA,
    ) -> None:
        self.q = _vector(q, "q")
        self.preimage = _vector(preimage, "preimage", size=self.q.size)
        self.image = _vector(image, "physical image", size=self.q.size)
        if level not in {"Q0", "Q1_20", "Q1_100", "Q1_200"}:
            raise ValueError("W11A carrier level is not fixed")
        if type(predicted_live_set_bytes) is not int or predicted_live_set_bytes < 0:
            raise ValueError("W11A predicted live set is invalid")
        payload = int(self.q.nbytes + self.preimage.nbytes + self.image.nbytes)
        if payload > W11A_RETAINED_PAYLOAD_LIMIT_BYTES:
            raise ValueError("W11A one-vector retained payload exceeds the gate")
        if not validate_w11a_architecture(architecture):
            raise ValueError("W11A physical architecture is not closed")
        self.level = level
        self.counters = dict(counters)
        self.architecture = dict(architecture)
        self.predicted_live_set_bytes = predicted_live_set_bytes
        self.block_size = _block_size(block_size)
        self.schema = schema
        self._audit = {
            "schema": schema,
            "level": level,
            "rows": int(self.q.size),
            "retained_payload_bytes": payload,
            "retained_payload_limit_bytes": W11A_RETAINED_PAYLOAD_LIMIT_BYTES,
            "dense_global_matrix_materialized": False,
            "physical_ksp_calls": 0,
            "pde_calls": 0,
            "block_size": self.block_size,
            "predicted_live_set_bytes": predicted_live_set_bytes,
            "predicted_live_set_limit_bytes": W11A_PREDICTED_LIVE_SET_LIMIT_BYTES,
            "derived_not_measured": True,
        }

    @property
    def audit(self) -> dict[str, Any]:
        return {**self._audit, "counters": dict(self.counters), "architecture": dict(self.architecture)}

    def measure(self, target: np.ndarray) -> dict[str, Any]:
        target_value = _vector(target, "target", size=self.q.size)
        q_measurement = repeat_rank_one_projection(
            self.q, self.image, block_size=self.block_size, schema=self.schema
        )
        target_measurement = repeat_rank_one_projection(
            target_value, self.image, block_size=self.block_size, schema=self.schema
        )
        return {
            "q": q_measurement,
            "target": target_measurement,
            "finite": bool(q_measurement["finite"] and target_measurement["finite"]),
            "repeat_exact": bool(
                q_measurement["repeat_exact"] and target_measurement["repeat_exact"]
            ),
        }


def validate_w11a_architecture(value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    required_false = (
        "global_matrix_materialized",
        "augmented_matrix_materialized",
        "condensation",
        "static_condensed_operator_used",
        "trace_slab_pc_used",
        "physical_ksp_used",
        "pde_used",
    )
    return bool(
        value.get("fine_space") == "uncondensed_fullspace"
        and all(key in value and value[key] is False for key in required_false)
    )


def validate_w11a_authorities(value: Any) -> bool:
    """Validate the small identity record before any action is called."""

    if not isinstance(value, Mapping):
        return False
    required = ("source_sha", "q", "target", "m3y", "m6a", "layout", "mpc")
    if any(key not in value or not isinstance(value[key], Mapping) for key in required[1:]):
        return False
    source = value.get("source_sha")
    if not isinstance(source, str) or len(source) != 40 or any(c not in "0123456789abcdef" for c in source):
        return False
    q = value["q"]
    target = value["target"]
    vector_fields = ("rows", "shape", "dtype", "array_sha256", "file_sha256")
    if not all(field in q and field in target for field in vector_fields):
        return False
    if q["rows"] != target["rows"] or q["shape"] != target["shape"] or q["dtype"] != "complex128":
        return False
    if any(not isinstance(item, str) or len(item) != 64 for item in (q["array_sha256"], q["file_sha256"], target["array_sha256"], target["file_sha256"])):
        return False
    m3y = value["m3y"]
    m6a = value["m6a"]
    if not all(isinstance(m3y.get(key), str) and len(m3y[key]) == 64 for key in ("manifest_sha256", "evidence_sha256")):
        return False
    if not isinstance(m3y.get("source_sha256"), str) or len(m3y["source_sha256"]) != 40:
        return False
    if not isinstance(m6a.get("source_sha256"), str) or len(m6a["source_sha256"]) != 40:
        return False
    return bool(
        value["layout"] == {"rows": q["rows"], "dtype": "complex128", "mpi_size": 1}
        and value["mpc"] == {"owner_local": True, "homogenized": True, "packing": "fullspace_mpc"}
    )


def _b0_gate(value: Mapping[str, Any], limit: float) -> bool:
    residual = value.get("true_residual")
    return isinstance(residual, (int, float)) and math.isfinite(float(residual)) and 0.0 <= float(residual) <= limit


def _projection_gate(value: Mapping[str, Any]) -> bool:
    rho = value.get("rho")
    orthogonality = value.get("projection_orthogonality")
    closure = value.get("normal_closure")
    if not all(
        isinstance(item, (int, float)) and math.isfinite(float(item))
        for item in (rho, orthogonality, closure)
    ):
        return False
    return bool(
        value.get("finite") is True
        and value.get("repeat_exact") is True
        and float(orthogonality) <= 1.0e-11
        and float(closure) <= 1.0e-11
    )


def run_persistent_residual_diagnostic(
    q: np.ndarray,
    target: np.ndarray,
    *,
    b0_apply: Callable[[np.ndarray], np.ndarray],
    physical_action: Callable[[np.ndarray], np.ndarray],
    b0_solve: Callable[[int], Mapping[str, Any]],
    architecture: Mapping[str, Any],
    predicted_live_set_bytes: int,
    counters: Mapping[str, Any] | None = None,
    block_size: int = _DEFAULT_BLOCK_SIZE,
) -> dict[str, Any]:
    """Run fixed Q0, then Q1-20 and only-on-failure Q1-100 selection."""

    q_value = _vector(q, "q")
    target_value = _vector(target, "target", size=q_value.size)
    base_counters = dict(counters or {})
    z0 = _vector(b0_apply(q_value), "Q0 preimage", size=q_value.size)
    p0 = _vector(physical_action(z0), "Q0 physical image", size=q_value.size)
    q0_carrier = OneVectorCoarseCarrier(
        q_value,
        z0,
        p0,
        level="Q0",
        counters={
            **base_counters,
            "q0_b0_pc_apply_count": 1,
            "q0_physical_action_count": 1,
            "physical_action_count": 1,
        },
        architecture=architecture,
        predicted_live_set_bytes=predicted_live_set_bytes,
        block_size=block_size,
    )
    q0 = q0_carrier.measure(target_value)
    q0_pass = bool(
        _projection_gate(q0["q"])
        and _projection_gate(q0["target"])
        and q0["q"]["rho"] <= W11A_Q_RHO_LIMIT
        and q0["target"]["rho"] <= W11A_TARGET_RHO_LIMIT
    )
    selected: OneVectorCoarseCarrier | None = q0_carrier
    q1: dict[str, Any] = {"status": "not_run_gate_satisfied"} if q0_pass else {"status": "required"}
    q0_projection_pass = q0_pass
    if not q0_pass:
        selected = None
        del q0_carrier, z0, p0
        solve20 = dict(b0_solve(20))
        q1["solve20"] = {key: value for key, value in solve20.items() if key != "solution"}
        if _b0_gate(solve20, W11A_B0_20_RESIDUAL_LIMIT):
            chosen = solve20
            level = "Q1_20"
        else:
            solve100 = dict(b0_solve(100))
            q1["solve100"] = {key: value for key, value in solve100.items() if key != "solution"}
            if not _b0_gate(solve100, W11A_B0_100_RESIDUAL_LIMIT):
                return {
                    "schema": W11A_SCHEMA,
                    "status": "gate_failed",
                    "classification": "W11A_PERSISTENT_DIRECTION_FAIL",
                    "selected_level": None,
                    "q0": q0,
                    "q1": q1,
                    "checks": {"b0_solve": False, "q_projection": False, "target_projection": False},
                    "problems": ["b0_solve_residual"],
                    "formal_pass": False,
                    "pde_pass": False,
                    "official_rta": False,
                }
            chosen = solve100
            level = "Q1_100"
        z = _vector(chosen.get("solution"), f"{level} preimage", size=q_value.size)
        p = _vector(physical_action(z), f"{level} physical image", size=q_value.size)
        selected = OneVectorCoarseCarrier(
            q_value,
            z,
            p,
            level=level,
            counters={
                **base_counters,
                "q0_b0_pc_apply_count": 1,
                "q0_physical_action_count": 1,
                "q1_b0_solve_max_it": int(level.split("_")[1]),
                "q1_physical_action_count": 1,
                "physical_action_count": 2,
            },
            architecture=architecture,
            predicted_live_set_bytes=predicted_live_set_bytes,
            block_size=block_size,
        )
    if selected is None:
        raise RuntimeError("W11A selected carrier was not constructed")
    measurement = q0 if selected.level == "Q0" else selected.measure(target_value)
    checks = {
        "b0_solve": q0_pass or selected.level in {"Q1_20", "Q1_100"},
        "q_projection": _projection_gate(measurement["q"]) and measurement["q"]["rho"] <= W11A_Q_RHO_LIMIT,
        "target_projection": _projection_gate(measurement["target"]) and measurement["target"]["rho"] <= W11A_TARGET_RHO_LIMIT,
        "finite_deterministic": measurement["finite"] and measurement["repeat_exact"],
        "architecture": validate_w11a_architecture(architecture),
        "payload": selected.audit["retained_payload_bytes"] <= W11A_RETAINED_PAYLOAD_LIMIT_BYTES,
        "predicted_live_set": predicted_live_set_bytes <= W11A_PREDICTED_LIVE_SET_LIMIT_BYTES,
    }
    problems = sorted(name for name, passed in checks.items() if not passed)
    return {
        "schema": W11A_SCHEMA,
        "status": "diagnostic_complete" if not problems else "gate_failed",
        "classification": "W11A_QUALIFIED" if not problems else "W11A_PERSISTENT_DIRECTION_FAIL",
        "selected_level": selected.level,
        "q0": q0,
        "q1": q1,
        "q0_projection_gate": q0_projection_pass,
        "measurement": measurement,
        "carrier_audit": selected.audit,
        "checks": checks,
        "problems": problems,
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
    }


def run_w11b_fixed_200_exact_proxy(
    q: np.ndarray,
    target: np.ndarray,
    *,
    b0_solve: Callable[[], Mapping[str, Any]],
    physical_action: Callable[[np.ndarray], np.ndarray],
    architecture: Mapping[str, Any],
    predicted_live_set_bytes: int,
    counters: Mapping[str, Any] | None = None,
    block_size: int = _DEFAULT_BLOCK_SIZE,
) -> dict[str, Any]:
    """Run the single fixed-200 W11B B0 solve and exact proxy measurement.

    The callback must perform the zero-start right-FGMRES solve with the
    fixed restart-20/max-it-200 contract.  The physical callback is reached
    only after its explicit true residual passes ``1e-8``.
    """

    q_value = _vector(q, "q")
    target_value = _vector(target, "target", size=q_value.size)
    solve = dict(b0_solve())
    solve_evidence = {key: value for key, value in solve.items() if key != "solution"}
    fixed_contract = (
        solve.get("max_it") == 200
        and solve.get("ksp_type") == "fgmres"
        and solve.get("initial_solution") == "zero_start"
        and solve.get("iterations") == 200
        and solve.get("converged_reason") == -3
        and solve.get("pc_apply_count") == 200
        and solve.get("restart") == 20
        and solve.get("pc_side") == "right"
        and solve.get("norm_type") == "unpreconditioned"
        and solve.get("rtol") == 0.0
        and solve.get("atol") == 0.0
        and solve.get("finite") is True
    )
    b0_pass = fixed_contract and _b0_gate(solve, W11A_B0_100_RESIDUAL_LIMIT)
    if not b0_pass:
        failed = {
            "b0_configuration": fixed_contract,
            "b0_solve": _b0_gate(solve, W11A_B0_100_RESIDUAL_LIMIT),
        }
        return {
            "schema": W11B_SCHEMA,
            "status": "gate_failed",
            "classification": "W11B_B0_SOLVE_FAIL",
            "selected_level": None,
            "b0": {"solve200": solve_evidence},
            "checks": failed,
            "problems": [name for name, passed in failed.items() if not passed],
            "formal_pass": False,
            "pde_pass": False,
            "official_rta": False,
        }
    z = _vector(solve.get("solution"), "Q1_200 preimage", size=q_value.size)
    p = _vector(physical_action(z), "Q1_200 physical image", size=q_value.size)
    base_counters = dict(counters or {})
    carrier = OneVectorCoarseCarrier(
        q_value,
        z,
        p,
        level="Q1_200",
        counters={
            **base_counters,
            "b0_solve_max_it": 200,
            "q1_physical_action_count": 1,
            "physical_action_count": 1,
        },
        architecture=architecture,
        predicted_live_set_bytes=predicted_live_set_bytes,
        block_size=block_size,
        schema=W11B_SCHEMA,
    )
    measurement = carrier.measure(target_value)
    checks = {
        "b0_configuration": True,
        "b0_solve": True,
        "q_projection": (
            _projection_gate(measurement["q"])
            and measurement["q"]["rho"] <= W11A_Q_RHO_LIMIT
        ),
        "target_projection": (
            _projection_gate(measurement["target"])
            and measurement["target"]["rho"] <= W11A_TARGET_RHO_LIMIT
        ),
        "finite_deterministic": measurement["finite"] and measurement["repeat_exact"],
        "architecture": validate_w11a_architecture(architecture),
        "payload": carrier.audit["retained_payload_bytes"] <= W11A_RETAINED_PAYLOAD_LIMIT_BYTES,
        "predicted_live_set": predicted_live_set_bytes <= W11A_PREDICTED_LIVE_SET_LIMIT_BYTES,
    }
    problems = sorted(name for name, passed in checks.items() if not passed)
    passed = not problems
    result = {
        "schema": W11B_SCHEMA,
        "status": "diagnostic_complete" if passed else "gate_failed",
        "classification": "W11B_PASS" if passed else "W11B_PROJECTION_FAIL",
        "selected_level": "Q1_200" if passed else None,
        "candidate_level": "Q1_200",
        "b0": {"solve200": solve_evidence},
        "measurement": measurement,
        "carrier_audit": carrier.audit,
        "checks": checks,
        "problems": problems,
        "formal_pass": False,
        "pde_pass": False,
        "official_rta": False,
    }
    if passed:
        result["_candidate_vectors"] = {"preimage": z, "physical_image": p}
    return result
