"""V18 saved-only full -Jz candidate worker; performs no factors or solves."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import tempfile
import time
from typing import Any, Mapping

import numpy as np

from src.runners.task41_p0_contract import (
    TASK41_B0_V18_SAVED_JZ_SCOPE,
    TASK41_MODEL_ID,
)
from src.runners.task41_p0_v4_volume_only_audit import task41_p0_v18_evaluate_saved_jz_candidate

SCHEMA = "task41.p0.v18.saved_jz_candidate.v1"
MAX_REPORT_BYTES = 16 * 1024**2
MAX_RAW_BYTES = 16 * 1024**3
MIN_FREE_BYTES = 2 * 1024**3
MAX_WORKING_BYTES = 4 * 1024**3

SOURCE_BINDINGS: dict[str, tuple[str, str]] = {
    "v17": (
        "results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/7d12b524c385f3d211579a5b49772f36b4e0f1198e9364a49a0afc2733dbbc54/selected_incident_replay/attempt04/task41_p0_v17_selected_two_cell_worker.json",
        "4e6fce6680a0bb304ed0370542f8b5c6003d39940d94ff3e54f19322aeb1709b",
    ),
    "v14_v11": (
        "results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/4f5d35994e2034c7128a87528303b87892c5563beddc2363e511d1c26dd2d47c/selected_incident_replay/attempt01/candidate/task41_p0_v14_saved_rhs_candidate.json",
        "a0ed3dd42129705e4806092d611c559403b832862eb3f6ee54a90880ea0f8f19",
    ),
    "v14_v8": (
        "results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/4f5d35994e2034c7128a87528303b87892c5563beddc2363e511d1c26dd2d47c/selected_incident_replay/attempt04/candidate/task41_p0_v14_saved_rhs_candidate.json",
        "e65f3471351f51cc7b7033718af3ae2876096c20f124cefd8566483cb14248f7",
    ),
    "v11": (
        "results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/4fc153c4e0526a21eb01aa3d6e5c774af7c74a849a3461b676e7ffdf214debc6/selected_incident_replay/attempt03/task41_p0_v11_selected_trace_candidate_replay.json",
        "2463e322ea72160bfcca7f3345d149ab20e5b017982f1f9ed55010df0afa9876",
    ),
    "v11_metadata": (
        "results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/bc646b17157eed567e2c5391df79e4eda681ab4028f9e86901e8c7fcfd9222b4/selected_incident_replay/attempt02/task41_p0_v8_selected_trace_star_metadata.json",
        "332baa3a5253a8322b56615c7fe087e401f909c3c889fa048fccc3f9f2b9fcd3",
    ),
    "v8": (
        "results/task41extra_phi90_p50x50_g17x20/task41_b0_v8_selected_star_35fd1bbf_20261021T072801Z_attempt1/task41_p0_v8_selected_trace_star_audit.json",
        "1bdd07ac38bce95d58a153bacdca0de6cf5941d08d2706dc127e8b00d8e2764f",
    ),
}
V18_EXPECTED_ITEMS = {
    ("v17", cell, column, state)
    for cell in (7873, 8014)
    for column in (0, 1)
    for state in ("initial", "final")
} | {
    (star, cell, column, "final")
    for star, cells in (("v14_v11", (360, 446)), ("v14_v8", (23352, 23493)))
    for cell in cells
    for column in (0, 1)
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_pinned_json(root: Path, key: str) -> tuple[Path, dict[str, Any]]:
    relative, expected = SOURCE_BINDINGS[key]
    path = root / relative
    if path.is_symlink():
        raise ValueError(f"V18 {key} report is a symlink")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or resolved.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError(f"V18 {key} report path/size is outside the fixed source scope")
    if sha256_file(resolved) != expected:
        raise ValueError(f"V18 {key} report SHA-256 differs")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"V18 {key} report is not a JSON object")
    return resolved, payload


def _load_pinned_sources(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    reports: dict[str, dict[str, Any]] = {}
    paths: dict[str, str] = {}
    expected_schema_status = {
        "v17": ("task41.p0.b0.v17.selected_two_cell_worker_receipt.v1", "COMPLETED_LOCAL_SELECTED_TWO_CELL_REPLAY"),
        "v14_v11": ("task41.p0.v14.saved_same_lu_rhs_candidate.v1", "CANDIDATE_PRODUCED_PENDING_INDEPENDENT_CHECK"),
        "v14_v8": ("task41.p0.v14.saved_same_lu_rhs_candidate.v1", "CANDIDATE_PRODUCED_PENDING_INDEPENDENT_CHECK"),
        "v11": ("task41.p0.v11.selected_trace_star_candidate_replay_receipt.v1", "COMPLETED_LOCAL_CANDIDATE_REPLAY"),
        "v11_metadata": ("task41.p0.v8.selected_trace_star_metadata_only_receipt.v1", "COMPLETED_METADATA_ONLY"),
        "v8": ("task41.p0.v8.selected_trace_star_audit_receipt.v1", "COMPLETED_SELECTED_TRACE_STAR_AUDIT"),
    }
    for key in SOURCE_BINDINGS:
        path, payload = _read_pinned_json(root, key)
        schema, status = expected_schema_status[key]
        if payload.get("schema") != schema or payload.get("status") != status:
            raise ValueError(f"V18 {key} schema/status differs")
        reports[key], paths[key] = payload, str(path)
    if reports["v14_v11"].get("producer_report_sha256") != SOURCE_BINDINGS["v11"][1]:
        raise ValueError("V18 V14/V11 donor binding differs")
    if reports["v14_v8"].get("producer_report_sha256") != SOURCE_BINDINGS["v11"][1]:
        raise ValueError("V18 V14/V8 V11 producer binding differs")
    if reports["v14_v8"].get("star_producer_report_sha256") != SOURCE_BINDINGS["v8"][1]:
        raise ValueError("V18 V14/V8 star binding differs")
    if reports["v14_v11"].get("consumer_window_sha256") != "4f5d35994e2034c7128a87528303b87892c5563beddc2363e511d1c26dd2d47c":
        raise ValueError("V18 V14/V11 source window differs")
    if reports["v17"].get("consumer_window_sha256") != "7d12b524c385f3d211579a5b49772f36b4e0f1198e9364a49a0afc2733dbbc54":
        raise ValueError("V18 V17 source window differs")
    metadata_report_path = reports["v11"].get("selected_metadata_report_path")
    expected_metadata_path = str((root / SOURCE_BINDINGS["v11_metadata"][0]).resolve())
    if Path(str(metadata_report_path)).resolve(strict=True) != Path(expected_metadata_path):
        raise ValueError("V18 V11 receipt points to another map metadata report")
    return reports, paths


def _pair(value: Any, label: str) -> complex:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or any(type(part) not in (int, float) or not math.isfinite(float(part)) for part in value)
    ):
        raise ValueError(f"V18 {label} must be a finite real/imaginary pair")
    return complex(float(value[0]), float(value[1]))


def _refs_equal(left: Any, right: Any) -> bool:
    return isinstance(left, Mapping) and isinstance(right, Mapping) and dict(left) == dict(right)


def _build_sources(reports: Mapping[str, Mapping[str, Any]], report_paths: Mapping[str, str]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Bind all 16 exact J/z inputs and replay groups to pinned receipt nodes."""
    items: list[dict[str, Any]] = []
    groups: list[dict[str, Any]] = []
    callback = reports["v17"]["selected_two_cell_candidate_callback"]
    if callback.get("scope", {}).get("selected_active_row") != 1_622_464:
        raise ValueError("V18 V17 selected active row differs")
    if callback.get("scope", {}).get("selected_original_row") != 5_218_672:
        raise ValueError("V18 V17 selected original row differs")
    v17_cells = {int(row["cell_index"]): row for row in callback["cells"]}
    v17_columns = {int(row["column"]): row for row in callback["columns"]}
    if set(v17_cells) != {7873, 8014} or set(v17_columns) != {0, 1}:
        raise ValueError("V18 V17 fixed cell/column coverage differs")
    for column in (0, 1):
        column_record = v17_columns[column]
        for state, z_name, base_name, y_name, g_name in (
            ("initial", "z0", "z0_minus_Jz", "saved_y9", "saved_g9"),
            ("final", "final_z", "returned_minus_Jz", "saved_y15", "saved_g15"),
        ):
            group = {
                "star": "v17", "state": state, "column_index": column,
                "cell_order": [7873, 8014], "selected_active_row": 1_622_464,
                "selected_original_row": 5_218_672,
                "b_t": column_record["native_rhs_t"],
                "native_volume_rhs_t": column_record["native_volume_rhs_t"],
                "b_alpha": column_record["b_alpha_t"],
                "saved_y": column_record[y_name], "saved_g": column_record[g_name],
                "source_node": {"report_sha256": SOURCE_BINDINGS["v17"][1], "column_index": column, "state_key": y_name},
                "s_action_refs": {}, "known_interior_refs": {}, "known_trace_refs": {},
            }
            for cell in (7873, 8014):
                cell_record = v17_cells[cell]
                if len(cell_record["columns"]) != 2:
                    raise ValueError("V18 V17 cell row must preserve two ordered columns")
                column_rows = {index: row for index, row in enumerate(cell_record["columns"])}
                if any(int(row.get("cell_index", cell)) != cell for row in column_rows.values()):
                    raise ValueError("V18 V17 local column record is attached to another cell")
                local = column_rows[column]
                rhs = local["rhs_artifacts"]
                item = {
                    "star": "v17", "state": state, "cell_index": cell,
                    "column_index": column, "selected_active_row": 1_622_464,
                    "selected_original_row": 5_218_672,
                    "tensor_ref": cell_record["candidate_artifacts"]["oriented_tensor"],
                    "map_refs": cell_record["fresh_map_artifacts"],
                    "z_ref": rhs[z_name], "baseline_ref": rhs[base_name],
                    "s_action_ref": local["S_action_artifact"],
                    "source_node": {
                        "report_sha256": SOURCE_BINDINGS["v17"][1],
                        "cell_index": cell, "column_index": column,
                        "state_key": z_name,
                    },
                }
                items.append(item)
                group["s_action_refs"][str(cell)] = local["S_action_artifact"]
                group["known_interior_refs"][str(cell)] = local["known_interior_local_artifact"]
                group["known_trace_refs"][str(cell)] = local["known_trace_local_artifact"]
            groups.append(group)

    v11_meta = reports["v11_metadata"]["selected_trace_star_metadata_only"]["selected_cells"]
    map_v11 = {int(record["cell_index"]): record["arrays"] for record in v11_meta}
    v8_cells = reports["v8"]["selected_trace_star_metadata"]["cell_artifacts"]
    map_v8 = {int(cell): value["arrays"] for cell, value in v8_cells.items() if str(cell).isdigit()}
    for star, metadata, cells, active_row, original_row in (
        ("v14_v11", "v11_metadata", (360, 446), 87_567, 250_113),
        ("v14_v8", "v8", (23352, 23493), 4_766_937, 15_440_235),
    ):
        candidate = reports[star]
        rhs_rows: dict[tuple[int, int], Mapping[str, Any]] = {}
        for row in candidate["candidate_rhs"]:
            key = (int(row["cell_index"]), int(row["column"]))
            if key in rhs_rows:
                raise ValueError(f"V18 {star} duplicates candidate RHS key {key}")
            rhs_rows[key] = row
        if set(rhs_rows) != {(cell, col) for cell in cells for col in (0, 1)}:
            raise ValueError(f"V18 {star} fixed J/z row coverage differs")
        expected_maps = map_v11 if metadata == "v11_metadata" else map_v8
        if set(cells) - set(expected_maps):
            raise ValueError(f"V18 {star} map metadata lacks a pinned selected cell")
        production_rows = candidate["production_order_rows"]
        expected_states = {None} if star == "v14_v11" else {"j0", "j3"}
        expected_row_keys = {(col, state) for col in (0, 1) for state in expected_states}
        row_map: dict[tuple[int, str | None], Mapping[str, Any]] = {}
        for row in production_rows:
            col = int(row["column"])
            state = row.get("state")
            if (col, state) in row_map:
                raise ValueError(f"V18 {star} duplicated production row {(col, state)}")
            row_map[(col, state)] = row
        if set(row_map) != expected_row_keys:
            raise ValueError(f"V18 {star} production row state/column coverage differs")
        for (column, source_state), production in sorted(row_map.items(), key=lambda pair: (pair[0][0], str(pair[0][1]))):
            if production.get("selected_active_row") != active_row or production.get("selected_original_row") != original_row:
                raise ValueError(f"V18 {star} selected row identity differs")
            if production.get("incident_cell_order") != list(cells):
                raise ValueError(f"V18 {star} production cell order differs")
            state = "final" if source_state is None else str(source_state)
            group = {
                "star": star, "state": state, "source_state": source_state,
                "column_index": column, "cell_order": list(cells),
                "selected_active_row": active_row, "selected_original_row": original_row,
                "b_t": production["base_b_t"],
                "b_alpha": production["b_alpha_row_used_once"],
                "saved_y": production["saved_y"],
                "saved_g": production["candidate_g_actual_returned_correction_cell_order"],
                "s_action_refs": {},
                "source_node": {
                    "report_sha256": SOURCE_BINDINGS[star][1],
                    "production_order_row": production_rows.index(production),
                    "metadata_report_sha256": SOURCE_BINDINGS[metadata][1],
                },
            }
            actions = production["y_cell_s_action_sources"]
            if len(actions) != len(cells):
                raise ValueError(f"V18 {star} S-action source count differs")
            for cell, action_ref in zip(cells, actions, strict=True):
                rhs = rhs_rows[(cell, column)]
                item_key = (star, cell, column, "final")
                if not any((item["star"], item["cell_index"], item["column_index"], item["state"]) == item_key for item in items):
                    items.append({
                        "star": star, "state": "final", "cell_index": cell,
                        "column_index": column, "selected_active_row": active_row,
                        "selected_original_row": original_row,
                        "tensor_ref": rhs["oriented_tensor"],
                        "map_refs": expected_maps[cell], "z_ref": rhs["final_z"],
                        "baseline_ref": rhs["returned_correction"],
                        "source_node": {
                            "report_sha256": SOURCE_BINDINGS[star][1],
                            "candidate_rhs_key": [cell, column],
                            "metadata_report_sha256": SOURCE_BINDINGS[metadata][1],
                        },
                    })
                group["s_action_refs"][str(cell)] = action_ref
            groups.append(group)
    identities = [(item["star"], item["cell_index"], item["column_index"], item["state"]) for item in items]
    if len(items) != 16 or len(set(identities)) != 16 or set(identities) != V18_EXPECTED_ITEMS:
        raise ValueError("V18 exactly 16 complete-J/z input associations differ")
    return items, groups


def _load_array_ref(
    ref: Any, *, results_root: Path, cache: dict[tuple[str, str], np.ndarray], label: str,
) -> np.ndarray:
    if not isinstance(ref, Mapping):
        raise ValueError(f"V18 {label} reference is malformed")
    raw_path = Path(str(ref.get("path", "")))
    if not raw_path.is_absolute() or raw_path.is_symlink():
        raise ValueError(f"V18 {label} path is not a regular absolute source path")
    path = raw_path.resolve(strict=True)
    digest = ref.get("sha256")
    if (
        not path.is_relative_to(results_root) or not path.is_file()
        or type(ref.get("bytes")) is not int or path.stat().st_size != ref["bytes"]
        or not isinstance(digest, str) or sha256_file(path) != digest
    ):
        raise ValueError(f"V18 {label} path, size, or SHA-256 differs")
    key = (str(path), digest)
    if key not in cache:
        value = np.load(path, mmap_mode="r", allow_pickle=False)
        if value.dtype.hasobject or list(value.shape) != ref.get("shape") or str(value.dtype) != ref.get("dtype"):
            raise ValueError(f"V18 {label} shape/dtype differs from its pinned receipt")
        cache[key] = value
    return cache[key]


def _collect_refs(items: list[dict[str, Any]], groups: list[dict[str, Any]]) -> dict[tuple[str, str], Mapping[str, Any]]:
    refs: dict[tuple[str, str], Mapping[str, Any]] = {}
    for item in items:
        for label, ref in (("tensor", item["tensor_ref"]), ("z", item["z_ref"]), ("baseline", item["baseline_ref"])):
            if not isinstance(ref, Mapping):
                raise ValueError(f"V18 {label} source reference is malformed")
            refs[(str(ref.get("path")), str(ref.get("sha256")))] = ref
        maps = item["map_refs"]
        for label in ("active_ids", "interior_positions", "trace_positions", "trace_expansion_data", "trace_expansion_indices", "trace_expansion_indptr"):
            refs[(str(maps[label].get("path")), str(maps[label].get("sha256")))] = maps[label]
    for group in groups:
        for mapping_name in ("s_action_refs", "known_interior_refs", "known_trace_refs"):
            for ref in group.get(mapping_name, {}).values():
                refs[(str(ref.get("path")), str(ref.get("sha256")))] = ref
    return refs


def stat_bound_raw_artifact_inventory(*, repo_root: Path) -> list[dict[str, Any]]:
    """Return a path-deduplicated stat inventory without hashing/loading NPY payloads."""
    root = repo_root.resolve(strict=True)
    results_root = (root / "results" / TASK41_MODEL_ID).resolve(strict=True)
    reports, report_paths = _load_pinned_sources(root)
    items, groups = _build_sources(reports, report_paths)
    refs = _collect_refs(items, groups)
    by_path: dict[Path, dict[str, Any]] = {}
    for ref in refs.values():
        raw = Path(str(ref.get("path", "")))
        digest = ref.get("sha256")
        size = ref.get("bytes")
        if (
            not raw.is_absolute() or raw.is_symlink()
            or type(size) is not int or size <= 0
            or not isinstance(digest, str) or len(digest) != 64
        ):
            raise ValueError("V18 bound source inventory has a malformed path/size/hash")
        path = raw.resolve(strict=True)
        if (
            not path.is_file() or not path.is_relative_to(results_root)
            or path.suffix.lower() not in {".npy", ".npz"}
            or path.stat().st_size != size
        ):
            raise ValueError("V18 bound source inventory escaped results or changed size")
        current = {"path": str(path), "bytes": size, "sha256": digest}
        previous = by_path.setdefault(path, current)
        if previous != current:
            raise ValueError("V18 bound source inventory repeats a path with conflicting identity")
    return [by_path[path] for path in sorted(by_path)]


def _load_operation(item: Mapping[str, Any], *, results_root: Path, cache: dict[tuple[str, str], np.ndarray]) -> dict[str, Any]:
    tensor = _load_array_ref(item["tensor_ref"], results_root=results_root, cache=cache, label="oriented tensor")
    maps = item["map_refs"]
    interior = np.asarray(_load_array_ref(maps["interior_positions"], results_root=results_root, cache=cache, label="interior positions"), dtype=np.int64)
    trace = np.asarray(_load_array_ref(maps["trace_positions"], results_root=results_root, cache=cache, label="trace positions"), dtype=np.int64)
    if tensor.shape != (882, 882) or tensor.dtype != np.dtype(np.complex128):
        raise ValueError("V18 full oriented tensor must be complex128 882x882")
    if interior.shape != (450,) or trace.shape != (432,) or not np.array_equal(np.sort(np.r_[interior, trace]), np.arange(882)):
        raise ValueError("V18 saved I/T maps are not a unique full 450/432 partition")
    J = np.array(tensor[np.ix_(trace, interior)], dtype=np.complex128, order="C", copy=True)
    if not np.isfinite(J).all():
        raise ValueError("V18 extracted complete J contains non-finite values")
    z_view = _load_array_ref(item["z_ref"], results_root=results_root, cache=cache, label="saved z")
    baseline_view = _load_array_ref(item["baseline_ref"], results_root=results_root, cache=cache, label="saved baseline correction")
    if z_view.shape != (450,) or z_view.dtype != np.dtype(np.complex128) or baseline_view.shape != (432,) or baseline_view.dtype != np.dtype(np.complex128):
        raise ValueError("V18 saved z/correction layout differs")
    z = np.array(z_view, dtype=np.complex128, copy=True)
    baseline = np.array(baseline_view, dtype=np.complex128, copy=True)
    if not np.isfinite(z).all() or not np.isfinite(baseline).all():
        raise ValueError("V18 saved z/correction contains non-finite values")
    active = _load_array_ref(maps["active_ids"], results_root=results_root, cache=cache, label="active ids")
    data = np.asarray(_load_array_ref(maps["trace_expansion_data"], results_root=results_root, cache=cache, label="trace expansion data"), dtype=np.complex128)
    indices = np.asarray(_load_array_ref(maps["trace_expansion_indices"], results_root=results_root, cache=cache, label="trace expansion indices"), dtype=np.int64)
    indptr = np.asarray(_load_array_ref(maps["trace_expansion_indptr"], results_root=results_root, cache=cache, label="trace expansion indptr"), dtype=np.int64)
    if (
        active.ndim != 1 or active.size == 0 or active.dtype.kind not in "iu"
        or data.ndim != 1 or indices.shape != data.shape
        or indptr.shape != (trace.size + 1,) or indptr[0] != 0
        or indptr[-1] != data.size or np.any(indptr[1:] < indptr[:-1])
        or np.any(indices < 0) or np.any(indices >= active.size)
        or not np.isfinite(data).all()
    ):
        raise ValueError("V18 saved MPC expansion CSR is malformed")
    target_active = int(item["selected_active_row"])
    positions = np.flatnonzero(active == target_active)
    if positions.size != 1:
        raise ValueError("V18 selected active row is absent/duplicated in saved cell map")
    return {"J": J, "z": z, "baseline": baseline, "active": active,
            "tensor_fortran_order": bool(tensor.flags.f_contiguous and not tensor.flags.c_contiguous),
            "data": data, "indices": indices, "indptr": indptr,
            "target_position": int(positions[0])}


def _scatter_target(accumulator: complex, operation: Mapping[str, Any], values: np.ndarray) -> complex:
    """Mirror P6 cell/trace order with b_t or prior-cell accumulator already seeded."""
    total = np.complex128(accumulator)
    data = operation["data"]; indices = operation["indices"]; indptr = operation["indptr"]
    target = int(operation["target_position"])
    if values.shape != (indptr.size - 1,) or values.dtype != np.dtype(np.complex128):
        raise ValueError("V18 trace action has a wrong shape/dtype")
    for row in range(values.size):
        start, stop = int(indptr[row]), int(indptr[row + 1]); ids = indices[start:stop]
        if np.unique(ids).size != ids.size:
            raise ValueError("V18 MPC CSR row has duplicate active ids; scatter semantics are ambiguous")
        matches = np.flatnonzero(ids == target)
        if matches.size > 1:
            raise ValueError("V18 MPC row repeats selected active id")
        if matches.size:
            index = start + int(matches[0])
            product = np.conjugate(np.complex128(data[index])) * np.complex128(values[row])
            total = np.complex128(total + product)
    return complex(total)


def _atomic_npy(path: Path, value: np.ndarray) -> dict[str, Any]:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            np.save(stream, np.asarray(value, dtype=np.complex128), allow_pickle=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size,
            "shape": list(value.shape), "dtype": "complex128"}


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > MAX_REPORT_BYTES:
        raise OSError("V18 report exceeds 16 MiB evidence cap")
    with path.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())


def _validate_consumer_bindings(root: Path, contract_path: Path, window_path: Path, contract_sha: str, window_sha: str) -> None:
    for path, expected, label in ((contract_path, contract_sha, "contract"), (window_path, window_sha, "window")):
        if path.is_symlink():
            raise ValueError(f"V18 {label} path is a symlink")
        resolved = path.resolve(strict=True)
        if not resolved.is_relative_to(root) or sha256_file(resolved) != expected:
            raise ValueError(f"V18 {label} path/hash differs")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("execution_scope") != TASK41_B0_V18_SAVED_JZ_SCOPE:
        raise ValueError("V18 execution contract scope differs")
    strategy = contract.get("numerical_strategy", {})
    if strategy.get("jz_evaluation_strategy") != "binary64_real_imag_fsum":
        raise ValueError("V18 contract numerical strategy differs")


def produce_saved_jz_candidate(
    *, repo_root: Path, output_dir: Path, contract_path: Path, window_path: Path,
    contract_sha256: str, window_sha256: str,
) -> dict[str, Any]:
    root = repo_root.resolve(strict=True)
    results_root = (root / "results" / TASK41_MODEL_ID).resolve(strict=True)
    contract_path = (root / contract_path).resolve(strict=True) if not contract_path.is_absolute() else contract_path.resolve(strict=True)
    window_path = (root / window_path).resolve(strict=True) if not window_path.is_absolute() else window_path.resolve(strict=True)
    _validate_consumer_bindings(root, contract_path, window_path, contract_sha256, window_sha256)
    output_raw = output_dir if output_dir.is_absolute() else root / output_dir
    if output_raw.is_symlink():
        raise ValueError("V18 output path may not be a symlink")
    output = output_raw.resolve()
    if not output.is_relative_to(results_root) or output.exists():
        raise ValueError("V18 output must be a new directory under the fixed Task41 results tree")
    receipt_started = time.perf_counter()
    reports, report_paths = _load_pinned_sources(root)
    items, groups = _build_sources(reports, report_paths)
    receipt_load_seconds = time.perf_counter() - receipt_started
    refs = _collect_refs(items, groups)
    raw_bytes = sum(int(ref["bytes"]) for ref in refs.values())
    if raw_bytes > MAX_RAW_BYTES:
        raise OSError("V18 unique input references exceed the 16 GiB per-run raw cap")
    tensor_refs = {(str(item["tensor_ref"]["path"]), str(item["tensor_ref"]["sha256"])): item["tensor_ref"] for item in items}
    unique_tensor_bytes = sum(int(ref["bytes"]) for ref in tensor_refs.values())
    max_tensor_bytes = max(int(ref["bytes"]) for ref in tensor_refs.values())
    full_j_bytes = 16 * 432 * 450 * np.dtype(np.complex128).itemsize
    correction_bytes = 16 * 432 * np.dtype(np.complex128).itemsize
    decimal_scratch_bytes = 16 * 1024**2
    extraction_scratch_bytes = 3 * max_tensor_bytes + 2 * (432 * 450 * np.dtype(np.complex128).itemsize)
    runtime_allowance_bytes = 512 * 1024**2
    workspace_parts = {
        "all_unique_source_references_resident_upper": raw_bytes,
        "all_16_materialized_full_J_arrays": full_j_bytes,
        "all_16_candidate_corrections": correction_bytes,
        "one_row_decimal_reference_terms_and_temporaries": decimal_scratch_bytes,
        "tensor_extraction_and_advanced_indexing_scratch": extraction_scratch_bytes,
        "python_numpy_runtime_allowance": runtime_allowance_bytes,
        "unique_oriented_tensor_bytes_included_in_raw_references": unique_tensor_bytes,
    }
    planned_workspace = sum(value for key, value in workspace_parts.items() if key != "unique_oriented_tensor_bytes_included_in_raw_references")
    if planned_workspace > MAX_WORKING_BYTES:
        raise OSError("V18 explicitly accounted planned working set exceeds 4 GiB cap")
    if shutil.disk_usage(output.parent if output.parent.exists() else results_root).free < MIN_FREE_BYTES:
        raise OSError("V18 free-space floor of 2 GiB is not met")
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.stage-", dir=output.parent))
    cache: dict[tuple[str, str], np.ndarray] = {}
    operations: dict[tuple[str, int, int, str], dict[str, Any]] = {}
    corrections: dict[tuple[str, int, int, str], np.ndarray] = {}
    started = time.perf_counter()
    timings = {
        "pinned_receipt_load_hash_seconds": receipt_load_seconds,
        "input_array_hash_load_and_full_J_extract_seconds": 0.0,
        "historical_BLAS_Jz_seconds": 0.0,
        "candidate_shared_Jz_core_seconds": 0.0,
        "candidate_array_and_report_save_seconds": 0.0,
        "replay_S_action_hash_load_seconds": 0.0,
        "production_order_scatter_seconds": 0.0,
        "replay_report_save_seconds": 0.0,
    }
    durable = False
    try:
        records: list[dict[str, Any]] = []
        for item in items:
            input_started = time.perf_counter()
            operation = _load_operation(item, results_root=results_root, cache=cache)
            timings["input_array_hash_load_and_full_J_extract_seconds"] += time.perf_counter() - input_started
            blas_started = time.perf_counter()
            historical = -(operation["J"] @ operation["z"])
            timings["historical_BLAS_Jz_seconds"] += time.perf_counter() - blas_started
            if not np.array_equal(operation["baseline"], historical):
                raise ValueError("V18 saved old correction is not exactly the frozen BLAS -(J @ z)")
            key = (item["star"], int(item["cell_index"]), int(item["column_index"]), item["state"])
            operations[key] = operation
            core_started = time.perf_counter()
            correction = task41_p0_v18_evaluate_saved_jz_candidate(operation["J"], operation["z"])
            timings["candidate_shared_Jz_core_seconds"] += time.perf_counter() - core_started
            corrections[key] = correction
            basename = f"correction_{item['star']}_cell{item['cell_index']}_col{item['column_index']}_{item['state']}.npy"
            save_started = time.perf_counter()
            correction_ref = _atomic_npy(stage / basename, correction)
            timings["candidate_array_and_report_save_seconds"] += time.perf_counter() - save_started
            correction_ref["path"] = str(output / basename)
            records.append({
                "star": item["star"], "state": item["state"],
                "cell_index": item["cell_index"], "column_index": item["column_index"],
                "selected_active_row": item["selected_active_row"],
                "selected_original_row": item["selected_original_row"],
                "source_node": item["source_node"], "tensor_ref": item["tensor_ref"],
                "map_refs": item["map_refs"], "z_ref": item["z_ref"],
                "baseline_ref": item["baseline_ref"],
                "source_tensor_shape": [882, 882], "source_tensor_dtype": "complex128",
                "source_tensor_layout": "fortran" if operation["tensor_fortran_order"] else "c",
                "J_shape": [432, 450], "J_layout": "c", "z_unchanged": True,
                "baseline_blas_reproduced": True, "candidate_correction": correction_ref,
                "factorization_count": 0, "getrs_count": 0, "native_fe_action_count": 0,
            })
        evidence = {
            "schema": SCHEMA, "status": "CANDIDATE_OUTPUT_SAVED_PENDING_REPLAY",
            "consumer_contract_sha256": contract_sha256, "consumer_window_sha256": window_sha256,
            "source_reports": {key: {"path": report_paths[key], "sha256": SOURCE_BINDINGS[key][1]} for key in SOURCE_BINDINGS},
            "complete_jz_input_count": 16, "new_correction_count": 16,
            "jz_evaluation_strategy": "binary64_real_imag_fsum",
            "candidate_inputs": records, "unique_bound_source_bytes": raw_bytes,
            "campaign_raw_evidence_accounting": "Enforced separately by saved_diagnostics_budget_check in the service receipt; this is the unique byte sum of this worker's bound references only.",
            "planned_working_set_upper_bytes": planned_workspace,
            "factorization_count": 0, "getrs_count": 0, "native_fe_action_count": 0,
            "global_qualified": False, "official_result": False,
            "scientific_qualified": False, "full_owner_unlocked": False,
        }
        candidate_path = stage / "task41_p0_v18_saved_jz_candidate.json"
        save_started = time.perf_counter()
        _atomic_json(candidate_path, evidence)
        timings["candidate_array_and_report_save_seconds"] += time.perf_counter() - save_started
        evidence_bytes = sum(path.stat().st_size for path in stage.iterdir() if path.is_file())
        if evidence_bytes > MAX_REPORT_BYTES:
            raise OSError("V18 candidate output package exceeds 16 MiB evidence cap")
        os.replace(stage, output)
        durable = True

        replay_rows: list[dict[str, Any]] = []
        for group in groups:
            star = str(group["star"]); state = str(group["state"]); column = int(group["column_index"])
            b_t = _pair(group["b_t"], "b_t"); b_alpha = _pair(group["b_alpha"], "B-alpha")
            saved_y = _pair(group["saved_y"], "saved_y"); saved_g = _pair(group["saved_g"], "saved_g")
            replay_y = np.complex128(0.0 + 0.0j)
            baseline_g = np.complex128(b_t); candidate_g = np.complex128(b_t)
            for cell in group["cell_order"]:
                input_state = "initial" if star == "v17" and state == "initial" else "final"
                key = (star, int(cell), column, input_state); operation = operations[key]
                load_started = time.perf_counter()
                s_action = np.asarray(_load_array_ref(
                    group["s_action_refs"][str(cell)], results_root=results_root, cache=cache, label="saved S-action"), dtype=np.complex128)
                timings["replay_S_action_hash_load_seconds"] += time.perf_counter() - load_started
                if s_action.shape != (432,) or not np.isfinite(s_action).all():
                    raise ValueError("V18 saved S-action must be finite complex128 length 432")
                scatter_started = time.perf_counter()
                replay_y = np.complex128(_scatter_target(replay_y, operation, s_action))
                baseline_g = np.complex128(_scatter_target(baseline_g, operation, operation["baseline"]))
                candidate_g = np.complex128(_scatter_target(candidate_g, operation, corrections[key]))
                timings["production_order_scatter_seconds"] += time.perf_counter() - scatter_started
            replay_y = np.complex128(replay_y + np.complex128(b_alpha))
            if complex(replay_y) != saved_y:
                raise ValueError(f"V18 baseline S-action/B-alpha replay differs for {star}/{state}/c{column}")
            if complex(baseline_g) != saved_g:
                raise ValueError(f"V18 baseline correction scatter differs for {star}/{state}/c{column}")
            replay_rows.append({
                "star": star, "state": state, "source_state": group.get("source_state"),
                "column_index": column, "cell_order": group["cell_order"],
                "selected_active_row": group["selected_active_row"],
                "selected_original_row": group["selected_original_row"],
                "source_node": group["source_node"], "b_t": group["b_t"],
                "b_alpha_once": group["b_alpha"], "native_volume_rhs_t": group.get("native_volume_rhs_t"),
                "s_action_refs": group["s_action_refs"], "known_interior_refs": group.get("known_interior_refs", {}),
                "known_trace_refs": group.get("known_trace_refs", {}),
                "saved_y": group["saved_y"], "replayed_y": [replay_y.real, replay_y.imag],
                "baseline_g": group["saved_g"], "replayed_baseline_g": [baseline_g.real, baseline_g.imag],
                "candidate_g": [candidate_g.real, candidate_g.imag],
                "baseline_d": [(saved_y - saved_g).real, (saved_y - saved_g).imag],
                "candidate_d": [(complex(replay_y) - complex(candidate_g)).real, (complex(replay_y) - complex(candidate_g)).imag],
                "baseline_reproduced": True, "candidate_getrs_count": 0,
            })
        replay_report = {
            "schema": "task41.p0.v18.saved_jz_production_order_replay.v1",
            "status": "PRODUCTION_ORDER_REPLAYED_PENDING_INDEPENDENT_CHECK",
            "candidate_report_path": str(output / candidate_path.name),
            "candidate_report_sha256": sha256_file(output / candidate_path.name),
            "consumer_contract_sha256": contract_sha256, "consumer_window_sha256": window_sha256,
            "production_order": "cell order; local original_trace order; E^H updates; b_t first; B-alpha once after S-action y",
            "replay": replay_rows, "timings_seconds": dict(timings),
            "getrs_count": 0, "factorization_count": 0,
            "native_fe_action_count": 0, "official_result": False, "global_qualified": False,
            "elapsed_seconds": time.perf_counter() - started,
        }
        replay_path = output / "task41_p0_v18_saved_jz_replay.json"
        replay_save_started = time.perf_counter()
        _atomic_json(replay_path, replay_report)
        timings["replay_report_save_seconds"] += time.perf_counter() - replay_save_started
        evidence_bytes = sum(path.stat().st_size for path in output.iterdir() if path.is_file())
        if evidence_bytes > MAX_REPORT_BYTES:
            raise OSError("V18 candidate and production replay package exceeds 16 MiB cap")
        dir_fd = os.open(output, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        return {
            "candidate_report_path": str(output / candidate_path.name),
            "candidate_report_sha256": sha256_file(output / candidate_path.name),
            "candidate_report_bytes": (output / candidate_path.name).stat().st_size,
            "replay_report_path": str(replay_path), "replay_report_sha256": sha256_file(replay_path),
            "new_evidence_bytes": evidence_bytes, "complete_jz_input_count": 16,
            "getrs_count": 0, "factorization_count": 0, "native_fe_action_count": 0,
            "status": "PRODUCTION_ORDER_REPLAYED_PENDING_INDEPENDENT_CHECK",
            "timings_seconds": dict(timings),
        }
    except Exception as exc:
        if not durable:
            completed_files = [path for path in stage.iterdir() if path.is_file()]
            if completed_files and not output.exists():
                partial = {
                    "schema": "task41.p0.v18.saved_jz_partial_output.v1",
                    "status": "PARTIAL_OUTPUT_RETAINED_NOT_A_CANDIDATE",
                    "consumer_contract_sha256": contract_sha256,
                    "consumer_window_sha256": window_sha256,
                    "completed_file_names": sorted(path.name for path in completed_files),
                    "completed_file_bytes": sum(path.stat().st_size for path in completed_files),
                    "failure_type": type(exc).__name__,
                    "failure_message": str(exc)[:1000],
                    "factorization_count": 0, "getrs_count": 0,
                    "native_fe_action_count": 0, "official_result": False,
                }
                try:
                    _atomic_json(stage / "task41_p0_v18_partial_output.json", partial)
                    os.replace(stage, output)
                    durable = True
                except Exception:
                    # Keep the staging directory on disk for forensic inspection.
                    pass
            elif not completed_files:
                shutil.rmtree(stage, ignore_errors=True)
        raise

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--contract-path", type=Path, required=True)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--window-path", type=Path, required=True)
    parser.add_argument("--window-sha256", required=True)
    args = parser.parse_args(argv)
    result = produce_saved_jz_candidate(
        repo_root=Path(__file__).resolve().parents[2], output_dir=args.output_dir,
        contract_path=args.contract_path, window_path=args.window_path,
        contract_sha256=args.contract_sha256, window_sha256=args.window_sha256,
    )
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
