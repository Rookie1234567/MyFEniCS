"""Tiny Task040 side-impedance and transmission contracts."""

from __future__ import annotations

import numpy as np
import pytest
import ufl
from types import SimpleNamespace

from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.common.config_3d import SimulationConfig3D
from src.solvers.hcurl_assembly_time_condensation import (
    build_unconstrained_assembly_time_condensation,
)
from src.solvers.hybrid_moving_pml import build_moving_pml_full_state_action
from src.solvers.hybrid_side_impedance import (
    ArtificialZTraceMass,
    TASK040_BACKWARD_ORDER,
    TASK040_FORWARD_ORDER,
    TASK040_LEVEL_A_SOURCE_LABELS,
    TASK040_LEVEL_A_SUBDOMAINS,
    assemble_reduced_artificial_interface_tangential_mass,
    audit_petsc_level_a_one_apply,
    audit_artificial_z_interface_support,
    build_petsc_side_impedance_transmission_action,
    build_first_order_petsc_interface_impedance,
    build_first_order_interface_impedance,
    build_first_order_tangential_impedance,
    build_level_a_cell_recovery_group_rows,
    build_level_a_oracle,
    build_side_impedance_transmission_action,
)
from src.solvers.hybrid_layer_block import run_v1_1_right_preconditioned_fgmres_batch


def _moving_pml_tiny_fixture():
    comm = MPI.COMM_WORLD
    msh = mesh.create_unit_cube(
        comm,
        1,
        1,
        6,
        cell_type=mesh.CellType.hexahedron,
        ghost_mode=mesh.GhostMode.shared_facet,
    )
    cell_count = int(msh.topology.index_map(msh.topology.dim).size_local)
    cell_tags = mesh.meshtags(
        msh,
        msh.topology.dim,
        np.arange(cell_count, dtype=np.int32),
        np.ones(cell_count, dtype=np.int32),
    )
    V = fem.functionspace(
        msh,
        element("N1curl", msh.basix_cell(), 2, dtype=default_real_type),
    )
    cfg = SimulationConfig3D(
        lambda0=2.0 * np.pi,
        n_air=1.0 + 0.05j,
        mesh_cell_type="hexahedron",
        nedelec_degree=2,
    )
    u = ufl.TrialFunction(V)
    v = ufl.TestFunction(V)
    dx = ufl.Measure("dx", domain=msh, subdomain_data=cell_tags)
    compiled = fem.form(
        (
            PETSc.ScalarType(1.0 / cfg.mu_r) * ufl.inner(ufl.curl(u), ufl.curl(v))
            - cfg.k0**2 * PETSc.ScalarType(cfg.eps_air) * ufl.inner(u, v)
        )
        * dx(1)
    )
    condensed = build_unconstrained_assembly_time_condensation(
        compiled,
        V,
        cell_tags,
        materialize_global_matrix=True,
        retain_local_schur_for_matrix_free=True,
    )
    assert condensed.matrix is not None
    z_values = np.linspace(0.0, 1.0, 7)
    system = SimpleNamespace(
        V=V,
        cfg=cfg,
        local_mesh=SimpleNamespace(
            mesh=msh,
            mesh_data=SimpleNamespace(mesh=msh, cell_tags=cell_tags),
            z_values=z_values,
        ),
        static_condensation=SimpleNamespace(condensed=condensed),
        floquet_data=SimpleNamespace(mpc=None),
    )
    return msh, V, system, condensed


def _tiny_level_a_builder():
    comm = MPI.COMM_WORLD
    global_rows = 6
    bare = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, global_rows), (PETSc.DECIDE, global_rows)),
        nnz=2,
        comm=comm,
    )
    first, last = map(int, bare.getOwnershipRange())
    for row in range(first, last):
        bare.setValue(row, row, PETSc.ScalarType(3.0 + 0.2 * row))
    bare.assemble()
    masses = []
    for active_row in (2, 4):
        matrix = PETSc.Mat().createAIJ(
            size=((PETSc.DECIDE, global_rows), (PETSc.DECIDE, global_rows)),
            nnz=1,
            comm=comm,
        )
        if first <= active_row < last:
            matrix.setValue(active_row, active_row, PETSc.ScalarType(1.0))
        matrix.assemble()
        masses.append(
            ArtificialZTraceMass(
                matrix,
                {
                    "active_support_count": 1,
                    "support_sha256": f"tiny-{active_row}",
                },
            )
        )
    groups = tuple(
        np.asarray(
            [row for row in rows if first <= row < last],
            dtype=PETSc.IntType,
        )
        for rows in ((0, 1, 2), (2, 3, 4), (4, 5))
    )
    return bare, masses, groups


def _tiny_artificial_z_fixture():
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
        msh, element("N1curl", "hexahedron", 1, dtype=default_real_type)
    )
    global_rows = int(V.dofmap.index_map.size_global)
    expansion = {
        row: (
            np.asarray([row], dtype=PETSc.IntType),
            np.asarray([1.0], dtype=np.complex128),
        )
        for row in range(global_rows)
    }
    local_start, local_stop = map(int, V.dofmap.index_map.local_range)
    condensed = SimpleNamespace(
        full_rows=global_rows,
        active_rows=global_rows,
        owned_active_rows=local_stop - local_start,
        trace_constraints=SimpleNamespace(expansion_by_original=expansion),
    )
    bare = PETSc.Mat().createAIJ(
        size=(
            (local_stop - local_start, global_rows),
            (local_stop - local_start, global_rows),
        ),
        nnz=1,
        comm=comm,
    )
    for row in range(local_start, local_stop):
        bare.setValue(row, row, PETSc.ScalarType(1.0))
    bare.assemble()
    return msh, V, condensed, bare


def test_artificial_z_mass_uses_two_sided_support_and_single_trace_integral():
    _msh, V, condensed, bare = _tiny_artificial_z_fixture()
    support = audit_artificial_z_interface_support(V, condensed, 0.5)
    assert support["facet_count_global"] == 4
    assert support["support_sets_exact_match"] is True
    assert support["lower_support"] == support["upper_support"]
    mass = assemble_reduced_artificial_interface_tangential_mass(
        V, condensed, support, bare_operator=bare
    )
    pair = build_first_order_petsc_interface_impedance(mass, 0.41 + 0.17j, (1, -1))
    q = -1j * (0.41 + 0.17j)
    probe = mass.matrix.createVecRight()
    expected = mass.matrix.createVecLeft()
    observed = mass.matrix.createVecLeft()
    local_start, local_stop = map(int, V.dofmap.index_map.local_range)
    try:
        probe.array[:] = np.asarray(
            [0.2 + 0.03j * index for index in range(local_start, local_stop)],
            dtype=PETSc.ScalarType,
        )
        probe.assemble()
        mass.matrix.mult(probe, expected)
        physical_field = fem.Function(V)
        physical_field.interpolate(
            lambda x: np.vstack(
                (
                    np.ones(x.shape[1]),
                    np.zeros(x.shape[1]),
                    np.zeros(x.shape[1]),
                )
            )
        )
        physical_field.x.scatter_forward()
        physical_image = mass.matrix.createVecLeft()
        try:
            mass.matrix.mult(physical_field.x.petsc_vec, physical_image)
            physical_checksum = complex(physical_field.x.petsc_vec.dot(physical_image))
            assert abs(physical_checksum - 1.0) <= 1.0e-12
            assert abs(physical_checksum.imag) <= 1.0e-12
        finally:
            physical_image.destroy()
        for matrix in pair:
            matrix.mult(probe, observed)
            difference = observed.duplicate()
            try:
                observed.copy(difference)
                difference.axpy(PETSc.ScalarType(-q), expected)
                assert float(difference.norm()) <= 1.0e-12
            finally:
                difference.destroy()
        audit = mass.audit
        assert audit["mass_integral_count"] == 1
        assert audit["trace_side_integrated"] == "+"
        assert audit["finite"] is True
        assert audit["hermitian_relative_defect"] <= 1.0e-10
        assert audit["rayleigh_probe_nonnegative"] is True
        assert audit["bare_operator_unchanged"] is True
        assert "raw_support" not in audit
        assert "active_support" not in audit
        assert (
            audit["full_structural_nz_used"] >= audit["full_thresholded_effective_nnz"]
        )
        assert audit["reduced_matrix_value_sha256"]
        assert audit["reduced_matrix_frobenius_norm"] > 0.0
    finally:
        observed.destroy()
        expected.destroy()
        probe.destroy()
        for matrix in pair:
            matrix.destroy()
        mass.destroy()
        bare.destroy()


def _restriction(start: int, size: int, total: int) -> np.ndarray:
    matrix = np.zeros((size, total), dtype=np.complex128)
    matrix[np.arange(size), np.arange(start, start + size)] = 1.0
    return matrix


def _tiny_chain():
    layer_size = 2
    total = 6 * layer_size
    diagonal = tuple(
        np.asarray(
            [
                [3.2 + 0.12j + 0.15 * index, 0.18 - 0.04j],
                [0.06 + 0.02j, 2.7 + 0.09j + 0.1 * index],
            ],
            dtype=np.complex128,
        )
        for index in range(6)
    )
    lower = tuple(
        np.asarray(
            [[0.11 + 0.02j, -0.03 + 0.01j], [0.04 - 0.01j, 0.09 + 0.02j]],
            dtype=np.complex128,
        )
        * (1.0 + 0.05 * index)
        for index in range(5)
    )
    upper = tuple(
        np.asarray(
            [[-0.08 + 0.03j, 0.02 + 0.01j], [0.01 - 0.02j, -0.07 + 0.01j]],
            dtype=np.complex128,
        )
        * (1.0 - 0.04 * index)
        for index in range(5)
    )
    bare = np.zeros((total, total), dtype=np.complex128)
    for index, block in enumerate(diagonal):
        rows = slice(index * layer_size, (index + 1) * layer_size)
        bare[rows, rows] = block
        if index:
            bare[rows, slice((index - 1) * layer_size, index * layer_size)] = lower[
                index - 1
            ]
        if index < 5:
            bare[rows, slice((index + 1) * layer_size, (index + 2) * layer_size)] = (
                upper[index]
            )

    local_bare = []
    for first, second in TASK040_LEVEL_A_SUBDOMAINS:
        indices = np.r_[
            np.arange(first * layer_size, (first + 1) * layer_size),
            np.arange(second * layer_size, (second + 1) * layer_size),
        ]
        local_bare.append(bare[np.ix_(indices, indices)])
    tangent_mass = np.asarray(
        [[1.7 + 0.0j, 0.2 - 0.05j], [0.2 + 0.05j, 1.3 + 0.0j]],
        dtype=np.complex128,
    )
    impedance_pairs = tuple(
        build_first_order_interface_impedance(
            tangent_mass,
            0.41 + 0.17j,
            (1, -1),
        )
        for _ in range(2)
    )
    zeros = np.zeros_like(local_bare[0])

    def embed(block: np.ndarray, offset: int) -> np.ndarray:
        result = np.zeros_like(local_bare[0])
        result[offset : offset + layer_size, offset : offset + layer_size] = block
        return result

    left_impedance = [
        zeros.copy(),
        embed(impedance_pairs[0][1], 0),
        embed(impedance_pairs[1][1], 0),
    ]
    right_impedance = [
        embed(impedance_pairs[0][0], layer_size),
        embed(impedance_pairs[1][0], layer_size),
        zeros.copy(),
    ]
    local_pc = [
        local_bare[index] + left_impedance[index] + right_impedance[index]
        for index in range(3)
    ]
    restrictions = tuple(
        _restriction(first * layer_size, 2 * layer_size, total)
        for first, _ in TASK040_LEVEL_A_SUBDOMAINS
    )
    prolongations = tuple(matrix.T.copy() for matrix in restrictions)
    coupling_left = []
    coupling_right = []
    for first, _ in TASK040_LEVEL_A_SUBDOMAINS[:2]:
        left = np.zeros((2 * layer_size, 2 * layer_size), dtype=np.complex128)
        right = np.zeros_like(left)
        left[:layer_size, layer_size:] = lower[first + 1]
        right[layer_size:, :layer_size] = upper[first + 1]
        coupling_left.append(left)
        coupling_right.append(right)

    restriction_matrices = tuple(
        _restriction(first * layer_size, 2 * layer_size, total)
        for first, _ in TASK040_LEVEL_A_SUBDOMAINS
    )
    prolongation_matrices = tuple(matrix.T.copy() for matrix in restriction_matrices)
    comm = MPI.COMM_WORLD
    distributed = comm.size > 1

    def owner_roundtrip(values: np.ndarray) -> np.ndarray:
        values = np.asarray(values, dtype=np.complex128)
        if not distributed:
            return values.copy()
        owned = values[comm.rank :: comm.size].copy()
        pieces = comm.allgather(owned)
        result = np.empty_like(values)
        for rank, piece in enumerate(pieces):
            result[rank :: comm.size] = piece
        return result

    def make_restriction(start: int):
        def restrict(values: np.ndarray) -> np.ndarray:
            global_values = owner_roundtrip(values)
            return np.asarray(global_values[start : start + 2 * layer_size]).copy()

        return restrict

    def make_prolongation(start: int):
        def prolong(values: np.ndarray) -> np.ndarray:
            local_values = np.asarray(values, dtype=np.complex128)
            global_values = np.zeros(total, dtype=np.complex128)
            if distributed:
                owned = local_values[comm.rank :: comm.size].copy()
                pieces = comm.allgather(owned)
                local_values = np.empty_like(local_values)
                for rank, piece in enumerate(pieces):
                    local_values[rank :: comm.size] = piece
            global_values[start : start + 2 * layer_size] = local_values
            return global_values

        return prolong

    restrictions = tuple(
        make_restriction(first * layer_size) for first, _ in TASK040_LEVEL_A_SUBDOMAINS
    )
    prolongations = tuple(
        make_prolongation(first * layer_size) for first, _ in TASK040_LEVEL_A_SUBDOMAINS
    )

    def map_audit() -> float:
        probes = (
            np.ones(total, dtype=np.complex128),
            np.arange(total, dtype=np.complex128),
            np.asarray([1.0 - 0.2j * index for index in range(total)]),
        )
        error = 0.0
        for probe in probes:
            reconstructed = sum(
                (
                    prolongations[index](restrictions[index](probe))
                    for index in range(3)
                ),
                start=np.zeros(total, dtype=np.complex128),
            )
            error = max(error, float(np.linalg.norm(reconstructed - probe, ord=np.inf)))
        return float(comm.allreduce(error, op=MPI.MAX))

    bare_before = bare.copy()

    def bare_audit() -> bool:
        return bool(np.array_equal(bare, bare_before))

    def solver(matrix):
        return lambda rhs: np.linalg.solve(matrix, rhs)

    action = build_side_impedance_transmission_action(
        global_size=total,
        local_sizes=(4, 4, 4),
        restriction=restrictions,
        prolongation=prolongations,
        local_solve=tuple(solver(matrix) for matrix in local_pc),
        coupling_left=tuple(coupling_left),
        coupling_right=tuple(coupling_right),
        interface_normals=((1, -1), (1, -1)),
        restriction_prolongation_audit=map_audit,
        bare_operator_identity_audit=bare_audit,
        local_bare_matrices=local_bare,
        local_pc_matrices=local_pc,
        local_left_impedance=left_impedance,
        local_right_impedance=right_impedance,
        comm=MPI.COMM_WORLD,
    )
    return (
        action,
        bare,
        {
            "local_bare": tuple(local_bare),
            "local_pc": tuple(local_pc),
            "left_impedance": tuple(left_impedance),
            "right_impedance": tuple(right_impedance),
            "restriction_matrices": restriction_matrices,
            "prolongation_matrices": prolongation_matrices,
            "coupling_left": tuple(coupling_left),
            "coupling_right": tuple(coupling_right),
            "comm": comm,
            "distributed": distributed,
            "tangent_mass": tangent_mass,
        },
    )


def _reference_forward_backward(source: np.ndarray, metadata: dict) -> np.ndarray:
    restrictions = metadata["restriction_matrices"]
    prolongations = metadata["prolongation_matrices"]
    local_pc = metadata["local_pc"]
    coupling_left = metadata["coupling_left"]
    coupling_right = metadata["coupling_right"]
    values: list[np.ndarray | None] = [None, None, None]
    for index in TASK040_FORWARD_ORDER:
        rhs = restrictions[index] @ source
        if index:
            rhs = rhs - coupling_left[index - 1] @ values[index - 1]
        values[index] = np.linalg.solve(local_pc[index], rhs)
    for index in TASK040_BACKWARD_ORDER:
        rhs = restrictions[index] @ source
        if index:
            rhs = rhs - coupling_left[index - 1] @ values[index - 1]
        if index < 2:
            rhs = rhs - coupling_right[index] @ values[index + 1]
        values[index] = np.linalg.solve(local_pc[index], rhs)
    return sum(
        (prolongations[index] @ values[index] for index in range(3)),
        start=np.zeros_like(source),
    )


def _reference_backward_only(source: np.ndarray, metadata: dict) -> np.ndarray:
    restrictions = metadata["restriction_matrices"]
    prolongations = metadata["prolongation_matrices"]
    local_pc = metadata["local_pc"]
    coupling_right = metadata["coupling_right"]
    values: list[np.ndarray | None] = [None, None, None]
    for index in TASK040_BACKWARD_ORDER:
        rhs = restrictions[index] @ source
        if index < 2:
            rhs = rhs - coupling_right[index] @ values[index + 1]
        values[index] = np.linalg.solve(local_pc[index], rhs)
    return sum(
        (prolongations[index] @ values[index] for index in range(3)),
        start=np.zeros_like(source),
    )


def test_first_order_impedance_has_explicit_normal_orientation() -> None:
    mass = np.asarray([[2.0, 0.1], [0.1, 1.4]], dtype=np.complex128)
    plus = build_first_order_tangential_impedance(mass, 0.7 + 0.2j, 1)
    minus = build_first_order_tangential_impedance(mass, 0.7 + 0.2j, -1)
    np.testing.assert_allclose(plus, minus, rtol=0.0, atol=1.0e-14)
    np.testing.assert_allclose(
        plus,
        -1j * (0.7 + 0.2j) * mass,
        rtol=0.0,
        atol=1.0e-14,
    )
    with pytest.raises(ValueError, match="opposite"):
        build_first_order_interface_impedance(mass, 1.0, (1, 1))


def test_task040_transmission_tiny_oracle_is_linear_and_does_not_change_bare_f() -> (
    None
):
    action, bare, metadata = _tiny_chain()
    before = bare.copy()
    source_a = np.asarray(
        [0.3 + 0.2j * index for index in range(bare.shape[0])],
        dtype=np.complex128,
    )
    source_b = np.asarray(
        [0.1 - 0.11j * index for index in range(bare.shape[0])],
        dtype=np.complex128,
    )
    audit = action.audit((source_a, source_b), bare_apply=lambda value: bare @ value)
    actual = action.apply(source_a)
    expected = _reference_forward_backward(source_a, metadata)
    old = _reference_backward_only(source_a, metadata)
    np.testing.assert_allclose(actual, expected, rtol=1.0e-12, atol=1.0e-12)
    assert np.linalg.norm(actual - old) > 1.0e-8
    assert audit["finite"] is True
    assert audit["zero_map_pass"] is True
    assert audit["repeat_pass"] is True
    assert audit["linearity_pass"] is True
    assert audit["restriction_prolongation_pass"] is True
    assert max(audit["rho"]) < 1.0
    assert audit["forward_order"] == list(TASK040_FORWARD_ORDER)
    assert audit["backward_order"] == list(TASK040_BACKWARD_ORDER)
    assert audit["interface_normals"] == [[1, -1], [1, -1]]
    assert audit["impedance_applied_to_pc_only"] is True
    assert audit["bare_operator_unchanged"] is True
    np.testing.assert_array_equal(bare, before)
    assert action.diagnostics["pc_identity_bound"] is True
    delta0 = metadata["local_pc"][0] - metadata["local_bare"][0]
    delta1 = metadata["local_pc"][1] - metadata["local_bare"][1]
    np.testing.assert_allclose(delta0[:2, :2], 0.0, rtol=0.0, atol=1.0e-14)
    np.testing.assert_allclose(
        delta0[2:, 2:],
        metadata["right_impedance"][0][2:, 2:],
        rtol=0.0,
        atol=1.0e-14,
    )
    np.testing.assert_allclose(
        delta1[:2, :2],
        metadata["left_impedance"][1][:2, :2],
        rtol=0.0,
        atol=1.0e-14,
    )
    np.testing.assert_allclose(
        delta1[2:, 2:],
        metadata["right_impedance"][1][2:, 2:],
        rtol=0.0,
        atol=1.0e-14,
    )
    action.destroy()
    with pytest.raises(RuntimeError, match="destroyed"):
        action.apply(source_a)


def test_task040_mpi_identity_is_collectively_finite() -> None:
    action, bare, metadata = _tiny_chain()
    source = np.asarray(
        [0.07 + 0.03j * index for index in range(bare.shape[0])],
        dtype=np.complex128,
    )
    result = action.apply(source)
    expected = _reference_forward_backward(source, metadata)
    np.testing.assert_allclose(result, expected, rtol=1.0e-12, atol=1.0e-12)
    expected = action.apply(source)
    local_error = float(np.linalg.norm(result - expected))
    global_error = MPI.COMM_WORLD.allreduce(local_error, op=MPI.MAX)
    assert global_error <= 1.0e-12
    assert MPI.COMM_WORLD.allreduce(bool(np.all(np.isfinite(result))), op=MPI.LAND)
    assert metadata["distributed"] is (MPI.COMM_WORLD.size > 1)
    action.destroy()


def test_task040_petsc_vecscatter_carrier_preserves_owned_identity() -> None:
    comm = MPI.COMM_WORLD
    size = comm.size
    parent = PETSc.Vec().createMPI((12, 12 * size), comm=comm)
    local_templates = [
        PETSc.Vec().createMPI((4, 4 * size), comm=comm) for _ in range(3)
    ]
    scatters = []
    for index, local in enumerate(local_templates):
        source_ids = np.arange(
            comm.rank * 12 + index * 4,
            comm.rank * 12 + (index + 1) * 4,
            dtype=PETSc.IntType,
        )
        target_ids = np.arange(
            comm.rank * 4,
            (comm.rank + 1) * 4,
            dtype=PETSc.IntType,
        )
        source_is = PETSc.IS().createGeneral(source_ids, comm=comm)
        target_is = PETSc.IS().createGeneral(target_ids, comm=comm)
        scatters.append(PETSc.Scatter().create(parent, source_is, local, target_is))
        source_is.destroy()
        target_is.destroy()

    couplings = []
    for _ in range(4):
        matrix = PETSc.Mat().createAIJ(
            size=((4, 4 * size), (4, 4 * size)), nnz=1, comm=comm
        )
        matrix.setUp()
        matrix.assemble()
        couplings.append(matrix)

    def set_owned(vector: PETSc.Vec, values: np.ndarray) -> None:
        vector.array[:] = np.asarray(values, dtype=np.complex128)

    def map_audit() -> float:
        probe = parent.duplicate()
        restored = parent.duplicate()
        local_values = [template.duplicate() for template in local_templates]
        try:
            set_owned(
                probe,
                np.asarray(
                    [0.4 + 0.03j * (comm.rank * 12 + index) for index in range(12)],
                    dtype=np.complex128,
                ),
            )
            restored.set(0.0)
            for scatter, local in zip(scatters, local_values):
                scatter.scatter(
                    probe,
                    local,
                    addv=PETSc.InsertMode.INSERT_VALUES,
                    mode=PETSc.ScatterMode.FORWARD,
                )
                scatter.scatter(
                    local,
                    restored,
                    addv=PETSc.InsertMode.ADD_VALUES,
                    mode=PETSc.ScatterMode.REVERSE,
                )
            restored.assemble()
            difference = restored.duplicate()
            restored.copy(difference)
            difference.axpy(PETSc.ScalarType(-1.0), probe)
            return float(difference.norm())
        finally:
            for vector in reversed(local_values):
                vector.destroy()
            restored.destroy()
            probe.destroy()

    def bare_audit() -> bool:
        return bool(comm.allreduce(np.all(parent.array == 0.0), op=MPI.LAND))

    def copy_local(source: PETSc.Vec, target: PETSc.Vec) -> None:
        source.copy(target)

    action = build_petsc_side_impedance_transmission_action(
        parent_template=parent,
        local_templates=local_templates,
        scatters=scatters,
        local_solve=(copy_local, copy_local, copy_local),
        coupling_left=(couplings[0], couplings[1]),
        coupling_right=(couplings[2], couplings[3]),
        interface_normals=((1, -1), (1, -1)),
        restriction_prolongation_audit=map_audit,
        bare_operator_identity_audit=bare_audit,
    )
    try:
        set_owned(
            parent,
            np.asarray(
                [0.2 - 0.02j * (comm.rank * 12 + index) for index in range(12)],
                dtype=np.complex128,
            ),
        )
        target = parent.duplicate()
        repeat = parent.duplicate()
        zero = parent.duplicate()
        try:
            action.apply(parent, target)
            action.apply(parent, repeat)
            zero.set(0.0)
            action.apply(zero, zero)
            difference = target.duplicate()
            target.copy(difference)
            difference.axpy(PETSc.ScalarType(-1.0), parent)
            assert float(difference.norm()) <= 1.0e-12
            difference.destroy()
            repeat_difference = target.duplicate()
            target.copy(repeat_difference)
            repeat_difference.axpy(PETSc.ScalarType(-1.0), repeat)
            assert float(repeat_difference.norm()) <= 1.0e-12
            repeat_difference.destroy()
            assert float(zero.norm()) <= 1.0e-12
            diagnostics = action.diagnostics
            assert diagnostics["carrier"] == "petsc_vecscatter"
            assert diagnostics["global_numpy_copy"] is False
            assert diagnostics["subdomain_vectors_global_numpy_copy"] is False
            assert diagnostics["bare_operator_unchanged"] is True
            assert diagnostics["restriction_prolongation_pass"] is True
        finally:
            zero.destroy()
            repeat.destroy()
            target.destroy()

        audit_bare = PETSc.Mat().createAIJ(
            size=((12, 12 * size), (12, 12 * size)), nnz=1, comm=comm
        )
        audit_bare.setUp()
        for row in range(comm.rank * 12, (comm.rank + 1) * 12):
            audit_bare.setValue(row, row, 1.0)
        audit_bare.assemble()
        audit_sources = []
        try:
            for source_index in range(6):
                source = parent.duplicate()
                if source_index == 0:
                    source.set(0.0)
                else:
                    set_owned(
                        source,
                        np.asarray(
                            [
                                0.1 * source_index + 0.02j * (comm.rank * 12 + index)
                                for index in range(12)
                            ],
                            dtype=np.complex128,
                        ),
                    )
                audit_sources.append(source)
            audit = audit_petsc_level_a_one_apply(
                action,
                audit_bare,
                dict(
                    zip(
                        (
                            "physical_side_rhs",
                            "modal_traction_positive",
                            "modal_traction_negative",
                            "external_dtn_coupling",
                            "fixed_random_repeat_0",
                            "fixed_random_repeat_1",
                        ),
                        audit_sources,
                    )
                ),
                {
                    "observed": True,
                    "factor_count_ready": 3,
                    "oracle_only": True,
                    "scalable_candidate": False,
                    "full_side_exact_factor_count": 0,
                    "global_direct_factor_count": 0,
                    "nested_ksp_count": 0,
                },
            )
            assert audit["gate"]["pass"] is True
            assert audit["gate"]["zero_map_pass"] is True
            assert audit["gate"]["action_identity_pass"] is True
            assert audit["action_identity"]["carrier"] == "petsc_vecscatter"
            assert audit["action_identity"]["global_numpy_copy"] is False
            assert audit["action_identity"]["restriction_prolongation_pass"] is True
            assert audit["action_identity"]["bare_operator_unchanged"] is True
            assert audit["gate"]["worst_mandatory_rho"] == 0.0
            assert audit["formal_source_apply_count"] == 6
            assert audit["repeat_audit_apply_count"] == 6
            assert audit["linearity_audit_apply_count"] == 1
            assert audit["action_apply_count_delta"] == 13
            assert all(
                "true_residual_norm" in report
                and "true_residual_relative" in report
                and "true_residual" not in report
                for report in audit["reports"]
            )
            assert all(report["finite"] for report in audit["reports"])
        finally:
            for source in reversed(audit_sources):
                source.destroy()
            audit_bare.destroy()
    finally:
        action.destroy()
        for matrix in couplings:
            matrix.destroy()
        for vector in local_templates:
            vector.destroy()
        parent.destroy()


def test_task040_petsc_multiplicative_overlap_uses_current_workspace_only() -> None:
    comm = MPI.COMM_WORLD
    size = comm.size
    parent = PETSc.Vec().createMPI((4, 4 * size), comm=comm)
    bare = PETSc.Mat().createAIJ(size=((4, 4 * size), (4, 4 * size)), nnz=1, comm=comm)
    local_templates = [
        PETSc.Vec().createMPI((2, 2 * size), comm=comm) for _ in range(3)
    ]
    weights = [PETSc.Vec().createMPI((2, 2 * size), comm=comm) for _ in range(3)]
    scatters = []
    group_offsets = ((0, 1), (1, 2), (2, 3))
    diagonal = ((2.0, 3.0), (5.0, 7.0), (11.0, 13.0))
    for row in range(4 * comm.rank, 4 * (comm.rank + 1)):
        bare.setValue(row, row, PETSc.ScalarType(1.0))
    bare.assemble()
    for index, offsets in enumerate(group_offsets):
        base = 4 * comm.rank
        source_ids = np.asarray(
            [base + offset for offset in offsets], dtype=PETSc.IntType
        )
        target_ids = np.asarray([2 * comm.rank, 2 * comm.rank + 1], dtype=PETSc.IntType)
        source_is = PETSc.IS().createGeneral(source_ids, comm=comm)
        target_is = PETSc.IS().createGeneral(target_ids, comm=comm)
        scatters.append(
            PETSc.Scatter().create(parent, source_is, local_templates[index], target_is)
        )
        source_is.destroy()
        target_is.destroy()
    weights[0].array[:] = (1.0, 0.5)
    weights[1].array[:] = (0.5, 0.5)
    weights[2].array[:] = (0.5, 1.0)

    def solve(index: int):
        def _solve(rhs: PETSc.Vec, target: PETSc.Vec) -> None:
            target.array[:] = rhs.array / np.asarray(
                diagonal[index], dtype=PETSc.ScalarType
            )

        return _solve

    def restriction_audit() -> float:
        probe = parent.duplicate()
        restored = parent.duplicate()
        local_values = [template.duplicate() for template in local_templates]
        try:
            base = 4 * comm.rank
            probe.array[:] = np.asarray(
                [0.2 + 0.03j * (base + index) for index in range(4)],
                dtype=PETSc.ScalarType,
            )
            restored.set(0.0)
            for index, scatter in enumerate(scatters):
                scatter.scatter(
                    probe,
                    local_values[index],
                    addv=PETSc.InsertMode.INSERT_VALUES,
                    mode=PETSc.ScatterMode.FORWARD,
                )
                local_values[index].pointwiseMult(local_values[index], weights[index])
                scatter.scatter(
                    local_values[index],
                    restored,
                    addv=PETSc.InsertMode.ADD_VALUES,
                    mode=PETSc.ScatterMode.REVERSE,
                )
            restored.assemble()
            difference = restored.duplicate()
            restored.copy(difference)
            difference.axpy(PETSc.ScalarType(-1.0), probe)
            error = float(difference.norm())
            difference.destroy()
            return error
        finally:
            for vector in reversed(local_values):
                vector.destroy()
            restored.destroy()
            probe.destroy()

    def bare_audit() -> bool:
        probe = bare.createVecRight()
        image = bare.createVecLeft()
        try:
            probe.array[:] = np.asarray(
                [0.4 + 0.02j * (4 * comm.rank + index) for index in range(4)],
                dtype=PETSc.ScalarType,
            )
            bare.mult(probe, image)
            difference = image.duplicate()
            image.copy(difference)
            difference.axpy(PETSc.ScalarType(-1.0), probe)
            passed = difference.norm() <= 1.0e-14
            difference.destroy()
            return bool(comm.allreduce(bool(passed), op=MPI.LAND))
        finally:
            image.destroy()
            probe.destroy()

    action = build_petsc_side_impedance_transmission_action(
        parent_template=parent,
        local_templates=local_templates,
        scatters=scatters,
        local_solve=tuple(solve(index) for index in range(3)),
        coupling_left=(),
        coupling_right=(),
        interface_normals=((1, -1), (1, -1)),
        restriction_prolongation_audit=restriction_audit,
        bare_operator_identity_audit=bare_audit,
        prolongation_weights=weights,
        bare_operator=bare,
        multiplicative_sequence=(0, 1, 2, 2, 1, 0),
    )
    try:
        source = parent.duplicate()
        target = parent.duplicate()
        try:
            base = 4 * comm.rank
            source.array[:] = np.asarray(
                [0.7 + 0.11j * (base + index) for index in range(4)],
                dtype=PETSc.ScalarType,
            )
            action.apply(source, target)
            expected = np.zeros(4, dtype=np.complex128)
            local_source = np.asarray(source.array, dtype=np.complex128)
            for index in (0, 1, 2, 2, 1, 0):
                residual = local_source - expected
                local_delta = residual[list(group_offsets[index])] / np.asarray(
                    diagonal[index], dtype=np.complex128
                )
                expected[list(group_offsets[index])] += (
                    np.asarray(weights[index].array, dtype=np.complex128) * local_delta
                )
            local_error = float(np.max(np.abs(np.asarray(target.array) - expected)))
            assert comm.allreduce(local_error, op=MPI.MAX) <= 1.0e-12
            diagnostics = action.diagnostics
            assert diagnostics["sweep_mode"] == "multiplicative_schwarz"
            assert diagnostics["multiplicative_sequence"] == [0, 1, 2, 2, 1, 0]
            assert diagnostics["partition_of_unity_weighted_prolongation"] is True
        finally:
            target.destroy()
            source.destroy()
    finally:
        action.destroy()
        for vector in local_templates:
            vector.destroy()
        parent.destroy()
        bare.destroy()


def test_task040_level_a_builder_owns_factors_and_preserves_bare_f() -> None:
    bare, masses, group_rows = _tiny_level_a_builder()
    from src.solvers.hybrid_side_impedance import _petsc_matrix_hash

    before_hash = _petsc_matrix_hash(bare)
    action = owner = None
    try:
        action, owner, diagnostics = build_level_a_oracle(
            bare_f=bare,
            group_rows=group_rows,
            interface_masses=masses,
            beta=0.41 + 0.17j,
            group_audit={
                "group_global_rows": [3, 3, 2],
                "group_local_rows": [len(rows) for rows in group_rows],
                "interface_support_coverage": [],
            },
        )
        assert diagnostics["cross_section_factor_count_ready"] == 3
        assert diagnostics["full_side_exact_factor_count"] == 0
        assert diagnostics["global_direct_factor_count"] == 0
        assert diagnostics["nested_ksp_count"] == 0
        assert diagnostics["restriction_prolongation_error"] <= 1.0e-12
        source = bare.createVecRight()
        target = bare.createVecLeft()
        try:
            first, last = map(int, source.getOwnershipRange())
            source.array[:] = np.asarray(
                0.2 + 0.03j * np.arange(first, last), dtype=PETSc.ScalarType
            )
            source.assemble()
            action.apply(source, target)
            assert np.all(np.isfinite(target.array_r))
        finally:
            target.destroy()
            source.destroy()
        ready = owner.diagnostics
        assert ready["factor_count_ready"] == 3
        assert ready["action_destroyed"] is False
    finally:
        if owner is not None:
            owner.destroy()
            after = owner.diagnostics
            assert after["factor_count_after_cleanup"] == 0
            assert after["factor_count_ready"] == 0
            assert after["action_destroyed"] is True
        elif action is not None:
            action.destroy()
        assert _petsc_matrix_hash(bare) == before_hash
        for mass in masses:
            mass.destroy()
        bare.destroy()


def test_task040_cell_union_mpi_or_recovers_remote_owned_membership() -> None:
    comm = MPI.COMM_WORLD
    global_rows = 6
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, global_rows), (PETSc.DECIDE, global_rows)),
        nnz=1,
        comm=comm,
    )
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        matrix.setValue(row, row, PETSc.ScalarType(1.0))
    matrix.assemble()
    layers = [layer for layer in range(6) if layer % comm.size == comm.rank]
    expansion = {
        0: (np.asarray([0, 5], dtype=PETSc.IntType), np.ones(2)),
        1: (np.asarray([0], dtype=PETSc.IntType), np.ones(1)),
        2: (np.asarray([1, 5], dtype=PETSc.IntType), np.ones(2)),
        3: (np.asarray([1, 2, 4], dtype=PETSc.IntType), np.ones(3)),
        4: (np.asarray([3, 4], dtype=PETSc.IntType), np.ones(2)),
        5: (np.asarray([3], dtype=PETSc.IntType), np.ones(1)),
    }
    geometry = SimpleNamespace(
        dofmap=np.arange(len(layers), dtype=np.int64)[:, None],
        x=np.asarray([[0.0, 0.0, layer + 0.5] for layer in layers]),
    )
    system = SimpleNamespace(
        local_mesh=SimpleNamespace(
            z_values=np.arange(7.0), mesh=SimpleNamespace(geometry=geometry)
        ),
        static_condensation=SimpleNamespace(
            condensed=SimpleNamespace(
                trace_constraints=SimpleNamespace(expansion_by_original=expansion),
                cell_recovery_maps=[
                    SimpleNamespace(trace_original_dofs=(layer,)) for layer in layers
                ],
            )
        ),
    )
    supports = (
        {"active_support": (5,)},
        {"active_support": (4,)},
    )
    try:
        rows, audit = build_level_a_cell_recovery_group_rows(system, matrix, supports)
        assert audit["mapping_source"] == "cell_recovery_union_mpi_or"
        assert audit["oracle_only_global_boolean_metadata_collective"] is True
        if comm.rank == comm.size - 1:
            assert first <= 5 < last
            assert 5 in rows[0]
            assert 5 in rows[1]
        assert comm.allgather(5 in rows[0]) == [
            rank == comm.size - 1 for rank in range(comm.size)
        ]
        assert all(
            item["lower_complete"] and item["upper_complete"]
            for item in audit["interface_support_coverage"]
        )
        assert comm.allreduce(
            bool(5 in rows[0] if first <= 5 < last else True), op=MPI.LAND
        )
        assert len(set(comm.allgather(tuple(audit["group_mask_sha256"])))) == 1
    finally:
        matrix.destroy()


def test_task040_v1_1_batch_reuses_one_right_pc_and_zero_initial_guesses() -> None:
    comm = MPI.COMM_WORLD
    size = 64
    operator = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, size), (PETSc.DECIDE, size)),
        nnz=2,
        comm=comm,
    )
    first, last = map(int, operator.getOwnershipRange())
    for row in range(first, last):
        operator.setValue(row, row, PETSc.ScalarType(1.0 + 0.01 * row))
        if row + 1 < size:
            operator.setValue(row, row + 1, PETSc.ScalarType(0.03 + 0.001j))
    operator.assemble()

    class IdentityAction:
        def apply(self, source, target):
            source.copy(target)

    labels = (
        "modal_traction_positive",
        "modal_traction_negative",
        "external_dtn_coupling",
        "fixed_random_repeat_0",
        "fixed_random_repeat_1",
    )
    rhs_by_label = {}
    for label_index, label in enumerate(labels):
        rhs = operator.createVecRight()
        rhs.array[:] = np.asarray(
            [1.0 + 0.01 * (label_index + row) for row in range(first, last)],
            dtype=PETSc.ScalarType,
        )
        rhs.assemble()
        rhs_by_label[label] = rhs
    checkpoint_rows = []
    try:
        result = run_v1_1_right_preconditioned_fgmres_batch(
            operator,
            rhs_by_label,
            IdentityAction(),
            labels=labels,
            resource_callback=lambda: {
                "all_status_readable": True,
                "rss_bytes": 2**20,
                "swap_bytes": 0,
                "pass": True,
            },
            checkpoint_callback=checkpoint_rows.append,
        )
        assert result["ksp_setup_count"] == 1
        assert result["ksp_destroy_count"] == 1
        assert result["ksp_destroyed"] is True
        assert result["zero_initial_guess_all_rhs"] is True
        assert "phase1_frozen_gate" not in result
        assert "stop_on_frozen_gate" not in result
        assert set(result["phase1"]) == set(labels)
        assert all(
            set(record["checkpoints"]) == {"0", "4", "8", "16"}
            for record in result["phase1"].values()
        )
        assert all(
            record["zero_initial_guess"] is True
            and record["shared_ksp"] is True
            and record["true_residual_matvec_count"] == 3
            for record in result["phase1"].values()
        )
        assert result["conditional_32_authorized"] is True
        assert set(result["phase2"]) == set(labels)
        assert all(
            set(record["checkpoints"]) == {"0", "4", "8", "16", "32"}
            for record in result["phase2"].values()
        )
        negative = run_v1_1_right_preconditioned_fgmres_batch(
            operator,
            rhs_by_label,
            IdentityAction(),
            labels=labels,
            resource_callback=lambda: {
                "all_status_readable": True,
                "rss_bytes": 2**20,
                "swap_bytes": 0,
                "pass": False,
            },
        )
        assert negative["conditional_32_authorized"] is False
        assert negative["phase2"] == {}
        assert negative["ksp_setup_count"] == 1
        assert negative["ksp_destroy_count"] == 1
        assert negative["ksp_destroyed"] is True
        frozen = run_v1_1_right_preconditioned_fgmres_batch(
            operator,
            rhs_by_label,
            IdentityAction(),
            labels=labels,
            resource_callback=lambda: {
                "all_status_readable": True,
                "rss_bytes": 2**20,
                "swap_bytes": 0,
                "pass": True,
            },
            stop_on_frozen_gate=True,
        )
        assert frozen["phase1_frozen_gate"] is True
        assert frozen["conditional_32_authorized"] is False
        assert frozen["phase2"] == {}
        assert frozen["ksp_setup_count"] == 1
        assert frozen["ksp_destroy_count"] == 1
        assert len(checkpoint_rows) >= 15
    finally:
        for rhs in rhs_by_label.values():
            rhs.destroy()
        operator.destroy()


def test_task040_scalar_contractions_use_complex_petsc_dot_direction() -> None:
    comm = MPI.COMM_WORLD
    size = 8
    bare = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, size), (PETSc.DECIDE, size)), nnz=1, comm=comm
    )
    first, last = map(int, bare.getOwnershipRange())
    for row in range(first, last):
        bare.setValue(row, row, PETSc.ScalarType(1.0))
    bare.assemble()

    class ComplexScalingAction:
        def __init__(self):
            self.diagnostics = {
                "carrier": "petsc_vecscatter",
                "global_numpy_copy": False,
                "subdomain_vectors_global_numpy_copy": False,
                "restriction_prolongation_pass": True,
                "bare_operator_unchanged": True,
                "apply_count": 0,
            }

        def apply(self, source, target):
            source.copy(target)
            target.scale(PETSc.ScalarType(0.7 + 0.4j))
            self.diagnostics["apply_count"] += 1

    sources = {}
    for label_index, label in enumerate(TASK040_LEVEL_A_SOURCE_LABELS):
        source = bare.createVecRight()
        source.array[:] = np.asarray(
            0.0
            if label_index == 0
            else [1.0 + 0.1j * (label_index + row) for row in range(first, last)],
            dtype=PETSc.ScalarType,
        )
        source.assemble()
        sources[label] = source
    factor_inventory = {
        "observed": True,
        "factor_count_ready": 3,
        "cross_section_factor_count_ready": 3,
        "full_side_exact_factor_count": 0,
        "global_direct_factor_count": 0,
        "nested_ksp_count": 0,
        "oracle_only": True,
        "scalable_candidate": False,
    }
    try:
        result = audit_petsc_level_a_one_apply(
            ComplexScalingAction(),
            bare,
            sources,
            factor_inventory,
            collect_scalar_contractions=True,
        )
        contractions = result["scalar_contractions"]
        gamma = 0.7 + 0.4j
        for index, label in enumerate(contractions["labels"]):
            b2 = complex(*contractions["BHB"][index][index])
            by = complex(*contractions["BHY"][index][index])
            y2 = complex(*contractions["YHY"][index][index])
            assert by == pytest.approx(gamma * b2)
            assert y2 == pytest.approx(abs(gamma) ** 2 * b2)
            assert contractions["per_source"][label]["x_norm_squared"] == pytest.approx(
                abs(gamma) ** 2 * b2.real
            )
    finally:
        for source in sources.values():
            source.destroy()
        bare.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size not in (1, 2),
    reason="C6a moving-PML pilot is focused on serial and MPI2",
)
def test_task040_moving_pml_full_state_action_uses_fixed_core_collars() -> None:
    comm = MPI.COMM_WORLD
    _msh, V, system, condensed = _moving_pml_tiny_fixture()
    bare = condensed.matrix
    assert bare is not None
    z_values = system.local_mesh.z_values
    supports = tuple(
        audit_artificial_z_interface_support(V, condensed, z_values[index])
        for index in (2, 4)
    )
    action = None
    source = None
    output = None
    try:
        core_rows, _ = build_level_a_cell_recovery_group_rows(
            system,
            bare,
            supports,
        )
        action = build_moving_pml_full_state_action(system, bare, core_rows)
        source = bare.createVecRight()
        output = bare.createVecLeft()
        first, last = map(int, source.getOwnershipRange())
        source.array[:] = np.asarray(
            [0.2 + 0.03j * row for row in range(first, last)],
            dtype=PETSc.ScalarType,
        )
        source.assemble()
        action.apply(source, output)
        assert comm.allreduce(bool(np.all(np.isfinite(output.array))), op=MPI.LAND)

        diagnostics = action.diagnostics
        assert diagnostics["sweep"] == [0, 1, 2, 2, 1, 0]
        assert diagnostics["global_auxiliary_matrix"] is False
        assert diagnostics["numeric_allgather"] is False
        assert diagnostics["bare_f_unchanged"] is True
        assert diagnostics["bare_f_hash_before"] == diagnostics["bare_f_hash_after"]
        assert diagnostics["apply_count"] == 1
        expected_layers = ({0, 1, 2, 3}, {0, 1, 2, 3, 4, 5}, {2, 3, 4, 5})
        expected_collar = (2, 4, 2)
        for group, expected in enumerate(expected_layers):
            group_diagnostics = diagnostics["groups"][group]
            layers = {
                int(layer)
                for packet in comm.allgather(
                    group_diagnostics["selected_layer_counts_local"]
                )
                for layer, count in packet.items()
                if count
            }
            assert layers == expected
            assert group_diagnostics["selected_cells_global"] == len(expected)
            assert group_diagnostics["collar_cells_global"] == expected_collar[group]
            assert group_diagnostics["global_auxiliary_matrix"] is False
            assert group_diagnostics["collar_prolongation_weight"] == 0.0
            expected_counts = {
                f"{side}:{material}": 0
                for side in ("bottom", "top")
                for material in ("air", "substrate", "grating")
            }
            if group in (0, 1):
                expected_counts["top:air"] = 2
            if group in (1, 2):
                expected_counts["bottom:air"] = 2
            assert group_diagnostics["collar_cell_counts_global"] == expected_counts
            assert len(group_diagnostics["material_side_tags"]) == 6
            owner = int(group_diagnostics["owner_rank"])
            by_rank = comm.allgather(group_diagnostics)
            owner_diagnostics = by_rank[owner]
            assert owner_diagnostics["core_rows"] > 0
            assert owner_diagnostics["collar_rows"] >= 0
            assert owner_diagnostics["extended_factor_count"] == 0
            assert owner_diagnostics["core_factor_count"] == 1
            assert owner_diagnostics["core_factor_nnz"] >= 0
            assert owner_diagnostics["core_factor_diagnostics"][
                "factor_only_storage"
            ] is True
            owner_inner = owner_diagnostics["inner"]
            assert owner_inner["iterations"] == 2
            assert np.all(
                np.isfinite(
                    [
                        owner_inner["initial_true_residual"],
                        owner_inner["final_true_residual"],
                        owner_inner["ratio"],
                    ]
                )
            )
            assert group_diagnostics["destroyed"] is False

        action.destroy()
        after_destroy = action.diagnostics
        assert after_destroy["destroyed"] is True
        assert after_destroy["groups"] == []
        assert after_destroy["bare_f_unchanged"] is True
    finally:
        if output is not None:
            output.destroy()
        if source is not None:
            source.destroy()
        if action is not None:
            action.destroy()
        condensed.destroy()
