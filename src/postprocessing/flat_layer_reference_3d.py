from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
from mpi4py import MPI

from ..common.analytic_fields_3d import _fresnel_components, fresnel_reference
from ..common.config_3d import SimulationConfig3D
from ..common.modes_3d import incident_power_3d


FLAT_LAYER_REFERENCE_NOTE = (
    "Flat-layer reference uses the analytic Fresnel/layered solution in the same "
    "code units as Stage-4 postprocessing: H=curl(E)/(i*k0*mu_r) and "
    "S=0.5*Re(E x conj(H)). For lossy substrates, transmitted power is evaluated "
    "at the requested bottom plane, so propagation attenuation below the interface "
    "is included."
)

VOLUME_ABSORPTION_REFERENCE_FORMULA = (
    "P_abs = integral 0.5*k0*Im(epsilon_r)*|E_total|^2 dV"
)


def _json_default(value):
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot JSON serialize {type(value)!r}")


def _complex_pair(value: complex) -> list[float]:
    number = complex(value)
    return [float(number.real), float(number.imag)]


def flat_layer_probe_planes(cfg: SimulationConfig3D) -> tuple[float, float]:
    """Return the top/bottom probe planes used by diffraction postprocessing."""

    probe_fraction = float(cfg.diffraction_probe_fraction)
    if not (0.0 < probe_fraction < 1.0):
        raise ValueError("diffraction_probe_fraction must be between 0 and 1.")
    if cfg.diffraction_top_probe_z is not None:
        top_z = float(cfg.diffraction_top_probe_z)
    else:
        top_z = cfg.interface_z + probe_fraction * (cfg.physical_z_max - cfg.interface_z)
    if cfg.diffraction_bottom_probe_z is not None:
        bottom_z = float(cfg.diffraction_bottom_probe_z)
    else:
        bottom_z = cfg.interface_z + probe_fraction * (cfg.physical_z_min - cfg.interface_z)

    if not (cfg.interface_z < top_z < cfg.physical_z_max):
        raise ValueError(
            f"Top diffraction probe z={top_z:g} nm must be in the uniform air layer."
        )
    if not (cfg.physical_z_min < bottom_z < cfg.interface_z):
        raise ValueError(
            f"Bottom diffraction probe z={bottom_z:g} nm must be in the uniform substrate layer."
        )
    return top_z, bottom_z


def _plane_wave_power(
    cfg: SimulationConfig3D,
    *,
    kvec: np.ndarray,
    e_amplitude: np.ndarray,
    outward_normal: np.ndarray,
) -> float:
    h_amplitude = np.cross(kvec, e_amplitude) / (cfg.k0 * complex(cfg.mu_r))
    poynting = 0.5 * np.real(np.cross(e_amplitude, np.conj(h_amplitude)))
    area = (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
    return max(float(np.dot(poynting, outward_normal)) * area, 0.0)


def _relative_phase(kz: complex, z: float, cfg: SimulationConfig3D) -> complex:
    return complex(np.exp(1j * complex(kz) * (float(z) - float(cfg.interface_z))))


def _transmitted_power_at_z(cfg: SimulationConfig3D, z: float) -> float:
    _, _, k_trn, _, _, e_trn = _fresnel_components(cfg)
    e_at_z = e_trn * _relative_phase(k_trn[2], z, cfg)
    return _plane_wave_power(
        cfg,
        kvec=k_trn,
        e_amplitude=e_at_z,
        outward_normal=np.asarray((0.0, 0.0, -1.0), dtype=np.float64),
    )


def _reflected_power_at_z(cfg: SimulationConfig3D, z: float) -> float:
    _, k_ref, _, _, e_ref, _ = _fresnel_components(cfg)
    e_at_z = e_ref * _relative_phase(k_ref[2], z, cfg)
    return _plane_wave_power(
        cfg,
        kvec=k_ref,
        e_amplitude=e_at_z,
        outward_normal=np.asarray((0.0, 0.0, 1.0), dtype=np.float64),
    )


def analytic_volume_absorption_between_z(
    cfg: SimulationConfig3D,
    *,
    bottom_z: float,
    top_z: float | None = None,
) -> dict[str, float | str]:
    """Analytic substrate absorption between two z planes in code units.

    This integral is the closed-form lossy-plane-wave counterpart of
    ``compute_volume_absorption_3d``. It is intentionally limited to the flat
    air/substrate layer and excludes air and PML cells.
    """

    top_limit = float(cfg.interface_z if top_z is None else top_z)
    upper = min(top_limit, float(cfg.interface_z))
    lower = float(bottom_z)
    if lower >= upper:
        return {
            "absorbed_power_code_units": 0.0,
            "A_volume_ref": 0.0,
            "status": "empty_interval",
        }

    eps_imag = float(complex(cfg.eps_substrate).imag)
    incident_power = incident_power_3d(cfg)
    if eps_imag <= 0.0:
        return {
            "absorbed_power_code_units": 0.0,
            "A_volume_ref": 0.0,
            "status": "lossless",
        }

    _, _, k_trn, _, _, e_trn = _fresnel_components(cfg)
    kz = complex(k_trn[2])
    z0 = float(cfg.interface_z)
    exponent_scale = -2.0 * float(np.imag(kz))
    lower_rel = lower - z0
    upper_rel = upper - z0
    if abs(exponent_scale) < 1.0e-15:
        z_integral = upper_rel - lower_rel
    else:
        z_integral = (
            np.exp(exponent_scale * upper_rel) - np.exp(exponent_scale * lower_rel)
        ) / exponent_scale
    e_norm_sq = float(np.real(np.vdot(e_trn, e_trn)))
    area = (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
    absorbed_power = float(0.5 * cfg.k0 * eps_imag * e_norm_sq * area * z_integral)
    absorbed_power = max(absorbed_power, 0.0)
    return {
        "absorbed_power_code_units": absorbed_power,
        "A_volume_ref": absorbed_power / incident_power if incident_power > 0.0 else 0.0,
        "status": "ok",
    }


def _reference_for_bottom_plane(
    cfg: SimulationConfig3D,
    *,
    top_z: float,
    bottom_z: float,
    label: str,
) -> dict[str, Any]:
    ref = fresnel_reference(cfg)
    incident_power = incident_power_3d(cfg)
    reflected_power = _reflected_power_at_z(cfg, top_z)
    transmitted_power = _transmitted_power_at_z(cfg, bottom_z)
    absorbed_power = max(incident_power - reflected_power - transmitted_power, 0.0)
    volume_ref = analytic_volume_absorption_between_z(cfg, bottom_z=bottom_z)
    return {
        "label": label,
        "reference_plane_z_top": float(top_z),
        "reference_plane_z_bottom": float(bottom_z),
        "interface_z": float(cfg.interface_z),
        "incident_power_ref": float(incident_power),
        "reflected_power_ref": float(reflected_power),
        "bottom_transmitted_power_ref": float(transmitted_power),
        "absorbed_power_ref": float(absorbed_power),
        "R_ref": float(reflected_power / incident_power),
        "T_ref_at_bottom_reference_plane": float(transmitted_power / incident_power),
        "A_ref_between_reference_planes": float(absorbed_power / incident_power),
        "A_volume_ref_between_reference_planes": float(volume_ref["A_volume_ref"]),
        "volume_absorption_status": volume_ref["status"],
        "fresnel_R_at_interface": float(ref["R"]),
        "fresnel_T_at_interface": float(ref["T"]),
    }


def compute_flat_layer_reference_3d(cfg: SimulationConfig3D) -> dict[str, Any]:
    """Compute analytic flat-layer R/T/A at probe and port planes."""

    top_probe_z, bottom_probe_z = flat_layer_probe_planes(cfg)
    top_port_z = float(cfg.physical_z_max)
    bottom_port_z = float(cfg.physical_z_min)
    ref = fresnel_reference(cfg)
    _, _, k_trn, _, _, _ = _fresnel_components(cfg)
    probe_reference = _reference_for_bottom_plane(
        cfg,
        top_z=top_probe_z,
        bottom_z=bottom_probe_z,
        label="probe_planes",
    )
    port_reference = _reference_for_bottom_plane(
        cfg,
        top_z=top_port_z,
        bottom_z=bottom_port_z,
        label="port_planes",
    )
    return {
        "method": "flat_layer_analytic_reference",
        "status": "ok",
        "note": FLAT_LAYER_REFERENCE_NOTE,
        "volume_absorption_formula_code_units": VOLUME_ABSORPTION_REFERENCE_FORMULA,
        "r_amplitude": complex(ref["r"]),
        "t_amplitude": complex(ref["t"]),
        "transmitted_kz": complex(k_trn[2]),
        "n_air": _complex_pair(cfg.n_air),
        "n_substrate": _complex_pair(cfg.substrate_index),
        "epsilon_substrate": _complex_pair(cfg.eps_substrate),
        "reference_plane_z_top": probe_reference["reference_plane_z_top"],
        "reference_plane_z_bottom": probe_reference["reference_plane_z_bottom"],
        "interface_z": float(cfg.interface_z),
        "R_ref": probe_reference["R_ref"],
        "T_ref_at_bottom_reference_plane": probe_reference["T_ref_at_bottom_reference_plane"],
        "A_ref_between_reference_planes": probe_reference["A_ref_between_reference_planes"],
        "incident_power_ref": probe_reference["incident_power_ref"],
        "reflected_power_ref": probe_reference["reflected_power_ref"],
        "bottom_transmitted_power_ref": probe_reference["bottom_transmitted_power_ref"],
        "absorbed_power_ref": probe_reference["absorbed_power_ref"],
        "probe_planes": probe_reference,
        "port_planes": port_reference,
        "R_ref_at_port_planes": port_reference["R_ref"],
        "T_ref_at_bottom_port_plane": port_reference["T_ref_at_bottom_reference_plane"],
        "A_ref_between_port_planes": port_reference["A_ref_between_reference_planes"],
    }


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _diff(value: Any, reference: float) -> float | None:
    number = _maybe_float(value)
    return None if number is None else float(number - reference)


def compute_power_consistency_against_flat_reference(
    cfg: SimulationConfig3D,
    reference: dict[str, Any],
    *,
    port_metrics: dict[str, Any] | None,
    probe_metrics: dict[str, Any] | None,
    volume_metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    """Compare Stage-4 power outputs with analytic flat-layer references."""

    del cfg
    probe_ref = reference["probe_planes"]
    port_ref = reference["port_planes"]
    R_probe_ref = float(probe_ref["R_ref"])
    T_probe_ref = float(probe_ref["T_ref_at_bottom_reference_plane"])
    A_probe_ref = float(probe_ref["A_ref_between_reference_planes"])
    R_port_ref = float(port_ref["R_ref"])
    T_port_ref = float(port_ref["T_ref_at_bottom_reference_plane"])
    A_port_ref = float(port_ref["A_ref_between_reference_planes"])

    port_R = _maybe_float(None if port_metrics is None else port_metrics.get("R_total"))
    port_T = _maybe_float(None if port_metrics is None else port_metrics.get("T_total"))
    port_A = _maybe_float(None if port_metrics is None else port_metrics.get("A_balance"))
    probe_R = _maybe_float(None if probe_metrics is None else probe_metrics.get("R_total"))
    probe_T = _maybe_float(None if probe_metrics is None else probe_metrics.get("T_total"))
    probe_A = _maybe_float(None if probe_metrics is None else probe_metrics.get("A_balance"))
    flux_R = _maybe_float(None if probe_metrics is None else probe_metrics.get("R_total_from_net_flux"))
    flux_T = _maybe_float(None if probe_metrics is None else probe_metrics.get("T_total_from_net_flux"))
    flux_A = _maybe_float(None if probe_metrics is None else probe_metrics.get("A_balance_from_net_flux"))
    volume_A = _maybe_float(None if volume_metrics is None else volume_metrics.get("A_volume_total"))

    diffs = {
        "R_port_minus_R_ref": None if port_R is None else port_R - R_port_ref,
        "T_port_minus_T_ref": None if port_T is None else port_T - T_port_ref,
        "A_port_minus_A_ref": None if port_A is None else port_A - A_port_ref,
        "R_probe_minus_R_ref": None if probe_R is None else probe_R - R_probe_ref,
        "T_probe_minus_T_ref": None if probe_T is None else probe_T - T_probe_ref,
        "A_probe_minus_A_ref": None if probe_A is None else probe_A - A_probe_ref,
        "R_flux_minus_R_ref": None if flux_R is None else flux_R - R_probe_ref,
        "T_flux_minus_T_ref": None if flux_T is None else flux_T - T_probe_ref,
        "A_flux_minus_A_ref": None if flux_A is None else flux_A - A_probe_ref,
        "A_volume_minus_A_ref": None if volume_A is None else volume_A - A_port_ref,
        "closure_error_port_volume": None
        if port_R is None or port_T is None or volume_A is None
        else port_R + port_T + volume_A - 1.0,
    }
    return {
        "method": "power_consistency_against_flat_layer_reference",
        "status": "ok",
        "note": (
            "Port and volume absorption are compared at physical port planes. "
            "Probe_eh_fourier and net_flux are compared at diffraction probe planes."
        ),
        "reference_values_by_method": {
            "port": {
                "R_ref": R_port_ref,
                "T_ref": T_port_ref,
                "A_ref": A_port_ref,
                "reference_plane_z_top": port_ref["reference_plane_z_top"],
                "reference_plane_z_bottom": port_ref["reference_plane_z_bottom"],
            },
            "volume_absorption": {
                "A_ref": A_port_ref,
                "reference_plane_z_top": port_ref["reference_plane_z_top"],
                "reference_plane_z_bottom": port_ref["reference_plane_z_bottom"],
            },
            "probe_eh_fourier": {
                "R_ref": R_probe_ref,
                "T_ref": T_probe_ref,
                "A_ref": A_probe_ref,
                "reference_plane_z_top": probe_ref["reference_plane_z_top"],
                "reference_plane_z_bottom": probe_ref["reference_plane_z_bottom"],
            },
            "net_flux": {
                "R_ref": R_probe_ref,
                "T_ref": T_probe_ref,
                "A_ref": A_probe_ref,
                "reference_plane_z_top": probe_ref["reference_plane_z_top"],
                "reference_plane_z_bottom": probe_ref["reference_plane_z_bottom"],
            },
        },
        "observed": {
            "port": {"R": port_R, "T": port_T, "A": port_A},
            "probe_eh_fourier": {"R": probe_R, "T": probe_T, "A": probe_A},
            "net_flux": {"R": flux_R, "T": flux_T, "A": flux_A},
            "volume_absorption": {"A": volume_A},
        },
        "diffs": diffs,
        **diffs,
    }


def write_flat_layer_reference_outputs(
    out_dir: Path,
    cfg: SimulationConfig3D,
    comm: MPI.Intracomm,
    *,
    port_metrics: dict[str, Any] | None,
    probe_metrics: dict[str, Any] | None,
    volume_metrics: dict[str, Any] | None,
) -> dict[str, Any]:
    """Write flat-layer analytic reference and consistency diagnostics."""

    reference = compute_flat_layer_reference_3d(cfg)
    consistency = compute_power_consistency_against_flat_reference(
        cfg,
        reference,
        port_metrics=port_metrics,
        probe_metrics=probe_metrics,
        volume_metrics=volume_metrics,
    )
    if comm.rank == 0:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "flat_layer_reference.json").write_text(
            json.dumps(reference, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        (out_dir / "power_consistency.json").write_text(
            json.dumps(consistency, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
    comm.barrier()
    return {
        "flat_layer_reference_file": "flat_layer_reference.json",
        "power_consistency_file": "power_consistency.json",
        "flat_layer_reference": reference,
        "power_consistency": consistency,
    }
