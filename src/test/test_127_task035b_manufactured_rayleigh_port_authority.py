"""Independent manufactured Rayleigh-port/reference-plane authority tests."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import numpy as np
import pytest

from benchmarks.task035b_manufactured_rayleigh_port_authority import (
    EXPECTED_BRANCH,
    _production_contract_bridge,
    _verified_source_identity,
    build_manufactured_rayleigh_port_authority_record,
)
from src.common.config_3d import target_stage4_config
from src.common.modes_3d import outgoing_port_modes_3d
from src.solvers.dtn_port_3d import (
    _mode_assembly_projection_denominator,
    _mode_auxiliary_coordinate_scale,
    _mode_boundary_phase,
    _mode_projection_denominator,
    _mode_uses_boundary_referenced_auxiliary,
)
from src.solvers.manufactured_rayleigh_port_authority import (
    AUTHORITY_TOLERANCE,
    build_manufactured_rayleigh_port_physics,
    manufactured_rayleigh_mode,
    numerical_outward_power,
    numerical_rayleigh_projection,
    source_free_maxwell_identity_audit,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def _qualified_fixture_source() -> dict[str, object]:
    sha = "a" * 40
    return {
        "commit_sha": sha,
        "verified_clean_sha": sha,
        "branch": EXPECTED_BRANCH,
        "tracked_source_dirty": False,
        "stable_and_clean_before": True,
        "checks": {"fixture_source_identity": True},
    }


def _qualified_fixture_environment() -> dict[str, object]:
    return {
        "pass": True,
        "checks": {"fixture_environment": True},
    }


@pytest.fixture(scope="module")
def physics() -> dict[str, object]:
    return build_manufactured_rayleigh_port_physics()


@pytest.fixture(scope="module")
def authority_record() -> dict[str, object]:
    return build_manufactured_rayleigh_port_authority_record(
        REPO_ROOT,
        source=_qualified_fixture_source(),
        environment=_qualified_fixture_environment(),
    )


def test_manufactured_authority_proves_each_requested_convention(
    authority_record: dict[str, object],
) -> None:
    assert authority_record["pass"] is True
    assert (
        authority_record["status"]
        == "manufactured_rayleigh_port_authority_pass"
    )
    checks = authority_record["qualification"]["checks"]
    assert checks["top_bottom_outgoing_sign_proved"] is True
    assert checks["two_plane_phase_propagation_proved"] is True
    assert checks["projection_normalization_proved"] is True
    assert checks["propagating_power_invariance_proved"] is True
    assert checks["evanescent_coordinate_algebra_proved"] is True
    assert checks["production_contract_bridge_pass"] is True
    assert checks["source_free_maxwell_identities_proved"] is True
    assert checks["ordinary_default_unchanged"] is True
    assert checks["pde_not_run"] is True
    assert authority_record["pde"]["status"] == "not_run"
    assert (
        authority_record["decision"]["ordinary_default_changed"]
        is False
    )


def test_top_bottom_s_p_outgoing_sign_phase_projection_and_power(
    physics: dict[str, object],
) -> None:
    cases = physics["propagating_cases"]
    assert {
        (case["side"], case["polarization"])
        for case in cases
    } == {
        ("top", "s"),
        ("top", "p"),
        ("bottom", "s"),
        ("bottom", "p"),
    }
    assert all(case["pass"] for case in cases)
    assert all(
        case["outgoing_power_at_planes"][0] > 0.0
        and case["incoming_power_at_plane_1"] < 0.0
        for case in cases
    )
    assert max(
        error
        for case in cases
        for error in case["errors"].values()
    ) <= AUTHORITY_TOLERANCE
    assert all(
        case["source_free_maxwell_identities"]["pass"]
        for case in cases
    )


def test_evanescent_global_and_boundary_coordinates_are_equivalent(
    physics: dict[str, object],
) -> None:
    cases = physics["evanescent_cases"]
    assert {case["side"] for case in cases} == {"top", "bottom"}
    assert all(case["pass"] for case in cases)
    assert all(
        0.0 < case["abs_coordinate_scale"] < 1.0
        for case in cases
    )
    assert all(
        abs(case["outward_real_power"]) <= AUTHORITY_TOLERANCE
        for case in cases
    )
    assert all(
        case["source_free_maxwell_identities"]["pass"]
        for case in cases
    )


def test_source_free_maxwell_identities_fail_on_wrong_dispersion() -> None:
    inconsistent = manufactured_rayleigh_mode(
        side="top",
        direction="outgoing",
        polarization="s",
        alpha=0.1,
        gamma=0.2,
        beta=0.35,
        k0=0.5,
    )
    audit = source_free_maxwell_identity_audit(inconsistent)

    assert audit["pass"] is False
    assert audit["checks"]["dispersion_identity"] is False
    assert (
        audit["checks"][
            "ampere_identity_k_cross_h_eq_minus_k0_epsilon_e"
        ]
        is False
    )
    assert audit["checks"]["electric_transversality"] is True
    assert audit["checks"]["magnetic_transversality"] is True
    assert (
        audit["checks"]["faraday_identity_k_cross_e_eq_k0_mu_h"]
        is True
    )


def test_production_contract_bridge_matches_independent_formulas() -> None:
    bridge = _production_contract_bridge()

    assert bridge["pass"] is True
    assert bridge["default_mode_count"] == 80
    assert bridge["buffer1_mode_count"] == 340
    assert bridge["buffer1_scaled_evanescent_mode_count"] == 260
    assert (
        bridge["default_mode_identity_sha256"]
        == "f039dd14264f7bc2987e75e311ef338682388b1f17a4ea194702ff888f4c7a21"
    )
    assert (
        bridge["buffer1_mode_identity_sha256"]
        == "74f785341325c2f88a6512747bb4cf0d2cad1d8b8dc66fd0c7e2a63ee758f629"
    )
    assert bridge["maximum_formula_relative_error"] <= AUTHORITY_TOLERANCE
    assert (
        bridge["maximum_production_mode_physics_relative_error"]
        <= AUTHORITY_TOLERANCE
    )
    assert bridge["checks"][
        "buffer1_top_bottom_sign_kz_and_power_magnitude_verified"
    ]
    assert all(bridge["checks"].values())


def test_projection_fails_closed_on_degenerate_plane() -> None:
    mode = manufactured_rayleigh_mode(
        side="top",
        direction="outgoing",
        polarization="s",
        alpha=0.1,
        gamma=0.2,
        beta=0.3,
        k0=0.5,
    )
    with pytest.raises(ValueError, match="plane lengths"):
        numerical_rayleigh_projection(
            mode,
            global_amplitude=1.0 + 0.0j,
            z=0.0,
            lx=0.0,
            ly=1.0,
            reference_z=None,
        )


def test_incoming_mode_has_negative_outward_flux_on_both_sides() -> None:
    for side in ("top", "bottom"):
        mode = manufactured_rayleigh_mode(
            side=side,
            direction="incoming",
            polarization="s",
            alpha=0.1,
            gamma=0.05,
            beta=0.4,
            k0=0.5,
        )
        assert numerical_outward_power(
            mode,
            global_amplitude=0.4 - 0.2j,
            z=0.0,
            lx=2.0,
            ly=3.0,
        ) < 0.0


def test_authority_record_fails_closed_on_unqualified_source() -> None:
    source = _qualified_fixture_source()
    source["branch"] = "wrong"
    record = build_manufactured_rayleigh_port_authority_record(
        REPO_ROOT,
        source=source,
        environment=_qualified_fixture_environment(),
    )
    assert record["pass"] is False
    assert (
        record["qualification"]["checks"][
            "clean_source_identity_hash_bound"
        ]
        is False
    )


def test_authority_record_fails_closed_on_failed_physics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from benchmarks import (
        task035b_manufactured_rayleigh_port_authority as builder,
    )

    failed = deepcopy(build_manufactured_rayleigh_port_physics())
    failed["pass"] = False
    monkeypatch.setattr(
        builder,
        "build_manufactured_rayleigh_port_physics",
        lambda: failed,
    )
    record = builder.build_manufactured_rayleigh_port_authority_record(
        REPO_ROOT,
        source=_qualified_fixture_source(),
        environment=_qualified_fixture_environment(),
    )
    assert record["pass"] is False
    assert (
        record["qualification"]["checks"][
            "independent_manufactured_physics_pass"
        ]
        is False
    )


def test_cli_source_gate_fails_closed_while_worktree_is_dirty() -> None:
    with pytest.raises(SystemExit, match="source gate failed"):
        _verified_source_identity(REPO_ROOT, "0" * 40)


def test_production_evanescent_scaling_matches_independent_algebra() -> None:
    config = target_stage4_config(degree=6, h_nm=15.0)
    config.stage4_dtn_evanescent_buffer = 1
    modes = outgoing_port_modes_3d(config)
    selected = [
        mode
        for mode in modes
        if _mode_uses_boundary_referenced_auxiliary(mode, config)
    ]
    assert selected
    for side in ("top", "bottom"):
        mode = min(
            (item for item in selected if item.side == side),
            key=lambda item: abs(_mode_boundary_phase(item, config)),
        )
        scale = _mode_auxiliary_coordinate_scale(mode, config)
        expected = np.exp(
            1j
            * mode.k_vector[2]
            * (
                config.physical_z_max
                if side == "top"
                else config.physical_z_min
            )
        )
        assert scale == pytest.approx(
            expected,
            rel=2.0e-15,
            abs=0.0,
        )
        assert _mode_projection_denominator(
            mode,
            config,
        ) == pytest.approx(
            abs(scale) ** 2
            * _mode_assembly_projection_denominator(mode, config),
            rel=2.0e-15,
            abs=0.0,
        )


def test_authority_record_is_json_serializable(
    authority_record: dict[str, object],
) -> None:
    encoded = json.dumps(authority_record, ensure_ascii=False)
    assert "manufactured_rayleigh_port_authority_pass" in encoded
