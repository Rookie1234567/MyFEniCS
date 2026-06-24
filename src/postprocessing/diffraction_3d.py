from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import ufl
from mpi4py import MPI
from petsc4py import PETSc

from dolfinx import fem, geometry

from ..common.config_3d import SimulationConfig3D


@dataclass(frozen=True)
class DiffractionOrder3D:
    """One transverse Floquet wavevector shared by top and bottom media."""

    m: int
    n: int
    alpha: complex
    gamma: complex
    beta_top: complex
    beta_bottom: complex
    top_propagating: bool
    bottom_propagating: bool
    rayleigh_warning_top: bool
    rayleigh_warning_bottom: bool


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
    if root.imag < -1.0e-14 or (abs(root.imag) < 1.0e-14 and root.real < 0.0):
        root = -root
    return complex(root)


def _is_propagating(beta: complex) -> bool:
    return abs(complex(beta).imag) < 1.0e-9 and complex(beta).real > 1.0e-12


def _near_rayleigh(beta: complex, n_medium: complex, cfg: SimulationConfig3D) -> bool:
    scale = max(abs(complex(n_medium) * cfg.k0), 1.0e-30)
    return abs(complex(beta)) / scale < cfg.diffraction_rayleigh_tol


def enumerate_diffraction_orders_3d(
    cfg: SimulationConfig3D,
    *,
    max_m_override: int | None = None,
    max_n_override: int | None = None,
) -> list[DiffractionOrder3D]:
    """Enumerate transverse Floquet orders for the 3D periodic cell.

    The first Stage-4 benchmark defaults to zero-order-only because the
    350 nm x 300 nm cell at lambda=633 nm has no propagating higher orders in
    air/substrate.  Setting diffraction_zero_order_only=False or explicit
    max_m/max_n exposes the same catalog used later by an auxiliary modal port.
    """

    if max_m_override is not None or max_n_override is not None:
        max_m = 0 if max_m_override is None else int(max_m_override)
        max_n = 0 if max_n_override is None else int(max_n_override)
    elif cfg.diffraction_zero_order_only:
        max_m = 0
        max_n = 0
    else:
        n_max = max(abs(complex(cfg.n_air)), abs(complex(cfg.substrate_index)))
        max_m = cfg.diffraction_order_max_m
        max_n = cfg.diffraction_order_max_n
        # Official power orders should cover propagating candidates, not an
        # extra evanescent buffer.  Adding far-evanescent orders to the main
        # least-squares fit can make the modal matrix badly conditioned and
        # corrupt the propagating R/T values.  The small-period zero-order
        # benchmark still adds nearest evanescent neighbors separately in
        # _orders_for_modal_fit().
        if max_m is None:
            max_m = int(np.floor((n_max * cfg.k0 + abs(cfg.kx)) * (cfg.x_max - cfg.x_min) / (2.0 * np.pi) + 1.0e-12))
        if max_n is None:
            max_n = int(np.floor((n_max * cfg.k0 + abs(cfg.ky)) * (cfg.y_max - cfg.y_min) / (2.0 * np.pi) + 1.0e-12))
    if max_m < 0 or max_n < 0:
        raise ValueError("diffraction_order_max_m/n must be non-negative.")

    orders: list[DiffractionOrder3D] = []
    for m in range(-int(max_m), int(max_m) + 1):
        for n in range(-int(max_n), int(max_n) + 1):
            alpha = complex(cfg.kx + 2.0 * np.pi * m / (cfg.x_max - cfg.x_min))
            gamma = complex(cfg.ky + 2.0 * np.pi * n / (cfg.y_max - cfg.y_min))
            beta_top = _positive_sqrt((cfg.k0 * complex(cfg.n_air)) ** 2 - alpha**2 - gamma**2)
            beta_bottom = _positive_sqrt(
                (cfg.k0 * complex(cfg.substrate_index)) ** 2 - alpha**2 - gamma**2
            )
            orders.append(
                DiffractionOrder3D(
                    m=m,
                    n=n,
                    alpha=alpha,
                    gamma=gamma,
                    beta_top=beta_top,
                    beta_bottom=beta_bottom,
                    top_propagating=_is_propagating(beta_top),
                    bottom_propagating=_is_propagating(beta_bottom),
                    rayleigh_warning_top=_near_rayleigh(beta_top, cfg.n_air, cfg),
                    rayleigh_warning_bottom=_near_rayleigh(beta_bottom, cfg.substrate_index, cfg),
                )
            )
    return orders


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


def polarization_basis_3d(
    alpha: complex,
    gamma: complex,
    beta: complex,
    n_medium: complex,
    vertical_sign: int,
    cfg: SimulationConfig3D,
) -> list[tuple[str, np.ndarray]]:
    """Return two transverse E-polarization vectors for one 3D order."""

    kt_norm = float(np.sqrt(abs(alpha) ** 2 + abs(gamma) ** 2))
    if kt_norm < 1.0e-12 * max(abs(cfg.k0 * complex(n_medium)), 1.0):
        return [
            ("x", np.asarray((1.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j), dtype=np.complex128)),
            ("y", np.asarray((0.0 + 0.0j, 1.0 + 0.0j, 0.0 + 0.0j), dtype=np.complex128)),
        ]

    s_vec = np.asarray((-gamma / kt_norm, alpha / kt_norm, 0.0 + 0.0j), dtype=np.complex128)
    kvec = np.asarray((alpha, gamma, vertical_sign * beta), dtype=np.complex128)
    direction = kvec / (cfg.k0 * complex(n_medium))
    p_vec = np.cross(direction, s_vec)
    p_norm = float(np.sqrt(np.sum(np.abs(p_vec) ** 2)))
    if p_norm <= 0.0:
        raise ValueError("Cannot build p polarization for a degenerate 3D diffraction mode.")
    return [("s", s_vec), ("p", p_vec / p_norm)]


def mode_eh_vectors(
    alpha: complex,
    gamma: complex,
    beta: complex,
    polarization: np.ndarray,
    vertical_sign: int,
    cfg: SimulationConfig3D,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return k, E, H code-unit vectors for one unit-amplitude mode."""

    kvec = np.asarray((alpha, gamma, vertical_sign * beta), dtype=np.complex128)
    e_vec = np.asarray(polarization, dtype=np.complex128)
    h_vec = np.cross(kvec, e_vec) / (cfg.k0 * complex(cfg.mu_r))
    return kvec, e_vec, h_vec


def _mode_power(
    kvec: np.ndarray,
    e_vec: np.ndarray,
    cfg: SimulationConfig3D,
    outward_normal: np.ndarray,
) -> float:
    h_vec = np.cross(kvec, e_vec) / (cfg.k0 * complex(cfg.mu_r))
    s_vec = 0.5 * np.real(np.cross(e_vec, np.conj(h_vec)))
    density = float(np.dot(s_vec, outward_normal))
    return max(density, 0.0) * (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)


def _incident_power(cfg: SimulationConfig3D) -> float:
    e_vec = complex(cfg.incident_amplitude) * np.asarray(cfg.polarization_vector, dtype=np.complex128)
    h_vec = np.cross(np.asarray(cfg.wavevector, dtype=np.complex128), e_vec) / (cfg.k0 * complex(cfg.mu_r))
    s_vec = 0.5 * np.real(np.cross(e_vec, np.conj(h_vec)))
    area = (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
    return max(float(-s_vec[2]) * area, 1.0e-30)


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
    """Compute propagating R/T from 2D Fourier coefficients of E on probe planes.

    This is the official Stage-4 power path for coarse Nedelec runs.  The older
    E/H least-squares modal fit is still reported as a diagnostic because H is
    reconstructed from the FE curl and can over-amplify high-order channels.
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
                R = abs(ref_amp) ** 2 * _mode_power(top_k, top_e_vec, cfg, top_normal) / incident_power
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
                T = abs(trn_amp) ** 2 * _mode_power(bottom_k, bottom_e_vec, cfg, bottom_normal) / incident_power
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


def _probe_z_locations(cfg: SimulationConfig3D) -> tuple[float, float]:
    probe_fraction = 0.95
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


def compute_diffraction_orders_3d(mesh_data, cfg: SimulationConfig3D, E_total, out_dir: Path) -> dict[str, Any]:
    """Compute 3D reflected/transmitted diffraction-order powers from probes."""

    out_dir.mkdir(parents=True, exist_ok=True)
    comm = mesh_data.mesh.comm
    power_orders = enumerate_diffraction_orders_3d(cfg)
    orders, fit_includes_evanescent_neighbors = _orders_for_modal_fit(cfg, power_orders)
    min_sample_count_x, min_sample_count_y = _validate_sample_counts(cfg, orders)
    top_z, bottom_z = _probe_z_locations(cfg)
    top_points = _plane_points(cfg, top_z)
    bottom_points = _plane_points(cfg, bottom_z)
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
    top_flux_outward = _sampled_flux_code_units(top_e, top_h, np.asarray((0.0, 0.0, 1.0)), cfg)
    bottom_flux_outward = _sampled_flux_code_units(bottom_e, bottom_h, np.asarray((0.0, 0.0, -1.0)), cfg)
    R_from_net_flux = 1.0 + top_flux_outward / incident_power
    T_from_net_flux = bottom_flux_outward / incident_power
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
                R = abs(ref_amp) ** 2 * _mode_power(top_k, top_e_vec, cfg, top_normal) / incident_power
                R_total += float(R)
            if include_in_total_power and order.bottom_propagating:
                T = abs(trn_amp) ** 2 * _mode_power(bottom_k, bottom_e_vec, cfg, bottom_normal) / incident_power
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
                    "top_fit_residual": top_residual,
                    "bottom_fit_residual": bottom_residual,
                }
            )

    modal_R_total = float(R_total)
    modal_T_total = float(T_total)
    modal_R_plus_T = float(modal_R_total + modal_T_total)
    official_R_total = float(e_fourier_metrics["R_total_from_e_fourier"])
    official_T_total = float(e_fourier_metrics["T_total_from_e_fourier"])
    official_R_plus_T = float(e_fourier_metrics["R_plus_T_from_e_fourier"])
    flux_R_total = float(R_from_net_flux)
    flux_T_total = float(T_from_net_flux)
    flux_R_plus_T = float(flux_R_total + flux_T_total)
    metrics = {
        "R_total": official_R_total,
        "T_total": official_T_total,
        "R_plus_T": official_R_plus_T,
        "A_balance": float(1.0 - official_R_plus_T),
        "diffraction_total_power_source": "e_fourier_orders",
        "diffraction_e_fourier_note": (
            "Official Stage-4 R/T uses Fourier coefficients of E on uniform probe planes. "
            "The older E/H least-squares modal powers remain diagnostic because H is reconstructed from FE curl."
        ),
        **e_fourier_metrics,
        "diffraction_modal_order_powers_diagnostic_only": True,
        "R_total_from_modal_orders": modal_R_total,
        "T_total_from_modal_orders": modal_T_total,
        "R_plus_T_from_modal_orders": modal_R_plus_T,
        "A_balance_from_modal_orders": float(1.0 - modal_R_plus_T),
        "top_net_flux_code_units": float(top_flux_outward),
        "bottom_net_flux_code_units": float(bottom_flux_outward),
        "sampled_net_flux_diagnostic_only": True,
        "sampled_net_flux_note": "Diagnostic only: this uses H reconstructed from the finite-element curl on probe samples. Official Stage-4 R/T uses modal amplitudes.",
        "R_total_from_net_flux": flux_R_total,
        "T_total_from_net_flux": flux_T_total,
        "R_plus_T_from_net_flux": flux_R_plus_T,
        "A_balance_from_net_flux": float(1.0 - flux_R_plus_T),
        "modal_minus_flux_R_total": float(modal_R_total - flux_R_total),
        "modal_minus_flux_T_total": float(modal_T_total - flux_T_total),
        "modal_minus_flux_R_plus_T": float(modal_R_plus_T - flux_R_plus_T),
        "diffraction_order_count": len(power_orders),
        "diffraction_fit_order_count": len(orders),
        "diffraction_channel_count": len(rows),
        "diffraction_zero_order_only": bool(cfg.diffraction_zero_order_only),
        "diffraction_fit_includes_evanescent_neighbors": bool(fit_includes_evanescent_neighbors),
        "diffraction_top_probe_z": top_z,
        "diffraction_bottom_probe_z": bottom_z,
        "diffraction_probe_position_fraction_from_interface_to_physical_boundary": 0.95,
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
    comm.barrier()
    return metrics
