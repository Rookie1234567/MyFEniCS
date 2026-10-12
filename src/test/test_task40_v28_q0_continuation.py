"""Focused contracts for V28 continuation routing and its live allocation gate."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from types import SimpleNamespace

import pytest


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _passing_readback() -> dict[str, object]:
    components = {
        name: {"active_block": {"relative": 0.0}, "native_off_block_relative": 0.0}
        for name in ("volume", "minus_D", "C", "Hhat")
    }
    artifact = {"path": "v28_q0_csr_readback.npz", "bytes": 3, "sha256": "a" * 64}
    return {
        "q0_case_1_full_csr_vs_native_total": {"relative": 0.0},
        "q0_case_2_full_csr_vs_native_total": {"relative": 0.0},
        "q0_case_1_csr_trace_port_masked_components_vs_native": components,
        "q0_case_1_trace_plus_port_vs_full_csr": {"relative": 0.0},
        "relative_error_limit": 1.0e-11,
        "all_gates_passed": True,
        "csr_readback_artifact": artifact,
    }


def test_v28_service_selector_binds_manifest_state_dispatch_policy(monkeypatch, tmp_path):
    from scripts import task40_v20_service_workflow as service

    repo = tmp_path
    monkeypatch.setattr(service, "V28_ARTIFACT_ROOT", Path("artifacts/v28"))
    monkeypatch.setattr(service, "V28_PATTERN_MANIFEST_RELATIVE", Path("results/pattern.json"))
    pattern_path = repo / service.V28_PATTERN_MANIFEST_RELATIVE
    pattern_path.parent.mkdir(parents=True)
    pattern_path.write_text("immutable pattern", encoding="utf-8")
    pattern_sha = _sha(pattern_path)
    monkeypatch.setattr(service, "V28_PATTERN_MANIFEST_SHA256", pattern_sha)
    campaign_sha = "c" * 64
    monkeypatch.setattr(service, "TASK40_V28_CAMPAIGN_SHA256", campaign_sha)
    donor = {"producer_identity": {"producer_run_id": "fixed-v26"}}
    monkeypatch.setattr(service, "verify_v27_v26_donor_import", lambda **_kwargs: donor)
    selector_path = repo / service.V28_ARTIFACT_ROOT / "selector.json"
    selector_path.parent.mkdir(parents=True)
    input_path = repo / "input.dat"
    input_path.write_text("fixture", encoding="utf-8")
    continuation_path = pattern_path.with_name(service.V28_CONTINUATION_MANIFEST_NAME)
    selector = {
        "schema": "task40extra.review_v28_q0_continuation_operation.v1",
        "operation": service.V28_CONTINUATION_OPERATION,
        "campaign_window_sha256": campaign_sha,
        "input_sha256": service._sha256_file(input_path),
        "model_profile": service.V28_TARGET_PROFILE,
        "stop_stage": "selected_reference_q_csr",
        "donor_import": donor,
        "pattern_manifest_path": str(pattern_path.resolve()),
        "pattern_manifest_sha256": pattern_sha,
        "continuation_manifest_path": str(continuation_path.resolve()),
        "continuation_policy": service.V28_CONTINUATION_POLICY,
    }
    selector_path.write_text(json.dumps(selector), encoding="utf-8")

    binding = service._bind_v28_q0_continuation_selector(
        selector_path,
        input_path=input_path,
        campaign_registration={"version": "V28", "sha256": campaign_sha},
        profile=service.V28_TARGET_PROFILE,
        stop_stage="selected_reference_q_csr",
        repo_root=repo,
    )
    assert binding["selector_sha256"] == _sha(selector_path)

    selector["continuation_policy"] = "fill always"
    selector_path.write_text(json.dumps(selector), encoding="utf-8")
    with pytest.raises(ValueError, match="V28 selector or V27 donor/pattern identity"):
        service._bind_v28_q0_continuation_selector(
            selector_path,
            input_path=input_path,
            campaign_registration={"version": "V28", "sha256": campaign_sha},
            profile=service.V28_TARGET_PROFILE,
            stop_stage="selected_reference_q_csr",
            repo_root=repo,
        )


def test_v28_action_selector_covers_pending_readback_and_factor_only():
    from src.runners.task40_v20_stage_runner import _v28_continuation_action

    assert _v28_continuation_action("NUMERIC_FILL_INCOMPLETE", False) == "fill_and_readback"
    assert _v28_continuation_action("COMPLETE_CSR", False) == "readback_and_factor"
    assert _v28_continuation_action("COMPLETE_CSR", True) == "factor_only"


def test_v28_native_pass_can_be_reused_across_current_window_with_bound_identity(tmp_path):
    from src.runners.task40_v20_stage_runner import (
        _load_matching_v28_native_qualification,
    )

    repo = tmp_path
    artifact_root = repo / "results/task40extra_nonseparable_0p7nm/attempt-a"
    artifact_root.mkdir(parents=True)
    pattern = repo / "pattern-v27.json"
    pattern.write_text("immutable pattern", encoding="utf-8")
    readback_path = artifact_root / "v28_q0_csr_readback.npz"
    readback_path.write_bytes(b"raw readback")
    manifest_path = repo / "csr" / "continuation.json"
    manifest_path.parent.mkdir()
    csr_hashes = {name: (name[0] * 64) for name in ("indptr", "indices", "data")}
    old_window_sha = "b" * 64
    current_window_sha = "c" * 64
    readback_artifact = {
        "path": readback_path.name,
        "bytes": readback_path.stat().st_size,
        "sha256": _sha(readback_path),
    }
    readback = _passing_readback()
    readback["csr_readback_artifact"] = readback_artifact
    qualification_path = artifact_root / "v28_q0_native_qualification.json"
    identity = {
        "source_sha": "d" * 40,
        "run_id": "fixture-run",
        "input_sha256": "e" * 64,
        "physical_model_sha256": "f" * 64,
        "campaign_window_sha256": old_window_sha,
        "mode_manifest_sha256": "1" * 64,
        "ordered_mode_key_sha256": "2" * 64,
    }
    qualification = {
        "schema": "task40extra.review_v28_q0_native_qualification.v1",
        "status": "PASS_COMPLETE_Q0_CSR_NATIVE_READBACK",
        "source_identity": identity,
        "donor_identity_sha256": "3" * 64,
        "campaign_window_sha256": old_window_sha,
        "original_pattern_manifest": {"path": str(pattern), "sha256": _sha(pattern)},
        "csr_manifest_path": str(manifest_path.resolve()),
        "csr_artifact_hashes": csr_hashes,
        "csr_shape": [4, 4],
        "stored_structural_slots": 6,
        "readback": readback,
        "readback_artifact": readback_artifact,
    }
    qualification_path.write_text(json.dumps(qualification), encoding="utf-8")
    manifest = {
        "status": "COMPLETE_CSR",
        "shape": [4, 4],
        "stored_structural_slots": 6,
        "csr_artifacts": {
            name: {"sha256": value, "bytes": 1}
            for name, value in csr_hashes.items()
        },
        "native_qualification": {
            "path": str(qualification_path),
            "sha256": _sha(qualification_path),
            "status": qualification["status"],
        },
    }

    binding = _load_matching_v28_native_qualification(
        repo_root=repo,
        manifest_path=manifest_path,
        manifest=manifest,
        expected_pattern_path=pattern,
        expected_pattern_sha256=_sha(pattern),
        donor_identity_sha256="3" * 64,
        input_sha256=identity["input_sha256"],
        physical_model_sha256=identity["physical_model_sha256"],
        run_id=identity["run_id"],
        campaign_window_sha256=current_window_sha,
        mode_manifest_sha256=identity["mode_manifest_sha256"],
        ordered_mode_key_sha256=identity["ordered_mode_key_sha256"],
        sha256_file=_sha,
    )
    assert binding is not None
    assert binding[1]["campaign_window_sha256"] == old_window_sha

    qualification["readback"]["q0_case_1_full_csr_vs_native_total"]["relative"] = -1.0
    qualification_path.write_text(json.dumps(qualification), encoding="utf-8")
    manifest["native_qualification"]["sha256"] = _sha(qualification_path)
    assert _load_matching_v28_native_qualification(
        repo_root=repo,
        manifest_path=manifest_path,
        manifest=manifest,
        expected_pattern_path=pattern,
        expected_pattern_sha256=_sha(pattern),
        donor_identity_sha256="3" * 64,
        input_sha256=identity["input_sha256"],
        physical_model_sha256=identity["physical_model_sha256"],
        run_id=identity["run_id"],
        campaign_window_sha256=current_window_sha,
        mode_manifest_sha256=identity["mode_manifest_sha256"],
        ordered_mode_key_sha256=identity["ordered_mode_key_sha256"],
        sha256_file=_sha,
    ) is None


def test_v28_actual_saved_q0_allocation_gate_is_semantically_bounded(tmp_path):
    from src.runners.task40_v20_stage_runner import (
        _make_saved_q0_allocation_gate,
    )

    class Blocked(Exception):
        def __init__(self, stage, facts):
            super().__init__(stage)
            self.stage = stage
            self.facts = facts

    current = {"memory_current_bytes": 100}

    def admission(stage, requested, **_kwargs):
        if requested >= 100:
            raise Blocked(
                stage,
                {
                    "stage": stage,
                    "host_effective_available_bytes": 900,
                    "current_process_cgroup": {"memory_current_bytes": current["memory_current_bytes"]},
                },
            )
        return {
            "host_effective_available_bytes": 1_000,
            "current_process_cgroup": {"memory_current_bytes": current["memory_current_bytes"]},
        }

    gate, store, records, timing = _make_saved_q0_allocation_gate(
        output_directory=tmp_path,
        disk_reserve_bytes=10,
        resource_admission=admission,
        resource_sample=lambda: {},
        cgroup_snapshot=lambda: dict(current),
        blocked_exception=Blocked,
        disk_usage=lambda _path: SimpleNamespace(free=10_000),
    )
    gate("task40_v28_q_projection_support/cell/0", {"workspace_bytes": 20})
    current["memory_current_bytes"] = 300
    gate("task40_v28_q_projection_support/cell/1", {"workspace_bytes": 40})
    with pytest.raises(Blocked):
        gate("task40_v28_q_projection_support/cell/2", {"workspace_bytes": 100})

    projection = store["q0_projection/support"]
    assert projection["observation_count"] == 3
    assert projection["maximum_additional_object_upper_bound_bytes"] == 100
    assert projection["first_original_stage_label"] == "task40_v28_q_projection_support/cell/0"
    assert projection["last_original_stage_label"] == "task40_v28_q_projection_support/cell/2"
    assert projection["original_failure_stage_label"] == "task40_v28_q_projection_support/cell/2"
    assert projection["maximum_task_cgroup_memory_current_bytes"] == 300
    assert "original_stage_labels" not in projection
    assert records() == list(store.values())
    assert timing["calls"] == 3
    assert timing["seconds"] >= 0.0

    with pytest.raises(Blocked):
        gate("task40_v28_q_hhat_sparse_scatter/port/7", {"disk_payload_bytes": 20_000})
    hhat = store["q0_H/sparse_scatter"]
    assert hhat["passed"] is False
    assert hhat["original_failure_stage_label"] == "task40_v28_q_hhat_sparse_scatter/port/7"


def test_v28_completed_observer_runs_after_direct_h_volume_and_surface_scatter():
    import numpy as np
    from scipy import sparse

    from src.solvers.task40_v10_p6_yorbit import (
        _accumulate_bounded_q_pattern_values,
    )

    indices = np.asarray([0, 1, 0, 1], dtype=np.int32)
    target = sparse.csr_matrix(
        (
            np.zeros(4, dtype=np.complex128),
            indices,
            np.asarray([0, 2, 4], dtype=np.int32),
        ),
        shape=(2, 2),
    )
    blocks = {(0, 0): target}
    identity = sparse.eye(2, format="csr", dtype=np.complex128)
    expected = {
        "ports/Hhat/direct_sparse_q0": ((1, 1), 7.0 + 2.0j),
        "volume/cell/0": ((0, 0), 2.0 + 1.0j),
        "surface/facet/0": ((1, 0), 3.0 - 4.0j),
    }

    class Action:
        q0_trace_rows = 1
        port_count = 1

        def q0_hhat_sparse_term(self, *, allocation_gate):
            allocation_gate("fixture/hhat", {"matrix_payload_bytes": 16})
            return sparse.csr_matrix(
                np.asarray([[7.0 + 2.0j]], dtype=np.complex128)
            )

        def iter_reduced_contributions(self, **kwargs):
            assert kwargs["include_hhat"] is False
            yield (
                np.asarray([0], dtype=np.int32),
                np.asarray([0], dtype=np.int32),
                np.asarray([[2.0 + 1.0j]], dtype=np.complex128),
                "volume/cell/0",
            )
            yield (
                np.asarray([1], dtype=np.int32),
                np.asarray([0], dtype=np.int32),
                np.asarray([[3.0 - 4.0j]], dtype=np.complex128),
                "surface/facet/0",
            )

    completed = []

    def observe_completed(rows, columns, values, label, timings):
        assert set(timings) == {
            "generation_seconds",
            "projection_seconds",
            "accumulation_seconds",
        }
        assert all(math.isfinite(value) and value >= 0.0 for value in timings.values())
        coordinate, value = expected[label]
        assert blocks[(0, 0)][coordinate] == value
        if label == "ports/Hhat/direct_sparse_q0":
            assert rows is None and columns is None
            np.testing.assert_array_equal(values, np.asarray([7.0 + 2.0j]))
        else:
            assert rows is not None and columns is not None and values is not None
        completed.append(label)

    result, audit = _accumulate_bounded_q_pattern_values(
        Action(),
        (identity,),
        blocks,
        allocation_gate=lambda _label, _facts: None,
        assembly_strategy="fixture",
        pattern_algorithm="fixture",
        patterns={},
        pattern_seconds=0.0,
        contribution_completed_observer=observe_completed,
        projection_method="sparse_local",
        direct_hhat=True,
    )

    assert result is blocks
    assert completed == list(expected)
    assert audit["numeric_contribution_count"] == 2
    assert audit["hhat_numeric_contribution_count"] == 0
    assert audit["numeric_contribution_count_including_direct_hhat"] == 3


def test_v28_checker_rejects_csr_path_escape_before_payload_hash(tmp_path, monkeypatch):
    from scripts import task40_v20_service_workflow as service

    monkeypatch.setattr(service, "ROOT", tmp_path)
    monkeypatch.setattr(service, "V28_PATTERN_MANIFEST_RELATIVE", Path("pattern.json"))
    pattern = tmp_path / "pattern.json"
    pattern.write_text(
        json.dumps({"schema": "task40extra.review_v27_saved_q0_csr.v1", "status": "NUMERIC_FILL_INCOMPLETE"}),
        encoding="utf-8",
    )
    pattern_sha = _sha(pattern)
    monkeypatch.setattr(service, "V28_PATTERN_MANIFEST_SHA256", pattern_sha)

    outside = tmp_path / "outside" / "indptr.bin"
    outside.parent.mkdir()
    outside.write_bytes(b"x")
    manifest_path = tmp_path / "csr" / "manifest.json"
    manifest_path.parent.mkdir()
    manifest = {
        "schema": "task40extra.review_v28_saved_q0_csr.v1",
        "status": "COMPLETE_CSR",
        "shape": [1, 1],
        "stored_structural_slots": 1,
        "original_pattern_manifest": {"sha256": pattern_sha},
        "continuation_event": {
            "old_manifest_modified": False,
            "full_csr_copy_created": False,
            "data_restart_policy": "clear_all_values_before_each_numeric_pass",
        },
        "csr_artifacts": {
            name: {
                "path": str(outside),
                "bytes": outside.stat().st_size,
                "sha256": _sha(outside),
            }
            for name in ("indptr", "indices", "data")
        },
    }
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    stop_stage = "fixture_stop"
    donor = {}
    donor_sha = hashlib.sha256(json.dumps(donor, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    selector_path = tmp_path / "selector.json"
    selector = {
        "schema": "task40extra.review_v28_q0_continuation_operation.v1",
        "operation": service.V28_CONTINUATION_OPERATION,
        "stop_stage": stop_stage,
        "campaign_window_sha256": service.TASK40_V28_CAMPAIGN_SHA256,
        "donor_import": donor,
        "continuation_policy": service.V28_CONTINUATION_POLICY,
        "pattern_manifest_path": str(pattern),
        "pattern_manifest_sha256": pattern_sha,
    }
    selector_path.write_text(json.dumps(selector), encoding="utf-8")
    selector_sha = _sha(selector_path)
    operation = {
        "schema": "task40extra.review_v28_q0_continuation_stage.v1",
        "operation": service.V28_CONTINUATION_OPERATION,
        "status": "PASS_COMPLETE_Q0_CSR",
        "stop_stage": stop_stage,
        "selector_sha256": selector_sha,
        "donor_import_identity": donor,
        "donor_import_identity_sha256": donor_sha,
        "current_execution_identity": {"campaign_window_sha256": service.TASK40_V28_CAMPAIGN_SHA256},
        "csr_manifest_path": str(manifest_path),
        "csr_manifest_sha256": _sha(manifest_path),
        "csr_status": "COMPLETE_CSR",
        "complete_numeric_csr": True,
        "official_result": False,
        "saved_only_no_fe_or_native_rebuild": True,
        "source_pattern_reused": True,
        "pattern_manifest_sha256": pattern_sha,
    }
    output = tmp_path / "output"
    output.mkdir()
    operation_path = output / "operation.json"
    operation_path.write_text(json.dumps(operation), encoding="utf-8")
    partial = {
        "official_result": False,
        "v28_q0_continuation": {
            "operation": operation,
            "operation_path": operation_path.name,
            "operation_sha256": _sha(operation_path),
            "selector_path": str(selector_path),
            "selector_sha256": selector_sha,
            "donor_import_identity_sha256": donor_sha,
        },
    }
    hash_calls = []
    original_hash = service._sha256_owned_payload

    def track_payload_hash(path):
        hash_calls.append(Path(path))
        return original_hash(path)

    monkeypatch.setattr(service, "_sha256_owned_payload", track_payload_hash)
    hashes = {}
    checks = service._v28_saved_q0_continuation_checks(
        output_directory=output,
        partial=partial,
        expected_stop_stage=stop_stage,
        artifact_hashes=hashes,
    )

    assert checks["v28_complete_csr_requires_all_three_payload_hashes"] is False
    assert hash_calls == []
    assert not any(key.startswith("v28_csr_") for key in hashes)
