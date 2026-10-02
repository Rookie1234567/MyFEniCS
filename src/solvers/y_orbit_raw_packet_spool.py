"""Lossless current-mode observer spool; no assembly, cutoff, or qualification.

Artifacts use the caller's existing writer and resource-admission callback.
This module retains only compact descriptor records, never raw mode arrays.
"""
from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
import hashlib
import json
import math
import re

import numpy as np


OBSERVER_SCHEMA = "task40extra.dtn-raw-mode-observer.research.v1"
SPOOL_SCHEMA = "task40extra.lossless-raw-packet-spool.v1"
MODE_COUNTS = {None: 532, 0: 228, 1: 304}
RAW_FIELDS = ("raw_C", "raw_D", "after_component_mask_C", "after_component_mask_D")
PAIR_FIELDS = ("raw_component_0", "raw_component_1", "raw_C", "raw_D",
               "after_component_mask_C", "after_component_mask_D",
               "component_masked_entries_0", "component_masked_entries_1", "stored_C_sparse", "stored_D_sparse")
METADATA_FIELDS = (
    "schema", "local_mode_index", "original_mode_index", "original_mode_key", "original_mode_row",
    "physical_generator_manifest_sha256", "assembly_context_sha256", "assembly_context",
    "quotient_contract_sha256", "quotient_twist_index", "local_branch_index", "ownership_range",
    "component_masks", "combination_masks", "local_plane_H", "original_plane_H",
    "single_D_conjugation", "raw_vectors_destroyed_before_callback", "array_ownership",
)


def _profile_errors(packet, *, next_index, original_indices, direct_profile=None):
    """Pure observer metadata checks; no numerical array access."""
    direct = None
    if direct_profile is not None:
        from .y_orbit_direct_profile import direct_profile_metadata
        direct = direct_profile_metadata(direct_profile)
    K = direct.replication_count if direct is not None else 2
    counts = {None: 532, **{b: count for b, count in enumerate(direct.sector_port_counts)}} if direct else MODE_COUNTS
    errors = ["missing " + name for name in METADATA_FIELDS if name not in packet]
    index, original, twist = (packet.get(name) for name in
                             ("local_mode_index", "original_mode_index", "quotient_twist_index"))
    if packet.get("schema") != OBSERVER_SCHEMA:
        errors.append("unsupported observer schema")
    if type(index) is not int or index != next_index:
        errors.append("local indices must be unique contiguous integers")
    if type(original) is not int or not 0 <= original < 532 or original in original_indices:
        errors.append("original index is missing, duplicated, or out of range")
    if twist is not None and (type(twist) is not int or twist not in tuple(range(K))):
        errors.append("only global or two quotient twists are supported")
    count = counts.get(twist) if twist is None or type(twist) is int else None
    if count is not None and type(index) is int and index >= count:
        errors.append("packet exceeds the exact global/sector inventory")
    key = packet.get("original_mode_key")
    if (not isinstance(key, (tuple, list)) or len(key) != 4
            or key[0] not in ("top", "bottom") or type(key[1]) is not int or type(key[2]) is not int
            or not isinstance(key[3], str)):
        errors.append("complete original semantic key is required")
    if twist is None:
        if original != index or packet.get("local_branch_index") is not None or packet.get("quotient_contract_sha256") is not None:
            errors.append("global observer mapping must retain the original contiguous index")
    else:
        branch, key = packet.get("local_branch_index"), packet.get("original_mode_key")
        if type(branch) is not int or branch not in (0, 1):
            errors.append("local branch must be explicit 0 or 1")
        if not isinstance(key, (tuple, list)) or len(key) != 4 or type(key[2]) is not int:
            errors.append("complete original semantic key is required")
        elif type(twist) is int and twist in tuple(range(K)):
            if (key[2]-twist) % K or branch != ((key[2]-twist)//K) % 2:
                errors.append("original n and explicit twist/branch disagree")
        if not packet.get("quotient_contract_sha256"):
            errors.append("quotient contract hash is required")
    if packet.get("single_D_conjugation") is not True or packet.get("raw_vectors_destroyed_before_callback") is not True:
        errors.append("existing observer conjugation/lifecycle proof is required")
    ownership = packet.get("ownership_range")
    if (not isinstance(ownership, (tuple, list)) or len(ownership) != 2
            or any(type(value) is not int for value in ownership) or ownership[0] != 0
            or ownership[1] != ((direct.storage_rows if twist is None else direct.local_storage_rows)
                                if direct is not None else (17204 if twist is None else 8940))):
        errors.append("bounded MPI1 p4 owned storage is required")
    return errors


def _encode_metadata(value):
    """JSON codec with explicit reversible nonfinite diagnostic markers."""
    if isinstance(value, np.generic):
        return _encode_metadata(value.item())
    if isinstance(value, complex):
        return {"__raw_spool_complex__": [_encode_metadata(value.real), _encode_metadata(value.imag)]}
    if isinstance(value, float) and not math.isfinite(value):
        return {"__raw_spool_nonfinite__": "nan" if math.isnan(value) else ("inf" if value > 0 else "-inf")}
    if isinstance(value, Mapping):
        return {str(key): _encode_metadata(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode_metadata(item) for item in value]
    if isinstance(value, (str, bool, int, float)) or value is None:
        return value
    raise TypeError("observer metadata must not contain unbounded arrays or unsupported objects")


def _offset_inventory_errors(inventory, total_entries):
    """Fixed ten-pair layout; missing/reordered/overlapping ranges fail closed."""
    if type(total_entries) is not int or total_entries < 0:
        return ["invalid combined sparse length"]
    if not isinstance(inventory, list) or len(inventory) != len(PAIR_FIELDS):
        return ["exactly ten ordered sparse offset records are required"]
    errors, next_offset = [], 0
    for field, item in zip(PAIR_FIELDS, inventory):
        if not isinstance(item, dict) or item.get("field") != field:
            errors.append("missing or reordered field " + field)
            continue
        start, length = item.get("offset"), item.get("length")
        if type(start) is not int or type(length) is not int or length < 0:
            errors.append("invalid offset/length for " + field)
            continue
        if start != next_offset or start+length > total_entries:
            errors.append("overlap, gap, or out-of-range offset for " + field)
        next_offset = start+length
        if not isinstance(item.get("original_rows_dtype"), str):
            errors.append("original row dtype is missing for " + field)
    if next_offset != total_entries:
        errors.append("offset inventory does not cover the exact combined payload")
    return errors


def _decode_metadata(value):
    if isinstance(value, dict):
        if set(value) == {"__raw_spool_complex__"}:
            real, imaginary = value["__raw_spool_complex__"]
            return complex(_decode_metadata(real), _decode_metadata(imaginary))
        if set(value) == {"__raw_spool_nonfinite__"}:
            return float(value["__raw_spool_nonfinite__"])
        return {key: _decode_metadata(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_decode_metadata(item) for item in value]
    return value


def _metadata_finite(value):
    if isinstance(value, np.generic):
        return _metadata_finite(value.item())
    if isinstance(value, complex):
        return math.isfinite(value.real) and math.isfinite(value.imag)
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, Mapping):
        return all(_metadata_finite(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(_metadata_finite(item) for item in value)
    return True


def _file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _array_sha256(array):
    return hashlib.sha256(array.tobytes(order="C")).hexdigest()


class RawModeSpool:
    """Current-mode spool with caller-owned NPY writer and allocation gate.

    ``save_array(name, ndarray)`` returns path/file_sha256/shape/dtype and
    payload_bytes. Relative artifact paths resolve under ``root_directory``;
    this supports the runner's overall run_directory/arrays writer while
    descriptors live in run_directory/raw_global or raw_twist_b. Default
    root_directory is directory. ``allocation_gate(label, facts)`` uses the
    runner's matrix_payload_bytes/workspace_bytes/evidence_reserve_bytes keys.

    ``packets()`` requires a complete 532/228/304 packet inventory. It may
    expose complete nonfinite failure evidence, marked diagnostic-only;
    neither the spool nor its READY_UNQUALIFIED status qualifies raw ports.
    ``packet(index)`` also permits reading a recorded partial/failed packet.
    Returned sparse arrays are read-only mmaps and belong to the caller.
    """

    def __init__(self, directory, *, save_array, allocation_gate, root_directory=None, direct_profile=None):
        if not callable(save_array) or not callable(allocation_gate):
            raise TypeError("existing save_array and allocation_gate callbacks are required")
        self.directory = Path(directory).resolve()
        self.root_directory = Path(root_directory).resolve() if root_directory is not None else self.directory
        self.directory.relative_to(self.root_directory)
        self.save_array, self.allocation_gate = save_array, allocation_gate
        self.direct_profile = direct_profile
        if direct_profile is not None:
            from .y_orbit_direct_profile import direct_profile_metadata
            metadata = direct_profile_metadata(direct_profile)
            self._mode_counts = {None: 532, **dict(enumerate(metadata.sector_port_counts))}
            self._maximum_storage_rows = metadata.storage_rows
            self._direct_identity = metadata.identity()
        else:
            self._mode_counts, self._maximum_storage_rows, self._direct_identity = MODE_COUNTS, 17204, None
        self.manifest_path = self.directory / "raw_packet_manifest.json"
        if self.manifest_path.exists():
            raise ValueError("raw spool manifest already exists; use a fresh directory")
        self._records, self._original_indices = [], set()
        self._profile, self._identity, self._failure = None, None, None
        stem = re.sub(r"[^A-Za-z0-9_]", "_", self.directory.name)
        self._prefix = "raw_" + stem + "_" + hashlib.sha256(str(self.directory).encode()).hexdigest()[:8]
        self.allocation_gate("raw_spool_initialize", {"matrix_payload_bytes": 0, "workspace_bytes": 1 << 20,
                                                     "evidence_reserve_bytes": 8 << 20, "factor_count": 0})
        self.directory.mkdir(parents=True, exist_ok=True)
        self._write_manifest()

    def _write_json(self, path, payload):
        encoded = (json.dumps(payload, indent=2, allow_nan=False)+"\n").encode()
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("xb") as stream:
            stream.write(encoded)
        temporary.replace(path)
        return hashlib.sha256(encoded).hexdigest()

    def _write_manifest(self):
        expected = self._mode_counts.get(self._profile) if self._identity is not None else None
        complete = expected is not None and len(self._records) == expected
        finite = all(record["all_finite"] for record in self._records)
        status = ("FAILED_RAW_PACKET_SPOOL" if self._failure is not None else
                  "COMPLETE_RAW_FAILURE_DIAGNOSTIC_ONLY" if complete and not finite else
                  "READY_RAW_PACKETS_UNQUALIFIED" if complete else "PARTIAL_RAW_PACKET_SPOOL")
        self._write_json(self.manifest_path, {
            "schema": SPOOL_SCHEMA, "observer_schema": OBSERVER_SCHEMA, "status": status,
            **({"direct_profile_metadata": self._direct_identity} if self._direct_identity is not None else {}),
            "raw_port_qualified": False, "PDE_solved": False, "factor_count": 0, "official_results": False,
            "root_directory": str(self.root_directory), "expected_mode_count": expected,
            "recorded_mode_count": len(self._records), "all_finite": finite,
            "complete_finite_stream": complete and finite and self._failure is None,
            "frozen_stream_identity": self._identity, "records": self._records, "failure": self._failure,
            "lossless_rule": "every exact nonzero including NaN/Inf; no magnitude cutoff",
        })

    def _artifact_path(self, descriptor):
        path = Path(descriptor["path"])
        path = path.resolve() if path.is_absolute() else (self.root_directory/path).resolve()
        path.relative_to(self.root_directory)
        if not path.is_file():
            raise FileNotFoundError("caller artifact descriptor does not resolve below root_directory")
        return path

    def _save(self, name, array):
        descriptor = dict(self.save_array(self._prefix + "_" + name, array))
        required = {"path", "file_sha256", "shape", "dtype", "payload_bytes"}
        if required.difference(descriptor):
            raise ValueError("save_array must return the runner's complete NPY descriptor")
        path = self._artifact_path(descriptor)
        if (_file_sha256(path) != descriptor["file_sha256"] or tuple(descriptor["shape"]) != array.shape
                or descriptor["dtype"] != str(array.dtype) or descriptor["payload_bytes"] != array.nbytes):
            raise ValueError("save_array descriptor is not bound to the current exact array")
        finite = int(np.count_nonzero(np.isfinite(array)))
        descriptor.update(path=str(path.relative_to(self.root_directory)), array_sha256=_array_sha256(array),
                          finite_entries=finite, nonfinite_entries=int(array.size)-finite,
                          raw_failure_diagnostic_only=finite != int(array.size))
        return descriptor

    def _validate_pair(self, pair, n):
        rows, values = pair
        if (not isinstance(rows, np.ndarray) or not isinstance(values, np.ndarray)
                or rows.ndim != 1 or values.shape != rows.shape or rows.dtype.kind not in "iu"
                or values.dtype != np.dtype(np.complex128)
                or np.any(rows < 0) or np.any(rows >= n)
                or (len(rows) > 1 and np.any(rows[1:] <= rows[:-1]))):
            raise ValueError("sparse packet requires sorted unique integer rows and unchanged complex128 values")

    def observe(self, packet):
        """Capture this borrowed packet, including honest nonfinite evidence."""
        if self._failure is not None:
            raise RuntimeError("failed spool cannot accept more observer packets")
        admitted = False
        metadata = None
        artifacts, offsets = {}, []
        try:
            ownership = packet.get("ownership_range")
            n = ownership[1] if isinstance(ownership, (tuple, list)) and len(ownership) == 2 else self._maximum_storage_rows
            if type(n) is not int or not 0 < n <= self._maximum_storage_rows:
                n = self._maximum_storage_rows
            # Conservative current-mode sparse upper bound, including all four
            # existing masked pairs. This precedes extraction, copying, encoding,
            # and writes; no hidden conversion or dense all-mode cache occurs.
            payload_upper = 10*n*(8+16)
            self.allocation_gate("raw_spool_capture_mode_" + str(len(self._records)), {
                "matrix_payload_bytes": payload_upper, "workspace_bytes": payload_upper + (2 << 20),
                "evidence_reserve_bytes": 8 << 20, "factor_count": 0,
                "exact_nonzero_sparse_upper_bytes": payload_upper,
            })
            admitted = True
            metadata = {field: packet[field] for field in METADATA_FIELDS if field in packet}
            errors = _profile_errors(packet, next_index=len(self._records), original_indices=self._original_indices, direct_profile=self.direct_profile)
            if errors:
                raise ValueError("; ".join(errors))
            identity = {field: metadata[field] for field in (
                "physical_generator_manifest_sha256", "assembly_context_sha256", "quotient_contract_sha256",
                "quotient_twist_index", "ownership_range")}
            encoded_identity = _encode_metadata(identity)
            if self._identity is not None and encoded_identity != self._identity:
                raise ValueError("raw observer stream physical/context/twist/ownership identity changed")
            index = packet["local_mode_index"]
            components = packet["raw_components"]
            if len(components) != 2:
                raise ValueError("exactly two true raw components are required")
            current_pairs = []
            for field, vector in [("raw_component_0", components[0]), ("raw_component_1", components[1])] + [
                    (field, packet[field]) for field in RAW_FIELDS]:
                if not isinstance(vector, np.ndarray) or vector.shape != (n,) or vector.dtype != np.dtype(np.complex128):
                    raise ValueError("raw vectors must be the complete original complex128 ndarrays")
                rows = np.flatnonzero(vector != 0)
                values = vector[rows]
                current_pairs.append((rows, values))
            component_pairs = packet["component_masked_entries"]
            if len(component_pairs) != 2:
                raise ValueError("exactly two preserved masked component pairs are required")
            current_pairs.extend(component_pairs)
            current_pairs.extend((packet["stored_C_sparse"], packet["stored_D_sparse"]))
            total_entries = 0
            for field, pair in zip(PAIR_FIELDS, current_pairs, strict=True):
                self._validate_pair(pair, n)
                offsets.append({"field": field, "offset": total_entries, "length": len(pair[0]),
                                "original_rows_dtype": str(pair[0].dtype)})
                total_entries += len(pair[0])
            errors = _offset_inventory_errors(offsets, total_entries)
            if errors:
                raise ValueError("; ".join(errors))
            # Current extracted pairs are already visible in caller-tree RSS.
            # Admit the actual two complete concatenated arrays before copies.
            complete_payload_bytes = total_entries*(8+16)
            self.allocation_gate("raw_spool_concatenate_mode_" + str(index), {
                "matrix_payload_bytes": complete_payload_bytes,
                "workspace_bytes": complete_payload_bytes + (2 << 20),
                "evidence_reserve_bytes": 8 << 20, "factor_count": 0,
                "exact_combined_entries": total_entries, "sparse_pair_count": 10,
            })
            combined_rows = np.concatenate([pair[0] for pair in current_pairs], dtype=np.int64)
            combined_values = np.concatenate([pair[1] for pair in current_pairs], dtype=np.complex128)
            artifacts["rows"] = self._save(f"m{index:04d}_rows", combined_rows)
            artifacts["values"] = self._save(f"m{index:04d}_values", combined_values)
            all_finite = _metadata_finite(metadata) and artifacts["values"]["nonfinite_entries"] == 0
            descriptor_path = self.directory / f"packet_{index:04d}.json"
            descriptor = {"schema": SPOOL_SCHEMA, "metadata": _encode_metadata(metadata),
                          "sparse_payload": artifacts, "offset_inventory": offsets,
                          "all_finite": all_finite, "raw_failure_diagnostic_only": not all_finite}
            descriptor_sha = self._write_json(descriptor_path, descriptor)
            del combined_rows, combined_values, current_pairs, rows, values
            self._records.append({"local_mode_index": index, "original_mode_index": packet["original_mode_index"],
                                  "descriptor_path": str(descriptor_path.relative_to(self.root_directory)),
                                  "descriptor_sha256": descriptor_sha, "all_finite": all_finite})
            self._original_indices.add(packet["original_mode_index"])
            self._profile, self._identity = packet["quotient_twist_index"], encoded_identity
            self._write_manifest()
        except Exception as error:
            self._failure = {"exception_type": type(error).__name__, "exception": str(error),
                             "attempted_local_index": _encode_metadata(packet.get("local_mode_index")),
                             "allocation_admitted": admitted,
                             "partial_sparse_artifacts": artifacts, "offset_inventory": offsets}
            try:
                self._failure["metadata"] = _encode_metadata(metadata) if metadata else None
            except Exception as encoding_error:
                self._failure["metadata_encoding_failure"] = str(encoding_error)
            if admitted:
                self._write_manifest()
            raise

    def _load(self, descriptor):
        path = self._artifact_path(descriptor)
        if _file_sha256(path) != descriptor["file_sha256"]:
            raise ValueError("raw packet artifact file hash changed")
        array = np.load(path, mmap_mode="r", allow_pickle=False)
        if (array.dtype.hasobject or tuple(descriptor["shape"]) != array.shape
                or descriptor["dtype"] != str(array.dtype) or descriptor["payload_bytes"] != array.nbytes
                or _array_sha256(array) != descriptor["array_sha256"]):
            raise ValueError("raw packet array shape/dtype/content digest changed")
        return array

    def packet(self, index):
        """Read one recorded sparse observer packet for audit or folding."""
        if type(index) is not int or not 0 <= index < len(self._records):
            raise IndexError("raw packet index must name a recorded contiguous local mode")
        record = self._records[index]
        path = (self.root_directory/record["descriptor_path"]).resolve()
        path.relative_to(self.root_directory)
        self.allocation_gate("raw_spool_read_descriptor_" + str(index), {
            "matrix_payload_bytes": path.stat().st_size, "workspace_bytes": 2 << 20,
            "evidence_reserve_bytes": 8 << 20, "factor_count": 0})
        if _file_sha256(path) != record["descriptor_sha256"]:
            raise ValueError("raw packet JSON descriptor hash changed")
        descriptor = json.loads(path.read_text())
        sparse = descriptor["sparse_payload"]
        shape = sparse["rows"]["shape"]
        if len(shape) != 1 or shape != sparse["values"]["shape"]:
            raise ValueError("combined raw rows/values require the same one-dimensional shape")
        errors = _offset_inventory_errors(descriptor["offset_inventory"], shape[0])
        if errors:
            raise ValueError("; ".join(errors))
        payload = sum(int(sparse[side]["payload_bytes"]) for side in ("rows", "values"))
        self.allocation_gate("raw_spool_read_arrays_" + str(index), {
            "matrix_payload_bytes": payload, "workspace_bytes": payload + (2 << 20),
            "evidence_reserve_bytes": 8 << 20, "factor_count": 0})
        combined_rows, combined_values = self._load(sparse["rows"]), self._load(sparse["values"])
        if combined_rows.dtype != np.dtype(np.int64) or combined_values.dtype != np.dtype(np.complex128):
            raise ValueError("combined sparse artifacts must retain integer rows and complex128 values")
        slices = {}
        for item in descriptor["offset_inventory"]:
            start, end = item["offset"], item["offset"]+item["length"]
            slices[item["field"]] = combined_rows[start:end], combined_values[start:end]
        packet = _decode_metadata(descriptor["metadata"])
        packet["raw_components_sparse"] = tuple(slices[f"raw_component_{component}"] for component in (0, 1))
        for field in RAW_FIELDS:
            packet[field + "_sparse"] = slices[field]
        packet["component_masked_entries"] = tuple(slices[f"component_masked_entries_{component}"] for component in (0, 1))
        for field in ("stored_C_sparse", "stored_D_sparse"):
            packet[field] = slices[field]
        packet["raw_failure_diagnostic_only"] = descriptor["raw_failure_diagnostic_only"]
        errors = _profile_errors(packet, next_index=index, original_indices=set(), direct_profile=self.direct_profile)
        if errors or packet["original_mode_index"] != record["original_mode_index"]:
            raise ValueError("decoded raw packet metadata no longer matches its exact descriptor index")
        return packet

    def packets(self):
        """Yield exactly one current-mode sparse packet; no packet collection."""
        expected = self._mode_counts.get(self._profile) if self._identity is not None else None
        if expected is None or len(self._records) != expected:
            raise ValueError("raw audit stream is partial; exact 532/228/304 packet count is required")
        if self._failure is not None:
            raise ValueError("raw spool has a captured failure and cannot supply an audit-ready stream")
        for index in range(expected):
            yield self.packet(index)
