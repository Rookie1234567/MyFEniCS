"""Independent full-A6 and identity checker for the Task41 P0 A1 result."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from math import fsum
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from typing import Any, Mapping, Sequence

import numpy as np

from src.geometry.task41_phi90_profile import (
    TASK41_B0_COMPARISON_GROUP,
    TASK41_B0_GEOMETRY_IDENTITY,
    TASK41_B0_PRECONDITIONER,
    TASK41_B0_RUN_ID,
    TASK41_G13_A2_PRECONDITIONER,
    TASK41_G13_A2_RUN_ID,
    task41_direct_summary_errors,
)
from src.io import load_and_resolve
from src.runners.task41_p0_contract import (
    TASK41_A1_COMPARISON_BINDING_RELATIVE,
    TASK41_B0_SAVED_DIAGNOSTICS_SCOPE,
    TASK41_B0_V9_INTERNAL_RHS_STRATEGY,
    TASK41_B0_RUN_ID,
    TASK41_B0_V9_WINDOW_RELATIVE,
    TASK41_MODEL_ID,
    require_task41_a1_comparison_binding,
    contract_relative_path,
    require_task41_p0_contract,
    sha256_file,
    task41_case_id_for_run_id,
    validate_task41_specification,
)
from src.runners.task41_p0_comparison import (
    TASK41_COMPARISON_SCHEMA,
    TASK41_MODE_RELATIVE_LIMIT,
    compare_task41_modal_artifacts,
    compare_task41_power_totals,
    evaluate_task41_metric_packet,
)

CHECKER_SCHEMA = "task41.p0.direct_checker.v1"
A2_CHECKER_SCHEMA = "task41.p0.a2_iterative_checker.v1"
B0_CHECKER_SCHEMA = "task41.p0.b0_iterative_checker.v1"
TASK41_P0_V5_FROZEN_DENOMINATORS = (2225.481253487629, 2225.4807123031883)
TASK41_P0_V5_RELATIVE_TOLERANCE = 1.0e-11
TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256 = (
    "a47eb7a8795b5af542c23ae45915588d89c962d1af1bb8360b8a9d42f1e7c031"
)
TASK41_P0_V9_V8_REPORT_SHA256 = (
    "1bdd07ac38bce95d58a153bacdca0de6cf5941d08d2706dc127e8b00d8e2764f"
)
TASK41_P0_V9_V8_CHECKER_RESULT_SHA256 = (
    "b12af06f818dd4a93443498371aa653216b1646207418f8eaac265e09ddf78c6"
)
TASK41_P0_B0_SAVED_Y_G_SHAPE = (5_752_120, 2)
TASK41_P0_B0_SAVED_Y_G_TRACE_ROWS = 5_688_000
TASK41_P0_B0_SAVED_Y_G_TARGET_ROWS = (4_766_937, 87_567)
TASK41_P0_B0_SAVED_Y_G_FILE_SHA256 = {
    "v6_y": "740eae4b52d810060e334e96a62979626a7f13fe0464cf86f87670bd98c9eaac",
    "v6_g": "56a19fba308ff044e5f9c83bf76f691355838f814237729e10840997b0d19bf4",
    "v9_y": "740eae4b52d810060e334e96a62979626a7f13fe0464cf86f87670bd98c9eaac",
    "v9_g": "ac5a86b9c06656d6d8461ec20db973ea8df0c6635a42af9d79d207b44362a55b",
}
TASK41_P0_B0_SAVED_Y_G_DENOMINATORS = (2225.481253487629, 2225.4807123031883)
TASK41_P0_B0_SAVED_Y_G_IDENTITY_FIELDS = (
    "source_sha", "input_sha256", "physical_model_sha256", "column_identity",
    "active_ordering_sha256", "evaluator_identity", "kernel_identity",
    "cache_identity", "h_identity",
)


def compare_task41_p0_b0_y_g_identity(
    v6_identity: Mapping[str, Any], v9_identity: Mapping[str, Any]
) -> dict[str, Any]:
    """Compare explicit producer identities without assuming equal operators."""
    missing = {
        side: [field for field in TASK41_P0_B0_SAVED_Y_G_IDENTITY_FIELDS if identity.get(field) is None]
        for side, identity in (("v6", v6_identity), ("v9", v9_identity))
    }
    fields = {
        field: {
            "v6": v6_identity.get(field),
            "v9": v9_identity.get(field),
            "equal": (
                v6_identity.get(field) == v9_identity.get(field)
                if field not in missing["v6"] and field not in missing["v9"]
                else None
            ),
        }
        for field in TASK41_P0_B0_SAVED_Y_G_IDENTITY_FIELDS
    }
    complete = not any(missing.values())
    return {
        "status": "COMPLETE" if complete else "INCOMPLETE",
        "fields": fields,
        "missing_fields": missing,
        "same_operator_claim_allowed": bool(
            complete and all(item["equal"] is True for item in fields.values())
        ),
    }


def select_task41_p0_b0_v9_failed_terminal_audit_route(
    *,
    contract: Mapping[str, Any],
    run_case_returncode: int | None,
    run_root: str | Path,
    summary_path: str | Path,
    manifest_path: str | Path,
    numerical_output_path: str | Path,
    repo_root: str | Path | None = None,
    explicit_saved_terminal: bool = False,
) -> str:
    """Select the narrow V9 negative audit only for a failed, complete compact run.

    This is shared by the ordinary service's numeric-failure closeout and the
    retrospective saved-service route. The selector only chooses a route; the
    audit still reopens and verifies every hash-bound input independently.
    """
    root = Path(repo_root or Path(__file__).resolve().parents[2]).resolve()
    case = contract.get("case")
    window = contract.get("window")
    strategy = contract.get("numerical_strategy")
    if (
        not isinstance(case, Mapping)
        or case.get("run_id") != TASK41_B0_RUN_ID
        or not isinstance(window, Mapping)
        or not isinstance(strategy, Mapping)
        or strategy.get("internal_rhs_strategy") != "same_lu_rhs_solve"
    ):
        return "ordinary"
    registered_window = (root / TASK41_B0_V9_WINDOW_RELATIVE).resolve()
    raw_window = Path(str(window.get("path", "")))
    bound_window = (raw_window if raw_window.is_absolute() else root / raw_window).resolve()
    run_root_path = Path(run_root).resolve()
    summary_file = Path(summary_path).resolve()
    manifest_file = Path(manifest_path).resolve()
    numerical_output = Path(numerical_output_path).resolve()
    expected_numerical_output = run_root_path / "numerical_output"
    failed = explicit_saved_terminal or (
        type(run_case_returncode) is int and run_case_returncode != 0
    )
    if (
        not failed
        or bound_window != registered_window
        or not run_root_path.is_relative_to(
            (root / "results" / TASK41_MODEL_ID).resolve()
        )
        or summary_file != run_root_path / "task40_v10_p6_candidate_summary.json"
        or manifest_file != run_root_path / "run_manifest.json"
        or numerical_output != expected_numerical_output
        or numerical_output.exists()
        or not summary_file.is_file()
        or not manifest_file.is_file()
        or not (run_root_path / "run_summary.json").is_file()
    ):
        return "ordinary"
    try:
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "ordinary"
    compact = summary.get("b0_v9_compact_volume_audit") if isinstance(summary, Mapping) else None
    independent = summary.get("b0_v9_independent_check") if isinstance(summary, Mapping) else None
    if (
        not isinstance(compact, Mapping)
        or not isinstance(independent, Mapping)
        or not isinstance(manifest, Mapping)
        or Path(str(manifest.get("output_directory", ""))).resolve() != run_root_path
        or Path(str(manifest.get("numerical_output_directory", ""))).resolve()
        != expected_numerical_output
    ):
        return "ordinary"
    return "v9_failed_terminal_audit"


def compare_task41_p0_b0_saved_y_g_arrays(
    *,
    v6_y_path: str | Path,
    v6_g_path: str | Path,
    v9_y_path: str | Path,
    v9_g_path: str | Path,
    expected_sha256s: Mapping[str, str],
    expected_shape: tuple[int, int] = TASK41_P0_B0_SAVED_Y_G_SHAPE,
    trace_rows: int = TASK41_P0_B0_SAVED_Y_G_TRACE_ROWS,
    target_rows: Sequence[int] = TASK41_P0_B0_SAVED_Y_G_TARGET_ROWS,
    denominators: Sequence[float] = TASK41_P0_B0_SAVED_Y_G_DENOMINATORS,
    block_rows: int = 65_536,
    v6_identity: Mapping[str, Any] | None = None,
    v9_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compare saved y/g columns in bounded mmap chunks without saving deltas."""
    if type(block_rows) is not int or block_rows <= 0 or block_rows > 65_536:
        raise ValueError("saved y/g comparison block_rows must be in [1, 65536]")
    if (
        len(expected_shape) != 2
        or expected_shape[0] <= 0
        or expected_shape[1] != 2
        or type(trace_rows) is not int
        or not 0 <= trace_rows <= expected_shape[0]
        or len(denominators) != 2
        or any(not np.isfinite(value) or value <= 0 for value in denominators)
    ):
        raise ValueError("saved y/g comparison requires a positive [rows, 2] shape and denominators")
    paths = {
        "v6_y": Path(v6_y_path).resolve(strict=True),
        "v6_g": Path(v6_g_path).resolve(strict=True),
        "v9_y": Path(v9_y_path).resolve(strict=True),
        "v9_g": Path(v9_g_path).resolve(strict=True),
    }
    if set(expected_sha256s) != set(paths):
        raise ValueError("saved y/g comparison requires exactly four expected file hashes")
    arrays: dict[str, np.ndarray] = {}
    file_records: dict[str, dict[str, Any]] = {}
    for name, path in paths.items():
        digest = sha256_file(path)
        if digest != expected_sha256s[name]:
            raise ValueError(f"saved y/g input {name} differs from its bound SHA-256")
        array = np.load(path, mmap_mode="r", allow_pickle=False)
        if array.dtype != np.dtype(np.complex128) or tuple(array.shape) != tuple(expected_shape):
            raise ValueError(f"saved y/g input {name} must be complex128 with the bound shape")
        arrays[name] = array
        file_records[name] = {
            "path": str(path),
            "bytes": int(path.stat().st_size),
            "sha256": digest,
            "shape": list(array.shape),
            "dtype": str(array.dtype),
        }

    vector_names = (
        "v6_y", "v6_g", "v9_y", "v9_g", "d6", "d9", "delta_y",
        "delta_g", "y9_g6", "y6_g9", "delta_d", "delta_d_arithmetic",
        "subtraction_remainder",
    )
    norm2_chunks: dict[str, list[list[float]]] = {name: [[], []] for name in vector_names}
    region_norm2_chunks: dict[str, dict[str, list[list[float]]]] = {
        name: {region: [[], []] for region in ("trace", "port")}
        for name in vector_names
    }
    independent_norm2_chunks: dict[str, list[list[float]]] = {
        name: [[], []] for name in vector_names
    }
    independent_region_norm2_chunks: dict[str, dict[str, list[list[float]]]] = {
        name: {region: [[], []] for region in ("trace", "port")}
        for name in vector_names
    }
    region_maxima: dict[str, dict[str, dict[str, list[Any]]]] = {
        name: {
            region: {
                "abs": [0.0, 0.0], "abs_row": [None, None],
                "real": [0.0, 0.0], "real_row": [None, None],
                "imag": [0.0, 0.0], "imag_row": [None, None],
            }
            for region in ("trace", "port")
        }
        for name in vector_names
    }
    max_abs = {name: [0.0, 0.0] for name in vector_names}
    max_abs_row: dict[str, list[int | None]] = {name: [None, None] for name in vector_names}
    max_real = {name: [0.0, 0.0] for name in vector_names}
    max_imag = {name: [0.0, 0.0] for name in vector_names}
    block_energy: dict[str, list[list[float]]] = {name: [[], []] for name in ("d6", "d9", "delta_y", "delta_g", "delta_d")}
    top_rows: dict[str, list[list[tuple[float, int]]]] = {
        name: [[], []] for name in ("d6", "d9", "delta_y", "delta_g", "delta_d")
    }
    dot_real_chunks_by_column: list[list[float]] = [[], []]
    numpy_dot_chunks_by_column: list[list[float]] = [[], []]
    max_real_row: dict[str, list[int | None]] = {name: [None, None] for name in vector_names}
    max_imag_row: dict[str, list[int | None]] = {name: [None, None] for name in vector_names}
    row_count = int(expected_shape[0])
    selected_row_values: dict[int, dict[str, list[list[float]]]] = {}

    def collect_vector(name: str, values: np.ndarray, row_offset: int, block_index: int) -> None:
        magnitude = np.abs(values)
        if not np.all(np.isfinite(values)) or not np.all(np.isfinite(magnitude)):
            raise ValueError(f"saved y/g comparison derived vector {name} contains non-finite values")
        trace_stop = max(0, min(values.shape[0], trace_rows - row_offset))
        regions = {
            "trace": (values[:trace_stop], row_offset),
            "port": (values[trace_stop:], row_offset + trace_stop),
        }
        for column in range(2):
            norm2_chunks[name][column].append(float(np.sum(magnitude[:, column] ** 2, dtype=np.float64)))
            row_energy = values[:, column].real**2 + values[:, column].imag**2
            independent_norm2_chunks[name][column].append(fsum(row_energy.tolist()))
            for region, (region_values, region_offset) in regions.items():
                region_magnitude = np.abs(region_values[:, column])
                region_norm2_chunks[name][region][column].append(
                    float(np.sum(region_magnitude**2, dtype=np.float64))
                )
                region_energy = region_values[:, column].real**2 + region_values[:, column].imag**2
                independent_region_norm2_chunks[name][region][column].append(
                    fsum(region_energy.tolist())
                )
                if region_values.shape[0]:
                    region_abs_index = int(np.argmax(region_magnitude))
                    region_abs = float(region_magnitude[region_abs_index])
                    real_abs = np.abs(region_values[:, column].real)
                    real_index = int(np.argmax(real_abs))
                    imag_abs = np.abs(region_values[:, column].imag)
                    imag_index = int(np.argmax(imag_abs))
                    maxima = region_maxima[name][region]
                    if region_abs > maxima["abs"][column]:
                        maxima["abs"][column] = region_abs
                        maxima["abs_row"][column] = region_offset + region_abs_index
                    if float(real_abs[real_index]) > maxima["real"][column]:
                        maxima["real"][column] = float(real_abs[real_index])
                        maxima["real_row"][column] = region_offset + real_index
                    if float(imag_abs[imag_index]) > maxima["imag"][column]:
                        maxima["imag"][column] = float(imag_abs[imag_index])
                        maxima["imag_row"][column] = region_offset + imag_index
            abs_index = int(np.argmax(magnitude[:, column]))
            candidate_abs = float(magnitude[abs_index, column])
            if candidate_abs > max_abs[name][column]:
                max_abs[name][column] = candidate_abs
                max_abs_row[name][column] = row_offset + abs_index
            real_abs = np.abs(values[:, column].real)
            real_index = int(np.argmax(real_abs))
            if float(real_abs[real_index]) > max_real[name][column]:
                max_real[name][column] = float(real_abs[real_index])
                max_real_row[name][column] = row_offset + real_index
            imag_abs = np.abs(values[:, column].imag)
            imag_index = int(np.argmax(imag_abs))
            if float(imag_abs[imag_index]) > max_imag[name][column]:
                max_imag[name][column] = float(imag_abs[imag_index])
                max_imag_row[name][column] = row_offset + imag_index
            if name in block_energy:
                energy = np.sum(magnitude[:, column] ** 2, dtype=np.float64)
                if len(block_energy[name][column]) == block_index:
                    block_energy[name][column].append(float(energy))
                else:
                    block_energy[name][column][block_index] += float(energy)
        if name in top_rows:
            keep = min(10, magnitude.shape[0])
            for column in range(2):
                column_energy = magnitude[:, column] ** 2
                if keep:
                    indices = np.argpartition(column_energy, -keep)[-keep:]
                    merged = top_rows[name][column] + [
                        (float(column_energy[index]), row_offset + int(index))
                        for index in indices
                    ]
                    top_rows[name][column] = sorted(merged, reverse=True)[:10]

    for block_index, start in enumerate(range(0, row_count, block_rows)):
        stop = min(start + block_rows, row_count)
        v6_y = np.asarray(arrays["v6_y"][start:stop])
        v6_g = np.asarray(arrays["v6_g"][start:stop])
        v9_y = np.asarray(arrays["v9_y"][start:stop])
        v9_g = np.asarray(arrays["v9_g"][start:stop])
        d6 = v6_y - v6_g
        d9 = v9_y - v9_g
        delta_y = v9_y - v6_y
        delta_g = v9_g - v6_g
        delta_d = delta_y - delta_g
        delta_d_arithmetic = d9 - d6
        subtraction_remainder = delta_d_arithmetic - delta_d
        vectors = {
            "v6_y": v6_y,
            "v6_g": v6_g,
            "v9_y": v9_y,
            "v9_g": v9_g,
            "d6": d6,
            "d9": d9,
            "delta_y": delta_y,
            "delta_g": delta_g,
            "y9_g6": v9_y - v6_g,
            "y6_g9": v6_y - v9_g,
            "delta_d": delta_d,
            "delta_d_arithmetic": delta_d_arithmetic,
            "subtraction_remainder": subtraction_remainder,
        }
        for name, values in vectors.items():
            collect_vector(name, values, start, block_index)
        for column in range(2):
            real_inner = (
                d6[:, column].real * delta_d[:, column].real
                + d6[:, column].imag * delta_d[:, column].imag
            )
            dot_real_chunks_by_column[column].append(fsum(real_inner.tolist()))
            numpy_dot_chunks_by_column[column].append(
                float(np.real(np.vdot(d6[:, column], delta_d[:, column])))
            )
        for target_row in target_rows:
            if type(target_row) is int and start <= target_row < stop:
                index = target_row - start
                selected_row_values[target_row] = {
                    "y6": [[float(value.real), float(value.imag)] for value in v6_y[index]],
                    "g6": [[float(value.real), float(value.imag)] for value in v6_g[index]],
                    "d6": [[float(value.real), float(value.imag)] for value in d6[index]],
                    "y9": [[float(value.real), float(value.imag)] for value in v9_y[index]],
                    "g9": [[float(value.real), float(value.imag)] for value in v9_g[index]],
                    "d9": [[float(value.real), float(value.imag)] for value in d9[index]],
                    "delta_y": [[float(value.real), float(value.imag)] for value in delta_y[index]],
                    "delta_g": [[float(value.real), float(value.imag)] for value in delta_g[index]],
                    "delta_d": [[float(value.real), float(value.imag)] for value in delta_d[index]],
                }

    vector_summary: dict[str, Any] = {}
    for name in vector_names:
        norm2 = [fsum(chunks) for chunks in independent_norm2_chunks[name]]
        numpy_norm2 = [fsum(chunks) for chunks in norm2_chunks[name]]
        region_norm2 = {
            region: [fsum(chunks) for chunks in columns]
            for region, columns in independent_region_norm2_chunks[name].items()
        }
        numpy_region_norm2 = {
            region: [fsum(chunks) for chunks in columns]
            for region, columns in region_norm2_chunks[name].items()
        }
        vector_summary[name] = {
            "norm2_by_column": norm2,
            "norm_by_column": [float(np.sqrt(value)) for value in norm2],
            "norm_over_frozen_denominator_by_column": [
                float(np.sqrt(value)) / float(denominators[column]) for column, value in enumerate(norm2)
            ],
            "max_abs_component_by_column": max_abs[name],
            "max_abs_row_by_column": max_abs_row[name],
            "max_abs_real_component_by_column": max_real[name],
            "max_abs_imag_component_by_column": max_imag[name],
            "max_abs_real_component_row_by_column": max_real_row[name],
            "max_abs_imag_component_row_by_column": max_imag_row[name],
            "norm2_by_region_and_column": region_norm2,
            "norm_by_region_and_column": {
                region: [float(np.sqrt(value)) for value in column_values]
                for region, column_values in region_norm2.items()
            },
            "norm_over_frozen_denominator_by_region_and_column": {
                region: [
                    float(np.sqrt(value)) / float(denominators[column])
                    for column, value in enumerate(column_values)
                ]
                for region, column_values in region_norm2.items()
            },
            "maxima_by_region_and_column": region_maxima[name],
            "numpy_reduction_crosscheck_norm2_by_column": numpy_norm2,
            "independent_minus_numpy_norm2_by_column": [
                norm2[column] - numpy_norm2[column] for column in range(2)
            ],
            "numpy_reduction_crosscheck_norm2_by_region_and_column": numpy_region_norm2,
        }
        if name in block_energy:
            block_norm2 = block_energy[name]
            total = [fsum(column_blocks) for column_blocks in block_norm2]
            vector_summary[name]["block_energy_norm2_by_column"] = [
                [float(value) for value in column_blocks] for column_blocks in block_norm2
            ]
            ordered = []
            for column in range(2):
                candidates = sorted(
                    ((energy, index) for index, energy in enumerate(block_norm2[column])),
                    reverse=True,
                )[:10]
                ordered.append([
                    {
                        "block_index": index,
                        "row_start": index * block_rows,
                        "row_stop": min((index + 1) * block_rows, row_count),
                        "norm2": energy,
                        "energy_fraction": energy / total[column] if total[column] else 0.0,
                    }
                    for energy, index in candidates
                ])
            vector_summary[name]["block_energy_top10_by_column"] = ordered
            vector_summary[name]["top_rows_by_column"] = [
                [
                    {
                        "row": row,
                        "norm2": energy,
                        "energy_fraction": energy / norm2[column]
                        if norm2[column]
                        else 0.0,
                    }
                    for energy, row in rows
                ]
                for column, rows in enumerate(top_rows[name])
            ]
            vector_summary[name]["top10_energy_coverage_by_column"] = [
                fsum(energy for energy, _row in rows) / norm2[column]
                if norm2[column]
                else 0.0
                for column, rows in enumerate(top_rows[name])
            ]

    d6_norm2 = vector_summary["d6"]["norm2_by_column"]
    d9_norm2 = vector_summary["d9"]["norm2_by_column"]
    delta_d_by_column = vector_summary["delta_d"]["norm2_by_column"]
    lhs_by_column = [d9_norm2[column] - d6_norm2[column] for column in range(2)]
    rhs_by_column = [
        2.0 * fsum(dot_real_chunks_by_column[column]) + delta_d_by_column[column]
        for column in range(2)
    ]
    energy_identity = {
        "lhs_norm2_d9_minus_d6_by_column": lhs_by_column,
        "rhs_2real_inner_d6_delta_d_plus_norm2_delta_d_by_column": rhs_by_column,
        "independent_fsum_2real_inner_by_column": [
            2.0 * fsum(chunks) for chunks in dot_real_chunks_by_column
        ],
        "numpy_vdot_crosscheck_2real_inner_by_column": [
            2.0 * fsum(chunks) for chunks in numpy_dot_chunks_by_column
        ],
        "independent_minus_numpy_2real_inner_by_column": [
            2.0
            * (
                fsum(dot_real_chunks_by_column[column])
                - fsum(numpy_dot_chunks_by_column[column])
            )
            for column in range(2)
        ],
        "residual_lhs_minus_rhs_by_column": [
            lhs_by_column[column] - rhs_by_column[column] for column in range(2)
        ],
        "identity_residual_norm2_aggregate": fsum(lhs_by_column) - fsum(rhs_by_column),
        "formula": "||d9||^2-||d6||^2 = 2 Re<d6, delta_y-delta_g> + ||delta_y-delta_g||^2",
    }
    return {
        "schema": "task41.p0.b0.saved_y_g_comparison.v1",
        "status": "COMPLETED",
        "data_integrity": True,
        "arrays": file_records,
        "expected_shape": list(expected_shape),
        "trace_rows": trace_rows,
        "port_rows": row_count - trace_rows,
        "selected_row_slices": {
            str(row): selected_row_values[row]
            for row in target_rows
            if type(row) is int and row in selected_row_values
        },
        "block_rows": block_rows,
        "frozen_denominators": list(denominators),
        "identity_comparison": (
            compare_task41_p0_b0_y_g_identity(v6_identity, v9_identity)
            if v6_identity is not None and v9_identity is not None
            else {"status": "INCOMPLETE", "reason": "producer identity metadata was not supplied"}
        ),
        "vectors": vector_summary,
        "cross_diagnostics": {
            "y9_minus_g6": vector_summary["y9_g6"],
            "y6_minus_g9": vector_summary["y6_g9"],
            "cross_terms_are_diagnostics_only": True,
        },
        "energy_identity": energy_identity,
        "trace_port_split": {
            "status": "COMPLETED",
            "trace_row_interval": [0, trace_rows],
            "port_row_interval": [trace_rows, row_count],
            "norm2_and_norm_reported_for_each_vector_and_column": True,
        },
        "subtraction_associativity": {
            "status": "COMPLETED",
            "formula": "(d9-d6) - (delta_y-delta_g)",
            "remainder": vector_summary["subtraction_remainder"],
        },
        "finite_values_verified_for_inputs_and_derived_chunks": True,
        "numerical_accumulation": {
            "primary_method": "math.fsum of rowwise float64 norm-square and real-inner-product terms within each bounded chunk, then math.fsum across chunks",
            "crosscheck_method": "float64 NumPy reductions within each bounded chunk, then math.fsum across chunks",
            "independent_scalar_reduction": True,
            "arithmetic_precision": "float64 only; no wider arithmetic or production answer",
        },
        "full_length_delta_arrays_saved": False,
        "official_result": False,
    }


def _task41_p0_saved_y_g_common_donor_identity(
    *,
    repo_root: str | Path,
    expected_manifest_sha256: str,
    active_rows: int,
    port_rows: int,
    expected_shape: tuple[int, int],
) -> tuple[dict[str, Any], tuple[Path, Path]]:
    """Bind the shared V4 donor map from its small summary/manifest, without loading arrays."""
    from src.runners.task41_p0_contract import TASK41_B0_V9_VOLUME_DONOR_RUN_RELATIVE
    from src.solvers.task41_v4_volume_only_audit import TASK41_V4_DONOR_MANIFEST_SHA256

    root = Path(repo_root).resolve(strict=True)
    if (
        type(active_rows) is not int
        or active_rows <= 0
        or type(port_rows) is not int
        or port_rows <= 0
        or len(expected_shape) != 2
        or expected_shape[1] != 2
        or any(type(value) is not int or value <= 0 for value in expected_shape)
    ):
        raise ValueError("shared V4 donor expected row layout is malformed")
    donor_run = (root / TASK41_B0_V9_VOLUME_DONOR_RUN_RELATIVE).resolve(strict=True)
    summary_path = (donor_run / "task40_v10_p6_candidate_summary.json").resolve(strict=True)
    summary = _json_object(summary_path, "shared V4 donor summary")
    evidence = summary.get("b0_recovery_evidence")
    manifest_record = evidence.get("manifest") if isinstance(evidence, Mapping) else None
    if not isinstance(manifest_record, Mapping):
        raise ValueError("shared V4 donor summary omits its recovery manifest")
    manifest_path = _task41_run_artifact(donor_run, manifest_record, "shared V4 donor manifest")
    manifest_sha256 = sha256_file(manifest_path)
    if (
        manifest_sha256 != TASK41_V4_DONOR_MANIFEST_SHA256
        or expected_manifest_sha256 != manifest_sha256
    ):
        raise ValueError("V6/V9 reports do not bind the frozen shared V4 donor manifest")
    manifest = _json_object(manifest_path, "shared V4 donor manifest")
    if (
        manifest.get("schema") != "task41.p0.b0.recovery_evidence.v1"
        or type(manifest.get("full_storage_rows")) is not int
        or manifest.get("full_storage_rows", 0) <= 0
        or manifest.get("active_trace_rows") != active_rows
        or manifest.get("port_rows") != port_rows
        or active_rows + port_rows != expected_shape[0]
    ):
        raise ValueError("shared V4 donor manifest has a different saved-vector row layout")
    columns = manifest.get("columns")
    inputs = manifest.get("input_identities")
    if not isinstance(columns, list) or len(columns) != 2 or not isinstance(inputs, list) or len(inputs) != 2:
        raise ValueError("shared V4 donor manifest must bind two ordered columns and input recipes")

    full_rows = manifest["full_storage_rows"]
    sha_pattern = re.compile(r"[0-9a-f]{64}")
    array_specs = {
        "active_original_rows": ("int64", [active_rows]),
        "slave_rows": ("int64", None),
        "known_field": ("complex128", [full_rows]),
        "native_rhs": ("complex128", [full_rows]),
        "native_volume_rhs": ("complex128", [full_rows]),
    }
    input_hash_fields = (
        "probe_values_sha256", "active_original_rows_sha256", "mapped_active_rows_sha256",
        "interior_rows_sha256", "interior_values_sha256", "raw_slave_rows_sha256",
        "raw_slave_values_sha256",
    )
    identities: list[dict[str, Any]] = []
    for index, (column, input_identity) in enumerate(zip(columns, inputs)):
        if (
            not isinstance(column, Mapping)
            or type(column.get("column")) is not int
            or column.get("column") != index
            or not isinstance(input_identity, Mapping)
            or type(input_identity.get("mode_index")) is not int
            or column.get("mode_index") != input_identity.get("mode_index")
        ):
            raise ValueError("shared V4 donor columns or input recipes are out of order")
        mode_key = input_identity.get("mode_key")
        alpha = input_identity.get("port_alpha")
        if (
            not isinstance(mode_key, list)
            or not mode_key
            or input_identity.get("mode_index", -1) < 0
            or input_identity.get("mode_index") in {
                item.get("mode_index") for item in inputs[:index]
                if isinstance(item, Mapping)
            }
            or not isinstance(alpha, list)
            or len(alpha) != 2
            or any(type(value) not in (int, float) or not np.isfinite(value) for value in alpha)
            or any(type(input_identity.get(name)) is not int or input_identity[name] < 0
                   for name in ("probe_rows", "active_trace_rows", "cell_interior_rows", "mpc_slave_rows"))
            or any(
                not isinstance(input_identity.get(name), str)
                or sha_pattern.fullmatch(input_identity[name]) is None
                for name in input_hash_fields
            )
        ):
            raise ValueError(f"shared V4 donor column {index} input recipe is malformed")
        artifacts = column.get("artifacts")
        if not isinstance(artifacts, Mapping):
            raise ValueError(f"shared V4 donor column {index} has no artifact inventory")
        column_artifacts: dict[str, dict[str, Any]] = {}
        for name in (
            *array_specs,
            "b_alpha_rows", "b_alpha_values", "selected_B_frame_rows", "selected_B_frame_values",
        ):
            record = artifacts.get(name)
            if not isinstance(record, Mapping):
                raise ValueError(f"shared V4 donor column {index} omits {name}")
            dtype, fixed_shape = array_specs.get(name, (None, None))
            shape = record.get("shape")
            if (
                not isinstance(record.get("path"), str)
                or not record["path"]
                or type(record.get("bytes")) is not int
                or record["bytes"] <= 0
                or not isinstance(record.get("sha256"), str)
                or sha_pattern.fullmatch(record["sha256"]) is None
                or not isinstance(shape, list)
                or not shape
                or any(type(dim) is not int or dim < 0 for dim in shape)
                or (dtype is not None and record.get("dtype") != dtype)
                or (fixed_shape is not None and shape != fixed_shape)
                or (name == "slave_rows" and len(shape) != 1)
            ):
                raise ValueError(f"shared V4 donor column {index} {name} record is malformed")
            if name in {"b_alpha_rows", "selected_B_frame_rows"} and (
                record.get("dtype") != "int64" or len(shape) != 1
            ):
                raise ValueError(f"shared V4 donor column {index} {name} layout differs")
            if name in {"b_alpha_values", "selected_B_frame_values"} and (
                record.get("dtype") != "complex128" or len(shape) != 1
            ):
                raise ValueError(f"shared V4 donor column {index} {name} layout differs")
            if name.endswith("_rows") and name in {"b_alpha_rows", "selected_B_frame_rows"}:
                paired_name = name.replace("_rows", "_values")
                if shape != artifacts.get(paired_name, {}).get("shape"):
                    raise ValueError(f"shared V4 donor column {index} {name} and values differ in shape")
            array_sha256 = record.get("array_sha256")
            if array_sha256 is not None and (
                not isinstance(array_sha256, str)
                or sha_pattern.fullmatch(array_sha256) is None
            ):
                raise ValueError(f"shared V4 donor column {index} {name} array hash is malformed")
            raw = Path(record["path"])
            artifact_path = (raw if raw.is_absolute() else donor_run / raw).resolve(strict=True)
            if (
                not artifact_path.is_relative_to(donor_run)
                or not artifact_path.is_file()
                or artifact_path.stat().st_size != record["bytes"]
            ):
                raise ValueError(f"shared V4 donor column {index} {name} path or size differs")
            column_artifacts[name] = {
                "path": str(artifact_path),
                "bytes": record["bytes"],
                "sha256": record["sha256"],
                **({"array_sha256": array_sha256} if array_sha256 is not None else {}),
                "shape": list(shape),
                "dtype": record["dtype"],
                "identity_source": "manifest_metadata_only_payload_not_opened",
            }
        identities.append({
            "column": index,
            "mode_index": input_identity["mode_index"],
            "mode_key": mode_key,
            "port_alpha": [float(value) for value in alpha],
            "input_recipe": {name: input_identity[name] for name in (
                "probe_rows", "active_trace_rows", "cell_interior_rows", "mpc_slave_rows",
                *input_hash_fields,
            )},
            "full_active_mapping_artifact": column_artifacts["active_original_rows"],
            "artifacts": column_artifacts,
        })
    raw_inventory: dict[Path, int] = {}

    def collect_raw_artifact_records(value: Any) -> None:
        if isinstance(value, Mapping):
            raw_path = value.get("path")
            byte_count = value.get("bytes")
            if isinstance(raw_path, str) and raw_path.endswith((".npy", ".npz")):
                if type(byte_count) is not int or byte_count <= 0:
                    raise ValueError("shared V4 donor raw artifact size is malformed")
                relative = Path(raw_path)
                path = (relative if relative.is_absolute() else donor_run / relative).resolve(strict=True)
                if not path.is_relative_to(donor_run) or not path.is_file() or path.stat().st_size != byte_count:
                    raise ValueError("shared V4 donor raw artifact path or stat differs")
                prior = raw_inventory.setdefault(path, byte_count)
                if prior != byte_count:
                    raise ValueError("shared V4 donor repeats a raw artifact with conflicting size")
            for nested in value.values():
                collect_raw_artifact_records(nested)
        elif isinstance(value, list):
            for nested in value:
                collect_raw_artifact_records(nested)

    collect_raw_artifact_records(manifest)
    identity = {
        "status": "HASH_BOUND_DONOR_METADATA_ONLY",
        "raw_artifact_count": len(raw_inventory),
        "raw_artifact_bytes_stat_only": sum(raw_inventory.values()),
        "run_relative_path": TASK41_B0_V9_VOLUME_DONOR_RUN_RELATIVE.as_posix(),
        "summary_path": str(summary_path),
        "summary_sha256": sha256_file(summary_path),
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha256,
        "payload_arrays_opened": False,
        "shared_mapping_and_known_rhs_identity": identities,
        "old_per_key_lu_identity": "UNKNOWN_NOT_PERSISTED_BY_V6",
    }
    return identity, (summary_path, manifest_path)


def compare_task41_p0_b0_saved_y_g_reports(
    *,
    v6_report_path: str | Path,
    v6_report_sha256: str,
    v9_report_path: str | Path,
    v9_report_sha256: str,
    v9_summary_path: str | Path,
    v9_summary_sha256: str,
    v9_service_receipt_path: str | Path,
    v9_service_receipt_sha256: str,
    consumer_contract_path: str | Path,
    consumer_contract_sha256: str,
    output_path: str | Path,
    repo_root: str | Path | None = None,
    expected_shape: tuple[int, int] = TASK41_P0_B0_SAVED_Y_G_SHAPE,
    trace_rows: int = TASK41_P0_B0_SAVED_Y_G_TRACE_ROWS,
    target_rows: Sequence[int] = TASK41_P0_B0_SAVED_Y_G_TARGET_ROWS,
    block_rows: int = 65_536,
) -> dict[str, Any]:
    """Compare only the y/g artifacts named by the hash-bound V6/V9 reports.

    Producer metadata and the current saved-diagnostics contract are validated
    before the low-level helper opens any of the four scientific arrays. No
    caller-supplied identity values participate in the compatibility decision.
    """
    root = Path(repo_root or Path(__file__).resolve().parents[2]).resolve()

    def read_bound_object(path_value: str | Path, expected: str, label: str) -> tuple[Path, dict[str, Any]]:
        if re.fullmatch(r"[0-9a-f]{64}", str(expected)) is None:
            raise ValueError(f"{label} requires a full SHA-256")
        path = Path(path_value).resolve(strict=True)
        if not path.is_file() or sha256_file(path) != expected:
            raise ValueError(f"{label} path or SHA-256 differs from its explicit binding")
        if path.stat().st_size > 8 * 1024**2:
            raise ValueError(f"{label} metadata exceeds the 8 MiB metadata bound")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"{label} is not readable JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError(f"{label} must be a JSON object")
        return path, payload

    # Check the new consumer first: this operation is admitted only under the
    # existing, explicitly scoped saved-diagnostics contract.
    consumer_contract_path, consumer_contract = read_bound_object(
        consumer_contract_path, consumer_contract_sha256, "saved-diagnostics consumer contract"
    )
    require_task41_p0_contract(
        consumer_contract_path,
        expected_sha256=consumer_contract_sha256,
        current_root=root,
        check_current_source=True,
        require_clean_source=True,
        case_id="B0",
    )
    scope = consumer_contract.get("execution_scope")
    if (
        scope != TASK41_B0_SAVED_DIAGNOSTICS_SCOPE
        or scope.get("kind") != "saved_diagnostics_only"
        or "v6_v9_saved_y_g_comparison" not in scope.get("actions", [])
        or scope.get("full_owner") is not False
    ):
        raise ValueError("saved y/g comparison requires the exact saved_diagnostics_only scope")

    v6_report_path, v6 = read_bound_object(
        v6_report_path, v6_report_sha256, "V6 candidate report"
    )
    v9_report_path, v9 = read_bound_object(
        v9_report_path, v9_report_sha256, "V9 compact volume report"
    )
    v9_summary_path, v9_summary = read_bound_object(
        v9_summary_path, v9_summary_sha256, "V9 run summary"
    )
    v9_service_receipt_path, v9_receipt = read_bound_object(
        v9_service_receipt_path, v9_service_receipt_sha256, "V9 service receipt"
    )

    if v6_report_path.name != "task41_p0_v6_actual_qmetric_candidate.json":
        raise ValueError("V6 report is not the registered actual-qmetric candidate report")
    if _task41_mesh_actual_exact_candidate_profile(v6_report_path, v6).get("version") != "v6":
        raise ValueError("V6 report profile is not the registered V6 actual-qmetric producer")
    if (
        v9_report_path.name != "task41_p0_b0_v9_compact_volume_audit.json"
        or v9.get("schema") != "task41.p0.b0.v9.compact_volume_identity.v1"
        or v9.get("completed") is not True
        or v9.get("status") != "GATE_FAILED"
        or v9.get("official_result") is not False
    ):
        raise ValueError("V9 input is not the completed, negative compact volume report")

    output_root = Path(str(v9_summary.get("output_directory", ""))).resolve(strict=True)
    if (
        v9_summary.get("run_id") != TASK41_B0_RUN_ID
        or v9_summary.get("status") != "finished"
        or v9_summary.get("result_classification") != "WORKER_FAILED"
        or v9_report_path.parent != output_root
    ):
        raise ValueError("V9 summary does not bind the compact report to its failed B0 run")
    if (
        v9_receipt.get("schema") != "task41.p0.service_receipt.v1"
        or v9_receipt.get("case_id") != "B0"
        or type(v9_receipt.get("run_case_returncode")) is not int
        or v9_receipt.get("run_case_returncode") == 0
    ):
        raise ValueError("V9 service receipt does not identify the failed B0 producer run")

    v6_contract_path_value = v6.get("consumer_contract_path")
    v6_contract_sha = v6.get("consumer_contract_sha256")
    v9_contract_path_value = v9_receipt.get("contract_path")
    v9_contract_sha = v9_receipt.get("contract_sha256")
    if not all(isinstance(item, str) for item in (
        v6_contract_path_value, v6_contract_sha, v9_contract_path_value, v9_contract_sha
    )):
        raise ValueError("V6/V9 reports omit their producer contract bindings")
    v6_contract_path, v6_contract = read_bound_object(
        v6_contract_path_value, v6_contract_sha, "V6 producer contract"
    )
    v9_contract_path, v9_contract = read_bound_object(
        v9_contract_path_value, v9_contract_sha, "V9 producer contract"
    )
    require_task41_p0_contract(
        v6_contract_path,
        expected_sha256=v6_contract_sha,
        current_root=root,
        check_current_source=False,
        require_clean_source=False,
        case_id="B0",
    )
    require_task41_p0_contract(
        v9_contract_path,
        expected_sha256=v9_contract_sha,
        current_root=root,
        check_current_source=False,
        require_clean_source=False,
        case_id="B0",
    )
    if (
        v6.get("consumer_source_sha") != v6_contract.get("source", {}).get("sha")
        or v9_receipt.get("source_sha") != v9_contract.get("source", {}).get("sha")
        or v9_receipt.get("contract_path") != str(v9_contract_path)
    ):
        raise ValueError("V6/V9 producer report source identity differs from its contract")

    identity_case_fields = (
        "model_id", "run_id", "method", "mpi_size", "input_sha256",
        "physical_model_sha256", "resolved_config_sha256", "profile_identity",
        "solver_stage", "comparison_group", "geometry_identity",
    )
    v6_case = v6_contract.get("case")
    v9_case = v9_contract.get("case")
    if not isinstance(v6_case, Mapping) or not isinstance(v9_case, Mapping):
        raise ValueError("V6/V9 producer contracts omit their B0 case identity")
    case_identity = {
        key: {"v6": v6_case.get(key), "v9": v9_case.get(key)}
        for key in identity_case_fields
    }
    missing_case_fields = [
        key for key, values in case_identity.items()
        if values["v6"] is None or values["v9"] is None
    ]
    differing_case_fields = [
        key for key, values in case_identity.items()
        if values["v6"] is not None and values["v9"] is not None
        and values["v6"] != values["v9"]
    ]
    if missing_case_fields or differing_case_fields:
        raise ValueError(
            "V6/V9 B0 identity mismatch before array scan: "
            f"missing={missing_case_fields}, differing={differing_case_fields}"
        )

    v6_identity_audit = v6.get("identity_audit")
    v6_evaluator = (
        v6_identity_audit.get("candidate_evaluator_audit")
        if isinstance(v6_identity_audit, Mapping)
        else None
    )
    v6_gate = (
        v6_identity_audit.get("candidate_full_action_gate")
        if isinstance(v6_identity_audit, Mapping)
        else None
    )
    v9_gate = v9.get("candidate_full_action_gate")
    if not all(isinstance(item, Mapping) for item in (v6_identity_audit, v6_evaluator, v6_gate, v9_gate)):
        raise ValueError("V6/V9 reports omit evaluator or full-action identity metadata")
    v6_columns = v6_gate.get("columns")
    v9_columns = v9_gate.get("columns")
    def column_indices(value: Any) -> list[int]:
        if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
            raise ValueError("saved y/g full-action column metadata is malformed")
        result = [item.get("column") for item in value]
        if result != [0, 1]:
            raise ValueError("saved y/g evidence must bind ordered columns 0 and 1")
        return result

    if column_indices(v6_columns) != column_indices(v9_columns):
        raise ValueError("V6/V9 saved y/g column order differs")
    v6_cache_id = v6_identity_audit.get("candidate_evaluator_cache_identity")
    v9_cache_id = v9.get("candidate_evaluator_cache_identity")
    v6_evaluator_id = v6_identity_audit.get("candidate_evaluator_identity")
    v9_evaluator_id = v9.get("candidate_evaluator_identity")
    if (
        v6_evaluator_id != v9_evaluator_id
        or v6_cache_id != v9_cache_id
        or not isinstance(v6_evaluator, Mapping)
        or v6_evaluator.get("cache_identity") != v6_cache_id
        or v6_evaluator.get("cache_identity_sha256")
        != str(v6_cache_id).rsplit(":", 1)[-1]
    ):
        raise ValueError("V6/V9 evaluator or integration cache identity differs")
    if (
        v6.get("donor_manifest_sha256") != v9.get("donor_manifest_sha256")
        or v6.get("geometry_policy") != v9.get("geometry_policy")
        or v6_identity_audit.get("active_rows") != v9.get("active_rows")
        or v6_identity_audit.get("saved_port_rows") != v9.get("appended_rows")
        or v9.get("internal_rhs_strategy") != TASK41_B0_V9_INTERNAL_RHS_STRATEGY
        or v9_contract.get("numerical_strategy", {}).get("internal_rhs_strategy")
        != TASK41_B0_V9_INTERNAL_RHS_STRATEGY
    ):
        raise ValueError("V6/V9 donor, row map, geometry, or RHS identity differs")
    shared_donor_identity, _shared_donor_metadata_paths = (
        _task41_p0_saved_y_g_common_donor_identity(
            repo_root=root,
            expected_manifest_sha256=str(v6.get("donor_manifest_sha256", "")),
            active_rows=v6_identity_audit["active_rows"],
            port_rows=v9["appended_rows"],
            expected_shape=expected_shape,
        )
    )

    def denominator_by_column(columns: Sequence[Mapping[str, Any]]) -> list[float]:
        values = [item.get("frozen_denominator") for item in columns]
        if len(values) != 2 or any(type(value) not in (int, float) or value <= 0 for value in values):
            raise ValueError("saved y/g frozen known-field denominators are malformed")
        return [float(value) for value in values]

    v6_denominators = denominator_by_column(v6_columns)
    v9_denominators = denominator_by_column(v9_columns)
    if v6_denominators != v9_denominators:
        raise ValueError("V6/V9 known-field denominators differ")
    if v9_gate.get("relative_tolerance") != v6_gate.get("relative_tolerance"):
        raise ValueError("V6/V9 frozen full-action tolerance differs")

    def find_artifact(report: Mapping[str, Any], name: str) -> Mapping[str, Any]:
        inventory = report.get("persisted_evidence_arrays")
        if not isinstance(inventory, list):
            raise ValueError("V6 saved report omits persisted evidence arrays")
        matches = [item for item in inventory if isinstance(item, Mapping) and item.get("name") == name]
        if len(matches) != 1:
            raise ValueError(f"V6 report must bind exactly one {name} artifact")
        return matches[0]

    v6_action_name = v6_gate.get("full_action_artifact")
    v6_rhs_name = v6_gate.get("full_reduced_rhs_artifact")
    if not isinstance(v6_action_name, str) or not isinstance(v6_rhs_name, str):
        raise ValueError("V6 full-action report omits its named y/g arrays")
    v6_y = find_artifact(v6, v6_action_name)
    v6_g = find_artifact(v6, v6_rhs_name)
    v9_y = v9_gate.get("full_action_artifact")
    v9_g = v9_gate.get("full_reduced_rhs_artifact")
    if not isinstance(v9_y, Mapping) or not isinstance(v9_g, Mapping):
        raise ValueError("V9 compact report omits its named y/g arrays")

    def artifact_path(record: Mapping[str, Any], basis: Path, label: str) -> Path:
        raw = record.get("path")
        digest = record.get("sha256")
        byte_count = record.get("bytes")
        if (
            not isinstance(raw, str)
            or not isinstance(digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
            or type(byte_count) is not int
            or record.get("dtype") != "complex128"
            or record.get("shape") != list(expected_shape)
        ):
            raise ValueError(f"{label} file identity is malformed before array scan")
        path = Path(raw)
        path = (path if path.is_absolute() else basis / path).resolve(strict=True)
        if not path.is_relative_to(basis.resolve(strict=True)):
            raise ValueError(f"{label} must remain inside its bound producer run")
        return path

    v6_y_path = artifact_path(v6_y, v6_report_path.parent, "V6 y")
    v6_g_path = artifact_path(v6_g, v6_report_path.parent, "V6 g")
    v9_y_path = artifact_path(v9_y, output_root, "V9 y")
    v9_g_path = artifact_path(v9_g, output_root, "V9 g")

    # Record source/window identity separately. A different consumer source or
    # window is expected for this retrospective comparison and is not an
    # operator-equality claim. Per-key LU identity was not persisted by V6.
    source_window_bindings = {}
    for label, producer_contract in (("v6", v6_contract), ("v9", v9_contract)):
        source_window_bindings[label] = {
            "source_sha": producer_contract.get("source", {}).get("sha"),
            "contract_path": str(v6_contract_path if label == "v6" else v9_contract_path),
            "contract_sha256": v6_contract_sha if label == "v6" else v9_contract_sha,
            "window_path": producer_contract.get("window", {}).get("path"),
            "window_sha256": producer_contract.get("window", {}).get("sha256"),
            "entry_source_sha": producer_contract.get("window", {}).get("entry_source_sha"),
        }
    v6_identity = {
        "source_sha": source_window_bindings["v6"]["source_sha"],
        "input_sha256": v6_case["input_sha256"],
        "physical_model_sha256": v6_case["physical_model_sha256"],
        "column_identity": column_indices(v6_columns),
        "active_ordering_sha256": None,
        "evaluator_identity": v6_evaluator_id,
        "kernel_identity": v6_evaluator.get("full_form_signature"),
        "cache_identity": v6_cache_id,
        "h_identity": None,
    }
    v9_identity = {
        "source_sha": source_window_bindings["v9"]["source_sha"],
        "input_sha256": v9_case["input_sha256"],
        "physical_model_sha256": v9_case["physical_model_sha256"],
        "column_identity": column_indices(v9_columns),
        "active_ordering_sha256": None,
        "evaluator_identity": v9_evaluator_id,
        "kernel_identity": None,
        "cache_identity": v9_cache_id,
        "h_identity": None,
    }
    compared = compare_task41_p0_b0_saved_y_g_arrays(
        v6_y_path=v6_y_path,
        v6_g_path=v6_g_path,
        v9_y_path=v9_y_path,
        v9_g_path=v9_g_path,
        expected_sha256s={
            "v6_y": str(v6_y["sha256"]),
            "v6_g": str(v6_g["sha256"]),
            "v9_y": str(v9_y["sha256"]),
            "v9_g": str(v9_g["sha256"]),
        },
        expected_shape=expected_shape,
        trace_rows=trace_rows,
        target_rows=target_rows,
        denominators=tuple(v6_denominators),
        block_rows=block_rows,
        v6_identity=v6_identity,
        v9_identity=v9_identity,
    )
    compared.update(
        status="COMPLETED",
        classification="SAVED_VECTOR_COMPARISON_DIAGNOSTIC_ONLY",
        official_result=False,
        errors=[],
        v6_report={"path": str(v6_report_path), "sha256": v6_report_sha256},
        v9_report={"path": str(v9_report_path), "sha256": v9_report_sha256},
        v9_summary={"path": str(v9_summary_path), "sha256": v9_summary_sha256},
        v9_service_receipt={
            "path": str(v9_service_receipt_path),
            "sha256": v9_service_receipt_sha256,
        },
        producer_case_identity=case_identity,
        source_window_bindings=source_window_bindings,
        saved_operand_roles={
            "y": "full_p6_action_vector",
            "g": "full_reduced_rhs_vector",
            "v6_rhs_reducer": v6_identity_audit.get("rhs_reducer"),
            "v9_internal_rhs_strategy": v9.get("internal_rhs_strategy"),
            "frozen_known_field_denominators": v6_denominators,
            "donor_manifest_sha256": v6.get("donor_manifest_sha256"),
        },
        map_and_evaluator_identity={
            "columns": [0, 1],
            "active_rows": v6_identity_audit.get("active_rows"),
            "saved_port_rows": v6_identity_audit.get("saved_port_rows"),
            "row_ordering_sha256": "UNKNOWN_NOT_PRESENT_IN_COMPACT_REPORTS",
            "evaluator_identity": v6_evaluator_id,
            "cache_identity": v6_cache_id,
            "integration_identity_payload_sha256": v6_evaluator.get("cache_identity_sha256"),
            "old_lu_per_key_sha256": "UNKNOWN_NOT_PERSISTED_BY_V6_REPORT",
        },
        shared_donor_identity=shared_donor_identity,
        identity_compatibility={
            "status": "COMPATIBLE_FOR_SAVED_VECTOR_DIAGNOSTICS",
            "equal_case_fields": identity_case_fields,
            "source_and_window_equality_required": False,
            "same_operator_claim": False,
            "reason": "producer sources/windows differ and full per-key operator/LU identities are unavailable",
        },
    )
    output = Path(output_path).resolve()
    if output.exists():
        raise ValueError("saved y/g comparison output must be new")
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(compared, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    if len(payload.encode("utf-8")) > TASK41_B0_SAVED_DIAGNOSTICS_SCOPE["new_evidence_limit_bytes"]:
        raise ValueError("saved y/g comparison exceeds the saved-diagnostics new-evidence cap")
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    try:
        os.link(temporary, output)
    except FileExistsError as exc:
        raise ValueError("saved y/g comparison output appeared concurrently") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return compared


def evaluate_task41_numerical_summary(
    summary: Mapping[str, Any], numerical_output_directory: str | Path
) -> list[str]:
    """Recompute Task41 native full-space A6, recovery, MUMPS, and energy gates."""
    return task41_direct_summary_errors(summary, numerical_output_directory)


def _task41_a2_diagnostic_inventory_from_data(
    metrics: Mapping[str, Any],
    orders: Any,
    *,
    expected_m_max: int,
    expected_n_max: int,
) -> dict[str, Any]:
    """Recompute the diagnostic grid from raw rows, independently of worker status."""
    rows = orders if isinstance(orders, list) else []
    valid_bounds = (
        type(expected_m_max) is int
        and expected_m_max >= 0
        and type(expected_n_max) is int
        and expected_n_max >= 0
    )
    expected = (
        {
            (m, n, pol)
            for m in range(-expected_m_max, expected_m_max + 1)
            for n in range(-expected_n_max, expected_n_max + 1)
            for pol in ("s", "p")
        }
        if valid_bounds
        else set()
    )
    actual: list[tuple[int, int, str]] = []
    malformed = 0
    for row in rows:
        if (
            not isinstance(row, Mapping)
            or type(row.get("m")) is not int
            or type(row.get("n")) is not int
            or row.get("polarization") not in {"s", "p"}
        ):
            malformed += 1
            continue
        actual.append((row["m"], row["n"], row["polarization"]))
    spatial_count = len(expected) // 2
    channel_count = len(expected)
    checks = {
        "resolved_reporting_bounds_match_frozen_config": bool(
            valid_bounds
            and metrics.get("diffraction_order_max_m_requested") == expected_m_max
            and metrics.get("diffraction_order_max_n_requested") == expected_n_max
            and metrics.get("diffraction_order_max_m_resolved") == expected_m_max
            and metrics.get("diffraction_order_max_n_resolved") == expected_n_max
        ),
        "spatial_counts_match_frozen_grid": bool(
            metrics.get("diffraction_order_count") == spatial_count
            and metrics.get("diffraction_fit_order_count") == spatial_count
        ),
        "polarized_row_count_matches_grid": len(rows) == channel_count,
        "channel_count_matches_grid": metrics.get("diffraction_channel_count") == channel_count,
        "raw_polarization_keys_are_unique_and_complete": bool(
            malformed == 0 and len(actual) == len(set(actual)) and set(actual) == expected
        ),
    }
    return {
        "schema": "task41.p0.independent_diagnostic_inventory.v1",
        "frozen_reporting_order_bounds": {
            "m_max": expected_m_max,
            "n_max": expected_n_max,
        },
        "expected_spatial_order_count": spatial_count,
        "expected_channel_count": channel_count,
        "actual_order_rows": len(rows),
        "malformed_order_rows": malformed,
        "checks": checks,
        "passed": all(checks.values()),
    }


def _json_object(path: Path, label: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object")
    return value


def _task41_artifact_path(root: Path, binding: Mapping[str, Any], name: str) -> Path:
    artifacts = binding["a1"]["comparison_artifacts"]
    record = artifacts[name]
    raw = Path(str(record["path"]))
    path = (raw if raw.is_absolute() else root / raw).resolve(strict=True)
    if path.stat().st_size != record["bytes"] or sha256_file(path) != record["sha256"]:
        raise ValueError(f"bound A1 comparison artifact changed: {name}")
    return path


def _task41_npz_array(path: Path, key: str) -> np.ndarray:
    import numpy as np

    with np.load(path, allow_pickle=False) as arrays:
        if key not in arrays.files:
            raise ValueError(f"Task41 bound NPZ artifact omits {key!r}")
        return np.array(arrays[key], copy=True)


def _task40_packet_array(packet: Mapping[str, Any], key: str) -> np.ndarray:
    arrays_record = packet.get("arrays")
    if not isinstance(arrays_record, Mapping):
        raise ValueError("Task41 output packet omits its array manifest")
    npz_path = Path(str(arrays_record.get("path", ""))).resolve(strict=True)
    if sha256_file(npz_path) != arrays_record.get("sha256"):
        raise ValueError("Task41 output packet NPZ hash changed")
    with np.load(npz_path, allow_pickle=False) as arrays:
        reference = packet.get(key)
        if not isinstance(reference, Mapping) or reference.get("array_key") not in arrays.files:
            raise ValueError(f"Task41 output packet omits raw array {key!r}")
        value = np.asarray(arrays[reference["array_key"]])
        if list(value.shape) != reference.get("shape") or str(value.dtype) != reference.get("dtype"):
            raise ValueError(f"Task41 output packet array identity changed for {key}")
        return np.array(value, copy=True)


def _load_task41_a2_full_solution(output_packet: Mapping[str, Any]) -> np.ndarray:
    scientific = output_packet.get("scientific_identity")
    if not isinstance(scientific, Mapping):
        raise ValueError("Task41 A2 official output omits scientific identity")
    residual_path = Path(str(scientific.get("full_solution_packet_json", ""))).resolve(strict=True)
    residual = _json_object(residual_path, "A2 full-solution residual packet")
    return _task40_packet_array(residual, "full_solution_storage").astype(np.complex128, copy=False)


def _task41_run_artifact(root: Path, record: Mapping[str, Any], label: str) -> Path:
    raw = Path(str(record.get("path", "")))
    path = (raw if raw.is_absolute() else root / raw).resolve(strict=True)
    if (
        not path.is_relative_to(root.resolve())
        or (
            record.get("bytes") is not None
            and (
                type(record.get("bytes")) is not int
                or path.stat().st_size != record["bytes"]
            )
        )
        or not isinstance(record.get("sha256"), str)
        or sha256_file(path) != record.get("sha256")
    ):
        raise ValueError(f"Task41 A2 {label} artifact is outside its run or changed")
    return path


def _task41_npy_artifact(
    root: Path, record: Mapping[str, Any], label: str
) -> np.ndarray:
    path = _task41_run_artifact(root, record, label)
    value = np.load(path, mmap_mode="r", allow_pickle=False)
    if (
        not isinstance(value, np.ndarray)
        or (record.get("shape") is not None and list(value.shape) != record.get("shape"))
        or (
            record.get("dtype") is not None
            and np.dtype(value.dtype) != np.dtype(str(record.get("dtype")))
        )
    ):
        raise ValueError(f"Task41 A2 {label} array identity changed")
    return value


def _task41_b0_owned_writable_lu_pivots(
    raw_pivots: np.ndarray, *, order: int
) -> np.ndarray:
    """Copy validated SciPy 0-based pivots into writable owned int32 storage."""
    pivots = np.asarray(raw_pivots)
    if (
        type(order) is not int
        or order < 1
        or order > np.iinfo(np.int32).max
        or pivots.shape != (order,)
        or pivots.dtype.kind not in "iu"
        or not np.isfinite(pivots).all()
    ):
        raise ValueError("Task41 B0 LU pivots have an invalid zero-based layout")
    zero_based_steps = np.arange(order, dtype=np.int64)
    if np.any(pivots < zero_based_steps) or np.any(pivots >= order):
        raise ValueError("Task41 B0 LU pivots are outside SciPy's zero-based pivot range")
    writable = np.array(pivots, dtype=np.int32, order="C", copy=True)
    if not writable.flags.owndata or not writable.flags.writeable:
        raise ValueError("Task41 B0 LU pivots were not copied to writable owned storage")
    return writable


def _task41_sparse_identity(matrix: Any) -> str:
    digest = hashlib.sha256()
    digest.update(str(matrix.format).encode("ascii"))
    digest.update(np.asarray(matrix.shape, dtype=np.int64).tobytes())
    digest.update(np.dtype(matrix.dtype).str.encode("ascii"))
    for name in ("indptr", "indices", "data"):
        values = np.ascontiguousarray(getattr(matrix, name))
        digest.update(name.encode("ascii"))
        digest.update(values.dtype.str.encode("ascii"))
        digest.update(np.asarray(values.shape, dtype=np.int64).tobytes())
        digest.update(memoryview(values).cast("B"))
    return digest.hexdigest()


def _task41_relative_vector_error(actual: np.ndarray, expected: np.ndarray) -> float:
    left = np.asarray(actual, dtype=np.complex128).reshape(-1)
    right = np.asarray(expected, dtype=np.complex128).reshape(-1)
    if left.shape != right.shape or not np.isfinite(left).all() or not np.isfinite(right).all():
        raise ValueError("Task41 A2 independent vector action has invalid shape or values")
    return float(
        np.linalg.norm(left - right)
        / max(float(np.linalg.norm(right)), np.finfo(float).tiny)
    )


def _task41_a2_verify_saved_q_consumer_receipt(
    *,
    repo_root: Path,
    artifact_root: Path,
    reuse_binding: Mapping[str, Any],
    consumer_execution: Mapping[str, Any],
    q: int,
    entry: Mapping[str, Any],
    receipt: Mapping[str, Any],
    manifest_path: Path,
    qualification_path: Path,
    manifest: Mapping[str, Any],
    qualification: Mapping[str, Any],
) -> None:
    """Recheck the immutable prior native PASS and the new consumer receipt."""
    from src.solvers.task40_v10_p6_periodic_profile import TASK41_G13_A2_P6_PROFILE
    from src.solvers.task40_v30_qualified_q_csr import make_v31_q_csr_import_authorization

    expected_twist = q % TASK41_G13_A2_P6_PROFILE.replication_count
    authorization_map = reuse_binding.get("consumer_import_authorizations")
    expected_authorization = (
        authorization_map.get(str(q)) if isinstance(authorization_map, Mapping) else None
    )
    consumer_ref = receipt.get("consumer_receipt")
    if not isinstance(expected_authorization, Mapping) or not isinstance(consumer_ref, Mapping):
        raise ValueError(f"Task41 A2 imported q={q} omits its contract authorization or consumer receipt")
    consumer_path = _task41_run_artifact(
        artifact_root, consumer_ref, f"q{q} V31 consumer receipt"
    )
    consumer = _json_object(consumer_path, f"q={q} V31 consumer receipt")
    manifest_ref = entry.get("csr_manifest")
    qualification_ref = entry.get("native_qualification")
    matrix_source = manifest.get("matrix_source_identity")
    producer_execution = manifest.get("execution_identity")
    native_execution = qualification.get("execution_identity")
    artifacts = manifest.get("csr_artifacts")
    if (
        not isinstance(manifest_ref, Mapping)
        or not isinstance(qualification_ref, Mapping)
        or not isinstance(matrix_source, Mapping)
        or not isinstance(producer_execution, Mapping)
        or not isinstance(native_execution, Mapping)
        or not isinstance(artifacts, Mapping)
    ):
        raise ValueError(f"Task41 A2 imported q={q} saved producer records are incomplete")
    normalized_artifacts = {}
    for name in ("data", "indices", "indptr"):
        record = artifacts.get(name)
        if not isinstance(record, Mapping):
            raise ValueError(f"Task41 A2 imported q={q} CSR manifest omits {name}")
        raw_path = Path(str(record.get("path", "")))
        artifact_path = (raw_path if raw_path.is_absolute() else manifest_path.parent / raw_path).resolve()
        if not artifact_path.is_relative_to(repo_root):
            raise ValueError(f"Task41 A2 imported q={q} CSR {name} escaped the repository")
        normalized_artifacts[name] = {
            "path": str(artifact_path),
            "bytes": record.get("bytes"),
            "sha256": record.get("sha256"),
        }
    expected = make_v31_q_csr_import_authorization(
        q_index=q,
        twist_index=expected_twist,
        profile=str(manifest.get("profile", "")),
        operator_identity=manifest.get("operator_identity", {}),
        matrix_source_identity=matrix_source,
        producer_identity=manifest.get("producer_identity", {}),
        producer_execution_identity=producer_execution,
        native_execution_identity=native_execution,
        csr_manifest_sha256=str(manifest_ref.get("sha256", "")),
        native_qualification_sha256=str(qualification_ref.get("sha256", "")),
        csr_artifacts=normalized_artifacts,
        consumer_execution_identity=consumer_execution,
    )
    expected_consumer_sha = hashlib.sha256(
        json.dumps(expected, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    if (
        expected != expected_authorization
        or receipt.get("qualification_kind") != "V30_NATIVE_PASS"
        or receipt.get("qualification_status") != "PASS"
        or receipt.get("csr_manifest_path") != str(manifest_path)
        or receipt.get("csr_manifest_sha256") != manifest_ref.get("sha256")
        or receipt.get("native_qualification_path") != str(qualification_path)
        or receipt.get("native_qualification_sha256") != qualification_ref.get("sha256")
        or receipt.get("selector_sha256") != reuse_binding.get("selector_sha256")
        or consumer.get("schema") != "task40extra.review_v31_q_csr_consumer_receipt.v1"
        or consumer.get("status") != "CONSUMED_COMPLETE_CSR_NATIVE_PASS"
        or consumer.get("q_index") != q
        or consumer.get("twist_index") != expected_twist
        or manifest.get("twist_index") != expected_twist
        or qualification.get("twist_index") != expected_twist
        or entry.get("twist_index") != expected_twist
        or consumer.get("profile") != manifest.get("profile")
        or consumer.get("operator_identity") != manifest.get("operator_identity")
        or consumer.get("matrix_source_identity") != matrix_source
        or consumer.get("producer_identity") != manifest.get("producer_identity")
        or consumer.get("producer_execution_identity") != producer_execution
        or consumer.get("native_execution_identity") != native_execution
        or consumer.get("consumer_execution_identity") != consumer_execution
        or consumer.get("csr_manifest")
        != {"path": str(manifest_path), "sha256": manifest_ref.get("sha256")}
        or consumer.get("native_qualification")
        != {
            "path": str(qualification_path),
            "sha256": qualification_ref.get("sha256"),
            "status": "PASS",
        }
        or consumer.get("authorization") != expected
        or consumer.get("authorization_sha256") != expected_consumer_sha
        or consumer.get("csr_artifacts") != normalized_artifacts
        or consumer.get("original_manifest_and_native_pass_rewritten") is not False
    ):
        raise ValueError(f"Task41 A2 imported q={q} consumer receipt does not preserve its producer PASS")


def _task41_iterative_reference_audit_checks(
    summary: Mapping[str, Any],
    numerical_output: Path,
    *,
    repo_root: Path | None = None,
    case_id: str = "A2",
    b0_profile_capability: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Reapply saved q CSR actions and both factor probe residuals from raw vectors."""
    from scipy import sparse

    from src.solvers.task40_v10_p6_periodic_profile import (
        TASK41_G13_A2_P6_PROFILE,
        task41_b0_periodic_profile,
    )

    if case_id not in {"A2", "B0"}:
        raise ValueError("Task41 iterative audit supports only A2 or B0")
    if case_id == "B0":
        if (
            not isinstance(b0_profile_capability, Mapping)
            or b0_profile_capability.get("verified") is not True
            or b0_profile_capability.get("identity") != TASK41_B0_PRECONDITIONER
        ):
            raise ValueError("Task41 B0 iterative audit requires its reopened profile capability")
        profile = task41_b0_periodic_profile(
            tuple(map(int, b0_profile_capability.get("q_port_counts", ()))),
            tuple(map(int, b0_profile_capability.get("sector_port_counts", ()))),
        )
    else:
        profile = TASK41_G13_A2_P6_PROFILE

    artifact_root = numerical_output.parent.resolve()
    repo_root = Path(repo_root or Path(__file__).resolve().parents[2]).resolve()
    authority = summary.get("campaign_authority", {})
    reuse_binding = (
        authority.get("q_csr_reuse") if isinstance(authority, Mapping) else None
    )
    consumer_execution = {
        "source_sha": authority.get("source_sha") if isinstance(authority, Mapping) else None,
        "window_sha256": (
            authority.get("campaign_window_sha256")
            if isinstance(authority, Mapping)
            else None
        ),
    }
    imported_saved_q_indices: set[int] = set()
    snapshot = summary.get("reference_audit_snapshot")
    if not isinstance(snapshot, Mapping):
        raise ValueError("Task41 A2 worker summary omits its pre-destroy reference audit")
    sectors = snapshot.get("sector_audits_before_destroy")
    factor = snapshot.get("factor_audit_before_destroy")
    q_matrix_audits = snapshot.get("q_matrix_audits_before_destroy")
    if (
        not isinstance(sectors, list)
        or len(sectors) != profile.replication_count
        or not isinstance(factor, Mapping)
        or not isinstance(q_matrix_audits, Mapping)
    ):
        raise ValueError("Task41 A2 reference audit omits five sectors or its All-Q factor audit")

    q_count = profile.q_count
    q_indices = list(range(q_count))
    if (
        factor.get("all_q_required") != q_indices
        or factor.get("numeric_ready_q") != q_indices
        or factor.get("all_q_numeric_ready") is not True
        or factor.get("all_q_factors_retained_simultaneously") is not True
        or factor.get("all_q_factor_objects_live_simultaneously") is not True
        or factor.get("all_q_numeric_factors_strict_true_residual_passed") is not True
        or factor.get("all_q_second_rhs_strict_true_residual_passed") is not True
        or factor.get("all_q_fresh_probe_and_second_rhs_passed") is not True
        or factor.get("factors_live_count_current") != q_count
        or factor.get("strict_factor_qualification_required") is not True
    ):
        raise ValueError("Task41 A2 All-Q factor audit does not record ten live strict q factors")
    second_contract = factor.get("second_rhs_qualification")
    if (
        not isinstance(second_contract, Mapping)
        or second_contract.get("schema") != f"task41.p0.{case_id.lower()}_all_q_second_rhs.v1"
        or second_contract.get("formula")
        != "real=2+(index mod 17)/17; imag=1.5+(index mod 13)/13"
        or second_contract.get("strict_limit") != 1.0e-10
        or second_contract.get("all_entries_nonzero") is not True
        or second_contract.get("distinct_from_direct_cos_sin_probe") is not True
    ):
        raise ValueError("Task41 A2 All-Q factor audit has the wrong strict second-RHS contract")

    def by_q(rows: Any, label: str) -> dict[int, Mapping[str, Any]]:
        if not isinstance(rows, list):
            raise ValueError(f"Task41 A2 All-Q {label} inventory is missing")
        result: dict[int, Mapping[str, Any]] = {}
        for row in rows:
            if not isinstance(row, Mapping) or type(row.get("q")) is not int:
                raise ValueError(f"Task41 A2 All-Q {label} row is malformed")
            q = int(row["q"])
            if q in result:
                raise ValueError(f"Task41 A2 All-Q {label} repeats q={q}")
            result[q] = row
        if set(result) != set(q_indices):
            raise ValueError(f"Task41 A2 All-Q {label} does not cover q=0..9")
        return result

    factor_tests = by_q(factor.get("factor_tests"), "fresh factor probes")
    second_tests = by_q(factor.get("second_rhs_tests"), "second-RHS probes")
    factor_inputs = by_q(factor.get("factor_inputs"), "factor input identities")

    sector_by_q: dict[int, tuple[Mapping[str, Any], Mapping[str, Any], Mapping[str, Any]]] = {}
    expected_sector_pairs = {
        (twist, twist + profile.replication_count)
        for twist in range(profile.replication_count)
    }
    actual_sector_pairs: set[tuple[int, int]] = set()
    for sector_index, sector in enumerate(sectors):
        if not isinstance(sector, Mapping):
            raise ValueError(f"Task41 A2 sector audit {sector_index} is malformed")
        raw_pair = sector.get("q_indices")
        if not isinstance(raw_pair, list) or len(raw_pair) != 2:
            raise ValueError(f"Task41 A2 sector audit {sector_index} lacks its q pair")
        pair = tuple(sorted(int(q) for q in raw_pair))
        if pair not in expected_sector_pairs or pair in actual_sector_pairs:
            raise ValueError("Task41 A2 sector audit has an unexpected or duplicate q pair")
        actual_sector_pairs.add(pair)
        preparation = sector.get(f"task41_{case_id.lower()}_independent_q_csr_preparation")
        if not isinstance(preparation, Mapping):
            raise ValueError(f"Task41 A2 sector {pair} omits its independent CSR preparation")
        saved_import = (
            preparation.get("schema")
            == "task41.p0.a2_saved_q_csr_import_audit.v1"
        )
        identity = preparation.get("qualification_identity")
        if saved_import:
            if case_id != "A2":
                raise ValueError("Task41 B0 cannot use saved A1/A2 q-CSR evidence")
            from src.runners.task41_p0_contract import (
                TASK41_A2_Q_CSR_REUSE_SCHEMA,
                TASK41_A2_Q_CSR_REUSE_SCHEMA_V1,
            )

            pair_twist = pair[0]
            binding_schema = (
                reuse_binding.get("schema") if isinstance(reuse_binding, Mapping) else None
            )
            authorization_rows = (
                reuse_binding.get("consumer_import_authorizations")
                if isinstance(reuse_binding, Mapping)
                else None
            )
            if binding_schema == TASK41_A2_Q_CSR_REUSE_SCHEMA_V1:
                authorized_binding = (
                    isinstance(authorization_rows, Mapping)
                    and pair == (0, 5)
                    and reuse_binding.get("q_indices") == [0, 5]
                    and reuse_binding.get("twist_index") == 0
                    and set(authorization_rows) == {"0", "5"}
                )
            elif binding_schema == TASK41_A2_Q_CSR_REUSE_SCHEMA:
                expected_q_indices = list(range(profile.q_count))
                expected_twists = {
                    str(q): q % profile.replication_count
                    for q in expected_q_indices
                }
                authorized_binding = (
                    isinstance(authorization_rows, Mapping)
                    and reuse_binding.get("q_indices") == expected_q_indices
                    and reuse_binding.get("twist_indices_by_q") == expected_twists
                    and set(authorization_rows) == {str(q) for q in expected_q_indices}
                )
            else:
                authorized_binding = False
            if (
                not authorized_binding
                or preparation.get("qualification_origin")
                != "saved_v30_native_pass_cross_window_import"
                or preparation.get("selected_q_indices") != list(pair)
                or preparation.get("imported_saved_q_indices") != list(pair)
                or preparation.get("twist_index") != pair_twist
                or preparation.get("all_complete_native_pass") is not True
                or preparation.get("four_complete_csr_actions_passed") is not True
                or preparation.get("paired_sector_leakage_passed") is not True
                or not isinstance(identity, Mapping)
                or identity.get("q_indices") != list(pair)
                or identity.get("twist_index") != pair_twist
                or identity.get("profile_identity") != profile.identity()
                or not isinstance(consumer_execution.get("source_sha"), str)
                or not isinstance(consumer_execution.get("window_sha256"), str)
            ):
                raise ValueError("Task41 A2 saved q import is not authorized for its exact paired sector")
        elif (
            preparation.get("selected_q_indices") != list(pair)
            or preparation.get("all_complete_native_pass") is not True
            or preparation.get("four_complete_csr_actions_passed") is not True
            or preparation.get("paired_sector_leakage_passed") is not True
            or not isinstance(identity, Mapping)
            or identity.get("q_indices") != list(pair)
            or identity.get("twist_index") != pair[0]
            or identity.get("profile_identity") != profile.identity()
        ):
            raise ValueError(f"Task41 A2 sector {pair} failed its saved CSR qualification gates")
        entries = preparation.get("selector_entries")
        receipts = preparation.get("qualification_receipts")
        native_facts = preparation.get("native_facts_by_q")
        if (
            not isinstance(entries, list)
            or not isinstance(receipts, list)
            or len(entries) != 2
            or len(receipts) != 2
            or (
                not saved_import
                and (
                    not isinstance(native_facts, Mapping)
                    or set(native_facts) != {str(q) for q in pair}
                )
            )
        ):
            raise ValueError(f"Task41 A2 sector {pair} does not preserve both q receipts")
        entries_by_q = {int(row["q_index"]): row for row in entries if isinstance(row, Mapping)}
        receipts_by_q = {int(row["q_index"]): row for row in receipts if isinstance(row, Mapping)}
        if set(entries_by_q) != set(pair) or set(receipts_by_q) != set(pair):
            raise ValueError(f"Task41 A2 sector {pair} has a malformed q receipt inventory")
        for q in pair:
            entry = entries_by_q[q]
            receipt = receipts_by_q[q]
            facts = native_facts[str(q)] if isinstance(native_facts, Mapping) else None
            if saved_import:
                if (
                    entry.get("twist_index") != pair[0]
                    or receipt.get("q_index") != q
                    or receipt.get("twist_index") != pair[0]
                    or receipt.get("qualification_kind") != "V30_NATIVE_PASS"
                    or receipt.get("qualification_status") != "PASS"
                    or not isinstance(receipt.get("maximum_relative_error"), (int, float))
                    or receipt.get("maximum_relative_error") > 1.0e-11
                ):
                    raise ValueError(f"Task41 A2 q={q} saved native PASS receipt is incomplete")
            elif (
                entry.get("twist_index") != pair[0]
                or receipt.get("twist_index") != pair[0]
                or entry.get("manifest_status") != "COMPLETE_CSR"
                or entry.get("qualification_status") != "PASS"
                or receipt.get("manifest_status") != "COMPLETE_CSR"
                or receipt.get("qualification_status") != "PASS"
                or not isinstance(facts, Mapping)
                or facts.get("status") != "PASS"
                or facts.get("four_complete_csr_actions_passed") is not True
                or facts.get("paired_sector_leakage_passed") is not True
            ):
                raise ValueError(f"Task41 A2 q={q} selector receipt is not a complete native PASS")
            manifest_ref = entry.get("csr_manifest")
            qualification_ref = entry.get("native_qualification")
            if not isinstance(manifest_ref, Mapping) or not isinstance(qualification_ref, Mapping):
                raise ValueError(f"Task41 A2 q={q} selector entry omits hash-bound receipts")
            if saved_import:
                if (
                    Path(str(receipt.get("csr_manifest_path", ""))).resolve()
                    != Path(str(manifest_ref.get("path", ""))).resolve()
                    or receipt.get("csr_manifest_sha256") != manifest_ref.get("sha256")
                    or Path(str(receipt.get("native_qualification_path", ""))).resolve()
                    != Path(str(qualification_ref.get("path", ""))).resolve()
                    or receipt.get("native_qualification_sha256") != qualification_ref.get("sha256")
                ):
                    raise ValueError(f"Task41 A2 q={q} imported selector and provider receipt hashes disagree")
            elif (
                receipt.get("csr_manifest_path") != manifest_ref.get("path")
                or receipt.get("csr_manifest_sha256") != manifest_ref.get("sha256")
                or receipt.get("native_qualification_path") != qualification_ref.get("path")
                or receipt.get("native_qualification_sha256") != qualification_ref.get("sha256")
                or facts.get("csr_manifest_sha256") != manifest_ref.get("sha256")
                or facts.get("native_qualification_sha256") != qualification_ref.get("sha256")
            ):
                raise ValueError(f"Task41 A2 q={q} sector receipt hashes disagree")
            evidence_root = repo_root if saved_import else artifact_root
            manifest_path = _task41_run_artifact(
                evidence_root, manifest_ref, f"q{q} CSR manifest"
            )
            qualification_path = _task41_run_artifact(
                evidence_root, qualification_ref, f"q{q} native qualification"
            )
            manifest = _json_object(manifest_path, f"q={q} CSR manifest")
            qualification = _json_object(qualification_path, f"q={q} native qualification")
            if (
                manifest.get("schema") != "task40extra.review_v30_q_csr.v1"
                or manifest.get("status") != "COMPLETE_CSR"
                or manifest.get("q_index") != q
                or manifest.get("twist_index") != pair[0]
                or manifest.get("profile") != profile.name
                or manifest.get("shape") != entry.get("shape")
                or qualification.get("schema")
                != "task40extra.review_v30_q_csr_native_qualification.v1"
                or qualification.get("status") != "PASS"
                or qualification.get("q_index") != q
                or qualification.get("twist_index") != pair[0]
                or qualification.get("csr_manifest_sha256") != manifest_ref.get("sha256")
                or qualification.get("four_complete_csr_actions_passed") is not True
                or qualification.get("csr_action_count") != 4
                or qualification.get("paired_sector_leakage_passed") is not True
                or qualification.get("relative_error_limit") != 1.0e-11
                or qualification.get("maximum_relative_error")
                != receipt.get("maximum_relative_error")
            ):
                raise ValueError(f"Task41 A2 q={q} CSR manifest or qualification is invalid")
            arrays = qualification.get("native_array_artifacts")
            csr_artifacts = manifest.get("csr_artifacts")
            required_arrays = {
                *(f"input_{name}" for name in ("case1_full", "case1_trace_only", "case1_port_only", "case2_full")),
                *(f"csr_{name}" for name in ("case1_full", "case1_trace_only", "case1_port_only", "case2_full")),
                *(f"native_{name}" for name in ("case1_full", "case1_trace_only", "case1_port_only", "case2_full")),
                *(f"component_case1_{name}" for name in ("volume", "minus_D", "C", "Hhat")),
                "paired_peer_input",
                "paired_peer_native_diagonal",
                "paired_peer_native_cross",
                "paired_selected_native_cross",
            }
            if not isinstance(arrays, Mapping) or not required_arrays.issubset(arrays):
                raise ValueError(f"Task41 A2 q={q} CSR qualification omits required raw vectors")
            if not isinstance(csr_artifacts, Mapping) or set(csr_artifacts) != {"data", "indices", "indptr"}:
                raise ValueError(f"Task41 A2 q={q} CSR manifest omits its three arrays")
            if saved_import:
                _task41_a2_verify_saved_q_consumer_receipt(
                    repo_root=repo_root,
                    artifact_root=artifact_root,
                    reuse_binding=reuse_binding,
                    consumer_execution=consumer_execution,
                    q=q,
                    entry=entry,
                    receipt=receipt,
                    manifest_path=manifest_path,
                    qualification_path=qualification_path,
                    manifest=manifest,
                    qualification=qualification,
                )
                imported_saved_q_indices.add(q)
            sector_by_q[q] = (manifest, qualification, arrays)
        if actual_sector_pairs != expected_sector_pairs:
            continue
    if actual_sector_pairs != expected_sector_pairs or set(sector_by_q) != set(q_indices):
        raise ValueError("Task41 A2 sector audits do not cover all ten q branches")

    def load_csr(q: int):
        manifest, _qualification, _arrays = sector_by_q[q]
        records = manifest["csr_artifacts"]
        evidence_root = repo_root if q in imported_saved_q_indices else artifact_root
        data = _task41_npy_artifact(evidence_root, records["data"], f"q{q} CSR data")
        indices = _task41_npy_artifact(evidence_root, records["indices"], f"q{q} CSR indices")
        indptr = _task41_npy_artifact(evidence_root, records["indptr"], f"q{q} CSR indptr")
        if (
            data.dtype != np.dtype(np.complex128)
            or indices.dtype != np.dtype(np.int32)
            or indptr.dtype != np.dtype(np.int32)
            or len(manifest["shape"]) != 2
        ):
            raise ValueError(f"Task41 A2 q={q} CSR dtype or shape is invalid")
        matrix = sparse.csr_matrix(
            (data, indices, indptr), shape=tuple(manifest["shape"]), copy=False
        )
        if (
            matrix.shape[0] != matrix.shape[1]
            or matrix.nnz != manifest.get("stored_structural_slots")
            or not matrix.has_canonical_format
            or not matrix.has_sorted_indices
            or not np.isfinite(matrix.data).all()
        ):
            raise ValueError(f"Task41 A2 q={q} saved CSR is not finite canonical CSR")
        return matrix

    def load_factor_packet(
        packet_ref: Any, *, q: int, label: str, expected_rhs: np.ndarray,
        matrix: Any, recorded_relative: Any,
    ) -> float:
        if not isinstance(packet_ref, Mapping):
            raise ValueError(f"Task41 A2 q={q} {label} factor packet reference is missing")
        packet_path = _task41_run_artifact(artifact_root, packet_ref, f"q{q} {label} factor packet")
        if (
            packet_ref.get("array_names") != ["residual", "rhs", "solution"]
            or packet_ref.get("dtype") != np.dtype(np.complex128).str
            or packet_ref.get("rows") != matrix.shape[0]
            or packet_ref.get("readback_verified") is not True
        ):
            raise ValueError(f"Task41 A2 q={q} {label} factor packet metadata is invalid")
        with np.load(packet_path, allow_pickle=False) as packet:
            if set(packet.files) != {"rhs", "solution", "residual"}:
                raise ValueError(f"Task41 A2 q={q} {label} factor packet array inventory changed")
            values = {name: np.array(packet[name], copy=True) for name in packet.files}
        expected_hashes = packet_ref.get("array_sha256")
        if not isinstance(expected_hashes, Mapping) or set(expected_hashes) != set(values):
            raise ValueError(f"Task41 A2 q={q} {label} factor packet hashes are incomplete")
        for name, value in values.items():
            if (
                value.dtype != np.dtype(np.complex128)
                or value.shape != expected_rhs.shape
                or not np.isfinite(value).all()
                or hashlib.sha256(
                    value.dtype.str.encode("ascii")
                    + np.asarray(value.shape, dtype=np.int64).tobytes()
                    + np.ascontiguousarray(value).view(np.uint8).tobytes()
                ).hexdigest() != expected_hashes.get(name)
            ):
                raise ValueError(f"Task41 A2 q={q} {label} factor packet {name} changed")
        if not np.array_equal(values["rhs"], expected_rhs):
            raise ValueError(f"Task41 A2 q={q} {label} RHS differs from the frozen formula")
        recomputed = np.asarray(matrix @ values["solution"], dtype=np.complex128)
        recomputed -= values["rhs"]
        if _task41_relative_vector_error(recomputed, values["residual"]) > 1.0e-13:
            raise ValueError(f"Task41 A2 q={q} {label} saved factor residual vector changed")
        relative = float(np.linalg.norm(recomputed) / np.linalg.norm(values["rhs"]))
        if not np.isclose(relative, float(recorded_relative), rtol=1.0e-10, atol=1.0e-15):
            raise ValueError(f"Task41 A2 q={q} {label} factor residual scalar does not recompute")
        if not np.isfinite(relative) or relative > 1.0e-10:
            raise ValueError(f"Task41 A2 q={q} {label} factor residual exceeds 1e-10")
        return relative

    factor_results = []
    csr_results = []
    required_actions = ("case1_full", "case1_trace_only", "case1_port_only", "case2_full")
    for twist in range(profile.replication_count):
        pair = (twist, twist + profile.replication_count)
        matrices = {q: load_csr(q) for q in pair}
        for q in pair:
            matrix = matrices[q]
            manifest, qualification, array_records = sector_by_q[q]
            expected_columns = (
                profile.trace_rows_per_q
                + profile.q_port_counts[q]
            )
            if matrix.shape != (expected_columns, expected_columns):
                raise ValueError(f"Task41 A2 q={q} CSR dimensions differ from the frozen profile")
            matrix_identity = _task41_sparse_identity(matrix)
            factor_input = factor_inputs[q]
            q_audit = q_matrix_audits.get(str(q), q_matrix_audits.get(q))
            if (
                not isinstance(q_audit, Mapping)
                or q_audit.get("shape") != list(matrix.shape)
                or q_audit.get("nnz") != matrix.nnz
                or factor_input.get("shape") != list(matrix.shape)
                or factor_input.get("nnz") != matrix.nnz
                or factor_input.get("caller_input_sha256_before") != matrix_identity
                or factor_input.get("caller_input_sha256_after") != matrix_identity
                or factor_input.get("factor_csr_sha256_before") != matrix_identity
                or factor_input.get("factor_csr_sha256_after") != matrix_identity
                or factor_input.get("input_identity_unchanged") is not True
            ):
                raise ValueError(f"Task41 A2 q={q} factor input does not match the saved CSR")

            n = matrix.shape[0]
            index = np.arange(n, dtype=np.int64)
            fresh_rhs = np.cos(0.23 * index) + 1j * np.sin(0.37 * index)
            first = factor_tests[q]
            fresh = first.get("fresh_rhs")
            second = second_tests[q]
            nested_second = first.get("second_rhs")
            second_rhs = np.empty(n, dtype=np.complex128)
            second_rhs.real[:] = 2.0 + (index % 17) / 17.0
            second_rhs.imag[:] = 1.5 + (index % 13) / 13.0
            if (
                first.get("rows") != n
                or first.get("strict_passed") is not True
                or first.get("strict_limit") != 1.0e-10
                or not isinstance(fresh, Mapping)
                or fresh.get("formula") != "cos(0.23*i) + 1j*sin(0.37*i)"
                or fresh.get("constructed_directly_not_from_csr_times_x") is not True
                or second.get("schema") != f"task41.p0.{case_id.lower()}_all_q_second_rhs_result.v1"
                or second.get("formula") != second_contract.get("formula")
                or second.get("strict_passed") is not True
                or second.get("strict_limit") != 1.0e-10
                or not isinstance(nested_second, Mapping)
                or nested_second.get("packet") != second.get("packet")
            ):
                raise ValueError(f"Task41 A2 q={q} strict factor qualification row is invalid")
            fresh_relative = load_factor_packet(
                fresh.get("packet"), q=q, label="fresh probe", expected_rhs=fresh_rhs,
                matrix=matrix, recorded_relative=first.get("relative_true_residual"),
            )
            second_relative = load_factor_packet(
                second.get("packet"), q=q, label="second RHS", expected_rhs=second_rhs,
                matrix=matrix,
                recorded_relative=second.get("relative_full_csr_true_residual"),
            )
            if (
                not np.isclose(fresh_relative, float(first.get("relative_true_residual")), rtol=1.0e-10, atol=1.0e-15)
                or not np.isclose(second_relative, float(second.get("relative_full_csr_true_residual")), rtol=1.0e-10, atol=1.0e-15)
            ):
                raise ValueError(f"Task41 A2 q={q} factor residuals differ from the audit")
            factor_results.append(
                {"q": q, "fresh_probe_relative_residual": fresh_relative,
                 "second_rhs_relative_residual": second_relative,
                 "factor_csr_identity": matrix_identity}
            )

            evidence_root = repo_root if q in imported_saved_q_indices else artifact_root
            native_records = {
                name: _task41_npy_artifact(
                    evidence_root, array_records[name], f"q{q} {name}"
                )
                for name in array_records
            }
            inputs = {name: native_records[f"input_{name}"] for name in required_actions}
            outputs = {name: native_records[f"csr_{name}"] for name in required_actions}
            native_outputs = {name: native_records[f"native_{name}"] for name in required_actions}
            trace_rows = profile.trace_rows_per_q
            first_input = inputs["case1_full"]
            if (
                any(value.dtype != np.dtype(np.complex128) or not np.isfinite(value).all() for value in inputs.values())
                or np.any(first_input == 0.0)
                or np.any(inputs["case2_full"] == 0.0)
                or np.array_equal(first_input, inputs["case2_full"])
                or not np.array_equal(inputs["case1_trace_only"][:trace_rows], first_input[:trace_rows])
                or np.any(inputs["case1_trace_only"][trace_rows:] != 0.0)
                or np.any(inputs["case1_port_only"][:trace_rows] != 0.0)
                or not np.array_equal(inputs["case1_port_only"][trace_rows:], first_input[trace_rows:])
            ):
                raise ValueError(f"Task41 A2 q={q} saved four-action input split is invalid")
            action_errors: dict[str, float] = {}
            for name in required_actions:
                computed = np.asarray(matrix @ inputs[name], dtype=np.complex128)
                saved_csr_error = _task41_relative_vector_error(computed, outputs[name])
                native_error = _task41_relative_vector_error(computed, native_outputs[name])
                if max(saved_csr_error, native_error) > 1.0e-11:
                    raise ValueError(f"Task41 A2 q={q} {name} CSR/native action exceeds 1e-11")
                action_errors[name] = native_error
            components = sum(
                (np.asarray(native_records[f"component_case1_{name}"]) for name in ("volume", "minus_D", "C", "Hhat")),
                np.zeros(matrix.shape[0], dtype=np.complex128),
            )
            component_error = _task41_relative_vector_error(components, native_outputs["case1_full"])
            split_error = _task41_relative_vector_error(
                native_outputs["case1_trace_only"] + native_outputs["case1_port_only"],
                native_outputs["case1_full"],
            )
            peer = pair[1] if q == pair[0] else pair[0]
            peer_input = native_records["paired_peer_input"]
            peer_diagonal = native_records["paired_peer_native_diagonal"]
            peer_matrix_action = np.asarray(matrices[peer] @ peer_input, dtype=np.complex128)
            peer_csr_error = _task41_relative_vector_error(peer_matrix_action, peer_diagonal)
            leakage = qualification.get("paired_sector_leakage", {})
            q_to_peer = native_records["paired_selected_native_cross"]
            peer_to_q = native_records["paired_peer_native_cross"]
            q_to_peer_relative = float(
                np.linalg.norm(q_to_peer)
                / max(float(np.linalg.norm(native_outputs["case1_full"])), np.finfo(float).tiny)
            )
            peer_to_q_relative = float(
                np.linalg.norm(peer_to_q)
                / max(float(np.linalg.norm(peer_diagonal)), np.finfo(float).tiny)
            )
            reported_errors = qualification.get("relative_errors", {})
            if (
                component_error > 1.0e-11
                or split_error > 1.0e-11
                or peer_csr_error > 1.0e-11
                or not isinstance(leakage, Mapping)
                or not np.isclose(float(leakage.get("q_to_peer", {}).get("relative", np.nan)), q_to_peer_relative, rtol=1.0e-10, atol=1.0e-15)
                or not np.isclose(float(leakage.get("peer_to_q", {}).get("relative", np.nan)), peer_to_q_relative, rtol=1.0e-10, atol=1.0e-15)
                or max(q_to_peer_relative, peer_to_q_relative) > 1.0e-11
                or float(leakage.get("peer_to_q", {}).get("peer_csr_native_relative", np.inf)) > 1.0e-11
                or not isinstance(reported_errors, Mapping)
                or set(reported_errors) != set(required_actions)
                or any(not np.isclose(float(reported_errors[name]), action_errors[name], rtol=1.0e-10, atol=1.0e-15) for name in required_actions)
                or not np.isclose(float(qualification.get("maximum_relative_error", np.nan)), max(action_errors.values()), rtol=1.0e-10, atol=1.0e-15)
            ):
                raise ValueError(f"Task41 A2 q={q} sector action, component, or leakage audit failed")
            csr_results.append(
                {"q": q, "peer_q": peer, "four_action_relative_errors": action_errors,
                 "component_reassembly_relative": component_error,
                 "trace_port_reassembly_relative": split_error,
                 "paired_peer_csr_relative_error": peer_csr_error,
                 "q_to_peer_relative": q_to_peer_relative,
                 "peer_to_q_relative": peer_to_q_relative}
            )
    return {
        "all_q_factor_probes_reapplied": True,
        "factor_operator_reapplied_from_hash_bound_q_csr": True,
        "factor_probe_count": len(factor_results),
        "factor_results": factor_results,
        "all_q_four_action_csr_reapplied": True,
        "saved_native_qualification_q_indices": sorted(imported_saved_q_indices),
        "fresh_native_qualification_q_indices": sorted(set(q_indices) - imported_saved_q_indices),
        "sector_count": len(actual_sector_pairs),
        "q_csr_action_count": sum(len(row["four_action_relative_errors"]) for row in csr_results),
        "paired_peer_csr_action_count": len(csr_results),
        "csr_results": csr_results,
        "relative_error_limit": 1.0e-11,
    }



def _task41_a2_reference_audit_checks(
    summary: Mapping[str, Any],
    numerical_output: Path,
    *,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Backward-compatible A2 entry point for the shared iterative audit."""
    return _task41_iterative_reference_audit_checks(
        summary, numerical_output, repo_root=repo_root, case_id="A2"
    )


def _task41_a2_numerical_checks(
    summary: Mapping[str, Any],
    numerical_output: Path,
    contract: Mapping[str, Any],
    *,
    repo_root: Path,
    reference_audit_source: tuple[Mapping[str, Any], Path] | None = None,
) -> dict[str, Any]:
    """Independently reopen A2 output, A1 evidence, mode and metric packets."""
    errors: list[str] = []
    case = contract["case"]
    authority = summary.get("campaign_authority")
    comparison = summary.get("task41_a1_a2_comparison")
    if not isinstance(authority, Mapping) or not isinstance(comparison, Mapping):
        raise ValueError("Task41 A2 worker summary omits contract authority or A1/A2 comparison")
    if (
        case.get("run_id") != TASK41_G13_A2_RUN_ID
        or case.get("method") != "full3d_iterative"
        or summary.get("run_id") != TASK41_G13_A2_RUN_ID
        or summary.get("profile") != TASK41_G13_A2_PRECONDITIONER
        or summary.get("stage") != "TASK41_A2"
        or summary.get("status") != "PASS"
        or summary.get("official_result") is not True
        or summary.get("numeric_gates_passed") is not True
        or summary.get("output_gates_passed") is not True
        or authority.get("task41_contract_sha256")
        != hashlib.sha256(
            Path(str(authority.get("task41_contract_path", ""))).read_bytes()
        ).hexdigest()
    ):
        errors.append("A2 worker result or frozen Task41 contract identity did not pass")
    if comparison.get("schema") != TASK41_COMPARISON_SCHEMA or comparison.get("pass") is not True:
        errors.append("A1/A2 comparison gate did not pass")
    if (
        authority.get("source_sha") != contract.get("source", {}).get("sha")
        or authority.get("campaign_window_sha256") != contract.get("window", {}).get("sha256")
        or authority.get("q_csr_reuse") != contract.get("q_csr_reuse")
    ):
        errors.append("A2 worker authority differs from its source/window-bound q reuse contract")
    audit_summary, audit_output = (
        reference_audit_source
        if reference_audit_source is not None
        else (summary, numerical_output)
    )
    reference_audit_recheck = _task41_a2_reference_audit_checks(
        audit_summary, audit_output, repo_root=repo_root
    )
    expected_binding_path = (repo_root / TASK41_A1_COMPARISON_BINDING_RELATIVE).resolve()
    binding_path = Path(str(comparison.get("a1_binding_path", ""))).resolve()
    binding_sha = str(contract.get("comparison", {}).get("a1_binding_sha256", ""))
    if (
        binding_path != expected_binding_path
        or comparison.get("a1_binding_sha256") != binding_sha
        or authority.get("a1_comparison_binding_sha256") != binding_sha
    ):
        raise ValueError("Task41 A2 comparison uses a different A1 evidence binding")
    binding, actual_binding_sha = require_task41_a1_comparison_binding(
        binding_path,
        expected_sha256=binding_sha,
        current_root=repo_root,
    )
    if comparison.get("a1_run_id") != binding["a1"]["run_id"]:
        raise ValueError("Task41 A2 comparison run identity differs from its bound A1 record")

    output_packet_meta = summary.get("output_packet")
    if not isinstance(output_packet_meta, Mapping) or not isinstance(output_packet_meta.get("arrays"), Mapping):
        raise ValueError("Task41 A2 summary omits its official output packet")
    output_packet_npz = Path(str(output_packet_meta["arrays"].get("path", ""))).resolve(strict=True)
    output_packet_path = output_packet_npz.with_suffix(".json")
    if output_packet_path.parent != numerical_output.parent.resolve():
        raise ValueError("Task41 A2 official output packet escaped its run directory")
    output_packet = _json_object(output_packet_path, "A2 official output packet")
    from src.runners.task40_v10_output_checker import (
        _verify_v31_reference_tiers,
        verify_v10_output_bundle,
    )

    output_recheck = verify_v10_output_bundle(
        output_packet_path, expected_channel_count=168
    )
    if output_recheck.get("status") != "PASS":
        errors.append("A2 full-field/output packet checker did not pass")
    diagnostic_recheck: dict[str, Any]
    try:
        from src.io.input_validation import simulation_config_3d_from_normalized

        resolved_config_path = audit_output.parent / "resolved_config.json"
        if (
            not resolved_config_path.is_file()
            or hashlib.sha256(resolved_config_path.read_bytes()).hexdigest()
            != contract["case"]["resolved_config_sha256"]
        ):
            raise ValueError("producer resolved configuration hash differs from the contract")
        resolved_config = _json_object(resolved_config_path, "Task41 frozen resolved configuration")
        reporting_cfg = simulation_config_3d_from_normalized(resolved_config)
        diagnostic_doc = _json_object(
            numerical_output / "diffraction_orders_3d.json",
            "A2 diagnostic diffraction output",
        )
        diagnostic_metrics = diagnostic_doc.get("metrics")
        diagnostic_recheck = (
            _task41_a2_diagnostic_inventory_from_data(
                diagnostic_metrics,
                diagnostic_doc.get("orders"),
                expected_m_max=reporting_cfg.reporting_diffraction_order_max_m,
                expected_n_max=reporting_cfg.reporting_diffraction_order_max_n,
            )
            if isinstance(diagnostic_metrics, Mapping)
            else {"passed": False, "error": "diagnostic metrics object is missing"}
        )
    except (OSError, ValueError, TypeError, KeyError) as exc:
        diagnostic_recheck = {"passed": False, "error": str(exc)}
    if diagnostic_recheck.get("passed") is not True:
        errors.append("A2 diagnostic diffraction rows do not match the frozen reporting grid")
    reference_tiers = _verify_v31_reference_tiers(
        summary.get("regular_inverse_checks", {}),
        expected_profile=TASK41_G13_A2_PRECONDITIONER,
    )
    if reference_tiers.get("case_count") != 6 or reference_tiers.get("passed") is not True:
        errors.append("A2 six startup reference cases did not independently pass")

    a1_modal = _task41_artifact_path(repo_root, binding, "modal_amplitudes")
    a1_orders = _task41_artifact_path(repo_root, binding, "diffraction_orders")
    a2_modal = (numerical_output / "dtn_port_modal_amplitudes_3d.npz").resolve(strict=True)
    a2_orders = (numerical_output / "dtn_port_diffraction_orders_3d.json").resolve(strict=True)
    modal_comparison = compare_task41_modal_artifacts(a1_modal, a2_modal, a1_orders, a2_orders)
    if modal_comparison.get("mode_count") != 168 or modal_comparison.get("pass") is not True:
        errors.append("A1/A2 physical-boundary modal amplitude or per-mode power comparison failed")
    a1_port = json.loads(_task41_artifact_path(repo_root, binding, "port_power_metrics").read_text(encoding="utf-8"))
    a1_volume = json.loads(_task41_artifact_path(repo_root, binding, "volume_absorption").read_text(encoding="utf-8"))
    power_comparison = compare_task41_power_totals(a1_port, a1_volume, output_packet.get("output", {}))
    if power_comparison.get("pass") is not True:
        errors.append("A1/A2 R/T/A/A_volume total comparison failed")

    a1_airbox = _task41_artifact_path(repo_root, binding, "airbox_fields")
    a2_airbox = numerical_output / "airbox_fields_3d_scientific.npz"
    mesh_checks = []
    mesh_keys = ("coordinates_nm", "vtk_cells", "vtk_cell_types", "cell_domain_tags")
    with np.load(a1_airbox, allow_pickle=False) as reference_mesh, np.load(
        a2_airbox, allow_pickle=False
    ) as candidate_mesh:
        for key in mesh_keys:
            equal = key in reference_mesh.files and key in candidate_mesh.files and np.array_equal(
                reference_mesh[key], candidate_mesh[key]
            )
            mesh_checks.append({"array": key, "equal": bool(equal)})
            if not equal:
                errors.append(f"A1/A2 mesh or material array differs: {key}")

    sample_archive = _task41_artifact_path(repo_root, binding, "full3d_samples_archive")
    sample_metadata_path = _task41_artifact_path(repo_root, binding, "full3d_samples_metadata")
    sample_metadata = _json_object(sample_metadata_path, "A1 saved-field sample metadata")
    if sample_metadata.get("archive_sha256") != sha256_file(sample_archive):
        errors.append("A1 saved-field sample metadata does not bind its NPZ")
    sample_witness = comparison.get("sample_representation_witness", {})
    if (
        sample_witness.get("pass") is not True
        or float(sample_witness.get("electric_relative_l2", float("inf"))) > TASK41_MODE_RELATIVE_LIMIT
        or float(sample_witness.get("magnetic_relative_l2_from_direct_fe_curl", float("inf")))
        > TASK41_MODE_RELATIVE_LIMIT
    ):
        errors.append("A1 recovered-field representation witness failed")

    full_solution = _load_task41_a2_full_solution(output_packet)
    a1_full_solution = _task41_npz_array(
        _task41_artifact_path(repo_root, binding, "full_solution"), "recovered_field"
    ).astype(np.complex128, copy=False)
    metric_meta = comparison.get("metric_packet")
    if not isinstance(metric_meta, Mapping) or not isinstance(metric_meta.get("arrays"), Mapping):
        raise ValueError("Task41 A2 comparison omits its full-volume metric packet")
    metric_json = Path(str(metric_meta["arrays"].get("path", ""))).resolve(strict=True).with_suffix(".json")
    if metric_json.parent != numerical_output.parent.resolve():
        raise ValueError("Task41 A1/A2 metric packet escaped its run directory")
    field_comparison = evaluate_task41_metric_packet(
        metric_json,
        reference_full_field=a1_full_solution,
        candidate_full_field=full_solution,
        expected_binding_sha256=actual_binding_sha,
    )
    stored_metric = comparison.get("full_volume_metric", {})
    for key in ("electric_relative_l2", "scaled_curl_relative_l2"):
        if not np.isclose(
            float(stored_metric.get(key, np.nan)),
            float(field_comparison[key]),
            rtol=1.0e-11,
            atol=1.0e-13,
        ):
            errors.append(f"A1/A2 stored full-volume {key} differs from the checker recomputation")
    if field_comparison.get("pass") is not True:
        errors.append("A1/A2 full-volume E/scaled-curl metric exceeds its limit")

    return {
        "errors": errors,
        "output_packet_recheck": output_recheck,
        "diagnostic_diffraction_inventory_recheck": diagnostic_recheck,
        "reference_tiers": reference_tiers,
        "modal_comparison": modal_comparison,
        "power_comparison": power_comparison,
        "mesh_array_checks": mesh_checks,
        "sample_representation_witness": sample_witness,
        "full_volume_metric_recheck": field_comparison,
        "reference_audit_recheck": reference_audit_recheck,
        "a1_binding_sha256": actual_binding_sha,
    }


def _task41_b0_chunked_norm(values: np.ndarray, *, chunk_rows: int = 262_144) -> float:
    total = 0.0
    for start in range(0, int(values.shape[0]), chunk_rows):
        block = np.asarray(values[start : start + chunk_rows], dtype=np.complex128)
        if not np.isfinite(block).all():
            raise ValueError("Task41 B0 norm input contains non-finite values")
        total += float(np.vdot(block, block).real)
    return float(np.sqrt(max(0.0, total)))


def _task41_b0_chunked_difference_summary(
    left: np.ndarray,
    right: np.ndarray,
    *,
    start: int = 0,
    stop: int | None = None,
    chunk_rows: int = 262_144,
) -> dict[str, float]:
    """Summarize a saved vector difference without materializing the whole delta."""
    end = int(left.shape[0]) if stop is None else stop
    if (
        left.ndim != 1
        or right.ndim != 1
        or left.shape != right.shape
        or type(start) is not int
        or type(end) is not int
        or start < 0
        or end < start
        or end > int(left.shape[0])
        or type(chunk_rows) is not int
        or chunk_rows < 1
    ):
        raise ValueError("Task41 B0 partitioned difference has an invalid vector range")
    squared_norm = 0.0
    maximum_row = 0.0
    maximum_row_index: int | None = None
    for offset in range(start, end, chunk_rows):
        block_end = min(end, offset + chunk_rows)
        lhs = np.asarray(left[offset:block_end], dtype=np.complex128)
        rhs = np.asarray(right[offset:block_end], dtype=np.complex128)
        if not np.isfinite(lhs).all() or not np.isfinite(rhs).all():
            raise ValueError("Task41 B0 partitioned difference contains non-finite values")
        difference = lhs - rhs
        squared_norm += float(np.vdot(difference, difference).real)
        if difference.size:
            magnitudes = np.abs(difference)
            local_index = int(np.argmax(magnitudes))
            local_maximum = float(magnitudes[local_index])
            if maximum_row_index is None or local_maximum > maximum_row:
                maximum_row = local_maximum
                maximum_row_index = offset + local_index
    return {
        "absolute_l2": float(np.sqrt(max(0.0, squared_norm))),
        "sum_squares": max(0.0, squared_norm),
        "max_abs_row": maximum_row,
        "max_abs_row_index": maximum_row_index,
    }


def _task41_b0_v7_map_original_rows_to_active(
    original_rows: np.ndarray, active_original_rows: np.ndarray
) -> np.ndarray:
    """Map sparse original B-alpha rows to active ids without another MPC map."""
    rows = np.asarray(original_rows, dtype=np.int64)
    active = np.asarray(active_original_rows, dtype=np.int64)
    if rows.ndim != 1 or active.ndim != 1 or np.unique(active).size != active.size:
        raise ValueError("Task41 V7 original/active row maps are malformed")
    if rows.size and not active.size:
        raise ValueError("Task41 V7 B-alpha cannot map to an empty active trace")
    order = np.argsort(active, kind="stable")
    sorted_active = active[order]
    positions = np.searchsorted(sorted_active, rows)
    if positions.size and (
        np.any(positions >= sorted_active.size)
        or np.any(sorted_active[np.minimum(positions, sorted_active.size - 1)] != rows)
    ):
        raise ValueError("Task41 V7 B-alpha row is not an independent active row")
    return order[positions]


def _task41_b0_v7_metric_state() -> dict[str, Any]:
    return {"sum_squares": 0.0, "max_abs": 0.0, "max_row": None}


def _task41_b0_v7_add_metric(
    state: dict[str, Any],
    values: np.ndarray,
    *,
    row_offset: int,
    row_indices: np.ndarray | None = None,
) -> None:
    vector = np.asarray(values, dtype=np.complex128).reshape(-1)
    if not np.isfinite(vector).all():
        raise ValueError("Task41 V7 diagnostic vector contains non-finite values")
    state["sum_squares"] += float(np.vdot(vector, vector).real)
    if vector.size:
        magnitudes = np.abs(vector)
        local_index = int(np.argmax(magnitudes))
        local_max = float(magnitudes[local_index])
        if state["max_row"] is None or local_max > float(state["max_abs"]):
            state["max_abs"] = local_max
            state["max_row"] = (
                int(np.asarray(row_indices, dtype=np.int64)[local_index])
                if row_indices is not None
                else row_offset + local_index
            )


def _task41_b0_v7_finish_metric(state: Mapping[str, Any]) -> dict[str, Any]:
    sum_squares = max(0.0, float(state["sum_squares"]))
    return {
        "absolute_l2": float(np.sqrt(sum_squares)),
        "sum_squares": sum_squares,
        "max_abs": float(state["max_abs"]),
        "max_row": state["max_row"],
    }


def _task41_b0_v7_rhs_split_metrics(
    native_rhs: np.ndarray,
    native_volume_rhs: np.ndarray,
    b_alpha_rows: np.ndarray,
    b_alpha_values: np.ndarray,
    *,
    chunk_rows: int = 262_144,
) -> dict[str, Any]:
    if (
        native_rhs.ndim != 1
        or native_volume_rhs.shape != native_rhs.shape
        or b_alpha_rows.ndim != 1
        or b_alpha_values.shape != b_alpha_rows.shape
        or b_alpha_rows.dtype.kind not in "iu"
        or b_alpha_values.dtype != np.dtype(np.complex128)
        or (b_alpha_rows.size and np.any(b_alpha_rows >= native_rhs.size))
        or (b_alpha_rows.size and np.any(b_alpha_rows < 0))
    ):
        raise ValueError("Task41 V7 full/volume RHS and B-alpha layouts differ")
    order = np.argsort(b_alpha_rows, kind="stable")
    rows = np.asarray(b_alpha_rows[order], dtype=np.int64)
    values = np.asarray(b_alpha_values[order], dtype=np.complex128)
    metrics = _task41_b0_v7_metric_state()
    for start in range(0, int(native_rhs.size), chunk_rows):
        stop = min(int(native_rhs.size), start + chunk_rows)
        difference = np.asarray(native_rhs[start:stop], dtype=np.complex128) - np.asarray(
            native_volume_rhs[start:stop], dtype=np.complex128
        )
        lo = int(np.searchsorted(rows, start, side="left"))
        hi = int(np.searchsorted(rows, stop, side="left"))
        if hi > lo:
            np.add.at(difference, rows[lo:hi] - start, -values[lo:hi])
        _task41_b0_v7_add_metric(metrics, difference, row_offset=start)
    return _task41_b0_v7_finish_metric(metrics)


def _task41_b0_v7_nonactive_rhs_difference(
    native_rhs: np.ndarray,
    native_volume_rhs: np.ndarray,
    active_original_rows: np.ndarray,
    *,
    chunk_rows: int = 262_144,
) -> dict[str, Any]:
    if native_rhs.ndim != 1 or native_volume_rhs.shape != native_rhs.shape:
        raise ValueError("Task41 V7 nonactive RHS vectors differ in layout")
    active = np.asarray(active_original_rows, dtype=np.int64)
    if active.ndim != 1 or (active.size and (np.any(active < 0) or np.any(active >= native_rhs.size))):
        raise ValueError("Task41 V7 active original-row map is invalid")
    active_mask = np.zeros(native_rhs.size, dtype=np.bool_)
    active_mask[active] = True
    metrics = _task41_b0_v7_metric_state()
    for start in range(0, int(native_rhs.size), chunk_rows):
        stop = min(int(native_rhs.size), start + chunk_rows)
        selected = ~active_mask[start:stop]
        difference = (
            np.asarray(native_rhs[start:stop], dtype=np.complex128)
            - np.asarray(native_volume_rhs[start:stop], dtype=np.complex128)
        )
        row_indices = np.flatnonzero(selected) + start
        _task41_b0_v7_add_metric(
            metrics,
            difference[selected],
            row_offset=start,
            row_indices=row_indices,
        )
    return _task41_b0_v7_finish_metric(metrics)


def _task41_b0_v7_attribution_state_recheck(
    *,
    candidate_d_full: np.ndarray,
    candidate_d_volume: np.ndarray,
    active_original_rows: np.ndarray,
    native_rhs: np.ndarray,
    native_volume_rhs: np.ndarray,
    b_alpha_rows: np.ndarray,
    b_alpha_values: np.ndarray,
    native_volume_action: np.ndarray,
    T_r_i: np.ndarray,
    delta_t: np.ndarray,
    attributed_terms: np.ndarray,
    reduce_r_volume: np.ndarray,
    reduce_r_full: np.ndarray,
    frozen_denominator: float,
    evidence_directory: Path | None = None,
    evidence_prefix: str | None = None,
) -> dict[str, Any]:
    """Independently recompute V7 full/volume formulas from saved arrays."""
    active = np.asarray(active_original_rows, dtype=np.int64)
    active_rows = int(active.size)
    if (
        active.ndim != 1
        or np.unique(active).size != active_rows
        or any(
            np.asarray(value).shape != (active_rows,)
            for value in (
                candidate_d_full,
                candidate_d_volume,
                T_r_i,
                delta_t,
                attributed_terms,
                reduce_r_volume,
                reduce_r_full,
            )
        )
        or native_rhs.ndim != 1
        or native_volume_rhs.shape != native_rhs.shape
        or native_volume_action.shape != native_rhs.shape
        or (active.size and (np.any(active < 0) or np.any(active >= native_rhs.size)))
        or b_alpha_rows.shape != b_alpha_values.shape
        or b_alpha_values.dtype != np.dtype(np.complex128)
    ):
        raise ValueError("Task41 V7 attribution state arrays have incompatible identities/layouts")
    beta_active_ids = _task41_b0_v7_map_original_rows_to_active(
        b_alpha_rows, active
    )
    beta_active = np.zeros(active_rows, dtype=np.complex128)
    np.add.at(beta_active, beta_active_ids, b_alpha_values)
    support_mask = np.zeros(active_rows, dtype=np.bool_)
    support_mask[beta_active_ids] = True
    metrics = {
        key: _task41_b0_v7_metric_state()
        for key in (
            "legacy_closure_minus_beta_active",
            "legacy_closure_vector",
            "legacy_minus_beta_vs_corrected_full",
            "legacy_closure_on_beta_support",
            "legacy_closure_off_beta_support",
            "corrected_full_closure",
            "corrected_volume_closure",
            "reduce_r_volume_vs_raw_trace_plus_T_r_i",
            "d_volume_plus_reduce_r_volume_vs_delta_plus_Q",
            "reduce_r_full_vs_raw_trace_plus_T_r_i",
            "d_full_plus_reduce_r_full_vs_delta_plus_Q",
            "d_hat_full_minus_candidate_d_full",
            "d_hat_volume_minus_saved_d_volume",
            "full_minus_volume_d_plus_rhs_split",
        )
    }
    beta_norm_sq = 0.0
    beta_inner = 0.0 + 0.0j
    term_norm_squares = {
        name: 0.0
        for name in (
            "delta_t",
            "attributed_terms_Q",
            "r_volume_trace",
            "r_full_trace",
            "T_r_i",
            "candidate_d_full",
            "saved_d_volume",
        )
    }
    d_hat_volume = np.empty(active_rows, dtype=np.complex128)
    d_hat_full = np.empty(active_rows, dtype=np.complex128)
    array_outputs: dict[str, Any] = {}
    output_maps: dict[str, np.memmap] = {}
    temporary_paths: dict[str, Path] = {}
    final_paths: dict[str, Path] = {}
    if evidence_directory is not None:
        if not evidence_prefix:
            raise ValueError("Task41 V7 closure arrays require a bound artifact prefix")
        evidence_directory = Path(evidence_directory).resolve()
        if not evidence_directory.is_dir():
            raise FileNotFoundError("Task41 V7 evidence directory was not prepared")
        for field in ("corrected_full_closure", "corrected_volume_closure"):
            name = f"{evidence_prefix}_{field}"
            final_path = evidence_directory / f"{name}.npy"
            temporary_path = evidence_directory / f".{name}.npy.tmp"
            if final_path.exists() or temporary_path.exists():
                raise FileExistsError(f"Task41 V7 closure artifact already exists: {name}")
            output_maps[field] = np.lib.format.open_memmap(
                temporary_path,
                mode="w+",
                dtype=np.complex128,
                shape=(active_rows,),
            )
            temporary_paths[field] = temporary_path
            final_paths[field] = final_path
    for start in range(0, active_rows, 262_144):
        stop = min(active_rows, start + 262_144)
        original = active[start:stop]
        d_full = np.asarray(candidate_d_full[start:stop], dtype=np.complex128)
        d_volume = np.asarray(candidate_d_volume[start:stop], dtype=np.complex128)
        f_t = np.asarray(native_rhs[original], dtype=np.complex128)
        b_t = np.asarray(native_volume_rhs[original], dtype=np.complex128)
        n_t = np.asarray(native_volume_action[original], dtype=np.complex128)
        beta = beta_active[start:stop]
        u = np.asarray(T_r_i[start:stop], dtype=np.complex128)
        delta = np.asarray(delta_t[start:stop], dtype=np.complex128)
        q = np.asarray(attributed_terms[start:stop], dtype=np.complex128)
        volume_reduce = np.asarray(reduce_r_volume[start:stop], dtype=np.complex128)
        full_reduce = np.asarray(reduce_r_full[start:stop], dtype=np.complex128)
        right = delta + q
        r_volume = b_t - n_t
        r_full = f_t - n_t - beta
        legacy = d_full + (f_t - n_t) + u - right
        legacy_minus_beta = legacy - beta
        corrected_full = d_full + r_full + u - right
        corrected_volume = d_volume + r_volume + u - right
        expected_volume_reduce = r_volume + u
        expected_full_reduce = r_full + u
        d_volume_plus_reduce = d_volume + volume_reduce - right
        d_full_plus_reduce = d_full + full_reduce - right
        hat_volume = right - r_volume - u
        hat_full = right - r_full - u
        rhs_split_active = f_t - b_t - beta
        split = (d_full - d_volume) + rhs_split_active
        d_hat_volume[start:stop] = hat_volume
        d_hat_full[start:stop] = hat_full
        if output_maps:
            output_maps["corrected_full_closure"][start:stop] = corrected_full
            output_maps["corrected_volume_closure"][start:stop] = corrected_volume
        chunk_vectors = {
            "legacy_closure_minus_beta_active": legacy_minus_beta,
            "legacy_closure_vector": legacy,
            "legacy_minus_beta_vs_corrected_full": corrected_full - legacy_minus_beta,
            "legacy_closure_on_beta_support": legacy[support_mask[start:stop]],
            "legacy_closure_off_beta_support": legacy[~support_mask[start:stop]],
            "corrected_full_closure": corrected_full,
            "corrected_volume_closure": corrected_volume,
            "reduce_r_volume_vs_raw_trace_plus_T_r_i": volume_reduce - expected_volume_reduce,
            "d_volume_plus_reduce_r_volume_vs_delta_plus_Q": d_volume_plus_reduce,
            "reduce_r_full_vs_raw_trace_plus_T_r_i": full_reduce - expected_full_reduce,
            "d_full_plus_reduce_r_full_vs_delta_plus_Q": d_full_plus_reduce,
            "d_hat_full_minus_candidate_d_full": hat_full - d_full,
            "d_hat_volume_minus_saved_d_volume": hat_volume - d_volume,
            "full_minus_volume_d_plus_rhs_split": split,
        }
        for key, values in chunk_vectors.items():
            if key == "legacy_closure_on_beta_support":
                selected = np.flatnonzero(support_mask[start:stop]) + start
                _task41_b0_v7_add_metric(
                    metrics[key], values, row_offset=start, row_indices=selected
                )
            elif key == "legacy_closure_off_beta_support":
                selected = np.flatnonzero(~support_mask[start:stop]) + start
                _task41_b0_v7_add_metric(
                    metrics[key], values, row_offset=start, row_indices=selected
                )
            else:
                _task41_b0_v7_add_metric(metrics[key], values, row_offset=start)
        beta_norm_sq += float(np.vdot(beta, beta).real)
        beta_inner += complex(np.vdot(beta, legacy))
        for name, term in (
            ("delta_t", delta),
            ("attributed_terms_Q", q),
            ("r_volume_trace", r_volume),
            ("r_full_trace", r_full),
            ("T_r_i", u),
            ("candidate_d_full", d_full),
            ("saved_d_volume", d_volume),
        ):
            term_norm_squares[name] += float(np.vdot(term, term).real)
    if output_maps:
        for value in output_maps.values():
            value.flush()
        output_maps.clear()
        import os

        for field, temporary_path in temporary_paths.items():
            final_path = final_paths[field]
            os.replace(temporary_path, final_path)
            array_outputs[field] = {
                "name": final_path.stem,
                "path": str(final_path),
                "sha256": sha256_file(final_path),
                "bytes": final_path.stat().st_size,
                "shape": [active_rows],
                "dtype": "complex128",
            }
    diagnostics = {key: _task41_b0_v7_finish_metric(value) for key, value in metrics.items()}
    term_scales = {
        name: {
            "absolute_l2": float(np.sqrt(max(0.0, square_sum))),
            "frozen_denominator": float(frozen_denominator),
            "frozen_denominator_relative": float(np.sqrt(max(0.0, square_sum)))
            / frozen_denominator,
        }
        for name, square_sum in term_norm_squares.items()
    }
    d_volume_norm = term_scales["saved_d_volume"]["absolute_l2"]
    d_full_norm = term_scales["candidate_d_full"]["absolute_l2"]
    diagnostics.update(
        {
            "corrected_full_closure_frozen_denominator_relative": diagnostics[
                "corrected_full_closure"
            ]["absolute_l2"]
            / frozen_denominator,
            "corrected_volume_closure_frozen_denominator_relative": diagnostics[
                "corrected_volume_closure"
            ]["absolute_l2"]
            / frozen_denominator,
            "corrected_full_closure_relative_to_d_full": diagnostics[
                "corrected_full_closure"
            ]["absolute_l2"]
            / max(d_full_norm, np.finfo(float).tiny),
            "corrected_volume_closure_relative_to_d_volume": diagnostics[
                "corrected_volume_closure"
            ]["absolute_l2"]
            / max(d_volume_norm, np.finfo(float).tiny),
            "term_scales": term_scales,
        }
    )
    return {
        "diagnostics": diagnostics,
        "legacy_closure_beta_active_l2": float(np.sqrt(max(0.0, beta_norm_sq))),
        "legacy_beta_conjugate_inner_product": {
            "real": float(beta_inner.real),
            "imag": float(beta_inner.imag),
        },
        "epsilon_rhs_native_minus_volume_minus_Balpha": _task41_b0_v7_rhs_split_metrics(
            native_rhs,
            native_volume_rhs,
            np.asarray(b_alpha_rows, dtype=np.int64),
            b_alpha_values,
        ),
        "_d_hat_volume": d_hat_volume,
        "_d_hat_full": d_hat_full,
        "persisted_closure_arrays": array_outputs,
    }


def _task41_b0_chunked_relative_error(
    actual: np.ndarray, expected: np.ndarray, *, chunk_rows: int = 262_144
) -> float:
    if actual.shape != expected.shape:
        raise ValueError("Task41 B0 recovery arrays differ in shape")
    error_squared = 0.0
    expected_squared = 0.0
    for start in range(0, int(actual.shape[0]), chunk_rows):
        stop = min(int(actual.shape[0]), start + chunk_rows)
        left = np.asarray(actual[start:stop], dtype=np.complex128)
        right = np.asarray(expected[start:stop], dtype=np.complex128)
        if not np.isfinite(left).all() or not np.isfinite(right).all():
            raise ValueError("Task41 B0 recovery array contains non-finite values")
        difference = left - right
        error_squared += float(np.vdot(difference, difference).real)
        expected_squared += float(np.vdot(right, right).real)
    return float(
        np.sqrt(max(0.0, error_squared))
        / max(float(np.sqrt(max(0.0, expected_squared))), np.finfo(float).tiny)
    )


def _task41_b0_chunked_difference_norm(
    left: np.ndarray, right: np.ndarray, *, chunk_rows: int = 262_144
) -> float:
    if left.shape != right.shape:
        raise ValueError("Task41 B0 residual arrays differ in shape")
    total = 0.0
    for start in range(0, int(left.shape[0]), chunk_rows):
        stop = min(int(left.shape[0]), start + chunk_rows)
        lhs = np.asarray(left[start:stop], dtype=np.complex128)
        rhs = np.asarray(right[start:stop], dtype=np.complex128)
        if not np.isfinite(lhs).all() or not np.isfinite(rhs).all():
            raise ValueError("Task41 B0 residual array contains non-finite values")
        difference = lhs - rhs
        total += float(np.vdot(difference, difference).real)
    return float(np.sqrt(max(0.0, total)))


def _task41_b0_chunked_residual_discrepancy(
    residual: np.ndarray,
    rhs: np.ndarray,
    action: np.ndarray,
    *,
    chunk_rows: int = 262_144,
) -> float:
    if residual.shape != rhs.shape or rhs.shape != action.shape:
        raise ValueError("Task41 B0 native residual vectors differ in shape")
    total = 0.0
    for start in range(0, int(rhs.shape[0]), chunk_rows):
        stop = min(int(rhs.shape[0]), start + chunk_rows)
        r = np.asarray(residual[start:stop], dtype=np.complex128)
        b = np.asarray(rhs[start:stop], dtype=np.complex128)
        a = np.asarray(action[start:stop], dtype=np.complex128)
        if not np.isfinite(r).all() or not np.isfinite(b).all() or not np.isfinite(a).all():
            raise ValueError("Task41 B0 native residual witness contains non-finite values")
        delta = r - (b - a)
        total += float(np.vdot(delta, delta).real)
    return float(np.sqrt(max(0.0, total)))


def _task41_b0_chunked_symmetric_relative_error(
    actual: np.ndarray, expected: np.ndarray, *, chunk_rows: int = 262_144
) -> float:
    if actual.shape != expected.shape:
        raise ValueError("Task41 B0 compared arrays differ in shape")
    error_squared = actual_squared = expected_squared = 0.0
    for start in range(0, int(actual.shape[0]), chunk_rows):
        stop = min(int(actual.shape[0]), start + chunk_rows)
        left = np.asarray(actual[start:stop], dtype=np.complex128)
        right = np.asarray(expected[start:stop], dtype=np.complex128)
        if not np.isfinite(left).all() or not np.isfinite(right).all():
            raise ValueError("Task41 B0 compared arrays contain non-finite values")
        error = left - right
        error_squared += float(np.vdot(error, error).real)
        actual_squared += float(np.vdot(left, left).real)
        expected_squared += float(np.vdot(right, right).real)
    return float(
        np.sqrt(max(0.0, error_squared))
        / max(
            float(np.sqrt(max(0.0, actual_squared))),
            float(np.sqrt(max(0.0, expected_squared))),
            np.finfo(float).tiny,
        )
    )


def _task41_b0_indexed_arrays_equal(
    left: np.ndarray,
    right: np.ndarray,
    rows: np.ndarray,
    *,
    zero: bool = False,
    chunk_rows: int = 262_144,
) -> bool:
    for start in range(0, int(rows.shape[0]), chunk_rows):
        selected = np.asarray(rows[start : start + chunk_rows], dtype=np.int64)
        left_values = np.asarray(left[selected])
        if zero:
            if np.any(left_values != 0.0):
                return False
        elif not np.array_equal(left_values, np.asarray(right[selected])):
            return False
    return True


def _task41_b0_recovery_evidence_checks(
    summary: Mapping[str, Any],
    numerical_output: Path,
    contract: Mapping[str, Any],
    *,
    contract_sha256: str,
    run_root: Path | None = None,
    expected_mode_indices: tuple[int, int] = (16030, 48090),
    checkpoint_path: Path | None = None,
    checkpoint_identity: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Recompute B0 recovery and joint-action gates from hash-bound raw arrays."""
    errors: list[str] = []
    integrity_errors: list[str] = []
    recovery_errors: list[str] = []
    joint_action_errors: list[str] = []
    manifest_loaded = False
    manifest_identity_binding_valid = False
    joint_action_completed = False
    joint_action_passed: bool | None = None
    joint_action_metrics: list[dict[str, Any]] = []
    raw_audit_completed_columns = 0
    checkpoint_events: list[dict[str, Any]] = []

    def save_checkpoint(stage: str, **details: Any) -> None:
        event = {"stage": stage, **details}
        checkpoint_events.append(event)
        if checkpoint_path is None:
            return
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = checkpoint_path.with_name(checkpoint_path.name + ".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "schema": "task41.p0.b0.saved_evidence_audit_checkpoint.v1",
                    "status": "IN_PROGRESS",
                    "identity": dict(checkpoint_identity or {}),
                    "events": checkpoint_events,
                },
                ensure_ascii=False,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
            + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, checkpoint_path)

    def integrity_error(message: str) -> None:
        errors.append(message)
        integrity_errors.append(message)

    def recovery_error(message: str) -> None:
        errors.append(message)
        recovery_errors.append(message)

    def joint_action_error(message: str) -> None:
        errors.append(message)
        joint_action_errors.append(message)

    campaign_authority = summary.get("campaign_authority")
    contract_strategy = contract.get("numerical_strategy", {}).get(
        "internal_rhs_strategy"
    ) if isinstance(contract.get("numerical_strategy"), Mapping) else None
    campaign_strategy = (
        campaign_authority.get("internal_rhs_strategy")
        if isinstance(campaign_authority, Mapping)
        else None
    )
    if "same_lu_rhs_solve" in {contract_strategy, campaign_strategy}:
        v9_binding = summary.get("b0_v9_compact_volume_audit")
        checker_binding = summary.get("b0_v9_independent_check")
        if not isinstance(v9_binding, Mapping) or not isinstance(checker_binding, Mapping):
            message = "Task41 B0 same-LU strategy requires the V9 compact volume audit and independent checker"
            return {
                "schema": "task41.p0.b0.recovery_evidence_checker.v1",
                "terminal_route": "task41_b0_v9_compact_volume_audit",
                "audit_completed": False,
                "data_integrity": False,
                "recovery_passed": False,
                "joint_action_passed": False,
                "official_result": False,
                "integrity_errors": [message],
                "recovery_errors": [],
                "joint_action_errors": [],
                "errors": [message],
                "passed": False,
            }
        try:
            run_root = (
                Path(run_root).resolve(strict=True)
                if run_root is not None
                else numerical_output.parent.resolve(strict=True)
            )
            repo_root = Path(__file__).resolve().parents[2]
            v9_path = _task41_run_artifact(run_root, v9_binding, "V9 compact volume audit")
            checker_path = _task41_run_artifact(
                run_root, checker_binding, "V9 independent compact checker"
            )
            v9_report = _json_object(v9_path, "V9 compact volume audit")
            v9_checker = _json_object(checker_path, "V9 independent compact checker")
            donor_binding = summary.get("b0_v9_volume_donor_binding")
            prefix_binding = summary.get("b0_v9_saved_prefix_binding")
            if not isinstance(donor_binding, Mapping) or not isinstance(prefix_binding, Mapping):
                raise ValueError("V9 terminal summary omits donor or source-prefix identity")
            from src.runners.task41_p0_contract import TASK41_B0_V9_VOLUME_DONOR_RUN_RELATIVE
            from src.solvers.task41_v4_volume_only_audit import TASK41_V4_APPENDED_ROWS

            donor_run = (repo_root / TASK41_B0_V9_VOLUME_DONOR_RUN_RELATIVE).resolve(strict=True)
            donor_summary_path = donor_run / "task40_v10_p6_candidate_summary.json"
            if (
                donor_binding.get("relative_path")
                != TASK41_B0_V9_VOLUME_DONOR_RUN_RELATIVE.as_posix()
                or donor_binding.get("attempt_id") != TASK41_B0_V9_VOLUME_DONOR_RUN_RELATIVE.name
                or donor_binding.get("summary_bytes") != donor_summary_path.stat().st_size
                or donor_binding.get("summary_sha256") != sha256_file(donor_summary_path)
            ):
                raise ValueError("V9 frozen V4 donor summary identity differs")
            donor = load_task41_v4_volume_only_donor(
                summary_path=donor_summary_path,
                numerical_output=donor_run / "numerical_output",
            )
            if (
                donor_binding.get("manifest_sha256") != donor.get("manifest_sha256")
                or donor_binding.get("existing_evidence_bytes")
                != donor.get("existing_evidence_bytes")
                or type(donor_binding.get("prior_new_evidence_bytes")) is not int
            ):
                raise ValueError("V9 frozen V4 donor manifest or evidence accounting differs")
            source_path = Path(str(prefix_binding.get("c_source_path", ""))).resolve(strict=True)
            if (
                not source_path.is_relative_to(repo_root)
                or sha256_file(source_path) != prefix_binding.get("c_source_sha256")
                or prefix_binding.get("candidate_evaluator_identity")
                != "task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1"
                or not isinstance(prefix_binding.get("candidate_cache_identity"), str)
                or not prefix_binding.get("candidate_cache_identity")
                or prefix_binding.get("owner_internal_rhs_strategy") != "same_lu_rhs_solve"
                or prefix_binding.get("owner_geometry_policy") != "mesh_actual_exact"
                or prefix_binding.get("appended_rows") != TASK41_V4_APPENDED_ROWS
                or prefix_binding.get("loaded_v7_payloads") is not False
            ):
                raise ValueError("V9 frozen source/cache or live-owner identity differs")
            action_gate = v9_report.get("candidate_full_action_gate")
            recovery_gate = v9_report.get("candidate_recovery_gate")
            if not isinstance(action_gate, Mapping) or not isinstance(recovery_gate, Mapping):
                raise ValueError("V9 compact report omits its action or recovery gate")
            action_status = action_gate.get("status")
            recovery_status = recovery_gate.get("status")
            action_passed = action_status == "PASS"
            recovery_passed = recovery_status == "PASS"
            qualification_passed = bool(action_passed and recovery_passed)
            expected_report_status = "PASS" if qualification_passed else "GATE_FAILED"
            checker_errors = v9_checker.get("errors")
            if (
                contract_strategy != "same_lu_rhs_solve"
                or campaign_strategy != "same_lu_rhs_solve"
                or v9_report.get("schema") != "task41.p0.b0.v9.compact_volume_identity.v1"
                or v9_report.get("completed") is not True
                or v9_report.get("official_result") is not False
                or v9_report.get("internal_rhs_strategy") != "same_lu_rhs_solve"
                or v9_report.get("donor_manifest_sha256") != donor_binding.get("manifest_sha256")
                or v9_report.get("existing_evidence_bytes")
                != donor_binding.get("existing_evidence_bytes")
                or v9_report.get("prior_new_evidence_bytes")
                != donor_binding.get("prior_new_evidence_bytes")
                or v9_report.get("status") != expected_report_status
                or v9_binding.get("schema") != v9_report.get("schema")
                or v9_binding.get("status") != v9_report.get("status")
                or v9_binding.get("action_gate") != action_gate
                or v9_binding.get("recovery_gate") != recovery_gate
                or v9_checker.get("schema")
                != "task41.p0.b0.v9.compact_volume_independent_check.v1"
                or v9_checker.get("official_result") is not False
                or v9_checker.get("status") != ("PASS" if qualification_passed else "FAIL")
                or v9_checker.get("passed") is not qualification_passed
                or checker_binding.get("schema") != v9_checker.get("schema")
                or checker_binding.get("status") != v9_checker.get("status")
                or checker_binding.get("passed") is not qualification_passed
                or not isinstance(checker_errors, list)
                or checker_errors
            ):
                raise ValueError("V9 summary, compact audit, and independent checker identities disagree")
            replay = check_task41_b0_v9_compact_volume_audit(
                v9_report,
                donor,
                output_directory=run_root,
                native_volume_apply=None,
                native_action_receipt=v9_checker,
                expected_candidate_identity=str(
                    prefix_binding["candidate_evaluator_identity"]
                ),
                expected_cache_identity=str(prefix_binding["candidate_cache_identity"]),
            )
            if (
                replay.get("schema")
                != "task41.p0.b0.v9.compact_volume_independent_check.v1"
                or replay.get("status") != v9_checker.get("status")
                or replay.get("passed") is not v9_checker.get("passed")
                or replay.get("errors")
                or replay.get("native_action_receipts_reused")
                != (2 if action_passed else 0)
            ):
                raise ValueError("V9 saved-only replay differs from its live native-action checker")
            audit_completed = True
            data_integrity = True
            return {
                "schema": "task41.p0.b0.recovery_evidence_checker.v1",
                "terminal_route": "task41_b0_v9_compact_volume_audit",
                "manifest_path": str(v9_path),
                "manifest_stage": "V9_COMPACT_VOLUME_ONLY",
                "audit_completed": audit_completed,
                "data_integrity": data_integrity,
                "integrity_errors": [],
                "recovery_passed": recovery_passed,
                "recovery_errors": [],
                "joint_action_status": action_status,
                "joint_action_passed": action_passed,
                "joint_action_replayed": replay.get("checks", {}).get(
                    "both_dynamic_and_frozen_action_gates"
                ) is not None,
                "joint_action_errors": [],
                "qualification_passed": qualification_passed,
                "official_result": False,
                "run_identity_rechecked": True,
                "support_certificate_rechecked": None,
                "saved_only_compact_replay": replay,
                "columns": [],
                "errors": [],
                "passed": qualification_passed,
            }
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            message = f"Task41 B0 V9 compact terminal evidence recheck failed: {type(exc).__name__}: {exc}"
            return {
                "schema": "task41.p0.b0.recovery_evidence_checker.v1",
                "terminal_route": "task41_b0_v9_compact_volume_audit",
                "audit_completed": False,
                "data_integrity": False,
                "recovery_passed": False,
                "joint_action_passed": None,
                "qualification_passed": False,
                "official_result": False,
                "integrity_errors": [message],
                "recovery_errors": [],
                "joint_action_errors": [],
                "errors": [message],
                "passed": False,
            }

    binding = summary.get("b0_recovery_evidence")
    if not isinstance(binding, Mapping):
        message = "Task41 B0 summary omits its recovery evidence binding"
        return {
            "schema": "task41.p0.b0.recovery_evidence_checker.v1",
            "audit_completed": False,
            "data_integrity": False,
            "recovery_passed": False,
            "joint_action_passed": None,
            "official_result": False,
            "integrity_errors": [message],
            "recovery_errors": [],
            "joint_action_errors": [],
            "errors": [message],
            "passed": False,
        }
    manifest_ref = binding.get("manifest")
    manifest: Mapping[str, Any] = {}
    if not isinstance(manifest_ref, Mapping):
        integrity_error("Task41 B0 recovery evidence omits its manifest artifact record")
    else:
        try:
            manifest_path = _task41_run_artifact(
                numerical_output.parent, manifest_ref, "B0 recovery manifest"
            )
            manifest = _json_object(manifest_path, "B0 recovery manifest")
            manifest_loaded = True
            manifest_stage = manifest.get("stage")
            manifest_status = manifest.get("status")
            expected_status = (
                "PASS"
                if manifest_stage == "FULL_ACTION_QUALIFIED"
                else "FAIL"
                if manifest_stage
                in {"FULL_ACTION_GATE_FAILED", "RECOVERY_GATE_FAILED"}
                else None
            )
            if (
                manifest_ref.get("stage") != manifest_stage
                or binding.get("stage") != manifest_stage
                or manifest.get("schema") != "task41.p0.b0.recovery_evidence.v1"
                or expected_status is None
                or manifest_status != expected_status
                or binding.get("status") != expected_status
            ):
                integrity_error(
                    "Task41 B0 recovery manifest stage/status binding is invalid"
                )
        except (OSError, ValueError, TypeError, KeyError) as exc:
            integrity_error(
                f"Task41 B0 recovery manifest failed its path/hash check: {exc}"
            )

    case = contract.get("case", {})
    window = contract.get("window", {})
    run_identity = manifest.get("run_identity", {})
    mode_inventory = summary.get("b0_mode_inventory", {})
    expected_identity = {
        "case_id": "B0",
        "run_id": summary.get("run_id"),
        "source_sha": contract.get("source", {}).get("sha")
        if isinstance(contract.get("source"), Mapping)
        else None,
        "input_sha256": case.get("input_sha256") if isinstance(case, Mapping) else None,
        "physical_model_sha256": case.get("physical_model_sha256")
        if isinstance(case, Mapping)
        else None,
        "campaign_window_sha256": window.get("sha256")
        if isinstance(window, Mapping)
        else None,
        "execution_contract_sha256": contract_sha256,
        "mode_manifest_sha256": mode_inventory.get("mode_manifest_sha256")
        if isinstance(mode_inventory, Mapping)
        else None,
    }
    if not isinstance(run_identity, Mapping):
        integrity_error("Task41 B0 recovery manifest has no run identity")
        run_identity = {}
    for key, expected in expected_identity.items():
        if not expected or run_identity.get(key) != expected:
            integrity_error(f"Task41 B0 recovery run identity differs at {key}")
    for key in ("staged_input_sha256", "carrier_committed_prefix_sha256"):
        value = run_identity.get(key)
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
        ):
            integrity_error(f"Task41 B0 recovery run identity has invalid {key}")
    manifest_identity_binding_valid = manifest_loaded and not integrity_errors

    support = manifest.get("saved_surface_support_certificate")
    summary_support = summary.get("b0_saved_surface_support_certificate")
    support_nonzero = (
        support.get("cell_interior_nonzero_values")
        if isinstance(support, Mapping)
        else None
    )
    support_digest = hashlib.sha256(
        json.dumps(
            support if isinstance(support, Mapping) else {},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    if (
        not isinstance(support, Mapping)
        or support.get("schema") != "task41.p0.b0.saved_surface_support_inventory.v1"
        or support != summary_support
        or support_nonzero != 0
        or manifest.get("local_interior_Bi_Di_exact_zero") is not True
        or manifest.get("local_interior_Bi_Di_nonzero_entry_count") != 0
        or manifest.get("saved_surface_support_certificate_passed") is not True
        or manifest.get("saved_surface_support_certificate_sha256") != support_digest
    ):
        integrity_error("Task41 B0 exact-zero local Bi/Di support certificate is absent or mismatched")
    loop = binding.get("same_lu_refinement_loop")
    loop_identity_matches = (
        isinstance(loop, Mapping)
        and loop.get("production_and_witness_share_loop") is True
        and loop.get("maximum_steps_per_column") == 3
        and loop.get("full_carrier_sweeps_per_correction") == 0
        and loop.get("correction_driver")
        == "independent_native_cell_interior_volume_residual"
    )
    legacy_failed_missing_step_limit = (
        "b0_recovery_refinement_max_steps" not in summary
        and manifest_identity_binding_valid
        and manifest.get("stage") == "FULL_ACTION_GATE_FAILED"
        and manifest.get("status") == "FAIL"
        and binding.get("stage") == "FULL_ACTION_GATE_FAILED"
        and binding.get("status") == "FAIL"
        and loop_identity_matches
        and loop.get("production_route_reached") is False
    )
    if (
        summary.get("b0_recovery_refinement_max_steps") != 3
        and not legacy_failed_missing_step_limit
    ):
        integrity_error(
            "Task41 B0 production path is not bound to the shared three-step recovery loop"
        )
    if not loop_identity_matches:
        integrity_error("Task41 B0 recovery evidence does not bind the shared same-LU correction loop")

    checked_columns = []
    shared_raw_classes: dict[str, tuple[str, str, str, str]] = {}
    columns = manifest.get("columns")
    full_rows = manifest.get("full_storage_rows")
    if type(full_rows) is not int or full_rows < 1:
        integrity_error("Task41 B0 recovery manifest has an invalid full storage size")
    if not isinstance(columns, list) or len(columns) != 2:
        integrity_error("Task41 B0 recovery manifest does not contain both input columns")
        columns = []

    def load_array(record: Any, label: str) -> np.ndarray:
        if not isinstance(record, Mapping):
            raise ValueError(f"{label} artifact record is missing")
        return _task41_npy_artifact(numerical_output.parent, record, label)

    def require_vector(record: Any, label: str, *, size: int | None = None) -> np.ndarray:
        value = load_array(record, label)
        if (
            value.ndim != 1
            or value.dtype != np.dtype(np.complex128)
            or (size is not None and value.shape != (size,))
        ):
            raise ValueError(f"{label} has an invalid complex-vector layout")
        return value

    def require_close_recorded(actual: float, recorded: Any, label: str) -> None:
        try:
            declared = float(recorded)
        except (TypeError, ValueError):
            integrity_error(f"Task41 B0 {label} metric is missing")
            return
        if not np.isfinite(declared) or abs(actual - declared) > 5.0e-13 * max(1.0, abs(actual)):
            integrity_error(f"Task41 B0 {label} metric differs from its raw arrays")

    full_action = manifest.get("full_action")
    if not isinstance(full_action, Mapping):
        integrity_error("Task41 B0 joint-action record is missing")
    else:
        joint = full_action.get("artifacts")
        if not isinstance(joint, Mapping):
            integrity_error("Task41 B0 joint-action artifact inventory is missing")
        else:
            try:
                p6 = load_array(joint.get("p6_result"), "joint P6 result")
                port_rhs = load_array(joint.get("port_rhs"), "joint port RHS")
                reduced_rhs = load_array(joint.get("reduced_rhs"), "joint reduced RHS")
                if (
                    p6.ndim != 2
                    or reduced_rhs.shape != p6.shape
                    or p6.shape[1] != 2
                    or port_rhs.ndim != 2
                    or port_rhs.shape[1] != 2
                    or port_rhs.shape[0] < 1
                    or port_rhs.shape[0] >= p6.shape[0]
                    or p6.dtype != np.dtype(np.complex128)
                    or port_rhs.dtype != np.dtype(np.complex128)
                    or reduced_rhs.dtype != np.dtype(np.complex128)
                    or not np.isfinite(p6).all()
                    or not np.isfinite(port_rhs).all()
                    or not np.isfinite(reduced_rhs).all()
                ):
                    raise ValueError(
                        "joint-action arrays have invalid shapes, dtypes, or non-finite values"
                    )

                active_rows = int(p6.shape[0] - port_rhs.shape[0])
                port_rows = int(port_rhs.shape[0])
                declared_errors = full_action.get(
                    "p6_vs_native_reduced_rhs_relative_errors"
                )
                if not isinstance(declared_errors, list) or len(declared_errors) != 2:
                    integrity_error(
                        "Task41 B0 joint-action record omits both per-column error metrics"
                    )

                column_metrics: list[dict[str, Any]] = []
                errors_by_column: list[float] = []
                for column_index in range(2):
                    left = p6[:, column_index]
                    right = reduced_rhs[:, column_index]
                    denominator = max(
                        _task41_b0_chunked_norm(left),
                        _task41_b0_chunked_norm(right),
                        np.finfo(float).tiny,
                    )
                    overall = _task41_b0_chunked_difference_summary(left, right)
                    trace = _task41_b0_chunked_difference_summary(
                        left, right, start=0, stop=active_rows
                    )
                    port = _task41_b0_chunked_difference_summary(
                        left, right, start=active_rows, stop=int(p6.shape[0])
                    )
                    relative_error = overall["absolute_l2"] / denominator
                    errors_by_column.append(relative_error)
                    if isinstance(declared_errors, list) and len(declared_errors) == 2:
                        require_close_recorded(
                            relative_error,
                            declared_errors[column_index],
                            f"joint P6/native column {column_index} relative error",
                        )

                    p6_port = p6[active_rows:, column_index]
                    reduced_port = reduced_rhs[active_rows:, column_index]
                    saved_port_rhs = port_rhs[:, column_index]
                    port_comparisons = {
                        "p6_vs_reduced": _task41_b0_chunked_difference_summary(
                            p6_port, reduced_port
                        ),
                        "p6_vs_port_rhs": _task41_b0_chunked_difference_summary(
                            p6_port, saved_port_rhs
                        ),
                        "reduced_vs_port_rhs": _task41_b0_chunked_difference_summary(
                            reduced_port, saved_port_rhs
                        ),
                        "p6_port_norm": _task41_b0_chunked_norm(p6_port),
                        "reduced_port_norm": _task41_b0_chunked_norm(reduced_port),
                        "port_rhs_norm": _task41_b0_chunked_norm(saved_port_rhs),
                    }
                    for comparison in (
                        "p6_vs_reduced",
                        "p6_vs_port_rhs",
                        "reduced_vs_port_rhs",
                    ):
                        port_comparisons[comparison][
                            "same_overall_denominator_contribution"
                        ] = (
                            port_comparisons[comparison]["absolute_l2"] / denominator
                        )
                    column_metrics.append(
                        {
                            "column": column_index,
                            "original_denominator": denominator,
                            "absolute_l2": overall["absolute_l2"],
                            "sum_squares": overall["sum_squares"],
                            "max_abs_row": overall["max_abs_row"],
                            "max_abs_row_index": overall["max_abs_row_index"],
                            "relative_error": relative_error,
                            "trace_rows": active_rows,
                            "trace": {
                                **trace,
                                "same_overall_denominator_contribution": (
                                    trace["absolute_l2"] / denominator
                                ),
                            },
                            "port_rows": port_rows,
                            "port": {
                                **port,
                                "same_overall_denominator_contribution": (
                                    port["absolute_l2"] / denominator
                                ),
                            },
                            "port_comparisons": port_comparisons,
                        }
                    )

                declared_d_error = full_action.get(
                    "original_and_active_D_relative_error"
                )
                try:
                    d_error = float(declared_d_error)
                except (TypeError, ValueError):
                    d_error = float("nan")
                d_passed = bool(np.isfinite(d_error) and d_error <= 1.0e-11)
                joint_action_passed = bool(
                    all(value <= 1.0e-11 for value in errors_by_column) and d_passed
                )
                if not d_passed:
                    joint_action_error(
                        "Task41 B0 recorded original/active D error fails the original gate"
                    )
                if not all(value <= 1.0e-11 for value in errors_by_column):
                    joint_action_error(
                        "Task41 B0 saved P6/native reduced RHS difference reproduces the original gate failure"
                    )
                expected_joint_status = "PASS" if joint_action_passed else "FAIL"
                if full_action.get("status") != expected_joint_status:
                    integrity_error(
                        "Task41 B0 joint-action status differs from its recomputed arrays"
                    )
                if full_action.get("valid_shapes_and_finite_values") is not True:
                    integrity_error(
                        "Task41 B0 joint-action finite/layout claim differs from valid saved arrays"
                    )
                joint_action_completed = True
                joint_action_metrics = column_metrics
            except (OSError, ValueError, TypeError, KeyError) as exc:
                integrity_error(f"Task41 B0 joint-action replay is incomplete: {exc}")

    save_checkpoint(
        "JOINT_ACTION_CHUNKS_COMPLETE",
        replayed=joint_action_completed,
        passed=joint_action_passed,
        metrics=joint_action_metrics,
        integrity_error_count=len(integrity_errors),
    )

    for expected_column, column in enumerate(columns):
        try:
            if not isinstance(column, Mapping):
                raise ValueError("column record is malformed")
            artifacts = column.get("artifacts")
            if not isinstance(artifacts, Mapping):
                raise ValueError("column artifact inventory is missing")
            if column.get("column") != expected_column or column.get("status") != "CAPTURED":
                raise ValueError("recovery column identity or captured status differs")
            mode_index = column.get("mode_index")
            input_rows = manifest.get("input_identities", [])
            identity_row = input_rows[expected_column]
            if (
                mode_index != expected_mode_indices[expected_column]
                or identity_row.get("mode_index") != mode_index
            ):
                raise ValueError("the two frozen selected B modes or column order differ")
            known = require_vector(artifacts.get("known_field"), "known field", size=full_rows)
            volume_rhs = require_vector(
                artifacts.get("native_volume_rhs"), "native volume RHS", size=full_rows
            )
            native_rhs = require_vector(
                artifacts.get("native_rhs"), "aggregate native RHS", size=full_rows
            )
            b_rows = load_array(artifacts.get("selected_B_frame_rows"), "selected B rows")
            b_values = load_array(artifacts.get("selected_B_frame_values"), "selected B values")
            b_alpha_rows = load_array(artifacts.get("b_alpha_rows"), "B-alpha rows")
            b_alpha_values = load_array(artifacts.get("b_alpha_values"), "B-alpha values")
            if (
                b_rows.ndim != 1
                or b_rows.dtype.kind not in "iu"
                or b_values.shape != b_rows.shape
                or b_values.dtype != np.dtype(np.complex128)
                or b_alpha_rows.ndim != 1
                or b_alpha_rows.dtype.kind not in "iu"
                or b_alpha_values.shape != b_alpha_rows.shape
                or b_alpha_values.dtype != np.dtype(np.complex128)
                or (b_rows.size and (int(b_rows[0]) < 0 or int(b_rows[-1]) >= full_rows))
                or (b_rows.size > 1 and np.any(b_rows[1:] <= b_rows[:-1]))
                or (b_alpha_rows.size > 1 and np.any(b_alpha_rows[1:] <= b_alpha_rows[:-1]))
                or (b_alpha_rows.size and (int(b_alpha_rows[0]) < 0 or int(b_alpha_rows[-1]) >= full_rows))
                or not np.isfinite(b_values).all()
                or not np.isfinite(b_alpha_values).all()
            ):
                raise ValueError("selected B-frame artifacts have invalid row/value layouts")
            alpha_pair = identity_row.get("port_alpha")
            if not isinstance(alpha_pair, list) or len(alpha_pair) != 2:
                raise ValueError("selected B input has no saved complex port amplitude")
            alpha = complex(float(alpha_pair[0]), float(alpha_pair[1]))
            if not np.isfinite([alpha.real, alpha.imag]).all():
                raise ValueError("selected B input amplitude is non-finite")
            expected_b_values = b_values * alpha
            nonzero = expected_b_values != 0.0
            if not np.array_equal(b_alpha_rows, b_rows[nonzero]) or not np.array_equal(
                b_alpha_values, expected_b_values[nonzero]
            ):
                raise ValueError("saved B-alpha vector does not replay from the selected B frame")
            for start in range(0, full_rows, 262_144):
                stop = min(full_rows, start + 262_144)
                expected_rhs = np.asarray(volume_rhs[start:stop], dtype=np.complex128).copy()
                selected = (b_alpha_rows >= start) & (b_alpha_rows < stop)
                if np.any(selected):
                    expected_rhs[b_alpha_rows[selected] - start] += b_alpha_values[selected]
                if not np.array_equal(expected_rhs, np.asarray(native_rhs[start:stop])):
                    raise ValueError("aggregate native RHS does not equal saved volume RHS plus B-alpha")

            active_original_rows = load_array(
                artifacts.get("active_original_rows"), "active original rows"
            )
            slave_rows = load_array(artifacts.get("slave_rows"), "MPC slave rows")
            if (
                active_original_rows.ndim != 1
                or active_original_rows.dtype.kind not in "iu"
                or slave_rows.ndim != 1
                or slave_rows.dtype.kind not in "iu"
                or np.any(active_original_rows < 0)
                or np.any(active_original_rows >= full_rows)
                or np.any(slave_rows < 0)
                or np.any(slave_rows >= full_rows)
                or np.unique(active_original_rows).size != active_original_rows.size
                or np.unique(slave_rows).size != slave_rows.size
                or np.intersect1d(active_original_rows, slave_rows).size
            ):
                raise ValueError("active or slave original-row identity is malformed")

            initial_storage = require_vector(
                artifacts.get("recovered_storage"), "initial recovered storage", size=full_rows
            )
            initial_action = require_vector(
                artifacts.get("native_volume_action_recovered"),
                "initial native volume action",
                size=full_rows,
            )
            initial_residual = require_vector(
                artifacts.get("native_volume_residual"), "initial native volume residual", size=full_rows
            )
            if _task41_b0_chunked_residual_discrepancy(
                initial_residual, volume_rhs, initial_action
            ) > 5.0e-13 * max(1.0, _task41_b0_chunked_norm(volume_rhs)):
                raise ValueError("initial native volume residual does not replay from raw vectors")
            if (
                not _task41_b0_indexed_arrays_equal(
                    initial_storage, known, active_original_rows
                )
                or not _task41_b0_indexed_arrays_equal(
                    known, known, slave_rows, zero=True
                )
                or not _task41_b0_indexed_arrays_equal(
                    volume_rhs, volume_rhs, slave_rows, zero=True
                )
                or not _task41_b0_indexed_arrays_equal(
                    native_rhs, native_rhs, slave_rows, zero=True
                )
                or not _task41_b0_indexed_arrays_equal(
                    initial_storage, initial_storage, slave_rows, zero=True
                )
                or not _task41_b0_indexed_arrays_equal(
                    initial_action, initial_action, slave_rows, zero=True
                )
                or not _task41_b0_indexed_arrays_equal(
                    initial_residual, initial_residual, slave_rows, zero=True
                )
            ):
                raise ValueError("initial recovery did not preserve trace/slave storage identities")
            initial_forward = _task41_b0_chunked_relative_error(initial_storage, known)
            initial_residual_relative = (
                _task41_b0_chunked_norm(initial_residual)
                / max(_task41_b0_chunked_norm(volume_rhs), np.finfo(float).tiny)
            )
            require_close_recorded(
                initial_forward, column.get("forward_relative_error"), "initial forward error"
            )
            require_close_recorded(
                initial_residual_relative,
                column.get("native_volume_residual_relative"),
                "initial volume residual",
            )

            refinement = column.get("same_lu_refinement", [])
            if not isinstance(refinement, list) or len(refinement) > 3:
                raise ValueError("same-LU correction inventory exceeds three steps")
            final_storage = initial_storage
            final_residual_relative = initial_residual_relative
            final_forward = initial_forward
            for step, record in enumerate(refinement, start=1):
                if not isinstance(record, Mapping) or record.get("step") != step:
                    raise ValueError("same-LU correction steps are missing or out of order")
                step_artifacts = record.get("artifacts")
                if not isinstance(step_artifacts, Mapping):
                    raise ValueError("same-LU correction step omits raw artifacts")
                final_storage = require_vector(
                    step_artifacts.get("storage"), "same-LU storage", size=full_rows
                )
                step_action = require_vector(
                    step_artifacts.get("native_volume_action"),
                    "same-LU volume action",
                    size=full_rows,
                )
                step_residual = require_vector(
                    step_artifacts.get("native_volume_residual"),
                    "same-LU volume residual",
                    size=full_rows,
                )
                discrepancy = _task41_b0_chunked_residual_discrepancy(
                    step_residual, volume_rhs, step_action
                )
                if discrepancy > 5.0e-13 * max(
                    1.0, _task41_b0_chunked_norm(volume_rhs)
                ):
                    raise ValueError("same-LU native volume residual does not replay")
                final_forward = _task41_b0_chunked_relative_error(final_storage, known)
                final_residual_relative = _task41_b0_chunked_norm(step_residual) / max(
                    _task41_b0_chunked_norm(volume_rhs), np.finfo(float).tiny
                )
                if (
                    not _task41_b0_indexed_arrays_equal(
                        final_storage, known, active_original_rows
                    )
                    or not _task41_b0_indexed_arrays_equal(
                        final_storage, final_storage, slave_rows, zero=True
                    )
                    or not _task41_b0_indexed_arrays_equal(
                        step_action, step_action, slave_rows, zero=True
                    )
                    or not _task41_b0_indexed_arrays_equal(
                        step_residual, step_residual, slave_rows, zero=True
                    )
                ):
                    raise ValueError("same-LU correction changed trace or nonzero MPC slave storage")
                require_close_recorded(
                    final_forward, record.get("forward_relative_error"), "same-LU forward error"
                )
                require_close_recorded(
                    final_residual_relative,
                    record.get("native_volume_residual_relative"),
                    "same-LU volume residual",
                )

            if refinement:
                require_close_recorded(
                    final_forward, column.get("final_forward_relative_error"), "final forward error"
                )
                require_close_recorded(
                    final_residual_relative,
                    column.get("final_native_volume_residual_relative"),
                    "final volume residual",
                )

            initial_gate_passed = bool(
                np.isfinite(initial_forward)
                and initial_forward <= 1.0e-11
                and np.isfinite(initial_residual_relative)
                and initial_residual_relative <= 1.0e-10
            )
            final_gate_passed = bool(
                np.isfinite(final_forward)
                and final_forward <= 1.0e-11
                and np.isfinite(final_residual_relative)
                and final_residual_relative <= 1.0e-10
            )
            column_passed = bool(
                final_gate_passed
                and column.get("recovery_passed") is True
                and (
                    bool(refinement)
                    or column.get("final_forward_relative_error") is None
                )
            )
            column_result = {
                "column": expected_column,
                "mode_index": mode_index,
                "initial_forward_relative": initial_forward,
                "initial_native_volume_residual_relative": initial_residual_relative,
                "initial_gate_passed": initial_gate_passed,
                "same_lu_steps_replayed": len(refinement),
                "final_forward_relative": final_forward,
                "final_native_volume_residual_relative": final_residual_relative,
                "final_gate_passed": final_gate_passed,
                "manifest_claim_matches_recomputed_gate": (
                    column.get("recovery_passed") is final_gate_passed
                ),
                "passed": column_passed,
            }
            checked_columns.append(column_result)
            if not column_passed:
                recovery_error(
                    f"Task41 B0 recovery column {expected_column} finite gate failed: "
                    f"forward={final_forward}, volume_residual={final_residual_relative}"
                )

            raw_integrity_errors_before = len(integrity_errors)
            raw_diagnostic = column.get("raw_cell_diagnostic")
            if refinement or not initial_gate_passed:
                if (
                    not isinstance(raw_diagnostic, Mapping)
                    or raw_diagnostic.get("structure_identity_passed") is not True
                    or raw_diagnostic.get("raw_matrices_are_independently_retabulated") is not True
                    or not isinstance(raw_diagnostic.get("cells"), list)
                    or not 1 <= len(raw_diagnostic["cells"]) <= 3
                ):
                    integrity_error(
                        f"Task41 B0 recovery column {expected_column} lacks bounded raw-cell evidence"
                    )
                else:
                    for cell in raw_diagnostic["cells"]:
                        cell_artifacts = cell.get("artifacts", {})
                        class_artifacts = cell.get("class_artifacts", {})
                        class_identity = str(class_artifacts.get("class_identity", ""))
                        class_refs = tuple(
                            str(class_artifacts.get(name, {}).get("path", ""))
                            for name in ("Vii", "Vit", "lu_factor", "lu_pivots")
                        )
                        if not class_identity or any(not path for path in class_refs):
                            integrity_error("Task41 B0 raw class lacks matrix/LU artifact identity")
                            continue
                        if class_identity in shared_raw_classes and shared_raw_classes[class_identity] != class_refs:
                            integrity_error("Task41 B0 repeated raw class matrices were not shared")
                            continue
                        shared_raw_classes[class_identity] = class_refs
                        vii = np.asarray(load_array(class_artifacts.get("Vii"), "raw Vii"))
                        vit = np.asarray(load_array(class_artifacts.get("Vit"), "raw Vit"))
                        lu_factor = np.asarray(load_array(class_artifacts.get("lu_factor"), "raw local LU"))
                        lu_pivots = np.asarray(load_array(class_artifacts.get("lu_pivots"), "raw local pivots"))
                        known_i = np.asarray(load_array(cell_artifacts.get("known_interior"), "raw known interior"))
                        known_t = np.asarray(load_array(cell_artifacts.get("known_trace"), "raw known trace"))
                        rhs_i = np.asarray(load_array(cell_artifacts.get("native_volume_rhs_interior"), "raw volume RHS interior"))
                        rec_i = np.asarray(load_array(cell_artifacts.get("recovered_interior"), "raw recovered interior"))
                        rec_t = np.asarray(load_array(cell_artifacts.get("recovered_trace"), "raw recovered trace"))
                        action_i = np.asarray(load_array(cell_artifacts.get("native_volume_action_interior"), "raw volume action interior"))
                        residual_i = np.asarray(load_array(cell_artifacts.get("native_volume_residual_interior"), "raw volume residual interior"))
                        interior_rows = np.asarray(load_array(cell_artifacts.get("interior_original_rows"), "raw interior row map"))
                        trace_rows = np.asarray(load_array(cell_artifacts.get("trace_original_rows"), "raw trace row map"))
                        active_ids = np.asarray(load_array(cell_artifacts.get("active_ids"), "raw active ids"))
                        expansion_data = np.asarray(load_array(cell_artifacts.get("trace_expansion_data"), "raw trace expansion data"))
                        expansion_indices = np.asarray(load_array(cell_artifacts.get("trace_expansion_indices"), "raw trace expansion indices"))
                        expansion_indptr = np.asarray(load_array(cell_artifacts.get("trace_expansion_indptr"), "raw trace expansion indptr"))
                        permutation = np.asarray(load_array(cell_artifacts.get("cell_permutation_info"), "raw cell permutation"))
                        if (
                            vii.ndim != 2 or vit.ndim != 2 or vii.shape[0] != vii.shape[1]
                            or vit.shape[0] != vii.shape[0]
                            or lu_factor.shape != vii.shape or lu_pivots.shape != (vii.shape[0],)
                            or lu_pivots.dtype.kind not in "iu"
                            or vii.dtype != np.dtype(np.complex128)
                            or vit.dtype != np.dtype(np.complex128)
                            or lu_factor.dtype != np.dtype(np.complex128)
                            or known_i.shape != (vii.shape[0],) or rhs_i.shape != known_i.shape
                            or rec_i.shape != known_i.shape or known_t.shape != (vit.shape[1],)
                            or rec_t.shape != known_t.shape
                            or action_i.shape != known_i.shape or residual_i.shape != known_i.shape
                            or any(
                                value.dtype != np.dtype(np.complex128)
                                for value in (known_i, rhs_i, rec_i, known_t, rec_t, action_i, residual_i)
                            )
                            or interior_rows.shape != known_i.shape or interior_rows.dtype.kind not in "iu"
                            or trace_rows.shape != known_t.shape or trace_rows.dtype.kind not in "iu"
                            or np.any(interior_rows < 0) or np.any(interior_rows >= full_rows)
                            or np.any(trace_rows < 0) or np.any(trace_rows >= full_rows)
                            or np.unique(interior_rows).size != interior_rows.size
                            or np.unique(trace_rows).size != trace_rows.size
                            or active_ids.ndim != 1 or active_ids.dtype.kind not in "iu"
                            or np.any(active_ids < 0) or np.any(active_ids >= active_original_rows.size)
                            or np.unique(active_ids).size != active_ids.size
                            or expansion_data.ndim != 1
                            or expansion_data.dtype != np.dtype(np.complex128)
                            or expansion_indices.ndim != 1
                            or expansion_indices.dtype.kind not in "iu"
                            or expansion_indptr.ndim != 1
                            or expansion_indptr.dtype.kind not in "iu"
                            or expansion_indptr.shape != (len(trace_rows) + 1,)
                            or expansion_indices.shape != expansion_data.shape
                            or expansion_indptr[0] != 0
                            or np.any(expansion_indptr < 0)
                            or np.any(expansion_indptr[1:] < expansion_indptr[:-1])
                            or expansion_indptr[-1] != len(expansion_data)
                            or np.any(expansion_indices < 0)
                            or np.any(expansion_indices >= len(active_ids))
                            or not np.isfinite(vii).all()
                            or not np.isfinite(vit).all()
                            or not np.isfinite(lu_factor).all()
                            or not np.isfinite(expansion_data).all()
                            or permutation.shape != (1,)
                            or permutation.dtype.kind not in "iu"
                        ):
                            integrity_error("Task41 B0 raw-cell Vii/Vit evidence has inconsistent local layouts")
                            continue
                        try:
                            from scipy.sparse import csr_matrix
                            from scipy.linalg import lu_solve

                            expansion = csr_matrix(
                                (expansion_data, expansion_indices, expansion_indptr),
                                shape=(len(trace_rows), len(active_ids)),
                            )
                            if not expansion.has_canonical_format:
                                raise ValueError("raw trace-expansion CSR is not canonical")
                            active_values = np.asarray(known[active_original_rows], dtype=np.complex128)
                            recovered_active_values = np.asarray(initial_storage[active_original_rows], dtype=np.complex128)
                            expected_known_trace = np.asarray(
                                expansion @ active_values[active_ids], dtype=np.complex128
                            ).reshape(-1)
                            expected_recovered_trace = np.asarray(
                                expansion @ recovered_active_values[active_ids], dtype=np.complex128
                            ).reshape(-1)
                            writable_pivots = _task41_b0_owned_writable_lu_pivots(
                                lu_pivots, order=vii.shape[0]
                            )
                            save_checkpoint(
                                "BEFORE_SMALL_CLASS_GETRS",
                                column=expected_column,
                                class_identity=class_identity,
                                factor_shape=list(lu_factor.shape),
                                factor_dtype=str(lu_factor.dtype),
                                pivot_dtype=str(lu_pivots.dtype),
                                pivot_copy_dtype=str(writable_pivots.dtype),
                                pivot_copy_owns_data=bool(writable_pivots.flags.owndata),
                                pivot_copy_writeable=bool(writable_pivots.flags.writeable),
                            )
                            lu_identity = lu_solve((lu_factor, writable_pivots), vii)
                            lu_identity_max_abs_error = float(
                                np.max(np.abs(lu_identity - np.eye(vii.shape[0])))
                            )
                            save_checkpoint(
                                "AFTER_SMALL_CLASS_GETRS",
                                column=expected_column,
                                class_identity=class_identity,
                                lu_identity_max_abs_error=lu_identity_max_abs_error,
                            )
                        except (ValueError, TypeError, IndexError) as exc:
                            integrity_error(f"Task41 B0 raw cell mapping/LU replay failed: {exc}")
                            continue
                        if (
                            not np.array_equal(known_i, known[interior_rows])
                            or not np.array_equal(volume_rhs[interior_rows], rhs_i)
                            or not np.array_equal(initial_storage[interior_rows], rec_i)
                            or not np.array_equal(initial_action[interior_rows], action_i)
                            or not np.array_equal(initial_residual[interior_rows], residual_i)
                            or not np.array_equal(known_t, expected_known_trace)
                            or not np.array_equal(rec_t, expected_recovered_trace)
                            or not np.allclose(lu_identity, np.eye(vii.shape[0]), rtol=1e-10, atol=1e-10)
                        ):
                            integrity_error("Task41 B0 raw local rows, MPC trace expansion, or LU identity failed")
                            continue
                        known_action = vii @ known_i + vit @ known_t
                        recovered_action = vii @ rec_i + vit @ rec_t
                        local_scale = max(float(np.linalg.norm(rhs_i)), float(np.linalg.norm(action_i)), np.finfo(float).tiny)
                        if (
                            np.linalg.norm(known_action - rhs_i) / local_scale > 1.0e-10
                            or np.linalg.norm(recovered_action - action_i) / local_scale > 1.0e-10
                            or not np.allclose(rhs_i - action_i, residual_i, rtol=5e-13, atol=5e-13)
                        ):
                            integrity_error("Task41 B0 independent raw-cell Vii/Vit replay failed")
            raw_audit_passed = len(integrity_errors) == raw_integrity_errors_before
            if raw_audit_passed:
                raw_audit_completed_columns += 1
            save_checkpoint(
                "COLUMN_AUDIT_RETURNED",
                column=expected_column,
                mode_index=column_result["mode_index"],
                recovery_passed=column_result["passed"],
                raw_audit_passed=raw_audit_passed,
                integrity_error_count=len(integrity_errors),
            )
        except (OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            integrity_error(f"Task41 B0 recovery column {expected_column} replay failed: {exc}")
            save_checkpoint(
                "COLUMN_AUDIT_RETURNED",
                column=expected_column,
                status="ERROR",
                error=str(exc),
                integrity_error_count=len(integrity_errors),
            )

    actual_steps = max(
        (
            len(row.get("same_lu_refinement", []))
            for row in columns
            if isinstance(row, Mapping)
        ),
        default=0,
    )
    recorded_steps = manifest.get("same_lu_refinement_max_steps_used", 0)
    if type(recorded_steps) is not int or recorded_steps != actual_steps or not 0 <= recorded_steps <= 3:
        integrity_error("Task41 B0 manifest same-LU step count differs from its raw states")
    if len(shared_raw_classes) > 3:
        integrity_error("Task41 B0 recovery evidence stores more than three raw local classes")
    recovery_passed = bool(
        len(checked_columns) == 2
        and all(row.get("passed") is True for row in checked_columns)
    )
    audit_completed = bool(
        manifest_loaded
        and len(checked_columns) == 2
        and raw_audit_completed_columns == 2
        and joint_action_completed
    )
    data_integrity = not integrity_errors
    qualification_passed = bool(
        audit_completed
        and data_integrity
        and recovery_passed
        and joint_action_passed is True
        and manifest.get("status") == "PASS"
        and binding.get("status") == "PASS"
    )
    # This helper audits recovery/action evidence only; it does not certify an
    # official target solve, full-field residual, or physical-output result.
    official_result = False
    return {
        "schema": "task41.p0.b0.recovery_evidence_checker.v1",
        "manifest_path": manifest_ref.get("path") if isinstance(manifest_ref, Mapping) else None,
        "manifest_stage": manifest.get("stage"),
        "audit_completed": audit_completed,
        "legacy_failed_missing_step_limit_accepted": legacy_failed_missing_step_limit,
        "production_route_reached": (
            loop.get("production_route_reached")
            if isinstance(loop, Mapping) and type(loop.get("production_route_reached")) is bool
            else None
        ),
        "data_integrity": data_integrity,
        "integrity_errors": integrity_errors,
        "recovery_passed": recovery_passed,
        "recovery_errors": recovery_errors,
        "joint_action_status": (
            "PASS"
            if joint_action_passed is True
            else "FAIL"
            if joint_action_passed is False
            else "NOT_RUN"
        ),
        "joint_action_passed": joint_action_passed,
        "joint_action_replayed": joint_action_completed,
        "joint_action_errors": joint_action_errors,
        "joint_action_metrics": joint_action_metrics,
        "checkpoints": checkpoint_events,
        "qualification_passed": qualification_passed,
        "official_result": official_result,
        "run_identity_rechecked": not any("identity" in error for error in integrity_errors),
        "support_certificate_rechecked": not any(
            "support certificate" in error for error in integrity_errors
        ),
        "columns": checked_columns,
        "errors": errors,
        "passed": qualification_passed,
    }


def check_task41_p0_b0_v9_failed_terminal_audit(
    *,
    run_root: str | Path,
    summary_path: str | Path,
    manifest_path: str | Path,
    producer_contract_path: str | Path,
    producer_contract_sha256: str,
    consumer_contract_path: str | Path,
    consumer_contract_sha256: str,
    output_path: str | Path,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    """Audit V9 compact evidence under a distinct, frozen consumer contract."""
    root = Path(repo_root or Path(__file__).resolve().parents[2]).resolve()
    supplied_run_root = Path(run_root).resolve(strict=True)
    manifest_file = Path(manifest_path).resolve(strict=True)
    summary_file = Path(summary_path).resolve(strict=True)
    if manifest_file.parent != supplied_run_root:
        raise ValueError("V9 terminal audit run root must be the verified manifest parent")

    producer, producer_digest = require_task41_p0_contract(
        producer_contract_path,
        expected_sha256=producer_contract_sha256,
        current_root=root,
        check_current_source=False,
        require_clean_source=False,
        case_id="B0",
    )
    consumer, consumer_digest = require_task41_p0_contract(
        consumer_contract_path,
        expected_sha256=consumer_contract_sha256,
        current_root=root,
        check_current_source=True,
        require_clean_source=False,
        case_id="B0",
    )
    producer_case = producer["case"]
    consumer_case = consumer["case"]
    identity_fields = (
        "model_id", "run_id", "method", "mpi_size", "input_sha256",
        "physical_model_sha256", "resolved_config_sha256", "profile_identity",
        "solver_stage", "comparison_group", "geometry_identity",
    )
    if any(producer_case.get(key) != consumer_case.get(key) for key in identity_fields):
        raise ValueError("V9 producer and audit consumer contracts differ in B0 identity")

    results_root = (root / "results" / str(producer_case["model_id"])).resolve()
    numerical_output = supplied_run_root / "numerical_output"
    if (
        not supplied_run_root.is_relative_to(results_root)
        or summary_file != supplied_run_root / "task40_v10_p6_candidate_summary.json"
        or manifest_file != supplied_run_root / "run_manifest.json"
        or (numerical_output.exists() and not numerical_output.is_dir())
    ):
        raise ValueError("V9 terminal audit paths differ from the registered B0 producer run")

    manifest = _json_object(manifest_file, "V9 producer run manifest")
    launcher_summary = _json_object(
        supplied_run_root / "run_summary.json", "V9 producer launcher summary"
    )
    expected_manifest = {
        "model_id": producer_case["model_id"],
        "run_id": producer_case["run_id"],
        "method": producer_case["method"],
        "mpi_size": producer_case["mpi_size"],
        "input_sha256": producer_case["input_sha256"],
        "physical_model_sha256": producer_case["physical_model_sha256"],
        "resolved_config_sha256": producer_case["resolved_config_sha256"],
        "source_sha": producer["source"]["sha"],
    }
    if (
        any(manifest.get(key) != value for key, value in expected_manifest.items())
        or Path(str(manifest.get("output_directory", ""))).resolve() != supplied_run_root
        or Path(str(manifest.get("numerical_output_directory", ""))).resolve()
        != numerical_output
        or launcher_summary.get("run_id") != producer_case["run_id"]
        or Path(str(launcher_summary.get("output_directory", ""))).resolve()
        != supplied_run_root
        or Path(str(launcher_summary.get("numerical_output_directory", ""))).resolve()
        != numerical_output
    ):
        raise ValueError("V9 producer manifest or launcher summary differs from its frozen contract")

    copied_input = supplied_run_root / "input_original.dat"
    resolved_config = supplied_run_root / "resolved_config.json"
    input_path = Path(str(producer_case["input_path"])).resolve()
    if (
        not copied_input.is_file()
        or sha256_file(copied_input) != producer_case["input_sha256"]
        or not resolved_config.is_file()
        or sha256_file(resolved_config) != producer_case["resolved_config_sha256"]
        or not input_path.is_file()
        or sha256_file(input_path) != producer_case["input_sha256"]
    ):
        raise ValueError("V9 producer DAT or resolved configuration identity differs")

    candidate_summary = _json_object(summary_file, "V9 B0 candidate summary")
    authority = candidate_summary.get("campaign_authority")
    producer_window = producer["window"]
    expected_window_path = Path(str(producer_window["path"]))
    expected_window_path = (
        expected_window_path if expected_window_path.is_absolute() else root / expected_window_path
    ).resolve()
    if (
        candidate_summary.get("run_id") != producer_case["run_id"]
        or candidate_summary.get("source_sha") != producer["source"]["sha"]
        or not isinstance(authority, Mapping)
        or authority.get("case_id") != "B0"
        or Path(str(authority.get("task41_contract_path", ""))).resolve()
        != Path(producer_contract_path).resolve()
        or authority.get("task41_contract_sha256") != producer_digest
        or authority.get("source_sha") != producer["source"]["sha"]
        or authority.get("campaign_window_sha256") != producer_window.get("sha256")
        or Path(str(authority.get("campaign_window_path", ""))).resolve()
        != expected_window_path
    ):
        raise ValueError("V9 candidate summary is not bound to its producer contract/window")

    evidence = _task41_b0_recovery_evidence_checks(
        candidate_summary,
        numerical_output,
        producer,
        contract_sha256=producer_digest,
        run_root=manifest_file.parent,
    )
    v9_binding = candidate_summary.get("b0_v9_compact_volume_audit")
    recovery_gate = v9_binding.get("recovery_gate") if isinstance(v9_binding, Mapping) else None
    action_passed = evidence.get("joint_action_passed")
    audit_completed = evidence.get("audit_completed") is True and evidence.get("data_integrity") is True
    result = {
        "schema": "task41.p0.b0.v9.failed_terminal_audit.v1",
        "status": (
            "AUDIT_COMPLETED_ACTION_GATE_FAILED"
            if audit_completed and action_passed is False
            else "AUDIT_COMPLETED"
            if audit_completed
            else "INCOMPLETE"
        ),
        "audit_completed": audit_completed,
        "data_integrity": evidence.get("data_integrity") is True,
        "action_passed": action_passed,
        "recovery_status": recovery_gate.get("status") if isinstance(recovery_gate, Mapping) else None,
        "official_result": False,
        "producer": {
            "contract_path": str(Path(producer_contract_path).resolve()),
            "contract_sha256": producer_digest,
            "source_sha": producer["source"]["sha"],
            "window_sha256": producer_window.get("sha256"),
            "run_root": str(manifest_file.parent),
            "run_manifest_sha256": sha256_file(manifest_file),
            "launcher_summary_sha256": sha256_file(supplied_run_root / "run_summary.json"),
            "candidate_summary_sha256": sha256_file(summary_file),
        },
        "consumer": {
            "contract_path": str(Path(consumer_contract_path).resolve()),
            "contract_sha256": consumer_digest,
            "source_sha": consumer["source"]["sha"],
            "window_sha256": consumer["window"].get("sha256"),
        },
        "recovery_evidence_recheck": evidence,
        "errors": evidence.get("errors", []),
        "raw_evidence_retained": True,
    }
    output = Path(output_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(output.name + ".tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output)
    return result


def load_task41_v4_volume_only_donor(
    *, summary_path: Path, numerical_output: Path, metadata_only: bool = False
) -> dict[str, Any]:
    """Load only the hash-bound B0 arrays needed by the V4 volume audit.

    This intentionally reuses the saved-audit artifact checker and returns the
    narrow normalized mapping consumed by the V4 solver helper. The existing
    full saved-evidence checker still runs in the service's closeout phase.
    """

    from src.solvers.task41_v4_volume_only_audit import (
        TASK41_V4_DONOR_MANIFEST_SHA256,
        TASK41_V4_DONOR_NPY_BYTES,
    )

    summary_path = Path(summary_path).resolve(strict=True)
    run_root = summary_path.parent.resolve(strict=True)
    numerical_output = Path(numerical_output).resolve()
    if (
        summary_path.name != "task40_v10_p6_candidate_summary.json"
        or numerical_output != run_root / "numerical_output"
    ):
        raise ValueError("Task41 V4 donor path differs from the registered saved-output run")
    summary = _json_object(summary_path, "Task41 V4 donor summary")
    binding = summary.get("b0_recovery_evidence")
    manifest_ref = binding.get("manifest") if isinstance(binding, Mapping) else None
    if not isinstance(manifest_ref, Mapping):
        raise ValueError("Task41 V4 donor summary omits the recovery-manifest reference")
    manifest_path = _task41_run_artifact(run_root, manifest_ref, "V4 recovery manifest")
    manifest_sha256 = sha256_file(manifest_path)
    if manifest_sha256 != TASK41_V4_DONOR_MANIFEST_SHA256:
        raise ValueError("Task41 V4 donor recovery-manifest hash differs from the frozen identity")
    manifest = _json_object(manifest_path, "Task41 V4 recovery manifest")

    evidence_records: dict[str, int] = {}

    def collect_array_records(value: Any) -> None:
        if isinstance(value, Mapping):
            if (
                isinstance(value.get("path"), str)
                and isinstance(value.get("shape"), list)
                and isinstance(value.get("dtype"), str)
            ):
                raw_path = Path(str(value["path"]))
                path = (raw_path if raw_path.is_absolute() else run_root / raw_path).resolve()
                if not path.is_relative_to(run_root) or type(value.get("bytes")) is not int:
                    raise ValueError("Task41 V4 evidence inventory has an invalid array artifact")
                size = int(value["bytes"])
                previous = evidence_records.setdefault(str(path), size)
                if previous != size:
                    raise ValueError("Task41 V4 repeated artifact path has conflicting byte counts")
            for nested in value.values():
                collect_array_records(nested)
        elif isinstance(value, list):
            for nested in value:
                collect_array_records(nested)

    collect_array_records(manifest)
    if len(evidence_records) != 141 or sum(evidence_records.values()) != TASK41_V4_DONOR_NPY_BYTES:
        raise ValueError("Task41 V4 donor does not bind the frozen 141-array evidence set")

    def load(record: Any, label: str) -> np.ndarray:
        if not isinstance(record, Mapping):
            raise ValueError(f"Task41 V4 {label} artifact record is missing")
        return _task41_npy_artifact(run_root, record, label)

    columns_meta = manifest.get("columns")
    raw_groups = manifest.get("raw_cell_diagnostics")
    if not isinstance(columns_meta, list) or len(columns_meta) != 2 or not isinstance(raw_groups, list) or len(raw_groups) != 2:
        raise ValueError("Task41 V4 donor manifest omits one of its two volume columns")
    if metadata_only:
        columns = []
        for column_index, column_meta in enumerate(columns_meta):
            artifacts = column_meta.get("artifacts")
            if not isinstance(artifacts, Mapping):
                raise ValueError(f"Task41 V4 column {column_index} artifact inventory is missing")
            active_rows = load(
                artifacts.get("active_original_rows"),
                f"column {column_index} active_original_rows",
            )
            if active_rows.ndim != 1 or active_rows.dtype.kind not in "iu":
                raise ValueError(
                    f"Task41 V4 column {column_index} active-original row map is not a 1-D integer array"
                )
            columns.append({"active_original_rows": active_rows})
        if not np.array_equal(
            np.asarray(columns[0]["active_original_rows"]),
            np.asarray(columns[1]["active_original_rows"]),
        ):
            raise ValueError("Task41 V4 donor columns disagree on the saved active-original row map")
        return {
            "manifest": manifest,
            "manifest_sha256": manifest_sha256,
            "existing_evidence_bytes": sum(evidence_records.values()),
            "columns": columns,
            "metadata_only": True,
        }
    columns: list[dict[str, Any]] = []
    raw_by_key: dict[tuple[Any, ...], dict[str, Any]] = {}
    cell_maps: list[dict[str, Any]] = []
    for column_index, column_meta in enumerate(columns_meta):
        artifacts = column_meta.get("artifacts")
        if not isinstance(artifacts, Mapping):
            raise ValueError(f"Task41 V4 column {column_index} artifact inventory is missing")
        column = {
            name: load(artifacts.get(name), f"column {column_index} {name}")
            for name in ("active_original_rows", "slave_rows", "known_field", "native_rhs")
        }
        for name in ("native_volume_rhs", "b_alpha_rows", "b_alpha_values", "selected_B_frame_rows", "selected_B_frame_values"):
            column[name] = load(artifacts.get(name), f"column {column_index} {name}")
        input_identity = manifest["input_identities"][column_index]
        alpha_pair = input_identity.get("port_alpha")
        if not isinstance(alpha_pair, list) or len(alpha_pair) != 2:
            raise ValueError(f"Task41 V4 column {column_index} port alpha is missing")
        alpha = complex(float(alpha_pair[0]), float(alpha_pair[1]))
        if not np.isfinite([alpha.real, alpha.imag]).all():
            raise ValueError(f"Task41 V4 column {column_index} port alpha is non-finite")
        expected_b_alpha = column["selected_B_frame_values"] * alpha
        nonzero = expected_b_alpha != 0.0
        full_rows = int(manifest.get("full_storage_rows", -1))
        frame_rows = column["selected_B_frame_rows"]
        frame_values = column["selected_B_frame_values"]
        b_alpha_rows = column["b_alpha_rows"]
        b_alpha_values = column["b_alpha_values"]
        if (
            frame_rows.ndim != 1
            or frame_rows.dtype.kind not in "iu"
            or frame_values.shape != frame_rows.shape
            or frame_values.dtype != np.dtype(np.complex128)
            or not np.isfinite(frame_values).all()
            or (frame_rows.size and (np.any(frame_rows < 0) or np.any(frame_rows >= full_rows)))
            or (frame_rows.size > 1 and np.any(frame_rows[1:] <= frame_rows[:-1]))
            or b_alpha_rows.ndim != 1
            or b_alpha_rows.dtype.kind not in "iu"
            or b_alpha_values.shape != b_alpha_rows.shape
            or b_alpha_values.dtype != np.dtype(np.complex128)
            or not np.isfinite(b_alpha_values).all()
            or (b_alpha_rows.size and (np.any(b_alpha_rows < 0) or np.any(b_alpha_rows >= full_rows)))
            or (b_alpha_rows.size > 1 and np.any(b_alpha_rows[1:] <= b_alpha_rows[:-1]))
            or not np.array_equal(b_alpha_rows, frame_rows[nonzero])
            or not np.array_equal(b_alpha_values, expected_b_alpha[nonzero])
        ):
            raise ValueError(f"Task41 V4 column {column_index} saved B-alpha does not replay")
        column["port_alpha"] = alpha

        state_artifacts = [
            (
                "j0",
                artifacts.get("recovered_storage"),
                artifacts.get("native_volume_action_recovered"),
                artifacts.get("native_volume_residual"),
            )
        ]
        refinement = column_meta.get("same_lu_refinement")
        if not isinstance(refinement, list) or len(refinement) != 3:
            raise ValueError(f"Task41 V4 column {column_index} lacks its saved j3 refinement state")
        last_step = refinement[-1]
        last_artifacts = last_step.get("artifacts") if isinstance(last_step, Mapping) else None
        if not isinstance(last_artifacts, Mapping) or last_step.get("step") != 3:
            raise ValueError(f"Task41 V4 column {column_index} last state is not step 3")
        state_artifacts.append(
            (
                "j3",
                last_artifacts.get("storage"),
                last_artifacts.get("native_volume_action"),
                last_artifacts.get("native_volume_residual"),
            )
        )
        column["states"] = [
            {
                "label": label,
                "storage": load(storage_ref, f"column {column_index} {label} storage"),
                "native_volume_action": load(action_ref, f"column {column_index} {label} action"),
                "native_volume_residual": load(residual_ref, f"column {column_index} {label} residual"),
            }
            for label, storage_ref, action_ref, residual_ref in state_artifacts
        ]
        columns.append(column)

        group = raw_groups[column_index]
        if (
            group.get("structure_identity_passed") is not True
            or group.get("raw_matrices_are_independently_retabulated") is not True
            or len(group.get("cells", ())) != 3
        ):
            raise ValueError(f"Task41 V4 column {column_index} raw-cell inventory is incomplete")
        for cell in group["cells"]:
            class_key = tuple(cell["class_key"])
            class_artifacts = cell["class_artifacts"]
            if class_key not in raw_by_key:
                raw_by_key[class_key] = {
                    "class_key": class_key,
                    "Vii": load(class_artifacts.get("Vii"), f"raw Vii class {class_key}"),
                    "Vit": load(class_artifacts.get("Vit"), f"raw Vit class {class_key}"),
                }
            cell_artifacts = cell["artifacts"]
            cell_maps.append(
                {
                    "column": column_index,
                    "cell_index": int(cell["cell_index"]),
                    "class_key": class_key,
                    **{
                        name: load(cell_artifacts.get(name), f"cell {cell['cell_index']} {name}")
                        for name in (
                            "interior_original_rows",
                            "trace_original_rows",
                            "active_ids",
                            "cell_permutation_info",
                            "trace_expansion_data",
                            "trace_expansion_indices",
                            "trace_expansion_indptr",
                        )
                    },
                }
            )

    full_action = manifest.get("full_action")
    joint_artifacts = full_action.get("artifacts") if isinstance(full_action, Mapping) else None
    if not isinstance(joint_artifacts, Mapping):
        raise ValueError("Task41 V4 donor full-action arrays are missing")
    support = manifest.get("saved_surface_support_certificate")
    support_digest = hashlib.sha256(
        json.dumps(
            support if isinstance(support, Mapping) else {},
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    if (
        not isinstance(support, Mapping)
        or support.get("cell_interior_nonzero_values") != 0
        or summary.get("b0_saved_surface_support_certificate") != support
        or manifest.get("local_interior_Bi_Di_exact_zero") is not True
        or manifest.get("local_interior_Bi_Di_nonzero_entry_count") != 0
        or manifest.get("saved_surface_support_certificate_passed") is not True
        or manifest.get("saved_surface_support_certificate_sha256") != support_digest
    ):
        raise ValueError("Task41 V4 donor lacks the exact-zero Bi/Di support certificate")
    return {
        "manifest": manifest,
        "manifest_sha256": manifest_sha256,
        "existing_evidence_bytes": sum(evidence_records.values()),
        "columns": columns,
        "raw_classes": list(raw_by_key.values()),
        "cell_maps": cell_maps,
        "attribution": {
            "joint": {
                name: load(joint_artifacts.get(name), f"joint {name}")
                for name in ("p6_result", "reduced_rhs", "port_rhs")
            },
            "local_class_identities": [],
        },
    }


def _task41_v11_load_selected_donor_vectors(
    *,
    summary_path: Path,
    donor_contract: Mapping[str, Any],
    donor_contract_sha256: str,
    repo_root: Path,
) -> dict[str, Any]:
    """Open only hash-bound donor vectors needed for the two-cell saved replay."""
    from src.solvers.task41_v4_volume_only_audit import (
        TASK41_V4_DONOR_MANIFEST_SHA256,
        TASK41_V4_FULL_STORAGE_ROWS,
    )
    from src.runners.task41_p0_v4_volume_only_audit import TASK41_P0_V11_GLOBAL_ROW_COUNT

    summary_path = Path(summary_path).resolve(strict=True)
    repo_root = Path(repo_root).resolve(strict=True)
    run_root = summary_path.parent.resolve(strict=True)
    results_root = (repo_root / "results").resolve()
    case = donor_contract.get("case")
    if (
        not summary_path.is_relative_to(results_root)
        or summary_path.name != "task40_v10_p6_candidate_summary.json"
        or not isinstance(case, Mapping)
        or task41_case_id_for_run_id(str(case.get("run_id", ""))) != "B0"
    ):
        raise ValueError("V11 selected-vector donor summary or contract is outside frozen B0")
    summary = _json_object(summary_path, "V11 saved donor candidate summary")
    binding = summary.get("b0_recovery_evidence")
    manifest_ref = binding.get("manifest") if isinstance(binding, Mapping) else None
    if not isinstance(manifest_ref, Mapping):
        raise ValueError("V11 donor summary omits its saved recovery manifest")
    manifest_path = _task41_run_artifact(run_root, manifest_ref, "V11 donor recovery manifest")
    manifest_sha = sha256_file(manifest_path)
    if manifest_sha != TASK41_V4_DONOR_MANIFEST_SHA256:
        raise ValueError("V11 donor recovery manifest differs from its frozen identity")
    manifest = _json_object(manifest_path, "V11 saved donor manifest")
    run_manifest_path = run_root / "run_manifest.json"
    run_manifest = _json_object(run_manifest_path, "V11 saved donor run manifest")
    expected_identity = {
        "run_id": case.get("run_id"),
        "model_id": case.get("model_id"),
        "method": case.get("method"),
        "mpi_size": case.get("mpi_size"),
        "input_sha256": case.get("input_sha256"),
        "physical_model_sha256": case.get("physical_model_sha256"),
        "resolved_config_sha256": case.get("resolved_config_sha256"),
        "source_sha": donor_contract.get("source", {}).get("sha")
        if isinstance(donor_contract.get("source"), Mapping)
        else None,
    }
    if (
        summary.get("run_id") != case.get("run_id")
        or manifest.get("run_id") != case.get("run_id")
        or any(run_manifest.get(key) != value for key, value in expected_identity.items())
        or Path(str(run_manifest.get("output_directory", ""))).resolve() != run_root
        or manifest.get("contract_sha256") != donor_contract_sha256
        or manifest.get("source_sha") != expected_identity["source_sha"]
        or manifest.get("full_storage_rows") != TASK41_V4_FULL_STORAGE_ROWS
        or not isinstance(manifest.get("columns"), list)
        or len(manifest["columns"]) != 2
    ):
        raise ValueError("V11 donor manifest, run summary, or frozen contract identity differs")

    artifact_cache: dict[tuple[str, str], np.ndarray] = {}

    def load_record(record: Any, label: str) -> np.ndarray:
        if not isinstance(record, Mapping):
            raise ValueError(f"V11 donor omits {label} artifact identity")
        raw_path = Path(str(record.get("path", "")))
        path = (raw_path if raw_path.is_absolute() else run_root / raw_path).resolve(strict=True)
        digest = record.get("sha256")
        if not path.is_relative_to(run_root) or not isinstance(digest, str):
            raise ValueError(f"V11 donor {label} path is outside its saved run")
        key = (str(path), digest)
        if key not in artifact_cache:
            artifact_cache[key] = _task41_npy_artifact(run_root, record, label)
        return artifact_cache[key]

    columns: list[dict[str, Any]] = []
    full_rows = int(manifest["full_storage_rows"])
    for column_index, column_meta in enumerate(manifest["columns"]):
        artifacts = column_meta.get("artifacts")
        if not isinstance(artifacts, Mapping):
            raise ValueError(f"V11 donor column {column_index} artifact map is malformed")
        loaded = {
            name: load_record(artifacts.get(name), f"column {column_index} {name}")
            for name in (
                "active_original_rows",
                "known_field",
                "native_rhs",
                "native_volume_rhs",
                "b_alpha_rows",
                "b_alpha_values",
            )
        }
        active = np.asarray(loaded["active_original_rows"])
        if (
            active.ndim != 1
            or active.dtype.kind not in "iu"
            or active.size != TASK41_P0_V11_GLOBAL_ROW_COUNT
            or any(np.asarray(loaded[name]).shape != (full_rows,) for name in ("known_field", "native_rhs", "native_volume_rhs"))
            or any(np.asarray(loaded[name]).dtype != np.dtype(np.complex128) for name in ("known_field", "native_rhs", "native_volume_rhs", "b_alpha_values"))
            or loaded["b_alpha_rows"].ndim != 1
            or loaded["b_alpha_rows"].dtype.kind not in "iu"
            or loaded["b_alpha_values"].shape != loaded["b_alpha_rows"].shape
            or (loaded["b_alpha_rows"].size > 1 and np.any(loaded["b_alpha_rows"][1:] <= loaded["b_alpha_rows"][:-1]))
        ):
            raise ValueError(f"V11 donor column {column_index} selected source vectors have invalid layout")
        input_identity = manifest.get("input_identities", [])[column_index]
        alpha_pair = input_identity.get("port_alpha") if isinstance(input_identity, Mapping) else None
        if not isinstance(alpha_pair, list) or len(alpha_pair) != 2:
            raise ValueError(f"V11 donor column {column_index} omits port alpha")
        alpha = complex(float(alpha_pair[0]), float(alpha_pair[1]))
        if not np.isfinite([alpha.real, alpha.imag]).all():
            raise ValueError(f"V11 donor column {column_index} port alpha is non-finite")

        state_records = [
            (
                "j0",
                artifacts.get("recovered_storage"),
                artifacts.get("native_volume_action_recovered"),
            )
        ]
        refinement = column_meta.get("same_lu_refinement")
        if not isinstance(refinement, list) or len(refinement) != 3:
            raise ValueError(f"V11 donor column {column_index} lacks its three-step j3 history")
        final_step = refinement[-1]
        final_artifacts = final_step.get("artifacts") if isinstance(final_step, Mapping) else None
        if not isinstance(final_artifacts, Mapping) or final_step.get("step") != 3:
            raise ValueError(f"V11 donor column {column_index} final saved state is not j3")
        state_records.append(("j3", final_artifacts.get("storage"), final_artifacts.get("native_volume_action")))
        states = [
            {
                "label": label,
                "storage": load_record(storage_ref, f"column {column_index} {label} storage"),
                "native_volume_action": load_record(action_ref, f"column {column_index} {label} native action"),
            }
            for label, storage_ref, action_ref in state_records
        ]
        for state in states:
            if any(np.asarray(state[name]).shape != (full_rows,) or np.asarray(state[name]).dtype != np.dtype(np.complex128) for name in ("storage", "native_volume_action")):
                raise ValueError(f"V11 donor column {column_index} {state['label']} vectors have invalid layout")
        columns.append({**loaded, "port_alpha": alpha, "states": states})
    if not np.array_equal(columns[0]["active_original_rows"], columns[1]["active_original_rows"]):
        raise ValueError("V11 donor columns disagree on active-to-original row mapping")
    return {
        "manifest": manifest,
        "manifest_sha256": manifest_sha,
        "columns": columns,
        "summary_path": summary_path,
        "summary_sha256": sha256_file(summary_path),
        "run_root": run_root,
    }


def _task41_p0_v12_integral_profile_matches_frozen_evaluator(
    integration_identity: Mapping[str, Any],
) -> bool:
    """Independently require the full material-tag/kernel profile frozen by V6."""
    from src.solvers.task41_actual_qmetric_blocked_gram import PROFILE_TAGS

    expected_tags = sorted(int(tag) for tag in PROFILE_TAGS)
    expected_counts = {str(tag): 1 for tag in expected_tags}
    for key in ("frozen_evaluator_profile_tags", "cell_integral_ids"):
        values = integration_identity.get(key)
        if (
            not isinstance(values, list)
            or any(type(value) is not int for value in values)
            or values != expected_tags
        ):
            return False
    counts = integration_identity.get("integral_kernel_counts")
    return (
        isinstance(counts, Mapping)
        and set(counts) == set(expected_counts)
        and all(type(counts[key]) is int and counts[key] == 1 for key in expected_counts)
    )


def check_task41_p0_v11_candidate_replay_saved_arrays(
    *,
    summary_path: Path,
    donor_contract_path: Path,
    donor_contract_sha256: str,
    consumer_contract_path: Path,
    consumer_contract_sha256: str,
    candidate_report_path: Path,
    candidate_report_sha256: str,
    output_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    """Read-only independent recheck of V11's saved two-cell arrays and row terms."""
    from src.runners.task41_p0_contract import (
        TASK41_B0_V12_CANDIDATE_REPLAY_SCOPE,
        load_task41_p0_fixed_window,
    )
    from src.runners.task41_p0_v4_volume_only_audit import (
        TASK41_P0_V11_FFCX_C_SOURCE_SHA256,
        TASK41_P0_V11_METADATA_ACTIVE_ROW,
        TASK41_P0_V11_GLOBAL_ROW_COUNT,
        TASK41_P0_V11_METADATA_CONSUMER_CONTRACT_RELATIVE,
        TASK41_P0_V11_METADATA_CONSUMER_CONTRACT_SHA256,
        TASK41_P0_V11_METADATA_CONSUMER_SOURCE_SHA,
        TASK41_P0_V11_METADATA_REPORT_SHA256,
        TASK41_P0_V11_METADATA_SERVICE_RECEIPT_SHA256,
        TASK41_P0_V11_METADATA_WINDOW_SHA256,
        TASK41_P0_V11_V9_COMPACT_REPORT_SHA256,
        TASK41_P0_V11_V9_FULL_ACTION_ARRAY_SHA256,
        TASK41_P0_V11_V9_REDUCED_RHS_ARRAY_SHA256,
    )
    from src.solvers.task41_v4_volume_only_audit import TASK41_V4_DONOR_MANIFEST_SHA256

    repo_root = Path(repo_root).resolve(strict=True)
    results_root = (repo_root / "results").resolve()
    donor_contract, donor_digest = require_task41_p0_contract(
        donor_contract_path,
        expected_sha256=donor_contract_sha256,
        current_root=repo_root,
        check_current_source=False,
        require_clean_source=False,
        case_id="B0",
    )
    consumer_contract, consumer_digest = require_task41_p0_contract(
        consumer_contract_path,
        expected_sha256=consumer_contract_sha256,
        current_root=repo_root,
        check_current_source=True,
        require_clean_source=True,
        case_id="B0",
    )
    donor_case = donor_contract.get("case")
    consumer_case = consumer_contract.get("case")
    if (
        not isinstance(donor_case, Mapping)
        or not isinstance(consumer_case, Mapping)
        or consumer_contract.get("execution_scope") != TASK41_B0_V12_CANDIDATE_REPLAY_SCOPE
        or consumer_contract.get("numerical_strategy", {}).get("internal_rhs_strategy") != "same_lu_rhs_solve"
        or any(
            donor_case.get(field) != consumer_case.get(field)
            for field in ("model_id", "method", "mpi_size", "input_sha256", "physical_model_sha256", "resolved_config_sha256")
        )
    ):
        raise ValueError("V11 saved-array checker requires the frozen donor and V12 consumer identities")
    fixed_window = load_task41_p0_fixed_window(
        consumer_contract, current_root=repo_root, require_current_boot=False
    )
    summary_path = Path(summary_path).resolve(strict=True)
    candidate_report_path = Path(candidate_report_path).resolve(strict=True)
    output_path = Path(output_path).resolve()
    if (
        not summary_path.is_relative_to(results_root)
        or not candidate_report_path.is_relative_to(results_root)
        or output_path.exists()
        or not output_path.is_relative_to(results_root)
        or output_path.is_relative_to(summary_path.parent)
        or not re.fullmatch(r"[0-9a-f]{64}", str(candidate_report_sha256))
        or sha256_file(candidate_report_path) != candidate_report_sha256
        or candidate_report_path.stat().st_size > 64 * 1024**2
    ):
        raise ValueError("V11 candidate report/output path or report SHA-256 is invalid")
    report_envelope = _json_object(
        candidate_report_path, "V11 selected candidate replay receipt envelope"
    )
    replay = report_envelope.get("v11_selected_trace_candidate_replay")
    expected_attempt_root = candidate_report_path.parent.resolve(strict=True)
    expected_volume_root = (
        expected_attempt_root / "selected_trace_star_candidate_replay"
    ).resolve(strict=True)
    if (
        candidate_report_path.name != "task41_p0_v11_selected_trace_candidate_replay.json"
        or report_envelope.get("schema")
        != "task41.p0.v11.selected_trace_star_candidate_replay_receipt.v1"
        or report_envelope.get("status") != "COMPLETED_LOCAL_CANDIDATE_REPLAY"
        or Path(str(report_envelope.get("consumer_contract_path", ""))).resolve()
        != Path(consumer_contract_path).resolve(strict=True)
        or report_envelope.get("consumer_contract_sha256") != consumer_digest
        or report_envelope.get("consumer_source_sha")
        != consumer_contract.get("source", {}).get("sha")
        or Path(str(report_envelope.get("donor_contract_path", ""))).resolve()
        != Path(donor_contract_path).resolve(strict=True)
        or report_envelope.get("donor_contract_sha256") != donor_digest
        or report_envelope.get("donor_source_sha")
        != donor_contract.get("source", {}).get("sha")
        or Path(str(report_envelope.get("consumer_window_path", ""))).resolve()
        != Path(fixed_window.path).resolve()
        or report_envelope.get("consumer_window_sha256") != fixed_window.sha256
        or report_envelope.get("donor_manifest_sha256")
        != TASK41_V4_DONOR_MANIFEST_SHA256
        or Path(str(report_envelope.get("output_directory", ""))).resolve()
        != expected_attempt_root
        or Path(str(report_envelope.get("volume_evidence_directory", ""))).resolve()
        != expected_volume_root
        or not isinstance(replay, Mapping)
        or replay.get("schema")
        != "task41.p0.v11.selected_trace_star_candidate_replay.v1"
        or replay.get("status") != "COMPLETED_LOCAL_CANDIDATE_REPLAY"
        or replay.get("consumer_contract_sha256") != consumer_digest
        or replay.get("consumer_source_sha")
        != consumer_contract.get("source", {}).get("sha")
        or Path(str(replay.get("consumer_window_path", ""))).resolve()
        != Path(fixed_window.path).resolve()
        or replay.get("consumer_window_sha256") != fixed_window.sha256
        or replay.get("donor_manifest_sha256")
        != TASK41_V4_DONOR_MANIFEST_SHA256
        or replay.get("metadata_report_sha256")
        != TASK41_P0_V11_METADATA_REPORT_SHA256
        or report_envelope.get("selected_metadata_report_path")
        != replay.get("metadata_report_path")
        or report_envelope.get("selected_metadata_report_sha256")
        != replay.get("metadata_report_sha256")
        or replay.get("v9_compact_report_sha256")
        != TASK41_P0_V11_V9_COMPACT_REPORT_SHA256
        or report_envelope.get("v9_compact_report_path")
        != replay.get("v9_compact_report_path")
        or report_envelope.get("v9_compact_report_sha256")
        != replay.get("v9_compact_report_sha256")
        or replay.get("ffcx_c_source_sha256") != TASK41_P0_V11_FFCX_C_SOURCE_SHA256
        or replay.get("classification") not in ("LOCAL_REPLAY_COMPLETED", "LOCAL_REPLAY_UNBOUND")
    ):
        raise ValueError("V11 candidate replay receipt is not bound to the donor and current consumer")
    report = replay

    metadata_path = Path(str(report.get("metadata_report_path", ""))).resolve(strict=True)
    if (
        not metadata_path.is_relative_to(results_root)
        or metadata_path.name != "task41_p0_v8_selected_trace_star_metadata.json"
        or sha256_file(metadata_path) != TASK41_P0_V11_METADATA_REPORT_SHA256
    ):
        raise ValueError("V11 metadata path or SHA-256 differs from the frozen completed metadata run")
    metadata_report = _json_object(metadata_path, "V11 completed metadata-only report")
    old_contract_path = Path(str(metadata_report.get("consumer_contract_path", ""))).resolve(strict=True)
    expected_old_contract_path = (repo_root / TASK41_P0_V11_METADATA_CONSUMER_CONTRACT_RELATIVE).resolve(strict=True)
    old_contract, old_contract_digest = require_task41_p0_contract(
        old_contract_path,
        expected_sha256=TASK41_P0_V11_METADATA_CONSUMER_CONTRACT_SHA256,
        current_root=repo_root,
        check_current_source=False,
        require_clean_source=False,
        case_id="B0",
    )
    old_window = load_task41_p0_fixed_window(old_contract, current_root=repo_root, require_current_boot=False)
    metadata_window_state = metadata_report.get("initial_fixed_window_state")
    if (
        old_contract_path != expected_old_contract_path
        or old_contract_digest != TASK41_P0_V11_METADATA_CONSUMER_CONTRACT_SHA256
        or old_contract.get("source", {}).get("sha") != TASK41_P0_V11_METADATA_CONSUMER_SOURCE_SHA
        or old_window.sha256 != TASK41_P0_V11_METADATA_WINDOW_SHA256
        or not isinstance(metadata_window_state, Mapping)
        or metadata_window_state.get("campaign_window_sha256") != old_window.sha256
        or metadata_report.get("schema") != "task41.p0.v8.selected_trace_star_metadata_only_receipt.v1"
        or metadata_report.get("status") != "COMPLETED_METADATA_ONLY"
        or metadata_report.get("consumer_source_sha") != TASK41_P0_V11_METADATA_CONSUMER_SOURCE_SHA
        or metadata_report.get("consumer_contract_sha256") != old_contract_digest
        or old_window.sha256 == fixed_window.sha256
    ):
        raise ValueError("V11 metadata source window is not distinct from the new consumer window")
    metadata = metadata_report.get("selected_trace_star_metadata_only")
    receipt_path = Path(str(report.get("metadata_service_receipt_path", ""))).resolve(strict=True)
    if (
        not isinstance(metadata, Mapping)
        or metadata.get("status") != "COMPLETED_METADATA_ONLY"
        or metadata.get("numerical_work_started") is not False
        or receipt_path
        != metadata_path.parent.with_name(metadata_path.parent.name + ".service")
        / "task41_p0_service_receipt.json"
        or report.get("metadata_service_receipt_sha256")
        != TASK41_P0_V11_METADATA_SERVICE_RECEIPT_SHA256
        or sha256_file(receipt_path) != TASK41_P0_V11_METADATA_SERVICE_RECEIPT_SHA256
        or report.get("metadata_consumer_contract_sha256")
        != TASK41_P0_V11_METADATA_CONSUMER_CONTRACT_SHA256
    ):
        raise ValueError("V11 metadata-only source or completed service receipt differs")

    v9_path = Path(str(report.get("v9_compact_report_path", ""))).resolve(strict=True)
    if (
        v9_path.name != "task41_p0_b0_v9_compact_volume_audit.json"
        or not v9_path.is_relative_to(results_root)
        or sha256_file(v9_path) != TASK41_P0_V11_V9_COMPACT_REPORT_SHA256
        or v9_path.stat().st_size > 8 * 1024**2
    ):
        raise ValueError("V11 checker V9 compact report path or hash differs")
    v9_report = _json_object(v9_path, "V11 frozen V9 compact report")
    action_gate = v9_report.get("candidate_full_action_gate")
    if (
        v9_report.get("schema") != "task41.p0.b0.v9.compact_volume_identity.v1"
        or v9_report.get("status") != "GATE_FAILED"
        or v9_report.get("official_result") is not False
        or v9_report.get("internal_rhs_strategy") != "same_lu_rhs_solve"
        or v9_report.get("donor_manifest_sha256") != report.get("donor_manifest_sha256")
        or not isinstance(action_gate, Mapping)
        or action_gate.get("status") != "GATE_FAILED"
        or report.get("candidate_evaluator_identity") != v9_report.get("candidate_evaluator_identity")
        or report.get("candidate_cache_identity") != v9_report.get("candidate_evaluator_cache_identity")
        or report.get("v9_compact_evaluator_identity") != v9_report.get("candidate_evaluator_identity")
        or report.get("v9_compact_cache_identity") != v9_report.get("candidate_evaluator_cache_identity")
    ):
        raise ValueError("V11 candidate evaluator/cache identity differs from the V9 compact source")
    integration_identity = report.get("integration_identity")
    if (
        not isinstance(integration_identity, Mapping)
        or integration_identity.get("schema") != "task41.p0.v12.same_mesh_p6_curl_plus_mass.v1"
        or integration_identity.get("degree") != 6
        or integration_identity.get("form_terms") != ["curl", "mass"]
        or not _task41_p0_v12_integral_profile_matches_frozen_evaluator(integration_identity)
        or integration_identity.get("sum_duplicate_cell_integrals") is not True
        or integration_identity.get("internal_rhs_strategy") != "same_lu_rhs_solve"
        or integration_identity.get("candidate_evaluator_identity") != v9_report.get("candidate_evaluator_identity")
        or integration_identity.get("candidate_cache_identity") != v9_report.get("candidate_evaluator_cache_identity")
    ):
        raise ValueError("V11 prepared evaluator/integration identity is not bound to V9")

    donor = _task41_v11_load_selected_donor_vectors(
        summary_path=summary_path,
        donor_contract=donor_contract,
        donor_contract_sha256=donor_digest,
        repo_root=repo_root,
    )
    if donor["manifest_sha256"] != report.get("donor_manifest_sha256"):
        raise ValueError("V11 selected vector inputs differ from the report donor manifest")

    def load_report_array(record: Any, label: str) -> np.ndarray:
        if not isinstance(record, Mapping) or not isinstance(record.get("path"), str):
            raise ValueError(f"V11 saved {label} artifact is missing its path")
        path = Path(str(record["path"])).resolve(strict=True)
        if (
            not path.is_relative_to(results_root)
            or path.stat().st_size != record.get("bytes")
            or not isinstance(record.get("sha256"), str)
            or sha256_file(path) != record.get("sha256")
        ):
            raise ValueError(f"V11 saved {label} artifact path/hash/size differs")
        value = np.load(path, mmap_mode="r", allow_pickle=False)
        if list(value.shape) != record.get("shape") or str(value.dtype) != record.get("dtype"):
            raise ValueError(f"V11 saved {label} artifact shape/dtype differs")
        return value

    def load_candidate_or_metadata_array(record: Any, label: str) -> np.ndarray:
        path = Path(str(record.get("path", ""))).resolve(strict=True) if isinstance(record, Mapping) else Path()
        allowed_root = metadata_path.parent if " metadata " in f" {label} " else candidate_report_path.parent
        if not path.is_relative_to(allowed_root.resolve(strict=True)):
            raise ValueError(f"V11 {label} artifact escaped its producer directory")
        return load_report_array(record, label)

    def load_v9_row(field: str, digest: str) -> np.ndarray:
        record = action_gate.get(field)
        if not isinstance(record, Mapping):
            raise ValueError(f"V11 V9 compact report omits {field}")
        raw_path = Path(str(record.get("path", "")))
        path = (raw_path if raw_path.is_absolute() else v9_path.parent / raw_path).resolve(strict=True)
        if (
            not path.is_relative_to(v9_path.parent.resolve(strict=True))
            or path.stat().st_size != record.get("bytes")
            or record.get("sha256") != digest
            or sha256_file(path) != digest
            or record.get("shape") != [TASK41_P0_V11_GLOBAL_ROW_COUNT, 2]
            or record.get("dtype") != "complex128"
        ):
            raise ValueError(f"V11 V9 compact {field} vector identity differs")
        array = np.load(path, mmap_mode="r", allow_pickle=False)
        if array.shape != (TASK41_P0_V11_GLOBAL_ROW_COUNT, 2) or array.dtype != np.dtype(np.complex128):
            raise ValueError(f"V11 V9 compact {field} vector shape/dtype differs")
        return np.asarray(array[TASK41_P0_V11_METADATA_ACTIVE_ROW, :]).copy()

    v9_y_row = load_v9_row("full_action_artifact", TASK41_P0_V11_V9_FULL_ACTION_ARRAY_SHA256)
    v9_g_row = load_v9_row("full_reduced_rhs_artifact", TASK41_P0_V11_V9_REDUCED_RHS_ARRAY_SHA256)
    numeric = _task41_v11_recompute_saved_candidate_arrays(
        report,
        metadata,
        donor,
        v9_y_row=v9_y_row,
        v9_g_row=v9_g_row,
        load_array=load_candidate_or_metadata_array,
    )
    payload = {
        **numeric,
        "checked_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "candidate_report_path": str(candidate_report_path),
        "candidate_report_sha256": candidate_report_sha256,
        "consumer_contract_sha256": consumer_digest,
        "consumer_window_sha256": fixed_window.sha256,
        "donor_contract_sha256": donor_digest,
        "donor_manifest_sha256": donor["manifest_sha256"],
        "donor_summary_sha256": donor["summary_sha256"],
        "metadata_report_sha256": TASK41_P0_V11_METADATA_REPORT_SHA256,
        "v9_compact_report_sha256": TASK41_P0_V11_V9_COMPACT_REPORT_SHA256,
        "raw_evidence_retained": True,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    if output_path.exists() or temporary.exists():
        raise ValueError("V11 independent checker output must be new")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    try:
        os.link(temporary, output_path)
    except FileExistsError as exc:
        raise ValueError("V11 independent checker output appeared concurrently") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return payload


def check_task41_b0_v9_compact_volume_audit(
    report: Mapping[str, Any],
    donor: Mapping[str, Any],
    *,
    output_directory: str | Path,
    native_volume_apply: Any | None,
    native_action_receipt: Mapping[str, Any] | None = None,
    expected_candidate_identity: str | None = None,
    expected_cache_identity: str | None = None,
) -> dict[str, Any]:
    """Reopen compact V9 artifacts and recompute gates, replaying native action only when live."""

    from src.solvers.task41_v4_volume_only_audit import (
        TASK41_V4_ACTIVE_TRACE_ROWS,
        TASK41_V4_APPENDED_ROWS,
        TASK41_V4_FULL_STORAGE_ROWS,
        TASK41_V5_FROZEN_DENOMINATORS,
        TASK41_V5_FULL_ACTION_RELATIVE_TOLERANCE,
    )

    root = Path(output_directory).resolve(strict=True)
    columns = tuple(donor.get("columns", ()))
    joint = donor.get("attribution", {}).get("joint", {})
    saved_p6 = np.asarray(joint.get("p6_result"))
    saved_reduced = np.asarray(joint.get("reduced_rhs"))
    saved_port_rhs = np.asarray(joint.get("port_rhs"))
    errors: list[str] = []
    action_receipts: list[dict[str, Any]] = []
    native_action_calls = 0
    reused_action_receipts = 0

    def array_sha256(values: np.ndarray) -> str:
        array = np.asarray(values)
        if not array.flags.c_contiguous:
            array = np.ascontiguousarray(array)
        return hashlib.sha256(memoryview(array).cast("B")).hexdigest()

    def bound_array(binding: Mapping[str, Any]) -> np.ndarray:
        raw = Path(str(binding.get("path", "")))
        path = (raw if raw.is_absolute() else root / raw).resolve(strict=True)
        if (
            not path.is_relative_to(root)
            or type(binding.get("bytes")) is not int
            or path.stat().st_size != binding["bytes"]
            or sha256_file(path) != binding.get("sha256")
        ):
            raise ValueError("V9 compact array path, byte count, or file SHA-256 differs")
        array = np.load(path, mmap_mode="r", allow_pickle=False)
        if (
            list(array.shape) != binding.get("shape")
            or str(array.dtype) != binding.get("dtype")
            or array.dtype != np.dtype(np.complex128)
        ):
            raise ValueError("V9 compact array shape or dtype differs from its binding")
        return array

    def referenced_array(binding: Mapping[str, Any], label: str) -> np.ndarray:
        kind = binding.get("kind")
        if kind == "artifact":
            return bound_array(binding)
        column_index = binding.get("column")
        if type(column_index) is not int or not 0 <= column_index < len(columns):
            raise ValueError(f"V9 {label} donor column reference is malformed")
        if kind == "v4_donor_known_field":
            return np.asarray(columns[column_index]["known_field"])
        if kind == "v4_donor_initial_native_volume_residual":
            return np.asarray(columns[column_index]["states"][0]["native_volume_residual"])
        raise ValueError(f"V9 {label} artifact reference kind is unknown")

    def squared_norm(values: np.ndarray) -> float:
        total = 0.0
        for start in range(0, values.size, 262_144):
            chunk = np.asarray(values[start : start + 262_144], dtype=np.complex128)
            total += float(np.vdot(chunk, chunk).real)
        return total

    def squared_difference(left: np.ndarray, right: np.ndarray) -> float:
        if left.shape != right.shape:
            raise ValueError("V9 independent comparison array shapes differ")
        total = 0.0
        for start in range(0, left.size, 262_144):
            stop = min(left.size, start + 262_144)
            delta = np.asarray(left[start:stop], dtype=np.complex128) - np.asarray(
                right[start:stop], dtype=np.complex128
            )
            total += float(np.vdot(delta, delta).real)
        return total

    def finite(values: np.ndarray) -> bool:
        return all(
            bool(np.isfinite(np.asarray(values[start : start + 262_144])).all())
            for start in range(0, values.size, 262_144)
        )

    checks: dict[str, bool] = {
        "compact_schema_and_strategy": bool(
            report.get("schema") == "task41.p0.b0.v9.compact_volume_identity.v1"
            and report.get("internal_rhs_strategy") == "same_lu_rhs_solve"
            and report.get("geometry_policy") == "mesh_actual_exact"
            and report.get("official_result") is False
            and isinstance(report.get("candidate_evaluator_identity"), str)
            and report.get("candidate_evaluator_identity")
            and (
                expected_candidate_identity is None
                or report.get("candidate_evaluator_identity") == expected_candidate_identity
            )
            and isinstance(report.get("candidate_evaluator_cache_identity"), str)
            and report.get("candidate_evaluator_cache_identity")
            and (
                expected_cache_identity is None
                or report.get("candidate_evaluator_cache_identity") == expected_cache_identity
            )
            and report.get("donor_manifest_sha256") == donor.get("manifest_sha256")
            and report.get("existing_evidence_bytes") == donor.get("existing_evidence_bytes")
            and type(report.get("prior_new_evidence_bytes")) is int
        ),
        "frozen_layout": bool(
            len(columns) == 2
            and report.get("active_rows") == TASK41_V4_ACTIVE_TRACE_ROWS
            and report.get("appended_rows") == TASK41_V4_APPENDED_ROWS
            and report.get("full_storage_rows") == TASK41_V4_FULL_STORAGE_ROWS
            and saved_p6.shape == (TASK41_V4_ACTIVE_TRACE_ROWS + TASK41_V4_APPENDED_ROWS, 2)
            and saved_reduced.shape == saved_p6.shape
            and saved_port_rhs.shape == (TASK41_V4_APPENDED_ROWS, 2)
        ),
    }
    try:
        if not all(checks.values()):
            raise ValueError("V9 compact report schema or frozen donor layout differs")
        if not callable(native_volume_apply):
            if not isinstance(native_action_receipt, Mapping):
                raise ValueError("saved-only V9 replay requires the hash-bound live native-action receipt")
            if (
                native_action_receipt.get("schema")
                != "task41.p0.b0.v9.compact_volume_independent_check.v1"
                or native_action_receipt.get("official_result") is not False
                or not isinstance(native_action_receipt.get("errors"), list)
                or native_action_receipt.get("errors")
            ):
                raise ValueError("saved-only V9 native-action receipt has invalid identity or errors")
            receipt_rows = native_action_receipt.get("native_volume_action_receipts")
            if not isinstance(receipt_rows, list):
                raise ValueError("saved-only V9 native-action receipt omits per-column identities")
            action_receipts = [dict(item) for item in receipt_rows if isinstance(item, Mapping)]
            if len(action_receipts) != len(receipt_rows):
                raise ValueError("saved-only V9 native-action receipt has malformed column rows")
        else:
            action_receipts = []
        gate = report.get("candidate_full_action_gate")
        if not isinstance(gate, Mapping):
            raise ValueError("V9 compact report omits its full-action gate")
        full_p6 = bound_array(gate["full_action_artifact"])
        full_reduced = bound_array(gate["full_reduced_rhs_artifact"])
        checks["action_artifacts_finite"] = finite(full_p6) and finite(full_reduced)
        checks["saved_port_rows_unchanged"] = bool(
            np.array_equal(full_p6[TASK41_V4_ACTIVE_TRACE_ROWS :], saved_p6[TASK41_V4_ACTIVE_TRACE_ROWS :])
            and np.array_equal(
                full_reduced[TASK41_V4_ACTIVE_TRACE_ROWS :],
                saved_reduced[TASK41_V4_ACTIVE_TRACE_ROWS :],
            )
            and np.array_equal(full_p6[TASK41_V4_ACTIVE_TRACE_ROWS :], saved_port_rhs)
            and np.array_equal(full_reduced[TASK41_V4_ACTIVE_TRACE_ROWS :], saved_port_rhs)
        )
        action_columns = []
        reported_action_columns = gate.get("columns")
        reported_action_columns_match = isinstance(reported_action_columns, list) and len(
            reported_action_columns
        ) == 2
        for column_index, frozen_denominator in enumerate(TASK41_V5_FROZEN_DENOMINATORS):
            delta_squared = squared_difference(full_p6[:, column_index], full_reduced[:, column_index])
            difference = float(np.sqrt(max(0.0, delta_squared)))
            dynamic_denom = max(
                float(np.sqrt(max(0.0, squared_norm(full_p6[:, column_index])))),
                float(np.sqrt(max(0.0, squared_norm(full_reduced[:, column_index])))),
                np.finfo(float).tiny,
            )
            dynamic_relative = difference / dynamic_denom
            frozen_relative = difference / frozen_denominator
            dynamic_passed = dynamic_relative <= TASK41_V5_FULL_ACTION_RELATIVE_TOLERANCE
            frozen_passed = frozen_relative <= TASK41_V5_FULL_ACTION_RELATIVE_TOLERANCE
            action_columns.append(bool(dynamic_passed and frozen_passed))
            if not isinstance(reported_action_columns, list) or len(reported_action_columns) != 2:
                continue
            reported = reported_action_columns[column_index]
            try:
                reported_difference = reported["difference"]
                reported_action_columns_match = bool(
                    reported_action_columns_match
                    and isinstance(reported, Mapping)
                    and reported.get("column") == column_index
                    and type(reported.get("frozen_denominator")) in {int, float}
                    and float(reported["frozen_denominator"]) == float(frozen_denominator)
                    and type(reported.get("dynamic_gate_passed")) is bool
                    and reported.get("dynamic_gate_passed") is bool(dynamic_passed)
                    and type(reported.get("frozen_gate_passed")) is bool
                    and reported.get("frozen_gate_passed") is bool(frozen_passed)
                    and abs(float(reported.get("dynamic_denominator_relative")) - dynamic_relative)
                    <= 5.0e-13 * max(1.0, abs(dynamic_relative))
                    and abs(float(reported.get("frozen_denominator_relative")) - frozen_relative)
                    <= 5.0e-13 * max(1.0, abs(frozen_relative))
                    and isinstance(reported_difference, Mapping)
                    and abs(float(reported_difference.get("absolute_l2")) - difference)
                    <= 5.0e-13 * max(1.0, abs(difference))
                )
            except (KeyError, TypeError, ValueError):
                reported_action_columns_match = False
        checks["reported_action_columns_match_recalculation"] = reported_action_columns_match
        checks["reported_frozen_denominators_match_contract"] = bool(
            reported_action_columns_match
            and isinstance(reported_action_columns, list)
            and all(
                type(item.get("frozen_denominator")) in {int, float}
                and float(item["frozen_denominator"]) == float(expected)
                for item, expected in zip(
                    reported_action_columns, TASK41_V5_FROZEN_DENOMINATORS, strict=True
                )
                if isinstance(item, Mapping)
            )
        )
        checks["both_dynamic_and_frozen_action_gates"] = all(action_columns)

        recovery_gate = report.get("candidate_recovery_gate")
        if not isinstance(recovery_gate, Mapping):
            raise ValueError("V9 compact report omits its recovery gate")
        recovery_columns = recovery_gate.get("columns")
        independent_action_gate_passed = bool(
            all(action_columns) and checks["saved_port_rows_unchanged"]
        )
        checks["reported_action_gate_matches_recalculation"] = gate.get("status") == (
            "PASS" if independent_action_gate_passed else "GATE_FAILED"
        )
        if not independent_action_gate_passed:
            checks["recovery_not_run_after_action_gate_failure"] = bool(
                recovery_gate.get("status") == "NOT_RUN_ACTION_GATE_FAILED"
                and recovery_columns == []
                and recovery_gate.get("native_volume_action_calls") == 0
            )
            checks["both_candidate_recovery_gates"] = False
            checks["independent_native_volume_action_call_count"] = native_action_calls == 0
            checks["native_action_receipt_branch_matches"] = bool(
                not callable(native_volume_apply)
                and native_action_receipt is not None
                and native_action_receipt.get("native_volume_action_receipts") == []
                and native_action_receipt.get("independent_native_volume_action_calls") == 0
            ) if not callable(native_volume_apply) else True
            if not checks["recovery_not_run_after_action_gate_failure"]:
                raise ValueError(
                    "V9 recovery was run or malformed after the independently recomputed action gate failed"
                )
        else:
            if not isinstance(recovery_columns, list) or len(recovery_columns) != 2:
                raise ValueError("V9 compact report omits its two recovery columns")
            if recovery_gate.get("status") not in {"PASS", "GATE_FAILED"}:
                raise ValueError("V9 recovery gate has an invalid completed status")
            recovery_passes = []
            producer_native_action_calls = 0
            for column_index, item in enumerate(recovery_columns):
                if not isinstance(item, Mapping) or item.get("column") != column_index:
                    raise ValueError("V9 compact recovery column order differs")
                steps = item.get("step_records")
                corrections = item.get("same_lu_corrections")
                if (
                    not isinstance(steps, list)
                    or not steps
                    or len(steps) > 4
                    or type(corrections) is not int
                    or corrections != len(steps) - 1
                    or corrections > 3
                    or item.get("maximum_same_lu_corrections") != 3
                    or item.get("native_volume_action_calls") != len(steps)
                ):
                    raise ValueError("V9 compact correction inventory is malformed or exceeds three steps")
                for step_index, record in enumerate(steps):
                    if (
                        not isinstance(record, Mapping)
                        or record.get("step") != step_index
                        or record.get("native_volume_action_calls") != step_index + 1
                    ):
                        raise ValueError("V9 same-LU step records are not a consecutive bounded sequence")
                initial_storage = referenced_array(item["initial_storage_artifact"], "initial storage")
                final_storage = referenced_array(item["final_storage_artifact"], "final storage")
                final_residual = referenced_array(
                    item["final_native_volume_residual_artifact"], "final native residual"
                )
                known = np.asarray(columns[column_index]["known_field"])
                volume_rhs = np.asarray(columns[column_index]["native_volume_rhs"])
                active_original = np.asarray(columns[column_index]["active_original_rows"])
                slave_rows = np.asarray(columns[column_index]["slave_rows"])
                if any(
                    array.shape != (TASK41_V4_FULL_STORAGE_ROWS,)
                    or array.dtype != np.dtype(np.complex128)
                    or not finite(array)
                    for array in (initial_storage, final_storage, final_residual, known, volume_rhs)
                ):
                    raise ValueError("V9 recovery field or residual has an invalid shape/dtype/value")
                final_forward_relative = float(
                    np.sqrt(max(0.0, squared_difference(final_storage, known)))
                    / max(np.sqrt(max(0.0, squared_norm(known))), np.finfo(float).tiny)
                )
                trace_exact = all(
                    np.array_equal(
                        final_storage[active_original[start : start + 262_144]],
                        known[active_original[start : start + 262_144]],
                    )
                    for start in range(0, active_original.size, 262_144)
                )
                final_slave_zero = all(
                    not np.any(final_storage[slave_rows[start : start + 262_144]] != 0.0)
                    for start in range(0, slave_rows.size, 262_144)
                )
                residual_slave_zero = all(
                    not np.any(final_residual[slave_rows[start : start + 262_144]] != 0.0)
                    for start in range(0, slave_rows.size, 262_144)
                )
                residual_identity_squared = 0.0
                final_storage_sha256 = array_sha256(final_storage)
                if callable(native_volume_apply):
                    independently_applied = np.asarray(
                        native_volume_apply(
                            np.array(final_storage, dtype=np.complex128, copy=True)
                        ),
                        dtype=np.complex128,
                    )
                    native_action_calls += 1
                    if (
                        independently_applied.shape != (TASK41_V4_FULL_STORAGE_ROWS,)
                        or not finite(independently_applied)
                    ):
                        raise ValueError("V9 independent native volume action returned an invalid vector")
                    for start in range(0, TASK41_V4_FULL_STORAGE_ROWS, 262_144):
                        stop = min(TASK41_V4_FULL_STORAGE_ROWS, start + 262_144)
                        difference = (
                            np.asarray(volume_rhs[start:stop], dtype=np.complex128)
                            - independently_applied[start:stop]
                            - np.asarray(final_residual[start:stop], dtype=np.complex128)
                        )
                        residual_identity_squared += float(np.vdot(difference, difference).real)
                    residual_identity_relative = float(
                        np.sqrt(max(0.0, residual_identity_squared))
                        / max(np.sqrt(max(0.0, squared_norm(volume_rhs))), 1.0)
                    )
                    action_receipts.append(
                        {
                            "schema": "task41.p0.b0.v9.live_native_action_receipt.v1",
                            "column": column_index,
                            "native_action_calls": 1,
                            "input_storage_sha256": final_storage_sha256,
                            "output_action_sha256": array_sha256(independently_applied),
                            "candidate_evaluator_identity": expected_candidate_identity
                            or report.get("candidate_evaluator_identity"),
                            "candidate_cache_identity": expected_cache_identity
                            or report.get("candidate_evaluator_cache_identity"),
                            "residual_identity_relative": residual_identity_relative,
                        }
                    )
                    del independently_applied
                else:
                    receipt = next(
                        (row for row in action_receipts if row.get("column") == column_index),
                        None,
                    )
                    if (
                        not isinstance(receipt, Mapping)
                        or receipt.get("schema")
                        != "task41.p0.b0.v9.live_native_action_receipt.v1"
                        or receipt.get("native_action_calls") != 1
                        or receipt.get("input_storage_sha256") != final_storage_sha256
                        or receipt.get("candidate_evaluator_identity")
                        != report.get("candidate_evaluator_identity")
                        or receipt.get("candidate_cache_identity")
                        != report.get("candidate_evaluator_cache_identity")
                        or not isinstance(receipt.get("output_action_sha256"), str)
                        or len(receipt["output_action_sha256"]) != 64
                        or any(char not in "0123456789abcdef" for char in receipt["output_action_sha256"])
                    ):
                        raise ValueError("V9 inherited native-action receipt does not bind this saved column")
                    try:
                        residual_identity_relative = float(receipt["residual_identity_relative"])
                    except (KeyError, TypeError, ValueError) as exc:
                        raise ValueError("V9 inherited native-action receipt omits its residual identity") from exc
                    if not np.isfinite(residual_identity_relative):
                        raise ValueError("V9 inherited native-action residual identity is non-finite")
                    reused_action_receipts += 1
                residual_identity_squared = residual_identity_relative * residual_identity_relative
                residual_relative = float(
                    np.sqrt(max(0.0, squared_norm(final_residual)))
                    / max(np.sqrt(max(0.0, squared_norm(volume_rhs))), np.finfo(float).tiny)
                )
                step0 = steps[0]
                storage_hash_matches = array_sha256(final_storage) == item.get("final_storage_sha256")
                residual_hash_matches = array_sha256(final_residual) == item.get("final_native_residual_sha256")
                actual_initial_sha256 = array_sha256(initial_storage)
                column_passed = bool(
                    item.get("initial_storage_sha256") == actual_initial_sha256
                    and step0.get("storage_sha256") == actual_initial_sha256
                    and final_forward_relative <= 1.0e-11
                    and residual_relative <= 1.0e-10
                    and residual_identity_relative <= 1.0e-12
                    and trace_exact
                    and final_slave_zero
                    and residual_slave_zero
                    and storage_hash_matches
                    and residual_hash_matches
                    and item.get("final_native_action_sha256")
                    == (
                        action_receipts[-1].get("output_action_sha256")
                        if callable(native_volume_apply)
                        else next(
                            row.get("output_action_sha256")
                            for row in action_receipts
                            if row.get("column") == column_index
                        )
                    )
                    and step0.get("active_trace_unchanged") is True
                    and step0.get("slave_rows_zero") is True
                )
                recovery_passes.append(column_passed)
                producer_native_action_calls += int(item["native_volume_action_calls"])
            checks["reported_recovery_columns_match_recalculation"] = all(
                item.get("passed") is passed
                for item, passed in zip(recovery_columns, recovery_passes, strict=True)
            )
            checks["reported_recovery_action_call_count_matches_columns"] = (
                recovery_gate.get("native_volume_action_calls") == producer_native_action_calls
            )
            checks["both_candidate_recovery_gates"] = len(recovery_passes) == 2 and all(recovery_passes)
            checks["reported_recovery_gate_matches_recalculation"] = recovery_gate.get(
                "status"
            ) == ("PASS" if all(recovery_passes) else "GATE_FAILED")
            checks["independent_native_volume_action_call_count"] = native_action_calls == (
                2 if callable(native_volume_apply) else 0
            )
            checks["native_action_receipt_branch_matches"] = bool(
                native_action_receipt is None
                if callable(native_volume_apply)
                else reused_action_receipts == 2
                and len(action_receipts) == 2
                and native_action_receipt.get("independent_native_volume_action_calls") == 2
            )
        checks["reported_port_rows_unchanged"] = report.get("saved_port_rows_unchanged") is True
    except (KeyError, OSError, ValueError, TypeError, FloatingPointError) as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
    passed = not errors and all(checks.values())
    return {
        "schema": "task41.p0.b0.v9.compact_volume_independent_check.v1",
        "status": "PASS" if passed else "FAIL",
        "passed": passed,
        "official_result": False,
        "checks": checks,
        "independent_native_volume_action_calls": native_action_calls,
        "native_volume_action_receipts": action_receipts,
        "native_action_receipts_reused": reused_action_receipts,
        "errors": errors,
    }


def _task41_mesh_actual_exact_candidate_profile(
    report_path: Path, report: Mapping[str, Any]
) -> dict[str, str]:
    """Select a frozen V5, V6, or V8 exact-geometry evidence contract."""
    if report_path.name == "task41_p0_v5_mesh_actual_exact_attribution.json":
        if report.get("schema") != "task41.p0.v5.mesh_actual_exact_attribution_receipt.v1":
            raise ValueError("V5 candidate report schema differs")
        return {
            "version": "v5",
            "candidate_prefix": "task41_p0_v5_candidate",
            "attribution_prefix": "task41_p0_v5_attribution",
            "action_schema": "task41.p0.v5.global_geometry_native_elimination_attribution.v1",
            "denominators_source": "review_report_v5.md",
            "check_schema": "task41.p0.v5.mesh_actual_exact_candidate_check.v1",
        }
    if report_path.name == "task41_p0_v6_actual_qmetric_candidate.json":
        expected_identity = "task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1"
        identity_audit = report.get("identity_audit")
        if (
            report.get("schema") != "task41.p0.v6.actual_qmetric_candidate_receipt.v1"
            or report.get("raw_tensor_evaluator") != "actual_qmetric_blocked_gram"
            or not isinstance(identity_audit, Mapping)
            or identity_audit.get("candidate_evaluator_identity") != expected_identity
        ):
            raise ValueError("V6 actual-qmetric candidate identity differs")
        return {
            "version": "v6",
            "candidate_prefix": "task41_p0_v6_qmetric_candidate",
            "attribution_prefix": "task41_p0_v6_qmetric_candidate_attribution",
            "action_schema": "task41.p0.v6.global_geometry_native_elimination_attribution.v1",
            "denominators_source": "review_report_v6.md",
            "check_schema": "task41.p0.v6.actual_qmetric_candidate_check.v1",
        }
    if report_path.name == "task41_p0_v8_selected_trace_star_audit.json":
        if (
            report.get("schema") != "task41.p0.v8.selected_trace_star_audit_receipt.v1"
            or report.get("status") != "COMPLETED_SELECTED_TRACE_STAR_AUDIT"
            or report.get("raw_tensor_evaluator") != "actual_qmetric_blocked_gram"
        ):
            raise ValueError("V8 selected trace-star report schema or status differs")
        return {
            "version": "v8",
            "candidate_prefix": "task41_p0_v8_selected_cell",
            "attribution_prefix": "task41_p0_v8_selected_cell",
            "action_schema": "task41.p0.v8.selected_trace_star_p3_replay.v1",
            "denominators_source": "review_report_v8.md",
            "check_schema": "task41.p0.v8.selected_trace_star_independent_check.v1",
        }
    raise ValueError("exact-geometry candidate report filename is not registered")


def _task41_v6_candidate_producer_contract(
    report_path: Path,
    *,
    expected_report_sha256: str,
    consumer_contract: Mapping[str, Any],
    repo_root: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    """Reopen a saved V6/V8 report's producer contract beside the current checker contract."""
    report_path = Path(report_path).resolve(strict=True)
    results_root = (Path(repo_root) / "results").resolve()
    if not report_path.is_relative_to(results_root):
        raise ValueError("exact-geometry candidate report is outside the registered results tree")
    if (
        not re.fullmatch(r"[0-9a-f]{64}", str(expected_report_sha256))
        or sha256_file(report_path) != expected_report_sha256
    ):
        raise ValueError("exact-geometry candidate report SHA-256 differs from the explicit binding")
    report = _json_object(report_path, "Task41 exact-geometry candidate report")
    profile = _task41_mesh_actual_exact_candidate_profile(report_path, report)
    if profile["version"] not in {"v6", "v8"}:
        return None, None

    source_sha = report.get("consumer_source_sha")
    contract_sha256 = report.get("consumer_contract_sha256")
    raw_contract_path = report.get("consumer_contract_path")
    if (
        not isinstance(source_sha, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_sha) is None
        or not isinstance(contract_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", contract_sha256) is None
        or not isinstance(raw_contract_path, str)
    ):
        raise ValueError("V6 candidate report omits its original producer contract binding")
    producer_contract_path = Path(raw_contract_path)
    producer_contract_path = (
        producer_contract_path
        if producer_contract_path.is_absolute()
        else Path(repo_root) / producer_contract_path
    ).resolve(strict=True)
    expected_contract_path = (
        Path(repo_root) / contract_relative_path(source_sha, "B0")
    ).resolve()
    if producer_contract_path != expected_contract_path:
        raise ValueError("V6 candidate producer contract path differs from its frozen source SHA")
    producer_contract, producer_digest = require_task41_p0_contract(
        producer_contract_path,
        expected_sha256=contract_sha256,
        current_root=repo_root,
        check_current_source=False,
        require_clean_source=False,
        case_id="B0",
    )
    producer_case = producer_contract.get("case")
    consumer_case = consumer_contract.get("case")
    producer_window = producer_contract.get("window")
    consumer_window = consumer_contract.get("window")
    if (
        producer_contract.get("source", {}).get("sha") != source_sha
        or not isinstance(producer_case, Mapping)
        or not isinstance(consumer_case, Mapping)
        or task41_case_id_for_run_id(str(producer_case.get("run_id", ""))) != "B0"
        or task41_case_id_for_run_id(str(consumer_case.get("run_id", ""))) != "B0"
        or not isinstance(producer_window, Mapping)
        or not isinstance(consumer_window, Mapping)
        or producer_window.get("sha256") != consumer_window.get("sha256")
    ):
        raise ValueError("V6 candidate producer contract differs from the current B0 checker window")
    for key in (
        "model_id",
        "method",
        "mpi_size",
        "input_sha256",
        "physical_model_sha256",
        "resolved_config_sha256",
        "run_id",
    ):
        if producer_case.get(key) != consumer_case.get(key):
            raise ValueError(f"V6 candidate producer/checker contracts differ at {key}")
    return producer_contract, producer_digest


def _task41_validate_v6_prefix_qualification(
    qualification: Any,
    *,
    require_qualified: bool,
) -> str:
    from src.solvers.task41_actual_qmetric_blocked_gram import (
        V6_PREFIX_QUALIFICATION_SCHEMA,
        V6_PREFIX_SAMPLE_CELL_INDICES,
    )
    from src.solvers.task41_v4_volume_only_audit import (
        TASK41_V5_FROZEN_DENOMINATORS,
    )

    if not isinstance(qualification, Mapping):
        raise ValueError("V6 candidate evaluator omits its prefix qualification state")
    records = qualification.get("records")
    if (
        qualification.get("schema") != V6_PREFIX_QUALIFICATION_SCHEMA
        or qualification.get("required_sample_cell_indices")
        != list(V6_PREFIX_SAMPLE_CELL_INDICES)
        or not isinstance(records, list)
        or qualification.get("sample_count") != len(records)
        or qualification.get("required_sample_count")
        != len(V6_PREFIX_SAMPLE_CELL_INDICES)
    ):
        raise ValueError("V6 prefix qualification inventory is malformed")
    status = qualification.get("status")
    if status == "P0_NOT_RUN_NO_WINDOW_APPROVAL":
        if (
            records
            or qualification.get("sample_count") != 0
            or qualification.get("geometry_witness_count") != 0
            or qualification.get("full_admission_eligible") is not False
            or require_qualified
        ):
            raise ValueError(
                "a P0 no-window record is legal only as non-qualified inventory, never full admission"
            )
        return "P0_NOT_RUN_NO_WINDOW_APPROVAL"
    if status != "PREFIX_QUALIFIED":
        if require_qualified:
            raise ValueError("V6 full candidate admission requires a qualified eight-key prefix")
        return str(status)
    if (
        len(records) != len(V6_PREFIX_SAMPLE_CELL_INDICES)
        or [record.get("cell_index") for record in records]
        != list(V6_PREFIX_SAMPLE_CELL_INDICES)
        or qualification.get("geometry_witness_count", 0) < 1
        or qualification.get("full_admission_eligible") is not True
    ):
        raise ValueError("V6 qualified prefix is incomplete or attached to a non-qualified report")
    saved_count = 0
    oracle_count = 0
    for record in records:
        source = record.get("source")
        if source == "V4_SAVED_ACTUAL_BLOCKS":
            saved_count += 1
            witness = record.get("geometry_witness")
            if (
                record.get("coordinates_bitwise_identity_passed") is not True
                or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("reference_report_sha256", "")))
                or not isinstance(witness, Mapping)
                or witness.get("status") != "NOT_REQUIRED_V4_SAVED_ACTUAL_BLOCKS"
                or len(record.get("local_action_comparisons", ())) != 6
            ):
                raise ValueError("V6 V4-saved prefix record omits actual identity or local-action evidence")
            observed_actions = record.get("local_action_comparisons", ())
            expected_action_keys = {
                (column, state)
                for column in (0, 1)
                for state in ("known", "j0", "j3")
            }
            if {
                (item.get("column"), item.get("state")) for item in observed_actions
            } != expected_action_keys or any(
                item.get("selected_active_row") != 5_458_716
                or item.get("frozen_denominator")
                != TASK41_V5_FROZEN_DENOMINATORS[item.get("column")]
                or item.get("selected_row_scale_check") != "diagnostic_only"
                or not np.isfinite(item.get("selected_row_difference_over_frozen_denominator", np.nan))
                or not isinstance(item.get("full_local_action"), Mapping)
                or not isinstance(
                    item.get("full_local_action", {}).get("absolute_frobenius"),
                    (int, float),
                )
                or not np.isfinite(
                    item.get("full_local_action", {}).get("absolute_frobenius", np.nan)
                )
                or item.get("full_local_action_scale_check") != "diagnostic_only"
                or not isinstance(
                    item.get("full_local_action_difference_over_frozen_denominator"),
                    (int, float),
                )
                or not np.isfinite(
                    item.get("full_local_action_difference_over_frozen_denominator", np.nan)
                )
                or not np.isclose(
                    item.get("full_local_action_difference_over_frozen_denominator", np.nan),
                    item["full_local_action"]["absolute_frobenius"]
                    / item["frozen_denominator"],
                    rtol=1.0e-12,
                    atol=0.0,
                )
                for item in observed_actions
            ):
                raise ValueError("V6 saved-cell action evidence omits frozen denominator checks")
        elif source == "ORIGINAL_FFCX_KERNEL_ORACLE":
            oracle_count += 1
            witness = record.get("geometry_witness")
            if (
                record.get("coordinates_bitwise_identity_passed") is not True
                or not isinstance(witness, Mapping)
                or witness.get("status") != "BITWISE_EQUAL"
                or witness.get("q_begin") != 0
                or witness.get("q_end") != 512
            ):
                raise ValueError("V6 missing-key sample lacks a full original-kernel geometry witness")
        else:
            raise ValueError("V6 prefix sample source is not registered")
        comparisons = record.get("comparisons")
        if (
            record.get("status") != "PASS"
            or record.get("admission_eligible") is not True
            or not isinstance(comparisons, Mapping)
            or any(
                not isinstance(comparisons.get(name), Mapping)
                or comparisons[name].get("status") != "PASS"
                or comparisons[name].get("relative_limit") != 1.0e-11
                for name in ("raw_tensor", "oriented_tensor")
            )
            or not isinstance(comparisons.get("K_G_J_L"), Mapping)
            or set(comparisons["K_G_J_L"]) != {"K", "G", "J", "L"}
            or any(
                comparisons["K_G_J_L"][name].get("status") != "PASS"
                or comparisons["K_G_J_L"][name].get("relative_limit") != 1.0e-11
                for name in ("K", "G", "J", "L")
            )
            or not isinstance(comparisons.get("R_T_S"), Mapping)
            or set(comparisons["R_T_S"]) != {"R", "T", "S"}
            or any(
                comparisons["R_T_S"][name].get("status") != "PASS"
                or comparisons["R_T_S"][name].get("relative_limit") != 1.0e-11
                for name in ("R", "T", "S")
            )
            or not isinstance(comparisons.get("strict_lu"), Mapping)
            or comparisons["strict_lu"].get("passed") is not True
            or comparisons["strict_lu"].get("relative_limit") != 1.0e-11
            or comparisons.get("condensation_defects_classification") != "diagnostic_only"
        ):
            raise ValueError(
                "V6 prefix sample has a failed/malformed tensor/Schur screen "
                "or mislabeled diagnostic_only defects"
            )
        for defect_name in ("reference_condensation_defects_relative", "candidate_condensation_defects_relative"):
            defects = comparisons.get(defect_name)
            if (
                not isinstance(defects, Mapping)
                or set(defects) != {"KR_plus_G", "TK_plus_J"}
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not np.isfinite(value)
                    or value < 0.0
                    for value in defects.values()
                )
            ):
                raise ValueError("V6 prefix sample has invalid diagnostic condensation defects")
    if saved_count != 2 or oracle_count != 6:
        raise ValueError("V6 prefix qualification must use two saved V4 keys and six missing-key oracles")
    return "PREFIX_QUALIFIED" if require_qualified else "PREFIX_QUALIFIED_INVENTORY"


def _task41_validate_v6_actual_qmetric_audit(
    identity_audit: Mapping[str, Any],
    *,
    require_prefix_qualified: bool = False,
) -> None:
    """Check the source, table, geometry, and compiler profile recorded by V6."""
    from src.solvers.task41_actual_qmetric_blocked_gram import (
        CACHE_IDENTITY_SCHEMA,
        DIMENSION,
        EXPECTED_C_CACHE_SHA256,
        EXPECTED_C_SOURCE_BYTES,
        EXPECTED_C_SOURCE_SHA256,
        EXPECTED_STATIC_TABLE_EXTENTS,
        EXPECTED_GEOMETRY_TABLE_NAMES,
        EXPECTED_UFCX_MODULE_SHA256,
        EXPECTED_UFCX_SIGNATURE,
        FEATURE_NAMES,
        GEOMETRY_ORACLE_TRACE_SCHEMA,
        HELPER_COMPILER_FLAGS,
        IDENTITY,
        INTEGRAL_BODY_BY_TAG,
        POINT_BLOCK_SIZE,
        POINT_COUNT,
        PROFILE_TAGS,
        MAX_GEOMETRY_ORACLE_COMPARISONS,
        QUALIFICATION_STATUS,
        REQUIRED_GEOMETRY_TRACE_FIELDS,
        _cache_identity_digest,
    )

    candidate = identity_audit.get("candidate_evaluator_audit")
    if not isinstance(candidate, Mapping):
        raise ValueError("V6 candidate report omits its evaluator audit")
    prefix_qualification = candidate.get("prefix_qualification")
    prefix_state = _task41_validate_v6_prefix_qualification(
        prefix_qualification,
        require_qualified=require_prefix_qualified,
    )
    helper = candidate.get("geometry_helper")
    if not isinstance(helper, Mapping):
        raise ValueError("V6 candidate report omits its frozen geometry-helper audit")
    source_path = Path(str(helper.get("source_path", "")))
    cache_path = Path(str(helper.get("compile_metadata_path", "")))
    source_hash = str(helper.get("source_sha256", ""))
    cache_hash = str(helper.get("compile_metadata_sha256", ""))
    helper_source_hash = str(helper.get("helper_source_sha256", ""))
    helper_library_hash = str(helper.get("helper_library_sha256", ""))
    reference_hashes = helper.get("reference_table_hashes")
    reference_zero_counts = helper.get("reference_table_zero_counts")
    reference_zero_hashes = helper.get("reference_table_zero_pattern_hashes")
    static_extents = helper.get("static_table_declared_extents")
    geometry_trace_fields = helper.get("geometry_trace_fields")
    feature_pairs = helper.get("feature_pair_map")
    cache_payload = candidate.get("cache_identity_payload")
    cache_identity = str(candidate.get("cache_identity", ""))
    cache_identity_sha256 = str(candidate.get("cache_identity_sha256", ""))
    evaluator_source_path = Path(str(candidate.get("evaluator_source_path", "")))
    evaluator_source_hash = (
        sha256_file(evaluator_source_path)
        if evaluator_source_path.is_file()
        else ""
    )
    expected_pairs = {(left, right) for left in range(12) for right in range(12)}
    observed_pairs = (
        {tuple(pair) for pair in feature_pairs}
        if isinstance(feature_pairs, list)
        and all(
            isinstance(pair, list)
            and len(pair) == 2
            and all(type(index) is int for index in pair)
            for pair in feature_pairs
        )
        else set()
    )
    expected_body_map = {str(tag): digest for tag, digest in INTEGRAL_BODY_BY_TAG.items()}
    expected_extents = {
        name: list(shape) for name, shape in EXPECTED_STATIC_TABLE_EXTENTS.items()
    }
    reference_table_bytes = (
        len(FEATURE_NAMES) * POINT_COUNT * DIMENSION * np.dtype(np.float64).itemsize
        + POINT_COUNT * np.dtype(np.float64).itemsize
    )
    geometry_table_bytes = sum(
        int(np.prod(EXPECTED_STATIC_TABLE_EXTENTS[name], dtype=np.int64))
        * np.dtype(np.float64).itemsize
        for name in EXPECTED_GEOMETRY_TABLE_NAMES
    ) * len(set(INTEGRAL_BODY_BY_TAG.values()))
    expected_cache_payload = {
        "schema": CACHE_IDENTITY_SCHEMA,
        "implementation": IDENTITY,
        "evaluator_source_sha256": candidate.get("evaluator_source_sha256"),
        "ffcx_c_source_sha256": EXPECTED_C_SOURCE_SHA256,
        "ffcx_compile_metadata_sha256": EXPECTED_C_CACHE_SHA256,
        "ffcx_module_sha256": EXPECTED_UFCX_MODULE_SHA256,
        "ufcx_signature": EXPECTED_UFCX_SIGNATURE,
        "reference_table_source_sha256": EXPECTED_C_SOURCE_SHA256,
        "integral_body_by_tag": expected_body_map,
        "table_extent_contract": {
            "FE0": [1, 1, POINT_COUNT, DIMENSION],
            "FE2": [1, 1, POINT_COUNT, 8],
            "weights": [POINT_COUNT],
        },
        "compiler_flags": list(HELPER_COMPILER_FLAGS),
        "geometry_oracle_trace_schema": GEOMETRY_ORACLE_TRACE_SCHEMA,
    }
    oracle_count = helper.get("original_kernel_oracle_execution_count")
    oracle_status = helper.get("original_kernel_oracle_execution_status")
    oracle_artifact_bytes = helper.get("original_kernel_oracle_artifact_bytes")
    oracle_compile_audits = helper.get("original_kernel_oracle_compile_audits")
    oracle_records = candidate.get("original_kernel_oracle_records")
    geometry_records = candidate.get("geometry_oracle_comparison_records")
    valid_oracle_inventory = (
        type(oracle_count) is int
        and 0 <= oracle_count <= MAX_GEOMETRY_ORACLE_COMPARISONS
        and isinstance(oracle_artifact_bytes, int)
        and 0 <= oracle_artifact_bytes <= 512 * 1024**2
        and isinstance(oracle_compile_audits, Mapping)
        and isinstance(oracle_records, list)
        and len(oracle_records) == oracle_count
        and isinstance(geometry_records, list)
        and len(geometry_records) == oracle_count
    )
    if valid_oracle_inventory:
        allowed_digests = set(INTEGRAL_BODY_BY_TAG.values())
        valid_oracle_inventory = set(oracle_compile_audits).issubset(allowed_digests)
        audited_artifact_bytes = 0
        for digest, compile_audit in oracle_compile_audits.items():
            if not isinstance(compile_audit, Mapping):
                valid_oracle_inventory = False
                break
            source_bytes = compile_audit.get("source_bytes")
            library_bytes = compile_audit.get("library_bytes")
            if (
                type(source_bytes) is not int
                or not 0 < source_bytes <= 2 * EXPECTED_C_SOURCE_BYTES
                or type(library_bytes) is not int
                or library_bytes <= 0
                or compile_audit.get("compile_metadata_sha256") != EXPECTED_C_CACHE_SHA256
                or not re.fullmatch(r"[0-9a-f]{64}", str(compile_audit.get("source_sha256", "")))
                or not re.fullmatch(r"[0-9a-f]{64}", str(compile_audit.get("library_sha256", "")))
                or not isinstance(compile_audit.get("compiler_flags"), list)
                or not isinstance(compile_audit.get("command"), list)
                or any(
                    not isinstance(compile_audit.get(key), (int, float))
                    or not np.isfinite(compile_audit.get(key))
                    or compile_audit.get(key) < 0
                    for key in ("source_generation_seconds", "compiler_seconds")
                )
            ):
                valid_oracle_inventory = False
                break
            audited_artifact_bytes += source_bytes + library_bytes
        if audited_artifact_bytes != oracle_artifact_bytes:
            valid_oracle_inventory = False
        for index, record in enumerate(oracle_records):
            geometry_record = geometry_records[index]
            if not isinstance(record, Mapping) or not isinstance(geometry_record, Mapping):
                valid_oracle_inventory = False
                break
            tag = record.get("tag")
            body_digest = INTEGRAL_BODY_BY_TAG.get(tag) if type(tag) is int else None
            tensor_comparison = record.get("tensor_comparison")
            geometry_comparison = record.get("geometry_comparison")
            times = (
                "kernel_call_seconds",
                "output_allocation_seconds",
                "source_generation_seconds",
                "compiler_seconds",
                "candidate_build_seconds",
            )
            if (
                tag not in PROFILE_TAGS
                or body_digest not in oracle_compile_audits
                or record.get("execution_status") != "EXECUTED_BOUNDED_ORIGINAL_KERNEL_ORACLE"
                or type(record.get("q_begin")) is not int
                or type(record.get("q_end")) is not int
                or not 0 <= record["q_begin"] < record["q_end"] <= POINT_COUNT
                or any(
                    not isinstance(record.get(key), (int, float))
                    or not np.isfinite(record.get(key))
                    or record.get(key) < 0
                    for key in times
                )
                or not isinstance(tensor_comparison, Mapping)
                or tensor_comparison.get("relative_limit") != 1.0e-11
                or tensor_comparison.get("status")
                != ("PASS_SCREEN" if tensor_comparison.get("relative_frobenius", np.inf) <= 1.0e-11 else "FAIL_SCREEN")
                or any(
                    not isinstance(tensor_comparison.get(key), (int, float))
                    or not np.isfinite(tensor_comparison.get(key))
                    or tensor_comparison.get(key) < 0
                    for key in ("relative_frobenius", "absolute_frobenius", "max_abs")
                )
                or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("original_tensor_sha256", "")))
                or not re.fullmatch(r"[0-9a-f]{64}", str(record.get("candidate_tensor_sha256", "")))
                or not isinstance(geometry_comparison, Mapping)
                or geometry_comparison.get("status") not in {"BITWISE_EQUAL", "MISMATCH"}
                or geometry_record.get("tag") != tag
                or geometry_record.get("q_begin") != record.get("q_begin")
                or geometry_record.get("q_end") != record.get("q_end")
                or geometry_record.get("status") != geometry_comparison.get("status")
                or record.get("compile_audit") != oracle_compile_audits.get(body_digest)
            ):
                valid_oracle_inventory = False
                break
    if valid_oracle_inventory and oracle_count == 0:
        valid_oracle_inventory = (
            oracle_status == "NOT_RUN_NO_WINDOW_APPROVAL"
            and oracle_artifact_bytes == 0
            and not oracle_compile_audits
            and prefix_state == "P0_NOT_RUN_NO_WINDOW_APPROVAL"
            and not require_prefix_qualified
        )
    elif valid_oracle_inventory:
        valid_oracle_inventory = (
            oracle_status == "EXECUTED_BOUNDED_ORIGINAL_KERNEL_ORACLE"
            and bool(oracle_compile_audits)
            and (
                prefix_state
                not in {"PREFIX_QUALIFIED", "PREFIX_QUALIFIED_INVENTORY"}
                or oracle_count == 6
            )
            and (
                not require_prefix_qualified
                or (oracle_count == 6 and prefix_state == "PREFIX_QUALIFIED")
            )
        )
    if not valid_oracle_inventory:
        raise ValueError("V6 bounded original-kernel oracle inventory is malformed")
    cache_identity_digest = _cache_identity_digest(expected_cache_payload)
    if (
        candidate.get("implementation") != IDENTITY
        or candidate.get("qualification_status") != QUALIFICATION_STATUS
        or candidate.get("expected_ufcx_signature") != EXPECTED_UFCX_SIGNATURE
        or candidate.get("full_form_signature") != EXPECTED_UFCX_SIGNATURE
        or candidate.get("ffcx_module_sha256") != EXPECTED_UFCX_MODULE_SHA256
        or candidate.get("ffcx_default_kernel_absent") is not True
        or candidate.get("point_block_size") != POINT_BLOCK_SIZE
        or candidate.get("workspace_bytes_upper") != 1024**3
        or candidate.get("prepare_workspace_bytes_upper") != 1024**3
        or candidate.get("key_workspace_bytes_upper") != 128 * 1024**2
        or candidate.get("class_timing_metadata_bytes_upper") != 16 * 1024**2
        or candidate.get("helper_scratch_bytes_upper") != 128 * 1024**2
        or candidate.get("original_kernel_oracle_scratch_bytes_upper") != 512 * 1024**2
        or type(candidate.get("class_timing_metadata_bytes")) is not int
        or not 0 <= candidate.get("class_timing_metadata_bytes", -1)
        <= candidate.get("class_timing_metadata_bytes_upper", 0)
        or not isinstance(candidate.get("phase_seconds_by_stage"), Mapping)
        or set(candidate.get("phase_seconds_by_stage", {}))
        != {"geometry", "pack", "gram", "scatter", "release"}
        or any(
            not isinstance(value, (int, float))
            or not np.isfinite(value)
            or value < 0
            for value in candidate.get("phase_seconds_by_stage", {}).values()
        )
        or not isinstance(candidate.get("class_seconds_summary"), Mapping)
        or candidate.get("class_seconds_summary", {}).get("count")
        != candidate.get("class_count")
        or not isinstance(candidate.get("class_seconds_summary", {}).get("total"), (int, float))
        or not isinstance(candidate.get("class_seconds_summary", {}).get("max"), (int, float))
        or candidate.get("class_seconds_summary", {}).get("total", -1) < 0
        or candidate.get("class_seconds_summary", {}).get("max", -1) < 0
        or candidate.get("class_seconds_summary", {}).get("max", 0)
        > candidate.get("class_seconds_summary", {}).get("total", 0)
        or not isinstance(helper.get("helper_source_bytes"), int)
        or helper.get("helper_source_bytes", -1) < 0
        or not isinstance(helper.get("helper_library_bytes"), int)
        or helper.get("helper_library_bytes", -1) < 0
        or helper.get("helper_scratch_retained_bytes")
        != helper.get("helper_source_bytes", 0) + helper.get("helper_library_bytes", 0)
        or helper.get("helper_scratch_retained_bytes", 0) > 128 * 1024**2
        or candidate.get("cache_identity_payload") != expected_cache_payload
        or cache_identity_sha256 != cache_identity_digest
        or cache_identity != f"{IDENTITY}:{cache_identity_digest}"
        or identity_audit.get("candidate_evaluator_cache_identity") != cache_identity
        or candidate.get("evaluator_source_path") is None
        or not Path(str(candidate.get("evaluator_source_path"))).is_absolute()
        or not re.fullmatch(r"[0-9a-f]{64}", str(candidate.get("evaluator_source_sha256", "")))
        or evaluator_source_hash != candidate.get("evaluator_source_sha256")
        or candidate.get("mass_coefficient_conjugated") is not False
        or candidate.get("hermitian_assumption") is not False
        or candidate.get("raw_tensor_built_before_original_schur") is not True
        or not source_path.is_absolute()
        or source_path.suffix != ".c"
        or cache_path != Path(str(source_path) + ".cached")
        or helper.get("source_bytes") != EXPECTED_C_SOURCE_BYTES
        or source_hash != EXPECTED_C_SOURCE_SHA256
        or cache_hash != EXPECTED_C_CACHE_SHA256
        or helper.get("reference_table_names") != list(FEATURE_NAMES)
        or helper.get("reference_table_bytes") != reference_table_bytes
        or helper.get("shared_table_bytes_upper")
        != reference_table_bytes + geometry_table_bytes
        or static_extents != expected_extents
        or not isinstance(reference_zero_counts, list)
        or len(reference_zero_counts) != len(FEATURE_NAMES)
        or any(type(value) is not int or not 0 <= value <= POINT_COUNT * DIMENSION for value in reference_zero_counts)
        or not isinstance(reference_zero_hashes, list)
        or len(reference_zero_hashes) != len(FEATURE_NAMES)
        or any(not re.fullmatch(r"[0-9a-f]{64}", str(item)) for item in reference_zero_hashes)
        or not isinstance(geometry_trace_fields, list)
        or not REQUIRED_GEOMETRY_TRACE_FIELDS.issubset(geometry_trace_fields)
        or helper.get("geometry_trace_source")
        != "same_frozen_FFCx_scalar_graph_as_actual_qmetric_block"
        or helper.get("original_kernel_oracle_generator")
        != "_FrozenFFCxGeometryHelper.original_kernel_oracle_source"
        or candidate.get("original_kernel_oracle_workspace_bytes_upper") != 1024**3
        or candidate.get("original_kernel_oracle_source_bytes_upper")
        != 2 * EXPECTED_C_SOURCE_BYTES
        or not isinstance(candidate.get("geometry_oracle_comparison_records"), list)
        or helper.get("quadrature_point_count") != POINT_COUNT
        or helper.get("geometry_helper_block_size") != POINT_BLOCK_SIZE
        or helper.get("geometry_expression_source")
        != "frozen_FFCx_Q907_Jacobian_and_fw_graph"
        or helper.get("geometry_shortcut_used") is not False
        or helper.get("compiler_flags") != list(HELPER_COMPILER_FLAGS)
        or candidate.get("integral_body_by_tag") != expected_body_map
        or not isinstance(feature_pairs, list)
        or len(feature_pairs) != 144
        or observed_pairs != expected_pairs
        or not isinstance(reference_hashes, list)
        or len(reference_hashes) != len(FEATURE_NAMES)
        or any(not re.fullmatch(r"[0-9a-f]{64}", str(item)) for item in reference_hashes)
        or not re.fullmatch(r"[0-9a-f]{64}", str(helper.get("reference_weight_sha256", "")))
        or not re.fullmatch(r"[0-9a-f]{64}", helper_source_hash)
        or not re.fullmatch(r"[0-9a-f]{64}", helper_library_hash)
    ):
        raise ValueError("V6 candidate evaluator audit differs from the frozen source profile")


def _task41_v6_report_requires_prefix_qualification(report: Mapping[str, Any]) -> bool:
    """Require a passing eight-key prefix for every completed full candidate outcome."""
    return (
        report.get("candidate_numeric_status")
        in {"PASS", "ACTUAL_COORDINATES_INSUFFICIENT"}
        or report.get("status")
        in {"CANDIDATE_NUMERICAL_PASS_CHECKER_PENDING", "ACTUAL_COORDINATES_INSUFFICIENT"}
    )


def _task41_v6_global_attribution_identity_binding(
    attribution: Mapping[str, Any], identity_audit: Mapping[str, Any]
) -> None:
    """Bind optional attribution identity copies to the independently checked parent audit."""
    identity_fields = (
        "candidate_evaluator_identity",
        "candidate_evaluator_cache_identity",
    )
    parent_values = {field: identity_audit.get(field) for field in identity_fields}
    if any(not isinstance(value, str) or not value for value in parent_values.values()):
        raise ValueError("V6 global attribution parent identity_audit is incomplete")
    if any(
        field in attribution and attribution[field] != parent_values[field]
        for field in identity_fields
    ):
        raise ValueError(
            "V6 global attribution evaluator/cache identity differs from parent identity_audit"
        )


def _task41_v8_complex_pair(value: Any, label: str) -> complex:
    if (
        not isinstance(value, (list, tuple))
        or len(value) != 2
        or any(type(part) not in (int, float) for part in value)
        or not np.isfinite(np.asarray(value, dtype=np.float64)).all()
    ):
        raise ValueError(f"V8 {label} is not a finite real/imaginary pair")
    return complex(float(value[0]), float(value[1]))


def _task41_v8_complex_pairs(value: Any, label: str) -> np.ndarray:
    """Decode the producer's JSON list of [real, imag] coefficients."""
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"V8 {label} is not a sequence of real/imaginary pairs")
    return np.asarray(
        [
            _task41_v8_complex_pair(pair, f"{label}[{index}]")
            for index, pair in enumerate(value)
        ],
        dtype=np.complex128,
    )


def _task41_v8_check_selected_row_contributions(
    contributions: Mapping[str, Any], scalars: Mapping[str, complex], label: str
) -> None:
    """Check producer-owned selected-row scalars without treating arrays as scalars."""
    if not isinstance(contributions, Mapping):
        raise ValueError(f"V8 {label} omits selected scalar contributions")
    field_keys = {
        "s": "S_action",
        "rhs_i": "local_reduced_rhs_T_b_i",
        "T_r_i": "T_r_i",
        "delta_t": "delta_t_cell",
        "Q": "Q_cell",
        "Q_regrouped": "Q_regrouped_cell",
    }
    for field, report_key in field_keys.items():
        value = _task41_v8_complex_pair(contributions.get(report_key), report_key)
        _task41_v8_assert_close(value, scalars[field], f"{label} scalar {report_key}")
    # projected_T_r_i is intentionally absent here: the producer saves it as
    # an array in signed_action_artifacts, and the caller checks that array.
    for report_key, scalar_name in (
        ("projected_actual_trace", "delta_t"),
        ("projected_Q", "Q"),
        ("projected_Q_regrouped", "Q_regrouped"),
    ):
        _task41_v8_assert_close(
            _task41_v8_complex_pair(contributions.get(report_key), report_key),
            scalars[scalar_name],
            f"{label} scalar {report_key}",
        )


def _task41_v8_assert_close(actual: Any, expected: Any, label: str) -> None:
    left = np.asarray(actual)
    right = np.asarray(expected)
    if (
        left.shape != right.shape
        or not np.isfinite(left).all()
        or not np.isfinite(right).all()
        or not np.allclose(left, right, rtol=2.0e-12, atol=2.0e-13)
    ):
        raise ValueError(f"V8 independent replay differs from saved {label}")


def _task41_v11_recompute_saved_candidate_arrays(
    report: Mapping[str, Any],
    metadata: Mapping[str, Any],
    donor: Mapping[str, Any],
    *,
    v9_y_row: np.ndarray,
    v9_g_row: np.ndarray,
    load_array: Any,
) -> dict[str, Any]:
    """Recompute selected y/g and signed identities from saved matrices and LU."""
    from scipy import sparse
    from scipy.linalg import lu_solve
    from src.runners.task41_p0_v4_volume_only_audit import (
        TASK41_P0_V11_METADATA_ACTIVE_ROW as ACTIVE,
        TASK41_P0_V11_METADATA_ORIGINAL_ROW as ORIGINAL,
        TASK41_P0_V11_SELECTED_CELLS as CELLS,
    )

    def array(ref: Any, label: str) -> np.ndarray:
        value = np.asarray(load_array(ref, label))
        if value.dtype.kind not in "fciu" or not np.isfinite(value).all():
            raise ValueError(f"{label} contains invalid values")
        return value

    def saved(ref: Any, expected: np.ndarray, label: str) -> None:
        _task41_v8_assert_close(array(ref, label), expected, label)

    def pair(value: complex) -> list[float]:
        value = complex(value)
        return [float(value.real), float(value.imag)]

    if (
        report.get("schema") != "task41.p0.v11.selected_trace_star_candidate_replay.v1"
        or report.get("status") != "COMPLETED_LOCAL_CANDIDATE_REPLAY"
        or report.get("selected_active_row") != ACTIVE
        or report.get("selected_original_row") != ORIGINAL
        or report.get("incident_cell_order") != list(CELLS)
        or report.get("scientific_qualified") is not False
        or metadata.get("selected_active_row") != ACTIVE
        or metadata.get("selected_original_row") != ORIGINAL
    ):
        raise ValueError("V11 saved replay scope or metadata identity differs")
    metadata_cells = metadata.get("selected_cells")
    report_cells = report.get("cells")
    report_columns = report.get("columns")
    columns = donor.get("columns")
    if (
        not isinstance(metadata_cells, list)
        or [item.get("cell_index") for item in metadata_cells] != list(CELLS)
        or not isinstance(report_cells, list)
        or [item.get("cell_index") for item in report_cells] != list(CELLS)
        or not isinstance(report_columns, list)
        or len(report_columns) != 2
        or not isinstance(columns, (list, tuple))
        or len(columns) != 2
    ):
        raise ValueError("V11 saved replay coverage is incomplete")
    active_rows = np.asarray(columns[0]["active_original_rows"])
    if (
        active_rows.ndim != 1
        or active_rows.dtype.kind not in "iu"
        or not np.array_equal(active_rows, np.asarray(columns[1]["active_original_rows"]))
        or ACTIVE >= active_rows.size
        or int(active_rows[ACTIVE]) != ORIGINAL
    ):
        raise ValueError("V11 donor active-to-original mapping differs")

    cell_identity = {360: (2, 4680, 375), 446: (1, 0, 75)}
    cells: dict[int, dict[str, Any]] = {}
    for meta, record in zip(metadata_cells, report_cells, strict=True):
        cell = int(meta["cell_index"])
        tag, permutation, local_trace = cell_identity[cell]
        refs = meta.get("arrays")
        candidate_refs = record.get("candidate_artifacts")
        if (
            meta.get("cell_tag") != tag
            or meta.get("cell_permutation") != permutation
            or meta.get("selected_local_trace_rows") != [local_trace]
            or meta.get("selected_trace_coefficients") != [[1.0, 0.0]]
            or record.get("cell_tag") != tag
            or record.get("cell_permutation") != permutation
            or record.get("actual_coordinate_sha256") != meta.get("actual_coordinate_sha256")
            or not isinstance(refs, Mapping)
            or not isinstance(candidate_refs, Mapping)
        ):
            raise ValueError(f"V11 cell {cell} metadata identity differs")
        local = {
            name: array(refs[name], f"cell {cell} metadata {name}")
            for name in (
                "actual_geometry_coordinates", "original_rows", "interior_positions",
                "trace_positions", "interior_original_rows", "trace_original_rows",
                "active_ids", "trace_expansion_data", "trace_expansion_indices",
                "trace_expansion_indptr",
            )
        }
        coord = np.ascontiguousarray(local["actual_geometry_coordinates"], dtype=np.float64)
        if hashlib.sha256(memoryview(coord).cast("B")).hexdigest() != meta.get("actual_coordinate_sha256"):
            raise ValueError(f"V11 cell {cell} coordinates differ from their saved identity")
        dim = int(metadata.get("element_dimension", -1))
        interior = np.asarray(local["interior_positions"], dtype=np.int64)
        trace = np.asarray(local["trace_positions"], dtype=np.int64)
        orig = np.asarray(local["original_rows"], dtype=np.int64)
        irows = np.asarray(local["interior_original_rows"], dtype=np.int64)
        trows = np.asarray(local["trace_original_rows"], dtype=np.int64)
        ids = np.asarray(local["active_ids"], dtype=np.int64)
        if (
            dim < 1
            or orig.shape != (dim,)
            or not np.array_equal(orig[interior], irows)
            or not np.array_equal(orig[trace], trows)
            or not np.array_equal(np.sort(np.r_[interior, trace]), np.arange(dim))
            or np.any(ids < 0)
            or np.any(ids >= active_rows.size)
            or trows[local_trace] != ORIGINAL
        ):
            raise ValueError(f"V11 cell {cell} local row maps differ")
        E = sparse.csr_matrix(
            (
                np.asarray(local["trace_expansion_data"], dtype=np.complex128),
                np.asarray(local["trace_expansion_indices"], dtype=np.int32),
                np.asarray(local["trace_expansion_indptr"], dtype=np.int32),
            ),
            shape=(len(trace), len(ids)),
        )
        target = np.flatnonzero(ids == ACTIVE)
        e_row = E.getrow(local_trace)
        if (
            target.size != 1
            or e_row.nnz != 1
            or int(e_row.indices[0]) != int(target[0])
            or e_row.data[0] != 1.0 + 0.0j
        ):
            raise ValueError(f"V11 cell {cell} selected E row differs")
        names = {"raw_tensor", "oriented_tensor", "R", "T", "S", "interior_lu", "interior_lu_pivots"}
        if set(candidate_refs) != names:
            raise ValueError(f"V11 cell {cell} candidate artifact inventory differs")
        c = {name: array(candidate_refs[name], f"cell {cell} {name}") for name in names}
        tensor = np.asarray(c["oriented_tensor"], dtype=np.complex128)
        lu = np.asarray(c["interior_lu"], dtype=np.complex128)
        pivots = _task41_b0_owned_writable_lu_pivots(
            np.asarray(c["interior_lu_pivots"]), order=len(interior)
        )
        if (
            np.asarray(c["raw_tensor"]).shape != (dim, dim)
            or tensor.shape != (dim, dim)
            or lu.shape != (len(interior), len(interior))
            or any(c[name].dtype != np.dtype(np.complex128) for name in names - {"interior_lu_pivots"})
        ):
            raise ValueError(f"V11 cell {cell} saved matrix layout differs")
        K = tensor[np.ix_(interior, interior)]
        G = tensor[np.ix_(interior, trace)]
        J = tensor[np.ix_(trace, interior)]
        L = tensor[np.ix_(trace, trace)]
        R, T, S = (np.asarray(c[name], dtype=np.complex128) for name in ("R", "T", "S"))
        if R.shape != (len(interior), len(trace)) or T.shape != (len(trace), len(interior)) or S.shape != (len(trace), len(trace)):
            raise ValueError(f"V11 cell {cell} saved R/T/S layout differs")
        cells[cell] = {
            "record": record, "irows": irows, "trows": trows, "ids": ids,
            "E": E, "target": int(target[0]), "K": K, "G": G, "J": J,
            "L": L, "R": R, "T": T, "S": S, "lu": lu, "pivots": pivots,
        }

    checked = 0
    solves = {"bi": 0, "ri": 0, "getrs": 0}
    replay_rows = []
    for col, (column_report, donor_col) in enumerate(zip(report_columns, columns, strict=True)):
        states = donor_col.get("states")
        if not isinstance(states, (list, tuple)) or len(states) != 2:
            raise ValueError(f"V11 donor column {col} lacks j0/j3 states")
        state = {item.get("label"): item for item in states}
        if len(state) != 2 or set(state) != {"j0", "j3"}:
            raise ValueError(f"V11 donor column {col} state labels are duplicated")
        b_full = np.asarray(donor_col["native_rhs"])
        b_volume = np.asarray(donor_col["native_volume_rhs"])
        known = np.asarray(donor_col["known_field"])
        if any(a.ndim != 1 for a in (b_full, b_volume, known)):
            raise ValueError(f"V11 donor column {col} source vectors are malformed")
        b_row = complex(b_full[ORIGINAL])
        beta_rows = np.asarray(donor_col["b_alpha_rows"])
        beta_values = np.asarray(donor_col["b_alpha_values"])
        beta_pos = np.flatnonzero(beta_rows == ORIGINAL)
        if beta_pos.size > 1:
            raise ValueError(f"V11 donor column {col} duplicates selected B-alpha")
        beta = complex(beta_values[int(beta_pos[0])]) if beta_pos.size else 0.0j
        incident = column_report.get("incident_cell_terms")
        if not isinstance(incident, list) or [x.get("cell_index") for x in incident] != list(CELLS):
            raise ValueError(f"V11 column {col} cell coverage differs")
        by_cell = {int(x["cell_index"]): x for x in incident}
        s_terms, t_terms, lu_terms = [], [], []
        state_cell_terms = {
            label: {key: [] for key in ("delta_t", "C_S_t", "J_middle", "minus_J_z_r")}
            for label in ("j0", "j3")
        }
        for cell_id in CELLS:
            c = cells[cell_id]
            item = by_cell[cell_id]
            arts = item["artifacts"]
            b_i = np.asarray(b_full[c["irows"]], dtype=np.complex128)
            if not np.array_equal(b_i, b_volume[c["irows"]]):
                raise ValueError(f"V11 cell {cell_id} native volume/full RHS differs")
            t_c = np.asarray(c["E"] @ known[active_rows[c["ids"]]], dtype=np.complex128).reshape(-1)
            selected_trace = 375 if cell_id == 360 else 75
            if complex(t_c[selected_trace]) != complex(known[ORIGINAL]):
                raise ValueError(f"V11 cell {cell_id} selected known trace differs")
            S_t, T_b = c["S"] @ t_c, c["T"] @ b_i
            z_b = lu_solve((c["lu"], c["pivots"].copy()), b_i, check_finite=True)
            minus_J_z_b = -(c["J"] @ z_b)
            pS = np.asarray(c["E"].conj().T @ S_t).reshape(-1)
            pT = np.asarray(c["E"].conj().T @ T_b).reshape(-1)
            pLU = np.asarray(c["E"].conj().T @ minus_J_z_b).reshape(-1)
            pos = c["target"]
            s_terms.append(complex(pS[pos]))
            t_terms.append(complex(pT[pos]))
            lu_terms.append(complex(pLU[pos]))
            for name, value in (
                ("known_trace_local", t_c), ("native_rhs_interior", b_i),
                ("S_action", S_t), ("S_projected_active", pS),
                ("T_native_rhs", T_b), ("T_projected_active", pT),
                ("same_lu_z_b", z_b), ("same_lu_minus_Jz_b", minus_J_z_b),
                ("same_lu_minus_Jz_b_independent_difference", np.zeros_like(minus_J_z_b)),
                ("same_lu_projected_active", pLU),
            ):
                saved(arts.get(name), value, f"cell {cell_id}/{name}")
                checked += 1
            for label in ("j0", "j3"):
                q = state[label]
                u = np.asarray(q["storage"][c["irows"]], dtype=np.complex128)
                n = np.asarray(q["native_volume_action"][c["irows"]], dtype=np.complex128)
                n_t = np.asarray(q["native_volume_action"][c["trows"]], dtype=np.complex128)
                r_i = b_i - n
                z_r = lu_solve((c["lu"], c["pivots"].copy()), r_i, check_finite=True)
                minus_J_z_r = -(c["J"] @ z_r)
                r_b, r_r = b_i - c["K"] @ z_b, r_i - c["K"] @ z_r
                delta_i = c["K"] @ u + c["G"] @ t_c - n
                delta_t = c["J"] @ u + c["L"] @ t_c
                E_R_t = (c["K"] @ c["R"] + c["G"]) @ t_c
                C_S_t = (c["S"] - c["L"] - c["J"] @ c["R"]) @ t_c
                middle = c["R"] @ t_c + z_b - z_r - u
                eq_l, eq_r = c["K"] @ middle, E_R_t - delta_i - r_b + r_r
                state_item = next((x for x in arts.get("states", []) if x.get("state") == label), None)
                if not isinstance(state_item, Mapping):
                    raise ValueError(f"V11 cell {cell_id}/{label} saved arrays missing")
                state_arts = state_item.get("artifacts")
                for name, value in (
                    ("u_i", u), ("native_action_i", n), ("native_action_global_trace_slice", n_t),
                    ("r_i", r_i), ("same_lu_z_r", z_r), ("same_lu_minus_Jz_r", minus_J_z_r),
                    ("delta_i", delta_i), ("delta_t", delta_t), ("r_b", r_b), ("r_r", r_r),
                    ("E_R_t", E_R_t), ("C_S_t", C_S_t), ("review_eq2_left", eq_l),
                    ("review_eq2_right", eq_r), ("review_eq2_difference", eq_l - eq_r),
                    ("old_Tb_plus_Jzb", T_b + c["J"] @ z_b),
                    ("old_identity_rhs", (c["J"] + c["T"] @ c["K"]) @ z_b + c["T"] @ r_b),
                    ("old_identity_difference", (T_b + c["J"] @ z_b) - ((c["J"] + c["T"] @ c["K"]) @ z_b + c["T"] @ r_b)),
                ):
                    saved(state_arts.get(name), value, f"cell {cell_id}/{label}/{name}")
                    checked += 1
                project = lambda x: complex(np.asarray(c["E"].conj().T @ x).reshape(-1)[pos])
                state_cell_terms[label]["delta_t"].append(project(delta_t))
                state_cell_terms[label]["C_S_t"].append(project(C_S_t))
                state_cell_terms[label]["J_middle"].append(project(c["J"] @ middle))
                state_cell_terms[label]["minus_J_z_r"].append(project(minus_J_z_r))
                solves["ri"] += 1
                solves["getrs"] += 1
            solves["bi"] += 1
            solves["getrs"] += 1

        row_states: dict[str, dict[str, complex]] = {}
        for label in ("j0", "j3"):
            action = complex(state[label]["native_volume_action"][ORIGINAL])
            y = 0.0 + 0.0j
            g = b_row
            g_t = b_row
            review_rhs = 0.0 + 0.0j
            review_lu_residual = 0.0 + 0.0j
            for cell_index, _cell_id in enumerate(CELLS):
                y += s_terms[cell_index]
                g += lu_terms[cell_index]
                g_t += t_terms[cell_index]
                review_rhs += state_cell_terms[label]["delta_t"][cell_index]
                review_rhs += state_cell_terms[label]["C_S_t"][cell_index]
                review_rhs += state_cell_terms[label]["J_middle"][cell_index]
                review_lu_residual += state_cell_terms[label]["minus_J_z_r"][cell_index]
            y += beta
            review_rhs -= action
            residual = b_row - action - beta
            lhs = y - g + residual + review_lu_residual
            row_states[label] = {"y": y, "g": g, "g_t": g_t, "lhs": lhs, "rhs": review_rhs}

        producer_y = _task41_v8_complex_pair(column_report.get("replayed_y9"), "replayed_y9")
        producer_g = _task41_v8_complex_pair(column_report.get("replayed_g9_same_lu"), "replayed_g9_same_lu")
        producer_g_t = _task41_v8_complex_pair(column_report.get("replayed_g9_stored_T"), "replayed_g9_stored_T")
        identities = column_report.get("review_v11_row_identities")
        if not isinstance(identities, list):
            raise ValueError(f"V11 column {col} omits paired review identities")
        identity_by_state = {
            str(item.get("state")): item
            for item in identities
            if isinstance(item, Mapping) and item.get("column") == col
        }
        if set(identity_by_state) != {"j0", "j3"}:
            raise ValueError(f"V11 column {col} must bind j0/j3 review identities")

        state_comparisons: dict[str, dict[str, Any]] = {}
        for label in ("j0", "j3"):
            row = row_states[label]
            identity = identity_by_state[label]
            lhs_reported = _task41_v8_complex_pair(identity.get("equation_1_lhs"), f"{label} equation_1_lhs")
            rhs_reported = _task41_v8_complex_pair(identity.get("equation_1_rhs"), f"{label} equation_1_rhs")
            y_saved_delta = row["y"] - complex(v9_y_row[col])
            g_saved_delta = row["g"] - complex(v9_g_row[col])
            y_report_delta = row["y"] - producer_y
            g_report_delta = row["g"] - producer_g
            g_t_report_delta = row["g_t"] - producer_g_t
            lhs_report_delta = row["lhs"] - lhs_reported
            rhs_report_delta = row["rhs"] - rhs_reported
            state_comparisons[label] = {
                "y9": pair(row["y"]),
                "g9_same_lu": pair(row["g"]),
                "g9_stored_T": pair(row["g_t"]),
                "equation_1_lhs": pair(row["lhs"]),
                "equation_1_rhs": pair(row["rhs"]),
                "saved_v9_y9_delta": pair(y_saved_delta),
                "saved_v9_g9_delta": pair(g_saved_delta),
                "exactly_matches_saved_v9_y9": y_saved_delta == 0.0j,
                "exactly_matches_saved_v9_g9": g_saved_delta == 0.0j,
                "candidate_report_y9_delta": pair(y_report_delta),
                "candidate_report_g9_same_lu_delta": pair(g_report_delta),
                "candidate_report_g9_stored_T_delta": pair(g_t_report_delta),
                "exactly_matches_candidate_report_y_g": y_report_delta == 0.0j and g_report_delta == 0.0j,
                "exactly_matches_candidate_report_stored_T": g_t_report_delta == 0.0j,
                "producer_equation_1_lhs_delta": pair(lhs_report_delta),
                "producer_equation_1_rhs_delta": pair(rhs_report_delta),
                "exactly_matches_producer_equation_1": lhs_report_delta == 0.0j and rhs_report_delta == 0.0j,
            }

        paired_state = {
            key: row_states["j3"][key] - row_states["j0"][key]
            for key in ("y", "g", "g_t", "lhs", "rhs")
        }
        exact_v9_y_g = all(
            state_comparisons[label][key]
            for label in ("j0", "j3")
            for key in ("exactly_matches_saved_v9_y9", "exactly_matches_saved_v9_g9")
        )
        exact_candidate_report = all(
            state_comparisons[label][key]
            for label in ("j0", "j3")
            for key in (
                "exactly_matches_candidate_report_y_g",
                "exactly_matches_candidate_report_stored_T",
            )
        )
        exact_identity_report = all(
            state_comparisons[label]["exactly_matches_producer_equation_1"]
            for label in ("j0", "j3")
        )
        exact_paired_y_g = all(paired_state[key] == 0.0j for key in ("y", "g", "g_t"))
        replay_rows.append(
            {
                "column": col,
                "states": state_comparisons,
                "j3_minus_j0": {key: pair(value) for key, value in paired_state.items()},
                "j0_j3_y_g_stored_T_exact": exact_paired_y_g,
                "saved_v9_y_g_exact": exact_v9_y_g,
                "candidate_report_y_g_stored_T_exact": exact_candidate_report,
                "producer_equation_1_exact_for_both_states": exact_identity_report,
            }
        )
    if solves != {"bi": 4, "ri": 8, "getrs": 12}:
        raise ValueError(f"V11 independent checker expected 4 bi/8 ri/12 GETRS, got {solves}")
    producer = report.get("stage_accounting", {}).get("diagnostic_same_lu_getrs")
    if not isinstance(producer, Mapping) or any(producer.get(k) != v for k, v in (("bi_calls", 4), ("ri_calls", 8), ("getrs_calls", 12), ("expected_getrs_calls", 12))):
        raise ValueError("V11 producer GETRS accounting differs")
    exact_replay = all(
        row[key]
        for row in replay_rows
        for key in (
            "j0_j3_y_g_stored_T_exact",
            "saved_v9_y_g_exact",
            "candidate_report_y_g_stored_T_exact",
            "producer_equation_1_exact_for_both_states",
        )
    )
    return {
        "schema": "task41.p0.v11.selected_trace_star_saved_array_independent_check.v1",
        "check_completed": True,
        "candidate_passed": None,
        "scientific_qualified": False,
        "official_result": False,
        "formal_candidate_or_residual_gate_changed": False,
        "saved_arrays_recomputed": checked,
        "independent_checker_solver_accounting": {**solves, "build_and_audit_separate": True},
        "per_column_replays": replay_rows,
        "exact_reproduction_status": "EXACT" if exact_replay else "UNBOUND",
        "classification": "INDEPENDENT_SAVED_ARRAY_CHECK_COMPLETED",
    }



def _task41_v8_check_ordered_summary_closures(
    *,
    replay: Mapping[str, Any],
    expected_left_volume: complex,
    expected_left_full: complex,
    expected_closure_volume: complex,
    expected_closure_full: complex,
    comparisons: Mapping[str, Any] | None,
    role: str,
    label: str,
) -> dict[str, Any]:
    """Bind saved grouped-left values and candidate closures by meaning."""
    for report_key, expected in (
        ("v7_grouped_left_volume", expected_left_volume),
        ("v7_grouped_left_full", expected_left_full),
    ):
        _task41_v8_assert_close(
            _task41_v8_complex_pair(replay.get(report_key), report_key),
            expected,
            f"{label} {report_key}",
        )

    if role == "candidate":
        if not isinstance(comparisons, Mapping):
            raise ValueError(f"{label} candidate summary omits saved closure comparisons")
        for report_key, expected in (
            ("star_corrected_volume_closure", expected_closure_volume),
            ("star_corrected_full_closure", expected_closure_full),
        ):
            _task41_v8_assert_close(
                expected,
                _task41_v8_complex_pair(comparisons.get(report_key), report_key),
                f"{label} {report_key}",
            )
        closure_comparison = "MATCHED_SAVED_CANDIDATE_CORRECTED_CLOSURES"
    elif role == "reference":
        closure_comparison = "REFERENCE_CLOSURES_RECOMPUTED_NO_SAVED_REFERENCE_CLOSURE"
    else:
        raise ValueError(f"{label} has an unsupported ordered-summary role {role!r}")

    return {
        "v7_grouped_left_volume": [expected_left_volume.real, expected_left_volume.imag],
        "v7_grouped_left_full": [expected_left_full.real, expected_left_full.imag],
        "recomputed_closure_volume": [expected_closure_volume.real, expected_closure_volume.imag],
        "recomputed_closure_full": [expected_closure_full.real, expected_closure_full.imag],
        "closure_comparison": closure_comparison,
    }


def _task41_v8_lu_rhs_counterfactual(
    *,
    K: np.ndarray,
    J: np.ndarray,
    T: np.ndarray,
    b_i: np.ndarray,
    factor: tuple[np.ndarray, np.ndarray],
    selected_local_rows: np.ndarray,
    selected_coefficients: np.ndarray,
) -> dict[str, Any]:
    """Compare saved T @ b_i with -J @ solve(K, b_i) for one saved cell RHS."""
    from scipy.linalg import lu_solve

    counterfactual_started = time.perf_counter()
    K = np.asarray(K, dtype=np.complex128)
    J = np.asarray(J, dtype=np.complex128)
    T = np.asarray(T, dtype=np.complex128)
    rhs = np.asarray(b_i, dtype=np.complex128)
    rows = np.asarray(selected_local_rows, dtype=np.int64)
    coefficients = np.asarray(selected_coefficients, dtype=np.complex128)
    if (
        K.ndim != 2
        or K.shape[0] != K.shape[1]
        or J.ndim != 2
        or J.shape[1] != K.shape[0]
        or T.shape != J.shape
        or rhs.shape != (K.shape[0],)
        or rows.ndim != 1
        or coefficients.shape != rows.shape
        or rows.size == 0
        or np.any(rows < 0)
        or np.any(rows >= J.shape[0])
        or not all(np.isfinite(value).all() for value in (K, J, T, rhs, coefficients))
    ):
        raise ValueError("V8 saved RHS LU counterfactual inputs are malformed")
    solve_started = time.perf_counter()
    solution = lu_solve(factor, rhs, check_finite=True)
    solve_seconds = time.perf_counter() - solve_started
    residual = K @ solution - rhs
    residual_norm = float(np.linalg.norm(residual))
    rhs_norm = float(np.linalg.norm(rhs))
    solution_norm = float(np.linalg.norm(solution))
    backward_residual_scale = float(
        np.linalg.norm(K) * solution_norm + rhs_norm
    )
    old_vector = T @ rhs
    new_vector = -(J @ solution)
    old_projected = complex(np.vdot(coefficients, old_vector[rows]))
    new_projected = complex(np.vdot(coefficients, new_vector[rows]))
    if not np.isfinite(
        [
            residual_norm,
            rhs_norm,
            solution_norm,
            backward_residual_scale,
            old_projected.real,
            old_projected.imag,
            new_projected.real,
            new_projected.imag,
        ]
    ).all():
        raise ValueError("V8 saved RHS LU counterfactual produced non-finite values")
    delta = new_projected - old_projected
    return {
        "old_T_b_i_projected": [old_projected.real, old_projected.imag],
        "new_minus_J_solve_K_b_i_projected": [new_projected.real, new_projected.imag],
        "complex_signed_new_minus_old": [delta.real, delta.imag],
        "solve_residual_norm": residual_norm,
        "solve_residual_rhs_norm": rhs_norm,
        "solve_solution_norm": solution_norm,
        "solve_backward_residual_scale": backward_residual_scale,
        "solve_residual_relative_to_rhs": residual_norm
        / max(rhs_norm, np.finfo(np.float64).tiny),
        "solve_residual_backward_scaled": residual_norm
        / max(backward_residual_scale, 1.0),
        "solve_seconds": solve_seconds,
        "counterfactual_seconds": time.perf_counter() - counterfactual_started,
        "_solution_array": solution,
        "_residual_array": residual,
    }


def _task41_v8_lu_rhs_totals(
    *,
    native_volume_rhs: np.ndarray,
    selected_active_row: int,
    selected_original_row: int,
    selected_S_sum: complex,
    old_local_rhs_sum: complex,
    new_local_rhs_sum: complex,
) -> dict[str, Any]:
    """Combine two-cell RHS terms with the global volume RHS at its original row."""
    native = np.asarray(native_volume_rhs, dtype=np.complex128)
    if (
        native.ndim != 1
        or type(selected_active_row) is not int
        or type(selected_original_row) is not int
        or selected_active_row < 0
        or selected_original_row < 0
        or selected_original_row >= native.size
    ):
        raise ValueError("V8 local RHS totals have an invalid active/original row map")
    b_t = complex(native[selected_original_row])
    s_sum = complex(selected_S_sum)
    old_sum = complex(old_local_rhs_sum)
    new_sum = complex(new_local_rhs_sum)
    if not np.isfinite(
        [b_t.real, b_t.imag, s_sum.real, s_sum.imag, old_sum.real, old_sum.imag, new_sum.real, new_sum.imag]
    ).all():
        raise ValueError("V8 local RHS totals contain non-finite values")
    g_old = b_t + old_sum
    g_new = b_t + new_sum
    d_old = s_sum - g_old
    d_new = s_sum - g_new
    return {
        "selected_active_row": selected_active_row,
        "selected_original_row": selected_original_row,
        "original_b_t_added_once": [b_t.real, b_t.imag],
        "selected_S_sum": [s_sum.real, s_sum.imag],
        "g_old_b_t_plus_T_b_i": [g_old.real, g_old.imag],
        "g_new_b_t_plus_direct_minus_J_solve_K_b_i": [g_new.real, g_new.imag],
        "d_old_S_minus_g_old": [d_old.real, d_old.imag],
        "d_new_S_minus_g_new": [d_new.real, d_new.imag],
        "complex_signed_delta_g_new_minus_old": [
            (g_new - g_old).real,
            (g_new - g_old).imag,
        ],
        "complex_signed_delta_d_new_minus_old": [
            (d_new - d_old).real,
            (d_new - d_old).imag,
        ],
    }


def _task41_v9_wide_local_projection(
    matrix: np.ndarray,
    vector: np.ndarray,
    *,
    selected_local_rows: np.ndarray,
    selected_coefficients: np.ndarray,
) -> tuple[np.longdouble, np.longdouble]:
    """Re-evaluate a small saved local complex projection in longdouble."""

    A = np.asarray(matrix, dtype=np.complex128)
    x = np.asarray(vector, dtype=np.complex128)
    rows = np.asarray(selected_local_rows, dtype=np.int64)
    coefficients = np.asarray(selected_coefficients, dtype=np.complex128)
    if (
        A.ndim != 2
        or x.shape != (A.shape[1],)
        or rows.ndim != 1
        or coefficients.shape != rows.shape
        or not rows.size
        or np.any(rows < 0)
        or np.any(rows >= A.shape[0])
        or not all(np.isfinite(value).all() for value in (A, x, coefficients))
    ):
        raise ValueError("V9 wide local projection inputs are malformed")
    wide = np.longdouble
    xr = x.real.astype(wide)
    xi = x.imag.astype(wide)
    selected_A = A[rows, :]
    vr = np.sum(
        selected_A.real.astype(wide) * xr[None, :]
        - selected_A.imag.astype(wide) * xi[None, :],
        axis=1,
        dtype=wide,
    )
    vi = np.sum(
        selected_A.real.astype(wide) * xi[None, :]
        + selected_A.imag.astype(wide) * xr[None, :],
        axis=1,
        dtype=wide,
    )
    cr = coefficients.real.astype(wide)
    ci = coefficients.imag.astype(wide)
    projected_real = np.sum(cr * vr + ci * vi, dtype=wide)
    projected_imag = np.sum(cr * vi - ci * vr, dtype=wide)
    if not np.isfinite(projected_real) or not np.isfinite(projected_imag):
        raise ValueError("V9 wide local projection produced non-finite values")
    return projected_real, projected_imag


def _task41_v9_signed_local_identity(
    *,
    K: np.ndarray,
    J: np.ndarray,
    T: np.ndarray,
    b_i: np.ndarray,
    z: np.ndarray,
    selected_local_rows: np.ndarray,
    selected_coefficients: np.ndarray,
) -> dict[str, complex]:
    """Project the signed saved-LU identity using only selected trace rows."""

    K = np.asarray(K, dtype=np.complex128)
    J = np.asarray(J, dtype=np.complex128)
    T = np.asarray(T, dtype=np.complex128)
    rhs = np.asarray(b_i, dtype=np.complex128)
    solution = np.asarray(z, dtype=np.complex128)
    rows = np.asarray(selected_local_rows, dtype=np.int64)
    coefficients = np.asarray(selected_coefficients, dtype=np.complex128)
    if (
        K.ndim != 2
        or K.shape[0] != K.shape[1]
        or J.ndim != 2
        or J.shape[1] != K.shape[0]
        or T.shape != J.shape
        or rhs.shape != (K.shape[0],)
        or solution.shape != rhs.shape
        or rows.ndim != 1
        or coefficients.shape != rows.shape
        or rows.size == 0
        or np.any(rows < 0)
        or np.any(rows >= J.shape[0])
        or not all(
            np.isfinite(value).all()
            for value in (K, J, T, rhs, solution, coefficients)
        )
    ):
        raise ValueError("V9 signed saved-LU identity inputs are malformed")

    kz = K @ solution
    selected_J = J[rows, :]
    selected_T = T[rows, :]
    selected_tb = selected_T @ rhs
    selected_jz = selected_J @ solution
    selected_E_T = selected_J + selected_T @ K
    selected_rhs_j_tk = selected_E_T @ solution
    selected_reassociated_j_tk = selected_jz + selected_T @ kz
    selected_rhs_residual = selected_T @ (rhs - kz)

    def project(value: np.ndarray) -> complex:
        return complex(np.vdot(coefficients, value))

    projected_tb = project(selected_tb)
    projected_jz = project(selected_jz)
    projected_lhs = projected_tb + projected_jz
    projected_j_tk = project(selected_rhs_j_tk)
    projected_reassociated_j_tk = project(selected_reassociated_j_tk)
    projected_t_residual = project(selected_rhs_residual)
    projected_rhs = projected_j_tk + projected_t_residual
    values = (
        projected_tb,
        projected_jz,
        projected_lhs,
        projected_j_tk,
        projected_reassociated_j_tk,
        projected_t_residual,
        projected_rhs,
    )
    if not np.isfinite(
        [component for value in values for component in (value.real, value.imag)]
    ).all():
        raise ValueError("V9 signed saved-LU identity produced non-finite projections")
    return {
        "projected_T_b_i": projected_tb,
        "projected_J_z": projected_jz,
        "projected_signed_lhs": projected_lhs,
        "projected_(J+TK)_z": projected_j_tk,
        "projected_reassociated_Jz_plus_TKz": projected_reassociated_j_tk,
        "projection_reassociation_difference": (
            projected_reassociated_j_tk - projected_j_tk
        ),
        "projected_T_(b_i-Kz)": projected_t_residual,
        "projected_signed_rhs": projected_rhs,
        "projection_identity_remainder": projected_lhs - projected_rhs,
    }


def _task41_v9_wide_local_rhs_totals(
    *,
    native_volume_rhs_at_selected_row: complex,
    wide_s_sum: tuple[np.longdouble, np.longdouble],
    wide_old_local_rhs_sum: tuple[np.longdouble, np.longdouble],
    wide_new_local_rhs_sum: tuple[np.longdouble, np.longdouble],
) -> dict[str, list[float]]:
    b_t = complex(native_volume_rhs_at_selected_row)
    if not np.isfinite([b_t.real, b_t.imag]).all():
        raise ValueError("V9 wide local RHS totals have a non-finite native row")
    wide = np.longdouble
    btr, bti = wide(b_t.real), wide(b_t.imag)
    old_gr = btr + wide_old_local_rhs_sum[0]
    old_gi = bti + wide_old_local_rhs_sum[1]
    new_gr = btr + wide_new_local_rhs_sum[0]
    new_gi = bti + wide_new_local_rhs_sum[1]
    old_dr = wide_s_sum[0] - old_gr
    old_di = wide_s_sum[1] - old_gi
    new_dr = wide_s_sum[0] - new_gr
    new_di = wide_s_sum[1] - new_gi
    return {
        "wide_selected_S_sum": [float(wide_s_sum[0]), float(wide_s_sum[1])],
        "wide_g_old_b_t_plus_T_b_i": [float(old_gr), float(old_gi)],
        "wide_g_new_b_t_plus_direct_minus_J_solve_K_b_i": [
            float(new_gr), float(new_gi)
        ],
        "wide_d_old_S_minus_g_old": [float(old_dr), float(old_di)],
        "wide_d_new_S_minus_g_new": [float(new_dr), float(new_di)],
    }


def _task41_v9_wide_sum_complex(values: Sequence[complex]) -> tuple[np.longdouble, np.longdouble]:
    """Sum already-computed complex128 local contributions at wider precision."""

    wide = np.longdouble
    real = wide(0.0)
    imag = wide(0.0)
    for value in values:
        item = complex(value)
        if not np.isfinite([item.real, item.imag]).all():
            raise ValueError("V9 local contribution is non-finite")
        real += wide(item.real)
        imag += wide(item.imag)
    return real, imag


def _task41_v9_rhs_scatter_selected_row(
    target: np.ndarray,
    local_vector: np.ndarray,
    *,
    selected_local_rows: np.ndarray,
    selected_coefficients: np.ndarray,
) -> list[dict[str, Any]]:
    """Replay one selected active row of ``reduce_rhs`` in original-row order.

    The production reducer updates ``result[ids]`` once per original trace row.
    This helper keeps that update order for the selected active row instead of
    first collapsing a cell with ``vdot``.
    """

    result = np.asarray(target)
    vector = np.asarray(local_vector, dtype=np.complex128)
    rows = np.asarray(selected_local_rows, dtype=np.int64)
    coefficients = np.asarray(selected_coefficients, dtype=np.complex128)
    if (
        result.shape != (1,)
        or result.dtype != np.dtype(np.complex128)
        or vector.ndim != 1
        or rows.ndim != 1
        or not rows.size
        or coefficients.shape != rows.shape
        or np.any(rows < 0)
        or np.any(rows >= vector.size)
        or len(np.unique(rows)) != len(rows)
        or not all(np.isfinite(value).all() for value in (result, vector, coefficients))
    ):
        raise ValueError("V9 production RHS selected-row scatter inputs are malformed")
    coefficient_by_row = {
        int(row): np.complex128(coefficient)
        for row, coefficient in zip(rows, coefficients, strict=True)
    }
    contributions: list[dict[str, Any]] = []
    for row in range(vector.size):
        coefficient = coefficient_by_row.get(row)
        if coefficient is None:
            continue
        term = np.conjugate(coefficient) * vector[row]
        result[0] += term
        contributions.append(
            {
                "original_trace_position": row,
                "coefficient": [float(coefficient.real), float(coefficient.imag)],
                "term": [float(term.real), float(term.imag)],
                "accumulator_after": [float(result[0].real), float(result[0].imag)],
            }
        )
    return contributions


def _task41_v9_apply_cell_s_to_selected_active_row(
    local_action: np.ndarray,
    *,
    selected_local_rows: np.ndarray,
    selected_coefficients: np.ndarray,
) -> np.ndarray:
    """Apply one cell's actual sparse ``E.conjugate().T @ local_action``.

    Only the selected active column is needed by the local screen.  A CSR with
    that exact column preserves the sorted local-row order of the full
    ``cell.expansion`` used by ``P6CellCondensedAction._apply_array``.
    """

    from scipy import sparse

    vector = np.asarray(local_action, dtype=np.complex128)
    rows = np.asarray(selected_local_rows, dtype=np.int64)
    coefficients = np.asarray(selected_coefficients, dtype=np.complex128)
    if (
        vector.ndim != 1
        or rows.ndim != 1
        or not rows.size
        or coefficients.shape != rows.shape
        or np.any(rows < 0)
        or np.any(rows >= vector.size)
        or len(np.unique(rows)) != len(rows)
        or not all(np.isfinite(value).all() for value in (vector, coefficients))
    ):
        raise ValueError("V9 production S selected-column projection inputs are malformed")
    expansion_column = sparse.csr_matrix(
        (
            coefficients,
            (rows.astype(np.int32, copy=False), np.zeros(rows.size, dtype=np.int32)),
        ),
        shape=(vector.size, 1),
        dtype=np.complex128,
    )
    projected = np.asarray(
        expansion_column.conjugate().T @ vector, dtype=np.complex128
    ).reshape(-1)
    if projected.shape != (1,) or not np.isfinite(projected).all():
        raise ValueError("V9 production S selected-column projection is malformed")
    return projected


def _task41_v9_wide_precision_metadata() -> dict[str, Any]:
    """Describe actual NumPy mantissa widths without implying a zero error."""

    longdouble_info = np.finfo(np.longdouble)
    float64_info = np.finfo(np.float64)
    # ``nmant`` excludes the implicit leading bit for the IEEE formats used
    # here; report both that field and total significand bits explicitly.
    longdouble_bits = int(longdouble_info.nmant) + 1
    float64_bits = int(float64_info.nmant) + 1
    return {
        "dtype": str(np.dtype(np.longdouble)),
        "numpy_finfo_nmant_fraction_bits": int(longdouble_info.nmant),
        "significand_bits_including_leading_bit": longdouble_bits,
        "float64_significand_bits_including_leading_bit": float64_bits,
        "wider_than_float64": longdouble_bits > float64_bits,
        "wide_value_not_used_as_complex128_d_answer": True,
        "wide_delta_used_only_for_conservative_uncertainty": True,
    }


def _task41_v9_wide_final_combination_diagnostic(
    *,
    native_volume_rhs_at_selected_row: complex,
    production_s_terms: Sequence[complex],
    production_old_rhs_terms: Sequence[complex],
    production_new_rhs_terms: Sequence[complex],
    production_d_old: complex,
    production_d_new: complex,
) -> dict[str, Any]:
    """Compare wider final sums to production d before any float64 conversion."""

    wide = np.longdouble
    bt = complex(native_volume_rhs_at_selected_row)
    if not np.isfinite([bt.real, bt.imag]).all():
        raise ValueError("V9 wide final-combination diagnostic has a non-finite b_t")
    wide_s = _task41_v9_wide_sum_complex(production_s_terms)
    wide_old = _task41_v9_wide_sum_complex(production_old_rhs_terms)
    wide_new = _task41_v9_wide_sum_complex(production_new_rhs_terms)
    old_g = (wide(bt.real) + wide_old[0], wide(bt.imag) + wide_old[1])
    new_g = (wide(bt.real) + wide_new[0], wide(bt.imag) + wide_new[1])
    old_d = (wide_s[0] - old_g[0], wide_s[1] - old_g[1])
    new_d = (wide_s[0] - new_g[0], wide_s[1] - new_g[1])
    old_answer = complex(production_d_old)
    new_answer = complex(production_d_new)
    old_delta = np.hypot(
        old_d[0] - wide(old_answer.real), old_d[1] - wide(old_answer.imag)
    )
    new_delta = np.hypot(
        new_d[0] - wide(new_answer.real), new_d[1] - wide(new_answer.imag)
    )
    if not np.isfinite([old_delta, new_delta]).all():
        raise ValueError("V9 wide final-combination diagnostic is non-finite")
    return {
        "wide_d_T_longdouble_components": [str(old_d[0]), str(old_d[1])],
        "wide_d_LU_longdouble_components": [str(new_d[0]), str(new_d[1])],
        "absolute_wide_minus_production_d_T": float(old_delta),
        "absolute_wide_minus_production_d_LU": float(new_delta),
        "not_a_strict_error_bound": True,
        "not_used_as_complex128_d_answer": True,
    }


def task41_p0_v9_saved_star_screen(
    *,
    v8_report_path: Path,
    v8_report_sha256: str,
    v8_checker_result_path: Path,
    v8_checker_result_sha256: str,
    repo_root: Path,
) -> dict[str, Any]:
    """Screen the frozen two-cell V8 star using its saved LU and RHS evidence.

    This narrow consumer intentionally avoids the older V8 rechecker, which
    rebuilds four local factorizations. It reads only the two incident cells,
    their selected-row state inputs, and the already-saved V8 LU/pivot/z files.
    """

    from src.solvers.hcurl_assembly_time_condensation import (
        prepare_saved_lu_pivots_for_getrs,
        project_internal_rhs_same_lu,
    )

    repo_root = Path(repo_root).resolve(strict=True)
    results_root = (repo_root / "results").resolve()
    report_path = Path(v8_report_path).resolve(strict=True)
    checker_path = Path(v8_checker_result_path).resolve(strict=True)
    if (
        not report_path.is_relative_to(results_root)
        or not checker_path.is_relative_to(results_root)
        or v8_report_sha256 != TASK41_P0_V9_V8_REPORT_SHA256
        or v8_checker_result_sha256 != TASK41_P0_V9_V8_CHECKER_RESULT_SHA256
        or sha256_file(report_path) != v8_report_sha256
        or sha256_file(checker_path) != v8_checker_result_sha256
    ):
        raise ValueError("V9 saved-star input report path or frozen SHA-256 differs")
    report = _json_object(report_path, "V9 V8 selected-star report")
    checker = _json_object(checker_path, "V9 V8 saved checker result")
    mesh_check = checker.get("mesh_actual_exact_candidate_check")
    counterfactual = (
        mesh_check.get("local_rhs_lu_counterfactual")
        if isinstance(mesh_check, Mapping)
        else None
    )
    if (
        report.get("schema") != TASK41_P0_V8_SELECTED_TRACE_STAR_REPORT_SCHEMA
        or report.get("status") != "COMPLETED_SELECTED_TRACE_STAR_AUDIT"
        or report.get("geometry_policy") != "mesh_actual_exact"
        or report.get("raw_tensor_evaluator") != "actual_qmetric_blocked_gram"
        or report.get("consumer_source_sha")
        != TASK41_P0_V8_LEGACY_CONSUMER_SOURCE_SHA
        or report.get("consumer_contract_sha256")
        != TASK41_P0_V8_LEGACY_CONSUMER_CONTRACT_SHA256
        or checker.get("schema") != "task41.p0.b0.saved_evidence_audit.v1"
        or checker.get("status") != "COMPLETE"
        or not isinstance(mesh_check, Mapping)
        or mesh_check.get("check_completed") is not True
        or mesh_check.get("report_sha256_rechecked") != v8_report_sha256
        or not isinstance(counterfactual, Mapping)
        or counterfactual.get("schema")
        != "task41.p0.v8.local_rhs_lu_counterfactual.v1"
        or counterfactual.get("source_report_sha256_rechecked")
        != v8_report_sha256
        or counterfactual.get("new_strict_lu_factorization_count") != 4
        or counterfactual.get("direct_rhs_solve_count") != 8
    ):
        raise ValueError("V9 saved-star inputs do not match the frozen completed V8 evidence")

    selected = report.get("selected_trace_star_audit")
    if not isinstance(selected, Mapping):
        raise ValueError("V9 V8 report omits its selected trace-star section")
    metadata = selected.get("metadata")
    numeric_rows = selected.get("local_numeric_cell_identity_and_artifacts")
    p3 = selected.get("p3_production_row_replay")
    persisted = report.get("persisted_evidence_arrays")
    if (
        not isinstance(metadata, Mapping)
        or not isinstance(numeric_rows, list)
        or not isinstance(p3, Mapping)
        or not isinstance(persisted, list)
        or selected.get("selected_active_row") != 4_766_937
        or selected.get("selected_original_row") != 15_440_235
        or metadata.get("incident_cell_order") != [23_352, 23_493]
    ):
        raise ValueError("V9 V8 selected-row/cell identity differs from the frozen star")

    cells = (23_352, 23_493)
    roles = ("candidate", "reference")
    states = ("j0", "j3")
    numeric_by_cell = {
        row.get("cell_index"): row
        for row in numeric_rows
        if isinstance(row, Mapping) and row.get("cell_index") in cells
    }
    p3_rows_raw = p3.get("per_cell_signed_contributions")
    if not isinstance(p3_rows_raw, list):
        raise ValueError("V9 V8 selected-star P3 section omits incident cell rows")
    p3_by_cell = {
        row.get("cell_index"): row
        for row in p3_rows_raw
        if isinstance(row, Mapping) and row.get("cell_index") in cells
    }
    if set(numeric_by_cell) != set(cells) or set(p3_by_cell) != set(cells):
        raise ValueError("V9 V8 report lacks one of the two frozen incident cells")

    source_inventory: dict[str, Mapping[str, Any]] = {}
    for item in persisted:
        if not isinstance(item, Mapping) or not isinstance(item.get("name"), str):
            raise ValueError("V9 V8 saved-array inventory is malformed")
        name = str(item["name"])
        if name in source_inventory:
            raise ValueError(f"V9 V8 saved-array name is duplicated: {name}")
        source_inventory[name] = item
    checker_arrays_raw = counterfactual.get("array_artifacts")
    factorizations_raw = counterfactual.get("factorizations")
    if not isinstance(checker_arrays_raw, list) or not isinstance(factorizations_raw, list):
        raise ValueError("V9 V8 checker result omits its saved LU/RHS array inventory")
    checker_inventory: dict[str, Mapping[str, Any]] = {}
    for item in checker_arrays_raw:
        if not isinstance(item, Mapping) or not isinstance(item.get("name"), str):
            raise ValueError("V9 V8 checker array inventory is malformed")
        name = str(item["name"])
        if name in checker_inventory:
            raise ValueError(f"V9 V8 checker array name is duplicated: {name}")
        checker_inventory[name] = item

    source_cache: dict[str, np.ndarray] = {}
    checker_cache: dict[str, np.ndarray] = {}

    def load_array(
        ref: Any,
        *,
        inventory: Mapping[str, Mapping[str, Any]],
        cache: dict[str, np.ndarray],
        basis: Path,
        label: str,
        expected_dtype: str | None = None,
    ) -> np.ndarray:
        if not isinstance(ref, Mapping) or not isinstance(ref.get("name"), str):
            raise ValueError(f"V9 {label} omits its named array authorization")
        name = str(ref["name"])
        item = inventory.get(name)
        if not isinstance(item, Mapping):
            raise ValueError(f"V9 {label} is not in the fixed V8 array inventory: {name}")
        for field in ("name", "path", "sha256", "bytes", "dtype", "shape"):
            if ref.get(field) != item.get(field):
                raise ValueError(f"V9 {label} inventory identity differs at {field}: {name}")
        if name not in cache:
            raw_path = Path(str(item.get("path", "")))
            path = (raw_path if raw_path.is_absolute() else basis / raw_path).resolve(strict=True)
            if (
                not path.is_relative_to(basis.resolve())
                or not path.is_relative_to(results_root)
                or path.stat().st_size != item.get("bytes")
                or not isinstance(item.get("sha256"), str)
                or sha256_file(path) != item.get("sha256")
            ):
                raise ValueError(f"V9 {label} array path, size, or SHA-256 changed: {name}")
            array = np.load(path, mmap_mode="r", allow_pickle=False)
            if (
                list(array.shape) != item.get("shape")
                or str(array.dtype) != item.get("dtype")
                or (expected_dtype is not None and str(array.dtype) != expected_dtype)
                or array.dtype.kind not in "fciu"
                or not np.isfinite(array).all()
            ):
                raise ValueError(f"V9 {label} array shape, dtype, or values changed: {name}")
            cache[name] = array
        return cache[name]

    factor_by_key: dict[tuple[int, str], Mapping[str, Any]] = {}
    for factor in factorizations_raw:
        if not isinstance(factor, Mapping):
            raise ValueError("V9 V8 factorization record is malformed")
        key = (factor.get("cell_index"), factor.get("role"))
        if key in factor_by_key:
            raise ValueError(f"V9 V8 factorization record is duplicated: {key!r}")
        factor_by_key[key] = factor
    expected_factor_keys = {(cell, role) for cell in cells for role in roles}
    if set(factor_by_key) != expected_factor_keys:
        raise ValueError("V9 V8 saved LU inventory does not cover both cells and roles")

    case_rows = counterfactual.get("cases")
    if not isinstance(case_rows, list):
        raise ValueError("V9 V8 checker result omits the saved RHS case records")
    checker_case_by_key = {
        (item.get("role"), item.get("column"), item.get("state")): item
        for item in case_rows
        if isinstance(item, Mapping)
    }
    expected_case_keys = {
        (role, column, state)
        for role in roles
        for column in range(2)
        for state in states
    }
    if set(checker_case_by_key) != expected_case_keys:
        raise ValueError("V9 V8 checker RHS records do not cover both roles, columns, and states")

    numeric_data: dict[tuple[int, str], dict[str, Any]] = {}
    for cell in cells:
        numeric = numeric_by_cell[cell]
        interior = np.asarray(numeric.get("true_interior_positions"), dtype=np.int64)
        trace = np.asarray(numeric.get("trace_complement_positions"), dtype=np.int64)
        selected_rows = np.asarray(numeric.get("selected_local_trace_rows"), dtype=np.int64)
        coefficients = _task41_v8_complex_pairs(
            numeric.get("selected_trace_coefficients"),
            f"V9 cell {cell} selected trace coefficients",
        )
        if (
            interior.ndim != 1
            or trace.ndim != 1
            or selected_rows.ndim != 1
            or not selected_rows.size
            or coefficients.shape != selected_rows.shape
            or np.intersect1d(interior, trace).size
            or not np.array_equal(np.sort(np.r_[interior, trace]), np.arange(interior.size + trace.size))
            or np.any(selected_rows < 0)
            or np.any(selected_rows >= trace.size)
        ):
            raise ValueError(f"V9 cell {cell} selected local map is malformed")
        role_rows = numeric.get("roles")
        if not isinstance(role_rows, list):
            raise ValueError(f"V9 cell {cell} omits candidate/reference matrix artifacts")
        roles_by_name = {item.get("role"): item for item in role_rows if isinstance(item, Mapping)}
        if set(roles_by_name) != set(roles):
            raise ValueError(f"V9 cell {cell} role inventory differs")
        for role in roles:
            role_row = roles_by_name[role]
            artifacts = role_row.get("raw_oriented_RTS_artifacts")
            if not isinstance(artifacts, Mapping):
                raise ValueError(f"V9 cell {cell} {role} omits saved oriented blocks")
            tensor = load_array(
                artifacts.get("oriented_tensor"), inventory=source_inventory,
                cache=source_cache, basis=report_path.parent,
                label=f"cell {cell} {role} oriented tensor",
                expected_dtype="complex128",
            )
            T = load_array(
                artifacts.get("T"), inventory=source_inventory,
                cache=source_cache, basis=report_path.parent,
                label=f"cell {cell} {role} T",
                expected_dtype="complex128",
            )
            S = load_array(
                artifacts.get("S"), inventory=source_inventory,
                cache=source_cache, basis=report_path.parent,
                label=f"cell {cell} {role} S",
                expected_dtype="complex128",
            )
            if (
                tensor.shape != (interior.size + trace.size,) * 2
                or T.shape != (trace.size, interior.size)
                or S.shape != (trace.size, trace.size)
            ):
                raise ValueError(f"V9 cell {cell} {role} local matrix dimensions differ")
            K = np.asarray(tensor[np.ix_(interior, interior)], dtype=np.complex128)
            J = np.asarray(tensor[np.ix_(trace, interior)], dtype=np.complex128)
            factor_record = factor_by_key[(cell, role)]
            if (
                factor_record.get("factorization_identity")
                != "fresh _strict_local_lu(K) from saved oriented_tensor; reused for both columns and states"
                or factor_record.get("oriented_tensor_sha256")
                != artifacts["oriented_tensor"].get("sha256")
                or factor_record.get("saved_T_sha256") != artifacts["T"].get("sha256")
                or factor_record.get("K_sha256")
                != hashlib.sha256(np.ascontiguousarray(K).view(np.uint8)).hexdigest()
            ):
                raise ValueError(f"V9 cell {cell} {role} saved LU is not bound to its K/T/tensor")
            factor = load_array(
                factor_record.get("lu_factor_artifact"), inventory=checker_inventory,
                cache=checker_cache, basis=checker_path.parent,
                label=f"cell {cell} {role} saved LU",
                expected_dtype="complex128",
            )
            pivots = load_array(
                factor_record.get("owned_pivots_artifact"), inventory=checker_inventory,
                cache=checker_cache, basis=checker_path.parent,
                label=f"cell {cell} {role} saved pivots",
                expected_dtype="int32",
            )
            if factor.shape != K.shape or pivots.shape != (K.shape[0],):
                raise ValueError(f"V9 cell {cell} {role} saved LU layout differs")
            normalized_pivots = prepare_saved_lu_pivots_for_getrs(
                pivots, dimension=K.shape[0]
            )
            numeric_data[(cell, role)] = {
                "K": K,
                "J": J,
                "T": T,
                "S": S,
                "selected_rows": selected_rows,
                "coefficients": coefficients,
                "factor": (factor, normalized_pivots),
                "factor_record": factor_record,
                "tensor_sha256": artifacts["oriented_tensor"].get("sha256"),
                "T_sha256": artifacts["T"].get("sha256"),
            }

    p3_state_by_key: dict[tuple[int, int, str], Mapping[str, Any]] = {}
    for cell in cells:
        rows = p3_by_cell[cell].get("roles_and_states")
        if not isinstance(rows, list):
            raise ValueError(f"V9 cell {cell} omits its saved P3 state rows")
        for row in rows:
            if not isinstance(row, Mapping):
                raise ValueError(f"V9 cell {cell} P3 state row is malformed")
            key = (cell, row.get("column"), row.get("state"))
            if key in p3_state_by_key:
                raise ValueError(f"V9 cell {cell} P3 state row is duplicated: {key!r}")
            p3_state_by_key[key] = row
    expected_state_keys = {
        (cell, column, state)
        for cell in cells
        for column in range(2)
        for state in states
    }
    if set(p3_state_by_key) != expected_state_keys:
        raise ValueError("V9 V8 P3 states do not cover both cells, columns, and j0/j3")

    z_by_rhs: dict[tuple[int, str, int], np.ndarray] = {}
    correction_by_rhs: dict[tuple[int, str, int], np.ndarray] = {}
    rhs_by_pair: dict[tuple[int, str, int], np.ndarray] = {}
    trace_by_pair: dict[tuple[int, str, int], np.ndarray] = {}
    b_t_by_pair: dict[tuple[str, int], complex] = {}
    residual_checks: list[dict[str, Any]] = []
    local_cases: list[dict[str, Any]] = []
    original_path_checks = 0
    production_core_checks = 0
    paired_rhs_checks = 0
    paired_trace_checks = 0
    paired_b_t_checks = 0
    production_rhs_scatter_count = 0
    production_s_cell_projection_count = 0
    cached_correction_reuse_count = 0
    wide_precision = _task41_v9_wide_precision_metadata()
    for role in roles:
        for column in range(2):
            for state in states:
                ordinary_s_terms: list[complex] = []
                ordinary_old_terms: list[complex] = []
                ordinary_new_terms: list[complex] = []
                production_s_terms: list[complex] = []
                production_old_terms: list[complex] = []
                production_new_terms: list[complex] = []
                signed_identity_terms: list[complex] = []
                signed_projection_terms: list[complex] = []
                signed_identity_remainders: list[complex] = []
                native_b_t_values = [
                    _task41_v8_complex_pair(
                        p3_state_by_key[(cell, column, state)].get(
                            "native_volume_rhs_at_selected_original_row"
                        ),
                        "V9 original native b_t",
                    )
                    for cell in cells
                ]
                if any(value != native_b_t_values[0] for value in native_b_t_values[1:]):
                    raise ValueError(
                        "V9 V8 original native b_t differs across incident cells"
                    )
                b_t_for_row = native_b_t_values[0]
                b_t_pair_key = (role, column)
                if state == "j0":
                    b_t_by_pair[b_t_pair_key] = b_t_for_row
                elif b_t_by_pair.get(b_t_pair_key) != b_t_for_row:
                    raise ValueError("V9 paired j0/j3 selected original-row b_t changed")
                else:
                    paired_b_t_checks += 1
                # reduce_rhs writes the selected original b_t before entering
                # its cell/original-trace/MPC scatter loops.
                production_g_t = np.asarray([b_t_for_row], dtype=np.complex128)
                production_g_lu = np.asarray([b_t_for_row], dtype=np.complex128)
                # _apply_array initializes its result to zero, then adds one
                # sparse E^H local projection per cell in owner order.
                production_s = np.zeros(1, dtype=np.complex128)
                cell_output = []
                saved_checker_case = checker_case_by_key[(role, column, state)]
                saved_cell_terms = saved_checker_case.get("cell_terms")
                if not isinstance(saved_cell_terms, list) or len(saved_cell_terms) != len(cells):
                    raise ValueError("V9 V8 checker case omits the two saved local terms")
                checker_terms_by_cell = {
                    item.get("cell_index"): item
                    for item in saved_cell_terms
                    if isinstance(item, Mapping)
                }
                if set(checker_terms_by_cell) != set(cells):
                    raise ValueError("V9 V8 checker local terms do not bind the fixed cells")
                for cell in cells:
                    p3_state = p3_state_by_key[(cell, column, state)]
                    p3_roles = p3_state.get("roles")
                    if not isinstance(p3_roles, list):
                        raise ValueError(f"V9 cell {cell} omits candidate/reference P3 roles")
                    p3_role_by_name = {
                        item.get("role"): item for item in p3_roles if isinstance(item, Mapping)
                    }
                    if set(p3_role_by_name) != set(roles):
                        raise ValueError(f"V9 cell {cell} P3 roles differ")
                    p3_role = p3_role_by_name[role]
                    local_values = p3_role.get("local_values")
                    saved_row_terms = p3_role.get("selected_row_contributions")
                    if not isinstance(local_values, Mapping) or not isinstance(saved_row_terms, Mapping):
                        raise ValueError(f"V9 cell {cell} {role} omits original local RHS inputs")
                    b_i = load_array(
                        local_values.get("b_i"), inventory=source_inventory,
                        cache=source_cache, basis=report_path.parent,
                        label=f"cell {cell} {role} col{column} {state} b_i",
                        expected_dtype="complex128",
                    )
                    t_c = load_array(
                        local_values.get("t_c"), inventory=source_inventory,
                        cache=source_cache, basis=report_path.parent,
                        label=f"cell {cell} {role} col{column} {state} t_c",
                        expected_dtype="complex128",
                    )
                    local = numeric_data[(cell, role)]
                    K, J, T, S = local["K"], local["J"], local["T"], local["S"]
                    if b_i.shape != (K.shape[0],) or t_c.shape != (S.shape[1],):
                        raise ValueError(f"V9 cell {cell} {role} b_i/t_c layout differs")
                    rhs_key = (cell, role, column)
                    if state == "j0":
                        rhs_by_pair[rhs_key] = np.asarray(b_i, dtype=np.complex128).copy()
                        trace_by_pair[rhs_key] = np.asarray(t_c, dtype=np.complex128).copy()
                    else:
                        if not np.array_equal(b_i, rhs_by_pair.get(rhs_key)):
                            raise ValueError(f"V9 cell {cell} {role} paired j0/j3 b_i changed")
                        if not np.array_equal(t_c, trace_by_pair.get(rhs_key)):
                            raise ValueError(f"V9 cell {cell} {role} paired j0/j3 t_c changed")
                        paired_rhs_checks += 1
                        paired_trace_checks += 1
                    if state == "j0":
                        solution_ref_name = (
                            f"v8_lu_solve_cell{cell}_{role}_col{column}_solution"
                        )
                        residual_ref_name = (
                            f"v8_lu_solve_cell{cell}_{role}_col{column}_residual"
                        )
                        saved_solution = load_array(
                            checker_inventory.get(solution_ref_name),
                            inventory=checker_inventory, cache=checker_cache,
                            basis=checker_path.parent,
                            label=f"cell {cell} {role} col{column} saved z",
                            expected_dtype="complex128",
                        )
                        saved_residual = load_array(
                            checker_inventory.get(residual_ref_name),
                            inventory=checker_inventory, cache=checker_cache,
                            basis=checker_path.parent,
                            label=f"cell {cell} {role} col{column} saved residual",
                            expected_dtype="complex128",
                        )
                        if not np.array_equal(K @ saved_solution - b_i, saved_residual):
                            scale = max(float(np.linalg.norm(K) * np.linalg.norm(saved_solution) + np.linalg.norm(b_i)), 1.0)
                            if np.linalg.norm(K @ saved_solution - b_i - saved_residual) > 1.0e-13 * scale:
                                raise ValueError(f"V9 cell {cell} {role} saved z residual does not recompute")
                        solved, correction, core_timing = project_internal_rhs_same_lu(
                            local["factor"], J, b_i
                        )
                        if (
                            not isinstance(solved, np.ndarray)
                            or solved.shape != (K.shape[0],)
                            or solved.dtype != np.dtype(np.complex128)
                            or not np.isfinite(solved).all()
                            or not np.allclose(solved, saved_solution, rtol=1.0e-13, atol=1.0e-13)
                        ):
                            raise ValueError(f"V9 cell {cell} {role} production-core z differs from saved z")
                        independent_minus_jz = -(J @ solved)
                        if (
                            not isinstance(correction, np.ndarray)
                            or correction.shape != (J.shape[0],)
                            or correction.dtype != np.dtype(np.complex128)
                            or not np.isfinite(correction).all()
                            or not np.array_equal(correction, independent_minus_jz)
                        ):
                            raise ValueError(
                                f"V9 cell {cell} {role} production-core correction disagrees "
                                "with independent full -(J@z) shape/dtype/finite/sign/value check"
                            )
                        correction = np.asarray(correction, dtype=np.complex128).copy()
                        new_residual = K @ solved - b_i
                        saved_norm = float(np.linalg.norm(saved_residual))
                        new_norm = float(np.linalg.norm(new_residual))
                        saved_rhs_norm = float(np.linalg.norm(b_i))
                        new_rhs_norm = float(np.linalg.norm(b_i))
                        saved_rhs_relative = saved_norm / max(
                            saved_rhs_norm, np.finfo(np.float64).tiny
                        )
                        new_rhs_relative = new_norm / max(
                            new_rhs_norm, np.finfo(np.float64).tiny
                        )
                        scale = max(float(np.linalg.norm(K) * np.linalg.norm(solved) + np.linalg.norm(b_i)), 1.0)
                        saved_relative = saved_norm / scale
                        new_relative = new_norm / scale
                        if new_relative > saved_relative + 1.0e-13:
                            raise ValueError(f"V9 cell {cell} {role} production-core residual worsened")
                        z_by_rhs[rhs_key] = np.asarray(solved, dtype=np.complex128).copy()
                        correction_by_rhs[rhs_key] = correction
                        residual_checks.append(
                            {
                                "cell_index": cell,
                                "role": role,
                                "column": column,
                                "saved_z_matches_production_core": True,
                                "saved_residual_recomputed": True,
                                "saved_residual_absolute_norm": saved_norm,
                                "production_core_residual_absolute_norm": new_norm,
                                "saved_residual_relative_to_rhs": saved_rhs_relative,
                                "production_core_residual_relative_to_rhs": new_rhs_relative,
                                "saved_backward_relative_residual": saved_relative,
                                "production_core_backward_relative_residual": new_relative,
                                "backward_residual_scale": scale,
                                "production_correction_matches_independent_full_minus_Jz": True,
                                "correction_independent_max_abs_difference": float(
                                    np.max(np.abs(correction - independent_minus_jz), initial=0.0)
                                ),
                                "getrs_count": 1,
                                "getrs_seconds": core_timing["getrs_seconds"],
                            }
                        )
                        production_core_checks += 1
                    z = z_by_rhs.get(rhs_key)
                    correction = correction_by_rhs.get(rhs_key)
                    if z is None or correction is None:
                        raise ValueError(
                            f"V9 cell {cell} {role} paired state has no cached saved-LU z/correction"
                        )
                    selected_rows = local["selected_rows"]
                    coefficients = local["coefficients"]

                    # Keep all three full-vector matvecs.  V8's grouped replay
                    # uses its historical selected-row dot product below;
                    # the new gate consumes the returned production correction
                    # and production scatter order instead.
                    old_vector = T @ b_i
                    s_vector = S @ t_c
                    new_vector = -(J @ z)
                    if not np.array_equal(correction, new_vector):
                        raise ValueError(
                            f"V9 cell {cell} {role} cached correction changed from independent full -(J@z)"
                        )
                    old_projected = complex(
                        np.vdot(coefficients, old_vector[selected_rows])
                    )
                    s_projected = complex(
                        np.vdot(coefficients, s_vector[selected_rows])
                    )
                    new_projected = complex(
                        np.vdot(coefficients, new_vector[selected_rows])
                    )
                    rhs_old_scatter = _task41_v9_rhs_scatter_selected_row(
                        production_g_t,
                        old_vector,
                        selected_local_rows=selected_rows,
                        selected_coefficients=coefficients,
                    )
                    rhs_correction_scatter = _task41_v9_rhs_scatter_selected_row(
                        production_g_lu,
                        correction,
                        selected_local_rows=selected_rows,
                        selected_coefficients=coefficients,
                    )
                    s_cell_projection = _task41_v9_apply_cell_s_to_selected_active_row(
                        s_vector,
                        selected_local_rows=selected_rows,
                        selected_coefficients=coefficients,
                    )
                    production_s += s_cell_projection
                    production_s_cell_projection_count += 1
                    production_rhs_scatter_count += (
                        len(rhs_old_scatter) + len(rhs_correction_scatter)
                    )
                    production_old_terms.extend(
                        complex(*item["term"]) for item in rhs_old_scatter
                    )
                    production_new_terms.extend(
                        complex(*item["term"]) for item in rhs_correction_scatter
                    )
                    production_s_terms.append(complex(s_cell_projection[0]))
                    if state == "j3":
                        # The cached pair is consumed again for j3.  This count
                        # closes reuse without a second GETRS call.
                        cached_correction_reuse_count += 1

                    # This selected-row algebra is diagnostic-only. In
                    # particular, it must never supply a g/d/gate projection.
                    signed_identity = _task41_v9_signed_local_identity(
                        K=K,
                        J=J,
                        T=T,
                        b_i=b_i,
                        z=z,
                        selected_local_rows=selected_rows,
                        selected_coefficients=coefficients,
                    )
                    j_z_projected = -new_projected
                    selected_s_diagnostic = complex(
                        np.vdot(coefficients, S[selected_rows, :] @ t_c)
                    )
                    _task41_v8_assert_close(
                        _task41_v8_complex_pair(
                            saved_row_terms.get("local_reduced_rhs_T_b_i"),
                            "V8 local_reduced_rhs_T_b_i",
                        ),
                        old_projected,
                        f"V9 original T b_i row replay cell {cell} {role} col{column} {state}",
                    )
                    _task41_v8_assert_close(
                        _task41_v8_complex_pair(saved_row_terms.get("S_action"), "V8 S_action"),
                        s_projected,
                        f"V9 original S t row replay cell {cell} {role} col{column} {state}",
                    )
                    checker_term = checker_terms_by_cell[cell]
                    _task41_v8_assert_close(
                        _task41_v8_complex_pair(
                            checker_term.get("old_T_b_i_projected"), "V8 saved old projection"
                        ),
                        old_projected,
                        f"V9 V8 old RHS diagnostic replay cell {cell} {role} col{column} {state}",
                    )
                    _task41_v8_assert_close(
                        _task41_v8_complex_pair(
                            checker_term.get("new_minus_J_solve_K_b_i_projected"),
                            "V8 saved new projection",
                        ),
                        new_projected,
                        f"V9 V8 saved-LU projection replay cell {cell} {role} col{column} {state}",
                    )
                    original_path_checks += 3
                    ordinary_s_terms.append(s_projected)
                    ordinary_old_terms.append(old_projected)
                    ordinary_new_terms.append(new_projected)
                    signed_identity_terms.append(
                        signed_identity["projected_signed_lhs"]
                    )
                    signed_projection_terms.extend(
                        (
                            signed_identity["projected_T_b_i"],
                            signed_identity["projected_J_z"],
                        )
                    )
                    signed_identity_remainders.append(
                        signed_identity["projection_identity_remainder"]
                    )
                    wide_projection = {
                        "S_action": _task41_v9_wide_local_projection(
                            S, t_c, selected_local_rows=selected_rows,
                            selected_coefficients=coefficients,
                        ),
                        "T_b_i": _task41_v9_wide_local_projection(
                            T, b_i, selected_local_rows=selected_rows,
                            selected_coefficients=coefficients,
                        ),
                        "J_z": _task41_v9_wide_local_projection(
                            J, z, selected_local_rows=selected_rows,
                            selected_coefficients=coefficients,
                        ),
                    }
                    cell_output.append(
                        {
                            "cell_index": cell,
                            "s_complex128": [s_projected.real, s_projected.imag],
                            "production_apply_sparse_EH_S_t_selected_active_row": [
                                float(s_cell_projection[0].real),
                                float(s_cell_projection[0].imag),
                            ],
                            "production_reduce_rhs_T_b_i_original_trace_scatter": rhs_old_scatter,
                            "production_reduce_rhs_returned_correction_original_trace_scatter": rhs_correction_scatter,
                            "T_b_i_projected_complex128": [old_projected.real, old_projected.imag],
                            "J_z_projected_complex128": [j_z_projected.real, j_z_projected.imag],
                            "minus_J_z_projected_complex128": [new_projected.real, new_projected.imag],
                            "returned_correction_projected_complex128": [
                                complex(np.vdot(coefficients, correction[selected_rows])).real,
                                complex(np.vdot(coefficients, correction[selected_rows])).imag,
                            ],
                            "independent_full_minus_Jz_matches_returned_correction": True,
                            "correction_independent_max_abs_difference": float(
                                np.max(np.abs(correction - new_vector), initial=0.0)
                            ),
                            "selected_row_vs_full_matvec_projection_remainders": {
                                "E_H_T_b_i_selected_minus_full": [
                                    (
                                        signed_identity["projected_T_b_i"]
                                        - old_projected
                                    ).real,
                                    (
                                        signed_identity["projected_T_b_i"]
                                        - old_projected
                                    ).imag,
                                ],
                                "E_H_S_t_selected_minus_full": [
                                    (selected_s_diagnostic - s_projected).real,
                                    (selected_s_diagnostic - s_projected).imag,
                                ],
                                "E_H_J_z_selected_minus_full": [
                                    (signed_identity["projected_J_z"] - j_z_projected).real,
                                    (signed_identity["projected_J_z"] - j_z_projected).imag,
                                ],
                                "diagnostic_only_not_used_for_gate": True,
                            },
                            "signed_saved_lu_identity_projection": {
                                "formula": "T b_i + J z = (J + T K) z + T (b_i - K z)",
                                "E_H_T_b_i": [
                                    signed_identity["projected_T_b_i"].real,
                                    signed_identity["projected_T_b_i"].imag,
                                ],
                                "E_H_J_z": [
                                    signed_identity["projected_J_z"].real,
                                    signed_identity["projected_J_z"].imag,
                                ],
                                "E_H_signed_lhs": [
                                    signed_identity["projected_signed_lhs"].real,
                                    signed_identity["projected_signed_lhs"].imag,
                                ],
                                "E_H_(J+TK)_z": [
                                    signed_identity["projected_(J+TK)_z"].real,
                                    signed_identity["projected_(J+TK)_z"].imag,
                                ],
                                "E_H_reassociated_Jz_plus_TKz": [
                                    signed_identity[
                                        "projected_reassociated_Jz_plus_TKz"
                                    ].real,
                                    signed_identity[
                                        "projected_reassociated_Jz_plus_TKz"
                                    ].imag,
                                ],
                                "reassociation_difference": [
                                    signed_identity[
                                        "projection_reassociation_difference"
                                    ].real,
                                    signed_identity[
                                        "projection_reassociation_difference"
                                    ].imag,
                                ],
                                "E_H_T_(b_i-Kz)": [
                                    signed_identity["projected_T_(b_i-Kz)"].real,
                                    signed_identity["projected_T_(b_i-Kz)"].imag,
                                ],
                                "E_H_signed_rhs": [
                                    signed_identity["projected_signed_rhs"].real,
                                    signed_identity["projected_signed_rhs"].imag,
                                ],
                                "projection_identity_remainder": [
                                    signed_identity["projection_identity_remainder"].real,
                                    signed_identity["projection_identity_remainder"].imag,
                                ],
                                "diagnostic_only_not_used_for_gate": True,
                            },
                            "wide_local_projection_recompute_diagnostic": {
                                name: [float(value[0]), float(value[1])]
                                for name, value in wide_projection.items()
                            },
                            "local_projection_recompute_diagnostic_not_used_for_gate": True,
                        }
                    )
                # Preserve the V8 historical grouped calculation independently
                # for comparison. It is not the new candidate gate.
                v8_grouped_s = sum(ordinary_s_terms, 0.0 + 0.0j)
                v8_grouped_g_old = b_t_for_row + sum(
                    ordinary_old_terms, 0.0 + 0.0j
                )
                v8_grouped_g_new = b_t_for_row + sum(
                    ordinary_new_terms, 0.0 + 0.0j
                )
                v8_grouped_d_old = v8_grouped_s - v8_grouped_g_old
                v8_grouped_d_new = v8_grouped_s - v8_grouped_g_new

                # Gate values follow the actual production paths: reduce_rhs
                # starts from b_t then scatters each original trace row; apply
                # computes one full S@t_c and sparse E^H result per cell before
                # adding that vector to its active IDs.
                s_sum = complex(production_s[0])
                g_old = complex(production_g_t[0])
                g_new = complex(production_g_lu[0])
                d_old = s_sum - g_old
                d_new = s_sum - g_new
                direct_delta_d = d_new - d_old
                measured_old_order_delta = abs(d_old - v8_grouped_d_old)
                measured_new_order_delta = abs(d_new - v8_grouped_d_new)
                naive_signed_projection_sum = sum(signed_identity_terms, 0.0 + 0.0j)
                accurate_signed_projection_sum = complex(
                    fsum(value.real for value in signed_projection_terms),
                    fsum(value.imag for value in signed_projection_terms),
                )
                fpu_remainder = direct_delta_d - accurate_signed_projection_sum
                projection_identity_remainder_sum = sum(
                    signed_identity_remainders, 0.0 + 0.0j
                )
                wide_totals = _task41_v9_wide_local_rhs_totals(
                    native_volume_rhs_at_selected_row=b_t_for_row,
                    wide_s_sum=_task41_v9_wide_sum_complex(production_s_terms),
                    wide_old_local_rhs_sum=_task41_v9_wide_sum_complex(production_old_terms),
                    wide_new_local_rhs_sum=_task41_v9_wide_sum_complex(production_new_terms),
                )
                if wide_precision["wider_than_float64"]:
                    wide_final_diagnostic = _task41_v9_wide_final_combination_diagnostic(
                        native_volume_rhs_at_selected_row=b_t_for_row,
                        production_s_terms=production_s_terms,
                        production_old_rhs_terms=production_old_terms,
                        production_new_rhs_terms=production_new_terms,
                        production_d_old=d_old,
                        production_d_new=d_new,
                    )
                    wide_old_final_difference = wide_final_diagnostic[
                        "absolute_wide_minus_production_d_T"
                    ]
                    wide_new_final_difference = wide_final_diagnostic[
                        "absolute_wide_minus_production_d_LU"
                    ]
                else:
                    # Do not present float64-as-longdouble equality as zero
                    # uncertainty when the platform has no additional bits.
                    wide_totals = {name: None for name in wide_totals}
                    wide_old_final_difference = None
                    wide_new_final_difference = None
                    wide_final_diagnostic = None
                local_cases.append(
                    {
                        "role": role,
                        "column": column,
                        "state": state,
                        "selected_original_row": int(selected["selected_original_row"]),
                        "frozen_D": float(TASK41_P0_V5_FROZEN_DENOMINATORS[column]),
                        "original_b_t_added_once": [b_t_for_row.real, b_t_for_row.imag],
                        "s_complex128": [s_sum.real, s_sum.imag],
                        "g_T_complex128": [g_old.real, g_old.imag],
                        "g_LU_complex128": [g_new.real, g_new.imag],
                        "d_T_complex128": [d_old.real, d_old.imag],
                        "d_LU_complex128": [d_new.real, d_new.imag],
                        "production_order": {
                            "rhs": "b_t first; then incident cells in [23352,23493] order; within each cell original_trace row order with MPC coefficient applied per row using +=",
                            "S": "full S@t_c per cell; sparse expansion.conjugate().T @ local_action; then result[cell.active_ids] += in incident-cell order",
                            "candidate_gate_uses_returned_correction": True,
                        },
                        "v8_grouped_replay": {
                            "s_complex128": [v8_grouped_s.real, v8_grouped_s.imag],
                            "g_T_complex128": [v8_grouped_g_old.real, v8_grouped_g_old.imag],
                            "g_LU_complex128": [v8_grouped_g_new.real, v8_grouped_g_new.imag],
                            "d_T_complex128": [v8_grouped_d_old.real, v8_grouped_d_old.imag],
                            "d_LU_complex128": [v8_grouped_d_new.real, v8_grouped_d_new.imag],
                            "preserved_for_historical_V8_comparison": True,
                        },
                        "measured_last_combination_order_delta": {
                            "v8_grouped_vs_production_d_T": measured_old_order_delta,
                            "v8_grouped_vs_production_d_LU": measured_new_order_delta,
                            "wide_vs_production_d_T": wide_old_final_difference,
                            "wide_vs_production_d_LU": wide_new_final_difference,
                            "conservative_max_d_T": (
                                max(measured_old_order_delta, wide_old_final_difference)
                                if wide_old_final_difference is not None
                                else None
                            ),
                            "conservative_max_d_LU": (
                                max(measured_new_order_delta, wide_new_final_difference)
                                if wide_new_final_difference is not None
                                else None
                            ),
                            "method": "record V8 grouped versus production-order complex128 difference and wide versus production-order diagnostic separately; use their maximum per old/new d only when longdouble is wider",
                            "wide_comparison_available": bool(
                                wide_precision["wider_than_float64"]
                            ),
                            "wide_is_not_a_strict_error_bound": True,
                            "used_for_candidate_gate": bool(
                                wide_precision["wider_than_float64"]
                            ),
                        },
                        "wide_final_combination_diagnostic": {
                            "precision": wide_precision,
                            "available": bool(wide_precision["wider_than_float64"]),
                            "absolute_wide_minus_production_d_T": wide_old_final_difference,
                            "absolute_wide_minus_production_d_LU": wide_new_final_difference,
                            "wide_d_T_longdouble_components": (
                                None
                                if wide_final_diagnostic is None
                                else wide_final_diagnostic[
                                    "wide_d_T_longdouble_components"
                                ]
                            ),
                            "wide_d_LU_longdouble_components": (
                                None
                                if wide_final_diagnostic is None
                                else wide_final_diagnostic[
                                    "wide_d_LU_longdouble_components"
                                ]
                            ),
                            "not_a_strict_error_bound": True,
                            "used_only_in_conservative_uncertainty_estimate": bool(
                                wide_precision["wider_than_float64"]
                            ),
                            "not_used_as_complex128_d_answer": True,
                        },
                        "signed_d_LU_minus_d_T_identity_diagnostic": {
                            "formula": "d_LU - d_T = sum_cells E^H(T b_i + J z); b_t cancels after being added once to each g",
                            "signed_cell_projection_sum_complex128": [
                                naive_signed_projection_sum.real,
                                naive_signed_projection_sum.imag,
                            ],
                            "accurate_sum_of_rounded_signed_E_H_terms": [
                                accurate_signed_projection_sum.real,
                                accurate_signed_projection_sum.imag,
                            ],
                            "signed_E_H_projection_term_count": len(
                                signed_projection_terms
                            ),
                            "direct_d_LU_minus_d_T_complex128": [
                                direct_delta_d.real,
                                direct_delta_d.imag,
                            ],
                            "fpu_remainder_direct_minus_accurate_projection_sum": [
                                fpu_remainder.real,
                                fpu_remainder.imag,
                            ],
                            "sum_of_cell_projection_identity_remainders": [
                                projection_identity_remainder_sum.real,
                                projection_identity_remainder_sum.imag,
                            ],
                            "diagnostic_only_not_used_for_gate": True,
                        },
                        **wide_totals,
                        "production_order_accumulators": {
                            "reduce_rhs_g_T": [float(g_old.real), float(g_old.imag)],
                            "reduce_rhs_g_LU_from_returned_correction": [
                                float(g_new.real), float(g_new.imag)
                            ],
                            "apply_S_selected_active_row": [
                                float(s_sum.real), float(s_sum.imag)
                            ],
                        },
                        "cell_terms": cell_output,
                    }
                )

    old_checker_cases_by_key = {
        (item["role"], item["column"], item["state"]): item
        for item in counterfactual.get("cases", [])
    }
    for item in local_cases:
        old_case = old_checker_cases_by_key[
            (item["role"], item["column"], item["state"])
        ]
        _task41_v8_assert_close(
            _task41_v8_complex_pair(old_case.get("d_old_S_minus_g_old"), "V8 d_T"),
            complex(*item["v8_grouped_replay"]["d_T_complex128"]),
            f"V9 original candidate/reference d_T replay {item['role']} col{item['column']} {item['state']}",
        )
        _task41_v8_assert_close(
            _task41_v8_complex_pair(old_case.get("d_new_S_minus_g_new"), "V8 d_LU"),
            complex(*item["v8_grouped_replay"]["d_LU_complex128"]),
            f"V9 saved-LU d_LU replay {item['role']} col{item['column']} {item['state']}",
        )
        original_path_checks += 2

    classified = _task41_v9_classify_candidate_self_d(
        [
            {
                "role": item["role"],
                "column": item["column"],
                "state": item["state"],
                "d_old_S_minus_g_old": item["d_T_complex128"],
                "d_new_S_minus_g_new": item["d_LU_complex128"],
                "last_combination_uncertainty_old": item[
                    "measured_last_combination_order_delta"
                ]["conservative_max_d_T"],
                "last_combination_uncertainty_new": item[
                    "measured_last_combination_order_delta"
                ]["conservative_max_d_LU"],
                "production_vs_v8_grouped_delta_old": item[
                    "measured_last_combination_order_delta"
                ]["v8_grouped_vs_production_d_T"],
                "production_vs_v8_grouped_delta_new": item[
                    "measured_last_combination_order_delta"
                ]["v8_grouped_vs_production_d_LU"],
                "wide_vs_production_delta_old": item[
                    "measured_last_combination_order_delta"
                ]["wide_vs_production_d_T"],
                "wide_vs_production_delta_new": item[
                    "measured_last_combination_order_delta"
                ]["wide_vs_production_d_LU"],
                "wide_comparison_available": item[
                    "measured_last_combination_order_delta"
                ]["wide_comparison_available"],
                "frozen_D": item["frozen_D"],
                "wide_d_old_S_minus_g_old": item["wide_d_old_S_minus_g_old"],
                "wide_d_new_S_minus_g_new": item["wide_d_new_S_minus_g_new"],
            }
            for item in local_cases
        ],
        identity_replay_closed=(
            original_path_checks
            == len(roles) * 2 * len(states) * len(cells) * 3
            + len(roles) * 2 * len(states) * 2
        ),
        production_core_replay_closed=(
            production_core_checks == len(cells) * len(roles) * 2
            and all(
                item["saved_z_matches_production_core"]
                and item["saved_residual_recomputed"]
                and item["production_core_backward_relative_residual"]
                <= item["saved_backward_relative_residual"] + 1.0e-13
                and item["production_correction_matches_independent_full_minus_Jz"]
                and item["correction_independent_max_abs_difference"] == 0.0
                and item["getrs_count"] == 1
                for item in residual_checks
            )
            and cached_correction_reuse_count == len(cells) * len(roles) * 2
            and paired_rhs_checks == len(cells) * len(roles) * 2
            and paired_trace_checks == len(cells) * len(roles) * 2
            and paired_b_t_checks == len(roles) * 2
            and production_s_cell_projection_count
            == len(cells) * len(roles) * 2 * len(states)
        ),
    )
    gap_diagnostics = []
    cases_by_key = {
        (item["role"], item["column"], item["state"]): item
        for item in local_cases
    }
    for column in range(2):
        for state in states:
            candidate = cases_by_key[("candidate", column, state)]
            reference = cases_by_key[("reference", column, state)]
            old_gap = np.asarray(candidate["g_T_complex128"]) - np.asarray(reference["g_T_complex128"])
            new_gap = np.asarray(candidate["g_LU_complex128"]) - np.asarray(reference["g_LU_complex128"])
            gap_diagnostics.append(
                {
                    "column": column,
                    "state": state,
                    "candidate_minus_reference_g_T": old_gap.tolist(),
                    "candidate_minus_reference_g_LU": new_gap.tolist(),
                    "diagnostic_only_not_candidate_gate": True,
                }
            )
    return {
        **classified,
        "schema": "task41.p0.v9.saved_star_screen.v1",
        "input_identity": {
            "v8_report_sha256": v8_report_sha256,
            "v8_checker_result_sha256": v8_checker_result_sha256,
            "selected_active_row": selected["selected_active_row"],
            "selected_original_row": selected["selected_original_row"],
            "incident_cells": list(cells),
            "loaded_source_array_count": len(source_cache),
            "loaded_saved_lu_rhs_array_count": len(checker_cache),
        },
        "replay_checks": {
            "original_s_and_T_b_i_reproduced_from_saved_V8_arrays": True,
            "old_original_path_and_V8_d_replayed_check_count": original_path_checks,
            "saved_z_and_residual_recomputed_with_shared_production_core": True,
            "independent_Kz_minus_b_i_and_no_deterioration_check_count": production_core_checks,
            "production_core_GETRS_count": production_core_checks,
            "production_core_correction_cached_and_consumed_by_gate": True,
            "cached_correction_j3_reuse_count_without_extra_GETRS": cached_correction_reuse_count,
            "paired_j0_j3_b_i_check_count": paired_rhs_checks,
            "paired_j0_j3_t_c_check_count": paired_trace_checks,
            "paired_j0_j3_b_t_check_count": paired_b_t_checks,
            "production_reduce_rhs_original_trace_scatter_contribution_count": production_rhs_scatter_count,
            "production_apply_sparse_EH_cell_projection_count": production_s_cell_projection_count,
            "production_reduce_rhs_and_apply_orders_replayed_separately": True,
            "v8_grouped_historical_replay_retained_and_compared": True,
            "measured_production_vs_v8_grouped_order_delta_used_for_gate": True,
            "wide_local_projection_recompute_is_diagnostic_only": True,
            "wide_final_combination_difference_is_diagnostic_only": True,
            "wide_vs_production_difference_used_only_in_conservative_uncertainty": True,
            "wide_arithmetic_not_used_as_d_answer_or_strict_error_bound": True,
            "signed_saved_lu_identity_uses_selected_trace_rows_and_is_diagnostic_only": True,
            "signed_d_lu_minus_d_t_fpu_remainder_is_diagnostic_only": True,
        },
        "wide_precision": wide_precision,
        "candidate_reference_gap_diagnostics": gap_diagnostics,
        "candidate_and_reference_recomputed_s_g_d": local_cases,
        "saved_lu_residual_checks": residual_checks,
    }


def check_task41_p0_b0_v9_saved_star_screen(
    *,
    contract_path: Path,
    contract_sha256: str,
    v8_report_path: Path,
    v8_report_sha256: str,
    v8_checker_result_path: Path,
    v8_checker_result_sha256: str,
    output_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    """Run and persist the V9 local screen under its frozen B0 contract."""

    repo_root = Path(repo_root).resolve(strict=True)
    contract_file = Path(contract_path).resolve(strict=True)
    output_file = Path(output_path).resolve()
    contract, actual_contract_sha = require_task41_p0_contract(
        contract_file,
        expected_sha256=contract_sha256,
        current_root=repo_root,
        require_clean_source=True,
        check_current_source=True,
        case_id="B0",
    )
    from src.runners.task41_p0_contract import (
        TASK41_B0_V9_INTERNAL_RHS_STRATEGY,
        TASK41_B0_V9_WINDOW_RELATIVE,
    )

    if (
        contract.get("numerical_strategy", {}).get("internal_rhs_strategy")
        != TASK41_B0_V9_INTERNAL_RHS_STRATEGY
        or contract.get("window", {}).get("path") != str(TASK41_B0_V9_WINDOW_RELATIVE)
    ):
        raise ValueError("V9 saved-star screen requires the explicit V9 B0 window and strategy")
    results_root = (repo_root / "results").resolve()
    if not output_file.is_relative_to(results_root):
        raise ValueError("V9 saved-star screen output must be inside repository results")
    screen = task41_p0_v9_saved_star_screen(
        v8_report_path=v8_report_path,
        v8_report_sha256=v8_report_sha256,
        v8_checker_result_path=v8_checker_result_path,
        v8_checker_result_sha256=v8_checker_result_sha256,
        repo_root=repo_root,
    )
    payload = {
        "schema": "task41.p0.b0.v9.saved_star_screen_result.v1",
        "status": screen["status"],
        "screen_completed": True,
        "local_candidate_ready": screen["status"] == "LOCAL_CANDIDATE_READY",
        "official_result": False,
        "task_id": contract["task_id"],
        "run_id": contract["case"]["run_id"],
        "source_sha": contract["source"]["sha"],
        "contract_path": str(contract_file),
        "contract_sha256": actual_contract_sha,
        "window_path": contract["window"]["path"],
        "window_sha256": contract["window"]["sha256"],
        "saved_star_screen": screen,
        "raw_evidence_retained": True,
    }
    if output_file.exists():
        raise ValueError("V9 saved-star screen output already exists; refusing to overwrite it")
    output_file.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{output_file.name}.", suffix=".tmp", dir=output_file.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, output_file)
        except FileExistsError as exc:
            raise ValueError("V9 saved-star screen output appeared concurrently") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return payload


def _task41_v9_classify_candidate_self_d(
    cases: list[Mapping[str, Any]],
    *,
    identity_replay_closed: bool,
    production_core_replay_closed: bool,
) -> dict[str, Any]:
    """Gate candidate-own d improvement after the measured last sum only."""

    expected = {
        (role, column, state)
        for role in ("candidate", "reference")
        for column in range(2)
        for state in ("j0", "j3")
    }
    by_key: dict[tuple[str, int, str], Mapping[str, Any]] = {}
    for item in cases:
        if not isinstance(item, Mapping):
            raise ValueError("V9 saved-star d cases must be mappings")
        key = (item.get("role"), item.get("column"), item.get("state"))
        if key in by_key:
            raise ValueError(f"V9 saved-star d case is duplicated: {key!r}")
        by_key[key] = item
    if set(by_key) != expected:
        raise ValueError("V9 saved-star d cases must bind both roles, columns, and states")

    result_cases = []
    candidate_by_column: dict[int, list[dict[str, Any]]] = {0: [], 1: []}
    for role, column, state in sorted(expected):
        item = by_key[(role, column, state)]
        old = _task41_v8_complex_pair(item.get("d_old_S_minus_g_old"), "old d")
        new = _task41_v8_complex_pair(item.get("d_new_S_minus_g_new"), "new d")
        raw_wide_old = item.get("wide_d_old_S_minus_g_old")
        raw_wide_new = item.get("wide_d_new_S_minus_g_new")
        wide_old = (
            None
            if raw_wide_old is None
            else _task41_v8_complex_pair(raw_wide_old, "wide old d")
        )
        wide_new = (
            None
            if raw_wide_new is None
            else _task41_v8_complex_pair(raw_wide_new, "wide new d")
        )
        grouped_delta_old = item.get("production_vs_v8_grouped_delta_old")
        grouped_delta_new = item.get("production_vs_v8_grouped_delta_new")
        wide_delta_old = item.get("wide_vs_production_delta_old")
        wide_delta_new = item.get("wide_vs_production_delta_new")
        wide_comparison_available = item.get("wide_comparison_available") is True
        if (
            isinstance(grouped_delta_old, bool)
            or not isinstance(grouped_delta_old, (int, float))
            or not np.isfinite(grouped_delta_old)
            or grouped_delta_old < 0.0
            or isinstance(grouped_delta_new, bool)
            or not isinstance(grouped_delta_new, (int, float))
            or not np.isfinite(grouped_delta_new)
            or grouped_delta_new < 0.0
        ):
            raise ValueError("V9 V8-grouped/production deltas must be finite and nonnegative")
        if wide_comparison_available:
            if (
                wide_old is None
                or wide_new is None
                or isinstance(wide_delta_old, bool)
                or not isinstance(wide_delta_old, (int, float))
                or not np.isfinite(wide_delta_old)
                or wide_delta_old < 0.0
                or isinstance(wide_delta_new, bool)
                or not isinstance(wide_delta_new, (int, float))
                or not np.isfinite(wide_delta_new)
                or wide_delta_new < 0.0
            ):
                raise ValueError(
                    "V9 wider-longdouble comparison is missing finite production deltas"
                )
            uncertainty_old = max(grouped_delta_old, wide_delta_old)
            uncertainty_new = max(grouped_delta_new, wide_delta_new)
        else:
            # Missing extra precision is not treated as a measured zero delta.
            uncertainty_old = None
            uncertainty_new = None
        frozen_denominator = item.get("frozen_D")
        if frozen_denominator != TASK41_P0_V5_FROZEN_DENOMINATORS[column]:
            raise ValueError(f"V9 saved-star frozen D changed for column {column}")
        improvement_margin = (
            None
            if uncertainty_old is None or uncertainty_new is None
            else abs(old) - abs(new) - uncertainty_old - uncertainty_new
        )
        entry = {
            "role": role,
            "column": column,
            "state": state,
            "d_old": [old.real, old.imag],
            "d_new": [new.real, new.imag],
            "wide_d_old_diagnostic_only": (
                None if wide_old is None else [wide_old.real, wide_old.imag]
            ),
            "wide_d_new_diagnostic_only": (
                None if wide_new is None else [wide_new.real, wide_new.imag]
            ),
            "wide_comparison_available": wide_comparison_available,
            "production_vs_v8_grouped_delta_old": grouped_delta_old,
            "production_vs_v8_grouped_delta_new": grouped_delta_new,
            "wide_vs_production_delta_old_diagnostic_only": wide_delta_old,
            "wide_vs_production_delta_new_diagnostic_only": wide_delta_new,
            "last_combination_uncertainty_old": uncertainty_old,
            "last_combination_uncertainty_new": uncertainty_new,
            "last_combination_uncertainty_source": (
                "maximum of measured V8-grouped/production and wider-longdouble/production d differences"
            ),
            "old_absolute_d": abs(old),
            "new_absolute_d": abs(new),
            "frozen_D": frozen_denominator,
            "old_frozen_D_relative": abs(old) / frozen_denominator,
            "new_frozen_D_relative": abs(new) / frozen_denominator,
            "improvement_beyond_last_combination_uncertainty": (
                improvement_margin is not None and improvement_margin > 0.0
            ),
            "improvement_margin_after_uncertainty": improvement_margin,
        }
        result_cases.append(entry)
        if role == "candidate":
            candidate_by_column[column].append(entry)
    column_gates = [
        {
            "column": column,
            "states": [item["state"] for item in candidate_by_column[column]],
            "evaluable": len(candidate_by_column[column]) == 2
            and all(item["wide_comparison_available"] for item in candidate_by_column[column]),
            "passed": len(candidate_by_column[column]) == 2
            and all(item["wide_comparison_available"] for item in candidate_by_column[column])
            and all(
                item["improvement_beyond_last_combination_uncertainty"]
                for item in candidate_by_column[column]
            ),
        }
        for column in range(2)
    ]
    candidate_gate_evaluable = all(item["evaluable"] for item in column_gates)
    passed = (
        identity_replay_closed
        and production_core_replay_closed
        and all(item["passed"] for item in column_gates)
    )
    return {
        "schema": "task41.p0.v9.saved_star_candidate_self_d_gate.v1",
        "status": "LOCAL_CANDIDATE_READY" if passed else "LOCAL_CANDIDATE_REJECTED",
        "identity_replay_closed": bool(identity_replay_closed),
        "production_core_replay_closed": bool(production_core_replay_closed),
        "candidate_gate_evaluable": candidate_gate_evaluable,
        "candidate_gate_blockers": (
            []
            if candidate_gate_evaluable
            else [
                "longdouble does not provide wider precision, so wide-vs-production delta is not evaluable"
            ]
        ),
        "candidate_gate_requires_both_columns_and_paired_states": True,
        "candidate_column_gates": column_gates,
        "candidate_and_reference_own_d": result_cases,
        "method": (
            "rebuild production-order s, g_T, g_LU and d from saved two-cell terms; "
            "compare each candidate-own |d| reduction after subtracting the larger "
            "of the measured V8-grouped/production and wider-longdouble/production "
            "d differences; wide math never replaces the complex128 answer and is "
            "not a strict error bound; platforms without wider longdouble are not "
            "eligible for READY; reference-own d is reported without using the "
            "candidate-reference gap as the gate"
        ),
    }


def _task41_v8_local_matrix_defect_diagnostic(
    *,
    tensor: np.ndarray,
    interior_positions: np.ndarray,
    trace_positions: np.ndarray,
    R: np.ndarray,
    T: np.ndarray,
    S: np.ndarray,
) -> dict[str, Any]:
    """Measure the four saved elimination defects without imposing a new gate."""
    block = np.asarray(tensor, dtype=np.complex128)
    interior = np.asarray(interior_positions, dtype=np.int64)
    trace = np.asarray(trace_positions, dtype=np.int64)
    R = np.asarray(R, dtype=np.complex128)
    T = np.asarray(T, dtype=np.complex128)
    S = np.asarray(S, dtype=np.complex128)
    dimension = block.shape[0] if block.ndim == 2 else -1
    if (
        block.ndim != 2
        or block.shape != (dimension, dimension)
        or not np.array_equal(
            np.sort(np.concatenate((interior, trace))), np.arange(dimension)
        )
    ):
        raise ValueError("V8 local tensor partition is malformed")
    K = block[np.ix_(interior, interior)]
    G = block[np.ix_(interior, trace)]
    J = block[np.ix_(trace, interior)]
    L = block[np.ix_(trace, trace)]
    if (
        R.shape != G.shape
        or T.shape != J.shape
        or S.shape != L.shape
        or any(not np.isfinite(value).all() for value in (K, G, J, L, R, T, S))
    ):
        raise ValueError("V8 saved local matrix layouts or values are malformed")
    E_R = K @ R + G
    E_T = J + T @ K
    C_S = S - L - J @ R
    E_S = S - L - T @ G
    identity_rhs = C_S + E_T @ R - T @ E_R
    identity_residual = E_S - identity_rhs

    def metrics(values: np.ndarray) -> dict[str, float]:
        matrix = np.asarray(values, dtype=np.complex128)
        return {
            "frobenius": float(np.linalg.norm(matrix.ravel())),
            "max_abs": float(np.max(np.abs(matrix), initial=0.0)),
        }

    return {
        "E_R": metrics(E_R),
        "E_T": metrics(E_T),
        "C_S": metrics(C_S),
        "E_S": metrics(E_S),
        "E_S_identity_residual": metrics(identity_residual),
        "diagnostic_only": True,
        "new_rejection_tolerance": None,
    }


def _task41_v8_local_p3_replay(
    *,
    tensor: np.ndarray,
    interior_positions: np.ndarray,
    trace_positions: np.ndarray,
    R: np.ndarray,
    T: np.ndarray,
    S: np.ndarray,
    u_i: np.ndarray,
    t_c: np.ndarray,
    b_i: np.ndarray,
    n_i: np.ndarray,
    selected_local_rows: np.ndarray,
    selected_coefficients: np.ndarray,
) -> tuple[dict[str, np.ndarray], dict[str, complex]]:
    """Recreate the saved local P3 vectors and sparse E^H selected-row products."""
    block = np.asarray(tensor, dtype=np.complex128)
    interior = np.asarray(interior_positions, dtype=np.int64)
    trace = np.asarray(trace_positions, dtype=np.int64)
    R = np.asarray(R, dtype=np.complex128)
    T = np.asarray(T, dtype=np.complex128)
    S = np.asarray(S, dtype=np.complex128)
    u_i, t_c, b_i, n_i = (
        np.asarray(value, dtype=np.complex128) for value in (u_i, t_c, b_i, n_i)
    )
    selected_rows = np.asarray(selected_local_rows, dtype=np.int64)
    coefficients = np.asarray(selected_coefficients, dtype=np.complex128)
    dimension = block.shape[0] if block.ndim == 2 else -1
    if (
        block.ndim != 2
        or block.shape != (dimension, dimension)
        or interior.ndim != 1
        or trace.ndim != 1
        or np.intersect1d(interior, trace).size
        or not np.array_equal(
            np.sort(np.concatenate((interior, trace))), np.arange(dimension)
        )
        or u_i.shape != (len(interior),)
        or b_i.shape != u_i.shape
        or n_i.shape != u_i.shape
        or t_c.shape != (len(trace),)
        or selected_rows.ndim != 1
        or coefficients.shape != selected_rows.shape
        or selected_rows.size == 0
        or np.any(selected_rows < 0)
        or np.any(selected_rows >= len(trace))
        or np.unique(selected_rows).size != selected_rows.size
        or not np.isfinite(block).all()
        or not all(np.isfinite(value).all() for value in (R, T, S, u_i, t_c, b_i, n_i, coefficients))
    ):
        raise ValueError("V8 saved local P3 inputs or tensor partition are malformed")

    K = block[np.ix_(interior, interior)]
    G = block[np.ix_(interior, trace)]
    J = block[np.ix_(trace, interior)]
    L = block[np.ix_(trace, trace)]
    if (
        R.shape != G.shape
        or T.shape != J.shape
        or S.shape != L.shape
    ):
        raise ValueError("V8 saved local R/T/S matrix layouts differ from the oriented tensor")

    K_u = K @ u_i
    G_t = G @ t_c
    actual_i = K_u + G_t
    delta_i = actual_i - n_i
    J_u = J @ u_i
    L_t = L @ t_c
    actual_t = J_u + L_t
    S_action = S @ t_c
    local_reduced_rhs = T @ b_i
    T_r_i = T @ (b_i - n_i)
    T_delta_i = T @ delta_i
    E_S_t = S_action - L_t - T @ G_t
    E_T_u = J_u + T @ K_u
    minus_E_T_u = -E_T_u
    Q_local = T_delta_i + E_S_t - E_T_u
    Q_regrouped_local = (S - L) @ t_c - J_u - T @ n_i
    arrays = {
        "K_u": K_u,
        "G_t": G_t,
        "actual_i": actual_i,
        "delta_i": delta_i,
        "J_u": J_u,
        "L_t": L_t,
        "actual_t": actual_t,
        "S_action": S_action,
        "local_reduced_rhs": local_reduced_rhs,
        "T_r_i": T_r_i,
        "T_delta_i": T_delta_i,
        "E_S_t": E_S_t,
        "minus_E_T_u": minus_E_T_u,
        "Q_local": Q_local,
        "Q_regrouped_local": Q_regrouped_local,
    }
    weights = np.zeros(len(trace), dtype=np.complex128)
    weights[selected_rows] = coefficients
    scalar_names = {
        "s": S_action,
        "rhs_i": local_reduced_rhs,
        "T_r_i": T_r_i,
        "delta_t": actual_t,
        "Q": Q_local,
        "Q_regrouped": Q_regrouped_local,
    }
    scalars = {
        name: complex(np.vdot(weights, vector))
        for name, vector in scalar_names.items()
    }
    return arrays, scalars


TASK41_P0_V8_LEGACY_REPORT_SHA256 = "1bdd07ac38bce95d58a153bacdca0de6cf5941d08d2706dc127e8b00d8e2764f"
TASK41_P0_V8_LEGACY_CONSUMER_SOURCE_SHA = "35fd1bbf2bca13bd17e89cc79cf7cd825b94411c"
TASK41_P0_V8_LEGACY_CONSUMER_CONTRACT_SHA256 = "a6a69b75e48572d59ae73f12a9424b06a3accdca957c6a32b5c72bcf2fb867da"
TASK41_P0_V8_SELECTED_TRACE_STAR_REPORT_SCHEMA = (
    "task41.p0.v8.selected_trace_star_audit_receipt.v1"
)


def _task41_v8_report_independent_checker_status(
    report: Mapping[str, Any], *, expected_report_sha256: str
) -> str | None:
    """Treat only the pinned pre-field V8 receipt as an explicitly not-run checker."""
    if report.get("independent_checker_status") == "NOT_RUN":
        return "NOT_RUN"
    if (
        "independent_checker_status" not in report
        and expected_report_sha256 == TASK41_P0_V8_LEGACY_REPORT_SHA256
        and report.get("schema") == TASK41_P0_V8_SELECTED_TRACE_STAR_REPORT_SCHEMA
        and report.get("status") == "COMPLETED_SELECTED_TRACE_STAR_AUDIT"
        and report.get("geometry_policy") == "mesh_actual_exact"
        and report.get("raw_tensor_evaluator") == "actual_qmetric_blocked_gram"
        and report.get("consumer_source_sha")
        == TASK41_P0_V8_LEGACY_CONSUMER_SOURCE_SHA
        and report.get("consumer_contract_sha256")
        == TASK41_P0_V8_LEGACY_CONSUMER_CONTRACT_SHA256
    ):
        return "NOT_RUN"
    return None


def _task41_v8_selected_trace_star_recheck(
    report_path: Path,
    *,
    expected_report_sha256: str,
    donor: Mapping[str, Any],
    donor_contract_sha256: str,
    consumer: Mapping[str, Any],
    consumer_contract_sha256: str,
    candidate_producer_contract: Mapping[str, Any] | None,
    candidate_producer_contract_sha256: str | None,
    donor_contract: Mapping[str, Any],
    repo_root: Path,
    output_directory: Path,
) -> dict[str, Any]:
    """Recheck only hash-authorized V8 local operands and selected-row attribution."""
    from src.runners.task41_p0_v4_volume_only_audit import (
        TASK41_P0_V8_SELECTED_ACTIVE_ROW,
        TASK41_P0_V8_V6_INDEX_SHA256,
        TASK41_P0_V8_V6_REPORT_SHA256,
        TASK41_P0_V8_V7_ARRAY_SHA256,
        TASK41_P0_V8_V7_INDEX_SHA256,
    )

    report_path = Path(report_path).resolve(strict=True)
    repo_root = Path(repo_root).resolve(strict=True)
    results_root = (repo_root / "results").resolve()
    if (
        not report_path.is_relative_to(results_root)
        or not re.fullmatch(r"[0-9a-f]{64}", str(expected_report_sha256))
        or sha256_file(report_path) != expected_report_sha256
    ):
        raise ValueError("V8 report path or explicit SHA-256 differs")
    report = _json_object(report_path, "V8 selected trace-star report")
    profile = _task41_mesh_actual_exact_candidate_profile(report_path, report)
    if profile["version"] != "v8":
        raise ValueError("V8 independent checker received a different candidate profile")
    consumer_case = consumer.get("case")
    report_producer = candidate_producer_contract or consumer
    report_producer_sha256 = candidate_producer_contract_sha256 or consumer_contract_sha256
    if (
        report.get("geometry_policy") != "mesh_actual_exact"
        or report.get("raw_tensor_evaluator") != "actual_qmetric_blocked_gram"
        or report.get("donor_contract_sha256") != donor_contract_sha256
        or report.get("consumer_contract_sha256") != report_producer_sha256
        or report.get("donor_source_sha") != donor_contract.get("source", {}).get("sha")
        or report.get("consumer_source_sha") != report_producer.get("source", {}).get("sha")
        or report.get("donor_manifest_sha256") != donor.get("manifest_sha256")
        or _task41_v8_report_independent_checker_status(
            report, expected_report_sha256=expected_report_sha256
        )
        != "NOT_RUN"
        or not isinstance(consumer_case, Mapping)
    ):
        raise ValueError("V8 report donor/consumer/geometry identity differs")
    selected = report.get("selected_trace_star_audit")
    if not isinstance(selected, Mapping):
        raise ValueError("V8 report omits its selected trace-star result")
    metadata = selected.get("metadata")
    p3 = selected.get("p3_production_row_replay")
    source_replay = selected.get("saved_operand_recomposition")
    source_artifacts = (
        source_replay.get("source_artifacts")
        if isinstance(source_replay, Mapping)
        else None
    )
    if (
        selected.get("status") != "COMPLETED_SELECTED_TRACE_STAR_AUDIT"
        or selected.get("selected_active_row") != TASK41_P0_V8_SELECTED_ACTIVE_ROW
        or not isinstance(metadata, Mapping)
        or not isinstance(p3, Mapping)
        or not isinstance(source_artifacts, Mapping)
        or p3.get("schema") != "task41.p0.v8.selected_trace_star_p3_replay.v1"
        or p3.get("complete_incident_cell_coverage") is not True
    ):
        raise ValueError("V8 selected trace-star report lacks its complete P3 receipt")

    expected_indices = {
        "v6_index": (
            repo_root
            / "docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v6_actual_qmetric_hash_index_20261021.json",
            TASK41_P0_V8_V6_INDEX_SHA256,
        ),
        "v7_index": (
            repo_root
            / "docs/task41extra_phi90_p50x50_g17x20/outcomes/b0_v7_saved_attribution_20261021.json",
            TASK41_P0_V8_V7_INDEX_SHA256,
        ),
    }
    source_documents: dict[str, tuple[Path, dict[str, Any]]] = {}
    for key, (expected_path, expected_sha) in expected_indices.items():
        path = Path(str(source_artifacts.get(key, ""))).resolve(strict=True)
        digest = source_artifacts.get(f"{key}_sha256")
        if path != expected_path.resolve() or digest != expected_sha or sha256_file(path) != expected_sha:
            raise ValueError(f"V8 frozen {key} path or SHA-256 differs")
        source_documents[key] = (path, _json_object(path, f"V8 {key}"))

    v6_index = source_documents["v6_index"][1]
    v7_index = source_documents["v7_index"][1]
    v6_payload = v6_index.get("candidate_persisted_arrays")
    v7_payload = v7_index.get("arrays")
    v7_audit = v7_index.get("audit")
    if not isinstance(v6_payload, Mapping) or not isinstance(v7_payload, Mapping) or not isinstance(v7_audit, Mapping):
        raise ValueError("V8 V6/V7 source indexes are malformed")
    v6_report_path = Path(str(source_artifacts.get("v6_report", ""))).resolve(strict=True)
    v7_report_path = Path(str(source_artifacts.get("v7_report", ""))).resolve(strict=True)
    if (
        v6_report_path != Path(str(v6_index.get("candidate_report_path", ""))).resolve()
        or not v6_report_path.is_relative_to(results_root)
        or source_artifacts.get("v6_report_sha256") != TASK41_P0_V8_V6_REPORT_SHA256
        or sha256_file(v6_report_path) != TASK41_P0_V8_V6_REPORT_SHA256
        or v7_report_path != Path(str(v7_audit.get("report_path", ""))).resolve()
        or not v7_report_path.is_relative_to(results_root)
        or source_artifacts.get("v7_report_sha256") != v7_audit.get("report_sha256")
        or sha256_file(v7_report_path) != v7_audit.get("report_sha256")
    ):
        raise ValueError("V8 V6/V7 source report path or SHA-256 differs from its index")
    v6_report = _json_object(v6_report_path, "V8 V6 source report")
    v7_report = _json_object(v7_report_path, "V8 V7 source report")
    v6_index_records = v6_payload.get("items")
    v6_report_records = v6_report.get("persisted_evidence_arrays")
    v7_index_records = v7_payload.get("records")
    if not all(isinstance(value, list) for value in (v6_index_records, v6_report_records, v7_index_records)):
        raise ValueError("V8 V6/V7 source indexes omit their array lists")
    v6_index_by_name = {item.get("name"): item for item in v6_index_records if isinstance(item, Mapping)}
    v6_report_by_name = {item.get("name"): item for item in v6_report_records if isinstance(item, Mapping)}
    v7_index_by_name = {item.get("name"): item for item in v7_index_records if isinstance(item, Mapping)}
    v6_source_arrays = source_artifacts.get("v6_arrays")
    v7_source_arrays = source_artifacts.get("v7_arrays")
    if (
        not isinstance(v6_source_arrays, Mapping)
        or not isinstance(v7_source_arrays, Mapping)
        or not v6_source_arrays
        or set(v6_source_arrays) - set(v6_index_by_name)
        or set(v6_source_arrays) - set(v6_report_by_name)
        or set(v7_source_arrays) != set(v7_index_by_name)
        or set(v7_source_arrays) != set(TASK41_P0_V8_V7_ARRAY_SHA256)
    ):
        raise ValueError("V8 explicit V6/V7 authorized-array lists differ from frozen indexes")

    def same_array_identity(left: Mapping[str, Any], right: Mapping[str, Any], basis: Path) -> bool:
        left_path = Path(str(left.get("path", "")))
        right_path = Path(str(right.get("path", "")))
        left_resolved = (left_path if left_path.is_absolute() else basis / left_path).resolve()
        right_resolved = (right_path if right_path.is_absolute() else repo_root / right_path).resolve()
        return bool(
            left.get("name") == right.get("name")
            and left_resolved == right_resolved
            and all(left.get(field) == right.get(field) for field in ("sha256", "bytes", "shape", "dtype"))
        )

    v6_basis = Path(str(v6_payload.get("path_basis", ""))).resolve(strict=True)
    if v6_basis != repo_root:
        raise ValueError("V8 V6 array index has a different path basis")
    for name, ref in v6_source_arrays.items():
        if (
            not isinstance(ref, Mapping)
            or not same_array_identity(ref, v6_index_by_name[name], v6_basis)
            or not same_array_identity(ref, v6_report_by_name[name], repo_root)
        ):
            raise ValueError(f"V8 V6 explicit array authorization differs for {name}")
    for name, ref in v7_source_arrays.items():
        expected_sha = TASK41_P0_V8_V7_ARRAY_SHA256[name]
        if (
            not isinstance(ref, Mapping)
            or not same_array_identity(ref, v7_index_by_name[name], repo_root)
            or ref.get("sha256") != expected_sha
        ):
            raise ValueError(f"V8 V7 explicit array authorization differs for {name}")

    v8_records_raw = report.get("persisted_evidence_arrays")
    if not isinstance(v8_records_raw, list):
        raise ValueError("V8 report omits its explicit saved-array inventory")
    v8_records: dict[str, Mapping[str, Any]] = {}
    for item in v8_records_raw:
        if not isinstance(item, Mapping) or not isinstance(item.get("name"), str):
            raise ValueError("V8 persisted-array inventory has a malformed item")
        name = str(item["name"])
        if name in v8_records:
            raise ValueError(f"V8 persisted-array name is duplicated: {name}")
        path = Path(str(item.get("path", ""))).resolve(strict=True)
        if (
            not path.is_relative_to(report_path.parent)
            or path.stat().st_size != item.get("bytes")
            or not isinstance(item.get("sha256"), str)
            or sha256_file(path) != item.get("sha256")
        ):
            raise ValueError(f"V8 persisted-array path/hash differs for {name}")
        v8_records[name] = item

    cache: dict[tuple[str, str], np.ndarray] = {}

    def load_array_ref(ref: Any, label: str) -> np.ndarray:
        if not isinstance(ref, Mapping) or not isinstance(ref.get("name"), str):
            raise ValueError(f"V8 {label} omits its named array authorization")
        name = str(ref["name"])
        if name in v8_records:
            inventory, basis = v8_records[name], report_path.parent
            cache_key = ("v8", name)
        elif name in v6_source_arrays:
            inventory, basis = v6_source_arrays[name], v6_basis
            cache_key = ("v6", name)
        elif name in v7_source_arrays:
            inventory, basis = v7_source_arrays[name], repo_root
            cache_key = ("v7", name)
        else:
            raise ValueError(f"V8 {label} references an unauthorized array: {name}")
        if not same_array_identity(ref, inventory, basis):
            raise ValueError(f"V8 {label} identity differs from its authorized inventory")
        if cache_key not in cache:
            path = Path(str(inventory["path"]))
            path = (path if path.is_absolute() else basis / path).resolve(strict=True)
            if (
                not path.is_relative_to(results_root)
                or path.stat().st_size != inventory.get("bytes")
                or sha256_file(path) != inventory.get("sha256")
            ):
                raise ValueError(f"V8 {label} array path/hash changed: {name}")
            array = np.load(path, mmap_mode="r", allow_pickle=False)
            if (
                list(array.shape) != inventory.get("shape")
                or str(array.dtype) != inventory.get("dtype")
                or array.dtype.kind not in "fciu"
                or not np.isfinite(array).all()
            ):
                raise ValueError(f"V8 {label} array layout or values changed: {name}")
            cache[cache_key] = array
        return cache[cache_key]

    incident_order = metadata.get("incident_cell_order")
    selected_active_row = selected.get("selected_active_row")
    selected_original_row = selected.get("selected_original_row")
    if (
        not isinstance(incident_order, list)
        or not incident_order
        or any(type(cell) is not int for cell in incident_order)
        or incident_order != sorted(set(incident_order))
        or type(selected_original_row) is not int
        or metadata.get("incident_cell_count") != len(incident_order)
        or selected_active_row != TASK41_P0_V8_SELECTED_ACTIVE_ROW
    ):
        raise ValueError("V8 selected row or incident-cell map is malformed")
    columns = donor.get("columns")
    if not isinstance(columns, (list, tuple)) or len(columns) != 2:
        raise ValueError("V8 checker requires the normalized two-column saved donor")
    for column in columns:
        active = np.asarray(column["active_original_rows"])
        if (
            active.ndim != 1
            or active.dtype.kind not in "iu"
            or selected_active_row >= active.size
            or int(active[selected_active_row]) != selected_original_row
        ):
            raise ValueError("V8 selected original row does not resolve through donor map")

    numeric_records = selected.get("local_numeric_cell_identity_and_artifacts")
    selected_cells = metadata.get("selected_cells")
    per_cell_rows = p3.get("per_cell_signed_contributions")
    if not all(isinstance(value, list) for value in (numeric_records, selected_cells, per_cell_rows)):
        raise ValueError("V8 selected-star report omits local cells or P3 inputs")
    selected_by_id = {item.get("cell_index"): item for item in selected_cells if isinstance(item, Mapping)}
    numeric_by_id = {item.get("cell_index"): item for item in numeric_records if isinstance(item, Mapping)}
    p3_by_id = {item.get("cell_index"): item for item in per_cell_rows if isinstance(item, Mapping)}
    if (
        len(selected_by_id) != len(selected_cells)
        or len(numeric_by_id) != len(numeric_records)
        or len(p3_by_id) != len(per_cell_rows)
        or list(selected_by_id) != incident_order
        or set(incident_order) - set(numeric_by_id)
        or set(p3_by_id) != set(incident_order)
    ):
        raise ValueError("V8 selected-cell identity does not cover the complete incident star")

    from src.solvers.hcurl_assembly_time_condensation import _strict_local_lu

    cell_terms: dict[tuple[int, int, str, str], dict[str, complex]] = {}
    local_vector_checks = 0
    local_matrix_defects: list[dict[str, Any]] = []
    local_rhs_lu_factors: dict[tuple[int, str], dict[str, Any]] = {}
    local_rhs_lu_inputs: dict[tuple[int, str, int], np.ndarray] = {}
    local_rhs_lu_terms: dict[tuple[int, str, int], dict[str, Any]] = {}
    local_rhs_lu_solution_arrays: dict[tuple[int, str, int], dict[str, np.ndarray]] = {}
    local_rhs_lu_factorizations: list[dict[str, Any]] = []
    local_rhs_lu_state_pair_reuses = 0
    for cell_index in incident_order:
        numeric = numeric_by_id[cell_index]
        selected_map = selected_by_id[cell_index]
        if numeric.get("is_target_row_incident") is not True:
            raise ValueError("V8 numeric-cell inventory marks an incident cell as nonincident")
        local_meta = {
            key: numeric.get(key)
            for key in ("selected_local_trace_rows", "selected_trace_coefficients")
        }
        if (
            local_meta["selected_local_trace_rows"] != selected_map.get("selected_local_trace_rows")
            or local_meta["selected_trace_coefficients"] != selected_map.get("selected_trace_coefficients")
        ):
            raise ValueError(f"V8 selected-row support differs between cell {cell_index} records")
        interior_positions = np.asarray(numeric.get("true_interior_positions"), dtype=np.int64)
        trace_positions = np.asarray(numeric.get("trace_complement_positions"), dtype=np.int64)
        interior_rows = np.asarray(numeric.get("interior_original_rows"), dtype=np.int64)
        trace_rows = np.asarray(numeric.get("trace_original_rows"), dtype=np.int64)
        active_ids = np.asarray(numeric.get("active_ids"), dtype=np.int64)
        selected_local_rows = np.asarray(local_meta["selected_local_trace_rows"], dtype=np.int64)
        selected_coefficients = _task41_v8_complex_pairs(
            local_meta["selected_trace_coefficients"],
            f"cell {cell_index} selected trace coefficients",
        )
        if (
            interior_positions.ndim != 1
            or trace_positions.ndim != 1
            or interior_rows.shape != interior_positions.shape
            or trace_rows.shape != trace_positions.shape
            or active_ids.ndim != 1
            or np.intersect1d(interior_positions, trace_positions).size
            or not np.array_equal(
                np.sort(np.concatenate((interior_positions, trace_positions))),
                np.arange(len(interior_positions) + len(trace_positions)),
            )
            or selected_local_rows.size == 0
            or np.any(selected_local_rows >= len(trace_positions))
            or np.unique(selected_local_rows).size != selected_local_rows.size
            or not np.isfinite(selected_coefficients).all()
            or not np.any(selected_coefficients != 0.0)
        ):
            raise ValueError(f"V8 cell {cell_index} selected-row local partition is malformed")
        locations = np.flatnonzero(active_ids == selected_active_row)
        if locations.size != 1 or not np.array_equal(selected_local_rows, np.asarray(selected_map["selected_local_trace_rows"], dtype=np.int64)):
            raise ValueError(f"V8 cell {cell_index} active trace row is missing or duplicated")

        role_records = numeric.get("roles")
        state_records = p3_by_id[cell_index].get("roles_and_states")
        if not isinstance(role_records, list) or not isinstance(state_records, list):
            raise ValueError(f"V8 cell {cell_index} omits role/state records")
        roles_by_name = {row.get("role"): row for row in role_records if isinstance(row, Mapping)}
        if set(roles_by_name) != {"candidate", "reference"}:
            raise ValueError(f"V8 cell {cell_index} does not bind both numeric roles")
        state_lookup = {
            (row.get("column"), row.get("state")): row
            for row in state_records
            if isinstance(row, Mapping)
        }
        if set(state_lookup) != {
            (column, state) for column in range(2) for state in ("j0", "j3")
        }:
            raise ValueError(f"V8 cell {cell_index} does not bind both columns and paired states")

        for role in ("candidate", "reference"):
            role_row = roles_by_name[role]
            if (
                role_row.get("producer_identity")
                != (selected.get("candidate_identity") if role == "candidate" else "original_ffcx_reference_kernel")
                or not isinstance(role_row.get("raw_oriented_RTS_artifacts"), Mapping)
            ):
                raise ValueError(f"V8 cell {cell_index} {role} producer identity is missing")
            artifact_refs = role_row["raw_oriented_RTS_artifacts"]
            tensors = load_array_ref(artifact_refs.get("oriented_tensor"), f"cell {cell_index} {role} tensor")
            if tensors.shape != (len(interior_positions) + len(trace_positions),) * 2:
                raise ValueError(f"V8 cell {cell_index} {role} oriented tensor shape differs")
            RTS = {
                name: load_array_ref(artifact_refs.get(name), f"cell {cell_index} {role} {name}")
                for name in ("R", "T", "S")
            }
            if any(array.dtype != np.dtype(np.complex128) for array in [tensors, *RTS.values()]):
                raise ValueError(f"V8 cell {cell_index} {role} local matrices are not complex128")
            local_matrix_defects.append(
                {
                    "cell_index": cell_index,
                    "role": role,
                    **_task41_v8_local_matrix_defect_diagnostic(
                        tensor=tensors,
                        interior_positions=interior_positions,
                        trace_positions=trace_positions,
                        R=RTS["R"],
                        T=RTS["T"],
                        S=RTS["S"],
                    ),
                }
            )
            K = np.asarray(
                tensors[np.ix_(interior_positions, interior_positions)],
                dtype=np.complex128,
            )
            J = np.asarray(
                tensors[np.ix_(trace_positions, interior_positions)],
                dtype=np.complex128,
            )
            factor_key = (cell_index, role)
            if factor_key in local_rhs_lu_factors:
                raise ValueError(f"V8 local RHS diagnostic repeats LU factor {factor_key}")
            K_sha256 = hashlib.sha256(np.ascontiguousarray(K).view(np.uint8)).hexdigest()
            factor_started = time.perf_counter()
            local_factor, strict_identity_defect = _strict_local_lu(K)
            factor_seconds = time.perf_counter() - factor_started
            local_rhs_lu_factors[factor_key] = {
                "factor": local_factor,
                "K": K,
                "J": J,
                "T": RTS["T"],
                "selected_local_rows": selected_local_rows,
                "selected_coefficients": selected_coefficients,
                "K_sha256": K_sha256,
            }
            local_rhs_lu_factorizations.append(
                {
                    "cell_index": cell_index,
                    "role": role,
                    "factorization_identity": "fresh _strict_local_lu(K) from saved oriented_tensor; reused for both columns and states",
                    "K_sha256": K_sha256,
                    "oriented_tensor_sha256": artifact_refs["oriented_tensor"].get("sha256"),
                    "saved_T_sha256": artifact_refs["T"].get("sha256"),
                    "strict_identity_relative_defect": strict_identity_defect,
                    "factorization_seconds": factor_seconds,
                }
            )
            for column_index in range(2):
                donor_column = columns[column_index]
                native_volume_rhs = np.asarray(donor_column["native_volume_rhs"], dtype=np.complex128)
                native_rhs = np.asarray(donor_column["native_rhs"], dtype=np.complex128)
                for state_label in ("j0", "j3"):
                    state_row = state_lookup[(column_index, state_label)]
                    if state_row.get("native_full_rhs_at_selected_original_row") is None:
                        raise ValueError("V8 P3 state omits its native full RHS value")
                    state_role = next(
                        (
                            entry for entry in state_row.get("roles", [])
                            if isinstance(entry, Mapping) and entry.get("role") == role
                        ),
                        None,
                    )
                    if not isinstance(state_role, Mapping):
                        raise ValueError(f"V8 cell {cell_index} {role} P3 state input is absent")
                    local_values = state_role.get("local_values")
                    signed_refs = state_role.get("signed_action_artifacts")
                    if not isinstance(local_values, Mapping) or not isinstance(signed_refs, Mapping):
                        raise ValueError("V8 P3 state does not bind its local inputs/actions")
                    state = next(item for item in donor_column["states"] if item.get("label") == state_label)
                    storage = np.asarray(state["storage"], dtype=np.complex128)
                    native_action = np.asarray(state["native_volume_action"], dtype=np.complex128)
                    inputs = {
                        "u_i": load_array_ref(local_values.get("u_i"), "u_i"),
                        "t_c": load_array_ref(local_values.get("t_c"), "t_c"),
                        "b_i": load_array_ref(local_values.get("b_i"), "b_i"),
                        "n_i": load_array_ref(local_values.get("n_i"), "n_i"),
                    }
                    _task41_v8_assert_close(inputs["u_i"], storage[interior_rows], f"cell {cell_index} u_i donor slice")
                    _task41_v8_assert_close(inputs["t_c"], storage[trace_rows], f"cell {cell_index} t_c donor slice")
                    _task41_v8_assert_close(inputs["b_i"], native_volume_rhs[interior_rows], f"cell {cell_index} b_i donor slice")
                    _task41_v8_assert_close(inputs["n_i"], native_action[interior_rows], f"cell {cell_index} n_i donor slice")
                    vectors, scalars = _task41_v8_local_p3_replay(
                        tensor=tensors,
                        interior_positions=interior_positions,
                        trace_positions=trace_positions,
                        R=RTS["R"],
                        T=RTS["T"],
                        S=RTS["S"],
                        u_i=inputs["u_i"],
                        t_c=inputs["t_c"],
                        b_i=inputs["b_i"],
                        n_i=inputs["n_i"],
                        selected_local_rows=selected_local_rows,
                        selected_coefficients=selected_coefficients,
                    )
                    for name, expected in vectors.items():
                        actual = load_array_ref(signed_refs.get(name), f"cell {cell_index} {name}")
                        _task41_v8_assert_close(actual, expected, f"cell {cell_index} {name}")
                        local_vector_checks += 1
                    projected_location = int(locations[0])
                    for name, scalar_name in (
                        ("projected_actual_trace", "delta_t"),
                        ("projected_T_r_i", "T_r_i"),
                        ("projected_Q", "Q"),
                        ("projected_Q_regrouped", "Q_regrouped"),
                    ):
                        projected = load_array_ref(
                            signed_refs.get(name), f"cell {cell_index} {name}"
                        )
                        if projected.shape != (active_ids.size,):
                            raise ValueError(
                                f"V8 cell {cell_index} {name} projection layout differs"
                            )
                        _task41_v8_assert_close(
                            projected[projected_location],
                            scalars[scalar_name],
                            f"cell {cell_index} selected {name}",
                        )
                        local_vector_checks += 1
                    contributions = state_role.get("selected_row_contributions")
                    _task41_v8_check_selected_row_contributions(
                        contributions, scalars, f"cell {cell_index}"
                    )
                    rhs_key = (cell_index, role, column_index)
                    if state_label == "j0":
                        if rhs_key in local_rhs_lu_terms:
                            raise ValueError(f"V8 local RHS diagnostic duplicates {rhs_key}")
                        lu_data = local_rhs_lu_factors[(cell_index, role)]
                        rhs_diagnostic = _task41_v8_lu_rhs_counterfactual(
                            K=lu_data["K"],
                            J=lu_data["J"],
                            T=lu_data["T"],
                            b_i=inputs["b_i"],
                            factor=lu_data["factor"],
                            selected_local_rows=lu_data["selected_local_rows"],
                            selected_coefficients=lu_data["selected_coefficients"],
                        )
                        local_rhs_lu_solution_arrays[rhs_key] = {
                            "solution": rhs_diagnostic.pop("_solution_array"),
                            "residual": rhs_diagnostic.pop("_residual_array"),
                        }
                        local_rhs_lu_terms[rhs_key] = rhs_diagnostic
                        local_rhs_lu_inputs[rhs_key] = inputs["b_i"]
                        local_rhs_lu_terms[rhs_key].update(
                            {
                                "cell_index": cell_index,
                                "role": role,
                                "column": column_index,
                                "b_i_sha256": local_values["b_i"].get("sha256"),
                                "factorization_K_sha256": lu_data["K_sha256"],
                            }
                        )
                    else:
                        previous_rhs = local_rhs_lu_inputs.get(rhs_key)
                        if previous_rhs is None or not np.array_equal(
                            inputs["b_i"], previous_rhs
                        ):
                            raise ValueError(
                                f"V8 paired-state b_i differs for local RHS LU reuse {rhs_key}"
                            )
                        local_rhs_lu_state_pair_reuses += 1
                    cell_terms[(cell_index, column_index, state_label, role)] = scalars

    local_rhs_lu_cases: list[dict[str, Any]] = []
    for role in ("candidate", "reference"):
        for column_index in range(2):
            native_volume_rhs = np.asarray(
                columns[column_index]["native_volume_rhs"], dtype=np.complex128
            )
            for state_label in ("j0", "j3"):
                s_sum = sum(
                    cell_terms[(cell_index, column_index, state_label, role)]["s"]
                    for cell_index in incident_order
                )
                old_rhs_sum = sum(
                    complex(*local_rhs_lu_terms[(cell_index, role, column_index)]["old_T_b_i_projected"])
                    for cell_index in incident_order
                )
                new_rhs_sum = sum(
                    complex(*local_rhs_lu_terms[(cell_index, role, column_index)]["new_minus_J_solve_K_b_i_projected"])
                    for cell_index in incident_order
                )
                local_rhs_lu_cases.append(
                    {
                        "role": role,
                        "column": column_index,
                        "state": state_label,
                        **_task41_v8_lu_rhs_totals(
                            native_volume_rhs=native_volume_rhs,
                            selected_active_row=selected_active_row,
                            selected_original_row=selected_original_row,
                            selected_S_sum=s_sum,
                            old_local_rhs_sum=old_rhs_sum,
                            new_local_rhs_sum=new_rhs_sum,
                        ),
                        "cell_terms": [
                            local_rhs_lu_terms[(cell_index, role, column_index)]
                            for cell_index in incident_order
                        ],
                    }
                )
    local_rhs_lu_case_by_key = {
        (item["role"], item["column"], item["state"]): item
        for item in local_rhs_lu_cases
    }
    local_rhs_lu_candidate_reference_gaps = []
    for column_index in range(2):
        candidate = local_rhs_lu_case_by_key[("candidate", column_index, "j0")]
        reference = local_rhs_lu_case_by_key[("reference", column_index, "j0")]
        old_gap = np.asarray(candidate["g_old_b_t_plus_T_b_i"]) - np.asarray(
            reference["g_old_b_t_plus_T_b_i"]
        )
        new_gap = np.asarray(
            candidate["g_new_b_t_plus_direct_minus_J_solve_K_b_i"]
        ) - np.asarray(reference["g_new_b_t_plus_direct_minus_J_solve_K_b_i"])
        local_rhs_lu_candidate_reference_gaps.append(
            {
                "column": column_index,
                "state_used": "j0 (paired j3 b_i reuse is checked above)",
                "old_candidate_minus_reference_g": old_gap.tolist(),
                "new_candidate_minus_reference_g": new_gap.tolist(),
                "old_absolute_gap": float(np.linalg.norm(old_gap)),
                "new_absolute_gap": float(np.linalg.norm(new_gap)),
            }
        )
    expected_factorizations = len(incident_order) * 2
    expected_rhs_pairs = len(incident_order) * 2 * 2
    if (
        len(local_rhs_lu_factorizations) != expected_factorizations
        or len(local_rhs_lu_terms) != expected_rhs_pairs
        or local_rhs_lu_state_pair_reuses != expected_rhs_pairs
    ):
        raise ValueError("V8 saved local RHS LU counterfactual is incomplete")
    local_rhs_lu_counterfactual = {
        "schema": "task41.p0.v8.local_rhs_lu_counterfactual.v1",
        "status": "DIAGNOSTIC_ONLY",
        "source_report_sha256_rechecked": expected_report_sha256,
        "formal_candidate_or_residual_gate_changed": False,
        "production_solver_changed": False,
        "incident_cells": incident_order,
        "new_strict_lu_factorization_count": len(local_rhs_lu_factorizations),
        "direct_rhs_solve_count": len(local_rhs_lu_terms),
        "paired_state_rhs_reuse_count": local_rhs_lu_state_pair_reuses,
        "strict_factorization_seconds_sum": sum(
            row["factorization_seconds"] for row in local_rhs_lu_factorizations
        ),
        "rhs_counterfactual_seconds_sum": sum(
            row["counterfactual_seconds"] for row in local_rhs_lu_terms.values()
        ),
        "factorizations": local_rhs_lu_factorizations,
        "cases": local_rhs_lu_cases,
        "candidate_reference_gaps": local_rhs_lu_candidate_reference_gaps,
        "method": "Rebuild one strict LU per saved cell/role, reuse it for both columns; verify j0/j3 b_i equality and solve only once per pair; compare saved T @ b_i with -J @ solve(K, b_i), project by selected local-row coefficients, then add the original global b_t once.",
        "scope": "Saved incident cells only; no tensor regeneration, FE/PDE run, refinement, production change, or threshold change.",
    }

    v6_index_by_name = {str(name): value for name, value in v6_index_by_name.items()}
    v7_values = {str(name): value for name, value in v7_index_by_name.items()}

    def source_value(name: str, label: str) -> np.ndarray:
        ref = v6_source_arrays.get(name) or v7_source_arrays.get(name)
        if not isinstance(ref, Mapping):
            raise ValueError(f"V8 required saved {label} is not in its authorized source list")
        return load_array_ref(ref, label)

    active_rows = int(donor["manifest"].get("active_trace_rows", -1))
    p6_saved = source_value("task41_p0_v6_qmetric_candidate_full_p6", "V6 full_p6")
    reduced_saved = source_value("task41_p0_v6_qmetric_candidate_full_reduced_rhs", "V6 full reduced RHS")
    if p6_saved.shape[0] <= selected_active_row or reduced_saved.shape != p6_saved.shape:
        raise ValueError("V8 V6 full-row arrays have an invalid layout")
    v6_attribution: dict[tuple[int, str, str], complex] = {}
    v7_closures: dict[tuple[int, str, str], complex] = {}
    for column_index in range(2):
        for state_label in ("j0", "j3"):
            prefix = f"task41_p0_v6_qmetric_candidate_attribution_col{column_index}_{state_label}_"
            for field in ("T_r_i", "delta_t", "attributed_terms"):
                v6_attribution[(column_index, state_label, field)] = complex(
                    source_value(prefix + field, f"V6 {field}")[selected_active_row]
                )
            for kind in ("full", "volume"):
                name = f"task41_p0_v7_attribution_col{column_index}_{state_label}_corrected_{kind}_closure"
                v7_closures[(column_index, state_label, kind)] = complex(
                    source_value(name, f"V7 {kind} closure")[selected_active_row]
                )

    expected_orders = p3.get("cell_sum_orders")
    if not isinstance(expected_orders, Mapping):
        raise ValueError("V8 P3 report omits its two ordered summation maps")
    production_order = expected_orders.get("production_original_cell_order")
    observer_order = expected_orders.get("v6_eight_key_prefix_observer_order")
    prefix_order = expected_orders.get("v6_eight_key_prefix_order")
    if production_order != incident_order or not isinstance(observer_order, list) or not isinstance(prefix_order, list) or len(prefix_order) != 8:
        raise ValueError("V8 production or V6-prefix summation order differs")
    ordered_summaries = p3.get("ordered_summaries")
    if not isinstance(ordered_summaries, Mapping):
        raise ValueError("V8 P3 report omits ordered selected-row summaries")
    scalar_rows_checked = 0
    native_rhs_split_epsilon: dict[int, complex] = {}
    summary_field_map = {
        "s": "s_r_volume_sum_wH_S_t",
        "s_full": "s_r_full_volume_plus_B_alpha_once",
        "g_volume": "g_volume_r_b_t_plus_sum_wH_T_b_i",
        "d_volume_star": "d_volume_star_s_minus_g_volume",
        "g_full": "g_full_r_f_t_plus_sum_wH_T_b_i",
        "d_full_star": "d_full_star_s_plus_B_alpha_minus_g_full",
        "T_r_i": "sum_wH_T_r_i",
        "delta_t": "delta_t_original_order_starts_at_minus_native_action",
        "Q": "Q_sum_wH_attributed_terms",
        "Q_regrouped": "Q_regrouped_sum",
    }
    ordered_p3_row_checks = []
    for order_name, order in (("production_original_cell_order", production_order), ("v6_eight_key_prefix_observer_order", observer_order)):
        if ordered_summaries.get(order_name) is None:
            raise ValueError(f"V8 P3 summary omits order {order_name}")
        report_rows = ordered_summaries[order_name]
        if not isinstance(report_rows, list):
            raise ValueError(f"V8 P3 summary rows are malformed for {order_name}")
        for column_index in range(2):
            donor_column = columns[column_index]
            native_v = complex(donor_column["native_volume_rhs"][selected_original_row])
            native_f = complex(donor_column["native_rhs"][selected_original_row])
            state_by_label = {item["label"]: item for item in donor_column["states"]}
            beta_rows = np.asarray(donor_column["b_alpha_rows"], dtype=np.int64)
            beta_values = np.asarray(donor_column["b_alpha_values"], dtype=np.complex128)
            beta = beta_values[beta_rows == selected_original_row]
            if beta.size > 1:
                raise ValueError("V8 donor B-alpha has duplicate selected-row entries")
            beta_value = complex(beta[0]) if beta.size else 0.0 + 0.0j
            native_rhs_split_epsilon[column_index] = native_f - native_v - beta_value
            for state_label in ("j0", "j3"):
                native_action = complex(state_by_label[state_label]["native_volume_action"][selected_original_row])
                for role in ("candidate", "reference"):
                    totals = {name: 0.0 + 0.0j for name in ("s", "rhs_i", "T_r_i", "Q", "Q_regrouped")}
                    totals["delta_t"] = -native_action
                    for cell_index in order:
                        terms = cell_terms.get((cell_index, column_index, state_label, role))
                        if terms is not None:
                            for name, value in terms.items():
                                totals[name] += value
                    s_full = totals["s"] + beta_value
                    g_volume = native_v + totals["rhs_i"]
                    g_full = native_f + totals["rhs_i"]
                    d_volume = totals["s"] - g_volume
                    d_full = s_full - g_full
                    r_volume = native_v - native_action
                    r_full = native_f - native_action - beta_value
                    d_volume_saved = complex(source_value(f"task41_v4_d_volume_trace_col{column_index}", "V6 d_volume")[selected_active_row])
                    d_full_saved = complex(p6_saved[selected_active_row, column_index] - reduced_saved[selected_active_row, column_index])
                    left_volume = (d_volume_saved + r_volume) + totals["T_r_i"]
                    left_full = (d_full_saved + r_full) + totals["T_r_i"]
                    right_attribution = totals["delta_t"] + totals["Q"]
                    closure_volume = left_volume - right_attribution
                    closure_full = left_full - right_attribution
                    expected_values = {
                        "s": totals["s"],
                        "s_full": s_full,
                        "g_volume": g_volume,
                        "d_volume_star": d_volume,
                        "g_full": g_full,
                        "d_full_star": d_full,
                        "T_r_i": totals["T_r_i"],
                        "delta_t": totals["delta_t"],
                        "Q": totals["Q"],
                        "Q_regrouped": totals["Q_regrouped"],
                    }
                    row = next(
                        (item for item in report_rows if isinstance(item, Mapping) and item.get("column") == column_index and item.get("state") == state_label and item.get("role") == role),
                        None,
                    )
                    if not isinstance(row, Mapping):
                        raise ValueError(f"V8 P3 ordered summary row is missing: {order_name}/{column_index}/{state_label}/{role}")
                    native_record = row.get("selected_row_rhs_and_action")
                    if not isinstance(native_record, Mapping):
                        raise ValueError("V8 P3 ordered summary omits its native row split")
                    for report_key, expected in (
                        ("native_volume_rhs_b_t", native_v),
                        ("native_full_rhs_f_t", native_f),
                        ("native_volume_action_n_t", native_action),
                        ("B_alpha_selected_row_applied_once", beta_value),
                    ):
                        _task41_v8_assert_close(
                            _task41_v8_complex_pair(native_record.get(report_key), report_key),
                            expected,
                            f"{order_name} {report_key}",
                        )
                    replay = row.get("production_row_replay")
                    if not isinstance(replay, Mapping):
                        raise ValueError("V8 P3 ordered summary omits production terms")
                    for name, report_key in summary_field_map.items():
                        actual = _task41_v8_complex_pair(replay.get(report_key), report_key)
                        _task41_v8_assert_close(actual, expected_values[name], f"{order_name} {report_key}")
                    comparisons = (
                        row.get("saved_v6_v7_row_comparisons")
                        if role == "candidate"
                        else None
                    )
                    if role == "candidate" and not isinstance(comparisons, Mapping):
                        raise ValueError("V8 candidate P3 summary omits its V6/V7 comparisons")
                    closure_check = _task41_v8_check_ordered_summary_closures(
                        replay=replay,
                        expected_left_volume=left_volume,
                        expected_left_full=left_full,
                        expected_closure_volume=closure_volume,
                        expected_closure_full=closure_full,
                        comparisons=comparisons,
                        role=role,
                        label=f"{order_name}/{column_index}/{state_label}/{role}",
                    )
                    ordered_p3_row_checks.append(
                        {
                            "order": order_name,
                            "column": column_index,
                            "state": state_label,
                            "role": role,
                            **closure_check,
                        }
                    )
                    if role == "candidate":
                        expected_differences = {
                            "star_s_full_minus_V6_full_p6": s_full - complex(p6_saved[selected_active_row, column_index]),
                            "star_g_full_minus_V6_full_reduced_rhs": g_full - complex(reduced_saved[selected_active_row, column_index]),
                            "star_d_volume_minus_V6_d_volume": d_volume - d_volume_saved,
                            "star_d_full_minus_V6_d_full": d_full - d_full_saved,
                            "star_delta_t_minus_V6": totals["delta_t"] - v6_attribution[(column_index, state_label, "delta_t")],
                            "star_T_r_i_minus_V6": totals["T_r_i"] - v6_attribution[(column_index, state_label, "T_r_i")],
                            "star_Q_minus_V6": totals["Q"] - v6_attribution[(column_index, state_label, "attributed_terms")],
                            "recomposed_full_closure_minus_V7": closure_full - v7_closures[(column_index, state_label, "full")],
                            "recomposed_volume_closure_minus_V7": closure_volume - v7_closures[(column_index, state_label, "volume")],
                        }
                        for name, expected in expected_differences.items():
                            _task41_v8_assert_close(
                                _task41_v8_complex_pair(comparisons.get(name), name),
                                expected,
                                f"{order_name} {name}",
                            )
                    scalar_rows_checked += 1

    production_rows = ordered_summaries["production_original_cell_order"]
    old_baseline_crosschecks = []
    for case in local_rhs_lu_cases:
        summary_row = next(
            (
                item
                for item in production_rows
                if isinstance(item, Mapping)
                and item.get("column") == case["column"]
                and item.get("state") == case["state"]
                and item.get("role") == case["role"]
            ),
            None,
        )
        replay = summary_row.get("production_row_replay") if isinstance(summary_row, Mapping) else None
        if not isinstance(replay, Mapping):
            raise ValueError("V8 local RHS counterfactual cannot bind production-order baseline")
        expected_g = _task41_v8_complex_pair(
            replay.get(summary_field_map["g_volume"]), "production-order g_volume"
        )
        expected_d = _task41_v8_complex_pair(
            replay.get(summary_field_map["d_volume_star"]),
            "production-order d_volume_star",
        )
        actual_g = complex(*case["g_old_b_t_plus_T_b_i"])
        actual_d = complex(*case["d_old_S_minus_g_old"])
        _task41_v8_assert_close(
            actual_g, expected_g, "production-order local RHS counterfactual g_old"
        )
        _task41_v8_assert_close(
            actual_d, expected_d, "production-order local RHS counterfactual d_old"
        )
        old_baseline_crosschecks.append(
            {
                "order": "production_original_cell_order",
                "role": case["role"],
                "column": case["column"],
                "state": case["state"],
                "g_old_matches_existing_ordered_summary": True,
                "d_old_matches_existing_ordered_summary": True,
            }
        )
    local_rhs_lu_counterfactual["production_order_old_baseline_crosschecks"] = (
        old_baseline_crosschecks
    )

    import shutil

    from src.runners.task41_p0_v4_volume_only_audit import _persist_array

    diagnostic_output = Path(output_directory).resolve(strict=True)
    if not diagnostic_output.is_relative_to(results_root) or not diagnostic_output.is_dir():
        raise ValueError("V8 local RHS diagnostic output must be inside the registered results tree")
    planned_arrays: list[tuple[str, np.ndarray, str, dict[str, Any], str]] = []
    factor_record_by_key = {
        (row["cell_index"], row["role"]): row
        for row in local_rhs_lu_factorizations
    }
    for key, lu_data in local_rhs_lu_factors.items():
        cell_index, role = key
        factor_lu, factor_pivots = lu_data["factor"]
        planned_arrays.extend(
            (
                (
                    f"v8_lu_cell{cell_index}_{role}",
                    factor_lu,
                    "LOCAL_LU_RECONSTRUCTED_FROM_SAVED_TENSOR",
                    factor_record_by_key[key],
                    "lu_factor_artifact",
                ),
                (
                    f"v8_lu_cell{cell_index}_{role}_pivots",
                    factor_pivots,
                    "LOCAL_LU_PIVOTS",
                    factor_record_by_key[key],
                    "owned_pivots_artifact",
                ),
            )
        )
    for key, arrays in local_rhs_lu_solution_arrays.items():
        cell_index, role, column_index = key
        term_record = local_rhs_lu_terms[key]
        planned_arrays.extend(
            (
                (
                    f"v8_lu_solve_cell{cell_index}_{role}_col{column_index}_solution",
                    arrays["solution"],
                    "LOCAL_LU_SOLUTION",
                    term_record,
                    "solution_artifact",
                ),
                (
                    f"v8_lu_solve_cell{cell_index}_{role}_col{column_index}_residual",
                    arrays["residual"],
                    "LOCAL_LU_SOLVE_RESIDUAL",
                    term_record,
                    "residual_artifact",
                ),
            )
        )
    planned_array_payload_bytes = sum(int(array.nbytes) for _, array, _, _, _ in planned_arrays)
    planned_npy_header_allowance = 1024 * len(planned_arrays)
    prior_array_payload_bytes = int(selected.get("prior_array_payload_bytes", -1))
    persisted_report_bytes = int(report.get("persisted_evidence_bytes", -1))
    evidence_cap_bytes = int(report.get("evidence_cap_bytes", -1))
    free_space_floor_bytes = int(report.get("free_space_floor_bytes", -1))
    if min(
        prior_array_payload_bytes,
        persisted_report_bytes,
        evidence_cap_bytes,
        free_space_floor_bytes,
    ) < 0:
        raise ValueError("V8 report omits evidence-cap or free-space accounting")
    preflight_increment_bytes = planned_array_payload_bytes + planned_npy_header_allowance
    projected_cumulative_bytes = (
        prior_array_payload_bytes + persisted_report_bytes + preflight_increment_bytes
    )
    free_space_before_bytes = shutil.disk_usage(diagnostic_output).free
    if projected_cumulative_bytes > evidence_cap_bytes:
        raise ValueError("V8 local RHS LU artifacts exceed the report evidence cap")
    if free_space_before_bytes < preflight_increment_bytes + free_space_floor_bytes:
        raise ValueError("V8 local RHS LU artifacts would violate the report free-space floor")
    diagnostic_arrays_directory = diagnostic_output / "local_rhs_lu_counterfactual"
    diagnostic_arrays_directory.mkdir(parents=False, exist_ok=False)
    array_artifacts = []

    def persist_diagnostic_array(name: str, array: np.ndarray, *, kind: str) -> dict[str, Any]:
        record = _persist_array(
            diagnostic_arrays_directory,
            name,
            array,
            sha256_file=sha256_file,
        )
        item = {"name": name, "kind": kind, **record}
        array_artifacts.append(item)
        return item

    for name, array, kind, owner, field in planned_arrays:
        owner[field] = persist_diagnostic_array(name, array, kind=kind)
    persisted_diagnostic_bytes = sum(int(item["bytes"]) for item in array_artifacts)
    cumulative_bytes_after = (
        prior_array_payload_bytes + persisted_report_bytes + persisted_diagnostic_bytes
    )
    free_space_after_bytes = shutil.disk_usage(diagnostic_output).free
    if cumulative_bytes_after > evidence_cap_bytes:
        raise RuntimeError("V8 local RHS LU artifacts exceeded the report evidence cap after writing")
    if free_space_after_bytes < free_space_floor_bytes:
        raise RuntimeError("V8 local RHS LU artifacts violated the report free-space floor after writing")
    local_rhs_lu_counterfactual["array_directory"] = str(
        diagnostic_arrays_directory.resolve()
    )
    local_rhs_lu_counterfactual["array_artifact_count"] = len(array_artifacts)
    local_rhs_lu_counterfactual["array_artifacts"] = array_artifacts
    local_rhs_lu_counterfactual["evidence_cap_accounting"] = {
        "prior_array_payload_bytes": prior_array_payload_bytes,
        "report_persisted_evidence_bytes": persisted_report_bytes,
        "diagnostic_array_payload_bytes": planned_array_payload_bytes,
        "diagnostic_npy_header_allowance_bytes": planned_npy_header_allowance,
        "diagnostic_persisted_file_bytes": persisted_diagnostic_bytes,
        "evidence_cap_bytes": evidence_cap_bytes,
        "projected_cumulative_bytes_with_header_allowance": projected_cumulative_bytes,
        "cumulative_persisted_bytes_after_write": cumulative_bytes_after,
        "free_space_before_bytes": free_space_before_bytes,
        "free_space_after_bytes": free_space_after_bytes,
        "free_space_floor_bytes": free_space_floor_bytes,
    }

    return {
        "schema": "task41.p0.v8.selected_trace_star_independent_check.v1",
        "check_completed": True,
        "candidate_passed": None,
        "formal_candidate_or_residual_gate_changed": False,
        "report_sha256_rechecked": expected_report_sha256,
        "report_producer_source_sha": report_producer.get("source", {}).get("sha"),
        "report_producer_contract_sha256": report_producer_sha256,
        "checker_consumer_source_sha": consumer.get("source", {}).get("sha"),
        "authorized_v8_array_count": len(v8_records),
        "authorized_v6_array_count": len(v6_source_arrays),
        "authorized_v7_array_count": len(v7_source_arrays),
        "incident_cell_count": len(incident_order),
        "local_saved_vector_recomputations": local_vector_checks,
        "local_matrix_defect_diagnostics": local_matrix_defects,
        "local_rhs_lu_counterfactual": local_rhs_lu_counterfactual,
        "ordered_p3_summary_rows_recomputed": scalar_rows_checked,
        "ordered_p3_row_checks": ordered_p3_row_checks,
        "native_rhs_split_epsilon_by_column": {
            str(column): [value.real, value.imag]
            for column, value in native_rhs_split_epsilon.items()
        },
        "recomputed_production_splits": {
            "s_full": "sum(w^H S t) + sparse B_alpha exactly once",
            "g_full": "saved native full RHS once + sum(w^H T b_i)",
            "r_full": "native full RHS - native action - sparse B_alpha exactly once",
            "closure_grouping": "(d + r) + T_r_i - (delta_t + Q)",
        },
    }


def _task41_mesh_actual_exact_candidate_recheck(
    report_path: Path,
    *,
    expected_report_sha256: str | None = None,
    donor: Mapping[str, Any],
    donor_contract_sha256: str,
    consumer: Mapping[str, Any],
    consumer_contract_sha256: str,
    donor_contract: Mapping[str, Any],
    repo_root: Path,
    candidate_producer_contract: Mapping[str, Any] | None = None,
    candidate_producer_contract_sha256: str | None = None,
    v7_evidence_directory: Path | None = None,
    diagnostic_output_directory: Path | None = None,
) -> dict[str, Any]:
    """Independently recheck persisted exact-geometry candidate vectors, without FE work."""
    report_path = Path(report_path).resolve(strict=True)
    results_root = (Path(repo_root) / "results").resolve()
    if not report_path.is_relative_to(results_root):
        raise ValueError("exact-geometry candidate report is outside the registered results tree")
    report = _json_object(report_path, "Task41 exact-geometry candidate report")
    profile = _task41_mesh_actual_exact_candidate_profile(report_path, report)
    if profile["version"] == "v8":
        if expected_report_sha256 is None or diagnostic_output_directory is None:
            raise ValueError(
                "V8 selected trace-star checker requires its report SHA-256 and consumer output directory"
            )
        return _task41_v8_selected_trace_star_recheck(
            report_path,
            expected_report_sha256=expected_report_sha256,
            donor=donor,
            donor_contract_sha256=donor_contract_sha256,
            consumer=consumer,
            consumer_contract_sha256=consumer_contract_sha256,
            candidate_producer_contract=candidate_producer_contract,
            candidate_producer_contract_sha256=candidate_producer_contract_sha256,
            donor_contract=donor_contract,
            repo_root=repo_root,
            output_directory=diagnostic_output_directory,
        )
    candidate_prefix = profile["candidate_prefix"]
    attribution_prefix = profile["attribution_prefix"]
    if profile["version"] == "v6":
        require_prefix_qualified = _task41_v6_report_requires_prefix_qualification(
            report
        )
        _task41_validate_v6_actual_qmetric_audit(
            report.get("identity_audit", {}),
            require_prefix_qualified=require_prefix_qualified,
        )
        if require_prefix_qualified:
            _task41_validate_v6_prefix_qualification(
                report.get("candidate_prefix_qualification"),
                require_qualified=True,
            )
            incident = report["candidate_prefix_qualification"].get(
                "original_failed_row_incident_contributions"
            )
            if (
                not isinstance(incident, list)
                or len(incident) != 6
                or any(
                    item.get("cell_count") != 2
                    or item.get("frozen_denominator")
                    != TASK41_P0_V5_FROZEN_DENOMINATORS[item.get("column")]
                    or not np.isfinite(
                        item.get("difference_over_frozen_denominator", np.nan)
                    )
                    for item in incident
                )
            ):
                raise ValueError(
                    "V6 candidate report omits the two saved-cell contributions on the frozen failed row"
                )
    candidate_contract = consumer
    candidate_contract_digest = consumer_contract_sha256
    if profile["version"] == "v6":
        if (
            not isinstance(candidate_producer_contract, Mapping)
            or candidate_producer_contract_sha256 is None
        ):
            raise ValueError("V6 candidate report requires its separately bound producer contract")
        candidate_contract = candidate_producer_contract
        candidate_contract_digest = candidate_producer_contract_sha256
    if (
        report.get("geometry_policy") != "mesh_actual_exact"
        or report.get("donor_contract_sha256") != donor_contract_sha256
        or report.get("consumer_contract_sha256") != candidate_contract_digest
        or report.get("donor_source_sha") != donor_contract.get("source", {}).get("sha")
        or report.get("consumer_source_sha") != candidate_contract.get("source", {}).get("sha")
        or report.get("donor_manifest_sha256") != donor.get("manifest_sha256")
        or report.get("independent_checker_status") != "NOT_RUN"
    ):
        raise ValueError("V5 candidate report donor/consumer/geometry identity differs")
    candidate_output = report.get("output_directory")
    evidence_directory = report.get("volume_evidence_directory")
    if (
        not isinstance(candidate_output, str)
        or Path(candidate_output).resolve() != report_path.parent
        or not isinstance(evidence_directory, str)
    ):
        raise ValueError("V5 candidate output directory differs from its report path")
    evidence_root = Path(evidence_directory).resolve(strict=True)
    if not evidence_root.is_relative_to(report_path.parent.resolve()):
        raise ValueError("V5 candidate evidence arrays escape the consumer output directory")
    v7_array_directory: Path | None = None
    v7_expected_bytes = 0
    v7_evidence_accounting: dict[str, Any] | None = None
    reference_path = Path(str(report.get("geometry_reference_report_path", ""))).resolve(strict=True)
    if (
        not reference_path.is_relative_to(results_root)
        or report.get("geometry_reference_report_sha256")
        != TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256
        or sha256_file(reference_path) != TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256
    ):
        raise ValueError("V5 frozen two-cell geometry reference path/hash differs")

    manifest = donor.get("manifest")
    columns = donor.get("columns")
    if not isinstance(manifest, Mapping) or not isinstance(columns, (list, tuple)) or len(columns) != 2:
        raise ValueError("V5 candidate checker requires the normalized two-column B0 donor")
    active_rows = int(manifest.get("active_trace_rows", -1))
    port_rows = int(manifest.get("port_rows", -1))
    full_rows = int(manifest.get("full_storage_rows", -1))
    if active_rows < 1 or port_rows < 0 or full_rows < 1:
        raise ValueError("V5 donor row counts are invalid")
    candidate_rows = active_rows + port_rows

    records_raw = report.get("persisted_evidence_arrays")
    if not isinstance(records_raw, list):
        raise ValueError("V5 candidate report omits persisted evidence-array records")
    records: dict[str, Mapping[str, Any]] = {}
    for item in records_raw:
        if not isinstance(item, Mapping) or not isinstance(item.get("name"), str):
            raise ValueError("V5 candidate evidence-array record is malformed")
        name = str(item["name"])
        if name in records:
            raise ValueError(f"V5 candidate evidence-array name is duplicated: {name}")
        records[name] = item

    loaded: dict[str, np.ndarray] = {}

    def load_array(name: str, expected_shape: tuple[int, ...]) -> np.ndarray:
        record = records.get(name)
        if record is None:
            raise ValueError(f"V5 candidate evidence is missing array {name}")
        path = Path(str(record.get("path", ""))).resolve(strict=True)
        if (
            not path.is_relative_to(evidence_root)
            or path.stat().st_size != int(record.get("bytes", -1))
            or sha256_file(path) != record.get("sha256")
        ):
            raise ValueError(f"V5 candidate evidence path/hash differs for {name}")
        array = np.load(path, mmap_mode="r", allow_pickle=False)
        if (
            array.shape != expected_shape
            or array.dtype != np.dtype(np.complex128)
            or record.get("shape") != list(expected_shape)
            or record.get("dtype") != "complex128"
        ):
            raise ValueError(f"V5 candidate evidence shape/dtype differs for {name}")
        for start in range(0, int(array.shape[0]), 262_144):
            if not np.isfinite(np.asarray(array[start : start + 262_144])).all():
                raise ValueError(f"V5 candidate evidence contains non-finite values: {name}")
        loaded[name] = array
        return array

    if profile["version"] == "v6":
        if v7_evidence_directory is None:
            raise ValueError("V7 saved checker requires a dedicated closure-array directory")
        v7_array_directory = Path(v7_evidence_directory).resolve()
        if (
            not v7_array_directory.is_relative_to(results_root)
            or v7_array_directory.is_relative_to(evidence_root)
            or v7_array_directory.is_relative_to(report_path.parent.resolve())
            or v7_array_directory.exists()
        ):
            raise ValueError("V7 closure-array output must be new and separate under results")
        unique_candidate_paths: dict[str, int] = {}
        for record in records.values():
            raw_path = Path(str(record.get("path", ""))).resolve()
            byte_count = int(record.get("bytes", -1))
            if byte_count < 0:
                raise ValueError("V6 candidate inventory has an invalid byte count")
            previous = unique_candidate_paths.setdefault(str(raw_path), byte_count)
            if previous != byte_count:
                raise ValueError("V6 candidate paths have conflicting byte counts")
        donor_bytes = int(donor.get("existing_evidence_bytes", -1))
        candidate_bytes = sum(unique_candidate_paths.values())
        if donor_bytes < 0 or (
            report.get("persisted_evidence_bytes") is not None
            and int(report["persisted_evidence_bytes"]) != candidate_bytes
        ):
            raise ValueError("V7 evidence accounting differs from donor/candidate inventories")
        v7_payload_bytes = active_rows * np.dtype(np.complex128).itemsize * 2 * 4
        v7_expected_bytes = v7_payload_bytes + 4096 * 8
        evidence_cap_bytes = 16 * 1024**3
        if donor_bytes + candidate_bytes + v7_expected_bytes > evidence_cap_bytes:
            raise MemoryError("V7 closure arrays would exceed the fixed 16 GiB evidence cap")
        import shutil

        anchor = v7_array_directory.parent
        while not anchor.exists() and anchor != anchor.parent:
            anchor = anchor.parent
        free_bytes = int(shutil.disk_usage(anchor).free)
        free_floor_bytes = 2 * 1024**3
        if free_bytes < v7_expected_bytes + free_floor_bytes:
            raise OSError("V7 closure arrays would violate the fixed 2 GiB free-space floor")
        v7_evidence_accounting = {
            "donor_bytes": donor_bytes,
            "candidate_unique_path_bytes": candidate_bytes,
            "new_closure_array_payload_bytes": v7_payload_bytes,
            "new_closure_array_bytes_expected": v7_expected_bytes,
            "cumulative_bytes_expected": donor_bytes + candidate_bytes + v7_expected_bytes,
            "evidence_cap_bytes": evidence_cap_bytes,
            "free_bytes_before_write": free_bytes,
            "free_space_floor_bytes": free_floor_bytes,
        }

    candidate_p6 = load_array(f"{candidate_prefix}_full_p6", (candidate_rows, 2))
    candidate_reduced = load_array(
        f"{candidate_prefix}_full_reduced_rhs", (candidate_rows, 2)
    )
    saved_port_rhs = np.asarray(donor["attribution"]["joint"]["port_rhs"])
    if saved_port_rhs.shape != (port_rows, 2) or saved_port_rhs.dtype != np.dtype(np.complex128):
        raise ValueError("V5 inherited donor port output has an invalid shape or dtype")
    if not (
        np.array_equal(candidate_p6[active_rows:, :], saved_port_rhs)
        and np.array_equal(candidate_reduced[active_rows:, :], saved_port_rhs)
    ):
        raise ValueError("V5 candidate changed the inherited port outputs")

    action_columns = []
    for column_index, frozen_denominator in enumerate(
        TASK41_P0_V5_FROZEN_DENOMINATORS
    ):
        difference = _task41_b0_chunked_difference_summary(
            candidate_p6[:, column_index], candidate_reduced[:, column_index]
        )
        dynamic_denominator = max(
            _task41_b0_chunked_norm(candidate_p6[:, column_index]),
            _task41_b0_chunked_norm(candidate_reduced[:, column_index]),
            np.finfo(float).tiny,
        )
        dynamic_relative = difference["absolute_l2"] / dynamic_denominator
        frozen_relative = difference["absolute_l2"] / frozen_denominator
        action_columns.append(
            {
                "column": column_index,
                "difference": difference,
                "dynamic_denominator": dynamic_denominator,
                "dynamic_denominator_relative": dynamic_relative,
                "frozen_denominator": frozen_denominator,
                "frozen_denominator_relative": frozen_relative,
                "dynamic_gate_passed": dynamic_relative
                <= TASK41_P0_V5_RELATIVE_TOLERANCE,
                "frozen_gate_passed": frozen_relative
                <= TASK41_P0_V5_RELATIVE_TOLERANCE,
            }
        )
    action_status = (
        "PASS"
        if all(
            item["dynamic_gate_passed"] and item["frozen_gate_passed"]
            for item in action_columns
        )
        else "ACTUAL_COORDINATES_INSUFFICIENT"
    )
    reported_action = report.get("identity_audit", {}).get("candidate_full_action_gate")
    if (
        not isinstance(reported_action, Mapping)
        or reported_action.get("relative_tolerance") != TASK41_P0_V5_RELATIVE_TOLERANCE
        or reported_action.get("status") != action_status
        or reported_action.get("frozen_denominators_source") != profile["denominators_source"]
        or reported_action.get("full_action_artifact") != f"{candidate_prefix}_full_p6"
        or reported_action.get("full_reduced_rhs_artifact")
        != f"{candidate_prefix}_full_reduced_rhs"
        or reported_action.get("port_rows_inherited_after_validation") is not True
        or len(reported_action.get("columns", ())) != 2
    ):
        raise ValueError("V5 candidate report action-gate classification differs from recomputation")
    for actual, recorded in zip(action_columns, reported_action["columns"], strict=True):
        if not isinstance(recorded, Mapping):
            raise ValueError("V5 candidate report action column is malformed")
        for key in ("dynamic_gate_passed", "frozen_gate_passed", "frozen_denominator"):
            if recorded.get(key) != actual[key]:
                raise ValueError(f"V5 candidate report action {key} differs from recomputation")
        for key in ("dynamic_denominator", "dynamic_denominator_relative", "frozen_denominator_relative"):
            if not np.isclose(float(recorded.get(key, np.nan)), actual[key], rtol=2e-12, atol=1e-300):
                raise ValueError(f"V5 candidate report action {key} differs from recomputation")
        recorded_difference = recorded.get("difference")
        if not isinstance(recorded_difference, Mapping) or not np.isclose(
            float(recorded_difference.get("absolute_l2", np.nan)),
            actual["difference"]["absolute_l2"],
            rtol=2e-12,
            atol=1e-300,
        ):
            raise ValueError("V5 candidate report action difference differs from recomputation")
    identity_audit = report.get("identity_audit", {})
    attribution = (
        identity_audit.get("global_geometry_native_elimination_attribution")
        if isinstance(identity_audit, Mapping)
        else None
    )
    if (
        not isinstance(attribution, Mapping)
        or attribution.get("schema") != profile["action_schema"]
        or len(attribution.get("columns", ())) != 2
        or attribution.get("global_closure_status") != "DIAGNOSTIC_ONLY"
        or attribution.get("diagnostic_scales") != [
            "left_and_right_identity_norms",
            "frozen_candidate_denominator",
            "sum_of_accumulated_term_norms",
        ]
    ):
        raise ValueError("V5 global attribution receipt is missing or malformed")
    if profile["version"] == "v6":
        _task41_v6_global_attribution_identity_binding(attribution, identity_audit)
    closure_results = []
    v7_formula_columns = []
    expected_artifact_names: set[str] = {
        f"{candidate_prefix}_full_p6",
        f"{candidate_prefix}_full_reduced_rhs",
    }
    recovery_gate = report.get("identity_audit", {}).get("candidate_recovery_gate")
    if (
        not isinstance(recovery_gate, Mapping)
        or recovery_gate.get("relative_forward_tolerance") != 1.0e-11
        or recovery_gate.get("native_volume_residual_relative_tolerance") != 1.0e-10
        or recovery_gate.get("native_volume_action_count") != 2
        or recovery_gate.get("recovery_source")
        != "saved native_volume_rhs with the current exact-geometry owner"
        or not isinstance(recovery_gate.get("columns"), list)
        or len(recovery_gate["columns"]) != 2
    ):
        raise ValueError("V5 candidate report omits the two-column affected recovery gate")
    recovery_results = []
    for column_index, (recorded, donor_column) in enumerate(
        zip(recovery_gate["columns"], columns, strict=True)
    ):
        if not isinstance(recorded, Mapping) or recorded.get("column") != column_index:
            raise ValueError("V5 candidate recovery column record is malformed")
        expected_names = {
            "recovered_storage_artifact": (
                f"{candidate_prefix}_recovered_storage_col{column_index}",
                "recovered_storage",
            ),
            "native_volume_residual_artifact": (
                f"{candidate_prefix}_native_volume_residual_col{column_index}",
                "native_volume_residual",
            ),
        }
        arrays = {}
        for field, (name, label) in expected_names.items():
            artifact = recorded.get(field)
            record = records.get(name)
            if (
                not isinstance(artifact, Mapping)
                or artifact.get("name") != name
                or not isinstance(record, Mapping)
                or any(
                    artifact.get(key) != record.get(key)
                    for key in ("path", "sha256", "bytes", "shape", "dtype")
                )
            ):
                raise ValueError(f"V5 candidate {label} artifact metadata differs")
            expected_artifact_names.add(name)
            arrays[label] = load_array(name, (full_rows,))
        known = np.asarray(donor_column["known_field"], dtype=np.complex128)
        rhs = np.asarray(donor_column["native_volume_rhs"], dtype=np.complex128)
        active_original = np.asarray(donor_column["active_original_rows"], dtype=np.int64)
        slave_rows = np.asarray(donor_column["slave_rows"], dtype=np.int64)
        recovered = arrays["recovered_storage"]
        residual = arrays["native_volume_residual"]
        if (
            known.shape != (full_rows,)
            or rhs.shape != (full_rows,)
            or active_original.shape != (active_rows,)
            or slave_rows.ndim != 1
        ):
            raise ValueError(f"V5 candidate recovery vectors have invalid donor layout in column {column_index}")
        forward = _task41_b0_chunked_difference_summary(recovered, known)
        forward_relative = forward["absolute_l2"] / max(
            _task41_b0_chunked_norm(known), np.finfo(float).tiny
        )
        residual_norm = _task41_b0_chunked_norm(residual)
        residual_relative = residual_norm / max(
            _task41_b0_chunked_norm(rhs), np.finfo(float).tiny
        )
        active_trace_exact = _task41_b0_indexed_arrays_equal(
            recovered, known, active_original
        )
        slave_rows_zero = _task41_b0_indexed_arrays_equal(
            recovered, recovered, slave_rows, zero=True
        )
        residual_slave_rows_zero = _task41_b0_indexed_arrays_equal(
            residual, residual, slave_rows, zero=True
        )
        forward_passed = bool(
            np.isfinite(forward_relative) and forward_relative <= 1.0e-11
        )
        residual_passed = bool(
            np.isfinite(residual_relative) and residual_relative <= 1.0e-10
        )
        passed = bool(
            forward_passed
            and residual_passed
            and active_trace_exact
            and slave_rows_zero
            and residual_slave_rows_zero
        )
        for key, actual in (
            ("forward_error_absolute_l2", forward["absolute_l2"]),
            ("forward_error_relative", forward_relative),
            ("native_volume_residual_absolute_l2", residual_norm),
            ("native_volume_residual_relative", residual_relative),
        ):
            if not np.isclose(float(recorded.get(key, np.nan)), actual, rtol=2e-12, atol=1e-300):
                raise ValueError(f"V5 candidate recovery {key} differs from independent recheck")
        for key, actual in (
            ("forward_gate_passed", forward_passed),
            ("native_volume_residual_gate_passed", residual_passed),
            ("active_trace_exact", active_trace_exact),
            ("slave_rows_zero", slave_rows_zero),
            ("residual_slave_rows_zero", residual_slave_rows_zero),
            ("passed", passed),
        ):
            if recorded.get(key) is not actual:
                raise ValueError(f"V5 candidate recovery {key} differs from independent recheck")
        recovery_results.append(
            {
                "column": column_index,
                "forward_error_relative": forward_relative,
                "native_volume_residual_relative": residual_relative,
                "active_trace_exact": active_trace_exact,
                "slave_rows_zero": slave_rows_zero,
                "residual_slave_rows_zero": residual_slave_rows_zero,
                "passed": passed,
            }
        )
    recovery_status = (
        "PASS" if all(item["passed"] for item in recovery_results) else "ACTUAL_COORDINATES_INSUFFICIENT"
    )
    if recovery_gate.get("status") != recovery_status:
        raise ValueError("V5 candidate recovery-gate classification differs from independent recheck")
    if v7_array_directory is not None:
        if v7_array_directory.exists():
            raise FileExistsError("V7 closure-array output directory appeared after preflight")
        import shutil

        anchor = v7_array_directory.parent
        while not anchor.exists() and anchor != anchor.parent:
            anchor = anchor.parent
        free_before_write = int(shutil.disk_usage(anchor).free)
        if free_before_write < v7_expected_bytes + 2 * 1024**3:
            raise OSError("V7 closure-array output lost its fixed 2 GiB free-space reserve")
        v7_array_directory.mkdir(parents=True, exist_ok=False)
        if v7_evidence_accounting is not None:
            v7_evidence_accounting["free_bytes_before_write"] = free_before_write
    for column_index, (column_report, donor_column) in enumerate(
        zip(attribution["columns"], columns, strict=True)
    ):
        active_original = np.asarray(donor_column["active_original_rows"], dtype=np.int64)
        native_rhs = np.asarray(donor_column["native_rhs"], dtype=np.complex128)
        native_volume_rhs = np.asarray(
            donor_column["native_volume_rhs"], dtype=np.complex128
        )
        b_alpha_rows = np.asarray(donor_column["b_alpha_rows"], dtype=np.int64)
        b_alpha_values = np.asarray(donor_column["b_alpha_values"], dtype=np.complex128)
        if (
            active_original.shape != (active_rows,)
            or native_rhs.ndim != 1
            or native_volume_rhs.shape != native_rhs.shape
            or b_alpha_rows.shape != b_alpha_values.shape
            or b_alpha_rows.ndim != 1
            or b_alpha_values.dtype != np.dtype(np.complex128)
            or not np.isfinite(b_alpha_values).all()
            or (b_alpha_rows.size and (np.any(b_alpha_rows < 0) or np.any(b_alpha_rows >= full_rows)))
        ):
            raise ValueError(f"V5 donor column {column_index} has invalid trace rows")
        donor_states = {str(item["label"]): item for item in donor_column["states"]}
        state_reports = column_report.get("states")
        if not isinstance(state_reports, list) or set(
            str(item.get("state")) for item in state_reports if isinstance(item, Mapping)
        ) != set(donor_states):
            raise ValueError(f"V5 attribution states differ in column {column_index}")
        if profile["version"] == "v6" and set(donor_states) != {"j0", "j3"}:
            raise ValueError("V7 donor attribution requires the bound j0 and j3 states")
        slave_rows = np.asarray(donor_column["slave_rows"], dtype=np.int64)
        if b_alpha_rows.size and slave_rows.size and np.isin(b_alpha_rows, slave_rows).any():
            raise ValueError("V7 saved B-alpha has support on an MPC slave row")
        _task41_b0_v7_map_original_rows_to_active(b_alpha_rows, active_original)
        nonactive_rhs_difference = _task41_b0_v7_nonactive_rhs_difference(
            native_rhs, native_volume_rhs, active_original
        )
        if profile["version"] == "v6":
            volume_d_name = f"task41_v4_d_volume_trace_col{column_index}"
            expected_artifact_names.add(volume_d_name)
            d_volume = load_array(volume_d_name, (active_rows,))
            d_full = np.asarray(candidate_p6[:active_rows, column_index]) - np.asarray(
                candidate_reduced[:active_rows, column_index]
            )
        else:
            d_volume = d_full = None
        v7_states = []
        for state_report in state_reports:
            state_label = str(state_report["state"])
            donor_state = donor_states[state_label]
            native_action = np.asarray(
                donor_state["native_volume_action"], dtype=np.complex128
            )
            if native_action.shape != native_rhs.shape:
                raise ValueError("V5 native RHS/action vectors differ in shape")
            state_storage = np.asarray(donor_state["storage"], dtype=np.complex128)
            known_field = np.asarray(donor_column["known_field"], dtype=np.complex128)
            if (
                state_storage.shape != native_rhs.shape
                or known_field.shape != native_rhs.shape
                or not _task41_b0_indexed_arrays_equal(
                    state_storage, known_field, active_original
                )
            ):
                raise ValueError("V7 donor j0/j3 state trace differs from its bound known field")
            artifact_report = state_report.get("accumulator_artifacts")
            if not isinstance(artifact_report, Mapping):
                raise ValueError("V5 attribution report omits full accumulator vectors")
            arrays = {}
            for field in ("T_r_i", "delta_t", "attributed_terms"):
                artifact = artifact_report.get(field)
                if not isinstance(artifact, Mapping) or not isinstance(artifact.get("name"), str):
                    raise ValueError(f"V5 attribution artifact {field} is malformed")
                name = str(artifact["name"])
                expected_name = f"{attribution_prefix}_col{column_index}_{state_label}_{field}"
                if name != expected_name:
                    raise ValueError("V5 attribution artifact name is not bound to its column/state")
                expected_artifact_names.add(name)
                record = records.get(name)
                if not isinstance(record, Mapping) or any(
                    artifact.get(key) != record.get(key)
                    for key in ("path", "sha256", "bytes", "shape", "dtype")
                ):
                    raise ValueError(f"V5 attribution artifact record differs for {name}")
                arrays[field] = load_array(name, (active_rows,))
            lhs_sq = rhs_sq = error_sq = 0.0
            accumulated_term_norm_squares = [0.0] * 5
            max_abs = 0.0
            for start in range(0, active_rows, 262_144):
                stop = min(active_rows, start + 262_144)
                d = np.asarray(candidate_p6[start:stop, column_index]) - np.asarray(
                    candidate_reduced[start:stop, column_index]
                )
                r_t = (
                    native_rhs[active_original[start:stop]]
                    - native_action[active_original[start:stop]]
                )
                t_r_i = np.asarray(arrays["T_r_i"][start:stop])
                delta_t = np.asarray(arrays["delta_t"][start:stop])
                attributed_terms = np.asarray(arrays["attributed_terms"][start:stop])
                lhs = d + r_t + t_r_i
                rhs = delta_t + attributed_terms
                difference = lhs - rhs
                if not all(np.isfinite(value).all() for value in (lhs, rhs, difference)):
                    raise ValueError("V5 attribution closure contains non-finite values")
                lhs_sq += float(np.vdot(lhs, lhs).real)
                rhs_sq += float(np.vdot(rhs, rhs).real)
                error_sq += float(np.vdot(difference, difference).real)
                for term_index, term in enumerate((d, r_t, t_r_i, delta_t, attributed_terms)):
                    accumulated_term_norm_squares[term_index] += float(np.vdot(term, term).real)
                if difference.size:
                    max_abs = max(max_abs, float(np.max(np.abs(difference))))
            closure_l2 = float(np.sqrt(max(0.0, error_sq)))
            lhs_l2 = float(np.sqrt(max(0.0, lhs_sq)))
            rhs_l2 = float(np.sqrt(max(0.0, rhs_sq)))
            frozen_relative = closure_l2 / TASK41_P0_V5_FROZEN_DENOMINATORS[column_index]
            accumulation_scale = float(
                sum(np.sqrt(max(0.0, value)) for value in accumulated_term_norm_squares)
            )
            accumulation_relative = closure_l2 / max(accumulation_scale, np.finfo(float).tiny)
            recorded_closure = state_report.get("closure_difference")
            if (
                not isinstance(recorded_closure, Mapping)
                or not np.isclose(
                    float(recorded_closure.get("absolute_l2", np.nan)),
                    closure_l2,
                    rtol=2e-12,
                    atol=1e-300,
                )
                or not np.isclose(
                    float(recorded_closure.get("max_abs", np.nan)),
                    max_abs,
                    rtol=2e-12,
                    atol=1e-300,
                )
                or not np.isclose(
                    float(state_report.get("left_d_plus_r_t_plus_T_r_i_l2", np.nan)),
                    lhs_l2,
                    rtol=2e-12,
                    atol=1e-300,
                )
                or not np.isclose(
                    float(state_report.get("right_delta_t_plus_local_defects_l2", np.nan)),
                    rhs_l2,
                    rtol=2e-12,
                    atol=1e-300,
                )
                or not np.isclose(
                    float(state_report.get("closure_frozen_denominator", np.nan)),
                    TASK41_P0_V5_FROZEN_DENOMINATORS[column_index],
                    rtol=0.0,
                    atol=0.0,
                )
                or not np.isclose(
                    float(state_report.get("closure_frozen_denominator_relative", np.nan)),
                    frozen_relative,
                    rtol=2e-12,
                    atol=1e-300,
                )
                or not np.isclose(
                    float(state_report.get("accumulation_scale_l2_sum", np.nan)),
                    accumulation_scale,
                    rtol=2e-12,
                    atol=1e-300,
                )
                or not np.isclose(
                    float(state_report.get("closure_relative_to_accumulation_scale", np.nan)),
                    accumulation_relative,
                    rtol=2e-12,
                    atol=1e-300,
                )
            ):
                raise ValueError("V5 global closure diagnostics differ from independent vector recheck")
            closure_results.append(
                {
                    "column": column_index,
                    "state": state_label,
                    "absolute_l2": closure_l2,
                    "max_abs": max_abs,
                    "left_l2": lhs_l2,
                    "right_l2": rhs_l2,
                    "frozen_denominator": TASK41_P0_V5_FROZEN_DENOMINATORS[column_index],
                    "frozen_denominator_relative": frozen_relative,
                    "accumulation_scale": accumulation_scale,
                    "relative_to_accumulation_scale": accumulation_relative,
                }
            )
            if profile["version"] != "v6":
                continue
            reduce_volume_name = (
                f"task41_v4_reduce_r_volume_{state_label}_col{column_index}"
            )
            reduce_full_name = f"task41_v4_reduce_r_full_{state_label}_col{column_index}"
            expected_artifact_names.update((reduce_volume_name, reduce_full_name))
            formula = _task41_b0_v7_attribution_state_recheck(
                candidate_d_full=d_full,
                candidate_d_volume=d_volume,
                active_original_rows=active_original,
                native_rhs=native_rhs,
                native_volume_rhs=native_volume_rhs,
                b_alpha_rows=b_alpha_rows,
                b_alpha_values=b_alpha_values,
                native_volume_action=native_action,
                T_r_i=arrays["T_r_i"],
                delta_t=arrays["delta_t"],
                attributed_terms=arrays["attributed_terms"],
                reduce_r_volume=load_array(reduce_volume_name, (active_rows,)),
                reduce_r_full=load_array(reduce_full_name, (active_rows,)),
                frozen_denominator=TASK41_P0_V5_FROZEN_DENOMINATORS[column_index],
                evidence_directory=v7_array_directory,
                evidence_prefix=(
                    f"task41_p0_v7_attribution_col{column_index}_{state_label}"
                    if profile["version"] == "v6"
                    else None
                ),
            )
            v7_states.append(
                {
                    "state": state_label,
                    "diagnostics": formula["diagnostics"],
                    "epsilon_rhs_native_minus_volume_minus_Balpha": formula[
                        "epsilon_rhs_native_minus_volume_minus_Balpha"
                    ],
                    "legacy_closure_beta_active_l2": formula[
                        "legacy_closure_beta_active_l2"
                    ],
                    "legacy_beta_conjugate_inner_product": formula[
                        "legacy_beta_conjugate_inner_product"
                    ],
                    "persisted_closure_arrays": formula["persisted_closure_arrays"],
                    "_d_hat_volume": formula["_d_hat_volume"],
                    "_d_hat_full": formula["_d_hat_full"],
                }
            )
        state_consistency = {}
        if len(v7_states) == 2:
            left_state, right_state = v7_states
            state_consistency = {
                "d_hat_volume_between_donor_states": _task41_b0_chunked_difference_summary(
                    left_state["_d_hat_volume"], right_state["_d_hat_volume"]
                ),
                "d_hat_full_between_donor_states": _task41_b0_chunked_difference_summary(
                    left_state["_d_hat_full"], right_state["_d_hat_full"]
                ),
            }
        rhs_split_receipt = (
            v7_states[0]["epsilon_rhs_native_minus_volume_minus_Balpha"]
            if v7_states
            else None
        )
        surface_support = donor.get("manifest", {}).get(
            "saved_surface_support_certificate", {}
        )
        interior_rhs_identity_verified = bool(
            profile["version"] == "v6"
            and nonactive_rhs_difference["absolute_l2"] == 0.0
            and isinstance(surface_support, Mapping)
            and surface_support.get("cell_interior_nonzero_values") == 0
            and donor.get("manifest", {}).get("local_interior_Bi_Di_exact_zero") is True
        )
        for state in v7_states:
            state.pop("_d_hat_volume")
            state.pop("_d_hat_full")
        v7_formula_columns.append(
            {
                "column": column_index,
                "states": v7_states,
                "same_trace_donor_state_consistency": state_consistency,
                "B_alpha_rows_map_once_to_active_trace": profile["version"] == "v6",
                "interior_f_equals_b_verified": interior_rhs_identity_verified,
                "interior_rhs_identity_basis": {
                    "native_rhs_minus_native_volume_rhs_on_nonactive_rows": nonactive_rhs_difference,
                    "full_rhs_split_epsilon_absolute_l2": rhs_split_receipt.get("absolute_l2")
                    if isinstance(rhs_split_receipt, Mapping)
                    else None,
                    "saved_cell_interior_nonzero_values": surface_support.get(
                        "cell_interior_nonzero_values"
                    )
                    if isinstance(surface_support, Mapping)
                    else None,
                    "local_interior_Bi_Di_exact_zero": donor.get("manifest", {}).get(
                        "local_interior_Bi_Di_exact_zero"
                    ),
                },
                "candidate_initial_recovery_is_separate": True,
            }
        )
    if set(records) & expected_artifact_names != expected_artifact_names:
        raise ValueError("V5 candidate report is missing independently consumed evidence arrays")
    closure_status = "DIAGNOSTIC_ONLY"
    candidate_status = (
        "PASS" if action_status == "PASS" and recovery_status == "PASS"
        else "ACTUAL_COORDINATES_INSUFFICIENT"
    )
    if report.get("candidate_numeric_status") != candidate_status:
        raise ValueError("V5 candidate numeric status differs from independent action/recovery recheck")
    run_status = (
        "CANDIDATE_NUMERICAL_PASS_CHECKER_PENDING"
        if candidate_status == "PASS"
        else "ACTUAL_COORDINATES_INSUFFICIENT"
    )
    if report.get("status") != run_status or attribution.get("global_closure_status") != closure_status:
        raise ValueError("V5 candidate/action or attribution-diagnostic classification differs from independent recheck")
    if v7_array_directory is not None and v7_evidence_accounting is not None:
        closure_records = [
            record
            for column in v7_formula_columns
            for state in column["states"]
            for record in state["persisted_closure_arrays"].values()
        ]
        actual_new_bytes = sum(int(record["bytes"]) for record in closure_records)
        if actual_new_bytes > v7_expected_bytes or len(closure_records) != 8:
            raise ValueError("V7 corrected closure array inventory differs from its preflight")
        v7_evidence_accounting.update(
            {
                "new_closure_array_bytes_actual": actual_new_bytes,
                "cumulative_bytes_actual": int(v7_evidence_accounting["donor_bytes"])
                + int(v7_evidence_accounting["candidate_unique_path_bytes"])
                + actual_new_bytes,
                "closure_array_bytes_expected_upper": v7_expected_bytes,
                "closure_array_records": closure_records,
                "evidence_directory": str(v7_array_directory),
            }
        )
    return {
        "schema": profile["check_schema"],
        "check_completed": True,
        "report_classification_matches": True,
        "action_status": action_status,
        "action_passed": action_status == "PASS",
        "recovery_status": recovery_status,
        "recovery_passed": recovery_status == "PASS",
        "recovery_columns": recovery_results,
        "attribution_closure_status": closure_status,
        "attribution_closure_passed": None,
        "candidate_passed": candidate_status == "PASS",
        "candidate_status": candidate_status,
        "action_columns": action_columns,
        "global_closure_states": closure_results,
        "attribution_v7_formula_recheck": {
            "schema": "task41.p0.v7.saved_full_volume_attribution_recheck.v1",
            "independently_recomputed_from_hash_bound_arrays": True,
            "legacy_global_closure_preserves_v6_formula": True,
            "corrected_full_residual": "native_rhs_trace - native_volume_action_trace - B_alpha_trace",
            "corrected_volume_residual": "native_volume_rhs_trace - native_volume_action_trace",
            "corrected_full_identity": "d_full + r_full_trace + T_r_i = delta_t + attributed_terms",
            "corrected_volume_identity": "d_volume + r_volume_trace + T_r_i = delta_t + attributed_terms",
            "formula_status": "DIAGNOSTIC_ONLY"
            if profile["version"] == "v6"
            else "NOT_APPLICABLE_V5",
            "columns": v7_formula_columns,
            "evidence_accounting": v7_evidence_accounting,
        },
        "candidate_report_path": str(report_path),
        "candidate_report_sha256": sha256_file(report_path),
        "candidate_producer_source_sha": candidate_contract.get("source", {}).get("sha"),
        "candidate_producer_contract_sha256": candidate_contract_digest,
        "checker_consumer_source_sha": consumer.get("source", {}).get("sha"),
        "checker_consumer_contract_sha256": consumer_contract_sha256,
        "geometry_reference_report_sha256": TASK41_P0_V5_GEOMETRY_REFERENCE_SHA256,
        "candidate_arrays_rehashed_and_reopened": True,
        "port_outputs_inherited_unchanged": True,
    }


def check_task41_p0_b0_saved_evidence_audit(
    *,
    summary_path: Path,
    numerical_output: Path,
    contract_path: Path,
    contract_sha256: str,
    consumer_contract_path: Path,
    consumer_contract_sha256: str,
    output_path: Path,
    repo_root: Path,
    mesh_actual_exact_report_path: Path | None = None,
    mesh_actual_exact_report_sha256: str | None = None,
) -> dict[str, Any]:
    """Audit producer arrays read-only under a separately bound consumer window/source."""
    if (mesh_actual_exact_report_path is None) != (mesh_actual_exact_report_sha256 is None):
        raise ValueError("saved B0 candidate report requires both explicit path and SHA-256")
    donor, donor_digest = require_task41_p0_contract(
        contract_path,
        expected_sha256=contract_sha256,
        current_root=repo_root,
        check_current_source=False,
        require_clean_source=False,
    )
    consumer, consumer_digest = require_task41_p0_contract(
        consumer_contract_path,
        expected_sha256=consumer_contract_sha256,
        current_root=repo_root,
        check_current_source=True,
        require_clean_source=True,
        case_id="B0",
    )
    donor_case = donor.get("case")
    consumer_case = consumer.get("case")
    if (
        not isinstance(donor_case, Mapping)
        or not isinstance(consumer_case, Mapping)
        or task41_case_id_for_run_id(str(donor_case.get("run_id", ""))) != "B0"
        or task41_case_id_for_run_id(str(consumer_case.get("run_id", ""))) != "B0"
    ):
        raise ValueError("saved B0 audit requires frozen B0 donor and consumer contracts")
    for key in (
        "model_id",
        "method",
        "mpi_size",
        "input_sha256",
        "physical_model_sha256",
        "resolved_config_sha256",
    ):
        if donor_case.get(key) != consumer_case.get(key):
            raise ValueError(f"saved B0 donor/consumer contracts differ at {key}")

    summary_path = summary_path.resolve(strict=True)
    donor_directory = summary_path.parent
    numerical_output = numerical_output.resolve()
    expected_numerical_output = donor_directory / "numerical_output"
    if numerical_output != expected_numerical_output or (
        numerical_output.exists() and not numerical_output.is_dir()
    ):
        raise ValueError(
            "saved B0 donor numerical-output path differs from its bound logical child"
        )
    output_path = output_path.resolve()
    output_root = (repo_root / "results").resolve()
    if (
        summary_path.name != "task40_v10_p6_candidate_summary.json"
        or not output_path.is_relative_to(output_root)
        or output_path.is_relative_to(donor_directory)
        or output_path.name != "task41_p0_b0_saved_evidence_audit.json"
        or output_path.exists()
        or output_path.with_name(output_path.name + ".tmp").exists()
    ):
        raise ValueError("saved B0 audit output must be a new file in a separate consumer result directory")

    run_manifest_path = donor_directory / "run_manifest.json"
    if not run_manifest_path.is_file():
        raise ValueError("saved B0 donor run manifest is missing")
    run_manifest = _json_object(run_manifest_path, "saved B0 donor run manifest")
    launcher_summary_path = donor_directory / "run_summary.json"
    launcher_summary = _json_object(launcher_summary_path, "saved B0 donor run summary")
    summary = _json_object(summary_path, "saved B0 donor candidate summary")
    expected_manifest = {
        "run_id": donor_case.get("run_id"),
        "model_id": donor_case.get("model_id"),
        "method": donor_case.get("method"),
        "mpi_size": donor_case.get("mpi_size"),
        "input_sha256": donor_case.get("input_sha256"),
        "physical_model_sha256": donor_case.get("physical_model_sha256"),
        "resolved_config_sha256": donor_case.get("resolved_config_sha256"),
        "source_sha": donor.get("source", {}).get("sha")
        if isinstance(donor.get("source"), Mapping)
        else None,
    }
    if any(run_manifest.get(key) != value for key, value in expected_manifest.items()):
        raise ValueError("saved B0 donor manifest differs from its frozen producer contract")
    if (
        summary.get("run_id") != donor_case.get("run_id")
        or launcher_summary.get("run_id") != donor_case.get("run_id")
        or Path(str(run_manifest.get("output_directory", ""))).resolve() != donor_directory
        or Path(str(run_manifest.get("numerical_output_directory", ""))).resolve()
        != numerical_output
        or Path(str(launcher_summary.get("output_directory", ""))).resolve()
        != donor_directory
        or Path(str(launcher_summary.get("numerical_output_directory", ""))).resolve()
        != numerical_output
    ):
        raise ValueError("saved B0 donor summaries and numerical-output path differ")
    input_path = donor_directory / "input_original.dat"
    config_path = donor_directory / "resolved_config.json"
    if (
        not input_path.is_file()
        or sha256_file(input_path) != donor_case.get("input_sha256")
        or not config_path.is_file()
        or sha256_file(config_path) != donor_case.get("resolved_config_sha256")
    ):
        raise ValueError("saved B0 donor input/config identity differs from its frozen contract")

    evidence = _task41_b0_recovery_evidence_checks(
        summary,
        numerical_output,
        donor,
        contract_sha256=donor_digest,
        checkpoint_path=output_path,
        checkpoint_identity={
            "donor_contract_sha256": donor_digest,
            "donor_source_sha": donor.get("source", {}).get("sha"),
            "donor_window_sha256": donor.get("window", {}).get("sha256"),
            "consumer_contract_sha256": consumer_digest,
            "consumer_source_sha": consumer.get("source", {}).get("sha"),
            "consumer_window_sha256": consumer.get("window", {}).get("sha256"),
        },
    )
    mesh_actual_candidate_check = None
    candidate_producer_contract = None
    candidate_producer_contract_sha256 = None
    if mesh_actual_exact_report_path is not None:
        candidate_producer_contract, candidate_producer_contract_sha256 = (
            _task41_v6_candidate_producer_contract(
                mesh_actual_exact_report_path,
                expected_report_sha256=str(mesh_actual_exact_report_sha256),
                consumer_contract=consumer,
                repo_root=repo_root,
            )
        )
        normalized_donor = load_task41_v4_volume_only_donor(
            summary_path=summary_path, numerical_output=numerical_output
        )
        mesh_actual_candidate_check = _task41_mesh_actual_exact_candidate_recheck(
            mesh_actual_exact_report_path,
            expected_report_sha256=mesh_actual_exact_report_sha256,
            donor=normalized_donor,
            donor_contract_sha256=donor_digest,
            donor_contract=donor,
            consumer=consumer,
            consumer_contract_sha256=consumer_digest,
            repo_root=repo_root,
            candidate_producer_contract=candidate_producer_contract,
            candidate_producer_contract_sha256=candidate_producer_contract_sha256,
            v7_evidence_directory=(
                output_path.with_name(output_path.stem + "_v7_attribution_arrays")
            ),
            diagnostic_output_directory=output_path.parent,
        )
    audit_completed = bool(evidence.get("audit_completed") is True) and (
        mesh_actual_candidate_check is None
        or mesh_actual_candidate_check.get("check_completed") is True
    )
    payload = {
        "schema": "task41.p0.b0.saved_evidence_audit.v1",
        "status": "COMPLETE" if audit_completed else "INCOMPLETE",
        "audit_completed": audit_completed,
        "data_integrity": evidence.get("data_integrity") is True,
        "recovery_passed": evidence.get("recovery_passed") is True,
        "joint_action_passed": evidence.get("joint_action_passed"),
        "qualification_passed": evidence.get("qualification_passed") is True,
        "official_result": False,
        "donor": {
            "run_id": donor_case.get("run_id"),
            "source_sha": donor.get("source", {}).get("sha"),
            "contract_sha256": donor_digest,
            "window_sha256": donor.get("window", {}).get("sha256"),
            "run_directory": str(donor_directory),
            "run_manifest_sha256": sha256_file(run_manifest_path),
            "launcher_summary_sha256": sha256_file(launcher_summary_path),
            "candidate_summary_sha256": sha256_file(summary_path),
            "launcher_result_classification": launcher_summary.get("result_classification"),
        },
        "consumer": {
            "run_id": consumer_case.get("run_id"),
            "source_sha": consumer.get("source", {}).get("sha"),
            "contract_sha256": consumer_digest,
            "window_sha256": consumer.get("window", {}).get("sha256"),
        },
        "recovery_evidence_recheck": evidence,
        **(
            {"mesh_actual_exact_candidate_check": mesh_actual_candidate_check}
            if mesh_actual_candidate_check is not None
            else {}
        ),
        "checkpoints": evidence.get("checkpoints", []),
        "raw_evidence_retained": True,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output_path)
    return payload


def _task41_b0_numerical_checks(
    summary: Mapping[str, Any],
    numerical_output: Path,
    contract: Mapping[str, Any],
    *,
    contract_path: Path,
    contract_sha256: str,
    repo_root: Path,
) -> dict[str, Any]:
    """Reopen B0's identity-bound all-mode and q-map records independently."""
    from src.solvers import task41_b0_mode_inventory as inventory_module
    from src.solvers.task41_b0_mode_inventory import TASK41_B0_MODE_COUNT

    errors: list[str] = []
    case = contract.get("case", {})
    window = contract.get("window", {})
    authority = summary.get("campaign_authority", {})
    if not isinstance(case, Mapping) or not isinstance(window, Mapping):
        return {"errors": ["Task41 B0 contract case/window is malformed"]}
    if not isinstance(authority, Mapping):
        authority = {}
    from src.runners.task41_p0_contract import task41_raw_artifact_limit_bytes

    expected_raw_limit = task41_raw_artifact_limit_bytes(contract)
    if contract.get("evidence", {}).get("raw_disk_policy") is not None and (
        summary.get("raw_artifact_limit_bytes") != expected_raw_limit
        or authority.get("raw_artifact_limit_bytes") != expected_raw_limit
    ):
        errors.append("Task41 B0 raw evidence limit differs from its approved contract")
    expected_identity = {
        "run_id": TASK41_B0_RUN_ID,
        "profile": TASK41_B0_PRECONDITIONER,
        "stage": "TASK41_B0",
        "source_sha": contract.get("source", {}).get("sha")
        if isinstance(contract.get("source"), Mapping)
        else None,
    }
    for key, expected in expected_identity.items():
        if summary.get(key) != expected:
            errors.append(f"Task41 B0 candidate summary {key} differs from the fixed contract")
    if (
        case.get("run_id") != TASK41_B0_RUN_ID
        or case.get("profile_identity") != TASK41_B0_PRECONDITIONER
        or case.get("solver_stage") != "TASK41_B0"
        or case.get("comparison_group") != TASK41_B0_COMPARISON_GROUP
        or case.get("geometry_identity") != TASK41_B0_GEOMETRY_IDENTITY
        or case.get("method") != "full3d_iterative"
        or contract.get("comparison") is not None
        or contract.get("q_csr_reuse") is not None
    ):
        errors.append("Task41 B0 fixed contract has a changed identity or donor binding")
    expected_window_path = (repo_root / str(window.get("path", ""))).resolve()
    if (
        authority.get("case_id") != "B0"
        or Path(str(authority.get("task41_contract_path", ""))).resolve()
        != contract_path.resolve()
        or authority.get("task41_contract_sha256") != contract_sha256
        or authority.get("source_sha") != expected_identity["source_sha"]
        or authority.get("campaign_window_sha256") != window.get("sha256")
        or Path(str(authority.get("campaign_window_path", ""))).resolve()
        != expected_window_path
    ):
        errors.append("Task41 B0 campaign authority differs from the fixed contract/window")
    abi_facts = summary.get("abi")
    runtime_contract = contract.get("runtime")
    if (
        not isinstance(abi_facts, Mapping)
        or not isinstance(runtime_contract, Mapping)
        or runtime_contract.get("profile") != "native_linux"
        or abi_facts.get("profile_identity") != TASK41_B0_PRECONDITIONER
        or abi_facts.get("runtime_profile") != runtime_contract.get("profile")
        or abi_facts.get("receipt_sha256")
        != runtime_contract.get("abi_receipt_sha256")
        or abi_facts.get("qualification")
        != "task41_p0_contract_receipt_bound"
        or abi_facts.get("scalar") != "complex128"
        or abi_facts.get("integer") != "int32"
        or abi_facts.get("mpi_size") != 1
    ):
        errors.append(
            "Task41 B0 mode-manifest ABI identity differs from the frozen native contract receipt"
        )
    if (
        summary.get("precision_status") != "NOT_QUALIFIED"
        or summary.get("mode_truncation_status") != "MODE_TRUNCATION_UNQUALIFIED"
        or summary.get("comparison_authority") is not None
        or "task41_a1_a2_comparison" in summary
        or summary.get("live_mode_inventory_status") != "LIVE_CAPTURED_AND_HASH_VERIFIED"
    ):
        errors.append("Task41 B0 qualification labels or no-comparison status changed")

    inventory = summary.get("b0_mode_inventory")
    periodic = summary.get("periodic_inventory_expectations")
    if not isinstance(inventory, Mapping) or not isinstance(periodic, Mapping):
        return {"errors": errors + ["Task41 B0 summary omits its live inventory/profile"]}
    run_directory = numerical_output.parent.resolve()
    b0_profile_capability = None
    try:
        b0_profile_capability = inventory_module.recheck_task41_b0_mode_inventory(
            run_directory,
            inventory,
            source_sha=str(expected_identity["source_sha"]),
            input_sha256=str(case.get("input_sha256", "")),
            abi_facts=abi_facts,
        )
        if (
            periodic.get("name") != TASK41_B0_PRECONDITIONER
            or periodic.get("name") != b0_profile_capability["identity"]
            or periodic.get("q_count") != b0_profile_capability["q_count"]
            or periodic.get("mode_count") != b0_profile_capability["mode_count"]
            or periodic.get("q_port_counts") != b0_profile_capability["q_port_counts"]
            or periodic.get("sector_port_counts")
            != b0_profile_capability["sector_port_counts"]
            or summary.get("b0_profile_capability") != b0_profile_capability
        ):
            errors.append("Task41 B0 periodic profile differs from the reopened mode/q capability")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors.append(f"Task41 B0 verified profile capability failed: {exc}")
    q_counts = (
        b0_profile_capability.get("q_port_counts")
        if isinstance(b0_profile_capability, Mapping)
        else None
    )
    sector_counts = (
        b0_profile_capability.get("sector_port_counts")
        if isinstance(b0_profile_capability, Mapping)
        else None
    )

    iterative_reference_recheck = None
    recovery_evidence_recheck = None
    reference_tier_recheck = None
    output_packet_recheck = None
    post_release_recheck = None
    factor_release_recheck = None
    power_recheck = None
    if (
        summary.get("status") != "PASS"
        or summary.get("official_result") is not True
        or summary.get("numeric_gates_passed") is not True
        or summary.get("output_gates_passed") is not True
        or summary.get("solver_status") != "TRUE_RESIDUAL_PASS"
        or summary.get("comparison_authority") is not None
        or "task41_a1_a2_comparison" in summary
    ):
        errors.append("Task41 B0 worker result or no-comparison outcome did not pass")
    try:
        iterative_reference_recheck = _task41_iterative_reference_audit_checks(
            summary,
            numerical_output,
            repo_root=repo_root,
            case_id="B0",
            b0_profile_capability=b0_profile_capability,
        )
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        errors.append(f"Task41 B0 iterative CSR/factor audit failed: {exc}")
    recovery_evidence_recheck = _task41_b0_recovery_evidence_checks(
        summary,
        numerical_output,
        contract,
        contract_sha256=contract_sha256,
    )
    errors.extend(recovery_evidence_recheck["errors"])

    output_meta = summary.get("output_packet")
    output_packet_path = None
    if (
        isinstance(output_meta, Mapping)
        and isinstance(output_meta.get("arrays"), Mapping)
        and isinstance(output_meta["arrays"].get("path"), str)
    ):
        output_npz = Path(str(output_meta["arrays"]["path"])).resolve()
        output_packet_path = output_npz.with_suffix(".json")
        if (
            output_npz.parent != run_directory
            or output_packet_path.parent != run_directory
            or not output_packet_path.is_file()
        ):
            errors.append("Task41 B0 official output packet escaped its run directory or is missing")
    else:
        errors.append("Task41 B0 worker summary omits its official output packet")
    if output_packet_path is not None and b0_profile_capability is not None:
        try:
            from src.runners.task40_v10_output_checker import (
                _verify_v31_reference_tiers,
                verify_v10_output_bundle,
            )

            output_packet = _json_object(output_packet_path, "B0 official output packet")
            output_packet_recheck = verify_v10_output_bundle(
                output_packet_path, expected_channel_count=TASK41_B0_MODE_COUNT
            )
            if output_packet_recheck.get("status") != "PASS":
                errors.append("Task41 B0 official output packet checker did not pass")
            reference_tier_recheck = _verify_v31_reference_tiers(
                summary.get("regular_inverse_checks", {}),
                expected_profile=TASK41_B0_PRECONDITIONER,
                b0_profile_capability=b0_profile_capability,
            )
            if (
                reference_tier_recheck.get("case_count") != 6
                or reference_tier_recheck.get("passed") is not True
            ):
                errors.append("Task41 B0 six full FE/port startup reference cases did not pass")
            power = summary.get("power")
            if not isinstance(power, Mapping):
                raise ValueError("Task41 B0 worker summary omits R/T/A/A_volume")
            power_values = {
                name: float(power.get(name, np.nan))
                for name in ("R", "T", "A", "A_volume")
            }
            closure = abs(power_values["R"] + power_values["T"] + power_values["A_volume"] - 1.0)
            absorption = abs(power_values["A"] - power_values["A_volume"])
            power_recheck = {
                "R_T_A_A_volume": power_values,
                "R_plus_T_plus_A_volume_minus_one": closure,
                "A_minus_A_volume": absorption,
                "limit": 1.0e-5,
                "passed": bool(
                    np.isfinite(list(power_values.values())).all()
                    and closure <= 1.0e-5
                    and absorption <= 1.0e-5
                    and abs(closure - float(summary.get("energy_closure_absolute", np.nan)))
                    <= 1.0e-12
                    and abs(
                        absorption - float(summary.get("absorption_consistency_absolute", np.nan))
                    )
                    <= 1.0e-12
                    and output_packet.get("passed") is True
                ),
            }
            if not power_recheck["passed"]:
                errors.append("Task41 B0 R/T/A/A_volume physical energy gate did not pass")
        except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
            errors.append(f"Task41 B0 output/reference-tier recheck failed: {exc}")

    post_meta = summary.get("post_release_final_residual_packet")
    if isinstance(post_meta, Mapping) and isinstance(post_meta.get("arrays"), Mapping):
        post_npz = Path(str(post_meta["arrays"].get("path", ""))).resolve()
        post_json = post_npz.with_suffix(".json")
        if post_npz.parent != run_directory or post_json.parent != run_directory:
            errors.append("Task41 B0 post-release A6 packet escaped its run directory")
        else:
            try:
                from src.runners.task40_v10_output_checker import (
                    verify_saved_full_a6_residual_packet,
                )

                post_release_recheck = verify_saved_full_a6_residual_packet(
                    post_json,
                    expected_identity={
                        key: (
                            summary.get("scientific_identity", {}).get(key)
                            if isinstance(summary.get("scientific_identity"), Mapping)
                            else None
                        )
                        for key in ("source_sha", "input_sha256", "physical_model_sha256")
                    },
                    expected_reference_factors_released=True,
                )
            except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
                errors.append(f"Task41 B0 post-release full A6 residual recheck failed: {exc}")
    else:
        errors.append("Task41 B0 worker summary omits its post-release full A6 packet")

    release = summary.get("b0_factor_release_audit")
    if not isinstance(release, Mapping) or (
        release.get("cleanup_status") != "DESTROYED"
        or release.get("destroyed") is not True
        or release.get("cleanup_failed") is not False
        or release.get("factors_live_count_current") != 0
        or release.get("matrices_live_count_current") != 0
        or release.get("cleanup_last_attempt_failures") != []
        or release.get("unconfirmed_owner_tags") != []
        or release.get("max_simultaneous_factors") != 200
        or release.get("all_q_factor_objects_live_simultaneously") is not True
    ):
        errors.append("Task41 B0 All-Q factors were not independently recorded as released")
    else:
        factor_release_recheck = {
            "cleanup_status": release["cleanup_status"],
            "factors_live_count_current": release["factors_live_count_current"],
            "matrices_live_count_current": release["matrices_live_count_current"],
            "max_simultaneous_factors": release["max_simultaneous_factors"],
            "all_q_factor_objects_live_simultaneously": True,
            "passed": True,
        }
    return {
        "schema": "task41.p0.b0_inventory_recheck.v1",
        "errors": errors,
        "mode_manifest_sha256": (
            b0_profile_capability.get("mode_manifest_sha256")
            if isinstance(b0_profile_capability, Mapping)
            else inventory.get("mode_manifest_sha256")
            if isinstance(inventory, Mapping)
            else None
        ),
        "mode_count": (
            b0_profile_capability.get("mode_count")
            if isinstance(b0_profile_capability, Mapping)
            else inventory.get("mode_count")
            if isinstance(inventory, Mapping)
            else TASK41_B0_MODE_COUNT
        ),
        "q_count": 200,
        "sector_count": 100,
        "q_port_counts_recomputed": q_counts,
        "sector_port_counts_recomputed": sector_counts,
        "verified_profile_capability": b0_profile_capability,
        "iterative_reference_recheck": iterative_reference_recheck,
        "recovery_evidence_recheck": recovery_evidence_recheck,
        "reference_tier_recheck": reference_tier_recheck,
        "output_packet_recheck": output_packet_recheck,
        "post_release_a6_recheck": post_release_recheck,
        "factor_release_recheck": factor_release_recheck,
        "power_recheck": power_recheck,
        "passed": not errors,
    }


def check_task41_p0(
    *,
    input_path: Path,
    summary_path: Path,
    manifest_path: Path,
    numerical_output: Path,
    contract_path: Path,
    contract_sha256: str,
    output_path: Path,
    repo_root: Path,
) -> dict[str, Any]:
    contract, contract_digest = require_task41_p0_contract(
        contract_path,
        expected_sha256=contract_sha256,
        current_root=repo_root,
        check_current_source=True,
        require_clean_source=True,
    )
    case = contract["case"]
    case_id = task41_case_id_for_run_id(str(case.get("run_id", "")))
    source_sha = contract["source"]["sha"]
    specification = load_and_resolve(input_path)
    validate_task41_specification(
        specification, input_path, contract, current_root=repo_root
    )
    input_path = input_path.resolve()
    summary_path = summary_path.resolve()
    manifest_path = manifest_path.resolve()
    numerical_output = numerical_output.resolve()
    output_path = output_path.resolve()
    if input_path != (repo_root / case["input_path"]).resolve():
        raise ValueError("checker input path differs from the frozen Task41 DAT")
    if summary_path.parent != manifest_path.parent:
        raise ValueError("run summary and manifest do not share the same run directory")
    manifest = _json_object(manifest_path, "run manifest")
    launcher_summary = _json_object(summary_path, "launcher summary")
    output_summary_path = (
        summary_path.parent / "task40_v10_p6_candidate_summary.json"
        if case_id in {"A2", "B0"}
        else numerical_output / "run_summary.json"
    )
    output_summary = _json_object(output_summary_path, "full numerical summary")
    run_directory = summary_path.parent
    expected_output_dir = Path(str(manifest.get("output_directory", ""))).resolve()
    expected_numerical_output = Path(
        str(manifest.get("numerical_output_directory", ""))
    ).resolve()
    if (
        summary_path != run_directory / "run_summary.json"
        or manifest_path != run_directory / "run_manifest.json"
        or expected_output_dir != run_directory
        or expected_numerical_output != numerical_output
        or Path(str(launcher_summary.get("output_directory", ""))).resolve() != run_directory
        or Path(str(launcher_summary.get("numerical_output_directory", ""))).resolve()
        != numerical_output
        or launcher_summary.get("run_id") != case["run_id"]
    ):
        raise ValueError("persisted run summary, manifest, and numerical-output paths disagree")
    expected_manifest = {
        "model_id": case["model_id"],
        "run_id": case["run_id"],
        "method": case["method"],
        "mpi_size": case["mpi_size"],
        "input_sha256": case["input_sha256"],
        "physical_model_sha256": case["physical_model_sha256"],
        "resolved_config_sha256": case["resolved_config_sha256"],
        "source_sha": source_sha,
    }
    identity_errors = [
        f"run manifest {key} differs from the Task41 contract"
        for key, expected in expected_manifest.items()
        if manifest.get(key) != expected
    ]
    copied_input = run_directory / "input_original.dat"
    resolved_config = run_directory / "resolved_config.json"
    if not copied_input.is_file() or sha256_file(copied_input) != case["input_sha256"]:
        identity_errors.append("copied original DAT is missing or has a different hash")
    if (
        not resolved_config.is_file()
        or hashlib.sha256(resolved_config.read_bytes()).hexdigest()
        != case["resolved_config_sha256"]
    ):
        identity_errors.append("saved resolved configuration is missing or has a different hash")
    a2_rechecks = None
    b0_rechecks = None
    if case_id == "A2":
        a2_rechecks = _task41_a2_numerical_checks(
            output_summary,
            numerical_output,
            contract,
            repo_root=repo_root,
        )
        numerical_errors = list(a2_rechecks["errors"])
    elif case_id == "B0":
        b0_rechecks = _task41_b0_numerical_checks(
            output_summary,
            numerical_output,
            contract,
            contract_path=contract_path,
            contract_sha256=contract_digest,
            repo_root=repo_root,
        )
        numerical_errors = list(b0_rechecks["errors"])
    else:
        numerical_errors = evaluate_task41_numerical_summary(output_summary, numerical_output)
    errors = identity_errors + numerical_errors
    passed = not errors
    payload = {
        "schema": (
            A2_CHECKER_SCHEMA
            if case_id == "A2"
            else B0_CHECKER_SCHEMA
            if case_id == "B0"
            else CHECKER_SCHEMA
        ),
        "checked_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "PASS" if passed else "FAIL",
        "checker_passed": passed,
        "full_pass": passed,
        "official_result": passed,
        "task_id": contract["task_id"],
        "run_id": case["run_id"],
        "source_sha": source_sha,
        "contract_sha256": contract_digest,
        "window_path": str((repo_root / contract["window"]["path"]).resolve()),
        "window_sha256": contract["window"]["sha256"],
        "input_sha256": case["input_sha256"],
        "physical_model_sha256": case["physical_model_sha256"],
        "resolved_config_sha256": case["resolved_config_sha256"],
        "run_manifest_sha256": sha256_file(manifest_path),
        "launcher_summary_sha256": sha256_file(summary_path),
        "numerical_summary_sha256": sha256_file(output_summary_path),
        "launcher_result_classification": launcher_summary.get("result_classification"),
        **({"a2_independent_rechecks": a2_rechecks} if a2_rechecks is not None else {}),
        **({"b0_independent_rechecks": b0_rechecks} if b0_rechecks is not None else {}),
        "errors": errors,
        "raw_evidence_retained": True,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, output_path)
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--input", type=Path)
    mode.add_argument("--saved-output-continuation-input", type=Path)
    mode.add_argument("--saved-b0-evidence-audit", action="store_true")
    mode.add_argument("--saved-b0-y-g-comparison", action="store_true")
    mode.add_argument("--v9-saved-star-screen", action="store_true")
    mode.add_argument("--v9-failed-terminal-audit", action="store_true")
    mode.add_argument("--v11-candidate-replay-saved-check", action="store_true")
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--numerical-output", type=Path)
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--contract", required=True, type=Path)
    parser.add_argument("--contract-sha256", required=True)
    parser.add_argument("--consumer-contract", type=Path)
    parser.add_argument("--consumer-contract-sha256")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--mesh-actual-exact-report", type=Path)
    parser.add_argument("--mesh-actual-exact-report-sha256")
    parser.add_argument("--v8-report", type=Path)
    parser.add_argument("--v8-report-sha256")
    parser.add_argument("--v8-checker-result", type=Path)
    parser.add_argument("--v8-checker-result-sha256")
    parser.add_argument("--v6-report", type=Path)
    parser.add_argument("--v6-report-sha256")
    parser.add_argument("--v9-report", type=Path)
    parser.add_argument("--v9-report-sha256")
    parser.add_argument("--v9-summary", type=Path)
    parser.add_argument("--v9-summary-sha256")
    parser.add_argument("--v9-service-receipt", type=Path)
    parser.add_argument("--v9-service-receipt-sha256")
    parser.add_argument("--v11-report", type=Path)
    parser.add_argument("--v11-report-sha256")
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[2]
    if args.v11_candidate_replay_saved_check:
        if (
            args.summary is None
            or args.consumer_contract is None
            or args.consumer_contract_sha256 is None
            or args.v11_report is None
            or args.v11_report_sha256 is None
            or args.input is not None
            or args.saved_output_continuation_input is not None
            or args.saved_b0_evidence_audit
            or args.saved_b0_y_g_comparison
            or args.v9_saved_star_screen
            or args.v9_failed_terminal_audit
            or any(
                value is not None
                for value in (
                    args.manifest,
                    args.numerical_output,
                    args.run_root,
                    args.mesh_actual_exact_report,
                    args.mesh_actual_exact_report_sha256,
                    args.v8_report,
                    args.v8_report_sha256,
                    args.v8_checker_result,
                    args.v8_checker_result_sha256,
                    args.v6_report,
                    args.v6_report_sha256,
                    args.v9_report,
                    args.v9_report_sha256,
                    args.v9_summary,
                    args.v9_summary_sha256,
                    args.v9_service_receipt,
                    args.v9_service_receipt_sha256,
                )
            )
        ):
            parser.error(
                "V11 saved-array check requires --contract/--contract-sha256 (donor), "
                "--consumer-contract/--consumer-contract-sha256, --summary, and "
                "--v11-report/--v11-report-sha256"
            )
        try:
            result = check_task41_p0_v11_candidate_replay_saved_arrays(
                summary_path=args.summary,
                donor_contract_path=args.contract,
                donor_contract_sha256=args.contract_sha256,
                consumer_contract_path=args.consumer_contract,
                consumer_contract_sha256=args.consumer_contract_sha256,
                candidate_report_path=args.v11_report,
                candidate_report_sha256=args.v11_report_sha256,
                output_path=args.output,
                repo_root=root,
            )
        except (OSError, ValueError, RuntimeError, KeyError, TypeError, IndexError) as exc:
            result = {
                "schema": "task41.p0.v11.selected_trace_star_saved_array_independent_check.v1",
                "check_completed": False,
                "candidate_passed": None,
                "scientific_qualified": False,
                "official_result": False,
                "errors": [f"{type(exc).__name__}: {exc}"],
                "raw_evidence_retained": True,
            }
            output_path = args.output.resolve()
            if not output_path.exists() and output_path.is_relative_to((root / "results").resolve()):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = output_path.with_name(output_path.name + ".tmp")
                temporary.write_text(
                    json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8",
                )
                try:
                    os.link(temporary, output_path)
                except FileExistsError:
                    pass
                finally:
                    temporary.unlink(missing_ok=True)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("check_completed") is True else 2
    if args.saved_b0_y_g_comparison:
        comparison_inputs = (
            args.v6_report,
            args.v6_report_sha256,
            args.v9_report,
            args.v9_report_sha256,
            args.v9_summary,
            args.v9_summary_sha256,
            args.v9_service_receipt,
            args.v9_service_receipt_sha256,
        )
        if (
            args.input is not None
            or args.saved_output_continuation_input is not None
            or args.saved_b0_evidence_audit
            or args.v9_saved_star_screen
            or args.v9_failed_terminal_audit
            or any(value is None for value in comparison_inputs)
            or args.summary is not None
            or args.manifest is not None
            or args.numerical_output is not None
            or args.run_root is not None
            or args.consumer_contract is not None
            or args.consumer_contract_sha256 is not None
            or args.mesh_actual_exact_report is not None
            or args.mesh_actual_exact_report_sha256 is not None
            or args.v8_report is not None
            or args.v8_report_sha256 is not None
            or args.v8_checker_result is not None
            or args.v8_checker_result_sha256 is not None
        ):
            parser.error(
                "saved V6/V9 y/g comparison requires hash-bound V6/V9 reports, "
                "V9 summary/receipt, and the saved-diagnostics --contract"
            )
        try:
            result = compare_task41_p0_b0_saved_y_g_reports(
                v6_report_path=args.v6_report,
                v6_report_sha256=args.v6_report_sha256,
                v9_report_path=args.v9_report,
                v9_report_sha256=args.v9_report_sha256,
                v9_summary_path=args.v9_summary,
                v9_summary_sha256=args.v9_summary_sha256,
                v9_service_receipt_path=args.v9_service_receipt,
                v9_service_receipt_sha256=args.v9_service_receipt_sha256,
                consumer_contract_path=args.contract,
                consumer_contract_sha256=args.contract_sha256,
                output_path=args.output,
                repo_root=root,
            )
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            result = {
                "schema": "task41.p0.b0.saved_y_g_comparison.v1",
                "status": "INCOMPLETE",
                "data_integrity": False,
                "classification": "SAVED_VECTOR_COMPARISON_INCOMPLETE",
                "official_result": False,
                "errors": [f"{type(exc).__name__}: {exc}"],
                "raw_evidence_retained": True,
            }
            output_path = args.output.resolve()
            if not output_path.exists() and output_path.is_relative_to((root / "results").resolve()):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = output_path.with_name(output_path.name + ".tmp")
                temporary.write_text(
                    json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8",
                )
                try:
                    os.link(temporary, output_path)
                except FileExistsError:
                    pass
                finally:
                    temporary.unlink(missing_ok=True)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("status") == "COMPLETED" else 2
    if args.v9_saved_star_screen:
        if (
            args.input is not None
            or args.saved_output_continuation_input is not None
            or args.saved_b0_evidence_audit
            or args.summary is not None
            or args.manifest is not None
            or args.numerical_output is not None
            or args.run_root is not None
            or args.consumer_contract is not None
            or args.consumer_contract_sha256 is not None
            or args.mesh_actual_exact_report is not None
            or args.mesh_actual_exact_report_sha256 is not None
            or args.v8_report is None
            or args.v8_report_sha256 is None
            or args.v8_checker_result is None
            or args.v8_checker_result_sha256 is None
        ):
            parser.error(
                "V9 saved-star screen requires only its V9 contract and both hash-bound V8 reports"
            )
        try:
            result = check_task41_p0_b0_v9_saved_star_screen(
                contract_path=args.contract,
                contract_sha256=args.contract_sha256,
                v8_report_path=args.v8_report,
                v8_report_sha256=args.v8_report_sha256,
                v8_checker_result_path=args.v8_checker_result,
                v8_checker_result_sha256=args.v8_checker_result_sha256,
                output_path=args.output,
                repo_root=root,
            )
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            result = {
                "schema": "task41.p0.b0.v9.saved_star_screen_result.v1",
                "status": "INCOMPLETE",
                "screen_completed": False,
                "local_candidate_ready": False,
                "official_result": False,
                "errors": [f"{type(exc).__name__}: {exc}"],
                "raw_evidence_retained": True,
            }
            output_path = args.output.resolve()
            if not output_path.exists() and output_path.is_relative_to((root / "results").resolve()):
                output_path.parent.mkdir(parents=True, exist_ok=True)
                temporary = output_path.with_name(output_path.name + ".tmp")
                temporary.write_text(
                    json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                    encoding="utf-8",
                )
                try:
                    os.link(temporary, output_path)
                except FileExistsError:
                    pass
                finally:
                    temporary.unlink(missing_ok=True)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 2
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("screen_completed") is True else 2
    if args.v9_failed_terminal_audit:
        if (
            args.input is not None
            or args.saved_output_continuation_input is not None
            or args.saved_b0_evidence_audit
            or args.numerical_output is not None
            or args.summary is None
            or args.manifest is None
            or args.run_root is None
            or args.consumer_contract is None
            or args.consumer_contract_sha256 is None
            or args.mesh_actual_exact_report is not None
            or args.mesh_actual_exact_report_sha256 is not None
            or args.v8_report is not None
            or args.v8_report_sha256 is not None
            or args.v8_checker_result is not None
            or args.v8_checker_result_sha256 is not None
        ):
            parser.error(
                "V9 failed-terminal audit requires a verified run root, summary/manifest, "
                "producer contract and a distinct consumer contract"
            )
        try:
            result = check_task41_p0_b0_v9_failed_terminal_audit(
                run_root=args.run_root,
                summary_path=args.summary,
                manifest_path=args.manifest,
                producer_contract_path=args.contract,
                producer_contract_sha256=args.contract_sha256,
                consumer_contract_path=args.consumer_contract,
                consumer_contract_sha256=args.consumer_contract_sha256,
                output_path=args.output,
                repo_root=root,
            )
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            result = {
                "schema": "task41.p0.b0.v9.failed_terminal_audit.v1",
                "status": "INCOMPLETE",
                "audit_completed": False,
                "data_integrity": False,
                "action_passed": None,
                "recovery_status": None,
                "official_result": False,
                "errors": [f"{type(exc).__name__}: {exc}"],
                "raw_evidence_retained": True,
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("audit_completed") is True else 2
    if args.saved_b0_evidence_audit:
        if (
            args.input is not None
            or args.saved_output_continuation_input is not None
            or args.manifest is not None
            or args.summary is None
            or args.numerical_output is None
            or args.run_root is not None
            or args.consumer_contract is None
            or args.consumer_contract_sha256 is None
            or (args.mesh_actual_exact_report is None)
            != (args.mesh_actual_exact_report_sha256 is None)
        ):
            parser.error(
                "saved B0 evidence audit requires donor --summary/--numerical-output "
                "and a strict --consumer-contract binding"
            )
        try:
            result = check_task41_p0_b0_saved_evidence_audit(
                summary_path=args.summary,
                numerical_output=args.numerical_output,
                contract_path=args.contract,
                contract_sha256=args.contract_sha256,
                consumer_contract_path=args.consumer_contract,
                consumer_contract_sha256=args.consumer_contract_sha256,
                output_path=args.output,
                repo_root=root,
                mesh_actual_exact_report_path=args.mesh_actual_exact_report,
                mesh_actual_exact_report_sha256=args.mesh_actual_exact_report_sha256,
            )
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            result = {
                "schema": "task41.p0.b0.saved_evidence_audit.v1",
                "status": "INCOMPLETE",
                "audit_completed": False,
                "data_integrity": False,
                "recovery_passed": False,
                "joint_action_passed": None,
                "qualification_passed": False,
                "official_result": False,
                "errors": [f"{type(exc).__name__}: {exc}"],
                "raw_evidence_retained": True,
            }
            print(json.dumps(result, ensure_ascii=False, sort_keys=True))
            return 2
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("audit_completed") is True else 2
    if args.saved_output_continuation_input is not None:
        checker_only = os.environ.get("TASK41_P0_SAVED_OUTPUT_CHECKER_ONLY") == "1"
        expected_output = (
            Path(os.environ.get("TASK41_P0_CHECKER_RESULT_PATH", "")).resolve()
            if checker_only
            else (
                args.saved_output_continuation_input.resolve().parent
                / "task41_p0_saved_output_checker_result.json"
            ).resolve()
        )
        if (
            args.summary is not None
            or args.manifest is not None
            or args.numerical_output is not None
            or args.run_root is not None
            or args.output.resolve() != expected_output
        ):
            parser.error("saved-output continuation checker uses its bound input snapshot and adjacent result path")
        try:
            from src.runners.task41_p0_saved_output_continuation import (
                check_task41_p0_saved_output_continuation,
            )

            result = check_task41_p0_saved_output_continuation(
                args.saved_output_continuation_input,
                contract_path=args.contract,
                contract_sha256=args.contract_sha256,
                repo_root=root,
                result_path=args.output.resolve(),
            )
        except (OSError, ValueError, RuntimeError, KeyError) as exc:
            result = {
                "schema": "task41.p0.saved_output_checker.v1",
                "status": "FAIL",
                "checker_passed": False,
                "errors": [f"{type(exc).__name__}: {exc}"],
                "raw_evidence_retained": True,
            }
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result.get("checker_passed") is True else 2
    if args.run_root is not None:
        parser.error("--run-root is only valid for V9 failed-terminal audit")
    if any(value is None for value in (args.summary, args.manifest, args.numerical_output)):
        parser.error("ordinary Task41 checker mode requires --summary, --manifest, and --numerical-output")
    try:
        result = check_task41_p0(
            input_path=args.input,
            summary_path=args.summary,
            manifest_path=args.manifest,
            numerical_output=args.numerical_output,
            contract_path=args.contract,
            contract_sha256=args.contract_sha256,
            output_path=args.output,
            repo_root=root,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        result = {
            "schema": CHECKER_SCHEMA,
            "status": "FAIL",
            "checker_passed": False,
            "full_pass": False,
            "official_result": False,
            "errors": [f"{type(exc).__name__}: {exc}"],
            "raw_evidence_retained": True,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("checker_passed") is True else 2


if __name__ == "__main__":
    raise SystemExit(main())
