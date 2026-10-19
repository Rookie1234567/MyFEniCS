from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers.hcurl_assembly_time_condensation import (
    CellRecoveryMap,
    TraceConstraintMap,
    iter_selected_volume_audit_cells,
)


def test_selected_active_row_finds_slave_predecessors_without_identity_shortcut():
    constraints = TraceConstraintMap(
        owned_active_original_dofs=np.arange(10, dtype=np.int64),
        original_to_active={},
        expansion_by_original={
            10: (np.asarray([7]), np.asarray([1.0])),
            11: (np.asarray([3, 7]), np.asarray([0.5, 0.25])),
            12: (np.asarray([1, 7]), np.asarray([0.75, 0.25])),
            13: (np.asarray([4]), np.asarray([1.0])),
        },
        full_trace_rows=14,
        active_rows=10,
        slave_rows=4,
        owned_active_range=(0, 10),
        build_audit={},
    )
    cells = (
        CellRecoveryMap(
            interior_original_dofs=np.asarray([100]),
            trace_original_dofs=np.asarray([10, 11]),
            class_key=("same-class",),
        ),
        CellRecoveryMap(
            interior_original_dofs=np.asarray([101]),
            trace_original_dofs=np.asarray([12, 13]),
            class_key=("same-class",),
        ),
    )
    T = np.asarray([[1.0 + 2.0j, 3.0 - 1.0j]])
    R = np.asarray([[2.0j], [4.0 + 1.0j]])
    S = np.asarray([[5.0 + 0.5j]])
    LU = (np.asarray([[2.0, 0.0], [1.0, 3.0]]), np.asarray([0, 1]))
    owner = SimpleNamespace(
        active_rows=10,
        cell_recovery_maps=cells,
        trace_constraints=constraints,
        trace_from_interior_rhs_by_class={("same-class",): T},
        interior_from_trace_by_class={("same-class",): R},
        retained_local_schur_by_class={("same-class",): S},
        interior_lu_by_class={("same-class",): LU},
    )

    selected = list(iter_selected_volume_audit_cells(owner, [7]))

    assert [cell["cell_index"] for cell in selected] == [0, 1]
    assert all(7 in cell["active_ids"] for cell in selected)
    first = selected[0]
    assert first["active_ids"].tolist() == [3, 7]
    np.testing.assert_allclose(first["E"].toarray(), [[0.0, 1.0], [0.5, 0.25]])
    assert not np.array_equal(first["E"].toarray(), np.eye(2))
    assert selected[1]["active_ids"].tolist() == [1, 4, 7]
    np.testing.assert_allclose(
        selected[1]["E"].toarray(), [[0.75, 0.0, 0.25], [0.0, 1.0, 0.0]]
    )

    for cell in selected:
        for cached, reference in zip(
            (cell["T"], cell["R"], cell["S"], *cell["LU"]),
            (T, R, S, *LU),
            strict=True,
        ):
            assert np.shares_memory(cached, reference)
            assert not cached.flags.writeable
        assert not cell["E"].data.flags.writeable

    assert [cell["cell_index"] for cell in iter_selected_volume_audit_cells(owner)] == [0, 1]
    with pytest.raises(ValueError, match="integer active rows"):
        list(iter_selected_volume_audit_cells(owner, [7.0]))
    with pytest.raises(ValueError, match=r"\[0, 10\)"):
        list(iter_selected_volume_audit_cells(owner, [10]))
