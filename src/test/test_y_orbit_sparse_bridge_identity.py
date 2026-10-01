"""Bridge receipt identity regressions; no numerical qualification implied."""
import hashlib
import json

import pytest

from benchmarks import run_y_orbit_sparse_probe as runner


def _write(path, value):
    path.write_text(json.dumps(value, sort_keys=True))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    source = {"head": "f" * 40, "branch": "task40extra_dot_parallel_cloud", "dirty": "", "files_sha256": {}}
    report = {"status": "SPARSE_CONDENSED_FULL3D_PROBE_PASS", "degree": 2,
              "source_clean_unchanged": True, "source": source,
              "saved_dense_p2_bridge": {"passed": True}, "artifacts": {}}
    path = tmp_path / "probe_report.json"
    digest = _write(path, report)
    provenance_hash = _write(tmp_path / "provenance.json", {"source": source})
    watcher = tmp_path / "checker_supervision"
    watcher.mkdir()
    watcher_hash = _write(watcher / "summary.json", {"classification": "COMPLETED", "source_state": source,
        "sampled_process_tree_swap_peak_bytes": 0, "process_tree_all_status_readable": True,
        "process_tree_all_identity_complete": True, "descendants_cleared": True})
    checker = {"gate_pass": True, "evidence_valid": True, "report_sha256": digest,
        "provenance_sha256": provenance_hash,
        "artifact_manifest_sha256": hashlib.sha256(b"{}").hexdigest(), "source": source, "degree": 2,
        "checker_watchdog_receipt": {"path": "checker_supervision/summary.json", "sha256": watcher_hash}}
    _write(tmp_path / "independent_checker.json", checker)
    return path, digest, source, checker


def test_bridge_receipt_is_bound_to_exact_report_and_manifest(tmp_path, monkeypatch):
    path, digest, source, _ = _fixture(tmp_path, monkeypatch)
    assert runner._validate_bridge(path, digest, source["head"], source)["report_sha256"] == digest


@pytest.mark.parametrize("field", ["report_sha256", "provenance_sha256", "artifact_manifest_sha256"])
def test_stale_or_swapped_checker_pass_cannot_unlock_p4(tmp_path, monkeypatch, field):
    path, digest, source, checker = _fixture(tmp_path, monkeypatch)
    checker[field] = "0" * 64
    _write(tmp_path / "independent_checker.json", checker)
    with pytest.raises(RuntimeError, match="bridge has not passed"):
        runner._validate_bridge(path, digest, source["head"], source)


def test_checker_without_evidence_valid_cannot_unlock_p4(tmp_path, monkeypatch):
    path, digest, source, checker = _fixture(tmp_path, monkeypatch)
    checker["evidence_valid"] = False
    _write(tmp_path / "independent_checker.json", checker)
    with pytest.raises(RuntimeError, match="bridge has not passed"):
        runner._validate_bridge(path, digest, source["head"], source)
