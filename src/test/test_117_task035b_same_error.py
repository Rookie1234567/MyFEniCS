"""Tests for the Task035b strict cross-mesh same-error audit."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import tempfile
from types import SimpleNamespace

import numpy as np
import pyvista as pv
import pytest

from benchmarks.run_task035_actual_r5 import (
    _compact_channel_adjoint_diagnostic,
    _compact_solve,
    _fixed_trace_x_contract_checks,
    _fixed_trace_resource_preflight,
    _parse_args,
    _preflight_artifact_evidence,
    _resolve_new_record_path,
    _select_qualifier,
    _structured_axis_global_control_preflight,
    _structured_axis_y_contract_checks,
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


def test_reference_v1_gate_rejects_nonfinite_and_zero_tolerance(
    tmp_path: Path,
) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    reference_path = (
        repo_root
        / "benchmarks/cases/095_high_order_local_hp_resource_envelope/"
        "records/significant_channel_reference_v1.json"
    )
    reference = json.loads(reference_path.read_text(encoding="utf-8"))
    reference_sha256 = hashlib.sha256(
        reference_path.read_bytes()
    ).hexdigest()
    p6_authority = next(
        row
        for row in reference["authorities"]
        if row["sample_id"] == "p6_h10"
    )
    authoritative_candidate = json.loads(
        (
            repo_root
            / p6_authority["raw_dtn_port_orders"]["path"]
        ).read_text(encoding="utf-8")
    )
    frozen_key = (
        reference["channels"][0]["channel"]["side"],
        reference["channels"][0]["channel"]["m"],
        reference["channels"][0]["channel"]["n"],
        reference["channels"][0]["channel"]["polarization"],
    )

    for field, invalid_value in (
        ("power_ratio", float("nan")),
        ("outgoing_amplitude_at_boundary", [float("inf"), 0.0]),
    ):
        candidate = json.loads(json.dumps(authoritative_candidate))
        selected = next(
            order
            for order in candidate["orders"]
            if (
                order["side"],
                order["m"],
                order["n"],
                order["polarization"],
            )
            == frozen_key
        )
        selected[field] = invalid_value
        candidate_path = tmp_path / f"invalid_{field}.json"
        candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
        with pytest.raises(ValueError, match="finite physical Gate"):
            compare_significant_channels_to_reference_v1(
                candidate_path=candidate_path,
                reference_record_path=reference_path,
                reference_record_sha256=reference_sha256,
            )

    invalid_reference = json.loads(json.dumps(reference))
    invalid_reference["channels"][0]["unchanged_v0_acceptance_gate"][
        "power_absolute_tolerance"
    ] = 0.0
    invalid_reference_path = tmp_path / "zero_tolerance_reference.json"
    invalid_reference_path.write_text(
        json.dumps(invalid_reference),
        encoding="utf-8",
    )
    valid_candidate_path = tmp_path / "valid_candidate.json"
    valid_candidate_path.write_text(
        json.dumps(authoritative_candidate),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="finite physical Gate"):
        compare_significant_channels_to_reference_v1(
            candidate_path=valid_candidate_path,
            reference_record_path=invalid_reference_path,
            reference_record_sha256=hashlib.sha256(
                invalid_reference_path.read_bytes()
            ).hexdigest(),
        )


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
    assert evanescent_preflight["pass"] is True
    assert evanescent_preflight["checks"][
        "actual_port_basis_numerically_safe"
    ] is True
    assert evanescent_preflight["port_basis_scaling_preflight"][
        "status"
    ] == "safe_boundary_referenced_evanescent_basis"
    assert evanescent_preflight["port_basis_scaling_preflight"][
        "pde_authorized"
    ] is True
    assert evanescent_preflight["port_basis_scaling_preflight"][
        "historical_unscaled_basis_numerically_safe"
    ] is False
    assert evanescent_preflight["port_basis_scaling_preflight"][
        "boundary_referenced_mode_count"
    ] == 260
    assert evanescent_preflight["port_basis_scaling_preflight"][
        "minimum_assembly_projection_denominator"
    ] == pytest.approx(32.1362606996094)
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


def test_channel_adjoint_record_compaction_preserves_top_proxy_rows() -> None:
    localization = {
        "schema_version": "proxy.v1",
        "actual_dwr_indicator": False,
        "lane_b_formal_selection_authorized": False,
        "entities": {
            "cell": {
                "canonical_entity_count": 3,
                "rows": [
                    {
                        "canonical_cell_id": index,
                        "normalized_sensitivity_proxy": value,
                    }
                    for index, value in enumerate((1.0, 4.0, 2.0))
                ],
            }
        },
        "periodic_transitive_aggregation": {
            "axes": ["x"],
            "edge_trace": {
                "component_count": 2,
                "member_to_component": {"0": 0, "1": 1},
                "components": [
                    {
                        "periodic_component_id": 0,
                        "component_proxy_sum": 2.0,
                    },
                    {
                        "periodic_component_id": 1,
                        "component_proxy_sum": 5.0,
                    },
                ],
            },
            "face_trace": {
                "component_count": 0,
                "member_to_component": {},
                "components": [],
            },
        },
    }
    compact = _compact_channel_adjoint_diagnostic(
        {
            "pass": True,
            "recovered_full_duals": {
                "goal": {
                    "full_fe_rows": 10,
                    "entity_sensitivity_proxy": localization,
                }
            },
        }
    )
    assert compact is not None
    proxy = compact["recovered_full_duals"]["goal"][
        "entity_sensitivity_proxy"
    ]
    assert proxy["raw_payload_sha256"]
    assert proxy["entities"]["cell"]["raw_row_count"] == 3
    assert [
        row["normalized_sensitivity_proxy"]
        for row in proxy["entities"]["cell"][
            "top_normalized_sensitivity_rows"
        ]
    ] == [4.0, 2.0, 1.0]
    assert "member_to_component" not in (
        proxy["periodic_transitive_aggregation"]["edge_trace"]
    )
    assert proxy["periodic_transitive_aggregation"]["edge_trace"][
        "top_component_proxy_rows"
    ][0]["component_proxy_sum"] == 5.0


def test_directional_fixed_trace_cli_keeps_z_and_adds_exact_x_lane() -> None:
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
            "directional_exactly_one_axis_changed"
        ]
        assert preflight["checks"][
            "directional_nonselected_axes_match_h15"
        ]
        assert preflight["directional_axis"] == "z"
        assert preflight["axis_plan"]["changed_axes_from_h15"] == ["z"]

    x_args = _parse_args(
        [
            *arguments("15"),
            "--fixed-trace-directional-axis",
            "x",
            "--structured-axis-cells",
            "7,2,10",
        ]
    )
    assert x_args.fixed_trace_directional_axis == "x"
    assert x_args.structured_axis_cells == (7, 2, 10)
    x_preflight = _fixed_trace_resource_preflight(x_args)
    assert x_preflight["pass"] is True
    assert x_preflight["axis_plan"]["mesh_cells_resolved"] == [7, 2, 10]
    assert x_preflight["axis_plan"]["changed_axes_from_h15"] == ["x"]
    assert x_preflight["directional_mesh_change_semantics"] == (
        "exact_material_fitted_remeshing_not_nested_refinement"
    )
    assert x_preflight["axis_plan"]["axis_sha256"]["x"] == (
        "f99cf720acdbd78d426ef4f36cb22c0944de3a6b23f744750d48a51d85d342cd"
    )
    assert x_preflight["axis_plan"]["expected_mesh_identity"][
        "partition_independent_mesh_sha256"
    ] == "326019d01cf2b98a83422e9c0aa520795daaa5bbc1fdeb73d567799504c705b1"
    assert x_preflight["predicted_resources"]["candidate_dofs"] == 87195
    assert (
        x_preflight["predicted_resources"]["expected_active_rows"]
        == 19680
    )
    assert x_preflight["predicted_resources"]["base_schur_nnz"] == 10650850

    explicit_z_args = _parse_args(
        [
            *arguments("14"),
            "--fixed-trace-directional-axis",
            "z",
            "--fixed-trace-explicit-z-profile",
            "h14_max-R5_slab_bisect",
        ]
    )
    explicit_z_preflight = _fixed_trace_resource_preflight(
        explicit_z_args
    )
    assert explicit_z_preflight["pass"] is True
    assert explicit_z_preflight["explicit_z_profile"] == (
        "h14_max-R5_slab_bisect"
    )
    assert explicit_z_preflight["axis_plan"]["mesh_cells_resolved"] == [
        6,
        2,
        12,
    ]
    assert explicit_z_preflight["axis_plan"]["axis_sha256"]["z"] == (
        "9048a25cdb01a0ef2aa123bc5f7ec66116a2320ed42376e63ec22679e5f3c6d8"
    )
    assert (
        explicit_z_preflight["predicted_resources"]["candidate_dofs"]
        == 89740
    )
    assert (
        explicit_z_preflight["predicted_resources"][
            "expected_active_rows"
        ]
        == 20120
    )
    with pytest.raises(SystemExit):
        _parse_args(
            [
                *arguments("13"),
                "--fixed-trace-explicit-z-profile",
                "h14_max-R5_slab_bisect",
            ]
        )
    with pytest.raises(SystemExit):
        _parse_args(
            [
                *arguments("14"),
                "--fixed-trace-explicit-z-profile",
                "h14_max-R5_slab_bisect",
                "--structured-axis-cells",
                "6,2,12",
            ]
        )
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
    with pytest.raises(SystemExit):
        _parse_args(
            [
                *arguments("15"),
                "--fixed-trace-directional-axis",
                "x",
            ]
        )
    with pytest.raises(SystemExit):
        _parse_args(
            [
                *arguments("15"),
                "--fixed-trace-directional-axis",
                "x",
                "--structured-axis-cells",
                "6,3,10",
            ]
        )


def test_y_only_global_p5_control_is_exact_and_fail_closed() -> None:
    values = [
        "--coarse-degree",
        "4",
        "--enriched-degree",
        "5",
        "--h-nm",
        "15",
        "--mesh-cell-type",
        "hexahedron",
        "--mpi-size",
        "8",
        "--single-mesh-pair",
        "--structured-axis-cells",
        "6,3,10",
    ]
    for degree in ("4", "5"):
        values.extend(["--static-condensation-degree", degree])
        values.extend(["--assembly-time-condensation-degree", degree])
        values.extend(["--floquet-slave-elimination-degree", degree])

    args = _parse_args(values)
    assert args.structured_axis_cells == (6, 3, 10)
    assert _select_qualifier(args).__name__ == "_qualify"
    preflight = _structured_axis_global_control_preflight(args)
    assert preflight["pass"] is True
    assert preflight["ordinary_default_changed"] is False
    axis_plan = preflight["axis_plan"]
    assert axis_plan["mesh_cells_resolved"] == [6, 3, 10]
    assert axis_plan["axis_sha256"]["y"] == (
        "d7841480e80baeda07536ebc44681af4488f7d61a2eaa7de4d33cdacb9fa19fb"
    )
    assert axis_plan["expected_mesh_identity"][
        "partition_independent_mesh_sha256"
    ] == "59d053ac70baaa80c6de82fcd2388d0076291f033cf074197c218055756eec8f"
    assert axis_plan["expected_mesh_identity"]["cell_tag_sha256"] == (
        "60209a26ca68027775dc54783cc44a67314804ced204928025d35607c4d999e0"
    )
    assert axis_plan["expected_mesh_identity"]["facet_tag_sha256"] == (
        "270b60e1c061cd539e64219e349e29abe0deb6e414c35c979abb25e2660b9c75"
    )
    resources = preflight["predicted_resources"]
    assert resources["coarse_p4_dofs"] == 38092
    assert resources["coarse_p4_active_rows_with_dtn"] == 15776
    assert resources["coarse_p4_base_schur_nnz"] == 5808384
    assert resources["coarse_p4_predicted_used_nnz"] == 5872400
    assert resources["enriched_p5_dofs"] == 72995
    assert resources["enriched_p5_active_rows_with_dtn"] == 25280
    assert resources["enriched_p5_base_schur_nnz"] == 14333400
    assert resources["enriched_p5_predicted_used_nnz"] == 14433128

    wrong_axis = list(values)
    wrong_axis[wrong_axis.index("6,3,10")] = "7,2,10"
    with pytest.raises(SystemExit):
        _parse_args(wrong_axis)
    without_single_mesh = [
        value for value in values if value != "--single-mesh-pair"
    ]
    with pytest.raises(SystemExit):
        _parse_args(without_single_mesh)
    incomplete_condensation = list(values)
    index = incomplete_condensation.index(
        "--assembly-time-condensation-degree"
    )
    del incomplete_condensation[index : index + 2]
    with pytest.raises(SystemExit):
        _parse_args(incomplete_condensation)


def test_x_directional_focused_qualifier_is_mutation_closed() -> None:
    args = SimpleNamespace(
        fixed_trace_directional_recovery=True,
        fixed_trace_directional_axis="x",
        structured_axis_cells=(7, 2, 10),
        mpi_size=8,
        h_nm=15.0,
    )
    preflight = {
        "pass": True,
        "directional_axis": "x",
        "structured_axis_cells_requested": [7, 2, 10],
        "predicted_resources": {
            "mesh_cells_resolved": [7, 2, 10],
            "num_mesh_cells": 140,
            "candidate_dofs": 87195,
            "global_p6_dofs": 98322,
            "active_rows_with_dtn": 19680,
            "base_schur_nnz": 10650850,
            "predicted_used_nnz": 10728434,
            "safe_allocated_nnz_upper": 11065344,
        },
    }
    result = {
        "target_identity": {
            "directional_axis": "x",
            "mesh_axis_cell_counts_requested": [7, 2, 10],
            "actual_mesh_cells_resolved": [7, 2, 10],
            "directional_mesh_change_semantics": (
                "exact_material_fitted_remeshing_not_nested_refinement"
            ),
        },
        "candidate": {
            "summary": {
                "mesh_cells_resolved": [7, 2, 10],
                "num_mesh_cells": 140,
                "num_nedelec_dofs": 87195,
                "config": {
                    "mesh_axis_cell_counts_requested": [7, 2, 10]
                },
                "matrix_stats": {
                    "matrix_rows": 19680,
                    "matrix_nnz_used": 10728434,
                    "matrix_nnz_allocated": 11065344,
                    "matrix_mallocs": 0,
                    "matrix_average_nnz_per_row": 545.144,
                    "matrix_maximum_nnz_per_row": 965,
                },
            },
            "high_order_resource_audit": {
                "mesh_identity": {
                    "partition_independent_mesh_sha256": (
                        "326019d01cf2b98a83422e9c0aa520795daaa5bbc1fdeb73d567799504c705b1"
                    ),
                    "cell_tag_sha256": (
                        "1434790f1ba5bb102c57561dd9a925f8f6f46aa4ebcb7c37194e205ee2e3d11c"
                    ),
                    "facet_tag_sha256": (
                        "d2fa4745b79663b1838fa51473545f3b8290b0ed17212c28d162e27ae0e6c693"
                    ),
                },
                "matrix_factor_resource": {
                    "factor_inventory_available": True,
                    "factor_nnz": 3.0e7,
                    "factor_average_row_width": 1524.0,
                    "factor_fill_ratio": 2.8,
                },
            },
        },
        "dof_target": {
            "active_full3d_equivalent_dofs": 87195,
            "same_mesh_global_p6_dofs": 98322,
            "minimum_le_90000": True,
            "inactive_p6_trace_modes_physically_absent": True,
        },
        "directional_parent_authority": {
            "status": "not_required_primary_x",
            "required": False,
        },
        "same_mesh_global_p6_baseline": {
            "required": False,
        },
    }
    checks = _fixed_trace_x_contract_checks(
        result,
        args=args,
        preflight=preflight,
    )
    assert checks and all(checks.values())

    mutated = json.loads(json.dumps(result))
    mutated["candidate"]["summary"]["matrix_stats"][
        "matrix_nnz_used"
    ] += 1
    assert not _fixed_trace_x_contract_checks(
        mutated,
        args=args,
        preflight=preflight,
    )["matrix_structure"]
    mutated = json.loads(json.dumps(result))
    mutated["candidate"]["high_order_resource_audit"][
        "mesh_identity"
    ]["cell_tag_sha256"] = "bad"
    assert not _fixed_trace_x_contract_checks(
        mutated,
        args=args,
        preflight=preflight,
    )["mesh_and_tag_identity"]
    mutated = json.loads(json.dumps(result))
    mutated["target_identity"][
        "directional_mesh_change_semantics"
    ] = "nested_refinement"
    assert not _fixed_trace_x_contract_checks(
        mutated,
        args=args,
        preflight=preflight,
    )["target_identity"]


def test_y_control_focused_qualifier_is_mutation_closed(
    tmp_path: Path,
) -> None:
    args = SimpleNamespace(
        structured_axis_cells=(6, 3, 10),
        mpi_size=8,
        coarse_degree=4,
        enriched_degree=5,
        h_nm=15.0,
        polarization_kind="s",
        run_dir=tmp_path,
    )
    orders = (
        tmp_path
        / "enriched_p5"
        / "dtn_port_diffraction_orders_3d.json"
    )
    orders.parent.mkdir(parents=True)
    orders.write_text(
        json.dumps({"orders": [{} for _ in range(80)]}) + "\n",
        encoding="utf-8",
    )

    def solve(degree: int) -> dict[str, object]:
        dofs, rows, nnz = {
            4: (38092, 15776, 5872400),
            5: (72995, 25280, 14433128),
        }[degree]
        return {
            "degree": degree,
            "summary": {
                "mesh_cells_resolved": [6, 3, 10],
                "num_mesh_cells": 180,
                "num_nedelec_dofs": dofs,
                "config": {
                    "mesh_axis_cell_counts_requested": [6, 3, 10]
                },
                "matrix_stats": {
                    "matrix_rows": rows,
                    "matrix_nnz_used": nnz,
                },
                "cell_static_condensation": {
                    "full_explicit_true_residual": {
                        "linear_system_relative_residual": 1.0e-12
                    }
                },
                "dtn_port_orders_json": (
                    "dtn_port_diffraction_orders_3d.json"
                    if degree == 5
                    else None
                ),
            },
        }

    preflight = {
        "pass": True,
        "control_role": "y_only_global_p5_directional_control",
        "predicted_resources": {
            "mesh_cells_resolved": [6, 3, 10],
            "num_mesh_cells": 180,
            "coarse_p4_dofs": 38092,
            "coarse_p4_active_rows_with_dtn": 15776,
            "coarse_p4_base_schur_nnz": 5808384,
            "coarse_p4_predicted_used_nnz": 5872400,
            "enriched_p5_dofs": 72995,
            "enriched_p5_active_rows_with_dtn": 25280,
            "enriched_p5_base_schur_nnz": 14333400,
            "enriched_p5_predicted_used_nnz": 14433128,
        },
    }
    result = {
        "coarse": solve(4),
        "enriched": solve(5),
        "common_mesh_identity": {
            "mesh_cells_resolved": [6, 3, 10],
            "global_cell_count": 180,
            "partition_independent_mesh_sha256": (
                "59d053ac70baaa80c6de82fcd2388d0076291f033cf074197c218055756eec8f"
            ),
            "cell_tag_sha256": (
                "60209a26ca68027775dc54783cc44a67314804ced204928025d35607c4d999e0"
            ),
            "facet_tag_sha256": (
                "270b60e1c061cd539e64219e349e29abe0deb6e414c35c979abb25e2660b9c75"
            ),
        },
    }
    checks = _structured_axis_y_contract_checks(
        result,
        args=args,
        preflight=preflight,
    )
    assert checks and all(checks.values())
    mutated = json.loads(json.dumps(result))
    mutated["enriched"]["summary"]["num_nedelec_dofs"] = 90001
    assert not _structured_axis_y_contract_checks(
        mutated,
        args=args,
        preflight=preflight,
    )["topology_and_dofs"]
    mutated = json.loads(json.dumps(result))
    mutated["coarse"]["summary"]["cell_static_condensation"][
        "full_explicit_true_residual"
    ]["linear_system_relative_residual"] = 2.0e-9
    assert not _structured_axis_y_contract_checks(
        mutated,
        args=args,
        preflight=preflight,
    )["full_true_residuals"]


@pytest.mark.parametrize(
    ("mode", "fixed_exists", "structured_exists"),
    (
        ("fixed_x", True, False),
        ("fixed_z_legacy", True, False),
        ("y_control", False, True),
        ("ordinary", False, False),
    ),
)
def test_preflight_artifact_evidence_is_conditional(
    tmp_path: Path,
    mode: str,
    fixed_exists: bool,
    structured_exists: bool,
) -> None:
    fixed = tmp_path / f"{mode}_fixed.json"
    structured = tmp_path / f"{mode}_structured.json"
    if fixed_exists:
        fixed.write_text('{"mode":"fixed"}\\n', encoding="utf-8")
    if structured_exists:
        structured.write_text('{"mode":"structured"}\\n', encoding="utf-8")

    evidence = _preflight_artifact_evidence(
        fixed_trace_path=fixed,
        structured_axis_path=structured,
    )
    assert (
        evidence["fixed_trace_resource_preflight"] is not None
    ) is fixed_exists
    assert (
        evidence["fixed_trace_resource_preflight_sha256"] is not None
    ) is fixed_exists
    assert (
        evidence["structured_axis_resource_preflight"] is not None
    ) is structured_exists
    assert (
        evidence[
            "structured_axis_resource_preflight_sha256"
        ]
        is not None
    ) is structured_exists
    if fixed_exists:
        assert evidence["fixed_trace_resource_preflight_sha256"] == (
            hashlib.sha256(fixed.read_bytes()).hexdigest()
        )
    if structured_exists:
        assert evidence[
            "structured_axis_resource_preflight_sha256"
        ] == hashlib.sha256(structured.read_bytes()).hexdigest()


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
    with pytest.raises(ValueError, match="requires legacy h14 or h13"):
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
    with pytest.raises(ValueError, match="exact axis cells"):
        run_target_fixed_trace_candidate(
            tmp_path / "wrong_x",
            control_record=tmp_path / "control.json",
            control_sha256="a" * 64,
            significant_channel_reference_record=(
                tmp_path / "significant.json"
            ),
            significant_channel_reference_sha256="b" * 64,
            h_nm=15.0,
            directional_recovery=True,
            directional_axis="x",
            mesh_axis_cell_counts=(6, 3, 10),
        )
    with pytest.raises(ValueError, match="three integers"):
        run_target_fixed_trace_candidate(
            tmp_path / "float_axis",
            control_record=tmp_path / "control.json",
            control_sha256="a" * 64,
            significant_channel_reference_record=(
                tmp_path / "significant.json"
            ),
            significant_channel_reference_sha256="b" * 64,
            h_nm=15.0,
            directional_recovery=True,
            directional_axis="x",
            mesh_axis_cell_counts=(7, 2, 10.0),
        )
    with pytest.raises(ValueError, match="three integers"):
        run_target_fixed_trace_candidate(
            tmp_path / "scalar_axis",
            control_record=tmp_path / "control.json",
            control_sha256="a" * 64,
            significant_channel_reference_record=(
                tmp_path / "significant.json"
            ),
            significant_channel_reference_sha256="b" * 64,
            h_nm=15.0,
            directional_recovery=True,
            directional_axis="x",
            mesh_axis_cell_counts=7,  # type: ignore[arg-type]
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
    assert compact["mesh_cells_resolved"] is None
    assert compact["mesh_axis_cell_counts_requested"] is None
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
