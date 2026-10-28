from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from src.runners import task41_p0_v4_volume_only_audit as v17_worker
from src.runners.task41_p0_checker import (
    TASK41_P0_B0_V17_SELECTED_METADATA_RELATIVE,
    TASK41_P0_B0_V17_SELECTED_METADATA_SHA256,
    _task41_p0_b0_v17_accumulate_native_then_cells,
    _task41_p0_b0_v17_normalize_selected_metadata,
    load_task41_p0_b0_v17_selected_cell_metadata,
    task41_p0_b0_v17_signed_cell_identity,
    task41_p0_b0_v17_signed_two_cell_identity,
)
from src.runners.task41_p0_contract import (
    TASK41_B0_V17_SAVED_VECTOR_MANIFEST_RELATIVE,
    TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256,
    sha256_file,
)


def _metadata_path() -> Path:
    return Path(__file__).resolve().parents[2] / TASK41_P0_B0_V17_SELECTED_METADATA_RELATIVE


def test_v17_metadata_loader_binds_exact_source_and_uses_ordered_hex() -> None:
    normalized = load_task41_p0_b0_v17_selected_cell_metadata()
    source = json.loads(_metadata_path().read_text(encoding="utf-8"))

    assert normalized["source_metadata_sha256"] == TASK41_P0_B0_V17_SELECTED_METADATA_SHA256
    assert normalized["incident_cell_order"] == [7873, 8014]
    assert [cell["cell_id"] for cell in normalized["cells"]] == [7873, 8014]
    for cell, source_cell in zip(normalized["cells"], source["incident_cells"], strict=True):
        expected = np.asarray(
            [[float.fromhex(value) for value in row] for row in source_cell["coordinate_hex"]],
            dtype=np.float64,
        )
        np.testing.assert_array_equal(cell["coordinates"], expected)
        np.testing.assert_array_equal(cell["coordinates"], source_cell["coordinates"])


def test_v17_metadata_normalizer_does_not_use_sorted_actual_keys() -> None:
    source = json.loads(_metadata_path().read_text(encoding="utf-8"))
    source["incident_cells"][0]["actual_keys"] = list(
        reversed(source["incident_cells"][0]["actual_keys"])
    )

    normalized = _task41_p0_b0_v17_normalize_selected_metadata(source)

    expected = np.asarray(
        [[float.fromhex(value) for value in row] for row in source["incident_cells"][0]["coordinate_hex"]],
        dtype=np.float64,
    )
    np.testing.assert_array_equal(normalized["cells"][0]["coordinates"], expected)


def test_v17_metadata_rejects_wrong_hash_and_missing_cell_coverage() -> None:
    with pytest.raises(ValueError, match="size or SHA-256 differs"):
        load_task41_p0_b0_v17_selected_cell_metadata(
            expected_sha256="0" * 64
        )

    source = json.loads(_metadata_path().read_text(encoding="utf-8"))
    source["incident_cells"].pop()
    with pytest.raises(ValueError, match="incident-cell coverage differs"):
        _task41_p0_b0_v17_normalize_selected_metadata(source)


def test_v17_checker_preserves_native_then_cell_order_for_complex_cancellation() -> None:
    native = complex(1.0e16, 1.0e16)
    first_cell = complex(-1.0e16, -1.0e16)
    second_cell = complex(1.0, 2.0)

    production_order = _task41_p0_b0_v17_accumulate_native_then_cells(
        native, (first_cell, second_cell)
    )
    aggregate_then_native = native + (first_cell + second_cell)

    assert production_order == complex(1.0, 2.0)
    assert aggregate_then_native == 0.0 + 2.0j


def test_v17_v16_manifest_relative_path_is_under_model_results_root() -> None:
    expected = Path(
        "task41_p0_saved_diagnostics_6h/"
        "3d22e02f713c4a68c79759b2c5cb7cbcec693b7b3277ad98b529838008e38beb/"
        "saved_vector_distribution/attempt05.service/"
        "task41_p0_v16_metadata_bound_manifest.json"
    )
    assert v17_worker.TASK41_P0_V17_V16_MANIFEST_RELATIVE == expected
    assert (
        Path("results")
        / "task41extra_phi90_p50x50_g17x20"
        / v17_worker.TASK41_P0_V17_V16_MANIFEST_RELATIVE
    ) == TASK41_B0_V17_SAVED_VECTOR_MANIFEST_RELATIVE
    assert v17_worker.TASK41_P0_V17_V16_MANIFEST_SHA256 == (
        TASK41_B0_V17_SAVED_VECTOR_MANIFEST_SHA256
    )


def _wide_pair(pair: list[str]) -> np.clongdouble:
    return np.clongdouble(pair[0]) + np.clongdouble(1j) * np.clongdouble(pair[1])


def test_v17_two_cell_signed_identity_keeps_global_terms_and_widened_diagnostics() -> None:
    rng = np.random.default_rng(41)
    local_records = []
    for cell_id, perturb in ((7873, 1.0e-5j), (8014, -2.0e-5 + 1.0e-5j)):
        K = np.asarray(
            [[4.0 + 0.2j, 0.3 - 0.1j], [0.1 + 0.05j, 3.0 + 0.1j]],
            dtype=np.complex128,
        )
        G = np.asarray([[0.2 + 0.1j], [0.4 - 0.2j]], dtype=np.complex128)
        J = np.asarray([[0.1 - 0.2j, 0.3 + 0.1j]], dtype=np.complex128)
        L = np.asarray([[2.0 + 0.3j]], dtype=np.complex128)
        R = -np.linalg.solve(K, G)
        T = -J @ np.linalg.inv(K)
        T[0, 0] += perturb
        S = L + J @ R
        q = np.asarray([1.0 + 0.25j], dtype=np.complex128)
        u_i = np.asarray(
            rng.normal(size=2) + 1j * rng.normal(size=2), dtype=np.complex128
        )
        t_c = np.asarray([0.25 - 0.5j], dtype=np.complex128)
        b_i = np.asarray([0.2 + 0.1j, -0.4 + 0.3j], dtype=np.complex128)
        z_c = np.linalg.solve(K, b_i)
        cell = task41_p0_b0_v17_signed_cell_identity(
            K=K,
            G=G,
            J=J,
            L=L,
            R=R,
            T=T,
            S=S,
            q=q,
            u_i=u_i,
            t_c=t_c,
            b_i=b_i,
            z_c=z_c,
        )
        cell["cell_id"] = cell_id
        local_records.append(cell)

    assert all(cell["status"] == "DIAGNOSTIC_ONLY" for cell in local_records)
    assert all(cell["t_is_elementwise_zero"] is False for cell in local_records)
    for cell in local_records:
        assert "stored_value_terms" not in cell
        assert cell["independent_evaluation"]["wider_than_binary64"] is True
        assert cell["independent_evaluation"][
            "binary64_identity_is_not_stored_value_proof"
        ] is True
        assert cell["independent_evaluation"]["real_mantissa_bits"] > cell[
            "independent_evaluation"
        ]["binary64_mantissa_bits"]
        assert _wide_pair(
            cell["widened_evaluation_terms"]["e_lambda_H_w"]
        ) != np.clongdouble(0)

    observed_d = 0.75 - 0.2j
    result = task41_p0_b0_v17_signed_two_cell_identity(
        cells=local_records,
        b_t_volume=0.4 + 0.1j,
        b_t_full=0.9 - 0.2j,
        b_alpha_t=0.1 + 0.05j,
        observed_d=observed_d,
    )
    assert result["status"] == "DIAGNOSTIC_ONLY"
    assert result["cell_order"] == [7873, 8014]
    assert result["global_terms_subtracted_once"] is True
    assert result["evaluation_remainder_is_not_assigned_to_stored_terms"] is True
    terms = result["widened_evaluation_terms"]
    expected_sum = sum(
        (_wide_pair(cell["widened_evaluation_terms"]["local_delta_t"])
         for cell in local_records),
        np.clongdouble(0),
    )
    np.testing.assert_allclose(
        _wide_pair(terms["delta_t"]), expected_sum - np.clongdouble(0.4 + 0.1j),
        atol=np.clongdouble("1e-18"),
    )
    expected_epsilon = (
        np.clongdouble(0.9 - 0.2j)
        - np.clongdouble(0.4 + 0.1j)
        - np.clongdouble(0.1 + 0.05j)
    )
    np.testing.assert_allclose(
        _wide_pair(terms["epsilon_t"]), expected_epsilon,
        atol=np.clongdouble("1e-18"),
    )
    np.testing.assert_allclose(
        _wide_pair(terms["direct_d_without_evaluation_remainder"]),
        _wide_pair(terms["expanded_d_without_evaluation_remainder"]),
        atol=np.clongdouble("1e-14"),
    )
    remainder = _wide_pair(terms["saved_d_minus_direct_evaluation_remainder"])
    assert remainder != np.clongdouble(0)


def test_v17_completed_cell_and_rhs_reopen_without_build_or_solve_and_rejects_pollution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results_root = tmp_path / "results" / "task41extra_phi90_p50x50_g17x20"
    output_directory = results_root / "attempt_reopen"
    output_directory.mkdir(parents=True)
    persisted_count = 0

    def persist(name: str, value: np.ndarray) -> dict[str, object]:
        nonlocal persisted_count
        persisted_count += 1
        unique_name = f"{name}_{persisted_count}"
        return {"name": unique_name, **v17_worker._persist_array(
            output_directory, unique_name, value, sha256_file=sha256_file
        )}

    dimension = 2
    interior_size = 1
    trace_size = 1
    tensor = np.asarray(
        [[2.0 + 0.2j, 0.1 - 0.05j], [0.3 + 0.1j, 4.0 - 0.1j]],
        dtype=np.complex128,
    )
    candidate_values = {
        "raw_tensor": tensor.copy(),
        "oriented_tensor": tensor,
        "R": np.asarray([[-0.05 + 0.01j]], dtype=np.complex128),
        "T": np.asarray([[-0.15 - 0.05j]], dtype=np.complex128),
        "S": np.asarray([[3.98 - 0.08j]], dtype=np.complex128),
        "interior_lu": np.asarray([[2.0 + 0.2j]], dtype=np.complex128),
        "interior_lu_pivots": np.asarray([0], dtype=np.int32),
    }
    candidate_records = {
        name: persist(f"candidate_{name}", value)
        for name, value in candidate_values.items()
    }
    cell_identity_sha256 = "a" * 64
    cell_state = {
        "candidate_status": "CELL_COMPLETE",
        "candidate_identity_sha256": cell_identity_sha256,
        "candidate_artifacts": candidate_records,
        "candidate_build_count": 1,
        "lu_factorization_count": 1,
        "matrix_rhs_getrs_count": 3,
        "strict_lu_residual": 1.0e-16,
    }

    forbidden_calls = {"build": 0, "solve": 0}

    def forbidden_build(*_args: object, **_kwargs: object) -> None:
        forbidden_calls["build"] += 1
        raise AssertionError("completed V17 candidate must not rebuild")

    def forbidden_solve(*_args: object, **_kwargs: object) -> None:
        forbidden_calls["solve"] += 1
        raise AssertionError("completed V17 RHS must not call GETRS")

    monkeypatch.setattr(v17_worker, "_v8_rebuild_selected_cell_role_artifacts", forbidden_build)
    from src.solvers import hcurl_assembly_time_condensation as hcurl

    monkeypatch.setattr(hcurl, "project_internal_rhs_same_lu", forbidden_solve)
    candidate, charges = v17_worker._task41_p0_v17_reopen_completed_candidate(
        cell_state=cell_state,
        cell_index=7873,
        expected_cell_identity_sha256=cell_identity_sha256,
        artifact_names=set(candidate_records),
        dimension=dimension,
        interior_size=interior_size,
        trace_size=trace_size,
        results_root=results_root,
        sha256_file=sha256_file,
        candidate_evaluator_identity="synthetic-v17-evaluator",
    )
    assert charges == {
        "candidate_build_count": 1,
        "lu_factorization_count": 1,
        "matrix_rhs_getrs_count": 3,
    }
    reopened_candidate_values = {
        "raw_tensor": candidate["raw_tensor"],
        "oriented_tensor": candidate["oriented_tensor"],
        **candidate["rts"],
        "interior_lu": candidate["lu"],
        "interior_lu_pivots": candidate["pivots"],
    }
    for name, expected in candidate_values.items():
        np.testing.assert_array_equal(reopened_candidate_values[name], expected)

    J = np.asarray(candidate["oriented_tensor"])[np.ix_([1], [0])]
    z0 = np.asarray([0.25 - 0.5j], dtype=np.complex128)
    z_final = np.asarray([0.2 - 0.4j], dtype=np.complex128)
    minus_Jz = np.asarray(-J @ z_final, dtype=np.complex128)
    minus_Jz0 = np.asarray(-J @ z0, dtype=np.complex128)
    rhs_identity = {
        "cell_identity_sha256": cell_identity_sha256,
        "column": 0,
        "refinement_max_steps": 2,
        "rhs_sha256": v17_worker._task41_p0_v17_array_sha256(
            np.asarray([1.0 + 2.0j], dtype=np.complex128)
        ),
    }

    def completed_rhs_state(correction: np.ndarray) -> dict[str, object]:
        rhs_artifacts = {
            "z0": persist("rhs_z0", z0),
            "final_z": persist("rhs_final_z", z_final),
            "returned_minus_Jz": persist("rhs_returned_minus_Jz", correction),
            "z0_minus_Jz": persist("rhs_z0_minus_Jz", minus_Jz0),
        }
        return {
            "status": "RHS_COMPLETE",
            "rhs_identity": rhs_identity,
            "rhs_identity_sha256": v17_worker._task41_p0_v17_json_sha256(rhs_identity),
            "artifacts": rhs_artifacts,
            "steps": {"final": {"getrs_count": 2}},
            "timing": {"getrs_count": 2, "residual_evaluation_count": 1},
        }

    state, loaded_z0, loaded_final, loaded_correction, loaded_z0_action, timing = (
        v17_worker._task41_p0_v17_reopen_completed_rhs(
            rhs_state=completed_rhs_state(minus_Jz),
            expected_rhs_identity=rhs_identity,
            expected_rhs_identity_sha256=v17_worker._task41_p0_v17_json_sha256(rhs_identity),
            cell_index=7873,
            column_index=0,
            interior_size=interior_size,
            trace_size=trace_size,
            J=J,
            results_root=results_root,
            sha256_file=sha256_file,
        )
    )
    assert state["status"] == "RHS_COMPLETE"
    np.testing.assert_array_equal(loaded_z0, z0)
    np.testing.assert_array_equal(loaded_final, z_final)
    np.testing.assert_array_equal(loaded_correction, minus_Jz)
    np.testing.assert_array_equal(loaded_z0_action, minus_Jz0)
    assert timing["getrs_count"] == 2
    assert forbidden_calls == {"build": 0, "solve": 0}

    zero_rhs = np.zeros(interior_size, dtype=np.complex128)
    zero_trace = np.zeros(trace_size, dtype=np.complex128)
    zero_identity = {
        **rhs_identity,
        "rhs_sha256": v17_worker._task41_p0_v17_array_sha256(zero_rhs),
    }
    zero_artifacts = {
        "z0": persist("zero_rhs_z0", zero_rhs),
        "final_z": persist("zero_rhs_final_z", zero_rhs),
        "returned_minus_Jz": persist("zero_rhs_correction", zero_trace),
        "z0_minus_Jz": persist("zero_rhs_z0_action", zero_trace),
    }
    zero_state, zero_z0, zero_final, zero_correction, zero_z0_action, zero_timing = (
        v17_worker._task41_p0_v17_reopen_completed_rhs(
            rhs_state={
                "status": "RHS_IN_PROGRESS",
                "rhs_identity": zero_identity,
                "rhs_identity_sha256": v17_worker._task41_p0_v17_json_sha256(zero_identity),
                "artifacts": zero_artifacts,
                "steps": {"final": {"getrs_count": 0, "stop_reason": "zero_rhs"}},
            },
            expected_rhs_identity=zero_identity,
            expected_rhs_identity_sha256=v17_worker._task41_p0_v17_json_sha256(zero_identity),
            cell_index=7873,
            column_index=1,
            interior_size=interior_size,
            trace_size=trace_size,
            J=J,
            results_root=results_root,
            sha256_file=sha256_file,
        )
    )
    assert zero_state["status"] == "RHS_COMPLETE"
    assert zero_timing["nonzero_rhs"] is False
    assert zero_timing["getrs_count"] == 0
    np.testing.assert_array_equal(zero_z0, zero_rhs)
    np.testing.assert_array_equal(zero_final, zero_rhs)
    np.testing.assert_array_equal(zero_correction, zero_trace)
    np.testing.assert_array_equal(zero_z0_action, zero_trace)
    assert forbidden_calls == {"build": 0, "solve": 0}

    polluted = minus_Jz.copy()
    polluted[0] += 1.0e-4j
    with pytest.raises(ValueError, match="not -Jz"):
        v17_worker._task41_p0_v17_reopen_completed_rhs(
            rhs_state=completed_rhs_state(polluted),
            expected_rhs_identity=rhs_identity,
            expected_rhs_identity_sha256=v17_worker._task41_p0_v17_json_sha256(rhs_identity),
            cell_index=7873,
            column_index=0,
            interior_size=interior_size,
            trace_size=trace_size,
            J=J,
            results_root=results_root,
            sha256_file=sha256_file,
        )
    assert forbidden_calls == {"build": 0, "solve": 0}


def test_v17_signed_identity_uses_each_cells_own_selected_e_column() -> None:
    from scipy.sparse import csr_matrix

    for active_slot, selected_trace_slot in ((4, 11), (7, 2)):
        expansion = np.zeros((16, 9), dtype=np.complex128)
        expansion[selected_trace_slot, active_slot] = 1.0 + 0.0j
        q = v17_worker._task41_p0_v17_selected_q_from_expansion(
            csr_matrix(expansion),
            active_slot=active_slot,
            selected_trace_slot=selected_trace_slot,
        )
        expected = np.zeros(16, dtype=np.complex128)
        expected[selected_trace_slot] = 1.0 + 0.0j
        np.testing.assert_array_equal(q, expected)
