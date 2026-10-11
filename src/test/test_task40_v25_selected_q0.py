from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers.task40_v25_selected_q0 import (
    _iter_saved_surface_functionals,
    _q0_reference_surface_inventory,
    _q0_source_mode_rows_from_runtime_view,
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


def test_frozen_mode_identity_uses_ledger_digest_and_rejects_index_or_order_changes():
    from src.solvers.task40_v25_selected_q0 import (
        _mode_key,
        _validate_frozen_mode_identity,
    )

    modes = (
        SimpleNamespace(side="bottom", m=-1, n=0, polarization="s"),
        SimpleNamespace(side="top", m=0, n=1, polarization="p"),
        SimpleNamespace(side="bottom", m=2, n=-1, polarization="s"),
    )
    rows = tuple(
        {
            "mode_index": index,
            "side": mode.side,
            "m": mode.m,
            "n": mode.n,
            "polarization": mode.polarization,
        }
        for index, mode in enumerate(modes)
    )
    # Fixed digest of TARGET_LEDGER's ordered [side, m, n, polarization] payload.
    ledger_digest = "9850c990f87337f9319b04daf5228039af18443832215ae9b867e2626a1cb56d"
    full_keys = tuple(_mode_key(index, mode) for index, mode in enumerate(modes))

    actual_keys, actual_digest = _validate_frozen_mode_identity(
        modes,
        rows,
        expected_ordered_mode_key_sha256=ledger_digest,
        frozen_mode_keys=full_keys,
    )
    assert actual_keys == full_keys
    assert actual_digest == ledger_digest
    assert all(key[0] == row["mode_index"] for key, row in zip(actual_keys, rows, strict=True))

    bad_index_rows = (dict(rows[0]), {**rows[1], "mode_index": 2}, dict(rows[2]))
    with pytest.raises(ValueError, match="preflight mode rows differ"):
        _validate_frozen_mode_identity(
            modes,
            bad_index_rows,
            expected_ordered_mode_key_sha256=ledger_digest,
            frozen_mode_keys=full_keys,
        )

    reordered_modes = tuple(reversed(modes))
    reordered_rows = tuple(
        {
            "mode_index": index,
            "side": mode.side,
            "m": mode.m,
            "n": mode.n,
            "polarization": mode.polarization,
        }
        for index, mode in enumerate(reordered_modes)
    )
    reordered_keys = tuple(
        _mode_key(index, mode) for index, mode in enumerate(reordered_modes)
    )
    with pytest.raises(ValueError, match="mode-key identity differs"):
        _validate_frozen_mode_identity(
            reordered_modes,
            reordered_rows,
            expected_ordered_mode_key_sha256=ledger_digest,
            frozen_mode_keys=reordered_keys,
        )


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


def test_q0_runtime_plane_view_recovers_only_frozen_source_rows():
    from src.solvers.fullspace_dtn_action import (
        FULLSPACE_DTN_MANIFEST_SCHEMA,
        FULLSPACE_DTN_PROFILE,
        _canonical_json_bytes,
    )

    source_rows = [
        {
            "mode_index": 0,
            "side": "bottom",
            "m": 2,
            "n": -1,
            "polarization": "s",
            "classification": "propagating",
            "alpha": {"real": 1.25, "imag": 0.0},
        },
        {
            "mode_index": 1,
            "side": "top",
            "m": 3,
            "n": 1,
            "polarization": "p",
            "classification": "propagating",
            "alpha": {"real": 2.5, "imag": 0.0},
        },
    ]
    payload = {
        "schema": FULLSPACE_DTN_MANIFEST_SCHEMA,
        "profile": FULLSPACE_DTN_PROFILE,
        "mode_count": len(source_rows),
        "modes": source_rows,
    }
    source_sha = hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()
    runtime_rows = [
        {**row, "reference_plane_nm": -10.0 if row["side"] == "bottom" else 130.0}
        for row in source_rows
    ]
    modes = [
        SimpleNamespace(side="bottom", m=2, n=-1, polarization="s"),
        SimpleNamespace(side="top", m=3, n=1, polarization="p"),
    ]

    recovered, identity = _q0_source_mode_rows_from_runtime_view(
        runtime_rows,
        modes,
        expected_manifest_sha256=source_sha,
        boundary_planes_nm_by_side={"bottom": -10.0, "top": 130.0},
    )

    assert list(recovered) == source_rows
    assert identity["source_manifest_sha256"] == source_sha
    assert identity["runtime_view_added_only"] == "reference_plane_nm"
    assert identity["runtime_mode_count_by_side"] == {"bottom": 1, "top": 1}

    changed_other_field = [dict(row) for row in runtime_rows]
    changed_other_field[1]["classification"] = "changed"
    with pytest.raises(ValueError, match="frozen source manifest"):
        _q0_source_mode_rows_from_runtime_view(
            changed_other_field,
            modes,
            expected_manifest_sha256=source_sha,
            boundary_planes_nm_by_side={"bottom": -10.0, "top": 130.0},
        )

    changed_plane = [dict(row) for row in runtime_rows]
    changed_plane[0]["reference_plane_nm"] = -9.0
    with pytest.raises(ValueError, match="actual boundary-plane context"):
        _q0_source_mode_rows_from_runtime_view(
            changed_plane,
            modes,
            expected_manifest_sha256=source_sha,
            boundary_planes_nm_by_side={"bottom": -10.0, "top": 130.0},
        )


def test_q0_reference_inventory_routes_both_real_sides_through_native_mpc_adapter():
    from src.solvers.task40_v22_operator_probe import _V22NativeFacetRule

    def cell_corners(x0, y0, z0, dz=70.0):
        x1, y1, z1 = x0 + 1.0, y0 + 1.0, z0 + dz
        return np.asarray(
            [
                [x0, y0, z0],
                [x1, y0, z0],
                [x0, y1, z0],
                [x1, y1, z0],
                [x0, y0, z1],
                [x1, y0, z1],
                [x0, y1, z1],
                [x1, y1, z1],
            ],
            dtype=np.float64,
        )

    class FakeIndexMap:
        size_global = 2001
        local_range = (0, 1764)
        size_local = 1764
        num_ghosts = 0
        ghosts = np.empty(0, dtype=np.int32)
        owners = np.empty(0, dtype=np.int32)

        @staticmethod
        def local_to_global(rows):
            return np.asarray(rows, dtype=np.int32)

    class FakeDofMap:
        index_map = FakeIndexMap()

        @staticmethod
        def cell_dofs(cell_id):
            return np.arange(882, dtype=np.int32) + int(cell_id) * 882

    class FakeTopology:
        dim = 3

        @staticmethod
        def create_entity_permutations():
            return None

        @staticmethod
        def create_connectivity(_source, _target):
            return None

        @staticmethod
        def index_map(_dimension):
            return SimpleNamespace(size_local=2)

        @staticmethod
        def get_cell_permutation_info():
            return np.asarray([0, 1], dtype=np.uint32)

        @staticmethod
        def connectivity(_source, _target):
            return SimpleNamespace(
                links=lambda facet: np.asarray(
                    [0] if int(facet) == 10 else [1], dtype=np.int32
                )
            )

    class FakeFacetTags:
        indices = np.asarray([10, 11], dtype=np.int32)
        values = np.asarray([1, 2], dtype=np.int32)

        @staticmethod
        def find(tag):
            return np.asarray([10] if int(tag) == 1 else [11], dtype=np.int32)

    bottom_points = cell_corners(0.0, 0.0, -10.0)
    top_points = cell_corners(1.0, 0.0, 60.0)
    mesh = SimpleNamespace(
        topology=FakeTopology(),
        geometry=SimpleNamespace(
            dofmap=np.arange(16, dtype=np.int32).reshape(2, 8),
            x=np.vstack((bottom_points, top_points)),
        ),
        comm=SimpleNamespace(size=1),
    )
    space = SimpleNamespace(
        mesh=mesh,
        dofmap=FakeDofMap(),
        element=SimpleNamespace(needs_dof_transformations=False, space_dimension=882),
    )
    mesh_data = SimpleNamespace(facet_tags=FakeFacetTags())
    cfg = SimpleNamespace(
        mesh_axis_cell_counts=(1, 1, 2),
        physical_z_min=-10.0,
        physical_z_max=130.0,
        tags=SimpleNamespace(z_min=1, z_max=2),
    )

    rows, support_groups, allowed_rows, permutation_info, inventory = (
        _q0_reference_surface_inventory(mesh_data, space, cfg)
    )
    original_geometry_dofmap = mesh.geometry.dofmap
    misordered_geometry_dofmap = original_geometry_dofmap.copy()
    misordered_geometry_dofmap[0] = misordered_geometry_dofmap[0][
        np.asarray([0, 2, 1, 3, 4, 6, 5, 7], dtype=np.int64)
    ]
    mesh.geometry.dofmap = misordered_geometry_dofmap
    with pytest.raises(ValueError, match="actual geometry-dofmap vertex order"):
        _q0_reference_surface_inventory(mesh_data, space, cfg)
    mesh.geometry.dofmap = original_geometry_dofmap

    assert [row["side"] for row in rows] == ["bottom", "top"]
    assert np.array_equal(rows[0]["ordered_cell_coordinates_nm"], bottom_points)
    assert [len(group) for group in support_groups] == [1, 1]
    assert [len(group) for group in allowed_rows] == [882, 882]
    assert [row["cell_permutation"] for row in rows] == [0, 1]
    assert permutation_info.tolist() == [0, 1]
    assert inventory["facet_count_by_side"] == {"bottom": 1, "top": 1}
    assert inventory["cell_dofs_per_boundary_cell"] == 882

    class FakePolynomial:
        @staticmethod
        def integral_native(*_args):
            values = np.zeros((882, 2), dtype=np.complex128)
            values[1, 0] = 2.0 + 1.0j
            values[2, 1] = 3.0 - 1.0j
            return values

    rule = _V22NativeFacetRule(
        space=space,
        dof_index_map=FakeIndexMap(),
        mapping_rows=rows,
        permutation_info=permutation_info,
        polynomial=FakePolynomial(),
        quadrature_degree=160,
        cfg=SimpleNamespace(
            physical_z_min=-10.0,
            physical_z_max=130.0,
            tags=cfg.tags,
        ),
        mpc_expansions={
            1: (np.asarray([2000], dtype=np.int64), np.asarray([0.5 + 0.25j]))
        },
    )
    assemblers = rule.assemblers()
    bottom_assembler = assemblers[("bottom", 0)]
    top_assembler = assemblers[("top", 0)]
    assert callable(bottom_assembler.assemble_entries)
    assert bottom_assembler.boundary_tag == 1
    assert top_assembler.boundary_tag == 2
    assert bottom_assembler.quadrature_degree == top_assembler.quadrature_degree == 160

    bottom_mode = SimpleNamespace(
        side="bottom",
        m=2,
        n=-1,
        polarization="s",
        alpha=0.5 + 0.0j,
        gamma=0.25 + 0.0j,
        k_vector=np.asarray([0.5, 0.25, 1.0], dtype=np.complex128),
    )
    bottom_rows, bottom_values = bottom_assembler.assemble_entries(bottom_mode, None)
    assert 1 not in bottom_rows
    assert 2000 in bottom_rows
    assert bottom_values[np.searchsorted(bottom_rows, 2000)] == 1.25 + 0.0j

    top_mode = SimpleNamespace(
        side="top",
        m=3,
        n=1,
        polarization="p",
        alpha=0.5 + 0.0j,
        gamma=0.25 + 0.0j,
        k_vector=np.asarray([0.5, 0.25, 1.0], dtype=np.complex128),
    )
    top_rows, top_values = top_assembler.assemble_entries(top_mode, None)
    expected_phase = np.exp(0.5j)
    assert 883 in top_rows
    assert top_values[np.searchsorted(top_rows, 883)] == expected_phase * (2.0 + 1.0j)


def test_native_volume_apply_keeps_borrowed_output_vec_alive_across_repeated_calls(
    monkeypatch,
):
    import sys

    from src.solvers.task40_v25_selected_q0 import _native_volume_apply

    source_vectors = []

    class FakeVec:
        def __init__(self, array=None):
            self.array = array
            self.destroyed = False

        def createWithArray(self, array, *, comm):
            assert comm == "fixture-comm"
            vector = FakeVec(array)
            source_vectors.append(vector)
            return vector

        def getArray(self, *, readonly):
            assert readonly is True
            assert not self.destroyed
            return self.array

        def destroy(self):
            self.destroyed = True

    reusable_output = FakeVec(np.zeros(2, dtype=np.complex128))

    class ReusingVolumeAction:
        calls = 0

        def apply(self, source):
            assert not reusable_output.destroyed
            self.calls += 1
            reusable_output.array[:] = self.calls * source.array
            return reusable_output

    action = ReusingVolumeAction()
    fake_petsc = SimpleNamespace(Vec=FakeVec)
    monkeypatch.setitem(sys.modules, "petsc4py", SimpleNamespace(PETSc=fake_petsc))

    first = _native_volume_apply(
        action, np.asarray([1.0, 2.0], dtype=np.complex128), "fixture-comm"
    )
    second = _native_volume_apply(
        action, np.asarray([3.0, 4.0], dtype=np.complex128), "fixture-comm"
    )

    assert action.calls == 2
    assert reusable_output.destroyed is False
    assert all(vector.destroyed for vector in source_vectors)
    np.testing.assert_array_equal(first, [1.0, 2.0])
    np.testing.assert_array_equal(second, [6.0, 8.0])
    assert not np.shares_memory(first, reusable_output.array)
