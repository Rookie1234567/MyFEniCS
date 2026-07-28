from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

import pytest

from benchmarks.task035e_case098_checker import (
    CASE098,
    Task035eCase098EvidenceError,
    check_case098,
    main,
)


SOURCE_SHA = "a" * 40
ARTIFACT_SHA = "b" * 64


def _copy_case(tmp_path: Path) -> Path:
    case = tmp_path / "case098"
    case.mkdir()
    for name in ("config.json", "expected.json", "schema.json"):
        shutil.copy2(CASE098 / name, case / name)
    (case / "records").mkdir()
    return case


def _load_config(case: Path) -> dict[str, Any]:
    payload = json.loads((case / "config.json").read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


def _write_config(case: Path, payload: dict[str, Any]) -> None:
    (case / "config.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_source_record(case: Path) -> tuple[str, str]:
    path = case / "records" / "synthetic_authority.json"
    path.write_text(
        json.dumps({"source_sha": SOURCE_SHA}, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return "records/synthetic_authority.json", hashlib.sha256(
        path.read_bytes(),
    ).hexdigest()


def _pointer(path: str, sha256: str, status: str = "completed") -> dict[str, Any]:
    return {
        "status": status,
        "path": path,
        "sha256": sha256,
        "source_sha": SOURCE_SHA,
    }


def _completed_cycle(
    index: int,
    path: str,
    sha256: str,
    *,
    p_verified: bool,
    h_verified: bool,
) -> dict[str, Any]:
    return {
        "cycle_index": index,
        "accepted": True,
        "full_explicit_true_residual": 1.0e-11,
        "energy_identity_error": 1.0e-11,
        "max_normalized_p_shadow_delta": 0.25,
        "max_normalized_h_shadow_delta": 0.25,
        "level_counts": {"0": 20, "1": 40, "2": 80},
        "separated_patch_count": 2,
        "maximum_adjacent_level_jump": 1,
        "periodic_closure_pass": True,
        "material_interface_pass": True,
        "hanging_trace_pass": True,
        "mpi_ownership_pass": True,
        "p_shadow_verified": p_verified,
        "h_shadow_verified": h_verified,
        "outputs_stable_to_previous": True,
        "evidence": _pointer(path, sha256),
    }


def _make_synthetic_completed(case: Path) -> dict[str, Any]:
    config = _load_config(case)
    evidence_path, evidence_sha = _write_source_record(case)
    config["source_commit_sha"] = SOURCE_SHA
    config["campaign_status"] = "completed"
    config["numerical_credit_claimed"] = True

    for layer in config["layer_packages"].values():
        layer["package_manifest"] = _pointer(evidence_path, evidence_sha)

    for run in config["reference_campaign"]["runs"]:
        run["status"] = "completed"
        run["evidence"] = _pointer(evidence_path, evidence_sha)
        run["gate"] = {
            "completed_full_solve": True,
            "full_explicit_true_residual": 1.0e-11,
            "energy_identity_error": 1.0e-11,
            "absorption_identity_error": 1.0e-11,
            "physical_memory_free_fraction_after": 0.3,
            "swap_gib": 0.0,
        }
    config["reference_campaign"]["convergence_authority"] = _pointer(
        evidence_path,
        evidence_sha,
    )
    config["reference_campaign"]["qualification_claimed"] = True

    for blind_path in config["blind_trials"]["paths"]:
        blind_path["status"] = "frozen"
        blind_path["cycles"] = [
            _completed_cycle(
                1,
                evidence_path,
                evidence_sha,
                p_verified=True,
                h_verified=False,
            ),
            _completed_cycle(
                2,
                evidence_path,
                evidence_sha,
                p_verified=False,
                h_verified=True,
            ),
        ]
        blind_path["final_authority"] = _pointer(
            evidence_path,
            evidence_sha,
        )
    config["blind_trials"]["two_start_comparison"] = {
        "max_normalized_output_difference": 0.2,
        "evidence": _pointer(evidence_path, evidence_sha),
    }

    config["freeze"] = {
        "status": "frozen",
        "candidate_immutable": True,
        "source_commit_sha": SOURCE_SHA,
        "mesh_forest_sha256": ARTIFACT_SHA,
        "degree_map_sha256": ARTIFACT_SHA,
        "output_sha256": ARTIFACT_SHA,
        "internal_certificate_sha256": ARTIFACT_SHA,
        "resource_authority_sha256": ARTIFACT_SHA,
    }
    config["hidden_audit"] = {
        "status": "completed",
        "opened_after_freeze": True,
        "power_pass_count": 16,
        "complex_amplitude_pass_count": 16,
        "full_propagating_spectrum_pass": True,
        "total_observables_pass": True,
        "field_observables_pass": True,
        "residual_and_energy_pass": True,
        "candidate_retuned_after_open": False,
        "evidence": _pointer(evidence_path, evidence_sha),
    }
    config["resource_ledger"]["full3d"] = {
        "status": "completed",
        "active_rows": 50000,
        "matrix_nnz": 41000000,
        "factor_nnz": 200000000,
        "solver_phase_peak_gib": 10.5,
        "swap_gib": 0.0,
        "same_mpi_solver_lifecycle_telemetry": True,
        "evidence": _pointer(evidence_path, evidence_sha),
    }
    return config


def test_case098_scaffold_is_valid_but_has_no_numerical_credit() -> None:
    report = check_case098()
    assert report["evidence_valid"] is True
    assert report["classification"] == "SCAFFOLD_NOT_RUN"
    assert report["completion_pass"] is False
    assert report["reference_qualified"] is False
    assert report["hidden_audit_pass"] is False
    assert report["ordinary_default_changed"] is False
    assert report["reference_run_gate_pass"] == {
        "p6_h10": False,
        "p6_h7p5": False,
        "p6_h5": False,
    }


def test_case098_rejects_dummy_evidence_even_when_config_claims_success(
    tmp_path: Path,
) -> None:
    case = _copy_case(tmp_path)
    config = _make_synthetic_completed(case)
    _write_config(case, config)
    with pytest.raises(
        Task035eCase098EvidenceError,
        match="layer package manifest keys differ",
    ):
        check_case098(case)


def test_case098_rejects_unknown_root_and_nested_properties(
    tmp_path: Path,
) -> None:
    case = _copy_case(tmp_path)
    config = _load_config(case)
    config["unexpected"] = True
    _write_config(case, config)
    with pytest.raises(
        Task035eCase098EvidenceError,
        match="strict schema validation failed",
    ):
        check_case098(case)

    config.pop("unexpected")
    config["goal_contract"]["hidden_reference_path"] = "forbidden.json"
    _write_config(case, config)
    with pytest.raises(
        Task035eCase098EvidenceError,
        match="strict schema validation failed",
    ):
        check_case098(case)


def test_case098_not_run_cannot_be_renamed_to_completed(
    tmp_path: Path,
) -> None:
    case = _copy_case(tmp_path)
    config = _load_config(case)
    config["campaign_status"] = "completed"
    config["numerical_credit_claimed"] = True
    _write_config(case, config)
    with pytest.raises(
        Task035eCase098EvidenceError,
        match="numerical_credit_claimed",
    ):
        check_case098(case)


def test_case098_controlled_h5_resource_stop_is_not_reference_success(
    tmp_path: Path,
) -> None:
    case = _copy_case(tmp_path)
    config = _load_config(case)
    controlled_path = case / "records" / "h5_controlled_stop.json"
    controlled_path.write_text(
        json.dumps(
            {
                "schema_version": "task033.full3d-watchdog.v1",
                "source": {"commit_sha": SOURCE_SHA},
                "degree": 6,
                "h_nm": 5.0,
                "run_kind": "full-solve",
                "mpi_size": 8,
                "status": "controlled_resource_stop",
                "qualification": {"pass": False},
                "no_swap": True,
                "task035e_reference_certifier": {
                    "schema_version": (
                        "task035e.reference-resource-authority.v1"
                    ),
                    "selected": True,
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    evidence_path = "records/h5_controlled_stop.json"
    evidence_sha = hashlib.sha256(controlled_path.read_bytes()).hexdigest()
    config["source_commit_sha"] = SOURCE_SHA
    config["campaign_status"] = "controlled_stop"
    h5 = next(
        run
        for run in config["reference_campaign"]["runs"]
        if run["run_id"] == "p6_h5"
    )
    h5["status"] = "controlled_resource_stop"
    h5["gate"]["completed_full_solve"] = False
    h5["evidence"] = _pointer(
        evidence_path,
        evidence_sha,
        "controlled_resource_stop",
    )
    _write_config(case, config)
    report = check_case098(case)
    assert report["classification"] == "REFERENCE_CERTIFICATION_INCOMPLETE"
    assert report["reference_qualified"] is False
    assert report["completion_pass"] is False


def test_case098_rejects_hash_and_source_identity_drift(
    tmp_path: Path,
) -> None:
    case = _copy_case(tmp_path)
    config = _load_config(case)
    evidence_path, _ = _write_source_record(case)
    config["source_commit_sha"] = SOURCE_SHA
    config["campaign_status"] = "in_progress"
    h10 = config["reference_campaign"]["runs"][0]
    h10["status"] = "failed_gate"
    h10["evidence"] = _pointer(evidence_path, "0" * 64, "failed_gate")
    _write_config(case, config)
    with pytest.raises(Task035eCase098EvidenceError, match="SHA-256 mismatch"):
        check_case098(case)


def test_case098_fixed_n8_and_six_cycle_contract_fail_closed(
    tmp_path: Path,
) -> None:
    case = _copy_case(tmp_path)
    config = _load_config(case)
    config["goal_contract"]["m"][-1] = -8
    _write_config(case, config)
    with pytest.raises(
        Task035eCase098EvidenceError,
        match="fixed N=8 contract",
    ):
        check_case098(case)

    config = _load_config(CASE098)
    config["blind_trials"]["maximum_cycles_per_path"] = 7
    _write_config(case, config)
    with pytest.raises(Task035eCase098EvidenceError, match="cycle cap"):
        check_case098(case)


def test_case098_cli_distinguishes_integrity_from_completion(
    tmp_path: Path,
) -> None:
    output = tmp_path / "check.json"
    assert main(["--output", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["evidence_valid"] is True
    assert report["completion_pass"] is False
    assert main(["--output", str(output), "--require-complete"]) == 1
