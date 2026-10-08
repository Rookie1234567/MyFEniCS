"""Generic two-cell p6 Bloch-orbit maps for the isolated Task40 Ny=8 probe.

The production V10/V15/V16 four-cell path is intentionally untouched. This
module owns only the algebra for a complete native entity map with Ny = K*ell,
where a two-cell local window is repeated K times around the physical period.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

import numpy as np

MAPPING_LIMIT = 1e-12


def _field(value: Any, name: str) -> Any:
    return value.get(name) if isinstance(value, Mapping) else getattr(value, name)


def _complex(value: Any) -> complex:
    if isinstance(value, Mapping) and set(value) >= {"real", "imag"}:
        return complex(value["real"], value["imag"])
    return complex(value)


def _norm(value: np.ndarray) -> float:
    magnitude = np.abs(np.asarray(value))
    return float(np.sqrt(np.sum(magnitude * magnitude, dtype=np.longdouble)))


def _relative(actual: np.ndarray, expected: np.ndarray) -> float:
    denominator = _norm(expected)
    if denominator == 0.0:
        error = _norm(np.asarray(actual) - np.asarray(expected))
        return 0.0 if error == 0.0 else float("inf")
    return _norm(np.asarray(actual) - np.asarray(expected)) / denominator


@dataclass(frozen=True)
class NyOrbitSector:
    twist_index: int
    eta: complex
    tau: complex
    global_q_indices: tuple[int, ...]
    original_mode_indices: np.ndarray
    local_branch_indices: np.ndarray
    q_counts: tuple[int, ...]

    def audit(self) -> dict[str, Any]:
        return {
            "twist_index": self.twist_index,
            "eta": [self.eta.real, self.eta.imag],
            "tau": [self.tau.real, self.tau.imag],
            "global_q_indices": list(self.global_q_indices),
            "mode_count": int(len(self.original_mode_indices)),
            "local_branch_counts": list(self.q_counts),
            "global_q_coverage": "one mode assignment per frozen ordered key",
        }


def assign_ny_orbit_sectors(
    modes: Sequence[Any],
    *,
    ky: complex,
    period_y: float,
    cell_width_y: float,
    global_y_cells: int,
    local_y_cells: int = 2,
    tolerance: float = MAPPING_LIMIT,
) -> tuple[NyOrbitSector, ...]:
    """Assign each actual mode to exactly one Ny Bloch q and its two-cell twist.

    For ``Ny=K*ell``, twist b owns q=b+j*K for j=0,...,ell-1. The mode is
    classified from its actual transverse propagation constant, not from a
    hand-built q label. This keeps the returned inventory bound to the frozen
    physical mode records.
    """
    ny, ell = int(global_y_cells), int(local_y_cells)
    if ny < 1 or ell < 1 or ny % ell:
        raise ValueError("global Ny must be a positive multiple of the local window cell count")
    if not np.isfinite(period_y) or period_y <= 0 or not np.isfinite(cell_width_y) or cell_width_y <= 0:
        raise ValueError("period and y-cell width must be finite and positive")
    if abs(ny * cell_width_y - period_y) > tolerance * max(period_y, 1.0):
        raise ValueError("actual Ny cell width does not close the physical y period")
    if not np.isfinite(ky) or abs(complex(ky).imag) > tolerance:
        raise ValueError("the orbit mapper requires a real Bloch ky")
    if not modes:
        raise ValueError("the frozen physical mode inventory must be nonempty")
    K = ny // ell
    theta = complex(ky).real * float(period_y)
    eta = np.asarray(
        [np.exp(1j * (theta + 2.0 * np.pi * b) / ny) for b in range(K)],
        dtype=np.complex128,
    )
    expected_q = np.asarray(
        [np.exp(1j * (theta + 2.0 * np.pi * q) / ny) for q in range(ny)],
        dtype=np.complex128,
    )
    assigned = np.empty(len(modes), dtype=np.int64)
    for index, mode in enumerate(modes):
        gamma = _complex(_field(mode, "gamma"))
        actual = np.exp(1j * gamma * float(cell_width_y))
        errors = np.abs(expected_q - actual)
        q = int(np.argmin(errors))
        if not np.isfinite(actual) or abs(abs(actual) - 1.0) > tolerance or errors[q] > tolerance:
            raise ValueError(f"mode index {index} has no real-Bloch Ny q within the original mapping gate")
        assigned[index] = q
    if np.any(assigned < 0) or np.any(assigned >= ny):
        raise ValueError("a frozen mode was not assigned to a global q")

    sectors = []
    for b in range(K):
        qids = tuple(b + branch * K for branch in range(ell))
        indices = np.flatnonzero(np.isin(assigned, qids)).astype(np.int64)
        branches = ((assigned[indices] - b) // K).astype(np.int64)
        q_counts = tuple(int(np.count_nonzero(assigned[indices] == q)) for q in qids)
        if len(np.unique(indices)) != len(indices) or len(branches) != len(indices):
            raise ValueError("sector mode indices or local branch assignments are duplicated")
        tau = complex(eta[b] ** ell)
        if abs(tau**K - np.exp(1j * theta)) > tolerance:
            raise ValueError("two-cell local twist does not reproduce the global Bloch phase")
        sectors.append(NyOrbitSector(
            twist_index=b,
            eta=complex(eta[b]),
            tau=tau,
            global_q_indices=qids,
            original_mode_indices=indices,
            local_branch_indices=branches,
            q_counts=q_counts,
        ))
    covered = np.concatenate([sector.original_mode_indices for sector in sectors])
    if not np.array_equal(np.sort(covered), np.arange(len(modes), dtype=np.int64)):
        raise ValueError("twist sectors do not cover every ordered physical mode exactly once")
    if len(np.unique(covered)) != len(modes):
        raise ValueError("twist sectors assign an ordered physical mode more than once")
    return tuple(sectors)


class TwoCellNyOrbitTransport:
    """Native primal/dual fold and lift for any complete Ny=K*2 entity maps."""

    def __init__(
        self,
        full: Any,
        local: Any,
        *,
        twist_index: int,
        eta: complex,
        cfg: Any,
        local_y_cells: int = 2,
    ) -> None:
        ell = int(local_y_cells)
        if ell != local.ny or full.ny < ell or full.ny % ell:
            raise ValueError("complete full/local entity maps must satisfy Ny=K*ell")
        K = full.ny // ell
        if type(twist_index) is not int or not 0 <= twist_index < K:
            raise ValueError("twist index must be one of the K actual translation sectors")
        required_dims = (1, 2, 3)
        if (
            full.width != local.width
            or len(full.independent) != full.ny * full.width
            or len(local.independent) != local.ny * local.width
            or full.bases != local.bases
            or full.slots != local.slots
            or any(full.dimension_counts.get(d, 0) <= 0 for d in required_dims)
            or any(local.dimension_counts.get(d, 0) <= 0 for d in required_dims)
            or len(full.records) != full.ny * len(full.bases)
            or len(local.records) != local.ny * len(local.bases)
        ):
            raise ValueError("complete full/local native interior-edge-face inventories do not match")
        widths = np.asarray(full.y_widths, dtype=np.float64)
        local_widths = np.asarray(local.y_widths, dtype=np.float64)
        expected_widths = np.tile(local_widths, K)
        if (
            widths.shape != (full.ny,)
            or local_widths.shape != (ell,)
            or not np.isfinite(widths).all()
            or not np.isfinite(local_widths).all()
            or np.any(widths <= 0.0)
            or np.any(local_widths <= 0.0)
        ):
            raise ValueError("the physical y mesh widths must be finite positive full/local vectors")
        width_relative_difference = np.abs(widths - expected_widths) / np.maximum(
            np.abs(expected_widths), np.finfo(np.float64).tiny
        )
        width_max_relative_metric_difference = float(
            np.max(width_relative_difference, initial=0.0)
        )
        if width_max_relative_metric_difference > MAPPING_LIMIT:
            raise ValueError("the physical y mesh is not a translated repetition within the mapping gate")
        widths_bitwise_equal = bool(np.array_equal(widths, expected_widths))
        if type(twist_index) is not int:
            raise ValueError("twist index must be an integer")
        self.full, self.local = full, local
        self.b, self.K, self.ell, self.ny = twist_index, K, ell, full.ny
        self.eta = complex(eta)
        self.tau = self.eta**ell
        theta = complex(cfg.ky).real * float(cfg.period_y)
        expected_eta = np.exp(1j * (theta + 2.0 * np.pi * self.b) / self.ny)
        phase = complex(cfg.floquet_phase_y)
        if (
            abs(complex(cfg.ky).imag) > MAPPING_LIMIT
            or abs(self.eta - expected_eta) > MAPPING_LIMIT
            or abs(self.tau**self.K - phase) > MAPPING_LIMIT
            or abs(abs(self.eta) - 1.0) > MAPPING_LIMIT
        ):
            raise ValueError("Ny twist does not preserve the actual unit-modulus global Bloch phase")
        self.audit = {
            "global_y_cells": self.ny,
            "local_y_cells": self.ell,
            "translation_count_K": self.K,
            "twist_index": self.b,
            "global_q_branches": [self.b + j * self.K for j in range(self.ell)],
            "eta": [self.eta.real, self.eta.imag],
            "tau": [self.tau.real, self.tau.imag],
            "full_native_dimension": int(len(full.independent)),
            "local_native_dimension": int(len(local.independent)),
            "interior_edge_face_maps_complete": True,
            "uniform_translated_y_cells_exact": widths_bitwise_equal,
            "uniform_translated_y_cells_mapping_gate_passed": True,
            "y_widths_bitwise_equal": widths_bitwise_equal,
            "y_widths_max_relative_metric_difference": width_max_relative_metric_difference,
            "mapping_limit": MAPPING_LIMIT,
            "fourier_normalization": "1/sqrt(K)",
        }

    def _values(self, values: Any, length: int, label: str) -> np.ndarray:
        array = np.asarray(values, dtype=np.complex128)
        if (
            array.ndim not in (1, 2)
            or array.shape[0] != length
            or (array.ndim == 2 and array.shape[1] > 32)
            or not np.isfinite(array).all()
        ):
            raise ValueError(f"{label} must be a finite native vector or panel with at most 32 columns")
        return array

    def _fold_canonical(self, values: np.ndarray, *, dual: bool) -> np.ndarray:
        array = self._values(values, len(self.full.independent), "full canonical input")
        tail = array.shape[1:]
        panels = array.reshape((self.ny, self.full.width) + tail)
        result = np.zeros((self.ell, self.local.width) + tail, dtype=np.complex128)
        phase = np.conjugate(self.tau) if dual else self.tau
        for copy in range(self.K):
            for cell in range(self.ell):
                result[cell] += phase**copy * panels[copy * self.ell + cell]
        result /= np.sqrt(float(self.K))
        return result.reshape((len(self.local.independent),) + tail)

    def _lift_canonical(self, values: np.ndarray) -> np.ndarray:
        array = self._values(values, len(self.local.independent), "local canonical input")
        tail = array.shape[1:]
        panels = array.reshape((self.ell, self.local.width) + tail)
        result = np.empty((self.ny, self.full.width) + tail, dtype=np.complex128)
        scale = np.sqrt(float(self.K))
        for copy in range(self.K):
            result[copy * self.ell : (copy + 1) * self.ell] = (
                self.tau**copy * panels / scale
            )
        return result.reshape((len(self.full.independent),) + tail)

    def fold_dual(self, full_native: Any) -> np.ndarray:
        canonical = self.full.transform(full_native, direction="dual_to_canonical")
        folded = self._fold_canonical(canonical, dual=True)
        return self.local.transform(folded, direction="dual_from_canonical")

    def lift_primal(self, local_native: Any) -> np.ndarray:
        canonical = self.local.transform(local_native, direction="primal_to_canonical")
        lifted = self._lift_canonical(canonical)
        return self.full.transform(lifted, direction="primal_from_canonical")

    def extract_primal(self, full_native: Any) -> np.ndarray:
        canonical = self.full.transform(full_native, direction="primal_to_canonical")
        folded = self._fold_canonical(canonical, dual=True)
        return self.local.transform(folded, direction="primal_from_canonical")

    def lift_dual(self, local_native: Any) -> np.ndarray:
        canonical = self.local.transform(local_native, direction="dual_to_canonical")
        lifted = self._lift_canonical(canonical)
        return self.full.transform(lifted, direction="dual_from_canonical")


def audit_ny_port_scaling(
    *,
    global_h: Any,
    local_h: Any,
    global_alpha: Any,
    local_alpha: Any,
    global_normalized_rhs: Any,
    local_normalized_rhs: Any,
    global_raw_rhs: Any,
    local_raw_rhs: Any,
    translation_count: int,
    tolerance: float = MAPPING_LIMIT,
) -> dict[str, Any]:
    """Audit H, primal, normalized-dual, raw-dual, and work scaling.

    ``normalized_rhs = raw_rhs / H`` is the RHS after division by the modal
    port normalization. Coherent primal and normalized RHS vectors therefore
    fold with ``sqrt(K)``. The raw dual RHS folds with ``1/sqrt(K)`` so the
    original primal/raw-dual pairing stays unchanged. The full-work check uses
    the equivalent H-weighted normalized pairing on each mesh.
    """
    if type(translation_count) is not int or translation_count < 1:
        raise ValueError("translation_count K must be a positive integer")
    H = np.asarray(global_h, dtype=np.float64)
    h_local = np.asarray(local_h, dtype=np.float64)
    alpha = np.asarray(global_alpha, dtype=np.complex128)
    alpha_local = np.asarray(local_alpha, dtype=np.complex128)
    rhs_normalized = np.asarray(global_normalized_rhs, dtype=np.complex128)
    rhs_normalized_local = np.asarray(local_normalized_rhs, dtype=np.complex128)
    rhs_raw = np.asarray(global_raw_rhs, dtype=np.complex128)
    rhs_raw_local = np.asarray(local_raw_rhs, dtype=np.complex128)
    vectors = (H, h_local, alpha, alpha_local, rhs_normalized,
               rhs_normalized_local, rhs_raw, rhs_raw_local)
    if (
        H.ndim != 1
        or any(x.shape != H.shape for x in vectors)
        or not all(np.isfinite(x).all() for x in vectors)
        or np.any(H <= 0)
        or np.any(h_local <= 0)
    ):
        raise ValueError("global/local H, alpha and normalized/raw RHS must be matching finite modal vectors")
    scale = np.sqrt(float(translation_count))
    expected_H = H / float(translation_count)
    expected_alpha = scale * alpha
    expected_rhs_normalized = scale * rhs_normalized
    expected_rhs_raw = rhs_raw / scale
    h_error = _relative(h_local, expected_H)
    alpha_error = _relative(alpha_local, expected_alpha)
    normalized_rhs_error = _relative(rhs_normalized_local, expected_rhs_normalized)
    raw_rhs_error = _relative(rhs_raw_local, expected_rhs_raw)
    global_normalization_error = _relative(rhs_raw, H * rhs_normalized)
    local_normalization_error = _relative(rhs_raw_local, h_local * rhs_normalized_local)
    global_power = H * np.abs(alpha) ** 2
    local_power = h_local * np.abs(alpha_local) ** 2
    global_work = np.vdot(alpha, H * rhs_normalized)
    local_work = np.vdot(alpha_local, h_local * rhs_normalized_local)
    global_raw_work = np.vdot(alpha, rhs_raw)
    local_raw_work = np.vdot(alpha_local, rhs_raw_local)
    work_denominator = max(abs(global_work), abs(global_raw_work), np.finfo(float).tiny)
    power_error = _relative(local_power, global_power)
    weighted_work_error = abs(local_work - global_work) / work_denominator
    global_raw_consistency_error = abs(global_raw_work - global_work) / work_denominator
    local_raw_consistency_error = abs(local_raw_work - local_work) / work_denominator
    passed = bool(max(
        h_error, alpha_error, normalized_rhs_error, raw_rhs_error,
        global_normalization_error, local_normalization_error, power_error,
        float(weighted_work_error), float(global_raw_consistency_error),
        float(local_raw_consistency_error),
    ) <= tolerance)
    return {
        "translation_count_K": translation_count,
        "H_identity": "H_local = H_global / K",
        "alpha_identity": "alpha_local = sqrt(K) * alpha_global in the same gauge",
        "normalized_rhs_definition": "normalized_rhs = raw_dual_rhs / H",
        "normalized_rhs_identity": "normalized_rhs_local = sqrt(K) * normalized_rhs_global",
        "raw_dual_rhs_identity": "raw_dual_rhs_local = raw_dual_rhs_global / sqrt(K)",
        "global_normalized_to_raw_consistency_relative_error": global_normalization_error,
        "local_normalized_to_raw_consistency_relative_error": local_normalization_error,
        "H_relative_error": h_error,
        "alpha_relative_error": alpha_error,
        "normalized_rhs_relative_error": normalized_rhs_error,
        "raw_dual_rhs_relative_error": raw_rhs_error,
        "power_relative_error_H_abs_alpha_squared": power_error,
        "global_H_weighted_work": [float(global_work.real), float(global_work.imag)],
        "local_H_weighted_work": [float(local_work.real), float(local_work.imag)],
        "global_raw_dual_work": [float(global_raw_work.real), float(global_raw_work.imag)],
        "local_raw_dual_work": [float(local_raw_work.real), float(local_raw_work.imag)],
        "H_weighted_primal_dual_work_relative_error": float(weighted_work_error),
        "global_raw_vs_H_weighted_work_relative_error": float(global_raw_consistency_error),
        "local_raw_vs_H_weighted_work_relative_error": float(local_raw_consistency_error),
        "tolerance": tolerance,
        "passed": passed,
    }
