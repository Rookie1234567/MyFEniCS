from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from benchmarks.task035e_blind_campaign import (
    AttemptHandle,
    BlindCampaignIdentity,
    BlindPathIdentity,
    CampaignStage,
    PreparedStage,
    StageArtifactBinding,
    StageExecutionContext,
    StageResult,
    build_campaign_stage_dag,
)
from benchmarks.task035e_campaign_stages import (
    ContractStagePreparer,
    STAGE_WIRING_AUDIT_SCHEMA,
    audit_campaign_stage_wiring,
    formal_stage_contracts,
    prepare_candidate_freeze,
    prepare_two_start_comparison,
    require_executable_stage_wiring,
)
from src.adaptivity.blind_controller.contracts import (
    FORMAL_GOAL_IDS,
    GoalVector,
)
from src.adaptivity.blind_controller.freeze import FrozenCandidate


def _private_file(path: Path, body: bytes) -> tuple[Path, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    path.chmod(0o600)
    return path, hashlib.sha256(body).hexdigest()


def _dag(tmp_path: Path):
    plan_a, sha_a = _private_file(tmp_path / "a.json", b'{"a":1}\n')
    plan_b, sha_b = _private_file(tmp_path / "b.json", b'{"b":1}\n')
    authority_a, authority_sha_a = _private_file(
        tmp_path / "authority-a.json",
        b'{"authority":"a"}\n',
    )
    authority_b, authority_sha_b = _private_file(
        tmp_path / "authority-b.json",
        b'{"authority":"b"}\n',
    )
    config_a, config_sha_a = _private_file(
        tmp_path / "config-a.json",
        b'{"config":"a"}\n',
    )
    config_b, config_sha_b = _private_file(
        tmp_path / "config-b.json",
        b'{"config":"b"}\n',
    )
    identity = BlindCampaignIdentity(
        source_sha="a" * 40,
        abi_sha256="b" * 64,
        paths=(
            BlindPathIdentity(
                path_id="A",
                trial_id="task035e-blind-path-a",
                nominal_h_nm=20.0,
                initial_plan_path=plan_a,
                initial_plan_sha256=sha_a,
                initial_space_authority_path=authority_a,
                initial_space_authority_sha256=authority_sha_a,
                qualified_solver_config_path=config_a,
                qualified_solver_config_sha256=config_sha_a,
            ),
            BlindPathIdentity(
                path_id="B",
                trial_id="task035e-blind-path-b",
                nominal_h_nm=15.0,
                initial_plan_path=plan_b,
                initial_plan_sha256=sha_b,
                initial_space_authority_path=authority_b,
                initial_space_authority_sha256=authority_sha_b,
                qualified_solver_config_path=config_b,
                qualified_solver_config_sha256=config_sha_b,
            ),
        ),
    )
    return build_campaign_stage_dag(identity)


def test_stage_map_covers_every_current_campaign_stage(tmp_path: Path) -> None:
    dag = _dag(tmp_path)
    contract_names = {
        contract.stage_name for contract in formal_stage_contracts()
    }
    assert {stage.stage_name for stage in dag} == contract_names
    report = audit_campaign_stage_wiring(dag)
    assert report["schema_version"] == STAGE_WIRING_AUDIT_SCHEMA
    assert report["formal_stage_count"] == len(contract_names)
    assert not any(
        row["code"] == "unmapped_campaign_stage"
        for row in report["issues"]
    )


def test_wiring_audit_accepts_closed_structural_contract(
    tmp_path: Path,
) -> None:
    report = audit_campaign_stage_wiring(_dag(tmp_path))
    assert report["status"] == "ready"
    assert report["formal_preparer_enabled"] is True
    assert report["pde_executed"] is False
    assert report["issues"] == []
    require_executable_stage_wiring(_dag(tmp_path))


def test_contract_records_real_producer_entrypoints() -> None:
    by_name = {
        contract.stage_name: contract
        for contract in formal_stage_contracts()
    }
    assert (
        "benchmarks.run_task033_full3d_watchdog:main"
        in by_name["current_solve"].producer_entrypoints
    )
    assert (
        "benchmarks.task035e_cellwise_authority:"
        "write_cellwise_authority"
        in by_name["cellwise_partition"].producer_entrypoints
    )
    assert (
        "benchmarks.task035e_blind_cycle:main"
        in by_name["cycle_advance"].producer_entrypoints
    )
    p_selected = by_name["p_selected_shadow_verification"]
    h_selected = by_name["h_selected_shadow_verification"]
    assert p_selected.heavy_command_count_minimum == 0
    assert h_selected.heavy_command_count_maximum == 1
    assert (
        by_name["internal_gate_deferred_or_final"]
        .heavy_command_count_maximum
        == 4
    )


def test_contract_preparer_checks_inputs_commands_and_outputs(
    tmp_path: Path,
) -> None:
    contracts = formal_stage_contracts()

    def handler(
        context: StageExecutionContext,
        _attempt: AttemptHandle,
    ) -> PreparedStage:
        contract = next(
            row
            for row in contracts
            if row.stage_name == context.stage.stage_name
        )

        def execute(
            attempt: AttemptHandle,
            command_receipts: tuple[object, ...],
        ) -> StageResult:
            artifacts = []
            for role in contract.provided_artifact_roles:
                path = attempt.write_artifact(
                    f"{role}.json",
                    {"role": role},
                )
                artifacts.append(
                    StageArtifactBinding.from_file(role, path)
                )
            return StageResult(
                status="completed",
                classification="contract_test_completed",
                input_plan_sha256=context.input_plan_sha256,
                artifacts=tuple(artifacts),
                command_receipt_file_sha256s=tuple(
                    receipt.receipt_file_sha256
                    for receipt in command_receipts
                ),
            )

        return PreparedStage(execute=execute)

    handlers = {contract.stage_name: handler for contract in contracts}
    preparer = ContractStagePreparer(handlers)
    assert callable(preparer)
    with pytest.raises(
        Exception,
        match="lacks typed inputs",
    ):
        context = StageExecutionContext(
            campaign_root=tmp_path,
            stage=_dag(tmp_path)[1],
            source_sha="a" * 40,
            abi_sha256="b" * 64,
            trial_id="task035e-blind-path-a",
            nominal_h_nm=20.0,
            input_plan_sha256="c" * 64,
            input_artifacts=(),
        )
        attempt = AttemptHandle(
            context=context,
            attempt_number=1,
            attempt_dir=tmp_path,
        )
        preparer(context, attempt)


def test_contract_preparer_preserves_controlled_resource_stop_policy(
    tmp_path: Path,
) -> None:
    contracts = formal_stage_contracts()

    def handler(
        _context: StageExecutionContext,
        _attempt: AttemptHandle,
    ) -> PreparedStage:
        return PreparedStage(
            execute=lambda _attempt, _receipts: StageResult(
                status="blocked",
                classification="fixture",
                input_plan_sha256="c" * 64,
            ),
            argv=("/bin/true",),
            allow_controlled_resource_stop=True,
        )

    preparer = ContractStagePreparer(
        {contract.stage_name: handler for contract in contracts}
    )
    stage = next(
        row
        for row in _dag(tmp_path)
        if row.stage_name == "p_shadow_discovery"
    )
    contract = next(
        row
        for row in contracts
        if row.stage_name == stage.stage_name
    )
    bindings = []
    for role in contract.required_artifact_roles:
        path, _sha = _private_file(
            tmp_path / "inputs" / f"{role}.json",
            b"{}\n",
        )
        bindings.append(StageArtifactBinding.from_file(role, path))
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    context = StageExecutionContext(
        campaign_root=tmp_path,
        stage=stage,
        source_sha="a" * 40,
        abi_sha256="b" * 64,
        trial_id="task035e-blind-path-a",
        nominal_h_nm=20.0,
        input_plan_sha256="c" * 64,
        input_artifacts=tuple(bindings),
    )
    prepared = preparer(
        context,
        AttemptHandle(
            context=context,
            attempt_number=1,
            attempt_dir=attempt_dir,
        ),
    )

    assert prepared.allow_controlled_resource_stop is True
    assert prepared.command_argvs == (("/bin/true",),)


def _binding(role: str, path: Path) -> StageArtifactBinding:
    return StageArtifactBinding.from_file(role, path)


def _cycle_binding_file(
    path: Path,
    *,
    peak: int,
    rows: int,
) -> Path:
    payload = {
        "resource_inventory": {
            "active_dofs": rows + 10,
            "rows": rows,
            "matrix_nnz": rows * 20,
            "factor_nnz": rows * 50,
            "solver_peak_bytes": peak,
        }
    }
    outer = {
        "schema_version": "test",
        "sha256": hashlib.sha256(
            json.dumps(
                payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
                allow_nan=False,
            ).encode("ascii")
        ).hexdigest(),
        "payload": payload,
    }
    return _private_file(
        path,
        (json.dumps(outer, sort_keys=True) + "\n").encode(),
    )[0]


def test_real_two_start_gate_selects_lower_resource_and_rejects_mismatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import benchmarks.task035e_campaign_stages as stage_module

    output_a = _private_file(
        tmp_path / "output-a.json",
        b'{"marker":"a"}\n',
    )[0]
    output_b = _private_file(
        tmp_path / "output-b.json",
        b'{"marker":"b"}\n',
    )[0]
    cycle_a = _cycle_binding_file(
        tmp_path / "cycle-a.json",
        peak=2_000,
        rows=200,
    )
    cycle_b = _cycle_binding_file(
        tmp_path / "cycle-b.json",
        peak=1_000,
        rows=300,
    )
    generic = {
        role: _private_file(
            tmp_path / f"{role}.json",
            b"{}\n",
        )[0]
        for role in (
            "path_a_internal_gate_authority",
            "path_b_internal_gate_authority",
            "path_a_trial_state",
            "path_b_trial_state",
            "path_a_trial_metadata",
            "path_b_trial_metadata",
            "path_a_current_watchdog_record",
            "path_b_current_watchdog_record",
        )
    }
    artifacts = {
        "path_a_current_candidate_output": output_a,
        "path_b_current_candidate_output": output_b,
        "path_a_cycle_binding": cycle_a,
        "path_b_cycle_binding": cycle_b,
        **generic,
    }

    goals = GoalVector.from_mapping(
        {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    )

    def resource_authority(*, peak: int, rows: int):
        return {
            "schema_version": "task035e.resource-authority.v1",
            "active_dofs": rows + 10,
            "rows": rows,
            "matrix_nnz": rows * 20,
            "factor_nnz": rows * 50,
            "solver_peak_bytes": peak,
            "swap_peak_bytes": 0,
            "mpi_size": 8,
            "same_solver_lifecycle_telemetry": True,
        }

    output_sha_a = stage_module._canonical_sha256({"marker": "a"})
    output_sha_b = stage_module._canonical_sha256({"marker": "b"})
    endpoint_a = SimpleNamespace(
        freeze_ready=True,
        goals=goals,
        complete_output_sha256=output_sha_a,
        resource_inventory_sha256=stage_module._canonical_sha256(
            resource_authority(peak=2_000, rows=200)
        ),
        cycle_index=2,
        plan_file_sha256="1" * 64,
        mesh_forest_sha256="2" * 64,
        degree_map_sha256="3" * 64,
        internal_certificate={},
    )
    endpoint_b = SimpleNamespace(
        freeze_ready=True,
        goals=goals,
        complete_output_sha256=output_sha_b,
        resource_inventory_sha256=stage_module._canonical_sha256(
            resource_authority(peak=1_000, rows=300)
        ),
        cycle_index=2,
        plan_file_sha256="4" * 64,
        mesh_forest_sha256="5" * 64,
        degree_map_sha256="6" * 64,
        internal_certificate={},
    )

    def trial(path_id: str, endpoint):
        return SimpleNamespace(
            trial_id=f"task035e-blind-path-{path_id.lower()}",
            algorithm_id="task035e-blind-multilevel-hp-v1",
            source_sha="a" * 40,
            initial_path_id=f"path-{path_id}",
            initial_mesh_forest_sha256=(
                "7" * 64 if path_id == "A" else "8" * 64
            ),
            physical_identity_sha256="9" * 64,
            maximum_cycles=6,
            results=(endpoint,),
            cycle_chain_root_sha256=(
                "b" * 64 if path_id == "A" else "c" * 64
            ),
        )

    trials = {
        "A": trial("A", endpoint_a),
        "B": trial("B", endpoint_b),
    }
    monkeypatch.setattr(
        stage_module,
        "_load_terminal_trial",
        lambda _context, *, path_id: trials[path_id],
    )
    metadata = {
        "geometry_sha256": "d" * 64,
        "material_sha256": "e" * 64,
        "incident_sha256": "f" * 64,
        "dtn_definition_sha256": "0" * 64,
        "postprocessing_sha256": "1" * 64,
        "physical_identity_sha256": "9" * 64,
    }
    monkeypatch.setattr(
        stage_module,
        "_load_terminal_metadata",
        lambda _context, *, path_id, trial: metadata,
    )
    stage = CampaignStage(
        ordinal=1,
        path_id="FINAL",
        cycle_index=None,
        stage_name="two_start_comparison",
        heavy=False,
        predecessor_stage_id=None,
    )
    context = StageExecutionContext(
        campaign_root=tmp_path,
        stage=stage,
        source_sha="a" * 40,
        abi_sha256="b" * 64,
        trial_id="task035e-blind-two-start-final",
        nominal_h_nm=0.0,
        input_plan_sha256="c" * 64,
        input_artifacts=tuple(
            _binding(role, path)
            for role, path in sorted(artifacts.items())
        ),
    )
    pass_attempt_dir = tmp_path / "pass-attempt"
    pass_attempt_dir.mkdir(mode=0o700)
    pass_attempt = AttemptHandle(context, 1, pass_attempt_dir)
    passed = prepare_two_start_comparison(
        context,
        pass_attempt,
    ).execute(pass_attempt, ())
    assert passed.status == "completed"
    comparison_path = passed.artifacts[0].path
    comparison = json.loads(comparison_path.read_text())
    assert comparison["pass"] is True
    assert comparison["chosen_path_id"] == "B"
    assert comparison["two_path_gate"]["pass"] is True

    adapted = SimpleNamespace(
        payload={"marker": "b"},
        output_sha256=output_sha_b,
        record_sha256=_binding(
            "record",
            generic["path_b_current_watchdog_record"],
        ).sha256,
        source_sha="a" * 40,
        trial_id="task035e-blind-path-b",
        cycle_index=2,
        output_role="current",
        plan_file_sha256="4" * 64,
        forest_leaf_catalog_sha256="5" * 64,
        cell_degree_plan_sha256="6" * 64,
        structural_inventory={
            "active_fe_dofs": 310,
            "matrix_rows": 300,
            "matrix_nnz": 6_000,
            "factor_nnz": 15_000,
            "solver_peak_bytes": 1_000,
        },
    )
    monkeypatch.setattr(
        stage_module,
        "adapt_candidate_output",
        lambda _record: adapted,
    )
    freeze_calls = []

    def fake_freeze(
        selected_trial,
        *,
        two_path_gate,
        physical_identity_sha256,
        resource_authority,
    ):
        freeze_calls.append(
            (
                selected_trial,
                two_path_gate,
                physical_identity_sha256,
                resource_authority,
            )
        )
        return FrozenCandidate(
            schema_version="task035e.hidden-audit-freeze-receipt.v1",
            trial_id=selected_trial.trial_id,
            algorithm_id=selected_trial.algorithm_id,
            source_sha=selected_trial.source_sha,
            initial_path_id=selected_trial.initial_path_id,
            initial_mesh_forest_sha256=(
                selected_trial.initial_mesh_forest_sha256
            ),
            cycle_chain_root_sha256=(
                selected_trial.cycle_chain_root_sha256
            ),
            cycle_index=2,
            physical_identity_sha256=physical_identity_sha256,
            mesh_forest_sha256="5" * 64,
            degree_map_sha256="6" * 64,
            output_sha256=output_sha_b,
            internal_certificate_sha256="2" * 64,
            resource_inventory_sha256=(
                stage_module._canonical_sha256(resource_authority)
            ),
            two_path_gate_sha256=stage_module._canonical_sha256(
                two_path_gate
            ),
            frozen_payload_sha256="3" * 64,
        )

    monkeypatch.setattr(stage_module, "freeze_candidate", fake_freeze)

    freeze_context = StageExecutionContext(
        campaign_root=tmp_path,
        stage=CampaignStage(
            ordinal=2,
            path_id="FINAL",
            cycle_index=None,
            stage_name="candidate_freeze",
            heavy=False,
            predecessor_stage_id=stage.stage_id,
        ),
        source_sha=context.source_sha,
        abi_sha256=context.abi_sha256,
        trial_id=context.trial_id,
        nominal_h_nm=0.0,
        input_plan_sha256=context.input_plan_sha256,
        input_artifacts=(
            *context.input_artifacts,
            _binding("two_start_comparison", comparison_path),
        ),
    )
    freeze_attempt_dir = tmp_path / "freeze-attempt"
    freeze_attempt_dir.mkdir(mode=0o700)
    freeze_attempt = AttemptHandle(
        freeze_context,
        1,
        freeze_attempt_dir,
    )
    frozen = prepare_candidate_freeze(
        freeze_context,
        freeze_attempt,
    ).execute(freeze_attempt, ())
    assert frozen.status == "completed"
    freeze = json.loads(frozen.artifacts[0].path.read_text())
    assert freeze["chosen_path_id"] == "B"
    assert freeze["external_audit_run"] is False
    assert (
        freeze["evaluator_preflight_status"]
        == "deferred_until_blind_exit"
    )
    assert {binding.role for binding in frozen.artifacts} == {
        "candidate_freeze",
        "freeze_receipt",
        "frozen_candidate_bundle",
    }
    assert len(freeze_calls) == 1

    mismatch_values = {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    mismatch_values[FORMAL_GOAL_IDS[0]] = 1.0
    trials["B"] = trial(
        "B",
        SimpleNamespace(
            **{
                **endpoint_b.__dict__,
                "goals": GoalVector.from_mapping(mismatch_values),
            }
        ),
    )
    mismatch_context = StageExecutionContext(
        campaign_root=tmp_path,
        stage=stage,
        source_sha=context.source_sha,
        abi_sha256=context.abi_sha256,
        trial_id=context.trial_id,
        nominal_h_nm=0.0,
        input_plan_sha256=context.input_plan_sha256,
        input_artifacts=context.input_artifacts,
    )
    mismatch_attempt_dir = tmp_path / "mismatch-attempt"
    mismatch_attempt_dir.mkdir(mode=0o700)
    mismatch_attempt = AttemptHandle(
        mismatch_context,
        1,
        mismatch_attempt_dir,
    )
    rejected = prepare_two_start_comparison(
        mismatch_context,
        mismatch_attempt,
    ).execute(mismatch_attempt, ())
    assert rejected.status == "controlled_negative"
    assert rejected.classification == "two_start_outputs_differ"
