from __future__ import annotations

import csv
import json
from pathlib import Path

import numpy as np
import ufl

from dolfinx import geometry
from dolfinx import fem
from mpi4py import MPI
from petsc4py import PETSc

from ..common.config import SimulationConfig
from ..common.materials import relative_permittivity
from .near_field_2d import near_field_reference_areas_2d, near_field_regions_2d


def _json_default(value):
    if isinstance(value, complex):
        return [value.real, value.imag]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot JSON serialize {type(value)!r}")


def _positive_sqrt(value: complex) -> complex:
    root = np.sqrt(complex(value))
    if root.imag < -1e-14 or (abs(root.imag) < 1e-14 and root.real < 0):
        root = -root
    return root


def _probe_y_locations(cfg: SimulationConfig) -> tuple[float, float]:
    fraction = 0.95
    top_gap = cfg.physical_y_max - cfg.grating_y_max
    if top_gap <= 0:
        raise ValueError(
            "The top uniform air probe line requires physical_y_max > grating_y_max."
        )
    bottom_gap = cfg.substrate_y_max - cfg.substrate_y_min
    if bottom_gap <= 0:
        raise ValueError(
            "The bottom substrate probe line requires substrate_y_max > substrate_y_min."
        )
    top_y = cfg.grating_y_max + fraction * top_gap
    bottom_y = cfg.substrate_y_max - fraction * bottom_gap
    return float(top_y), float(bottom_y)


def _sample_field_at_points(
    function, x_values: np.ndarray, y_values: np.ndarray
) -> np.ndarray:
    msh = function.function_space.mesh
    comm = msh.comm
    points = np.zeros((len(x_values), 3), dtype=np.float64)
    points[:, 0] = x_values
    points[:, 1] = y_values

    tree = geometry.bb_tree(msh, msh.topology.dim)
    candidates = geometry.compute_collisions_points(tree, points)
    collisions = geometry.compute_colliding_cells(msh, candidates, points)
    local_indices: list[int] = []
    local_cells: list[int] = []
    for i in range(len(x_values)):
        links = collisions.links(i)
        if len(links) >= 1:
            local_indices.append(i)
            local_cells.append(int(links[0]))

    if local_indices:
        local_points = points[np.asarray(local_indices, dtype=np.int32)]
        local_values = function.eval(
            local_points, np.asarray(local_cells, dtype=np.int32)
        )
        local_values = np.asarray(local_values, dtype=np.complex128)
        if local_values.ndim == 1:
            local_values = local_values.reshape((-1, 1))
    else:
        local_values = np.zeros((0, 0), dtype=np.complex128)

    packets = comm.allgather((local_indices, local_values))
    value_width = 0
    for _, packet_values in packets:
        if packet_values.size:
            value_width = int(packet_values.shape[1])
            break
    if value_width == 0:
        raise RuntimeError("No rank could evaluate the requested power probe points.")

    values = np.zeros((len(x_values), value_width), dtype=np.complex128)
    filled = np.zeros(len(x_values), dtype=bool)
    for packet_indices, packet_values in packets:
        if not packet_indices:
            continue
        packet_indices_array = np.asarray(packet_indices, dtype=np.int32)
        for local_row, point_index in enumerate(packet_indices_array):
            if not filled[point_index]:
                values[point_index] = packet_values[local_row]
                filled[point_index] = True

    if not np.all(filled):
        missing = np.flatnonzero(~filled)[:5]
        examples = ", ".join(
            f"(x={x_values[i]:.6g}, y={y_values[i]:.6g})" for i in missing
        )
        raise RuntimeError(
            f"No mesh cell found for {np.count_nonzero(~filled)} power probe points: {examples}"
        )
    return values


def _wrap_x_values(
    x_values: np.ndarray, cfg: SimulationConfig
) -> tuple[np.ndarray, np.ndarray]:
    """Map raw x coordinates into one cell and return the matching Floquet phase."""
    shifted = (x_values - cfg.x_min) / cfg.period_x
    periods = np.floor(shifted).astype(np.int64)
    wrapped = x_values - periods * cfg.period_x

    too_high = wrapped >= cfg.x_max
    if np.any(too_high):
        wrapped[too_high] -= cfg.period_x
        periods[too_high] += 1

    too_low = wrapped < cfg.x_min
    if np.any(too_low):
        wrapped[too_low] += cfg.period_x
        periods[too_low] -= 1

    phases = np.exp(1j * cfg.kx * periods * cfg.period_x)
    return wrapped, phases


def _sample_field_on_wrapped_line(
    E_total, raw_x_values: np.ndarray, y: float, cfg: SimulationConfig
) -> np.ndarray:
    wrapped_x, floquet_phases = _wrap_x_values(raw_x_values, cfg)
    y_values = np.full(len(raw_x_values), y, dtype=np.float64)
    values = _sample_field_at_points(E_total, wrapped_x, y_values)
    return values * floquet_phases[:, None]


def _sample_scalar_on_wrapped_line(
    function, raw_x_values: np.ndarray, y: float, cfg: SimulationConfig
) -> np.ndarray:
    wrapped_x, floquet_phases = _wrap_x_values(raw_x_values, cfg)
    y_values = np.full(len(raw_x_values), y, dtype=np.float64)
    values = _sample_field_at_points(function, wrapped_x, y_values).reshape(
        (len(raw_x_values), -1)
    )[:, 0]
    return values * floquet_phases


def _scaled_hz_function(E_total, cfg: SimulationConfig):
    msh = E_total.function_space.mesh
    degree = max(int(cfg.nedelec_degree), 1)
    Q = fem.functionspace(msh, ("DG", degree))
    curl_z = ufl.Dx(E_total[1], 0) - ufl.Dx(E_total[0], 1)
    interpolation_points = Q.element.interpolation_points
    if callable(interpolation_points):
        interpolation_points = interpolation_points()
    expression = fem.Expression(curl_z / PETSc.ScalarType(1j), interpolation_points)
    hz_scaled = fem.Function(Q, name="Hz_scaled")
    hz_scaled.interpolate(expression)
    hz_scaled.x.scatter_forward()
    return hz_scaled


def _scaled_hx_function(E_total, cfg: SimulationConfig):
    msh = E_total.function_space.mesh
    degree = max(int(cfg.nedelec_degree), 1)
    Q = fem.functionspace(msh, ("DG", degree))
    interpolation_points = Q.element.interpolation_points
    if callable(interpolation_points):
        interpolation_points = interpolation_points()
    expression = fem.Expression(
        ufl.Dx(E_total, 1) / PETSc.ScalarType(1j), interpolation_points
    )
    hx_scaled = fem.Function(Q, name="Hx_scaled")
    hx_scaled.interpolate(expression)
    hx_scaled.x.scatter_forward()
    return hx_scaled


def _line_field_and_scaled_hz(
    E_total,
    hz_scaled,
    y: float,
    cfg: SimulationConfig,
    num_points: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Sample E and H_z up to the common factor 1/(omega*mu0).

    The solved 2D field is E=(Ex,Ey). With exp(-i omega t) convention,
    H_z = (d_x Ey - d_y Ex)/(i omega mu0). Since all powers are normalized by
    the same incident power, this routine returns H_z scaled by omega*mu0.
    """
    x_values = (
        cfg.x_min
        + (np.arange(num_points, dtype=np.float64) + 0.5) * cfg.period_x / num_points
    )
    center = _sample_field_on_wrapped_line(E_total, x_values, y, cfg)
    scaled_hz = _sample_scalar_on_wrapped_line(hz_scaled, x_values, y, cfg)
    return x_values, center, scaled_hz


def _line_scalar_and_scaled_hx(
    E_total,
    hx_scaled,
    y: float,
    cfg: SimulationConfig,
    num_points: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Sample TE Ez and Hx_scaled=dEz/dy/i on a wrapped horizontal line."""
    x_values = (
        cfg.x_min
        + (np.arange(num_points, dtype=np.float64) + 0.5) * cfg.period_x / num_points
    )
    ez_values = _sample_scalar_on_wrapped_line(E_total, x_values, y, cfg)
    hx_values = _sample_scalar_on_wrapped_line(hx_scaled, x_values, y, cfg)
    return x_values, ez_values, hx_values


def _fourier_line_coefficients(
    x_values: np.ndarray, values: np.ndarray, cfg: SimulationConfig, order_count: int
):
    coeffs: dict[int, complex] = {}
    for order in range(-order_count, order_count + 1):
        alpha = cfg.kx + 2.0 * np.pi * order / cfg.period_x
        coeffs[order] = complex(np.mean(values * np.exp(-1j * alpha * x_values)))
    return coeffs


def _modal_admittance(k_medium: complex, beta: complex) -> complex:
    return complex(k_medium**2 / beta)


def _modal_power_factor(admittance: complex) -> float:
    factor = 0.5 * np.real(admittance)
    return float(max(factor, 0.0))


def _modal_power_on_plane(
    period: float,
    power_factor: float,
    boundary_coefficient: complex,
    power_carrying: bool,
) -> float:
    """Evaluate modal power from the coefficient on the actual port plane."""

    if not power_carrying:
        return 0.0
    return float(period) * float(power_factor) * abs(complex(boundary_coefficient)) ** 2


def _is_propagating(beta: complex, dispersion_value: complex | None = None) -> bool:
    """Return whether an outgoing order carries normal real power.

    Propagating modes in lossy media have complex beta. Requiring Im(beta)=0
    drops their transmitted power and mislabels it as absorption. The sign of
    Re(beta**2) separates those modes from below-cutoff evanescent orders.
    """

    beta = complex(beta)
    if beta.real <= 1.0e-12:
        return False
    value = complex(beta**2 if dispersion_value is None else dispersion_value)
    scale = max(abs(value), abs(beta) ** 2, 1.0e-30)
    return value.real > -1.0e-10 * scale


def _volume_absorption_metrics(
    mesh_data,
    cfg: SimulationConfig,
    E_total,
    incident_power: float,
    field_model: str,
) -> dict[str, object]:
    msh = mesh_data.mesh
    dx = ufl.Measure("dx", msh, subdomain_data=mesh_data.cell_tags)
    d_physical = dx((cfg.tags.air, cfg.tags.substrate, cfg.tags.grating))
    eps = relative_permittivity(mesh_data, cfg)
    eps_imag = ufl.imag(eps)
    field_abs2 = ufl.inner(E_total, E_total)
    local_abs = fem.assemble_scalar(
        fem.form(0.5 * cfg.k0**2 * eps_imag * field_abs2 * d_physical)
    )
    absorbed_power = float(np.real(msh.comm.allreduce(local_abs, op=MPI.SUM)))
    absorbed_power = max(absorbed_power, 0.0)
    return {
        "field_model_for_absorption": field_model,
        "absorbed_power_weighted": absorbed_power,
        "A_volume": absorbed_power / incident_power if incident_power > 0 else None,
        "absorption_volume_note": (
            "Volume absorption uses 0.5*k0^2*Im(epsilon_r)*|E|^2 integrated only over "
            "physical air/substrate/grating cells. PML cells are deliberately excluded."
        ),
    }


def _box_indicator(x, bounds: dict[str, float]):
    in_x = ufl.And(ufl.ge(x[0], bounds["x_min"]), ufl.le(x[0], bounds["x_max"]))
    in_y = ufl.And(ufl.ge(x[1], bounds["y_min"]), ufl.le(x[1], bounds["y_max"]))
    return ufl.conditional(
        ufl.And(in_x, in_y), PETSc.ScalarType(1.0), PETSc.ScalarType(0.0)
    )


def compute_near_field_integrals(
    mesh_data, cfg: SimulationConfig, E_total
) -> dict[str, object]:
    """Integrate |E|^2 over grating, nearby air, and nearby substrate regions."""
    msh = mesh_data.mesh
    x = ufl.SpatialCoordinate(msh)
    dx = ufl.Measure("dx", msh, subdomain_data=mesh_data.cell_tags)
    field_abs2 = ufl.real(ufl.inner(E_total, E_total))
    regions = near_field_regions_2d(cfg)
    areas = near_field_reference_areas_2d(cfg)

    integrals: dict[str, float] = {}
    grating_local = fem.assemble_scalar(fem.form(field_abs2 * dx(cfg.tags.grating)))
    integrals["grating"] = float(np.real(msh.comm.allreduce(grating_local, op=MPI.SUM)))

    air_indicator = _box_indicator(x, regions["air_near"])
    air_local = fem.assemble_scalar(
        fem.form(air_indicator * field_abs2 * dx(cfg.tags.air))
    )
    integrals["air_near"] = float(np.real(msh.comm.allreduce(air_local, op=MPI.SUM)))

    sub_indicator = _box_indicator(x, regions["sub_near"])
    sub_local = fem.assemble_scalar(
        fem.form(sub_indicator * field_abs2 * dx(cfg.tags.substrate))
    )
    integrals["sub_near"] = float(np.real(msh.comm.allreduce(sub_local, op=MPI.SUM)))

    means = {
        name: (integrals[name] / areas[name] if areas[name] > 0.0 else None)
        for name in integrals
    }
    return {
        "definition": "2D near-field metrics integrate |E|^2 over fixed grating-local boxes in nm^2.",
        "regions": regions,
        "areas_nm2": areas,
        "integral_abs_E2_dOmega": {
            "I_grating": integrals["grating"],
            "I_air_near": integrals["air_near"],
            "I_sub_near": integrals["sub_near"],
        },
        "mean_abs_E2": {
            "mean_grating": means["grating"],
            "mean_air_near": means["air_near"],
            "mean_sub_near": means["sub_near"],
        },
    }


def _attach_absorption_metrics(
    metrics: dict[str, object],
    mesh_data,
    cfg: SimulationConfig,
    E_total,
    incident_power: float,
    field_model: str,
) -> None:
    balance = 1.0 - float(metrics["R_total"]) - float(metrics["T_total"])
    metrics["A_balance"] = balance
    try:
        absorption = _volume_absorption_metrics(
            mesh_data, cfg, E_total, incident_power, field_model
        )
    except (
        Exception
    ) as exc:  # pragma: no cover - postprocess should not hide the solved field
        metrics["A_volume"] = None
        metrics["absorbed_power_weighted"] = None
        metrics["absorption_postprocess_error"] = str(exc)
        return
    metrics.update(absorption)
    try:
        metrics["near_field_integrals"] = compute_near_field_integrals(
            mesh_data, cfg, E_total
        )
    except (
        Exception
    ) as exc:  # pragma: no cover - diagnostics should not hide R/T output
        metrics["near_field_integrals_error"] = str(exc)
    if metrics.get("A_volume") is not None:
        metrics["absorption_difference_volume_minus_balance"] = (
            float(metrics["A_volume"]) - balance
        )


def _compute_power_metrics_from_lines(
    mesh_data,
    cfg: SimulationConfig,
    E_total,
    out_dir: Path,
    *,
    order_count: int,
    num_points: int,
    top_y: float,
    bottom_y: float,
    metrics_filename: str,
    orders_json_filename: str,
    orders_csv_filename: str,
    sampling_method: str,
    order_count_name: str,
    extra_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    hz_scaled = _scaled_hz_function(E_total, cfg)
    x_top, top_values, top_hz = _line_field_and_scaled_hz(
        E_total, hz_scaled, top_y, cfg, num_points
    )
    x_bottom, bottom_values, bottom_hz = _line_field_and_scaled_hz(
        E_total, hz_scaled, bottom_y, cfg, num_points
    )
    top_ex_coeff = _fourier_line_coefficients(x_top, top_values[:, 0], cfg, order_count)
    top_hz_coeff = _fourier_line_coefficients(x_top, top_hz, cfg, order_count)
    bottom_ex_coeff = _fourier_line_coefficients(
        x_bottom, bottom_values[:, 0], cfg, order_count
    )
    bottom_hz_coeff = _fourier_line_coefficients(x_bottom, bottom_hz, cfg, order_count)

    incident_ex = complex(cfg.port_incident_amplitude) * cfg.polarization[0]
    k_air = complex(cfg.k0 * cfg.n_air)
    k_sub = complex(cfg.k0 * cfg.n_substrate)
    beta_inc = _positive_sqrt(k_air**2 - cfg.kx**2)
    incident_admittance = _modal_admittance(k_air, beta_inc)
    incident_power = (
        cfg.period_x * _modal_power_factor(incident_admittance) * abs(incident_ex) ** 2
    )
    if incident_power <= 0:
        raise RuntimeError(
            "Incident modal power is zero; cannot normalize reflection/transmission metrics."
        )

    top_flux_y = cfg.period_x * float(
        np.mean(-0.5 * np.real(top_values[:, 0] * np.conj(top_hz)))
    )
    bottom_flux_y = cfg.period_x * float(
        np.mean(-0.5 * np.real(bottom_values[:, 0] * np.conj(bottom_hz)))
    )
    top_outward_power = top_flux_y
    bottom_outward_power = -bottom_flux_y
    net_outward_power = top_outward_power + bottom_outward_power

    rows: list[dict[str, object]] = []
    reflected_total = 0.0
    transmitted_total = 0.0
    for order in range(-order_count, order_count + 1):
        alpha = cfg.kx + 2.0 * np.pi * order / cfg.period_x
        beta_top = _positive_sqrt(k_air**2 - alpha**2)
        beta_bottom = _positive_sqrt(k_sub**2 - alpha**2)
        y_top_admittance = _modal_admittance(k_air, beta_top)
        y_bottom_admittance = _modal_admittance(k_sub, beta_bottom)

        top_line_coeff = top_ex_coeff[order]
        top_hz_line_coeff = top_hz_coeff[order]
        bottom_line_coeff = bottom_ex_coeff[order]
        bottom_hz_line_coeff = bottom_hz_coeff[order]

        incident_line_coeff = 0.0 + 0.0j
        if order == 0:
            incident_line_coeff = incident_ex * np.exp(-1j * beta_top * top_y)

        top_down_line_coeff = 0.5 * (
            top_line_coeff + top_hz_line_coeff / y_top_admittance
        )
        top_up_line_coeff = 0.5 * (
            top_line_coeff - top_hz_line_coeff / y_top_admittance
        )
        bottom_down_line_coeff = 0.5 * (
            bottom_line_coeff + bottom_hz_line_coeff / y_bottom_admittance
        )
        bottom_up_line_coeff = 0.5 * (
            bottom_line_coeff - bottom_hz_line_coeff / y_bottom_admittance
        )

        reflected_amp = top_up_line_coeff * np.exp(-1j * beta_top * top_y)
        transmitted_amp = bottom_down_line_coeff * np.exp(1j * beta_bottom * bottom_y)
        top_down_amp = top_down_line_coeff * np.exp(1j * beta_top * top_y)
        bottom_up_amp = bottom_up_line_coeff * np.exp(-1j * beta_bottom * bottom_y)

        top_propagating = _is_propagating(beta_top)
        bottom_propagating = _is_propagating(beta_bottom)
        # Power is evaluated on the actual probe plane. Phase-normalized
        # amplitudes are retained for reporting, but in a lossy medium their
        # magnitude changes when transported to y=0.
        reflected_power = _modal_power_on_plane(
            cfg.period_x,
            _modal_power_factor(y_top_admittance),
            top_up_line_coeff,
            top_propagating,
        )
        transmitted_power = _modal_power_on_plane(
            cfg.period_x,
            _modal_power_factor(y_bottom_admittance),
            bottom_down_line_coeff,
            bottom_propagating,
        )
        reflected_total += reflected_power
        transmitted_total += transmitted_power

        rows.append(
            {
                "order": order,
                "alpha": alpha,
                "beta_top_real": beta_top.real,
                "beta_top_imag": beta_top.imag,
                "beta_bottom_real": beta_bottom.real,
                "beta_bottom_imag": beta_bottom.imag,
                "top_modal_admittance_real": y_top_admittance.real,
                "top_modal_admittance_imag": y_top_admittance.imag,
                "bottom_modal_admittance_real": y_bottom_admittance.real,
                "bottom_modal_admittance_imag": y_bottom_admittance.imag,
                "top_propagating": top_propagating,
                "bottom_propagating": bottom_propagating,
                "incident_Ex_abs": abs(incident_ex) if order == 0 else 0.0,
                "incident_Ex_line_abs": abs(incident_line_coeff) if order == 0 else 0.0,
                "top_down_Ex_abs": abs(top_down_amp),
                "top_up_Ex_abs": abs(reflected_amp),
                "bottom_down_Ex_abs": abs(transmitted_amp),
                "bottom_up_Ex_abs": abs(bottom_up_amp),
                "top_down_minus_incident_abs": abs(
                    top_down_line_coeff - incident_line_coeff
                )
                if order == 0
                else 0.0,
                "reflected_Ex_real": reflected_amp.real,
                "reflected_Ex_imag": reflected_amp.imag,
                "reflected_Ex_abs": abs(reflected_amp),
                "reflected_Ex_phase": float(np.angle(reflected_amp)),
                "transmitted_Ex_real": transmitted_amp.real,
                "transmitted_Ex_imag": transmitted_amp.imag,
                "transmitted_Ex_abs": abs(transmitted_amp),
                "transmitted_Ex_phase": float(np.angle(transmitted_amp)),
                "R_order": reflected_power / incident_power,
                "T_order": transmitted_power / incident_power,
            }
        )

    R_total = reflected_total / incident_power
    T_total = transmitted_total / incident_power
    metrics: dict[str, object] = {
        "method": cfg.calculation_method,
        "polarization_type": "TM",
        "field_model": "in-plane vector E=(Ex,Ey)",
        "sampling_method": sampling_method,
        "scattering_background": cfg.scattering_background,
        "port_boundary_model": cfg.port_boundary_model,
        order_count_name: order_count,
        "modal_order_count_used": order_count,
        "num_probe_points": num_points,
        "top_sample_y": top_y,
        "bottom_sample_y": bottom_y,
        "top_probe_y": top_y,
        "bottom_probe_y": bottom_y,
        "hz_reconstruction": "DG interpolation of (dEy/dx - dEx/dy) / i",
        "hz_dg_degree": max(int(cfg.nedelec_degree), 1),
        "incident_power_weighted": incident_power,
        "reflected_power_weighted": reflected_total,
        "transmitted_power_weighted": transmitted_total,
        "top_flux_y_weighted": top_flux_y,
        "bottom_flux_y_weighted": bottom_flux_y,
        "top_outward_power_weighted": top_outward_power,
        "bottom_outward_power_weighted": bottom_outward_power,
        "net_outward_power_weighted": net_outward_power,
        "poynting_R_plus_T_from_net_flux": 1.0 + net_outward_power / incident_power,
        "poynting_energy_residual": -(net_outward_power / incident_power),
        "R_total": R_total,
        "T_total": T_total,
        "R_plus_T": R_total + T_total,
        "energy_residual_1_minus_R_minus_T": 1.0 - R_total - T_total,
        "orders": rows,
        "normalization_note": (
            "Power ratios use H_z reconstructed from curl(E), with the common constant 1/(omega*mu0) omitted "
            "from numerator and denominator. Only propagating Floquet orders contribute to R/T."
        ),
    }
    if extra_metadata:
        metrics.update(extra_metadata)
    _attach_absorption_metrics(
        metrics, mesh_data, cfg, E_total, incident_power, "TM vector Ex/Ey"
    )

    if mesh_data.mesh.comm.rank == 0:
        (out_dir / metrics_filename).write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        (out_dir / orders_json_filename).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        with (out_dir / orders_csv_filename).open(
            "w", newline="", encoding="utf-8"
        ) as fp:
            writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    return metrics


def _compute_te_power_metrics_from_lines(
    mesh_data,
    cfg: SimulationConfig,
    E_total,
    out_dir: Path,
    *,
    order_count: int,
    num_points: int,
    top_y: float,
    bottom_y: float,
    metrics_filename: str,
    orders_json_filename: str,
    orders_csv_filename: str,
    sampling_method: str,
    order_count_name: str,
    extra_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    hx_scaled = _scaled_hx_function(E_total, cfg)
    x_top, top_ez, top_hx = _line_scalar_and_scaled_hx(
        E_total, hx_scaled, top_y, cfg, num_points
    )
    x_bottom, bottom_ez, bottom_hx = _line_scalar_and_scaled_hx(
        E_total, hx_scaled, bottom_y, cfg, num_points
    )
    top_ez_coeff = _fourier_line_coefficients(x_top, top_ez, cfg, order_count)
    top_hx_coeff = _fourier_line_coefficients(x_top, top_hx, cfg, order_count)
    bottom_ez_coeff = _fourier_line_coefficients(x_bottom, bottom_ez, cfg, order_count)
    bottom_hx_coeff = _fourier_line_coefficients(x_bottom, bottom_hx, cfg, order_count)

    incident_ez = complex(cfg.port_incident_amplitude)
    k_air = complex(cfg.k0 * cfg.n_air)
    k_sub = complex(cfg.k0 * cfg.n_substrate)
    beta_inc = _positive_sqrt(k_air**2 - cfg.kx**2)
    incident_power = (
        cfg.period_x * 0.5 * float(max(np.real(beta_inc), 0.0)) * abs(incident_ez) ** 2
    )
    if incident_power <= 0:
        raise RuntimeError(
            "Incident TE modal power is zero; cannot normalize reflection/transmission metrics."
        )

    top_flux_y = cfg.period_x * float(np.mean(0.5 * np.real(top_ez * np.conj(top_hx))))
    bottom_flux_y = cfg.period_x * float(
        np.mean(0.5 * np.real(bottom_ez * np.conj(bottom_hx)))
    )
    top_outward_power = top_flux_y
    bottom_outward_power = -bottom_flux_y
    net_outward_power = top_outward_power + bottom_outward_power

    rows: list[dict[str, object]] = []
    reflected_total = 0.0
    transmitted_total = 0.0
    for order in range(-order_count, order_count + 1):
        alpha = cfg.kx + 2.0 * np.pi * order / cfg.period_x
        beta_top = _positive_sqrt(k_air**2 - alpha**2)
        beta_bottom = _positive_sqrt(k_sub**2 - alpha**2)
        beta_top_factor = 0.5 * float(max(np.real(beta_top), 0.0))
        beta_bottom_factor = 0.5 * float(max(np.real(beta_bottom), 0.0))

        top_ez_line = top_ez_coeff[order]
        top_hx_line = top_hx_coeff[order]
        bottom_ez_line = bottom_ez_coeff[order]
        bottom_hx_line = bottom_hx_coeff[order]

        incident_line_coeff = 0.0 + 0.0j
        if order == 0:
            incident_line_coeff = incident_ez * np.exp(-1j * beta_top * top_y)

        top_down_line_coeff = 0.5 * (top_ez_line - top_hx_line / beta_top)
        top_up_line_coeff = 0.5 * (top_ez_line + top_hx_line / beta_top)
        bottom_down_line_coeff = 0.5 * (bottom_ez_line - bottom_hx_line / beta_bottom)
        bottom_up_line_coeff = 0.5 * (bottom_ez_line + bottom_hx_line / beta_bottom)

        reflected_amp = top_up_line_coeff * np.exp(-1j * beta_top * top_y)
        transmitted_amp = bottom_down_line_coeff * np.exp(1j * beta_bottom * bottom_y)
        top_down_amp = top_down_line_coeff * np.exp(1j * beta_top * top_y)
        bottom_up_amp = bottom_up_line_coeff * np.exp(-1j * beta_bottom * bottom_y)

        top_propagating = _is_propagating(beta_top)
        bottom_propagating = _is_propagating(beta_bottom)
        reflected_power = _modal_power_on_plane(
            cfg.period_x, beta_top_factor, top_up_line_coeff, top_propagating
        )
        transmitted_power = _modal_power_on_plane(
            cfg.period_x, beta_bottom_factor, bottom_down_line_coeff, bottom_propagating
        )
        reflected_total += reflected_power
        transmitted_total += transmitted_power

        rows.append(
            {
                "order": order,
                "alpha": alpha,
                "beta_top_real": beta_top.real,
                "beta_top_imag": beta_top.imag,
                "beta_bottom_real": beta_bottom.real,
                "beta_bottom_imag": beta_bottom.imag,
                "top_propagating": top_propagating,
                "bottom_propagating": bottom_propagating,
                "incident_Ez_abs": abs(incident_ez) if order == 0 else 0.0,
                "incident_Ez_line_abs": abs(incident_line_coeff) if order == 0 else 0.0,
                "top_down_Ez_abs": abs(top_down_amp),
                "top_up_Ez_abs": abs(reflected_amp),
                "bottom_down_Ez_abs": abs(transmitted_amp),
                "bottom_up_Ez_abs": abs(bottom_up_amp),
                "top_down_minus_incident_abs": abs(
                    top_down_line_coeff - incident_line_coeff
                )
                if order == 0
                else 0.0,
                "reflected_Ez_real": reflected_amp.real,
                "reflected_Ez_imag": reflected_amp.imag,
                "reflected_Ez_abs": abs(reflected_amp),
                "reflected_Ez_phase": float(np.angle(reflected_amp)),
                "transmitted_Ez_real": transmitted_amp.real,
                "transmitted_Ez_imag": transmitted_amp.imag,
                "transmitted_Ez_abs": abs(transmitted_amp),
                "transmitted_Ez_phase": float(np.angle(transmitted_amp)),
                "R_order": reflected_power / incident_power,
                "T_order": transmitted_power / incident_power,
            }
        )

    R_total = reflected_total / incident_power
    T_total = transmitted_total / incident_power
    metrics: dict[str, object] = {
        "method": cfg.calculation_method,
        "polarization_type": "TE",
        "field_model": "scalar Ez",
        "sampling_method": sampling_method,
        "scattering_background": cfg.scattering_background,
        "port_boundary_model": cfg.port_boundary_model,
        order_count_name: order_count,
        "modal_order_count_used": order_count,
        "num_probe_points": num_points,
        "top_sample_y": top_y,
        "bottom_sample_y": bottom_y,
        "top_probe_y": top_y,
        "bottom_probe_y": bottom_y,
        "magnetic_reconstruction": "Hx_scaled = dEz/dy / i",
        "hx_dg_degree": max(int(cfg.nedelec_degree), 1),
        "incident_power_weighted": incident_power,
        "reflected_power_weighted": reflected_total,
        "transmitted_power_weighted": transmitted_total,
        "top_flux_y_weighted": top_flux_y,
        "bottom_flux_y_weighted": bottom_flux_y,
        "top_outward_power_weighted": top_outward_power,
        "bottom_outward_power_weighted": bottom_outward_power,
        "net_outward_power_weighted": net_outward_power,
        "poynting_R_plus_T_from_net_flux": 1.0 + net_outward_power / incident_power,
        "poynting_energy_residual": -(net_outward_power / incident_power),
        "R_total": R_total,
        "T_total": T_total,
        "R_plus_T": R_total + T_total,
        "energy_residual_1_minus_R_minus_T": 1.0 - R_total - T_total,
        "orders": rows,
        "normalization_note": (
            "TE power ratios use Hx_scaled=dEz/dy/i with the common constant 1/(omega*mu0) omitted. "
            "Only propagating Floquet orders contribute to R/T."
        ),
    }
    if extra_metadata:
        metrics.update(extra_metadata)
    _attach_absorption_metrics(
        metrics, mesh_data, cfg, E_total, incident_power, "TE scalar Ez"
    )

    if mesh_data.mesh.comm.rank == 0:
        (out_dir / metrics_filename).write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        (out_dir / orders_json_filename).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        with (out_dir / orders_csv_filename).open(
            "w", newline="", encoding="utf-8"
        ) as fp:
            writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    return metrics


def compute_power_metrics(
    mesh_data, cfg: SimulationConfig, E_total, out_dir: Path
) -> dict[str, object]:
    """Compute reflection/transmission metrics from interior horizontal probe lines."""
    if not cfg.compute_power_metrics:
        return {}

    order_count = int(cfg.diffraction_order_count)
    if order_count < 0:
        raise ValueError("diffraction_order_count must be non-negative.")
    num_points = max(int(cfg.power_probe_num_points), 8 * (2 * order_count + 1), 64)
    top_y, bottom_y = _probe_y_locations(cfg)

    if cfg.polarization_type.upper() == "TE":
        return _compute_te_power_metrics_from_lines(
            mesh_data,
            cfg,
            E_total,
            out_dir,
            order_count=order_count,
            num_points=num_points,
            top_y=top_y,
            bottom_y=bottom_y,
            metrics_filename="power_metrics.json",
            orders_json_filename="diffraction_orders.json",
            orders_csv_filename="diffraction_orders.csv",
            sampling_method="interior_horizontal_probe_line",
            order_count_name="diffraction_order_count",
            extra_metadata={
                "postprocess_family": "probe_line",
                "probe_position_fraction_from_structure_to_outer_interface": 0.95,
                "sampling_note": (
                    "TE Floquet modal amplitudes are projected from Ez and Hx_scaled=dEz/dy/i on two "
                    "horizontal lines inside the uniform top air and bottom substrate regions."
                ),
            },
        )

    return _compute_power_metrics_from_lines(
        mesh_data,
        cfg,
        E_total,
        out_dir,
        order_count=order_count,
        num_points=num_points,
        top_y=top_y,
        bottom_y=bottom_y,
        metrics_filename="power_metrics.json",
        orders_json_filename="diffraction_orders.json",
        orders_csv_filename="diffraction_orders.csv",
        sampling_method="interior_horizontal_probe_line",
        order_count_name="diffraction_order_count",
        extra_metadata={
            "postprocess_family": "probe_line",
            "probe_position_fraction_from_structure_to_outer_interface": 0.95,
            "sampling_note": (
                "Floquet modal amplitudes are projected on two horizontal lines inside the uniform top air "
                "and bottom substrate regions. The lines are placed at 95 percent of the distance from the "
                "near-structure interface toward the outer physical/PML interface. This method is available "
                "for scattered-field, Robin-port, and DtN-port runs."
            ),
        },
    )


def _trace_modal_coefficient(
    trace_vectors: dict[str, dict[int, dict[str, object]]],
    side: str,
    order: int,
    solution: np.ndarray,
    cfg: SimulationConfig,
) -> complex:
    try:
        trace = trace_vectors[side][order]
    except KeyError as exc:
        raise RuntimeError(
            f"Missing DtN trace projection vector for side={side!r}, order={order}."
        ) from exc
    indices = np.asarray(trace["indices"], dtype=np.int64)
    values = np.asarray(trace["values"], dtype=np.complex128)
    if len(indices) == 0:
        return 0.0 + 0.0j
    return complex(np.dot(solution[indices], np.conj(values)) / cfg.period_x)


def _compute_tm_dtn_power_from_coefficients(
    mesh_data,
    cfg: SimulationConfig,
    E_total,
    out_dir: Path,
    *,
    top_ex_coeff: dict[int, complex],
    bottom_ex_coeff: dict[int, complex],
    metrics_filename: str,
    orders_json_filename: str,
    orders_csv_filename: str,
    sampling_method: str,
    postprocess_family: str,
    projection_source: str,
    extra_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    out_dir.mkdir(parents=True, exist_ok=True)
    top_y = float(cfg.y_max)
    bottom_y = float(cfg.y_min)
    top_orders = sorted(int(order) for order in top_ex_coeff.keys())
    bottom_orders = sorted(int(order) for order in bottom_ex_coeff.keys())
    all_orders = sorted(set(top_orders) | set(bottom_orders))
    if not all_orders:
        raise RuntimeError("No DtN port modal coefficients were provided.")

    incident_ex = complex(cfg.port_incident_amplitude) * cfg.polarization[0]
    k_air = complex(cfg.k0 * cfg.n_air)
    k_sub = complex(cfg.k0 * cfg.n_substrate)
    beta_inc = _positive_sqrt(k_air**2 - cfg.kx**2)
    incident_admittance = _modal_admittance(k_air, beta_inc)
    incident_power = (
        cfg.period_x * _modal_power_factor(incident_admittance) * abs(incident_ex) ** 2
    )
    if incident_power <= 0:
        raise RuntimeError(
            "Incident modal power is zero; cannot normalize DtN port power metrics."
        )

    rows: list[dict[str, object]] = []
    reflected_total = 0.0
    transmitted_total = 0.0
    for order in all_orders:
        alpha = cfg.kx + 2.0 * np.pi * order / cfg.period_x
        beta_top = _positive_sqrt(k_air**2 - alpha**2)
        beta_bottom = _positive_sqrt(k_sub**2 - alpha**2)
        y_top_admittance = _modal_admittance(k_air, beta_top)
        y_bottom_admittance = _modal_admittance(k_sub, beta_bottom)
        top_included = order in top_ex_coeff
        bottom_included = order in bottom_ex_coeff
        top_total = top_ex_coeff.get(order, 0.0 + 0.0j)
        bottom_total = bottom_ex_coeff.get(order, 0.0 + 0.0j)

        incident_line_coeff = 0.0 + 0.0j
        if order == 0:
            incident_line_coeff = incident_ex * np.exp(-1j * beta_top * top_y)

        reflected_amp = (
            (top_total - incident_line_coeff) * np.exp(-1j * beta_top * top_y)
            if top_included
            else 0.0 + 0.0j
        )
        transmitted_amp = (
            bottom_total * np.exp(1j * beta_bottom * bottom_y)
            if bottom_included
            else 0.0 + 0.0j
        )

        top_propagating = _is_propagating(beta_top)
        bottom_propagating = _is_propagating(beta_bottom)
        reflected_boundary_coeff = (
            top_total - incident_line_coeff if top_included else 0.0 + 0.0j
        )
        transmitted_boundary_coeff = bottom_total if bottom_included else 0.0 + 0.0j
        reflected_power = _modal_power_on_plane(
            cfg.period_x,
            _modal_power_factor(y_top_admittance),
            reflected_boundary_coeff,
            top_propagating,
        )
        transmitted_power = _modal_power_on_plane(
            cfg.period_x,
            _modal_power_factor(y_bottom_admittance),
            transmitted_boundary_coeff,
            bottom_propagating,
        )
        reflected_total += reflected_power
        transmitted_total += transmitted_power

        rows.append(
            {
                "order": order,
                "alpha": alpha,
                "beta_top_real": beta_top.real,
                "beta_top_imag": beta_top.imag,
                "beta_bottom_real": beta_bottom.real,
                "beta_bottom_imag": beta_bottom.imag,
                "top_modal_admittance_real": y_top_admittance.real,
                "top_modal_admittance_imag": y_top_admittance.imag,
                "bottom_modal_admittance_real": y_bottom_admittance.real,
                "bottom_modal_admittance_imag": y_bottom_admittance.imag,
                "top_propagating": top_propagating,
                "bottom_propagating": bottom_propagating,
                "top_order_included": top_included,
                "bottom_order_included": bottom_included,
                "incident_Ex_abs": abs(incident_ex) if order == 0 else 0.0,
                "incident_Ex_line_abs": abs(incident_line_coeff) if order == 0 else 0.0,
                "top_total_Ex_port_real": top_total.real,
                "top_total_Ex_port_imag": top_total.imag,
                "top_total_Ex_port_abs": abs(top_total),
                "bottom_total_Ex_port_real": bottom_total.real,
                "bottom_total_Ex_port_imag": bottom_total.imag,
                "bottom_total_Ex_port_abs": abs(bottom_total),
                "reflected_Ex_boundary_abs": abs(reflected_boundary_coeff),
                "transmitted_Ex_boundary_abs": abs(transmitted_boundary_coeff),
                "reflected_Ex_real": reflected_amp.real,
                "reflected_Ex_imag": reflected_amp.imag,
                "reflected_Ex_abs": abs(reflected_amp),
                "reflected_Ex_phase": float(np.angle(reflected_amp)),
                "transmitted_Ex_real": transmitted_amp.real,
                "transmitted_Ex_imag": transmitted_amp.imag,
                "transmitted_Ex_abs": abs(transmitted_amp),
                "transmitted_Ex_phase": float(np.angle(transmitted_amp)),
                "R_order": reflected_power / incident_power,
                "T_order": transmitted_power / incident_power,
            }
        )

    R_total = reflected_total / incident_power
    T_total = transmitted_total / incident_power
    metrics: dict[str, object] = {
        "method": cfg.calculation_method,
        "polarization_type": "TM",
        "field_model": "in-plane vector E=(Ex,Ey)",
        "sampling_method": sampling_method,
        "postprocess_family": postprocess_family,
        "projection_source": projection_source,
        "trace_vector_storage": "compressed_nonzero_indices_and_values",
        "scattering_background": cfg.scattering_background,
        "port_boundary_model": cfg.port_boundary_model,
        "port_dtn_order_count": int(cfg.port_dtn_order_count),
        "port_dtn_assembly": cfg.port_dtn_assembly,
        "port_use_diffraction_orders": cfg.port_use_diffraction_orders,
        "modal_order_count_used": {
            "top": top_orders,
            "bottom": bottom_orders,
            "combined": all_orders,
        },
        "port_orders_by_side": {
            "top": top_orders,
            "bottom": bottom_orders,
        },
        "top_port_y": float(cfg.y_max),
        "bottom_port_y": float(cfg.y_min),
        "top_sample_y": top_y,
        "bottom_sample_y": bottom_y,
        "incident_power_weighted": incident_power,
        "reflected_power_weighted": reflected_total,
        "transmitted_power_weighted": transmitted_total,
        "R_total": R_total,
        "T_total": T_total,
        "R_plus_T": R_total + T_total,
        "energy_residual_1_minus_R_minus_T": 1.0 - R_total - T_total,
        "orders": rows,
        "amplitude_definition": (
            "Top reflected amplitudes use reflected_m = (Ex_top_m - incident_m) exp(-i beta_top y_top). "
            "Bottom transmitted amplitudes use transmitted_m = Ex_bottom_m exp(i beta_bottom y_bottom). "
            "Ex_top_m and Ex_bottom_m are computed by applying the same assembled DtN boundary-integral trace "
            "vectors to the solved finite-element coefficient vector."
        ),
        "normalization_note": (
            "Power ratios use the modal admittance k_medium^2/beta_m and the field coefficient on the actual "
            "port plane. Lossy power-carrying modes may have complex beta; below-cutoff evanescent orders do "
            "not contribute to R/T. Phase-normalized amplitudes are reporting fields only."
        ),
    }
    if extra_metadata:
        metrics.update(extra_metadata)
    _attach_absorption_metrics(
        metrics, mesh_data, cfg, E_total, incident_power, "TM vector Ex/Ey"
    )

    if mesh_data.mesh.comm.rank == 0:
        (out_dir / metrics_filename).write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        (out_dir / orders_json_filename).write_text(
            json.dumps(rows, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        with (out_dir / orders_csv_filename).open(
            "w", newline="", encoding="utf-8"
        ) as fp:
            writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    return metrics


def compute_dtn_port_power_metrics(
    mesh_data,
    cfg: SimulationConfig,
    E_total,
    out_dir: Path,
    trace_vectors: dict[str, dict[int, dict[str, object]]],
) -> dict[str, object]:
    """Compute R/T by reusing the DtN boundary-integral projection vectors."""
    if not cfg.compute_power_metrics:
        return {}
    if cfg.port_boundary_model != "dtn":
        return {
            "skipped": True,
            "reason": "dtn_port_power_metrics requires port_boundary_model='dtn'.",
        }
    if cfg.use_pml:
        return {
            "skipped": True,
            "reason": "dtn_port_power_metrics is defined for the no-PML DtN port boundary placement.",
        }
    if mesh_data.mesh.comm.size != 1:
        return {
            "skipped": True,
            "reason": "dtn_port_power_metrics currently reuses serial manual DtN trace vectors.",
        }

    solution = np.asarray(E_total.x.array, dtype=np.complex128)
    top_ex_coeff = {
        int(order): _trace_modal_coefficient(
            trace_vectors, "top", int(order), solution, cfg
        )
        for order in sorted(trace_vectors.get("top", {}).keys())
    }
    bottom_ex_coeff = {
        int(order): _trace_modal_coefficient(
            trace_vectors, "bottom", int(order), solution, cfg
        )
        for order in sorted(trace_vectors.get("bottom", {}).keys())
    }

    return _compute_tm_dtn_power_from_coefficients(
        mesh_data,
        cfg,
        E_total,
        out_dir,
        top_ex_coeff=top_ex_coeff,
        bottom_ex_coeff=bottom_ex_coeff,
        metrics_filename="dtn_port_power_metrics.json",
        orders_json_filename="dtn_port_diffraction_orders.json",
        orders_csv_filename="dtn_port_diffraction_orders.csv",
        sampling_method="dtn_port_boundary_integral_projection",
        postprocess_family="dtn_port_trace",
        projection_source="same_compressed_trace_vectors_used_to_assemble_fourier_dtn_port_matrix",
    )


def compute_dtn_auxiliary_power_metrics(
    mesh_data,
    cfg: SimulationConfig,
    E_total,
    out_dir: Path,
    auxiliary_coefficients: dict[str, dict[int, complex]],
    port_metadata: dict[str, object] | None = None,
) -> dict[str, object]:
    """Compute R/T directly from the auxiliary modal-amplitude unknowns."""
    if not cfg.compute_power_metrics:
        return {}
    if cfg.port_boundary_model != "dtn":
        return {
            "skipped": True,
            "reason": "dtn_auxiliary_power_metrics requires port_boundary_model='dtn'.",
        }
    if cfg.port_dtn_assembly != "auxiliary":
        return {
            "skipped": True,
            "reason": "auxiliary modal amplitudes exist only for port_dtn_assembly='auxiliary'.",
        }
    if cfg.use_pml:
        return {
            "skipped": True,
            "reason": "dtn_auxiliary_power_metrics is defined for the no-PML DtN port boundary placement.",
        }
    if mesh_data.mesh.comm.size != 1:
        return {
            "skipped": True,
            "reason": "dtn_auxiliary_power_metrics currently uses serial manual DtN auxiliary values.",
        }

    return _compute_tm_dtn_power_from_coefficients(
        mesh_data,
        cfg,
        E_total,
        out_dir,
        top_ex_coeff={
            int(order): complex(value)
            for order, value in auxiliary_coefficients.get("top", {}).items()
        },
        bottom_ex_coeff={
            int(order): complex(value)
            for order, value in auxiliary_coefficients.get("bottom", {}).items()
        },
        metrics_filename="dtn_auxiliary_power_metrics.json",
        orders_json_filename="dtn_auxiliary_diffraction_orders.json",
        orders_csv_filename="dtn_auxiliary_diffraction_orders.csv",
        sampling_method="dtn_auxiliary_modal_amplitudes",
        postprocess_family="dtn_auxiliary_trace",
        projection_source="auxiliary_unknowns_in_the_expanded_fourier_dtn_block_system",
        extra_metadata={
            "auxiliary_power_note": (
                "The auxiliary unknown a_m is constrained by a_m=(1/L)*ell_m^H*u, so this power metric should "
                "match dtn_port_power_metrics.json up to linear-solve roundoff."
            ),
            "port_order_candidates": (port_metadata or {}).get("mode_candidates", []),
            "port_rayleigh_warnings": (port_metadata or {}).get(
                "rayleigh_warnings", []
            ),
        },
    )


def compute_te_dtn_port_power_metrics(
    mesh_data,
    cfg: SimulationConfig,
    E_total,
    out_dir: Path,
    trace_vectors: dict[str, dict[int, dict[str, object]]],
) -> dict[str, object]:
    """Compute TE R/T by reusing scalar DtN boundary-integral projection vectors."""
    if not cfg.compute_power_metrics:
        return {}
    if cfg.port_boundary_model != "dtn":
        return {
            "skipped": True,
            "reason": "TE dtn_port_power_metrics requires port_boundary_model='dtn'.",
        }
    if cfg.use_pml:
        return {
            "skipped": True,
            "reason": "TE dtn_port_power_metrics is defined for the no-PML DtN port boundary placement.",
        }
    if mesh_data.mesh.comm.size != 1:
        return {
            "skipped": True,
            "reason": "TE DtN port metrics currently reuse serial manual DtN trace vectors.",
        }

    order_count = int(cfg.port_dtn_order_count)
    if order_count < 0:
        raise ValueError("port_dtn_order_count must be non-negative.")
    out_dir.mkdir(parents=True, exist_ok=True)

    solution = np.asarray(E_total.x.array, dtype=np.complex128)
    top_y = float(cfg.y_max)
    bottom_y = float(cfg.y_min)
    top_ez_coeff: dict[int, complex] = {}
    bottom_ez_coeff: dict[int, complex] = {}
    for order in range(-order_count, order_count + 1):
        top_ez_coeff[order] = _trace_modal_coefficient(
            trace_vectors, "top", order, solution, cfg
        )
        bottom_ez_coeff[order] = _trace_modal_coefficient(
            trace_vectors, "bottom", order, solution, cfg
        )

    incident_ez = complex(cfg.port_incident_amplitude)
    k_air = complex(cfg.k0 * cfg.n_air)
    k_sub = complex(cfg.k0 * cfg.n_substrate)
    beta_inc = _positive_sqrt(k_air**2 - cfg.kx**2)
    incident_power = (
        cfg.period_x * 0.5 * float(max(np.real(beta_inc), 0.0)) * abs(incident_ez) ** 2
    )
    if incident_power <= 0:
        raise RuntimeError(
            "Incident TE modal power is zero; cannot normalize TE DtN port power metrics."
        )

    rows: list[dict[str, object]] = []
    reflected_total = 0.0
    transmitted_total = 0.0
    for order in range(-order_count, order_count + 1):
        alpha = cfg.kx + 2.0 * np.pi * order / cfg.period_x
        beta_top = _positive_sqrt(k_air**2 - alpha**2)
        beta_bottom = _positive_sqrt(k_sub**2 - alpha**2)
        beta_top_factor = 0.5 * float(max(np.real(beta_top), 0.0))
        beta_bottom_factor = 0.5 * float(max(np.real(beta_bottom), 0.0))

        incident_line_coeff = 0.0 + 0.0j
        if order == 0:
            incident_line_coeff = incident_ez * np.exp(-1j * beta_top * top_y)

        reflected_amp = (top_ez_coeff[order] - incident_line_coeff) * np.exp(
            -1j * beta_top * top_y
        )
        transmitted_amp = bottom_ez_coeff[order] * np.exp(1j * beta_bottom * bottom_y)

        top_propagating = _is_propagating(beta_top)
        bottom_propagating = _is_propagating(beta_bottom)
        reflected_boundary_coeff = top_ez_coeff[order] - incident_line_coeff
        transmitted_boundary_coeff = bottom_ez_coeff[order]
        reflected_power = _modal_power_on_plane(
            cfg.period_x, beta_top_factor, reflected_boundary_coeff, top_propagating
        )
        transmitted_power = _modal_power_on_plane(
            cfg.period_x,
            beta_bottom_factor,
            transmitted_boundary_coeff,
            bottom_propagating,
        )
        reflected_total += reflected_power
        transmitted_total += transmitted_power

        rows.append(
            {
                "order": order,
                "alpha": alpha,
                "beta_top_real": beta_top.real,
                "beta_top_imag": beta_top.imag,
                "beta_bottom_real": beta_bottom.real,
                "beta_bottom_imag": beta_bottom.imag,
                "top_propagating": top_propagating,
                "bottom_propagating": bottom_propagating,
                "incident_Ez_abs": abs(incident_ez) if order == 0 else 0.0,
                "incident_Ez_line_abs": abs(incident_line_coeff) if order == 0 else 0.0,
                "top_total_Ez_port_real": top_ez_coeff[order].real,
                "top_total_Ez_port_imag": top_ez_coeff[order].imag,
                "top_total_Ez_port_abs": abs(top_ez_coeff[order]),
                "bottom_total_Ez_port_real": bottom_ez_coeff[order].real,
                "bottom_total_Ez_port_imag": bottom_ez_coeff[order].imag,
                "bottom_total_Ez_port_abs": abs(bottom_ez_coeff[order]),
                "reflected_Ez_boundary_abs": abs(reflected_boundary_coeff),
                "transmitted_Ez_boundary_abs": abs(transmitted_boundary_coeff),
                "reflected_Ez_real": reflected_amp.real,
                "reflected_Ez_imag": reflected_amp.imag,
                "reflected_Ez_abs": abs(reflected_amp),
                "reflected_Ez_phase": float(np.angle(reflected_amp)),
                "transmitted_Ez_real": transmitted_amp.real,
                "transmitted_Ez_imag": transmitted_amp.imag,
                "transmitted_Ez_abs": abs(transmitted_amp),
                "transmitted_Ez_phase": float(np.angle(transmitted_amp)),
                "R_order": reflected_power / incident_power,
                "T_order": transmitted_power / incident_power,
            }
        )

    R_total = reflected_total / incident_power
    T_total = transmitted_total / incident_power
    metrics: dict[str, object] = {
        "method": cfg.calculation_method,
        "polarization_type": "TE",
        "field_model": "scalar Ez",
        "sampling_method": "dtn_port_boundary_integral_projection",
        "postprocess_family": "dtn_port_trace",
        "projection_source": "same_compressed_trace_vectors_used_to_assemble_scalar_fourier_dtn_port_matrix",
        "trace_vector_storage": "compressed_nonzero_indices_and_values",
        "scattering_background": cfg.scattering_background,
        "port_boundary_model": cfg.port_boundary_model,
        "port_dtn_order_count": order_count,
        "modal_order_count_used": order_count,
        "top_port_y": float(cfg.y_max),
        "bottom_port_y": float(cfg.y_min),
        "top_sample_y": top_y,
        "bottom_sample_y": bottom_y,
        "incident_power_weighted": incident_power,
        "reflected_power_weighted": reflected_total,
        "transmitted_power_weighted": transmitted_total,
        "R_total": R_total,
        "T_total": T_total,
        "R_plus_T": R_total + T_total,
        "energy_residual_1_minus_R_minus_T": 1.0 - R_total - T_total,
        "orders": rows,
        "amplitude_definition": (
            "Top reflected amplitudes use reflected_m=(Ez_top_m-incident_m) exp(-i beta_top y_top). "
            "Bottom transmitted amplitudes use transmitted_m=Ez_bottom_m exp(i beta_bottom y_bottom)."
        ),
        "normalization_note": (
            "TE power ratios use 0.5*Re(beta_m) and coefficients on the actual port plane. Lossy "
            "power-carrying modes may have complex beta; below-cutoff evanescent orders do not contribute."
        ),
    }
    _attach_absorption_metrics(
        metrics, mesh_data, cfg, E_total, incident_power, "TE scalar Ez"
    )

    if mesh_data.mesh.comm.rank == 0:
        (out_dir / "dtn_port_power_metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        (out_dir / "dtn_port_diffraction_orders.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        with (out_dir / "dtn_port_diffraction_orders.csv").open(
            "w", newline="", encoding="utf-8"
        ) as fp:
            writer = csv.DictWriter(fp, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)

    return metrics
