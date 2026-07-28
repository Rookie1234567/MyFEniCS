from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace
from typing import Any

import pytest

from benchmarks import task035e_blind_cycle as blind_cycle
import benchmarks.task035e_blind_bindings as blind_bindings
import benchmarks.task035e_internal_gate_authority as gate_authority
from benchmarks.task035e_blind_bindings import (
    SNAPSHOT_COMMON_NAMESPACE,
    SNAPSHOT_GATE_NAMESPACE,
    SNAPSHOT_MANIFEST_NAMESPACE,
    SNAPSHOT_PLAN_NAMESPACE,
    SNAPSHOT_RESIDUAL_NAMESPACE,
    SNAPSHOT_SCHEMA,
    TRIAL_METADATA_SCHEMA,
    VERIFICATION_PREDICTION_SCHEMA,
    BlindBindingError,
    ShadowEndpointInput,
    VerificationPredictionInput,
    main,
    write_blind_input_manifest,
    write_cycle_binding,
    write_shadow_request,
    write_verification_prediction,
)
from benchmarks.task035e_candidate_output import (
    CandidateWatchdogInput,
    adapt_candidate_output,
    write_candidate_output,
)
from benchmarks.task035e_goal_marking import produce_goal_marking
from benchmarks.task035e_reference_leak_checker import (
    FORMAL_BLIND_ENTRYPOINTS,
    build_reference_leak_report,
    scan_blind_controller,
    validate_blind_input_manifest,
    write_reference_leak_report_artifact,
)
from benchmarks.task035e_shadow_bundle import (
    BoundJSONInput,
    build_shadow_bundle,
)
from benchmarks.task035e_transition_producer import write_transition_bundle
from src.adaptivity.blind_controller import (
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
    BlindCycleInput,
    BlindTrial,
    GoalVector,
    InternalGates,
    ShadowCatalog,
    ShadowCost,
    StructuralInventory,
    advance_blind_trial,
    build_unmeasured_h_level3_saturation_authority,
    build_unmeasured_p6_saturation_authority,
    build_shadow_action,
    h_level3_saturation_authority_payload,
    p6_saturation_authority_payload,
)
from src.adaptivity.task035e_h_saturation import (
    build_level3_h_saturation_catalog,
)
from src.adaptivity.task035e_hp_transition import (
    canonical_hp_cell_target_id,
)
from src.adaptivity.task035e_initial_space import (
    build_task035e_initial_space_plan,
)
from src.adaptivity.task035e_plan_transition import (
    canonical_solver_content_sha256,
    rebuild_hp_transition_state_from_solver_plan,
)
from src.common.config_3d import target_stage4_config
from src.test.test_232_task035e_candidate_output import (
    _write_candidate_run,
)
from src.test.test_236_task035e_blind_cycle import _action_row
from src.test.test_236_task035e_blind_cycle import (
    _internal_gate_authority,
)
from src.test.test_241_task035e_actual_shadow_bundle import (
    _fixture as _actual_shadow_fixture,
)
from src.test.test_259_task035e_goal_marking import _cellwise_authority


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _h_saturation_for_state(
    state: Any,
    *,
    plan_file_sha256: str,
    mesh_forest_sha256: str,
    degree_map_sha256: str,
) -> object:
    targets = tuple(
        sorted(
            canonical_hp_cell_target_id(key)
            for key in state.cell_degree_by_key
            if key.level == 2
        )
    )
    if targets:
        catalog = build_level3_h_saturation_catalog(state)
        orbit_ids = tuple(
            sorted(orbit.orbit_id for orbit in catalog.periodic_orbits)
        )
        orbit_catalog_sha = catalog.audit["orbit_catalog_sha256"]
    else:
        orbit_ids = ()
        orbit_catalog_sha = _canonical_sha(
            {
                "schema_version": (
                    "task035e.level3-h-saturation-empty-orbit-catalog.v1"
                ),
                "level_two_target_ids": [],
                "periodic_orbit_ids": [],
            }
        )
    return build_unmeasured_h_level3_saturation_authority(
        level_two_target_ids=targets,
        periodic_orbit_ids=orbit_ids,
        orbit_catalog_sha256=orbit_catalog_sha,
        current_plan_file_sha256=plan_file_sha256,
        current_mesh_forest_sha256=mesh_forest_sha256,
        current_degree_map_sha256=degree_map_sha256,
    )


def _namespaced_sha(value: Any, namespace: str) -> str:
    digest = hashlib.sha256()
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


def _private_json(path: Path, value: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return _file_sha(path)


def _scalar(candidate: dict[str, Any], name: str) -> float:
    return float(
        next(
            row["value"]
            for row in candidate["scalar_observations"]
            if row["name"] == name
        )
    )


def _cycle_zero_record(tmp_path: Path) -> Any:
    record_input = _write_candidate_run(tmp_path)
    record = json.loads(record_input.path.read_text(encoding="utf-8"))
    source_sha = str(record["source"]["commit_sha"])
    config = target_stage4_config(degree=6, h_nm=20.0)
    plan = build_task035e_initial_space_plan(
        config,
        path_id="A",
        source_sha=source_sha,
        comm_size=8,
    ).plan_payload()
    summary_path = Path(record["raw_evidence"]["solver_summary"])
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    plan_path = Path(
        summary["stage4_local_h_constraint_audit"]["mesh"]["plan_path"]
    )
    plan_sha = _private_json(plan_path, plan)
    forest_sha = str(plan["expected_forest"]["leaf_catalog_sha256"])
    degree_sha = str(plan["cell_interior_degree_plan_sha256"])
    local_h = summary["stage4_local_h_constraint_audit"]
    mesh = local_h["mesh"]
    mesh["plan_file_sha256"] = plan_sha
    mesh["cell_interior_degree_plan_sha256"] = degree_sha
    mesh["forest"]["leaf_catalog_sha256"] = forest_sha
    mesh["carrier"]["leaf_catalog_sha256"] = forest_sha
    local_h["degree_plan"]["cell_degree_plan_sha256"] = degree_sha
    summary_sha = _private_json(summary_path, summary)
    record["task035e_blind_candidate"]["cycle_index"] = 0
    record["task035e_blind_candidate"]["trial_id"] = (
        "task035e-blind-path-a"
    )
    plan_gate = record["task035e_blind_candidate_launch_gate"]["plan"]
    plan_gate["expected_file_sha256"] = plan_sha
    plan_gate["observed_file_sha256"] = plan_sha
    record["solver_summary_sha256"] = summary_sha
    record["solver_summary"] = summary
    record_sha = _private_json(record_input.path, record)
    return CandidateWatchdogInput(record_input.path, record_sha)


def _shadow_outer(current: Any) -> dict[str, Any]:
    goals = blind_cycle.goal_vector_from_candidate_output(current.payload)
    p_action = _action_row(
        action_id="p-up-cell-1",
        kind="p-up",
        target_id="cell:1",
        current=goals,
    )
    h_action = _action_row(
        action_id="h-refine-root-9",
        kind="h-refine",
        target_id="root:9",
        current=goals,
    )
    for action in (p_action, h_action):
        next_mesh = (
            "a" * 64
            if action["kind"] == "h-refine"
            else current.forest_leaf_catalog_sha256
        )
        next_degree = "b" * 64
        rebuilt = build_shadow_action(
            action_id=str(action["action_id"]),
            kind=str(action["kind"]),
            target_ids=tuple(action["target_ids"]),
            current=goals,
            shadow=GoalVector.from_mapping(action["shadow_goals"]),
            signed_dwr_delta=action["signed_dwr_delta"],
            cost=ShadowCost(
                *(
                    action["cost"][name]
                    for name in ShadowCost.__dataclass_fields__
                )
            ),
            sign_consistent=bool(action["sign_consistent"]),
            transition_action_sha256=str(
                action["transition_action_sha256"]
            ),
            transition_action_file_sha256=str(
                action["transition_action_file_sha256"]
            ),
            transition_action_identity_sha256=str(
                action["transition_action_identity_sha256"]
            ),
            next_mesh_forest_sha256=next_mesh,
            next_degree_map_sha256=next_degree,
            actual_added_leaf_count=int(
                action["actual_added_leaf_count"]
            ),
        )
        action["next_mesh_forest_sha256"] = next_mesh
        action["next_degree_map_sha256"] = next_degree
        action["action_sha256"] = rebuilt.action_sha256
        evidence = action["external_evidence"]
        evidence["current_plan_file_sha256"] = (
            current.plan_file_sha256
        )
        evidence["from_leaf_catalog_sha256"] = (
            current.forest_leaf_catalog_sha256
        )
        evidence["from_cell_degree_plan_sha256"] = (
            current.cell_degree_plan_sha256
        )
        evidence["next_leaf_catalog_sha256"] = next_mesh
        evidence["next_cell_degree_plan_sha256"] = next_degree
    current_plan = json.loads(current.plan_path.read_text(encoding="utf-8"))
    current_state = rebuild_hp_transition_state_from_solver_plan(
        target_stage4_config(
            degree=6,
            h_nm=float(current_plan["base_config"]["mesh_target_size"]),
        ),
        current_plan=current_plan,
        comm_size=8,
    )
    p6_saturation = build_unmeasured_p6_saturation_authority(
        p6_target_ids=tuple(
            sorted(
                canonical_hp_cell_target_id(key)
                for key, degree in current_state.cell_degree_by_key.items()
                if degree == 6
            )
        ),
        current_plan_file_sha256=current.plan_file_sha256,
        current_mesh_forest_sha256=current.forest_leaf_catalog_sha256,
        current_degree_map_sha256=current.cell_degree_plan_sha256,
    )
    payload = {
        "schema_version": blind_cycle.SHADOW_BUNDLE_SCHEMA,
        "producer_role": "external_actual_shadow_dwr_solver",
        "source_sha": current.source_sha,
        "mpi_size": 8,
        "trial_id": current.trial_id,
        "cycle_index": current.cycle_index,
        "mesh_forest_sha256": current.forest_leaf_catalog_sha256,
        "degree_map_sha256": current.cell_degree_plan_sha256,
        "complete_output_sha256": current.output_sha256,
        "current_goal_sha256": goals.sha256,
        "actual_shadow_solves": True,
        "actual_dwr_evaluations": True,
        "synthetic": False,
        "reference_derived": False,
        "p6_saturation": p6_saturation_authority_payload(
            p6_saturation
        ),
        "h_level3_saturation": h_level3_saturation_authority_payload(
            _h_saturation_for_state(
                current_state,
                plan_file_sha256=current.plan_file_sha256,
                mesh_forest_sha256=current.forest_leaf_catalog_sha256,
                degree_map_sha256=current.cell_degree_plan_sha256,
            )
        ),
        "p_actions": [p_action],
        "h_actions": [h_action],
    }
    return {
        "schema_version": blind_cycle.SHADOW_BUNDLE_SCHEMA,
        "sha256": _canonical_sha(payload),
        "payload": payload,
    }


def _snapshot(
    tmp_path: Path,
    *,
    current: Any,
    candidate: dict[str, Any],
) -> Path:
    plan_path = current.plan_path.resolve()
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    residual = {
        "linear_system_relative_residual": float(
            candidate["full_explicit_true_residual"]
        )
    }
    gate = {
        "full_active_residual": residual,
        "full_active_residual_sha256": _namespaced_sha(
            residual,
            SNAPSHOT_RESIDUAL_NAMESPACE,
        ),
        "port_operator_audit_sha256": "8" * 64,
        "port_metrics_sha256": "9" * 64,
        "primal_solver_telemetry": {"converged_reason": 1},
        "primal_solver_telemetry_sha256": "a" * 64,
    }
    common = {"fixture": "MPI8-current"}
    shards = []
    for rank in range(8):
        shard = tmp_path / "snapshot" / f"rank-{rank}.npz"
        shard.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(
            shard,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(f"fixture-rank-{rank}".encode("ascii"))
        shards.append(
            {
                "rank": rank,
                "path": shard.name,
                "file_sha256": _file_sha(shard),
            }
        )
    unsigned = {
        "schema_version": SNAPSHOT_SCHEMA,
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
            "path": str(plan_path),
            "file_sha256": current.plan_file_sha256,
            "payload_sha256": _namespaced_sha(
                plan,
                SNAPSHOT_PLAN_NAMESPACE,
            ),
            "provenance_sha256": "b" * 64,
            "provenance_schema_version": (
                "task035e.blind-initial-provenance.v1"
            ),
            "forest_leaf_catalog_sha256": (
                current.forest_leaf_catalog_sha256
            ),
            "cell_degree_plan_sha256": (
                current.cell_degree_plan_sha256
            ),
        },
        "common_identity": common,
        "common_identity_sha256": _namespaced_sha(
            common,
            SNAPSHOT_COMMON_NAMESPACE,
        ),
        "qualified_primal_gate": gate,
        "qualified_primal_gate_sha256": _namespaced_sha(
            gate,
            SNAPSHOT_GATE_NAMESPACE,
        ),
        "partitions": {},
        "matrix_operator": {},
        "rank_bound_identity_sha256": "c" * 64,
        "shards": shards,
        "publication": "mode-0600 test fixture",
        "no_full_vector_python_allgather": True,
        "full_matrix_persisted": False,
        "capability_credit": {
            "current_primal_snapshot_complete": True,
            "accuracy_credit": False,
        },
        "ordinary_default_changed": False,
    }
    manifest = {
        **unsigned,
        "manifest_payload_sha256": _namespaced_sha(
            unsigned,
            SNAPSHOT_MANIFEST_NAMESPACE,
        ),
    }
    path = tmp_path / "snapshot" / "manifest.json"
    _private_json(path, manifest)
    return path


def _cycle_fixture(tmp_path: Path) -> dict[str, Any]:
    current_record = _cycle_zero_record(tmp_path / "current")
    current = adapt_candidate_output(current_record)
    candidate_path = tmp_path / "candidate.json"
    write_candidate_output(candidate_path, current)
    shadow_path = tmp_path / "shadow-bundle.json"
    _private_json(shadow_path, _shadow_outer(current))
    snapshot_path = _snapshot(
        tmp_path,
        current=current,
        candidate=dict(current.payload),
    )
    trial_path = tmp_path / "trial.json"
    physical_components = {
        "geometry_sha256": "1" * 64,
        "material_sha256": "2" * 64,
        "incident_sha256": "3" * 64,
        "dtn_definition_sha256": "4" * 64,
        "postprocessing_sha256": "5" * 64,
        "source_sha": current.source_sha,
    }
    trial_unsigned = {
        "schema_version": TRIAL_METADATA_SCHEMA,
        "status": "qualified",
        "pass": True,
        "trial_id": current.trial_id,
        "algorithm_id": "reference-blind-multilevel-hp-v1",
        "source_sha": current.source_sha,
        "initial_path_id": "path-A-h20",
        "initial_mesh_forest_sha256": (
            current.forest_leaf_catalog_sha256
        ),
        "initial_degree_map_sha256": current.cell_degree_plan_sha256,
        "initial_state_sha256": rebuild_hp_transition_state_from_solver_plan(
            target_stage4_config(degree=6, h_nm=20.0),
            current_plan=json.loads(
                current.plan_path.read_text(encoding="utf-8")
            ),
            comm_size=8,
        ).state_sha256,
        "initial_plan_file_sha256": current.plan_file_sha256,
        "initial_plan_payload_sha256": _canonical_sha(
            json.loads(current.plan_path.read_text(encoding="utf-8"))
        ),
        "initial_space_authority_file_sha256": "6" * 64,
        "initial_space_authority_payload_sha256": "7" * 64,
        "qualified_solver_config_file_sha256": "8" * 64,
        "qualified_solver_config_payload_sha256": "9" * 64,
        **{
            name: physical_components[name]
            for name in (
                "geometry_sha256",
                "material_sha256",
                "incident_sha256",
                "dtn_definition_sha256",
                "postprocessing_sha256",
            )
        },
        "physical_identity_sha256": _canonical_sha(
            physical_components
        ),
        "formal_mpi_size": 8,
        "maximum_cycles": 6,
        "ordinary_default_changed": False,
    }
    _private_json(
        trial_path,
        {
            **trial_unsigned,
            "metadata_payload_sha256": _canonical_sha(trial_unsigned),
        },
    )
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    plan = json.loads(current.plan_path.read_text(encoding="utf-8"))
    gates_path = tmp_path / "internal-gate-authority.json"
    _private_json(
        gates_path,
        _internal_gate_authority(
            source_sha=current.source_sha,
            trial_id=current.trial_id,
            cycle_index=current.cycle_index,
            candidate_record_file_sha256=current.record_sha256,
            candidate_output_file_sha256=_file_sha(candidate_path),
            candidate_output_payload_sha256=current.output_sha256,
            plan_file_sha256=current.plan_file_sha256,
            plan_payload_sha256=_canonical_sha(plan),
            mesh_forest_sha256=current.forest_leaf_catalog_sha256,
            degree_map_sha256=current.cell_degree_plan_sha256,
            snapshot_file_sha256=_file_sha(snapshot_path),
            snapshot_payload_sha256=snapshot[
                "manifest_payload_sha256"
            ],
            snapshot_full_residual_sha256=snapshot[
                "qualified_primal_gate"
            ]["full_active_residual_sha256"],
            full_explicit_residual=float(
                current.payload["full_explicit_true_residual"]
            ),
            energy_closure_error=abs(
                _scalar(dict(current.payload), "energy_closure") - 1.0
            ),
            absorption_volume=_scalar(
                dict(current.payload),
                "A_volume",
            ),
        ),
    )
    return {
        "current_record": current_record,
        "current": current,
        "candidate_path": candidate_path,
        "shadow_path": shadow_path,
        "snapshot_path": snapshot_path,
        "trial_path": trial_path,
        "gates_path": gates_path,
    }


def _prediction_fixture(tmp_path: Path) -> dict[str, Any]:
    source_sha = "1234567890abcdef1234567890abcdef12345678"
    config = target_stage4_config(degree=6, h_nm=20.0)
    plan = build_task035e_initial_space_plan(
        config,
        path_id="A",
        source_sha=source_sha,
        comm_size=8,
    ).plan_payload()
    state = rebuild_hp_transition_state_from_solver_plan(
        config,
        current_plan=plan,
        comm_size=8,
    )
    plan_path = tmp_path / "current-plan.json"
    plan_sha = _private_json(plan_path, plan)
    authority = _cellwise_authority(
        plan=plan,
        plan_file_sha256=plan_sha,
        state=state,
    )
    authority_path = tmp_path / "dwr-authority.json"
    authority_sha = _private_json(authority_path, authority)
    marking_path = tmp_path / "goal-marking.json"
    marking_receipt = produce_goal_marking(
        current_plan_path=plan_path,
        current_plan_file_sha256=plan_sha,
        dwr_authority_path=authority_path,
        dwr_authority_file_sha256=authority_sha,
        source_sha=source_sha,
        action_kind="p-up",
        output_path=marking_path,
    )
    transition = write_transition_bundle(
        current_plan_path=plan_path,
        current_plan_file_sha256=plan_sha,
        source_sha=source_sha,
        action_kind="p-up",
        canonical_target_ids=marking_receipt.canonical_target_ids,
        action_path=tmp_path / "transition-action.json",
        next_plan_path=tmp_path / "next-plan.json",
    )
    return {
        "source_sha": source_sha,
        "marking_path": marking_path,
        "marking_receipt": marking_receipt,
        "transition": transition,
    }


def test_shadow_request_recomputes_hashes_and_replays_existing_builder(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _request, context = _actual_shadow_fixture(tmp_path / "actual")
    raw = context["request"]
    p = raw["p_actions"][0]
    h = raw["h_actions"][0]
    output = tmp_path / "published-shadow-request.json"
    receipt = write_shadow_request(
        output,
        current_record_path=Path(raw["current_record"]["path"]),
        p_actions=(
            ShadowEndpointInput(
                Path(p["transition_action"]["path"]),
                Path(p["goal_marking"]["path"]),
                Path(p["verification_prediction"]["path"]),
                Path(p["shadow_record"]["path"]),
                Path(p["dwr_evidence"]["path"]),
            ),
        ),
        h_actions=(
            ShadowEndpointInput(
                Path(h["transition_action"]["path"]),
                Path(h["goal_marking"]["path"]),
                Path(h["verification_prediction"]["path"]),
                Path(h["shadow_record"]["path"]),
                Path(h["dwr_evidence"]["path"]),
            ),
        ),
    )

    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert receipt.file_sha256 == _file_sha(output)
    built = build_shadow_bundle(
        BoundJSONInput(output, receipt.file_sha256)
    )
    assert built.source_sha == context["current"].source_sha
    assert built.current_output_sha256 == context["current"].output_sha256
    with pytest.raises(FileExistsError):
        write_shadow_request(
            output,
            current_record_path=Path(raw["current_record"]["path"]),
            p_actions=(
                ShadowEndpointInput(
                    Path(p["transition_action"]["path"]),
                    Path(p["goal_marking"]["path"]),
                    Path(p["verification_prediction"]["path"]),
                    Path(p["shadow_record"]["path"]),
                    Path(p["dwr_evidence"]["path"]),
                ),
            ),
            h_actions=(
                ShadowEndpointInput(
                    Path(h["transition_action"]["path"]),
                    Path(h["goal_marking"]["path"]),
                    Path(h["verification_prediction"]["path"]),
                    Path(h["shadow_record"]["path"]),
                    Path(h["dwr_evidence"]["path"]),
                ),
            ),
        )

    cli_output = tmp_path / "published-shadow-request-cli.json"
    assert (
        main(
            [
                "shadow-request",
                "--current-record",
                raw["current_record"]["path"],
                "--p-action",
                p["transition_action"]["path"],
                p["goal_marking"]["path"],
                p["verification_prediction"]["path"],
                p["shadow_record"]["path"],
                p["dwr_evidence"]["path"],
                "--h-action",
                h["transition_action"]["path"],
                h["goal_marking"]["path"],
                h["verification_prediction"]["path"],
                h["shadow_record"]["path"],
                h["dwr_evidence"]["path"],
                "--output",
                str(cli_output),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["status"] == "completed"

    with pytest.raises(BlindBindingError, match="differ"):
        write_shadow_request(
            tmp_path / "mismatched-selected-shadow-request.json",
            current_record_path=Path(raw["current_record"]["path"]),
            p_actions=(
                ShadowEndpointInput(
                    Path(p["transition_action"]["path"]),
                    Path(h["goal_marking"]["path"]),
                    Path(h["verification_prediction"]["path"]),
                    Path(p["shadow_record"]["path"]),
                    Path(p["dwr_evidence"]["path"]),
                ),
            ),
            h_actions=(
                ShadowEndpointInput(
                    Path(h["transition_action"]["path"]),
                    Path(h["goal_marking"]["path"]),
                    Path(h["verification_prediction"]["path"]),
                    Path(h["shadow_record"]["path"]),
                    Path(h["dwr_evidence"]["path"]),
                ),
            ),
        )
    p_marking_path = Path(p["goal_marking"]["path"])
    p_marking_path.chmod(0o644)
    with pytest.raises(BlindBindingError, match="mode 0600"):
        write_shadow_request(
            tmp_path / "non-private-selected-shadow-request.json",
            current_record_path=Path(raw["current_record"]["path"]),
            p_actions=(
                ShadowEndpointInput(
                    Path(p["transition_action"]["path"]),
                    p_marking_path,
                    Path(p["verification_prediction"]["path"]),
                    Path(p["shadow_record"]["path"]),
                    Path(p["dwr_evidence"]["path"]),
                ),
            ),
            h_actions=(
                ShadowEndpointInput(
                    Path(h["transition_action"]["path"]),
                    Path(h["goal_marking"]["path"]),
                    Path(h["verification_prediction"]["path"]),
                    Path(h["shadow_record"]["path"]),
                    Path(h["dwr_evidence"]["path"]),
                ),
            ),
        )


def test_verification_prediction_is_closed_marking_derived_and_self_hashed(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = _prediction_fixture(tmp_path)
    output = tmp_path / "verification-prediction.json"
    receipt = write_verification_prediction(
        output,
        goal_marking_path=inputs["marking_path"],
        transition_action_path=inputs["transition"].action_path,
    )
    payload = json.loads(output.read_text(encoding="utf-8"))
    unsigned = dict(payload)
    prediction_sha = unsigned.pop("prediction_sha256")

    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    assert payload["schema_version"] == VERIFICATION_PREDICTION_SCHEMA
    assert payload["source_sha"] == inputs["source_sha"]
    assert payload["cycle_index"] == inputs["transition"].cycle_index
    assert payload["marking_cycle_index"] + 1 == payload["cycle_index"]
    assert payload["action_id"] == inputs["transition"].action_id
    assert payload["action_kind"] == inputs["transition"].action_kind
    assert payload["action_sha256"] == inputs["transition"].action_sha256
    assert payload["marking_file_sha256"] == _file_sha(
        inputs["marking_path"]
    )
    assert payload["marking_payload_sha256"] == (
        inputs["marking_receipt"].marking_sha256
    )
    assert payload["formal_goal_count"] == len(FORMAL_GOAL_IDS)
    assert payload["ordered_goal_ids"] == list(FORMAL_GOAL_IDS)
    assert [row[0] for row in payload["predicted_deltas"]] == list(
        FORMAL_GOAL_IDS
    )
    assert prediction_sha == _namespaced_sha(
        unsigned,
        VERIFICATION_PREDICTION_SCHEMA,
    )
    assert receipt.payload_sha256 == prediction_sha
    assert receipt.file_sha256 == _file_sha(output)
    with pytest.raises(FileExistsError):
        write_verification_prediction(
            output,
            goal_marking_path=inputs["marking_path"],
            transition_action_path=inputs["transition"].action_path,
        )

    cli_output = tmp_path / "verification-prediction-cli.json"
    assert (
        main(
            [
                "verification-prediction",
                "--goal-marking",
                str(inputs["marking_path"]),
                "--transition-action",
                str(inputs["transition"].action_path),
                "--output",
                str(cli_output),
            ]
        )
        == 0
    )
    cli_receipt = json.loads(capsys.readouterr().out)
    assert cli_receipt["kind"] == "verification_prediction"
    assert cli_receipt["action_id"] == inputs["transition"].action_id
    assert json.loads(cli_output.read_text(encoding="utf-8")) == payload


def test_real_pkeep_action_closes_stability_repeat_binding(
    tmp_path: Path,
) -> None:
    source_sha = "1234567890abcdef1234567890abcdef12345678"
    config = target_stage4_config(degree=6, h_nm=20.0)
    initial = build_task035e_initial_space_plan(
        config,
        path_id="A",
        source_sha=source_sha,
        comm_size=8,
    ).plan_payload()
    initial_path = tmp_path / "initial-plan.json"
    initial_file_sha = _private_json(initial_path, initial)
    initial_state = rebuild_hp_transition_state_from_solver_plan(
        config,
        current_plan=initial,
        comm_size=8,
    )
    goals = GoalVector.from_mapping(
        {goal_id: 1.0 for goal_id in FORMAL_GOAL_IDS}
    )

    def neutral_action(
        action_id: str,
        kind: str,
        target: str,
    ) -> Any:
        return build_shadow_action(
            action_id=action_id,
            kind=kind,
            target_ids=(target,),
            current=goals,
            shadow=goals,
            signed_dwr_delta={
                goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS
            },
            cost=ShadowCost(1, 1, 1, 1, 1),
            sign_consistent=True,
            transition_action_sha256="1" * 64,
            transition_action_file_sha256="2" * 64,
            transition_action_identity_sha256="3" * 64,
            next_mesh_forest_sha256=initial_state.audit[
                "leaf_catalog_sha256"
            ],
            next_degree_map_sha256=initial_state.audit[
                "cell_degree_plan_sha256"
            ],
            actual_added_leaf_count=7 if kind == "h-refine" else 0,
        )

    prior = advance_blind_trial(
        BlindTrial(
            trial_id="pkeep-binding",
            algorithm_id="reference-blind-multilevel-hp-v1",
            source_sha=source_sha,
            initial_path_id="path-a-coarse-root",
            initial_mesh_forest_sha256=initial_state.audit[
                "leaf_catalog_sha256"
            ],
            physical_identity_sha256="4" * 64,
        ),
        BlindCycleInput(
            cycle_index=0,
            mesh_forest_sha256=initial_state.audit[
                "leaf_catalog_sha256"
            ],
            degree_map_sha256=initial_state.audit[
                "cell_degree_plan_sha256"
            ],
            plan_file_sha256=initial_file_sha,
            plan_content_sha256=_canonical_sha(initial),
            plan_solver_content_sha256=(
                canonical_solver_content_sha256(initial)
            ),
            state_sha256=initial_state.state_sha256,
            solution_snapshot_sha256="5" * 64,
            watchdog_record_file_sha256="6" * 64,
            complete_output_sha256="7" * 64,
            full_residual_sha256="8" * 64,
            adjoint_bundle_sha256="9" * 64,
            resource_inventory_sha256="a" * 64,
            goals=goals,
            shadows=ShadowCatalog(
                current_goal_sha256=goals.sha256,
                p_actions=(
                    neutral_action("p-neutral", "p-up", "cell:1"),
                ),
                h_actions=(
                    neutral_action("h-neutral", "h-refine", "root:1"),
                ),
                p6_saturation=(
                    build_unmeasured_p6_saturation_authority(
                        p6_target_ids=(),
                        current_plan_file_sha256=initial_file_sha,
                        current_mesh_forest_sha256=initial_state.audit[
                            "leaf_catalog_sha256"
                        ],
                        current_degree_map_sha256=initial_state.audit[
                            "cell_degree_plan_sha256"
                        ],
                    )
                ),
                h_level3_saturation=_h_saturation_for_state(
                    initial_state,
                    plan_file_sha256=initial_file_sha,
                    mesh_forest_sha256=initial_state.audit[
                        "leaf_catalog_sha256"
                    ],
                    degree_map_sha256=initial_state.audit[
                        "cell_degree_plan_sha256"
                    ],
                ),
            ),
            inventory=StructuralInventory(1, 1, 1, 1, 1),
            gates=InternalGates(
                full_explicit_residual=1.0e-12,
                energy_closure_error=1.0e-12,
                absorption_volume=0.0,
                floquet_residual_pass=True,
                hanging_residual_pass=True,
                serial_mpi_identity_pass=False,
                multilevel_mesh_pass=False,
                separated_patch_count=0,
                all_local_levels_present=False,
                algebraic_budget_fraction=1.0,
                dtn_budget_fraction=1.0,
                postprocess_budget_fraction=1.0,
            ),
        ),
    )
    assert prior.results[-1].status == "accepted_no_safe_action"
    prior_path = tmp_path / "prior-trial-state.json"
    prior_file_sha = _private_json(
        prior_path,
        blind_cycle._trial_state_outer(prior),
    )

    transition = write_transition_bundle(
        current_plan_path=initial_path,
        current_plan_file_sha256=initial_file_sha,
        source_sha=source_sha,
        action_kind="p-keep",
        canonical_target_ids=(),
        action_path=tmp_path / "pkeep-action.json",
        next_plan_path=tmp_path / "pkeep-plan.json",
    )
    next_plan = json.loads(
        transition.plan_path.read_text(encoding="utf-8")
    )
    next_state = rebuild_hp_transition_state_from_solver_plan(
        config,
        current_plan=next_plan,
        comm_size=8,
    )
    context = blind_bindings._CycleContext(
        current=SimpleNamespace(
            source_sha=source_sha,
            cycle_index=1,
            forest_leaf_catalog_sha256=next_state.audit[
                "leaf_catalog_sha256"
            ],
            cell_degree_plan_sha256=next_state.audit[
                "cell_degree_plan_sha256"
            ],
            record_sha256="b" * 64,
        ),
        candidate={},
        candidate_file_sha256="c" * 64,
        candidate_payload_sha256="7" * 64,
        plan=blind_bindings._PlanBinding(
            payload=next_plan,
            provenance=dict(next_plan["provenance"]),
            file_sha256=transition.plan_file_sha256,
            content_sha256=_canonical_sha(next_plan),
            solver_content_sha256=(
                canonical_solver_content_sha256(next_plan)
            ),
            state_sha256=next_state.state_sha256,
        ),
        snapshot=blind_bindings._SnapshotBinding(
            file_sha256="d" * 64,
            payload_sha256="e" * 64,
            residual_sha256="f" * 64,
            residual_value=1.0e-12,
        ),
        shadow_payload={},
        shadow_file_sha256="0" * 64,
        p_action_count=1,
        h_action_count=1,
        trial={
            "trial_id": prior.trial_id,
            "algorithm_id": prior.algorithm_id,
            "initial_path_id": prior.initial_path_id,
            "initial_mesh_forest_sha256": (
                prior.initial_mesh_forest_sha256
            ),
            "physical_identity_sha256": prior.physical_identity_sha256,
            "maximum_cycles": prior.maximum_cycles,
        },
        inventory={},
        resource_inventory_sha256="a" * 64,
    )
    transition_binding = blind_bindings._transition_binding(
        context=context,
        prior_trial_state_path=prior_path,
        verification_inputs=(),
        stability_repeat_action_path=transition.action_path,
    )
    repeat = transition_binding["stability_repeat_verification"]

    assert repeat["action_kind"] == "p-keep"
    assert repeat["action_file_sha256"] == transition.action_file_sha256
    assert repeat["previous_plan_solver_content_sha256"] == (
        repeat["next_plan_solver_content_sha256"]
    )
    assert repeat["previous_plan_content_sha256"] != (
        repeat["next_plan_content_sha256"]
    )
    with pytest.raises(
        BlindBindingError,
        match="requires --stability-repeat-action",
    ):
        blind_bindings._transition_binding(
            context=context,
            prior_trial_state_path=prior_path,
            verification_inputs=(),
            stability_repeat_action_path=None,
        )
    with pytest.raises(
        BlindBindingError,
        match="cannot consume shadow verification",
    ):
        blind_bindings._transition_binding(
            context=context,
            prior_trial_state_path=prior_path,
            verification_inputs=(
                VerificationPredictionInput(
                    transition.action_path,
                    transition.action_path,
                    transition.action_path,
                ),
            ),
            stability_repeat_action_path=transition.action_path,
        )
    assert prior_file_sha == _file_sha(prior_path)


def test_manifest_and_cycle_binding_feed_existing_leak_and_cycle_readers(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    inputs = _cycle_fixture(tmp_path)
    manifest_path = tmp_path / "blind-input-manifest.json"
    manifest_receipt = write_blind_input_manifest(
        manifest_path,
        trial_metadata_path=inputs["trial_path"],
        current_record_path=inputs["current_record"].path,
        candidate_output_path=inputs["candidate_path"],
        current_snapshot_path=inputs["snapshot_path"],
        shadow_bundle_path=inputs["shadow_path"],
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    assert stat.S_IMODE(manifest_path.stat().st_mode) == 0o600
    assert manifest_receipt.payload_sha256 == (
        blind_cycle.cycle_manifest_sha256(manifest)
    )
    assert validate_blind_input_manifest(manifest)["pass"] is True
    assert manifest["cycle"]["goal_inventory_sha256"] == (
        FORMAL_GOAL_INVENTORY_SHA256
    )
    cli_manifest_path = tmp_path / "blind-input-manifest-cli.json"
    assert (
        main(
            [
                "blind-manifest",
                "--trial-metadata",
                str(inputs["trial_path"]),
                "--current-record",
                str(inputs["current_record"].path),
                "--candidate-output",
                str(inputs["candidate_path"]),
                "--current-snapshot",
                str(inputs["snapshot_path"]),
                "--shadow-bundle",
                str(inputs["shadow_path"]),
                "--output",
                str(cli_manifest_path),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["kind"] == (
        "blind_input_manifest"
    )
    assert json.loads(cli_manifest_path.read_text(encoding="utf-8")) == (
        manifest
    )

    root = Path(blind_cycle.__file__).resolve().parents[1]
    protected = tmp_path / "audit-canary"
    protected.mkdir()
    isolation = build_reference_leak_report(
        controller_package=root / "src/adaptivity/blind_controller",
        source_root=root,
        source_entrypoints=tuple(
            root / relative for relative in FORMAL_BLIND_ENTRYPOINTS
        ),
        manifest=manifest,
        audit_entrypoint=(
            root / "src/adaptivity/blind_controller/manifest.py"
        ),
        audit_protected_paths=(protected,),
        audit_cwd=root,
    )
    assert isolation["pass"] is True
    isolation_path = tmp_path / "isolation-report.json"
    isolation_receipt = write_reference_leak_report_artifact(
        isolation_path,
        isolation,
    )

    binding_path = tmp_path / "cycle-binding.json"
    binding_receipt = write_cycle_binding(
        binding_path,
        trial_metadata_path=inputs["trial_path"],
        current_record_path=inputs["current_record"].path,
        candidate_output_path=inputs["candidate_path"],
        current_snapshot_path=inputs["snapshot_path"],
        shadow_bundle_path=inputs["shadow_path"],
        internal_gates_path=inputs["gates_path"],
        isolation_report_path=isolation_path,
    )
    binding, payload_sha, file_sha = blind_cycle._load_cycle_binding(
        binding_path,
        binding_receipt.file_sha256,
    )

    assert stat.S_IMODE(binding_path.stat().st_mode) == 0o600
    assert file_sha == binding_receipt.file_sha256
    assert payload_sha == binding_receipt.payload_sha256
    assert binding["candidate_output_file_sha256"] == _file_sha(
        inputs["candidate_path"]
    )
    assert binding["candidate_record_file_sha256"] == (
        inputs["current"].record_sha256
    )
    assert binding["current_snapshot_file_sha256"] == _file_sha(
        inputs["snapshot_path"]
    )
    assert binding["internal_gates"]["schema_version"] == (
        gate_authority.AUTHORITY_SCHEMA
    )
    assert binding["shadow_bundle_file_sha256"] == _file_sha(
        inputs["shadow_path"]
    )
    current_plan = json.loads(
        inputs["current"].plan_path.read_text(encoding="utf-8")
    )
    current_state = rebuild_hp_transition_state_from_solver_plan(
        target_stage4_config(degree=6, h_nm=20.0),
        current_plan=current_plan,
        comm_size=8,
    )
    assert binding["plan_file_sha256"] == _file_sha(
        inputs["current"].plan_path
    )
    assert binding["plan_content_sha256"] == _canonical_sha(current_plan)
    assert binding["plan_solver_content_sha256"] == (
        canonical_solver_content_sha256(current_plan)
    )
    assert binding["state_sha256"] == current_state.state_sha256
    assert binding[
        "reference_isolation_report_file_sha256"
    ] == isolation_receipt["file_sha256"]
    assert binding["transition"] == {
        "previous_trial_state_file_sha256": None,
        "previous_cycle_certificate_sha256": None,
        "executed_action_verifications": [],
        "stability_repeat_verification": None,
    }
    cli_binding_path = tmp_path / "cycle-binding-cli.json"
    assert (
        main(
            [
                "cycle-binding",
                "--trial-metadata",
                str(inputs["trial_path"]),
                "--current-record",
                str(inputs["current_record"].path),
                "--candidate-output",
                str(inputs["candidate_path"]),
                "--current-snapshot",
                str(inputs["snapshot_path"]),
                "--shadow-bundle",
                str(inputs["shadow_path"]),
                "--internal-gates",
                str(inputs["gates_path"]),
                "--isolation-report",
                str(isolation_path),
                "--output",
                str(cli_binding_path),
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out)["kind"] == "cycle_binding"
    assert json.loads(cli_binding_path.read_text(encoding="utf-8")) == (
        json.loads(binding_path.read_text(encoding="utf-8"))
    )

    result = blind_cycle.run_blind_cycle(
        candidate_output_path=inputs["candidate_path"],
        candidate_output_sha256=_file_sha(inputs["candidate_path"]),
        shadow_bundle_path=inputs["shadow_path"],
        shadow_bundle_sha256=_file_sha(inputs["shadow_path"]),
        cycle_binding_path=binding_path,
        cycle_binding_sha256=binding_receipt.file_sha256,
        reference_isolation_report_path=isolation_path,
        reference_isolation_report_sha256=(
            isolation_receipt["file_sha256"]
        ),
        evidence_output_path=tmp_path / "cycle-evidence.json",
        trial_state_output_path=tmp_path / "trial-state.json",
    )
    assert result.trial_advanced is True
    assert result.controlled_negative is False


def test_strict_private_inputs_and_layer_paths_fail_closed(
    tmp_path: Path,
) -> None:
    inputs = _cycle_fixture(tmp_path / "valid")
    non_private = tmp_path / "trial-world-readable.json"
    non_private.write_text(
        inputs["trial_path"].read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    non_private.chmod(0o644)
    with pytest.raises(BlindBindingError, match="mode 0600"):
        write_blind_input_manifest(
            tmp_path / "manifest-non-private.json",
            trial_metadata_path=non_private,
            current_record_path=inputs["current_record"].path,
            candidate_output_path=inputs["candidate_path"],
            current_snapshot_path=inputs["snapshot_path"],
            shadow_bundle_path=inputs["shadow_path"],
        )

    protected_dir = tmp_path / "sealed_reference"
    protected_dir.mkdir()
    protected_trial = protected_dir / "trial.json"
    _private_json(
        protected_trial,
        json.loads(inputs["trial_path"].read_text(encoding="utf-8")),
    )
    with pytest.raises(BlindBindingError, match="protected"):
        write_blind_input_manifest(
            tmp_path / "manifest-protected.json",
            trial_metadata_path=protected_trial,
            current_record_path=inputs["current_record"].path,
            candidate_output_path=inputs["candidate_path"],
            current_snapshot_path=inputs["snapshot_path"],
            shadow_bundle_path=inputs["shadow_path"],
        )

    duplicate = tmp_path / "trial-duplicate.json"
    duplicate.write_text(
        '{"schema_version":"x","schema_version":"y"}\n',
        encoding="utf-8",
    )
    duplicate.chmod(0o600)
    with pytest.raises(BlindBindingError, match="duplicate"):
        write_blind_input_manifest(
            tmp_path / "manifest-duplicate.json",
            trial_metadata_path=duplicate,
            current_record_path=inputs["current_record"].path,
            candidate_output_path=inputs["candidate_path"],
            current_snapshot_path=inputs["snapshot_path"],
            shadow_bundle_path=inputs["shadow_path"],
        )

    legacy = json.loads(inputs["trial_path"].read_text(encoding="utf-8"))
    legacy["schema_version"] = "task035e.blind-trial-metadata.v1"
    legacy_unsigned = dict(legacy)
    legacy_unsigned.pop("metadata_payload_sha256")
    legacy["metadata_payload_sha256"] = _canonical_sha(legacy_unsigned)
    legacy_path = tmp_path / "trial-v1.json"
    _private_json(legacy_path, legacy)
    with pytest.raises(BlindBindingError, match="fixed contract differs"):
        write_blind_input_manifest(
            tmp_path / "manifest-v1.json",
            trial_metadata_path=legacy_path,
            current_record_path=inputs["current_record"].path,
            candidate_output_path=inputs["candidate_path"],
            current_snapshot_path=inputs["snapshot_path"],
            shadow_bundle_path=inputs["shadow_path"],
        )


def test_flat_internal_gates_and_rebound_authority_identity_fail_closed(
    tmp_path: Path,
) -> None:
    inputs = _cycle_fixture(tmp_path)
    context = blind_bindings._cycle_context(
        trial_metadata_path=inputs["trial_path"],
        current_record_path=inputs["current_record"].path,
        candidate_output_path=inputs["candidate_path"],
        current_snapshot_path=inputs["snapshot_path"],
        shadow_bundle_path=inputs["shadow_path"],
    )
    legacy = tmp_path / "legacy-flat-internal-gates.json"
    _private_json(
        legacy,
        {
            "schema_version": "task035e.blind-internal-gates-input.v1",
            **dict(
                json.loads(
                    inputs["gates_path"].read_text(encoding="utf-8")
                )["gates"]
            ),
        },
    )
    with pytest.raises(BlindBindingError, match="closed schema"):
        blind_bindings._internal_gates(legacy, context=context)

    tampered = json.loads(
        inputs["gates_path"].read_text(encoding="utf-8")
    )
    tampered["candidate_identity"][
        "watchdog_record_file_sha256"
    ] = "f" * 64
    unsigned = dict(tampered)
    unsigned.pop("authority_sha256")
    tampered["authority_sha256"] = gate_authority._json_sha256(
        unsigned,
        namespace=gate_authority.AUTHORITY_NAMESPACE,
    )
    rebound = tmp_path / "rebound-internal-gate-authority.json"
    _private_json(rebound, tampered)
    with pytest.raises(
        BlindBindingError,
        match="watchdog_record_file_sha256 differs",
    ):
        blind_bindings._internal_gates(rebound, context=context)


def test_binding_producer_is_safe_as_an_isolation_entrypoint() -> None:
    root = Path(blind_cycle.__file__).resolve().parents[1]
    report = scan_blind_controller(
        root / "src/adaptivity/blind_controller",
        source_root=root,
        source_entrypoints=(
            root / "benchmarks/task035e_blind_bindings.py",
        ),
    )

    assert report["pass"] is True
    assert report["findings"] == []
