"""Small algebra tests for the Task40 V10 p6 y-orbit core."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
from scipy import sparse

from src.solvers.task40_v10_p6_yorbit import (
    TwoCellNativeTransport,
    YOrbitEntities,
    build_task40_v10_sector_contexts,
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
