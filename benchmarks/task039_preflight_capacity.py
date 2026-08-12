"""Deterministic Task39 A0 capacity estimates from one resolved input.

This module reads one tracked compact extract of two reviewed topology sources
and reuses the existing Task39 external-mode inventory. It does not query live
memory or launch a solver; later phases may attach measured resource and ABI
snapshots.
"""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import re
import json
from pathlib import Path
from typing import Any, Mapping

from src.io.input_validation import (
    InputError,
    load_and_resolve,
    task039_dynamic_external_mode_inventory,
)
from src.io.resolved_config import canonical_json_bytes, resolved_config_sha256
from src.io.run_specification import RunSpecification


_SOURCE_SHA = re.compile(r"^[0-9a-f]{40}$")
_ROOT = Path(__file__).resolve().parents[1]
_COMPACT_CARRIER = (
    _ROOT / "benchmarks/cases/103_5nm_full3d_hybrid_feasibility/records/"
    "inherited_p6h10_topology_v1.json"
)
_TASK039_AUXILIARY_CHANNEL_NNZ = 2 * 882 + 1
_COMPLEX128_BYTES = 16


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InputError(f"Task39 capacity carrier cannot be read: {path}") from exc
    if not isinstance(value, dict):
        raise InputError(f"Task39 capacity carrier must be an object: {path}")
    return value


def _at(record: Mapping[str, Any], path: tuple[str, ...]) -> Any:
    value: Any = record
    for key in path:
        if not isinstance(value, Mapping) or key not in value:
            raise InputError(f"Task39 capacity carrier missing {'.'.join(path)}")
        value = value[key]
    return value


def _require_int(
    record: Mapping[str, Any], path: tuple[str, ...], expected: int
) -> int:
    value = _at(record, path)
    if isinstance(value, bool) or not isinstance(value, int) or value != expected:
        raise InputError(
            f"Task39 capacity carrier {'.'.join(path)}={value!r}, expected {expected}"
        )
    return value


def _require_float(
    record: Mapping[str, Any], path: tuple[str, ...], expected: float
) -> float:
    value = _at(record, path)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or value != expected
    ):
        raise InputError(
            f"Task39 capacity carrier {'.'.join(path)}={value!r}, expected {expected}"
        )
    return float(value)


def _inherited_geometry_topology() -> dict[str, Any]:
    carrier = _read_json(_COMPACT_CARRIER)
    source = carrier["sources"]["full3d_geometry"]
    if (
        source.get("classification") != "inherited_measured"
        or source.get("role") != "same_geometry_topology_not_5nm_measurement"
    ):
        raise InputError("Task39 compact geometry carrier classification is invalid")
    record = source["fields"]
    values = {
        "cells": _require_int(record, ("cells",), 252),
        "full_fe_dofs": _require_int(record, ("full_fe_dofs",), 173802),
        "active_trace_rows": _require_int(record, ("active_trace_rows",), 51192),
        "old_auxiliary_rows": _require_int(record, ("old_auxiliary_rows",), 80),
        "old_total_rows": _require_int(record, ("old_total_rows",), 51272),
        "old_matrix_nnz": _require_float(record, ("old_matrix_nnz",), 41989040.0),
    }
    return {
        "classification": source["classification"],
        "role": source["role"],
        "path": source["path"],
        "record_sha256": source["sha256"],
        "values": values,
    }


def _inherited_hybrid_topology() -> dict[str, Any]:
    carrier = _read_json(_COMPACT_CARRIER)
    source = carrier["sources"]["hybrid_endcaps"]
    if (
        source.get("classification") != "inherited_measured"
        or source.get("role") != "same_geometry_topology_not_5nm_measurement"
    ):
        raise InputError("Task39 compact hybrid carrier classification is invalid")
    record = source["fields"]
    values: dict[str, dict[str, int]] = {}
    for side in ("bottom", "top"):
        section = (side,)
        values[side] = {
            "full_fe_rows": _require_int(record, section + ("full_fe_rows",), 25986),
            "trace_rows_before_constraints": _require_int(
                record, section + ("trace_rows_before_constraints",), 9786
            ),
            "active_trace_rows": _require_int(
                record, section + ("active_trace_rows",), 8424
            ),
            "cell_interior_rows": _require_int(
                record, section + ("cell_interior_rows",), 16200
            ),
            "floquet_slave_rows": _require_int(
                record, section + ("floquet_slave_rows",), 1362
            ),
            "old_external_auxiliary_rows": _require_int(
                record, section + ("old_external_auxiliary_rows",), 40
            ),
            "old_local_algebra_rows": _require_int(
                record, section + ("old_local_algebra_rows",), 8464
            ),
        }
    if values["bottom"] != values["top"]:
        raise InputError("Task39 inherited hybrid topology differs between sides")
    return {
        "classification": source["classification"],
        "role": source["role"],
        "path": source["path"],
        "record_sha256": source["sha256"],
        "values": values,
    }


def _derived_estimates(
    inventory: Mapping[str, Any],
    geometry: Mapping[str, Any],
    hybrid: Mapping[str, Any],
) -> dict[str, Any]:
    counts = inventory["counts"]
    total_channels = int(inventory["count"])
    per_side = counts["per_side"]
    old = geometry["values"]
    base_fe_nnz = old["old_matrix_nnz"] - (
        old["old_auxiliary_rows"] * _TASK039_AUXILIARY_CHANNEL_NNZ
    )
    estimated_nnz = base_fe_nnz + total_channels * _TASK039_AUXILIARY_CHANNEL_NNZ
    full3d = {
        "classification": "derived_estimate",
        "rows": old["active_trace_rows"] + total_channels,
        "nnz": int(estimated_nnz),
        "formula": {
            "rows": "historical active_trace_rows + current total external channels",
            "nnz": "base_fe_nnz + current total channels * (2*882+1)",
            "per_auxiliary_channel_topology_nnz": _TASK039_AUXILIARY_CHANNEL_NNZ,
            "per_auxiliary_channel_topology_formula": "2*882+1",
            "per_auxiliary_channel_topology_classification": "derived_estimate",
            "per_auxiliary_channel_topology_source": (
                "Task39 A0 formula assumption; 095 carrier does not measure this field"
            ),
            "historical_auxiliary_contribution": old["old_auxiliary_rows"]
            * _TASK039_AUXILIARY_CHANNEL_NNZ,
            "base_fe_nnz": int(base_fe_nnz),
        },
        "assumptions": [
            "1765/mode is a Task39 topology assumption, not a 095 measured field",
            "FE sparsity outside external auxiliary channels is unchanged",
            "rows and NNZ are estimates, not Task39 measurements",
        ],
    }
    hybrid_values = hybrid["values"]
    sides: dict[str, Any] = {}
    total_w = 0
    total_k = 0
    for side in ("bottom", "top"):
        n_side = int(per_side[side])
        rows = hybrid_values[side]["active_trace_rows"] + n_side
        w_bytes = hybrid_values[side]["active_trace_rows"] * n_side * _COMPLEX128_BYTES
        k_bytes = n_side * n_side * _COMPLEX128_BYTES
        total_w += w_bytes
        total_k += k_bytes
        sides[side] = {
            "classification": "derived_estimate",
            "external_channels": n_side,
            "local_algebra_rows": rows,
            "W_bytes_complex128": w_bytes,
            "K_bytes_complex128": k_bytes,
            "formula": {
                "local_algebra_rows": "inherited active_trace_rows + current side channels",
                "W_bytes_complex128": "8424 * N_side * 16",
                "K_bytes_complex128": "N_side * N_side * 16",
            },
        }
    return {
        "full3d": full3d,
        "hybrid": {
            "classification": "derived_estimate",
            "sides": sides,
            "total_W_bytes_complex128": total_w,
            "total_K_bytes_complex128": total_k,
        },
    }


def build_task039_capacity_snapshot(
    specification: RunSpecification,
    *,
    verified_clean_source_sha: str | None = None,
    capacity_snapshot: Mapping[str, Any] | None = None,
    abi_snapshot: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build one deterministic A0 snapshot without querying live resources."""

    model_id = str(specification.identity.get("model_id", ""))
    if (
        model_id != "task039_5nm_full3d_direct"
        or specification.method.get("kind") != "full3d_direct"
    ):
        raise InputError(
            "Task39 capacity calculator accepts only task039_5nm_full3d_direct"
        )
    if verified_clean_source_sha is not None and not _SOURCE_SHA.fullmatch(
        verified_clean_source_sha
    ):
        raise InputError(
            "verified_clean_source_sha must be 40 lowercase hex characters"
        )
    inventory = task039_dynamic_external_mode_inventory(specification.as_jsonable())
    inventory_sha = sha256(canonical_json_bytes(inventory)).hexdigest()
    geometry = _inherited_geometry_topology()
    hybrid = _inherited_hybrid_topology()
    return {
        "schema_version": "task039.preflight-capacity.v1",
        "classification": "deterministic_capacity_estimate",
        "model_id": model_id,
        "source_path": specification.source_path.relative_to(_ROOT).as_posix(),
        "input_sha256": specification.input_sha256,
        "physical_model_sha256": specification.physical_model_sha256,
        "resolved_config_sha256": resolved_config_sha256(specification),
        "external_mode_inventory": inventory,
        "external_mode_inventory_sha256": inventory_sha,
        "inherited_geometry_topology": geometry,
        "inherited_hybrid_topology": hybrid,
        "derived_estimates": _derived_estimates(inventory, geometry, hybrid),
        "provenance": {
            "verified_clean_source_sha": verified_clean_source_sha,
            "capacity_snapshot": deepcopy(capacity_snapshot),
            "abi_snapshot": deepcopy(abi_snapshot),
        },
    }


def build_task039_capacity_snapshot_from_dat(
    dat_path: str | Path,
    **kwargs: Any,
) -> dict[str, Any]:
    """Resolve one dat and build its deterministic Task39 A0 snapshot."""

    return build_task039_capacity_snapshot(load_and_resolve(dat_path), **kwargs)


def write_task039_capacity_snapshot(
    snapshot: Mapping[str, Any], target: str | Path
) -> str:
    """Write a caller-supplied snapshot for T2b without collecting live data."""

    path = Path(target)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(snapshot) + b"\n")
    return sha256(path.read_bytes()).hexdigest()


__all__ = [
    "build_task039_capacity_snapshot",
    "build_task039_capacity_snapshot_from_dat",
    "write_task039_capacity_snapshot",
]
