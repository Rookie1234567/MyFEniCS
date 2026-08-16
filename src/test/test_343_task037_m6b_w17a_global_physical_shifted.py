"""Focused pure contracts for the W17A global physical-shifted core."""

from __future__ import annotations

from copy import deepcopy

import numpy as np
import pytest

from benchmarks import run_task037_extra_m6b as runner
from src.solvers import hcurl_m6b_w16_global_shifted_inner_pc as core
from src.test.test_342_task037_m6b_w16b_outer2 import (
    _fixed40_record,
    _synthetic_summary,
)


def _w17a_summary() -> dict[str, object]:
    audits = []
    for run_index in (1, 2):
        record = deepcopy(_fixed40_record(1, run_index))
        record.update(
            {
                "run_index": run_index,
                "schema": core.W17A_INNER_SCHEMA,
                "algorithm": core.W17A_INNER_ALGORITHM,
                "auxiliary_operator": core.W17A_AUXILIARY_OPERATOR,
                "right_pc": core.W17A_AUXILIARY_PC,
                "auxiliary_dtn_used": True,
                "auxiliary_dtn_action_count": 43,
            }
        )
        audits.append(record)
    identity = {
        "finite": True,
        "dtype": "complex128",
        "shape_equal": True,
        "sha256_equal": True,
        "first_sha256": audits[0]["solution_sha256"],
        "second_sha256": audits[1]["solution_sha256"],
        "relative_difference": 0.0,
    }
    p_identity = deepcopy(identity)
    p_identity["first_sha256"] = "b" * 64
    p_identity["second_sha256"] = "b" * 64
    return {
        "schema": core.W17A_SCHEMA,
        "fixed_identity": {
            "operator": core.W17A_AUXILIARY_OPERATOR,
            "beta": 1.0,
            "right_pc": core.W17A_AUXILIARY_PC,
            "auxiliary_dtn_used": True,
            "physical_operator": core.W17A_PHYSICAL_OPERATOR,
            "projected_range_used": False,
            "b0_used": False,
            "m3y_used": False,
            "range_store_used": False,
        },
        "inner_audits": audits,
        "z_identity": identity,
        "p_identity": p_identity,
        "measurements": [
            {
                "schema": core.W17A_SCHEMA,
                "finite": True,
                "repeat_exact": True,
                "rho": 0.84,
                "normal_closure": 0.0,
                "projection_orthogonality": 0.0,
            },
            {
                "schema": core.W17A_SCHEMA,
                "finite": True,
                "repeat_exact": True,
                "rho": 0.84,
                "normal_closure": 0.0,
                "projection_orthogonality": 0.0,
            },
        ],
        "action_counts": {
            "global_auxiliary_action_count": 86,
            "local_pc_apply_count": 80,
            "local_exact_shifted_volume_action_count": 80,
            "shifted_action_count": 166,
            "auxiliary_dtn_action_count": 86,
            "physical_volume_action_count": 2,
            "physical_dtn_action_count": 2,
            "total_dtn_action_count": 88,
        },
        "architecture": {
            "fine_space": "uncondensed_fullspace",
            "auxiliary_operator": core.W17A_AUXILIARY_OPERATOR,
            "physical_operator": core.W17A_PHYSICAL_OPERATOR,
            "local_pc_callback": core.W16A_AUXILIARY_OPERATOR,
            "auxiliary_dtn_used": True,
            "global_matrix_materialized": False,
            "global_condensed_schur_materialized": False,
            "augmented_matrix_materialized": False,
            "condensation": False,
            "static_condensation": False,
            "static_condensed_operator_used": False,
            "trace_slab": False,
            "trace_slab_pc_used": False,
            "slab_factors": 0,
            "factor_store": "beta1_direct_local_patch_only",
            "physical_ksp_used": False,
            "pde_used": False,
            "official_rta": False,
        },
        "lifecycle": {
            "shared_dtn_reused": True,
            "shared_dtn_instance_count": 1,
            "auxiliary_physical_context_overlap": False,
            "release_between_inner_runs": False,
            "events": [
                "dtn_constructed",
                "auxiliary_constructed",
                "auxiliary_run_1",
                "auxiliary_run_2",
                "auxiliary_released",
                "physical_constructed",
                "physical_apply_1",
                "physical_apply_2",
                "physical_released",
                "dtn_released",
            ],
        },
        "prediction": {
            "bytes": core.W17A_PREDICTED_LIVE_SET_BYTES,
            "limit_bytes": 1_750_000_000,
            "watchdog_limit_bytes": 1_950_000_000,
            "derived_not_measured": True,
            "scratch_is_disk_not_rss": True,
            "scratch_two_run_total_bytes": core.W17A_SCRATCH_TWO_RUN_TOTAL_BYTES,
            "components": dict(core.W17A_PREDICTION_COMPONENTS),
        },
    }


def test_w17a_wrapper_relabels_shared_fixed40_only(monkeypatch: pytest.MonkeyPatch) -> None:
    old = core.W16BFixed40Result(
        solution=np.array([1.0 + 0.0j], dtype=np.complex128),
        cycle20_audit={"cycle": 20},
        cycle40_audit={"cycle": 40},
        final_relative_residual=0.0,
        audit={"schema": core.W16B_INNER_SCHEMA, "algorithm": "old"},
    )
    monkeypatch.setattr(core, "run_w16b_fixed40", lambda *args: old)
    result = core.run_w17a_fixed40(lambda value: value, lambda value: value, np.ones(1), "x")
    assert result.solution is old.solution
    assert result.cycle20_audit is old.cycle20_audit
    assert result.audit["schema"] == core.W17A_INNER_SCHEMA
    assert result.audit["auxiliary_operator"] == core.W17A_AUXILIARY_OPERATOR
    assert result.audit["auxiliary_dtn_used"] is True
    assert old.audit == {"schema": core.W16B_INNER_SCHEMA, "algorithm": "old"}


def test_w17a_evaluator_accepts_core_fixture() -> None:
    report = core.evaluate_w17a_global_physical_shifted_gate(_w17a_summary())
    assert report["pass"] is True
    assert all(type(value) is bool and value for value in report["checks"].values())


def test_w17a_residual_failure_remains_a_numeric_gate() -> None:
    summary = _w17a_summary()
    summary["inner_audits"][0]["final_relative_residual"] = 0.010001
    summary["inner_audits"][0]["cycle40_relative_residual"] = 0.010001
    report = core.evaluate_w17a_global_physical_shifted_gate(summary)
    assert report["checks"]["inner_audits"] is True
    assert report["checks"]["inner_residual"] is False
    checks = dict(report["checks"])
    checks.update(source=True, cache=True, execution=True)
    status = runner._m6b_w17a_final_status(checks, None)
    assert status[2] == "W17A_GLOBAL_PHYSICAL_SHIFTED_NUMERIC_FAIL"


@pytest.mark.parametrize(
    "tamper,check",
    [
        ("observer", "inner_audits"),
        ("auxiliary_dtn", "inner_audits"),
        ("inner_residual", "inner_residual"),
        ("dtn_count", "inner_audits"),
        ("z_identity", "z_identity"),
        ("local_pc", "architecture"),
        ("rho", "measurements"),
        ("count", "action_counts"),
        ("lifecycle_overlap", "lifecycle"),
        ("lifecycle_count", "lifecycle"),
        ("prediction", "prediction"),
    ],
)
def test_w17a_evaluator_fails_closed(tamper, check: str) -> None:
    summary = _w17a_summary()
    if tamper == "observer":
        summary["inner_audits"][0]["cycle20"]["observer_count"] = 1
    elif tamper == "auxiliary_dtn":
        summary["inner_audits"][0]["auxiliary_dtn_used"] = False
    elif tamper == "inner_residual":
        summary["inner_audits"][0]["final_relative_residual"] = 0.010001
    elif tamper == "dtn_count":
        summary["inner_audits"][0]["auxiliary_dtn_action_count"] = 42
    elif tamper == "z_identity":
        summary["z_identity"]["first_sha256"] = "bad"
    elif tamper == "local_pc":
        summary["architecture"]["local_pc_callback"] = "wrong"
    elif tamper == "rho":
        summary["measurements"][0]["rho"] = 0.850001
    elif tamper == "count":
        summary["action_counts"]["shifted_action_count"] = 165
    elif tamper == "lifecycle_overlap":
        summary["lifecycle"]["auxiliary_physical_context_overlap"] = True
    elif tamper == "lifecycle_count":
        summary["lifecycle"]["shared_dtn_instance_count"] = 2
    else:
        summary["prediction"]["components"][
            "shared_dtn_retained_and_work_bytes"
        ] = 1
    report = core.evaluate_w17a_global_physical_shifted_gate(summary)
    assert report["pass"] is False
    assert report["checks"][check] is False


def test_w16b_synthetic_contract_remains_unchanged() -> None:
    report = core.evaluate_w16b_outer2_gate(_synthetic_summary())
    assert report["pass"] is True
