import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.solvers import hcurl_assembly_time_condensation as condensation
from src.solvers.hcurl_assembly_time_condensation import TraceConstraintMap


def _fake_selected_trace_case():
    cells = [
        np.asarray([0, 6, 5, 2, 7, 4], dtype=np.int32),
        np.asarray([3, 8, 9, 10, 11, 12], dtype=np.int32),
        np.asarray([0, 13, 9, 10, 14, 12], dtype=np.int32),
    ]

    class IndexMap:
        size_global = 16
        size_local = 16
        local_range = (0, 16)

        @staticmethod
        def local_to_global(values):
            return np.asarray(values, dtype=np.int64)

    class DofMap:
        index_map = IndexMap()
        index_map_bs = 1

        @staticmethod
        def cell_dofs(cell):
            return cells[cell]

    class Topology:
        dim = 3

        @staticmethod
        def index_map(_dimension):
            return SimpleNamespace(size_local=len(cells))

        @staticmethod
        def create_entity_permutations():
            return None

        @staticmethod
        def get_cell_permutation_info():
            return np.asarray([1, 2, 3], dtype=np.uint32)

    class Comm:
        size = 1
        rank = 0

        @staticmethod
        def allgather(value):
            return [value]

    coordinates = np.arange(3 * 8 * len(cells), dtype=np.float64).reshape(-1, 3)
    geometry_dofmap = np.arange(8 * len(cells), dtype=np.int32).reshape(-1, 8)
    mesh = SimpleNamespace(
        comm=Comm(),
        topology=Topology(),
        geometry=SimpleNamespace(dofmap=geometry_dofmap, x=coordinates),
    )
    space = SimpleNamespace(
        mesh=mesh,
        dofmap=DofMap(),
        element=SimpleNamespace(
            space_dimension=6,
            basix_element=SimpleNamespace(entity_dofs=[[], [], [], [[1, 4]]]),
        ),
    )
    constraints = TraceConstraintMap(
        owned_active_original_dofs=np.asarray([0, 2, 3, 4], dtype=np.int64),
        original_to_active={},
        expansion_by_original={
            0: (np.asarray([0]), np.asarray([1.0 + 0.0j])),
            2: (np.asarray([1]), np.asarray([1.0 + 0.0j])),
            3: (np.asarray([2]), np.asarray([1.0 + 0.0j])),
            4: (np.asarray([3]), np.asarray([1.0 + 0.0j])),
            5: (np.asarray([2]), np.asarray([0.5 + 0.25j])),
            9: (np.asarray([0]), np.asarray([1.0 + 0.0j])),
            10: (np.asarray([1]), np.asarray([1.0 + 0.0j])),
            12: (np.asarray([3]), np.asarray([1.0 + 0.0j])),
        },
        full_trace_rows=8,
        active_rows=4,
        slave_rows=1,
        owned_active_range=(0, 4),
        build_audit={"status": "fixture"},
    )
    tags = SimpleNamespace(
        indices=np.arange(len(cells), dtype=np.int32),
        values=np.asarray([1, 2, 3], dtype=np.int32),
    )
    return space, constraints, tags, cells


def test_selected_trace_star_uses_noncontiguous_partition_and_mpc_preimages(monkeypatch):
    space, constraints, tags, cells = _fake_selected_trace_case()
    seen_partition = {}

    def owned_numbering(function_space, local_interiors, *, compact):
        assert function_space is space
        assert compact is True
        seen_partition["interiors"] = tuple(np.asarray(row).copy() for row in local_interiors)
        return (
            np.asarray([0, 2, 3, 4, 5, 9, 10, 12], dtype=np.int32),
            {row: index for index, row in enumerate([0, 2, 3, 4, 5, 9, 10, 12])},
            8,
            16,
        )

    def constraint_map(_space, _owned, _mapping, _trace_rows, _mpc, *, compact):
        assert compact is True
        return constraints

    monkeypatch.setattr(condensation, "_owned_trace_numbering", owned_numbering)
    monkeypatch.setattr(condensation, "_trace_constraint_map", constraint_map)

    selected = condensation.build_selected_volume_trace_star_metadata(
        space,
        object(),
        tags,
        selected_active_row=2,
        expected_active_original_rows=np.asarray([0, 2, 3, 4], dtype=np.int64),
    )

    assert [item["cell_index"] for item in selected["incidents"]] == [0, 1]
    assert selected["selected_original_row"] == 3
    assert selected["owned_cells"] == 3
    assert [row.tolist() for row in seen_partition["interiors"]] == [
        [6, 7], [8, 11], [13, 14]
    ]
    first, second = selected["incidents"]
    assert first["interior_positions"].tolist() == [1, 4]
    assert first["trace_positions"].tolist() == [0, 2, 3, 5]
    assert first["trace_original_rows"].tolist() == [0, 5, 2, 4]
    assert first["selected_local_trace_rows"].tolist() == [1]
    assert first["selected_trace_contribution_kinds"] == ["mpc_expansion_preimage"]
    np.testing.assert_allclose(first["selected_trace_coefficients"], [0.5 + 0.25j])
    assert second["trace_original_rows"][second["selected_local_trace_rows"][0]] == 3
    assert second["selected_trace_contribution_kinds"] == ["direct_original_row"]
    assert first["actual_geometry_coordinates"].shape == (8, 3)
    assert first["actual_coordinate_sha256"]
    assert len(cells) == selected["owned_cells"]


def test_v8_metadata_selection_reaches_both_production_roles_and_saved_arrays(
    monkeypatch, tmp_path
):
    from src.runners import task41_p0_v4_volume_only_audit as audit

    space, _constraints, tags, _cells = _fake_selected_trace_case()
    space.element.T_apply = lambda _values, _cell_info, _dimension: None
    active_rows = np.asarray([0, 1, 2, 3, 4, 9, 10, 12, 15], dtype=np.int64)
    offsets = np.zeros(17, dtype=np.int64)
    offsets[6:] = 1
    mpc = SimpleNamespace(
        function_space=space,
        slaves=np.asarray([5], dtype=np.int32),
        masters=SimpleNamespace(
            links=lambda local_slave: np.asarray([3], dtype=np.int32)
        ),
        coefficients=lambda: (
            np.asarray([0.5 + 0.25j], dtype=np.complex128),
            offsets,
        ),
    )
    metadata = condensation.build_selected_volume_trace_star_metadata(
        space,
        mpc,
        tags,
        selected_active_row=3,
        expected_active_original_rows=active_rows,
    )
    assert [row["cell_index"] for row in metadata["incidents"]] == [0, 1]
    assert metadata["selected_original_row"] == 3
    slave_preimage, direct = metadata["incidents"]
    assert slave_preimage["selected_local_trace_rows"].tolist() == [1]
    assert slave_preimage["selected_trace_contribution_kinds"] == [
        "mpc_expansion_preimage"
    ]
    np.testing.assert_allclose(
        slave_preimage["selected_trace_coefficients"], [0.5 + 0.25j]
    )
    assert direct["selected_trace_contribution_kinds"] == ["direct_original_row"]

    candidate_tensor = np.asarray(
        [
            [4.0 + 0.1j, 0.2, 0.0, 0.0, 0.1j, 0.0],
            [0.1, 5.0, 0.2j, 0.0, 0.1, 0.0],
            [0.0, 0.1j, 6.0, 0.2, 0.0, 0.0],
            [0.0, 0.0, 0.1, 7.0, 0.1j, 0.0],
            [0.2j, 0.1, 0.0, 0.1j, 8.0, 0.2],
            [0.0, 0.0, 0.0, 0.0, 0.1, 9.0],
        ],
        dtype=np.complex128,
    )
    reference_tensor = candidate_tensor + np.diag(
        np.asarray([0.5, 0.25, 0.5, 0.25, 0.5, 0.25], dtype=np.complex128)
    )

    class CandidateEvaluator:
        identity = "fixture_qmetric_candidate"

        def __init__(self):
            self.cells = []

        def __call__(self, _form, _kernels, coordinates, *, tag, dimension):
            self.cells.append((tag, dimension, coordinates.shape))
            return candidate_tensor.copy()

    candidate = CandidateEvaluator()
    reference_calls = []

    def reference_kernel(_form, _kernels, coordinates, *, tag, dimension):
        reference_calls.append((tag, dimension, coordinates.shape))
        return reference_tensor.copy()

    monkeypatch.setattr(
        condensation, "_tabulate_raw_tensor_class", reference_kernel
    )
    evidence = tmp_path / "selected-cell-evidence"
    evidence.mkdir()
    saved_arrays = {}

    def persist(name, array):
        record = audit._persist_array(
            evidence,
            name,
            array,
            sha256_file=lambda path: hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        saved_arrays[name] = np.load(record["path"], allow_pickle=False)
        return record

    progress = []
    role_results = {}
    for row in metadata["incidents"]:
        cell_index = int(row["cell_index"])
        role_results[cell_index] = audit._v8_rebuild_selected_cell_role_artifacts(
            cell_index=cell_index,
            row=row,
            combined_form=object(),
            kernels={},
            element=space.element,
            dimension=space.element.space_dimension,
            interior_positions=metadata["interior_positions"],
            trace_positions=metadata["trace_positions"],
            candidate_evaluator=candidate,
            persist_array=persist,
            progress=progress.append,
        )

    assert set(role_results) == {0, 1}
    assert candidate.cells == [(1, 6, (8, 3)), (2, 6, (8, 3))]
    assert reference_calls == candidate.cells
    assert len(saved_arrays) == 2 * 2 * 7
    for cell_index, roles in role_results.items():
        assert set(roles) == {"candidate", "reference"}
        for role, result in roles.items():
            assert result["source"] == "RECONSTRUCTED_SELECTED_CELL"
            assert set(result["artifacts"]) == {
                "raw_tensor",
                "oriented_tensor",
                "R",
                "T",
                "S",
                "interior_lu",
                "interior_lu_pivots",
            }
            for field, artifact in result["artifacts"].items():
                saved = saved_arrays[artifact["name"]]
                expected = (
                    result["rts"][field]
                    if field in result["rts"]
                    else result[field]
                    if field in {"raw_tensor", "oriented_tensor", "lu", "pivots"}
                    else None
                )
                if field == "interior_lu":
                    expected = result["lu"]
                elif field == "interior_lu_pivots":
                    expected = result["pivots"]
                np.testing.assert_array_equal(saved, expected)
                assert (
                    hashlib.sha256(Path(artifact["path"]).read_bytes()).hexdigest()
                    == artifact["sha256"]
                )
    assert sum(event["status"] == "COMPLETED" for event in progress) == 4


def test_selected_trace_column_support_ignores_exact_zero_but_keeps_complex_slave_term():
    from scipy import sparse

    active_ids = np.asarray([4, 9], dtype=np.int64)
    expansion = sparse.csr_matrix(
        np.asarray(
            [
                [1.0, 0.0],
                [0.0, 0.25 + 0.5j],
                [0.0, 0.0],
            ],
            dtype=np.complex128,
        )
    )
    rows, coefficients = condensation._selected_trace_column_support(
        active_ids, expansion, 9
    )
    assert rows.tolist() == [1]
    np.testing.assert_array_equal(coefficients, np.asarray([0.25 + 0.5j]))
    assert condensation._selected_trace_column_support(active_ids, expansion, 4)[0].tolist() == [0]
    assert condensation._selected_trace_column_support(active_ids, expansion, 12) is None


def test_stored_block_defects_distinguish_cs_from_es_and_keep_nonhermitian_terms():
    from src.runners.task41_p0_v4_volume_only_audit import _v8_defect_matrices

    # C_S is exactly zero for these stored blocks, while the solve error in T
    # makes E_S nonzero. The matrices are intentionally non-Hermitian.
    K = np.asarray([[2.0 + 0.0j]])
    G = np.asarray([[1.0 + 0.0j]])
    J = np.asarray([[3.0 + 0.0j]])
    L = np.asarray([[4.0 + 0.0j]])
    R = np.asarray([[-0.5 + 0.0j]])
    T = np.asarray([[-1.4 + 0.0j]])
    S = np.asarray([[2.5 + 0.0j]])
    result = _v8_defect_matrices(K, G, J, L, R, T, S)
    assert result["C_S"]["max_abs"] == 0.0
    assert result["E_R"]["max_abs"] == 0.0
    assert np.isclose(result["E_T"]["max_abs"], 0.2, rtol=0.0, atol=3.0e-16)
    assert np.isclose(result["E_S"]["max_abs"], 0.1, rtol=0.0, atol=2.0e-16)
    assert result["E_S_identity_residual"]["max_abs"] == 0.0

    K = np.asarray([[2.0 + 0.2j, 0.3], [0.1j, 1.4 - 0.1j]])
    G = np.asarray([[0.3 + 0.2j, 0.1], [0.4j, -0.2 + 0.1j]])
    J = np.asarray([[0.7 - 0.1j, -0.3j], [0.2, 0.5 + 0.2j]])
    L = np.asarray([[1.1 + 0.3j, 0.2j], [-0.1, 0.9 - 0.2j]])
    R = np.asarray([[0.1 + 0.2j, -0.3], [0.05j, 0.2 - 0.1j]])
    T = np.asarray([[-0.1 + 0.2j, 0.3], [0.15j, -0.2 + 0.1j]])
    S = np.asarray([[0.9 + 0.1j, 0.1], [-0.2j, 1.2 - 0.1j]])
    result = _v8_defect_matrices(K, G, J, L, R, T, S)
    assert result["E_S_identity_residual"]["frobenius"] < 1.0e-14


def test_selected_volume_condensation_uses_actual_noncontiguous_i_t_positions():
    matrix = np.asarray(
        [
            [5, 1, 2, 0],
            [3, 7, 0, 1],
            [0, 2, 6, 4],
            [1, 0, 3, 8],
        ],
        dtype=np.complex128,
    )
    blocks = condensation.condense_selected_volume_tensor(
        matrix,
        np.asarray([1, 3], dtype=np.int32),
        np.asarray([0, 2], dtype=np.int32),
    )
    np.testing.assert_array_equal(blocks["K"], matrix[np.ix_([1, 3], [1, 3])])
    np.testing.assert_array_equal(blocks["G"], matrix[np.ix_([1, 3], [0, 2])])
    np.testing.assert_array_equal(blocks["J"], matrix[np.ix_([0, 2], [1, 3])])
    np.testing.assert_array_equal(blocks["L"], matrix[np.ix_([0, 2], [0, 2])])
    np.testing.assert_allclose(blocks["R"], -np.linalg.solve(blocks["K"], blocks["G"]))
    np.testing.assert_allclose(
        blocks["T"], -np.linalg.solve(blocks["K"].conj().T, blocks["J"].conj().T).conj().T
    )
    np.testing.assert_allclose(blocks["S"], blocks["L"] + blocks["J"] @ blocks["R"])


def test_v8_last_combination_recomposes_saved_operands_with_wider_real_imag_arithmetic():
    from src.runners.task41_p0_v4_volume_only_audit import (
        _v8_recompose_saved_closure_inputs,
    )

    active = np.asarray([2, 0], dtype=np.int64)
    native_rhs = np.asarray([0.0, 0.0, 1.0], dtype=np.complex128)
    native_volume_rhs = np.asarray([0.0, 0.0, 1.0], dtype=np.complex128)
    native_action = np.zeros(3, dtype=np.complex128)
    full = np.asarray([[1.0e16, 0.0], [0.0, 0.0], [0.0, 0.0]], dtype=np.complex128)
    reduced = np.zeros_like(full)
    d_volume = np.asarray([1.0e16, 0.0], dtype=np.complex128)
    reduce_r = np.asarray([1.0, 0.0], dtype=np.complex128)
    zeros = np.zeros(2, dtype=np.complex128)
    # The saved V7-style float64 expression rounds d + 1 - d to exactly zero.
    result = _v8_recompose_saved_closure_inputs(
        active_original_rows=active,
        native_rhs=native_rhs,
        native_volume_rhs=native_volume_rhs,
        native_volume_action=native_action,
        b_alpha_rows=np.asarray([], dtype=np.int64),
        b_alpha_values=np.asarray([], dtype=np.complex128),
        full_p6=full,
        full_reduced_rhs=reduced,
        d_volume=d_volume,
        reduce_r_full=reduce_r,
        reduce_r_volume=reduce_r,
        T_r_i=zeros,
        delta_t=np.asarray([1.0e16, 0.0], dtype=np.complex128),
        attributed_terms=zeros,
        saved_full_closure=zeros,
        saved_volume_closure=zeros,
        column_index=0,
        paired_state_inputs={
            "native_volume_action": native_action,
            "T_r_i": zeros,
            "delta_t": np.asarray([1.0e16, 0.0], dtype=np.complex128),
            "attributed_terms": zeros,
        },
        chunk_size=1,
    )
    assert result["full_float64_recompose_vs_saved"]["max_abs"] == 0.0
    assert result["volume_float64_recompose_vs_saved"]["max_abs"] == 0.0
    wider = np.finfo(np.longdouble).nmant > np.finfo(np.float64).nmant
    expected_last_term = 1.0 if wider else 0.0
    assert result["full_longdouble_recompose_vs_saved"]["max_abs"] == expected_last_term
    assert result["volume_longdouble_recompose_vs_saved"]["max_abs"] == expected_last_term
    assert result["full_longdouble_closure"]["absolute_l2"] == expected_last_term
    assert result["volume_longdouble_closure"]["absolute_l2"] == expected_last_term
    assert result["full_longdouble_dhat_j0_vs_j3"]["max_abs"] == 0.0
    assert result["volume_longdouble_dhat_j0_vs_j3"]["max_abs"] == 0.0
    assert result["full_longdouble_recompose_vs_saved"]["max_row"] == (0 if wider else None)
    assert result["volume_longdouble_recompose_vs_saved"]["max_row"] == (0 if wider else None)
    assert result["full_longdouble_recompose_vs_saved"]["longdouble_is_wider_than_float64"] == wider


def test_v8_sparse_selected_row_projection_and_original_order_delta_t_are_explicit():
    from src.runners.task41_p0_v4_volume_only_audit import (
        _v8_selected_row_vdot,
        _v8_replay_selected_row_rhs_split,
        _v8_sum_selected_row_cell_terms,
    )

    weights = np.asarray([0.0, 0.25 + 0.75j, 0.0, -0.5j], dtype=np.complex128)
    vector = np.asarray([100.0, 2.0 - 3.0j, -5.0, 4.0 + 2.0j], dtype=np.complex128)
    np.testing.assert_allclose(
        _v8_selected_row_vdot(weights, vector, np.asarray([1, 3])),
        np.vdot(weights[[1, 3]], vector[[1, 3]]),
    )

    cell_contributions = {}
    for cell, delta in ((10, 1.0e16), (11, 1.0)):
        float_terms = {
            name: (delta if name == "delta_t" else 0.0 + 0.0j)
            for name in ("s", "rhs_i", "T_r_i", "delta_t", "Q", "Q_regrouped")
        }
        wide_terms = {
            name: (
                np.longdouble(float_terms[name].real),
                np.longdouble(float_terms[name].imag),
            )
            for name in float_terms
        }
        cell_contributions[(cell, 0, "j0", "candidate")] = {
            "float": float_terms,
            "wide": wide_terms,
        }
    replay = _v8_sum_selected_row_cell_terms(
        cell_contributions,
        column_index=0,
        state_label="j0",
        role="candidate",
        cell_order=(10, 11),
        native_trace=1.0e16,
    )
    assert replay["float64_complex128"]["delta_t"] == 1.0
    assert replay["delta_t_sum_then_subtract_diagnostic"] == 0.0

    split = _v8_replay_selected_row_rhs_split(
        s_volume=7.0 + 1.0j,
        reduced_rhs_i=2.0 - 0.5j,
        native_volume_rhs_t=3.0 + 0.2j,
        native_full_rhs_t=3.25 + 0.2j,
        native_volume_action_t=1.5 - 0.1j,
        b_alpha_t=0.25 + 0.0j,
    )
    np.testing.assert_allclose(split["s_full"], 7.25 + 1.0j, rtol=0.0, atol=1.0e-15)
    np.testing.assert_allclose(split["g_full"], 5.25 - 0.3j, rtol=0.0, atol=1.0e-15)
    np.testing.assert_allclose(split["r_full"], 1.5 + 0.3j, rtol=0.0, atol=1.0e-15)


def test_v8_checker_replays_saved_complex_local_vectors_and_reports_defects_only():
    from src.runners.task41_p0_checker import (
        _task41_v8_complex_pairs,
        _task41_v8_local_matrix_defect_diagnostic,
        _task41_v8_local_p3_replay,
    )
    import pytest

    tensor = np.asarray(
        [
            [4.0 + 0.2j, 0.3, 0.2j, -0.1],
            [0.1j, 3.0 - 0.1j, 0.4, 0.2j],
            [0.7, -0.3j, 2.0 + 0.1j, 0.5],
            [0.2j, 0.6, -0.1, 1.5 - 0.2j],
        ],
        dtype=np.complex128,
    )
    interior = np.asarray([0, 2])
    trace = np.asarray([1, 3])
    R = np.asarray([[0.2 + 0.1j, -0.3], [0.4j, 0.1 - 0.2j]], dtype=np.complex128)
    T = np.asarray([[0.1 - 0.2j, 0.3j], [-0.1, 0.25 + 0.1j]], dtype=np.complex128)
    S = np.asarray([[1.2 + 0.1j, 0.2], [-0.3j, 0.9 - 0.2j]], dtype=np.complex128)
    u_i = np.asarray([0.5 + 0.25j, -0.4j])
    t_c = np.asarray([1.0 - 0.5j, 0.2 + 0.8j])
    b_i = np.asarray([0.3j, 1.2 - 0.1j])
    n_i = np.asarray([-0.1 + 0.2j, 0.7j])
    # This nested pair shape matches the saved V8 JSON field. Its non-real
    # value exercises the Hermitian row product after decoding.
    assert _task41_v8_complex_pairs([[1.0, 0.0]], "saved selector").shape == (1,)
    coefficients = _task41_v8_complex_pairs(
        [[0.3, 0.6]], "selected trace coefficients"
    )
    assert coefficients.shape == (1,)
    assert coefficients[0] == complex(0.3, 0.6)
    arrays, scalars = _task41_v8_local_p3_replay(
        tensor=tensor,
        interior_positions=interior,
        trace_positions=trace,
        R=R,
        T=T,
        S=S,
        u_i=u_i,
        t_c=t_c,
        b_i=b_i,
        n_i=n_i,
        selected_local_rows=np.asarray([1]),
        selected_coefficients=coefficients,
    )
    K = tensor[np.ix_(interior, interior)]
    G = tensor[np.ix_(interior, trace)]
    J = tensor[np.ix_(trace, interior)]
    L = tensor[np.ix_(trace, trace)]
    actual_t = J @ u_i + L @ t_c
    expected_delta = np.vdot(coefficients, actual_t[[1]])
    np.testing.assert_allclose(arrays["delta_i"], K @ u_i + G @ t_c - n_i)
    np.testing.assert_allclose(scalars["delta_t"], expected_delta)
    np.testing.assert_allclose(
        scalars["Q"], np.vdot(coefficients, arrays["Q_local"][[1]])
    )
    np.testing.assert_allclose(
        arrays["Q_regrouped_local"], (S - L) @ t_c - J @ u_i - T @ n_i
    )

    defects = _task41_v8_local_matrix_defect_diagnostic(
        tensor=tensor,
        interior_positions=interior,
        trace_positions=trace,
        R=R,
        T=T,
        S=S,
    )
    assert defects["diagnostic_only"] is True
    assert defects["new_rejection_tolerance"] is None
    assert set(("E_R", "E_T", "C_S", "E_S", "E_S_identity_residual")) <= defects.keys()
    with pytest.raises(ValueError, match="real/imaginary pair"):
        _task41_v8_complex_pairs([[1.0, 0.0, 2.0]], "selected trace coefficients")


def test_v8_selected_scalar_replay_matches_p3_producer_schema():
    import pytest

    from src.runners.task41_p0_checker import (
        _task41_v8_check_selected_row_contributions,
    )

    scalars = {
        "s": 1.25 + 0.5j,
        "rhs_i": -0.25 + 0.75j,
        "T_r_i": 0.4 - 0.3j,
        "delta_t": -0.2 + 0.1j,
        "Q": 0.6 + 0.8j,
        "Q_regrouped": 0.5 - 0.9j,
    }

    def pair(value):
        return [value.real, value.imag]

    # This mirrors P3: projected_T_r_i is an array reference under
    # signed_action_artifacts; its selected value is already checked from
    # that array. selected_row_contributions only has the T_r_i scalar.
    contributions = {
        "S_action": pair(scalars["s"]),
        "local_reduced_rhs_T_b_i": pair(scalars["rhs_i"]),
        "T_r_i": pair(scalars["T_r_i"]),
        "delta_t_cell": pair(scalars["delta_t"]),
        "Q_cell": pair(scalars["Q"]),
        "Q_regrouped_cell": pair(scalars["Q_regrouped"]),
        "projected_actual_trace": pair(scalars["delta_t"]),
        "projected_Q": pair(scalars["Q"]),
        "projected_Q_regrouped": pair(scalars["Q_regrouped"]),
    }
    signed_action_artifacts = {
        "projected_T_r_i": {
            "path": "projected_T_r_i.npy",
            "shape": [4],
            "dtype": "complex128",
        }
    }

    assert "projected_T_r_i" not in contributions
    assert "projected_T_r_i" in signed_action_artifacts
    _task41_v8_check_selected_row_contributions(
        contributions, scalars, "fixture cell"
    )
    wrong_scalar = dict(contributions, T_r_i=[0.0, 0.0])
    with pytest.raises(ValueError, match="T_r_i"):
        _task41_v8_check_selected_row_contributions(
            wrong_scalar, scalars, "fixture cell"
        )


def test_v8_rhs_counterfactual_uses_original_full_storage_row_once():
    from src.runners.task41_p0_checker import (
        _task41_v8_lu_rhs_counterfactual,
        _task41_v8_lu_rhs_totals,
    )
    from src.solvers.hcurl_assembly_time_condensation import _strict_local_lu

    K = np.asarray(
        [[3.0 + 0.2j, 0.1 - 0.3j], [0.4j, 2.0 - 0.1j]],
        dtype=np.complex128,
    )
    J = np.asarray([[0.7 + 0.2j, -0.1 + 0.3j]], dtype=np.complex128)
    b_i = np.asarray([0.5 - 0.4j, 0.2 + 0.6j], dtype=np.complex128)
    T = -J @ np.linalg.solve(K, np.eye(2, dtype=np.complex128)) + np.asarray(
        [[1.0e-4 - 2.0e-4j, -3.0e-4 + 1.0e-4j]], dtype=np.complex128
    )
    lu, _ = _strict_local_lu(K)
    local = _task41_v8_lu_rhs_counterfactual(
        K=K,
        J=J,
        T=T,
        b_i=b_i,
        factor=lu,
        selected_local_rows=np.asarray([0]),
        selected_coefficients=np.asarray([1.0 + 0.0j]),
    )
    expected_old = T @ b_i
    expected_solution = np.linalg.solve(K, b_i)
    expected_new = -(J @ expected_solution)
    np.testing.assert_allclose(
        local["old_T_b_i_projected"], [expected_old[0].real, expected_old[0].imag]
    )
    np.testing.assert_allclose(
        local["new_minus_J_solve_K_b_i_projected"],
        [expected_new[0].real, expected_new[0].imag],
    )
    np.testing.assert_allclose(
        local["_residual_array"], K @ local["_solution_array"] - b_i
    )
    assert local["solve_residual_norm"] >= 0.0
    assert local["solve_residual_rhs_norm"] == np.linalg.norm(b_i)
    assert local["solve_solution_norm"] == np.linalg.norm(local["_solution_array"])
    assert local["solve_backward_residual_scale"] > 0.0

    native_volume_rhs = np.asarray(
        [10 + 1j, 20 + 2j, 30 + 3j, 40 + 4j, 50 + 5j],
        dtype=np.complex128,
    )
    result = _task41_v8_lu_rhs_totals(
        native_volume_rhs=native_volume_rhs,
        selected_active_row=1,
        selected_original_row=4,
        selected_S_sum=9 + 1j,
        old_local_rhs_sum=2 + 2j,
        new_local_rhs_sum=3 + 4j,
    )

    assert result["selected_active_row"] == 1
    assert result["selected_original_row"] == 4
    assert result["original_b_t_added_once"] == [50.0, 5.0]
    assert result["g_old_b_t_plus_T_b_i"] == [52.0, 7.0]
    assert result["g_new_b_t_plus_direct_minus_J_solve_K_b_i"] == [53.0, 9.0]
    assert result["d_old_S_minus_g_old"] == [-43.0, -6.0]
    assert result["d_new_S_minus_g_new"] == [-44.0, -8.0]


def test_v8_legacy_missing_checker_field_is_exact_hash_and_identity_bound():
    from src.runners.task41_p0_checker import (
        TASK41_P0_V8_LEGACY_CONSUMER_CONTRACT_SHA256,
        TASK41_P0_V8_LEGACY_CONSUMER_SOURCE_SHA,
        TASK41_P0_V8_LEGACY_REPORT_SHA256,
        TASK41_P0_V8_SELECTED_TRACE_STAR_REPORT_SCHEMA,
        _task41_v8_report_independent_checker_status,
    )

    assert TASK41_P0_V8_LEGACY_REPORT_SHA256 == (
        "1bdd07ac38bce95d58a153bacdca0de6cf5941d08d2706dc127e8b00d8e2764f"
    )
    assert len(TASK41_P0_V8_LEGACY_REPORT_SHA256) == 64
    report = {
        "schema": TASK41_P0_V8_SELECTED_TRACE_STAR_REPORT_SCHEMA,
        "status": "COMPLETED_SELECTED_TRACE_STAR_AUDIT",
        "geometry_policy": "mesh_actual_exact",
        "raw_tensor_evaluator": "actual_qmetric_blocked_gram",
        "consumer_source_sha": TASK41_P0_V8_LEGACY_CONSUMER_SOURCE_SHA,
        "consumer_contract_sha256": TASK41_P0_V8_LEGACY_CONSUMER_CONTRACT_SHA256,
    }
    assert _task41_v8_report_independent_checker_status(
        report, expected_report_sha256=TASK41_P0_V8_LEGACY_REPORT_SHA256
    ) == "NOT_RUN"
    assert _task41_v8_report_independent_checker_status(
        report, expected_report_sha256="0" * 64
    ) is None
    for key, value in (
        ("consumer_source_sha", "0" * 40),
        ("consumer_contract_sha256", "0" * 64),
        ("schema", "task41.p0.v8.other_receipt.v1"),
        ("independent_checker_status", "PASS"),
    ):
        tampered = {**report, key: value}
        assert _task41_v8_report_independent_checker_status(
            tampered, expected_report_sha256=TASK41_P0_V8_LEGACY_REPORT_SHA256
        ) is None


def test_v8_ordered_summary_keeps_grouped_left_distinct_from_closure():
    import pytest

    from src.runners.task41_p0_checker import (
        _task41_v8_check_ordered_summary_closures,
    )

    left_volume = 1.25 - 0.75j
    left_full = -0.5 + 1.5j
    right_attribution = 0.4 - 0.25j
    closure_volume = left_volume - right_attribution
    closure_full = left_full - right_attribution
    replay = {
        "v7_grouped_left_volume": [left_volume.real, left_volume.imag],
        "v7_grouped_left_full": [left_full.real, left_full.imag],
    }
    comparisons = {
        "star_corrected_volume_closure": [closure_volume.real, closure_volume.imag],
        "star_corrected_full_closure": [closure_full.real, closure_full.imag],
    }

    candidate = _task41_v8_check_ordered_summary_closures(
        replay=replay,
        expected_left_volume=left_volume,
        expected_left_full=left_full,
        expected_closure_volume=closure_volume,
        expected_closure_full=closure_full,
        comparisons=comparisons,
        role="candidate",
        label="fixture",
    )
    assert candidate["closure_comparison"] == "MATCHED_SAVED_CANDIDATE_CORRECTED_CLOSURES"
    assert candidate["v7_grouped_left_volume"] == [left_volume.real, left_volume.imag]
    assert candidate["recomputed_closure_volume"] == [closure_volume.real, closure_volume.imag]

    wrong_binding = {
        **comparisons,
        "star_corrected_volume_closure": [left_volume.real, left_volume.imag],
        "star_corrected_full_closure": [left_full.real, left_full.imag],
    }
    with pytest.raises(ValueError, match="star_corrected_volume_closure"):
        _task41_v8_check_ordered_summary_closures(
            replay=replay,
            expected_left_volume=left_volume,
            expected_left_full=left_full,
            expected_closure_volume=closure_volume,
            expected_closure_full=closure_full,
            comparisons=wrong_binding,
            role="candidate",
            label="fixture",
        )

    reference = _task41_v8_check_ordered_summary_closures(
        replay=replay,
        expected_left_volume=left_volume,
        expected_left_full=left_full,
        expected_closure_volume=closure_volume,
        expected_closure_full=closure_full,
        comparisons=None,
        role="reference",
        label="fixture",
    )
    assert (
        reference["closure_comparison"]
        == "REFERENCE_CLOSURES_RECOMPUTED_NO_SAVED_REFERENCE_CLOSURE"
    )
    assert reference["recomputed_closure_full"] == [closure_full.real, closure_full.imag]


def test_v9_signed_saved_lu_identity_uses_complex_mpc_and_selected_rows():
    from src.runners.task41_p0_checker import _task41_v9_signed_local_identity

    K = np.asarray(
        [[2.0 + 0.3j, 0.2 + 0.8j], [-0.4 + 0.1j, 1.7 - 0.2j]],
        dtype=np.complex128,
    )
    J = np.asarray(
        [[0.3 + 0.5j, -0.7 + 0.2j], [0.1 - 0.4j, 0.8 + 0.1j],
         [-0.2 + 0.9j, 0.4 - 0.6j]],
        dtype=np.complex128,
    )
    T = np.asarray(
        [[0.6 - 0.1j, 0.2 + 0.7j], [-0.3 + 0.8j, 0.5 + 0.1j],
         [0.9 + 0.2j, -0.4 + 0.3j]],
        dtype=np.complex128,
    )
    b_i = np.asarray([0.8 - 0.2j, -0.5 + 0.7j], dtype=np.complex128)
    z = np.linalg.solve(K, b_i) + np.asarray([2.0e-5 - 3.0e-5j, -1.0e-5 + 4.0e-5j])
    rows = np.asarray([0, 2], dtype=np.int64)
    coefficients = np.asarray([0.5 + 0.8j, -0.3 + 0.4j], dtype=np.complex128)

    result = _task41_v9_signed_local_identity(
        K=K,
        J=J,
        T=T,
        b_i=b_i,
        z=z,
        selected_local_rows=rows,
        selected_coefficients=coefficients,
    )

    selected_T_b_i = T[rows, :] @ b_i
    selected_J_z = J[rows, :] @ z
    selected_E_T = J[rows, :] + T[rows, :] @ K
    selected_E_T_z = selected_E_T @ z
    selected_reassociated = selected_J_z + T[rows, :] @ (K @ z)
    selected_T_residual = T[rows, :] @ (b_i - K @ z)
    signed_lhs = np.vdot(coefficients, selected_T_b_i + selected_J_z)
    signed_rhs = np.vdot(coefficients, selected_E_T_z + selected_T_residual)

    assert result["projected_T_b_i"] == pytest.approx(np.vdot(coefficients, selected_T_b_i))
    assert result["projected_J_z"] == pytest.approx(np.vdot(coefficients, selected_J_z))
    assert result["projected_(J+TK)_z"] == pytest.approx(
        np.vdot(coefficients, selected_E_T_z)
    )
    assert result["projected_reassociated_Jz_plus_TKz"] == pytest.approx(
        np.vdot(coefficients, selected_reassociated)
    )
    assert result["projected_T_(b_i-Kz)"] == pytest.approx(
        np.vdot(coefficients, selected_T_residual)
    )
    assert result["projected_signed_lhs"] == pytest.approx(signed_lhs)
    assert result["projected_signed_rhs"] == pytest.approx(signed_rhs)
    assert result["projection_identity_remainder"] == pytest.approx(signed_lhs - signed_rhs)
    assert result["projection_reassociation_difference"] == pytest.approx(
        np.vdot(coefficients, selected_reassociated)
        - np.vdot(coefficients, selected_E_T_z)
    )
    assert abs(signed_lhs - np.dot(coefficients, selected_T_b_i + selected_J_z)) > 1.0e-3


def test_v9_saved_star_candidate_own_d_gate_uses_both_columns_and_paired_states():
    from src.runners.task41_p0_checker import (
        _task41_v9_classify_candidate_self_d,
        _task41_v9_wide_local_projection,
        _task41_v9_wide_local_rhs_totals,
    )

    matrix = np.asarray(
        [[1.2 + 0.4j, -0.3 + 0.8j], [0.7 - 0.2j, 1.5 + 0.1j]],
        dtype=np.complex128,
    )
    vector = np.asarray([0.4 - 0.6j, 0.2 + 0.3j], dtype=np.complex128)
    projection = _task41_v9_wide_local_projection(
        matrix,
        vector,
        selected_local_rows=np.asarray([0, 1]),
        selected_coefficients=np.asarray([0.3 + 0.6j, -0.2 + 0.5j]),
    )
    expected = np.vdot(
        np.asarray([0.3 + 0.6j, -0.2 + 0.5j]), matrix @ vector
    )
    np.testing.assert_allclose(
        complex(float(projection[0]), float(projection[1])), expected,
        rtol=1.0e-15, atol=1.0e-15,
    )
    totals = _task41_v9_wide_local_rhs_totals(
        native_volume_rhs_at_selected_row=2.0 + 0.5j,
        wide_s_sum=(np.longdouble(1.0), np.longdouble(-0.5)),
        wide_old_local_rhs_sum=(np.longdouble(-0.25), np.longdouble(0.1)),
        wide_new_local_rhs_sum=(np.longdouble(-0.5), np.longdouble(0.2)),
    )
    assert totals["wide_g_old_b_t_plus_T_b_i"] == [1.75, 0.6]
    assert totals["wide_d_old_S_minus_g_old"] == [-0.75, -1.1]
    assert totals["wide_g_new_b_t_plus_direct_minus_J_solve_K_b_i"] == [1.5, 0.7]

    cases = []
    for role in ("candidate", "reference"):
        for column in range(2):
            for state in ("j0", "j3"):
                scale = 1.0 if role == "candidate" else 12.0
                old = scale + 0.2j
                new = (0.45 * scale) + 0.1j if role == "candidate" else scale + 0.2j
                cases.append(
                    {
                        "role": role,
                        "column": column,
                        "state": state,
                        "d_old_S_minus_g_old": [old.real, old.imag],
                        "d_new_S_minus_g_new": [new.real, new.imag],
                        "wide_d_old_S_minus_g_old": [old.real + 1.0e-5, old.imag],
                        "wide_d_new_S_minus_g_new": [new.real + 1.0e-5, new.imag],
                    }
                )

    ready = _task41_v9_classify_candidate_self_d(
        cases,
        identity_replay_closed=True,
        production_core_replay_closed=True,
    )
    assert ready["status"] == "LOCAL_CANDIDATE_READY"
    assert len(ready["candidate_and_reference_own_d"]) == 8
    assert all(gate["passed"] for gate in ready["candidate_column_gates"])
    assert all(
        item["role"] == "reference" or item["improvement_beyond_last_combination_uncertainty"]
        for item in ready["candidate_and_reference_own_d"]
    )

    rejected_cases = [dict(item) for item in cases]
    failed = next(
        item
        for item in rejected_cases
        if item["role"] == "candidate" and item["column"] == 1 and item["state"] == "j3"
    )
    failed["d_new_S_minus_g_new"] = failed["d_old_S_minus_g_old"]
    failed["wide_d_new_S_minus_g_new"] = failed["wide_d_old_S_minus_g_old"]
    rejected = _task41_v9_classify_candidate_self_d(
        rejected_cases,
        identity_replay_closed=True,
        production_core_replay_closed=True,
    )
    assert rejected["status"] == "LOCAL_CANDIDATE_REJECTED"
    assert [gate["passed"] for gate in rejected["candidate_column_gates"]] == [True, False]


def test_v9_saved_star_screen_reopens_pinned_lu_arrays_without_refactor(tmp_path, monkeypatch):
    from scipy.linalg import lu_factor, lu_solve
    import pytest
    from src.runners import task41_p0_checker as checker

    root = tmp_path
    results = root / "results"
    report_dir = results / "v8_selected_star"
    checker_dir = results / "v8_saved_checker"
    source_arrays = report_dir / "arrays"
    checker_arrays = checker_dir / "arrays"
    source_arrays.mkdir(parents=True)
    checker_arrays.mkdir(parents=True)
    source_inventory = []
    checker_inventory = []

    def save_array(directory, inventory, name, value, kind):
        path = directory / f"{name}.npy"
        np.save(path, np.asarray(value), allow_pickle=False)
        item = {
            "name": name,
            "path": str(path),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
            "dtype": str(np.load(path, allow_pickle=False).dtype),
            "shape": list(np.load(path, allow_pickle=False).shape),
            "kind": kind,
        }
        inventory.append(item)
        return item

    cells = (23352, 23493)
    roles = ("candidate", "reference")
    states = ("j0", "j3")
    numeric_cells = []
    p3_cells = []
    factorizations = []
    checker_terms = {(role, column, state): [] for role in roles for column in range(2) for state in states}
    tensors = {}
    matrices = {}
    factors = {}
    b_i_values = {}
    b_t_by_column = {0: 0.1 - 0.05j, 1: -0.2 + 0.08j}

    for cell_offset, cell in enumerate(cells):
        role_rows = []
        for role_offset, role in enumerate(roles):
            K = np.asarray(
                [[3.0 + 0.1j * role_offset, 0.2 - 0.05j], [0.1j, 2.0 + 0.2j * cell_offset]],
                dtype=np.complex128,
            )
            J = np.asarray([[0.4 + 0.1j * role_offset, -0.15 + 0.03j]], dtype=np.complex128)
            T = np.zeros((1, 2), dtype=np.complex128)
            S = np.ones((1, 1), dtype=np.complex128)
            tensor = np.zeros((3, 3), dtype=np.complex128)
            tensor[:2, :2] = K
            tensor[2:, :2] = J
            tensor[:2, 2:] = np.asarray([[0.1 + 0.02j], [-0.04j]])
            tensor[2, 2] = 1.3 + 0.1j
            tensor_ref = save_array(
                source_arrays, source_inventory,
                f"cell{cell}_{role}_oriented_tensor", tensor, "oriented_tensor",
            )
            T_ref = save_array(source_arrays, source_inventory, f"cell{cell}_{role}_T", T, "T")
            S_ref = save_array(source_arrays, source_inventory, f"cell{cell}_{role}_S", S, "S")
            tensors[(cell, role)] = tensor
            matrices[(cell, role)] = (K, J, T, S)
            lu, pivots = lu_factor(K)
            factor_ref = save_array(
                checker_arrays, checker_inventory,
                f"lu_cell{cell}_{role}", lu, "LOCAL_LU_RECONSTRUCTED_FROM_SAVED_TENSOR",
            )
            pivot_ref = save_array(
                checker_arrays, checker_inventory,
                f"lu_cell{cell}_{role}_pivots", pivots.astype(np.int32), "LOCAL_LU_PIVOTS",
            )
            factors[(cell, role)] = (lu, pivots)
            factorizations.append(
                {
                    "cell_index": cell,
                    "role": role,
                    "factorization_identity": "fresh _strict_local_lu(K) from saved oriented_tensor; reused for both columns and states",
                    "K_sha256": hashlib.sha256(np.ascontiguousarray(K).view(np.uint8)).hexdigest(),
                    "oriented_tensor_sha256": tensor_ref["sha256"],
                    "saved_T_sha256": T_ref["sha256"],
                    "lu_factor_artifact": factor_ref,
                    "owned_pivots_artifact": pivot_ref,
                }
            )
            role_rows.append(
                {
                    "role": role,
                    "producer_identity": "task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1" if role == "candidate" else "original_ffcx_reference_kernel",
                    "raw_oriented_RTS_artifacts": {
                        "oriented_tensor": tensor_ref,
                        "T": T_ref,
                        "S": S_ref,
                    },
                }
            )

        numeric_cells.append(
            {
                "cell_index": cell,
                "true_interior_positions": [0, 1],
                "trace_complement_positions": [2],
                "selected_local_trace_rows": [0],
                "selected_trace_coefficients": [[1.0, 0.0]],
                "roles": role_rows,
            }
        )
        state_rows = []
        for column in range(2):
            for state in states:
                p3_roles = []
                for role in roles:
                    K, J, T, S = matrices[(cell, role)]
                    b_i = np.asarray([1.0 + 0.2j * column, -0.4 + 0.3j * cell_offset], dtype=np.complex128)
                    z = lu_solve(factors[(cell, role)], b_i)
                    b_i_values[(cell, role, column, state)] = b_i
                    if role == "candidate":
                        t_c = np.asarray([b_t_by_column[column] - (J @ z)[0]], dtype=np.complex128)
                    else:
                        t_c = np.asarray([b_t_by_column[column]], dtype=np.complex128)
                    b_ref = save_array(
                        source_arrays, source_inventory,
                        f"cell{cell}_{role}_col{column}_{state}_b_i", b_i, "b_i",
                    )
                    t_ref = save_array(
                        source_arrays, source_inventory,
                        f"cell{cell}_{role}_col{column}_{state}_t_c", t_c, "t_c",
                    )
                    old = complex(np.vdot(np.asarray([1.0 + 0.0j]), T @ b_i))
                    s_term = complex(np.vdot(np.asarray([1.0 + 0.0j]), S @ t_c))
                    new = complex(np.vdot(np.asarray([1.0 + 0.0j]), -(J @ z)))
                    p3_roles.append(
                        {
                            "role": role,
                            "local_values": {"b_i": b_ref, "t_c": t_ref},
                            "selected_row_contributions": {
                            "T_r_i": [1.0e-8, -2.0e-8],
                            "local_reduced_rhs_T_b_i": [old.real, old.imag],
                                "S_action": [s_term.real, s_term.imag],
                            },
                        }
                    )
                    checker_terms[(role, column, state)].append(
                        {
                            "cell_index": cell,
                            "old_T_b_i_projected": [old.real, old.imag],
                            "new_minus_J_solve_K_b_i_projected": [new.real, new.imag],
                        }
                    )
                bt = b_t_by_column[column]
                state_rows.append(
                    {
                        "column": column,
                        "state": state,
                        "native_volume_rhs_at_selected_original_row": [bt.real, bt.imag],
                        "roles": p3_roles,
                    }
                )
        p3_cells.append({"cell_index": cell, "roles_and_states": state_rows})

    report = {
        "schema": "task41.p0.v8.selected_trace_star_audit_receipt.v1",
        "status": "COMPLETED_SELECTED_TRACE_STAR_AUDIT",
        "geometry_policy": "mesh_actual_exact",
        "raw_tensor_evaluator": "actual_qmetric_blocked_gram",
        "consumer_source_sha": checker.TASK41_P0_V8_LEGACY_CONSUMER_SOURCE_SHA,
        "consumer_contract_sha256": checker.TASK41_P0_V8_LEGACY_CONSUMER_CONTRACT_SHA256,
        "persisted_evidence_arrays": source_inventory,
        "selected_trace_star_audit": {
            "selected_active_row": 4_766_937,
            "selected_original_row": 15_440_235,
            "candidate_identity": "task41extra_actual_qmetric_blocked_gram_ffcx_profile_v1",
            "metadata": {"incident_cell_order": list(cells)},
            "local_numeric_cell_identity_and_artifacts": numeric_cells,
            "p3_production_row_replay": {
                "per_cell_signed_contributions": p3_cells,
            },
        },
    }
    report_path = report_dir / "task41_v8_selected_star.json"
    report_path.write_text(json.dumps(report, sort_keys=True))
    report_sha = hashlib.sha256(report_path.read_bytes()).hexdigest()

    for role in roles:
        for column in range(2):
            for state in states:
                local = []
                bt = b_t_by_column[column]
                for cell in cells:
                    K, J, _T, _S = matrices[(cell, role)]
                    b_i = b_i_values[(cell, role, column, state)]
                    z = lu_solve(factors[(cell, role)], b_i)
                    residual = K @ z - b_i
                    z_ref = save_array(
                        checker_arrays, checker_inventory,
                        f"v8_lu_solve_cell{cell}_{role}_col{column}_solution", z, "LOCAL_LU_SOLUTION",
                    ) if state == "j0" else next(
                        item for item in checker_inventory
                        if item["name"] == f"v8_lu_solve_cell{cell}_{role}_col{column}_solution"
                    )
                    _residual_ref = save_array(
                        checker_arrays, checker_inventory,
                        f"v8_lu_solve_cell{cell}_{role}_col{column}_residual", residual, "LOCAL_LU_SOLVE_RESIDUAL",
                    ) if state == "j0" else next(
                        item for item in checker_inventory
                        if item["name"] == f"v8_lu_solve_cell{cell}_{role}_col{column}_residual"
                    )
                    term = checker_terms[(role, column, state)][cells.index(cell)]
                    local.append(term)
                s_sum = sum(
                    complex(*next(
                        item["selected_row_contributions"]["S_action"]
                        for p3 in p3_cells if p3["cell_index"] == cell
                        for state_row in p3["roles_and_states"]
                        if state_row["column"] == column and state_row["state"] == state
                        for item in state_row["roles"] if item["role"] == role
                    ))
                    for cell in cells
                )
                old_sum = sum(complex(*item["old_T_b_i_projected"]) for item in local)
                new_sum = sum(complex(*item["new_minus_J_solve_K_b_i_projected"]) for item in local)
                g_old = bt + old_sum
                g_new = bt + new_sum
                d_old = s_sum - g_old
                d_new = s_sum - g_new
                checker_terms[(role, column, state)] = local
                if state == "j0":
                    checker_terms[(role, column, state)] = {
                        "cell_terms": local,
                        "d_old": [d_old.real, d_old.imag],
                        "d_new": [d_new.real, d_new.imag],
                    }
                else:
                    checker_terms[(role, column, state)] = {
                        "cell_terms": local,
                        "d_old": [d_old.real, d_old.imag],
                        "d_new": [d_new.real, d_new.imag],
                    }

    cases = []
    for role in roles:
        for column in range(2):
            for state in states:
                data = checker_terms[(role, column, state)]
                cases.append(
                    {
                        "role": role,
                        "column": column,
                        "state": state,
                        "d_old_S_minus_g_old": data["d_old"],
                        "d_new_S_minus_g_new": data["d_new"],
                        "cell_terms": data["cell_terms"],
                    }
                )
    checker_result = {
        "schema": "task41.p0.b0.saved_evidence_audit.v1",
        "status": "COMPLETE",
        "mesh_actual_exact_candidate_check": {
            "check_completed": True,
            "report_sha256_rechecked": report_sha,
            "local_rhs_lu_counterfactual": {
                "schema": "task41.p0.v8.local_rhs_lu_counterfactual.v1",
                "source_report_sha256_rechecked": report_sha,
                "new_strict_lu_factorization_count": 4,
                "direct_rhs_solve_count": 8,
                "factorizations": factorizations,
                "array_artifacts": checker_inventory,
                "cases": cases,
            },
        },
    }
    checker_path = checker_dir / "task41_v8_saved_checker_result.json"
    checker_path.write_text(json.dumps(checker_result, sort_keys=True))
    checker_sha = hashlib.sha256(checker_path.read_bytes()).hexdigest()
    saved_d_by_key = {
        (item["role"], item["column"], item["state"]): (
            item["d_old_S_minus_g_old"],
            item["d_new_S_minus_g_new"],
        )
        for item in cases
    }
    monkeypatch.setattr(checker, "TASK41_P0_V9_V8_REPORT_SHA256", report_sha)
    monkeypatch.setattr(checker, "TASK41_P0_V9_V8_CHECKER_RESULT_SHA256", checker_sha)
    original_signed_identity = checker._task41_v9_signed_local_identity
    diagnostic_bias = 0.25 + 0.5j

    def biased_diagnostic_only_identity(**kwargs):
        result = original_signed_identity(**kwargs)
        return {name: value + diagnostic_bias for name, value in result.items()}

    monkeypatch.setattr(
        checker,
        "_task41_v9_signed_local_identity",
        biased_diagnostic_only_identity,
    )

    result = checker.task41_p0_v9_saved_star_screen(
        v8_report_path=report_path,
        v8_report_sha256=report_sha,
        v8_checker_result_path=checker_path,
        v8_checker_result_sha256=checker_sha,
        repo_root=root,
    )
    assert result["status"] == "LOCAL_CANDIDATE_READY"
    assert result["replay_checks"]["production_core_GETRS_count"] == 8
    assert result["replay_checks"]["old_original_path_and_V8_d_replayed_check_count"] == 64
    assert result["replay_checks"]["wide_local_projection_recompute_is_diagnostic_only"] is True
    assert all(gate["passed"] for gate in result["candidate_column_gates"])
    assert len(result["candidate_and_reference_recomputed_s_g_d"]) == 8
    for case in result["candidate_and_reference_recomputed_s_g_d"]:
        saved_d = saved_d_by_key[(case["role"], case["column"], case["state"])]
        assert case["d_T_complex128"] == saved_d[0]
        assert case["d_LU_complex128"] == saved_d[1]
        b_t = complex(*case["original_b_t_added_once"])
        cells = case["cell_terms"]
        sum_t_b_i = sum(
            complex(*cell["T_b_i_projected_complex128"]) for cell in cells
        )
        sum_minus_j_z = sum(
            complex(*cell["minus_J_z_projected_complex128"]) for cell in cells
        )
        assert complex(*case["g_T_complex128"]) == pytest.approx(b_t + sum_t_b_i)
        assert complex(*case["g_LU_complex128"]) == pytest.approx(b_t + sum_minus_j_z)
        assert all(
            cell["signed_saved_lu_identity_projection"]["formula"]
            == "T b_i + J z = (J + T K) z + T (b_i - K z)"
            for cell in cells
        )
        assert all(
            complex(
                *cell["selected_row_vs_full_matvec_projection_remainders"][
                    "E_H_T_b_i_selected_minus_full"
                ]
            )
            == pytest.approx(diagnostic_bias)
            for cell in cells
        )
        diagnostic = case["signed_d_LU_minus_d_T_identity_diagnostic"]
        direct = complex(*diagnostic["direct_d_LU_minus_d_T_complex128"])
        accurate = complex(*diagnostic["accurate_sum_of_rounded_signed_E_H_terms"])
        remainder = complex(
            *diagnostic["fpu_remainder_direct_minus_accurate_projection_sum"]
        )
        assert accurate == pytest.approx(
            sum_t_b_i - sum_minus_j_z + 4 * diagnostic_bias
        )
        assert direct == pytest.approx(
            complex(*case["d_LU_complex128"])
            - complex(*case["d_T_complex128"])
        )
        assert remainder == pytest.approx(direct - accurate)
        assert diagnostic["diagnostic_only_not_used_for_gate"] is True

    corrupted = bytearray(checker_path.read_bytes())
    corrupted[-2] ^= 1
    checker_path.write_bytes(corrupted)
    with pytest.raises(ValueError, match="frozen SHA-256 differs"):
        checker.task41_p0_v9_saved_star_screen(
            v8_report_path=report_path,
            v8_report_sha256=report_sha,
            v8_checker_result_path=checker_path,
            v8_checker_result_sha256=checker_sha,
            repo_root=root,
        )


def test_v9_saved_star_screen_contract_wrapper_is_local_only_and_persists_result(
    tmp_path, monkeypatch
):
    from src.runners import task41_p0_checker as checker
    from src.runners.task41_p0_contract import TASK41_B0_V9_WINDOW_RELATIVE

    root = tmp_path.resolve()
    contract_path = root / "contract.json"
    contract_path.write_text("{}\n", encoding="utf-8")
    output_path = root / "results" / "v9_screen.json"
    contract = {
        "task_id": "task41extra_phi90_p50x50_g17x20",
        "case": {"run_id": "task41extra_b0_p6_phi90_07nm_iterative"},
        "source": {"sha": "c" * 40},
        "window": {
            "path": str(TASK41_B0_V9_WINDOW_RELATIVE),
            "sha256": "d" * 64,
        },
        "numerical_strategy": {
            "schema": "task41.p0.b0.internal_rhs_strategy.v1",
            "internal_rhs_strategy": "same_lu_rhs_solve",
        },
    }
    monkeypatch.setattr(
        checker,
        "require_task41_p0_contract",
        lambda *_args, **_kwargs: (contract, "e" * 64),
    )
    monkeypatch.setattr(
        checker,
        "task41_p0_v9_saved_star_screen",
        lambda **_kwargs: {
            "schema": "task41.p0.v9.saved_star_screen.v1",
            "status": "LOCAL_CANDIDATE_READY",
        },
    )
    result = checker.check_task41_p0_b0_v9_saved_star_screen(
        contract_path=contract_path,
        contract_sha256="f" * 64,
        v8_report_path=root / "results/v8.json",
        v8_report_sha256="1" * 64,
        v8_checker_result_path=root / "results/v8_checker.json",
        v8_checker_result_sha256="2" * 64,
        output_path=output_path,
        repo_root=root,
    )
    assert result["screen_completed"] is True
    assert result["local_candidate_ready"] is True
    assert result["official_result"] is False
    assert json.loads(output_path.read_text())["contract_sha256"] == "e" * 64
    with pytest.raises(ValueError, match="already exists"):
        checker.check_task41_p0_b0_v9_saved_star_screen(
            contract_path=contract_path,
            contract_sha256="f" * 64,
            v8_report_path=root / "results/v8.json",
            v8_report_sha256="1" * 64,
            v8_checker_result_path=root / "results/v8_checker.json",
            v8_checker_result_sha256="2" * 64,
            output_path=output_path,
            repo_root=root,
        )
