from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def test_v29_source_absolute_input_maps_through_real_v27_donor_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts import task40_v20_service_workflow as service

    execution_root = tmp_path / "execution-root"
    source_root = tmp_path / "source-root"
    execution_root.mkdir()
    source_root.mkdir()
    producer_relative = Path("fixture-producer")
    producer_root = execution_root / producer_relative
    producer_root.mkdir()
    stage_relative = (
        service.V25_ARTIFACT_ROOT
        / "stage_inputs/selected_reference_q_build_only"
        / "target_original_ny8_operator_probe_v22.dat"
    )
    execution_dat = execution_root / stage_relative
    execution_dat.parent.mkdir(parents=True, exist_ok=True)
    execution_dat.write_bytes(b"small V28-bound stage DAT fixture\n")
    source_dat = source_root / stage_relative

    input_sha = _sha(execution_dat)
    physical_sha = "c" * 64
    source_sha = "b" * 40
    run_id = "synthetic-v26-producer"
    malformed_legacy_sha = "a" * 62
    payload_path = producer_root / "payload.bin"
    payload_path.write_bytes(b"payload")
    payload_sha = _sha(payload_path)

    resolved_path = producer_root / "resolved_config.json"
    _write_json(
        resolved_path,
        {
            "provenance": {
                "input_sha256": input_sha,
                "physical_model_sha256": physical_sha,
            }
        },
    )
    resolved_sha = _sha(resolved_path)
    (producer_root / "input_original.dat").write_bytes(execution_dat.read_bytes())
    (producer_root / "input_sha256.txt").write_text(input_sha, encoding="ascii")
    (producer_root / "physical_model_sha256.txt").write_text(physical_sha, encoding="ascii")
    (producer_root / "source_sha.txt").write_text(source_sha, encoding="ascii")
    _write_json(
        producer_root / "run_manifest.json",
        {
            "input_path": str(source_dat),
            "input_sha256": input_sha,
            "physical_model_sha256": physical_sha,
            "resolved_config_sha256": resolved_sha,
            "run_id": run_id,
            "source_sha": source_sha,
        },
    )
    _write_json(producer_root / "run_summary.json", {"status": "fixture"})
    support_names = (
        "input_sha256.txt",
        "physical_model_sha256.txt",
        "source_sha.txt",
        "run_manifest.json",
        "run_summary.json",
    )
    support = [
        {
            "path": name,
            "bytes": (producer_root / name).stat().st_size,
            "sha256": _sha(producer_root / name),
        }
        for name in support_names
    ]
    failure_index = producer_root / "v25_q0_failure_artifact_index.json"
    _write_json(
        failure_index,
        {
            "run": {
                "input_sha256": malformed_legacy_sha,
                "physical_model_sha256": physical_sha,
                "relative_run_directory": str(producer_relative),
                "resolved_config_sha256": resolved_sha,
                "run_id": run_id,
                "source_sha": source_sha,
            },
            "supporting_records": support,
            "data_artifacts": [
                {"path": "payload.bin", "bytes": 7, "sha256": payload_sha}
            ],
        },
    )

    monkeypatch.setattr(service, "V26_PRODUCER_RUN_RELATIVE", producer_relative)
    monkeypatch.setattr(service, "V26_FAILURE_INDEX_SHA256", _sha(failure_index))
    monkeypatch.setattr(service, "V26_PRODUCER_SOURCE_SHA", source_sha)
    monkeypatch.setattr(service, "V26_PRODUCER_RUN_ID", run_id)
    monkeypatch.setattr(service, "V26_LEGACY_BAD_INPUT_SHA256", malformed_legacy_sha)
    monkeypatch.setattr(service, "V26_VERIFIED_INPUT_SHA256", input_sha)
    monkeypatch.setattr(service, "V26_PRODUCER_FILE_HASHES", {"payload.bin": (7, payload_sha)})

    def resolve_source_to_execution(value: str | Path) -> Path:
        candidate = Path(value).resolve()
        return (execution_root / candidate.relative_to(source_root.resolve())).resolve()

    old_manifest_bytes = (producer_root / "run_manifest.json").read_bytes()

    replay_root = execution_root / "fixture-replay"
    replay_root.mkdir()
    monkeypatch.setattr(service, "V27_REPLAY_ROOT", Path("fixture-replay"))
    monkeypatch.setattr(service, "V27_REPLAY_MANIFEST_SHA256", "pending")
    producer_identity = service.verify_v26_saved_producer_metadata(
        producer_root=producer_root,
        repo_root=execution_root,
        path_resolver=resolve_source_to_execution,
    )
    producer_identity_sha = hashlib.sha256(
        json.dumps(
            producer_identity, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    replay_manifest = replay_root / "v26_saved_q_replay_manifest.json"
    _write_json(
        replay_manifest,
        {
            "schema": "task40extra.review_v26_saved_q_replay.v1",
            "status": "PASS_SAVED_STREAM_REPLAY_NO_NATIVE",
            "producer_identity": producer_identity,
            "producer_identity_sha256": producer_identity_sha,
            "official_result": False,
            "csr_built": False,
            "artifacts": {},
        },
    )
    replay_sha = _sha(replay_manifest)
    monkeypatch.setattr(service, "V27_REPLAY_MANIFEST_SHA256", replay_sha)

    native_relative = Path("fixture-native")
    native_root = execution_root / native_relative
    native_root.mkdir()
    monkeypatch.setattr(service, "V27_NATIVE_ROOT", native_relative)
    recovery_tag = "fixture-recovery"
    monkeypatch.setattr(service, "V27_NATIVE_RECOVERY_TAG", recovery_tag)
    cases = {}
    for case_name in ("q0_case_1", "q0_case_2", "q4_pair"):
        filename = f"{case_name}.bin"
        case_path = native_root / filename
        case_path.write_bytes(case_name.encode("ascii"))
        cases[case_name] = {
            "path": filename,
            "bytes": case_path.stat().st_size,
            "sha256": _sha(case_path),
            "array_sha256": {},
            "array_shapes": {},
        }
    checker_path = native_root / f"v26_native_action_recovery_check_{recovery_tag}.json"
    _write_json(
        checker_path,
        {
            "schema": "task40extra.review_v26_native_case_recovery_check.v1",
            "status": "PASS_READONLY_THREE_CASE_RECOVERY",
            "native_cases": cases,
        },
    )
    recovery_path = native_root / f"v26_native_action_recovery_{recovery_tag}.json"
    _write_json(
        recovery_path,
        {
            "schema": "task40extra.review_v26_native_action_recovery.v1",
            "status": "PASS_RECOVERED_THREE_NATIVE_CASES",
            "saved_replay_manifest_sha256": replay_sha,
            "recovery_checker_receipt_sha256": _sha(checker_path),
            "cases": cases,
        },
    )
    monkeypatch.setattr(service, "V27_NATIVE_RECOVERY_SHA256", _sha(recovery_path))
    monkeypatch.setattr(service, "V27_NATIVE_CHECKER_SHA256", _sha(checker_path))

    row_relative = Path("fixture-row.npz")
    row_path = execution_root / row_relative
    row_path.write_bytes(b"row structure")
    row_sha = _sha(row_path)
    row_manifest = row_path.with_suffix(".json")
    _write_json(
        row_manifest,
        {
            "schema": "task40extra.review_v26_selected_q0_row_structure_checkpoint.v1",
            "shape": [777_644, 777_644],
            "nnz": 577_061_168,
            "required_csr_payload_bytes": 11_544_333_940,
            "array_artifact": {"sha256": row_sha},
        },
    )
    monkeypatch.setattr(service, "V27_ROW_STRUCTURE_RELATIVE", row_relative)
    monkeypatch.setattr(service, "V27_ROW_STRUCTURE_SHA256", row_sha)
    monkeypatch.setattr(service, "V27_ROW_STRUCTURE_MANIFEST_SHA256", _sha(row_manifest))

    donor = service.verify_v27_v26_donor_import(
        repo_root=execution_root,
        path_resolver=resolve_source_to_execution,
    )

    assert donor["producer_identity"]["actual_v25_dat_sha256"] == input_sha
    assert donor["producer_identity"]["verified_input_sha256"] == input_sha
    assert donor["producer_identity"]["payloads"] == [
        {"path": "payload.bin", "bytes": 7, "sha256": payload_sha}
    ]
    assert (producer_root / "run_manifest.json").read_bytes() == old_manifest_bytes
    with pytest.raises(ValueError, match="actual executed V25 dat path/hash"):
        service.verify_v27_v26_donor_import(repo_root=execution_root)
    assert (producer_root / "run_manifest.json").read_bytes() == old_manifest_bytes
