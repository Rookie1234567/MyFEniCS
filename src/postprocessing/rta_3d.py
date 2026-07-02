from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import ufl
from mpi4py import MPI

from dolfinx import fem

from ..common.config_3d import SimulationConfig3D
from .diffraction_3d import _json_default


VOLUME_ABSORPTION_POWER_SOURCE = "volume_integral_Im_epsilon_E2"
VOLUME_ABSORPTION_NORMALIZATION_NOTE = (
    "A_volume uses the current Stage-4 code-unit normalization: "
    "P_abs = integral 0.5*k0^2*Im(epsilon_r)*|E_total|^2 dV over physical "
    "material cells, divided by incident_power_code_units. PML cells and air "
    "cells are deliberately excluded from material volume absorption."
)


def _complex_pair(value: complex) -> list[float]:
    number = complex(value)
    return [float(number.real), float(number.imag)]


def _global_cell_count(mesh_data, tag: int) -> int:
    local_count = len(mesh_data.cell_tags.find(tag))
    return int(mesh_data.mesh.comm.allreduce(local_count, op=MPI.SUM))


def _region_volume(mesh_data, tag: int) -> float:
    msh = mesh_data.mesh
    dx = ufl.Measure("dx", domain=msh, subdomain_data=mesh_data.cell_tags)
    local = fem.assemble_scalar(fem.form(ufl.as_ufl(1.0) * dx(tag)))
    return float(np.real(msh.comm.allreduce(local, op=MPI.SUM)))


def _region_absorbed_power(mesh_data, cfg: SimulationConfig3D, E_total, tag: int, eps_r: complex) -> float:
    msh = mesh_data.mesh
    dx = ufl.Measure("dx", domain=msh, subdomain_data=mesh_data.cell_tags)
    field_abs2 = ufl.real(ufl.inner(E_total, E_total))
    density_scale = 0.5 * cfg.k0**2 * float(complex(eps_r).imag)
    local = fem.assemble_scalar(fem.form(density_scale * field_abs2 * dx(tag)))
    absorbed = float(np.real(msh.comm.allreduce(local, op=MPI.SUM)))
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
    absorbed_power = _region_absorbed_power(mesh_data, cfg, E_total, tag, eps_r)
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


def compute_volume_absorption_3d(
    mesh_data,
    cfg: SimulationConfig3D,
    E_total,
    out_dir: Path,
    *,
    incident_power: float,
    port_metrics: dict[str, Any] | None = None,
    probe_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compute material volume absorption from the total electric field.

    This is a material-loss diagnostic, not a PML-loss diagnostic.  The input
    field must be the total field; callers using a scattered formulation should
    pass E_background + E_scattered.
    """

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
        "formula_code_units": "P_abs = integral 0.5*k0^2*Im(epsilon_r)*|E_total|^2 dV",
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
                source="dtn_auxiliary_port_amplitudes",
            )
        )
    else:
        rows.append(
            _summary_row(
                method="port",
                role="primary",
                status="ok",
                source=port_metrics.get("diffraction_total_power_source", "dtn_auxiliary_port_amplitudes"),
                R=port_metrics.get("R_total"),
                T=port_metrics.get("T_total"),
                A=port_metrics.get("A_balance"),
            )
        )

    if probe_metrics is None:
        rows.append(
            _summary_row(
                method="probe_eh_fourier",
                role="cross_check",
                status="skipped",
                source="eh_fourier_orders",
            )
        )
        rows.append(
            _summary_row(
                method="net_flux",
                role="diagnostic",
                status="skipped",
                source="sampled_poynting_flux",
            )
        )
    else:
        rows.append(
            _summary_row(
                method="probe_eh_fourier",
                role="cross_check",
                status="ok",
                source=probe_metrics.get("diffraction_total_power_source", "eh_fourier_orders"),
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
                source="sampled_poynting_flux",
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
