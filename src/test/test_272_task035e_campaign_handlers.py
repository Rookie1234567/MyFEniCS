from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

import pytest

from benchmarks import task035e_campaign_handlers as handlers
from benchmarks import task035e_blind_cycle as blind_cycle
from benchmarks import task035e_shadow_bundle as shadow_bundle
import benchmarks.task035e_cellwise_authority as cellwise_adapter
from benchmarks.task035e_blind_campaign import (
    AttemptHandle,
    CampaignEvidenceError,
    CampaignStage,
    CommandExecutionReceipt,
    StageArtifactBinding,
    StageExecutionContext,
)
from benchmarks.task035e_candidate_output import (
    CandidateWatchdogInput,
    adapt_candidate_output,
)
from benchmarks.task035e_campaign_stages import (
    ContractStagePreparer,
    formal_stage_contracts,
)
from src.adaptivity.task035e_initial_space import (
    build_task035e_initial_space_plan,
)
from src.adaptivity.task035e_plan_transition import (
    canonical_solver_content_sha256,
)
from src.common.config_3d import target_stage4_config
from src.adaptivity.blind_controller import (
    FORMAL_GOAL_IDS,
    GoalVector,
    ShadowCost,
    build_unmeasured_h_level3_saturation_authority,
    build_unmeasured_p6_saturation_authority,
    build_shadow_action,
)
from src.test.test_241_task035e_actual_shadow_bundle import (
    _fixture as _actual_shadow_fixture,
)
from src.test.test_258_task035e_blind_bindings import (
    _cycle_fixture,
    _cycle_zero_record,
    _snapshot,
)
from src.test.test_261_task035e_cellwise_authority import (
    _fixture as _cellwise_fixture,
)
from src.test.test_263_task035e_internal_gate_authority import (
    _fixture as _internal_gate_fixture,
)
from src.test.test_264_task035e_trial_metadata import (
    _bundle as _initial_bundle,
)


SOURCE_SHA = "1234567890abcdef1234567890abcdef12345678"
ABI_SHA256 = "a" * 64


def _private_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            value,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n",
        encoding="ascii",
    )
    path.chmod(0o600)
    return path


def _binding(role: str, path: Path) -> StageArtifactBinding:
    return StageArtifactBinding.from_file(role, path)


def _settings(tmp_path: Path) -> handlers.FormalCampaignSettings:
    return handlers.FormalCampaignSettings(
        python_executable=Path(sys.executable),
        artifact_root=tmp_path / "artifacts",
        tensor_cache_directory=tmp_path / "tensor-cache",
        timeout_seconds=60.0,
    )


def _context(
    tmp_path: Path,
    *,
    stage_name: str,
    artifacts: tuple[StageArtifactBinding, ...],
    input_plan_sha256: str = "b" * 64,
    source_sha: str = SOURCE_SHA,
    trial_id: str = "task035e-blind-path-a",
    cycle_index: int = 0,
) -> StageExecutionContext:
    return StageExecutionContext(
        campaign_root=tmp_path,
        stage=CampaignStage(
            ordinal=0,
            path_id="A",
            cycle_index=cycle_index,
            stage_name=stage_name,
            heavy=False,
            predecessor_stage_id=None,
        ),
        source_sha=source_sha,
        abi_sha256=ABI_SHA256,
        trial_id=trial_id,
        nominal_h_nm=20.0,
        input_plan_sha256=input_plan_sha256,
        input_artifacts=artifacts,
    )


def _attempt(
    tmp_path: Path,
    context: StageExecutionContext,
) -> AttemptHandle:
    path = tmp_path / "attempt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.mkdir(mode=0o700)
    return AttemptHandle(
        context=context,
        attempt_number=1,
        attempt_dir=path,
    )


def _receipt(
    attempt: AttemptHandle,
    *,
    record_path: Path,
    exit_code: int = 0,
) -> CommandExecutionReceipt:
    stdout = _private_json(
        attempt.attempt_dir / "synthetic.stdout",
        {"status": "synthetic_no_pde"},
    )
    stderr = _private_json(
        attempt.attempt_dir / "synthetic.stderr",
        {"status": "empty"},
    )
    receipt_path = _private_json(
        attempt.attempt_dir / "synthetic-receipt.json",
        {"status": "synthetic_command_receipt"},
    )
    return CommandExecutionReceipt(
        invocation_index=0,
        argv_sha256="1" * 64,
        pid=1,
        linux_start_ticks="1",
        exit_code=exit_code,
        stdout_path=stdout,
        stdout_sha256=hashlib.sha256(stdout.read_bytes()).hexdigest(),
        stderr_path=stderr,
        stderr_sha256=hashlib.sha256(stderr.read_bytes()).hexdigest(),
        watchdog_record_path=record_path,
        watchdog_record_sha256=hashlib.sha256(
            record_path.read_bytes()
        ).hexdigest(),
        receipt_path=receipt_path,
        receipt_file_sha256=hashlib.sha256(
            receipt_path.read_bytes()
        ).hexdigest(),
    )


def _by_role(result: Any) -> dict[str, StageArtifactBinding]:
    return {artifact.role: artifact for artifact in result.artifacts}


def _actual_bundle_with_one_saturation_only_lane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    measured_lane: str,
) -> tuple[Any, dict[str, Any], Any]:
    _request, fixture = _actual_shadow_fixture(tmp_path / "fixture")
    request = fixture["request"]
    current = fixture["current"]
    current.plan_path.chmod(0o600)
    current_record_path = Path(request["current_record"]["path"])
    current_record_path.chmod(0o600)
    skipped_lane = "h" if measured_lane == "p" else "p"
    selected = request[f"{measured_lane}_actions"][0]
    bindings = [
        _binding("current_watchdog_record", current_record_path),
    ]
    for role, source_role in (
        ("selected_transition_action", "transition_action"),
        ("goal_marking", "goal_marking"),
        ("verification_prediction", "verification_prediction"),
        ("selected_shadow_watchdog_record", "shadow_record"),
        ("selected_live_dwr_evidence", "dwr_evidence"),
    ):
        path = Path(selected[source_role]["path"])
        path.chmod(0o600)
        bindings.append(
            _binding(f"{measured_lane}_{role}", path)
        )
    skip_path = _private_json(
        tmp_path / f"{skipped_lane}-selected-skip.json",
        {
            "schema_version": handlers.LEGAL_SKIP_SCHEMA,
            "status": "legal_no_target_skip",
            "pass": True,
        },
    )
    bindings.append(
        _binding(
            f"{skipped_lane}_selected_transition_action",
            skip_path,
        )
    )

    if skipped_lane == "h":
        authority = build_unmeasured_h_level3_saturation_authority(
            level_two_target_ids=("cell:r0:l2:i0:j0:k0",),
            periodic_orbit_ids=("h3-orbit-000000-abc123",),
            orbit_catalog_sha256="d" * 64,
            current_plan_file_sha256=current.plan_file_sha256,
            current_mesh_forest_sha256=(
                current.forest_leaf_catalog_sha256
            ),
            current_degree_map_sha256=(
                current.cell_degree_plan_sha256
            ),
        )
        monkeypatch.setattr(
            shadow_bundle,
            "_current_h_level3_saturation_authority",
            lambda observed: (
                authority
                if observed.plan_file_sha256
                == current.plan_file_sha256
                else pytest.fail("unexpected current plan"),
                False,
            ),
        )
    else:
        authority = build_unmeasured_p6_saturation_authority(
            p6_target_ids=("cell:r0:l1:i0:j0:k0",),
            current_plan_file_sha256=current.plan_file_sha256,
            current_mesh_forest_sha256=(
                current.forest_leaf_catalog_sha256
            ),
            current_degree_map_sha256=(
                current.cell_degree_plan_sha256
            ),
        )
        monkeypatch.setattr(
            shadow_bundle,
            "_current_p6_saturation_authority",
            lambda observed: (
                authority
                if observed.plan_file_sha256
                == current.plan_file_sha256
                else pytest.fail("unexpected current plan"),
                False,
            ),
        )

    context = _context(
        tmp_path,
        stage_name="shadow_bundle",
        artifacts=tuple(bindings),
        input_plan_sha256=current.plan_file_sha256,
        source_sha=current.source_sha,
        trial_id=current.trial_id,
        cycle_index=current.cycle_index,
    )
    attempt = _attempt(tmp_path, context)
    result = handlers.RepositoryFormalStageHandlers(
        _settings(tmp_path)
    ).shadow_bundle(context, attempt).execute(attempt, ())
    bundle = json.loads(
        _by_role(result)["shadow_bundle"].path.read_text(
            encoding="ascii"
        )
    )
    return result, bundle["payload"], current


def _neutralize_shadow_bundle(path: Path, current: Any) -> None:
    outer = json.loads(path.read_text(encoding="utf-8"))
    payload = outer["payload"]
    goals = blind_cycle.goal_vector_from_candidate_output(current.payload)
    neutral_values = dict(goals.by_id)
    zero_dwr = {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    for row in (*payload["p_actions"], *payload["h_actions"]):
        cost = ShadowCost(
            *(
                row["cost"][name]
                for name in ShadowCost.__dataclass_fields__
            )
        )
        rebuilt = build_shadow_action(
            action_id=row["action_id"],
            kind=row["kind"],
            target_ids=tuple(row["target_ids"]),
            current=goals,
            shadow=GoalVector.from_mapping(neutral_values),
            signed_dwr_delta=zero_dwr,
            cost=cost,
            sign_consistent=True,
            transition_action_sha256=row[
                "transition_action_sha256"
            ],
            transition_action_file_sha256=row[
                "transition_action_file_sha256"
            ],
            transition_action_identity_sha256=row[
                "transition_action_identity_sha256"
            ],
            next_mesh_forest_sha256=row[
                "next_mesh_forest_sha256"
            ],
            next_degree_map_sha256=row["next_degree_map_sha256"],
            actual_added_leaf_count=row["actual_added_leaf_count"],
        )
        row["shadow_goals"] = neutral_values
        row["signed_dwr_delta"] = zero_dwr
        row["sign_consistent"] = True
        row["action_sha256"] = rebuilt.action_sha256
    outer["sha256"] = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()
    _private_json(path, outer)


def test_repository_inventory_covers_every_formal_stage(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    mapping = handlers.repository_formal_stage_handlers(settings)
    expected = {
        contract.stage_name for contract in formal_stage_contracts()
    }

    assert set(mapping) == expected
    assert settings.python_executable == Path(sys.executable)
    assert settings.python_executable != Path(sys.executable).resolve()
    assert isinstance(
        handlers.RepositoryFormalStageHandlers(
            _settings(tmp_path)
        ).preparer(),
        ContractStagePreparer,
    )


def test_initial_plan_handler_runs_actual_metadata_producer(
    tmp_path: Path,
) -> None:
    plan, authority, config = _initial_bundle(tmp_path, path_id="A")
    plan_binding = _binding("current_plan", plan)
    context = _context(
        tmp_path,
        stage_name="initial_plan",
        artifacts=(
            plan_binding,
            _binding("initial_space_authority", authority),
            _binding("qualified_solver_config", config),
        ),
        input_plan_sha256=plan_binding.sha256,
        source_sha="a" * 40,
    )
    attempt = _attempt(tmp_path, context)

    prepared = handlers.RepositoryFormalStageHandlers(
        _settings(tmp_path)
    ).initial_plan(context, attempt)
    result = prepared.execute(attempt, ())
    metadata = json.loads(
        result.artifacts[0].path.read_text(encoding="ascii")
    )

    assert result.classification == "trial_metadata_qualified"
    assert metadata["source_sha"] == context.source_sha
    assert metadata["trial_id"] == context.trial_id
    assert metadata["initial_plan_file_sha256"] == plan_binding.sha256


def test_current_handler_prepares_mpi8_venv_argv_and_finalizes_fixture(
    tmp_path: Path,
) -> None:
    source_record = _cycle_zero_record(tmp_path / "producer-fixture")
    source_record_payload = json.loads(
        source_record.path.read_text(encoding="utf-8")
    )
    current = adapt_candidate_output(source_record)
    plan = _binding("current_plan", current.plan_path)
    context = _context(
        tmp_path,
        stage_name="current_solve",
        artifacts=(plan,),
        input_plan_sha256=plan.sha256,
        source_sha=current.source_sha,
        trial_id=current.trial_id,
        cycle_index=current.cycle_index,
    )
    attempt = _attempt(tmp_path, context)
    implementation = handlers.RepositoryFormalStageHandlers(
        _settings(tmp_path)
    )
    prepared = implementation.current_solve(context, attempt)

    assert prepared.argv is not None
    assert prepared.argv[0] == sys.executable
    mpi_index = prepared.argv.index("--mpi-size")
    assert prepared.argv[mpi_index + 1] == "8"
    record_index = prepared.argv.index("--record")
    record_path = _private_json(
        Path(prepared.argv[record_index + 1]),
        source_record_payload,
    )
    run_dir = Path(
        source_record_payload["raw_evidence"]["run_directory"]
    )
    generated_snapshot = _snapshot(
        run_dir,
        current=current,
        candidate=dict(current.payload),
    )
    live_snapshot_dir = run_dir / "task035e_current_snapshot"
    generated_snapshot.parent.rename(live_snapshot_dir)

    result = prepared.execute(
        attempt,
        (_receipt(attempt, record_path=record_path),),
    )

    assert result.classification == "current_candidate_solve_pass"
    assert {artifact.role for artifact in result.artifacts} == {
        "current_watchdog_record",
        "current_candidate_output",
        "current_snapshot",
    }


def test_current_handler_rejects_record_from_another_source(
    tmp_path: Path,
) -> None:
    source_record = _cycle_zero_record(tmp_path / "producer-fixture")
    current = adapt_candidate_output(source_record)
    plan = _binding("current_plan", current.plan_path)
    context = _context(
        tmp_path,
        stage_name="current_solve",
        artifacts=(plan,),
        input_plan_sha256=plan.sha256,
        source_sha="f" * 40,
        trial_id=current.trial_id,
    )
    attempt = _attempt(tmp_path, context)
    prepared = handlers.RepositoryFormalStageHandlers(
        _settings(tmp_path)
    ).current_solve(context, attempt)
    assert prepared.argv is not None
    record_index = prepared.argv.index("--record")
    record_path = _private_json(
        Path(prepared.argv[record_index + 1]),
        json.loads(source_record.path.read_text(encoding="utf-8")),
    )

    with pytest.raises(
        CampaignEvidenceError,
        match="identity differs",
    ):
        prepared.execute(
            attempt,
            (_receipt(attempt, record_path=record_path),),
        )


def test_discovery_producer_and_shadow_argv_cover_both_lanes(
    tmp_path: Path,
) -> None:
    plan, _authority, _config = _initial_bundle(tmp_path, path_id="A")
    plan_binding = _binding("current_plan", plan)
    context = _context(
        tmp_path,
        stage_name="shadow_target_discovery",
        artifacts=(plan_binding,),
        input_plan_sha256=plan_binding.sha256,
        source_sha="a" * 40,
    )
    attempt = _attempt(tmp_path, context)
    implementation = handlers.RepositoryFormalStageHandlers(
        _settings(tmp_path)
    )
    result = implementation.shadow_target_discovery(
        context,
        attempt,
    ).execute(attempt, ())
    discovered = {artifact.role: artifact for artifact in result.artifacts}

    assert set(discovered) == {
        "p_discovery_targets",
        "p_discovery_transition_action",
        "p_discovery_plan",
        "h_discovery_targets",
        "h_discovery_transition_action",
        "h_discovery_plan",
    }
    p_targets = json.loads(
        discovered["p_discovery_targets"].path.read_text(encoding="ascii")
    )
    h_targets = json.loads(
        discovered["h_discovery_targets"].path.read_text(encoding="ascii")
    )
    assert p_targets["eligible_target_count"] == 160
    assert p_targets["window_selected_target_count"] == 32
    assert 32 <= p_targets["selected_target_count"] <= 56
    assert h_targets["eligible_target_count"] == 160
    assert h_targets["window_selected_target_count"] == 4
    assert 1 <= h_targets["selected_target_count"] <= 4
    assert (
        p_targets["selection_audit"]["window"][
            "hidden_reference_consumed"
        ]
        is False
    )
    assert (
        p_targets["selection_audit"]["p_degree_jump_closure"]["pass"]
        is True
    )
    assert (
        h_targets["selection_audit"]["window"]["accuracy_credit"]
        is False
    )
    h_budget = h_targets["selection_audit"][
        "h_balance_closure_budget"
    ]
    assert h_budget["pass"] is True
    assert h_budget["final_net_added_leaf_count"] <= 56
    assert h_budget["hidden_reference_consumed"] is False
    assert h_budget["solved_field_consumed"] is False
    snapshot = _private_json(
        tmp_path / "current-snapshot.json",
        {"status": "synthetic_prepare_only"},
    )
    current_record = _private_json(
        tmp_path / "current-watchdog.json",
        {"status": "synthetic_prepare_only"},
    )
    for lane in ("p", "h"):
        lane_context = _context(
            tmp_path / lane,
            stage_name=f"{lane}_shadow_discovery",
            artifacts=(
                discovered[f"{lane}_discovery_targets"],
                discovered[f"{lane}_discovery_transition_action"],
                discovered[f"{lane}_discovery_plan"],
                _binding("current_snapshot", snapshot),
                _binding("current_watchdog_record", current_record),
            ),
            input_plan_sha256=plan_binding.sha256,
            source_sha="a" * 40,
        )
        lane_attempt = _attempt(tmp_path / lane, lane_context)
        prepared = getattr(
            implementation,
            f"{lane}_shadow_discovery",
        )(lane_context, lane_attempt)
        assert prepared.argv is not None
        role_index = prepared.argv.index(
            "--task035e-blind-output-role"
        )
        assert prepared.argv[role_index + 1] == f"{lane}-shadow"
        assert prepared.argv[prepared.argv.index("--mpi-size") + 1] == "8"
        assert prepared.allow_controlled_resource_stop is True


def test_shadow_handler_classifies_hash_bound_11_gib_stop(
    tmp_path: Path,
) -> None:
    plan, _authority, _config = _initial_bundle(tmp_path, path_id="A")
    plan_binding = _binding("current_plan", plan)
    context = _context(
        tmp_path,
        stage_name="shadow_target_discovery",
        artifacts=(plan_binding,),
        input_plan_sha256=plan_binding.sha256,
        source_sha="a" * 40,
    )
    implementation = handlers.RepositoryFormalStageHandlers(
        _settings(tmp_path)
    )
    discovery_attempt = _attempt(tmp_path, context)
    discovery = implementation.shadow_target_discovery(
        context,
        discovery_attempt,
    ).execute(discovery_attempt, ())
    found = _by_role(discovery)
    snapshot = _private_json(
        tmp_path / "current-snapshot.json",
        {"status": "synthetic_prepare_only"},
    )
    current_record = _private_json(
        tmp_path / "current-watchdog.json",
        {"status": "synthetic_prepare_only"},
    )
    lane_context = _context(
        tmp_path / "p",
        stage_name="p_shadow_discovery",
        artifacts=(
            found["p_discovery_targets"],
            found["p_discovery_transition_action"],
            found["p_discovery_plan"],
            _binding("current_snapshot", snapshot),
            _binding("current_watchdog_record", current_record),
        ),
        input_plan_sha256=plan_binding.sha256,
        source_sha="a" * 40,
    )
    attempt = _attempt(tmp_path / "p", lane_context)
    prepared = implementation.p_shadow_discovery(
        lane_context,
        attempt,
    )
    shadow_plan = found["p_discovery_plan"]
    record = _private_json(
        attempt.attempt_dir / "p-shadow-watchdog.json",
        {
            "status": "controlled_resource_stop",
            "controlled_resource_stop": True,
            "terminated_for_memory": True,
            "terminated_for_timeout": False,
            "terminated_for_authority_unreadable": False,
            "controlled_resource_stop_reason": (
                "effective_job_cap_reached"
            ),
            "no_swap": True,
            "task035e_blind_candidate": None,
            "source": {
                "commit_sha": "a" * 40,
                "head_after_sha": "a" * 40,
                "stable_and_clean_after": True,
                "tracked_source_dirty": False,
            },
            "task035e_blind_candidate_launch_gate": {
                "selected": True,
                "plan": {
                    "pass": True,
                    "observed_file_sha256": shadow_plan.sha256,
                },
                "live_resource_gate": {
                    "controlled_resource_stop": True,
                    "zero_swap_every_sample": True,
                    "effective_job_cap_respected": False,
                    "stop_reason": "effective_job_cap_reached",
                },
            },
            "resource_policy": {"termination_gib": 11.0},
            "resource_authority": {
                "combined_memory_swap_authority_gib": 11.01,
            },
        },
    )
    result = prepared.execute(
        attempt,
        (_receipt(attempt, record_path=record, exit_code=2),),
    )
    assert result.status == "controlled_negative"
    assert result.lane_decision == "controlled_negative"
    blocker = json.loads(
        _by_role(result)["stage_blocker"].path.read_text(encoding="ascii")
    )
    assert blocker["code"] == "p-shadow_controlled_resource_stop"
    assert blocker["inputs"]["no_swap"] is True
    assert blocker["inputs"]["accuracy_credit"] is False


def test_actual_selected_shadow_fixture_runs_repository_bundle_handler(
    tmp_path: Path,
) -> None:
    _request, fixture = _actual_shadow_fixture(tmp_path / "fixture")
    request = fixture["request"]
    current = fixture["current"]
    current.plan_path.chmod(0o600)
    for lane in ("p", "h"):
        for bound in request[f"{lane}_actions"][0].values():
            Path(bound["path"]).chmod(0o600)
    Path(request["current_record"]["path"]).chmod(0o600)
    bindings = [
        _binding(
            "current_watchdog_record",
            Path(request["current_record"]["path"]),
        )
    ]
    for lane in ("p", "h"):
        row = request[f"{lane}_actions"][0]
        bindings.extend(
            (
                _binding(
                    f"{lane}_selected_transition_action",
                    Path(row["transition_action"]["path"]),
                ),
                _binding(
                    f"{lane}_goal_marking",
                    Path(row["goal_marking"]["path"]),
                ),
                _binding(
                    f"{lane}_verification_prediction",
                    Path(row["verification_prediction"]["path"]),
                ),
                _binding(
                    f"{lane}_selected_shadow_watchdog_record",
                    Path(row["shadow_record"]["path"]),
                ),
                _binding(
                    f"{lane}_selected_live_dwr_evidence",
                    Path(row["dwr_evidence"]["path"]),
                ),
            )
        )
    context = _context(
        tmp_path,
        stage_name="shadow_bundle",
        artifacts=tuple(bindings),
        input_plan_sha256=current.plan_file_sha256,
        source_sha=current.source_sha,
        trial_id=current.trial_id,
        cycle_index=current.cycle_index,
    )
    attempt = _attempt(tmp_path, context)

    result = handlers.RepositoryFormalStageHandlers(
        _settings(tmp_path)
    ).shadow_bundle(context, attempt).execute(attempt, ())
    by_role = {artifact.role: artifact for artifact in result.artifacts}
    bundle = json.loads(
        by_role["shadow_bundle"].path.read_text(encoding="ascii")
    )

    assert result.classification == "actual_selected_shadow_bundle_pass"
    assert len(bundle["payload"]["p_actions"]) == 1
    assert len(bundle["payload"]["h_actions"]) == 1
    assert bundle["payload"]["source_sha"] == current.source_sha
    catalog = blind_cycle._shadow_catalog(
        bundle["payload"],
        current=blind_cycle.goal_vector_from_candidate_output(
            current.payload
        ),
        source_sha=current.source_sha,
        trial_id=current.trial_id,
        cycle_index=current.cycle_index,
        mesh_forest_sha256=current.forest_leaf_catalog_sha256,
        degree_map_sha256=current.cell_degree_plan_sha256,
        plan_file_sha256=current.plan_file_sha256,
        complete_output_sha256=current.output_sha256,
    )
    assert catalog.h_level3_saturation.level_two_target_count == 0
    assert catalog.h_level3_saturation.status == "measured_pass"
    assert (
        catalog.h_level3_saturation.evidence_kind
        == "zero_level2_targets_vacuous"
    )
    assert catalog.h_level3_saturation.freeze_passed is True
    assert catalog.p6_saturation.p6_target_count == 0
    assert catalog.p6_saturation.freeze_passed is True


def test_fixture_shadow_evidence_runs_cellwise_marking_and_selected_argv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "fixture").mkdir()
    (
        _plan,
        _state,
        plan_path,
        plan_sha,
        current,
        shadow,
        evidence,
        live_path,
        _live_sha,
    ) = _cellwise_fixture(tmp_path / "fixture")

    def candidate(*_args: Any, role: str, **_kwargs: Any) -> Any:
        selected = current if role == "current" else shadow
        return selected, selected.record_sha256, selected.output_sha256

    monkeypatch.setattr(cellwise_adapter, "_candidate", candidate)
    monkeypatch.setattr(
        cellwise_adapter,
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
        cellwise_adapter,
        "goal_vector_from_candidate_output",
        lambda _payload: zero_goals,
    )
    current_record = _private_json(tmp_path / "current-record.json", {})
    current_output = _private_json(tmp_path / "current-output.json", {})
    p_record = _private_json(tmp_path / "p-record.json", {})
    p_output = _private_json(tmp_path / "p-output.json", {})
    h_skip = _private_json(
        tmp_path / "h-live-skip.json",
        {
            "schema_version": handlers.LEGAL_SKIP_SCHEMA,
            "status": "legal_no_target_skip",
            "pass": True,
        },
    )
    artifacts = [
        _binding("current_watchdog_record", current_record),
        _binding("current_candidate_output", current_output),
        _binding("p_shadow_watchdog_record", p_record),
        _binding("p_shadow_candidate_output", p_output),
        _binding("p_live_dwr_evidence", live_path),
        _binding("h_live_dwr_evidence", h_skip),
    ]
    implementation = handlers.RepositoryFormalStageHandlers(
        _settings(tmp_path)
    )
    cellwise_context = _context(
        tmp_path / "cellwise",
        stage_name="cellwise_partition",
        artifacts=tuple(artifacts),
        input_plan_sha256=plan_sha,
        source_sha=current.source_sha,
        trial_id=current.trial_id,
        cycle_index=current.cycle_index,
    )
    cellwise_attempt = _attempt(tmp_path / "cellwise", cellwise_context)
    cellwise_result = implementation.cellwise_partition(
        cellwise_context,
        cellwise_attempt,
    ).execute(cellwise_attempt, ())
    cellwise = _by_role(cellwise_result)

    marking_context = _context(
        tmp_path / "marking",
        stage_name="goal_marking",
        artifacts=(
            _binding("current_plan", plan_path),
            cellwise["p_cellwise_authority"],
            cellwise["h_cellwise_authority"],
        ),
        input_plan_sha256=plan_sha,
        source_sha=current.source_sha,
        trial_id=current.trial_id,
        cycle_index=current.cycle_index,
    )
    marking_attempt = _attempt(tmp_path / "marking", marking_context)
    marking_result = implementation.goal_marking(
        marking_context,
        marking_attempt,
    ).execute(marking_attempt, ())
    marked = _by_role(marking_result)
    snapshot = _private_json(
        tmp_path / "selected-snapshot.json",
        {"status": "synthetic_prepare_only"},
    )

    assert marking_result.status == "completed"
    for lane in ("p", "h"):
        verification_context = _context(
            tmp_path / f"{lane}-selected",
            stage_name=f"{lane}_selected_shadow_verification",
            artifacts=(
                marked[f"{lane}_selected_transition_action"],
                marked[f"{lane}_selected_plan"],
                _binding("current_snapshot", snapshot),
                artifacts[0],
            ),
            input_plan_sha256=plan_sha,
            source_sha=current.source_sha,
            trial_id=current.trial_id,
            cycle_index=current.cycle_index,
        )
        verification_attempt = _attempt(
            tmp_path / f"{lane}-selected",
            verification_context,
        )
        prepared = getattr(
            implementation,
            f"{lane}_selected_shadow_verification",
        )(verification_context, verification_attempt)
        if lane == "p":
            assert prepared.argv is not None
            assert prepared.argv[
                prepared.argv.index("--task035e-blind-output-role") + 1
            ] == "p-shadow"
        else:
            assert prepared.argv is None
            skipped = prepared.execute(verification_attempt, ())
            assert skipped.classification == (
                "legal_no_selected_action_skip"
            )


def test_internal_deferred_handler_runs_actual_authority_producer(
    tmp_path: Path,
) -> None:
    fixture = _internal_gate_fixture(tmp_path / "fixture")
    current = adapt_candidate_output(
        CandidateWatchdogInput(
            fixture["candidate_record"].path,
            fixture["candidate_record"].sha256,
        )
    )
    context = _context(
        tmp_path,
        stage_name="internal_gate_deferred_or_final",
        artifacts=(
            _binding(
                "current_watchdog_record",
                fixture["candidate_record"].path,
            ),
            _binding(
                "current_candidate_output",
                fixture["candidate_output"].path,
            ),
            _binding("current_plan", fixture["current_plan"].path),
            _binding(
                "current_snapshot",
                fixture["current_snapshot"].path,
            ),
        ),
        input_plan_sha256=current.plan_file_sha256,
        source_sha=current.source_sha,
        trial_id=current.trial_id,
        cycle_index=current.cycle_index,
    )
    attempt = _attempt(tmp_path, context)

    result = handlers.RepositoryFormalStageHandlers(
        _settings(tmp_path)
    ).internal_gate_deferred_or_final(
        context,
        attempt,
    ).execute(attempt, ())

    assert result.status == "completed"
    assert result.classification == "internal_gate_deferred"
    authority = json.loads(
        result.artifacts[0].path.read_text(encoding="ascii")
    )
    assert authority["classification"] == "deferred_intermediate_cycle"


def test_light_late_chain_advances_controller_and_publishes_next_cycle(
    tmp_path: Path,
) -> None:
    inputs = _cycle_fixture(tmp_path / "fixture")
    current = inputs["current"]
    _neutralize_shadow_bundle(inputs["shadow_path"], current)
    implementation = handlers.RepositoryFormalStageHandlers(
        _settings(tmp_path)
    )
    common = {
        "current_watchdog_record": _binding(
            "current_watchdog_record",
            inputs["current_record"].path,
        ),
        "current_candidate_output": _binding(
            "current_candidate_output",
            inputs["candidate_path"],
        ),
        "current_snapshot": _binding(
            "current_snapshot",
            inputs["snapshot_path"],
        ),
        "current_plan": _binding("current_plan", current.plan_path),
        "trial_metadata": _binding(
            "trial_metadata",
            inputs["trial_path"],
        ),
        "shadow_bundle": _binding(
            "shadow_bundle",
            inputs["shadow_path"],
        ),
    }

    gate = _binding(
        "internal_gate_authority",
        inputs["gates_path"],
    )

    isolation_context = _context(
        tmp_path / "isolation",
        stage_name="isolation_audit",
        artifacts=tuple(
            common[name]
            for name in (
                "trial_metadata",
                "current_watchdog_record",
                "current_candidate_output",
                "current_snapshot",
                "shadow_bundle",
            )
        ),
        input_plan_sha256=current.plan_file_sha256,
        source_sha=current.source_sha,
        trial_id=current.trial_id,
        cycle_index=current.cycle_index,
    )
    isolation_attempt = _attempt(
        tmp_path / "isolation",
        isolation_context,
    )
    isolation_result = implementation.isolation_audit(
        isolation_context,
        isolation_attempt,
    ).execute(isolation_attempt, ())
    assert isolation_result.status == "completed"
    isolation = _by_role(isolation_result)["isolation_report"]

    binding_context = _context(
        tmp_path / "binding",
        stage_name="cycle_binding",
        artifacts=(
            common["trial_metadata"],
            common["current_watchdog_record"],
            common["current_candidate_output"],
            common["current_snapshot"],
            common["shadow_bundle"],
            gate,
            isolation,
        ),
        input_plan_sha256=current.plan_file_sha256,
        source_sha=current.source_sha,
        trial_id=current.trial_id,
        cycle_index=current.cycle_index,
    )
    binding_attempt = _attempt(tmp_path / "binding", binding_context)
    binding_result = implementation.cycle_binding(
        binding_context,
        binding_attempt,
    ).execute(binding_attempt, ())
    binding = _by_role(binding_result)["cycle_binding"]

    advance_context = _context(
        tmp_path / "advance",
        stage_name="cycle_advance",
        artifacts=(
            common["current_candidate_output"],
            common["shadow_bundle"],
            binding,
            isolation,
        ),
        input_plan_sha256=current.plan_file_sha256,
        source_sha=current.source_sha,
        trial_id=current.trial_id,
        cycle_index=current.cycle_index,
    )
    advance_attempt = _attempt(tmp_path / "advance", advance_context)
    advance_result = implementation.cycle_advance(
        advance_context,
        advance_attempt,
    ).execute(advance_attempt, ())
    advanced = _by_role(advance_result)
    selection = json.loads(
        advanced["selected_action_binding_or_pkeep"].path.read_text(
            encoding="ascii"
        )
    )
    assert advance_result.status == "completed"
    assert selection["selected_action_ids"] == []
    assert advance_result.p6_saturation == "verified"
    assert advance_result.h_level3_saturation == "verified"
    freeze_intent = json.loads(
        advanced["freeze_intent"].path.read_text(encoding="ascii")
    )
    assert freeze_intent["p6_saturation_freeze_passed"] is True
    assert (
        freeze_intent["h_level3_saturation_freeze_passed"] is True
    )

    skips = []
    for role in (
        "p_goal_marking",
        "p_selected_transition_action",
        "p_verification_prediction",
        "h_goal_marking",
        "h_selected_transition_action",
        "h_verification_prediction",
    ):
        skips.append(
            _binding(
                role,
                _private_json(
                    tmp_path / "transition-inputs" / f"{role}.json",
                    {
                        "schema_version": handlers.LEGAL_SKIP_SCHEMA,
                        "status": "legal_no_target_skip",
                        "pass": True,
                    },
                ),
            )
        )
    transition_context = _context(
        tmp_path / "transition",
        stage_name="transition_or_pkeep",
        artifacts=(
            common["current_plan"],
            advanced["trial_state"],
            advanced["selected_action_binding_or_pkeep"],
            *skips,
        ),
        input_plan_sha256=current.plan_file_sha256,
        source_sha=current.source_sha,
        trial_id=current.trial_id,
        cycle_index=current.cycle_index,
    )
    transition_attempt = _attempt(
        tmp_path / "transition",
        transition_context,
    )
    transition_result = implementation.transition_or_pkeep(
        transition_context,
        transition_attempt,
    ).execute(transition_attempt, ())

    assert transition_result.classification == (
        "pkeep_transition_published"
    )
    assert transition_result.next_plan_sha256 is not None
    assert _by_role(transition_result)["current_plan"].sha256 == (
        transition_result.next_plan_sha256
    )


def test_nonzero_level2_inventory_flows_to_unknown_h_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, payload, current = (
        _actual_bundle_with_one_saturation_only_lane(
            tmp_path,
            monkeypatch,
            measured_lane="p",
        )
    )
    catalog = blind_cycle._shadow_catalog(
        payload,
        current=blind_cycle.goal_vector_from_candidate_output(
            current.payload
        ),
        source_sha=current.source_sha,
        trial_id=current.trial_id,
        cycle_index=current.cycle_index,
        mesh_forest_sha256=current.forest_leaf_catalog_sha256,
        degree_map_sha256=current.cell_degree_plan_sha256,
        plan_file_sha256=current.plan_file_sha256,
        complete_output_sha256=current.output_sha256,
    )
    authority = catalog.h_level3_saturation

    assert result.status == "completed"
    assert result.classification == "actual_selected_shadow_bundle_pass"
    assert payload["h_actions"] == []
    assert payload["p_actions"]
    assert authority.level_two_target_count > 0
    assert authority.periodic_orbit_count > 0
    assert authority.status == "unknown"
    assert authority.coverage_complete is False
    assert authority.normalized_max is None
    assert authority.freeze_passed is False
    assert (
        authority.evidence_kind
        == "no_independent_global_level3_evidence"
    )


def test_nonzero_p6_inventory_without_endpoint_is_unknown(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result, payload, current = (
        _actual_bundle_with_one_saturation_only_lane(
            tmp_path,
            monkeypatch,
            measured_lane="h",
        )
    )
    catalog = blind_cycle._shadow_catalog(
        payload,
        current=blind_cycle.goal_vector_from_candidate_output(
            current.payload
        ),
        source_sha=current.source_sha,
        trial_id=current.trial_id,
        cycle_index=current.cycle_index,
        mesh_forest_sha256=current.forest_leaf_catalog_sha256,
        degree_map_sha256=current.cell_degree_plan_sha256,
        plan_file_sha256=current.plan_file_sha256,
        complete_output_sha256=current.output_sha256,
    )
    authority = catalog.p6_saturation

    assert result.status == "completed"
    assert payload["p_actions"] == []
    assert payload["h_actions"]
    assert authority.p6_target_count > 0
    assert authority.status == "unknown"
    assert authority.coverage_complete is False
    assert authority.normalized_max is None
    assert authority.freeze_passed is False


def test_no_production_selection_publishes_real_pkeep_transition(
    tmp_path: Path,
) -> None:
    initial = build_task035e_initial_space_plan(
        target_stage4_config(degree=6, h_nm=20.0),
        path_id="A",
        source_sha=SOURCE_SHA,
        comm_size=8,
    ).plan_payload()
    plan_path = _private_json(tmp_path / "current-plan.json", initial)
    plan_binding = _binding("current_plan", plan_path)
    selection_path = _private_json(
        tmp_path / "selection.json",
        {
            "schema_version": handlers.SELECTION_SCHEMA,
            "status": "no_production_action",
            "selected_action_ids": [],
        },
    )
    context = _context(
        tmp_path,
        stage_name="transition_or_pkeep",
        artifacts=(
            plan_binding,
            _binding(
                "selected_action_binding_or_pkeep",
                selection_path,
            ),
        ),
        input_plan_sha256=plan_binding.sha256,
    )
    attempt = _attempt(tmp_path, context)

    prepared = handlers.RepositoryFormalStageHandlers(
        _settings(tmp_path)
    ).transition_or_pkeep(context, attempt)
    result = prepared.execute(attempt, ())

    by_role = {artifact.role: artifact for artifact in result.artifacts}
    next_plan = json.loads(
        by_role["current_plan"].path.read_text(encoding="ascii")
    )
    action = json.loads(
        by_role["next_transition_action"].path.read_text(
            encoding="ascii"
        )
    )
    transition_mode = json.loads(
        by_role["previous_transition_mode"].path.read_text(
            encoding="ascii"
        )
    )

    assert result.status == "completed"
    assert result.classification == "pkeep_transition_published"
    assert action["kind"] == "p-keep"
    assert action["canonical_target_ids"] == []
    assert transition_mode["mode"] == "pkeep"
    assert canonical_solver_content_sha256(next_plan) == (
        canonical_solver_content_sha256(initial)
    )
    assert result.next_plan_sha256 == by_role["current_plan"].sha256


def test_direct_cli_uses_repository_preparer_without_handler_injection(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    seed_paths = {}
    for lane in ("a", "b"):
        for name in (
            "plan",
            "initial-space-authority",
            "qualified-solver-config",
        ):
            seed_paths[(lane, name)] = _private_json(
                tmp_path / f"{lane}-{name}.json",
                {"lane": lane, "kind": name},
            )
    observed: dict[str, Any] = {}

    monkeypatch.setattr(
        handlers,
        "live_clean_source_sha",
        lambda: SOURCE_SHA,
    )
    monkeypatch.setattr(
        handlers,
        "live_qualified_abi_sha256",
        lambda: ABI_SHA256,
    )

    def initialize_campaign(root: Path, identity: Any) -> Path:
        observed["identity"] = identity
        return root

    def run_campaign(
        root: Path,
        identity: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        observed["root"] = root
        observed["identity_again"] = identity
        observed.update(kwargs)
        return {"status": "partial"}

    monkeypatch.setattr(
        handlers,
        "initialize_campaign",
        initialize_campaign,
    )
    monkeypatch.setattr(handlers, "run_campaign", run_campaign)

    argv = [
        "--campaign-root",
        str(tmp_path / "campaign"),
        "--source-sha",
        SOURCE_SHA,
        "--abi-sha256",
        ABI_SHA256,
        "--artifact-root",
        str(tmp_path / "artifacts"),
        "--tensor-cache-directory",
        str(tmp_path / "cache"),
        "--maximum-new-stages",
        "3",
    ]
    for lane in ("a", "b"):
        for name in (
            "plan",
            "initial-space-authority",
            "qualified-solver-config",
        ):
            path = seed_paths[(lane, name)]
            argv.extend(
                (
                    f"--path-{lane}-{name}",
                    str(path),
                    f"--path-{lane}-{name}-sha256",
                    hashlib.sha256(path.read_bytes()).hexdigest(),
                )
            )

    assert handlers.main(argv) == 0
    assert isinstance(observed["prepare_stage"], ContractStagePreparer)
    assert observed["maximum_new_stages"] == 3
    assert observed["identity"] is observed["identity_again"]
