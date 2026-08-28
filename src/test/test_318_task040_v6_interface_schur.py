"""Tiny V6-2 canonical-interface Schur and owner-routing contracts."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

import benchmarks.check_task040_v7_scale_normalized_identity as v7_checker
import benchmarks.task040_v6_2_interface_schur as v7_runner
from src.solvers.hybrid_interface_schur import (
    _filter_rows_by_int_set,
    build_canonical_interface_layout,
    build_petsc_d1_reference_interface_schur_mat,
    build_owner_local_group_rows,
    build_petsc_full_interface_schur_action,
    build_petsc_interface_schur_oracle,
    build_v6_cell_recovery_owner_group_rows,
)
from src.solvers.hybrid_interface_packet_dolfinx import (
    build_gamma_canonical_layout,
    make_gamma_entity_block,
)
from src.solvers.hybrid_interface_packet import canonical_key_json


GROUP_ROWS = ((0, 1, 3), (1, 2, 3, 4, 5), (2, 4, 6))
LOWER_ROWS = (1, 3)
UPPER_ROWS = (2, 4)
CANONICAL_ROWS = np.asarray(LOWER_ROWS + UPPER_ROWS, dtype=np.int64)


def _dense_bare() -> np.ndarray:
    rows = np.arange(7, dtype=float)[:, None]
    columns = np.arange(7, dtype=float)[None, :]
    matrix = (0.021 + 0.013j) * (rows + 1.0) * (columns + 2.0)
    matrix += np.diag(4.0 + 0.17j * np.arange(7))
    interior = (0, 5, 6)
    for row in interior:
        for column in interior:
            if row != column:
                matrix[row, column] = 0.0
    for row, column in (
        (0, 2),
        (0, 4),
        (2, 0),
        (4, 0),
        (6, 1),
        (6, 3),
        (1, 6),
        (3, 6),
    ):
        matrix[row, column] = 0.0
    return np.asarray(matrix, dtype=np.complex128)


def _distributed_bare(dense: np.ndarray) -> PETSc.Mat:
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, dense.shape[0]), (PETSc.DECIDE, dense.shape[1])),
        nnz=dense.shape[1],
        comm=MPI.COMM_WORLD,
    )
    first, last = map(int, matrix.getOwnershipRange())
    for row in range(first, last):
        for column, value in enumerate(dense[row]):
            matrix.setValue(row, column, PETSc.ScalarType(value))
    matrix.assemble()
    return matrix


def _local_group_rows(matrix: PETSc.Mat) -> tuple[np.ndarray, ...]:
    first, last = map(int, matrix.getOwnershipRange())
    return tuple(
        np.asarray([row for row in rows if first <= row < last], dtype=PETSc.IntType)
        for rows in GROUP_ROWS
    )


def _canonical_layout(matrix: PETSc.Mat):
    first, last = map(int, matrix.getOwnershipRange())
    lower_rows = tuple(row for row in LOWER_ROWS if first <= row < last)
    upper_rows = tuple(row for row in UPPER_ROWS if first <= row < last)
    lower_keys = tuple(
        canonical_key_json({"ordinal": LOWER_ROWS.index(row)}) for row in lower_rows
    )
    upper_keys = tuple(
        canonical_key_json({"ordinal": UPPER_ROWS.index(row)}) for row in upper_rows
    )
    return build_canonical_interface_layout(
        SimpleNamespace(
            gamma_rows_local=np.asarray(lower_rows, dtype=np.int64),
            canonical_keys=lower_keys,
        ),
        SimpleNamespace(
            gamma_rows_local=np.asarray(upper_rows, dtype=np.int64),
            canonical_keys=upper_keys,
        ),
        comm=MPI.COMM_WORLD,
        expected_lower_count=len(LOWER_ROWS),
        expected_upper_count=len(UPPER_ROWS),
    )


def _set_global_values(vector: PETSc.Vec, values: np.ndarray) -> None:
    first, last = map(int, vector.getOwnershipRange())
    vector.array[:] = np.asarray(values[first:last], dtype=PETSc.ScalarType)
    vector.assemble()


def _collect_global_values(vector: PETSc.Vec) -> np.ndarray:
    first, _last = map(int, vector.getOwnershipRange())
    local = np.asarray(vector.array, dtype=np.complex128).copy()
    pieces = MPI.COMM_WORLD.allgather((first, local))
    result = np.empty(vector.getSize(), dtype=np.complex128)
    for start, values in pieces:
        result[start : start + values.size] = values
    return result


def test_gamma_layout_cross_rank_duplicate_keys_fail_collectively() -> None:
    """A root-only duplicate finding must be propagated before any hash bcast."""

    comm = MPI.COMM_WORLD
    if comm.size != 2:
        pytest.skip("run this collective regression with MPI2")
    row = int(comm.rank)
    block = make_gamma_entity_block(
        name=f"rank{comm.rank}",
        entity_dimension=1,
        physical_entity={"rank": int(comm.rank)},
        raw_row_ids=(row,),
        canonical_to_raw=np.ones((1, 1), dtype=np.complex128),
        orientation_state={"sign": 1},
        canonical_key_records=({"shared_channel": 0},),
    )

    with pytest.raises(ValueError, match="duplicated across ranks"):
        build_gamma_canonical_layout(
            (block,),
            (row,),
            plane_identity={"test": "cross_rank_duplicate"},
            comm=comm,
        )

    # This second collective is a liveness assertion: both ranks reached the
    # common error branch instead of one rank raising before the bcast.
    assert comm.allgather(True) == [True, True]


def _reference_full_schur(dense: np.ndarray, source: np.ndarray) -> np.ndarray:
    all_rows = np.arange(dense.shape[0], dtype=np.int64)
    gamma = CANONICAL_ROWS
    interior = np.asarray(
        [row for row in all_rows if row not in set(gamma.tolist())], dtype=np.int64
    )
    a_gg = dense[np.ix_(gamma, gamma)]
    a_gi = dense[np.ix_(gamma, interior)]
    a_ig = dense[np.ix_(interior, gamma)]
    a_ii = dense[np.ix_(interior, interior)]
    return a_gg @ source - a_gi @ np.linalg.solve(a_ii, a_ig @ source)


def _full_elimination_residual(
    dense: np.ndarray, source: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    all_rows = np.arange(dense.shape[0], dtype=np.int64)
    gamma = CANONICAL_ROWS
    interior = np.asarray(
        [row for row in all_rows if row not in set(gamma.tolist())], dtype=np.int64
    )
    a_ii = dense[np.ix_(interior, interior)]
    a_ig = dense[np.ix_(interior, gamma)]
    interior_values = -np.linalg.solve(a_ii, a_ig @ source)
    full = np.zeros(dense.shape[0], dtype=np.complex128)
    full[gamma] = source
    full[interior] = interior_values
    residual = dense @ full
    return residual[gamma], residual[interior]


def _naive_sum_of_three_schurs(dense: np.ndarray, source: np.ndarray) -> np.ndarray:
    position = {row: index for index, row in enumerate(CANONICAL_ROWS.tolist())}
    result = np.zeros_like(source)
    groups = (
        ((1, 3), (0,)),
        ((1, 2, 3, 4), (5,)),
        ((2, 4), (6,)),
    )
    for gamma_rows, interior_rows in groups:
        positions = [position[row] for row in gamma_rows]
        a_gg = dense[np.ix_(gamma_rows, gamma_rows)]
        a_gi = dense[np.ix_(gamma_rows, interior_rows)]
        a_ig = dense[np.ix_(interior_rows, gamma_rows)]
        a_ii = dense[np.ix_(interior_rows, interior_rows)]
        result[positions] += (a_gg - a_gi @ np.linalg.solve(a_ii, a_ig)) @ source[
            positions
        ]
    return result


def _apply(matrix: PETSc.Mat, action, values: np.ndarray) -> np.ndarray:
    source = action.create_interface_vector()
    target = action.create_interface_vector()
    try:
        _set_global_values(source, values)
        matrix.mult(source, target)
        return _collect_global_values(target)
    finally:
        target.destroy()
        source.destroy()


def test_v7_scaled_tiny_d0_d1_and_layer_a_contract():
    """Keep scaled relative D1 evidence separate from the V6 absolute node."""

    comm = MPI.COMM_WORLD
    if comm.size not in (1, 2):
        pytest.skip("run this V7 tiny contract with serial or MPI2")
    dense = _dense_bare()
    bare = _distributed_bare(dense)
    oracle = None
    matrix = None
    d1_matrix = None
    action = None
    source = None
    d0_target = None
    d1_target = None
    summed_target = None
    contributions: list[PETSc.Vec] = []
    group_vectors: list[tuple[PETSc.Vec, PETSc.Vec, PETSc.Vec]] = []
    full_state = None
    residual = None
    try:
        canonical_layout = _canonical_layout(bare)
        first, last = map(int, bare.getOwnershipRange())
        lower_local = np.asarray(
            [row for row in LOWER_ROWS if first <= row < last], dtype=PETSc.IntType
        )
        upper_local = np.asarray(
            [row for row in UPPER_ROWS if first <= row < last], dtype=PETSc.IntType
        )
        oracle = build_petsc_interface_schur_oracle(
            bare, _local_group_rows(bare), (lower_local, upper_local)
        )
        matrix, action = build_petsc_full_interface_schur_action(
            oracle,
            canonical_layout=canonical_layout,
        )
        diagnostics = action.diagnostics
        assert diagnostics["scratch_vector_count"] == 7
        assert diagnostics["layout_template_vector_count"] == 1
        assert diagnostics["preallocated_vector_count"] == 8
        assert diagnostics["scratch_vectors_allocated_per_apply"] == 0
        d1_matrix = build_petsc_d1_reference_interface_schur_mat(action)

        source = action.create_interface_vector()
        d0_target = action.create_interface_vector()
        d1_target = action.create_interface_vector()
        summed_target = action.create_interface_vector()
        contributions = [action.create_interface_vector() for _ in range(4)]
        base = np.asarray(
            [0.7 - 0.2j, -0.4 + 0.3j, 0.2 + 0.6j, 1.1 - 0.5j],
            dtype=np.complex128,
        )
        scale_records: list[dict[str, float | str]] = []
        for scale in (2.0**-10, 1.0, 2.0**10):
            values = scale * base
            _set_global_values(source, values)
            matrix.mult(source, d0_target)
            action.apply_d1_reference(
                source,
                d1_target,
                *contributions,
            )
            d1_matrix.mult(source, summed_target)
            observed_d0 = _collect_global_values(d0_target)
            observed_d1 = _collect_global_values(d1_target)
            assert np.array_equal(
                _collect_global_values(summed_target), observed_d1
            )

            summed_target.set(0.0)
            for sign, contribution in zip(
                (1.0, -1.0, -1.0, -1.0), contributions, strict=True
            ):
                summed_target.axpy(PETSc.ScalarType(sign), contribution)
            summed_target.assemble()
            assert np.array_equal(
                _collect_global_values(summed_target), observed_d1
            )

            contribution_norms = tuple(
                float(np.linalg.norm(_collect_global_values(contribution)))
                for contribution in contributions
            )
            source_norm = float(np.linalg.norm(values))
            reference, interior_reference = _full_elimination_residual(
                dense, values
            )
            reference_norm = float(np.linalg.norm(reference))
            d0_error = float(np.linalg.norm(observed_d0 - reference))
            d1_error = float(np.linalg.norm(observed_d1 - reference))
            d0_relative = d0_error / max(
                float(np.linalg.norm(observed_d0)) + reference_norm,
                1.0e-300,
            )
            d1_relative = d1_error / max(
                float(np.linalg.norm(observed_d1)) + reference_norm,
                1.0e-300,
            )
            d0_d1_error = float(np.linalg.norm(observed_d0 - observed_d1))
            d0_d1_relative = d0_d1_error / max(
                float(np.linalg.norm(observed_d0))
                + float(np.linalg.norm(observed_d1)),
                1.0e-300,
            )
            relative_pass = (
                d0_relative <= 1.0e-10
                and d1_relative <= 1.0e-10
                and d0_d1_relative <= 1.0e-10
            )
            scale_records.append(
                {
                    "scale": float(scale),
                    "source_norm": source_norm,
                    "d0_norm": float(np.linalg.norm(observed_d0)),
                    "d1_norm": float(np.linalg.norm(observed_d1)),
                    "reference_norm": reference_norm,
                    "d0_absolute_error": d0_error,
                    "d1_absolute_error": d1_error,
                    "d0_relative": d0_relative,
                    "d1_relative": d1_relative,
                    "eta_d0_d1": d0_d1_relative,
                    "independent_full_interior_absolute_norm": float(
                        np.linalg.norm(interior_reference)
                    ),
                    "middle_boundary_norm": contribution_norms[0],
                    "middle_correction_norm": contribution_norms[1],
                    "lower_correction_norm": contribution_norms[2],
                    "upper_correction_norm": contribution_norms[3],
                    "classification": (
                        "TINY_RELATIVE_PASS"
                        if relative_pass
                        else "TINY_RELATIVE_FAIL"
                    ),
                }
            )

        assert len(scale_records) == 3
        assert len({record["classification"] for record in scale_records}) == 1
        assert all(
            record["classification"] == "TINY_RELATIVE_PASS"
            for record in scale_records
        )
        assert all(
            np.isfinite(float(record[field]))
            for record in scale_records
            for field in (
                "source_norm",
                "d0_norm",
                "d1_norm",
                "reference_norm",
                "d0_absolute_error",
                "d1_absolute_error",
                "d0_relative",
                "d1_relative",
                "eta_d0_d1",
                "independent_full_interior_absolute_norm",
                "middle_boundary_norm",
                "middle_correction_norm",
                "lower_correction_norm",
                "upper_correction_norm",
            )
        )

        _set_global_values(source, base)
        factor_identities = []
        for group in range(3):
            rhs = action.create_group_interior_vector(group)
            solution_first = action.create_group_interior_vector(group)
            solution_second = action.create_group_interior_vector(group)
            group_vectors.append((rhs, solution_first, solution_second))
            factor_before = action.group_factor_diagnostics(group)
            action.build_group_interior_rhs(group, source, rhs)
            global_group_gamma_rows = np.asarray(
                [
                    row
                    for row in GROUP_ROWS[group]
                    if row in set(CANONICAL_ROWS.tolist())
                ],
                dtype=np.int64,
            )
            local_interior_rows = oracle.group_interior_rows_local(group)
            local_positions = [
                int(np.flatnonzero(CANONICAL_ROWS == row)[0])
                for row in global_group_gamma_rows
            ]
            expected_rhs = dense[
                np.ix_(local_interior_rows, global_group_gamma_rows)
            ] @ base[local_positions]
            assert np.linalg.norm(
                np.asarray(rhs.array, dtype=np.complex128) - expected_rhs
            ) <= 1.0e-10

            action.solve_group_interior_rhs(group, rhs, solution_first)
            action.solve_group_interior_rhs(group, rhs, solution_second)
            factor_after = action.group_factor_diagnostics(group)
            assert (
                int(factor_after["solve_count"])
                - int(factor_before["solve_count"])
                == 2
            )
            assert factor_before["factor_identity"] == factor_after["factor_identity"]
            assert (
                factor_before["factor_identity"]
                != factor_before["operator_identity"]
            )
            factor_identities.append(factor_after["factor_identity"])
            local_difference = np.asarray(
                solution_first.array - solution_second.array,
                dtype=np.complex128,
            )
            local_first = np.asarray(solution_first.array, dtype=np.complex128)
            local_second = np.asarray(solution_second.array, dtype=np.complex128)
            difference_norm = np.sqrt(
                comm.allreduce(
                    float(np.vdot(local_difference, local_difference).real),
                    op=MPI.SUM,
                )
            )
            first_norm = np.sqrt(
                comm.allreduce(
                    float(np.vdot(local_first, local_first).real),
                    op=MPI.SUM,
                )
            )
            second_norm = np.sqrt(
                comm.allreduce(
                    float(np.vdot(local_second, local_second).real),
                    op=MPI.SUM,
                )
            )
            solve_repeat = float(
                difference_norm / max(first_norm + second_norm, 1.0e-300)
            )
            assert np.isfinite(solve_repeat)
            assert solve_repeat <= 1.0e-11
        assert len(set(factor_identities)) == 3

        full_state, _state_audit = action.build_full_eliminated_state(source)
        residual = bare.createVecLeft()
        bare.mult(full_state, residual)
        residual_first, _residual_last = map(int, residual.getOwnershipRange())
        backward_records = []
        for group, (rhs, _solution_first, _solution_second) in enumerate(
            group_vectors
        ):
            local_rows = oracle.group_interior_rows_local(group)
            local_residual = np.asarray(
                residual.array[local_rows - residual_first], dtype=np.complex128
            )
            local_rhs = np.asarray(rhs.array, dtype=np.complex128)
            local_residual_norm_sq = float(np.vdot(local_residual, local_residual).real)
            local_difference_norm_sq = float(
                np.vdot(local_residual - local_rhs, local_residual - local_rhs).real
            )
            local_rhs_norm_sq = float(np.vdot(local_rhs, local_rhs).real)
            residual_norm = np.sqrt(
                comm.allreduce(local_residual_norm_sq, op=MPI.SUM)
            )
            difference_norm = np.sqrt(
                comm.allreduce(local_difference_norm_sq, op=MPI.SUM)
            )
            rhs_norm = np.sqrt(comm.allreduce(local_rhs_norm_sq, op=MPI.SUM))
            denominator = float(difference_norm + rhs_norm)
            eta = float(residual_norm / max(denominator, 1.0e-300))
            backward_records.append(
                {
                    "group": group,
                    "eta": eta,
                    "denominator": float(denominator),
                }
            )
            assert np.isfinite(eta)
            assert eta <= 1.0e-10
        assert len(backward_records) == 3

        raw_metrics = v7_runner.collect_v7_scale_normalized_identity_metrics(
            comm, bare, matrix, action, oracle
        )
        checked_metrics = v7_checker.check_v7_scale_normalized_identity(raw_metrics)
        assert raw_metrics["schema"] == v7_runner.V7_SCALE_NORMALIZED_IDENTITY_SCHEMA
        assert checked_metrics["evidence_valid"] is True
        assert checked_metrics["checker_pass"] is True
        assert checked_metrics["formal_adjudication"] is False
        assert checked_metrics["gate_candidates"]["d0_pass_candidate"] is True
        assert checked_metrics["gate_candidates"]["d1_pass_candidate"] is True
        assert [item["exponent"] for item in raw_metrics["scales"]] == [-10, 0, 10]
        identity_records = raw_metrics["identity_records"]
        linearity_records = raw_metrics["linearity_records"]
        assert len(identity_records) == 9
        assert len(linearity_records) == 3
        assert all(
            {item["group"] for item in record["layer_a"]["groups"]}
            == {0, 1, 2}
            for record in identity_records
        )
        contribution_names = set(v7_checker.CONTRIBUTION_NAMES)
        assert all(
            set(record["layer_b"]) == contribution_names
            for record in linearity_records
        )
        assert all(
            set(record["layer_c"]["contribution_output_norms"])
            == contribution_names
            for record in identity_records
        )
    finally:
        if d1_matrix is not None:
            d1_matrix.destroy()
            assert action is not None and action.diagnostics["destroyed"] is False
        if residual is not None:
            residual.destroy()
        if full_state is not None:
            full_state.destroy()
        for rhs, solution_first, solution_second in reversed(group_vectors):
            solution_second.destroy()
            solution_first.destroy()
            rhs.destroy()
        for contribution in reversed(contributions):
            contribution.destroy()
        if summed_target is not None:
            summed_target.destroy()
        if d1_target is not None:
            d1_target.destroy()
        if d0_target is not None:
            d0_target.destroy()
        if source is not None:
            source.destroy()
        if matrix is not None:
            matrix.destroy()
        if action is not None:
            action.destroy()
        if oracle is not None and matrix is None:
            oracle.destroy()
        bare.destroy()


def test_v6_2_canonical_joint_action_matches_independent_full_elimination():
    dense = _dense_bare()
    bare = _distributed_bare(dense)
    oracle = None
    matrix = None
    action = None
    try:
        canonical_layout = _canonical_layout(bare)
        first, last = map(int, bare.getOwnershipRange())
        lower_local = np.asarray(
            [row for row in LOWER_ROWS if first <= row < last], dtype=PETSc.IntType
        )
        upper_local = np.asarray(
            [row for row in UPPER_ROWS if first <= row < last], dtype=PETSc.IntType
        )
        oracle = build_petsc_interface_schur_oracle(
            bare, _local_group_rows(bare), (lower_local, upper_local)
        )
        matrix, action = build_petsc_full_interface_schur_action(
            oracle,
            canonical_layout=canonical_layout,
        )
        diagnostics = action.diagnostics
        layout = diagnostics["interface_layout"]
        assert layout["canonical_order"] == "Gamma_L_then_Gamma_U_by_physical_key"
        assert layout["canonical_position_bijection"] is True
        assert layout["coverage_exact"] is True
        assert layout["owner_distributed"] is True
        assert layout["per_rank_full_interface_replica"] is False
        assert layout["root_metadata_gather"] is True
        assert layout["owner_local_mapping_count"] == len(
            canonical_layout.local_row_to_position
        )
        if MPI.COMM_WORLD.size > 1:
            assert len(canonical_layout.local_row_to_position) < (
                canonical_layout.lower_global_count
                + canonical_layout.upper_global_count
            )
        assert layout["group1_order_is_canonical"] is False
        assert layout["canonical_order_sha256"] != layout["group_order_sha256"][1]
        assert not hasattr(action, "_canonical_lower")
        assert not hasattr(action, "_canonical_upper")
        assert diagnostics["scratch_vector_count"] == 7
        assert diagnostics["layout_template_vector_count"] == 1
        assert diagnostics["preallocated_vector_count"] == 8
        assert diagnostics["scatter_count"] == 3
        assert diagnostics["numeric_allgather"] is False
        assert diagnostics["fe_numeric_allgather"] is False
        assert diagnostics["value_basis"] == "current_raw_active_coefficients"
        assert diagnostics["canonical_block_transforms_applied"] is False
        assert diagnostics["interface_layout"]["transform_required_for"] == (
            "V6-3_full_spectrum_trace_authority"
        )
        assert diagnostics["factor_count_ready"] == 3
        assert diagnostics["factor_lifecycle"]["ready"] == 3
        assert diagnostics["factor_lifecycle"]["simultaneous_max"] == 3

        forbidden_non_neighbor = np.concatenate(
            (
                dense[np.ix_([0], [2, 4])].ravel(),
                dense[np.ix_([2, 4], [0])].ravel(),
                dense[np.ix_([6], [1, 3])].ravel(),
                dense[np.ix_([1, 3], [6])].ravel(),
            )
        )
        assert np.linalg.norm(forbidden_non_neighbor) <= 1.0e-13
        assert np.linalg.norm(dense[np.ix_([1, 3], [2, 4])]) > 1.0e-8
        assert np.linalg.norm(dense[np.ix_(CANONICAL_ROWS, CANONICAL_ROWS)]) > 1.0e-8

        zero = np.zeros(4, dtype=np.complex128)
        observed_zero = _apply(matrix, action, zero)
        assert np.linalg.norm(observed_zero) <= 1.0e-13

        first = np.asarray(
            [0.7 - 0.2j, -0.4 + 0.3j, 0.2 + 0.6j, 1.1 - 0.5j],
            dtype=np.complex128,
        )
        second = np.asarray(
            [-0.2 + 0.4j, 0.9 + 0.1j, -0.6 - 0.3j, 0.5 + 0.8j],
            dtype=np.complex128,
        )
        third = np.asarray(
            [1.2 + 0.05j, 0.1 - 0.9j, 0.8 + 0.2j, -0.7 + 0.6j],
            dtype=np.complex128,
        )
        observed_first = _apply(matrix, action, first)
        observed_second = _apply(matrix, action, second)
        observed_third = _apply(matrix, action, third)
        expected_first = _reference_full_schur(dense, first)
        expected_second = _reference_full_schur(dense, second)
        expected_third = _reference_full_schur(dense, third)
        assert np.linalg.norm(observed_first - expected_first) <= 1.0e-10
        assert np.linalg.norm(observed_second - expected_second) <= 1.0e-10
        assert np.linalg.norm(observed_third - expected_third) <= 1.0e-10
        for source, expected in (
            (first, expected_first),
            (second, expected_second),
            (third, expected_third),
        ):
            gamma_residual, interior_residual = _full_elimination_residual(
                dense, source
            )
            assert np.linalg.norm(gamma_residual - expected) <= 1.0e-10
            assert np.linalg.norm(interior_residual) <= 1.0e-10

            state_source = action.create_interface_vector()
            full_state = None
            residual = bare.createVecLeft()
            try:
                _set_global_values(state_source, source)
                full_state, state_audit = action.build_full_eliminated_state(
                    state_source
                )
                bare.mult(full_state, residual)
                extracted_gamma = action.extract_interface_from_active_vector(
                    residual
                )
                try:
                    observed_gamma = _collect_global_values(extracted_gamma)
                    assert np.linalg.norm(observed_gamma - expected) <= 1.0e-10
                finally:
                    extracted_gamma.destroy()
                interior_rows = np.asarray(
                    state_audit["interior_rows_local"], dtype=np.int64
                )
                local_first, local_last = map(
                    int, residual.getOwnershipRange()
                )
                local_interior = residual.array[interior_rows - local_first]
                interior_norm = np.sqrt(
                    MPI.COMM_WORLD.allreduce(
                        float(np.vdot(local_interior, local_interior).real),
                        op=MPI.SUM,
                    )
                )
                assert interior_norm <= 1.0e-10
                assert state_audit["group_interior_solve_count"] == 3
                assert set(state_audit["gamma_rows_local"]).isdisjoint(
                    set(state_audit["interior_rows_local"])
                )
            finally:
                residual.destroy()
                if full_state is not None:
                    full_state.destroy()
                state_source.destroy()

        repeated = _apply(matrix, action, first)
        assert np.linalg.norm(repeated - observed_first) <= 1.0e-11
        alpha, beta = 0.31 - 0.27j, -0.42 + 0.16j
        combined = _apply(matrix, action, alpha * first + beta * second)
        assert (
            np.linalg.norm(combined - (alpha * observed_first + beta * observed_second))
            <= 1.0e-11
        )
        assert (
            np.linalg.norm(_naive_sum_of_three_schurs(dense, first) - expected_first)
            > 1.0e-8
        )

        first_vector = action.create_interface_vector()
        try:
            _set_global_values(first_vector, first)
            lower, upper = action.restrict_interface(first_vector)
            try:
                roundtrip = action.create_interface_vector()
                try:
                    action.prolong_interface(lower, upper, roundtrip)
                    assert (
                        np.linalg.norm(_collect_global_values(roundtrip) - first)
                        <= 1.0e-11
                    )
                finally:
                    roundtrip.destroy()
            finally:
                upper.destroy()
                lower.destroy()
        finally:
            first_vector.destroy()
        assert action.diagnostics["apply_count"] == 6
    finally:
        if matrix is not None:
            matrix.destroy()
        if action is not None:
            action.destroy()
        if oracle is not None and matrix is None:
            oracle.destroy()
        bare.destroy()
    assert action is not None
    assert action.diagnostics["destroyed"] is True
    assert action.diagnostics["factor_count_after_cleanup"] == 0
    assert action.diagnostics["group_factor_count"] == 0


def test_v6_2_condensed_rhs_and_recovery_support_nonzero_interior_rhs():
    dense = _dense_bare()
    bare = _distributed_bare(dense)
    oracle = None
    matrix = None
    action = None
    active_rhs = None
    gamma_rhs = None
    interior_rhs = {}
    condensed_rhs = None
    solution = None
    full_state = None
    residual = None
    extracted_residual = None
    try:
        canonical_layout = _canonical_layout(bare)
        local_groups = _local_group_rows(bare)
        first, last = map(int, bare.getOwnershipRange())
        lower_local = np.asarray(
            [row for row in LOWER_ROWS if first <= row < last], dtype=PETSc.IntType
        )
        upper_local = np.asarray(
            [row for row in UPPER_ROWS if first <= row < last], dtype=PETSc.IntType
        )
        oracle = build_petsc_interface_schur_oracle(
            bare, local_groups, (lower_local, upper_local)
        )
        matrix, action = build_petsc_full_interface_schur_action(
            oracle,
            canonical_layout=canonical_layout,
        )

        active_values = np.asarray(
            [
                0.8 - 0.4j,
                -0.3 + 0.7j,
                0.6 + 0.2j,
                1.1 - 0.1j,
                -0.9 + 0.5j,
                0.25 + 0.8j,
                -0.6 - 0.35j,
            ],
            dtype=np.complex128,
        )
        active_rhs = bare.createVecRight()
        _set_global_values(active_rhs, active_values)
        gamma_rhs, interior_rhs, condensed_rhs = (
            action.build_condensed_rhs_from_active_vector(active_rhs)
        )
        expected_gamma = active_values[CANONICAL_ROWS]
        assert np.linalg.norm(_collect_global_values(gamma_rhs) - expected_gamma) <= (
            1.0e-12
        )
        interior_rows = np.asarray((0, 5, 6), dtype=np.int64)
        expected_condensed = expected_gamma - dense[
            np.ix_(CANONICAL_ROWS, interior_rows)
        ] @ np.linalg.solve(
            dense[np.ix_(interior_rows, interior_rows)], active_values[interior_rows]
        )
        assert (
            np.linalg.norm(_collect_global_values(condensed_rhs) - expected_condensed)
            <= 1.0e-11
        )
        assert np.linalg.norm(_collect_global_values(active_rhs) - active_values) <= (
            1.0e-12
        )

        solution_values = np.asarray(
            [0.45 + 0.2j, -0.7 + 0.15j, 0.3 - 0.6j, 0.9 + 0.4j],
            dtype=np.complex128,
        )
        solution = action.create_interface_vector()
        _set_global_values(solution, solution_values)
        full_state, recovery_audit = action.build_full_state_from_condensed_solution(
            solution,
            interior_rhs,
        )
        assert recovery_audit["group_interior_solve_count"] == 3
        assert recovery_audit["interior_rhs_nonzero"] is True
        assert all(norm > 0.0 for norm in recovery_audit["interior_rhs_norms"])

        residual = bare.createVecLeft()
        bare.mult(full_state, residual)
        residual.axpy(PETSc.ScalarType(-1.0), active_rhs)
        extracted_residual = action.extract_interface_from_active_vector(residual)
        observed_gamma_residual = _collect_global_values(extracted_residual)
        expected_gamma_residual = _reference_full_schur(
            dense, solution_values
        ) - expected_condensed
        assert (
            np.linalg.norm(observed_gamma_residual - expected_gamma_residual)
            <= 1.0e-10
        )
        observed_full_residual = _collect_global_values(residual)
        assert np.linalg.norm(observed_full_residual[interior_rows]) <= 1.0e-10
        assert np.linalg.norm(_collect_global_values(active_rhs) - active_values) <= (
            1.0e-12
        )
    finally:
        if extracted_residual is not None:
            extracted_residual.destroy()
        if residual is not None:
            residual.destroy()
        if full_state is not None:
            full_state.destroy()
        if condensed_rhs is not None:
            condensed_rhs.destroy()
        for vector in interior_rhs.values():
            vector.destroy()
        if gamma_rhs is not None:
            gamma_rhs.destroy()
        if solution is not None:
            solution.destroy()
        if active_rhs is not None:
            active_rhs.destroy()
        if matrix is not None:
            matrix.destroy()
        if action is not None:
            action.destroy()
        if oracle is not None and matrix is None:
            oracle.destroy()
        bare.destroy()


def test_v6_2_prebuilt_row_membership_filter_preserves_large_coverage():
    rows = np.arange(200_000, dtype=PETSc.IntType)
    gamma = rows[::7]
    gamma_set = {int(row) for row in gamma}
    interior = _filter_rows_by_int_set(
        rows,
        gamma_set,
        keep_members=False,
    )
    selected = _filter_rows_by_int_set(
        rows,
        gamma_set,
        keep_members=True,
    )
    assert np.array_equal(selected, gamma)
    assert np.array_equal(
        np.sort(np.concatenate((selected, interior))),
        rows,
    )
    assert np.intersect1d(selected, interior).size == 0


def test_v6_2_owner_router_deduplicates_shared_rows_without_numeric_gather():
    comm = MPI.COMM_WORLD
    ranges = [(2 * rank, 2 * rank + 2) for rank in range(comm.size)]
    start, _last = ranges[comm.rank]
    pairs = [(start, 0), (start, 1), (start + 1, 1), (start + 1, 2)]
    if comm.rank > 0:
        pairs.extend(((start - 1, 1), (start - 1, 2)))
    rows, audit = build_owner_local_group_rows(
        np.asarray(pairs, dtype=np.int64),
        ranges,
        comm=comm,
        global_size=2 * comm.size,
    )
    assert [value.tolist() for value in rows] == [
        [start],
        [start, start + 1],
        [start + 1],
    ]
    assert audit["numeric_allgather"] is False
    assert audit["owner_local"] is True


def test_v6_2_sparse_cell_builder_routes_shared_incident_row_to_one_owner():
    comm = MPI.COMM_WORLD
    if comm.size != 2:
        pytest.skip("run this shared-cell fixture with mpiexec -n 2")
    matrix = PETSc.Mat().createAIJ(
        size=((PETSc.DECIDE, 4), (PETSc.DECIDE, 4)),
        nnz=1,
        comm=comm,
    )
    matrix.assemble()
    recovery = (SimpleNamespace(trace_original_dofs=(0,)),)
    geometry = SimpleNamespace(
        dofmap=np.asarray([[0, 1], [2, 3]], dtype=np.int64),
        x=np.asarray(
            [
                [0.0, 0.0, 0.25],
                [0.0, 0.0, 0.25],
                [0.0, 0.0, 0.35],
                [0.0, 0.0, 0.35],
            ]
        ),
    )
    condensed = SimpleNamespace(
        cell_recovery_maps=recovery,
        trace_constraints=SimpleNamespace(
            expansion_by_original={
                0: (
                    np.asarray([0], dtype=np.int64),
                    np.asarray([1.0 + 0.0j], dtype=np.complex128),
                )
            }
        ),
    )
    system = SimpleNamespace(
        static_condensation=SimpleNamespace(condensed=condensed),
        local_mesh=SimpleNamespace(
            z_values=np.arange(7, dtype=np.float64),
            mesh=SimpleNamespace(geometry=geometry),
        ),
    )
    try:
        rows, audit = build_v6_cell_recovery_owner_group_rows(system, matrix)
        assert rows[0].tolist() == ([0] if comm.rank == 0 else [])
        assert rows[1].size == 0
        assert rows[2].size == 0
        assert audit["global_boolean_mask_allocated"] is False
        assert audit["owned_cell_prefix"] is True
        assert audit["ghost_geometry_cells_ignored"] == 1
        assert audit["numeric_allgather"] is False
        assert audit["routing"]["owner_local"] is True
        assert comm.allgather(audit["routing"]["duplicate_pair_count_local"]) == [
            1,
            0,
        ]
    finally:
        matrix.destroy()
