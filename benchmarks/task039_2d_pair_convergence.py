"""Offline pair convergence checks for two Task39 V3 2D TE runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from benchmarks.task039_review_v1_contracts import TASK039_V2_PRIMARY_POWER_FLOOR

SCALAR_LIMIT = 1.0e-6
CLOSURE_LIMIT = 1.0e-8
ORDER_LIMIT = 1.0e-4
WEIGHTED_LIMIT = 1.0e-5
E_LIMIT = 1.0e-3
H_LIMIT = 2.0e-3
OBSERVABLES = ("R_total", "T_total", "A_balance", "A_volume")
ORDER_FIELDS = (
    "reflected_Ez_real",
    "reflected_Ez_imag",
    "transmitted_Ez_real",
    "transmitted_Ez_imag",
    "R_order",
    "T_order",
)


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError(f"{label} is not readable JSON: {exc}") from exc


def _artifact(root: Path, descriptor: Any, label: str) -> Path:
    if not isinstance(descriptor, Mapping):
        raise ValueError(f"{label} descriptor is missing")
    relative, expected = descriptor.get("path"), descriptor.get("sha256")
    if not isinstance(relative, str) or not isinstance(expected, str):
        raise ValueError(f"{label} descriptor is incomplete")
    path = root / "numerical_output" / relative
    if not path.is_file() or _sha(path) != expected:
        raise ValueError(f"{label} artifact is missing or hash-mismatched")
    return path


def _orders(rows: Any, label: str) -> dict[int, Mapping[str, Any]]:
    if not isinstance(rows, list) or len(rows) != 43:
        raise ValueError(f"{label} must contain 43 rows")
    result = {}
    for row in rows:
        if not isinstance(row, Mapping) or not isinstance(row.get("order"), int):
            raise ValueError(f"{label} contains an invalid row")
        order = row["order"]
        if order in result or not -21 <= order <= 21:
            raise ValueError(f"{label} has duplicate/out-of-range orders")
        if not all(
            isinstance(row.get(k), bool)
            for k in ("top_propagating", "bottom_propagating")
        ):
            raise ValueError(f"{label} propagation flags are invalid")
        if not all(_finite(row.get(k)) for k in ORDER_FIELDS):
            raise ValueError(f"{label} has non-finite order data")
        result[order] = row
    if set(result) != set(range(-21, 22)):
        raise ValueError(f"{label} does not cover -21..21")
    top = {n for n, row in result.items() if row["top_propagating"]}
    bottom = {n for n, row in result.items() if row["bottom_propagating"]}
    if top != set(range(-19, 1)) or bottom != set(range(-19, 0)):
        raise ValueError(f"{label} propagation inventory is not the V3 contract")
    return result


def _load_formal_run(run_directory: str | Path, label: str) -> dict[str, Any]:
    root = Path(run_directory).resolve()
    reference = _json(
        root / "numerical_output/v3_2d_reference.json", f"{label} reference"
    )
    if (
        not isinstance(reference, Mapping)
        or reference.get("schema") != "task039.v3-2d-te-reference.v1"
    ):
        raise ValueError(f"{label} reference schema is invalid")
    artifacts = reference.get("artifacts")
    if not isinstance(artifacts, Mapping):
        raise ValueError(f"{label} artifact descriptors are missing")
    power_path = _artifact(
        root, artifacts.get("dtn_port_power_metrics.json"), f"{label} power"
    )
    orders_path = _artifact(
        root, artifacts.get("dtn_port_diffraction_orders.json"), f"{label} orders"
    )
    selected = artifacts.get("selected_fields")
    if not isinstance(selected, Mapping):
        raise ValueError(f"{label} selected-field descriptors are missing")
    payload_path = _artifact(root, selected.get("payload"), f"{label} selected payload")
    metadata_path = _artifact(
        root, selected.get("metadata"), f"{label} selected metadata"
    )

    power = _json(power_path, f"{label} power")
    rows = _json(orders_path, f"{label} orders")
    if (
        not isinstance(power, Mapping)
        or not isinstance(rows, list)
        or power.get("orders") != rows
    ):
        raise ValueError(f"{label} raw DtN evidence is inconsistent")
    if power.get("port_dtn_order_count") != 21:
        raise ValueError(f"{label} DtN order count is not 21")
    order_map = _orders(rows, f"{label} orders")
    for key in OBSERVABLES:
        if not _finite(power.get(key)) or power[key] != reference.get(
            "observables", {}
        ).get(key):
            raise ValueError(f"{label} observable evidence is inconsistent: {key}")
    closure = float(power["R_total"] + power["T_total"] + power["A_volume"] - 1.0)
    if not _finite(
        reference.get("energy_closure_R_plus_T_plus_A_volume_minus_1")
    ) or not math.isclose(
        closure,
        float(reference["energy_closure_R_plus_T_plus_A_volume_minus_1"]),
        rel_tol=0.0,
        abs_tol=1e-15,
    ):
        raise ValueError(f"{label} closure evidence is inconsistent")

    metadata = _json(metadata_path, f"{label} selected metadata")
    if not isinstance(metadata, Mapping) or metadata.get("payload_sha256") != _sha(
        payload_path
    ):
        raise ValueError(f"{label} selected metadata hash is invalid")
    try:
        with np.load(payload_path, allow_pickle=False) as archive:
            names = (
                "x_nm",
                "z_nm",
                "electric_y_V_per_m",
                "magnetic_x_A_per_m",
                "magnetic_z_A_per_m",
            )
            if set(archive.files) != set(names):
                raise ValueError(f"{label} selected array keys are invalid")
            fields = {name: np.asarray(archive[name]).copy() for name in names}
    except (OSError, ValueError) as exc:
        if isinstance(exc, ValueError) and str(exc).startswith(f"{label} selected"):
            raise
        raise ValueError(f"{label} selected payload is unreadable: {exc}") from exc
    shapes = {"x_nm": (40,), "z_nm": (7,)} | {name: (7, 40) for name in names[2:]}
    if any(fields[name].shape != shape for name, shape in shapes.items()) or any(
        not np.all(np.isfinite(fields[name])) for name in names
    ):
        raise ValueError(f"{label} selected arrays have invalid shape or values")

    resolved = _json(root / "resolved_config.json", f"{label} resolved config")
    identities = {}
    for name in ("source_sha", "input_sha256", "physical_model_sha256"):
        path = root / f"{name}.txt"
        if not path.is_file() or not (
            value := path.read_text(encoding="utf-8").strip()
        ):
            raise ValueError(f"{label} {name} is missing")
        identities[name] = value
    model_id = reference.get("model_id")
    if not isinstance(model_id, str) or not model_id:
        raise ValueError(f"{label} model_id is missing")
    return {
        "root": str(root),
        "reference": reference,
        "power": power,
        "orders": order_map,
        "closure": closure,
        "fields": fields,
        "model_id": model_id,
        "source_sha": identities["source_sha"],
        "input_sha": identities["input_sha256"],
        "physical_sha": identities["physical_model_sha256"],
        "mesh_target_nm": resolved.get("discretization", {}).get("mesh_target_nm"),
        "resolved_method": resolved.get("method"),
        "resolved_solver": resolved.get("solver"),
    }


def _relative(left: float, right: float) -> tuple[float, float]:
    denominator = max(left, right, 1.0e-30)
    return abs(left - right) / denominator, denominator


def _field(left: np.ndarray, right: np.ndarray, limit: float) -> dict[str, Any]:
    absolute = float(np.linalg.norm(left - right))
    denominator = max(
        float(np.linalg.norm(left)), float(np.linalg.norm(right)), 1.0e-30
    )
    return {
        "absolute_l2": absolute,
        "denominator": denominator,
        "relative_l2": absolute / denominator,
        "limit": limit,
        "pass": absolute / denominator <= limit,
    }


def _order(
    side: str, number: int, left: Mapping[str, Any], right: Mapping[str, Any], key: str
) -> dict[str, Any]:
    lp, rp = float(left[key]), float(right[key])
    relative, denominator = _relative(lp, rp)
    return {
        "side": side,
        "order": number,
        "power_left": lp,
        "power_right": rp,
        "absolute_delta": abs(lp - rp),
        "relative_delta": relative,
        "denominator": denominator,
        "limit": ORDER_LIMIT,
        "pass": relative <= ORDER_LIMIT,
    }


def compare_2d_pair(
    left_run_directory: str | Path, right_run_directory: str | Path
) -> dict[str, Any]:
    """Compare two accepted Task39 V3 2D formal reference runs offline."""
    left = _load_formal_run(left_run_directory, "left")
    right = _load_formal_run(right_run_directory, "right")
    if left["model_id"] != right["model_id"]:
        raise ValueError("2D pair model_id values differ")
    coordinates_exact = all(
        np.array_equal(left["fields"][key], right["fields"][key])
        for key in ("x_nm", "z_nm")
    )

    scalars = {}
    for key in OBSERVABLES:
        delta = abs(left["power"][key] - right["power"][key])
        scalars[key] = {
            "left": left["power"][key],
            "right": right["power"][key],
            "absolute_delta": delta,
            "limit": SCALAR_LIMIT,
            "pass": delta <= SCALAR_LIMIT,
        }
    scalar_gate = {
        "formula": "max(abs(left-observable-right-observable))",
        "items": scalars,
        "limit": SCALAR_LIMIT,
        "maximum_absolute_delta": max(
            item["absolute_delta"] for item in scalars.values()
        ),
        "pass": all(item["pass"] for item in scalars.values()),
    }
    closure = {
        name: {
            "value": run["closure"],
            "absolute_value": abs(run["closure"]),
            "limit": CLOSURE_LIMIT,
            "pass": abs(run["closure"]) <= CLOSURE_LIMIT,
        }
        for name, run in (("left", left), ("right", right))
    }

    primary, all_pairs = [], []
    for side, power_key, flag in (
        ("top", "R_order", "top_propagating"),
        ("bottom", "T_order", "bottom_propagating"),
    ):
        for number in range(-21, 22):
            lrow, rrow = left["orders"][number], right["orders"][number]
            all_pairs.append((float(lrow[power_key]), float(rrow[power_key])))
            if (
                lrow[flag]
                and rrow[flag]
                and max(lrow[power_key], rrow[power_key])
                >= TASK039_V2_PRIMARY_POWER_FLOOR
            ):
                primary.append(_order(side, number, lrow, rrow, power_key))
    primary_gate = {
        "power_floor": TASK039_V2_PRIMARY_POWER_FLOOR,
        "count": len(primary),
        "limit": ORDER_LIMIT,
        "maximum_relative_delta": max(
            (row["relative_delta"] for row in primary), default=0.0
        ),
        "pass": bool(primary) and all(row["pass"] for row in primary),
        "rows": primary,
    }
    numerator = sum(
        abs(left_power - right_power) for left_power, right_power in all_pairs
    )
    denominator = max(
        sum(max(left_power, right_power) for left_power, right_power in all_pairs),
        1.0e-30,
    )
    weighted_gate = {
        "formula": "sum(abs(delta power over top R and bottom T, all 43 orders))/max(sum(max(pair powers)),1e-30)",
        "numerator": numerator,
        "denominator": denominator,
        "value": numerator / denominator,
        "limit": WEIGHTED_LIMIT,
        "pass": numerator / denominator <= WEIGHTED_LIMIT,
    }

    e_gate = _field(
        left["fields"]["electric_y_V_per_m"],
        right["fields"]["electric_y_V_per_m"],
        E_LIMIT,
    )
    hx_gate = _field(
        left["fields"]["magnetic_x_A_per_m"],
        right["fields"]["magnetic_x_A_per_m"],
        H_LIMIT,
    )
    hz_gate = _field(
        left["fields"]["magnetic_z_A_per_m"],
        right["fields"]["magnetic_z_A_per_m"],
        H_LIMIT,
    )
    h_gate = _field(
        np.concatenate(
            (
                left["fields"]["magnetic_x_A_per_m"].ravel(),
                left["fields"]["magnetic_z_A_per_m"].ravel(),
            )
        ),
        np.concatenate(
            (
                right["fields"]["magnetic_x_A_per_m"].ravel(),
                right["fields"]["magnetic_z_A_per_m"].ravel(),
            )
        ),
        H_LIMIT,
    )
    gates = {
        "scalar_observables": scalar_gate["pass"],
        "closure": all(item["pass"] for item in closure.values()),
        "primary_propagating_orders": primary_gate["pass"],
        "all_order_weighted_power": weighted_gate["pass"],
        "electric_field": coordinates_exact and e_gate["pass"],
        "magnetic_field": coordinates_exact and h_gate["pass"],
    }
    passed = all(gates.values())
    return {
        "schema": "task039.v3-2d-pair-convergence.v1",
        "pass": passed,
        "classification": "TASK039_V3_2D_PAIR_CONVERGENCE_PASS"
        if passed
        else "TASK039_V3_2D_PAIR_CONVERGENCE_FAIL",
        "runs": {
            name: {
                "root": run["root"],
                "mesh_target_nm": run["mesh_target_nm"],
                "linear": run["reference"].get("linear"),
                "elapsed_seconds": run["reference"].get("elapsed_seconds"),
            }
            for name, run in (("left", left), ("right", right))
        },
        "source_identity": {
            "left_source_sha": left["source_sha"],
            "right_source_sha": right["source_sha"],
            "source_sha_equal": left["source_sha"] == right["source_sha"],
            "left_input_sha256": left["input_sha"],
            "right_input_sha256": right["input_sha"],
            "left_physical_model_sha256": left["physical_sha"],
            "right_physical_model_sha256": right["physical_sha"],
            "model_id_equal": left["model_id"] == right["model_id"],
            "resolved_method_equal": left["resolved_method"]
            == right["resolved_method"],
            "resolved_solver_equal": left["resolved_solver"]
            == right["resolved_solver"],
            "source_sha_policy": "reported_identity_not_a_convergence_gate",
        },
        "coordinates": {
            "exact": coordinates_exact,
            "x_shape": list(left["fields"]["x_nm"].shape),
            "z_shape": list(left["fields"]["z_nm"].shape),
        },
        "scalar_observables": scalar_gate,
        "closure": closure,
        "primary_power_rows": primary_gate,
        "all_order_weighted_power": weighted_gate,
        "fields": {
            "electric_y": e_gate,
            "magnetic_x": hx_gate,
            "magnetic_z": hz_gate,
            "magnetic_concat": h_gate,
        },
        "gates": gates,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--left-run", required=True, type=Path)
    parser.add_argument("--right-run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare_2d_pair(args.left_run, args.right_run)
        code = 0 if result["pass"] else 1
    except (OSError, ValueError, KeyError) as exc:
        result = {
            "schema": "task039.v3-2d-pair-convergence.v1",
            "pass": False,
            "classification": "TASK039_V3_2D_PAIR_CHECKER_ERROR",
            "error": str(exc),
        }
        code = 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return code


__all__ = ["compare_2d_pair", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
