from __future__ import annotations

import copy
from types import SimpleNamespace

import numpy as np
import pytest
from scipy import sparse

from src.runners.task40_v10_worker import (
    _task40_v31_reference_tier_receipt,
    _task40_v31_finalize_admission_after_resource_gate,
    _task40_v31_reference_future_reserve,
    _task40_v31_reference_only_allq_callback,
    _task40_v31_target_build_admission,
    _task40_v31_target_ready_admission,
)
from src.solvers.augmented_reference_correction import STRICT_REFERENCE_LIMITS
from src.solvers.task40_v10_p6_mumps import AllQExactMumps
from src.solvers.task40_v10_p6_yorbit import (
    Task40V10SectorContext,
    TwoCellBranchCoordinates,
)
from src.solvers.task40_v10_p6_periodic_profile import TASK40_V18_P6_B0_Y8_PROFILE


def _reference_facts() -> dict:
    estimates = {str(q): 100 + q for q in range(8)}
    reference_rows = 120
    planned_rows = reference_rows
    ksp_bytes = 500
    inverse_payload_bytes = 70
    inverse_workspace_bytes = 20
    recovery_output_bytes = 40
    selected_phase_bytes = max(
        ksp_bytes + inverse_workspace_bytes,
        recovery_output_bytes + inverse_workspace_bytes,
    )
    return {
        "q_symbolic_estimates_bytes": estimates,
        "all_q_symbolic_estimate_sum_bytes": sum(estimates.values()),
        "all_q_symbolic_q_completed": True,
        "full_storage_rows_for_future_recovery": reference_rows,
        "reference_full_storage_rows": reference_rows,
        "planned_target_full_storage_rows": planned_rows,
        "actual_target_full_storage_rows": None,
        "planned_target_rows_match_reference": False,
        "actual_target_rows_match_reference": False,
        "target_budget_status": "PLANNED_ROWS_RESERVED_ACTUAL_NOT_BUILT",
        "target_owner_increment_inventory": {
            "mesh_mpc": None,
            "local_lu": None,
            "cache": None,
            "carrier": None,
        },
        "pre_release_recovery_output_inventory": {
            "pre_release_peak_bytes": recovery_output_bytes,
            "reference_full_storage_rows": reference_rows,
            "planned_target_full_storage_rows": planned_rows,
            "actual_target_full_storage_rows": None,
            "actual_target_and_reference_full_rows_match": False,
            "actual_target_and_reference_full_rows_match_required": False,
        },
        "future_retained_krylov_and_vector_bytes": ksp_bytes,
        "future_inverse_payload_bytes": inverse_payload_bytes,
        "future_inverse_single_operation_workspace_bytes": inverse_workspace_bytes,
        "future_full_p6_pre_release_recovery_output_bytes": recovery_output_bytes,
        "selected_future_nonfactor_co_resident_peak_bytes": selected_phase_bytes,
        "future_ksp_plus_inverse_workspace_bytes": ksp_bytes + inverse_workspace_bytes,
        "future_full_output_plus_inverse_workspace_bytes": (
            recovery_output_bytes + inverse_workspace_bytes
        ),
        "future_inverse_payload_plus_selected_phase_bytes": (
            inverse_payload_bytes + selected_phase_bytes
        ),
    }


def _resource_admission(*, total: bool = True, incremental: bool = True) -> dict:
    return {
        "total_rss_inequality_passed": total,
        "incremental_headroom_inequality_passed": incremental,
    }


def _resource_sample() -> dict:
    return {"rss_bytes": 1234, "memory_envelope": {"launch_cap_bytes": 9000}}


def _future_reserve() -> dict:
    return {
        "remaining_transform_inverse_payload_bytes": 5,
        "remaining_inverse_template_count": 1,
        "future_inverse_single_operation_workspace_bytes": 7,
        "future_krylov_and_vector_bytes": 100,
        "future_full_p6_recovery_output_bytes": 80,
        "selected_nonfactor_co_resident_phase_bytes": 107,
        "future_co_resident_reserve_bytes": 112,
    }


def _owner_inventory(*, measured_only: bool = False) -> dict:
    statuses = {"mesh_mpc": "measured", "local_lu": "measured", "cache": "measured", "carrier": "measured"}
    if not measured_only:
        statuses["mesh_mpc"] = "derived"
    return {
        name: {
            "bytes": 10 + index,
            "status": statuses[name],
            "owner_id": f"target.{name}",
            "evidence": f"fixture:{name}",
        }
        for index, name in enumerate(("mesh_mpc", "local_lu", "cache", "carrier"))
    }


def _actual_owner_inventory_with_opaque_native_bytes() -> dict:
    return {
        "mesh_mpc": {
            "bytes": None,
            "status": "unknown",
            "owner_id": "target.mesh_mpc.native_backing",
            "evidence": "opaque native backing covered by process-tree/cgroup RSS gate",
        },
        "local_lu": {
            "bytes": None,
            "status": "unknown",
            "owner_id": "target.local_lu.native_backing",
            "evidence": "opaque native backing covered by process-tree/cgroup RSS gate",
        },
        "cache": {
            "bytes": 12,
            "status": "measured",
            "owner_id": "target.cache.arrays",
            "evidence": "unique NumPy backing bytes",
        },
        "carrier": {
            "bytes": 13,
            "status": "measured",
            "owner_id": "target.carrier.arrays",
            "evidence": "unique NumPy backing bytes",
        },
    }


def _admitted_reference() -> dict:
    candidate = _task40_v31_reference_only_allq_callback(
        _reference_facts(), expected_q_count=8
    )
    return _task40_v31_finalize_admission_after_resource_gate(
        candidate, _resource_admission(), _resource_sample()
    )


def test_real_reference_callback_requires_eight_q_and_keeps_target_unknown():
    candidate = _task40_v31_reference_only_allq_callback(
        _reference_facts(), expected_q_count=8
    )
    assert candidate["status"] == "REFERENCE_INVENTORY_READY"
    assert candidate["future_reserve_bytes"] == sum(
        candidate["future_reserve_components"].values()
    )
    assert candidate["actual_target_full_storage_rows"] is None
    assert set(candidate["target_owner_increment_inventory"].values()) == {None}

    with pytest.raises(ValueError, match="eight-q"):
        _task40_v31_reference_only_allq_callback(
            _reference_facts(), expected_q_count=4
        )


def test_reference_callback_gate_failure_never_emits_admitted_record():
    candidate = _task40_v31_reference_only_allq_callback(
        _reference_facts(), expected_q_count=8
    )
    with pytest.raises(ValueError, match="both resource inequalities"):
        _task40_v31_finalize_admission_after_resource_gate(
            candidate, _resource_admission(total=False), _resource_sample()
        )
    assert candidate["status"] == "REFERENCE_INVENTORY_READY"


def test_target_build_requires_all_four_owner_components_before_gate():
    reference = _admitted_reference()
    with pytest.raises(ValueError, match="UNKNOWN"):
        _task40_v31_target_build_admission(reference, None)

    candidate = _task40_v31_target_build_admission(reference, _owner_inventory())
    assert candidate["status"] == "TARGET_BUILD_INVENTORY_READY"
    assert candidate["reserved_target_owner_increment_bytes"] == 46
    with pytest.raises(ValueError, match="both resource inequalities"):
        _task40_v31_finalize_admission_after_resource_gate(
            candidate, _resource_admission(incremental=False), _resource_sample()
        )

    admitted = _task40_v31_finalize_admission_after_resource_gate(
        candidate, _resource_admission(), _resource_sample()
    )
    assert admitted["status"] == "ADMITTED_TARGET_BUILD"
    assert admitted["target_build_admitted"] is True


def test_target_ready_requires_measured_inventory_identity_and_live_gate():
    reference = _admitted_reference()
    build_candidate = _task40_v31_target_build_admission(reference, _owner_inventory())
    build_admitted = _task40_v31_finalize_admission_after_resource_gate(
        build_candidate, _resource_admission(), _resource_sample()
    )
    actual_inventory = _actual_owner_inventory_with_opaque_native_bytes()
    facts = {
        "actual_target_full_storage_rows": 120,
        "planned_target_full_storage_rows": 120,
        "mode_identity_passed": True,
        "map_identity_passed": True,
        "layout_identity_passed": True,
        "future_reserve": _future_reserve(),
    }

    row_mismatch = copy.deepcopy(facts)
    row_mismatch["actual_target_full_storage_rows"] = 119
    with pytest.raises(ValueError, match="rows do not match"):
        _task40_v31_target_ready_admission(
            reference, build_admitted, actual_inventory, row_mismatch
        )

    map_mismatch = copy.deepcopy(facts)
    map_mismatch["map_identity_passed"] = False
    with pytest.raises(ValueError, match="map_identity_passed"):
        _task40_v31_target_ready_admission(
            reference, build_admitted, actual_inventory, map_mismatch
        )

    unknown_future = copy.deepcopy(facts)
    unknown_future.pop("future_reserve")
    with pytest.raises(ValueError, match="future co-resident reserve is UNKNOWN"):
        _task40_v31_target_ready_admission(
            reference, build_admitted, actual_inventory, unknown_future
        )

    candidate = _task40_v31_target_ready_admission(
        reference, build_admitted, actual_inventory, facts
    )
    assert candidate["status"] == "TARGET_READY_INVENTORY_READY"
    with pytest.raises(ValueError, match="both resource inequalities"):
        _task40_v31_finalize_admission_after_resource_gate(
            candidate, _resource_admission(), None
        )
    admitted = _task40_v31_finalize_admission_after_resource_gate(
        candidate, _resource_admission(), _resource_sample()
    )
    assert admitted["status"] == "ADMITTED_TARGET_READY"
    assert admitted["target_ready"] is True
    assert admitted["unmeasured_target_owner_components"] == ["mesh_mpc", "local_lu"]
    assert admitted["actual_target_owner_inventory"]["mesh_mpc"]["bytes"] is None
    assert admitted["complete_target_owner_bytes"] is None


def test_zero_bytes_require_alias_evidence_and_target_actual_unknown_stays_blocked():
    reference = _admitted_reference()
    zero_inventory = _owner_inventory()
    zero_inventory["cache"]["bytes"] = 0
    with pytest.raises(ValueError, match="alias_of"):
        _task40_v31_target_build_admission(reference, zero_inventory)

    build_candidate = _task40_v31_target_build_admission(reference, _owner_inventory())
    build_admitted = _task40_v31_finalize_admission_after_resource_gate(
        build_candidate, _resource_admission(), _resource_sample()
    )
    unknown_actual = {name: None for name in ("mesh_mpc", "local_lu", "cache", "carrier")}
    with pytest.raises(ValueError, match="UNKNOWN"):
        _task40_v31_target_ready_admission(
            reference,
            build_admitted,
            unknown_actual,
            {
                "actual_target_full_storage_rows": 120,
                "planned_target_full_storage_rows": 120,
                "mode_identity_passed": True,
                "map_identity_passed": True,
                "layout_identity_passed": True,
            },
        )


def test_target_ready_future_reserve_reuses_only_still_pending_live_owners():
    class Bank:
        def future_inverse_reserve(self):
            return {
                "future_unique_inverse_payload_bytes": 40,
                "future_single_inverse_workspace_bytes": 20,
                "future_unique_inverse_template_count": 2,
            }

    class Borrower:
        def future_legacy_inverse_reserve(self):
            return {
                "future_legacy_inverse_payload_bytes": 10,
                "future_legacy_single_inverse_workspace_bytes": 15,
            }

    factors = SimpleNamespace(
        audit={
            "all_q_factors_retained_simultaneously": True,
            "all_q_numeric_factors_true_residual_passed": True,
        },
        row_counts=(100,) * 8,
        transform_bank=Bank(),
        inverse_borrowers={"global": Borrower()},
    )
    layout = SimpleNamespace(full_rows=12)
    reserve = _task40_v31_reference_future_reserve(
        {"factors": factors, "full_layout": layout}
    )
    assert reserve["remaining_transform_inverse_payload_bytes"] == 50
    assert reserve["remaining_inverse_template_count"] == 2
    assert reserve["future_inverse_single_operation_workspace_bytes"] == 20
    assert reserve["symbolic_estimate_reserve_released_into_current_rss"] is True
    assert reserve["future_co_resident_reserve_bytes"] == (
        reserve["remaining_transform_inverse_payload_bytes"]
        + reserve["selected_nonfactor_co_resident_phase_bytes"]
    )


def test_allq_reference_only_uses_reference_rows_without_promoting_target_plan(tmp_path):
    q_count = 8
    matrices = {
        q: sparse.eye(3, dtype=np.complex128, format="csr")
        for q in range(q_count)
    }
    gates = []
    factor_config = {
        "schema": "task40extra.review_v30_all_q_factor_bank.v1",
        "require_two_strict_rhs": True,
        "second_rhs_formula": (
            "real=2+(index mod 17)/17; imag=1.5+(index mod 13)/13"
        ),
        "output_directory": str(tmp_path),
    }
    with AllQExactMumps(
        matrices,
        allocation_gate=lambda name, facts: gates.append((name, dict(facts))) or {},
        expected_shapes=(3,) * q_count,
        profile=TASK40_V18_P6_B0_Y8_PROFILE,
        full_storage_rows=6,
        actual_target_full_storage_rows=None,
        planned_target_full_storage_rows=9,
        target_admission_phase="REFERENCE_ONLY",
        v30_config=factor_config,
    ) as factors:
        assert factors.audit["target_admission_phase"] == "REFERENCE_ONLY"
        assert factors.audit["all_q_numeric_factors_true_residual_passed"] is True

    facts = next(
        facts for name, facts in gates if name == "all_q_symbolic_before_any_numeric"
    )
    assert facts["reference_full_storage_rows"] == 6
    assert facts["planned_target_full_storage_rows"] == 9
    assert facts["actual_target_full_storage_rows"] is None
    assert facts["actual_target_rows_match_reference"] is False
    assert facts["full_storage_rows_for_future_recovery"] == 6
    assert facts["target_owner_increment_inventory"] == {
        "mesh_mpc": None,
        "local_lu": None,
        "cache": None,
        "carrier": None,
    }
    assert facts["pre_release_recovery_output_inventory"][
        "actual_target_and_reference_full_rows_match_required"
    ] is False


def test_v31_strict_and_v15_tiers_report_the_same_selected_state_separately():
    state_sha = "a" * 64
    metrics = {name: float(limit) * 0.5 for name, limit in STRICT_REFERENCE_LIMITS.items()}
    metrics["full_equation"] = float(STRICT_REFERENCE_LIMITS["full_equation"]) * 2.0
    frozen = {name: float(limit) * 0.5 for name, limit in STRICT_REFERENCE_LIMITS.items()}
    row = {
        "reference_pc_candidate": {"state_sha256": state_sha, "state_label": "corrected"},
        "reference_pc_metrics": metrics,
        "frozen_scale_metrics": frozen,
        "reference_pc_structural_gates": {"full_augmented_state_is_finite": True},
        "selected_state_sha256": state_sha,
        "selected_v15_raw_facts": {"state_sha256": state_sha},
        "reference_pc_admission": "V15_REFERENCE_PC_PASS",
    }

    receipt = _task40_v31_reference_tier_receipt(
        row, reference_pc_strategy="NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15"
    )

    assert receipt["strict_reference_passed"] is False
    assert receipt["v15_reference_passed"] is True
    assert receipt["strict_reference_selected_state_sha256"] == state_sha
    assert receipt["v15_reference_selected_state_sha256"] == state_sha

    row["selected_state_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="same selected FE/alpha state"):
        _task40_v31_reference_tier_receipt(
            row, reference_pc_strategy="NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15"
        )


def test_twist_local_carrier_h_is_independent_of_q_label_spacing():
    trace = {
        "trace_width": 1,
        "ny": 2,
        "R_t": sparse.eye(2, format="csr", dtype=np.complex128),
        "F_t": sparse.eye(2, format="csr", dtype=np.complex128),
    }
    for q_pair in ((0, 4), (0, 7)):
        context = Task40V10SectorContext(
            twist_index=0,
            eta=1.0 + 0.0j,
            tau=1.0 + 0.0j,
            global_q_indices=q_pair,
            local_axes={"y": (0.0, 1.0, 2.0)},
            original_mode_indices=np.asarray([0, 1], dtype=np.int64),
            local_branch_indices=np.asarray([0, 1], dtype=np.int8),
            expected_alias_counts=(1, 1),
        )
        coordinates = TwoCellBranchCoordinates(
            trace,
            trace_rows=2,
            local_modes=(object(), object()),
            local_h=np.asarray([2.0, 5.0]),
            context=context,
            allocation_gate=lambda *_args, **_kwargs: None,
        )
        np.testing.assert_allclose(
            coordinates.scale, 1.0 / np.sqrt(np.asarray([2.0, 5.0]))
        )
        assert coordinates.audit["local_carrier_H_scale_applied"] is True
