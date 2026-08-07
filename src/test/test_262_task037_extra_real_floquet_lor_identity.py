from __future__ import annotations

import numpy as np
import pytest
import ufl
from dolfinx import fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.constraints.floquet_3d import build_double_floquet_mpc
from src.constraints.floquet_3d_high_order import floquet_geometry_tolerance
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.physical_slab_two_level import (
    build_owner_local_slab_plan,
    collect_owner_local_lor_transfer,
)
from src.test.test_46_task033_high_order_floquet_topology import (
    _fixed_target_fixture,
)


_SERIAL_AUTHORITY: dict[str, object] = {
    "parent_count": 18,
    "parent_id_hash": "14a51abf4a9df4acf82fcec8d29740b4dada11e97f2548634790efaaba2e4439",
    "physical_edge_count": 616,
    "physical_edge_keys_sha256": "d8e3f024f07d37e41aa6f658dcd3c9fc7c58711da896103ca686fd2d02215319",
    "active_edge_count": 480,
    "active_edge_keys_sha256": "a0e3f63dfe4be29f809870a48bb4c50f574cf4547b339fd5fa7e1dd3f53e2b67",
    "periodic_slave_edge_count": 136,
    "merged_periodic_block_count": 53,
    "matched_identity_block_count": 53,
    "periodic_relation_count": 136,
    "full_rows": 480,
    "interior_rows": 108,
    "trace_rows": 372,
    "complete_trace_row_count": 864,
}


def _real_floquet_condensed_fixture():
    cfg, mesh_data, function_space = _fixed_target_fixture(2, h_nm=1000.0)
    mesh_3d = mesh_data.mesh
    owned_cells = int(mesh_3d.topology.index_map(mesh_3d.topology.dim).size_local)
    cell_tags = mesh.meshtags(
        mesh_3d,
        mesh_3d.topology.dim,
        np.arange(owned_cells, dtype=np.int32),
        np.ones(owned_cells, dtype=np.int32),
    )
    u = ufl.TrialFunction(function_space)
    v = ufl.TestFunction(function_space)
    dx = ufl.Measure("dx", domain=mesh_3d, subdomain_data=cell_tags)
    compiled = fem.form(
        (
            ufl.inner(ufl.curl(u), ufl.curl(v))
            + PETSc.ScalarType(2.5 - 0.2j) * ufl.inner(u, v)
        )
        * dx(1)
    )
    floquet = build_double_floquet_mpc(function_space, mesh_data, cfg)
    condensed = build_unconstrained_assembly_time_condensation(
        compiled,
        function_space,
        cell_tags,
        mpc=floquet.mpc,
        materialize_global_matrix=False,
        retain_local_schur_for_matrix_free=True,
        retain_fullspace_slab_blocks_for_research=True,
    )
    return cfg, mesh_data, function_space, cell_tags, floquet, condensed


@pytest.mark.parametrize("comm", (MPI.COMM_WORLD,), ids=("world",))
def test_real_p2_floquet_c_to_lor_identity_is_partition_invariant(comm):
    if comm.size not in (1, 2):
        pytest.skip("test262 is qualified only for COMM_WORLD size 1 or 2")

    cfg, mesh_data, function_space, cell_tags, floquet, condensed = (
        _real_floquet_condensed_fixture()
    )
    try:
        topology = floquet.phase_independent_topology
        assert topology is not None
        blocks = topology.blocks
        assert {block.kind for block in blocks} >= {"x", "y", "corner"}
        assert {block.entity_kind for block in blocks} >= {"edge", "face"}
        assert all(block.has_physical_entity_identity for block in blocks)
        assert (
            abs(complex(cfg.floquet_phase_x) - 1.0) > 1.0e-12
            or abs(complex(cfg.floquet_phase_y) - 1.0) > 1.0e-12
        )

        plan = build_owner_local_slab_plan(
            condensed,
            mesh_data.mesh,
            domain_z=(cfg.domain_z_min, cfg.domain_z_max),
            num_slabs=1,
            overlap_fraction=0.0,
        )
        handle, topologies, audit = collect_owner_local_lor_transfer(
            condensed,
            plan,
            mesh_data.mesh,
            cell_tags,
            0,
            degree=2,
            floquet_topology=topology,
            phase_x=complex(floquet.phase_x),
            phase_y=complex(floquet.phase_y),
            coordinate_tolerance=floquet_geometry_tolerance(cfg),
        )
        assert all(received == audit for received in comm.allgather(audit))
        assert audit["parent_count"] > 0
        assert audit["partial_cell_count"] == 0
        assert audit["incomplete_trace_row_count"] == 0
        assert audit["complete_trace_row_count"] > 0
        assert audit["complete_trace_row_count"] == _SERIAL_AUTHORITY[
            "complete_trace_row_count"
        ]
        assert audit["complete_trace_reconstruction_max_relative_error"] <= 1.0e-11
        assert audit["shared_trace_max_relative_error"] <= 1.0e-11
        assert audit["merged_periodic_block_count"] > 0
        assert audit["matched_identity_block_count"] == audit[
            "merged_periodic_block_count"
        ]
        assert audit["periodic_relation_count"] > 0
        assert audit["periodic_slave_edge_count"] > 0
        assert audit["active_edge_count"] < audit["physical_edge_count"]
        assert audit["missing_writer_count"] == 0
        assert audit["gathered_physical_identity_block_count"] >= audit[
            "merged_periodic_block_count"
        ]
        assert audit["condensed_trace_matrix_materialized"] is False
        assert audit["retained_numeric_payload_lower_bound_bytes"] > 0
        assert audit["high_order_coefficient_transform_gathered"] is False
        assert (handle is not None) == (
            comm.rank == int(plan.slab_owners[0])
        )

        if comm.rank == int(plan.slab_owners[0]):
            assert handle is not None
            assert topologies is None
            rng = np.random.default_rng(2620)
            active_values = (
                rng.normal(size=int(audit["active_edge_count"]))
                + 1j * rng.normal(size=int(audit["active_edge_count"]))
            )
            full_values = handle.apply(active_values)
            assert np.array_equal(full_values, handle.apply(active_values))
            adjoint_input = (
                np.arange(int(audit["full_rows"]), dtype=np.float64)
                + 1j * np.arange(int(audit["full_rows"]), dtype=np.float64) / 5.0
            )
            left = np.vdot(full_values, adjoint_input)
            right = np.vdot(active_values, handle.apply_adjoint(adjoint_input))
            assert abs(left - right) / max(abs(left), abs(right), 1.0) <= 1.0e-11

        second, second_topologies, second_audit = collect_owner_local_lor_transfer(
            condensed,
            plan,
            mesh_data.mesh,
            cell_tags,
            0,
            degree=2,
            floquet_topology=topology,
            phase_x=complex(floquet.phase_x),
            phase_y=complex(floquet.phase_y),
            coordinate_tolerance=floquet_geometry_tolerance(cfg),
        )
        assert second_audit == audit
        assert second_topologies is None
        assert (second is not None) == (handle is not None)
        if comm.rank == int(plan.slab_owners[0]):
            assert second is not None
            assert np.array_equal(full_values, second.apply(active_values))

        authority = {
            key: audit[key]
            for key in (
                "parent_count",
                "parent_id_hash",
                "physical_edge_count",
                "physical_edge_keys_sha256",
                "active_edge_count",
                "active_edge_keys_sha256",
                "periodic_slave_edge_count",
                "merged_periodic_block_count",
                "matched_identity_block_count",
                "periodic_relation_count",
                "full_rows",
                "interior_rows",
                "trace_rows",
                "complete_trace_row_count",
            )
        }
        assert authority == _SERIAL_AUTHORITY
    finally:
        condensed.destroy()
