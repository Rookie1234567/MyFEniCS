"""Independent saved-Jz checker; it does not import or call the producer evaluator."""
from __future__ import annotations

import argparse
from decimal import Decimal, localcontext
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any, Mapping

import numpy as np

from src.runners.task41_p0_contract import TASK41_B0_V18_SAVED_JZ_SCOPE, TASK41_MODEL_ID

SCHEMA = "task41.p0.v18.saved_jz_independent_check.v1"
MAX_REPORT_BYTES = 16 * 1024**2
MAX_RAW_BYTES = 16 * 1024**3
SOURCE_BINDINGS: dict[str, tuple[str, str]] = {
    "v17": ("results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/7d12b524c385f3d211579a5b49772f36b4e0f1198e9364a49a0afc2733dbbc54/selected_incident_replay/attempt04/task41_p0_v17_selected_two_cell_worker.json", "4e6fce6680a0bb304ed0370542f8b5c6003d39940d94ff3e54f19322aeb1709b"),
    "v14_v11": ("results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/4f5d35994e2034c7128a87528303b87892c5563beddc2363e511d1c26dd2d47c/selected_incident_replay/attempt01/candidate/task41_p0_v14_saved_rhs_candidate.json", "a0ed3dd42129705e4806092d611c559403b832862eb3f6ee54a90880ea0f8f19"),
    "v14_v8": ("results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/4f5d35994e2034c7128a87528303b87892c5563beddc2363e511d1c26dd2d47c/selected_incident_replay/attempt04/candidate/task41_p0_v14_saved_rhs_candidate.json", "e65f3471351f51cc7b7033718af3ae2876096c20f124cefd8566483cb14248f7"),
    "v11": ("results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/4fc153c4e0526a21eb01aa3d6e5c774af7c74a849a3461b676e7ffdf214debc6/selected_incident_replay/attempt03/task41_p0_v11_selected_trace_candidate_replay.json", "2463e322ea72160bfcca7f3345d149ab20e5b017982f1f9ed55010df0afa9876"),
    "v11_metadata": ("results/task41extra_phi90_p50x50_g17x20/task41_p0_saved_diagnostics_6h/bc646b17157eed567e2c5391df79e4eda681ab4028f9e86901e8c7fcfd9222b4/selected_incident_replay/attempt02/task41_p0_v8_selected_trace_star_metadata.json", "332baa3a5253a8322b56615c7fe087e401f909c3c889fa048fccc3f9f2b9fcd3"),
    "v8": ("results/task41extra_phi90_p50x50_g17x20/task41_b0_v8_selected_star_35fd1bbf_20261021T072801Z_attempt1/task41_p0_v8_selected_trace_star_audit.json", "1bdd07ac38bce95d58a153bacdca0de6cf5941d08d2706dc127e8b00d8e2764f"),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _pinned_json(root: Path, key: str) -> tuple[Path, dict[str, Any]]:
    rel, expected = SOURCE_BINDINGS[key]
    path = root / rel
    if path.is_symlink():
        raise ValueError(f"V18 checker {key} report is a symlink")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root) or resolved.stat().st_size > MAX_REPORT_BYTES or sha256_file(resolved) != expected:
        raise ValueError(f"V18 checker {key} report path/size/hash differs")
    value = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"V18 checker {key} report is not an object")
    return resolved, value


def _sources(root: Path) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    schemas = {
        "v17": ("task41.p0.b0.v17.selected_two_cell_worker_receipt.v1", "COMPLETED_LOCAL_SELECTED_TWO_CELL_REPLAY"),
        "v14_v11": ("task41.p0.v14.saved_same_lu_rhs_candidate.v1", "CANDIDATE_PRODUCED_PENDING_INDEPENDENT_CHECK"),
        "v14_v8": ("task41.p0.v14.saved_same_lu_rhs_candidate.v1", "CANDIDATE_PRODUCED_PENDING_INDEPENDENT_CHECK"),
        "v11": ("task41.p0.v11.selected_trace_star_candidate_replay_receipt.v1", "COMPLETED_LOCAL_CANDIDATE_REPLAY"),
        "v11_metadata": ("task41.p0.v8.selected_trace_star_metadata_only_receipt.v1", "COMPLETED_METADATA_ONLY"),
        "v8": ("task41.p0.v8.selected_trace_star_audit_receipt.v1", "COMPLETED_SELECTED_TRACE_STAR_AUDIT"),
    }
    reports: dict[str, dict[str, Any]] = {}; paths: dict[str, str] = {}
    for key in SOURCE_BINDINGS:
        path, payload = _pinned_json(root, key)
        if (payload.get("schema"), payload.get("status")) != schemas[key]:
            raise ValueError(f"V18 checker {key} schema/status differs")
        reports[key] = payload; paths[key] = str(path)
    if reports["v14_v11"].get("producer_report_sha256") != SOURCE_BINDINGS["v11"][1]:
        raise ValueError("V18 checker V14/V11 source binding differs")
    if reports["v14_v8"].get("producer_report_sha256") != SOURCE_BINDINGS["v11"][1] or reports["v14_v8"].get("star_producer_report_sha256") != SOURCE_BINDINGS["v8"][1]:
        raise ValueError("V18 checker V14/V8 source binding differs")
    if reports["v17"].get("consumer_window_sha256") != "7d12b524c385f3d211579a5b49772f36b4e0f1198e9364a49a0afc2733dbbc54":
        raise ValueError("V18 checker V17 source window differs")
    if reports["v14_v11"].get("consumer_window_sha256") != "4f5d35994e2034c7128a87528303b87892c5563beddc2363e511d1c26dd2d47c":
        raise ValueError("V18 checker V14 source window differs")
    meta = Path(str(reports["v11"].get("selected_metadata_report_path", "")))
    if meta.resolve(strict=True) != (root / SOURCE_BINDINGS["v11_metadata"][0]).resolve(strict=True):
        raise ValueError("V18 checker V11 map report path differs")
    return reports, paths


def _expected(root: Path, reports: Mapping[str, Mapping[str, Any]]) -> tuple[dict[tuple[str, int, int, str], dict[str, Any]], dict[tuple[str, str, int], dict[str, Any]]]:
    """Independently bind accepted source records to each item and replay state."""
    items: dict[tuple[str, int, int, str], dict[str, Any]] = {}
    groups: dict[tuple[str, str, int], dict[str, Any]] = {}
    cb = reports["v17"]["selected_two_cell_candidate_callback"]
    if cb.get("scope", {}).get("selected_active_row") != 1_622_464 or cb.get("scope", {}).get("selected_original_row") != 5_218_672:
        raise ValueError("V18 checker V17 selected row differs")
    for cell_record in cb["cells"]:
        cell = int(cell_record["cell_index"])
        if cell not in (7873, 8014):
            raise ValueError("V18 checker has unexpected V17 cell")
        if len(cell_record["columns"]) != 2:
            raise ValueError("V18 checker V17 cell row must preserve two ordered columns")
        local_columns = {index: row for index, row in enumerate(cell_record["columns"])}
        if any(int(row.get("cell_index", cell)) != cell for row in local_columns.values()):
            raise ValueError("V18 checker V17 local column record is attached to another cell")
        for col in (0, 1):
            local = local_columns[col]; rhs = local["rhs_artifacts"]
            for state, zfield, basefield in (("initial", "z0", "z0_minus_Jz"), ("final", "final_z", "returned_minus_Jz")):
                items[("v17", cell, col, state)] = {
                    "tensor_ref": cell_record["candidate_artifacts"]["oriented_tensor"],
                    "map_refs": cell_record["fresh_map_artifacts"], "z_ref": rhs[zfield],
                    "baseline_ref": rhs[basefield], "s_action_ref": local["S_action_artifact"],
                    "active": 1_622_464, "original": 5_218_672,
                    "source_node": {"report_sha256": SOURCE_BINDINGS["v17"][1], "cell_index": cell, "column_index": col, "state_key": zfield},
                }
    callback_columns = {int(row["column"]): row for row in cb["columns"]}
    for col in (0, 1):
        base = callback_columns[col]
        for state, yfield, gfield in (("initial", "saved_y9", "saved_g9"), ("final", "saved_y15", "saved_g15")):
            groups[("v17", state, col)] = {
                "star": "v17", "state": state, "column_index": col,
                "cells": [7873, 8014], "active": 1_622_464, "original": 5_218_672,
                "b_t": base["native_rhs_t"], "native_volume_rhs_t": base["native_volume_rhs_t"], "b_alpha": base["b_alpha_t"],
                "saved_y": base[yfield], "saved_g": base[gfield],
                "s_actions": {str(c): next(row for row in cb["cells"] if int(row["cell_index"]) == c)["columns"][col]["S_action_artifact"] for c in (7873, 8014)},
                "known_interior_refs": {str(c): next(row for row in cb["cells"] if int(row["cell_index"]) == c)["columns"][col]["known_interior_local_artifact"] for c in (7873, 8014)},
                "known_trace_refs": {str(c): next(row for row in cb["cells"] if int(row["cell_index"]) == c)["columns"][col]["known_trace_local_artifact"] for c in (7873, 8014)},
                "source_node": {"report_sha256": SOURCE_BINDINGS["v17"][1], "column_index": col, "state_key": yfield},
            }
    map11 = {int(row["cell_index"]): row["arrays"] for row in reports["v11_metadata"]["selected_trace_star_metadata_only"]["selected_cells"]}
    map8 = {int(cell): row["arrays"] for cell, row in reports["v8"]["selected_trace_star_metadata"]["cell_artifacts"].items() if str(cell).isdigit()}
    for star, cells, active, original, meta in (("v14_v11", (360, 446), 87_567, 250_113, map11), ("v14_v8", (23352, 23493), 4_766_937, 15_440_235, map8)):
        meta_key = "v11_metadata" if star == "v14_v11" else "v8"
        source = reports[star]
        rhs = {(int(r["cell_index"]), int(r["column"])): r for r in source["candidate_rhs"]}
        rows = source["production_order_rows"]
        expected_states = {None} if star == "v14_v11" else {"j0", "j3"}
        seen: set[tuple[int, str | None]] = set()
        for row_index, row in enumerate(rows):
            col = int(row["column"]); source_state = row.get("state")
            key = (col, source_state)
            if key in seen or source_state not in expected_states or row.get("incident_cell_order") != list(cells):
                raise ValueError(f"V18 checker {star} production row identity differs")
            seen.add(key)
            if row.get("selected_active_row") != active or row.get("selected_original_row") != original:
                raise ValueError(f"V18 checker {star} row id differs")
            label = "final" if source_state is None else str(source_state)
            actions = row["y_cell_s_action_sources"]
            if len(actions) != len(cells):
                raise ValueError(f"V18 checker {star} S-action binding count differs")
            group = {"cells": list(cells), "active": active, "original": original,
                     "b_t": row["base_b_t"], "b_alpha": row["b_alpha_row_used_once"],
                     "saved_y": row["saved_y"], "saved_g": row["candidate_g_actual_returned_correction_cell_order"],
                     "s_actions": {str(cell): action for cell, action in zip(cells, actions, strict=True)},
                     "source_report_sha256": SOURCE_BINDINGS[star][1], "source_row_index": row_index,
                     "source_node": {"report_sha256": SOURCE_BINDINGS[star][1], "production_order_row": row_index, "metadata_report_sha256": SOURCE_BINDINGS[meta_key][1]}}
            groups[(star, label, col)] = group
            for cell, action in zip(cells, actions, strict=True):
                source_rhs = rhs.get((cell, col))
                if source_rhs is None:
                    raise ValueError(f"V18 checker {star} missing fixed RHS cell/column")
                item_key = (star, cell, col, "final")
                expected_item = {"tensor_ref": source_rhs["oriented_tensor"],
                                 "map_refs": meta[cell], "z_ref": source_rhs["final_z"],
                                 "baseline_ref": source_rhs["returned_correction"],
                                 "active": active, "original": original,
                                 "source_node": {"report_sha256": SOURCE_BINDINGS[star][1], "candidate_rhs_key": [cell, col], "metadata_report_sha256": SOURCE_BINDINGS[meta_key][1]}}
                existing = items.get(item_key)
                if existing is not None and any(existing[k] != expected_item[k] for k in expected_item):
                    raise ValueError("V18 checker j0/j3 do not share an identical final J/z binding")
                items[item_key] = expected_item
        if seen != {(col, state) for col in (0, 1) for state in expected_states}:
            raise ValueError(f"V18 checker {star} production row coverage differs")
    expected_keys = {
        ("v17", c, col, state) for c in (7873, 8014) for col in (0, 1) for state in ("initial", "final")
    } | {
        (star, c, col, "final") for star, cells in (("v14_v11", (360, 446)), ("v14_v8", (23352, 23493))) for c in cells for col in (0, 1)
    }
    if set(items) != expected_keys or len(items) != 16:
        raise ValueError("V18 checker exact 16 input keys differ")
    return items, groups


def _pair(value: Any, label: str) -> complex:
    if not isinstance(value, list) or len(value) != 2 or any(type(x) not in (int, float) or not math.isfinite(float(x)) for x in value):
        raise ValueError(f"V18 checker {label} pair is malformed")
    return complex(float(value[0]), float(value[1]))


def _array(ref: Any, *, root: Path, cache: dict[tuple[str, str], np.ndarray]) -> np.ndarray:
    if not isinstance(ref, Mapping):
        raise ValueError("V18 checker array ref is not a mapping")
    raw = Path(str(ref.get("path", "")))
    if not raw.is_absolute() or raw.is_symlink():
        raise ValueError("V18 checker source array path is not a regular absolute path")
    path = raw.resolve(strict=True); digest = ref.get("sha256")
    if not path.is_relative_to(root) or type(ref.get("bytes")) is not int or path.stat().st_size != ref["bytes"] or not isinstance(digest, str):
        raise ValueError("V18 checker source array path/size/hash metadata malformed")
    key = (str(path), digest)
    if key not in cache:
        if sha256_file(path) != digest:
            raise ValueError("V18 checker source array SHA-256 differs")
        arr = np.load(path, mmap_mode="r", allow_pickle=False)
        if arr.dtype.hasobject or list(arr.shape) != ref.get("shape") or str(arr.dtype) != ref.get("dtype"):
            raise ValueError("V18 checker source array shape/dtype differs")
        cache[key] = arr
    return cache[key]


def _tensor_maps(expected: Mapping[str, Any], *, root: Path, cache: dict[tuple[str, str], np.ndarray]) -> dict[str, Any]:
    tensor = _array(expected["tensor_ref"], root=root, cache=cache)
    maps = expected["map_refs"]
    interior = np.asarray(_array(maps["interior_positions"], root=root, cache=cache), dtype=np.int64)
    trace = np.asarray(_array(maps["trace_positions"], root=root, cache=cache), dtype=np.int64)
    if tensor.shape != (882, 882) or tensor.dtype != np.dtype(np.complex128) or interior.shape != (450,) or trace.shape != (432,) or not np.array_equal(np.sort(np.r_[interior, trace]), np.arange(882)):
        raise ValueError("V18 checker actual full tensor or I/T map invalid")
    J = np.asarray(tensor[np.ix_(trace, interior)], dtype=np.complex128)
    z = np.asarray(_array(expected["z_ref"], root=root, cache=cache), dtype=np.complex128)
    baseline = np.asarray(_array(expected["baseline_ref"], root=root, cache=cache), dtype=np.complex128)
    if J.shape != (432, 450) or z.shape != (450,) or baseline.shape != (432,) or not np.isfinite(J).all() or not np.isfinite(z).all() or not np.isfinite(baseline).all():
        raise ValueError("V18 checker J/z/baseline dimensions or finite values invalid")
    if not np.array_equal(baseline, -(J @ z)):
        raise ValueError("V18 checker frozen correction is not exact historical BLAS -(J @ z)")
    active = _array(maps["active_ids"], root=root, cache=cache)
    data = np.asarray(_array(maps["trace_expansion_data"], root=root, cache=cache), dtype=np.complex128)
    indices = np.asarray(_array(maps["trace_expansion_indices"], root=root, cache=cache), dtype=np.int64)
    indptr = np.asarray(_array(maps["trace_expansion_indptr"], root=root, cache=cache), dtype=np.int64)
    if active.ndim != 1 or active.dtype.kind not in "iu" or data.ndim != 1 or indices.shape != data.shape or indptr.shape != (432 + 1,) or indptr[0] != 0 or indptr[-1] != data.size or np.any(indptr[1:] < indptr[:-1]) or np.any(indices < 0) or np.any(indices >= active.size) or not np.isfinite(data).all():
        raise ValueError("V18 checker actual MPC expansion CSR invalid")
    positions = np.flatnonzero(active == int(expected["active"]))
    if positions.size != 1:
        raise ValueError("V18 checker selected active row absent or duplicated")
    return {"J": J, "z": z, "baseline": baseline, "active": active, "data": data,
            "indices": indices, "indptr": indptr, "target": int(positions[0])}


def _decimal_jz_row(J: np.ndarray, z: np.ndarray, row: int, *, precision: int) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    real_rounded: list[Decimal] = []; imag_rounded: list[Decimal] = []
    with localcontext() as ctx:
        ctx.prec = precision
        real_exact = Decimal(0); imag_exact = Decimal(0)
        for col in range(z.size):
            a = float(J[row, col].real); b = float(J[row, col].imag)
            x = float(z[col].real); y = float(z[col].imag)
            rx, by, ay, bx = a * x, b * y, a * y, b * x
            real_rounded.extend((Decimal.from_float(rx), Decimal.from_float(-by)))
            imag_rounded.extend((Decimal.from_float(ay), Decimal.from_float(bx)))
            da, db = Decimal.from_float(a), Decimal.from_float(b)
            dx, dy = Decimal.from_float(x), Decimal.from_float(y)
            real_exact += da * dx - db * dy
            imag_exact += da * dy + db * dx
        rounded_real = sum(real_rounded, Decimal(0)); rounded_imag = sum(imag_rounded, Decimal(0))
        return -rounded_real, -rounded_imag, -real_exact, -imag_exact


def _measure_vector(J: np.ndarray, z: np.ndarray, actual: np.ndarray, baseline: np.ndarray, selected_rows: set[int]) -> dict[str, Any]:
    """Check every real/imag component independently against two Decimal references."""
    sums = {
        "candidate_rounded_real": Decimal(0), "candidate_rounded_imag": Decimal(0),
        "candidate_full_real": Decimal(0), "candidate_full_imag": Decimal(0),
        "baseline_full_real": Decimal(0), "baseline_full_imag": Decimal(0),
        "reference_delta_real": Decimal(0), "reference_delta_imag": Decimal(0),
    }
    maxima = {name: Decimal(0) for name in sums}
    rows: list[dict[str, Any]] = []
    key: dict[str, Any] = {}
    candidate_rounded_within_one_ulp = True
    component_regressions: list[dict[str, Any]] = []
    with localcontext() as ctx:
        ctx.prec = 100
        for row in range(J.shape[0]):
            rounded80_r, rounded80_i, full80_r, full80_i = _decimal_jz_row(J, z, row, precision=80)
            rounded100_r, rounded100_i, full100_r, full100_i = _decimal_jz_row(J, z, row, precision=100)
            ar = Decimal.from_float(float(actual[row].real)); ai = Decimal.from_float(float(actual[row].imag))
            br = Decimal.from_float(float(baseline[row].real)); bi = Decimal.from_float(float(baseline[row].imag))
            rounded_errors = (ar - rounded80_r, ai - rounded80_i)
            candidate_full_errors = (ar - full80_r, ai - full80_i)
            baseline_full_errors = (br - full80_r, bi - full80_i)
            full_ref_delta = (abs(full100_r - full80_r), abs(full100_i - full80_i))
            rounded_ref_delta = (abs(rounded100_r - rounded80_r), abs(rounded100_i - rounded80_i))
            component_ulp = (Decimal.from_float(math.ulp(float(actual[row].real))), Decimal.from_float(math.ulp(float(actual[row].imag))))
            within = (abs(rounded_errors[0]) <= component_ulp[0], abs(rounded_errors[1]) <= component_ulp[1])
            candidate_full_abs = (abs(candidate_full_errors[0]), abs(candidate_full_errors[1]))
            baseline_full_abs = (abs(baseline_full_errors[0]), abs(baseline_full_errors[1]))
            regressions: list[dict[str, Any]] = []
            for component, cand_err, base_err, delta in zip(("real", "imag"), candidate_full_abs, baseline_full_abs, full_ref_delta, strict=True):
                margin = cand_err - base_err
                # Both distances share one high-precision reference; twice the measured
                # 80-vs-100 movement is a conservative resolution envelope.
                resolution = Decimal(2) * delta
                decision = "RESOLVED_REGRESSION" if margin > resolution else "RESOLVED_IMPROVEMENT" if margin < -resolution else "INCONCLUSIVE_AT_80_VS_100_RESOLUTION"
                if decision == "RESOLVED_REGRESSION":
                    regressions.append({"component": component, "candidate_abs_error_80d": str(cand_err), "baseline_abs_error_80d": str(base_err), "candidate_minus_baseline_abs_error": str(margin), "resolution_envelope": str(resolution)})
            component_regressions.extend({"row": row, **entry} for entry in regressions)
            values = {
                "candidate_rounded_real": abs(rounded_errors[0]), "candidate_rounded_imag": abs(rounded_errors[1]),
                "candidate_full_real": candidate_full_abs[0], "candidate_full_imag": candidate_full_abs[1],
                "baseline_full_real": baseline_full_abs[0], "baseline_full_imag": baseline_full_abs[1],
                "reference_delta_real": full_ref_delta[0], "reference_delta_imag": full_ref_delta[1],
            }
            for name, value in values.items():
                sums[name] += value * value
                maxima[name] = max(maxima[name], value)
            candidate_rounded_within_one_ulp = candidate_rounded_within_one_ulp and all(within)
            row_record = {
                "row": row,
                "candidate": [float(actual[row].real), float(actual[row].imag)],
                "baseline": [float(baseline[row].real), float(baseline[row].imag)],
                "rounded_products_reference_80d": [str(rounded80_r), str(rounded80_i)],
                "stored_operands_reference_80d": [str(full80_r), str(full80_i)],
                "candidate_error_vs_rounded_products": [str(rounded_errors[0]), str(rounded_errors[1])],
                "candidate_error_vs_stored_operands": [str(candidate_full_errors[0]), str(candidate_full_errors[1])],
                "baseline_error_vs_stored_operands": [str(baseline_full_errors[0]), str(baseline_full_errors[1])],
                "component_output_ulp": [str(component_ulp[0]), str(component_ulp[1])],
                "candidate_rounded_component_within_one_ulp": list(within),
                "stored_reference_80_vs_100_abs_delta": [str(full_ref_delta[0]), str(full_ref_delta[1])],
                "rounded_reference_80_vs_100_abs_delta": [str(rounded_ref_delta[0]), str(rounded_ref_delta[1])],
                "stored_reference_resolution_by_component": [
                    "STABLE_WITHIN_HALF_OUTPUT_ULP" if full_ref_delta[i] <= component_ulp[i] / Decimal(2) else "INCONCLUSIVE_REFERENCE_PRECISION"
                    for i in (0, 1)
                ],
                "rounded_reference_resolution_by_component": [
                    "STABLE_WITHIN_HALF_OUTPUT_ULP" if rounded_ref_delta[i] <= component_ulp[i] / Decimal(2) else "INCONCLUSIVE_REFERENCE_PRECISION"
                    for i in (0, 1)
                ],
                "component_regression_vs_baseline": regressions,
            }
            rows.append(row_record)
            if row in selected_rows:
                key[str(row)] = {
                    "rounded_products_reference_100d": [str(rounded100_r), str(rounded100_i)],
                    "stored_operands_reference_100d": [str(full100_r), str(full100_i)],
                    "rounded_reference_80_vs_100_abs_delta": [str(rounded_ref_delta[0]), str(rounded_ref_delta[1])],
                    "stored_reference_80_vs_100_abs_delta": [str(full_ref_delta[0]), str(full_ref_delta[1])],
                    "component_output_ulp": [str(component_ulp[0]), str(component_ulp[1])],
                    "stored_reference_resolution_by_component": [
                        "STABLE_WITHIN_HALF_OUTPUT_ULP" if full_ref_delta[i] <= component_ulp[i] / Decimal(2) else "INCONCLUSIVE_REFERENCE_PRECISION"
                        for i in (0, 1)
                    ],
                    "candidate_error_vs_stored_operands_100d": [str(ar - full100_r), str(ai - full100_i)],
                    "baseline_error_vs_stored_operands_100d": [str(br - full100_r), str(bi - full100_i)],
                }
    l2 = {name: value.sqrt() for name, value in sums.items()}
    candidate_l2 = (l2["candidate_full_real"] ** 2 + l2["candidate_full_imag"] ** 2).sqrt()
    baseline_l2 = (l2["baseline_full_real"] ** 2 + l2["baseline_full_imag"] ** 2).sqrt()
    reference_delta_l2 = (l2["reference_delta_real"] ** 2 + l2["reference_delta_imag"] ** 2).sqrt()
    improvement_margin = baseline_l2 - candidate_l2
    reference_resolution = Decimal(2) * reference_delta_l2
    input_decision = "IMPROVED" if improvement_margin > reference_resolution else "DEGRADED" if improvement_margin < -reference_resolution else "INCONCLUSIVE_AT_80_VS_100_RESOLUTION"
    return {
        "all_432_rows_checked": True,
        "all_432_real_imag_component_errors": rows,
        "candidate_vs_rounded_binary64_products_real_l2": float(l2["candidate_rounded_real"]),
        "candidate_vs_rounded_binary64_products_imag_l2": float(l2["candidate_rounded_imag"]),
        "candidate_vs_rounded_binary64_products_real_max_abs": float(maxima["candidate_rounded_real"]),
        "candidate_vs_rounded_binary64_products_imag_max_abs": float(maxima["candidate_rounded_imag"]),
        "candidate_within_one_ulp_of_rounded_decimal_reference": candidate_rounded_within_one_ulp,
        "candidate_vs_original_stored_operands_80d_real_l2": float(l2["candidate_full_real"]),
        "candidate_vs_original_stored_operands_80d_imag_l2": float(l2["candidate_full_imag"]),
        "candidate_vs_original_stored_operands_80d_real_max_abs": float(maxima["candidate_full_real"]),
        "candidate_vs_original_stored_operands_80d_imag_max_abs": float(maxima["candidate_full_imag"]),
        "baseline_vs_original_stored_operands_80d_real_l2": float(l2["baseline_full_real"]),
        "baseline_vs_original_stored_operands_80d_imag_l2": float(l2["baseline_full_imag"]),
        "baseline_vs_original_stored_operands_80d_real_max_abs": float(maxima["baseline_full_real"]),
        "baseline_vs_original_stored_operands_80d_imag_max_abs": float(maxima["baseline_full_imag"]),
        "candidate_vs_original_stored_operands_80d_complex_l2": float(candidate_l2),
        "baseline_vs_original_stored_operands_80d_complex_l2": float(baseline_l2),
        "candidate_minus_baseline_error_l2_decision": input_decision,
        "candidate_minus_baseline_error_l2_margin": str(improvement_margin),
        "candidate_minus_baseline_error_l2_resolution_envelope": str(reference_resolution),
        "resolved_component_regressions_vs_baseline": component_regressions,
        "key_components_100d": key,
        "decimal_precision": {"all_rows": 80, "key_components": 100},
    }

def _scatter(accumulator: complex, target: int, data: np.ndarray, indices: np.ndarray, indptr: np.ndarray, values: np.ndarray) -> complex:
    total = np.complex128(accumulator)
    if values.shape != (indptr.size - 1,) or values.dtype != np.dtype(np.complex128):
        raise ValueError("V18 checker scatter operand shape/dtype differs")
    for row in range(values.size):
        first, last = int(indptr[row]), int(indptr[row + 1]); ids = indices[first:last]
        if np.unique(ids).size != ids.size:
            raise ValueError("V18 checker MPC row has duplicate active ids")
        found = np.flatnonzero(ids == target)
        if found.size > 1:
            raise ValueError("V18 checker selected active id repeats in one MPC row")
        if found.size:
            product = np.conjugate(np.complex128(data[first + int(found[0])])) * np.complex128(values[row])
            total = np.complex128(total + product)
    return complex(total)


def _decimal_scatter(target: int, data: np.ndarray, indices: np.ndarray, indptr: np.ndarray, values: np.ndarray) -> tuple[Decimal, Decimal]:
    real = Decimal(0); imag = Decimal(0)
    for row in range(values.size):
        first, last = int(indptr[row]), int(indptr[row + 1]); ids = indices[first:last]
        if np.unique(ids).size != ids.size:
            raise ValueError("V18 checker Decimal MPC row has duplicate active ids")
        found = np.flatnonzero(ids == target)
        if found.size:
            k = first + int(found[0]); c = np.complex128(data[k]); v = np.complex128(values[row])
            a, b, x, y = (Decimal.from_float(float(c.real)), Decimal.from_float(float(c.imag)), Decimal.from_float(float(v.real)), Decimal.from_float(float(v.imag)))
            with localcontext() as ctx:
                ctx.prec = 80
                real += a * x + b * y
                imag += a * y - b * x
    return real, imag


def _decimal_pair(value: Any, label: str) -> tuple[Decimal, Decimal]:
    pair = _pair(value, label)
    return Decimal.from_float(pair.real), Decimal.from_float(pair.imag)


def _decimal_matvec_row(J: np.ndarray, vector: np.ndarray, row: int, *, subtract: np.ndarray | None = None) -> tuple[Decimal, Decimal]:
    real = Decimal(0); imag = Decimal(0)
    with localcontext() as ctx:
        ctx.prec = 100
        for col in range(vector.size):
            a = Decimal.from_float(float(J[row, col].real)); b = Decimal.from_float(float(J[row, col].imag))
            x = Decimal.from_float(float(vector[col].real)); y = Decimal.from_float(float(vector[col].imag))
            if subtract is not None:
                x -= Decimal.from_float(float(subtract[col].real))
                y -= Decimal.from_float(float(subtract[col].imag))
            real += a * x - b * y
            imag += a * y + b * x
    return real, imag


def _target_coefficients(op: Mapping[str, Any]) -> list[tuple[int, complex]]:
    target = int(op["target"]); result: list[tuple[int, complex]] = []
    for row in range(int(op["indptr"].size) - 1):
        first, last = int(op["indptr"][row]), int(op["indptr"][row + 1])
        ids = op["indices"][first:last]
        if np.unique(ids).size != ids.size:
            raise ValueError("V18 signed-D MPC row contains duplicate active ids")
        matches = np.flatnonzero(ids == target)
        if matches.size > 1:
            raise ValueError("V18 signed-D MPC row repeats selected active id")
        if matches.size:
            result.append((row, complex(np.complex128(op["data"][first + int(matches[0])]))))
    return result


def _decimal_qh_jv(op: Mapping[str, Any], vector: np.ndarray, *, subtract: np.ndarray | None = None) -> tuple[Decimal, Decimal]:
    total_r = Decimal(0); total_i = Decimal(0)
    with localcontext() as ctx:
        ctx.prec = 100
        for row, q in _target_coefficients(op):
            jr, ji = _decimal_matvec_row(op["J"], vector, row, subtract=subtract)
            qr = Decimal.from_float(q.real); qi = Decimal.from_float(q.imag)
            total_r += qr * jr + qi * ji
            total_i += qr * ji - qi * jr
    return total_r, total_i


def _decimal_qh_candidate_minus_jz(op: Mapping[str, Any], positive_candidate_jz: np.ndarray) -> tuple[Decimal, Decimal]:
    total_r = Decimal(0); total_i = Decimal(0); z = op["z"]
    with localcontext() as ctx:
        ctx.prec = 100
        for row, q in _target_coefficients(op):
            jr, ji = _decimal_matvec_row(op["J"], z, row)
            pr = Decimal.from_float(float(positive_candidate_jz[row].real)); pi = Decimal.from_float(float(positive_candidate_jz[row].imag))
            qr = Decimal.from_float(q.real); qi = Decimal.from_float(q.imag)
            dr = pr - jr; di = pi - ji
            total_r += qr * dr + qi * di
            total_i += qr * di - qi * dr
    return total_r, total_i


def _decimal_pair_add(left: tuple[Decimal, Decimal], right: tuple[Decimal, Decimal]) -> tuple[Decimal, Decimal]:
    with localcontext() as ctx:
        ctx.prec = 100
        return left[0] + right[0], left[1] + right[1]


def _decimal_pair_sub(left: tuple[Decimal, Decimal], right: tuple[Decimal, Decimal]) -> tuple[Decimal, Decimal]:
    with localcontext() as ctx:
        ctx.prec = 100
        return left[0] - right[0], left[1] - right[1]


def _decimal_pair_text(value: tuple[Decimal, Decimal]) -> list[str]:
    return [str(value[0]), str(value[1])]


def _signed_main_star_decomposition(
    *, group: Mapping[str, Any], ops: Mapping[tuple[str, int, int, str], Mapping[str, Any]],
    replay: Mapping[str, Any], results_root: Path, cache: dict[tuple[str, str], np.ndarray],
) -> dict[str, Any]:
    """Reconstruct signed main-star D terms from pinned J, z, u_i and saved outputs."""
    if group.get("star") != "v17" or group.get("state") != "final":
        raise ValueError("V18 signed-D is defined only for final V17 main-star inputs")
    col = int(group["column_index"]); local_terms = (Decimal(0), Decimal(0)); fixed_terms = (Decimal(0), Decimal(0))
    jeval_candidate = (Decimal(0), Decimal(0)); jeval_baseline = (Decimal(0), Decimal(0)); s_term = (Decimal(0), Decimal(0))
    cell_rows: list[dict[str, Any]] = []
    for cell in group["cells"]:
        cell_key = str(cell)
        op = ops[("v17", int(cell), col, "final")]
        u_ref = group["known_interior_refs"].get(cell_key); t_ref = group["known_trace_refs"].get(cell_key)
        u_i = np.asarray(_array(u_ref, root=results_root, cache=cache), dtype=np.complex128)
        t_i = np.asarray(_array(t_ref, root=results_root, cache=cache), dtype=np.complex128)
        if u_i.shape != (450,) or not np.isfinite(u_i).all() or t_i.shape != (432,) or not np.isfinite(t_i).all():
            raise ValueError("V18 signed-D source known-interior/trace vectors have invalid shape or values")
        if np.any(t_i != 0):
            raise ValueError("V18 main-star fixed trace is not elementwise zero; signed-D formula is not applicable")
        s_action = np.asarray(_array(group["s_actions"][cell_key], root=results_root, cache=cache), dtype=np.complex128)
        if s_action.shape != (432,) or not np.isfinite(s_action).all() or np.any(s_action != 0):
            raise ValueError("V18 main-star zero trace does not reproduce an all-zero saved S action")
        local_cell = _decimal_qh_jv(op, u_i)
        fixed_cell = _decimal_qh_jv(op, op["z"], subtract=u_i)
        candidate_jz_cell = _decimal_qh_candidate_minus_jz(op, -np.asarray(op["candidate"], dtype=np.complex128))
        baseline_jz_cell = _decimal_qh_candidate_minus_jz(op, -np.asarray(op["baseline"], dtype=np.complex128))
        local_terms = _decimal_pair_add(local_terms, local_cell)
        fixed_terms = _decimal_pair_add(fixed_terms, fixed_cell)
        jeval_candidate = _decimal_pair_add(jeval_candidate, candidate_jz_cell)
        jeval_baseline = _decimal_pair_add(jeval_baseline, baseline_jz_cell)
        cell_s = _decimal_scatter(op["target"], op["data"], op["indices"], op["indptr"], s_action)
        s_term = _decimal_pair_add(s_term, cell_s)
        cell_rows.append({"cell_index": cell, "known_interior_ref": u_ref, "known_trace_ref": t_ref,
                          "J_shape": [432, 450], "trace_is_elementwise_zero": True,
                          "saved_S_action_is_elementwise_zero": True,
                          "q_H_J_u_i": _decimal_pair_text(local_cell),
                          "q_H_J_z_minus_u_i": _decimal_pair_text(fixed_cell),
                          "q_H_candidate_minus_J_z": _decimal_pair_text(candidate_jz_cell)})
    b_t_full = _decimal_pair(group["b_t"], "native_rhs_t")
    b_t_volume = _decimal_pair(group["native_volume_rhs_t"], "native_volume_rhs_t")
    b_alpha = _decimal_pair(group["b_alpha"], "B-alpha")
    local_terms = _decimal_pair_sub(local_terms, b_t_volume)
    rhs_adjustment = _decimal_pair_sub(b_alpha, _decimal_pair_sub(b_t_full, b_t_volume))
    candidate_d = _decimal_pair(replay["candidate_d"], "candidate d")
    baseline_d = _decimal_pair(replay["baseline_d"], "baseline d")

    def closeout(observed: tuple[Decimal, Decimal], exact_replay: tuple[Decimal, Decimal], jeval: tuple[Decimal, Decimal]) -> dict[str, Any]:
        subtotal = _decimal_pair_add(_decimal_pair_add(local_terms, fixed_terms), _decimal_pair_add(jeval, s_term))
        subtotal = _decimal_pair_add(subtotal, rhs_adjustment)
        split_identity_residual = _decimal_pair_sub(exact_replay, subtotal)
        # This epsilon comes from a separate high-precision replay of the original
        # binary64 scatter operands; it is not defined as observed minus subtotal.
        epsilon = _decimal_pair_sub(observed, exact_replay)
        reconstructed = _decimal_pair_add(_decimal_pair_add(subtotal, split_identity_residual), epsilon)
        closure = _decimal_pair_sub(observed, reconstructed)
        return {"D_local_native": _decimal_pair_text(local_terms),
                "D_fixed_solve": _decimal_pair_text(fixed_terms),
                "D_J_evaluation": _decimal_pair_text(jeval),
                "S_action_contribution": _decimal_pair_text(s_term),
                "epsilon_B_RHS": _decimal_pair_text(rhs_adjustment),
                "formula_split_residual_vs_independent_decimal_replay": _decimal_pair_text(split_identity_residual),
                "independent_decimal_production_order_replay_d": _decimal_pair_text(exact_replay),
                "epsilon_scatter_subtraction": _decimal_pair_text(epsilon),
                "observed_d_binary64": _decimal_pair_text(observed),
                "reconstructed_d": _decimal_pair_text(reconstructed),
                "closure_residual": _decimal_pair_text(closure)}

    return {
        "definition": "D_local/native=sum_cell(q^H J u_i)-b_t,volume; D_fixed_solve=sum_cell(q^H J(z-u_i)); D_J_evaluation=sum_cell(q^H((-correction)-Jz)); epsilon_B_RHS=b_alpha-(b_t_full-b_t_volume); epsilon_scatter_subtraction is the signed remainder from production-order replay",
        "source_report_node": group["source_node"], "column_index": col,
        "b_t_full": group["b_t"], "b_t_volume": group["native_volume_rhs_t"], "b_alpha": group["b_alpha"],
        "cells": cell_rows,
        "baseline_historical_BLAS": closeout(
            baseline_d,
            (Decimal(str(replay["exact_baseline_d_decimal"][0])), Decimal(str(replay["exact_baseline_d_decimal"][1]))),
            jeval_baseline,
        ),
        "candidate_fsum": closeout(
            candidate_d,
            (Decimal(str(replay["exact_candidate_d_decimal"][0])), Decimal(str(replay["exact_candidate_d_decimal"][1]))),
            jeval_candidate,
        ),
        "independent_native_rank1_and_scatter_evidence": "NOT_SAVED; remains a next-evidence gap",
    }

def _write_json(path: Path, payload: Mapping[str, Any], *, package_root: Path | None = None) -> int:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    if len(encoded) > MAX_REPORT_BYTES:
        raise OSError("V18 checker report exceeds 16 MiB")
    if package_root is not None:
        package_files = list(package_root.iterdir())
        if any(item.is_symlink() for item in package_files):
            raise OSError("V18 candidate/checker package cannot contain symlinks")
        existing_bytes = sum(item.stat().st_size for item in package_files if item.is_file())
        if existing_bytes + len(encoded) > MAX_REPORT_BYTES:
            raise OSError("V18 candidate/checker package would exceed 16 MiB; no prior evidence was changed")
    if path.exists() or path.is_symlink():
        raise FileExistsError("V18 checker will not replace prior evidence")
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(encoded); stream.flush(); os.fsync(stream.fileno())
        os.link(temp_name, path)
        os.unlink(temp_name)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
        return len(encoded)
    except Exception:
        try: os.unlink(temp_name)
        except FileNotFoundError: pass
        raise


def check_saved_jz_candidate(*, repo_root: Path, candidate_path: Path, candidate_sha256: str, replay_path: Path, replay_sha256: str, contract_path: Path, contract_sha256: str, window_path: Path, window_sha256: str) -> dict[str, Any]:
    root = repo_root.resolve(strict=True); results_root = (root / "results" / TASK41_MODEL_ID).resolve(strict=True)
    def resolve_and_hash(path: Path, digest: str, label: str) -> Path:
        raw = path if path.is_absolute() else root / path
        if raw.is_symlink(): raise ValueError(f"V18 checker {label} is a symlink")
        resolved = raw.resolve(strict=True)
        if not resolved.is_relative_to(root) or sha256_file(resolved) != digest: raise ValueError(f"V18 checker {label} path/hash differs")
        return resolved
    candidate_path = resolve_and_hash(candidate_path, candidate_sha256, "candidate")
    replay_path = resolve_and_hash(replay_path, replay_sha256, "replay")
    contract_path = resolve_and_hash(contract_path, contract_sha256, "contract")
    window_path = resolve_and_hash(window_path, window_sha256, "window")
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("execution_scope") != TASK41_B0_V18_SAVED_JZ_SCOPE or contract.get("numerical_strategy", {}).get("jz_evaluation_strategy") != "binary64_real_imag_fsum":
        raise ValueError("V18 checker contract scope/strategy differs")
    if not candidate_path.is_relative_to(results_root) or not replay_path.parent == candidate_path.parent:
        raise ValueError("V18 checker candidate/replay are outside the fixed result package")
    candidate = json.loads(candidate_path.read_text(encoding="utf-8")); replay = json.loads(replay_path.read_text(encoding="utf-8"))
    if candidate.get("schema") != "task41.p0.v18.saved_jz_candidate.v1" or candidate.get("status") != "CANDIDATE_OUTPUT_SAVED_PENDING_REPLAY":
        raise ValueError("V18 checker candidate schema/status differs")
    if replay.get("schema") != "task41.p0.v18.saved_jz_production_order_replay.v1" or replay.get("status") != "PRODUCTION_ORDER_REPLAYED_PENDING_INDEPENDENT_CHECK":
        raise ValueError("V18 checker replay schema/status differs")
    if candidate.get("consumer_contract_sha256") != contract_sha256 or candidate.get("consumer_window_sha256") != window_sha256 or replay.get("consumer_contract_sha256") != contract_sha256 or replay.get("consumer_window_sha256") != window_sha256:
        raise ValueError("V18 checker consumer contract/window hash binding differs")
    if replay.get("candidate_report_path") != str(candidate_path) or replay.get("candidate_report_sha256") != candidate_sha256:
        raise ValueError("V18 checker replay does not bind the saved candidate report")
    reports, report_paths = _sources(root); expected_items, expected_groups = _expected(root, reports)
    expected_source_reports = {key: {"path": str((root / rel).resolve(strict=True)), "sha256": digest} for key, (rel, digest) in SOURCE_BINDINGS.items()}
    if candidate.get("source_reports") != expected_source_reports:
        raise ValueError("V18 checker candidate source report index differs from fixed source bindings")
    candidate_items = candidate.get("candidate_inputs")
    if not isinstance(candidate_items, list) or len(candidate_items) != 16:
        raise ValueError("V18 checker must receive exactly 16 complete J/z outputs")
    row_by_key: dict[tuple[str, int, int, str], Mapping[str, Any]] = {}
    for row in candidate_items:
        key = (str(row.get("star")), int(row.get("cell_index", -1)), int(row.get("column_index", -1)), str(row.get("state")))
        if key in row_by_key or key not in expected_items:
            raise ValueError("V18 checker candidate item key is duplicated or unexpected")
        src = expected_items[key]
        if any(row.get(field) != src.get(field) for field in ("tensor_ref", "map_refs", "z_ref", "baseline_ref", "source_node")) or row.get("selected_active_row") != src["active"] or row.get("selected_original_row") != src["original"]:
            raise ValueError(f"V18 checker candidate item is not bound to its exact source node: {key}")
        if row.get("source_tensor_shape") != [882, 882] or row.get("J_shape") != [432, 450] or row.get("source_tensor_dtype") != "complex128":
            raise ValueError(f"V18 checker candidate item source layout claim differs: {key}")
        row_by_key[key] = row
    if set(row_by_key) != set(expected_items): raise ValueError("V18 checker candidate item coverage differs")
    cache: dict[tuple[str, str], np.ndarray] = {}; ops: dict[tuple[str, int, int, str], dict[str, Any]] = {}
    metrics: list[dict[str, Any]] = []; unique_refs: dict[tuple[str, str], Mapping[str, Any]] = {}
    for key in sorted(expected_items):
        row = row_by_key[key]; source = expected_items[key]
        for ref in (source["tensor_ref"], source["map_refs"]["active_ids"], source["map_refs"]["interior_positions"], source["map_refs"]["trace_positions"], source["map_refs"]["trace_expansion_data"], source["map_refs"]["trace_expansion_indices"], source["map_refs"]["trace_expansion_indptr"], source["z_ref"], source["baseline_ref"]):
            unique_refs[(str(ref["path"]), str(ref["sha256"]))] = ref
        op = _tensor_maps(source, root=results_root, cache=cache); ops[key] = op
        ref = row.get("candidate_correction")
        if not isinstance(ref, Mapping): raise ValueError(f"V18 checker output ref missing: {key}")
        raw = Path(str(ref.get("path", "")))
        if raw.is_symlink(): raise ValueError("V18 checker correction is a symlink")
        out_path = raw.resolve(strict=True)
        if not out_path.is_relative_to(candidate_path.parent) or type(ref.get("bytes")) is not int or out_path.stat().st_size != ref["bytes"] or sha256_file(out_path) != ref.get("sha256"):
            raise ValueError("V18 checker correction output path/size/hash differs")
        actual = np.load(out_path, allow_pickle=False)
        if actual.shape != (432,) or actual.dtype != np.dtype(np.complex128) or not np.isfinite(actual).all() or list(actual.shape) != ref.get("shape") or str(actual.dtype) != ref.get("dtype"):
            raise ValueError("V18 checker correction output is not finite complex128[432]")
        row_indices = {int(j) for j in range(432) if np.any(op["indices"][int(op["indptr"][j]):int(op["indptr"][j + 1])] == op["target"])}
        row_indices.add(int(np.argmax(np.abs(actual - op["baseline"]))))
        row_indices.add(0)
        measures = _measure_vector(op["J"], op["z"], actual, op["baseline"], row_indices)
        metrics.append({"key": list(key), "candidate_output_sha256": ref["sha256"], **measures})
        op["candidate"] = actual
    for group in expected_groups.values():
        for mapping_name in ("s_actions", "known_interior_refs", "known_trace_refs"):
            for action_ref in group.get(mapping_name, {}).values():
                unique_refs[(str(action_ref["path"]), str(action_ref["sha256"]))] = action_ref
    raw_bytes = sum(int(ref["bytes"]) for ref in unique_refs.values())
    if raw_bytes > MAX_RAW_BYTES or candidate.get("unique_bound_source_bytes") != raw_bytes:
        raise ValueError("V18 checker unique bound source bytes exceed/misstate 16 GiB")
    replay_rows = replay.get("replay")
    if not isinstance(replay_rows, list) or len(replay_rows) != len(expected_groups):
        raise ValueError("V18 checker production replay group count differs")
    claimed: dict[tuple[str, str, int], Mapping[str, Any]] = {}
    for row in replay_rows:
        key = (str(row.get("star")), str(row.get("state")), int(row.get("column_index", -1)))
        if key in claimed or key not in expected_groups: raise ValueError("V18 checker replay key duplicated/unexpected")
        group = expected_groups[key]
        if row.get("cell_order") != group["cells"] or row.get("selected_active_row") != group["active"] or row.get("selected_original_row") != group["original"] or row.get("b_t") != group["b_t"] or row.get("native_volume_rhs_t") != group.get("native_volume_rhs_t") or row.get("b_alpha_once") != group["b_alpha"] or row.get("saved_y") != group["saved_y"] or row.get("baseline_g") != group["saved_g"] or row.get("s_action_refs") != group["s_actions"] or row.get("known_interior_refs", {}) != group.get("known_interior_refs", {}) or row.get("known_trace_refs", {}) != group.get("known_trace_refs", {}) or row.get("source_node") != group["source_node"]:
            raise ValueError(f"V18 checker replay is not bound to original production-order row: {key}")
        claimed[key] = row
    if set(claimed) != set(expected_groups): raise ValueError("V18 checker replay state coverage differs")
    replay_metrics: list[dict[str, Any]] = []
    for key, group in expected_groups.items():
        star, state, col = key; target_y = np.complex128(0j); baseline_g = np.complex128(_pair(group["b_t"], "b_t")); candidate_g = np.complex128(baseline_g)
        exact_y_real = Decimal(0); exact_y_imag = Decimal(0); exact_base_g_real = Decimal.from_float(float(baseline_g.real)); exact_base_g_imag = Decimal.from_float(float(baseline_g.imag)); exact_candidate_g_real = exact_base_g_real; exact_candidate_g_imag = exact_base_g_imag
        for cell in group["cells"]:
            item_state = "initial" if star == "v17" and state == "initial" else "final"; op = ops[(star, int(cell), col, item_state)]
            s_ref = group["s_actions"][str(cell)]; s_action = np.asarray(_array(s_ref, root=results_root, cache=cache), dtype=np.complex128)
            if s_action.shape != (432,) or not np.isfinite(s_action).all(): raise ValueError("V18 checker saved S action shape/value differs")
            target_y = np.complex128(_scatter(target_y, op["target"], op["data"], op["indices"], op["indptr"], s_action))
            baseline_g = np.complex128(_scatter(baseline_g, op["target"], op["data"], op["indices"], op["indptr"], op["baseline"]))
            candidate_g = np.complex128(_scatter(candidate_g, op["target"], op["data"], op["indices"], op["indptr"], op["candidate"]))
            dy_r, dy_i = _decimal_scatter(op["target"], op["data"], op["indices"], op["indptr"], s_action)
            db_r, db_i = _decimal_scatter(op["target"], op["data"], op["indices"], op["indptr"], op["baseline"])
            dc_r, dc_i = _decimal_scatter(op["target"], op["data"], op["indices"], op["indptr"], op["candidate"])
            with localcontext() as ctx:
                ctx.prec = 80
                exact_y_real += dy_r; exact_y_imag += dy_i
                exact_base_g_real += db_r; exact_base_g_imag += db_i
                exact_candidate_g_real += dc_r; exact_candidate_g_imag += dc_i
        beta = _pair(group["b_alpha"], "B-alpha")
        target_y = np.complex128(target_y + beta)
        with localcontext() as ctx:
            ctx.prec = 80
            exact_y_real += Decimal.from_float(beta.real); exact_y_imag += Decimal.from_float(beta.imag)
            exact_base_dr = exact_y_real - exact_base_g_real; exact_base_di = exact_y_imag - exact_base_g_imag
            exact_candidate_dr = exact_y_real - exact_candidate_g_real; exact_candidate_di = exact_y_imag - exact_candidate_g_imag
        baseline_d = target_y - baseline_g; candidate_d = target_y - candidate_g
        claimed_row = claimed[key]
        if [target_y.real, target_y.imag] != claimed_row.get("replayed_y") or [baseline_g.real, baseline_g.imag] != claimed_row.get("replayed_baseline_g") or [candidate_g.real, candidate_g.imag] != claimed_row.get("candidate_g") or [baseline_d.real, baseline_d.imag] != claimed_row.get("baseline_d") or [candidate_d.real, candidate_d.imag] != claimed_row.get("candidate_d"):
            raise ValueError(f"V18 checker independently replayed row differs from candidate claim: {key}")
        saved_y = _pair(group["saved_y"], "source saved_y"); saved_g = _pair(group["saved_g"], "source saved_g")
        if target_y != saved_y or baseline_g != saved_g:
            raise ValueError(f"V18 checker historical production-order replay fails: {key}")
        with localcontext() as ctx:
            ctx.prec = 80
            base_round = (Decimal.from_float(baseline_d.real) - exact_base_dr) ** 2 + (Decimal.from_float(baseline_d.imag) - exact_base_di) ** 2
            cand_round = (Decimal.from_float(candidate_d.real) - exact_candidate_dr) ** 2 + (Decimal.from_float(candidate_d.imag) - exact_candidate_di) ** 2
            resolution = base_round.sqrt() + cand_round.sqrt()
            base_mag = (Decimal.from_float(baseline_d.real)**2 + Decimal.from_float(baseline_d.imag)**2).sqrt()
            cand_mag = (Decimal.from_float(candidate_d.real)**2 + Decimal.from_float(candidate_d.imag)**2).sqrt()
            margin = base_mag - cand_mag
            decision = "IMPROVED" if margin > resolution else "DEGRADED" if margin < -resolution else "INCONCLUSIVE_WITHIN_MEASURED_ROUNDING"
        replay_metrics.append({"key": list(key), "baseline_d": [float(baseline_d.real), float(baseline_d.imag)], "candidate_d": [float(candidate_d.real), float(candidate_d.imag)],
                              "exact_baseline_d_decimal": [str(exact_base_dr), str(exact_base_di)],
                              "exact_candidate_d_decimal": [str(exact_candidate_dr), str(exact_candidate_di)],
                              "baseline_abs": float(base_mag), "candidate_abs": float(cand_mag),
                              "measured_resolution": float(resolution), "improvement_margin": float(margin), "decision": decision})
    final_metrics = [row for row in replay_metrics if row["key"][1] != "initial"]
    main_final = [row for row in final_metrics if row["key"][0] == "v17"]
    if len(main_final) != 2: raise ValueError("V18 checker main-star final-column coverage differs")
    final_jz = [row for row in metrics if row["key"][3] == "final"]
    candidate_sq = sum(row["candidate_vs_original_stored_operands_80d_complex_l2"] ** 2 for row in final_jz)
    baseline_sq = sum(row["baseline_vs_original_stored_operands_80d_complex_l2"] ** 2 for row in final_jz)
    contraction_improved = math.sqrt(candidate_sq) < math.sqrt(baseline_sq)
    main_both_improved = all(row["decision"] == "IMPROVED" for row in main_final)
    old_degraded = [row for row in final_metrics if row["key"][0] != "v17" and row["decision"] == "DEGRADED"]
    candidate_numerical_rejections = [
        {"key": row["key"], "failed_component_count": sum(
            not within
            for item in row["all_432_real_imag_component_errors"]
            for within in item["candidate_rounded_component_within_one_ulp"]
        )}
        for row in metrics if not row["candidate_within_one_ulp_of_rounded_decimal_reference"]
    ]
    resolved_jz_regressions = [
        {"key": row["key"], "components": row["resolved_component_regressions_vs_baseline"]}
        for row in final_jz if row["resolved_component_regressions_vs_baseline"]
    ]
    unresolved_reference_inputs = [
        {"key": row["key"], "rows": [item["row"] for item in row["all_432_real_imag_component_errors"]
         if "INCONCLUSIVE_REFERENCE_PRECISION" in (item["stored_reference_resolution_by_component"] + item["rounded_reference_resolution_by_component"])]}
        for row in final_jz
    ]
    unresolved_reference_inputs = [row for row in unresolved_reference_inputs if row["rows"]]
    replay_metrics_by_key = {tuple(row["key"]): row for row in replay_metrics}
    signed_decompositions = [
        _signed_main_star_decomposition(
            group=expected_groups[("v17", "final", int(col))], ops=ops,
            replay=replay_metrics_by_key[("v17", "final", int(col))],
            results_root=results_root, cache=cache,
        )
        for col in (0, 1)
    ]
    if candidate_numerical_rejections:
        classification = "LOCAL_CANDIDATE_NOT_SUPPORTED"
    elif old_degraded and main_both_improved:
        classification = "LOCAL_MIXED_NOT_QUALIFIED"
    elif unresolved_reference_inputs:
        classification = "INCONCLUSIVE"
    elif main_both_improved and not old_degraded:
        classification = "LOCAL_CANDIDATE_SUPPORTED_GLOBAL_NOT_RUN"
    elif contraction_improved:
        classification = "CONTRACTION_IMPROVED_JOINT_INSUFFICIENT"
    elif any(row["decision"] == "INCONCLUSIVE_WITHIN_MEASURED_ROUNDING" for row in main_final):
        classification = "INCONCLUSIVE"
    else:
        classification = "LOCAL_CANDIDATE_NOT_SUPPORTED"
    output_path = candidate_path.parent / "task41_p0_v18_independent_check.json"
    if output_path.exists() or output_path.is_symlink(): raise FileExistsError("V18 independent checker output already exists")
    result = {
        "schema": SCHEMA, "status": classification, "audit_completed": True,
        "candidate_report_path": str(candidate_path), "candidate_report_sha256": candidate_sha256,
        "production_replay_path": str(replay_path), "production_replay_sha256": replay_sha256,
        "consumer_contract_sha256": contract_sha256, "consumer_window_sha256": window_sha256,
        "source_reports": {key: {"path": report_paths[key], "sha256": SOURCE_BINDINGS[key][1]} for key in SOURCE_BINDINGS},
        "complete_jz_input_count": 16, "all_corrections_all_432_rows_checked": True,
        "candidate_corrections": metrics, "production_order_replay": replay_metrics,
        "candidate_numerical_conformance": not candidate_numerical_rejections,
        "candidate_numerical_rejections": candidate_numerical_rejections,
        "candidate_input_regressions": [
            {"key": row["key"], "candidate_minus_baseline_error_l2_decision": row["candidate_minus_baseline_error_l2_decision"],
             "candidate_minus_baseline_error_l2_margin": row["candidate_minus_baseline_error_l2_margin"],
             "candidate_minus_baseline_error_l2_resolution_envelope": row["candidate_minus_baseline_error_l2_resolution_envelope"],
             "resolved_component_regressions_vs_baseline": row["resolved_component_regressions_vs_baseline"]}
            for row in final_jz
        ],
        "aggregate_final_correction_error_complex_l2_vs_original_operands_80d": math.sqrt(candidate_sq),
        "aggregate_baseline_correction_error_complex_l2_vs_original_operands_80d": math.sqrt(baseline_sq),
        "resolved_jz_input_component_regressions": resolved_jz_regressions,
        "unresolved_reference_precision_inputs": unresolved_reference_inputs,
        "contraction_improved": contraction_improved, "main_two_final_columns_both_credibly_improved": main_both_improved,
        "main_star_signed_D_decomposition": signed_decompositions,
        "old_star_final_degradations": old_degraded, "classification": classification,
        "candidate_supported": classification == "LOCAL_CANDIDATE_SUPPORTED_GLOBAL_NOT_RUN",
        "getrs_count": 0, "factorization_count": 0, "native_fe_action_count": 0,
        "global_qualified": False, "official_result": False, "scientific_qualified": False, "full_owner_unlocked": False,
    }
    _write_json(output_path, result, package_root=candidate_path.parent)
    package_bytes = sum(p.stat().st_size for p in candidate_path.parent.iterdir() if p.is_file())
    return {"checker_report_path": str(output_path), "checker_report_sha256": sha256_file(output_path), "checker_report_bytes": output_path.stat().st_size, "package_bytes": package_bytes, "status": classification, "audit_completed": True, "global_qualified": False, "official_result": False}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("candidate-report", "candidate-sha256", "replay-report", "replay-sha256", "contract-path", "contract-sha256", "window-path", "window-sha256"):
        parser.add_argument(f"--{flag}", required=True)
    args = parser.parse_args(argv)
    report = check_saved_jz_candidate(
        repo_root=Path(__file__).resolve().parents[2], candidate_path=Path(args.candidate_report), candidate_sha256=args.candidate_sha256,
        replay_path=Path(args.replay_report), replay_sha256=args.replay_sha256,
        contract_path=Path(args.contract_path), contract_sha256=args.contract_sha256,
        window_path=Path(args.window_path), window_sha256=args.window_sha256,
    )
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
