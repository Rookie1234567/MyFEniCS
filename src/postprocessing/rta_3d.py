from __future__ import annotations

import csv
import json
from math import isfinite
from pathlib import Path
from typing import Any

import numpy as np
import ufl
from mpi4py import MPI

from dolfinx import fem

from ..common.config_3d import SimulationConfig3D
from .diffraction_3d import (
    DIAGNOSTIC_EH_FOURIER_PROBE_POWER_SOURCE,
    DIAGNOSTIC_SAMPLED_NET_FLUX_POWER_SOURCE,
    _json_default,
)


VOLUME_ABSORPTION_POWER_SOURCE = "volume_integral_Im_epsilon_E2"
VOLUME_ABSORPTION_NORMALIZATION_NOTE = (
    "A_volume uses the current Stage-4 code-unit normalization: "
    "P_abs = integral 0.5*k0*Im(epsilon_r)*|E_total|^2 dV over physical "
    "material cells, divided by incident_power_code_units. PML cells and air "
    "cells are deliberately excluded from material volume absorption. The k0 "
    "factor follows from H_code=curl(E)/(i*k0*mu_r) and the corresponding "
    "Poynting balance."
)


def _complex_pair(value: complex) -> list[float]:
    number = complex(value)
    return [float(number.real), float(number.imag)]


def _global_cell_count(mesh_data, tag: int) -> int:
    local_count = len(mesh_data.cell_tags.find(tag))
    return int(mesh_data.mesh.comm.allreduce(local_count, op=MPI.SUM))


def _gate_cd_volume_measure_metadata(cfg, volume_quadrature_metadata):
    """Validate the opt-in Gate-CD volume rule for postprocessing measures."""

    if volume_quadrature_metadata is None:
        return None
    if getattr(cfg, "geometry_kind", None) != "task40_gate_cd_mapped":
        raise ValueError("explicit volume quadrature is restricted to Gate-CD")
    if not isinstance(volume_quadrature_metadata, (tuple, list)) or len(
        volume_quadrature_metadata
    ) != 2:
        raise ValueError("Gate-CD volume quadrature requires curl and mass metadata")
    normalized = tuple(dict(item) for item in volume_quadrature_metadata)
    if normalized[0] != normalized[1]:
        raise ValueError("Gate-CD postprocessing requires one shared curl/mass volume rule")
    metadata = normalized[0]
    if set(metadata) != {"quadrature_degree", "quadrature_rule"}:
        raise ValueError("Gate-CD volume quadrature metadata has unsupported fields")
    if metadata.get("quadrature_degree") not in (15, 21, 27) or metadata.get(
        "quadrature_rule"
    ) != "default":
        raise ValueError("Gate-CD selected volume quadrature must be q15/q21/q27 default")
    return metadata


def _volume_dx_measure(mesh_data, cfg, volume_quadrature_metadata=None):
    metadata = _gate_cd_volume_measure_metadata(cfg, volume_quadrature_metadata)
    if metadata is None:
        return ufl.Measure(
            "dx", domain=mesh_data.mesh, subdomain_data=mesh_data.cell_tags
        )
    return ufl.Measure(
        "dx",
        domain=mesh_data.mesh,
        subdomain_data=mesh_data.cell_tags,
        metadata=metadata,
    )


def _region_volume(mesh_data, tag: int) -> float:
    msh = mesh_data.mesh
    dx = ufl.Measure("dx", domain=msh, subdomain_data=mesh_data.cell_tags)
    local = fem.assemble_scalar(fem.form(ufl.as_ufl(1.0) * dx(tag)))
    volume = float(np.real(msh.comm.allreduce(local, op=MPI.SUM)))
    if not isfinite(volume) or volume < 0.0:
        raise ValueError(f"non-finite or negative tagged volume for tag {tag}")
    return volume


def _region_absorbed_power(
    mesh_data,
    cfg: SimulationConfig3D,
    E_total,
    tag: int,
    eps_r: complex,
    volume_quadrature_metadata=None,
) -> float:
    msh = mesh_data.mesh
    dx = _volume_dx_measure(mesh_data, cfg, volume_quadrature_metadata)
    field_abs2 = ufl.real(ufl.inner(E_total, E_total))
    density_scale = 0.5 * cfg.k0 * float(complex(eps_r).imag)
    local = fem.assemble_scalar(fem.form(density_scale * field_abs2 * dx(tag)))
    absorbed = float(np.real(msh.comm.allreduce(local, op=MPI.SUM)))
    if not isfinite(absorbed):
        raise ValueError(f"non-finite absorbed power for tag {tag}")
    return max(absorbed, 0.0)


def _region_absorption(
    mesh_data,
    cfg: SimulationConfig3D,
    E_total,
    *,
    name: str,
    tag: int,
    eps_r: complex,
    n_value: complex,
    material_label: str | None,
    incident_power: float,
    volume_quadrature_metadata=None,
) -> dict[str, Any]:
    cell_count = _global_cell_count(mesh_data, tag)
    eps_imag = float(complex(eps_r).imag)
    region = {
        "name": name,
        "tag": int(tag),
        "cell_count": cell_count,
        "volume_nm3": _region_volume(mesh_data, tag) if cell_count > 0 else 0.0,
        "n_complex": _complex_pair(n_value),
        "epsilon_r_complex": _complex_pair(eps_r),
        "Im_epsilon_r": eps_imag,
        "material_label": material_label,
    }
    if cell_count <= 0:
        region.update(
            {
                "status": "missing",
                "reason": f"no cells tagged as {name}",
                "absorbed_power_code_units": None,
                "A_volume": None,
            }
        )
        return region
    if eps_imag <= 0.0:
        region.update(
            {
                "status": "lossless",
                "reason": "Im(epsilon_r) <= 0",
                "absorbed_power_code_units": 0.0,
                "A_volume": 0.0 if incident_power > 0.0 else None,
            }
        )
        return region
    absorbed_power = _region_absorbed_power(
        mesh_data, cfg, E_total, tag, eps_r, volume_quadrature_metadata
    )
    region.update(
        {
            "status": "ok",
            "reason": None,
            "absorbed_power_code_units": absorbed_power,
            "A_volume": absorbed_power / incident_power if incident_power > 0.0 else None,
        }
    )
    return region


def _maybe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _validated_gate_cd_region_absorption(
    regions: dict[str, dict[str, Any]],
    expected_labels: tuple[str, ...],
) -> tuple[dict[str, float], float]:
    """Reject a partial/non-finite physical loss map instead of summing what remains."""

    if set(regions) != set(expected_labels):
        raise ValueError("gate_cd volume-loss results do not cover every mapped region")
    region_values: dict[str, float] = {}
    for label in expected_labels:
        facts = regions[label]
        if int(facts.get("cell_count", -1)) <= 0:
            raise ValueError(
                f"gate_cd volume-loss tag {label} has no cells"
            )
        if facts.get("status") not in {"ok", "lossless"}:
            raise ValueError(
                f"gate_cd volume-loss tag {label} is not measurable: {facts.get('status')}"
            )
        area = _maybe_float(facts.get("A_volume"))
        power = _maybe_float(facts.get("absorbed_power_code_units"))
        if area is None or power is None or not isfinite(area) or not isfinite(power):
            raise ValueError(f"gate_cd volume-loss tag {label} has a missing/non-finite result")
        region_values[label] = area
    total = float(sum(region_values.values()))
    if not isfinite(total):
        raise ValueError("gate_cd total A_volume is non-finite")
    return region_values, total


def compute_volume_absorption_3d(
    mesh_data,
    cfg: SimulationConfig3D,
    E_total,
    out_dir: Path,
    *,
    incident_power: float,
    port_metrics: dict[str, Any] | None = None,
    probe_metrics: dict[str, Any] | None = None,
    volume_quadrature_metadata=None,
) -> dict[str, Any]:
    """Compute material volume absorption from the total electric field.

    This is a material-loss diagnostic, not a PML-loss diagnostic.  The input
    field must be the total field; callers using a scattered formulation should
    pass E_background + E_scattered.
    """

    selected_volume_metadata = _gate_cd_volume_measure_metadata(
        cfg, volume_quadrature_metadata
    )
    if cfg.physical_material_regions is not None:
        from ..common.gate_cd_materials import validate_gate_cd_region_entries

        entries = validate_gate_cd_region_entries(cfg.physical_material_regions)
        if cfg.geometry_kind != "task40_gate_cd_mapped":
            raise ValueError(
                "explicit volume material reporting is restricted to gate_cd"
            )
        if any(str(entry["label"]) == "Air" for entry in entries) and complex(
            next(entry["epsilon_r"] for entry in entries if entry["label"] == "Air")
        ).imag != 0.0:
            raise ValueError("gate_cd air must be lossless before it can be excluded from A_volume")
        regions: dict[str, Any] = {}
        for entry in entries:
            label = str(entry["label"])
            regions[label] = _region_absorption(
                mesh_data,
                cfg,
                E_total,
                name=label,
                tag=int(entry["tag"]),
                eps_r=complex(entry["epsilon_r"]),
                n_value=complex(entry["n_complex"]),
                material_label=str(entry["material_name"]),
                incident_power=incident_power,
                volume_quadrature_metadata=volume_quadrature_metadata,
            )
        expected_labels = tuple(str(entry["label"]) for entry in entries)
        region_A, A_volume_total = _validated_gate_cd_region_absorption(
            regions, expected_labels
        )
        port_R = _maybe_float(
            None if port_metrics is None else port_metrics.get("R_total")
        )
        port_T = _maybe_float(
            None if port_metrics is None else port_metrics.get("T_total")
        )
        port_A = _maybe_float(
            None if port_metrics is None else port_metrics.get("A_balance")
        )
        probe_A = _maybe_float(
            None if probe_metrics is None else probe_metrics.get("A_balance")
        )
        flux_A = _maybe_float(
            None
            if probe_metrics is None
            else probe_metrics.get("A_balance_from_net_flux")
        )
        A_substrate = region_A.get("Si_substrate")
        payload: dict[str, Any] = {
            "method": "volume_absorption",
            "role": "absorption_check",
            "status": "ok",
            "power_source": VOLUME_ABSORPTION_POWER_SOURCE,
            "field_model_for_absorption": "total_field",
            "incident_power_code_units": float(incident_power),
            "formula_code_units": "P_abs = integral 0.5*k0*Im(epsilon_r)*|E_total|^2 dV",
            "epsilon_definition": "epsilon_r = n^2; the absorption integrand uses Im(epsilon_r), not Im(n)",
            "pml_cells_excluded": True,
            "port_halfspaces_excluded": True,
            "air_cells_included_after_lossless_validation": True,
            "normalization_note": VOLUME_ABSORPTION_NORMALIZATION_NOTE,
            "material_region_map": [
                {
                    "tag": int(entry["tag"]),
                    "label": str(entry["label"]),
                    "material_name": str(entry["material_name"]),
                    "epsilon_r_complex": _complex_pair(complex(entry["epsilon_r"])),
                }
                for entry in entries
            ],
            "regions": regions,
            "A_volume_by_region": region_A,
            "A_grating": None,
            "A_substrate": A_substrate,
            "A_volume_grating": None,
            "A_volume_substrate": A_substrate,
            "A_volume_total": A_volume_total,
            "A_port_balance_minus_A_volume_total": None
            if port_A is None
            else float(port_A - A_volume_total),
            "A_probe_balance_minus_A_volume_total": None
            if probe_A is None
            else float(probe_A - A_volume_total),
            "A_flux_minus_A_volume_total": None
            if flux_A is None
            else float(flux_A - A_volume_total),
            "energy_closure_error_port_volume": None
            if port_R is None or port_T is None
            else float(port_R + port_T + A_volume_total - 1.0),
        }
        if selected_volume_metadata is not None:
            payload["volume_quadrature_metadata"] = selected_volume_metadata
        if mesh_data.mesh.comm.rank == 0:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "volume_absorption.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
                encoding="utf-8",
            )
        mesh_data.mesh.comm.barrier()
        return payload

    regions = {
        "grating": _region_absorption(
            mesh_data,
            cfg,
            E_total,
            name="grating",
            tag=cfg.tags.grating,
            eps_r=cfg.eps_grating,
            n_value=cfg.grating_index,
            material_label=cfg.grating_material_label,
            incident_power=incident_power,
            volume_quadrature_metadata=volume_quadrature_metadata,
        ),
        "substrate": _region_absorption(
            mesh_data,
            cfg,
            E_total,
            name="substrate",
            tag=cfg.tags.substrate,
            eps_r=cfg.eps_substrate,
            n_value=cfg.substrate_index,
            material_label=cfg.substrate_material_label,
            incident_power=incident_power,
            volume_quadrature_metadata=volume_quadrature_metadata,
        ),
    }
    A_grating = _maybe_float(regions["grating"]["A_volume"])
    A_substrate = _maybe_float(regions["substrate"]["A_volume"])
    A_volume_total = float(sum(value for value in (A_grating, A_substrate) if value is not None))

    port_R = _maybe_float(None if port_metrics is None else port_metrics.get("R_total"))
    port_T = _maybe_float(None if port_metrics is None else port_metrics.get("T_total"))
    port_A = _maybe_float(None if port_metrics is None else port_metrics.get("A_balance"))
    probe_A = _maybe_float(None if probe_metrics is None else probe_metrics.get("A_balance"))
    flux_A = _maybe_float(None if probe_metrics is None else probe_metrics.get("A_balance_from_net_flux"))
    payload: dict[str, Any] = {
        "method": "volume_absorption",
        "role": "absorption_check",
        "status": "ok",
        "power_source": VOLUME_ABSORPTION_POWER_SOURCE,
        "field_model_for_absorption": "total_field",
        "incident_power_code_units": float(incident_power),
        "formula_code_units": "P_abs = integral 0.5*k0*Im(epsilon_r)*|E_total|^2 dV",
        "epsilon_definition": "epsilon_r = n^2; the absorption integrand uses Im(epsilon_r), not Im(n)",
        "pml_cells_excluded": True,
        "air_cells_excluded": True,
        "normalization_note": VOLUME_ABSORPTION_NORMALIZATION_NOTE,
        "regions": regions,
        "A_grating": A_grating,
        "A_substrate": A_substrate,
        "A_volume_grating": A_grating,
        "A_volume_substrate": A_substrate,
        "A_volume_total": A_volume_total,
        "A_port_balance_minus_A_volume_total": None if port_A is None else float(port_A - A_volume_total),
        "A_probe_balance_minus_A_volume_total": None if probe_A is None else float(probe_A - A_volume_total),
        "A_flux_minus_A_volume_total": None if flux_A is None else float(flux_A - A_volume_total),
        "energy_closure_error_port_volume": None
        if port_R is None or port_T is None
        else float(port_R + port_T + A_volume_total - 1.0),
    }
    if selected_volume_metadata is not None:
        payload["volume_quadrature_metadata"] = selected_volume_metadata

    if mesh_data.mesh.comm.rank == 0:
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "volume_absorption.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
    mesh_data.mesh.comm.barrier()
    return payload


def _summary_row(
    *,
    method: str,
    role: str,
    status: str,
    source: str,
    R: Any = None,
    T: Any = None,
    A: Any = None,
) -> dict[str, Any]:
    return {
        "method": method,
        "R": "" if R is None else float(R),
        "T": "" if T is None else float(T),
        "A": "" if A is None else float(A),
        "role": role,
        "status": status,
        "source": source,
    }


def power_summary_rows(
    *,
    port_metrics: dict[str, Any] | None,
    probe_metrics: dict[str, Any] | None,
    volume_metrics: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    rows = []
    if port_metrics is None:
        rows.append(
            _summary_row(
                method="port",
                role="primary",
                status="skipped",
                source="dtn_port_modal_amplitudes",
            )
        )
    else:
        rows.append(
            _summary_row(
                method="port",
                role="primary",
                status="ok",
                source=port_metrics.get(
                    "power_source",
                    port_metrics.get("diffraction_total_power_source", "dtn_port_modal_amplitudes"),
                ),
                R=port_metrics.get("R_total"),
                T=port_metrics.get("T_total"),
                A=port_metrics.get("A_balance"),
            )
        )

    if probe_metrics is None:
        rows.append(
            _summary_row(
                method="probe_eh_fourier",
                role="diagnostic",
                status="skipped",
                source=DIAGNOSTIC_EH_FOURIER_PROBE_POWER_SOURCE,
            )
        )
        rows.append(
            _summary_row(
                method="net_flux",
                role="diagnostic",
                status="skipped",
                source=DIAGNOSTIC_SAMPLED_NET_FLUX_POWER_SOURCE,
            )
        )
    else:
        rows.append(
            _summary_row(
                method="probe_eh_fourier",
                role="diagnostic",
                status="ok",
                source=probe_metrics.get("power_source", DIAGNOSTIC_EH_FOURIER_PROBE_POWER_SOURCE),
                R=probe_metrics.get("R_total"),
                T=probe_metrics.get("T_total"),
                A=probe_metrics.get("A_balance"),
            )
        )
        rows.append(
            _summary_row(
                method="net_flux",
                role="diagnostic",
                status="ok",
                source=DIAGNOSTIC_SAMPLED_NET_FLUX_POWER_SOURCE,
                R=probe_metrics.get("R_total_from_net_flux"),
                T=probe_metrics.get("T_total_from_net_flux"),
                A=probe_metrics.get("A_balance_from_net_flux"),
            )
        )

    if volume_metrics is None:
        rows.append(
            _summary_row(
                method="volume_absorption",
                role="absorption_check",
                status="skipped",
                source=VOLUME_ABSORPTION_POWER_SOURCE,
            )
        )
    else:
        rows.append(
            _summary_row(
                method="volume_absorption",
                role="absorption_check",
                status=volume_metrics.get("status", "ok"),
                source=volume_metrics.get("power_source", VOLUME_ABSORPTION_POWER_SOURCE),
                A=volume_metrics.get("A_volume_total"),
            )
        )
    return rows


def write_power_summary_csv(
    out_dir: Path,
    comm: MPI.Intracomm,
    *,
    port_metrics: dict[str, Any] | None,
    probe_metrics: dict[str, Any] | None,
    volume_metrics: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    rows = power_summary_rows(
        port_metrics=port_metrics,
        probe_metrics=probe_metrics,
        volume_metrics=volume_metrics,
    )
    if comm.rank == 0:
        out_dir.mkdir(parents=True, exist_ok=True)
        with (out_dir / "power_summary.csv").open("w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=["method", "R", "T", "A", "role", "status", "source"])
            writer.writeheader()
            writer.writerows(rows)
    comm.barrier()
    return rows
