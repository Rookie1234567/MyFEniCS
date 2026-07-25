"""Production/profile wiring for canonical orientation-class reuse."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import tempfile
from unittest.mock import patch

import pytest

from benchmarks.run_task035b_direct_setup_profile import (
    _classify_profile,
    _direct_config,
    _dry_run_plan,
    _extract_setup_evidence,
    _parse_args,
)
from src.common.config_3d import SimulationConfig3D
from src.solvers.dtn_port_3d import (
    _build_assembly_time_condensation_with_request,
    _canonical_orientation_class_reuse_request_audit,
)


def _profile_config(*, enabled: bool) -> SimulationConfig3D:
    with tempfile.TemporaryDirectory() as directory:
        return _direct_config(
            source_sha="a" * 40,
            cache_directory=Path(directory) / "cache",
            cache_state="warm",
            h_nm=15.0,
            canonical_orientation_class_reuse=enabled,
        )


def test_ordinary_config_and_profile_cli_default_remain_off() -> None:
    ordinary = SimulationConfig3D()
    assert ordinary.stage4_canonical_orientation_class_reuse is False
    assert (
        ordinary.as_jsonable()[
            "stage4_canonical_orientation_class_reuse"
        ]
        is False
    )

    args = _parse_args([])
    plan = _dry_run_plan(args)
    assert args.canonical_orientation_class_reuse is False
    assert (
        plan["explicit_opt_ins"]["canonical_orientation_class_reuse"]
        is False
    )
    assert (
        _profile_config(
            enabled=False
        ).stage4_canonical_orientation_class_reuse
        is False
    )
    ordinary_audit = _canonical_orientation_class_reuse_request_audit(
        ordinary
    )
    assert ordinary_audit["requested"] is False
    assert ordinary_audit["eligible"] is False
    assert ordinary_audit["accepted"] is False
    assert (
        "assembly_time_cell_static_condensation_required"
        in ordinary_audit["rejection_reasons"]
    )


def test_explicit_profile_request_is_eligible_and_reaches_core_keyword() -> None:
    args = _parse_args(["--canonical-orientation-class-reuse"])
    plan = _dry_run_plan(args)
    assert args.canonical_orientation_class_reuse is True
    assert (
        plan["explicit_opt_ins"]["canonical_orientation_class_reuse"]
        is True
    )

    cfg = _profile_config(enabled=True)
    audit = _canonical_orientation_class_reuse_request_audit(cfg)
    assert audit == {
        "schema_version": (
            "task035b.canonical-orientation-reuse-request.v1"
        ),
        "requested": True,
        "eligible": True,
        "accepted": True,
        "rejection_reasons": [],
        "required_path": (
            "assembly_time_fixed_trace_strictly_higher_interior"
        ),
        "regionwise_p_supported": False,
        "ordinary_default_changed": False,
    }

    sentinel = object()
    with patch(
        "src.solvers.dtn_port_3d."
        "build_unconstrained_assembly_time_condensation",
        return_value=sentinel,
    ) as core:
        result = _build_assembly_time_condensation_with_request(
            object(),
            object(),
            object(),
            canonical_orientation_request_audit=audit,
            defer_final_assembly=True,
        )
    assert result is sentinel
    assert core.call_args.kwargs[
        "canonical_orientation_class_reuse"
    ] is True
    assert core.call_args.kwargs["defer_final_assembly"] is True


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        (
            {"stage4_assembly_time_cell_static_condensation": False},
            "assembly_time_cell_static_condensation_required",
        ),
        (
            {
                "nedelec_trace_degree": 6,
                "nedelec_interior_degree": 6,
            },
            "fixed_trace_with_strictly_higher_interior_degree_required",
        ),
        (
            {"stage4_regionwise_interior_p": True},
            "regionwise_p_conflict",
        ),
        (
            {
                "stage4_dtn_order_policy": "zero_order",
                "incident_theta_deg": 0.0,
            },
            "zero_order_local_robin_path_unsupported",
        ),
    ],
)
def test_ineligible_explicit_combinations_fail_closed(
    updates: dict[str, object],
    reason: str,
) -> None:
    cfg = replace(_profile_config(enabled=True), **updates)
    with pytest.raises(ValueError, match=reason):
        _canonical_orientation_class_reuse_request_audit(cfg)


def test_profile_evidence_preserves_request_and_core_coverage() -> None:
    request = _canonical_orientation_class_reuse_request_audit(
        _profile_config(enabled=True)
    )
    core = {
        "schema_version": (
            "task035b.canonical-orientation-condensation.v1"
        ),
        "enabled": True,
        "ordinary_default_changed": False,
        "canonical_class_construction_count_sum": 6,
        "oriented_class_derived_count_sum": 115,
        "aii_factorizations_avoided_sum": 109,
        "used_cell_permutations": [0, 1, 2],
        "qualified_cell_permutations": [0, 1, 2],
        "trace_interior_block_diagonal_proven_for_every_used_permutation": (
            True
        ),
        "used_set_equals_qualified_set": True,
        "inactive_or_postzero_rows_created": False,
    }
    evidence = _extract_setup_evidence(
        {
            "status": "worker_completed_with_summary",
            "rank_failures": [],
            "summary": {
                "config": {
                    "stage4_canonical_orientation_class_reuse": True,
                },
                "cell_static_condensation": {
                    "canonical_orientation_class_reuse": core,
                },
                "stage4_canonical_orientation_class_reuse_request": (
                    request
                ),
            },
        }
    )
    assert (
        evidence["configuration_identity"][
            "canonical_orientation_class_reuse"
        ]
        is True
    )
    assert evidence["canonical_orientation_class_reuse"] == {
        "request": request,
        "core": core,
    }

    classified = _classify_profile(
        evidence,
        {},
        cache_state="warm",
        source_sha="a" * 40,
        expected_mpi_size=8,
        return_code=0,
        terminated_for_memory=False,
        terminated_for_timeout=False,
        telemetry_readable=True,
        source_stable_and_clean_after=True,
        expected_canonical_orientation_class_reuse=True,
    )
    assert (
        classified["checks"][
            "canonical_orientation_request_identity"
        ]
        is True
    )
    assert (
        classified["checks"][
            "canonical_orientation_request_provenance"
        ]
        is True
    )
    assert (
        classified["checks"]["canonical_orientation_core_audit"]
        is True
    )

    core[
        "trace_interior_block_diagonal_proven_for_every_used_permutation"
    ] = False
    rejected = _classify_profile(
        evidence,
        {},
        cache_state="warm",
        source_sha="a" * 40,
        expected_mpi_size=8,
        return_code=0,
        terminated_for_memory=False,
        terminated_for_timeout=False,
        telemetry_readable=True,
        source_stable_and_clean_after=True,
        expected_canonical_orientation_class_reuse=True,
    )
    assert (
        rejected["checks"]["canonical_orientation_core_audit"]
        is False
    )
