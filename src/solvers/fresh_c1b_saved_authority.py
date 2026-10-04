"""Pinned fresh C1b validation arrays for the C1c b0/q0 prefactor component.

No FE imports, carrier restoration, factorization or source exceptions. Saved
full-Ny maps/matrices are validation controls only. Array imports are lazy.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re

SCHEMA = "task40extra.fresh-c1b-saved-validation-authority.v1"
HEAD = "dd26a1a9d1699e8cd7173c5d987496477db2152b"
BRANCH = "task40extra_dot_parallel_cloud"
ABI_SHA = "e87625e839b6360c47c333dfeb861616f604a9468202752b62a0096ad4046dbb"
INPUT_SHA = "6654ec211efbc6112f3ccba13ad67ff3a97cdbc471bdd48e39f891819f51a41e"
FILE_HASHES = {
    "probe_report.json": "58448f050b223c36728e24bf5ecc985d6734ed77191a3dfd2a2917e435feef2c",
    "independent_checker.json": "96f64a10a64587ae867282d0d0116e1afabacfe985328b0a8354c877299a1beb",
    "provenance.json": "a63ab74119d3e122c48bc62c69561aae83d5b3946ff15df4ee01b21dc232ec36",
    "summary.json": "211bd65ceaf5bc91ec5c3c3443587d9d5b4ea98a3b8b2028fdcd00aa0bc4cf6b",
}
ARTIFACT_DIGEST = "67a86101fb39c0cd751fa49344a002d7f3d5bd9eeb53aa29f40d96649c1d7041"
WORKER_LIBRARY_RECEIPT_SHA = "8b0d262e96f4007f28502023528bb29b55b70ab1d1a01f1fe136dbf78552ee2e"
CHECKER_LIBRARY_RECEIPT_SHA = "c3ab43cde7798014ab41b053359fe2691e3c653716da381cc8cb77e6d5a16ab6"
WORKER_LIBRARY_INDEX = "libfile_6c5d9eaccaa081919951a2abf2611064"
CHECKER_LIBRARY_FILE = "libfile_d9ebe52606348191b6a6e1d1121419a5"
ENV_FIELDS = ("python", "prefix", "modules", "petsc_scalar_type", "petsc_int_type",
              "petsc_version", "mpi_library", "qualification_manifest_sha256", "qualification_scope")
CSR_SHAPES = {
    "q_0_S": (1884, 1884), "full_Q": (15872, 15872),
    "full_R_inverse": (15872, 15872), "full_F": (15872, 15872),
    "full_T": (15872, 15872), "trace_R_t": (7232, 7232),
    "trace_R_t_inverse": (7232, 7232), "trace_F_t": (7232, 7232),
    "trace_native_trace_translation": (7232, 7232), "reference_S": (7764, 7764),
    "original_port_C": (17204, 532), "original_port_D": (532, 17204),
}


def file_sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def bound_path(root, relative):
    if not isinstance(relative, str):
        raise ValueError("a relative saved-artifact path is required")
    raw = PurePosixPath(relative)
    if raw.is_absolute() or not raw.parts or any(p in (".", "..") for p in raw.parts):
        raise ValueError("saved-artifact path traversal/absolute path rejected")
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise ValueError("saved-artifact path must be a readable file within the authority")
    return path


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _json(path, expected_sha, gate):
    path = Path(path)
    size = path.stat().st_size
    if size > 16 << 20 or file_sha(path) != expected_sha:
        raise ValueError("pinned C1b metadata hash/size differs: " + path.name)
    gate("fresh_C1b_metadata_" + path.name,
         {"matrix_payload_bytes": 0, "workspace_bytes": 6 * size + (1 << 20),
          "validation_only": True})
    def nonfinite(value):
        raise ValueError("nonfinite JSON value: " + value)
    return json.loads(path.read_text(), object_pairs_hook=_pairs, parse_constant=nonfinite)


def validate_source_environment(saved_source, new_source, saved_env, new_env, *, allowed_added_paths=()):
    """Existing dependencies must stay byte-identical; only named additions are allowed."""
    if (saved_source.get("head") != HEAD or saved_source.get("branch") != BRANCH
            or saved_source.get("dirty") or new_source.get("branch") != BRANCH
            or new_source.get("dirty") or not re.fullmatch(r"[0-9a-f]{40}", new_source.get("head", ""))):
        raise ValueError("clean pinned own-branch source identities required")
    before, after = saved_source.get("files_sha256", {}), new_source.get("files_sha256", {})
    if not before or any(after.get(name) != sha for name, sha in before.items()):
        raise ValueError("existing C1b dependency changed or disappeared; no source waiver")
    added = set(after) - set(before)
    allowed = set(allowed_added_paths)
    if (not added.issubset(allowed) or any(name in before for name in allowed)
            or any(PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts for name in allowed)
            or any(not re.fullmatch(r"[0-9a-f]{64}", sha) for sha in after.values())):
        raise ValueError("only explicitly reviewed new dependency paths are admitted")
    if (saved_env.get("qualification_manifest_sha256") != ABI_SHA
            or any(key not in saved_env or key not in new_env or saved_env[key] != new_env[key]
                   for key in ENV_FIELDS)):
        raise ValueError("fresh C1b ABI must match exactly")
    return sorted(added)


def validate_metadata(report, checker, provenance):
    if (report.get("status") != "SPARSE_CONDENSED_FULL3D_PROBE_PASS"
            or report.get("degree") != 4 or report.get("fresh_fixture_c1") != "p4-chain"
            or report.get("input_sha256") != INPUT_SHA or report.get("source_clean_unchanged") is not True
            or checker.get("gate_pass") is not True or checker.get("evidence_valid") is not True
            or checker.get("report_sha256") != FILE_HASHES["probe_report.json"]
            or checker.get("provenance_sha256") != FILE_HASHES["provenance.json"]
            or checker.get("artifact_manifest_sha256") != ARTIFACT_DIGEST
            or checker.get("compact_p4_quotient_qualified") is not False
            or checker.get("source") != report.get("source")
            or provenance.get("source") != report.get("source")
            or provenance.get("environment") != report.get("environment")
            or digest_json(report.get("artifacts")) != ARTIFACT_DIGEST):
        raise ValueError("exact fresh C1b report/checker/provenance linkage required")
    checks = checker.get("checks", ())
    if len(checks) != 148 or any(c.get("passed") is not True or
        not isinstance(c.get("measured"), (int, float)) or not math.isfinite(c["measured"]) or
        not isinstance(c.get("limit"), (int, float)) or not math.isfinite(c["limit"]) or
        c["measured"] > c["limit"] for c in checks):
        raise ValueError("all 148 exact saved checker measurements must pass")


class FreshC1bSavedAuthority:
    """Own small metadata; borrow read-only mmap arrays, never cache arrays/CSR.

    Caller owns returned mappings/CSR and releases them after comparison. The
    allocation callback must measure the complete current process tree. There
    is no restore_bundle, factor/solve or all-q authority API in this reader.
    """
    def __init__(self, directory, *, new_source, new_environment, allocation_gate,
                 worker_library_receipt, checker_library_receipt, allowed_added_paths=()):
        if not callable(allocation_gate):
            raise ValueError("fresh measured whole-tree allocation callback required")
        self.directory = Path(directory).resolve()
        self.allocation_gate = allocation_gate
        objects = {name: _json(bound_path(self.directory, name), sha, allocation_gate)
                   for name, sha in FILE_HASHES.items()}
        report, checker, provenance = (objects[name] for name in
                                      ("probe_report.json", "independent_checker.json", "provenance.json"))
        validate_metadata(report, checker, provenance)
        additions = validate_source_environment(report["source"], new_source,
            report["environment"], new_environment, allowed_added_paths=allowed_added_paths)
        summary = objects["summary.json"]
        if summary.get("classification") != "COMPLETED":
            raise ValueError("saved worker supervision must be completed")
        watch = checker["checker_watchdog_receipt"]
        checked = _json(bound_path(self.directory, watch["path"]), watch["sha256"], allocation_gate)
        if checked.get("classification") != "COMPLETED":
            raise ValueError("saved checker supervision must be completed")
        if file_sha(bound_path(self.directory, "abi_manifest.json")) != ABI_SHA:
            raise ValueError("saved ABI bytes differ")
        live = report["centered_identity"]["live_component_receipt"]
        _json(bound_path(self.directory, live["filename"]), live["sha256"], allocation_gate)
        worker = _json(worker_library_receipt, WORKER_LIBRARY_RECEIPT_SHA, allocation_gate)
        durable = _json(checker_library_receipt, CHECKER_LIBRARY_RECEIPT_SHA, allocation_gate)
        if (worker.get("status") != "LIBRARY_C1b_COMPLETE_WORKER_PACKET_FULL_ROUNDTRIP_PASS"
                or worker.get("source_head") != HEAD or worker.get("parts_verified") != 4
                or worker.get("NPYs_shape_dtype_numeric_hash_verified") != 327
                or durable.get("status") != "FRESH_LIBRARY_READBACK_ALL_HASHES_PASS"
                or durable.get("library_file_id") != CHECKER_LIBRARY_FILE
                or durable.get("metadata", {}).get("worker_raw_Library_index") != WORKER_LIBRARY_INDEX
                or durable["metadata"].get("worker_report_sha256") != FILE_HASHES["probe_report.json"]
                or durable["metadata"].get("checker_report_sha256") != FILE_HASHES["independent_checker.json"]):
            raise ValueError("exact worker/full-raw and final-checker Library readbacks required")
        self.report = report
        allocation_gate("fresh_C1b_freeze_saved_descriptors",
            {"matrix_payload_bytes": 0, "workspace_bytes": 4 * len(json.dumps(report["artifacts"])) + (1 << 20),
             "validation_only": True})
        self._artifacts = copy.deepcopy(report["artifacts"])
        # Files remain hash-checked again at every array access, including unused
        # authority arrays. No NPY numerical payload is opened by the constructor.
        for descriptor in self._artifacts.values():
            path = bound_path(self.directory, descriptor["path"])
            if file_sha(path) != descriptor["file_sha256"]:
                raise ValueError("C1b saved artifact bytes differ")
        self.receipt = {"schema": SCHEMA, "source_head": HEAD,
            "new_head": new_source["head"], "file_hashes": dict(FILE_HASHES),
            "ABI_sha256": ABI_SHA, "artifact_manifest_sha256": ARTIFACT_DIGEST,
            "worker_Library_index": WORKER_LIBRARY_INDEX, "checker_Library_file": CHECKER_LIBRARY_FILE,
            "Library_receipt_hashes": [WORKER_LIBRARY_RECEIPT_SHA, CHECKER_LIBRARY_RECEIPT_SHA],
            "reviewed_added_dependencies": additions, "existing_dependencies_unchanged": True,
            "validation_only_full_maps": True, "candidate_setup_uses_old_full_maps": False,
            "scope": "C1c b0/q0 prefactor validation only; no full compact quotient qualification"}

    def identity(self):
        return copy.deepcopy(self.receipt)

    def load(self, name):
        if not isinstance(name, str) or name not in self._artifacts:
            raise KeyError("array must belong to the pinned C1b inventory")
        descriptor = self._artifacts[name]
        path = bound_path(self.directory, descriptor["path"])
        if file_sha(path) != descriptor["file_sha256"]:
            raise ValueError("C1b array changed after constructor validation")
        self.allocation_gate("fresh_C1b_validation_mmap_" + name,
            {"matrix_payload_bytes": int(descriptor["payload_bytes"]), "workspace_bytes": 1 << 20,
             "validation_only": True, "readonly_mmap": True})
        import numpy as np
        value = np.load(path, allow_pickle=False, mmap_mode="r")
        if (list(value.shape) != descriptor["shape"] or str(value.dtype) != descriptor["dtype"]
                or value.nbytes != descriptor["payload_bytes"] or value.dtype.hasobject or value.flags.writeable):
            raise ValueError("C1b array descriptor/read-only contract differs")
        if value.dtype.kind in "fc" and any(not np.isfinite(v) for v in value.flat):
            raise ValueError("C1b array contains nonfinite values")
        return value

    def load_csr(self, prefix, shape=None, *, csc=False):
        expected = CSR_SHAPES.get(prefix)
        if expected is None or (shape is not None and tuple(shape) != expected):
            raise ValueError("only the fixed validation CSR inventory/shape is admitted")
        arrays = [self.load(prefix + "_" + part) for part in ("data", "indices", "indptr")]
        values, indices, offsets = arrays
        compressed, width = (expected[1], expected[0]) if csc else expected
        if (values.ndim != 1 or indices.ndim != 1 or offsets.ndim != 1
                or str(values.dtype) != "complex128" or str(indices.dtype) != "int32"
                or str(offsets.dtype) != "int32" or len(values) != len(indices)
                or len(offsets) != compressed + 1 or int(offsets[0]) != 0
                or int(offsets[-1]) != len(values) or any(int(a) > int(b) for a, b in zip(offsets, offsets[1:]))
                or any(int(i) < 0 or int(i) >= width for i in indices)
                or (prefix == "q_0_S" and len(values) != 436012)):
            raise ValueError("saved CSR/CSC width/NNZ/index inventory differs before construction")
        self.allocation_gate("fresh_C1b_validation_sparse_constructor_" + prefix,
            {"matrix_payload_bytes": sum(int(a.nbytes) for a in arrays), "workspace_bytes": 1 << 20,
             "validation_only": True, "possible_SciPy_constructor_copy_included": True})
        from scipy import sparse
        cls = sparse.csc_matrix if csc else sparse.csr_matrix
        matrix = cls(tuple(arrays), shape=expected, copy=False)
        # q0 has the existing canonical CSR contract. Historical full maps may
        # retain unsorted storage; their pinned bytes are valid controls and must
        # never be sorted in place. A consumer needing sorted storage owns a copy.
        if prefix == "q_0_S" and (not matrix.has_sorted_indices or not matrix.has_canonical_format):
            raise ValueError("saved sparse validation control is noncanonical")
        for array in (matrix.data, matrix.indices, matrix.indptr):
            array.setflags(write=False)
        return matrix

    def q_block(self, q):
        if type(q) is not int or q != 0:
            raise ValueError("this reader admits q0 only; further branches require separate scope")
        return self.load_csr("q_0_S", (1884, 1884))


__all__ = ("FreshC1bSavedAuthority",)
