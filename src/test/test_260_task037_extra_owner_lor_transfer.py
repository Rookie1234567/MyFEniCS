from __future__ import annotations

import basix
import numpy as np
import pytest
from dolfinx import default_real_type, fem
from mpi4py import MPI

from src.constraints.high_order_floquet_trace import (
    FloquetTopologyKey,
    FloquetTraceTopology,
)
from src.geometry.tetra_mesh_audit import (
    canonical_owned_cell_ids,
    mesh_coordinate_tolerance,
)
from src.solvers.hcurl_assembly_time_condensation import (
    _cell_trace_expansion,
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.static_fullspace_slab_factor_oracle import (
    assemble_fullspace_slab_matrix,
)
from src.solvers.static_lor_hcurl_transfer import (
    LORSlabParentPackingRecord,
    _csr_payload_bytes,
    _reference_transfer_data,
    build_affine_lor_parent_topology,
    build_lor_slab_edge_space,
    build_owner_local_lor_transfer,
)
from src.solvers.physical_slab_two_level import (
    build_owner_local_slab_plan,
    collect_owner_local_fullspace_slab_cells,
)
from src.test.test_224_task037_static_local_schur_action import _build_fixture
from src.test.test_258_task037_extra_lor_topology import _positive_reference_edges


def _empty_floquet(degree: int) -> FloquetTraceTopology:
    return FloquetTraceTopology(
        key=FloquetTopologyKey(
            mesh_token=f"c1b1-empty-{degree}",
            element_family="N1curl",
            degree=degree,
        ),
        blocks=(),
        topology_build_seconds=0.0,
        bytes_sent=0,
        bytes_received=0,
    )


def _affine_field(point: np.ndarray) -> np.ndarray:
    x, y, z = point
    return np.asarray(
        [
            1.0 + 2.0 * y - 0.5 * z,
            -0.2 + 0.75 * x + 0.3 * z,
            0.4 - 0.6 * x + 0.9 * y,
        ],
        dtype=np.complex128,
    )


def _constant_field(point: np.ndarray) -> np.ndarray:
    del point
    return np.asarray([0.7, -0.2, 1.1], dtype=np.complex128)


def _physical_edge_line_integrals(topologies, edge_space, field):
    endpoints_by_key = {}
    for topology in topologies:
        starts, ends, _signs = _positive_reference_edges(topology)
        degree = int(topology.degree)
        node_count = degree + 1

        def grid_index(i, j, k):
            return (i * node_count + j) * node_count + k

        origin = topology.vertices[grid_index(0, 0, 0)]
        axes = np.column_stack(
            (
                topology.vertices[grid_index(degree, 0, 0)] - origin,
                topology.vertices[grid_index(0, degree, 0)] - origin,
                topology.vertices[grid_index(0, 0, degree)] - origin,
            )
        )

        def physical_point(reference_point):
            return origin + axes @ reference_point

        for edge_id, edge_key in enumerate(topology.edge_keys):
            endpoints_by_key.setdefault(
                edge_key,
                (
                    physical_point(starts[edge_id]),
                    physical_point(ends[edge_id]),
                ),
            )
    values = []
    for edge_key in edge_space.active_edge_keys:
        first, second = endpoints_by_key[edge_key]
        tangent = second - first
        values.append(
            0.5 * np.dot(field(first) + field(second), tangent)
        )
    return np.asarray(values, dtype=np.complex128)


def _packing_records(condensed, mesh, cell_tags, plan, slab):
    cells, collector_audit = collect_owner_local_fullspace_slab_cells(
        condensed,
        plan,
        mesh,
        slab,
    )
    canonical_ids, geometry_records, _ordered_keys = canonical_owned_cell_ids(mesh)
    tolerance = mesh_coordinate_tolerance(mesh)
    mesh.topology.create_entity_permutations()
    cell_permutations = mesh.topology.get_cell_permutation_info()
    tag_by_cell = {
        int(index): int(value)
        for index, value in zip(cell_tags.indices, cell_tags.values, strict=True)
    }
    owner_rows = np.asarray(plan.owner_rows[slab], dtype=np.int64)
    constraints = condensed.trace_constraints
    local_index_by_canonical_id = {
        int(canonical_id): cell_index
        for cell_index, canonical_id in enumerate(canonical_ids)
    }
    records = []
    ordered_recoveries = []
    for cell in cells:
        cell_index = local_index_by_canonical_id[cell.canonical_cell_id]
        recovery = condensed.cell_recovery_maps[cell_index]
        topology = build_affine_lor_parent_topology(
            geometry_records[cell_index].coordinates,
            degree=2,
            canonical_cell_id=int(canonical_ids[cell_index]),
            material_tag=tag_by_cell[cell_index],
            cell_permutation=int(cell_permutations[cell_index]),
            coordinate_tolerance=tolerance,
        )
        full_active_ids, full_expansion, _identity = _cell_trace_expansion(
            recovery.trace_original_dofs,
            constraints,
        )
        selected_active_ids = {
            int(owner_rows[position]) for position in cell.active_positions
        }
        complete_rows = []
        for row in range(full_expansion.shape[0]):
            start = int(full_expansion.indptr[row])
            stop = int(full_expansion.indptr[row + 1])
            complete_rows.append(
                all(
                    int(full_active_ids[column]) in selected_active_ids
                    for column in full_expansion.indices[start:stop]
                )
            )
        trace_active_rows = np.asarray(
            [
                constraints.original_to_active.get(int(original), -1)
                for original in recovery.trace_original_dofs
            ],
            dtype=np.int64,
        )
        records.append(
            LORSlabParentPackingRecord(
                topology=topology,
                trace_original_dofs=recovery.trace_original_dofs,
                trace_active_rows=trace_active_rows,
                trace_expansion=cell.trace_expansion,
                active_positions=cell.active_positions,
                trace_complete_rows=np.asarray(complete_rows, dtype=np.bool_),
            )
        )
        ordered_recoveries.append(recovery)
    records.sort(key=lambda record: record.topology.canonical_cell_id)
    recovery_by_id = {
        int(canonical_ids[cell_index]): condensed.cell_recovery_maps[cell_index]
        for cell_index in range(len(canonical_ids))
    }
    ordered_recoveries = [
        recovery_by_id[record.topology.canonical_cell_id]
        for record in records
    ]
    return records, cells, owner_rows, ordered_recoveries, collector_audit


@pytest.mark.parametrize("field", (_constant_field, _affine_field))
def test_owner_local_lor_transfer_packs_real_p2_fixture(field):
    mesh, cell_tags, function_space, compiled = _build_fixture(MPI.COMM_SELF)
    condensed = build_unconstrained_assembly_time_condensation(
        compiled,
        function_space,
        cell_tags,
        materialize_global_matrix=False,
        retain_local_schur_for_matrix_free=True,
        retain_fullspace_slab_blocks_for_research=True,
    )
    try:
        plan = build_owner_local_slab_plan(
            condensed,
            mesh,
            domain_z=(0.0, 1.0),
            num_slabs=3,
            overlap_fraction=0.0,
        )
        slab = 0
        (
            records,
            cells,
            owner_rows,
            ordered_recoveries,
            collector_audit,
        ) = _packing_records(
            condensed,
            mesh,
            cell_tags,
            plan,
            slab,
        )
        assert collector_audit["partial_cell_count"] == 0
        assert collector_audit["owner_cell_count"] == len(cells)
        topologies = [record.topology for record in records]
        edge_space = build_lor_slab_edge_space(
            topologies,
            _empty_floquet(2),
            phase_x=1.0 + 0.0j,
            phase_y=1.0 + 0.0j,
        )
        transfer = build_owner_local_lor_transfer(
            records,
            edge_space,
            owner_rows,
        )
        assert transfer.edge_space is edge_space

        element = basix.ufl.element(
            "N1curl",
            mesh.basix_cell(),
            2,
            dtype=default_real_type,
        ).basix_element
        interior_count = len(element.entity_dofs[3][0])
        assert transfer.audit["parent_ids"] == sorted(
            transfer.audit["parent_ids"]
        )
        assert transfer.audit["full_rows"] == (
            transfer.audit["interior_rows"] + owner_rows.size
        )
        assert transfer.audit["trace_offset"] == transfer.audit["interior_rows"]
        assert transfer.audit["owner_row_count"] == owner_rows.size
        assert transfer.audit["row_order"] == (
            "canonical_cell_id_interiors_then_owner_rows"
        )
        assert transfer.audit["cell_interior_row_counts"] == [
            interior_count
        ] * len(records)
        assert transfer.audit["cell_interior_offsets"] == [
            index * interior_count for index in range(len(records))
        ]
        assert transfer.audit["parent_ids"] == [
            cell.canonical_cell_id for cell in cells
        ]
        assert transfer.audit["missing_writer_count"] == 0
        assert transfer.audit["shared_trace_max_relative_error"] <= 1.0e-11
        assert (
            transfer.audit["complete_trace_reconstruction_max_relative_error"]
            <= 1.0e-11
        )
        assert transfer.audit["unique_parent_transfer_stencil_count"] < len(records)
        assert transfer.audit["global_dense_T_retained"] is False
        assert not hasattr(transfer, "_q_tail")
        unique_transfers = {
            id(value): value for value in transfer._parent_transfers
        }.values()
        unique_t_forward_bytes = sum(
            _csr_payload_bytes(value._forward) for value in unique_transfers
        )
        unique_t_adjoint_bytes = sum(
            _csr_payload_bytes(value._adjoint) for value in unique_transfers
        )
        e_forward_bytes = sum(
            _csr_payload_bytes(value)
            for value in transfer._edge_space._parent_expansions
        )
        e_adjoint_bytes = sum(
            _csr_payload_bytes(value)
            for value in transfer._edge_space._parent_adjoint
        )
        packing_index_bytes = sum(
            int(value.nbytes)
            for arrays in (
                transfer._interior_positions,
                transfer._trace_positions,
            )
            for value in arrays
        )
        reference_csr = _reference_transfer_data(2)[0]
        assert transfer.audit["unique_T_forward_csr_payload_bytes"] == (
            unique_t_forward_bytes
        )
        assert transfer.audit["unique_T_adjoint_csr_payload_bytes"] == (
            unique_t_adjoint_bytes
        )
        assert transfer.audit["E_csr_payload_bytes"] == e_forward_bytes
        assert transfer.audit["E_adjoint_csr_payload_bytes"] == e_adjoint_bytes
        assert transfer.audit["retained_numpy_packing_index_bytes"] == (
            packing_index_bytes
        )
        assert transfer.audit["reference_transfer_csr_cache_bytes"] == (
            _csr_payload_bytes(reference_csr)
        )
        payload_components = (
            unique_t_forward_bytes,
            unique_t_adjoint_bytes,
            e_forward_bytes,
            e_adjoint_bytes,
            packing_index_bytes,
            _csr_payload_bytes(reference_csr),
        )
        assert transfer.audit["retained_numeric_payload_lower_bound_bytes"] == sum(
            payload_components
        )
        assert unique_t_forward_bytes < sum(
            _csr_payload_bytes(value._forward)
            for value in transfer._parent_transfers
        )

        matrix, matrix_audit = assemble_fullspace_slab_matrix(
            cells,
            active_size=int(owner_rows.size),
        )
        assert matrix_audit["cell_canonical_ids"] == transfer.audit["parent_ids"]
        assert matrix_audit["cell_interior_offsets"] == transfer.audit[
            "cell_interior_offsets"
        ]
        assert matrix_audit["cell_interior_row_counts"] == transfer.audit[
            "cell_interior_row_counts"
        ]
        assert matrix_audit["trace_offset"] == transfer.audit["trace_offset"]
        assert matrix_audit["full_rows"] == transfer.audit["full_rows"]
        assert matrix_audit["trace_rows"] == owner_rows.size
        matrix.destroy()

        active_values = np.arange(
            len(edge_space.active_edge_keys),
            dtype=np.float64,
        ) + 0.25j
        full_values = transfer.apply(active_values)
        assert np.array_equal(full_values, transfer.apply(active_values))
        adjoint_input = np.arange(
            transfer.audit["full_rows"],
            dtype=np.float64,
        ) - 0.75j
        left = np.vdot(full_values, adjoint_input)
        right = np.vdot(active_values, transfer.apply_adjoint(adjoint_input))
        assert abs(left - right) / max(abs(left), abs(right), 1.0) <= 1.0e-11

        field_function = fem.Function(function_space)

        def dolfinx_field(points):
            x, y, z = points
            values = np.vstack(
                [
                    1.0 + 2.0 * y - 0.5 * z,
                    -0.2 + 0.75 * x + 0.3 * z,
                    0.4 - 0.6 * x + 0.9 * y,
                ]
            )
            if field is _constant_field:
                values = np.vstack(
                    [
                        np.full_like(x, 0.7),
                        np.full_like(x, -0.2),
                        np.full_like(x, 1.1),
                    ]
                )
            return values

        field_function.interpolate(dolfinx_field)
        field_function.x.scatter_forward()
        expected_coefficients = np.asarray(
            field_function.x.array,
            dtype=np.complex128,
        )
        lor_values = _physical_edge_line_integrals(
            topologies,
            edge_space,
            field,
        )
        observed = transfer.apply(lor_values)
        active_to_original = {
            int(active): int(original)
            for original, active in condensed.trace_constraints.original_to_active.items()
        }
        owner_original_dofs = np.asarray(
            [active_to_original[int(row)] for row in owner_rows],
            dtype=np.int64,
        )
        expected = np.concatenate(
            [
                expected_coefficients[recovery.interior_original_dofs]
                for recovery in ordered_recoveries
            ]
            + [expected_coefficients[owner_original_dofs]]
        )
        relative = np.linalg.norm(observed - expected) / max(
            np.linalg.norm(expected),
            np.finfo(float).tiny,
        )
        assert relative <= 1.0e-11
    finally:
        condensed.destroy()
