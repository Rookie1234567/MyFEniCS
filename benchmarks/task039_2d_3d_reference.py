"""Offline identity and field comparison for the Task39 1-degree S/TE path."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from benchmarks.task039_2d_pair_convergence import _load_formal_run
from benchmarks.task039_full3d_identity import _load_run
from src.common.modes_3d import incident_power_3d
from src.io.input_validation import (
    simulation_config_2d_from_normalized,
    simulation_config_3d_from_normalized,
)

SCALAR_LIMIT = 1.0e-4
CLOSURE_LIMIT = 1.0e-5
ORDER_LIMIT = 1.0e-3
E_LIMIT = 5.0e-3
H_LIMIT = 1.0e-2
LEAKAGE_LIMIT = 1.0e-6
POWER_FLOOR = 1.0e-6
COMMON_Z = (30.0, 60.0, 90.0)
OBSERVABLES = ("R_total", "T_total", "A_balance", "A_volume")


def _json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not readable JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} is not a JSON object")
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} is not a scalar")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{label} is not finite")
    return result


def _metric(left: float, right: float, limit: float) -> dict[str, Any]:
    denominator = max(abs(left), abs(right), 1.0e-30)
    absolute = abs(left - right)
    return {
        "left": left,
        "right": right,
        "absolute_delta": absolute,
        "denominator": denominator,
        "relative_delta": absolute / denominator,
        "limit": limit,
        "pass": absolute <= limit,
    }


def _complex_metric(left: complex, right: complex) -> dict[str, Any]:
    left, right = complex(left), complex(right)
    denominator = max(abs(left), abs(right), 1.0e-30)
    absolute = abs(left - right)
    return {
        "left": [left.real, left.imag],
        "right": [right.real, right.imag],
        "absolute_delta": absolute,
        "denominator": denominator,
        "relative_delta": absolute / denominator,
        "limit": 1.0e-12,
        "pass": absolute / denominator <= 1.0e-12,
    }


def _field(left: np.ndarray, right: np.ndarray, limit: float) -> dict[str, Any]:
    absolute = float(np.linalg.norm(left - right))
    denominator = max(float(np.linalg.norm(left)), float(np.linalg.norm(right)), 1e-30)
    relative = absolute / denominator
    return {
        "absolute_l2": absolute,
        "denominator": denominator,
        "relative_l2": relative,
        "limit": limit,
        "pass": relative <= limit,
    }


def _load_configs(two_d: Mapping[str, Any], three_d: Mapping[str, Any]):
    cfg2 = _json(Path(two_d["root"]) / "resolved_config.json", "2D resolved config")
    cfg3 = _json(Path(three_d["root"]) / "resolved_config.json", "3D resolved config")
    return simulation_config_2d_from_normalized(
        cfg2
    ), simulation_config_3d_from_normalized(cfg3)


def _identity(
    cfg2: Any, cfg3: Any, two_d: Mapping[str, Any], three_d: Mapping[str, Any]
) -> dict[str, Any]:
    if two_d.get("model_id") != "task039_5nm_v3_1deg_s5":
        raise ValueError("2D run is not the Task39 1-degree S/TE profile")
    if three_d["manifest"].get("model_id") != "task039_5nm_v3_1deg_s5_full3d":
        raise ValueError("3D run is not the Task39 1-degree S profile")
    if not math.isclose(cfg2.incident_angle_deg, 89.0, abs_tol=1e-12):
        raise ValueError("2D angle identity failed")
    if not math.isclose(
        cfg3.incident_theta_deg, 89.0, abs_tol=1e-12
    ) or not math.isclose(cfg3.incident_phi_deg, 0.0, abs_tol=1e-12):
        raise ValueError("3D angle identity failed")
    for label, left, right in (
        ("wavelength_nm", cfg2.lambda0, cfg3.lambda0),
        ("period_x_nm", cfg2.period_x, cfg3.period_x),
        ("grating_width_nm", cfg2.grating_width, cfg3.grating_width_x),
        ("grating_height_nm", cfg2.grating_height, cfg3.grating_height),
    ):
        if not math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12):
            raise ValueError(f"geometry identity failed: {label}")
    materials = {
        name: _complex_metric(left, right)
        for name, left, right in (
            ("n_air", cfg2.n_air, cfg3.n_air),
            ("n_substrate", cfg2.n_substrate, cfg3.n_substrate),
            ("n_grating", cfg2.n_grating, cfg3.n_grating),
        )
    }
    kx = _complex_metric(cfg2.kx, cfg3.kx)
    kz = _complex_metric(cfg2.ky, cfg3.wavevector[2])
    if not kx["pass"]:
        raise ValueError("kx identity failed")
    if not kz["pass"]:
        raise ValueError("kz identity failed")
    if not np.allclose(
        cfg3.s_polarization_vector, (0.0, 1.0, 0.0), rtol=1e-12, atol=1e-13
    ):
        raise ValueError("3D S polarization is not Ey")
    beta = np.sqrt((cfg2.k0 * cfg2.n_air) ** 2 - cfg2.kx**2 + 0j)
    power = _metric(
        0.5 * float(np.real(beta)) * cfg2.period_x,
        incident_power_3d(cfg3) * cfg2.k0 / cfg3.period_y,
        1.0e-12,
    )
    power["pass"] = power["relative_delta"] <= 1.0e-12
    power["formula"] = "P2D = P3D * k0 / period_y"
    return {
        "model_2d": two_d["model_id"],
        "model_3d": three_d["manifest"]["model_id"],
        "wavelength_nm": cfg2.lambda0,
        "grazing_angle_deg": 90.0 - cfg2.incident_angle_deg,
        "azimuth_deg": cfg3.incident_phi_deg,
        "polarization": "S/TE",
        "kx": kx,
        "kz": kz,
        "s_polarization_3d": np.asarray(cfg3.s_polarization_vector).tolist(),
        "materials": materials,
        "incident_power": power,
    }


def _observables_and_closure(two_d: Mapping[str, Any], three_d: Mapping[str, Any]):
    numeric = three_d["numeric"]
    names = {
        "R_total": ("R_total_dtn_port_modal", "R_total"),
        "T_total": ("T_total_dtn_port_modal", "T_total"),
        "A_balance": ("A_balance_dtn_port_modal", "A_balance"),
        "A_volume": ("A_volume_total",),
    }
    values = {}
    for name, keys in names.items():
        left = _finite(two_d["power"].get(name), f"2D {name}")
        right = next(
            (_finite(numeric.get(key), f"3D {key}") for key in keys if key in numeric),
            None,
        )
        if right is None:
            raise ValueError(f"3D {name} is missing")
        values[name] = _metric(left, right, SCALAR_LIMIT)
    observable = {
        "items": values,
        "maximum_absolute_delta": max(x["absolute_delta"] for x in values.values()),
        "limit": SCALAR_LIMIT,
        "pass": all(x["pass"] for x in values.values()),
    }
    powers = {
        "2d": two_d["power"],
        "3d": {
            "R_total": numeric.get("R_total_dtn_port_modal", numeric.get("R_total")),
            "T_total": numeric.get("T_total_dtn_port_modal", numeric.get("T_total")),
            "A_volume": numeric.get("A_volume_total"),
        },
    }
    closure_values = {}
    for label, power in powers.items():
        value = (
            sum(
                _finite(power.get(key), f"{label} {key}")
                for key in ("R_total", "T_total", "A_volume")
            )
            - 1.0
        )
        closure_values[label] = {
            "value": value,
            "absolute": abs(value),
            "limit": CLOSURE_LIMIT,
            "pass": abs(value) <= CLOSURE_LIMIT,
        }
    return observable, {
        "values": closure_values,
        "pass": all(x["pass"] for x in closure_values.values()),
    }


def _fields(two_d: Mapping[str, Any], three_d: Mapping[str, Any]) -> dict[str, Any]:
    f2, ref = two_d["fields"], three_d["reference"]["arrays"]
    x2, z2, x3, z3 = map(np.asarray, (f2["x_nm"], f2["z_nm"], ref["x_nm"], ref["z_nm"]))
    if x2.shape != x3.shape or not np.array_equal(x2, x3):
        raise ValueError("2D/3D selected x coordinates are not exact")
    i2, i3 = [], []
    for z in COMMON_Z:
        a, b = np.flatnonzero(z2 == z), np.flatnonzero(z3 == z)
        if len(a) != 1 or len(b) != 1:
            raise ValueError(f"missing common selected plane z={z}")
        i2.append(int(a[0]))
        i3.append(int(b[0]))
    e3, h3 = np.asarray(ref["E_V_per_m"])[i3], np.asarray(ref["H_A_per_m"])[i3]
    if (
        e3.ndim != 4
        or h3.shape != e3.shape
        or e3.shape[2:] != (x3.size, 3)
        or not np.isfinite(e3).all()
        or not np.isfinite(h3).all()
    ):
        raise ValueError("Full3D selected field shape or values are invalid")
    ey, hx, hz = e3[:, :, :, 1], h3[:, :, :, 0], h3[:, :, :, 2]
    ey_mean, hx_mean, hz_mean = ey.mean(axis=1), hx.mean(axis=1), hz.mean(axis=1)
    e_gate = _field(np.asarray(f2["electric_y_V_per_m"])[i2], ey_mean, E_LIMIT)
    hx_gate = _field(np.asarray(f2["magnetic_x_A_per_m"])[i2], hx_mean, H_LIMIT)
    hz_gate = _field(np.asarray(f2["magnetic_z_A_per_m"])[i2], hz_mean, H_LIMIT)

    def den(a: np.ndarray) -> float:
        return max(float(np.linalg.norm(a)), 1e-30)

    invariance = {
        "electric_y_relative": float(
            np.linalg.norm(ey - ey_mean[:, None, :]) / den(ey)
        ),
        "magnetic_x_relative": float(
            np.linalg.norm(hx - hx_mean[:, None, :]) / den(hx)
        ),
        "magnetic_z_relative": float(
            np.linalg.norm(hz - hz_mean[:, None, :]) / den(hz)
        ),
        "non_Ey_component_relative": float(
            np.linalg.norm(e3[:, :, :, (0, 2)]) / den(ey)
        ),
    }
    flux3 = 0.5 * np.real(
        e3[:, :, :, 0] * np.conj(h3[:, :, :, 1])
        - e3[:, :, :, 1] * np.conj(h3[:, :, :, 0])
    ).mean(axis=1)
    flux2 = -0.5 * np.real(
        np.asarray(f2["electric_y_V_per_m"])[i2]
        * np.conj(np.asarray(f2["magnetic_x_A_per_m"])[i2])
    )
    flux_absolute = float(np.linalg.norm(flux2 - flux3))
    flux_denominator = max(
        float(np.linalg.norm(flux2)), float(np.linalg.norm(flux3)), 1.0e-30
    )
    return {
        "planes_nm": list(COMMON_Z),
        "reduction": "uniform-y arithmetic mean over all sampled y points",
        "electric_y": e_gate,
        "magnetic_x": hx_gate,
        "magnetic_z": hz_gate,
        "y_invariance_diagnostic": invariance,
        "normal_flux_diagnostic": {
            "formula_3d": "0.5*Re(Ex*conj(Hy)-Ey*conj(Hx))",
            "formula_2d_mapped": "-0.5*Re(Ey*conj(Hx))",
            "absolute_l2": flux_absolute,
            "denominator": flux_denominator,
            "relative_l2": flux_absolute / flux_denominator,
        },
        "pass": e_gate["pass"] and hx_gate["pass"] and hz_gate["pass"],
    }


def _orders(two_d: Mapping[str, Any], three_d: Mapping[str, Any]) -> dict[str, Any]:
    rows3, primary, pairs, amplitudes = three_d["orders"]["rows"], [], [], []
    missing_primary, missing_weak = [], []
    for side, power_key, flag in (
        ("top", "R_order", "top_propagating"),
        ("bottom", "T_order", "bottom_propagating"),
    ):
        for m, row2 in sorted(two_d["orders"].items()):
            key = (side, m, 0, "s")
            left = _finite(row2[power_key], f"2D {key} power")
            if key not in rows3:
                if row2[flag] and left >= POWER_FLOOR:
                    missing_primary.append(key)
                else:
                    missing_weak.append(key)
                continue
            right = _finite(rows3[key]["power_ratio"], f"3D {key} power")
            item = _metric(left, right, ORDER_LIMIT) | {
                "side": side,
                "m": m,
                "power_left": left,
                "power_right": right,
            }
            pairs.append(item)
            if row2[flag] and max(left, right) >= POWER_FLOOR:
                primary.append(item)
            amp = "reflected" if side == "top" else "transmitted"
            amplitudes.append(
                abs(
                    complex(row2[f"{amp}_Ez_real"], row2[f"{amp}_Ez_imag"])
                    - rows3[key]["outgoing_amplitude"]
                )
            )
    primary_den = max(
        sum(max(x["power_left"], x["power_right"]) for x in primary), 1e-30
    )
    primary_num = sum(x["absolute_delta"] for x in primary)
    all_den = max(sum(max(x["power_left"], x["power_right"]) for x in pairs), 1e-30)
    all_num = sum(x["absolute_delta"] for x in pairs)
    leak_den = max(sum(x["power_right"] for x in pairs), 1e-30)
    leak_power = sum(
        row["power_ratio"]
        for (side, m, n, pol), row in rows3.items()
        if n != 0 or pol.lower() != "s"
    )
    primary_weighted = {
        "numerator": primary_num,
        "denominator": primary_den,
        "value": primary_num / primary_den,
        "limit": ORDER_LIMIT,
        "pass": (
            bool(primary)
            and not missing_primary
            and primary_num / primary_den <= ORDER_LIMIT
        ),
    }
    return {
        "mapping": "3D (side,m,n=0,S) to 2D (top R_order/bottom T_order)",
        "primary_power_floor": POWER_FLOOR,
        "primary_count": len(primary),
        "missing_primary_keys": [list(key) for key in missing_primary],
        "missing_primary_count": len(missing_primary),
        "missing_weak_keys": [list(key) for key in missing_weak],
        "missing_weak_count": len(missing_weak),
        "primary_max_relative": max(
            (x["relative_delta"] for x in primary), default=0.0
        ),
        "primary_weighted": primary_weighted,
        "primary_pass": primary_weighted["pass"],
        "weighted_all_m": {
            "numerator": all_num,
            "denominator": all_den,
            "value": all_num / all_den,
            "limit": ORDER_LIMIT,
            "pass": all_num / all_den <= ORDER_LIMIT,
        },
        "leakage": {
            "union_definition": "n != 0 OR polarization != s; each row counted once",
            "aggregate": {
                "absolute_power": leak_power,
                "diagnostic_denominator": leak_den,
                "diagnostic_relative": leak_power / leak_den,
                "limit": LEAKAGE_LIMIT,
                "pass": leak_power <= LEAKAGE_LIMIT,
            },
        },
        "complex_amplitude_diagnostic": {
            "count": len(amplitudes),
            "maximum_absolute_delta": max(amplitudes, default=0.0),
        },
        "all_rows_count": len(pairs),
    }


def compare_2d_3d_reference(
    two_d_run_directory: str | Path, full3d_run_directory: str | Path
) -> dict[str, Any]:
    two_d = _load_formal_run(two_d_run_directory, "2D")
    three_d = _load_run(
        full3d_run_directory,
        "direct",
        expected_mesh_target_size=None,
        profile="v3_1deg",
    )
    cfg2, cfg3 = _load_configs(two_d, three_d)
    identity = _identity(cfg2, cfg3, two_d, three_d)
    observables, closure = _observables_and_closure(two_d, three_d)
    fields, orders = _fields(two_d, three_d), _orders(two_d, three_d)
    gates = {
        "identity": identity["incident_power"]["pass"]
        and all(x["pass"] for x in identity["materials"].values()),
        "scalar_observables": observables["pass"],
        "closure": closure["pass"],
        "selected_fields": fields["pass"],
        "primary_m_orders": orders["primary_pass"],
        "leakage": orders["leakage"]["aggregate"]["pass"],
    }
    passed = all(gates.values())
    return {
        "schema": "task039.v3-2d-3d-reference.v1",
        "pass": passed,
        "classification": "TASK039_V3_2D_3D_REFERENCE_PASS"
        if passed
        else "TASK039_V3_2D_3D_REFERENCE_FAIL",
        "source_identity": {
            "two_d_source_sha": two_d["source_sha"],
            "full3d_source_sha": three_d["manifest"]["source_sha"],
            "source_sha_policy": "solver/config identities are reported; checker source may differ",
        },
        "runs": {"two_d": two_d["root"], "full3d": str(three_d["root"])},
        "identity": identity,
        "observables": observables,
        "closure": closure,
        "orders": orders,
        "fields": fields,
        "gates": gates,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--2d-run", required=True, type=Path)
    parser.add_argument("--full3d-run", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        result = compare_2d_3d_reference(vars(args)["2d_run"], args.full3d_run)
        code = 0 if result["pass"] else 1
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {
            "schema": "task039.v3-2d-3d-reference.v1",
            "pass": False,
            "classification": "TASK039_V3_2D_3D_REFERENCE_CHECKER_ERROR",
            "error": str(exc),
        }
        code = 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return code


__all__ = ["compare_2d_3d_reference", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
