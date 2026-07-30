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
from src.forward_data.task002_campaign import (
    _atomic_write, _parser, campaign_status, load_manifest,
    recover_or_retry_row, register_design, run_design, task002_hybrid_command,
)
from src.forward_data.task002_dataset import verify_compact_dataset, write_compact_dataset
from src.forward_data.task002_dataset_checker import verify_exact_design_dataset
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
from src.forward_data.task002_m3r_design import freeze_all_designs
from src.forward_data.task002_m4 import (
    audit_rebind, design_point_hash, formal_record_to_production_sample,
    rebind_frozen_designs,
)
from src.forward_data.task002_runtime_topology import planned_runtime_identity
from src.forward_data.task002_full3d import (
    AXIS_CELL_COUNTS, build_task002_full3d_config, task002_full3d_command,
    task002_full3d_config_identity, task002_full3d_topology_identity,
)
from src.forward_data.task002_schema import (
    TASK002_FIXED_M_ORDERS, TASK002_OBSERVABLE_SCHEMA_VERSION,
    Task002ForwardParameters,
    classify_task002_request, task002_parameter_catalog,
)


PROD = "S_PROD_FULL3D_STATIC_P5_H10_NY4"


def _parameters(**updates) -> Task002ForwardParameters:
    values = dict(
        height_nm=120.0, width_x_nm=17.0, grazing_deg=5.25,
        azimuth_deg=45.0, model_id=PROD,
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
    assert set(audit["propagating_m_union"]).issubset(TASK002_FIXED_M_ORDERS)
    cutoff = cutoff_diagnostics(_parameters(grazing_deg=0.5, azimuth_deg=0.0))
    assert cutoff["cutoff_metric"] >= 0.0
    assert len(cutoff["orders"]) == len(TASK002_FIXED_M_ORDERS)


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
            _parameters(model_id=PROD), root=tmp_path, baseline_sha="a" * 40,
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
    assert command[-2:] == ["--output-profile", "compact_surrogate_record"]
    parameters = _parameters()
    cfg = build_task002_full3d_config(parameters)
    topology = task002_full3d_topology_identity(parameters)
    assert cfg.mesh_axis_cell_counts == AXIS_CELL_COUNTS
    assert cfg.nedelec_degree == 5
    assert cfg.nedelec_trace_degree is None
    assert cfg.nedelec_interior_degree is None
    assert topology["element_identity"]["family"] == "N1curl"
    assert topology["element_identity"]["degree"] == 5
    compact_cfg = build_task002_full3d_config(
        parameters, output_profile="compact_surrogate_record",
    )
    assert compact_cfg.task002_output_profile == "compact_surrogate_record"
    runtime_plan = planned_runtime_identity(parameters)
    assert runtime_plan["axis_cell_counts"] == [6, 4, 14]
    assert runtime_plan["expected_global_dof_count"] == 134320
    for diagnostic in (
        "S_DIAG_FULL3D_STATIC_P4_H10", "S_LF_FULL3D_STATIC_P4_H10",
        "S_HF_FULL3D_STATIC_P5_H10", "S_LF_HYBRID_P4_H10_M120",
    ):
        with pytest.raises(ValueError, match="p5-only"):
            _parameters(model_id=diagnostic).validate()


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


def test_campaign_cli_is_design_bound_and_has_no_manual_run_one(tmp_path: Path) -> None:
    args = _parser().parse_args([
        "run-design", "--root", str(tmp_path), "--baseline-sha", "a" * 40,
        "--design", str(tmp_path / "training.json"), "--split", "train",
        "--artifact-root", str(tmp_path / "artifacts"),
        "--campaign-manifest", str(tmp_path / "campaign.json"),
        "--role", "domain_corner",
    ])
    assert args.command == "run-design" and args.role == "domain_corner"
    with pytest.raises(SystemExit):
        _parser().parse_args(["run-one"])


def test_campaign_registration_stale_retry_recovery_and_immutability(tmp_path: Path) -> None:
    source_sha = "a" * 40
    design = freeze_all_designs(source_sha)["training_design.json"]
    design_path = tmp_path / "training_design.json"
    design_path.write_text(json.dumps(design))
    manifest_path = tmp_path / "campaign.json"
    manifest = load_manifest(manifest_path, baseline_sha=source_sha)
    register_design(manifest, design=design, design_path=design_path, split="train")
    _atomic_write(manifest_path, manifest)
    assert len(manifest["samples"]) == 96
    row = manifest["samples"][f"{design['design_id']}:0000"]
    assert recover_or_retry_row(row) == "interrupted_retryable"
    run = tmp_path / "attempt"
    (run / "results").mkdir(parents=True)
    (run / "results/task002_full3d_record.json").write_text(json.dumps({"gates": {"x": True}}))
    (run / "execution.json").write_text(json.dumps({"watchdog": {
        "status": "completed", "return_code": 0, "peak_swap_bytes": 0,
        "cleanup_complete": True,
    }}))
    row.update({"run_directory": str(run), "status": "running",
                "attempts": [{"status": "running"}]})
    assert recover_or_retry_row(row) == "measured_pass"
    assert recover_or_retry_row(row) == "measured_pass"
    assert campaign_status(manifest)["status_counts"]["measured_pass"] == 1
    with pytest.raises(ValueError, match="baseline"):
        load_manifest(manifest_path, baseline_sha="b" * 40)


def test_campaign_preflight_exception_is_persisted_as_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_sha = "a" * 40
    design = freeze_all_designs(source_sha)["training_design.json"]
    design_path = tmp_path / "training_design.json"
    design_path.write_text(json.dumps(design))
    manifest_path = tmp_path / "campaign.json"

    def refuse_preflight(*args, **kwargs):
        raise RuntimeError("Task002 resource preflight failed: swap_unused")

    monkeypatch.setattr(
        "src.forward_data.task002_full3d.run_formal_task002_full3d",
        refuse_preflight,
    )
    args = _parser().parse_args([
        "run-design", "--root", str(tmp_path), "--baseline-sha", source_sha,
        "--design", str(design_path), "--split", "train",
        "--artifact-root", str(tmp_path / "artifacts"),
        "--campaign-manifest", str(manifest_path),
        "--start-index", "0", "--stop-index", "1",
    ])
    assert run_design(args) == 3
    manifest = json.loads(manifest_path.read_text())
    row = manifest["samples"][f"{design['design_id']}:0000"]
    assert row["status"] == "interrupted_retryable"
    assert row["attempts"][-1]["status"] == "interrupted_retryable"
    assert "swap_unused" in row["attempts"][-1]["preflight_error"]
    assert manifest["stop_reason"].startswith("preflight_interruption:")


def _mother_response() -> dict:
    orders = []
    for side in ("reflection", "transmission"):
        for m in TASK002_FIXED_M_ORDERS:
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
    return {
        "schema_version": TASK002_OBSERVABLE_SCHEMA_VERSION, "orders": orders,
        "uncovered_power_carrying_n0": [],
        "leakage": {
            "n_nonzero_reflection_power_sum": 0.0,
            "n_nonzero_transmission_power_sum": 0.0,
            "n_nonzero_max_abs_amplitude": 0.0,
        },
        "power_ledger": {
            "raw_R_minus_fixed_n0_R_minus_n_nonzero_R": 0.0,
            "raw_T_minus_fixed_n0_T_minus_n_nonzero_T": 0.0,
        },
    }


def _passing_sample_gates() -> dict:
    return {
        "numerical_gates": {"all": True},
        "resource_gates": {"all": True},
    }


def test_dataset_roundtrip_hash_split_and_structural_null(tmp_path: Path) -> None:
    samples = []
    for index, split in enumerate(("train", "frozen_validation")):
        samples.append({
            "sample_id": f"s{index}", "source_sha": "c" * 40, "source_dirty": False,
            "status": "measured_pass", "split": split,
            "model_id": PROD,
            "axis_cell_counts": [6, 4, 14],
            "solver_route_id": "full3d_static_uniform_n1curl_p5_h10_ny4",
            "inputs": [120.0, 17.0, 5.25, 45.0],
            "aggregates": {"R_total": 0.1, "T_total": 0.6, "A_balance": 0.3, "A_volume": 0.3},
            "mother_response": _mother_response(),
            **_passing_sample_gates(),
        })
    dataset_dir = tmp_path / "dataset"
    result = write_compact_dataset(samples, output_dir=dataset_dir, dataset_id="synthetic")
    assert result["status"] == "pass" and result["sample_count"] == 2
    powers = np.load(dataset_dir / "order_powers.npy", allow_pickle=False)
    mask = np.load(dataset_dir / "power_carrying_mask.npy", allow_pickle=False)
    assert np.array_equal(np.isnan(powers), ~mask)
    assert verify_compact_dataset(dataset_dir) == result
    with (dataset_dir / "sample_records.jsonl").open("a") as stream:
        stream.write("tamper\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_compact_dataset(dataset_dir)


def test_dataset_rejects_failed_and_nonproduction_solver_routes(tmp_path: Path) -> None:
    sample = {
        "sample_id": "failed", "source_sha": "c" * 40, "source_dirty": False,
        "status": "failed_numerical_gate", "split": "train",
        "model_id": PROD,
        "axis_cell_counts": [6, 4, 14],
        "solver_route_id": "full3d_static_uniform_n1curl_p5_h10_ny4",
        "inputs": [120.0, 17.0, 5.25, 45.0],
        "aggregates": {"R_total": 0.1, "T_total": 0.6, "A_balance": 0.3, "A_volume": 0.3},
        "mother_response": _mother_response(),
        **_passing_sample_gates(),
    }
    with pytest.raises(ValueError, match="measured_pass"):
        write_compact_dataset([sample], output_dir=tmp_path / "failed", dataset_id="failed")
    sample["status"] = "measured_pass"
    sample["solver_route_id"] = "full3d_static_uniform_n1curl_p4_h10"
    with pytest.raises(ValueError, match="Ny4"):
        write_compact_dataset([sample], output_dir=tmp_path / "mixed", dataset_id="mixed")


def test_formal_record_adapter_is_design_bound(tmp_path: Path) -> None:
    formal = tmp_path / "task002_full3d_record.json"
    execution = tmp_path / "execution.json"
    point = {"height_nm": 120.0, "width_x_nm": 17.0, "grazing_deg": 5.25,
             "azimuth_deg": 45.0, "model_id": PROD,
             "solver_route_id": "full3d_static_uniform_n1curl_p5_h10_ny4"}
    row = {
        "design_id": "task002_p5_initial_training_v1", "design_index": 0,
        "split": "train", "point_tuple": [120.0, 17.0, 5.25, 45.0],
        "point_hash": design_point_hash(
            design_id="task002_p5_initial_training_v1", design_index=0, point=point,
        ), "source_sha": "e" * 40, "status": "measured_pass",
    }
    formal.write_text(json.dumps({
        "source_sha": "e" * 40, "model_id": PROD,
        "solver_route_id": point["solver_route_id"],
        "output_profile": "compact_surrogate_record", "parameter_hash": "p",
        "config_identity": {"config_sha256": "c"},
        "planned_topology_identity": {"topology_element_hash": "t", "axis_cell_counts": [6, 4, 14]},
        "actual_runtime_topology_identity": {"actual": True, "axis_cell_counts": [6, 4, 14]},
        "artifact_hashes": {}, "gates": {"all": True},
        "parameters": {"geometry": {"height_nm": 120.0, "width_x_nm": 17.0},
                       "configuration": {"grazing_deg": 5.25, "azimuth_deg": 45.0}},
        "observables": {"R_total": 0.1, "T_total": 0.6, "A_balance": 0.3,
                        "A_volume": 0.3, "mother_response": _mother_response()},
    }))
    execution.write_text(json.dumps({"watchdog": {
        "status": "completed", "return_code": 0, "peak_swap_bytes": 0,
        "cleanup_complete": True,
    }}))
    sample = formal_record_to_production_sample(
        manifest_row=row, formal_record_path=formal, execution_path=execution,
    )
    assert sample["design_index"] == 0 and sample["source_sha"] == "e" * 40
    row["point_tuple"][0] = 119.0
    with pytest.raises(ValueError, match="tuple"):
        formal_record_to_production_sample(
            manifest_row=row, formal_record_path=formal, execution_path=execution,
        )


def test_independent_dataset_checker_requires_exact_96_plus_16(tmp_path: Path) -> None:
    source_sha = "f" * 40
    designs = freeze_all_designs(source_sha)
    train_path = tmp_path / "training.json"
    validation_path = tmp_path / "validation.json"
    train_path.write_text(json.dumps(designs["training_design.json"]))
    validation_path.write_text(json.dumps(designs["frozen_validation_design.json"]))
    samples = []
    for name, split in (("training_design.json", "train"),
                        ("frozen_validation_design.json", "frozen_validation")):
        design = designs[name]
        for index, point in enumerate(design["points"]):
            inputs = [float(point[key]) for key in (
                "height_nm", "width_x_nm", "grazing_deg", "azimuth_deg",
            )]
            samples.append({
                "sample_id": f"{split}-{index}", "design_id": design["design_id"],
                "design_index": index, "point_hash": design_point_hash(
                    design_id=design["design_id"], design_index=index, point=point,
                ), "source_sha": source_sha, "source_dirty": False,
                "status": "measured_pass", "split": split,
                "model_id": PROD,
                "axis_cell_counts": [6, 4, 14],
                "solver_route_id": "full3d_static_uniform_n1curl_p5_h10_ny4",
                "inputs": inputs,
                "aggregates": {"R_total": 0.1, "T_total": 0.6,
                               "A_balance": 0.3, "A_volume": 0.3},
                "mother_response": _mother_response(), **_passing_sample_gates(),
            })
    dataset = tmp_path / "dataset"
    write_compact_dataset(samples, output_dir=dataset, dataset_id="exact-synthetic")
    result = verify_exact_design_dataset(
        dataset, training_design_path=train_path,
        validation_design_path=validation_path, baseline_sha=source_sha,
    )
    assert result["training_count"] == 96
    assert result["frozen_validation_count"] == 16


def test_m3r_designs_are_deterministic_hash_bound_and_production_disjoint() -> None:
    source_sha = "d" * 40
    first = freeze_all_designs(source_sha)
    repeated = freeze_all_designs(source_sha)
    assert first == repeated
    assert first["training_design.json"]["point_count"] == 96
    assert first["frozen_validation_design.json"]["point_count"] == 16
    assert first["candidate_pool.json"]["point_count"] == 4096
    assert 6 <= first["discretization_audit_design.json"]["point_count"] <= 10
    intersections = first["split_hashes.json"]["intersection_audit"]
    assert intersections["training_validation"] == []
    assert intersections["training_candidate"] == []
    assert intersections["validation_candidate"] == []
    for value in first.values():
        assert value["source_sha"] == source_sha


def test_m4_design_rebind_changes_metadata_not_tuples(tmp_path: Path) -> None:
    old_sha, new_sha = "1" * 40, "2" * 40
    old = freeze_all_designs(old_sha)
    source = tmp_path / "old"
    rebound = tmp_path / "new"
    source.mkdir()
    for name, value in old.items():
        (source / name).write_text(json.dumps(value))
    record = rebind_frozen_designs(
        source_dir=source, output_dir=rebound, baseline_sha=new_sha,
    )
    new = {name: json.loads((rebound / name).read_text()) for name in old}
    assert record["pass"] and audit_rebind(old, new)["pass"]
    assert new["training_design.json"]["source_sha"] == new_sha
    assert old["training_design.json"]["points"] == new["training_design.json"]["points"]


def test_case112_scaffold_contract() -> None:
    record = build_scaffold_record()
    assert all(record["gates"].values())


def test_case113_m2a_scaffold_is_fail_closed() -> None:
    record = build_case113_scaffold()
    assert all(record["scope_gates"].values())
    assert record["raw_evidence_disposition"] == "immutable_reuse"
