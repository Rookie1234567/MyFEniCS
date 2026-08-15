"""Task38 ordinary 2D adapter for the existing TM/TE solver entrypoints."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Callable, Mapping

import numpy as np

from src.io.input_validation import simulation_config_2d_from_normalized


def _finite(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _linear_residual_errors(summary: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    residual = summary.get("reduced_linear_residual")
    if not _finite(residual) or not 0.0 <= float(residual) <= 1.0e-9:
        errors.append("2D solver reduced residual exceeds 1e-9")
    return errors


def _authority_errors(
    summary: Mapping[str, Any], output: Mapping[str, Any]
) -> list[str]:
    errors = _linear_residual_errors(summary)
    if output.get("compute_power_metrics"):
        metrics = summary.get("power_metrics")
        if not isinstance(metrics, Mapping):
            errors.append("2D requested power metrics are missing")
        else:
            for key in ("R_total", "T_total", "R_plus_T"):
                if not _finite(metrics.get(key)):
                    errors.append(
                        f"2D requested power metric {key} is missing or non-finite"
                    )
    return errors


def _is_v3_2d_payload(payload: Mapping[str, Any]) -> bool:
    identity = payload.get("identity", payload)
    method = payload.get("method")
    return bool(
        isinstance(identity, Mapping)
        and identity.get("model_id") == "task039_5nm_v3_1deg_s5"
        and isinstance(method, Mapping)
        and method.get("kind") == "2d_port"
    )


def _v3_2d_file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _v3_2d_order_contract(rows: Any) -> list[dict[str, Any]] | None:
    fields = (
        "order",
        "top_propagating",
        "bottom_propagating",
        "reflected_Ez_real",
        "reflected_Ez_imag",
        "transmitted_Ez_real",
        "transmitted_Ez_imag",
        "R_order",
        "T_order",
    )
    if not isinstance(rows, list) or any(not isinstance(row, Mapping) for row in rows):
        return None
    return [{key: row.get(key) for key in fields} for row in rows]


def _v3_2d_raw_dtn_rows(
    metrics: Mapping[str, Any], numerical_output: Path
) -> tuple[list[Mapping[str, Any]] | None, list[str]]:
    errors: list[str] = []
    power_path = numerical_output / "dtn_port_power_metrics.json"
    orders_path = numerical_output / "dtn_port_diffraction_orders.json"
    try:
        raw_power = json.loads(power_path.read_text(encoding="utf-8"))
        raw_orders = json.loads(orders_path.read_text(encoding="utf-8"))
    except (OSError, TypeError, ValueError) as exc:
        return None, [f"V3 2D raw DtN evidence is unreadable: {exc}"]
    if not isinstance(raw_power, Mapping):
        errors.append("V3 2D raw power evidence is not a mapping")
    if not isinstance(raw_orders, list):
        errors.append("V3 2D raw diffraction evidence is not a list")
    if errors:
        return None, errors
    for key in (
        "port_dtn_order_count",
        "R_total",
        "T_total",
        "R_plus_T",
        "A_balance",
        "A_volume",
    ):
        if raw_power.get(key) != metrics.get(key):
            errors.append(f"V3 2D raw power field disagrees with summary: {key}")
    summary_rows = metrics.get("orders")
    raw_power_rows = raw_power.get("orders")
    raw_contract = _v3_2d_order_contract(raw_power_rows)
    summary_contract = _v3_2d_order_contract(summary_rows)
    if raw_contract is None or summary_contract is None:
        errors.append("V3 2D raw/summary order contract is not a list of mappings")
    elif raw_contract != summary_contract:
        errors.append("V3 2D raw power orders disagree with summary orders")
    if raw_orders != raw_power_rows:
        errors.append("V3 2D raw diffraction orders disagree with raw power orders")
    return raw_orders, errors


def _v3_2d_reference_record(
    payload: Mapping[str, Any], summary: Mapping[str, Any], numerical_output: Path
) -> Path | None:
    descriptor = summary.get("v3_selected_fields")
    dtn = summary.get("dtn_port_power_metrics")
    if not isinstance(descriptor, Mapping) or not isinstance(dtn, Mapping):
        return None
    artifacts: dict[str, Any] = {}
    for name in ("dtn_port_power_metrics.json", "dtn_port_diffraction_orders.json"):
        path = numerical_output / name
        if not path.is_file():
            return None
        artifacts[name] = {"path": path.name, "sha256": _v3_2d_file_sha(path)}
    selected_payload = numerical_output / str(descriptor["payload_path"])
    selected_metadata = numerical_output / str(descriptor["metadata_path"])
    if not selected_payload.is_file() or not selected_metadata.is_file():
        return None
    artifacts["selected_fields"] = {
        "payload": {
            "path": selected_payload.name,
            "sha256": _v3_2d_file_sha(selected_payload),
        },
        "metadata": {
            "path": selected_metadata.name,
            "sha256": _v3_2d_file_sha(selected_metadata),
        },
    }
    rows = dtn.get("orders", [])
    propagating = {
        side: [int(row["order"]) for row in rows if row.get(f"{side}_propagating")]
        for side in ("top", "bottom")
    }
    provenance = payload.get("provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    r_total = dtn.get("R_total")
    t_total = dtn.get("T_total")
    a_volume = dtn.get("A_volume")
    energy_closure = (
        float(r_total) + float(t_total) + float(a_volume) - 1.0
        if all(_finite(value) for value in (r_total, t_total, a_volume))
        else None
    )
    a_balance = dtn.get("A_balance")
    balance_minus_volume = (
        float(a_balance) - float(a_volume)
        if all(_finite(value) for value in (a_balance, a_volume))
        else None
    )
    observables = {
        key: dtn.get(key)
        for key in (
            "R_total",
            "T_total",
            "R_plus_T",
            "A_balance",
            "A_volume",
            "energy_residual_1_minus_R_minus_T",
            "incident_power_weighted",
        )
    }
    observables["A_balance_minus_A_volume"] = balance_minus_volume
    record = {
        "schema": "task039.v3-2d-te-reference.v1",
        "model_id": payload.get("model_id"),
        "provenance": {
            "input_sha256": provenance.get("input_sha256"),
            "physical_model_sha256": provenance.get("physical_model_sha256"),
            "source_path": provenance.get("source_path"),
            "source_sha256_from_outer_manifest": True,
        },
        "artifacts": artifacts,
        "observables": observables,
        "energy_closure_R_plus_T_plus_A_volume_minus_1": energy_closure,
        "propagating_orders": propagating,
        "order_bound": int(dtn.get("port_dtn_order_count", 0)),
        "linear": {
            key: summary.get(key)
            for key in (
                "num_mesh_cells",
                "num_scalar_dofs",
                "num_reduced_dofs",
                "linear_matrix_rows",
                "linear_matrix_nnz",
                "reduced_matrix_nnz",
            )
        },
        "elapsed_seconds": summary.get("elapsed_seconds"),
    }
    path = numerical_output / "v3_2d_reference.json"
    path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def _v3_2d_authority_errors(
    summary: Mapping[str, Any], numerical_output: Path
) -> list[str]:
    errors: list[str] = []
    metrics = summary.get("dtn_port_power_metrics")
    if not isinstance(metrics, Mapping):
        return ["V3 2D DtN power metrics are missing"]
    for key in (
        "R_total",
        "T_total",
        "R_plus_T",
        "A_balance",
        "A_volume",
    ):
        if not _finite(metrics.get(key)):
            errors.append(f"V3 2D DtN observable {key} is missing or non-finite")
    r_total = metrics.get("R_total")
    t_total = metrics.get("T_total")
    a_volume = metrics.get("A_volume")
    if all(_finite(value) for value in (r_total, t_total, a_volume)):
        closure = float(r_total) + float(t_total) + float(a_volume) - 1.0
        if abs(closure) > 1.0e-8:
            errors.append(
                "V3 2D energy closure R_total+T_total+A_volume-1 exceeds 1e-8"
            )
    else:
        errors.append("V3 2D energy closure cannot be computed from finite observables")
    rows = metrics.get("orders")
    if metrics.get("port_dtn_order_count") != 21:
        errors.append("V3 2D DtN order bound must be exactly 21")
    if not isinstance(rows, list) or not rows:
        errors.append("V3 2D propagating-order catalog is missing")
    else:
        order_values = [row.get("order") for row in rows if isinstance(row, Mapping)]
        valid_orders = all(
            isinstance(order, int) and not isinstance(order, bool)
            for order in order_values
        )
        if (
            len(rows) != 43
            or not valid_orders
            or sorted(order_values) != list(range(-21, 22))
        ):
            errors.append(
                "V3 2D DtN order catalog must contain each unique order -21..21"
            )
        expected_top = set(range(-19, 1))
        expected_bottom = set(range(-19, 0))
        actual_top = {
            row.get("order")
            for row in rows
            if isinstance(row, Mapping) and row.get("top_propagating") is True
        }
        actual_bottom = {
            row.get("order")
            for row in rows
            if isinstance(row, Mapping) and row.get("bottom_propagating") is True
        }
        if actual_top != expected_top or actual_bottom != expected_bottom:
            errors.append(
                "V3 2D propagating inventory must be top -19..0 and bottom -19..-1"
            )
        for row in rows:
            if not isinstance(row, Mapping):
                errors.append("V3 2D order row is not an object")
                continue
            for key in (
                "order",
                "top_propagating",
                "bottom_propagating",
                "reflected_Ez_real",
                "reflected_Ez_imag",
                "transmitted_Ez_real",
                "transmitted_Ez_imag",
                "R_order",
                "T_order",
            ):
                if key not in row or (
                    key not in {"order", "top_propagating", "bottom_propagating"}
                    and not _finite(row[key])
                ):
                    errors.append(f"V3 2D order field {key} is missing or non-finite")
    descriptor = summary.get("v3_selected_fields")
    if not isinstance(descriptor, Mapping):
        return errors + ["V3 2D selected field descriptor is missing"]
    for name in ("dtn_port_power_metrics.json", "dtn_port_diffraction_orders.json"):
        path = numerical_output / name
        if not path.is_file():
            errors.append(f"V3 2D required DtN artifact is missing: {name}")
        else:
            try:
                _v3_2d_file_sha(path)
            except OSError as exc:
                errors.append(f"V3 2D required DtN artifact is unreadable: {exc}")
    if not any(
        "required DtN artifact is missing" in error
        or "required DtN artifact is unreadable" in error
        for error in errors
    ):
        raw_rows, raw_errors = _v3_2d_raw_dtn_rows(metrics, numerical_output)
        errors.extend(raw_errors)
        if raw_rows is not None:
            rows = raw_rows
        else:
            rows = []
    else:
        rows = []
    payload_path = numerical_output / str(descriptor.get("payload_path", ""))
    metadata_path = numerical_output / str(descriptor.get("metadata_path", ""))
    if not payload_path.is_file() or not metadata_path.is_file():
        return errors + ["V3 2D selected field payload or metadata is missing"]
    if descriptor.get("payload_sha256") != _v3_2d_file_sha(payload_path):
        errors.append("V3 2D selected field payload SHA mismatch")
    if descriptor.get("metadata_sha256") != _v3_2d_file_sha(metadata_path):
        errors.append("V3 2D selected field metadata SHA mismatch")
    try:
        with np.load(payload_path, allow_pickle=False) as arrays:
            expected = {
                "x_nm",
                "z_nm",
                "electric_y_V_per_m",
                "magnetic_x_A_per_m",
                "magnetic_z_A_per_m",
            }
            if set(arrays.files) != expected:
                errors.append("V3 2D selected field array keys are not exact")
            if arrays["x_nm"].shape != (40,) or arrays["z_nm"].shape != (7,):
                errors.append("V3 2D selected field coordinates have the wrong shape")
            for key in (
                "electric_y_V_per_m",
                "magnetic_x_A_per_m",
                "magnetic_z_A_per_m",
            ):
                if arrays[key].shape != (7, 40) or not np.all(np.isfinite(arrays[key])):
                    errors.append(
                        f"V3 2D selected field {key} shape/finite contract failed"
                    )
    except (KeyError, OSError, ValueError) as exc:
        errors.append(f"V3 2D selected field payload is unreadable: {exc}")
    return errors


def _run_solver(
    cfg: Any, output_directory: Path, constraint_backend: str
) -> Mapping[str, Any]:
    from src.solvers.solve_port_maxwell import run_port_case
    from src.solvers.solve_te_maxwell import run_te_case, run_te_port_case
    from src.solvers.solve_vector_maxwell import run_case

    if cfg.calculation_method == "scattered":
        runner = run_te_case if cfg.polarization_type.upper() == "TE" else run_case
    elif cfg.polarization_type.upper() == "TE":
        runner = run_te_port_case
    else:
        runner = run_port_case
    return runner(cfg, output_directory, constraint_backend=constraint_backend)


def run_2d(
    resolved_payload: Mapping[str, Any],
    run_directory: str | Path,
    *,
    solver_runner: Callable[[Any, Path, str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run one connected ordinary 2D method without a CLI round trip."""

    if resolved_payload.get("dimension") != 2:
        raise ValueError("2D adapter requires dimension=2")
    method = resolved_payload.get("method")
    if not isinstance(method, Mapping) or method.get("kind") not in {
        "2d_scattered",
        "2d_port",
    }:
        raise ValueError("2D adapter requires method.kind=2d_scattered or 2d_port")
    solver = resolved_payload.get("solver")
    if not isinstance(solver, Mapping) or solver.get("linear_solver") != "direct":
        raise ValueError("2D adapter requires solver.linear_solver=direct")
    output = resolved_payload.get("output")
    if not isinstance(output, Mapping):
        raise ValueError("resolved output payload is missing")
    cfg = simulation_config_2d_from_normalized(resolved_payload)
    numerical_output = Path(run_directory).resolve() / "numerical_output"
    runner = solver_runner or _run_solver
    summary = runner(cfg, numerical_output, str(method["constraint_backend"]))
    if not isinstance(summary, Mapping):
        return {
            "passed": False,
            "errors": ["2D solver did not return a summary object"],
            "summary": None,
            "numerical_output_directory": str(numerical_output),
        }
    reference_record = None
    if _is_v3_2d_payload(resolved_payload):
        errors = _linear_residual_errors(summary)
        errors.extend(_v3_2d_authority_errors(summary, numerical_output))
        if not errors:
            reference_record = _v3_2d_reference_record(
                resolved_payload, summary, numerical_output
            )
    else:
        errors = _authority_errors(summary, output)
    result = {
        "passed": not errors,
        "errors": errors,
        "summary": summary,
        "numerical_output_directory": str(numerical_output),
    }
    if reference_record is not None:
        result["v3_2d_reference_record"] = str(reference_record)
    return result


__all__ = ["run_2d"]
