from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import numpy as np
import ufl
from mpi4py import MPI
from petsc4py import PETSc

from dolfinx import fem, geometry

from ..common.config_3d import SimulationConfig3D
from ..common.analytic_fields_3d import electric_field_code_values, magnetic_field_code_values
from ..common.modes_3d import (
    DiffractionOrder3D,
    enumerate_diffraction_orders_3d,
    incident_power_3d,
    mode_eh_vectors,
    mode_power,
    polarization_basis_3d,
    positive_sqrt,
)


DIAGNOSTIC_EH_FOURIER_PROBE_POWER_SOURCE = "diagnostic_eh_fourier_probe"
DIAGNOSTIC_E_ONLY_FOURIER_PROBE_POWER_SOURCE = "diagnostic_e_only_fourier_probe"
DIAGNOSTIC_SAMPLED_NET_FLUX_POWER_SOURCE = "diagnostic_sampled_net_flux"

# Kept as a compatibility alias for tests and callers that imported the old
# name.  Stage-4 dtn_port official R/T now comes from DtN port modal
# amplitudes; this probe-plane path is diagnostic.
OFFICIAL_STAGE4_DIFFRACTION_POWER_SOURCE = DIAGNOSTIC_EH_FOURIER_PROBE_POWER_SOURCE
OFFICIAL_STAGE4_DIFFRACTION_POWER_NOTE = (
    "Diagnostic only: E/H Fourier probe-plane fitting separates up/down waves "
    "on uniform probe planes. Stage-4 dtn_port official R/T uses DtN port "
    "modal amplitudes instead."
)
E_FOURIER_DIAGNOSTIC_NOTE = (
    "Diagnostic only: E-only Fourier powers assume a single outgoing direction and can overcount "
    "when finite-PML reflections or non-transverse FE components are present."
)
SAMPLED_NET_FLUX_DIAGNOSTIC_NOTE = (
    "Diagnostic only: sampled net flux uses H reconstructed from the finite-element curl on probe samples. "
    "Stage-4 dtn_port official R/T uses DtN port modal amplitudes."
)


def _json_default(value):
    if isinstance(value, complex):
        return [value.real, value.imag]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    raise TypeError(f"Cannot JSON serialize {type(value)!r}")


def _orders_for_modal_fit(cfg: SimulationConfig3D, power_orders: list[DiffractionOrder3D]) -> tuple[list[DiffractionOrder3D], bool]:
    """Return modal-fit orders, optionally adding evanescent neighbors.

    The default Stage-4 benchmark has only the zero order propagating, but the
    field on a finite probe plane still contains evanescent grating harmonics.
    Including the nearest non-propagating orders in the least-squares basis
    prevents those near-field terms from being folded into the zero-order
    reflected/transmitted amplitudes.
    """

    if not (cfg.diffraction_zero_order_only and cfg.has_grating_block):
        return power_orders, False
    max_m = 1 if cfg.diffraction_order_max_m is None else max(1, int(cfg.diffraction_order_max_m))
    max_n = 1 if cfg.diffraction_order_max_n is None else max(1, int(cfg.diffraction_order_max_n))
    return enumerate_diffraction_orders_3d(cfg, max_m_override=max_m, max_n_override=max_n), True


def _mode_power(
    kvec: np.ndarray,
    e_vec: np.ndarray,
    cfg: SimulationConfig3D,
    outward_normal: np.ndarray,
) -> float:
    return mode_power(kvec, e_vec, cfg, outward_normal)


def _incident_power(cfg: SimulationConfig3D) -> float:
    return incident_power_3d(cfg)


def _sampled_flux_code_units(e_values: np.ndarray, h_values: np.ndarray, normal: np.ndarray, cfg: SimulationConfig3D) -> float:
    """Return average sampled Poynting flux through one horizontal probe plane."""

    poynting = 0.5 * np.real(np.cross(e_values, np.conj(h_values)))
    normal = np.asarray(normal, dtype=np.float64)
    area = (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
    return float(np.mean(poynting @ normal) * area)


def _fourier_e_coefficient(points: np.ndarray, e_values: np.ndarray, alpha: complex, gamma: complex) -> np.ndarray:
    phase = np.exp(-1j * (alpha * points[:, 0] + gamma * points[:, 1]))
    return np.mean(e_values * phase[:, None], axis=0)


def _project_e_amplitudes(coefficient: np.ndarray, basis: list[tuple[str, np.ndarray]]) -> tuple[dict[str, complex], float]:
    matrix = np.column_stack([vec for _, vec in basis]).astype(np.complex128)
    rhs = np.asarray(coefficient, dtype=np.complex128).reshape(3)
    amplitudes, *_ = np.linalg.lstsq(matrix, rhs, rcond=None)
    residual = float(np.linalg.norm(matrix @ amplitudes - rhs) / max(float(np.linalg.norm(rhs)), 1.0e-30))
    return {name: complex(value) for value, (name, _) in zip(amplitudes, basis)}, residual


def _e_fourier_order_powers(
    cfg: SimulationConfig3D,
    power_orders: list[DiffractionOrder3D],
    top_points: np.ndarray,
    top_e: np.ndarray,
    bottom_points: np.ndarray,
    bottom_e: np.ndarray,
    incident_power: float,
) -> tuple[dict[tuple[int, int, str], dict[str, float | complex]], dict[str, float]]:
    """Compute diagnostic R/T from 2D Fourier coefficients of E on probe planes.

    E-only Fourier data cannot separate coexisting up/down waves of the same
    diffraction order.  Keep this path as a diagnostic cross-check only.
    """

    top_z = float(top_points[0, 2])
    bottom_z = float(bottom_points[0, 2])
    top_normal = np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
    bottom_normal = np.asarray((0.0, 0.0, -1.0), dtype=np.float64)
    incident_coeff = complex(cfg.incident_amplitude) * np.asarray(cfg.polarization_vector, dtype=np.complex128)

    rows: dict[tuple[int, int, str], dict[str, float | complex]] = {}
    R_total = 0.0
    T_total = 0.0
    top_residuals: list[float] = []
    bottom_residuals: list[float] = []
    for order in power_orders:
        top_coeff = _fourier_e_coefficient(top_points, top_e, order.alpha, order.gamma)
        bottom_coeff = _fourier_e_coefficient(bottom_points, bottom_e, order.alpha, order.gamma)
        if order.m == 0 and order.n == 0:
            top_coeff = top_coeff - incident_coeff * np.exp(-1j * order.beta_top * top_z)

        top_basis = polarization_basis_3d(order.alpha, order.gamma, order.beta_top, cfg.n_air, 1, cfg)
        bottom_basis = polarization_basis_3d(order.alpha, order.gamma, order.beta_bottom, cfg.substrate_index, -1, cfg)
        top_amp, top_res = _project_e_amplitudes(top_coeff * np.exp(-1j * order.beta_top * top_z), top_basis)
        bottom_amp, bottom_res = _project_e_amplitudes(
            bottom_coeff * np.exp(1j * order.beta_bottom * bottom_z),
            bottom_basis,
        )
        top_residuals.append(top_res)
        bottom_residuals.append(bottom_res)
        top_by_name = {name: vec for name, vec in top_basis}
        bottom_by_name = {name: vec for name, vec in bottom_basis}
        for pol_name in sorted(set(top_by_name) | set(bottom_by_name)):
            ref_amp = top_amp.get(pol_name, 0.0 + 0.0j)
            trn_amp = bottom_amp.get(pol_name, 0.0 + 0.0j)
            R = 0.0
            T = 0.0
            if order.top_propagating and pol_name in top_by_name:
                top_k, top_e_vec, _ = mode_eh_vectors(order.alpha, order.gamma, order.beta_top, top_by_name[pol_name], 1, cfg)
                top_e_at_plane = top_e_vec * np.exp(1j * top_k[2] * top_z)
                R = abs(ref_amp) ** 2 * _mode_power(top_k, top_e_at_plane, cfg, top_normal) / incident_power
                R_total += float(R)
            if order.bottom_propagating and pol_name in bottom_by_name:
                bottom_k, bottom_e_vec, _ = mode_eh_vectors(
                    order.alpha,
                    order.gamma,
                    order.beta_bottom,
                    bottom_by_name[pol_name],
                    -1,
                    cfg,
                )
                bottom_e_at_plane = bottom_e_vec * np.exp(1j * bottom_k[2] * bottom_z)
                T = abs(trn_amp) ** 2 * _mode_power(bottom_k, bottom_e_at_plane, cfg, bottom_normal) / incident_power
                T_total += float(T)
            rows[(order.m, order.n, pol_name)] = {
                "reflected_amplitude_e_fourier": ref_amp,
                "transmitted_amplitude_e_fourier": trn_amp,
                "R_e_fourier": float(R),
                "T_e_fourier": float(T),
                "top_e_fourier_projection_residual": float(top_res),
                "bottom_e_fourier_projection_residual": float(bottom_res),
            }
    metrics = {
        "R_total_from_e_fourier": float(R_total),
        "T_total_from_e_fourier": float(T_total),
        "R_plus_T_from_e_fourier": float(R_total + T_total),
        "A_balance_from_e_fourier": float(1.0 - R_total - T_total),
        "diffraction_top_e_fourier_projection_residual_max": float(max(top_residuals) if top_residuals else 0.0),
        "diffraction_bottom_e_fourier_projection_residual_max": float(max(bottom_residuals) if bottom_residuals else 0.0),
    }
    return rows, metrics


def _fit_directional_eh_amplitudes_for_order(
    cfg: SimulationConfig3D,
    points: np.ndarray,
    e_values: np.ndarray,
    h_values: np.ndarray,
    order: DiffractionOrder3D,
    *,
    side: str,
) -> tuple[dict[tuple[str, str], complex], float]:
    """Separate up/down amplitudes for one order from tangential E/H Fourier data.

    A single transverse Fourier coefficient of E alone cannot distinguish a
    downward wave from an upward wave with the same (m, n).  That matters when a
    finite PML leaves a small reflected component on the probe plane.  The
    tangential pair (E_x, E_y, H_x, H_y) gives a small local modal system for
    each order and is the Stage-4 power path closest to a real modal port.
    """

    if side == "top":
        beta = order.beta_top
        n_medium = complex(cfg.n_air)
    elif side == "bottom":
        beta = order.beta_bottom
        n_medium = complex(cfg.substrate_index)
    else:
        raise ValueError("side must be 'top' or 'bottom'.")

    z = float(points[0, 2])
    e_coeff = _fourier_e_coefficient(points, e_values, order.alpha, order.gamma)
    h_coeff = _fourier_e_coefficient(points, h_values, order.alpha, order.gamma)
    rhs = np.asarray((e_coeff[0], e_coeff[1], h_coeff[0], h_coeff[1]), dtype=np.complex128)

    columns: list[np.ndarray] = []
    keys: list[tuple[str, str]] = []
    for direction_name, vertical_sign in (("down", -1), ("up", 1)):
        for pol_name, pol_vec in polarization_basis_3d(
            order.alpha,
            order.gamma,
            beta,
            n_medium,
            vertical_sign,
            cfg,
        ):
            kvec, e_vec, h_vec = mode_eh_vectors(order.alpha, order.gamma, beta, pol_vec, vertical_sign, cfg)
            phase_z = np.exp(1j * kvec[2] * z)
            columns.append(
                np.asarray(
                    (
                        phase_z * e_vec[0],
                        phase_z * e_vec[1],
                        phase_z * h_vec[0],
                        phase_z * h_vec[1],
                    ),
                    dtype=np.complex128,
                )
            )
            keys.append((pol_name, direction_name))

    matrix = np.column_stack(columns).astype(np.complex128)
    amplitudes, *_ = np.linalg.lstsq(matrix, rhs, rcond=None)
    rhs_norm = float(np.linalg.norm(rhs))
    if rhs_norm < 1.0e-12:
        residual = 0.0
    else:
        residual = float(np.linalg.norm(matrix @ amplitudes - rhs) / rhs_norm)
    return {key: complex(value) for key, value in zip(keys, amplitudes)}, residual


def _eh_fourier_order_powers(
    cfg: SimulationConfig3D,
    power_orders: list[DiffractionOrder3D],
    top_points: np.ndarray,
    top_e: np.ndarray,
    top_h: np.ndarray,
    bottom_points: np.ndarray,
    bottom_e: np.ndarray,
    bottom_h: np.ndarray,
    incident_power: float,
) -> tuple[dict[tuple[int, int, str], dict[str, float | complex]], dict[str, float]]:
    """Compute official Stage-4 R/T by per-order directional E/H Fourier fitting."""

    top_normal = np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
    bottom_normal = np.asarray((0.0, 0.0, -1.0), dtype=np.float64)
    top_z = float(top_points[0, 2])
    bottom_z = float(bottom_points[0, 2])
    rows: dict[tuple[int, int, str], dict[str, float | complex]] = {}
    R_total = 0.0
    T_total = 0.0
    top_residuals: list[float] = []
    bottom_residuals: list[float] = []

    for order in power_orders:
        top_amp, top_res = _fit_directional_eh_amplitudes_for_order(
            cfg,
            top_points,
            top_e,
            top_h,
            order,
            side="top",
        )
        bottom_amp, bottom_res = _fit_directional_eh_amplitudes_for_order(
            cfg,
            bottom_points,
            bottom_e,
            bottom_h,
            order,
            side="bottom",
        )
        top_residuals.append(top_res)
        bottom_residuals.append(bottom_res)

        top_basis = dict(polarization_basis_3d(order.alpha, order.gamma, order.beta_top, cfg.n_air, 1, cfg))
        bottom_basis = dict(
            polarization_basis_3d(order.alpha, order.gamma, order.beta_bottom, cfg.substrate_index, -1, cfg)
        )
        for pol_name in sorted(set(top_basis) | set(bottom_basis)):
            ref_amp = top_amp.get((pol_name, "up"), 0.0 + 0.0j)
            trn_amp = bottom_amp.get((pol_name, "down"), 0.0 + 0.0j)
            R = 0.0
            T = 0.0
            if order.top_propagating and pol_name in top_basis:
                top_k, top_e_vec, _ = mode_eh_vectors(order.alpha, order.gamma, order.beta_top, top_basis[pol_name], 1, cfg)
                top_e_at_plane = top_e_vec * np.exp(1j * top_k[2] * top_z)
                R = abs(ref_amp) ** 2 * _mode_power(top_k, top_e_at_plane, cfg, top_normal) / incident_power
                R_total += float(R)
            if order.bottom_propagating and pol_name in bottom_basis:
                bottom_k, bottom_e_vec, _ = mode_eh_vectors(
                    order.alpha,
                    order.gamma,
                    order.beta_bottom,
                    bottom_basis[pol_name],
                    -1,
                    cfg,
                )
                bottom_e_at_plane = bottom_e_vec * np.exp(1j * bottom_k[2] * bottom_z)
                T = abs(trn_amp) ** 2 * _mode_power(bottom_k, bottom_e_at_plane, cfg, bottom_normal) / incident_power
                T_total += float(T)
            rows[(order.m, order.n, pol_name)] = {
                "reflected_amplitude_eh_fourier": ref_amp,
                "transmitted_amplitude_eh_fourier": trn_amp,
                "R_eh_fourier": float(R),
                "T_eh_fourier": float(T),
                "top_eh_fourier_fit_residual": float(top_res),
                "bottom_eh_fourier_fit_residual": float(bottom_res),
            }

    metrics = {
        "R_total_from_eh_fourier": float(R_total),
        "T_total_from_eh_fourier": float(T_total),
        "R_plus_T_from_eh_fourier": float(R_total + T_total),
        "A_balance_from_eh_fourier": float(1.0 - R_total - T_total),
        "diffraction_top_eh_fourier_fit_residual_max": float(max(top_residuals) if top_residuals else 0.0),
        "diffraction_bottom_eh_fourier_fit_residual_max": float(max(bottom_residuals) if bottom_residuals else 0.0),
    }
    return rows, metrics


def _probe_z_locations(cfg: SimulationConfig3D) -> tuple[float, float]:
    probe_fraction = float(cfg.diffraction_probe_fraction)
    if not (0.0 < probe_fraction < 1.0):
        raise ValueError("diffraction_probe_fraction must be between 0 and 1.")
    if cfg.diffraction_top_probe_z is not None:
        top_z = float(cfg.diffraction_top_probe_z)
    else:
        top_lower_z = cfg.grating_z_max if cfg.has_grating_block else cfg.interface_z
        top_z = top_lower_z + probe_fraction * (cfg.physical_z_max - top_lower_z)
    if cfg.diffraction_bottom_probe_z is not None:
        bottom_z = float(cfg.diffraction_bottom_probe_z)
    else:
        bottom_z = cfg.interface_z + probe_fraction * (cfg.physical_z_min - cfg.interface_z)

    if not (cfg.interface_z < top_z < cfg.physical_z_max):
        raise ValueError(
            f"Top diffraction probe z={top_z:g} nm must be in the uniform air layer before the top PML."
        )
    if cfg.has_grating_block and top_z <= cfg.grating_z_max:
        raise ValueError(
            f"Top diffraction probe z={top_z:g} nm must be above the block top z={cfg.grating_z_max:g} nm."
        )
    if not (cfg.physical_z_min < bottom_z < cfg.interface_z):
        raise ValueError(
            f"Bottom diffraction probe z={bottom_z:g} nm must be in the uniform substrate layer before the bottom PML."
        )
    return top_z, bottom_z


def _sample_count_requirements(orders: list[DiffractionOrder3D]) -> tuple[int, int]:
    max_m = max((abs(order.m) for order in orders), default=0)
    max_n = max((abs(order.n) for order in orders), default=0)
    return 2 * int(max_m) + 1, 2 * int(max_n) + 1


def _validate_sample_counts(cfg: SimulationConfig3D, orders: list[DiffractionOrder3D]) -> tuple[int, int]:
    min_x, min_y = _sample_count_requirements(orders)
    if int(cfg.diffraction_sample_count_x) < min_x or int(cfg.diffraction_sample_count_y) < min_y:
        raise ValueError(
            "diffraction_sample_count_x/y are too small for the requested diffraction catalog: "
            f"got {cfg.diffraction_sample_count_x} x {cfg.diffraction_sample_count_y}, "
            f"need at least {min_x} x {min_y}."
        )
    return min_x, min_y


def _plane_points(cfg: SimulationConfig3D, z: float) -> np.ndarray:
    nx = int(cfg.diffraction_sample_count_x)
    ny = int(cfg.diffraction_sample_count_y)
    if nx <= 0 or ny <= 0:
        raise ValueError("diffraction_sample_count_x/y must be positive.")
    xs = cfg.x_min + (np.arange(nx, dtype=np.float64) + 0.5) * (cfg.x_max - cfg.x_min) / nx
    ys = cfg.y_min + (np.arange(ny, dtype=np.float64) + 0.5) * (cfg.y_max - cfg.y_min) / ny
    return np.asarray([[x, y, z] for y in ys for x in xs], dtype=np.float64)


def _sample_field_at_points(function, points: np.ndarray) -> np.ndarray:
    msh = function.function_space.mesh
    comm = msh.comm
    points = np.asarray(points, dtype=np.float64).reshape((-1, 3))
    tree = geometry.bb_tree(msh, msh.topology.dim)
    candidates = geometry.compute_collisions_points(tree, points)
    collisions = geometry.compute_colliding_cells(msh, candidates, points)
    local_indices: list[int] = []
    local_cells: list[int] = []
    for i in range(len(points)):
        links = collisions.links(i)
        if len(links) >= 1:
            local_indices.append(i)
            local_cells.append(int(links[0]))

    if local_indices:
        local_points = points[np.asarray(local_indices, dtype=np.int32)]
        local_values = function.eval(local_points, np.asarray(local_cells, dtype=np.int32))
        local_values = np.asarray(local_values, dtype=np.complex128)
        if local_values.ndim == 1:
            local_values = local_values.reshape((len(local_points), -1))
    else:
        local_values = np.zeros((0, 0), dtype=np.complex128)

    packets = comm.allgather((local_indices, local_values))
    width = 0
    for _, values in packets:
        if values.size:
            width = int(values.shape[1])
            break
    if width == 0:
        raise RuntimeError("No rank could evaluate the requested 3D diffraction probe points.")

    values = np.zeros((len(points), width), dtype=np.complex128)
    filled = np.zeros(len(points), dtype=bool)
    for indices, packet_values in packets:
        for row, point_index in enumerate(indices):
            if not filled[point_index]:
                values[int(point_index)] = packet_values[row]
                filled[int(point_index)] = True
    if not np.all(filled):
        missing = np.flatnonzero(~filled)[:5]
        examples = ", ".join(str(points[i].tolist()) for i in missing)
        raise RuntimeError(f"No mesh cell found for {np.count_nonzero(~filled)} 3D diffraction points: {examples}")
    return values[:, :3]


def _interpolation_points(V):
    points = V.element.interpolation_points
    return points() if callable(points) else points


def _h_from_curl_function(E_total, cfg: SimulationConfig3D):
    msh = E_total.function_space.mesh
    V_dg = fem.functionspace(msh, ("DG", max(int(cfg.visualization_degree), 1), (3,)))
    h_expr = (1.0 / (1j * cfg.k0 * cfg.mu_r)) * ufl.curl(E_total)
    H = fem.Function(V_dg, name="H_code_from_curl")
    H.interpolate(fem.Expression(h_expr, _interpolation_points(V_dg)))
    H.x.scatter_forward()
    return H


def fit_diffraction_amplitudes_from_samples(
    cfg: SimulationConfig3D,
    orders: list[DiffractionOrder3D],
    points: np.ndarray,
    e_values: np.ndarray,
    h_values: np.ndarray,
    *,
    side: str,
) -> tuple[dict[tuple[int, int, str, str], complex], float]:
    """Fit up/down modal amplitudes from sampled tangential E and H."""

    if side == "top":
        n_medium = complex(cfg.n_air)
        beta_getter = lambda order: order.beta_top
    elif side == "bottom":
        n_medium = complex(cfg.substrate_index)
        beta_getter = lambda order: order.beta_bottom
    else:
        raise ValueError("side must be 'top' or 'bottom'.")

    columns = _modal_columns(cfg, orders, points, side=side)

    if not columns:
        return {}, 0.0
    matrix = np.column_stack([column for _, column in columns]).astype(np.complex128)
    rhs = np.column_stack((e_values[:, 0], e_values[:, 1], h_values[:, 0], h_values[:, 1])).reshape(-1)
    amplitudes, *_ = np.linalg.lstsq(matrix, rhs, rcond=None)
    residual = float(np.linalg.norm(matrix @ amplitudes - rhs) / max(float(np.linalg.norm(rhs)), 1.0e-30))
    return {key: complex(value) for value, (key, _) in zip(amplitudes, columns)}, residual


def _modal_columns(
    cfg: SimulationConfig3D,
    orders: list[DiffractionOrder3D],
    points: np.ndarray,
    *,
    side: str,
) -> list[tuple[tuple[int, int, str, str], np.ndarray]]:
    if side == "top":
        n_medium = complex(cfg.n_air)
        beta_getter = lambda order: order.beta_top
    elif side == "bottom":
        n_medium = complex(cfg.substrate_index)
        beta_getter = lambda order: order.beta_bottom
    else:
        raise ValueError("side must be 'top' or 'bottom'.")

    columns: list[tuple[tuple[int, int, str, str], np.ndarray]] = []
    for order in orders:
        beta = beta_getter(order)
        for direction_name, vertical_sign in (("down", -1), ("up", 1)):
            for pol_name, pol_vec in polarization_basis_3d(
                order.alpha,
                order.gamma,
                beta,
                n_medium,
                vertical_sign,
                cfg,
            ):
                kvec, e_vec, h_vec = mode_eh_vectors(order.alpha, order.gamma, beta, pol_vec, vertical_sign, cfg)
                phase = np.exp(
                    1j
                    * (
                        kvec[0] * points[:, 0]
                        + kvec[1] * points[:, 1]
                        + kvec[2] * points[:, 2]
                    )
                )
                values = np.column_stack(
                    (
                        phase * e_vec[0],
                        phase * e_vec[1],
                        phase * h_vec[0],
                        phase * h_vec[1],
                    )
                ).reshape(-1)
                columns.append(((order.m, order.n, pol_name, direction_name), values))
    return columns


def _mode_field(function_space, kvec: np.ndarray, e_vec: np.ndarray):
    field = fem.Function(function_space, name="diffraction_mode_calibration")

    def eval_field(x):
        coords = x.T
        phase = np.exp(1j * (kvec[0] * coords[:, 0] + kvec[1] * coords[:, 1] + kvec[2] * coords[:, 2]))
        return (phase[:, None] * e_vec[None, :]).T

    field.interpolate(eval_field)
    field.x.scatter_forward()
    return field


def _mode_key_vectors(
    cfg: SimulationConfig3D,
    orders: list[DiffractionOrder3D],
    *,
    side: str,
) -> dict[tuple[int, int, str, str], tuple[np.ndarray, np.ndarray]]:
    if side == "top":
        n_medium = complex(cfg.n_air)
        beta_getter = lambda order: order.beta_top
    elif side == "bottom":
        n_medium = complex(cfg.substrate_index)
        beta_getter = lambda order: order.beta_bottom
    else:
        raise ValueError("side must be 'top' or 'bottom'.")
    vectors: dict[tuple[int, int, str, str], tuple[np.ndarray, np.ndarray]] = {}
    for order in orders:
        beta = beta_getter(order)
        for direction_name, vertical_sign in (("down", -1), ("up", 1)):
            for pol_name, pol_vec in polarization_basis_3d(order.alpha, order.gamma, beta, n_medium, vertical_sign, cfg):
                kvec, e_vec, _ = mode_eh_vectors(order.alpha, order.gamma, beta, pol_vec, vertical_sign, cfg)
                vectors[(order.m, order.n, pol_name, direction_name)] = (kvec, e_vec)
    return vectors


def _calibrated_amplitudes(
    raw: dict[tuple[int, int, str, str], complex],
    E_total,
    cfg: SimulationConfig3D,
    orders: list[DiffractionOrder3D],
    points: np.ndarray,
    *,
    side: str,
) -> tuple[dict[tuple[int, int, str, str], complex], float | None]:
    keys = [key for key, _ in _modal_columns(cfg, orders, points, side=side)]
    if not keys:
        return raw, None
    vectors = _mode_key_vectors(cfg, orders, side=side)
    response_columns: list[list[complex]] = []
    for key in keys:
        kvec, e_vec = vectors[key]
        mode_field = _mode_field(E_total.function_space, kvec, e_vec)
        mode_h = _h_from_curl_function(mode_field, cfg)
        mode_e_values = _sample_field_at_points(mode_field, points)
        mode_h_values = _sample_field_at_points(mode_h, points)
        apparent, _ = fit_diffraction_amplitudes_from_samples(
            cfg,
            orders,
            points,
            mode_e_values,
            mode_h_values,
            side=side,
        )
        response_columns.append([apparent.get(row_key, 0.0 + 0.0j) for row_key in keys])
    response = np.asarray(response_columns, dtype=np.complex128).T
    raw_vector = np.asarray([raw.get(key, 0.0 + 0.0j) for key in keys], dtype=np.complex128)
    condition = float(np.linalg.cond(response)) if response.size else None
    if condition is None or not np.isfinite(condition) or condition > 1.0e12:
        return raw, condition
    corrected = np.linalg.solve(response, raw_vector)
    return {key: complex(value) for key, value in zip(keys, corrected)}, condition


def _complex_text(value: complex) -> str:
    number = complex(value)
    return f"{number.real:.16e}{number.imag:+.16e}j"


def compute_diffraction_orders_3d(
    mesh_data,
    cfg: SimulationConfig3D,
    E_total,
    out_dir: Path,
    *,
    E_scattered=None,
) -> dict[str, Any]:
    """Compute 3D reflected/transmitted diffraction-order powers from probes."""

    out_dir.mkdir(parents=True, exist_ok=True)
    comm = mesh_data.mesh.comm
    power_orders = enumerate_diffraction_orders_3d(cfg)
    orders, fit_includes_evanescent_neighbors = _orders_for_modal_fit(cfg, power_orders)
    min_sample_count_x, min_sample_count_y = _validate_sample_counts(cfg, orders)
    top_z, bottom_z = _probe_z_locations(cfg)
    top_points = _plane_points(cfg, top_z)
    bottom_points = _plane_points(cfg, bottom_z)
    use_exact_layered_background = E_scattered is not None and cfg.stage_case in {
        "stage4_block_grating",
        "stage4_flat_layer_sanity",
    }
    if use_exact_layered_background:
        # Stage 4 solves only the scattered field.  The flat-layer background is
        # analytic, so using an interpolated E_total at EUV wavelengths can
        # corrupt R/T when the mesh is still too coarse to represent the fast
        # substrate phase.  Official power postprocess therefore samples the
        # numerical scattered field and adds the exact layered background on the
        # probe planes.
        H_scattered = _h_from_curl_function(E_scattered, cfg)
        top_e = _sample_field_at_points(E_scattered, top_points) + electric_field_code_values(cfg, top_points)
        top_h = _sample_field_at_points(H_scattered, top_points) + magnetic_field_code_values(cfg, top_points)
        bottom_e = _sample_field_at_points(E_scattered, bottom_points) + electric_field_code_values(cfg, bottom_points)
        bottom_h = _sample_field_at_points(H_scattered, bottom_points) + magnetic_field_code_values(cfg, bottom_points)
    else:
        H_total = _h_from_curl_function(E_total, cfg)
        top_e = _sample_field_at_points(E_total, top_points)
        top_h = _sample_field_at_points(H_total, top_points)
        bottom_e = _sample_field_at_points(E_total, bottom_points)
        bottom_h = _sample_field_at_points(H_total, bottom_points)
    incident_power = _incident_power(cfg)
    e_fourier_rows, e_fourier_metrics = _e_fourier_order_powers(
        cfg,
        power_orders,
        top_points,
        top_e,
        bottom_points,
        bottom_e,
        incident_power,
    )
    eh_fourier_rows, eh_fourier_metrics = _eh_fourier_order_powers(
        cfg,
        power_orders,
        top_points,
        top_e,
        top_h,
        bottom_points,
        bottom_e,
        bottom_h,
        incident_power,
    )
    top_flux_outward = _sampled_flux_code_units(top_e, top_h, np.asarray((0.0, 0.0, 1.0)), cfg)
    bottom_flux_outward = _sampled_flux_code_units(bottom_e, bottom_h, np.asarray((0.0, 0.0, -1.0)), cfg)
    R_from_net_flux = 1.0 + top_flux_outward / incident_power
    T_from_net_flux = bottom_flux_outward / incident_power
    compute_modal_diagnostic = bool(cfg.diffraction_compute_modal_diagnostic)
    if compute_modal_diagnostic:
        top_amp, top_residual = fit_diffraction_amplitudes_from_samples(
            cfg, orders, top_points, top_e, top_h, side="top"
        )
        bottom_amp, bottom_residual = fit_diffraction_amplitudes_from_samples(
            cfg, orders, bottom_points, bottom_e, bottom_h, side="bottom"
        )
        top_amp, top_response_condition = _calibrated_amplitudes(
            top_amp,
            E_total,
            cfg,
            orders,
            top_points,
            side="top",
        )
        bottom_amp, bottom_response_condition = _calibrated_amplitudes(
            bottom_amp,
            E_total,
            cfg,
            orders,
            bottom_points,
            side="bottom",
        )
    else:
        top_amp = {}
        bottom_amp = {}
        top_residual = None
        bottom_residual = None
        top_response_condition = None
        bottom_response_condition = None

    top_normal = np.asarray((0.0, 0.0, 1.0), dtype=np.float64)
    bottom_normal = np.asarray((0.0, 0.0, -1.0), dtype=np.float64)
    power_order_keys = {(order.m, order.n) for order in power_orders}
    rows: list[dict[str, Any]] = []
    R_total = 0.0
    T_total = 0.0
    for order in orders:
        top_basis = polarization_basis_3d(order.alpha, order.gamma, order.beta_top, cfg.n_air, 1, cfg)
        bottom_basis = polarization_basis_3d(
            order.alpha, order.gamma, order.beta_bottom, cfg.substrate_index, -1, cfg
        )
        bottom_by_name = {name: vec for name, vec in bottom_basis}
        for pol_name, top_pol in top_basis:
            bottom_pol = bottom_by_name.get(pol_name)
            if bottom_pol is None:
                continue
            ref_amp = top_amp.get((order.m, order.n, pol_name, "up"), 0.0 + 0.0j)
            trn_amp = bottom_amp.get((order.m, order.n, pol_name, "down"), 0.0 + 0.0j)
            top_k, top_e_vec, _ = mode_eh_vectors(order.alpha, order.gamma, order.beta_top, top_pol, 1, cfg)
            bottom_k, bottom_e_vec, _ = mode_eh_vectors(
                order.alpha, order.gamma, order.beta_bottom, bottom_pol, -1, cfg
            )
            R = 0.0
            T = 0.0
            include_in_total_power = (order.m, order.n) in power_order_keys
            if include_in_total_power and order.top_propagating:
                top_e_at_plane = top_e_vec * np.exp(1j * top_k[2] * top_z)
                R = abs(ref_amp) ** 2 * _mode_power(top_k, top_e_at_plane, cfg, top_normal) / incident_power
                R_total += float(R)
            if include_in_total_power and order.bottom_propagating:
                bottom_e_at_plane = bottom_e_vec * np.exp(1j * bottom_k[2] * bottom_z)
                T = abs(trn_amp) ** 2 * _mode_power(bottom_k, bottom_e_at_plane, cfg, bottom_normal) / incident_power
                T_total += float(T)
            rows.append(
                {
                    "m": order.m,
                    "n": order.n,
                    "polarization": pol_name,
                    "alpha": order.alpha,
                    "gamma": order.gamma,
                    "beta_top": order.beta_top,
                    "beta_bottom": order.beta_bottom,
                    "top_propagating": order.top_propagating,
                    "bottom_propagating": order.bottom_propagating,
                    "included_in_total_power": include_in_total_power,
                    "rayleigh_warning": order.rayleigh_warning_top or order.rayleigh_warning_bottom,
                    "rayleigh_warning_top": order.rayleigh_warning_top,
                    "rayleigh_warning_bottom": order.rayleigh_warning_bottom,
                    "reflected_amplitude": ref_amp,
                    "transmitted_amplitude": trn_amp,
                    "R": float(R),
                    "T": float(T),
                    **e_fourier_rows.get((order.m, order.n, pol_name), {}),
                    **eh_fourier_rows.get((order.m, order.n, pol_name), {}),
                    "top_fit_residual": top_residual,
                    "bottom_fit_residual": bottom_residual,
                }
            )

    modal_R_total = float(R_total) if compute_modal_diagnostic else None
    modal_T_total = float(T_total) if compute_modal_diagnostic else None
    modal_R_plus_T = float(modal_R_total + modal_T_total) if compute_modal_diagnostic else None
    official_R_total = float(eh_fourier_metrics["R_total_from_eh_fourier"])
    official_T_total = float(eh_fourier_metrics["T_total_from_eh_fourier"])
    official_R_plus_T = float(eh_fourier_metrics["R_plus_T_from_eh_fourier"])
    flux_R_total = float(R_from_net_flux)
    flux_T_total = float(T_from_net_flux)
    flux_R_plus_T = float(flux_R_total + flux_T_total)
    diagnostic_A_balance = float(1.0 - official_R_plus_T)
    flux_A_balance = float(1.0 - flux_R_plus_T)
    metrics = {
        # Legacy aliases retained so old scripts that call this diagnostic
        # function directly can still read R_total/T_total.  The power source
        # and explicit diagnostic_* aliases below make clear these are not the
        # Stage-4 dtn_port official values.
        "R_total": official_R_total,
        "T_total": official_T_total,
        "R_plus_T": official_R_plus_T,
        "A_balance": diagnostic_A_balance,
        "diffraction_total_power_source": OFFICIAL_STAGE4_DIFFRACTION_POWER_SOURCE,
        "power_source": DIAGNOSTIC_EH_FOURIER_PROBE_POWER_SOURCE,
        "diagnostic_power_legacy_aliases": ["R_total", "T_total", "R_plus_T", "A_balance"],
        "diffraction_eh_fourier_note": OFFICIAL_STAGE4_DIFFRACTION_POWER_NOTE,
        "diffraction_e_fourier_note": E_FOURIER_DIAGNOSTIC_NOTE,
        "R_total_diagnostic_eh_fourier": official_R_total,
        "T_total_diagnostic_eh_fourier": official_T_total,
        "R_plus_T_diagnostic_eh_fourier": official_R_plus_T,
        "A_balance_diagnostic_eh_fourier": diagnostic_A_balance,
        "diagnostic_eh_fourier_probe_R_total": official_R_total,
        "diagnostic_eh_fourier_probe_T_total": official_T_total,
        "diagnostic_eh_fourier_probe_R_plus_T": official_R_plus_T,
        "diagnostic_eh_fourier_probe_A_balance": diagnostic_A_balance,
        "R_total_diagnostic_e_only_fourier": float(e_fourier_metrics["R_total_from_e_fourier"]),
        "T_total_diagnostic_e_only_fourier": float(e_fourier_metrics["T_total_from_e_fourier"]),
        "R_plus_T_diagnostic_e_only_fourier": float(e_fourier_metrics["R_plus_T_from_e_fourier"]),
        "A_balance_diagnostic_e_only_fourier": float(e_fourier_metrics["A_balance_from_e_fourier"]),
        "diffraction_background_evaluated_analytically": bool(use_exact_layered_background),
        **eh_fourier_metrics,
        **e_fourier_metrics,
        "diffraction_modal_order_powers_diagnostic_only": True,
        "diffraction_modal_diagnostic_computed": compute_modal_diagnostic,
        "R_total_from_modal_orders": modal_R_total,
        "T_total_from_modal_orders": modal_T_total,
        "R_plus_T_from_modal_orders": modal_R_plus_T,
        "A_balance_from_modal_orders": None if modal_R_plus_T is None else float(1.0 - modal_R_plus_T),
        "top_net_flux_code_units": float(top_flux_outward),
        "bottom_net_flux_code_units": float(bottom_flux_outward),
        "sampled_net_flux_diagnostic_only": True,
        "sampled_net_flux_note": SAMPLED_NET_FLUX_DIAGNOSTIC_NOTE,
        "R_total_from_net_flux": flux_R_total,
        "T_total_from_net_flux": flux_T_total,
        "R_plus_T_from_net_flux": flux_R_plus_T,
        "A_balance_from_net_flux": flux_A_balance,
        "R_total_diagnostic_sampled_net_flux": flux_R_total,
        "T_total_diagnostic_sampled_net_flux": flux_T_total,
        "R_plus_T_diagnostic_sampled_net_flux": flux_R_plus_T,
        "A_balance_diagnostic_sampled_net_flux": flux_A_balance,
        "modal_minus_flux_R_total": None if modal_R_total is None else float(modal_R_total - flux_R_total),
        "modal_minus_flux_T_total": None if modal_T_total is None else float(modal_T_total - flux_T_total),
        "modal_minus_flux_R_plus_T": None if modal_R_plus_T is None else float(modal_R_plus_T - flux_R_plus_T),
        "diffraction_order_count": len(power_orders),
        "diffraction_fit_order_count": len(orders),
        "diffraction_channel_count": len(rows),
        "diffraction_zero_order_only": bool(cfg.diffraction_zero_order_only),
        "diffraction_order_max_m_requested": cfg.diffraction_order_max_m,
        "diffraction_order_max_n_requested": cfg.diffraction_order_max_n,
        "diffraction_order_max_m_resolved": int(max((abs(order.m) for order in power_orders), default=0)),
        "diffraction_order_max_n_resolved": int(max((abs(order.n) for order in power_orders), default=0)),
        "diffraction_fit_includes_evanescent_neighbors": bool(fit_includes_evanescent_neighbors),
        "diffraction_top_probe_z": top_z,
        "diffraction_bottom_probe_z": bottom_z,
        "diffraction_probe_position_fraction_from_interface_to_physical_boundary": float(cfg.diffraction_probe_fraction),
        "diffraction_top_probe_distance_to_pml_start": float(cfg.physical_z_max - top_z),
        "diffraction_bottom_probe_distance_to_pml_start": float(bottom_z - cfg.physical_z_min),
        "diffraction_top_probe_distance_above_block": float(top_z - cfg.grating_z_max) if cfg.has_grating_block else None,
        "diffraction_bottom_probe_distance_below_interface": float(cfg.interface_z - bottom_z),
        "diffraction_sample_count_x": int(cfg.diffraction_sample_count_x),
        "diffraction_sample_count_y": int(cfg.diffraction_sample_count_y),
        "diffraction_sample_point_count_per_plane": int(cfg.diffraction_sample_count_x) * int(cfg.diffraction_sample_count_y),
        "diffraction_min_sample_count_x_for_fit_orders": int(min_sample_count_x),
        "diffraction_min_sample_count_y_for_fit_orders": int(min_sample_count_y),
        "diffraction_top_fit_residual": top_residual,
        "diffraction_bottom_fit_residual": bottom_residual,
        "diffraction_top_fe_response_condition": top_response_condition,
        "diffraction_bottom_fe_response_condition": bottom_response_condition,
        "incident_power_code_units": incident_power,
        "probe_power_file": "probe_power.json",
        "flux_power_file": "flux_power.json",
        "diffraction_orders_json": str(out_dir / "diffraction_orders_3d.json"),
        "diffraction_orders_csv": str(out_dir / "diffraction_orders_3d.csv"),
    }

    if comm.rank == 0:
        payload = {"metrics": metrics, "orders": rows}
        (out_dir / "diffraction_orders_3d.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        csv_rows = []
        for row in rows:
            csv_rows.append(
                {
                    key: _complex_text(value) if isinstance(value, complex) else value
                    for key, value in row.items()
                }
            )
        with (out_dir / "diffraction_orders_3d.csv").open("w", newline="", encoding="utf-8") as fp:
            writer = csv.DictWriter(fp, fieldnames=list(csv_rows[0].keys()) if csv_rows else ["m", "n"])
            writer.writeheader()
            writer.writerows(csv_rows)
        (out_dir / "power_metrics_3d.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        probe_payload = {
            "method": DIAGNOSTIC_EH_FOURIER_PROBE_POWER_SOURCE,
            "role": "diagnostic",
            "status": "ok",
            "power_source": DIAGNOSTIC_EH_FOURIER_PROBE_POWER_SOURCE,
            "R_total": official_R_total,
            "T_total": official_T_total,
            "A_balance": diagnostic_A_balance,
            "R_plus_T": official_R_plus_T,
            "R_total_diagnostic_eh_fourier": official_R_total,
            "T_total_diagnostic_eh_fourier": official_T_total,
            "A_balance_diagnostic_eh_fourier": diagnostic_A_balance,
            "R_plus_T_diagnostic_eh_fourier": official_R_plus_T,
            "incident_power_code_units": incident_power,
            "top_probe_z": top_z,
            "bottom_probe_z": bottom_z,
            "sample_count_x": int(cfg.diffraction_sample_count_x),
            "sample_count_y": int(cfg.diffraction_sample_count_y),
            "sample_point_count_per_plane": int(cfg.diffraction_sample_count_x) * int(cfg.diffraction_sample_count_y),
            "fit_residuals": {
                "top_eh_fourier_max": metrics["diffraction_top_eh_fourier_fit_residual_max"],
                "bottom_eh_fourier_max": metrics["diffraction_bottom_eh_fourier_fit_residual_max"],
                "top_modal_diagnostic": top_residual,
                "bottom_modal_diagnostic": bottom_residual,
            },
            "diffraction_zero_order_only": bool(cfg.diffraction_zero_order_only),
            "diffraction_order_max_m_requested": cfg.diffraction_order_max_m,
            "diffraction_order_max_n_requested": cfg.diffraction_order_max_n,
            "per_order": rows,
            "diagnostic_e_fourier": {
                "note": E_FOURIER_DIAGNOSTIC_NOTE,
                "power_source": DIAGNOSTIC_E_ONLY_FOURIER_PROBE_POWER_SOURCE,
                "R_total": metrics["R_total_from_e_fourier"],
                "T_total": metrics["T_total_from_e_fourier"],
                "A_balance": metrics["A_balance_from_e_fourier"],
            },
            "note": OFFICIAL_STAGE4_DIFFRACTION_POWER_NOTE,
        }
        (out_dir / "probe_power.json").write_text(
            json.dumps(probe_payload, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        flux_payload = {
            "method": DIAGNOSTIC_SAMPLED_NET_FLUX_POWER_SOURCE,
            "role": "diagnostic",
            "status": "ok",
            "power_source": DIAGNOSTIC_SAMPLED_NET_FLUX_POWER_SOURCE,
            "top_flux_outward": float(top_flux_outward),
            "bottom_flux_outward": float(bottom_flux_outward),
            "incident_power_code_units": incident_power,
            "R_total_from_net_flux": flux_R_total,
            "T_total_from_net_flux": flux_T_total,
            "A_flux": flux_A_balance,
            "R_plus_T_from_net_flux": flux_R_plus_T,
            "R_total_diagnostic_sampled_net_flux": flux_R_total,
            "T_total_diagnostic_sampled_net_flux": flux_T_total,
            "A_balance_diagnostic_sampled_net_flux": flux_A_balance,
            "top_probe_z": top_z,
            "bottom_probe_z": bottom_z,
            "sample_count_x": int(cfg.diffraction_sample_count_x),
            "sample_count_y": int(cfg.diffraction_sample_count_y),
            "note": "does_not_resolve_diffraction_orders; " + SAMPLED_NET_FLUX_DIAGNOSTIC_NOTE,
        }
        (out_dir / "flux_power.json").write_text(
            json.dumps(flux_payload, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
    comm.barrier()
    return metrics
