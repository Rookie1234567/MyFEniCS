"""Dynamic owner-local Fourier-DtN action for the current 3D port contract.

The carrier keeps sparse surface functionals and one explicit projection
denominator ``H_i`` per mode.  Applying the action reduces the projection and
coupling in deterministic batches; it never creates numeric C/D matrices or a
FE-sized replicated vector.  Surface functionals are assembled by the
existing MPC-aware port machinery so Floquet phase and H(curl) orientation are
applied exactly once.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import time
from types import MappingProxyType
from typing import Any

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc


FULLSPACE_DTN_PROFILE = "full3d_scalable_v1"
FULLSPACE_DTN_BATCH_SIZE = 8
FULLSPACE_DTN_PROGRESS_INTERVAL = 64
FULLSPACE_DTN_MANIFEST_SCHEMA = "fullspace-dtn.mode-manifest.v1"
_SURFACE_FUNCTIONAL_FRAME = struct.Struct("<qQQd")
_RESUMABLE_SURFACE_STREAM_SCHEMA = "task40extra.v33_resumable_surface_functionals.v1"

_MODE_IDENTITY_FIELDS = frozenset(
    {
        "schema",
        "mode_index",
        "side",
        "m",
        "n",
        "polarization",
        "alpha",
        "gamma",
        "beta",
        "k_vector",
        "e_vector",
        "h_vector",
        "refractive_index",
        "vertical_sign",
        "electric_tangential_norm_sq",
        "power_per_unit_amplitude",
        "propagating",
        "rayleigh_warning",
        "classification",
        "rayleigh_tolerance",
        "projection_denominator",
        "traction_vector",
    }
)


def _readonly(values: Any, dtype: np.dtype[Any]) -> np.ndarray:
    array = np.ascontiguousarray(np.asarray(values, dtype=dtype))
    array.flags.writeable = False
    return array


def _jsonable(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        if not np.isfinite(value.real) or not np.isfinite(value.imag):
            raise ValueError("mode identity contains a non-finite complex value")
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, float):
        if not np.isfinite(value):
            raise ValueError("mode identity contains a non-finite float")
        return float(value)
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (tuple, list, np.ndarray)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, bool, int)) or value is None:
        return value
    raise TypeError(f"unsupported mode identity value: {type(value).__name__}")


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _jsonable(value),
        ensure_ascii=True,
        allow_nan=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("ascii")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_json(path: Path, value: Mapping[str, Any]) -> bytes:
    encoded = _canonical_json_bytes(value) + b"\n"
    temporary = path.with_name(f"{path.name}.tmp.{os.getpid()}.{time.time_ns()}")
    with temporary.open("xb") as stream:
        stream.write(encoded)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    _fsync_directory(path.parent)
    return encoded


def _file_identity_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _surface_frame_arrays(
    stream, *, expected_index: int, expected_h: float, digest=None,
    stream_end: int | None = None, max_frame_bytes: int | None = None,
):
    start = stream.tell()
    header = stream.read(_SURFACE_FUNCTIONAL_FRAME.size)
    if len(header) != _SURFACE_FUNCTIONAL_FRAME.size:
        raise IOError("resumable surface stream has an incomplete frame header")
    mode_index, coupling_count, projection_count, normalization_h = (
        _SURFACE_FUNCTIONAL_FRAME.unpack(header)
    )
    if (
        int(mode_index) != int(expected_index)
        or not np.isfinite(normalization_h)
        or float(normalization_h) != float(expected_h)
    ):
        raise ValueError("resumable surface frame mode/H identity changed")
    body_bytes = 20 * (int(coupling_count) + int(projection_count))
    frame_bytes = _SURFACE_FUNCTIONAL_FRAME.size + body_bytes
    if max_frame_bytes is not None:
        if type(max_frame_bytes) is not int or max_frame_bytes < _SURFACE_FUNCTIONAL_FRAME.size:
            raise ValueError("resumable surface frame byte bound is invalid")
        if frame_bytes > max_frame_bytes:
            raise ValueError("resumable surface frame exceeds its current FE support byte bound")
    body_start = stream.tell()
    if stream_end is None:
        stream.seek(0, os.SEEK_END)
        end = stream.tell()
        stream.seek(body_start)
    else:
        end = int(stream_end)
    if body_bytes > end - body_start:
        raise IOError("resumable surface stream has a truncated frame payload")
    body = stream.read(body_bytes)
    if len(body) != body_bytes:
        raise IOError("resumable surface stream has a truncated frame payload")
    offset = 0

    def take(count: int, dtype: str, itemsize: int):
        nonlocal offset
        result = np.frombuffer(
            body,
            dtype=np.dtype(dtype),
            count=int(count),
            offset=offset,
        )
        offset += int(count) * itemsize
        return result

    coupling_rows = take(coupling_count, "<i4", 4)
    coupling_values = take(coupling_count, "<c16", 16)
    projection_rows = take(projection_count, "<i4", 4)
    projection_values = take(projection_count, "<c16", 16)
    if offset != body_bytes:
        raise IOError("resumable surface frame length is inconsistent")
    for rows, values in (
        (coupling_rows, coupling_values),
        (projection_rows, projection_values),
    ):
        if (
            rows.size != values.size
            or (rows.size > 1 and np.any(rows[1:] <= rows[:-1]))
            or (rows.size and int(rows[0]) < 0)
            or not np.isfinite(values).all()
        ):
            raise ValueError("resumable surface frame contains invalid sparse rows/values")
    end = stream.tell()
    if digest is not None:
        digest.update(header)
        digest.update(body)
    return (
        int(mode_index),
        float(normalization_h),
        coupling_rows,
        coupling_values,
        projection_rows,
        projection_values,
        int(end - start),
    )


class ReadOnlySurfaceFunctionalSource:
    """Validated indexed view of an immutable resumable carrier file.

    Validation consumes the committed prefix exactly once.  Later action
    sweeps stream one frame at a time from the same file and never retain the
    complete carrier payload in Python memory.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        expected_manifest_sha256: str,
        expected_checkpoint_sha256: str,
        expected_identity_sha256: str,
        expected_prefix_sha256: str,
        expected_mode_count: int,
        expected_committed_bytes: int,
        max_frame_bytes: int | None = None,
        max_batch_modes: int = FULLSPACE_DTN_BATCH_SIZE,
        offset_index_path: str | Path | None = None,
        expected_mode_keys: Sequence[tuple[Any, ...]],
        expected_normalization_h: Sequence[float],
        global_rows: int,
        ownership_range: tuple[int, int],
        slave_rows: Any = (),
        identity_validator: Callable[[Mapping[str, Any], Sequence[Mapping[str, Any]]], None] | None = None,
        frame_observer: Callable[..., None] | None = None,
        progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
        progress_interval: int = 256,
    ) -> None:
        self.path = Path(path).resolve()
        self.checkpoint_path = Path(str(self.path) + ".checkpoint.json")
        self.manifest_path = Path(str(self.path) + ".manifest.json")
        if (
            type(expected_mode_count) is not int
            or expected_mode_count <= 0
            or type(expected_committed_bytes) is not int
            or expected_committed_bytes < 0
            or type(max_batch_modes) is not int
            or max_batch_modes <= 0
            or (
                max_frame_bytes is not None
                and (type(max_frame_bytes) is not int or max_frame_bytes < _SURFACE_FUNCTIONAL_FRAME.size)
            )
            or type(progress_interval) is not int
            or progress_interval <= 0
        ):
            raise ValueError("saved surface donor expectations are invalid")
        if identity_validator is not None and not callable(identity_validator):
            raise TypeError("saved surface donor identity validator must be callable")
        if frame_observer is not None and not callable(frame_observer):
            raise TypeError("saved surface donor frame observer must be callable")
        if progress_callback is not None and not callable(progress_callback):
            raise TypeError("saved surface donor progress callback must be callable")
        for digest in (
            expected_manifest_sha256,
            expected_checkpoint_sha256,
            expected_identity_sha256,
            expected_prefix_sha256,
        ):
            if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                raise ValueError("saved surface donor SHA-256 binding is malformed")
        self._global_rows = int(global_rows)
        self._owned_start, self._owned_end = map(int, ownership_range)
        if (
            self._global_rows <= 0
            or not 0 <= self._owned_start <= self._owned_end <= self._global_rows
        ):
            raise ValueError("saved surface donor FE row layout is invalid")
        self._expected_mode_count = expected_mode_count
        self._expected_committed_bytes = expected_committed_bytes
        self.max_batch_modes = max_batch_modes
        self.max_frame_bytes = max_frame_bytes
        self._offset_index_path = (
            None if offset_index_path is None else Path(offset_index_path).resolve()
        )
        self._expected_prefix_sha256 = expected_prefix_sha256
        self._offsets = np.empty(expected_mode_count + 1, dtype=np.int64)
        self._read_sweeps = 0
        self._read_batches = 0
        self._read_modes = 0
        self._read_bytes = 0
        self._path_identity: tuple[int, int, int, int, int] | None = None
        self._validation_seconds = 0.0
        self._validation_frame_read_hash_seconds = 0.0
        self._validation_classification_seconds = 0.0
        self._validation_frame_observer_seconds = 0.0
        self._validation_payload_digest_seconds = 0.0
        self._read_frame_parse_seconds = 0.0
        self._max_frame_bytes_observed = 0

        if not self.path.is_file() or not self.checkpoint_path.is_file() or not self.manifest_path.is_file():
            raise FileNotFoundError("require-existing surface donor data/checkpoint/manifest is incomplete")
        metadata_paths = (self.checkpoint_path, self.manifest_path)
        metadata_identities = {
            item: self._stat_identity(item.stat()) for item in metadata_paths
        }
        checkpoint_sha = _file_identity_sha256(self.checkpoint_path)
        if checkpoint_sha != expected_checkpoint_sha256:
            raise ValueError("saved surface donor checkpoint SHA-256 differs from the contract")
        manifest_sha = _file_identity_sha256(self.manifest_path)
        if manifest_sha != expected_manifest_sha256:
            raise ValueError("saved surface donor manifest SHA-256 differs from the contract")
        try:
            checkpoint = json.loads(self.checkpoint_path.read_text(encoding="ascii"))
            with self.manifest_path.open("r", encoding="ascii") as stream:
                manifest = json.load(stream)
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError("saved surface donor metadata is unreadable") from exc
        if any(
            self._stat_identity(item.stat()) != metadata_identities[item]
            for item in metadata_paths
        ):
            raise IOError("saved surface donor metadata changed while it was being read")
        if not isinstance(checkpoint, dict) or not isinstance(manifest, dict):
            raise ValueError("saved surface donor metadata must be JSON objects")
        if (
            manifest.get("schema") != _RESUMABLE_SURFACE_STREAM_SCHEMA
            or manifest.get("identity_sha256") != expected_identity_sha256
            or hashlib.sha256(_canonical_json_bytes(manifest.get("identity"))).hexdigest()
            != expected_identity_sha256
            or checkpoint.get("schema") != _RESUMABLE_SURFACE_STREAM_SCHEMA
            or checkpoint.get("identity_sha256") != expected_identity_sha256
            or checkpoint.get("manifest_sha256") != expected_manifest_sha256
            or checkpoint.get("expected_mode_count") != expected_mode_count
            or checkpoint.get("committed_mode_count") != expected_mode_count
            or checkpoint.get("committed_bytes") != expected_committed_bytes
            or checkpoint.get("committed_prefix_sha256") != expected_prefix_sha256
            or type(checkpoint.get("peak_component_cache_unique_backing_bytes")) is not int
            or checkpoint["peak_component_cache_unique_backing_bytes"] < 0
        ):
            raise ValueError("saved surface donor checkpoint/manifest identity differs from the contract")
        identity = manifest.get("identity")
        mode_keys_raw = manifest.get("mode_keys")
        mode_identities_raw = manifest.get("mode_identities")
        normalization_raw = manifest.get("normalization_h")
        if (
            not isinstance(identity, dict)
            or not isinstance(mode_keys_raw, list)
            or not isinstance(mode_identities_raw, list)
            or not isinstance(normalization_raw, list)
            or len(mode_keys_raw) != expected_mode_count
            or len(mode_identities_raw) != expected_mode_count
            or len(normalization_raw) != expected_mode_count
            or len(expected_mode_keys) != expected_mode_count
            or len(expected_normalization_h) != expected_mode_count
        ):
            raise ValueError("saved surface donor mode metadata is incomplete")
        self.identity = MappingProxyType(dict(identity))
        self.mode_keys = tuple(
            (int(row[0]), str(row[1]), int(row[2]), int(row[3]), str(row[4]))
            for row in mode_keys_raw
        )
        frozen_expected_keys = tuple(tuple(row) for row in expected_mode_keys)
        if self.mode_keys != frozen_expected_keys or len(set(self.mode_keys)) != expected_mode_count:
            raise ValueError("saved surface donor mode key/order differs from the current inventory")
        self.normalization_h = np.asarray(normalization_raw, dtype=np.float64)
        expected_h = np.asarray(expected_normalization_h, dtype=np.float64)
        if (
            self.normalization_h.shape != (expected_mode_count,)
            or not np.isfinite(self.normalization_h).all()
            or np.any(self.normalization_h <= 0.0)
            or not np.array_equal(self.normalization_h, expected_h)
        ):
            raise ValueError("saved surface donor H inventory differs from the current modes")
        self.normalization_h.flags.writeable = False
        self.mode_identities = tuple(
            MappingProxyType(row) if isinstance(row, dict) else row
            for row in mode_identities_raw
        )
        if any(not isinstance(row, Mapping) for row in self.mode_identities):
            raise ValueError("saved surface donor mode identity row is invalid")
        for index, (key, identity_row, h_value) in enumerate(
            zip(self.mode_keys, self.mode_identities, self.normalization_h, strict=True)
        ):
            missing = _MODE_IDENTITY_FIELDS.difference(identity_row)
            if missing:
                raise ValueError(
                    "saved surface donor mode identity is incomplete: "
                    + ",".join(sorted(missing))
                )
            identity_key = (
                index,
                str(identity_row["side"]),
                int(identity_row["m"]),
                int(identity_row["n"]),
                str(identity_row["polarization"]),
            )
            denominator = identity_row["projection_denominator"]
            if isinstance(denominator, Mapping):
                denominator = complex(denominator["real"], denominator["imag"])
            else:
                denominator = complex(denominator)
            if (
                key != identity_key
                or identity_row.get("mode_index") != index
                or denominator != complex(float(h_value), 0.0)
            ):
                raise ValueError("saved surface donor mode identity/key/H differs from its metadata")
        if identity_validator is not None:
            identity_validator(identity, self.mode_identities)

        slave_array = np.unique(np.asarray(slave_rows, dtype=np.int64).reshape(-1))
        if slave_array.size and (
            int(slave_array[0]) < self._owned_start
            or int(slave_array[-1]) >= self._owned_end
        ):
            raise ValueError("saved surface donor slave rows are outside local ownership")
        self._slave_rows = slave_array
        self._slave_rows.flags.writeable = False
        started = time.perf_counter()
        file_stat = self.path.stat()
        if file_stat.st_size != expected_committed_bytes:
            raise IOError("saved surface donor has bytes outside the exact committed prefix")
        self._path_identity = self._stat_identity(file_stat)
        digest = hashlib.sha256()
        carrier_payload_digest = hashlib.sha256()
        with self.path.open("rb") as stream:
            for index, expected_h_value in enumerate(self.normalization_h):
                self._offsets[index] = stream.tell()
                frame_started = time.perf_counter()
                frame = _surface_frame_arrays(
                    stream,
                    expected_index=index,
                    expected_h=float(expected_h_value),
                    digest=digest,
                    stream_end=expected_committed_bytes,
                    max_frame_bytes=max_frame_bytes,
                )
                self._validation_frame_read_hash_seconds += max(
                    0.0, time.perf_counter() - frame_started
                )
                (
                    _mode_index,
                    _h_value,
                    coupling_rows,
                    coupling_values,
                    projection_rows,
                    projection_values,
                    _frame_bytes,
                ) = frame
                classification_started = time.perf_counter()
                for rows, values in (
                    (coupling_rows, coupling_values),
                    (projection_rows, projection_values),
                ):
                    if rows.size and (
                        int(rows[0]) < self._owned_start
                        or int(rows[-1]) >= self._owned_end
                        or int(rows[-1]) >= self._global_rows
                    ):
                        raise ValueError("saved surface donor row exceeds the current FE ownership")
                    if self._slave_rows.size and rows.size:
                        positions = np.searchsorted(self._slave_rows, rows)
                        matched = positions < self._slave_rows.size
                        if np.any(matched):
                            valid = np.flatnonzero(matched)
                            matched[valid] = self._slave_rows[positions[valid]] == rows[valid]
                        if np.any(matched):
                            raise ValueError("saved surface donor contains a current MPC slave row")
                self._validation_classification_seconds += max(
                    0.0, time.perf_counter() - classification_started
                )
                if frame_observer is not None:
                    observer_started = time.perf_counter()
                    frame_observer(
                        index,
                        self.mode_identities[index],
                        coupling_rows,
                        coupling_values,
                        projection_rows,
                        projection_values,
                    )
                    self._validation_frame_observer_seconds += max(
                        0.0, time.perf_counter() - observer_started
                    )
                    payload_digest_started = time.perf_counter()
                    carrier_payload_digest.update(
                        json.dumps(
                            self.mode_keys[index],
                            separators=(",", ":"),
                            ensure_ascii=True,
                        ).encode()
                    )
                    carrier_payload_digest.update(
                        np.asarray([_h_value], dtype=np.float64).tobytes()
                    )
                    for name, array in (
                        ("coupling_rows", coupling_rows),
                        ("coupling_values", coupling_values),
                        ("projection_rows", projection_rows),
                        ("projection_values", projection_values),
                    ):
                        contiguous = np.ascontiguousarray(array)
                        carrier_payload_digest.update(name.encode("ascii"))
                        carrier_payload_digest.update(contiguous.dtype.str.encode("ascii"))
                        carrier_payload_digest.update(
                            np.asarray(contiguous.shape, dtype=np.int64).tobytes()
                        )
                        carrier_payload_digest.update(memoryview(contiguous).cast("B"))
                    self._validation_payload_digest_seconds += max(
                        0.0, time.perf_counter() - payload_digest_started
                    )
                self._offsets[index + 1] = stream.tell()
                self._max_frame_bytes_observed = max(
                    self._max_frame_bytes_observed, int(_frame_bytes)
                )
                if progress_callback is not None and (
                    index + 1 == expected_mode_count
                    or (index + 1) % progress_interval == 0
                ):
                    progress_callback(
                        {
                            "phase": "task41_b0_saved_donor_validation",
                            "status": "PROGRESS",
                            "completed_modes": index + 1,
                            "total_modes": expected_mode_count,
                            "validated_bytes": int(stream.tell()),
                        }
                    )
            if stream.tell() != expected_committed_bytes:
                raise IOError("saved surface donor end offset differs from committed bytes")
        if digest.hexdigest() != expected_prefix_sha256:
            raise IOError("saved surface donor committed prefix SHA-256 differs from the contract")
        after = self.path.stat()
        if self._stat_identity(after) != self._path_identity:
            raise IOError("saved surface donor changed during sequential validation")
        if any(
            self._stat_identity(item.stat()) != metadata_identities[item]
            for item in metadata_paths
        ):
            raise IOError("saved surface donor metadata changed during sequential validation")
        if self._offsets[0] != 0 or self._offsets[-1] != expected_committed_bytes:
            raise IOError("saved surface donor offset inventory is incomplete")
        self._validation_seconds = max(0.0, time.perf_counter() - started)
        self.manifest_sha256 = manifest_sha
        self.manifest_file_bytes = int(self.manifest_path.stat().st_size)
        self.checkpoint_sha256 = checkpoint_sha
        self.identity_sha256 = expected_identity_sha256
        self.committed_prefix_sha256 = digest.hexdigest()
        self._carrier_payload_sha256 = carrier_payload_digest.hexdigest()
        self.committed_bytes = expected_committed_bytes
        self.offset_index_facts: Mapping[str, Any] | None = None
        if self._offset_index_path is not None:
            index_path = self._offset_index_path
            metadata_path = Path(str(index_path) + ".json")
            if index_path.exists() or index_path.is_symlink() or metadata_path.exists() or metadata_path.is_symlink():
                raise FileExistsError("saved surface donor offset index path already exists")
            index_path.parent.mkdir(parents=True, exist_ok=True)
            encoded_offsets = np.ascontiguousarray(self._offsets, dtype="<i8")
            offset_digest = hashlib.sha256(memoryview(encoded_offsets).cast("B")).hexdigest()
            temporary = index_path.with_name(
                f"{index_path.name}.tmp.{os.getpid()}.{time.time_ns()}"
            )
            with temporary.open("xb") as stream:
                stream.write(memoryview(encoded_offsets).cast("B"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, index_path)
            _fsync_directory(index_path.parent)
            offset_facts = {
                "schema": "task41.p0.b0.saved_surface_offset_index.v1",
                "offset_index_path": str(index_path),
                "offset_index_metadata_path": str(metadata_path),
                "offset_index_sha256": offset_digest,
                "offset_count": int(encoded_offsets.size),
                "offset_dtype": "<i8",
                "offset_index_bytes": int(encoded_offsets.nbytes),
                "mode_count": expected_mode_count,
                "committed_bytes": expected_committed_bytes,
                "committed_prefix_sha256": self.committed_prefix_sha256,
                "manifest_sha256": manifest_sha,
                "checkpoint_sha256": checkpoint_sha,
                "identity_sha256": expected_identity_sha256,
                "complete_stream_validation_preceded_persistence": True,
            }
            _atomic_json(metadata_path, offset_facts)
            self.offset_index_facts = MappingProxyType(offset_facts)
        self.validation_facts = MappingProxyType(
            {
                "status": "VALIDATED_READ_ONLY",
                "manifest_sha256": manifest_sha,
                "checkpoint_sha256": checkpoint_sha,
                "identity_sha256": expected_identity_sha256,
                "committed_prefix_sha256": self.committed_prefix_sha256,
                "carrier_payload_rows_values_sha256": self._carrier_payload_sha256,
                "committed_bytes": expected_committed_bytes,
                "mode_count": expected_mode_count,
                "validation_sweeps": 1,
                "validation_seconds": self._validation_seconds,
                "validation_frame_read_parse_prefix_hash_seconds": (
                    self._validation_frame_read_hash_seconds
                ),
                "validation_row_classification_seconds": (
                    self._validation_classification_seconds
                ),
                "validation_frame_observer_seconds": self._validation_frame_observer_seconds,
                "validation_carrier_payload_digest_seconds": (
                    self._validation_payload_digest_seconds
                ),
                "offset_index_dtype": str(self._offsets.dtype),
                "offset_index_bytes": int(self._offsets.nbytes),
                "persisted_offset_index": (
                    None if self.offset_index_facts is None
                    else dict(self.offset_index_facts)
                ),
                "max_frame_bytes_bound": max_frame_bytes,
                "max_frame_bytes_observed": self._max_frame_bytes_observed,
                "payload_retained_in_memory": False,
            }
        )

    @staticmethod
    def _stat_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
        return (
            int(value.st_dev),
            int(value.st_ino),
            int(value.st_size),
            int(value.st_mtime_ns),
            int(value.st_ctime_ns),
        )

    @property
    def mode_count(self) -> int:
        return self._expected_mode_count

    @property
    def global_rows(self) -> int:
        return self._global_rows

    @property
    def ownership_range(self) -> tuple[int, int]:
        return self._owned_start, self._owned_end

    @property
    def slave_rows(self) -> np.ndarray:
        return self._slave_rows

    def _assert_unchanged(self) -> None:
        if self._stat_identity(self.path.stat()) != self._path_identity:
            raise IOError("validated saved surface donor changed after validation")

    @property
    def carrier_payload_rows_values_sha256(self) -> str:
        """Return the exact legacy payload digest without replaying the carrier."""
        self._assert_unchanged()
        return self._carrier_payload_sha256

    def _read_entry(self, stream, index: int) -> FullspaceDtnModeFunctional:
        started = time.perf_counter()
        start = int(self._offsets[index])
        if stream.tell() != start:
            stream.seek(start)
        frame = _surface_frame_arrays(
            stream,
            expected_index=index,
            expected_h=float(self.normalization_h[index]),
            stream_end=self.committed_bytes,
            max_frame_bytes=self.max_frame_bytes,
        )
        if stream.tell() != int(self._offsets[index + 1]):
            raise IOError("saved surface donor frame changed after validation")
        self._read_modes += 1
        self._read_bytes += int(frame[-1])
        self._read_frame_parse_seconds += max(0.0, time.perf_counter() - started)
        return FullspaceDtnModeFunctional(
            mode_key=self.mode_keys[index],
            coupling_rows=frame[2],
            coupling_values=frame[3],
            projection_rows=frame[4],
            projection_values=frame[5],
            normalization_h=frame[1],
            mode_identity=self.mode_identities[index],
        )

    def iter_entries(self, start: int = 0, stop: int | None = None):
        stop = self.mode_count if stop is None else int(stop)
        start = int(start)
        if not 0 <= start <= stop <= self.mode_count:
            raise IndexError("saved surface donor mode range is invalid")
        self._assert_unchanged()
        if start == 0 and stop == self.mode_count:
            self._read_sweeps += 1
        with self.path.open("rb") as stream:
            for index in range(start, stop):
                yield self._read_entry(stream, index)

    def read_batch(self, start: int, stop: int) -> tuple[FullspaceDtnModeFunctional, ...]:
        if int(stop) - int(start) > self.max_batch_modes:
            raise ValueError("saved surface donor read batch exceeds its configured memory bound")
        self._read_batches += 1
        return tuple(self.iter_entries(start, stop))

    @property
    def audit(self) -> Mapping[str, Any]:
        return MappingProxyType(
            {
                **dict(self.validation_facts),
                "complete_stream_sweeps_after_validation": int(self._read_sweeps),
                "bounded_read_batches_after_validation": int(self._read_batches),
                "read_modes_after_validation": int(self._read_modes),
                "read_bytes_after_validation": int(self._read_bytes),
                "read_frame_parse_seconds_after_validation": (
                    self._read_frame_parse_seconds
                ),
                "max_frame_bytes_bound": self.max_frame_bytes,
                "max_frame_bytes_observed": self._max_frame_bytes_observed,
                "source_path": str(self.path),
            }
        )


class _FileBackedSurfaceEntries(Sequence[Any]):
    def __init__(self, source: ReadOnlySurfaceFunctionalSource) -> None:
        self._source = source

    def __len__(self) -> int:
        return self._source.mode_count

    def __iter__(self):
        return self._source.iter_entries()

    def __getitem__(self, index):
        if isinstance(index, slice):
            start, stop, step = index.indices(len(self))
            if len(range(start, stop, step)) > self._source.max_batch_modes:
                raise ValueError("file-backed carrier slicing exceeds its configured batch bound")
            if step == 1:
                return self._source.read_batch(start, stop)
            return tuple(self._source.read_batch(i, i + 1)[0] for i in range(start, stop, step))
        resolved = int(index)
        if resolved < 0:
            resolved += len(self)
        if not 0 <= resolved < len(self):
            raise IndexError(index)
        return self._source.read_batch(resolved, resolved + 1)[0]


class _ResumableSurfaceFunctionalStream:
    """Append committed production frames and validate a saved prefix once."""

    def __init__(
        self,
        path: str | Path,
        *,
        identity: Mapping[str, Any],
        modes: Sequence[Any],
        mode_identities: Sequence[Mapping[str, Any]],
        normalization_h: Sequence[float],
    ) -> None:
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.checkpoint_path = Path(str(self.path) + ".checkpoint.json")
        self.manifest_path = Path(str(self.path) + ".manifest.json")
        self.identity = dict(identity)
        self.identity_sha256 = hashlib.sha256(_canonical_json_bytes(self.identity)).hexdigest()
        self.modes = tuple(modes)
        self.mode_identities = tuple(dict(row) for row in mode_identities)
        self.normalization_h = tuple(float(value) for value in normalization_h)
        if not self.modes or len(self.modes) != len(self.mode_identities) or len(self.modes) != len(self.normalization_h):
            raise ValueError("resumable surface stream mode inventory is incomplete")
        self.mode_keys = tuple(
            (int(index), str(mode.side), int(mode.m), int(mode.n), str(mode.polarization))
            for index, mode in enumerate(self.modes)
        )
        self.manifest_payload = {
            "schema": _RESUMABLE_SURFACE_STREAM_SCHEMA,
            "identity": self.identity,
            "identity_sha256": self.identity_sha256,
            "mode_keys": self.mode_keys,
            "mode_identities": self.mode_identities,
            "normalization_h": self.normalization_h,
        }
        self.manifest_bytes = _canonical_json_bytes(self.manifest_payload) + b"\n"
        self.manifest_sha256 = hashlib.sha256(self.manifest_bytes).hexdigest()
        self._digest = hashlib.sha256()
        self._committed_mode_count = 0
        self._committed_bytes = 0
        self._peak_component_cache_bytes = 0

    def _write_manifest_once(self) -> None:
        if self.manifest_path.exists():
            if self.manifest_path.read_bytes() != self.manifest_bytes:
                raise ValueError("resumable surface stream manifest identity changed")
            return
        temporary = self.manifest_path.with_name(
            f"{self.manifest_path.name}.tmp.{os.getpid()}.{time.time_ns()}"
        )
        with temporary.open("xb") as stream:
            stream.write(self.manifest_bytes)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, self.manifest_path)
        _fsync_directory(self.path.parent)

    def _checkpoint_payload(self) -> dict[str, Any]:
        return {
            "schema": _RESUMABLE_SURFACE_STREAM_SCHEMA,
            "identity_sha256": self.identity_sha256,
            "manifest_sha256": self.manifest_sha256,
            "expected_mode_count": len(self.modes),
            "committed_mode_count": self._committed_mode_count,
            "committed_bytes": self._committed_bytes,
            "committed_prefix_sha256": self._digest.copy().hexdigest(),
            "peak_component_cache_unique_backing_bytes": self._peak_component_cache_bytes,
        }

    def _publish_checkpoint(self) -> None:
        _atomic_json(self.checkpoint_path, self._checkpoint_payload())

    def open(self) -> tuple[list[FullspaceDtnModeFunctional], int]:
        self._write_manifest_once()
        raw_exists = self.path.exists()
        checkpoint_exists = self.checkpoint_path.exists()
        if raw_exists != checkpoint_exists:
            raise ValueError("resumable surface stream data/checkpoint pair is incomplete")
        if not raw_exists:
            with self.path.open("xb") as stream:
                stream.flush()
                os.fsync(stream.fileno())
            _fsync_directory(self.path.parent)
            self._publish_checkpoint()
            return [], 0
        try:
            checkpoint = json.loads(self.checkpoint_path.read_text(encoding="ascii"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("resumable surface stream checkpoint is unreadable") from error
        if (
            not isinstance(checkpoint, dict)
            or checkpoint.get("schema") != _RESUMABLE_SURFACE_STREAM_SCHEMA
            or checkpoint.get("identity_sha256") != self.identity_sha256
            or checkpoint.get("manifest_sha256") != self.manifest_sha256
            or checkpoint.get("expected_mode_count") != len(self.modes)
        ):
            raise ValueError("resumable surface stream checkpoint identity changed")
        count = checkpoint.get("committed_mode_count")
        committed_bytes = checkpoint.get("committed_bytes")
        if (
            type(count) is not int
            or not 0 <= count <= len(self.modes)
            or type(committed_bytes) is not int
            or committed_bytes < 0
            or type(checkpoint.get("peak_component_cache_unique_backing_bytes")) is not int
            or checkpoint["peak_component_cache_unique_backing_bytes"] < 0
        ):
            raise ValueError("resumable surface stream checkpoint counters are invalid")
        size = self.path.stat().st_size
        if size != committed_bytes:
            raise IOError(
                "resumable surface stream has bytes outside its committed prefix; evidence retained"
            )
        entries: list[FullspaceDtnModeFunctional] = []
        with self.path.open("rb") as stream:
            for index in range(count):
                frame = _surface_frame_arrays(
                    stream,
                    expected_index=index,
                    expected_h=self.normalization_h[index],
                    digest=self._digest,
                )
                mode_index, h_value, coupling_rows, coupling_values, projection_rows, projection_values, _length = frame
                entries.append(
                    FullspaceDtnModeFunctional(
                        mode_key=self.mode_keys[mode_index],
                        coupling_rows=coupling_rows,
                        coupling_values=coupling_values,
                        projection_rows=projection_rows,
                        projection_values=projection_values,
                        normalization_h=h_value,
                        mode_identity=self.mode_identities[mode_index],
                    )
                )
            if stream.tell() != committed_bytes:
                raise IOError("resumable surface stream committed byte count differs from its frames")
        if self._digest.hexdigest() != checkpoint.get("committed_prefix_sha256"):
            raise IOError("resumable surface stream committed prefix SHA-256 changed")
        self._committed_mode_count = count
        self._committed_bytes = committed_bytes
        self._peak_component_cache_bytes = checkpoint[
            "peak_component_cache_unique_backing_bytes"
        ]
        return entries, self._peak_component_cache_bytes

    def append(
        self,
        entry: FullspaceDtnModeFunctional,
        *,
        peak_component_cache_bytes: int,
    ) -> None:
        index = self._committed_mode_count
        if index >= len(self.modes) or tuple(entry.mode_key) != self.mode_keys[index]:
            raise ValueError("resumable surface append differs from the next frozen mode")
        h_value = float(entry.normalization_h)
        if not np.isfinite(h_value) or h_value != self.normalization_h[index]:
            raise ValueError("resumable surface append H differs from the frozen mode inventory")
        if type(peak_component_cache_bytes) is not int or peak_component_cache_bytes < 0:
            raise ValueError("resumable surface component-cache peak is invalid")
        arrays = []
        for rows, values in (
            (entry.coupling_rows, entry.coupling_values),
            (entry.projection_rows, entry.projection_values),
        ):
            row_array = np.asarray(rows).reshape(-1)
            value_array = np.asarray(values, dtype=np.complex128).reshape(-1)
            if (
                row_array.dtype.kind not in "iu"
                or row_array.size != value_array.size
                or not np.isfinite(value_array).all()
                or (row_array.size and (int(row_array.min()) < 0 or int(row_array.max()) > np.iinfo(np.int32).max))
                or (row_array.size > 1 and np.any(row_array[1:] <= row_array[:-1]))
            ):
                raise ValueError("resumable surface append has invalid sorted sparse arrays")
            arrays.extend((np.ascontiguousarray(row_array, dtype="<i4"), np.ascontiguousarray(value_array, dtype="<c16")))
        header = _SURFACE_FUNCTIONAL_FRAME.pack(index, len(arrays[0]), len(arrays[2]), h_value)
        next_digest = self._digest.copy()
        next_digest.update(header)
        for array in arrays:
            next_digest.update(memoryview(array).cast("B"))
        frame_bytes = _SURFACE_FUNCTIONAL_FRAME.size + sum(array.nbytes for array in arrays)
        with self.path.open("ab") as stream:
            stream.write(header)
            for array in arrays:
                stream.write(memoryview(array).cast("B"))
            stream.flush()
            os.fsync(stream.fileno())
        self._digest = next_digest
        self._committed_mode_count += 1
        self._committed_bytes += frame_bytes
        self._peak_component_cache_bytes = max(
            self._peak_component_cache_bytes, peak_component_cache_bytes
        )
        self._publish_checkpoint()


def classify_port_mode(mode: Any) -> str:
    """Classify one current-tree port mode using the existing mode flags.

    ``near_rayleigh`` is deliberately checked first.  Thus a mode that is
    technically propagating but lies inside the frozen Rayleigh warning band
    is recorded as ``near-cutoff`` rather than silently treated as ordinary
    propagation.
    """

    if bool(mode.rayleigh_warning):
        return "near-cutoff"
    if bool(mode.propagating):
        return "propagating"
    return "evanescent"


def _mode_identity(index: int, mode: Any, cfg: Any, denominator: float) -> dict[str, Any]:
    from .dtn_port_3d import _traction_vector

    return {
        "schema": "fullspace-dtn.mode.v1",
        "mode_index": int(index),
        "side": str(mode.side),
        "m": int(mode.m),
        "n": int(mode.n),
        "polarization": str(mode.polarization),
        "alpha": complex(mode.alpha),
        "gamma": complex(mode.gamma),
        "beta": complex(mode.beta),
        "k_vector": tuple(complex(value) for value in mode.k_vector),
        "e_vector": tuple(complex(value) for value in mode.e_vector),
        "h_vector": tuple(complex(value) for value in mode.h_vector),
        "refractive_index": complex(mode.refractive_index),
        "vertical_sign": int(mode.vertical_sign),
        "electric_tangential_norm_sq": float(mode.electric_tangential_norm_sq),
        "power_per_unit_amplitude": float(mode.power_per_unit_amplitude),
        "propagating": bool(mode.propagating),
        "rayleigh_warning": bool(mode.rayleigh_warning),
        "classification": classify_port_mode(mode),
        "rayleigh_tolerance": float(cfg.diffraction_rayleigh_tol),
        "projection_denominator": float(denominator),
        "traction_vector": tuple(
            complex(value) for value in _traction_vector(mode, cfg)
        ),
    }


def build_ordered_mode_manifest(
    modes: Sequence[Any], cfg: Any
) -> tuple[tuple[Mapping[str, Any], ...], bytes, str]:
    """Return the ordered physical mode manifest and its content hash."""

    from .dtn_port_3d import _mode_projection_denominator

    if not modes:
        raise ValueError("the dynamic DtN inventory must contain at least one mode")
    rows: list[Mapping[str, Any]] = []
    for index, mode in enumerate(modes):
        denominator = _mode_projection_denominator(mode, cfg)
        if not np.isfinite(denominator) or denominator <= 0.0:
            raise ValueError("DtN projection denominator H must be finite and positive")
        rows.append(_mode_identity(index, mode, cfg, denominator))
    payload = {
        "schema": FULLSPACE_DTN_MANIFEST_SCHEMA,
        "profile": FULLSPACE_DTN_PROFILE,
        "mode_count": len(rows),
        "modes": rows,
    }
    encoded = _canonical_json_bytes(payload)
    return tuple(rows), encoded, hashlib.sha256(encoded).hexdigest()


def build_dynamic_mode_inventory(
    cfg: Any,
) -> tuple[tuple[Any, ...], tuple[Mapping[str, Any], ...], str]:
    """Resolve modes from the current physical configuration and hash them."""

    from ..common.modes_3d import outgoing_port_modes_3d

    modes = tuple(outgoing_port_modes_3d(cfg))
    manifest, _encoded, digest = build_ordered_mode_manifest(modes, cfg)
    return modes, manifest, digest


def _sparse_entries(
    rows: Any,
    values: Any,
    *,
    owned_start: int,
    owned_end: int,
) -> tuple[np.ndarray, np.ndarray]:
    row_array = np.asarray(rows, dtype=PETSc.IntType).reshape(-1)
    value_array = np.asarray(values, dtype=np.complex128).reshape(-1)
    if row_array.shape != value_array.shape:
        raise ValueError("DtN sparse rows and values must have matching shapes")
    if row_array.size:
        if int(row_array.min()) < owned_start or int(row_array.max()) >= owned_end:
            raise ValueError("DtN sparse rows must be locally owned")
        order = np.argsort(row_array, kind="stable")
        row_array = row_array[order]
        value_array = value_array[order]
        if np.any(row_array[1:] == row_array[:-1]):
            raise ValueError("DtN sparse rows must be unique")
    if not np.all(np.isfinite(value_array)):
        raise ValueError("DtN sparse values must be finite")
    return _readonly(row_array, np.dtype(PETSc.IntType)), _readonly(
        value_array, np.dtype(np.complex128)
    )


@dataclass(frozen=True)
class FullspaceDtnModeFunctional:
    """One owner-local coupling/projection pair and its explicit H weight."""

    mode_key: tuple[Any, ...]
    coupling_rows: np.ndarray
    coupling_values: np.ndarray
    projection_rows: np.ndarray
    projection_values: np.ndarray
    normalization_h: float
    mode_identity: Mapping[str, Any]


class FullspaceDtnCarrier:
    """Immutable dynamic sparse carrier with no explicit C or D matrix."""

    def __init__(
        self,
        entries: Sequence[FullspaceDtnModeFunctional],
        *,
        global_rows: int,
        ownership_range: tuple[int, int],
        slave_rows: Any = (),
        batch_size: int = FULLSPACE_DTN_BATCH_SIZE,
        comm: MPI.Intracomm | None = None,
        surface_source: ReadOnlySurfaceFunctionalSource | None = None,
    ) -> None:
        self._comm = MPI.COMM_SELF if comm is None else comm
        self._global_rows = int(global_rows)
        self._owned_start, self._owned_end = map(int, ownership_range)
        if self._global_rows <= 0 or not 0 <= self._owned_start <= self._owned_end:
            raise ValueError("DtN carrier row identity is invalid")
        if self._owned_end > self._global_rows:
            raise ValueError("DtN carrier ownership exceeds global rows")
        if int(batch_size) <= 0:
            raise ValueError("DtN modal batch size must be positive")
        self._batch_size = int(batch_size)
        self._surface_source = surface_source
        normalized: list[FullspaceDtnModeFunctional] = []
        seen_keys: set[tuple[Any, ...]] = set()
        seen_identity: set[bytes] = set()
        manifest_rows: list[Mapping[str, Any]] = []
        slave_array = np.unique(np.asarray(slave_rows, dtype=PETSc.IntType).reshape(-1))
        if slave_array.size and (
            int(slave_array.min()) < self._owned_start
            or int(slave_array.max()) >= self._owned_end
        ):
            raise ValueError("DtN slave rows must be locally owned")
        self._slave_rows = _readonly(slave_array, np.dtype(PETSc.IntType))
        if surface_source is None:
            for index, item in enumerate(entries):
                if not isinstance(item, FullspaceDtnModeFunctional):
                    raise TypeError("DtN carrier entries have an invalid type")
                if item.mode_key in seen_keys:
                    raise ValueError("DtN mode keys are not unique")
                seen_keys.add(item.mode_key)
                identity = dict(item.mode_identity)
                if _MODE_IDENTITY_FIELDS.difference(identity):
                    missing = ",".join(sorted(_MODE_IDENTITY_FIELDS.difference(identity)))
                    raise ValueError(f"DtN mode identity is missing fields: {missing}")
                if identity.get("mode_index") != index:
                    raise ValueError("DtN mode indices must follow carrier order")
                identity_bytes = _canonical_json_bytes(identity)
                if identity_bytes in seen_identity:
                    raise ValueError("DtN mode identities are not unique")
                seen_identity.add(identity_bytes)
                coupling_rows, coupling_values = _sparse_entries(
                    item.coupling_rows,
                    item.coupling_values,
                    owned_start=self._owned_start,
                    owned_end=self._owned_end,
                )
                projection_rows, projection_values = _sparse_entries(
                    item.projection_rows,
                    item.projection_values,
                    owned_start=self._owned_start,
                    owned_end=self._owned_end,
                )
                h = float(item.normalization_h)
                if not np.isfinite(h) or h <= 0.0:
                    raise ValueError("DtN normalization H must be finite and positive")
                normalized.append(
                    FullspaceDtnModeFunctional(
                        tuple(item.mode_key),
                        coupling_rows,
                        coupling_values,
                        projection_rows,
                        projection_values,
                        h,
                        MappingProxyType(identity),
                    )
                )
                manifest_rows.append(identity)
            if not normalized:
                raise ValueError("DtN carrier requires at least one dynamic mode")
            manifest = {
                "schema": FULLSPACE_DTN_MANIFEST_SCHEMA,
                "profile": FULLSPACE_DTN_PROFILE,
                "mode_count": len(manifest_rows),
                "modes": manifest_rows,
            }
            self._entries = tuple(normalized)
            self._mode_manifest = _canonical_json_bytes(manifest)
            self._mode_manifest_sha256 = hashlib.sha256(self._mode_manifest).hexdigest()
            self._mode_keys = tuple(tuple(item.mode_key) for item in normalized)
            self._mode_identities = tuple(item.mode_identity for item in normalized)
            self._normalization_h = np.asarray(
                [item.normalization_h for item in normalized], dtype=np.float64
            )
            self._retained_numeric_bytes = int(self._slave_rows.nbytes)
            for item in self._entries:
                if np.intersect1d(item.coupling_rows, self._slave_rows).size:
                    raise ValueError("DtN coupling functional intersects a local slave row")
                if np.intersect1d(item.projection_rows, self._slave_rows).size:
                    raise ValueError("DtN projection functional intersects a local slave row")
                self._retained_numeric_bytes += int(
                    item.coupling_rows.nbytes
                    + item.coupling_values.nbytes
                    + item.projection_rows.nbytes
                    + item.projection_values.nbytes
                    + np.dtype(np.float64).itemsize
                )
            self._retained_identity_bytes = len(self._mode_manifest)
        else:
            if not isinstance(surface_source, ReadOnlySurfaceFunctionalSource):
                raise TypeError("file-backed DtN carrier requires a validated surface source")
            if (
                surface_source.global_rows != self._global_rows
                or surface_source.ownership_range != (self._owned_start, self._owned_end)
                or surface_source.max_batch_modes < self._batch_size
                or not np.array_equal(surface_source.slave_rows, self._slave_rows)
            ):
                raise ValueError("validated surface source FE/MPC row layout differs from the carrier")
            self._entries = _FileBackedSurfaceEntries(surface_source)
            self._mode_keys = surface_source.mode_keys
            self._mode_identities = surface_source.mode_identities
            self._normalization_h = surface_source.normalization_h
            manifest_payload = {
                "schema": FULLSPACE_DTN_MANIFEST_SCHEMA,
                "profile": FULLSPACE_DTN_PROFILE,
                "mode_count": len(self._mode_identities),
                "modes": self._mode_identities,
            }
            self._mode_manifest = _canonical_json_bytes(manifest_payload)
            self._mode_manifest_sha256 = hashlib.sha256(self._mode_manifest).hexdigest()
            self._retained_numeric_bytes = int(
                self._slave_rows.nbytes
                + surface_source._offsets.nbytes
                + surface_source.normalization_h.nbytes
            )
            self._retained_identity_bytes = sum(
                len(_canonical_json_bytes(row)) for row in self._mode_identities
            )
        self._retained_numeric_global_sum = int(
            self._comm.allreduce(self._retained_numeric_bytes, op=MPI.SUM)
        )
        self._retained_numeric_global_max = int(
            self._comm.allreduce(self._retained_numeric_bytes, op=MPI.MAX)
        )

    @property
    def entries(self) -> Sequence[FullspaceDtnModeFunctional]:
        return self._entries

    @property
    def mode_keys(self) -> tuple[tuple[Any, ...], ...]:
        return self._mode_keys

    @property
    def mode_identities(self) -> tuple[Mapping[str, Any], ...]:
        return self._mode_identities

    @property
    def normalization_h(self) -> np.ndarray:
        view = self._normalization_h.view()
        view.flags.writeable = False
        return view

    @property
    def surface_source(self) -> ReadOnlySurfaceFunctionalSource | None:
        return self._surface_source

    def entry_batch(self, start: int, stop: int) -> tuple[FullspaceDtnModeFunctional, ...]:
        if self._surface_source is not None:
            return self._surface_source.read_batch(start, stop)
        return self._entries[start:stop]

    @property
    def mode_manifest_bytes(self) -> bytes:
        if self._mode_manifest is None:
            raise RuntimeError("DtN mode manifest is unavailable")
        return self._mode_manifest

    @property
    def mode_manifest_sha256(self) -> str:
        return self._mode_manifest_sha256

    @property
    def global_rows(self) -> int:
        return self._global_rows

    @property
    def ownership_range(self) -> tuple[int, int]:
        return self._owned_start, self._owned_end

    @property
    def batch_size(self) -> int:
        return self._batch_size

    @property
    def comm(self) -> MPI.Intracomm:
        return self._comm

    @property
    def retained_numeric_bytes(self) -> int:
        return self._retained_numeric_bytes

    @property
    def slave_rows(self) -> np.ndarray:
        return self._slave_rows

    @property
    def audit(self) -> Mapping[str, Any]:
        mode_count = len(self._entries)
        h_values = self._normalization_h
        result = {
                "schema": "fullspace-dtn.carrier.v1",
                "profile": FULLSPACE_DTN_PROFILE,
                "mode_count": mode_count,
                "batch_size": self._batch_size,
                "batch_count": (mode_count + self._batch_size - 1) // self._batch_size,
                "mode_manifest_sha256": self._mode_manifest_sha256,
                "normalization": "explicit_diagonal_projection_denominator_H",
                "normalization_nonidentity": bool(
                    np.any(np.abs(h_values - 1.0) > 1.0e-14)
                ),
                "normalization_h_min": float(np.min(h_values)),
                "normalization_h_max": float(np.max(h_values)),
                "retained_numeric_bytes_local": self._retained_numeric_bytes,
                "retained_numeric_bytes_global_sum": self._retained_numeric_global_sum,
                "retained_numeric_bytes_global_max": self._retained_numeric_global_max,
                "retained_identity_bytes": self._retained_identity_bytes,
                "owner_local_surface_functionals": True,
                "slave_rows_local": int(self._slave_rows.size),
                "slave_functional_rows_local": 0,
                "slave_functional_rows_global": 0,
                "numeric_allgather": False,
                "explicit_c_matrix_count": 0,
                "explicit_d_matrix_count": 0,
                "global_aij_materialized": False,
                "global_schur_materialized": False,
                "trace_matrix_materialized": False,
                "ksp_created": False,
                "pde_solved": False,
            }
        if self._surface_source is not None:
            result["storage_kind"] = "validated_file_backed_read_only"
            result["saved_source"] = dict(self._surface_source.audit)
            result["saved_source_manifest_sha256"] = self._surface_source.manifest_sha256
        else:
            result["storage_kind"] = "resident_arrays"
        return MappingProxyType(result)


class FullspaceDtnAction:
    """PETSc MatPython wrapper around the bounded forward DtN action."""

    def __init__(self, carrier: FullspaceDtnCarrier, *, comm: MPI.Intracomm) -> None:
        self.carrier = carrier
        self.comm = comm
        self._local_modal = np.empty(carrier.batch_size, dtype=np.complex128)
        self._global_modal = np.empty_like(self._local_modal)
        owned = carrier.ownership_range[1] - carrier.ownership_range[0]
        self._matrix: PETSc.Mat | None = PETSc.Mat().createPython(
            ((owned, carrier.global_rows), (owned, carrier.global_rows)),
            context=self,
            comm=comm,
        )
        self._matrix.setUp()
        self._apply_count = 0
        self._modal_allreduce_count = 0
        self._apply_modal_allreduce_count = 0
        self._recovery_modal_allreduce_count = 0
        self._destroyed = False
        self._work_bytes = int(self._local_modal.nbytes + self._global_modal.nbytes)
        self._work_global_sum = int(self.comm.allreduce(self._work_bytes, op=MPI.SUM))
        self._work_global_max = int(self.comm.allreduce(self._work_bytes, op=MPI.MAX))

    @property
    def matrix(self) -> PETSc.Mat:
        if self._matrix is None:
            raise RuntimeError("DtN action has been destroyed")
        return self._matrix

    def _vector_values(self, vector: PETSc.Vec, *, writable: bool) -> np.ndarray:
        start, end = self.carrier.ownership_range
        values = np.asarray(
            vector.getArray() if writable else vector.getArray(readonly=True),
            dtype=np.complex128,
        )
        if (
            vector.getSize() != self.carrier.global_rows
            or tuple(map(int, vector.getOwnershipRange())) != (start, end)
            or values.size != end - start
        ):
            raise ValueError("DtN vector has an incompatible global/owned layout")
        return values

    def _modal_batch(
        self,
        source_values: np.ndarray,
        batch_start: int,
        entries: Sequence[FullspaceDtnModeFunctional],
    ) -> np.ndarray:
        start, _end = self.carrier.ownership_range
        count = len(entries)
        local = self._local_modal[:count]
        global_values = self._global_modal[:count]
        local.fill(0.0)
        for offset, item in enumerate(entries):
            if item.projection_rows.size:
                local[offset] = np.dot(
                    item.projection_values,
                    source_values[item.projection_rows - start],
                )
        self.comm.Allreduce(local, global_values, op=MPI.SUM)
        self._modal_allreduce_count += 1
        return global_values

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        if self._destroyed:
            raise RuntimeError("DtN action has been destroyed")
        source_values = self._vector_values(source, writable=False)
        target_values = self._vector_values(target, writable=True)
        target_values.fill(0.0)
        for batch_start in range(0, len(self.carrier.entries), self.carrier.batch_size):
            batch_stop = min(
                batch_start + self.carrier.batch_size, len(self.carrier.entries)
            )
            entries = self.carrier.entry_batch(batch_start, batch_stop)
            modal = self._modal_batch(source_values, batch_start, entries)
            self._apply_modal_allreduce_count += 1
            start, _end = self.carrier.ownership_range
            for offset, item in enumerate(entries):
                if item.coupling_rows.size:
                    target_values[item.coupling_rows - start] += (
                        modal[offset] / item.normalization_h * item.coupling_values
                    )
        self._apply_count += 1

    def mult(
        self,
        _matrix: PETSc.Mat,
        source: PETSc.Vec,
        target: PETSc.Vec,
    ) -> None:
        self.apply(source, target)

    def recover_auxiliary(self, source: PETSc.Vec) -> np.ndarray:
        """Recover ``a_i = H_i^{-1} D_i u`` without a total-mode work buffer."""

        if self._destroyed:
            raise RuntimeError("DtN action has been destroyed")
        source_values = self._vector_values(source, writable=False)
        recovered = np.empty(len(self.carrier.entries), dtype=np.complex128)
        for batch_start in range(0, len(self.carrier.entries), self.carrier.batch_size):
            batch_stop = min(
                batch_start + self.carrier.batch_size, len(self.carrier.entries)
            )
            entries = self.carrier.entry_batch(batch_start, batch_stop)
            modal = self._modal_batch(source_values, batch_start, entries)
            self._recovery_modal_allreduce_count += 1
            for offset, item in enumerate(entries):
                recovered[batch_start + offset] = modal[offset] / item.normalization_h
        return recovered

    def compose_physical_rhs(
        self,
        base_incident_traction: PETSc.Vec,
        mode_amplitudes: Sequence[complex],
        target: PETSc.Vec,
    ) -> None:
        """Write ``base_incident_traction + C a`` using the retained carrier."""

        base_values = self._vector_values(base_incident_traction, writable=False)
        target_values = self._vector_values(target, writable=True)
        amplitudes = np.asarray(tuple(mode_amplitudes), dtype=np.complex128)
        if amplitudes.shape != (len(self.carrier.entries),) or not np.all(
            np.isfinite(amplitudes)
        ):
            raise ValueError("DtN RHS amplitudes have an incompatible layout")
        target_values[:] = base_values
        start, _end = self.carrier.ownership_range
        for batch_start in range(0, len(self.carrier.entries), self.carrier.batch_size):
            batch_stop = min(
                batch_start + self.carrier.batch_size, len(self.carrier.entries)
            )
            entries = self.carrier.entry_batch(batch_start, batch_stop)
            for offset, item in enumerate(entries):
                if item.coupling_rows.size:
                    target_values[item.coupling_rows - start] += (
                        amplitudes[batch_start + offset] * item.coupling_values
                    )

    def apply_modal_rhs(
        self, mode_amplitudes: Sequence[complex], target: PETSc.Vec
    ) -> None:
        target_values = self._vector_values(target, writable=True)
        amplitudes = np.asarray(tuple(mode_amplitudes), dtype=np.complex128)
        if amplitudes.shape != (len(self.carrier.entries),) or not np.all(
            np.isfinite(amplitudes)
        ):
            raise ValueError("DtN RHS amplitudes have an incompatible layout")
        target_values.fill(0.0)
        start, _end = self.carrier.ownership_range
        for batch_start in range(0, len(self.carrier.entries), self.carrier.batch_size):
            batch_stop = min(
                batch_start + self.carrier.batch_size, len(self.carrier.entries)
            )
            entries = self.carrier.entry_batch(batch_start, batch_stop)
            for offset, item in enumerate(entries):
                if item.coupling_rows.size:
                    target_values[item.coupling_rows - start] += (
                        amplitudes[batch_start + offset] * item.coupling_values
                    )

    @property
    def audit(self) -> Mapping[str, Any]:
        audit = dict(self.carrier.audit)
        audit.update(
            {
                "matrix_type": self.matrix.getType(),
                "apply_count": int(self._apply_count),
                "modal_allreduce_count": int(self._modal_allreduce_count),
                "apply_modal_allreduce_count": int(self._apply_modal_allreduce_count),
                "recovery_modal_allreduce_count": int(
                    self._recovery_modal_allreduce_count
                ),
                "modal_allreduce_count_per_apply": self.carrier.audit["batch_count"],
                "bounded_work_bytes_local": self._work_bytes,
                "bounded_work_bytes_global_sum": self._work_global_sum,
                "bounded_work_bytes_global_max": self._work_global_max,
                "bounded_work_scales_with": "fixed_modal_batch_size",
                "recovery_output_bytes": int(
                    len(self.carrier.entries) * np.dtype(np.complex128).itemsize
                ),
                "numeric_allgather": False,
                "explicit_c_matrix_count": 0,
                "explicit_d_matrix_count": 0,
            }
        )
        return MappingProxyType(audit)

    def destroy(self, _matrix: PETSc.Mat | None = None) -> None:
        if self._destroyed:
            return
        self._destroyed = True
        matrix = self._matrix
        self._matrix = None
        if matrix is not None:
            matrix.destroy()
        self._local_modal = np.empty(0, dtype=np.complex128)
        self._global_modal = np.empty(0, dtype=np.complex128)


def build_fullspace_dtn_action(
    carrier: FullspaceDtnCarrier,
    *,
    comm: MPI.Intracomm | None = None,
) -> FullspaceDtnAction:
    """Build the forward action from one validated dynamic carrier."""

    return FullspaceDtnAction(carrier, comm=carrier.comm if comm is None else comm)


def build_fullspace_dtn_carrier_from_validated_source(
    source: ReadOnlySurfaceFunctionalSource,
    mpc: Any,
    *,
    batch_size: int = FULLSPACE_DTN_BATCH_SIZE,
) -> FullspaceDtnCarrier:
    """Bind a previously validated immutable donor to the current FE row owner."""
    if not isinstance(source, ReadOnlySurfaceFunctionalSource):
        raise TypeError("saved surface carrier requires a validated read-only source")
    if mpc is None:
        raise ValueError("saved surface carrier requires the finalized current MPC")
    comm = mpc.function_space.mesh.comm
    if int(comm.Get_size()) != 1:
        raise ValueError("saved surface carrier reuse is qualified only for MPI1")
    index_map = mpc.function_space.dofmap.index_map
    owned_start = int(index_map.local_range[0])
    owned_end = owned_start + int(index_map.size_local)
    global_rows = int(index_map.size_global)
    if (source.global_rows, source.ownership_range) != (
        global_rows,
        (owned_start, owned_end),
    ):
        raise ValueError("saved surface donor global/owned FE row identity differs from current MPC")
    slaves = np.asarray(mpc.slaves, dtype=np.int32)
    owned_slaves = slaves[slaves < int(index_map.size_local)]
    slave_rows = np.asarray(index_map.local_to_global(owned_slaves), dtype=PETSc.IntType)
    result = FullspaceDtnCarrier(
        (),
        global_rows=global_rows,
        ownership_range=(owned_start, owned_end),
        slave_rows=slave_rows,
        batch_size=batch_size,
        comm=comm,
        surface_source=source,
    )
    result.phase_gauge = str(source.identity.get("phase_gauge", ""))
    result.physical_generator_manifest_sha256 = str(
        source.identity.get("ordered_mode_manifest_sha256", "")
    )
    first_identity = source.mode_identities[0]
    result.assembly_context_sha256 = str(first_identity.get("assembly_context_sha256", ""))
    result.donor_validation_facts = source.validation_facts
    return result


def iter_fullspace_dtn_functionals_from_surface(
    modes: Sequence[Any],
    surface_assemblers: Mapping[tuple[str, int], Any],
    mpc: Any,
    cfg: Any,
    *,
    phase_gauge: str = "global_z",
    assembly_context: Mapping[str, Any] | None = None,
    start_index: int = 0,
    stop_index: int | None = None,
    mode_indices: Sequence[int] | None = None,
    precomputed_mode_rows: Sequence[Mapping[str, Any]] | None = None,
    precomputed_physical_manifest_sha256: str | None = None,
    audit: dict[str, Any] | None = None,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
    progress_interval: int = FULLSPACE_DTN_PROGRESS_INTERVAL,
    initial_peak_component_cache_bytes: int = 0,
):
    """Yield production B/D/H functionals one ordered mode at a time.

    The two global support filters remain inside ``assemble_entries`` and
    ``_combine_owned_entries`` after MPC assembly. The iterator retains only
    the current component arrays (plus an immediately adjacent duplicate
    polarization when it shares a wavevector); callers may apply and discard
    each yielded functional before asking for the next one.
    """
    if mpc is None:
        raise ValueError("dynamic DtN surface iterator requires the finalized MPC")
    from .dtn_port_3d import _combine_owned_entries
    from .dtn_boundary_phase_gauge import (
        BOUNDARY_PLANE,
        assembly_projection_denominator,
        deep_frozen_identity,
        phase_gauge_descriptor,
        port_plane_z,
        validate_phase_gauge,
    )

    validate_phase_gauge(phase_gauge)
    if type(progress_interval) is not int or progress_interval < 1:
        raise ValueError("DtN carrier progress interval must be a positive integer")
    if type(initial_peak_component_cache_bytes) is not int or initial_peak_component_cache_bytes < 0:
        raise ValueError("initial DtN component-cache peak must be a nonnegative integer")
    if progress_callback is not None and not callable(progress_callback):
        raise TypeError("DtN carrier progress callback must be callable")
    modes = tuple(modes)
    if not modes:
        raise ValueError("dynamic DtN surface iterator requires a nonempty ordered mode table")
    start_index = int(start_index)
    stop_index = len(modes) if stop_index is None else int(stop_index)
    if not 0 <= start_index <= stop_index <= len(modes):
        raise ValueError("surface functional mode range is outside the ordered mode table")
    if mode_indices is None:
        selected_indices = tuple(range(start_index, stop_index))
    else:
        if start_index != 0 or stop_index != len(modes):
            raise ValueError("explicit mode_indices cannot be combined with a mode range")
        selected_indices = tuple(mode_indices)
        if not selected_indices:
            raise ValueError("explicit surface functional mode selection must be nonempty")
        if any(type(index) is not int for index in selected_indices):
            raise ValueError("explicit surface functional mode indices must be Python integers")
        if any(index < 0 or index >= len(modes) for index in selected_indices):
            raise ValueError("explicit surface functional mode index is outside the ordered mode table")
        if any(right <= left for left, right in zip(selected_indices, selected_indices[1:])):
            raise ValueError("explicit surface functional mode indices must be strictly increasing")
    if precomputed_mode_rows is None:
        if precomputed_physical_manifest_sha256 is not None:
            raise ValueError("a precomputed manifest SHA requires precomputed ordered mode rows")
        manifest_rows, _manifest_bytes, physical_manifest_sha = build_ordered_mode_manifest(modes, cfg)
    else:
        if precomputed_physical_manifest_sha256 is None:
            raise ValueError("precomputed ordered mode rows require their frozen manifest SHA")
        manifest_rows = tuple(precomputed_mode_rows)
        if len(manifest_rows) != len(modes):
            raise ValueError("precomputed ordered mode rows differ from the frozen mode table")
        manifest_payload = {
            "schema": FULLSPACE_DTN_MANIFEST_SCHEMA,
            "profile": FULLSPACE_DTN_PROFILE,
            "mode_count": len(manifest_rows),
            "modes": manifest_rows,
        }
        computed_manifest_sha = hashlib.sha256(_canonical_json_bytes(manifest_payload)).hexdigest()
        if computed_manifest_sha != str(precomputed_physical_manifest_sha256):
            raise ValueError("precomputed ordered mode rows do not match their frozen manifest SHA")
        for index, (mode, row) in enumerate(zip(modes, manifest_rows, strict=True)):
            if (
                int(row.get("mode_index", -1)) != index
                or str(row.get("side")) != str(mode.side)
                or int(row.get("m", 0)) != int(mode.m)
                or int(row.get("n", 0)) != int(mode.n)
                or str(row.get("polarization")) != str(mode.polarization)
            ):
                raise ValueError("precomputed mode row identity differs from the frozen mode table")
        physical_manifest_sha = computed_manifest_sha
    if phase_gauge == BOUNDARY_PLANE:
        required = {"schema", "source_sha256", "mesh", "cell_dofmap_sha256", "orientation",
                    "basix_coefficients", "MPC", "config_sha256", "gauss", "ABI"}
        if not isinstance(assembly_context, Mapping) or required.difference(assembly_context):
            raise ValueError("boundary-plane carrier requires a complete discrete/source assembly context")
        assembly_context = deep_frozen_identity(assembly_context)
        context_sha = hashlib.sha256(_canonical_json_bytes(assembly_context)).hexdigest()
        for mode_index in selected_indices:
            mode = modes[mode_index]
            expected_z = port_plane_z(mode, cfg)
            expected_tag = int(cfg.tags.z_max if mode.side == "top" else cfg.tags.z_min)
            for component in (0, 1):
                assembler = surface_assemblers[(mode.side, component)]
                if (getattr(assembler, "boundary_reference_z", None) != expected_z
                        or getattr(assembler, "quadrature_degree", None) != assembly_context["gauss"]["degree"]
                        or getattr(assembler, "boundary_tag", None) != expected_tag):
                    raise ValueError("surface assembler phase/tag/quadrature differs from boundary-plane context")
    elif assembly_context is not None:
        raise ValueError("assembly_context is reserved for explicit boundary-plane assembly")
    else:
        context_sha = None

    comm = mpc.function_space.mesh.comm
    index_map = mpc.function_space.dofmap.index_map
    owned_start = int(index_map.local_range[0])
    owned_end = owned_start + int(index_map.size_local)
    global_rows = int(index_map.size_global)
    def key_for(mode: Any):
        return (str(mode.side), int(mode.m), int(mode.n), complex(mode.alpha),
                complex(mode.gamma), complex(mode.k_vector[2]))

    stats = audit if audit is not None else {}
    peak_component_bytes = int(initial_peak_component_cache_bytes)
    emitted = 0
    combination_filter_totals = {
        name: {
            "mode_count": 0,
            "input_component_entry_count": 0,
            "coalesced_row_count_before_mask": 0,
            "rows_dropped_by_global_mask": 0,
            "retained_row_count": 0,
            "global_maximum_abs_max": 0.0,
            "global_cutoff_max": 0.0,
            "norm_before_squared_sum": 0.0,
            "norm_after_squared_sum": 0.0,
        }
        for name in ("projection", "coupling")
    }
    combination_filter_hashers = {
        name: hashlib.sha256() for name in ("projection", "coupling")
    }

    def record_combination_filter(name, detail, mode_index, rows, values):
        if audit is None:
            return
        total = combination_filter_totals[name]
        total["mode_count"] += 1
        total["input_component_entry_count"] += detail[
            "local_input_component_entry_count"
        ]
        total["coalesced_row_count_before_mask"] += detail[
            "local_coalesced_row_count_before_mask"
        ]
        total["rows_dropped_by_global_mask"] += detail[
            "local_rows_dropped_by_global_mask"
        ]
        total["retained_row_count"] += detail["local_retained_row_count"]
        total["global_maximum_abs_max"] = max(
            total["global_maximum_abs_max"], detail["global_maximum_abs"]
        )
        total["global_cutoff_max"] = max(
            total["global_cutoff_max"], detail["global_cutoff"]
        )
        total["norm_before_squared_sum"] += detail["local_norm_before_mask"] ** 2
        total["norm_after_squared_sum"] += detail["local_norm_after_mask"] ** 2
        hasher = combination_filter_hashers[name]
        hasher.update(np.asarray([mode_index], dtype="<i8").tobytes())
        hasher.update(np.ascontiguousarray(rows).tobytes())
        hasher.update(np.ascontiguousarray(values, dtype=np.complex128).tobytes())
    cached_key = None
    cached_components = None
    components = None
    functional = None
    progress_started = time.perf_counter()
    progress_cpu_started = time.process_time()

    def component_backing_bytes(component_pairs):
        owners = {}
        for pair in component_pairs:
            for component in pair:
                for array in component:
                    owner = array
                    while isinstance(getattr(owner, "base", None), np.ndarray):
                        owner = owner.base
                    owners[id(owner)] = int(owner.nbytes)
        return int(sum(owners.values()))

    def assemble_components(mode):
        first = surface_assemblers[(mode.side, 0)].assemble_entries(mode, mpc)
        second = surface_assemblers[(mode.side, 1)].assemble_entries(mode, mpc)
        return first, second

    try:
        for selection_position, index in enumerate(selected_indices):
            mode = modes[index]
            key = key_for(mode)
            if key != cached_key:
                # Drop every iterator-owned alias before generating the next
                # pair.  This bounds unique numeric backing independently of
                # whether a duplicate wavevector appears later in the table.
                components = None
                cached_components = None
                cached_key = None
                cached_components = assemble_components(mode)
                cached_key = key
            components = cached_components
            current_component_bytes = component_backing_bytes(cached_components or ())
            peak_component_bytes = max(peak_component_bytes, current_component_bytes)
            projection_audit: dict[str, Any] | None = {} if audit is not None else None
            projection_rows, projection_values = _combine_owned_entries(
                components,
                (mode.e_vector[0], mode.e_vector[1]),
                comm=comm,
                audit=projection_audit,
            )
            if projection_audit is not None:
                record_combination_filter(
                    "projection", projection_audit, index, projection_rows, projection_values
                )
            from .dtn_port_3d import _mode_projection_denominator, _traction_vector

            denominator = (
                assembly_projection_denominator(mode, cfg, phase_gauge)
                if phase_gauge == BOUNDARY_PLANE
                else _mode_projection_denominator(mode, cfg)
            )
            mode_identity = manifest_rows[index]
            if phase_gauge == BOUNDARY_PLANE:
                mode_identity = _mode_identity(index, mode, cfg, denominator)
                mode_identity.update({
                    "assembly_identity_schema": "task40extra.fullspace-dtn-plane-assembly.v1",
                    "physical_generator_manifest_sha256": physical_manifest_sha,
                    "assembly_context_sha256": context_sha,
                    "global_projection_denominator_diagnostic": manifest_rows[index]["projection_denominator"],
                    "phase_gauge": phase_gauge_descriptor(mode, cfg, phase_gauge),
                })
                mode_identity = deep_frozen_identity(mode_identity)
            traction = _traction_vector(mode, cfg)
            coupling_audit: dict[str, Any] | None = {} if audit is not None else None
            coupling_rows, coupling_values = _combine_owned_entries(
                components,
                (-traction[0], -traction[1]),
                comm=comm,
                audit=coupling_audit,
            )
            if coupling_audit is not None:
                record_combination_filter(
                    "coupling", coupling_audit, index, coupling_rows, coupling_values
                )
            functional = FullspaceDtnModeFunctional(
                mode_key=(int(index), str(mode.side), int(mode.m), int(mode.n), str(mode.polarization)),
                coupling_rows=coupling_rows,
                coupling_values=_readonly(coupling_values, np.dtype(np.complex128)),
                projection_rows=projection_rows,
                projection_values=_readonly(
                    np.conjugate(projection_values), np.dtype(np.complex128)
                ),
                normalization_h=float(denominator),
                mode_identity=mode_identity,
            )
            emitted += 1
            stats["peak_component_cache_unique_backing_bytes"] = int(peak_component_bytes)
            if progress_callback is not None and (
                emitted % progress_interval == 0 or emitted == len(selected_indices)
            ):
                progress_callback(
                    {
                        "phase": "dtn_carrier_mode",
                        "status": "PROGRESS",
                        "completed": int(emitted),
                        "total": int(len(selected_indices)),
                        "mode_index": int(index),
                        "side": str(mode.side),
                        "polarization": str(mode.polarization),
                        "throttle_interval": int(progress_interval),
                        "elapsed_seconds": max(0.0, time.perf_counter() - progress_started),
                        "process_cpu_seconds": max(0.0, time.process_time() - progress_cpu_started),
                    }
                )
            yield functional
            next_index = (
                selected_indices[selection_position + 1]
                if selection_position + 1 < len(selected_indices)
                else None
            )
            next_key = key_for(modes[next_index]) if next_index is not None else None
            if next_index != index + 1 or next_key != key:
                cached_key = None
                cached_components = None
            functional = None
            components = None
            del coupling_rows, coupling_values, projection_rows, projection_values
    finally:
        cached_key = None
        cached_components = None
        components = None
        functional = None
        stats.update({
            "mode_index_range": [start_index, stop_index],
            "selected_mode_indices": list(selected_indices),
            "yielded_mode_count": emitted,
            "peak_component_cache_unique_backing_bytes": int(peak_component_bytes),
            "current_component_cache_unique_backing_bytes": 0,
            "component_cache_max_live_wavevector_keys": 1,
            "component_cache_policy": "one current wavevector key; only adjacent duplicate polarizations are reused; key transition drops prior backing before assembly",
            "global_support_threshold_stages": [
                "component vectors after MPC assembly via _vec_nonzero_owned_entries",
                "weighted component combination via _combine_owned_entries",
            ],
            "raw_D_with_original_Hp": True,
            "assembly_context_sha256": context_sha,
            "physical_generator_manifest_sha256": physical_manifest_sha,
            "owned_range": [owned_start, owned_end],
            "global_rows": global_rows,
            "global_combination_filter_audit": {
                name: {
                    **combination_filter_totals[name],
                    "norm_before_mask": float(
                        np.sqrt(combination_filter_totals[name]["norm_before_squared_sum"])
                    ),
                    "norm_after_mask": float(
                        np.sqrt(combination_filter_totals[name]["norm_after_squared_sum"])
                    ),
                    "retained_stream_sha256": combination_filter_hashers[name].copy().hexdigest(),
                    "relative_tol": 1e-13,
                    "absolute_floor": 0.0,
                    "scope": "second production global combination mask after weighted component coalescing",
                }
                for name in ("projection", "coupling")
            },
        })


def _resumable_carrier_mode_identity(
    modes: Sequence[Any],
    cfg: Any,
    *,
    phase_gauge: str,
    assembly_context: Mapping[str, Any] | None,
    execution_identity: Mapping[str, Any],
    mode_rows: Sequence[Mapping[str, Any]],
    physical_manifest_sha256: str,
) -> tuple[tuple[Mapping[str, Any], ...], np.ndarray, str | None, dict[str, Any]]:
    from .dtn_boundary_phase_gauge import (
        BOUNDARY_PLANE,
        assembly_projection_denominator,
        deep_frozen_identity,
        phase_gauge_descriptor,
        validate_phase_gauge,
    )

    validate_phase_gauge(phase_gauge)
    external = dict(execution_identity)
    source_sha = str(external.get("source_sha", ""))
    input_sha = str(external.get("input_sha256", ""))
    staged_input_sha = str(external.get("staged_input_sha256", ""))
    window_sha = str(external.get("campaign_window_sha256", ""))
    surface_scope = external.get("surface_scope")
    twist_index = external.get("twist_index")
    if (
        len(source_sha) != 40
        or any(value not in "0123456789abcdef" for value in source_sha)
        or len(input_sha) != 64
        or any(value not in "0123456789abcdef" for value in input_sha)
        or len(staged_input_sha) != 64
        or any(value not in "0123456789abcdef" for value in staged_input_sha)
        or len(window_sha) != 64
        or any(value not in "0123456789abcdef" for value in window_sha)
        or surface_scope not in {"global", "local"}
        or (surface_scope == "global" and twist_index is not None)
        or (
            surface_scope == "local"
            and (type(twist_index) is not int or twist_index < 0)
        )
    ):
        raise ValueError("resumable carrier requires source/input/window and owner-scope identities")
    if phase_gauge != BOUNDARY_PLANE or not isinstance(assembly_context, Mapping):
        raise ValueError("resumable Task40 carrier requires the complete boundary-plane assembly context")
    required_context = {
        "schema", "source_sha256", "mesh", "cell_dofmap_sha256", "orientation",
        "basix_coefficients", "MPC", "config_sha256", "gauss", "ABI",
    }
    if required_context.difference(assembly_context):
        raise ValueError("resumable carrier assembly context omits mesh/MPC/orientation identity")
    frozen_context = deep_frozen_identity(assembly_context)
    context_sha = hashlib.sha256(_canonical_json_bytes(frozen_context)).hexdigest()
    mode_identities: list[Mapping[str, Any]] = []
    h_values = np.empty(len(modes), dtype=np.float64)
    for index, (mode, base_row) in enumerate(zip(modes, mode_rows, strict=True)):
        denominator = assembly_projection_denominator(mode, cfg, phase_gauge)
        h_values[index] = float(denominator)
        identity = _mode_identity(index, mode, cfg, denominator)
        identity.update({
            "assembly_identity_schema": "task40extra.fullspace-dtn-plane-assembly.v1",
            "physical_generator_manifest_sha256": physical_manifest_sha256,
            "assembly_context_sha256": context_sha,
            "global_projection_denominator_diagnostic": base_row["projection_denominator"],
            "phase_gauge": phase_gauge_descriptor(mode, cfg, phase_gauge),
        })
        mode_identities.append(deep_frozen_identity(identity))
    if not np.isfinite(h_values).all() or np.any(h_values <= 0.0):
        raise ValueError("resumable carrier H inventory is invalid")
    h_sha256 = hashlib.sha256(np.ascontiguousarray(h_values, dtype="<f8").tobytes()).hexdigest()
    physical_context = {
        "assembly_context_sha256": context_sha,
        "mesh": frozen_context["mesh"],
        "cell_dofmap_sha256": frozen_context["cell_dofmap_sha256"],
        "orientation": frozen_context["orientation"],
        "basix_coefficients": frozen_context["basix_coefficients"],
        "MPC": frozen_context["MPC"],
        "config_sha256": frozen_context["config_sha256"],
        "ABI": frozen_context["ABI"],
    }
    identity = {
        "schema": _RESUMABLE_SURFACE_STREAM_SCHEMA,
        "source_sha": source_sha,
        "input_sha256": input_sha,
        "staged_input_sha256": staged_input_sha,
        "campaign_window_sha256": window_sha,
        "execution_contract_sha256": external.get("execution_contract_sha256"),
        "surface_scope": surface_scope,
        "twist_index": twist_index,
        "twist": {
            "floquet_phase_x": getattr(cfg, "floquet_phase_x", None),
            "floquet_phase_y": getattr(cfg, "floquet_phase_y", None),
        },
        "phase_gauge": phase_gauge,
        "ordered_mode_manifest_sha256": physical_manifest_sha256,
        "normalization_h_sha256": h_sha256,
        "mode_count": len(modes),
        "mesh_mpc_orientation": physical_context,
    }
    _canonical_json_bytes(identity)
    return tuple(mode_identities), h_values, context_sha, identity


def build_fullspace_dtn_carrier_from_surface(
    modes: Sequence[Any],
    surface_assemblers: Mapping[tuple[str, int], Any],
    mpc: Any,
    cfg: Any,
    *,
    phase_gauge: str = "global_z",
    assembly_context: Mapping[str, Any] | None = None,
    persistence_path: str | Path | None = None,
    persistence_identity: Mapping[str, Any] | None = None,
    progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
    progress_interval: int = FULLSPACE_DTN_PROGRESS_INTERVAL,
) -> FullspaceDtnCarrier:
    """Build the cached carrier by consuming the same production iterator."""

    if mpc is None:
        raise ValueError("dynamic DtN surface carrier requires the finalized MPC")
    modes = tuple(modes)
    if (persistence_path is None) != (persistence_identity is None):
        raise ValueError("resumable surface carrier requires both a path and execution identity")
    iterator_audit: dict[str, Any] = {}
    if persistence_path is None:
        entries = tuple(iter_fullspace_dtn_functionals_from_surface(
            modes, surface_assemblers, mpc, cfg, phase_gauge=phase_gauge,
            assembly_context=assembly_context, audit=iterator_audit,
            progress_callback=progress_callback,
            progress_interval=progress_interval,
        ))
        physical_manifest_sha = iterator_audit["physical_generator_manifest_sha256"]
        context_sha = iterator_audit["assembly_context_sha256"]
        persistence_facts = None
    else:
        comm = mpc.function_space.mesh.comm
        if int(comm.Get_size()) != 1:
            raise ValueError("resumable Task40 surface stream is qualified only for MPI1")
        mode_rows, _mode_manifest_bytes, physical_manifest_sha = build_ordered_mode_manifest(modes, cfg)
        mode_identities, h_values, context_sha, stream_identity = _resumable_carrier_mode_identity(
            modes,
            cfg,
            phase_gauge=phase_gauge,
            assembly_context=assembly_context,
            execution_identity=persistence_identity,
            mode_rows=mode_rows,
            physical_manifest_sha256=physical_manifest_sha,
        )
        stream = _ResumableSurfaceFunctionalStream(
            persistence_path,
            identity=stream_identity,
            modes=modes,
            mode_identities=mode_identities,
            normalization_h=h_values,
        )
        entries, prefix_peak = stream.open()
        prefix_count = len(entries)
        if progress_callback is not None and prefix_count:
            progress_callback({
                "phase": "dtn_carrier_mode",
                "status": "PROGRESS",
                "completed": prefix_count,
                "total": len(modes),
                "generated_mode_count": prefix_count,
                "committed_mode_count": prefix_count,
                "committed_bytes": stream._committed_bytes,
                "resumed_committed_prefix": prefix_count,
                "progress_semantics": "durably_committed",
            })
        if prefix_count < len(modes):
            pending_generated_progress: dict[str, Any] | None = None

            def record_generated_progress(facts: Mapping[str, Any]) -> None:
                nonlocal pending_generated_progress
                pending_generated_progress = dict(facts)

            suffix = iter_fullspace_dtn_functionals_from_surface(
                modes,
                surface_assemblers,
                mpc,
                cfg,
                phase_gauge=phase_gauge,
                assembly_context=assembly_context,
                mode_indices=tuple(range(prefix_count, len(modes))),
                precomputed_mode_rows=mode_rows,
                precomputed_physical_manifest_sha256=physical_manifest_sha,
                audit=iterator_audit,
                progress_callback=(
                    record_generated_progress if progress_callback is not None else None
                ),
                progress_interval=progress_interval,
                initial_peak_component_cache_bytes=prefix_peak,
            )
            for entry in suffix:
                stream.append(
                    entry,
                    peak_component_cache_bytes=int(
                        iterator_audit.get("peak_component_cache_unique_backing_bytes", prefix_peak)
                    ),
                )
                entries.append(entry)
                if pending_generated_progress is not None and progress_callback is not None:
                    generated = prefix_count + int(
                        pending_generated_progress["completed"]
                    )
                    committed = int(stream._committed_mode_count)
                    progress_callback({
                        **pending_generated_progress,
                        "completed": committed,
                        "total": len(modes),
                        "generated_mode_count": generated,
                        "committed_mode_count": committed,
                        "committed_bytes": stream._committed_bytes,
                        "resumed_committed_prefix": prefix_count,
                        "progress_semantics": "durably_committed",
                    })
                    pending_generated_progress = None
        else:
            iterator_audit.update({
                "mode_index_range": [0, len(modes)],
                "selected_mode_indices": list(range(len(modes))),
                "yielded_mode_count": len(modes),
                "peak_component_cache_unique_backing_bytes": int(prefix_peak),
                "current_component_cache_unique_backing_bytes": 0,
                "physical_generator_manifest_sha256": physical_manifest_sha,
                "assembly_context_sha256": context_sha,
            })
        if len(entries) != len(modes):
            raise IOError("resumable surface stream did not produce the complete frozen mode inventory")
        entries = tuple(entries)
        physical_manifest_sha = iterator_audit.get(
            "physical_generator_manifest_sha256", physical_manifest_sha
        )
        context_sha = iterator_audit.get("assembly_context_sha256", context_sha)
        persistence_facts = {
            "path": str(stream.path),
            "checkpoint_path": str(stream.checkpoint_path),
            "manifest_sha256": stream.manifest_sha256,
            "identity_sha256": stream.identity_sha256,
            "resumed_prefix_mode_count": prefix_count,
            "committed_mode_count": stream._committed_mode_count,
            "committed_bytes": stream._committed_bytes,
            "committed_prefix_sha256": stream._digest.hexdigest(),
        }
    index_map = mpc.function_space.dofmap.index_map
    owned_start = int(index_map.local_range[0])
    owned_end = owned_start + int(index_map.size_local)
    global_rows = int(index_map.size_global)
    slaves = np.asarray(mpc.slaves, dtype=np.int32)
    owned_slaves = slaves[slaves < int(index_map.size_local)]
    slave_rows = np.asarray(index_map.local_to_global(owned_slaves), dtype=PETSc.IntType)
    result = FullspaceDtnCarrier(
        entries,
        global_rows=global_rows,
        ownership_range=(owned_start, owned_end),
        slave_rows=slave_rows,
        batch_size=FULLSPACE_DTN_BATCH_SIZE,
        comm=mpc.function_space.mesh.comm,
    )
    if persistence_facts is not None:
        result.persistence_facts = MappingProxyType(dict(persistence_facts))
    if phase_gauge == "boundary_plane":
        from .dtn_boundary_phase_gauge import deep_frozen_identity

        frozen_context = deep_frozen_identity(assembly_context)
        result.phase_gauge = phase_gauge
        result.physical_generator_manifest_sha256 = iterator_audit["physical_generator_manifest_sha256"]
        result.assembly_context = frozen_context
        result.assembly_context_sha256 = iterator_audit["assembly_context_sha256"]
        staging_arrays = [
            array for item in entries
            for array in (item.coupling_rows, item.coupling_values,
                          item.projection_rows, item.projection_values)
        ]
        retained_arrays = [
            array for item in result.entries
            for array in (item.coupling_rows, item.coupling_values,
                          item.projection_rows, item.projection_values)
        ]
        owners = {}
        for array in staging_arrays + retained_arrays:
            owner = array
            while isinstance(getattr(owner, "base", None), np.ndarray):
                owner = owner.base
            owners[id(owner)] = int(owner.nbytes)
        result.construction_numeric_inventory = MappingProxyType({
            "component_cache_current_unique_backing_bytes_after_build": int(
                iterator_audit["current_component_cache_unique_backing_bytes"]
            ),
            "component_cache_peak_unique_backing_bytes_during_build": int(
                iterator_audit["peak_component_cache_unique_backing_bytes"]
            ),
            "staging_functional_payload_with_aliases": sum(array.nbytes for array in staging_arrays),
            "retained_functional_payload_with_aliases": sum(array.nbytes for array in retained_arrays),
            "unique_named_numpy_backing_bytes_before_staging_release": int(sum(owners.values())),
            "scope": "component current and peak unique backing are reported separately; functional staging and retained carrier payload are measured at construction overlap; none is RSS/process-tree peak",
            "resource_authority": "external whole-tree gate required",
        })
    return result


__all__ = (
    "FULLSPACE_DTN_BATCH_SIZE",
    "FULLSPACE_DTN_PROGRESS_INTERVAL",
    "FULLSPACE_DTN_MANIFEST_SCHEMA",
    "FULLSPACE_DTN_PROFILE",
    "FullspaceDtnAction",
    "FullspaceDtnCarrier",
    "FullspaceDtnModeFunctional",
    "build_dynamic_mode_inventory",
    "build_fullspace_dtn_action",
    "build_fullspace_dtn_carrier_from_surface",
    "iter_fullspace_dtn_functionals_from_surface",
    "build_ordered_mode_manifest",
    "classify_port_mode",
)
