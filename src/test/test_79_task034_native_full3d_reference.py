from __future__ import annotations

import copy
from pathlib import Path

import pytest

from benchmarks.run_task032_phase6_augmented import (
    _normalize_full3d_reference_record,
)


ROOT = Path(__file__).resolve().parents[2]
REFERENCE_PATH = (
    ROOT
    / "benchmarks/artifacts/task034/phase_f/records/"
    "fixture_full3d_watchdog.json"
)
RUN_ROOT = (
    ROOT
    / "benchmarks/artifacts/task034/phase_f/full3d/"
    "fixture_full_solve"
)


def _native_watchdog_fixture() -> dict:
    return {
        "schema_version": "task033.full3d-watchdog.v1",
        "status": "full3d_reference_pass",
        "run_kind": "full-solve",
        "degree": 2,
        "h_nm": 5.0,
        "mpi_size": 8,
        "no_swap": True,
        "source": {
            "commit_sha": "a" * 40,
            "tracked_source_dirty": False,
            "stable_and_clean_after": True,
        },
        "qualification": {"pass": True},
        "resource_authority": {"memory_authority_gib": 3.0},
        "solver_summary": {
            "case_status": "completed",
            "official_result": True,
            "polarization_kind": "s",
            "incident_theta_deg": 80.0,
            "incident_phi_deg": 0.0,
            "linear_system_relative_residual": 1.0e-11,
            "R_total": 0.1,
            "T_total": 0.5,
            "A_balance": 0.4,
            "A_volume_total": 0.4,
            "energy_closure_error_port_volume": 0.0,
            "full3d_reference_exported": True,
            "full3d_reference_archive": str(
                RUN_ROOT / "full3d_reference_samples.npz"
            ),
            "full3d_reference_metadata": str(
                RUN_ROOT / "full3d_reference_samples.json"
            ),
            "full3d_reference_archive_sha256": "b" * 64,
        },
    }


def test_native_watchdog_reference_normalizes_in_memory() -> None:
    normalized = _normalize_full3d_reference_record(
        _native_watchdog_fixture(),
        path=REFERENCE_PATH,
    )
    assert normalized["record_type"] == "task034_full3d_reference"
    assert normalized["metadata"]["commit_sha"] == "a" * 40
    assert normalized["physical_model"]["nedelec_degree"] == 2
    assert normalized["physical_model"]["mesh_h_nm"] == 5.0
    assert normalized["physical_model"]["mpi_size"] == 8
    assert (
        normalized["artifacts"]["ignored_run_root"]
        == "benchmarks/artifacts/task034/phase_f/full3d/fixture_full_solve"
    )
    assert normalized["artifacts"]["reference_npz_sha256"] == "b" * 64
    assert normalized["qualification"]["phase1_reference_pass"]
    assert not normalized["qualification"]["grid_converged"]


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        (None, "status", "formal_not_pass"),
        (None, "no_swap", False),
        ("source", "stable_and_clean_after", False),
        ("qualification", "pass", False),
        ("solver_summary", "official_result", False),
        ("solver_summary", "linear_system_relative_residual", 2.0e-9),
        ("solver_summary", "polarization_kind", "p"),
        ("solver_summary", "full3d_reference_exported", False),
    ],
)
def test_native_watchdog_reference_fails_closed(
    section: str | None,
    key: str,
    value: object,
) -> None:
    fixture = _native_watchdog_fixture()
    target = fixture if section is None else fixture[section]
    target[key] = value
    with pytest.raises(RuntimeError):
        _normalize_full3d_reference_record(fixture, path=REFERENCE_PATH)


def test_legacy_descriptor_is_preserved_without_rewriting() -> None:
    descriptor = {"record_type": "task034_full3d_reference"}
    original = copy.deepcopy(descriptor)
    assert (
        _normalize_full3d_reference_record(
            descriptor,
            path=REFERENCE_PATH,
        )
        is descriptor
    )
    assert descriptor == original
