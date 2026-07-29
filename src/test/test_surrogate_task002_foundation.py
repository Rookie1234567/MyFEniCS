from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks.check_case112_task002 import build_scaffold_record
from benchmarks.check_case113_task002_m2a import build_scaffold_record as build_case113_scaffold
from benchmarks.check_case114_task002_m2b import SELECTED as M2B_SELECTED
from benchmarks.check_case114_task002_m2b import _order_delta as m2b_order_delta
from benchmarks.run_task032_phase6_augmented import _parse_args
from src.forward_data.orders import FIXED_M_ORDERS
from src.forward_data.task002_campaign import (
    _parser, load_manifest, sample_key, task002_hybrid_command, update_manifest,
)
from src.forward_data.task002_dataset import verify_compact_dataset, write_compact_dataset
from src.forward_data.task002_design import (
    audit_order_window, cutoff_diagnostics, cutoff_diagnostics_v2,
    fixed_hf_angle_pilot, incident_wave_audit, lf_angle_pilot,
)
from src.forward_data.task002_m2a import hybrid_command, validate_hybrid_scope
from src.forward_data.task002_m2b import (
    AZIMUTH_DEG as M2B_AZIMUTH_DEG,
    GRAZING_DEG as M2B_GRAZING_DEG,
    hybrid_command as m2b_hybrid_command,
)
from src.forward_data.task002_full3d import (
    AXIS_CELL_COUNTS, build_task002_full3d_config, task002_full3d_command,
    task002_full3d_config_identity, task002_full3d_topology_identity,
)
from src.forward_data.task002_schema import (
    TASK002_OBSERVABLE_SCHEMA_VERSION, Task002ForwardParameters,
    classify_task002_request, task002_parameter_catalog,
)


LF = "S_LF_FULL3D_STATIC_P4_H10"
HF = "S_HF_FULL3D_STATIC_P5_H10"


def _parameters(**updates) -> Task002ForwardParameters:
    values = dict(
        height_nm=120.0, width_x_nm=17.0, grazing_deg=5.25,
        azimuth_deg=45.0, model_id=LF,
    )
    values.update(updates)
    return Task002ForwardParameters(**values)


def test_s_only_schema_and_exact_zero_fail_closed() -> None:
    catalog = task002_parameter_catalog()
    assert catalog["fixed"] == {"wavelength_nm": 13.5, "incident_polarization": "S"}
    assert classify_task002_request({
        "height_nm": 120, "width_x_nm": 17, "grazing_deg": 0,
        "azimuth_deg": 45,
    })["status"] == "zero_grazing_limit_not_defined"
    assert classify_task002_request({
        "height_nm": 120, "width_x_nm": 17, "grazing_deg": 0.1,
        "azimuth_deg": 45,
    })["status"] == "out_of_training_domain"
    assert classify_task002_request({
        "height_nm": 120, "width_x_nm": 17, "grazing_deg": 5,
        "azimuth_deg": 45, "incident_polarization": "P",
    })["status"] == "polarization_not_trained"
    with pytest.raises(ValueError, match="polarization_not_trained"):
        _parameters(incident_polarization="P").validate()


@pytest.mark.parametrize("grazing,azimuth", [(0.5, 0.0), (5.25, 45.0), (10.0, 90.0)])
def test_angle_conversion_and_normalized_wavevector(grazing: float, azimuth: float) -> None:
    parameters = _parameters(grazing_deg=grazing, azimuth_deg=azimuth)
    assert parameters.theta_deg == pytest.approx(90.0 - grazing)
    features = parameters.normalized_features()
    assert features.shape == (4,)
    assert features[2] ** 2 + features[3] ** 2 == pytest.approx(
        np.cos(np.deg2rad(grazing)) ** 2
    )


def test_lf_and_hf_angle_pilot_are_frozen_and_unique() -> None:
    lf = lf_angle_pilot()
    hf = fixed_hf_angle_pilot()
    assert len(lf) == len({row["angle_id"] for row in lf}) == 49
    assert len(hf) == len({row["angle_id"] for row in hf}) == 9
    assert {row["role"] for row in hf} == {"corner", "edge_midpoint", "center"}


def test_order_window_and_cutoff_audit() -> None:
    audit = audit_order_window()
    assert audit["coverage_pass"] is True
    assert audit["missing_propagating_m"] == []
    assert set(audit["propagating_m_union"]).issubset(FIXED_M_ORDERS)
    cutoff = cutoff_diagnostics(_parameters(grazing_deg=0.5, azimuth_deg=0.0))
    assert cutoff["cutoff_metric"] >= 0.0
    assert len(cutoff["orders"]) == len(FIXED_M_ORDERS)


def test_cutoff_v2_separates_incident_grazing_from_nonzero_orders() -> None:
    parameters = _parameters(grazing_deg=0.5, azimuth_deg=15.0)
    cutoff = cutoff_diagnostics_v2(parameters)
    assert cutoff["schema_version"] == "task002.cutoff-diagnostics.v2"
    assert cutoff["incident_specular_abs_beta_over_k0"] == pytest.approx(
        np.sin(np.deg2rad(0.5)), rel=1e-10,
    )
    assert cutoff["nearest_order"]["m"] != 0
    assert isinstance(cutoff["rayleigh_crossing_in_local_angle_neighborhood"], bool)
    assert all("beta_top" in row and "beta_bottom" in row for row in cutoff["orders"])
    incident = incident_wave_audit(parameters)
    assert incident["abs_k_over_k0_abs_n_air"] == pytest.approx(1.0)
    assert incident["incident_normal_power_density"] > 0.0


@pytest.mark.parametrize(
    "degree,modes", [(4, 80), (4, 120), (4, 160), (4, 240), (5, 120), (6, 120)],
)
def test_m2a_matrix_gate_is_exact(tmp_path: Path, degree: int, modes: int) -> None:
    _, command = hybrid_command(
        root=tmp_path, baseline_sha="a" * 40, degree=degree, modes=modes,
        grazing=0.5, azimuth=15.0, output=tmp_path / "record.json",
        memory_stages=tmp_path / "stages.jsonl",
    )
    parsed = _parse_args(command[command.index("benchmarks.run_task032_phase6_augmented") + 1:])
    assert parsed.task002_m2a_diagnostic_gate is True
    assert parsed.requested_modes == modes and parsed.candidate_modes == 2 * modes


def test_m2a_scope_rejects_campaign_and_polarization_changes() -> None:
    with pytest.raises(ValueError, match="outside"):
        validate_hybrid_scope(degree=4, modes=120, grazing=4.0, azimuth=45.0)


@pytest.mark.parametrize("degree", [4, 5, 6])
@pytest.mark.parametrize("route", ["continuous", "discrete"])
def test_m2b_axial_routes_are_exact_and_fail_closed(
    tmp_path: Path, degree: int, route: str,
) -> None:
    _, command = m2b_hybrid_command(
        root=tmp_path, baseline_sha="a" * 40, degree=degree,
        grazing=0.5, azimuth=45.0, route=route,
        output=tmp_path / "record.json", memory_stages=tmp_path / "stages.jsonl",
    )
    parsed = _parse_args(command[command.index("benchmarks.run_task032_phase6_augmented") + 1:])
    assert parsed.task002_m2b_diagnostic_gate is True
    assert parsed.requested_modes == 120 and parsed.candidate_modes == 240
    expected = (
        ("continuous_beta", "continuous_qep_beta")
        if route == "continuous"
        else ("full3d_uniform_cg", "scalar_cg_discrete_derivative")
    )
    assert (parsed.internal_propagation_model, parsed.internal_traction_model) == expected


def test_m2b_angle_matrix_is_exactly_80_points() -> None:
    assert len(M2B_GRAZING_DEG) * len(M2B_AZIMUTH_DEG) == 80
    with pytest.raises(ValueError, match="outside"):
        m2b_hybrid_command(
            root=Path("."), baseline_sha="a" * 40, degree=4,
            grazing=3.0, azimuth=45.0, route="discrete",
            output=Path("record.json"), memory_stages=Path("stages.jsonl"),
        )


def test_m2b_selected_higher_order_set_and_order_checker() -> None:
    assert len(M2B_SELECTED) == 12
    assert (0.5, 15.0) in M2B_SELECTED and (0.5, 45.0) in M2B_SELECTED
    assert (1.0, 45.0) in M2B_SELECTED and (10.0, 45.0) in M2B_SELECTED
    left = {"orders": [{
        "side": "top", "m": 0, "n": 0, "polarization": "s",
        "outgoing_amplitude_at_boundary": [1.0, 2.0], "power_ratio": 0.5,
    }]}
    right = {"orders": [{
        "side": "top", "m": 0, "n": 0, "polarization": "s",
        "outgoing_amplitude_at_boundary": [1.0, 1.0], "power_ratio": 0.4,
    }]}
    delta = m2b_order_delta(left, right)
    assert delta["common_order_channels"] == 1
    assert delta["max_complex_amplitude_abs_error"] == pytest.approx(1.0)
    assert delta["max_power_ratio_abs_error"] == pytest.approx(0.1)


def test_task002_hybrid_production_route_is_hard_quarantined(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="hard quarantined"):
        task002_hybrid_command(
            _parameters(model_id=HF), root=tmp_path, baseline_sha="a" * 40,
            output_record=tmp_path / "record.json",
            memory_stages=tmp_path / "stages.jsonl",
        )


def test_task002_full3d_command_and_uniform_element_identity(tmp_path: Path) -> None:
    parameters_path = tmp_path / "parameters.json"
    command = task002_full3d_command(
        root=tmp_path, parameters_file=parameters_path, baseline_sha="a" * 40,
        output_dir=tmp_path / "results",
    )
    assert command[:3] == ["mpiexec", "-n", "2"]
    assert command[4:6] == ["-m", "src.runners.run_task002_full3d"]
    for model_id, degree in ((LF, 4), (HF, 5)):
        parameters = _parameters(model_id=model_id)
        cfg = build_task002_full3d_config(parameters)
        topology = task002_full3d_topology_identity(parameters)
        assert cfg.mesh_axis_cell_counts == AXIS_CELL_COUNTS
        assert cfg.nedelec_degree == degree
        assert cfg.nedelec_trace_degree is None
        assert cfg.nedelec_interior_degree is None
        assert topology["element_identity"]["family"] == "N1curl"
        assert topology["element_identity"]["degree"] == degree


def test_task002_fixed_topology_is_geometry_invariant() -> None:
    rows = []
    for height in (115.0, 120.0, 125.0):
        for width in (16.0, 17.0, 18.0):
            rows.append(task002_full3d_topology_identity(
                _parameters(height_nm=height, width_x_nm=width),
            ))
    for key in (
        "logical_connectivity_sha256", "material_tag_topology_sha256",
        "floquet_entity_topology_sha256", "dof_layout_identity_sha256",
        "topology_element_hash",
    ):
        assert len({row[key] for row in rows}) == 1
    assert len({row["coordinate_sha256"] for row in rows}) == 9


def test_task002_config_hash_is_deterministic_and_parameter_bound() -> None:
    first = task002_full3d_config_identity(_parameters())
    repeated = task002_full3d_config_identity(_parameters())
    changed = task002_full3d_config_identity(_parameters(azimuth_deg=60.0))
    assert first == repeated
    assert first["config_sha256"] != changed["config_sha256"]


def test_campaign_cli_requires_one_explicit_sample(tmp_path: Path) -> None:
    args = _parser().parse_args([
        "run-one", "--root", str(tmp_path), "--baseline-sha", "a" * 40,
        "--artifact-root", str(tmp_path / "artifacts"),
        "--campaign-manifest", str(tmp_path / "campaign.json"),
        "--model-id", LF, "--height-nm", "120", "--width-x-nm", "17",
        "--grazing-deg", "0.5", "--azimuth-deg", "90",
    ])
    assert args.command == "run-one" and args.grazing_deg == 0.5


def test_campaign_dedup_resume_and_completed_immutability(tmp_path: Path) -> None:
    manifest_path = tmp_path / "campaign.json"
    parameters = _parameters()
    update_manifest(
        manifest_path, baseline_sha="a" * 40, parameters=parameters,
        status="reserved", run_directory=tmp_path / "run",
    )
    update_manifest(
        manifest_path, baseline_sha="a" * 40, parameters=parameters,
        status="measured_pass", run_directory=tmp_path / "run",
    )
    manifest = load_manifest(manifest_path, baseline_sha="a" * 40)
    assert list(manifest["samples"]) == [sample_key(parameters)]
    with pytest.raises(ValueError, match="immutable"):
        update_manifest(
            manifest_path, baseline_sha="a" * 40, parameters=parameters,
            status="reserved",
        )
    with pytest.raises(ValueError, match="baseline"):
        load_manifest(manifest_path, baseline_sha="b" * 40)


def _mother_response() -> dict:
    orders = []
    for side in ("reflection", "transmission"):
        for m in FIXED_M_ORDERS:
            carrying = m != 1
            orders.append({
                "side": side, "port_side": "top" if side == "reflection" else "bottom",
                "m": m, "n": 0, "kx": {"re": 0.0, "im": 0.0},
                "ky": {"re": 0.0, "im": 0.0}, "kz": {"re": 1.0, "im": 0.0},
                "dispersion_propagating": carrying, "power_carrying": carrying,
                "components": {
                    pol: {
                        "amplitude_re": 0.1 if carrying else None,
                        "amplitude_im": 0.0 if carrying else None,
                        "power": 0.01 if carrying else None,
                        "power_carrying": carrying,
                    } for pol in ("s", "p")
                },
                "order_total_power": 0.02 if carrying else None,
            })
    return {"schema_version": TASK002_OBSERVABLE_SCHEMA_VERSION, "orders": orders}


def test_dataset_roundtrip_hash_split_and_structural_null(tmp_path: Path) -> None:
    samples = []
    for index, split in enumerate(("train_lf", "train_hf", "frozen_validation")):
        samples.append({
            "sample_id": f"s{index}", "source_sha": "c" * 40, "source_dirty": False,
            "status": "measured_pass", "split": split,
            "inputs": [120.0, 17.0, 5.25, 45.0],
            "aggregates": {"R_total": 0.1, "T_total": 0.6, "A_balance": 0.3, "A_volume": 0.3},
            "mother_response": _mother_response(),
        })
    dataset_dir = tmp_path / "dataset"
    result = write_compact_dataset(samples, output_dir=dataset_dir, dataset_id="synthetic")
    assert result["status"] == "pass" and result["sample_count"] == 3
    powers = np.load(dataset_dir / "order_powers.npy", allow_pickle=False)
    mask = np.load(dataset_dir / "power_carrying_mask.npy", allow_pickle=False)
    assert np.array_equal(np.isnan(powers), ~mask)
    assert verify_compact_dataset(dataset_dir) == result
    with (dataset_dir / "sample_records.jsonl").open("a") as stream:
        stream.write("tamper\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_compact_dataset(dataset_dir)


def test_case112_scaffold_contract() -> None:
    record = build_scaffold_record()
    assert all(record["gates"].values())


def test_case113_m2a_scaffold_is_fail_closed() -> None:
    record = build_case113_scaffold()
    assert all(record["scope_gates"].values())
    assert record["raw_evidence_disposition"] == "immutable_reuse"
