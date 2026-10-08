from __future__ import annotations

import copy
import os
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.io import load_and_resolve

ROOT = Path(__file__).resolve().parents[2]
INPUT_ROOT = ROOT / "input/task40extra_0p7nm_engineering"
CASES = (
    (
        "b0_p6_reference_v17.dat",
        "task40extra_v17_p6_y_orbit_b0_reference_v1",
        "task40extra_0p7nm_b0_p6_reference_v17",
        "B0_CANDIDATE",
    ),
    (
        "nonseparable_gx560_p6_reference_v17.dat",
        "task40extra_v17_p6_y_orbit_gx560_reference_v1",
        "task40extra_0p7nm_nonseparable_gx560_p6_reference_v17",
        "Q4_ORIGINAL",
    ),
    (
        "nonseparable_e1_p6_reference_v17.dat",
        "task40extra_v17_p6_y_orbit_e1_reference_v1",
        "task40extra_0p7nm_nonseparable_e1_p6_reference_v17",
        "Q4_ORIGINAL",
    ),
)


@pytest.mark.parametrize("filename,profile_name,run_id,stage", CASES)
def test_v17_profiles_configs_and_checker_inventory_are_exact(
    filename, profile_name, run_id, stage
):
    from src.geometry.task40_nonseparable_plan import TASK40_Q_ASSEMBLY_ROW_TILE_V17
    from src.io.physical_intermediate_profile import profile_facts
    from src.runners.task40_v10_output_checker import _registered_v15_profile_inventory
    from src.solvers.task40_v10_p6_periodic_profile import TASK40_P6_PERIODIC_PROFILES

    payload = load_and_resolve(INPUT_ROOT / filename).as_jsonable()
    facts = profile_facts(profile_name)
    periodic = TASK40_P6_PERIODIC_PROFILES[profile_name]

    assert payload["run_id"] == run_id == facts["run_id"]
    assert payload["solver"]["preconditioner"] == profile_name
    assert payload["solver"]["task40_reference_pc_strategy"] == (
        "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15"
    )
    assert payload["solver"]["task40_q_assembly_strategy"] == (
        TASK40_Q_ASSEMBLY_ROW_TILE_V17
    )
    assert facts["input_path"] == f"input/task40extra_0p7nm_engineering/{filename}"
    assert facts["q_assembly_strategy"] == TASK40_Q_ASSEMBLY_ROW_TILE_V17
    assert facts["stage"] == stage
    assert periodic.q_count == 4
    assert periodic.mode_count == sum(periodic.q_port_counts)
    inventory = _registered_v15_profile_inventory(profile_name)
    assert inventory["identity"] == profile_name
    assert inventory["q_count"] == 4
    assert inventory["q_port_counts"] == tuple(periodic.q_port_counts)

    physical_filename = filename.replace("_v17.dat", "_v15.dat")
    reference = load_and_resolve(INPUT_ROOT / physical_filename).as_jsonable()
    for section in ("geometry", "materials", "incidence", "boundary"):
        assert payload[section] == reference[section]


def test_v18_ny8_profile_config_and_inventory_are_exact():
    from src.geometry.task40_nonseparable_plan import (
        TASK40_B0_P6_V18_Y8_RUN_ID,
        TASK40_Q_ASSEMBLY_ROW_TILE_V17,
        task40_mesh_plan,
    )
    from src.io.physical_intermediate_profile import (
        TASK40_V18_P6_B0_Y8_PROFILE,
        profile_facts,
    )
    from src.runners.task40_v10_output_checker import _registered_v15_profile_inventory
    from src.solvers.task40_v10_p6_periodic_profile import TASK40_P6_PERIODIC_PROFILES

    filename = "b0_p6_reference_v18_ny8.dat"
    payload = load_and_resolve(INPUT_ROOT / filename).as_jsonable()
    profile = TASK40_P6_PERIODIC_PROFILES[TASK40_V18_P6_B0_Y8_PROFILE]
    facts = profile_facts(TASK40_V18_P6_B0_Y8_PROFILE)
    inventory = _registered_v15_profile_inventory(TASK40_V18_P6_B0_Y8_PROFILE)
    mesh = task40_mesh_plan("B0_Y8")

    assert payload["run_id"] == TASK40_B0_P6_V18_Y8_RUN_ID == facts["run_id"]
    assert payload["solver"]["preconditioner"] == TASK40_V18_P6_B0_Y8_PROFILE
    assert payload["solver"]["task40_reference_pc_strategy"] == (
        "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15"
    )
    assert payload["solver"]["task40_q_assembly_strategy"] == TASK40_Q_ASSEMBLY_ROW_TILE_V17
    assert facts["input_path"] == f"input/task40extra_0p7nm_engineering/{filename}"
    assert profile.q_count == inventory["q_count"] == 8
    assert profile.q_port_counts == (76, 76, 76, 76, 0, 76, 76, 76)
    assert inventory["sector_port_counts"] == (76, 152, 152, 152)
    assert payload["discretization"]["mesh_axis_cell_counts"] == [4, 8, 5]
    assert payload["discretization"]["mesh_plan_id"] == mesh["mesh_plan_id"]
    assert payload["discretization"]["mesh_plan_sha256"] == mesh["mesh_plan_sha256"]
    assert payload["discretization"]["mesh_axis_y_values"] == mesh["axis_coordinates_nm"]["y"]
    assert mesh["expected_hexahedra"] == 160


def test_v18_worker_contract_accepts_only_its_ny8_route():
    from src.io.physical_intermediate_profile import (
        TASK40_V18_P6_B0_Y8_PROFILE,
        profile_facts,
    )
    from src.runners import task40_v10_worker
    from src.runners.physical_v14_budget import V14_TIME_POLICY_ENFORCE

    payload = load_and_resolve(
        INPUT_ROOT / "b0_p6_reference_v18_ny8.dat"
    ).as_jsonable()
    window_sha = "a" * 64
    runtime = SimpleNamespace(
        stage="B0_CANDIDATE",
        campaign_context={
            "read_only": True,
            "window_path": "fixed-window.json",
            "window_sha256": window_sha,
            "accounting_path": "accounting.json",
        },
        shared_budget={"campaign_window_sha256": window_sha},
        workflow_reserved_seconds=1000.0,
        require_zero_swap=True,
        _ledger_path=None,
        time_policy=V14_TIME_POLICY_ENFORCE,
    )
    contract = task40_v10_worker._candidate_contract(
        payload,
        profile_facts(TASK40_V18_P6_B0_Y8_PROFILE),
        runtime,
        profile_identity=TASK40_V18_P6_B0_Y8_PROFILE,
    )
    assert contract["schema"] == (
        "task40extra.review_v18_ny8_p6_reference_worker_contract.v1"
    )
    assert contract["checks"] and all(contract["checks"].values())

    payload["run_id"] = "unreviewed_v18_run"
    with pytest.raises(ValueError, match="worker contract failed"):
        task40_v10_worker._candidate_contract(
            payload,
            profile_facts(TASK40_V18_P6_B0_Y8_PROFILE),
            runtime,
            profile_identity=TASK40_V18_P6_B0_Y8_PROFILE,
        )


def test_v18_dispatcher_and_run_case_keep_the_exact_ny8_identity(
    monkeypatch, tmp_path: Path, capsys
):
    from scripts import run_case
    from src.runners import task038_full3d_iterative, task038_launcher
    from src.runners import task40_v10_worker

    input_path = INPUT_ROOT / "b0_p6_reference_v18_ny8.dat"
    payload = load_and_resolve(input_path).as_jsonable()
    captured = {}

    def fake_worker(resolved, run_directory, **kwargs):
        del run_directory
        captured["worker"] = (
            resolved["run_id"],
            kwargs["profile_identity"],
            resolved["solver"]["task40_q_assembly_strategy"],
        )
        return {"status": "dispatch_fixture_pass"}

    monkeypatch.setattr(
        task40_v10_worker,
        "run_task40_v10_p6_reference_worker",
        fake_worker,
    )
    assert task038_full3d_iterative.run_full3d_iterative(
        payload, tmp_path, source_sha="f" * 40
    ) == {"status": "dispatch_fixture_pass"}

    def fake_launcher(specification, **kwargs):
        captured["launcher"] = (
            specification.identity["run_id"],
            specification.solver["preconditioner"],
            kwargs["task40_v10_campaign_window"],
        )
        return {"result_classification": "worker_exit0"}

    monkeypatch.setattr(task038_launcher, "launch_specification", fake_launcher)
    window = tmp_path / "fixed-window.json"
    assert run_case.main(
        [str(input_path), "--task40-v10-campaign-window", str(window)]
    ) == 0
    capsys.readouterr()
    assert captured["worker"] == (
        "task40extra_0p7nm_b0_p6_reference_v18_ny8",
        "task40extra_v18_p6_y_orbit_b0_y8_reference_v1",
        "ROW_TILE_BOUNDED_CSR_V17",
    )
    assert captured["launcher"] == (
        "task40extra_0p7nm_b0_p6_reference_v18_ny8",
        "task40extra_v18_p6_y_orbit_b0_y8_reference_v1",
        window,
    )


def test_v18_launcher_accepts_the_registered_fixed_window_route(
    monkeypatch, tmp_path: Path
):
    from src.runners import task038_launcher, task40_v10_campaign

    specification = load_and_resolve(
        INPUT_ROOT / "b0_p6_reference_v18_ny8.dat"
    )
    reached = []

    class FixedWindowReached(Exception):
        pass

    def stop_at_fixed_window(path):
        reached.append(Path(path))
        raise FixedWindowReached

    monkeypatch.setattr(
        task40_v10_campaign, "load_fixed_campaign_window", stop_at_fixed_window
    )
    window = tmp_path / "fixed-window.json"
    with pytest.raises(FixedWindowReached):
        task038_launcher.launch_specification(
            specification, task40_v10_campaign_window=window
        )
    assert reached == [window]


@pytest.mark.parametrize("filename,profile_name,run_id,stage", CASES)
def test_v17_worker_contract_accepts_only_its_row_tile_route(
    filename, profile_name, run_id, stage
):
    from src.geometry.task40_nonseparable_plan import TASK40_Q_ASSEMBLY_ROW_TILE_V17
    from src.io.physical_intermediate_profile import profile_facts
    from src.runners import task40_v10_worker
    from src.runners.physical_v14_budget import V14_TIME_POLICY_ENFORCE

    del run_id
    payload = load_and_resolve(INPUT_ROOT / filename).as_jsonable()
    window_sha = "a" * 64
    runtime = SimpleNamespace(
        stage=stage,
        campaign_context={
            "read_only": True,
            "window_path": "fixed-window.json",
            "window_sha256": window_sha,
            "accounting_path": "accounting.json",
        },
        shared_budget={"campaign_window_sha256": window_sha},
        workflow_reserved_seconds=1000.0,
        require_zero_swap=True,
        _ledger_path=None,
        time_policy=V14_TIME_POLICY_ENFORCE,
    )
    contract = task40_v10_worker._candidate_contract(
        payload,
        profile_facts(profile_name),
        runtime,
        profile_identity=profile_name,
    )
    assert contract["schema"] == (
        "task40extra.review_v17_row_tile_p6_reference_worker_contract.v1"
    )
    assert contract["checks"] and all(contract["checks"].values())

    payload["solver"]["task40_q_assembly_strategy"] = "BOUNDED_STAGING_CSR_V16"
    with pytest.raises(ValueError):
        task40_v10_worker._candidate_contract(
            payload,
            profile_facts(profile_name),
            runtime,
            profile_identity=profile_name,
        )


@pytest.mark.parametrize("filename,profile_name,run_id,stage", CASES)
def test_v17_dispatcher_calls_worker_with_exact_identity(
    monkeypatch, tmp_path: Path, filename, profile_name, run_id, stage
):
    from src.geometry.task40_nonseparable_plan import TASK40_Q_ASSEMBLY_ROW_TILE_V17
    from src.runners import task038_full3d_iterative, task40_v10_worker

    del stage
    payload = load_and_resolve(INPUT_ROOT / filename).as_jsonable()
    captured = {}

    def fake_worker(resolved, run_directory, **kwargs):
        del run_directory
        captured["run_id"] = resolved["run_id"]
        captured["profile_identity"] = kwargs["profile_identity"]
        captured["q_assembly_strategy"] = resolved["solver"][
            "task40_q_assembly_strategy"
        ]
        return {"status": "dispatch_fixture_pass"}

    monkeypatch.setattr(task40_v10_worker, "run_task40_v10_p6_reference_worker", fake_worker)
    result = task038_full3d_iterative.run_full3d_iterative(
        payload, tmp_path, source_sha="f" * 40
    )
    assert result == {"status": "dispatch_fixture_pass"}
    assert captured == {
        "run_id": run_id,
        "profile_identity": profile_name,
        "q_assembly_strategy": TASK40_Q_ASSEMBLY_ROW_TILE_V17,
    }


@pytest.mark.parametrize("filename,profile_name,run_id,stage", CASES)
def test_v17_run_case_reaches_fixed_window_launcher(
    monkeypatch, tmp_path: Path, capsys,
    filename, profile_name, run_id, stage,
):
    from scripts import run_case
    from src.runners import task038_launcher

    del stage
    captured = {}

    def fake_launcher(specification, **kwargs):
        captured["run_id"] = specification.identity["run_id"]
        captured["profile"] = specification.solver["preconditioner"]
        captured["reference_pc_strategy"] = specification.solver[
            "task40_reference_pc_strategy"
        ]
        captured["q_assembly_strategy"] = specification.solver[
            "task40_q_assembly_strategy"
        ]
        captured["campaign_window"] = kwargs["task40_v10_campaign_window"]
        return {"result_classification": "worker_exit0"}

    monkeypatch.setattr(task038_launcher, "launch_specification", fake_launcher)
    window = tmp_path / "fixed-window.json"
    result = run_case.main([
        str(INPUT_ROOT / filename),
        "--task40-v10-campaign-window",
        str(window),
    ])
    capsys.readouterr()
    assert result == 0
    assert captured == {
        "run_id": run_id,
        "profile": profile_name,
        "reference_pc_strategy": "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15",
        "q_assembly_strategy": "ROW_TILE_BOUNDED_CSR_V17",
        "campaign_window": window,
    }


@pytest.mark.parametrize("filename,profile_name,run_id,stage", CASES)
def test_v17_launcher_admits_exact_fixed_window_before_fe(
    monkeypatch, tmp_path: Path, filename, profile_name, run_id, stage
):
    from src.runners import task038_launcher, task40_v10_campaign

    specification = load_and_resolve(INPUT_ROOT / filename)
    reached = []

    class FixedWindowReached(Exception):
        pass

    def stop_at_fixed_window(path):
        reached.append(Path(path))
        raise FixedWindowReached

    monkeypatch.setattr(
        task40_v10_campaign, "load_fixed_campaign_window", stop_at_fixed_window
    )
    window = tmp_path / "fixed-window.json"
    with pytest.raises(FixedWindowReached):
        task038_launcher.launch_specification(
            specification, task40_v10_campaign_window=window
        )

    assert reached == [window]
    assert specification.identity["run_id"] == run_id
    assert specification.solver["preconditioner"] == profile_name
    assert specification.solver["stage"] == stage


@pytest.mark.parametrize("filename,profile_name,run_id,stage", CASES)
@pytest.mark.parametrize(
    "section,key,value",
    (
        ("identity", "run_id", "unreviewed_v17_run"),
        ("identity", "model_id", "unreviewed_model"),
        ("solver", "preconditioner", "unreviewed_v17_profile"),
        ("solver", "stage", "UNREVIEWED_STAGE"),
        ("solver", "task40_reference_pc_strategy", "STRICT_ONLY"),
        ("solver", "task40_q_assembly_strategy", "BOUNDED_STAGING_CSR_V16"),
    ),
)
def test_v17_launcher_rejects_unreviewed_fixed_window_scope(
    monkeypatch, tmp_path: Path, filename, profile_name, run_id, stage,
    section, key, value,
):
    from src.io.input_loader import InputError
    from src.runners import task038_launcher, task40_v10_campaign

    del profile_name, run_id, stage
    specification = load_and_resolve(INPUT_ROOT / filename)
    identity = dict(specification.identity)
    solver = dict(specification.solver)
    target = identity if section == "identity" else solver
    target[key] = value
    altered = replace(specification, identity=identity, solver=solver)
    monkeypatch.setattr(
        task40_v10_campaign,
        "load_fixed_campaign_window",
        lambda _path: pytest.fail("unreviewed V17 scope reached fixed-window loading"),
    )

    with pytest.raises(InputError, match="fixed campaign window is restricted"):
        task038_launcher.launch_specification(
            altered,
            task40_v10_campaign_window=tmp_path / "fixed-window.json",
        )


def _valid_v17_sector(global_q_indices):
    shapes = {
        "00": [2, 2],
        "01": [2, 3],
        "10": [3, 2],
        "11": [3, 3],
    }
    norms = {"00": 2.0, "01": 1.0e-12, "10": 2.0e-12, "11": 3.0}
    diagonal_scale = max(norms["00"], norms["11"])
    patterns = {
        key: {
            "shape": shape,
            "wide_counts_and_prefix_checked_before_cast": True,
            "full_shape_bitset_bytes": 0,
            "full_coo_list_count": 0,
        }
        for key, shape in shapes.items()
    }
    return {
        "global_q_indices": global_q_indices,
        "assembly_strategy": "ROW_TILE_BOUNDED_CSR_V17",
        "block_shapes": shapes,
        "pattern_facts_by_block": patterns,
        "complete_csr_frobenius_norm_by_block": norms,
        "off_diagonal_relative": {
            "q0_q1_relative": norms["01"] / diagonal_scale,
            "q1_q0_relative": norms["10"] / diagonal_scale,
        },
        "pattern_layout_pass_count": 1,
        "numeric_contribution_pass_count": 1,
        "cartesian_support_pairs_materialized": 0,
        "full_shape_bitset_bytes": 0,
        "full_coo_list_count": 0,
        "global_python_row_set_count": 0,
        "route_query_uses_temporary_sort": False,
        "support_route_spool_removed_after_pattern": True,
        "row_tiles_are_materialized_in_two_descriptor_passes": True,
        "descriptor_replay_regenerates_no_FE_or_Hhat_values": True,
        "all_four_complete_csr_owners_retained_through_norm_gate": True,
        "staging_peak_bytes_total_all_blocks": 4096,
        "staging_budget_bytes_total_all_q_blocks": 256 * 1024**2,
        "final_four_block_csr_payload_bytes": 8192,
        "final_csr_payload_bytes_total": 8192,
        "temporary_filesystem_free_space_reserve_bytes": 256 * 1024**2,
        "temporary_filesystem_free_bytes_minimum_observed": 2 * 1024**3,
    }


def _valid_v17_summary():
    from src.io.physical_intermediate_profile import TASK40_V17_P6_B0_PROFILE

    return {
        "q_assembly_strategy": "ROW_TILE_BOUNDED_CSR_V17",
        "profile": TASK40_V17_P6_B0_PROFILE,
        "source_sha": "a" * 40,
        "reference_audit_snapshot": {
            "sector_audits_before_destroy": [
                _valid_v17_sector([0, 2]),
                _valid_v17_sector([1, 3]),
            ]
        },
    }


def test_v17_checker_recomputes_offdiagonal_ratios_and_labels_its_scope(tmp_path: Path):
    from src.runners.task40_v10_output_checker import _verify_v17_row_tile_assembly_summary

    result = _verify_v17_row_tile_assembly_summary(tmp_path, _valid_v17_summary())
    assert result["passed"] is True
    assert result["off_diagonal_recomputed_from_saved_complete_csr_norms"] is True
    assert result["operator_reapplied_by_checker"] is False
    assert "did not reapply" in result["checker_scope"]
    assert "sum_final_four_block_csr_payload_bytes_across_sequential_sectors" in result


def test_v17_checker_rejects_tampered_norms_and_unregistered_profile(tmp_path: Path):
    from src.runners.task40_v10_output_checker import _verify_v17_row_tile_assembly_summary

    tampered = _valid_v17_summary()
    tampered_sector = tampered["reference_audit_snapshot"]["sector_audits_before_destroy"][0]
    tampered_sector["complete_csr_frobenius_norm_by_block"]["01"] = 1.0e-8
    with pytest.raises(ValueError, match="off-diagonal"):
        _verify_v17_row_tile_assembly_summary(tmp_path, tampered)

    altered_profile = copy.deepcopy(_valid_v17_summary())
    altered_profile["profile"] = "task40extra_v17_p6_y_orbit_unregistered_v1"
    with pytest.raises(ValueError, match="exact registered V17 profile"):
        _verify_v17_row_tile_assembly_summary(tmp_path, altered_profile)


def test_v18_row_tile_checker_covers_all_eight_q_branches(tmp_path: Path):
    from src.io.physical_intermediate_profile import TASK40_V18_P6_B0_Y8_PROFILE
    from src.runners.task40_v10_output_checker import _verify_v17_row_tile_assembly_summary

    summary = {
        "q_assembly_strategy": "ROW_TILE_BOUNDED_CSR_V17",
        "profile": TASK40_V18_P6_B0_Y8_PROFILE,
        "source_sha": "b" * 40,
        "reference_audit_snapshot": {
            "sector_audits_before_destroy": [
                _valid_v17_sector([0, 1]),
                _valid_v17_sector([2, 3]),
                _valid_v17_sector([4, 5]),
                _valid_v17_sector([6, 7]),
            ]
        },
    }
    result = _verify_v17_row_tile_assembly_summary(tmp_path, summary)
    assert result["passed"] is True
    assert result["schema"] == "task40extra.review_v18_ny8_row_tile_assembly_checker.v1"
    assert result["sector_count"] == 4
    assert result["covered_q"] == list(range(8))


def test_v18_operator_checker_recomputes_64_block_and_eight_schur_gates():
    import hashlib
    import json

    from src.io.physical_intermediate_profile import TASK40_V18_P6_B0_Y8_PROFILE
    from src.runners.task40_v10_output_checker import (
        _registered_v15_profile_inventory,
        _verify_v18_ny8_operator_qualification,
    )

    inventory = _registered_v15_profile_inventory(TASK40_V18_P6_B0_Y8_PROFILE)
    q_count = inventory["q_count"]
    width = inventory["global_independent_rows"] // q_count
    block_shapes = {
        f"{p}{q}": [
            width + inventory["q_port_counts"][p],
            width + inventory["q_port_counts"][q],
        ]
        for p in range(q_count)
        for q in range(q_count)
    }
    offdiagonal_keys = {
        f"{p}{q}" for p in range(q_count) for q in range(q_count) if p != q
    }
    operator = {
        "schema": "task40extra.review_v18_complete_ny_reference_operator.v1",
        "status": "PASS",
        "passed": True,
        "ny": 8,
        "translation_count_K": 4,
        "local_y_cells_ell": 2,
        "native_independent_rows": inventory["global_independent_rows"],
        "full_q_block_coverage_count": 64,
        "expected_full_q_block_coverage_count": 64,
        "all_ordered_q_blocks_covered": True,
        "q_port_counts": list(inventory["q_port_counts"]),
        "empty_port_q_indices": [4],
        "q4_nonzero_fe_rhs_norm": 1.0,
        "q4_nonzero_fe_rhs_witness_passed": True,
        "q4_zero_port_nonzero_fe_gate_passed": True,
        "mode_identities_covered_once": True,
        "complex_nonhermitian_reference_witness_relative": 2.0e-12,
        "complex_nonhermitian_reference_witness_passed": True,
        "complex_material_volume_imaginary_nnz": 1,
        "complex_material_volume_witness_passed": True,
        "original_H_mode_count": inventory["mode_count"],
        "original_H_minimum": 1.0,
        "original_H_maximum": 2.0,
        "global_y_phase": [0.0, 1.0],
        "global_y_phase_distance_from_one": 2.0**0.5,
        "mapping_limit": 1.0e-12,
        "operator_limit": 1.0e-11,
        "q_dft_unitarity_frobenius_defect": 0.0,
        "offdiagonal_diagonal_frobenius_scale": 1.0,
        "complete_augmented_diagonal_frobenius_by_q": {
            str(q): 1.0 for q in range(q_count)
        },
        "offdiagonal_frobenius_by_block": {key: 0.0 for key in offdiagonal_keys},
        "offdiagonal_relative_by_block": {key: 0.0 for key in offdiagonal_keys},
        "maximum_complete_offdiagonal_relative": 0.0,
        "independent_schur_relative_by_q": {str(q): 0.0 for q in range(q_count)},
        "independent_schur_norms_by_q": {
            str(q): {
                "independent_schur_frobenius": 1.0,
                "candidate_csr_frobenius": 1.0,
                "complete_difference_frobenius": 0.0,
            }
            for q in range(q_count)
        },
        "maximum_independent_schur_relative": 0.0,
        "complete_q_block_shapes": block_shapes,
    }
    digest = hashlib.sha256(
        json.dumps(operator, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    summary = {
        "complete_operator_qualification_sha256": digest,
        "reference_audit_snapshot": {"complete_operator_qualification": operator},
    }
    result = _verify_v18_ny8_operator_qualification(summary, inventory)
    assert result["passed"] is True
    assert result["complete_q_block_count"] == 64
    assert result["independent_schur_q_count"] == 8

    tampered = copy.deepcopy(summary)
    tampered["reference_audit_snapshot"]["complete_operator_qualification"][
        "independent_schur_norms_by_q"
    ]["4"]["complete_difference_frobenius"] = 1.0e-5
    with pytest.raises(ValueError, match="identity hash"):
        _verify_v18_ny8_operator_qualification(tampered, inventory)

    denominator_tampered = copy.deepcopy(summary)
    denominator_operator = denominator_tampered["reference_audit_snapshot"][
        "complete_operator_qualification"
    ]
    denominator_operator["complete_augmented_diagonal_frobenius_by_q"]["4"] = 2.0
    denominator_tampered["complete_operator_qualification_sha256"] = hashlib.sha256(
        json.dumps(
            denominator_operator,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="diagonal scale"):
        _verify_v18_ny8_operator_qualification(denominator_tampered, inventory)


@pytest.mark.parametrize("filename,profile_name,run_id,stage", CASES)
def test_v17_profiles_are_in_the_exact_local_abi_allowlist(
    filename, profile_name, run_id, stage
):
    del filename, run_id, stage
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        pytest.skip("requires the existing qualified local Task40 ABI activation")
    from src.runners.task40_v10_abi import qualified_task40_v10_abi

    facts = qualified_task40_v10_abi(profile_identity=profile_name)
    assert facts["qualification"] == "task40_v10_exact_profile_receipt_bound"
    assert facts["profile_identity"] == profile_name
    assert facts["scalar"] == "complex128"
    assert facts["integer"] == "int32"
    assert facts["mpi_size"] == 1


@pytest.mark.parametrize("filename,profile_name,run_id,stage", CASES)
def test_v17_v14_runtime_uses_existing_readonly_campaign_window_without_fe(
    monkeypatch, tmp_path: Path, filename, profile_name, run_id, stage
):
    del filename, run_id
    from src.io.physical_intermediate_profile import profile_facts
    from src.runners.physical_p4_schur_v14 import _V14Runtime
    from src.runners.task40_v10_campaign import load_fixed_campaign_window

    window_path = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w17_wsl/campaign_window_v17.json"
    accounting_path = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w17_wsl/campaign_accounting_v10.jsonl"
    original_window = window_path.read_bytes()
    original_accounting = accounting_path.read_bytes()
    window = load_fixed_campaign_window(window_path)
    assert window.sha256 == "83f47e542dc28309d398a55c6b7e1b1ca76dab25dead854d88cc6feb6758ed24"
    assert window.payload["t0_utc"] == "2026-10-08T00:38:07.073088478Z"
    assert window.payload["deadline_utc"] == "2026-10-09T00:38:07.073088478Z"
    monkeypatch.setenv("TASK40_V10_CAMPAIGN_WINDOW", str(window_path))
    monkeypatch.setenv("TASK40_V10_CAMPAIGN_WINDOW_SHA256", window.sha256)
    monkeypatch.setenv("TASK40_V10_CAMPAIGN_ACCOUNTING", str(accounting_path))
    monkeypatch.setenv("PHYSICAL_WATCHDOG_PHASE_PATH", str(tmp_path / "workflow_phase.json"))

    contract = profile_facts(profile_name)
    resources = contract["resources"]
    if "pss_sampling_policy" in resources:
        monkeypatch.setenv("PHYSICAL_WATCHDOG_PSS_POLICY", resources["pss_sampling_policy"])
    if "watchdog_memory_policy" in resources:
        monkeypatch.setenv("PHYSICAL_WATCHDOG_MEMORY_POLICY", resources["watchdog_memory_policy"])
    case_label = "b0" if stage == "B0_CANDIDATE" else "gx560" if "gx560" in profile_name else "e1"
    source_sha = "a" * 40
    runtime = _V14Runtime(
        tmp_path,
        stage,
        contract,
        root=ROOT,
        source_sha=source_sha,
        batch_identity=f"task40_review_v17_{case_label}_p6_reference",
        evidence_prefix="v17_runtime_fixture",
    )

    assert runtime.source_sha == source_sha
    assert runtime.stage == stage
    assert runtime.contract["identity"] == profile_name
    assert runtime.contract["scope"].startswith("review_v17_row_tile_")
    assert runtime.campaign_context["read_only"] is True
    assert runtime.campaign_context["window_sha256"] == window.sha256
    assert runtime.campaign_context["accounting_path"] == str(accounting_path.resolve())
    assert runtime.shared_budget["schema"] == "task40extra.review_v17_campaign_worker_view.v1"
    assert runtime.shared_budget["batch_identity"] == f"task40_review_v17_{case_label}_p6_reference"
    assert runtime.shared_budget["total_budget_seconds"] == 86400.0
    assert runtime.shared_budget["remaining_numerical_seconds_at_worker_entry"] > 0.0
    assert runtime.workflow_reserved_seconds == runtime.shared_budget[
        "remaining_numerical_seconds_at_worker_entry"
    ]
    assert runtime.workflow_clock_start["boot_id"] == window.anchor["boot_id"]
    assert runtime.shared_attempt["source_sha"] == source_sha
    assert runtime.workflow_clock_source == "task40_v17_fixed_campaign_read_only_projection"
    assert window_path.read_bytes() == original_window
    assert accounting_path.read_bytes() == original_accounting


def test_v17_v14_runtime_rejects_unregistered_scope_before_reading_campaign(
    monkeypatch, tmp_path: Path
):
    from src.io.physical_intermediate_profile import TASK40_V17_P6_B0_PROFILE, profile_facts
    from src.runners.physical_p4_schur_v14 import _V14Runtime

    contract = profile_facts(TASK40_V17_P6_B0_PROFILE)
    contract["scope"] = "review_v17_row_tile_b0_unregistered_scope"
    window_path = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w17_wsl/campaign_window_v17.json"
    accounting_path = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w17_wsl/campaign_accounting_v10.jsonl"
    monkeypatch.setenv("TASK40_V10_CAMPAIGN_WINDOW", str(window_path))
    monkeypatch.setenv(
        "TASK40_V10_CAMPAIGN_WINDOW_SHA256",
        "83f47e542dc28309d398a55c6b7e1b1ca76dab25dead854d88cc6feb6758ed24",
    )
    monkeypatch.setenv("TASK40_V10_CAMPAIGN_ACCOUNTING", str(accounting_path))
    with pytest.raises(RuntimeError, match="rejected this exact stage/profile/scope"):
        _V14Runtime(
            tmp_path,
            "B0_CANDIDATE",
            contract,
            root=ROOT,
            source_sha="a" * 40,
            batch_identity="task40_review_v17_b0_p6_reference",
            evidence_prefix="v17_runtime_negative",
        )


def test_v18_v14_runtime_uses_existing_fixed_campaign_window_without_fe(
    monkeypatch, tmp_path: Path
):
    from src.io.physical_intermediate_profile import TASK40_V18_P6_B0_Y8_PROFILE, profile_facts
    from src.runners.physical_p4_schur_v14 import _V14Runtime
    from src.runners.task40_v10_campaign import load_fixed_campaign_window

    window_path = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w17_wsl/campaign_window_v17.json"
    accounting_path = ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w17_wsl/campaign_accounting_v10.jsonl"
    original_window = window_path.read_bytes()
    original_accounting = accounting_path.read_bytes()
    window = load_fixed_campaign_window(window_path)
    assert window.sha256 == "83f47e542dc28309d398a55c6b7e1b1ca76dab25dead854d88cc6feb6758ed24"
    monkeypatch.setenv("TASK40_V10_CAMPAIGN_WINDOW", str(window_path))
    monkeypatch.setenv("TASK40_V10_CAMPAIGN_WINDOW_SHA256", window.sha256)
    monkeypatch.setenv("TASK40_V10_CAMPAIGN_ACCOUNTING", str(accounting_path))
    monkeypatch.setenv("PHYSICAL_WATCHDOG_PHASE_PATH", str(tmp_path / "workflow_phase.json"))

    contract = profile_facts(TASK40_V18_P6_B0_Y8_PROFILE)
    resources = contract["resources"]
    if "pss_sampling_policy" in resources:
        monkeypatch.setenv("PHYSICAL_WATCHDOG_PSS_POLICY", resources["pss_sampling_policy"])
    if "watchdog_memory_policy" in resources:
        monkeypatch.setenv("PHYSICAL_WATCHDOG_MEMORY_POLICY", resources["watchdog_memory_policy"])
    runtime = _V14Runtime(
        tmp_path,
        "B0_CANDIDATE",
        contract,
        root=ROOT,
        source_sha="b" * 40,
        batch_identity="task40_review_v18_b0_y8_p6_reference",
        evidence_prefix="v18_runtime_fixture",
    )

    assert runtime.contract["identity"] == TASK40_V18_P6_B0_Y8_PROFILE
    assert runtime.contract["scope"] == (
        "review_v18_ny8_row_tile_b0_y8_full_p6_y_orbit_reference_inverse"
    )
    assert runtime.campaign_context["read_only"] is True
    assert runtime.campaign_context["window_sha256"] == window.sha256
    assert runtime.campaign_context["accounting_path"] == str(accounting_path.resolve())
    assert runtime.shared_budget["campaign_window_sha256"] == window.sha256
    assert runtime.shared_budget["batch_identity"] == "task40_review_v18_b0_y8_p6_reference"
    assert runtime.shared_budget["total_budget_seconds"] == 86400.0
    assert runtime.shared_budget["remaining_numerical_seconds_at_worker_entry"] > 0.0
    assert runtime.workflow_reserved_seconds == runtime.shared_budget[
        "remaining_numerical_seconds_at_worker_entry"
    ]
    assert window_path.read_bytes() == original_window
    assert accounting_path.read_bytes() == original_accounting


def test_v18_v14_runtime_rejects_wrong_scope_before_reading_campaign(
    monkeypatch, tmp_path: Path
):
    from src.io.physical_intermediate_profile import TASK40_V18_P6_B0_Y8_PROFILE, profile_facts
    from src.runners import task40_v10_campaign
    from src.runners.physical_p4_schur_v14 import _V14Runtime

    contract = profile_facts(TASK40_V18_P6_B0_Y8_PROFILE)
    contract["scope"] = "review_v18_ny8_row_tile_b0_y8_wrong_scope"
    monkeypatch.setenv(
        "TASK40_V10_CAMPAIGN_WINDOW",
        str(ROOT / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w17_wsl/campaign_window_v17.json"),
    )
    monkeypatch.setattr(
        task40_v10_campaign,
        "load_fixed_campaign_window",
        lambda *_args, **_kwargs: pytest.fail("wrong scope reached the campaign window"),
    )
    with pytest.raises(RuntimeError, match="rejected this exact stage/profile/scope"):
        _V14Runtime(
            tmp_path,
            "B0_CANDIDATE",
            contract,
            root=ROOT,
            source_sha="c" * 40,
            batch_identity="task40_review_v18_wrong_scope",
            evidence_prefix="v18_runtime_negative",
        )
