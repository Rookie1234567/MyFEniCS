"""Bounded, read-only W6B-S0 spectral diagnosis for the frozen W6A scratch."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
from typing import Any

import numpy as np
from scipy.linalg import solve_triangular

from src.solvers.disk_backed_flexible_gmres import RawPositionalColumnStore
from src.solvers.hcurl_m6b_sparse_range import (
    _array_sha256,
    _file_sha256,
    _json_sha256,
)
from src.solvers.hcurl_m6b_w6a_multi_order_range import (
    W6A_DIFFRACTION_ORDERS,
    W6A_LEGACY_AZ_COLUMN_SHA256_AGGREGATE,
    W6A_LEGACY_BASIS_MANIFEST_SHA256,
    W6A_LEGACY_COLUMNS,
    W6A_NORMAL_CLOSURE_LIMIT,
    W6A_REPEAT_COLUMNS,
    W6A_SCHEMA,
    W6A_TOTAL_COLUMNS,
    _RANK_THRESHOLD_FACTOR,
    _load_manifest_array,
    fixed_w6a_column_specs,
)

__all__ = (
    "W6B_S0_SCHEMA",
    "W6B_S0_CHECKPOINTS",
    "W6B_S0_RHO_AUTHORITY",
    "W6B_S0_SUBSET_NAMES",
    "fixed_w6b_s0_subsets",
    "run_w6b_s0",
)


W6B_S0_SCHEMA = "task037.extra.m6b.w6b.s0.spectral-diagnostic.v1"
W6B_S0_CHECKPOINTS = (20, 100, 150, 200)
W6B_S0_RHO_AUTHORITY = {
    "20": {
        "rho75": 0.9998604902222914,
        "rho390": 0.9703655744743771,
    },
    "100": {
        "rho75": 0.999954723453673,
        "rho390": 0.981841863933189,
    },
    "150": {
        "rho75": 0.9999695769032492,
        "rho390": 0.9800663350965748,
    },
    "200": {
        "rho75": 0.99998845810871,
        "rho390": 0.9764446942793935,
    },
}
W6B_S0_SUBSET_NAMES = (
    "legacy75",
    *(f"cumulative_through_order_m{order}" for order in W6A_DIFFRACTION_ORDERS),
    *(f"leave_out_order_m{order}" for order in W6A_DIFFRACTION_ORDERS),
    *(f"legacy75_plus_component_{component}" for component in range(3)),
    "full390",
)
_COMPLEX128 = np.dtype(np.complex128)
_INDEX_DTYPE = np.dtype(np.int32)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _artifact(path: Path, root: Path) -> dict[str, Any]:
    path = path.resolve()
    root = root.resolve()
    return {
        "path": str(path),
        "relative_path": str(path.relative_to(root)),
        "bytes": int(path.stat().st_size),
        "sha256": _file_sha256(path),
        "present": True,
    }


def fixed_w6b_s0_subsets() -> dict[str, tuple[int, ...]]:
    """Return the one fixed W6B-S0 subset collection in audit order."""

    specs = fixed_w6a_column_specs()
    order_columns = {
        order: tuple(
            spec.column_index
            for spec in specs
            if spec.family == "diffraction_n0" and spec.order_m == order
        )
        for order in W6A_DIFFRACTION_ORDERS
    }
    component_columns = {
        component: tuple(
            spec.column_index
            for spec in specs
            if spec.family == "diffraction_n0" and spec.component == component
        )
        for component in range(3)
    }
    subsets: dict[str, tuple[int, ...]] = {"legacy75": tuple(range(W6A_LEGACY_COLUMNS))}
    cumulative: list[int] = []
    for order in W6A_DIFFRACTION_ORDERS:
        cumulative.extend(order_columns[order])
        subsets[f"cumulative_through_order_m{order}"] = (
            *subsets["legacy75"],
            *cumulative,
        )
    for order in W6A_DIFFRACTION_ORDERS:
        subsets[f"leave_out_order_m{order}"] = tuple(
            column
            for column in range(W6A_TOTAL_COLUMNS)
            if column not in order_columns[order]
        )
    for component in range(3):
        subsets[f"legacy75_plus_component_{component}"] = (
            *subsets["legacy75"],
            *component_columns[component],
        )
    subsets["full390"] = tuple(range(W6A_TOTAL_COLUMNS))
    _require(tuple(subsets) == W6B_S0_SUBSET_NAMES, "W6B subset order is not fixed")
    _require(
        all(len(values) == len(set(values)) for values in subsets.values()),
        "W6B subset contains duplicate columns",
    )
    return subsets


def _load_w6a_input(w6a_raw_dir: Path) -> tuple[dict[str, Any], dict[str, np.ndarray], RawPositionalColumnStore]:
    root = Path(w6a_raw_dir).resolve()
    store_root = root / "sparse_range_store"
    manifest_path = store_root / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _require(isinstance(manifest, Mapping), "W6B W6A manifest is not a mapping")
    _require(manifest.get("schema") == W6A_SCHEMA, "W6B W6A schema differs")
    _require(
        manifest.get("evidence_sha256")
        == _json_sha256(
            {key: value for key, value in manifest.items() if key != "evidence_sha256"}
        ),
        "W6B W6A manifest evidence is invalid",
    )
    _require(manifest.get("columns") == W6A_TOTAL_COLUMNS, "W6B W6A column count differs")
    global_rows = manifest.get("global_rows")
    _require(type(global_rows) is int and global_rows > 0, "W6B W6A rows are invalid")
    _require(
        manifest.get("ownership_range") == [0, global_rows],
        "W6B W6A ownership is not MPI1 full ownership",
    )
    _require(
        tuple(manifest.get("column_specs", ()))
        == tuple(spec.__dict__ for spec in fixed_w6a_column_specs()),
        "W6B W6A column specs differ",
    )
    _require(manifest.get("repeat_columns") == list(W6A_REPEAT_COLUMNS), "W6B repeats differ")
    _require(manifest.get("repeat_exact") is True, "W6B W6A repeats are not exact")
    _require(
        manifest.get("legacy_z_identity", {}).get("basis_manifest_sha256")
        == W6A_LEGACY_BASIS_MANIFEST_SHA256,
        "W6B W1A basis authority differs",
    )
    _require(
        manifest.get("legacy_z_identity", {}).get("az_column_sha256_aggregate")
        == W6A_LEGACY_AZ_COLUMN_SHA256_AGGREGATE,
        "W6B W1A AZ authority differs",
    )
    arrays_entry = manifest.get("arrays")
    _require(
        isinstance(arrays_entry, Mapping)
        and set(arrays_entry) == {"z_data", "z_indices", "z_indptr", "gram", "r_factor"},
        "W6B W6A array set differs",
    )
    arrays = {
        name: _load_manifest_array(store_root, name, arrays_entry[name])
        for name in ("z_data", "z_indices", "z_indptr", "gram", "r_factor")
    }
    z_data = np.asarray(arrays["z_data"])
    z_indices = np.asarray(arrays["z_indices"])
    z_indptr = np.asarray(arrays["z_indptr"])
    gram = np.asarray(arrays["gram"])
    r_factor = np.asarray(arrays["r_factor"])
    _require(
        z_data.dtype == _COMPLEX128
        and z_indices.dtype == _INDEX_DTYPE
        and z_indptr.dtype == _INDEX_DTYPE
        and z_indptr.shape == (W6A_TOTAL_COLUMNS + 1,)
        and int(z_indptr[0]) == 0
        and int(z_indptr[-1]) == z_data.size == z_indices.size
        and gram.shape == (W6A_TOTAL_COLUMNS, W6A_TOTAL_COLUMNS)
        and r_factor.shape == gram.shape
        and np.all(np.isfinite(gram))
        and np.all(np.isfinite(r_factor)),
        "W6B W6A array structure is invalid",
    )
    _require(
        np.array_equal(r_factor, np.triu(r_factor))
        and np.all(np.real(np.diag(r_factor)) > 0.0),
        "W6B W6A factor is not upper triangular positive",
    )
    gram_norm = max(float(np.linalg.norm(gram)), np.finfo(float).tiny)
    gram_defect = float(np.linalg.norm(gram - gram.conjugate().T) / gram_norm)
    normal_closure = float(
        np.linalg.norm(r_factor.conjugate().T @ r_factor - gram) / gram_norm
    )
    singular = np.linalg.svd(r_factor, compute_uv=False)
    threshold = float(
        _RANK_THRESHOLD_FACTOR * np.finfo(float).eps * max(1.0, singular[0])
    )
    _require(
        np.isfinite(gram_defect)
        and gram_defect <= W6A_NORMAL_CLOSURE_LIMIT
        and np.isfinite(normal_closure)
        and normal_closure <= W6A_NORMAL_CLOSURE_LIMIT
        and int(np.count_nonzero(singular > threshold)) == W6A_TOTAL_COLUMNS,
        "W6B W6A Gram/factor audit failed",
    )
    scratch = manifest.get("az_scratch")
    _require(isinstance(scratch, Mapping), "W6B W6A AZ scratch metadata is missing")
    scratch_path = Path(scratch.get("path", "")).resolve()
    expected_scratch = (root / "az_scratch" / "az_columns.bin").resolve()
    _require(scratch_path == expected_scratch, "W6B W6A AZ scratch path differs")
    _require(
        scratch_path.is_file()
        and scratch_path.stat().st_size == scratch.get("bytes")
        and _file_sha256(scratch_path) == scratch.get("sha256")
        and scratch.get("rows") == global_rows
        and scratch.get("capacity") == W6A_TOTAL_COLUMNS,
        "W6B W6A AZ scratch identity is invalid",
    )
    store = RawPositionalColumnStore.open_readonly(
        scratch_path, global_rows, W6A_TOTAL_COLUMNS
    )
    manifest["_diagnostic_audit"] = {
        "manifest_path": str(manifest_path),
        "manifest_file_sha256": _file_sha256(manifest_path),
        "gram_hermitian_defect": gram_defect,
        "normal_closure": normal_closure,
        "rank": int(np.count_nonzero(singular > threshold)),
        "rank_threshold": threshold,
        "r_condition_estimate": float(singular[0] / singular[-1]),
    }
    return manifest, arrays, store


def _load_w5_residuals(w5_raw_dir: Path, rows: int) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    root = Path(w5_raw_dir).resolve()
    residuals: dict[str, np.ndarray] = {}
    artifacts: dict[str, Any] = {}
    for iteration in W6B_S0_CHECKPOINTS:
        name = f"m6b_iter{iteration}_residual.npy"
        path = root / name
        value = np.load(path, allow_pickle=False, mmap_mode="r")
        _require(
            value.dtype == _COMPLEX128
            and value.shape == (rows,)
            and np.all(np.isfinite(value)),
            f"W6B W5 residual {name} is invalid",
        )
        residuals[str(iteration)] = value
        artifacts[str(iteration)] = {
            **_artifact(path, root),
            "array_sha256": _array_sha256(value),
            "shape": [rows],
            "dtype": "complex128",
        }
    return residuals, artifacts


def _subset_factor(gram: np.ndarray, indices: tuple[int, ...]) -> dict[str, Any]:
    subgram = np.asarray(gram[np.ix_(indices, indices)])
    norm = max(float(np.linalg.norm(subgram)), np.finfo(float).tiny)
    hermitian_defect = float(
        np.linalg.norm(subgram - subgram.conjugate().T) / norm
    )
    lower = np.linalg.cholesky(subgram)
    factor = np.asarray(lower.conjugate().T, dtype=_COMPLEX128)
    factor_closure = float(np.linalg.norm(factor.conjugate().T @ factor - subgram) / norm)
    singular = np.linalg.svd(factor, compute_uv=False)
    threshold = float(
        _RANK_THRESHOLD_FACTOR * np.finfo(float).eps * max(1.0, singular[0])
    )
    rank = int(np.count_nonzero(singular > threshold))
    _require(
        np.isfinite(hermitian_defect)
        and hermitian_defect <= W6A_NORMAL_CLOSURE_LIMIT
        and np.isfinite(factor_closure)
        and factor_closure <= W6A_NORMAL_CLOSURE_LIMIT
        and rank == len(indices),
        "W6B subset Gram audit failed",
    )
    return {
        "column_count": len(indices),
        "column_indices": list(indices),
        "gram_hermitian_defect": hermitian_defect,
        "factor_normal_closure": factor_closure,
        "rank": rank,
        "rank_threshold": threshold,
        "condition_estimate": float(singular[0] / singular[-1]),
        "factor": factor,
        "gram": subgram,
    }


def _subset_measurement(
    factor_info: Mapping[str, Any], h: np.ndarray, rhs_norm_sq: float
) -> dict[str, Any]:
    factor = np.asarray(factor_info["factor"])
    subgram = np.asarray(factor_info["gram"])
    y = solve_triangular(
        factor, h, trans="C", lower=False, check_finite=False
    )
    coefficients = solve_triangular(
        factor, y, lower=False, check_finite=False
    )
    normal_defect = float(
        np.linalg.norm(subgram @ coefficients - h)
        / max(float(np.linalg.norm(h)), np.finfo(float).tiny)
    )
    captured = float(np.real(np.vdot(h, coefficients)))
    energy_defect = float(
        abs(np.vdot(coefficients, subgram @ coefficients).real - captured)
        / max(abs(captured), np.finfo(float).tiny)
    )
    remaining_sq = float(rhs_norm_sq - captured)
    _require(
        np.isfinite(normal_defect)
        and normal_defect <= W6A_NORMAL_CLOSURE_LIMIT
        and np.isfinite(energy_defect)
        and energy_defect <= W6A_NORMAL_CLOSURE_LIMIT
        and np.isfinite(captured)
        and captured >= 0.0
        and remaining_sq >= -1.0e-11 * max(rhs_norm_sq, 1.0),
        "W6B least-squares energy closure failed",
    )
    remaining_sq = max(remaining_sq, 0.0)
    return {
        "rho": float(np.sqrt(remaining_sq / rhs_norm_sq)),
        "captured_energy": captured,
        "captured_energy_ratio": captured / rhs_norm_sq,
        "normal_equation_closure": normal_defect,
        "energy_closure": energy_defect,
        "finite": True,
    }


def run_w6b_s0(
    w6a_raw_dir: Path, w5_raw_dir: Path, *, expected_source_sha: str
) -> dict[str, Any]:
    """Run the single fixed W6B-S0 pass without physical actions."""

    manifest, arrays, az_store = _load_w6a_input(Path(w6a_raw_dir))
    try:
        rows = int(manifest["global_rows"])
        residuals, residual_artifacts = _load_w5_residuals(Path(w5_raw_dir), rows)
        h_by_iteration = {
            iteration: np.empty(W6A_TOTAL_COLUMNS, dtype=_COMPLEX128)
            for iteration in residuals
        }
        az_buffer = np.empty(rows, dtype=_COMPLEX128)
        column_hashes: list[str] = []
        for column in range(W6A_TOTAL_COLUMNS):
            az_store.read_column(column, az_buffer)
            column_hashes.append(_array_sha256(az_buffer))
            for iteration, residual in residuals.items():
                h_by_iteration[iteration][column] = np.vdot(az_buffer, residual)
        _require(
            column_hashes == manifest["column_sha256"]
            and _json_sha256(column_hashes[:W6A_LEGACY_COLUMNS])
            == W6A_LEGACY_AZ_COLUMN_SHA256_AGGREGATE
            and _json_sha256(column_hashes) == manifest["az_column_sha256_aggregate"],
            "W6B AZ column identity differs",
        )
        subsets = fixed_w6b_s0_subsets()
        factors = {name: _subset_factor(np.asarray(arrays["gram"]), indices) for name, indices in subsets.items()}
        measurements: dict[str, Any] = {}
        authority_comparison: dict[str, Any] = {}
        for iteration, residual in residuals.items():
            rhs_norm_sq = float(np.vdot(residual, residual).real)
            _require(np.isfinite(rhs_norm_sq) and rhs_norm_sq > 0.0, "W6B residual norm is invalid")
            checkpoint = {
                "rhs_norm": float(np.sqrt(rhs_norm_sq)),
                "rhs_array_sha256": residual_artifacts[iteration]["array_sha256"],
                "h_array_sha256": _array_sha256(h_by_iteration[iteration]),
                "subsets": {},
            }
            for name, factor_info in factors.items():
                measurement = _subset_measurement(
                    factor_info, h_by_iteration[iteration][list(subsets[name])], rhs_norm_sq
                )
                checkpoint["subsets"][name] = {
                    **{key: value for key, value in measurement.items()},
                    "column_count": factor_info["column_count"],
                }
            legacy = checkpoint["subsets"]["legacy75"]
            full = checkpoint["subsets"]["full390"]
            for name, item in checkpoint["subsets"].items():
                item["relative_rho_improvement_vs_legacy"] = float(
                    1.0 - item["rho"] / legacy["rho"]
                )
                item["additional_captured_energy_ratio_vs_legacy"] = float(
                    item["captured_energy_ratio"] - legacy["captured_energy_ratio"]
                )
            expected = W6B_S0_RHO_AUTHORITY[iteration]
            authority_comparison[iteration] = {
                key: {
                    "observed": float(checkpoint["subsets"][key]["rho"]),
                    "expected": float(expected["rho75" if key == "legacy75" else "rho390"]),
                    "abs_delta": abs(
                        float(checkpoint["subsets"][key]["rho"])
                        - float(expected["rho75" if key == "legacy75" else "rho390"])
                    ),
                    "pass": abs(
                        float(checkpoint["subsets"][key]["rho"])
                        - float(expected["rho75" if key == "legacy75" else "rho390"])
                    ) <= 1.0e-12,
                }
                for key in ("legacy75", "full390")
            }
            checkpoint["full390_vs_legacy75_relative_improvement"] = float(
                1.0 - full["rho"] / legacy["rho"]
            )
            measurements[iteration] = checkpoint
        authority_pass = all(
            item["pass"]
            for checkpoint in authority_comparison.values()
            for item in checkpoint.values()
        )
        subset_audit = {
            name: {
                key: value
                for key, value in factor_info.items()
                if key not in {"factor", "gram"}
            }
            for name, factor_info in factors.items()
        }
        return {
            "schema": W6B_S0_SCHEMA,
            "status": "diagnostic_complete" if authority_pass else "gate_failed",
            "classification": "DIAGNOSTIC_ONLY",
            "diagnostic_pass": bool(authority_pass),
            "formal_pass": False,
            "pde_pass": False,
            "official_rta": False,
            "execution": {
                "expected_source_sha": expected_source_sha,
                "operator_actions": 0,
                "physical_action_called": False,
                "parameter_scan": False,
                "selection_as_pass": False,
            },
            "w6a_authority": {
                "raw_dir": str(Path(w6a_raw_dir).resolve()),
                "manifest": manifest["_diagnostic_audit"],
                "manifest_schema": manifest["schema"],
                "column_count": manifest["columns"],
                "legacy_basis_manifest_sha256": W6A_LEGACY_BASIS_MANIFEST_SHA256,
                "legacy_az_column_sha256_aggregate": W6A_LEGACY_AZ_COLUMN_SHA256_AGGREGATE,
                "az_column_sha256_aggregate": manifest["az_column_sha256_aggregate"],
                "column_hashes": column_hashes,
                "az_store_audit": az_store.audit(),
            },
            "w5_residual_authority": {
                "raw_dir": str(Path(w5_raw_dir).resolve()),
                "checkpoints": residual_artifacts,
            },
            "subset_definitions": {
                name: {
                    "column_indices": list(indices),
                    "column_count": len(indices),
                    "indices_sha256": _array_sha256(np.asarray(indices, dtype=np.int32)),
                }
                for name, indices in subsets.items()
            },
            "subset_audit": subset_audit,
            "checkpoints": measurements,
            "authority_comparison": authority_comparison,
            "resource_audit": {
                "az_read_passes": 1,
                "az_column_reads": az_store.read_count,
                "dense_az_retained": False,
                "dense_z_retained": False,
                "max_live_az_full_vector_buffers": 1,
                "residuals_mmap": True,
                "disk_scratch_bytes": az_store.allocated_bytes,
                "swap_gate": 0,
                "peak_rss_target_bytes": 1_000_000_000,
                "measured_by_watchdog": False,
            },
            "analysis_inputs": {
                "fixed_orders": list(W6A_DIFFRACTION_ORDERS),
                "fixed_components": [0, 1, 2],
                "fixed_repeat_columns": list(W6A_REPEAT_COLUMNS),
                "full390_and_legacy75_authority_tolerance": 1.0e-12,
            },
        }
    finally:
        az_store.close()
