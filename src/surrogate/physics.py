"""Deterministic physical reconstruction for surrogate predictions."""

from __future__ import annotations

import numpy as np


def power_mask_authority(points: np.ndarray, *, m_values=range(-7, 4),
                         wavelength_nm: float = 13.5) -> dict[str, np.ndarray]:
    """Extract independent top/bottom masks from the runtime Floquet policy.

    This intentionally delegates propagation and Poynting evaluation to the
    same production configuration/mode implementation used by Full3D.  It is
    not an algebraic duplicate of the old single-side helper.  The returned
    dispersion and power identities are kept separate: a lossy substrate can
    have a complex beta while its selected outgoing m=0 port still carries
    finite positive power.
    """
    values = np.asarray(points, dtype=np.float64)
    if values.ndim == 1:
        values = values[None, :]
    if values.ndim != 2 or values.shape[1] != 4:
        raise ValueError("points must have shape (n,4)")
    # mpi4py/OpenMPI in the FEM environment uses /mnt/c by default, which is
    # read-only in the CPU sandbox.  The import remains lazy so surrogate-only
    # code does not initialize MPI until mask authority is requested.
    import os
    os.environ.setdefault("TMPDIR", "/tmp")
    from src.common.modes_3d import (enumerate_diffraction_orders_3d,
                                     mode_eh_vectors, mode_power,
                                     polarization_basis_3d)
    from src.forward_data.task002_full3d import build_task002_full3d_config
    from src.forward_data.task002_schema import Task002ForwardParameters

    orders_m = tuple(int(m) for m in m_values)
    power = np.zeros((len(values), 2 * len(orders_m), 2), dtype=bool)
    dispersion = np.zeros_like(power)
    for row, point in enumerate(values):
        parameters = Task002ForwardParameters(
            height_nm=float(point[0]), width_x_nm=float(point[1]),
            grazing_deg=float(point[2]), azimuth_deg=float(point[3]),
            model_id="S_PROD_FULL3D_STATIC_P5_H10_NY4",
        )
        cfg = build_task002_full3d_config(parameters)
        order_map = {item.m: item for item in enumerate_diffraction_orders_3d(
            cfg, max_m_override=max(abs(m) for m in orders_m), max_n_override=0,
        )}
        sides = (
            ("top", cfg.n_air, np.asarray((0.0, 0.0, 1.0)), 1),
            ("bottom", cfg.substrate_index, np.asarray((0.0, 0.0, -1.0)), -1),
        )
        for side_index, (_side, medium, normal, sign) in enumerate(sides):
            for order_index, m in enumerate(orders_m):
                order = order_map[m]
                beta = order.beta_top if side_index == 0 else order.beta_bottom
                propagating = (order.top_propagating if side_index == 0
                               else order.bottom_propagating)
                # outgoing_port_modes_3d deliberately retains incident m=0
                # even when a lossy-medium beta is complex.
                selected = bool(m == 0 or propagating)
                dispersion[row, side_index * len(orders_m) + order_index, :] = bool(propagating)
                for component, (_name, e_vec) in enumerate(polarization_basis_3d(
                        order.alpha, order.gamma, beta, medium, sign, cfg)):
                    k_vec, e_vec, _h_vec = mode_eh_vectors(
                        order.alpha, order.gamma, beta, e_vec, sign, cfg)
                    carried = (selected and np.isfinite(mode_power(
                        k_vec, e_vec, cfg, normal))
                        and mode_power(k_vec, e_vec, cfg, normal) > 1.0e-12)
                    power[row, side_index * len(orders_m) + order_index, component] = bool(carried)
    return {"power_carrying": power, "dispersion_propagating": dispersion}


def analytic_power_mask(points: np.ndarray, *, m_values=range(-7, 4),
                        wavelength_nm: float = 13.5,
                        period_x_nm: float = 50.0,
                        period_y_nm: float = 25.0) -> np.ndarray:
    """Compatibility wrapper returning the runtime power-carrying identity."""
    del wavelength_nm, period_x_nm, period_y_nm
    return power_mask_authority(points, m_values=m_values)["power_carrying"]


def reconstruct_aggregates(latent: np.ndarray) -> np.ndarray:
    """Recover R/T/A from ``(zR,zT)`` via softmax ``(zR,zT,0)``."""

    values = np.asarray(latent, dtype=np.float64)
    if values.ndim != 2 or values.shape[1] not in (2, 3):
        raise ValueError("aggregate reconstruction expects two log-ratio latents")
    logits = np.column_stack((values[:, :2], np.zeros(len(values), dtype=np.float64)))
    logits -= np.max(logits, axis=1, keepdims=True)
    weights = np.exp(logits)
    weights /= np.sum(weights, axis=1, keepdims=True)
    return np.column_stack((weights, weights[:, 2]))


def reconstruct_powers(raw: np.ndarray, mask: np.ndarray, aggregates: np.ndarray,
                       *, sidewise_renormalize: bool = True) -> np.ndarray:
    """Apply non-negativity, analytic nulls, and optional side ledgers."""

    values = np.maximum(np.asarray(raw, dtype=np.float64), 0.0)
    active = np.asarray(mask, dtype=bool)
    if values.shape != active.shape:
        raise ValueError("power/mask shapes disagree")
    output = np.full(values.shape, np.nan, dtype=np.float64)
    output[active] = values[active]
    if not sidewise_renormalize:
        return output
    aggregates = np.asarray(aggregates, dtype=np.float64)
    for side, sl in ((0, slice(0, 11)), (1, slice(11, 22))):
        carrying = active[:, sl, :]
        current = np.nansum(np.where(carrying, output[:, sl, :], 0.0), axis=(1, 2))
        desired = aggregates[:, side]
        scale = np.divide(desired, current, out=np.ones_like(desired), where=current > 0.0)
        block = output[:, sl, :]
        block[carrying] *= np.repeat(scale, block.shape[1] * block.shape[2])[carrying.ravel()]
        output[:, sl, :] = block
    return output


def physics_audit(aggregates: np.ndarray, powers: np.ndarray,
                  mask: np.ndarray) -> dict[str, float | int]:
    output = np.asarray(powers)
    active = np.asarray(mask, dtype=bool)
    inactive_nonnull = int(np.count_nonzero(~active & np.isfinite(output)))
    negative = int(np.count_nonzero(output[active] < 0.0))
    r_ledger = np.nansum(np.where(active[:, :11, :], output[:, :11, :], 0.0), axis=(1, 2))
    t_ledger = np.nansum(np.where(active[:, 11:, :], output[:, 11:, :], 0.0), axis=(1, 2))
    return {
        "negative_power_count": negative,
        "inactive_channel_nonnull_count": inactive_nonnull,
        "max_reflection_ledger_error": float(np.max(np.abs(r_ledger - aggregates[:, 0]))),
        "max_transmission_ledger_error": float(np.max(np.abs(t_ledger - aggregates[:, 1]))),
    }
