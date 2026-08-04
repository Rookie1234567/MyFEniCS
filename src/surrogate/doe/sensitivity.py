"""Central finite-difference records and Task005 measurement contracts."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Iterable

import numpy as np

from .design import (
    ANGLE_CANDIDATES, AUDIT_ANGLE_IDS, H0, W0, FORWARD_SOLVER_SHA,
    MODEL_ID, ROUTE_ID, OBSERVABLE_SCHEMA, canonical_hash,
)


STEPS = {
    "coarse": {"delta_h_nm": 2.5, "delta_w_nm": 0.5},
    "half": {"delta_h_nm": 1.25, "delta_w_nm": 0.25},
}
STATES = ("H-", "H+", "W-", "W+")
CONTRACTS = ("M0_aggregate_RT", "M1_order_total_robust", "M2_order_total_extended")
NOISES = ("N1", "N2")
SCALE = {"h": 5.0, "w": 1.0}


def _as_record(value: Path | dict[str, Any]) -> dict[str, Any]:
    if isinstance(value, Path):
        return json.loads(value.read_text())
    return value


def record_passes(record: dict[str, Any]) -> bool:
    """Recheck the explicit formal status/gates before using a record."""

    if record.get("status") != "measured_pass":
        return False
    numerical = record.get("numerical_gates", {})
    resources = record.get("resource_gates", {})
    if numerical and not all(bool(value) for value in numerical.values()):
        return False
    if resources and not all(bool(value) for value in resources.values()):
        return False
    if record.get("source_sha") != FORWARD_SOLVER_SHA or record.get("source_dirty") is not False:
        return False
    if record.get("model_id") != MODEL_ID or record.get("solver_route_id") != ROUTE_ID:
        return False
    if record.get("observable_schema_version") != OBSERVABLE_SCHEMA:
        return False
    inputs = record.get("inputs", [])
    # M1 records are the four permitted geometry perturbations, not nominal
    # rows.  Their geometry must remain inside the reviewed Task002 domain;
    # the nominal center is checked separately by the reuse report.
    return bool(
        len(inputs) == 4 and 115.0 <= float(inputs[0]) <= 125.0
        and 16.0 <= float(inputs[1]) <= 18.0
        and 0.5 <= float(inputs[2]) <= 10.0
        and 0.0 <= float(inputs[3]) <= 90.0
    )


def _order_identity(record: dict[str, Any]) -> list[tuple[str, int, int]]:
    return [(str(order.get("side")), int(order.get("m")), int(order.get("n", 0)))
            for order in record.get("mother_response", {}).get("orders", [])]


def _order_power_vector(record: dict[str, Any]) -> tuple[list[tuple[str, int, int]], np.ndarray,
                                                         np.ndarray, np.ndarray]:
    orders = record.get("mother_response", {}).get("orders", [])
    identity = _order_identity(record)
    values = np.full(len(orders), np.nan, dtype=np.float64)
    s_values = np.full(len(orders), np.nan, dtype=np.float64)
    p_values = np.full(len(orders), np.nan, dtype=np.float64)
    for index, order in enumerate(orders):
        if not bool(order.get("power_carrying", False)):
            continue
        total = order.get("order_total_power")
        values[index] = float(total) if total is not None else np.nan
        components = order.get("components", {})
        for key, target in (("s", s_values), ("p", p_values)):
            value = components.get(key, {}).get("power")
            if value is not None and bool(components.get(key, {}).get("power_carrying", False)):
                target[index] = float(value)
    return identity, values, s_values, p_values


def record_observables(record: dict[str, Any]) -> dict[str, Any]:
    """Extract only the declared power observables, never amplitude/phase."""

    aggregates = record.get("aggregates", {})
    aggregate = np.asarray([float(aggregates["R_total"]), float(aggregates["T_total"])], dtype=np.float64)
    identity, total, s_power, p_power = _order_power_vector(record)
    return {
        "aggregate_RT": aggregate,
        "order_identity": identity,
        "order_total": total,
        "order_s": s_power,
        "order_p": p_power,
    }


def noise_sigma(y: np.ndarray, scenario: str) -> np.ndarray:
    y = np.asarray(y, dtype=np.float64)
    if scenario == "N1":
        return np.sqrt((0.01 * np.abs(y)) ** 2 + 1.0e-4 ** 2)
    if scenario == "N2":
        return np.sqrt((0.02 * np.abs(y)) ** 2 + 5.0e-4 ** 2)
    raise ValueError(f"unknown provisional noise scenario: {scenario}")


def _active_channels(nominal: np.ndarray, states: Iterable[np.ndarray], threshold: float) -> np.ndarray:
    stack = np.vstack([np.asarray(nominal, dtype=np.float64)] + [np.asarray(row) for row in states])
    finite = np.all(np.isfinite(stack), axis=0)
    return finite & (np.max(np.abs(stack), axis=0) >= threshold)


def contract_vector(record: dict[str, Any], contract: str,
                    *, active: np.ndarray | None = None) -> tuple[np.ndarray, list[Any]]:
    values = record_observables(record)
    if contract == "M0_aggregate_RT":
        return values["aggregate_RT"], ["R_total", "T_total"]
    if contract in {"M1_order_total_robust", "M2_order_total_extended"}:
        vector = values["order_total"]
        if active is None:
            threshold = 1.0e-3 if contract == "M1_order_total_robust" else 1.0e-5
            active = np.isfinite(vector) & (np.abs(vector) >= threshold)
        return vector[active], [values["order_identity"][index] for index in np.flatnonzero(active)]
    raise ValueError(f"unsupported formal contract: {contract}")


def _common_order_active(records: Iterable[dict[str, Any]], contract: str) -> np.ndarray:
    recs = list(records)
    if not recs:
        raise ValueError("cannot identify channels from empty records")
    identity, *_ = _order_power_vector(recs[0])
    for record in recs[1:]:
        if _order_identity(record) != identity:
            raise ValueError("order identity changed between nominal and perturbation records")
    vectors = [_order_power_vector(record)[1] for record in recs]
    threshold = 1.0e-3 if contract == "M1_order_total_robust" else 1.0e-5
    return _active_channels(vectors[0], vectors[1:], threshold)


def central_difference(nominal: dict[str, Any], minus: dict[str, Any], plus: dict[str, Any],
                      contract: str, parameter: str, *, active: np.ndarray | None = None) -> dict[str, Any]:
    if parameter not in {"h", "w"}:
        raise ValueError(parameter)
    delta_key = "delta_h_nm" if parameter == "h" else "delta_w_nm"
    # The caller places delta in a private field, keeping this function pure
    # with respect to the immutable perturbation schema.
    delta = float(plus["_task005_delta"][delta_key])
    if active is None and contract != "M0_aggregate_RT":
        active = _common_order_active([nominal, minus, plus], contract)
    y_minus, channels = contract_vector(minus, contract, active=active)
    y_plus, channels_plus = contract_vector(plus, contract, active=active)
    if channels != channels_plus:
        raise ValueError("channel identity changed across central-difference pair")
    derivative = (y_plus - y_minus) / (2.0 * delta)
    return {"derivative": derivative, "channels": channels,
            "delta_nm": delta, "active_mask": active.tolist() if active is not None else None}


def _attach_delta(record: dict[str, Any], step: str) -> dict[str, Any]:
    value = dict(record)
    value["_task005_delta"] = STEPS[step]
    return value


def _metric(coarse: np.ndarray, half: np.ndarray, sigma: np.ndarray,
            *, scale: float) -> dict[str, Any]:
    wc = coarse * scale / sigma
    wh = half * scale / sigma
    nc = float(np.linalg.norm(wc)); nh = float(np.linalg.norm(wh))
    if nc == 0.0 or nh == 0.0:
        cosine = 0.0
        relative = float("inf")
    else:
        cosine = float(np.dot(wc, wh) / (nc * nh))
        relative = float(np.linalg.norm(wh - wc) / nc)
    count = max(1, int(math.ceil(len(wc) * 0.2)))
    ranking = np.argsort(-np.abs(wc), kind="stable")[:count]
    signs = np.sign(wc[ranking]) * np.sign(wh[ranking])
    signs = signs[np.isfinite(signs)]
    sign_agreement = float(np.mean(signs > 0.0)) if len(signs) else 0.0
    return {
        "whitened_norm_coarse": nc, "whitened_norm_half": nh,
        "whitened_cosine": cosine, "relative_l2_difference": relative,
        "top_snr_count": int(count), "top_snr_sign_agreement": sign_agreement,
        "signal_floor_pass": bool(nh >= 1.0),
        "gate": bool(cosine >= 0.98 and relative <= 0.20 and sign_agreement >= 0.80),
    }


def build_step_audit(*, nominal_by_angle: dict[str, dict[str, Any]],
                     records_by_key: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Compute M0/M1 step comparisons from fresh-process formal records."""

    audit: dict[str, Any] = {
        "schema_version": "task005.finite-difference-step-audit.v1",
        "forward_solver_sha": FORWARD_SOLVER_SHA, "model_id": MODEL_ID,
        "solver_route_id": ROUTE_ID, "audit_angle_ids": list(AUDIT_ANGLE_IDS),
        "steps": STEPS, "noise_scenarios": list(NOISES),
        "contracts": list(CONTRACTS), "records": {}, "comparisons": {},
        "status": "pending",
    }
    failures: list[str] = []
    all_pass_records = True
    for angle_id in AUDIT_ANGLE_IDS:
        nominal = nominal_by_angle[angle_id]
        row_key = f"{angle_id}/coarse"
        step_states: dict[str, dict[str, dict[str, Any]]] = {}
        for step in STEPS:
            step_states[step] = {}
            for state in STATES:
                key = f"{angle_id}/{step}/{state}"
                record = records_by_key[key]
                passed = record_passes(record)
                all_pass_records = all_pass_records and passed
                step_states[step][state] = record
                audit["records"][key] = {
                    "status": record.get("status"), "record_passes": passed,
                    "source_sha": record.get("source_sha"),
                    "formal_record_sha256": record.get("formal_record_sha256"),
                    "execution_sha256": record.get("execution_sha256"),
                    "inputs": record.get("inputs"),
                }
                if not passed:
                    failures.append(f"record_gate:{key}")
        all_records = [nominal] + [step_states[step][state] for step in STEPS for state in STATES]
        for contract in ("M0_aggregate_RT", "M1_order_total_robust"):
            active = None if contract == "M0_aggregate_RT" else _common_order_active(all_records, contract)
            vectors: dict[str, dict[str, np.ndarray]] = {}
            for step in STEPS:
                vectors[step] = {}
                for parameter, minus_state, plus_state in (
                    ("h", "H-", "H+"), ("w", "W-", "W+")):
                    value = central_difference(
                        _attach_delta(nominal, step),
                        _attach_delta(step_states[step][minus_state], step),
                        _attach_delta(step_states[step][plus_state], step),
                        contract, parameter, active=active,
                    )
                    vectors[step][parameter] = value["derivative"]
                    if angle_id not in audit["comparisons"]:
                        audit["comparisons"][angle_id] = {}
                    audit["comparisons"][angle_id].setdefault(contract, {})
                    audit["comparisons"][angle_id][contract].setdefault("channels", value["channels"])
            for parameter in ("h", "w"):
                nominal_vector, _ = contract_vector(nominal, contract, active=active)
                for noise in NOISES:
                    metric = _metric(vectors["coarse"][parameter], vectors["half"][parameter],
                                     noise_sigma(nominal_vector, noise), scale=SCALE[parameter])
                    metric["noise"] = noise
                    metric["parameter"] = parameter
                    audit["comparisons"][angle_id][contract].setdefault(parameter, {})[noise] = metric
                    # The M1 decision is made under N1; N2 is diagnostic.
                    if noise == "N1" and not metric["gate"]:
                        failures.append(f"step_gate:{angle_id}:{contract}:{parameter}")
        # Preserve a Richardson diagnostic for reviewers; it is not a production derivative.
        audit["comparisons"][angle_id]["richardson_diagnostic"] = {}
        for parameter, minus_state, plus_state in (("h", "H-", "H+"), ("w", "W-", "W+")):
            for contract in ("M0_aggregate_RT", "M1_order_total_robust"):
                active = None if contract == "M0_aggregate_RT" else _common_order_active(all_records, contract)
                c = central_difference(_attach_delta(nominal, "coarse"),
                                       _attach_delta(step_states["coarse"][minus_state], "coarse"),
                                       _attach_delta(step_states["coarse"][plus_state], "coarse"),
                                       contract, parameter, active=active)["derivative"]
                h = central_difference(_attach_delta(nominal, "half"),
                                       _attach_delta(step_states["half"][minus_state], "half"),
                                       _attach_delta(step_states["half"][plus_state], "half"),
                                       contract, parameter, active=active)["derivative"]
                audit["comparisons"][angle_id]["richardson_diagnostic"][f"{contract}:{parameter}"] = ((4.0 * h - c) / 3.0).tolist()
    audit["record_gate_pass"] = bool(all_pass_records)
    audit["failure_reasons"] = failures
    angle_gate = {}
    for contract in ("M0_aggregate_RT", "M1_order_total_robust"):
        for parameter in ("h", "w"):
            passed_angles = []
            for angle_id in AUDIT_ANGLE_IDS:
                metric = audit["comparisons"][angle_id][contract][parameter]["N1"]
                if metric["gate"] and metric["signal_floor_pass"]:
                    passed_angles.append(angle_id)
            key = f"{contract}:{parameter}"
            angle_gate[key] = {
                "passing_angle_ids": passed_angles,
                "pass_count": len(passed_angles),
                "at_least_4_of_5": len(passed_angles) >= 4,
                "A14_A15_not_both_fail": not ({"A14", "A15"} <= (set(AUDIT_ANGLE_IDS) - set(passed_angles))),
            }
            if len(passed_angles) < 4:
                failures.append(f"angle_gate:{key}")
    audit["angle_gate"] = angle_gate
    # A14 and A15 must not both fail for each parameter in either formal contract.
    for contract in ("M0_aggregate_RT", "M1_order_total_robust"):
        for parameter in ("h", "w"):
            a14 = audit["comparisons"]["A14"][contract][parameter]["N1"]["gate"]
            a15 = audit["comparisons"]["A15"][contract][parameter]["N1"]["gate"]
            if not (a14 or a15):
                failures.append(f"baseline_pair_both_fail:{contract}:{parameter}")
    audit["failure_reasons"] = failures
    audit["status"] = "pass" if not failures else "controlled_stop"
    audit["production_step_recommendation"] = {
        parameter: ("half" if all(
            audit["angle_gate"][f"{contract}:{parameter}"]["at_least_4_of_5"]
            for contract in ("M0_aggregate_RT", "M1_order_total_robust")) else "coarse")
        for parameter in ("h", "w")
    }
    return audit


def choose_active_channels(nominal: dict[str, Any], perturbations: Iterable[dict[str, Any]],
                           contract: str) -> np.ndarray:
    if contract == "M0_aggregate_RT":
        return np.ones(2, dtype=bool)
    return _common_order_active([nominal, *list(perturbations)], contract)


def build_production_derivatives(*, nominal: dict[str, Any], states: dict[str, dict[str, Any]],
                                 step: str) -> dict[str, Any]:
    """Return central derivatives and fixed channel identities for one angle."""

    all_records = [nominal] + list(states.values())
    result: dict[str, Any] = {"step": step, "parameters": {}, "contracts": {}}
    for contract in CONTRACTS:
        active = choose_active_channels(nominal, states.values(), contract)
        y, channels = contract_vector(nominal, contract, active=active)
        contract_payload = {"channels": [list(item) if isinstance(item, tuple) else item for item in channels],
                            "nominal": y.tolist(), "noise_sigma": {
                                noise: noise_sigma(y, noise).tolist() for noise in NOISES}}
        for parameter, minus_state, plus_state in (("h", "H-", "H+"), ("w", "W-", "W+")):
            value = central_difference(_attach_delta(nominal, step),
                                       _attach_delta(states[minus_state], step),
                                       _attach_delta(states[plus_state], step),
                                       contract, parameter, active=active)
            contract_payload.setdefault("derivatives", {})[parameter] = value["derivative"].tolist()
        result["contracts"][contract] = contract_payload
    result["record_ids"] = {state: states[state].get("sample_id") for state in states}
    result["record_hashes"] = {state: states[state].get("formal_record_sha256") for state in states}
    return result


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n")
