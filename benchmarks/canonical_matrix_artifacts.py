"""Streaming owner-sharded canonical matrix artifacts.

Only one coefficient column is materialized at a time while writing.  The
numeric artifact is an ``open_memmap`` NPY shard; canonical keys remain a
small metadata index for offline comparison.  MPI communication is limited
to descriptor dictionaries and the root manifest.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

import numpy as np

from benchmarks.canonical_vector_artifacts import (
    KEY_DIGEST_ALGORITHM,
    canonical_key_json_bytes,
)


MATRIX_SHARD_SCHEMA = "task038.canonical-matrix-shard.v1"
MATRIX_MANIFEST_SCHEMA = "task038.canonical-matrix-manifest.v1"
MATRIX_PREFIXES = (16, 32, 48, 64)
DEFAULT_RELATIVE_TOLERANCE = 1.0e-12
_CHUNK_ROWS = 4096


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _finite_value(value: Any) -> complex:
    coefficient = complex(value)
    if not math.isfinite(coefficient.real) or not math.isfinite(coefficient.imag):
        raise ValueError("canonical matrix coefficient is non-finite")
    return coefficient


def _column_source(
    columns: Iterable[Iterable[tuple[tuple[Any, ...], complex]]]
    | Callable[[int], Iterable[tuple[tuple[Any, ...], complex]]],
    column: int,
    iterator: Any,
) -> Iterable[tuple[tuple[Any, ...], complex]]:
    if callable(columns):
        return columns(column)
    return next(iterator)


def _consume_first_column(
    packets: Iterable[tuple[tuple[Any, ...], complex]],
) -> tuple[tuple[bytes, ...], np.ndarray]:
    keys: list[bytes] = []
    values: list[complex] = []
    seen: set[bytes] = set()
    duplicate_count = 0
    for key, value in packets:
        key_bytes = canonical_key_json_bytes(key)
        if key_bytes in seen:
            duplicate_count += 1
        seen.add(key_bytes)
        keys.append(key_bytes)
        values.append(_finite_value(value))
    if duplicate_count:
        raise ValueError(
            "canonical matrix first column duplicate count "
            f"is {duplicate_count}, limit=0"
        )
    return tuple(keys), np.asarray(values, dtype=np.complex128)


def _consume_next_column(
    packets: Iterable[tuple[tuple[Any, ...], complex]],
    expected_keys: tuple[bytes, ...],
    column: int,
) -> np.ndarray:
    values = np.empty(len(expected_keys), dtype=np.complex128)
    seen: set[bytes] = set()
    row = 0
    duplicate_count = 0
    for key, value in packets:
        key_bytes = canonical_key_json_bytes(key)
        if key_bytes in seen:
            duplicate_count += 1
        seen.add(key_bytes)
        if row >= len(expected_keys) or key_bytes != expected_keys[row]:
            raise ValueError(
                f"canonical matrix column {column} key order differs at row {row}"
            )
        values[row] = _finite_value(value)
        row += 1
    if duplicate_count:
        raise ValueError(
            f"canonical matrix column {column} duplicate count "
            f"is {duplicate_count}, limit=0"
        )
    if row != len(expected_keys):
        raise ValueError(
            f"canonical matrix column {column} packet count is {row}, "
            f"expected={len(expected_keys)}"
        )
    return values


def _read_key_lines(path: Path, expected_count: int) -> tuple[tuple[bytes, ...], int]:
    lines = path.read_bytes().splitlines()
    if len(lines) != int(expected_count):
        raise ValueError(
            f"canonical matrix key count is {len(lines)}, expected={expected_count}"
        )
    keys: list[bytes] = []
    seen: set[bytes] = set()
    duplicate_count = 0
    for line in lines:
        if not line:
            raise ValueError("canonical matrix key file contains an empty line")
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError("canonical matrix key JSON is invalid") from exc
        if (
            not isinstance(payload, dict)
            or set(payload) != {"tuple"}
            or not isinstance(payload["tuple"], list)
        ):
            raise ValueError("canonical matrix key tuple encoding is invalid")
        canonical = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        if canonical != line:
            raise ValueError("canonical matrix key bytes are not canonical")
        if line in seen:
            duplicate_count += 1
        seen.add(line)
        keys.append(line)
    return tuple(keys), duplicate_count


def _validate_manifest_header(manifest: Mapping[str, Any]) -> tuple[int, int]:
    if manifest.get("schema_version") != MATRIX_MANIFEST_SCHEMA:
        raise ValueError("canonical matrix manifest schema is unsupported")
    if manifest.get("dtype") != "complex128":
        raise ValueError("canonical matrix manifest dtype is not complex128")
    if manifest.get("key_digest_algorithm") != KEY_DIGEST_ALGORITHM:
        raise ValueError("canonical matrix key digest algorithm is unsupported")
    role = manifest.get("role")
    if not isinstance(role, str) or not role:
        raise ValueError("canonical matrix manifest role is missing")
    mpi_size = manifest.get("mpi_size")
    column_count = manifest.get("column_count")
    if (
        isinstance(mpi_size, bool)
        or not isinstance(mpi_size, int)
        or mpi_size < 1
    ):
        raise ValueError("canonical matrix manifest mpi_size is invalid")
    if (
        isinstance(column_count, bool)
        or not isinstance(column_count, int)
        or not 1 <= column_count <= 64
    ):
        raise ValueError("canonical matrix manifest column_count is invalid")
    if not isinstance(manifest.get("extractor_audit"), dict):
        raise ValueError("canonical matrix extractor audit is missing")
    shards = manifest.get("per_rank_shards")
    if not isinstance(shards, list) or len(shards) != mpi_size:
        raise ValueError("canonical matrix shard descriptor count is invalid")
    return mpi_size, column_count


def _open_matrix_index(manifest_path: Path) -> dict[str, Any]:
    try:
        manifest = json.loads(manifest_path.read_bytes())
    except json.JSONDecodeError as exc:
        raise ValueError("canonical matrix manifest JSON is invalid") from exc
    if not isinstance(manifest, dict):
        raise ValueError("canonical matrix manifest must be an object")
    mpi_size, column_count = _validate_manifest_header(manifest)
    descriptors = manifest["per_rank_shards"]
    base = manifest_path.parent
    ranks: set[int] = set()
    states: list[dict[str, Any]] = []
    index: dict[bytes, tuple[int, int]] = {}
    packet_count = 0
    duplicate_count = 0
    for shard_index, descriptor in enumerate(descriptors):
        if not isinstance(descriptor, dict):
            raise ValueError("canonical matrix shard descriptor is invalid")
        rank = descriptor.get("rank")
        if isinstance(rank, bool) or not isinstance(rank, int) or rank in ranks:
            raise ValueError("canonical matrix shard rank is invalid")
        if rank < 0 or rank >= mpi_size:
            raise ValueError("canonical matrix shard rank is outside mpi_size")
        ranks.add(rank)
        count = descriptor.get("local_packet_count")
        shape = descriptor.get("value_shape")
        if (
            descriptor.get("schema_version") != MATRIX_SHARD_SCHEMA
            or descriptor.get("key_shape") != [count]
            or descriptor.get("key_dtype") != "canonical-key-json-v1"
            or descriptor.get("key_digest_algorithm") != KEY_DIGEST_ALGORITHM
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 0
            or shape != [count, column_count]
            or descriptor.get("value_dtype") != "complex128"
        ):
            raise ValueError("canonical matrix shard shape or dtype is invalid")
        key_name = descriptor.get("key_filename")
        value_name = descriptor.get("value_filename")
        if not isinstance(key_name, str) or not isinstance(value_name, str):
            raise ValueError("canonical matrix shard filenames are missing")
        key_path = base / key_name
        value_path = base / value_name
        if not key_path.is_file() or not value_path.is_file():
            raise ValueError("canonical matrix shard file is missing")
        if descriptor.get("key_file_bytes") != key_path.stat().st_size:
            raise ValueError("canonical matrix key byte count does not match")
        if descriptor.get("value_file_bytes") != value_path.stat().st_size:
            raise ValueError("canonical matrix value byte count does not match")
        if descriptor.get("key_file_sha256") != _sha256(key_path):
            raise ValueError("canonical matrix key SHA256 does not match")
        if descriptor.get("value_file_sha256") != _sha256(value_path):
            raise ValueError("canonical matrix value SHA256 does not match")
        keys, local_duplicates = _read_key_lines(key_path, count)
        if local_duplicates != descriptor.get("local_duplicate_count", 0):
            raise ValueError("canonical matrix local duplicate count does not match")
        if local_duplicates:
            duplicate_count += local_duplicates
        try:
            values = np.load(value_path, mmap_mode="r", allow_pickle=False)
        except (OSError, ValueError) as exc:
            raise ValueError("canonical matrix NPY value file is invalid") from exc
        if values.shape != (count, column_count) or values.dtype != np.complex128:
            raise ValueError("canonical matrix NPY shape or dtype does not match")
        for start in range(0, count, _CHUNK_ROWS):
            if not np.all(np.isfinite(values[start : start + _CHUNK_ROWS])):
                raise ValueError("canonical matrix values contain non-finite data")
        states.append({"keys": keys, "values": values, "path": value_path})
        for row, key_bytes in enumerate(keys):
            if key_bytes in index:
                duplicate_count += 1
                raise ValueError("canonical matrix has duplicate keys across shards")
            index[key_bytes] = (shard_index, row)
        packet_count += count
    if ranks != set(range(mpi_size)):
        raise ValueError("canonical matrix shard ranks are incomplete")
    if manifest.get("global_packet_count") != packet_count:
        raise ValueError("canonical matrix global packet count does not match")
    if manifest.get("global_duplicate_count") != duplicate_count:
        raise ValueError("canonical matrix global duplicate count does not match")
    if duplicate_count:
        raise ValueError("canonical matrix duplicate count is nonzero")
    return {
        "manifest": manifest,
        "column_count": column_count,
        "states": states,
        "index": index,
    }


def write_canonical_matrix_shard(
    root: Path,
    *,
    role: str,
    column_count: int,
    columns: Iterable[Iterable[tuple[tuple[Any, ...], complex]]]
    | Callable[[int], Iterable[tuple[tuple[Any, ...], complex]]],
    extractor_audit: Mapping[str, Any],
    comm: Any | None = None,
    manifest_name: str = "matrix.manifest.json",
) -> dict[str, Any]:
    """Write one owner-local matrix shard and a root-only descriptor manifest."""

    if not isinstance(role, str) or not role:
        raise ValueError("canonical matrix role is required")
    if isinstance(column_count, bool) or not 1 <= int(column_count) <= 64:
        raise ValueError("canonical matrix column_count must be in 1..64")
    if not isinstance(extractor_audit, Mapping):
        raise ValueError("canonical matrix extractor audit is required")
    if comm is None:
        from mpi4py import MPI

        comm = MPI.COMM_WORLD
    column_count = int(column_count)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    rank = int(comm.rank)
    mpi_size = int(comm.size)
    iterator = None if callable(columns) else iter(columns)
    descriptor: dict[str, Any] | None = None
    local_error: str | None = None
    key_path = root / f"rank_{rank:04d}.keys.jsonl"
    value_path = root / f"rank_{rank:04d}.values.npy"
    try:
        if key_path.exists() or value_path.exists():
            raise FileExistsError("canonical matrix shard path already exists")
        first = _column_source(columns, 0, iterator)
        keys, first_values = _consume_first_column(first)
        with key_path.open("xb") as stream:
            for key_bytes in keys:
                stream.write(key_bytes + b"\n")
        values = np.lib.format.open_memmap(
            value_path,
            mode="w+",
            dtype=np.complex128,
            shape=(len(keys), column_count),
        )
        try:
            values[:, 0] = first_values
            for column in range(1, column_count):
                current = _column_source(columns, column, iterator)
                values[:, column] = _consume_next_column(current, keys, column)
            values.flush()
        finally:
            values.flush()
            del values
        descriptor = {
            "schema_version": MATRIX_SHARD_SCHEMA,
            "rank": rank,
            "key_filename": key_path.name,
            "value_filename": value_path.name,
            "key_file_bytes": int(key_path.stat().st_size),
            "value_file_bytes": int(value_path.stat().st_size),
            "key_file_sha256": _sha256(key_path),
            "value_file_sha256": _sha256(value_path),
            "key_digest_algorithm": KEY_DIGEST_ALGORITHM,
            "local_packet_count": int(len(keys)),
            "local_duplicate_count": 0,
            "key_shape": [int(len(keys))],
            "key_dtype": "canonical-key-json-v1",
            "value_shape": [int(len(keys)), column_count],
            "value_dtype": "complex128",
        }
    except (OSError, TypeError, ValueError) as exc:
        local_error = f"rank {rank}: {type(exc).__name__}: {exc}"

    gathered = comm.gather(
        {"descriptor": descriptor, "error": local_error},
        root=0,
    )
    failure: str | None = None
    manifest: dict[str, Any] | None = None
    manifest_sha256: str | None = None
    manifest_path = root / manifest_name
    if rank == 0:
        errors = [item["error"] for item in gathered if item["error"]]
        if errors:
            failure = "; ".join(errors)
        else:
            descriptors = sorted(
                (item["descriptor"] for item in gathered),
                key=lambda item: int(item["rank"]),
            )
            manifest = {
                "schema_version": MATRIX_MANIFEST_SCHEMA,
                "role": role,
                "mpi_size": mpi_size,
                "column_count": column_count,
                "dtype": "complex128",
                "key_digest_algorithm": KEY_DIGEST_ALGORITHM,
                "global_packet_count": int(
                    sum(item["local_packet_count"] for item in descriptors)
                ),
                "global_duplicate_count": int(
                    sum(item["local_duplicate_count"] for item in descriptors)
                ),
                "per_rank_shards": descriptors,
                "extractor_audit": dict(extractor_audit),
            }
            try:
                payload = (
                    json.dumps(
                        manifest,
                        ensure_ascii=False,
                        sort_keys=True,
                        indent=2,
                    ).encode("utf-8")
                    + b"\n"
                )
                with manifest_path.open("xb") as stream:
                    stream.write(payload)
                manifest_sha256 = hashlib.sha256(payload).hexdigest()
            except (OSError, TypeError, ValueError) as exc:
                failure = f"manifest: {type(exc).__name__}: {exc}"
    failure = comm.bcast(failure, root=0)
    if failure is not None:
        raise RuntimeError(failure)
    return {
        "manifest_path": manifest_path,
        "manifest_sha256": manifest_sha256,
        "manifest": manifest,
        "rank_descriptor": descriptor,
    }


def read_canonical_matrix_manifest(path: Path) -> dict[str, Any]:
    """Validate a matrix manifest and all mmap-backed shard contents."""

    state = _open_matrix_index(Path(path))
    manifest = state["manifest"]
    del state
    return manifest


def _comparison_failure(message: str) -> dict[str, Any]:
    return {
        "passed": False,
        "errors": [message],
        "missing_count": 0,
        "extra_count": 0,
        "duplicate_count": 0,
        "prefixes": {},
    }


def compare_canonical_matrices(
    left_path: Path,
    right_path: Path,
    *,
    relative_tolerance: float = DEFAULT_RELATIVE_TOLERANCE,
    prefixes: Iterable[int] | None = None,
    chunk_rows: int = _CHUNK_ROWS,
) -> dict[str, Any]:
    """Compare canonical matrix coefficients without loading full matrices."""

    try:
        tolerance = float(relative_tolerance)
        if not np.isfinite(tolerance) or tolerance < 0.0:
            raise ValueError("matrix relative tolerance is invalid")
        left = _open_matrix_index(Path(left_path))
        right = _open_matrix_index(Path(right_path))
        left_manifest = left["manifest"]
        right_manifest = right["manifest"]
        if left_manifest["role"] != right_manifest["role"]:
            raise ValueError("canonical matrix roles differ")
        column_count = int(left["column_count"])
        if column_count != int(right["column_count"]):
            raise ValueError("canonical matrix column counts differ")
        if prefixes is None:
            selected = tuple(p for p in MATRIX_PREFIXES if p <= column_count)
        else:
            selected = tuple(int(p) for p in prefixes)
        if selected != tuple(sorted(set(selected))) or any(
            p < 1 or p > column_count for p in selected
        ):
            raise ValueError("canonical matrix prefixes are invalid")
        left_keys = set(left["index"])
        right_keys = set(right["index"])
        missing = right_keys - left_keys
        extra = left_keys - right_keys
        if missing or extra:
            return {
                "passed": False,
                "errors": ["canonical matrix key sets differ"],
                "key_set_exact": False,
                "missing_count": len(missing),
                "extra_count": len(extra),
                "duplicate_count": 0,
                "prefixes": {},
            }
        common_keys = tuple(sorted(left_keys))
        if chunk_rows < 1:
            raise ValueError("matrix chunk_rows must be positive")
        diff_sq = {prefix: 0.0 for prefix in selected}
        reference_sq = {prefix: 0.0 for prefix in selected}
        max_abs = {prefix: 0.0 for prefix in selected}
        for start in range(0, len(common_keys), int(chunk_rows)):
            chunk_keys = common_keys[start : start + int(chunk_rows)]
            left_values = np.empty(
                (len(chunk_keys), column_count), dtype=np.complex128
            )
            right_values = np.empty_like(left_values)
            for row, key_bytes in enumerate(chunk_keys):
                left_shard, left_row = left["index"][key_bytes]
                right_shard, right_row = right["index"][key_bytes]
                left_values[row, :] = left["states"][left_shard]["values"][
                    left_row, :
                ]
                right_values[row, :] = right["states"][right_shard]["values"][
                    right_row, :
                ]
            for prefix in selected:
                difference = left_values[:, :prefix] - right_values[:, :prefix]
                diff_sq[prefix] += float(np.vdot(difference, difference).real)
                reference_sq[prefix] += float(
                    np.vdot(right_values[:, :prefix], right_values[:, :prefix]).real
                )
                if difference.size:
                    max_abs[prefix] = max(
                        max_abs[prefix], float(np.max(np.abs(difference)))
                    )
        prefix_results: dict[str, Any] = {}
        passed = True
        for prefix in selected:
            relative = float(
                np.sqrt(diff_sq[prefix])
                / max(np.sqrt(reference_sq[prefix]), np.finfo(float).tiny)
            )
            prefix_passed = bool(np.isfinite(relative) and relative <= tolerance)
            prefix_results[str(prefix)] = {
                "relative_l2": relative,
                "max_abs": max_abs[prefix],
                "limit": tolerance,
                "passed": prefix_passed,
            }
            passed = passed and prefix_passed
        return {
            "passed": bool(passed),
            "errors": [],
            "key_set_exact": True,
            "missing_count": 0,
            "extra_count": 0,
            "duplicate_count": 0,
            "left_packet_count": len(left_keys),
            "right_packet_count": len(right_keys),
            "left_mpi_size": left_manifest["mpi_size"],
            "right_mpi_size": right_manifest["mpi_size"],
            "prefixes": prefix_results,
            "relative_tolerance": tolerance,
            "comparison": "chunked_mmap_by_canonical_key",
        }
    except (OSError, TypeError, ValueError, KeyError) as exc:
        return _comparison_failure(str(exc))


__all__ = [
    "DEFAULT_RELATIVE_TOLERANCE",
    "MATRIX_MANIFEST_SCHEMA",
    "MATRIX_PREFIXES",
    "MATRIX_SHARD_SCHEMA",
    "compare_canonical_matrices",
    "read_canonical_matrix_manifest",
    "write_canonical_matrix_shard",
]
