"""Opt-in glue for exact cell condensation in the bounded full-3D y pilot.

The caller owns the original degree-only action and all-q factor. This module
reuses the Task39 cell kernels, complete ports and recovery. It adds only the
exact restriction of the existing full-FE y map and a p2 oracle bridge. There
is no dense global p4 matrix, private PETSc FFI, factor builder or PDE runner.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any

import numpy as np
from scipy import sparse

SCHEMA = "task40extra.y-orbit-condensed-adapter.v2"


def _gate(gate, name, payload, workspace=0, **facts):
    if not callable(gate):
        raise ValueError("a fresh measured whole-tree allocation gate is required")
    gate(name, {"matrix_payload_bytes": int(payload), "workspace_bytes": int(workspace),
                "allocation_semantics": "additional_objects_to_current_resident_RSS", **facts})


def _payload(matrix):
    return int(matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes)


def _csr_payload_upper(rows, nnz, int_type, scalar_type=np.complex128):
    index_bytes = np.dtype(int_type).itemsize
    return int((int(rows) + 1) * index_bytes + int(nnz) *
               (index_bytes + np.dtype(scalar_type).itemsize))


def _port_payload_upper(interior_dimension, port_counts, int_type):
    """Bi/Di/XiB plus actual-width port index arrays and local index scratch."""
    scalar_bytes, index_bytes = np.dtype(np.complex128).itemsize, np.dtype(int_type).itemsize
    ni, counts = int(interior_dimension), tuple(map(int, port_counts))
    retained = sum(3 * ni * count * scalar_bytes + count * index_bytes for count in counts)
    maximum = max(counts, default=0)
    scratch = (4 * maximum**2 * scalar_bytes + 3 * ni * maximum * scalar_bytes
               + maximum * index_bytes)
    return int(retained), int(scratch)


def _integer_capacity(rows, nnz, int_type):
    """Reject dimension/CSR-offset overflow before calling a narrowing API."""
    limit = int(np.iinfo(np.dtype(int_type)).max)
    if not 0 < int(rows) <= limit or (nnz is not None and not 0 <= int(nnz) <= limit):
        raise OverflowError("original/CSR size exceeds PETSc.IntType before narrowing")


def _native_indices(values, full_rows, int_type):
    """Check original wide integer values, then explicitly narrow if valid."""
    _integer_capacity(full_rows, None, int_type)
    raw = np.asarray(values)
    if raw.ndim != 1 or raw.dtype.kind not in "iu":
        raise ValueError("native independent positions must be a one-dimensional integer array")
    if raw.size and (int(raw.min()) < 0 or int(raw.max()) >= int(full_rows)
                     or int(raw.max()) > int(np.iinfo(np.dtype(int_type)).max)):
        raise OverflowError("native index exceeds original/PETSc range before narrowing")
    if len(np.unique(raw)) != len(raw):
        raise ValueError("native independent indices repeat")
    return raw.astype(int_type, copy=False)


def _storage(system, values, layout):
    from petsc4py import PETSc
    values = np.asarray(values, dtype=np.complex128)
    independent = _native_indices(layout.independent, system.full_rows, PETSc.IntType)
    if (layout.full_rows != system.full_rows or values.shape != independent.shape
            or independent.ndim != 1 or len(np.unique(independent)) != len(independent)
            or np.any(independent < 0) or np.any(independent >= system.full_rows)
            or not np.isfinite(values).all()):
        raise ValueError("invalid complete native independent vector")
    result = PETSc.Vec().createSeq(system.full_rows, comm=PETSc.COMM_SELF)
    result.set(0)
    result.array[independent] = values
    return result


@dataclass
class CondensedReference:
    """Own inherited condensation/recovery; borrow physical action and factor."""
    action_bundle: dict[str, Any]
    system: Any
    port_terms: dict[int, Any]
    inverse: Any
    audit: dict[str, Any]
    destroyed: bool = False

    @property
    def setup(self):
        return self.action_bundle["setup"]

    @property
    def config(self):
        return self.action_bundle["cfg"]

    @property
    def space(self):
        return self.setup["spaces"][int(self.action_bundle["degree"])]

    @property
    def floquet(self):
        return self.setup["floquets"][int(self.action_bundle["degree"])]

    @property
    def carrier(self):
        return self.action_bundle["dtn_action"].carrier

    def scipy_csr(self, *, allocation_gate):
        """One public CSR materialization, no extra explicit ndarray copies.

        Treat the returned CSR as read-only and keep this reference alive until
        the consumer releases it. getValuesCSR may copy in petsc4py; the gate
        accounts for that plus possible SciPy index conversion, never assumes
        zero-copy PETSc backing. No persistent CSR cache is retained here.
        """
        if self.destroyed:
            raise RuntimeError("condensed reference destroyed")
        from petsc4py import PETSc
        rows = int(self.system.matrix.getSize()[0])
        nnz = int(self.system.matrix.getInfo()["nz_used"])
        _integer_capacity(rows, nnz, PETSc.IntType)
        _integer_capacity(int(self.system.matrix.getSize()[1]), nnz, PETSc.IntType)
        payload = _csr_payload_upper(rows, nnz, PETSc.IntType, PETSc.ScalarType)
        _gate(allocation_gate, "condensed_CSR_export", payload, 2 * payload)
        indptr, indices, data = self.system.matrix.getValuesCSR()
        if (len(indptr) != rows + 1 or int(indptr[-1]) != nnz
                or np.any(indptr < 0) or np.any(np.diff(indptr) < 0)
                or (indices.size and (int(indices.min()) < 0 or int(indices.max()) >= rows))):
            raise ValueError("public CSR integer inventory is inconsistent")
        if not np.isfinite(data).all():
            raise ValueError("nonfinite condensed CSR")
        return sparse.csr_matrix((data, indices, indptr), shape=self.system.matrix.getSize(), copy=False)

    def reduce_independent(self, rhs, full_layout):
        """Complete native FE RHS, including every cell-interior load."""
        storage = _storage(self.system, rhs, full_layout)
        reduced = None
        try:
            # The exact routine used by inherited apply(), not a new Schur RHS.
            reduced = self.inverse._reduce_storage_rhs(storage)
            return reduced.array.copy()
        finally:
            if reduced is not None:
                reduced.destroy()
            storage.destroy()

    def apply_independent(self, rhs, full_layout):
        if self.destroyed or self.inverse.factor is None:
            raise RuntimeError("an admitted real factor.solve_repeated must be attached")
        storage = _storage(self.system, rhs, full_layout)
        solution = None
        try:
            solution = self.inverse.apply(storage)
            if np.any(solution.array[np.asarray(self.floquet.mpc.slaves)] != 0):
                raise ValueError("complete recovery violates native slave-zero storage")
            return solution.array[full_layout.independent].copy()
        finally:
            if solution is not None:
                solution.destroy()
            storage.destroy()

    def apply_storage(self, source, target):
        self.action_bundle["physical_action"].apply(source, target)

    def destroy(self):
        if not self.destroyed:
            # owns_condensed=True clears the inherited numeric caches and matrix;
            # owns_factor=False leaves the caller's retained all-q factors alone.
            self.inverse.destroy()
            self.port_terms.clear()
            self.destroyed = True


def _boundary_support(action):
    """Actual carrier support audit and safe tagged-slab preallocation."""
    from petsc4py import PETSc
    setup, cfg = action["setup"], action["cfg"]
    space = setup["spaces"][int(action["degree"])]
    mesh = space.mesh
    owned = int(mesh.topology.index_map(3).size_local)
    mesh.topology.create_connectivity(2, 3)
    connectivity = mesh.topology.connectivity(2, 3)
    groups, rows = [], []
    for tag in (cfg.tags.z_min, cfg.tags.z_max):
        cells = sorted({int(cell) for facet in setup["mesh_data"].facet_tags.find(tag)
                        for cell in connectivity.links(int(facet)) if int(cell) < owned})
        if not cells:
            raise ValueError("actual tagged boundary has no owned support cells")
        groups.append(np.asarray(cells, dtype=np.int32))
        rows.append({int(row) for cell in cells for row in space.dofmap.cell_dofs(cell)})
    interior = np.asarray(space.element.basix_element.entity_dofs[3][0], dtype=np.int32)
    owner = {int(row): cell for cell in range(owned)
             for row in np.asarray(space.dofmap.cell_dofs(cell))[interior]}
    row_groups, interior_ports = [], {}
    for port, entry in enumerate(action["dtn_action"].carrier.entries):
        group = {"bottom": 0, "top": 1}.get(str(entry.mode_identity["side"]))
        if group is None:
            raise ValueError("unsupported actual carrier side")
        row_groups.append(group)
        for support, values in ((entry.coupling_rows, entry.coupling_values),
                                (entry.projection_rows, entry.projection_values)):
            if any(int(row) not in rows[group] for row in support):
                raise ValueError("carrier escapes audited boundary slab; recompute admission")
            for row, value in zip(support, values, strict=True):
                cell = owner.get(int(row))
                if cell is not None and value != 0:
                    interior_ports.setdefault(cell, set()).add(port)
    retained, scratch = _port_payload_upper(len(interior),
        (len(ports) for ports in interior_ports.values()), PETSc.IntType)
    # Bi/Di/XiB plus conservative local Hhat products; Python dictionaries and
    # allocator overhead remain measured by the enclosing whole-tree watchdog.
    return tuple(groups), tuple(row_groups), {
        "actual_boundary_support_cells": [group.tolist() for group in groups],
        "actual_boundary_support_full_row_counts": list(map(len, rows)),
        "carrier_nonzero_interior_cell_count": len(interior_ports),
        "Bi_Di_XiB_retained_bytes_upper": retained,
        "port_local_scratch_bytes_upper": scratch,
        "port_index_itemsize_bytes": np.dtype(PETSc.IntType).itemsize,
        "local_DOLFINx_cell_index_dtype": "int32_not_PETSc_global_index_assumption",
        "interior_port_zero_assumed": False,
    }


def build_condensed_reference(action_bundle, *, allocation_gate):
    from dolfinx import fem
    from petsc4py import PETSc
    from src.solvers.hcurl_assembly_time_condensation import build_unconstrained_assembly_time_condensation
    from src.solvers.p4_cell_condensed_inverse import P4CellCondensedInverse, assemble_condensed_ports
    degree = int(action_bundle["degree"])
    setup = action_bundle["setup"]
    space, floquet = setup["spaces"][degree], setup["floquets"][degree]
    if (degree not in (2, 4) or space.mesh.comm.size != 1 or set(setup["spaces"]) != {degree}
            or np.dtype(PETSc.ScalarType) != np.dtype(np.complex128)):
        raise ValueError("require an admitted serial degree-only p2/p4 setup")
    _integer_capacity(int(space.dofmap.index_map.size_local), None, PETSc.IntType)
    _integer_capacity(int(space.mesh.topology.index_map(3).size_local), None, PETSc.IntType)
    groups, row_groups, support = _boundary_support(action_bundle)
    system = inverse = None
    try:
        _gate(allocation_gate, "compile_complete_curl_plus_mass", 0, 64 * 1024**2,
              estimate_status="declared_compiler_allowance_not_memory_bound")
        compiled = fem.form(action_bundle["volume_action"].bilinear_form)
        system = build_unconstrained_assembly_time_condensation(
            compiled, space, setup["mesh_data"].cell_tags, mpc=floquet.mpc,
            appended_global_rows=len(action_bundle["dtn_action"].carrier.entries),
            appended_support_owned_cell_groups=groups, appended_support_group_by_row=row_groups,
            dense_appended_block=True, sum_duplicate_cell_integrals=True, strict_local_checks=True,
            defer_final_assembly=True, preserve_exact_geometry=True, share_identity_cache=True,
            allocation_gate=allocation_gate,
        )
        del compiled
        _gate(allocation_gate, "complete_port_terms", support["Bi_Di_XiB_retained_bytes_upper"],
              support["port_local_scratch_bytes_upper"])
        terms = assemble_condensed_ports(system, action_bundle["dtn_action"].carrier)
        inverse = P4CellCondensedInverse(system, None, port_terms=terms,
                                        owns_condensed=True, owns_factor=False)
        audit = {"schema": SCHEMA, "degree": degree, "condensation": system.build_audit,
                 "boundary_support": support, "complete_interiors_and_port_formulas": True,
                 "borrowed_original_action": True, "borrowed_factor": True,
                 "full_p6_constructed": False, "global_factor_created_here": False}
        return CondensedReference(action_bundle, system, terms, inverse, audit)
    except BaseException:
        if inverse is not None:
            inverse.destroy()
        elif system is not None:
            system.destroy()
        raise


def trace_layout_coordinates(full_layout, system, *, allocation_gate):
    """Restrict existing build_y_orbit_layout; do not build another orbit map."""
    full = np.asarray(full_layout.independent, dtype=np.int64)
    active = np.asarray(system.trace_constraints.owned_active_original_dofs, dtype=np.int64)
    interior = np.concatenate([cell.interior_original_dofs for cell in system.cell_recovery_maps])
    if (full_layout.full_rows != system.full_rows or full.ndim != 1 or active.ndim != 1
            or np.any(full < 0) or np.any(full >= system.full_rows)
            or np.any(active < 0) or np.any(active >= system.full_rows)
            or len(np.unique(active)) != system.active_rows or len(np.unique(full)) != len(full)
            or len(np.unique(interior)) != system.active_interior_rows
            or len(interior) != system.active_interior_rows
            or len(np.intersect1d(active, interior))
            or not np.array_equal(np.sort(np.concatenate((active, interior))), np.sort(full))):
        raise ValueError("complete native trace/interior/full-FE partition disagrees")
    row_of = np.full(system.full_rows, -1, dtype=np.int64)
    row_of[full] = np.arange(len(full))
    positions = row_of[active]
    ny, width = int(full_layout.ny), int(full_layout.width)
    if len(np.unique(positions)) != system.active_rows or np.any(positions < 0) or system.active_rows % ny:
        raise ValueError("native trace positions/orbit count invalid")
    upper = 4 * _payload(full_layout.r) + 2 * _payload(full_layout.fourier)
    _gate(allocation_gate, "exact_trace_map_restriction", upper, upper)
    restricted = full_layout.r[positions, :].tocsr()
    columns = np.unique(restricted.indices)
    slots = columns[columns < width]
    if (len(slots) != system.active_rows // ny
            or not np.array_equal(columns, np.concatenate([j * width + slots for j in range(ny)]))):
        raise ValueError("trace canonical slots are not complete identical y orbits")
    outside = np.setdiff1d(np.arange(len(full)), positions)
    canonical_outside = np.setdiff1d(np.arange(len(full)), columns)
    # Exact structural closure, no small coefficient deletion or abs(orientation)=1.
    if (full_layout.r[outside, :][:, columns].nnz
            or full_layout.r_inverse[columns, :][:, outside].nnz
            or full_layout.native_translation[positions, :][:, outside].nnz
            or full_layout.native_translation[outside, :][:, positions].nnz
            or full_layout.fourier[columns, :][:, canonical_outside].nnz
            or full_layout.fourier[canonical_outside, :][:, columns].nnz):
        raise ValueError("trace restriction mixes interior and trace coordinates")
    r = restricted[:, columns].tocsr()
    del restricted
    ri = full_layout.r_inverse[columns, :][:, positions].tocsr()
    f = full_layout.fourier[columns, :][:, columns].tocsr()
    t = full_layout.native_translation[positions, :][:, positions].tocsr()
    identity = sparse.eye(system.active_rows, dtype=np.complex128, format="csr")
    scale = np.sqrt(system.active_rows)
    defects = {"left_inverse_relative": float(sparse.linalg.norm(ri @ r - identity) / scale),
               "right_inverse_relative": float(sparse.linalg.norm(r @ ri - identity) / scale),
               "fourier_unitarity_relative": float(sparse.linalg.norm(f.conj().T @ f - identity) / scale)}
    if any(not np.isfinite(value) or value > 1e-12 for value in defects.values()):
        raise ValueError("restricted native/canonical/DFT inverse gate failed")
    return {"R_t": r, "R_t_inverse": ri, "F_t": f, "native_trace_translation": t,
            "trace_width": system.active_rows // ny, "ny": ny,
            "trace_original_rows": active,
            "full_independent_trace_positions": positions,
            "full_canonical_trace_positions": columns,
            "audit": {**defects, "complete_trace_rows": system.active_rows,
                      "complete_interior_rows": len(interior), "partition_exact": True,
                      "structural_trace_interior_closure": True,
                      "primal_map": "Q_t=R_t F_t", "dual_map": "Q_t^H",
                      "primal_inverse": "F_t^H R_t_inverse", "R_unitary_assumed": False}}


def audit_original_solution(reference, full_layout, rhs, solution, *, auxiliary_ports=None, return_vectors=False):
    """Full recovered ORIGINAL action plus inherited augmented residual identity."""
    from src.solvers.fullspace_p4_blr import augmented_residual_identity
    source = _storage(reference.system, solution, full_layout)
    right = _storage(reference.system, rhs, full_layout)
    target = source.duplicate()
    try:
        reference.apply_storage(source, target)
        native = right.array - target.array
        ports = (reference.action_bundle["dtn_action"].recover_auxiliary(source).copy()
                 if auxiliary_ports is None else np.asarray(auxiliary_ports, dtype=np.complex128))
        if ports.shape != (len(reference.carrier.entries),) or not np.isfinite(ports).all():
            raise ValueError("invalid recovered auxiliary solution")
        projected = np.asarray([np.dot(e.projection_values, source.array[e.projection_rows])
                                for e in reference.carrier.entries])
        h = np.asarray([e.normalization_h for e in reference.carrier.entries])
        coupling = np.zeros(reference.system.full_rows, complex)
        for value, entry in zip(ports, reference.carrier.entries, strict=True):
            np.add.at(coupling, entry.coupling_rows, value * entry.coupling_values)
        # Borrowed reusable output Vec owned by the original volume action;
        # consume/copy before another apply and never destroy it here.
        volume = reference.action_bundle["volume_action"].apply(source)
        top = right.array - volume.array - coupling
        port_residual = projected - h * ports  # inherited helper expects e_port=Dc-Ha
        identity = augmented_residual_identity(native, top, port_residual, reference.carrier,
                                               rhs_norm=right.norm(), native_action_norm=target.norm())
        scale = max(float(right.norm()), np.finfo(float).tiny)
        packet = {"full_original_true_residual": float(np.linalg.norm(native) / scale),
                "augmented_FE_true_residual": float(np.linalg.norm(top) / scale),
                "augmented_port_closure_relative": float(np.linalg.norm(port_residual) /
                    max(np.linalg.norm(projected), np.finfo(float).tiny)),
                "augmented_residual_identity": identity,
                "full_native_slave_zero": bool(np.all(source.array[np.asarray(reference.floquet.mpc.slaves)] == 0)),
                "original_action_used": True, "condensed_action_used_for_residual": False,
                "degree": int(reference.action_bundle["degree"]), "original_storage_rows": reference.system.full_rows}
        if return_vectors:
            packet["vectors"] = {"rhs_storage": right.array.copy(), "solution_storage": source.array.copy(),
                                 "original_action": target.array.copy(), "volume_action": volume.array.copy(),
                                 "auxiliary_ports": ports.copy(), "projection": projected.copy(),
                                 "normalization_h": h.copy(), "coupling_action": coupling.copy(),
                                 "native_residual": native.copy(), "augmented_FE_residual": top.copy(),
                                 "augmented_port_residual": port_residual.copy()}
        return packet
    finally:
        target.destroy()
        right.destroy()
        source.destroy()


def audit_recovered_translation(reference, full_layout, rhs, solution):
    """Witness A T x = T^{-H} g at full recovered FE level, not trace only."""
    shifted_x = np.asarray(full_layout.native_translation @ solution)
    # T=R shift R^-1. shift is unitary for the admitted real-ky wrap;
    # inverse-H dual transform is R^-H shift R^H, not T applied to a load.
    shifted_rhs = np.asarray(full_layout.r_inverse.conj().T @
                             (full_layout.shift @ (full_layout.r.conj().T @ rhs)))
    packet = audit_original_solution(reference, full_layout, shifted_rhs, shifted_x)
    packet["translation_scope"] = "full_recovered_FE_including_all_interiors_RHS_witness_not_operator_norm"
    packet["dual_translation"] = "T^{-H}=R^{-H} shift R^H"
    return packet


def recovery_numeric_identity(reference):
    """Hash inherited cache/map/port values in place; no persistence framework.

    Length-prefixed UTF-8 JSON label/dtype/shape then C-order bytes. Class
    ordinals follow this builder's insertion order and all cell references
    bind to them. The caller also binds source/form/config/native MPC identity.
    """
    digest = hashlib.sha256()
    arrays = payload = 0

    def add(label, value):
        nonlocal arrays, payload
        array = np.asarray(value)
        if array.dtype.hasobject or (array.dtype.kind in "fc" and not np.isfinite(array).all()):
            raise ValueError("invalid inherited recovery numeric payload")
        header = json.dumps([label, array.dtype.str, list(array.shape)], separators=(",", ":")).encode()
        digest.update(len(header).to_bytes(8, "little")); digest.update(header)
        digest.update(memoryview(np.ascontiguousarray(array)).cast("B"))
        arrays += 1; payload += array.nbytes

    system = reference.system
    class_ids = {key: i for i, key in enumerate(system.interior_lu_by_class)}
    for key, index in class_ids.items():
        lu, pivots = system.interior_lu_by_class[key]
        add(f"class/{index}/LU", lu); add(f"class/{index}/pivots", pivots)
        for name in ("interior_from_trace_by_class", "trace_from_interior_rhs_by_class",
                     "interior_rhs_projection_by_class", "interior_solution_embedding_by_class",
                     "interior_residual_projection_by_class"):
            add(f"class/{index}/{name}", getattr(system, name)[key])
    for i, cell in enumerate(system.cell_recovery_maps):
        add(f"cell/{i}/class", np.asarray([class_ids[cell.class_key]], dtype=np.int64))
        add(f"cell/{i}/interiors", cell.interior_original_dofs)
        add(f"cell/{i}/traces", cell.trace_original_dofs)
        if i in reference.port_terms:
            for name in ("Bi", "Di", "port_indices"):
                add(f"cell/{i}/{name}", getattr(reference.port_terms[i], name))
            add(f"cell/{i}/XiB", reference.inverse._xiB_by_cell[i])
    add("native/active_original", system.trace_constraints.owned_active_original_dofs)
    for row, (indices, coefficients) in sorted(system.trace_constraints.expansion_by_original.items()):
        add(f"native/expansion/{row}/ids", indices)
        add(f"native/expansion/{row}/coefficients", coefficients)
    return {"schema": SCHEMA + ".recovery-identity", "sha256": digest.hexdigest(),
            "array_count": arrays, "hashed_logical_array_bytes": int(payload),
            "logical_bytes_are_not_RSS_shared_arrays_count_per_role": True,
            "protocol": "length_u64_le + compact_UTF8_JSON[label,dtype.str,shape] + C_order_bytes",
            "native_matrix_identity": reference.inverse.matrix_identity,
            "operator_cache_identity": system.build_audit["operator_cache_identity"],
            "cross_run_factor_or_recovery_loader": False}


def coordinate_array_views(coordinates):
    """Borrowed arrays for the caller's existing hash-bound ignored writer.

    This is a coordinate export, not a second recovery serializer or a factor
    persistence/restart format. Complete recovery state is the inherited system.
    """
    for name in ("trace_original_rows", "full_independent_trace_positions", "full_canonical_trace_positions"):
        yield name, coordinates[name]
    for name in ("R_t", "R_t_inverse", "F_t", "native_trace_translation"):
        matrix = coordinates[name]
        for suffix in ("data", "indices", "indptr"):
            yield name + "_" + suffix, getattr(matrix, suffix)


def _mpc_expansion_width(mpc, rows):
    """Measure finalized public MPI1 coefficient/master map, or stop admission."""
    coefficients, offsets = mpc.coefficients()  # raises if not finalized
    coefficients, offsets = np.asarray(coefficients), np.asarray(offsets)
    slaves, masters = np.asarray(mpc.slaves), np.asarray(mpc.masters.array)
    if (offsets.shape != (rows + 1,) or offsets.dtype.kind not in "iu"
            or slaves.dtype.kind not in "iu" or masters.dtype.kind not in "iu"
            or coefficients.ndim != 1 or not np.isfinite(coefficients).all()
            or int(offsets[0]) != 0 or int(offsets[-1]) != len(coefficients)
            or len(masters) != len(coefficients) or np.any(offsets[1:] < offsets[:-1])
            or (slaves.size and (int(slaves.min()) < 0 or int(slaves.max()) >= rows))
            or (masters.size and (int(masters.min()) < 0 or int(masters.max()) >= rows))
            or len(np.unique(slaves)) != len(slaves) or len(np.intersect1d(slaves, masters))):
        raise ValueError("finalized public MPC expansion map cannot qualify sparse admission")
    for slave in slaves:
        start, stop = int(offsets[int(slave)]), int(offsets[int(slave) + 1])
        if stop <= start or not np.array_equal(mpc.masters.links(int(slave)), masters[start:stop]):
            raise ValueError("public MPC slave/master coefficient inventories disagree")
    # Include stored zero-coefficient master links, conservatively. Non-slave
    # rows retain identity width1; no assumption about high-order moments.
    return max(1, max((int(b) - int(a) for a, b in zip(offsets[:-1], offsets[1:], strict=True)), default=0))


def assemble_sparse_p2_volume(action_bundle, full_layout, *, allocation_gate):
    """Public original MPC sparse-volume bridge; no port outer products/factor."""
    from dolfinx import fem
    from petsc4py import PETSc
    import dolfinx_mpc
    if int(action_bundle["degree"]) != 2:
        raise ValueError("full original sparse-volume bridge is p2 qualification only")
    space = action_bundle["setup"]["spaces"][2]
    cells = int(space.mesh.topology.index_map(3).size_local)
    rows = int(space.dofmap.index_map.size_local)
    width = _mpc_expansion_width(action_bundle["setup"]["floquets"][2].mpc, rows)
    nnz_upper = cells * int(space.element.space_dimension)**2 * width**2 + rows
    _integer_capacity(rows, nnz_upper, PETSc.IntType)
    _native_indices(full_layout.independent, rows, PETSc.IntType)
    payload = _csr_payload_upper(rows, nnz_upper, PETSc.IntType, PETSc.ScalarType)
    _gate(allocation_gate, "p2_original_MPC_sparse_bridge", payload, 3 * payload,
          measured_finalized_mpc_expansion_width=width, structural_nnz_upper=nnz_upper,
          petsc_index_itemsize_bytes=np.dtype(PETSc.IntType).itemsize,
          petsc_scalar_itemsize_bytes=np.dtype(PETSc.ScalarType).itemsize,
          graph_bound_includes_mpc_expansion_width_squared=True)
    matrix = dolfinx_mpc.assemble_matrix(fem.form(action_bundle["volume_action"].bilinear_form),
                                      action_bundle["setup"]["floquets"][2].mpc, bcs=[])
    try:
        matrix.assemble()
        indptr, indices, data = matrix.getValuesCSR()
        volume = sparse.csr_matrix((data, indices, indptr), shape=matrix.getSize(), copy=False)
        # The restricted result owns its slice arrays before PETSc destruction.
        return volume[full_layout.independent, :][:, full_layout.independent].tocsr()
    finally:
        matrix.destroy()


def compare_p2_saved_dense(volume, carrier, full_layout, saved_dense, *, allocation_gate, panel_columns=32):
    """Compare EVERY p2 column to a separately hash-validated saved dense oracle.

    saved_dense must be the mmap-loaded frozen A0_original artifact. The caller
    verifies source/ABI/config/native-row identities and all file hashes first.
    Only an N x panel_columns dense work panel is created, never dense p4.
    """
    n = len(full_layout.independent)
    if n != 2048 or saved_dense.shape != (n, n) or volume.shape != (n, n):
        raise ValueError("only the previously qualified 2048-row p2 oracle is admitted")
    if not 1 <= int(panel_columns) <= 32:
        raise ValueError("p2 dense oracle panels must be 1..32 columns")
    _gate(allocation_gate, "p2_saved_oracle_streamed_comparison", 3 * n * int(panel_columns) * np.dtype(np.complex128).itemsize,
          int(saved_dense.nbytes) + 8 * n * np.dtype(np.complex128).itemsize,
          mmap_residency_allowance="all_saved_oracle_pages_may_become_resident")
    row_of = np.full(full_layout.full_rows, -1, dtype=np.int64)
    row_of[full_layout.independent] = np.arange(n)
    entries = []
    for entry in carrier.entries:
        c, d = row_of[entry.coupling_rows], row_of[entry.projection_rows]
        if np.any(c < 0) or np.any(d < 0):
            raise ValueError("carrier contains an eliminated native row")
        entries.append((c, d, entry))
    difference_squared = oracle_squared = 0.0
    for start in range(0, n, int(panel_columns)):
        stop = min(start + int(panel_columns), n)
        current = volume[:, start:stop].toarray()
        for c, d, entry in entries:
            selected = (d >= start) & (d < stop)
            if np.any(selected):
                current[np.ix_(c, d[selected] - start)] += np.outer(
                    entry.coupling_values, entry.projection_values[selected]) / entry.normalization_h
        oracle = np.asarray(saved_dense[:, start:stop])
        if not np.isfinite(current).all() or not np.isfinite(oracle).all():
            raise ValueError("nonfinite p2 oracle/action panel")
        difference_squared += float(np.linalg.norm(current - oracle)**2)
        oracle_squared += float(np.linalg.norm(oracle)**2)
    relative = np.sqrt(difference_squared / max(oracle_squared, np.finfo(float).tiny))
    return {"all_original_columns_compared": n, "matrix_relative_difference": float(relative),
            "limit": 1e-11, "passed": bool(np.isfinite(relative) and relative <= 1e-11),
            "dense_new_global_matrix_created": False, "maximum_panel_columns": int(panel_columns)}
