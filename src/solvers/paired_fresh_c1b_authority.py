"""Pinned fresh C1b read-only controls for the bounded paired-live all-four-q run.

No FE imports, carrier restoration, factorization, or solver qualification. The
only existing-source exception is the exact reviewed structural-empty provider
optimization. Actual new all-q and cross comparisons remain caller-side gates.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path, PurePosixPath
import re

from src.solvers import fresh_c1b_saved_authority as saved

SCHEMA = "task40extra.paired-fresh-c1b-validation-authority.v1"
HEAD, BRANCH, ABI_SHA = saved.HEAD, saved.BRANCH, saved.ABI_SHA
ENV_FIELDS = saved.ENV_FIELDS
FILE_HASHES = dict(saved.FILE_HASHES)
ARTIFACT_DIGEST = saved.ARTIFACT_DIGEST
PROVIDER_PATH = "src/solvers/y_orbit_two_cell_block_audit.py"
PROVIDER_OLD_SHA = "8dcfbf8278ce2de5a969aef1db97c8d42462e486e8813e60bb9599cc6a18f5bd"
PROVIDER_NEW_SHA = "4ba8df2f06d0feb35931b9aca51dee77bbe66bf0b555afe7f6d39b148cade46b"
Q_SHAPES = ((1884, 1884), (1960, 1960), (1960, 1960), (1960, 1960))
Q_NNZ = (436012, 454744, 454744, 455143)
CSR_SHAPES = dict(saved.CSR_SHAPES)
CSR_SHAPES.update({f"q_{q}_S": shape for q, shape in enumerate(Q_SHAPES)})
Q_CSR_NNZ = {f"q_{q}_S": nnz for q, nnz in enumerate(Q_NNZ)}
file_sha, digest_json, bound_path = saved.file_sha, saved.digest_json, saved.bound_path
_json, _pairs, validate_metadata = saved._json, saved._pairs, saved.validate_metadata


def _relative_dependency(name):
    if not isinstance(name, str) or not name or "\\" in name:
        return False
    path = PurePosixPath(name)
    return (not path.is_absolute() and bool(path.parts) and ".." not in path.parts
            and str(path) == name)


def validate_source_environment(saved_source, new_source, saved_env, new_env, *,
                                allowed_added_paths=()):
    """Admit the exact provider old/new pair; every other old dependency is fixed."""
    if not all(isinstance(value, dict) for value in
               (saved_source, new_source, saved_env, new_env)):
        raise ValueError("complete source/environment dictionaries required")
    if ("dirty" not in saved_source or "dirty" not in new_source
            or saved_source.get("head") != HEAD or saved_source.get("branch") != BRANCH
            or saved_source.get("dirty") or new_source.get("branch") != BRANCH
            or new_source.get("dirty")
            or not isinstance(new_source.get("head"), str)
            or not re.fullmatch(r"[0-9a-f]{40}", new_source["head"])):
        raise ValueError("clean pinned own-branch source identities required")
    before, after = saved_source.get("files_sha256"), new_source.get("files_sha256")
    if (not isinstance(before, dict) or not before or not isinstance(after, dict)
            or any(not _relative_dependency(name) for name in (*before, *after))
            or any(not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha)
                   for sha in (*before.values(), *after.values()))):
        raise ValueError("complete valid source dependency hashes required")
    if (before.get(PROVIDER_PATH) != PROVIDER_OLD_SHA
            or after.get(PROVIDER_PATH) != PROVIDER_NEW_SHA):
        raise ValueError("exact reviewed provider old/new hash pair required")
    if any(after.get(name) != sha for name, sha in before.items() if name != PROVIDER_PATH):
        raise ValueError("another existing C1b dependency changed or disappeared")
    added = set(after) - set(before)
    allowed = set(allowed_added_paths)
    if (not added.issubset(allowed) or any(name in before for name in allowed)
            or any(not _relative_dependency(name) for name in allowed)):
        raise ValueError("only explicitly declared new dependency paths are admitted")
    if (saved_env.get("qualification_manifest_sha256") != ABI_SHA
            or any(key not in saved_env or key not in new_env for key in ENV_FIELDS)
            or saved_env != new_env or digest_json(saved_env) != digest_json(new_env)):
        raise ValueError("complete fresh C1b environment dictionaries must match exactly")
    return sorted(added)


class PairedFreshC1bAuthority(saved.FreshC1bSavedAuthority):
    """Own metadata only; caller owns and releases each returned read-only control.

    All original metadata, Library, supervision and array-byte pins apply.
    No constructor payload import, cached arrays/CSR, factor or restore API.
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
        if objects["summary.json"].get("classification") != "COMPLETED":
            raise ValueError("saved worker supervision must be completed")
        watch = checker["checker_watchdog_receipt"]
        checked = _json(bound_path(self.directory, watch["path"]), watch["sha256"], allocation_gate)
        if checked.get("classification") != "COMPLETED":
            raise ValueError("saved checker supervision must be completed")
        if file_sha(bound_path(self.directory, "abi_manifest.json")) != ABI_SHA:
            raise ValueError("saved ABI bytes differ")
        live = report["centered_identity"]["live_component_receipt"]
        _json(bound_path(self.directory, live["filename"]), live["sha256"], allocation_gate)
        worker = _json(worker_library_receipt, saved.WORKER_LIBRARY_RECEIPT_SHA, allocation_gate)
        durable = _json(checker_library_receipt, saved.CHECKER_LIBRARY_RECEIPT_SHA, allocation_gate)
        if (worker.get("status") != "LIBRARY_C1b_COMPLETE_WORKER_PACKET_FULL_ROUNDTRIP_PASS"
                or worker.get("source_head") != HEAD or worker.get("parts_verified") != 4
                or worker.get("NPYs_shape_dtype_numeric_hash_verified") != 327
                or durable.get("status") != "FRESH_LIBRARY_READBACK_ALL_HASHES_PASS"
                or durable.get("library_file_id") != saved.CHECKER_LIBRARY_FILE
                or durable.get("metadata", {}).get("worker_raw_Library_index") != saved.WORKER_LIBRARY_INDEX
                or durable["metadata"].get("worker_report_sha256") != FILE_HASHES["probe_report.json"]
                or durable["metadata"].get("checker_report_sha256") != FILE_HASHES["independent_checker.json"]):
            raise ValueError("exact worker/full-raw and final-checker Library readbacks required")
        allocation_gate("paired_fresh_C1b_freeze_saved_descriptors",
            {"matrix_payload_bytes": 0,
             "workspace_bytes": 4 * len(json.dumps(report["artifacts"]))
                                + 4 * len(json.dumps(new_source)) + (1 << 20),
             "validation_only": True})
        self.report = report
        self._artifacts = copy.deepcopy(report["artifacts"])
        for descriptor in self._artifacts.values():
            path = bound_path(self.directory, descriptor["path"])
            if file_sha(path) != descriptor["file_sha256"]:
                raise ValueError("C1b saved artifact bytes differ")
        self.receipt = {"schema": SCHEMA, "source_head": HEAD,
            "new_head": new_source["head"], "file_hashes": dict(FILE_HASHES),
            "ABI_sha256": ABI_SHA, "artifact_manifest_sha256": ARTIFACT_DIGEST,
            "worker_Library_index": saved.WORKER_LIBRARY_INDEX,
            "checker_Library_file": saved.CHECKER_LIBRARY_FILE,
            "Library_receipt_hashes": [saved.WORKER_LIBRARY_RECEIPT_SHA,
                                       saved.CHECKER_LIBRARY_RECEIPT_SHA],
            "reviewed_added_dependencies": additions,
            "reviewed_changed_dependencies": [{"path": PROVIDER_PATH,
                "saved_sha256": PROVIDER_OLD_SHA, "new_sha256": PROVIDER_NEW_SHA,
                "reason": "six-line bounded opt-in structural-empty skip after label/index/value validation"}],
            "existing_dependencies_unchanged": False,
            "other_existing_dependencies_unchanged": True,
            "saved_source_identity_sha256": digest_json(report["source"]),
            "new_source_identity_sha256": digest_json(new_source),
            "new_source": copy.deepcopy(new_source),
            "complete_environment_equal": True,
            "validation_only_full_maps": True, "candidate_setup_uses_old_full_maps": False,
            "q_shapes": [list(shape) for shape in Q_SHAPES], "q_nnz": list(Q_NNZ),
            "numerical_equivalence": "NOT_RUN; caller must pass fresh all-q/cross comparisons before factors",
            "scope": "bounded paired-live all-four-q saved controls; no target or production qualification"}

    def load_csr(self, prefix, shape=None, *, csc=False):
        expected = CSR_SHAPES.get(prefix)
        if (expected is None or (shape is not None and tuple(shape) != expected)
                or (prefix in Q_CSR_NNZ and csc)):
            raise ValueError("only fixed validation shapes and full-width q CSR are admitted")
        arrays = [self.load(prefix + "_" + part) for part in ("data", "indices", "indptr")]
        values, indices, offsets = arrays
        compressed, width = (expected[1], expected[0]) if csc else expected
        if (values.ndim != 1 or indices.ndim != 1 or offsets.ndim != 1
                or str(values.dtype) != "complex128" or str(indices.dtype) != "int32"
                or str(offsets.dtype) != "int32" or len(values) != len(indices)
                or len(offsets) != compressed + 1 or int(offsets[0]) != 0
                or int(offsets[-1]) != len(values)
                or any(int(a) > int(b) for a, b in zip(offsets, offsets[1:]))
                or any(int(i) < 0 or int(i) >= width for i in indices)
                or (prefix in Q_CSR_NNZ and len(values) != Q_CSR_NNZ[prefix])):
            raise ValueError("saved CSR/CSC full-width/NNZ/index inventory differs before construction")
        self.allocation_gate("paired_fresh_C1b_validation_sparse_constructor_" + prefix,
            {"matrix_payload_bytes": sum(int(a.nbytes) for a in arrays), "workspace_bytes": 1 << 20,
             "validation_only": True, "possible_SciPy_constructor_copy_included": True})
        from scipy import sparse
        cls = sparse.csc_matrix if csc else sparse.csr_matrix
        matrix = cls(tuple(arrays), shape=expected, copy=False)
        if prefix in Q_CSR_NNZ and (not matrix.has_sorted_indices or not matrix.has_canonical_format):
            raise ValueError("saved q CSR validation control is noncanonical")
        # Historical full maps may be unsorted. Preserve their original bytes;
        # a consumer needing canonical storage must own a separately gated copy.
        for array in (matrix.data, matrix.indices, matrix.indptr):
            array.setflags(write=False)
        return matrix

    def q_block(self, q):
        if type(q) is not int or q not in range(4):
            raise ValueError("paired-live reader admits explicit integer q0..q3 only")
        return self.load_csr(f"q_{q}_S", Q_SHAPES[q])


__all__ = ("PairedFreshC1bAuthority",)
