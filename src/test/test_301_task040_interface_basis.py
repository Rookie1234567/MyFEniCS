"""Focused Task040 V1-2 artificial-interface basis contracts."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import numpy as np
import pytest
from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_interface_basis import (
    build_artificial_gamma_column,
    build_group_basis_columns,
    build_lower_fourier_trace_columns,
    build_mass_dual_from_active_vec,
    build_mass_dual_columns,
    canonical_external_mode_metadata_sha256,
    canonical_mode_keys_sha256,
    canonical_selected_packet_beta_sha256,
    collect_streamed_trace_basis,
    map_lifted_trace_to_gamma_rows,
    tangential_fourier_trace,
)
from src.solvers.hybrid_interface_schur import build_petsc_interface_schur_oracle
from src.coupling.hybrid_internal_modes import _ReusableInterfaceLifter


def _bare(size: int = 8) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, size), (PETSc.DECIDE, size)),
        nnz=size,
        comm=MPI.COMM_WORLD,
    )
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        for col in range(size):
            value = (0.04 + 0.01j) * (row + 1) * (col + 1)
            if row == col:
                value += 2.0 + 0.2j * row
            matrix.setValue(row, col, PETSc.ScalarType(value))
    matrix.assemble()
    return matrix


def _oracle():
    bare = _bare()
    first, last = map(int, bare.getOwnershipRange())
    groups = ((0, 1, 2, 3), (6, 2, 3, 4, 5), (6, 7))
    local_groups = tuple(
        np.asarray([row for row in rows if first <= row < last], dtype=PETSc.IntType)
        for rows in groups
    )
    oracle = build_petsc_interface_schur_oracle(bare, local_groups, ((2, 3), (6,)))
    return bare, oracle


def test_public_gamma_rows_bind_local_order_and_hash():
    bare, oracle = _oracle()
    try:
        for group, expected_global in enumerate(((2, 3), (6, 2, 3), (6,))):
            rows = oracle.group_gamma_rows_local(group)
            first, last = map(int, bare.getOwnershipRange())
            expected = np.asarray(
                [row for row in expected_global if first <= row < last],
                dtype=PETSc.IntType,
            )
            assert np.array_equal(rows, expected)
            layout = oracle.group_gamma_layout(group)
            assert layout["local_size"] == len(expected)
            assert layout["gamma_rows_local_sha256"]
            assert layout["gamma_rows_global_order_sha256"]
            joined = np.asarray(
                [
                    row
                    for part in MPI.COMM_WORLD.allgather(expected.tolist())
                    for row in part
                ],
                dtype=np.int64,
            )
            assert (
                layout["gamma_rows_global_order_sha256"]
                == hashlib.sha256(np.ascontiguousarray(joined).tobytes()).hexdigest()
            )
            rows[:] = -1
            assert np.array_equal(oracle.group_gamma_rows_local(group), expected)
            all_hashes = MPI.COMM_WORLD.allgather(
                layout["gamma_rows_global_order_sha256"]
            )
            assert len(set(all_hashes)) == 1
        assert MPI.COMM_WORLD.allreduce(True, op=MPI.LAND)
    finally:
        oracle.destroy()
        bare.destroy()


def test_lower_fourier_trace_phase_and_identity_contract():
    modes = [
        SimpleNamespace(
            side="bottom",
            m=0,
            n=0,
            polarization="s",
            alpha=0.3 + 0.1j,
            gamma=-0.2 + 0.05j,
            beta=1.2 + 0.03j,
            vertical_sign=-1,
            propagating=True,
            rayleigh_warning=False,
            e_vector=np.array([1.0 + 0.2j, 0.4 - 0.1j, 0.0]),
            k_vector=np.array([0.3 + 0.1j, -0.2 + 0.05j, -1.2 - 0.03j]),
        ),
        SimpleNamespace(
            side="bottom",
            m=0,
            n=1,
            polarization="p",
            alpha=-0.1 + 0.02j,
            gamma=0.7 - 0.05j,
            beta=0.8 + 0.02j,
            vertical_sign=-1,
            propagating=True,
            rayleigh_warning=False,
            e_vector=np.array([0.2 - 0.3j, 1.0 + 0.1j, 0.0]),
            k_vector=np.array([-0.1 + 0.02j, 0.7 - 0.05j, -0.8 - 0.02j]),
        ),
    ]
    xy = np.array([[0.0, 0.0], [0.2, -0.4]], dtype=float)
    expected_keys = (
        {"m": 0, "n": 1, "polarization": "p", "side": "bottom"},
        {"m": 0, "n": 0, "polarization": "s", "side": "bottom"},
    )
    expected_metadata = (
        {
            "side": "bottom",
            "m": 0,
            "n": 1,
            "polarization": "p",
            "beta": [0.8, 0.02],
            "propagating": True,
            "rayleigh_warning": False,
        },
        {
            "side": "bottom",
            "m": 0,
            "n": 0,
            "polarization": "s",
            "beta": [1.2, 0.03],
            "propagating": True,
            "rayleigh_warning": False,
        },
    )
    result = build_lower_fourier_trace_columns(
        modes,
        xy,
        -3.333333333333333,
        expected_count=2,
        expected_keys=expected_keys,
        expected_key_sha256=canonical_mode_keys_sha256(expected_keys),
        expected_metadata=expected_metadata,
        expected_metadata_sha256=canonical_external_mode_metadata_sha256(
            expected_metadata
        ),
        frozen_manifest_beta_metadata_sha256=(
            "a58a3c6bc335bb5ae7f6b929a7abce4c193dedb27b115f17304091afb353318c"
        ),
        trace_to_gamma=lambda value, info: value[:, 0] + 0.5 * value[:, 1],
    )
    expected = tangential_fourier_trace(
        modes[0].e_vector,
        modes[0].alpha,
        modes[0].gamma,
        modes[0].k_vector[2],
        xy,
        -3.333333333333333,
    )
    assert result["values"].shape == (2, 2)
    expected_second = tangential_fourier_trace(
        modes[1].e_vector,
        modes[1].alpha,
        modes[1].gamma,
        modes[1].k_vector[2],
        xy,
        -3.333333333333333,
    )
    assert np.allclose(
        result["values"][:, 0], expected_second[:, 0] + 0.5 * expected_second[:, 1]
    )
    assert np.allclose(result["values"][:, 1], expected[:, 0] + 0.5 * expected[:, 1])
    assert result["metadata"][0]["polarization"] == "p"
    assert result["metadata"][0]["branch"] == "outgoing_bottom"
    assert result["basis_global_replicated"] is False
    assert result["mode_count"] == 2
    assert result["frozen_manifest_beta_metadata_reproducible"] is False
    bad = list(modes)
    bad[1] = SimpleNamespace(**{**vars(modes[1]), "vertical_sign": 1})
    with pytest.raises(ValueError, match="branch"):
        build_lower_fourier_trace_columns(
            bad,
            xy,
            0.0,
            expected_count=2,
            expected_keys=expected_keys,
            expected_key_sha256=canonical_mode_keys_sha256(expected_keys),
            expected_metadata=expected_metadata,
            expected_metadata_sha256=canonical_external_mode_metadata_sha256(
                expected_metadata
            ),
            frozen_manifest_beta_metadata_sha256=(
                "a58a3c6bc335bb5ae7f6b929a7abce4c193dedb27b115f17304091afb353318c"
            ),
            trace_to_gamma=lambda value, info: value[:, 0],
        )


def test_streamed_right_left_columns_are_ordered_and_not_hydrated():
    events: list[tuple[int, str]] = []
    keys = (("upper", 0), ("upper", 1))

    def trace(values, info, side):
        events.append((int(info["mode_key"][1]), side))
        return np.asarray(values, dtype=np.complex128).reshape(2)

    def stream(callback):
        for index in range(2):
            callback(
                index,
                np.array([1.0 + 0.2j + index, 2.0 - 0.1j]),
                np.array([0.4 + 0.3j + index, 1.0 + 0.2j]),
                {
                    "branch": "positive",
                    "mode_key": keys[index],
                    "beta": (0.7 + 0.2j) * (index + 1),
                },
            )
        return {"arrays_retained": False, "consumer_qep_required": False}

    result = collect_streamed_trace_basis(
        stream,
        indices=(0, 1),
        trace_from_values=trace,
        expected_mode_keys=keys,
        expected_mode_key_sha256=canonical_mode_keys_sha256(keys),
        expected_betas=(0.7 + 0.2j, 1.4 + 0.4j),
        expected_selected_packet_beta_sha256=canonical_selected_packet_beta_sha256(
            (0.7 + 0.2j, 1.4 + 0.4j)
        ),
    )
    assert result["right"].shape == (2, 2)
    assert result["left"].shape == (2, 2)
    assert result["transient_pair_peak"] == 1
    assert result["arrays_retained"] is False
    assert result["qep_calls"] == 0
    assert events == [(0, "right"), (0, "left"), (1, "right"), (1, "left")]

    def wrong_order(callback):
        callback(
            1,
            np.ones(2),
            np.ones(2),
            {"branch": "positive", "mode_key": keys[1], "beta": 0.7 + 0.2j},
        )
        return {"arrays_retained": False, "consumer_qep_required": False}

    with pytest.raises(ValueError, match="order"):
        collect_streamed_trace_basis(
            wrong_order,
            indices=(0, 1),
            trace_from_values=trace,
            expected_mode_keys=keys,
            expected_mode_key_sha256=canonical_mode_keys_sha256(keys),
            expected_betas=(0.7 + 0.2j, 1.4 + 0.4j),
            expected_selected_packet_beta_sha256=canonical_selected_packet_beta_sha256(
                (0.7 + 0.2j, 1.4 + 0.4j)
            ),
        )


def test_mass_dual_and_group_basis_keep_nontrivial_identity():
    mass = np.array(
        [[2.0, 0.3 - 0.2j, 0.0], [0.3 + 0.2j, 1.7, 0.1], [0.0, 0.1, 1.2]],
        dtype=np.complex128,
    )
    left = np.array(
        [[1.0 + 0.2j, 0.1], [0.4 - 0.3j, 1.0], [0.2, -0.2j]],
        dtype=np.complex128,
    )
    right = np.array(
        [[0.7, 0.1 + 0.2j], [0.2 - 0.1j, 0.8], [0.4, 0.3 + 0.1j]],
        dtype=np.complex128,
    )
    dual = build_mass_dual_columns(left, lambda value: mass @ value)
    assert not np.allclose(dual, right)
    assert not np.allclose(dual.conj().T @ right, np.eye(2))
    assert np.allclose(dual.conj().T @ right, left.conj().T @ mass @ right)

    lower_rows = np.array([20], dtype=np.int64)
    upper_rows = np.array([40, 50], dtype=np.int64)
    group_rows = np.array([50, 20, 40], dtype=np.int64)
    group = build_group_basis_columns(
        1,
        group_rows,
        lower_rows,
        np.array([[1.0, 2.0]], dtype=np.complex128),
        upper_rows,
        np.array([[3.0, 4.0, 5.0], [6.0, 7.0, 8.0]], dtype=np.complex128),
    )
    assert group.shape == (3, 5)
    assert np.array_equal(group[1, :2], [1.0, 2.0])
    assert np.array_equal(group[2, 2:], [3.0, 4.0, 5.0])
    assert np.array_equal(group[0, 2:], [6.0, 7.0, 8.0])
    with pytest.raises(ValueError, match="supports"):
        build_group_basis_columns(
            1,
            np.array([20, 40]),
            lower_rows,
            np.ones((1, 1)),
            np.array([20]),
            np.ones((1, 1)),
        )


def test_lifted_trace_maps_original_active_to_public_gamma_order_and_releases():
    constraints = SimpleNamespace(
        owned_active_original_dofs=np.array([10, 11], dtype=np.int64),
        original_to_active={10: 4, 11: 7},
        expansion_by_original={
            10: (np.array([4]), np.array([1.0 + 0.0j])),
            11: (np.array([7]), np.array([1.0 + 0.0j])),
        },
    )
    state: list[str] = []
    field = object()

    def lift(source):
        assert source == "trace"
        return field, 1

    result = map_lifted_trace_to_gamma_rows(
        "trace",
        lift_trace=lift,
        constraints=constraints,
        plane_original_dofs=(10, 11),
        gamma_rows_local=(7, 4),
        homogenize=lambda value: state.append("homogenize"),
        scatter=lambda value: state.append("scatter"),
        read_owned_original_values=lambda value, rows: {10: 1.0 + 2.0j, 11: -3.0j},
        release_lifted=lambda value: state.append("release"),
    )
    assert np.array_equal(result, [0.0 - 3.0j, 1.0 + 2.0j])
    assert state == ["homogenize", "scatter", "release"]
    with pytest.raises(ValueError, match="Gamma"):
        map_lifted_trace_to_gamma_rows(
            "trace",
            lift_trace=lift,
            constraints=constraints,
            plane_original_dofs=(10, 11),
            gamma_rows_local=(4, 5),
            homogenize=lambda value: None,
            scatter=lambda value: None,
            read_owned_original_values=lambda value, rows: {10: 1.0, 11: 2.0},
        )


def test_runtime_gamma_and_full_active_mass_adapters_use_authority_order():
    constraints = SimpleNamespace(
        owned_active_original_dofs=np.array([10, 11], dtype=np.int64),
        original_to_active={10: 4, 11: 7},
        expansion_by_original={
            10: (np.array([4]), np.array([1.0 + 0.0j])),
            11: (np.array([7]), np.array([1.0 + 0.0j])),
        },
    )
    state: list[str] = []

    class FakeVec:
        def __init__(self, values):
            self.array = np.asarray(values, dtype=np.complex128)

        def getOwnershipRange(self):
            return (0, self.array.size)

        def getValues(self, rows):
            return np.asarray([self.array[int(row)] for row in rows])

    field_values = np.zeros(12, dtype=np.complex128)
    field_values[10] = 1.0 + 2.0j
    field_values[11] = -3.0j
    field = SimpleNamespace(
        x=SimpleNamespace(petsc_vec=FakeVec(field_values), scatter_forward=lambda: None)
    )
    lifter = SimpleNamespace(lift=lambda source: (field, 1))
    mpc = SimpleNamespace(homogenize=lambda value: state.append("homogenize"))
    system = SimpleNamespace(floquet_data=SimpleNamespace(mpc=mpc))
    column = build_artificial_gamma_column(
        "source",
        system=system,
        condensed=SimpleNamespace(trace_constraints=constraints),
        interface_z_nm=4.0,
        plane_cell_side="lower",
        plane_original_dofs=(10, 11),
        gamma_rows_local=(7, 4),
        lifter=lifter,
    )
    assert np.array_equal(column, [-3j, 1 + 2j])
    assert state == ["homogenize"]

    matrix = np.array(
        [
            [2.0, 0.1, 0.2, 0.0, 0.0],
            [0.1, 1.7, 0.0, 0.3 - 0.1j, 0.0],
            [0.2, 0.0, 1.4, 0.2, 0.1],
            [0.0, 0.3 + 0.1j, 0.2, 1.8, 0.2j],
            [0.0, 0.0, 0.1, -0.2j, 1.2],
        ],
        dtype=np.complex128,
    )

    class FakeActive:
        def __init__(self):
            self.array = np.zeros(5, dtype=np.complex128)

        def duplicate(self):
            return FakeActive()

        def getOwnershipRange(self):
            return (0, 5)

        def set(self, value):
            self.array[:] = value

        def assemble(self):
            return None

        def destroy(self):
            self.array = np.empty(0, dtype=np.complex128)

    class FakeMatrix:
        def mult(self, source, target):
            target.array[:] = matrix @ source.array

    left = np.array([[1.0 + 0.2j, 0.1], [0.3 - 0.1j, 1.0]], dtype=np.complex128)
    audit = {}
    dual = build_mass_dual_from_active_vec(
        SimpleNamespace(matrix=FakeMatrix()),
        SimpleNamespace(create_active_vector=FakeActive),
        (1, 3),
        left,
        audit=audit,
    )
    assert np.allclose(dual, matrix[np.ix_((1, 3), (1, 3))] @ left)
    assert audit == {
        "mass_action_count": 2,
        "mass_integrated_once": True,
        "mass_source": "ArtificialZTraceMass.matrix",
    }


def test_real_dolfinx_arbitrary_z_lifter_and_petsc_cross_row_mass_action():
    comm = MPI.COMM_WORLD
    msh = mesh.create_unit_cube(
        comm,
        2,
        2,
        2,
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    V = fem.functionspace(
        msh, element("N1curl", msh.basix_cell(), 1, dtype=default_real_type)
    )
    target_space = fem.functionspace(
        msh,
        element("DG", msh.basix_cell(), 1, shape=(3,), dtype=default_real_type),
    )
    mesh_data = SimpleNamespace(
        mesh_axis_cell_stats={"x": {"max": 1.0}, "y": {"max": 1.0}}
    )
    local_mesh = SimpleNamespace(mesh=msh, mesh_data=mesh_data)
    system = SimpleNamespace(local_mesh=local_mesh, V=V, side="bottom")
    lower = _ReusableInterfaceLifter(
        system,
        target_space=target_space,
        interface_z_nm=0.5,
        plane_cell_side="lower",
    )
    upper = _ReusableInterfaceLifter(
        system,
        target_space=target_space,
        interface_z_nm=0.5,
        plane_cell_side="upper",
    )
    try:
        geometry = np.asarray(msh.geometry.x)
        geometry_dofmap = np.asarray(msh.geometry.dofmap)
        lower_z = [
            float(np.max(geometry[geometry_dofmap[int(cell)], 2]))
            for cell in lower.cells
        ]
        upper_z = [
            float(np.min(geometry[geometry_dofmap[int(cell)], 2]))
            for cell in upper.cells
        ]
        assert all(np.isclose(value, 0.5) for value in lower_z)
        assert all(np.isclose(value, 0.5) for value in upper_z)
        assert comm.allreduce(len(lower.cells) > 0, op=MPI.LOR)
        assert comm.allreduce(len(upper.cells) > 0, op=MPI.LOR)

        field = fem.Function(V)
        vector = field.x.petsc_vec
        first, last = map(int, vector.getOwnershipRange())
        has_two = last - first >= 2
        assert comm.allreduce(has_two, op=MPI.LAND)
        plane = np.asarray([first, first + 1], dtype=np.int64)
        field.x.array[:2] = np.asarray([1.0 + 2.0j, -3.0j], dtype=PETSc.ScalarType)
        field.x.scatter_forward()
        constraints = SimpleNamespace(
            owned_active_original_dofs=plane.copy(),
            original_to_active={
                int(plane[0]): int(plane[0]),
                int(plane[1]): int(plane[1]),
            },
            expansion_by_original={
                int(plane[0]): (np.asarray([plane[0]]), np.asarray([1.0 + 0.0j])),
                int(plane[1]): (np.asarray([plane[1]]), np.asarray([1.0 + 0.0j])),
            },
        )
        system.floquet_data = SimpleNamespace(
            mpc=SimpleNamespace(homogenize=lambda value: None)
        )
        column = build_artificial_gamma_column(
            "unused-source",
            system=system,
            condensed=SimpleNamespace(trace_constraints=constraints),
            interface_z_nm=0.5,
            plane_cell_side="lower",
            plane_original_dofs=plane,
            gamma_rows_local=(int(plane[1]), int(plane[0])),
            lifter=SimpleNamespace(lift=lambda source: (field, 0)),
        )
        assert np.allclose(column, [-3.0j, 1.0 + 2.0j])

        active_template = PETSc.Vec().createMPI(4, comm=comm)
        first_active, last_active = map(int, active_template.getOwnershipRange())
        rows = np.arange(first_active, last_active, dtype=np.int64)
        matrix = PETSc.Mat().createAIJ(
            size=((PETSc.DECIDE, 4), (PETSc.DECIDE, 4)), nnz=4, comm=comm
        )
        first_matrix, last_matrix = map(int, matrix.getOwnershipRange())
        dense = np.array(
            [
                [2.0, 0.2, 0.0, 0.1],
                [0.2, 1.5, 0.3, 0.0],
                [0.0, 0.3, 1.8, 0.4],
                [0.1, 0.0, 0.4, 1.2],
            ],
            dtype=np.complex128,
        )
        for row in range(first_matrix, last_matrix):
            for col in range(4):
                matrix.setValue(row, col, PETSc.ScalarType(dense[row, col]))
        matrix.assemble()
        left_local = np.asarray(
            [[1.0 + 0.1j * int(row)] for row in rows], dtype=np.complex128
        )
        mass_audit = {}
        dual = build_mass_dual_from_active_vec(
            SimpleNamespace(matrix=matrix),
            SimpleNamespace(create_active_vector=active_template.duplicate),
            rows,
            left_local,
            audit=mass_audit,
        )
        full_left = np.asarray(
            [1.0 + 0.1j * row for row in range(4)], dtype=np.complex128
        )
        expected = (dense @ full_left)[rows]
        assert np.allclose(dual[:, 0], expected)
        assert mass_audit["mass_action_count"] == 1
        assert mass_audit["mass_integrated_once"] is True
        matrix.destroy()
        active_template.destroy()
    finally:
        del lower, upper, target_space, V, msh
