"""Memory-first p6/h10 foundation objects for the V11 S2 audit.

This module is an audit-only assembly path.  It keeps the high operator
matrix-free, the physical DtN action streaming, and the low positive operator
as one sparse edge matrix.  It deliberately has no HX, nodal, coarse, or
global high-order matrix path.  The only dense numerical object used while
deriving the bounded cell transfer is released before the case is returned;
the retained transfer is three axis-local tensors and its fixed batch scratch.
"""

from __future__ import annotations

from pathlib import Path
import copy
from types import SimpleNamespace
from typing import Any, Callable, Iterable, Mapping

import numpy as np


S2_SCHEMA = "task038.full3d.lor-memory-first.s2-foundation.v1"
S2_DEGREE = 6
S2_H_NM = 10.0
S2_WAVELENGTH_NM = 13.5
S2_REPEAT_COUNT = 10
S2_RESTART_BASIS_COUNT = 21
S2_AUXILIARY_VECTOR_COUNT = 4
S2_RESERVE_VECTOR_COUNT = S2_RESTART_BASIS_COUNT + S2_AUXILIARY_VECTOR_COUNT
S2_COLD_RSS_LIMIT = 1_800_000_000
S2_RETAINED_RSS_LIMIT = 1_550_000_000
S2_REPEAT_GROWTH_LIMIT = 32_000_000
S2_TRANSFER_CELL_CAP = 32
S2_REPEAT_NORM_TOL = 1.0e-13
S2_SETUP_RESOURCE_STAGES = (
    "start",
    "high_mesh_space_mpc",
    "high_actions",
    "low_mesh_space_mpc",
    "low_matrix_transfer_topology_work",
)
S2_APPLY_NAMES = (
    "high_positive",
    "physical_volume_dtn",
    "restrict_high_to_lor",
    "lor_edge_matvec",
    "lift_lor_to_high",
)


def _finite_norm(vector: Any) -> tuple[bool, float]:
    """Return a PETSc global norm without retaining a vector copy."""

    value = float(vector.norm())
    return bool(np.isfinite(value)), value


def allocate_restart20_reserve(
    template: Any,
    *,
    basis_count: int = S2_RESTART_BASIS_COUNT,
    auxiliary_count: int = S2_AUXILIARY_VECTOR_COUNT,
) -> dict[str, Any]:
    """Allocate and touch the fixed restart-20 live vector reserve.

    The reserve is explicitly 21 Krylov vectors plus solution, RHS, residual,
    and action.  A tuple is retained so the test and record can prove that the
    vectors exist; no history of iterations or applications is accumulated.
    """

    basis_count = int(basis_count)
    auxiliary_count = int(auxiliary_count)
    if (basis_count, auxiliary_count) != (
        S2_RESTART_BASIS_COUNT,
        S2_AUXILIARY_VECTOR_COUNT,
    ):
        raise ValueError("S2 reserve counts are frozen at 21 basis + 4 auxiliary")
    vectors = tuple(template.duplicate() for _ in range(basis_count + auxiliary_count))
    for vector in vectors:
        vector.set(0.125 + 0.25j)
    local_entries = int(template.getLocalSize())
    itemsize = int(np.dtype(np.complex128).itemsize)
    return {
        "basis_count": basis_count,
        "auxiliary_vector_count": auxiliary_count,
        "vector_count": len(vectors),
        "touched": True,
        "local_entries_per_vector": local_entries,
        "local_numeric_bytes": int(len(vectors) * local_entries * itemsize),
        "vectors": vectors,
    }


def destroy_restart20_reserve(reserve: Mapping[str, Any]) -> None:
    """Destroy all reserve vectors exactly once."""

    for vector in tuple(reserve.get("vectors", ())):
        vector.destroy()


def run_fixed_apply_ledger(
    operations: Iterable[tuple[str, Callable[[], Any]]],
    *,
    repeats: int = S2_REPEAT_COUNT,
    resource_sample: Callable[[], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run the five fixed operations and retain scalar rows only."""

    operations = tuple(operations)
    if tuple(name for name, _ in operations) != S2_APPLY_NAMES:
        raise ValueError("S2 apply order is frozen")
    repeats = int(repeats)
    if repeats != S2_REPEAT_COUNT:
        raise ValueError("S2 repeat count is frozen at ten")
    rows: list[dict[str, Any]] = []
    for repeat in range(repeats):
        row: dict[str, Any] = {"repeat": int(repeat)}
        for name, operation in operations:
            result = operation()
            if isinstance(result, Mapping):
                finite = bool(result["finite"])
                norm = float(result["norm"])
                digest = str(result["digest"])
            else:
                finite, norm = _finite_norm(result)
                digest = ""
            row[name] = {
                "finite": finite,
                "norm": norm,
                "digest": digest,
            }
        if resource_sample is not None:
            row["resource"] = dict(resource_sample())
        rows.append(row)
    return {
        "operation_names": list(S2_APPLY_NAMES),
        "repeat_count": repeats,
        "rows": rows,
        "retains_vectors": False,
    }


def _space_storage_bytes(space: Any) -> int:
    index_map = space.dofmap.index_map
    entries = int(index_map.size_local + index_map.num_ghosts)
    return int(entries * np.dtype(np.complex128).itemsize)


def _matrix_facts(matrix: Any) -> dict[str, Any]:
    from petsc4py import PETSc

    info = dict(matrix.getInfo())
    rows, cols = (int(value) for value in matrix.getSize())
    nnz = int(round(float(info.get("nz_used", info.get("nz_allocated", 0.0)))))
    return {
        "rows": rows,
        "cols": cols,
        "local_rows": int(matrix.getLocalSize()[0]),
        "local_cols": int(matrix.getLocalSize()[1]),
        "nnz": nnz,
        "index_bytes": int((rows + 1 + nnz) * np.dtype(PETSc.IntType).itemsize),
        "numeric_bytes": int(nnz * np.dtype(PETSc.ScalarType).itemsize),
        "petsc_reported_memory_bytes": int(info.get("memory", 0.0)),
        "type": str(matrix.getType()),
    }


def _streaming_transfer():
    """Build the bounded axis-local transfer and sanitize its audit."""

    from .fullspace_lor_transfer import build_reference_factor_lor_transfer

    base = build_reference_factor_lor_transfer(S2_DEGREE)
    audit = dict(base.audit)
    # The derivation oracle is gone; only the retained streaming facts are
    # exposed to the S2 record.
    keep = {
        "degree": S2_DEGREE,
        "axis_count": 3,
        "batch_cell_cap": S2_TRANSFER_CELL_CAP,
        "global_transfer_matrix": False,
        "owner_local_streaming": True,
        "dense_derivation_workspace_retained": False,
        "numeric_allgather": False,
        "forward_tensor_numeric_bytes": int(audit["forward_tensor_numeric_bytes"]),
        "inverse_tensor_numeric_bytes": int(audit["inverse_tensor_numeric_bytes"]),
        "retained_numeric_bytes": int(audit["reference_factor_numeric_bytes"]),
        "reference_factor_index_metadata_bytes": int(
            audit["reference_factor_index_metadata_bytes"]
        ),
        "reference_factor_approx_retained_bytes": int(
            audit["reference_factor_approx_retained_bytes"]
        ),
        "batch_scratch_bytes": int(
            2 * S2_TRANSFER_CELL_CAP * 882 * 16
            + S2_TRANSFER_CELL_CAP * 294 * 16
        ),
    }
    class _StreamingTransfer:
        degree = S2_DEGREE
        edge_count = 3 * S2_DEGREE * (S2_DEGREE + 1) ** 2

        def __init__(self, delegate: Any, facts: Mapping[str, Any]) -> None:
            self._delegate = delegate
            self.audit = dict(facts)

        @property
        def nodes(self) -> np.ndarray:
            return self._delegate.nodes

        def high_to_lor_many(self, values: np.ndarray) -> np.ndarray:
            return self._delegate.high_to_lor_many(values)

        def lor_to_high_many(self, values: np.ndarray) -> np.ndarray:
            return self._delegate.lor_to_high_many(values)

        def lor_to_high_adjoint_many(self, values: np.ndarray) -> np.ndarray:
            return self._delegate.lor_to_high_adjoint_many(values)

    return _StreamingTransfer(base, keep)


def _make_positive_form(space: Any, coefficients: tuple[Any, Any]) -> Any:
    import ufl

    mu_inverse, mass = coefficients
    trial = ufl.TrialFunction(space)
    test = ufl.TestFunction(space)
    return (
        mu_inverse * ufl.inner(ufl.curl(trial), ufl.curl(test))
        + mass * ufl.inner(trial, test)
    ) * ufl.dx


def _canonical_raw_map(
    edge_space: Any,
    node_space: Any,
    edge_records: Mapping[int, tuple[int, int, float, int]],
    axes: tuple[np.ndarray, np.ndarray, np.ndarray],
    *,
    owner_ids: np.ndarray,
    local_permutations: np.ndarray,
    validate_local_owner_layout: bool = True,
) -> dict[str, np.ndarray]:
    from .fullspace_lor_topology import _pack_canonical_edges
    upper = np.asarray([axis.size - 1 for axis in axes], dtype=np.int32)
    index_map = edge_space.dofmap.index_map
    raw_ids = np.asarray(
        index_map.local_to_global(np.arange(int(index_map.size_local), dtype=np.int32)),
        dtype=np.int64,
    )
    canonical = np.empty(raw_ids.size, dtype=np.uint32)
    phase = np.empty(raw_ids.size, dtype=np.uint8)
    by_id = {int(key): value for key, value in edge_records.items()}
    # This is setup metadata only; no per-apply dictionary is retained.
    node_coordinates = np.asarray(node_space.tabulate_dof_coordinates(), dtype=np.float64)
    node_map = node_space.dofmap.index_map
    node_global = np.asarray(
        node_map.local_to_global(
            np.arange(int(node_map.size_local + node_map.num_ghosts), dtype=np.int32)
        ),
        dtype=np.int64,
    )
    coordinate_by_gid = {int(node_global[index]): node_coordinates[index] for index in range(node_global.size)}
    for position, raw_id in enumerate(raw_ids):
        low_gid, high_gid, _length, _axis = by_id[int(raw_id)]
        low = coordinate_by_gid[int(low_gid)]
        high = coordinate_by_gid[int(high_gid)]
        start = np.asarray(
            [int(np.argmin(np.abs(axis - low[axis_index]))) for axis_index, axis in enumerate(axes)],
            dtype=np.int32,
        )
        end = np.asarray(
            [int(np.argmin(np.abs(axis - high[axis_index]))) for axis_index, axis in enumerate(axes)],
            dtype=np.int32,
        )
        ids, _orientation, phases = _pack_canonical_edges(
            start[None, :], end[None, :], upper
        )
        canonical[position] = ids[0]
        phase[position] = phases[0]
    owner_ids = np.asarray(owner_ids, dtype=np.uint32)
    active = phase == 0
    active_ids = canonical[active]
    if np.unique(active_ids).size != active_ids.size:
        raise RuntimeError("active raw edge canonical map is not unique")
    if validate_local_owner_layout and not np.array_equal(
        np.sort(active_ids), np.sort(owner_ids)
    ):
        raise RuntimeError("active raw edge canonical map does not cover owner ids")
    work_space = edge_space
    cell_info = np.asarray(work_space.mesh.topology.get_cell_permutation_info(), dtype=np.uint32)
    storage_map = work_space.dofmap.index_map
    storage_global = np.asarray(
        storage_map.local_to_global(
            np.arange(int(storage_map.size_local + storage_map.num_ghosts), dtype=np.int32)
        ),
        dtype=np.int64,
    )
    factors = np.zeros(raw_ids.size, dtype=np.int8)
    seen = np.zeros(raw_ids.size, dtype=bool)
    raw_position = {int(value): index for index, value in enumerate(raw_ids)}
    local_permutations = np.asarray(local_permutations, dtype=np.int32)
    cell_count = int(work_space.mesh.topology.index_map(3).size_local)
    if local_permutations.shape != (cell_count, 12):
        raise RuntimeError("p1 local edge permutation inventory has wrong shape")
    for cell in range(cell_count):
        local_dofs = np.asarray(work_space.dofmap.cell_dofs(cell), dtype=np.int32)
        for local_edge in local_permutations[cell]:
            local_edge = int(local_edge)
            basis = np.zeros(local_dofs.size, dtype=np.complex128)
            basis[local_edge] = 1.0 + 0.0j
            work_space.element.Tt_apply(
                basis, np.asarray([cell_info[cell]], dtype=np.uint32), 1
            )
            factor = complex(basis[local_edge])
            if abs(factor.imag) > 1.0e-14 or abs(abs(factor.real) - 1.0) > 1.0e-14:
                raise RuntimeError("p1 edge orientation is not a sign")
            raw_global = int(storage_global[int(local_dofs[local_edge])])
            position = raw_position.get(raw_global)
            if position is None:
                continue
            sign = np.int8(1 if factor.real > 0.0 else -1)
            if seen[position] and factors[position] != sign:
                raise RuntimeError("p1 raw edge orientation is inconsistent")
            factors[position] = sign
            seen[position] = True
    if not np.all(seen):
        raise RuntimeError("p1 raw edge orientation inventory is incomplete")
    return {
        "raw_ids": raw_ids,
        "canonical_ids": canonical,
        "phase_codes": phase,
        "orientation_factors": factors,
    }


def _retained_array_bytes(value: Any, seen: set[int] | None = None) -> int:
    """Count retained ndarray storage once, including typed schedule mappings."""

    if seen is None:
        seen = set()
    if isinstance(value, np.ndarray):
        identity = id(value)
        if identity in seen:
            return 0
        seen.add(identity)
        return int(value.nbytes)
    if isinstance(value, Mapping):
        return int(sum(_retained_array_bytes(item, seen) for item in value.values()))
    if isinstance(value, (tuple, list)):
        return int(sum(_retained_array_bytes(item, seen) for item in value))
    return 0


def _topology_retained_arrays(topology: Any) -> tuple[Any, ...]:
    """Return the actual retained topology arrays and shared schedules."""

    return (
        topology.cell_edge_ids,
        topology.cell_orientation,
        topology.cell_phase_codes,
        topology.phase_values,
        topology.unique_edge_ids,
        topology.owned_edge_ids,
        topology.owner_schedule,
        topology.owner_received_sort_order,
        topology.owner_received_sorted_ids,
        topology.owner_received_group_starts,
        topology.pull_schedule,
        topology.pull_received_positions,
        topology.pull_send_positions,
    )


class S2FoundationCase:
    """One p6/h10 matrix-free foundation case with explicit ownership."""

    def __init__(self, objects: Mapping[str, Any]) -> None:
        self.__dict__.update(dict(objects))

    @property
    def audit(self) -> dict[str, Any]:
        return {
            "schema": S2_SCHEMA,
            "degree": S2_DEGREE,
            "h_nm": S2_H_NM,
            "wavelength_nm": S2_WAVELENGTH_NM,
            "global_high_order_aij": False,
            "global_dense_transfer": False,
            "global_numeric_allgather": False,
            "numeric_allgather": False,
            "scalar_node_matrix_built": False,
            "hx_hierarchy_built": False,
            "pcgamg_hierarchy_built": False,
            "p6_exact_edge_factor_built": False,
            "global_direct_coarse_built": False,
            "recovery_field_arrays_built": False,
            "hx_or_node_action_built": False,
            "production_local_spectral_built": False,
            "high_space": {
                "global_rows": int(self.high_space.dofmap.index_map.size_global),
                "local_storage_entries": int(
                    self.high_space.dofmap.index_map.size_local
                    + self.high_space.dofmap.index_map.num_ghosts
                ),
            },
            "low_space": {
                "global_rows": int(self.low_edge_space.dofmap.index_map.size_global),
                "local_storage_entries": int(
                    self.low_edge_space.dofmap.index_map.size_local
                    + self.low_edge_space.dofmap.index_map.num_ghosts
                ),
            },
            "low_raw_map": {
                "owned_raw_rows": int(self.low_raw_map["raw_ids"].size),
                "active_raw_rows": int(
                    np.count_nonzero(self.low_raw_map["phase_codes"] == 0)
                ),
                "phase_rows": int(
                    np.count_nonzero(self.low_raw_map["phase_codes"] != 0)
                ),
                "owner_id_authority": "low_topology.owned_edge_ids",
                "array_bytes": int(
                    sum(int(array.nbytes) for array in self.low_raw_map.values())
                ),
            },
            "transfer": dict(self.transfer.audit),
            "low_matrix": _matrix_facts(self.low_matrix),
            "physical_action": dict(self.physical_action.audit),
            "high_positive_action": dict(self.high_positive.audit),
            "setup_resources": list(getattr(self, "setup_resources", ())),
        }

    def high_positive_into(self, source: Any, target: Any) -> None:
        result = self.high_positive.apply(source)
        result.copy(target)

    def physical_into(self, source: Any, target: Any) -> None:
        self.physical_action.apply(source, target)

    def restrict_into(self, source: Any, target: Any) -> None:
        owner_ids, owner_values = _route_high_dual_to_lor(
            self.high_space,
            self.high_floquet,
            self.high_topology,
            self.transfer,
            source,
        )
        unique = self.low_topology.pull_owner_unique_values(owner_ids, owner_values)
        _fill_raw_vector(target, unique, self.low_raw_map, self.low_topology.unique_edge_ids)

    def lor_matvec_into(self, source: Any, target: Any) -> None:
        self.low_matrix.mult(source, target)

    def lift_into(self, source: Any, target: Any) -> None:
        owner_ids, owner_values = _route_low_to_owner(
            self.low_edge_space,
            self.low_floquet,
            self.low_topology,
            source,
            self.low_p1_transfer_local_indices,
        )
        unique = self.high_topology.pull_owner_unique_values(owner_ids, owner_values)
        _fill_high_from_unique(
            self.high_space,
            self.high_floquet,
            self.high_topology,
            self.transfer,
            unique,
            target,
        )

    def retained_ledger(self, reserve: Mapping[str, Any], resource: Mapping[str, Any]) -> dict[str, Any]:
        high_vec_bytes = _space_storage_bytes(self.high_space)
        low_vec_bytes = _space_storage_bytes(self.low_edge_space)
        dtn_audit = dict(self.physical_action.audit.get("dtn_action", {}))
        dtn_numeric = int(dtn_audit.get("retained_numeric_bytes_global_sum", 0))
        dtn_identity = int(dtn_audit.get("retained_identity_bytes", 0))
        dtn_work = int(dtn_audit.get("bounded_work_bytes_global_sum", 0))
        volume_audit = dict(self.physical_action.audit.get("volume_action", {}))
        volume_arrays = int(volume_audit.get("retained_numeric_payload_global_sum_bytes", 0))
        high_arrays = int(self.audit["high_positive_action"].get("retained_numeric_payload_global_sum_bytes", 0))
        low_matrix = self.audit["low_matrix"]
        low_topology = self.low_topology.audit
        high_topology = self.high_topology.audit
        raw_map_bytes = sum(
            int(array.nbytes) for array in self.low_raw_map.values()
        )
        high_topology_arrays = _retained_array_bytes(
            _topology_retained_arrays(self.high_topology)
        )
        low_topology_arrays = _retained_array_bytes(
            _topology_retained_arrays(self.low_topology)
        )
        transfer_approx = int(
            self.transfer.audit["reference_factor_approx_retained_bytes"]
        )
        known = {
            "mesh_space_mpc_known_array_bytes": None,
            "high_positive_action_known_array_bytes": high_arrays,
            "physical_volume_action_known_array_bytes": volume_arrays,
            "foundation_high_work_vectors_bytes": int(3 * high_vec_bytes),
            "foundation_low_work_vectors_bytes": int(3 * low_vec_bytes),
            "restart_reserve_numeric_bytes": int(reserve["local_numeric_bytes"]),
            "transfer_reference_factor_approx_retained_bytes": transfer_approx,
            "lor_matrix_index_bytes": int(low_matrix["index_bytes"]),
            "lor_matrix_numeric_bytes": int(low_matrix["numeric_bytes"]),
            "lor_matrix_petsc_overhead_bytes": int(
                max(
                    int(low_matrix["petsc_reported_memory_bytes"])
                    - int(low_matrix["index_bytes"])
                    - int(low_matrix["numeric_bytes"]),
                    0,
                )
            ),
            "high_topology_retained_array_bytes": high_topology_arrays,
            "low_topology_retained_array_bytes": low_topology_arrays,
            "low_raw_map_bytes": int(raw_map_bytes),
            "low_p1_permutation_bytes": int(
                self.low_p1_transfer_local_indices.nbytes
            ),
            "dtn_retained_numeric_bytes_global_sum": dtn_numeric,
            "dtn_retained_identity_bytes_global_sum": dtn_identity,
            "dtn_bounded_work_bytes_global_sum": dtn_work,
        }
        rss = int(resource.get("process_tree", {}).get("rss_bytes", 0))
        known_total = int(sum(value for value in known.values() if isinstance(value, int)))
        return {
            "scope": "rank0 process-tree sample minus explicit retained object ledger",
            "known_bytes": known,
            "known_total_bytes": known_total,
            "bounded_temporary_bytes": {
                "transfer_batch_scratch_bytes": int(
                    self.transfer.audit["batch_scratch_bytes"]
                ),
                "topology_apply_scratch_upper_bound_bytes": int(
                    max(
                        high_topology.get("apply_scratch_upper_bound_bytes", 0),
                        low_topology.get("apply_scratch_upper_bound_bytes", 0),
                    )
                ),
                "included_in_known_total": False,
            },
            "object_bytes_semantics": (
                "mesh/space/MPC C++ allocations are not decomposed: their known "
                "array bytes are null, measured_separately is false, and they are "
                "included in the measured unattributed remainder; stage RSS "
                "deltas are allocator/JIT-sensitive and are not added to known bytes"
            ),
            "mesh_space_mpc": {
                "known_array_bytes": None,
                "measured_separately": False,
                "included_in_unattributed": True,
            },
            "vector_facts": {
                "high_bytes_per_vector": int(high_vec_bytes),
                "high_vector_count": 3,
                "low_bytes_per_vector": int(low_vec_bytes),
                "low_vector_count": 3,
            },
            "measured_process_tree_rss_bytes": rss,
            "unattributed_remainder_bytes": int(rss - known_total),
            "resource": dict(resource),
        }

    def destroy(self) -> None:
        for name in (
            "high_primal_source",
            "high_dual_source",
            "low_primal_source",
            "low_work_input",
            "low_work_output",
            "high_work_output",
        ):
            vector = getattr(self, name, None)
            if vector is not None:
                vector.destroy()
                setattr(self, name, None)
        for name in ("physical_action", "high_positive", "low_matrix"):
            obj = getattr(self, name, None)
            if obj is not None and hasattr(obj, "destroy"):
                obj.destroy()
                setattr(self, name, None)
        for name in ("high_floquet", "low_floquet", "high_mesh", "low_mesh"):
            setattr(self, name, None)
        for name in (
            "high_data",
            "low_data",
            "high_space",
            "low_edge_space",
            "high_topology",
            "low_topology",
            "transfer",
            "low_raw_map",
            "low_p1_transfer_local_indices",
            "setup_resources",
            "high_coeff_audit",
            "low_coeff_audit",
            "mode_manifest",
            "resolved_config",
        ):
            setattr(self, name, None)


def _route_high_dual_to_lor(
    space: Any, floquet: Any, topology: Any, transfer: Any, source: Any
):
    """Apply the adjoint high-to-LOR restriction with owner addition."""

    from petsc4py import PETSc
    from dolfinx import fem

    work_space = floquet.mpc.function_space
    residual_field = _field_from_vec(work_space, source)
    floquet.mpc.homogenize(residual_field)
    residual_field.x.scatter_forward()
    multiplicity = fem.Function(work_space)
    multiplicity.x.array[:] = 0.0
    cell_count = int(space.mesh.topology.index_map(3).size_local)
    cell_info = np.asarray(space.mesh.topology.get_cell_permutation_info(), dtype=np.uint32)
    for cell in range(cell_count):
        local_dofs = np.asarray(work_space.dofmap.cell_dofs(cell), dtype=np.int32)
        multiplicity.x.array[local_dofs] += 1.0
    multiplicity.x.petsc_vec.ghostUpdate(
        addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE
    )
    multiplicity.x.scatter_forward()

    def chunks():
        batch_start = 0
        batch: list[np.ndarray] = []
        for cell in range(cell_count):
            local_dofs = np.asarray(work_space.dofmap.cell_dofs(cell), dtype=np.int32)
            local_multiplicity = np.asarray(
                multiplicity.x.array[local_dofs].real, dtype=np.float64
            )
            if np.any(local_multiplicity <= 0.0):
                raise RuntimeError("high dual restriction multiplicity is incomplete")
            values = np.asarray(
                residual_field.x.array[local_dofs], dtype=np.complex128
            ).copy() / local_multiplicity
            work_space.element.Tt_apply(
                values, np.asarray([cell_info[cell]], dtype=np.uint32), 1
            )
            batch.append(values)
            if len(batch) == S2_TRANSFER_CELL_CAP or cell + 1 == cell_count:
                yield batch_start, transfer.lor_to_high_adjoint_many(
                    np.asarray(batch, dtype=np.complex128)
                )
                batch_start = cell + 1
                batch = []

    try:
        return topology.route_owner_cell_chunks_additive(chunks())
    finally:
        del multiplicity, residual_field


def _route_low_to_owner(
    space: Any,
    floquet: Any,
    topology: Any,
    source: Any,
    local_permutations: np.ndarray,
):
    work_space = floquet.mpc.function_space
    local_field = _field_from_vec(work_space, source)
    floquet.mpc.homogenize(local_field)
    local_field.x.scatter_forward()
    floquet.mpc.backsubstitution(local_field)
    local_field.x.scatter_forward()
    cell_info = np.asarray(space.mesh.topology.get_cell_permutation_info(), dtype=np.uint32)

    def chunks():
        batch_start = 0
        batch: list[np.ndarray] = []
        for cell in range(topology.cell_edge_ids.shape[0]):
            local_dofs = np.asarray(work_space.dofmap.cell_dofs(cell), dtype=np.int32)
            values = np.asarray(local_field.x.array[local_dofs], dtype=np.complex128).copy()
            work_space.element.Tt_apply(values, np.asarray([cell_info[cell]], dtype=np.uint32), 1)
            values = values[np.asarray(local_permutations[cell], dtype=np.int32)]
            batch.append(values)
            if len(batch) == S2_TRANSFER_CELL_CAP or cell + 1 == topology.cell_edge_ids.shape[0]:
                yield batch_start, np.asarray(batch, dtype=np.complex128)
                batch_start = cell + 1
                batch = []
    try:
        return topology.route_owner_cell_chunks(chunks())
    finally:
        del local_field


def _field_from_vec(space: Any, vector: Any) -> Any:
    from dolfinx import fem

    field = fem.Function(space)
    vector.copy(field.x.petsc_vec)
    field.x.scatter_forward()
    return field


def _fill_raw_vector(target: Any, unique: np.ndarray, raw_map: Mapping[str, np.ndarray], unique_ids: np.ndarray) -> None:
    positions = np.searchsorted(unique_ids, raw_map["canonical_ids"])
    if np.any(positions >= unique_ids.size) or not np.array_equal(unique_ids[positions], raw_map["canonical_ids"]):
        raise RuntimeError("low raw/canonical owner map is incomplete")
    values = np.asarray(unique[positions], dtype=np.complex128).copy()
    values /= np.asarray(raw_map["orientation_factors"], dtype=np.complex128)
    values[np.asarray(raw_map["phase_codes"]) != 0] = 0.0
    target.set(0.0 + 0.0j)
    target.array[:] = values


def _fill_high_from_unique(space: Any, floquet: Any, topology: Any, transfer: Any, unique: np.ndarray, target: Any) -> None:
    from petsc4py import PETSc
    from dolfinx import fem

    work_space = floquet.mpc.function_space
    cell_info = np.asarray(space.mesh.topology.get_cell_permutation_info(), dtype=np.uint32)
    field = fem.Function(work_space)
    multiplicity = fem.Function(work_space)
    field.x.array[:] = 0.0 + 0.0j
    multiplicity.x.array[:] = 0.0
    for start in range(0, topology.cell_edge_ids.shape[0], S2_TRANSFER_CELL_CAP):
        stop = min(start + S2_TRANSFER_CELL_CAP, topology.cell_edge_ids.shape[0])
        low_values = topology.cell_values_from_unique(unique, start, stop)
        high_values = transfer.lor_to_high_many(low_values)
        for offset, cell in enumerate(range(start, stop)):
            local_dofs = np.asarray(work_space.dofmap.cell_dofs(cell), dtype=np.int32)
            values = np.asarray(high_values[offset], dtype=np.complex128).copy()
            work_space.element.T_apply(values, np.asarray([cell_info[cell]], dtype=np.uint32), 1)
            field.x.array[local_dofs] += values
            multiplicity.x.array[local_dofs] += 1.0
    field.x.petsc_vec.ghostUpdate(addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE)
    multiplicity.x.petsc_vec.ghostUpdate(addv=PETSc.InsertMode.ADD_VALUES, mode=PETSc.ScatterMode.REVERSE)
    owned = int(work_space.dofmap.index_map.size_local)
    if np.any(multiplicity.x.array[:owned] <= 0.0):
        raise RuntimeError("high lift multiplicity does not cover owned rows")
    field.x.array[:owned] /= multiplicity.x.array[:owned]
    field.x.petsc_vec.ghostUpdate(addv=PETSc.InsertMode.INSERT_VALUES, mode=PETSc.ScatterMode.FORWARD)
    floquet.mpc.homogenize(field)
    floquet.mpc.backsubstitution(field)
    field.x.scatter_forward()
    field.x.petsc_vec.copy(target)
    del multiplicity, field


def build_s2_foundation_case(
    raw_dir: Path,
    comm: Any,
    cfg: Any,
    *,
    resolved_config: str | bytes,
    resource_sample: Callable[[], Mapping[str, Any]] | None = None,
) -> S2FoundationCase:
    """Build the p6/h10 foundation from the caller's resolved Task38 config."""

    import ufl
    from dolfinx import fem
    from mpi4py import MPI
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.mesh_builder_3d import (
        _mark_boundary_facets,
        _mark_cells,
        _stage4_axis_plan,
        _structured_hexa_mesh,
        build_airbox_mesh_3d,
    )
    from src.solvers.common_3d_forms import _build_variational_forms
    from src.solvers.common_3d_solve import _create_nedelec_space
    from src.solvers.dtn_port_3d import _dtn_surface_quadrature_degree
    from src.solvers.fullspace_dtn_action import (
        build_dynamic_mode_inventory,
        build_fullspace_dtn_action,
        build_fullspace_dtn_carrier_from_surface,
    )
    from basix.ufl import element
    from src.solvers.fullspace_lor_native_hx_fixture import (
        _P1IdentityTransfer,
        _assemble_sparse,
        _consistent_field,
        _edge_records,
        _p1_transfer_local_indices,
        _piecewise_positive_coefficients,
        _refined_axis,
    )
    from src.solvers.fullspace_lor_topology import build_canonical_lor_subedge_topology
    from src.solvers.fullspace_mpc_action import build_fullspace_mpc_form_action
    from src.solvers.fullspace_physical_action import FullspacePhysicalAction
    from benchmarks.run_task038_full3d_r4 import _make_surface_assemblers

    if comm != MPI.COMM_WORLD:
        raise ValueError("S2 case uses the qualified MPI world communicator")
    if (
        int(cfg.nedelec_degree) != S2_DEGREE
        or abs(float(cfg.mesh_target_size) - S2_H_NM) > 0.0
        or abs(float(cfg.lambda0) - S2_WAVELENGTH_NM) > 0.0
    ):
        raise ValueError("S2 builder received a non-frozen p6/h10 resolved config")

    setup_resources: list[dict[str, Any]] = []

    def snapshot(stage: str) -> None:
        if resource_sample is None:
            return
        sample = dict(resource_sample())
        process_tree = dict(sample.get("process_tree", {}))
        row = {
            "stage": stage,
            "process_tree": {
                "rss_bytes": int(process_tree.get("rss_bytes", -1)),
                "swap_bytes": int(process_tree.get("swap_bytes", -1)),
                "all_status_readable": bool(
                    process_tree.get("all_status_readable", False)
                ),
            },
        }
        if setup_resources:
            row["rss_delta_bytes"] = int(
                row["process_tree"]["rss_bytes"]
                - setup_resources[-1]["process_tree"]["rss_bytes"]
            )
        setup_resources.append(row)

    snapshot("start")
    high_data = build_airbox_mesh_3d(cfg, Path(raw_dir) / "mesh")
    high_space = _create_nedelec_space(high_data.mesh, cfg)
    high_floquet = build_double_floquet_mpc(high_space, high_data, cfg)
    snapshot("high_mesh_space_mpc")
    high_mu, high_mass, high_coeff_audit = _piecewise_positive_coefficients(
        high_data.mesh, high_data.cell_tags, cfg
    )
    high_form = _make_positive_form(high_space, (high_mu, high_mass))
    high_positive = build_fullspace_mpc_form_action(
        high_form, high_space, mpc=high_floquet.mpc
    )
    seed_field = _consistent_field(high_space, high_floquet)
    high_primal_source = seed_field.x.petsc_vec.copy()
    del seed_field
    high_dual_work = high_positive.apply(high_primal_source)
    high_dual_source = high_dual_work.copy()

    modes, _mode_rows, mode_inventory_sha = build_dynamic_mode_inventory(cfg)
    from src.solvers.fullspace_dtn_action import build_ordered_mode_manifest

    mode_manifest, _mode_bytes, mode_sha = build_ordered_mode_manifest(modes, cfg)
    if mode_inventory_sha != mode_sha:
        raise RuntimeError("dynamic mode inventory and ordered manifest hashes differ")
    qdegree = _dtn_surface_quadrature_degree(cfg, list(modes))
    assemblers = _make_surface_assemblers(high_space, high_data, cfg, qdegree)
    carrier = build_fullspace_dtn_carrier_from_surface(
        modes, assemblers, high_floquet.mpc, cfg
    )
    dtn_action = build_fullspace_dtn_action(carrier, comm=comm)
    physical_form, _rhs = _build_variational_forms(
        high_data.mesh, high_data, cfg, high_space, field_formulation="total_field"
    )
    volume_action = build_fullspace_mpc_form_action(
        physical_form, high_space, mpc=high_floquet.mpc
    )
    physical_action = FullspacePhysicalAction(volume_action, dtn_action)
    snapshot("high_actions")

    plan = _stage4_axis_plan(cfg, comm.size)
    refined_axes = tuple(_refined_axis(values, S2_DEGREE) for values in (plan.x_values, plan.y_values, plan.z_values))
    low_mesh = _structured_hexa_mesh(
        comm,
        *refined_axes,
        preserve_input_partition=cfg.stage4_preserve_structured_input_partition,
    )
    low_facets, _ = _mark_boundary_facets(low_mesh, cfg)
    low_cells = _mark_cells(low_mesh, cfg)
    low_data = SimpleNamespace(mesh=low_mesh, cell_tags=low_cells, facet_tags=low_facets)
    low_cfg = copy.deepcopy(cfg)
    low_cfg.nedelec_degree = 1
    low_cfg.visualization_degree = 1
    low_cfg.nedelec_trace_degree = None
    low_cfg.nedelec_interior_degree = None
    low_cfg.case_name = f"{cfg.case_name}_lor_p1"
    low_edge_space = fem.functionspace(
        low_mesh,
        element("N1curl", low_mesh.basix_cell(), 1, dtype=np.float64),
    )
    low_floquet = build_double_floquet_mpc(low_edge_space, low_data, low_cfg)
    snapshot("low_mesh_space_mpc")
    low_p1_transfer_local_indices = np.asarray(
        [
            _p1_transfer_local_indices(low_edge_space, cell)
            for cell in range(int(low_mesh.topology.index_map(3).size_local))
        ],
        dtype=np.int32,
    )
    low_mu, low_mass, low_coeff_audit = _piecewise_positive_coefficients(
        low_mesh, low_cells, low_cfg
    )
    low_trial = ufl.TrialFunction(low_edge_space)
    low_test = ufl.TestFunction(low_edge_space)
    low_form = (
        low_mu * ufl.inner(ufl.curl(low_trial), ufl.curl(low_test))
        + low_mass * ufl.inner(low_trial, low_test)
    ) * ufl.dx
    low_matrix = _assemble_sparse(low_form, mpc=low_floquet.mpc)
    transfer = _streaming_transfer()
    high_topology = build_canonical_lor_subedge_topology(
        high_space, high_floquet, transfer
    )
    low_topology = build_canonical_lor_subedge_topology(
        low_edge_space, low_floquet, _P1IdentityTransfer()
    )
    if not np.array_equal(high_topology.owned_edge_ids, low_topology.owned_edge_ids):
        raise RuntimeError("high and low owner inventories do not close")
    low_node_space = fem.functionspace(
        low_mesh,
        element("Lagrange", low_mesh.basix_cell(), 1, dtype=np.float64),
    )
    low_records, low_metadata_bytes = _edge_records(low_edge_space, low_node_space)
    low_raw_map = _canonical_raw_map(
        low_edge_space,
        low_node_space,
        low_records,
        refined_axes,
        owner_ids=low_topology.owned_edge_ids,
        local_permutations=low_p1_transfer_local_indices,
    )
    low_seed_field = _consistent_field(low_edge_space, low_floquet)
    low_primal_source = low_seed_field.x.petsc_vec.copy()
    del low_seed_field, low_node_space
    low_work_input = low_matrix.createVecRight()
    low_work_output = low_matrix.createVecLeft()
    high_work_output = high_positive.matrix.createVecLeft()
    snapshot("low_matrix_transfer_topology_work")
    return S2FoundationCase(
        {
            "cfg": cfg,
            "high_data": high_data,
            "low_data": low_data,
            "high_mesh": high_data.mesh,
            "low_mesh": low_mesh,
            "high_space": high_space,
            "low_edge_space": low_edge_space,
            "high_floquet": high_floquet,
            "low_floquet": low_floquet,
            "high_positive": high_positive,
            "physical_action": physical_action,
            "low_matrix": low_matrix,
            "transfer": transfer,
            "high_topology": high_topology,
            "low_topology": low_topology,
            "low_raw_map": low_raw_map,
            "high_primal_source": high_primal_source,
            "high_dual_source": high_dual_source,
            "low_primal_source": low_primal_source,
            "low_work_input": low_work_input,
            "low_work_output": low_work_output,
            "high_work_output": high_work_output,
            "low_p1_transfer_local_indices": low_p1_transfer_local_indices,
            "high_coeff_audit": high_coeff_audit,
            "low_coeff_audit": low_coeff_audit,
            "mode_manifest": mode_manifest,
            "mode_sha": mode_sha,
            "resolved_config": resolved_config,
            "low_metadata_bytes": int(low_metadata_bytes),
            "high_metadata_bytes": 0,
            "setup_resources": setup_resources,
        }
    )


__all__ = [
    "S2_APPLY_NAMES",
    "S2_COLD_RSS_LIMIT",
    "S2_DEGREE",
    "S2_H_NM",
    "S2_REPEAT_COUNT",
    "S2_REPEAT_NORM_TOL",
    "S2_REPEAT_GROWTH_LIMIT",
    "S2_RESTART_BASIS_COUNT",
    "S2_RETAINED_RSS_LIMIT",
    "S2_RESERVE_VECTOR_COUNT",
    "S2_SCHEMA",
    "S2_TRANSFER_CELL_CAP",
    "S2_SETUP_RESOURCE_STAGES",
    "S2_WAVELENGTH_NM",
    "S2FoundationCase",
    "allocate_restart20_reserve",
    "build_s2_foundation_case",
    "destroy_restart20_reserve",
    "run_fixed_apply_ledger",
]
