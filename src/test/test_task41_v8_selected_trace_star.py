import hashlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np

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
