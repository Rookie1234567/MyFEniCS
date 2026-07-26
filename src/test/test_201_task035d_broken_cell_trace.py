from __future__ import annotations

from types import SimpleNamespace

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest
from scipy import sparse
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem

from src.adaptivity.dyadic_hexa_broken_mesh import (
    build_broken_dyadic_hexa_carrier,
)
from src.adaptivity.dyadic_hexa_refinement import (
    DyadicHexKey,
    build_root_dyadic_hexa_forest,
    refine_balanced_dyadic_hexa_forest,
)
from src.adaptivity.exact_sequence_variable_p import (
    build_variable_p_reference_space,
)
from src.adaptivity.hcurl_broken_cell_trace import (
    build_broken_hexa_cell_trace_constraint_map,
)
from src.adaptivity.hcurl_broken_trace_graph import (
    build_broken_hexa_trace_constraint_authority,
)
from src.adaptivity.variable_p_entity_map import (
    build_variable_p_global_entity_map,
)
from src.solvers.hcurl_variable_p_assembly import (
    build_variable_p_condensed_trace_system,
    build_variable_p_condensed_trace_system_from_compiled_form,
    condense_variable_p_active_vector_to_trace,
    recover_variable_p_active_full_vector,
)
from src.solvers.hcurl_variable_p_reduction import (
    _reduced_trace_auxiliary_norm,
)
from src.solvers.hcurl_variable_p_local import project_p6_local_tensor


def _degree_array(msh, dimension: int, degree: int) -> np.ndarray:
    msh.topology.create_entities(dimension)
    index_map = msh.topology.index_map(dimension)
    return np.full(
        int(index_map.size_local + index_map.num_ghosts),
        int(degree),
        dtype=np.int32,
    )


def _single_hanging_fixture(
    *,
    degree: int = 4,
    cell_degree: int = 4,
):
    forest = build_root_dyadic_hexa_forest(
        [
            (0.0, 0.0, 0.0, 1.0, 1.0, 1.0),
            (1.0, 0.0, 0.0, 2.0, 1.0, 1.0),
        ],
        [1, 1],
        periodic_axes=(),
    )
    forest = refine_balanced_dyadic_hexa_forest(
        forest,
        [DyadicHexKey(0, 0, 0, 0, 0)],
    )
    carrier = build_broken_dyadic_hexa_carrier(
        forest,
        comm=MPI.COMM_WORLD,
    )
    msh = carrier.mesh
    entity_map = build_variable_p_global_entity_map(
        msh,
        edge_degrees=_degree_array(msh, 1, degree),
        face_degrees=_degree_array(msh, 2, degree),
        cell_degrees=_degree_array(msh, 3, cell_degree),
    )
    authority = build_broken_hexa_trace_constraint_authority(
        forest,
        carrier,
        degree=degree,
    )
    constraints = build_broken_hexa_cell_trace_constraint_map(
        forest,
        carrier,
        entity_map,
        authority,
    )
    return forest, carrier, entity_map, authority, constraints


def _periodic_corner_fixture():
    boxes = [
        (
            float(i),
            float(j),
            0.0,
            float(i + 1),
            float(j + 1),
            1.0,
        )
        for j in range(3)
        for i in range(3)
    ]
    forest = build_root_dyadic_hexa_forest(
        boxes,
        [1] * len(boxes),
        periodic_axes=("x", "y"),
    )
    forest = refine_balanced_dyadic_hexa_forest(
        forest,
        [DyadicHexKey(0, 0, 0, 0, 0)],
    )
    carrier = build_broken_dyadic_hexa_carrier(
        forest,
        comm=MPI.COMM_WORLD,
    )
    msh = carrier.mesh
    entity_map = build_variable_p_global_entity_map(
        msh,
        edge_degrees=_degree_array(msh, 1, 4),
        face_degrees=_degree_array(msh, 2, 4),
        cell_degrees=_degree_array(msh, 3, 4),
    )
    authority = build_broken_hexa_trace_constraint_authority(
        forest,
        carrier,
        degree=4,
        phase_x=np.exp(0.2j),
        phase_y=np.exp(-0.3j),
    )
    constraints = build_broken_hexa_cell_trace_constraint_map(
        forest,
        carrier,
        entity_map,
        authority,
    )
    return entity_map, authority, constraints


def _dense_p6_tensor() -> np.ndarray:
    values = np.linspace(0.1, 1.0, 882)
    return (
        np.diag(2.0 + values)
        + 0.01 * np.outer(values, values)
    ).astype(np.complex128)


def _global_trace_expansion(constraints) -> sparse.csr_matrix:
    rows: list[int] = []
    columns: list[int] = []
    values: list[complex] = []
    for block in constraints.entity_blocks.values():
        local_rows, local_columns = np.nonzero(
            np.abs(block.full_from_independent) > 0.0
        )
        rows.extend(map(int, block.full_rows[local_rows]))
        columns.extend(map(int, block.independent_rows[local_columns]))
        values.extend(
            map(complex, block.full_from_independent[local_rows, local_columns])
        )
    return sparse.coo_matrix(
        (values, (rows, columns)),
        shape=(
            constraints.entity_map.active_trace_rows,
            constraints.independent_trace_rows,
        ),
        dtype=np.complex128,
    ).tocsr()


def _matrix_action(matrix: PETSc.Mat, values: np.ndarray) -> np.ndarray:
    vector = matrix.createVecRight()
    result = matrix.createVecLeft()
    start, stop = vector.getOwnershipRange()
    vector.getArray()[:] = np.asarray(values[start:stop])
    vector.assemble()
    matrix.mult(vector, result)
    output = np.concatenate(
        matrix.comm.tompi4py().allgather(
            np.asarray(result.getArray(readonly=True)).copy()
        )
    )
    vector.destroy()
    result.destroy()
    return output


def _global_vector_values(vector: PETSc.Vec) -> np.ndarray:
    return np.concatenate(
        vector.comm.tompi4py().allgather(
            np.asarray(vector.getArray(readonly=True)).copy()
        )
    )


def test_actual_cell_info_binding_is_partition_independent() -> None:
    if MPI.COMM_WORLD.size not in {1, 2, 8}:
        pytest.skip("Task035d cell binding qualifies serial/MPI2/MPI8")
    _, _, entity_map, authority, constraints = _single_hanging_fixture()
    audit = constraints.audit
    assert audit["pass"] is True
    assert audit["raw_trace_rows"] == 1272
    assert audit["independent_trace_rows"] == 1128
    assert audit["eliminated_hanging_or_floquet_rows"] == 144
    assert audit["maximum_entity_transform_orthogonality_error"] <= 5.0e-11
    assert audit["maximum_cell_transform_error"] <= 5.0e-11
    assert audit["maximum_unpermuted_cell_chart_error"] <= 5.0e-11
    assert audit["maximum_trace_interior_mixing_error"] <= 5.0e-11
    assert audit["maximum_cell_expansion_condition"] == pytest.approx(
        3184846.1196,
        rel=2.0e-9,
    )
    assert audit["physical_authority_sha256"] == (
        "d65bc72969f7ee2180d08563bc75f4c60067a954a518da0b14afed2750ba2177"
    )
    hashes = MPI.COMM_WORLD.allgather(
        audit["canonical_cell_graph_sha256"]
    )
    assert len(set(hashes)) == 1
    assert len(constraints.owned_cells) == len(entity_map.owned_cells)
    assert all(
        cell.full_trace_from_independent.shape[0]
        == len(entity_map.owned_cells[index].trace_rows)
        for index, cell in enumerate(constraints.owned_cells)
    )
    assert authority.graph.audit["maximum_relation_residual"] <= 5.0e-11


@pytest.mark.parametrize(
    ("degree", "raw_rows", "independent_rows", "condition_bounds"),
    (
        (5, 2010, 1790, (1.0e8, 2.0e8)),
        (6, 2916, 2604, (5.0e9, 2.0e10)),
    ),
)
def test_p5_p6_hanging_cell_bindings_remain_explicit_risk_authorities(
    degree: int,
    raw_rows: int,
    independent_rows: int,
    condition_bounds: tuple[float, float],
) -> None:
    if MPI.COMM_WORLD.size not in {1, 2, 8}:
        pytest.skip("Task035d p5/p6 binding qualifies serial/MPI2/MPI8")
    _, _, _, authority, constraints = _single_hanging_fixture(
        degree=degree,
        cell_degree=6,
    )
    audit = constraints.audit
    assert audit["raw_trace_rows"] == raw_rows
    assert audit["independent_trace_rows"] == independent_rows
    assert audit["maximum_cell_transform_error"] <= 5.0e-11
    assert audit["maximum_trace_interior_mixing_error"] == 0.0
    assert condition_bounds[0] < audit[
        "maximum_cell_expansion_condition"
    ] < condition_bounds[1]
    assert authority.graph.audit["maximum_relation_residual"] <= 5.0e-11
    assert audit["pde_accuracy_credit"] is False


def test_constrained_schur_action_matches_raw_trace_congruence() -> None:
    if MPI.COMM_WORLD.size != 1:
        pytest.skip("serial algebraic congruence authority")
    _, _, entity_map, _, constraints = _single_hanging_fixture()
    tensor = _dense_p6_tensor()
    tensors = [tensor] * len(entity_map.owned_cells)
    keys = ("shared-p6",) * len(tensors)
    raw = build_variable_p_condensed_trace_system(
        entity_map,
        tensors,
        tensor_class_keys=keys,
    )
    constrained = build_variable_p_condensed_trace_system(
        entity_map,
        tensors,
        tensor_class_keys=keys,
        trace_constraints=constraints,
    )
    try:
        expansion = _global_trace_expansion(constraints)
        rng = np.random.default_rng(3520101)
        for _ in range(3):
            root = (
                rng.standard_normal(constraints.independent_trace_rows)
                + 1j
                * rng.standard_normal(
                    constraints.independent_trace_rows
                )
            )
            expected = expansion.conj().T @ _matrix_action(
                raw.matrix,
                expansion @ root,
            )
            observed = _matrix_action(constrained.matrix, root)
            np.testing.assert_allclose(
                observed,
                expected,
                rtol=3.0e-11,
                atol=3.0e-9,
            )
        audit = constrained.build_audit
        assert audit["trace_constraint_elimination_applied_before_insertion"]
        assert audit["hanging_or_floquet_slave_rows"] == 144
        assert audit["periodic_slave_rows"] is None
        assert audit["matrix_rows"] == 1128
        assert audit["matrix_mallocs"] == 0
        assert "compiled_p6_tensor_builder" not in audit
        norm_vector = constrained.matrix.createVecRight()
        norm_vector.getArray()[:] = root
        norm_vector.assemble()
        gram = sparse.csr_matrix(constraints.component_gram)
        expected_primal = float(
            np.sqrt(np.vdot(root, gram @ root).real)
        )
        expected_dual = float(
            np.sqrt(
                np.vdot(
                    root,
                    sparse.linalg.spsolve(gram.tocsc(), root),
                ).real
            )
        )
        assert _reduced_trace_auxiliary_norm(
            constrained,
            norm_vector,
            trace_kind="primal",
        ) == pytest.approx(expected_primal, rel=2.0e-12)
        assert _reduced_trace_auxiliary_norm(
            constrained,
            norm_vector,
            trace_kind="dual",
        ) == pytest.approx(expected_dual, rel=2.0e-12)
        norm_vector.destroy()
    finally:
        constrained.destroy()
        raw.destroy()


def test_trace_constraint_protocol_fails_closed() -> None:
    if MPI.COMM_WORLD.size != 1:
        pytest.skip("serial malformed-constraint controls")
    _, _, entity_map, _, constraints = _single_hanging_fixture()
    tensors = [_dense_p6_tensor()] * len(entity_map.owned_cells)
    failed_audit = SimpleNamespace(
        entity_map=entity_map,
        audit={"pass": False},
        independent_trace_rows=constraints.independent_trace_rows,
        owned_cells=constraints.owned_cells,
        entity_blocks=constraints.entity_blocks,
    )
    with pytest.raises(ValueError, match="has not passed"):
        build_variable_p_condensed_trace_system(
            entity_map,
            tensors,
            trace_constraints=failed_audit,
        )

    first = constraints.owned_cells[0]
    invalid_expansion = np.asarray(
        first.full_trace_from_independent
    ).copy()
    invalid_expansion[0, 0] = np.nan
    invalid_cell = SimpleNamespace(
        global_cell=first.global_cell,
        independent_rows=first.independent_rows,
        full_trace_from_independent=invalid_expansion,
    )
    nonfinite = SimpleNamespace(
        entity_map=entity_map,
        audit={"pass": True},
        independent_trace_rows=constraints.independent_trace_rows,
        owned_cells=(invalid_cell, *constraints.owned_cells[1:]),
        entity_blocks=constraints.entity_blocks,
    )
    with pytest.raises(ValueError, match="non-finite"):
        build_variable_p_condensed_trace_system(
            entity_map,
            tensors,
            trace_constraints=nonfinite,
        )

    block_key, block = next(iter(constraints.entity_blocks.items()))
    invalid_block_expansion = np.asarray(
        block.full_from_independent
    ).copy()
    nonzero = np.argwhere(np.abs(invalid_block_expansion) > 0.0)[0]
    invalid_block_expansion[tuple(nonzero)] += 0.5
    invalid_block = SimpleNamespace(
        full_rows=block.full_rows,
        independent_rows=block.independent_rows,
        full_from_independent=invalid_block_expansion,
    )
    invalid_blocks = dict(constraints.entity_blocks)
    invalid_blocks[block_key] = invalid_block
    inconsistent = SimpleNamespace(
        entity_map=entity_map,
        audit={"pass": True},
        independent_trace_rows=constraints.independent_trace_rows,
        owned_cells=constraints.owned_cells,
        entity_blocks=invalid_blocks,
        component_gram=constraints.component_gram,
    )
    with pytest.raises(ValueError, match="cell and entity trace expansions"):
        build_variable_p_condensed_trace_system(
            entity_map,
            tensors,
            trace_constraints=inconsistent,
        )


def test_mpi_rank_local_constraint_corruption_fails_collectively() -> None:
    if MPI.COMM_WORLD.size != 2:
        pytest.skip("MPI2 rank-local malformed constraint control")
    _, _, entity_map, _, constraints = _single_hanging_fixture()
    cells = list(constraints.owned_cells)
    if MPI.COMM_WORLD.rank == 0:
        first = cells[0]
        invalid_expansion = np.asarray(
            first.full_trace_from_independent
        ).copy()
        invalid_expansion[0, 0] = np.nan
        cells[0] = SimpleNamespace(
            global_cell=first.global_cell,
            independent_rows=first.independent_rows,
            full_trace_from_independent=invalid_expansion,
        )
    rank_local = SimpleNamespace(
        entity_map=entity_map,
        audit={"pass": True},
        independent_trace_rows=constraints.independent_trace_rows,
        owned_cells=tuple(cells),
        entity_blocks=constraints.entity_blocks,
        component_gram=constraints.component_gram,
    )
    tensors = [_dense_p6_tensor()] * len(entity_map.owned_cells)
    with pytest.raises(ValueError, match="collective trace constraint"):
        build_variable_p_condensed_trace_system(
            entity_map,
            tensors,
            trace_constraints=rank_local,
        )


def test_periodic_hanging_chains_bind_without_numbered_slaves() -> None:
    if MPI.COMM_WORLD.size not in {1, 2, 8}:
        pytest.skip("Task035d combined graph qualifies serial/MPI2/MPI8")
    entity_map, authority, constraints = _periodic_corner_fixture()
    audit = constraints.audit
    assert authority.audit["maximum_chain_depth"] == 2
    assert authority.audit["maximum_relation_residual"] <= 5.0e-11
    assert audit["raw_trace_rows"] == 5120
    assert audit["independent_trace_rows"] == 3384
    assert audit["eliminated_hanging_or_floquet_rows"] == 1736
    assert audit["maximum_cell_transform_error"] <= 5.0e-11
    assert audit["maximum_trace_interior_mixing_error"] == 0.0
    assert audit["hanging_or_floquet_slave_rows_globally_numbered"] is False
    assert len(constraints.owned_cells) == len(entity_map.owned_cells)
    hashes = MPI.COMM_WORLD.allgather(
        audit["canonical_cell_graph_sha256"]
    )
    assert len(set(hashes)) == 1


def test_periodic_hanging_matrix_uses_conjugated_phases_before_insertion() -> None:
    if MPI.COMM_WORLD.size not in {1, 2, 8}:
        pytest.skip("Task035d combined matrix qualifies serial/MPI2/MPI8")
    entity_map, authority, constraints = _periodic_corner_fixture()
    tensor = _dense_p6_tensor()
    tensors = [tensor] * len(entity_map.owned_cells)
    system = build_variable_p_condensed_trace_system(
        entity_map,
        tensors,
        tensor_class_keys=("combined-p4",) * len(tensors),
        trace_constraints=constraints,
    )
    try:
        audit = system.build_audit
        assert audit["trace_constraint_kinds"] == ["floquet", "hanging"]
        assert audit["floquet_elimination_applied_before_insertion"] is True
        assert audit["hanging_elimination_applied_before_insertion"] is True
        assert audit["periodic_slave_rows"] == 616
        assert audit["hanging_slave_rows"] == 1120
        assert audit["hanging_or_floquet_slave_rows"] == 1736
        assert audit["active_trace_rows"] == 3384
        assert audit["matrix_rows"] == 3384
        assert audit["matrix_mallocs"] == 0
        assert audit["trace_slave_rows_globally_numbered"] is False

        rows = np.arange(constraints.independent_trace_rows)
        left = np.sin(0.017 * rows) + 1j * np.cos(0.013 * rows)
        right = np.cos(0.019 * rows) + 1j * np.sin(0.023 * rows)
        applied_left = _matrix_action(system.matrix, left)
        applied_right = _matrix_action(system.matrix, right)
        left_bilinear = np.vdot(left, applied_right)
        right_bilinear = np.vdot(applied_left, right)
        assert abs(left_bilinear - right_bilinear) / max(
            abs(left_bilinear),
            abs(right_bilinear),
            1.0,
        ) <= 3.0e-11

        recovered = system.recover_owned_active_cells(left)
        by_global_cell = {
            cell.global_cell: cell for cell in constraints.owned_cells
        }
        for cell, active in recovered:
            constrained_cell = by_global_cell[cell.global_cell]
            space = build_variable_p_reference_space(cell.degree_map)
            expected_trace = (
                constrained_cell.full_trace_from_independent
                @ left[constrained_cell.independent_rows]
            )
            np.testing.assert_allclose(
                active[space.trace_dofs],
                expected_trace,
                rtol=2.0e-12,
                atol=2.0e-12,
            )
            oriented = space.orient_hcurl_tensor(
                project_p6_local_tensor(space, tensor),
                cell_info=cell.cell_info,
            )
            residual = oriented @ active
            assert float(
                np.max(
                    np.abs(residual[space.interior_dofs]),
                    initial=0.0,
                )
            ) <= 3.0e-9
        assert authority.audit["maximum_relation_residual"] <= 5.0e-11

        raw_trace = _global_trace_expansion(constraints) @ left
        expected_active = np.zeros(
            entity_map.active_rows,
            dtype=np.complex128,
        )
        expected_active[: entity_map.active_trace_rows] = raw_trace
        interior_rows = np.arange(
            entity_map.active_trace_rows,
            entity_map.active_rows,
        )
        expected_active[interior_rows] = (
            np.sin(0.011 * interior_rows)
            + 1j * np.cos(0.007 * interior_rows)
        )
        quotient, remainder = divmod(
            entity_map.active_rows,
            MPI.COMM_WORLD.size,
        )
        local_count = quotient + (
            1 if MPI.COMM_WORLD.rank < remainder else 0
        )
        active_rhs = PETSc.Vec().createMPI(
            (local_count, entity_map.active_rows),
            comm=MPI.COMM_WORLD,
        )
        for cell in entity_map.owned_cells:
            space = build_variable_p_reference_space(cell.degree_map)
            oriented = space.orient_hcurl_tensor(
                project_p6_local_tensor(space, tensor),
                cell_info=cell.cell_info,
            )
            active_rhs.setValues(
                np.asarray(cell.active_rows, dtype=PETSc.IntType),
                np.asarray(
                    oriented @ expected_active[cell.active_rows],
                    dtype=PETSc.ScalarType,
                ),
                addv=PETSc.InsertMode.ADD_VALUES,
            )
        active_rhs.assemble()
        reduced_rhs = condense_variable_p_active_vector_to_trace(
            system,
            active_rhs,
            side="right",
        )
        np.testing.assert_allclose(
            _global_vector_values(reduced_rhs),
            applied_left,
            rtol=3.0e-10,
            atol=3.0e-8,
        )
        recovered_full = recover_variable_p_active_full_vector(
            system,
            left,
            active_full_rhs=active_rhs,
        )
        np.testing.assert_allclose(
            _global_vector_values(recovered_full),
            expected_active,
            rtol=3.0e-9,
            atol=3.0e-8,
        )
        recovered_full.destroy()
        reduced_rhs.destroy()
        active_rhs.destroy()
    finally:
        system.destroy()


def test_compiled_p6_kernel_binds_to_p5_hanging_trace_rows() -> None:
    if MPI.COMM_WORLD.size not in {1, 2, 8}:
        pytest.skip(
            "Task035d compiled local-h binding qualifies serial/MPI2/MPI8"
        )
    _, carrier, entity_map, _, constraints = _single_hanging_fixture(
        degree=5,
        cell_degree=6,
    )
    msh = carrier.mesh
    p6_space = fem.functionspace(
        msh,
        element(
            "N1curl",
            msh.basix_cell(),
            6,
            dtype=default_real_type,
        ),
    )
    trial = ufl.TrialFunction(p6_space)
    test = ufl.TestFunction(p6_space)
    dx = ufl.Measure(
        "dx",
        domain=msh,
        subdomain_data=carrier.cell_tags,
    )
    compiled = fem.form(
        (
            ufl.inner(ufl.curl(trial), ufl.curl(test))
            + PETSc.ScalarType(2.5)
            * ufl.inner(trial, test)
        )
        * dx(1)
    )
    system = build_variable_p_condensed_trace_system_from_compiled_form(
        compiled,
        p6_space,
        carrier.cell_tags,
        entity_map,
        trace_constraints=constraints,
    )
    try:
        audit = system.build_audit
        assert audit["pass"] is True
        assert audit["compiled_p6_tensor_builder"] is True
        assert audit["compiled_trace_constraint_binding_complete"] is True
        assert audit["trace_constraint_elimination_applied_before_insertion"]
        assert audit["active_full3d_rows_before_condensation"] == 6060
        assert audit["active_trace_rows_before_periodic_elimination"] == 2010
        assert audit["active_trace_rows"] == 1790
        assert audit["hanging_or_floquet_slave_rows"] == 220
        assert audit["matrix_rows"] == 1790
        assert audit["matrix_mallocs"] == 0
        assert audit["full_p6_global_matrix_constructed"] is False
        assert audit["full_active_global_matrix_constructed"] is False
        assert audit["hanging_or_floquet_slave_rows_globally_numbered"] is False
        root = np.sin(
            0.017 * np.arange(constraints.independent_trace_rows)
        ) + 1j * np.cos(
            0.013 * np.arange(constraints.independent_trace_rows)
        )
        applied = _matrix_action(system.matrix, root)
        assert np.all(np.isfinite(applied))
        recovered = system.recover_owned_active_cells(root)
        assert len(recovered) == len(entity_map.owned_cells)
        constrained_by_cell = {
            cell.global_cell: cell for cell in constraints.owned_cells
        }
        for cell, values in recovered:
            assert np.all(np.isfinite(values))
            space = build_variable_p_reference_space(cell.degree_map)
            constrained_cell = constrained_by_cell[cell.global_cell]
            np.testing.assert_allclose(
                values[space.trace_dofs],
                constrained_cell.full_trace_from_independent
                @ root[constrained_cell.independent_rows],
                rtol=3.0e-12,
                atol=3.0e-12,
            )
        assert constraints.audit["maximum_cell_expansion_condition"] > 1.0e8
        assert constraints.audit["cell_expansion_inverse_used"] is False
        assert constraints.audit["distributed_scalability_qualified"] is False
    finally:
        system.destroy()
