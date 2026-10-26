from __future__ import annotations

import copy
from functools import wraps
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks.task43_hp_adaptivity import compare_round1_candidate as comparison
from benchmarks.task43_hp_adaptivity import candidate_checkpoints
from benchmarks.task43_hp_adaptivity import h100_anchor
from benchmarks.task43_hp_adaptivity import round1_candidates
from benchmarks.task43_hp_adaptivity.candidate_checkpoints import (
    task43_v11_partial_terminal_record,
    write_v11_primary_field_sample,
    write_v11_primary_packet,
)
from src.postprocessing.physical_field_comparison import build_common_volume_quadrature


CONTRACT_PATH = Path(
    "docs/task43_hp_adaptivity/outcomes/records/v11_scientific_restart_contract.json"
)
SELECTION_PATH = Path(
    "docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json"
)
ACCEPTANCE_PATH = Path(
    "docs/task43_hp_adaptivity/outcomes/records/round1_acceptance_contract_v1.json"
)


def _contract() -> dict:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _raw_vectors(*, failed_condensed: bool = False) -> dict[str, np.ndarray]:
    residual = np.asarray([1.0 if failed_condensed else 0.0], dtype=np.complex128)
    return {
        "independent_A6_independent_active_residual_trace": np.zeros(1, dtype=np.complex128),
        "independent_A6_independent_active_residual_cell_interior": np.zeros(1, dtype=np.complex128),
        "independent_A6_independent_active_modal_lower_solver_gauge": np.zeros(612, dtype=np.complex128),
        "independent_A6_independent_active_rhs_trace": np.ones(1, dtype=np.complex128),
        "independent_A6_independent_active_rhs_cell_interior": np.ones(1, dtype=np.complex128),
        "full_active_reduced_trace_dtn_residual_Ax_minus_b_owned": np.zeros(613, dtype=np.complex128),
        "full_active_reduced_trace_dtn_residual_trace_metric_action": np.zeros(1, dtype=np.complex128),
        "full_active_reduced_trace_dtn_rhs_owned": np.zeros(613, dtype=np.complex128),
        "full_active_reduced_trace_dtn_rhs_trace_metric_action": np.zeros(1, dtype=np.complex128),
        "full_active_active_full_rhs": np.asarray([0.0, 0.0, 1.0], dtype=np.complex128),
        "full_active_active_full_solution": np.zeros(3, dtype=np.complex128),
        "full_active_eliminated_active_interior_residual": np.zeros(3, dtype=np.complex128),
        "recovered_active_full_rhs_owned": np.asarray([0.0, 0.0, 1.0], dtype=np.complex128),
        "recovered_active_full_solution_owned": np.zeros(3, dtype=np.complex128),
        "returned_trace_dtn_rhs": np.ones(613, dtype=np.complex128),
        "returned_trace_dtn_solution": np.ones(613, dtype=np.complex128),
        "returned_trace_dtn_b_minus_Ax": np.pad(residual, (0, 612)),
        "normal_before_normal_correction_rhs": np.ones(613, dtype=np.complex128),
        "normal_after_normal_correction_rhs": np.ones(613, dtype=np.complex128),
        "normal_before_normal_correction_residual_b_minus_Ax": np.ones(613, dtype=np.complex128),
        "normal_after_normal_correction_residual_b_minus_Ax": np.pad(residual, (0, 612)),
        "normal_before_normal_correction_solution": np.zeros(613, dtype=np.complex128),
        "normal_after_normal_correction_solution": np.ones(613, dtype=np.complex128),
    }


def _raw_gate_arguments() -> dict:
    return {
        "active_trace_rows": 1,
        "active_interior_rows": 1,
        "independent_fe_dofs": 2,
        "active_full_rows": 3,
        "full_active_scope": {
            "active_full_rows": 3,
            "reduced_trace_dtn_rows": 613,
            "reduced_trace_dtn_owned_range": [0, 613],
            "mpi_size": 1,
        },
        "independent_a6_scope": {
            "trace_rows": 1,
            "active_interior_rows": 1,
            "modal_lower_rows": 612,
        },
        "normal_correction_count": 1,
        "normal_converged_reason": 2,
        "normal_correction_status": "passed",
        "extra_correction_count": 0,
    }


def test_raw_vector_residual_recomputation_uses_saved_gram_action():
    arrays = _raw_vectors()
    arrays["full_active_reduced_trace_dtn_residual_Ax_minus_b_owned"][0] = 0.5
    arrays["full_active_reduced_trace_dtn_residual_trace_metric_action"][0] = 0.25
    arrays["full_active_reduced_trace_dtn_rhs_owned"][0] = 1.0
    arrays["full_active_reduced_trace_dtn_rhs_trace_metric_action"][0] = 4.0

    result = h100_anchor._v11_raw_vector_gates(arrays, **_raw_gate_arguments())

    expected_metric_relative = np.sqrt(0.5 * 0.25) / np.sqrt(4.0 + 1.0)
    euclidean_relative = 0.5 / np.sqrt(1.0 + 1.0)
    assert result["full_active_transformed"]["relative_residual"] == pytest.approx(
        expected_metric_relative
    )
    assert result["full_active_transformed"]["relative_residual"] != pytest.approx(
        euclidean_relative
    )
    assert result["full_active_transformed"]["trace_metric"] == "saved same-pass Gram inverse action"

    malformed = _raw_vectors()
    malformed["returned_trace_dtn_rhs"] = np.ones(1, dtype=np.complex128)
    with pytest.raises(ValueError, match="returned condensed RHS"):
        h100_anchor._v11_raw_vector_gates(malformed, **_raw_gate_arguments())


def _pending_fixture(root: Path, *, failed_condensed: bool = False) -> tuple[Path, dict, dict, str]:
    artifact_prefix = root / "artifacts"
    p4 = {
        "root": "formal/R9_H8_attempt1",
        "script": "launch/R9_H8_attempt1.sh",
        "phase": "R9_H8",
        "candidate_id": "v11_r9_h8",
        "required_fe_bounds": {"parent_fe_dofs": 1, "target_exclusive_upper": 20},
    }
    p2_plan = Path("artifacts/support/p2/plans/v11_r9_h8.json")
    selection_file = root / "docs/selection.json"
    selection_file.parent.mkdir(parents=True)
    selection_file.write_text("selection\n", encoding="utf-8")
    selection_sha = hashlib.sha256(selection_file.read_bytes()).hexdigest()
    contract = {
        "artifact_prefix": str(artifact_prefix),
        "phases": {"P2": {"plan_output_path": str(p2_plan)}, "P4": p4},
        "inputs": [
            {
                "role": "R9_selection_transition",
                "path": "docs/selection.json",
                "sha256": selection_sha,
            }
        ],
    }
    contract_file = root / "docs/task43_hp_adaptivity/outcomes/records/v11_scientific_restart_contract.json"
    contract_file.parent.mkdir(parents=True, exist_ok=True)
    contract_bytes = (json.dumps(contract, sort_keys=True) + "\n").encode()
    contract_file.write_bytes(contract_bytes)
    contract_sha = hashlib.sha256(contract_bytes).hexdigest()
    candidate_root = artifact_prefix / p4["root"] / "run"
    attempt_root = candidate_root.parent
    candidate_root.mkdir(parents=True)
    p2_path = root / p2_plan
    p2_path.parent.mkdir(parents=True)
    plan = {
        "task43_candidate": {
            "candidate_id": "v11_r9_h8",
            "action": "h_refine",
            "provenance": {"accepted_parent_selection_sha256": selection_sha},
        }
    }
    plan_bytes = (json.dumps(plan, sort_keys=True) + "\n").encode()
    p2_path.write_bytes(plan_bytes)
    run_plan_path = candidate_root / "candidate_plan.json"
    run_plan_path.write_bytes(plan_bytes)
    plan_sha = hashlib.sha256(plan_bytes).hexdigest()
    audit = {
        "forest": {"root_cell_count": 1, "actual_leaf_cell_count": 1},
        "dofs": {
            "independent_trace_rows": 1,
            "active_cell_interior_rows": 1,
            "independent_active_fe_dofs": 2,
        },
        "degrees": {
            "cell_interior_histogram": {"p6": 1},
            "entity_degree_plan_sha256": "entity-plan",
        },
        "actual_geometry": {"mesh_box_catalog_sha256": "mesh-boxes"},
    }
    audit_path = p2_path.parent / "v11_r9_h8.audit.json"
    audit_path.write_text(json.dumps(audit, sort_keys=True), encoding="utf-8")
    p2_audit_sha = hashlib.sha256(audit_path.read_bytes()).hexdigest()

    source_map = {"benchmarks/fake_source.py": "source-sha"}
    script_path = artifact_prefix / p4["script"]
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    snapshots = attempt_root / "snapshots"
    snapshots.mkdir(parents=True)
    launch_snapshot = snapshots / "launch.sh"
    launch_snapshot.write_bytes(script_path.read_bytes())
    watchdog_dir = attempt_root / "watchdog"
    watchdog_dir.mkdir()
    (watchdog_dir / "summary.json").write_text(
        json.dumps(
            {
                "classification": "COMPLETED",
                "leader_exit_code": 0,
                "descendants_cleared": True,
                "remaining_child_pids": [],
            }
        ),
        encoding="utf-8",
    )
    (attempt_root / "launcher_exit_code.txt").write_text("0\n", encoding="ascii")
    (attempt_root / "watchdog_exit_code.txt").write_text("0\n", encoding="ascii")
    manifest = {
        "schema": "task43.v11.launch-input-manifest.v1",
        "contract_sha256": contract_sha,
        "launch_shell_sha256": hashlib.sha256(launch_snapshot.read_bytes()).hexdigest(),
        "source": [{"path": name, "sha256": digest} for name, digest in source_map.items()],
        "inputs": [
            {
                "path": str(selection_file.resolve()),
                "sha256": selection_sha,
            }
        ],
    }
    (snapshots / "launch_manifest.json").write_text(
        json.dumps(manifest, sort_keys=True), encoding="utf-8"
    )

    arrays = _raw_vectors(failed_condensed=failed_condensed)
    identity = {
        "phase": "R9_H8",
        "contract_sha256": contract_sha,
        "candidate_plan_sha256": plan_sha,
        "candidate_identity": {"candidate_id": "v11_r9_h8"},
        "independent_active_fe_dofs": 2,
        "raw_full_active_scope": _raw_gate_arguments()["full_active_scope"],
        "independent_A6_raw_vector_scope": _raw_gate_arguments()["independent_a6_scope"],
        "normal_correction_count": 1,
        "extra_correction_count": 0,
        "normal_correction_audit": {
            "status": "passed",
            "correction_ksp": {"converged_reason": 2},
        },
    }
    packet = write_v11_primary_packet(
        candidate_root / "primary_state.npz",
        arrays,
        phase="R9_H8",
        identity=identity,
    )
    raw_recomputed = h100_anchor._v11_raw_vector_gates(arrays, **_raw_gate_arguments())
    candidate_identity = {
        "candidate_id": "v11_r9_h8",
        "v11_phase": "R9_H8",
        "v11_contract_sha256": contract_sha,
        "plan_sha256": plan_sha,
        "run_plan_path": str(run_plan_path.resolve()),
        "accepted_parent_selection_sha256": selection_sha,
    }
    watchdog_identity = {
        "worker_pid": 99999991,
        "worker_start_ticks": 1,
        "tracer_pid": 99999992,
        "tracer_start_ticks": 1,
        "direct_watchdog_parent_verified": True,
        "tracer_descends_from_watchdog": True,
        "worker_tid_affinities": [{"tid": 99999991, "cpu_list": [1]}],
    }
    source_identity = {
        "v11_primary_contract": {
            "contract_path": str(contract_file.resolve()),
            "contract_sha256": contract_sha,
            "phase": "R9_H8",
        },
        "file_sha256": source_map,
        "v11_watchdog_worker_identity": watchdog_identity,
    }
    actual = {
        "root_cell_count": 1,
        "leaf_cell_count": 1,
        "independent_trace_rows": 1,
        "active_cell_interior_rows": 1,
        "independent_active_fe_dofs": 2,
        "cell_interior_histogram": {"p6": 1},
        "entity_degree_plan_sha256": "entity-plan",
        "entity_map_sha256": "entity-map",
        "mesh_box_catalog_sha256": "mesh-boxes",
    }
    audit["degrees"]["entity_map_sha256"] = "entity-map"
    audit_path.write_text(json.dumps(audit, sort_keys=True), encoding="utf-8")
    p2_audit_sha = hashlib.sha256(audit_path.read_bytes()).hexdigest()
    record = {
        "schema": "task43.v11.primary-endpoint.v1",
        "phase": "R9_H8",
        "status": "SOLVED_PENDING_POSTPROCESS",
        "official_result": False,
        "selection_eligible": False,
        "selection_candidate": False,
        "candidate_selected": False,
        "continuation_all_false": True,
        "gates": {"pass": True},
        "pass": True,
        "passed": True,
        "candidate_identity": candidate_identity,
        "candidate_plan_sha256": plan_sha,
        "source_identity": source_identity,
        "solver": {"official_result": False},
        "field_samples": {"status": "not_run_pending_p5_common_union_sampling"},
        "primary_samples": {},
        "primary_packet": packet,
        "primary_raw_vector_audit": {
            "pass": raw_recomputed["pass"],
            "gates": raw_recomputed["gates"],
        },
        "p4_preassembly_space_audit": {
            "pass": True,
            "p2_plan_sha256": plan_sha,
            "p2_audit_sha256": p2_audit_sha,
            "actual": actual,
        },
        "recovered_solution_storage": {
            "active_trace_rows": 1,
            "active_cell_interior_rows": 1,
        },
    }
    endpoint_path = candidate_root / "task43_round1_candidate_record.json"
    endpoint_path.write_text("endpoint bytes\n", encoding="utf-8")
    terminal = {
        "schema": "task43.v11.primary-terminal.v1",
        "phase": "R9_H8",
        "status": "SOLVED_PENDING_POSTPROCESS",
        "official_result": False,
        "passed": False,
        "selection_eligible": False,
        "selection_candidate": False,
        "candidate_selected": False,
        "continuation_all_false": True,
        "contract_sha256": contract_sha,
        "candidate_identity": candidate_identity,
        "source_identity": source_identity,
        "endpoint_record_path": str(endpoint_path),
        "endpoint_record_sha256": hashlib.sha256(endpoint_path.read_bytes()).hexdigest(),
        "candidate_plan_sha256": plan_sha,
        "primary_packet": packet,
        "primary_samples": {},
    }
    (candidate_root / "task43_v11_primary_terminal.json").write_text(
        json.dumps(terminal, sort_keys=True), encoding="utf-8"
    )
    return candidate_root, record, contract, contract_sha


def test_pending_candidate_restore_is_v11_contract_scoped(tmp_path, monkeypatch):
    scenarios = (
        "valid",
        "launcher_exit",
        "watchdog_exit",
        "source_mismatch",
        "plan_mismatch",
        "raw_gate_failure",
        "nonpositive_fe_growth",
        "fe_upper_bound",
        "terminal_failure",
    )
    for scenario in scenarios:
        root = tmp_path / scenario
        candidate_root, record, contract, contract_sha = _pending_fixture(
            root, failed_condensed=scenario == "raw_gate_failure"
        )
        monkeypatch.setattr(comparison, "ROOT", root)
        monkeypatch.setattr(
            comparison,
            "_v11_source_snapshot",
            lambda: {"benchmarks/fake_source.py": "source-sha"},
        )
        if scenario == "valid":
            p2_path = root / contract["phases"]["P2"]["plan_output_path"]
            resolved = comparison._validate_v11_pending_candidate(
                candidate_root,
                record=record,
                contract=contract,
                contract_sha256=contract_sha,
            )
            assert resolved[0] == candidate_root / "candidate_plan.json"
            assert resolved[0] != p2_path
            assert resolved[2] == hashlib.sha256(p2_path.read_bytes()).hexdigest()
            continue
        attempt_root = candidate_root.parent
        if scenario == "launcher_exit":
            (attempt_root / "launcher_exit_code.txt").write_text("1\n", encoding="ascii")
        elif scenario == "watchdog_exit":
            (attempt_root / "watchdog_exit_code.txt").write_text("1\n", encoding="ascii")
        elif scenario == "source_mismatch":
            manifest_path = attempt_root / "snapshots/launch_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["source"][0]["sha256"] = "changed-source"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        elif scenario == "plan_mismatch":
            (candidate_root / "candidate_plan.json").write_text("different plan\n", encoding="utf-8")
        elif scenario == "raw_gate_failure":
            assert record["primary_raw_vector_audit"]["pass"] is False
        elif scenario == "nonpositive_fe_growth":
            contract["phases"]["P4"]["required_fe_bounds"]["parent_fe_dofs"] = 2
        elif scenario == "fe_upper_bound":
            contract["phases"]["P4"]["required_fe_bounds"]["target_exclusive_upper"] = 2
        elif scenario == "terminal_failure":
            terminal_path = candidate_root / "task43_v11_primary_terminal.json"
            terminal = json.loads(terminal_path.read_text(encoding="utf-8"))
            terminal["status"] = "FAILED"
            terminal_path.write_text(json.dumps(terminal), encoding="utf-8")
        with pytest.raises((ValueError, FileNotFoundError)):
            comparison._validate_v11_pending_candidate(
                candidate_root,
                record=record,
                contract=contract,
                contract_sha256=contract_sha,
            )


def test_fixed_seed8_plan_rejects_nonroot_and_alternate_seed(monkeypatch):
    contract = _contract()
    phase = contract["phases"]["P4"]
    seed = phase["seed"]
    seed_box = tuple(map(float, (*seed["lower_nm"], *seed["upper_nm"])))
    parent = {
        "selected_candidate_id": "round9_p_up",
        "parent_independent_fe_dofs": phase["required_fe_bounds"]["parent_fe_dofs"],
        "parent_marked_root_boxes": [],
        "parent_boxes_by_global_id": {8: seed_box},
        "parent_forest": SimpleNamespace(root_boxes=(seed_box,)),
        "parent_degree_by_box": {seed_box: 5},
    }
    calls = []

    def build(_cfg, *, action, candidate_id, parent, comm_size):
        calls.append((action, candidate_id, parent["marked_global_cell_ids"], comm_size))
        return {"task43_candidate": {"provenance": {}}}, {"status": "plan_built"}

    monkeypatch.setattr(round1_candidates, "_build_next_round_plan", build)
    plan = round1_candidates._build_v11_seed8_plan(
        object(), parent=parent, comm_size=1, contract=contract
    )
    assert calls == [("h_refine", "v11_r9_h8", [8], 1)]
    assert plan["task43_candidate"]["provenance"]["full_dorfer_set_not_used"] is True

    nonroot_parent = copy.deepcopy(parent)
    nonroot_parent["parent_forest"] = SimpleNamespace(root_boxes=())
    with pytest.raises(ValueError, match="not an unrefined root"):
        round1_candidates._build_v11_seed8_plan(
            object(), parent=nonroot_parent, comm_size=1, contract=contract
        )
    alternate_seed_contract = copy.deepcopy(contract)
    alternate_seed_contract["phases"]["P4"]["seed"]["global_cell_id"] = 9
    with pytest.raises(ValueError, match="seed identity"):
        round1_candidates._build_v11_seed8_plan(
            object(), parent=parent, comm_size=1, contract=alternate_seed_contract
        )


def test_v11_primary_cli_forbids_extra_and_binds_q10_output(tmp_path, monkeypatch):
    contract = _contract()
    selection = Path("docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json").resolve()
    acceptance = Path("docs/task43_hp_adaptivity/outcomes/records/round1_acceptance_contract_v1.json").resolve()
    phase_args = (
        ("A1_q3", "benchmarks/artifacts/task43/round10_p_only_authority_attempt1/plan_output/plans/round10_p_up.json"),
        ("R9_H8", contract["phases"]["P2"]["plan_output_path"]),
    )
    for phase, relative_plan in phase_args:
        entry = contract["phases"]["P3" if phase == "A1_q3" else "P4"]
        run_root = Path(contract["artifact_prefix"]) / entry["root"] / "run"
        h100_anchor._validate_v11_primary_cli(
            contract=contract,
            phase=phase,
            run_root=run_root,
            candidate_id=entry.get("candidate_id", entry.get("space", {}).get("candidate_id")),
            candidate_plan_path=Path(relative_plan),
            candidate_parent_selection_record=selection,
            candidate_acceptance_contract=acceptance,
            normal_correction_enabled=True,
            extra_correction_enabled=False,
            direct_factor_backend="mumps",
        )
        with pytest.raises(ValueError, match="exactly one normal correction"):
            h100_anchor._validate_v11_primary_cli(
                contract=contract,
                phase=phase,
                run_root=run_root,
                candidate_id=entry.get("candidate_id", entry.get("space", {}).get("candidate_id")),
                candidate_plan_path=Path(relative_plan),
                candidate_parent_selection_record=selection,
                candidate_acceptance_contract=acceptance,
                normal_correction_enabled=True,
                extra_correction_enabled=True,
                direct_factor_backend="mumps",
            )
    with pytest.raises(ValueError, match="unsupported V11 primary phase"):
        h100_anchor._validate_v11_primary_cli(
            contract=contract,
            phase="unknown",
            run_root=Path(contract["artifact_prefix"]) / "invalid" / "run",
            candidate_id="round10_p_up",
            candidate_plan_path=Path(phase_args[0][1]),
            candidate_parent_selection_record=selection,
            candidate_acceptance_contract=acceptance,
            normal_correction_enabled=True,
            extra_correction_enabled=False,
            direct_factor_backend="mumps",
        )
    with pytest.raises(ValueError, match="unique contract root"):
        h100_anchor._validate_v11_primary_cli(
            contract=contract,
            phase="R9_H8",
            run_root=(
                Path(contract["artifact_prefix"])
                / contract["phases"]["P4"]["root"]
                / "wrong-run-root"
            ),
            candidate_id="v11_r9_h8",
            candidate_plan_path=Path(phase_args[1][1]),
            candidate_parent_selection_record=selection,
            candidate_acceptance_contract=acceptance,
            normal_correction_enabled=True,
            extra_correction_enabled=False,
            direct_factor_backend="mumps",
        )

    cfg = SimpleNamespace()
    q_identity = h100_anchor._configure_v11_primary_endpoint(cfg, "A1_q3", contract)
    assert (q_identity["volume_quadrature_degree"], q_identity["incident_and_port_quadrature_degree"]) == (19, 32)
    assert q_identity["R13_rectangle"]["count"] == 612

    # Exercise the real q8/q10 response loop with only its old frozen data reader stubbed.
    cfg.period_x = cfg.period_y = 50.0
    cfg.domain_z_min, cfg.domain_z_max = -10.0, 130.0
    cfg.k0 = 1.0
    cfg.magnetic_field_scale_A_per_m = 1.0
    cfg.mu_r = 1.0
    monkeypatch.setattr(
        h100_anchor,
        "_v2_legacy_r10_reference",
        lambda: {
            "payload": {},
            "A_volume_total": 0.1,
            "physical_configuration_sha256": "reference-physics",
            "discretization_sha256": "reference-space",
            "phase": "A1_q",
            "record_sha256": "record",
            "payload_sha256": "modes",
            "samples_sha256": "samples",
            "solver_source_compatibility": {"pass": True},
            "samples_path": Path("saved_samples.npz"),
        },
    )
    seen_orders = []
    monkeypatch.setattr(h100_anchor, "compare_r13_modal_outputs", lambda *args, **kwargs: {"pass_10_percent_perturbation_gate": True})
    monkeypatch.setattr(h100_anchor, "_v2_field_bundle_from_npz", lambda path, order, *args: {"order": order})
    monkeypatch.setattr(h100_anchor, "_v2_field_bundle_from_capture", lambda sample, *args: sample)

    def compare_fields(reference, candidate, **kwargs):
        seen_orders.append(reference["order"])
        return {"pass_10_percent_perturbation_gate": True}

    monkeypatch.setattr(h100_anchor, "compare_field_sample_bundles", compare_fields)
    response = h100_anchor._v11_primary_q_response(
        phase="A1_q3",
        cfg=cfg,
        candidate_identity={"candidate_id": "round10_p_up"},
        endpoint_identity={
            "physical_configuration": {
                "sha256": "candidate-physics",
                "discretization_identity": {"sha256": "candidate-space"},
            }
        },
        captured={"fields": {"samples": {"q8": {"order": 8}, "q10": {"order": 10}}}},
        port_payload={},
        A_volume_total=0.1,
    )
    assert seen_orders == [8, 10]
    assert set(response["field_comparisons"]) == {"q8", "q10"}
    assert response["pass"] is True

    rows = []
    for side, m, n, polarization in h100_anchor.R13_MODE_KEYS:
        rows.append(
            {
                "side": side,
                "m": m,
                "n": n,
                "polarization": polarization,
                "outgoing_amplitude_at_boundary": [0.0, 0.0],
                "power_carrying": False,
                "power_ratio": 0.0,
                "R": 0.0,
                "T": 0.0,
            }
        )
    port_payload = {
        "orders": rows,
        "metrics": {
            "R_total": 0.0,
            "T_total": 0.0,
            "R00_s": 0.0,
            "R00_p": 0.0,
            "R00_total": 0.0,
            "dtn_port_mode_count": 612,
        },
    }
    assert len(
        h100_anchor._v2_validated_rows(
            port_payload, label="P1 V11 mode sentinel", expected=h100_anchor.R13_MODE_KEYS
        )
    ) == 612
    nonfinite_payload = copy.deepcopy(port_payload)
    nonfinite_payload["orders"][0]["outgoing_amplitude_at_boundary"] = [float("nan"), 0.0]
    with pytest.raises(ValueError):
        h100_anchor._v2_validated_rows(
            nonfinite_payload,
            label="P1 V11 nonfinite mode sentinel",
            expected=h100_anchor.R13_MODE_KEYS,
        )

    # Exercise the production field-capture loop: q8 is durable before the q10
    # writer failure is propagated to the surrounding primary-terminal handler.
    axes = (np.asarray([0.0, 50.0]), np.asarray([0.0, 50.0]), np.asarray([-10.0, 130.0]))
    monkeypatch.setattr(
        h100_anchor,
        "prepare_cell_local_vector_field_export",
        lambda _field: SimpleNamespace(
            electric_dgq6=object(),
            curl_electric_dgq6=object(),
            source_degree=6,
            target_degree=6,
            representation="DGQ6",
        ),
    )
    monkeypatch.setattr(h100_anchor, "_mesh_axes", lambda _mesh, _comm: axes)
    monkeypatch.setattr(h100_anchor, "_assert_mesh_profile", lambda *_args, **_kwargs: {"pass": True})
    monkeypatch.setattr(
        h100_anchor,
        "build_common_volume_quadrature",
        lambda _axes, *, gauss_order: SimpleNamespace(
            points_nm=np.asarray([[float(gauss_order), 0.0, 0.0]]),
            weights_nm3=np.asarray([1.0]),
        ),
    )
    monkeypatch.setattr(
        h100_anchor,
        "sample_cell_local_vector_fields",
        lambda _fields, points: {
            "E_total": np.ones((len(points), 3), dtype=np.complex128),
            "curl_E_total": np.ones((len(points), 3), dtype=np.complex128),
        },
    )
    monkeypatch.setattr(
        h100_anchor,
        "magnetic_field_from_electric_curl",
        lambda curl, **_kwargs: np.asarray(curl),
    )

    class SerialComm:
        rank = 0

        @staticmethod
        def allgather(value):
            return [value]

    q8_path = tmp_path / "primary_field_sample_q8.npz"
    primary_path = tmp_path / "primary_state.npz"
    primary_packet = write_v11_primary_packet(
        primary_path,
        _raw_vectors(),
        phase="A1_q3",
        identity={"phase": "A1_q3", "contract_sha256": "fixture"},
    )
    sample_records = {}
    writes = []
    q8_sha_before_q10_failure = None

    def persist_sample(order, sample):
        nonlocal q8_sha_before_q10_failure
        writes.append(order)
        if order == 10:
            raise OSError("injected q10 output failure")
        write_v11_primary_field_sample(
            q8_path,
            order,
            sample,
            identity={"phase": "A1_q3", "contract_sha256": "fixture"},
            sample_records=sample_records,
        )
        q8_sha_before_q10_failure = hashlib.sha256(q8_path.read_bytes()).hexdigest()

    with pytest.raises(RuntimeError, match="field sample postprocessing failed collectively"):
        h100_anchor._field_capture(
            object(),
            SimpleNamespace(mesh=object()),
            SimpleNamespace(magnetic_field_scale_A_per_m=1.0, k0=1.0, mu_r=1.0),
            SerialComm(),
            reference_axes=None,
            geometry_profile="h100",
            sample_fields=True,
            on_sample=persist_sample,
        )
    assert writes == [8, 10]
    assert q8_path.is_file()
    assert q8_sha_before_q10_failure is not None
    failure_terminal = h100_anchor._write_v11_partial_terminal(
        tmp_path,
        phase="A1_q3",
        source_identity={"file_sha256": {"fake.py": "sha"}},
        captured={
            "v11_primary_packet": primary_packet,
            "v11_primary_sample_records": sample_records,
        },
        candidate_identity={"candidate_id": "round10_p_up"},
        error="field sample postprocessing failed collectively",
    )
    terminal = json.loads(Path(failure_terminal["path"]).read_text(encoding="utf-8"))
    assert terminal["primary_packet"]["npz_sha256"] == primary_packet["npz_sha256"]
    assert terminal["primary_samples"]["q8"]["npz_sha256"] == sample_records["q8"]["npz_sha256"]
    assert hashlib.sha256(q8_path.read_bytes()).hexdigest() == q8_sha_before_q10_failure


def test_v11_terminal_failure_is_incomplete_and_primary_only(tmp_path, monkeypatch):
    path = tmp_path / "run"
    path.mkdir()
    primary_packet = write_v11_primary_packet(
        path / "primary_state.npz",
        _raw_vectors(),
        phase="A1_q3",
        identity={"phase": "A1_q3", "contract_sha256": "fixture"},
    )
    sample_path = path / "primary_field_sample_q8.npz"
    sample = write_v11_primary_field_sample(
        sample_path,
        8,
        {"points_nm": np.zeros((2, 3)), "E_total": np.ones((2, 3))},
        identity={"phase": "A1_q3", "contract_sha256": "fixture"},
        sample_records={},
    )
    endpoint_path = path / "task43_round1_candidate_record.json"
    endpoint_path.write_text(
        json.dumps(
            {
                "schema": "task43.v11.primary-endpoint.v1",
                "status": "SOLVED_PRIMARY_Q_RESPONSE_PASS",
                "official_result": False,
                "selection_eligible": False,
                "selection_candidate": False,
                "candidate_selected": False,
                "continuation_all_false": True,
                "pass": True,
                "passed": True,
                "solver": {"official_result": False},
                "gates": {"pass": True, "status": "passed"},
                "primary_packet": primary_packet,
            }
        ),
        encoding="utf-8",
    )
    packet_hash = primary_packet["npz_sha256"]
    sample_hash = sample["npz_sha256"]
    result = h100_anchor._write_v11_partial_terminal(
        path,
        phase="A1_q3",
        source_identity={"file_sha256": {"fake.py": "sha"}},
        captured={
            "v11_primary_packet": primary_packet,
            "v11_primary_sample_records": {"q8": sample},
        },
        candidate_identity={"candidate_id": "round10_p_up"},
        error=RuntimeError("mesh sentinel"),
    )
    terminal = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
    assert terminal["status"] == "FAILED"
    assert terminal["official_result"] is False
    assert terminal["passed"] is False
    assert terminal["selection_eligible"] is False
    assert terminal["continuation_all_false"] is True
    assert terminal["primary_packet"]["npz_sha256"] == packet_hash
    assert terminal["primary_samples"]["q8"]["npz_sha256"] == sample_hash
    demoted = json.loads(endpoint_path.read_text(encoding="utf-8"))
    assert demoted["pass"] is False
    assert demoted["passed"] is False
    assert demoted["gates"]["pass"] is False
    assert demoted["official_result"] is False
    assert result["sha256"] == hashlib.sha256(Path(result["path"]).read_bytes()).hexdigest()

    root = tmp_path / "terminal_writer_failure"
    candidate_root, pending_record, contract, contract_sha = _pending_fixture(root)
    monkeypatch.setattr(comparison, "ROOT", root)
    monkeypatch.setattr(
        comparison,
        "_v11_source_snapshot",
        lambda: {"benchmarks/fake_source.py": "source-sha"},
    )
    endpoint_path = candidate_root / "task43_round1_candidate_record.json"
    endpoint_path.write_text(
        json.dumps(
            {
                "schema": "task43.v11.primary-endpoint.v1",
                "phase": "R9_H8",
                "status": "SOLVED_PENDING_POSTPROCESS",
                "pass": True,
                "passed": True,
                "official_result": False,
                "selection_eligible": False,
                "selection_candidate": False,
                "candidate_selected": False,
                "continuation_all_false": True,
                "solver": {"official_result": False},
                "gates": {"pass": True, "status": "passed"},
            }
        ),
        encoding="utf-8",
    )
    primary_path = candidate_root / "primary_state.npz"
    primary_packet_sha = hashlib.sha256(primary_path.read_bytes()).hexdigest()
    q8_path = candidate_root / "primary_field_sample_q8_wrapper.npz"
    q8_sample = write_v11_primary_field_sample(
        q8_path,
        8,
        {"points_nm": np.zeros((2, 3)), "E_total": np.ones((2, 3))},
        identity={"phase": "R9_H8", "contract_sha256": contract_sha},
        sample_records={},
    )
    q8_sha = hashlib.sha256(q8_path.read_bytes()).hexdigest()
    success_terminal_path = candidate_root / "attempted_success_terminal.json"
    failed_terminal_writes = []
    original_replace = candidate_checkpoints._replace_atomically

    def fail_success_terminal_output(path_arg, writer):
        if Path(path_arg) == success_terminal_path:
            failed_terminal_writes.append(str(path_arg))
            raise OSError("injected successful terminal output failure")
        return original_replace(path_arg, writer)

    monkeypatch.setattr(candidate_checkpoints, "_replace_atomically", fail_success_terminal_output)
    endpoint_demotion_failures = []
    original_atomic_json = h100_anchor.write_atomic_json

    def fail_endpoint_demotion(path_arg, record_arg, **kwargs):
        if Path(path_arg) == endpoint_path:
            endpoint_demotion_failures.append(str(path_arg))
            raise OSError("injected partial-terminal endpoint demotion failure")
        return original_atomic_json(path_arg, record_arg, **kwargs)

    monkeypatch.setattr(h100_anchor, "write_atomic_json", fail_endpoint_demotion)
    source_identity = pending_record["source_identity"]
    candidate_identity = pending_record["candidate_identity"]

    def fake_run_impl(
        case,
        run_root,
        v11_primary_diagnostic_phase,
        _failure_context=None,
    ):
        assert case == "round1_candidate_mpi1"
        _failure_context.update(
            run_root=Path(run_root),
            run_root_acquired=True,
            phase=v11_primary_diagnostic_phase,
            source_identity=source_identity,
            captured={
                "v11_primary_packet": pending_record["primary_packet"],
                "v11_primary_sample_records": {"q8": q8_sample},
            },
            candidate_identity=candidate_identity,
        )
        return h100_anchor.write_v11_primary_terminal(
            success_terminal_path,
            phase=v11_primary_diagnostic_phase,
            status="SOLVED_PENDING_POSTPROCESS",
            source_identity=source_identity,
            candidate_identity=candidate_identity,
            contract_sha256=contract_sha,
            candidate_plan_sha256=pending_record["candidate_plan_sha256"],
            primary_packet=pending_record["primary_packet"],
            primary_samples={"q8": q8_sample},
            endpoint_record_path=endpoint_path,
        )

    with pytest.raises(OSError, match="successful terminal output failure"):
        h100_anchor._run_with_v3_failure_terminal(
            fake_run_impl,
            case="round1_candidate_mpi1",
            run_root=candidate_root,
            v11_primary_diagnostic_phase="R9_H8",
        )
    assert failed_terminal_writes == [str(success_terminal_path)]
    assert endpoint_demotion_failures == [str(endpoint_path)]
    assert hashlib.sha256(primary_path.read_bytes()).hexdigest() == primary_packet_sha
    assert hashlib.sha256(q8_path.read_bytes()).hexdigest() == q8_sha
    partial_path = candidate_root / "task43_v11_partial_terminal.json"
    partial = json.loads(partial_path.read_text(encoding="utf-8"))
    assert partial["primary_packet"]["npz_sha256"] == pending_record["primary_packet"]["npz_sha256"]
    assert partial["primary_samples"]["q8"]["npz_sha256"] == q8_sample["npz_sha256"]
    assert json.loads(endpoint_path.read_text(encoding="utf-8"))["pass"] is True

    attempt_root = candidate_root.parent
    (attempt_root / "launcher_exit_code.txt").write_text("1\n", encoding="ascii")
    with pytest.raises(ValueError, match="launcher_exit_code"):
        comparison._validate_v11_pending_candidate(
            candidate_root,
            record=pending_record,
            contract=contract,
            contract_sha256=contract_sha,
        )
    (attempt_root / "launcher_exit_code.txt").write_text("0\n", encoding="ascii")
    with pytest.raises(ValueError, match="success terminal is missing or conflicts"):
        comparison._validate_v11_pending_candidate(
            candidate_root,
            record=pending_record,
            contract=contract,
            contract_sha256=contract_sha,
        )


def test_v11_empty_root_guard_preserves_existing_file_hash(tmp_path):
    run_root = tmp_path / "nonempty"
    run_root.mkdir()
    marker = run_root / "previous_negative.json"
    marker.write_bytes(b"preserve-me\n")
    before_files = {
        child.relative_to(run_root).as_posix(): hashlib.sha256(
            child.read_bytes()
        ).hexdigest()
        for child in run_root.iterdir()
        if child.is_file()
    }

    class SerialComm:
        rank = 0

        @staticmethod
        def bcast(value, root=0):
            return value

        @staticmethod
        def Barrier():
            return None

    comm = SerialComm()
    acquired = []

    def fake_run_impl(
        case,
        run_root,
        v11_primary_diagnostic_phase,
        _failure_context=None,
    ):
        assert case == "round1_candidate_mpi1"
        assert v11_primary_diagnostic_phase == "A1_q3"
        h100_anchor._acquire_empty_run_root(run_root, comm)
        _failure_context["run_root_acquired"] = True
        acquired.append(True)

    with pytest.raises(RuntimeError, match="refusing to overwrite nonempty output root"):
        h100_anchor._run_with_v3_failure_terminal(
            fake_run_impl,
            case="round1_candidate_mpi1",
            run_root=run_root,
            v11_primary_diagnostic_phase="A1_q3",
        )
    assert acquired == []
    after_files = {
        child.relative_to(run_root).as_posix(): hashlib.sha256(
            child.read_bytes()
        ).hexdigest()
        for child in run_root.iterdir()
        if child.is_file()
    }
    assert after_files == before_files
    assert list(run_root.iterdir()) == [marker]
    assert not (run_root / "task43_v11_partial_terminal.json").exists()


def test_v11_common_points_identity_and_fe_bounds(tmp_path, monkeypatch):
    axes = (
        np.asarray([0.0, 50.0]),
        np.asarray([0.0, 50.0]),
        np.asarray([-10.0, 130.0]),
    )
    q8 = build_common_volume_quadrature([axes, axes, axes], gauss_order=8)
    q10 = build_common_volume_quadrature([axes, axes, axes], gauss_order=10)
    assert float(np.sum(q8.weights_nm3)) == pytest.approx(350000.0, abs=1.0e-8)
    assert float(np.sum(q10.weights_nm3)) == pytest.approx(350000.0, abs=1.0e-8)
    assert np.array_equal(q8.points_nm, build_common_volume_quadrature([axes] * 3, gauss_order=8).points_nm)
    assert np.array_equal(q8.weights_nm3, build_common_volume_quadrature([axes] * 3, gauss_order=8).weights_nm3)
    assert not np.array_equal(q8.points_nm, q10.points_nm)

    bounds = _contract()["phases"]["P4"]["required_fe_bounds"]
    assert int(bounds["strict_added_dofs_minimum"]) > 0
    root = tmp_path / "actual-fe-bound-gate"
    candidate_root, record, contract, contract_sha = _pending_fixture(root)
    monkeypatch.setattr(comparison, "ROOT", root)
    monkeypatch.setattr(
        comparison,
        "_v11_source_snapshot",
        lambda: {"benchmarks/fake_source.py": "source-sha"},
    )
    contract["phases"]["P4"]["required_fe_bounds"]["parent_fe_dofs"] = 2
    with pytest.raises(ValueError, match="strict growth bounds"):
        comparison._validate_v11_pending_candidate(
            candidate_root,
            record=record,
            contract=contract,
            contract_sha256=contract_sha,
        )


def test_main_reaches_v11_mesh_sentinel_with_watchdog_identity(tmp_path, monkeypatch):
    frozen = _contract()
    repository = tmp_path / "isolated_repo"
    contract = copy.deepcopy(frozen)
    contract["artifact_prefix"] = str(
        repository / "benchmarks/artifacts/task43/v11_science"
    )
    contract["phases"]["P2"]["plan_output_path"] = (
        "benchmarks/artifacts/task43/v11_science/support/p2/plan_output/"
        "plans/v11_r9_h8.json"
    )
    contract["phases"]["P3"]["root"] = "support/p1_a1_q3_main_sentinel"
    contract["phases"]["P4"]["root"] = "support/p1_r9_h8_main_sentinel"

    selection_path = repository / "docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json"
    acceptance_path = repository / "docs/task43_hp_adaptivity/outcomes/records/round1_acceptance_contract_v1.json"
    selection_path.parent.mkdir(parents=True, exist_ok=True)
    selection_path.write_text("isolated accepted R9 selection\n", encoding="utf-8")
    acceptance_path.write_text("isolated frozen acceptance\n", encoding="utf-8")
    selection_sha = hashlib.sha256(selection_path.read_bytes()).hexdigest()
    acceptance_sha = hashlib.sha256(acceptance_path.read_bytes()).hexdigest()

    r10_plan_path = repository / "benchmarks/artifacts/task43/round10_p_only_authority_attempt1/plan_output/plans/round10_p_up.json"
    r10_plan = {
        "task43_candidate": {
            "candidate_id": "round10_p_up",
            "action": "p_up",
            "provenance": {},
        }
    }
    r10_plan_path.parent.mkdir(parents=True, exist_ok=True)
    r10_plan_path.write_text(
        json.dumps(r10_plan, sort_keys=True) + "\n", encoding="utf-8"
    )
    r10_plan_sha = hashlib.sha256(r10_plan_path.read_bytes()).hexdigest()
    h_plan_path = repository / contract["phases"]["P2"]["plan_output_path"]
    h_plan = {
        "task43_candidate": {
            "candidate_id": "v11_r9_h8",
            "action": "h_refine",
            "provenance": {
                "marked_global_cell_ids_source": "v11_predeclared_seed8",
                "v11_seed": frozen["phases"]["P4"]["seed"],
                "accepted_parent_selection_sha256": selection_sha,
            },
        }
    }
    h_plan_path.parent.mkdir(parents=True, exist_ok=True)
    h_plan_path.write_text(json.dumps(h_plan, sort_keys=True) + "\n", encoding="utf-8")
    h_plan_sha = hashlib.sha256(h_plan_path.read_bytes()).hexdigest()

    contract["inputs"] = [
        {
            "role": "R9_selection_transition",
            "path": str(selection_path.relative_to(repository)),
            "sha256": selection_sha,
        },
        {
            "role": "frozen_acceptance_contract",
            "path": str(acceptance_path.relative_to(repository)),
            "sha256": acceptance_sha,
        },
        {
            "role": "R10_authority_plan",
            "path": str(r10_plan_path.relative_to(repository)),
            "sha256": r10_plan_sha,
        },
    ]
    contract_path = repository / "docs/task43_hp_adaptivity/outcomes/records/v11_scientific_restart_contract.json"
    contract_path.parent.mkdir(parents=True, exist_ok=True)
    contract_bytes = (json.dumps(contract, sort_keys=True) + "\n").encode()
    contract_path.write_bytes(contract_bytes)
    contract_sha = hashlib.sha256(contract_bytes).hexdigest()

    monkeypatch.setattr(h100_anchor, "_REPOSITORY_ROOT", repository)
    monkeypatch.setattr(
        h100_anchor,
        "_load_v11_primary_contract",
        lambda _path: (contract, contract_sha),
    )

    class MeshSentinel(RuntimeError):
        pass

    def mesh_sentinel(*_args, **_kwargs):
        raise MeshSentinel("reached real h100 main mesh builder")

    monkeypatch.setattr(h100_anchor, "build_airbox_mesh_3d", mesh_sentinel)
    run_impl_controls = []
    extra_helper_calls = []

    def fail_if_extra_correction_called(*args, **kwargs):
        extra_helper_calls.append({"args": repr(args), "kwargs": repr(kwargs)})
        raise AssertionError("V11 main sentinel called the forbidden extra-correction helper")

    monkeypatch.setattr(h100_anchor, "_same_lu_tightening", fail_if_extra_correction_called)
    real_run_impl = h100_anchor._run_impl

    @wraps(real_run_impl)
    def observe_run_impl(*args, **kwargs):
        run_impl_controls.append(
            {
                "phase": kwargs.get("v11_primary_diagnostic_phase"),
                "same_lu_tightening_enabled": kwargs.get(
                    "same_lu_tightening_enabled"
                ),
                "same_lu_solve_residual_correction_enabled": kwargs.get(
                    "same_lu_solve_residual_correction_enabled"
                ),
            }
        )
        assert kwargs.get("same_lu_tightening_enabled") is False
        return real_run_impl(*args, **kwargs)

    monkeypatch.setattr(h100_anchor, "_run_impl", observe_run_impl)
    calls = []
    runtime_environments = []
    live_phase_path = Path(os.environ["PHYSICAL_WATCHDOG_PHASE_PATH"]).resolve()
    assert live_phase_path.is_absolute()
    assert live_phase_path.parent.is_dir()
    assert not live_phase_path.exists()

    def archive_phase(label: str, *, remove_live: bool) -> None:
        assert live_phase_path.is_file()
        archive_path = tmp_path / "watchdog_phase_archive" / f"{label}.json"
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(live_phase_path, archive_path)
        if remove_live:
            live_phase_path.unlink()

    real_identity = h100_anchor._require_v11_watchdog_worker_identity

    def observe_identity(**kwargs):
        identity = real_identity(**kwargs)
        calls.append(identity)
        return identity

    monkeypatch.setattr(h100_anchor, "_require_v11_watchdog_worker_identity", observe_identity)
    real_runtime_envelope = h100_anchor._check_v11_runtime_envelope

    def observe_runtime_envelope(comm, **kwargs):
        environment = real_runtime_envelope(comm, **kwargs)
        runtime_environments.append(environment)
        return environment

    monkeypatch.setattr(h100_anchor, "_check_v11_runtime_envelope", observe_runtime_envelope)

    for phase, candidate_id, plan_path, plan, plan_sha, action in (
        ("A1_q3", "round10_p_up", r10_plan_path, r10_plan, r10_plan_sha, "p_up"),
        ("R9_H8", "v11_r9_h8", h_plan_path, h_plan, h_plan_sha, "h_refine"),
    ):
        run_root = (
            Path(contract["artifact_prefix"])
            / contract["phases"]["P3" if phase == "A1_q3" else "P4"]["root"]
            / "run"
        )
        def accepted_inputs(**_kwargs):
            return (
                plan,
                plan_sha,
                {
                    "action": action,
                    "accepted_parent_selection_sha256": selection_sha,
                    "acceptance_contract_sha256": acceptance_sha,
                },
            )

        monkeypatch.setattr(h100_anchor, "_validate_accepted_candidate_inputs", accepted_inputs)
        argv = [
            "--case",
            "round1_candidate_mpi1",
            "--run-root",
            str(run_root),
            "--candidate-plan",
            str(plan_path),
            "--candidate-id",
            candidate_id,
            "--candidate-acceptance-contract",
            str(acceptance_path),
            "--candidate-parent-selection-record",
            str(selection_path),
            "--primary-diagnostic-phase",
            phase,
            "--primary-diagnostic-contract",
            str(contract_path),
            "--direct-factor-backend",
            "mumps",
            "--same-lu-solve-residual-correction",
        ]
        with pytest.raises(MeshSentinel, match="reached real h100 main mesh builder"):
            h100_anchor.main(argv)
        partial_path = run_root / "task43_v11_partial_terminal.json"
        assert partial_path.is_file()
        partial = json.loads(partial_path.read_text(encoding="utf-8"))
        assert partial["phase"] == phase
        assert partial["official_result"] is False
        assert partial["passed"] is False
        archive_phase(phase, remove_live=True)

    assert len(calls) >= 6
    assert [item["phase"] for item in run_impl_controls] == ["A1_q3", "R9_H8"]
    assert all(item["same_lu_tightening_enabled"] is False for item in run_impl_controls)
    assert extra_helper_calls == []
    assert all(item["direct_watchdog_parent_verified"] for item in calls)
    assert all(item["tracer_descends_from_watchdog"] for item in calls)
    assert all(
        all(tid["cpu_list"] == [1] for tid in item["worker_tid_affinities"])
        for item in calls
    )
    for key in (
        "worker_pid",
        "worker_parent_pid",
        "worker_start_ticks",
        "watchdog_pid",
        "watchdog_start_ticks",
        "tracer_pid",
        "tracer_start_ticks",
        "phase_path",
    ):
        assert len({item[key] for item in calls}) == 1

    # Run the actual P2 CLI through plan construction and ledger creation, then
    # stop at its existing mesh-authority audit boundary, all under tmp_path.
    monkeypatch.setattr(round1_candidates, "ROOT", repository)
    monkeypatch.setattr(round1_candidates, "DEFAULT_ACCEPTANCE", acceptance_path)
    monkeypatch.setattr(
        round1_candidates,
        "_check_v11_runtime_envelope",
        observe_runtime_envelope,
    )
    output_root = (repository / contract["phases"]["P2"]["plan_output_path"]).parent.parent
    shutil.rmtree(output_root)
    monkeypatch.setattr(round1_candidates, "DEFAULT_OUTPUT", output_root)
    monkeypatch.setattr(
        round1_candidates,
        "_load_v11_primary_contract",
        lambda _path: (contract, contract_sha),
    )
    monkeypatch.setattr(
        round1_candidates,
        "_v11_input_snapshot",
        lambda _contract, roles: {role: {"path": "isolated", "sha256": "fixture"} for role in roles},
    )
    monkeypatch.setattr(
        round1_candidates,
        "_v11_source_snapshot",
        lambda: {"benchmarks/fake_source.py": "source-sha"},
    )
    monkeypatch.setattr(
        round1_candidates,
        "_load_accepted_parent_state",
        lambda *_args, **_kwargs: {"parent_independent_fe_dofs": 100},
    )
    monkeypatch.setattr(
        round1_candidates,
        "_build_v11_seed8_plan",
        lambda *_args, **_kwargs: h_plan,
    )

    class P2AuditSentinel(RuntimeError):
        pass

    def stop_at_p2_audit(*, plan_path, **_kwargs):
        assert plan_path.is_file()
        assert json.loads(plan_path.read_text(encoding="utf-8"))["task43_candidate"]["candidate_id"] == "v11_r9_h8"
        raise P2AuditSentinel("reached existing P2 mesh authority audit boundary")

    monkeypatch.setattr(round1_candidates, "_audit_plan", stop_at_p2_audit)
    with pytest.raises(P2AuditSentinel, match="existing P2 mesh authority"):
        round1_candidates.main(
            [
                "--accepted-parent-selection-record",
                str(selection_path),
                "--primary-diagnostic-contract",
                str(contract_path),
                "--output-root",
                str(output_root),
            ]
        )
    assert (output_root / "plans/v11_r9_h8.json").is_file()
    archive_phase("P2", remove_live=False)

    assert len(runtime_environments) == 3
    for environment in runtime_environments:
        assert environment["petsc_scalar_type"]
        assert environment["petsc_int_type"]
        assert all(value == "1" for value in environment["v11_math_threads"].values())
        assert environment["v11_worker_local_environment"] == {
            "HWLOC_COMPONENTS": "-x86",
            "OMPI_MCA_pml": "ob1",
        }
        assert environment["v11_mumps_available"] is True
        assert all(
            tid["cpu_list"] == [1]
            for tid in environment["v11_watchdog_worker_identity"]["worker_tid_affinities"]
        )
    runtime_evidence = {
        "schema": "task43.v11.p1.main_sentinel_runtime_identity.v1",
        "environments": runtime_environments,
        "worker_identity_checkpoints": calls,
        "run_impl_controls": run_impl_controls,
        "forbidden_extra_correction_helper_calls": extra_helper_calls,
        "phase_path": str(live_phase_path),
        "phase_archives": {
            label: str(tmp_path / "watchdog_phase_archive" / f"{label}.json")
            for label in ("A1_q3", "R9_H8", "P2")
        },
        "claim_scope": "actual pytest worker and WorkflowLedger observations through each real main mesh-before-solve sentinel only; no solver or PDE stage was entered; extra-correction absence after solve is not established by this sentinel and must be established from saved raw-vector/formal run evidence",
    }
    runtime_evidence_path = tmp_path / "main_sentinel_runtime_identity.json"
    runtime_evidence_path.write_text(
        json.dumps(runtime_evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    def traced_child(label: str, exit_code: int) -> None:
        child = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import time; time.sleep(0.15); raise SystemExit(" + str(exit_code) + ")",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        proc_path = Path(f"/proc/{child.pid}")
        deadline = time.monotonic() + 2.0
        start_ticks = None
        tracer_pid = 0
        while time.monotonic() < deadline and proc_path.is_dir():
            try:
                stat_fields = (proc_path / "stat").read_text(encoding="ascii").rsplit(")", 1)[1].split()
                status_lines = (proc_path / "status").read_text(encoding="ascii").splitlines()
                start_ticks = int(stat_fields[19])
                tracer_pid = int(
                    next(line for line in status_lines if line.startswith("TracerPid:")).split(":", 1)[1]
                )
            except (OSError, StopIteration, ValueError, IndexError):
                time.sleep(0.01)
                continue
            if tracer_pid > 0:
                break
            time.sleep(0.01)
        assert start_ticks is not None
        assert tracer_pid == calls[-1]["tracer_pid"]
        stdout, stderr = child.communicate(timeout=5.0)
        assert child.returncode == exit_code, (stdout, stderr)
        after_start_ticks = None
        if proc_path.is_dir():
            try:
                fields = (proc_path / "stat").read_text(encoding="ascii").rsplit(")", 1)[1].split()
                after_start_ticks = int(fields[19])
            except (OSError, ValueError, IndexError):
                after_start_ticks = None
        assert after_start_ticks != start_ticks
        evidence = {
            "schema": "task43.v11.p1.traced_child_cleanup.v1",
            "label": label,
            "worker_pid": os.getpid(),
            "watchdog_parent_pid": calls[-1]["watchdog_pid"],
            "worker_tracer_pid": calls[-1]["tracer_pid"],
            "child_pid": child.pid,
            "child_parent_pid": os.getpid(),
            "child_start_ticks": start_ticks,
            "child_tracer_pid": tracer_pid,
            "expected_exit_code": exit_code,
            "observed_exit_code": child.returncode,
            "child_reaped": after_start_ticks != start_ticks,
            "direct_watchdog_worker": False,
        }
        evidence_path = tmp_path / "traced_child_cleanup" / f"{label}.json"
        evidence_path.parent.mkdir(parents=True, exist_ok=True)
        evidence_path.write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    traced_child("normal_exit", 0)
    traced_child("controlled_fault_exit", 7)
