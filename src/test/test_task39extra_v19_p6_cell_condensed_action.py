"""Small reference-free tests for the V19 p6 action-only algebra."""

from __future__ import annotations

from dataclasses import dataclass
import gc
from types import SimpleNamespace
import weakref

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc
from scipy import sparse
from scipy.linalg import lu_factor, lu_solve

from src.solvers.hcurl_assembly_time_condensation import CellRecoveryMap
from src.solvers.augmented_reference_correction import (
    augmented_port_state_offset,
    evaluate_complete_augmented_residual,
    stable_euclidean_norm,
)
from src.solvers.p6_cell_condensed_action import (
    P6MatrixFreeHhatTerm,
    P6CellCondensedAction,
    P6CellPortTerms,
    P6GeneratedCellPortAction,
    P6DirectTracePortTerms,
    P6GlobalDirectCarrierProvider,
    P6RetainedBALHBridge,
    apply_p6_hhat_vector_action,
    build_p6_cell_condensed_action_from_carrier,
    build_p6_cell_condensed_action_from_generated,
    condense_physical_cell_blocks,
    native_residual_from_augmented,
    raw_plane_D_action_from_global_normalized,
)
from src.solvers.original_port_blocks import (
    DenseOriginalPortBlock,
    DiagonalOriginalPortBlock,
)
from src.solvers.retained_port_block_layout import RESEARCH_PORT_LAYOUT
from src.solvers.task40_v10_p6_yorbit import (
    Q_ASSEMBLY_BOUNDED_V16,
    Q_ASSEMBLY_LEGACY,
    assemble_task40_v10_sector_blocks,
    compare_task40_v10_sector_assembly,
)


def _matrix(rng: np.random.Generator, rows: int, columns: int, diagonal: float = 0.0) -> np.ndarray:
    value = rng.normal(size=(rows, columns)) + 1j * rng.normal(size=(rows, columns))
    if rows == columns:
        value += diagonal * np.eye(rows)
    return value.astype(np.complex128)


@dataclass
class _FakeCondensed:
    blocks: tuple[dict[str, np.ndarray], ...]
    appended_rows: int = 2

    def __post_init__(self) -> None:
        self.matrix = None
        self.active_rows = 2
        self.appended_rows = int(self.appended_rows)
        self.full_rows = 4
        self.owned_active_rows = 2
        self.owned_appended_rows = 2
        self.comm = MPI.COMM_SELF
        trace = np.asarray([2, 3], dtype=PETSc.IntType)
        self.owned_trace_original_dofs = trace.copy()
        self.trace_constraints = SimpleNamespace(
            owned_active_original_dofs=trace.copy(),
            original_to_active={2: 0, 3: 1},
            expansion_by_original={
                2: (np.asarray([0], dtype=PETSc.IntType), np.asarray([1.0 + 0.0j])),
                3: (np.asarray([1], dtype=PETSc.IntType), np.asarray([1.0 + 0.0j])),
            },
        )
        self.cell_recovery_maps = tuple(
            CellRecoveryMap(
                interior_original_dofs=np.asarray([0, 1], dtype=PETSc.IntType),
                trace_original_dofs=trace.copy(),
                class_key=(index,),
            )
            for index, _block in enumerate(self.blocks)
        )
        self.interior_lu_by_class = {}
        self.interior_from_trace_by_class = {}
        self.trace_from_interior_rhs_by_class = {}
        self.retained_local_schur_by_class = {}
        for index, block in enumerate(self.blocks):
            factor = lu_factor(block["Vii"])
            xit = lu_solve(factor, block["Vit"])
            self.interior_lu_by_class[(index,)] = factor
            self.interior_from_trace_by_class[(index,)] = -xit
            self.trace_from_interior_rhs_by_class[(index,)] = -block["Vti"] @ lu_solve(
                factor, np.eye(2, dtype=np.complex128)
            )
            self.retained_local_schur_by_class[(index,)] = block["Vtt"] - block["Vti"] @ xit
        self.build_audit = {}

    def create_augmented_vector(self) -> PETSc.Vec:
        return PETSc.Vec().createSeq(self.active_rows + self.appended_rows, comm=PETSc.COMM_SELF)

    def destroy(self) -> None:
        self.matrix = None


def _problem() -> tuple[_FakeCondensed, dict[str, np.ndarray], P6CellCondensedAction]:
    rng = np.random.default_rng(20260914)
    block = {
        "Vii": _matrix(rng, 2, 2, 5.0),
        "Vit": _matrix(rng, 2, 2),
        "Vti": _matrix(rng, 2, 2),
        "Vtt": _matrix(rng, 2, 2, 3.0),
        "Bi": _matrix(rng, 2, 2),
        "Bt": _matrix(rng, 2, 2),
        "Di": _matrix(rng, 2, 2),
        "Dt": _matrix(rng, 2, 2),
        "H": _matrix(rng, 2, 2, 4.0),
    }
    condensed = _FakeCondensed((block,))
    terms = {
        0: P6CellPortTerms(
            block["Bi"], block["Di"], np.asarray([0, 1], dtype=PETSc.IntType),
            Bt=block["Bt"], Dt=block["Dt"], H=block["H"],
        )
    }
    action = P6CellCondensedAction(condensed, H_p=block["H"] * 0.0 + _matrix(rng, 2, 2, 6.0), port_terms=terms)
    return condensed, block, action


def test_absent_cached_port_blocks_match_explicit_zeros_without_dense_payload() -> None:
    condensed, block, seed_action = _problem()
    hp = seed_action._H_p.copy()
    seed_action.destroy()
    rng = np.random.default_rng(20261010)
    ports = np.asarray([0, 1], dtype=PETSc.IntType)
    bi = np.asarray(1.0e-12 * block["Bi"], dtype=np.complex128)
    di = np.asarray(1.0e-12 * block["Di"], dtype=np.complex128)
    explicit_zero_terms = {
        0: P6CellPortTerms(
            bi,
            di,
            ports,
            Bt=np.zeros((2, 2), dtype=np.complex128),
            Dt=np.zeros((2, 2), dtype=np.complex128),
            H=np.zeros((2, 2), dtype=np.complex128),
        )
    }
    absent_terms = {
        0: P6CellPortTerms(bi, di, ports, Bt=None, Dt=None, H=None)
    }
    direct_terms = (
        P6DirectTracePortTerms(
            port_index=0,
            B_original_rows=np.asarray([2], dtype=PETSc.IntType),
            B_values=np.asarray([1.0e-15 + 2.0e-15j], dtype=np.complex128),
            D_original_rows=np.asarray([3], dtype=PETSc.IntType),
            D_values=np.asarray([-2.0e-15 + 1.0e-15j], dtype=np.complex128),
        ),
    )
    explicit_zero = P6CellCondensedAction(
        condensed,
        H_p=hp,
        port_terms=explicit_zero_terms,
        direct_trace_terms=direct_terms,
    )
    absent = P6CellCondensedAction(
        condensed,
        H_p=hp,
        port_terms=absent_terms,
        direct_trace_terms=direct_terms,
    )
    try:
        assert absent._cells[0].Bt is None
        assert absent._cells[0].Dt is None
        assert absent._cells[0].Hlocal is None
        assert np.any(absent._cells[0].Bi != 0.0)
        assert np.any(absent._cells[0].Di != 0.0)
        assert np.any(absent._H_p != 0.0)

        reduced = rng.normal(size=absent.reduced_size) + 1j * rng.normal(
            size=absent.reduced_size
        )
        full_rhs = rng.normal(size=condensed.full_rows) + 1j * rng.normal(
            size=condensed.full_rows
        )
        port_rhs = rng.normal(size=condensed.appended_rows) + 1j * rng.normal(
            size=condensed.appended_rows
        )
        recovered_zero = explicit_zero.recover_storage(reduced, full_rhs=full_rhs)
        recovered_absent = absent.recover_storage(reduced, full_rhs=full_rhs)
        comparisons = (
            ("reduced_action", explicit_zero.apply(reduced), absent.apply(reduced)),
            (
                "condensed_rhs",
                explicit_zero.reduce_rhs(full_rhs, port_rhs=port_rhs),
                absent.reduce_rhs(full_rhs, port_rhs=port_rhs),
            ),
            ("recovery", recovered_zero, recovered_absent),
            (
                "full_B",
                explicit_zero.apply_B_full(reduced[condensed.active_rows :]),
                absent.apply_B_full(reduced[condensed.active_rows :]),
            ),
            (
                "full_D",
                explicit_zero.apply_D_full(recovered_zero),
                absent.apply_D_full(recovered_absent),
            ),
        )
        for _name, expected, observed in comparisons:
            np.testing.assert_allclose(observed, expected, rtol=0.0, atol=0.0)

        old_inventory = explicit_zero.buffer_inventory
        new_inventory = absent.buffer_inventory
        assert old_inventory["raw_port_payload_bytes_sum"] - new_inventory[
            "raw_port_payload_bytes_sum"
        ] == 3 * 2 * 2 * np.dtype(np.complex128).itemsize
        assert old_inventory["staging_port_payload_bytes_sum"] - new_inventory[
            "staging_port_payload_bytes_sum"
        ] == 3 * 2 * 2 * np.dtype(np.complex128).itemsize
        assert old_inventory["unique_port_payload_owner_bytes"] > new_inventory[
            "unique_port_payload_owner_bytes"
        ]
    finally:
        absent.destroy()
        explicit_zero.destroy()


def test_streamed_absent_port_blocks_use_port_dimension_when_nt_differs() -> None:
    rng = np.random.default_rng(20261011)
    block = {
        "Vii": _matrix(rng, 2, 2, 5.0),
        "Vit": _matrix(rng, 2, 2),
        "Vti": _matrix(rng, 2, 2),
        "Vtt": _matrix(rng, 2, 2, 3.0),
        "Bi": _matrix(rng, 2, 3),
        "Di": _matrix(rng, 3, 2),
    }
    condensed = _FakeCondensed((block,), appended_rows=3)
    terms = {
        0: P6CellPortTerms(
            block["Bi"],
            block["Di"],
            np.arange(3, dtype=PETSc.IntType),
            Bt=None,
            Dt=None,
            H=None,
        )
    }
    hp = np.diag(np.asarray([1.2 + 0.1j, 1.4 - 0.2j, 1.7 + 0.3j]))
    cached = P6CellCondensedAction(condensed, H_p=hp, port_terms=terms)
    streamed = P6CellCondensedAction(
        condensed, H_p=hp, port_terms=terms, port_coupling_mode="streamed"
    )
    try:
        assert cached._cells[0].Dt is None
        assert streamed._cells[0].Dt is None
        assert len(streamed._cells[0].ports) == 3
        assert len(streamed._cells[0].original_trace) == 2
        reduced = rng.normal(size=cached.reduced_size) + 1j * rng.normal(
            size=cached.reduced_size
        )
        full_rhs = rng.normal(size=condensed.full_rows) + 1j * rng.normal(
            size=condensed.full_rows
        )
        port_rhs = rng.normal(size=condensed.appended_rows) + 1j * rng.normal(
            size=condensed.appended_rows
        )
        np.testing.assert_allclose(
            streamed.apply(reduced), cached.apply(reduced), rtol=2.0e-13, atol=2.0e-13
        )
        np.testing.assert_allclose(
            streamed.reduce_rhs(full_rhs, port_rhs=port_rhs),
            cached.reduce_rhs(full_rhs, port_rhs=port_rhs),
            rtol=2.0e-13,
            atol=2.0e-13,
        )
        streamed_recovery = streamed.recover_storage(reduced, full_rhs=full_rhs)
        cached_recovery = cached.recover_storage(reduced, full_rhs=full_rhs)
        np.testing.assert_allclose(
            streamed_recovery, cached_recovery, rtol=2.0e-13, atol=2.0e-13
        )
        np.testing.assert_allclose(
            streamed.apply_B_full(reduced[condensed.active_rows :]),
            cached.apply_B_full(reduced[condensed.active_rows :]),
            rtol=0.0,
            atol=0.0,
        )
        np.testing.assert_allclose(
            streamed.apply_D_full(streamed_recovery),
            cached.apply_D_full(cached_recovery),
            rtol=5.0e-15,
            atol=5.0e-15,
        )
    finally:
        streamed.destroy()
        cached.destroy()


def test_reduced_contribution_iterator_matches_cached_action() -> None:
    _condensed, _block, action = _problem()
    n = action.reduced_size
    assembled = np.zeros((n, n), dtype=np.complex128)
    gates = []
    for rows, columns, values, _label in action.iter_reduced_contributions(
        allocation_gate=lambda name, facts: gates.append((name, facts))
    ):
        assembled[np.ix_(rows, columns)] += values
    rhs = _matrix(np.random.default_rng(39191), n, 1)[:, 0]
    np.testing.assert_allclose(assembled @ rhs, action.apply(rhs), rtol=2e-12, atol=2e-12)
    assert len(gates) == 4
    assert all(facts["consumer_must_release_before_next"] for _name, facts in gates)


def test_reduced_contribution_iterator_builds_hhat_by_column_blocks(monkeypatch) -> None:
    _condensed, _block, action = _problem()
    n = action.reduced_size
    rhs = _matrix(np.random.default_rng(20261008), n, 1)[:, 0]
    expected = action.apply(rhs)
    full = np.zeros((n, n), dtype=np.complex128)
    for rows, columns, values, _label in action.iter_reduced_contributions(
        allocation_gate=lambda *_args: None
    ):
        full[np.ix_(rows, columns)] += values

    def reject_full_hhat_materialization():
        raise AssertionError("blocked Hhat path must not materialize the full Hhat")

    monkeypatch.setattr(action, "_materialize_Hhat", reject_full_hhat_materialization)
    blocked = np.zeros((n, n), dtype=np.complex128)
    labels = []
    for rows, columns, values, label in action.iter_reduced_contributions(
        allocation_gate=lambda *_args: None,
        hhat_block_columns=1,
    ):
        blocked[np.ix_(rows, columns)] += values
        labels.append(label)

    np.testing.assert_allclose(blocked, full, rtol=0.0, atol=1e-14)
    np.testing.assert_allclose(blocked @ rhs, expected, rtol=2e-12, atol=2e-12)
    assert labels[:2] == ["ports/Hhat/0:1", "ports/Hhat/1:2"]


def test_generated_reduced_contributions_stream_bounded_b_d_and_hhat_tiles() -> None:
    condensed, block, _seed = _problem()
    rng = np.random.default_rng(20261010)
    hp = _matrix(rng, 2, 2, diagonal=7.0)
    mode_keys = [(index, "top", index, 0, "s") for index in range(2)]
    original_hp = DenseOriginalPortBlock(
        hp, mode_keys, reason="two-mode generated q-tile oracle", max_bytes=64
    )
    cached = P6CellCondensedAction(
        condensed,
        H_p=None,
        port_terms={
            0: P6CellPortTerms(
                block["Bi"],
                block["Di"],
                np.asarray([0, 1], dtype=PETSc.IntType),
                Bt=block["Bt"],
                Dt=block["Dt"],
            )
        },
        port_block_layout=RESEARCH_PORT_LAYOUT,
        original_port_block=original_hp,
    )
    b_widths: list[int] = []
    d_shapes: list[tuple[int, int]] = []
    generated_gate_labels: list[str] = []

    def apply_b(alpha):
        return block["Bi"] @ alpha, block["Bt"] @ alpha

    def apply_d(xi, xt):
        return block["Di"] @ xi + block["Dt"] @ xt

    def apply_b_tile(ports, alpha):
        b_widths.append(int(alpha.shape[1]))
        return block["Bi"][:, ports] @ alpha, block["Bt"][:, ports] @ alpha

    def apply_d_tile(ports, xi, xt):
        d_shapes.append((len(ports), int(xi.shape[1])))
        return block["Di"][ports, :] @ xi + block["Dt"][ports, :] @ xt

    generated = build_p6_cell_condensed_action_from_generated(
        condensed,
        original_hp,
        {
            0: P6GeneratedCellPortAction(
                port_indices=np.asarray([0, 1], dtype=PETSc.IntType),
                apply_B=apply_b,
                apply_D=apply_d,
                callback_workspace_bytes=256,
                apply_B_tile=apply_b_tile,
                apply_D_tile=apply_d_tile,
            )
        },
    )
    try:
        cached_matrix = np.zeros((cached.reduced_size, cached.reduced_size), dtype=np.complex128)
        for rows, columns, values, _label in cached.iter_reduced_contributions(
            allocation_gate=lambda *_args: None,
            hhat_block_columns=1,
        ):
            cached_matrix[np.ix_(rows, columns)] += values
        generated_matrix = np.zeros_like(cached_matrix)
        labels = []

        def generated_gate(label, _facts):
            generated_gate_labels.append(label)

        for rows, columns, values, label in generated.iter_reduced_contributions(
            allocation_gate=generated_gate,
            hhat_block_columns=1,
        ):
            generated_matrix[np.ix_(rows, columns)] += values
            labels.append(label)

        np.testing.assert_allclose(generated_matrix, cached_matrix, rtol=3e-13, atol=3e-13)
        rhs = _matrix(np.random.default_rng(20261011), generated.reduced_size, 1)[:, 0]
        np.testing.assert_allclose(generated_matrix @ rhs, generated.apply(rhs), rtol=3e-13, atol=3e-13)
        assert "ports/Hhat/0:1" in labels
        assert "cell/C_hat/0/0:1" in labels
        assert "cell/-D_hat/0/0:1" in labels
        assert b_widths and max(b_widths) == 1
        assert d_shapes.count((2, 1)) == 2
        assert d_shapes.count((1, 2)) == 2
        identity_gate = "p6_reduced_contribution/cell/D_trace_identity/0"
        first_d_gate = "p6_reduced_contribution/cell/-D_hat/0/0:1"
        assert generated_gate_labels.index(identity_gate) < generated_gate_labels.index(first_d_gate)
    finally:
        generated.destroy()
        cached.destroy()


def test_global_direct_provider_streams_full_reduced_and_contribution_paths() -> None:
    condensed, block, prior = _problem()
    prior.destroy()
    mode_keys = [(index, "top", index, 0, "s") for index in range(2)]
    hp = np.asarray([[6.0, 0.2], [-0.1, 7.0]], dtype=np.complex128)
    original_hp = DenseOriginalPortBlock(
        hp, mode_keys, reason="two-mode global direct provider fixture", max_bytes=64
    )
    rows = np.asarray([2, 3], dtype=PETSc.IntType)
    b_expected = (
        np.asarray([0.5 + 0.2j, -0.1 + 0.4j], dtype=np.complex128),
        np.asarray([-0.3 + 0.1j, 0.8 - 0.2j], dtype=np.complex128),
    )
    d_expected = (
        np.asarray([0.2 - 0.3j, 0.6 + 0.1j], dtype=np.complex128),
        np.asarray([-0.4 + 0.2j, 0.3 + 0.5j], dtype=np.complex128),
    )
    value_refs: list[weakref.ReferenceType[np.ndarray]] = []
    source_closed: list[bool] = []

    def stream_modes():
        try:
            for port in range(2):
                b_values = b_expected[port].copy()
                d_values = d_expected[port].copy()
                value_refs.extend((weakref.ref(b_values), weakref.ref(d_values)))
                yield SimpleNamespace(
                    mode_key=mode_keys[port],
                    coupling_rows=rows,
                    coupling_values=b_values,
                    projection_rows=rows,
                    projection_values=d_values,
                )
        finally:
            source_closed.append(True)

    provider = P6GlobalDirectCarrierProvider(
        stream_modes, condensed=condensed, mode_count=2, source_label="test-stream"
    )
    other_condensed = _FakeCondensed((block,))
    mismatched_provider = P6GlobalDirectCarrierProvider(
        stream_modes, condensed=other_condensed, mode_count=2, source_label="wrong-owner"
    )
    with pytest.raises(ValueError, match="different condensed owner"):
        build_p6_cell_condensed_action_from_generated(
            condensed, original_hp, {}, global_direct_provider=mismatched_provider
        )
    action = build_p6_cell_condensed_action_from_generated(
        condensed, original_hp, {}, global_direct_provider=provider
    )
    try:
        alpha = np.asarray([1.2 - 0.3j, -0.4 + 0.8j], dtype=np.complex128)
        expected_b = np.zeros(condensed.full_rows, dtype=np.complex128)
        for port in range(2):
            expected_b[rows] += b_expected[port] * alpha[port]
        np.testing.assert_allclose(action.apply_B_full(alpha), expected_b, rtol=0.0, atol=0.0)

        field = np.asarray([0.1j, -0.2, 0.7 + 0.3j, -0.5j], dtype=np.complex128)
        expected_d = np.asarray(
            [np.dot(d_expected[port], field[rows]) for port in range(2)],
            dtype=np.complex128,
        )
        np.testing.assert_allclose(action.apply_D_full(field), expected_d, rtol=0.0, atol=0.0)

        with pytest.raises(ValueError, match="bounded Hhat port columns"):
            list(action.iter_reduced_contribution_layouts())
        with pytest.raises(ValueError, match="bounded Hhat port columns"):
            list(action.iter_reduced_contributions(allocation_gate=lambda *_args: None))
        layouts = list(action.iter_reduced_contribution_layouts(hhat_block_columns=1))
        assert any(label == "direct/C/provider/0" for _r, _c, label in layouts)
        assert any(label == "direct/-D/provider/1" for _r, _c, label in layouts)
        matrix = np.zeros((action.reduced_size, action.reduced_size), dtype=np.complex128)
        direct = np.zeros_like(matrix)
        for contribution_rows, contribution_columns, values, label in action.iter_reduced_contributions(
            allocation_gate=lambda *_args: None, hhat_block_columns=1
        ):
            matrix[np.ix_(contribution_rows, contribution_columns)] += values
            if label.startswith("direct/") and "/provider/" in label:
                direct[np.ix_(contribution_rows, contribution_columns)] += values
        expected_direct = np.zeros_like(matrix)
        for port in range(2):
            expected_direct[:2, 2 + port] = b_expected[port]
            expected_direct[2 + port, :2] = -d_expected[port]
        np.testing.assert_array_equal(direct, expected_direct)
        reduced = np.asarray([0.4, -0.7j, 0.2 + 0.3j, 0.5], dtype=np.complex128)
        np.testing.assert_allclose(matrix @ reduced, action.apply(reduced), rtol=2e-13, atol=2e-13)
        assert action.audit["generated_port_action_count"] == 0
        assert action.buffer_inventory["global_direct_provider_resident_value_bytes"] == 0
        assert action.buffer_inventory["global_direct_provider_expected_H_copy_bytes"] == 0
        assert action.buffer_inventory["global_direct_provider_mode_key_metadata_shallow_bytes"] > 0
        assert action.buffer_inventory["global_direct_provider_owned_backing_bytes"] >= action.buffer_inventory[
            "global_direct_provider_mode_key_metadata_shallow_bytes"
        ]
        assert "fixed H copy and mode-key metadata" in action.buffer_inventory[
            "global_direct_provider_bytes_scope"
        ]
        assert action.audit["global_direct_provider"]["second_mpc_application"] is False
        assert action.audit["global_direct_provider"]["iterator_sweeps_by_operation"] == {
            "apply_B_full": 1,
            "apply_D_full": 1,
            "reduced_layouts": 1,
            "reduced_contributions": 1,
            "reduced_apply": 1,
        }
        direct_tiles = list(provider.iter_reduced_direct_tiles())
        assert [port for port, _b, _d in direct_tiles] == [0, 1]
        for port, b_data, d_data in direct_tiles:
            assert b_data is not None and d_data is not None
            np.testing.assert_array_equal(b_data[1], b_expected[port])
            np.testing.assert_array_equal(d_data[1], d_expected[port])
            np.testing.assert_array_equal(b_data[2], [0, 1])
            np.testing.assert_array_equal(d_data[2], [0, 1])
        del direct_tiles, port, b_data, d_data
        gc.collect()
        assert action.audit["global_direct_provider"]["iterator_sweeps_by_operation"][
            "reduced_direct_tiles"
        ] == 1
        closed_before = len(source_closed)
        early = provider._iter_mode_data("early_close")
        borrowed = next(early)
        del borrowed
        early.close()
        assert len(source_closed) == closed_before + 1
        del layouts, matrix, direct
        gc.collect()
        assert value_refs and all(reference() is None for reference in value_refs)
    finally:
        action.destroy()


def test_global_direct_provider_inventory_counts_h_copy_and_mode_keys() -> None:
    condensed = SimpleNamespace(
        full_rows=32,
        appended_rows=1,
        trace_constraints=SimpleNamespace(original_to_active={}),
        cell_recovery_maps=(),
    )
    provider = P6GlobalDirectCarrierProvider(
        lambda: iter(()), condensed=condensed, mode_count=1, source_label="inventory-fixture"
    )
    original_h = DiagonalOriginalPortBlock(
        np.asarray([3.0 + 0.0j], dtype=np.complex128),
        [(0, "bottom", 1, 2, "s")],
    )
    provider.bind_original_port_block(original_h, mode_indices=(0,))
    audit = provider.audit
    assert audit["expected_H_values_backing_bytes"] == np.dtype(np.complex128).itemsize
    assert audit["expected_mode_key_metadata_shallow_bytes"] > 0
    assert audit["provider_owned_backing_bytes"] == (
        audit["interior_classifier_bytes"]
        + audit["expected_H_values_backing_bytes"]
        + audit["expected_mode_key_metadata_shallow_bytes"]
    )


@pytest.mark.parametrize("trace_term", ("Bt", "Dt"))
def test_global_direct_provider_rejects_overlapping_cached_trace_terms(trace_term: str) -> None:
    condensed, block, prior = _problem()
    prior.destroy()
    mode_keys = [(index, "top", index, 0, "s") for index in range(2)]
    rows = np.asarray([2, 3], dtype=PETSc.IntType)

    def stream_modes():
        for port in range(2):
            values = np.asarray([1.0 + port, 0.5j], dtype=np.complex128)
            yield SimpleNamespace(
                mode_key=mode_keys[port],
                coupling_rows=rows,
                coupling_values=values,
                projection_rows=rows,
                projection_values=values.copy(),
            )

    provider = P6GlobalDirectCarrierProvider(
        stream_modes,
        condensed=condensed,
        mode_count=2,
        interior_rows_are_managed=True,
    )
    trace_terms = {
        "Bt": np.zeros_like(block["Bt"]),
        "Dt": np.zeros_like(block["Dt"]),
    }
    trace_terms[trace_term][0, 0] = 1.0 + 0.25j
    terms = {
        0: P6CellPortTerms(
            block["Bi"],
            block["Di"],
            np.asarray([0, 1], dtype=PETSc.IntType),
            **trace_terms,
        )
    }
    original_hp = DenseOriginalPortBlock(
        block["H"], mode_keys, reason="overlapping provider trace fixture", max_bytes=64
    )

    with pytest.raises(
        ValueError,
        match=(
            "global direct provider owns all trace B rows"
            if trace_term == "Bt"
            else "global direct provider owns all trace D rows"
        ),
    ):
        build_p6_cell_condensed_action_from_generated(
            condensed,
            original_hp,
            {},
            port_terms=terms,
            global_direct_provider=provider,
        )


def test_global_direct_provider_rejects_same_ordinal_wrong_full_mode_key() -> None:
    condensed, block, prior = _problem()
    prior.destroy()
    rows = np.asarray([2, 3], dtype=PETSc.IntType)
    expected_keys = [(0, "top", 0, 0, "s"), (1, "top", 1, 0, "s")]

    def stream_modes():
        for port in range(2):
            # The ordinal is unchanged, but the physical side identity is wrong.
            emitted_key = (
                (port, "bottom", 0, 0, "s") if port == 0 else expected_keys[port]
            )
            values = np.asarray([0.25 + 0.5j, -0.3j], dtype=np.complex128)
            yield SimpleNamespace(
                mode_key=emitted_key,
                coupling_rows=rows,
                coupling_values=values,
                projection_rows=rows,
                projection_values=values.copy(),
            )

    provider = P6GlobalDirectCarrierProvider(
        stream_modes, condensed=condensed, mode_count=2, source_label="wrong-physical-key"
    )
    original_hp = DenseOriginalPortBlock(
        np.eye(2, dtype=np.complex128),
        expected_keys,
        reason="full ordered mode-key mismatch fixture",
        max_bytes=64,
    )
    action = build_p6_cell_condensed_action_from_generated(
        condensed, original_hp, {}, global_direct_provider=provider
    )
    try:
        with pytest.raises(ValueError, match="full mode key/order differs from original H_p at port 0"):
            action.apply_B_full(np.ones(2, dtype=np.complex128))
    finally:
        action.destroy()


def test_global_direct_provider_defers_interior_rows_only_to_existing_cell_terms() -> None:
    condensed, block, prior = _problem()
    prior.destroy()
    mode_keys = [(index, "top", index, 0, "s") for index in range(2)]
    rows = np.asarray([0, 1, 2, 3], dtype=PETSc.IntType)
    b_trace = np.asarray([[0.5, -0.2], [0.3j, 0.7]], dtype=np.complex128)
    d_trace = np.asarray([[0.1, -0.4j], [0.6, 0.2 + 0.3j]], dtype=np.complex128)

    def stream_modes():
        for port in range(2):
            yield SimpleNamespace(
                mode_key=mode_keys[port],
                coupling_rows=rows,
                coupling_values=np.concatenate((block["Bi"][:, port], b_trace[:, port])),
                projection_rows=rows,
                projection_values=np.concatenate((block["Di"][port, :], d_trace[port, :])),
            )

    original_hp = DenseOriginalPortBlock(
        block["H"], mode_keys, reason="interior/direct split fixture", max_bytes=64
    )
    unmanaged = P6GlobalDirectCarrierProvider(
        stream_modes, condensed=condensed, mode_count=2
    )
    unmanaged.bind_original_port_block(original_hp)
    with pytest.raises(ValueError, match="interior rows without local cell terms"):
        unmanaged.add_B_full(np.ones(2, dtype=np.complex128), np.zeros(4, dtype=np.complex128))

    partial_provider = P6GlobalDirectCarrierProvider(
        stream_modes,
        condensed=condensed,
        mode_count=2,
        interior_rows_are_managed=True,
    )
    partial_action = build_p6_cell_condensed_action_from_generated(
        condensed,
        original_hp,
        {},
        port_terms={
            0: P6CellPortTerms(
                block["Bi"][:, :1],
                block["Di"][:1, :],
                np.asarray([0], dtype=PETSc.IntType),
            )
        },
        global_direct_provider=partial_provider,
    )
    with pytest.raises(ValueError, match="mode 1.*cell 0"):
        partial_action.apply_B_full(np.ones(2, dtype=np.complex128))
    partial_action.destroy()

    provider = P6GlobalDirectCarrierProvider(
        stream_modes,
        condensed=condensed,
        mode_count=2,
        interior_rows_are_managed=True,
    )
    action = build_p6_cell_condensed_action_from_generated(
        condensed,
        original_hp,
        {},
        port_terms={
            0: P6CellPortTerms(
                block["Bi"],
                block["Di"],
                np.asarray([0, 1], dtype=PETSc.IntType),
            )
        },
        global_direct_provider=provider,
    )
    try:
        alpha = np.asarray([0.8 + 0.2j, -0.1 + 0.6j], dtype=np.complex128)
        expected_b = np.zeros(4, dtype=np.complex128)
        expected_b[:2] = block["Bi"] @ alpha
        expected_b[2:] = b_trace @ alpha
        np.testing.assert_allclose(action.apply_B_full(alpha), expected_b, rtol=0.0, atol=0.0)
        field = np.asarray([0.4, -0.3j, 0.2 + 0.1j, -0.5], dtype=np.complex128)
        expected_d = block["Di"] @ field[:2] + d_trace @ field[2:]
        np.testing.assert_allclose(action.apply_D_full(field), expected_d, rtol=0.0, atol=0.0)
        audit = action.audit["global_direct_provider"]
        assert audit["interior_rows_are_managed_by_local_terms"] is True
        assert audit["interior_rows_deferred_by_operation_and_side"]["apply_B_full/B"] == 4
        assert audit["interior_rows_deferred_by_operation_and_side"]["apply_D_full/D"] == 4
    finally:
        action.destroy()


def test_v16_bounded_q_route_matches_small_p6_action_fixture(monkeypatch) -> None:
    """Exercise the registered q route with the actual action class on a small algebra fixture."""
    def diagonal(values):
        return np.diag(np.asarray(values, dtype=np.complex128))

    block = {
        "Vii": diagonal([4.0, 5.0]),
        "Vit": diagonal([0.1, 0.2]),
        "Vti": diagonal([0.15, 0.25]),
        "Vtt": diagonal([2.0, 3.0]),
        "Bi": diagonal([0.3, 0.4]),
        "Bt": diagonal([0.2, 0.3]),
        "Di": diagonal([0.1, 0.2]),
        "Dt": diagonal([0.4, 0.5]),
        "H": diagonal([6.0, 7.0]),
    }
    condensed = _FakeCondensed((block,))
    terms = {
        0: P6CellPortTerms(
            block["Bi"],
            block["Di"],
            np.asarray([0, 1], dtype=PETSc.IntType),
            Bt=block["Bt"],
            Dt=block["Dt"],
            H=block["H"],
        )
    }
    action = P6CellCondensedAction(
        condensed, H_p=diagonal([8.0, 9.0]), port_terms=terms
    )

    class _Coordinates:
        maps = (
            sparse.csr_matrix(
                np.asarray(
                    [[1.0, 0.0], [0.0, 0.0], [0.0, 1.0], [0.0, 0.0]],
                    dtype=np.complex128,
                )
            ),
            sparse.csr_matrix(
                np.asarray(
                    [[0.0, 0.0], [1.0, 0.0], [0.0, 0.0], [0.0, 1.0]],
                    dtype=np.complex128,
                )
            ),
        )

        def q_map(self, branch, *, allocation_gate):
            allocation_gate("real_p6_fixture_q_map", {"branch": int(branch)})
            return self.maps[branch]

    coordinates = _Coordinates()
    context = SimpleNamespace(global_q_indices=(0, 2))
    native_blocks = {}
    for p in (0, 1):
        for q in (0, 1):
            q_basis = coordinates.maps[q].toarray()
            native_action = np.column_stack(
                [action.apply(q_basis[:, column]) for column in range(q_basis.shape[1])]
            )
            native_blocks[p, q] = coordinates.maps[p].conjugate().T @ native_action

    legacy, _legacy_audit = assemble_task40_v10_sector_blocks(
        action,
        coordinates,
        context,
        allocation_gate=lambda *_args: None,
        assembly_strategy=Q_ASSEMBLY_LEGACY,
        return_all_blocks=True,
    )
    comparison = compare_task40_v10_sector_assembly(
        action,
        coordinates,
        context,
        allocation_gate=lambda *_args: None,
        candidate_strategy=Q_ASSEMBLY_BOUNDED_V16,
    )
    assert comparison["schema"] == "task40extra.review_v16_q_assembly_pair.v1"
    assert comparison["candidate_strategy"] == Q_ASSEMBLY_BOUNDED_V16
    assert comparison["numerically_equivalent_at_original_operator_gate"]
    assert comparison["all_four_blocks_independently_compared"]

    def reject_full_hhat_materialization():
        raise AssertionError("V16 q route must use streamed Hhat contribution blocks")

    monkeypatch.setattr(action, "_materialize_Hhat", reject_full_hhat_materialization)
    bounded, audit = assemble_task40_v10_sector_blocks(
        action,
        coordinates,
        context,
        allocation_gate=lambda *_args: None,
        assembly_strategy=Q_ASSEMBLY_BOUNDED_V16,
        return_all_blocks=True,
    )

    assert set(bounded) == {(0, 0), (0, 1), (1, 0), (1, 1)}
    assert audit["assembly_strategy"] == Q_ASSEMBLY_BOUNDED_V16
    assert audit["numeric_contribution_count"] > 0
    assert audit["staging_peak_bytes_total_all_blocks"] <= audit[
        "staging_budget_bytes_total_all_q_blocks"
    ]
    for key in bounded:
        np.testing.assert_allclose(
            bounded[key].toarray(), legacy[key].toarray(), rtol=0.0, atol=1e-14
        )
        np.testing.assert_allclose(
            bounded[key].toarray(), native_blocks[key], rtol=2e-12, atol=2e-12
        )
    assert audit["off_diagonal_relative"] == {
        "q0_q1_relative": 0.0,
        "q1_q0_relative": 0.0,
    }


def test_v13_augmented_residual_sign_and_original_h_scale_match_small_p6_action():
    condensed, block, prior_action = _problem()
    prior_action.destroy()
    h = np.asarray([1.7, 0.8], dtype=np.float64)
    terms = {
        0: P6CellPortTerms(
            block["Bi"],
            block["Di"],
            np.asarray([0, 1], dtype=PETSc.IntType),
            Bt=block["Bt"],
            Dt=block["Dt"],
        )
    }
    action = P6CellCondensedAction(
        condensed, H_p=np.diag(h).astype(np.complex128), port_terms=terms
    )
    try:
        volume = np.block(
            [[block["Vii"], block["Vit"]], [block["Vti"], block["Vtt"]]]
        )
        coupling = np.vstack((block["Bi"], block["Bt"]))
        dual = np.hstack((block["Di"], block["Dt"]))
        assert action.operator_recipe["sign_convention"] == "augmented=[[V,B],[-D,Hp]]"
        assert not np.allclose(dual, coupling.conj().T)
        np.testing.assert_array_equal(np.diag(action.H_p).real, h)

        rng = np.random.default_rng(401031)
        finite_element = (
            rng.standard_normal(4) + 1j * rng.standard_normal(4)
        ).astype(np.complex128)
        alpha = (
            rng.standard_normal(2) + 1j * rng.standard_normal(2)
        ).astype(np.complex128)
        fe_rhs = (
            rng.standard_normal(4) + 1j * rng.standard_normal(4)
        ).astype(np.complex128)
        port_rhs = (
            rng.standard_normal(2) + 1j * rng.standard_normal(2)
        ).astype(np.complex128)
        recovered = action.original_hp_solve(dual @ finite_element)
        offset = augmented_port_state_offset(alpha, recovered)
        native_physical_action = volume @ finite_element + coupling @ recovered
        dual_port_action = coupling @ offset
        original_fe_scale = stable_euclidean_norm(fe_rhs) + stable_euclidean_norm(
            coupling @ (port_rhs / h)
        )

        result = evaluate_complete_augmented_residual(
            physical_action_storage=native_physical_action,
            dual_coupling_storage=dual_port_action,
            finite_element_rhs=fe_rhs,
            port_amplitudes=alpha,
            recovered_port_amplitudes=recovered,
            port_state_offset=offset,
            port_rhs=port_rhs,
            h=h,
            original_fe_equation_scale=original_fe_scale,
            independent_rows=np.arange(4, dtype=np.int64),
        )

        expected_fe_residual = fe_rhs - (volume @ finite_element + coupling @ alpha)
        expected_port_residual = port_rhs - (
            -dual @ finite_element + np.diag(h) @ alpha
        )
        np.testing.assert_allclose(
            result["finite_element_residual"], expected_fe_residual,
            rtol=3e-13, atol=3e-13,
        )
        np.testing.assert_allclose(
            result["port_residual"], expected_port_residual,
            rtol=3e-13, atol=3e-13,
        )
        assert result["original_fe_equation_scale"] == pytest.approx(original_fe_scale)
        assert result["complete_augmented_fe_equation_relative"] == pytest.approx(
            stable_euclidean_norm(expected_fe_residual) / original_fe_scale
        )
    finally:
        action.destroy()
        condensed.destroy()


def test_nonhermitian_local_condensation_and_recovery_match_dense_blocks() -> None:
    rng = np.random.default_rng(19)
    ni, nt, np_ = 3, 2, 2
    blocks = {
        name: _matrix(rng, rows, columns, diagonal)
        for name, rows, columns, diagonal in (
            ("Vii", ni, ni, 5.0), ("Vit", ni, nt, 0.0), ("Vti", nt, ni, 0.0),
            ("Vtt", nt, nt, 3.0), ("Bi", ni, np_, 0.0), ("Bt", nt, np_, 0.0),
            ("Di", np_, ni, 0.0), ("Dt", np_, nt, 0.0), ("H", np_, np_, 4.0),
        )
    }
    cell = condense_physical_cell_blocks(*(blocks[name] for name in (
        "Vii", "Vit", "Vti", "Vtt", "Bi", "Bt", "Di", "Dt", "H"
    )))
    inverse = np.linalg.inv(blocks["Vii"])
    np.testing.assert_allclose(cell.S_V, blocks["Vtt"] - blocks["Vti"] @ inverse @ blocks["Vit"])
    np.testing.assert_allclose(cell.Bhat, blocks["Bt"] - blocks["Vti"] @ inverse @ blocks["Bi"])
    np.testing.assert_allclose(cell.Dhat, blocks["Dt"] - blocks["Di"] @ inverse @ blocks["Vit"])
    np.testing.assert_allclose(cell.Hhat, blocks["H"] + blocks["Di"] @ inverse @ blocks["Bi"])
    trace = _matrix(rng, nt, 1)[:, 0]
    alpha = _matrix(rng, np_, 1)[:, 0]
    rhs_i = _matrix(rng, ni, 1)[:, 0]
    expected = inverse @ (rhs_i - blocks["Vit"] @ trace - blocks["Bi"] @ alpha)
    np.testing.assert_allclose(cell.recover(trace, alpha, rhs_i), expected, rtol=2e-12, atol=2e-12)
    assert not np.allclose(blocks["Di"], blocks["Bi"].conj().T)


def test_action_rhs_recovery_and_native_residual_identity_match_oracle() -> None:
    _condensed, block, action = _problem()
    hp = action.H_p
    inverse = np.linalg.inv(block["Vii"])
    sv = block["Vtt"] - block["Vti"] @ inverse @ block["Vit"]
    bhat = block["Bt"] - block["Vti"] @ inverse @ block["Bi"]
    dhat = block["Dt"] - block["Di"] @ inverse @ block["Vit"]
    hhat = hp + block["Di"] @ inverse @ block["Bi"]
    reduced = np.block([[sv, bhat], [-dhat, hhat]])
    rng = np.random.default_rng(77)
    y = _matrix(rng, 4, 1)[:, 0]
    np.testing.assert_allclose(action.apply(y), reduced @ y, rtol=2e-12, atol=2e-12)
    np.testing.assert_allclose(action.apply(y + 0.25j * y), action.apply(y) + 0.25j * action.apply(y))
    b = _matrix(rng, 4, 1)[:, 0]
    rp = _matrix(rng, 2, 1)[:, 0]
    expected_rhs = np.r_[b[2:] - block["Vti"] @ inverse @ b[:2], rp + block["Di"] @ inverse @ b[:2]]
    np.testing.assert_allclose(action.reduce_rhs(b, port_rhs=rp), expected_rhs, rtol=2e-12, atol=2e-12)
    np.testing.assert_allclose(
        action.recover_storage(y, full_rhs=b)[:2],
        inverse @ b[:2] - inverse @ block["Vit"] @ y[:2] - inverse @ block["Bi"] @ y[2:],
        rtol=2e-12,
        atol=2e-12,
    )

    V = np.block([[block["Vii"], block["Vit"]], [block["Vti"], block["Vtt"]]])
    B = np.vstack([block["Bi"], block["Bt"]])
    D = np.hstack([block["Di"], block["Dt"]])
    x = _matrix(rng, 4, 1)[:, 0]
    alpha = y[2:]
    rhs = _matrix(rng, 4, 1)[:, 0]
    top_error = rhs - V @ x - B @ alpha
    port_error = D @ x - hp @ alpha
    native = rhs - (V + B @ np.linalg.solve(hp, D)) @ x
    np.testing.assert_allclose(
        native_residual_from_augmented(action, top_error, port_error),
        native,
        rtol=2e-12,
        atol=2e-12,
    )
    evaluated = action.evaluate_native_residual(
        y,
        b,
        lambda value: (V + B @ np.linalg.solve(hp, D)) @ value,
    )
    assert evaluated["strict_zero_slave_storage"] is True
    assert evaluated["internal_residual_relative"] <= 2e-12
    np.testing.assert_allclose(
        evaluated["native_residual"],
        b - (V + B @ np.linalg.solve(hp, D)) @ evaluated["storage_solution"],
        rtol=2e-12,
        atol=2e-12,
    )
    np.testing.assert_allclose(
        evaluated["native_identity_difference"],
        0.0,
        rtol=0.0,
        atol=3e-12,
    )
    reduced_rhs = action.reduce_rhs(b)
    supplied_residual = reduced_rhs - action.apply(y)
    apply_count_before = action.audit["apply_count"]
    supplied = action.evaluate_native_residual(
        y,
        b,
        lambda value: (V + B @ np.linalg.solve(hp, D)) @ value,
        reduced_residual=supplied_residual,
    )
    assert supplied["reduced_residual_supplied"] is True
    assert action.audit["apply_count"] == apply_count_before
    for key in (
        "native_rhs_operation_scale",
        "native_identity_operation_scale",
        "port_operation_scale",
        "internal_operation_scale",
        "schur_operation_scale",
        "schur_port_identity_operation_scale",
    ):
        assert supplied[key] >= 0.0
    assert action.audit["global_s6_allocated"] is False
    assert action.audit["global_a6_allocated"] is False


def test_retained_bal_h_bridge_uses_original_hp_and_one_bal_h_call() -> None:
    _condensed, block, action = _problem()
    hp = action.H_p
    V = np.block([[block["Vii"], block["Vit"]], [block["Vti"], block["Vtt"]]])
    B = np.vstack([block["Bi"], block["Bt"]])
    D = np.hstack([block["Di"], block["Dt"]])
    a6 = V + B @ np.linalg.solve(hp, D)
    sv = block["Vtt"] - block["Vti"] @ np.linalg.solve(block["Vii"], block["Vit"])
    bhat = block["Bt"] - block["Vti"] @ np.linalg.solve(block["Vii"], block["Bi"])
    dhat = block["Dt"] - block["Di"] @ np.linalg.solve(block["Vii"], block["Vit"])
    reduced = np.block([[sv, bhat], [-dhat, action.Hhat]])
    bridge = P6RetainedBALHBridge(action, lambda rhs: np.linalg.solve(a6, rhs))
    rhs = np.asarray([1.0 + 0.2j, -0.3 + 0.7j, 0.4 - 0.5j, -0.8 + 0.1j])
    rhs_before = rhs.copy()
    observed = bridge.apply(rhs)
    np.testing.assert_allclose(observed, np.linalg.solve(reduced, rhs), rtol=2e-11, atol=2e-11)
    assert bridge.apply_count == bridge.bal_h_count == 1
    assert action.hp_solve_count == 2
    assert not np.allclose(action.Hhat, action.H_p)
    np.testing.assert_array_equal(rhs, rhs_before)

    second = np.asarray([-0.2 + 0.4j, 0.9 - 0.1j, -0.7 - 0.6j, 0.3 + 0.8j])
    second_before = second.copy()
    repeated = bridge.apply(rhs)
    combined = bridge.apply(rhs + second)
    np.testing.assert_allclose(repeated, observed, rtol=0.0, atol=0.0)
    np.testing.assert_allclose(
        combined,
        observed + bridge.apply(second),
        rtol=2e-11,
        atol=2e-11,
    )
    np.testing.assert_allclose(
        bridge.apply((0.37 - 0.22j) * rhs),
        (0.37 - 0.22j) * observed,
        rtol=2e-11,
        atol=2e-11,
    )
    np.testing.assert_array_equal(rhs, rhs_before)
    np.testing.assert_array_equal(second, second_before)

    bal_h_before = bridge.bal_h_count
    zero = bridge.apply(np.zeros_like(rhs))
    np.testing.assert_array_equal(zero, np.zeros_like(rhs))
    assert bridge.apply_count == 6
    assert bridge.bal_h_count == bal_h_before


def test_direct_trace_carrier_and_mpc_slave_are_fail_closed() -> None:
    condensed, block, _action = _problem()
    _action.destroy()

    class Entry:
        def __init__(self, port: int) -> None:
            self.normalization_h = 2.0 + 0.5j + port
            self.coupling_rows = np.asarray([0, 2] if port == 0 else [1, 3], dtype=np.int64)
            self.coupling_values = np.asarray([1.0 + 0.1j, 0.4 - 0.2j] if port == 0 else [0.3 + 0.4j, -0.1 + 0.2j])
            self.projection_rows = np.asarray([1, 3] if port == 0 else [0, 2], dtype=np.int64)
            self.projection_values = np.asarray([-0.2 + 0.3j, 0.6 + 0.1j] if port == 0 else [0.7 - 0.2j, 0.2 + 0.3j])

    carrier = SimpleNamespace(entries=(Entry(0), Entry(1)))
    carrier_before = tuple(
        tuple(
            np.asarray(getattr(entry, name)).copy()
            for name in (
                "coupling_rows",
                "coupling_values",
                "projection_rows",
                "projection_values",
            )
        )
        for entry in carrier.entries
    )
    carrier_action = build_p6_cell_condensed_action_from_carrier(condensed, carrier)
    owned_action = build_p6_cell_condensed_action_from_carrier(
        condensed, carrier, bounded_direct_term_build=True
    )
    assert carrier_action.audit["direct_trace_B_entry_count"] == 2
    assert carrier_action.audit["direct_trace_D_entry_count"] == 2
    assert owned_action.audit["direct_term_construction"]["strategy"] == (
        "bounded_reusable_chunk_owned_outputs"
    )
    assert owned_action.audit["direct_term_construction"][
        "unique_output_backing_bytes"
    ] <= 2 * sum(
        np.asarray(getattr(entry, rows_name)).size
        * (np.dtype(PETSc.IntType).itemsize + np.dtype(np.complex128).itemsize)
        for entry in carrier.entries
        for rows_name in ("coupling_rows", "projection_rows")
    )
    for name in (
        "_direct_B_original",
        "_direct_D_original",
        "_direct_B_active",
        "_direct_D_active",
    ):
        legacy_map = getattr(carrier_action, name)
        owned_map = getattr(owned_action, name)
        assert legacy_map.keys() == owned_map.keys()
        for port in legacy_map:
            for legacy_array, owned_array in zip(
                legacy_map[port], owned_map[port], strict=True
            ):
                np.testing.assert_array_equal(legacy_array, owned_array)

    V = np.block([[block["Vii"], block["Vit"]], [block["Vti"], block["Vtt"]]])
    B = np.zeros((4, 2), dtype=np.complex128)
    D = np.zeros((2, 4), dtype=np.complex128)
    hp = np.zeros((2, 2), dtype=np.complex128)
    for port, entry in enumerate(carrier.entries):
        np.add.at(B[:, port], entry.coupling_rows, entry.coupling_values)
        np.add.at(D[port], entry.projection_rows, entry.projection_values)
        hp[port, port] = entry.normalization_h
    full_augmented = np.block([[V, B], [-D, hp]])
    interior = np.asarray([0, 1])
    retained = np.asarray([2, 3, 4, 5])
    expected_action = full_augmented[np.ix_(retained, retained)] - (
        full_augmented[np.ix_(retained, interior)]
        @ np.linalg.solve(
            full_augmented[np.ix_(interior, interior)],
            full_augmented[np.ix_(interior, retained)],
        )
    )
    rng = np.random.default_rng(20261002)
    reduced = _matrix(rng, 4, 1)[:, 0]
    full_rhs = _matrix(rng, 4, 1)[:, 0]
    port_rhs = _matrix(rng, 2, 1)[:, 0]
    expected_rhs = np.r_[full_rhs[2:], port_rhs] - (
        full_augmented[np.ix_(retained, interior)]
        @ np.linalg.solve(
            full_augmented[np.ix_(interior, interior)], full_rhs[:2]
        )
    )
    storage_expected = np.r_[
        np.linalg.solve(
            block["Vii"],
            full_rhs[:2] - block["Vit"] @ reduced[:2] - B[:2] @ reduced[2:],
        ),
        reduced[:2],
    ]
    for action in (carrier_action, owned_action):
        np.testing.assert_allclose(action.apply(reduced), expected_action @ reduced)
        np.testing.assert_allclose(action.reduce_rhs(full_rhs, port_rhs=port_rhs), expected_rhs)
        np.testing.assert_allclose(action.recover_storage(reduced, full_rhs=full_rhs), storage_expected)
        np.testing.assert_allclose(action.apply_B_full(reduced[2:]), B @ reduced[2:])
        np.testing.assert_allclose(action.apply_D_full(storage_expected), D @ storage_expected)
    for legacy_value, owned_value in zip(
        carrier_action.apply(reduced), owned_action.apply(reduced), strict=True
    ):
        assert legacy_value == pytest.approx(owned_value)
    for entry, before in zip(carrier.entries, carrier_before, strict=True):
        for name, value in zip(
            ("coupling_rows", "coupling_values", "projection_rows", "projection_values"),
            before,
            strict=True,
        ):
            np.testing.assert_array_equal(getattr(entry, name), value)
    assert np.all(np.isfinite(carrier_action.Hhat))
    carrier_action.destroy()
    owned_action.destroy()

    slave_constraints = SimpleNamespace(
        owned_active_original_dofs=np.asarray([2], dtype=PETSc.IntType),
        original_to_active={2: 0},
        expansion_by_original={
            2: (np.asarray([0], dtype=PETSc.IntType), np.asarray([1.0 + 0j])),
            3: (np.asarray([0], dtype=PETSc.IntType), np.asarray([0.5 + 0.2j])),
        },
    )
    condensed.trace_constraints = slave_constraints
    for bounded in (False, True):
        with pytest.raises(ValueError, match="MPC slave"):
            build_p6_cell_condensed_action_from_carrier(
                condensed, carrier, bounded_direct_term_build=bounded
            )

    condensed, _block, _action = _problem()
    _action.destroy()
    unknown_entry = Entry(0)
    unknown_entry.coupling_rows = np.asarray([99], dtype=np.int64)
    unknown_entry.coupling_values = np.asarray([0.3 + 0.4j])
    unknown_carrier = SimpleNamespace(entries=(unknown_entry, Entry(1)))
    for bounded in (False, True):
        with pytest.raises(ValueError, match="unknown trace row"):
            build_p6_cell_condensed_action_from_carrier(
                condensed, unknown_carrier, bounded_direct_term_build=bounded
            )

    nan_entry = Entry(0)
    nan_entry.projection_values[0] = np.nan + 0j
    nan_carrier = SimpleNamespace(entries=(nan_entry, Entry(1)))
    with pytest.raises(ValueError, match="non-finite"):
        build_p6_cell_condensed_action_from_carrier(
            condensed, nan_carrier, bounded_direct_term_build=True
        )


def test_bounded_direct_carrier_handles_chunk_boundary_and_task40_local_dimensions() -> None:
    interior_rows, trace_rows, port_rows = 450, 432, 340
    trace = np.arange(interior_rows, interior_rows + trace_rows, dtype=PETSc.IntType)
    class_key = ("task40-450-432",)
    condensed = SimpleNamespace(
        matrix=None,
        active_rows=trace_rows,
        appended_rows=port_rows,
        full_rows=interior_rows + trace_rows,
        owned_active_rows=trace_rows,
        owned_appended_rows=port_rows,
        comm=MPI.COMM_SELF,
        owned_trace_original_dofs=trace.copy(),
        trace_constraints=SimpleNamespace(
            owned_active_original_dofs=trace.copy(),
            original_to_active={int(row): i for i, row in enumerate(trace)},
            expansion_by_original={
                int(row): (
                    np.asarray([i], dtype=PETSc.IntType),
                    np.asarray([1.0 + 0.0j], dtype=np.complex128),
                )
                for i, row in enumerate(trace)
            },
        ),
        cell_recovery_maps=(
            CellRecoveryMap(
                interior_original_dofs=np.arange(interior_rows, dtype=PETSc.IntType),
                trace_original_dofs=trace.copy(),
                class_key=class_key,
            ),
        ),
        interior_lu_by_class={class_key: lu_factor(np.eye(interior_rows, dtype=np.complex128))},
        interior_from_trace_by_class={
            class_key: np.zeros((interior_rows, trace_rows), dtype=np.complex128)
        },
        trace_from_interior_rhs_by_class={
            class_key: np.zeros((trace_rows, interior_rows), dtype=np.complex128)
        },
        retained_local_schur_by_class={
            class_key: np.eye(trace_rows, dtype=np.complex128)
        },
        build_audit={},
    )

    class Entry:
        def __init__(self, port: int) -> None:
            self.normalization_h = 1.5 + 0.001j * port
            self.coupling_rows = np.asarray(
                [port % interior_rows, interior_rows + port % trace_rows],
                dtype=PETSc.IntType,
            )
            self.coupling_values = np.asarray(
                [0.2 + 0.01j * port, -0.1 + 0.02j * port], dtype=np.complex128
            )
            self.projection_rows = np.asarray(
                [(port + 1) % interior_rows, interior_rows + port % trace_rows],
                dtype=PETSc.IntType,
            )
            self.projection_values = np.asarray(
                [0.03 - 0.001j * port, 0.04 + 0.002j * port], dtype=np.complex128
            )

    carrier = SimpleNamespace(entries=tuple(Entry(port) for port in range(port_rows)))
    action = build_p6_cell_condensed_action_from_carrier(
        condensed,
        carrier,
        bounded_direct_term_build=True,
        port_coupling_mode="streamed",
    )
    try:
        assert action.audit["active_trace_rows"] == 432
        assert action.audit["appended_port_rows"] == 340
        assert action.audit["direct_term_construction"]["chunk_entries"] == 32 * 1024
        assert action.audit["direct_term_construction"]["unique_output_backing_bytes"] < 2 * (
            4 * port_rows * (np.dtype(PETSc.IntType).itemsize + np.dtype(np.complex128).itemsize)
        )
    finally:
        action.destroy()


def test_bounded_direct_carrier_slices_across_32768_entry_chunk_boundary() -> None:
    condensed, _block, base_action = _problem()
    base_action.destroy()

    class LongEntry:
        normalization_h = 2.0 + 0.1j
        coupling_rows = np.resize(
            np.asarray([2, 3], dtype=PETSc.IntType), 32 * 1024 + 1
        )
        coupling_values = (
            np.arange(32 * 1024 + 1, dtype=np.float64) * (1.0 + 0.25j)
        ).astype(np.complex128)
        projection_rows = np.empty(0, dtype=PETSc.IntType)
        projection_values = np.empty(0, dtype=np.complex128)

    class EmptyEntry:
        normalization_h = 3.0 - 0.2j
        coupling_rows = np.empty(0, dtype=PETSc.IntType)
        coupling_values = np.empty(0, dtype=np.complex128)
        projection_rows = np.empty(0, dtype=PETSc.IntType)
        projection_values = np.empty(0, dtype=np.complex128)

    carrier = SimpleNamespace(entries=(LongEntry(), EmptyEntry()))
    original_rows = carrier.entries[0].coupling_rows.copy()
    original_values = carrier.entries[0].coupling_values.copy()
    action = build_p6_cell_condensed_action_from_carrier(
        condensed, carrier, bounded_direct_term_build=True
    )
    try:
        rows, values = action._direct_B_original[0]
        np.testing.assert_array_equal(rows, original_rows)
        np.testing.assert_array_equal(values, original_values)
        np.testing.assert_array_equal(carrier.entries[0].coupling_rows, original_rows)
        np.testing.assert_array_equal(carrier.entries[0].coupling_values, original_values)
        assert action.audit["direct_term_construction"]["chunk_entries"] == 32 * 1024
        assert action.audit["direct_term_construction"][
            "unique_output_backing_bytes"
        ] == 2 * (32 * 1024 + 1) * (
            np.dtype(PETSc.IntType).itemsize + np.dtype(np.complex128).itemsize
        )
    finally:
        action.destroy()


def test_action_cleanup_releases_shell_resources_and_rejects_reuse() -> None:
    _condensed, _block, action = _problem()
    matrix = action.create_matrix()
    source = matrix.createVecRight()
    target = matrix.createVecLeft()
    source.set(1.0)
    matrix.mult(source, target)
    assert action.audit["apply_count"] == 1
    action.destroy()
    source.destroy()
    target.destroy()
    with pytest.raises(RuntimeError, match="destroyed"):
        action.apply(np.ones(4, dtype=np.complex128))


def test_action_owns_mutated_hp_and_destroys_vec_result_on_mult_failure() -> None:
    condensed, block, base_action = _problem()
    base_action.destroy()
    rng = np.random.default_rng(404)
    hp = _matrix(rng, 2, 2, 7.0)
    hp_before = hp.copy()
    action = P6CellCondensedAction(
        condensed,
        H_p=hp,
        port_terms={
            0: P6CellPortTerms(
                block["Bi"], block["Di"], np.asarray([0, 1], dtype=PETSc.IntType),
                Bt=block["Bt"], Dt=block["Dt"], H=_matrix(rng, 2, 2, 0.0),
            )
        },
    )
    try:
        np.testing.assert_array_equal(hp, hp_before)
        source = action.create_reduced_rhs_vector()
        source.set(1.0)
        try:
            def fail(_matrix: PETSc.Mat | None, _source: PETSc.Vec, _target: PETSc.Vec) -> None:
                raise RuntimeError("intentional MatShell failure")

            action.mult = fail  # type: ignore[method-assign]
            with pytest.raises(RuntimeError, match="intentional MatShell failure"):
                action.apply(source)
        finally:
            source.destroy()
    finally:
        action.destroy()


def test_noncommuting_sum_adjoint_bilinear_repeat_and_input_immutability() -> None:
    rng = np.random.default_rng(3920)
    fields = []
    for seed in (1, 2):
        local = np.random.default_rng(seed)
        fields.append(
            {
                name: _matrix(local, rows, columns, diagonal)
                for name, rows, columns, diagonal in (
                    ("Vii", 2, 2, 5.0), ("Vit", 2, 2, 0.0),
                    ("Vti", 2, 2, 0.0), ("Vtt", 2, 2, 3.0),
                    ("Bi", 2, 2, 0.0), ("Bt", 2, 2, 0.0),
                    ("Di", 2, 2, 0.0), ("Dt", 2, 2, 0.0),
                    ("H", 2, 2, 4.0),
                )
            }
        )
    condensed_cells = [
        condense_physical_cell_blocks(
            *(field[name] for name in (
                "Vii", "Vit", "Vti", "Vtt", "Bi", "Bt", "Di", "Dt", "H"
            ))
        )
        for field in fields
    ]
    combined = {
        name: fields[0][name] + fields[1][name]
        for name in fields[0]
    }
    combined_cell = condense_physical_cell_blocks(
        *(combined[name] for name in (
            "Vii", "Vit", "Vti", "Vtt", "Bi", "Bt", "Di", "Dt", "H"
        ))
    )
    assert not np.allclose(
        combined_cell.S_V,
        condensed_cells[0].S_V + condensed_cells[1].S_V,
    )

    _condensed, block, action = _problem()
    hp = action.H_p
    inverse = np.linalg.inv(block["Vii"])
    reduced = np.block([
        [block["Vtt"] - block["Vti"] @ inverse @ block["Vit"],
         block["Bt"] - block["Vti"] @ inverse @ block["Bi"]],
        [-(block["Dt"] - block["Di"] @ inverse @ block["Vit"]),
         hp + block["Di"] @ inverse @ block["Bi"]],
    ])
    x = _matrix(rng, 4, 1)[:, 0]
    y = _matrix(rng, 4, 1)[:, 0]
    y_before = y.copy()
    inventory_before = dict(action.buffer_inventory)
    observed = action.apply(y)
    repeated = action.apply(y)
    np.testing.assert_array_equal(y, y_before)
    np.testing.assert_allclose(observed, repeated, rtol=0.0, atol=0.0)
    np.testing.assert_allclose(
        np.vdot(x, observed),
        np.vdot(reduced.conj().T @ x, y),
        rtol=2e-12,
        atol=2e-12,
    )
    assert dict(action.buffer_inventory) == inventory_before
    with pytest.raises(ValueError, match="expected"):
        action.apply(np.ones(3, dtype=np.complex128))
    action.destroy()


def test_fixed_p64_galerkin_then_condense_does_not_equal_trace_condense() -> None:
    """Keep the two fine internal DoFs needed to expose non-commutation.

    ``A4=P64^H A6 P64`` is constructed exactly.  The comparison then uses
    the scalar coarse trace Schur complement versus the fine two-internal-DoF
    Schur complement restricted by the trace block of ``P64``.
    """

    A6 = np.asarray(
        [
            [4.0 + 0.2j, 0.7 - 0.1j, 1.2 + 0.3j],
            [-0.4 + 0.5j, 3.3 - 0.2j, -0.8 + 0.4j],
            [0.6 - 0.7j, 1.1 + 0.2j, 2.4 + 0.6j],
        ],
        dtype=np.complex128,
    )
    P64 = np.asarray(
        [
            [1.0 + 0.1j, 0.0 + 0.0j],
            [0.25 - 0.2j, 0.0 + 0.0j],
            [0.0 + 0.0j, 1.0 + 0.0j],
        ],
        dtype=np.complex128,
    )
    A4 = P64.conj().T @ A6 @ P64
    np.testing.assert_allclose(
        A4,
        np.asarray(
            [
                [4.31225 + 0.026j, 0.95 + 0.12j],
                [0.985 - 0.81j, 2.4 + 0.6j],
            ],
            dtype=np.complex128,
        ),
        rtol=0.0,
        atol=2e-15,
    )

    fine_internal = slice(0, 2)
    fine_trace = slice(2, 3)
    coarse_internal = slice(0, 1)
    coarse_trace = slice(1, 2)
    S6 = A6[fine_trace, fine_trace] - (
        A6[fine_trace, fine_internal]
        @ np.linalg.solve(A6[fine_internal, fine_internal], A6[fine_internal, fine_trace])
    )
    S4 = A4[coarse_trace, coarse_trace] - (
        A4[coarse_trace, coarse_internal]
        @ np.linalg.solve(
            A4[coarse_internal, coarse_internal], A4[coarse_internal, coarse_trace]
        )
    )
    P_trace = P64[fine_trace, coarse_trace]
    restricted_fine_schur = P_trace.conj().T @ S6 @ P_trace

    assert abs(complex(S4[0, 0] - restricted_fine_schur[0, 0])) > 1.0e-3
    np.testing.assert_allclose(
        S4,
        np.asarray([[2.16138079 + 0.75247356j]], dtype=np.complex128),
        rtol=2e-8,
        atol=2e-8,
    )
    np.testing.assert_allclose(
        restricted_fine_schur,
        np.asarray([[2.40110146 + 0.77955336j]], dtype=np.complex128),
        rtol=2e-8,
        atol=2e-8,
    )


@pytest.mark.parametrize(
    "port_count, port_coupling_mode",
    ((2, "cached"), (80, "cached"), (80, "streamed")),
)
def test_real_ffcx_mpc_action_only_matches_augmented_schur_and_nonzero_rhs(
    port_count: int, port_coupling_mode: str
) -> None:
    """Exercise cached and streamed actions on a real complex-MPC FE fixture."""

    import dolfinx_mpc
    import ufl
    from basix.ufl import element
    from dolfinx import fem, mesh
    from dolfinx import default_real_type
    from dolfinx.fem import petsc as fem_petsc
    from scipy.sparse import csr_matrix

    from src.solvers.hcurl_assembly_time_condensation import (
        build_unconstrained_assembly_time_condensation,
    )
    from src.solvers.hcurl_cell_static_condensation import owned_hcurl_cell_interior_dofs

    domain = mesh.create_unit_cube(
        MPI.COMM_SELF, 2, 1, 1, cell_type=mesh.CellType.hexahedron
    )
    tags = mesh.meshtags(
        domain,
        3,
        np.asarray([0, 1], dtype=np.int32),
        np.asarray([1, 2], dtype=np.int32),
    )
    space = fem.functionspace(
        domain,
        element("N1curl", domain.basix_cell(), 2, dtype=default_real_type),
    )
    u, v = ufl.TrialFunction(space), ufl.TestFunction(space)
    dx = ufl.Measure("dx", domain=domain, subdomain_data=tags)
    form = fem.form(
        (
            (ufl.inner(ufl.curl(u), ufl.curl(v))
             + PETSc.ScalarType(2.5 - 0.2j) * ufl.inner(u, v)) * dx(1)
            + (ufl.inner(ufl.curl(u), ufl.curl(v))
               + PETSc.ScalarType(1.7 + 0.1j) * ufl.inner(u, v)) * dx(2)
        )
    )
    interiors = np.concatenate(owned_hcurl_cell_interior_dofs(space))
    n = int(space.dofmap.index_map.size_global)
    trace = np.setdiff1d(np.arange(n), interiors)
    master, slave = int(trace[0]), int(trace[-1])
    mpc = dolfinx_mpc.MultiPointConstraint(space)
    mpc.add_constraint(
        space,
        np.asarray([slave], dtype=np.int32),
        np.asarray([master], dtype=np.int64),
        np.asarray([np.exp(0.43j)], dtype=np.complex128),
        np.asarray([0], dtype=np.int32),
        np.asarray([0, 1], dtype=np.int32),
    )
    mpc.finalize()
    full = dolfinx_mpc.assemble_matrix(form, mpc, bcs=[])
    full.assemble()
    unconstrained_full = fem_petsc.assemble_matrix(form, bcs=[])
    unconstrained_full.assemble()
    condensed = build_unconstrained_assembly_time_condensation(
        form,
        space,
        tags,
        mpc=mpc,
        appended_global_rows=port_count,
        materialize_global_matrix=False,
        retain_local_schur_for_matrix_free=True,
        sum_duplicate_cell_integrals=True,
    )
    rng = np.random.default_rng(3919)
    B = 0.02 * (rng.normal(size=(n, port_count)) + 1j * rng.normal(size=(n, port_count))
                ).astype(np.complex128)
    D = 0.03 * (rng.normal(size=(port_count, n)) + 1j * rng.normal(size=(port_count, n))
                ).astype(np.complex128)
    B[slave, :] = 0.0
    D[:, slave] = 0.0
    H = np.diag(np.asarray([1.1 + 0.003 * i + 0.3j - 0.001j * i
                            for i in range(port_count)], dtype=np.complex128))
    entries = tuple(
        SimpleNamespace(
            coupling_rows=np.flatnonzero(B[:, port]).astype(PETSc.IntType),
            coupling_values=B[B[:, port] != 0.0, port].copy(),
            projection_rows=np.flatnonzero(D[port] != 0.0).astype(PETSc.IntType),
            projection_values=D[port, D[port] != 0.0].copy(),
            normalization_h=H[port, port],
        )
        for port in range(port_count)
    )
    carrier = SimpleNamespace(entries=entries)
    action = None
    try:
        action = build_p6_cell_condensed_action_from_carrier(
            condensed, carrier, port_coupling_mode=port_coupling_mode
        )
        tensor_identities = condensed.build_audit["action_only_complete_tensor_identities"]
        assert len(tensor_identities) == len(condensed.retained_local_schur_by_class)
        assert tensor_identities
        for identity in tensor_identities.values():
            assert identity["dtype"] == "complex128"
            assert len(identity["shape"]) == 2
            assert len(identity["raw_sha256"]) == 64
            assert len(identity["oriented_sha256"]) == 64
        indptr, indices, values = full.getValuesCSR()
        volume = csr_matrix((values, indices, indptr), shape=(n, n)).toarray()
        indptr_u, indices_u, values_u = unconstrained_full.getValuesCSR()
        volume_unconstrained = csr_matrix(
            (values_u, indices_u, indptr_u), shape=(n, n)
        ).toarray()
        augmented = np.block([[volume, B], [-D, H]])
        retained = np.r_[
            condensed.trace_constraints.owned_active_original_dofs,
            n + np.arange(port_count),
        ]
        eliminated = interiors
        expected = augmented[np.ix_(retained, retained)] - (
            augmented[np.ix_(retained, eliminated)]
            @ np.linalg.solve(
                augmented[np.ix_(eliminated, eliminated)],
                augmented[np.ix_(eliminated, retained)],
            )
        )
        for seed in (11, 12, 13):
            vector = rng.normal(size=action.reduced_size) + 1j * rng.normal(size=action.reduced_size)
            np.testing.assert_allclose(action.apply(vector), expected @ vector, rtol=2e-10, atol=2e-11)
        rhs = rng.normal(size=n) + 1j * rng.normal(size=n)
        rhs[slave] = 0.0
        port_rhs = rng.normal(size=port_count) + 1j * rng.normal(size=port_count)
        expected_rhs = np.r_[rhs, port_rhs][retained] - (
            augmented[np.ix_(retained, eliminated)]
            @ np.linalg.solve(
                augmented[np.ix_(eliminated, eliminated)],
                rhs[eliminated],
            )
        )
        np.testing.assert_allclose(
            action.reduce_rhs(rhs, port_rhs=port_rhs, rhs_is_mpc_dual=True),
            expected_rhs,
            rtol=2e-10,
            atol=2e-11,
        )
        solution = np.linalg.solve(expected, expected_rhs)
        recovered = action.recover_storage(solution, full_rhs=rhs)
        assert recovered[slave] == 0.0
        phase = np.exp(0.43j)

        def native_action(value: np.ndarray) -> np.ndarray:
            primal = value.copy()
            primal[slave] = phase * primal[master]
            raw = (volume_unconstrained + B @ np.linalg.solve(H, D)) @ primal
            projected = raw.copy()
            projected[master] += np.conjugate(phase) * raw[slave]
            projected[slave] = 0.0
            return projected

        evaluated = action.evaluate_native_residual(
            solution,
            rhs,
            native_action,
            port_rhs=port_rhs,
            rhs_is_mpc_dual=True,
        )
        assert evaluated["internal_residual_relative"] <= 3e-10
        assert evaluated["port_residual_relative"] <= 3e-10
        assert evaluated["native_identity_relative"] <= 3e-10, {
            key: evaluated[key]
            for key in (
                "native_identity_relative",
                "native_residual_relative",
                "internal_residual_relative",
                "port_residual_relative",
                "schur_port_identity_relative",
                "native_identity_operation_scale",
            )
        } | {
            "norm_native_residual": float(np.linalg.norm(evaluated["native_residual"])),
            "norm_derived_native_residual": float(np.linalg.norm(evaluated["derived_native_residual"])),
            "norm_augmented_fe": float(np.linalg.norm(evaluated["augmented_fe_residual"])),
            "norm_difference": float(np.linalg.norm(evaluated["native_identity_difference"])),
        }
        assert evaluated["schur_port_identity_relative"] <= 3e-10
        assert evaluated["storage_solution"][slave] == 0.0
        carrier_closure = -D @ recovered + H @ solution[condensed.active_rows :]
        np.testing.assert_allclose(
            carrier_closure, port_rhs, rtol=3e-10, atol=3e-11
        )
        if port_coupling_mode == "streamed":
            inventory = action.buffer_inventory
            assert inventory["Hhat_materialized"] is False
            assert inventory["resident_Hhat_bytes"] == 0
            assert inventory["transformed_port_payload_bytes_sum"] == 0
            assert inventory["per_cell_transformed_arrays_resident"] is False
            assert action.audit["streamed_max_local_scratch_bytes"] > 0
        assert action.buffer_inventory["unique_S_V_buffers"] <= action.buffer_inventory["class_count"]
        assert action.buffer_inventory["unique_recovery_buffers"] <= action.buffer_inventory["class_count"]
        assert action.operator_recipe["global_S6_matrix"] is False
    finally:
        if action is not None:
            action.destroy()
        else:
            condensed.destroy()
        unconstrained_full.destroy()
        full.destroy()


def test_p6_matrix_free_hhat_action_preserves_independent_nonhermitian_blocks_and_multirhs():
    port_keys = tuple((index, "top", index, 0, "s") for index in range(4))
    original_h = DiagonalOriginalPortBlock(
        np.asarray([2.0 + 0.3j, 1.4 - 0.2j, 3.1 + 0.1j, 0.8 + 0.4j]),
        port_keys,
    )
    alpha = np.asarray(
        [
            [0.8 + 0.2j, -0.3 + 0.9j, 0.5 - 0.1j],
            [0.1 - 0.6j, 0.7 + 0.3j, -0.4 + 0.2j],
            [-0.5 + 0.4j, 0.2 + 0.1j, 0.9 - 0.7j],
            [0.6 + 0.5j, -0.8 + 0.2j, 0.3 + 0.6j],
        ],
        dtype=np.complex128,
    )
    blocks = []
    for vii, bi, di, ports, callback_bytes in (
        (
            np.asarray([[3.0 + 0.4j, 0.2 - 0.3j], [-0.1 + 0.5j, 2.2 - 0.2j]]),
            np.asarray(
                [[0.2 + 0.3j, -0.4 + 0.1j, 0.7 - 0.2j, 0.1 + 0.6j],
                 [0.5 - 0.1j, 0.3 + 0.8j, -0.2 + 0.4j, 0.9 + 0.2j]]
            ),
            np.asarray([[0.4 + 0.2j, -0.3 + 0.7j], [0.1 - 0.5j, 0.8 + 0.1j]]),
            np.asarray([0, 2], dtype=np.int32),
            1024,
        ),
        (
            np.asarray([[1.7 - 0.6j]]),
            np.asarray([[0.3 + 0.5j, -0.7 + 0.2j, 0.6 + 0.1j, -0.2 - 0.4j]]),
            np.asarray([[0.2 - 0.3j], [0.9 + 0.4j]]),
            np.asarray([1, 2], dtype=np.int32),
            2048,
        ),
    ):
        factor = lu_factor(vii)
        internal_rhs = np.ascontiguousarray(bi @ alpha)
        blocks.append(
            {
                "factor": factor,
                "rhs": internal_rhs,
                "ports": ports,
                "di": di,
                "callback_bytes": callback_bytes,
            }
        )

    gate_records = []

    def allocation_gate(stage, facts):
        gate_records.append((stage, dict(facts)))

    terms = tuple(
        P6MatrixFreeHhatTerm(
            output_ports=block["ports"],
            interior_lu=block["factor"],
            interior_rhs=block["rhs"],
            apply_Di=lambda value, di=block["di"]: np.ascontiguousarray(di @ value),
            callback_workspace_bytes=block["callback_bytes"],
        )
        for block in blocks
    )
    actual = apply_p6_hhat_vector_action(
        original_h,
        alpha,
        terms,
        allocation_gate=allocation_gate,
    )

    expected = original_h.apply(alpha)
    for block in blocks:
        correction = block["di"] @ lu_solve(block["factor"], block["rhs"])
        np.add.at(expected, block["ports"], correction)
    assert actual.shape == (4, 3)
    np.testing.assert_allclose(actual, expected, rtol=2e-14, atol=2e-14)
    assert np.linalg.norm(alpha) > 0.0
    assert all(np.linalg.norm(block["rhs"]) > 0.0 for block in blocks)
    assert not np.allclose(original_h.diagonal, np.ones(original_h.count))
    assert [stage for stage, _facts in gate_records] == [
        "p6_hhat_vector/original_H",
        "p6_hhat_vector/local_D/0",
        "p6_hhat_vector/local_D/1",
    ]
    for _stage, facts in gate_records[1:]:
        assert facts["full_Hhat_allocated"] is False
        assert facts["mode_square_matrix_allocated"] is False
        assert facts["global_factorization_calls"] == 0
        assert facts["original_H_output_bytes"] == actual.nbytes
        assert facts["Di_output_bytes"] == 2 * 3 * np.dtype(np.complex128).itemsize


def test_p6_hhat_action_rejects_nonfinite_solve_and_accumulation():
    keys = ((0, "top", 0, 0, "s"),)
    allocation_gate = lambda _stage, _facts: None
    original_h = DiagonalOriginalPortBlock(np.asarray([2.0 + 0.5j]), keys)
    callback_called = False

    def unexpected_callback(_value):
        nonlocal callback_called
        callback_called = True
        return np.zeros(1, dtype=np.complex128)

    singular = P6MatrixFreeHhatTerm(
        output_ports=np.asarray([0], dtype=np.int32),
        interior_lu=(
            np.zeros((1, 1), dtype=np.complex128),
            np.asarray([0], dtype=np.int32),
        ),
        interior_rhs=np.asarray([1.0 + 0.0j]),
        apply_Di=unexpected_callback,
    )
    with pytest.raises(FloatingPointError, match="local interior solve returned nonfinite"):
        apply_p6_hhat_vector_action(
            original_h,
            np.asarray([0.7 + 0.2j]),
            (singular,),
            allocation_gate=allocation_gate,
        )
    assert callback_called is False

    large_h = DiagonalOriginalPortBlock(np.asarray([1.0e308 + 0.0j]), keys)
    overflowing = P6MatrixFreeHhatTerm(
        output_ports=np.asarray([0], dtype=np.int32),
        interior_lu=lu_factor(np.asarray([[1.0 + 0.0j]])),
        interior_rhs=np.asarray([1.0 + 0.0j]),
        apply_Di=lambda _value: np.asarray([1.0e308 + 0.0j]),
    )
    with pytest.raises(FloatingPointError, match="Hhat accumulation returned nonfinite"):
        apply_p6_hhat_vector_action(
            large_h,
            np.asarray([1.0 + 0.0j]),
            (overflowing,),
            allocation_gate=allocation_gate,
        )


def test_global_normalized_projection_maps_to_raw_boundary_plane_di():
    from src.common.config_3d import SimulationConfig3D
    from src.common.modes_3d import PortMode3D
    from src.solvers.dtn_boundary_phase_gauge import assembly_projection_denominator
    from src.solvers.dtn_boundary_phase_gauge import BOUNDARY_PLANE

    cfg = SimulationConfig3D(period_x=50.0, period_y=25.0, z_min=-10.0, z_max=130.0)
    mode = PortMode3D(
        side="top",
        m=0,
        n=0,
        polarization="s",
        alpha=0.0 + 0.0j,
        gamma=0.0 + 0.0j,
        beta=0.02 + 0.01j,
        refractive_index=1.0 + 0.0j,
        vertical_sign=1,
        e_vector=np.asarray([1.0 + 0.0j, 0.0 + 0.0j, 0.0 + 0.0j]),
        k_vector=np.asarray([0.0 + 0.0j, 0.0 + 0.0j, 0.02 + 0.01j]),
        h_vector=np.asarray([0.0 + 0.0j, 1.0 + 0.0j, 0.0 + 0.0j]),
        electric_tangential_norm_sq=1.0,
        power_per_unit_amplitude=0.0,
        propagating=False,
        rayleigh_warning=False,
    )
    hp = assembly_projection_denominator(mode, cfg, BOUNDARY_PLANE)
    original_h = DiagonalOriginalPortBlock(
        np.asarray([hp], dtype=np.complex128),
        ((0, "top", 0, 0, "s"),),
    )
    global_normalized = np.asarray([[0.2 - 0.4j, -0.7 + 0.1j]], dtype=np.complex128)
    actual = raw_plane_D_action_from_global_normalized(
        global_normalized,
        (mode,),
        cfg,
        original_h,
    )
    scale = np.exp(1j * mode.k_vector[2] * cfg.physical_z_max)
    expected = hp * scale * global_normalized
    np.testing.assert_allclose(actual, expected, rtol=2e-14, atol=2e-14)
    assert not np.isclose(abs(scale), 1.0)


def test_generated_port_action_matches_cached_with_unequal_modes_and_mpc_slave():
    rng = np.random.default_rng(20261012)
    n_i, n_t, n_p = 2, 3, 2
    interior = np.asarray([0, 1], dtype=PETSc.IntType)
    trace = np.asarray([2, 3, 4], dtype=PETSc.IntType)
    class_key = ("generated-mpc-fixture",)
    volume = _matrix(rng, n_i + n_t, n_i + n_t, 6.0)
    vii = volume[np.ix_(interior, interior)]
    vit = volume[np.ix_(interior, trace)]
    vti = volume[np.ix_(trace, interior)]
    vtt = volume[np.ix_(trace, trace)]
    factor = lu_factor(vii)
    xit = lu_solve(factor, vit)
    recovery = -xit
    trace_rhs_projection = -vti @ lu_solve(factor, np.eye(n_i, dtype=np.complex128))
    schur = vtt - vti @ xit
    active_trace = np.asarray([2, 3], dtype=PETSc.IntType)
    expansion_by_original = {
        2: (np.asarray([0], dtype=PETSc.IntType), np.asarray([1.0], dtype=np.complex128)),
        3: (np.asarray([1], dtype=PETSc.IntType), np.asarray([1.0], dtype=np.complex128)),
        4: (
            np.asarray([0, 1], dtype=PETSc.IntType),
            np.asarray([0.35 + 0.1j, 0.65 - 0.1j], dtype=np.complex128),
        ),
    }
    constraints = SimpleNamespace(
        owned_active_original_dofs=active_trace.copy(),
        original_to_active={2: 0, 3: 1},
        expansion_by_original=expansion_by_original,
    )
    condensed = SimpleNamespace(
        matrix=None,
        active_rows=2,
        appended_rows=n_p,
        full_rows=n_i + n_t,
        owned_active_rows=2,
        owned_appended_rows=n_p,
        owned_trace_original_dofs=trace.copy(),
        comm=MPI.COMM_SELF,
        trace_constraints=constraints,
        cell_recovery_maps=(CellRecoveryMap(
            interior_original_dofs=interior.copy(),
            trace_original_dofs=trace.copy(),
            class_key=class_key,
        ),),
        interior_lu_by_class={class_key: factor},
        interior_from_trace_by_class={class_key: recovery},
        trace_from_interior_rhs_by_class={class_key: trace_rhs_projection},
        retained_local_schur_by_class={class_key: schur},
        build_audit={},
    )

    def mode_column(port):
        scale = float(port + 1)
        bi_col = np.asarray([0.2 + 0.1j * scale, -0.3j + 0.05 * scale], dtype=np.complex128)
        bt_col = np.asarray(
            [0.07j * scale, 0.11 * scale, (0.03 + 0.02j) * scale],
            dtype=np.complex128,
        )
        di_row = np.asarray([0.13 - 0.03j * scale, -0.09j * scale], dtype=np.complex128)
        dt_row = np.asarray(
            [0.02j * scale, -0.04 * scale, (-0.015 + 0.025j) * scale],
            dtype=np.complex128,
        )
        return bi_col, bt_col, di_row, dt_row

    ports = np.arange(n_p, dtype=PETSc.IntType)
    bi_columns, bt_columns, di_rows, dt_rows = zip(
        *(mode_column(port) for port in range(n_p)), strict=True
    )
    bi = np.column_stack(bi_columns)
    bt_raw = np.column_stack(bt_columns)
    di = np.vstack(di_rows)
    dt_raw = np.vstack(dt_rows)
    trace_expansion = np.asarray(
        [
            [1.0 + 0.0j, 0.0j],
            [0.0j, 1.0 + 0.0j],
            [0.35 + 0.1j, 0.65 - 0.1j],
        ],
        dtype=np.complex128,
    )
    # The cached fixture uses production-dual rows. The generated path below
    # receives raw local rows and applies E^H B and D E itself.
    bt = np.zeros_like(bt_raw)
    bt[:2] = trace_expansion.conjugate().T @ bt_raw
    dt = np.zeros_like(dt_raw)
    dt[:, :2] = dt_raw @ trace_expansion
    hp_diagonal = np.asarray([1.3 + 0.1j, 1.7 - 0.2j], dtype=np.complex128)
    hp = np.diag(hp_diagonal)
    cached = P6CellCondensedAction(
        condensed,
        H_p=hp,
        port_terms={0: P6CellPortTerms(
            bi, di, ports, Bt=bt, Dt=dt,
            H=np.zeros((n_p, n_p), dtype=np.complex128),
        )},
    )

    def generate_B(amplitudes):
        bi_action = np.zeros(n_i, dtype=np.complex128)
        bt_action = np.zeros(n_t, dtype=np.complex128)
        for port, amplitude in enumerate(amplitudes):
            _bi, _bt, _di, _dt = mode_column(port)
            bi_action += _bi * amplitude
            bt_action += _bt * amplitude
        return bi_action, bt_action

    def generate_D(interior_values, trace_values):
        return np.ascontiguousarray([
            np.dot(mode_column(port)[2], interior_values)
            + np.dot(mode_column(port)[3], trace_values)
            for port in range(n_p)
        ], dtype=np.complex128)

    generated = P6CellCondensedAction(
        condensed,
        H_p=None,
        port_block_layout=RESEARCH_PORT_LAYOUT,
        original_port_block=DiagonalOriginalPortBlock(
            hp_diagonal,
            [("target", "bottom", -1, 0, "s"), ("target", "bottom", 0, 0, "s")],
        ),
        port_coupling_mode="streamed",
        generated_port_actions={0: P6GeneratedCellPortAction(
            port_indices=ports,
            apply_B=generate_B,
            apply_D=generate_D,
            callback_workspace_bytes=1024,
        )},
    )
    try:
        assert generated._cells[0].generated_action is not None
        assert generated._cells[0].Bt is None and generated._cells[0].Dt is None
        assert generated._cells[0].Bi.shape == (n_i, 0)
        assert generated._cells[0].Di.shape == (0, n_i)
        assert generated.buffer_inventory["raw_port_payload_bytes_sum"] == 0
        assert generated.buffer_inventory["transformed_port_payload_bytes_sum"] == 0
        assert generated.buffer_inventory["generated_port_mode_count"] == n_p
        assert generated.buffer_inventory["generated_callback_workspace_bound_bytes"] == 1024
        assert generated.port_block_representation_identity["generated_cell_port_actions"]
        assert generated._condensed_port_block is None

        reduced = rng.normal(size=generated.reduced_size) + 1j * rng.normal(
            size=generated.reduced_size
        )
        full_rhs = rng.normal(size=condensed.full_rows) + 1j * rng.normal(
            size=condensed.full_rows
        )
        full_rhs[4] = 0.0
        port_rhs = rng.normal(size=n_p) + 1j * rng.normal(size=n_p)
        np.testing.assert_allclose(generated.apply(reduced), cached.apply(reduced), rtol=2e-13, atol=2e-13)
        np.testing.assert_allclose(
            generated.reduce_rhs(full_rhs, port_rhs=port_rhs),
            cached.reduce_rhs(full_rhs, port_rhs=port_rhs),
            rtol=2e-13,
            atol=2e-13,
        )
        generated_recovery = generated.recover_storage(reduced, full_rhs=full_rhs)
        cached_recovery = cached.recover_storage(reduced, full_rhs=full_rhs)
        np.testing.assert_allclose(generated_recovery, cached_recovery, rtol=2e-13, atol=2e-13)
        assert generated_recovery[4] == 0.0
        alpha = reduced[condensed.active_rows :]
        generated_B = generated.apply_B_full(alpha)
        cached_B = cached.apply_B_full(alpha)
        np.testing.assert_allclose(generated_B, cached_B, rtol=0.0, atol=2e-16)
        assert generated_B[4] == 0.0
        full_field = rng.normal(size=condensed.full_rows) + 1j * rng.normal(size=condensed.full_rows)
        full_field[4] = 3.0 - 2.0j
        np.testing.assert_allclose(
            generated.apply_D_full(full_field),
            cached.apply_D_full(full_field),
            rtol=0.0,
            atol=0.0,
        )

        raw_B = np.zeros((condensed.full_rows, n_p), dtype=np.complex128)
        raw_B[interior, :] = bi
        raw_B[trace, :] = bt_raw
        raw_D = np.zeros((n_p, condensed.full_rows), dtype=np.complex128)
        raw_D[:, interior] = di
        raw_D[:, trace] = dt_raw

        def expand_primal(storage):
            expanded = np.asarray(storage, dtype=np.complex128).copy()
            expanded[4] = trace_expansion[2] @ expanded[active_trace]
            return expanded

        def pullback_dual(raw):
            dual = np.asarray(raw, dtype=np.complex128).copy()
            dual[active_trace] += trace_expansion[2].conjugate() * dual[4]
            dual[4] = 0.0
            return dual

        alpha = reduced[condensed.active_rows :]
        oracle_B = pullback_dual(raw_B @ alpha)
        np.testing.assert_allclose(
            generated.apply_B_full(alpha), oracle_B, rtol=2e-14, atol=2e-14
        )
        oracle_D = raw_D @ expand_primal(full_field)
        np.testing.assert_allclose(
            generated.apply_D_full(full_field), oracle_D, rtol=2e-14, atol=2e-14
        )

        def native_apply(storage):
            primal = expand_primal(storage)
            port_action = raw_D @ primal
            raw_native = volume @ primal + raw_B @ (port_action / hp_diagonal)
            return pullback_dual(raw_native)

        residual_facts = generated.evaluate_native_residual(
            reduced,
            full_rhs,
            native_apply,
            port_rhs=port_rhs,
            rhs_is_mpc_dual=True,
        )
        assert np.linalg.norm(residual_facts["internal_residual"]) > 0.0
        assert np.linalg.norm(residual_facts["native_residual"]) > 0.0
        for metric in ("native_identity_relative", "schur_port_identity_relative"):
            assert residual_facts[metric] <= 1e-10, (metric, residual_facts[metric])
        assert generated.audit["generated_callback_call_count"] > 0
    finally:
        generated.destroy()
        cached.destroy()
