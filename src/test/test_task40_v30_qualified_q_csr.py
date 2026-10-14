from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
from scipy import sparse

from src.solvers.task40_v30_qualified_q_csr import (
    QualifiedQCSRProvider,
    V30_Q0_LEGACY_IMPORT_SCHEMA,
    V30_Q_CSR_MANIFEST_SCHEMA,
    V30_Q_CSR_NATIVE_SCHEMA,
    V30_Q_CSR_SELECTOR_SCHEMA,
    _array_sha256,
    _csr_sha256,
    make_v31_q_csr_import_authorization,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path, value: dict) -> Path:
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def _runtime_identity(matrix: sparse.csr_matrix, original_h: np.ndarray) -> dict[str, str]:
    return {
        "scientific_input_sha256": "1" * 64,
        "profile_identity_sha256": "2" * 64,
        "ordered_mode_sha256": "3" * 64,
        "q_map_sha256": _csr_sha256(matrix),
        "original_h_sha256": _array_sha256(original_h, np.dtype(np.complex128), "fixture H"),
    }


def _provider(
    root: Path,
    selector_path: Path,
    gates: list | None = None,
    **kwargs,
) -> QualifiedQCSRProvider:
    return QualifiedQCSRProvider(
        selector_path,
        selector_sha256=_sha(selector_path),
        repo_root=root,
        path_resolver=lambda path: Path(path).resolve(),
        allocation_gate=lambda name, facts: gates.append((name, dict(facts))) if gates is not None else None,
        **kwargs,
    )


def _v30_fixture(root: Path):
    matrix = sparse.csr_matrix(
        np.asarray(
            [
                [4.0 + 0.2j, 1.0 - 0.1j, 0.0],
                [0.5 + 0.3j, 3.5 + 0.4j, 0.2 - 0.1j],
                [0.0, 0.7 + 0.2j, 2.5 - 0.3j],
            ],
            dtype=np.complex128,
        )
    )
    original_h = np.asarray([1.0 + 0j, 2.0 - 0.25j, 3.0 + 0.5j], dtype=np.complex128)
    identity = _runtime_identity(matrix, original_h)
    source = {"source_sha": "a" * 40, "window_sha256": "b" * 64}
    execution = {"source_sha": "c" * 40, "window_sha256": "d" * 64}
    csr_dir = root / "q5_csr"
    csr_dir.mkdir(parents=True)
    artifacts = {}
    for name, array in (
        ("data", matrix.data),
        ("indices", matrix.indices.astype(np.int32, copy=False)),
        ("indptr", matrix.indptr.astype(np.int32, copy=False)),
    ):
        path = csr_dir / f"q5_{name}.npy"
        np.save(path, array, allow_pickle=False)
        artifacts[name] = {"path": path.name, "bytes": path.stat().st_size, "sha256": _sha(path)}
    manifest = {
        "schema": V30_Q_CSR_MANIFEST_SCHEMA,
        "status": "COMPLETE_CSR",
        "profile": "task40extra_v20_target_original_ny8",
        "q_index": 5,
        "twist_index": 1,
        "shape": [3, 3],
        "stored_structural_slots": int(matrix.nnz),
        "csr_index_dtype": np.dtype(np.int32).str,
        "csr_data_dtype": np.dtype(np.complex128).str,
        "operator_identity": identity,
        "matrix_source_identity": source,
        "csr_artifacts": artifacts,
    }
    manifest_path = _json(csr_dir / "q5_manifest.json", manifest)
    qualification_path = _json(
        root / "q5_native.json",
        {
            "schema": V30_Q_CSR_NATIVE_SCHEMA,
            "status": "PASS",
            "q_index": 5,
            "twist_index": 1,
            "csr_manifest_sha256": _sha(manifest_path),
            "operator_identity": identity,
            "matrix_source_identity": source,
            "execution_identity": execution,
            "four_complete_csr_actions_passed": True,
            "paired_sector_leakage_passed": True,
            "maximum_relative_error": 8e-15,
        },
    )
    selector = {
        "schema": V30_Q_CSR_SELECTOR_SCHEMA,
        "profile": "task40extra_v20_target_original_ny8",
        "q_csr_entries": [
            {
                "q_index": 5,
                "twist_index": 1,
                "shape": [3, 3],
                "operator_identity": identity,
                "matrix_source_identity": source,
                "execution_identity": execution,
                "csr_manifest": {"path": str(manifest_path), "sha256": _sha(manifest_path)},
                "native_qualification": {
                    "path": str(qualification_path),
                    "sha256": _sha(qualification_path),
                },
            }
        ],
    }
    selector_path = _json(root / "selector.json", selector)
    return matrix, original_h, identity, execution, selector_path


def test_v30_provider_checks_actual_q_map_h_and_40_digit_source_hash(tmp_path):
    expected, original_h, identity, execution, selector_path = _v30_fixture(tmp_path)
    gates: list = []
    provider = _provider(tmp_path, selector_path, gates)
    actual, receipt = provider.load(
        5,
        1,
        expected_operator_identity=identity,
        expected_execution_identity=execution,
        expected_q_map=expected,
        expected_original_h=original_h,
    )
    vector = np.asarray([1.0 + 0.3j, -0.2 + 0.7j, 0.5 - 0.1j])
    assert np.array_equal(actual @ vector, expected @ vector)
    assert actual.has_canonical_format and actual.has_sorted_indices
    assert not actual.data.flags.writeable
    assert receipt["qualification_kind"] == "V30_NATIVE_PASS"
    assert receipt["maximum_relative_error"] == 8e-15
    assert gates[0][0] == "task40_v30_q5_runtime_identity"
    assert gates[-1][1]["mmap_file_pages_counted_as_memory"] is True

    changed_h = original_h.copy()
    changed_h[0] += 1
    with pytest.raises(ValueError, match="actual runtime input/operator data"):
        provider.load(
            5,
            1,
            expected_operator_identity=identity,
            expected_execution_identity=execution,
            expected_q_map=expected,
            expected_original_h=changed_h,
        )
    changed_execution = dict(execution, window_sha256="e" * 64)
    with pytest.raises(ValueError, match="cross-window COMPLETE q import"):
        provider.load(
            5,
            1,
            expected_operator_identity=identity,
            expected_execution_identity=changed_execution,
            expected_q_map=expected,
            expected_original_h=original_h,
        )


def test_v30_sector_loader_reuses_owner_bound_map_and_provider_rejects_wrong_map(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace

    from src.solvers import task40_v10_p6_yorbit as yorbit

    expected, original_h, identity, execution, selector_path = _v30_fixture(tmp_path)
    provider = _provider(tmp_path, selector_path)
    monkeypatch.setattr(
        yorbit,
        "_task40_v30_profile_identity_sha256",
        lambda _profile: identity["profile_identity_sha256"],
    )
    monkeypatch.setattr(
        yorbit,
        "_task40_v30_ordered_mode_key_sha256",
        lambda _modes: identity["ordered_mode_sha256"],
    )

    class Coordinates:
        calls = 0

        def q_map(self, branch, *, allocation_gate):
            self.calls += 1
            raise AssertionError(f"unexpected fresh q_map construction for branch {branch}")

    class Profile:
        name = "task40extra_v20_target_original_ny8"

        def identity(self):
            return {"name": self.name}

    mode = SimpleNamespace(side="top", m=0, n=0, polarization="s")
    mode_sha = "4" * 64
    action = SimpleNamespace(
        condensed=SimpleNamespace(
            full_rows=3,
            trace_constraints=SimpleNamespace(original_to_active={0: 0}),
        )
    )
    context = SimpleNamespace(twist_index=1, global_q_indices=(1, 5))
    runtime_identity = {
        "scientific_input_sha256": identity["scientific_input_sha256"],
        "ordered_mode_key_sha256": identity["ordered_mode_sha256"],
        "execution_identity": execution,
        "legacy_q0_identity": {"mode_manifest_sha256": mode_sha},
    }
    q_maps_by_q = {1: sparse.csr_matrix((3, 3), dtype=np.complex128), 5: expected}
    coordinates = Coordinates()

    matrices, audit = yorbit._task40_v30_load_sector_q_csr_pair(
        provider,
        action=action,
        coordinates=coordinates,
        context=context,
        local_h=original_h,
        profile=Profile(),
        global_bundle={"mode_sha256": mode_sha, "modes": (mode,)},
        mode_inventory=((mode,), ({"mode_index": 0},), mode_sha),
        runtime_identity=runtime_identity,
        allocation_gate=lambda *_args: None,
        selected_q_indices={5},
        prebuilt_q_maps_by_q=q_maps_by_q,
    )

    assert coordinates.calls == 0
    assert set(matrices) == {5}
    assert matrices[5].shape == expected.shape
    assert audit["qualification_receipts"][0]["qualification_status"] == "PASS"

    wrong_q_map = expected.copy()
    wrong_q_map.data[0] += 1.0
    with pytest.raises(ValueError, match="actual runtime input/operator data"):
        yorbit._task40_v30_load_sector_q_csr_pair(
            provider,
            action=action,
            coordinates=coordinates,
            context=context,
            local_h=original_h,
            profile=Profile(),
            global_bundle={"mode_sha256": mode_sha, "modes": (mode,)},
            mode_inventory=((mode,), ({"mode_index": 0},), mode_sha),
            runtime_identity=runtime_identity,
            allocation_gate=lambda *_args: None,
            selected_q_indices={5},
            prebuilt_q_maps_by_q={1: q_maps_by_q[1], 5: wrong_q_map},
        )


def test_v31_cross_window_complete_import_requires_exact_authorization_and_writes_consumer_receipt(
    tmp_path,
):
    expected, original_h, identity, producer_execution, selector_path = _v30_fixture(tmp_path)
    selector = json.loads(selector_path.read_text(encoding="utf-8"))
    entry = selector["q_csr_entries"][0]
    manifest_path = Path(entry["csr_manifest"]["path"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    native_path = Path(entry["native_qualification"]["path"])
    native = json.loads(native_path.read_text(encoding="utf-8"))
    consumer_execution = {"source_sha": "e" * 40, "window_sha256": "f" * 64}
    artifacts = {
        name: {
            "path": str((manifest_path.parent / row["path"]).resolve()),
            "bytes": row["bytes"],
            "sha256": row["sha256"],
        }
        for name, row in manifest["csr_artifacts"].items()
    }
    authorization = make_v31_q_csr_import_authorization(
        q_index=5,
        twist_index=1,
        profile=selector["profile"],
        operator_identity=identity,
        matrix_source_identity=entry["matrix_source_identity"],
        producer_identity=manifest.get("producer_identity", {}),
        producer_execution_identity=producer_execution,
        native_execution_identity=native["execution_identity"],
        csr_manifest_sha256=entry["csr_manifest"]["sha256"],
        native_qualification_sha256=entry["native_qualification"]["sha256"],
        csr_artifacts=artifacts,
        consumer_execution_identity=consumer_execution,
    )
    saved_manifest = manifest_path.read_bytes()
    saved_native = native_path.read_bytes()
    receipt_root = tmp_path / "consumer_receipts"
    kwargs = {
        "consumer_receipt_directory": receipt_root,
    }
    provider = _provider(tmp_path, selector_path, **kwargs)
    with pytest.raises(ValueError, match="approved V31 contract authorization"):
        provider.load(
            5,
            1,
            expected_operator_identity=identity,
            expected_execution_identity=consumer_execution,
            expected_q_map=expected,
            expected_original_h=original_h,
        )
    assert not list(receipt_root.glob("*.json")) if receipt_root.exists() else True

    provider = _provider(
        tmp_path,
        selector_path,
        consumer_import_authorizations={"5": authorization},
        **kwargs,
    )
    actual, receipt = provider.load(
        5,
        1,
        expected_operator_identity=identity,
        expected_execution_identity=consumer_execution,
        expected_q_map=expected,
        expected_original_h=original_h,
    )
    assert np.array_equal(actual.toarray(), expected.toarray())
    consumer = receipt["consumer_receipt"]
    saved = json.loads(Path(consumer["path"]).read_text(encoding="utf-8"))
    assert consumer["sha256"] == _sha(Path(consumer["path"]))
    assert saved["producer_execution_identity"] == producer_execution
    assert saved["native_execution_identity"] == producer_execution
    assert saved["consumer_execution_identity"] == consumer_execution
    assert saved["authorization"] == authorization
    assert saved["original_manifest_and_native_pass_rewritten"] is False
    assert manifest_path.read_bytes() == saved_manifest
    assert native_path.read_bytes() == saved_native

    wrong_authorization = dict(authorization, csr_manifest_sha256="9" * 64)
    wrong_provider = _provider(
        tmp_path,
        selector_path,
        consumer_import_authorizations={"5": wrong_authorization},
        consumer_receipt_directory=tmp_path / "wrong_receipts",
    )
    with pytest.raises(ValueError, match="approved V31 contract authorization"):
        wrong_provider.load(
            5,
            1,
            expected_operator_identity=identity,
            expected_execution_identity=consumer_execution,
            expected_q_map=expected,
            expected_original_h=original_h,
        )
    assert not list((tmp_path / "wrong_receipts").glob("*.json"))


def _v28_readback(readback_record: dict) -> dict:
    components = {
        name: {"active_block": {"relative": 0.0}, "native_off_block_relative": 0.0}
        for name in ("volume", "minus_D", "C", "Hhat")
    }
    return {
        "q0_case_1_full_csr_vs_native_total": {"relative": 1e-14},
        "q0_case_2_full_csr_vs_native_total": {"relative": 2e-14},
        "q0_case_1_csr_trace_port_masked_components_vs_native": components,
        "q0_case_1_trace_plus_port_vs_full_csr": {"relative": 0.0},
        "relative_error_limit": 1e-11,
        "all_gates_passed": True,
        "full_csr_multiply_count": 4,
        "csr_readback_artifact": readback_record,
    }


def _legacy_fixture(root: Path):
    results = root / "results/task40extra_nonseparable_0p7nm"
    csr_dir = results / "attempt-csr"
    native_dir = results / "attempt-native"
    producer_dir = results / "attempt-producer"
    for path in (csr_dir, native_dir, producer_dir):
        path.mkdir(parents=True)

    donor_map = sparse.csr_matrix(
        np.asarray(
            [
                [1.0 + 0.25j, 0.0, 0.5 - 0.1j],
                [0.0, 2.0 + 0.5j, 0.0],
                [0.3 - 0.2j, 0.0, 3.0 + 0.75j],
            ],
            dtype=np.complex128,
        )
    )
    donor_h = np.asarray([1.25 + 0j, 2.5 + 0j], dtype=np.complex128)
    active_lookup = np.asarray([0, 1, -1, 2], dtype=np.int32)
    map_path = producer_dir / "v25_selected_q0_map.npz"
    sparse.save_npz(map_path, donor_map, compressed=False)
    h_path = producer_dir / "v25_selected_q0_local_H_p.npy"
    lookup_path = producer_dir / "v25_selected_q0_original_to_active_int32.npy"
    np.save(h_path, donor_h, allow_pickle=False)
    np.save(lookup_path, active_lookup, allow_pickle=False)

    csr_artifacts = {}
    for name, array in (
        ("data", donor_map.data),
        ("indices", donor_map.indices.astype(np.int32, copy=False)),
        ("indptr", donor_map.indptr.astype(np.int32, copy=False)),
    ):
        path = csr_dir / f"q0_{name}.npy"
        np.save(path, array, allow_pickle=False)
        csr_artifacts[name] = {
            "path": str(path),
            "bytes": path.stat().st_size,
            "sha256": _sha(path),
        }
    pattern_path = _json(csr_dir / "v27_pattern.json", {"pattern": "frozen donor"})
    manifest_path = csr_dir / "task40_v28_q0_csr_continuation_manifest.json"
    readback_path = native_dir / "v28_q0_csr_readback.npz"
    readback_path.write_bytes(b"small immutable native readback")
    readback_record = {
        "path": readback_path.name,
        "bytes": readback_path.stat().st_size,
        "sha256": _sha(readback_path),
    }
    old_source = "c" * 40
    old_window = "d" * 64
    current_window = "e" * 64
    mode_manifest_sha = "f" * 64
    donor_identity_sha = "9" * 64
    donor_input_sha = "0" * 64
    runtime_identity = _runtime_identity(donor_map, donor_h)
    legacy_identity = {
        "input_sha256": donor_input_sha,
        "physical_model_sha256": "8" * 64,
        "run_id": "task40extra_0p7nm_target_original_ny8_operator_probe_v22",
        "campaign_window_sha256": old_window,
        "mode_manifest_sha256": mode_manifest_sha,
        "ordered_mode_key_sha256": runtime_identity["ordered_mode_sha256"],
        "donor_identity_sha256": donor_identity_sha,
    }
    payloads = []
    for path in (map_path, h_path, lookup_path):
        payloads.append(
            {"path": path.name, "bytes": path.stat().st_size, "sha256": _sha(path)}
        )
    donor = {
        "producer_identity": {
            "producer_run_directory": str(producer_dir.relative_to(root)),
            "payloads": payloads,
        }
    }
    source_identity = {"donor_identity": donor}
    native_qualification_path = native_dir / "v28_q0_native_qualification.json"
    native_qualification = {
        "schema": "task40extra.review_v28_q0_native_qualification.v1",
        "status": "PASS_COMPLETE_Q0_CSR_NATIVE_READBACK",
        "source_identity": {
            "source_sha": old_source,
            "input_sha256": donor_input_sha,
            "physical_model_sha256": legacy_identity["physical_model_sha256"],
            "run_id": legacy_identity["run_id"],
            "campaign_window_sha256": old_window,
            "mode_manifest_sha256": mode_manifest_sha,
            "ordered_mode_key_sha256": runtime_identity["ordered_mode_sha256"],
        },
        "donor_identity_sha256": donor_identity_sha,
        "campaign_window_sha256": old_window,
        "original_pattern_manifest": {
            "path": str(pattern_path),
            "sha256": _sha(pattern_path),
        },
        "csr_manifest_path": str(manifest_path),
        "csr_artifact_hashes": {
            name: record["sha256"] for name, record in csr_artifacts.items()
        },
        "csr_shape": [3, 3],
        "stored_structural_slots": int(donor_map.nnz),
        "readback_artifact": readback_record,
        "readback": _v28_readback(readback_record),
    }
    _json(native_qualification_path, native_qualification)
    native_record = {
        "path": str(native_qualification_path),
        "sha256": _sha(native_qualification_path),
        "status": native_qualification["status"],
    }
    old_matrix_source = {"source_sha": old_source, "window_sha256": old_window}
    manifest = {
        "schema": "task40extra.review_v28_saved_q0_csr.v1",
        "status": "COMPLETE_CSR",
        "shape": [3, 3],
        "stored_structural_slots": int(donor_map.nnz),
        "csr_index_dtype": np.dtype(np.int32).str,
        "csr_data_dtype": np.dtype(np.complex128).str,
        "q_map_count": 1,
        "q_map_branch": 0,
        "saved_only_no_fe_or_native_rebuild": True,
        "source_identity": source_identity,
        "numeric_fill_identity": {
            "execution_identity": {
                "source_sha": old_source,
                "campaign_window_sha256": old_window,
            },
            "donor_identity": donor,
        },
        "csr_artifacts": csr_artifacts,
        "native_qualification": native_record,
    }
    _json(manifest_path, manifest)
    native_qualification["csr_manifest_path"] = str(manifest_path)
    _json(native_qualification_path, native_qualification)
    native_record["sha256"] = _sha(native_qualification_path)
    manifest["native_qualification"] = native_record
    _json(manifest_path, manifest)

    execution = {"source_sha": "a" * 40, "window_sha256": current_window}
    pattern_record = {"path": str(pattern_path), "sha256": _sha(pattern_path)}
    qualification_record = dict(manifest["native_qualification"])
    entry = {
        "q_index": 0,
        "twist_index": 0,
        "shape": [3, 3],
        "operator_identity": runtime_identity,
        "matrix_source_identity": old_matrix_source,
        "execution_identity": execution,
        "csr_manifest": {"path": str(manifest_path), "sha256": _sha(manifest_path)},
        "native_qualification": qualification_record,
        "legacy_q0_import": {
            "schema": V30_Q0_LEGACY_IMPORT_SCHEMA,
            "v28_identity": legacy_identity,
            "original_pattern_manifest": pattern_record,
        },
    }
    selector_path = _json(
        root / "q0_selector.json",
        {
            "schema": V30_Q_CSR_SELECTOR_SCHEMA,
            "profile": "task40extra_v20_target_original_ny8",
            "q_csr_entries": [entry],
        },
    )
    legacy_expected = {
        "input_sha256": donor_input_sha,
        "physical_model_sha256": legacy_identity["physical_model_sha256"],
        "mode_manifest_sha256": mode_manifest_sha,
        "manifest_sha256": _sha(manifest_path),
        "native_qualification_sha256": _sha(native_qualification_path),
    }
    return donor_map, donor_h, active_lookup, runtime_identity, execution, legacy_expected, selector_path


def test_q0_import_reuses_original_v28_verifier_and_keeps_old_window_separate(tmp_path):
    donor_map, donor_h, active_lookup, identity, execution, legacy, selector_path = _legacy_fixture(tmp_path)
    gates: list = []
    provider = _provider(tmp_path, selector_path, gates)
    assert identity["scientific_input_sha256"] != legacy["input_sha256"]
    actual, receipt = provider.load(
        0,
        0,
        expected_operator_identity=identity,
        expected_execution_identity=execution,
        expected_q_map=donor_map,
        expected_original_h=donor_h,
        expected_legacy_q0_identity=legacy,
        expected_q0_active_lookup=active_lookup,
    )
    vector = np.asarray([1 + 0.2j, -0.3 + 0.8j, 0.5 - 0.7j])
    assert np.array_equal(actual @ vector, donor_map @ vector)
    assert receipt["qualification_kind"] == "LEGACY_QUALIFICATION_IMPORTED_OPERATOR_BINDINGS_DERIVED"
    assert receipt["qualification_status"] == "PASS_COMPLETE_Q0_CSR_NATIVE_READBACK"
    assert receipt["matrix_source_identity"]["window_sha256"] == "d" * 64
    assert receipt["execution_identity"]["window_sha256"] == "e" * 64
    assert receipt["matrix_source_window_differs_from_execution_window"] is True
    assert receipt["maximum_relative_error"] is None
    assert gates[-1][0] == "task40_v30_q0_csr_open"
    assert any(name == "task40_v30_legacy_q0_map_h_identity" for name, _ in gates)


def test_selector_coverage_is_strict_by_default_and_explicit_for_sector_preparation(tmp_path):
    *_donor, selector_path = _legacy_fixture(tmp_path)
    provider = _provider(tmp_path, selector_path)

    with pytest.raises(ValueError, match="all-q phase requires"):
        provider.require_coverage(set(range(8)), phase="all_q")

    preparation = provider.require_coverage(
        set(range(8)), phase="sector_preparation_subset"
    )
    assert preparation == {
        "phase": "sector_preparation_subset",
        "required_q_indices": list(range(8)),
        "available_q_indices": [0],
        "complete_coverage": False,
    }
    with pytest.raises(ValueError, match="explicit phase"):
        provider.require_coverage(set(range(8)), phase="implicit_partial")


def test_q0_map_import_requires_identity_proof_if_row_or_column_numbering_changes():
    donor = sparse.csr_matrix(np.asarray([[1, 2], [3, 4]], dtype=np.complex128))
    current = donor[[1, 0], :][:, [1, 0]].tocsr()
    current.indices = current.indices.astype(np.int32)
    current.indptr = current.indptr.astype(np.int32)
    current.sort_indices()
    with pytest.raises(ValueError, match="different q0 FE numbering"):
        QualifiedQCSRProvider._compare_q0_map(donor, current, None)
    mapping = {
        "row_keys_current": np.asarray([20, 10], dtype=np.int64),
        "row_keys_donor": np.asarray([10, 20], dtype=np.int64),
        "rows_current_to_donor": np.asarray([1, 0], dtype=np.int64),
        "column_keys_current": np.asarray([200, 100], dtype=np.int64),
        "column_keys_donor": np.asarray([100, 200], dtype=np.int64),
        "columns_current_to_donor": np.asarray([1, 0], dtype=np.int64),
    }
    assert QualifiedQCSRProvider._compare_q0_map(donor, current, mapping) == _csr_sha256(donor)


def test_provider_rejects_missing_q_without_assembly_fallback(tmp_path):
    _matrix, original_h, identity, execution, selector_path = _v30_fixture(tmp_path)
    provider = _provider(tmp_path, selector_path)
    with pytest.raises(ValueError, match="no qualified q"):
        provider.load(
            4,
            0,
            expected_operator_identity=identity,
            expected_execution_identity=execution,
            expected_q_map=_matrix,
            expected_original_h=original_h,
        )

