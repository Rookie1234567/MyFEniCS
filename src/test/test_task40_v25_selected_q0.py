from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers.task40_v25_selected_q0 import (
    _iter_saved_surface_functionals,
    _write_surface_functional_stream,
)


def _entry(mode_key, *, coupling_rows, coupling_values, projection_rows, projection_values):
    return SimpleNamespace(
        mode_key=mode_key,
        normalization_h=2.0,
        coupling_rows=np.asarray(coupling_rows, dtype=np.int32),
        coupling_values=np.asarray(coupling_values, dtype=np.complex128),
        projection_rows=np.asarray(projection_rows, dtype=np.int32),
        projection_values=np.asarray(projection_values, dtype=np.complex128),
    )


def test_saved_surface_stream_preserves_nonzero_internal_values_and_drops_only_exact_zeros(tmp_path):
    mode = SimpleNamespace(side="bottom", m=1, n=-1, polarization="s")
    path = tmp_path / "surface.bin"
    facts = _write_surface_functional_stream(
        path,
        [
            _entry(
                (3, "bottom", 1, -1, "s"),
                coupling_rows=[2, 3, 4],
                coupling_values=[1.0, 0.0, 2.0],
                projection_rows=[3],
                projection_values=[7.0],
            )
        ],
        selected_indices=np.asarray([3], dtype=np.int64),
        local_modes=(mode,),
        local_h=np.asarray([2.0]),
        allowed_rows_by_side=(np.arange(10, dtype=np.int64), np.arange(10, dtype=np.int64)),
        interior_rows=np.asarray([3], dtype=np.int64),
    )
    assert facts["internal_row_entry_count"] == {"B": 1, "D": 1}
    assert facts["internal_nonzero_entry_count"] == {"B": 0, "D": 1}
    raw = path.read_bytes()
    assert len(raw) == facts["bytes"]

    entries = list(
        _iter_saved_surface_functionals(
            path,
            selected_indices=np.asarray([3], dtype=np.int64),
            local_modes=(mode,),
            local_h=np.asarray([2.0]),
            mode_rows=tuple({"mode_index": index} for index in range(4)),
            interior_rows=np.asarray([3], dtype=np.int64),
        )
    )
    assert len(entries) == 1
    np.testing.assert_array_equal(entries[0].coupling_rows, [2, 4])
    np.testing.assert_array_equal(entries[0].coupling_values, [1.0, 2.0])
    np.testing.assert_array_equal(entries[0].projection_rows, [3])
    np.testing.assert_array_equal(entries[0].projection_values, [7.0])


def test_surface_stream_retains_incomplete_raw_prefix(tmp_path):
    mode = SimpleNamespace(side="bottom", m=0, n=0, polarization="p")
    path = tmp_path / "surface.bin"
    with pytest.raises(ValueError, match="emitted 1 modes; expected 2"):
        _write_surface_functional_stream(
            path,
            [
                _entry(
                    (3, "bottom", 0, 0, "p"),
                    coupling_rows=[1], coupling_values=[2.0],
                    projection_rows=[2], projection_values=[3.0],
                )
            ],
            selected_indices=np.asarray([3, 5], dtype=np.int64),
            local_modes=(mode, mode),
            local_h=np.asarray([2.0, 2.0]),
            allowed_rows_by_side=(np.arange(10, dtype=np.int64), np.arange(10, dtype=np.int64)),
            interior_rows=np.empty(0, dtype=np.int64),
        )
    partial = Path(str(path) + ".partial")
    sidecar = Path(str(partial) + ".json")
    assert partial.is_file()
    facts = json.loads(sidecar.read_text(encoding="utf-8"))
    assert facts["status"] == "INCOMPLETE_RETAINED"
    assert facts["completed_mode_count"] == 1
    assert facts["expected_mode_count"] == 2
    assert hashlib.sha256(partial.read_bytes()).hexdigest() == facts["sha256"]


def test_direct_provider_uses_noncontiguous_original_mode_indices(monkeypatch):
    from src.solvers import fullspace_dtn_action
    from src.solvers.original_port_blocks import DiagonalOriginalPortBlock
    from src.solvers.p6_cell_condensed_action import build_p6_global_direct_provider_from_surface

    captured = {}

    def fake_iter(modes, *_args, **kwargs):
        captured["mode_indices"] = tuple(kwargs["mode_indices"])
        captured["precomputed_mode_rows"] = kwargs["precomputed_mode_rows"]
        captured["manifest_sha"] = kwargs["precomputed_physical_manifest_sha256"]
        return iter(())

    monkeypatch.setattr(fullspace_dtn_action, "iter_fullspace_dtn_functionals_from_surface", fake_iter)
    modes = tuple(
        SimpleNamespace(side="bottom" if index % 2 == 0 else "top", m=index, n=-index, polarization="s")
        for index in range(4)
    )
    keys = tuple((index, mode.side, mode.m, mode.n, mode.polarization) for index, mode in enumerate(modes))
    condensed = SimpleNamespace(
        appended_rows=2,
        full_rows=8,
        trace_constraints=SimpleNamespace(original_to_active={0: 0, 1: 1, 2: 2, 3: 3}),
    )
    provider = build_p6_global_direct_provider_from_surface(
        condensed,
        modes,
        {},
        object(),
        object(),
        mode_indices=(1, 3),
        precomputed_mode_rows=tuple({"mode_index": index} for index in range(4)),
        precomputed_physical_manifest_sha256="a" * 64,
        interior_rows=np.empty(0, dtype=np.int32),
    )
    hp = DiagonalOriginalPortBlock(np.asarray([1, 2, 3, 4], dtype=np.complex128), keys)
    provider.bind_original_port_block(hp, mode_indices=(1, 3))
    tuple(provider._entry_factory())

    assert provider.mode_count == 2
    assert provider._original_h_mode_indices == (1, 3)
    assert provider._expected_mode_keys == (keys[1], keys[3])
    np.testing.assert_array_equal(provider._expected_h_values, [2, 4])
    assert captured == {
        "mode_indices": (1, 3),
        "precomputed_mode_rows": tuple({"mode_index": index} for index in range(4)),
        "manifest_sha": "a" * 64,
    }


def _write_v25_q0_checker_fixture(output: Path):
    from scripts.task40_v20_service_workflow import _sha256_file

    output.mkdir(parents=True, exist_ok=True)
    mode_sha = "a" * 64
    key_sha = "b" * 64
    (output / "v20_stage_preflight.json").write_text(
        json.dumps(
            {
                "target_mode_inventory": {
                    "mode_manifest_sha256": mode_sha,
                    "ordered_mode_key_sha256": key_sha,
                }
            }
        ),
        encoding="utf-8",
    )
    replay_path = output / "consumer_replay.npz"
    arrays = {
        "input_q0_case_1": np.asarray([1.0, 0.0], dtype=np.complex128),
        "input_q0_case_2": np.asarray([0.0, 2.0], dtype=np.complex128),
        "input_q4_pair": np.asarray([0.0, 3.0], dtype=np.complex128),
        "stream_q0_output_case_1": np.asarray([2.0, 1.0], dtype=np.complex128),
        "stream_q0_output_case_2": np.asarray([1.0, 3.0], dtype=np.complex128),
        "native_q0_output_case_1": np.asarray([2.0, 1.0], dtype=np.complex128),
        "native_q0_output_case_2": np.asarray([1.0, 3.0], dtype=np.complex128),
        "stream_q4_output_from_q0_case_1": np.zeros(2, dtype=np.complex128),
        "native_q4_output_from_q0_case_1": np.zeros(2, dtype=np.complex128),
        "stream_q0_output_from_q4": np.zeros(2, dtype=np.complex128),
        "native_q0_output_from_q4": np.zeros(2, dtype=np.complex128),
        "stream_q4_output_case_pair": np.asarray([4.0, 1.0], dtype=np.complex128),
        "native_q4_output_case_pair": np.asarray([4.0, 1.0], dtype=np.complex128),
    }
    for name, values in (
        ("volume", [1.0, 2.0]),
        ("C", [2.0, 4.0]),
        ("minus_D", [3.0, 6.0]),
        ("Hhat", [4.0, 8.0]),
    ):
        arrays[f"component_{name}_stream"] = np.asarray(values, dtype=np.complex128)
        arrays[f"component_{name}_native"] = np.asarray(values, dtype=np.complex128)
    with replay_path.open("wb") as stream:
        np.savez(stream, **arrays)

    error = {"absolute": 0.0, "relative_to_component": 0.0}
    operation = {
        "schema": "task40extra.review_v25_selected_reference_q0_consumer.v1",
        "status": "PASS_COMPLETE_Q0_STREAM",
        "selected_q": 0,
        "paired_q": 4,
        "official_result": False,
        "factor_or_solve_built": False,
        "ksp_created": False,
        "pde_solved": False,
        "mode_inventory": {
            "mode_manifest_sha256": mode_sha,
            "ordered_mode_key_sha256": key_sha,
            "q0_alias_count_actual": 2,
            "q4_alias_count_actual": 2,
            "selected_twist_alias_count_actual": 4,
        },
        "pre_fe_resource_gate": {
            "task_cgroup_gate_passed": True,
            "swap_gate_status": "PASS_ZERO_TASK_CGROUP_SWAP",
            "explicit_process_tree_cap_bytes": 16 * 1024**3,
            "disk_gate_passed": True,
        },
        "complete_stream": {
            "schema": "task40extra.review_v25_selected_q0_complete_stream.v1",
            "complete_data_consumer_passed": True,
            "consumer_replay": {
                "q0_replay_relative_errors": [error, error],
                "q0_component_relative_errors": {
                    name: error for name in ("volume", "C", "-D", "Hhat")
                },
                "q0_to_q4_relative_error": error,
                "q4_to_q0_relative_error": error,
                "q4_to_q4_relative_error": error,
                "q0_to_q4_leakage_ratio": 0.0,
                "q4_to_q0_leakage_ratio": 0.0,
                "replay_artifact": {"path": replay_path.name},
            },
        },
        "direct_only_support": {
            "passed": True,
            "internal_B_nonzero_count": 0,
            "internal_D_nonzero_count": 0,
        },
        "original_H_p": {
            "local_global_scaling_error": error,
            "q0_normalized_H_p_identity_max_abs": 0.0,
            "q0_q4_H_p_alias_overlap": 0,
        },
        "saved_artifacts": {
            "complete_consumer_replay": {"path": replay_path.name},
        },
    }
    operation_path = output / "v25_selected_q0_consumer.json"
    partial = {
        "status": "stage_completed",
        "outcome": "STAGE_COMPLETED",
        "official_result": False,
        "selected_reference_q0_consumer": {
            "operation_path": operation_path.name,
        },
        "q_coverage": {"built_q_count": 0, "csr_status": "NOT_BUILT"},
    }

    def persist_identity():
        replay_sha = _sha256_file(replay_path)
        replay_facts = operation["complete_stream"]["consumer_replay"]["replay_artifact"]
        replay_facts.update(
            {"bytes": replay_path.stat().st_size, "sha256": replay_sha}
        )
        operation["saved_artifacts"]["complete_consumer_replay"].update(
            {"bytes": replay_path.stat().st_size, "sha256": replay_sha}
        )
        operation_path.write_text(json.dumps(operation), encoding="utf-8")
        partial["selected_reference_q0_consumer"].update(
            {
                "operation_sha256": _sha256_file(operation_path),
                "operation_status": operation["status"],
            }
        )

    persist_identity()
    return operation, partial, arrays, replay_path, persist_identity


def test_v25_q0_partial_checker_recomputes_raw_vectors_and_artifact_identity(tmp_path):
    from scripts.task40_v20_service_workflow import _v25_selected_q0_readback_checks

    output = tmp_path / "run"
    operation, partial, arrays, replay_path, persist = _write_v25_q0_checker_fixture(output)
    checks = _v25_selected_q0_readback_checks(output_directory=output, partial=partial)
    assert checks
    assert all(checks.values()), checks

    # Refresh all hashes after changing raw evidence so only numerical recomputation
    # can reject this internally self-consistent but incorrect replay.
    arrays["stream_q0_output_case_1"] = arrays["stream_q0_output_case_1"].copy()
    arrays["stream_q0_output_case_1"][0] += 0.25
    with replay_path.open("wb") as stream:
        np.savez(stream, **arrays)
    persist()
    bad_data_checks = _v25_selected_q0_readback_checks(
        output_directory=output, partial=partial
    )
    assert not bad_data_checks["q0_raw_stream_and_native_errors_recomputed"]
    assert not bad_data_checks["q0_stage_status_matches_recomputed_consumer"]

    # A forged status is rejected even when the receipt carries its matching hash.
    operation["status"] = "FORGED_PASS_STATUS"
    persist()
    bad_status_checks = _v25_selected_q0_readback_checks(
        output_directory=output, partial=partial
    )
    assert bad_status_checks["q0_operation_identity_and_status_hash"]
    assert not bad_status_checks["q0_failure_is_retained"]


@pytest.mark.parametrize(
    ("stop_stage", "expected_operation", "build_csr"),
    [
        ("selected_reference_q_consumer", "SELECTED_REFERENCE_Q_CONSUMER", False),
        ("selected_reference_q_build_only", "SELECTED_REFERENCE_Q_BUILD_ONLY", True),
        ("selected_reference_q_csr", "SELECTED_REFERENCE_Q_CSR", True),
    ],
)
def test_v25_service_and_stage_runner_route_frozen_selected_q0(
    tmp_path, monkeypatch, stop_stage, expected_operation, build_csr
):
    from src.io import load_and_resolve
    from scripts import task40_v20_service_workflow as service
    from src.runners import task40_v20_stage_runner as runner
    from src.solvers import task40_v22_operator_probe as probe

    canonical = Path("input/task40extra_0p7nm_engineering/target_original_ny8_operator_probe_v22.dat")
    staged_text = service.render_stage_input(canonical.read_text(encoding="utf-8"), stop_stage)
    stage_root = tmp_path / service.V25_ARTIFACT_ROOT / "stage_inputs" / stop_stage
    stage_root.mkdir(parents=True)
    stage_input = stage_root / canonical.name
    stage_input.write_text(staged_text, encoding="utf-8")
    resolved = load_and_resolve(stage_input).as_jsonable()
    assert resolved["execution"]["task40_execution_stop_stage"] == stop_stage
    assert resolved["execution"]["task40_v22_operator_probe_authorized"] is False

    case = service._parse_case_arguments(
        [str(stage_input), "--task40-v10-campaign-window", "campaign_window_v25.json"]
    )
    assert case[2] == stop_stage

    input_sha = service._sha256_file(stage_input)
    selector = {
        "schema": "task40extra.review_v25_selected_operation.v1",
        "operation": expected_operation,
        "campaign_window_sha256": service.TASK40_V25_CAMPAIGN_SHA256,
        "input_sha256": input_sha,
        "model_profile": service.V25_TARGET_PROFILE,
        "stop_stage": stop_stage,
    }
    selector_path = stage_root / "selected_operation.json"
    selector_path.write_text(json.dumps(selector), encoding="utf-8")
    binding = service._bind_v25_selected_operation_selector(
        selector_path,
        input_path=stage_input,
        campaign_registration={
            "version": "V25",
            "sha256": service.TASK40_V25_CAMPAIGN_SHA256,
        },
        profile=service.V25_TARGET_PROFILE,
        stop_stage=stop_stage,
        repo_root=tmp_path,
    )
    assert binding["operation"] == expected_operation
    assert binding["input_sha256"] == input_sha

    mode_sha, key_sha = "a" * 64, "b" * 64
    modes = (SimpleNamespace(side="bottom", m=0, n=0, polarization="s"),)
    rows = ({"mode_index": 0},)
    monkeypatch.setattr(
        runner,
        "_preflight",
        lambda *_args, **_kwargs: (
            {
                "run_id": resolved["run_id"],
                "source_sha": "c" * 40,
                "input_sha256": resolved["provenance"]["input_sha256"],
                "physical_model_sha256": resolved["provenance"]["physical_model_sha256"],
                "target_mode_inventory": {
                    "mode_manifest_sha256": mode_sha,
                    "ordered_mode_key_sha256": key_sha,
                },
            },
            modes,
            rows,
        ),
    )
    monkeypatch.setattr(
        probe,
        "_resource_admission",
        lambda stage, additional, **kwargs: {
            "stage": stage,
            "additional_object_upper_bound_bytes": additional,
            "host_gate_passed": True,
            "process_tree_gate_passed": True,
            "task_cgroup_gate_passed": True,
            "swap_gate_status": "PASS_ZERO_TASK_CGROUP_SWAP",
        },
    )
    monkeypatch.setattr(runner, "_resource_snapshot", lambda: {})
    from src.io import input_validation
    monkeypatch.setattr(
        input_validation,
        "simulation_config_3d_from_normalized",
        lambda _payload: SimpleNamespace(),
    )
    received = {}

    def fake_q0(_cfg, _axes, **kwargs):
        received.update(kwargs)
        kwargs["allocation_gate"]("fixture_pre_fe", {"additional_payload_bytes": 1})
        operation = {
            "schema": "task40extra.review_v25_selected_reference_q0_consumer.v1",
            "status": "PASS_COMPLETE_Q0_STREAM",
            "selected_q": 0,
            "paired_q": 4,
            "official_result": False,
            "complete_stream": {
                "schema": "task40extra.review_v25_selected_q0_complete_stream.v1"
            },
            "saved_artifacts": {},
        }
        (tmp_path / "run" / "v25_selected_q0_consumer.json").write_text(
            json.dumps(operation), encoding="utf-8"
        )
        return operation

    monkeypatch.setattr(runner, "_resource_snapshot", lambda: {})
    import src.solvers.task40_v25_selected_q0 as q0_module
    monkeypatch.setattr(q0_module, "run_task40_v25_selected_q0_consumer", fake_q0)
    result = runner.run_task40_v20_stage(
        resolved,
        tmp_path / "run",
        source_sha="c" * 40,
    )
    assert result["status"] == "stage_completed"
    assert received["frozen_modes"] is modes
    assert received["frozen_mode_rows"] is rows
    assert received["frozen_mode_manifest_sha256"] == mode_sha
    assert received["expected_ordered_mode_key_sha256"] == key_sha
    assert received["build_csr"] is build_csr
    assert result["summary"]["q_coverage"]["factor_count"] == 0
    assert result["summary"]["official_result"] is False
