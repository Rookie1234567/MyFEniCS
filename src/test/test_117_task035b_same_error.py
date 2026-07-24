"""Tests for the Task035b strict cross-mesh same-error audit."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import tempfile

import numpy as np
import pyvista as pv
import pytest

from benchmarks.run_task035_actual_r5 import (
    _compact_solve,
    _fixed_trace_resource_preflight,
    _parse_args,
    _resolve_new_record_path,
    _select_qualifier,
)
from benchmarks.task035b_fixed_trace_port_preflight import (
    build_controlled_stop_record,
)
from src.adaptivity.high_order_same_error import (
    ProbeSet,
    build_task034_fixed_probe_sets,
    compare_diffraction_channels,
    compare_observables,
    compare_significant_channels_to_reference_v1,
    sample_owned_vtu_shards,
)
from src.adaptivity.target_fixed_trace_candidate import (
    _derived_standard_global_dofs,
    _execution_integrity_pass,
    _same_mesh_identity,
    _same_mesh_resource_comparison,
    run_target_fixed_trace_candidate,
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


def _channel(
    *,
    power: float,
    amplitude: float,
    side: str = "top",
    m: int = 0,
    propagating: bool = True,
    power_carrying: bool = True,
) -> dict:
    return {
        "side": side,
        "m": m,
        "n": 0,
        "polarization": "s",
        "direction": (
            "outgoing_up" if side == "top" else "outgoing_down"
        ),
        "medium": "air" if side == "top" else "substrate",
        "order_m": m,
        "order_n": 0,
        "alpha": [0.0, 0.0],
        "gamma": [0.0, 0.0],
        "beta": [1.0, 0.0],
        "kz": [1.0, 0.0],
        "vertical_sign": 1,
        "propagating": propagating,
        "power_carrying": power_carrying,
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


def test_channel_diagnostic_can_audit_extra_evanescent_modes() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        paths = [
            root / name
            for name in ("p5.json", "p6.json", "candidate.json")
        ]
        shared = _channel(power=0.1, amplitude=0.3)
        extra = _channel(
            power=2.0e-7,
            amplitude=0.0,
            side="bottom",
            m=1,
            propagating=False,
            power_carrying=True,
        )
        payloads = (
            {"orders": [shared]},
            {"orders": [shared]},
            {"orders": [shared, extra]},
        )
        for path, payload in zip(paths, payloads, strict=True):
            path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError, match="identities differ"):
            compare_diffraction_channels(
                global_p5_path=paths[0],
                global_p6_path=paths[1],
                candidate_p6_path=paths[2],
            )
        comparison = compare_diffraction_channels(
            global_p5_path=paths[0],
            global_p6_path=paths[1],
            candidate_p6_path=paths[2],
            allow_candidate_extra_modes=True,
        )
        assert comparison["channel_count"] == 1
        assert comparison["candidate_extra_mode_audit"]["count"] == 1
        assert comparison["candidate_extra_mode_audit"][
            "power_carrying_count_diagnostic_only"
        ] == 1
        assert comparison["candidate_extra_mode_audit"][
            "nonzero_power_count_diagnostic_only"
        ] == 1
        assert comparison["candidate_extra_mode_audit"]["pass"] is True
        assert comparison["pass"] is True


def test_reference_v1_gate_requires_exact_12_of_12(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    reference_path = (
        repo_root
        / "benchmarks/cases/095_high_order_local_hp_resource_envelope/"
        "records/significant_channel_reference_v1.json"
    )
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    p6_authority = next(
        row
        for row in reference["authorities"]
        if row["sample_id"] == "p6_h10"
    )
    candidate_path = tmp_path / "candidate.json"
    candidate_path.write_text(
        (
            repo_root
            / p6_authority["raw_dtn_port_orders"]["path"]
        ).read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    reference_sha256 = hashlib.sha256(
        reference_path.read_bytes()
    ).hexdigest()
    passing = compare_significant_channels_to_reference_v1(
        candidate_path=candidate_path,
        reference_record_path=reference_path,
        reference_record_sha256=reference_sha256,
    )
    assert passing["pass"] is True
    assert passing["significant_power_pass_count"] == 12
    assert passing["significant_complex_amplitude_pass_count"] == 12

    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    failed_key = (
        reference["channels"][0]["channel"]["side"],
        reference["channels"][0]["channel"]["m"],
        reference["channels"][0]["channel"]["n"],
        reference["channels"][0]["channel"]["polarization"],
    )
    failed_order = next(
        order
        for order in candidate["orders"]
        if (
            order["side"],
            order["m"],
            order["n"],
            order["polarization"],
        )
        == failed_key
    )
    failed_order["outgoing_amplitude_at_boundary"][0] += 1.0
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
    failed = compare_significant_channels_to_reference_v1(
        candidate_path=candidate_path,
        reference_record_path=reference_path,
        reference_record_sha256=reference_sha256,
    )
    assert failed["pass"] is False
    assert failed["significant_power_pass_count"] == 12
    assert failed["significant_complex_amplitude_pass_count"] == 11


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
    values = [
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
        "--fixed-trace-significant-channel-reference-record",
        "significant.json",
        "--fixed-trace-significant-channel-reference-sha256",
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
    args = _parse_args(values)
    assert args.fixed_trace_control_sha256 == sha
    assert args.fixed_trace_degree == 5
    assert args.fixed_interior_degree == 6
    assert args.fixed_trace_global_p6_baseline_sha256 == sha
    assert _select_qualifier(args).__name__ == "_qualify_fixed_trace"
    diagnostic = _parse_args(
        [*values, "--fixed-trace-channel-adjoint-diagnostic"]
    )
    assert diagnostic.fixed_trace_channel_adjoint_diagnostic is True
    quadrature = _parse_args(
        [*values, "--fixed-trace-dtn-quadrature-degree", "31"]
    )
    assert quadrature.fixed_trace_dtn_quadrature_degree == 31
    quadrature_preflight = _fixed_trace_resource_preflight(quadrature)
    assert quadrature_preflight["pass"] is True
    assert quadrature_preflight["predicted_resources"][
        "dtn_surface_quadrature_degree"
    ] == 31
    assert quadrature_preflight["predicted_resources"][
        "dtn_auxiliary_rows"
    ] == 80
    evanescent = _parse_args(
        [*values, "--fixed-trace-dtn-evanescent-buffer", "1"]
    )
    assert evanescent.fixed_trace_dtn_evanescent_buffer == 1
    evanescent_preflight = _fixed_trace_resource_preflight(evanescent)
    assert evanescent_preflight["pass"] is False
    assert evanescent_preflight["checks"][
        "unscaled_port_basis_numerically_safe"
    ] is False
    assert evanescent_preflight["port_basis_scaling_preflight"][
        "status"
    ] == "controlled_stop_unscaled_evanescent_port_basis"
    assert evanescent_preflight["port_basis_scaling_preflight"][
        "pde_authorized"
    ] is False
    assert evanescent_preflight["predicted_resources"][
        "dtn_surface_quadrature_degree"
    ] == 25
    assert evanescent_preflight["predicted_resources"][
        "dtn_auxiliary_rows"
    ] == 340
    assert evanescent_preflight["predicted_resources"][
        "dtn_evanescent_rows"
    ] == 260
    assert evanescent_preflight["predicted_resources"][
        "expected_active_rows"
    ] == 17140
    with pytest.raises(SystemExit):
        _parse_args(
            [
                *values,
                "--fixed-trace-dtn-quadrature-degree",
                "31",
                "--fixed-trace-dtn-evanescent-buffer",
                "1",
            ]
        )
    with pytest.raises(SystemExit):
        _parse_args(
            [
                *values,
                "--fixed-trace-channel-adjoint-diagnostic",
                "--fixed-trace-dtn-quadrature-degree",
                "31",
            ]
        )
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


def test_buffer1_preflight_is_a_preserved_controlled_stop() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    record = build_controlled_stop_record(
        repo_root,
        source={
            "commit_sha": "test",
            "branch": "test",
            "tracked_source_dirty": False,
            "stable_and_clean_before": True,
        },
    )
    assert record["pass"] is True
    assert (
        record["status"]
        == "controlled_stop_unscaled_evanescent_port_basis"
    )
    assert record["pde"]["status"] == "not_run"
    assert record["pde"]["heavy_case_started"] is False
    scaling = record["port_basis_scaling_preflight"]
    assert scaling["pde_authorized"] is False
    assert scaling["minimum_abs_boundary_phase"] == pytest.approx(
        4.698738560873268e-84
    )
    assert scaling["minimum_projection_denominator"] == pytest.approx(
        1.314525165643265e-164
    )
    assert record["resource_projection"]["dtn_auxiliary_rows"] == 340


def test_directional_fixed_trace_cli_allows_only_hash_bound_h14_h13() -> None:
    sha = "b" * 64

    def arguments(h_nm: str) -> list[str]:
        values = [
            "--coarse-degree",
            "5",
            "--enriched-degree",
            "6",
            "--h-nm",
            h_nm,
            "--mesh-cell-type",
            "hexahedron",
            "--mpi-size",
            "8",
            "--fixed-trace-control-record",
            "control.json",
            "--fixed-trace-control-sha256",
            sha,
            "--fixed-trace-significant-channel-reference-record",
            "significant.json",
            "--fixed-trace-significant-channel-reference-sha256",
            sha,
            "--fixed-trace-degree",
            "5",
            "--fixed-interior-degree",
            "6",
            "--fixed-trace-directional-recovery",
        ]
        if h_nm == "13":
            values.extend(
                [
                    "--fixed-trace-directional-parent-record",
                    "h14.json",
                    "--fixed-trace-directional-parent-sha256",
                    sha,
                ]
            )
        return values

    for h_nm in ("14", "13"):
        args = _parse_args(arguments(h_nm))
        assert args.fixed_trace_directional_recovery is True
        assert args.fixed_trace_global_p6_baseline_record is None
        assert (
            args.fixed_trace_directional_parent_record is not None
        ) == (h_nm == "13")
        assert _select_qualifier(args).__name__ == "_qualify_fixed_trace"
        preflight = _fixed_trace_resource_preflight(args)
        assert preflight["pass"] is True
        assert preflight["axis_plan"]["mesh_cells_resolved"] == (
            [6, 2, 11] if h_nm == "14" else [6, 2, 12]
        )
        assert preflight["checks"][
            "directional_x_axis_matches_h15"
        ]
        assert preflight["checks"][
            "directional_y_axis_matches_h15"
        ]
        assert preflight["checks"][
            "directional_z_axis_differs_from_h15"
        ]
    with pytest.raises(SystemExit):
        _parse_args(arguments("12"))
    with pytest.raises(SystemExit):
        _parse_args(
            arguments("13")[:-4]
        )
    with pytest.raises(SystemExit):
        _parse_args(
            [
                item
                for item in arguments("14")
                if item != "--fixed-trace-directional-recovery"
            ]
        )


def test_directional_same_mesh_global_p6_dof_count_is_exact() -> None:
    audit = {
        "entity_dof_inventory": {
            "global_entity_counts": {
                "edges": 615,
                "faces": 496,
                "cells": 132,
            }
        }
    }
    assert _derived_standard_global_dofs(audit, degree=6) == 92850


def test_target_api_rejects_unreviewed_directional_topology(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="requires h14 or h13"):
        run_target_fixed_trace_candidate(
            tmp_path / "unreviewed",
            control_record=tmp_path / "control.json",
            control_sha256="a" * 64,
            significant_channel_reference_record=(
                tmp_path / "significant.json"
            ),
            significant_channel_reference_sha256="b" * 64,
            h_nm=12.0,
            directional_recovery=True,
        )


def test_watchdog_record_path_never_overwrites_evidence(
    tmp_path: Path,
) -> None:
    authority = tmp_path / "authority.json"
    authority.write_text("{}\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="must not alias"):
        _resolve_new_record_path(
            authority,
            input_authorities=(authority,),
        )
    existing = tmp_path / "existing.json"
    existing.write_text("{}\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="already exists"):
        _resolve_new_record_path(
            existing,
            input_authorities=(authority,),
        )
    fresh = tmp_path / "fresh.json"
    assert _resolve_new_record_path(
        fresh,
        input_authorities=(authority,),
    ) == fresh.resolve()


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
