from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import stat
from typing import Any, Mapping

import pytest

from benchmarks.task035e_candidate_output import adapt_candidate_output
from benchmarks.task035e_candidate_output import CandidateOutputError
from benchmarks.task035e_live_shadow_bridge import (
    LIVE_SHADOW_BRIDGE_NEGATIVE_STATUS,
    LIVE_SHADOW_BRIDGE_SCHEMA,
    LiveShadowBridgeError,
    _effectivity_audit,
    build_live_shadow_bridge,
    write_live_shadow_bridge,
)
from benchmarks.task035e_shadow_bundle import (
    REQUEST_SCHEMA,
    BoundJSONInput,
    ShadowBundleError,
    _action_row,
    build_shadow_bundle,
)
from benchmarks.task035e_blind_cycle import goal_vector_from_candidate_output
from src.adaptivity.blind_controller import (
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
)
from src.adaptivity.task035e_actual_dwr import ACTUAL_DWR_SCHEMA
from src.adaptivity.task035e_shadow_observer import (
    SHADOW_EVALUATION_SCHEMA,
)
from src.test.test_232_task035e_candidate_output import (
    _rewrite_record,
    _write_candidate_run,
)
from src.test.test_241_task035e_actual_shadow_bundle import (
    P_DEGREE_SHA,
    _marking_and_prediction,
    _rewrite_shadow_candidate,
    _set_role,
    _transition_payload,
    _upgrade_to_replayable_cycle3_plan,
)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _namespaced_sha(value: object, namespace: str) -> str:
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    digest.update(_canonical_bytes(value))
    return digest.hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object, *, mode: int = 0o644) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    path.chmod(mode)
    return _file_sha(path)


def _bind_live_reference(
    record: Any,
    *,
    role: str,
    path: Path,
    schema: str,
    status: str,
) -> Any:
    sha = _file_sha(path)

    def mutate(payload: dict[str, object]) -> None:
        artifact = payload["task035e_blind_candidate_launch_gate"][
            "artifacts"
        ]
        assert isinstance(artifact, dict)
        artifact["blind_live_role_evidence"] = {
            "role": role,
            "path": str(path),
            "sha256": sha,
            "schema_version": schema,
            "status": status,
            "independent_gate": {
                "schema_version": (
                    "task035e.blind-live-role-evidence-gate.v1"
                ),
                "pass": True,
                "checks": {"fixture_replay": True},
                "failures": [],
                "details": {"role": role},
            },
        }

    return _rewrite_record(record, mutate)


def _current_snapshot(
    *,
    current: Any,
    path: Path,
) -> Mapping[str, object]:
    unsigned: dict[str, object] = {
        "schema_version": "task035e.multigoal-current-live-snapshot.v1",
        "status": "multigoal_current_live_snapshot_pass",
        "pass": True,
        "role": "current_blind_state",
        "source_sha": current.source_sha,
        "trial_id": current.trial_id,
        "cycle_index": current.cycle_index,
        "mpi_size": 8,
        "formal_mpi8_qualified": True,
        "diagnostic_serial_fixture": False,
        "plan_identity": {
            "file_sha256": current.plan_file_sha256,
        },
        "ordinary_default_changed": False,
    }
    payload = {
        **unsigned,
        "manifest_payload_sha256": _namespaced_sha(
            unsigned,
            "task035e.multigoal-current-manifest.v1",
        ),
    }
    _write_json(path, payload, mode=0o600)
    return payload


def _actual_dwr_report(
    *,
    shadow: Any,
    shadow_kind: str,
    signed_eta: Mapping[str, float],
) -> Mapping[str, object]:
    plan = {
        "file_sha256": shadow.plan_file_sha256,
        "forest_leaf_catalog_sha256": (
            shadow.forest_leaf_catalog_sha256
        ),
        "cell_degree_plan_sha256": shadow.cell_degree_plan_sha256,
    }
    layout = {"fixture": "owner-partition"}
    operator = {"fixture": "shadow-operator"}
    implementation_sha = "5" * 64
    residual_sha = "6" * 64
    goal_rows = []
    for goal_id in FORMAL_GOAL_IDS:
        row_unsigned = {
            "goal_id": goal_id,
            "signed_eta_real_zH_r": signed_eta[goal_id],
            "actual_adjoint_solve_complete": True,
            "endpoint_goal_delta_consumed": False,
            "ksp_converged_reason": 2,
            "adjoint_true_relative_residual": 1.0e-12,
            "adjoint_relative_tolerance": 1.0e-9,
        }
        goal_rows.append(
            {
                **row_unsigned,
                "goal_evidence_sha256": _namespaced_sha(
                    row_unsigned,
                    "task035e.actual-dwr.per-goal.v1",
                ),
            }
        )
    adjoint_sha = _namespaced_sha(
        {
            "shadow_plan_identity": plan,
            "layout_identity": layout,
            "operator_identity": operator,
        },
        "task035e.actual-dwr-adjoint-system.v1",
    )
    unsigned: dict[str, object] = {
        "schema_version": ACTUAL_DWR_SCHEMA,
        "status": "actual_live_shadow_dwr_pass",
        "pass": True,
        "source_sha": shadow.source_sha,
        "shadow_kind": shadow_kind,
        "shadow_plan_identity": plan,
        "layout_identity": layout,
        "operator_identity": operator,
        "implementation_identity": {
            "implementation_sha256": implementation_sha,
        },
        "enriched_current_residual": {
            "partition_bound_sha256": residual_sha,
        },
        "goal_inventory": {
            "formal_goal_count": len(FORMAL_GOAL_IDS),
            "formal_goal_inventory_sha256": (
                FORMAL_GOAL_INVENTORY_SHA256
            ),
            "ordered_goal_ids": list(FORMAL_GOAL_IDS),
        },
        "goals": goal_rows,
        "aggregate_identities": {
            "implementation_sha256": implementation_sha,
            "primal_residual_sha256": residual_sha,
            "adjoint_system_sha256": adjoint_sha,
        },
        "capability_credit": {
            "actual_enriched_residual_complete": True,
            "actual_59_goal_adjoint_complete": True,
            "actual_signed_dwr_complete": True,
        },
        "ordinary_default_changed": False,
    }
    return {
        **unsigned,
        "report_sha256": _namespaced_sha(
            unsigned,
            "task035e.actual-live-shadow-dwr-report.v1",
        ),
    }


def _shadow_live_evidence(
    *,
    current: Any,
    shadow: Any,
    current_snapshot_path: Path,
    current_snapshot: Mapping[str, object],
    path: Path,
    signed_eta: Mapping[str, float],
) -> Mapping[str, object]:
    report = _actual_dwr_report(
        shadow=shadow,
        shadow_kind="p-shadow",
        signed_eta=signed_eta,
    )
    unsigned: dict[str, object] = {
        "schema_version": SHADOW_EVALUATION_SCHEMA,
        "status": "live_shadow_59_goal_actual_dwr_pass",
        "pass": True,
        "source_sha": shadow.source_sha,
        "trial_id": shadow.trial_id,
        "cycle_index": shadow.cycle_index,
        "shadow_kind": "p-shadow",
        "mpi_size": 8,
        "formal_mpi8_qualified": True,
        "diagnostic_serial_fixture": False,
        "current_snapshot": {
            "manifest_path": str(current_snapshot_path),
            "manifest_file_sha256": _file_sha(current_snapshot_path),
            "manifest_payload_sha256": current_snapshot[
                "manifest_payload_sha256"
            ],
            "current_plan_file_sha256": current.plan_file_sha256,
        },
        "shadow_plan_file_sha256": shadow.plan_file_sha256,
        "actual_dwr": report,
        "signed_dwr_delta": dict(signed_eta),
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
        "hidden_reference_consumed": False,
        "endpoint_delta_used_as_dwr": False,
        "ordinary_default_changed": False,
    }
    payload = {
        **unsigned,
        "payload_sha256": _namespaced_sha(
            unsigned,
            "task035e.live-shadow-evaluation-payload.v1",
        ),
    }
    _write_json(path, payload, mode=0o600)
    return payload


def _fixture(
    tmp_path: Path,
    *,
    nonzero_eta_goal: str | None = None,
) -> dict[str, Any]:
    current_record = _upgrade_to_replayable_cycle3_plan(
        _write_candidate_run(tmp_path / "current")
    )
    current_pre = adapt_candidate_output(current_record)
    transition = _transition_payload(
        current=current_pre,
        action_id="p-up-cell-1",
        kind="p-up",
        target_root=1,
        next_forest_sha=current_pre.forest_leaf_catalog_sha256,
        next_degree_sha=P_DEGREE_SHA,
    )
    shadow_record = _rewrite_shadow_candidate(
        _set_role(
            _write_candidate_run(tmp_path / "p-shadow"),
            "blind_p_shadow_solve",
        ),
        current=current_pre,
        transition=transition,
        next_forest_sha=current_pre.forest_leaf_catalog_sha256,
        next_degree_sha=P_DEGREE_SHA,
        increments=(20, 20, 10, 100, 200, 1024),
    )
    shadow_pre = adapt_candidate_output(
        shadow_record,
        output_role="p-shadow",
    )
    snapshot_path = (
        current_record.path.parent
        / "task035e_current_snapshot"
        / "manifest.json"
    )
    snapshot = _current_snapshot(
        current=current_pre,
        path=snapshot_path,
    )
    signed_eta = {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    if nonzero_eta_goal is not None:
        signed_eta[nonzero_eta_goal] = 1.0e-8
    live_path = (
        shadow_record.path.parent
        / "task035e_p_shadow_evaluation.json"
    )
    _shadow_live_evidence(
        current=current_pre,
        shadow=shadow_pre,
        current_snapshot_path=snapshot_path,
        current_snapshot=snapshot,
        path=live_path,
        signed_eta=signed_eta,
    )
    current_record = _bind_live_reference(
        current_record,
        role="current",
        path=snapshot_path,
        schema="task035e.multigoal-current-live-snapshot.v1",
        status="multigoal_current_live_snapshot_pass",
    )
    shadow_record = _bind_live_reference(
        shadow_record,
        role="p-shadow",
        path=live_path,
        schema=SHADOW_EVALUATION_SCHEMA,
        status="live_shadow_59_goal_actual_dwr_pass",
    )
    transition_path = tmp_path / "transition.json"
    transition_sha = _write_json(transition_path, transition)
    (
        marking_path,
        marking_sha,
        prediction_path,
        prediction_sha,
        _prediction,
    ) = _marking_and_prediction(
        root=tmp_path / "p-selected",
        current=current_pre,
        transition=transition,
    )
    return {
        "current_record": BoundJSONInput(
            current_record.path,
            current_record.sha256,
        ),
        "shadow_record": BoundJSONInput(
            shadow_record.path,
            shadow_record.sha256,
        ),
        "transition": BoundJSONInput(
            transition_path,
            transition_sha,
        ),
        "goal_marking": BoundJSONInput(marking_path, marking_sha),
        "verification_prediction": BoundJSONInput(
            prediction_path,
            prediction_sha,
        ),
        "live": BoundJSONInput(live_path, _file_sha(live_path)),
    }


def test_live_bridge_passes_neutral_59_goal_actual_dwr_and_feeds_bundle(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    built = build_live_shadow_bridge(
        current_record=fixture["current_record"],
        shadow_record=fixture["shadow_record"],
        transition_action=fixture["transition"],
        live_shadow_evidence=fixture["live"],
    )
    assert built.passed is True
    assert built.payload["effectivity_audit"][
        "factor_two_or_neutral_goal_count"
    ] == 59
    assert built.payload["effectivity_audit"]["neutral_goal_count"] == 59
    output = tmp_path / "bridge.json"
    receipt = write_live_shadow_bridge(output, built)
    assert receipt.passed is True
    assert stat.S_IMODE(output.stat().st_mode) == 0o600

    current = adapt_candidate_output(
        fixture["current_record"],
    )
    action, bridge_file_sha = _action_row(
        {
            "transition_action": {
                "path": str(fixture["transition"].path),
                "sha256": fixture["transition"].sha256,
            },
            "goal_marking": {
                "path": str(fixture["goal_marking"].path),
                "sha256": fixture["goal_marking"].sha256,
            },
            "verification_prediction": {
                "path": str(fixture["verification_prediction"].path),
                "sha256": fixture["verification_prediction"].sha256,
            },
            "shadow_record": {
                "path": str(fixture["shadow_record"].path),
                "sha256": fixture["shadow_record"].sha256,
            },
            "dwr_evidence": {
                "path": str(output),
                "sha256": receipt.file_sha256,
            },
        },
        base=tmp_path,
        lane="p",
        current=current,
        current_goals=goal_vector_from_candidate_output(current.payload),
    )
    assert action["sign_consistent"] is True
    assert bridge_file_sha == receipt.file_sha256


def test_live_bridge_preserves_actual_zero_eta_nonzero_as_controlled_negative(
    tmp_path: Path,
) -> None:
    failed_goal = FORMAL_GOAL_IDS[0]
    fixture = _fixture(tmp_path, nonzero_eta_goal=failed_goal)
    built = build_live_shadow_bridge(
        current_record=fixture["current_record"],
        shadow_record=fixture["shadow_record"],
        transition_action=fixture["transition"],
        live_shadow_evidence=fixture["live"],
    )
    assert built.passed is False
    assert built.payload["status"] == LIVE_SHADOW_BRIDGE_NEGATIVE_STATUS
    assert built.payload["classification"] == (
        "controlled_negative_effectivity"
    )
    assert built.payload["effectivity_audit"][
        "actual_near_zero_eta_nonzero_goal_ids"
    ] == [failed_goal]
    output = tmp_path / "controlled-negative.json"
    receipt = write_live_shadow_bridge(output, built)
    assert receipt.passed is False
    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == (
        LIVE_SHADOW_BRIDGE_SCHEMA
    )


def test_effectivity_requires_54_of_59_and_rejects_opposite_sign() -> None:
    current = {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    shadow = {goal_id: 1.0 for goal_id in FORMAL_GOAL_IDS}
    eta = {
        goal_id: (1.0 if index < 54 else 0.1)
        for index, goal_id in enumerate(FORMAL_GOAL_IDS)
    }
    audit, _ = _effectivity_audit(
        signed_eta=eta,
        current_values=current,
        shadow_values=shadow,
    )
    assert audit["pass"] is True
    assert audit["factor_two_or_neutral_goal_count"] == 54

    eta[FORMAL_GOAL_IDS[53]] = 0.1
    audit, _ = _effectivity_audit(
        signed_eta=eta,
        current_values=current,
        shadow_values=shadow,
    )
    assert audit["pass"] is False
    assert audit["factor_two_or_neutral_goal_count"] == 53

    eta[FORMAL_GOAL_IDS[0]] = -1.0
    audit, _ = _effectivity_audit(
        signed_eta=eta,
        current_values=current,
        shadow_values=shadow,
    )
    assert audit["pass"] is False
    assert audit["opposite_sign_goal_ids"] == [FORMAL_GOAL_IDS[0]]


def test_live_bridge_rejects_explicit_live_artifact_hash_drift(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    with pytest.raises(
        LiveShadowBridgeError,
        match="explicit live-shadow artifact differs",
    ):
        build_live_shadow_bridge(
            current_record=fixture["current_record"],
            shadow_record=fixture["shadow_record"],
            transition_action=fixture["transition"],
            live_shadow_evidence=BoundJSONInput(
                fixture["live"].path,
                "f" * 64,
            ),
        )


def test_formal_live_watchdogs_cannot_bypass_bridge_with_raw_dwr(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    built = build_live_shadow_bridge(
        current_record=fixture["current_record"],
        shadow_record=fixture["shadow_record"],
        transition_action=fixture["transition"],
        live_shadow_evidence=fixture["live"],
    )
    raw_dwr_path = tmp_path / "raw-dwr.json"
    raw_dwr_sha = _write_json(
        raw_dwr_path,
        built.payload["dwr_evidence"],
    )
    current = adapt_candidate_output(fixture["current_record"])
    with pytest.raises(ShadowBundleError, match="require.*post-PDE bridge"):
        _action_row(
            {
                "transition_action": {
                    "path": str(fixture["transition"].path),
                    "sha256": fixture["transition"].sha256,
                },
                "goal_marking": {
                    "path": str(fixture["goal_marking"].path),
                    "sha256": fixture["goal_marking"].sha256,
                },
                "verification_prediction": {
                    "path": str(
                        fixture["verification_prediction"].path
                    ),
                    "sha256": (
                        fixture["verification_prediction"].sha256
                    ),
                },
                "shadow_record": {
                    "path": str(fixture["shadow_record"].path),
                    "sha256": fixture["shadow_record"].sha256,
                },
                "dwr_evidence": {
                    "path": str(raw_dwr_path),
                    "sha256": raw_dwr_sha,
                },
            },
            base=tmp_path,
            lane="p",
            current=current,
            current_goals=goal_vector_from_candidate_output(
                current.payload
            ),
        )


def test_shadow_bundle_rejects_controlled_negative_bridge(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path, nonzero_eta_goal=FORMAL_GOAL_IDS[0])
    built = build_live_shadow_bridge(
        current_record=fixture["current_record"],
        shadow_record=fixture["shadow_record"],
        transition_action=fixture["transition"],
        live_shadow_evidence=fixture["live"],
    )
    output = tmp_path / "negative.json"
    receipt = write_live_shadow_bridge(output, built)
    request = {
        "schema_version": REQUEST_SCHEMA,
        "current_record": {
            "path": str(fixture["current_record"].path),
            "sha256": fixture["current_record"].sha256,
        },
        "p_actions": [
            {
                "transition_action": {
                    "path": str(fixture["transition"].path),
                    "sha256": fixture["transition"].sha256,
                },
                "goal_marking": {
                    "path": str(fixture["goal_marking"].path),
                    "sha256": fixture["goal_marking"].sha256,
                },
                "verification_prediction": {
                    "path": str(
                        fixture["verification_prediction"].path
                    ),
                    "sha256": (
                        fixture["verification_prediction"].sha256
                    ),
                },
                "shadow_record": {
                    "path": str(fixture["shadow_record"].path),
                    "sha256": fixture["shadow_record"].sha256,
                },
                "dwr_evidence": {
                    "path": str(output),
                    "sha256": receipt.file_sha256,
                },
            }
        ],
        "h_actions": [],
    }
    request_path = tmp_path / "request.json"
    request_sha = _write_json(request_path, request)
    with pytest.raises(ShadowBundleError, match="controlled negative"):
        build_shadow_bundle(BoundJSONInput(request_path, request_sha))


def test_live_bridge_has_no_evaluator_package_or_auditor_import() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "benchmarks"
        / "task035e_live_shadow_bridge.py"
    )
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.append(node.module or "")
    assert not any(
        "reference_certifier" in name or "hidden_auditor" in name
        for name in imported
    )


def test_nonfixture_candidate_cannot_omit_live_role_evidence(
    tmp_path: Path,
) -> None:
    record = _write_candidate_run(tmp_path)

    def mutate(payload: dict[str, object]) -> None:
        artifact = payload["task035e_blind_candidate_launch_gate"][
            "artifacts"
        ]
        assert isinstance(artifact, dict)
        artifact["checks"] = {
            "solver_summary_hash_bound": True,
            "blind_live_role_evidence_hash_bound": True,
        }

    record = _rewrite_record(record, mutate)
    with pytest.raises(CandidateOutputError, match="lacks live-role"):
        adapt_candidate_output(record)
