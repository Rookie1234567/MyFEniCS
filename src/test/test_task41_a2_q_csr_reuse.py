from __future__ import annotations

import hashlib
import json
from pathlib import Path
import numpy as np
import pytest
from scipy import sparse

from src.geometry.task41_phi90_profile import TASK41_G13_A2_PRECONDITIONER
from src.runners.task41_p0_contract import (
    Task41ContractError,
    _prepare_task41_a2_q_csr_reuse,
    _validate_task41_a2_q_csr_reuse,
)
from src.runners.task40_v10_worker import _task41_a2_load_saved_q_csr_pair
from src.solvers.task40_v30_qualified_q_csr import (
    QualifiedQCSRProvider,
    V30_Q_CSR_MANIFEST_SCHEMA,
    V30_Q_CSR_NATIVE_SCHEMA,
    _array_sha256,
    _csr_sha256,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_saved_q(root: Path, q: int, input_sha256: str) -> Path:
    directory = root / "results" / f"q{q}_twist0"
    directory.mkdir(parents=True, exist_ok=True)
    artifact_rows = {}
    for name in ("data", "indices", "indptr"):
        data = f"fixture q={q} {name}".encode()
        artifact = directory / f"q{q}_{name}.npy"
        artifact.write_bytes(data)
        artifact_rows[name] = {
            "path": str(artifact),
            "bytes": len(data),
            "sha256": _sha(data),
        }
    producer_execution = {
        "source_sha": "1" * 40,
        "window_sha256": "2" * 64,
    }
    operator_identity = {
        "scientific_input_sha256": input_sha256,
        "profile_identity_sha256": "3" * 64,
        "ordered_mode_sha256": "4" * 64,
        "q_map_sha256": "5" * 64,
        "original_h_sha256": "6" * 64,
    }
    manifest = {
        "schema": V30_Q_CSR_MANIFEST_SCHEMA,
        "status": "COMPLETE_CSR",
        "profile": TASK41_G13_A2_PRECONDITIONER,
        "q_index": q,
        "twist_index": 0,
        "shape": [2, 2],
        "stored_structural_slots": 2,
        "operator_identity": operator_identity,
        "matrix_source_identity": producer_execution,
        "execution_identity": producer_execution,
        "producer_identity": {"kind": "fixture"},
        "csr_artifacts": artifact_rows,
    }
    manifest_path = directory / f"task40_v30_q{q}_twist0_csr_manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    manifest_sha = _sha(manifest_path.read_bytes())
    qualification = {
        "schema": V30_Q_CSR_NATIVE_SCHEMA,
        "status": "PASS",
        "q_index": q,
        "twist_index": 0,
        "csr_manifest_sha256": manifest_sha,
        "operator_identity": operator_identity,
        "matrix_source_identity": producer_execution,
        "execution_identity": producer_execution,
        "four_complete_csr_actions_passed": True,
        "paired_sector_leakage_passed": True,
        "maximum_relative_error": 1e-14,
    }
    (directory / f"task40_v30_q{q}_twist0_native_qualification.json").write_text(
        json.dumps(qualification, sort_keys=True), encoding="utf-8"
    )
    return manifest_path


def test_task41_a2_saved_q_selector_prepare_load_and_same_source_reopen(tmp_path):
    input_sha256 = "a" * 64
    source_sha = "7" * 40
    window_sha256 = "8" * 64
    manifests = [
        _write_saved_q(tmp_path, q, input_sha256)
        for q in (0, 5)
    ]
    binding = _prepare_task41_a2_q_csr_reuse(
        tmp_path,
        manifests,
        source_sha=source_sha,
        window_sha256=window_sha256,
        expected_input_sha256=input_sha256,
    )
    _validate_task41_a2_q_csr_reuse(
        tmp_path,
        binding,
        source_sha=source_sha,
        window_sha256=window_sha256,
        expected_input_sha256=input_sha256,
    )
    reopened = _prepare_task41_a2_q_csr_reuse(
        tmp_path,
        manifests,
        source_sha=source_sha,
        window_sha256=window_sha256,
        expected_input_sha256=input_sha256,
    )
    assert reopened == binding
    assert binding["q_indices"] == [0, 5]
    assert set(binding["consumer_import_authorizations"]) == {"0", "5"}
    for authorization in binding["consumer_import_authorizations"].values():
        assert authorization["consumer_execution_identity"] == {
            "source_sha": source_sha,
            "window_sha256": window_sha256,
        }


def test_task41_a2_saved_q_binding_rejects_changed_authorization(tmp_path):
    input_sha256 = "a" * 64
    binding = _prepare_task41_a2_q_csr_reuse(
        tmp_path,
        [_write_saved_q(tmp_path, q, input_sha256) for q in (0, 5)],
        source_sha="7" * 40,
        window_sha256="8" * 64,
        expected_input_sha256=input_sha256,
    )
    binding["consumer_import_authorizations"]["5"]["csr_manifest_sha256"] = "9" * 64
    with pytest.raises(Task41ContractError, match="source-bound"):
        _validate_task41_a2_q_csr_reuse(
            tmp_path,
            binding,
            source_sha="7" * 40,
            window_sha256="8" * 64,
            expected_input_sha256=input_sha256,
        )
    binding["manifest_bindings"] = None
    with pytest.raises(Task41ContractError, match="incomplete"):
        _validate_task41_a2_q_csr_reuse(
            tmp_path,
            binding,
            source_sha="7" * 40,
            window_sha256="8" * 64,
            expected_input_sha256=input_sha256,
        )


def test_task41_a2_zero_port_q1_build_and_native_pair_with_q6(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from src.solvers import task40_v25_selected_q0
    from src.solvers.task40_v30_selected_q_csr import (
        build_saved_selected_q_pattern,
        fill_saved_selected_q_values,
        qualify_selected_q_native,
        run_selected_q_native_actions,
    )

    trace_rows = 28_440
    active_rows = 126_000
    local_port_rows = 56_880
    reduced_rows = active_rows + local_port_rows

    def embedded_map(column_rows):
        rows = np.asarray(column_rows, dtype=np.int32)
        columns = np.arange(len(rows), dtype=np.int32)
        result = sparse.csr_matrix(
            (
                np.ones(len(rows), dtype=np.complex128),
                (rows, columns),
            ),
            shape=(reduced_rows, len(rows)),
        )
        result.indices = result.indices.astype(np.int32, copy=False)
        result.indptr = result.indptr.astype(np.int32, copy=False)
        return result

    q1_map = embedded_map(np.arange(trace_rows, dtype=np.int32))
    q6_map = embedded_map(
        np.concatenate(
            (
                np.arange(trace_rows, 2 * trace_rows, dtype=np.int32),
                np.arange(active_rows, active_rows + 28, dtype=np.int32),
            )
        )
    )
    assert q1_map.shape == (reduced_rows, trace_rows)
    assert q6_map.shape == (reduced_rows, trace_rows + 28)

    class SavedSource:
        def __init__(self):
            self.active_rows = active_rows
            self.port_count = local_port_rows
            self.reduced_rows = reduced_rows
            self.local_h = np.ones(local_port_rows, dtype=np.complex128)

        def iter_reduced_contribution_layouts(self, *, hhat_block_columns=None):
            yield np.asarray([0], dtype=np.int32), np.asarray([0], dtype=np.int32), "trace/zero-port"

        def iter_reduced_contributions(
            self, *, allocation_gate, hhat_block_columns=None, include_hhat=True
        ):
            allocation_gate("fixture/base", {"additional_payload_bytes": 0, "workspace_bytes": 0})
            yield (
                np.asarray([0], dtype=np.int32),
                np.asarray([0], dtype=np.int32),
                np.asarray([[2.0 + 0.0j]], dtype=np.complex128),
                "trace/zero-port",
            )

    source = SavedSource()
    pattern, view, _pattern_facts = build_saved_selected_q_pattern(
        source,
        q1_map,
        q_index=1,
        twist_index=1,
        trace_rows=trace_rows,
        output_directory=tmp_path / "q1_pattern",
        allocation_gate=lambda *_args: None,
    )
    assert view.selected_port_rows == 0
    hhat = view.selected_hhat_sparse_term(allocation_gate=lambda *_args: None)
    assert hhat.shape == (0, 0)
    assert hhat.nnz == 0
    pattern, numeric_facts = fill_saved_selected_q_values(
        source,
        pattern,
        q1_map,
        q_index=1,
        twist_index=1,
        trace_rows=trace_rows,
        allocation_gate=lambda *_args: None,
        direct_hhat=True,
        direct_hhat_evidence={
            "numeric_internal_support_empty": True,
            "internal_B_nnz": 0,
            "internal_D_nnz": 0,
        },
    )
    assert pattern.shape == (trace_rows, trace_rows)
    assert numeric_facts["numeric_fill_complete"] is True
    assert numeric_facts["direct_hhat_sparse_selected_q"]["term_shape"] == [0, 0]

    class NativeAction:
        def __init__(self):
            self.reduced_size = reduced_rows
            self.condensed = SimpleNamespace(
                full_rows=195_132,
                active_rows=active_rows,
                appended_rows=local_port_rows,
            )

        def recover_storage(self, reduced, *, expand_trace):
            assert expand_trace is False
            full = np.zeros(self.condensed.full_rows, dtype=np.complex128)
            full[:reduced_rows] = reduced
            return full

        def reduce_rhs(self, rhs, *, port_rhs=None, rhs_is_mpc_dual):
            assert rhs_is_mpc_dual is True
            reduced = np.asarray(rhs[:reduced_rows], dtype=np.complex128).copy()
            if port_rhs is not None:
                reduced[active_rows:] += np.asarray(port_rhs, dtype=np.complex128)
            return reduced

        def apply_B_full(self, ports):
            assert np.asarray(ports).shape == (local_port_rows,)
            return np.zeros(self.condensed.full_rows, dtype=np.complex128)

        def apply_D_full(self, field):
            return np.zeros(local_port_rows, dtype=np.complex128)

        def _apply_original_h(self, ports):
            return np.zeros_like(ports, dtype=np.complex128)

    monkeypatch.setattr(
        task40_v25_selected_q0,
        "_native_volume_apply",
        lambda _volume_action, field, _comm, counters=None: np.asarray(field).copy(),
    )
    action = NativeAction()
    for selected_q, selected_map, peer_map in (
        (1, q1_map, q6_map),
        (6, q6_map, q1_map),
    ):
        selected_rows = selected_map.shape[1]
        peer_rows = peer_map.shape[1]
        receipt = run_selected_q_native_actions(
            action=action,
            volume_action=object(),
            comm=object(),
            q_maps=(q1_map, q6_map),
            q_indices=(1, 6),
            trace_rows_by_q={1: trace_rows, 6: trace_rows},
            selected_q_index=selected_q,
            twist_index=1,
            matrix=sparse.eye(selected_rows, dtype=np.complex128, format="csr"),
            peer_matrix=sparse.eye(peer_rows, dtype=np.complex128, format="csr"),
            allocation_gate=lambda *_args: None,
        )
        assert receipt["status"] == "PASS"
        assert receipt["csr_action_count"] == 4
        assert receipt["paired_sector_leakage_passed"] is True
        assert max(receipt["paired_sector_leakage"][key]["relative"] for key in ("q_to_peer", "peer_to_q")) == 0.0
        assert max(receipt["relative_errors"].values()) == 0.0
        if selected_q == 1:
            assert receipt["inputs"]["case1_port_only"].shape == (trace_rows,)
            assert not np.any(receipt["inputs"]["case1_port_only"])
            assert receipt["native_outputs"]["case1_port_only"].shape == (trace_rows,)
            assert not np.any(receipt["native_outputs"]["case1_port_only"])
            changed_native = dict(receipt["native_outputs"])
            changed_native["case1_port_only"] = np.ones(trace_rows, dtype=np.complex128)
            with pytest.raises(ValueError, match="CSR/native error exceeded"):
                qualify_selected_q_native(
                    matrix=sparse.eye(trace_rows, dtype=np.complex128, format="csr"),
                    inputs=receipt["inputs"],
                    csr_outputs=receipt["csr_outputs"],
                    native_outputs=changed_native,
                    native_components_case1=receipt["native_components_case1"],
                    paired_leakage=receipt["paired_sector_leakage"],
                    trace_rows=trace_rows,
                )


def _write_provider_q(
    root: Path,
    q: int,
    q_map: sparse.csr_matrix,
    original_h: np.ndarray,
    input_sha256: str,
    producer_execution: dict[str, str],
) -> tuple[Path, dict[str, str]]:
    directory = root / f"provider_q{q}"
    directory.mkdir()
    q_matrix = sparse.csr_matrix(
        np.asarray([[2.0 + q, 0.25j], [-0.5j, 3.0 + q]], dtype=np.complex128)
    )
    operator_identity = {
        "scientific_input_sha256": input_sha256,
        "profile_identity_sha256": "2" * 64,
        "ordered_mode_sha256": "3" * 64,
        "q_map_sha256": _csr_sha256(q_map),
        "original_h_sha256": _array_sha256(
            original_h, np.dtype(np.complex128), "fixture original H"
        ),
    }
    artifact_rows = {}
    for name, array in (
        ("data", q_matrix.data),
        ("indices", q_matrix.indices.astype(np.int32, copy=False)),
        ("indptr", q_matrix.indptr.astype(np.int32, copy=False)),
    ):
        artifact_path = directory / f"q{q}_{name}.npy"
        np.save(artifact_path, array, allow_pickle=False)
        artifact_rows[name] = {
            "path": artifact_path.name,
            "bytes": artifact_path.stat().st_size,
            "sha256": _sha(artifact_path.read_bytes()),
        }
    manifest = {
        "schema": V30_Q_CSR_MANIFEST_SCHEMA,
        "status": "COMPLETE_CSR",
        "profile": TASK41_G13_A2_PRECONDITIONER,
        "q_index": q,
        "twist_index": 0,
        "shape": list(q_matrix.shape),
        "stored_structural_slots": int(q_matrix.nnz),
        "csr_index_dtype": np.dtype(np.int32).str,
        "csr_data_dtype": np.dtype(np.complex128).str,
        "operator_identity": operator_identity,
        "matrix_source_identity": producer_execution,
        "execution_identity": producer_execution,
        "producer_identity": {"kind": "Task41 A2 provider fixture"},
        "csr_artifacts": artifact_rows,
    }
    manifest_path = directory / f"task40_v30_q{q}_twist0_csr_manifest.json"
    manifest_path.write_text(json.dumps(manifest, sort_keys=True), encoding="utf-8")
    manifest_sha = _sha(manifest_path.read_bytes())
    qualification = {
        "schema": V30_Q_CSR_NATIVE_SCHEMA,
        "status": "PASS",
        "q_index": q,
        "twist_index": 0,
        "csr_manifest_sha256": manifest_sha,
        "operator_identity": operator_identity,
        "matrix_source_identity": producer_execution,
        "execution_identity": producer_execution,
        "four_complete_csr_actions_passed": True,
        "paired_sector_leakage_passed": True,
        "maximum_relative_error": 1e-14,
    }
    (directory / f"task40_v30_q{q}_twist0_native_qualification.json").write_text(
        json.dumps(qualification, sort_keys=True), encoding="utf-8"
    )
    return manifest_path, operator_identity


def test_task41_a2_import_helper_uses_real_provider_for_non_square_maps_only_at_twist_zero(
    tmp_path,
):
    input_sha256 = "a" * 64
    producer_execution = {"source_sha": "1" * 40, "window_sha256": "2" * 64}
    consumer_execution = {"source_sha": "7" * 40, "window_sha256": "8" * 64}
    original_h = np.asarray([1.0 + 0.1j, -0.25 + 0.5j], dtype=np.complex128)
    q_maps = {
        0: sparse.csr_matrix(
            np.asarray([[1.0, 0.0], [0.0, 1.0], [1.0, -1.0]], dtype=np.complex128)
        ),
        5: sparse.csr_matrix(
            np.asarray([[1.0, 0.5], [0.0, 1.0], [-1.0, 0.0], [0.25, 0.75]], dtype=np.complex128)
        ),
    }
    assert q_maps[0].shape == (3, 2)
    assert q_maps[5].shape == (4, 2)
    manifests_and_identities = {
        q: _write_provider_q(
            tmp_path,
            q,
            q_maps[q],
            original_h,
            input_sha256,
            producer_execution,
        )
        for q in (0, 5)
    }
    binding = _prepare_task41_a2_q_csr_reuse(
        tmp_path,
        [manifests_and_identities[q][0] for q in (0, 5)],
        source_sha=consumer_execution["source_sha"],
        window_sha256=consumer_execution["window_sha256"],
        expected_input_sha256=input_sha256,
    )
    provider = QualifiedQCSRProvider(
        tmp_path / binding["selector_path"],
        selector_sha256=binding["selector_sha256"],
        repo_root=tmp_path,
        path_resolver=lambda path: Path(path).resolve(),
        allocation_gate=lambda *_args, **_kwargs: None,
        consumer_receipt_directory=tmp_path / "consumer_receipts",
        consumer_import_authorizations=binding["consumer_import_authorizations"],
    )
    result = _task41_a2_load_saved_q_csr_pair(
        provider,
        q_indices=(0, 5),
        twist_index=0,
        q_maps_by_q=q_maps,
        original_h=original_h,
        operator_identity_by_q={
            q: manifests_and_identities[q][1] for q in (0, 5)
        },
        execution_identity=consumer_execution,
        profile_name=TASK41_G13_A2_PRECONDITIONER,
        qualification_identity={"profile_identity": TASK41_G13_A2_PRECONDITIONER},
    )
    assert result is not None
    matrices, audit = result
    assert {q: matrix.shape for q, matrix in matrices.items()} == {0: (2, 2), 5: (2, 2)}
    assert audit["all_complete_native_pass"] is True
    assert audit["paired_sector_leakage_passed"] is True
    assert all(row["consumer_receipt"]["sha256"] for row in audit["qualification_receipts"])

    assert _task41_a2_load_saved_q_csr_pair(
        provider,
        q_indices=(0, 5),
        twist_index=1,
        q_maps_by_q=q_maps,
        original_h=original_h,
        operator_identity_by_q={
            q: manifests_and_identities[q][1] for q in (0, 5)
        },
        execution_identity=consumer_execution,
        profile_name=TASK41_G13_A2_PRECONDITIONER,
        qualification_identity={"profile_identity": TASK41_G13_A2_PRECONDITIONER},
    ) is None

