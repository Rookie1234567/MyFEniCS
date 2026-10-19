import hashlib
from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers.hcurl_assembly_time_condensation import (
    CellRecoveryMap,
    TraceConstraintMap,
    iter_selected_volume_audit_cells,
    tabulate_volume_audit_cell,
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


def test_tabulate_volume_audit_cell_uses_all_kernels_rows_and_orientation(monkeypatch):
    class _Topology:
        dim = 3

        @staticmethod
        def index_map(_dimension):
            return SimpleNamespace(size_local=1)

        @staticmethod
        def create_entity_permutations():
            return None

        @staticmethod
        def get_cell_permutation_info():
            return np.asarray([7], dtype=np.uint32)

    class _Element:
        space_dimension = 4
        basix_element = SimpleNamespace(entity_dofs=[[], [], [], [[1, 3]]])

        @staticmethod
        def T_apply(data, cell_info, dimension):
            matrix = np.asarray(data).reshape(dimension, dimension)
            if int(cell_info[0]) == 7:
                matrix[:] = matrix[[1, 0, 2, 3]].copy()

    points = np.asarray(
        [
            [0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0],
            [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1],
        ],
        dtype=np.float64,
    )
    mesh = SimpleNamespace(
        topology=_Topology(),
        geometry=SimpleNamespace(
            x=points,
            dofmap=np.arange(8, dtype=np.int32).reshape(1, 8),
        ),
    )
    function_space = SimpleNamespace(
        mesh=mesh,
        element=_Element(),
        dofmap=SimpleNamespace(
            cell_dofs=lambda _cell: np.arange(4, dtype=np.int32),
            index_map=SimpleNamespace(
                local_to_global=lambda rows: np.asarray(rows, dtype=np.int64) + 100
            ),
        ),
    )
    cell_tags = SimpleNamespace(
        indices=np.asarray([0], dtype=np.int32),
        values=np.asarray([4], dtype=np.int32),
    )
    class_key = (4, 1.0, 1.0, 1.0, 7)
    cell_map = CellRecoveryMap(
        interior_original_dofs=np.asarray([101, 103], dtype=np.int64),
        trace_original_dofs=np.asarray([100, 102], dtype=np.int64),
        class_key=class_key,
    )
    owner = SimpleNamespace(cell_recovery_maps=(cell_map,))

    class _Kernel:
        pass

    default_kernel, tag_kernel_a, tag_kernel_b = _Kernel(), _Kernel(), _Kernel()
    kernels = (default_kernel, tag_kernel_a, tag_kernel_b)
    form = SimpleNamespace(
        ufcx_form=SimpleNamespace(
            form_integral_offsets=np.asarray([0, 3], dtype=np.int32),
            form_integral_ids=np.asarray([-1, 4, 4], dtype=np.int32),
            form_integrals=[
                SimpleNamespace(tabulate_tensor_complex128=kernel)
                for kernel in kernels
            ],
            num_coefficients=0,
            num_constants=0,
        ),
        module=SimpleNamespace(ffi=SimpleNamespace(NULL=object())),
    )
    default_tensor = np.asarray(
        [
            [1 + 2j, 2 + 1j, 3 - 1j, 4 + 3j],
            [5 - 2j, 6 + 1j, 7 + 4j, 8 - 3j],
            [9 + 1j, 10 - 4j, 11 + 2j, 12 + 5j],
            [13 - 1j, 14 + 3j, 15 - 2j, 16 + 1j],
        ],
        dtype=np.complex128,
    )
    tag_tensor_a = np.diag(np.asarray([1j, 2j, 3j, 4j], dtype=np.complex128))
    tag_tensor_b = np.zeros((4, 4), dtype=np.complex128)
    tag_tensor_b[0, 1] = 2 - 3j
    tag_tensor_b[3, 2] = -1 + 2j
    tensors = {
        default_kernel: default_tensor,
        tag_kernel_a: tag_tensor_a,
        tag_kernel_b: tag_tensor_b,
    }
    tabulation_calls = []

    def fake_tabulate(_form, kernel, _coordinates, dimension):
        tabulation_calls.append(kernel)
        assert dimension == 4
        return tensors[kernel].copy()

    monkeypatch.setattr(
        "src.solvers.hcurl_assembly_time_condensation._tabulate_cell_tensor",
        fake_tabulate,
    )
    result = tabulate_volume_audit_cell(form, function_space, cell_tags, owner, 0)

    raw = default_tensor + tag_tensor_a + tag_tensor_b
    expected_oriented = raw[[1, 0, 2, 3]][:, [1, 0, 2, 3]]
    interior = np.asarray([1, 3], dtype=np.int32)
    trace = np.asarray([0, 2], dtype=np.int32)
    np.testing.assert_array_equal(result["K"], expected_oriented[np.ix_(interior, interior)])
    np.testing.assert_array_equal(result["G"], expected_oriented[np.ix_(interior, trace)])
    np.testing.assert_array_equal(result["J"], expected_oriented[np.ix_(trace, interior)])
    np.testing.assert_array_equal(result["L"], expected_oriented[np.ix_(trace, trace)])
    assert not np.allclose(result["J"], result["G"].T)
    assert result["integral_kernel_counts"] == {"default": 1, "tagged": 2}
    assert tabulation_calls == list(kernels)
    assert result["class_key"] == class_key
    assert result["interior_original_dofs"].tolist() == [101, 103]
    assert result["trace_original_dofs"].tolist() == [100, 102]
    assert len(result["hashes"]["raw_tensor"]) == 64
    assert result["hashes"]["raw_tensor"] == hashlib.sha256(raw.tobytes()).hexdigest()

    wrong_rows = SimpleNamespace(
        cell_recovery_maps=(
            CellRecoveryMap(
                interior_original_dofs=np.asarray([101, 103]),
                trace_original_dofs=np.asarray([100, 999]),
                class_key=class_key,
            ),
        )
    )
    with pytest.raises(ValueError, match="original-row identity mismatch"):
        tabulate_volume_audit_cell(form, function_space, cell_tags, wrong_rows, 0)

    wrong_direction = SimpleNamespace(
        cell_recovery_maps=(
            CellRecoveryMap(
                interior_original_dofs=np.asarray([101, 103]),
                trace_original_dofs=np.asarray([100, 102]),
                class_key=(4, 1.0, 1.0, 1.0, 6),
            ),
        )
    )
    with pytest.raises(ValueError, match="class identity mismatch"):
        tabulate_volume_audit_cell(form, function_space, cell_tags, wrong_direction, 0)
    assert tabulation_calls == list(kernels)
