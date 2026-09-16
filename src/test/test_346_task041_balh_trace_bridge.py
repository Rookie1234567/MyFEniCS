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

from benchmarks.task041_exact_side_workflow import (
    _task041_communicator_identity,
    _task041_held_petsc_identity,
    _task041_mpc_layout_metadata,
    _task041_space_layout_metadata,
    _task041_stream_array_metadata,
)
from src.common.config_3d import SimulationConfig3D
from src.constraints.floquet_3d import build_double_floquet_mpc
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.physical_balanced_same_mesh_transfer import (
    ROW_CONSISTENCY_LIMIT,
    _apply_conjugate_transpose_vector,
    _owner_ranges,
    _owner_ranks,
    _resolve_owner_candidates,
    _resolve_owner_candidates_batched,
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


def _assert_layout_api_helpers(
    transfer,
    fine_space,
    coarse_space,
    fine_mpc,
    coarse_mpc,
    mesh_obj,
    petsc_vector,
    expected_comm_size: int,
) -> None:
    fine_layout = _task041_space_layout_metadata(
        "transfer.fine_space", fine_space
    )
    coarse_layout = _task041_space_layout_metadata(
        "transfer.coarse_space", coarse_space
    )
    fine_mpc_layout = _task041_mpc_layout_metadata(
        "fine_floquet.mpc", fine_mpc
    )
    coarse_mpc_layout = _task041_mpc_layout_metadata(
        "coarse_floquet.mpc", coarse_mpc
    )
    geometry_layout = _task041_stream_array_metadata(
        "mesh.geometry.x", np.asarray(mesh_obj.geometry.x)
    )
    geometry_dofmap_layout = _task041_stream_array_metadata(
        "mesh.geometry.dofmap", np.asarray(mesh_obj.geometry.dofmap)
    )
    communicator = _task041_communicator_identity(
        "transfer.comm", transfer.comm
    )
    vector_identity = _task041_held_petsc_identity("probe", petsc_vector)
    assert fine_layout["dofmap"]["map"]["hash_status"].startswith("measured")
    assert coarse_layout["dofmap"]["map"]["hash_status"].startswith("measured")
    assert fine_mpc_layout["slaves"]["hash_status"].startswith("measured")
    assert coarse_mpc_layout["slaves"]["hash_status"].startswith("measured")
    assert geometry_layout["hash_status"].startswith("measured")
    assert geometry_dofmap_layout["hash_status"].startswith("measured")
    assert communicator["size"] == expected_comm_size
    assert vector_identity["petsc_handle"] > 0


class _SerialReduction:
    def __init__(self):
        self.values = []

    def allreduce(self, value, op=None):
        self.values.append(value)
        return value


class _FixedReduction:
    def __init__(self, value):
        self.value = value

    def allreduce(self, value, op=None):
        return self.value


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


@pytest.mark.parametrize(
    "optimization_profile",
    (None, "task041_schur_speed_v2"),
    ids=("legacy", "task041_schur_speed_v2"),
)
def test_task041_h1b_empty_owner_range_is_supported_on_one_cell_mesh(
    optimization_profile: str | None,
) -> None:
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
        optimization_profile=optimization_profile,
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
        _assert_layout_api_helpers(
            owner,
            fine_space,
            coarse_space,
            fine_floquet.mpc,
            coarse_floquet.mpc,
            box,
            coarse,
            expected_comm_size=2,
        )
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


@pytest.mark.parametrize(
    ("defect", "raises"),
    ((5.0e-12, False), (2.0e-11, True)),
)
def test_task041_h1b_batched_owner_groups_match_legacy_duplicate_gate(
    defect: float,
    raises: bool,
) -> None:
    ids = np.asarray((0, 0, 0, 2, 2, 2, 5), dtype=np.uint64)
    values = np.asarray(
        (
            2.0 + 3.0j,
            2.0 + 3.0j,
            2.0 + 3.0j,
            7.0 - 1.0j,
            7.0 - 1.0j,
            7.0 - 1.0j,
            -1.0 + 0.5j,
        ),
        dtype=np.complex128,
    )
    values[2] += defect
    source_ranks = np.asarray((1, 0, 2, 2, 1, 0, 0), dtype=np.int32)
    snapshots = (ids.copy(), values.copy(), source_ranks.copy())
    comm = _SerialReduction()
    if raises:
        with pytest.raises(RuntimeError):
            _resolve_owner_candidates(
                ids, values, source_ranks, owner_rank=0, comm=comm
            )
        with pytest.raises(RuntimeError):
            _resolve_owner_candidates_batched(
                ids, values, source_ranks, owner_rank=0, comm=comm
            )
    else:
        legacy = _resolve_owner_candidates(
            ids, values, source_ranks, owner_rank=0, comm=comm
        )
        batched = _resolve_owner_candidates_batched(
            ids, values, source_ranks, owner_rank=0, comm=comm
        )
        np.testing.assert_array_equal(batched[0], legacy[0])
        np.testing.assert_array_equal(batched[1], legacy[1])
        assert batched[2] == legacy[2]
        assert batched[3] == legacy[3]
    np.testing.assert_array_equal(ids, snapshots[0])
    np.testing.assert_array_equal(values, snapshots[1])
    np.testing.assert_array_equal(source_ranks, snapshots[2])


@pytest.mark.parametrize("value", (np.nan + 0.0j, np.inf + 0.0j))
def test_task041_h1b_batched_owner_groups_reject_nonfinite_values(
    value, monkeypatch
) -> None:
    import src.solvers.physical_balanced_same_mesh_transfer as transfer_module

    monkeypatch.setattr(transfer_module, "_OWNER_RESOLUTION_CHUNK_ROWS", 1)
    ids = np.asarray((0, 0, 1), dtype=np.uint64)
    values = np.asarray(
        (1.0 + 0.5j, value, 2.0 - 0.25j), dtype=np.complex128
    )
    source_ranks = np.asarray((0, 1, 0), dtype=np.int32)
    comm = _SerialReduction()
    with pytest.raises(RuntimeError):
        _resolve_owner_candidates_batched(
            ids,
            values,
            source_ranks,
            owner_rank=0,
            comm=comm,
        )
    assert len(comm.values) == 1
    assert np.isposinf(comm.values[0])


def test_task041_h1b_batched_owner_groups_accept_single_group_and_empty_packet() -> None:
    single = _resolve_owner_candidates_batched(
        np.asarray((7, 7, 7), dtype=np.uint64),
        np.asarray((2.0 + 1.0j, 2.0 + 1.0j, 2.0 + 1.0j)),
        np.asarray((2, 0, 1), dtype=np.int32),
        owner_rank=0,
        comm=_SerialReduction(),
    )
    np.testing.assert_array_equal(single[0], np.asarray((7,), dtype=np.uint64))
    np.testing.assert_array_equal(single[1], np.asarray((2.0 + 1.0j,)))
    assert single[2:] == (0.0, 3)

    empty = _resolve_owner_candidates_batched(
        np.empty(0, dtype=np.uint64),
        np.empty(0, dtype=np.complex128),
        np.empty(0, dtype=np.int32),
        owner_rank=0,
        comm=_SerialReduction(),
    )
    assert empty[0].size == 0
    assert empty[1].size == 0
    assert empty[2:] == (0.0, 0)


def test_task041_h1b_batched_owner_groups_reject_missing_owner_like_legacy() -> None:
    ids = np.asarray((0, 0, 1), dtype=np.uint64)
    values = np.asarray((1.0 + 0.5j, 1.0 + 0.5j, 2.0 - 0.25j))
    source_ranks = np.asarray((1, 1, 1), dtype=np.int32)
    comm = _SerialReduction()
    with pytest.raises(ValueError):
        _resolve_owner_candidates(ids, values, source_ranks, 0, comm)
    with pytest.raises(ValueError):
        _resolve_owner_candidates_batched(ids, values, source_ranks, 0, comm)


def test_task041_h1b_batched_owner_groups_cover_last_and_cross_chunk(monkeypatch) -> None:
    import src.solvers.physical_balanced_same_mesh_transfer as transfer_module

    monkeypatch.setattr(transfer_module, "_OWNER_RESOLUTION_CHUNK_ROWS", 3)
    ids = np.asarray((4, 4, 4, 4, 9, 9, 9, 12), dtype=np.uint64)
    values = np.asarray(
        (2.0 + 1.0j, 2.0 + 1.0j, 2.0 + 1.0j, 2.0 + 1.0j,
         -1.0 + 0.25j, -1.0 + 0.25j, -1.0 + 0.25j, 4.0 - 2.0j),
        dtype=np.complex128,
    )
    source_ranks = np.asarray((1, 0, 1, 1, 1, 0, 1, 0), dtype=np.int32)
    expected = _resolve_owner_candidates(
        ids, values, source_ranks, owner_rank=0, comm=_SerialReduction()
    )
    actual = _resolve_owner_candidates_batched(
        ids, values, source_ranks, owner_rank=0, comm=_SerialReduction()
    )
    np.testing.assert_array_equal(actual[0], expected[0])
    np.testing.assert_array_equal(actual[1], expected[1])
    assert actual[2:] == expected[2:]

    conflicting = values.copy()
    # Group 9 starts in the second chunk and its non-canonical candidate is
    # in the final chunk; that later chunk must still be checked.
    conflicting[6] += 2.0e-11
    with pytest.raises(RuntimeError):
        _resolve_owner_candidates_batched(
            ids,
            conflicting,
            source_ranks,
            owner_rank=0,
            comm=_SerialReduction(),
        )


def test_task041_h1b_batched_empty_packet_applies_global_duplicate_gate() -> None:
    with pytest.raises(RuntimeError):
        _resolve_owner_candidates_batched(
            np.empty(0, dtype=np.uint64),
            np.empty(0, dtype=np.complex128),
            np.empty(0, dtype=np.int32),
            owner_rank=0,
            comm=_FixedReduction(2.0 * ROW_CONSISTENCY_LIMIT),
        )


def test_task041_h1b_complex_adjoint_helper_matches_explicit_matrix_adjoint() -> None:
    matrix = np.asarray(
        (
            (1.0 + 0.5j, -2.0 + 1.25j),
            (0.75 - 0.25j, 3.0 - 0.5j),
            (-1.5 + 2.0j, 0.25 + 0.875j),
        ),
        dtype=np.complex128,
    )
    values = np.asarray((0.5 - 1.0j, -2.0 + 0.25j, 1.5 + 0.75j))
    matrix_before = matrix.copy()
    values_before = values.copy()
    actual = _apply_conjugate_transpose_vector(matrix, values)
    expected = matrix.conj().T @ values
    np.testing.assert_allclose(actual, expected, atol=0.0, rtol=1.0e-14)
    np.testing.assert_array_equal(matrix, matrix_before)
    np.testing.assert_array_equal(values, values_before)


@pytest.mark.skipif(
    MPI.COMM_WORLD.size == 8,
    reason="the V2 transfer equivalence fixture is serial/MPI2-only",
)
def test_task041_h1b_v2_owner_and_adjoint_match_legacy_with_alternation(
    small_fe_fixture,
    monkeypatch,
) -> None:
    data = small_fe_fixture
    import src.solvers.physical_balanced_same_mesh_transfer as transfer_module

    kernel_calls = {
        "legacy_owner": 0,
        "batched_owner": 0,
        "conjugate_transpose_identity": 0,
    }

    legacy_resolver = transfer_module._resolve_owner_candidates
    batched_resolver = transfer_module._resolve_owner_candidates_batched
    conjugate_transpose = transfer_module._apply_conjugate_transpose_vector

    def traced_legacy(*args, **kwargs):
        kernel_calls["legacy_owner"] += 1
        return legacy_resolver(*args, **kwargs)

    def traced_batched(*args, **kwargs):
        kernel_calls["batched_owner"] += 1
        return batched_resolver(*args, **kwargs)

    def traced_conjugate_transpose(*args, **kwargs):
        kernel_calls["conjugate_transpose_identity"] += 1
        return conjugate_transpose(*args, **kwargs)

    monkeypatch.setattr(transfer_module, "_resolve_owner_candidates", traced_legacy)
    monkeypatch.setattr(
        transfer_module, "_resolve_owner_candidates_batched", traced_batched
    )
    monkeypatch.setattr(
        transfer_module,
        "_apply_conjugate_transpose_vector",
        traced_conjugate_transpose,
    )
    owner = build_same_mesh_hcurl_owner_transfer(
        data["fine_space"],
        data["fine_floquet"],
        data["coarse_space"],
        data["coarse_floquet"],
        optimization_profile="task041_schur_speed_v2",
    )
    assert owner.audit["optimization_profile"] == "task041_schur_speed_v2"
    assert owner.audit["default_execution_variant"] == "optimized"
    assert owner.audit["owner_resolution"] == "numpy_batched"
    assert owner.audit["adjoint_cell_apply"] == (
        "conjugate_transpose_identity"
    )

    coarse_space = data["coarse_space"]
    fine_space = data["fine_space"]
    coarse_slaves = np.asarray(owner._coarse_slaves, dtype=np.int64)
    fine_slaves = np.asarray(owner._fine_slaves, dtype=np.int64)
    q1 = create_vector(
        [(coarse_space.dofmap.index_map, int(coarse_space.dofmap.index_map_bs))]
    )
    q2 = q1.duplicate()
    fine_probe1 = create_vector(
        [(fine_space.dofmap.index_map, int(fine_space.dofmap.index_map_bs))]
    )
    fine_probe2 = fine_probe1.duplicate()
    outputs = []
    p_difference = None
    ph_difference = None
    try:
        _assert_layout_api_helpers(
            owner,
            fine_space,
            coarse_space,
            data["fine_floquet"].mpc,
            data["coarse_floquet"].mpc,
            data["box"],
            q1,
            expected_comm_size=MPI.COMM_WORLD.size,
        )
        _fill_algebraic_vector(q1, coarse_slaves, 2.5)
        _fill_algebraic_vector(q2, coarse_slaves, -1.25)
        _fill_algebraic_vector(fine_probe1, fine_slaves, 4.0)
        _fill_algebraic_vector(fine_probe2, fine_slaves, -2.0)
        q1_before = np.asarray(q1.getArray(readonly=True), dtype=np.complex128).copy()
        fine_probe1_before = np.asarray(
            fine_probe1.getArray(readonly=True), dtype=np.complex128
        ).copy()

        with owner.variant_context("legacy"):
            legacy_p = owner.apply_primal(q1)
            legacy_p_facts = owner.last_apply_facts
            legacy_ph = owner.apply_adjoint(fine_probe1)
            legacy_ph_facts = owner.last_apply_facts
        legacy_counts = dict(kernel_calls)
        assert legacy_counts["legacy_owner"] > 0
        assert legacy_counts["batched_owner"] == 0
        assert legacy_counts["conjugate_transpose_identity"] == 0
        with (
            pytest.raises(RuntimeError, match="cannot change while active"),
            owner.variant_context("legacy"),
            owner.variant_context("optimized"),
        ):
            pass
        with owner.variant_context("optimized"):
            optimized_p = owner.apply_primal(q1)
            optimized_p2 = owner.apply_primal(q2)
            optimized_ph = owner.apply_adjoint(fine_probe1)
            optimized_ph2 = owner.apply_adjoint(fine_probe2)
        optimized_counts = dict(kernel_calls)
        assert optimized_counts["legacy_owner"] == legacy_counts["legacy_owner"]
        assert optimized_counts["batched_owner"] > legacy_counts["batched_owner"]
        if owner._records:
            assert optimized_counts["conjugate_transpose_identity"] > (
                legacy_counts["conjugate_transpose_identity"]
            )
        else:
            assert (
                optimized_counts["conjugate_transpose_identity"]
                == legacy_counts["conjugate_transpose_identity"]
            )
        with owner.variant_context("legacy"):
            legacy_p_repeat = owner.apply_primal(q1)
            legacy_ph_repeat = owner.apply_adjoint(fine_probe1)
        legacy_repeat_counts = dict(kernel_calls)
        assert legacy_repeat_counts["legacy_owner"] > optimized_counts["legacy_owner"]
        assert legacy_repeat_counts["batched_owner"] == optimized_counts["batched_owner"]
        assert (
            legacy_repeat_counts["conjugate_transpose_identity"]
            == optimized_counts["conjugate_transpose_identity"]
        )
        with owner.variant_context("optimized"):
            optimized_p_repeat = owner.apply_primal(q1)
            optimized_ph_repeat = owner.apply_adjoint(fine_probe1)
        final_kernel_counts = dict(kernel_calls)
        assert final_kernel_counts["legacy_owner"] == legacy_repeat_counts["legacy_owner"]
        assert final_kernel_counts["batched_owner"] > optimized_counts["batched_owner"]
        if owner._records:
            assert final_kernel_counts["conjugate_transpose_identity"] > (
                optimized_counts["conjugate_transpose_identity"]
            )
        else:
            assert (
                final_kernel_counts["conjugate_transpose_identity"]
                == optimized_counts["conjugate_transpose_identity"]
            )
        outputs.extend(
            (
                legacy_p,
                optimized_p,
                optimized_p2,
                legacy_p_repeat,
                optimized_p_repeat,
                legacy_ph,
                optimized_ph,
                optimized_ph2,
                legacy_ph_repeat,
                optimized_ph_repeat,
            )
        )
        assert legacy_p_facts["execution_variant"] == "legacy"
        assert legacy_p_facts["owner_resolution"] == "legacy_python"
        assert legacy_p_facts["execution_variant_source"] == "explicit_context"
        assert legacy_ph_facts["execution_variant"] == "legacy"
        assert legacy_ph_facts["adjoint_cell_apply"] == (
            "explicit_conjugate_transpose"
        )
        assert owner._variant_context_active is False
        assert owner.last_apply_facts["execution_variant"] == "optimized"
        assert owner.execution_variant == "optimized"

        np.testing.assert_allclose(
            optimized_p.getArray(readonly=True),
            legacy_p.getArray(readonly=True),
            atol=1.0e-11,
            rtol=1.0e-11,
        )
        np.testing.assert_allclose(
            optimized_ph.getArray(readonly=True),
            legacy_ph.getArray(readonly=True),
            atol=1.0e-11,
            rtol=1.0e-11,
        )

        p_difference = optimized_p.duplicate()
        optimized_p.copy(p_difference)
        p_difference.axpy(PETSc.ScalarType(-1.0), legacy_p)
        p_difference_norm = float(p_difference.norm())
        legacy_p_norm = float(legacy_p.norm())
        if legacy_p_norm == 0.0:
            assert p_difference_norm == 0.0
            p_relative = 0.0
        else:
            p_relative = p_difference_norm / legacy_p_norm
        assert np.isfinite(p_relative)
        assert p_relative <= 1.0e-11
        if MPI.COMM_WORLD.rank == 0:
            print(f"task041 V2 global P relative={p_relative:.16e}", flush=True)

        ph_difference = optimized_ph.duplicate()
        optimized_ph.copy(ph_difference)
        ph_difference.axpy(PETSc.ScalarType(-1.0), legacy_ph)
        ph_difference_norm = float(ph_difference.norm())
        legacy_ph_norm = float(legacy_ph.norm())
        if legacy_ph_norm == 0.0:
            assert ph_difference_norm == 0.0
            ph_relative = 0.0
        else:
            ph_relative = ph_difference_norm / legacy_ph_norm
        assert np.isfinite(ph_relative)
        assert ph_relative <= 1.0e-11
        if MPI.COMM_WORLD.rank == 0:
            print(
                f"task041 V2 global PH relative={ph_relative:.16e}",
                flush=True,
            )

        np.testing.assert_allclose(
            optimized_p.getArray(readonly=True),
            optimized_p_repeat.getArray(readonly=True),
            atol=1.0e-11,
            rtol=1.0e-11,
        )
        np.testing.assert_allclose(
            optimized_ph.getArray(readonly=True),
            optimized_ph_repeat.getArray(readonly=True),
            atol=1.0e-11,
            rtol=1.0e-11,
        )
        np.testing.assert_allclose(
            legacy_p.getArray(readonly=True),
            legacy_p_repeat.getArray(readonly=True),
            atol=1.0e-11,
            rtol=1.0e-11,
        )
        np.testing.assert_allclose(
            legacy_ph.getArray(readonly=True),
            legacy_ph_repeat.getArray(readonly=True),
            atol=1.0e-11,
            rtol=1.0e-11,
        )
        assert not np.allclose(
            optimized_p.getArray(readonly=True), optimized_p2.getArray(readonly=True)
        )
        assert not np.allclose(
            optimized_ph.getArray(readonly=True),
            optimized_ph2.getArray(readonly=True),
        )
        np.testing.assert_array_equal(
            q1.getArray(readonly=True), q1_before
        )
        np.testing.assert_array_equal(
            fine_probe1.getArray(readonly=True), fine_probe1_before
        )
    finally:
        for output in outputs:
            output.destroy()
        q1.destroy()
        q2.destroy()
        fine_probe1.destroy()
        fine_probe2.destroy()
        if p_difference is not None:
            p_difference.destroy()
        if ph_difference is not None:
            ph_difference.destroy()
        owner.destroy()


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
