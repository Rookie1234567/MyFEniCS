from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from scipy.sparse import csr_matrix

from src.runners import task41_p0_checker as v16_checker
from src.runners.task41_p0_checker import (
    Task41P0B0V16RowIncidenceAccumulator,
    Task41P0B0V16StreamedMetadataCollector,
    _task41_p0_v16_compare_v14_star_terminals,
    _task41_p0_v16_replay_v14_star_saved_arrays,
    load_task41_p0_b0_v16_saved_vector_manifest,
    load_task41_p0_b0_v16_v14_star_bindings,
    summarize_task41_p0_b0_v16_saved_vectors,
)
from src.runners.task41_p0_contract import TASK41_MODEL_ID


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n")
    return {
        "path": path.relative_to(path.parents[1]).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _sha(path),
    }


def _write_array(path: Path, values: np.ndarray) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, values, allow_pickle=False)
    return {
        "path": path.relative_to(path.parents[1]).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": _sha(path),
        "dtype": str(values.dtype),
        "shape": list(values.shape),
    }


def _complete_v16_fixture(
    tmp_path: Path,
    *,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> tuple[Path, str]:
    results = tmp_path / "results" / TASK41_MODEL_ID
    reports_dir = results / "producer_reports"
    arrays_dir = results / "arrays"
    source9 = {
        "source_sha": "a" * 40,
        "input_sha256": "b" * 64,
        "physical_model_sha256": "c" * 64,
        "resolved_config_sha256": "d" * 64,
    }
    source15 = {**source9, "source_sha": "e" * 40}
    shared = {
        "candidate_evaluator_identity": "task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1",
        "candidate_evaluator_cache_identity": "task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1:" + "f" * 64,
        "donor_manifest_sha256": "1" * 64,
        "active_rows": 3,
        "appended_rows": 1,
    }
    actual_k_lu_identity = {
        "schema": "task41.p0.b0.v15_actual_k_lu_generation_identity.v1",
        "actual_k_and_lu_share_generation_token_for_every_class": True,
        "class_count": 2,
        "class_key_set_sha256": "2" * 64,
        "identity_source": "fixture retained actual K/LU identity maps",
    }

    y9 = np.asarray(
        [[2 + 0j, 4 + 1j], [2 + 0j, 5 + 0j], [3 + 0j, 6 + 0j], [0 + 0j, 0 + 0j]],
        dtype=np.complex128,
    )
    g9 = np.asarray(
        [[1 + 0j, 2 + 0j], [1 + 0j, 4 + 0j], [3 + 0j, 6 + 0j], [0 + 0j, 0 + 0j]],
        dtype=np.complex128,
    )
    y15 = np.asarray(
        [[3 + 0j, 4 + 0j], [2 + 0j, 5 + 0j], [3 + 0j, 6 + 0j], [0 + 0j, 0 + 0j]],
        dtype=np.complex128,
    )
    g15 = np.asarray(
        [[1 + 0j, 2 + 0j], [1.5 + 0j, 4 + 0j], [3 + 0j, 6 + 0j], [0 + 0j, 0 + 0j]],
        dtype=np.complex128,
    )
    y9_record = _write_array(arrays_dir / "v9_y.npy", y9)
    g9_record = _write_array(arrays_dir / "v9_g.npy", g9)
    for name, record, values in (
        ("task41_p0_b0_v9_compact_candidate_full_p6", y9_record, y9),
        ("task41_p0_b0_v9_compact_candidate_reduced_rhs_p6", g9_record, g9),
    ):
        record["name"] = name
        record["array_sha256"] = hashlib.sha256(
            memoryview(np.ascontiguousarray(values, dtype=np.complex128)).cast("B")
        ).hexdigest()
    y15_records = [_write_array(arrays_dir / f"v15_y{column}.npy", y15[:, column]) for column in range(2)]
    g15_records = [_write_array(arrays_dir / f"v15_g{column}.npy", g15[:, column]) for column in range(2)]
    for column, record in enumerate(y15_records):
        record["name"] = f"saved_y_column_{column}"
    for column, record in enumerate(g15_records):
        record["name"] = f"saved_g_column_{column}"

    names = (
        "v9_audit", "v15_audit", "v15_checkpoint", "v15_checker",
        "v9_run_manifest", "v15_run_manifest", "v15_candidate_summary",
    )
    report_paths = {name: reports_dir / f"{name}.json" for name in names}
    report_paths["v15_checker"] = (
        tmp_path / v16_checker.TASK41_P0_B0_V16_V15_CHECKER_REPORT_RELATIVE
    )
    v9_audit = {
        "schema": "task41.p0.b0.v9.compact_volume_identity.v1",
        "status": "GATE_FAILED",
        **shared,
        "candidate_full_action_gate": {
            "status": "GATE_FAILED",
            "columns": [0, 1],
            "full_action_artifact": y9_record,
            "full_reduced_rhs_artifact": g9_record,
        },
    }
    v9_binding = _write_json(report_paths["v9_audit"], v9_audit)

    def v15_column(column: int) -> dict[str, object]:
        return {
            "column": column,
            "full_action_artifact": y15_records[column],
            "full_reduced_rhs_artifact": g15_records[column],
        }

    v15_columns = [v15_column(column) for column in range(2)]
    actual_v9_audit_path = (
        Path(__file__).resolve().parents[2]
        / "docs/task41extra_phi90_p50x50_g17x20/outcomes/v15_closeout/run/"
        "task41_p0_b0_v9_compact_volume_audit.json"
    )
    actual_v9_audit = json.loads(actual_v9_audit_path.read_text())
    actual_same_s_binding = actual_v9_audit["candidate_full_action_gate"][
        "same_s_action_reference_binding"
    ]
    same_s_artifact = {
        **actual_same_s_binding["artifact"],
        **y9_record,
        "path": str((results / y9_record["path"]).resolve()),
    }
    v15_audit = {
        "schema": "task41.p0.b0.v9.compact_volume_identity.v1",
        "status": "GATE_FAILED",
        "compact_evidence_layout": "v15_terminal_sufficient",
        **shared,
        "candidate_full_action_gate": {
            "status": "GATE_FAILED",
            "column_artifacts": v15_columns,
            "same_s_action_reference_binding": {
                "artifact": same_s_artifact,
                "report_path": str(report_paths["v9_audit"].resolve()),
                "report_sha256": v9_binding["sha256"],
                "source_reassigned": False,
            },
        },
        "persisted_artifacts": [*y15_records, *g15_records],
    }
    v15_audit_binding = _write_json(report_paths["v15_audit"], v15_audit)

    checkpoint = {
        "schema": "task41.p0.b0.v15_terminal_sufficient_checkpoint.v1",
        "status": "GATE_FAILED",
        "completed_action_columns": [0, 1],
        "completed_recovery_columns": [],
        "action_gate": {"status": "GATE_FAILED", "column_artifacts": [v15_column(0), v15_column(1)]},
        "identity_audit": {
            "path": v15_audit_binding["path"], "sha256": v15_audit_binding["sha256"],
            "status": "GATE_FAILED",
        },
        "actual_k_lu_identity": actual_k_lu_identity,
        "source_sha": source15["source_sha"],
        "contract_sha256": "3" * 64,
        "window_sha256": "4" * 64,
    }
    checkpoint_binding = _write_json(report_paths["v15_checkpoint"], checkpoint)

    def make_run_manifest(source: dict[str, str], contract_sha: str, window_sha: str) -> dict[str, object]:
        return {
            **source,
            "task41_p0_execution_contract": {
                "contract_sha256": contract_sha,
                "input_sha256": source["input_sha256"],
                "physical_model_sha256": source["physical_model_sha256"],
                "resolved_config_sha256": source["resolved_config_sha256"],
                "source_sha": source["source_sha"],
            },
            "task41_p0_campaign": {"window_sha256": window_sha},
        }

    v9_manifest_binding = _write_json(
        report_paths["v9_run_manifest"], make_run_manifest(source9, "5" * 64, "6" * 64)
    )
    v15_manifest_binding = _write_json(
        report_paths["v15_run_manifest"],
        make_run_manifest(source15, checkpoint["contract_sha256"], checkpoint["window_sha256"]),
    )
    summary_binding = _write_json(report_paths["v15_candidate_summary"], {
        "b0_v15_terminal_sufficient_checkpoint": {"sha256": checkpoint_binding["sha256"]},
        "v15_actual_k_lu_identity": actual_k_lu_identity,
    })
    checker_binding = _write_json(report_paths["v15_checker"], {
        "schema": "task41.p0.b0.v15.terminal_sufficient_independent_check.v1",
        "status": "NUMERICAL_FAIL",
        "audit_completed": True,
        "data_integrity": True,
        "action_passed": False,
        "recovery_passed": None,
        "official_result": False,
        "errors": [],
        "run_binding": {
            "checkpoint_sha256": checkpoint_binding["sha256"],
            "manifest_sha256": v15_manifest_binding["sha256"],
            "summary_sha256": summary_binding["sha256"],
            "source_sha": source15["source_sha"],
            "contract_sha256": checkpoint["contract_sha256"],
            "window_sha256": checkpoint["window_sha256"],
        },
    })
    report_records = {
        name: _write_json(path, json.loads(path.read_text()))
        for name, path in report_paths.items()
    }
    checker_report = report_paths["v15_checker"]
    report_records["v15_checker"] = {
        **report_records["v15_checker"],
        "path": str(checker_report.resolve()),
    }
    if monkeypatch is not None:
        monkeypatch.setattr(
            v16_checker,
            "TASK41_P0_B0_V16_V15_CHECKER_REPORT_BYTES",
            checker_report.stat().st_size,
        )
        monkeypatch.setattr(
            v16_checker,
            "TASK41_P0_B0_V16_V15_CHECKER_REPORT_SHA256",
            report_records["v15_checker"]["sha256"],
        )
    identities = {
        "v9": {
            **source9, **shared, "contract_sha256": "5" * 64, "window_sha256": "6" * 64,
        },
        "v15": {
            **source15, **shared,
            "contract_sha256": checkpoint["contract_sha256"],
            "window_sha256": checkpoint["window_sha256"],
            "actual_k_lu_identity": actual_k_lu_identity,
        },
    }
    arrays = {
        name: [
            {
                **record,
                "column": column,
                "layout": layout,
            }
            for column in range(2)
        ]
        for name, record, layout in (
            ("y9", y9_record, "two_column_matrix"),
            ("g9", g9_record, "two_column_matrix"),
        )
    }
    arrays.update({
        "y15": [{**record, "column": column, "layout": "single_column_vector"} for column, record in enumerate(y15_records)],
        "g15": [{**record, "column": column, "layout": "single_column_vector"} for column, record in enumerate(g15_records)],
    })

    accumulator = Task41P0B0V16RowIncidenceAccumulator(
        row_count=4,
        trace_rows=3,
        tag_codebook=(1, 2),
        direction_codebook=(0, 4680),
        probe_row=1,
    )
    for cell, tag, direction, original_rows, active_ids, slave_mask in (
        (10, 1, 0, [100, 101], [0, 1], [False, False]),
        (11, 2, 4680, [101, 102], [1, 2], [True, False]),
    ):
        accumulator.add_cell({
            "cell_index": cell,
            "cell_tag": tag,
            "cell_permutation": direction,
            "trace_original_rows": np.asarray(original_rows, dtype=np.int64),
            "active_ids": np.asarray(active_ids, dtype=np.int64),
            "trace_expansion": csr_matrix(np.eye(2, dtype=np.complex128)),
            "mpc_slave_trace_mask": np.asarray(slave_mask, dtype=np.bool_),
        })
    codes, definitions, provenance = accumulator.finish(
        np.asarray([100, 101, 102], dtype=np.int64)
    )
    codes_record = _write_array(arrays_dir / "v16_trace_row_group_codes.npy", codes.astype(np.int32))
    codes_record["dtype"] = np.dtype(np.int32).str
    active_original_rows = np.asarray([100, 101, 102], dtype=np.int64)
    active_map_record = _write_array(arrays_dir / "v15_active_original_rows.npy", active_original_rows)
    active_map_values_sha256 = hashlib.sha256(
        memoryview(
            np.ascontiguousarray(active_original_rows, dtype=np.dtype("<i8"))
        ).cast("B")
    ).hexdigest()
    active_map_array_sha_digest = hashlib.sha256()
    active_map_array_sha_digest.update(
        repr((active_original_rows.shape, str(active_original_rows.dtype))).encode("ascii")
    )
    active_map_array_sha_digest.update(
        memoryview(
            np.ascontiguousarray(active_original_rows, dtype=np.dtype("<i8"))
        ).cast("B")
    )
    active_map_array_sha256 = active_map_array_sha_digest.hexdigest()
    active_map_record["dtype"] = np.dtype("<i8").str
    active_map_record["array_sha256"] = active_map_array_sha256
    active_map_record["raw_bytes_sha256"] = active_map_values_sha256
    probe_binding = _write_json(results / "metadata" / "v16_max_row_probe.json", {
        "schema": "task41.p0.b0.v16.max_row_probe_metadata.v1",
        "row": 1,
        "original_row": 101,
        "incident_cells": [{
            "cell_id": 11,
            "local_position": 0,
            "trace_E": [{"active_id": 7, "coefficient_real": 1.0, "coefficient_imag": 0.0}],
            "active_ids": [7],
            "projection_coefficients": [{"real": 1.0, "imag": 0.0}],
            "coordinates": [[0.0, 0.0, 0.0]],
            "actual_keys": ["fixture-key"],
        }],
    })
    provenance.update({
        "row_group_codes_sha256": codes_record["sha256"],
        "max_row_probe_metadata_sha256": probe_binding["sha256"],
    })
    manifest = {
        "schema": "task41.p0.b0.v16.saved_vector_manifest.v1",
        "rows": 4,
        "trace_rows": 3,
        "columns": [0, 1],
        "probe_row": 1,
        "producer_reports": report_records,
        "producer_identities": identities,
        "arrays": arrays,
        "row_group_codes": codes_record,
        "row_group_definitions": definitions,
        "row_incidence_provenance": provenance,
        "max_row_probe_metadata": probe_binding,
        "metadata_source": {
            "active_original_rows": active_map_record,
            "active_original_rows_file_sha256": active_map_record["sha256"],
            "active_original_rows_values_sha256": active_map_array_sha256,
            "active_original_rows_raw_bytes_sha256": active_map_values_sha256,
        },
    }
    manifest_path = results / "v16_saved_vector_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
    return manifest_path, _sha(manifest_path)


def _refresh_manifest_sha(path: Path) -> str:
    return _sha(path)


def test_v16_trace_groups_cover_trace_only_and_keep_port_rows_separate():
    accumulator = Task41P0B0V16RowIncidenceAccumulator(
        row_count=3,
        trace_rows=2,
        tag_codebook=(1, 2),
        direction_codebook=(0, 4680),
        probe_row=1,
    )
    for cell, tag, direction, original_rows, active_ids, slave_mask in (
        (10, 1, 0, [100, 101], [0, 1], [False, False]),
        (11, 2, 4680, [101, 102], [1], [True, False]),
    ):
        # Two trace rows in the second cell can expand to the same active row.
        expansion = csr_matrix(
            (np.asarray([1.0 + 0j, 0.5 + 0j]), (np.asarray([0, 1]), np.asarray([0, 0]))),
            shape=(2, 1),
        ) if cell == 11 else csr_matrix(np.eye(2, dtype=np.complex128))
        accumulator.add_cell({
            "cell_index": cell,
            "cell_tag": tag,
            "cell_permutation": direction,
            "trace_original_rows": np.asarray(original_rows, dtype=np.int64),
            "active_ids": np.asarray(active_ids, dtype=np.int64),
            "trace_expansion": expansion,
            "mpc_slave_trace_mask": np.asarray(slave_mask, dtype=np.bool_),
        })
    codes, definitions, provenance = accumulator.finish(
        np.asarray([100, 101], dtype=np.int64)
    )
    assert codes.shape == (2,)
    assert provenance["covered_trace_rows"] == 2
    assert provenance["port_rows_excluded_from_incidence"] == 1
    assert provenance["probe_original_row"] == 101
    assert provenance["probe_incident_cell_ids"] == [10, 11]
    assert provenance["probe_incident_count"] == 2
    assert sorted(item["incident_cell_count"] for item in definitions) == [1, 2]
    assert any(item["periodic_slave_e_incident_cell_count"] == 1 for item in definitions)


def test_v16_streamed_incidence_uses_dense_codebooks_for_raw_permutations():
    accumulator = Task41P0B0V16RowIncidenceAccumulator(
        row_count=4,
        trace_rows=3,
        tag_codebook=(1, 2),
        direction_codebook=(0, 4680),
        probe_row=1,
    )
    for cell, tag, permutation, original_rows, active_ids, slave_mask in (
        (0, 2, 4680, [100, 101], [0, 1], [False, False]),
        (1, 1, 0, [101, 102], [1, 2], [True, False]),
    ):
        accumulator.add_cell({
            "cell_index": cell,
            "cell_tag": tag,
            "cell_permutation": permutation,
            "trace_original_rows": np.asarray(original_rows, dtype=np.int64),
            "active_ids": np.asarray(active_ids, dtype=np.int64),
            "trace_expansion": csr_matrix(np.eye(2, dtype=np.complex128)),
            "mpc_slave_trace_mask": np.asarray(slave_mask, dtype=np.bool_),
        })
    codes, definitions, provenance = accumulator.finish(
        np.asarray([100, 101, 102], dtype=np.int64)
    )
    assert codes.shape == (3,)
    assert provenance["probe_incident_cell_ids"] == [0, 1]
    assert provenance["incidence_records"] == 4
    assert provenance["direction_codebook"] == [
        {"code": 0, "raw_permutation_value": 0},
        {"code": 1, "raw_permutation_value": 4680},
    ]
    assert any(item["direction_codes"] == [1] for item in definitions)
    assert any(item["periodic_slave_e_incident_cell_count"] == 1 for item in definitions)


def test_v16_streamed_collector_consumes_builder_callback_events_in_order():
    collector = Task41P0B0V16StreamedMetadataCollector(
        row_count=3, trace_rows=2, probe_row=1
    )
    with pytest.raises(ValueError, match="start with one codebook"):
        collector.consume({"phase": "cell"})
    collector.consume({
        "phase": "codebook",
        "tag_raw_values": [2, 9],
        "direction_raw_values": [0, 4680],
        "codebook_values_are_dense_ids_not_raw_bit_positions": True,
    })
    collector.consume({
        "phase": "cell",
        "cell_index": 0,
        "cell_tag": 2,
        "cell_permutation": 4680,
        "trace_original_rows": np.asarray([100, 101], dtype=np.int64),
        "active_ids": np.asarray([0, 1], dtype=np.int64),
        "trace_expansion": csr_matrix(np.eye(2, dtype=np.complex128)),
        "mpc_slave_trace_mask": np.asarray([False, False]),
    })
    collector.consume({
        "phase": "cell",
        "cell_index": 1,
        "cell_tag": 9,
        "cell_permutation": 0,
        "trace_original_rows": np.asarray([101, 102], dtype=np.int64),
        "active_ids": np.asarray([1], dtype=np.int64),
        "trace_expansion": csr_matrix(
            np.asarray([[1.0], [0.5]], dtype=np.complex128)
        ),
        "mpc_slave_trace_mask": np.asarray([True, False]),
    })
    codes, definitions, provenance = collector.finish(
        np.asarray([100, 101], dtype=np.int64)
    )
    assert codes.shape == (2,)
    assert provenance["probe_incident_cell_ids"] == [0, 1]
    assert provenance["direction_codebook"] == [
        {"code": 0, "raw_permutation_value": 0},
        {"code": 1, "raw_permutation_value": 4680},
    ]
    assert any(item["periodic_slave_e_incident_cell_count"] == 1 for item in definitions)
    with pytest.raises(ValueError, match="more than one codebook"):
        collector.consume({
            "phase": "codebook",
            "tag_raw_values": [2],
            "direction_raw_values": [0],
            "codebook_values_are_dense_ids_not_raw_bit_positions": True,
        })


def test_v16_v14_attempt01_binds_y_and_g_separately_without_state_field():
    spec = {
        "active_row": 1,
        "original_row": 250_113,
        "cells": [360, 446],
        "states": {0: (None,), 1: (None,)},
    }
    y15 = (
        np.asarray([0j, 2 + 3j], dtype=np.complex128),
        np.asarray([0j, 5 - 1j], dtype=np.complex128),
    )
    g15 = (
        np.asarray([0j, 7 + 1j], dtype=np.complex128),
        np.asarray([0j, 11 - 2j], dtype=np.complex128),
    )
    rows = [
        {
            "column": 0,
            "selected_active_row": 1,
            "selected_original_row": 250_113,
            "incident_cell_order": [360, 446],
            "saved_y": [2.0, 3.0],
            "candidate_g_actual_returned_correction_cell_order": [8.0, 1.0],
        },
        {
            "column": 1,
            "selected_active_row": 1,
            "selected_original_row": 250_113,
            "incident_cell_order": [360, 446],
            "saved_y": [5.0, -2.0],
            "candidate_g_actual_returned_correction_cell_order": [11.0, -2.0],
        },
    ]
    comparisons, all_bound = _task41_p0_v16_compare_v14_star_terminals(
        attempt="01", rows=rows, spec=spec, y15=y15, g15=g15
    )
    assert not all_bound
    assert [(item["y_exactly_bound"], item["g_exactly_bound"]) for item in comparisons] == [
        (True, False), (False, True)
    ]
    assert comparisons[0]["delta_g_v14_minus_v15"] == [1.0, 0.0]
    assert comparisons[1]["delta_y_v14_minus_v15"] == [0.0, -1.0]
    with pytest.raises(ValueError, match="no-state-field"):
        _task41_p0_v16_compare_v14_star_terminals(
            attempt="01", rows=[{**rows[0], "state": "j0"}], spec=spec,
            y15=y15, g15=g15,
        )


def test_v16_attempt01_selected_trace_row_maps_to_nonmatching_active_id_column():
    active_ids = np.arange(432, dtype=np.int64)
    active_ids[111] = 87_567
    row_indices = np.arange(432, dtype=np.int32)
    column_indices = np.arange(432, dtype=np.int32)
    column_indices[[75, 111]] = column_indices[[111, 75]]
    expansion = csr_matrix(
        (
            np.ones(432, dtype=np.complex128),
            (row_indices, column_indices),
        ),
        shape=(432, 432),
    )

    assert v16_checker._task41_p0_v16_selected_trace_active_position(
        active_ids=active_ids,
        active_row=87_567,
        local_trace_row=75,
        expansion=expansion,
        label="V16 attempt01 V8 cell446",
    ) == 111

    wrong_expansion = csr_matrix(np.eye(432, dtype=np.complex128))
    with pytest.raises(ValueError, match="selected E row differs"):
        v16_checker._task41_p0_v16_selected_trace_active_position(
            active_ids=active_ids,
            active_row=87_567,
            local_trace_row=75,
            expansion=wrong_expansion,
            label="V16 attempt01 V8 cell446",
        )

    duplicate_ids = active_ids.copy()
    duplicate_ids[112] = 87_567
    with pytest.raises(ValueError, match="not uniquely mapped"):
        v16_checker._task41_p0_v16_selected_trace_active_position(
            active_ids=duplicate_ids,
            active_row=87_567,
            local_trace_row=75,
            expansion=expansion,
            label="V16 attempt01 V8 cell446",
        )


def test_v16_attempt04_filters_full_v8_numeric_inventory_to_exact_incident_star():
    cells = [23_352, 23_493]
    full_v8_cells = [0, 1, 2, 5, 6, 7_505, *cells, 26_762, 26_897]
    metadata_cells = {
        str(cell): {
            "cell_index": cell,
            "cell_tag": 1 if cell in cells else 3,
            "cell_permutation": 0,
            "arrays": {"actual_geometry_coordinates": {"name": f"coords-{cell}"}},
        }
        for cell in full_v8_cells
    }
    numeric_rows = [
        {
            "cell_index": cell,
            "is_target_row_incident": cell in cells,
            "roles": [
                {"role": role, "raw_oriented_RTS_artifacts": {"R": f"{role}-{cell}-R"}}
                for role in ("candidate", "reference")
            ],
        }
        for cell in full_v8_cells
    ]
    p3_rows = [
        {
            "cell_index": cell,
            "roles_and_states": [
                {
                    "column": column,
                    "state": state,
                    "roles": [
                        {
                            "role": role,
                            "local_values": {"u_i": f"{cell}-{column}-{state}-u"},
                            "signed_action_artifacts": {"S_action": f"{cell}-{column}-{state}-S"},
                        }
                        for role in ("candidate", "reference")
                    ],
                }
                for column in (0, 1)
                for state in ("j0", "j3")
            ],
        }
        for cell in cells
    ]

    numeric_by_cell, p3_by_cell = v16_checker._task41_p0_v16_v8_star_cell_inventory(
        metadata_cells=metadata_cells,
        numeric_rows=numeric_rows,
        p3_rows=p3_rows,
        cells=cells,
    )
    assert list(numeric_by_cell) == cells
    assert list(p3_by_cell) == cells
    assert all(numeric_by_cell[cell]["is_target_row_incident"] is True for cell in cells)
    assert [len(p3_by_cell[cell]["roles_and_states"]) for cell in cells] == [4, 4]

    missing_incident = [
        {**item, "is_target_row_incident": False}
        if item["cell_index"] == cells[1] else item
        for item in numeric_rows
    ]
    with pytest.raises(ValueError, match="exact two-cell star"):
        v16_checker._task41_p0_v16_v8_star_cell_inventory(
            metadata_cells=metadata_cells,
            numeric_rows=missing_incident,
            p3_rows=p3_rows,
            cells=cells,
        )
    with pytest.raises(ValueError, match="numeric cell inventory is duplicated"):
        v16_checker._task41_p0_v16_v8_star_cell_inventory(
            metadata_cells=metadata_cells,
            numeric_rows=[*numeric_rows, numeric_rows[0]],
            p3_rows=p3_rows,
            cells=cells,
        )
    with pytest.raises(ValueError, match="exact two-cell star"):
        v16_checker._task41_p0_v16_v8_star_cell_inventory(
            metadata_cells=metadata_cells,
            numeric_rows=numeric_rows,
            p3_rows=list(reversed(p3_rows)),
            cells=cells,
        )


def test_v16_attempt01_legacy_basename_sources_bind_only_to_pinned_v3_donor_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    results_root = tmp_path / "results" / TASK41_MODEL_ID
    donor_root = results_root / v16_checker.TASK41_P0_B0_V16_V3_DONOR_RUN_NAME
    donor_root.mkdir(parents=True)
    sources = {
        "native_rhs": (
            "native_rhs.npy", np.asarray([1 + 2j, 3 + 4j], dtype=np.complex128)
        ),
        "b_alpha_rows": ("b_alpha_rows.npy", np.asarray([1], dtype=np.int64)),
        "b_alpha_values": (
            "b_alpha_values.npy", np.asarray([0.25 + 0.5j], dtype=np.complex128)
        ),
    }
    expected: dict[str, tuple[str, str, int, str, list[int]]] = {}
    vector_records: list[dict[str, object]] = []
    row_references: dict[str, dict[str, object]] = {}
    loaded_values: dict[str, np.ndarray] = {}
    for role, (filename, values) in sources.items():
        donor_path = donor_root / filename
        np.save(donor_path, values, allow_pickle=False)
        reference = {
            "path": filename,
            "sha256": _sha(donor_path),
            "bytes": donor_path.stat().st_size,
            "dtype": str(values.dtype),
            "shape": list(values.shape),
            "array_sha256": hashlib.sha256(
                memoryview(np.ascontiguousarray(values)).cast("B")
            ).hexdigest(),
        }
        row_references[role] = dict(reference)
        vector_records.append(dict(reference))
        expected[role] = (
            filename, reference["sha256"], reference["bytes"],
            reference["dtype"], reference["shape"],
        )
        loaded_values[role] = values
        # A same-name artifact in the model root must never win over the pinned donor.
        np.save(results_root / filename, np.zeros_like(values), allow_pickle=False)

    monkeypatch.setattr(
        v16_checker,
        "TASK41_P0_B0_V16_V3_ATTEMPT01_SOURCE_BINDINGS",
        {0: expected},
    )
    bound: dict[str, dict[str, object]] = {}
    for role in sources:
        bound[role] = v16_checker._task41_p0_v16_v3_donor_source_ref(
            row_references[role],
            vector_records=vector_records,
            donor_run_root=donor_root,
            column=0,
            role=role,
            label=f"fixture {role}",
        )
        assert bound[role]["path"] == str(donor_root / sources[role][0])
        assert bound[role]["sha256"] == row_references[role]["sha256"]

    assert np.array_equal(
        v16_checker._task41_p0_v16_bound_complex_vector(
            bound["native_rhs"], results_root=results_root, label="fixture native RHS"
        ),
        loaded_values["native_rhs"],
    )
    assert np.array_equal(
        v16_checker._task41_p0_v16_bound_metadata_npy(
            bound["b_alpha_rows"], results_root=results_root, label="fixture B-alpha rows"
        ),
        loaded_values["b_alpha_rows"],
    )
    assert np.array_equal(
        v16_checker._task41_p0_v16_bound_complex_vector(
            bound["b_alpha_values"], results_root=results_root, label="fixture B-alpha values"
        ),
        loaded_values["b_alpha_values"],
    )

    minimal_reference = {
        "path": row_references["native_rhs"]["path"],
        "sha256": row_references["native_rhs"]["sha256"],
    }
    minimal_bound = v16_checker._task41_p0_v16_v3_donor_source_ref(
        minimal_reference,
        vector_records=vector_records,
        donor_run_root=donor_root,
        column=0,
        role="native_rhs",
        label="fixture path/hash-only legacy reference",
    )
    assert minimal_bound == bound["native_rhs"]

    mismatched_hash = {**row_references["native_rhs"], "sha256": "0" * 64}
    with pytest.raises(ValueError, match="saved source hash differs"):
        v16_checker._task41_p0_v16_v3_donor_source_ref(
            mismatched_hash,
            vector_records=vector_records,
            donor_run_root=donor_root,
            column=0,
            role="native_rhs",
            label="fixture mismatched hash",
        )
    traversing_path = {**row_references["native_rhs"], "path": "../native_rhs.npy"}
    with pytest.raises(ValueError, match="relative source must be the pinned donor basename"):
        v16_checker._task41_p0_v16_v3_donor_source_ref(
            traversing_path,
            vector_records=vector_records,
            donor_run_root=donor_root,
            column=0,
            role="native_rhs",
            label="fixture traversal",
        )
    wrong_absolute_path = {
        **row_references["native_rhs"],
        "path": str(results_root / "native_rhs.npy"),
    }
    with pytest.raises(ValueError, match="absolute source path differs from the pinned donor"):
        v16_checker._task41_p0_v16_v3_donor_source_ref(
            wrong_absolute_path,
            vector_records=vector_records,
            donor_run_root=donor_root,
            column=0,
            role="native_rhs",
            label="fixture wrong absolute path",
        )


def test_v16_v14_attempt04_preserves_j0_j3_terminal_bindings():
    spec = {
        "active_row": 1,
        "original_row": 15_440_235,
        "cells": [23_352, 23_493],
        "states": {0: ("j0", "j3"), 1: ("j0", "j3")},
    }
    y15 = (
        np.asarray([0j, 2 + 3j], dtype=np.complex128),
        np.asarray([0j, 5 - 1j], dtype=np.complex128),
    )
    g15 = (
        np.asarray([0j, 7 + 1j], dtype=np.complex128),
        np.asarray([0j, 11 - 2j], dtype=np.complex128),
    )
    rows = [
        {
            "column": column,
            "state": state,
            "selected_active_row": 1,
            "selected_original_row": 15_440_235,
            "incident_cell_order": [23_352, 23_493],
            "saved_y": [float(y15[column][1].real), float(y15[column][1].imag)],
            "candidate_g_actual_returned_correction_cell_order": [
                float(g15[column][1].real), float(g15[column][1].imag)
            ],
        }
        for column in range(2)
        for state in ("j0", "j3")
    ]
    comparisons, all_bound = _task41_p0_v16_compare_v14_star_terminals(
        attempt="04", rows=rows, spec=spec, y15=y15, g15=g15
    )
    assert all_bound
    assert [(item["column"], item["state"]) for item in comparisons] == [
        (0, "j0"), (0, "j3"), (1, "j0"), (1, "j3")
    ]
    with pytest.raises(ValueError, match="j0/j3"):
        _task41_p0_v16_compare_v14_star_terminals(
            attempt="04", rows=[{**rows[0], "state": None}, *rows[1:]], spec=spec,
            y15=y15, g15=g15,
        )


def _v16_saved_array_replay_fixture(
    *, attempt: str, cell: int, interior_count: int, trace_count: int,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, object]:
    active_row = 1
    original_row = 2
    cells = [cell]
    states = (
        {0: (None,), 1: (None,)}
        if attempt == "01"
        else {0: ("j0", "j3"), 1: ("j0", "j3")}
    )
    spec = {
        "attempt": attempt,
        "stage": "initial_screen" if attempt == "01" else "saved_star_extension",
        "active_row": active_row,
        "original_row": original_row,
        "cells": cells,
        "states": states,
    }
    n_active = 3
    interior = np.arange(interior_count, dtype=np.int64)
    trace = np.arange(interior_count, interior_count + trace_count, dtype=np.int64)
    K = np.diag(np.linspace(2.0, 3.0, interior_count)).astype(np.complex128)
    if interior_count > 1:
        K[0, 1] = 0.125 + 0.25j
        K[1, 0] = -0.0625j
    G = np.full((interior_count, trace_count), 0.03125 + 0.015625j, dtype=np.complex128)
    J = np.full((trace_count, interior_count), -0.015625 + 0.0078125j, dtype=np.complex128)
    L = np.eye(trace_count, dtype=np.complex128) * (0.5 + 0.125j)
    S = np.eye(trace_count, dtype=np.complex128) * (0.75 - 0.0625j)
    R = np.full((interior_count, trace_count), 0.0234375 - 0.01171875j, dtype=np.complex128)
    expansion_dense = np.zeros((trace_count, n_active), dtype=np.complex128)
    expansion_dense[:, active_row] = np.linspace(1.0, 1.5, trace_count) + 0.125j
    expansion_dense[0, active_row] = 1.0 + 0.0j
    expansion = csr_matrix(expansion_dense)
    weights = np.asarray(expansion[:, active_row].toarray()).reshape(-1)
    lu = np.asarray(K, dtype=np.complex128).copy()
    pivots = np.arange(interior_count, dtype=np.int32)
    oriented_tensor = np.block([[K, G], [J, L]]).astype(np.complex128)

    candidate_arrays: dict[tuple[int, int], dict[str, np.ndarray]] = {}
    t_by_key: dict[tuple[int, str | None], np.ndarray] = {}
    saved_s_action_by_key: dict[tuple[int, int, str | None], np.ndarray] = {}
    states_by_key: dict[tuple[int, int, str], dict[str, np.ndarray]] = {}
    native_rhs_by_column: dict[int, np.ndarray] = {}
    b_volume_rhs_by_column: dict[int, complex] = {}
    b_alpha_by_column = {0: 0.125 - 0.0625j, 1: -0.25 + 0.03125j}
    rows: list[dict[str, object]] = []
    y15 = [np.zeros(active_row + 1, dtype=np.complex128) for _ in range(2)]
    g15 = [np.zeros(active_row + 1, dtype=np.complex128) for _ in range(2)]

    for column in (0, 1):
        if attempt == "01":
            t_by_key[(column, None)] = np.linspace(
                0.25 + column * 0.125j, 0.5 + column * 0.25j, trace_count
            ).astype(np.complex128)
        else:
            for state_offset, state in enumerate(("j0", "j3")):
                t_by_key[(column, state)] = np.linspace(
                    0.25 + column * 0.125j,
                    0.5 + column * 0.25j,
                    trace_count,
                ).astype(np.complex128)
        for terminal_state in states[column]:
            saved_s_action_by_key[(cell, column, terminal_state)] = np.asarray(
                S @ t_by_key[(column, terminal_state)], dtype=np.complex128
            )
        native_rhs = np.zeros(original_row + 1, dtype=np.complex128)
        native_rhs[original_row] = 10.0 + column + 0.5j
        native_rhs_by_column[column] = native_rhs
        b_volume_rhs_by_column[column] = (
            complex(native_rhs[original_row])
            - b_alpha_by_column[column]
            - (0.25 - 0.125j)
        )
        b_i = np.linspace(1.0 + column * 0.25j, 2.0 + column * 0.5j, interior_count)
        final_z = np.linspace(0.125 + column * 0.0625j, 0.375 + column * 0.125j, interior_count)
        correction = np.asarray(-(J @ final_z), dtype=np.complex128)
        projected_active = np.asarray(expansion.conjugate().transpose() @ correction).reshape(-1)
        candidate_arrays[(cell, column)] = {
            "b_i": np.asarray(b_i, dtype=np.complex128),
            "oriented_tensor": oriented_tensor,
            "interior_lu": lu,
            "final_z": np.asarray(final_z, dtype=np.complex128),
            "returned_correction": correction,
            "projected_active": projected_active,
        }
        state_labels = ("j0", "j3")
        for state_index, state in enumerate(state_labels):
            t_key = (column, None) if attempt == "01" else (column, state)
            t_state = t_by_key[t_key]
            u_i = np.linspace(0.0625 + state_index * 0.015625, 0.125 + column * 0.03125j, interior_count)
            u_i = np.asarray(u_i, dtype=np.complex128)
            n_i = np.asarray(K @ u_i + G @ t_state - b_i, dtype=np.complex128)
            states_by_key[(cell, column, state)] = {"u_i": u_i, "n_i": n_i}

        y_values: dict[str | None, complex] = {}
        for terminal_state in states[column]:
            t_state = t_by_key[(column, terminal_state)]
            projected_s = np.asarray(
                expansion.conjugate().transpose() @ (S @ t_state)
            ).reshape(-1)
            y_values[terminal_state] = complex(projected_s[active_row]) + b_alpha_by_column[column]
        g_value = complex(native_rhs[original_row]) + complex(projected_active[active_row])
        y15[column][active_row] = next(iter(y_values.values()))
        g15[column][active_row] = g_value
        for state in states[column]:
            row: dict[str, object] = {
                "column": column,
                "selected_active_row": active_row,
                "selected_original_row": original_row,
                "incident_cell_order": cells,
                "saved_y": [y_values[state].real, y_values[state].imag],
                "candidate_g_actual_returned_correction_cell_order": [g_value.real, g_value.imag],
                "candidate_d": [0.5, -0.25],
            }
            if state is not None:
                row["state"] = state
            rows.append(row)

    star_cells = {
        cell: {
            "interior_positions": interior,
            "trace_positions": trace,
            "selected_row_weights": weights,
            "target_active_position": active_row,
            "expansion": expansion,
            "S": S,
            "R": R,
            "interior_lu_pivots": pivots if attempt == "01" else None,
            "t_by_key": t_by_key,
        }
    }
    v13_lambda_by_cell: dict[int, dict[str, object]] = {}
    if attempt == "01":
        lambda_vector = np.linspace(0.5 + 0.125j, 0.75 + 0.25j, interior_count).astype(np.complex128)
        saved_h = np.asarray(J.conjugate().transpose() @ weights, dtype=np.complex128)
        numerical_identity = {
            "cell_index": cell,
            "K": v16_checker._task41_p0_v13_array_identity(K),
            "J": v16_checker._task41_p0_v13_array_identity(J),
            "q": v16_checker._task41_p0_v13_array_identity(weights),
            "LU": v16_checker._task41_p0_v13_array_identity(lu),
            "pivots": v16_checker._task41_p0_v13_array_identity(pivots),
            "h": v16_checker._task41_p0_v13_array_identity(saved_h),
            "transpose": 2,
            "purpose": "ADJOINT_DIAGNOSTIC",
        }
        spec_identity = {
            "lambda": v16_checker._task41_p0_v13_array_identity(lambda_vector),
            "h": v16_checker._task41_p0_v13_array_identity(saved_h),
            "numerical_identity": numerical_identity,
        }
        scope_identity = {
            "candidate_report_sha256": "2463e322ea72160bfcca7f3345d149ab20e5b017982f1f9ed55010df0afa9876",
            "donor_manifest_sha256": "f55ac594382f40662954e19521ef9922d805abc64459cc7812877b12ec618465",
            "window_sha256": v16_checker.TASK41_P0_B0_V13_WINDOW_SHA256,
        }
        receipt = {
            "schema": "task41.p0.v13.adjoint_lambda_receipt.v1",
            "cell_index": cell,
            "purpose": "ADJOINT_DIAGNOSTIC",
            "transpose": 2,
            "solve_call_ordinal": 1,
            "scope_identity": scope_identity,
            "numerical_identity": numerical_identity,
            "lambda_identity": spec_identity["lambda"],
            "h_identity": spec_identity["h"],
            "campaign_source_identity_at_solve": "fixture-bound-source-identity",
            "official_result": False,
        }
        v13_lambda_by_cell[cell] = {
            "vector": lambda_vector,
            "h": saved_h,
            "receipt": receipt,
            "expected": dict(receipt),
            "package_path": "fixture/v13-adjoint.npz",
            "package_sha256": "a" * 64,
        }
        monkeypatch.setattr(v16_checker, "TASK41_P0_B0_V13_ADJOINT_EXPECTED_IDENTITIES", {
            **v16_checker.TASK41_P0_B0_V13_ADJOINT_EXPECTED_IDENTITIES,
            cell: spec_identity,
        })

    return {
        "attempt": attempt,
        "spec": spec,
        "rows": rows,
        "y15": tuple(y15),
        "g15": tuple(g15),
        "candidate_arrays": candidate_arrays,
        "star_cells": star_cells,
        "native_rhs_by_column": native_rhs_by_column,
        "b_alpha_by_column": b_alpha_by_column,
        "b_volume_rhs_by_column": b_volume_rhs_by_column,
        "states_by_key": states_by_key,
        "saved_s_action_by_key": saved_s_action_by_key,
        "v13_lambda_by_cell": v13_lambda_by_cell,
    }


def test_v16_saved_array_replay_uses_rectangular_i_t_lambda_and_rejects_correction_pollution(
    monkeypatch: pytest.MonkeyPatch,
):
    attempt01 = _v16_saved_array_replay_fixture(
        attempt="01", cell=360, interior_count=3, trace_count=2, monkeypatch=monkeypatch
    )
    result01 = _task41_p0_v16_replay_v14_star_saved_arrays(**attempt01)
    assert result01["status"] == "REPLAYED_SAVED_ARRAYS"
    assert result01["saved_state_equation_decomposition"][
        "unlabeled_attempt01_terminal_state_assignment"
    ] is False
    assert result01["saved_state_equation_decomposition"][
        "existing_identity_bound_lambda"
    ] == "V13_CACHE_REUSED_FOR_ATTEMPT01_CELLS_360_446"
    assert result01["cell_decomposition"][0]["v13_lambda_binding"]["status"] == (
        "REUSED_IDENTITY_BOUND_SAVED_PACKAGE_NO_SOLVE"
    )
    equation01 = result01["saved_state_equation_decomposition"][
        "equation2_reconstruction_by_column"
    ]["column0"][0]
    assert equation01["equation2_reconstruction_complete"] is True
    assert equation01["rhs_manufacturing_epsilon_full_minus_volume_minus_Balpha"] == [
        0.25, -0.125
    ]
    assert equation01["state_is_bound_to_production_terminal"] is False
    assert equation01["reconstructed_d_minus_v14_saved_d"] is None

    attempt04 = _v16_saved_array_replay_fixture(
        attempt="04", cell=23_352, interior_count=4, trace_count=3, monkeypatch=monkeypatch
    )
    result04 = _task41_p0_v16_replay_v14_star_saved_arrays(**attempt04)
    assert result04["status"] == "REPLAYED_SAVED_ARRAYS"
    assert result04["attempt01_state_decomposition"] == "j0_j3_bound_separately"
    assert result04["cell_decomposition"][0]["v13_lambda_binding"]["status"] == (
        "NOT_AVAILABLE_FOR_THIS_V14_STAR_CELL"
    )
    equation04 = result04["saved_state_equation_decomposition"][
        "equation2_reconstruction_by_column"
    ]["column0"][0]
    assert equation04["equation2_reconstruction_complete"] is False
    assert "identity_bound_lambda_projection" in equation04["missing_terms"]

    contaminated = dict(attempt04["candidate_arrays"])
    first_key = next(iter(contaminated))
    corrupted = dict(contaminated[first_key])
    corrupted["returned_correction"] = corrupted["returned_correction"].copy()
    corrupted["returned_correction"][0] += 1.0e-4
    contaminated[first_key] = corrupted
    with pytest.raises(ValueError, match="contaminated relative to saved final_z"):
        _task41_p0_v16_replay_v14_star_saved_arrays(
            **{**attempt04, "candidate_arrays": contaminated}
        )


def test_v16_attempt04_default_context_binds_two_cell_v8_candidate_and_volume_rhs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from src.runners import task41_p0_v14_candidate_io as v14_io

    cells = (101, 102)
    active_row = 1
    original_row = 2
    fixtures = [
        _v16_saved_array_replay_fixture(
            attempt="04", cell=cell, interior_count=4, trace_count=3,
            monkeypatch=monkeypatch,
        )
        for cell in cells
    ]
    identities: dict[int, dict[str, object]] = {}
    results = (tmp_path / "results" / TASK41_MODEL_ID).resolve()
    arrays_dir = results / "v8_arrays"
    arrays_dir.mkdir(parents=True)
    inventory: list[dict[str, object]] = []

    def save_v8_array(name: str, values: np.ndarray) -> dict[str, object]:
        path = arrays_dir / f"{name}.npy"
        record = _write_array(path, np.asarray(values))
        record.update({"name": name, "path": str(path.resolve())})
        inventory.append(record)
        return {
            key: record[key]
            for key in ("name", "path", "sha256", "bytes", "shape", "dtype")
        }

    candidate_identity = {"source_sha": "a" * 40}
    metadata_cells: dict[str, dict[str, object]] = {}
    numeric_rows: list[dict[str, object]] = []
    p3_rows: list[dict[str, object]] = []
    candidate_arrays: dict[tuple[int, int], dict[str, np.ndarray]] = {}
    states_by_key: dict[tuple[int, int, str], dict[str, np.ndarray]] = {}
    actions_by_key: dict[tuple[int, int, str], np.ndarray] = {}
    cell_identity_digest: dict[int, str] = {}

    for cell, fixture in zip(cells, fixtures, strict=True):
        old_cell = next(iter(fixture["star_cells"]))
        old_star = fixture["star_cells"][old_cell]
        coordinates = np.full((8, 3), float(cell), dtype=np.float64)
        coordinate_sha = hashlib.sha256(
            memoryview(np.ascontiguousarray(coordinates)).cast("B")
        ).hexdigest()
        tag = 200 + cell
        permutation = "fixture-permutation"
        identities[cell] = {
            "cell_tag": tag,
            "permutation": permutation,
            "coordinate_sha256": coordinate_sha,
            "selected_local_trace_row": 0,
        }
        cell_identity_digest[cell] = coordinate_sha
        expansion = old_star["expansion"]
        metadata_values = {
            "actual_geometry_coordinates": coordinates,
            "interior_positions": np.asarray(old_star["interior_positions"], dtype=np.int32),
            "trace_positions": np.asarray(old_star["trace_positions"], dtype=np.int32),
            "trace_original_rows": np.asarray([original_row, 3, 4], dtype=np.int64),
            "active_ids": np.asarray([0, active_row, 2], dtype=np.int64),
            "trace_expansion_data": np.asarray(expansion.data, dtype=np.complex128),
            "trace_expansion_indices": np.asarray(expansion.indices, dtype=np.int32),
            "trace_expansion_indptr": np.asarray(expansion.indptr, dtype=np.int32),
            "selected_local_trace_rows": np.asarray([0], dtype=np.int32),
            "selected_trace_coefficients": np.asarray([1.0 + 0.0j], dtype=np.complex128),
        }
        metadata_refs = {
            name: save_v8_array(f"cell{cell}_{name}", values)
            for name, values in metadata_values.items()
        }
        metadata_cells[str(cell)] = {
            "cell_index": cell,
            "cell_tag": tag,
            "cell_permutation": permutation,
            "actual_coordinate_sha256": coordinate_sha,
            "arrays": metadata_refs,
        }

        matrix_arrays = fixtures[cells.index(cell)]["candidate_arrays"]
        first_local = matrix_arrays[(old_cell, 0)]
        matrix_refs = {
            "oriented_tensor": save_v8_array(
                f"cell{cell}_oriented_tensor", first_local["oriented_tensor"]
            ),
            "R": save_v8_array(f"cell{cell}_R", old_star["R"]),
            "S": save_v8_array(f"cell{cell}_S", old_star["S"]),
        }
        roles = [
            {
                "role": "candidate",
                "producer_identity": candidate_identity,
                "raw_oriented_RTS_artifacts": matrix_refs,
            },
            {"role": "reference"},
        ]
        numeric_rows.append({
            "cell_index": cell,
            "tag": tag,
            "permutation_and_direction": permutation,
            "actual_geometry_coordinates_sha256": coordinate_sha,
            "is_target_row_incident": True,
            "true_interior_positions": metadata_values["interior_positions"].tolist(),
            "trace_complement_positions": metadata_values["trace_positions"].tolist(),
            "trace_original_rows": metadata_values["trace_original_rows"].tolist(),
            "active_ids": metadata_values["active_ids"].tolist(),
            "roles": roles,
        })
        for column in (0, 1):
            candidate_arrays[(cell, column)] = {
                name: np.asarray(value)
                for name, value in matrix_arrays[(old_cell, column)].items()
            }
            for state in ("j0", "j3"):
                old_key = (old_cell, column, state)
                states_by_key[(cell, column, state)] = {
                    **fixture["states_by_key"][old_key],
                    "t_c": old_star["t_by_key"][(column, state)],
                    "b_i": fixture["candidate_arrays"][(old_cell, column)]["b_i"],
                }
                actions_by_key[(cell, column, state)] = fixture["saved_s_action_by_key"][old_key]

        signed_states = []
        for column in (0, 1):
            for state in ("j0", "j3"):
                operands = states_by_key[(cell, column, state)]
                local_refs = {
                    name: save_v8_array(
                        f"cell{cell}_column{column}_{state}_{name}", operands[name]
                    )
                    for name in ("u_i", "n_i", "t_c", "b_i")
                }
                action_ref = save_v8_array(
                    f"cell{cell}_column{column}_{state}_S_action",
                    actions_by_key[(cell, column, state)],
                )
                signed_states.append({
                    "column": column,
                    "state": state,
                    "roles": [
                        {
                            "role": "candidate",
                            "local_values": local_refs,
                            "signed_action_artifacts": {"S_action": action_ref},
                        },
                        {"role": "reference"},
                    ],
                })
        p3_rows.append({"cell_index": cell, "roles_and_states": signed_states})

    monkeypatch.setattr(v14_io, "V14_V8_STAR_CELLS", cells)
    monkeypatch.setattr(v14_io, "V14_V8_STAR_ACTIVE_ROW", active_row)
    monkeypatch.setattr(v14_io, "V14_V8_STAR_ORIGINAL_ROW", original_row)
    monkeypatch.setattr(v14_io, "V14_V8_STAR_IDENTITIES", identities)
    v8_payload = {
        "schema": "task41.p0.v8.selected_trace_star_audit_receipt.v1",
        "status": "COMPLETED_SELECTED_TRACE_STAR_AUDIT",
        "selected_trace_star_metadata": {
            "schema": "task41.p0.v8.selected_trace_star_metadata.v1",
            "selected_active_row": active_row,
            "selected_original_row": original_row,
            "incident_cell_order": list(cells),
            "cell_artifacts": metadata_cells,
        },
        "selected_trace_star_result": {
            "schema": "task41.p0.v8.selected_trace_star_audit_result.v1",
            "status": "COMPLETED_SELECTED_TRACE_STAR_AUDIT",
            "selected_active_row": active_row,
            "selected_original_row": original_row,
            "candidate_identity": candidate_identity,
            "local_numeric_cell_identity_and_artifacts": numeric_rows,
        },
        "selected_trace_star_p3_replay": {
            "schema": "task41.p0.v8.selected_trace_star_p3_replay.v1",
            "status": "COMPLETED_LOCAL_ROW_REPLAY",
            "complete_incident_cell_coverage": True,
            "selected_active_row": active_row,
            "selected_original_row": original_row,
            "per_cell_signed_contributions": p3_rows,
        },
        "persisted_evidence_arrays": inventory,
    }
    producer_path = results / "v8" / "selected_trace_star.json"
    producer_path.parent.mkdir(parents=True, exist_ok=True)
    producer_path.write_text(json.dumps(v8_payload, sort_keys=True, separators=(",", ":")) + "\n")
    producer_sha = _sha(producer_path)
    monkeypatch.setattr(v16_checker, "TASK41_P0_B0_V16_V8_STAR_REPORT_SHA256", producer_sha)
    monkeypatch.setattr(v14_io, "V14_V8_STAR_REPORT_SHA256", producer_sha)
    monkeypatch.setattr(v16_checker, "TASK41_P0_B0_V16_STORAGE_ROWS", 3)
    volume_scalars = fixtures[0]["b_volume_rhs_by_column"]
    monkeypatch.setattr(
        v16_checker,
        "_task41_p0_v16_v3_volume_rhs_scalars",
        lambda **_: (volume_scalars, {"fixture_v3_binding": True}),
    )

    rows = [dict(row, incident_cell_order=list(cells)) for row in fixtures[0]["rows"]]
    full_rhs_sources: dict[int, dict[str, object]] = {}
    alpha_sources: dict[int, dict[str, dict[str, object]]] = {}
    donor_root = results / "task41extra_b0_p6_phi90_07nm_iterative"
    donor_root.mkdir(parents=True)
    donor_vector_records: list[dict[str, object]] = []
    donor_source_bindings: dict[int, dict[str, tuple[object, ...]]] = {}

    def register_donor_source(
        column: int, role: str, filename: str, record: dict[str, object]
    ) -> dict[str, object]:
        indexed = {**record, "path": filename}
        donor_vector_records.append(indexed)
        donor_source_bindings.setdefault(column, {})[role] = (
            filename,
            record["sha256"],
            record["bytes"],
            record["dtype"],
            record["shape"],
        )
        return {key: indexed[key] for key in (
            "path", "sha256", "bytes", "dtype", "shape"
        )}

    for column in (0, 1):
        source = np.asarray(fixtures[0]["native_rhs_by_column"][column], dtype=np.complex128)
        full_rhs_name = f"column{column}_native_rhs.npy"
        full_rhs_path = donor_root / full_rhs_name
        full_rhs_sources[column] = register_donor_source(
            column, "native_rhs", full_rhs_name, _write_array(full_rhs_path, source)
        )
        alpha_rows = np.asarray([original_row], dtype=np.int64)
        alpha_value = np.asarray([fixtures[0]["b_alpha_by_column"][column]], dtype=np.complex128)
        alpha_rows_name = f"column{column}_b_alpha_rows.npy"
        alpha_values_name = f"column{column}_b_alpha_values.npy"
        alpha_rows_path = donor_root / alpha_rows_name
        alpha_values_path = donor_root / alpha_values_name
        alpha_sources[column] = {
            "rows": register_donor_source(
                column, "b_alpha_rows", alpha_rows_name,
                _write_array(alpha_rows_path, alpha_rows),
            ),
            "values": register_donor_source(
                column, "b_alpha_values", alpha_values_name,
                _write_array(alpha_values_path, alpha_value),
            ),
        }
        for row in rows:
            if row["column"] == column:
                row.update({
                    "base_b_t_source": full_rhs_sources[column],
                    "base_b_t": [float(source[original_row].real), float(source[original_row].imag)],
                    "b_alpha_sources": alpha_sources[column],
                    "b_alpha_row_used_once": [
                        float(alpha_value[0].real), float(alpha_value[0].imag)
                    ],
                })

    monkeypatch.setattr(
        v16_checker,
        "TASK41_P0_B0_V16_V3_ATTEMPT01_SOURCE_BINDINGS",
        donor_source_bindings,
    )
    donor_root = donor_root.resolve(strict=True)
    monkeypatch.setattr(
        v16_checker,
        "_task41_p0_v16_v3_donor_index",
        lambda **_: (
            {}, donor_root / "vector_index.json", donor_root,
            donor_root / "recovery_manifest.json", donor_vector_records,
        ),
    )

    candidate_rhs_rows = []
    for cell, fixture in zip(cells, fixtures, strict=True):
        old_cell = next(iter(fixture["star_cells"]))
        for column in (0, 1):
            arrays = fixture["candidate_arrays"][(old_cell, column)]
            rhs_record = {
                "cell_index": cell,
                "column": column,
                "actual_coordinate_sha256": cell_identity_digest[cell],
            }
            for field in (
                "b_i", "oriented_tensor", "interior_lu", "final_z",
                "returned_correction", "projected_active",
            ):
                rhs_record[field] = save_v8_array(
                    f"cell{cell}_column{column}_{field}", arrays[field]
                )
            candidate_rhs_rows.append(rhs_record)

    candidate = {
        "star_producer_report_path": str(producer_path.relative_to(results)),
        "star_producer_report_sha256": producer_sha,
        "candidate_rhs": candidate_rhs_rows,
    }
    spec = {
        "attempt": "04",
        "active_row": active_row,
        "original_row": original_row,
        "cells": list(cells),
        "states": {0: ("j0", "j3"), 1: ("j0", "j3")},
    }
    replay_inputs = v16_checker._task41_p0_v16_attempt04_replay_inputs(
        candidate=candidate,
        rows=rows,
        spec=spec,
        candidate_arrays=candidate_arrays,
        repo_root=tmp_path.resolve(),
        results_root=results,
    )
    assert replay_inputs["b_volume_rhs_by_column"] == volume_scalars
    assert replay_inputs["_binding_report"]["candidate_state_role_only"] == "candidate"
    assert replay_inputs["_binding_report"]["states_kept_separate"] == ["j0", "j3"]
    assert len(replay_inputs["_binding_report"]["state_input_bindings"]) == 8
    assert all(star["interior_lu_pivots"] is None for star in replay_inputs["star_cells"].values())
    assert len(replay_inputs["_binding_report"]["full_rhs"]) == 2
    assert len(replay_inputs["_binding_report"]["b_alpha"]) == 2
    for column in (0, 1):
        assert replay_inputs["_binding_report"]["full_rhs"][f"column{column}"]["path"] == str(
            donor_root / f"column{column}_native_rhs.npy"
        )
        assert replay_inputs["_binding_report"]["b_alpha"][f"column{column}"]["rows"]["path"] == str(
            donor_root / f"column{column}_b_alpha_rows.npy"
        )
        assert replay_inputs["_binding_report"]["b_alpha"][f"column{column}"]["values"]["path"] == str(
            donor_root / f"column{column}_b_alpha_values.npy"
        )
        column_rows = [row for row in rows if row["column"] == column]
        assert [row["state"] for row in column_rows] == ["j0", "j3"]
        assert all(row["base_b_t_source"]["path"] == f"column{column}_native_rhs.npy" for row in column_rows)
        assert all(row["b_alpha_sources"] == alpha_sources[column] for row in column_rows)


def test_v16_saved_final_z_wide_residual_reports_signed_lambda_impact():
    from src.solvers.hcurl_assembly_time_condensation import (
        _same_lu_binary64_compensated_residual,
    )

    two_to_53 = float(2**53)
    K = np.asarray([[two_to_53, 1.0], [0.0, 1.0]], dtype=np.complex128)
    b_i = np.asarray([two_to_53, 1.0], dtype=np.complex128)
    final_z = np.asarray([1.0, 1.0], dtype=np.complex128)
    r_f_matmul = np.asarray(b_i - K @ final_z, dtype=np.complex128)
    r_f_fsum = np.asarray(
        _same_lu_binary64_compensated_residual(K, b_i, final_z),
        dtype=np.complex128,
    )
    lambda_vector = np.asarray([1.0, 0.0], dtype=np.complex128)

    diagnostic = v16_checker._task41_p0_v16_final_residual_wide_diagnostic(
        K=K,
        b_i=b_i,
        final_z=final_z,
        r_f_matmul=r_f_matmul,
        r_f_fsum=r_f_fsum,
        lambda_vector=lambda_vector,
    )

    if not diagnostic["precision"]["wider_than_float64"]:
        pytest.skip("platform longdouble does not provide a wider mantissa")
    assert diagnostic["status"] == "WIDER_CLONGDOUBLE_EVALUATED"
    assert diagnostic["precision"]["float64_significand_bits"] == 53
    assert diagnostic["wide_residual_b_minus_Kz"]["max_value"] == ["-1.0", "0.0"]
    assert diagnostic["wide_minus_ordinary_binary64_matmul"]["l2"] == "1.0"
    assert diagnostic["wide_minus_compensated_binary64_fsum"]["l2"] == "0.0"
    projection = diagnostic["lambda_projection"]
    assert projection["lambda_H_r_f"]["ordinary_binary64_matmul_residual"] == [0.0, 0.0]
    assert projection["lambda_H_r_f"]["compensated_binary64_fsum_residual"] == [-1.0, 0.0]
    assert projection["lambda_H_r_f"]["independent_clongdouble_residual_and_dot"] == [
        "-1.0", "0.0"
    ]
    assert projection["wide_minus_binary64_fsum_projection"] == ["0.0", "0.0"]
    assert projection["signed_contribution_minus_lambda_H_r_f"][
        "compensated_binary64_fsum_residual"
    ] == [1.0, -0.0]
    assert projection["signed_contribution_minus_lambda_H_r_f"][
        "independent_clongdouble_residual_and_dot"
    ] == ["1.0", "-0.0"]
    assert diagnostic["not_used_for_correction_or_production_answer"] is True
    assert diagnostic["new_getrs_or_factorization_count"] == 0


def test_v16_v14_reader_hash_binds_saved_reports_and_keeps_local_pass_non_global(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    root = tmp_path
    results = root / "results" / TASK41_MODEL_ID
    window_sha = "f" * 64
    monkeypatch.setattr(v16_checker, "TASK41_P0_B0_V14_WINDOW_SHA256", window_sha)
    evidence_root = (
        results / "task41_p0_saved_diagnostics_6h" / window_sha / "selected_incident_replay"
    )
    entries: dict[tuple[str, str], tuple[str, str, str]] = {}
    index_entries = []
    saved = np.asarray([1.0 + 2.0j], dtype=np.complex128)
    saved_ref = _write_array(results / "arrays" / "saved_scalar.npy", saved)
    saved_ref["path"] = "arrays/saved_scalar.npy"
    saved_ref["dtype"] = saved.dtype.str
    y15 = (
        np.asarray([0j, 2 + 3j, 5 - 1j, 0j], dtype=np.complex128),
        np.asarray([0j, 4 - 2j, 7 + 6j, 0j], dtype=np.complex128),
    )
    g15 = (
        np.asarray([0j, 8 + 1j, 3 + 5j, 0j], dtype=np.complex128),
        np.asarray([0j, 9 - 4j, 6 - 7j, 0j], dtype=np.complex128),
    )
    star_specs = (
        {
            "attempt": "01", "stage": "initial_screen", "active_row": 1,
            "original_row": 250_113, "cells": [10, 20],
            "states": {0: (None,), 1: (None,)},
        },
        {
            "attempt": "04", "stage": "saved_star_extension", "active_row": 2,
            "original_row": 15_440_235, "cells": [30, 40],
            "states": {0: ("j0", "j3"), 1: ("j0", "j3")},
        },
    )

    def save_report(attempt: str, kind: str, relative: str, payload: dict[str, object], classification: str):
        path = evidence_root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
        digest = _sha(path)
        entries[(attempt, kind)] = (relative, digest, classification)
        index_entries.append({
            "attempt": attempt,
            "kind": kind,
            "path": relative,
            "sha256": digest,
            "classification": classification,
        })
        return path, digest

    for spec in star_specs:
        attempt = str(spec["attempt"])
        active = int(spec["active_row"])
        original = int(spec["original_row"])
        cells = list(spec["cells"])
        stage = str(spec["stage"])
        if attempt == "04":
            star_path = results / "metadata" / "attempt04_star.json"
            star_path.parent.mkdir(parents=True, exist_ok=True)
            star_path.write_text('{"schema":"fixture"}\n')
            star_report_ref = {
                "star_producer_report_path": "metadata/attempt04_star.json",
                "star_producer_report_sha256": _sha(star_path),
            }
        else:
            star_report_ref = {}
        state_rows = [
            (column, state)
            for column, state_labels in spec["states"].items()
            for state in state_labels
        ]
        production_rows = []
        for column, state in state_rows:
            row = {
                "column": column,
                "selected_active_row": active,
                "selected_original_row": original,
                "incident_cell_order": cells,
                "saved_y": [float(y15[column][active].real), float(y15[column][active].imag)],
                "candidate_g_actual_returned_correction_cell_order": [
                    float(g15[column][active].real), float(g15[column][active].imag)
                ],
            }
            if state is not None:
                row["state"] = state
            production_rows.append(row)
        candidate_rhs = [
            {
                "cell_index": cell,
                "column": column,
                **{field: saved_ref for field in (
                    "b_i", "oriented_tensor", "interior_lu", "final_z",
                    "returned_correction", "projected_active",
                )},
            }
            for cell in cells
            for column in (0, 1)
        ]
        candidate_path, candidate_sha = save_report(
            attempt,
            "saved_candidate_report" if attempt == "01" else "saved_star_candidate_report",
            f"attempt{attempt}/candidate.json",
            {
                "schema": "task41.p0.v14.saved_same_lu_rhs_candidate.v1",
                "status": "CANDIDATE_PRODUCED_PENDING_INDEPENDENT_CHECK",
                "official_result": False,
                "scientific_qualified": False,
                "consumer_window_sha256": window_sha,
                "producer_window_sha256": v16_checker.TASK41_P0_B0_V13_WINDOW_SHA256,
                "scope": {"stage": stage, "cells": cells, "columns": [0, 1], "full_owner": False},
                "getrs_count": 12,
                "new_evidence_bytes": 1,
                "candidate_rhs": candidate_rhs,
                "production_order_rows": production_rows,
                **star_report_ref,
            },
            "CANDIDATE_PRODUCED_PENDING_INDEPENDENT_CHECK",
        )
        checker_path, checker_sha = save_report(
            attempt,
            "wide_arithmetic_independent_check",
            f"attempt{attempt}/wide_check.json",
            {
                "schema": "task41.p0.v14.saved_same_lu_rhs_candidate_independent_check.v1",
                "status": "INCONCLUSIVE",
                "check_completed": True,
                "candidate_passed": None,
                "official_result": False,
                "scientific_qualified": False,
                "candidate_report_path": str(candidate_path),
                "candidate_report_sha256": candidate_sha,
                "consumer_window_sha256": window_sha,
                "full_owner_unlocked": False,
            },
            "INCONCLUSIVE",
        )
        decimal_path, decimal_sha = save_report(
            "03" if attempt == "01" else "06",
            "decimal_residual_recheck",
            f"attempt{attempt}/decimal.json",
            {
                "schema": "task41.p0.v14.saved_rhs_decimal_residual_recheck.v1",
                "status": "LOCAL_CANDIDATE_PASS",
                "candidate_passed": True,
                "check_completed": True,
                "official_result": False,
                "scientific_qualified": False,
                "full_owner_unlocked": False,
                "getrs_invoked": 0,
                "getrs_added": 0,
                "candidate_report_path": str(candidate_path),
                "candidate_report_sha256": candidate_sha,
                "prior_independent_check_path": str(checker_path),
                "prior_independent_check_sha256": checker_sha,
                "fixed_window_sha256": window_sha,
            },
            "LOCAL_CANDIDATE_PASS",
        )
        receipt_attempt = "03" if attempt == "01" else "06"
        save_report(
            receipt_attempt,
            "service_receipt",
            f"attempt{attempt}.service/receipt.json",
            {
                "schema": "task41.p0.saved_output_service_receipt.v1",
                "status": "completed",
                "result_classification": (
                    "V14_DECIMAL_SUPPLEMENTAL_PASS"
                    if attempt == "01"
                    else "V14_SAVED_COVERAGE_DECIMAL_PASS_NOT_GLOBAL"
                ),
                "window_sha256": window_sha,
                "v14_candidate_passed": True,
                "full_owner_unlocked": False,
                "official_result": False,
                "scientific_qualified": False,
                "v14_saved_candidate_report_path": str(candidate_path),
                "v14_saved_candidate_report_sha256": candidate_sha,
                "v14_prior_independent_check_path": str(checker_path),
                "v14_prior_independent_check_sha256": checker_sha,
                "v14_decimal_residual_check_path": str(decimal_path),
                "v14_decimal_residual_check_sha256": decimal_sha,
            },
            (
                "V14_DECIMAL_SUPPLEMENTAL_PASS"
                if attempt == "01"
                else "V14_SAVED_COVERAGE_DECIMAL_PASS_NOT_GLOBAL"
            ),
        )

    monkeypatch.setattr(
        v16_checker,
        "TASK41_P0_B0_V16_V14_EXPECTED_EVIDENCE_ENTRIES",
        entries,
    )
    index_path = root / "docs" / "v14_evidence_index.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps({
        "schema": "task41.p0.v14.closeout_evidence_index.v1",
        "review": "V14",
        "window": {"sha256": window_sha},
        "evidence_root": str(evidence_root),
        "entries": index_entries,
    }, sort_keys=True, separators=(",", ":")) + "\n")
    replay_calls: list[dict[str, object]] = []
    attempt04_default_calls: list[dict[str, object]] = []

    def attempt04_default_spy(**kwargs):
        attempt04_default_calls.append(kwargs)
        return {"star_cells": {"fixture": "attempt04-default"}}

    def replay_spy(**kwargs):
        replay_calls.append(kwargs)
        return {"schema": "fixture.replay", "status": "CALLED_FROM_V14_LOADER"}

    monkeypatch.setattr(
        v16_checker, "_task41_p0_v16_replay_v14_star_saved_arrays", replay_spy
    )
    monkeypatch.setattr(
        v16_checker, "_task41_p0_v16_attempt04_replay_inputs", attempt04_default_spy
    )
    result = load_task41_p0_b0_v16_v14_star_bindings(
        repo_root=root,
        results_root=results,
        y15=y15,
        g15=g15,
        evidence_index_path=index_path,
        evidence_index_sha256=_sha(index_path),
        star_specs=star_specs,
        include_saved_array_replay=True,
        saved_array_replay_inputs_by_attempt={
            "01": {"star_cells": {"fixture": "attempt01"}},
        },
    )
    assert [item["binding_status"] for item in result["stars"]] == [
        "V14_TERMINAL_Y_AND_G_EXACTLY_BOUND_TO_V15",
        "V14_TERMINAL_Y_AND_G_EXACTLY_BOUND_TO_V15",
    ]
    assert result["stars"][1]["terminal_comparisons"][0]["state"] == "j0"
    assert result["stars"][1]["terminal_comparisons"][1]["state"] == "j3"
    assert result["local_decimal_pass_is_not_global_qualification"] is True
    assert result["official_result"] is False
    assert result["full_owner_unlocked"] is False
    assert [call["attempt"] for call in replay_calls] == ["01", "04"]
    assert [call["star_cells"]["fixture"] for call in replay_calls] == [
        "attempt01", "attempt04-default"
    ]
    assert len(attempt04_default_calls) == 1
    assert attempt04_default_calls[0]["spec"]["attempt"] == "04"
    attempt04_candidate = attempt04_default_calls[0]["candidate"]
    attempt04_star_path = results / attempt04_candidate["star_producer_report_path"]
    assert _sha(attempt04_star_path) == attempt04_candidate["star_producer_report_sha256"]
    assert all(call["candidate_arrays"] for call in replay_calls)
    assert all(
        row["saved_array_replay"]["status"] == "CALLED_FROM_V14_LOADER"
        for row in result["stars"]
    )


def test_v16_manifest_binds_real_matrix_and_per_column_producer_layouts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    manifest_path, manifest_sha = _complete_v16_fixture(tmp_path, monkeypatch=monkeypatch)
    manifest, vectors, codes = load_task41_p0_b0_v16_saved_vector_manifest(
        manifest_path,
        manifest_sha,
        repo_root=tmp_path,
        expected_rows=4,
        expected_trace_rows=3,
    )
    assert vectors["y9"][0].tolist() == [2 + 0j, 2 + 0j, 3 + 0j, 0 + 0j]
    assert vectors["y9"][1].tolist() == [4 + 1j, 5 + 0j, 6 + 0j, 0 + 0j]
    assert vectors["y15"][0].tolist() == [3 + 0j, 2 + 0j, 3 + 0j, 0 + 0j]
    assert codes.shape == (3,)
    assert manifest["producer_identities"]["v9"]["source_sha"] != manifest["producer_identities"]["v15"]["source_sha"]
    assert manifest["verified_row_incidence_provenance"]["port_rows_kept_separate"] is True
    assert manifest["verified_max_row_probe_metadata"]["original_row"] == 101


def test_v16_metadata_persist_and_loader_recompute_active_row_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    manifest_path, _ = _complete_v16_fixture(tmp_path, monkeypatch=monkeypatch)
    manifest = json.loads(manifest_path.read_text())
    results = manifest_path.parent
    active_record = manifest["metadata_source"]["active_original_rows"]
    active_rows = np.load(results / active_record["path"], mmap_mode="r", allow_pickle=False)
    raw_sha256, array_sha256 = v16_checker._task41_p0_v16_active_rows_hashes(active_rows)
    assert raw_sha256 != array_sha256
    assert raw_sha256 == active_record["raw_bytes_sha256"]
    assert array_sha256 == active_record["array_sha256"]
    assert manifest["metadata_source"]["active_original_rows_values_sha256"] == array_sha256
    assert manifest["metadata_source"]["active_original_rows_raw_bytes_sha256"] == raw_sha256

    provenance = manifest["row_incidence_provenance"]
    assert provenance["schema"] == "task41.p0.b0.v16.row_incidence_metadata.v2"
    assert provenance["active_original_rows_raw_bytes_sha256"] == raw_sha256
    assert provenance["active_original_rows_array_sha256"] == array_sha256
    codes_record = manifest["row_group_codes"]
    codes = np.load(results / codes_record["path"], mmap_mode="r", allow_pickle=False)
    stage_dir = results / "attempt04" / "stage_a"
    stage_dir.mkdir(parents=True)
    coordinates0 = np.arange(24, dtype=np.float64).reshape(8, 3) + 10.0
    coordinates1 = np.arange(24, dtype=np.float64).reshape(8, 3) + 11.0

    def probe_cell(
        cell_id: int,
        tag: int,
        permutation: int,
        original: list[int],
        ids: list[int],
        coordinates: np.ndarray,
    ) -> dict[str, object]:
        return {
            "cell_index": cell_id,
            "cell_tag": tag,
            "cell_permutation": permutation,
            "active_ids": np.asarray(ids, dtype=np.int64),
            "trace_original_rows": np.asarray(original, dtype=np.int64),
            "trace_positions": np.asarray([0, 1], dtype=np.int64),
            "trace_expansion_data": np.asarray([1 + 0j, 1 + 0j], dtype=np.complex128),
            "trace_expansion_indices": np.asarray([0, 1], dtype=np.int32),
            "trace_expansion_indptr": np.asarray([0, 1, 2], dtype=np.int32),
            "actual_geometry_coordinates": coordinates,
            "actual_coordinate_sha256": hashlib.sha256(
                memoryview(np.ascontiguousarray(coordinates, dtype=np.float64)).cast("B")
            ).hexdigest(),
        }

    monkeypatch.setattr(v16_checker, "TASK41_P0_B0_V16_MAX_PROBE_ROW", 1)
    monkeypatch.setattr(v16_checker, "TASK41_P0_B0_V16_TRACE_ROWS", 3)
    scan = {
        "active_original_rows_record": active_record,
        "row_group_codes": np.asarray(codes, dtype=np.int32),
        "row_group_definitions": manifest["row_group_definitions"],
        "row_incidence_provenance": provenance,
        "mesh_metadata": {"resolved_config_sha256": "d" * 64},
        "probe_original_row": 101,
        "selected_probe_star": [
            probe_cell(10, 1, 0, [100, 101], [0, 1], coordinates0),
            probe_cell(11, 2, 4680, [101, 102], [1, 2], coordinates1),
        ],
    }
    derived_path, derived_sha, _ = v16_checker._task41_p0_v16_persist_metadata_bundle(
        manifest=manifest,
        scan=scan,
        stage_output_dir=stage_dir,
        results_root=results,
    )
    loaded, _, _ = load_task41_p0_b0_v16_saved_vector_manifest(
        derived_path, derived_sha, repo_root=tmp_path, expected_rows=4, expected_trace_rows=3
    )
    verified = loaded["verified_metadata_source"]
    assert verified["active_original_rows_values_sha256"] == array_sha256
    assert verified["active_original_rows_raw_bytes_sha256"] == raw_sha256

    derived = json.loads(derived_path.read_text())
    derived["metadata_source"]["active_original_rows"]["raw_bytes_sha256"] = "0" * 64
    derived["metadata_source"]["active_original_rows_raw_bytes_sha256"] = "0" * 64
    derived["row_incidence_provenance"]["active_original_rows_raw_bytes_sha256"] = "0" * 64
    derived_path.write_text(json.dumps(derived, sort_keys=True, separators=(",", ":")) + chr(10))
    with pytest.raises(ValueError, match="active-original-row source map differs"):
        load_task41_p0_b0_v16_saved_vector_manifest(
            derived_path,
            _refresh_manifest_sha(derived_path),
            repo_root=tmp_path,
            expected_rows=4,
            expected_trace_rows=3,
        )


def test_v16_manifest_rejects_bad_hash_column_swap_and_producer_metadata_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    manifest_path, manifest_sha = _complete_v16_fixture(tmp_path, monkeypatch=monkeypatch)
    with pytest.raises(ValueError, match="manifest path, size, or SHA-256"):
        load_task41_p0_b0_v16_saved_vector_manifest(
            manifest_path, "0" * 64, repo_root=tmp_path, expected_rows=4, expected_trace_rows=3
        )

    manifest = json.loads(manifest_path.read_text())
    manifest["arrays"]["y15"].reverse()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(ValueError, match="manifest layout/column"):
        load_task41_p0_b0_v16_saved_vector_manifest(
            manifest_path, _refresh_manifest_sha(manifest_path), repo_root=tmp_path,
            expected_rows=4, expected_trace_rows=3,
        )

    manifest_path, _ = _complete_v16_fixture(tmp_path / "second", monkeypatch=monkeypatch)
    manifest = json.loads(manifest_path.read_text())
    manifest["arrays"]["y15"][0]["bytes"] += 1
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
    with pytest.raises(ValueError, match="not bound to its producer report: bytes"):
        load_task41_p0_b0_v16_saved_vector_manifest(
            manifest_path, _refresh_manifest_sha(manifest_path), repo_root=tmp_path / "second",
            expected_rows=4, expected_trace_rows=3,
        )



def test_v16_metadata_pending_analyzer_admits_resources_before_mesh_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from datetime import datetime, timedelta, timezone
    from types import SimpleNamespace
    from src.runners.task41_p0_contract import (
        TASK41_B0_V16_SAVED_VECTOR_SCOPE,
        TASK41_HOST_RESERVE_BYTES,
        TASK41_TASK_MEMORY_MAX_BYTES,
    )
    from src.solvers import task40_v22_operator_probe as resource_probe

    manifest_path, _ = _complete_v16_fixture(tmp_path, monkeypatch=monkeypatch)
    real_manifest_loader = v16_checker.load_task41_p0_b0_v16_saved_vector_manifest

    def small_manifest_loader(*args, **kwargs):
        kwargs.setdefault("expected_rows", 4)
        kwargs.setdefault("expected_trace_rows", 3)
        return real_manifest_loader(*args, **kwargs)

    monkeypatch.setattr(
        v16_checker, "load_task41_p0_b0_v16_saved_vector_manifest", small_manifest_loader
    )
    manifest = json.loads(manifest_path.read_text())
    manifest["metadata_pending"] = True
    for name in (
        "row_group_codes", "row_group_definitions", "row_incidence_provenance",
        "max_row_probe_metadata",
    ):
        manifest.pop(name)
    manifest_path.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n")
    manifest_sha = _sha(manifest_path)

    root = tmp_path.resolve()
    results = root / "results" / TASK41_MODEL_ID
    stage_dir = results / "v16" / "attempt01.service"
    stage_dir.mkdir(parents=True)
    window_path = root / v16_checker.TASK41_B0_V16_SAVED_VECTOR_WINDOW_RELATIVE
    window_path.parent.mkdir(parents=True, exist_ok=True)
    t0 = datetime.now(timezone.utc).replace(microsecond=0)
    window_payload = {
        "t0_utc": t0.isoformat().replace("+00:00", "Z"),
        "numerical_deadline_utc": (t0 + timedelta(seconds=20_400)).isoformat().replace("+00:00", "Z"),
        "deadline_utc": (t0 + timedelta(seconds=21_600)).isoformat().replace("+00:00", "Z"),
        "total_seconds": 21_600.0,
        "numerical_seconds": 20_400.0,
        "closeout_seconds": 1_200.0,
    }
    window_path.write_text(json.dumps(window_payload, sort_keys=True, separators=(",", ":")) + "\n")
    contract = {
        "execution_scope": TASK41_B0_V16_SAVED_VECTOR_SCOPE,
        "time": {
            "total_seconds": 21_600.0,
            "numerical_seconds": 20_400.0,
            "closeout_seconds": 1_200.0,
        },
        "resources": {
            "task_memory_max_bytes": TASK41_TASK_MEMORY_MAX_BYTES,
            "host_reserve_bytes": TASK41_HOST_RESERVE_BYTES,
            "memory_swap_max_bytes": 0,
        },
        "window": {
            "path": str(window_path.relative_to(root)),
            "sha256": _sha(window_path),
        },
    }
    resource_calls: list[dict[str, object]] = []
    scan_calls: list[str] = []

    def resource_admission(stage, additional_bytes, **kwargs):
        resource_calls.append({"stage": stage, "additional_bytes": additional_bytes, **kwargs})
        return {
            "current_process_cgroup": {
                "dedicated_job_cgroup": True,
                "memory_limit_bytes": TASK41_TASK_MEMORY_MAX_BYTES,
                "memory_current_bytes": 128 * 1024**2,
                "swap_current_bytes": 0,
            },
            "host_effective_available_bytes": TASK41_HOST_RESERVE_BYTES + 32 * 1024**3,
        }

    monkeypatch.setattr(resource_probe, "_resource_admission", resource_admission)
    monkeypatch.setattr(
        v16_checker.shutil,
        "disk_usage",
        lambda _: SimpleNamespace(free=3 * 1024**3),
    )

    def scan_spy(**kwargs):
        scan_calls.append("scan")
        raise RuntimeError("fixture stops before mesh traversal")

    monkeypatch.setattr(v16_checker, "_task41_p0_v16_scan_same_mesh_row_metadata", scan_spy)
    with pytest.raises(RuntimeError, match="fixture stops before mesh traversal"):
        v16_checker.analyze_task41_p0_b0_v16_saved_vector_distribution(
            manifest_path=manifest_path,
            manifest_sha256=manifest_sha,
            repo_root=root,
            execution_contract=contract,
            stage_output_dir=stage_dir,
        )
    assert len(resource_calls) == 1
    assert resource_calls[0]["additional_bytes"] == 16 * 1024**3
    assert resource_calls[0]["explicit_process_tree_cap_bytes"] == TASK41_TASK_MEMORY_MAX_BYTES
    assert resource_calls[0]["host_reserve_bytes"] == TASK41_HOST_RESERVE_BYTES
    assert resource_calls[0]["task_cgroup_reserve_bytes"] == 0
    assert scan_calls == ["scan"]


def test_v16_cli_default_route_passes_bound_contract_to_saved_analyzer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from src.runners.task41_p0_contract import TASK41_B0_V16_SAVED_VECTOR_SCOPE

    root = tmp_path.resolve()
    fake_module = root / "src" / "runners" / "task41_p0_checker.py"
    fake_module.parent.mkdir(parents=True)
    fake_module.touch()
    monkeypatch.setattr(v16_checker, "__file__", str(fake_module))
    manifest_path = root / "results" / TASK41_MODEL_ID / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("{}\n")
    contract_path = root / "docs" / "fixture_contract.json"
    contract_path.parent.mkdir(parents=True)
    contract_path.write_text("{}\n")
    window_sha = "a" * 64
    contract = {
        "execution_scope": TASK41_B0_V16_SAVED_VECTOR_SCOPE,
        "source": {"sha": "e" * 40},
        "window": {
            "path": str(v16_checker.TASK41_B0_V16_SAVED_VECTOR_WINDOW_RELATIVE),
            "sha256": window_sha,
        },
    }
    monkeypatch.setattr(
        v16_checker,
        "require_task41_p0_contract",
        lambda *args, **kwargs: (contract, "b" * 64),
    )
    monkeypatch.setattr(v16_checker, "task41_raw_artifact_limit_bytes", lambda _: 16 * 1024**3)
    stage_root = (
        root / "results" / TASK41_MODEL_ID / "task41_p0_saved_diagnostics_6h"
        / window_sha / "saved_vector_distribution"
    )
    stage_dir = stage_root / "attempt01.service"
    stage_dir.mkdir(parents=True)
    output_path = stage_dir / "task41_p0_checker_result.json"
    analyzer_calls: list[dict[str, object]] = []

    def analyzer_spy(**kwargs):
        analyzer_calls.append(kwargs)
        return {
            "schema": "task41.p0.b0.v16.saved_vector_distribution.v1",
            "status": "COMPLETED_DIAGNOSTIC_ONLY",
            "data_integrity": True,
            "official_result": False,
        }

    monkeypatch.setattr(
        v16_checker,
        "analyze_task41_p0_b0_v16_saved_vector_distribution",
        analyzer_spy,
    )
    result = v16_checker.main([
        "--saved-b0-v16-vector-analysis",
        "--manifest", str(manifest_path),
        "--manifest-sha256", "c" * 64,
        "--contract", str(contract_path),
        "--contract-sha256", "d" * 64,
        "--output", str(output_path),
    ])
    assert result == 0
    assert len(analyzer_calls) == 1
    assert analyzer_calls[0]["execution_contract"] is contract
    assert analyzer_calls[0]["repo_root"] == root
    assert analyzer_calls[0]["stage_output_dir"] == output_path.parent
    saved = json.loads(output_path.read_text())
    assert saved["status"] == "COMPLETED_DIAGNOSTIC_ONLY"
    assert saved["official_result"] is False


def test_v16_stage_a_checkpoint_survives_stage_b_failure_and_is_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    manifest_path, manifest_sha = _complete_v16_fixture(tmp_path, monkeypatch=monkeypatch)
    results = (tmp_path / "results" / TASK41_MODEL_ID).resolve()
    first_output = results / "v16" / "attempt01.service"
    retry_output = results / "v16" / "attempt02.service"
    first_output.mkdir(parents=True)
    retry_output.mkdir(parents=True)
    summarize_calls = 0
    real_summarize = v16_checker.summarize_task41_p0_b0_v16_saved_vectors
    real_manifest_loader = v16_checker.load_task41_p0_b0_v16_saved_vector_manifest

    def small_manifest_loader(*args, **kwargs):
        kwargs.setdefault("expected_rows", 4)
        kwargs.setdefault("expected_trace_rows", 3)
        return real_manifest_loader(*args, **kwargs)

    monkeypatch.setattr(
        v16_checker,
        "load_task41_p0_b0_v16_saved_vector_manifest",
        small_manifest_loader,
    )

    def summarize_spy(**kwargs):
        nonlocal summarize_calls
        summarize_calls += 1
        return real_summarize(**kwargs)

    monkeypatch.setattr(v16_checker, "summarize_task41_p0_b0_v16_saved_vectors", summarize_spy)
    monkeypatch.setattr(
        v16_checker,
        "load_task41_p0_b0_v16_v14_star_bindings",
        lambda **_: (_ for _ in ()).throw(ValueError("fixture Stage B failure")),
    )
    first = v16_checker.analyze_task41_p0_b0_v16_saved_vector_distribution(
        manifest_path=manifest_path,
        manifest_sha256=manifest_sha,
        repo_root=tmp_path,
        stage_output_dir=first_output,
    )
    assert first["status"] == "INCOMPLETE"
    assert first["stage_b"]["status"] == "INCOMPLETE_LOCAL_TERMINAL_REPLAY"
    assert summarize_calls == 1
    resume = first["stage_a_resume_manifest"]
    monkeypatch.setattr(
        v16_checker,
        "load_task41_p0_b0_v16_v14_star_bindings",
        lambda **_: {
            "stars": [
                {"attempt": attempt, "saved_array_replay": {"complete": True}}
                for attempt in ("01", "04")
            ]
        },
    )
    second = v16_checker.analyze_task41_p0_b0_v16_saved_vector_distribution(
        manifest_path=resume["path"],
        manifest_sha256=resume["sha256"],
        repo_root=tmp_path,
        stage_output_dir=retry_output,
    )
    assert second["status"] == "COMPLETED_DIAGNOSTIC_ONLY"
    assert second["stage_b"]["status"] == "COMPLETED_LOCAL_TERMINAL_REPLAY"
    assert summarize_calls == 1
    assert second["stage_a"]["path"] == first["stage_a"]["path"]


def test_v16_summary_counts_signed_improved_worsened_unchanged_rows_once_per_group():
    y9 = (np.asarray([2, 2, 3, 0], dtype=np.complex128),) * 2
    g9 = (np.asarray([1, 1, 3, 0], dtype=np.complex128),) * 2
    y15 = (np.asarray([3, 2, 3, 0], dtype=np.complex128),) * 2
    g15 = (np.asarray([1, 1.5, 3, 0], dtype=np.complex128),) * 2
    definitions = [{
        "code": 0,
        "incident_tag_codes": [0],
        "direction_codes": [0],
        "incident_cell_count": 1,
        "periodic_slave_e_incident_cell_count": 0,
        "has_nontrivial_mpc": False,
    }]
    provenance = {
        "schema": "task41.p0.b0.v16.row_incidence_metadata.v1",
        "row_count": 3,
        "covered_active_rows": 3,
        "periodic_slave_e_expanded": True,
        "one_mutually_exclusive_code_per_trace_row": True,
        "port_rows_kept_separate": True,
    }
    result = summarize_task41_p0_b0_v16_saved_vectors(
        y9=y9,
        g9=g9,
        y15=y15,
        g15=g15,
        trace_rows=3,
        dynamic_denominators_v9=(3.0, 3.0),
        dynamic_denominators_v15=(3.0, 3.0),
        frozen_denominators=(2.2, 2.3),
        row_group_codes=np.asarray([0, 0, 0], dtype=np.int32),
        row_group_definitions=definitions,
        row_incidence_provenance=provenance,
        probe_row=1,
        block_rows=2,
    )
    grouped = result["row_incident_groups"]["groups"]
    states = {item["region_state"]: item["rows"] for item in grouped}
    assert states == {"trace_improved": 1, "trace_unchanged": 1, "trace_worsened": 1}
    assert sum(states.values()) == 3
    assert result["columns"][0]["regions"]["trace"]["row_change"]["improved"]["rows"] == 1
    assert result["columns"][0]["regions"]["trace"]["row_change"]["worsened"]["rows"] == 1
    assert result["columns"][0]["regions"]["trace"]["row_change"]["unchanged"]["rows"] == 1
    assert result["full_size_complex_differences_persisted"] is False


def test_v16_zero_error_and_zero_total_energy_have_finite_coverage():
    zero = np.zeros(3, dtype=np.complex128)
    result = summarize_task41_p0_b0_v16_saved_vectors(
        y9=(zero, zero),
        g9=(zero, zero),
        y15=(zero, zero),
        g15=(zero, zero),
        trace_rows=2,
        dynamic_denominators_v9=(1.0, 1.0),
        dynamic_denominators_v15=(1.0, 1.0),
        frozen_denominators=(1.0, 1.0),
        probe_row=0,
        block_rows=2,
    )
    for column in result["columns"]:
        assert column["top_k"]["1"]["energy_fraction"] == 1.0
        assert column["minimum_rows_for_energy_coverage"]["90_percent"]["minimum_rows"] == 0
        assert column["minimum_rows_for_energy_coverage"]["ideal_required"]["minimum_rows"] == 0
        assert column["current_gate_relative_l2_max_dynamic_frozen"] == 0.0
    assert result["two_column_top_10000_union"]["coverage_by_column"]["0"]["energy_fraction"] == 1.0
