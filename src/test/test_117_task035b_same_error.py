"""Tests for the Task035b strict cross-mesh same-error audit."""

from __future__ import annotations

import math
from pathlib import Path
import tempfile

import numpy as np
import pyvista as pv

from src.adaptivity.high_order_same_error import (
    ProbeSet,
    build_task034_fixed_probe_sets,
    compare_diffraction_channels,
    compare_observables,
    sample_owned_vtu_shards,
)


def test_fixed_probe_contract_is_frozen_and_avoids_interfaces() -> None:
    probes = build_task034_fixed_probe_sets()
    volume = probes["volume"]
    interface = probes["interface"]
    assert len(volume.points) == 416
    assert len(interface.points) == 320
    assert math.isclose(float(volume.weights.sum()), 175000.0, rel_tol=1e-14)
    assert math.isclose(float(interface.weights.sum()), 15350.0, rel_tol=1e-14)
    assert (
        volume.sha256
        == "02f1e8e4275319164f04fcb19aaa2deebe95452c286a43535db196ac267f1820"
    )
    assert (
        interface.sha256
        == "ceb8e25d1684aa04ea647a582c833afffe1a1001e0513b3986a0f197087e2c35"
    )
    x, _, z = interface.points.T
    assert not np.any(np.isclose(z, 0.0, rtol=0.0, atol=1e-12))
    assert not np.any(np.isclose(z, 120.0, rtol=0.0, atol=1e-12))
    assert not np.any(np.isclose(x, 16.5, rtol=0.0, atol=1e-12))
    assert not np.any(np.isclose(x, 33.5, rtol=0.0, atol=1e-12))


def test_observable_gate_keeps_strict_r00_and_normalized_vector() -> None:
    p5 = {
        "R00_total": 0.0010,
        "R_total": 0.0011,
        "T_total": 0.60,
    }
    p6 = {
        "R00_total": 0.0009,
        "R_total": 0.0010,
        "T_total": 0.61,
    }
    candidate = {
        "R00_total": 0.00095,
        "R_total": 0.00105,
        "T_total": 0.605,
    }
    passing = compare_observables(candidate, p5, p6)
    assert passing["pass"] is True
    failed_candidate = dict(candidate, R00_total=0.0011)
    failed = compare_observables(failed_candidate, p5, p6)
    assert failed["observables"]["R00_total"]["pass"] is False
    assert failed["pass"] is False


def _channel(*, power: float, amplitude: float) -> dict:
    return {
        "side": "top",
        "m": 0,
        "n": 0,
        "polarization": "s",
        "direction": "outgoing_up",
        "medium": "air",
        "order_m": 0,
        "order_n": 0,
        "alpha": [0.0, 0.0],
        "gamma": [0.0, 0.0],
        "beta": [1.0, 0.0],
        "kz": [1.0, 0.0],
        "vertical_sign": 1,
        "propagating": True,
        "power_carrying": True,
        "rayleigh_warning": False,
        "refractive_index": [1.0, 0.0],
        "boundary_phase": [1.0, 0.0],
        "power_ratio": power,
        "outgoing_amplitude_at_boundary": [amplitude, 0.0],
    }


def test_significant_channel_gate_does_not_hide_amplitude_regression() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        paths = [root / name for name in ("p5.json", "p6.json", "candidate.json")]
        payloads = (
            {"orders": [_channel(power=0.1, amplitude=0.3)]},
            {"orders": [_channel(power=0.11, amplitude=0.31)]},
            {"orders": [_channel(power=0.115, amplitude=0.34)]},
        )
        import json

        for path, payload in zip(paths, payloads, strict=True):
            path.write_text(json.dumps(payload), encoding="utf-8")
        comparison = compare_diffraction_channels(
            global_p5_path=paths[0],
            global_p6_path=paths[1],
            candidate_p6_path=paths[2],
        )
        assert comparison["significant_order_power_gate_pass"] is True
        assert comparison["significant_complex_amplitude_gate_pass"] is False
        assert comparison["pass"] is False


def test_shard_sampler_fails_closed_on_missing_or_duplicate_ownership(
    monkeypatch,
) -> None:
    probe = ProbeSet(
        name="fixture",
        points=np.asarray([[0.25, 0.25, 0.25]], dtype=float),
        weights=np.asarray([1.0]),
        region_labels=("fixture",),
        definition={},
        sha256="fixture",
    )
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        paths = [
            root / f"fields_3d_for_paraview_rank{rank:04d}.vtu"
            for rank in range(8)
        ]
        # Use a small fake reader so the test isolates fail-closed ownership
        # semantics from VTK's high-order cell writer.
        class Grid:
            celltypes = np.asarray([72])
            n_cells = 1
            n_points = 8

        class Sample:
            def __init__(self, valid: bool):
                self.point_data = {
                    "vtkValidPointMask": np.asarray([int(valid)]),
                    "E_tot_V_per_m_real": np.zeros((1, 3)),
                    "E_tot_V_per_m_imag": np.zeros((1, 3)),
                }

        for path in paths:
            path.write_bytes(b"fixture")
        monkeypatch.setattr(pv, "read", lambda _path: Grid())
        monkeypatch.setattr(
            pv.PolyData,
            "sample",
            lambda self, grid, **kwargs: Sample(False),
        )
        try:
            sample_owned_vtu_shards(paths, probe)
        except ValueError as error:
            assert "unique MPI-shard ownership" in str(error)
        else:
            raise AssertionError("zero-hit probe was not rejected")
        monkeypatch.setattr(
            pv.PolyData,
            "sample",
            lambda self, grid, **kwargs: Sample(True),
        )
        try:
            sample_owned_vtu_shards(paths, probe)
        except ValueError as error:
            assert "unique MPI-shard ownership" in str(error)
        else:
            raise AssertionError("multi-hit probe was not rejected")
