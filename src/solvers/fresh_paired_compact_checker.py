"""Saved-only checker for the fresh same80 paired compact inverse.

No FE assembly, JIT, new factor, inverse application or PDE solve is performed.
The original live FFCx volume vectors are saved authorities. Compact recipes,
carrier algebra, cached cell-LU applications, MPC recovery and mode outputs
are recomputed independently. Saved q maps and their column diagnostics remain
producer controls: this checker does not reconstruct geometric entity maps.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from types import SimpleNamespace

SCHEMA = "task40extra.fresh-paired-live-compact-inverse.v1"
CHECKER_SCHEMA = "task40extra.fresh-paired-live-compact-checker.v1"
Q_ROWS = (1884, 1960, 1960, 1960)
PORT_COUNTS = (228, 304)
SOURCES = ("generic", "interior_only", "physical", "notch_supported")
CROSS_PAIRS = {(0, 2), (2, 0), (1, 3), (3, 1)}
VECTOR_SUFFIXES = ("rhs_storage", "solution_storage", "original_action", "volume_action",
                   "coupling_action", "auxiliary_ports", "projection", "normalization_h",
                   "native_residual", "augmented_FE_residual", "augmented_port_residual")
OUTPUT_SUFFIXES = ("recovered_field", "plane_total_auxiliary", "plane_outgoing_auxiliary",
                   "plane_incident_projections", "plane_electric", "plane_magnetic",
                   "direct_plane_outgoing_power_diagnostic", "mode_local_amplitude_scale",
                   "plane_electric_scale", "plane_magnetic_scale", "mode_power_operation_scale")
GLOBAL_OUTPUT_SUFFIXES = ("global_total_auxiliary", "global_incident_projections")
DTYPE_BYTES = {"complex128": 16, "float64": 8, "int64": 8, "int32": 4,
               "uint64": 8, "uint32": 4, "int8": 1, "uint8": 1, "bool": 1}


def _require(condition, message):
    if not condition:
        raise ValueError(message)


def _sha_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                    allow_nan=False).encode()).hexdigest()


def _numeric_sha(value):
    digest = hashlib.sha256(repr((value.shape, str(value.dtype))).encode())
    if value.ndim < 2:
        digest.update(value.tobytes(order="C"))
    else:
        for row in value:
            digest.update(row.tobytes(order="C"))
    return digest.hexdigest()


def _refs(value):
    """Find actual snapshot references, without manufacturing another schema."""
    if isinstance(value, dict):
        if {"name", "shape", "dtype", "numeric_bytes", "sha256"}.issubset(value):
            yield value
        else:
            for child in value.values():
                yield from _refs(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            yield from _refs(child)


def validate_candidate_inventory(report, authority_report):
    """Pure metadata admission; must precede every candidate mmap/CSR load."""
    stage = report.get("stage")
    _require(report.get("schema") == SCHEMA and stage in ("prefactor", "solve")
             and report.get("status") == ("FRESH_PAIRED_ALLQ_PREFACTOR_PASS" if stage == "prefactor"
                                         else "FRESH_PAIRED_COMPACT_FULL3D_INVERSE_PASS")
             and report.get("prefactor_only") is (stage == "prefactor")
             and report.get("factor_count") == (0 if stage == "prefactor" else 4)
             and report.get("degree") == 4 and report.get("physical_mode_count") == 532,
             "fresh paired stage/schema/factor inventory differs")
    _require(all(report.get(k) is False for k in ("candidate_full_Ny_CSR_created",
                                                 "candidate_full_F_created", "candidate_full_Q_created"))
             and report.get("resident_Hhat_bytes") == 0
             and report.get("all_prefactor_gates_before_factors") is True,
             "candidate compact ownership/prefactor gates differ")
    layout = report.get("layout", {})
    _require(all(layout.get(k) == v for k, v in {"full_storage_rows": 17204, "independent_rows": 15872,
             "ny": 4, "rows_per_q": 3968, "all_q": [0, 1, 2, 3]}.items()),
             "complete original same80 layout is required")
    keys = report.get("global_mode_keys", [])
    _require(len(keys) == 532 and len({tuple(k) for k in keys}) == 532
             and all(len(k) == 4 for k in keys) and keys == authority_report.get("mode_keys")
             and report.get("input_sha256") == authority_report.get("input_sha256")
             and report.get("physical_generator_manifest_sha256") == authority_report.get("mode_manifest_sha256"),
             "exact full532 physical generator/input inventory differs")
    blocks = report.get("reformed_blocks", [])
    _require(len(blocks) == 4 and [v.get("q") for v in blocks] == list(range(4)),
             "ordered exact all4 diagonal block inventory required")
    for q, block in enumerate(blocks):
        _require(block.get("shape") == [Q_ROWS[q], Q_ROWS[q]] and block.get("csr_prefix") == f"q_{q}_S"
                 and block.get("physical_alias_count") == (76, 152, 152, 152)[q]
                 and type(block.get("nnz")) is int and block["nnz"] > 0
                 and re.fullmatch("[0-9a-f]{64}", block.get("CSR_sha256", "")),
                 "complete q diagonal dimensions/hash/aliases required")
    crosses = report.get("cross_blocks", [])
    _require(len(crosses) == 4 and {(v.get("p"), v.get("q")) for v in crosses} == CROSS_PAIRS,
             "four ordered same-twist cross directions required")
    for item in crosses:
        _require(item.get("csr_prefix") == f"cross_{item['p']}_{item['q']}", "cross CSR identity differs")
    raw = report.get("raw_sector_receipts", [])
    local = report.get("local_compact_snapshots", [])
    _require(len(raw) == 2 and [v.get("b") for v in raw] == [0, 1]
             and len(local) == 2 and [v.get("twist") for v in local] == [0, 1],
             "both fresh sector receipts and actual compact snapshots required")
    union = []
    for b, (receipt, snapshot) in enumerate(zip(raw, local, strict=True)):
        indices = [i for i, key in enumerate(keys) if int(key[2]) % 2 == b]
        _require(receipt.get("sector_original_indices") == indices and len(indices) == PORT_COUNTS[b]
                 and snapshot.get("port_count") == PORT_COUNTS[b] and snapshot.get("q_indices") == [b, b + 2]
                 and len(snapshot.get("cells", [])) == 40 and len(snapshot.get("qmaps", [])) == 2
                 and len(snapshot.get("carrier_records", [])) == PORT_COUNTS[b]
                 and set(snapshot.get("partition", {})) == {"independent", "trace", "interior", "slaves"}
                 and snapshot.get("resident_dense_H_bytes") == snapshot.get("resident_Hhat_bytes") == 0
                 and type(snapshot.get("original_H_diagonal_bytes")) is int
                 and snapshot["original_H_diagonal_bytes"] == PORT_COUNTS[b] * 16,
                 "complete actual local40/228+304 cell/port/map partition differs")
        _require([m.get("shape") for m in snapshot["qmaps"]] ==
                 [[3616 + PORT_COUNTS[b], Q_ROWS[q]] for q in (b, b + 2)], "complete two-branch q maps differ")
        labels = [v.get("label") for v in snapshot.get("recipes", [])]
        required_labels = {"ports/H_original"} | {f"volume/cell/{i}" for i in range(40)}
        required_labels |= {f"direct/{side}/port/{i}" for side in ("C", "-D") for i in range(PORT_COUNTS[b])}
        _require(len(set(labels)) == len(labels) and required_labels.issubset(labels),
                 "complete unique compact recipe inventory required")
        union.extend(indices)
    _require(sorted(union) == list(range(532)), "exact once-only 532 sector union required")
    shapes = {"independent_storage_rows": [15872], "actual_interior_positions": [8640],
              "full_mpc_slaves": [1332], "full_mpc_offsets": [17205], "port_original_H": [532],
              "port_q_labels": [532], "port_factor_coordinate_scale": [532]}
    required = set(shapes)
    required |= {"full_mpc_masters", "full_mpc_coefficients", "original_carrier_global_rows",
                 "original_carrier_ownership_range", "original_carrier_slave_rows", "original_mode_e_vectors",
                 "original_mode_k_vectors", "original_mode_outward_signs", "original_mode_magnetic_denominator",
                 "original_mode_boundary_area", "original_mode_incident_projections"}
    shapes.update({"original_carrier_global_rows": [], "original_carrier_ownership_range": [2],
                   "original_carrier_slave_rows": [1332], "original_mode_e_vectors": [532, 3],
                   "original_mode_k_vectors": [532, 3], "original_mode_outward_signs": [532],
                   "original_mode_magnetic_denominator": [], "original_mode_boundary_area": [],
                   "original_mode_incident_projections": [532]})
    for prefix in [f"q_{q}_S" for q in range(4)] + [v["csr_prefix"] for v in crosses] + ["original_port_C", "original_port_D"]:
        required |= {prefix + "_" + part for part in ("data", "indices", "indptr")}
    for q in range(4):
        for suffix in ("column_error_norms", "reference_column_norms"):
            shapes[f"q_{q}_map_{suffix}"] = [3968]
    for b in (0, 1):
        for suffix, size in (("state", 8940), ("alpha", PORT_COUNTS[b]), ("FE_rhs", 8940),
                             ("port_rhs", PORT_COUNTS[b]), ("reduced_rhs", 3616 + PORT_COUNTS[b]),
                             ("reduced_action", 3616 + PORT_COUNTS[b]), ("recovered", 8940)):
            shapes[f"twist_{b}_complete_recovery_{suffix}"] = [size]
        shapes[f"twist_{b}_original_H"] = [PORT_COUNTS[b]]
    if stage == "solve":
        _require(report.get("PDE_solved") is True and set(report.get("regular_sources", {})) == set(SOURCES)
                 and set(report.get("notched_sources", {})) == set(SOURCES)
                 and len(report.get("augmented_controls", [])) == 4
                 and [v.get("q") for v in report["augmented_controls"]] == list(range(4)),
                 "all original regular/notch four loads and augmented controls required")
        for packets in (report["regular_sources"], report["notched_sources"]):
            for packet in packets.values():
                output = packet.get("outputs", {})
                _require(output.get("status") == "representable_global_output"
                         and output.get("global_output_component_consistency_checked") is True
                         and output.get("finite_plane_mode_count") == 532,
                         "required producer global-output representability contract differs")
        factor = report.get("factor", {})
        inputs = factor.get("input_blocks", [])
        _require(factor.get("all_q_factors") == 4 and factor.get("all_four_retained_simultaneously") is True
                 and factor.get("factor_reuse_plus_minus_q") is False and len(inputs) == 4
                 and [v.get("q") for v in inputs] == list(range(4)), "actual all4 retained factor input inventory required")
        for q, item in enumerate(inputs):
            _require(all(item.get(k) == blocks[q][k] for k in ("shape", "nnz", "CSR_sha256")),
                     "saved factor detached from reformed diagonal CSR")
            for suffix in ("rhs_a", "rhs_b", "solution_a", "solution_a_repeat", "solution_b", "solution_sum", "action_a"):
                shapes[f"q_{q}_" + suffix] = [Q_ROWS[q]]
        before, after = report.get("live_cache_numeric_sha256_before", []), report.get("live_cache_numeric_sha256_after", [])
        _require(len(before) == 2 and before == after
                 and all(isinstance(v, str) and re.fullmatch("[0-9a-f]{64}", v) for v in before)
                 and len(report.get("live_cache_recipe_before", [])) == 2
                 and report["live_cache_recipe_before"] == report.get("live_cache_recipe_after")
                 and report.get("same_live_cache_owners_through_apply") is True
                 and report.get("cache_rebuilt_per_PC_apply") is False,
                 "complete same-live cache lifecycle producer proof required")
        for name in SOURCES:
            shapes[name + "_rhs"] = [15872]
            for prefix in ("regular_", "notch_"):
                label = prefix + name
                shapes[label + "_solution"] = [15872]
                required |= {label + "_" + s for s in VECTOR_SUFFIXES + OUTPUT_SUFFIXES + GLOBAL_OUTPUT_SUFFIXES}
                for suffix in VECTOR_SUFFIXES + OUTPUT_SUFFIXES + GLOBAL_OUTPUT_SUFFIXES:
                    shapes[label + "_" + suffix] = ([532, 3] if suffix in ("plane_electric", "plane_magnetic") else
                        [17204] if suffix in ("rhs_storage", "solution_storage", "original_action", "volume_action",
                                              "coupling_action", "native_residual", "augmented_FE_residual", "recovered_field") else [532])
        for q in range(4):
            label = f"aug_q_{q}"
            required |= {label + "_" + s for s in VECTOR_SUFFIXES +
                         ("FE_rhs", "port_rhs", "solution", "effective_rhs", "port_operation_scale")}
            for suffix in VECTOR_SUFFIXES + ("FE_rhs", "port_rhs", "solution", "effective_rhs", "port_operation_scale"):
                shapes[label + "_" + suffix] = ([15872] if suffix in ("FE_rhs", "solution", "effective_rhs") else
                    [17204] if suffix in ("rhs_storage", "solution_storage", "original_action", "volume_action",
                                          "coupling_action", "native_residual", "augmented_FE_residual") else [532])
    required.update(shapes)
    descriptors = report.get("artifacts", {})
    _require(required.issubset(descriptors), "complete required saved candidate arrays absent")
    for name, shape in shapes.items():
        _require(descriptors[name].get("shape") == shape, "saved array shape inventory differs: " + name)
    for name, descriptor in descriptors.items():
        shape, dtype = descriptor.get("shape"), descriptor.get("dtype")
        _require(isinstance(shape, list) and all(type(v) is int and v >= 0 for v in shape)
                 and dtype in DTYPE_BYTES and descriptor.get("payload_bytes") == math.prod(shape) * DTYPE_BYTES[dtype]
                 and re.fullmatch("[0-9a-f]{64}", descriptor.get("file_sha256", "")),
                 "primitive saved-array descriptor invalid: " + name)
    for ref in _refs(local):
        descriptor = descriptors.get(ref["name"], {})
        _require(ref["shape"] == descriptor.get("shape") and ref["dtype"] == descriptor.get("dtype")
                 and ref["numeric_bytes"] == descriptor.get("payload_bytes")
                 and re.fullmatch("[0-9a-f]{64}", ref["sha256"]), "snapshot reference not bound to saved inventory")
    return True


def metric_record(error, scale, limit):
    finite = all(math.isfinite(float(v)) and v >= 0 for v in (error, scale, limit))
    relative = (error / scale if scale else 0.0) if finite else None
    if relative is not None and not math.isfinite(relative):
        relative = None
    return {"error_norm": float(error) if math.isfinite(error) else None,
            "operation_scale": float(scale) if math.isfinite(scale) else None,
            "limit": float(limit) if math.isfinite(limit) else None,
            "relative": relative, "finite": finite,
            "zero_scale_rule": "error_must_be_exactly_zero",
            "passed": bool(finite and (error <= limit * scale if scale > 0 else error == 0))}


def stable_norm(value):
    import numpy as np
    value = np.asarray(value)
    peak = float(np.max(np.abs(value), initial=0))
    return peak * float(np.sqrt(np.sum(np.abs(value / peak) ** 2))) if peak else 0.0


class _Checks:
    def __init__(self):
        self.records = []

    def compare(self, label, actual, expected, *, scale=None, limit=1e-11, **facts):
        import numpy as np
        _require(np.shape(actual) == np.shape(expected), "compared shape differs: " + label)
        difference = np.asarray(actual) - np.asarray(expected)
        record = {"name": label, **metric_record(stable_norm(difference),
                    stable_norm(expected) if scale is None else float(scale), limit), **facts}
        self.records.append(record)
        _require(record["passed"], "saved algebra gate failed: " + label)
        return record

    def modes(self, label, actual, expected, scales, *, limit=1e-10):
        import numpy as np
        a, e, scales = np.asarray(actual), np.asarray(expected), np.asarray(scales)
        _require(a.shape == e.shape and len(a) == len(scales) and scales.ndim == 1
                 and np.isfinite(scales).all() and np.all(scales >= 0), "per-mode comparison inventory differs")
        errors = np.abs(a - e) if a.ndim == 1 else np.asarray([stable_norm(v) for v in a - e])
        passed = np.isfinite(errors).all() and np.all(errors <= limit * scales) and not np.any((scales == 0) & (errors != 0))
        ratios = np.divide(errors, scales, out=np.zeros_like(errors, dtype=float), where=scales > 0)
        maximum = float(np.max(ratios, initial=0))
        self.records.append({"name": label, "compared_modes": len(a), "limit": limit,
                             "maximum_relative": maximum if math.isfinite(maximum) else None,
                             "zero_scale_rule": "error_must_be_exactly_zero", "passed": bool(passed)})
        _require(passed, "independent per-mode gate failed: " + label)


class _Candidate:
    """Each candidate load admits its declared bytes before opening any mmap."""
    def __init__(self, directory, report, gate):
        self.directory, self.descriptors, self.gate = Path(directory).resolve(), report["artifacts"], gate

    def path(self, relative):
        from .fresh_c1b_saved_authority import bound_path
        return bound_path(self.directory, relative)

    def json(self, relative, expected_sha):
        path = self.path(relative)
        size = path.stat().st_size
        _require(size <= 16 << 20 and _sha_file(path) == expected_sha, "bound receipt hash/size differs")
        self.gate("paired_checker_receipt_" + relative, {"matrix_payload_bytes": 0, "workspace_bytes": 6 * size + (1 << 20)})
        def pairs(items):
            result = {}
            for key, value in items:
                _require(key not in result, "duplicate receipt JSON key")
                result[key] = value
            return result
        def invalid(value):
            raise ValueError("nonfinite receipt JSON: " + value)
        return json.loads(path.read_text(), object_pairs_hook=pairs, parse_constant=invalid)

    def load(self, reference):
        import numpy as np
        name = reference if isinstance(reference, str) else reference["name"]
        descriptor = self.descriptors[name]
        self.gate("paired_checker_mmap_" + name, {"matrix_payload_bytes": int(descriptor["payload_bytes"]),
                  "workspace_bytes": (1 << 20) + 2 * min(int(descriptor["payload_bytes"]), 1 << 20),
                  "readonly_mmap": True, "before_array_open": True})
        path = self.path(descriptor["path"])
        _require(_sha_file(path) == descriptor["file_sha256"], "candidate file SHA differs: " + name)
        value = np.load(path, allow_pickle=False, mmap_mode="r")
        _require(list(value.shape) == descriptor["shape"] and str(value.dtype) == descriptor["dtype"]
                 and value.nbytes == descriptor["payload_bytes"] and not value.dtype.hasobject
                 and not value.flags.writeable, "candidate descriptor/read-only array differs: " + name)
        # A bounded row/chunk test avoids a full-array boolean allocation.
        for row in (value,) if value.ndim < 2 else value:
            flat = np.asarray(row).ravel(order="K")
            for start in range(0, flat.size, 65536):
                _require(np.isfinite(flat[start:start + 65536]).all(), "nonfinite candidate array: " + name)
        if isinstance(reference, dict) and "sha256" in reference:
            _require(_numeric_sha(value) == reference["sha256"], "snapshot numeric hash differs: " + name)
        return value

    def csr(self, record, shape=None, *, csc=False, canonical=True):
        import numpy as np
        from scipy import sparse
        from .y_orbit_sparse_reference import integer_admission, csr_audit
        if isinstance(record, str):
            record = {"shape": list(shape), **{k: record + "_" + k for k in ("data", "indices", "indptr")}}
        shape = tuple(record["shape"])
        payload = sum(self.descriptors[r if isinstance(r, str) else r["name"]]["payload_bytes"]
                      for r in (record[k] for k in ("data", "indices", "indptr")))
        self.gate("paired_checker_sparse_buffers", {"matrix_payload_bytes": payload, "workspace_bytes": 2 * payload + (1 << 20),
                                                    "before_array_open": True})
        data, indices, offsets = (self.load(record[k]) for k in ("data", "indices", "indptr"))
        integer_admission(shape, len(data), index_dtype=indices.dtype, indptr_dtype=offsets.dtype)
        integer_admission(shape, len(data), index_dtype="int32")
        rows, width = (shape[1], shape[0]) if csc else shape
        _require(data.ndim == 1 and str(data.dtype) == "complex128" and indices.shape == data.shape
                 and offsets.shape == (rows + 1,) and offsets[0] == 0 and offsets[-1] == len(data)
                 and np.all(offsets >= 0) and np.all(offsets <= len(data)) and np.all(offsets[1:] >= offsets[:-1])
                 and np.all(indices >= 0) and np.all(indices < width), "raw sparse buffers invalid before SciPy constructor")
        matrix = (sparse.csc_matrix if csc else sparse.csr_matrix)((data, indices, offsets), shape=shape, copy=False)
        if canonical:
            _require(matrix.has_canonical_format, "saved sparse candidate is not canonical")
            if not csc:
                csr_audit(matrix, petsc_index_dtype=np.int32)
        return matrix


def _sparse_compare(checks, gate, left, right, label, *, diagonal_scales=None):
    import numpy as np
    _require(left.shape == right.shape, "complete sparse comparison shape differs")
    payload = (left.nnz + right.nnz) * 24 + 8 * (left.shape[0] + 1)
    gate("paired_checker_difference_" + label, {"matrix_payload_bytes": payload, "workspace_bytes": 2 * payload})
    difference = left - right
    if diagonal_scales is not None:
        for index, scale in enumerate(diagonal_scales):
            checks.compare(label + f"_Frobenius_diagonal{index}", [stable_norm(difference.data)], [0.0],
                           scale=scale, all_entries_checked=True)
        return
    for suffix, error, scale in (("Frobenius", stable_norm(difference.data), stable_norm(right.data)),
                                 ("maximum_entry", float(np.max(np.abs(difference.data), initial=0)),
                                  float(np.max(np.abs(right.data), initial=0)))):
        checks.compare(label + "_" + suffix, [error], [0.0], scale=scale, all_entries_checked=True)


def _project_recipes(snapshot, read, gate, checks, matrices):
    import numpy as np
    from scipy import sparse
    maps = [read.csr(item) for item in snapshot["qmaps"]]
    pairs = [(a, b) for a in (0, 1) for b in (0, 1)]
    results = {pair: sparse.csr_matrix((maps[pair[0]].shape[1], maps[pair[1]].shape[1]), dtype=complex) for pair in pairs}
    b = snapshot["twist"]
    part = {key: read.load(ref) for key, ref in snapshot["partition"].items()}
    from benchmarks.check_y_orbit_two_cell_audit import validate_local_row_partition
    validate_local_row_partition(*(part[k].tolist() for k in ("independent", "trace", "interior", "slaves")))
    state = read.load(f"twist_{b}_complete_recovery_state")
    alpha = read.load(f"twist_{b}_complete_recovery_alpha")
    native_state = np.concatenate((state[part["trace"]], alpha))
    native_action = np.zeros(len(native_state), complex)
    labels = set()
    for item in snapshot["recipes"]:
        labels.add(item["label"])
        rows, cols = read.load(item["rows"]), read.load(item["cols"])
        _require(rows.ndim == cols.ndim == 1 and rows.dtype.kind in "iu" and cols.dtype.kind in "iu"
                 and len(np.unique(rows)) == len(rows) and len(np.unique(cols)) == len(cols)
                 and np.all(rows >= 0) and np.all(cols >= 0) and np.all(rows < len(native_state))
                 and np.all(cols < len(native_state)), "compact recipe indices differ")
        kind = item["kind"]
        if kind == "correction":
            di, xib = read.load(item["Di"]), read.load(item["XiB"])
            _require(di.ndim == xib.ndim == 2 and di.shape[0] == len(rows) and xib.shape[1] == len(cols)
                     and di.shape[1] == xib.shape[0], "compact correction dimensions differ")
            native_action[rows] += di @ (xib @ native_state[cols])
        else:
            values = read.load(item["values"])
            _require(kind in ("dense", "diagonal") and values.shape ==
                     ((len(rows), len(cols)) if kind == "dense" else (len(rows),))
                     and (kind != "diagonal" or len(rows) == len(cols)), "compact contribution kind/dimensions differ")
            native_action[rows] += values @ native_state[cols] if kind == "dense" else values * native_state[cols]
        for p, q in pairs:
            left, right = maps[p][rows], maps[q][cols]
            lp, rp = np.unique(left.indices), np.unique(right.indices)
            if not len(lp) or not len(rp):
                continue
            size = 16 * (len(rows) * len(lp) + len(cols) * len(rp) + 2 * len(lp) * len(rp))
            gate("paired_checker_projected_recipe", {"matrix_payload_bytes": size,
                 "workspace_bytes": 3 * (results[p, q].nnz + len(lp) * len(rp)) * 24 + (1 << 20)})
            l, r = left[:, lp].toarray(), right[:, rp].toarray()
            projected = ((l.conj().T @ di) @ (xib @ r) if kind == "correction" else
                         l.conj().T @ (values[:, None] * r) if kind == "diagonal" else l.conj().T @ values @ r)
            ii, jj = np.nonzero(projected)
            results[p, q] = (results[p, q] + sparse.coo_matrix((projected[ii, jj], (lp[ii], rp[jj])),
                                                             shape=results[p, q].shape).tocsr()).tocsr()
    expected = {"ports/H_original"} | {f"volume/cell/{i}" for i in range(40)}
    expected |= {f"direct/{s}/port/{i}" for s in ("C", "-D") for i in range(snapshot["port_count"])}
    for i, cell in enumerate(snapshot["cells"]):
        if len(read.load(cell["ports"])):
            expected |= {f"cell/{s}/{i}" for s in ("C_hat", "-D_hat", "Hhat_correction")}
    _require(labels == expected, "exact complete compact contribution inventory differs")
    for p, q in pairs:
        gp, gq = snapshot["q_indices"][p], snapshot["q_indices"][q]
        target = matrices[gp] if p == q else read.csr(f"cross_{gp}_{gq}", (Q_ROWS[gp], Q_ROWS[gq]))
        _sparse_compare(checks, gate, results[p, q], target, f"independent_twist{b}_recipe_{gp}_{gq}",
                        diagonal_scales=None if p == q else
                        (stable_norm(matrices[gp].data), stable_norm(matrices[gq].data)))
    checks.compare(f"twist{b}_complete_native_recipe_action", native_action,
                   read.load(f"twist_{b}_complete_recovery_reduced_action"))
    return part, native_action


def _check_local_recovery(snapshot, part, native_action, read, checks, gate):
    import numpy as np
    from scipy.linalg import lu_solve
    b, m = snapshot["twist"], snapshot["port_count"]
    base = f"twist_{b}_complete_recovery_"
    rhs, alpha, state, g = (read.load(base + k) for k in ("FE_rhs", "alpha", "state", "port_rhs"))
    reduced = np.concatenate((rhs[part["trace"]], g)).copy()
    recovered = np.zeros(8940, complex)
    active = state[part["trace"]]
    recovered[part["trace"]] = active
    covered = []
    for cell in snapshot["cells"]:
        ids, aid, ports = (read.load(cell[k]) for k in ("original_interiors", "active_ids", "ports"))
        _require(ids.shape == (108,) and ids.dtype.kind in "iu" and len(np.unique(ids)) == 108
                 and np.all(np.isin(ids, part["interior"])) and aid.ndim == ports.ndim == 1
                 and aid.dtype.kind in "iu" and ports.dtype.kind in "iu" and np.all(aid >= 0)
                 and np.all(aid < 3616) and np.all(ports >= 0) and np.all(ports < m), "cell recovery index inventory differs")
        exp, lu, piv = read.csr(cell["expansion"]), read.load(cell["LU"]), read.load(cell["pivots"])
        recovery, reduction = read.load(cell["recovery"]), read.load(cell["trace_from_interior"])
        _require(lu.shape == (108, 108) and piv.shape == (108,) and piv.dtype.kind in "iu"
                 and np.all(piv >= np.arange(108)) and np.all(piv < 108) and exp.shape[1] == len(aid)
                 and recovery.shape == (108, exp.shape[0]) and reduction.shape == (exp.shape[0], 108),
                 "complete saved cell LU/recovery dimensions differ before LAPACK")
        gate("paired_checker_saved_cell_LU_apply", {"matrix_payload_bytes": 108 * 20,
                                                   "workspace_bytes": 108 * 108 * 16 + (64 << 10), "new_factor": False})
        solved = lu_solve((lu, np.array(piv, dtype=np.int32, copy=True)), rhs[ids])
        reduced[aid] += exp.conj().T @ (reduction @ rhs[ids])
        recovered[ids] = solved + recovery @ (exp @ active[aid])
        if len(ports):
            di, xib = read.load(cell["Di"]), read.load(cell["XiB"])
            _require(di.shape == (len(ports), 108) and xib.shape == (108, len(ports)), "cell complete port recovery differs")
            reduced[3616 + ports] += di @ solved
            recovered[ids] -= xib @ alpha[ports]
        covered.extend(ids.tolist())
    _require(sorted(covered) == sorted(part["interior"].tolist()) and len(covered) == 4320
             and np.count_nonzero(rhs[part["interior"]]) == 4320 and np.count_nonzero(g) == m
             and np.all(recovered[part["slaves"]] == 0) and np.all(state[part["slaves"]] == 0),
             "every4320 actual local interior/nonzero port RHS/slave inventory required")
    for suffix, actual in (("reduced_rhs", reduced), ("recovered", recovered), ("state", recovered)):
        checks.compare(f"twist{b}_independent_{suffix}", actual, read.load(base + suffix))
    checks.compare(f"twist{b}_manufactured_reduced_equation", native_action, reduced, limit=1e-10)
    original = snapshot["original_witness"]
    coupling, projection, dnorm = _carrier_actions(snapshot["carrier_records"], read, recovered, alpha, 8940)
    h = read.load(original["H"])
    _require(h.shape == (m,) and np.all(h > 0) and np.array_equal(h, read.load(f"twist_{b}_original_H")), "local original H binding differs")
    checks.compare(f"twist{b}_original_C", coupling, read.load(original["coupling_action"]))
    checks.compare(f"twist{b}_original_D", projection, read.load(original["projection"]))
    volume = read.load(original["volume_action"])
    fe, port = rhs - volume - coupling, g + projection - h * alpha
    checks.compare(f"twist{b}_saved_live_original_FE", fe, np.zeros(8940), scale=stable_norm(rhs), limit=1e-10)
    checks.modes(f"twist{b}_original_nonzero_port_equation", port, np.zeros(m),
                 dnorm * stable_norm(recovered) + np.abs(h * alpha) + np.abs(g))
    checks.compare(f"twist{b}_FE_residual_record", fe, read.load(original["FE_residual"]),
                   scale=stable_norm(rhs) + stable_norm(volume) + stable_norm(coupling),
                   scale_scope="sum of saved original equation operand norms")
    checks.compare(f"twist{b}_port_residual_record", port, read.load(original["port_residual"]),
                   scale=stable_norm(g) + stable_norm(projection) + stable_norm(h * alpha),
                   scale_scope="sum of independent port equation operand norms")


def _carrier_actions(records, read, field, alpha, rows):
    import numpy as np
    coupling, projection, norms = np.zeros(rows, complex), np.empty(len(records), complex), np.empty(len(records))
    for i, item in enumerate(records):
        cr, cv, dr, dv = (read.load(item[k]) for k in ("C_rows", "C_values", "D_rows", "D_values"))
        _require(cr.ndim == dr.ndim == 1 and cr.shape == cv.shape and dr.shape == dv.shape
                 and cr.dtype.kind in "iu" and dr.dtype.kind in "iu" and len(cr) > 0 and len(dr) > 0
                 and np.all(cr >= 0) and np.all(cr < rows) and np.all(dr >= 0) and np.all(dr < rows), "complete carrier support differs")
        np.add.at(coupling, cr, cv * alpha[i])
        projection[i], norms[i] = np.dot(dv, field[dr]), stable_norm(dv)
    return coupling, projection, norms


def _bind_carrier(identity, entries, global_rows, ownership_range, slaves):
    from .dtn_boundary_plane_qualification import carrier_numeric_identity
    carrier = SimpleNamespace(entries=entries, global_rows=global_rows, ownership_range=ownership_range, slave_rows=slaves,
                physical_generator_manifest_sha256=identity["physical_generator_manifest_sha256"],
                mode_manifest_sha256=identity["assembly_mode_manifest_sha256"], assembly_context_sha256=identity["assembly_context_sha256"])
    _require(carrier_numeric_identity(carrier)["carrier_numeric_sha256"] == identity["carrier_numeric_sha256"],
             "saved original carrier detached from exact qualified live numeric digest")


def _bind_receipts(report, read):
    from .y_orbit_live_boundary_contract import load_bound_live_receipt
    from benchmarks.check_y_orbit_two_cell_audit import validate_raw_port_receipt
    identity = report["fresh_global_identity"]
    receipt = identity["live_component_receipt"]
    read.json(receipt["filename"], receipt["sha256"])
    global_receipt = load_bound_live_receipt(read.directory, identity, worker_source=report["source"], expected_degree=4, fresh_fixture_c1=True)
    sectors = []
    for item in report["raw_sector_receipts"]:
        raw = read.json(item["path"], item["sha256"])
        validate_raw_port_receipt(raw, item, report_source=report["source"], keys=report["global_mode_keys"])
        sectors.append(raw)
    return global_receipt, sectors


def _global_inventory(report, read, reference, checks):
    import numpy as np
    independent, interiors = read.load("independent_storage_rows"), read.load("actual_interior_positions")
    slaves, masters, coefficients, offsets = (read.load("full_mpc_" + k) for k in ("slaves", "masters", "coefficients", "offsets"))
    _require(independent.dtype.kind in "iu" and len(np.unique(independent)) == 15872
             and np.array_equal(independent, np.sort(independent)) and np.all(independent >= 0) and np.all(independent < 17204)
             and slaves.dtype.kind in "iu" and len(np.unique(slaves)) == 1332
             and set(independent.tolist()).isdisjoint(slaves.tolist())
             and sorted(independent.tolist() + slaves.tolist()) == list(range(17204)), "full original independent/slave partition differs")
    _require(interiors.dtype.kind in "iu" and len(np.unique(interiors)) == 8640 and np.all(interiors >= 0)
             and np.all(interiors < 15872) and np.array_equal(interiors, reference.load("actual_interior_positions"))
             and np.array_equal(independent, reference.load("independent_storage_rows")), "all8640 actual original interior inventory differs")
    _require(offsets.dtype.kind in "iu" and offsets[0] == 0 and offsets[-1] == len(coefficients)
             and masters.dtype.kind in "iu" and masters.shape == coefficients.shape and np.all(offsets[1:] >= offsets[:-1])
             and np.all(masters >= 0) and np.all(masters < 17204) and not np.any(np.isin(masters, slaves))
             and np.all(offsets[slaves + 1] > offsets[slaves]), "full finalized MPC masters/coefficients/offsets differ")
    from .dtn_boundary_phase_gauge import _array_signature
    context = report["fresh_global_identity"]["actual_context"]["MPC"]
    for key, value in (("slaves", slaves), ("masters", masters), ("coefficients", coefficients), ("offsets", offsets)):
        _require(json.loads(json.dumps(_array_signature(value))) == context[key], "full actual MPC raw signature differs: " + key)
    h = read.load("port_original_H")
    _require(np.all(h > 0) and np.array_equal(h, reference.load("port_original_H")), "global actual original H differs")
    checks.compare("original_H_factor_coordinate_scale", read.load("port_factor_coordinate_scale"), 1 / np.sqrt(h), limit=1e-12)
    qlabels = np.asarray([int(k[2]) % 4 for k in report["global_mode_keys"]])
    _require(np.array_equal(read.load("port_q_labels"), qlabels), "all532 port q assignment differs")
    c, d = read.csr("original_port_C", (17204, 532), csc=True), read.csr("original_port_D", (532, 17204))
    _require(np.all(np.diff(c.indptr) > 0) and np.all(np.diff(d.indptr) > 0), "all532 actual C/D must be nonempty")
    entries = [SimpleNamespace(mode_key=(j, *report["global_mode_keys"][j]), normalization_h=float(h[j]),
                coupling_rows=c.indices[c.indptr[j]:c.indptr[j + 1]], coupling_values=c.data[c.indptr[j]:c.indptr[j + 1]],
                projection_rows=d.indices[d.indptr[j]:d.indptr[j + 1]], projection_values=d.data[d.indptr[j]:d.indptr[j + 1]]) for j in range(532)]
    _require(np.array_equal(read.load("original_carrier_slave_rows"), slaves), "exported carrier/MPC slaves differ")
    _bind_carrier(report["fresh_global_identity"], entries, int(read.load("original_carrier_global_rows")),
                  tuple(read.load("original_carrier_ownership_range")), read.load("original_carrier_slave_rows"))
    dnorm = np.asarray([stable_norm(entry.projection_values) for entry in entries])
    return independent, interiors, slaves, masters, coefficients, offsets, h, c, d, dnorm


def _original_equations(label, rhs, x, g, read, checks, inventory):
    import numpy as np
    independent, _, slaves, _, _, _, h, c, d, dnorm = inventory
    field, storage_rhs = read.load(label + "_solution_storage"), read.load(label + "_rhs_storage")
    _require(field.shape == storage_rhs.shape == (17204,) and np.array_equal(field[independent], x)
             and np.array_equal(storage_rhs[independent], rhs) and np.all(field[slaves] == 0)
             and np.all(storage_rhs[slaves] == 0), "original saved solution/RHS/slave binding differs: " + label)
    volume, action, alpha = (read.load(label + "_" + k) for k in ("volume_action", "original_action", "auxiliary_ports"))
    _require(alpha.shape == (532,) and np.array_equal(read.load(label + "_normalization_h"), h), "original alpha/H binding differs")
    projection, coupling = d @ field, c @ alpha
    checks.compare(label + "_original_D_projection", projection, read.load(label + "_projection"))
    checks.compare(label + "_original_C_coupling", coupling, read.load(label + "_coupling_action"), scale=stable_norm(coupling))
    physical_coupling = c @ (projection / h)
    checks.compare(label + "_bound_original_action", action, volume + physical_coupling,
                   scale=stable_norm(volume) + stable_norm(physical_coupling),
                   scale_scope="independent original volume and carrier operand norms")
    effective = storage_rhs - c @ (g / h)
    native, top, port = effective - action, storage_rhs - volume - coupling, projection - h * alpha + g
    checks.compare(label + "_full_original_true_residual", native, np.zeros(17204), scale=stable_norm(effective), limit=1e-10)
    checks.compare(label + "_augmented_FE_true_residual", top, np.zeros(17204), scale=stable_norm(storage_rhs), limit=1e-10)
    port_scale = dnorm * stable_norm(x) + np.abs(h * alpha) + np.abs(g)
    checks.modes(label + "_each_original_port_equation", port, np.zeros(532), port_scale)
    checks.compare(label + "_aggregate_original_port_equation", port, np.zeros(532),
                   scale=stable_norm(projection) + stable_norm(h * alpha) + stable_norm(g), limit=1e-10)
    for suffix, vector, scale in (("native_residual", native, stable_norm(effective) + stable_norm(action)),
        ("augmented_FE_residual", top, stable_norm(storage_rhs) + stable_norm(volume) + stable_norm(coupling)),
        ("augmented_port_residual", port, stable_norm(projection) + stable_norm(h * alpha) + stable_norm(g))):
        checks.compare(label + "_" + suffix + "_record", vector, read.load(label + "_" + suffix),
                       scale=scale, limit=1e-11, scale_scope="sum of independently bound equation operand norms")
    port_correction = c @ (port / h)
    checks.compare(label + "_native_augmented_identity", native, top - port_correction,
                   scale=stable_norm(storage_rhs) + stable_norm(volume) + stable_norm(coupling)
                         + stable_norm(port_correction) + stable_norm(effective) + stable_norm(action),
                   limit=1e-11, scale_scope="sum of independently bound identity operand norms")
    return field, projection, port_scale


def _generator(report, read, input_path):
    import numpy as np
    from .task40extra_y_orbit_reference import pilot_config
    from ..common.modes_3d import outgoing_port_modes_3d
    from .dtn_boundary_phase_gauge import incident_projection_in_solver_coordinates, BOUNDARY_PLANE
    cfg, _, sha = pilot_config(input_path, azimuth_deg=5.0)
    modes = outgoing_port_modes_3d(cfg)
    keys = [[str(m.side), int(m.m), int(m.n), str(m.polarization)] for m in modes]
    e, k = np.asarray([m.e_vector for m in modes]), np.asarray([m.k_vector for m in modes])
    outward = np.asarray([1 if m.side == "top" else -1 for m in modes])
    incident = np.asarray([incident_projection_in_solver_coordinates(m, cfg, BOUNDARY_PLANE) for m in modes])
    denominator, area = cfg.k0 * complex(cfg.mu_r), (cfg.x_max - cfg.x_min) * (cfg.y_max - cfg.y_min)
    _require(sha == report["input_sha256"] and keys == report["global_mode_keys"]
             and np.array_equal(e, read.load("original_mode_e_vectors")) and np.array_equal(k, read.load("original_mode_k_vectors"))
             and np.array_equal(outward, read.load("original_mode_outward_signs"))
             and np.array_equal(incident, read.load("original_mode_incident_projections"))
             and denominator == read.load("original_mode_magnetic_denominator")
             and area == read.load("original_mode_boundary_area"), "saved modes/incident projection detached from optical generator")
    return e, k, outward, incident, denominator, area, modes, cfg


def _saved_factor_controls(q, matrix, read, checks):
    """Only saved vectors and matrix products; never apply or create a factor."""
    import numpy as np
    a, b, x, repeat, y, combined, action = (read.load(f"q_{q}_" + suffix) for suffix in
                  ("rhs_a", "rhs_b", "solution_a", "solution_a_repeat", "solution_b", "solution_sum", "action_a"))
    j = np.arange(matrix.shape[0])
    _require(np.array_equal(a, np.cos(.23 * j) + 1j * np.sin(.37 * j))
             and np.array_equal(b, np.sin(.29 * j) + 1j * np.cos(.41 * j)), "saved factor manufactured RHS binding differs")
    checks.compare(f"q{q}_saved_factor_true_residual_a", matrix @ x, a, limit=1e-10)
    checks.compare(f"q{q}_saved_factor_true_residual_b", matrix @ y, b, limit=1e-10)
    checks.compare(f"q{q}_saved_factor_repeated", repeat, x)
    checks.compare(f"q{q}_saved_factor_linearity", combined, x + y, scale=stable_norm(combined))
    checks.compare(f"q{q}_saved_factor_action_binding", action, matrix @ x)


def _outputs(label, physical, field, projection, read, reference, checks, inventory, generator):
    import numpy as np
    independent, _, slaves, masters, coefficients, offsets, h, _, _, dnorm = inventory
    e, k, outward, physical_incident, denominator, area, modes, cfg = generator
    backsub = field.copy()
    for slave in slaves:
        start, end = int(offsets[slave]), int(offsets[slave + 1])
        backsub[slave] = np.dot(coefficients[start:end], field[masters[start:end]])
    checks.compare(label + "_independent_MPC_backsubstitution", read.load(label + "_recovered_field"), backsub, limit=1e-12)
    checks.compare(label + "_saved_C1b_recovered_field", backsub, reference.load(label + "_recovered_field"), limit=1e-9)
    total = projection / h
    incident = physical_incident if physical else np.zeros(532, complex)
    outgoing = total - incident
    electric, unit_magnetic = outgoing[:, None] * e, np.cross(k, e) / denominator
    magnetic = np.cross(k, electric) / denominator
    power = np.maximum(.5 * np.real(np.cross(electric, np.conj(magnetic)))[:, 2] * outward, 0) * area
    scale = dnorm / h * stable_norm(field[independent])
    scales = {"mode_local_amplitude_scale": scale, "plane_electric_scale": scale * np.linalg.norm(e, axis=1),
              "plane_magnetic_scale": scale * np.linalg.norm(unit_magnetic, axis=1),
              "mode_power_operation_scale": .5 * area * (scale + np.abs(incident)) ** 2 * np.linalg.norm(e, axis=1) * np.linalg.norm(unit_magnetic, axis=1)}
    _require(np.array_equal(read.load(label + "_plane_incident_projections"), incident), "output physical incident binding differs")
    for name, values in scales.items():
        checks.modes(label + "_independent_" + name, read.load(label + "_" + name), values, np.abs(values), limit=1e-12)
    for name, values, scale_name in (("plane_total_auxiliary", total, "mode_local_amplitude_scale"),
        ("plane_outgoing_auxiliary", outgoing, "mode_local_amplitude_scale"), ("plane_electric", electric, "plane_electric_scale"),
        ("plane_magnetic", magnetic, "plane_magnetic_scale"), ("direct_plane_outgoing_power_diagnostic", power, "mode_power_operation_scale")):
        checks.modes(label + "_independent_" + name, read.load(label + "_" + name), values, scales[scale_name])
        checks.modes(label + "_C1b_" + name, read.load(label + "_" + name), reference.load(label + "_" + name),
                     scales[scale_name] + reference.load(label + "_" + scale_name))
    from .dtn_boundary_phase_gauge import global_amplitudes_from_solver, solver_amplitudes_from_global, BOUNDARY_PLANE
    global_total = global_amplitudes_from_solver(total, modes, cfg, BOUNDARY_PLANE)
    global_incident = global_amplitudes_from_solver(incident, modes, cfg, BOUNDARY_PLANE)
    global_scale = np.abs(global_amplitudes_from_solver(scale, modes, cfg, BOUNDARY_PLANE))
    _require(np.isfinite(global_total).all() and np.isfinite(global_incident).all() and np.isfinite(global_scale).all(),
             "required global output conversion is nonfinite")
    checks.modes(label + "_bound_global_total_auxiliary", read.load(label + "_global_total_auxiliary"), global_total, global_scale)
    checks.modes(label + "_bound_global_incident_projections", read.load(label + "_global_incident_projections"),
                 global_incident, np.abs(global_incident))
    checks.modes(label + "_global_total_roundtrip", solver_amplitudes_from_global(global_total, modes, cfg, BOUNDARY_PLANE),
                 total, scale, limit=1e-12)
    checks.modes(label + "_global_incident_roundtrip", solver_amplitudes_from_global(global_incident, modes, cfg, BOUNDARY_PLANE),
                 incident, np.abs(incident), limit=1e-12)


def check_paired_compact_inverse(report, *, directory, reference, allocation_gate,
                                checker_source=None, checker_environment=None, input_path=None):
    """Check one actual paired report; ``reference`` is the pinned fresh C1b reader.

    This callable is additive. It never routes the report through a legacy whole
    checker or constructs a pretend legacy report. The caller owns supervision,
    current source/ABI freezing, receipt publication and final resource gates.
    """
    _require(callable(allocation_gate), "measured whole-tree candidate admission callback required")
    validate_candidate_inventory(report, reference.report)
    source = report.get("source", {})
    _require(source.get("branch") == "task40extra_dot_parallel_cloud" and source.get("dirty") == ""
             and re.fullmatch("[0-9a-f]{40}", source.get("head", ""))
             and report.get("source_clean_unchanged") is True,
             "clean frozen own-branch source required")
    if checker_source is not None:
        _require(source == checker_source, "worker/checker source identity differs")
    if checker_environment is not None:
        _require(report.get("environment") == checker_environment, "worker/checker ABI identity differs")
    _require(report.get("authority") == reference.identity(), "pinned fresh C1b authority receipt differs")
    read, checks = _Candidate(directory, report, allocation_gate), _Checks()
    _, sector_receipts = _bind_receipts(report, read)
    # Even unused diagnostics cannot conceal a substituted artifact.
    for name in read.descriptors:
        read.load(name)
    for ref in _refs(report["local_compact_snapshots"]):
        read.load(ref)
    from .y_orbit_sparse_reference import sparse_hash
    matrices, norms = {}, {}
    for q in range(4):
        matrix = read.csr(f"q_{q}_S", (Q_ROWS[q], Q_ROWS[q]))
        _require(matrix.nnz == report["reformed_blocks"][q]["nnz"]
                 and sparse_hash(matrix) == report["reformed_blocks"][q]["CSR_sha256"], "actual complete diagonal CSR hash/NNZ differs")
        _sparse_compare(checks, allocation_gate, matrix, reference.q_block(q), f"q{q}_fresh_C1b_complete_CSR")
        matrices[q], norms[q] = matrix, stable_norm(matrix.data)
        error, scale = read.load(f"q_{q}_map_column_error_norms"), read.load(f"q_{q}_map_reference_column_norms")
        _require(error.shape == scale.shape == (3968,) and (error >= 0).all() and (scale > 0).all(), "complete3968 map column controls differ")
        checks.modes(f"q{q}_producer_native_map_column_control", error, error * 0, scale, limit=1e-12)
    for item in report["cross_blocks"]:
        p, q = item["p"], item["q"]
        cross = read.csr(item["csr_prefix"], (Q_ROWS[p], Q_ROWS[q]))
        _require(min(norms[p], norms[q]) > 0, "both diagonal cross scales must be positive")
        for diagonal in (p, q):
            checks.compare(f"cross{p}_{q}_relative_to_diagonal{diagonal}", [stable_norm(cross.data)], [0.0],
                           scale=norms[diagonal], limit=1e-11)
    for snapshot, raw in zip(report["local_compact_snapshots"], sector_receipts, strict=True):
        part, action = _project_recipes(snapshot, read, allocation_gate, checks, matrices)
        _check_local_recovery(snapshot, part, action, read, checks, allocation_gate)
        identity = raw["carrier_identity_before"]
        h = read.load(snapshot["original_witness"]["H"])
        entries = [SimpleNamespace(mode_key=tuple(identity["ordered_mode_keys"][i]), normalization_h=float(h[i]),
                 **{long: read.load(item[short]) for short, long in (("C_rows", "coupling_rows"), ("C_values", "coupling_values"),
                           ("D_rows", "projection_rows"), ("D_values", "projection_values"))})
                   for i, item in enumerate(snapshot["carrier_records"])]
        _bind_carrier(identity, entries, 8940, (0, 8940), part["slaves"])
    inventory = _global_inventory(report, read, reference, checks)
    input_path = input_path or Path(__file__).resolve().parents[2] / "input/task40extra_0p7nm_engineering/nonseparable_g0_p6_q4_review_v1.dat"
    generator = _generator(report, read, input_path)
    if report["stage"] == "solve":
        import numpy as np
        for q in range(4):
            _saved_factor_controls(q, matrices[q], read, checks)
        # Pinned C1b full maps are validation controls, never candidate maps.
        old_q = reference.load_csr("full_Q", (15872, 15872))
        old_ri = reference.load_csr("full_R_inverse", (15872, 15872))
        old_f = reference.load_csr("full_F", (15872, 15872))
        allocation_gate("paired_checker_full_C1b_modal_vector_controls", {"matrix_payload_bytes": 12 * 15872 * 16,
                        "workspace_bytes": 8 * 15872 * 16, "validation_only_full_maps": True})
        generic_norms = np.linalg.norm(np.asarray(old_q.conj().T @ read.load("generic_rhs")).reshape(4, 3968), axis=1)
        _require(np.min(generic_norms) / stable_norm(generic_norms) >= 1e-3, "saved generic RHS must excite all4 q controls")
        interiors = inventory[1]
        _require(np.count_nonzero(read.load("interior_only_rhs")[interiors]) == 8640
                 and np.count_nonzero(read.load("interior_only_rhs")) == 8640, "every actual original8640 interior RHS required")
        for name in SOURCES:
            rhs = read.load(name + "_rhs")
            _require(np.array_equal(rhs, reference.load(name + "_rhs")), "exact same original four-load RHS control differs")
            for prefix in ("regular_", "notch_"):
                label, x = prefix + name, read.load(prefix + name + "_solution")
                field, projection, _ = _original_equations(label, rhs, x, np.zeros(532), read, checks, inventory)
                checks.compare(label + "_fresh_C1b_solution", x, reference.load(label + "_solution"), limit=1e-9)
                _outputs(label, name == "physical", field, projection, read, reference, checks, inventory, generator)
                modal_norms = np.linalg.norm(np.asarray(old_f.conj().T @ (old_ri @ x)).reshape(4, 3968), axis=1)
                packet = report["regular_sources" if prefix == "regular_" else "notched_sources"][name]
                checks.compare(label + "_C1b_map_primal_q_norm_control", packet["solution_primal_q_norms"], modal_norms,
                               limit=1e-12, scope="pinned saved map validation control; no independent geometric map reconstruction")
                if prefix == "notch_" and name == "physical":
                    _require(stable_norm(modal_norms[1:]) / stable_norm(modal_norms) > 1e-12,
                             "notch physical full-original solution must contain nonzero transverse q modes")
        for q in range(4):
            label = f"aug_q_{q}"
            rhs, g, x = (read.load(label + "_" + s) for s in ("FE_rhs", "port_rhs", "solution"))
            ids = np.asarray([i for i, key in enumerate(report["global_mode_keys"]) if int(key[2]) % 4 == q])
            expected = np.zeros(532, complex)
            j = np.arange(len(ids))
            expected[ids] = np.sqrt(inventory[6][ids]) * (np.cos(.17 * j) + 1j * np.sin(.43 * j))
            _require(np.array_equal(g, expected) and np.count_nonzero(g) == len(ids), "all-q manufactured nonzero augmented port RHS differs")
            modal_rhs = np.zeros(15872, complex)
            j = np.arange(3968)
            modal_rhs[q * 3968:(q + 1) * 3968] = np.cos(.31 * j) + 1j * np.sin(.47 * j)
            checks.compare(label + "_C1b_map_manufactured_FE_rhs_control", old_q.conj().T @ rhs, modal_rhs,
                           limit=1e-12, scope="pinned saved full native map validation control")
            _, _, scales = _original_equations(label, rhs, x, g, read, checks, inventory)
            checks.modes(label + "_independent_port_scale", read.load(label + "_port_operation_scale"), scales, scales, limit=1e-12)
            checks.compare(label + "_effective_rhs_binding", read.load(label + "_effective_rhs"),
                           rhs - (inventory[7] @ (g / inventory[6]))[inventory[0]], limit=1e-12)
    return {"schema": CHECKER_SCHEMA, "gate_pass": True, "evidence_valid": True, "checks": checks.records,
            "stage": report["stage"], "factor_count": report["factor_count"], "checker_new_factors": 0,
            "checker_PDE_solved": False, "checker_FE_JIT": False, "all4_complete_CSR_checked": True,
            "four_cross_directions_scaled_by_both_diagonals": True, "fresh_global_and_228_plus_304_raw_receipts_bound": True,
            "all8640_actual_interiors_and_full_MPC_inventory_checked": True,
            "all8_full_original_load_output_packets_checked": report["stage"] == "solve",
            "augmented_nonzero_port_RHS_controls_checked": report["stage"] == "solve",
            "independent_recipe_projection_and_cell_RHS_recovery": True,
            "all4_saved_factor_controls_checked": report["stage"] == "solve",
            "cache_lifecycle_scope": "source-bound producer numeric/recipe identities and owner controls; no independent live mutation test",
            "independent_map_reconstruction": False, "map_column_diagnostics_scope": "producer controls, independently range/gate checked",
            "volume_authority": "saved original live FFCx volume action vectors; no independent volume rebuild",
            "raw_receipt_scope": "exact fresh source/hash-bound literal-component receipts, no independent literal reassembly",
            "target_geometry_accuracy": False, "no_2TB_or_48h_claim": True,
            "source": source, "artifact_manifest_sha256": _digest(report["artifacts"])}


__all__ = ("check_paired_compact_inverse", "validate_candidate_inventory")
