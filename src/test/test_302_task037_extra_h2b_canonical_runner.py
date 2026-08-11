from __future__ import annotations

import inspect
import json
from pathlib import Path

import numpy as np

import benchmarks.run_task037_extra_h2b as runner


_PROGRESS_DIGEST = "d" * 64


def _marker(event, *, digest=_PROGRESS_DIGEST, representative_count=1):
    item = {"schema": runner.H2B_PROGRESS_SCHEMA, "phase": "c1", "event": event}
    if event == "neighborhood_discovery_ready":
        item.update({"neighborhood_count": runner.H2B_C1_NEIGHBORHOOD_COUNT, "neighborhood_digest": digest})
    elif event in {"candidate_orbit_ready", "transform_orbit_ready"}:
        item.update({"representative_count": representative_count, "neighborhood_digest": digest})
    elif event == "probe_ready":
        item["probe_seed"] = 20260812
    return item


def _progress(path, order):
    events = list(runner.H2B_C1_EVENTS[:8])
    items = [_marker(event) for event in events]
    items.extend(_marker(event) for event in runner.H2B_C1_EVENTS[8:12])
    for index, neighborhood_id in enumerate(order):
        items.append({
            "schema": runner.H2B_PROGRESS_SCHEMA,
            "phase": "c1",
            "event": "patch_audit_started",
            "neighborhood_id": neighborhood_id,
            "patch_order_index": index,
        })
        items.append({
            "schema": runner.H2B_PROGRESS_SCHEMA,
            "phase": "c1",
            "event": "patch_audit_ready",
            "neighborhood_id": neighborhood_id,
            "patch_order_index": index,
        })
    items.append({"schema": runner.H2B_PROGRESS_SCHEMA, "phase": "c1", "event": "summary_ready"})
    path.write_text("\n".join(json.dumps(item) for item in items) + "\n", encoding="utf-8")


def _partial_progress(path, order, count=1):
    items = [_marker(event) for event in runner.H2B_C1_EVENTS[:12]]
    for index, neighborhood_id in enumerate(order[:count]):
        items.extend(
            [
                {
                    "schema": runner.H2B_PROGRESS_SCHEMA,
                    "phase": "c1",
                    "event": "patch_audit_started",
                    "neighborhood_id": neighborhood_id,
                    "patch_order_index": index,
                },
                {
                    "schema": runner.H2B_PROGRESS_SCHEMA,
                    "phase": "c1",
                    "event": "patch_audit_ready",
                    "neighborhood_id": neighborhood_id,
                    "patch_order_index": index,
                },
            ]
        )
    items.append({"schema": runner.H2B_PROGRESS_SCHEMA, "phase": "c1", "event": "summary_ready"})
    path.write_text("\n".join(json.dumps(item) for item in items) + "\n", encoding="utf-8")


def _early_progress(path, suffix, *, digest=_PROGRESS_DIGEST, representative_count=1):
    items = [
        _marker(event, digest=digest, representative_count=representative_count)
        for event in runner.H2B_C1_EVENTS[:8]
    ]
    if suffix == "predicted":
        items.append(
            _marker(
                "transform_orbit_ready",
                digest=digest,
                representative_count=representative_count,
            )
        )
    items.append({"schema": runner.H2B_PROGRESS_SCHEMA, "phase": "c1", "event": "summary_ready"})
    path.write_text("\n".join(json.dumps(item) for item in items) + "\n", encoding="utf-8")


def test_c1_progress_has_84_neighborhoods_not_252(tmp_path):
    order = list(reversed(range(runner.H2B_C1_NEIGHBORHOOD_COUNT)))
    path = tmp_path / "c1_progress.jsonl"
    _progress(path, order)
    assert runner._c1_progress_state(path, None, order) == (True, 84)
    assert runner._c1_progress_state(path, None, list(range(84))) == (False, 0)
    assert runner.H2B_FIXED_CELLS == 252


def test_c1_partial_numeric_progress_requires_canonical_ready_index(tmp_path):
    order = list(reversed(range(runner.H2B_C1_NEIGHBORHOOD_COUNT)))
    actual_prefix = order[:1]
    path = tmp_path / "c1_partial_progress.jsonl"
    _partial_progress(path, actual_prefix)
    assert runner._c1_progress_state(
        path, "c1_patch_or_action_gate", actual_prefix
    ) == (True, 1)
    lines = path.read_text(encoding="utf-8").splitlines()
    ready = json.loads(lines[13])
    ready["patch_order_index"] = 1
    lines[13] = json.dumps(ready)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert runner._c1_progress_state(
        path, "c1_patch_or_action_gate", actual_prefix
    ) == (False, 0)


def test_c1_predicted_and_candidate_progress_sequences_bind_metadata(tmp_path):
    path = tmp_path / "c1_early_progress.jsonl"
    _early_progress(path, "predicted")
    assert runner._c1_progress_state(
        path,
        "predicted_live_set_gate",
        expected_neighborhood_digest=_PROGRESS_DIGEST,
        expected_candidate_count=1,
    ) == (True, 0)

    lines = path.read_text(encoding="utf-8").splitlines()
    transform = json.loads(lines[8])
    transform["neighborhood_digest"] = "e" * 64
    lines[8] = json.dumps(transform)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert runner._c1_progress_state(path, "predicted_live_set_gate") == (False, 0)

    _early_progress(path, "predicted")
    lines = path.read_text(encoding="utf-8").splitlines()
    transform = json.loads(lines[8])
    transform["representative_count"] = 2
    lines[8] = json.dumps(transform)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert runner._c1_progress_state(path, "predicted_live_set_gate") == (False, 0)

    _early_progress(path, "candidate")
    assert runner._c1_progress_state(
        path, "candidate_representative_limit"
    ) == (True, 0)
    lines = path.read_text(encoding="utf-8").splitlines()
    lines.insert(8, json.dumps(_marker("transform_orbit_ready")))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert runner._c1_progress_state(
        path, "MONOMIAL_TRANSFORM_NOT_PROVEN"
    ) == (False, 0)


def test_c1_candidate_artifact_inventory_has_no_patch_files(tmp_path):
    required = {
        "stage_progress.jsonl", "stage_stdout.txt", "stage_summary.json",
        "stage_timeline.jsonl", "stage_root_pid.json", "c1_progress.jsonl",
        "c1_stdout.txt", "c1_summary.json", "c1_timeline.jsonl", "c1_root_pid.json",
        "c1_candidate_stop.json", "c1_manifest.json", "neighborhood_ids.npy",
        "orbit_ids.npy", "representative_ids.npy", "metadata_sha256.npy",
        "provenance_sha256.npy", "row_token_sha256.npy", "row_provenance_sha256.npy",
    }
    for name in required:
        (tmp_path / name).write_bytes(b"{}")
    recorded = {name: runner._artifact(tmp_path, name) for name in runner.H2B_C1_ARTIFACT_NAMES}
    assert runner._c1_artifacts_match(
        tmp_path,
        recorded,
        controlled_reason="candidate_representative_limit",
        patch_count=0,
    )
    (tmp_path / "c1_manifest.json").unlink()
    assert not runner._c1_artifacts_match(
        tmp_path,
        {name: runner._artifact(tmp_path, name) for name in runner.H2B_C1_ARTIFACT_NAMES},
        controlled_reason="candidate_representative_limit",
        patch_count=0,
    )


def test_c1_each_artifact_inventory_matches_its_real_stop_state(tmp_path):
    all_names = set(runner.H2B_C1_ARTIFACT_NAMES)
    patch_names = {name for name in all_names if name.startswith("patch_")}
    base = all_names - patch_names - {"c1_candidate_stop.json"}
    candidate_files = {
        "stage_progress.jsonl", "stage_stdout.txt", "stage_summary.json",
        "stage_timeline.jsonl", "stage_root_pid.json", "c1_progress.jsonl",
        "c1_stdout.txt", "c1_summary.json", "c1_timeline.jsonl", "c1_root_pid.json",
        "c1_candidate_stop.json", "c1_manifest.json", "neighborhood_ids.npy",
        "orbit_ids.npy", "representative_ids.npy", "metadata_sha256.npy",
        "provenance_sha256.npy", "row_token_sha256.npy", "row_provenance_sha256.npy",
    }
    cases = {
        "candidate_representative_limit": candidate_files,
        "MONOMIAL_TRANSFORM_NOT_PROVEN": candidate_files,
        "predicted_live_set_gate": base,
        "c1_patch_or_action_gate": base | patch_names,
        None: base | patch_names,
    }
    for index, (reason, required) in enumerate(cases.items()):
        root = tmp_path / str(index)
        root.mkdir()
        for name in required:
            (root / name).write_bytes(b"x")
        recorded = {name: runner._artifact(root, name) for name in all_names}
        assert runner._c1_artifacts_match(
            root,
            recorded,
            controlled_reason=reason,
            patch_count=1 if reason == "c1_patch_or_action_gate" else 0,
        )


def test_c1_unknown_stop_reason_and_orbit_partition_fail_closed():
    recorded = {name: {} for name in runner.H2B_C1_ARTIFACT_NAMES}
    assert not runner._c1_artifacts_match(
        Path("/tmp/c1-unused"),
        recorded,
        controlled_reason="unclassified_stop",
        patch_count=0,
    )
    audit = {
        "representative_count": 2,
        "representative_members": [list(range(0, 84, 2)), list(range(1, 84, 2))],
    }
    orbit_ids = np.asarray([0, 1] * 42, dtype=np.int32)
    representative_ids = np.asarray([0, 1] * 42, dtype=np.int32)
    metadata = np.vstack(
        [np.frombuffer(b"a" * 64, dtype=np.uint8) if index % 2 == 0
         else np.frombuffer(b"b" * 64, dtype=np.uint8)
         for index in range(84)]
    )
    assert runner._c1_orbit_partition_valid(
        audit, orbit_ids, representative_ids, metadata
    )
    representative_ids[2] = 1
    assert not runner._c1_orbit_partition_valid(
        audit, orbit_ids, representative_ids, metadata
    )


def test_c1_numeric_checker_recomputes_arrays_and_worker_has_no_factor_api():
    count = runner.H2B_C1_NEIGHBORHOOD_COUNT
    nloc = 3
    records = [
        {
            "neighborhood_id": index,
            "hermitian_error": 0.0,
            "congruence_relative_error": 0.0,
            "patch_action_relative_error": 0.0,
            "exact_action_relative_error": 0.0,
            "matrix_sha256": "a" * 64,
            "repeat_matrix_sha256": "a" * 64,
            "deterministic": True,
        }
        for index in range(count)
    ]
    arrays = {
        "patch_congruence_row_numerator_squared": np.zeros((count, nloc)),
        "patch_congruence_row_denominator_squared": np.ones((count, nloc)),
        "patch_hermitian_row_numerator_squared": np.zeros((count, nloc)),
        "patch_member_action": np.ones((count, 2, nloc), dtype=np.complex128),
        "patch_transformed_action": np.ones((count, 2, nloc), dtype=np.complex128),
        "patch_member_exact_action": np.ones((count, 2, nloc), dtype=np.complex128),
    }
    assert runner._c1_numeric_gate({"patch_audits": records}, arrays)
    arrays["patch_congruence_row_numerator_squared"][0, 0] = 1.0
    assert not runner._c1_numeric_gate({"patch_audits": records}, arrays)
    arrays["patch_congruence_row_numerator_squared"][0, 0] = 0.0
    arrays["patch_congruence_row_denominator_squared"][0, 0] = -1.0
    assert not runner._c1_numeric_gate({"patch_audits": records}, arrays)
    arrays["patch_congruence_row_denominator_squared"][0, 0] = 1.0
    records[-1]["matrix_sha256"] = "b" * 64
    records[-1]["deterministic"] = False
    evidence, gate, failure = runner._c1_numeric_state(
        {"patch_audits": records},
        arrays,
        processed_count=count,
        controlled_reason="c1_patch_or_action_gate",
    )
    assert evidence is True and gate is False and failure == count - 1
    assert "factorize_h2b_p0_patch" not in inspect.getsource(runner._run_c1_worker)
    assert "H2BP1FactorLedger.accept" not in inspect.getsource(runner._run_c1_worker)
    assert "write_h2b_p1_factor_store" not in inspect.getsource(runner._run_c1_worker)
