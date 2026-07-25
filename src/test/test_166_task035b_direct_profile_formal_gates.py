"""Fail-closed physical and PETSc provenance gates for the direct profiler."""

from __future__ import annotations

from dataclasses import replace
import math
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from benchmarks.run_task035b_direct_setup_profile import (
    DIRECT_SETUP_TYPED_PETSC_OPTIONS,
    _classify_profile,
    _direct_config,
    _extract_setup_evidence,
    _raw_petsc_option_provenance,
    _typed_direct_petsc_option_audit,
)


def _collective_petsc_provenance() -> dict[str, object]:
    return {
        "schema_version": (
            "task035b.collective-petsc-option-provenance.v1"
        ),
        "rank_count": 8,
        "raw_audit_present_on_all_ranks": True,
        "typed_audit_present_on_all_ranks": True,
        "raw_options_absent_on_all_ranks": True,
        "typed_allowlist_pass_on_all_ranks": True,
        "rank_audits_identical": True,
        "pass": True,
    }


def _physical_evidence() -> dict[str, object]:
    return {
        "case_status": "completed",
        "official_result": True,
        "diagnostic_only": False,
        "postprocess_skipped": False,
        "mpi_size": 8,
        "R00_total": 7.5e-4,
        "R_total": 7.6e-4,
        "T_total": 0.60,
        "A_closure": 0.39924,
        "petsc_option_provenance": _collective_petsc_provenance(),
        "configuration_identity": {
            "direct_solver_profile": "default",
            "condensed_iterative_profile": None,
            "typed_direct_petsc_options": dict(
                DIRECT_SETUP_TYPED_PETSC_OPTIONS
            ),
        },
    }


def _classify(evidence: dict[str, object]) -> dict[str, object]:
    return _classify_profile(
        evidence,
        {"observed_worker_rank_count": 8},
        cache_state="cold",
        source_sha="a" * 40,
        expected_mpi_size=8,
        return_code=0,
        terminated_for_memory=False,
        terminated_for_timeout=False,
        telemetry_readable=True,
        source_stable_and_clean_after=True,
        expected_canonical_orientation_class_reuse=True,
    )


def test_direct_config_uses_only_the_typed_mumps_allowlist() -> None:
    cfg = _direct_config(
        source_sha="a" * 40,
        cache_directory=Path("/tmp/task035b-unused-cache"),
        cache_state="cold",
        h_nm=15.0,
        canonical_orientation_class_reuse=True,
    )
    audit = _typed_direct_petsc_option_audit(cfg)
    assert audit["pass"] is True
    assert audit["configured_options"] == DIRECT_SETUP_TYPED_PETSC_OPTIONS
    assert audit["provenance"] == (
        "runner_constant_allowlist_not_raw_environment_or_cli"
    )

    changed = replace(
        cfg,
        petsc_extra_options={
            **DIRECT_SETUP_TYPED_PETSC_OPTIONS,
            "ksp_type": "gmres",
        },
    )
    assert _typed_direct_petsc_option_audit(changed)["pass"] is False


def test_raw_petsc_environment_is_hashed_and_fails_closed() -> None:
    with patch.dict(
        os.environ,
        {"PETSC_OPTIONS": "-ksp_type gmres"},
        clear=False,
    ):
        audit = _raw_petsc_option_provenance()
    assert audit["PETSC_OPTIONS_present"] is True
    assert audit["PETSC_OPTIONS_nonempty"] is True
    assert isinstance(audit["PETSC_OPTIONS_sha256"], str)
    assert audit["raw_options_absent"] is False
    assert "PETSC_OPTIONS_value" not in audit
    assert audit["raw_option_values_recorded"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("case_status", "failed"),
        ("official_result", False),
        ("diagnostic_only", True),
        ("postprocess_skipped", True),
    ],
)
def test_nonphysical_or_incomplete_run_fails_formal_gate(
    field: str,
    value: object,
) -> None:
    evidence = _physical_evidence()
    evidence[field] = value
    result = _classify(evidence)
    assert (
        result["checks"]["physical_full_run_completed"]
        is False
    )
    assert result["formal_profile_pass"] is False


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("R00_total", None),
        ("R_total", math.nan),
        ("T_total", math.inf),
        ("A_closure", -math.inf),
    ],
)
def test_nonfinite_physical_observable_fails_formal_gate(
    field: str,
    value: object,
) -> None:
    evidence = _physical_evidence()
    evidence[field] = value
    result = _classify(evidence)
    assert (
        result["checks"]["physical_R00_R_T_Aclosure_finite"]
        is False
    )
    assert result["formal_profile_pass"] is False


def test_collective_raw_and_typed_petsc_provenance_is_required() -> None:
    evidence = _physical_evidence()
    result = _classify(evidence)
    assert (
        result["checks"][
            "raw_petsc_options_absent_on_all_worker_ranks"
        ]
        is True
    )
    assert (
        result["checks"][
            "typed_direct_petsc_options_exact_allowlist"
        ]
        is True
    )

    provenance = evidence["petsc_option_provenance"]
    assert isinstance(provenance, dict)
    provenance["raw_options_absent_on_all_ranks"] = False
    rejected = _classify(evidence)
    assert (
        rejected["checks"][
            "raw_petsc_options_absent_on_all_worker_ranks"
        ]
        is False
    )
    assert rejected["evidence_valid"] is False


def test_worker_evidence_preserves_physical_and_petsc_provenance() -> None:
    provenance = _collective_petsc_provenance()
    evidence = _extract_setup_evidence(
        {
            "status": "worker_completed_with_summary",
            "rank_failures": [],
            "petsc_option_provenance": provenance,
            "summary": {
                "case_status": "completed",
                "official_result": True,
                "diagnostic_only": False,
                "postprocess_skipped": False,
                "R00_total": 0.1,
                "R_total": 0.2,
                "T_total": 0.3,
                "config": {
                    "petsc_direct_solver_profile": "default",
                    "stage4_condensed_iterative_profile": None,
                    "petsc_extra_options": dict(
                        DIRECT_SETUP_TYPED_PETSC_OPTIONS
                    ),
                },
            },
        }
    )
    assert evidence["petsc_option_provenance"] == provenance
    assert evidence["A_closure"] == pytest.approx(0.5)
    assert evidence["configuration_identity"][
        "typed_direct_petsc_options"
    ] == DIRECT_SETUP_TYPED_PETSC_OPTIONS
