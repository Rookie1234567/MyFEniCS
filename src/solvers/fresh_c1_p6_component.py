"""Fresh same80 p6 component controls; explicit research entry point only.

This source is staged and unqualified.  It borrows a previously built and
same-live-qualified physical bundle.  The caller must supervise *all* cold JIT
before building that bundle, provide a measured allocation gate, and retain the
current qualification receipt.  No quotient, global p6 matrix, global p6 factor,
physical outputs, or solver-default change is introduced here.

The returned receipt describes worker evidence, never independent qualification.
The independent checker must read the hash-bound original cell tensors and
recompute its own local dense solves.  Saved/mmap LU pivots must be copied to a
private writable int32 array after admission before any SciPy solve.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Callable, Mapping


SCHEMA = "fresh-c1.same80.p6-component.v1"
SOURCE_STATUS = "NEW_UNQUALIFIED"
ACTION_RECOVERY_LIMIT = 1.0e-11
ORIGINAL_RESIDUAL_LIMIT = 1.0e-10
ALGEBRA_LIMIT = 1.0e-12
ZERO_SCALE_ABSOLUTE_LIMIT = 1.0e-12
GEOMETRY_TOLERANCE = 1.0e-11
NPY_HEADER_BYTES_UPPER = 4096
P6_INVENTORY = {
    "degree": 6, "cell_count": 80, "local_dimension": 882,
    "local_interiors": 450, "local_traces": 432, "storage_rows": 55950,
    "independent_rows": 52992, "interior_rows": 36000,
    "active_trace_rows": 16992, "port_rows": 532,
}


class SnapshotBudgetExceeded(MemoryError):
    """Controlled stop before export; complete evidence is never clipped."""


def require_callbacks(allocation_gate, save_array, checkpoint, archive_payload_limit_bytes):
    """Reject missing supervision/export callbacks before numerical imports."""
    for name, callback in (("allocation_gate", allocation_gate),
                           ("save_array", save_array), ("checkpoint", checkpoint)):
        if not callable(callback):
            raise TypeError(f"{name} must be callable")
    if (isinstance(archive_payload_limit_bytes, bool)
            or not isinstance(archive_payload_limit_bytes, int)
            or archive_payload_limit_bytes <= 0):
        raise ValueError("archive_payload_limit_bytes must be a positive integer")


def admit_snapshot_bytes(current_bytes, numeric_bytes, limit_bytes):
    """Admit a conservative .npy member upper bound before exporting it."""
    for value in (current_bytes, numeric_bytes, limit_bytes):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("snapshot sizes must be nonnegative integers")
    projected = current_bytes + numeric_bytes + NPY_HEADER_BYTES_UPPER
    if projected > limit_bytes:
        raise SnapshotBudgetExceeded("fresh p6 snapshot payload exceeds admitted archive limit")
    return projected


def metric_record(error_norm, operation_scale, limit, *, absolute_limit=ZERO_SCALE_ABSOLUTE_LIMIT,
                  nonzero_error_at_zero_scale=False):
    """Use relative error at positive scale and exact equality at zero scale."""
    numbers = tuple(float(x) for x in (error_norm, operation_scale, limit, absolute_limit))
    if any(not math.isfinite(x) or x < 0 for x in numbers):
        return {"finite": False, "error_norm": None, "operation_scale": None,
                "relative": None, "limit": float(limit) if math.isfinite(float(limit)) else None,
                "absolute_limit": float(absolute_limit) if math.isfinite(float(absolute_limit)) else None,
                "passed": False}
    error, scale, relative_limit, absolute = numbers
    relative = error / scale if scale > 0 else (0.0 if error == 0 else None)
    finite = relative is None or math.isfinite(relative)
    exact_zero_violation = scale == 0 and bool(nonzero_error_at_zero_scale)
    return {"finite": finite, "error_norm": error, "operation_scale": scale,
            "relative": relative if finite else None, "limit": relative_limit,
            "absolute_limit": absolute, "zero_scale_rule": "error_must_be_exactly_zero",
            "absolute_limit_is_supplemental_nonzero_scale_metadata": True,
            "nonzero_error_at_zero_scale": exact_zero_violation,
            "error_norm_underflow_at_zero_scale": exact_zero_violation and error == 0,
            "passed": finite and not exact_zero_violation
                      and (error <= relative_limit * scale if scale > 0 else error == 0)}


def _gate(callback, name, payload=0, workspace=0, **facts):
    callback("fresh_p6_component/" + name, {
        "matrix_payload_bytes": int(payload), "workspace_bytes": int(workspace),
        "allocation_semantics": "additional_objects_to_current_resident_RSS", **facts,
    })


def _jsonable(value):
    """Reuse established scalar/container conversion; reject NaN/Inf JSON."""
    from .fullspace_dtn_action import _jsonable as convert
    result = convert(value)
    json.dumps(result, allow_nan=False)
    return result


def _finite(array):
    import numpy as np
    value = np.asarray(array)
    if value.ndim < 2:
        return bool(np.isfinite(value).all())
    return all(bool(np.isfinite(row).all()) for row in value)


def _sha(array, *, header=True):
    """Hash by row so a Fortran-order LU never needs a full C-order copy."""
    import numpy as np
    value = np.asarray(array)
    digest = hashlib.sha256()
    if header:
        digest.update(repr((value.shape, str(value.dtype))).encode("utf-8"))
    if value.ndim < 2:
        digest.update(value.tobytes(order="C"))
    else:
        for row in value:
            digest.update(row.tobytes(order="C"))
    return digest.hexdigest()


class _Snapshot:
    """Export each identical payload once; bind every role to its member."""

    def __init__(self, save_array, gate, checkpoint, limit):
        self.save_array, self.gate, self.checkpoint = save_array, gate, checkpoint
        self.limit, self.upper_bytes, self.numeric_bytes = limit, 0, 0
        self.members, self.roles, self.interned = [], {}, {}

    def array(self, role, value):
        import numpy as np
        array = np.asarray(value)
        if role in self.roles or array.dtype.kind not in "biufc":
            raise ValueError("snapshot role repeats or array dtype is unsupported")
        row_bytes = int(array.nbytes if array.ndim < 2 else array[0].nbytes if len(array) else 0)
        _gate(self.gate, "snapshot_hash/" + role, workspace=2 * row_bytes + NPY_HEADER_BYTES_UPPER)
        finite = _finite(array)
        self.checkpoint("array_finite_diagnostic", {"role": role, "finite": finite,
                                                    "shape": list(array.shape), "dtype": str(array.dtype)})
        if not finite:
            raise FloatingPointError(f"nonfinite snapshot array: {role}")
        digest = _sha(array)
        reference = self.interned.get(digest)
        if reference is None:
            projected = admit_snapshot_bytes(self.upper_bytes, int(array.nbytes), self.limit)
            _gate(self.gate, "snapshot_export/" + role,
                  workspace=2 * int(array.nbytes) + NPY_HEADER_BYTES_UPPER,
                  borrowed_numeric_bytes=int(array.nbytes),
                  projected_archive_member_bytes_upper=projected,
                  archive_payload_limit_bytes=self.limit, numpy_save_copy_allowance=True)
            location = self.save_array(role, array)
            reference = {"name": role, "shape": list(array.shape), "dtype": str(array.dtype),
                         "numeric_bytes": int(array.nbytes), "sha256": digest}
            if location is not None:
                reference["callback_reference"] = _jsonable(location)
            self.upper_bytes, self.numeric_bytes = projected, self.numeric_bytes + int(array.nbytes)
            self.members.append(reference)
            self.interned[digest] = reference
        self.roles[role] = reference
        return reference

    def identity(self):
        return {"members": self.members, "roles": self.roles,
                "unique_member_count": len(self.members), "numeric_bytes": self.numeric_bytes,
                "archive_members_bytes_upper": self.upper_bytes,
                "archive_payload_limit_bytes": self.limit,
                "byte_scope": "uncompressed_primitive_npy_members_upper_not_final_compressed_archive",
                "final_compressed_archive_bytes": None,
                "final_archive_size_and_other_members_owned_by_caller": True,
                "header_allowance_per_member": NPY_HEADER_BYTES_UPPER,
                "hash_recipe": "sha256(repr((shape,str(dtype)))+C_order_bytes), streamed by row",
                "compression_ratio_assumed": False}


def _checked_indices(values, bound, name):
    import numpy as np
    value = np.asarray(values)
    if value.ndim != 1 or value.dtype.kind not in "iu":
        raise ValueError(f"{name} must contain wide integer indices")
    if value.size and (int(value.min()) < 0 or int(value.max()) >= bound
                       or int(value.max()) > np.iinfo(np.int32).max):
        raise OverflowError(f"{name} fails native/int32 admission before narrowing")
    if len(np.unique(value)) != len(value):
        raise ValueError(f"{name} repeats")
    return value


def _save_native_maps(bundle, system, snapshot, gate):
    import numpy as np
    mpc = bundle["setup"]["floquets"][6].mpc
    coefficients, offsets = mpc.coefficients()
    for name, array in (("slaves", mpc.slaves), ("masters", mpc.masters.array),
                        ("coefficients", coefficients), ("offsets", offsets)):
        snapshot.array("native/mpc/" + name, array)
    constraints = system.trace_constraints
    originals = np.asarray(system.owned_trace_original_dofs)
    nnz = sum(len(constraints.expansion_by_original[int(row)][0]) for row in originals)
    _gate(gate, "native_trace_expansion", (len(originals) + 1 + nnz) * 8 + nnz * 16,
          (len(originals) + nnz) * 64, actual_expansion_nnz=nnz,
          actual_maximum_expansion_width=max((len(constraints.expansion_by_original[int(row)][0])
                                              for row in originals), default=0))
    ptr, ids, data = [0], [], []
    for row in originals:
        columns, values = constraints.expansion_by_original[int(row)]
        _checked_indices(columns, system.active_rows, "actual trace expansion")
        if len(columns) != len(values):
            raise ValueError("actual trace expansion dimensions differ")
        ids.extend(map(int, columns)); data.extend(values); ptr.append(len(ids))
    for role, array in (("trace_original", originals),
                        ("active_original", constraints.owned_active_original_dofs),
                        ("expansion_indptr", np.asarray(ptr, dtype=np.int64)),
                        ("expansion_indices", np.asarray(ids, dtype=np.int64)),
                        ("expansion_data", np.asarray(data, dtype=np.complex128))):
        snapshot.array("native/" + role, array)
    interiors = np.concatenate([cell.interior_original_dofs for cell in system.cell_recovery_maps])
    _checked_indices(interiors, system.full_rows, "complete cell interiors")
    active = _checked_indices(constraints.owned_active_original_dofs, system.full_rows,
                              "complete independent traces")
    slaves = _checked_indices(mpc.slaves, system.full_rows, "actual MPC slaves")
    if (len(interiors) != P6_INVENTORY["interior_rows"] or len(active) != system.active_rows
            or len(np.intersect1d(interiors, active))
            or len(np.intersect1d(slaves, np.r_[interiors, active]))
            or len(interiors) + len(active) + len(slaves) != system.full_rows):
        raise ValueError("actual interiors/trace/slaves do not partition every native row")
    snapshot.array("native/interior_original", interiors)
    return interiors, slaves


def _action_capacity(system, carrier, gate):
    """Count actual factory supports, including stored zero coefficients."""
    import numpy as np
    _gate(gate, "port_support_metadata", system.full_rows * 4 + 80 * 532,
          system.full_rows * 8, before_port_factory=True)
    row_owner = np.full(system.full_rows, -1, dtype=np.int32)
    for index, cell in enumerate(system.cell_recovery_maps):
        row_owner[cell.interior_original_dofs] = index
    support = np.zeros((80, 532), dtype=bool)
    interior_entries = trace_entries = 0
    for port, entry in enumerate(carrier.entries):
        for row_name, value_name in (("coupling_rows", "coupling_values"),
                                     ("projection_rows", "projection_values")):
            rows = _checked_indices(getattr(entry, row_name), system.full_rows, row_name)
            values = getattr(entry, value_name)
            if len(rows) != len(values) or not _finite(values):
                raise ValueError("actual carrier support is nonfinite or inconsistent")
            owners = row_owner[rows]
            local = owners[owners >= 0]
            support[local, port] = True
            interior_entries += len(local)
            trace_entries += len(rows) - len(local)
    counts = np.count_nonzero(support, axis=1)
    count_sum, count_max = int(counts.sum()), int(counts.max())
    # Factory staging Bi/Di, owned Bi/Di/XiB, owned Bt/Dt/Bhat/Dhat,
    # and conservative three copies of port indices at construction.
    per_action_payload = count_sum * (16 * (5 * 450 + 4 * 432) + 3 * 4)
    # Original/active direct dictionaries plus temporary direct-term copies.
    direct_payload_and_temporary = trace_entries * 8 * (4 + 16)
    return {"actual_cell_port_counts": counts.tolist(), "actual_cell_port_count_sum": count_sum,
            "actual_maximum_cell_ports": count_max, "actual_interior_carrier_entries": interior_entries,
            "actual_trace_carrier_entries": trace_entries,
            "two_actions_carrier_payload_bytes_upper": 2 * per_action_payload + 2 * direct_payload_and_temporary,
            "factory_workspace_bytes_upper": 2 * interior_entries * 224 + count_max**2 * 16
                                               + (3 * 450 + 4 * 432) * count_max * 16,
            "stored_zero_coefficients_included": True,
            "named_capacity_is_not_measured_RSS": True}


def _export_original_tensors(bundle, compiled, system, snapshot, gate):
    """Original inherited FFCx tabulation/orientation, one raw class at a time."""
    import numpy as np
    from .hcurl_assembly_time_condensation import (
        _cell_tag_array, _cell_integral_kernels, _canonical_axis_aligned_coordinates,
        _tabulate_raw_tensor_class, _orient_cell_tensor,
    )
    space = bundle["setup"]["spaces"][6]
    mesh, element = space.mesh, space.element
    tags = _cell_tag_array(bundle["setup"]["mesh_data"].cell_tags, 80)
    kernels = _cell_integral_kernels(compiled, sum_duplicate_cell_integrals=True)
    mesh.topology.create_entity_permutations()
    permutations = mesh.topology.get_cell_permutation_info()
    groups, cells = {}, []
    for index, cell in enumerate(system.cell_recovery_maps):
        coordinates, widths = _canonical_axis_aligned_coordinates(
            mesh, index, tolerance=GEOMETRY_TOLERANCE, preserve_exact_geometry=True)
        raw_key = (int(tags[index]), *widths)
        class_key = (*raw_key, int(permutations[index]))
        if class_key != cell.class_key:
            raise ValueError("actual tensor class differs from condensation cell class")
        group = groups.setdefault(raw_key, {"coordinates": coordinates, "classes": {}})
        if not np.array_equal(group["coordinates"], coordinates):
            raise ValueError("actual raw class geometry differs")
        group["classes"].setdefault(class_key, []).append(index)
        cells.append({"cell_index": index, "class_key": _jsonable(class_key),
                      "raw_key": _jsonable(raw_key), "cell_info": int(permutations[index])})
    _gate(gate, "original_tensor_export_class_admission", workspace=3 * 882**2 * 16,
          raw_class_count=len(groups), oriented_class_count=sum(len(g["classes"]) for g in groups.values()),
          simultaneous_raw_tensor_count=1, simultaneous_oriented_tensor_count=1,
          no_global_FE_matrix=True, no_new_FFI_or_kernel=True)
    originals, classes, orientation_refs, orientation_maps = [], [], {}, {}
    identities = system.build_audit["action_only_complete_tensor_identities"]
    basis = element.basix_element
    native_element = {
        "family": "N1curl", "cell": "hexahedron", "degree": int(basis.degree),
        "dtype": str(np.dtype(basis.dtype)), "map_type": basis.map_type.name,
        "basix_hash": int(basis.hash()),
        "coefficient_matrix_C_sha256": _sha(basis.coefficient_matrix, header=False),
        "local_dimension": int(basis.dim),
        "local_interiors": len(basis.entity_dofs[3][0]),
        "local_traces": int(basis.dim) - len(basis.entity_dofs[3][0]),
    }
    positions = np.asarray(basis.entity_dofs[3][0], dtype=np.int32)
    traces = np.setdiff1d(np.arange(882, dtype=np.int32), positions, assume_unique=True)
    if (basis.family.name != "N1E" or basis.cell_type.name != "hexahedron"
            or native_element["degree"] != 6 or native_element["dtype"] != "float64"
            or native_element["map_type"] != "covariantPiola"
            or native_element["local_dimension"] != 882
            or len(positions) != 450 or len(traces) != 432):
        raise ValueError("actual native p6 element identity or partition differs")
    for raw_index, (raw_key, group) in enumerate(sorted(groups.items())):
        raw = _tabulate_raw_tensor_class(compiled, kernels, group["coordinates"],
                                         tag=int(raw_key[0]), dimension=882)
        raw_ref = snapshot.array(f"original/raw_class/{raw_index}/tensor", raw)
        coordinate_ref = snapshot.array(f"original/raw_class/{raw_index}/coordinates", group["coordinates"])
        originals.append({"raw_key": _jsonable(raw_key), "tensor": raw_ref,
                          "coordinates": coordinate_ref})
        for class_key, cell_indices in sorted(group["classes"].items()):
            index = len(classes)
            oriented = raw.copy()
            _orient_cell_tensor(element, oriented, np.asarray([class_key[-1]], dtype=np.uint32))
            identity = identities[repr(class_key)]
            actual_hashes = {"raw_sha256": _sha(raw, header=False),
                             "oriented_sha256": _sha(oriented, header=False)}
            snapshot.checkpoint("original_tensor_native_identity", {
                "class_key": _jsonable(class_key), "expected": _jsonable(identity),
                "actual": actual_hashes, "native_element": native_element})
            if (actual_hashes["raw_sha256"] != identity["raw_sha256"]
                    or actual_hashes["oriented_sha256"] != identity["oriented_sha256"]):
                raise ValueError("fresh original tensor differs from actual pre-elimination tensor identity")
            cell_info = int(class_key[-1])
            if cell_info not in orientation_refs:
                # T_apply is the existing actual Basix transformation.  Save
                # its exact sparse entries, with no magnitude threshold.
                # The dense witness exists only in this export window.
                from scipy import sparse
                _gate(gate, "actual_Basix_orientation_witness", 882**2 * 16,
                      882**2 * 48, cell_info=cell_info,
                      actual_basis_hash=int(element.basix_element.hash()),
                      dense_witness_transient=True)
                transform = np.eye(882, dtype=np.complex128)
                if hasattr(element, "space_dimension"):
                    element.T_apply(transform.ravel(), np.asarray([cell_info], dtype=np.uint32), 882)
                else:
                    element.T_apply(transform.ravel(), 882, cell_info)
                transform_csr = sparse.csr_matrix(transform)
                orientation_refs[cell_info] = {
                    "representation": "actual_Basix_T_apply_CSR",
                    "shape": [882, 882], "cell_info": cell_info,
                    "basis_hash": int(element.basix_element.hash()),
                    "indptr": snapshot.array(f"original/orientation/{cell_info}/indptr", transform_csr.indptr),
                    "indices": snapshot.array(f"original/orientation/{cell_info}/indices", transform_csr.indices),
                    "data": snapshot.array(f"original/orientation/{cell_info}/data", transform_csr.data),
                    "small_entry_threshold": None,
                }
                orientation_maps[cell_info] = transform_csr
                del transform
            # The prepared native T_apply and a materialized CSR product use
            # different floating-point operation orders. Native bytes bind the
            # original tensor; the complete unthresholded CSR is a numerical
            # witness at the existing algebra limit, including every block.
            transform_csr = orientation_maps[cell_info]
            _gate(gate, "CSR_native_orientation_equivalence", 2 * 882**2 * 16,
                  4 * 882**2 * 16, class_index=index, cell_info=cell_info,
                  cached_sparse_orientation_bytes=sum(
                      value.data.nbytes + value.indices.nbytes + value.indptr.nbytes
                      for value in orientation_maps.values()),
                  native_raw_and_oriented_already_resident=True,
                  all_four_partition_blocks=True, numerical_limit=ALGEBRA_LIMIT)
            reconstructed = np.asarray(transform_csr @ raw)
            reconstructed = np.asarray(transform_csr @ reconstructed.T).T
            orientation_metrics = {}
            for label, rows, columns in (("full", None, None),
                                         ("ii", positions, positions),
                                         ("it", positions, traces),
                                         ("ti", traces, positions),
                                         ("tt", traces, traces)):
                reference = oriented if rows is None else oriented[np.ix_(rows, columns)]
                candidate = reconstructed if rows is None else reconstructed[np.ix_(rows, columns)]
                _compare(snapshot.checkpoint, orientation_metrics, label,
                         candidate, reference, ALGEBRA_LIMIT)
            del reconstructed
            original_ref = {"representation": "native_Basix_row_transpose_row_v2",
                            "recipe": "DOLFINx.T_apply_C_order_then_T_apply_transpose_C_order; no conjugation",
                            "raw_tensor": raw_ref, "orientation": orientation_refs[cell_info],
                            "native_element": native_element,
                            "CSR_native_equivalence_metrics": orientation_metrics,
                            "shape": [882, 882], "dtype": "complex128",
                            "C_order_bytes_sha256": identity["oriented_sha256"]}
            caches = {"S_V": system.retained_local_schur_by_class[class_key],
                      "recovery": system.interior_from_trace_by_class[class_key],
                      "trace_rhs_projection": system.trace_from_interior_rhs_by_class[class_key],
                      "LU": system.interior_lu_by_class[class_key][0],
                      "pivots": system.interior_lu_by_class[class_key][1]}
            refs = {name: snapshot.array(f"cache/class/{index}/" + name, value)
                    for name, value in caches.items()}
            classes.append({"class_index": index, "class_key": _jsonable(class_key),
                            "raw_tensor": raw_ref, "original_tensor": original_ref,
                            "cache_arrays": refs, "cell_indices": cell_indices,
                            "saved_pivot_solve_requirement": "admit_private_writable_int32_copy_before_solve"})
            for cell_index in cell_indices:
                cells[cell_index]["class_index"] = index
            del oriented
        del raw
    snapshot.array("original/interior_positions", positions)
    snapshot.array("original/trace_positions", traces)
    return {"raw_classes": originals, "classes": classes, "cells": cells,
            "raw_class_count": len(originals), "oriented_class_count": len(classes),
            "complete_form_signature": compiled.module.ffi.string(compiled.ufcx_form.signature).decode("ascii"),
            "original_helper_source": "_tabulate_raw_tensor_class + _orient_cell_tensor",
            "geometry_tolerance": GEOMETRY_TOLERANCE,
            "geometry_tolerance_matches_condensation_builder": True,
            "pre_elimination_tensor_identities": _jsonable(identities),
            "oriented_full_tensor_exported": False,
            "orientation_proof": "exact native operation-order raw/oriented hash; complete CSR numerical witness",
            "original_tensor_checker_recipe": "native row/transpose/row T_apply; verify original C-byte hash; separately compare unthresholded CSR full/ii/it/ti/tt at 1e-12",
            "no_new_factorization_in_export": True}


def _export_carrier(carrier, compact, snapshot):
    entries = tuple(carrier.entries)
    ports = []
    for index, entry in enumerate(entries):
        arrays = {name: snapshot.array(f"carrier/port/{index}/" + name, getattr(entry, name))
                  for name in ("coupling_rows", "coupling_values", "projection_rows", "projection_values")}
        ports.append({"port_index": index, "mode_key": _jsonable(entry.mode_key),
                      "normalization_h": _jsonable(complex(entry.normalization_h)),
                      "mode_identity": _jsonable(entry.mode_identity), "arrays": arrays})
    cells = []
    for index, cell in enumerate(compact._cells):
        arrays = {name: snapshot.array(f"cell/{index}/" + name, getattr(cell, name))
                  for name in ("original_interiors", "original_trace", "ports", "Bi", "Bt", "Di", "Dt",
                               "XiB", "Bhat", "Dhat")}
        if cell.Hlocal is not None:
            if cell.Hlocal.size and (cell.Hlocal != 0).any():
                raise NotImplementedError("fresh component does not admit nonzero Hlocal")
            arrays["Hlocal"] = snapshot.array(f"cell/{index}/Hlocal", cell.Hlocal)
        cells.append({"cell_index": index, "class_key": _jsonable(cell.class_key),
                      "zero_port_cell": len(cell.ports) == 0, "Hlocal_is_None": cell.Hlocal is None,
                      "arrays": arrays})
    return {"ports": ports, "cells": cells, "ordered_mode_keys": [_jsonable(e.mode_key) for e in entries],
            "carrier_global_rows": carrier.global_rows,
            "carrier_ownership_range": list(carrier.ownership_range),
            "carrier_slave_rows": snapshot.array("carrier/slave_rows", carrier.slave_rows),
            "assembly_context_sha256": carrier.assembly_context_sha256,
            "assembly_mode_manifest_sha256": carrier.mode_manifest_sha256,
            "physical_generator_manifest_sha256": carrier.physical_generator_manifest_sha256}


def _live_apply(bundle, values, *, volume=False):
    import numpy as np
    from petsc4py import PETSc
    source = PETSc.Vec().createSeq(len(values), comm=PETSc.COMM_SELF)
    target = None
    try:
        source.array[:] = values
        if volume:
            target = bundle["volume_action"].apply(source)
        else:
            target = source.duplicate()
            bundle["physical_action"].apply(source, target)
        return np.asarray(target.array, dtype=np.complex128).copy()
    finally:
        # FullspaceSplitVolumeAction.apply returns its owned reusable output;
        # only the explicit physical-action destination is owned here.
        if target is not None and not volume:
            target.destroy()
        source.destroy()


def _actual_expansion(bundle, storage):
    from dolfinx import fem
    field = fem.Function(bundle["setup"]["spaces"][6])
    field.x.array[:] = storage
    field.x.scatter_forward()
    mpc = bundle["setup"]["floquets"][6].mpc
    mpc.homogenize(field)
    mpc.backsubstitution(field)
    field.x.scatter_forward()
    return field.x.array.copy()


def _metric(checkpoint, metrics, name, error, scale, limit):
    import numpy as np
    # A norm can underflow for a nonzero vector (e.g. 1e-300).  Exact-zero
    # arithmetic semantics therefore inspect components before taking a norm.
    nonzero_at_zero_scale = float(scale) == 0 and bool(np.any(np.asarray(error) != 0))
    record = metric_record(np.linalg.norm(error), scale, limit,
                           nonzero_error_at_zero_scale=nonzero_at_zero_scale)
    checkpoint("metric_finite_diagnostic", {"name": name, **record})
    metrics[name] = record
    if not record["passed"]:
        raise FloatingPointError(f"fresh p6 component metric failed: {name}")


def _compare(checkpoint, metrics, name, actual, reference, limit=ACTION_RECOVERY_LIMIT):
    import numpy as np
    if actual.shape != reference.shape or not _finite(actual) or not _finite(reference):
        checkpoint("metric_finite_diagnostic", {"name": name, "finite": False, "passed": False})
        raise FloatingPointError(f"invalid compared arrays: {name}")
    _metric(checkpoint, metrics, name, actual - reference, float(np.linalg.norm(reference)), limit)


def _residual_packet(bundle, action, reduced, rhs, port_rhs, snapshot, label,
                     checkpoint, metrics, *, manufactured):
    import numpy as np
    field = action.recover_storage(reduced, full_rhs=rhs)
    alpha = reduced[action.condensed.active_rows:]
    volume = _live_apply(bundle, field, volume=True)
    native = _live_apply(bundle, field)
    ba = action.apply_B_full(alpha)
    dx = action.apply_D_full(field)
    hp_alpha = action._original_port_block.apply(alpha)
    hp_g = action.original_hp_solve(port_rhs)
    effective = rhs - action.apply_B_full(hp_g)
    fe_residual = rhs - volume - ba
    port_residual = port_rhs + dx - hp_alpha
    native_residual = effective - native
    derived = fe_residual - action.apply_B_full(action.original_hp_solve(port_residual))
    expected_native = volume + action.apply_B_full(action.original_hp_solve(dx))
    reduced_rhs, reduced_action = action.reduce_rhs(rhs, port_rhs=port_rhs, rhs_is_mpc_dual=True), action.apply(reduced)
    reduced_residual = reduced_rhs - reduced_action
    packet = {"storage": field, "full_rhs": rhs, "port_rhs": port_rhs, "reduced": reduced,
              "live_volume_action": volume, "live_original_action": native, "B_alpha": ba, "D_field": dx,
              "H_alpha": hp_alpha, "effective_native_rhs": effective, "augmented_fe_residual": fe_residual,
              "augmented_port_residual": port_residual, "original_native_residual": native_residual,
              "derived_native_residual": derived, "reduced_rhs": reduced_rhs,
              "reduced_action": reduced_action, "reduced_residual": reduced_residual}
    refs = {name: snapshot.array(label + "/" + name, value) for name, value in packet.items()}
    _compare(checkpoint, metrics, label + "/live_original_action_identity", native, expected_native, ALGEBRA_LIMIT)
    _metric(checkpoint, metrics, label + "/native_augmented_residual_identity", native_residual - derived,
            float(np.linalg.norm(effective) + np.linalg.norm(native) + np.linalg.norm(fe_residual)
                  + np.linalg.norm(derived)), ALGEBRA_LIMIT)
    scales = {"fe": float(np.linalg.norm(rhs) + np.linalg.norm(volume) + np.linalg.norm(ba)),
              "port": float(np.linalg.norm(port_rhs) + np.linalg.norm(dx) + np.linalg.norm(hp_alpha)),
              "native": float(np.linalg.norm(effective)),
              "reduced": float(np.linalg.norm(reduced_rhs) + np.linalg.norm(reduced_action))}
    diagnostics = {"manufactured_consistent_state": manufactured, "global_solve_performed": False,
                   "arbitrary_retained_state_is_solved": False, "operation_scales": scales,
                   "original_residual_norm": float(np.linalg.norm(native_residual)),
                   "augmented_fe_residual_norm": float(np.linalg.norm(fe_residual)),
                   "augmented_port_residual_norm": float(np.linalg.norm(port_residual))}
    checkpoint("original_residual_diagnostic", {"label": label, **diagnostics})
    if manufactured:
        for name, error, scale, limit in (("original_native", native_residual, scales["native"], ORIGINAL_RESIDUAL_LIMIT),
                                          ("augmented_fe", fe_residual, scales["fe"], ORIGINAL_RESIDUAL_LIMIT),
                                          ("augmented_port", port_residual, scales["port"], ORIGINAL_RESIDUAL_LIMIT),
                                          ("reduced", reduced_residual, scales["reduced"], ACTION_RECOVERY_LIMIT)):
            _metric(checkpoint, metrics, label + "/" + name, error, scale, limit)
    return field, {"arrays": refs, **diagnostics}


def _material_control(compact, snapshot, gate, checkpoint, metrics):
    """Independent artificial couplings on one actual p6 cache; physical data stay borrowed."""
    import numpy as np
    from scipy.linalg import lu_solve
    from .p6_cell_condensed_action import _factored_matrix_action
    cell = compact._cells[0]
    ni = len(cell.original_interiors)
    _gate(gate, "material_negative_control", 12 * ni * 16, 4 * ni**2 * 16,
          actual_p6_cell_index=0, physical_PDE_or_carrier_modified=False,
          original_owned_live_pivots_unchanged=True)
    rows = np.arange(1, ni + 1, dtype=np.float64)
    target = np.column_stack((np.cos(.17 * rows) + 1j * np.sin(.31 * rows),
                              np.cos(.23 * rows) + 1j * np.sin(.41 * rows))) / np.sqrt(ni)
    bi = _factored_matrix_action(cell.interior_lu, target)
    xib = lu_solve(cell.interior_lu, bi)
    di = np.vstack((np.sin(.29 * rows) + 1j * np.cos(.37 * rows),
                    np.sin(.43 * rows) + 1j * np.cos(.19 * rows))) / np.sqrt(ni)
    raw_norm = float(np.linalg.norm(di @ xib))
    checkpoint("material_control_finite_diagnostic", {"finite": math.isfinite(raw_norm), "raw_correction_norm": raw_norm if math.isfinite(raw_norm) else None})
    if not math.isfinite(raw_norm) or raw_norm <= 0:
        raise FloatingPointError("material control correction is not finite and nonzero")
    di *= .5 / raw_norm
    original_h = np.diag(np.asarray([1.0 + .2j, 1.4 - .3j], dtype=np.complex128))
    correction = di @ xib
    hhat = original_h + correction
    alpha = np.asarray([.4 + .7j, -.2 + .9j], dtype=np.complex128)
    dense = hhat @ alpha
    factored = original_h @ alpha + di @ (xib @ alpha)
    omitted, wrong_sign = original_h @ alpha, (original_h - correction) @ alpha
    wrong_conjugation = original_h @ alpha + di.conjugate() @ (xib @ alpha)
    rhs = np.asarray([.8 - .3j, -.5 + .6j], dtype=np.complex128)
    hp_solve, wrong_hhat_solve = np.linalg.solve(original_h, rhs), np.linalg.solve(hhat, rhs)
    arrays = {"target_XiB": target, "Bi": bi, "Di": di, "XiB": xib, "H_original": original_h,
              "correction": correction, "Hhat_dense": hhat, "alpha": alpha,
              "dense_action": dense, "factored_action": factored, "omitted_action": omitted,
              "wrong_sign_action": wrong_sign, "wrong_conjugation_action": wrong_conjugation,
              "port_rhs": rhs, "original_H_solve": hp_solve, "wrong_Hhat_solve": wrong_hhat_solve}
    refs = {name: snapshot.array("material_control/" + name, value) for name, value in arrays.items()}
    _compare(checkpoint, metrics, "material_control/dense_factored", factored, dense, ALGEBRA_LIMIT)
    _compare(checkpoint, metrics, "material_control/actual_p6_LU_solve", xib, target, ACTION_RECOVERY_LIMIT)
    negatives = {}
    for name, wrong, reference in (("omitted_correction", omitted, dense), ("wrong_sign", wrong_sign, dense),
                                    ("wrong_conjugation", wrong_conjugation, dense),
                                    ("Hhat_substituted_for_original_H", wrong_hhat_solve, hp_solve)):
        diagnostic = metric_record(np.linalg.norm(wrong - reference), np.linalg.norm(reference), 1.0e-3)
        checkpoint("material_negative_diagnostic", {"name": name, **diagnostic})
        if not diagnostic["finite"] or diagnostic["relative"] is None or diagnostic["relative"] < 1.0e-3:
            raise FloatingPointError(f"material negative control lacks separation: {name}")
        negatives[name] = {**diagnostic, "rejected_by_action_gate": True, "minimum_separation": 1.0e-3}
    return {"label": "artificial_non_Hermitian_material_control_on_actual_p6_cell_cache",
            "physical_case": False, "physical_PDE_data_modified": False, "cell_index": 0,
            "class_key": _jsonable(cell.class_key), "interior_dimension": ni,
            "correction_norm": float(np.linalg.norm(correction)), "arrays": refs,
            "negative_controls": negatives}


def run_fresh_p6_component(action_bundle: Mapping[str, Any], *,
                           allocation_gate: Callable, save_array: Callable,
                           checkpoint: Callable, archive_payload_limit_bytes: int,
                           jit_options: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Borrow one live p6 bundle and produce complete current component evidence.

    save_array(name, array) must synchronously export the array; its optional
    return value is retained as a JSON-safe callback reference.  checkpoint(stage,
    facts) must synchronously persist diagnostics, including failure diagnostics.
    allocation_gate(stage, facts) must reject before allocation when the measured
    whole-process-tree envelope/reserve is insufficient.  Archive member budget
    is numeric bytes plus a conservative 4096-byte .npy header per unique member.
    The runner must admit and archive its own logs/JIT files/receipts separately.
    """
    require_callbacks(allocation_gate, save_array, checkpoint, archive_payload_limit_bytes)
    import numpy as np
    from dolfinx import fem
    from petsc4py import PETSc
    from .dtn_boundary_plane_qualification import validate_fresh_c1_bundle_profile, carrier_numeric_identity
    from .hcurl_assembly_time_condensation import build_unconstrained_assembly_time_condensation
    from .p6_cell_condensed_action import build_p6_cell_condensed_action_from_carrier
    from .retained_port_block_layout import LEGACY_PORT_LAYOUT, RESEARCH_PORT_LAYOUT
    from .original_port_blocks import DiagonalOriginalPortBlock
    from .y_orbit_condensed_adapter import _boundary_support

    profile = validate_fresh_c1_bundle_profile(action_bundle)
    setup, degree = action_bundle["setup"], int(action_bundle["degree"])
    space, floquet = setup["spaces"][degree], setup["floquets"][degree]
    carrier = action_bundle["dtn_action"].carrier
    if (degree != 6 or set(setup["spaces"]) != {6} or space.mesh.comm.size != 1
            or np.dtype(PETSc.ScalarType) != np.dtype(np.complex128)
            or np.dtype(PETSc.IntType) != np.dtype(np.int32)
            or action_bundle.get("dtn_phase_gauge") != "boundary_plane"):
        raise ValueError("fresh p6 component requires exact same80 MPI1 complex128/int32 degree-only boundary-plane bundle")
    carrier_before = carrier_numeric_identity(carrier)
    snapshot = _Snapshot(save_array, allocation_gate, checkpoint, archive_payload_limit_bytes)
    system = dense = compact = compiled = None
    pre_elimination_tensor_identities = None
    metrics = {}
    try:
        groups, row_groups, support = _boundary_support(action_bundle)
        checkpoint("complete_combined_form_compile_admission", {"cold_JIT_must_already_be_supervised": True})
        _gate(allocation_gate, "complete_combined_form_compile", workspace=64 * 1024**2,
              estimate_status="declared_allowance_not_compiler_peak_bound",
              caller_process_tree_cap_required=True)
        compiled = fem.form(action_bundle["volume_action"].bilinear_form,
                            **({"jit_options": dict(jit_options)} if jit_options is not None else {}))
        system = build_unconstrained_assembly_time_condensation(
            compiled, space, setup["mesh_data"].cell_tags, mpc=floquet.mpc,
            appended_global_rows=532, appended_support_owned_cell_groups=groups,
            appended_support_group_by_row=row_groups, sum_duplicate_cell_integrals=True,
            strict_local_checks=True, materialize_global_matrix=False,
            retain_local_schur_for_matrix_free=True, geometry_tolerance=GEOMETRY_TOLERANCE,
            preserve_exact_geometry=True,
            share_identity_cache=True, allocation_gate=allocation_gate)
        # Retain the exact original authority before any array export or later
        # control can fail. This is the actual inherited pre-elimination hash
        # inventory, never a hash derived from the CSR witness.
        pre_elimination_tensor_identities = _jsonable(
            system.build_audit["action_only_complete_tensor_identities"])
        checkpoint("pre_elimination_tensor_identities", {
            "identities": pre_elimination_tensor_identities,
            "hash_scope": "actual_raw_and_native_oriented_C_order_bytes_before_local_elimination"})
        actual = {"degree": degree, "cell_count": len(system.cell_recovery_maps),
                  "local_dimension": int(space.element.space_dimension),
                  "local_interiors": len(space.element.basix_element.entity_dofs[3][0]),
                  "local_traces": int(space.element.space_dimension) - len(space.element.basix_element.entity_dofs[3][0]),
                  "storage_rows": system.full_rows, "independent_rows": system.active_rows + system.active_interior_rows,
                  "interior_rows": system.active_interior_rows, "active_trace_rows": system.active_rows,
                  "port_rows": system.appended_rows}
        if actual != P6_INVENTORY or system.matrix is not None:
            raise ValueError("actual complete p6 inventory differs from fresh same80 contract")
        checkpoint("actual_condensed_inventory", actual)
        live_pivot_hashes = {key: _sha(factor[1]) for key, factor in system.interior_lu_by_class.items()}
        capacity = _action_capacity(system, carrier, allocation_gate)
        # Two action objects copy their additional port arrays but borrow all
        # volume caches.  Account for both, their factory maps and dense squares.
        square_bytes = 532**2 * 16
        carrier_bytes = int(carrier.retained_numeric_bytes)
        _gate(allocation_gate, "dense_and_compact_same_system_actions",
              capacity["two_actions_carrier_payload_bytes_upper"] + 2 * square_bytes + 532 * 16,
              capacity["factory_workspace_bytes_upper"] + 4 * square_bytes + 4 * carrier_bytes,
              actual_capacity=capacity,
              same_condensed_system=True, same_carrier=True, default_dense_and_explicit_research=True)
        dense = build_p6_cell_condensed_action_from_carrier(system, carrier, owns_condensed=False)
        original = DiagonalOriginalPortBlock.from_carrier(carrier.entries)
        compact = build_p6_cell_condensed_action_from_carrier(
            system, carrier, owns_condensed=False, port_coupling_mode="cached",
            port_block_layout=RESEARCH_PORT_LAYOUT, original_port_block=original)
        if (dense.port_block_layout != LEGACY_PORT_LAYOUT or dense.condensed is not compact.condensed
                or len(dense._cells) != 80 or len(compact._cells) != 80
                or any(left.class_key != right.class_key or left.interior_lu is not right.interior_lu
                       or left.S_V is not right.S_V or left.recovery is not right.recovery
                       or left.trace_from_interior is not right.trace_from_interior
                       for left, right in zip(dense._cells, compact._cells, strict=True))
                or compact._H_p is not None or compact._Hhat is not None):
            raise ValueError("same-system default-dense/compact representation ownership contract failed")
        _gate(allocation_gate, "vector_controls", 32 * system.full_rows * 16 + 16 * compact.reduced_size * 16,
              12 * system.full_rows * 16, full_native_rows_including_slaves=True)
        interiors, slaves = _save_native_maps(action_bundle, system, snapshot, allocation_gate)
        original_sources = _export_original_tensors(action_bundle, compiled, system, snapshot, allocation_gate)
        compiled = None
        carrier_sources = _export_carrier(carrier, compact, snapshot)
        snapshot.array("port/H_original_diagonal", original.diagonal)
        snapshot.array("port/H_original_dense", dense._H_p)
        snapshot.array("port/Hhat_legacy_dense", dense._Hhat)
        alpha = np.cos(.13 * np.arange(1, 533)) + 1j * np.sin(.37 * np.arange(1, 533))
        alpha = np.asarray(alpha, dtype=np.complex128)
        snapshot.array("controls/port_probe", alpha)
        h_apply, hp_dense_solve, hp_compact_solve = dense._H_p @ alpha, dense.original_hp_solve(alpha), compact.original_hp_solve(alpha)
        for name, value in (("H_apply_dense", h_apply), ("H_apply_compact", original.apply(alpha)),
                            ("H_solve_dense", hp_dense_solve), ("H_solve_compact", hp_compact_solve)):
            snapshot.array("controls/" + name, value)
        _compare(checkpoint, metrics, "original_H_apply", original.apply(alpha), h_apply, ALGEBRA_LIMIT)
        _compare(checkpoint, metrics, "original_H_solve", hp_compact_solve, hp_dense_solve, ALGEBRA_LIMIT)
        _gate(allocation_gate, "independent_Hhat_small_oracle", square_bytes, 2 * square_bytes,
              full_p6_matrix=False, port_square_only=True)
        independent_hhat = dense._H_p.copy()
        support_records = []
        for index, cell in enumerate(compact._cells):
            correction = cell.Di @ cell.XiB
            independent_hhat[np.ix_(cell.ports, cell.ports)] += correction
            support_records.append({"cell_index": index, "port_count": len(cell.ports),
                                    "Bi_nonzero": int(np.count_nonzero(cell.Bi)),
                                    "Di_nonzero": int(np.count_nonzero(cell.Di)),
                                    "Bi_norm": float(np.linalg.norm(cell.Bi)), "Di_norm": float(np.linalg.norm(cell.Di)),
                                    "XiB_norm": float(np.linalg.norm(cell.XiB)),
                                    "correction_norm": float(np.linalg.norm(correction))})
            del correction
        snapshot.array("port/Hhat_independent_dense", independent_hhat)
        hhat_dense, hhat_factored = independent_hhat @ alpha, compact._condensed_port_block.apply(alpha)
        snapshot.array("controls/Hhat_dense_action", hhat_dense)
        snapshot.array("controls/Hhat_factored_action", hhat_factored)
        _compare(checkpoint, metrics, "Hhat_legacy_independent_dense", dense._Hhat, independent_hhat, ALGEBRA_LIMIT)
        _compare(checkpoint, metrics, "Hhat_dense_factored_action", hhat_factored, hhat_dense)
        physical_correction_norm = float(np.linalg.norm(independent_hhat - dense._H_p))
        del independent_hhat
        material = _material_control(compact, snapshot, allocation_gate, checkpoint, metrics)
        n = compact.reduced_size
        reduced = np.asarray(np.cos(.19 * np.arange(1, n + 1)) + 1j * np.sin(.43 * np.arange(1, n + 1)), dtype=np.complex128)
        reduced[-532:] = alpha
        full_rhs = np.asarray(np.cos(.31 * np.arange(1, system.full_rows + 1)) + 1j * np.sin(.47 * np.arange(1, system.full_rows + 1)), dtype=np.complex128)
        full_rhs[slaves] = 0
        port_rhs = np.asarray(np.cos(.23 * np.arange(1, 533)) + 1j * np.sin(.41 * np.arange(1, 533)), dtype=np.complex128)
        if np.any(full_rhs[interiors] == 0) or np.any(port_rhs == 0):
            raise ValueError("arbitrary control requires every interior and every port load nonzero")
        dense_action, compact_action = dense.apply(reduced), compact.apply(reduced)
        dense_rhs, compact_rhs = dense.reduce_rhs(full_rhs, port_rhs=port_rhs, rhs_is_mpc_dual=True), compact.reduce_rhs(full_rhs, port_rhs=port_rhs, rhs_is_mpc_dual=True)
        dense_recovery = dense.recover_storage(reduced, full_rhs=full_rhs)
        compact_recovery = compact.recover_storage(reduced, full_rhs=full_rhs)
        for name, value in (("reduced_probe", reduced), ("arbitrary_full_rhs", full_rhs), ("arbitrary_port_rhs", port_rhs),
                            ("reduced_action_dense", dense_action), ("reduced_action_compact", compact_action),
                            ("reduced_rhs_dense", dense_rhs), ("reduced_rhs_compact", compact_rhs),
                            ("recovery_dense", dense_recovery), ("recovery_compact", compact_recovery)):
            snapshot.array("controls/" + name, value)
        _compare(checkpoint, metrics, "complete_reduced_action", compact_action, dense_action)
        _compare(checkpoint, metrics, "arbitrary_full_interior_port_RHS_reduction", compact_rhs, dense_rhs)
        _compare(checkpoint, metrics, "arbitrary_full_recovery", compact_recovery, dense_recovery)
        if np.any(dense_recovery[slaves] != 0) or np.any(compact_recovery[slaves] != 0):
            raise ValueError("native recovery must preserve exact zero slave storage")
        expanded = compact.recover_storage(reduced, full_rhs=full_rhs, expand_trace=True)
        actual_expanded = _actual_expansion(action_bundle, compact_recovery)
        snapshot.array("controls/recovery_expanded_from_condensation", expanded)
        snapshot.array("controls/recovery_expanded_from_actual_MPC", actual_expanded)
        _compare(checkpoint, metrics, "actual_MPC_expanded_physical_field", expanded, actual_expanded)
        _, arbitrary_packet = _residual_packet(action_bundle, compact, reduced, full_rhs, port_rhs,
                                                snapshot, "arbitrary", checkpoint, metrics, manufactured=False)
        # Manufacture f,g from the original live V,B,D,H and a chosen full
        # native state.  It is consistent by construction; no global solve is
        # claimed.  Every interior is loaded, independently of recovery caches.
        manufactured = compact.inject_trace_port(reduced)
        manufactured[interiors] = full_rhs[interiors]
        manufactured_volume = _live_apply(action_bundle, manufactured, volume=True)
        manufactured_rhs = manufactured_volume + compact.apply_B_full(alpha)
        manufactured_g = original.apply(alpha) - compact.apply_D_full(manufactured)
        if np.any(manufactured_rhs[slaves] != 0) or np.any(manufactured_rhs[interiors] == 0):
            raise ValueError("manufactured original native RHS must have zero slaves and all interiors loaded")
        snapshot.array("manufactured/chosen_native_storage", manufactured)
        snapshot.array("manufactured/chosen_actual_MPC_field", _actual_expansion(action_bundle, manufactured))
        recovered, manufactured_packet = _residual_packet(action_bundle, compact, reduced, manufactured_rhs,
                                                            manufactured_g, snapshot, "manufactured", checkpoint,
                                                            metrics, manufactured=True)
        _compare(checkpoint, metrics, "manufactured_recovery_original_state", recovered, manufactured)
        _compare(checkpoint, metrics, "manufactured_dense_compact_reduction",
                 compact.reduce_rhs(manufactured_rhs, port_rhs=manufactured_g, rhs_is_mpc_dual=True),
                 dense.reduce_rhs(manufactured_rhs, port_rhs=manufactured_g, rhs_is_mpc_dual=True))
        _compare(checkpoint, metrics, "manufactured_dense_compact_recovery", recovered,
                 dense.recover_storage(reduced, full_rhs=manufactured_rhs))
        carrier_after = carrier_numeric_identity(carrier)
        if carrier_after != carrier_before:
            raise ValueError("actual same-live physical carrier changed during component controls")
        if any(_sha(system.interior_lu_by_class[key][1]) != digest
               for key, digest in live_pivot_hashes.items()):
            raise ValueError("actual owned live LU pivots changed during component controls")
        receipt = {"schema": SCHEMA, "source_status": SOURCE_STATUS,
                   "status": "worker_component_controls_passed_independent_checker_pending",
                   "independent_checker_pass": False, "durable_archive_verified": False,
                   "actual_inventory": actual, "fresh_profile": _jsonable(profile),
                   "boundary_support": _jsonable(support), "condensation_audit": _jsonable(system.build_audit),
                   "port_factory_capacity": capacity,
                   "carrier_before": _jsonable(carrier_before), "carrier_after": _jsonable(carrier_after),
                   "actual_owned_live_pivots_unchanged": True,
                   "dense_layout": LEGACY_PORT_LAYOUT, "compact_layout": RESEARCH_PORT_LAYOUT,
                   "same_system_and_carrier": True, "same_live_qualification_owned_by_caller": True,
                   "dense_buffers": dict(dense.buffer_inventory), "compact_buffers": dict(compact.buffer_inventory),
                   "compact_representation_identity": _jsonable(compact.port_block_representation_identity),
                   "original_sources": original_sources, "carrier_sources": carrier_sources,
                   "physical_correction_support": support_records,
                   "physical_correction_norm": physical_correction_norm,
                   "physical_correction_materiality_claim": False,
                   "separate_material_control": material,
                   "arbitrary_state": arbitrary_packet, "manufactured_state": manufactured_packet,
                   "metrics": metrics, "limits": {"action_recovery": ACTION_RECOVERY_LIMIT,
                                                   "original_residual": ORIGINAL_RESIDUAL_LIMIT,
                                                   "pure_algebra": ALGEBRA_LIMIT,
                                                   "zero_scale_absolute": ZERO_SCALE_ABSOLUTE_LIMIT,
                                                   "absolute_units": "native coefficient/action norm in this component"},
                   "snapshot": snapshot.identity(), "global_p6_matrix_created": False,
                   "global_p6_factor_created": False, "quotient_constructed": False,
                   "physical_outputs_reported": False,
                   "ownership": "caller owns bundle/setup; actions borrow same system; system destroyed once"}
        json.dumps(receipt, allow_nan=False)
        checkpoint("component_worker_receipt", receipt)
        return receipt
    except BaseException as error:
        budget_stop = isinstance(error, SnapshotBudgetExceeded)
        checkpoint("component_control_failure", {"schema": SCHEMA,
                    "status": "controlled_stop" if budget_stop else "failed",
                    "stop_reason": "uncompressed_raw_member_budget_exceeded" if budget_stop else None,
                    "exception_type": type(error).__name__, "message": str(error),
                    "pre_elimination_tensor_identities": pre_elimination_tensor_identities,
                    "completed_metrics": metrics, "snapshot": snapshot.identity(),
                    "independent_checker_pass": False, "durable_archive_verified": False})
        raise
    finally:
        # Neither action owns the borrowed system.  The caller's original
        # physical bundle/setup are deliberately never destroyed here.
        if compact is not None:
            compact.destroy()
        if dense is not None:
            dense.destroy()
        if system is not None:
            system.destroy()


__all__ = ("run_fresh_p6_component", "require_callbacks", "admit_snapshot_bytes",
           "metric_record", "SnapshotBudgetExceeded", "P6_INVENTORY", "SCHEMA")
