"""Focused T4 topology and facet-Robin action contracts."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import numpy as np
import pytest
import ufl
from mpi4py import MPI
from dolfinx import fem, mesh

from src.constraints.floquet_3d import build_double_floquet_mpc
from src.geometry.mesh_builder_3d import build_airbox_mesh_3d
from src.solvers.common_3d_solve import _create_nedelec_space
from src.solvers.common_3d_fields import incident_air_plane_wave_field
from src.solvers.fullspace_slab_interface import (
    FULLSPACE_SCALABLE_PROFILE,
    FirstOrderImpedanceTransmission,
    build_fullspace_slab_interface,
)
from src.solvers.fullspace_mpc_action import build_fullspace_mpc_form_action
from src.test.stage2_test_utils import stage4_block_config


def _real_fixture(tmp_path: Path, degree: int):
    comm = MPI.COMM_WORLD
    root = Path(comm.bcast(str(tmp_path) if comm.rank == 0 else None, root=0))
    cfg = replace(
        stage4_block_config(
            use_pml=False,
            pml_top_thickness=0.0,
            pml_bottom_thickness=0.0,
            mesh_target_size=50.0,
            stage4_dtn_order_policy="zero_order",
            incident_theta_deg=21.131,
            incident_phi_deg=33.690,
        ),
        nedelec_degree=degree,
    )
    mesh_data = build_airbox_mesh_3d(cfg, root / f"mesh-p{degree}-n{comm.size}")
    raw_V = _create_nedelec_space(mesh_data.mesh, cfg)
    floquet_data = build_double_floquet_mpc(raw_V, mesh_data, cfg)
    # The finalized MPC owns a distinct ghost layout.  Build the T4 field and
    # topology on that exact space so local MPC master indices and facet rows
    # share one layout on every rank.
    V = floquet_data.mpc.function_space
    topology = build_fullspace_slab_interface(V, mesh_data, floquet_data, cfg)
    return cfg, mesh_data, V, floquet_data, topology


def _analytic_field(topology, floquet_data, cfg, scale: complex = 1.0 + 0.0j):
    """Interpolate a coordinate-defined plane wave, then apply MPC once."""

    field = incident_air_plane_wave_field(topology.function_space, cfg)
    field.x.array[:] *= scale
    field.x.scatter_forward()
    floquet_data.mpc.homogenize(field)
    floquet_data.mpc.backsubstitution(field)
    field.x.scatter_forward()
    return field


def _copy_field_vector(field):
    vector = field.x.petsc_vec.duplicate()
    field.x.petsc_vec.copy(vector)
    return vector


def _authority_q(cfg, material_tag: int, direction: str) -> complex:
    assert direction in {"forward", "backward"}
    if material_tag == cfg.tags.air:
        refractive_index = complex(cfg.n_air)
    elif material_tag == cfg.tags.substrate:
        refractive_index = complex(cfg.substrate_index)
    elif material_tag == cfg.tags.grating:
        refractive_index = complex(cfg.grating_index)
    else:
        raise AssertionError(f"unsupported physical interface material tag {material_tag}")
    return complex(-1j * cfg.k0 * refractive_index)


def _oracle_material_pairs(topology) -> tuple[tuple[int, int, int], ...]:
    """Build the scalar-oracle inventory independently from candidate state."""

    local_pairs = {
        int(facet.interface_tag): (
            int(facet.lower_material.tag),
            int(facet.upper_material.tag),
        )
        for facet in topology.facets
    }
    reports = topology.mesh.comm.allgather(tuple(sorted(local_pairs.items())))
    global_pairs: dict[int, tuple[int, int]] = {}
    for report in reports:
        for tag, pair in report:
            previous = global_pairs.setdefault(int(tag), tuple(int(v) for v in pair))
            assert previous == tuple(int(v) for v in pair)
    return tuple(
        (tag, pair[0], pair[1]) for tag, pair in sorted(global_pairs.items())
    )


def _direct_scalar_robin_oracle(topology, source_field, test_field, direction: str) -> complex:
    """Fresh scalar facet quadrature; it never calls the candidate action."""

    tags = mesh.meshtags(
        topology.mesh,
        topology.mesh.topology.dim - 1,
        topology.interface_facet_indices.copy(),
        topology.interface_facet_tag_values.copy(),
    )
    u_plus = source_field("+")
    v_plus = test_field("+")
    u_t = ufl.as_vector((u_plus[0], u_plus[1], 0.0))
    v_t = ufl.as_vector((v_plus[0], v_plus[1], 0.0))
    dS = ufl.Measure("dS", domain=topology.mesh, subdomain_data=tags)
    pairs = _oracle_material_pairs(topology)
    expression = 0
    for tag, lower_tag, upper_tag in pairs:
        side_tag = upper_tag if direction == "forward" else lower_tag
        expression += _authority_q(topology.cfg, side_tag, direction) * ufl.inner(u_t, v_t) * dS(tag)
    local = fem.assemble_scalar(fem.form(expression))
    return complex(topology.mesh.comm.allreduce(local, op=MPI.SUM))


def _active_inner(topology, output, test_field) -> complex:
    output_values = np.asarray(output.getArray(readonly=True), dtype=np.complex128)
    test_values = np.asarray(
        test_field.x.petsc_vec.getArray(readonly=True), dtype=np.complex128
    )
    return complex(
        np.vdot(
            test_values[topology.owned_trace_local_rows],
            output_values[topology.owned_trace_local_rows],
        )
    )


def _global_norm(values: np.ndarray, comm: MPI.Comm) -> float:
    return float(
        np.sqrt(
            comm.allreduce(float(np.vdot(values, values).real), op=MPI.SUM)
        )
    )


def _slave_relation_error(field, floquet_data, comm: MPI.Comm) -> float:
    coefficients, offsets = floquet_data.mpc.coefficients()
    coefficients = np.asarray(coefficients, dtype=np.complex128)
    offsets = np.asarray(offsets, dtype=np.int64)
    values = np.asarray(field.x.array, dtype=np.complex128)
    errors = []
    for slave in np.asarray(floquet_data.mpc.slaves, dtype=np.int32):
        row = int(slave)
        masters = np.asarray(floquet_data.mpc.masters.links(row), dtype=np.int32)
        start, stop = int(offsets[row]), int(offsets[row + 1])
        errors.append(
            abs(values[row] - np.dot(coefficients[start:stop], values[masters]))
        )
    return float(comm.allreduce(max(errors, default=0.0), op=MPI.MAX))


def _reconstruct_and_check(topology, floquet_data, source_field, comm):
    reconstructed = fem.Function(topology.function_space)
    reconstructed.x.array[:] = source_field.x.array
    reconstructed.x.scatter_forward()
    before = reconstructed.x.array.copy()
    floquet_data.mpc.homogenize(reconstructed)
    floquet_data.mpc.backsubstitution(reconstructed)
    reconstructed.x.scatter_forward()
    after = reconstructed.x.array.copy()
    full_difference = float(comm.allreduce(np.max(np.abs(after - before)), op=MPI.MAX))
    assert full_difference <= 1.0e-13
    slave_rows = np.asarray(floquet_data.local_slave_dofs, dtype=np.int32)
    local_slave_difference = (
        float(np.max(np.abs(after[slave_rows] - before[slave_rows])))
        if slave_rows.size
        else 0.0
    )
    slave_difference = float(comm.allreduce(local_slave_difference, op=MPI.MAX))
    assert slave_difference <= 1.0e-13
    assert _slave_relation_error(reconstructed, floquet_data, comm) <= 1.0e-11
    return reconstructed


def _run_real_checks(tmp_path: Path, degree: int):
    cfg, _mesh_data, V, floquet_data, topology = _real_fixture(tmp_path, degree)
    comm = MPI.COMM_WORLD
    assert topology.profile == FULLSPACE_SCALABLE_PROFILE
    assert topology.canonical_global_count > 0
    assert topology.global_material_pairs
    assert set(topology.audit["interface_classifications"]) == {
        "homogeneous",
        "nonhomogeneous",
    }
    assert topology.audit["slave_rows_excluded"] is True
    assert topology.audit["numeric_allgather"] is False
    assert "metadata_allgather" not in topology.audit
    assert topology.audit["cell_tag_scope"] == (
        "local_owned_plus_ghost"
        if comm.size == 1
        else "owned_local_sparse_ghost_owner_exchange"
    )
    assert topology.audit["lower_upper_trace_maps"] is True
    assert not hasattr(topology, "slab_owner_ranks")
    assert all(
        owner in range(comm.size)
        for facet in topology.facets
        for owner in facet.trace_owners
    )
    assert all(
        local not in set(int(value) for value in floquet_data.local_slave_dofs)
        for facet in topology.facets
        for local in facet.trace_local_rows
    )

    rng = np.random.default_rng(272000 + degree)
    volume = np.asarray(
        rng.normal(size=topology.volume_owned_size)
        + 1j * rng.normal(size=topology.volume_owned_size),
        dtype=np.complex128,
    )
    trace = np.asarray(
        rng.normal(size=topology.owned_trace_count)
        + 1j * rng.normal(size=topology.owned_trace_count),
        dtype=np.complex128,
    )
    lhs = np.vdot(topology.restrict_volume_to_trace(volume), trace)
    rhs = np.vdot(volume, topology.prolong_trace_to_volume(trace))
    assert abs(lhs - rhs) <= 1.0e-11

    assert max(
        abs(value - 1.0)
        for value in (
            floquet_data.phase_x,
            floquet_data.phase_y,
            floquet_data.phase_corner,
        )
    ) > 1.0e-8
    source_field = _analytic_field(topology, floquet_data, cfg)
    source = _copy_field_vector(source_field)
    source_norm = _global_norm(
        np.asarray(
            source_field.x.array[topology.owned_trace_local_rows],
            dtype=np.complex128,
        ),
        comm,
    )
    assert source_norm > 0.0
    slave_norm = _global_norm(
        np.asarray(
            source_field.x.array[np.asarray(floquet_data.local_slave_dofs, dtype=np.int32)],
            dtype=np.complex128,
        ),
        comm,
    )
    assert slave_norm > 0.0

    assert _slave_relation_error(source_field, floquet_data, comm) <= 1.0e-11
    reconstructed_field = _reconstruct_and_check(
        topology, floquet_data, source_field, comm
    )
    reconstructed = _copy_field_vector(reconstructed_field)

    test_field = _analytic_field(topology, floquet_data, cfg, scale=0.6 - 0.2j)
    candidate = FirstOrderImpedanceTransmission(V, topology, mpc=floquet_data.mpc)
    _coefficients, offsets = floquet_data.mpc.coefficients()
    local_storage = int(
        floquet_data.mpc.function_space.dofmap.index_map.size_local
        + floquet_data.mpc.function_space.dofmap.index_map.num_ghosts
    )
    masters = np.concatenate(
        [
            np.asarray(floquet_data.mpc.masters.links(int(slave)), dtype=np.int32)
            for slave in np.asarray(floquet_data.mpc.slaves, dtype=np.int32)
        ]
    )
    assert len(offsets) - 1 <= local_storage
    assert masters.max(initial=-1) < local_storage
    try:
        for direction in ("forward", "backward"):
            observed = candidate.apply(source, direction)
            try:
                observed_norm = _global_norm(
                    np.asarray(observed.getArray(readonly=True), dtype=np.complex128),
                    comm,
                )
                assert observed_norm > 0.0
                expected_scalar = _direct_scalar_robin_oracle(
                    topology, source_field, test_field, direction
                )
                observed_scalar = _active_inner(topology, observed, test_field)
                observed_scalar = complex(comm.allreduce(observed_scalar, op=MPI.SUM))
                assert abs(observed_scalar - expected_scalar) <= 1.0e-11 * max(
                    abs(expected_scalar), 1.0
                )

                # A second, different source immediately follows the first;
                # the action buffer must be cleared by the bounded assembler.
                source_two_field = _analytic_field(
                    topology, floquet_data, cfg, scale=-0.35 + 0.4j
                )
                source_two = _copy_field_vector(source_two_field)
                try:
                    observed_two = candidate.apply(source_two, direction)
                    try:
                        expected_two = _direct_scalar_robin_oracle(
                            topology, source_two_field, test_field, direction
                        )
                        observed_two_scalar = _active_inner(
                            topology, observed_two, test_field
                        )
                        observed_two_scalar = complex(
                            comm.allreduce(observed_two_scalar, op=MPI.SUM)
                        )
                        assert abs(observed_two_scalar - expected_two) <= 1.0e-11 * max(
                            abs(expected_two), 1.0
                        )
                    finally:
                        observed_two.destroy()
                finally:
                    source_two.destroy()
                    source_two_field.x.petsc_vec.destroy()
            finally:
                observed.destroy()
        assert candidate.audit["action"] == "interior_facet_tangential_robin_weak_form"
        assert candidate.audit["global_aij_materialized"] is False
        assert candidate.audit["dense_interface_mass_materialized"] is False
        assert candidate.audit["dense_interface_schur_materialized"] is False
        assert candidate.audit["phase_application"] == "finalized_floquet_mpc_once"
    finally:
        candidate.destroy()
        source.destroy()
        reconstructed.destroy()
        source_field.x.petsc_vec.destroy()
        reconstructed_field.x.petsc_vec.destroy()
        test_field.x.petsc_vec.destroy()
    return topology


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="serial p2/p3 topology and facet action lane",
)
@pytest.mark.parametrize("degree", [2, 3])
def test_p2_p3_real_topology_adjoint_phase_and_facet_robin_serial(
    tmp_path: Path, degree: int
):
    _run_real_checks(tmp_path, degree)


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="MPI2 ownership, phase, adjoint, and facet action lane",
)
@pytest.mark.parametrize("degree", [2, 3])
def test_p2_p3_real_topology_adjoint_phase_and_facet_robin_mpi2(
    tmp_path: Path, degree: int
):
    topology = _run_real_checks(tmp_path, degree)
    comm = MPI.COMM_WORLD
    pair_identity = tuple(
        (
            int(tag),
            int(lower.tag),
            int(upper.tag),
            complex(lower.epsilon_r),
            complex(upper.epsilon_r),
            complex(lower.mu_r),
            complex(upper.mu_r),
        )
        for tag, lower, upper in topology.global_material_pairs
    )
    assert len(set(comm.allgather(pair_identity))) == 1
    assert len(set(comm.allgather(topology.canonical_sha256))) == 1
    assert len(set(comm.allgather(topology.canonical_global_count))) == 1
    assert comm.allreduce(len(topology.local_canonical_manifest), op=MPI.SUM) == (
        topology.canonical_global_count
    )
    assert set(int(value) for value in topology.owned_trace_global_rows).isdisjoint(
        int(value) for value in topology.ghost_trace_global_rows
    )
    assert all(
        int(owner) in {0, 1} for owner in topology.ghost_trace_owners
    )
    assert topology.audit["bounded_material_class_collective"] is True
    assert topology.audit["communication_plan_collective"] == "none_owner_local_owned_ghost_routes"
    assert topology.audit["canonical_identity_collective"] == "root_only_digest_count_gather_bcast"
    assert topology.audit["numeric_allgather"] is False
    assert isinstance(topology.neighbor_plan.forward_send_peers, tuple)
    assert isinstance(topology.neighbor_plan.forward_recv_peers, tuple)
    assert isinstance(topology.neighbor_plan.backward_send_peers, tuple)
    assert isinstance(topology.neighbor_plan.backward_recv_peers, tuple)


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 2,
    reason="MPI2 finalized-MPC metadata regression",
)
def test_mpi2_common_action_imported_ghost_master_metadata(
    tmp_path: Path,
):
    _cfg, _mesh_data, V, floquet_data, _topology = _real_fixture(tmp_path, 2)
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    action = build_fullspace_mpc_form_action(
        ufl.inner(u, v) * ufl.dx,
        V,
        mpc=floquet_data.mpc,
    )
    try:
        _coefficients, offsets = floquet_data.mpc.coefficients()
        index_map = floquet_data.mpc.function_space.dofmap.index_map
        local_storage = int(index_map.size_local + index_map.num_ghosts)
        masters = np.concatenate(
            [
                np.asarray(floquet_data.mpc.masters.links(int(slave)), dtype=np.int32)
                for slave in np.asarray(floquet_data.mpc.slaves, dtype=np.int32)
            ]
        )
        row_metadata_size = len(offsets) - 1
        assert local_storage >= row_metadata_size
        assert MPI.COMM_WORLD.allreduce(
            local_storage > row_metadata_size, op=MPI.LOR
        )
        imported_master_local = masters[masters >= row_metadata_size]
        assert MPI.COMM_WORLD.allreduce(
            imported_master_local.size > 0, op=MPI.LOR
        )

        def global_ids(local_rows):
            local_rows = np.asarray(local_rows, dtype=np.int32)
            result = np.empty(local_rows.size, dtype=np.int64)
            owned = local_rows < int(index_map.size_local)
            if np.any(owned):
                result[owned] = index_map.local_to_global(local_rows[owned])
            if np.any(~owned):
                result[~owned] = np.asarray(index_map.ghosts, dtype=np.int64)[
                    local_rows[~owned] - int(index_map.size_local)
                ]
            return result

        imported_master_global = global_ids(imported_master_local)
        local_slave_global = global_ids(floquet_data.mpc.slaves)
        global_slave_ids = {
            int(value)
            for packet in MPI.COMM_WORLD.allgather(local_slave_global.tolist())
            for value in packet
        }
        assert all(
            int(value) not in global_slave_ids
            for value in imported_master_global
        )
        assert masters.max(initial=-1) < local_storage
        assert action.audit["constraint_nnz_closes"] is True
    finally:
        action.destroy()
