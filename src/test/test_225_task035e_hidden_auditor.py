from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import stat

import pytest

from src.adaptivity.blind_controller import (
    build_unmeasured_h_level3_saturation_authority,
    build_unmeasured_p6_saturation_authority,
    h_level3_saturation_authority_payload,
    p6_saturation_authority_payload,
)
from src.adaptivity.hidden_auditor import (
    CANDIDATE_BUNDLE_SCHEMA,
    CANDIDATE_OUTPUT_SCHEMA,
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
    FREEZE_RECEIPT_SCHEMA,
    TWO_PATH_GATE_SCHEMA,
    HiddenAuditContractError,
    HiddenAuditReport,
    audit_frozen_candidate,
    build_hidden_audit_payload,
    canonical_json_sha256,
    preflight_frozen_candidate,
    validate_hidden_audit_payload,
)
from src.adaptivity.reference_certifier import (
    ComplexObservation,
    ComplexValue,
    DiffractionOrderObservation,
    PhysicalRunIdentity,
    REQUIRED_TOTAL_SCALARS,
    ReferenceCampaign,
    ReferenceRunResult,
    RunGateEvidence,
    ScalarObservation,
    certify_reference_campaign,
    write_sealed_reference_package,
)


def _identity() -> PhysicalRunIdentity:
    return PhysicalRunIdentity(
        geometry_sha256="1" * 64,
        material_sha256="2" * 64,
        incident_sha256="3" * 64,
        dtn_definition_sha256="4" * 64,
        postprocessing_sha256="5" * 64,
        source_sha="6" * 40,
    )


def _reference_orders() -> tuple[DiffractionOrderObservation, ...]:
    rows = []
    for port_index, port in enumerate(("top", "bottom")):
        order_pairs = (
            *((m, 0) for m in (0, -1, -2, -3, -4, -5, -6, -7)),
            (-2, 1),
        )
        for local_index, (m, n) in enumerate(order_pairs):
            index = port_index * len(order_pairs) + local_index
            propagating = m >= -5
            rows.append(
                DiffractionOrderObservation(
                    port=port,
                    m=m,
                    n=n,
                    propagating=propagating,
                    kz=(
                        ComplexValue(0.5 + 0.01 * index, 0.0)
                        if propagating
                        else ComplexValue(0.0, 0.2 + 0.01 * index)
                    ),
                    admittance=ComplexValue(1.0 + 0.02 * index, 0.0),
                    normalization_identity=(
                        f"official-dtn-normalization/{port}/m{m}/n{n}"
                    ),
                    total_power=(
                        1.0e-4 * (index + 1) if propagating else None
                    ),
                    co_polarized_amplitude=ComplexValue(
                        0.01 * (index + 1),
                        -0.005 * (index + 1),
                    ),
                    cross_polarized_power=(
                        1.0e-8 * (index + 1) if propagating else None
                    ),
                    cross_polarized_amplitude=ComplexValue(
                        1.0e-4 * (index + 1),
                        2.0e-4 * (index + 1),
                    ),
                )
            )
    return tuple(rows)


def _reference_run(h_nm: float) -> ReferenceRunResult:
    totals = {
        "R00_s": 9.0e-4,
        "R00_p": 1.0e-4,
        "R00_total": 1.0e-3,
        "R_total": 1.0e-3,
        "T_total": 0.6,
        "A_closure": 0.399,
        "A_volume": 0.399,
        "energy_closure": 0.0,
    }
    assert set(totals) == set(REQUIRED_TOTAL_SCALARS)
    return ReferenceRunResult(
        h_nm=h_nm,
        identity=_identity(),
        gate=RunGateEvidence(
            completed=True,
            full_explicit_true_residual=1.0e-12,
            energy_balance_error=2.0e-12,
            closure_volume_error=3.0e-12,
            official_postprocessing_passed=True,
            swap_peak_bytes=0,
            minimum_memory_headroom_fraction=0.4,
        ),
        evidence_sha256={
            10.0: "a" * 64,
            7.5: "b" * 64,
            5.0: "c" * 64,
        }[h_nm],
        scalar_observations=(
            *(
                ScalarObservation(name, value, "total")
                for name, value in sorted(totals.items())
            ),
            ScalarObservation(
                "interface_probe_l2",
                0.25,
                "interface_field",
            ),
            ScalarObservation(
                "volume_probe_l2",
                0.50,
                "volume_field",
            ),
        ),
        complex_observations=(
            ComplexObservation(
                "interface_probe_complex",
                ComplexValue(0.3, -0.2),
                "interface_field",
            ),
            ComplexObservation(
                "volume_probe_complex",
                ComplexValue(-0.1, 0.4),
                "volume_field",
            ),
        ),
        diffraction_orders=_reference_orders(),
    )


def _sealed_reference(tmp_path: Path) -> Path:
    campaign = ReferenceCampaign(
        h10=_reference_run(10.0),
        h7p5=_reference_run(7.5),
        h5=_reference_run(5.0),
    )
    certification = certify_reference_campaign(campaign)
    assert certification.qualified is True
    path = tmp_path / "sealed-reference.json"
    write_sealed_reference_package(path, certification)
    return path


def _candidate_outputs() -> dict[str, object]:
    h5 = _reference_run(5.0)
    port_index = {"top": 0, "bottom": 1}
    orders = sorted(
        h5.diffraction_orders,
        key=lambda row: (port_index[row.port], -row.m, row.n),
    )
    return {
        "schema_version": CANDIDATE_OUTPUT_SCHEMA,
        "orders": [
            {
                "port": row.port,
                "m": row.m,
                "n": row.n,
                "propagating": row.propagating,
                "total_power": row.total_power,
                "co_polarized_amplitude": {
                    "real": row.co_polarized_amplitude.real,
                    "imag": row.co_polarized_amplitude.imag,
                },
                "cross_polarized_power": row.cross_polarized_power,
                "cross_polarized_amplitude": {
                    "real": row.cross_polarized_amplitude.real,
                    "imag": row.cross_polarized_amplitude.imag,
                },
                "kz": {"real": row.kz.real, "imag": row.kz.imag},
                "admittance": {
                    "real": row.admittance.real,
                    "imag": row.admittance.imag,
                },
                "normalization_identity": row.normalization_identity,
            }
            for row in orders
        ],
        "scalar_observations": [
            {"name": row.name, "value": row.value}
            for row in h5.scalar_observations
        ],
        "complex_observations": [
            {
                "name": row.name,
                "value": {
                    "real": row.value.real,
                    "imag": row.value.imag,
                },
            }
            for row in h5.complex_observations
        ],
        "full_explicit_true_residual": 1.0e-12,
    }


def _candidate_and_receipt(
    *,
    outputs: dict[str, object] | None = None,
) -> tuple[dict[str, object], dict[str, object]]:
    outputs = outputs or _candidate_outputs()
    identity = {
        "trial_id": "blind-trial-A",
        "algorithm_id": "exact-sequence-hp-v1",
        "source_sha": "6" * 40,
        "initial_path_id": "path-A-h20",
        "initial_mesh_forest_sha256": "a" * 64,
        "cycle_chain_root_sha256": "b" * 64,
        "cycle_index": 5,
        "geometry_sha256": "1" * 64,
        "material_sha256": "2" * 64,
        "incident_sha256": "3" * 64,
        "dtn_definition_sha256": "4" * 64,
        "postprocessing_sha256": "5" * 64,
        "mesh_forest_sha256": "7" * 64,
        "degree_map_sha256": "8" * 64,
    }
    output_sha = canonical_json_sha256(outputs)
    physical_identity = {
        name: identity[name]
        for name in (
            "geometry_sha256",
            "material_sha256",
            "incident_sha256",
            "dtn_definition_sha256",
            "postprocessing_sha256",
            "source_sha",
        )
    }
    physical_identity_sha256 = canonical_json_sha256(physical_identity)
    two_path_gate = {
        "schema_version": TWO_PATH_GATE_SCHEMA,
        "pass": True,
        "algorithm_id": identity["algorithm_id"],
        "source_sha": identity["source_sha"],
        "physical_identity_sha256": physical_identity_sha256,
        "left_trial_id": identity["trial_id"],
        "right_trial_id": "blind-trial-B",
        "left_initial_path_id": "path-A-h20",
        "right_initial_path_id": "path-B-h15",
        "left_initial_mesh_forest_sha256": (
            identity["initial_mesh_forest_sha256"]
        ),
        "right_initial_mesh_forest_sha256": "c" * 64,
        "left_cycle_chain_root_sha256": identity["cycle_chain_root_sha256"],
        "right_cycle_chain_root_sha256": "d" * 64,
        "left_output_sha256": output_sha,
        "right_output_sha256": "9" * 64,
        "maximum_normalized_goal_distance": 0.0,
        "per_goal": {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS},
    }
    resource_authority = {
        "schema_version": "task035e.resource-authority.v1",
        "active_dofs": 80_000,
        "rows": 40_000,
        "matrix_nnz": 30_000_000,
        "factor_nnz": 180_000_000,
        "solver_peak_bytes": 9_000_000_000,
        "swap_peak_bytes": 0,
        "mpi_size": 8,
        "same_solver_lifecycle_telemetry": True,
    }
    p6_saturation = build_unmeasured_p6_saturation_authority(
        p6_target_ids=(),
        current_plan_file_sha256="4" * 64,
        current_mesh_forest_sha256=identity["mesh_forest_sha256"],
        current_degree_map_sha256=identity["degree_map_sha256"],
    )
    h_level3_saturation = build_unmeasured_h_level3_saturation_authority(
        level_two_target_ids=(),
        periodic_orbit_ids=(),
        orbit_catalog_sha256="a" * 64,
        current_plan_file_sha256="4" * 64,
        current_mesh_forest_sha256=identity["mesh_forest_sha256"],
        current_degree_map_sha256=identity["degree_map_sha256"],
    )
    internal_certificate = {
        "schema_version": "task035e.blind-internal-certificate.v2",
        "cycle_index": identity["cycle_index"],
        "accepted_current_state": True,
        "status": "freeze_ready",
        "reasons": ["both_shadow_lanes_inside_freeze_threshold"],
        "selected_action_bindings": [],
        "p_shadow_maximum": 0.1,
        "h_shadow_maximum": 0.1,
        "p_enrichment_action_count": 1,
        "h_enrichment_action_count": 1,
        "stable_from_previous": True,
        "stable_streak": 2,
        "freeze_ready": True,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
        "goal_sha256": "e" * 64,
        "mesh_forest_sha256": identity["mesh_forest_sha256"],
        "degree_map_sha256": identity["degree_map_sha256"],
        "plan_file_sha256": "4" * 64,
        "plan_content_sha256": "5" * 64,
        "plan_solver_content_sha256": "6" * 64,
        "state_sha256": "7" * 64,
        "solution_snapshot_sha256": "f" * 64,
        "watchdog_record_file_sha256": "8" * 64,
        "complete_output_sha256": output_sha,
        "full_residual_sha256": "0" * 64,
        "adjoint_bundle_sha256": "1" * 64,
        "shadow_catalog_sha256": "2" * 64,
        "p6_saturation": p6_saturation_authority_payload(
            p6_saturation
        ),
        "h_level3_saturation": h_level3_saturation_authority_payload(
            h_level3_saturation
        ),
        "executed_verification_sha256": "3" * 64,
        "stability_repeat_verification": None,
        "stability_repeat_verification_sha256": canonical_json_sha256(None),
        "resource_inventory_sha256": canonical_json_sha256(
            resource_authority
        ),
        "gates": {
            "full_explicit_residual": 1.0e-12,
            "energy_closure_error": 0.0,
            "absorption_volume": 0.399,
            "floquet_residual_pass": True,
            "hanging_residual_pass": True,
            "serial_mpi_identity_pass": True,
            "multilevel_mesh_pass": True,
            "separated_patch_count": 2,
            "all_local_levels_present": True,
            "algebraic_budget_fraction": 0.05,
            "dtn_budget_fraction": 0.05,
            "postprocess_budget_fraction": 0.05,
        },
    }
    candidate: dict[str, object] = {
        "schema_version": CANDIDATE_BUNDLE_SCHEMA,
        "identity": identity,
        "outputs": outputs,
        "internal_certificate": internal_certificate,
        "resource_authority": resource_authority,
        "two_path_gate": two_path_gate,
    }
    unsigned_receipt: dict[str, object] = {
        "schema_version": FREEZE_RECEIPT_SCHEMA,
        "trial_id": identity["trial_id"],
        "algorithm_id": identity["algorithm_id"],
        "source_sha": identity["source_sha"],
        "initial_path_id": identity["initial_path_id"],
        "initial_mesh_forest_sha256": (
            identity["initial_mesh_forest_sha256"]
        ),
        "cycle_chain_root_sha256": identity["cycle_chain_root_sha256"],
        "cycle_index": identity["cycle_index"],
        "physical_identity_sha256": physical_identity_sha256,
        "mesh_forest_sha256": identity["mesh_forest_sha256"],
        "degree_map_sha256": identity["degree_map_sha256"],
        "output_sha256": output_sha,
        "internal_certificate_sha256": canonical_json_sha256(
            internal_certificate
        ),
        "resource_inventory_sha256": canonical_json_sha256(
            resource_authority
        ),
        "two_path_gate_sha256": canonical_json_sha256(two_path_gate),
    }
    receipt = {
        **unsigned_receipt,
        "frozen_payload_sha256": canonical_json_sha256(unsigned_receipt),
    }
    return candidate, receipt


def _rebind_internal_certificate_receipt(
    candidate: dict[str, object],
    receipt: dict[str, object],
) -> dict[str, object]:
    rebound = {
        **receipt,
        "internal_certificate_sha256": canonical_json_sha256(
            candidate["internal_certificate"]
        ),
    }
    unsigned = dict(rebound)
    unsigned.pop("frozen_payload_sha256")
    rebound["frozen_payload_sha256"] = canonical_json_sha256(unsigned)
    return rebound


def _measured_p6_saturation_payload(
    internal: dict[str, object],
    *,
    target_ids: list[str],
    normalized_max: float,
) -> dict[str, object]:
    target_sha = canonical_json_sha256(
        {"canonical_target_ids": target_ids}
    )
    unsigned: dict[str, object] = {
        "schema_version": "task035e.p6-saturation-authority.v1",
        "status": (
            "measured_pass"
            if normalized_max <= 0.5
            else "measured_fail"
        ),
        "current_plan_file_sha256": internal["plan_file_sha256"],
        "current_mesh_forest_sha256": internal["mesh_forest_sha256"],
        "current_degree_map_sha256": internal["degree_map_sha256"],
        "p6_target_count": len(target_ids),
        "p6_target_ids": target_ids,
        "p6_target_ids_sha256": target_sha,
        "covered_target_count": len(target_ids),
        "covered_target_ids": target_ids,
        "covered_target_ids_sha256": target_sha,
        "coverage_complete": True,
        "shadow_only": True,
        "selectable_as_production": False,
        "normalized_max": normalized_max,
        "evidence_kind": "independent_p7_shadow",
        "evidence_sha256": "f" * 64,
    }
    return {
        **unsigned,
        "authority_sha256": canonical_json_sha256(unsigned),
    }


def _measured_h_level3_saturation_payload(
    internal: dict[str, object],
    *,
    normalized_max: float,
) -> dict[str, object]:
    targets = ["cell:r0:l2:i0:j0:k0"]
    orbits = ["h3-orbit-000000-abc123"]
    target_sha = canonical_json_sha256(
        {"canonical_target_ids": targets}
    )
    orbit_sha = canonical_json_sha256(
        {"canonical_orbit_ids": orbits}
    )
    unsigned: dict[str, object] = {
        "schema_version": "task035e.h-level3-saturation-authority.v1",
        "status": (
            "measured_pass"
            if normalized_max <= 0.5
            else "measured_fail"
        ),
        "current_plan_file_sha256": internal["plan_file_sha256"],
        "current_mesh_forest_sha256": internal["mesh_forest_sha256"],
        "current_degree_map_sha256": internal["degree_map_sha256"],
        "level_two_target_count": 1,
        "level_two_target_ids": targets,
        "level_two_target_ids_sha256": target_sha,
        "periodic_orbit_count": 1,
        "periodic_orbit_ids": orbits,
        "periodic_orbit_ids_sha256": orbit_sha,
        "orbit_catalog_sha256": "a" * 64,
        "covered_target_count": 1,
        "covered_target_ids": targets,
        "covered_target_ids_sha256": target_sha,
        "covered_orbit_count": 1,
        "covered_orbit_ids": orbits,
        "covered_orbit_ids_sha256": orbit_sha,
        "coverage_complete": True,
        "production_maximum_level": 2,
        "shadow_maximum_level": 3,
        "shadow_only": True,
        "selectable_as_production": False,
        "normalized_max": normalized_max,
        "normalized_limit": 0.5,
        "evidence_kind": "independent_global_level3_shadow",
        "evidence_sha256": "b" * 64,
    }
    return {
        **unsigned,
        "authority_sha256": canonical_json_sha256(unsigned),
    }


def test_fixed_n8_and_full_propagating_spectrum_audit_pass(
    tmp_path: Path,
) -> None:
    reference_path = _sealed_reference(tmp_path)
    candidate, freeze_receipt = _candidate_and_receipt()
    receipt_path = tmp_path / "audit" / "terminal.json"

    execution = audit_frozen_candidate(
        freeze_receipt=freeze_receipt,
        candidate_bundle=candidate,
        sealed_reference_path=reference_path,
        audit_receipt_path=receipt_path,
    )

    report = execution.report
    assert report.passed is True
    assert report.terminal is True
    assert report.status == "REFERENCE_BLIND_HP_ACCURACY_PASS"
    counts = report.counts_payload()
    assert counts["power_passed"] == counts["power_total"] == 16
    assert counts["power_applicable"] == 12
    assert counts["amplitude_passed"] == counts["amplitude_total"] == 16
    assert counts["total_passed"] == counts["total_total"] == 7
    assert counts["field_passed"] == counts["field_total"] == 2
    assert execution.write_receipt is not None
    assert execution.write_receipt.terminal is True
    assert stat.S_IMODE(receipt_path.stat().st_mode) == (
        stat.S_IRUSR | stat.S_IWUSR
    )
    payload = json.loads(receipt_path.read_text(encoding="utf-8"))
    validate_hidden_audit_payload(payload)
    assert payload["counts"]["amplitude_total"] == 16
    spectrum_gate = next(
        gate
        for gate in report.gates
        if gate.gate_id == "full_propagating_spectrum_audit"
    )
    assert spectrum_gate.passed is True
    assert spectrum_gate.actual["status"] == "completed"
    assert len(spectrum_gate.actual["reference_orders"]) == 14
    assert len(spectrum_gate.actual["candidate_orders"]) == 14
    assert spectrum_gate.actual["total_value_count"] == 56
    assert spectrum_gate.actual["passed_value_count"] == 56


def test_full_spectrum_missing_order_fails_terminal_with_exact_inventory(
    tmp_path: Path,
) -> None:
    reference_path = _sealed_reference(tmp_path)
    outputs = _candidate_outputs()
    orders = outputs["orders"]
    assert isinstance(orders, list)
    outputs["orders"] = [
        row
        for row in orders
        if (row["port"], row["m"], row["n"]) != ("top", -2, 1)
    ]
    candidate, freeze_receipt = _candidate_and_receipt(outputs=outputs)

    report = audit_frozen_candidate(
        freeze_receipt=freeze_receipt,
        candidate_bundle=candidate,
        sealed_reference_path=reference_path,
        audit_receipt_path=tmp_path / "missing-spectrum-terminal.json",
    ).report

    assert report.passed is False
    spectrum_gate = next(
        gate
        for gate in report.gates
        if gate.gate_id == "full_propagating_spectrum_audit"
    )
    assert spectrum_gate.passed is False
    assert spectrum_gate.actual["missing_candidate_orders"] == [
        {"port": "top", "m": -2, "n": 1}
    ]
    assert spectrum_gate.actual["unexpected_candidate_orders"] == []


@pytest.mark.parametrize(
    "quantity",
    (
        "total_power",
        "cross_polarized_power",
        "co_polarized_amplitude",
        "cross_polarized_amplitude",
    ),
)
def test_full_spectrum_co_and_cross_values_are_all_audited(
    tmp_path: Path,
    quantity: str,
) -> None:
    reference_path = _sealed_reference(tmp_path)
    outputs = _candidate_outputs()
    orders = outputs["orders"]
    assert isinstance(orders, list)
    row = next(
        item
        for item in orders
        if (item["port"], item["m"], item["n"]) == ("top", -2, 1)
    )
    if quantity.endswith("amplitude"):
        row[quantity]["real"] += 1.0e-2
    else:
        row[quantity] += 1.0e-2
    candidate, freeze_receipt = _candidate_and_receipt(outputs=outputs)

    report = audit_frozen_candidate(
        freeze_receipt=freeze_receipt,
        candidate_bundle=candidate,
        sealed_reference_path=reference_path,
        audit_receipt_path=tmp_path / f"{quantity}-terminal.json",
    ).report

    assert report.passed is False
    spectrum_gate = next(
        gate
        for gate in report.gates
        if gate.gate_id == "full_propagating_spectrum_audit"
    )
    comparison = next(
        item
        for item in spectrum_gate.actual["value_comparisons"]
        if (
            item["port"],
            item["m"],
            item["n"],
            item["quantity"],
        )
        == ("top", -2, 1, quantity)
    )
    assert comparison["passed"] is False
    assert comparison["actual_error"] == pytest.approx(1.0e-2)


def test_full_spectrum_metadata_drift_fails_closed(tmp_path: Path) -> None:
    reference_path = _sealed_reference(tmp_path)
    outputs = _candidate_outputs()
    orders = outputs["orders"]
    assert isinstance(orders, list)
    row = next(
        item
        for item in orders
        if (item["port"], item["m"], item["n"]) == ("bottom", -2, 1)
    )
    row["admittance"]["real"] += 1.0e-3
    candidate, freeze_receipt = _candidate_and_receipt(outputs=outputs)

    report = audit_frozen_candidate(
        freeze_receipt=freeze_receipt,
        candidate_bundle=candidate,
        sealed_reference_path=reference_path,
        audit_receipt_path=tmp_path / "metadata-terminal.json",
    ).report
    spectrum_gate = next(
        gate
        for gate in report.gates
        if gate.gate_id == "full_propagating_spectrum_audit"
    )
    metadata = next(
        item
        for item in spectrum_gate.actual["metadata_comparisons"]
        if (item["port"], item["m"], item["n"]) == ("bottom", -2, 1)
    )
    assert report.passed is False
    assert spectrum_gate.passed is False
    assert metadata["passed"] is False


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        ("duplicate", "duplicate physical diffraction orders"),
        ("unsorted", "not canonically sorted"),
        ("missing_fixed", "complete fixed N=8 subset"),
    ),
)
def test_candidate_full_spectrum_preflight_is_closed_before_hidden_access(
    mutation: str,
    message: str,
) -> None:
    outputs = _candidate_outputs()
    orders = outputs["orders"]
    assert isinstance(orders, list)
    if mutation == "duplicate":
        orders.append(deepcopy(orders[-1]))
    elif mutation == "unsorted":
        orders[0], orders[1] = orders[1], orders[0]
    else:
        outputs["orders"] = [
            row
            for row in orders
            if (row["port"], row["m"], row["n"]) != ("top", 0, 0)
        ]
    candidate, receipt = _candidate_and_receipt(outputs=outputs)
    with pytest.raises(HiddenAuditContractError, match=message):
        preflight_frozen_candidate(receipt, candidate)


def test_hidden_preflight_rejects_unloaded_p7_shadow_for_p6_only_lane() -> None:
    candidate, receipt = _candidate_and_receipt()
    internal = candidate["internal_certificate"]
    assert isinstance(internal, dict)
    internal["p_enrichment_action_count"] = 0
    internal["p6_saturation"] = _measured_p6_saturation_payload(
        internal,
        target_ids=["cell:r0:l0:i0:j0:k0"],
        normalized_max=0.25,
    )
    rebound = _rebind_internal_certificate_receipt(candidate, receipt)

    with pytest.raises(
        HiddenAuditContractError,
        match="no independently loaded p7 evidence artifact",
    ):
        preflight_frozen_candidate(rebound, candidate)


def test_hidden_preflight_rejects_unknown_or_tampered_p6_saturation() -> None:
    candidate, receipt = _candidate_and_receipt()
    internal = candidate["internal_certificate"]
    assert isinstance(internal, dict)
    internal["p_enrichment_action_count"] = 0
    unknown = build_unmeasured_p6_saturation_authority(
        p6_target_ids=("cell:r0:l0:i0:j0:k0",),
        current_plan_file_sha256=str(internal["plan_file_sha256"]),
        current_mesh_forest_sha256=str(
            internal["mesh_forest_sha256"]
        ),
        current_degree_map_sha256=str(internal["degree_map_sha256"]),
    )
    internal["p6_saturation"] = p6_saturation_authority_payload(
        unknown
    )
    rebound = _rebind_internal_certificate_receipt(candidate, receipt)
    with pytest.raises(
        HiddenAuditContractError,
        match="p6 saturation is not independently freeze-ready",
    ):
        preflight_frozen_candidate(rebound, candidate)

    internal["p6_saturation"] = _measured_p6_saturation_payload(
        internal,
        target_ids=["cell:r0:l0:i0:j0:k0"],
        normalized_max=0.25,
    )
    saturation = internal["p6_saturation"]
    assert isinstance(saturation, dict)
    saturation["p6_target_count"] = 2
    rebound = _rebind_internal_certificate_receipt(candidate, receipt)
    with pytest.raises(
        HiddenAuditContractError,
        match="target_count differs",
    ):
        preflight_frozen_candidate(rebound, candidate)


def test_hidden_preflight_rejects_unloaded_level3_h_saturation() -> None:
    candidate, receipt = _candidate_and_receipt()
    internal = candidate["internal_certificate"]
    assert isinstance(internal, dict)
    internal["h_enrichment_action_count"] = 0
    internal["h_level3_saturation"] = (
        _measured_h_level3_saturation_payload(
            internal,
            normalized_max=0.5,
        )
    )
    rebound = _rebind_internal_certificate_receipt(candidate, receipt)

    with pytest.raises(
        HiddenAuditContractError,
        match="no independently loaded level3 evidence artifact",
    ):
        preflight_frozen_candidate(rebound, candidate)


def test_hidden_preflight_rejects_unknown_or_tampered_h_saturation() -> None:
    candidate, receipt = _candidate_and_receipt()
    internal = candidate["internal_certificate"]
    assert isinstance(internal, dict)
    internal["h_enrichment_action_count"] = 0
    unknown = build_unmeasured_h_level3_saturation_authority(
        level_two_target_ids=("cell:r0:l2:i0:j0:k0",),
        periodic_orbit_ids=("h3-orbit-000000-abc123",),
        orbit_catalog_sha256="a" * 64,
        current_plan_file_sha256=str(internal["plan_file_sha256"]),
        current_mesh_forest_sha256=str(
            internal["mesh_forest_sha256"]
        ),
        current_degree_map_sha256=str(internal["degree_map_sha256"]),
    )
    internal["h_level3_saturation"] = (
        h_level3_saturation_authority_payload(unknown)
    )
    rebound = _rebind_internal_certificate_receipt(candidate, receipt)
    with pytest.raises(
        HiddenAuditContractError,
        match="level3 h saturation is not independently freeze-ready",
    ):
        preflight_frozen_candidate(rebound, candidate)

    internal["h_level3_saturation"] = (
        _measured_h_level3_saturation_payload(
            internal,
            normalized_max=0.25,
        )
    )
    saturation = internal["h_level3_saturation"]
    assert isinstance(saturation, dict)
    saturation["periodic_orbit_count"] = 2
    rebound = _rebind_internal_certificate_receipt(candidate, receipt)
    with pytest.raises(
        HiddenAuditContractError,
        match="periodic_orbit_count differs",
    ):
        preflight_frozen_candidate(rebound, candidate)


def test_full_spectrum_gate_payload_is_independently_recomputed(
    tmp_path: Path,
) -> None:
    reference_path = _sealed_reference(tmp_path)
    candidate, freeze_receipt = _candidate_and_receipt()
    report = audit_frozen_candidate(
        freeze_receipt=freeze_receipt,
        candidate_bundle=candidate,
        sealed_reference_path=reference_path,
        audit_receipt_path=tmp_path / "recompute-terminal.json",
    ).report
    payload = build_hidden_audit_payload(report)
    spectrum_gate = next(
        gate
        for gate in payload["gates"]
        if gate["gate_id"] == "full_propagating_spectrum_audit"
    )
    comparison = spectrum_gate["actual"]["value_comparisons"][0]
    comparison["candidate_value"] += 1.0e-2
    unsigned = dict(payload)
    unsigned.pop("audit_payload_sha256")
    payload["audit_payload_sha256"] = canonical_json_sha256(unsigned)

    with pytest.raises(
        HiddenAuditContractError,
        match="actual_error is not recomputable",
    ):
        validate_hidden_audit_payload(payload)


def test_failed_channel_is_preserved_with_actual_tolerance_and_terminal(
    tmp_path: Path,
) -> None:
    reference_path = _sealed_reference(tmp_path)
    outputs = _candidate_outputs()
    orders = outputs["orders"]
    assert isinstance(orders, list)
    orders[0]["total_power"] += 1.0e-2
    outputs["full_explicit_true_residual"] = 2.0e-9
    candidate, freeze_receipt = _candidate_and_receipt(outputs=outputs)

    execution = audit_frozen_candidate(
        freeze_receipt=freeze_receipt,
        candidate_bundle=candidate,
        sealed_reference_path=reference_path,
        audit_receipt_path=tmp_path / "failed-terminal.json",
    )

    report = execution.report
    assert report.passed is False
    assert report.terminal is True
    assert report.status == "BLIND_STOP_FALSE_POSITIVE"
    failed_power = next(
        item
        for item in report.items
        if item.output_id == "order/top/m0/n0/total_power"
    )
    assert failed_power.passed is False
    assert failed_power.actual_error == pytest.approx(1.0e-2)
    assert failed_power.tolerance == pytest.approx(5.0e-8)
    residual_gate = next(
        gate
        for gate in report.gates
        if gate.gate_id == "full_explicit_true_residual"
    )
    assert residual_gate.actual == 2.0e-9
    assert residual_gate.passed is False

    payload = build_hidden_audit_payload(report)
    payload["items"][0]["actual_error"] = 0.0
    with pytest.raises(
        HiddenAuditContractError,
        match="payload SHA-256 mismatch",
    ):
        validate_hidden_audit_payload(payload)


def test_output_tamper_fails_before_hidden_package_is_opened(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidate, freeze_receipt = _candidate_and_receipt()
    tampered = deepcopy(candidate)
    outputs = tampered["outputs"]
    assert isinstance(outputs, dict)
    outputs["full_explicit_true_residual"] = 5.0e-10
    opened = False

    def forbidden_open(path: object) -> dict[str, object]:
        del path
        nonlocal opened
        opened = True
        raise AssertionError("sealed package was opened before preflight")

    monkeypatch.setattr(
        "src.adaptivity.hidden_auditor.package_reader."
        "_load_sealed_reference_package",
        forbidden_open,
    )
    with pytest.raises(
        HiddenAuditContractError,
        match="does not bind candidate outputs",
    ):
        audit_frozen_candidate(
            freeze_receipt=freeze_receipt,
            candidate_bundle=tampered,
            sealed_reference_path=tmp_path / "must-not-open.json",
            audit_receipt_path=tmp_path / "must-not-write.json",
        )
    assert opened is False


def test_hidden_preflight_replays_stability_repeat_identity() -> None:
    candidate, freeze_receipt = _candidate_and_receipt()
    internal = candidate["internal_certificate"]
    assert isinstance(internal, dict)
    unsigned_repeat = {
        "schema_version": "task035e.stability-repeat-verification.v1",
        "action_id": "stability-repeat-cycle-2",
        "action_kind": "p-keep",
        "action_sha256": "9" * 64,
        "action_file_sha256": "a" * 64,
        "action_identity_sha256": "b" * 64,
        "from_state_sha256": "c" * 64,
        "next_state_sha256": internal["state_sha256"],
        "previous_plan_file_sha256": "d" * 64,
        "previous_plan_content_sha256": "e" * 64,
        "previous_plan_solver_content_sha256": internal[
            "plan_solver_content_sha256"
        ],
        "next_plan_file_sha256": internal["plan_file_sha256"],
        "next_plan_content_sha256": internal["plan_content_sha256"],
        "next_plan_solver_content_sha256": internal[
            "plan_solver_content_sha256"
        ],
        "previous_mesh_forest_sha256": internal["mesh_forest_sha256"],
        "next_mesh_forest_sha256": internal["mesh_forest_sha256"],
        "previous_degree_map_sha256": internal["degree_map_sha256"],
        "next_degree_map_sha256": internal["degree_map_sha256"],
        "before_solution_snapshot_sha256": "0" * 64,
        "after_solution_snapshot_sha256": internal[
            "solution_snapshot_sha256"
        ],
        "before_watchdog_record_file_sha256": "1" * 64,
        "after_watchdog_record_file_sha256": internal[
            "watchdog_record_file_sha256"
        ],
    }
    repeat_payload = {
        **unsigned_repeat,
        "verification_sha256": canonical_json_sha256(unsigned_repeat),
    }
    internal["stability_repeat_verification"] = repeat_payload
    internal["stability_repeat_verification_sha256"] = repeat_payload[
        "verification_sha256"
    ]
    rebound = {
        **freeze_receipt,
        "internal_certificate_sha256": canonical_json_sha256(internal),
    }
    rebound_unsigned = dict(rebound)
    rebound_unsigned.pop("frozen_payload_sha256")
    rebound["frozen_payload_sha256"] = canonical_json_sha256(
        rebound_unsigned
    )
    preflight_frozen_candidate(rebound, candidate)

    repeat_payload["next_mesh_forest_sha256"] = "f" * 64
    unsigned_tampered = dict(repeat_payload)
    unsigned_tampered.pop("verification_sha256")
    repeat_payload["verification_sha256"] = canonical_json_sha256(
        unsigned_tampered
    )
    internal["stability_repeat_verification_sha256"] = repeat_payload[
        "verification_sha256"
    ]
    rebound = {
        **rebound,
        "internal_certificate_sha256": canonical_json_sha256(internal),
    }
    rebound_unsigned = dict(rebound)
    rebound_unsigned.pop("frozen_payload_sha256")
    rebound["frozen_payload_sha256"] = canonical_json_sha256(
        rebound_unsigned
    )
    with pytest.raises(
        HiddenAuditContractError,
        match="p-keep changed mesh, degree, or solver content",
    ):
        preflight_frozen_candidate(rebound, candidate)


@pytest.mark.parametrize(
    ("target", "expected_message"),
    (
        ("source", "candidate source_sha differ"),
        ("mesh", "candidate mesh_forest_sha256 differ"),
        ("degree", "candidate degree_map_sha256 differ"),
        ("internal", "frozen internal certificate SHA-256 mismatch"),
        ("resource", "does not bind resource authority"),
        ("two_path", "frozen two-path gate SHA-256 mismatch"),
    ),
)
def test_every_frozen_binding_fails_before_hidden_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    target: str,
    expected_message: str,
) -> None:
    candidate, freeze_receipt = _candidate_and_receipt()
    identity = candidate["identity"]
    assert isinstance(identity, dict)
    if target == "source":
        identity["source_sha"] = "e" * 40
    elif target == "mesh":
        identity["mesh_forest_sha256"] = "e" * 64
    elif target == "degree":
        identity["degree_map_sha256"] = "e" * 64
    elif target == "internal":
        internal = candidate["internal_certificate"]
        assert isinstance(internal, dict)
        internal["p_shadow_maximum"] = 0.2
    elif target == "resource":
        resource = candidate["resource_authority"]
        assert isinstance(resource, dict)
        resource["rows"] += 1
    else:
        two_path = candidate["two_path_gate"]
        assert isinstance(two_path, dict)
        two_path["maximum_normalized_goal_distance"] = 0.25

    opened = False

    def forbidden_open(path: object) -> dict[str, object]:
        del path
        nonlocal opened
        opened = True
        raise AssertionError("sealed package was opened before preflight")

    monkeypatch.setattr(
        "src.adaptivity.hidden_auditor.package_reader."
        "_load_sealed_reference_package",
        forbidden_open,
    )
    with pytest.raises(
        HiddenAuditContractError,
        match=expected_message,
    ):
        audit_frozen_candidate(
            freeze_receipt=freeze_receipt,
                candidate_bundle=candidate,
                sealed_reference_path=tmp_path / "must-not-open.json",
                audit_receipt_path=tmp_path / f"{target}-must-not-write.json",
        )
    assert opened is False


def test_two_path_gate_and_physical_identity_fail_closed(
    tmp_path: Path,
) -> None:
    reference_path = _sealed_reference(tmp_path)
    candidate, _ = _candidate_and_receipt()
    gate = candidate["two_path_gate"]
    assert isinstance(gate, dict)
    gate["right_initial_path_id"] = gate["left_initial_path_id"]
    _, receipt = _candidate_and_receipt()
    candidate["two_path_gate"] = deepcopy(
        candidate["two_path_gate"]
    )
    unsigned = dict(receipt)
    unsigned.pop("frozen_payload_sha256")
    unsigned["two_path_gate_sha256"] = canonical_json_sha256(
        candidate["two_path_gate"]
    )
    receipt = {
        **unsigned,
        "frozen_payload_sha256": canonical_json_sha256(unsigned),
    }
    with pytest.raises(
        HiddenAuditContractError,
        match="two distinct initial paths",
    ):
        audit_frozen_candidate(
            freeze_receipt=receipt,
            candidate_bundle=candidate,
            sealed_reference_path=reference_path,
            audit_receipt_path=tmp_path / "two-path-must-not-write.json",
        )


@pytest.mark.parametrize(
    "missing_goal",
    ("scalar/R_total", "complex/interface_probe_complex/imag"),
)
def test_hidden_preflight_rejects_incomplete_formal_two_path_inventory(
    missing_goal: str,
) -> None:
    candidate, receipt = _candidate_and_receipt()
    gate = candidate["two_path_gate"]
    assert isinstance(gate, dict)
    per_goal = gate["per_goal"]
    assert isinstance(per_goal, dict)
    per_goal.pop(missing_goal)

    unsigned = dict(receipt)
    unsigned.pop("frozen_payload_sha256")
    unsigned["two_path_gate_sha256"] = canonical_json_sha256(gate)
    rebound_receipt = {
        **unsigned,
        "frozen_payload_sha256": canonical_json_sha256(unsigned),
    }

    with pytest.raises(
        HiddenAuditContractError,
        match="complete formal goal inventory",
    ):
        preflight_frozen_candidate(rebound_receipt, candidate)


def test_hidden_audit_is_one_shot_and_empty_report_is_rejected(
    tmp_path: Path,
) -> None:
    reference_path = _sealed_reference(tmp_path)
    candidate, freeze_receipt = _candidate_and_receipt()
    audit_frozen_candidate(
        freeze_receipt=freeze_receipt,
        candidate_bundle=candidate,
        sealed_reference_path=reference_path,
        audit_receipt_path=tmp_path / "first-terminal.json",
    )
    with pytest.raises(HiddenAuditContractError, match="already consumed"):
        audit_frozen_candidate(
            freeze_receipt=freeze_receipt,
            candidate_bundle=candidate,
            sealed_reference_path=reference_path,
            audit_receipt_path=tmp_path / "second-terminal.json",
        )
    with pytest.raises(HiddenAuditContractError, match="inventory is incomplete"):
        HiddenAuditReport(
            status="REFERENCE_BLIND_HP_ACCURACY_PASS",
            passed=True,
            terminal=True,
            candidate_frozen_payload_sha256="1" * 64,
            candidate_output_sha256="2" * 64,
            reference_sealed_payload_sha256="3" * 64,
            reference_campaign_binding_sha256="4" * 64,
            items=(),
            gates=(),
        )
