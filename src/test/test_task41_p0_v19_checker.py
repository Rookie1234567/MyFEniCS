from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np

from src.runners import task41_p0_v19_checker as checker
from src.runners import task41_p0_v19_native_rank1 as capture


def _identity_with_digest(identity: dict[str, Any]) -> dict[str, Any]:
    result = dict(identity)
    result["identity_sha256"] = checker._json_hash(identity)
    return result


def _cache_hit_run_identity() -> dict[str, Any]:
    components: dict[str, Any] = {}
    for component in ("curl", "material_mass"):
        module_name = f"fixture_{component}_ffcx"
        module_file = f"/ffcx-cache/{module_name}.cpython-312-x86_64-linux-gnu.so"
        component_identity: dict[str, Any] = {
            "component": component,
            "ffcx_generated_code_status": "CACHE_HIT_CODE_NOT_RETURNED",
            "ffcx_generated_code_sha256": None,
            "ffcx_generated_c_source_identity": {
                "module_name": module_name,
                "module_path": module_file,
                "c_source_path": f"/ffcx-cache/{module_name}.c",
                "c_source_bytes": 128,
                "c_source_sha256": "3" * 64,
                "c_source_status": "HASHED_FROM_FFCX_CACHE",
            },
            "compiled_module": {
                "module_name": module_name,
                "module_file": module_file,
                "module_file_sha256": "4" * 64,
                "module_file_status": "HASHED",
            },
            "ufl_signatures": {"bilinear": "fixture", "rank1_action": "fixture"},
            "jit_options": {},
            "abi_identity": {"fixture": "abi"},
            "integral_inventory": {"fixture": component},
        }
        component_identity["identity_sha256"] = checker._json_hash(component_identity)
        components[component] = component_identity
    native_identity: dict[str, Any] = {
        "schema": "task41.p0.v19.native_capture_identity.v1",
        "abi_identity": {"fixture": "abi"},
        "component_identities": components,
    }
    native_identity["identity_sha256"] = checker._json_hash(native_identity)
    return {
        "source_sha256": "1" * 64,
        "window_sha256": "2" * 64,
        "native_capture_identity": native_identity,
    }


def _refresh_native_identity_hashes(run_identity: dict[str, Any]) -> None:
    native = run_identity["native_capture_identity"]
    for identity in native["component_identities"].values():
        unsigned = {key: value for key, value in identity.items() if key != "identity_sha256"}
        identity["identity_sha256"] = checker._json_hash(unsigned)
    unsigned_native = {
        key: value for key, value in native.items() if key != "identity_sha256"
    }
    native["identity_sha256"] = checker._json_hash(unsigned_native)


def _bundle(root: Path) -> tuple[dict[str, Any], dict[str, Any], dict[tuple[str, int], list[tuple[int, int, int, int]]]]:
    term_directory = root / "native_rank1_terms"
    term_directory.mkdir(parents=True)
    run_identity = _cache_hit_run_identity()
    inventory: dict[str, Any] = {}
    capture_rows: list[dict[str, Any]] = []
    progress_terms: dict[str, Any] = {}

    for component in ("curl", "material_mass"):
        inventory[component] = {
            "cpp_integral_index_order": [0],
            "ufcx_physical_integral_ids": [17],
            "expected_selected_kernel_invocations": 2,
            "kernel_inventory_from_compiled_form": [{
                "cpp_integral_index": 0,
                "ufcx_kernel_position": 3,
                "ufcx_physical_integral_id": 17,
                "domain_entity_count": 6,
                "selected_entity_positions": [2, 5],
                "selected_entity_cell_order": [7873, 8014],
            }],
        }
        for column in capture.V19_COLUMNS:
            records = []
            for position, cell in zip((2, 5), capture.V19_SELECTED_CELLS, strict=True):
                arrays = {
                    "raw_kernel_output": np.full(882, 1 + 2j, dtype=np.complex128),
                    "oriented_test_vector": np.full(882, 3 - 1j, dtype=np.complex128),
                    "packed_coefficient_row": np.asarray([2 + 4j, 1 - 3j], dtype=np.complex128),
                    "packed_constants": np.asarray([5 + 0j], dtype=np.complex128),
                    "local_dofs": np.arange(882, dtype=np.int32),
                    "original_dofs": np.arange(882, dtype=np.int64) + cell * 1000,
                    "geometry_dof_indices": np.arange(8, dtype=np.int32),
                    "geometry_coordinates": np.arange(24, dtype=np.float64),
                }
                input_fields = {
                    "packed_coefficient_row", "packed_constants", "local_dofs",
                    "original_dofs", "geometry_dof_indices", "geometry_coordinates",
                }
                base_identity = {
                    "component": component,
                    "column": column,
                    "cell_index": cell,
                    "cpp_integral_index": 0,
                    "ufcx_physical_integral_id": 17,
                    "entity_position": position,
                    "array_identities": {
                        name: capture._array_identity(arrays[name]) for name in input_fields
                    },
                }
                term = {
                    **{name: arrays[name] for name in capture._TERM_ARRAY_FIELDS},
                    "component": component,
                    "column": column,
                    "cell_index": cell,
                    "cpp_integral_index": 0,
                    "ufcx_physical_integral_id": 17,
                    "entity_position": position,
                    "term_identity": _identity_with_digest(base_identity),
                    "capture_status": "CAPTURED_FINITE",
                    "capture_error": None,
                }
                saved = capture._write_term_archive(
                    term, term_directory=term_directory, output_directory=root
                )
                record = {
                    "component": component,
                    "column": column,
                    "cell_index": cell,
                    "cpp_integral_index": 0,
                    "ufcx_physical_integral_id": 17,
                    "entity_position": position,
                    "term_identity": term["term_identity"],
                    **saved,
                }
                records.append(record)
                progress_terms[checker._term_key(component, column, cell, 0)] = {
                    "archive_sha256": saved["archive_sha256"],
                    "term_identity": term["term_identity"],
                    "archive_binding_status": saved["archive_binding_status"],
                    "capture_status": saved["capture_status"],
                    "array_artifacts": saved["array_artifacts"],
                }
            capture_rows.append({
                "component": component,
                "column": column,
                "expected_selected_kernel_invocations": 2,
                "completed_selected_kernel_terms": 2,
                "terms": records,
            })

    receipt = {
        "run_identity": run_identity,
        "run_identity_sha256": checker._json_hash(run_identity),
        "stage_timings_seconds": {
            "mesh_construction_seconds": 0.0,
            "fresh_map_validation_seconds": 0.0,
            "form_jit_action_construction_seconds": 0.0,
            "coefficient_table_packing_seconds": 0.0,
            "selected_coefficient_row_packing_seconds": 0.0,
            "kernel_execution_seconds": 0.0,
            "direction_transform_seconds": 0.0,
            "term_archive_save_seconds": 0.0,
        },
        "worker_function_elapsed_seconds_pre_receipt_write": 0.0,
        "actual_integral_inventory": inventory,
        "component_column_captures": capture_rows,
    }
    progress = {
        "schema": capture.V19_PROGRESS_SCHEMA,
        "run_identity": run_identity,
        "run_identity_sha256": checker._json_hash(run_identity),
        "terms": progress_terms,
    }
    return receipt, progress, checker._expected_terms(receipt)


def test_checker_validates_returned_code_and_ffcx_cache_hit_identities() -> None:
    identity = _cache_hit_run_identity()
    checker._validate_native_capture_identity(identity)

    returned_code = json.loads(json.dumps(identity))
    for component in returned_code["native_capture_identity"]["component_identities"].values():
        component["ffcx_generated_code_status"] = "CODE_RETURNED"
        component["ffcx_generated_code_sha256"] = "5" * 64
        component["ffcx_generated_c_source_identity"] = None
    _refresh_native_identity_hashes(returned_code)
    checker._validate_native_capture_identity(returned_code)

    bad_module = json.loads(json.dumps(identity))
    bad_module["native_capture_identity"]["component_identities"]["curl"][
        "compiled_module"
    ]["module_file_status"] = "UNAVAILABLE"
    _refresh_native_identity_hashes(bad_module)
    with np.testing.assert_raises_regex(ValueError, "compiled module artifact"):
        checker._validate_native_capture_identity(bad_module)

    bad_source = json.loads(json.dumps(identity))
    bad_source["native_capture_identity"]["component_identities"]["curl"][
        "ffcx_generated_c_source_identity"
    ]["c_source_bytes"] = 0
    _refresh_native_identity_hashes(bad_source)
    with np.testing.assert_raises_regex(ValueError, "cache-hit C-source identity"):
        checker._validate_native_capture_identity(bad_source)


def test_independent_checker_compares_tag_and_permutation_with_v17_identity() -> None:
    saved_cell = {"cell_tag": 1, "cell_permutation": 0}
    metadata_cell = {"cell_tag": 1, "cell_permutation": 0}
    receipt_row = {"cell_index": 7873, "tag": 1, "permutation": 0}
    checker._validate_saved_v17_cell_direction(
        cell=7873,
        saved_cell=saved_cell,
        metadata_cell=metadata_cell,
        receipt_row=receipt_row,
    )
    for field, wrong in (("tag", 2), ("permutation", 1)):
        with np.testing.assert_raises_regex(ValueError, "tag/permutation"):
            checker._validate_saved_v17_cell_direction(
                cell=7873,
                saved_cell=saved_cell,
                metadata_cell=metadata_cell,
                receipt_row={**receipt_row, field: wrong},
            )



def test_dynamic_inventory_accepts_per_tag_cell_subsets_and_empty_kernels(tmp_path: Path) -> None:
    receipt, _progress, _order = _bundle(tmp_path)
    # Keep each selected cell on a distinct tag kernel, with one empty
    # selected-cell subset between them. The C++ integral inventory remains
    # in the form's original kernel order.
    for component in ("curl", "material_mass"):
        summary = receipt["actual_integral_inventory"][component]
        summary["cpp_integral_index_order"] = [0, 1, 2]
        summary["ufcx_physical_integral_ids"] = [17, 18, 19]
        summary["expected_selected_kernel_invocations"] = 2
        summary["kernel_inventory_from_compiled_form"] = [
            {
                "cpp_integral_index": 0, "ufcx_kernel_position": 3,
                "ufcx_physical_integral_id": 17, "domain_entity_count": 6,
                "selected_entity_positions": [2], "selected_entity_cell_order": [7873],
            },
            {
                "cpp_integral_index": 1, "ufcx_kernel_position": 4,
                "ufcx_physical_integral_id": 18, "domain_entity_count": 6,
                "selected_entity_positions": [], "selected_entity_cell_order": [],
            },
            {
                "cpp_integral_index": 2, "ufcx_kernel_position": 5,
                "ufcx_physical_integral_id": 19, "domain_entity_count": 6,
                "selected_entity_positions": [5], "selected_entity_cell_order": [8014],
            },
        ]
        for column in capture.V19_COLUMNS:
            row = next(
                item for item in receipt["component_column_captures"]
                if item["component"] == component and item["column"] == column
            )
            old_terms = {term["cell_index"]: term for term in row["terms"]}
            rewritten = []
            for integral, physical, position, cell in (
                (0, 17, 2, 7873), (2, 19, 5, 8014)
            ):
                term = dict(old_terms[cell])
                term.update({
                    "cpp_integral_index": integral,
                    "ufcx_physical_integral_id": physical,
                    "entity_position": position,
                })
                identity = {
                    key: value for key, value in term["term_identity"].items()
                    if key != "identity_sha256"
                }
                identity.update({
                    "cpp_integral_index": integral,
                    "ufcx_physical_integral_id": physical,
                    "entity_position": position,
                })
                term["term_identity"] = _identity_with_digest(identity)
                rewritten.append(term)
            row["terms"] = rewritten
            row["expected_selected_kernel_invocations"] = 2
            row["completed_selected_kernel_terms"] = 2

    expected = checker._expected_terms(receipt)
    assert expected[("curl", 0)] == [(0, 17, 2, 7873), (2, 19, 5, 8014)]
    assert expected[("material_mass", 1)] == [(0, 17, 2, 7873), (2, 19, 5, 8014)]

def test_checker_reopens_all_dynamic_term_archives_and_input_maps(tmp_path: Path) -> None:
    receipt, progress, order = _bundle(tmp_path)

    reopened, errors = checker._load_term_archives(receipt, progress, tmp_path, order)

    assert not errors
    assert len(reopened) == 8
    assert all(term["arrays"]["original_dofs"].shape == (882,) for term in reopened.values())
    assert all(
        saved["archive_binding_status"] == "CHECKPOINT_SHA256_VERIFIED"
        for capture_row in receipt["component_column_captures"]
        for saved in capture_row["terms"]
    )


def test_checker_rejects_resigned_member_when_external_archive_sha_is_stale(tmp_path: Path) -> None:
    receipt, progress, order = _bundle(tmp_path)
    record = receipt["component_column_captures"][0]["terms"][0]
    archive_path = tmp_path / record["array_artifacts"]["raw_kernel_output"]["path"]
    with np.load(archive_path, allow_pickle=False) as archive:
        members = {name: np.asarray(archive[name]).copy() for name in archive.files}
    metadata = json.loads(str(members["term_metadata"].item()))
    members["oriented_test_vector"][0] += 4j
    metadata["capture_array_identities"]["oriented_test_vector"] = capture._array_identity(
        members["oriented_test_vector"]
    )
    members["term_metadata"] = np.asarray(json.dumps(metadata, sort_keys=True))
    with archive_path.open("wb") as stream:
        np.savez(stream, **members)

    reopened, errors = checker._load_term_archives(receipt, progress, tmp_path, order)

    assert len(reopened) == 7
    assert any("archive bytes differ from the receipt SHA-256" in error for error in errors)


def test_orphan_archive_is_retained_but_never_checkpoint_bound(tmp_path: Path) -> None:
    receipt, progress, order = _bundle(tmp_path)
    record = receipt["component_column_captures"][0]["terms"][0]
    record["archive_binding_status"] = "ORPHAN_ATOMIC_ARCHIVE_INTERNAL_IDENTITY_ONLY"
    state_key = checker._term_key("curl", 0, 7873, 0)
    progress["terms"][state_key]["archive_binding_status"] = (
        "ORPHAN_ATOMIC_ARCHIVE_INTERNAL_IDENTITY_ONLY"
    )

    reopened, errors = checker._load_term_archives(receipt, progress, tmp_path, order)

    assert len(reopened) == 8
    assert any("orphan archive is retained but not checkpoint-bound" in error for error in errors)
    assert record["archive_sha256"] == reopened[("curl", 0, 7873, 0)]["archive_sha256"]


def test_checker_rejects_term_order_that_differs_from_dynamic_entity_inventory(tmp_path: Path) -> None:
    receipt, _progress, _order = _bundle(tmp_path)
    receipt["component_column_captures"][0]["terms"].reverse()

    try:
        checker._expected_terms(receipt)
    except ValueError as exc:
        assert "not in integral/entity order" in str(exc)
    else:
        raise AssertionError("reordered term receipt was accepted")



def test_audit_column_recomputes_b_alpha_after_loading_sparse_values() -> None:
    target = 5_218_672
    terms: dict[tuple[str, int, int, int], dict[str, Any]] = {}
    cells: dict[int, dict[str, Any]] = {}
    reference: dict[tuple[int, int], dict[str, np.ndarray]] = {}
    for cell_index, base in zip(capture.V19_SELECTED_CELLS, (10_000, 20_000), strict=True):
        local_dofs = np.concatenate((
            np.asarray([target], dtype=np.int32),
            np.arange(base, base + 881, dtype=np.int32),
        ))
        original_rows = local_dofs.astype(np.int64)
        interior_positions = np.arange(1, 451, dtype=np.int64)
        trace_positions = np.concatenate((
            np.asarray([0], dtype=np.int64),
            np.arange(451, 882, dtype=np.int64),
        ))
        geometry_dofs = np.arange(8, dtype=np.int32)
        geometry_coordinates = np.arange(24, dtype=np.float64)
        cells[cell_index] = {
            "maps": {
                "interior_original_rows": original_rows[interior_positions],
                "geometry_dofs": geometry_dofs,
                "actual_geometry_coordinates": geometry_coordinates,
            },
            "interior_positions": interior_positions,
            "trace_positions": trace_positions,
            "original_rows": original_rows,
            "local_dofs": local_dofs,
            "target_local_position": 0,
            "target_trace_slot": 0,
            "oriented_tensor": np.zeros((882, 882), dtype=np.complex128),
        }
        reference[(cell_index, 0)] = {
            "known_interior": np.zeros(450, dtype=np.complex128),
            "known_trace": np.zeros(432, dtype=np.complex128),
            "native_rhs_interior": np.zeros(450, dtype=np.complex128),
            "native_volume_rhs_interior": np.zeros(450, dtype=np.complex128),
        }
        arrays = {
            "oriented_test_vector": np.zeros(882, dtype=np.complex128),
            "local_dofs": local_dofs,
            "original_dofs": original_rows,
            "geometry_dof_indices": geometry_dofs,
            "geometry_coordinates": geometry_coordinates,
        }
        for component in ("curl", "material_mass"):
            terms[(component, 0, cell_index, 0)] = {
                "identity": {
                    "component": component,
                    "column": 0,
                    "cell_index": cell_index,
                    "cpp_integral_index": 0,
                    "ufcx_physical_integral_id": 17,
                    "entity_position": 0 if cell_index == 7873 else 1,
                },
                "arrays": arrays,
            }

    class _AtIndex:
        def __init__(self, value: complex) -> None:
            self.value = value

        def __getitem__(self, index: int) -> complex:
            assert index == target
            return self.value

    donor = {
        "columns": {
            0: {
                "native_volume_rhs": _AtIndex(5 + 7j),
                "native_rhs": _AtIndex(15 + 17j),
                "b_alpha_rows": np.asarray([target], dtype=np.int64),
                "b_alpha_values": np.asarray([2 + 3j], dtype=np.complex128),
            }
        }
    }

    result = checker._audit_column(
        column=0, terms=terms, cells=cells, reference=reference, donor=donor
    )

    assert result["b_alpha_binary64"] == [2.0, 3.0]
    assert result["b_volume_plus_b_alpha_binary64"] == [7.0, 10.0]
    assert result["b_full_minus_b_volume_then_b_alpha_binary64"] == [8.0, 7.0]
    assert result["b_full_minus_reassembled_volume_plus_b_alpha_binary64"] == [8.0, 7.0]

def test_decimal_cell_action_recomputes_cancellation_at_requested_precision() -> None:
    jrow = np.asarray([1.0e50, 1.0, -1.0e50], dtype=np.complex128)
    ui = np.ones(3, dtype=np.complex128)
    lrow = np.zeros(3, dtype=np.complex128)
    tc = np.ones(3, dtype=np.complex128)

    default_precision = checker._decimal_cell_action_at_precision(
        jrow, ui, lrow, tc, precision=28
    )
    decimal80 = checker._decimal_cell_action_at_precision(
        jrow, ui, lrow, tc, precision=80
    )
    decimal100 = checker._decimal_cell_action_at_precision(
        jrow, ui, lrow, tc, precision=100
    )

    assert default_precision == (checker.Decimal(0), checker.Decimal(0))
    assert decimal80 == (checker.Decimal(1), checker.Decimal(0))
    assert decimal100 == (checker.Decimal(1), checker.Decimal(0))


def test_missing_receipt_writes_complete_negative_audit_report(tmp_path: Path) -> None:
    attempt = tmp_path / "attempt"
    attempt.mkdir()

    result = checker.check_v19_saved_native_rank1(
        repo_root=tmp_path,
        output_directory=attempt,
        expected_receipt_sha256="c" * 64,
        expected_contract_sha256="a" * 64,
        expected_window_sha256="b" * 64,
    )

    report_path = attempt / "task41_p0_v19_independent_check.json"
    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert result["audit_completed"] is True
    assert result["data_complete"] is False
    assert result["native_binding_status"] == "NATIVE_REPLAY_UNBOUND"
    assert result["original_action_status"] == "FAIL"
    assert result["official_result"] is False
    assert saved["errors"] and "receipt/archive stage" in saved["errors"][0]


def test_archive_hash_failure_stays_unbound_after_diagnostics_continue(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    receipt, progress, _order = _bundle(attempt)
    contract_sha, window_sha = "a" * 64, "b" * 64
    receipt.update({
        "schema": capture.V19_RECEIPT_SCHEMA,
        "status": "COMPLETED_LOCAL_NATIVE_RANK1_CAPTURE",
        "official_result": False,
        "scientific_qualified": False,
        "full_owner_unlocked": False,
        "consumer_contract_sha256": contract_sha,
        "consumer_window_sha256": window_sha,
        "rank2_kernel_outputs": 0,
        "factorizations": 0,
        "getrs": 0,
        "full_native_action": False,
        "consumer_source_sha": "d" * 64,
        "original_donor": {"source_sha": "e" * 64, "historical_kernel_identity_status": "UNKNOWN"},
        "source_bindings": {},
        "fresh_v17_map_identity": {},
        "mpc_restriction_support": {},
    })
    receipt_path = attempt / f"task41_p0_v19_native_rank1_worker_{contract_sha}.json"
    receipt_bytes = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    receipt_path.write_bytes(receipt_bytes)
    (attempt / "task41_p0_v19_native_rank1_progress.json").write_text(
        json.dumps(progress, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )

    first = receipt["component_column_captures"][0]["terms"][0]
    archive_path = attempt / first["array_artifacts"]["raw_kernel_output"]["path"]
    with np.load(archive_path, allow_pickle=False) as archive:
        members = {name: np.asarray(archive[name]).copy() for name in archive.files}
    metadata = json.loads(str(members["term_metadata"].item()))
    members["oriented_test_vector"][0] += 2j
    metadata["capture_array_identities"]["oriented_test_vector"] = capture._array_identity(
        members["oriented_test_vector"]
    )
    members["term_metadata"] = np.asarray(json.dumps(metadata, sort_keys=True))
    with archive_path.open("wb") as stream:
        np.savez(stream, **members)

    monkeypatch.setattr(
        checker, "_load_v17_context",
        lambda **_kwargs: ({}, {}, {}, {"manifest_sha256": "f" * 64, "run_name": "fixture"}, attempt / "v17.json"),
    )
    monkeypatch.setattr(checker, "_load_local_reference_arrays", lambda **_kwargs: {})
    audited_columns: list[int] = []

    def finish_diagnostics(*, column: int, **_kwargs: Any) -> dict[str, Any]:
        audited_columns.append(column)
        return {
            "column": column,
            "native_binding_status": "BOUND_SELECTED_TARGET_AND_900_INTERNAL_ROWS",
        }

    monkeypatch.setattr(checker, "_audit_column", finish_diagnostics)
    result = checker.check_v19_saved_native_rank1(
        repo_root=tmp_path,
        output_directory=attempt,
        expected_receipt_sha256=hashlib.sha256(receipt_bytes).hexdigest(),
        expected_contract_sha256=contract_sha,
        expected_window_sha256=window_sha,
    )

    assert audited_columns == [0, 1]
    assert result["stages"]["archive_reopen"]["status"] == "UNBOUND_OR_INCOMPLETE"
    assert result["audit_completed"] is True
    assert result["data_complete"] is False
    assert result["native_binding_status"] == "NATIVE_REPLAY_UNBOUND"
    assert result["native_binding"]["status"] == "NATIVE_REPLAY_UNBOUND"


def test_complete_numeric_mismatch_is_data_complete_but_native_unbound(
    tmp_path: Path, monkeypatch: Any,
) -> None:
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    receipt, progress, _order = _bundle(attempt)
    contract_sha, window_sha = "a" * 64, "b" * 64
    receipt.update({
        "schema": capture.V19_RECEIPT_SCHEMA,
        "status": "COMPLETED_LOCAL_NATIVE_RANK1_CAPTURE",
        "official_result": False,
        "scientific_qualified": False,
        "full_owner_unlocked": False,
        "consumer_contract_sha256": contract_sha,
        "consumer_window_sha256": window_sha,
        "rank2_kernel_outputs": 0,
        "factorizations": 0,
        "getrs": 0,
        "full_native_action": False,
        "consumer_source_sha": "d" * 64,
        "original_donor": {"source_sha": "e" * 64, "historical_kernel_identity_status": "UNKNOWN"},
        "source_bindings": {},
        "fresh_v17_map_identity": {},
        "mpc_restriction_support": {},
    })
    receipt_path = attempt / f"task41_p0_v19_native_rank1_worker_{contract_sha}.json"
    receipt_bytes = json.dumps(receipt, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    receipt_path.write_bytes(receipt_bytes)
    (attempt / "task41_p0_v19_native_rank1_progress.json").write_text(
        json.dumps(progress, sort_keys=True, separators=(",", ":")), encoding="utf-8"
    )
    monkeypatch.setattr(
        checker, "_load_v17_context",
        lambda **_kwargs: ({}, {}, {}, {"manifest_sha256": "f" * 64, "run_name": "fixture"}, attempt / "v17.json"),
    )
    monkeypatch.setattr(checker, "_load_local_reference_arrays", lambda **_kwargs: {})
    monkeypatch.setattr(
        checker, "_audit_column",
        lambda *, column, **_kwargs: {
            "column": column,
            "native_binding_status": (
                "BOUND_SELECTED_TARGET_AND_900_INTERNAL_ROWS" if column == 0
                else "NATIVE_REPLAY_UNBOUND"
            ),
            "native_binding_reason": "EXACT_SELECTED_ROWS_MATCH" if column == 0 else "NUMERICAL_MISMATCH",
        },
    )

    result = checker.check_v19_saved_native_rank1(
        repo_root=tmp_path,
        output_directory=attempt,
        expected_receipt_sha256=hashlib.sha256(receipt_bytes).hexdigest(),
        expected_contract_sha256=contract_sha,
        expected_window_sha256=window_sha,
    )

    assert result["audit_completed"] is True
    assert result["data_complete"] is True
    assert result["status"] == "AUDIT_COMPLETED_DATA_COMPLETE"
    assert result["native_binding_status"] == "NATIVE_REPLAY_UNBOUND"
    assert result["native_binding_reason"] == "NUMERICAL_MISMATCH"
    assert [row["native_binding_status"] for row in result["column_diagnostics"]] == [
        "BOUND_SELECTED_TARGET_AND_900_INTERNAL_ROWS", "NATIVE_REPLAY_UNBOUND"
    ]
    assert result["column_diagnostics"][1]["native_binding_reason"] == "NUMERICAL_MISMATCH"
    assert result["original_action_status"] == "FAIL"
    assert result["scientific_qualified"] is False
