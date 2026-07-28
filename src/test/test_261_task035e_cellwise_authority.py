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
        "payload": {"fixture": "candidate-output"},
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
        output_role="current",
        structural_inventory=current_inventory,
    )
    shadow = SimpleNamespace(
        **{
            **common,
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
    zero_goals = GoalVector.from_mapping(
        {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    )
    monkeypatch.setattr(
        adapter,
        "goal_vector_from_candidate_output",
        lambda _payload: zero_goals,
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
    zero_goals = GoalVector.from_mapping(
        {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    )
    monkeypatch.setattr(
        adapter,
        "goal_vector_from_candidate_output",
        lambda _payload: zero_goals,
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
