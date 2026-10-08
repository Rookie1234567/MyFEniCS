from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers.task40_v17_ny_orbit import (
    TwoCellNyOrbitTransport,
    assign_ny_orbit_sectors,
    audit_ny_port_scaling,
)


class _ToyEntities:
    def __init__(self, ny: int, *, full_rows: int | None = None) -> None:
        self.ny = ny
        self.width = 4
        self.full_rows = full_rows or ny * self.width
        self.independent = np.arange(ny * self.width, dtype=np.int64)
        self.bases = ((1, "edge"), (2, "face"), (3, "interior"))
        self.slots = {self.bases[0]: (0, 2), self.bases[1]: (2, 1), self.bases[2]: (3, 1)}
        self.dimension_counts = {1: 2 * ny, 2: ny, 3: ny}
        self.y_widths = np.full(ny, 3.125, dtype=np.float64)
        self.records = {}
        edge_transform = np.asarray(
            [[2.0 + 0.1j, 0.35 - 0.2j], [0.15 + 0.05j, 1.3 - 0.1j]],
            dtype=np.complex128,
        )
        for orbit in range(ny):
            base_rows = {
                self.bases[0]: np.asarray([4 * orbit, 4 * orbit + 1], dtype=np.int64),
                self.bases[1]: np.asarray([4 * orbit + 2], dtype=np.int64),
                self.bases[2]: np.asarray([4 * orbit + 3], dtype=np.int64),
            }
            for base, rows in base_rows.items():
                matrix = edge_transform if base == self.bases[0] else np.asarray([[1]], dtype=np.complex128)
                self.records[(orbit, base)] = (rows, matrix)

    def transform(self, values, *, direction):
        array = np.asarray(values, dtype=np.complex128)
        if array.shape[0] != len(self.independent):
            raise ValueError("wrong toy vector size")
        result = np.empty_like(array)
        for orbit in range(self.ny):
            for base in self.bases:
                rows, matrix = self.records[(orbit, base)]
                first, size = self.slots[base]
                canonical = slice(orbit * self.width + first, orbit * self.width + first + size)
                if direction in ("primal_to_canonical", "dual_from_canonical", "functional_from_canonical"):
                    used = np.linalg.inv(matrix)
                else:
                    used = matrix
                if direction == "primal_to_canonical":
                    result[canonical] = used @ array[rows]
                elif direction == "primal_from_canonical":
                    result[rows] = used @ array[canonical]
                elif direction == "dual_to_canonical":
                    result[canonical] = used.conj().T @ array[rows]
                elif direction == "dual_from_canonical":
                    result[rows] = used.conj().T @ array[canonical]
                elif direction == "functional_to_canonical":
                    result[canonical] = used.T @ array[rows]
                elif direction == "functional_from_canonical":
                    result[rows] = used.T @ array[canonical]
                else:
                    raise ValueError("unsupported toy transform direction")
        return result


def test_ny8_two_cell_native_fold_lift_and_duality_with_nonunitary_entities():
    full, local = _ToyEntities(8), _ToyEntities(2)
    theta = 0.37 * 25.0
    cfg = SimpleNamespace(ky=0.37 + 0j, period_y=25.0, floquet_phase_y=np.exp(1j * theta))
    eta = np.exp(1j * (theta + 2 * np.pi) / 8)
    transport = TwoCellNyOrbitTransport(full, local, twist_index=1, eta=eta, cfg=cfg)
    entity_change = full.records[(0, full.bases[0])][1]
    assert np.linalg.matrix_rank(entity_change) == 2
    assert not np.allclose(entity_change.conj().T @ entity_change, np.eye(2))
    rng = np.random.default_rng(20261008)
    local_primal = rng.normal(size=8) + 1j * rng.normal(size=8)
    full_dual = rng.normal(size=32) + 1j * rng.normal(size=32)
    local_dual = rng.normal(size=8) + 1j * rng.normal(size=8)
    full_primal = rng.normal(size=32) + 1j * rng.normal(size=32)

    folded_dual = transport.fold_dual(full_dual)
    lifted_primal = transport.lift_primal(local_primal)
    np.testing.assert_allclose(np.vdot(local_primal, folded_dual), np.vdot(lifted_primal, full_dual), rtol=0, atol=2e-13)
    np.testing.assert_allclose(transport.extract_primal(lifted_primal), local_primal, rtol=0, atol=2e-13)

    extracted_primal = transport.extract_primal(full_primal)
    lifted_dual = transport.lift_dual(local_dual)
    np.testing.assert_allclose(np.vdot(extracted_primal, local_dual), np.vdot(full_primal, lifted_dual), rtol=0, atol=2e-13)
    np.testing.assert_allclose(transport.fold_dual(lifted_dual), local_dual, rtol=0, atol=2e-13)

    twist_reconstruction = np.zeros_like(full_primal)
    for twist_index in range(4):
        twist_eta = np.exp(1j * (theta + 2 * np.pi * twist_index) / 8)
        twist = TwoCellNyOrbitTransport(
            full, local, twist_index=twist_index, eta=twist_eta, cfg=cfg
        )
        twist_reconstruction += twist.lift_primal(twist.extract_primal(full_primal))
    np.testing.assert_allclose(twist_reconstruction, full_primal, rtol=0, atol=3e-13)

    assert transport.audit["global_q_branches"] == [1, 5]
    assert transport.audit["translation_count_K"] == 4


def test_ny8_assigns_all_physical_modes_once_to_four_twists_and_eight_qs():
    ny, ell, period, ky = 8, 2, 25.0, 0.41
    modes = []
    for q in range(ny):
        gamma = ky + 2 * np.pi * q / period
        modes.extend([
            {"gamma": gamma, "side": "top", "m": q, "n": 0, "polarization": "s"},
            {"gamma": gamma, "side": "bottom", "m": q, "n": 0, "polarization": "p"},
        ])
    sectors = assign_ny_orbit_sectors(
        modes, ky=ky, period_y=period, cell_width_y=period / ny,
        global_y_cells=ny, local_y_cells=ell,
    )
    assert len(sectors) == 4
    assert [sector.global_q_indices for sector in sectors] == [(0, 4), (1, 5), (2, 6), (3, 7)]
    covered = np.concatenate([sector.original_mode_indices for sector in sectors])
    np.testing.assert_array_equal(np.sort(covered), np.arange(len(modes)))
    assert len(np.unique(covered)) == len(modes)
    assert [sum(sector.q_counts) for sector in sectors] == [4, 4, 4, 4]
    assert [sector.q_counts for sector in sectors] == [(2, 2)] * 4


def test_ny8_rejects_mode_outside_actual_bloch_q_inventory():
    with pytest.raises(ValueError, match="no real-Bloch Ny q"):
        assign_ny_orbit_sectors(
            [{"gamma": 0.1234567}], ky=0.41, period_y=25.0,
            cell_width_y=25.0 / 8, global_y_cells=8, local_y_cells=2,
        )


def test_ny8_port_H_alpha_rhs_scales_are_separate_and_work_preserving():
    K = 4
    global_h = np.asarray([2.5, 4.0, 7.5], dtype=np.float64)
    global_alpha = np.asarray([1 + 2j, -0.5j, 3 - 0.25j], dtype=np.complex128)
    global_raw_rhs = np.asarray([-2j, 1 + 0.5j, 0.2 - 1j], dtype=np.complex128)
    global_normalized_rhs = global_raw_rhs / global_h
    result = audit_ny_port_scaling(
        global_h=global_h,
        local_h=global_h / K,
        global_alpha=np.ascontiguousarray(global_alpha),
        local_alpha=np.ascontiguousarray(np.sqrt(K) * global_alpha),
        global_normalized_rhs=np.ascontiguousarray(global_normalized_rhs),
        local_normalized_rhs=np.ascontiguousarray(np.sqrt(K) * global_normalized_rhs),
        global_raw_rhs=np.ascontiguousarray(global_raw_rhs),
        local_raw_rhs=np.ascontiguousarray(global_raw_rhs / np.sqrt(K)),
        translation_count=K,
    )
    assert result["passed"] is True
    assert result["H_identity"] == "H_local = H_global / K"
    assert result["alpha_identity"] == "alpha_local = sqrt(K) * alpha_global in the same gauge"
    assert result["normalized_rhs_identity"] == "normalized_rhs_local = sqrt(K) * normalized_rhs_global"
    assert result["raw_dual_rhs_identity"] == "raw_dual_rhs_local = raw_dual_rhs_global / sqrt(K)"
    assert result["H_weighted_primal_dual_work_relative_error"] < 1e-14
    assert result["global_raw_vs_H_weighted_work_relative_error"] < 1e-14
    assert result["local_raw_vs_H_weighted_work_relative_error"] < 1e-14

    wrong = audit_ny_port_scaling(
        global_h=global_h,
        local_h=global_h / K,
        global_alpha=np.ascontiguousarray(global_alpha),
        local_alpha=np.ascontiguousarray(K * global_alpha),
        global_normalized_rhs=np.ascontiguousarray(global_normalized_rhs),
        local_normalized_rhs=np.ascontiguousarray(K * global_normalized_rhs),
        global_raw_rhs=np.ascontiguousarray(global_raw_rhs),
        local_raw_rhs=np.ascontiguousarray(K * global_raw_rhs),
        translation_count=K,
    )
    assert wrong["passed"] is False


def test_ny8_scaling_rejects_wrong_modal_shapes_and_zero_H():
    with pytest.raises(ValueError, match="matching finite modal vectors"):
        audit_ny_port_scaling(
            global_h=np.asarray([0.0]), local_h=np.asarray([0.0]),
            global_alpha=np.ones(1, dtype=np.complex128),
            local_alpha=np.ones(1, dtype=np.complex128),
            global_normalized_rhs=np.ones(1, dtype=np.complex128),
            local_normalized_rhs=np.ones(1, dtype=np.complex128),
            global_raw_rhs=np.ones(1, dtype=np.complex128),
            local_raw_rhs=np.ones(1, dtype=np.complex128), translation_count=4,
        )
