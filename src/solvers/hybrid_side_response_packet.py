"""Small owner-row packet I/O contract for the V10-6 response pilot.

The packet is deliberately narrower than the V7 basis packet: it stores only
the fixed pilot response columns, never a global dense array or a solver
object.  Producer and consumer are separate callers; the consumer verifies
the manifest and reads only its target owner rows.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import hashlib
import json
from typing import Any

import numpy as np
from mpi4py import MPI

V10_SIDE_RESPONSE_PACKET_SCHEMA = "task039.v10.h4.exact_side_response_packet.v1"
V10_SIDE_RESPONSE_PACKET_COLUMNS = 16
V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS = 961
V10_SIDE_RESPONSE_PACKET_PRODUCER_LIMIT_GIB = 60.0
V10_SIDE_RESPONSE_PACKET_CONSUMER_LIMIT_GIB = 30.0
V10_SIDE_RESPONSE_PACKET_PAYLOAD_LIMIT_GIB = 16.0
V10_SIDE_RESPONSE_PACKET_EXACT_RESIDUAL_LIMIT = 1.0e-9
V10_SIDE_RESPONSE_PACKET_PROJECTED_WALL_LIMIT_SECONDS = 21600.0
_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")

__all__ = (
    "V10_SIDE_RESPONSE_PACKET_SCHEMA",
    "V10_SIDE_RESPONSE_PACKET_COLUMNS",
    "V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS",
    "V10_SIDE_RESPONSE_PACKET_PRODUCER_LIMIT_GIB",
    "V10_SIDE_RESPONSE_PACKET_CONSUMER_LIMIT_GIB",
    "V10_SIDE_RESPONSE_PACKET_PAYLOAD_LIMIT_GIB",
    "V10_SIDE_RESPONSE_PACKET_EXACT_RESIDUAL_LIMIT",
    "V10_SIDE_RESPONSE_PACKET_PROJECTED_WALL_LIMIT_SECONDS",
    "ExactSideResponsePacket",
    "write_exact_side_response_packet",
    "load_exact_side_response_packet",
    "validate_exact_side_response_reports",
    "projected_response_payload_bytes",
    "projected_response_wall_seconds",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _require_sha256(value: str, field_name: str) -> str:
    value = str(value)
    if len(value) != 64 or any(character not in _HEX_DIGITS for character in value):
        raise ValueError(f"response packet requires a 64-hex {field_name}")
    return value


def _validate_range(ownership_range: tuple[int, int], global_rows: int) -> None:
    first, last = (int(value) for value in ownership_range)
    if not 0 <= first <= last <= int(global_rows):
        raise ValueError("response packet ownership range is outside global rows")


def _validate_column_records(column_records: list[Mapping[str, Any]]) -> None:
    if len(column_records) != V10_SIDE_RESPONSE_PACKET_COLUMNS:
        raise ValueError("V10-6 pilot requires exactly sixteen response columns")
    labels = [str(record.get("label", "")) for record in column_records]
    if any(not label for label in labels) or len(set(labels)) != len(labels):
        raise ValueError("V10-6 response column labels must be unique and non-empty")


def _validate_manifest_coverage(
    shards: list[Mapping[str, Any]], global_rows: int
) -> list[Mapping[str, Any]]:
    ordered = sorted(shards, key=lambda item: int(item["ownership_range"][0]))
    cursor = 0
    for shard in ordered:
        start, end = (int(value) for value in shard["ownership_range"])
        if start != cursor or end <= start:
            raise ValueError("response packet shard coverage has a gap or overlap")
        cursor = end
    if cursor != int(global_rows):
        raise ValueError("response packet shard coverage is incomplete")
    return ordered


class ExactSideResponsePacket:
    """Read-only local response payload with explicit release semantics."""

    def __init__(
        self,
        local_values: np.ndarray,
        manifest: Mapping[str, Any],
        manifest_path: Path,
        diagnostics: Mapping[str, Any],
    ) -> None:
        self._local_values: np.ndarray | None = local_values
        self.manifest = dict(manifest)
        self.manifest_path = manifest_path
        self._diagnostics = dict(diagnostics)
        self._released = False

    @property
    def local_values(self) -> np.ndarray:
        if self._local_values is None:
            raise RuntimeError("response packet has been released")
        return self._local_values

    def column(self, index: int) -> np.ndarray:
        value = self.local_values[:, int(index)]
        value.setflags(write=False)
        return value

    @property
    def diagnostics(self) -> dict[str, Any]:
        result = dict(self._diagnostics)
        result["released"] = bool(self._released)
        result["local_values_retained"] = self._local_values is not None
        return result

    def destroy(self) -> None:
        self._local_values = None
        self._released = True


def projected_response_payload_bytes(
    global_rows: int, column_count: int = V10_SIDE_RESPONSE_PACKET_COLUMNS
) -> int:
    return int(global_rows) * int(column_count) * np.dtype(np.complex128).itemsize


def projected_response_wall_seconds(
    pilot_wall_seconds: float,
    pilot_columns: int = V10_SIDE_RESPONSE_PACKET_COLUMNS,
    projected_columns: int = V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS,
) -> float:
    if not np.isfinite(float(pilot_wall_seconds)) or float(pilot_wall_seconds) < 0:
        raise ValueError("pilot wall time must be finite and non-negative")
    return float(pilot_wall_seconds) * int(projected_columns) / int(pilot_columns)


def write_exact_side_response_packet(
    output_directory: str | Path,
    local_values: np.ndarray,
    *,
    global_rows: int,
    ownership_range: tuple[int, int],
    column_records: list[Mapping[str, Any]],
    source_sha: str,
    input_sha256: str,
    physical_model_sha256: str,
    comm: MPI.Intracomm,
) -> dict[str, Any]:
    """Write one sharded sixteen-column packet and one hash-bound manifest."""

    input_sha256 = _require_sha256(input_sha256, "input_sha256")
    physical_model_sha256 = _require_sha256(
        physical_model_sha256, "physical_model_sha256"
    )
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    _validate_range(ownership_range, global_rows)
    _validate_column_records(column_records)
    first, last = (int(value) for value in ownership_range)
    values = np.asarray(local_values, dtype=np.complex128, order="F")
    if values.shape != (last - first, V10_SIDE_RESPONSE_PACKET_COLUMNS):
        raise ValueError("response packet local shape does not match ownership")
    if not np.all(np.isfinite(values)):
        raise ValueError("response packet contains a non-finite response")
    shard_path = output_directory / f"rank{comm.rank:04d}_response.npy"
    np.save(shard_path, values, allow_pickle=False)
    shard = {
        "rank": int(comm.rank),
        "path": shard_path.name,
        "ownership_range": [first, last],
        "shape": list(values.shape),
        "dtype": str(values.dtype),
        "file_sha256": _sha256_file(shard_path),
    }
    shards = _validate_manifest_coverage(list(comm.allgather(shard)), int(global_rows))
    manifest = {
        "schema": V10_SIDE_RESPONSE_PACKET_SCHEMA,
        "method": "task039_v10_h4_side_response_packet_pilot",
        "global_rows": int(global_rows),
        "column_count": V10_SIDE_RESPONSE_PACKET_COLUMNS,
        "dtype": "complex128",
        "layout": "owner_row_sharded_column_major",
        "columns": [dict(record) for record in column_records],
        "provenance": {
            "source_sha": str(source_sha),
            "input_sha256": str(input_sha256),
            "physical_model_sha256": str(physical_model_sha256),
        },
        "shards": [dict(item) for item in shards],
        "coverage": {"exact": True, "global_range": [0, int(global_rows)]},
        "factor_inventory": {
            "producer_factor_count_ready": 1,
            "producer_factor_count_after_cleanup": "pending_producer_exit",
            "consumer_factor_count_required": 0,
        },
        "projected_full_packet": {
            "column_count": V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS,
            "payload_bytes": projected_response_payload_bytes(
                global_rows, V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS
            ),
        },
    }
    manifest_path = output_directory / "manifest.json"
    manifest_sha256 = None
    if comm.rank == 0:
        manifest_path.write_text(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        manifest_sha256 = _sha256_file(manifest_path)
    manifest_sha256 = comm.bcast(manifest_sha256, root=0)
    comm.barrier()
    return {
        "manifest_path": str(manifest_path),
        "manifest_sha256": str(manifest_sha256),
        "shards": shards,
        "global_rows": int(global_rows),
        "column_count": V10_SIDE_RESPONSE_PACKET_COLUMNS,
        "payload_bytes": projected_response_payload_bytes(global_rows),
        "coverage_exact": True,
        "factor_count_ready": 1,
        "factor_count_after_cleanup": "pending_producer_exit",
    }


def load_exact_side_response_packet(
    manifest_path: str | Path,
    *,
    expected_manifest_sha256: str,
    expected_provenance: Mapping[str, Any],
    global_rows: int,
    ownership_range: tuple[int, int],
    comm: MPI.Intracomm,
) -> ExactSideResponsePacket:
    """Validate and load only the target owner rows of a response packet."""

    expected_input_sha256 = _require_sha256(
        expected_provenance.get("input_sha256"), "input_sha256"
    )
    expected_physical_model_sha256 = _require_sha256(
        expected_provenance.get("physical_model_sha256"),
        "physical_model_sha256",
    )
    manifest_path = Path(manifest_path)
    if _sha256_file(manifest_path) != str(expected_manifest_sha256):
        raise ValueError("response packet manifest hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != V10_SIDE_RESPONSE_PACKET_SCHEMA:
        raise ValueError("response packet schema mismatch")
    if int(manifest.get("global_rows", -1)) != int(global_rows):
        raise ValueError("response packet global row size mismatch")
    if int(manifest.get("column_count", -1)) != V10_SIDE_RESPONSE_PACKET_COLUMNS:
        raise ValueError("response packet column count mismatch")
    expected_provenance = {
        **dict(expected_provenance),
        "input_sha256": expected_input_sha256,
        "physical_model_sha256": expected_physical_model_sha256,
    }
    if dict(manifest.get("provenance", {})) != dict(expected_provenance):
        raise ValueError("response packet provenance mismatch")
    _validate_column_records(list(manifest.get("columns", ())))
    shards = _validate_manifest_coverage(
        list(manifest.get("shards", ())), int(global_rows)
    )
    _validate_range(ownership_range, global_rows)
    first, last = (int(value) for value in ownership_range)
    root = manifest_path.parent
    source_ranges: list[list[int]] = []
    exact_source: Mapping[str, Any] | None = None
    for shard in shards:
        start, end = (int(value) for value in shard["ownership_range"])
        if start == first and end == last:
            exact_source = shard
        if start < last and end > first:
            source_ranges.append([start, end])
    if not source_ranges and first != last:
        raise ValueError("response packet has no shard overlapping target owner rows")
    if exact_source is not None:
        source_path = root / str(exact_source["path"])
        values = np.load(source_path, mmap_mode="r", allow_pickle=False)
        ownership_mode = "producer_owner_rows_mmap"
        owned_local_copy_count = 0
        if tuple(values.shape) != (last - first, V10_SIDE_RESPONSE_PACKET_COLUMNS):
            raise ValueError("response packet exact shard shape mismatch")
        if str(values.dtype) != "complex128":
            raise ValueError("response packet exact shard dtype mismatch")
        if _sha256_file(source_path) != exact_source.get("file_sha256"):
            raise ValueError("response packet exact shard hash mismatch")
        values.setflags(write=False)
    else:
        values = np.empty(
            (last - first, V10_SIDE_RESPONSE_PACKET_COLUMNS),
            dtype=np.complex128,
            order="F",
        )
        for shard in shards:
            source_start, source_end = (
                int(value) for value in shard["ownership_range"]
            )
            overlap_start = max(first, source_start)
            overlap_end = min(last, source_end)
            if overlap_start >= overlap_end:
                continue
            source_path = root / str(shard["path"])
            source = np.load(source_path, mmap_mode="r", allow_pickle=False)
            if (
                tuple(source.shape)
                != (
                    source_end - source_start,
                    V10_SIDE_RESPONSE_PACKET_COLUMNS,
                )
                or str(source.dtype) != "complex128"
            ):
                raise ValueError("response packet source shard shape/dtype mismatch")
            if _sha256_file(source_path) != shard.get("file_sha256"):
                raise ValueError("response packet source shard hash mismatch")
            values[overlap_start - first : overlap_end - first] = source[
                overlap_start - source_start : overlap_end - source_start
            ]
        values.setflags(write=False)
        ownership_mode = "remapped_owner_rows"
        owned_local_copy_count = 1
    diagnostics = {
        "ownership_mode": ownership_mode,
        "producer_ownership_ranges": [
            list(map(int, shard["ownership_range"])) for shard in shards
        ],
        "target_ownership_range": [first, last],
        "owner_row_coverage_exact": True,
        "owned_local_basis_copy_count": owned_local_copy_count,
        "global_basis_materialized": False,
        "consumer_factor_count": 0,
        "source_shard_hash_verified_local": True,
        "source_shard_hash_verification_scope": "target_overlap_shards_on_this_rank",
        "manifest_sha256": str(expected_manifest_sha256),
        "comm_size": int(comm.size),
    }
    return ExactSideResponsePacket(values, manifest, manifest_path, diagnostics)


def validate_exact_side_response_reports(
    reports: list[Mapping[str, Any]],
    *,
    residual_limit: float = V10_SIDE_RESPONSE_PACKET_EXACT_RESIDUAL_LIMIT,
) -> dict[str, Any]:
    """Recompute the pilot's per-column finite/residual Gate."""

    labels = [str(report.get("label", "")) for report in reports]
    complete = len(reports) == V10_SIDE_RESPONSE_PACKET_COLUMNS
    unique = len(labels) == len(set(labels)) and all(labels)
    finite = all(bool(report.get("finite")) for report in reports)
    residuals = [report.get("true_residual_relative") for report in reports]
    residuals_finite = all(
        isinstance(value, (int, float)) and np.isfinite(float(value))
        for value in residuals
    )
    residual_pass = residuals_finite and all(
        float(value) <= float(residual_limit) for value in residuals
    )
    wall_finite = all(
        isinstance(report.get("wall_seconds"), (int, float))
        and np.isfinite(float(report["wall_seconds"]))
        for report in reports
    )
    return {
        "complete": bool(complete and unique),
        "finite": bool(finite),
        "residual_pass": bool(residual_pass),
        "wall_finite": bool(wall_finite),
        "pass": bool(complete and unique and finite and residual_pass and wall_finite),
        "worst_true_residual_relative": (
            max((float(value) for value in residuals), default=None)
            if residuals_finite
            else None
        ),
        "residual_limit": float(residual_limit),
    }
