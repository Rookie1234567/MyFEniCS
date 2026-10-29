"""Independent read-only audit of the bounded V19 rank-1 capture.

The checker reopens only saved two-cell/two-column artifacts. It never
constructs FE forms, calls native kernels, builds rank-2 tensors, factors, or
solves.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
import argparse
from decimal import Decimal, localcontext
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any

import numpy as np

from src.runners import task41_p0_v19_native_rank1 as capture

V19_CHECKER_SCHEMA = "task41.p0.v19.native_rank1_independent_audit.v1"
_HEX64 = re.compile(r"[0-9a-f]{64}")
_TERM_INPUT_FIELDS = frozenset({
    "packed_coefficient_row", "packed_constants", "local_dofs",
    "original_dofs", "geometry_dof_indices", "geometry_coordinates",
})


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _read_json(path: Path, *, maximum_bytes: int, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum_bytes:
        raise ValueError(f"{label} path or size is invalid")
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} is not a JSON object")
    return value


def _term_key(component: str, column: int, cell: int, integral: int) -> str:
    return f"{component}_col{column}_cell{cell}_integral{integral:03d}"


def _expected_terms(receipt: Mapping[str, Any]) -> dict[tuple[str, int], list[tuple[int, int, int, int]]]:
    """Derive exact C++ integral/entity order from the dynamic receipt inventory."""
    inventory = receipt.get("actual_integral_inventory")
    captures = receipt.get("component_column_captures")
    if not isinstance(inventory, Mapping) or not isinstance(captures, list):
        raise ValueError("V19 receipt omits integral or term inventory")
    capture_by_key: dict[tuple[str, int], Mapping[str, Any]] = {}
    for row in captures:
        if not isinstance(row, Mapping):
            raise ValueError("V19 component/column row is malformed")
        component, column = row.get("component"), row.get("column")
        key = (str(component), column if type(column) is int else -1)
        if key in capture_by_key:
            raise ValueError("V19 receipt repeats a component/column row")
        capture_by_key[key] = row
    expected_keys = {
        (component, column)
        for component in ("curl", "material_mass")
        for column in capture.V19_COLUMNS
    }
    if set(capture_by_key) != expected_keys:
        raise ValueError("V19 component/column coverage is incomplete")

    result: dict[tuple[str, int], list[tuple[int, int, int, int]]] = {}
    for component in ("curl", "material_mass"):
        summary = inventory.get(component)
        if not isinstance(summary, Mapping):
            raise ValueError(f"V19 {component} integral inventory is missing")
        records = summary.get("kernel_inventory_from_compiled_form")
        indexes = summary.get("cpp_integral_index_order")
        physical_ids = summary.get("ufcx_physical_integral_ids")
        if not isinstance(records, list) or not records or indexes != list(range(len(records))) or not isinstance(physical_ids, list) or len(physical_ids) != len(records):
            raise ValueError(f"V19 {component} integral inventory is malformed")
        first_position = records[0].get("ufcx_kernel_position") if isinstance(records[0], Mapping) else None
        if type(first_position) is not int or first_position < 0:
            raise ValueError(f"V19 {component} UFCx cell-integral start is malformed")
        expected: list[tuple[int, int, int, int]] = []
        for integral, record in enumerate(records):
            if not isinstance(record, Mapping):
                raise ValueError(f"V19 {component} integral row is malformed")
            positions = record.get("selected_entity_positions")
            cells = record.get("selected_entity_cell_order")
            domain_count = record.get("domain_entity_count")
            physical_id = record.get("ufcx_physical_integral_id")
            valid_lists = isinstance(positions, list) and isinstance(cells, list)
            if (
                record.get("cpp_integral_index") != integral
                or type(record.get("ufcx_kernel_position")) is not int
                or record.get("ufcx_kernel_position") != first_position + integral
                or type(physical_id) is not int
                or physical_id != physical_ids[integral]
                or type(domain_count) is not int or domain_count < 0
                or not valid_lists
                or len(positions) != len(cells)
                or any(type(pos) is not int or not 0 <= pos < domain_count for pos in positions)
                or positions != sorted(positions)
                or len(set(positions)) != len(positions)
                or any(type(cell) is not int or cell not in capture.V19_SELECTED_CELLS for cell in cells)
                or len(set(cells)) != len(cells)
            ):
                raise ValueError(f"V19 {component} integral/entity order is malformed")
            expected.extend(
                (integral, int(physical_id), pos, cell)
                for pos, cell in zip(positions, cells, strict=True)
            )
        component_cells = {cell for _integral, _physical_id, _position, cell in expected}
        if component_cells != set(capture.V19_SELECTED_CELLS):
            raise ValueError(f"V19 {component} dynamic inventory does not cover both selected cells")
        if summary.get("expected_selected_kernel_invocations") != len(expected):
            raise ValueError(f"V19 {component} dynamic invocation count differs")
        for column in capture.V19_COLUMNS:
            row = capture_by_key[(component, column)]
            terms = row.get("terms")
            if (
                not isinstance(terms, list) or len(terms) != len(expected)
                or row.get("expected_selected_kernel_invocations") != len(expected)
                or row.get("completed_selected_kernel_terms") != len(expected)
            ):
                raise ValueError(f"V19 {component} column {column} term count differs")
            actual: list[tuple[int, int, int, int]] = []
            for term in terms:
                if not isinstance(term, Mapping):
                    raise ValueError("V19 receipt term row is malformed")
                identity_fields = (
                    "cpp_integral_index", "ufcx_physical_integral_id", "entity_position", "cell_index"
                )
                if any(type(term.get(name)) is not int for name in identity_fields):
                    raise ValueError("V19 receipt term order fields must be integer identities")
                actual.append((
                    term.get("cpp_integral_index"),
                    term.get("ufcx_physical_integral_id"),
                    term.get("entity_position"),
                    term.get("cell_index"),
                ))
                identity = term.get("term_identity")
                if (
                    not isinstance(identity, Mapping)
                    or identity.get("component") != component
                    or identity.get("column") != column
                    or any(identity.get(name) != term.get(name) for name in (
                        "cell_index", "cpp_integral_index", "ufcx_physical_integral_id", "entity_position"
                    ))
                ):
                    raise ValueError("V19 receipt term identity differs from the inventory row")
            if actual != expected:
                raise ValueError(f"V19 {component} column {column} is not in integral/entity order")
            result[(component, column)] = expected
    return result


def _read_progress(output_directory: Path, receipt: Mapping[str, Any]) -> dict[str, Any]:
    progress = _read_json(
        output_directory / "task41_p0_v19_native_rank1_progress.json",
        maximum_bytes=capture.V19_MAX_NEW_EVIDENCE_BYTES,
        label="V19 progress checkpoint",
    )
    identity = receipt.get("run_identity")
    if (
        progress.get("schema") != capture.V19_PROGRESS_SCHEMA
        or not isinstance(identity, Mapping)
        or progress.get("run_identity") != dict(identity)
        or progress.get("run_identity_sha256") != receipt.get("run_identity_sha256")
        or progress.get("run_identity_sha256") != _json_hash(identity)
        or not isinstance(progress.get("terms"), Mapping)
    ):
        raise ValueError("V19 progress checkpoint identity differs from the receipt")
    return progress


def _validate_layout(field: str, values: np.ndarray, local_size: int) -> None:
    dtypes = {
        "raw_kernel_output": np.dtype(np.complex128),
        "oriented_test_vector": np.dtype(np.complex128),
        "packed_coefficient_row": np.dtype(np.complex128),
        "packed_constants": np.dtype(np.complex128),
        "local_dofs": np.dtype(np.int32),
        "original_dofs": np.dtype(np.int64),
        "geometry_dof_indices": np.dtype(np.int32),
        "geometry_coordinates": np.dtype(np.float64),
    }
    if values.dtype != dtypes[field]:
        raise ValueError(f"V19 term member {field} has the wrong dtype")
    if field in {"raw_kernel_output", "oriented_test_vector", "local_dofs", "original_dofs"} and values.shape != (local_size,):
        raise ValueError(f"V19 term member {field} has the wrong local shape")
    if field == "geometry_dof_indices" and values.shape != (8,):
        raise ValueError("V19 geometry dof index shape differs")
    if field == "geometry_coordinates" and values.shape != (24,):
        raise ValueError("V19 geometry coordinate shape differs")
    if field in {"packed_coefficient_row", "packed_constants"} and values.ndim != 1:
        raise ValueError(f"V19 term member {field} must be one-dimensional")


def _load_term_archives(
    receipt: Mapping[str, Any], progress: Mapping[str, Any], output_directory: Path,
    expected_order: Mapping[tuple[str, int], Sequence[tuple[int, int, int, int]]],
) -> tuple[dict[tuple[str, int, int, int], dict[str, Any]], list[str]]:
    loaded: dict[tuple[str, int, int, int], dict[str, Any]] = {}
    errors: list[str] = []
    for capture_row in receipt["component_column_captures"]:
        component, column = str(capture_row["component"]), int(capture_row["column"])
        for record in capture_row["terms"]:
            cell, integral = int(record["cell_index"]), int(record["cpp_integral_index"])
            key = (component, column, cell, integral)
            digest = record.get("archive_sha256")
            if not isinstance(digest, str) or _HEX64.fullmatch(digest) is None:
                errors.append(f"{key}: receipt has no valid whole-archive SHA-256")
                continue
            if record.get("archive_binding_status") == "ORPHAN_ATOMIC_ARCHIVE_INTERNAL_IDENTITY_ONLY":
                errors.append(f"{key}: orphan archive is retained but not checkpoint-bound")
            elif record.get("archive_binding_status") != "CHECKPOINT_SHA256_VERIFIED":
                errors.append(f"{key}: archive is not checkpoint-SHA verified")
            if record.get("capture_status") != "CAPTURED_FINITE":
                errors.append(f"{key}: capture status is not finite-complete")
            artifacts = record.get("array_artifacts")
            if not isinstance(artifacts, Mapping) or set(artifacts) != set(capture._TERM_ARRAY_FIELDS):
                errors.append(f"{key}: array member reference set differs")
                continue
            ref0 = artifacts[capture._TERM_ARRAY_FIELDS[0]]
            raw_path = ref0.get("path") if isinstance(ref0, Mapping) else None
            if not isinstance(raw_path, str):
                errors.append(f"{key}: archive reference path is malformed")
                continue
            path = output_directory / raw_path
            expected_name = _term_key(component, column, cell, integral) + ".npz"
            try:
                resolved = path.resolve(strict=True)
                if (
                    path.is_symlink() or not resolved.is_relative_to(output_directory)
                    or resolved.name != expected_name or not resolved.is_file()
                ):
                    raise ValueError("archive path escaped or differs from its bounded name")
                size = int(resolved.stat().st_size)
                if _sha256(resolved) != digest:
                    raise ValueError("archive bytes differ from the receipt SHA-256")
                state_key = _term_key(component, column, cell, integral)
                saved_state = progress["terms"].get(state_key)
                if not isinstance(saved_state, Mapping) or (
                    saved_state.get("archive_sha256") != digest
                    or saved_state.get("term_identity") != record.get("term_identity")
                    or saved_state.get("archive_binding_status") != record.get("archive_binding_status")
                    or saved_state.get("capture_status") != record.get("capture_status")
                    or saved_state.get("array_artifacts") != dict(artifacts)
                ):
                    raise ValueError("receipt row differs from the progress checkpoint")
                with np.load(resolved, allow_pickle=False) as archive:
                    if set(archive.files) != {"term_metadata", *capture._TERM_ARRAY_FIELDS}:
                        raise ValueError("NPZ member set differs from schema")
                    metadata = json.loads(str(archive["term_metadata"].item()))
                    identity = record.get("term_identity")
                    if not isinstance(identity, Mapping) or (
                        metadata.get("schema") != capture.V19_TERM_ARCHIVE_SCHEMA
                        or metadata.get("term_identity") != identity
                    ):
                        raise ValueError("NPZ embedded identity differs from receipt")
                    unsigned = dict(identity)
                    if unsigned.pop("identity_sha256", None) != _json_hash(unsigned):
                        raise ValueError("NPZ term identity checksum is invalid")
                    capture_ids = metadata.get("capture_array_identities")
                    input_ids = identity.get("array_identities")
                    if (
                        not isinstance(capture_ids, Mapping)
                        or set(capture_ids) != set(capture._TERM_ARRAY_FIELDS)
                        or not isinstance(input_ids, Mapping)
                        or set(input_ids) != _TERM_INPUT_FIELDS
                    ):
                        raise ValueError("NPZ per-member identity inventory is incomplete")
                    arrays: dict[str, np.ndarray] = {}
                    local_size = -1
                    for field in capture._TERM_ARRAY_FIELDS:
                        values = np.asarray(archive[field])
                        actual = capture._array_identity(values)
                        if capture_ids.get(field) != actual:
                            raise ValueError(f"member {field} differs from embedded hash")
                        if field in _TERM_INPUT_FIELDS and input_ids.get(field) != actual:
                            raise ValueError(f"member {field} differs from term_identity input/map identity")
                        ref = artifacts[field]
                        if not isinstance(ref, Mapping) or (
                            ref.get("path") != raw_path or ref.get("member") != field
                            or ref.get("sha256") != digest or ref.get("bytes") != size
                            or ref.get("dtype") != values.dtype.str or ref.get("shape") != list(values.shape)
                        ):
                            raise ValueError(f"receipt member reference {field} differs from archive")
                        if field == "local_dofs":
                            local_size = int(values.size)
                        arrays[field] = np.array(values, copy=True)
                    for field, values in arrays.items():
                        _validate_layout(field, values, local_size)
                    for field in ("raw_kernel_output", "oriented_test_vector"):
                        if not np.isfinite(arrays[field]).all():
                            raise ValueError(f"finite capture member {field} has non-finite values")
                    if arrays["original_dofs"].size != np.unique(arrays["original_dofs"]).size:
                        raise ValueError("cell term original dof map repeats rows")
                    loaded[key] = {"identity": dict(identity), "arrays": arrays, "archive_sha256": digest}
            except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
                errors.append(f"{key}: {type(exc).__name__}: {exc}")
    expected_keys = {
        (component, column, cell, integral)
        for (component, column), rows in expected_order.items()
        for integral, _physical, _position, cell in rows
    }
    if set(loaded) != expected_keys:
        errors.append("archive set does not close the dynamic integral/entity inventory")
    state_names = {_term_key(*key) for key in expected_keys}
    if set(progress.get("terms", {})) != state_names:
        errors.append("progress contains missing or extra term archives")
    return loaded, errors


def _load_v17_context(
    *, root: Path, receipt: Mapping[str, Any]
) -> tuple[dict[str, Any], dict[int, dict[str, Any]], dict[str, Any], dict[str, Any], Path]:
    """Reopen pinned V17 maps/tensors and V3 donor arrays without FE work."""
    from src.runners.task41_p0_checker import (
        TASK41_P0_B0_V17_SELECTED_CELLS,
        TASK41_P0_B0_V17_SELECTED_ORIGINAL_ROW,
        TASK41_P0_B0_V17_SELECTED_ROW,
        TASK41_P0_B0_V3_DONOR_MANIFEST_SHA256,
        load_task41_p0_b0_v17_selected_cell_metadata,
        load_task41_p0_b0_v17_v3_selected_donor,
    )

    relative, report_sha = capture.SOURCE_BINDINGS["v17_report"]
    report_path = root / relative
    bindings = receipt.get("source_bindings")
    if (
        report_path.is_symlink() or not report_path.is_file()
        or _sha256(report_path) != report_sha
        or not isinstance(bindings, Mapping)
        or bindings.get("v17_report_sha256") != report_sha
        or Path(str(bindings.get("v17_report_path", ""))).resolve() != report_path.resolve()
    ):
        raise ValueError("pinned V17 report path or SHA-256 differs")
    report = _read_json(report_path, maximum_bytes=8 * 1024**2, label="pinned V17 report")
    callback = report.get("selected_two_cell_candidate_callback")
    if (
        report.get("schema") != "task41.p0.b0.v17.selected_two_cell_worker_receipt.v1"
        or report.get("status") != "COMPLETED_LOCAL_SELECTED_TWO_CELL_REPLAY"
        or report.get("official_result") is not False
        or not isinstance(callback, Mapping)
        or callback.get("scope", {}).get("selected_active_row") != TASK41_P0_B0_V17_SELECTED_ROW
        or callback.get("scope", {}).get("selected_original_row") != TASK41_P0_B0_V17_SELECTED_ORIGINAL_ROW
        or callback.get("scope", {}).get("cell_order") != list(TASK41_P0_B0_V17_SELECTED_CELLS)
        or callback.get("scope", {}).get("columns") != [0, 1]
    ):
        raise ValueError("pinned V17 callback scope differs")
    metadata = load_task41_p0_b0_v17_selected_cell_metadata(repo_root=root)
    donor = load_task41_p0_b0_v17_v3_selected_donor(repo_root=root)
    if (
        donor.get("manifest_sha256") != TASK41_P0_B0_V3_DONOR_MANIFEST_SHA256
        or donor.get("manifest_sha256") != receipt.get("v3_donor_manifest_sha256")
        or donor.get("source_index_sha256") != receipt.get("v3_vector_index_sha256")
        or donor.get("run_name") != capture.V19_ORIGINAL_DONOR_RUN
        or receipt.get("original_donor", {}).get("source_sha") != capture.V19_ORIGINAL_PRODUCER_SOURCE_SHA
        or receipt.get("consumer_source_sha") == capture.V19_ORIGINAL_PRODUCER_SOURCE_SHA
    ):
        raise ValueError("V19 original donor and consumer source identities are not distinct/bound")

    receipt_maps = receipt.get("fresh_v17_map_identity")
    callback_cells = callback.get("cells")
    if not isinstance(receipt_maps, Mapping) or not isinstance(callback_cells, list):
        raise ValueError("V19 receipt omits pinned selected-cell maps")
    meta_by_cell = {int(row["cell_id"]): row for row in metadata["cells"]}
    cells: dict[int, dict[str, Any]] = {}
    for saved_cell in callback_cells:
        cell = int(saved_cell["cell_index"])
        if cell not in TASK41_P0_B0_V17_SELECTED_CELLS:
            raise ValueError("V19 V17 callback contains an out-of-scope cell")
        records = saved_cell.get("fresh_map_artifacts")
        receipt_row = receipt_maps.get(str(cell))
        if (
            not isinstance(records, Mapping)
            or not isinstance(receipt_row, Mapping)
            or receipt_row.get("v17_map_artifacts") != dict(records)
        ):
            raise ValueError(f"V19 cell {cell} map refs differ between receipt and V17 report")
        metadata_cell = meta_by_cell.get(cell)
        saved_tag = saved_cell.get("cell_tag")
        saved_permutation = saved_cell.get("cell_permutation")
        _validate_saved_v17_cell_direction(
            cell=cell,
            saved_cell=saved_cell,
            metadata_cell=metadata_cell if isinstance(metadata_cell, Mapping) else None,
            receipt_row=receipt_row,
        )
        map_names = (
            "geometry_dofs", "actual_geometry_coordinates", "local_dofs", "original_rows",
            "interior_positions", "trace_positions", "interior_original_rows",
            "trace_original_rows", "active_ids", "trace_expansion_data",
            "trace_expansion_indices", "trace_expansion_indptr",
            "selected_local_trace_rows", "selected_trace_coefficients",
        )
        maps = {
            name: capture._load_map_array(
                root=root, report_path=report_path, record=records[name],
                label=f"V19 cell {cell} {name}",
            )
            for name in map_names
        }
        I = np.asarray(maps["interior_positions"], dtype=np.int64)
        T = np.asarray(maps["trace_positions"], dtype=np.int64)
        original = np.asarray(maps["original_rows"], dtype=np.int64)
        local_dofs = np.asarray(maps["local_dofs"], dtype=np.int32)
        local_position = int(meta_by_cell[cell]["local_position"])
        if (
            I.shape != (450,) or T.shape != (432,) or original.shape != (882,)
            or local_dofs.shape != (882,) or np.intersect1d(I, T).size
            or not np.array_equal(np.sort(np.r_[I, T]), np.arange(882))
            or not np.array_equal(maps["interior_original_rows"], original[I])
            or not np.array_equal(maps["trace_original_rows"], original[T])
            or not 0 <= local_position < 882
            or original[local_position] != TASK41_P0_B0_V17_SELECTED_ORIGINAL_ROW
            or local_dofs[local_position] != original[local_position]
            or not np.array_equal(maps["active_ids"], meta_by_cell[cell]["active_ids"])
        ):
            raise ValueError(f"V19 cell {cell} original/I/T maps do not close")
        trace_slots = np.flatnonzero(T == local_position)
        active_slots = np.flatnonzero(np.asarray(maps["active_ids"]) == TASK41_P0_B0_V17_SELECTED_ROW)
        data = np.asarray(maps["trace_expansion_data"], dtype=np.complex128)
        indices = np.asarray(maps["trace_expansion_indices"], dtype=np.int32)
        indptr = np.asarray(maps["trace_expansion_indptr"], dtype=np.int32)
        if (
            trace_slots.shape != (1,) or active_slots.shape != (1,)
            or data.ndim != 1 or indices.shape != data.shape
            or indptr.shape != (T.size + 1,) or indptr[0] != 0
            or indptr[-1] != data.size or np.any(np.diff(indptr) < 0)
            or np.any(indices < 0) or np.any(indices >= len(maps["active_ids"]))
            or not np.isfinite(data).all()
        ):
            raise ValueError(f"V19 cell {cell} trace expansion is malformed")
        q = np.zeros(T.size, dtype=np.complex128)
        for row in range(T.size):
            start, stop = int(indptr[row]), int(indptr[row + 1])
            columns = indices[start:stop]
            if columns.size != np.unique(columns).size:
                raise ValueError(f"V19 cell {cell} trace expansion has duplicate columns")
            hit = np.flatnonzero(columns == int(active_slots[0]))
            if hit.size:
                q[row] = data[start + int(hit[0])]
        selected_trace_slot = int(trace_slots[0])
        unit_q = np.zeros(T.size, dtype=np.complex128)
        unit_q[selected_trace_slot] = 1.0 + 0.0j
        if (
            not np.array_equal(q, unit_q)
            or maps["selected_local_trace_rows"].tolist() != [selected_trace_slot]
            or not np.array_equal(maps["selected_trace_coefficients"], np.asarray([1.0 + 0.0j]))
        ):
            raise ValueError(f"V19 cell {cell} target row has a nontrivial MPC pullback")
        candidate_refs = saved_cell.get("candidate_artifacts")
        if not isinstance(candidate_refs, Mapping) or not isinstance(candidate_refs.get("oriented_tensor"), Mapping):
            raise ValueError(f"V19 cell {cell} omits the old oriented K/G/J/L source")
        tensor = capture._load_map_array(
            root=root, report_path=report_path, record=candidate_refs["oriented_tensor"],
            label=f"V19 cell {cell} old oriented tensor",
        )
        if tensor.shape != (882, 882) or tensor.dtype != np.dtype(np.complex128):
            raise ValueError(f"V19 cell {cell} old K/G/J/L tensor layout differs")
        cells[cell] = {
            "maps": maps, "interior_positions": I, "trace_positions": T,
            "original_rows": original, "local_dofs": local_dofs,
            "target_local_position": local_position,
            "target_trace_slot": selected_trace_slot, "q": q,
            "oriented_tensor": np.asarray(tensor),
        }
    if set(cells) != set(TASK41_P0_B0_V17_SELECTED_CELLS):
        raise ValueError("V19 map/tensor coverage does not contain both selected cells")
    internal = [
        int(row) for cell in TASK41_P0_B0_V17_SELECTED_CELLS
        for row in cells[cell]["maps"]["interior_original_rows"]
    ]
    if len(set(internal)) != 900 or TASK41_P0_B0_V17_SELECTED_ORIGINAL_ROW in set(internal):
        raise ValueError("V19 internal rows are not two disjoint 450-row cell interiors")
    support = receipt.get("mpc_restriction_support")
    if not isinstance(support, Mapping) or (
        support.get("selected_rows_touch_any_mpc_slave_or_master") is not False
        or support.get("selected_rows_touch_mpc_indices") != []
    ):
        raise ValueError("V19 receipt does not retain the no-MPC support result")
    return dict(callback), cells, metadata, donor, report_path


def _validate_saved_v17_cell_direction(
    *, cell: int, saved_cell: Mapping[str, Any],
    metadata_cell: Mapping[str, Any] | None, receipt_row: Mapping[str, Any],
) -> None:
    saved_tag = saved_cell.get("cell_tag")
    saved_permutation = saved_cell.get("cell_permutation")
    if (
        not isinstance(metadata_cell, Mapping)
        or type(saved_tag) is not int
        or type(saved_permutation) is not int
        or saved_tag != metadata_cell.get("cell_tag")
        or saved_permutation != metadata_cell.get("cell_permutation")
        or receipt_row.get("tag") != saved_tag
        or receipt_row.get("permutation") != saved_permutation
        or receipt_row.get("cell_index") != cell
    ):
        raise ValueError(
            f"V19 cell {cell} receipt tag/permutation differs from the saved V17 identity"
        )


def _dcomplex(value: Any) -> tuple[Decimal, Decimal]:
    scalar = complex(np.complex128(value))
    return Decimal.from_float(float(scalar.real)), Decimal.from_float(float(scalar.imag))


def _dadd(a: tuple[Decimal, Decimal], b: tuple[Decimal, Decimal]) -> tuple[Decimal, Decimal]:
    return a[0] + b[0], a[1] + b[1]


def _dsub(a: tuple[Decimal, Decimal], b: tuple[Decimal, Decimal]) -> tuple[Decimal, Decimal]:
    return a[0] - b[0], a[1] - b[1]


def _dmul(a: tuple[Decimal, Decimal], b: tuple[Decimal, Decimal]) -> tuple[Decimal, Decimal]:
    return a[0] * b[0] - a[1] * b[1], a[0] * b[1] + a[1] * b[0]


def _ddot(a: np.ndarray, b: np.ndarray) -> tuple[Decimal, Decimal]:
    if a.shape != b.shape or a.ndim != 1:
        raise ValueError("V19 Decimal dot operands differ")
    total = (Decimal(0), Decimal(0))
    for left, right in zip(a, b, strict=True):
        total = _dadd(total, _dmul(_dcomplex(left), _dcomplex(right)))
    return total


def _decimal_cell_action_at_precision(
    jrow: np.ndarray, ui: np.ndarray, lrow: np.ndarray, tc: np.ndarray, *, precision: int
) -> tuple[Decimal, Decimal]:
    with localcontext() as context:
        context.prec = precision
        return _dadd(_ddot(jrow, ui), _ddot(lrow, tc))


def _dpair(value: tuple[Decimal, Decimal]) -> list[str]:
    return [str(value[0]), str(value[1])]


def _vector_summary(values: np.ndarray) -> dict[str, Any]:
    array = np.asarray(values, dtype=np.complex128)
    return {
        "rows": int(array.size),
        "l2_norm": float(np.linalg.norm(array)),
        "max_abs": float(np.max(np.abs(array))) if array.size else 0.0,
        "bitwise_zero": bool(not np.any(array)),
    }


def _bitwise_equal(left: np.ndarray, right: np.ndarray) -> bool:
    a = np.ascontiguousarray(np.asarray(left, dtype=np.complex128))
    b = np.ascontiguousarray(np.asarray(right, dtype=np.complex128))
    return a.shape == b.shape and a.tobytes() == b.tobytes()


def _load_local_reference_arrays(
    *, root: Path, report_path: Path, callback: Mapping[str, Any],
    cells: Mapping[int, Mapping[str, Any]], donor: Mapping[str, Any],
) -> dict[tuple[int, int], dict[str, np.ndarray]]:
    donor_columns, callback_columns = donor.get("columns"), callback.get("columns")
    if not isinstance(donor_columns, list) or len(donor_columns) != 2 or not isinstance(callback_columns, list):
        raise ValueError("V19 original donor columns are incomplete")
    result: dict[tuple[int, int], dict[str, np.ndarray]] = {}
    for column in capture.V19_COLUMNS:
        donor_column = donor_columns[column]
        if donor_column.get("column") != column:
            raise ValueError("V19 donor column order differs")
        known = np.asarray(donor_column["known_field"])
        native = np.asarray(donor_column["native_rhs"])
        volume = np.asarray(donor_column["native_volume_rhs"])
        active = np.asarray(donor_column["active_original_rows"])
        if (
            known.shape != (18_501_024,) or native.shape != known.shape or volume.shape != known.shape
            or known.dtype != np.dtype(np.complex128) or native.dtype != np.dtype(np.complex128)
            or volume.dtype != np.dtype(np.complex128) or active.shape != (5_688_000,)
            or active.dtype != np.dtype(np.int64) or int(active[1_622_464]) != 5_218_672
        ):
            raise ValueError(f"V19 column {column} donor vector layout differs")
        row = callback_columns[column]
        if row.get("column") != column or [item.get("cell_index") for item in row.get("cells", [])] != list(capture.V19_SELECTED_CELLS):
            raise ValueError(f"V19 column {column} saved cell order differs")
        for cell in capture.V19_SELECTED_CELLS:
            local = next(item for item in row["cells"] if item.get("cell_index") == cell)
            maps = cells[cell]["maps"]
            irows = np.asarray(maps["interior_original_rows"], dtype=np.int64)
            trows = np.asarray(maps["trace_original_rows"], dtype=np.int64)
            ui = np.asarray(known[irows], dtype=np.complex128)
            tc = np.asarray(known[trows], dtype=np.complex128)
            bvol = np.asarray(volume[irows], dtype=np.complex128)
            bfull = np.asarray(native[irows], dtype=np.complex128)
            checks = {
                "known_interior_local_artifact": ui,
                "known_trace_local_artifact": tc,
                "native_volume_rhs_interior_artifact": bvol,
                "native_rhs_interior_artifact": bfull,
            }
            for name, expected in checks.items():
                record = local.get(name)
                if not isinstance(record, Mapping):
                    raise ValueError(f"V19 cell {cell} column {column} omits {name}")
                saved = capture._load_map_array(
                    root=root, report_path=report_path, record=record,
                    label=f"V19 cell {cell} column {column} {name}",
                )
                if saved.dtype != np.dtype(np.complex128) or not np.array_equal(saved, expected):
                    raise ValueError(f"V19 cell {cell} column {column} {name} differs from V3 donor")
            result[(cell, column)] = {
                "known_interior": ui, "known_trace": tc,
                "native_rhs_interior": bfull, "native_volume_rhs_interior": bvol,
                "known_field": known, "native_rhs": native, "native_volume_rhs": volume,
                "b_alpha_rows": np.asarray(donor_column["b_alpha_rows"]),
                "b_alpha_values": np.asarray(donor_column["b_alpha_values"]),
            }
    return result


def _scatter_components(
    *, terms: Mapping[tuple[str, int, int, int], Mapping[str, Any]],
    cells: Mapping[int, Mapping[str, Any]], column: int,
) -> tuple[dict[str, dict[int, np.complex128]], list[dict[str, Any]]]:
    """Apply the saved row maps in kernel/entity order, then split axpy order."""
    covered = {
        int(row) for cell in capture.V19_SELECTED_CELLS
        for row in cells[cell]["maps"]["interior_original_rows"]
    }
    covered.add(5_218_672)
    component_rows: dict[str, dict[int, np.complex128]] = {}
    signed: list[dict[str, Any]] = []
    for component in ("curl", "material_mass"):
        accumulator = {row: np.complex128(0.0 + 0.0j) for row in covered}
        ordered = sorted(
            (
                (key, term) for key, term in terms.items()
                if key[0] == component and key[1] == column
            ),
            key=lambda item: (
                int(item[1]["identity"]["cpp_integral_index"]),
                int(item[1]["identity"]["entity_position"]),
            ),
        )
        for key, term in ordered:
            arr = term["arrays"]
            cell = int(key[2])
            cell_data = cells[cell]
            maps = cell_data["maps"]
            if (
                not np.array_equal(arr["local_dofs"], cell_data["local_dofs"])
                or not np.array_equal(arr["original_dofs"], cell_data["original_rows"])
                or not np.array_equal(arr["geometry_dof_indices"], maps["geometry_dofs"])
                or not np.array_equal(
                    arr["geometry_coordinates"],
                    np.asarray(maps["actual_geometry_coordinates"]).reshape(-1),
                )
            ):
                raise ValueError(f"V19 {component} term {key} local/geometry maps differ from V17")
            vector = arr["oriented_test_vector"]
            for local_index, original_row in enumerate(arr["original_dofs"]):
                row = int(original_row)
                if row in covered:
                    accumulator[row] = np.complex128(accumulator[row] + vector[local_index])
            local_position = int(cell_data["target_local_position"])
            value = np.complex128(vector[local_position])
            signed.append({
                "component": component,
                "column": column,
                "cell_index": cell,
                "cpp_integral_index": int(term["identity"]["cpp_integral_index"]),
                "ufcx_physical_integral_id": int(term["identity"]["ufcx_physical_integral_id"]),
                "entity_position": int(term["identity"]["entity_position"]),
                "target_signed_contribution_binary64": [float(value.real), float(value.imag)],
                "target_original_row": int(arr["original_dofs"][local_position]),
            })
        component_rows[component] = accumulator
    return component_rows, signed


def _audit_column(
    *, column: int, terms: Mapping[tuple[str, int, int, int], Mapping[str, Any]],
    cells: Mapping[int, Mapping[str, Any]], reference: Mapping[tuple[int, int], Mapping[str, np.ndarray]],
    donor: Mapping[str, Any],
) -> dict[str, Any]:
    component_rows, signed = _scatter_components(terms=terms, cells=cells, column=column)
    internal_rows: list[int] = []
    cell_reports: list[dict[str, Any]] = []
    A_operands: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
    Q_parts: list[tuple[Decimal, Decimal]] = []
    for cell in capture.V19_SELECTED_CELLS:
        data = cells[cell]
        maps = data["maps"]
        I, T = data["interior_positions"], data["trace_positions"]
        rows_i = np.asarray(maps["interior_original_rows"], dtype=np.int64)
        internal_rows.extend(int(row) for row in rows_i)
        tensor = data["oriented_tensor"]
        K = np.asarray(tensor[np.ix_(I, I)], dtype=np.complex128)
        G = np.asarray(tensor[np.ix_(I, T)], dtype=np.complex128)
        J = np.asarray(tensor[np.ix_(T, I)], dtype=np.complex128)
        L = np.asarray(tensor[np.ix_(T, T)], dtype=np.complex128)
        ui = reference[(cell, column)]["known_interior"]
        tc = reference[(cell, column)]["known_trace"]
        old_internal = np.asarray(K @ ui + G @ tc, dtype=np.complex128)
        target_trace = int(data["target_trace_slot"])
        old_target = np.complex128((J @ ui + L @ tc)[target_trace])
        A_operands.append((J[target_trace], ui, L[target_trace], tc))
        new_internal = np.asarray([
            np.complex128(component_rows["curl"][int(row)] + component_rows["material_mass"][int(row)])
            for row in rows_i
        ], dtype=np.complex128)
        bvol = reference[(cell, column)]["native_volume_rhs_interior"]
        bfull = reference[(cell, column)]["native_rhs_interior"]
        cell_reports.append({
            "cell_index": cell,
            "internal_rows": 450,
            "K_u_plus_G_t": _vector_summary(old_internal),
            "new_rank1_internal_scatter": _vector_summary(new_internal),
            "old_native_volume_rhs_internal": _vector_summary(bvol),
            "old_native_full_rhs_internal": _vector_summary(bfull),
            "K_G_minus_volume_rhs": _vector_summary(old_internal - bvol),
            "rank1_minus_volume_rhs": _vector_summary(new_internal - bvol),
            "rank1_minus_K_G": _vector_summary(new_internal - old_internal),
            "rank1_internal_bitwise_matches_volume_rhs": _bitwise_equal(new_internal, bvol),
            "matrix_internal_bitwise_matches_volume_rhs": _bitwise_equal(old_internal, bvol),
            "A_cell_binary64": [float(old_target.real), float(old_target.imag)],
        })
    if len(set(internal_rows)) != 900 or 5_218_672 in set(internal_rows):
        raise ValueError("V19 internal row support is incomplete or overlapping")

    for term_row in signed:
        key = (
            str(term_row["component"]), column, int(term_row["cell_index"]),
            int(term_row["cpp_integral_index"]),
        )
        term = terms[key]
        position = int(cells[int(term_row["cell_index"])]["target_local_position"])
        decimal_value = _dcomplex(term["arrays"]["oriented_test_vector"][position])
        Q_parts.append(decimal_value)
        term_row["target_signed_contribution_decimal80"] = [str(decimal_value[0]), str(decimal_value[1])]
    Q_parts_by_component = {
        component: [
            _dcomplex(
                terms[(component, column, int(term_row["cell_index"]), int(term_row["cpp_integral_index"]))]
                ["arrays"]["oriented_test_vector"]
                [int(cells[int(term_row["cell_index"])]["target_local_position"])]
            )
            for term_row in signed if term_row["component"] == component
        ]
        for component in ("curl", "material_mass")
    }

    target_row = 5_218_672
    curl_value = component_rows["curl"][target_row]
    mass_value = component_rows["material_mass"][target_row]
    b_replay = np.complex128(curl_value + mass_value)
    donor_column = donor["columns"][column]
    b_saved = np.complex128(donor_column["native_volume_rhs"][target_row])
    b_full = np.complex128(donor_column["native_rhs"][target_row])
    alpha_rows = np.asarray(donor_column["b_alpha_rows"])
    alpha_values = np.asarray(donor_column["b_alpha_values"])
    if alpha_rows.ndim != 1 or alpha_values.shape != alpha_rows.shape:
        raise ValueError(f"V19 column {column} B-alpha sparse arrays differ")
    alpha_hits = np.flatnonzero(alpha_rows == target_row)
    if alpha_hits.size > 1:
        raise ValueError(f"V19 column {column} repeats the B-alpha target row")
    b_alpha = np.complex128(alpha_values[int(alpha_hits[0])]) if alpha_hits.size else np.complex128(0j)
    b_full_minus_volume_then_alpha = np.complex128(np.complex128(b_full - b_saved) - b_alpha)
    volume_plus_alpha = np.complex128(b_saved + b_alpha)
    b_full_minus_reassembled = np.complex128(b_full - volume_plus_alpha)
    decimal: dict[str, Any] = {}
    for precision in (80, 100):
        with localcontext() as context:
            context.prec = precision
            A = (Decimal(0), Decimal(0))
            for cell_index, (jrow, ui, lrow, tc) in zip(
                capture.V19_SELECTED_CELLS, A_operands, strict=True
            ):
                # Re-evaluate products and reductions from the original saved
                # binary64 operands under this precision. Do not promote a
                # default-context result and label it as an 80/100 digit sum.
                A_cell = _decimal_cell_action_at_precision(
                    jrow, ui, lrow, tc, precision=precision
                )
                A = _dadd(A, A_cell)
                cell_reports[capture.V19_SELECTED_CELLS.index(cell_index)][
                    f"A_cell_decimal{precision}"
                ] = [str(A_cell[0]), str(A_cell[1])]
            Q = (Decimal(0), Decimal(0))
            for value in Q_parts:
                Q = _dadd(Q, value)
            component_term_sums: dict[str, tuple[Decimal, Decimal]] = {}
            component_scatter_values = {
                "curl": _dcomplex(curl_value),
                "material_mass": _dcomplex(mass_value),
            }
            component_scatter_residuals: dict[str, tuple[Decimal, Decimal]] = {}
            for component in ("curl", "material_mass"):
                component_sum = (Decimal(0), Decimal(0))
                for value in Q_parts_by_component[component]:
                    component_sum = _dadd(component_sum, value)
                component_term_sums[component] = component_sum
                component_scatter_residuals[component] = _dsub(
                    component_sum, component_scatter_values[component]
                )
            replay, saved = _dcomplex(b_replay), _dcomplex(b_saved)
            local_rank1 = _dsub(A, Q)
            assembly = _dsub(Q, replay)
            binding = _dsub(replay, saved)
            total = _dsub(A, saved)
            closure = _dsub(_dadd(_dadd(local_rank1, assembly), binding), total)
            scatter_sum = _dadd(
                component_scatter_values["curl"], component_scatter_values["material_mass"]
            )
            component_merge_rounding = _dsub(scatter_sum, replay)
            component_to_replay = _dadd(
                _dadd(
                    component_scatter_residuals["curl"],
                    component_scatter_residuals["material_mass"],
                ),
                component_merge_rounding,
            )
            q_replay = _dsub(Q, replay)
            q_replay_closure = _dsub(component_to_replay, q_replay)
            full, volume, alpha = _dcomplex(b_full), _dcomplex(b_saved), _dcomplex(b_alpha)
            decimal[str(precision)] = {
                "precision_digits": precision,
                "inputs_are_exact_decimal_encodings_of_binary64": True,
                "A": [str(A[0]), str(A[1])],
                "Q": [str(Q[0]), str(Q[1])],
                "b_replay_binary64": [str(replay[0]), str(replay[1])],
                "b_saved_native_volume_binary64": [str(saved[0]), str(saved[1])],
                "A_minus_Q_local_rank1": [str(local_rank1[0]), str(local_rank1[1])],
                "Q_minus_b_replay_native_assembly": [str(assembly[0]), str(assembly[1])],
                "Q_minus_b_replay_signed_segments": {
                    "curl_exact_term_sum_minus_original_order_scatter": _dpair(
                        component_scatter_residuals["curl"]
                    ),
                    "material_mass_exact_term_sum_minus_original_order_scatter": _dpair(
                        component_scatter_residuals["material_mass"]
                    ),
                    "original_order_component_sum_minus_final_curl_plus_mass": _dpair(
                        component_merge_rounding
                    ),
                    "segment_sum_minus_Q_minus_b_replay_closure": _dpair(q_replay_closure),
                },
                "exact_component_term_sums": {
                    name: _dpair(value) for name, value in component_term_sums.items()
                },
                "original_order_component_scatter_binary64": {
                    name: _dpair(value) for name, value in component_scatter_values.items()
                },
                "b_replay_minus_b_saved_binding": [str(binding[0]), str(binding[1])],
                "A_minus_b_saved": [str(total[0]), str(total[1])],
                "three_segment_signed_closure_residual": [str(closure[0]), str(closure[1])],
                "b_full_minus_b_volume_then_b_alpha_binary64": _dpair(
                    _dsub(_dsub(full, volume), alpha)
                ),
                "b_full_minus_reassembled_volume_plus_b_alpha_binary64": _dpair(
                    _dsub(full, _dadd(volume, alpha))
                ),
            }
    target_bound = _bitwise_equal(np.asarray([b_replay]), np.asarray([b_saved]))
    internal_bound = all(row["rank1_internal_bitwise_matches_volume_rhs"] for row in cell_reports)
    return {
        "column": column,
        "selected_original_row": target_row,
        "component_order": ["curl", "material_mass"],
        "combine_semantics": "curl_result.axpy(1, mass_result)",
        "component_target_binary64": {
            "curl": [float(curl_value.real), float(curl_value.imag)],
            "material_mass": [float(mass_value.real), float(mass_value.imag)],
        },
        "b_replay_binary64": [float(b_replay.real), float(b_replay.imag)],
        "b_saved_volume_binary64": [float(b_saved.real), float(b_saved.imag)],
        "b_full_rhs_binary64": [float(b_full.real), float(b_full.imag)],
        "b_alpha_binary64": [float(b_alpha.real), float(b_alpha.imag)],
        "b_volume_plus_b_alpha_binary64": [float(volume_plus_alpha.real), float(volume_plus_alpha.imag)],
        "b_full_minus_b_volume_then_b_alpha_binary64": [
            float(b_full_minus_volume_then_alpha.real), float(b_full_minus_volume_then_alpha.imag)
        ],
        "b_full_minus_reassembled_volume_plus_b_alpha_binary64": [
            float(b_full_minus_reassembled.real), float(b_full_minus_reassembled.imag)
        ],
        "target_bitwise_matches_saved_volume_rhs": target_bound,
        "all_900_internal_rows_bitwise_match_saved_volume_rhs": internal_bound,
        "native_binding_status": (
            "BOUND_SELECTED_TARGET_AND_900_INTERNAL_ROWS" if target_bound and internal_bound
            else "NATIVE_REPLAY_UNBOUND"
        ),
        "native_binding_reason": (
            "EXACT_SELECTED_ROWS_MATCH" if target_bound and internal_bound else "NUMERICAL_MISMATCH"
        ),
        "cells": cell_reports,
        "signed_integral_entity_contributions": signed,
        "decimal_signed_decomposition": decimal,
    }


def _write_report(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() or path.is_symlink():
        raise FileExistsError("V19 checker report already exists; preserving prior audit evidence")
    temporary = path.with_name(path.name + f".{os.getpid()}.tmp")
    if temporary.exists() or temporary.is_symlink():
        raise FileExistsError("V19 checker temporary output already exists")
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"
    if len(encoded) > capture.V19_MAX_NEW_EVIDENCE_BYTES:
        raise OSError("V19 checker report exceeds its 16 MiB evidence cap")
    try:
        with temporary.open("xb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        temporary.unlink()
        parent_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except Exception:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise


def check_v19_saved_native_rank1(
    *, repo_root: str | Path,
    output_directory: str | Path,
    expected_receipt_sha256: str,
    expected_contract_sha256: str,
    expected_window_sha256: str,
    receipt_path: str | Path | None = None,
    producer_contract_path: str | Path | None = None,
    expected_consumer_contract_sha256: str | None = None,
    consumer_contract_path: str | Path | None = None,
    expected_progress_sha256: str | None = None,
    output_path: str | Path | None = None,
    service_directory: str | Path | None = None,
) -> dict[str, Any]:
    """Reopen and independently audit one completed V19 capture.

    Missing inputs and binding failures are written into a complete negative
    report; they do not turn into an early generic exception or a PASS.
    """
    checker_started = time.perf_counter()
    root = Path(repo_root).resolve(strict=True)
    out = Path(output_directory).resolve(strict=True)
    report_path = Path(output_path) if output_path is not None else out / "task41_p0_v19_independent_check.json"
    if not report_path.is_absolute():
        report_path = (out / report_path).resolve(strict=False)
    if service_directory is None:
        if not report_path.resolve(strict=False).is_relative_to(out):
            raise ValueError("V19 checker report path escaped the attempt directory")
    else:
        service_root = Path(service_directory)
        if service_root.is_symlink() or not service_root.is_dir():
            raise ValueError("V19 checker service output directory is not a real directory")
        service_root = service_root.resolve(strict=True)
        if (
            service_root.parent != out.parent
            or not service_root.name.startswith(out.name + ".service-")
            or report_path.resolve(strict=False).parent != service_root
        ):
            raise ValueError("V19 checker report escaped its attempt-specific service directory")

    result: dict[str, Any] = {
        "schema": V19_CHECKER_SCHEMA,
        "audit_completed": False,
        "data_complete": False,
        "native_binding_status": "NATIVE_REPLAY_UNBOUND",
        "native_binding_reason": "INCOMPLETE_OR_UNBOUND_EVIDENCE",
        "original_action_status": "FAIL",
        "original_action_source": "Task41 Review V19 §1; inherited V9 full-action result",
        "scientific_qualified": False,
        "official_result": False,
        "full_owner_unlocked": False,
        "new_rank2_kernels": 0,
        "new_factorizations": 0,
        "new_getrs": 0,
        "new_full_native_action": False,
        "scope": {
            "selected_cells": list(capture.V19_SELECTED_CELLS),
            "columns": list(capture.V19_COLUMNS),
            "active_row": 1_622_464,
            "original_row": 5_218_672,
            "historical_producer_bitwise_replay_claimed": False,
        },
        "stages": {},
        "column_diagnostics": [],
        "errors": [],
    }
    receipt: dict[str, Any] | None = None
    terms: dict[tuple[str, int, int, int], dict[str, Any]] = {}
    term_errors: list[str] = []
    try:
        consumer_contract_sha256 = (
            expected_consumer_contract_sha256 or expected_contract_sha256
        )
        if (
            not isinstance(expected_receipt_sha256, str)
            or _HEX64.fullmatch(expected_receipt_sha256) is None
            or not isinstance(expected_contract_sha256, str)
            or _HEX64.fullmatch(expected_contract_sha256) is None
            or not isinstance(consumer_contract_sha256, str)
            or _HEX64.fullmatch(consumer_contract_sha256) is None
            or not isinstance(expected_window_sha256, str)
            or _HEX64.fullmatch(expected_window_sha256) is None
        ):
            raise ValueError("external receipt/contract/window SHA identity is malformed")
        receipt_file = (
            Path(receipt_path)
            if receipt_path is not None
            else out / f"task41_p0_v19_native_rank1_worker_{expected_contract_sha256}.json"
        )
        if not receipt_file.is_absolute():
            receipt_file = out / receipt_file
        if (
            receipt_file.is_symlink()
            or receipt_file.resolve(strict=False).parent != out
            or receipt_file.name != f"task41_p0_v19_native_rank1_worker_{expected_contract_sha256}.json"
            or not receipt_file.is_file()
            or _sha256(receipt_file) != expected_receipt_sha256
        ):
            raise ValueError("worker receipt is missing or differs from external SHA-256")
        receipt = _read_json(
            receipt_file, maximum_bytes=capture.V19_MAX_NEW_EVIDENCE_BYTES,
            label="V19 worker receipt",
        )
        if (
            receipt.get("schema") != capture.V19_RECEIPT_SCHEMA
            or receipt.get("status") != "COMPLETED_LOCAL_NATIVE_RANK1_CAPTURE"
            or receipt.get("official_result") is not False
            or receipt.get("scientific_qualified") is not False
            or receipt.get("full_owner_unlocked") is not False
            or receipt.get("consumer_contract_sha256") != expected_contract_sha256
            or receipt.get("consumer_window_sha256") != expected_window_sha256
            or receipt.get("rank2_kernel_outputs") != 0
            or receipt.get("factorizations") != 0
            or receipt.get("getrs") != 0
            or receipt.get("full_native_action") is not False
        ):
            raise ValueError("worker receipt scope or zero-new-solve boundary differs")
        stage_timings = receipt.get("stage_timings_seconds")
        required_timing_fields = {
            "mesh_construction_seconds",
            "fresh_map_validation_seconds",
            "form_jit_action_construction_seconds",
            "coefficient_table_packing_seconds",
            "selected_coefficient_row_packing_seconds",
            "kernel_execution_seconds",
            "direction_transform_seconds",
            "term_archive_save_seconds",
        }
        worker_elapsed = receipt.get("worker_function_elapsed_seconds_pre_receipt_write")
        if (
            not isinstance(stage_timings, Mapping)
            or set(stage_timings) != required_timing_fields
            or any(
                not isinstance(value, (int, float))
                or isinstance(value, bool)
                or not np.isfinite(float(value))
                or float(value) < 0.0
                for value in stage_timings.values()
            )
            or not isinstance(worker_elapsed, (int, float))
            or isinstance(worker_elapsed, bool)
            or not np.isfinite(float(worker_elapsed))
            or float(worker_elapsed) < 0.0
        ):
            raise ValueError("V19 receipt stage/worker elapsed timing fields are incomplete")
        result["stages"]["timing"] = {
            "status": "MEASURED",
            "clock": "time.perf_counter",
            "worker_function_elapsed_seconds_pre_receipt_write": float(worker_elapsed),
            "stage_timings_seconds": dict(stage_timings),
        }
        producer_contract_file: Path | None = None
        producer_contract: dict[str, Any] | None = None
        has_contract_rebinding = (
            producer_contract_path is not None
            or consumer_contract_path is not None
            or receipt.get("consumer_contract_path") is not None
        )
        if has_contract_rebinding:
            producer_contract_file = (
                Path(producer_contract_path)
                if producer_contract_path is not None
                else Path(str(receipt.get("consumer_contract_path", "")))
            )
            if producer_contract_file.is_symlink() or not producer_contract_file.is_absolute():
                raise ValueError("V19 producer contract path is not absolute and immutable")
            if producer_contract_file.resolve(strict=True) != Path(
                str(receipt.get("consumer_contract_path", ""))
            ).resolve(strict=True):
                raise ValueError("V19 producer contract path differs from its saved receipt")
            from src.runners.task41_p0_contract import (
                TASK41_B0_V19_NATIVE_RANK1_SCOPE,
                TASK41_B0_V19_NATIVE_RANK1_WINDOW_RELATIVE,
                _git,
                require_task41_p0_contract,
            )

            producer_contract, producer_contract_digest = require_task41_p0_contract(
                producer_contract_file,
                expected_sha256=expected_contract_sha256,
                current_root=root,
                require_clean_source=False,
                check_current_source=False,
                case_id="B0",
            )
            if (
                producer_contract_digest != expected_contract_sha256
                or producer_contract.get("source", {}).get("sha")
                != receipt.get("consumer_source_sha")
                or producer_contract.get("window", {}).get("sha256") != expected_window_sha256
                or producer_contract.get("window", {}).get("path")
                != TASK41_B0_V19_NATIVE_RANK1_WINDOW_RELATIVE.as_posix()
                or producer_contract.get("execution_scope") != TASK41_B0_V19_NATIVE_RANK1_SCOPE
            ):
                raise ValueError("V19 producer contract/source/window differs from the saved receipt")
            if consumer_contract_path is not None:
                consumer_contract_file = Path(consumer_contract_path)
                consumer_contract, consumer_contract_digest = require_task41_p0_contract(
                    consumer_contract_file,
                    expected_sha256=consumer_contract_sha256,
                    current_root=root,
                    require_clean_source=True,
                    check_current_source=True,
                    case_id="B0",
                )
                if (
                    consumer_contract_digest != consumer_contract_sha256
                    or consumer_contract.get("execution_scope") != TASK41_B0_V19_NATIVE_RANK1_SCOPE
                    or consumer_contract.get("window", {}).get("path")
                    != producer_contract.get("window", {}).get("path")
                    or consumer_contract.get("window", {}).get("sha256") != expected_window_sha256
                    or consumer_contract.get("resources") != producer_contract.get("resources")
                    or consumer_contract.get("source", {}).get("sha")
                    != _git(root, "rev-parse", "HEAD")
                ):
                    raise ValueError("V19 current consumer contract is not the same authorized window/scope/resources")
            elif consumer_contract_sha256 != expected_contract_sha256:
                raise ValueError("V19 source-repair recheck requires the new consumer contract path")
        producer_sha = receipt.get("original_donor", {}).get("source_sha")
        consumer_sha = receipt.get("consumer_source_sha")
        result["stages"]["receipt"] = {
            "status": "PINNED_COMPLETE_RECEIPT",
            "sha256": expected_receipt_sha256,
            "producer_contract_path": (
                str(producer_contract_file) if producer_contract_file is not None else None
            ),
            "producer_contract_sha256": expected_contract_sha256,
            "consumer_source_sha": consumer_sha,
            "producer_source_sha": producer_sha,
            "producer_consumer_source_separated": consumer_sha != producer_sha,
            "consumer_contract_sha256": consumer_contract_sha256,
            "window_sha256": expected_window_sha256,
            "historical_kernel_identity_status": receipt.get("original_donor", {}).get(
                "historical_kernel_identity_status"
            ),
        }
        order = _expected_terms(receipt)
        progress_path = out / "task41_p0_v19_native_rank1_progress.json"
        if expected_progress_sha256 is not None:
            if (
                _HEX64.fullmatch(expected_progress_sha256) is None
                or progress_path.is_symlink()
                or not progress_path.is_file()
                or _sha256(progress_path) != expected_progress_sha256
            ):
                raise ValueError("V19 progress checkpoint differs from its external input hash")
        progress = _read_progress(out, receipt)
        terms, term_errors = _load_term_archives(receipt, progress, out, order)
        result["stages"]["archive_reopen"] = {
            "expected_dynamic_term_count": sum(len(rows) for rows in order.values()),
            "reopened_term_count": len(terms),
            "status": "ALL_ARCHIVE_AND_MEMBER_HASHES_VERIFIED" if not term_errors else "UNBOUND_OR_INCOMPLETE",
            "errors": term_errors,
        }
        result["errors"].extend(term_errors)
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        result["errors"].append(f"receipt/archive stage: {type(exc).__name__}: {exc}")

    if receipt is not None:
        try:
            callback, cells, _metadata, donor, v17_path = _load_v17_context(root=root, receipt=receipt)
            reference = _load_local_reference_arrays(
                root=root, report_path=v17_path, callback=callback, cells=cells, donor=donor
            )
            result["stages"]["pinned_sources_and_maps"] = {
                "status": "V17_V3_AND_ACTUAL_I_T_E_MAPS_REOPENED",
                "donor_manifest_sha256": donor.get("manifest_sha256"),
                "donor_run": donor.get("run_name"),
                "covered_map_proof": (
                    "450 interior rows per cell are disjoint; the selected trace pullback is the direct +1 slot; "
                    "the two incident cells match pinned V16/V17 metadata"
                ),
                "worker_mpc_support_summary": receipt.get("mpc_restriction_support"),
                "producer_consumer_source_separated": (
                    receipt.get("consumer_source_sha") != receipt.get("original_donor", {}).get("source_sha")
                ),
            }
            for column in capture.V19_COLUMNS:
                result["column_diagnostics"].append(_audit_column(
                    column=column, terms=terms, cells=cells, reference=reference, donor=donor
                ))
            binding_statuses = [row["native_binding_status"] for row in result["column_diagnostics"]]
            result["data_complete"] = not result["errors"] and len(binding_statuses) == 2
            archive_complete = (
                result.get("stages", {}).get("archive_reopen", {}).get("status")
                == "ALL_ARCHIVE_AND_MEMBER_HASHES_VERIFIED"
            )
            if (
                not result["errors"] and archive_complete and len(binding_statuses) == 2
                and all(status == "BOUND_SELECTED_TARGET_AND_900_INTERNAL_ROWS" for status in binding_statuses)
            ):
                result["native_binding_status"] = "BOUND_SELECTED_TARGET_AND_900_INTERNAL_ROWS"
                result["native_binding_reason"] = "EXACT_SELECTED_ROWS_MATCH"
            elif result["errors"] or not archive_complete:
                result["native_binding_status"] = "NATIVE_REPLAY_UNBOUND"
                result["native_binding_reason"] = "INCOMPLETE_OR_UNBOUND_EVIDENCE"
            else:
                result["native_binding_status"] = "NATIVE_REPLAY_UNBOUND"
                result["native_binding_reason"] = "NUMERICAL_MISMATCH"
        except (OSError, ValueError, KeyError, IndexError, json.JSONDecodeError, TypeError) as exc:
            result["errors"].append(f"source/map/diagnostic stage: {type(exc).__name__}: {exc}")
            result["native_binding_status"] = "NATIVE_REPLAY_UNBOUND"
            result["native_binding_reason"] = "INCOMPLETE_OR_UNBOUND_EVIDENCE"
    else:
        result["errors"].append("source/map diagnostics skipped because the receipt is not externally bound")

    if result["errors"] and result["data_complete"]:
        result["data_complete"] = False
    result["audit_completed"] = True
    result["status"] = "AUDIT_COMPLETED_DATA_COMPLETE" if result["data_complete"] else "AUDIT_COMPLETED_DATA_INCOMPLETE"
    result["native_binding"] = {
        "status": result["native_binding_status"],
        "reason": result.get("native_binding_reason", "INCOMPLETE_OR_UNBOUND_EVIDENCE"),
        "historical_producer_bitwise_replay": False,
        "interpretation": "RECONSTRUCTED_SELECTED_NATIVE_ACTION_NOT_HISTORICAL_BITWISE_REPLAY",
    }
    result["checker_elapsed_seconds"] = time.perf_counter() - checker_started
    _write_report(report_path, result)
    return result






def _checker_cli(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Independently reopen a V19 rank-1 attempt")
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--receipt-sha256", required=True)
    parser.add_argument("--receipt-path", type=Path)
    parser.add_argument("--producer-contract-path", type=Path)
    parser.add_argument("--producer-contract-sha256")
    parser.add_argument("--consumer-contract-path", type=Path)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--window-sha256", required=True)
    parser.add_argument("--progress-sha256")
    parser.add_argument("--service-directory", type=Path, required=True)
    parser.add_argument("--report-path", type=Path, required=True)
    args = parser.parse_args(argv)
    result = check_v19_saved_native_rank1(
        repo_root=args.repo_root,
        output_directory=args.output_dir,
        expected_receipt_sha256=args.receipt_sha256,
        expected_contract_sha256=(args.producer_contract_sha256 or args.contract_sha256),
        expected_window_sha256=args.window_sha256,
        receipt_path=args.receipt_path,
        producer_contract_path=args.producer_contract_path,
        expected_consumer_contract_sha256=args.contract_sha256,
        consumer_contract_path=args.consumer_contract_path,
        expected_progress_sha256=args.progress_sha256,
        output_path=args.report_path,
        service_directory=args.service_directory,
    )
    print(json.dumps(result, sort_keys=True, ensure_ascii=False), flush=True)
    # A completed independent audit may correctly conclude UNBOUND/incomplete.
    return 0 if result.get("audit_completed") is True else 3


if __name__ == "__main__":
    raise SystemExit(_checker_cli())
