"""Tiny Task040 side-impedance and transmission contracts."""

from __future__ import annotations

import numpy as np
import pytest
from types import SimpleNamespace

from basix.ufl import element
from dolfinx import default_real_type, fem, mesh
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.hybrid_side_impedance import (
    TASK040_BACKWARD_ORDER,
    TASK040_FORWARD_ORDER,
    TASK040_LEVEL_A_SUBDOMAINS,
    assemble_reduced_artificial_interface_tangential_mass,
    audit_petsc_level_a_one_apply,
    audit_artificial_z_interface_support,
    build_petsc_side_impedance_transmission_action,
    build_first_order_petsc_interface_impedance,
    build_first_order_interface_impedance,
    build_first_order_tangential_impedance,
    build_side_impedance_transmission_action,
)


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
