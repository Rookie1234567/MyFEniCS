import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.runners.physical_diagnosis_worker import save_packet
from src.runners.task40_v10_worker import _save_packet
from src.runners.task40_v10_output_checker import (
    main as output_checker_main,
    verify_v10_dtn_port_mode_table,
    verify_v10_output_bundle,
    verify_v10_regular_internal_witness,
    verify_v15_pc_state_packet,
)
from src.solvers.augmented_reference_correction import (
    NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
    augmented_state_sha256,
    select_v15_reference_pc_candidate,
    stable_euclidean_norm,
)


@pytest.mark.parametrize(
    ("expected_channel_count", "modes_per_side"),
    ((532, 266), (340, 170), (588, 294)),
)
def test_v10_output_checker_reopens_field_identity_and_recomputes_residual(
    tmp_path, expected_channel_count, modes_per_side
):
    field_path = tmp_path / "field.vtu"
    field_path.write_bytes(b"tiny field fixture")
    import hashlib

    file_digest = hashlib.sha256(field_path.read_bytes()).hexdigest()
    port_table_path = tmp_path / "dtn_port_diffraction_orders_3d.csv"
    with port_table_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=("side", "m", "n", "polarization")
        )
        writer.writeheader()
        for side in ("top", "bottom"):
            for mode_index in range(modes_per_side):
                writer.writerow(
                    {
                        "side": side,
                        "m": mode_index,
                        "n": 0,
                        "polarization": "s",
                    }
                )
    port_table_digest = hashlib.sha256(port_table_path.read_bytes()).hexdigest()
    rhs = np.array([3 + 0j, 4 + 0j], dtype=np.complex128)
    applied = np.array([1 + 0j, 0 + 0j], dtype=np.complex128)
    residual = rhs - applied
    relative = float(np.linalg.norm(residual) / np.linalg.norm(rhs))
    save_packet(
        tmp_path,
        "residual",
        {
            "relative_residual": relative,
            "native_witness_relative_residual": relative,
            "limit": 1.0,
            "full_physical_rhs_storage": rhs,
            "full_solution_storage": np.array([0.5 + 0j, 0.25 + 0j]),
            "target_backend_applied_storage": applied,
            "target_backend_residual_storage": residual,
            "native_witness_applied_storage": applied,
            "native_witness_residual_storage": residual,
        },
    )
    save_packet(
        tmp_path,
        "output",
        {
            "scientific_identity": {
                "full_solution_packet_json": str(tmp_path / "residual.json"),
                "full_solution_storage_sha256": "a" * 64,
                "ordered_physical_mode_sha256": "b" * 64,
                "field_mode_and_diffraction_files": [
                    {
                        "path": str(field_path),
                        "size_bytes": field_path.stat().st_size,
                        "sha256": file_digest,
                    },
                    {
                        "path": str(port_table_path),
                        "size_bytes": port_table_path.stat().st_size,
                        "sha256": port_table_digest,
                    },
                ],
            }
        },
    )
    result = verify_v10_output_bundle(
        tmp_path / "output.json", expected_channel_count=expected_channel_count
    )
    residual_record = json.loads((tmp_path / "residual.json").read_text())
    output_record = json.loads((tmp_path / "output.json").read_text())
    assert result["status"] == "PASS"
    assert result["v17_row_tile_assembly"] is None
    assert result["v17_row_tile_allocation_admission_ledger"] is None
    assert result["v17_dispatch_binding"] is None
    assert all(row["passed"] for row in result["residual_checks"])
    assert result["field_mode_and_diffraction_file_checks"][0]["passed"]
    assert result["full_dtn_port_mode_table_check"]["actual_channel_count"] == (
        expected_channel_count
    )
    assert result["full_dtn_port_mode_table_check"]["channel_count_by_side"] == {
        "top": modes_per_side,
        "bottom": modes_per_side,
    }
    assert residual_record["arrays"]["sha256"]
    assert output_record["scientific_identity"]["full_solution_storage_sha256"] == "a" * 64
    if expected_channel_count == 340:
        with pytest.raises(ValueError, match="full top/bottom DtN port mode table"):
            verify_v10_output_bundle(tmp_path / "output.json", expected_channel_count=532)


def test_v10_dtn_port_mode_table_requires_paired_top_and_bottom_rows(tmp_path):
    table = tmp_path / "dtn_port_modes.csv"

    def write_rows(rows):
        with table.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream, fieldnames=("side", "m", "n", "polarization")
            )
            writer.writeheader()
            writer.writerows(rows)

    paired_rows = [
        {"side": side, "m": mode, "n": 0, "polarization": "s"}
        for side in ("top", "bottom")
        for mode in (0, 1)
    ]
    write_rows(paired_rows)
    result = verify_v10_dtn_port_mode_table(table, expected_channel_count=4)
    assert result["passed"]
    assert result["paired_top_bottom_mode_count"] == 2

    write_rows([row for row in paired_rows if row["side"] == "top"])
    incomplete = verify_v10_dtn_port_mode_table(table, expected_channel_count=4)
    assert not incomplete["passed"]
    assert incomplete["channel_count_by_side"] == {"top": 2, "bottom": 0}


def test_nested_checkpoint_packet_creates_parent_and_roundtrips(tmp_path):
    runtime = SimpleNamespace(directory=tmp_path, markers=[])
    runtime.marker = lambda name, facts: runtime.markers.append((name, facts))
    runtime.reserve_workspace = lambda *_args: None
    runtime.release_workspace = lambda *_args: None
    vector = np.array([1 + 0j, 2 + 3j], dtype=np.complex128)
    packet = _save_packet(
        runtime,
        "checkpoints/v10_candidate_p6_x_0000_0001",
        {"solution_storage": vector},
    )
    assert (tmp_path / "checkpoints/v10_candidate_p6_x_0000_0001.json").is_file()
    with np.load(packet["arrays"]["path"], allow_pickle=False) as arrays:
        np.testing.assert_array_equal(arrays["array_0"], vector)
    assert any(name == "v10_raw_disk_admission" for name, _facts in runtime.markers)


def _regular_internal_payload(
    *,
    limit=1.0e-11,
    action_offset=1.0e-12 + 1.0e-12j,
    residual_override=None,
    operation_scale=None,
    stored_relative=None,
    count=36_000,
    profile_identity=None,
    mode_count=None,
    q_port_counts=None,
):
    effective_rhs = np.ones(count, dtype=np.complex128)
    saved_action = effective_rhs - action_offset
    residual = effective_rhs - saved_action
    if operation_scale is None:
        operation_scale = 2.0 * float(np.linalg.norm(effective_rhs))
    if stored_relative is None:
        stored_relative = float(np.linalg.norm(residual) / operation_scale)
    payload = {
        "full_internal_effective_rhs": effective_rhs,
        "full_internal_saved_field_action": saved_action,
        "full_internal_recovery_residuals": (
            residual if residual_override is None else residual_override
        ),
        "full_internal_original_rows": np.tile(np.arange(count // 2, dtype=np.int64), 2),
        "full_internal_twist_indices": np.repeat(np.array([0, 1], dtype=np.int8), count // 2),
        "full_internal_recovery_rows": count,
        "full_internal_recovery_operation_scale": operation_scale,
        "limits": {"full_internal_recovery": limit},
        "full_internal_recovery_relative": stored_relative,
    }
    if profile_identity is not None:
        q_counts = tuple(q_port_counts)
        payload.update(
            profile_identity=profile_identity,
            expected_port_mode_count=mode_count,
            q_true_residuals=[
                {
                    "q": q,
                    "rhs_norm": 1.0,
                    "true_residual_norm": 0.0,
                    "true_residual_relative": 0.0,
                }
                for q in range(4)
            ],
            local_recovery_facts=[
                {
                    "twist_index": 0,
                    "global_q_indices": [0, 2],
                    "internal_row_count": count // 2,
                    "port_mode_count": q_counts[0] + q_counts[2],
                },
                {
                    "twist_index": 1,
                    "global_q_indices": [1, 3],
                    "internal_row_count": count // 2,
                    "port_mode_count": q_counts[1] + q_counts[3],
                },
            ],
        )
    return payload


def test_regular_internal_checker_recomputes_residual_from_raw_arrays(tmp_path):
    payload = _regular_internal_payload()
    save_packet(tmp_path, "regular_internal", payload)
    packet = json.loads((tmp_path / "regular_internal.json").read_text())

    result = verify_v10_regular_internal_witness(tmp_path / "regular_internal.json")

    assert result["passed"]
    assert result["internal_row_count"] == 36_000
    assert result["residual_algebra_defect_relative"] == 0.0
    assert result["packet_npz_sha256"] == packet["arrays"]["sha256"]


def test_regular_internal_checker_rejects_forged_saved_residual(tmp_path):
    count = 36_000
    payload = _regular_internal_payload(
        action_offset=1.0e-4,
        residual_override=np.zeros(count, dtype=np.complex128),
        operation_scale=1.0e16,
        stored_relative=0.0,
    )
    save_packet(tmp_path, "forged_regular_internal", payload)

    with pytest.raises(ValueError, match="failed raw-array recomputation"):
        verify_v10_regular_internal_witness(tmp_path / "forged_regular_internal.json")


def test_regular_internal_checker_rejects_relaxed_limit(tmp_path):
    save_packet(
        tmp_path,
        "relaxed_regular_internal",
        _regular_internal_payload(limit=1.0e-6),
    )

    with pytest.raises(ValueError, match="fixed 1e-11 contract"):
        verify_v10_regular_internal_witness(tmp_path / "relaxed_regular_internal.json")


def test_regular_internal_checker_rejects_missing_recorded_limit(tmp_path):
    payload = _regular_internal_payload()
    payload["limits"].clear()
    save_packet(tmp_path, "missing_regular_internal_limit", payload)

    with pytest.raises(ValueError, match="missing limits.full_internal_recovery"):
        verify_v10_regular_internal_witness(tmp_path / "missing_regular_internal_limit.json")


def test_regular_internal_checker_rejects_conflicting_duplicate_limit(tmp_path):
    payload = _regular_internal_payload()
    payload["full_internal_recovery_limit"] = 1.0e-12
    save_packet(tmp_path, "conflicting_regular_internal_limit", payload)

    with pytest.raises(ValueError, match="limit fields conflict"):
        verify_v10_regular_internal_witness(
            tmp_path / "conflicting_regular_internal_limit.json"
        )


@pytest.mark.parametrize(
    ("profile_identity", "count", "mode_count", "q_counts"),
    (
        ("task40extra_v15_p6_y_orbit_gx560_reference_v1", 252_000, 340, (68, 68, 136, 68)),
        ("task40extra_v15_p6_y_orbit_e1_reference_v1", 342_000, 588, (84, 168, 168, 168)),
    ),
)
def test_v15_regular_internal_checker_uses_registered_profile_rows_and_modes(
    tmp_path, profile_identity, count, mode_count, q_counts
):
    payload = _regular_internal_payload(
        action_offset=0.0,
        operation_scale=1.0,
        stored_relative=0.0,
        count=count,
        profile_identity=profile_identity,
        mode_count=mode_count,
        q_port_counts=q_counts,
    )
    save_packet(tmp_path, "v15_regular_internal", payload)

    result = verify_v10_regular_internal_witness(tmp_path / "v15_regular_internal.json")

    assert result["passed"] is True
    assert result["profile_identity"] == profile_identity
    assert result["internal_row_count"] == count
    assert result["expected_port_mode_count"] == mode_count


def _v15_pc_packet_payload(
    *, bad_state_hash=False, short_rhs=False, tiny_residual=False,
    bad_decomposition=False, bad_lifted_norm=False,
    profile_identity="task40extra_v15_p6_y_orbit_b0_reference_v1",
):
    from src.solvers.task40_v10_p6_periodic_profile import TASK40_P6_PERIODIC_PROFILES

    profile = TASK40_P6_PERIODIC_PROFILES[profile_identity]
    independent_rows = profile.global_independent_rows
    mode_count = profile.mode_count
    q_count = profile.q_count
    twist_count = profile.replication_count
    fe_state = np.zeros(independent_rows, dtype=np.complex128)
    alpha = np.zeros(mode_count, dtype=np.complex128)
    fe_rhs = np.zeros(independent_rows, dtype=np.complex128)
    fe_rhs[0] = 1.0 + 0.0j
    port_elimination_action = np.zeros(independent_rows, dtype=np.complex128)
    effective_rhs = fe_rhs.copy()
    lifted_rhs = [np.zeros(independent_rows, dtype=np.complex128) for _ in range(twist_count)]
    lifted_actions = [np.zeros(independent_rows, dtype=np.complex128) for _ in range(twist_count)]
    lifted_rhs[0] = effective_rhs.copy()
    lifted_actions[0] = effective_rhs.copy()
    if tiny_residual:
        lifted_actions[0][0] -= 1.0e-12
    lifted_errors = [rhs - action for rhs, action in zip(lifted_rhs, lifted_actions, strict=True)]
    sum_lifted_rhs = np.sum(lifted_rhs, axis=0)
    sum_lifted_actions = np.sum(lifted_actions, axis=0)
    global_action = sum_lifted_actions.copy()
    d_b = effective_rhs - sum_lifted_rhs
    d_a = sum_lifted_actions - global_action
    if tiny_residual:
        d_b[0] += 1.0e-16
        d_a[0] -= 1.0e-16
    b_delta = np.zeros(independent_rows, dtype=np.complex128)
    eliminated_direct = effective_rhs - global_action
    eliminated_decomposed = d_b + np.sum(lifted_errors, axis=0) + d_a
    complete_decomposed = eliminated_decomposed - b_delta
    complete_fe = complete_decomposed.copy()
    alpha_closure = np.zeros(mode_count, dtype=np.complex128)
    lifted_error_norms = [stable_euclidean_norm(value) for value in lifted_errors]
    if bad_lifted_norm:
        lifted_error_norms[0] += 1.0
    budget_norms = {
        "d_b": stable_euclidean_norm(d_b),
        "lifted_sector_errors": lifted_error_norms,
        "d_A": stable_euclidean_norm(d_a),
        "B_delta_alpha": stable_euclidean_norm(b_delta),
    }
    scale = stable_euclidean_norm(fe_rhs) + stable_euclidean_norm(port_elimination_action)
    budget_relative = (
        sum(lifted_error_norms)
        + budget_norms["d_b"]
        + budget_norms["d_A"]
        + budget_norms["B_delta_alpha"]
    ) / scale
    closure_scale = (
        stable_euclidean_norm(effective_rhs)
        + stable_euclidean_norm(global_action)
        + sum(stable_euclidean_norm(value) for value in lifted_rhs)
        + sum(stable_euclidean_norm(value) for value in lifted_actions)
        + stable_euclidean_norm(complete_fe)
        + stable_euclidean_norm(b_delta)
        + stable_euclidean_norm(fe_rhs)
        + stable_euclidean_norm(port_elimination_action)
    )
    closure_norm = max(
        stable_euclidean_norm(eliminated_direct - eliminated_decomposed),
        stable_euclidean_norm(complete_fe - complete_decomposed),
        stable_euclidean_norm(effective_rhs - (fe_rhs - port_elimination_action)),
    )
    if bad_decomposition:
        eliminated_decomposed[0] += 1.0
    eliminated_norm = stable_euclidean_norm(eliminated_direct)
    complete_norm = stable_euclidean_norm(complete_fe)
    state_hash = augmented_state_sha256(fe_state, alpha)
    if bad_state_hash:
        state_hash = "0" * 64
    mode_ids_by_twist = []
    next_mode = 0
    for count in profile.sector_port_counts:
        mode_ids_by_twist.append(list(range(next_mode, next_mode + count)))
        next_mode += count
    raw_facts = {
        "profile_identity": profile_identity,
        "effective_rhs_scale": scale,
        "eliminated_fe_residual_norm": eliminated_norm,
        "complete_augmented_fe_residual_norm": complete_norm,
        "budget_term_norms": budget_norms,
        "alpha_closure_residual_norm": 0.0,
        "alpha_closure_original_scale": 1.0,
        "alpha_closure_frozen_scale": 1.0,
        "q_true_residuals": [
            {
                "q": q,
                "rhs_norm": 1.0,
                "true_residual_norm": 0.0,
                "true_residual_relative": 0.0,
            }
            for q in range(q_count)
        ],
        "retained_mode_count": mode_count,
        "native_sector_facts": [
            {"twist_index": twist, "mode_indices": mode_ids_by_twist[twist]}
            for twist in range(twist_count)
        ],
        "decomposition_closure_norm": closure_norm,
        "decomposition_closure_scale": closure_scale,
        "state_sha256": state_hash,
    }
    candidate = {
        "metrics": {
            "eliminated_fe": eliminated_norm / scale,
            "complete_augmented_fe": complete_norm / scale,
            "noncancelling_budget": budget_relative,
            "alpha_closure": 0.0,
            "q_solve": 0.0,
        },
        "frozen_scale_metrics": {
            "eliminated_fe": eliminated_norm / scale,
            "complete_augmented_fe": complete_norm / scale,
            "noncancelling_budget": budget_relative,
            "alpha_closure": 0.0,
        },
        "structural_gates": {
            "startup_regular_inverse_gates_passed": True,
            "all_q_phases_covered": True,
            "all_retained_modes_mapped_once": True,
            "native_decomposition_closure": True,
            "native_augmented_actions_finite": True,
        },
        "state_label": "initial",
        "state_sha256": state_hash,
        "raw_facts": raw_facts,
    }
    selection = select_v15_reference_pc_candidate([candidate])
    payload = {
        "schema": "task40extra.review_v15_p6_pc_state_evidence.v1",
        "reference_pc_strategy": NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
        "profile": profile_identity,
        "profile_identity": profile_identity,
        "status": "PASS",
        "failure": None,
        "candidate_selection": selection,
        "candidate_facts": [
            {
                "evaluation_available": True,
                "metrics": candidate["metrics"],
                "frozen_scale_metrics": candidate["frozen_scale_metrics"],
                "raw_facts": raw_facts,
                "structural_gates": candidate["structural_gates"],
                "state_sha256": state_hash,
            }
        ],
        "fe_rhs": fe_rhs[:-int(short_rhs)] if short_rhs else fe_rhs,
        "port_rhs": np.zeros(mode_count, dtype=np.complex128),
        "candidate_0_finite_element_state": fe_state,
        "candidate_0_port_amplitudes": alpha,
        "candidate_0_effective_rhs": effective_rhs,
        "candidate_0_port_elimination_action": port_elimination_action,
        "candidate_0_sum_lifted_effective_rhs": sum_lifted_rhs,
        "candidate_0_sum_lifted_native_actions": sum_lifted_actions,
        "candidate_0_global_native_action_independent": global_action,
        "candidate_0_d_b": d_b,
        "candidate_0_d_A": d_a,
        "candidate_0_modal_alpha_defect_action": b_delta,
        "candidate_0_eliminated_fe_residual_direct": eliminated_direct,
        "candidate_0_eliminated_fe_residual_decomposed": eliminated_decomposed,
        "candidate_0_complete_fe_residual_decomposed": complete_decomposed,
        "candidate_0_complete_augmented_fe_residual": complete_fe,
        "candidate_0_complete_augmented_port_residual": np.zeros(mode_count, dtype=np.complex128),
        "candidate_0_alpha_closure_residual": alpha_closure,
    }
    for twist in range(twist_count):
        payload[f"candidate_0_lifted_sector_error_{twist}"] = lifted_errors[twist]
        payload[f"candidate_0_lifted_sector_effective_rhs_{twist}"] = lifted_rhs[twist]
        payload[f"candidate_0_lifted_sector_native_action_{twist}"] = lifted_actions[twist]
    return payload

def test_v15_pc_packet_checker_recomputes_hash_budget_and_selector(tmp_path):
    save_packet(tmp_path, "v15_pc", _v15_pc_packet_payload())

    result = verify_v15_pc_state_packet(tmp_path / "v15_pc.json")

    assert result["passed"] is True
    assert result["numerically_admitted"] is True
    assert result["profile_identity"] == "task40extra_v15_p6_y_orbit_b0_reference_v1"


def test_v18_ny8_pc_packet_checker_recomputes_all_q_and_twist_actions(tmp_path):
    save_packet(
        tmp_path,
        "v18_ny8_pc",
        _v15_pc_packet_payload(
            profile_identity="task40extra_v18_p6_y_orbit_b0_y8_reference_v1"
        ),
    )

    result = verify_v15_pc_state_packet(tmp_path / "v18_ny8_pc.json")

    assert result["passed"] is True
    assert result["numerically_admitted"] is True
    assert result["profile_identity"] == "task40extra_v18_p6_y_orbit_b0_y8_reference_v1"


def test_v15_packet_checker_uses_outer_ny4_identity_for_legacy_raw_facts(tmp_path):
    payload = _v15_pc_packet_payload()
    payload["candidate_facts"][0]["raw_facts"].pop("profile_identity")
    save_packet(tmp_path, "v15_pc_legacy_raw", payload)

    result = verify_v15_pc_state_packet(tmp_path / "v15_pc_legacy_raw.json")

    assert result["passed"] is True
    assert result["profile_identity"] == "task40extra_v15_p6_y_orbit_b0_reference_v1"


def test_v18_ny8_pc_packet_checker_rejects_raw_profile_mismatch(tmp_path):
    payload = _v15_pc_packet_payload(
        profile_identity="task40extra_v18_p6_y_orbit_b0_y8_reference_v1"
    )
    payload["candidate_facts"][0]["raw_facts"]["profile_identity"] = (
        "task40extra_v15_p6_y_orbit_b0_reference_v1"
    )
    save_packet(tmp_path, "v18_ny8_pc_wrong_profile", payload)

    with pytest.raises(ValueError, match="profile identity differs"):
        verify_v15_pc_state_packet(tmp_path / "v18_ny8_pc_wrong_profile.json")


def test_v18_ny8_pc_packet_checker_rejects_wrong_twist_budget_norm(tmp_path):
    save_packet(
        tmp_path,
        "v18_ny8_pc_bad_norm",
        _v15_pc_packet_payload(
            profile_identity="task40extra_v18_p6_y_orbit_b0_y8_reference_v1",
            bad_lifted_norm=True,
        ),
    )

    with pytest.raises(ValueError, match="raw metrics do not match|budget differs|lifted-sector budget norm"):
        verify_v15_pc_state_packet(tmp_path / "v18_ny8_pc_bad_norm.json")


def test_v15_pc_checker_cli_saves_pass_and_rejection_receipts(tmp_path, capsys):
    save_packet(tmp_path, "v15_cli_pass", _v15_pc_packet_payload())
    packet_path = tmp_path / "v15_cli_pass.json"

    assert output_checker_main([str(packet_path), "--v15-pc-state-packet"]) == 0
    pass_receipt_path = tmp_path / "v15_cli_pass.v15_checker_receipt.json"
    pass_receipt = json.loads(pass_receipt_path.read_text(encoding="utf-8"))
    assert pass_receipt["status"] == "PASS"
    assert pass_receipt["passed"] is True
    assert pass_receipt["packet_json_sha256"] == hashlib.sha256(
        packet_path.read_bytes()
    ).hexdigest()
    assert pass_receipt["packet_npz_sha256"] == pass_receipt["result"][
        "packet_npz_sha256"
    ]
    assert json.loads(capsys.readouterr().out)["receipt_path"] == str(
        pass_receipt_path.resolve()
    )

    save_packet(tmp_path, "v15_cli_rejected", _v15_pc_packet_payload())
    rejected_npz = tmp_path / "v15_cli_rejected.npz"
    with rejected_npz.open("ab") as stream:
        stream.write(b"corrupted")
    rejected_packet = tmp_path / "v15_cli_rejected.json"
    assert output_checker_main([str(rejected_packet), "--v15-pc-state-packet"]) == 2
    rejected_receipt = json.loads(
        (tmp_path / "v15_cli_rejected.v15_checker_receipt.json").read_text(
            encoding="utf-8"
        )
    )
    assert rejected_receipt["status"] == "REJECTED"
    assert rejected_receipt["passed"] is False
    assert rejected_receipt["error"]["type"] == "ValueError"
    assert "NPZ identity" in rejected_receipt["error"]["message"]
    assert json.loads(capsys.readouterr().out)["receipt_path"] == str(
        (tmp_path / "v15_cli_rejected.v15_checker_receipt.json").resolve()
    )


def test_v15_pc_packet_checker_uses_original_action_scale_for_roundoff(tmp_path):
    save_packet(
        tmp_path,
        "v15_pc_roundoff",
        _v15_pc_packet_payload(tiny_residual=True),
    )

    result = verify_v15_pc_state_packet(tmp_path / "v15_pc_roundoff.json")

    assert result["passed"] is True
    assert result["numerically_admitted"] is True
    assert result["candidate_selection"]["candidate_facts"][0][
        "original_scale_max_normalized_exceedance"
    ] < 1.0


@pytest.mark.parametrize("corruption", ("hash", "rows", "decomposition"))
def test_v15_pc_packet_checker_rejects_bad_hash_or_unregistered_rows(tmp_path, corruption):
    payload = _v15_pc_packet_payload(
        bad_state_hash=corruption == "hash",
        short_rhs=corruption == "rows",
        bad_decomposition=corruption == "decomposition",
    )
    save_packet(tmp_path, "v15_pc_bad", payload)

    with pytest.raises(ValueError, match="state hash|profile shape|action scale"):
        verify_v15_pc_state_packet(tmp_path / "v15_pc_bad.json")


_V17_OUTPUT_PROFILE = "task40extra_v17_p6_y_orbit_gx560_reference_v1"
_V17_OUTPUT_STRATEGY = "ROW_TILE_BOUNDED_CSR_V17"


def _make_v17_output_bundle_fixture(tmp_path):
    from src.io.physical_intermediate_profile import profile_facts

    source_sha = "c" * 40
    input_sha = "d" * 64
    physical_sha = "e" * 64
    profile = profile_facts(_V17_OUTPUT_PROFILE)
    run_id = profile["run_id"]
    stage = profile["stage"]
    field_path = tmp_path / "field.vtu"
    field_path.write_bytes(b"synthetic V17 field fixture")
    port_table_path = tmp_path / "dtn_port_diffraction_orders_3d.csv"
    with port_table_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=("side", "m", "n", "polarization")
        )
        writer.writeheader()
        for side in ("top", "bottom"):
            for mode_index in range(170):
                writer.writerow(
                    {"side": side, "m": mode_index, "n": 0, "polarization": "s"}
                )
    rhs = np.array([3 + 0j, 4 + 0j], dtype=np.complex128)
    applied = np.array([1 + 0j, 0 + 0j], dtype=np.complex128)
    residual = rhs - applied
    relative = float(np.linalg.norm(residual) / np.linalg.norm(rhs))
    save_packet(
        tmp_path,
        "residual",
        {
            "relative_residual": relative,
            "native_witness_relative_residual": relative,
            "limit": 1.0,
            "full_physical_rhs_storage": rhs,
            "full_solution_storage": np.array([0.5 + 0j, 0.25 + 0j]),
            "target_backend_applied_storage": applied,
            "target_backend_residual_storage": residual,
            "native_witness_applied_storage": applied,
            "native_witness_residual_storage": residual,
        },
    )
    output_identity = {
        "source_sha": source_sha,
        "profile_identity": _V17_OUTPUT_PROFILE,
        "q_assembly_strategy": _V17_OUTPUT_STRATEGY,
        "stage": stage,
        "run_id": run_id,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
    }
    scientific_identity = {
        "source_sha": source_sha,
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "full_solution_packet_json": str(tmp_path / "residual.json"),
        "full_solution_storage_sha256": "a" * 64,
        "ordered_physical_mode_sha256": "b" * 64,
        "field_mode_and_diffraction_files": [
            {
                "path": str(field_path),
                "sha256": hashlib.sha256(field_path.read_bytes()).hexdigest(),
            },
            {
                "path": str(port_table_path),
                "sha256": hashlib.sha256(port_table_path.read_bytes()).hexdigest(),
            },
        ],
    }
    output_path = tmp_path / "official_output.json"
    output_path.write_text(
        json.dumps(
            {
                "identity": output_identity,
                "scientific_identity": scientific_identity,
                "passed": True,
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "run_manifest.json").write_text(
        json.dumps({"source_sha": source_sha, "run_id": run_id}), encoding="utf-8"
    )
    allocation_events = tmp_path / "allocation_events.jsonl"
    allocation_bytes = (
        b'{"event":"v10_strict_allocation_admission"}\n'
        b'{"event":"v10_strict_allocation_admission_complete"}\n'
    )
    allocation_events.write_bytes(allocation_bytes)
    allocation_sha = hashlib.sha256(allocation_bytes).hexdigest()
    summary = {
        "source_sha": source_sha,
        "profile": _V17_OUTPUT_PROFILE,
        "q_assembly_strategy": _V17_OUTPUT_STRATEGY,
        "stage": stage,
        "status": "PASS",
        "allocation_gate_invocation_count": 1,
        "allocation_admission_raw_validation": {"passed": True},
        "allocation_admission_raw": {
            "path": "allocation_events.jsonl",
            "size_bytes": len(allocation_bytes),
            "sha256": allocation_sha,
            "record_count": 2,
            "allocation_admission_event_count": 1,
            "allocation_admission_complete_event_count": 1,
        },
        "reference_audit_snapshot": {
            "sector_audits_before_destroy": [
                _valid_v17_bundle_sector([0, 1]),
                _valid_v17_bundle_sector([2, 3]),
            ]
        },
        "scientific_identity": {
            "source_sha": source_sha,
            "input_sha256": input_sha,
            "physical_model_sha256": physical_sha,
        },
    }
    summary_path = tmp_path / "task40_v10_p6_candidate_summary.json"
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    return output_path, summary_path, output_identity


def _valid_v17_bundle_sector(global_q_indices):
    shapes = {
        "00": [2, 2],
        "01": [2, 3],
        "10": [3, 2],
        "11": [3, 3],
    }
    norms = {"00": 2.0, "01": 1.0e-12, "10": 2.0e-12, "11": 3.0}
    diagonal_scale = max(norms["00"], norms["11"])
    patterns = {
        key: {
            "shape": shape,
            "wide_counts_and_prefix_checked_before_cast": True,
            "full_shape_bitset_bytes": 0,
            "full_coo_list_count": 0,
        }
        for key, shape in shapes.items()
    }
    return {
        "global_q_indices": global_q_indices,
        "assembly_strategy": _V17_OUTPUT_STRATEGY,
        "block_shapes": shapes,
        "pattern_facts_by_block": patterns,
        "complete_csr_frobenius_norm_by_block": norms,
        "off_diagonal_relative": {
            "q0_q1_relative": norms["01"] / diagonal_scale,
            "q1_q0_relative": norms["10"] / diagonal_scale,
        },
        "pattern_layout_pass_count": 1,
        "numeric_contribution_pass_count": 1,
        "cartesian_support_pairs_materialized": 0,
        "full_shape_bitset_bytes": 0,
        "full_coo_list_count": 0,
        "global_python_row_set_count": 0,
        "route_query_uses_temporary_sort": False,
        "support_route_spool_removed_after_pattern": True,
        "row_tiles_are_materialized_in_two_descriptor_passes": True,
        "descriptor_replay_regenerates_no_FE_or_Hhat_values": True,
        "all_four_complete_csr_owners_retained_through_norm_gate": True,
        "staging_peak_bytes_total_all_blocks": 4096,
        "staging_budget_bytes_total_all_q_blocks": 256 * 1024**2,
        "final_four_block_csr_payload_bytes": 8192,
        "final_csr_payload_bytes_total": 8192,
        "temporary_filesystem_free_space_reserve_bytes": 256 * 1024**2,
        "temporary_filesystem_free_bytes_minimum_observed": 2 * 1024**3,
    }


def test_v17_output_bundle_dispatches_from_bound_run_identity(tmp_path):
    output_path, _summary_path, expected_identity = _make_v17_output_bundle_fixture(tmp_path)
    result = verify_v10_output_bundle(output_path, expected_channel_count=340)

    assert result["status"] == "PASS"
    assert result["v17_row_tile_assembly"]["passed"] is True
    assert result["v17_row_tile_assembly"]["covered_q"] == [0, 1, 2, 3]
    assert result["v17_row_tile_allocation_admission_ledger"]["passed"] is True
    assert (
        result["v17_row_tile_allocation_admission_ledger"][
            "allocation_gate_invocation_count"
        ]
        == 1
    )
    assert result["v17_dispatch_binding"] == {
        "identity_source": (
            "official_output.identity + adjacent run_manifest.json + "
            "task40_v10_p6_candidate_summary.json"
        ),
        "source_sha": expected_identity["source_sha"],
        "profile_identity": expected_identity["profile_identity"],
        "run_id": expected_identity["run_id"],
        "stage": expected_identity["stage"],
        "q_assembly_strategy": _V17_OUTPUT_STRATEGY,
        "registered_profile_contract_passed": True,
        "packet_scientific_identity_match_passed": True,
        "worker_summary_binding_passed": True,
        "run_manifest_binding_passed": True,
    }


@pytest.mark.parametrize(
    ("field", "bad_value"),
    (
        ("source_sha", "f" * 40),
        ("profile", "task40extra_v17_p6_y_orbit_b0_reference_v1"),
        ("q_assembly_strategy", "LEGACY_GLOBAL_CSR_SUM"),
        ("stage", "B0_CANDIDATE"),
    ),
)
def test_v17_output_bundle_rejects_worker_summary_identity_mismatch(
    tmp_path, field, bad_value
):
    output_path, summary_path, _identity = _make_v17_output_bundle_fixture(tmp_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary[field] = bad_value
    summary_path.write_text(json.dumps(summary), encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="worker summary differs from the output source/profile/run/strategy",
    ):
        verify_v10_output_bundle(output_path, expected_channel_count=340)


def test_v17_output_bundle_rejects_run_manifest_identity_mismatch(tmp_path):
    output_path, _summary_path, _identity = _make_v17_output_bundle_fixture(tmp_path)
    manifest_path = tmp_path / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["run_id"] = "other-run"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(
        ValueError, match="run manifest differs from the output source/run identity"
    ):
        verify_v10_output_bundle(output_path, expected_channel_count=340)


@pytest.mark.parametrize(
    ("identity_field", "error_match"),
    (
        ("q_assembly_strategy", "packet strategy identity is incomplete"),
        ("profile_identity", "omits its registered profile"),
        ("source_sha", "omits a valid frozen source SHA"),
    ),
)
def test_v17_output_bundle_rejects_missing_route_identity_fields(
    tmp_path, identity_field, error_match
):
    output_path, _summary_path, _identity = _make_v17_output_bundle_fixture(tmp_path)
    output = json.loads(output_path.read_text(encoding="utf-8"))
    del output["identity"][identity_field]
    output_path.write_text(json.dumps(output), encoding="utf-8")

    with pytest.raises(ValueError, match=error_match):
        verify_v10_output_bundle(output_path, expected_channel_count=340)
