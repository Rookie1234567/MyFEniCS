from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import benchmarks.task035e_cellwise_authority as adapter
from benchmarks.task035e_cellwise_authority import (
    CELLWISE_DWR_AUTHORITY_SCHEMA,
    STRUCTURAL_COST_MODEL_SCHEMA,
    STRUCTURAL_COST_ROW_SCHEMA,
    build_cellwise_authority,
    write_cellwise_authority,
)
from benchmarks.task035e_goal_marking import (
    GoalMarkingError,
    produce_goal_marking,
)
from src.adaptivity.blind_controller.contracts import (
    FORMAL_GOAL_IDS,
    GoalVector,
)
from src.adaptivity.dyadic_hexa_refinement import DyadicHexKey
from src.adaptivity.task035e_initial_space import (
    build_task035e_initial_space_plan,
)
from src.adaptivity.task035e_plan_transition import (
    rebuild_hp_transition_state_from_solver_plan,
)
from src.common.config_3d import target_stage4_config
from src.test.test_259_task035e_goal_marking import (
    _cellwise_authority,
    _global_dwr,
)


_SOURCE_SHA = "1234567890abcdef1234567890abcdef12345678"


def _canonical_sha(value: object, *, namespace: str | None = None) -> str:
    digest = hashlib.sha256()
    if namespace is not None:
        digest.update(namespace.encode("ascii"))
        digest.update(b"\0")
    digest.update(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    )
    return digest.hexdigest()


def _file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _fixture_goal_vector(payload: dict[str, object]) -> GoalVector:
    shadow = payload.get("fixture") == "shadow"
    return GoalVector.from_mapping(
        {
            goal_id: (
                1.0e-6
                if shadow and goal_id == FORMAL_GOAL_IDS[0]
                else 0.0
            )
            for goal_id in FORMAL_GOAL_IDS
        }
    )


def _write_private(path: Path, value: object) -> str:
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return _file_sha(path)


def _reclose_partition(
    partition: dict[str, object],
    *,
    total_rows: int,
) -> dict[str, object]:
    rows = partition["rows"]
    assert isinstance(rows, list)
    quotient, remainder = divmod(total_rows, len(rows))
    residual_hashes = []
    adjoint_hashes = []
    for index, row in enumerate(rows):
        assert isinstance(row, dict)
        count = quotient + int(index < remainder)
        row["assigned_reduced_row_count"] = count
        row["assigned_trace_row_count"] = count
        row["assigned_auxiliary_row_count"] = 0
        unsigned = dict(row)
        unsigned.pop("row_sha256")
        row["row_sha256"] = _canonical_sha(
            unsigned,
            namespace="task035e.cellwise-signed-dwr-row.v1",
        )
        residual_hashes.append(row["local_residual_partition_sha256"])
        adjoint_hashes.append(row["local_adjoint_partition_sha256"])
    designation = partition["row_designation_identity"]
    assert isinstance(designation, dict)
    designation.update(
        {
            "independent_trace_rows": total_rows,
            "appended_auxiliary_rows": 0,
            "total_reduced_rows": total_rows,
        }
    )
    designation_unsigned = dict(designation)
    designation_unsigned.pop("designation_sha256")
    designation["designation_sha256"] = _canonical_sha(
        designation_unsigned,
        namespace="task035e.actual-dwr-row-designation.v1",
    )
    partition["residual_partition_catalog_sha256"] = _canonical_sha(
        residual_hashes,
        namespace="task035e.actual-dwr.residual-partition-catalog.v1",
    )
    partition["adjoint_partition_catalog_sha256"] = _canonical_sha(
        adjoint_hashes,
        namespace="task035e.actual-dwr.adjoint-partition-catalog.v1",
    )
    unsigned_partition = dict(partition)
    unsigned_partition.pop("partition_sha256")
    partition["partition_sha256"] = _canonical_sha(
        unsigned_partition,
        namespace="task035e.cellwise-signed-dwr-partition.v1",
    )
    return partition


def _fixture(
    tmp_path: Path,
) -> tuple[
    dict[str, object],
    object,
    Path,
    str,
    object,
    object,
    dict[str, object],
    Path,
    str,
]:
    config = target_stage4_config(degree=6, h_nm=20.0)
    plan = build_task035e_initial_space_plan(
        config,
        path_id="A",
        source_sha=_SOURCE_SHA,
        comm_size=8,
    ).plan_payload()
    plan_path = tmp_path / "current-plan.json"
    plan_sha = _write_private(plan_path, plan)
    state = rebuild_hp_transition_state_from_solver_plan(
        config,
        current_plan=plan,
        comm_size=8,
    )
    leaf_count = len(state.forest.leaves)
    current_inventory = {
        "raw_active_fe_dofs": 100_000,
        "active_fe_dofs": 80_000,
        "matrix_rows": 10_000,
        "matrix_nnz": 2_000_000,
        "factor_nnz": 10_000_000,
        "solver_peak_bytes": 2_000_000_000,
    }
    shadow_inventory = {
        "raw_active_fe_dofs": 100_000 + 30 * leaf_count,
        "active_fe_dofs": 80_000 + 20 * leaf_count,
        "matrix_rows": 10_000 + 20 * leaf_count,
        "matrix_nnz": 2_000_000 + 200 * leaf_count,
        "factor_nnz": 10_000_000 + 800 * leaf_count,
        "solver_peak_bytes": 2_100_000_000,
    }
    common = {
        "source_sha": _SOURCE_SHA,
        "trial_id": "path-a-cost-authority",
        "cycle_index": 0,
        "output_sha256": "a" * 64,
        "record_sha256": "b" * 64,
        "config_sha256": "c" * 64,
        "plan_path": plan_path,
        "plan_file_sha256": plan_sha,
        "forest_leaf_catalog_sha256": state.audit[
            "leaf_catalog_sha256"
        ],
        "cell_degree_plan_sha256": state.audit[
            "cell_degree_plan_sha256"
        ],
    }
    current = SimpleNamespace(
        **common,
        payload={"fixture": "current"},
        output_role="current",
        structural_inventory=current_inventory,
    )
    shadow = SimpleNamespace(
        **{
            **common,
            "payload": {"fixture": "shadow"},
            "output_sha256": "d" * 64,
            "record_sha256": "e" * 64,
            "plan_file_sha256": "f" * 64,
            "forest_leaf_catalog_sha256": "1" * 64,
            "cell_degree_plan_sha256": "2" * 64,
        },
        output_role="p-shadow",
        structural_inventory=shadow_inventory,
    )
    skeleton = _cellwise_authority(
        plan=plan,
        plan_file_sha256=plan_sha,
        state=state,
    )
    partition = dict(skeleton["localization"])
    partition["shadow_plan_identity"] = {
        "file_sha256": shadow.plan_file_sha256,
        "forest_leaf_catalog_sha256": (
            shadow.forest_leaf_catalog_sha256
        ),
        "cell_degree_plan_sha256": shadow.cell_degree_plan_sha256,
    }
    partition = _reclose_partition(
        partition,
        total_rows=shadow_inventory["matrix_rows"],
    )
    report = _global_dwr(state=state)
    report["operator_identity"] = {
        "matrix": {
            "global_shape": [
                shadow_inventory["matrix_rows"],
                shadow_inventory["matrix_rows"],
            ],
            "global_nnz": shadow_inventory["matrix_nnz"],
        }
    }
    report_unsigned = dict(report)
    report_unsigned.pop("report_sha256")
    report["report_sha256"] = _canonical_sha(
        report_unsigned,
        namespace="task035e.actual-live-shadow-dwr-report.v1",
    )
    live_path = tmp_path / "live-shadow.json"
    live_sha = _write_private(live_path, {"fixture": True})
    return (
        plan,
        state,
        plan_path,
        plan_sha,
        current,
        shadow,
        {"report": report, "partition": partition},
        live_path,
        live_sha,
    )


def _formal_bridge(
    path: Path,
    *,
    current: object,
    shadow: object,
    current_live: dict[str, object],
    shadow_live: dict[str, object],
    current_goals: GoalVector,
    shadow_goals: GoalVector,
    report_sha256: str,
    signed_dwr: dict[str, float],
) -> tuple[Path, str, str]:
    effectivity, actual_endpoint_delta = adapter._effectivity_audit(
        signed_eta=signed_dwr,
        current_values=current_goals.by_id,
        shadow_values=shadow_goals.by_id,
    )
    assert effectivity["pass"] is True
    unsigned = {
        "schema_version": adapter.LIVE_SHADOW_BRIDGE_SCHEMA,
        "status": adapter.LIVE_SHADOW_BRIDGE_STATUS,
        "pass": True,
        "classification": "qualified_actual_dwr_effectivity_pass",
        "source_sha": current.source_sha,
        "mpi_size": 8,
        "trial_id": current.trial_id,
        "cycle_index": current.cycle_index,
        "action_id": "fixture.p-up",
        "kind": "p-up",
        "target_ids": ["cell:r0:l0:i0:j0:k0"],
        "transition_action_sha256": "4" * 64,
        "transition_action_file_sha256": "5" * 64,
        "transition_action_identity_sha256": "6" * 64,
        "transition_action_representation": "plain",
        "current_watchdog_record_sha256": current.record_sha256,
        "shadow_watchdog_record_sha256": shadow.record_sha256,
        "current_output_sha256": current.output_sha256,
        "shadow_output_sha256": shadow.output_sha256,
        "current_plan_file_sha256": current.plan_file_sha256,
        "shadow_plan_file_sha256": shadow.plan_file_sha256,
        "current_mesh_forest_sha256": (
            current.forest_leaf_catalog_sha256
        ),
        "current_degree_map_sha256": current.cell_degree_plan_sha256,
        "shadow_mesh_forest_sha256": (
            shadow.forest_leaf_catalog_sha256
        ),
        "shadow_degree_map_sha256": shadow.cell_degree_plan_sha256,
        "current_goal_sha256": current_goals.sha256,
        "shadow_goal_sha256": shadow_goals.sha256,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": (
            adapter.FORMAL_GOAL_INVENTORY_SHA256
        ),
        "current_live_role_evidence": current_live,
        "shadow_live_role_evidence": shadow_live,
        "current_snapshot_payload_sha256": "7" * 64,
        "actual_dwr_report_sha256": report_sha256,
        "signed_dwr_delta": signed_dwr,
        "actual_endpoint_delta": actual_endpoint_delta,
        "effectivity_audit": effectivity,
        "dwr_evidence": {"fixture": True},
        "capability_credit": {
            "hash_bound_live_adjoint_complete": True,
            "post_pde_endpoint_binding_complete": True,
            "shadow_endpoint_effectivity_complete": True,
            "accuracy_credit": False,
        },
        "hidden_reference_consumed": False,
        "endpoint_delta_used_as_dwr": False,
        "ordinary_default_changed": False,
    }
    assert set(unsigned) | {"payload_sha256"} == set(
        adapter._LIVE_BRIDGE_PAYLOAD_FIELDS
    )
    payload_sha = _canonical_sha(unsigned)
    outer = {
        "schema_version": adapter.LIVE_SHADOW_BRIDGE_SCHEMA,
        "sha256": payload_sha,
        "payload": {**unsigned, "payload_sha256": payload_sha},
    }
    return path, _write_private(path, outer), payload_sha


def test_structural_cost_closes_and_authority_feeds_goal_marking(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        plan,
        state,
        plan_path,
        plan_sha,
        current,
        shadow,
        evidence,
        live_path,
        live_sha,
    ) = _fixture(tmp_path)

    def candidate(*_args, role: str, **_kwargs):
        selected = current if role == "current" else shadow
        return selected, selected.record_sha256, selected.output_sha256

    monkeypatch.setattr(adapter, "_candidate", candidate)
    monkeypatch.setattr(
        adapter,
        "_validate_live_evidence",
        lambda *_args, **_kwargs: (
            evidence["report"],
            evidence["partition"],
            {
                goal_id: (
                    1.0e-6 if goal_id == FORMAL_GOAL_IDS[0] else 0.0
                )
                for goal_id in FORMAL_GOAL_IDS
            },
            "3" * 64,
        ),
    )
    monkeypatch.setattr(
        adapter,
        "goal_vector_from_candidate_output",
        _fixture_goal_vector,
    )
    authority = build_cellwise_authority(
        current_record_path=tmp_path / "unused-current-record.json",
        current_record_file_sha256="b" * 64,
        shadow_record_path=tmp_path / "unused-shadow-record.json",
        shadow_record_file_sha256="e" * 64,
        current_output_path=tmp_path / "unused-current-output.json",
        current_output_file_sha256="a" * 64,
        shadow_output_path=tmp_path / "unused-shadow-output.json",
        shadow_output_file_sha256="d" * 64,
        live_shadow_evidence_path=live_path,
        live_shadow_evidence_file_sha256=live_sha,
        source_sha=_SOURCE_SHA,
        action_kind="p-up",
    )
    assert authority["schema_version"] == CELLWISE_DWR_AUTHORITY_SCHEMA
    model = authority["structural_cost_model"]
    assert model["schema_version"] == STRUCTURAL_COST_MODEL_SCHEMA
    assert model["integer_apportionment"]["weights_are_leaf_count"] is False
    assert model["integer_apportionment"]["weights_are_eta"] is False
    assert (
        model["common_cost_exclusion"][
            "solver_job_peak_distributed_to_leaves"
        ]
        is False
    )
    assert all(row["closed"] for row in model["closure"].values())
    assert model["global_apportioned_cost"][
        "estimated_added_solver_peak_bytes"
    ] != model["measured_global_delta"]["solver_peak_bytes"]
    authority_path = tmp_path / "authority.json"
    receipt = write_cellwise_authority(authority_path, authority)
    assert receipt.status == "cellwise_59_goal_dwr_pass"
    output = tmp_path / "marking.json"
    marking = produce_goal_marking(
        current_plan_path=plan_path,
        current_plan_file_sha256=plan_sha,
        dwr_authority_path=authority_path,
        dwr_authority_file_sha256=receipt.file_sha256,
        source_sha=_SOURCE_SHA,
        action_kind="p-up",
        output_path=output,
    )
    assert marking.status == "goal_marking_targets_selected"
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["structural_cost_model_sha256"] == model["model_sha256"]
    assert payload["canonical_target_ids"]
    selected = set(payload["canonical_target_ids"])
    expected_signed = {
        goal_id: sum(
            row["signed_dwr_contribution"][goal_id]
            for row in authority["localization"]["rows"]
            if row["target_id"] in selected
        )
        for goal_id in FORMAL_GOAL_IDS
    }
    assert payload["selected_signed_dwr_delta"] == expected_signed
    assert payload["selected_signed_dwr_delta_sha256"] == _canonical_sha(
        {
            "formal_goal_inventory_sha256": (
                authority["formal_goal_inventory_sha256"]
            ),
            "ordered_goal_ids": list(FORMAL_GOAL_IDS),
            "canonical_target_ids": payload["canonical_target_ids"],
            "signed_dwr_delta": expected_signed,
        },
        namespace="task035e.goal-marking-selected-signed-dwr.v1",
    )
    assert authority["localization"] == evidence["partition"]
    assert plan == json.loads(plan_path.read_text(encoding="utf-8"))
    assert state.cycle_index == 0


def test_formal_bridge_resolves_raw_evaluation_and_binds_bridge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _plan,
        _state,
        plan_path,
        _plan_sha,
        current_base,
        shadow_base,
        evidence,
        live_path,
        live_sha,
    ) = _fixture(tmp_path)
    current_goals = GoalVector.from_mapping(
        {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    )
    signed = {
        goal_id: 1.0e-6 if goal_id == FORMAL_GOAL_IDS[0] else 0.0
        for goal_id in FORMAL_GOAL_IDS
    }
    shadow_goals = GoalVector.from_mapping(signed)
    current_live = {
        "role": "current",
        "path": str(plan_path.resolve()),
        "sha256": _file_sha(plan_path),
        "payload_sha256": "8" * 64,
        "schema_version": "task035e.multigoal-current-live-snapshot.v1",
        "status": "multigoal_current_live_snapshot_pass",
    }
    shadow_live = {
        "role": "p-shadow",
        "path": str(live_path.resolve()),
        "sha256": live_sha,
        "payload_sha256": "3" * 64,
        "schema_version": "task035e.live-shadow-evaluation.v1",
        "status": "live_shadow_59_goal_actual_dwr_pass",
    }
    current = SimpleNamespace(
        **{
            **vars(current_base),
            "payload": {"fixture": "current"},
            "live_role_evidence": current_live,
        }
    )
    shadow = SimpleNamespace(
        **{
            **vars(shadow_base),
            "payload": {"fixture": "shadow"},
            "live_role_evidence": shadow_live,
        }
    )
    monkeypatch.setattr(
        adapter,
        "_candidate",
        lambda *_args, role, **_kwargs: (
            current if role == "current" else shadow,
            (current if role == "current" else shadow).record_sha256,
            (current if role == "current" else shadow).output_sha256,
        ),
    )
    monkeypatch.setattr(
        adapter,
        "_validate_live_evidence",
        lambda *_args, **_kwargs: (
            evidence["report"],
            evidence["partition"],
            signed,
            shadow_live["payload_sha256"],
        ),
    )
    monkeypatch.setattr(
        adapter,
        "goal_vector_from_candidate_output",
        lambda payload: (
            current_goals
            if payload["fixture"] == "current"
            else shadow_goals
        ),
    )
    bridge_path, bridge_file_sha, bridge_payload_sha = _formal_bridge(
        tmp_path / "p-live-dwr-bridge.json",
        current=current,
        shadow=shadow,
        current_live=current_live,
        shadow_live=shadow_live,
        current_goals=current_goals,
        shadow_goals=shadow_goals,
        report_sha256=evidence["report"]["report_sha256"],
        signed_dwr=signed,
    )
    build_kwargs = {
        "current_record_path": tmp_path / "unused-current-record.json",
        "current_record_file_sha256": current.record_sha256,
        "shadow_record_path": tmp_path / "unused-shadow-record.json",
        "shadow_record_file_sha256": shadow.record_sha256,
        "current_output_path": tmp_path / "unused-current-output.json",
        "current_output_file_sha256": current.output_sha256,
        "shadow_output_path": tmp_path / "unused-shadow-output.json",
        "shadow_output_file_sha256": shadow.output_sha256,
        "live_shadow_evidence_path": bridge_path,
        "live_shadow_evidence_file_sha256": bridge_file_sha,
        "source_sha": _SOURCE_SHA,
        "action_kind": "p-up",
    }
    authority = build_cellwise_authority(**build_kwargs)
    assert authority["pass"] is True
    assert (
        authority["live_shadow_evidence_file_sha256"]
        == bridge_file_sha
    )
    assert (
        authority["live_shadow_evidence_payload_sha256"]
        == bridge_payload_sha
    )
    tampered = json.loads(bridge_path.read_text(encoding="utf-8"))
    tampered["payload"]["actual_endpoint_delta"][
        FORMAL_GOAL_IDS[0]
    ] *= 2.0
    unsigned_tampered = dict(tampered["payload"])
    unsigned_tampered.pop("payload_sha256")
    tampered_payload_sha = _canonical_sha(unsigned_tampered)
    tampered["payload"]["payload_sha256"] = tampered_payload_sha
    tampered["sha256"] = tampered_payload_sha
    tampered_path = tmp_path / "tampered-p-live-dwr-bridge.json"
    tampered_file_sha = _write_private(tampered_path, tampered)
    with pytest.raises(
        adapter.CellwiseAuthorityError,
        match="differs from its raw evaluation",
    ):
        build_cellwise_authority(
            **{
                **build_kwargs,
                "live_shadow_evidence_path": tampered_path,
                "live_shadow_evidence_file_sha256": tampered_file_sha,
            }
        )


def test_raw_live_evaluation_effectivity_is_recomputed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _plan,
        _state,
        _plan_path,
        _plan_sha,
        current,
        shadow,
        evidence,
        live_path,
        live_sha,
    ) = _fixture(tmp_path)
    signed = {
        goal_id: 1.0e-6 if goal_id == FORMAL_GOAL_IDS[0] else 0.0
        for goal_id in FORMAL_GOAL_IDS
    }
    monkeypatch.setattr(
        adapter,
        "_validate_live_evidence",
        lambda *_args, **_kwargs: (
            evidence["report"],
            evidence["partition"],
            signed,
            "3" * 64,
        ),
    )
    zero_goals = GoalVector.from_mapping(
        {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    )
    monkeypatch.setattr(
        adapter,
        "goal_vector_from_candidate_output",
        lambda _payload: zero_goals,
    )
    with pytest.raises(
        adapter.CellwiseAuthorityError,
        match="endpoint effectivity did not pass",
    ):
        adapter._validate_bound_live_evidence(
            {"schema_version": adapter.SHADOW_EVALUATION_SCHEMA},
            file_sha256=live_sha,
            current=current,
            shadow=shadow,
            action_kind="p-up",
            live_path=live_path,
        )


@pytest.mark.parametrize("action_kind", ("p-up", "h-refine"))
def test_zero_reduced_owner_uses_active_interior_support(
    monkeypatch: pytest.MonkeyPatch,
    action_kind: str,
) -> None:
    key = DyadicHexKey(root=0, level=0, i=0, j=0, k=0)
    state = SimpleNamespace(
        forest=SimpleNamespace(leaves=(SimpleNamespace(key=key),)),
        cell_degree_by_key={key: 4},
    )
    action = {
        "action_sha256": "1" * 64,
        "action_identity_sha256": "2" * 64,
        "expected_removed_leaf_keys": (
            [key.to_dict()] if action_kind == "h-refine" else []
        ),
        "expected_added_leaf_keys": (
            [{} for _index in range(8)]
            if action_kind == "h-refine"
            else []
        ),
        "expected_net_added_leaf_count": (
            7 if action_kind == "h-refine" else 0
        ),
    }
    monkeypatch.setattr(
        adapter,
        "_face_neighbor_pairs",
        lambda _forest: (),
    )
    monkeypatch.setattr(
        adapter,
        "hp_transition_action_payload",
        lambda *_args, **_kwargs: action,
    )
    target = adapter.canonical_hp_cell_target_id(key)
    dwr_rows = {
        target: {
            "assigned_reduced_row_count": 0,
            "assigned_active_interior_row_count": 108,
        }
    }
    topology = adapter._candidate_topology_rows(
        state=state,
        dwr_rows=dwr_rows,
        action_kind=action_kind,
    )
    row = next(item for item in topology if item["target_id"] == target)
    assert row["eligible"] is True
    assert row["topology"]["assigned_shadow_reduced_row_count"] == 0
    assert (
        row["topology"]["assigned_shadow_active_interior_row_count"]
        == 108
    )
    assert all(weight > 0 for weight in row["weights"].values())

    dwr_rows[target] = {
        "assigned_reduced_row_count": 0,
        "assigned_active_interior_row_count": 0,
    }
    with pytest.raises(
        adapter.CellwiseAuthorityError,
        match="lacks attributable topology/row support",
    ):
        adapter._candidate_topology_rows(
            state=state,
            dwr_rows=dwr_rows,
            action_kind=action_kind,
        )


def test_cost_or_dwr_row_perturbation_is_rejected_after_outer_rehash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (
        _plan,
        _state,
        plan_path,
        plan_sha,
        current,
        shadow,
        evidence,
        live_path,
        live_sha,
    ) = _fixture(tmp_path)
    monkeypatch.setattr(
        adapter,
        "_candidate",
        lambda *_args, role, **_kwargs: (
            current if role == "current" else shadow,
            (current if role == "current" else shadow).record_sha256,
            (current if role == "current" else shadow).output_sha256,
        ),
    )
    monkeypatch.setattr(
        adapter,
        "_validate_live_evidence",
        lambda *_args, **_kwargs: (
            evidence["report"],
            evidence["partition"],
            {
                goal_id: (
                    1.0e-6 if goal_id == FORMAL_GOAL_IDS[0] else 0.0
                )
                for goal_id in FORMAL_GOAL_IDS
            },
            "3" * 64,
        ),
    )
    monkeypatch.setattr(
        adapter,
        "goal_vector_from_candidate_output",
        _fixture_goal_vector,
    )
    authority = dict(
        build_cellwise_authority(
            current_record_path=tmp_path / "c-record.json",
            current_record_file_sha256="b" * 64,
            shadow_record_path=tmp_path / "s-record.json",
            shadow_record_file_sha256="e" * 64,
            current_output_path=tmp_path / "c-output.json",
            current_output_file_sha256="a" * 64,
            shadow_output_path=tmp_path / "s-output.json",
            shadow_output_file_sha256="d" * 64,
            live_shadow_evidence_path=live_path,
            live_shadow_evidence_file_sha256=live_sha,
            source_sha=_SOURCE_SHA,
            action_kind="p-up",
        )
    )
    model = dict(authority["structural_cost_model"])
    invalid_model = json.loads(json.dumps(model))
    invalid_row = invalid_model["rows"][0]
    invalid_row.update(
        {
            "eligible": False,
            "ineligibility": "fixture rejected action",
            "topology": None,
            "weights": {
                "active": 0,
                "rows": 0,
                "matrix_nnz": 0,
                "factor_nnz": 0,
            },
        }
    )
    invalid_unsigned_row = dict(invalid_row)
    invalid_unsigned_row.pop("row_sha256")
    invalid_row["row_sha256"] = _canonical_sha(
        invalid_unsigned_row,
        namespace=STRUCTURAL_COST_ROW_SCHEMA,
    )
    invalid_model["row_catalog_sha256"] = _canonical_sha(
        [row["row_sha256"] for row in invalid_model["rows"]],
        namespace="task035e.structural-cost-row-catalog.v1",
    )
    invalid_unsigned_model = dict(invalid_model)
    invalid_unsigned_model.pop("model_sha256")
    invalid_model["model_sha256"] = _canonical_sha(
        invalid_unsigned_model,
        namespace=STRUCTURAL_COST_MODEL_SCHEMA,
    )
    with pytest.raises(
        adapter.CellwiseAuthorityError,
        match="ineligible cost differs",
    ):
        adapter.validate_structural_cost_model(
            invalid_model,
            action_kind="p-up",
            dwr_rows={
                row["target_id"]: row
                for row in evidence["partition"]["rows"]
            },
        )

    model_rows = [dict(row) for row in model["rows"]]
    model_rows[0]["apportioned_cost"] = dict(
        model_rows[0]["apportioned_cost"]
    )
    model_rows[0]["apportioned_cost"]["estimated_added_rows"] += 1
    model["rows"] = model_rows
    model_unsigned = dict(model)
    model_unsigned.pop("model_sha256")
    model["model_sha256"] = _canonical_sha(
        model_unsigned,
        namespace=STRUCTURAL_COST_MODEL_SCHEMA,
    )
    authority["structural_cost_model"] = model
    unsigned = dict(authority)
    unsigned.pop("authority_sha256")
    authority["authority_sha256"] = _canonical_sha(
        unsigned,
        namespace=CELLWISE_DWR_AUTHORITY_SCHEMA,
    )
    path = tmp_path / "tampered-authority.json"
    sha = _write_private(path, authority)
    with pytest.raises(GoalMarkingError, match="structural cost row"):
        produce_goal_marking(
            current_plan_path=plan_path,
            current_plan_file_sha256=plan_sha,
            dwr_authority_path=path,
            dwr_authority_file_sha256=sha,
            source_sha=_SOURCE_SHA,
            action_kind="p-up",
            output_path=tmp_path / "must-not-exist.json",
        )


def test_private_bound_inputs_and_immutable_output_fail_closed(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "input.json"
    sha = _write_private(input_path, {"value": 1})
    loaded, resolved, observed = adapter._load_bound_private_json(
        input_path,
        sha,
        label="fixture input",
    )
    assert loaded == {"value": 1}
    assert resolved == input_path.resolve()
    assert observed == sha
    input_path.chmod(0o644)
    with pytest.raises(
        adapter.CellwiseAuthorityError,
        match="mode-0600",
    ):
        adapter._load_bound_private_json(
            input_path,
            sha,
            label="fixture input",
        )
    forbidden = tmp_path / "hidden_auditor" / "input.json"
    forbidden.parent.mkdir()
    _write_private(forbidden, {"value": 1})
    with pytest.raises(
        adapter.CellwiseAuthorityError,
        match="forbidden layer",
    ):
        adapter._load_bound_private_json(
            forbidden,
            _file_sha(forbidden),
            label="fixture input",
        )
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"value":1,"value":2}\n', encoding="utf-8")
    duplicate.chmod(0o600)
    with pytest.raises(
        adapter.CellwiseAuthorityError,
        match="duplicate",
    ):
        adapter._load_bound_private_json(
            duplicate,
            _file_sha(duplicate),
            label="fixture input",
        )
    output = tmp_path / "immutable.json"
    output.write_text("keep", encoding="utf-8")
    with pytest.raises(FileExistsError, match="overwrite"):
        write_cellwise_authority(
            output,
            {
                "status": "cellwise_authority_controlled_negative",
                "classification": "fixture",
                "pass": False,
                "payload_sha256": "0" * 64,
            },
        )
    assert output.read_text(encoding="utf-8") == "keep"
