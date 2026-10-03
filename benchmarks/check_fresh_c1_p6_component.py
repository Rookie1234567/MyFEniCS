"""Independent saved-only fresh same80 p6 component checker.

Import is standard-library only. The explicit entry point requires external
resource supervision and only then loads NumPy/SciPy. It never imports the
worker, FE stack, historical raw artifacts, or a canonical solver. This is new,
unqualified source; a result is numerical component evidence only. The caller
owns source, ABI, provenance, archive, Library and supervision bindings.
"""
from __future__ import annotations

import hashlib
import json
import math
import re

WORKER_SCHEMA = "fresh-c1.same80.p6-component.v1"
CHECKER_SCHEMA = "fresh-c1.same80.p6-component-saved-checker.v1"
SOURCE_STATUS = "NEW_UNQUALIFIED"
PIVOT_HELPER_PROVENANCE_SHA256 = "27df99ddc6df1997beffff03be0866e8648cbd1b4c1e1e756f79cd9717f2f869"
INVENTORY = {"degree": 6, "cell_count": 80, "local_dimension": 882,
             "local_interiors": 450, "local_traces": 432, "storage_rows": 55950,
             "independent_rows": 52992, "interior_rows": 36000,
             "active_trace_rows": 16992, "port_rows": 532}
PHYSICAL_GENERATOR = "4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951"
ACTION_LIMIT, RESIDUAL_LIMIT, ALGEBRA_LIMIT = 1.e-11, 1.e-10, 1.e-12
NEGATIVE_SEPARATION = 1.e-3


def require(condition, message):
    if not condition:
        raise ValueError(message)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, ensure_ascii=True).encode("ascii")


def metric_record(error_norm, operation_scale, limit):
    """An exactly zero operation scale requires exactly zero error."""
    values = tuple(float(value) for value in (error_norm, operation_scale, limit))
    if any(not math.isfinite(value) or value < 0 for value in values):
        return {"finite": False, "error_norm": None, "operation_scale": None,
                "relative": None, "limit": float(limit) if math.isfinite(float(limit)) else None,
                "passed": False, "zero_scale_rule": "error_must_be_exactly_zero"}
    error, scale, bound = values
    relative = error / scale if scale else (0.0 if error == 0 else None)
    finite = relative is None or math.isfinite(relative)
    return {"finite": finite, "error_norm": error, "operation_scale": scale,
            "relative": relative if finite else None, "limit": bound,
            "zero_scale_rule": "error_must_be_exactly_zero",
            "passed": finite and (error <= bound * scale if scale else error == 0)}


def _gate(callback, stage, payload=0, workspace=0, **facts):
    callback("fresh_p6_saved_checker/" + stage, {
        "matrix_payload_bytes": int(payload), "workspace_bytes": int(workspace),
        "allocation_semantics": "additional_objects_to_current_resident_RSS",
        "global_p6_matrix_count": 0, "global_p6_factor_count": 0, **facts})


def _sha(array, *, header=True):
    """C-order digest with at most one row of scratch; no whole-LU copy."""
    digest = hashlib.sha256()
    if header:
        digest.update(repr((array.shape, str(array.dtype))).encode("utf-8"))
    if array.ndim < 2:
        digest.update(array.tobytes(order="C"))
    else:
        for row in array:
            digest.update(row.tobytes(order="C"))
    return digest.hexdigest()


def solve_fresh_p6_saved_LU(lu, pivots, rhs, *, allocation_gate, label):
    """New 450-only port of the recovered 108 helper's safety contract.

    The historical helper's source hash is provenance, not this function's
    source hash. No historical module is loaded. Archived arrays are unchanged;
    GETRS receives only a detached writable int32 pivot copy after admission.
    """
    require(callable(allocation_gate), "saved LU requires allocation_gate")
    _gate(allocation_gate, "saved_LU_numerical_dependencies/" + label,
          workspace=64 << 20, numerical_dependencies_may_already_be_loaded=True,
          FE_imports=False, JIT=False)
    import numpy as np
    from scipy.linalg import lu_solve
    require(isinstance(lu, np.ndarray) and isinstance(pivots, np.ndarray)
            and isinstance(rhs, np.ndarray), "saved LU requires actual ndarray inputs")
    require(lu.shape == (450, 450) and lu.dtype == np.dtype("complex128")
            and pivots.shape == (450,) and pivots.dtype == np.dtype("int32")
            and rhs.ndim == 2 and rhs.shape[0] == 450 and rhs.dtype == np.dtype("complex128"),
            "exact 450-row complex128 LU/int32 pivots/2D RHS required")
    _gate(allocation_gate, "saved_LU_validation/" + label,
          workspace=2 * max(450 * 16, int(rhs.shape[1]) * 16) + 450 * 8)
    require(all(all(bool(np.isfinite(row).all()) for row in value) if value.ndim >= 2
                else bool(np.isfinite(value).all()) for value in (lu, pivots, rhs)),
            "saved LU/pivots/RHS must be finite")
    require(not np.any(pivots < np.arange(450)) and not np.any(pivots >= 450),
            "saved pivots fail exact zero-based GETRF range before narrowing")
    _gate(allocation_gate, "compact_private_pivots/" + label,
          payload=int(pivots.nbytes),
          workspace=int(rhs.nbytes) + int(lu.nbytes) + 2*(int(rhs.size)+int(lu.size)) + (1 << 20),
          immutable_archived_pivots_preserved=True, factor_count=0,
          dimension=450, helper_source_status=SOURCE_STATUS,
          possible_Fortran_LU_copy_bytes=int(lu.nbytes),
          native_finite_check_boolean_allowance_bytes=2*(int(rhs.size)+int(lu.size)))
    before = {name: _sha(value)
              for name, value in (("LU", lu), ("pivots", pivots), ("rhs", rhs))}
    private = np.array(pivots, dtype=np.int32, copy=True, order="C")
    require(private.flags.writeable and not np.shares_memory(private, pivots),
            "native solve requires detached writable private int32 pivots")
    result = lu_solve((lu, private), rhs, overwrite_b=False)
    after = {name: _sha(value)
             for name, value in (("LU", lu), ("pivots", pivots), ("rhs", rhs))}
    require(before == after and np.array_equal(private, pivots),
            "saved LU solve changed archived arrays or did not restore private pivots")
    require(bool(np.isfinite(result).all()), "saved LU solve returned nonfinite values")
    return result


class _Reader:
    def __init__(self, report, load_array, gate):
        import numpy as np
        self.load_array, self.gate, self.seen = load_array, gate, set()
        snapshot = report.get("snapshot")
        require(isinstance(snapshot, dict), "complete snapshot required")
        members, self.roles = snapshot.get("members"), snapshot.get("roles")
        require(isinstance(members, list) and members and isinstance(self.roles, dict),
                "snapshot members and logical roles required")
        self.members = {}
        numeric_bytes = 0
        for member in members:
            require(isinstance(member, dict) and isinstance(member.get("name"), str)
                    and member["name"] and member["name"] not in self.members,
                    "unique named saved members required")
            shape, dtype = member.get("shape"), member.get("dtype")
            require(isinstance(shape, list) and all(type(n) is int and 0 <= n <= 2**31-1 for n in shape)
                    and dtype in ("bool", "int32", "int64", "uint32", "uint64", "float64", "complex128"),
                    "primitive bounded saved-member shape/dtype required")
            size = math.prod(shape) * np.dtype(dtype).itemsize
            require(type(member.get("numeric_bytes")) is int and member["numeric_bytes"] == size
                    and isinstance(member.get("sha256"), str)
                    and re.fullmatch(r"[0-9a-f]{64}", member["sha256"]),
                    "saved member byte/hash inventory differs")
            self.members[member["name"]] = member
            numeric_bytes += size
        require(snapshot.get("unique_member_count") == len(members)
                and snapshot.get("numeric_bytes") == numeric_bytes
                and snapshot.get("archive_members_bytes_upper") == numeric_bytes + 4096 * len(members)
                and type(snapshot.get("archive_payload_limit_bytes")) is int
                and numeric_bytes + 4096 * len(members) <= snapshot["archive_payload_limit_bytes"],
                "uncompressed primitive payload budget/inventory differs")
        for name, reference in self.roles.items():
            require(isinstance(name, str) and isinstance(reference, dict)
                    and reference.get("name") in self.members
                    and reference == self.members[reference["name"]],
                    "every logical role must bind an exact canonical saved member")
        require(set(self.members) == {reference["name"] for reference in self.roles.values()},
                "snapshot cannot contain orphan saved members")
        require(all(self.roles.get(name) == member for name, member in self.members.items()),
                "canonical saved member names must identify their own original logical role")
        self.numeric_bytes = numeric_bytes

    def ref(self, reference, *, shape=None, dtype=None):
        import numpy as np
        require(isinstance(reference, dict) and reference.get("name") in self.members
                and reference == self.members[reference["name"]],
                "array reference is absent, extra, or differs from saved member inventory")
        declared_shape = tuple(reference["shape"])
        require(shape is None or declared_shape == tuple(shape), "required saved array shape differs")
        require(dtype is None or reference["dtype"] == dtype, "required saved array dtype differs")
        row_bytes = (reference["numeric_bytes"] if len(declared_shape) < 2 else
                     math.prod(declared_shape[1:]) * np.dtype(reference["dtype"]).itemsize)
        _gate(self.gate, "load_hash/" + reference["name"],
              payload=reference["numeric_bytes"], workspace=3 * row_bytes + 4096,
              saved_member_bytes=reference["numeric_bytes"], require_readonly=True)
        array = self.load_array(reference)
        require(isinstance(array, np.ndarray) and array.shape == declared_shape
                and str(array.dtype) == reference["dtype"] and array.nbytes == reference["numeric_bytes"]
                and not array.flags.writeable, "loaded saved member must be exact immutable ndarray/mmap")
        finite = (all(bool(np.isfinite(row).all()) for row in array) if array.ndim >= 2
                  else bool(np.isfinite(array).all()))
        require(finite, "nonfinite saved array: " + reference["name"])
        require(_sha(array) == reference["sha256"], "saved array hash differs: " + reference["name"])
        self.seen.add(reference["name"])
        return array

    def role(self, name, *, shape=None, dtype=None):
        require(name in self.roles, "missing required saved role: " + name)
        return self.ref(self.roles[name], shape=shape, dtype=dtype)

    def bound(self, role, reference, *, shape=None, dtype=None):
        require(self.roles.get(role) == reference, "logical saved role differs: " + role)
        return self.ref(reference, shape=shape, dtype=dtype)

    def verify_remaining(self):
        for name, reference in self.members.items():
            if name not in self.seen:
                self.ref(reference)


def _indices(array, bound, *, size=None, unique=True, name="indices"):
    import numpy as np
    require(array.ndim == 1 and array.dtype.kind in "iu"
            and (size is None or len(array) == size), "invalid " + name + " dimensions/dtype")
    require(not array.size or (int(array.min()) >= 0 and int(array.max()) < bound
                               and int(array.max()) <= np.iinfo(np.int32).max),
            name + " fails native/int32 range before narrowing")
    require(not unique or len(np.unique(array)) == len(array), "duplicate " + name)
    return array


def _pointers(array, nnz, *, size=None, strictly_increasing=False, name="CSR pointers"):
    """Range-admit wide/unsigned pointers before narrowing or differences."""
    import numpy as np
    require(array.ndim == 1 and array.dtype.kind in "iu" and len(array) >= 1
            and (size is None or len(array) == size), "invalid " + name + " shape/dtype")
    require(type(nnz) is int and 0 <= nnz <= np.iinfo(np.int32).max
            and int(array.min()) >= 0 and int(array.max()) <= nnz
            and array[0] == 0 and array[-1] == nnz,
            name + " fail native/int32 range before narrowing")
    difference = np.diff(array.astype(np.int64))
    require(not np.any(difference <= 0 if strictly_increasing else difference < 0),
            "invalid monotonic " + name)
    return array


class _Measurements:
    def __init__(self, checkpoint):
        self.checkpoint, self.records, self.negative = checkpoint, {}, {}

    def compare(self, name, actual, expected, limit=ACTION_LIMIT, *, scale=None):
        import numpy as np
        require(actual.shape == expected.shape, "compared shape differs: " + name)
        operation_scale = float(np.linalg.norm(expected)) if scale is None else float(scale)
        record = metric_record(float(np.linalg.norm(actual - expected)), operation_scale, limit)
        if operation_scale == 0:
            nonzero_error = not np.array_equal(actual, expected)
            record["nonzero_error_at_zero_scale"] = nonzero_error
            record["error_norm_underflow_at_zero_scale"] = nonzero_error and record["error_norm"] == 0
            record["passed"] = record["passed"] and not nonzero_error
        self.records[name] = record
        self.checkpoint("component_checker_metric", {"name": name, **record})
        require(record["passed"], "independent saved-data metric failed: " + name)

    def separate(self, name, wrong, reference):
        import numpy as np
        record = metric_record(float(np.linalg.norm(wrong - reference)),
                               float(np.linalg.norm(reference)), ACTION_LIMIT)
        separated = (record["finite"] and record["relative"] is not None
                     and record["relative"] >= NEGATIVE_SEPARATION and not record["passed"])
        self.negative[name] = {**record, "separated": separated,
                               "minimum_relative_separation": NEGATIVE_SEPARATION}
        self.checkpoint("component_checker_negative", {"name": name, **self.negative[name]})
        require(separated, "material negative control lacks independently recomputed separation: " + name)


def _native_maps(reader, gate):
    import numpy as np
    n, nt, ni = 55950, 16992, 36000
    _gate(gate, "complete_native_maps", payload=n*8*6, workspace=n*8*8)
    interior = _indices(reader.role("native/interior_original"), n, size=ni, name="complete interiors")
    active = _indices(reader.role("native/active_original"), n, size=nt, name="independent traces")
    trace = _indices(reader.role("native/trace_original"), n, size=n-ni, name="complete traces")
    slaves = _indices(reader.role("native/mpc/slaves", dtype="int32"), n, size=n-ni-nt, name="MPC slaves")
    require(np.array_equal(np.sort(np.r_[interior, trace]), np.arange(n))
            and np.array_equal(np.sort(np.r_[active, slaves]), np.sort(trace)),
            "actual complete interior/trace/slave inventory must partition all55950 rows")
    masters = reader.role("native/mpc/masters", dtype="int32")
    coeff = reader.role("native/mpc/coefficients", dtype="complex128")
    offsets = reader.role("native/mpc/offsets", dtype="int32")
    _indices(masters, n, unique=False, name="MPC masters")
    require(coeff.ndim == 1 and len(coeff) == len(masters) and offsets.ndim == 1
            and len(offsets) >= n+1 and offsets[0] == 0 and offsets[-1] == len(coeff)
            and not np.any(np.diff(offsets.astype(np.int64)) < 0), "invalid full finalized MPC CSR")
    require(not np.isin(masters, slaves).any() and np.isin(masters, active).all(),
            "MPC masters must be independent traces; chained/slave/interior masters inadmissible")
    ptr = reader.role("native/expansion_indptr", shape=(len(trace)+1,), dtype="int64")
    ids = reader.role("native/expansion_indices", dtype="int64")
    data = reader.role("native/expansion_data", dtype="complex128")
    _indices(ids, nt, unique=False, name="trace expansion columns")
    _pointers(ptr, len(ids), size=len(trace)+1, name="complete trace expansion pointers")
    require(data.ndim == 1 and len(data) == len(ids), "trace expansion CSR inventory differs")
    maximum_width = max((int(ptr[row+1])-int(ptr[row]) for row in range(len(trace))), default=0)
    _gate(gate, "complete_native_expansion_rows", payload=len(trace)*512+n*4,
          workspace=len(trace)*128+maximum_width*128,
          complete_expansion_Python_row_allowance_bytes=len(trace)*512,
          actual_expansion_row_count=len(trace), actual_expansion_nnz=len(ids),
          actual_maximum_expansion_width=maximum_width)
    active_id = np.full(n, -1, dtype=np.int32)
    active_id[active] = np.arange(nt, dtype=np.int32)
    expansion = {}
    for index, row in enumerate(trace):
        begin, end = int(ptr[index]), int(ptr[index+1])
        columns, values = ids[begin:end], data[begin:end]
        _indices(columns, nt, name="one trace expansion")
        if active_id[row] >= 0:
            require(len(columns) == 1 and columns[0] == active_id[row] and values[0] == 1,
                    "active trace expansion must be exactly identity")
            require(offsets[row+1] == offsets[row], "independent trace has native MPC master links")
        else:
            a, b = int(offsets[row]), int(offsets[row+1])
            require(b > a and np.array_equal(columns, active_id[masters[a:b]])
                    and np.array_equal(values, coeff[a:b]),
                    "saved condensation expansion differs from actual finalized native MPC")
        expansion[int(row)] = (columns, values)
    require(all(offsets[int(row)+1] == offsets[int(row)] for row in interior)
            and (len(offsets) == n+1 or np.all(offsets[n:] == len(coeff))),
            "interior or trailing native MPC rows contain unsupported links")
    return {"interior": interior, "active": active, "trace": trace, "slaves": slaves,
            "active_id": active_id, "expansion": expansion,
            "native_signatures": {name: _array_signature(value) for name, value in (
                ("slaves", slaves), ("masters", masters), ("coefficients", coeff), ("offsets", offsets))}}


def _expand(active_values, maps):
    import numpy as np
    result = np.zeros(55950, dtype=np.complex128)
    for row, (ids, values) in maps["expansion"].items():
        result[row] = np.dot(values, active_values[ids])
    return result


def _scatter_trace(target, originals, values, maps):
    import numpy as np
    for row, value in zip(originals, values, strict=True):
        ids, coefficients = maps["expansion"][int(row)]
        np.add.at(target, ids, coefficients.conjugate() * value)


def _complex_scalar(value):
    if isinstance(value, dict) and set(value) == {"real", "imag"}:
        result = complex(value["real"], value["imag"])
    elif type(value) in (int, float):
        result = complex(value)
    else:
        raise ValueError("saved normalization_h must be explicit finite JSON complex/real")
    require(math.isfinite(result.real) and math.isfinite(result.imag), "nonfinite carrier normalization")
    return result


def _array_signature(array):
    return {"shape": list(array.shape), "dtype": str(array.dtype), "sha256": _sha(array, header=False)}


def _carrier(reader, report, maps, cells, gate, measures):
    import numpy as np
    source = report.get("carrier_sources")
    require(isinstance(source, dict) and isinstance(source.get("ports"), list)
            and len(source["ports"]) == 532 and source.get("physical_generator_manifest_sha256") == PHYSICAL_GENERATOR,
            "complete current physical532 carrier source required")
    require(source.get("carrier_global_rows") == 55950 and source.get("carrier_ownership_range") == [0, 55950],
            "carrier must own all same80 native rows on MPI1")
    carrier_slaves = reader.bound("carrier/slave_rows", source.get("carrier_slave_rows"),
                                 shape=maps["slaves"].shape, dtype="int32")
    require(np.array_equal(carrier_slaves, maps["slaves"]), "carrier native slave map differs")
    _gate(gate, "carrier_support_maps", payload=55950*8 + 80*532,
          workspace=55950*8 + 80*532 + (4 << 20))
    owner, local = np.full(55950, -1, np.int32), np.full(55950, -1, np.int32)
    for index, cell in enumerate(cells):
        owner[cell["interiors"]] = index
        local[cell["interiors"]] = np.arange(450, dtype=np.int32)
    support = np.zeros((80, 532), dtype=bool)
    h = np.empty(532, dtype=np.complex128)
    ports, keys, physical_keys, q_counts = [], [], set(), [0, 0, 0, 0]
    for index, port in enumerate(source["ports"]):
        require(port.get("port_index") == index and isinstance(port.get("mode_identity"), dict),
                "every ordered carrier port identity required")
        identity, key = port["mode_identity"], port.get("mode_key")
        require(isinstance(key, list) and len(key) == 5 and key[0] == index
                and identity.get("mode_index") == index
                and key[1:] == [identity.get("side"), identity.get("m"), identity.get("n"), identity.get("polarization")],
                "ordered carrier keys differ from mode identities")
        physical = tuple(key[1:])
        alpha_mode, gamma_mode = _complex_scalar(identity.get("alpha")), _complex_scalar(identity.get("gamma"))
        medium = _complex_scalar(identity.get("refractive_index"))
        kt_norm = math.sqrt(abs(alpha_mode)**2 + abs(gamma_mode)**2)
        polarizations = (("x", "y") if kt_norm < 1.e-12 * max(abs((2*math.pi/.7)*medium), 1.)
                         else ("s", "p"))
        order = (index % 266)//2
        expected_semantic = ["top" if index < 266 else "bottom", order//7-9, order % 7-3,
                             polarizations[index % 2]]
        require(physical not in physical_keys and key[1] in ("bottom", "top")
                and type(key[2]) is int and -9 <= key[2] <= 9
                and type(key[3]) is int and -3 <= key[3] <= 3 and key[1:] == expected_semantic,
                "complete unique manualM9/N3 mode inventory required")
        physical_keys.add(physical); keys.append(key); q_counts[key[3] % 4] += 1
        h[index] = _complex_scalar(port.get("normalization_h"))
        require(h[index].imag == 0 and h[index].real > 0,
                "actual native physical normalization_h must be strictly positive finite float")
        arrays = {}
        for side, row_name, value_name in (("B", "coupling_rows", "coupling_values"),
                                           ("D", "projection_rows", "projection_values")):
            refs = port.get("arrays", {})
            rows = reader.bound(f"carrier/port/{index}/" + row_name, refs.get(row_name))
            values = reader.bound(f"carrier/port/{index}/" + value_name, refs.get(value_name),
                                  shape=rows.shape, dtype="complex128")
            _indices(rows, 55950, name="carrier " + side + " rows")
            require(np.all((owner[rows] >= 0) | (maps["active_id"][rows] >= 0)),
                    "carrier contains a native slave or unknown trace")
            support[owner[rows][owner[rows] >= 0], index] = True
            arrays[row_name], arrays[value_name] = rows, values
        ports.append(arrays)
    require(q_counts == [76, 152, 152, 152] and source.get("ordered_mode_keys") == keys,
            "allfour physical q alias inventories/order differ")
    # normalization_h is a float in the live schema. Preserve its scalar type
    # in the digest, rather than changing real values to JSON complex objects.
    digest = hashlib.sha256()
    digest.update(_canonical({"schema": "task40extra.live-boundary-carrier-digest.v1",
        "global_rows": 55950, "ownership_range": [0, 55950], "mode_count": 532,
        "slave_rows": _array_signature(carrier_slaves)}))
    for index, arrays in enumerate(ports):
        digest.update(_canonical({"index": index, "key": keys[index], "H": float(h[index].real),
            **{name: _array_signature(value) for name, value in arrays.items()}}))
    manifest = {"schema": "fullspace-dtn.mode-manifest.v1", "profile": "full3d_scalable_v1",
                "mode_count": 532, "modes": [record["mode_identity"] for record in source["ports"]]}
    require(hashlib.sha256(_canonical(manifest)).hexdigest() == source.get("assembly_mode_manifest_sha256"),
            "actual complete532 mode identity manifest digest differs")
    before, after = report.get("carrier_before"), report.get("carrier_after")
    require(isinstance(before, dict) and before == after
            and before.get("carrier_numeric_sha256") == digest.hexdigest()
            and before.get("ordered_mode_keys") == keys and before.get("mode_count") == 532
            and before.get("physical_generator_manifest_sha256") == PHYSICAL_GENERATOR
            and before.get("assembly_mode_manifest_sha256") == source.get("assembly_mode_manifest_sha256")
            and before.get("assembly_context_sha256") == source.get("assembly_context_sha256"),
            "actual complete saved carrier digest/order differs from before/after live identity")
    diagonal = reader.role("port/H_original_diagonal", shape=(532,), dtype="complex128")
    dense = reader.role("port/H_original_dense", shape=(532, 532), dtype="complex128")
    require(np.array_equal(diagonal, h) and np.array_equal(dense, np.diag(h)),
            "original physical H must exactly bind every ordered native carrier normalization")
    measures.compare("original_H_carrier_diagonal", diagonal, h, ALGEBRA_LIMIT)
    measures.compare("original_H_dense_diagonal", dense, np.diag(h), ALGEBRA_LIMIT)
    return {"ports": ports, "h": h, "support": support, "owner": owner, "local": local,
            "numeric_sha256": digest.hexdigest(), "q_alias_counts": q_counts}


def _B(carrier, alpha):
    import numpy as np
    result = np.zeros(55950, dtype=np.complex128)
    for index, port in enumerate(carrier["ports"]):
        np.add.at(result, port["coupling_rows"], port["coupling_values"] * alpha[index])
    return result


def _D(carrier, storage):
    import numpy as np
    return np.asarray([np.dot(port["projection_values"], storage[port["projection_rows"]])
                       for port in carrier["ports"]], dtype=np.complex128)


def _cell_blocks(carrier, index):
    import numpy as np
    ports = np.flatnonzero(carrier["support"][index]).astype(np.int32)
    bi, di = np.zeros((450, len(ports)), complex), np.zeros((len(ports), 450), complex)
    for column, port_id in enumerate(ports):
        port = carrier["ports"][int(port_id)]
        for target, row_name, value_name in ((bi[:, column], "coupling_rows", "coupling_values"),
                                            (di[column], "projection_rows", "projection_values")):
            rows, values = port[row_name], port[value_name]
            mask = carrier["owner"][rows] == index
            np.add.at(target, carrier["local"][rows[mask]], values[mask])
    return ports, bi, di


def _cell_inventory(reader, report, maps, gate):
    import numpy as np
    source = report.get("original_sources")
    port_cells = report.get("carrier_sources", {}).get("cells")
    require(isinstance(source, dict) and isinstance(source.get("cells"), list)
            and len(source["cells"]) == 80 and isinstance(port_cells, list) and len(port_cells) == 80,
            "all80 tensor and carrier cells required, including zero-port cells")
    cells, interior_parts, trace_union = [], [], set()
    _gate(gate, "complete_cell_maps", payload=80*882*8, workspace=80*882*64)
    for index, (original, port) in enumerate(zip(source["cells"], port_cells, strict=True)):
        require(original.get("cell_index") == index and port.get("cell_index") == index
                and original.get("class_key") == port.get("class_key")
                and type(original.get("class_index")) is int
                and isinstance(original.get("class_key"), list) and len(original["class_key"]) == 5
                and original.get("raw_key") == original["class_key"][:-1]
                and original.get("cell_info") == original["class_key"][-1],
                "actual tensor/carrier cell class identity differs")
        refs = port.get("arrays", {})
        interiors = reader.bound(f"cell/{index}/original_interiors", refs.get("original_interiors"))
        traces = reader.bound(f"cell/{index}/original_trace", refs.get("original_trace"))
        _indices(interiors, 55950, size=450, name="cell interior map")
        _indices(traces, 55950, size=432, name="cell trace map")
        require(not np.intersect1d(interiors, traces).size and np.isin(interiors, maps["interior"]).all()
                and np.isin(traces, maps["trace"]).all(), "cell map leaves complete native partition")
        interior_parts.append(interiors); trace_union.update(map(int, traces))
        cells.append({"interiors": interiors, "traces": traces, "source": original, "port": port})
    require(np.array_equal(np.concatenate(interior_parts), maps["interior"])
            and len(np.unique(np.concatenate(interior_parts))) == 36000
            and trace_union == set(map(int, maps["trace"])),
            "every450 interior in every80 cell and all original traces must be covered")
    positions = reader.role("original/interior_positions", dtype="int32")
    traces = reader.role("original/trace_positions", dtype="int32")
    _indices(positions, 882, size=450, name="actual element interior positions")
    _indices(traces, 882, size=432, name="actual element trace positions")
    require(np.array_equal(np.sort(np.r_[positions, traces]), np.arange(882)),
            "actual complete element position partition differs")
    return cells, positions, traces


def _class_inventory(report, cells, reader):
    source = report["original_sources"]
    classes, raw_classes = source.get("classes"), source.get("raw_classes")
    require(isinstance(classes, list) and 1 <= len(classes) <= 80
            and source.get("oriented_class_count") == len(classes)
            and isinstance(raw_classes, list) and 1 <= len(raw_classes) <= len(classes)
            and source.get("raw_class_count") == len(raw_classes),
            "actual unique raw/oriented class inventory required")
    raw_by_key = {}
    for index, raw in enumerate(raw_classes):
        key = _canonical(raw.get("raw_key"))
        require(key not in raw_by_key
                and reader.roles.get(f"original/raw_class/{index}/tensor") == raw.get("tensor")
                and reader.roles.get(f"original/raw_class/{index}/coordinates") == raw.get("coordinates"),
                "duplicate original raw class or missing exact logical raw role")
        raw_by_key[key] = raw
    covered, seen_keys, used_raw = set(), set(), set()
    for index, entry in enumerate(classes):
        key, ids = entry.get("class_key"), entry.get("cell_indices")
        require(entry.get("class_index") == index and isinstance(key, list) and len(key) == 5
                and _canonical(key) not in seen_keys and isinstance(ids, list) and ids
                and all(type(cell) is int and 0 <= cell < 80 for cell in ids)
                and ids == sorted(set(ids)) and not covered.intersection(ids),
                "complete nonoverlapping unique oriented class inventory required")
        raw_key = _canonical(key[:-1])
        require(raw_key in raw_by_key and entry.get("raw_tensor") == raw_by_key[raw_key].get("tensor"),
                "oriented class must bind exact saved raw tensor class")
        for cell in ids:
            require(cells[cell]["source"]["class_index"] == index
                    and cells[cell]["source"]["class_key"] == key,
                    "every actual cell must bind its exact oriented class")
        covered.update(ids); seen_keys.add(_canonical(key)); used_raw.add(raw_key)
    require(covered == set(range(80)) and used_raw == set(raw_by_key),
            "class/source inventory omits cells or contains unused raw classes")
    return classes, raw_by_key


def _role_inventory(reader, report):
    """Reject partial evidence and unrecognized payloads before further loads."""
    expected = {"native/" + name for name in (
        "trace_original", "active_original", "expansion_indptr", "expansion_indices", "expansion_data", "interior_original")}
    expected.update("native/mpc/" + name for name in ("slaves", "masters", "coefficients", "offsets"))
    expected.update(("original/interior_positions", "original/trace_positions", "carrier/slave_rows"))
    expected.update("port/" + name for name in (
        "H_original_diagonal", "H_original_dense", "Hhat_legacy_dense", "Hhat_independent_dense"))
    for index in range(532):
        expected.update(f"carrier/port/{index}/" + name for name in (
            "coupling_rows", "coupling_values", "projection_rows", "projection_values"))
    for index, cell in enumerate(report["carrier_sources"]["cells"]):
        expected.update(f"cell/{index}/" + name for name in (
            "original_interiors", "original_trace", "ports", "Bi", "Bt", "Di", "Dt", "XiB", "Bhat", "Dhat"))
        if cell.get("Hlocal_is_None") is False:
            expected.add(f"cell/{index}/Hlocal")
        else:
            require(cell.get("Hlocal_is_None") is True, "explicit cell Hlocal state required")
    for index, _entry in enumerate(report["original_sources"]["raw_classes"]):
        expected.update((f"original/raw_class/{index}/tensor", f"original/raw_class/{index}/coordinates"))
    for index, entry in enumerate(report["original_sources"]["classes"]):
        expected.update(f"cache/class/{index}/" + name for name in (
            "S_V", "recovery", "trace_rhs_projection", "LU", "pivots"))
        info = entry.get("original_tensor", {}).get("orientation", {}).get("cell_info")
        require(type(info) is int and 0 <= info <= 2**32-1, "actual bounded cell orientation info required")
        expected.update(f"original/orientation/{info}/" + name for name in ("indptr", "indices", "data"))
    expected.update("controls/" + name for name in (
        "port_probe", "H_apply_dense", "H_apply_compact", "H_solve_dense", "H_solve_compact",
        "Hhat_dense_action", "Hhat_factored_action", "reduced_probe", "arbitrary_full_rhs", "arbitrary_port_rhs",
        "reduced_action_dense", "reduced_action_compact", "reduced_rhs_dense", "reduced_rhs_compact",
        "recovery_dense", "recovery_compact", "recovery_expanded_from_condensation", "recovery_expanded_from_actual_MPC"))
    expected.update("material_control/" + name for name in (
        "target_XiB", "Bi", "Di", "XiB", "H_original", "correction", "Hhat_dense", "alpha",
        "dense_action", "factored_action", "omitted_action", "wrong_sign_action", "wrong_conjugation_action",
        "port_rhs", "original_H_solve", "wrong_Hhat_solve"))
    for label in ("arbitrary", "manufactured"):
        expected.update(label + "/" + name for name in (
            "storage", "full_rhs", "port_rhs", "reduced", "live_volume_action", "live_original_action",
            "B_alpha", "D_field", "H_alpha", "effective_native_rhs", "augmented_fe_residual",
            "augmented_port_residual", "original_native_residual", "derived_native_residual",
            "reduced_rhs", "reduced_action", "reduced_residual"))
    expected.update(("manufactured/chosen_native_storage", "manufactured/chosen_actual_MPC_field"))
    require(set(reader.roles) == expected,
            "required complete saved-role inventory differs; missing=" + str(sorted(expected-set(reader.roles)))
            + "; extra=" + str(sorted(set(reader.roles)-expected)))


def _original_tensor(reader, report, entry, raw_record, gate):
    import numpy as np
    from scipy.sparse import csr_matrix
    _gate(gate, "unique_class_tensor/" + str(entry["class_index"]),
          payload=3*882**2*16, workspace=8*882**2*16 + (64 << 20),
          simultaneous_oriented_classes=1, local_dense_factor_dimension=450,
          stream_release_before_next_class=True)
    raw = reader.ref(entry.get("raw_tensor"), shape=(882, 882), dtype="complex128")
    coordinates = reader.ref(raw_record.get("coordinates"), shape=(24,), dtype="float64").reshape(8, 3)
    widths = tuple(float(value) for value in coordinates.max(axis=0)-coordinates.min(axis=0))
    require(widths == tuple(entry["class_key"][1:4]) and all(value > 0 for value in widths)
            and np.all(coordinates.min(axis=0) == 0)
            and len({tuple(point) for point in coordinates}) == 8
            and all(value in (0., widths[axis]) for point in coordinates
                    for axis, value in enumerate(point)),
            "actual raw tensor class canonical hexahedral geometry differs")
    descriptor = entry.get("original_tensor", {})
    require(descriptor.get("representation") == "raw_tensor_congruence"
            and descriptor.get("recipe") == "T@raw@T.T; no conjugation"
            and descriptor.get("raw_tensor") == entry["raw_tensor"]
            and descriptor.get("shape") == [882, 882] and descriptor.get("dtype") == "complex128",
            "exact original raw/oriented tensor descriptor required")
    orient = descriptor.get("orientation", {})
    require(orient.get("representation") == "actual_Basix_T_apply_CSR"
            and orient.get("shape") == [882, 882] and orient.get("cell_info") == entry["class_key"][-1]
            and type(orient.get("basis_hash")) is int and orient.get("small_entry_threshold") is None,
            "actual complete no-threshold Basix orientation witness required")
    role = "original/orientation/" + str(orient["cell_info"]) + "/"
    ptr = reader.bound(role + "indptr", orient.get("indptr"), shape=(883,))
    indices = reader.bound(role + "indices", orient.get("indices"))
    data = reader.bound(role + "data", orient.get("data"), shape=indices.shape, dtype="complex128")
    _indices(indices, 882, unique=False, name="orientation columns")
    _pointers(ptr, len(indices), size=883, strictly_increasing=True, name="orientation pointers")
    require(not np.any(data == 0),
            "complete exact nonempty CSR orientation rows required")
    for row in range(882):
        _indices(indices[int(ptr[row]):int(ptr[row+1])], 882, name="orientation row")
    transform = csr_matrix((data, indices, ptr), shape=(882, 882), copy=False)
    intermediate = np.asarray(transform @ raw)
    tensor = np.asarray(transform @ intermediate.T).T
    del intermediate, transform
    require(bool(np.isfinite(tensor).all()), "reconstructed original tensor is nonfinite")
    byte_hash = _sha(tensor, header=False)
    identity = report.get("condensation_audit", {}).get("action_only_complete_tensor_identities", {}).get(
        repr(tuple(entry["class_key"])))
    require(isinstance(identity, dict) and identity.get("shape") == [882, 882]
            and identity.get("dtype") == "complex128"
            and identity.get("raw_sha256") == _sha(raw, header=False)
            and identity.get("oriented_sha256") == byte_hash
            and descriptor.get("C_order_bytes_sha256") == byte_hash,
            "actual pre-elimination raw/oriented tensor hashes differ")
    return tensor, byte_hash


def _saved_cell(reader, cell, index, ports, bi, di, recovery, projection, solve, measures):
    import numpy as np
    record, refs = cell["port"], cell["port"].get("arrays", {})
    stored_ports = reader.bound(f"cell/{index}/ports", refs.get("ports"))
    _indices(stored_ports, 532, size=len(ports), name="cell physical ports")
    require(np.array_equal(stored_ports, ports) and record.get("zero_port_cell") is (len(ports) == 0),
            "cell support must match actual raw carrier, including stored zeros and zero-port cells")
    expected = {"Bi": bi, "Di": di,
                "Bt": np.zeros((432, len(ports)), dtype=np.complex128),
                "Dt": np.zeros((len(ports), 432), dtype=np.complex128)}
    xib = solve(bi) if len(ports) else np.empty((450, 0), dtype=np.complex128)
    expected.update(XiB=xib, Bhat=expected["Bt"] + projection @ bi,
                    Dhat=expected["Dt"] + di @ recovery)
    for name, values in expected.items():
        saved = reader.bound(f"cell/{index}/" + name, refs.get(name), shape=values.shape, dtype="complex128")
        if name in ("Bi", "Bt", "Di", "Dt"):
            require(np.array_equal(saved, values), "raw carrier cell coupling identity differs: " + name)
        measures.compare(f"cell/{index}/" + name, saved, values)
    if record.get("Hlocal_is_None") is True:
        require("Hlocal" not in refs, "None Hlocal must have no saved payload")
    else:
        hlocal = reader.bound(f"cell/{index}/Hlocal", refs.get("Hlocal"),
                             shape=(len(ports), len(ports)), dtype="complex128")
        require(not np.any(hlocal != 0), "nonzero Hlocal is unsupported by fresh component")
    return xib, expected["Bhat"], expected["Dhat"]


def _state(reader, report, label):
    packet = report.get(label + "_state", {}).get("arrays")
    require(isinstance(packet, dict), "complete saved " + label + " residual packet required")
    fields = {"storage": (55950,), "full_rhs": (55950,), "port_rhs": (532,), "reduced": (17524,),
              "live_volume_action": (55950,), "live_original_action": (55950,), "B_alpha": (55950,),
              "D_field": (532,), "H_alpha": (532,), "effective_native_rhs": (55950,),
              "augmented_fe_residual": (55950,), "augmented_port_residual": (532,),
              "original_native_residual": (55950,), "derived_native_residual": (55950,),
              "reduced_rhs": (17524,), "reduced_action": (17524,), "reduced_residual": (17524,)}
    return {name: reader.bound(label + "/" + name, packet.get(name), shape=shape, dtype="complex128")
            for name, shape in fields.items()}


def _material(reader, report, class_index, vii, solve, gate, measures):
    import numpy as np
    record = report.get("separate_material_control", {})
    require(record.get("label") == "artificial_non_Hermitian_material_control_on_actual_p6_cell_cache"
            and record.get("physical_case") is False and record.get("physical_PDE_data_modified") is False
            and record.get("cell_index") == 0 and record.get("interior_dimension") == 450,
            "separate actual-p6 artificial non-Hermitian control required")
    refs = record.get("arrays", {})
    shapes = {"target_XiB": (450, 2), "Bi": (450, 2), "Di": (2, 450), "XiB": (450, 2),
              "H_original": (2, 2), "correction": (2, 2), "Hhat_dense": (2, 2),
              "alpha": (2,), "dense_action": (2,), "factored_action": (2,), "omitted_action": (2,),
              "wrong_sign_action": (2,), "wrong_conjugation_action": (2,), "port_rhs": (2,),
              "original_H_solve": (2,), "wrong_Hhat_solve": (2,)}
    arrays = {name: reader.bound("material_control/" + name, refs.get(name), shape=shape, dtype="complex128")
              for name, shape in shapes.items()}
    _gate(gate, "material_negative_control", workspace=450*2*16*8 + (1 << 20), class_index=class_index)
    rows = np.arange(1, 451, dtype=np.float64)
    target = np.column_stack((np.cos(.17*rows)+1j*np.sin(.31*rows),
                              np.cos(.23*rows)+1j*np.sin(.41*rows))) / np.sqrt(450)
    measures.compare("material/target_recipe", arrays["target_XiB"], target, ALGEBRA_LIMIT)
    measures.compare("material/Bi_original_Vii", arrays["Bi"], vii @ target)
    xib = solve(arrays["Bi"])
    measures.compare("material/actual_original_dense_solve", arrays["XiB"], xib)
    measures.compare("material/actual_p6_target_recovery", xib, target)
    di = np.vstack((np.sin(.29*rows)+1j*np.cos(.37*rows),
                    np.sin(.43*rows)+1j*np.cos(.19*rows))) / np.sqrt(450)
    raw_norm = float(np.linalg.norm(di @ xib))
    require(math.isfinite(raw_norm) and raw_norm > 0, "material correction is zero/nonfinite")
    di *= .5/raw_norm
    measures.compare("material/Di_recipe", arrays["Di"], di, ALGEBRA_LIMIT)
    h = np.diag(np.asarray([1.+.2j, 1.4-.3j], dtype=np.complex128))
    alpha, rhs = np.asarray([.4+.7j, -.2+.9j]), np.asarray([.8-.3j, -.5+.6j])
    measures.compare("material/original_H_recipe", arrays["H_original"], h, ALGEBRA_LIMIT)
    measures.compare("material/alpha_recipe", arrays["alpha"], alpha, ALGEBRA_LIMIT)
    measures.compare("material/RHS_recipe", arrays["port_rhs"], rhs, ALGEBRA_LIMIT)
    correction, hhat = di @ xib, h + di @ xib
    require(math.isfinite(float(np.linalg.norm(correction))) and float(np.linalg.norm(correction)) >= .49,
            "separate material control must have materially nonzero correction")
    expected = {"correction": correction, "Hhat_dense": hhat, "dense_action": hhat @ alpha,
        "factored_action": h @ alpha + di @ (xib @ alpha), "omitted_action": h @ alpha,
        "wrong_sign_action": (h-correction) @ alpha,
        "wrong_conjugation_action": h @ alpha + di.conjugate() @ (xib @ alpha),
        "original_H_solve": np.linalg.solve(h, rhs), "wrong_Hhat_solve": np.linalg.solve(hhat, rhs)}
    for name, value in expected.items():
        measures.compare("material/" + name, arrays[name], value, ALGEBRA_LIMIT)
    measures.compare("material/dense_factored", expected["factored_action"], expected["dense_action"], ALGEBRA_LIMIT)
    for name, wrong, reference in (
        ("omitted_correction", expected["omitted_action"], expected["dense_action"]),
        ("wrong_sign", expected["wrong_sign_action"], expected["dense_action"]),
        ("wrong_conjugation", expected["wrong_conjugation_action"], expected["dense_action"]),
        ("Hhat_substituted_for_original_H", expected["wrong_Hhat_solve"], expected["original_H_solve"])):
        measures.separate(name, wrong, reference)
    return {"correction_norm": float(np.linalg.norm(correction)), "cell_index": 0,
            "physical_case": False, "allfour_negative_controls_separated": True}


def check_component(report, load_array, *, allocation_gate, checkpoint):
    """Recompute component evidence from current-run immutable saved arrays.

    load_array(reference) receives the exact canonical member descriptor; the
    caller resolves its name inside the admitted artifact. Failures checkpoint
    a JSON-safe diagnostic and raise. All PASS fields in report are ignored.
    """
    require(callable(load_array) and callable(allocation_gate) and callable(checkpoint),
            "checker requires explicit loader/resource admission/persistent diagnostics")
    measures = _Measurements(checkpoint)
    try:
        result = _check_component(report, load_array, allocation_gate, checkpoint, measures)
        json.dumps(result, allow_nan=False)
        checkpoint("component_checker_receipt", result)
        return result
    except BaseException as error:
        checkpoint("component_checker_failure", {
            "schema": CHECKER_SCHEMA, "status": "failed", "independent_component_pass": False,
            "exception_type": type(error).__name__, "message": str(error),
            "completed_metrics": measures.records, "negative_controls": measures.negative,
            "source_status": SOURCE_STATUS, "durable_archive_verified": False})
        raise


def _check_component(report, load_array, gate, checkpoint, measures):
    require(isinstance(report, dict) and report.get("schema") == WORKER_SCHEMA
            and report.get("actual_inventory") == INVENTORY,
            "exact current fresh same80 p6 component schema/inventory required")
    # This allocation preadmission precedes numerical imports and all arrays.
    _gate(gate, "numerical_dependencies", workspace=64 << 20, FE_imports=False, JIT=False)
    import numpy as np
    from scipy.linalg import lu_factor, lu_solve
    reader = _Reader(report, load_array, gate)
    maps = _native_maps(reader, gate)
    profile = report.get("fresh_profile", {})
    actual_profile = profile.get("fresh_c1_actual_inventory", {})
    expected_profile_counts = {"cell_count": 80, "local_space_dimension": 882,
        "local_interior_rows": 450, "local_trace_rows": 432, "storage_rows": 55950,
        "independent_rows": 52992, "interior_rows": 36000, "independent_trace_rows": 16992,
        "native_slave_rows": 2958}
    require(profile.get("degree") == 6 and profile.get("element_degree") == 6
            and profile.get("local_space_dimension") == 882
            and profile.get("quadrature_degree") == 27 and profile.get("primary_facet_points") == 196
            and profile.get("fresh_fixture_c1") is True
            and all(actual_profile.get(name) == value for name, value in expected_profile_counts.items())
            and actual_profile.get("native_MPC") == maps["native_signatures"],
            "fresh degree6 profile must bind the independently reconstructed actual FE/native MPC inventory")
    cells, ipos, tpos = _cell_inventory(reader, report, maps, gate)
    classes, raw_by_key = _class_inventory(report, cells, reader)
    _role_inventory(reader, report)
    carrier = _carrier(reader, report, maps, cells, gate, measures)
    _gate(gate, "all_component_control_vectors", payload=96*55950*16 + 8*532**2*16,
          workspace=24*55950*16 + (16 << 20))
    alpha = reader.role("controls/port_probe", shape=(532,), dtype="complex128")
    probe = reader.role("controls/reduced_probe", shape=(17524,), dtype="complex128")
    rhs = reader.role("controls/arbitrary_full_rhs", shape=(55950,), dtype="complex128")
    g = reader.role("controls/arbitrary_port_rhs", shape=(532,), dtype="complex128")
    require(np.array_equal(probe[-532:], alpha) and np.all(rhs[maps["interior"]] != 0)
            and np.all(g != 0) and np.all(rhs[maps["slaves"]] == 0),
            "arbitrary control requires all36000 interior loads, nonzero532 port RHS and exact slave zeros")
    for name, expected in (("H_apply_dense", carrier["h"]*alpha), ("H_apply_compact", carrier["h"]*alpha),
                           ("H_solve_dense", alpha/carrier["h"]), ("H_solve_compact", alpha/carrier["h"])):
        measures.compare("original_H/" + name, reader.role("controls/"+name, shape=(532,), dtype="complex128"),
                         expected, ALGEBRA_LIMIT)
    states = {label: _state(reader, report, label) for label in ("arbitrary", "manufactured")}
    chosen = reader.role("manufactured/chosen_native_storage", shape=(55950,), dtype="complex128")
    for name, expected in (("reduced", probe), ("full_rhs", rhs), ("port_rhs", g)):
        measures.compare("arbitrary/control_binding/" + name, states["arbitrary"][name], expected, ALGEBRA_LIMIT)
    require(np.array_equal(states["manufactured"]["reduced"], probe)
            and np.array_equal(chosen[maps["active"]], probe[:16992])
            and np.array_equal(chosen[maps["interior"]], rhs[maps["interior"]]),
            "manufactured chosen state must use the complete nonzero arbitrary interior probe")
    require(all(np.all(state["storage"][maps["slaves"]] == 0)
                and np.all(state["full_rhs"][maps["slaves"]] == 0) for state in states.values())
            and np.all(chosen[maps["slaves"]] == 0), "native state/RHS storage must retain exact slave zeros")
    work = {}
    for label, state in states.items():
        trace_expanded = _expand(state["reduced"][:16992], maps)
        require(np.array_equal(state["storage"][maps["active"]], state["reduced"][:16992]),
                "native independent trace storage differs from reduced state")
        action = np.zeros(17524, dtype=np.complex128)
        action[-532:] = carrier["h"] * state["reduced"][-532:]
        reduced_rhs = np.r_[state["full_rhs"][maps["active"]], state["port_rhs"]].copy()
        recovered = np.zeros(55950, dtype=np.complex128)
        recovered[maps["active"]] = state["reduced"][:16992]
        volume = np.zeros(55950, dtype=np.complex128)
        # Raw carrier trace entries are already independent MPC-dual rows.
        for port, arrays in enumerate(carrier["ports"]):
            for row_name, value_name, side in (("coupling_rows", "coupling_values", "B"),
                                               ("projection_rows", "projection_values", "D")):
                rows, values = arrays[row_name], arrays[value_name]
                mask = maps["active_id"][rows] >= 0
                ids = maps["active_id"][rows[mask]]
                if side == "B":
                    np.add.at(action, ids, values[mask]*state["reduced"][-532+port])
                else:
                    action[16992+port] -= np.dot(values[mask], state["reduced"][ids])
        work[label] = {"trace": trace_expanded, "action": action, "rhs": reduced_rhs,
                       "recovery": recovered, "volume": volume}
    hhat = np.diag(carrier["h"])
    factored = carrier["h"] * alpha
    class_checks, cell_checks, support_checks, material_result = [], [], [], None
    for entry in classes:
        class_index = entry["class_index"]
        tensor, tensor_sha = _original_tensor(reader, report, entry,
                                              raw_by_key[_canonical(entry["class_key"][:-1])], gate)
        vii, vit = tensor[np.ix_(ipos, ipos)], tensor[np.ix_(ipos, tpos)]
        vti, vtt = tensor[np.ix_(tpos, ipos)], tensor[np.ix_(tpos, tpos)]
        # A fresh original-tensor local450 factor is independent of saved LU.
        factor = lu_factor(vii, overwrite_a=False, check_finite=True)
        solve = lambda values: lu_solve(factor, values, overwrite_b=False, check_finite=True)
        recovery = -solve(vit)
        projection = -lu_solve(factor, vti.T, trans=1, overwrite_b=False, check_finite=True).T
        schur = vtt + vti @ recovery
        cache = entry.get("cache_arrays", {})
        for name, value in (("S_V", schur), ("recovery", recovery), ("trace_rhs_projection", projection)):
            saved = reader.bound(f"cache/class/{class_index}/" + name, cache.get(name),
                                 shape=value.shape, dtype="complex128")
            measures.compare(f"class/{class_index}/"+name, saved, value)
            del saved
        saved_lu = reader.bound(f"cache/class/{class_index}/LU", cache.get("LU"),
                               shape=(450, 450), dtype="complex128")
        saved_pivots = reader.bound(f"cache/class/{class_index}/pivots", cache.get("pivots"),
                                   shape=(450,), dtype="int32")
        inverse_action = solve_fresh_p6_saved_LU(saved_lu, saved_pivots, vii,
                                                allocation_gate=gate, label=str(class_index)+"_original_Vii")
        measures.compare(f"class/{class_index}/saved_LU_original_matrix", inverse_action,
                         np.eye(450, dtype=np.complex128))
        saved_recovery = solve_fresh_p6_saved_LU(saved_lu, saved_pivots, vit,
                                                allocation_gate=gate, label=str(class_index)+"_trace")
        measures.compare(f"class/{class_index}/saved_LU_original_trace_solve", saved_recovery, -recovery)
        del inverse_action, saved_recovery, saved_lu, saved_pivots
        for index in entry["cell_indices"]:
            cell = cells[index]
            actual_ports = int(np.count_nonzero(carrier["support"][index]))
            _gate(gate, "cell_port_algebra/" + str(index),
                  payload=actual_ports*(450*5+432*4)*16,
                  workspace=actual_ports*(450*6+432*4)*16 + actual_ports**2*16*3 + (1 << 20),
                  actual_local_port_count=actual_ports, local_dense_factor_count=0)
            ports, bi, di = _cell_blocks(carrier, index)
            xib, bhat, dhat = _saved_cell(reader, cell, index, ports, bi, di, recovery, projection, solve, measures)
            correction = di @ xib
            hhat[np.ix_(ports, ports)] += correction
            factored[ports] += di @ (xib @ alpha[ports])
            support_checks.append({"cell_index": index, "port_count": len(ports),
                                   "Bi_nonzero": int(np.count_nonzero(bi)), "Di_nonzero": int(np.count_nonzero(di)),
                                   "correction_norm": float(np.linalg.norm(correction)),
                                   "zero_port_cell_checked": len(ports) == 0})
            for label, state in states.items():
                item, interiors, traces = work[label], cell["interiors"], cell["traces"]
                local_trace, local_alpha = item["trace"][traces], state["reduced"][-532:][ports]
                fi_solved = solve(state["full_rhs"][interiors])
                expected_i = fi_solved + recovery @ local_trace - xib @ local_alpha
                item["recovery"][interiors] = expected_i
                local_action = schur @ local_trace + bhat @ local_alpha
                _scatter_trace(item["action"], traces, local_action, maps)
                item["action"][16992+ports] += -dhat @ local_trace + correction @ local_alpha
                _scatter_trace(item["rhs"], traces, projection @ state["full_rhs"][interiors], maps)
                item["rhs"][16992+ports] += di @ fi_solved
                local_field = np.empty(882, dtype=np.complex128)
                local_field[ipos], local_field[tpos] = state["storage"][interiors], item["trace"][traces]
                local_volume = tensor @ local_field
                item["volume"][interiors] += local_volume[ipos]
                scatter = np.zeros(16992, dtype=np.complex128)
                _scatter_trace(scatter, traces, local_volume[tpos], maps)
                item["volume"][maps["active"]] += scatter
            cell_checks.append(index)
            if index == 0:
                require(report.get("separate_material_control", {}).get("class_key") == entry["class_key"],
                        "synthetic material control is detached from actual cell0 class")
                material_result = _material(reader, report, class_index, vii, solve, gate, measures)
            del bi, di, xib, bhat, dhat, correction
        class_checks.append({"class_index": class_index, "cell_indices": entry["cell_indices"],
                             "oriented_tensor_C_bytes_sha256": tensor_sha,
                             "original_dense_local_solve_checked": True, "saved_LU_private_pivots_checked": True})
        del tensor, vii, vit, vti, vtt, factor, solve, recovery, projection, schur
    require(sorted(cell_checks) == list(range(80)) and material_result is not None,
            "complete everycell/uniqueclass/material control coverage required")
    measures.compare("Hhat/legacy_dense", reader.role("port/Hhat_legacy_dense", shape=(532, 532), dtype="complex128"),
                     hhat, ALGEBRA_LIMIT)
    measures.compare("Hhat/worker_independent_dense", reader.role("port/Hhat_independent_dense", shape=(532, 532), dtype="complex128"),
                     hhat, ALGEBRA_LIMIT)
    measures.compare("Hhat/dense_factored_recomputed", factored, hhat @ alpha)
    for name, value in (("Hhat_dense_action", hhat @ alpha), ("Hhat_factored_action", factored)):
        measures.compare("Hhat/"+name, reader.role("controls/"+name, shape=(532,), dtype="complex128"), value)
    for label, state in states.items():
        item, a = work[label], state["reduced"][-532:]
        measures.compare(label+"/full_recovery_from_original_tensors", state["storage"], item["recovery"])
        measures.compare(label+"/reduced_action_from_original_tensors", state["reduced_action"], item["action"])
        measures.compare(label+"/full_interior_port_RHS_reduction", state["reduced_rhs"], item["rhs"])
        ba, dx, hp = _B(carrier, a), _D(carrier, state["storage"]), carrier["h"]*a
        effective = state["full_rhs"] - _B(carrier, state["port_rhs"]/carrier["h"])
        native = item["volume"] + _B(carrier, dx/carrier["h"])
        fe, port = state["full_rhs"]-item["volume"]-ba, state["port_rhs"]+dx-hp
        original = effective-native
        derived = fe-_B(carrier, port/carrier["h"])
        expected = {"live_volume_action": item["volume"], "live_original_action": native,
                    "B_alpha": ba, "D_field": dx, "H_alpha": hp, "effective_native_rhs": effective,
                    "augmented_fe_residual": fe, "augmented_port_residual": port,
                    "original_native_residual": original, "derived_native_residual": derived,
                    "reduced_residual": item["rhs"]-item["action"]}
        scales = {"augmented_fe_residual": float(np.linalg.norm(state["full_rhs"])+np.linalg.norm(item["volume"])+np.linalg.norm(ba)),
                  "augmented_port_residual": float(np.linalg.norm(state["port_rhs"])+np.linalg.norm(dx)+np.linalg.norm(hp)),
                  "original_native_residual": float(np.linalg.norm(effective)+np.linalg.norm(native)),
                  "derived_native_residual": float(np.linalg.norm(state["full_rhs"])+np.linalg.norm(item["volume"])
                                                   +np.linalg.norm(ba)+np.linalg.norm(_B(carrier, port/carrier["h"]))),
                  "reduced_residual": float(np.linalg.norm(item["rhs"])+np.linalg.norm(item["action"]))}
        for name, value in expected.items():
            measures.compare(label+"/"+name, state[name], value, ALGEBRA_LIMIT,
                             scale=scales.get(name, float(np.linalg.norm(value)+np.linalg.norm(state[name]))))
        measures.compare(label+"/original_augmented_closure", original, derived, ALGEBRA_LIMIT,
                         scale=float(np.linalg.norm(effective)+np.linalg.norm(native)+np.linalg.norm(fe)+np.linalg.norm(derived)))
        if label == "manufactured":
            measures.compare("manufactured/original_state_recovery", item["recovery"], chosen)
            for name, residual, scale, bound in (
                ("original_native", original, np.linalg.norm(effective), RESIDUAL_LIMIT),
                ("augmented_FE", fe, np.linalg.norm(state["full_rhs"])+np.linalg.norm(item["volume"])+np.linalg.norm(ba), RESIDUAL_LIMIT),
                ("augmented_port", port, np.linalg.norm(state["port_rhs"])+np.linalg.norm(dx)+np.linalg.norm(hp), RESIDUAL_LIMIT),
                ("reduced", item["rhs"]-item["action"], np.linalg.norm(item["rhs"])+np.linalg.norm(item["action"]), ACTION_LIMIT)):
                measures.compare("manufactured/residual/"+name, residual, np.zeros_like(residual), bound, scale=scale)
    for name, value in (("reduced_action_dense", work["arbitrary"]["action"]),
                        ("reduced_action_compact", work["arbitrary"]["action"]),
                        ("reduced_rhs_dense", work["arbitrary"]["rhs"]),
                        ("reduced_rhs_compact", work["arbitrary"]["rhs"]),
                        ("recovery_dense", work["arbitrary"]["recovery"]),
                        ("recovery_compact", work["arbitrary"]["recovery"])):
        measures.compare("complete_control/"+name, reader.role("controls/"+name, shape=value.shape, dtype="complex128"), value)
    arbitrary_expanded = work["arbitrary"]["recovery"].copy()
    arbitrary_expanded[maps["trace"]] = work["arbitrary"]["trace"][maps["trace"]]
    for name in ("recovery_expanded_from_condensation", "recovery_expanded_from_actual_MPC"):
        measures.compare("actual_MPC/"+name, reader.role("controls/"+name, shape=(55950,), dtype="complex128"), arbitrary_expanded)
    chosen_expanded = chosen.copy()
    chosen_expanded[maps["trace"]] = _expand(chosen[maps["active"]], maps)[maps["trace"]]
    measures.compare("manufactured/chosen_actual_MPC_field",
                     reader.role("manufactured/chosen_actual_MPC_field", shape=(55950,), dtype="complex128"), chosen_expanded)
    reader.verify_remaining()
    return {"schema": CHECKER_SCHEMA, "source_status": SOURCE_STATUS,
            "status": "independent_saved_component_controls_passed",
            "independent_component_pass": True, "durable_archive_verified": False,
            "source_ABI_provenance_binding": "caller_required_not_checked_here", "external_supervision_required": True,
            "actual_inventory_recomputed": dict(INVENTORY), "cells_checked": sorted(cell_checks),
            "unique_classes_checked": class_checks, "physical_correction_support": support_checks,
            "physical_correction_norm_recomputed": float(np.linalg.norm(hhat-np.diag(carrier["h"]))),
            "physical_correction_materiality_claim": False, "separate_material_control": material_result,
            "carrier_numeric_sha256_recomputed": carrier["numeric_sha256"],
            "q_alias_counts_recomputed": carrier["q_alias_counts"],
            "metrics": measures.records, "negative_controls": measures.negative,
            "all_saved_members_hash_checked": len(reader.seen) == len(reader.members),
            "unique_saved_members_checked": len(reader.seen), "uncompressed_numeric_bytes": reader.numeric_bytes,
            "saved_pivot_helper": {"source_status": SOURCE_STATUS, "dimension": 450,
                "historical108_semantics_provenance_sha256": PIVOT_HELPER_PROVENANCE_SHA256,
                "historical_hash_is_new_helper_hash": False, "private_writable_int32_copy": True},
            "limits": {"action_recovery": ACTION_LIMIT, "original_residual": RESIDUAL_LIMIT,
                       "pure_algebra": ALGEBRA_LIMIT, "zero_scale_rule": "error_must_be_exactly_zero"},
            "arbitrary_retained_state_claimed_solved": False, "manufactured_consistent_state_checked": True,
            "global_p6_matrix_created": False, "global_p6_factor_created": False,
            "p6_full_chain_claim": False, "physical_outputs_claim": False,
            "durability_and_compacted_archive_measurements_owned_by_caller": True}


__all__ = ("check_component", "solve_fresh_p6_saved_LU", "metric_record", "CHECKER_SCHEMA")
