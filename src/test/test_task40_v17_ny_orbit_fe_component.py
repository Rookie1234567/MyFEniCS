from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers.task40_v17_ny_orbit_fe_component import (
    build_native_ny8_orbit_component,
    combine_native_regular_actions,
)


class _NativeMap:
    def __init__(self, ny: int, bank: object) -> None:
        self.ny = ny
        self.width = 3
        self.full_rows = ny * self.width
        self.independent = np.arange(self.full_rows, dtype=np.int64)
        self.bases = ((1, "edge"), (2, "face"), (3, "interior"))
        self.slots = {base: (index, 1) for index, base in enumerate(self.bases)}
        self.dimension_counts = {1: ny, 2: ny, 3: ny}
        self.y_widths = np.full(ny, 1.0, dtype=np.float64)
        self.records = {}
        for orbit in range(ny):
            for index, base in enumerate(self.bases):
                self.records[(orbit, base)] = (
                    np.asarray([orbit * self.width + index], dtype=np.int64),
                    np.ones((1, 1), dtype=np.complex128),
                )
        self._transform_bank = bank

    def transform(self, values, *, direction):
        del direction
        return np.asarray(values, dtype=np.complex128).copy()


def _case_inputs(monkeypatch, *, length=8.0, shifted_local_twist=None, shifted_local_y=None):
    import src.solvers.task40_v10_p6_yorbit as legacy

    bank = object()
    full_map = _NativeMap(8, bank)
    local_map = _NativeMap(2, bank)
    calls = []

    def collect(space, floquet, cfg, axes, *, transform_bank):
        calls.append((space, floquet, cfg, axes, transform_bank))
        result = full_map if space == "global-space" else local_map
        result.y_widths = np.diff(np.asarray(axes["y"], dtype=np.float64))
        return result

    monkeypatch.setattr(legacy, "collect_y_orbit_entities", collect)
    theta = 0.37 * length
    cfg = SimpleNamespace(
        ky=0.37 + 0j,
        period_y=length,
        floquet_phase_y=np.exp(1j * theta),
    )
    full_axes = {
        "x": (0.0, 1.0),
        "y": tuple(np.linspace(0.0, length, 9)),
        "z": (0.0, 1.0),
    }
    local_axes = {
        "x": full_axes["x"],
        "y": full_axes["y"][:3],
        "z": full_axes["z"],
    }
    modes = []
    for q in range(8):
        gamma = cfg.ky.real + 2 * np.pi * q / cfg.period_y
        modes.extend([
            {"gamma": gamma, "side": "top", "m": q, "n": 0, "polarization": "s"},
            {"gamma": gamma, "side": "bottom", "m": q, "n": 0, "polarization": "p"},
        ])
    full_setup = {"spaces": {6: "global-space"}, "floquets": {6: "global-mpc"}}
    local_cases = []
    for twist in range(4):
        qids = (twist, twist + 4)
        indices = [i for i, mode in enumerate(modes) if mode["m"] in qids]
        tau = np.exp(1j * (theta + 2 * np.pi * twist) / 4)
        local_y = np.asarray(local_axes["y"], dtype=np.float64)
        if shifted_local_y == twist:
            local_y = local_y + 1e-5
        local_cases.append({
            "setup": {"spaces": {6: f"local-space-{twist}"}, "floquets": {6: f"local-mpc-{twist}"}},
            "cfg": SimpleNamespace(floquet_phase_y=tau * np.exp(1e-4j) if shifted_local_twist == twist else tau),
            "axes": {**local_axes, "y": tuple(local_y)},
            "global_mode_indices": indices,
            "modes": tuple(modes[i] for i in indices),
        })
    component = build_native_ny8_orbit_component(
        full_setup=full_setup,
        local_cases=local_cases,
        cfg=cfg,
        full_axes=full_axes,
        modes=modes,
        transform_bank=bank,
    )
    return component, calls, bank


def test_native_ny8_adapter_collects_all_four_twists_and_mode_keys(monkeypatch):
    component, calls, bank = _case_inputs(monkeypatch)
    audit = component.audit()
    assert len(calls) == 5
    assert all(row[-1] is bank for row in calls)
    assert audit["global_y_cells_Ny"] == 8
    assert audit["local_y_cells_ell"] == 2
    assert audit["translation_count_K"] == 4
    assert audit["global_q_coverage"] == list(range(8))
    assert audit["global_q_counts"] == [2] * 8
    assert audit["all_ordered_modes_covered_once"] is True
    assert [sector.context.global_q_indices for sector in component.sectors] == [
        (0, 4), (1, 5), (2, 6), (3, 7)
    ]
    assert all(
        sector.audit()["geometry_audit"]["first_window_y_coordinates"]["bitwise_equal"]
        for sector in component.sectors
    )


def test_native_ny8_accepts_float_mesh_roundoff_and_rejects_shift_or_wrong_phase(monkeypatch):
    component, _calls, _bank = _case_inputs(monkeypatch, length=25 * 7 / 135)
    audit = component.audit()
    assert audit["geometry_audit"]["global_y_widths_bitwise_equal_to_first_width"] is False
    assert audit["geometry_audit"]["global_y_widths_max_relative_metric_difference"] <= 1e-12
    assert all(
        sector.audit()["geometry_audit"]["first_window_y_coordinates"]["maximum_relative_metric_difference"] <= 1e-12
        for sector in component.sectors
    )

    with pytest.raises(ValueError, match="actual first two-cell"):
        _case_inputs(monkeypatch, shifted_local_y=2)
    with pytest.raises(ValueError, match="Floquet y phase"):
        _case_inputs(monkeypatch, shifted_local_twist=2)


def test_native_ny8_combined_matrix_free_action_closes_and_rejects_wrong_local_action(monkeypatch):
    component, _calls, _bank = _case_inputs(monkeypatch)
    rng = np.random.default_rng(20261008)
    vector = np.asarray(rng.normal(size=24) + 1j * rng.normal(size=24), dtype=np.complex128)
    identity = lambda values: np.asarray(values, dtype=np.complex128).copy()
    passed = combine_native_regular_actions(
        component,
        full_action=identity,
        local_actions=[identity] * 4,
        full_vectors=[vector],
    )
    assert passed["status"] == "PASS"
    assert passed["probe_records"][0]["relative_defect"] < 1e-13

    wrong = combine_native_regular_actions(
        component,
        full_action=identity,
        local_actions=[lambda values: 1.001 * values] * 4,
        full_vectors=[vector],
    )
    assert wrong["status"] == "FAIL"
    assert wrong["probe_records"][0]["relative_defect"] > 1e-4

    scaled = combine_native_regular_actions(
        component,
        full_action=identity,
        local_actions=[lambda values: 1.6 * values] * 4,
        full_vectors=[vector],
        tolerance=0.4,
    )
    assert scaled["status"] == "FAIL"
    assert scaled["probe_records"][0]["relative_defect_denominator"] == "full_action_norm"
    assert scaled["probe_records"][0]["relative_defect"] > 0.4

    zero_oracle = combine_native_regular_actions(
        component,
        full_action=lambda values: np.zeros_like(values),
        local_actions=[identity] * 4,
        full_vectors=[vector],
    )
    assert zero_oracle["status"] == "FAIL"
    assert zero_oracle["probe_records"][0]["full_action_norm_is_zero_oracle"] is True
    assert zero_oracle["probe_records"][0]["relative_defect"] is None
