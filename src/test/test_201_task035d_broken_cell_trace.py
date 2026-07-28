from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc
import pytest
from scipy import sparse
import ufl
from basix.ufl import element
from dolfinx import default_real_type, fem

import src.adaptivity.hcurl_broken_cell_trace as broken_cell_trace_module
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
    _maximal_rank_profile,
    build_broken_hexa_cell_trace_constraint_map,
)
from src.adaptivity.hcurl_broken_trace_graph import (
    build_broken_hexa_entity_degree_arrays,
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
    VariablePAssemblyTimeReduction,
    VariablePRecoveredSolution,
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


def test_wide_hanging_cell_expansion_requires_maximal_not_column_rank() -> None:
    rng = np.random.default_rng(350201)
    expansion = rng.standard_normal((300, 340))
    rank, expected_rank, condition = _maximal_rank_profile(expansion)

    assert rank == 300
    assert expected_rank == 300
    assert np.isfinite(condition)


def _single_hanging_fixture(
    *,
    degree: int = 4,
    cell_degree: int = 4,
    p5_interior_canonical_leaves: int = 0,
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
    cell_degrees = _degree_array(msh, 3, cell_degree)
    if p5_interior_canonical_leaves:
        if cell_degree != 6 or degree > 5:
            raise ValueError(
                "mixed fixture requires p5 trace and a p6 container"
            )
        canonical = np.asarray(
            carrier.canonical_leaf_by_local_cell,
            dtype=np.int64,
        )
        cell_degrees[
            canonical < int(p5_interior_canonical_leaves)
        ] = 5
    entity_map = build_variable_p_global_entity_map(
        msh,
        edge_degrees=_degree_array(msh, 1, degree),
        face_degrees=_degree_array(msh, 2, degree),
        cell_degrees=cell_degrees,
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


def test_nonhanging_selective_p6_face_binds_real_active_rows() -> None:
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
    base = build_broken_hexa_trace_constraint_authority(
        forest,
        carrier,
        degree=5,
    )
    hanging = {
        row.entity_geometry_key
        for relation in base.hanging_relations
        for row in (*relation.slave_rows, *relation.master_rows)
        if row.entity_dimension == 2
    }
    selected = next(
        entity.geometry_key
        for entity in base.entities
        if entity.dimension == 2
        and entity.geometry_key not in hanging
    )
    authority = build_broken_hexa_trace_constraint_authority(
        forest,
        carrier,
        degree=5,
        selected_p6_face_geometry_keys=(selected,),
    )
    edge_degrees, face_degrees = (
        build_broken_hexa_entity_degree_arrays(
            forest,
            carrier,
            authority,
        )
    )
    selected_local_copies = int(np.count_nonzero(face_degrees == 6))
    assert (
        carrier.mesh.comm.allreduce(
            selected_local_copies,
            op=MPI.SUM,
        )
        >= 1
    )
    assert np.all(edge_degrees == 5)
    entity_map = build_variable_p_global_entity_map(
        carrier.mesh,
        edge_degrees=edge_degrees,
        face_degrees=face_degrees,
        cell_degrees=_degree_array(carrier.mesh, 3, 6),
    )
    constraints = build_broken_hexa_cell_trace_constraint_map(
        forest,
        carrier,
        entity_map,
        authority,
    )

    assert constraints.audit["pass"] is True
    assert constraints.audit["trace_degree_values"] == [5, 6]
    assert constraints.audit["selected_p6_face_count"] == 1
    assert constraints.audit["local_variable_trace_implemented"] is True
    assert entity_map.active_trace_rows == (
        base.audit["raw_trace_rows"] + 20
    )
    assert constraints.independent_trace_rows == (
        base.audit["independent_trace_rows"] + 20
    )
    assert entity_map.audit["inactive_modes_globally_numbered"] is False


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
    blocks = getattr(
        constraints,
        "work_owned_entity_blocks",
        tuple(constraints.entity_blocks.values()),
    )
    for block in blocks:
        local_rows, local_columns = np.nonzero(
            np.abs(block.full_from_independent) > 0.0
        )
        rows.extend(map(int, block.full_rows[local_rows]))
        columns.extend(map(int, block.independent_rows[local_columns]))
        values.extend(
            map(complex, block.full_from_independent[local_rows, local_columns])
        )
    packets = MPI.COMM_WORLD.allgather(
        (
            np.asarray(rows, dtype=np.int64),
            np.asarray(columns, dtype=np.int64),
            np.asarray(values, dtype=np.complex128),
        )
    )
    return sparse.coo_matrix(
        (
            np.concatenate([packet[2] for packet in packets]),
            (
                np.concatenate([packet[0] for packet in packets]),
                np.concatenate([packet[1] for packet in packets]),
            ),
        ),
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
    routing = audit["owner_routed_trace_cache_audit"]
    assert audit["petsc_constraint_row_ownership_qualified"] is True
    assert audit["mpi_ghost_expansion_qualified"] is True
    assert audit["pde_launch_ownership_gate"] is True
    assert audit["replicated_entity_block_bytes_per_rank"] == 0
    assert audit["distributed_scalability_qualified"] is False
    assert routing["pass"] is True
    assert routing["dense_global_entity_catalog_replicated"] is False
    assert routing["declaration_catalog_is_metadata_only"] is True
    assert routing["request_reply_count_closes"] is True
    assert sum(routing["work_owned_block_counts_by_rank"]) == routing[
        "declaration_count"
    ]
    assert all(
        routing[name] == 0
        for name in (
            "missing_reply_count",
            "duplicate_reply_count",
            "unrequested_reply_count",
            "wrong_owner_reply_count",
            "stale_or_corrupt_reply_count",
        )
    )
    if MPI.COMM_WORLD.size > 1:
        assert sum(routing["request_counts_by_rank"]) > 0
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
        assert audit["interior_recovery_operator_residual_max"] <= 5.0e-11
        assert audit["interior_adjoint_operator_residual_max"] <= 5.0e-11
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

    work_block = constraints.work_owned_entity_blocks[0]
    wrong_owner = replace(
        work_block,
        active_vector_work_owner_rank=1,
    )
    wrong_owner_blocks = dict(constraints.entity_blocks)
    wrong_owner_blocks[
        (wrong_owner.dimension, wrong_owner.global_entity)
    ] = wrong_owner
    wrong_owner_work = tuple(
        wrong_owner if block is work_block else block
        for block in constraints.work_owned_entity_blocks
    )
    invalid_routing = SimpleNamespace(
        entity_map=entity_map,
        audit=constraints.audit,
        independent_trace_rows=constraints.independent_trace_rows,
        owned_cells=constraints.owned_cells,
        entity_blocks=wrong_owner_blocks,
        work_owned_entity_blocks=wrong_owner_work,
        component_gram=constraints.component_gram,
    )
    with pytest.raises(ValueError, match="wrong active-vector owner"):
        build_variable_p_condensed_trace_system(
            entity_map,
            tensors,
            trace_constraints=invalid_routing,
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

    divergent_fields = {
        "entity_map": entity_map,
        "audit": constraints.audit,
        "independent_trace_rows": constraints.independent_trace_rows,
        "owned_cells": constraints.owned_cells,
        "entity_blocks": constraints.entity_blocks,
        "component_gram": constraints.component_gram,
    }
    if MPI.COMM_WORLD.rank == 0:
        divergent_fields["work_owned_entity_blocks"] = (
            constraints.work_owned_entity_blocks
        )
    divergent_mode = SimpleNamespace(**divergent_fields)
    with pytest.raises(ValueError, match="routing-mode validation"):
        build_variable_p_condensed_trace_system(
            entity_map,
            tensors,
            trace_constraints=divergent_mode,
        )

    for mutation in ("duplicate", "missing"):
        work_blocks = list(constraints.work_owned_entity_blocks)
        if MPI.COMM_WORLD.rank == 0:
            if mutation == "duplicate":
                work_blocks.append(work_blocks[0])
            else:
                work_blocks.pop(0)
        malformed_partition = SimpleNamespace(
            entity_map=entity_map,
            audit=constraints.audit,
            independent_trace_rows=constraints.independent_trace_rows,
            owned_cells=constraints.owned_cells,
            entity_blocks=constraints.entity_blocks,
            work_owned_entity_blocks=tuple(work_blocks),
            component_gram=constraints.component_gram,
        )
        with pytest.raises(ValueError, match="partition"):
            build_variable_p_condensed_trace_system(
                entity_map,
                tensors,
                trace_constraints=malformed_partition,
            )


def test_mpi_rank_local_cell_expansion_failure_is_collective(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if MPI.COMM_WORLD.size != 2:
        pytest.skip("MPI2 rank-local cell-expansion failure control")
    if MPI.COMM_WORLD.rank == 0:

        def fail_cell_expansion(*_args, **_kwargs):
            raise RuntimeError("injected rank-local cell expansion failure")

        monkeypatch.setattr(
            broken_cell_trace_module,
            "_cell_expansion",
            fail_cell_expansion,
        )
    with pytest.raises(
        RuntimeError,
        match="cell trace expansion failed collectively",
    ):
        _single_hanging_fixture()


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
    routing = audit["owner_routed_trace_cache_audit"]
    assert routing["pass"] is True
    assert routing["dense_global_entity_catalog_replicated"] is False
    hanging_participants = {
        (int(row[0]), tuple(map(int, row[1])))
        for row in audit["cross_rank_hanging_participant_entities"]
    }
    remote_hanging_participants = {
        (int(row[0]), tuple(map(int, row[1])))
        for row in audit[
            "cross_rank_hanging_remote_participant_entities"
        ]
    }
    assert len(hanging_participants) == audit[
        "cross_rank_hanging_participant_entity_count"
    ]
    assert len(remote_hanging_participants) == audit[
        "cross_rank_hanging_remote_participant_entity_count"
    ]
    assert remote_hanging_participants <= hanging_participants
    if MPI.COMM_WORLD.size > 1:
        assert audit["cross_rank_hanging_patch_count"] > 0
        assert audit["cross_rank_hanging_relation_count"] > 0
        assert audit["cross_rank_hanging_participant_entity_count"] > 0
        assert remote_hanging_participants
        assert (
            sum(
                audit[
                    "cross_rank_hanging_remote_lookup_counts_by_rank"
                ]
            )
            > 0
        )
        assert sum(audit["remote_entity_lookup_counts_by_rank"]) > 0
        assert sum(routing["request_counts_by_rank"]) > 0
        assert all(
            count > 0
            for count in routing["work_owned_block_counts_by_rank"]
        )
        assert all(
            value > 0
            for value in routing[
                "work_owned_native_array_bytes_by_rank"
            ]
        )
        assert routing["retained_cache_duplication_factor"] >= 1.0
        assert all(
            count == 0
            for count in audit["hanging_cell_ghost_counts_by_rank"]
        )
    else:
        assert not hanging_participants
        assert not remote_hanging_participants
        assert (
            sum(
                audit[
                    "cross_rank_hanging_remote_lookup_counts_by_rank"
                ]
            )
            == 0
        )
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
        assert audit["interior_recovery_operator_residual_max"] <= 5.0e-11
        assert audit["interior_adjoint_operator_residual_max"] <= 5.0e-11
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


@pytest.mark.parametrize(
    ("p5_interior_canonical_leaves", "active_full_rows"),
    (
        (0, 6060),
        (1, 5850),
    ),
)
def test_compiled_p6_kernel_binds_to_p5_hanging_trace_rows(
    p5_interior_canonical_leaves: int,
    active_full_rows: int,
) -> None:
    if MPI.COMM_WORLD.size not in {1, 2, 8}:
        pytest.skip(
            "Task035d compiled local-h binding qualifies serial/MPI2/MPI8"
        )
    _, carrier, entity_map, _, constraints = _single_hanging_fixture(
        degree=5,
        cell_degree=6,
        p5_interior_canonical_leaves=(
            p5_interior_canonical_leaves
        ),
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
        assert (
            audit["active_full3d_rows_before_condensation"]
            == active_full_rows
        )
        assert audit["active_trace_rows_before_periodic_elimination"] == 2010
        assert audit["active_trace_rows"] == 1790
        assert audit["hanging_or_floquet_slave_rows"] == 220
        assert audit["matrix_rows"] == 1790
        assert audit["matrix_mallocs"] == 0
        assert audit["full_p6_global_matrix_constructed"] is False
        assert audit["full_active_global_matrix_constructed"] is False
        assert audit["hanging_or_floquet_slave_rows_globally_numbered"] is False
        assert audit["inactive_p6_full_rows"] >= (
            210 * p5_interior_canonical_leaves
        )
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
        recovered_full = recover_variable_p_active_full_vector(
            system,
            root,
        )
        reduced_solution = system.matrix.createVecRight()
        reduced_rhs = system.matrix.createVecLeft()
        active_rhs = recovered_full.duplicate()
        try:
            global_active = _global_vector_values(recovered_full)
            for recovery in system.cell_recovery:
                cell = recovery.cell
                expected_interior = (
                    system.interior_from_trace_by_class[
                        recovery.class_key
                    ]
                    @ global_active[cell.trace_rows]
                )
                np.testing.assert_array_equal(
                    global_active[cell.interior_rows],
                    expected_interior,
                )
            start, stop = reduced_solution.getOwnershipRange()
            reduced_solution.getArray()[:] = root[start:stop]
            reduced_solution.assemble()
            system.matrix.mult(reduced_solution, reduced_rhs)
            active_rhs.set(PETSc.ScalarType(0.0))
            active_rhs.assemble()
            reduction = VariablePAssemblyTimeReduction(
                system=system,
                transfer=None,  # type: ignore[arg-type]
                degree_plan=None,  # type: ignore[arg-type]
                build_audit={"pass": True},
            )
            residual = reduction.full_active_residual(
                system.matrix,
                reduced_rhs,
                reduced_solution,
                VariablePRecoveredSolution(
                    field=None,
                    active_full_solution=recovered_full,
                    active_full_rhs=active_rhs,
                    active_auxiliary_interior_action=None,
                    audit={"pass": True},
                ),
            )
            assert (
                residual["eliminated_cell_interior_residual_norm"]
                <= 1.0e-12
            )
            assert residual["linear_system_residual_norm"] <= 1.0e-12
        finally:
            active_rhs.destroy()
            reduced_rhs.destroy()
            reduced_solution.destroy()
            recovered_full.destroy()
        assert constraints.audit["maximum_cell_expansion_condition"] > 1.0e8
        assert constraints.audit["cell_expansion_inverse_used"] is False
        assert constraints.audit["distributed_scalability_qualified"] is False
    finally:
        system.destroy()
