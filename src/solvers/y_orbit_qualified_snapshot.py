"""Read-only Q0--Q2 snapshot authority and public-constructor restoration.

Importing this module does not import the project, PETSc, MPI, UFL or a solver.
Only ``restore_bundle`` enters the later caller-supervised volume/JIT stage.
No surface assembly, coefficient reconstruction, factor or PDE solve occurs here.
"""
from __future__ import annotations

from collections.abc import Mapping
from contextlib import contextmanager
import hashlib
import importlib.metadata
import importlib.util
import json
import math
from pathlib import Path
import sys
from types import MappingProxyType

import numpy as np


AUTHORITY_RUN = "y_orbit_two_cell_p4_phi5_audit_attempt1"
AUTHORITY_HEAD = "35dd9e5c39939d14bbded98f288007aff4a08368"
AUTHORITY_HASHES = {
    "audit_report.json": "d0bade55828b8e842f240ad3eb8b5d79d9adfdeb06976ad5be8e0a8fb2aeb37f",
    "independent_checker.json": "e3afab9490fce0a19f3ac868dbecac73957ddb2da5d528c1086a57c5e2b86b0f",
    "artifact_manifest.json": "845bfa52ad674ddc33e470f8017321f74d8ebb6e9d9d946046bde45aef7e2681",
    "raw_global/raw_packet_manifest.json": "3ce030aaa056d819ce4ac4b4ca0d6ff359ceb92a719eef0736160cb14727b85d",
    "raw_twist_0/raw_packet_manifest.json": "aa602bff2b2330883dc74349e207d892e780e10e84d033bf1ed03c467ae5c98f",
    "raw_twist_1/raw_packet_manifest.json": "4ab019ac01c00f6c9807b8775f6855e06fe0c37a9a1b32d7a75292e0561fb52c",
}
PHYSICAL_MANIFEST = "4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951"
ARTIFACT_INVENTORY_SHA256 = "00655d1357f45545c1cbc0e40bfb561f4508684868211b44c16d90014f4db70f"
SPOOL_SCHEMA = "task40extra.lossless-raw-packet-spool.v1"
OBSERVER_SCHEMA = "task40extra.dtn-raw-mode-observer.research.v1"
MODE_COUNTS = {None: 532, 0: 228, 1: 304}
PAIR_FIELDS = ("raw_component_0", "raw_component_1", "raw_C", "raw_D",
               "after_component_mask_C", "after_component_mask_D",
               "component_masked_entries_0", "component_masked_entries_1",
               "stored_C_sparse", "stored_D_sparse")
EVIDENCE_RESERVE_BYTES = 128 << 20
SCHEMA = "task40extra.qualified-quotient-snapshot-restoration.v1"


def _freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({str(k): _freeze(v) for k, v in value.items()})
    if isinstance(value, (tuple, list)):
        return tuple(_freeze(v) for v in value)
    return value


def _jsonable(value):
    # Exactly the fullspace_dtn_action canonical identity codec, including -0.0.
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        if not math.isfinite(value.real) or not math.isfinite(value.imag):
            raise ValueError("nonfinite complex identity")
        return {"real": float(value.real), "imag": float(value.imag)}
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("nonfinite identity")
        return float(value)
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in sorted(value.items(), key=lambda p: str(p[0]))}
    if isinstance(value, (tuple, list, np.ndarray)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (str, bool, int)) or value is None:
        return value
    raise TypeError("unsupported identity object")


def _canonical(value):
    return json.dumps(_jsonable(value), ensure_ascii=True, allow_nan=False,
                      separators=(",", ":"), sort_keys=True).encode("ascii")


def _decode_metadata(value):
    # RawModeSpool's reversible codec. Nonfinite markers are decoded, then refused.
    if isinstance(value, dict):
        if set(value) == {"__raw_spool_complex__"}:
            real, imaginary = value["__raw_spool_complex__"]
            return complex(_decode_metadata(real), _decode_metadata(imaginary))
        if set(value) == {"__raw_spool_nonfinite__"}:
            return float(value["__raw_spool_nonfinite__"])
        return {k: _decode_metadata(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode_metadata(v) for v in value]
    return value


def _file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _signature(value):
    array = np.asarray(value)
    if array.dtype.hasobject:
        raise ValueError("object arrays are forbidden")
    digest = hashlib.sha256()
    for chunk in np.nditer(array, flags=["external_loop", "buffered", "zerosize_ok"],
                           order="C", buffersize=65536):
        digest.update(memoryview(np.ascontiguousarray(chunk)).cast("B"))
    return {"shape": tuple(array.shape), "dtype": str(array.dtype), "sha256": digest.hexdigest()}


def _equal(left, right):
    return _canonical(left) == _canonical(right)


def _bound(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("snapshot paths must be relative and confined")
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("snapshot artifact is missing or escapes authority root")
    return path


def _admit(gate, label, payload=0, workspace=0, **facts):
    if not callable(gate):
        raise TypeError("allocation_gate callback is required")
    gate(label, {"matrix_payload_bytes": int(payload), "workspace_bytes": int(workspace),
                 "evidence_reserve_bytes": EVIDENCE_RESERVE_BYTES, "factor_count": 0, **facts})


def _read_json(root, relative, gate, expected=None):
    path = _bound(root, relative)
    size = path.stat().st_size
    _admit(gate, "snapshot_json_" + str(relative), size, 6 * size + (2 << 20))
    if expected is not None and _file_sha(path) != expected:
        raise ValueError("frozen JSON hash changed: " + str(relative))
    # Reject duplicate keys as well as nonstandard JSON NaN/Inf.
    def unique_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate snapshot JSON key")
            result[key] = value
        return result
    def nonfinite(value):
        raise ValueError("nonfinite snapshot JSON constant: " + value)
    return json.loads(path.read_text(), object_pairs_hook=unique_pairs, parse_constant=nonfinite)


def _close_array(array):
    owner = array
    while isinstance(getattr(owner, "base", None), np.ndarray):
        owner = owner.base
    mmap = getattr(owner, "_mmap", None)
    if mmap is not None:
        mmap.close()


def _load_array(root, descriptor, gate, label):
    path = _bound(root, descriptor["path"])
    shape = descriptor["shape"]
    dtype = np.dtype(descriptor["dtype"])
    if (dtype.hasobject or not isinstance(shape, (tuple, list))
            or any(type(v) is not int or v < 0 for v in shape)):
        raise ValueError("invalid snapshot shape/dtype")
    payload = math.prod(shape) * dtype.itemsize
    if type(descriptor["payload_bytes"]) is not int or payload != descriptor["payload_bytes"]:
        raise ValueError("snapshot payload size does not match shape/dtype")
    _admit(gate, label, payload, payload + (2 << 20), mmap_mode="r")
    if _file_sha(path) != descriptor["file_sha256"]:
        raise ValueError("frozen NPY file hash changed")
    array = np.load(path, mmap_mode="r", allow_pickle=False)
    try:
        if array.shape != tuple(shape) or array.dtype != dtype or array.nbytes != payload:
            raise ValueError("NPY shape/dtype/payload changed")
        if "array_sha256" in descriptor and _signature(array)["sha256"] != descriptor["array_sha256"]:
            raise ValueError("NPY array content hash changed")
        if (descriptor.get("nonfinite_entries") != 0
                or descriptor.get("raw_failure_diagnostic_only") is not False
                or not np.isfinite(array).all()):
            raise ValueError("failure-diagnostic arrays cannot restore a qualified carrier")
        return array
    except Exception:
        _close_array(array)
        raise


class _FrozenRawReader:
    """The existing spool schema without RawModeSpool's write-on-construction."""

    def __init__(self, root, directory, twist, gate, *, manifest_sha):
        self.root, self.directory, self.twist, self.gate = root, directory, twist, gate
        self.manifest = _freeze(_read_json(root, directory + "/raw_packet_manifest.json", gate, manifest_sha))
        m = self.manifest
        expected = MODE_COUNTS[twist]
        if (m.get("schema") != SPOOL_SCHEMA or m.get("observer_schema") != OBSERVER_SCHEMA
                or m.get("status") != "READY_RAW_PACKETS_UNQUALIFIED"
                or m.get("complete_finite_stream") is not True or m.get("all_finite") is not True
                or m.get("failure") is not None or m.get("expected_mode_count") != expected
                or m.get("recorded_mode_count") != expected or len(m.get("records", ())) != expected
                or m.get("factor_count") != 0 or m.get("PDE_solved") is not False
                or m.get("raw_port_qualified") is not False):
            raise ValueError("exact complete finite frozen raw stream required")
        indices = set()
        for i, record in enumerate(m["records"]):
            original = record.get("original_mode_index")
            if (record.get("local_mode_index") != i or type(original) is not int
                    or not 0 <= original < 532 or original in indices or record.get("all_finite") is not True
                    or record.get("descriptor_path") != f"{directory}/packet_{i:04d}.json"):
                raise ValueError("raw stream exact index/descriptor inventory changed")
            indices.add(original)
        self.identity = m["frozen_stream_identity"]
        if (self.identity["quotient_twist_index"] != twist
                or self.identity["physical_generator_manifest_sha256"] != PHYSICAL_MANIFEST
                or tuple(self.identity["ownership_range"]) != (0, 17204 if twist is None else 8940)):
            raise ValueError("frozen stream profile changed")

    def descriptor(self, index):
        if type(index) is not int or not 0 <= index < MODE_COUNTS[self.twist]:
            raise IndexError("packet index must be a contiguous original local index")
        record = self.manifest["records"][index]
        d = _read_json(self.root, record["descriptor_path"], self.gate, record["descriptor_sha256"])
        if d.get("schema") != SPOOL_SCHEMA or d.get("all_finite") is not True or d.get("raw_failure_diagnostic_only") is not False:
            raise ValueError("diagnostic or invalid raw descriptor")
        p = _decode_metadata(d["metadata"])
        _canonical(p)  # Finite metadata gate after reversible nonfinite decoding.
        required = {"schema", "local_mode_index", "original_mode_index", "original_mode_key", "original_mode_row",
                    "physical_generator_manifest_sha256", "assembly_context_sha256", "assembly_context",
                    "quotient_contract_sha256", "quotient_twist_index", "local_branch_index", "ownership_range",
                    "component_masks", "combination_masks", "local_plane_H", "original_plane_H",
                    "single_D_conjugation", "raw_vectors_destroyed_before_callback", "array_ownership"}
        if (required.difference(p) or p["schema"] != OBSERVER_SCHEMA
                or type(p["local_mode_index"]) is not int or p["local_mode_index"] != index
                or type(p["original_mode_index"]) is not int
                or p["original_mode_index"] != record["original_mode_index"]
                or p["quotient_twist_index"] != self.twist or p["single_D_conjugation"] is not True
                or p["raw_vectors_destroyed_before_callback"] is not True
                or not _equal({k: p[k] for k in self.identity}, self.identity)
                or hashlib.sha256(_canonical(p["assembly_context"])).hexdigest() != p["assembly_context_sha256"]):
            raise ValueError("raw metadata/physical/context/lifecycle identity changed")
        key = p["original_mode_key"]
        if (not isinstance(key, list) or len(key) != 4 or key[0] not in ("top", "bottom")
                or type(key[1]) is not int or type(key[2]) is not int or not isinstance(key[3], str)):
            raise ValueError("complete original semantic key required")
        if self.twist is None:
            if p["original_mode_index"] != index or p["local_branch_index"] is not None or p["quotient_contract_sha256"] is not None:
                raise ValueError("global observer index must remain original")
        elif (type(p["quotient_twist_index"]) is not int or type(p["local_branch_index"]) is not int
              or (key[2] - self.twist) % 2 or p["local_branch_index"] != ((key[2] - self.twist)//2) % 2
              or not p["quotient_contract_sha256"]):
            raise ValueError("quotient twist/branch/original mode mapping changed")
        if not (p["local_plane_H"] > 0 and p["original_plane_H"] > 0):
            raise ValueError("H must be positive finite")
        sparse, offsets = d["sparse_payload"], d["offset_inventory"]
        shape = sparse["rows"]["shape"]
        if len(shape) != 1 or shape != sparse["values"]["shape"] or len(offsets) != 10:
            raise ValueError("exact ten-pair one-dimensional payload required")
        next_offset = 0
        for field, item in zip(PAIR_FIELDS, offsets, strict=True):
            if (item.get("field") != field or type(item.get("offset")) is not int
                    or type(item.get("length")) is not int or item["length"] < 0
                    or item["offset"] != next_offset or item["offset"] + item["length"] > shape[0]
                    or not isinstance(item.get("original_rows_dtype"), str)
                    or np.dtype(item["original_rows_dtype"]).kind not in "iu"):
                raise ValueError("ten sparse pairs overlap, have a gap or changed order/dtype")
            next_offset += item["length"]
        if next_offset != shape[0]:
            raise ValueError("ten pairs must cover complete raw payload")
        return p, d

    @contextmanager
    def packet(self, index):
        """Borrow one verified packet; its backing closes on context exit."""
        p, d = self.descriptor(index)
        rows = values = None
        try:
            rows = _load_array(self.root, d["sparse_payload"]["rows"], self.gate, f"snapshot_rows_{self.twist}_{index}")
            values = _load_array(self.root, d["sparse_payload"]["values"], self.gate, f"snapshot_values_{self.twist}_{index}")
            if rows.dtype != np.dtype(np.int64) or values.dtype != np.dtype(np.complex128):
                raise ValueError("spool must retain int64/complex128 combined storage")
            pairs = {}
            for item in d["offset_inventory"]:
                start, end = item["offset"], item["offset"] + item["length"]
                rr, vv = rows[start:end], values[start:end]
                if (rr.size and (rr[0] < 0 or rr[-1] >= p["ownership_range"][1]
                                  or np.any(rr[1:] <= rr[:-1]))):
                    raise ValueError("sparse rows must be sorted unique and locally owned")
                pairs[item["field"]] = rr, vv
            yield p, pairs
        finally:
            if rows is not None:
                _close_array(rows)
            if values is not None:
                _close_array(values)


def _source_environment_gate(old_source, new_source, old_env, new_env):
    if (old_source.get("head") != AUTHORITY_HEAD or old_source.get("dirty")
            or new_source.get("dirty") or new_source.get("branch") != "task40extra_dot_parallel_cloud"
            or old_source.get("branch") != new_source.get("branch") or not new_source.get("head")):
        raise ValueError("requires clean frozen source and clean own-branch candidate")
    old, new = old_source["files_sha256"], new_source["files_sha256"]
    # Only documentation may differ. This also binds DAT inputs, meshes,
    # retained binary evidence and other numerical files with uncommon suffixes.
    numerical = [name for name in old if not name.endswith(".md")]
    for name in numerical:
        if old[name] != new.get(name):
            raise ValueError("old numerical dependency changed/deleted: " + name)
    fields = ("python", "prefix", "modules", "petsc_scalar_type", "petsc_int_type", "petsc_version",
              "mpi_library", "qualification_manifest_sha256", "qualification_scope")
    for name in fields:
        if name not in old_env or name not in new_env or not _equal(old_env[name], new_env[name]):
            raise ValueError("frozen numerical environment changed: " + name)
    return {"old_head": old_source["head"], "new_head": new_source["head"],
            "unchanged_numerical_dependency_count": len(numerical),
            "old_source_inventory_sha256": hashlib.sha256(_canonical(old)).hexdigest(),
            "new_source_inventory_sha256": hashlib.sha256(_canonical(new)).hexdigest(),
            "added_paths": tuple(sorted(set(new)-set(old))), "environment_fields_equal": fields}


def _validate_supervision(summary, source):
    """The frozen audit's whole-tree/time/swap acceptance, metadata only."""
    launch = summary.get("launch_envelope", {})
    delta = summary.get("global_swap_activity", {}).get("delta", {})
    if (summary.get("classification") != "COMPLETED" or summary.get("leader_exit_code") != 0
            or not _equal(summary.get("source_state"), source)
            or summary.get("sampled_process_tree_swap_peak_bytes") != 0
            or summary.get("descendants_cleared") is not True
            or summary.get("process_tree_all_status_readable") is not True
            or summary.get("process_tree_all_identity_complete") is not True
            or not 0 < summary.get("sampled_process_tree_rss_peak_bytes", 0) < 3*1024**3//2
            or not 0 < summary.get("elapsed_seconds", 0) < 600
            or not 0 < launch.get("launch_cap_bytes", 0) <= 3*1024**3//2
            or delta.get("pswpin_pages") != 0 or delta.get("pswpout_pages") != 0):
        raise ValueError("frozen audit whole-tree/zero-swap/time supervision failed")


def _verify_historical_surface_files(context, allocation_gate):
    """Rehash historical primary kernels/C files without loading or rebuilding.

    The frozen generated-C identity remains historical. Matching these files
    neither qualifies a newly compiled volume kernel nor equates old/new JIT.
    Reads stream in at most 1 MiB chunks after allocation admission.
    """
    gauss = context["gauss"]["compiled_forms_verified"]
    if set(gauss) != {"top/0", "top/1", "bottom/0", "bottom/1"}:
        raise ValueError("complete frozen primary Gauss kernel inventory required")
    records = {}
    for name in ("top/0", "top/1", "bottom/0", "bottom/1"):
        kernel = gauss[name]["loaded_kernel"]
        if kernel.get("schema") != "task40extra.loaded-surface-kernel.v1":
            raise ValueError("frozen loaded surface kernel schema changed: " + name)
        verified = {}
        for role, path_field, hash_field in (
                ("binary", "module_path", "binary_sha256"),
                ("generated_C", "module_bound_C_path", "module_bound_C_sha256")):
            path_value, expected = kernel[path_field], kernel[hash_field]
            if (not isinstance(path_value, str) or not Path(path_value).is_absolute()
                    or not isinstance(expected, str) or len(expected) != 64
                    or any(c not in "0123456789abcdef" for c in expected)):
                raise ValueError("historical kernel file path/hash is invalid: " + name + "/" + role)
            _admit(allocation_gate, "snapshot_historical_file_" + name + "/" + role,
                   0, 2 << 20, read_chunk_upper_bytes=1 << 20,
                   historical_file_only=True, load_module=False, rebuild_JIT=False)
            path = Path(path_value)
            if not path.is_file():
                raise FileNotFoundError("historical primary kernel file is missing: " + str(path))
            before = path.stat()
            actual = _file_sha(path)
            after = path.stat()
            if (actual != expected or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                    != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)):
                raise ValueError("historical primary kernel file hash/identity changed: " + str(path))
            verified[role] = {"recorded_path": path_value, "resolved_path": str(path.resolve()),
                              "expected_sha256": expected, "verified_sha256": actual,
                              "verified_bytes": after.st_size}
        records[name] = verified
    return _freeze({"schema": "task40extra.historical-primary-surface-file-verification.v1",
        "status": "VERIFIED_HISTORICAL_FILES_ONLY", "verified_primary_gauss_records": 4,
        "verified_file_references": 8, "assembly_context_sha256": hashlib.sha256(_canonical(context)).hexdigest(),
        "records": records, "read_chunk_upper_bytes": 1 << 20,
        "historical_kernel_provenance_retained": True, "modules_loaded": False,
        "new_JIT_performed": False, "new_volume_kernel_qualified": False})


class SavedQuotientSnapshotAuthority:
    """Pinned finite snapshot metadata; no authority is granted to raw spools alone."""

    def __init__(self, root, *, new_source, new_environment, allocation_gate):
        self.root = Path(root).resolve()
        if self.root.name != AUTHORITY_RUN or not callable(allocation_gate):
            raise ValueError("fixed Q0--Q2 run and allocation gate required")
        self.allocation_gate = allocation_gate
        report = _read_json(self.root, "audit_report.json", allocation_gate, AUTHORITY_HASHES["audit_report.json"])
        checker = _read_json(self.root, "independent_checker.json", allocation_gate, AUTHORITY_HASHES["independent_checker.json"])
        artifacts = _read_json(self.root, "artifact_manifest.json", allocation_gate, AUTHORITY_HASHES["artifact_manifest.json"])
        if (report.get("status") != "QUOTIENT_OPERATOR_AUDIT_PASS" or report.get("degree") != 4
                or report.get("factor_count") != 0 or report.get("PDE_solved") is not False
                or report.get("source_clean_unchanged") is not True or report.get("artifacts") != artifacts
                or checker.get("gate_pass") is not True or checker.get("evidence_valid") is not True
                or checker.get("report_sha256") != AUTHORITY_HASHES["audit_report.json"]
                or checker.get("artifact_manifest_sha256") != ARTIFACT_INVENTORY_SHA256
                or hashlib.sha256(_canonical(artifacts)).hexdigest() != ARTIFACT_INVENTORY_SHA256
                or checker.get("source") != report.get("source")
                or not all(checker.get(k) is True for k in ("all_four_q", "all_532_original_keys", "both_branches_each_twist"))
                or len(checker.get("checks", ())) != 4842
                or any(c.get("passed") is not True or not math.isfinite(c.get("measured", math.nan))
                       or c["measured"] > c["limit"] for c in checker["checks"])):
            raise ValueError("fixed complete Q0--Q2 report/checker qualification required")
        bridge = _source_environment_gate(report["source"], new_source, report["environment"], new_environment)
        supervision_hashes = {}
        for reference in (report["supervisor_receipt"], checker["checker_watchdog_receipt"]):
            summary = _read_json(self.root, reference["path"], allocation_gate, reference["sha256"])
            _validate_supervision(summary, report["source"])
            supervision_hashes[reference["path"]] = reference["sha256"]
        _admit(allocation_gate, "snapshot_freeze_authority_metadata", 0,
               6*sum(len(_canonical(item)) for item in (report, checker, artifacts, new_source, new_environment))+(2 << 20))
        self.report, self.checker, self.artifacts = map(_freeze, (report, checker, artifacts))
        self.saved_source, self.saved_environment = self.report["source"], self.report["environment"]
        self.new_source, self.new_environment = _freeze(new_source), _freeze(new_environment)
        self._readers, receipts = {}, {}
        for twist in (None, 0, 1):
            directory = "raw_global" if twist is None else f"raw_twist_{twist}"
            self._readers[twist] = _FrozenRawReader(self.root, directory, twist, allocation_gate,
                manifest_sha=AUTHORITY_HASHES[directory + "/raw_packet_manifest.json"])
        for sector in report["twists"]:
            b, reference = sector["b"], sector["raw_port_receipt"]
            r = _read_json(self.root, reference["path"], allocation_gate, reference["sha256"])
            if (r.get("raw_port_audit_pass") is not True or r.get("quotient_twist_index") != b
                    or r.get("mode_count") != MODE_COUNTS[b]
                    or r.get("carrier_identity_before") != r.get("carrier_identity_after")
                    or r.get("assembly_context_sha256") != self._readers[b].identity["assembly_context_sha256"]
                    or tuple(r.get("original_mode_indices", ())) != tuple(sector["sector_original_indices"])
                    or tuple(item["original_mode_index"] for item in self._readers[b].manifest["records"])
                       != tuple(sector["sector_original_indices"])):
                raise ValueError("local raw receipt and exact carrier identity changed")
            receipts[b] = _freeze(r)
        if set(receipts) != {0, 1}:
            raise ValueError("both exact local raw receipts required")
        self.receipts = _freeze(receipts)
        self.audit = _freeze({"schema": SCHEMA, "authority_run": AUTHORITY_RUN,
            "authority_hashes": AUTHORITY_HASHES, "source_bridge": bridge, "checker_pass_count": 4842,
            "artifact_inventory_sha256": ARTIFACT_INVENTORY_SHA256,
            "restorer_source_sha256": _file_sha(__file__),
            "supervision_hashes": supervision_hashes,
            "raw_port_qualification_scope": "historical Q0-Q2 immutable evidence only",
            "global_snapshot_digest_source": "verified current35 packets plus exact finalized slave header",
            "old_ad356715_C_D_H_comparison": "separate existing per-mode numerical gates required",
            "factor_count": 0, "PDE_solved": False})
        self.receipt = self.audit

    def load(self, name):
        """Borrow a hash-bound read-only audit array; the caller owns its backing."""
        if not isinstance(name, str) or name not in self.artifacts:
            raise KeyError("array must name the fixed audited artifact inventory")
        return _load_array(self.root, self.artifacts[name], self.allocation_gate, "snapshot_audit_array_" + name)

    def snapshot_context(self, twist):
        """Return the exact frozen metadata context without opening raw arrays."""
        if twist is not None and (type(twist) is not int or twist not in (0, 1)):
            raise ValueError("snapshot context requires global None or integer twist 0/1")
        packet, _ = self._readers[twist].descriptor(0)
        return _freeze(packet["assembly_context"])

    def q_block(self, q):
        """Validated read-only saved CSR; the inverse owner must compare fresh blocks."""
        if type(q) is not int or q not in range(4):
            raise ValueError("q must name one of all four original branches")
        branch = next(item for twist in self.report["twists"] for item in twist["branches"] if item["q"] == q)
        descriptors = [self.artifacts[branch["csr_prefix"] + "_" + k] for k in ("data", "indices", "indptr")]
        arrays = []
        try:
            for part, descriptor in zip(("data", "indices", "indptr"), descriptors, strict=True):
                arrays.append(_load_array(self.root, descriptor, self.allocation_gate, f"snapshot_q{q}_{part}"))
            data, indices, indptr = arrays
            n, m = branch["shape"]
            if (n != m or n != (1884, 1960, 1960, 1960)[q] or data.dtype != np.dtype(np.complex128)
                    or indices.dtype != np.dtype(np.int32) or indptr.dtype != np.dtype(np.int32)
                    or data.ndim != 1 or indices.shape != data.shape or indptr.shape != (n+1,)
                    or indptr[0] != 0 or indptr[-1] != data.size or np.any(indptr[1:] < indptr[:-1])
                    or np.any(indices < 0) or np.any(indices >= m)):
                raise ValueError("saved q CSR exact shape/dtype/storage changed")
            for start, end in zip(indptr[:-1], indptr[1:]):
                row = indices[start:end]
                if row.size > 1 and np.any(row[1:] <= row[:-1]):
                    raise ValueError("saved q CSR must have sorted unique columns")
            _admit(self.allocation_gate, f"snapshot_q{q}_public_csr", sum(a.nbytes for a in arrays),
                   sum(a.nbytes for a in arrays)+(2 << 20), saved_block_requires_fresh_comparison=True)
            from scipy.sparse import csr_matrix
            result = csr_matrix((data, indices, indptr), shape=(n, m), copy=False)
            for a in (result.data, result.indices, result.indptr):
                a.flags.writeable = False
            return result  # Caller owns mmap lifetime. No authority cache of q blocks.
        except Exception:
            for array in arrays:
                _close_array(array)
            raise

    def restore_bundle(self, setup, cfg, degree, *, physical_cfg=None,
                       quotient_context=None, global_mode_inventory=None,
                       jit_options=None, volume_quadrature_metadata=None):
        """Restore sparse ports, then build the existing split volume action.

        This entry point belongs only in a separately approved supervised run.
        Historical surface/JIT metadata stays frozen; new volume identity is distinct.
        """
        if degree != 4 or type(degree) is not int or global_mode_inventory is None:
            raise ValueError("restoration requires p4 and explicit complete original inventory")
        if _file_sha(__file__) != self.audit["restorer_source_sha256"]:
            raise ValueError("restorer source changed after authority construction")
        if (quotient_context is None) != (physical_cfg is None):
            raise ValueError("local restoration requires explicit quotient context and physical config")
        twist = None if quotient_context is None else quotient_context.twist_index
        if twist is not None and (type(twist) is not int or twist not in (0, 1)):
            raise ValueError("only the frozen global/two-twist profiles are supported")
        reader = self._readers[twist]
        packet0, _ = reader.descriptor(0)
        context = packet0["assembly_context"]
        historical_files = _verify_historical_surface_files(context, self.allocation_gate)
        _admit(self.allocation_gate, "snapshot_actual_discrete_binding", 0, 16 << 20)
        binding, slave_rows = _validate_actual_discrete(setup, cfg, context, degree, self.new_environment,
                                                     self.new_source, quotient_context)
        # All project imports are deferred past metadata/source/discrete admission.
        from .fullspace_dtn_action import (FullspaceDtnModeFunctional, FullspaceDtnCarrier,
            _mode_identity, build_ordered_mode_manifest, build_fullspace_dtn_action)
        from .dtn_boundary_phase_gauge import (assembly_projection_denominator, phase_gauge_descriptor,
                                               deep_frozen_identity, incident_projection_in_solver_coordinates)
        from .dtn_boundary_plane_qualification import carrier_numeric_identity
        from .fullspace_same_mesh_hcurl_pmg_physical import _build_split_volume_action
        from .fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
        from .fullspace_physical_action import FullspacePhysicalAction
        global_modes, global_rows, global_sha = global_mode_inventory
        global_modes, global_rows = tuple(global_modes), tuple(global_rows)
        actual_rows, _, actual_sha = build_ordered_mode_manifest(global_modes, cfg if twist is None else physical_cfg)
        if (len(global_modes) != 532 or len(global_rows) != 532 or global_sha != PHYSICAL_MANIFEST
                or actual_sha != global_sha or not _equal(actual_rows, global_rows)):
            raise ValueError("complete unchanged original 532 physical inventory required")
        if twist is None:
            modes, mode_rows = global_modes, global_rows
        else:
            modes, mode_rows, selected_sha = quotient_context.select_inventory(physical_cfg, cfg, global_mode_inventory)
            if (selected_sha != PHYSICAL_MANIFEST or quotient_context.sha256 != reader.identity["quotient_contract_sha256"]
                    or not _equal(quotient_context.identity(), context["y_orbit_quotient"]["contract"])):
                raise ValueError("exact quotient contract changed")
        entries, identities = [], []
        digest = hashlib.sha256()
        header = {"schema": "task40extra.live-boundary-carrier-digest.v1",
                  "global_rows": reader.identity["ownership_range"][1],
                  "ownership_range": reader.identity["ownership_range"], "mode_count": len(modes),
                  "slave_rows": _signature(slave_rows)}
        digest.update(_canonical(header))
        copied_payload = 0
        try:
            for index, mode in enumerate(modes):
                with reader.packet(index) as (packet, pairs):
                    original = packet["original_mode_index"]
                    key = (str(mode.side), int(mode.m), int(mode.n), str(mode.polarization))
                    if (tuple(packet["original_mode_key"]) != key
                            or not _equal(packet["original_mode_row"], global_rows[original])
                            or not _equal(packet["assembly_context"], context)):
                        raise ValueError("exact original physical mode row/key changed")
                    h = float(packet["local_plane_H"])
                    if h != assembly_projection_denominator(mode, cfg, "boundary_plane"):
                        raise ValueError("saved/current local H identity changed")
                    if packet["original_plane_H"] != assembly_projection_denominator(mode, cfg if twist is None else physical_cfg, "boundary_plane"):
                        raise ValueError("saved/current original plane H identity changed")
                    identity = _mode_identity(index, mode, cfg, h)
                    identity.update({"assembly_identity_schema": "task40extra.fullspace-dtn-plane-assembly.v1",
                        "physical_generator_manifest_sha256": PHYSICAL_MANIFEST,
                        "assembly_context_sha256": packet["assembly_context_sha256"],
                        "global_projection_denominator_diagnostic": packet["original_mode_row"]["projection_denominator"],
                        "phase_gauge": phase_gauge_descriptor(mode, cfg, "boundary_plane")})
                    if twist is not None:
                        identity.update({"original_mode_index": original, "original_mode_key": key,
                            "original_mode_row": packet["original_mode_row"],
                            "original_plane_projection_denominator": float(packet["original_plane_H"]),
                            "local_branch_index": packet["local_branch_index"], "quotient_twist_index": twist,
                            "quotient_contract_sha256": packet["quotient_contract_sha256"],
                            "local_H_scale_from_global_plane_H": 0.5})
                    cr, cv = pairs["stored_C_sparse"]
                    dr, dv = pairs["stored_D_sparse"]
                    # PETSc's frozen int32 ABI: check before conversion, never wrap.
                    maximum = np.iinfo(np.int32).max
                    if (cr.size and cr[-1] > maximum) or (dr.size and dr[-1] > maximum):
                        raise OverflowError("saved sparse row exceeds frozen PETSc integer ABI")
                    payload = (cr.size+dr.size)*(4+16)+8
                    _admit(self.allocation_gate, f"snapshot_copy_stored_{twist}_{index}", copied_payload+payload,
                           2*payload+(2 << 20), retained_entry_payload_bytes=copied_payload)
                    cr, cv, dr, dv = cr.astype(np.int32, copy=True), cv.copy(), dr.astype(np.int32, copy=True), dv.copy()
                    for a in (cr, cv, dr, dv):
                        a.flags.writeable = False
                    # stored_D is already conjugated. It is copied byte-for-byte.
                    mode_key = (index, *key)
                    digest.update(_canonical({"index": index, "key": mode_key, "H": h,
                        "coupling_rows": _signature(cr), "coupling_values": _signature(cv),
                        "projection_rows": _signature(dr), "projection_values": _signature(dv)}))
                    entries.append(FullspaceDtnModeFunctional(mode_key, cr, cv, dr, dv, h, deep_frozen_identity(identity)))
                    identities.append(identity)
                    copied_payload += payload
            expected_manifest = hashlib.sha256(_canonical({"schema": "fullspace-dtn.mode-manifest.v1",
                "profile": "full3d_scalable_v1", "mode_count": len(entries), "modes": identities})).hexdigest()
            expected = {"physical_generator_manifest_sha256": PHYSICAL_MANIFEST,
                        "assembly_mode_manifest_sha256": expected_manifest,
                        "assembly_context_sha256": reader.identity["assembly_context_sha256"],
                        "carrier_numeric_sha256": digest.hexdigest(), "mode_count": len(entries),
                        "ordered_mode_keys": tuple(e.mode_key for e in entries)}
            if twist is not None and not _equal(expected, self.receipts[str(twist)]["carrier_identity_after"]):
                raise ValueError("reconstructed local manifest/numeric digest differs from exact raw receipt")
            _admit(self.allocation_gate, f"snapshot_public_carrier_{twist}", copied_payload,
                   2*copied_payload + 6*sum(len(_canonical(i)) for i in identities)+(2 << 20),
                   constructor_second_entry_copy_bytes=copied_payload)
            carrier = FullspaceDtnCarrier(entries, global_rows=header["global_rows"],
                ownership_range=tuple(header["ownership_range"]), slave_rows=slave_rows,
                batch_size=8, comm=setup["mesh"].comm)
            carrier.phase_gauge = "boundary_plane"
            carrier.physical_generator_manifest_sha256 = PHYSICAL_MANIFEST
            carrier.assembly_context = deep_frozen_identity(context)
            carrier.assembly_context_sha256 = reader.identity["assembly_context_sha256"]
            retained_payload = 0
            owners = {}
            for entry in entries + list(carrier.entries):
                for array in (entry.coupling_rows, entry.coupling_values, entry.projection_rows, entry.projection_values):
                    owner = array
                    while isinstance(getattr(owner, "base", None), np.ndarray):
                        owner = owner.base
                    owners[id(owner)] = int(owner.nbytes)
            for entry in carrier.entries:
                retained_payload += sum(a.nbytes for a in (entry.coupling_rows, entry.coupling_values,
                                                           entry.projection_rows, entry.projection_values))
            carrier.construction_numeric_inventory = MappingProxyType({
                "component_cache_payload_with_aliases": 0,
                "staging_functional_payload_with_aliases": copied_payload - 8*len(entries),
                "retained_functional_payload_with_aliases": retained_payload,
                "unique_named_numpy_backing_bytes_before_staging_release": sum(owners.values()),
                "scope": "snapshot stored-pair copies plus public carrier buffers before release; not RSS/peak; excludes sorting/JIT/MPC/allocator/identity temporaries",
                "resource_authority": "external whole-tree gate required",
                "restoration_source": "verified frozen ten-pair packets; no surface assembly"})
            if twist is not None:
                carrier.quotient_context = quotient_context
                for name in ("original_mode_indices", "original_mode_keys", "original_mode_rows", "local_branch_indices"):
                    setattr(carrier, name, getattr(quotient_context, name))
            actual_identity = carrier_numeric_identity(carrier)
            if not _equal(actual_identity, expected):
                raise ValueError("public constructor changed frozen manifest/numeric carrier identity")
        finally:
            entries.clear()
            identities.clear()
        # Do not retain the final loop's staging copy through volume/JIT work.
        del cr, cv, dr, dv, entry, array, owner, owners, packet, pairs
        options = SAME_MESH_JIT_OPTIONS if jit_options is None else jit_options
        dtn_action = volume_action = physical_action = None
        try:
            _admit(self.allocation_gate, f"snapshot_build_existing_actions_{twist}", copied_payload, 64 << 20)
            dtn_action = build_fullspace_dtn_action(carrier, comm=setup["mesh"].comm)
            volume_action = _build_split_volume_action(setup["mesh_data"], cfg, setup["spaces"][degree],
                setup["floquets"][degree], jit_options=options,
                volume_quadrature_metadata=volume_quadrature_metadata)
            physical_action = FullspacePhysicalAction(volume_action, dtn_action)
            receipt = _freeze({"schema": SCHEMA, "status": "RESTORED_EXACT_SNAPSHOT_NEW_VOLUME_UNQUALIFIED",
                "authority": self.audit, "quotient_twist_index": twist, "actual_discrete_binding": binding,
                "expected_snapshot_identity": expected, "restored_public_carrier_identity": actual_identity,
                "local_raw_receipt_sha256": None if twist is None else self.report["twists"][twist]["raw_port_receipt"]["sha256"],
                "historical_raw_JIT_context_sha256": reader.identity["assembly_context_sha256"],
                "historical_primary_surface_file_verification": historical_files,
                "new_volume_source": self.new_source, "new_volume_environment": self.new_environment,
                "new_volume_audit": dict(volume_action.audit), "new_recovery_identity": "inverse owner must rebuild and compare fresh q blocks",
                "stored_D_second_conjugation": False, "packet_mmaps_released": True,
                "factor_count": 0, "PDE_solved": False})
            bundle = {"schema": "task40extra.boundary-plane-physical-action.research.v1", "setup": setup,
                "cfg": cfg, "degree": degree, "action": physical_action, "physical_action": physical_action,
                "volume_action": volume_action, "dtn_action": dtn_action, "modes": tuple(modes),
                "mode_rows": tuple(mode_rows), "mode_sha256": PHYSICAL_MANIFEST,
                "dtn_quadrature_degree": 23, "volume_quadrature_metadata": volume_quadrature_metadata,
                "incident_projections": (tuple(incident_projection_in_solver_coordinates(m, cfg, "boundary_plane") for m in modes)
                                          if twist is None else None),
                "compiled_surface_gauss_identity": context["gauss"]["compiled_forms_verified"],
                "dtn_phase_gauge": "boundary_plane", "physical_generator_manifest_sha256": PHYSICAL_MANIFEST,
                "assembly_mode_manifest_sha256": carrier.mode_manifest_sha256,
                "assembly_context_sha256": carrier.assembly_context_sha256,
                "solver_auxiliary_coordinate": "boundary_plane", "global_output_conversion": "explicit-representability-gated",
                "snapshot_restoration_receipt": receipt}
            if twist is not None:
                bundle.update({"quotient_context": quotient_context, "physical_cfg": physical_cfg,
                    "global_mode_inventory": global_mode_inventory, "original_mode_indices": quotient_context.original_mode_indices,
                    "global_mode_indices": quotient_context.original_mode_indices, "qbase": twist,
                    "original_mode_keys": quotient_context.original_mode_keys,
                    "local_branch_indices": quotient_context.local_branch_indices,
                    "physical_rhs_source": "dual_transport_of_original_global_MPC_load"})
            return bundle, receipt
        except Exception:
            if physical_action is not None:
                physical_action.destroy()
            else:
                if volume_action is not None:
                    volume_action.destroy()
                if dtn_action is not None:
                    dtn_action.destroy()
            raise


def _validate_actual_discrete(setup, cfg, context, degree, environment, source, quotient_context):
    """Public finalized inputs; no surface forms, coefficient assembly or JIT."""
    V, floquet, data = setup["spaces"][degree], setup["floquets"][degree], setup["mesh_data"]
    mpc, mesh = floquet.mpc, data.mesh
    if (mpc is None or getattr(mpc, "finalized", None) is not True
            or mesh is not V.mesh or mpc.function_space.mesh is not mesh
            or setup["mesh"] is not mesh or int(mesh.comm.size) != 1):
        raise ValueError("same actual space/mesh/finalized MPI1 MPC required")
    index_map = V.dofmap.index_map
    expected_rows = 17204 if quotient_context is None else 8940
    expected_cells = 80 if quotient_context is None else 40
    if (int(index_map.size_global) != expected_rows or int(index_map.size_local) != expected_rows
            or tuple(index_map.local_range) != (0, expected_rows)
            or int(V.dofmap.index_map_bs) != 1 or int(V.element.basix_element.degree) != degree):
        raise ValueError("actual full owned p4 storage/degree identity changed")
    mpc_map = mpc.function_space.dofmap.index_map
    if (int(mpc_map.size_global) != expected_rows or int(mpc_map.size_local) != expected_rows
            or tuple(mpc_map.local_range) != (0, expected_rows)
            or int(mpc.function_space.dofmap.index_map_bs) != 1):
        raise ValueError("actual finalized MPC space storage changed")
    coefficients, offsets = mpc.coefficients()
    for name, value in (("slaves", mpc.slaves), ("masters", mpc.masters.array), ("coefficients", coefficients), ("offsets", offsets)):
        if not _equal(_signature(value), context["MPC"][name]):
            raise ValueError("actual finalized MPC changed: " + name)
    mesh.topology.create_entity_permutations()
    mesh.topology.create_connectivity(mesh.topology.dim-1, 0)
    facets = mesh.topology.connectivity(mesh.topology.dim-1, 0)
    for name, value in (("geometry_x", mesh.geometry.x), ("geometry_dofmap", mesh.geometry.dofmap),
            ("facet_vertices", facets.array), ("facet_vertex_offsets", facets.offsets),
            ("facet_indices", data.facet_tags.indices), ("facet_values", data.facet_tags.values),
            ("cell_indices", data.cell_tags.indices), ("cell_values", data.cell_tags.values)):
        if not _equal(_signature(value), context["mesh"][name]):
            raise ValueError("actual mesh/facet/material identity changed: " + name)
    cell_count = int(mesh.topology.index_map(mesh.topology.dim).size_local)
    dofs = hashlib.sha256()
    for cell in range(cell_count):
        cell_dofs = np.asarray(V.dofmap.cell_dofs(cell))
        if not np.array_equal(cell_dofs, mpc.function_space.dofmap.cell_dofs(cell)):
            raise ValueError("actual finalized MPC and original cell dofmaps differ")
        dofs.update(_canonical(_signature(cell_dofs)))
    element = V.element.basix_element
    if (cell_count != expected_cells or dofs.hexdigest() != context["cell_dofmap_sha256"]
            or not _equal(_signature(mesh.topology.get_cell_permutation_info()), context["orientation"])
            or not _equal(_signature(element.coefficient_matrix), context["basix_coefficients"])
            or bool(V.element.needs_dof_transformations) != context["needs_dof_transformations"]
            or int(element.degree) != context["element_degree"] or element.map_type.name != context["element_map_type"]
            or hashlib.sha256(_canonical(cfg.as_jsonable())).hexdigest() != context["config_sha256"]
            or context["gauss"]["degree"] != 23 or context["gauss"]["facet_cell"] != "quadrilateral"):
        raise ValueError("actual dofmap/orientation/Basix/config/Gauss identity changed")
    abi = context["ABI"]
    if (abi["python"] != sys.version or abi["numpy"] != np.__version__
            or Path(sys.executable).resolve() != Path(environment["python"]).resolve()
            or Path(sys.prefix).resolve() != Path(environment["prefix"]).resolve()):
        raise ValueError("actual Python/NumPy ABI changed")
    import basix
    import dolfinx
    import ffcx
    for package in ("basix", "dolfinx", "ffcx"):
        expected = environment["modules"][package]["version"]
        module = sys.modules.get(package)
        if module is None or getattr(module, "__version__", None) != expected or abi[package] != expected:
            raise ValueError("actual loaded ABI changed: " + package)
    from petsc4py import PETSc
    from mpi4py import MPI
    actual_mpc_version = importlib.metadata.version("dolfinx_mpc")
    if (abi["dolfinx_mpc"] != actual_mpc_version or tuple(abi["PETSc"]) != tuple(PETSc.Sys.getVersion())
            or abi["scalar"] != str(np.dtype(PETSc.ScalarType)) or abi["integer"] != str(np.dtype(PETSc.IntType))
            or str(np.dtype(PETSc.IntType)) != "int32" or str(np.dtype(PETSc.ScalarType)) != "complex128"):
        raise ValueError("actual MPC/PETSc complex scalar/integer ABI changed")
    if MPI.Get_library_version() != environment["mpi_library"]:
        raise ValueError("actual MPI library changed")
    for name, expected in environment["modules"].items():
        module = importlib.import_module(name)
        if (getattr(module, "__version__", None) != expected["version"]
                or Path(module.__file__).resolve() != Path(expected["path"]).resolve()):
            raise ValueError("actual module ABI/origin changed: " + name)
    qualification_path = Path(environment["qualification_manifest"])
    if _file_sha(qualification_path) != environment["qualification_manifest_sha256"]:
        raise ValueError("actual qualified environment receipt changed")
    # Resolve the actual package search paths, so an external staged module can
    # coexist with unchanged canonical dependencies without changing __file__.
    package_root = __package__.rsplit(".", 1)[0]
    packages = (package_root + ".solvers", package_root + ".common", package_root + ".constraints")
    actual_sources = {}
    for name, expected in context["source_sha256"].items():
        if Path(name).name != name or not name.endswith(".py"):
            raise ValueError("bound source must name a Python module")
        candidates = []
        for package in packages:
            spec = importlib.util.find_spec(package)
            if spec is None or spec.submodule_search_locations is None:
                continue
            for location in spec.submodule_search_locations:
                path = Path(location)/name
                if path.is_file():
                    candidates.append((package, path.resolve()))
        if len(candidates) != 1 or _file_sha(candidates[0][1]) != expected:
            raise ValueError("actual bound numerical source changed: " + name)
        package, path = candidates[0]
        spec = importlib.util.find_spec(package + "." + name[:-3])
        if spec is None or spec.origin is None or Path(spec.origin).resolve() != path:
            raise ValueError("bound source is not the selected import origin: " + name)
        relative = "src/" + package.rsplit(".", 1)[1] + "/" + name
        if source["files_sha256"].get(relative) != expected:
            raise ValueError("actual source missing from new source inventory: " + relative)
        actual_sources[name] = expected
    if quotient_context is not None:
        if ((complex(floquet.phase_x), complex(floquet.phase_y)) != quotient_context.phase_override
                or complex(floquet.phase_corner) != quotient_context.phase_x*quotient_context.tau
                or floquet.orientation_factor_stats.get("research_phase_source") != "explicit_pre_finalize_topology_materialization"):
            raise ValueError("actual finalized explicit quotient wrap changed")
    slaves = np.asarray(mpc.slaves)
    owned = slaves[slaves < int(index_map.size_local)]
    slave_rows = np.asarray(index_map.local_to_global(owned), dtype=np.int32)
    slave_rows = np.unique(slave_rows)
    slave_rows.flags.writeable = False
    return {"actual_cells": cell_count, "actual_storage_rows": expected_rows,
            "actual_finalized_slave_rows": len(slave_rows), "cell_dofmap_sha256": dofs.hexdigest(),
            "actual_source_sha256": actual_sources, "ABI_equal": True, "config_equal": True}, slave_rows


__all__ = ("SavedQuotientSnapshotAuthority",)
