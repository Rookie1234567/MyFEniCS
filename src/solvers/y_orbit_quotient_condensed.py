"""Opt-in exact action-only condensation for the bounded two-y-cell p4 audit.

Geometry, explicit MPC phases, physical inventory and gauge context are
owned/qualified by the caller. This adapter owns only inherited condensation
and port action, with no assembled S, global factor or new elimination math.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

import numpy as np

SCHEMA = "task40extra.two-cell-p4-condensed-provider.v1"
PHYSICAL_MANIFEST = "4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951"


def _gate(gate, label, payload=0, workspace=0, **facts):
    if not callable(gate):
        raise ValueError("fresh measured whole-tree allocation gate required")
    gate(label, {"matrix_payload_bytes": int(payload), "workspace_bytes": int(workspace),
                 "allocation_semantics": "additional_objects_to_current_resident_RSS", **facts})


def _indices(values, upper, int_type):
    """Validate original wide integer input before any PETSc narrowing."""
    raw = np.asarray(values)
    if (raw.ndim != 1 or raw.dtype.kind not in "iu" or upper <= 0
            or upper - 1 > int(np.iinfo(np.dtype(int_type)).max)
            or (raw.size and (int(raw.min()) < 0 or int(raw.max()) >= upper))
            or len(np.unique(raw)) != len(raw)):
        raise ValueError("invalid unique native/original index inventory before narrowing")
    result = raw.astype(int_type, copy=True)
    result.setflags(write=False)
    return result


def _sector_inventory(action_bundle, global_mode_inventory, global_mode_indices, qbase, int_type):
    if type(qbase) is not int or qbase not in (0, 1):
        raise ValueError("two-cell Ny4 profile requires qbase0 or1")
    if len(global_mode_inventory) != 3:
        raise ValueError("complete global modes/rows/hash inventory required")
    modes, rows, digest = global_mode_inventory
    if (len(modes) != 532 or len(rows) != 532 or str(digest) != PHYSICAL_MANIFEST
            or action_bundle.get("mode_sha256") != str(digest)):
        raise ValueError("complete frozen532 physical generator identity differs")
    indices = _indices(global_mode_indices, len(modes), int_type)
    expected = np.asarray([i for i, mode in enumerate(modes) if int(mode.n) % 2 == qbase])
    if not np.array_equal(indices, expected):
        raise ValueError("sector must preserve every compatible original alias in original order")
    local_modes = tuple(action_bundle["modes"])
    carrier = action_bundle["dtn_action"].carrier
    if (len(indices) != (228 if qbase == 0 else 304) or len(local_modes) != len(indices)
            or len(carrier.entries) != len(indices)
            or getattr(carrier, "physical_generator_manifest_sha256", None) != digest
            or getattr(carrier, "phase_gauge", None) != "boundary_plane"):
        raise ValueError("actual local carrier/physical identity/sector count mismatch")
    for local, original in enumerate(indices):
        mode = modes[int(original)]
        entry = carrier.entries[local]
        key = (local, str(mode.side), int(mode.m), int(mode.n), str(mode.polarization))
        if (local_modes[local] is not mode or tuple(entry.mode_key) != key
                or int(entry.mode_identity["mode_index"]) != local
                or (int(mode.n) - qbase) % 2):
            raise ValueError("local carrier does not preserve selected original mode objects/keys")
    return indices


@dataclass
class QuotientCondensedBundle:
    """Own system/action; borrow immutable caller physical bundle and setup.

    All row inventories refer to original local storage. No canonical R/F/Q
    is created here. Contribution views belong to action/system and survive
    only until the iterator advances or this bundle is destroyed.
    """
    action_bundle: dict[str, Any]
    system: Any
    action: Any
    trace_original_rows: np.ndarray
    interior_original_rows: np.ndarray
    independent_original_rows: np.ndarray
    original_to_independent: np.ndarray
    global_mode_indices: np.ndarray
    qbase: int
    audit: dict[str, Any]
    destroyed: bool = False

    @property
    def original_to_active(self):
        self._live()
        return MappingProxyType(self.system.trace_constraints.original_to_active)

    def _live(self):
        if self.destroyed:
            raise RuntimeError("quotient condensation bundle destroyed")

    def iter_contributions(self, *, allocation_gate):
        self._live()
        return self.action.iter_reduced_contributions(allocation_gate=allocation_gate)

    def reduce_rhs(self, full_rhs, *, port_rhs=None, rhs_is_mpc_dual=False):
        self._live()
        return self.action.reduce_rhs(full_rhs, port_rhs=port_rhs, rhs_is_mpc_dual=rhs_is_mpc_dual)

    def recover_storage(self, reduced_solution, *, full_rhs=None, expand_trace=False):
        self._live()
        return self.action.recover_storage(reduced_solution, full_rhs=full_rhs, expand_trace=expand_trace)

    def evaluate_native_residual(self, reduced_solution, full_rhs, native_apply, **kwargs):
        self._live()
        return self.action.evaluate_native_residual(reduced_solution, full_rhs, native_apply, **kwargs)

    def destroy(self):
        if self.destroyed:
            return
        try:
            # action borrows the system; both are owned once here.
            self.action.destroy()
        finally:
            try:
                self.system.destroy()
            finally:
                self.action = self.system = None
                self.destroyed = True
        # Caller still owns physical action/setup. No borrowed Vec is destroyed.


def build_quotient_condensed(action_bundle, *, global_mode_inventory,
                             global_mode_indices, qbase, allocation_gate):
    """Construct only the exact local action/cache, with all sector aliases.

    This frozen profile is degree4,40cells,8940storage/7936independent,
    4320interiors/3616trace,228or304ports. Numeric factorization is restricted
    to inherited per-cell interior LU; global/q factor callbacks are absent.
    No standalone quotient phase/raw-boundary qualification is claimed here.
    """
    from dolfinx import fem
    from petsc4py import PETSc
    from .hcurl_assembly_time_condensation import build_unconstrained_assembly_time_condensation
    from .p6_cell_condensed_action import build_p6_cell_condensed_action_from_carrier
    from .y_orbit_condensed_adapter import _boundary_support, _integer_capacity, _mpc_expansion_width

    setup = action_bundle["setup"]
    space, floquet = setup["spaces"][4], setup["floquets"][4]
    carrier = action_bundle["dtn_action"].carrier
    full_rows = int(space.dofmap.index_map.size_local)
    cell_count = int(space.mesh.topology.index_map(3).size_local)
    ni = len(space.element.basix_element.entity_dofs[3][0])
    nc = int(space.element.space_dimension)
    if (type(action_bundle["degree"]) is not int or action_bundle["degree"] != 4
            or set(setup["spaces"]) != {4} or set(setup["floquets"]) != {4}
            or space.mesh.comm.size != 1 or np.dtype(PETSc.ScalarType) != np.dtype(np.complex128)
            or int(space.element.basix_element.degree) != 4 or (nc, nc-ni) != (300, 192)
            or ni != 108 or cell_count != 40 or full_rows != 8940
            or int(carrier.global_rows) != full_rows or tuple(carrier.ownership_range) != (0, full_rows)):
        raise ValueError("require exact serial degree-only40cell p4 action profile")
    _integer_capacity(full_rows, None, PETSc.IntType)
    _integer_capacity(3616 + len(carrier.entries), None, PETSc.IntType)
    index_bytes = np.dtype(PETSc.IntType).itemsize
    _gate(allocation_gate, "quotient_original_inventory", 8 * full_rows * index_bytes,
          8 * full_rows * index_bytes)
    indices = _sector_inventory(action_bundle, global_mode_inventory, global_mode_indices,
                                qbase, PETSc.IntType)
    slaves = _indices(floquet.mpc.slaves, full_rows, PETSc.IntType)
    independent = np.setdiff1d(np.arange(full_rows, dtype=PETSc.IntType), slaves)
    if len(independent) != 7936:
        raise ValueError("actual finalized MPC independent count differs from7936")
    expansion_audit = _mpc_expansion_width(floquet.mpc, full_rows)
    groups, row_groups, support = _boundary_support(action_bundle)
    by_side = {side: sum(str(entry.mode_identity["side"]) == side for entry in carrier.entries)
               for side in ("bottom", "top")}
    counts = [by_side[side] for side, cells in zip(("bottom", "top"), groups, strict=True)
              for _cell in cells]
    # Existing cached action may retain Bi/Di/XiB, zero Bt/Dt and cached
    # Bhat/Dhat/Hlocal. Count these even when actual interior support is tiny.
    port_arrays = sum(((3*ni + 4*(nc-ni))*count + count*count)*16 + count*index_bytes
                      for count in counts)
    dense_h = len(indices)**2 * 16
    carrier_bytes = int(carrier.retained_numeric_bytes)
    carrier_entries = sum(len(e.coupling_rows) + len(e.projection_rows) for e in carrier.entries)
    system = action = None
    try:
        _gate(allocation_gate, "quotient_compile_complete_volume", workspace=64*1024**2,
              estimate_status="declared_FFCx_allowance_not_memory_guarantee")
        compiled = fem.form(action_bundle["volume_action"].bilinear_form)
        try:
            system = build_unconstrained_assembly_time_condensation(
                compiled, space, setup["mesh_data"].cell_tags, mpc=floquet.mpc,
                appended_global_rows=len(indices), appended_support_owned_cell_groups=groups,
                appended_support_group_by_row=row_groups, sum_duplicate_cell_integrals=True,
                strict_local_checks=True, preserve_exact_geometry=True, share_identity_cache=True,
                materialize_global_matrix=False, retain_local_schur_for_matrix_free=True,
                allocation_gate=allocation_gate)
        finally:
            del compiled
        if (system.matrix is not None or system.full_rows != full_rows
                or system.active_rows != 3616 or system.active_interior_rows != 4320
                or system.appended_rows != len(indices)
                or system.retained_local_schur_by_class is None):
            raise ValueError("complete action-only trace/interior/port count mismatch")
        _gate(allocation_gate, "quotient_complete_port_action", port_arrays + 4*carrier_bytes + 3*dense_h,
              2*carrier_bytes + carrier_entries*224 + 2*dense_h,
              actual_interior_support=support["carrier_nonzero_interior_cell_count"],
              estimate_status="declared_named_array_and_Python_allowance_not_peak_RSS")
        action = build_p6_cell_condensed_action_from_carrier(
            system, carrier, owns_condensed=False, port_coupling_mode="cached")
        _gate(allocation_gate, "quotient_native_row_partition", 4*full_rows*index_bytes,
              8*full_rows*index_bytes)
        trace = _indices(system.trace_constraints.owned_active_original_dofs, full_rows, PETSc.IntType)
        interiors = _indices(np.concatenate([c.interior_original_dofs for c in system.cell_recovery_maps]),
                             full_rows, PETSc.IntType)
        if (len(interiors) != 4320 or len(trace) != 3616 or np.intersect1d(trace, interiors).size
                or not np.array_equal(np.sort(np.concatenate((trace, interiors))), independent)
                or any(system.trace_constraints.original_to_active[int(row)] != i
                       for i, row in enumerate(trace))):
            raise ValueError("native trace/interior/independent row partition is not exact")
        original_to_independent = np.full(full_rows, -1, dtype=PETSc.IntType)
        original_to_independent[independent] = np.arange(len(independent), dtype=PETSc.IntType)
        for array in (independent, original_to_independent):
            array.setflags(write=False)
        audit = {"schema": SCHEMA, "degree": 4, "qbase": qbase,
                 "full_storage_rows": full_rows, "independent_rows": len(independent),
                 "interior_rows": len(interiors), "active_trace_rows": len(trace),
                 "sector_port_rows": len(indices), "global_physical_mode_count": 532,
                 "physical_generator_manifest_sha256": global_mode_inventory[2],
                 "assembly_mode_manifest_sha256": carrier.mode_manifest_sha256,
                 "assembly_context_sha256": carrier.assembly_context_sha256,
                 "MPC_expansion": expansion_audit, "boundary_support": support,
                 "condensation": system.build_audit, "complete_port_action": dict(action.audit),
                 "complete_port_buffer_inventory": dict(action.buffer_inventory),
                 "port_allocation_named_upper_bytes": port_arrays + 4*carrier_bytes + 3*dense_h,
                 "original_H_from_local_area_carrier": True, "Hhat_diagonal_assumed": False,
                 "interior_port_zero_assumed": False, "owns_action_and_system": True,
                 "borrows_physical_bundle_and_setup": True, "no_materialized_S": True,
                 "no_global_or_q_factor": True, "qualification": "NOT_RUN_STAGED_COMPONENT"}
        return QuotientCondensedBundle(action_bundle, system, action, trace, interiors,
                                       independent, original_to_independent, indices, qbase, audit)
    except BaseException:
        try:
            if action is not None:
                action.destroy()
        finally:
            if system is not None:
                system.destroy()
        raise


__all__ = ("QuotientCondensedBundle", "build_quotient_condensed")
