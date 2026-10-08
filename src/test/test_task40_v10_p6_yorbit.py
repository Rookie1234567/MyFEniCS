"""Small algebra tests for the Task40 V10 p6 y-orbit core."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from src.solvers.task40_v10_p6_yorbit import (
    Q_ASSEMBLY_LEGACY,
    Q_ASSEMBLY_PREALLOCATED_V13,
    Q_ASSEMBLY_BOUNDED_V16,
    Q_ASSEMBLY_ROW_TILE_V17,
    V16StagingLimitError,
    _v16_checked_csr_layout,
    _assemble_v16_bitset_pattern,
    _project_accumulate_v16,
    TwoCellNativeTransport,
    YOrbitEntities,
    assemble_task40_v10_sector_blocks,
    build_task40_v10_sector_contexts,
    compare_task40_v10_sector_assembly,
    _summarize_task40_b0_q_assembly_pairs,
    project_reduced_contribution,
    trace_layout_coordinates,
)


class _IdentityEntities:
    def __init__(self, *, ny: int, width: int, full_rows: int):
        self.ny = ny
        self.width = width
        self.independent = np.arange(ny * width, dtype=np.int64)
        self.full_rows = full_rows
        self.dimension_counts = {3: max(1, ny)}
        self.bases = ((1, ((0, 0, 0),)),)
        self.slots = {self.bases[0]: (0, 1)}
        self.y_widths = np.ones(ny)

    def transform(self, values, *, direction):
        assert direction in {
            "primal_to_canonical",
            "primal_from_canonical",
            "dual_to_canonical",
            "dual_from_canonical",
        }
        return np.asarray(values, dtype=np.complex128).copy()


class _TwoBranchCoordinates:
    def __init__(self):
        self.maps = (
            sparse.csr_matrix(np.asarray([[1.0], [0.0]], dtype=np.complex128)),
            sparse.csr_matrix(np.asarray([[0.0], [1.0]], dtype=np.complex128)),
        )

    def q_map(self, branch, *, allocation_gate):
        allocation_gate("fixture_q_map", {"branch": branch})
        return self.maps[branch]


class _ContributionAction:
    def __init__(self, matrix):
        self.matrix = np.asarray(matrix, dtype=np.complex128)

    def iter_reduced_contribution_layouts(self, *, hhat_block_columns=None):
        del hhat_block_columns
        yield np.asarray([0, 1], dtype=np.int32), np.asarray([0, 1], dtype=np.int32), "fixture"

    def iter_reduced_contributions(self, *, allocation_gate, hhat_block_columns=None):
        del hhat_block_columns
        allocation_gate("fixture_numeric_contribution", {"rows": 2})
        yield (
            np.asarray([0, 1], dtype=np.int32),
            np.asarray([0, 1], dtype=np.int32),
            self.matrix.copy(),
            "fixture",
        )


class _LargeShapeRowTileCoordinates:
    def __init__(self, branch_size=50_000):
        self.branch_size = int(branch_size)
        source_size = 2 * self.branch_size
        branch0 = np.arange(self.branch_size, dtype=np.int32)
        branch1 = np.arange(self.branch_size, dtype=np.int32)
        self.maps = (
            sparse.csr_matrix(
                (
                    np.ones(self.branch_size, dtype=np.complex128),
                    (branch0, branch0),
                ),
                shape=(source_size, self.branch_size),
            ),
            sparse.csr_matrix(
                (
                    np.ones(self.branch_size, dtype=np.complex128),
                    (branch1 + self.branch_size, branch1),
                ),
                shape=(source_size, self.branch_size),
            ),
        )

    def q_map(self, branch, *, allocation_gate):
        allocation_gate("fixture_large_q_map", {"branch": branch})
        return self.maps[branch]


class _LargeShapeRowTileAction:
    def __init__(self, branch_size=50_000):
        n = int(branch_size)
        self.contributions = (
            (
                np.asarray([0, 20_000], dtype=np.int32),
                np.asarray([1, 30_000], dtype=np.int32),
                np.asarray([[2.0 + 0.5j, 0.0], [0.0, 3.0 - 0.25j]]),
                "branch0",
            ),
            (
                np.asarray([n + 5, n + 40_000], dtype=np.int32),
                np.asarray([n + 10, n + 45_000], dtype=np.int32),
                np.asarray([[4.0 - 0.75j, 0.0], [0.0, 5.0 + 0.125j]]),
                "branch1",
            ),
        )
        self.layout_passes = 0
        self.numeric_passes = 0

    def iter_reduced_contribution_layouts(self, *, hhat_block_columns=None):
        del hhat_block_columns
        self.layout_passes += 1
        for rows, columns, _values, label in self.contributions:
            yield rows, columns, label

    def iter_reduced_contributions(self, *, allocation_gate, hhat_block_columns=None):
        del hhat_block_columns
        self.numeric_passes += 1
        for rows, columns, values, label in self.contributions:
            allocation_gate("fixture_large_numeric_contribution", {"label": label})
            yield rows, columns, values.copy(), label


def _assemble_small_q_fixture(matrix, strategy):
    return assemble_task40_v10_sector_blocks(
        _ContributionAction(matrix),
        _TwoBranchCoordinates(),
        SimpleNamespace(global_q_indices=(0, 2)),
        allocation_gate=lambda *_args: None,
        assembly_strategy=strategy,
    )


def test_public_preallocated_assembly_retains_four_blocks_and_matches_legacy_diagonal():
    action = np.asarray(
        [[2.0 + 0.2j, 0.0], [0.0, 3.0 - 0.4j]], dtype=np.complex128
    )
    legacy, legacy_audit = _assemble_small_q_fixture(action, Q_ASSEMBLY_LEGACY)
    candidate, candidate_audit = _assemble_small_q_fixture(
        action, Q_ASSEMBLY_PREALLOCATED_V13
    )

    assert set(candidate) == {0, 2}
    assert set(candidate_audit["block_shapes"]) == {"00", "01", "10", "11"}
    assert candidate_audit["off_diagonal_relative"] == {
        "q0_q1_relative": 0.0,
        "q1_q0_relative": 0.0,
    }
    assert candidate_audit["global_csr_reallocations_during_numeric_pass"] == 0
    assert legacy_audit["assembly_strategy"] == Q_ASSEMBLY_LEGACY
    assert candidate_audit["assembly_strategy"] == Q_ASSEMBLY_PREALLOCATED_V13
    for audit in (legacy_audit, candidate_audit):
        assert audit["local_projection_call_count"] == 4
        assert audit["global_sparse_accumulation_call_count"] == 4
        assert audit["contribution_generation_seconds"] >= 0.0
        assert audit["local_projection_seconds"] >= 0.0
        assert audit["global_sparse_accumulation_seconds"] >= 0.0
        assert audit["timing_scope"]["child_intervals_are_nonoverlapping_and_already_inside_numeric_parent"]
    for q in (0, 2):
        np.testing.assert_array_equal(candidate[q].toarray(), legacy[q].toarray())
    np.testing.assert_array_equal(candidate[0].toarray(), [[2.0 + 0.2j]])
    np.testing.assert_array_equal(candidate[2].toarray(), [[3.0 - 0.4j]])



def test_public_v16_bounded_assembly_matches_legacy_and_preserves_all_block_return():
    matrix = np.asarray(
        [[2.0 + 0.2j, 0.0], [0.0, 3.0 - 0.4j]], dtype=np.complex128
    )
    legacy, _ = _assemble_small_q_fixture(matrix, Q_ASSEMBLY_LEGACY)
    bounded, audit = _assemble_small_q_fixture(matrix, Q_ASSEMBLY_BOUNDED_V16)
    all_blocks, all_audit = assemble_task40_v10_sector_blocks(
        _ContributionAction(matrix),
        _TwoBranchCoordinates(),
        SimpleNamespace(global_q_indices=(0, 2)),
        allocation_gate=lambda *_args: None,
        assembly_strategy=Q_ASSEMBLY_BOUNDED_V16,
        return_all_blocks=True,
    )

    assert set(bounded) == {0, 2}
    assert set(all_blocks) == {(0, 0), (0, 1), (1, 0), (1, 1)}
    assert all_audit["assembly_strategy"] == Q_ASSEMBLY_BOUNDED_V16
    assert audit["assembly_strategy"] == Q_ASSEMBLY_BOUNDED_V16
    assert audit["pattern_seconds"] >= 0.0
    assert audit["numeric_parent_seconds"] >= 0.0
    assert audit["numeric_parent_seconds"] == audit[
        "numeric_projection_and_accumulation_seconds"
    ]
    assert audit["timing_scope"]["parent_and_child_intervals_must_not_be_added"]
    assert audit["exact_zero_slots_retained_by_block"]["01"] > 0
    assert audit["final_nnz_by_block"]["01"] == audit["stored_pattern_slots_by_block"]["01"]
    assert audit["no_compaction_owner_copy_created"] is True
    assert audit["staging_peak_bytes_total_all_blocks"] <= audit["staging_budget_bytes_total_all_q_blocks"]
    assert audit["python_row_set_count"] == audit["full_coo_list_count"] == 0
    assert audit["global_csr_reallocations_during_numeric_pass"] == 0
    assert audit["off_diagonal_relative"] == {
        "q0_q1_relative": 0.0,
        "q1_q0_relative": 0.0,
    }
    for q in (0, 2):
        np.testing.assert_allclose(bounded[q].toarray(), legacy[q].toarray(), rtol=0.0, atol=1e-14)


def test_v16_exact_zero_cleanup_preserves_small_finite_nonzero_values():
    tiny = 1.0e-200
    matrix = np.asarray([[tiny, 0.0], [0.0, 1.0]], dtype=np.complex128)
    bounded, audit = _assemble_small_q_fixture(matrix, Q_ASSEMBLY_BOUNDED_V16)
    assert tiny in bounded[0].data
    assert audit["numeric_nonzero_entries_by_block"]["00"] == 1
    assert audit["exact_zero_cleanup"].startswith("not_applied")


def test_v17_row_tiles_cross_old_shape_limit_and_match_all_four_legacy_blocks():
    import src.solvers.task40_v10_p6_yorbit as yorbit

    n = 50_000
    action = _LargeShapeRowTileAction(n)
    coordinates = _LargeShapeRowTileCoordinates(n)
    context = SimpleNamespace(global_q_indices=(0, 1))
    gates = []
    candidate, audit = assemble_task40_v10_sector_blocks(
        action,
        coordinates,
        context,
        allocation_gate=lambda name, facts: gates.append((name, dict(facts))),
        assembly_strategy=Q_ASSEMBLY_ROW_TILE_V17,
        return_all_blocks=True,
    )
    full_shape_bitset_bytes = n * ((n + 7) // 8)

    assert full_shape_bitset_bytes > 256 * 1024**2
    assert set(candidate) == {(0, 0), (0, 1), (1, 0), (1, 1)}
    assert all(matrix.shape == (n, n) for matrix in candidate.values())
    assert candidate[0, 0].nnz == 4
    assert candidate[1, 1].nnz == 4
    assert candidate[0, 1].nnz == candidate[1, 0].nnz == 0
    assert candidate[0, 0][0, 1] == 2.0 + 0.5j
    assert candidate[0, 0][20_000, 30_000] == 3.0 - 0.25j
    assert candidate[1, 1][5, 10] == 4.0 - 0.75j
    assert candidate[1, 1][40_000, 45_000] == 5.0 + 0.125j
    assert action.layout_passes == action.numeric_passes == 1
    assert audit["assembly_strategy"] == Q_ASSEMBLY_ROW_TILE_V17
    assert audit["pattern_layout_pass_count"] == 1
    assert audit["numeric_contribution_pass_count"] == 1
    assert audit["numeric_contribution_count"] == 2
    assert audit["cartesian_support_pairs_materialized"] == 0
    assert audit["cartesian_support_pair_cardinality_by_block"] == {
        "00": 4, "01": 0, "10": 0, "11": 4,
    }
    assert audit["route_query_uses_temporary_sort"] is False
    assert audit["support_route_spool_removed_after_pattern"] is True
    assert audit["temporary_filesystem_free_space_reserve_bytes"] == (
        yorbit.V17_SQLITE_FREE_SPACE_RESERVE_BYTES
    )
    assert audit["staging_peak_bytes_total_all_blocks"] <= audit["staging_budget_bytes_total_all_q_blocks"]
    assert audit["full_shape_bitset_bytes"] == 0
    assert audit["full_coo_list_count"] == 0
    assert audit["global_python_row_set_count"] == 0
    assert audit["all_four_complete_csr_owners_retained_through_norm_gate"] is True
    assert audit["complete_csr_frobenius_norm_by_block"]["00"] == pytest.approx(
        np.sqrt(13.3125)
    )
    assert audit["complete_csr_frobenius_norm_by_block"]["11"] == pytest.approx(
        np.sqrt(41.578125)
    )
    assert audit["off_diagonal_relative"] == {
        "q0_q1_relative": 0.0,
        "q1_q0_relative": 0.0,
    }
    assert all(facts.get("staging_live_bytes_upper", 0) <= 256 * 1024**2 for _, facts in gates)

    report = compare_task40_v10_sector_assembly(
        action,
        coordinates,
        context,
        allocation_gate=lambda *_args: None,
        candidate_strategy=Q_ASSEMBLY_ROW_TILE_V17,
    )
    assert report["all_four_blocks_independently_compared"] is True
    assert report["numerically_equivalent_at_original_operator_gate"] is True
    assert report["candidate_selected_for_next_formal_case"] is True
    assert set(report["block_comparisons"]) == {"00", "01", "10", "11"}


def test_v17_csr_layout_checks_inttype_before_narrowing():
    from src.solvers.task40_v10_p6_yorbit import _v17_checked_row_tile_csr_layout

    limit = int(np.iinfo(np.int32).max)
    with pytest.raises(OverflowError, match="shape"):
        _v17_checked_row_tile_csr_layout((limit + 1, 0), [], np.int32)
    with pytest.raises(OverflowError, match="NNZ/indptr"):
        _v17_checked_row_tile_csr_layout((2, limit), [limit, 1], np.int32)
    with pytest.raises(ValueError, match="outside its checked range"):
        _v17_checked_row_tile_csr_layout((2, 1), [2, 0], np.int32)


def _v16_target_with_support(rows_count, columns_count, row_support, column_support):
    row_ids = np.repeat(row_support, len(column_support))
    column_ids = np.tile(column_support, len(row_support))
    values = np.zeros(len(row_ids), dtype=np.complex128)
    return sparse.csr_matrix(
        (values, (row_ids, column_ids)), shape=(rows_count, columns_count)
    )


def _assert_csr_equivalent_and_action(candidate, reference, *, probe_seed):
    difference = (candidate - reference).tocsr()
    assert difference.data.size == 0 or float(np.max(np.abs(difference.data))) <= 2.0e-12
    rng = np.random.default_rng(probe_seed)
    probe = rng.standard_normal(reference.shape[1]) + 1j * rng.standard_normal(reference.shape[1])
    np.testing.assert_allclose(candidate @ probe, reference @ probe, rtol=2.0e-12, atol=2.0e-12)


def test_v16_projection_uses_exact_support_for_b0_sized_local_block():
    import src.solvers.task40_v10_p6_yorbit as yorbit

    local_size = 432
    global_size = 8192
    support_size = 16
    rows = np.arange(local_size, dtype=np.int32)
    columns = np.arange(local_size, dtype=np.int32)
    support = np.arange(support_size, dtype=np.int32)
    indices = np.tile(support, local_size)
    indptr = np.arange(local_size + 1, dtype=np.int32) * support_size
    weights = np.tile(
        np.linspace(0.5, 1.25, support_size, dtype=np.float64).astype(np.complex128),
        local_size,
    )
    left = sparse.csr_matrix((weights, indices, indptr), shape=(local_size, global_size))
    right = sparse.csr_matrix((weights * (0.75 + 0.125j), indices, indptr), shape=(local_size, global_size))
    rng = np.random.default_rng(711)
    values = rng.standard_normal((local_size, local_size)) + 1j * rng.standard_normal((local_size, local_size))
    target = _v16_target_with_support(global_size, global_size, support, support)

    left_nnz = int(left.nnz)
    right_nnz = int(right.nnz)
    old_left_support = min(left.shape[1], left_nnz)
    old_right_support = min(right.shape[1], right_nnz)
    old_dense_upper = 16 * (
        2 * local_size * old_left_support
        + old_left_support * local_size
        + local_size * old_right_support
        + old_left_support * old_right_support
    )
    assert values.nbytes == 2_985_984  # 432-by-432 complex128 B0-scale projection fixture.
    assert old_dense_upper > yorbit.V16_Q_STAGING_BUDGET_BYTES

    gates = []
    projection_s, accumulation_s, staging_peak = _project_accumulate_v16(
        target,
        left,
        right,
        rows,
        columns,
        values,
        allocation_gate=lambda name, facts: gates.append((name, dict(facts))),
        label="b0-sized/repeated-support",
    )
    assert projection_s >= 0.0 and accumulation_s >= 0.0
    assert staging_peak <= yorbit.V16_Q_STAGING_BUDGET_BYTES
    support_gate = next(facts for name, facts in gates if "support_discovery" in name)
    projection_gate = next(
        facts for name, facts in gates if name == "task40_v16_q_projection_support/b0-sized/repeated-support"
    )
    assert support_gate["staging_live_bytes_upper"] <= yorbit.V16_Q_STAGING_BUDGET_BYTES
    assert projection_gate["left_support_count"] == support_size
    assert projection_gate["right_support_count"] == support_size
    assert projection_gate["projection_tile_count"] == 1
    legacy = project_reduced_contribution(
        left,
        right,
        rows,
        columns,
        values,
        allocation_gate=lambda *_args: None,
        label="b0-sized/repeated-support",
    )
    _assert_csr_equivalent_and_action(target, legacy, probe_seed=712)


def test_v16_projection_tiles_exact_support_without_recomputing_contributions(monkeypatch):
    import weakref
    import src.solvers.task40_v10_p6_yorbit as yorbit

    local_size = 432
    support_size = 864
    support = np.arange(support_size, dtype=np.int32)
    rows = np.arange(local_size, dtype=np.int32)
    columns = rows.copy()
    indices = np.arange(support_size, dtype=np.int32)
    indptr = np.arange(local_size + 1, dtype=np.int32) * 2
    left_data = np.linspace(0.75, 1.25, support_size, dtype=np.float64).astype(np.complex128)
    right_data = left_data * (0.875 - 0.125j)
    left = sparse.csr_matrix((left_data, indices, indptr), shape=(local_size, support_size))
    right = sparse.csr_matrix((right_data, indices, indptr), shape=(local_size, support_size))
    rng = np.random.default_rng(713)
    values = rng.standard_normal((local_size, local_size)) + 1j * rng.standard_normal((local_size, local_size))
    target = _v16_target_with_support(support_size, support_size, support, support)
    monkeypatch.setattr(yorbit, "V16_Q_STAGING_BUDGET_BYTES", 56 * 1024**2)

    gates = []
    projected_owners = []
    original_accumulator = yorbit._accumulate_v16_projection_tile

    def checked_accumulator(target_arg, projected, row_ids, column_ids, *, label):
        if projected_owners:
            assert projected_owners[-1]() is None
        elapsed = original_accumulator(
            target_arg, projected, row_ids, column_ids, label=label
        )
        projected_owners.append(weakref.ref(projected))
        return elapsed

    monkeypatch.setattr(yorbit, "_accumulate_v16_projection_tile", checked_accumulator)
    _project_accumulate_v16(
        target,
        left,
        right,
        rows,
        columns,
        values,
        allocation_gate=lambda name, facts: gates.append((name, dict(facts))),
        label="b0-sized/tile-required",
    )
    projection_gate = next(
        facts for name, facts in gates if name == "task40_v16_q_projection_support/b0-sized/tile-required"
    )
    assert projection_gate["projection_tile_count"] > 1
    assert projection_gate["projection_row_tile_count"] == 1
    assert projection_gate["projection_column_tile_count"] > 1
    assert projection_gate["projection_left_product_count"] == 1
    assert projection_gate["projection_live_output_tile_peak"] == 1
    assert len(projected_owners) == projection_gate["projection_tile_count"]
    assert all(owner() is None for owner in projected_owners)
    assert projection_gate["staging_live_bytes_upper"] <= 56 * 1024**2
    assert all(facts["staging_live_bytes_upper"] <= 56 * 1024**2 for _, facts in gates)

    legacy = project_reduced_contribution(
        left,
        right,
        rows,
        columns,
        values,
        allocation_gate=lambda *_args: None,
        label="b0-sized/tile-required",
    )
    _assert_csr_equivalent_and_action(target, legacy, probe_seed=714)


def test_v16_staging_budget_raises_typed_resource_gate_before_bitset_allocation(monkeypatch):
    import src.solvers.task40_v10_p6_yorbit as yorbit

    monkeypatch.setattr(yorbit, "V16_Q_STAGING_BUDGET_BYTES", yorbit.V16_PYTHON_OVERHEAD_RESERVE_BYTES)
    q_maps = _TwoBranchCoordinates().maps
    with pytest.raises(V16StagingLimitError) as captured:
        _assemble_v16_bitset_pattern(
            _ContributionAction(np.eye(2, dtype=np.complex128)),
            q_maps,
            (0, 0),
            allocation_gate=lambda *_args: None,
        )
    assert captured.value.evidence() == {
        "condition": "V16_BOUNDED_STAGING_LIMIT",
        "label": "pattern_bitset/p0q0",
        "required_bytes": yorbit.V16_PYTHON_OVERHEAD_RESERVE_BYTES + 1,
        "limit_bytes": yorbit.V16_PYTHON_OVERHEAD_RESERVE_BYTES,
    }


def test_v16_csr_bounds_use_python_integer_prefixes_before_allocation():
    limit = int(np.iinfo(np.int32).max)
    total, payload = _v16_checked_csr_layout((2, limit), [limit - 1, 1])
    assert total == limit
    assert payload == 3 * np.dtype(np.int32).itemsize + limit * (
        np.dtype(np.int32).itemsize + np.dtype(np.complex128).itemsize
    )
    with pytest.raises(OverflowError, match="NNZ/indptr"):
        _v16_checked_csr_layout((2, limit), [limit, 1])
    with pytest.raises(OverflowError, match="shape"):
        _v16_checked_csr_layout((2, limit + 1), [0, 0])

def test_public_preallocated_assembly_rejects_uncancelled_off_diagonal_q_blocks():
    matrix = np.asarray(
        [[2.0, 0.25 - 0.1j], [0.25 + 0.1j, 3.0]], dtype=np.complex128
    )
    with np.testing.assert_raises_regex(ValueError, "not diagonal in local q branches"):
        _assemble_small_q_fixture(matrix, Q_ASSEMBLY_PREALLOCATED_V13)


def test_paired_q_assembly_compares_all_blocks_and_actions_with_staged_oracles():
    matrix = np.asarray(
        [[2.0 + 0.2j, 0.0], [0.0, 3.0 - 0.4j]], dtype=np.complex128
    )
    report = compare_task40_v10_sector_assembly(
        _ContributionAction(matrix),
        _TwoBranchCoordinates(),
        SimpleNamespace(global_q_indices=(0, 2)),
        allocation_gate=lambda *_args: None,
    )

    assert report["all_four_blocks_independently_compared"]
    assert report["legacy_csr_oracle_released_before_candidate_assembly"]
    assert set(report["block_comparisons"]) == {"00", "01", "10", "11"}
    assert report["numerically_equivalent_at_original_operator_gate"]
    assert report["max_csr_difference_relative_to_diagonal"] == 0.0
    assert report["max_action_difference_relative_to_diagonal"] == 0.0
    assert report["legacy_off_diagonal_relative"] == {
        "q0_q1_relative": 0.0,
        "q1_q0_relative": 0.0,
    }
    assert report["candidate_off_diagonal_relative"] == {
        "q0_q1_relative": 0.0,
        "q1_q0_relative": 0.0,
    }


def test_b0_comparison_only_summary_checks_q_coverage_and_four_block_shapes():
    profile = SimpleNamespace(
        q_count=4,
        augmented_rows_per_q=(3, 4, 5, 6),
        identity=lambda: {"name": "fixture-b0"},
    )
    comparisons = {key: {"shape": [1, 1]} for key in ("00", "01", "10", "11")}
    reports = [
        {
            "global_q_indices": [0, 2],
            "block_shapes": {
                "00": [3, 3], "01": [3, 5], "10": [5, 3], "11": [5, 5]
            },
            "block_comparisons": comparisons,
            "legacy_assembly_seconds": 2.0,
            "candidate_assembly_seconds": 1.0,
            "all_four_blocks_independently_compared": True,
            "numerically_equivalent_at_original_operator_gate": True,
        },
        {
            "global_q_indices": [1, 3],
            "block_shapes": {
                "00": [4, 4], "01": [4, 6], "10": [6, 4], "11": [6, 6]
            },
            "block_comparisons": comparisons,
            "legacy_assembly_seconds": 2.0,
            "candidate_assembly_seconds": 1.0,
            "all_four_blocks_independently_compared": True,
            "numerically_equivalent_at_original_operator_gate": True,
        },
    ]

    summary = _summarize_task40_b0_q_assembly_pairs(profile, reports, {0, 1, 2, 3})

    assert summary["covered_q"] == [0, 1, 2, 3]
    assert summary["candidate_selected_for_formal_cases"]
    assert summary["selected_strategy"] == Q_ASSEMBLY_PREALLOCATED_V13
    assert not summary["mumps_factors_constructed"]
    with np.testing.assert_raises_regex(ValueError, "does not cover every"):
        _summarize_task40_b0_q_assembly_pairs(
            profile, [{**reports[0], "block_shapes": {"00": [3, 3]}}, reports[1]], {0, 1, 2, 3}
        )


def test_two_cell_transport_is_the_dual_of_primal_lift():
    cfg = SimpleNamespace(
        ky=0.25 + 0j,
        period_y=4.0,
        floquet_phase_y=np.exp(1j),
    )
    full = _IdentityEntities(ny=4, width=2, full_rows=12)
    local = _IdentityEntities(ny=2, width=2, full_rows=6)
    transport = TwoCellNativeTransport(
        full,
        local,
        twist_index=1,
        eta=np.exp(1j * (1.0 + 2.0 * np.pi) / 4),
        cfg=cfg,
    )
    rng = np.random.default_rng(17)
    rhs = rng.normal(size=8) + 1j * rng.normal(size=8)
    local_primal = rng.normal(size=4) + 1j * rng.normal(size=4)
    folded = transport.fold_dual(rhs)
    lifted = transport.lift_primal(local_primal)
    np.testing.assert_allclose(
        np.vdot(rhs, lifted), np.vdot(folded, local_primal), rtol=1e-13, atol=1e-13
    )


def test_sector_contexts_assign_all_runtime_modes_by_physical_phase():
    cfg = SimpleNamespace(
        ky=0.25 + 0j,
        period_y=4.0,
        floquet_phase_y=np.exp(1j),
    )
    axes = {
        "x": (0.0, 1.0),
        "y": (0.0, 1.0, 2.0, 3.0, 4.0),
        "z": (0.0, 1.0),
    }
    counts = (3, 2, 4, 5)
    modes = []
    for q, count in enumerate(counts):
        phase = np.exp(1j * (1.0 + 2.0 * np.pi * q) / 4)
        modes.extend(SimpleNamespace(gamma=float(np.angle(phase))) for _ in range(count))
    contexts = build_task40_v10_sector_contexts(tuple(modes), cfg, axes)
    assert [tuple(ctx.global_q_indices) for ctx in contexts] == [(0, 2), (1, 3)]
    assert [len(ctx.original_mode_indices) for ctx in contexts] == [7, 7]
    assert [tuple(np.bincount(ctx.local_branch_indices, minlength=2)) for ctx in contexts] == [
        (3, 4),
        (2, 5),
    ]
    joined = np.concatenate([ctx.original_mode_indices for ctx in contexts])
    np.testing.assert_array_equal(np.sort(joined), np.arange(len(modes)))


def test_streamed_contribution_projection_matches_dense_congruence():
    rng = np.random.default_rng(23)
    left = sparse.csr_matrix(
        np.asarray(
            [[1, 0, 0], [0, 1j, 0], [1, 1, 0], [0, 0, 1]],
            dtype=np.complex128,
        )
    )
    right = sparse.csr_matrix(
        np.asarray(
            [[1, 0], [0, 1], [1j, 1], [0, 1], [1, -1]],
            dtype=np.complex128,
        )
    )
    rows = np.asarray([0, 2, 3], dtype=np.int32)
    columns = np.asarray([0, 1, 2, 4], dtype=np.int32)
    block = rng.normal(size=(3, 4)) + 1j * rng.normal(size=(3, 4))
    gates = []
    projected = project_reduced_contribution(
        left,
        right,
        rows,
        columns,
        block.astype(np.complex128),
        allocation_gate=lambda stage, facts: gates.append((stage, facts)),
        label="fixture",
    )
    expected = left[rows, :].conj().T @ block @ right[columns, :]
    np.testing.assert_allclose(projected.toarray(), expected, rtol=1e-13, atol=1e-13)
    assert gates and gates[0][1]["global_q_factor_count"] == 0


def test_trace_restriction_keeps_trace_channels_and_local_cell_dft():
    edge = (1, ((0, 0, 0),))
    face = (2, ((0, 0, 0), (0, 0, 1)))
    interior = (3, ((0, 0, 0),))
    entities = YOrbitEntities(
        independent=np.arange(6, dtype=np.int64),
        full_rows=6,
        ny=2,
        width=3,
        bases=(edge, face, interior),
        records={
            (0, edge): (np.asarray([0]), np.asarray([[1.0 + 0j]])),
            (1, edge): (np.asarray([2]), np.asarray([[1.0 + 0j]])),
            (0, face): (np.asarray([1]), np.asarray([[1.0 + 0j]])),
            (1, face): (np.asarray([3]), np.asarray([[1.0 + 0j]])),
            (0, interior): (np.asarray([4]), np.asarray([[1.0 + 0j]])),
            (1, interior): (np.asarray([5]), np.asarray([[1.0 + 0j]])),
        },
        slots={edge: (0, 1), face: (1, 1), interior: (2, 1)},
        dimension_counts={1: 2, 2: 2, 3: 2},
        y_widths=np.ones(2),
    )
    system = SimpleNamespace(
        full_rows=6,
        active_rows=4,
        active_interior_rows=2,
        trace_constraints=SimpleNamespace(
            owned_active_original_dofs=np.asarray([0, 1, 2, 3], dtype=np.int64)
        ),
        cell_recovery_maps=(
            SimpleNamespace(interior_original_dofs=np.asarray([4], dtype=np.int64)),
            SimpleNamespace(interior_original_dofs=np.asarray([5], dtype=np.int64)),
        ),
    )
    trace = trace_layout_coordinates(
        entities,
        system,
        cell_phase_y=np.exp(0.2j),
        allocation_gate=lambda _stage, _facts: None,
    )
    assert trace["R_t"].shape == (4, 4)
    assert trace["F_t"].shape == (4, 4)
    assert trace["trace_width"] == 2
    np.testing.assert_allclose(
        (trace["R_t"] @ trace["F_t"]).toarray(),
        trace["F_t"].toarray(),
        rtol=1e-13,
        atol=1e-13,
    )
    assert trace["audit"]["complete_trace_rows"] == 4


def test_nonunitary_complex_native_entities_preserve_primal_dual_work_and_two_twist_reconstruction():
    cfg = SimpleNamespace(
        ky=0.25 + 0j,
        period_y=4.0,
        floquet_phase_y=np.exp(1j),
    )
    base = (1, ((0, 0, 0), (1, 0, 0)))
    full_matrices = (
        np.asarray([[1.2 + 0.2j, 0.3 - 0.1j], [0.1 + 0.05j, 0.8 - 0.2j]]),
        np.asarray([[0.9 - 0.1j, 0.2 + 0.3j], [-0.15 + 0.1j, 1.1 + 0.2j]]),
        np.asarray([[1.3 + 0.1j, -0.1 + 0.2j], [0.25 + 0.1j, 0.7 - 0.15j]]),
        np.asarray([[0.85 + 0.2j, 0.15 - 0.1j], [0.1 + 0.2j, 1.25 - 0.1j]]),
    )
    assert any(
        not np.allclose(matrix.conj().T @ matrix, np.eye(2))
        for matrix in full_matrices
    )

    def entities(ny, matrices):
        return YOrbitEntities(
            independent=np.arange(2 * ny, dtype=np.int64),
            full_rows=2 * ny + 3,
            ny=ny,
            width=2,
            bases=(base,),
            records={
                (orbit, base): (
                    np.asarray([2 * orbit, 2 * orbit + 1], dtype=np.int64),
                    matrix.astype(np.complex128),
                )
                for orbit, matrix in enumerate(matrices)
            },
            slots={base: (0, 2)},
            dimension_counts={1: 2 * ny, 3: ny},
            y_widths=np.ones(ny),
        )

    full = entities(4, full_matrices)
    local = entities(2, full_matrices[:2])
    rng = np.random.default_rng(31)
    rhs = rng.normal(size=8) + 1j * rng.normal(size=8)
    primal = rng.normal(size=4) + 1j * rng.normal(size=4)
    recon = np.zeros_like(rhs)
    for twist in (0, 1):
        eta = np.exp(1j * (1.0 + 2.0 * np.pi * twist) / 4)
        transport = TwoCellNativeTransport(
            full,
            local,
            twist_index=twist,
            eta=eta,
            cfg=cfg,
        )
        folded_dual = transport.fold_dual(rhs)
        lifted_primal = transport.lift_primal(primal)
        np.testing.assert_allclose(
            np.vdot(rhs, lifted_primal),
            np.vdot(folded_dual, primal),
            rtol=2e-13,
            atol=2e-13,
        )
        local_primal = transport.extract_primal(rhs)
        local_dual = rng.normal(size=4) + 1j * rng.normal(size=4)
        lifted_dual = transport.lift_dual(local_dual)
        np.testing.assert_allclose(
            np.vdot(local_dual, local_primal),
            np.vdot(lifted_dual, rhs),
            rtol=2e-13,
            atol=2e-13,
        )
        recon += transport.lift_primal(transport.extract_primal(rhs))
    np.testing.assert_allclose(recon, rhs, rtol=3e-13, atol=3e-13)
