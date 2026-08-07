from __future__ import annotations

import numpy as np
import pytest
from mpi4py import MPI

from src.constraints.high_order_floquet_trace import (
    FloquetTopologyKey,
    FloquetTraceTopology,
)
from src.geometry.tetra_mesh_audit import mesh_coordinate_tolerance
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.physical_slab_two_level import (
    build_owner_local_slab_plan,
    collect_owner_local_fullspace_slab_cells,
    collect_owner_local_lor_transfer,
)
from src.test.test_224_task037_static_local_schur_action import _build_fixture


def _empty_floquet(degree: int) -> FloquetTraceTopology:
    return FloquetTraceTopology(
        key=FloquetTopologyKey(
            mesh_token=f"c1b2-empty-{degree}",
            element_family="N1curl",
            degree=degree,
        ),
        blocks=(),
        topology_build_seconds=0.0,
        bytes_sent=0,
        bytes_received=0,
    )


def _assert_common_audit(audit: dict[str, object], collector_audit: dict[str, object]) -> None:
    assert audit["parent_count"] == collector_audit["global_cell_count"]
    assert audit["parent_id_hash"] == collector_audit["cell_canonical_id_hash"]
    assert audit["owner_active_row_count"] == collector_audit[
        "owner_active_row_count"
    ]
    assert audit["owner_active_row_hash"] == collector_audit[
        "owner_active_row_hash"
    ]
    assert audit["partial_cell_count"] == collector_audit["partial_cell_count"]
    assert audit["full_rows"] == audit["interior_rows"] + audit["trace_rows"]
    assert audit["trace_offset"] == audit["interior_rows"]
    assert audit["trace_rows"] == audit["owner_active_row_count"]
    assert audit["missing_writer_count"] == 0
    assert audit["shared_trace_max_relative_error"] <= 1.0e-11
    assert audit["complete_trace_reconstruction_max_relative_error"] <= 1.0e-11
    assert audit["unique_parent_transfer_stencil_count"] < audit["parent_count"]
    assert audit["global_dense_T_retained"] is False


@pytest.mark.parametrize("comm", (MPI.COMM_WORLD,), ids=("world",))
def test_owner_local_lor_transfer_is_partition_invariant(comm):
    if comm.size not in (1, 2):
        pytest.skip("C1b2 fixture is qualified only for COMM_WORLD size 1 or 2")

    mesh, cell_tags, function_space, compiled = _build_fixture(comm)
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
        _, collector_audit = collect_owner_local_fullspace_slab_cells(
            condensed,
            plan,
            mesh,
            slab,
        )
        floquet = _empty_floquet(2)
        handle, audit = collect_owner_local_lor_transfer(
            condensed,
            plan,
            mesh,
            cell_tags,
            slab,
            degree=2,
            floquet_topology=floquet,
            phase_x=1.0 + 0.0j,
            phase_y=1.0 + 0.0j,
            coordinate_tolerance=mesh_coordinate_tolerance(mesh),
        )
        assert all(received == audit for received in comm.allgather(audit))
        _assert_common_audit(audit, collector_audit)
        assert audit["physical_edge_count"] >= audit["active_edge_count"]
        assert audit["periodic_slave_edge_count"] == 0
        assert audit["merged_periodic_block_count"] == 0
        assert audit["gathered_physical_identity_block_count"] == 0
        assert audit["gathered_physical_identity_payload_bytes"] == 0
        assert audit["high_order_coefficient_transform_gathered"] is False
        assert audit["descriptor_count"] == audit["parent_count"]
        assert audit["descriptor_numeric_payload_bytes"] > 0
        assert audit["retained_numeric_payload_lower_bound_bytes"] > 0

        owner = int(plan.slab_owners[slab])
        assert (handle is not None) == (comm.rank == owner)
        if comm.rank == owner:
            assert handle is not None
            rng = np.random.default_rng(2610)
            active_values = (
                rng.normal(size=int(audit["active_edge_count"]))
                + 1j * rng.normal(size=int(audit["active_edge_count"]))
            )
            full_values = handle.apply(active_values)
            assert np.array_equal(full_values, handle.apply(active_values))
            adjoint_input = (
                np.arange(int(audit["full_rows"]), dtype=np.float64)
                - 0.5j
            )
            left = np.vdot(full_values, adjoint_input)
            right = np.vdot(active_values, handle.apply_adjoint(adjoint_input))
            assert abs(left - right) / max(abs(left), abs(right), 1.0) <= 1.0e-11

        second, second_audit = collect_owner_local_lor_transfer(
            condensed,
            plan,
            mesh,
            cell_tags,
            slab,
            degree=2,
            floquet_topology=floquet,
            phase_x=1.0 + 0.0j,
            phase_y=1.0 + 0.0j,
            coordinate_tolerance=mesh_coordinate_tolerance(mesh),
        )
        assert second_audit == audit
        assert (second is not None) == (comm.rank == owner)
        if comm.rank == owner:
            assert second is not None
            assert np.array_equal(full_values, second.apply(active_values))
    finally:
        condensed.destroy()
