"""Small algebra tests for the Task40 V10 p6 y-orbit core."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from scipy import sparse

from src.solvers.task40_v10_p6_yorbit import (
    Q_ASSEMBLY_LEGACY,
    Q_ASSEMBLY_PREALLOCATED_V13,
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

    def iter_reduced_contribution_layouts(self):
        yield np.asarray([0, 1], dtype=np.int32), np.asarray([0, 1], dtype=np.int32), "fixture"

    def iter_reduced_contributions(self, *, allocation_gate):
        allocation_gate("fixture_numeric_contribution", {"rows": 2})
        yield (
            np.asarray([0, 1], dtype=np.int32),
            np.asarray([0, 1], dtype=np.int32),
            self.matrix.copy(),
            "fixture",
        )


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
