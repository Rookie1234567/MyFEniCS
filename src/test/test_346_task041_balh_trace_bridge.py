"""Focused Task041 H1b tests for J/J^H and same-mesh P/P^H."""

from __future__ import annotations

import gc
import json
import weakref
from types import SimpleNamespace

import basix
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
from src.solvers.physical_balanced_coupling import PhysicalBalancedCoupling
from src.solvers.physical_balanced_same_mesh_transfer import (
    ROW_CONSISTENCY_LIMIT,
    SUPPORT_POLICY_ENTITY_CLOSURE,
    SameMeshHcurlOwnerTransfer,
    _apply_conjugate_transpose_vector,
    _diagnostic_packet_precheck,
    _owner_ranges,
    _owner_ranks,
    _resolve_owner_candidates,
    _resolve_owner_candidates_batched,
    build_same_mesh_hcurl_owner_transfer,
    build_same_mesh_hcurl_transfer,
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
        self.rank = 0
        self.size = 1

    def allreduce(self, value, op=None):
        self.values.append(value)
        return value


class _FixedReduction:
    def __init__(self, value):
        self.value = value

    def allreduce(self, value, op=None):
        return self.value


class _CountingRouteComm:
    def __init__(self, comm):
        self.comm = comm
        self.counts = {
            "route_preflight_allgather": 0,
            "count_alltoall": 0,
            "id_alltoallv": 0,
            "value_alltoallv": 0,
        }

    def __getattr__(self, name):
        return getattr(self.comm, name)

    @property
    def rank(self):
        return int(self.comm.rank)

    @property
    def size(self):
        return int(self.comm.size)

    def allreduce(self, value, op=None):
        return self.comm.allreduce(value, op=op)

    def allgather(self, value):
        self.counts["route_preflight_allgather"] += 1
        return self.comm.allgather(value)

    def Alltoall(self, sendbuf, recvbuf):
        self.counts["count_alltoall"] += 1
        return self.comm.Alltoall(sendbuf, recvbuf)

    def Alltoallv(self, sendbuf, recvbuf):
        kind = np.asarray(sendbuf[0]).dtype
        if kind == np.dtype(np.uint64):
            self.counts["id_alltoallv"] += 1
        elif kind == np.dtype(np.complex128):
            self.counts["value_alltoallv"] += 1
        else:
            raise AssertionError(f"unexpected same-mesh packet dtype {kind}")
        return self.comm.Alltoallv(sendbuf, recvbuf)


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
    ("optimization_profile", "reuse_primal_route_plan"),
    (
        (None, False),
        ("task041_schur_speed_v2", False),
        (None, True),
        ("task041_schur_speed_v2", True),
    ),
    ids=(
        "legacy_route_disabled",
        "task041_schur_speed_v2_route_disabled",
        "legacy_route_reuse",
        "task041_schur_speed_v2_route_reuse",
    ),
)
def test_task041_h1b_empty_owner_range_is_supported_on_one_cell_mesh(
    optimization_profile: str | None,
    reuse_primal_route_plan: bool,
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
        reuse_primal_route_plan=reuse_primal_route_plan,
    )
    reference_owner = None
    if reuse_primal_route_plan:
        reference_owner = build_same_mesh_hcurl_owner_transfer(
            fine_space,
            fine_floquet,
            coarse_space,
            coarse_floquet,
            local_transfer=owner.local_transfer,
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
    coarse_second = coarse.duplicate()
    outputs = []
    coarse_before = None
    coarse_second_before = None
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
        route_comm = _CountingRouteComm(MPI.COMM_WORLD)
        if reuse_primal_route_plan:
            owner.comm = route_comm
        coarse_slaves = np.asarray(owner._coarse_slaves, dtype=np.int64)
        fine_slaves = np.asarray(owner._fine_slaves, dtype=np.int64)
        _fill_algebraic_vector(coarse, coarse_slaves, 0.75)
        coarse_before = coarse.duplicate()
        coarse.copy(coarse_before)
        fine_output = owner.apply_primal(coarse)
        outputs.append(fine_output)
        if reuse_primal_route_plan:
            plan = owner._primal_route_plan
            plan_ready_states = MPI.COMM_WORLD.allgather(plan is not None)
            assert all(plan_ready_states)
            assert plan is not None
            empty_senders = MPI.COMM_WORLD.allreduce(
                int(plan.candidate_ids.size == 0), op=MPI.SUM
            )
            empty_receivers = MPI.COMM_WORLD.allreduce(
                int(plan.recv_ids.size == 0), op=MPI.SUM
            )
            assert empty_senders > 0
            assert empty_receivers > 0
            captured_state = owner.last_apply_facts["primal_route_plan_state"]
            captured_preflight = owner.last_apply_facts[
                "primal_route_plan_preflight"
            ]
            captured_reports = MPI.COMM_WORLD.allgather(
                (captured_state, captured_preflight)
            )
            assert all(
                report
                == (
                    "captured",
                    {
                        "status": "passed",
                        "collective": "allgather_plan_readiness_and_local_validation",
                        "collective_count": 1,
                        "participants": 2,
                    },
                )
                for report in captured_reports
            )

            _fill_algebraic_vector(coarse_second, coarse_slaves, -1.875)
            coarse_second_before = coarse_second.duplicate()
            coarse_second.copy(coarse_second_before)
            second_output = owner.apply_primal(coarse_second)
            outputs.append(second_output)
            reference_output = reference_owner.apply_primal(coarse_second)
            outputs.append(reference_output)
            second_matches_reference = bool(
                np.allclose(
                    second_output.getArray(readonly=True),
                    reference_output.getArray(readonly=True),
                    atol=1.0e-11,
                    rtol=1.0e-11,
                )
            )
            second_input_unchanged = bool(
                np.array_equal(
                    coarse_second.getArray(readonly=True),
                    coarse_second_before.getArray(readonly=True),
                )
            )
            coarse_norm = coarse.norm()
            coarse_second_norm = coarse_second.norm()
            rhs_difference = coarse.duplicate()
            coarse.copy(rhs_difference)
            rhs_difference.axpy(
                PETSc.ScalarType(-1.0), coarse_second
            )
            rhs_difference_norm = rhs_difference.norm()
            rhs_difference.destroy()
            second_state = owner.last_apply_facts["primal_route_plan_state"]
            second_counts = dict(route_comm.counts)
            second_reports = MPI.COMM_WORLD.allgather(
                (
                    second_matches_reference,
                    second_input_unchanged,
                    coarse_norm > 0.0,
                    coarse_second_norm > 0.0,
                    rhs_difference_norm > 0.0,
                    second_state,
                    second_counts,
                )
            )
            expected_second_counts = {
                "route_preflight_allgather": 2,
                "count_alltoall": 1,
                "id_alltoallv": 1,
                "value_alltoallv": 2,
            }
            assert all(
                report[:6]
                == (True, True, True, True, True, "reused")
                and report[6] == expected_second_counts
                for report in second_reports
            )
        else:
            assert owner._primal_route_plan is None
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

        dot_source = coarse_second if reuse_primal_route_plan else coarse
        dot_primal = outputs[1] if reuse_primal_route_plan else fine_output
        dot_lhs = dot_primal.dot(fine_probe)
        dot_rhs = dot_source.dot(coarse_output)
        dot_scale = max(abs(dot_lhs), abs(dot_rhs), np.finfo(float).tiny)
        dot_checks = MPI.COMM_WORLD.allgather(
            abs(dot_lhs - dot_rhs) / dot_scale <= 1.0e-10
        )
        assert all(dot_checks)

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
        if coarse_second_before is not None:
            coarse_second_before.destroy()
        if coarse_before is not None:
            coarse_before.destroy()
        coarse_second.destroy()
        if fine_probe_before is not None:
            fine_probe_before.destroy()
        if coarse_difference is not None:
            coarse_difference.destroy()
        if fine_difference is not None:
            fine_difference.destroy()
        owner.destroy()
        if reference_owner is not None:
            reference_owner.destroy()


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
    MPI.COMM_WORLD.size not in (1, 2),
    reason="the focused BAL_H transfer reuse check is serial/MPI2-only",
)
def test_task041_h1b_bal_h_transfer_dual_reuse_preserves_coupling_algebra(
    small_fe_fixture,
) -> None:
    data = small_fe_fixture
    owner = data["owner"]
    fine_space = data["fine_space"]
    fine_slaves = np.asarray(owner._fine_slaves, dtype=np.int64)
    sources = [
        create_vector(
            [(fine_space.dofmap.index_map, int(fine_space.dofmap.index_map_bs))]
        )
        for _ in range(2)
    ]
    _fill_algebraic_vector(sources[0], fine_slaves, 1.75)
    _fill_algebraic_vector(sources[1], fine_slaves, -2.25)
    originals = [
        np.asarray(source.getArray(readonly=True), dtype=np.complex128).copy()
        for source in sources
    ]
    assert any(np.imag(value).any() for value in originals)

    def make_case(reuse: bool):
        counts = {"P": 0, "Q_PH": 0, "audit_PH": 0, "q_handoff": []}
        action_state = {"source": None, "calls": 0}

        def action(value: PETSc.Vec) -> PETSc.Vec:
            result = value.duplicate()
            if action_state["calls"] == 0:
                action_state["source"].copy(result)
            else:
                result.set(PETSc.ScalarType(0.0))
            result.assemble()
            action_state["calls"] += 1
            return result

        def coarse(value: PETSc.Vec, *, return_leading_dual: bool = False):
            counts["q_handoff"].append(return_leading_dual)
            dual = owner.apply_adjoint(value)
            counts["Q_PH"] += 1
            result = owner.apply_primal(dual)
            counts["P"] += 1
            if return_leading_dual:
                return result, dual
            dual.destroy()
            return result

        def restriction(value: PETSc.Vec) -> PETSc.Vec:
            counts["audit_PH"] += 1
            return owner.apply_adjoint(value)

        coupling = PhysicalBalancedCoupling(
            action,
            coarse,
            lambda value: _zero_like(value),
            restriction,
            reuse_leading_ph=reuse,
        )
        return coupling, counts, action_state

    def _zero_like(value: PETSc.Vec) -> PETSc.Vec:
        result = value.duplicate()
        result.set(PETSc.ScalarType(0.0))
        result.assemble()
        return result

    legacy, legacy_counts, legacy_action = make_case(False)
    reused, reused_counts, reused_action = make_case(True)
    try:
        for index in (0, 1, 0):
            source = sources[index]
            legacy_action["source"] = source
            legacy_action["calls"] = 0
            reused_action["source"] = source
            reused_action["calls"] = 0
            legacy_before = dict(legacy_counts)
            reused_before = dict(reused_counts)
            legacy_output = legacy.apply(source)
            legacy_facts = legacy.last_apply_facts
            reused_output = reused.apply(source)
            reused_facts = reused.last_apply_facts
            try:
                legacy_values = np.asarray(
                    legacy_output.getArray(readonly=True), dtype=np.complex128
                ).copy()
                reused_values = np.asarray(
                    reused_output.getArray(readonly=True), dtype=np.complex128
                ).copy()
                np.testing.assert_allclose(
                    reused_values,
                    legacy_values,
                    rtol=1.0e-12,
                    atol=1.0e-12,
                )
                assert legacy_facts["initial"]["balance"] == reused_facts[
                    "initial"
                ]["balance"]
                assert legacy_facts["counts"] == {
                    "Q": 2,
                    "H6": 1,
                    "A6": 2,
                    "PH_audit": 2,
                }
                assert reused_facts["counts"] == {
                    "Q": 2,
                    "H6": 1,
                    "A6": 2,
                    "PH_audit": 2,
                    "PH_audit_transfer": 1,
                    "PH_audit_leading_reused": 1,
                }
                assert legacy_facts["status"] == reused_facts["status"]
                assert legacy_facts["live_after_cleanup"] == 0
                assert reused_facts["live_after_cleanup"] == 0
            finally:
                legacy_output.destroy()
                reused_output.destroy()
            legacy_delta = {
                name: legacy_counts[name] - legacy_before[name]
                for name in ("P", "Q_PH", "audit_PH")
            }
            reused_delta = {
                name: reused_counts[name] - reused_before[name]
                for name in ("P", "Q_PH", "audit_PH")
            }
            assert legacy_delta == {"P": 2, "Q_PH": 2, "audit_PH": 2}
            assert reused_delta == {"P": 2, "Q_PH": 2, "audit_PH": 1}
            assert legacy_counts["q_handoff"][-2:] == [False, False]
            assert reused_counts["q_handoff"][-2:] == [True, False]
            np.testing.assert_array_equal(
                source.getArray(readonly=True), originals[index]
            )
        assert legacy.apply_count == reused.apply_count == 3
    finally:
        for source in sources:
            source.destroy()


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
    comm.size = 2
    with pytest.raises(ValueError):
        _resolve_owner_candidates(ids, values, source_ranks, 0, comm)
    with pytest.raises(ValueError):
        _resolve_owner_candidates_batched(ids, values, source_ranks, 0, comm)


@pytest.mark.parametrize("defect", (0.0, 2.0e-11))
def test_task041_h1b_diagnostic_uses_full_packet_and_runs_both_resolvers(
    defect, monkeypatch
) -> None:
    import src.solvers.physical_balanced_same_mesh_transfer as transfer_module

    ids = np.asarray((0, 0, 2, 2), dtype=np.uint64)
    values = np.asarray(
        (1.0 + 0.5j, 1.0 + 0.5j, 2.0 - 0.25j, 2.0 - 0.25j),
        dtype=np.complex128,
    )
    values[1] += defect
    source_ranks = np.zeros(ids.size, dtype=np.int32)
    emitted_ids = ids.copy()
    emitted_values = values.copy()
    snapshots = (ids.copy(), values.copy(), source_ranks.copy())
    captured: dict[str, np.ndarray] = {}
    calls = {"legacy": 0, "batched": 0}

    legacy = transfer_module._resolve_owner_candidates
    batched = transfer_module._resolve_owner_candidates_batched

    def traced_legacy(*args, **kwargs):
        calls["legacy"] += 1
        return legacy(*args, **kwargs)

    def traced_batched(*args, **kwargs):
        calls["batched"] += 1
        return batched(*args, **kwargs)

    def callback(**payload):
        for name in ("ids", "values", "source_ranks", "emitted_ids", "emitted_values"):
            captured[name] = np.asarray(payload[name]).copy()
        return {"captured": True}

    monkeypatch.setattr(transfer_module, "_resolve_owner_candidates", traced_legacy)
    monkeypatch.setattr(
        transfer_module, "_resolve_owner_candidates_batched", traced_batched
    )
    transfer = object.__new__(SameMeshHcurlOwnerTransfer)
    transfer.comm = _SerialReduction()
    transfer.fine_ranges = ((0, 3),)
    transfer.coarse_ranges = ((0, 2),)
    transfer._execution_variant = "optimized"
    transfer._destroyed = False
    transfer._apply_in_progress = False
    transfer._diagnostic_context = None
    transfer._diagnostic_callback = None
    transfer._last_diagnostic = {}
    try:
        context = transfer.diagnostic_context(callback)
        with context:
            if defect > 1.0e-11:
                with pytest.raises(RuntimeError):
                    transfer._diagnostic_resolve_candidates(
                        ids, values, source_ranks, 0, emitted_ids,
                        emitted_values, object()
                    )
            else:
                result = transfer._diagnostic_resolve_candidates(
                    ids, values, source_ranks, 0, emitted_ids,
                    emitted_values, object()
                )
                np.testing.assert_array_equal(
                    result[0], np.asarray((0, 2), dtype=np.uint64)
                )
        assert transfer._diagnostic_context is None
        assert transfer._diagnostic_callback is None
        assert calls == {"legacy": 1, "batched": 1}
        np.testing.assert_array_equal(captured["ids"], snapshots[0])
        np.testing.assert_array_equal(captured["values"], snapshots[1])
        np.testing.assert_array_equal(
            captured["source_ranks"], snapshots[2]
        )
        np.testing.assert_array_equal(captured["emitted_ids"], emitted_ids)
        np.testing.assert_array_equal(
            captured["emitted_values"], emitted_values
        )
        assert transfer.last_diagnostic["callback"] == {"captured": True}
    finally:
        transfer._diagnostic_context = None
        transfer._diagnostic_callback = None


def test_task041_h1b_diagnostic_packet_precheck_and_context_recovery() -> None:
    comm = _SerialReduction()
    missing_owner_comm = _SerialReduction()
    missing_owner_comm.size = 2
    with pytest.raises(ValueError):
        _diagnostic_packet_precheck(
            np.asarray((0, 0), dtype=np.uint64),
            np.asarray((1.0 + 0.0j,), dtype=np.complex128),
            np.asarray((0, 0), dtype=np.int32),
            owner_rank=0,
            comm=comm,
        )
    with pytest.raises(ValueError):
        _diagnostic_packet_precheck(
            np.asarray((0, 0, 2), dtype=np.uint64),
            np.asarray((1.0 + 0.0j, 1.0 + 0.0j, 2.0 + 0.0j)),
            np.asarray((1, 1, 1), dtype=np.int32),
            owner_rank=0,
            comm=missing_owner_comm,
        )
    transfer = object.__new__(SameMeshHcurlOwnerTransfer)
    transfer._execution_variant = "optimized"
    transfer._destroyed = False
    transfer._apply_in_progress = False
    transfer._diagnostic_context = None
    transfer._diagnostic_callback = None
    transfer._last_diagnostic = {}
    with pytest.raises(RuntimeError, match="context sentinel"), transfer.diagnostic_context(
        lambda **_: {}
    ):
        raise RuntimeError("context sentinel")
    assert transfer._diagnostic_context is None
    assert transfer._diagnostic_callback is None
    normal = _resolve_owner_candidates(
        np.asarray((0, 0), dtype=np.uint64),
        np.asarray((1.0 + 0.0j, 1.0 + 0.0j)),
        np.asarray((0, 0), dtype=np.int32),
        owner_rank=0,
        comm=comm,
    )
    assert normal[3] == 2


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


@pytest.mark.parametrize(
    "cell_info",
    [0, 840882870, 81900640],
    ids=["reference", "captured_orientation_a", "captured_orientation_b"],
)
def test_task041_h1b_entity_closure_support_has_tabulation_oracle(
    cell_info: int,
) -> None:
    coarse_element = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        4,
        basix.LagrangeVariant.legendre,
    )
    fine_element = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        6,
        basix.LagrangeVariant.legendre,
    )
    legacy = build_same_mesh_hcurl_transfer(
        6,
        4,
        coarse_cell_info=cell_info,
        fine_cell_info=cell_info,
    )
    transfer = build_same_mesh_hcurl_transfer(
        6,
        4,
        coarse_cell_info=cell_info,
        fine_cell_info=cell_info,
        support_policy=SUPPORT_POLICY_ENTITY_CLOSURE,
    )
    assert transfer.audit["support_policy"] == SUPPORT_POLICY_ENTITY_CLOSURE
    assert transfer.audit["orientation_entity_blocks_verified"] is True
    assert transfer.audit["reference_entity_trace_v1"] is True
    assert transfer.audit["reference_edge_block"] == (
        "legendre_identity_zero"
    )
    assert transfer.audit["reference_face_block"] == (
        "quadrilateral_n1e_interpolation"
    )
    assert transfer.audit["reference_face_edge_map"] == [
        [0, 1, 3, 5],
        [0, 2, 4, 8],
        [1, 2, 6, 9],
        [3, 4, 7, 10],
        [5, 6, 7, 11],
        [8, 9, 10, 11],
    ]
    assert legacy.audit["reference_entity_trace_v1"] is False
    assert int(coarse_element.dim) == 300
    assert int(fine_element.dim) == 882
    for topological_dim, entities in enumerate(fine_element.entity_dofs):
        if topological_dim >= 3:
            continue
        for entity, rows in enumerate(entities):
            allowed = np.asarray(
                coarse_element.entity_closure_dofs[topological_dim][entity],
                dtype=np.intp,
            )
            disallowed = np.setdiff1d(
                np.arange(int(coarse_element.dim), dtype=np.intp),
                allowed,
            )
            for row in rows:
                assert np.all(transfer.matrix[int(row), disallowed] == 0.0)

    if cell_info == 0:
        nodes = (np.polynomial.legendre.leggauss(7)[0] + 1.0) / 2.0
        points = np.asarray(
            [[x, y, z] for x in nodes for y in nodes for z in nodes],
            dtype=np.float64,
        )
        # Seven tensor points per axis cover the degree-six component
        # polynomials while keeping this independent oracle bounded.
        coarse_basis = np.asarray(coarse_element.tabulate(0, points)[0])
        fine_basis = np.asarray(fine_element.tabulate(0, points)[0])
        mapped_basis = np.einsum(
            "pfv,fc->pcv",
            fine_basis,
            transfer.matrix,
        )
        basis_error = float(np.max(np.abs(mapped_basis - coarse_basis)))
        assert basis_error <= 1.0e-11, basis_error
    else:
        basis_error = None

    coefficients = np.asarray(
        [0.25 + 0.5j + 0.001 * index for index in range(int(coarse_element.dim))],
        dtype=np.complex128,
    )
    fine_probe = np.asarray(
        [0.5 - 0.25j + 0.002 * index for index in range(int(fine_element.dim))],
        dtype=np.complex128,
    )
    mapped = transfer.apply(coefficients)
    if cell_info == 0:
        coarse_values = np.einsum(
            "pcv,c->pv",
            coarse_basis,
            coefficients,
        )
        fine_values = np.einsum("pfv,f->pv", fine_basis, mapped)
        complex_error = float(np.max(np.abs(fine_values - coarse_values)))
        assert complex_error <= 1.0e-11, complex_error
    else:
        complex_error = None
    lhs = np.vdot(mapped, fine_probe)
    rhs = np.vdot(coefficients, transfer.apply_adjoint(fine_probe))
    dot_scale = max(abs(lhs), abs(rhs))
    if dot_scale == 0.0:
        dot_relative = 0.0
        assert lhs == rhs
    else:
        dot_relative = float(abs(lhs - rhs) / dot_scale)
        assert dot_relative <= 1.0e-10
    if cell_info == 0 and MPI.COMM_WORLD.rank == 0:
        print(
            json.dumps(
                {
                    "schema": "task041.h1b.reference_transfer_qualification.v1",
                    "cell_info": int(cell_info),
                    "support_policy": SUPPORT_POLICY_ENTITY_CLOSURE,
                    "basis_max_abs_error": basis_error,
                    "complex_action_max_abs_error": complex_error,
                    "complex_adjoint_dot_relative_error": dot_relative,
                },
                sort_keys=True,
            ),
            flush=True,
        )



def test_task041_h1b_reference_entity_trace_uses_ordered_hex_blocks() -> None:
    coarse_element = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        4,
        basix.LagrangeVariant.legendre,
    )
    fine_element = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.hexahedron,
        6,
        basix.LagrangeVariant.legendre,
    )
    transfer = build_same_mesh_hcurl_transfer(
        6,
        4,
        support_policy=SUPPORT_POLICY_ENTITY_CLOSURE,
    )
    legacy = build_same_mesh_hcurl_transfer(6, 4)
    expected_faces = [
        [0, 1, 3, 5],
        [0, 2, 4, 8],
        [1, 2, 6, 9],
        [3, 4, 7, 10],
        [5, 6, 7, 11],
        [8, 9, 10, 11],
    ]
    assert transfer.audit["reference_face_edge_map"] == expected_faces
    interior_rows = np.asarray(
        fine_element.entity_dofs[3][0],
        dtype=np.intp,
    )
    np.testing.assert_array_equal(
        transfer.matrix[interior_rows, :],
        legacy.matrix[interior_rows, :],
    )
    quad_coarse = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.quadrilateral,
        4,
        basix.LagrangeVariant.legendre,
    )
    quad_fine = basix.create_element(
        basix.ElementFamily.N1E,
        basix.CellType.quadrilateral,
        6,
        basix.LagrangeVariant.legendre,
    )
    quad_reference = np.asarray(
        basix.compute_interpolation_operator(quad_coarse, quad_fine),
        dtype=np.complex128,
    )
    edge_block = np.zeros((6, 4), dtype=np.complex128)
    edge_block[:4, :] = np.eye(4, dtype=np.complex128)
    for fine_rows, coarse_columns in zip(
        fine_element.entity_dofs[1],
        coarse_element.entity_dofs[1],
        strict=True,
    ):
        expected = np.zeros(
            (len(fine_rows), int(coarse_element.dim)),
            dtype=np.complex128,
        )
        expected[:, np.asarray(coarse_columns, dtype=np.intp)] = edge_block
        np.testing.assert_array_equal(
            transfer.matrix[np.asarray(fine_rows, dtype=np.intp), :],
            expected,
        )
    quad_rows = np.asarray(quad_fine.entity_dofs[2][0], dtype=np.intp)
    quad_columns = np.asarray(
        np.concatenate(
            [
                np.asarray(rows, dtype=np.intp)
                for rows in quad_coarse.entity_dofs[1]
            ]
            + [np.asarray(quad_coarse.entity_dofs[2][0], dtype=np.intp)]
        ),
        dtype=np.intp,
    )
    for face, mapped_edges in enumerate(expected_faces):
        fine_rows = np.asarray(
            fine_element.entity_dofs[2][face],
            dtype=np.intp,
        )
        coarse_columns = np.asarray(
            np.concatenate(
                [
                    np.asarray(
                        coarse_element.entity_dofs[1][edge],
                        dtype=np.intp,
                    )
                    for edge in mapped_edges
                ]
                + [
                    np.asarray(
                        coarse_element.entity_dofs[2][face],
                        dtype=np.intp,
                    )
                ]
            ),
            dtype=np.intp,
        )
        expected = quad_reference[np.ix_(quad_rows, quad_columns)]
        np.testing.assert_array_equal(
            transfer.matrix[np.ix_(fine_rows, coarse_columns)],
            expected,
        )
        outside = np.setdiff1d(
            np.arange(int(coarse_element.dim), dtype=np.intp),
            coarse_columns,
        )
        np.testing.assert_array_equal(
            transfer.matrix[np.ix_(fine_rows, outside)],
            np.zeros((fine_rows.size, outside.size), dtype=np.complex128),
        )


@pytest.mark.skipif(
    MPI.COMM_WORLD.size == 8,
    reason="the nonzero-Floquet owner oracle is serial/MPI2-only",
)
def test_task041_h1b_entity_closure_owner_covers_nonzero_floquet(
    small_fe_fixture,
) -> None:
    data = small_fe_fixture
    assert data["cfg6"].use_floquet_xy is True
    assert abs(complex(data["cfg6"].floquet_phase_x) - 1.0) > 1.0e-3
    assert abs(complex(data["cfg6"].floquet_phase_y) - 1.0) > 1.0e-3
    owner = build_same_mesh_hcurl_owner_transfer(
        data["fine_space"],
        data["fine_floquet"],
        data["coarse_space"],
        data["coarse_floquet"],
        optimization_profile="task041_schur_speed_v2",
        support_policy=SUPPORT_POLICY_ENTITY_CLOSURE,
    )
    coarse = create_vector(
        [
            (
                data["coarse_space"].dofmap.index_map,
                int(data["coarse_space"].dofmap.index_map_bs),
            )
        ]
    )
    fine_probe = create_vector(
        [
            (
                data["fine_space"].dofmap.index_map,
                int(data["fine_space"].dofmap.index_map_bs),
            )
        ]
    )
    coarse_field = fem.Function(data["coarse_floquet"].mpc.function_space)
    fine_oracle = fem.Function(data["fine_floquet"].mpc.function_space)
    fine_output = None
    coarse_output = None
    legacy_output = None
    fine_difference = None
    ph_difference = None
    try:
        assert owner.audit["support_policy"] == SUPPORT_POLICY_ENTITY_CLOSURE
        coarse_slaves = np.asarray(owner._coarse_slaves, dtype=np.int64)
        fine_slaves = np.asarray(owner._fine_slaves, dtype=np.int64)
        _fill_algebraic_vector(coarse, coarse_slaves, 0.875)
        _fill_algebraic_vector(fine_probe, fine_slaves, -0.625)
        coarse_before = np.asarray(
            coarse.getArray(readonly=True), dtype=np.complex128
        ).copy()
        fine_before = np.asarray(
            fine_probe.getArray(readonly=True), dtype=np.complex128
        ).copy()
        fine_output = owner.apply_primal(coarse)
        coarse.copy(coarse_field.x.petsc_vec)
        coarse_field.x.scatter_forward()
        data["coarse_floquet"].mpc.homogenize(coarse_field)
        coarse_field.x.scatter_forward()
        data["coarse_floquet"].mpc.backsubstitution(coarse_field)
        coarse_field.x.scatter_forward()
        fine_oracle.interpolate(coarse_field)
        fine_oracle.x.scatter_forward()
        data["fine_floquet"].mpc.homogenize(fine_oracle)
        fine_oracle.x.scatter_forward()
        fine_difference = fine_output.duplicate()
        fine_output.copy(fine_difference)
        fine_difference.axpy(
            PETSc.ScalarType(-1.0),
            fine_oracle.x.petsc_vec,
        )
        oracle_norm = fine_oracle.x.petsc_vec.norm()
        difference_norm = fine_difference.norm()
        if oracle_norm == 0.0:
            p_relative = 0.0
            assert difference_norm == 0.0
        else:
            p_relative = float(difference_norm / oracle_norm)
            assert p_relative <= 1.0e-11

        legacy_output = data["owner"].apply_adjoint(fine_probe)
        coarse_output = owner.apply_adjoint(fine_probe)
        ph_difference = coarse_output.duplicate()
        coarse_output.copy(ph_difference)
        ph_difference.axpy(PETSc.ScalarType(-1.0), legacy_output)
        legacy_norm = legacy_output.norm()
        ph_difference_norm = ph_difference.norm()
        if legacy_norm == 0.0:
            ph_relative = 0.0
            assert ph_difference_norm == 0.0
        else:
            ph_relative = float(ph_difference_norm / legacy_norm)
            assert ph_relative <= 1.0e-11
        np.testing.assert_array_equal(
            coarse.getArray(readonly=True),
            coarse_before,
        )
        np.testing.assert_array_equal(
            fine_probe.getArray(readonly=True),
            fine_before,
        )
        assert np.all(np.isfinite(fine_output.getArray(readonly=True)))
        assert np.all(np.isfinite(coarse_output.getArray(readonly=True)))
        assert np.all(fine_output.getArray(readonly=True)[fine_slaves] == 0.0)
        assert np.all(coarse_output.getArray(readonly=True)[coarse_slaves] == 0.0)
        assert np.all(legacy_output.getArray(readonly=True)[coarse_slaves] == 0.0)
        lhs = fine_output.dot(fine_probe)
        rhs = coarse.dot(coarse_output)
        dot_scale = max(abs(lhs), abs(rhs))
        if dot_scale == 0.0:
            dot_relative = 0.0
            assert lhs == rhs
        else:
            dot_relative = float(abs(lhs - rhs) / dot_scale)
            assert dot_relative <= 1.0e-10
        if MPI.COMM_WORLD.rank == 0:
            print(
                json.dumps(
                    {
                        "schema": "task041.h1b.entity_closure_floquet_qualification.v1",
                        "support_policy": SUPPORT_POLICY_ENTITY_CLOSURE,
                        "floquet_phase_x_nonunit": True,
                        "floquet_phase_y_nonunit": True,
                        "p_relative_error": p_relative,
                        "ph_relative_error_vs_legacy": ph_relative,
                        "dot_relative_error": dot_relative,
                        "oracle_norm": float(oracle_norm),
                        "p_difference_norm": float(difference_norm),
                        "legacy_ph_norm": float(legacy_norm),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
    finally:
        if fine_output is not None:
            fine_output.destroy()
        if coarse_output is not None:
            coarse_output.destroy()
        if legacy_output is not None:
            legacy_output.destroy()
        if fine_difference is not None:
            fine_difference.destroy()
        if ph_difference is not None:
            ph_difference.destroy()
        fine_probe.destroy()
        coarse.destroy()
        owner.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="compact orientation component test uses the existing serial/MPI2 fixture",
)
def test_task041_h1b_compact_orientation_preserves_complex_p_ph_and_releases(
    small_fe_fixture,
    monkeypatch,
) -> None:
    import src.solvers.physical_balanced_same_mesh_transfer as transfer_module

    data = small_fe_fixture
    support_policy = SUPPORT_POLICY_ENTITY_CLOSURE

    def check_owner_lifecycle():
        compact = None
        dense = None
        context_ref = None
        reference_ref = None
        vectors = []
        try:
            compact = build_same_mesh_hcurl_owner_transfer(
                data["fine_space"],
                data["fine_floquet"],
                data["coarse_space"],
                data["coarse_floquet"],
                support_policy=support_policy,
                compact_orientation=True,
            )
            dense = build_same_mesh_hcurl_owner_transfer(
                data["fine_space"],
                data["fine_floquet"],
                data["coarse_space"],
                data["coarse_floquet"],
                support_policy=support_policy,
            )
            context = compact._compact_orientation_context
            assert context is not None
            context_ref = weakref.ref(context)
            reference_ref = weakref.ref(context.reference_matrix)
            cached = tuple(compact._compact_orientation_transfers)
            cache_by_key = {
                (item.coarse_cell_info, item.fine_cell_info): item
                for item in cached
            }
            record_keys = {
                (
                    record["compact_transfer"].coarse_cell_info,
                    record["compact_transfer"].fine_cell_info,
                )
                for record in compact._records
            }
            assert len(record_keys) > 1
            assert all(item.matrix is None for item in cached)
            assert all(
                item.compact_orientation is not None
                and item.compact_orientation.context is context
                for item in cached
            )
            assert all(
                record["compact_transfer"]
                is cache_by_key[
                    (
                        record["compact_transfer"].coarse_cell_info,
                        record["compact_transfer"].fine_cell_info,
                    )
                ]
                for record in compact._records
            )
            assert dense.local_transfer.matrix is not None
            storage = compact.audit["orientation_storage"]
            assert storage["seed_included_in_unique_key_count"] is True
            assert storage["unique_key_count_including_seed"] == len(
                cached
            )
            assert storage["record_unique_key_count"] == len(record_keys)
            assert storage["records_are_shared_references"] is True
            assert storage["canonical_R_copies_per_adapter"] == 1
            assert storage["canonical_R_bytes_local"] == (
                context.reference_matrix.nbytes
            )
            assert storage["full_oriented_matrix_retained"] is False

            fine_dim, coarse_dim = context.reference_matrix.shape
            local_coarse = np.arange(coarse_dim, dtype=np.float64) * (
                0.013 + 0.021j
            ) + (0.37 - 0.19j)
            local_fine = np.arange(fine_dim, dtype=np.float64) * (
                0.017 - 0.011j
            ) + (0.29 + 0.23j)
            for item in cached:
                dense_local = build_same_mesh_hcurl_transfer(
                    6,
                    4,
                    coarse_cell_info=item.coarse_cell_info,
                    fine_cell_info=item.fine_cell_info,
                    support_policy=support_policy,
                )
                assert dense_local.matrix is not None
                compact_map = item.compact_orientation
                assert compact_map is not None
                compact_p = item.apply(local_coarse)
                dense_p = dense_local.matrix @ local_coarse
                compact_ph = item.apply_adjoint(local_fine)
                dense_ph = dense_local.matrix.conj().T @ local_fine
                assert np.linalg.norm(compact_p) > 0.0
                assert np.linalg.norm(compact_ph) > 0.0
                np.testing.assert_allclose(
                    compact_p, dense_p, rtol=1.0e-12, atol=1.0e-12
                )
                np.testing.assert_allclose(
                    compact_ph, dense_ph, rtol=1.0e-12, atol=1.0e-12
                )
                lhs = np.vdot(compact_p, local_fine)
                rhs = np.vdot(local_coarse, compact_ph)
                scale = max(abs(lhs), abs(rhs))
                assert scale > 0.0
                assert abs(lhs - rhs) / scale <= 1.0e-12

                fine_element = compact_map.context.fine_element
                coarse_element = compact_map.context.coarse_element
                # Directly exercise the compact actions on representative edge
                # and face closures for every actual direction key.  No compact
                # full matrix is reconstructed in these support checks.
                for topological_dim in (1, 2):
                    selected = None
                    for entity, fine_rows in enumerate(
                        fine_element.entity_dofs[topological_dim]
                    ):
                        if not fine_rows:
                            continue
                        allowed = np.asarray(
                            coarse_element.entity_closure_dofs[
                                topological_dim
                            ][entity],
                            dtype=np.intp,
                        )
                        outside = np.setdiff1d(
                            np.arange(coarse_dim, dtype=np.intp), allowed
                        )
                        if outside.size:
                            selected = (
                                np.asarray(fine_rows, dtype=np.intp),
                                outside,
                            )
                            break
                    assert selected is not None
                    fine_rows, outside = selected
                    exterior_coarse = np.zeros(
                        coarse_dim, dtype=np.complex128
                    )
                    exterior_coarse[outside] = 0.4 + 0.7j
                    exterior_image = item.apply(exterior_coarse)
                    np.testing.assert_array_equal(
                        exterior_image[fine_rows],
                        np.zeros(fine_rows.size, dtype=np.complex128),
                    )

                    entity_probe = np.zeros(
                        fine_dim, dtype=np.complex128
                    )
                    entity_probe[fine_rows] = 0.2 - 0.6j
                    adjoint_image = item.apply_adjoint(entity_probe)
                    np.testing.assert_array_equal(
                        adjoint_image[outside],
                        np.zeros(outside.size, dtype=np.complex128),
                    )

                for topological_dim, entities in enumerate(
                    fine_element.entity_dofs
                ):
                    if topological_dim >= 3:
                        continue
                    for entity, fine_rows in enumerate(entities):
                        if not fine_rows:
                            continue
                        allowed = np.asarray(
                            coarse_element.entity_closure_dofs[topological_dim][
                                entity
                            ],
                            dtype=np.intp,
                        )
                        outside = np.setdiff1d(
                            np.arange(coarse_dim, dtype=np.intp), allowed
                        )
                        np.testing.assert_array_equal(
                            dense_local.matrix[
                                np.ix_(np.asarray(fine_rows), outside)
                            ],
                            np.zeros(
                                (len(fine_rows), outside.size),
                                dtype=np.complex128,
                            ),
                        )

            coarse = create_vector(
                [(data["coarse_space"].dofmap.index_map, 1)]
            )
            vectors.append(coarse)
            fine_probe = create_vector(
                [(data["fine_space"].dofmap.index_map, 1)]
            )
            vectors.append(fine_probe)
            _fill_algebraic_vector(coarse, compact._coarse_slaves, 0.375)
            _fill_algebraic_vector(fine_probe, compact._fine_slaves, -0.625)
            coarse_before = coarse.getArray(readonly=True).copy()
            fine_before = fine_probe.getArray(readonly=True).copy()
            compact_p = compact.apply_primal(coarse)
            vectors.append(compact_p)
            compact_ph = compact.apply_adjoint(fine_probe)
            vectors.append(compact_ph)
            dense_p = dense.apply_primal(coarse)
            vectors.append(dense_p)
            dense_ph = dense.apply_adjoint(fine_probe)
            vectors.append(dense_ph)
            np.testing.assert_allclose(
                compact_p.getArray(readonly=True),
                dense_p.getArray(readonly=True),
                rtol=1.0e-12,
                atol=1.0e-12,
            )
            np.testing.assert_array_equal(
                coarse.getArray(readonly=True), coarse_before
            )
            np.testing.assert_array_equal(
                fine_probe.getArray(readonly=True), fine_before
            )
            np.testing.assert_allclose(
                compact_ph.getArray(readonly=True),
                dense_ph.getArray(readonly=True),
                rtol=1.0e-12,
                atol=1.0e-12,
            )
            assert compact_p.norm() > 0.0
            assert compact_ph.norm() > 0.0
            lhs = compact_p.dot(fine_probe)
            rhs = coarse.dot(compact_ph)
            scale = max(abs(lhs), abs(rhs))
            assert scale > 0.0
            assert abs(lhs - rhs) / scale <= 1.0e-10
        finally:
            for vector in vectors:
                vector.destroy()
            if compact is not None:
                compact.destroy()
            if dense is not None:
                dense.destroy()
        assert context_ref is not None and reference_ref is not None
        return context_ref, reference_ref

    context_ref, reference_ref = check_owner_lifecycle()
    gc.collect()
    assert context_ref() is None
    assert reference_ref() is None

    failed_refs = []

    def fail_compact_seed(context, **_kwargs):
        failed_refs.append(
            (weakref.ref(context), weakref.ref(context.reference_matrix))
        )
        raise RuntimeError("test-only compact seed construction failure")

    monkeypatch.setattr(
        transfer_module,
        "_build_compact_same_mesh_hcurl_transfer",
        fail_compact_seed,
    )

    def trigger_failed_build():
        with pytest.raises(RuntimeError, match="test-only compact seed"):
            build_same_mesh_hcurl_owner_transfer(
                data["fine_space"],
                data["fine_floquet"],
                data["coarse_space"],
                data["coarse_floquet"],
                support_policy=support_policy,
                compact_orientation=True,
            )

    trigger_failed_build()
    monkeypatch.undo()
    gc.collect()
    assert failed_refs and all(
        context_ref() is None and reference_ref() is None
        for context_ref, reference_ref in failed_refs
    )


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


@pytest.mark.skipif(
    MPI.COMM_WORLD.size == 8,
    reason="the primal route-plan oracle is serial/MPI2-only",
)
def test_task041_h1b_primal_route_plan_matches_legacy_with_alternation(
    small_fe_fixture,
    monkeypatch,
) -> None:
    data = small_fe_fixture
    fine_space = data["fine_space"]
    coarse_space = data["coarse_space"]
    local_transfer = data["owner"].local_transfer
    common = {
        "local_transfer": local_transfer,
        "optimization_profile": None,
    }
    legacy = build_same_mesh_hcurl_owner_transfer(
        fine_space,
        data["fine_floquet"],
        coarse_space,
        data["coarse_floquet"],
        **common,
    )
    legacy_route_comm = _CountingRouteComm(MPI.COMM_WORLD)
    legacy.comm = legacy_route_comm
    cached = build_same_mesh_hcurl_owner_transfer(
        fine_space,
        data["fine_floquet"],
        coarse_space,
        data["coarse_floquet"],
        reuse_primal_route_plan=True,
        **common,
    )
    route_comm = _CountingRouteComm(MPI.COMM_WORLD)
    cached.comm = route_comm

    # Reverse each cached record's local row order before its first apply.  The
    # paired indices/matrix view keep the same map while forcing recv_order to
    # be non-identity on the real tiny bridge.
    for record in cached._records:
        record["fine_global"] = record["fine_global"][::-1]
        record["fine_local"] = record["fine_local"][::-1]
        record["authority"] = record["authority"][::-1]
        record["matrix"] = record["matrix"][::-1, :]

    coarse_a = create_vector(
        [(coarse_space.dofmap.index_map, int(coarse_space.dofmap.index_map_bs))]
    )
    coarse_b = coarse_a.duplicate()
    fine_a = create_vector(
        [(fine_space.dofmap.index_map, int(fine_space.dofmap.index_map_bs))]
    )
    fine_b = fine_a.duplicate()
    vectors = [coarse_a, coarse_b, fine_a, fine_b]
    outputs = []
    route_p_values = []
    route_ph_values = []
    failed_first = None
    try:
        _fill_algebraic_vector(coarse_a, legacy._coarse_slaves, 2.25)
        _fill_algebraic_vector(coarse_b, legacy._coarse_slaves, -1.5)
        _fill_algebraic_vector(fine_a, legacy._fine_slaves, 3.125)
        _fill_algebraic_vector(fine_b, legacy._fine_slaves, -0.875)
        inputs_before = {
            id(vector): np.asarray(
                vector.getArray(readonly=True), dtype=np.complex128
            ).copy()
            for vector in vectors
        }

        for source in (coarse_a, coarse_b, coarse_a):
            expected = legacy.apply_primal(source)
            actual = cached.apply_primal(source)
            outputs.extend((expected, actual))
            expected_values = np.asarray(
                expected.getArray(readonly=True), dtype=np.complex128
            ).copy()
            actual_values = np.asarray(
                actual.getArray(readonly=True), dtype=np.complex128
            ).copy()
            local_p_checks = (
                bool(
                    np.allclose(
                        actual_values,
                        expected_values,
                        atol=1.0e-11,
                        rtol=1.0e-11,
                    )
                ),
                bool(
                    np.array_equal(
                        source.getArray(readonly=True),
                        inputs_before[id(source)],
                    )
                ),
            )
            p_checks_by_rank = MPI.COMM_WORLD.allgather(local_p_checks)
            assert all(check == (True, True) for check in p_checks_by_rank)
            route_p_values.append(actual_values)
        legacy_preflight_counts = MPI.COMM_WORLD.allgather(
            legacy_route_comm.counts["route_preflight_allgather"]
        )
        assert all(count == 0 for count in legacy_preflight_counts)

        plan = cached._primal_route_plan
        plan_ready_states = MPI.COMM_WORLD.allgather(plan is not None)
        assert all(plan_ready_states)
        assert plan is not None
        local_nontrivial_receive_order = not np.array_equal(
            plan.recv_order,
            np.arange(plan.recv_order.size, dtype=np.int64),
        )
        assert MPI.COMM_WORLD.allreduce(
            int(local_nontrivial_receive_order), op=MPI.MAX
        ) == 1
        last_route_facts = (
            cached.last_apply_facts["primal_route_plan_state"],
            cached.last_apply_facts["primal_route_plan_preflight"],
        )
        route_facts_by_rank = MPI.COMM_WORLD.allgather(last_route_facts)
        assert all(
            facts
            == (
                "reused",
                {
                    "status": "passed",
                    "collective": "allgather_plan_readiness_and_local_validation",
                    "collective_count": 1,
                    "participants": int(MPI.COMM_WORLD.size),
                },
            )
            for facts in route_facts_by_rank
        )
        initial_route_counts = MPI.COMM_WORLD.allgather(dict(route_comm.counts))
        expected_initial_route_counts = {
            "route_preflight_allgather": 3,
            "count_alltoall": 1,
            "id_alltoallv": 1,
            "value_alltoallv": 3,
        }
        assert all(
            counts == expected_initial_route_counts
            for counts in initial_route_counts
        )
        repeated_p_checks = MPI.COMM_WORLD.allgather(
            bool(
                np.allclose(
                    route_p_values[0],
                    route_p_values[2],
                    atol=1.0e-12,
                    rtol=1.0e-12,
                )
            )
        )
        assert all(repeated_p_checks)

        for source in (fine_a, fine_b, fine_a):
            expected = legacy.apply_adjoint(source)
            actual = cached.apply_adjoint(source)
            outputs.extend((expected, actual))
            expected_values = np.asarray(
                expected.getArray(readonly=True), dtype=np.complex128
            ).copy()
            actual_values = np.asarray(
                actual.getArray(readonly=True), dtype=np.complex128
            ).copy()
            local_ph_checks = (
                bool(
                    np.allclose(
                        actual_values,
                        expected_values,
                        atol=1.0e-11,
                        rtol=1.0e-11,
                    )
                ),
                bool(
                    np.array_equal(
                        source.getArray(readonly=True),
                        inputs_before[id(source)],
                    )
                ),
            )
            ph_checks_by_rank = MPI.COMM_WORLD.allgather(local_ph_checks)
            assert all(check == (True, True) for check in ph_checks_by_rank)
            route_ph_values.append(actual_values)

        lhs = outputs[1].dot(fine_a)
        rhs = coarse_a.dot(outputs[7])
        scale = max(abs(lhs), abs(rhs), np.finfo(float).tiny)
        dot_relative = abs(lhs - rhs) / scale
        repeated_ph_match = bool(
            np.allclose(
                route_ph_values[0],
                route_ph_values[2],
                atol=1.0e-12,
                rtol=1.0e-12,
            )
        )
        adjoint_checks_by_rank = MPI.COMM_WORLD.allgather(
            (
                dot_relative <= 1.0e-10,
                repeated_ph_match,
                dict(route_comm.counts),
            )
        )
        expected_after_adjoint_counts = {
            "route_preflight_allgather": 3,
            "count_alltoall": 1,
            "id_alltoallv": 1,
            "value_alltoallv": 3,
        }
        assert all(
            checks[:2] == (True, True)
            and checks[2] == expected_after_adjoint_counts
            for checks in adjoint_checks_by_rank
        )

        original_values_packet = cached._candidate_values_packet
        before_invalid_length = dict(route_comm.counts)
        invalid_rank = 1 if MPI.COMM_WORLD.size > 1 else 0

        def invalid_dynamic_values_length():
            values = original_values_packet()
            if MPI.COMM_WORLD.rank == invalid_rank:
                return np.concatenate(
                    (values, np.asarray((1.0 + 0.5j,), dtype=np.complex128))
                )
            return values

        monkeypatch.setattr(
            cached, "_candidate_values_packet", invalid_dynamic_values_length
        )
        try:
            cached.apply_primal(coarse_a)
        except (RuntimeError, ValueError) as exc:
            invalid_length_error = str(exc)
        else:
            invalid_length_error = None
        invalid_length_errors = MPI.COMM_WORLD.allgather(invalid_length_error)
        invalid_length_progress = MPI.COMM_WORLD.allgather("after_values_size_reject")
        invalid_length_statuses = MPI.COMM_WORLD.allgather(
            cached._last_primal_route_preflight["status"]
        )
        invalid_length_counts = MPI.COMM_WORLD.allgather(
            dict(route_comm.counts)
        )
        invalid_length_inputs_unchanged = MPI.COMM_WORLD.allgather(
            bool(
                np.array_equal(
                    coarse_a.getArray(readonly=True),
                    inputs_before[id(coarse_a)],
                )
            )
        )
        assert invalid_length_errors[0] is not None
        assert all(error == invalid_length_errors[0] for error in invalid_length_errors)
        assert all(
            error
            == "same-mesh primal route preflight rejected: "
            "local_binding_or_values_shape_mismatch"
            for error in invalid_length_errors
        )
        assert all(value == "after_values_size_reject" for value in invalid_length_progress)
        assert all(
            status == "local_binding_or_values_shape_mismatch"
            for status in invalid_length_statuses
        )
        assert all(
            counts
            == {
                **before_invalid_length,
                "route_preflight_allgather": (
                    before_invalid_length["route_preflight_allgather"] + 1
                ),
            }
            for counts in invalid_length_counts
        )
        assert all(invalid_length_inputs_unchanged)
        monkeypatch.setattr(cached, "_candidate_values_packet", original_values_packet)

        if MPI.COMM_WORLD.size > 1:
            saved_plan = cached._primal_route_plan
            if MPI.COMM_WORLD.rank == 1:
                cached._primal_route_plan = None
            try:
                cached.apply_primal(coarse_a)
            except (RuntimeError, ValueError) as exc:
                readiness_error = str(exc)
            else:
                readiness_error = None
            readiness_errors = MPI.COMM_WORLD.allgather(readiness_error)
            readiness_progress = MPI.COMM_WORLD.allgather("after_plan_state_reject")
            readiness_statuses = MPI.COMM_WORLD.allgather(
                cached._last_primal_route_preflight["status"]
            )
            readiness_counts = MPI.COMM_WORLD.allgather(
                dict(route_comm.counts)
            )
            cached._primal_route_plan = saved_plan
            assert readiness_errors[0] is not None
            assert all(error == readiness_errors[0] for error in readiness_errors)
            assert all(
                error
                == "same-mesh primal route preflight rejected: "
                "plan_readiness_mismatch"
                for error in readiness_errors
            )
            assert all(value == "after_plan_state_reject" for value in readiness_progress)
            assert all(
                status == "plan_readiness_mismatch"
                for status in readiness_statuses
            )
            expected_readiness_counts = {
                "route_preflight_allgather": 5,
                "count_alltoall": 1,
                "id_alltoallv": 1,
                "value_alltoallv": 3,
            }
            assert all(
                counts == expected_readiness_counts for counts in readiness_counts
            )

        after_preflight_counts = MPI.COMM_WORLD.allgather(dict(route_comm.counts))
        expected_after_preflight_counts = {
            "route_preflight_allgather": (4 if MPI.COMM_WORLD.size == 1 else 5),
            "count_alltoall": 1,
            "id_alltoallv": 1,
            "value_alltoallv": 3,
        }
        assert all(
            counts == expected_after_preflight_counts
            for counts in after_preflight_counts
        )

        _unique, inverse, counts = np.unique(
            plan.candidate_ids, return_inverse=True, return_counts=True
        )
        if np.any(counts > 1):
            duplicate_group = int(np.flatnonzero(counts > 1)[0])
            duplicate_position = int(
                np.flatnonzero(inverse == duplicate_group)[-1]
            )
        else:
            duplicate_position = None
        duplicate_ranks = MPI.COMM_WORLD.allreduce(
            int(duplicate_position is not None), op=MPI.MAX
        )
        assert duplicate_ranks == 1
        original_values_packet = cached._candidate_values_packet

        def mismatched_duplicate_values():
            values = original_values_packet()
            if duplicate_position is not None:
                values[duplicate_position] += 1.0e-4 + 2.0e-4j
            return values

        monkeypatch.setattr(
            cached, "_candidate_values_packet", mismatched_duplicate_values
        )
        try:
            cached.apply_primal(coarse_a)
        except (RuntimeError, ValueError) as exc:
            cached_duplicate_error = str(exc)
        else:
            cached_duplicate_error = None
        cached_duplicate_errors = MPI.COMM_WORLD.allgather(cached_duplicate_error)
        cached_duplicate_progress = MPI.COMM_WORLD.allgather(
            "after_cached_duplicate_reject"
        )
        cached_duplicate_counts = MPI.COMM_WORLD.allgather(
            dict(route_comm.counts)
        )
        cached_duplicate_inputs_unchanged = MPI.COMM_WORLD.allgather(
            bool(
                np.array_equal(
                    coarse_a.getArray(readonly=True),
                    inputs_before[id(coarse_a)],
                )
            )
        )
        cached_duplicate_plan_states = MPI.COMM_WORLD.allgather(
            cached._primal_route_plan is plan
        )
        assert cached_duplicate_errors[0] is not None
        assert all(error == cached_duplicate_errors[0] for error in cached_duplicate_errors)
        assert "same-mesh owner row candidates disagree" in cached_duplicate_errors[0]
        assert all(
            value == "after_cached_duplicate_reject"
            for value in cached_duplicate_progress
        )
        expected_cached_duplicate_counts = {
            "route_preflight_allgather": (5 if MPI.COMM_WORLD.size == 1 else 6),
            "count_alltoall": 1,
            "id_alltoallv": 1,
            "value_alltoallv": 4,
        }
        assert all(
            counts == expected_cached_duplicate_counts
            for counts in cached_duplicate_counts
        )
        assert all(cached_duplicate_inputs_unchanged)
        assert all(cached_duplicate_plan_states)
        legacy_plan_states = MPI.COMM_WORLD.allgather(
            legacy._primal_route_plan is None
        )
        assert all(legacy_plan_states)

        failed_first = build_same_mesh_hcurl_owner_transfer(
            fine_space,
            data["fine_floquet"],
            coarse_space,
            data["coarse_floquet"],
            local_transfer=local_transfer,
            reuse_primal_route_plan=True,
        )
        for record in failed_first._records:
            record["fine_global"] = record["fine_global"][::-1]
            record["fine_local"] = record["fine_local"][::-1]
            record["authority"] = record["authority"][::-1]
            record["matrix"] = record["matrix"][::-1, :]
        failed_comm = _CountingRouteComm(MPI.COMM_WORLD)
        failed_first.comm = failed_comm
        failed_ids = failed_first._candidate_ids_packet()
        _failed_unique, failed_inverse, failed_counts = np.unique(
            failed_ids, return_inverse=True, return_counts=True
        )
        if np.any(failed_counts > 1):
            failed_group = int(np.flatnonzero(failed_counts > 1)[0])
            failed_position = int(
                np.flatnonzero(failed_inverse == failed_group)[-1]
            )
        else:
            failed_position = None
        assert MPI.COMM_WORLD.allreduce(
            int(failed_position is not None), op=MPI.MAX
        ) == 1
        failed_values_packet = failed_first._candidate_values_packet

        def first_route_duplicate_values():
            values = failed_values_packet()
            if failed_position is not None:
                values[failed_position] += 1.0e-4 + 2.0e-4j
            return values

        monkeypatch.setattr(
            failed_first,
            "_candidate_values_packet",
            first_route_duplicate_values,
        )
        try:
            failed_first.apply_primal(coarse_a)
        except (RuntimeError, ValueError) as exc:
            first_route_error = str(exc)
        else:
            first_route_error = None
        first_route_errors = MPI.COMM_WORLD.allgather(first_route_error)
        first_route_progress = MPI.COMM_WORLD.allgather(
            "after_first_duplicate_reject"
        )
        first_route_plans = MPI.COMM_WORLD.allgather(
            failed_first._primal_route_plan is None
        )
        first_route_counts = MPI.COMM_WORLD.allgather(dict(failed_comm.counts))
        assert first_route_errors[0] is not None
        assert all(error == first_route_errors[0] for error in first_route_errors)
        assert "same-mesh owner row candidates disagree" in first_route_errors[0]
        assert all(
            value == "after_first_duplicate_reject" for value in first_route_progress
        )
        assert all(first_route_plans)
        expected_first_route_counts = {
            "route_preflight_allgather": 1,
            "count_alltoall": 1,
            "id_alltoallv": 1,
            "value_alltoallv": 1,
        }
        assert all(counts == expected_first_route_counts for counts in first_route_counts)
    finally:
        if failed_first is not None:
            failed_first.destroy()
        for vector in outputs:
            vector.destroy()
        for vector in vectors:
            vector.destroy()
        legacy.destroy()
        cached.destroy()
    assert cached._primal_route_plan is None
    assert local_transfer.audit["global_transfer_matrix"] is False
