from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from src.solvers import task40_v25_selected_q0
from src.solvers.task40_v30_selected_q_csr import (
    _raw_vector_sha256,
    build_saved_selected_q_pattern,
    finalize_selected_q_csr,
    fill_saved_selected_q_values,
    qualify_selected_q_native,
    require_direct_hhat_evidence,
    run_selected_q_native_actions,
    selected_q_operator_identity,
)


class _ToySavedContributions:
    active_rows = 2
    port_count = 2
    reduced_rows = 4
    local_h = np.asarray([2.0 + 0j, 3.0 + 0j], dtype=np.complex128)

    def __init__(self, base: np.ndarray):
        self.base = base
        self.include_hhat_seen = None

    def iter_reduced_contribution_layouts(self, *, hhat_block_columns=None):
        rows = np.arange(4, dtype=np.int32)
        yield rows, rows, "toy/local"

    def iter_reduced_contributions(self, *, allocation_gate, hhat_block_columns=None, include_hhat=True):
        self.include_hhat_seen = include_hhat
        allocation_gate("toy/saved", {"additional_payload_bytes": 0, "workspace_bytes": 0})
        rows = np.arange(4, dtype=np.int32)
        yield rows, rows, self.base.copy(), "toy/saved_base_without_H"


def _dense_pattern(n: int) -> sparse.csr_matrix:
    indices = np.tile(np.arange(n, dtype=np.int32), n)
    indptr = np.arange(0, n * n + 1, n, dtype=np.int32)
    data = np.zeros(n * n, dtype=np.complex128)
    return sparse.csr_matrix((data, indices, indptr), shape=(n, n), copy=False)


def test_saved_q4_fill_uses_sparse_local_and_selected_direct_h() -> None:
    base = np.asarray(
        [
            [4.0 + 0.1j, 0.2 + 0j, 0.1j, 0.0],
            [0.2 + 0j, 5.0 - 0.1j, 0.0, 0.2j],
            [0.1j, 0.0, 1.0 + 0j, 0.3],
            [0.0, 0.2j, 0.3, 2.0 + 0j],
        ],
        dtype=np.complex128,
    )
    q4_map = sparse.csr_matrix(
        np.asarray(
            [
                [1, 0, 0],
                [0, 1, 0],
                [0, 0, 1],
                [0, 0, 1j],
            ],
            dtype=np.complex128,
        )
    )
    source = _ToySavedContributions(base)
    matrix = _dense_pattern(3)
    matrix.data[:] = 17.0
    gate_records = []

    def gate(label, facts):
        facts = dict(facts)
        if label.endswith("preclear_csr_residency"):
            assert np.all(matrix.data == 17.0)
            gate_records.append((label, facts))
        else:
            gate_records.append((label, facts))

    matrix, audit = fill_saved_selected_q_values(
        source,
        matrix,
        q4_map,
        q_index=4,
        twist_index=0,
        trace_rows=2,
        allocation_gate=gate,
        direct_hhat=True,
        direct_hhat_evidence={
            "numeric_internal_support_empty": True,
            "internal_B_nnz": 0,
            "internal_D_nnz": 0,
            "witness": "independent saved-fixture inventory",
        },
    )
    expected_local = base + np.diag(np.asarray([0, 0, 2, 3], dtype=np.complex128))
    q4_dense = q4_map.toarray()
    expected = q4_dense.conjugate().T @ expected_local @ q4_dense
    assert np.allclose(matrix.toarray(), expected, rtol=0, atol=1e-14)
    assert source.include_hhat_seen is False
    assert audit["projection_method"] == "sparse_local"
    assert audit["direct_hhat_sparse_q0"] is None
    assert audit["direct_hhat_sparse_selected_q"]["selected_q_index"] == 4
    assert audit["direct_hhat_sparse_selected_q"]["term_shape"] == [1, 1]
    admission = next(row for label, row in gate_records if label.endswith("preclear_csr_residency"))
    assert admission["csr_payload_bytes"] == matrix.data.nbytes + matrix.indices.nbytes + matrix.indptr.nbytes
    assert admission["workspace_bytes"] == 256 * 1024**2
    assert admission["same_backing_pages_counted_once"] is True
    assert audit["preclear_memory_admission"]["preclear_admission"] is True
    assert any(label == "task40_v30_q4_direct_hhat" for label, _ in gate_records)


def test_direct_h_requires_explicit_empty_internal_b_and_d_evidence() -> None:
    with pytest.raises(ValueError, match="empty internal B and D"):
        require_direct_hhat_evidence(
            {"numeric_internal_support_empty": True, "internal_B_nnz": 1, "internal_D_nnz": 0}
        )


def test_native_qualification_checks_four_csr_actions_and_components() -> None:
    matrix = sparse.csr_matrix(
        np.asarray([[2 + 0.2j, 1 - 0.1j, 0], [0.5j, 3 + 0j, 0.2], [0, 0.4, 4 - 0.3j]], dtype=np.complex128)
    )
    full = np.asarray([1 + 0.2j, 2 - 0.3j, 3 + 0.4j], dtype=np.complex128)
    inputs = {
        "case1_full": full,
        "case1_trace_only": np.asarray([full[0], full[1], 0], dtype=np.complex128),
        "case1_port_only": np.asarray([0, 0, full[2]], dtype=np.complex128),
        "case2_full": np.asarray([0.4 + 0.7j, 0.9 - 0.5j, 1.7 + 0.1j], dtype=np.complex128),
    }
    outputs = {name: matrix @ value for name, value in inputs.items()}
    receipt = qualify_selected_q_native(
        matrix=matrix,
        inputs=inputs,
        csr_outputs=outputs,
        native_outputs=outputs,
        native_components_case1={
            "volume": outputs["case1_full"],
            "minus_D": np.zeros(3, dtype=np.complex128),
            "C": np.zeros(3, dtype=np.complex128),
            "Hhat": np.zeros(3, dtype=np.complex128),
        },
        paired_leakage={
            "q_to_peer": {"relative": 0.0},
            "peer_to_q": {"relative": 0.0},
        },
        trace_rows=2,
    )
    assert receipt["status"] == "PASS"
    assert receipt["csr_action_count"] == 4
    assert receipt["maximum_relative_error"] == 0.0

    changed = dict(outputs)
    changed["case2_full"] = outputs["case2_full"].copy()
    changed["case2_full"][0] += 1e-5
    with pytest.raises(ValueError, match="CSR/native error exceeded"):
        qualify_selected_q_native(
            matrix=matrix,
            inputs=inputs,
            csr_outputs=changed,
            native_outputs=outputs,
            native_components_case1={
                "volume": outputs["case1_full"],
                "minus_D": np.zeros(3, dtype=np.complex128),
                "C": np.zeros(3, dtype=np.complex128),
                "Hhat": np.zeros(3, dtype=np.complex128),
            },
            paired_leakage={
                "q_to_peer": {"relative": 0.0},
                "peer_to_q": {"relative": 0.0},
            },
            trace_rows=2,
        )


def test_q4_native_reuses_identity_bound_v26_pair_and_only_runs_missing_work(monkeypatch) -> None:
    q0_map = sparse.csr_matrix(
        np.asarray([[1, 0], [0, 1], [0, 0], [0, 0]], dtype=np.complex128)
    )
    q4_map = sparse.csr_matrix(
        np.asarray([[0, 0], [0, 0], [1, 0], [0, 1]], dtype=np.complex128)
    )
    matrix = sparse.diags(
        np.asarray([2.0, 3.0], dtype=np.complex128), format="csr", dtype=np.complex128
    )
    case1_input = np.asarray([1.0 + 0.25j, 0.75 + 0.5j], dtype=np.complex128)
    case1_output = matrix @ case1_input
    peer_input = np.asarray([2.0 + 0.5j, 1.25 + 0.75j], dtype=np.complex128)
    peer_output = np.asarray([peer_input[0], 2 * peer_input[1]], dtype=np.complex128)
    operator_identity = {"q_map_sha256": "1" * 64, "original_h_sha256": "2" * 64}
    arrays = {
        "case1_full_input": case1_input,
        "case1_full_output": case1_output,
        "selected_to_peer_cross": np.zeros(2, dtype=np.complex128),
        "peer_case1_input": peer_input,
        "peer_case1_output": peer_output,
        "peer_to_selected_cross": np.zeros(2, dtype=np.complex128),
    }
    array_sha = {name: _raw_vector_sha256(value) for name, value in arrays.items()}
    donor_identity = {
        "source_sha": "3" * 40,
        "run_id": "run-v26",
        "physical_model_sha256": "a" * 64,
        "campaign_window_sha256": "b" * 64,
        "producer_identity_sha256": "6" * 64,
        "mode_manifest_sha256": "c" * 64,
        "ordered_mode_key_sha256": "d" * 64,
    }
    current_identity = {
        **donor_identity,
        "source_sha": "e" * 40,
        "campaign_window_sha256": "f" * 64,
    }
    native_manifest = {
        "schema": "task40extra.review_v26_native_action.v1",
        "status": "PASS_COMPLETE_Q0_NATIVE_CONSUMER",
        "manifest_sha256": "4" * 64,
        "producer_identity_sha256": "6" * 64,
        "saved_replay_manifest_sha256": "5" * 64,
        "current_identity": donor_identity,
        "cases": {
            "q4_pair": {
                "array_sha256": {
                    "native_q4_total": array_sha["case1_full_output"],
                    "native_q0_from_q4": array_sha["selected_to_peer_cross"],
                }
            },
            "q0_case_1": {
                "array_sha256": {
                    "native_q0_total": array_sha["peer_case1_output"],
                    "native_q4_from_q0": array_sha["peer_to_selected_cross"],
                }
            },
        },
    }
    replay_manifest = {
        "schema": "task40extra.review_v26_saved_q_replay.v1",
        "status": "PASS_SAVED_STREAM_REPLAY_NO_NATIVE",
        "manifest_sha256": "5" * 64,
        "producer_identity_sha256": "6" * 64,
        "current_identity": donor_identity,
        "artifacts": {
            "inputs": {
                "array_sha256": {
                    "q4_pair": array_sha["case1_full_input"],
                    "q0_case_1": array_sha["peer_case1_input"],
                }
            }
        },
    }
    witness = {
        "schema": "task40extra.review_v30_selected_q_saved_native_reuse.v1",
        "operator_identity": operator_identity,
        "current_identity": donor_identity,
        "native_manifest_sha256": "4" * 64,
        "saved_replay_manifest_sha256": "5" * 64,
        "producer_identity_sha256": "6" * 64,
        "native_manifest": native_manifest,
        "saved_replay_manifest": replay_manifest,
        "donor_verifier_receipt": {
            "schema": "task40extra.review_v26_native_donor_readback.v1",
            "status": "PASS",
            "native_manifest_sha256": "4" * 64,
            "saved_replay_manifest_sha256": "5" * 64,
            "producer_identity_sha256": "6" * 64,
            "donor_current_identity": donor_identity,
        },
        "arrays": {
            name: {"value": value, "sha256": array_sha[name]}
            for name, value in arrays.items()
        },
    }
    action = SimpleNamespace(
        reduced_size=4,
        condensed=SimpleNamespace(full_rows=4),
    )
    calls = {"components": 0, "projected": 0}

    def component_actions(**kwargs):
        calls["components"] += 1
        trace = np.zeros(4, dtype=np.complex128)
        trace[2] = 2.0 * kwargs["trace_input"][0]
        port = np.zeros(4, dtype=np.complex128)
        port[3] = 3.0 * kwargs["port_input"][0]
        zeros = np.zeros(4, dtype=np.complex128)
        return {"volume": trace, "-D": zeros, "C": zeros, "Hhat": port}

    def projected_action(**kwargs):
        calls["projected"] += 1
        assert kwargs["include_components"] is False
        output_q4 = matrix @ kwargs["source"]
        output_q0 = np.zeros(2, dtype=np.complex128)
        return output_q0, output_q4, np.zeros(4, dtype=np.complex128)

    monkeypatch.setattr(task40_v25_selected_q0, "_native_component_reduced_actions", component_actions)
    monkeypatch.setattr(task40_v25_selected_q0, "_native_projected_action", projected_action)
    receipt = run_selected_q_native_actions(
        action=action,
        volume_action=object(),
        comm=object(),
        q_maps=(q0_map, q4_map),
        q_indices=(0, 4),
        trace_rows_by_q={0: 1, 4: 1},
        selected_q_index=4,
        twist_index=0,
        matrix=matrix,
        allocation_gate=lambda *_args: None,
        saved_native_witness=witness,
        expected_operator_identity=operator_identity,
        expected_current_identity=current_identity,
    )

    assert receipt["status"] == "PASS"
    assert receipt["saved_native_reused"] is True
    assert receipt["native_selected_case_count"] == 2
    assert receipt["native_volume_apply_count"] == 4
    assert calls == {"components": 1, "projected": 1}
    assert receipt["relative_errors"]["case1_trace_only"] == 0.0
    assert receipt["relative_errors"]["case1_port_only"] == 0.0


def test_saved_native_witness_rejects_identity_mismatch() -> None:
    from src.solvers.task40_v30_selected_q_csr import _checked_saved_native_vector

    value = np.asarray([1.0 + 1j], dtype=np.complex128)
    witness = {
        "schema": "task40extra.review_v30_selected_q_saved_native_reuse.v1",
        "operator_identity": {"q_map_sha256": "1" * 64},
        "current_identity": {"source_sha": "2" * 40},
        "native_manifest_sha256": "3" * 64,
        "saved_replay_manifest_sha256": "4" * 64,
        "producer_identity_sha256": "5" * 64,
        "arrays": {"case1_full_input": {"value": value, "sha256": _raw_vector_sha256(value)}},
    }
    with pytest.raises(ValueError, match="not bound to the live operator identity"):
        _checked_saved_native_vector(
            witness,
            "case1_full_input",
            expected_length=1,
            expected_operator_identity={"q_map_sha256": "9" * 64},
            expected_current_identity={"source_sha": "2" * 40},
        )


def test_disk_backed_q4_fill_and_finalize_keep_pattern_arrays_in_place(tmp_path) -> None:
    base = np.asarray(
        [
            [4.0 + 0.1j, 0.2 + 0j, 0.1j, 0.0],
            [0.2 + 0j, 5.0 - 0.1j, 0.0, 0.2j],
            [0.1j, 0.0, 1.0 + 0j, 0.3],
            [0.0, 0.2j, 0.3, 2.0 + 0j],
        ],
        dtype=np.complex128,
    )
    q4_map = sparse.csr_matrix(
        np.asarray(
            [[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 1j]],
            dtype=np.complex128,
        )
    )
    source = _ToySavedContributions(base)
    gate = lambda *_args: None
    matrix, _view, pattern = build_saved_selected_q_pattern(
        source,
        q4_map,
        q_index=4,
        twist_index=0,
        trace_rows=2,
        output_directory=tmp_path / "q4",
        allocation_gate=gate,
    )
    old_data_hash = pattern["csr_artifacts"]["data"]["sha256"]
    matrix, numeric = fill_saved_selected_q_values(
        source,
        matrix,
        q4_map,
        q_index=4,
        twist_index=0,
        trace_rows=2,
        allocation_gate=gate,
        direct_hhat=True,
        direct_hhat_evidence={
            "numeric_internal_support_empty": True,
            "internal_B_nnz": 0,
            "internal_D_nnz": 0,
        },
    )
    assert numeric["numeric_fill_complete"] is True
    assert pattern["csr_artifacts"]["data"]["sha256"] == old_data_hash
    assert hashlib.sha256(Path(pattern["csr_artifacts"]["data"]["path"]).read_bytes()).hexdigest() != old_data_hash

    inputs = {
        "case1_full": np.asarray([1 + 0.2j, 2 - 0.3j, 3 + 0.4j], dtype=np.complex128),
        "case1_trace_only": np.asarray([1 + 0.2j, 2 - 0.3j, 0], dtype=np.complex128),
        "case1_port_only": np.asarray([0, 0, 3 + 0.4j], dtype=np.complex128),
        "case2_full": np.asarray([0.4 + 0.7j, 0.9 - 0.5j, 1.7 + 0.1j], dtype=np.complex128),
    }
    csr_outputs = {name: np.asarray(matrix @ value) for name, value in inputs.items()}
    native_outputs = {name: value.copy() for name, value in csr_outputs.items()}
    components = {
        "volume": native_outputs["case1_trace_only"].copy(),
        "minus_D": np.zeros(3, dtype=np.complex128),
        "C": native_outputs["case1_port_only"].copy(),
        "Hhat": np.zeros(3, dtype=np.complex128),
    }
    paired_leakage = {
        "q_to_peer": {"relative": 0.0},
        "peer_to_q": {"relative": 0.0},
    }
    native = {
        **qualify_selected_q_native(
            matrix=matrix,
            inputs=inputs,
            csr_outputs=csr_outputs,
            native_outputs=native_outputs,
            native_components_case1=components,
            paired_leakage=paired_leakage,
            trace_rows=2,
        ),
        "inputs": inputs,
        "csr_outputs": csr_outputs,
        "native_outputs": native_outputs,
        "native_components_case1": components,
        "paired_peer_input": np.asarray([1 + 0.2j, 0.5 + 0.4j], dtype=np.complex128),
        "paired_peer_native_diagonal": np.asarray([0.8 + 0.1j, 0.6 + 0.3j], dtype=np.complex128),
        "paired_peer_native_cross": np.zeros(3, dtype=np.complex128),
        "paired_selected_native_cross": np.zeros(2, dtype=np.complex128),
        "paired_peer_case2_cross": np.zeros(2, dtype=np.complex128),
        "native_input_seeds": {"case1_full": 1, "case2_full": 2},
    }
    mode = SimpleNamespace(side="bottom", m=0, n=0, polarization="s")
    profile_identity = {"name": "selected-q-fixture", "trace_rows": 2}
    scientific_input_sha256 = "7" * 64
    original_h = np.asarray([2.0], dtype=np.complex128)
    operator_identity = selected_q_operator_identity(
        scientific_input_sha256=scientific_input_sha256,
        profile_identity=profile_identity,
        ordered_modes=(mode,),
        q_map=q4_map,
        original_h=original_h,
    )
    source_sha = "8" * 40
    window_sha256 = "9" * 64
    source_identity = {"source_sha": source_sha, "window_sha256": window_sha256}
    finalize_selected_q_csr(
        matrix=matrix,
        pattern_record=pattern,
        numeric_facts=numeric,
        native_result=native,
        output_directory=tmp_path / "q4",
        profile="selected-q-fixture",
        q_index=4,
        twist_index=0,
        q_map=q4_map,
        original_h=original_h,
        profile_identity=profile_identity,
        ordered_modes=(mode,),
        scientific_input_sha256=scientific_input_sha256,
        operator_identity=operator_identity,
        matrix_source_identity=source_identity,
        execution_identity=source_identity,
        producer_identity={"fixture": "saved-stream"},
    )
    manifest_path = tmp_path / "q4" / "task40_v30_q4_twist0_csr_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["v17_csr_arrays_reused_without_copy"] is True
    assert manifest["pattern_csr_artifacts"]["data"]["sha256"] == old_data_hash
    assert manifest["csr_artifacts"]["data"]["sha256"] != old_data_hash
    assert all(row["reused_in_place"] for row in manifest["csr_backing_identity"].values())
