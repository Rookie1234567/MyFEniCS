"""Tests for the Task035b strict cross-mesh same-error audit."""

from __future__ import annotations

import math
from pathlib import Path
import tempfile

import numpy as np
import pyvista as pv
import pytest

from benchmarks.run_task035_actual_r5 import (
    _compact_solve,
    _parse_args,
    _select_qualifier,
)
from src.adaptivity.high_order_same_error import (
    ProbeSet,
    build_task034_fixed_probe_sets,
    compare_diffraction_channels,
    compare_observables,
    sample_owned_vtu_shards,
)
from src.adaptivity.target_fixed_trace_candidate import (
    _execution_integrity_pass,
    _same_mesh_identity,
    _same_mesh_resource_comparison,
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


def test_fixed_trace_watchdog_cli_is_narrow_and_sha_bound() -> None:
    sha = "a" * 64
    args = _parse_args(
        [
            "--coarse-degree",
            "5",
            "--enriched-degree",
            "6",
            "--h-nm",
            "15",
            "--mesh-cell-type",
            "hexahedron",
            "--mpi-size",
            "8",
            "--fixed-trace-control-record",
            "control.json",
            "--fixed-trace-control-sha256",
            sha,
            "--fixed-trace-global-p6-baseline-record",
            "h15.json",
            "--fixed-trace-global-p6-baseline-sha256",
            sha,
            "--fixed-trace-degree",
            "5",
            "--fixed-interior-degree",
            "6",
        ]
    )
    assert args.fixed_trace_control_sha256 == sha
    assert args.fixed_trace_degree == 5
    assert args.fixed_interior_degree == 6
    assert args.fixed_trace_global_p6_baseline_sha256 == sha
    assert _select_qualifier(args).__name__ == "_qualify_fixed_trace"
    with pytest.raises(SystemExit):
        _parse_args(
            [
                "--coarse-degree",
                "5",
                "--enriched-degree",
                "6",
                "--h-nm",
                "15",
                "--fixed-trace-control-record",
                "control.json",
            ]
        )


def test_fixed_trace_resolved_degrees_come_from_persisted_config() -> None:
    summary = {
        "official_result": True,
        "mesh_cell_type_actual": "hexahedron",
        "nedelec_trace_degree_resolved": 4,
        "nedelec_interior_degree_resolved": 5,
        "config": {
            "nedelec_trace_degree_resolved": 5,
            "nedelec_interior_degree_resolved": 6,
        },
        "cell_static_condensation": {
            "full_global_matrix_allocated": False,
            "full_trace_matrix_allocated": False,
            "full_explicit_true_residual": {
                "linear_system_relative_residual": 1.0e-12,
            },
        },
    }
    resource_audit = {"entity_dof_inventory": {"pass": True}}
    assert _execution_integrity_pass(
        summary,
        resource_audit,
        trace_degree=5,
        interior_degree=6,
    )
    compact = _compact_solve(
        {
            "degree": 6,
            "h_nm": 15.0,
            "summary": summary,
        }
    )
    assert compact["nedelec_trace_degree_resolved"] == 5
    assert compact["nedelec_interior_degree_resolved"] == 6
    summary["config"] = {}
    assert not _execution_integrity_pass(
        summary,
        resource_audit,
        trace_degree=5,
        interior_degree=6,
    )


def test_fixed_trace_same_mesh_resource_baseline_is_explicit() -> None:
    mesh_identity = {
        "partition_independent_mesh_sha256": "mesh",
        "cell_tag_sha256": "cell-tags",
        "facet_tag_sha256": "facet-tags",
    }
    candidate_audit = {"mesh_identity": dict(mesh_identity)}
    baseline = {
        "num_nedelec_dofs": 84492,
        "matrix_stats": {
            "matrix_rows": 24704,
            "matrix_nnz_used": 19207136.0,
        },
        "stage4_dtn_factor_inventory": {
            "matrix_stats": {"matrix_nnz_used": 59616320.0},
        },
        "high_order_resource_audit": {
            "mesh_identity": dict(mesh_identity),
        },
    }
    summary = {
        "num_nedelec_dofs": 74890,
        "matrix_stats": {
            "matrix_rows": 16880,
            "matrix_nnz_used": 9195812.0,
        },
        "stage4_dtn_factor_inventory": {
            "matrix_stats": {"matrix_nnz_used": 30000000.0},
        },
    }
    identity = _same_mesh_identity(candidate_audit, baseline)
    assert identity["pass"] is True
    comparison = _same_mesh_resource_comparison(summary, baseline)
    dofs = comparison["metrics"]["full3d_equivalent_dofs"]
    assert dofs["global_p6"] == 84492
    assert dofs["candidate"] == 74890
    assert dofs["compression_ratio"] == pytest.approx(84492 / 74890)
    candidate_audit["mesh_identity"]["facet_tag_sha256"] = "wrong"
    assert _same_mesh_identity(candidate_audit, baseline)["pass"] is False
