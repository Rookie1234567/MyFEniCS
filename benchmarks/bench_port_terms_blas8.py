#!/usr/bin/env python3
"""Opt-in comparison of serial and scoped BLAS8 local port condensation.

This draft is intentionally outside src/. Do not run its production-data path
until the main review approves the frozen production-cell bundle and launch
contract. The bounded synthetic unit-test command uses no target data.
"""
from __future__ import annotations

import argparse
import ctypes
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import resource
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
from typing import Any

import numpy as np
from scipy.linalg import lu_solve
from scipy import sparse

SCHEMA = "cx9z10.port_terms_blas8_bundle.v1"
ERROR_TOL = 1.0e-12
MAX_CELLS = 3
_OPENBLAS_API: tuple[Any, str, Any, Any] | None = None


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _write_once(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _run_fresh_child_posix_spawn(
    command: list[str],
    *,
    env: dict[str, str],
    stdout_path: Path,
    stderr_path: Path,
) -> int:
    """Start a clean numeric child without Python fork after MPI initialization."""
    with stdout_path.open("xb") as stdout_stream, stderr_path.open("xb") as stderr_stream:
        actions = [
            (os.POSIX_SPAWN_DUP2, stdout_stream.fileno(), 1),
            (os.POSIX_SPAWN_DUP2, stderr_stream.fileno(), 2),
            (os.POSIX_SPAWN_CLOSE, stdout_stream.fileno()),
            (os.POSIX_SPAWN_CLOSE, stderr_stream.fileno()),
        ]
        child_pid = os.posix_spawn(
            command[0],
            command,
            env,
            file_actions=actions,
        )
        while True:
            try:
                _waited_pid, wait_status = os.waitpid(child_pid, 0)
                break
            except InterruptedError:
                continue
    return os.waitstatus_to_exitcode(wait_status)


def _dense(value: Any) -> np.ndarray:
    if hasattr(value, "toarray"):
        value = value.toarray()
    return np.asarray(value)


def _work_score(ni: int, nt: int, nports: int) -> int:
    # Upper-bound proxy for the LU solve, three local products, and two MPC
    # projection products. Selection is only for representative capture.
    return ni * ni * nports + 2 * nt * ni * nports + ni * nports * nports


def _carrier_port_side_inventory(carrier: Any) -> dict[str, Any]:
    """Derive non-contiguous port-side indices from actual carrier entries."""
    entries = getattr(carrier, "entries", None)
    if entries is None and getattr(carrier, "carrier", None) is not None:
        carrier = carrier.carrier
        entries = getattr(carrier, "entries", None)
    entries = tuple(entries or ())
    if not entries:
        raise ValueError("carrier has no ordered entries for top/bottom provenance")
    by_side: dict[str, list[int]] = {"top": [], "bottom": []}
    ordered_identity: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        identity = getattr(entry, "mode_identity", None)
        if not isinstance(identity, dict) and not hasattr(identity, "items"):
            raise ValueError(f"carrier entry {index} lacks mode_identity metadata")
        row = dict(identity)
        if row.get("mode_index") != index:
            raise ValueError(f"carrier mode index order mismatch at entry {index}")
        side = row.get("side")
        if side not in by_side:
            raise ValueError(f"carrier entry {index} has unsupported side {side!r}")
        by_side[side].append(index)
        ordered_identity.append({"mode_index": index, "side": side})
    manifest_bytes = getattr(carrier, "mode_manifest_bytes", None)
    if not isinstance(manifest_bytes, bytes):
        raise ValueError("carrier lacks persisted ordered mode manifest bytes")
    computed_sha = hashlib.sha256(manifest_bytes).hexdigest()
    declared_sha = getattr(carrier, "mode_manifest_sha256", computed_sha)
    if declared_sha != computed_sha:
        raise ValueError("carrier mode-manifest SHA does not match its bytes")
    return {
        "port_side_indices": by_side,
        "port_mode_manifest_sha256": computed_sha,
        "port_mode_count": len(entries),
        "ordered_mode_identity_sha256": hashlib.sha256(
            json.dumps(ordered_identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }


def _normalized_port_side_indices(
    provenance: dict[str, Any],
) -> tuple[dict[str, set[int]], str | None]:
    raw = provenance.get("port_side_indices")
    if not isinstance(raw, dict):
        return {}, "port_side_indices_missing"
    by_side: dict[str, set[int]] = {}
    for side in ("top", "bottom"):
        value = raw.get(side)
        if (
            not isinstance(value, (list, tuple))
            or not value
            or not all(isinstance(item, (int, np.integer)) for item in value)
        ):
            return {}, f"port_side_indices_invalid:{side}"
        side_indices = {int(item) for item in value}
        if min(side_indices) < 0 or len(side_indices) != len(value):
            return {}, f"port_side_indices_invalid:{side}"
        by_side[side] = side_indices
    if by_side["top"] & by_side["bottom"]:
        return {}, "port_side_indices_overlap"
    manifest_sha = provenance.get("port_mode_manifest_sha256")
    if not isinstance(manifest_sha, str) or len(manifest_sha) != 64:
        return {}, "port_mode_manifest_sha256_missing"
    mode_count = provenance.get("port_mode_count")
    if not isinstance(mode_count, (int, np.integer)) or int(mode_count) <= 0:
        return {}, "port_mode_count_missing"
    if any(
        any(index >= int(mode_count) for index in indices)
        for indices in by_side.values()
    ):
        return {}, "port_side_index_out_of_manifest_bounds"
    return by_side, None


def _select_representative_terms(
    condensed: Any,
    port_terms: dict[int, Any],
    provenance: dict[str, Any],
    *,
    max_cells: int = MAX_CELLS,
) -> tuple[dict[int, Any], dict[str, Any]]:
    """Select <=3 cells from light metadata before copying any term arrays."""
    if not 1 <= max_cells <= MAX_CELLS:
        raise ValueError(f"max_cells must be between 1 and {MAX_CELLS}")
    side_indices, side_error = _normalized_port_side_indices(provenance)
    candidates: list[dict[str, Any]] = []
    all_classes: set[str] = set()
    available_sides: set[str] = set()
    for index, term in port_terms.items():
        cell = condensed.cell_recovery_maps[index]
        class_key = repr(cell.class_key)
        ni = len(cell.interior_original_dofs)
        nt = len(cell.trace_original_dofs)
        bi_shape = tuple(int(value) for value in term.Bi.shape)
        di_shape = tuple(int(value) for value in term.Di.shape)
        ports = np.asarray(term.port_indices)
        if ports.ndim != 1:
            raise ValueError(f"CellPortTerms.port_indices for cell {index} is not 1D")
        sides = sorted(
            side
            for side, indices in side_indices.items()
            if any(int(port) in indices for port in ports)
        )
        all_classes.add(class_key)
        available_sides.update(sides)
        candidates.append(
            {
                "index": int(index),
                "class_key": class_key,
                "ni": int(ni),
                "nt": int(nt),
                "nports": int(len(ports)),
                "Bi_shape": list(bi_shape),
                "Di_shape": list(di_shape),
                "port_min": int(np.min(ports)) if len(ports) else None,
                "port_max": int(np.max(ports)) if len(ports) else None,
                "port_sides": sides,
                "work_score": int(_work_score(ni, nt, len(ports))),
            }
        )

    if not candidates:
        return {}, {
            "policy": "metadata_only_diverse_class_and_top_bottom_ports",
            "selected": [],
            "coverage_sufficient": False,
            "coverage_reason": "no_port_terms",
        }

    selected: list[dict[str, Any]] = []
    covered_classes: set[str] = set()
    covered_sides: set[str] = set()
    remaining = list(candidates)
    while remaining and len(selected) < max_cells:
        chosen = max(
            remaining,
            key=lambda item: (
                len(set(item["port_sides"]) - covered_sides),
                int(item["class_key"] not in covered_classes),
                item["work_score"],
                -item["index"],
            ),
        )
        selected.append(chosen)
        covered_classes.add(chosen["class_key"])
        covered_sides.update(chosen["port_sides"])
        remaining.remove(chosen)

    required_class_count = min(2, len(all_classes))
    required_sides = {"top", "bottom"}
    coverage_sufficient = (
        side_error is None
        and len(covered_classes) >= required_class_count
        and required_sides.issubset(covered_sides)
    )
    reasons = []
    if side_error is not None:
        reasons.append(side_error)
    if len(covered_classes) < required_class_count:
        reasons.append("insufficient_distinct_classes")
    if not required_sides.issubset(covered_sides):
        reasons.append("top_bottom_port_coverage_incomplete")
    selection = {
        "policy": "metadata_only_diverse_class_and_top_bottom_ports",
        "max_cells": max_cells,
        "available_class_count": len(all_classes),
        "required_class_count": required_class_count,
        "selected_class_count": len(covered_classes),
        "available_sides": sorted(available_sides),
        "selected_sides": sorted(covered_sides),
        "required_sides": sorted(required_sides),
        "port_mode_manifest_sha256": provenance.get("port_mode_manifest_sha256"),
        "port_mode_count": provenance.get("port_mode_count"),
        "ordered_mode_identity_sha256": provenance.get("ordered_mode_identity_sha256"),
        "selected": selected,
        "coverage_sufficient": coverage_sufficient,
        "coverage_reason": None if coverage_sufficient else ";".join(reasons),
        "selection_completed_before_array_copy": True,
    }
    return {item["index"]: port_terms[item["index"]] for item in selected}, selection


def _thread_cpu_ticks() -> dict[int, int]:
    """Read Linux per-thread user+system CPU ticks for concurrency evidence."""
    ticks: dict[int, int] = {}
    for task in Path("/proc/self/task").iterdir():
        try:
            stat = (task / "stat").read_text()
        except FileNotFoundError:
            continue
        close = stat.rfind(")")
        if close < 0:
            raise RuntimeError(f"malformed /proc thread stat for TID {task.name}")
        fields = stat[close + 1 :].split()  # starts with field 3 (state)
        if len(fields) < 13:
            raise RuntimeError(f"short /proc thread stat for TID {task.name}")
        ticks[int(task.name)] = int(fields[11]) + int(fields[12])
    return ticks


def _thread_activity_delta(
    before: dict[int, int], after: dict[int, int]
) -> dict[str, Any]:
    deltas = {
        tid: max(0, value - before.get(tid, 0)) for tid, value in after.items()
    }
    active = [tid for tid, delta in deltas.items() if delta > 0]
    native_id = threading.get_native_id()
    active_workers = [tid for tid in active if tid != native_id]
    return {
        "observed_thread_count_after": len(after),
        "active_thread_count": len(active),
        "active_worker_thread_count": len(active_workers),
        "active_worker_cpu_ticks": int(sum(deltas[tid] for tid in active_workers)),
    }


def freeze_live_terms(
    condensed: Any,
    port_terms: dict[int, Any],
    *,
    output_npz: str | Path,
    provenance: dict[str, Any],
    max_cells: int = MAX_CELLS,
) -> dict[str, Any]:
    """Freeze <=3 caller-selected actual production cells.

    The caller must pass only the selected-cell mapping, never the complete
    carrier/terms mapping. This function copies only those arrays; it does not
    build a carrier, matrix, mesh, or element tensor.
    """
    if not 1 <= max_cells <= MAX_CELLS:
        raise ValueError(f"max_cells must be between 1 and {MAX_CELLS}")
    if not 1 <= len(port_terms) <= MAX_CELLS:
        raise ValueError("pass only one to three already-selected production cells")
    source_sha = provenance.get("source_sha")
    profile_sha = provenance.get("target_profile_sha256")
    geometry_by_index = provenance.get("cell_geometry_by_index")
    if not isinstance(source_sha, str) or len(source_sha) != 40:
        raise ValueError("provenance must bind the 40-character source SHA")
    if not isinstance(profile_sha, str) or len(profile_sha) != 64:
        raise ValueError("provenance must bind the target profile SHA256")
    if not isinstance(geometry_by_index, dict):
        raise ValueError("provenance must identify selected cell geometry")
    for key in ("mesh_sha256", "input_sha256"):
        if not isinstance(provenance.get(key), str) or len(provenance[key]) != 64:
            raise ValueError(f"provenance must bind {key}")
    for key in (
        "profile_sha256",
        "resolved_solver_profile_sha256",
        "resolved_profile_identity",
        "worker_sha256",
        "launcher_sha256",
        "benchmark_worker_sha256",
        "port_mode_manifest_sha256",
    ):
        value = provenance.get(key)
        if not isinstance(value, str) or not value:
            raise ValueError(f"provenance must bind {key}")
        if key != "resolved_profile_identity" and len(value) != 64:
            raise ValueError(f"provenance must bind a full SHA256 for {key}")

    candidates: list[tuple[int, str, int]] = []
    for index, term in port_terms.items():
        cell = condensed.cell_recovery_maps[index]
        ni = len(cell.interior_original_dofs)
        nt = len(cell.trace_original_dofs)
        nports = len(term.port_indices)
        candidates.append((_work_score(ni, nt, nports), repr(cell.class_key), int(index)))
    if not candidates:
        raise ValueError("no production CellPortTerms were supplied")

    selected: list[int] = []
    used_classes: set[str] = set()
    for _score, class_key, index in sorted(candidates, reverse=True):
        if class_key in used_classes:
            continue
        selected.append(index)
        used_classes.add(class_key)
        if len(selected) == max_cells:
            break
    if len(selected) < max_cells:
        for _score, _class_key, index in sorted(candidates, reverse=True):
            if index not in selected:
                selected.append(index)
                if len(selected) == max_cells:
                    break

    from src.solvers.hcurl_assembly_time_condensation import _cell_trace_expansion

    arrays: dict[str, np.ndarray] = {}
    cell_records: list[dict[str, Any]] = []
    for slot, index in enumerate(selected):
        geometry_record = geometry_by_index.get(str(index), geometry_by_index.get(index))
        required_geometry = {
            "cell_id",
            "coordinates_nm",
            "material_label",
            "raw_width_binary64_hex",
            "raw_class_key",
        }
        if not isinstance(geometry_record, dict) or not required_geometry.issubset(
            geometry_record
        ):
            raise ValueError(
                f"cell {index} geometry record must include {sorted(required_geometry)}"
            )
        cell = condensed.cell_recovery_maps[index]
        term = port_terms[index]
        lu, piv = condensed.interior_lu_by_class[cell.class_key]
        ids, expansion, _identity = _cell_trace_expansion(
            np.asarray(cell.trace_original_dofs), condensed.trace_constraints
        )
        if not sparse.isspmatrix_csr(expansion):
            raise TypeError("production trace expansion must remain CSR")
        prefix = f"c{slot}"
        values = {
            "lu": np.asarray(lu),
            "piv": np.asarray(piv),
            "xit": -np.asarray(
                condensed.interior_from_trace_by_class[cell.class_key]
            ),
            "trace_from_interior": _dense(
                condensed.trace_from_interior_rhs_by_class[cell.class_key]
            ),
            "expansion_data": np.asarray(expansion.data),
            "expansion_indices": np.asarray(expansion.indices),
            "expansion_indptr": np.asarray(expansion.indptr),
            "expansion_shape": np.asarray(expansion.shape, dtype=np.int64),
            "active_ids": np.asarray(ids, dtype=np.int64),
            "Bi": _dense(term.Bi),
            "Di": _dense(term.Di),
            "port_indices": np.asarray(term.port_indices, dtype=np.int64),
        }
        probe_digest = hashlib.sha256(
            str(geometry_record["cell_id"]).encode()
        ).digest()
        probe_rng = np.random.default_rng(
            int.from_bytes(probe_digest[:8], "little")
        )
        values["probe_x"] = probe_rng.standard_normal(expansion.shape[1]) + 1j * (
            probe_rng.standard_normal(expansion.shape[1])
        )
        values["probe_y"] = probe_rng.standard_normal(len(term.port_indices)) + 1j * (
            probe_rng.standard_normal(len(term.port_indices))
        )
        for optional in ("Bt", "Dt", "H"):
            value = getattr(term, optional, None)
            if value is not None:
                values[optional] = _dense(value)
        for name, value in values.items():
            arrays[f"{prefix}_{name}"] = np.ascontiguousarray(value)
        cell_records.append(
            {
                "slot": slot,
                "cell_index": int(index),
                "class_key_repr": repr(cell.class_key),
                "geometry": geometry_record,
                "probe_generator": "numpy.default_rng(sha256(cell_id)[0:8], little-endian)",
                "shapes": {name: list(value.shape) for name, value in values.items()},
                "dtypes": {name: str(value.dtype) for name, value in values.items()},
                "optional_terms": [name for name in ("Bt", "Dt", "H") if name in values],
            }
        )

    for name, value in arrays.items():
        if value.dtype.kind in "fc" and not np.isfinite(value).all():
            raise ValueError(f"non-finite frozen input array: {name}")

    bundle_path = Path(output_npz)
    manifest_path = bundle_path.with_suffix(".json")
    with bundle_path.open("xb") as stream:
        np.savez_compressed(stream, **arrays)
        stream.flush()
        os.fsync(stream.fileno())
    manifest = {
        "schema": SCHEMA,
        "source_sha": source_sha,
        "target_profile_sha256": profile_sha,
        "input_sha256": provenance["input_sha256"],
        "mesh_sha256": provenance["mesh_sha256"],
        "provenance": provenance,
        "array_file": bundle_path.name,
        "array_file_sha256": _sha256(bundle_path),
        "arrays": {
            name: {"shape": list(value.shape), "dtype": str(value.dtype)}
            for name, value in sorted(arrays.items())
        },
        "selected_cell_count": len(cell_records),
        "selection_policy": "caller_selected_at_most_three_actual_production_cells",
        "cells": cell_records,
    }
    _write_once(
        manifest_path,
        (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode(),
    )
    return manifest


def _openblas_thread_api() -> tuple[Any, str, Any, Any]:
    """Resolve the one already-loaded OpenBLAS pthread control API."""
    global _OPENBLAS_API
    if _OPENBLAS_API is not None:
        return _OPENBLAS_API

    mapped: set[str] = set()
    try:
        lines = Path("/proc/self/maps").read_text().splitlines()
    except OSError as exc:
        raise RuntimeError(f"cannot inspect loaded libraries for OpenBLAS: {exc}") from exc
    for line in lines:
        fields = line.split()
        if not fields:
            continue
        candidate = fields[-1]
        if "openblas" in Path(candidate).name.lower() and candidate.startswith("/"):
            mapped.add(os.path.realpath(candidate.removesuffix(" (deleted)")))
    if len(mapped) != 1:
        raise RuntimeError(
            f"expected exactly one loaded OpenBLAS shared library, found {sorted(mapped)}"
        )

    library_path = next(iter(mapped))
    library = ctypes.CDLL(library_path)
    try:
        get_threads = library.openblas_get_num_threads
        set_threads = library.openblas_set_num_threads
    except AttributeError as exc:
        raise RuntimeError(
            f"loaded OpenBLAS library lacks the required pthread thread API: {library_path}"
        ) from exc
    get_threads.argtypes = []
    get_threads.restype = ctypes.c_int
    set_threads.argtypes = [ctypes.c_int]
    set_threads.restype = None
    _OPENBLAS_API = (library, library_path, get_threads, set_threads)
    return _OPENBLAS_API


def _blas_snapshot() -> list[dict[str, Any]]:
    _library, library_path, get_threads, _set_threads = _openblas_thread_api()
    return [
        {
            "filepath": library_path,
            "internal_api": "openblas",
            "num_threads": int(get_threads()),
            "version": None,
        }
    ]


@contextmanager
def _openblas_threads(threads: int):
    """Set OpenBLAS threads for one scope and always restore the serial state."""
    _library, library_path, get_threads, set_threads = _openblas_thread_api()
    before = int(get_threads())
    if before != 1:
        raise RuntimeError(
            f"OpenBLAS must be 1 before scoped change; found {before} in {library_path}"
        )
    try:
        set_threads(int(threads))
        during = int(get_threads())
        if during != threads:
            raise RuntimeError(
                f"OpenBLAS readback differs from requested {threads}: found {during}"
            )
        yield
    finally:
        set_threads(1)
        after = int(get_threads())
        if after != 1:
            raise RuntimeError(
                f"OpenBLAS failed to restore to 1; found {after} in {library_path}"
            )


def _load_cells(bundle: Path) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    manifest_path = bundle.with_suffix(".json")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("schema") != SCHEMA:
        raise ValueError("unrecognized frozen CellPortTerms bundle schema")
    if manifest.get("array_file") != bundle.name:
        raise ValueError("manifest array filename differs from requested bundle")
    if manifest.get("array_file_sha256") != _sha256(bundle):
        raise ValueError("frozen array bundle SHA256 mismatch")
    if not 1 <= manifest.get("selected_cell_count", 0) <= MAX_CELLS:
        raise ValueError("bundle must contain between one and three cells")
    with np.load(bundle, allow_pickle=False) as stored:
        arrays = {name: stored[name] for name in stored.files}
    schema = manifest.get("arrays")
    if not isinstance(schema, dict) or set(schema) != set(arrays):
        raise ValueError("frozen bundle array keys differ from the hash-bound manifest")
    for name, value in arrays.items():
        expected = schema[name]
        if list(value.shape) != expected.get("shape"):
            raise ValueError(f"frozen array shape mismatch: {name}")
        if str(value.dtype) != expected.get("dtype"):
            raise ValueError(f"frozen array dtype mismatch: {name}")
        if value.dtype.kind in "fc" and not np.isfinite(value).all():
            raise ValueError(f"non-finite frozen input array: {name}")
    for cell in manifest["cells"]:
        _validate_cell_arrays(arrays, cell)
    return arrays, manifest


def _validate_cell_arrays(arrays: dict[str, np.ndarray], record: dict[str, Any]) -> None:
    prefix = f"c{record['slot']}"
    lu = arrays[f"{prefix}_lu"]
    piv = arrays[f"{prefix}_piv"]
    xit = arrays[f"{prefix}_xit"]
    transfer = arrays[f"{prefix}_trace_from_interior"]
    bi = arrays[f"{prefix}_Bi"]
    di = arrays[f"{prefix}_Di"]
    ports = arrays[f"{prefix}_port_indices"]
    active_ids = arrays[f"{prefix}_active_ids"]
    expansion_data = arrays[f"{prefix}_expansion_data"]
    expansion_indices = arrays[f"{prefix}_expansion_indices"]
    expansion_indptr = arrays[f"{prefix}_expansion_indptr"]
    expansion_shape_array = arrays[f"{prefix}_expansion_shape"]
    if lu.ndim != 2 or lu.shape[0] != lu.shape[1]:
        raise ValueError(f"invalid LU factor shape for {prefix}: {lu.shape}")
    ni = lu.shape[0]
    if piv.shape != (ni,) or piv.dtype.kind not in "iu":
        raise ValueError(f"invalid LU pivot shape/type for {prefix}")
    if xit.ndim != 2 or xit.shape[0] != ni:
        raise ValueError(f"invalid Xit shape for {prefix}: {xit.shape}")
    nt = xit.shape[1]
    if transfer.shape != (nt, ni):
        raise ValueError(f"invalid trace-from-interior shape for {prefix}")
    if bi.ndim != 2 or bi.shape[0] != ni:
        raise ValueError(f"invalid Bi shape for {prefix}: {bi.shape}")
    nports = bi.shape[1]
    if di.shape != (nports, ni) or ports.shape != (nports,):
        raise ValueError(f"invalid Di/port dimensions for {prefix}")
    if expansion_shape_array.shape != (2,) or expansion_shape_array.dtype.kind not in "iu":
        raise ValueError(f"invalid CSR expansion shape descriptor for {prefix}")
    expansion_shape = tuple(int(value) for value in expansion_shape_array)
    if expansion_shape[0] != nt or active_ids.shape != (expansion_shape[1],):
        raise ValueError(f"invalid CSR expansion dimensions for {prefix}")
    if expansion_data.ndim != 1 or expansion_indices.shape != expansion_data.shape:
        raise ValueError(f"invalid CSR data/index arrays for {prefix}")
    if expansion_indices.dtype.kind not in "iu" or expansion_indptr.dtype.kind not in "iu":
        raise ValueError(f"CSR index arrays must be integer for {prefix}")
    if expansion_indptr.shape != (nt + 1,):
        raise ValueError(f"invalid CSR indptr shape for {prefix}")
    if (
        int(expansion_indptr[0]) != 0
        or int(expansion_indptr[-1]) != len(expansion_data)
        or np.any(np.diff(expansion_indptr) < 0)
        or np.any(expansion_indices < 0)
        or np.any(expansion_indices >= expansion_shape[1])
    ):
        raise ValueError(f"invalid CSR structure for {prefix}")
    if arrays[f"{prefix}_probe_x"].shape != (expansion_shape[1],):
        raise ValueError(f"invalid complex probe x shape for {prefix}")
    if arrays[f"{prefix}_probe_y"].shape != (nports,):
        raise ValueError(f"invalid complex probe y shape for {prefix}")
    optional_shapes = {
        "Bt": (nt, nports),
        "Dt": (nports, nt),
        "H": (nports, nports),
    }
    for name, shape in optional_shapes.items():
        key = f"{prefix}_{name}"
        if key in arrays and arrays[key].shape != shape:
            raise ValueError(f"invalid optional {name} shape for {prefix}")


def _evaluate_cell(arrays: dict[str, np.ndarray], record: dict[str, Any]) -> dict[str, np.ndarray]:
    prefix = f"c{record['slot']}"
    bi = arrays[f"{prefix}_Bi"]
    di = arrays[f"{prefix}_Di"]
    lu = (arrays[f"{prefix}_lu"], arrays[f"{prefix}_piv"])
    xit = arrays[f"{prefix}_xit"]
    trace_from_interior = arrays[f"{prefix}_trace_from_interior"]
    expansion_shape = tuple(
        int(value) for value in arrays[f"{prefix}_expansion_shape"]
    )
    expansion = sparse.csr_matrix(
        (
            arrays[f"{prefix}_expansion_data"],
            arrays[f"{prefix}_expansion_indices"],
            arrays[f"{prefix}_expansion_indptr"],
        ),
        shape=expansion_shape,
    )
    ports = arrays[f"{prefix}_port_indices"]
    if bi.shape[1] != di.shape[0] or bi.shape[1] != len(ports):
        raise ValueError(f"frozen B_i/D_i/port dimensions mismatch for {prefix}")

    xib = lu_solve(lu, bi)
    b_hat = trace_from_interior @ bi
    d_hat = -di @ xit
    h_hat = di @ xib
    if f"{prefix}_Bt" in arrays:
        b_hat = arrays[f"{prefix}_Bt"] + b_hat
    if f"{prefix}_Dt" in arrays:
        d_hat = arrays[f"{prefix}_Dt"] - di @ xit
    if f"{prefix}_H" in arrays:
        h_hat = arrays[f"{prefix}_H"] + h_hat
    b_active = np.ascontiguousarray(expansion.conj().T @ b_hat)
    d_active = np.ascontiguousarray(d_hat @ expansion)
    h_hat = np.ascontiguousarray(h_hat)

    return {
        "Bhat": np.ascontiguousarray(b_hat),
        "Dhat": np.ascontiguousarray(d_hat),
        "Hhat": h_hat,
        "Bactive": b_active,
        "Dactive": d_active,
    }


def _probe_action(
    result_arrays: dict[str, np.ndarray], arrays: dict[str, np.ndarray], prefix: str
) -> np.ndarray:
    x = arrays[f"{prefix}_probe_x"]
    y = arrays[f"{prefix}_probe_y"]
    upper = result_arrays[f"{prefix}_Bactive"] @ y
    lower = (
        -result_arrays[f"{prefix}_Dactive"] @ x
        + result_arrays[f"{prefix}_Hhat"] @ y
    )
    action = np.concatenate((upper, lower))
    if not np.isfinite(action).all() or float(np.linalg.norm(action)) == 0.0:
        raise ValueError(f"probe action must be finite and nonzero for {prefix}")
    return action


class _ExpectedRestoreProbe(Exception):
    """Intentional exception used only to verify BLAS context restoration."""


def _worker(args: argparse.Namespace) -> int:
    if "mpi4py" in sys.modules:
        raise RuntimeError("numeric child must not import or initialize MPI")
    bundle = Path(args.bundle).resolve()
    arrays, manifest = _load_cells(bundle)
    before = _blas_snapshot()
    before_one = bool(before) and all(item["num_threads"] == 1 for item in before)
    result_arrays: dict[str, np.ndarray] | None = None
    samples_wall: list[float] = []
    error: str | None = None
    during: list[dict[str, Any]] = []
    restore_probe_during: list[dict[str, Any]] = []
    restore_probe_after: list[dict[str, Any]] = []
    exception_restore_ok = False
    cpu_seconds = 0.0
    thread_activity: dict[str, Any] = {}
    cpu_wall_ratio: float | None = None
    probe_validation_wall_seconds: float | None = None
    try:
        if not before_one:
            raise RuntimeError(f"OpenBLAS must be 1 before each child: {before}")
        try:
            with _openblas_threads(args.threads):
                restore_probe_during = _blas_snapshot()
                if any(
                    item["num_threads"] != args.threads
                    for item in restore_probe_during
                ):
                    raise RuntimeError(
                        f"exception probe readback mismatch: {restore_probe_during}"
                    )
                raise _ExpectedRestoreProbe("intentional context-exit check")
        except _ExpectedRestoreProbe:
            pass
        restore_probe_after = _blas_snapshot()
        exception_restore_ok = bool(restore_probe_after) and all(
            item["num_threads"] == 1 for item in restore_probe_after
        )
        if not exception_restore_ok:
            raise RuntimeError(
                f"intentional exception did not restore BLAS to 1: {restore_probe_after}"
            )
        with _openblas_threads(args.threads):
            during = _blas_snapshot()
            if any(item["num_threads"] != args.threads for item in during):
                raise RuntimeError(
                    f"OpenBLAS readback differs from requested {args.threads}: {during}"
                )
            for _ in range(args.warmups):
                for cell in manifest["cells"]:
                    _evaluate_cell(arrays, cell)
            samples_wall = []
            thread_ticks_before = _thread_cpu_ticks()
            cpu_start = time.process_time()
            final: dict[str, np.ndarray] = {}
            for _ in range(args.iterations):
                started = time.perf_counter()
                current: dict[str, np.ndarray] = {}
                for cell in manifest["cells"]:
                    current.update(
                        {
                            f"c{cell['slot']}_{name}": value
                            for name, value in _evaluate_cell(arrays, cell).items()
                        }
                    )
                samples_wall.append(time.perf_counter() - started)
                final = current
            cpu_seconds = time.process_time() - cpu_start
            thread_ticks_after = _thread_cpu_ticks()
            thread_activity = _thread_activity_delta(
                thread_ticks_before, thread_ticks_after
            )
            measured_wall = float(sum(samples_wall))
            cpu_wall_ratio = (
                cpu_seconds / measured_wall if measured_wall > 0.0 else None
            )
            result_arrays = final
        probe_started = time.perf_counter()
        for cell in manifest["cells"]:
            prefix = f"c{cell['slot']}"
            result_arrays[f"{prefix}_probe_action"] = _probe_action(
                result_arrays, arrays, prefix
            )
        probe_validation_wall_seconds = time.perf_counter() - probe_started
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        after = _blas_snapshot()

    restored_one = bool(after) and all(item["num_threads"] == 1 for item in after)
    if not restored_one and error is None:
        error = f"BLAS thread limit did not restore to 1: {after}"
    output_prefix = Path(args.output_prefix)
    report = {
        "schema": "cx9z10.port_terms_blas8_worker.v1",
        "bundle_sha256": _sha256(bundle),
        "thread_count_requested": args.threads,
        "thread_count_before": before,
        "before_was_one": before_one,
        "exception_restore_probe_during": restore_probe_during,
        "exception_restore_probe_after": restore_probe_after,
        "intentional_exception_restored_one": exception_restore_ok,
        "thread_count_during": during,
        "thread_count_after": after,
        "error_path_restored_one": restored_one,
        "warmups": args.warmups,
        "measured_iterations": args.iterations,
        "wall_seconds_per_iteration": samples_wall,
        "median_wall_seconds": float(np.median(samples_wall)) if samples_wall else None,
        "cpu_seconds_measured": cpu_seconds,
        "measured_wall_seconds_total": float(sum(samples_wall)),
        "cpu_to_wall_ratio": cpu_wall_ratio,
        "native_thread_activity": thread_activity,
        "probe_validation_wall_seconds_outside_benchmark": probe_validation_wall_seconds,
        "peak_rss_bytes": int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024),
        "cpu_affinity": sorted(os.sched_getaffinity(0)),
        "error": error,
    }
    if result_arrays is not None:
        with Path(str(output_prefix) + ".npz").open("xb") as stream:
            np.savez_compressed(stream, **result_arrays)
            stream.flush()
            os.fsync(stream.fileno())
    _write_once(
        Path(str(output_prefix) + ".json"),
        (json.dumps(report, sort_keys=True, indent=2) + "\n").encode(),
    )
    print(json.dumps(report, sort_keys=True), flush=True)
    return 2 if error else 0


def _error_metrics(reference: np.ndarray, candidate: np.ndarray) -> dict[str, Any]:
    ref = np.asarray(reference)
    candidate = np.asarray(candidate)
    if candidate.shape != ref.shape or candidate.dtype != ref.dtype:
        raise ValueError(
            f"operator output shape/dtype mismatch: {ref.shape}/{ref.dtype} "
            f"vs {candidate.shape}/{candidate.dtype}"
        )
    if ref.dtype.kind in "fc" and (
        not np.isfinite(ref).all() or not np.isfinite(candidate).all()
    ):
        raise ValueError("operator comparison contains a non-finite value")
    diff = candidate - ref
    reference_norm = float(np.linalg.norm(ref.ravel()))
    diff_norm = float(np.linalg.norm(diff.ravel()))
    zero_norm = reference_norm == 0.0
    relative = None if zero_norm else diff_norm / reference_norm
    abs_max = float(np.max(np.abs(diff), initial=0.0))
    passed = (abs_max == 0.0) if zero_norm else bool(relative <= ERROR_TOL)
    return {
        "max_abs": abs_max,
        "reference_norm": reference_norm,
        "difference_norm": diff_norm,
        "zero_norm": zero_norm,
        "relative_error": relative,
        "passed_1e-12": passed,
    }


def _unit_test_synthetic() -> int:
    """Bounded CSR/thread-restoration regression; never target evidence."""
    from scipy.linalg import lu_factor

    rng = np.random.default_rng(4108)

    def complex_array(shape: tuple[int, ...]) -> np.ndarray:
        return rng.standard_normal(shape) + 1j * rng.standard_normal(shape)

    ni, nt, nactive, nports = 8, 6, 4, 5
    raw = complex_array((ni, ni))
    matrix = raw.conj().T @ raw + 4.0 * np.eye(ni)
    lu, piv = lu_factor(matrix)
    expansion = sparse.csr_matrix(complex_array((nt, nactive)))
    arrays = {
        "c0_lu": lu,
        "c0_piv": piv,
        "c0_xit": complex_array((ni, nt)),
        "c0_trace_from_interior": complex_array((nt, ni)),
        "c0_expansion_data": expansion.data.copy(),
        "c0_expansion_indices": expansion.indices.copy(),
        "c0_expansion_indptr": expansion.indptr.copy(),
        "c0_expansion_shape": np.asarray(expansion.shape, dtype=np.int64),
        "c0_active_ids": np.arange(nactive, dtype=np.int64),
        "c0_Bi": complex_array((ni, nports)),
        "c0_Di": complex_array((nports, ni)),
        "c0_port_indices": np.arange(nports, dtype=np.int64),
        "c0_probe_x": complex_array((nactive,)),
        "c0_probe_y": complex_array((nports,)),
    }
    record = {"slot": 0, "geometry": {"cell_id": "UNIT_TEST_SYNTHETIC_CELL"}}
    _validate_cell_arrays(arrays, record)
    before = _blas_snapshot()
    if not before or any(item["num_threads"] != 1 for item in before):
        raise RuntimeError(f"UNIT_TEST requires OpenBLAS before==1: {before}")

    restore_during: list[dict[str, Any]] = []
    try:
        with _openblas_threads(8):
            restore_during = _blas_snapshot()
            if any(item["num_threads"] != 8 for item in restore_during):
                raise RuntimeError("UNIT_TEST could not read back OpenBLAS=8")
            raise _ExpectedRestoreProbe("intentional UNIT_TEST exception")
    except _ExpectedRestoreProbe:
        pass
    restore_after = _blas_snapshot()
    if any(item["num_threads"] != 1 for item in restore_after):
        raise RuntimeError("UNIT_TEST exception path did not restore OpenBLAS=1")

    with _openblas_threads(1):
        one = _evaluate_cell(arrays, record)
    one_after = _blas_snapshot()
    with _openblas_threads(8):
        eight_readback = _blas_snapshot()
        if any(item["num_threads"] != 8 for item in eight_readback):
            raise RuntimeError("UNIT_TEST OpenBLAS=8 readback failed")
        eight = _evaluate_cell(arrays, record)
    eight_after = _blas_snapshot()
    one["probe_action"] = _probe_action(
        {f"c0_{name}": value for name, value in one.items()}, arrays, "c0"
    )
    eight["probe_action"] = _probe_action(
        {f"c0_{name}": value for name, value in eight.items()}, arrays, "c0"
    )

    metrics = {
        name: _error_metrics(one[name], eight[name])
        for name in sorted(one)
    }
    if any(not item["passed_1e-12"] for item in metrics.values()):
        raise AssertionError(f"UNIT_TEST CSR/operator error gate failed: {metrics}")
    if metrics["probe_action"]["zero_norm"]:
        raise AssertionError("UNIT_TEST complex probe action unexpectedly has zero norm")
    if any(item["num_threads"] != 1 for item in one_after + eight_after):
        raise AssertionError("UNIT_TEST normal path did not restore OpenBLAS=1")
    report = {
        "classification": "UNIT_TEST_SYNTHETIC_NOT_TARGET_DATA_OR_PERFORMANCE",
        "csr_representation_preserved": True,
        "before_threads": before,
        "intentional_exception_threads_during": restore_during,
        "intentional_exception_threads_after": restore_after,
        "normal_one_threads_after": one_after,
        "normal_eight_threads_during": eight_readback,
        "normal_eight_threads_after": eight_after,
        "operator_metrics": metrics,
        "speedup_claimed": False,
    }
    report["source_copy_exactly_once_gate_fault_injection"] = (
        _unit_test_source_gate_integration()
    )
    report["posix_spawn_after_mpi_init_smoke"] = _unit_test_posix_spawn()
    report["production_insertion_matrix_mock"] = _unit_test_production_insertion()
    report["representative_selection_metadata_mock"] = _unit_test_representative_selection()
    print(json.dumps(report, sort_keys=True), flush=True)
    return 0


def _unit_test_source_gate_integration() -> dict[str, Any]:
    """Exercise the copied production p4 hook with synthetic one-cell inputs."""
    from scipy.linalg import lu_factor
    import src.solvers.p4_cell_condensed_inverse as p4

    source_copy_root = Path(__file__).resolve().parents[1]
    if source_copy_root not in Path(p4.__file__).resolve().parents:
        raise AssertionError("UNIT_TEST did not import the isolated source-copy p4 module")

    sha = lambda char: char * 64
    source_sha = "a" * 40
    mode_bytes = b'{"modes":[{"mode_index":0,"side":"top"}]}'
    mode_sha = hashlib.sha256(mode_bytes).hexdigest()
    comparison = {
        "recommendation": "RECOMMEND_SCOPED_BLAS8",
        "numerical_gate": True,
        "speed_gate_1p10": True,
        "thread_readback_gate": True,
        "cpu_evidence_gate": True,
        "source_sha": source_sha,
        "profile_sha256": sha("b"),
        "input_sha256": sha("c"),
        "mesh_sha256": sha("d"),
        "port_mode_manifest_sha256": mode_sha,
        "worker_sha256": sha("e"),
        "launcher_sha256": sha("f"),
        "resolved_solver_profile_sha256": sha("1"),
        "benchmark_worker_sha256": sha("2"),
    }
    decision = p4.PortAssemblyExecutionDecision(
        profile_id=p4.CX9Z10_PRELU_B8_PROFILE_ID,
        source_sha=source_sha,
        worker_sha256=sha("e"),
        launcher_sha256=sha("f"),
        profile_sha256=sha("b"),
        resolved_solver_profile_sha256=sha("1"),
        benchmark_worker_sha256=sha("2"),
        input_sha256=sha("c"),
        mesh_sha256=sha("d"),
        carrier_mode_manifest_sha256=mode_sha,
        comparison_sha256=sha("3"),
        selected_cells=({"index": 0},),
        selection_coverage={
            "sufficient": True,
            "selected_sides": ["top", "bottom"],
            "selected_class_count": 1,
        },
        comparison=comparison,
    )

    class RecordingMatrix:
        def setValue(self, *_args: Any, **_kwargs: Any) -> None:
            return None

    class FakeGate:
        profile_id = p4.CX9Z10_PRELU_B8_PROFILE_ID

        def __init__(self, *, deny: bool = False):
            self.deny = deny
            self.preparation_error = "UNIT_TEST preparation denied" if deny else None
            self.finished: dict[str, Any] | None = None

        def prepare(self, **_kwargs: Any) -> Any:
            return None if self.deny else decision

        def finish(self, **kwargs: Any) -> dict[str, Any]:
            self.finished = {
                "status": kwargs["status"],
                "assembly_call_count": kwargs["assembly_call_count"],
                "assembly_started": kwargs["assembly_started"],
                "exception": kwargs["exception"],
            }
            return {"unit_test": self.finished}

    def fixture() -> tuple[Any, Any]:
        key = (3, 5.0, 2.0, 1.0, 0)
        cell = SimpleNamespace(
            interior_original_dofs=np.asarray([10]),
            trace_original_dofs=np.asarray([20]),
            class_key=key,
        )
        condensed = SimpleNamespace(
            matrix=RecordingMatrix(),
            appended_rows=1,
            active_rows=1,
            comm=SimpleNamespace(Get_size=lambda: 1),
            cell_recovery_maps=[cell],
            interior_lu_by_class={key: lu_factor(np.asarray([[2.0 + 0.0j]]))},
            interior_from_trace_by_class={key: np.asarray([[0.25 + 0.0j]])},
            trace_from_interior_rhs_by_class={key: np.asarray([[0.5 + 0.0j]])},
            trace_constraints=SimpleNamespace(original_to_active={20: 0}),
            build_audit={},
        )
        entry = SimpleNamespace(
            coupling_rows=np.asarray([10]),
            coupling_values=np.asarray([1.0 + 0.25j]),
            projection_rows=np.asarray([10]),
            projection_values=np.asarray([0.5 - 0.125j]),
            normalization_h=1.0 + 0.0j,
            mode_identity={"mode_index": 0, "side": "top"},
        )
        carrier = SimpleNamespace(
            entries=(entry,),
            mode_manifest_bytes=mode_bytes,
            mode_manifest_sha256=mode_sha,
        )
        return condensed, carrier

    old_assembler = p4.assemble_port_condensed_terms
    old_expansion = p4._cell_trace_expansion
    try:
        p4._cell_trace_expansion = lambda *_args: (
            np.asarray([0], dtype=np.int64),
            sparse.csr_matrix(np.asarray([[1.0 + 0.0j]])),
            "unit-test-identity",
        )
        outcomes: dict[str, Any] = {}
        for scenario in ("success", "pre_call_control_failure", "prepare_denied", "assembler_failure"):
            condensed, carrier = fixture()
            gate = FakeGate(deny=scenario == "prepare_denied")
            calls: list[int] = []

            def mock_assembler(_condensed: Any, _terms: Any) -> dict[str, Any]:
                threads = int(_blas_snapshot()[0]["num_threads"])
                calls.append(threads)
                if scenario == "assembler_failure":
                    raise ValueError("UNIT_TEST production callback failure")
                return {"matrix_identity": {"synthetic": True}, "nonzero_Bi": True}

            p4.assemble_port_condensed_terms = mock_assembler
            old_scope = p4.scoped_openblas_threads
            if scenario == "pre_call_control_failure":
                @contextmanager
                def control_failure(_threads: int):
                    raise p4.OpenBLASControlError(
                        "UNIT_TEST pre-call control failure",
                        serial_state_verified=True,
                    )
                    yield  # pragma: no cover

                p4.scoped_openblas_threads = control_failure
            try:
                try:
                    p4.assemble_condensed_ports(
                        condensed,
                        carrier,
                        pre_assembly_gate=gate,
                    )
                except ValueError as exc:
                    if scenario != "assembler_failure" or "callback failure" not in str(exc):
                        raise
                if scenario == "success" and calls != [8]:
                    raise AssertionError(f"success callback calls/threads: {calls}")
                if scenario in ("pre_call_control_failure", "prepare_denied") and calls != [1]:
                    raise AssertionError(f"serial fallback calls/threads: {calls}")
                if scenario == "assembler_failure" and calls != [8]:
                    raise AssertionError(f"failed callback was retried: {calls}")
                if gate.finished is None or gate.finished["assembly_call_count"] != 1:
                    raise AssertionError(f"source-copy terminal record missing: {gate.finished}")
                if scenario == "assembler_failure" and gate.finished["status"] != "FAILED_AFTER_ASSEMBLY_START":
                    raise AssertionError("post-start failure did not preserve failure status")
                if scenario == "pre_call_control_failure" and gate.finished["status"] != "COMPLETED_SERIAL_FALLBACK":
                    raise AssertionError("pre-call control failure did not use serial fallback")
                outcomes[scenario] = {
                    "callback_threads": calls,
                    "terminal_status": gate.finished["status"],
                    "exactly_once": gate.finished["assembly_call_count"] == 1,
                }
            finally:
                p4.scoped_openblas_threads = old_scope
    finally:
        p4.assemble_port_condensed_terms = old_assembler
        p4._cell_trace_expansion = old_expansion
    if any(item["num_threads"] != 1 for item in _blas_snapshot()):
        raise AssertionError("source-copy integration left OpenBLAS above one thread")
    return {
        "classification": "UNIT_TEST_SYNTHETIC_NOT_TARGET_DATA_OR_PERFORMANCE",
        "isolated_p4_module": str(Path(p4.__file__).resolve()),
        "scenarios": outcomes,
        "final_threads": _blas_snapshot(),
    }


def _unit_test_posix_spawn() -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="cx9z10_posix_spawn_unit_") as temporary:
        root = Path(temporary)
        stdout_path = root / "child.stdout"
        stderr_path = root / "child.stderr"
        code = (
            "import sys; "
            "print('FRESH_NUMERIC_CHILD_OK'); "
            "print('mpi4py' in sys.modules, file=sys.stderr)"
        )
        returncode = _run_fresh_child_posix_spawn(
            [sys.executable, "-c", code],
            env=os.environ.copy(),
            stdout_path=stdout_path,
            stderr_path=stderr_path,
        )
        stdout = stdout_path.read_text().strip()
        stderr = stderr_path.read_text().strip()
        if returncode != 0 or stdout != "FRESH_NUMERIC_CHILD_OK" or stderr != "False":
            raise AssertionError(
                f"posix_spawn smoke failed: rc={returncode}, stdout={stdout!r}, stderr={stderr!r}"
            )
        return {
            "classification": "UNIT_TEST_SYNTHETIC_NOT_TARGET_DATA_OR_PERFORMANCE",
            "spawn_api": "os.posix_spawn+waitpid",
            "returncode": returncode,
            "fresh_process_did_not_import_mpi4py": True,
        }


def _unit_test_production_insertion() -> dict[str, Any]:
    from scipy.linalg import lu_factor
    import src.solvers.p4_cell_condensed_inverse as p4_module

    rng = np.random.default_rng(108)

    def complex_array(shape: tuple[int, ...]) -> np.ndarray:
        return rng.standard_normal(shape) + 1j * rng.standard_normal(shape)

    class RecordingMatrix:
        def __init__(self, size: int):
            self.values = np.zeros((size, size), dtype=np.complex128)
            self.calls = 0
            self.assembled = False

        def setValues(self, rows: Any, columns: Any, values: Any, **_kwargs: Any) -> None:
            row_ids = np.asarray(rows, dtype=np.int64).reshape(-1)
            column_ids = np.asarray(columns, dtype=np.int64).reshape(-1)
            block = np.asarray(values, dtype=np.complex128)
            if block.shape != (len(row_ids), len(column_ids)):
                raise AssertionError("production setValues block shape changed")
            self.values[np.ix_(row_ids, column_ids)] += block
            self.calls += 1

        def assemble(self) -> None:
            self.assembled = True

    ni, nt, nactive, nports = 3, 2, 2, 2
    raw = complex_array((ni, ni))
    vii = raw.conj().T @ raw + 3.0 * np.eye(ni)
    lu, piv = lu_factor(vii)
    class_key = ("UNIT_TEST_CLASS", 7)
    cell = SimpleNamespace(
        class_key=class_key,
        interior_original_dofs=np.arange(ni),
        trace_original_dofs=np.asarray([20, 21]),
    )
    ids = np.asarray([0, 2], dtype=np.int64)
    expansion = sparse.csr_matrix(
        np.asarray([[1.0, 0.0], [0.25 + 0.1j, 1.0]], dtype=np.complex128)
    )
    interior_from_trace = complex_array((ni, nt))
    trace_from_interior = complex_array((nt, ni))
    bi = complex_array((ni, nports))
    di = complex_array((nports, ni))
    bt = complex_array((nt, nports))
    dt = complex_array((nports, nt))
    h = complex_array((nports, nports))
    ports = np.asarray([1, 2], dtype=np.int64)
    matrix = RecordingMatrix(8)
    condensed = SimpleNamespace(
        matrix=matrix,
        appended_rows=3,
        cell_recovery_maps=[cell],
        interior_lu_by_class={class_key: (lu, piv)},
        interior_from_trace_by_class={class_key: interior_from_trace},
        trace_from_interior_rhs_by_class={class_key: trace_from_interior},
        trace_constraints=object(),
        active_rows=5,
        build_audit={},
    )
    term = p4_module.CellPortTerms(Bi=bi, Di=di, port_indices=ports, Bt=bt, Dt=dt, H=h)
    old_expansion = p4_module._cell_trace_expansion
    old_identity = p4_module.petsc_csr_content_identity
    try:
        p4_module._cell_trace_expansion = lambda *_args: (ids, expansion, "mock")
        p4_module.petsc_csr_content_identity = lambda _matrix: {"mock_identity": True}
        audit = p4_module.assemble_port_condensed_terms(condensed, {0: term})
    finally:
        p4_module._cell_trace_expansion = old_expansion
        p4_module.petsc_csr_content_identity = old_identity

    xit = -interior_from_trace
    xib = lu_solve((lu, piv), bi)
    b_hat = bt + trace_from_interior @ bi
    d_hat = dt - di @ xit
    h_hat = h + di @ xib
    global_ports = condensed.active_rows + ports
    expected = np.zeros((8, 8), dtype=np.complex128)
    expected[np.ix_(ids, global_ports)] += expansion.conj().T @ b_hat
    expected[np.ix_(global_ports, ids)] += -(d_hat @ expansion)
    expected[np.ix_(global_ports, global_ports)] += h_hat
    np.testing.assert_allclose(matrix.values, expected, rtol=0.0, atol=1e-12)
    if matrix.calls != 3 or not matrix.assembled:
        raise AssertionError("production matrix insertion call pattern changed")
    if audit["cells_with_port_terms"] != 1 or not audit["nonzero_Bi"]:
        raise AssertionError("production insertion audit changed unexpectedly")
    return {
        "production_function_called": True,
        "mock_matrix_blocks": matrix.calls,
        "matrix_assembled": matrix.assembled,
        "complex_sign_projection_and_hhat_match": True,
        "target_physics_or_matrix_claimed": False,
    }


def _unit_test_representative_selection() -> dict[str, Any]:
    classes = ["A", "A", "B", "C"]
    ports = ([0], [1], [3], [6])
    cells = [
        SimpleNamespace(
            class_key=classes[index],
            interior_original_dofs=np.arange(4 + index),
            trace_original_dofs=np.arange(3),
        )
        for index in range(4)
    ]
    terms = {
        index: SimpleNamespace(
            Bi=np.zeros((len(cells[index].interior_original_dofs), 1)),
            Di=np.zeros((1, len(cells[index].interior_original_dofs))),
            port_indices=np.asarray(port_ids, dtype=np.int64),
        )
        for index, port_ids in enumerate(ports)
    }
    mode_rows = [
        {"mode_index": index, "side": "top" if index % 2 == 0 else "bottom"}
        for index in range(8)
    ]
    manifest_bytes = json.dumps({"modes": mode_rows}, sort_keys=True).encode()
    carrier = SimpleNamespace(
        entries=[
            SimpleNamespace(mode_identity=row)
            for row in mode_rows
        ],
        mode_manifest_bytes=manifest_bytes,
        mode_manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
    )
    inventory = _carrier_port_side_inventory(carrier)
    if inventory["port_side_indices"] != {
        "top": [0, 2, 4, 6],
        "bottom": [1, 3, 5, 7],
    }:
        raise AssertionError("carrier side indices were not derived in actual order")
    selected, coverage = _select_representative_terms(
        SimpleNamespace(cell_recovery_maps=cells),
        terms,
        inventory,
    )
    if len(selected) > MAX_CELLS or not coverage["coverage_sufficient"]:
        raise AssertionError(f"representative selection failed its coverage gate: {coverage}")
    selected_classes = {
        repr(cells[index].class_key) for index in selected
    }
    selected_sides = {
        side for record in coverage["selected"] for side in record["port_sides"]
    }
    if len(selected_classes) < 2 or selected_sides != {"top", "bottom"}:
        raise AssertionError("selected cells did not cover distinct classes and both ports")
    return {
        "selected_count": len(selected),
        "selected_classes": sorted(selected_classes),
        "selected_sides": sorted(selected_sides),
        "coverage_sufficient": True,
        "carrier_order_was_noncontiguous": True,
        "mode_manifest_sha256": inventory["port_mode_manifest_sha256"],
    }


def _orchestrate(args: argparse.Namespace) -> int:
    bundle = Path(args.bundle).resolve()
    _arrays, manifest = _load_cells(bundle)
    if args.pairs < 3:
        raise ValueError("at least three fresh paired measurements are required")
    affinity = sorted(os.sched_getaffinity(0))
    physical = {
        (
            Path(f"/sys/devices/system/cpu/cpu{cpu}/topology/physical_package_id").read_text().strip(),
            Path(f"/sys/devices/system/cpu/cpu{cpu}/topology/core_id").read_text().strip(),
        )
        for cpu in affinity
    }
    if len(affinity) < 8 or len(physical) < 8:
        raise RuntimeError("bind the comparison to at least eight distinct physical cores")

    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    for name in (
        "OMP_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "MKL_NUM_THREADS",
        "BLIS_NUM_THREADS",
        "VECLIB_MAXIMUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ):
        env[name] = "1"

    measurements: dict[int, list[dict[str, Any]]] = {1: [], 8: []}
    script = Path(__file__).resolve()
    if _sha256(script) != manifest["provenance"]["benchmark_worker_sha256"]:
        raise ValueError("comparison worker SHA differs from frozen run provenance")
    for pair in range(args.pairs):
        order = (1, 8) if pair % 2 == 0 else (8, 1)
        for threads in order:
            prefix = output / f"pair{pair:02d}_threads{threads}"
            command = [
                sys.executable,
                str(script),
                "worker",
                "--bundle",
                str(bundle),
                "--threads",
                str(threads),
                "--warmups",
                str(args.warmups),
                "--iterations",
                str(args.iterations),
                "--output-prefix",
                str(prefix),
            ]
            stdout_path = Path(str(prefix) + ".stdout.txt")
            stderr_path = Path(str(prefix) + ".stderr.txt")
            with stdout_path.open("xb") as stdout_stream, stderr_path.open("xb") as stderr_stream:
                actions = [
                    (os.POSIX_SPAWN_DUP2, stdout_stream.fileno(), 1),
                    (os.POSIX_SPAWN_DUP2, stderr_stream.fileno(), 2),
                    (os.POSIX_SPAWN_CLOSE, stdout_stream.fileno()),
                    (os.POSIX_SPAWN_CLOSE, stderr_stream.fileno()),
                ]
                child_pid = os.posix_spawn(
                    sys.executable,
                    command,
                    env,
                    file_actions=actions,
                )
                while True:
                    try:
                        _waited_pid, wait_status = os.waitpid(child_pid, 0)
                        break
                    except InterruptedError:
                        continue
            child_returncode = os.waitstatus_to_exitcode(wait_status)
            report_path = Path(str(prefix) + ".json")
            if child_returncode != 0 or not report_path.exists():
                raise RuntimeError(
                    f"fresh worker failed (pair={pair}, threads={threads}, "
                    f"returncode={child_returncode}); see {prefix} logs"
                )
            report = json.loads(report_path.read_text())
            if report["bundle_sha256"] != _sha256(bundle):
                raise RuntimeError("worker consumed a different frozen bundle")
            measurements[threads].append(report)

    pair_speedups = []
    error_report: dict[str, Any] = {}
    numeric_ok = True
    for pair in range(args.pairs):
        one = measurements[1][pair]
        eight = measurements[8][pair]
        pair_speedups.append(one["median_wall_seconds"] / eight["median_wall_seconds"])
        one_npz = np.load(output / f"pair{pair:02d}_threads1.npz", allow_pickle=False)
        eight_npz = np.load(output / f"pair{pair:02d}_threads8.npz", allow_pickle=False)
        if set(one_npz.files) != set(eight_npz.files):
            raise ValueError(f"operator output key mismatch in pair {pair}")
        for name in sorted(one_npz.files):
            metrics = _error_metrics(one_npz[name], eight_npz[name])
            error_report[f"pair{pair:02d}/{name}"] = metrics
            if name.endswith("_probe_action"):
                numeric_ok = numeric_ok and not metrics["zero_norm"]
            numeric_ok = numeric_ok and metrics["passed_1e-12"]
        one_npz.close()
        eight_npz.close()

    rss_one = float(np.median([item["peak_rss_bytes"] for item in measurements[1]]))
    rss_eight = float(np.median([item["peak_rss_bytes"] for item in measurements[8]]))
    rss_delta = rss_eight - rss_one
    rss_review_threshold = max(0.10 * rss_one, 128 * 1024**2)
    median_speedup = float(np.median(pair_speedups))
    speed_ok = median_speedup >= 1.10
    rss_review = rss_delta > rss_review_threshold

    def _thread_readback_ok(report: dict[str, Any], requested: int) -> bool:
        before = report.get("thread_count_before", [])
        during = report.get("thread_count_during", [])
        after = report.get("thread_count_after", [])
        return bool(
            report.get("before_was_one")
            and len(before) == 1
            and before[0].get("num_threads") == 1
            and len(during) == 1
            and during[0].get("num_threads") == requested
            and len(after) == 1
            and after[0].get("num_threads") == 1
            and report.get("intentional_exception_restored_one")
            and report.get("error_path_restored_one")
            and report.get("error") is None
        )

    thread_control_ok = all(
        _thread_readback_ok(report, 1) for report in measurements[1]
    ) and all(_thread_readback_ok(report, 8) for report in measurements[8])
    serial_cpu_ok = all(
        isinstance(report.get("cpu_to_wall_ratio"), (int, float))
        and report["cpu_to_wall_ratio"] <= 1.10
        and report.get("native_thread_activity", {}).get(
            "active_worker_thread_count", MAX_CELLS
        )
        == 0
        for report in measurements[1]
    )
    threaded_cpu_ratios = [
        report.get("cpu_to_wall_ratio") for report in measurements[8]
    ]
    threaded_worker_activity = [
        report.get("native_thread_activity", {}).get(
            "active_worker_thread_count", 0
        )
        for report in measurements[8]
    ]
    multi_core_cpu_ok = all(
        isinstance(ratio, (int, float))
        and ratio >= 1.10
        and worker_count >= 1
        for ratio, worker_count in zip(
            threaded_cpu_ratios, threaded_worker_activity, strict=True
        )
    )
    cpu_evidence_ok = serial_cpu_ok and multi_core_cpu_ok
    report = {
        "schema": "cx9z10.port_terms_blas8_comparison.v1",
        "bundle_sha256": _sha256(bundle),
        "manifest_sha256": _sha256(bundle.with_suffix(".json")),
        "source_sha": manifest["source_sha"],
        "target_profile_sha256": manifest["target_profile_sha256"],
        "profile_sha256": manifest["provenance"]["profile_sha256"],
        "resolved_profile_identity": manifest["provenance"][
            "resolved_profile_identity"
        ],
        "resolved_solver_profile_sha256": manifest["provenance"][
            "resolved_solver_profile_sha256"
        ],
        "worker_sha256": manifest["provenance"]["worker_sha256"],
        "launcher_sha256": manifest["provenance"]["launcher_sha256"],
        "input_sha256": manifest["input_sha256"],
        "mesh_sha256": manifest["mesh_sha256"],
        "port_mode_manifest_sha256": manifest["provenance"][
            "port_mode_manifest_sha256"
        ],
        "benchmark_worker_sha256": _sha256(script),
        "selected_cells": manifest["cells"],
        "paired_median_speedups": pair_speedups,
        "median_speedup": median_speedup,
        "speed_gate_1p10": speed_ok,
        "thread_readback_gate": thread_control_ok,
        "serial_cpu_evidence_gate": serial_cpu_ok,
        "multi_core_cpu_evidence_gate": multi_core_cpu_ok,
        "cpu_to_wall_ratios_threads8": threaded_cpu_ratios,
        "active_native_worker_threads_threads8": threaded_worker_activity,
        "cpu_evidence_gate": cpu_evidence_ok,
        "numerical_error_tolerance": ERROR_TOL,
        "numerical_gate": numeric_ok,
        "operator_error_metrics": error_report,
        "median_peak_rss_bytes_threads1": rss_one,
        "median_peak_rss_bytes_threads8": rss_eight,
        "rss_delta_bytes": rss_delta,
        "rss_review_threshold_bytes": rss_review_threshold,
        "rss_exceeds_review_threshold": rss_review,
        "fresh_process_count_per_thread_config": args.pairs,
        "physical_cores_inherited": len(physical),
        "cpu_affinity_inherited": affinity,
        "recommendation": (
            "REVIEW_RSS_DELTA"
            if numeric_ok and speed_ok and thread_control_ok and cpu_evidence_ok and rss_review
            else "RECOMMEND_SCOPED_BLAS8"
            if numeric_ok and speed_ok and thread_control_ok and cpu_evidence_ok
            else "KEEP_SERIAL"
        ),
        "target_authorization_note": "This comparison does not itself launch CX9Z10.",
    }
    _write_once(
        output / "comparison.json",
        (json.dumps(report, sort_keys=True, indent=2) + "\n").encode(),
    )
    print(json.dumps(report, sort_keys=True), flush=True)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    worker = sub.add_parser("worker")
    worker.add_argument("--bundle", required=True)
    worker.add_argument("--threads", type=int, choices=(1, 8), required=True)
    worker.add_argument("--warmups", type=int, default=1)
    worker.add_argument("--iterations", type=int, default=3)
    worker.add_argument("--output-prefix", required=True)
    compare = sub.add_parser("compare")
    compare.add_argument("--bundle", required=True)
    compare.add_argument("--output", required=True)
    compare.add_argument("--pairs", type=int, default=3)
    compare.add_argument("--warmups", type=int, default=1)
    compare.add_argument("--iterations", type=int, default=3)
    sub.add_parser("unit-test-synthetic")
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.command == "worker":
        if args.warmups < 1 or args.iterations < 3:
            raise ValueError("require >=1 warmup and >=3 measured iterations")
        return _worker(args)
    if args.command == "unit-test-synthetic":
        return _unit_test_synthetic()
    return _orchestrate(args)


if __name__ == "__main__":
    raise SystemExit(main())
