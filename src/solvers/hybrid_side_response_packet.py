"""Small owner-row packet I/O contract for the V10-6 response pilot.

The packet is deliberately narrower than the V7 basis packet: it stores only
the fixed pilot response columns, never a global dense array or a solver
object.  Producer and consumer are separate callers; the consumer verifies
the manifest and reads only its target owner rows.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
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
V10_SIDE_RESPONSE_PACKET_FULL_SCHEMA = (
    "task039.v10.h4.exact_side_response_packet.full.v1"
)
V10_SIDE_RESPONSE_PACKET_COMPRESSION_SCHEMA = (
    "task039.v10.h4.exact_side_response_packet.compression.v1"
)
V10_SIDE_RESPONSE_PACKET_FULL_METHOD = (
    "task039_v10_h4_side_response_packet_full_producer"
)
V10_SIDE_RESPONSE_PACKET_COMPRESSION_METHOD = (
    "task039_v10_h4_side_response_packet_compression"
)
V10_SIDE_RESPONSE_PACKET_FULL_HOLDOUT_COLUMNS = (
    0,
    1,
    240,
    267,
    479,
    480,
    481,
    720,
    746,
    959,
)
V11_BOTTOM_RESPONSE_SAMPLE_INDICES = (
    0,
    1,
    240,
    267,
    479,
    480,
    481,
    720,
    746,
    959,
)
V11_BOTTOM_FIELD_RESPONSE_SIGN = -1.0
V11_BOTTOM_SCHUR_CONTRIBUTION_SIGN = 1.0
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
    "V10_SIDE_RESPONSE_PACKET_FULL_SCHEMA",
    "V10_SIDE_RESPONSE_PACKET_COMPRESSION_SCHEMA",
    "V10_SIDE_RESPONSE_PACKET_FULL_METHOD",
    "V10_SIDE_RESPONSE_PACKET_COMPRESSION_METHOD",
    "V10_SIDE_RESPONSE_PACKET_FULL_HOLDOUT_COLUMNS",
    "V11_BOTTOM_RESPONSE_SAMPLE_INDICES",
    "V11_BOTTOM_FIELD_RESPONSE_SIGN",
    "V11_BOTTOM_SCHUR_CONTRIBUTION_SIGN",
    "ExactSideResponsePacket",
    "write_exact_side_response_packet",
    "load_exact_side_response_packet",
    "validate_exact_side_response_reports",
    "projected_response_payload_bytes",
    "projected_response_wall_seconds",
    "OwnerRowResponsePacketWriter",
    "load_full_side_response_packet",
    "compress_owner_row_response_packet",
    "audit_bottom_response_packet_algebra",
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


class OwnerRowResponsePacketWriter:
    """Stream one owner-row response column into a rank-local NPY memmap."""

    def __init__(
        self,
        output_directory: str | Path,
        *,
        global_rows: int,
        ownership_range: tuple[int, int],
        column_records: list[Mapping[str, Any]],
        source_sha: str,
        input_sha256: str,
        physical_model_sha256: str,
        comm: MPI.Intracomm,
        schema: str = V10_SIDE_RESPONSE_PACKET_FULL_SCHEMA,
        method: str = V10_SIDE_RESPONSE_PACKET_FULL_METHOD,
        zero_column_index: int = 960,
        training_column_indices: tuple[int, ...] | None = None,
        holdout_column_indices: tuple[int, ...] = (
            V10_SIDE_RESPONSE_PACKET_FULL_HOLDOUT_COLUMNS
        ),
        identity: Mapping[str, Any] | None = None,
    ) -> None:
        self.output_directory = Path(output_directory)
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self.global_rows = int(global_rows)
        self.ownership_range = tuple(int(value) for value in ownership_range)
        _validate_range(self.ownership_range, self.global_rows)
        self.column_records = [dict(record) for record in column_records]
        self.column_count = len(self.column_records)
        if self.column_count <= 0:
            raise ValueError("full response packet requires response columns")
        labels = [str(record.get("label", "")) for record in self.column_records]
        if any(not label for label in labels) or len(set(labels)) != len(labels):
            raise ValueError("full response packet labels must be unique")
        self.source_sha = str(source_sha)
        self.input_sha256 = _require_sha256(input_sha256, "input_sha256")
        self.physical_model_sha256 = _require_sha256(
            physical_model_sha256, "physical_model_sha256"
        )
        self.comm = comm
        self.schema = str(schema)
        self.method = str(method)
        self.zero_column_index = int(zero_column_index)
        self.holdout_column_indices = tuple(
            int(value) for value in holdout_column_indices
        )
        if training_column_indices is None:
            holdout = set(self.holdout_column_indices)
            training_column_indices = tuple(
                index
                for index in range(self.column_count)
                if index not in holdout and index != self.zero_column_index
            )
        self.training_column_indices = tuple(
            int(value) for value in training_column_indices
        )
        if self.zero_column_index not in range(self.column_count):
            raise ValueError("zero response column is outside the packet")
        if set(self.training_column_indices) & {
            *self.holdout_column_indices,
            self.zero_column_index,
        }:
            raise ValueError("training response columns overlap excluded columns")
        if any(
            index < 0 or index >= self.column_count
            for index in (*self.training_column_indices, *self.holdout_column_indices)
        ):
            raise ValueError("response column index is outside the packet")
        if self.column_count == V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS:
            expected_holdout = V10_SIDE_RESPONSE_PACKET_FULL_HOLDOUT_COLUMNS
            expected_training = tuple(
                index for index in range(960) if index not in expected_holdout
            )
            if (
                self.zero_column_index != 960
                or self.holdout_column_indices != expected_holdout
                or self.training_column_indices != expected_training
                or (
                    set(self.training_column_indices) | set(self.holdout_column_indices)
                )
                != set(range(960))
            ):
                raise ValueError(
                    "full response packet train/holdout/zero partition is not frozen"
                )
        self.identity = dict(identity or {})
        first, last = self.ownership_range
        self.shard_path = self.output_directory / f"rank{comm.rank:04d}_response.npy"
        self._values = np.lib.format.open_memmap(
            self.shard_path,
            mode="w+",
            dtype=np.complex128,
            shape=(last - first, self.column_count),
            fortran_order=True,
        )
        self._written: set[int] = set()
        self._finalized = False
        self._closed = False

    def write_column(self, column_index: int, local_values: np.ndarray) -> None:
        if self._finalized or self._closed:
            raise RuntimeError("response packet writer has been finalized")
        column_index = int(column_index)
        first, last = self.ownership_range
        values = np.asarray(local_values, dtype=np.complex128).reshape(-1)
        if not 0 <= column_index < self.column_count:
            raise ValueError("response column index is outside the packet")
        if values.shape != (last - first,):
            raise ValueError("response column does not match owner-row shape")
        if not np.all(np.isfinite(values)):
            raise ValueError("response packet contains a non-finite response")
        self._values[:, column_index] = values
        self._written.add(column_index)

    def close(self) -> None:
        """Release the current mmap; repeated calls are harmless."""

        if self._closed:
            return
        values = getattr(self, "_values", None)
        if values is not None:
            values.flush()
            del self._values
        self._closed = True

    def finalize(
        self,
        *,
        producer_factor_count_after_cleanup: int | str = "pending_producer_exit",
    ) -> dict[str, Any]:
        if self._finalized:
            raise RuntimeError("response packet writer has already been finalized")
        if self._written != set(range(self.column_count)):
            raise ValueError("response packet has unwritten columns")
        self.close()
        self._finalized = True
        first, last = self.ownership_range
        shard = {
            "rank": int(self.comm.rank),
            "path": self.shard_path.name,
            "ownership_range": [first, last],
            "shape": [last - first, self.column_count],
            "dtype": "complex128",
            "order": "F",
            "file_sha256": _sha256_file(self.shard_path),
        }
        shards = _validate_manifest_coverage(
            list(self.comm.allgather(shard)), self.global_rows
        )
        manifest = {
            "schema": self.schema,
            "method": self.method,
            "global_rows": self.global_rows,
            "column_count": self.column_count,
            "dtype": "complex128",
            "layout": "owner_row_sharded_column_major",
            "columns": [dict(record) for record in self.column_records],
            "training_column_indices": list(self.training_column_indices),
            "holdout_column_indices": list(self.holdout_column_indices),
            "training_column_count": len(self.training_column_indices),
            "holdout_column_count": len(self.holdout_column_indices),
            "zero_column_index": self.zero_column_index,
            "provenance": {
                "source_sha": self.source_sha,
                "input_sha256": self.input_sha256,
                "physical_model_sha256": self.physical_model_sha256,
                **self.identity,
            },
            "shards": [dict(item) for item in shards],
            "coverage": {"exact": True, "global_range": [0, self.global_rows]},
            "factor_inventory": {
                "producer_factor_count_ready": 1,
                "producer_factor_count_after_cleanup": producer_factor_count_after_cleanup,
                "consumer_factor_count_required": 0,
                "global_direct_factor_count": 0,
                "nested_ksp_count": 0,
            },
        }
        manifest_path = self.output_directory / "manifest.json"
        manifest_sha256 = None
        if self.comm.rank == 0:
            manifest_path.write_text(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )
            manifest_sha256 = _sha256_file(manifest_path)
        manifest_sha256 = self.comm.bcast(manifest_sha256, root=0)
        self.comm.barrier()
        return {
            "manifest_path": str(manifest_path),
            "manifest_sha256": str(manifest_sha256),
            "global_rows": self.global_rows,
            "column_count": self.column_count,
            "shards": shards,
            "coverage_exact": True,
            "factor_count_ready": 1,
            "factor_count_after_cleanup": producer_factor_count_after_cleanup,
        }


def load_full_side_response_packet(
    manifest_path: str | Path,
    *,
    expected_manifest_sha256: str,
    expected_provenance: Mapping[str, Any],
    global_rows: int,
    ownership_range: tuple[int, int],
    comm: MPI.Intracomm,
) -> ExactSideResponsePacket:
    """Load a full response packet without materializing global rows."""

    manifest_path = Path(manifest_path)
    if _sha256_file(manifest_path) != str(expected_manifest_sha256):
        raise ValueError("full response packet manifest hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema") != V10_SIDE_RESPONSE_PACKET_FULL_SCHEMA:
        raise ValueError("full response packet schema mismatch")
    if int(manifest.get("global_rows", -1)) != int(global_rows):
        raise ValueError("full response packet global row size mismatch")
    expected_columns = int(manifest.get("column_count", -1))
    if expected_columns != V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS:
        raise ValueError("full response packet column count mismatch")
    expected = dict(expected_provenance)
    for field in ("input_sha256", "physical_model_sha256"):
        expected[field] = _require_sha256(expected.get(field), field)
    if dict(manifest.get("provenance", {})) != expected:
        raise ValueError("full response packet provenance mismatch")
    columns = list(manifest.get("columns", ()))
    if len(columns) != expected_columns:
        raise ValueError("full response packet column records are incomplete")
    shards = _validate_manifest_coverage(
        list(manifest.get("shards", ())), int(global_rows)
    )
    _validate_range(ownership_range, global_rows)
    first, last = (int(value) for value in ownership_range)
    root = manifest_path.parent
    exact_source = next(
        (
            shard
            for shard in shards
            if tuple(int(value) for value in shard["ownership_range"]) == (first, last)
        ),
        None,
    )
    if exact_source is not None:
        source_path = root / str(exact_source["path"])
        values = np.load(source_path, mmap_mode="r", allow_pickle=False)
        if tuple(values.shape) != (last - first, expected_columns):
            raise ValueError("full response packet exact shard shape mismatch")
        if str(values.dtype) != "complex128":
            raise ValueError("full response packet exact shard dtype mismatch")
        if _sha256_file(source_path) != exact_source.get("file_sha256"):
            raise ValueError("full response packet exact shard hash mismatch")
        values.setflags(write=False)
        ownership_mode = "producer_owner_rows_mmap"
        copy_count = 0
    else:
        values = np.empty(
            (last - first, expected_columns), dtype=np.complex128, order="F"
        )
        overlap_count = 0
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
            if tuple(source.shape) != (source_end - source_start, expected_columns):
                raise ValueError("full response packet source shard shape mismatch")
            if str(source.dtype) != "complex128":
                raise ValueError("full response packet source shard dtype mismatch")
            if _sha256_file(source_path) != shard.get("file_sha256"):
                raise ValueError("full response packet source shard hash mismatch")
            values[overlap_start - first : overlap_end - first] = source[
                overlap_start - source_start : overlap_end - source_start
            ]
            overlap_count += 1
        if overlap_count == 0 and first != last:
            raise ValueError("full response packet has no overlapping shard")
        values.setflags(write=False)
        ownership_mode = "remapped_owner_rows"
        copy_count = 1
    diagnostics = {
        "ownership_mode": ownership_mode,
        "producer_ownership_ranges": [
            list(map(int, shard["ownership_range"])) for shard in shards
        ],
        "target_ownership_range": [first, last],
        "owner_row_coverage_exact": True,
        "owned_local_basis_copy_count": copy_count,
        "global_basis_materialized": False,
        "consumer_factor_count": 0,
        "source_shard_hash_verified_local": True,
        "source_shard_hash_verification_scope": "target_overlap_shards_on_this_rank",
        "manifest_sha256": str(expected_manifest_sha256),
        "comm_size": int(comm.size),
        "column_count": expected_columns,
    }
    return ExactSideResponsePacket(values, manifest, manifest_path, diagnostics)


def compress_owner_row_response_packet(
    packet: ExactSideResponsePacket,
    *,
    training_column_indices: tuple[int, ...] | list[int] | None = None,
    holdout_column_indices: tuple[int, ...] | list[int] | None = None,
    zero_column_index: int | None = None,
    comm: MPI.Intracomm,
    svd_tolerance: float | None = None,
) -> dict[str, Any]:
    """Rank-deficiency-tolerant owner-row TSQR followed by one small-R SVD.

    The decomposition never forms a response Gram matrix.  Local QR factors
    are reduced through the small R factors; all requested ranks are slices of
    the same SVD and therefore do not repeat TSQR or factorization.
    """

    values = np.asarray(packet.local_values)
    if values.ndim != 2 or values.shape[1] != V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS:
        raise ValueError("compression requires the full 961-column response packet")
    manifest = packet.manifest
    train = tuple(
        int(value)
        for value in (
            training_column_indices
            if training_column_indices is not None
            else manifest.get("training_column_indices", ())
        )
    )
    holdout = tuple(
        int(value)
        for value in (
            holdout_column_indices
            if holdout_column_indices is not None
            else manifest.get("holdout_column_indices", ())
        )
    )
    if zero_column_index is None:
        zero_column_index = int(manifest.get("zero_column_index", -1))
    if (
        len(train) != 950
        or len(set(train)) != 950
        or len(holdout) != 10
        or len(set(holdout)) != 10
        or set(train) & set(holdout)
        or set(train) | set(holdout) != set(range(960))
        or int(zero_column_index) != 960
    ):
        raise ValueError(
            "full response packet train/holdout/zero partition is not frozen"
        )

    for start in range(0, values.shape[1], 32):
        if not np.isfinite(values[:, start : start + 32]).all():
            raise ValueError("full response packet mmap contains non-finite values")
    zero_values = np.asarray(values[:, int(zero_column_index)], dtype=np.complex128)
    zero_finite = bool(np.isfinite(zero_values).all())
    zero_finite = bool(comm.allreduce(zero_finite, op=MPI.LAND))
    zero_local_sq = float(np.vdot(zero_values, zero_values).real)
    zero_global_sq = float(comm.allreduce(zero_local_sq, op=MPI.SUM))
    zero_output_norm = float(np.sqrt(max(zero_global_sq, 0.0)))

    matrix = np.asarray(values[:, train], dtype=np.complex128, order="F")
    local_rows, column_count = matrix.shape
    q_local = np.zeros((local_rows, column_count), dtype=np.complex128, order="F")
    r_local = np.zeros((column_count, column_count), dtype=np.complex128, order="F")
    if local_rows:
        q_small, r_small = np.linalg.qr(matrix, mode="reduced")
        q_local[:, : q_small.shape[1]] = q_small
        r_local[: r_small.shape[0], :] = r_small

    gathered_r = comm.gather(r_local, root=0)
    q2_block = None
    r_global = None
    u_r = None
    singular_values = None
    if comm.rank == 0:
        stacked_r = np.vstack(gathered_r)
        q2, r_global = np.linalg.qr(stacked_r, mode="reduced")
        u_r, singular_values, _ = np.linalg.svd(r_global, full_matrices=False)
        q2_blocks = [
            np.asarray(q2[index * column_count : (index + 1) * column_count])
            for index in range(comm.size)
        ]
    else:
        q2_blocks = None
    q2_block = comm.scatter(q2_blocks, root=0)
    r_global = comm.bcast(r_global, root=0)
    u_r = comm.bcast(u_r, root=0)
    singular_values = np.asarray(comm.bcast(singular_values, root=0), dtype=float)
    scale = float(singular_values[0]) if singular_values.size else 0.0
    global_rows = int(comm.allreduce(local_rows, op=MPI.SUM))
    if svd_tolerance is None:
        svd_tolerance = (
            np.finfo(float).eps * max(global_rows, column_count) * max(scale, 1.0)
        )
    numerical_rank = int(np.count_nonzero(singular_values > float(svd_tolerance)))
    nonzero = singular_values[singular_values > float(svd_tolerance)]
    condition = float(nonzero[0] / nonzero[-1]) if nonzero.size else None
    condition_finite = condition is not None and bool(np.isfinite(condition))

    q_local = q_local @ q2_block
    max_effective_rank = min(512, numerical_rank)
    response_basis = q_local @ u_r[:, :max_effective_rank]
    local_reconstruction = q_local @ r_global
    local_reconstruction_sq = float(np.linalg.norm(matrix - local_reconstruction) ** 2)
    local_matrix_sq = float(np.linalg.norm(matrix) ** 2)
    global_reconstruction_sq = comm.allreduce(local_reconstruction_sq, op=MPI.SUM)
    global_matrix_sq = comm.allreduce(local_matrix_sq, op=MPI.SUM)
    tsqr_reconstruction_error = (
        float(np.sqrt(max(global_reconstruction_sq, 0.0) / global_matrix_sq))
        if global_matrix_sq > 0.0
        else 0.0
    )
    singular_sq = singular_values * singular_values
    singular_total = float(np.sum(singular_sq))
    rank_reports: list[dict[str, Any]] = []
    for requested_rank in (64, 128, 256, 512):
        effective_rank = min(int(requested_rank), numerical_rank)
        rank_basis = response_basis[:, :effective_rank]
        local_gram = rank_basis.conj().T @ rank_basis
        global_gram = np.empty_like(local_gram)
        comm.Allreduce(local_gram, global_gram, op=MPI.SUM)
        identity = np.eye(effective_rank, dtype=np.complex128)
        projection_errors: dict[str, float | None] = {}
        for index in holdout:
            local_column = np.asarray(values[:, index], dtype=np.complex128)
            local_coefficients = rank_basis.conj().T @ local_column
            global_coefficients = np.empty_like(local_coefficients)
            comm.Allreduce(local_coefficients, global_coefficients, op=MPI.SUM)
            local_projection = rank_basis @ global_coefficients
            local_difference_sq = float(
                np.linalg.norm(local_column - local_projection) ** 2
            )
            local_column_sq = float(np.linalg.norm(local_column) ** 2)
            global_difference_sq = comm.allreduce(local_difference_sq, op=MPI.SUM)
            global_column_sq = comm.allreduce(local_column_sq, op=MPI.SUM)
            projection_errors[str(index)] = (
                float(np.sqrt(max(global_difference_sq, 0.0) / global_column_sq))
                if global_column_sq > 0.0
                else None
            )
        rank_tail = float(np.sum(singular_sq[effective_rank:]))
        rank_reports.append(
            {
                "requested_rank": int(requested_rank),
                "effective_rank": int(effective_rank),
                "training_optimal_frobenius_error": (
                    float(np.sqrt(rank_tail / singular_total))
                    if singular_total > 0.0
                    else 0.0
                ),
                "q_orthogonality_error": float(np.linalg.norm(global_gram - identity)),
                "holdout_projection_error": projection_errors,
                "holdout_worst_projection_error": max(
                    (
                        value
                        for value in projection_errors.values()
                        if value is not None
                    ),
                    default=None,
                ),
            }
        )
    return {
        "schema": V10_SIDE_RESPONSE_PACKET_COMPRESSION_SCHEMA,
        "method": V10_SIDE_RESPONSE_PACKET_COMPRESSION_METHOD,
        "training_column_indices": list(train),
        "holdout_column_indices": list(holdout),
        "zero_column_index": int(zero_column_index),
        "zero_output_finite": zero_finite,
        "zero_output_norm": zero_output_norm,
        "zero_map_pass": bool(zero_finite and zero_output_norm <= 1.0e-13),
        "singular_values": [float(value) for value in singular_values],
        "numerical_rank": numerical_rank,
        "condition": condition,
        "condition_finite": bool(condition_finite),
        "svd_tolerance": float(svd_tolerance),
        "tsqr_reconstruction_error": tsqr_reconstruction_error,
        "rank_reports": rank_reports,
        "factor_inventory": {
            "consumer_factor_count": 0,
            "global_direct_factor_count": 0,
            "nested_ksp_count": 0,
        },
        "gram_or_normal_equations_used": False,
        "one_tsqr_one_small_r_svd": True,
    }


def audit_bottom_response_packet_algebra(
    packet: ExactSideResponsePacket,
    *,
    actual_source_records: Sequence[Mapping[str, Any]],
    expected_identity_records: Sequence[Mapping[str, Any]],
    expected_provenance: Mapping[str, Any],
    source_columns: Mapping[int, np.ndarray],
    v7_schur_authority: np.ndarray,
    v7_modal_amplitudes: np.ndarray,
    v7_bottom_trace: np.ndarray,
    physical_rhs: np.ndarray,
    block_action: Callable[[np.ndarray], np.ndarray],
    schur_action: Callable[[np.ndarray], np.ndarray],
    trace_action: Callable[[np.ndarray], np.ndarray],
    factor_inventory: Mapping[str, int],
    field_response_sign: complex = V11_BOTTOM_FIELD_RESPONSE_SIGN,
    schur_contribution_sign: complex = V11_BOTTOM_SCHUR_CONTRIBUTION_SIGN,
    sample_indices: Sequence[int] = V11_BOTTOM_RESPONSE_SAMPLE_INDICES,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    system_assembled: bool = True,
) -> dict[str, Any]:
    """Audit packet equations without constructing a solver or factor.

    The expected identities are independently rebuilt from the selected-mode
    source contract.  Actual producer records are a separate input; manifest
    columns are used only for column/label coverage.  Field reconstruction
    uses the fixed minus sign from _recover_local_field, while the Schur
    contribution uses the fixed positive D X sign before H-D X.
    """

    def relative_error(actual: Any, expected: Any) -> float:
        actual = np.asarray(actual, dtype=np.complex128)
        expected = np.asarray(expected, dtype=np.complex128)
        if actual.shape != expected.shape:
            raise ValueError("bottom packet algebra vectors have different shapes")
        difference = actual - expected
        difference_sq = float(comm.allreduce(np.vdot(difference, difference).real))
        expected_sq = float(comm.allreduce(np.vdot(expected, expected).real))
        if expected_sq <= np.finfo(float).tiny:
            return 0.0 if difference_sq <= 1.0e-30 else float("inf")
        return float(np.sqrt(max(difference_sq, 0.0) / expected_sq))

    def identity_view(record: Mapping[str, Any]) -> tuple[Any, ...]:
        def canonical(value: Any) -> Any:
            if isinstance(value, Mapping):
                return tuple(
                    (str(key), canonical(item)) for key, item in sorted(value.items())
                )
            if isinstance(value, (list, tuple)):
                return tuple(canonical(item) for item in value)
            return value

        return (
            int(record.get("column_index", -1)),
            record.get("label"),
            record.get("source"),
            record.get("family"),
            record.get("branch"),
            record.get("mode_index"),
            canonical(record.get("raw_beta")),
            canonical(record.get("discrete_beta")),
            record.get("schedule_kind"),
        )

    packet_result: dict[str, Any] | None = None
    try:
        frozen_samples = tuple(int(index) for index in sample_indices)
        if frozen_samples != V11_BOTTOM_RESPONSE_SAMPLE_INDICES:
            raise ValueError("V11 bottom sample indices are not frozen")
        manifest = packet.manifest
        manifest_columns = list(manifest.get("columns", ()))
        expected = list(expected_identity_records)
        actual = list(actual_source_records)
        if (
            manifest.get("schema") != V10_SIDE_RESPONSE_PACKET_FULL_SCHEMA
            or manifest.get("method") != V10_SIDE_RESPONSE_PACKET_FULL_METHOD
            or len(manifest_columns) != V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS
            or len(expected) != V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS
            or len(actual) != V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS
        ):
            raise ValueError("V11 bottom packet identity size/schema failed")
        manifest_view = [
            (int(record.get("column", -1)), str(record.get("label", "")))
            for record in manifest_columns
        ]
        expected_manifest_view = [
            (int(record.get("column_index", -1)), str(record.get("label", "")))
            for record in expected
        ]
        manifest_columns_pass = manifest_view == expected_manifest_view
        order_pass = [
            int(record.get("column", -1)) for record in manifest_columns
        ] == list(range(V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS)) and [
            int(record.get("column_index", -1)) for record in expected
        ] == list(range(V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS))
        source_identity_pass = [identity_view(record) for record in actual] == [
            identity_view(record) for record in expected
        ]
        identity_pass = bool(
            comm.allreduce(
                bool(manifest_columns_pass and source_identity_pass),
                op=MPI.LAND,
            )
        )
        order_pass = bool(comm.allreduce(bool(order_pass), op=MPI.LAND))
        if not identity_pass:
            raise ValueError("V11 source or manifest identity mismatch")
        if not order_pass:
            raise ValueError("V11 source/manifest order contract failed")
        if (
            manifest_columns[960].get("column") != 960
            or manifest_columns[960].get("label") != "physical_side_rhs"
        ):
            raise ValueError("V11 physical RHS identity is not separate")
        provenance_pass = dict(manifest.get("provenance", {})) == dict(
            expected_provenance
        )
        if not provenance_pass:
            raise ValueError("V11 bottom packet provenance mismatch")
        local_values = np.asarray(packet.local_values, dtype=np.complex128)
        if (
            local_values.ndim != 2
            or local_values.shape[1] != V10_SIDE_RESPONSE_PACKET_FULL_COLUMNS
            or not local_values.flags.f_contiguous
        ):
            raise ValueError("V11 packet owner-row layout is invalid")
        local_rows = local_values.shape[0]
        values_finite = bool(
            comm.allreduce(bool(np.isfinite(local_values).all()), op=MPI.LAND)
        )
        if not values_finite:
            raise ValueError("V11 packet contains a nonfinite owner-row value")
        global_rows = int(comm.allreduce(local_rows))
        if int(manifest.get("global_rows", -1)) != global_rows:
            raise ValueError("V11 global row size mismatch")
        if (
            manifest.get("dtype") != "complex128"
            or manifest.get("layout") != "owner_row_sharded_column_major"
        ):
            raise ValueError("V11 packet dtype/layout mismatch")
        shards = _validate_manifest_coverage(
            list(manifest.get("shards", ())), global_rows
        )
        local_layout_pass = bool(
            shards
            and packet.diagnostics.get("owner_row_coverage_exact") is True
            and packet.diagnostics.get("source_shard_hash_verified_local") is True
        )
        layout_hash_pass = bool(comm.allreduce(local_layout_pass, op=MPI.LAND))
        required = set(V11_BOTTOM_RESPONSE_SAMPLE_INDICES)
        required_indices = tuple(V11_BOTTOM_RESPONSE_SAMPLE_INDICES)
        source_keys_pass = required.issubset(source_columns)
        if not bool(comm.allreduce(source_keys_pass, op=MPI.LAND)):
            raise ValueError("V11 sampled source authority is incomplete")
        amplitudes = np.asarray(v7_modal_amplitudes, dtype=np.complex128)
        amplitudes_shape_pass = amplitudes.shape == (960,)
        if not bool(comm.allreduce(amplitudes_shape_pass, op=MPI.LAND)):
            raise ValueError("V7 modal amplitude authority must contain 960 values")
        if not bool(comm.allreduce(bool(np.isfinite(amplitudes).all()), op=MPI.LAND)):
            raise ValueError("V7 modal amplitudes are nonfinite")
        physical_rhs = np.asarray(physical_rhs, dtype=np.complex128)
        if not bool(comm.allreduce(physical_rhs.shape == (local_rows,), op=MPI.LAND)):
            raise ValueError("V7 physical RHS ownership does not match")
        if not bool(comm.allreduce(bool(np.isfinite(physical_rhs).all()), op=MPI.LAND)):
            raise ValueError("V7 physical RHS is nonfinite")
        sample_sources = {
            column: np.asarray(source_columns[column], dtype=np.complex128)
            for column in required_indices
        }
        sample_inputs_pass = all(
            value.shape == (local_rows,) and np.isfinite(value).all()
            for value in sample_sources.values()
        )
        if not bool(comm.allreduce(sample_inputs_pass, op=MPI.LAND)):
            raise ValueError("V11 sampled source input is nonfinite or mis-sized")
        field_sign = complex(field_response_sign)
        schur_sign = complex(schur_contribution_sign)
        allowed_signs = (1.0 + 0.0j, -1.0 + 0.0j)
        if field_sign not in allowed_signs or schur_sign not in allowed_signs:
            raise ValueError("V11 response signs must be explicit plus or minus")
        sample_reports: list[dict[str, Any]] = []
        counters = {
            "block_action_count": 0,
            "schur_action_count": 0,
            "trace_action_count": 0,
        }
        physical_solution = np.array(local_values[:, 960], copy=True, order="F")
        zero_input = np.zeros(local_rows, dtype=np.complex128)
        combined = physical_solution.copy(order="F")
        schur_combined: np.ndarray | None = None
        for column in range(960):
            response = np.array(local_values[:, column], copy=True, order="F")
            counters["schur_action_count"] += 1
            schur_value = np.asarray(schur_action(response), dtype=np.complex128)
            if schur_combined is None:
                schur_combined = np.zeros_like(schur_value)
            schur_combined += schur_sign * schur_value * amplitudes[column]
            combined += field_sign * response * amplitudes[column]
            if column in required:
                counters["block_action_count"] += 1
                action_value = np.asarray(block_action(response), dtype=np.complex128)
                sample_finite = bool(
                    np.isfinite(action_value).all() and np.isfinite(schur_value).all()
                )
                sample_finite = bool(comm.allreduce(sample_finite, op=MPI.LAND))
                if not sample_finite:
                    raise ValueError(
                        f"V11 sampled action is nonfinite at column {column}"
                    )
                sample_reports.append(
                    {
                        "column": int(column),
                        "label": str(actual[column].get("label")),
                        "finite": sample_finite,
                        "source_equation_relative_error": relative_error(
                            action_value, sample_sources[column]
                        ),
                    }
                )
        if schur_combined is None:
            raise ValueError("V11 Schur action produced no authority")
        combined_finite = bool(
            comm.allreduce(bool(np.isfinite(combined).all()), op=MPI.LAND)
        )
        schur_finite = bool(
            comm.allreduce(bool(np.isfinite(schur_combined).all()), op=MPI.LAND)
        )
        if not combined_finite or not schur_finite:
            raise ValueError("V11 streamed packet reconstruction is nonfinite")
        counters["block_action_count"] += 2
        physical_action = np.asarray(
            block_action(physical_solution), dtype=np.complex128
        )
        zero_action = np.asarray(block_action(zero_input), dtype=np.complex128)
        if not bool(
            comm.allreduce(
                bool(
                    physical_action.shape == (local_rows,)
                    and zero_action.shape == (local_rows,)
                ),
                op=MPI.LAND,
            )
        ):
            raise ValueError("V11 physical/zero action ownership does not match")
        if not bool(
            comm.allreduce(
                bool(
                    np.isfinite(physical_action).all()
                    and np.isfinite(zero_action).all()
                ),
                op=MPI.LAND,
            )
        ):
            raise ValueError("V11 physical/zero action is nonfinite")
        counters["trace_action_count"] += 1
        physical_error = relative_error(physical_action, physical_rhs)
        zero_error = relative_error(zero_action, np.zeros_like(zero_input))
        trace_value = np.asarray(trace_action(combined), dtype=np.complex128)
        trace_expected = np.asarray(v7_bottom_trace, dtype=np.complex128)
        if not bool(
            comm.allreduce(trace_value.shape == trace_expected.shape, op=MPI.LAND)
        ):
            raise ValueError("V11 canonical trace ownership does not match")
        if not bool(
            comm.allreduce(
                bool(
                    np.isfinite(trace_value).all() and np.isfinite(trace_expected).all()
                ),
                op=MPI.LAND,
            )
        ):
            raise ValueError("V11 canonical trace is nonfinite")
        trace_error = relative_error(trace_value, trace_expected)
        schur_expected = np.asarray(v7_schur_authority, dtype=np.complex128)
        if not bool(
            comm.allreduce(
                bool(
                    schur_expected.shape == schur_combined.shape
                    and np.isfinite(schur_expected).all()
                ),
                op=MPI.LAND,
            )
        ):
            raise ValueError("V11 independent Schur authority is invalid")
        schur_error = relative_error(schur_combined, schur_expected)
        physical_rhs_norm = float(
            np.sqrt(
                max(
                    float(comm.allreduce(np.vdot(physical_rhs, physical_rhs).real)), 0.0
                )
            )
        )
        physical_output_norm = float(
            np.sqrt(
                max(
                    float(
                        comm.allreduce(
                            np.vdot(physical_solution, physical_solution).real
                        )
                    ),
                    0.0,
                )
            )
        )
        zero_finite = bool(
            comm.allreduce(bool(np.isfinite(zero_action).all()), op=MPI.LAND)
        )
        zero_output_norm = float(
            np.sqrt(
                max(float(comm.allreduce(np.vdot(zero_action, zero_action).real)), 0.0)
            )
        )
        inventory = {key: int(value) for key, value in factor_inventory.items()}
        if any(
            key not in inventory for key in ("factor_count", "ksp_count", "qep_count")
        ):
            raise ValueError("V11 factor/KSP/QEP inventory is incomplete")
        packet_result = {
            "schema": "task039.v11.bottom_packet_algebra.v1",
            "method": "task039_v11_bottom_packet_algebra_checker",
            "sample_indices": list(V11_BOTTOM_RESPONSE_SAMPLE_INDICES),
            "identity": {
                "manifest_columns_pass": bool(manifest_columns_pass),
                "order_pass": bool(order_pass),
                "source_identity_pass": bool(source_identity_pass),
                "all_960_metadata_identity": bool(identity_pass and order_pass),
                "sampled_numeric_source_identity_count": len(required_indices),
                "provider_scale": -1.0,
                "provider_scale_source": (
                    "StreamedPhysicalModalSourceProvider._entries_to_vec(scale=-1.0)"
                ),
                "normalization_contract_bound": bool(
                    manifest.get("provenance", {}).get(
                        "selected_mode_packet_manifest_sha256"
                    )
                    and manifest.get("provenance", {}).get("source_sha")
                ),
                "physical_rhs_separate": True,
                "owner_row_coverage_exact": layout_hash_pass,
                "dtype": manifest["dtype"],
                "f_order": True,
            },
            "provenance_pass": bool(provenance_pass),
            "physical_rhs": {
                "status": (
                    "degenerate_zero_rhs"
                    if physical_rhs_norm <= 1.0e-13
                    else "nondegenerate"
                ),
                "norm": physical_rhs_norm,
                "solution_norm": physical_output_norm,
                "mandatory": bool(physical_rhs_norm > 1.0e-13),
                "equation_relative_error": physical_error,
            },
            "zero_map": {
                "finite": zero_finite,
                "input_norm": 0.0,
                "output_norm": zero_output_norm,
                "relative_error": zero_error,
                "pass": bool(zero_finite and zero_output_norm <= 1.0e-13),
            },
            "sample_reports": sample_reports,
            "modal_reconstruction": {
                "field_response_sign": field_sign,
                "field_response_sign_source": (
                    "_recover_local_field: rhs.axpy(-1,coupling)"
                ),
                "schur_contribution_sign": schur_sign,
                "schur_contribution_sign_source": (
                    "build_hybrid_action_modal_schur: H-DX; compare positive DX"
                ),
                "trace_relative_error": trace_error,
                "schur_relative_error": schur_error,
            },
            "system_assembled": bool(system_assembled),
            "action_counters": counters,
            "factor_inventory": inventory,
            "packet_released": False,
            "pde_solve": "not_run",
        }
    finally:
        packet.destroy()
    packet_result["packet_released"] = bool(packet.diagnostics.get("released"))
    sample_pass = bool(
        len(packet_result["sample_reports"]) == len(required)
        and all(
            report["finite"] and report["source_equation_relative_error"] <= 1.0e-9
            for report in packet_result["sample_reports"]
        )
    )
    inventory_pass = all(
        packet_result["factor_inventory"][key] == 0
        for key in ("factor_count", "ksp_count", "qep_count")
    )
    packet_result["gate"] = {
        "manifest_columns_pass": bool(
            packet_result["identity"]["manifest_columns_pass"]
        ),
        "order_pass": bool(packet_result["identity"]["order_pass"]),
        "all_960_metadata_identity": bool(
            packet_result["identity"]["all_960_metadata_identity"]
        ),
        "source_identity_pass": bool(packet_result["identity"]["source_identity_pass"]),
        "provenance_pass": bool(packet_result["provenance_pass"]),
        "layout_hash_pass": bool(packet_result["identity"]["owner_row_coverage_exact"]),
        "system_assembled_pass": bool(packet_result["system_assembled"]),
        "physical_pass": bool(
            np.isfinite(packet_result["physical_rhs"]["equation_relative_error"])
            and packet_result["physical_rhs"]["equation_relative_error"] <= 1.0e-9
        ),
        "zero_map_pass": bool(packet_result["zero_map"]["pass"]),
        "sample_equation_pass": sample_pass,
        "modal_trace_pass": bool(
            np.isfinite(packet_result["modal_reconstruction"]["trace_relative_error"])
            and packet_result["modal_reconstruction"]["trace_relative_error"] <= 5.0e-9
        ),
        "modal_schur_pass": bool(
            np.isfinite(packet_result["modal_reconstruction"]["schur_relative_error"])
            and packet_result["modal_reconstruction"]["schur_relative_error"] <= 5.0e-9
        ),
        "sign_contract_pass": bool(
            field_sign == V11_BOTTOM_FIELD_RESPONSE_SIGN
            and schur_sign == V11_BOTTOM_SCHUR_CONTRIBUTION_SIGN
            and packet_result["identity"]["normalization_contract_bound"]
        ),
        "action_counters_pass": bool(
            counters["block_action_count"] == 12
            and counters["schur_action_count"] == 960
            and counters["trace_action_count"] == 1
        ),
        "factor_qep_ksp_pass": bool(inventory_pass),
        "packet_release_pass": bool(packet_result["packet_released"]),
    }
    packet_result["gate"]["pass"] = all(packet_result["gate"].values())
    return packet_result
