"""Saved-only all-eight compact projection replay; no FE/JIT/factor/PDE path.

The caller binds frozen source, report/checker file hashes, ABI, watchdog and
Library receipts before admission. ``load_array`` must enforce descriptor file
SHA/path binding (the existing ``_Candidate.load`` satisfies that contract).
This module additionally admits every read before invoking that callback and
checks readonly shape/dtype/payload, finite entries and snapshot numeric hashes.
Only one accumulator is live at once. Maps/recipes/saved targets and Python or
native workspaces are outside its named-array budget and use the external gate.

The baseline loader executes actual hash-verified source bytes in src.solvers;
its identity is a Git blob, never a fabricated old commit. Matched timing uses
an identical small recipe subset, callbacks, JSON encoding and owned budget.
It cannot be used to repeat the historical full baseline traversal.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import struct
import sys
from time import perf_counter
from types import ModuleType

import numpy as np
from scipy import sparse

from .original_port_blocks import CachedPortCorrection, DiagonalOriginalPortBlock

SCHEMA = "task40extra.saved-projection-support-replay.v1"
SCOPE = "saved_only_no_FE_JIT_new_factor_PDE"
BASELINE_GIT_BLOB = "235892c6bd8692aef6e9059611fdd9cdcf9fc688"
BASELINE_SHA256 = "ac7f73b51ce67e7a0655ab71af1136c56d70f86ca1c4e42a1634782b0672f925"
PAIRS = ((0, 0), (0, 1), (1, 0), (1, 1))


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _sha(value):
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def load_verified_accumulator(source_bytes, *, expected_sha256, git_blob=None):
    """Load exact source bytes with normal package-relative imports.

    A supplied Git blob is independently recomputed from the object header and
    bytes. This function performs no Git operation and makes no commit claim.
    """
    _require(isinstance(source_bytes, bytes), "verified source must be bytes")
    digest = hashlib.sha256(source_bytes).hexdigest()
    _require(re.fullmatch("[0-9a-f]{64}", expected_sha256) and digest == expected_sha256,
             "frozen accumulator source SHA differs before execution")
    if git_blob is not None:
        actual = hashlib.sha1(b"blob " + str(len(source_bytes)).encode() + b"\0" + source_bytes).hexdigest()
        _require(git_blob == actual, "frozen Git blob differs before execution")
    name = "src.solvers._saved_projection_" + digest
    existing = sys.modules.get(name)
    if existing is not None:
        _require(existing.__frozen_source_sha256__ == digest
                 and existing.__frozen_git_blob__ == git_blob, "frozen module identity differs")
        return existing.BoundedCompactQAccumulator
    module = ModuleType(name)
    module.__package__ = "src.solvers"
    module.__file__ = "verified-git-blob:" + git_blob if git_blob else "verified-source-sha256:" + digest
    module.__frozen_source_sha256__ = digest
    module.__frozen_git_blob__ = git_blob
    sys.modules[name] = module
    try:
        exec(compile(source_bytes, module.__file__, "exec"), module.__dict__)
    except BaseException:
        del sys.modules[name]
        raise
    return module.BoundedCompactQAccumulator


def _source_identity(accumulator_class, metadata):
    _require(isinstance(metadata, dict) and metadata.get("scope") == SCOPE,
             "frozen saved-only source metadata required")
    for field in ("candidate_source_sha256", "worker_report_sha256", "independent_checker_sha256"):
        _require(re.fullmatch("[0-9a-f]{64}", metadata.get(field, "")), "missing source hash: " + field)
    _require(re.fullmatch("[0-9a-f]{40}", metadata.get("source_git_head", "")), "frozen source Git HEAD required")
    module = sys.modules.get(accumulator_class.__module__)
    _require(module is not None and getattr(module, "__frozen_source_sha256__", None)
             == metadata["candidate_source_sha256"], "accumulator must be loaded from verified source bytes")
    return {"source_sha256": module.__frozen_source_sha256__,
            "git_blob": module.__frozen_git_blob__, "source_git_head": metadata["source_git_head"]}


class _Events:
    """The same admitted gate and deterministic JSONL encoding for both paths."""
    def __init__(self, allocation_gate, event, implementation):
        _require(callable(allocation_gate) and callable(event), "gate and event callbacks required")
        self.allocation_gate, self.event, self.implementation = allocation_gate, event, implementation
        self.event_count = self.log_bytes = self.read_count = 0

    def emit(self, kind, **facts):
        record = {"kind": kind, "implementation": self.implementation, **facts}
        # The external sink receives this exact encoding to make log-byte
        # accounting and serialization overhead comparable and reviewable.
        encoded = _json_bytes(record) + b"\n"
        self.event(record, encoded)
        self.event_count += 1
        self.log_bytes += len(encoded)

    def gate(self, label, facts):
        self.allocation_gate(label, facts)
        self.emit("allocation_admitted", label=label, **facts)

    def accumulator_gate(self, label, payload=0, workspace=0, **facts):
        self.gate(label, {"matrix_payload_bytes": int(payload), "workspace_bytes": int(workspace), **facts})


def _numeric_sha(value):
    digest = hashlib.sha256(repr((value.shape, str(value.dtype))).encode())
    # A Fortran matrix's row is strided. Copy only a bounded row chunk to
    # preserve the producer's literal C-order hash without a matrix copy.
    rows = (value,) if value.ndim < 2 else value
    for row in rows:
        flat = row.reshape(-1)
        for first in range(0, flat.size, 65536):
            digest.update(flat[first:first + 65536].tobytes(order="C"))
    return digest.hexdigest()


class _Read:
    def __init__(self, descriptors, load_array, events):
        _require(callable(load_array), "verified saved-array callback required")
        self.descriptors, self.load_array, self.events = descriptors, load_array, events

    def descriptor(self, ref):
        name = ref if isinstance(ref, str) else ref["name"]
        descriptor = self.descriptors[name]
        dtype, shape = np.dtype(descriptor["dtype"]), descriptor["shape"]
        _require(isinstance(shape, list) and all(type(v) is int and v >= 0 for v in shape)
                 and dtype.kind in "bifu c".replace(" ", "") and not dtype.hasobject
                 and descriptor["payload_bytes"] == math.prod(shape) * dtype.itemsize
                 and re.fullmatch("[0-9a-f]{64}", descriptor.get("file_sha256", "")),
                 "invalid primitive descriptor: " + name)
        if isinstance(ref, dict):
            _require(ref.get("shape") == shape and ref.get("dtype") == str(dtype)
                     and ref.get("numeric_bytes") == descriptor["payload_bytes"]
                     and re.fullmatch("[0-9a-f]{64}", ref.get("sha256", "")),
                     "snapshot reference differs from saved inventory: " + name)
            callback_ref = ref.get("callback_reference")
            _require(callback_ref is None or all(callback_ref.get(k) == descriptor.get(k)
                     for k in ("path", "shape", "dtype", "payload_bytes", "file_sha256")),
                     "snapshot callback descriptor differs: " + name)
        return name, descriptor

    def load(self, ref):
        name, descriptor = self.descriptor(ref)
        payload = int(descriptor["payload_bytes"])
        self.events.gate("saved_projection_read/" + name, {
            "matrix_payload_bytes": payload, "workspace_bytes": (1 << 20) + 2 * min(payload, 1 << 20),
            "before_array_open": True, "readonly_array_required": True,
            "descriptor_file_sha256": descriptor["file_sha256"],
            "file_hash_enforcement": "required_of_load_array_callback"})
        value = self.load_array(ref)
        _require(isinstance(value, np.ndarray) and list(value.shape) == descriptor["shape"]
                 and str(value.dtype) == descriptor["dtype"] and value.nbytes == payload
                 and value.ndim <= 2 and (value.flags.c_contiguous or value.flags.f_contiguous)
                 and not value.flags.writeable, "readonly contiguous saved array differs: " + name)
        flat = value.ravel(order="K")
        for first in range(0, flat.size, 65536):
            _require(np.isfinite(flat[first:first + 65536]).all(), "nonfinite saved array: " + name)
        numeric_sha = _numeric_sha(value)
        if isinstance(ref, dict):
            _require(numeric_sha == ref["sha256"], "snapshot numeric SHA differs: " + name)
        self.events.read_count += 1
        self.events.emit("saved_array_verified", name=name, payload_bytes=payload,
                         file_sha256=descriptor["file_sha256"], numeric_sha256=numeric_sha,
                         numeric_hash_bound_to_snapshot=isinstance(ref, dict))
        return value

    def csr(self, record):
        shape = tuple(record["shape"])
        _require(len(shape) == 2 and all(type(v) is int and v >= 0 for v in shape), "invalid saved CSR shape")
        refs = tuple(record[k] for k in ("data", "indices", "indptr"))
        payload = sum(self.descriptor(ref)[1]["payload_bytes"] for ref in refs)
        self.events.gate("saved_projection_CSR_constructor", {
            "matrix_payload_bytes": payload, "workspace_bytes": 2 * payload + (1 << 20),
            "before_array_open": True, "constructor_copy_allowance_bytes": payload})
        data, indices, indptr = (self.load(ref) for ref in refs)
        _require(data.ndim == indices.ndim == indptr.ndim == 1 and data.dtype == np.complex128
                 and indices.dtype.kind == indptr.dtype.kind == "i" and data.shape == indices.shape
                 and len(indptr) == shape[0] + 1 and int(indptr[0]) == 0
                 and int(indptr[-1]) == len(data), "invalid raw CSR buffers")
        previous = 0
        for row in range(shape[0]):
            end = int(indptr[row + 1])
            _require(previous <= end <= len(data), "invalid raw CSR row pointer")
            last = -1
            for k in range(previous, end):
                column = int(indices[k])
                _require(last < column < shape[1], "saved CSR must be canonical and in range")
                last = column
            previous = end
        return sparse.csr_matrix((data, indices, indptr), shape=shape, copy=False)


def _inventory(report, read):
    snapshots = report["local_compact_snapshots"]
    _require(len(snapshots) == 2 and [s["twist"] for s in snapshots] == [0, 1]
             and [s["q_indices"] for s in snapshots] == [[0, 2], [1, 3]], "exact two-twist/all-four-q inventory required")
    blocks = report["reformed_blocks"]
    _require(len(blocks) == 4 and [b["q"] for b in blocks] == [0, 1, 2, 3], "all-four diagonal targets required")
    shapes = {b["q"]: b["shape"] for b in blocks}
    for block in blocks:
        _require(len(block["shape"]) == 2 and block["shape"][0] == block["shape"][1]
                 and block["csr_prefix"] == f"q_{block['q']}_S", "diagonal target identity differs")
    crosses = report["cross_blocks"]
    wanted = {(0, 2), (2, 0), (1, 3), (3, 1)}
    _require(len(crosses) == 4 and {(c["p"], c["q"]) for c in crosses} == wanted,
             "all-four ordered cross targets required")
    for cross in crosses:
        _require(cross["csr_prefix"] == f"cross_{cross['p']}_{cross['q']}", "cross target identity differs")
    for snapshot in snapshots:
        qmaps = snapshot["qmaps"]
        _require(len(qmaps) == 2 and qmaps[0]["shape"][0] == qmaps[1]["shape"][0]
                 and [m["shape"][1] for m in qmaps] == [shapes[q][0] for q in snapshot["q_indices"]],
                 "complete qmap dimensions differ")
        expected = {"ports/H_original"} | {f"volume/cell/{i}" for i in range(len(snapshot["cells"]))}
        expected |= {f"direct/{side}/port/{i}" for side in ("C", "-D") for i in range(snapshot["port_count"])}
        for i, cell in enumerate(snapshot["cells"]):
            _, descriptor = read.descriptor(cell["ports"])
            _require(len(descriptor["shape"]) == 1, "cell ports must be an index vector")
            if descriptor["shape"][0]:
                expected |= {f"cell/{side}/{i}" for side in ("C_hat", "-D_hat", "Hhat_correction")}
        labels = [item["label"] for item in snapshot["recipes"]]
        _require(len(labels) == len(set(labels)) and set(labels) == expected,
                 "exact complete compact recipe inventory differs")
        for item in snapshot["recipes"]:
            _require(item["kind"] in ("dense", "diagonal", "correction"), "unsupported saved recipe kind")
            for key in ("rows", "cols") + (("Di", "XiB") if item["kind"] == "correction" else ("values",)):
                read.descriptor(item[key])
        for record in qmaps:
            for key in ("data", "indices", "indptr"):
                read.descriptor(record[key])
    return snapshots, shapes


def _target(read, p, q, shapes):
    prefix = f"q_{q}_S" if p == q else f"cross_{p}_{q}"
    return read.csr({"shape": [shapes[p][0], shapes[q][0]],
                     **{k: prefix + "_" + k for k in ("data", "indices", "indptr")}})


def _recipe(read, item, native_rows):
    rows, cols = read.load(item["rows"]), read.load(item["cols"])
    for ids in (rows, cols):
        _require(ids.ndim == 1 and ids.dtype.kind in "iu", "recipe native indices must be integer vectors")
        seen = set()
        for value in ids:
            index = int(value)
            _require(0 <= index < native_rows and index not in seen, "recipe native index duplicate/out of range")
            seen.add(index)
    if item["kind"] == "correction":
        di, xib = read.load(item["Di"]), read.load(item["XiB"])
        _require(di.dtype == xib.dtype == np.complex128 and di.ndim == xib.ndim == 2
                 and di.shape[0] == len(rows) and xib.shape[1] == len(cols)
                 and di.shape[1] == xib.shape[0], "saved factorized recipe dimensions differ")
        values = CachedPortCorrection(rows, di, xib)
    else:
        values = read.load(item["values"])
        _require(values.dtype == np.complex128 and values.shape ==
                 ((len(rows), len(cols)) if item["kind"] == "dense" else (len(rows),))
                 and (item["kind"] != "diagonal" or len(rows) == len(cols)),
                 "saved dense/diagonal recipe dimensions differ")
        if item["kind"] == "diagonal":
            read.events.gate("saved_projection_diagonal_constructor", {
                "matrix_payload_bytes": values.nbytes, "workspace_bytes": (1 << 20) + 3 * values.nbytes,
                "before_diagonal_copy": True, "public_original_H_identity_constructor": True,
                "owned_diagonal_reserved_from_accumulator_budget": True})
            values = DiagonalOriginalPortBlock(values, tuple(("saved", int(row)) for row in rows))
    return rows, cols, values


def _norm_data(data):
    norm = maximum = 0.0
    for value in data:
        magnitude = abs(complex(value))
        norm = math.hypot(norm, magnitude)
        maximum = max(maximum, magnitude)
    return norm, maximum


def csr_fingerprint(matrix):
    """The repository sparse_hash encoding, streamed without numeric copies."""
    digest = hashlib.sha256(struct.pack("<qq", *matrix.shape))
    for values in (matrix.indptr, matrix.indices, matrix.data):
        _require(values.flags.c_contiguous, "CSR fingerprint requires existing contiguous buffers")
        digest.update(str(values.dtype).encode() + b"\0")
        digest.update(memoryview(values).cast("B"))
    return {"shape": list(matrix.shape), "nnz": int(matrix.nnz), "CSR_sha256": digest.hexdigest(),
            "buffer_dtypes": [str(v.dtype) for v in (matrix.indptr, matrix.indices, matrix.data)],
            "CSR_payload_bytes": sum(v.nbytes for v in (matrix.indptr, matrix.indices, matrix.data))}


def compare_complete_csr(actual, expected, *, diagonal_scales=None, limit=1e-11):
    """Scalar canonical merge checks every entry, without a difference matrix."""
    _require(actual.shape == expected.shape and 0 < limit <= 1e-11, "complete comparison shape/limit differs")
    norm = maximum = 0.0
    compared = 0
    for row in range(actual.shape[0]):
        i, iend = int(actual.indptr[row]), int(actual.indptr[row + 1])
        j, jend = int(expected.indptr[row]), int(expected.indptr[row + 1])
        while i < iend or j < jend:
            ai = int(actual.indices[i]) if i < iend else actual.shape[1]
            ej = int(expected.indices[j]) if j < jend else expected.shape[1]
            if ai == ej:
                error = actual.data[i] - expected.data[j]
                i += 1
                j += 1
            elif ai < ej:
                error = actual.data[i]
                i += 1
            else:
                error = -expected.data[j]
                j += 1
            magnitude = abs(complex(error))
            norm = math.hypot(norm, magnitude)
            maximum = max(maximum, magnitude)
            compared += 1
    reference_norm, reference_maximum = _norm_data(expected.data)
    scales = (("Frobenius", norm, reference_norm), ("maximum_entry", maximum, reference_maximum))
    if diagonal_scales is not None:
        _require(len(diagonal_scales) == 2, "both corresponding diagonal norms required")
        scales = tuple((f"{kind}_diagonal{i}", error, float(scale))
                       for kind, error in (("Frobenius", norm), ("maximum_entry", maximum))
                       for i, scale in enumerate(diagonal_scales))
    records = []
    for name, error, scale in scales:
        finite = math.isfinite(error) and math.isfinite(scale) and scale >= 0
        passed = finite and (error == 0 if scale == 0 else error <= limit * scale)
        records.append({"name": name, "error_norm": error if math.isfinite(error) else None,
                        "operation_scale": scale if math.isfinite(scale) else None, "limit": limit,
                        "relative": (error / scale if scale else 0.0) if finite else None,
                        "zero_scale_rule": "error_must_be_exactly_zero", "passed": bool(passed),
                        "all_entries_checked": True, "compared_union_entries": compared})
    return records


def _run_pair(snapshot, pair, recipes, read, events, accumulator_class, options, serialize):
    maps = [read.csr(record) for record in snapshot["qmaps"]]
    p, q = pair
    gp, gq = snapshot["q_indices"][p], snapshot["q_indices"][q]
    diagonal_bytes = max((read.descriptor(item["values"])[1]["payload_bytes"]
                          for item in recipes if item["kind"] == "diagonal"), default=0)
    _require(options["max_owned_bytes"] > diagonal_bytes, "owned budget cannot admit diagonal recipe copy")
    accumulator_options = {**options, "max_owned_bytes": options["max_owned_bytes"] - diagonal_bytes}
    accumulator = accumulator_class((maps[p].shape[1], maps[q].shape[1]), gate=events.accumulator_gate, **accumulator_options)
    for item in recipes:
        rows, cols, values = _recipe(read, item, maps[0].shape[0])
        accumulator.add(maps[p], maps[q], rows, cols, values, item["label"])
        del rows, cols, values
    matrix = accumulator.finish()
    fingerprint = csr_fingerprint(matrix)
    if serialize is not None:
        events.gate("saved_projection_serialization", {"matrix_payload_bytes": 0,
                    "workspace_bytes": 1 << 20, "existing_CSR_payload_bytes": fingerprint["CSR_payload_bytes"]})
        serialize(gp, gq, matrix, events.implementation)
    return accumulator, matrix, {"twist": snapshot["twist"], "p": gp, "q": gq,
        "recipe_count": len(recipes), "ordered_recipe_labels_sha256": _sha([r["label"] for r in recipes]),
        **fingerprint, "peak_projection_owned_upper_bytes": accumulator.peak_owned_upper_bytes + diagonal_bytes,
        "owned_budget_bytes": options["max_owned_bytes"], "owned_diagonal_reservation_bytes": diagonal_bytes,
        "tiles_projected": accumulator.tiles_projected,
        "tiles_skipped_structural": getattr(accumulator, "tiles_skipped_structural", 0),
        "support_discoveries": getattr(accumulator, "support_discoveries", 0)}


def replay_saved_all8(report, *, accumulator_class, load_array, allocation_gate, event,
                      source_metadata, max_owned_bytes=128 << 20, tile_width=128,
                      index_dtype=np.int32, serialize=None, limit=1e-11):
    """Reconstruct all complete diagonal/cross CSR targets from exact recipes.

    No factor, recovery, native state/action, RHS or FE array is read. ``event``
    accepts ``(record, encoded_jsonl_bytes)``. The same callback contract is used
    for matched timing. Optional serialization must consume, not retain, CSR.
    """
    identity = _source_identity(accumulator_class, source_metadata)
    events = _Events(allocation_gate, event, "new")
    read = _Read(report["artifacts"], load_array, events)
    snapshots, shapes = _inventory(report, read)  # metadata before any load
    started = perf_counter()
    pairs = []
    options = dict(max_owned_bytes=max_owned_bytes, tile_width=tile_width, index_dtype=index_dtype)
    for snapshot in snapshots:
        diagonal_norms = []
        for q in snapshot["q_indices"]:
            target = _target(read, q, q, shapes)
            diagonal_norms.append(_norm_data(target.data)[0])
            del target
        for pair in PAIRS:
            accumulator, matrix, record = _run_pair(snapshot, pair, snapshot["recipes"], read,
                                                    events, accumulator_class, options, serialize)
            gp, gq = record["p"], record["q"]
            target = _target(read, gp, gq, shapes)
            events.gate("saved_projection_complete_comparison", {"matrix_payload_bytes": 0,
                "workspace_bytes": 1024, "scalar_merge_without_difference_CSR": True,
                "all_entries_checked": True})
            checks = compare_complete_csr(matrix, target,
                diagonal_scales=None if gp == gq else diagonal_norms, limit=limit)
            record["saved_target"] = csr_fingerprint(target)
            record["checks"] = checks
            record["passed"] = all(c["passed"] for c in checks)
            events.emit("complete_pair_compared", **record)
            pairs.append(record)
            del accumulator, matrix, target
    passed = len(pairs) == 8 and all(p["passed"] for p in pairs)
    return {"schema": SCHEMA, "status": "ALL8_SAVED_PROJECTION_REPLAY_PASS" if passed else "ALL8_SAVED_PROJECTION_REPLAY_FAILED",
            "passed": passed, "scope": SCOPE, "source": identity, "source_metadata": source_metadata,
            "snapshot_inventory_sha256": _sha(snapshots), "pairs": pairs, "all8_complete": len(pairs) == 8,
            "limit": limit, "wall_seconds": perf_counter() - started,
            "event_count": events.event_count, "log_bytes": events.log_bytes, "array_reads": events.read_count,
            "FE_calls": 0, "JIT_calls": 0, "new_factor_calls": 0, "PDE_calls": 0,
            "one_accumulator_live_at_once": True, "owned_budget_excludes_borrowed_maps_recipes_targets": True}


def select_matched_recipe_subset(snapshot, *, volume_cells=2):
    """Pure metadata selection; keep source order and representative families."""
    _require(volume_cells in (2, 4), "matched baseline permits only first two/four volume cells")
    recipes = snapshot["recipes"]
    wanted = {f"volume/cell/{i}" for i in range(min(volume_cells, len(snapshot["cells"])))}
    families = ((lambda r: r["kind"] == "diagonal"), (lambda r: r["kind"] == "correction"),
                (lambda r: r["label"].startswith("cell/C_hat/")),
                (lambda r: r["label"].startswith("cell/-D_hat/")),
                (lambda r: r["label"].startswith("direct/C/")),
                (lambda r: r["label"].startswith("direct/-D/")))
    for matches in families:
        candidate = next((r for r in recipes if matches(r)), None)
        if candidate is not None:
            wanted.add(candidate["label"])
    result = [r for r in recipes if r["label"] in wanted]
    _require(result and len(result) <= volume_cells + len(families), "bounded representative subset differs")
    return result


def compare_matched_subset(report, *, old_accumulator_class, new_accumulator_class,
                           load_array, allocation_gate, event, source_metadata,
                           max_owned_bytes=128 << 20, tile_width=128,
                           index_dtype=np.int32, volume_cells=2, serialize=None):
    """Measure actual OLD/NEW identical bounded subsets; never old full replay."""
    new_identity = _source_identity(new_accumulator_class, source_metadata)
    old_module = sys.modules.get(old_accumulator_class.__module__)
    _require(old_module is not None and getattr(old_module, "__frozen_git_blob__", None) == BASELINE_GIT_BLOB
             and getattr(old_module, "__frozen_source_sha256__", None) == BASELINE_SHA256,
             "matched baseline must be the verified historical Git blob bytes")
    options = dict(max_owned_bytes=max_owned_bytes, tile_width=tile_width, index_dtype=index_dtype)
    runs = []
    for implementation, accumulator_class in (("old", old_accumulator_class), ("new", new_accumulator_class)):
        events = _Events(allocation_gate, event, implementation)
        read = _Read(report["artifacts"], load_array, events)
        snapshots, _ = _inventory(report, read)
        started = perf_counter()
        pairs = []
        for snapshot in snapshots:
            recipes = select_matched_recipe_subset(snapshot, volume_cells=volume_cells)
            for pair in PAIRS:
                accumulator, matrix, record = _run_pair(snapshot, pair, recipes, read, events,
                                                        accumulator_class, options, serialize)
                events.emit("matched_pair_complete", **record)
                pairs.append(record)
                del accumulator, matrix
        runs.append({"implementation": implementation, "wall_seconds": perf_counter() - started,
                     "event_count": events.event_count, "log_bytes": events.log_bytes,
                     "array_reads": events.read_count, "pairs": pairs})
    matches = []
    for old, new in zip(runs[0]["pairs"], runs[1]["pairs"], strict=True):
        _require((old["p"], old["q"], old["ordered_recipe_labels_sha256"])
                 == (new["p"], new["q"], new["ordered_recipe_labels_sha256"]), "matched exact recipe sequence differs")
        matches.append({"p": old["p"], "q": old["q"], "bitwise_CSR_equal":
                        all(old[k] == new[k] for k in ("CSR_sha256", "shape", "nnz", "buffer_dtypes"))})
    equal = len(matches) == 8 and all(m["bitwise_CSR_equal"] for m in matches)
    return {"schema": SCHEMA, "status": "MATCHED_SUBSET_BITWISE_PASS" if equal else "MATCHED_SUBSET_BITWISE_FAILED",
            "scope": SCOPE, "passed": equal, "source": new_identity,
            "baseline": {"git_blob": BASELINE_GIT_BLOB, "source_sha256": BASELINE_SHA256},
            "volume_cells": volume_cells, "runs": runs, "pairs": matches,
            "same_callbacks_serialization_owned_budget": True, "max_owned_bytes": max_owned_bytes,
            "tile_width": tile_width, "old_full_replay_permitted": False,
            "FE_calls": 0, "JIT_calls": 0, "new_factor_calls": 0, "PDE_calls": 0}


__all__ = ("replay_saved_all8", "compare_matched_subset", "select_matched_recipe_subset",
           "load_verified_accumulator", "compare_complete_csr", "csr_fingerprint")
