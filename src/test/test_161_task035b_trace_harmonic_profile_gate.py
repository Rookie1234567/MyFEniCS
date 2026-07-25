"""Capability-only wiring contract for the trace-harmonic research profile."""

from __future__ import annotations

from petsc4py import PETSc
import pytest

from benchmarks.run_task035b_condensed_iterative import (
    SUPPORTED_PROFILES,
    TRACE_HARMONIC_PROFILE as RUNNER_TRACE_HARMONIC_PROFILE,
    _dry_run_plan,
    _iterative_config,
    _parse_args,
)
from src.common.config_3d import target_stage4_config
from src.solvers.condensed_iterative_profiles import (
    SUPPORTED_CONDENSED_ITERATIVE_PROFILES,
    TRACE_HARMONIC_PROFILE,
    condensed_iterative_profile,
    condensed_iterative_profile_contract,
    configure_condensed_iterative_outer_ksp,
)
from src.solvers.condensed_trace_harmonic_pc import (
    trace_harmonic_block_schur_contract,
)


def test_typed_profile_preserves_prototype_and_factor_blockers() -> None:
    assert TRACE_HARMONIC_PROFILE == RUNNER_TRACE_HARMONIC_PROFILE
    assert TRACE_HARMONIC_PROFILE in SUPPORTED_CONDENSED_ITERATIVE_PROFILES
    assert TRACE_HARMONIC_PROFILE in SUPPORTED_PROFILES

    profile = condensed_iterative_profile(TRACE_HARMONIC_PROFILE)
    contract = condensed_iterative_profile_contract(TRACE_HARMONIC_PROFILE)
    prototype = trace_harmonic_block_schur_contract()

    assert profile.ksp_type == "fgmres"
    assert profile.requires_trace_harmonic_partition is True
    assert profile.production_execution_enabled is False
    assert profile.prototype_replicates_full_vectors is True
    assert contract["configured_programmatically"] is True
    assert contract["raw_petsc_options_accepted"] is False
    assert contract["ordinary_default_changed"] is False

    gate = contract["trace_harmonic_partition_gate"]
    assert gate["required"] is True
    assert (
        gate["schema_version_required"]
        == "task035b.trace-harmonic-partition.v1"
    )
    assert gate["production_partition_builder_available"] is False
    assert gate["prototype_replicates_full_vectors"] is True
    assert gate["full_vector_replication_allowed_for_formal_pde"] is False
    assert gate["production_execution_enabled"] is False
    assert gate["fail_closed_before_profile_configuration"] is True

    factors = contract["factor_semantics"]
    assert factors["local_dense_trace_block_lu_disclosed"] is True
    assert factors["small_replicated_interface_schur_lu_disclosed"] is True
    assert factors["strictly_factorless"] is False
    assert factors["complete_factor_inventory_required"] is True
    assert prototype["prototype_limitation"].startswith(
        "apply_replicates_full_vectors"
    )
    assert prototype["formal_pde_status"] == "not_run"
    assert prototype["candidate_promotion"] is False


def test_outer_ksp_configuration_fails_before_capability_can_be_mislabeled() -> None:
    profile = condensed_iterative_profile(TRACE_HARMONIC_PROFILE)
    ksp = PETSc.KSP().create(PETSc.COMM_SELF)
    try:
        with pytest.raises(
            RuntimeError,
            match="capability-only.*production trace-harmonic partition",
        ):
            configure_condensed_iterative_outer_ksp(ksp, profile)
    finally:
        ksp.destroy()


def test_dry_plan_exposes_opt_in_but_execute_pde_is_rejected(
    capsys: pytest.CaptureFixture[str],
) -> None:
    args = _parse_args(["--profile", TRACE_HARMONIC_PROFILE])
    plan = _dry_run_plan(args)
    assert plan["pde_started"] is False
    assert plan["status"] == "capability_only_production_execution_blocked"
    assert plan["selected_profile_execution_enabled"] is False
    assert plan["selected_profile"] == TRACE_HARMONIC_PROFILE
    assert plan["raw_petsc_options_accepted"] is False
    gate = plan["trace_harmonic_capability_gate"]
    assert gate["production_partition_builder_available"] is False
    assert gate["prototype_apply_replicates_full_vectors"] is True
    assert gate["execute_pde_enabled"] is False
    assert gate["formal_pde_status"] == "not_run"
    assert gate["candidate_promotion"] is False

    with pytest.raises(SystemExit):
        _parse_args(
            ["--execute-pde", "--profile", TRACE_HARMONIC_PROFILE]
        )
    assert "capability-only" in capsys.readouterr().err


def test_internal_config_defense_and_ordinary_default_are_unchanged() -> None:
    with pytest.raises(RuntimeError, match="capability-only"):
        _iterative_config(TRACE_HARMONIC_PROFILE, h_nm=15.0)
    assert (
        target_stage4_config(
            degree=6,
            h_nm=15.0,
        ).stage4_condensed_iterative_profile
        is None
    )
