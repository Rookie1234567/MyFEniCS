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
    make_v31_pending_import_authorization,
    make_v32_q4_numeric_pending_import_authorization,
    prepare_saved_selected_q_numeric_pending,
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


def test_saved_q4_numeric_pending_is_created_without_native_owner(tmp_path, monkeypatch) -> None:
    from src.solvers import task40_v30_selected_q_csr as selected_q

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
        np.asarray([[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 1j]], dtype=np.complex128)
    )
    native_calls = []

    def forbidden_native(**kwargs):
        native_calls.append(kwargs)
        raise AssertionError("saved-first numeric preparation must not build a native owner")

    monkeypatch.setattr(selected_q, "run_selected_q_native_actions", forbidden_native)
    result = prepare_saved_selected_q_numeric_pending(
        source=_ToySavedContributions(base),
        q_map=q4_map,
        q_index=4,
        twist_index=0,
        trace_rows=2,
        allocation_gate=lambda *_args: None,
        profile="saved-first-fixture",
        operator_identity={"fixture_operator": "q4"},
        matrix_source_identity={"source_sha": "a" * 40, "window_sha256": "b" * 64},
        execution_identity={"source_sha": "c" * 40, "window_sha256": "d" * 64},
        producer_identity={"kind": "saved_fixture"},
        output_directory=tmp_path / "q4_twist0",
        direct_hhat_evidence={
            "numeric_internal_support_empty": True,
            "internal_B_nnz": 0,
            "internal_D_nnz": 0,
        },
    )

    pending_path = tmp_path / "q4_twist0" / "task40_v30_q4_twist0_numeric_pending.json"
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    assert result["status"] == "NUMERIC_COMPLETE_NATIVE_PENDING"
    assert result["numeric_facts"]["numeric_fill_complete"] is True
    assert pending["status"] == "NUMERIC_COMPLETE_NATIVE_PENDING"
    assert pending["q_index"] == 4 and pending["twist_index"] == 0
    assert pending["shape"] == [3, 3]
    assert pending["csr_content_sha256"]
    assert not (pending_path.parent / "task40_v30_q4_twist0_csr_manifest.json").exists()
    assert not (pending_path.parent / "task40_v30_q4_twist0_native_qualification.json").exists()
    assert native_calls == []


def test_saved_q4_numeric_pending_reopens_without_repeating_pattern_or_fill(tmp_path, monkeypatch):
    from src.solvers import task40_v30_selected_q_csr as selected_q

    base = np.asarray(
        [[4 + 0.1j, 0.2, 0.1j, 0], [0.2, 5 - 0.1j, 0, 0.2j],
         [0.1j, 0, 1, 0.3], [0, 0.2j, 0.3, 2]], dtype=np.complex128
    )
    q4_map = sparse.csr_matrix(
        np.asarray([[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 1j]], dtype=np.complex128)
    )
    identity = {"fixture_operator": "q4"}
    source_identity = {"source_sha": "a" * 40, "window_sha256": "b" * 64}
    execution_identity = {"source_sha": "c" * 40, "window_sha256": "d" * 64}
    producer_identity = {"kind": "saved_fixture"}
    kwargs = dict(
        source=_ToySavedContributions(base), q_map=q4_map, q_index=4, twist_index=0,
        trace_rows=2, allocation_gate=lambda *_args: None, profile="saved-first-fixture",
        operator_identity=identity, matrix_source_identity=source_identity,
        execution_identity=execution_identity, producer_identity=producer_identity,
        output_directory=tmp_path / "q4_twist0",
        direct_hhat_evidence={"numeric_internal_support_empty": True,
                              "internal_B_nnz": 0, "internal_D_nnz": 0},
    )
    first = prepare_saved_selected_q_numeric_pending(**kwargs)
    pending_path = tmp_path / "q4_twist0" / "task40_v30_q4_twist0_numeric_pending.json"
    assert pending_path.with_name(pending_path.name + ".sha256").is_file()

    def forbidden_repeat(*_args, **_kwargs):
        raise AssertionError("a complete numeric-pending CSR must be reopened, not refilled")

    monkeypatch.setattr(selected_q, "build_saved_selected_q_pattern", forbidden_repeat)
    monkeypatch.setattr(selected_q, "fill_saved_selected_q_values", forbidden_repeat)
    reopened = prepare_saved_selected_q_numeric_pending(**kwargs)
    assert reopened["reopened"] is True
    assert reopened["numeric_pending"]["record_sha256"] == first["numeric_pending"]["record_sha256"]
    assert np.array_equal(reopened["matrix"].data, first["matrix"].data)

    changed = dict(kwargs)
    changed_execution = {"source_sha": "e" * 40, "window_sha256": "f" * 64}
    changed["execution_identity"] = changed_execution
    with pytest.raises(ValueError, match="V31 contract import authorization"):
        prepare_saved_selected_q_numeric_pending(**changed)
    authorization = make_v31_pending_import_authorization(
        first["numeric_pending"],
        pending_sha256=first["numeric_pending"]["record_sha256"],
        consumer_execution_identity=changed_execution,
    )
    changed["consumer_import_authorization"] = authorization
    consumed = prepare_saved_selected_q_numeric_pending(**changed)
    consumer_receipt = consumed["consumer_receipt"]
    assert consumer_receipt["reopened"] is False
    assert consumer_receipt["payload"]["producer_execution_identity"] == execution_identity
    assert consumer_receipt["payload"]["consumer_execution_identity"] == changed_execution
    assert consumer_receipt["payload"]["original_record_rewritten"] is False
    assert consumed["numeric_pending"]["record_sha256"] == first["numeric_pending"]["record_sha256"]
    assert consumed["consumer_receipt"]["path"] != consumed["numeric_pending"]["record_path"]

    changed_source = dict(kwargs)
    changed_source["matrix_source_identity"] = {
        "source_sha": "9" * 40,
        "window_sha256": source_identity["window_sha256"],
    }
    with pytest.raises(ValueError, match="identity differs"):
        prepare_saved_selected_q_numeric_pending(**changed_source)


def test_v32_q4_import_requires_exact_existing_pending_and_writes_receipt_to_new_root(
    tmp_path, monkeypatch
):
    from src.solvers import task40_v30_selected_q_csr as selected_q

    base = np.asarray(
        [[4 + 0.1j, 0.2, 0.1j, 0], [0.2, 5 - 0.1j, 0, 0.2j],
         [0.1j, 0, 1, 0.3], [0, 0.2j, 0.3, 2]], dtype=np.complex128
    )
    q4_map = sparse.csr_matrix(
        np.asarray([[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 1j]], dtype=np.complex128)
    )
    producer_identity = {"source_sha": "c" * 40, "window_sha256": "d" * 64}
    matrix_source_identity = {"source_sha": "a" * 40, "window_sha256": "b" * 64}
    profile = "v32-q4-import-fixture"
    profile_identity = {"name": profile, "trace_rows": 2}
    ordered_modes = (SimpleNamespace(side="bottom", m=0, n=0, polarization="s"),)
    scientific_input_sha256 = "7" * 64
    original_h = np.asarray([2.0, 3.0], dtype=np.complex128)
    operator_identity = selected_q_operator_identity(
        scientific_input_sha256=scientific_input_sha256,
        profile_identity=profile_identity,
        ordered_modes=ordered_modes,
        q_map=q4_map,
        original_h=original_h,
    )
    producer = _ToySavedContributions(base)
    producer_kwargs = dict(
        source=producer, q_map=q4_map, q_index=4, twist_index=0,
        trace_rows=2, allocation_gate=lambda *_args: None, profile=profile,
        operator_identity=operator_identity, matrix_source_identity=matrix_source_identity,
        execution_identity=producer_identity, producer_identity={"kind": "saved_fixture"},
        output_directory=tmp_path / "old_read_only" / "q4_twist0",
        direct_hhat_evidence={"numeric_internal_support_empty": True,
                              "internal_B_nnz": 0, "internal_D_nnz": 0},
    )
    first = prepare_saved_selected_q_numeric_pending(**producer_kwargs)
    pending = first["numeric_pending"]
    consumer_identity = {"source_sha": "e" * 40, "window_sha256": "f" * 64}
    consumer_root = tmp_path / "new_source" / "factor_bank" / "selected_q" / "q4_twist0"
    authorization = make_v32_q4_numeric_pending_import_authorization(
        pending_record_path=pending["record_path"],
        pending_record_sha256=pending["record_sha256"],
        csr_artifacts_sha256={
            name: str(row["sha256"]) for name, row in pending["csr_artifacts"].items()
        },
        producer_execution_identity=producer_identity,
        matrix_source_identity=matrix_source_identity,
        consumer_execution_identity=consumer_identity,
        consumer_output_root=consumer_root,
    )

    def forbidden_repeat(*_args, **_kwargs):
        raise AssertionError("REQUIRE_EXISTING_NUMERIC_PENDING must never call a producer/filler")

    monkeypatch.setattr(selected_q, "build_saved_selected_q_pattern", forbidden_repeat)
    monkeypatch.setattr(selected_q, "fill_saved_selected_q_values", forbidden_repeat)
    pending_path = Path(pending["record_path"])
    old_root = pending_path.parent.resolve()
    imported_files = [pending_path, pending_path.with_name(pending_path.name + ".sha256")]
    imported_files.extend(Path(row["path"]) for row in pending["csr_artifacts"].values())
    before_hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in imported_files}
    old_modes = {path: path.stat().st_mode & 0o777 for path in imported_files}
    for path in imported_files:
        path.chmod(0o444)
    atomic_json = selected_q._atomic_json

    def guard_old_root_writes(path, payload):
        assert not Path(path).resolve().is_relative_to(old_root)
        return atomic_json(path, payload)

    monkeypatch.setattr(selected_q, "_atomic_json", guard_old_root_writes)
    import_kwargs = dict(producer_kwargs)
    import_kwargs.update(
        source=None,
        execution_identity=consumer_identity,
        output_directory=consumer_root,
        numeric_pending_import_authorization=authorization,
    )
    import resource

    def measured_import(elapsed_seconds, peak_rss_kib):
        clock = iter((100.0, 100.0 + elapsed_seconds))
        with monkeypatch.context() as measurement_patch:
            measurement_patch.setattr(
                selected_q.time, "perf_counter", lambda: next(clock)
            )
            measurement_patch.setattr(
                resource,
                "getrusage",
                lambda _who: SimpleNamespace(ru_maxrss=peak_rss_kib),
            )
            return prepare_saved_selected_q_numeric_pending(**import_kwargs)

    try:
        imported = measured_import(0.25, 100)
        first_receipt = imported["consumer_receipt"]
        first_receipt_path = Path(first_receipt["path"])
        first_receipt_sha256 = hashlib.sha256(first_receipt_path.read_bytes()).hexdigest()
        assert first_receipt["reopened"] is False
        assert (
            first_receipt["payload"]["numeric_pending_import_execution"]["elapsed_seconds"]
            == 0.25
        )
        assert first_receipt["payload"]["numeric_pending_import_execution"][
            "process_lifetime_peak_rss_bytes_at_import_completion"
        ] == 100 * 1024

        imported_with_new_measurements = measured_import(0.5, 200)
        second_receipt = imported_with_new_measurements["consumer_receipt"]
        second_receipt_path = Path(second_receipt["path"])
        second_receipt_sha256 = hashlib.sha256(second_receipt_path.read_bytes()).hexdigest()
        assert second_receipt["reopened"] is False
        assert second_receipt_path != first_receipt_path
        assert (
            second_receipt["payload"]["numeric_pending_import_execution"]["elapsed_seconds"]
            == 0.5
        )
        assert second_receipt["payload"]["numeric_pending_import_execution"][
            "process_lifetime_peak_rss_bytes_at_import_completion"
        ] == 200 * 1024
        assert hashlib.sha256(first_receipt_path.read_bytes()).hexdigest() == first_receipt_sha256

        imported = measured_import(0.5, 200)
        reopened_receipt = imported["consumer_receipt"]
        assert reopened_receipt["reopened"] is True
        assert reopened_receipt["path"] == second_receipt["path"]
        assert reopened_receipt["sha256"] == second_receipt["sha256"]
        assert reopened_receipt["payload"] == second_receipt["payload"]
        assert hashlib.sha256(second_receipt_path.read_bytes()).hexdigest() == second_receipt_sha256

        wrong_consumer = dict(import_kwargs)
        wrong_consumer["execution_identity"] = {
            "source_sha": "9" * 40,
            "window_sha256": consumer_identity["window_sha256"],
        }
        with pytest.raises(ValueError, match="consumer identity/policy"):
            prepare_saved_selected_q_numeric_pending(**wrong_consumer)

        wrong_pending_authorization = dict(authorization)
        wrong_pending_authorization["pending_record_sha256"] = "0" * 64
        wrong_pending = dict(import_kwargs)
        wrong_pending["numeric_pending_import_authorization"] = wrong_pending_authorization
        with pytest.raises(ValueError, match="record hash differs"):
            prepare_saved_selected_q_numeric_pending(**wrong_pending)

        wrong_array_authorization = dict(authorization)
        wrong_array_hashes = dict(authorization["csr_artifacts_sha256"])
        wrong_array_hashes["indices"] = "0" * 64
        wrong_array_authorization["csr_artifacts_sha256"] = wrong_array_hashes
        wrong_array = dict(import_kwargs)
        wrong_array["numeric_pending_import_authorization"] = wrong_array_authorization
        with pytest.raises(ValueError, match="declaration escapes"):
            prepare_saved_selected_q_numeric_pending(**wrong_array)
    finally:
        for path, mode in old_modes.items():
            path.chmod(mode)
    after_hashes = {path: hashlib.sha256(path.read_bytes()).hexdigest() for path in imported_files}

    assert before_hashes == after_hashes
    assert imported["reopened"] is True
    assert imported["numeric_pending"]["record_path"] == pending["record_path"]
    assert imported["numeric_pending"]["record_sha256"] == pending["record_sha256"]
    assert imported["output_directory"] == str(consumer_root.resolve())
    assert imported["consumer_receipt"]["path"].startswith(str(consumer_root.resolve()))
    assert len(list(consumer_root.glob("task40_v32_q4_twist0_consumer_*.json"))) == 2
    receipt = imported["consumer_receipt"]
    assert Path(receipt["path"]).is_file()
    assert receipt["payload"]["original_record_rewritten"] is False
    assert receipt["payload"]["producer_execution_identity"] == producer_identity
    assert receipt["payload"]["consumer_execution_identity"] == consumer_identity
    import_facts = receipt["payload"]["numeric_pending_import_execution"]
    assert import_facts == imported["numeric_pending_import_execution"]
    assert import_facts["read_only"] is True
    assert import_facts["reopened_existing_pending"] is True
    assert import_facts["large_array_hashes_checked"] is True
    assert all(
        import_facts[key] == 0
        for key in (
            "producer_invocations",
            "route_build_invocations",
            "pattern_build_invocations",
            "numeric_fill_invocations",
        )
    )
    assert import_facts["elapsed_seconds"] >= 0
    assert "not an import-interval peak" in import_facts["peak_rss_scope"]
    assert selected_q._require_v31_pending_consumer_receipt(
        imported, consumer_execution_identity=consumer_identity
    )["payload"] == receipt["payload"]
    assert not list(Path(pending["record_path"]).parent.glob("*consumer_*.json"))

    matrix = imported["matrix"]
    full1 = np.asarray([1.0 + 0.2j, 2.0 - 0.3j, 3.0 + 0.4j], dtype=np.complex128)
    inputs = {
        "case1_full": full1,
        "case1_trace_only": np.asarray([full1[0], full1[1], 0.0], dtype=np.complex128),
        "case1_port_only": np.asarray([0.0, 0.0, full1[2]], dtype=np.complex128),
        "case2_full": np.asarray([0.4 + 0.7j, 0.9 - 0.5j, 1.7 + 0.1j], dtype=np.complex128),
    }
    csr_outputs = {name: np.asarray(matrix @ value) for name, value in inputs.items()}
    # Independent toy algebra from the saved 4x4 source and trace/port map.
    # This exercises serialization/reopen only; it is not an FE or scientific native pass.
    trace_map = q4_map[:2, :2].toarray()
    port_map = q4_map[2:, 2:].toarray()
    native_matrices = {
        "volume": np.zeros((3, 3), dtype=np.complex128),
        "-D": np.zeros((3, 3), dtype=np.complex128),
        "C": np.zeros((3, 3), dtype=np.complex128),
        "Hhat": np.zeros((3, 3), dtype=np.complex128),
    }
    native_matrices["volume"][:2, :2] = trace_map.conj().T @ base[:2, :2] @ trace_map
    native_matrices["C"][:2, 2:] = trace_map.conj().T @ base[:2, 2:] @ port_map
    native_matrices["-D"][2:, :2] = port_map.conj().T @ base[2:, :2] @ trace_map
    native_matrices["Hhat"][2:, 2:] = port_map.conj().T @ (
        base[2:, 2:] + np.diag(producer.local_h)
    ) @ port_map
    component_outputs = {
        name: {case: np.asarray(component @ vector) for case, vector in inputs.items()}
        for name, component in native_matrices.items()
    }
    native_outputs = {
        case: sum(
            (component_outputs[name][case] for name in ("volume", "-D", "C", "Hhat")),
            np.zeros(3, dtype=np.complex128),
        )
        for case in inputs
    }
    native_components = {
        "volume": component_outputs["volume"]["case1_full"],
        "minus_D": component_outputs["-D"]["case1_full"],
        "C": component_outputs["C"]["case1_full"],
        "Hhat": component_outputs["Hhat"]["case1_full"],
    }
    native_result = {
        **qualify_selected_q_native(
            matrix=matrix,
            inputs=inputs,
            csr_outputs=csr_outputs,
            native_outputs=native_outputs,
            native_components_case1=native_components,
            paired_leakage={"q_to_peer": {"relative": 0.0}, "peer_to_q": {"relative": 0.0}},
            trace_rows=2,
        ),
        "inputs": inputs,
        "csr_outputs": csr_outputs,
        "native_outputs": native_outputs,
        "native_components_case1": native_components,
        "paired_peer_input": np.asarray([1.0 + 0.2j, 0.5 + 0.4j], dtype=np.complex128),
        "paired_peer_native_diagonal": np.asarray([0.8 + 0.1j, 0.6 + 0.3j], dtype=np.complex128),
        "paired_peer_native_cross": np.zeros(3, dtype=np.complex128),
        "paired_selected_native_cross": np.zeros(2, dtype=np.complex128),
        "paired_peer_case2_cross": np.zeros(2, dtype=np.complex128),
        "native_input_seeds": {"case1_full": 1, "case2_full": 2},
    }
    finalize_kwargs = dict(
        matrix=matrix,
        pattern_record=imported["pattern_record"],
        numeric_facts=imported["numeric_facts"],
        native_result=native_result,
        output_directory=consumer_root,
        profile=profile,
        q_index=4,
        twist_index=0,
        q_map=q4_map,
        original_h=original_h,
        profile_identity=profile_identity,
        ordered_modes=ordered_modes,
        scientific_input_sha256=scientific_input_sha256,
        operator_identity=operator_identity,
        matrix_source_identity=matrix_source_identity,
        execution_identity=consumer_identity,
        producer_identity=producer_kwargs["producer_identity"],
        numeric_pending_import_authorization=authorization,
    )
    data_path = Path(imported["numeric_pending"]["csr_artifacts"]["data"]["path"])
    saved_data_bytes = data_path.read_bytes()
    try:
        tampered = np.load(data_path, mmap_mode="r+", allow_pickle=False)
        tampered[0] += 1.0
        tampered.flush()
        del tampered
        with pytest.raises(IOError, match="content hash differs from its authorization"):
            finalize_selected_q_csr(**finalize_kwargs)
    finally:
        data_path.write_bytes(saved_data_bytes)

    manifest, qualification, selector_entry = finalize_selected_q_csr(**finalize_kwargs)
    assert manifest["status"] == "COMPLETE_CSR"
    assert qualification["status"] == "PASS"
    assert manifest["numeric_pending_import"]["old_arrays_modified"] is False
    manifest_path = Path(selector_entry["csr_manifest"]["path"])
    from src.solvers.task40_v30_qualified_q_csr import (
        QualifiedQCSRProvider,
        V30_Q_CSR_SELECTOR_SCHEMA,
    )

    selector_path = consumer_root / "v32_q4_selector.json"
    selector_path.write_text(
        json.dumps(
            {
                "schema": V30_Q_CSR_SELECTOR_SCHEMA,
                "profile": profile,
                "q_csr_entries": [selector_entry],
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    selector_sha256 = hashlib.sha256(selector_path.read_bytes()).hexdigest()
    provider = QualifiedQCSRProvider(
        selector_path,
        selector_sha256=selector_sha256,
        repo_root=tmp_path,
        path_resolver=lambda raw: Path(raw).resolve(),
        allocation_gate=lambda *_args: None,
        numeric_pending_import_authorizations={"4": authorization},
    )
    reopened, provider_receipt = provider.load(
        4,
        0,
        expected_operator_identity=operator_identity,
        expected_execution_identity=consumer_identity,
        expected_q_map=q4_map,
        expected_original_h=original_h,
    )
    assert np.array_equal(reopened @ inputs["case2_full"], csr_outputs["case2_full"])
    assert provider_receipt["numeric_pending_import"]["old_arrays_modified"] is False
    assert provider_receipt["numeric_pending_import"]["read_only_import_root"] == str(old_root)

    # The next source consumes the existing COMPLETE CSR under its own
    # authorization while the manifest keeps the original numeric-import facts.
    from src.solvers.task40_v30_qualified_q_csr import (
        make_v31_q_csr_import_authorization,
    )

    next_consumer = {"source_sha": "9" * 40, "window_sha256": "8" * 64}
    next_numeric_root = (
        tmp_path / "next_source" / "factor_bank" / "selected_q" / "q4_twist0"
    )
    next_numeric_authorization = make_v32_q4_numeric_pending_import_authorization(
        pending_record_path=pending["record_path"],
        pending_record_sha256=pending["record_sha256"],
        csr_artifacts_sha256={
            name: str(row["sha256"]) for name, row in pending["csr_artifacts"].items()
        },
        producer_execution_identity=producer_identity,
        matrix_source_identity=matrix_source_identity,
        consumer_execution_identity=next_consumer,
        consumer_output_root=next_numeric_root,
    )
    complete_artifacts = {
        name: {
            "path": str(Path(row["path"]).resolve()),
            "bytes": int(row["bytes"]),
            "sha256": str(row["sha256"]),
        }
        for name, row in manifest["csr_artifacts"].items()
    }
    complete_authorization = make_v31_q_csr_import_authorization(
        q_index=4,
        twist_index=0,
        profile=profile,
        operator_identity=operator_identity,
        matrix_source_identity=manifest["matrix_source_identity"],
        producer_identity=manifest["producer_identity"],
        producer_execution_identity=manifest["execution_identity"],
        native_execution_identity=qualification["execution_identity"],
        csr_manifest_sha256=selector_entry["manifest_sha256"],
        native_qualification_sha256=selector_entry["native_qualification_sha256"],
        csr_artifacts=complete_artifacts,
        consumer_execution_identity=next_consumer,
    )
    historical_manifest_bytes = manifest_path.read_bytes()
    historical_authorization = manifest["numeric_pending_import"]["authorization"]
    next_provider = QualifiedQCSRProvider(
        selector_path,
        selector_sha256=selector_sha256,
        repo_root=tmp_path,
        path_resolver=lambda raw: Path(raw).resolve(),
        allocation_gate=lambda *_args: None,
        consumer_receipt_directory=tmp_path / "next_consumer_receipts",
        consumer_import_authorizations={"4": complete_authorization},
        numeric_pending_import_authorizations={"4": next_numeric_authorization},
    )
    next_matrix, next_receipt = next_provider.load(
        4,
        0,
        expected_operator_identity=operator_identity,
        expected_execution_identity=next_consumer,
        expected_q_map=q4_map,
        expected_original_h=original_h,
    )
    assert np.array_equal(next_matrix.toarray(), matrix.toarray())
    assert next_receipt["numeric_pending_import"]["authorization"] == historical_authorization
    assert next_receipt["consumer_receipt"]["payload"]["authorization"] == complete_authorization
    assert next_receipt["consumer_receipt"]["payload"]["consumer_execution_identity"] == next_consumer
    assert manifest_path.read_bytes() == historical_manifest_bytes


def test_v32_q4_import_rejects_consumer_output_nested_inside_read_only_import_root(tmp_path):
    from src.solvers.task40_v30_selected_q_csr import preflight_v32_q4_numeric_pending_import

    old_root = tmp_path / "old_import"
    pending_path = old_root / "task40_v30_q4_twist0_numeric_pending.json"
    output_root = old_root / "nested_consumer"
    authorization = make_v32_q4_numeric_pending_import_authorization(
        pending_record_path=pending_path,
        pending_record_sha256="1" * 64,
        csr_artifacts_sha256={name: "2" * 64 for name in ("data", "indices", "indptr")},
        producer_execution_identity={"source_sha": "a" * 40, "window_sha256": "b" * 64},
        matrix_source_identity={"source_sha": "c" * 40, "window_sha256": "d" * 64},
        consumer_execution_identity={"source_sha": "e" * 40, "window_sha256": "f" * 64},
        consumer_output_root=output_root,
    )
    with pytest.raises(ValueError, match="authorized locations"):
        preflight_v32_q4_numeric_pending_import(
            authorization,
            profile="fixture",
            execution_identity=authorization["consumer_execution_identity"],
            output_directory=output_root,
        )


@pytest.mark.parametrize("tamper", ("missing_record", "wrong_record_sha"))
def test_v32_q4_import_blocks_missing_or_wrong_hash_before_any_fallback(tmp_path, monkeypatch, tamper):
    from src.solvers import task40_v30_selected_q_csr as selected_q

    base = np.eye(4, dtype=np.complex128)
    q4_map = sparse.eye(4, 3, dtype=np.complex128, format="csr")
    producer_identity = {"source_sha": "c" * 40, "window_sha256": "d" * 64}
    matrix_source_identity = {"source_sha": "a" * 40, "window_sha256": "b" * 64}
    kwargs = dict(
        source=_ToySavedContributions(base), q_map=q4_map, q_index=4, twist_index=0,
        trace_rows=2, allocation_gate=lambda *_args: None, profile="v32-q4-fail-closed-fixture",
        operator_identity={"fixture_operator": "q4"},
        matrix_source_identity=matrix_source_identity, execution_identity=producer_identity,
        producer_identity={"kind": "saved_fixture"}, output_directory=tmp_path / "old" / "q4_twist0",
        direct_hhat_evidence={"numeric_internal_support_empty": True,
                              "internal_B_nnz": 0, "internal_D_nnz": 0},
    )
    first = prepare_saved_selected_q_numeric_pending(**kwargs)
    pending = first["numeric_pending"]
    consumer_identity = {"source_sha": "e" * 40, "window_sha256": "f" * 64}
    consumer_root = tmp_path / "new" / "q4_twist0"
    authorization = make_v32_q4_numeric_pending_import_authorization(
        pending_record_path=pending["record_path"],
        pending_record_sha256=pending["record_sha256"],
        csr_artifacts_sha256={name: row["sha256"] for name, row in pending["csr_artifacts"].items()},
        producer_execution_identity=producer_identity,
        matrix_source_identity=matrix_source_identity,
        consumer_execution_identity=consumer_identity,
        consumer_output_root=consumer_root,
    )
    if tamper == "missing_record":
        missing_root = tmp_path / "missing_import_root"
        authorization["pending_record_path"] = str(
            missing_root / "task40_v30_q4_twist0_numeric_pending.json"
        )
        authorization["import_root"] = str(missing_root)
    else:
        authorization["pending_record_sha256"] = "0" * 64
    allocation_calls = []

    def forbidden_repeat(*_args, **_kwargs):
        raise AssertionError("an invalid existing import must not route through pattern/fill")

    monkeypatch.setattr(selected_q, "build_saved_selected_q_pattern", forbidden_repeat)
    monkeypatch.setattr(selected_q, "fill_saved_selected_q_values", forbidden_repeat)
    import_kwargs = dict(kwargs)
    import_kwargs.update(
        source=None,
        execution_identity=consumer_identity,
        output_directory=consumer_root,
        allocation_gate=lambda *args: allocation_calls.append(args),
        numeric_pending_import_authorization=authorization,
    )
    with pytest.raises(ValueError):
        prepare_saved_selected_q_numeric_pending(**import_kwargs)
    assert allocation_calls == []
    assert not consumer_root.exists()


def test_partial_saved_q_numeric_data_restarts_from_zero_after_gate(tmp_path, monkeypatch):
    from src.solvers import task40_v30_selected_q_csr as selected_q

    base = np.asarray(
        [[4 + 0.1j, 0.2, 0.1j, 0], [0.2, 5 - 0.1j, 0, 0.2j],
         [0.1j, 0, 1, 0.3], [0, 0.2j, 0.3, 2]], dtype=np.complex128
    )
    q4_map = sparse.csr_matrix(
        np.asarray([[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 1j]], dtype=np.complex128)
    )
    kwargs = dict(
        source=_ToySavedContributions(base), q_map=q4_map, q_index=4, twist_index=0,
        trace_rows=2, allocation_gate=lambda *_args: None, profile="partial-restart-fixture",
        operator_identity={"fixture_operator": "q4"},
        matrix_source_identity={"source_sha": "a" * 40, "window_sha256": "b" * 64},
        execution_identity={"source_sha": "c" * 40, "window_sha256": "d" * 64},
        producer_identity={"kind": "saved_fixture"}, output_directory=tmp_path / "q4_twist0",
        direct_hhat_evidence={"numeric_internal_support_empty": True,
                              "internal_B_nnz": 0, "internal_D_nnz": 0},
    )
    original_fill = selected_q.fill_saved_selected_q_values
    partial_arrays = []

    def interrupted_fill(source, matrix, *args, **fill_kwargs):
        matrix.data[:] = 19.0 + 2.0j
        partial_arrays.append(matrix.data)
        raise RuntimeError("fixture interruption after partial numeric bytes")

    monkeypatch.setattr(selected_q, "fill_saved_selected_q_values", interrupted_fill)
    with pytest.raises(RuntimeError, match="partial numeric bytes"):
        prepare_saved_selected_q_numeric_pending(**kwargs)
    assert partial_arrays and np.all(partial_arrays[0] == 19.0 + 2.0j)
    pattern_checkpoint = tmp_path / "q4_twist0" / "task40_v31_q4_twist0_pattern.json"
    assert pattern_checkpoint.is_file()
    assert not (tmp_path / "q4_twist0" / "task40_v30_q4_twist0_numeric_pending.json").exists()

    gate_observations = []

    def observe_gate(label, facts):
        if label == "task40_v31_q4_pattern_reopen":
            gate_observations.append(("pattern", np.array(partial_arrays[0], copy=True)))
        elif label == "task40_v30_q4_preclear_csr_residency":
            gate_observations.append(("fill", np.array(partial_arrays[0], copy=True)))
            assert facts["clear_policy"] == "restart from exact zero; do not add onto partial values"

    kwargs["allocation_gate"] = observe_gate
    monkeypatch.setattr(selected_q, "fill_saved_selected_q_values", original_fill)
    reopened = prepare_saved_selected_q_numeric_pending(**kwargs)
    assert [label for label, _ in gate_observations] == ["pattern", "fill"]
    assert np.all(gate_observations[0][1] == 19.0 + 2.0j)
    assert np.all(gate_observations[1][1] == 19.0 + 2.0j)
    assert reopened["numeric_facts"]["numeric_fill_complete"] is True
    expected_local = base + np.diag(np.asarray([0, 0, 2, 3], dtype=np.complex128))
    expected = q4_map.toarray().conjugate().T @ expected_local @ q4_map.toarray()
    assert np.allclose(reopened["matrix"].toarray(), expected, rtol=0, atol=1e-14)


def test_worker_reference_boundary_runs_saved_q4_pending_before_builder(tmp_path):
    from src.runners.task40_v10_worker import _task40_v31_build_reference_after_q4_pending

    base = np.asarray(
        [[4 + 0.1j, 0.2, 0.1j, 0], [0.2, 5 - 0.1j, 0, 0.2j],
         [0.1j, 0, 1, 0.3], [0, 0.2j, 0.3, 2]], dtype=np.complex128
    )
    q4_map = sparse.csr_matrix(
        np.asarray([[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 1j]], dtype=np.complex128)
    )
    forbidden_calls = {"global_fe": 0, "native": 0, "factor": 0}
    pending_path = tmp_path / "q4_twist0" / "task40_v30_q4_twist0_numeric_pending.json"

    def prepare_saved_q4():
        return prepare_saved_selected_q_numeric_pending(
            source=_ToySavedContributions(base), q_map=q4_map, q_index=4, twist_index=0,
            trace_rows=2, allocation_gate=lambda *_args: None, profile="worker-boundary-fixture",
            operator_identity={"fixture_operator": "q4"},
            matrix_source_identity={"source_sha": "a" * 40, "window_sha256": "b" * 64},
            execution_identity={"source_sha": "c" * 40, "window_sha256": "d" * 64},
            producer_identity={"kind": "saved_fixture"}, output_directory=tmp_path / "q4_twist0",
            direct_hhat_evidence={"numeric_internal_support_empty": True,
                                  "internal_B_nnz": 0, "internal_D_nnz": 0},
        )

    def reference_builder(pending):
        assert pending["status"] == "NUMERIC_COMPLETE_NATIVE_PENDING"
        assert pending_path.is_file()
        assert forbidden_calls == {"global_fe": 0, "native": 0, "factor": 0}
        return {"builder_entered_after_pending": True}

    reference, pending = _task40_v31_build_reference_after_q4_pending(
        prepare_saved_q4=prepare_saved_q4,
        build_reference=reference_builder,
    )
    assert reference["builder_entered_after_pending"] is True
    assert pending["numeric_pending"]["status"] == "NUMERIC_COMPLETE_NATIVE_PENDING"


def test_twist_sector_native_preparation_reuses_owner_q_maps_without_rebuilding():
    from src.runners.task40_v10_worker import _task40_v30_resolve_sector_q_maps

    class Coordinates:
        def __init__(self):
            self.calls = []

        def q_map(self, branch, *, allocation_gate):
            self.calls.append((branch, allocation_gate))
            return f"built-{branch}"

    coordinates = Coordinates()
    allocation_gate = object()
    q0_map = object()
    q4_map = object()
    reused = _task40_v30_resolve_sector_q_maps(
        coordinates,
        (0, 4),
        allocation_gate=allocation_gate,
        prebuilt_q_maps_by_q={0: q0_map, 4: q4_map},
    )
    assert reused[0] is q0_map
    assert reused[4] is q4_map
    assert coordinates.calls == []

    rebuilt = _task40_v30_resolve_sector_q_maps(
        coordinates,
        (1, 5),
        allocation_gate=allocation_gate,
    )
    assert rebuilt == {1: "built-0", 5: "built-1"}
    assert coordinates.calls == [(0, allocation_gate), (1, allocation_gate)]
    with pytest.raises(ValueError, match="do not match"):
        _task40_v30_resolve_sector_q_maps(
            coordinates,
            (0, 4),
            allocation_gate=allocation_gate,
            prebuilt_q_maps_by_q={0: q0_map},
        )
    assert coordinates.calls == [(0, allocation_gate), (1, allocation_gate)]


@pytest.mark.parametrize("fail_q4_preparer", (False, True))
def test_real_worker_prefix_persists_q4_before_reference_and_calls_q1_q5_sector_callback(
    tmp_path, monkeypatch, fail_q4_preparer
):
    from types import SimpleNamespace

    from src.geometry import mesh_builder_3d
    from src.geometry.task40_nonseparable_plan import (
        TASK40_Q_ASSEMBLY_ROW_TILE_V17,
        TASK40_V15_REFERENCE_PC_STRATEGY,
    )
    from src.io import input_validation, physical_intermediate_profile
    from src.common.config_3d import SimulationConfig3D
    from src.runners import physical_p4_schur_v14, task40_v10_worker, task40_v30_contract
    from src.solvers import (
        fullspace_same_mesh_hcurl_pmg_global,
        fullspace_same_mesh_hcurl_pmg_physical,
        task40_v10_p6_mumps,
        task40_v10_p6_periodic_profile,
        task40_v10_p6_yorbit,
        task40_v20_mode_inventory,
        task40_v20_registry,
        task40_v30_selected_q_csr as selected_q,
    )

    profile_identity = physical_intermediate_profile.TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE
    actual_case = task40_v20_registry.task40_v20_case(profile=profile_identity)
    mode = SimpleNamespace(
        side="top", m=0, n=0, polarization="s", electric_tangential_norm_sq=1.0
    )
    global_modes = (mode,) * 32_060
    global_mode_rows = ({},) * 32_060
    mode_sha = "3" * 64
    ordered_mode_sha = "4" * 64
    scientific_sha = "1" * 64
    physical_sha = "2" * 64
    current_source = "c" * 40
    producer_source = "a" * 40
    producer_window = "b" * 64
    current_window = "d" * 64
    current_identity = {"source_sha": current_source, "window_sha256": current_window}

    class TinyProfile:
        name = "v31-real-worker-prefix-fixture"
        q_count = 8
        global_storage_rows = 4
        global_cell_axes = (1, 1, 1)
        mode_count = 32_060
        q_port_counts = (2, 1, 0, 0, 1, 1, 0, 0)
        sector_port_counts = (2, 1, 0, 0, 1, 1, 0, 0)
        trace_rows_per_q = 2

        @staticmethod
        def identity():
            return {"profile": "v31-real-worker-prefix-fixture", "degree": 6}

    profile = TinyProfile()
    q0_map = sparse.eye(4, dtype=np.complex128, format="csr")
    q4_map = sparse.csr_matrix(
        np.asarray([[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 1j]], dtype=np.complex128)
    )
    q1_map = sparse.csr_matrix(
        np.asarray([[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 1j]], dtype=np.complex128)
    )
    q5_map = sparse.csr_matrix(
        np.asarray([[1, 0, 0], [0, 1, 0], [0, 0, 1j], [0, 0, 1]], dtype=np.complex128)
    )
    original_h = np.full(7_932, 75_000.0 + 0j, dtype=np.complex128)
    active_lookup = np.asarray([0, 1, 2, -1], dtype=np.int32)
    producer_facts = {
        "producer_source_sha": producer_source,
        "producer_window_sha256": producer_window,
        "payload_sha256": {"v25_selected_q0_original_to_active_int32.npy": "5" * 64},
    }
    donor_source = _ToySavedContributions(
        np.asarray(
            [[4 + 0.1j, 0.2, 0.1j, 0], [0.2, 5 - 0.1j, 0, 0.2j],
             [0.1j, 0, 1, 0.3], [0, 0.2j, 0.3, 2]], dtype=np.complex128
        )
    )
    q4_donor = {
        "source": donor_source,
        "q0_map": q0_map,
        "q4_map": q4_map,
        "original_h": original_h,
        "active_lookup": active_lookup,
        "producer_facts": producer_facts,
    }
    fake_contract = {
        "execution": {
            "campaign_window_path": str((tmp_path / "window.json").resolve()),
            "campaign_window_sha256": current_window,
            "resources": {
                "task_memory_max_bytes": 1 << 30,
                "host_reserve_bytes": 0,
                "memory_swap_max_bytes": 0,
            },
            "window": {"total_seconds": 43_200.0, "closeout_reserve_seconds": 1_200.0},
        },
        "preparation": {"q_csr_worklist": [{"q": 4}]},
    }
    markers = []
    runtime_holder = {}

    class TinyRuntime:
        def __init__(self, *args, **kwargs):
            self.time_policy = "fixture"
            self.time_policy_facts = {}
            self.shared_budget = {}
            self.stop_requested = False
            self.events_path = Path(args[0]) / "events.jsonl"
            self.events_path.parent.mkdir(parents=True, exist_ok=True)
            self.marker_rows = markers
            runtime_holder["runtime"] = self

        def sample(self, _label, **_kwargs):
            return {
                "rss_bytes": 1,
                "launch_cap_bytes": 1 << 50,
                "memory_envelope": {"launch_cap_bytes": 1 << 50},
            }

        def check_projected(self, _label, _amount, *, workspace_bytes=0):
            return {"workspace_untouched_reserve_bytes": 0, "workspace_bytes": workspace_bytes}

        def marker(self, name, facts):
            self.marker_rows.append((name, dict(facts)))

        def set_phase(self, _phase):
            return None

    def forbidden(kind):
        def call(*_args, **_kwargs):
            forbidden_calls[kind] += 1
            raise AssertionError(f"unexpected {kind} hook before saved-first boundary")

        return call

    forbidden_calls = {"fe_jit": 0, "native": 0, "factor": 0}
    monkeypatch.setenv("TASK40_V30_STRICT_EXECUTION", "1")
    monkeypatch.setenv("TASK40_V30_CONTRACT_PATH", str(tmp_path / "contract.json"))
    monkeypatch.setenv("TASK40_V30_CONTRACT_SHA256", "6" * 64)
    monkeypatch.setenv(
        "TASK40_V30_EXECUTION_WINDOW_PATH",
        fake_contract["execution"]["campaign_window_path"],
    )
    monkeypatch.setenv("TASK40_V30_EXECUTION_WINDOW_SHA256", current_window)
    monkeypatch.setenv("TASK40_V30_TASK_MEMORY_MAX_BYTES", str(1 << 30))
    monkeypatch.setenv("TASK40_V30_HOST_RESERVE_BYTES", "0")
    monkeypatch.setenv("TASK40_V30_MEMORY_SWAP_MAX_BYTES", "0")
    monkeypatch.setattr(
        task40_v30_contract,
        "require_authorized_contract",
        lambda *_args, **_kwargs: (fake_contract, "6" * 64),
    )
    monkeypatch.setattr(
        task40_v30_contract,
        "require_v30_input_identity",
        lambda *_args, **_kwargs: {
            "staged_input_sha256": scientific_sha,
            "scientific_input_sha256": scientific_sha,
        },
    )
    monkeypatch.setattr(
        physical_intermediate_profile,
        "profile_facts",
        lambda _identity: {"resources": {"process_tree_rss_cap_bytes": 1 << 30}},
    )
    monkeypatch.setattr(physical_p4_schur_v14, "_V14Runtime", TinyRuntime)
    monkeypatch.setattr(physical_p4_schur_v14, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(physical_p4_schur_v14, "_abi_facts", lambda **_kwargs: {"fixture": True})
    monkeypatch.setattr(
        task40_v10_worker,
        "_candidate_contract",
        lambda *_args, **_kwargs: {"campaign_window_sha256": current_window},
    )
    monkeypatch.setattr(
        task40_v10_worker,
        "_v12_memory_admission_bounds",
        lambda **_kwargs: {
            "total_rss_inequality_passed": True,
            "incremental_headroom_inequality_passed": True,
            "projected_process_tree_rss_bytes": 1,
            "projected_incremental_capacity_bytes": 1,
        },
    )
    monkeypatch.setattr(
        task40_v10_worker,
        "_event_file_identity",
        lambda _path: {
            "allocation_admission_event_count": sum(
                name == "v10_strict_allocation_admission" for name, _facts in markers
            ),
            "allocation_admission_complete_event_count": sum(
                name == "v10_strict_allocation_admission_complete" for name, _facts in markers
            ),
        },
    )
    monkeypatch.setattr(
        input_validation,
        "simulation_config_3d_from_normalized",
        lambda _payload: SimulationConfig3D(
            mesh_axis_cell_counts=profile.global_cell_axes,
            period_x=600.0,
            period_y=500.0,
        ),
    )
    monkeypatch.setattr(
        task40_v20_registry,
        "task40_v20_case",
        lambda **_kwargs: actual_case,
    )
    monkeypatch.setattr(
        task40_v20_mode_inventory,
        "load_v20_target_mode_inventory",
        lambda _payload: (
            global_modes,
            global_mode_rows,
            mode_sha,
            {"ordered_mode_key_sha256": ordered_mode_sha},
        ),
    )
    monkeypatch.setattr(
        task40_v10_p6_periodic_profile,
        "TASK40_P6_PERIODIC_PROFILES",
        {profile_identity: profile},
    )
    monkeypatch.setattr(
        mesh_builder_3d,
        "_stage4_axis_plan",
        lambda *_args, **_kwargs: SimpleNamespace(
            x_values=(0.0, 1.0), y_values=(0.0, 1.0), z_values=(0.0, 1.0)
        ),
    )
    monkeypatch.setattr(
        task40_v10_worker,
        "_task40_v30_q_csr_provider",
        lambda *_args, **_kwargs: SimpleNamespace(
            entries={0: {"q_index": 0}},
            selector_path=tmp_path / "selector.json",
            selector_sha256="7" * 64,
            profile=profile_identity,
        ),
    )
    monkeypatch.setattr(
        task40_v10_worker,
        "_task40_v30_open_saved_q4_source",
        lambda **_kwargs: dict(q4_donor),
    )
    monkeypatch.setattr(
        task40_v10_worker,
        "_task40_v30_q4_direct_hhat_evidence",
        lambda **_kwargs: {
            "numeric_internal_support_empty": True,
            "internal_B_nnz": 0,
            "internal_D_nnz": 0,
            "witness": "tiny worker fixture",
        },
    )
    monkeypatch.setattr(
        task40_v10_worker,
        "_task40_v30_sector_builder_inputs",
        lambda **_kwargs: {
            "trace_rows_by_q": {1: 2, 5: 2},
            "mode_manifest_sha256": mode_sha,
        },
    )
    monkeypatch.setattr(
        selected_q,
        "LiveP6SelectedQContributionSource",
        lambda *_args, **_kwargs: SimpleNamespace(kind="tiny-live-source"),
    )

    class SectorCallbackReached(Exception):
        pass

    class Q4NativePrepareFailure(Exception):
        pass

    callback_events = []

    twist0_mode_indices = np.arange(7_932, dtype=np.int64)
    twist0_branches = np.ones(7_932, dtype=np.int8)
    twist0_branches[:4_076] = 0
    twist0_context = SimpleNamespace(
        twist_index=0,
        global_q_indices=(0, 4),
        local_axes={"x": (0.0, 1.0), "y": (0.0, 1.0), "z": (0.0, 1.0)},
        original_mode_indices=twist0_mode_indices,
        local_branch_indices=twist0_branches,
    )
    cleanup_counts = {"action": 0, "bundle_action": 0, "mpc": 0, "bank": 0}

    def counted_destroy(name):
        def destroy():
            cleanup_counts[name] += 1

        return destroy

    class CountedBank:
        def __init__(self):
            self._closed = False

        def close(self):
            if self._closed:
                raise AssertionError("shared transform bank was closed twice")
            cleanup_counts["bank"] += 1
            self._closed = True

    transform_bank = CountedBank()
    fake_mpc = SimpleNamespace(destroy=counted_destroy("mpc"))
    fake_bundle_action = SimpleNamespace(destroy=counted_destroy("bundle_action"))
    twist0_action = SimpleNamespace(
        reduced_size=4,
        destroy=counted_destroy("action"),
        condensed=SimpleNamespace(
            comm=None,
            full_rows=4,
            active_rows=2,
            trace_constraints=SimpleNamespace(original_to_active={0: 0, 1: 1, 2: 2}),
        ),
    )
    twist0_coordinates = SimpleNamespace(
        width=2,
        q_map=lambda branch, *, allocation_gate: (q0_map, q4_map)[branch],
    )
    twist0_local_owner = {
        "context": twist0_context,
        "levels": {"floquets": {6: SimpleNamespace(mpc=fake_mpc)}},
        "bundle": {"volume_action": object(), "action": fake_bundle_action},
        "system": None,
        "action": twist0_action,
        "entities": object(),
        "transport": None,
        "coordinates": twist0_coordinates,
        "local_modes": (mode,) * 7_932,
        "mode_inventory": ((mode,) * 7_932, ({},) * 7_932, mode_sha),
        "local_h": original_h.real.copy(),
        "global_h_sha256": hashlib.sha256(
            np.ascontiguousarray(np.full(32_060, 300_000.0, dtype=np.float64))
            .view(np.uint8)
        ).hexdigest(),
        "transform_bank": transform_bank,
        "owner_receipt": {
            "schema": "task40extra.review_v31_twist0_local_owner.v1",
            "created_before_global_reference": True,
        },
    }

    monkeypatch.setattr(
        task40_v10_p6_yorbit,
        "build_task40_v10_sector_contexts",
        lambda *_args, **_kwargs: (twist0_context,),
    )

    def build_local_owner_fixture(*_args, **kwargs):
        assert kwargs["global_h"].shape == (32_060,)
        assert np.array_equal(kwargs["global_h"], np.full(32_060, 300_000.0))
        return twist0_local_owner

    monkeypatch.setattr(
        task40_v10_p6_yorbit,
        "build_task40_v10_p6_local_sector_owner",
        build_local_owner_fixture,
    )
    monkeypatch.setattr(
        task40_v10_worker,
        "_task40_v31_bind_saved_q4_to_live",
        lambda *_args, **_kwargs: {"status": "PASS_LIVE_MAP_H_LOOKUP_BOUND"},
    )
    monkeypatch.setattr(
        task40_v10_worker,
        "_task40_v30_open_saved_q4_native_witness",
        lambda **_kwargs: {"schema": "fixture_saved_native_witness"},
    )
    monkeypatch.setattr(
        task40_v10_p6_yorbit,
        "_task40_v30_load_sector_q_csr_pair",
        lambda *_args, **_kwargs: (
            {0: sparse.eye(4, dtype=np.complex128, format="csr")},
            {
                "qualification_receipts": [{"q_index": 0, "qualification_status": "PASS"}],
                "selector_entries": [{"q_index": 0, "qualification_status": "PASS"}],
            },
        ),
    )

    def stop_at_real_selected_q_callback(**kwargs):
        selected_qs = set(kwargs["producer_identity_by_q"])
        assert selected_qs in ({1, 5}, {4})
        for q_index, row in kwargs["producer_identity_by_q"].items():
            if q_index == 4:
                assert row["producer_source_sha"] == producer_source
                assert row["producer_window_sha256"] == producer_window
            else:
                assert row["ordered_mode_manifest_sha256"] == mode_sha
                assert row["source_sha"] == current_source
                assert row["window_sha256"] == current_window
        if selected_qs == {4}:
            callback_events.append("real_q4_callback_inputs_ready")
            assert kwargs["original_h"].shape == (7_932,)
            if fail_q4_preparer:
                raise Q4NativePrepareFailure("fixture q4 preparer/native failure")
            return (
                {4: sparse.eye(3, dtype=np.complex128, format="csr")},
                {
                    "all_complete_native_pass": True,
                    "qualification_receipts": [
                        {"q_index": 4, "qualification_status": "PASS"}
                    ],
                    "selector_entries": [
                        {"q_index": 4, "qualification_status": "PASS"}
                    ],
                },
            )
        callback_events.append("real_q1_q5_callback_inputs_ready")
        raise SectorCallbackReached

    monkeypatch.setattr(
        selected_q,
        "prepare_selected_q_csr_sector",
        stop_at_real_selected_q_callback,
    )
    monkeypatch.setattr(selected_q, "run_selected_q_native_actions", forbidden("native"))
    monkeypatch.setattr(task40_v10_p6_mumps, "AllQExactMumps", forbidden("factor"))
    monkeypatch.setattr(
        fullspace_same_mesh_hcurl_pmg_global,
        "_build_same_mesh_levels",
        forbidden("fe_jit"),
    )
    monkeypatch.setattr(
        fullspace_same_mesh_hcurl_pmg_physical,
        "build_same_mesh_physical_action",
        forbidden("fe_jit"),
    )
    monkeypatch.setattr(
        fullspace_same_mesh_hcurl_pmg_physical,
        "build_physical_rhs",
        forbidden("fe_jit"),
    )
    from dolfinx import fem

    monkeypatch.setattr(fem, "form", forbidden("fe_jit"))

    def build_reference_after_pending(*_args, **kwargs):
        pending_path = (
            Path(kwargs["factor_output_directory"])
            / "selected_q/q4_twist0/task40_v30_q4_twist0_numeric_pending.json"
        )
        saved = json.loads(pending_path.read_text(encoding="utf-8"))
        assert saved["status"] == "NUMERIC_COMPLETE_NATIVE_PENDING"
        markers_seen = [name for name, _facts in markers]
        assert "task40_v31_q4_numeric_pending_complete" in markers_seen
        assert kwargs["prebuilt_sector_owners"][0] is twist0_local_owner
        assert set(kwargs["prebuilt_sector_q_csr"][0][0]) == {0, 4}
        assert kwargs["prebuilt_sector_q_csr"][0][1][
            "native_owner_created_before_global_reference"
        ] is True
        callback_events.append("reference_builder_entered_after_pending")
        callback = kwargs["qualified_q_csr_preparer"]
        action = SimpleNamespace(
            reduced_size=4,
            condensed=SimpleNamespace(
                comm=None,
                full_rows=4,
                trace_constraints=SimpleNamespace(original_to_active={0: 0, 1: 1, 2: 2}),
            ),
        )
        callback(
            provider=SimpleNamespace(entries={0: {}}),
            action=action,
            volume_action=object(),
            coordinates=SimpleNamespace(
                q_map=lambda branch, *, allocation_gate: (q1_map, q5_map)[branch]
            ),
            context=SimpleNamespace(global_q_indices=(1, 5), twist_index=1),
            local_h=original_h,
            profile=profile,
            global_bundle={"modes": (mode,), "mode_sha256": mode_sha, "mode_rows": ()},
            local_bundle={},
            mode_inventory=((mode,), (), mode_sha),
            q_indices=(1, 5),
            available_sector_matrices={},
            runtime_identity={
                "scientific_input_sha256": scientific_sha,
                "execution_identity": current_identity,
            },
            allocation_gate=lambda *_args: None,
        )
        raise AssertionError("the q1/q5 callback fixture should stop at the callback boundary")

    monkeypatch.setattr(
        task40_v10_p6_yorbit,
        "build_task40_v10_p6_reference_inverse",
        build_reference_after_pending,
    )

    v30_factor_config = {
        "schema": "task40extra.review_v30_all_q_factor_bank.v1",
        "output_directory": str(tmp_path / "factor_output"),
    }
    payload = {
        "run_id": actual_case.run_id,
        "solver": {
            "preconditioner": profile_identity,
            "stage": actual_case.solver_stage,
            "task40_reference_pc_strategy": TASK40_V15_REFERENCE_PC_STRATEGY,
            "task40_q_assembly_strategy": TASK40_Q_ASSEMBLY_ROW_TILE_V17,
            "task40_factor_lifecycle_strategy": "ALL_Q_RESIDENT",
        },
        "provenance": {
            "input_sha256": scientific_sha,
            "physical_model_sha256": physical_sha,
            "source_path": str(tmp_path / "input.dat"),
        },
    }
    v30_binding = {
        "schema": "task40extra.review_v30_q_csr_worker_binding.v1",
        "selector_path": str(tmp_path / "selector.json"),
        "selector_sha256": "7" * 64,
    }
    expected_failure = Q4NativePrepareFailure if fail_q4_preparer else SectorCallbackReached
    with pytest.raises(expected_failure):
        task40_v10_worker.run_task40_v10_p6_reference_worker(
            payload,
            tmp_path / "run",
            source_sha=current_source,
            profile_identity=profile_identity,
            share_transform_bank=True,
            v30_q_csr_binding=v30_binding,
            v30_factor_config=v30_factor_config,
            v30_requested_factor_lifecycle_strategy="ONE_Q_REFACTOR_V19",
            v30_effective_factor_lifecycle_strategy="ALL_Q_RESIDENT",
        )
    if fail_q4_preparer:
        assert callback_events == ["real_q4_callback_inputs_ready"]
    else:
        assert callback_events == [
            "real_q4_callback_inputs_ready",
            "reference_builder_entered_after_pending",
            "real_q1_q5_callback_inputs_ready",
        ]
    assert forbidden_calls == {"fe_jit": 0, "native": 0, "factor": 0}
    cleanup_marker = next(
        facts
        for name, facts in reversed(markers)
        if name == "task40_v31_twist0_local_owner_cleanup"
    )
    assert cleanup_marker["status"] == "RELEASED"
    assert cleanup_marker["handover_status"] == (
        "TWIST0_LOCAL_OWNER_AWAITING_Q4_NATIVE"
        if fail_q4_preparer
        else "REFERENCE_BUILDER_FAILED"
    )
    assert cleanup_marker["reference_builder_returned"] is False
    assert cleanup_marker["reference_object_present_during_finally"] is False
    assert twist0_local_owner["owner_receipt"]["global_h_mode_count"] == 32_060
    assert twist0_local_owner["owner_receipt"]["saved_local_h_count"] == 7_932
    assert twist0_local_owner["owner_receipt"]["local_h_matches_saved_owner_exactly"] is True
    assert twist0_local_owner["owner_receipt"]["global_h_bound_to_current_carrier_identity"] is True
    assert cleanup_counts == {"action": 1, "bundle_action": 1, "mpc": 1, "bank": 1}


def test_reference_destroy_owns_prebuilt_twist0_and_worker_cleanup_is_idempotent():
    from src.solvers.task40_v10_p6_yorbit import (
        destroy_task40_v10_p6_local_sector_owner,
        destroy_task40_v10_p6_reference_inverse,
    )

    calls = {"owner_action": 0, "bundle_action": 0, "bank": 0}

    def counted(name):
        def destroy():
            calls[name] += 1

        return destroy

    class Bank:
        _closed = False

        def close(self):
            if self._closed:
                raise AssertionError("reference and worker both closed the shared bank")
            calls["bank"] += 1
            self._closed = True

    bank = Bank()
    sector = {
        "system": None,
        "action": SimpleNamespace(destroy=counted("owner_action")),
        "bundle": {"action": SimpleNamespace(destroy=counted("bundle_action"))},
        "levels": {"floquets": {}},
        "q_maps_by_q": {0: object(), 4: object()},
        "transform_bank": bank,
        "owner_receipt": {
            "owner_identity": "twist0:local_action_recovery_entities",
            "handover_status": "REFERENCE_OWNS_LOCAL_SECTOR",
        },
    }
    reference = {
        "inverse": None,
        "factors": None,
        "sectors": [sector],
        "global_bundle": None,
        "global_levels": None,
        "global_entities": None,
        "full_layout": None,
        "transform_bank": bank,
    }

    destroy_task40_v10_p6_reference_inverse(reference)
    receipt = destroy_task40_v10_p6_local_sector_owner(
        sector,
        close_transform_bank=True,
    )

    assert receipt["status"] == "RELEASED"
    assert receipt["transform_bank_released"] is True
    assert receipt["transform_bank_status"] == "RELEASED"
    assert receipt["q_maps_released"] is True
    assert sector["q_maps_by_q"] is None
    assert sector["transform_bank"] is None
    assert calls == {"owner_action": 1, "bundle_action": 1, "bank": 1}


def test_saved_surface_native_owner_builds_and_releases_real_complex_action(tmp_path):
    """Exercise the production saved-stream adapter with a tiny no-FE algebra fixture."""
    import struct

    from mpi4py import MPI
    from petsc4py import PETSc

    from src.solvers.hcurl_assembly_time_condensation import (
        AssemblyTimeCondensedSystem,
        TraceConstraintMap,
    )

    stream_path = tmp_path / "saved_surface.bin"
    lookup_path = tmp_path / "active_lookup.npy"
    selected = np.asarray([0, 1], dtype=np.int64)
    h_values = np.asarray([2.5, 4.0], dtype=np.float64)
    mode_records = (
        {
            "b_rows": np.asarray([0], dtype="<i4"),
            "b_values": np.asarray([2.0 + 1.0j], dtype="<c16"),
            "d_rows": np.asarray([1], dtype="<i4"),
            "d_values": np.asarray([0.5 - 0.25j], dtype="<c16"),
        },
        {
            "b_rows": np.asarray([1], dtype="<i4"),
            "b_values": np.asarray([-0.75 + 0.4j], dtype="<c16"),
            "d_rows": np.asarray([0], dtype="<i4"),
            "d_values": np.asarray([1.2 + 0.3j], dtype="<c16"),
        },
    )
    with stream_path.open("wb") as stream:
        for index, (h_value, record) in enumerate(zip(h_values, mode_records, strict=True)):
            stream.write(
                task40_v25_selected_q0._SURFACE_STREAM_HEADER.pack(
                    index,
                    len(record["b_rows"]),
                    len(record["d_rows"]),
                    float(h_value),
                )
            )
            for name in ("b_rows", "b_values", "d_rows", "d_values"):
                stream.write(record[name].tobytes())
    stream_sha256 = hashlib.sha256(stream_path.read_bytes()).hexdigest()
    np.save(lookup_path, np.asarray([0, 1], dtype=np.int32), allow_pickle=False)

    constraints = TraceConstraintMap(
        owned_active_original_dofs=np.asarray([0, 1], dtype=PETSc.IntType),
        original_to_active={0: 0, 1: 1},
        expansion_by_original={},
        full_trace_rows=2,
        active_rows=2,
        slave_rows=0,
        owned_active_range=(0, 2),
        build_audit={},
    )
    condensed = AssemblyTimeCondensedSystem(
        matrix=None,
        owned_trace_original_dofs=np.asarray([0, 1], dtype=PETSc.IntType),
        original_to_trace={0: 0, 1: 1},
        trace_constraints=constraints,
        cell_recovery_maps=(),
        interior_from_trace_by_class={},
        interior_lu_by_class={},
        interior_rhs_projection_by_class={},
        interior_solution_embedding_by_class={},
        trace_from_interior_rhs_by_class={},
        interior_residual_projection_by_class={},
        full_rows=2,
        trace_rows=2,
        active_rows=2,
        appended_rows=2,
        interior_rows=0,
        active_interior_rows=0,
        build_audit={},
        comm=MPI.COMM_SELF,
        owned_active_rows=2,
        owned_appended_rows=2,
        retained_local_schur_by_class={},
    )
    original_destroy = condensed.destroy
    destroy_count = {"condensed": 0}

    def counted_condensed_destroy():
        destroy_count["condensed"] += 1
        original_destroy()

    condensed.destroy = counted_condensed_destroy

    class VolumeAction:
        audit = {"fixture": "volume-only-no-fe"}

        def __init__(self):
            self.destroy_count = 0

        def destroy(self):
            self.destroy_count += 1

    volume_action = VolumeAction()
    modes = (
        SimpleNamespace(side="top", m=0, n=0, polarization="s"),
        SimpleNamespace(side="bottom", m=1, n=-1, polarization="p"),
    )
    full_mode_rows = ({"identity": "mode-0"}, {"identity": "mode-1"})
    support_seen = []
    stage_events = []

    def support_audit(lookup):
        support_seen.append(np.asarray(lookup).copy())
        return {
            "path": str(stream_path.resolve()),
            "sha256": stream_sha256,
            "numeric_internal_support_empty": True,
            "internal_nonzero_entry_count": {"B": 0, "D": 0},
            "mode_count": 2,
        }

    owner = task40_v25_selected_q0.build_saved_surface_native_owner(
        condensed=condensed,
        volume_action=volume_action,
        surface_stream_path=stream_path,
        surface_stream_sha256=stream_sha256,
        selected_indices=selected,
        local_modes=modes,
        local_h=h_values,
        full_mode_rows=full_mode_rows,
        active_lookup_path=lookup_path,
        interior_rows=np.empty(0, dtype=np.int64),
        numeric_internal_support_evidence={
            "numeric_internal_support_empty": True,
            "internal_B_nnz": 0,
            "internal_D_nnz": 0,
        },
        surface_support_audit=support_audit,
        producer_identity_sha256="a" * 64,
        global_mode_sha256="b" * 64,
        allocation_gate=lambda *_args, **_kwargs: None,
        stage_callback=stage_events.append,
        owns_condensed=True,
    )

    action = owner["action"]
    assert action.condensed is condensed
    assert action.owns_condensed is True
    assert action.audit["global_direct_provider_enabled"] is True
    assert owner["owner_receipt"]["native_owner_action_uses_exact_condensed_object"] is True
    np.testing.assert_array_equal(support_seen[0], np.asarray([0, 1], dtype=np.int32))

    source = np.asarray(
        [1.1 - 0.7j, -0.4 + 0.9j, 0.3 + 0.5j, -1.0 + 0.2j],
        dtype=np.complex128,
    )
    expected = np.asarray(
        [
            mode_records[0]["b_values"][0] * source[2],
            mode_records[1]["b_values"][0] * source[3],
            -mode_records[0]["d_values"][0] * source[1] + h_values[0] * source[2],
            -mode_records[1]["d_values"][0] * source[0] + h_values[1] * source[3],
        ],
        dtype=np.complex128,
    )
    np.testing.assert_allclose(action.apply(source), expected, rtol=0.0, atol=1e-14)

    class Vector:
        def __init__(self, values):
            self.values = np.asarray(values, dtype=np.complex128).copy()

        def getArray(self, readonly=False):
            return self.values

        def getSize(self):
            return len(self.values)

    saved_dtn = owner["saved_dtn_action"]
    dtn_result = Vector(np.zeros(2, dtype=np.complex128))
    saved_dtn.apply(Vector(source[:2]), dtn_result)
    expected_dtn = np.asarray(
        [
            mode_records[0]["b_values"][0]
            * np.dot(mode_records[0]["d_values"], source[[1]])
            / h_values[0],
            mode_records[1]["b_values"][0]
            * np.dot(mode_records[1]["d_values"], source[[0]])
            / h_values[1],
        ],
        dtype=np.complex128,
    )
    np.testing.assert_allclose(dtn_result.values, expected_dtn, rtol=0.0, atol=1e-14)
    np.testing.assert_allclose(
        saved_dtn.recover_auxiliary(Vector(source[:2])),
        np.asarray(
            [
                np.dot(mode_records[0]["d_values"], source[[1]]) / h_values[0],
                np.dot(mode_records[1]["d_values"], source[[0]]) / h_values[1],
            ],
            dtype=np.complex128,
        ),
        rtol=0.0,
        atol=1e-14,
    )
    modal_rhs = Vector(np.zeros(2, dtype=np.complex128))
    saved_dtn.apply_modal_rhs(source[2:], modal_rhs)
    np.testing.assert_allclose(
        modal_rhs.values,
        np.asarray(
            [
                mode_records[0]["b_values"][0] * source[2],
                mode_records[1]["b_values"][0] * source[3],
            ]
        ),
        rtol=0.0,
        atol=1e-14,
    )
    assert any(
        event.get("phase") == "saved_port_provider_action_binding"
        and event.get("status") == "COMPLETE"
        for event in stage_events
    )

    provider_sweeps_before_cleanup = int(
        owner["provider_sweep_counter"]["provider_sweep_count"]
    )
    owner["bundle"]["action"].destroy()
    action.destroy()
    assert volume_action.destroy_count == 1
    assert saved_dtn._destroyed is True
    assert saved_dtn.audit["mode_count"] == 2
    assert saved_dtn.audit["provider_sweep_count"] == provider_sweeps_before_cleanup
    assert destroy_count == {"condensed": 1}
    assert condensed._destroyed is True


def test_reference_builder_failure_releases_prebuilt_twist0_owner_once(monkeypatch):
    from types import SimpleNamespace

    from src.common.config_3d import SimulationConfig3D
    from src.solvers import fullspace_same_mesh_hcurl_pmg_global
    from src.solvers.task40_v10_p6_periodic_profile import (
        TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE,
    )
    from src.solvers.task40_v10_p6_yorbit import (
        Task40V10SectorContext,
        build_task40_v10_p6_reference_inverse,
    )

    profile = TASK40_V20_P6_TARGET_ORIGINAL_NY8_PROFILE
    cfg = SimulationConfig3D(
        nedelec_degree=6,
        mesh_axis_cell_counts=profile.global_cell_axes,
        geometry_identity="task40_v31_failure_fixture",
    )
    axes = {
        "x": tuple(np.linspace(0.0, cfg.period_x, profile.global_cell_axes[0] + 1)),
        "y": tuple(np.linspace(0.0, cfg.period_y, profile.global_cell_axes[1] + 1)),
        "z": tuple(np.linspace(cfg.z_min, cfg.z_max, profile.global_cell_axes[2] + 1)),
    }
    calls = {"owner_action": 0, "bundle_action": 0, "mpc": 0, "bank": 0}

    def counted(name):
        def destroy():
            calls[name] += 1

        return destroy

    class Bank:
        def __init__(self):
            self._closed = False

        def close(self):
            if self._closed:
                raise AssertionError("failed reference builder double-closed the bank")
            calls["bank"] += 1
            self._closed = True

    bank = Bank()
    context = Task40V10SectorContext(
        twist_index=0,
        eta=1.0 + 0.0j,
        tau=1.0 + 0.0j,
        global_q_indices=(0, 4),
        local_axes=axes,
        original_mode_indices=np.asarray([0], dtype=np.int64),
        local_branch_indices=np.asarray([0], dtype=np.int8),
    )
    owner = {
        "context": context,
        "levels": {
            "floquets": {
                6: SimpleNamespace(
                    mpc=SimpleNamespace(destroy=counted("mpc"))
                )
            }
        },
        "bundle": {"action": SimpleNamespace(destroy=counted("bundle_action"))},
        "action": SimpleNamespace(destroy=counted("owner_action")),
        "system": None,
        "transform_bank": bank,
        "owner_receipt": {"created_before_global_reference": True},
    }

    class GlobalSetupFailure(Exception):
        pass

    def fail_global_setup(*_args, **_kwargs):
        raise GlobalSetupFailure("fixture fails after reference builder accepts owner")

    monkeypatch.setattr(
        fullspace_same_mesh_hcurl_pmg_global,
        "_build_same_mesh_levels",
        fail_global_setup,
    )
    with pytest.raises(GlobalSetupFailure):
        build_task40_v10_p6_reference_inverse(
            cfg,
            axes,
            allocation_gate=lambda *_args, **_kwargs: None,
            profile=profile,
            share_transform_bank=True,
            prebuilt_sector_owners={0: owner},
        )

    assert owner["local_owner_cleanup_complete"] is True
    assert owner["local_owner_cleanup_receipt"]["status"] == "RELEASED"
    assert calls == {"owner_action": 1, "bundle_action": 1, "mpc": 1, "bank": 1}


def test_local_owner_cleanup_does_not_claim_release_when_mpc_destroy_fails():
    from src.solvers.task40_v10_p6_yorbit import (
        destroy_task40_v10_p6_local_sector_owner,
    )

    calls = {"action": 0, "bundle": 0, "mpc": 0, "bank": 0}

    def destroy_action(name):
        def destroy():
            calls[name] += 1

        return destroy

    class MpcFailure(Exception):
        pass

    class FailingMpc:
        def destroy(self):
            calls["mpc"] += 1
            raise MpcFailure("fixture MPC destroy failed")

    class Bank:
        _closed = False

        def close(self):
            calls["bank"] += 1
            self._closed = True

    levels = {"floquets": {6: SimpleNamespace(mpc=FailingMpc())}}
    owner = {
        "system": None,
        "action": SimpleNamespace(destroy=destroy_action("action")),
        "bundle": {"action": SimpleNamespace(destroy=destroy_action("bundle"))},
        "levels": levels,
        "transform_bank": Bank(),
        "owner_receipt": {"owner_identity": "twist0:local_action_recovery_entities"},
    }

    with pytest.raises(RuntimeError, match="local p6 sector owner cleanup failed"):
        destroy_task40_v10_p6_local_sector_owner(owner, close_transform_bank=True)

    receipt = owner["local_owner_cleanup_receipt"]
    assert receipt["status"] == "CLEANUP_FAILED"
    assert receipt["local_levels_released"] is False
    assert "MpcFailure" in receipt["failures"][0]["message"]
    assert owner["levels"] is levels
    assert levels["floquets"][6].mpc is not None
    assert owner["local_owner_cleanup_complete"] is False
    assert calls == {"action": 1, "bundle": 1, "mpc": 1, "bank": 1}


def test_level_cleanup_releases_current_dolfinx_mpc_by_reference():
    import gc
    import weakref

    import pytest

    dolfinx_mpc = pytest.importorskip("dolfinx_mpc")
    from src.solvers.task40_v10_p6_yorbit import _destroy_task40_v10_levels

    assert not callable(getattr(dolfinx_mpc.MultiPointConstraint, "destroy", None))

    class CurrentAbiMpc:
        pass

    mpc = CurrentAbiMpc()
    mpc_reference = weakref.ref(mpc)
    floquet = SimpleNamespace(mpc=mpc)
    levels = {"floquets": {6: floquet}}

    _destroy_task40_v10_levels(levels, strict=True)
    assert floquet.mpc is None
    del mpc
    gc.collect()
    assert mpc_reference() is None

    _destroy_task40_v10_levels(levels, strict=True)


def test_v31_cleanup_failure_invalidates_worker_and_checker_result():
    from src.runners.task40_v10_worker import (
        _task40_v31_apply_local_owner_cleanup_failure,
    )

    summary = {"status": "PASS", "official_result": True}
    worker_result = {"passed": True, "status": "complete", "errors": [], "summary": summary}
    cleanup_facts = {
        "schema": "task40extra.review_v31_twist0_owner_handoff_cleanup.v1",
        "status": "CLEANUP_FAILED",
        "error": {"type": "RuntimeError", "message": "MPC owner was not released"},
    }

    _task40_v31_apply_local_owner_cleanup_failure(
        summary,
        worker_result,
        cleanup_facts,
    )

    assert summary["status"] == "FAILED"
    assert summary["official_result"] is False
    assert summary["result_classification"] == "WORKER_CLEANUP_FAILED"
    assert worker_result["passed"] is False
    assert worker_result["status"] == "failed"
    assert worker_result["errors"] == ["MPC owner was not released"]
    assert worker_result["summary"] is summary


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

    incomplete_inputs = dict(inputs)
    incomplete_inputs.pop("case2_full")
    with pytest.raises(ValueError, match="omits one of its four complete actions"):
        qualify_selected_q_native(
            matrix=matrix,
            inputs=incomplete_inputs,
            csr_outputs=outputs,
            native_outputs=outputs,
            native_components_case1={},
            paired_leakage={},
            trace_rows=2,
        )

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


def test_sector_preparation_refuses_a_missing_peer_before_building_any_q(tmp_path) -> None:
    from types import SimpleNamespace

    from src.solvers.task40_v30_selected_q_csr import prepare_selected_q_csr_sector

    q_map = sparse.eye(2, dtype=np.complex128, format="csr")
    q_map.indices = q_map.indices.astype(np.int32)
    q_map.indptr = q_map.indptr.astype(np.int32)
    with pytest.raises(ValueError, match="pair every missing q"):
        prepare_selected_q_csr_sector(
            sources_by_q={4: object()},
            q_maps_by_q={0: q_map, 4: q_map},
            sector_q_indices=(0, 4),
            twist_index=0,
            trace_rows_by_q={0: 1, 4: 1},
            selected_q_indices=(4,),
            action=SimpleNamespace(),
            volume_action=SimpleNamespace(),
            comm=SimpleNamespace(),
            available_sector_matrices={},
            allocation_gate=lambda *_args: None,
            profile="fixture",
            profile_identity={},
            ordered_modes=(),
            original_h=np.ones(1, dtype=np.complex128),
            scientific_input_sha256="1" * 64,
            operator_identity_by_q={4: {}},
            matrix_source_identity_by_q={4: {}},
            execution_identity={"source_sha": "a" * 40, "window_sha256": "b" * 64},
            producer_identity_by_q={4: {}},
            output_directory=tmp_path / "selected-q",
        )
    assert not (tmp_path / "selected-q").exists()


def test_native_failure_keeps_numeric_pending_and_atomic_stage_evidence(tmp_path, monkeypatch):
    from src.solvers import task40_v30_selected_q_csr as selected_q

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
    q0_map = sparse.csr_matrix(
        np.asarray(
            [[1, 0], [0, 1], [0, 0], [0, 0]], dtype=np.complex128
        )
    )
    mode = SimpleNamespace(side="top", m=0, n=0, polarization="s")
    profile_identity = {"name": "selected-q-failure-fixture", "trace_rows": 2}
    input_sha = "7" * 64
    original_h = np.asarray([2.0, 3.0], dtype=np.complex128)
    operator_identity = selected_q_operator_identity(
        scientific_input_sha256=input_sha,
        profile_identity=profile_identity,
        ordered_modes=(mode,),
        q_map=q4_map,
        original_h=original_h,
    )
    output = tmp_path / "selected-q"

    def fail_after_first_stage(**kwargs):
        kwargs["native_stage_callback"](
            "inputs_ready",
            {"case2_full_input": np.asarray([1 + 2j, 2 + 3j, 3 + 4j], dtype=np.complex128)},
            {"test_native_failure": True},
        )
        raise RuntimeError("injected q4 native failure")

    monkeypatch.setattr(selected_q, "run_selected_q_native_actions", fail_after_first_stage)
    with pytest.raises(RuntimeError, match="injected q4 native failure"):
        selected_q.prepare_selected_q_csr_sector(
            sources_by_q={4: _ToySavedContributions(base)},
            q_maps_by_q={0: q0_map, 4: q4_map},
            sector_q_indices=(0, 4),
            twist_index=0,
            trace_rows_by_q={0: 1, 4: 2},
            selected_q_indices=(4,),
            action=SimpleNamespace(condensed=SimpleNamespace(comm=object())),
            volume_action=object(),
            comm=object(),
            available_sector_matrices={
                0: sparse.eye(2, dtype=np.complex128, format="csr")
            },
            allocation_gate=lambda *_args: None,
            profile="selected-q-failure-fixture",
            profile_identity=profile_identity,
            ordered_modes=(mode,),
            original_h=original_h,
            scientific_input_sha256=input_sha,
            operator_identity_by_q={4: operator_identity},
            matrix_source_identity_by_q={
                4: {"source_sha": "a" * 40, "window_sha256": "b" * 64}
            },
            execution_identity={"source_sha": "c" * 40, "window_sha256": "d" * 64},
            producer_identity_by_q={4: {"kind": "fixture"}},
            output_directory=output,
        )

    q_directory = output / "q4_twist0"
    pending_path = q_directory / "task40_v30_q4_twist0_numeric_pending.json"
    stage_path = q_directory / "task40_v30_q4_twist0_native_inputs_ready.json"
    failure_path = q_directory / "task40_v30_q4_twist0_native_failure.json"
    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    stage = json.loads(stage_path.read_text(encoding="utf-8"))
    failure = json.loads(failure_path.read_text(encoding="utf-8"))
    assert pending["status"] == "NUMERIC_COMPLETE_NATIVE_PENDING"
    assert stage["status"] == "STAGE_COMPLETE"
    assert stage["metadata"]["test_native_failure"] is True
    assert failure["status"] == "NATIVE_FAILED_AFTER_NUMERIC_COMPLETE"
    assert failure["error_message"] == "injected q4 native failure"
    assert failure["numeric_pending_record"]["record_sha256"]
    assert not (q_directory / "task40_v30_q4_twist0_csr_manifest.json").exists()


def test_final_all_q_selector_cannot_publish_an_incomplete_inventory(tmp_path) -> None:
    from src.solvers.task40_v30_selected_q_csr import publish_v30_q_selector

    path = tmp_path / "all-q-selector.json"
    entry = {
        "q_index": 0,
        "manifest_status": "COMPLETE_CSR",
        "qualification_status": "PASS",
        "manifest_sha256": "a" * 64,
        "native_qualification_sha256": "b" * 64,
    }
    with pytest.raises(ValueError, match="every q"):
        publish_v30_q_selector(
            path,
            profile="fixture",
            entries=(entry,),
            q_count=8,
        )
    assert not path.exists()
