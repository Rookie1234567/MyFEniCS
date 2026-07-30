from __future__ import annotations

import copy
import hashlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from benchmarks.run_task032_phase6_augmented import (
    _basis_summary,
    _normalize_full3d_reference_record,
    _parse_args,
    _should_load_full3d_reference,
    _validate_case080_reference_identity,
    _verify_explicit_full3d_reference_hash,
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


def _task036_conical_watchdog_fixture() -> dict:
    fixture = _native_watchdog_fixture()
    orders = [
        {
            "side": side,
            "m": 0,
            "n": 0,
            "polarization": polarization,
            "absolute_total_projection_difference": 1.0e-14,
            "absolute_outgoing_projection_difference": 1.0e-14,
        }
        for side in ("top", "bottom")
        for polarization in ("s", "p")
    ]
    audit = {
        "requested": True,
        "tolerance": 1.0e-10,
        "max_absolute_outgoing_projection_difference": 1.0e-14,
        "pass": True,
        "orders": orders,
    }
    fixture["solver_summary"].update(
        {
            "incident_phi_deg": 90.0,
            "dtn_port_mode_count": 4,
            "dtn_port_top_mode_count": 2,
            "dtn_port_bottom_mode_count": 2,
            "auxiliary_direct_tangential_projection_audit": audit,
        }
    )
    fixture["task036_forward_robustness_gate"] = True
    fixture["task036_direct_projection_audit"] = copy.deepcopy(audit)
    fixture["qualification"].update(
        {
            "checks": {
                "task036_direct_projection_requested": True,
                "task036_direct_projection_tolerance_frozen": True,
                "task036_direct_projection_nonempty_complete_finite_orders": True,
                "task036_direct_projection_exact_mode_count": True,
                "task036_direct_projection_unique_mode_identities": True,
                "task036_direct_projection_top_bottom_coverage": True,
                "task036_direct_projection_s_p_coverage": True,
                "task036_direct_projection_max_le_1e_10": True,
                "task036_direct_projection_pass": True,
            },
            "failures": [],
        }
    )
    return fixture


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
    assert normalized["physical_model"]["polarization_kind"] == "s"
    assert (
        normalized["artifacts"]["ignored_run_root"]
        == "benchmarks/artifacts/task034/phase_f/full3d/fixture_full_solve"
    )
    assert normalized["artifacts"]["reference_npz_sha256"] == "b" * 64
    assert normalized["qualification"]["phase1_reference_pass"]
    assert not normalized["qualification"]["grid_converged"]


def test_task036_conical_watchdog_reference_preserves_incidence() -> None:
    normalized = _normalize_full3d_reference_record(
        _task036_conical_watchdog_fixture(),
        path=REFERENCE_PATH,
    )
    assert normalized["physical_model"]["incident_theta_deg"] == 80.0
    assert normalized["physical_model"]["incident_grazing_deg"] == 10.0
    assert normalized["physical_model"]["incident_phi_deg"] == 90.0
    _validate_case080_reference_identity(
        normalized,
        degree=2,
        h_nm=5.0,
        path=REFERENCE_PATH,
        polarization_kind="s",
        incident_grazing_deg=10.0,
        incident_phi_deg=90.0,
    )


@pytest.mark.parametrize(
    "mutation",
    ("qualification_check", "raw_projection_difference"),
)
def test_task036_conical_watchdog_reference_fails_closed(
    mutation: str,
) -> None:
    fixture = _task036_conical_watchdog_fixture()
    if mutation == "qualification_check":
        fixture["qualification"]["checks"][
            "task036_direct_projection_exact_mode_count"
        ] = False
    else:
        for audit in (
            fixture["task036_direct_projection_audit"],
            fixture["solver_summary"][
                "auxiliary_direct_tangential_projection_audit"
            ],
        ):
            audit["orders"][0][
                "absolute_outgoing_projection_difference"
            ] = 2.0e-10
    with pytest.raises(RuntimeError):
        _normalize_full3d_reference_record(fixture, path=REFERENCE_PATH)


def test_explicit_reference_sha_is_generic_and_fail_closed(
    tmp_path: Path,
) -> None:
    reference = tmp_path / "full3d_watchdog.json"
    reference.write_text('{"status":"full3d_reference_pass"}', encoding="utf-8")
    digest = hashlib.sha256(reference.read_bytes()).hexdigest()
    args = _parse_args(
        [
            "--degree",
            "4",
            "--h-nm",
            "10",
            "--requested-modes",
            "120",
            "--candidate-modes",
            "240",
            "--full3d-reference",
            str(reference),
            "--full3d-reference-sha256",
            digest,
            "--verified-clean-sha",
            "a" * 40,
        ]
    )
    assert args.full3d_reference_sha256 == digest
    assert (
        _verify_explicit_full3d_reference_hash(reference, digest)
        == digest
    )
    with pytest.raises(RuntimeError):
        _verify_explicit_full3d_reference_hash(reference, "0" * 64)
    with pytest.raises(SystemExit):
        _parse_args(
            [
                "--degree",
                "4",
                "--h-nm",
                "10",
                "--full3d-reference-sha256",
                digest,
                "--verified-clean-sha",
                "a" * 40,
            ]
        )


def test_explicit_reference_is_loaded_outside_legacy_ten_degree_s_case():
    explicit = Path("/tmp/task036-explicit-full3d-reference.json")
    assert _should_load_full3d_reference(
        incident_grazing_deg=0.5,
        polarization_kind="p",
        explicit_reference=explicit,
    )
    assert _should_load_full3d_reference(
        incident_grazing_deg=10.0,
        polarization_kind="s",
        explicit_reference=None,
    )
    assert not _should_load_full3d_reference(
        incident_grazing_deg=0.5,
        polarization_kind="s",
        explicit_reference=None,
    )
    assert not _should_load_full3d_reference(
        incident_grazing_deg=10.0,
        polarization_kind="p",
        explicit_reference=None,
    )


def test_task036_scalar_reciprocal_basis_is_explicit_opt_in() -> None:
    ordinary = _parse_args([])
    selected = _parse_args(
        ["--task036-scalar-stage4-reciprocal-basis"]
    )
    assert ordinary.task036_scalar_stage4_reciprocal_basis is False
    assert selected.task036_scalar_stage4_reciprocal_basis is True


def test_basis_summary_records_origin_and_construction_audit() -> None:
    basis = SimpleNamespace(
        basis_origin="analytic_scalar_stage4_reciprocal",
        basis_construction_audit={
            "pass": True,
            "independent_negative_used_for_coupling": False,
        },
        biorthogonality_matrix=np.eye(1, dtype=np.complex128),
        modes=[
            SimpleNamespace(
                beta=1.0 + 0.0j,
                direction="backward",
                kind="propagating",
                passive_branch_valid=True,
                right=SimpleNamespace(polynomial_relative_residual=1.0e-12),
                left_polynomial_relative_residual=2.0e-12,
            )
        ],
        max_identity_error=0.0,
        max_entry_identity_error=0.0,
        left_pair_relative_errors=(1.0e-13,),
        groups=(),
        near_degenerate_partition_audit={"pass": True},
        full_vector_gathered=False,
    )
    summary = _basis_summary(basis)
    assert (
        summary["basis_origin"]
        == "analytic_scalar_stage4_reciprocal"
    )
    assert summary["basis_construction_audit"]["pass"] is True
    assert (
        summary["basis_construction_audit"][
            "independent_negative_used_for_coupling"
        ]
        is False
    )


@pytest.mark.parametrize(
    ("section", "key", "value"),
    [
        (None, "status", "formal_not_pass"),
        (None, "no_swap", False),
        ("source", "stable_and_clean_after", False),
        ("qualification", "pass", False),
        ("solver_summary", "official_result", False),
        ("solver_summary", "linear_system_relative_residual", 2.0e-9),
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


def test_native_p_watchdog_reference_preserves_and_validates_p_identity() -> None:
    fixture = _native_watchdog_fixture()
    fixture["solver_summary"]["polarization_kind"] = "p"
    normalized = _normalize_full3d_reference_record(
        fixture,
        path=REFERENCE_PATH,
    )
    assert normalized["physical_model"]["polarization_kind"] == "p"
    _validate_case080_reference_identity(
        normalized,
        degree=2,
        h_nm=5.0,
        path=REFERENCE_PATH,
        polarization_kind="p",
    )
    with pytest.raises(RuntimeError):
        _validate_case080_reference_identity(
            normalized,
            degree=2,
            h_nm=5.0,
            path=REFERENCE_PATH,
            polarization_kind="s",
        )


def test_native_watchdog_reference_rejects_unknown_polarization() -> None:
    fixture = _native_watchdog_fixture()
    fixture["solver_summary"]["polarization_kind"] = "custom"
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
