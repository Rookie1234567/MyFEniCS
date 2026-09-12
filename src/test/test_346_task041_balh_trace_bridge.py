"""Focused Task041 H1b tests for J/J^H and same-mesh P/P^H."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from dolfinx.la.petsc import create_vector
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import SimulationConfig3D
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.physical_balanced_same_mesh_transfer import (
    _owner_ranges,
    _owner_ranks,
    build_same_mesh_hcurl_owner_transfer,
)
from src.solvers.physical_balanced_trace_bridge import (
    extract_full_p6_to_active_trace,
    inject_active_residual_to_full_p6,
)

pytestmark = pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2, 8),
    reason="Task041 H1b bridge tests are focused on serial, MPI2, and one MPI8 audit",
)


def _boundary_tags(msh: mesh.Mesh, cfg: SimulationConfig3D) -> mesh.MeshTags:
    fdim = msh.topology.dim - 1
    records = (
        (cfg.tags.x_min, lambda x: np.isclose(x[0], cfg.x_min)),
        (cfg.tags.x_max, lambda x: np.isclose(x[0], cfg.x_max)),
        (cfg.tags.y_min, lambda x: np.isclose(x[1], cfg.y_min)),
        (cfg.tags.y_max, lambda x: np.isclose(x[1], cfg.y_max)),
        (cfg.tags.z_min, lambda x: np.isclose(x[2], cfg.domain_z_min)),
        (cfg.tags.z_max, lambda x: np.isclose(x[2], cfg.domain_z_max)),
    )
    facets = []
    values = []
    for tag, marker in records:
        found = mesh.locate_entities_boundary(msh, fdim, marker)
        facets.append(np.asarray(found, dtype=np.int32))
        values.append(np.full(len(found), tag, dtype=np.int32))
    indices = np.concatenate(facets) if facets else np.empty(0, dtype=np.int32)
    markers = np.concatenate(values) if values else np.empty(0, dtype=np.int32)
    order = np.argsort(indices)
    return mesh.meshtags(msh, fdim, indices[order], markers[order])


def _cell_tags(msh: mesh.Mesh) -> mesh.MeshTags:
    tdim = msh.topology.dim
    owned = int(msh.topology.index_map(tdim).size_local)
    return mesh.meshtags(
        msh,
        tdim,
        np.arange(owned, dtype=np.int32),
        np.ones(owned, dtype=np.int32),
    )


def _fixture_config(degree: int) -> SimulationConfig3D:
    return SimulationConfig3D(
        stage_case="stage4_block_grating",
        geometry_kind="rectangular_block_grating",
        lambda0=3.7,
        period_x=1.0,
        period_y=1.0,
        z_min=0.0,
        z_max=1.0,
        incident_theta_deg=28.0,
        incident_phi_deg=33.0,
        polarization_kind="s",
        nedelec_degree=degree,
        mesh_cell_type="hexahedron",
        mesh_target_size=2.0,
        use_floquet_xy=True,
        floquet_constraint_mode=f"topological_trace_p{degree}",
        grating_width_x=0.0,
        grating_width_y=0.0,
        grating_height=0.0,
    )


def _fill_owned_vector(vector: PETSc.Vec, seed: float) -> None:
    first, last = (int(value) for value in vector.getOwnershipRange())
    rows = np.arange(first, last, dtype=np.float64)
    vector.getArray()[:] = (
        seed + 1.0e-3 * rows + 1.0
        + 1j * (0.25 * seed + 2.0e-3 * rows + 0.5)
    ).astype(PETSc.ScalarType)
    vector.assemble()


def _fill_algebraic_vector(
    vector: PETSc.Vec,
    owned_slaves: np.ndarray,
    seed: float,
) -> None:
    _fill_owned_vector(vector, seed)
    local = vector.getArray()
    local[np.asarray(owned_slaves, dtype=np.int64)] = 0.0
    vector.assemble()


@pytest.fixture(scope="module")
def small_fe_fixture():
    comm = MPI.COMM_WORLD
    cfg6 = _fixture_config(6)
    cfg4 = _fixture_config(4)
    box = mesh.create_unit_cube(
        comm,
        2,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    facet_tags = _boundary_tags(box, cfg6)
    mesh_data = SimpleNamespace(mesh=box, facet_tags=facet_tags)
    fine_space = fem.functionspace(
        box,
        element("N1curl", box.basix_cell(), 6, dtype=default_real_type),
    )
    coarse_space = fem.functionspace(
        box,
        element("N1curl", box.basix_cell(), 4, dtype=default_real_type),
    )
    fine_floquet = build_double_floquet_mpc(fine_space, mesh_data, cfg6)
    coarse_floquet = build_double_floquet_mpc(coarse_space, mesh_data, cfg4)

    cell_tags = _cell_tags(box)
    u = ufl.TrialFunction(fine_space)
    v = ufl.TestFunction(fine_space)
    dx = ufl.Measure("dx", domain=box, subdomain_data=cell_tags)
    compiled = fem.form(
        (
            ufl.inner(ufl.curl(u), ufl.curl(v))
            + PETSc.ScalarType(1.0 + 0.2j) * ufl.inner(u, v)
        )
        * dx(1),
        dtype=PETSc.ScalarType,
        form_compiler_options={"quadrature_degree": 12},
    )
    condensed = build_unconstrained_assembly_time_condensation(
        compiled,
        fine_space,
        cell_tags,
        mpc=fine_floquet.mpc,
        retain_local_schur_for_matrix_free=True,
        materialize_global_matrix=False,
    )
    owner = build_same_mesh_hcurl_owner_transfer(
        fine_space,
        fine_floquet,
        coarse_space,
        coarse_floquet,
    )
    try:
        yield {
            "box": box,
            "fine_space": fine_space,
            "coarse_space": coarse_space,
            "fine_floquet": fine_floquet,
            "coarse_floquet": coarse_floquet,
            "condensed": condensed,
            "owner": owner,
            "cfg6": cfg6,
        }
    finally:
        owner.destroy()
        condensed.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size == 8,
    reason="the ordinary H1b bridge fixture is serial/MPI2-only",
)
def test_task041_h1b_j_and_jh_are_owned_trace_only(small_fe_fixture) -> None:
    data = small_fe_fixture
    condensed = data["condensed"]
    fine_space = data["fine_space"]
    full = create_vector(
        [(fine_space.dofmap.index_map, int(fine_space.dofmap.index_map_bs))]
    )
    _fill_owned_vector(full, 1.5)
    before = np.asarray(full.getArray(readonly=True), dtype=np.complex128).copy()
    active = extract_full_p6_to_active_trace(condensed, full)
    full_rhs = full.duplicate()
    try:
        active_original = np.asarray(
            condensed.trace_constraints.owned_active_original_dofs,
            dtype=np.int64,
        )
        first, _last = (int(value) for value in full.getOwnershipRange())
        expected_active = before[active_original - first]
        np.testing.assert_allclose(
            active.getArray(readonly=True), expected_active, atol=0.0, rtol=0.0
        )
        inject_active_residual_to_full_p6(condensed, active, full_rhs)
        expected_full = np.zeros_like(before)
        expected_full[active_original - first] = expected_active
        np.testing.assert_allclose(
            full_rhs.getArray(readonly=True), expected_full, atol=0.0, rtol=0.0
        )
        np.testing.assert_array_equal(full.getArray(readonly=True), before)
        assert np.all(
            full_rhs.getArray(readonly=True)[
                np.setdiff1d(
                    np.arange(len(before), dtype=np.int64),
                    active_original - first,
                    assume_unique=False,
                )
            ]
            == 0.0
        )
    finally:
        active.destroy()
        full_rhs.destroy()
        full.destroy()


def test_task041_h1b_empty_owner_range_is_supported_on_one_cell_mesh() -> None:
    if MPI.COMM_WORLD.size != 2:
        pytest.skip("empty-owner check uses a two-rank one-cell partition")
    box = mesh.create_unit_cube(
        MPI.COMM_WORLD,
        1,
        1,
        1,
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    cfg6 = _fixture_config(6)
    cfg4 = _fixture_config(4)
    mesh_data = SimpleNamespace(mesh=box, facet_tags=_boundary_tags(box, cfg6))
    fine_space = fem.functionspace(
        box,
        element("N1curl", box.basix_cell(), 6, dtype=default_real_type),
    )
    coarse_space = fem.functionspace(
        box,
        element("N1curl", box.basix_cell(), 4, dtype=default_real_type),
    )
    fine_floquet = build_double_floquet_mpc(fine_space, mesh_data, cfg6)
    coarse_floquet = build_double_floquet_mpc(coarse_space, mesh_data, cfg4)
    owner = build_same_mesh_hcurl_owner_transfer(
        fine_space,
        fine_floquet,
        coarse_space,
        coarse_floquet,
    )
    ranges = _owner_ranges(fine_space.dofmap.index_map, MPI.COMM_WORLD)
    assert any(first == last for first, last in ranges)
    global_rows = int(fine_space.dofmap.index_map.size_global)
    owners = _owner_ranks(
        np.asarray((0, global_rows - 1), dtype=np.int64),
        ranges,
    )
    assert np.all((owners >= 0) & (owners < MPI.COMM_WORLD.size))
    coarse = create_vector(
        [
            (
                coarse_space.dofmap.index_map,
                int(coarse_space.dofmap.index_map_bs),
            )
        ]
    )
    fine_probe = create_vector(
        [
            (
                fine_space.dofmap.index_map,
                int(fine_space.dofmap.index_map_bs),
            )
        ]
    )
    outputs = []
    coarse_before = None
    fine_probe_before = None
    coarse_difference = None
    fine_difference = None
    try:
        coarse_slaves = np.asarray(owner._coarse_slaves, dtype=np.int64)
        fine_slaves = np.asarray(owner._fine_slaves, dtype=np.int64)
        _fill_algebraic_vector(coarse, coarse_slaves, 0.75)
        coarse_before = coarse.duplicate()
        coarse.copy(coarse_before)
        fine_output = owner.apply_primal(coarse)
        outputs.append(fine_output)
        _fill_algebraic_vector(fine_probe, fine_slaves, -0.5)
        fine_probe_before = fine_probe.duplicate()
        fine_probe.copy(fine_probe_before)
        coarse_output = owner.apply_adjoint(fine_probe)
        outputs.append(coarse_output)

        fine_slave_values = np.asarray(fine_output.getArray(readonly=True))[
            fine_slaves
        ]
        fine_slave_max = float(
            np.max(np.abs(fine_slave_values)) if fine_slave_values.size else 0.0
        )
        coarse_slave_values = np.asarray(coarse_output.getArray(readonly=True))[
            coarse_slaves
        ]
        coarse_slave_max = float(
            np.max(np.abs(coarse_slave_values))
            if coarse_slave_values.size
            else 0.0
        )
        assert MPI.COMM_WORLD.allreduce(fine_slave_max, op=MPI.MAX) == 0.0
        assert MPI.COMM_WORLD.allreduce(coarse_slave_max, op=MPI.MAX) == 0.0
        assert coarse.norm() > 0.0
        assert fine_probe.norm() > 0.0
        assert fine_output.norm() > 0.0
        assert coarse_output.norm() > 0.0

        dot_lhs = fine_output.dot(fine_probe)
        dot_rhs = coarse.dot(coarse_output)
        dot_scale = max(abs(dot_lhs), abs(dot_rhs), np.finfo(float).tiny)
        assert abs(dot_lhs - dot_rhs) / dot_scale <= 1.0e-10

        coarse_difference = coarse.duplicate()
        coarse.copy(coarse_difference)
        coarse_difference.axpy(PETSc.ScalarType(-1.0), coarse_before)
        fine_difference = fine_probe.duplicate()
        fine_probe.copy(fine_difference)
        fine_difference.axpy(PETSc.ScalarType(-1.0), fine_probe_before)
        assert coarse_difference.norm() == 0.0
        assert fine_difference.norm() == 0.0
    finally:
        for vector in outputs:
            vector.destroy()
        coarse.destroy()
        fine_probe.destroy()
        if coarse_before is not None:
            coarse_before.destroy()
        if fine_probe_before is not None:
            fine_probe_before.destroy()
        if coarse_difference is not None:
            coarse_difference.destroy()
        if fine_difference is not None:
            fine_difference.destroy()
        owner.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size == 8,
    reason="the ordinary H1b bridge fixture is serial/MPI2-only",
)
def test_task041_h1b_same_mesh_p_and_ph_conjugacy_and_alternation(
    small_fe_fixture,
) -> None:
    data = small_fe_fixture
    owner = data["owner"]
    fine_space = data["fine_space"]
    coarse_space = data["coarse_space"]
    cfg6 = data["cfg6"]
    assert abs(complex(cfg6.floquet_phase_x) - 1.0) > 1.0e-3
    assert abs(complex(cfg6.floquet_phase_y) - 1.0) > 1.0e-3
    assert owner.audit["global_transfer_matrix"] is False
    assert owner.audit["numeric_allgather"] is False

    coarse_slaves = np.asarray(owner._coarse_slaves, dtype=np.int64)
    fine_slaves = np.asarray(owner._fine_slaves, dtype=np.int64)
    q1 = create_vector(
        [(coarse_space.dofmap.index_map, int(coarse_space.dofmap.index_map_bs))]
    )
    q2 = q1.duplicate()
    fine_probe = create_vector(
        [(fine_space.dofmap.index_map, int(fine_space.dofmap.index_map_bs))]
    )
    outputs = []
    coarse_field = fem.Function(data["coarse_floquet"].mpc.function_space)
    fine_oracle = fem.Function(data["fine_floquet"].mpc.function_space)
    try:
        _fill_algebraic_vector(q1, coarse_slaves, 2.0)
        q1_before = np.asarray(q1.getArray(readonly=True), dtype=np.complex128).copy()
        _fill_algebraic_vector(q2, coarse_slaves, 7.0)
        p_q1 = owner.apply_primal(q1)
        outputs.append(p_q1)
        p_q2 = owner.apply_primal(q2)
        outputs.append(p_q2)
        p_q1_repeat = owner.apply_primal(q1)
        outputs.append(p_q1_repeat)
        np.testing.assert_array_equal(q1.getArray(readonly=True), q1_before)
        np.testing.assert_allclose(
            p_q1.getArray(readonly=True),
            p_q1_repeat.getArray(readonly=True),
            atol=1.0e-12,
            rtol=1.0e-12,
        )
        assert not np.allclose(
            p_q1.getArray(readonly=True), p_q2.getArray(readonly=True)
        )
        assert np.all(p_q1.getArray(readonly=True)[fine_slaves] == 0.0)
        assert np.all(p_q2.getArray(readonly=True)[fine_slaves] == 0.0)

        q1.copy(coarse_field.x.petsc_vec)
        coarse_field.x.scatter_forward()
        data["coarse_floquet"].mpc.homogenize(coarse_field)
        coarse_field.x.scatter_forward()
        data["coarse_floquet"].mpc.backsubstitution(coarse_field)
        coarse_field.x.scatter_forward()
        fine_oracle.interpolate(coarse_field)
        fine_oracle.x.scatter_forward()
        data["fine_floquet"].mpc.homogenize(fine_oracle)
        fine_oracle.x.scatter_forward()
        np.testing.assert_allclose(
            p_q1.getArray(readonly=True),
            fine_oracle.x.petsc_vec.getArray(readonly=True),
            atol=1.0e-11,
            rtol=1.0e-11,
        )

        _fill_algebraic_vector(fine_probe, fine_slaves, 11.0)
        fine_probe_before = np.asarray(
            fine_probe.getArray(readonly=True), dtype=np.complex128
        ).copy()
        ph = owner.apply_adjoint(fine_probe)
        outputs.append(ph)
        lhs = p_q1.dot(fine_probe)
        rhs = q1.dot(ph)
        denominator = max(abs(lhs), abs(rhs), np.finfo(float).tiny)
        assert abs(lhs - rhs) / denominator <= 1.0e-10
        assert np.all(ph.getArray(readonly=True)[coarse_slaves] == 0.0)
        np.testing.assert_array_equal(
            fine_probe.getArray(readonly=True), fine_probe_before
        )
    finally:
        for vector in outputs:
            vector.destroy()
        q1.destroy()
        q2.destroy()
        fine_probe.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 8,
    reason="remote-master finalized MPC regression is MPI8-only",
)
def test_task041_h1b_mpi8_remote_master_ghost_uses_finalized_oracle() -> None:
    comm = MPI.COMM_WORLD
    cfg6 = _fixture_config(6)
    cfg4 = _fixture_config(4)
    box = mesh.create_unit_cube(
        comm,
        4,
        2,
        2,
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    mesh_data = SimpleNamespace(mesh=box, facet_tags=_boundary_tags(box, cfg6))
    fine_space = fem.functionspace(
        box,
        element("N1curl", box.basix_cell(), 6, dtype=default_real_type),
    )
    coarse_space = fem.functionspace(
        box,
        element("N1curl", box.basix_cell(), 4, dtype=default_real_type),
    )
    fine_floquet = None
    coarse_floquet = None
    owner = None
    q1 = None
    q1_before = None
    fine_probe = None
    fine_probe_before = None
    p_q1 = None
    ph_probe = None
    coarse_field = None
    fine_oracle = None
    try:
        fine_floquet = build_double_floquet_mpc(fine_space, mesh_data, cfg6)
        coarse_floquet = build_double_floquet_mpc(coarse_space, mesh_data, cfg4)
        owner = build_same_mesh_hcurl_owner_transfer(
            fine_space,
            fine_floquet,
            coarse_space,
            coarse_floquet,
        )
        old_storage_short = False
        new_storage_closed = True
        for space, floquet in (
            (coarse_space, coarse_floquet),
            (fine_space, fine_floquet),
        ):
            old_map = space.dofmap.index_map
            new_map = floquet.mpc.function_space.dofmap.index_map
            old_storage = int(old_map.size_local + old_map.num_ghosts)
            new_storage = int(new_map.size_local + new_map.num_ghosts)
            master_links = [
                np.asarray(floquet.mpc.masters.links(int(slave)), dtype=np.int64)
                for slave in np.asarray(floquet.mpc.slaves, dtype=np.int64)
            ]
            masters = (
                np.concatenate(master_links)
                if master_links
                else np.empty(0, dtype=np.int64)
            )
            master_max = int(masters.max()) if masters.size else -1
            old_storage_short |= master_max >= old_storage
            new_storage_closed &= master_max < new_storage
        old_storage_short_count = int(
            comm.allreduce(int(old_storage_short), op=MPI.SUM)
        )
        assert old_storage_short_count >= 1
        assert bool(comm.allreduce(new_storage_closed, op=MPI.LAND))

        coarse_slaves = np.asarray(owner._coarse_slaves, dtype=np.int64)
        fine_slaves = np.asarray(owner._fine_slaves, dtype=np.int64)
        q1 = create_vector(
            [
                (
                    coarse_space.dofmap.index_map,
                    int(coarse_space.dofmap.index_map_bs),
                )
            ]
        )
        fine_probe = create_vector(
            [
                (
                    fine_space.dofmap.index_map,
                    int(fine_space.dofmap.index_map_bs),
                )
            ]
        )
        _fill_algebraic_vector(q1, coarse_slaves, 1.75)
        _fill_algebraic_vector(fine_probe, fine_slaves, -0.875)
        q1_before = q1.duplicate()
        q1.copy(q1_before)
        fine_probe_before = fine_probe.duplicate()
        fine_probe.copy(fine_probe_before)
        p_q1 = owner.apply_primal(q1)
        ph_probe = owner.apply_adjoint(fine_probe)

        coarse_field = fem.Function(coarse_floquet.mpc.function_space)
        fine_oracle = fem.Function(fine_floquet.mpc.function_space)
        q1.copy(coarse_field.x.petsc_vec)
        coarse_field.x.scatter_forward()
        coarse_floquet.mpc.homogenize(coarse_field)
        coarse_field.x.scatter_forward()
        coarse_floquet.mpc.backsubstitution(coarse_field)
        coarse_field.x.scatter_forward()
        fine_oracle.interpolate(coarse_field)
        fine_oracle.x.scatter_forward()
        fine_floquet.mpc.homogenize(fine_oracle)
        fine_oracle.x.scatter_forward()

        p_values = np.asarray(p_q1.getArray(readonly=True), dtype=np.complex128)
        oracle_values = np.asarray(
            fine_oracle.x.petsc_vec.getArray(readonly=True),
            dtype=np.complex128,
        )
        fine_owned = int(fine_space.dofmap.index_map.size_local)
        assert p_values.size == fine_owned
        assert oracle_values.size == fine_owned
        difference_local = float(
            np.vdot(p_values - oracle_values, p_values - oracle_values).real
        )
        difference = float(np.sqrt(comm.allreduce(difference_local, op=MPI.SUM)))
        p_norm = float(p_q1.norm())
        relative = difference / max(p_norm, 1.0e-30)
        assert np.isfinite(relative)
        assert relative <= 1.0e-10

        lhs = p_q1.dot(fine_probe)
        rhs = q1.dot(ph_probe)
        dot_relative = abs(lhs - rhs) / max(
            abs(lhs), abs(rhs), np.finfo(float).tiny
        )
        assert dot_relative <= 1.0e-10
        assert p_q1.norm() > 0.0
        assert ph_probe.norm() > 0.0
        assert q1.norm() > 0.0
        assert fine_probe.norm() > 0.0
        assert np.all(p_values[fine_slaves] == 0.0)
        assert np.all(
            np.asarray(ph_probe.getArray(readonly=True))[coarse_slaves] == 0.0
        )
        np.testing.assert_array_equal(q1.getArray(readonly=True), q1_before.getArray(readonly=True))
        np.testing.assert_array_equal(
            fine_probe.getArray(readonly=True), fine_probe_before.getArray(readonly=True)
        )
        if comm.rank == 0:
            print(
                "task041 MPI8 finalized-MPC oracle: "
                f"relative={relative:.16e}, dot_relative={dot_relative:.16e}, "
                f"old_short_ranks={old_storage_short_count}",
                flush=True,
            )
    finally:
        for vector in (p_q1, ph_probe, q1_before, fine_probe_before, q1, fine_probe):
            if vector is not None:
                vector.destroy()
        del coarse_field, fine_oracle
        if owner is not None:
            owner.destroy()
        del owner, fine_floquet, coarse_floquet, fine_space, coarse_space, box
