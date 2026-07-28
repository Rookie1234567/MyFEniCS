from __future__ import annotations

from dataclasses import replace
import json
import math
from pathlib import Path
import stat

import pytest

from src.adaptivity.reference_certifier import (
    CertificationPolicy,
    ComplexObservation,
    ComplexValue,
    DiffractionOrderObservation,
    PhysicalRunIdentity,
    QUALIFIED,
    REFERENCE_CERTIFICATION_FAILED,
    REFERENCE_CERTIFICATION_INCOMPLETE,
    REQUIRED_TOTAL_SCALARS,
    ReferenceCampaign,
    ReferenceCertifier,
    ReferenceRunResult,
    RunGateEvidence,
    SEALED_REFERENCE_PACKAGE_JSON_SCHEMA,
    ScalarObservation,
    SealedReferencePackageError,
    build_sealed_reference_package,
    certify_reference_campaign,
    fixed_order_inventory,
    read_sealed_reference_package,
    validate_sealed_reference_package,
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


def _smooth_real(center: float, coefficient: float, h_nm: float) -> float:
    return center + coefficient * h_nm**2


def _smooth_complex(
    center: complex,
    coefficient: complex,
    h_nm: float,
) -> ComplexValue:
    return ComplexValue.from_complex(center + coefficient * h_nm**2)


def _orders(h_nm: float) -> tuple[DiffractionOrderObservation, ...]:
    rows = []
    for port_index, port in enumerate(("top", "bottom")):
        for m in (0, -1, -2, -3, -4, -5, -6, -7):
            propagating = m >= -5
            index = port_index * 8 - m
            total_power = (
                _smooth_real(
                    1.0e-4 * (index + 1),
                    1.0e-9 * (index + 1),
                    h_nm,
                )
                if propagating
                else None
            )
            cross_power = (
                _smooth_real(
                    1.0e-8 * (index + 1),
                    1.0e-13 * (index + 1),
                    h_nm,
                )
                if propagating
                else None
            )
            rows.append(
                DiffractionOrderObservation(
                    port=port,
                    m=m,
                    n=0,
                    propagating=propagating,
                    kz=(
                        ComplexValue(0.5 + 0.01 * index, 0.0)
                        if propagating
                        else ComplexValue(0.0, 0.2 + 0.01 * index)
                    ),
                    admittance=ComplexValue(
                        1.0 + 0.02 * index,
                        0.0,
                    ),
                    normalization_identity=(
                        f"official-dtn-normalization/{port}/m{m}/n0"
                    ),
                    total_power=total_power,
                    co_polarized_amplitude=_smooth_complex(
                        complex(
                            0.01 * (index + 1),
                            -0.005 * (index + 1),
                        ),
                        complex(
                            2.0e-7 * (index + 1),
                            -1.0e-7 * (index + 1),
                        ),
                        h_nm,
                    ),
                    cross_polarized_power=cross_power,
                    cross_polarized_amplitude=_smooth_complex(
                        complex(
                            1.0e-4 * (index + 1),
                            2.0e-4 * (index + 1),
                        ),
                        complex(
                            1.0e-9 * (index + 1),
                            2.0e-9 * (index + 1),
                        ),
                        h_nm,
                    ),
                )
            )
    return tuple(rows)


def _run(
    h_nm: float,
    *,
    overrides: dict[str, float] | None = None,
) -> ReferenceRunResult:
    centers = {
        "R00_s": 7.0e-4,
        "R00_p": 1.0e-5,
        "R00_total": 7.1e-4,
        "R_total": 7.6e-4,
        "T_total": 0.6027,
        "A_closure": 0.39654,
        "A_volume": 0.39654,
        "energy_closure": 1.0,
    }
    coefficients = {
        name: (index + 1) * 1.0e-8 for index, name in enumerate(sorted(centers))
    }
    values = {
        name: _smooth_real(centers[name], coefficients[name], h_nm) for name in centers
    }
    values.update(overrides or {})
    scalars = [
        ScalarObservation(
            name=name,
            value=values[name],
            category="total",
        )
        for name in sorted(REQUIRED_TOTAL_SCALARS)
    ]
    scalars.extend(
        (
            ScalarObservation(
                name="interface_probe_l2",
                value=_smooth_real(0.25, 2.0e-5, h_nm),
                category="interface_field",
            ),
            ScalarObservation(
                name="volume_probe_l2",
                value=_smooth_real(0.5, -1.0e-5, h_nm),
                category="volume_field",
            ),
        )
    )
    complex_observations = (
        ComplexObservation(
            name="interface_probe_complex",
            value=_smooth_complex(
                complex(0.3, -0.2),
                complex(2.0e-5, -1.0e-5),
                h_nm,
            ),
            category="interface_field",
        ),
        ComplexObservation(
            name="volume_probe_complex",
            value=_smooth_complex(
                complex(-0.1, 0.4),
                complex(-1.0e-5, 3.0e-5),
                h_nm,
            ),
            category="volume_field",
        ),
    )
    return ReferenceRunResult(
        h_nm=h_nm,
        identity=_identity(),
        gate=RunGateEvidence(
            completed=True,
            full_explicit_true_residual=_smooth_real(
                1.0e-12,
                1.0e-15,
                h_nm,
            ),
            energy_balance_error=_smooth_real(
                2.0e-12,
                2.0e-15,
                h_nm,
            ),
            closure_volume_error=_smooth_real(
                3.0e-12,
                3.0e-15,
                h_nm,
            ),
            official_postprocessing_passed=True,
            swap_peak_bytes=0,
            minimum_memory_headroom_fraction=0.40,
        ),
        evidence_sha256={
            10.0: "a" * 64,
            7.5: "b" * 64,
            5.0: "c" * 64,
        }[h_nm],
        scalar_observations=tuple(scalars),
        complex_observations=complex_observations,
        diffraction_orders=_orders(h_nm),
    )


def _campaign(
    *,
    h10_overrides: dict[str, float] | None = None,
    h7p5_overrides: dict[str, float] | None = None,
    h5_overrides: dict[str, float] | None = None,
) -> ReferenceCampaign:
    return ReferenceCampaign(
        h10=_run(10.0, overrides=h10_overrides),
        h7p5=_run(7.5, overrides=h7p5_overrides),
        h5=_run(5.0, overrides=h5_overrides),
    )


def test_fixed_n8_inventory_and_three_point_qualification() -> None:
    assert len(fixed_order_inventory()) == 16
    assert fixed_order_inventory()[0] == ("top", 0, 0)
    assert fixed_order_inventory()[-1] == ("bottom", -7, 0)

    certification = certify_reference_campaign(_campaign())
    assert certification.status == QUALIFIED
    assert certification.qualified is True
    assert certification.gates.passed is True
    assert certification.reasons == ()

    by_id = {row.output_id: row for row in certification.convergence}
    scalar = by_id["scalar/R_total"]
    assert scalar.d_10_7p5 > scalar.d_7p5_5
    assert scalar.monotonic is True
    assert scalar.sign_oscillation is False
    assert scalar.fit_stable is True
    assert scalar.fitted_q == pytest.approx(2.0, abs=1.0e-8)
    assert scalar.fitted_q_positive is True
    h5_scalars = {row.name: row.value for row in _run(5.0).scalar_observations}
    assert scalar.reference_center == h5_scalars["R_total"]
    assert scalar.reference_uncertainty == pytest.approx(
        max(
            scalar.d_7p5_5,
            scalar.h5_to_extrapolated_center,
        )
    )

    complex_row = by_id["order/top/m-2/n0/co_polarized_amplitude"]
    assert complex_row.value_kind == "complex"
    assert complex_row.fit_stable is True
    assert complex_row.fitted_q == pytest.approx(2.0, abs=1.0e-8)
    assert isinstance(complex_row.reference_center, ComplexValue)


def test_unexplained_oscillation_fails_closed() -> None:
    campaign = _campaign(
        h10_overrides={"R_total": 0.80},
        h7p5_overrides={"R_total": 0.70},
        h5_overrides={"R_total": 0.75},
    )
    certification = certify_reference_campaign(campaign)
    assert certification.status == REFERENCE_CERTIFICATION_FAILED
    assert certification.qualified is False
    assert certification.gates.no_unexplained_oscillation is False
    assert "unexplained_oscillation:scalar/R_total" in certification.reasons

    explicitly_explained = certify_reference_campaign(
        campaign,
        policy=CertificationPolicy(
            explained_oscillatory_output_ids=("scalar/R_total",)
        ),
    )
    assert explicitly_explained.status == QUALIFIED
    assert explicitly_explained.qualified is True


def test_diagnostic_cross_oscillation_and_pointwise_field_sign_do_not_fail() -> None:
    campaign = _campaign()
    h10_orders = list(campaign.h10.diffraction_orders)
    h7_orders = list(campaign.h7p5.diffraction_orders)
    h5_orders = list(campaign.h5.diffraction_orders)
    h10_orders[0] = replace(
        h10_orders[0],
        cross_polarized_amplitude=ComplexValue(1.0e-15, 0.0),
    )
    h7_orders[0] = replace(
        h7_orders[0],
        cross_polarized_amplitude=ComplexValue(-1.0e-15, 0.0),
    )
    h5_orders[0] = replace(
        h5_orders[0],
        cross_polarized_amplitude=ComplexValue(1.0e-15, 0.0),
    )
    h7_fields = list(campaign.h7p5.complex_observations)
    h5_fields = list(campaign.h5.complex_observations)
    h7_fields[0] = replace(
        h7_fields[0],
        value=ComplexValue(1.0e-15, 0.0),
    )
    h5_fields[0] = replace(
        h5_fields[0],
        value=ComplexValue(-1.0e-15, 0.0),
    )
    diagnostic = replace(
        campaign,
        h10=replace(
            campaign.h10,
            diffraction_orders=tuple(h10_orders),
        ),
        h7p5=replace(
            campaign.h7p5,
            diffraction_orders=tuple(h7_orders),
            complex_observations=tuple(h7_fields),
        ),
        h5=replace(
            campaign.h5,
            diffraction_orders=tuple(h5_orders),
            complex_observations=tuple(h5_fields),
        ),
    )
    certification = certify_reference_campaign(diagnostic)
    assert certification.qualified is True
    by_id = {row.output_id: row for row in certification.convergence}
    assert by_id[
        "order/top/m0/n0/cross_polarized_amplitude"
    ].sign_oscillation is True
    assert certification.gates.no_unexplained_oscillation is True
    assert certification.gates.selected_fields_stable is True


def test_material_oscillation_below_formal_tolerance_is_not_false_failure() -> None:
    campaign = _campaign()
    h10 = list(campaign.h10.diffraction_orders)
    h7 = list(campaign.h7p5.diffraction_orders)
    h5 = list(campaign.h5.diffraction_orders)
    for rows, value in (
        (h10, 1.0e-12),
        (h7, 2.0e-12),
        (h5, 1.5e-12),
    ):
        rows[0] = replace(rows[0], total_power=value)
    tiny = replace(
        campaign,
        h10=replace(campaign.h10, diffraction_orders=tuple(h10)),
        h7p5=replace(campaign.h7p5, diffraction_orders=tuple(h7)),
        h5=replace(campaign.h5, diffraction_orders=tuple(h5)),
    )
    certification = certify_reference_campaign(tiny)
    assert certification.qualified is True
    row = {
        item.output_id: item for item in certification.convergence
    }["order/top/m0/n0/total_power"]
    assert row.sign_oscillation is True
    assert certification.gates.no_unexplained_oscillation is True


def test_full_spectrum_is_preserved_while_fixed_n8_remains_mandatory() -> None:
    campaign = _campaign()

    def extra(run: ReferenceRunResult) -> ReferenceRunResult:
        row = replace(
            run.diffraction_orders[0],
            m=1,
            n=1,
            normalization_identity="full-spectrum/top/m1/n1",
        )
        return replace(
            run,
            diffraction_orders=(*run.diffraction_orders, row),
        )

    extended = replace(
        campaign,
        h10=extra(campaign.h10),
        h7p5=extra(campaign.h7p5),
        h5=extra(campaign.h5),
    )
    certification = certify_reference_campaign(extended)
    assert certification.qualified is True
    assert certification.gates.fixed_order_inventory_exact is True
    assert any(
        row.output_id == "order/top/m1/n1/total_power"
        for row in certification.convergence
    )

    missing_extra = replace(
        extended,
        h5=replace(
            extended.h5,
            diffraction_orders=extended.h5.diffraction_orders[:-1],
        ),
    )
    rejected = certify_reference_campaign(missing_extra)
    assert rejected.qualified is False
    assert rejected.gates.order_metadata_exact is False
    assert rejected.gates.observable_inventory_exact is False


def test_missing_fixed_order_or_identity_drift_fails_closed() -> None:
    campaign = _campaign()
    missing_order = replace(
        campaign.h5,
        diffraction_orders=campaign.h5.diffraction_orders[:-1],
    )
    missing = certify_reference_campaign(replace(campaign, h5=missing_order))
    assert missing.qualified is False
    assert missing.gates.fixed_order_inventory_exact is False
    assert missing.gates.observable_inventory_exact is False

    changed_identity = replace(
        campaign.h7p5.identity,
        geometry_sha256="f" * 64,
    )
    drifted = certify_reference_campaign(
        replace(
            campaign,
            h7p5=replace(campaign.h7p5, identity=changed_identity),
        )
    )
    assert drifted.qualified is False
    assert drifted.gates.physical_identity_exact is False


def test_h5_controlled_stop_is_incomplete_and_cannot_qualify(
    tmp_path: Path,
) -> None:
    campaign = _campaign()
    controlled_stop = ReferenceRunResult(
        h_nm=5.0,
        identity=_identity(),
        gate=RunGateEvidence(
            completed=False,
            full_explicit_true_residual=None,
            energy_balance_error=None,
            closure_volume_error=None,
            official_postprocessing_passed=False,
            swap_peak_bytes=0,
            minimum_memory_headroom_fraction=0.22,
            controlled_resource_stop=True,
            failure_reason="factorization headroom gate",
        ),
        evidence_sha256="d" * 64,
    )
    incomplete_campaign = replace(campaign, h5=controlled_stop)
    certification = certify_reference_campaign(incomplete_campaign)
    assert certification.status == REFERENCE_CERTIFICATION_INCOMPLETE
    assert certification.qualified is False
    assert any(
        reason.endswith("_controlled_resource_stop") for reason in certification.reasons
    )

    with pytest.raises(SealedReferencePackageError):
        build_sealed_reference_package(certification)

    path = tmp_path / "hidden" / "incomplete.json"
    result = ReferenceCertifier().certify_and_seal(
        incomplete_campaign,
        path,
        seal_incomplete_evidence=True,
    )
    assert result.receipt.status == REFERENCE_CERTIFICATION_INCOMPLETE
    payload = read_sealed_reference_package(path)
    assert payload["certification"]["qualified"] is False
    assert stat.S_IMODE(path.stat().st_mode) == stat.S_IRUSR | stat.S_IWUSR


def test_sealed_package_is_strict_hash_bound_and_atomic(
    tmp_path: Path,
) -> None:
    certification = certify_reference_campaign(_campaign())
    path = tmp_path / "reference.json"
    receipt = write_sealed_reference_package(path, certification)
    payload = read_sealed_reference_package(path)
    assert payload["seal"]["sealed_payload_sha256"] == (receipt.sealed_payload_sha256)
    assert payload["campaign_binding_sha256"] == (receipt.campaign_binding_sha256)
    assert receipt.qualified is True
    assert receipt.byte_count == path.stat().st_size
    with pytest.raises(FileExistsError):
        write_sealed_reference_package(path, certification)

    unknown_key = json.loads(json.dumps(payload))
    unknown_key["reference_hint"] = 1.0
    with pytest.raises(
        SealedReferencePackageError,
        match="keys differ",
    ):
        validate_sealed_reference_package(unknown_key)

    tampered = json.loads(json.dumps(payload))
    tampered["runs"][2]["scalar_observations"][0]["value"] += 1.0e-3
    with pytest.raises(
        SealedReferencePackageError,
        match="sealed payload SHA-256 mismatch",
    ):
        validate_sealed_reference_package(tampered)


def test_published_json_schema_closes_object_boundaries() -> None:
    schema = SEALED_REFERENCE_PACKAGE_JSON_SCHEMA
    assert schema["additionalProperties"] is False
    run_schema = schema["properties"]["runs"]["items"]
    assert run_schema["additionalProperties"] is False
    assert run_schema["properties"]["gate"]["additionalProperties"] is False
    certification_schema = schema["properties"]["certification"]
    assert certification_schema["additionalProperties"] is False
    assert len(certification_schema["required"]) == len(
        certification_schema["properties"]
    )


def test_h5_headroom_and_numerical_gates_are_recomputed() -> None:
    campaign = _campaign()
    low_headroom = replace(
        campaign.h5,
        gate=replace(
            campaign.h5.gate,
            minimum_memory_headroom_fraction=math.nextafter(0.20, 0.0),
        ),
    )
    resource_failure = certify_reference_campaign(replace(campaign, h5=low_headroom))
    assert resource_failure.status == REFERENCE_CERTIFICATION_FAILED
    assert resource_failure.gates.h5_memory_headroom_passed is False

    bad_residual = replace(
        campaign.h7p5,
        gate=replace(
            campaign.h7p5.gate,
            full_explicit_true_residual=1.01e-9,
        ),
    )
    numerical_failure = certify_reference_campaign(replace(campaign, h7p5=bad_residual))
    assert numerical_failure.status == REFERENCE_CERTIFICATION_FAILED
    assert numerical_failure.gates.residual_gate_passed is False
