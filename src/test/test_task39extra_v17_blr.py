"""Pure V17 BLR profile and admission-split contracts."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest


def _summary(*, rho: float = 0.2, field: float = 0.1) -> dict:
    rows = []
    for index in range(3):
        rows.append(
            {
                "rho": rho,
                "field_l2_relative": field,
                "scaled_curl_relative": field,
                "native_identity_relative": 1.0e-12,
            }
        )
    return {
        "solve_records": rows,
        "factor": {
            "numeric_raw": {
                "infog": {"9": 80.0, "29": 100.0, "35": 80.0},
                "rinfog": {"3": 100.0, "14": 80.0},
            }
        },
    }


def test_v17_profile_freezes_the_two_thresholds_and_stages():
    from src.io.physical_intermediate_profile import (
        P4_BLR_TRADEOFF_PROFILE,
        P4_BLR_TRADEOFF_THRESHOLDS,
        profile_facts,
        p4_blr_tradeoff_threshold,
    )

    assert P4_BLR_TRADEOFF_PROFILE in profile_facts(P4_BLR_TRADEOFF_PROFILE)["identity"]
    assert P4_BLR_TRADEOFF_THRESHOLDS == {
        "T1_BLR_CONTROL": 1.0e-3,
        "T2_BLR_CONTROL": 1.0e-4,
    }
    assert p4_blr_tradeoff_threshold("T1_BLR_CONTROL") == 1.0e-3
    assert p4_blr_tradeoff_threshold("T2_BLR_CONTROL") == 1.0e-4
    with pytest.raises(ValueError, match="T1_BLR_CONTROL"):
        p4_blr_tradeoff_threshold("S2_BLR_CONTROL")


def test_blr_factor_rejects_cross_profile_thresholds_before_backend_creation(monkeypatch):
    import src.solvers.fullspace_v17_p3_oracle as oracle

    created = {"backend": False}

    def fake_init(self, _matrix):
        created["backend"] = True

    monkeypatch.setattr(oracle._MumpsFactor, "__init__", fake_init)
    with pytest.raises(ValueError, match="frozen at CNTL"):
        oracle.MumpsBLRFactor(object(), threshold=1.0e-3)
    with pytest.raises(ValueError, match="accepts only"):
        oracle.MumpsBLRFactor(
            object(),
            profile="physical_p4_blr_tradeoff_v17",
            threshold=1.0e-5,
            enable_coverage_statistics=True,
        )
    assert created["backend"] is False


def test_t1_splitter_allows_t2_only_for_quality_failure_with_m_and_compression():
    from benchmarks.check_p4_blr_tradeoff_v17 import decide_t1

    t1 = decide_t1(
        _summary(rho=0.8),
        resource_evidence_complete=True,
        peak_ratio=0.95,
        live_ratio=0.75,
    )
    assert t1["action"] == "RUN_T2"
    assert t1["next_threshold"] == pytest.approx(1.0e-4)

    bad_resource = decide_t1(
        _summary(rho=0.8),
        resource_evidence_complete=False,
        peak_ratio=0.80,
        live_ratio=0.70,
    )
    assert bad_resource["action"] == "T5_CLOSE"

    bad_memory = decide_t1(
        _summary(rho=0.8),
        resource_evidence_complete=True,
        peak_ratio=1.10,
        live_ratio=0.90,
    )
    assert bad_memory["action"] == "T5_CLOSE"

    no_compression = copy.deepcopy(_summary(rho=0.8))
    no_compression["factor"]["numeric_raw"]["infog"]["9"] = 100.0
    assert decide_t1(
        no_compression,
        resource_evidence_complete=True,
        peak_ratio=0.80,
        live_ratio=0.70,
    )["action"] == "T5_CLOSE"


def test_t1_and_t2_selection_require_all_fixed_gates():
    from benchmarks.check_p4_blr_tradeoff_v17 import decide_t1, decide_t2

    selected = decide_t1(
        _summary(),
        resource_evidence_complete=True,
        peak_ratio=0.89,
        live_ratio=0.95,
    )
    assert selected["action"] == "SELECT_T1"
    assert decide_t2(
        _summary(),
        resource_evidence_complete=True,
        peak_ratio=0.89,
        live_ratio=0.95,
    )["action"] == "SELECT_T2"
    assert decide_t2(
        _summary(rho=0.6),
        resource_evidence_complete=True,
        peak_ratio=0.89,
        live_ratio=0.95,
    )["action"] == "T5_CLOSE"


def test_v17_checker_uses_raw_residual_facts_and_decodes_infog_units():
    from benchmarks.check_p4_blr_tradeoff_v17 import (
        _raw_compression_facts,
        quality_facts,
    )

    summary = {
        "factor": {
            "numeric_raw": {
                "infog": {"9": -53, "29": -60, "35": -54},
                "rinfog": {"3": 100.0, "14": 80.0},
            }
        },
        "solve_records": [
            {
                "rho": 9.0,
                "field_l2_relative": 9.0,
                "scaled_curl_relative": 9.0,
                "native_identity_relative": 9.0,
            }
            for _ in range(3)
        ],
    }
    compression = _raw_compression_facts(summary)
    assert compression["actual_storage_entries"] == pytest.approx(53.0e6)
    assert compression["theoretical_entries"] == pytest.approx(60.0e6)
    assert compression["effective_storage_entries"] == pytest.approx(54.0e6)
    assert compression["actual_compression_present"] is True
    summary["solve_records"] = [
        {
            "rho": 0.2,
            "field_l2_relative": 0.1,
            "scaled_curl_relative": 0.1,
            "native_identity_relative": 1.0e-12,
        }
        for _ in range(3)
    ]
    raw_quality = quality_facts(summary)
    assert raw_quality["quality_pass"] is True


@pytest.mark.parametrize(
    ("stage", "label", "marker"),
    [
        (
            "T1_BLR_CONTROL",
            "t1_blr_volume_and_augmented_preallocation",
            "v17_t1_blr_sparse_preallocation_gate",
        ),
        (
            "T2_BLR_CONTROL",
            "t2_blr_volume_and_augmented_preallocation",
            "v17_t2_blr_sparse_preallocation_gate",
        ),
    ],
)
def test_v17_preallocation_gate_covers_each_blr_control_stage(
    stage: str, label: str, marker: str
):
    from src.runners.physical_p4_schur_v14 import _v14_known_preallocation_gate

    class Runtime:
        def __init__(self):
            self.projected = []
            self.markers = []

        def check_projected(self, name, amount):
            self.projected.append((name, amount))

        def marker(self, name, facts):
            self.markers.append((name, facts))

    runtime = Runtime()
    _v14_known_preallocation_gate(
        runtime,
        stage,
        include_common=False,
        include_matrices=True,
    )
    assert [name for name, _ in runtime.projected] == [label]
    assert [name for name, _ in runtime.markers] == [marker]


def test_v17_t2_requires_hash_bound_settled_t1_decision(tmp_path: Path):
    from src.runners.task038_launcher import (
        V17_T1_DECISION_FILENAME,
        V17_T1_SUMMARY_FILENAME,
        _validate_v17_t2_prerequisite,
    )
    from src.io.input_loader import InputError

    run_directory = tmp_path / "t1"
    run_directory.mkdir()
    source_sha = "a" * 40
    summary = {"status": "STARTED", "source_sha": source_sha}
    summary_path = run_directory / V17_T1_SUMMARY_FILENAME
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    (run_directory / "run_manifest.json").write_text(
        json.dumps(
            {
                "status": "finished",
                "source_sha": source_sha,
                "source_after": {"source_sha": source_sha},
            }
        ),
        encoding="utf-8",
    )
    manifest_path = run_directory / "run_manifest.json"
    decision = {
        "schema": "task039extra.v17.independent-checker.v1",
        "directory": str(run_directory.resolve()),
        "stage": "T1_BLR_CONTROL",
        "source_sha": source_sha,
        "summary_sha256": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "decision": {
            "action": "RUN_T2",
            "next_threshold": 1.0e-4,
            "quality": {"correctness_pass": True, "quality_pass": False},
            "memory": {"memory_pass": True},
            "compression": {"actual_compression_present": True},
            "resource_evidence_complete": True,
        },
        "comparison_gates": {"raw": True, "controls": True},
    }
    decision_path = run_directory / V17_T1_DECISION_FILENAME
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    settled_ledger = {
        "stages": {
            "T1_BLR_CONTROL": {
                "active_attempt": None,
                "attempts": [
                    {
                        "source_sha": source_sha,
                        "run_directory": str(run_directory),
                        "status": "worker_exit0",
                        "actual_elapsed_seconds": 12.0,
                    }
                ],
            }
        }
    }
    facts = _validate_v17_t2_prerequisite(settled_ledger)
    assert facts["action"] == "RUN_T2"
    assert facts["decision_sha256"] == hashlib.sha256(
        decision_path.read_bytes()
    ).hexdigest()

    unsettled = json.loads(json.dumps(settled_ledger))
    unsettled["stages"]["T1_BLR_CONTROL"]["active_attempt"] = 0
    with pytest.raises(InputError, match="settled T1"):
        _validate_v17_t2_prerequisite(unsettled)

    decision["decision"]["action"] = "SELECT_T1"
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    with pytest.raises(InputError, match="RUN_T2"):
        _validate_v17_t2_prerequisite(settled_ledger)
