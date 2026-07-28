from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import stat
from typing import Any

import pytest

import benchmarks.task035e_blind_cycle as blind_cycle
import benchmarks.task035e_internal_gate_authority as gate_authority
from benchmarks.task035e_blind_cycle import (
    BlindCycleArtifactError,
    candidate_order_applicability_audit,
    goal_vector_from_candidate_output,
    load_cycle_evidence,
    load_trial_state,
    run_blind_cycle,
)
from benchmarks.task035e_reference_leak_checker import (
    FORMAL_BLIND_ENTRYPOINTS,
    build_reference_leak_report,
    write_reference_leak_report_artifact,
)
from src.adaptivity.blind_controller import (
    FIXED_ORDER_KEYS,
    FORMAL_FIELD_COMPLEX_NAMES,
    FORMAL_FIELD_SCALAR_NAMES,
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
    FORMAL_TOTAL_NAMES,
    GoalVector,
    ShadowCost,
    StabilityRepeatVerification,
    build_unmeasured_h_level3_saturation_authority,
    build_unmeasured_p6_saturation_authority,
    build_shadow_action,
    h_level3_saturation_authority_payload,
    p6_saturation_authority_payload,
    stability_repeat_verification_payload,
)
from src.adaptivity.blind_controller.manifest import build_cycle_manifest


SOURCE_SHA = "a" * 40
MESH_SHA = "1" * 64
DEGREE_SHA = "2" * 64
SOLUTION_SHA = "3" * 64
RESIDUAL_SHA = "4" * 64
PHYSICAL_SHA = "5" * 64
PLAN_FILE_SHA = "6" * 64
PLAN_CONTENT_SHA = "7" * 64
STATE_SHA = "8" * 64
PLAN_SOLVER_CONTENT_SHA = "a" * 64


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: object) -> str:
    path.write_text(
        json.dumps(value, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    return _file_sha256(path)


def _outer(schema: str, payload: dict[str, Any]) -> dict[str, Any]:
    assert payload["schema_version"] == schema
    return {
        "schema_version": schema,
        "sha256": _canonical_sha256(payload),
        "payload": payload,
    }


def _complex(real: float, imag: float) -> dict[str, float]:
    return {"real": real, "imag": imag}


def _candidate_payload() -> dict[str, Any]:
    orders = []
    for index, (port, m, n) in enumerate(FIXED_ORDER_KEYS):
        value = float(index + 1)
        orders.append(
            {
                "port": port,
                "m": m,
                "n": n,
                "propagating": True,
                "total_power": value * 1.0e-4,
                "co_polarized_amplitude": _complex(
                    value * 1.0e-2,
                    -value * 5.0e-3,
                ),
                "cross_polarized_power": value * 1.0e-8,
                "cross_polarized_amplitude": _complex(
                    value * 1.0e-4,
                    -value * 5.0e-5,
                ),
                "kz": _complex(0.2 + value * 1.0e-3, 0.0),
                "admittance": _complex(0.4 + value * 1.0e-3, 0.0),
                "normalization_identity": f"sha256:{'6' * 64}",
            }
        )
    scalar_values = {
        "R00_total": 0.2,
        "R_total": 0.3,
        "T_total": 0.4,
        "A_closure": 0.3,
        "A_volume": 0.3,
        "interface_probe_l2": 1.0,
        "volume_probe_l2": 2.0,
    }
    complex_values = {
        "interface_probe_complex": _complex(0.25, -0.125),
        "volume_probe_complex": _complex(0.5, -0.25),
    }
    assert set(FORMAL_TOTAL_NAMES) <= set(scalar_values)
    assert set(FORMAL_FIELD_SCALAR_NAMES) <= set(scalar_values)
    assert set(FORMAL_FIELD_COMPLEX_NAMES) == set(complex_values)
    return {
        "schema_version": blind_cycle.CANDIDATE_OUTPUT_SCHEMA,
        "orders": orders,
        "scalar_observations": [
            {"name": name, "value": value}
            for name, value in scalar_values.items()
        ],
        "complex_observations": [
            {"name": name, "value": value}
            for name, value in complex_values.items()
        ],
        "full_explicit_true_residual": 1.0e-12,
    }


def _action_row(
    *,
    action_id: str,
    kind: str,
    target_id: str,
    current: GoalVector,
    delta: float = 1.0e-3,
) -> dict[str, Any]:
    current_values = current.by_id
    shadow_values = {
        goal_id: current_values[goal_id] + delta
        for goal_id in FORMAL_GOAL_IDS
    }
    shadow = GoalVector.from_mapping(shadow_values)
    deltas = {
        goal_id: shadow_values[goal_id] - current_values[goal_id]
        for goal_id in FORMAL_GOAL_IDS
    }
    cost = ShadowCost(20, 10, 100, 200, 1024)
    added_leaves = 7 if kind == "h-refine" else 0
    next_mesh_sha = "a" * 64 if kind == "h-refine" else MESH_SHA
    next_degree_sha = "b" * 64
    action = build_shadow_action(
        action_id=action_id,
        kind=kind,
        target_ids=(target_id,),
        current=current,
        shadow=shadow,
        signed_dwr_delta=deltas,
        cost=cost,
        sign_consistent=True,
        transition_action_sha256="9" * 64,
        transition_action_file_sha256="a" * 64,
        transition_action_identity_sha256="b" * 64,
        next_mesh_forest_sha256=next_mesh_sha,
        next_degree_map_sha256=next_degree_sha,
        actual_added_leaf_count=added_leaves,
    )
    return {
        "action_id": action_id,
        "kind": kind,
        "target_ids": [target_id],
        "current_goal_sha256": current.sha256,
        "shadow_goals": shadow_values,
        "signed_dwr_delta": deltas,
        "cost": {
            name: getattr(cost, name)
            for name in ShadowCost.__dataclass_fields__
        },
        "sign_consistent": True,
        "actual_added_leaf_count": added_leaves,
        "transition_action_sha256": action.transition_action_sha256,
        "transition_action_file_sha256": (
            action.transition_action_file_sha256
        ),
        "transition_action_identity_sha256": (
            action.transition_action_identity_sha256
        ),
        "next_mesh_forest_sha256": action.next_mesh_forest_sha256,
        "next_degree_map_sha256": action.next_degree_map_sha256,
        "action_sha256": action.action_sha256,
        "external_evidence": {
            "actual_shadow_solve": True,
            "actual_dwr_evaluation": True,
            "shadow_output_sha256": "7" * 64,
            "dwr_evidence_sha256": "8" * 64,
            # The topology/degree transition and the controller shadow action
            # use different closed schemas and therefore different hashes.
            "transition_action_sha256": "9" * 64,
            "transition_action_file_sha256": "a" * 64,
            "transition_action_identity_sha256": "b" * 64,
            "transition_action_representation": "plain",
            "current_watchdog_record_sha256": "c" * 64,
            "shadow_watchdog_record_sha256": "d" * 64,
            "current_plan_file_sha256": "e" * 64,
            "shadow_plan_file_sha256": "f" * 64,
            "from_leaf_catalog_sha256": MESH_SHA,
            "from_cell_degree_plan_sha256": DEGREE_SHA,
            "next_leaf_catalog_sha256": next_mesh_sha,
            "next_cell_degree_plan_sha256": next_degree_sha,
            "goal_marking_file_sha256": "1" * 64,
            "goal_marking_payload_sha256": "2" * 64,
            "goal_marking_selection_role": "production_candidate",
            "verification_prediction_file_sha256": "3" * 64,
            "verification_prediction_payload_sha256": "4" * 64,
            "verification_prediction_marking_file_sha256": "1" * 64,
            "verification_prediction_marking_payload_sha256": "2" * 64,
            "selected_shadow_global_dwr_sha256": "5" * 64,
            "signed_structural_delta": {
                name: getattr(cost, name)
                for name in ShadowCost.__dataclass_fields__
            },
            "measured_structural_benefit": {
                name: 0 for name in ShadowCost.__dataclass_fields__
            },
        },
    }


def _shadow_payload(
    candidate: dict[str, Any],
    *,
    missing_dwr: bool,
    neutral: bool = False,
) -> dict[str, Any]:
    current = goal_vector_from_candidate_output(candidate)
    p_action = _action_row(
        action_id="p-up-cell-1",
        kind="p-up",
        target_id="cell:1",
        current=current,
        delta=0.0 if neutral else 1.0e-3,
    )
    h_action = _action_row(
        action_id="h-refine-root-9",
        kind="h-refine",
        target_id="root:9",
        current=current,
        delta=0.0 if neutral else 1.0e-3,
    )
    if missing_dwr:
        p_action["signed_dwr_delta"].pop(FORMAL_GOAL_IDS[-1])
    p6_saturation = build_unmeasured_p6_saturation_authority(
        p6_target_ids=(),
        current_plan_file_sha256=PLAN_FILE_SHA,
        current_mesh_forest_sha256=MESH_SHA,
        current_degree_map_sha256=DEGREE_SHA,
    )
    h_level3_saturation = build_unmeasured_h_level3_saturation_authority(
        level_two_target_ids=(),
        periodic_orbit_ids=(),
        orbit_catalog_sha256="e" * 64,
        current_plan_file_sha256=PLAN_FILE_SHA,
        current_mesh_forest_sha256=MESH_SHA,
        current_degree_map_sha256=DEGREE_SHA,
    )
    return {
        "schema_version": blind_cycle.SHADOW_BUNDLE_SCHEMA,
        "producer_role": "external_actual_shadow_dwr_solver",
        "source_sha": SOURCE_SHA,
        "mpi_size": 8,
        "trial_id": "blind-path-a",
        "cycle_index": 0,
        "mesh_forest_sha256": MESH_SHA,
        "degree_map_sha256": DEGREE_SHA,
        "complete_output_sha256": _canonical_sha256(candidate),
        "current_goal_sha256": current.sha256,
        "actual_shadow_solves": True,
        "actual_dwr_evaluations": True,
        "synthetic": False,
        "reference_derived": False,
        "p6_saturation": p6_saturation_authority_payload(
            p6_saturation
        ),
        "h_level3_saturation": h_level3_saturation_authority_payload(
            h_level3_saturation
        ),
        "p_actions": [p_action],
        "h_actions": [h_action],
    }


def _inventory() -> dict[str, int]:
    return {
        "active_dofs": 1_000,
        "rows": 800,
        "matrix_nnz": 20_000,
        "factor_nnz": 50_000,
        "solver_peak_bytes": 1_000_000,
    }


def _internal_gate_authority(
    *,
    source_sha: str,
    trial_id: str,
    cycle_index: int,
    candidate_record_file_sha256: str,
    candidate_output_file_sha256: str,
    candidate_output_payload_sha256: str,
    plan_file_sha256: str,
    plan_payload_sha256: str,
    mesh_forest_sha256: str,
    degree_map_sha256: str,
    snapshot_file_sha256: str,
    snapshot_payload_sha256: str,
    snapshot_full_residual_sha256: str,
    full_explicit_residual: float = 1.0e-12,
    energy_closure_error: float = 1.0e-12,
    absorption_volume: float = 0.3,
) -> dict[str, Any]:
    """Build a closed validator fixture without caller-authored Gate input."""

    gates = {
        "full_explicit_residual": full_explicit_residual,
        "energy_closure_error": energy_closure_error,
        "absorption_volume": absorption_volume,
        "floquet_residual_pass": True,
        "hanging_residual_pass": True,
        "serial_mpi_identity_pass": False,
        "multilevel_mesh_pass": False,
        "separated_patch_count": 0,
        "all_local_levels_present": False,
        "algebraic_budget_fraction": 1.0,
        "dtn_budget_fraction": 1.0,
        "postprocess_budget_fraction": 1.0,
    }
    empty_sha = gate_authority._json_sha256({})
    candidate_identity = {
        "watchdog_record_file_sha256": candidate_record_file_sha256,
        "candidate_output_file_sha256": candidate_output_file_sha256,
        "candidate_output_payload_sha256": (
            candidate_output_payload_sha256
        ),
        "plan_file_sha256": plan_file_sha256,
        "plan_payload_sha256": plan_payload_sha256,
        "mesh_forest_sha256": mesh_forest_sha256,
        "degree_map_sha256": degree_map_sha256,
        "current_snapshot_file_sha256": snapshot_file_sha256,
        "current_snapshot_payload_sha256": snapshot_payload_sha256,
        "snapshot_rank_bound_identity_sha256": "d" * 64,
        "snapshot_full_residual_sha256": (
            snapshot_full_residual_sha256
        ),
        "raw_artifact_sha256": {},
        "raw_artifact_inventory_sha256": empty_sha,
        "structural_inventory": {},
    }
    probe_identities = []
    for index, kind in enumerate(("algebraic", "dtn", "postprocess"), 1):
        probe_identities.append(
            {
                "kind": kind,
                "watchdog_record_file_sha256": f"{index:064x}",
                "candidate_output_payload_sha256": f"{index + 3:064x}",
                "config_sha256": f"{index + 6:064x}",
                "plan_file_sha256": f"{index + 9:064x}",
                "mesh_forest_sha256": mesh_forest_sha256,
                "degree_map_sha256": degree_map_sha256,
                "raw_artifact_sha256": {},
                "raw_artifact_inventory_sha256": empty_sha,
                "structural_inventory": {},
            }
        )
    snapshot_checks = {
        name: True for name in gate_authority._SNAPSHOT_CHECK_KEYS
    }
    constraint_checks = {
        name: True for name in gate_authority._CONSTRAINT_CHECK_KEYS
    }
    multilevel_checks = {
        name: False for name in gate_authority._MULTILEVEL_CHECK_KEYS
    }
    budgets = {
        kind: {
            "kind": kind,
            "budget_fraction": 1.0,
            "qualified_comparison": False,
        }
        for kind in ("algebraic", "dtn", "postprocess")
    }
    unsigned = {
        "schema_version": gate_authority.AUTHORITY_SCHEMA,
        "status": "internal_gate_authority_recomputed",
        "classification": gate_authority.FINAL_AUTHORITY_CLASSIFICATION,
        "source_sha": source_sha,
        "trial_id": trial_id,
        "cycle_index": cycle_index,
        "mpi_size": 8,
        "candidate_identity": candidate_identity,
        "probe_identities": probe_identities,
        "measurements": {
            "floquet": {},
            "hanging": {},
            "mpi_identity": {"status": "not_run"},
            "multilevel": {"separated_patch_count": 0},
            "budgets": budgets,
        },
        "recomputed_checks": {
            "snapshot": snapshot_checks,
            "constraint": constraint_checks,
            "multilevel": multilevel_checks,
            "budget_probe_qualified": {
                kind: False
                for kind in ("algebraic", "dtn", "postprocess")
            },
            "mpi8_candidate_plan_snapshot_identity": True,
            "serial_mpi1_same_plan_output_identity": False,
        },
        "gates": gates,
        "producer": gate_authority._producer_identity(),
    }
    authority = {
        **unsigned,
        "authority_sha256": gate_authority._json_sha256(
            unsigned,
            namespace=gate_authority.AUTHORITY_NAMESPACE,
        ),
    }
    gate_authority.validate_internal_gate_authority(authority)
    return authority


def _rebind_internal_gate_authority(
    binding: dict[str, Any],
) -> None:
    old = binding.get("internal_gates")
    gate_values = (
        old.get("gates")
        if isinstance(old, dict) and isinstance(old.get("gates"), dict)
        else {}
    )
    trial = binding["trial"]
    binding["internal_gates"] = _internal_gate_authority(
        source_sha=binding["source_sha"],
        trial_id=trial["trial_id"],
        cycle_index=binding["cycle_index"],
        candidate_record_file_sha256=(
            binding["candidate_record_file_sha256"]
        ),
        candidate_output_file_sha256=(
            binding["candidate_output_file_sha256"]
        ),
        candidate_output_payload_sha256=(
            binding["complete_output_sha256"]
        ),
        plan_file_sha256=binding["plan_file_sha256"],
        plan_payload_sha256=binding["plan_content_sha256"],
        mesh_forest_sha256=binding["mesh_forest_sha256"],
        degree_map_sha256=binding["degree_map_sha256"],
        snapshot_file_sha256=binding["current_snapshot_file_sha256"],
        snapshot_payload_sha256=binding["solution_snapshot_sha256"],
        snapshot_full_residual_sha256=binding["full_residual_sha256"],
        full_explicit_residual=float(
            gate_values.get("full_explicit_residual", 1.0e-12)
        ),
        energy_closure_error=float(
            gate_values.get("energy_closure_error", 1.0e-12)
        ),
        absorption_volume=float(
            gate_values.get("absorption_volume", 0.3)
        ),
    )


def _binding_payload(
    candidate: dict[str, Any],
    *,
    candidate_file_sha256: str,
    shadow_file_sha256: str,
) -> dict[str, Any]:
    inventory = _inventory()
    inventory_payload = {
        "schema_version": "task035e.resource-authority.v1",
        **inventory,
        "swap_peak_bytes": 0,
        "mpi_size": 8,
        "same_solver_lifecycle_telemetry": True,
    }
    payload = {
        "schema_version": blind_cycle.CYCLE_BINDING_SCHEMA,
        "trial": {
            "trial_id": "blind-path-a",
            "algorithm_id": "reference-blind-multilevel-hp-v1",
            "initial_path_id": "fixed-coarse-path-a",
            "initial_mesh_forest_sha256": MESH_SHA,
            "physical_identity_sha256": PHYSICAL_SHA,
            "maximum_cycles": 6,
        },
        "source_sha": SOURCE_SHA,
        "mpi_size": 8,
        "cycle_index": 0,
        "mesh_forest_sha256": MESH_SHA,
        "degree_map_sha256": DEGREE_SHA,
        "plan_file_sha256": PLAN_FILE_SHA,
        "plan_content_sha256": PLAN_CONTENT_SHA,
        "plan_solver_content_sha256": PLAN_SOLVER_CONTENT_SHA,
        "state_sha256": STATE_SHA,
        "solution_snapshot_sha256": SOLUTION_SHA,
        "complete_output_sha256": _canonical_sha256(candidate),
        "full_residual_sha256": RESIDUAL_SHA,
        "candidate_record_file_sha256": "9" * 64,
        "candidate_output_file_sha256": candidate_file_sha256,
        "current_snapshot_file_sha256": "0" * 64,
        "shadow_bundle_file_sha256": shadow_file_sha256,
        "resource_inventory": inventory,
        "resource_inventory_sha256": _canonical_sha256(
            inventory_payload
        ),
        "transition": {
            "previous_trial_state_file_sha256": None,
            "previous_cycle_certificate_sha256": None,
            "executed_action_verifications": [],
            "stability_repeat_verification": None,
        },
    }
    _rebind_internal_gate_authority(payload)
    return payload


def _attach_isolation_report(
    inputs: dict[str, Any],
    *,
    shadow_file_sha256: str,
    binding_payload: dict[str, Any],
) -> None:
    trial = binding_payload["trial"]
    manifest = build_cycle_manifest(
        trial_id=trial["trial_id"],
        algorithm_id=trial["algorithm_id"],
        source_sha=binding_payload["source_sha"],
        initial_path_id=trial["initial_path_id"],
        maximum_cycles=trial["maximum_cycles"],
        cycle_index=binding_payload["cycle_index"],
        state=blind_cycle.REFERENCE_ISOLATION_MANIFEST_STATE,
        mesh_forest_sha256=binding_payload["mesh_forest_sha256"],
        degree_map_sha256=binding_payload["degree_map_sha256"],
        solution_snapshot_sha256=(
            binding_payload["solution_snapshot_sha256"]
        ),
        goal_inventory_sha256=FORMAL_GOAL_INVENTORY_SHA256,
        full_residual_sha256=binding_payload["full_residual_sha256"],
        adjoint_bundle_sha256=shadow_file_sha256,
        p_shadow_bundle_sha256=shadow_file_sha256,
        h_shadow_bundle_sha256=shadow_file_sha256,
        resource_inventory_sha256=(
            binding_payload["resource_inventory_sha256"]
        ),
    )
    root = Path(blind_cycle.__file__).resolve().parents[1]
    controller = root / "src/adaptivity/blind_controller"
    audit_entry = controller / "manifest.py"
    protected = inputs["cycle_binding_path"].parent / "protected-evaluator"
    protected.mkdir(exist_ok=True)
    report = build_reference_leak_report(
        controller_package=controller,
        source_root=root,
        source_entrypoints=tuple(
            root / relative for relative in FORMAL_BLIND_ENTRYPOINTS
        ),
        manifest=manifest,
        audit_entrypoint=audit_entry,
        audit_protected_paths=(protected,),
        audit_cwd=root,
    )
    assert report["pass"] is True
    index = 0
    while True:
        report_path = (
            inputs["cycle_binding_path"].parent
            / f"isolation-report-{index}.json"
        )
        if not report_path.exists():
            break
        index += 1
    receipt = write_reference_leak_report_artifact(report_path, report)
    inputs["reference_isolation_report_path"] = report_path
    inputs["reference_isolation_report_sha256"] = receipt["file_sha256"]
    binding_payload["reference_isolation_report_file_sha256"] = receipt[
        "file_sha256"
    ]


def _inputs(
    tmp_path: Path,
    *,
    missing_dwr: bool = False,
    neutral: bool = False,
) -> dict[str, Any]:
    candidate = _candidate_payload()
    candidate_path = tmp_path / "candidate.json"
    candidate_file_sha = _write_json(candidate_path, candidate)

    shadow_payload = _shadow_payload(
        candidate,
        missing_dwr=missing_dwr,
        neutral=neutral,
    )
    shadow_path = tmp_path / "shadow.json"
    shadow_file_sha = _write_json(
        shadow_path,
        _outer(blind_cycle.SHADOW_BUNDLE_SCHEMA, shadow_payload),
    )

    binding_payload = _binding_payload(
        candidate,
        candidate_file_sha256=candidate_file_sha,
        shadow_file_sha256=shadow_file_sha,
    )
    binding_path = tmp_path / "binding.json"
    result = {
        "candidate_output_path": candidate_path,
        "candidate_output_sha256": candidate_file_sha,
        "shadow_bundle_path": shadow_path,
        "shadow_bundle_sha256": shadow_file_sha,
        "cycle_binding_path": binding_path,
        "evidence_output_path": tmp_path / "cycle-evidence.json",
        "trial_state_output_path": tmp_path / "trial-state.json",
    }
    _attach_isolation_report(
        result,
        shadow_file_sha256=shadow_file_sha,
        binding_payload=binding_payload,
    )
    result["cycle_binding_sha256"] = _write_json(
        binding_path,
        _outer(blind_cycle.CYCLE_BINDING_SCHEMA, binding_payload),
    )
    return result


def _rewrite_outer(path: Path, schema: str, payload: dict[str, Any]) -> str:
    return _write_json(path, _outer(schema, payload))


def _no_action_continuation_inputs(
    tmp_path: Path,
    *,
    previous_receipt: Any,
    drift_field: str | None = None,
) -> dict[str, Any]:
    tmp_path.mkdir()
    inputs = _inputs(tmp_path, neutral=True)
    shadow_outer = json.loads(
        inputs["shadow_bundle_path"].read_text(encoding="utf-8")
    )
    shadow_payload = shadow_outer["payload"]
    shadow_payload["cycle_index"] = 1
    shadow_payload["p6_saturation"] = p6_saturation_authority_payload(
        build_unmeasured_p6_saturation_authority(
            p6_target_ids=(),
            current_plan_file_sha256="b" * 64,
            current_mesh_forest_sha256=MESH_SHA,
            current_degree_map_sha256=DEGREE_SHA,
        )
    )
    shadow_payload["h_level3_saturation"] = (
        h_level3_saturation_authority_payload(
            build_unmeasured_h_level3_saturation_authority(
                level_two_target_ids=(),
                periodic_orbit_ids=(),
                orbit_catalog_sha256="e" * 64,
                current_plan_file_sha256="b" * 64,
                current_mesh_forest_sha256=MESH_SHA,
                current_degree_map_sha256=DEGREE_SHA,
            )
        )
    )
    shadow_sha = _rewrite_outer(
        inputs["shadow_bundle_path"],
        blind_cycle.SHADOW_BUNDLE_SCHEMA,
        shadow_payload,
    )
    inputs["shadow_bundle_sha256"] = shadow_sha

    binding_outer = json.loads(
        inputs["cycle_binding_path"].read_text(encoding="utf-8")
    )
    binding_payload = binding_outer["payload"]
    binding_payload["cycle_index"] = 1
    binding_payload["shadow_bundle_file_sha256"] = shadow_sha
    previous = load_trial_state(
        previous_receipt.trial_state_path,
        previous_receipt.trial_state_file_sha256,
    ).results[-1]
    binding_payload["plan_file_sha256"] = "b" * 64
    binding_payload["plan_content_sha256"] = "c" * 64
    binding_payload["plan_solver_content_sha256"] = (
        previous.plan_solver_content_sha256
    )
    binding_payload["state_sha256"] = "d" * 64
    binding_payload["solution_snapshot_sha256"] = "e" * 64
    binding_payload["candidate_record_file_sha256"] = "f" * 64
    repeat = StabilityRepeatVerification(
        action_id="cycle1.p-keep.stability-repeat",
        action_kind="p-keep",
        action_sha256="0" * 64,
        action_file_sha256="a" * 64,
        action_identity_sha256="b" * 64,
        from_state_sha256=previous.state_sha256,
        next_state_sha256=binding_payload["state_sha256"],
        previous_plan_file_sha256=previous.plan_file_sha256,
        previous_plan_content_sha256=previous.plan_content_sha256,
        previous_plan_solver_content_sha256=(
            previous.plan_solver_content_sha256
        ),
        next_plan_file_sha256=binding_payload["plan_file_sha256"],
        next_plan_content_sha256=binding_payload[
            "plan_content_sha256"
        ],
        next_plan_solver_content_sha256=binding_payload[
            "plan_solver_content_sha256"
        ],
        previous_mesh_forest_sha256=previous.mesh_forest_sha256,
        next_mesh_forest_sha256=binding_payload["mesh_forest_sha256"],
        previous_degree_map_sha256=previous.degree_map_sha256,
        next_degree_map_sha256=binding_payload["degree_map_sha256"],
        before_solution_snapshot_sha256=(
            previous.solution_snapshot_sha256
        ),
        after_solution_snapshot_sha256=binding_payload[
            "solution_snapshot_sha256"
        ],
        before_watchdog_record_file_sha256=(
            previous.watchdog_record_file_sha256
        ),
        after_watchdog_record_file_sha256=binding_payload[
            "candidate_record_file_sha256"
        ],
    )
    binding_payload["transition"] = {
        "previous_trial_state_file_sha256": (
            previous_receipt.trial_state_file_sha256
        ),
        "previous_cycle_certificate_sha256": (
            previous.internal_certificate_sha256
        ),
        "executed_action_verifications": [],
        "stability_repeat_verification": (
            stability_repeat_verification_payload(repeat)
        ),
    }
    if drift_field is not None:
        binding_payload[drift_field] = "9" * 64
    _rebind_internal_gate_authority(binding_payload)
    _attach_isolation_report(
        inputs,
        shadow_file_sha256=shadow_sha,
        binding_payload=binding_payload,
    )
    inputs["cycle_binding_sha256"] = _rewrite_outer(
        inputs["cycle_binding_path"],
        blind_cycle.CYCLE_BINDING_SCHEMA,
        binding_payload,
    )
    inputs["prior_trial_state_path"] = previous_receipt.trial_state_path
    inputs["prior_trial_state_sha256"] = (
        previous_receipt.trial_state_file_sha256
    )
    return inputs


def _rebind_shadow(
    inputs: dict[str, Any],
    shadow_payload: dict[str, Any],
) -> None:
    shadow_sha = _rewrite_outer(
        inputs["shadow_bundle_path"],
        blind_cycle.SHADOW_BUNDLE_SCHEMA,
        shadow_payload,
    )
    binding_outer = json.loads(
        inputs["cycle_binding_path"].read_text(encoding="utf-8")
    )
    binding_payload = binding_outer["payload"]
    binding_payload["shadow_bundle_file_sha256"] = shadow_sha
    inputs["shadow_bundle_sha256"] = shadow_sha
    _attach_isolation_report(
        inputs,
        shadow_file_sha256=shadow_sha,
        binding_payload=binding_payload,
    )
    inputs["cycle_binding_sha256"] = _rewrite_outer(
        inputs["cycle_binding_path"],
        blind_cycle.CYCLE_BINDING_SCHEMA,
        binding_payload,
    )


def test_candidate_output_builds_exact_59_goal_vector() -> None:
    goals = goal_vector_from_candidate_output(_candidate_payload())

    assert len(goals.values) == 59
    assert tuple(row.goal_id for row in goals.values) == FORMAL_GOAL_IDS
    assert goals.by_id["top:m0:n0:power"] == pytest.approx(1.0e-4)
    assert goals.by_id["top:m0:n0:co_amp_imag"] == pytest.approx(-5.0e-3)
    assert goals.by_id["scalar/R_total"] == pytest.approx(0.3)
    assert goals.by_id["complex/volume_probe_complex/imag"] == pytest.approx(
        -0.25
    )


def test_evanescent_fixed_order_maps_null_power_to_audited_zero() -> None:
    candidate = _candidate_payload()
    order = candidate["orders"][3]
    order["propagating"] = False
    order["total_power"] = None
    order["cross_polarized_power"] = None

    goals = goal_vector_from_candidate_output(candidate)
    audit = candidate_order_applicability_audit(candidate)
    row = audit[3]

    assert len(goals.values) == 59
    assert tuple(value.goal_id for value in goals.values) == FORMAL_GOAL_IDS
    assert goals.by_id[row["goal_id"]] == 0.0
    assert row["propagating"] is False
    assert row["power_applicable"] is False
    assert row["input_total_power_state"] == "null_not_applicable"
    assert row["input_cross_power_state"] == "null_not_applicable"
    assert row["mapping"] == "explicit_not_applicable_to_formal_zero"


@pytest.mark.parametrize(
    ("propagating", "total_power", "cross_power", "message"),
    (
        (None, None, None, "propagating must be boolean"),
        (False, 0.0, None, "evanescent order powers must be null"),
        (False, None, 0.0, "evanescent order powers must be null"),
        (True, None, 0.0, "total_power"),
        (True, 0.0, None, "cross_power"),
        (True, -1.0e-9, 0.0, "must be nonnegative"),
    ),
)
def test_candidate_power_applicability_is_fail_closed(
    propagating: object,
    total_power: object,
    cross_power: object,
    message: str,
) -> None:
    candidate = _candidate_payload()
    order = candidate["orders"][0]
    order["propagating"] = propagating
    order["total_power"] = total_power
    order["cross_polarized_power"] = cross_power

    with pytest.raises(BlindCycleArtifactError, match=message):
        goal_vector_from_candidate_output(candidate)


def test_cycle_writes_mode_0600_and_replays_independently(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)

    receipt = run_blind_cycle(**inputs)

    assert receipt.controlled_negative is False
    assert receipt.trial_advanced is True
    assert receipt.status == "accepted_action_selected"
    assert stat.S_IMODE(receipt.evidence_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(receipt.trial_state_path.stat().st_mode) == 0o600

    evidence = load_cycle_evidence(
        receipt.evidence_path,
        receipt.evidence_file_sha256,
    )
    trial = load_trial_state(
        receipt.trial_state_path,
        receipt.trial_state_file_sha256,
    )
    assert evidence["classification"] == "blind_cycle_decision"
    assert len(evidence["order_applicability_audit"]) == len(
        FIXED_ORDER_KEYS
    )
    assert evidence["reference_isolation_manifest_sha256"] is not None
    assert (
        evidence["reference_isolation_report_payload_sha256"] is not None
    )
    assert evidence["result_certificate_sha256"] == (
        trial.results[0].internal_certificate_sha256
    )
    assert trial.results[0].selected_action_ids == ("p-up-cell-1",)
    assert (
        "single_lane_policy_without_combined_shadow_selected_p"
        in trial.results[0].reasons
    )


def test_no_action_cycle_uses_fresh_pkeep_repeat_with_same_solver_content(
    tmp_path: Path,
) -> None:
    first_dir = tmp_path / "cycle-0"
    first_dir.mkdir()
    first = run_blind_cycle(**_inputs(first_dir, neutral=True))

    assert first.status == "accepted_no_safe_action"
    first_trial = load_trial_state(
        first.trial_state_path,
        first.trial_state_file_sha256,
    )
    assert first_trial.results[-1].selected_action_bindings == ()

    second = run_blind_cycle(
        **_no_action_continuation_inputs(
            tmp_path / "cycle-1",
            previous_receipt=first,
        )
    )

    assert second.controlled_negative is False
    assert second.trial_advanced is True
    second_trial = load_trial_state(
        second.trial_state_path,
        second.trial_state_file_sha256,
    )
    assert second_trial.results[-1].accepted_current_state is True
    assert second_trial.results[-1].selected_action_bindings == ()
    repeat = second_trial.results[-1].stability_repeat_verification
    assert repeat is not None
    assert repeat.previous_plan_solver_content_sha256 == (
        repeat.next_plan_solver_content_sha256
    )
    assert repeat.previous_plan_content_sha256 != (
        repeat.next_plan_content_sha256
    )


def test_pkeep_cycle_rejects_missing_repeat_and_shadow_role_mixing(
    tmp_path: Path,
) -> None:
    first_dir = tmp_path / "cycle-0"
    first_dir.mkdir()
    first = run_blind_cycle(**_inputs(first_dir, neutral=True))

    missing = _no_action_continuation_inputs(
        tmp_path / "missing-repeat",
        previous_receipt=first,
    )
    missing_outer = json.loads(
        missing["cycle_binding_path"].read_text(encoding="utf-8")
    )
    missing_payload = missing_outer["payload"]
    missing_payload["transition"]["stability_repeat_verification"] = None
    missing["cycle_binding_sha256"] = _rewrite_outer(
        missing["cycle_binding_path"],
        blind_cycle.CYCLE_BINDING_SCHEMA,
        missing_payload,
    )
    with pytest.raises(
        BlindCycleArtifactError,
        match="requires a p-keep stability repeat",
    ):
        run_blind_cycle(**missing)

    mixed = _no_action_continuation_inputs(
        tmp_path / "mixed-role",
        previous_receipt=first,
    )
    mixed_outer = json.loads(
        mixed["cycle_binding_path"].read_text(encoding="utf-8")
    )
    mixed_payload = mixed_outer["payload"]
    zero_packet = {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    mixed_payload["transition"]["executed_action_verifications"] = [
        {
            "action_id": "not-a-stability-repeat",
            "action_sha256": "0" * 64,
            "transition_action_sha256": "1" * 64,
            "transition_action_file_sha256": "2" * 64,
            "transition_action_identity_sha256": "3" * 64,
            "next_mesh_forest_sha256": mixed_payload[
                "mesh_forest_sha256"
            ],
            "next_degree_map_sha256": mixed_payload["degree_map_sha256"],
            "next_plan_file_sha256": mixed_payload["plan_file_sha256"],
            "next_plan_content_sha256": mixed_payload[
                "plan_content_sha256"
            ],
            "next_state_sha256": mixed_payload["state_sha256"],
            "before_output_sha256": "4" * 64,
            "after_output_sha256": mixed_payload["complete_output_sha256"],
            "predicted_deltas": zero_packet,
            "actual_deltas": zero_packet,
        }
    ]
    mixed["cycle_binding_sha256"] = _rewrite_outer(
        mixed["cycle_binding_path"],
        blind_cycle.CYCLE_BINDING_SCHEMA,
        mixed_payload,
    )
    with pytest.raises(
        BlindCycleArtifactError,
        match="cannot use shadow verification",
    ):
        run_blind_cycle(**mixed)


@pytest.mark.parametrize(
    "drift_field",
    (
        "mesh_forest_sha256",
        "degree_map_sha256",
        "plan_file_sha256",
        "plan_content_sha256",
        "plan_solver_content_sha256",
        "state_sha256",
        "solution_snapshot_sha256",
        "candidate_record_file_sha256",
    ),
)
def test_pkeep_cycle_rejects_any_repeat_identity_drift(
    tmp_path: Path,
    drift_field: str,
) -> None:
    first_dir = tmp_path / "cycle-0"
    first_dir.mkdir()
    first = run_blind_cycle(**_inputs(first_dir, neutral=True))

    with pytest.raises(
        BlindCycleArtifactError,
        match="stability-repeat transition/plan binding differs",
    ):
        run_blind_cycle(
            **_no_action_continuation_inputs(
                tmp_path / "cycle-1",
                previous_receipt=first,
                drift_field=drift_field,
            )
        )


def test_missing_dwr_is_preserved_as_controlled_negative(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path, missing_dwr=True)

    receipt = run_blind_cycle(**inputs)

    assert receipt.controlled_negative is True
    assert receipt.trial_advanced is False
    assert receipt.status == "input_rejected_controlled_negative"
    evidence = load_cycle_evidence(
        receipt.evidence_path,
        receipt.evidence_file_sha256,
    )
    trial = load_trial_state(
        receipt.trial_state_path,
        receipt.trial_state_file_sha256,
    )
    assert evidence["classification"] == "controlled_negative"
    assert "missing DWR" in evidence["failure"]
    assert evidence["result_certificate"] is None
    assert trial.results == ()


def test_cycle_rejects_shadow_transition_identity_drift(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    outer = json.loads(
        inputs["shadow_bundle_path"].read_text(encoding="utf-8")
    )
    payload = outer["payload"]
    payload["p_actions"][0]["next_mesh_forest_sha256"] = "f" * 64
    _rebind_shadow(inputs, payload)

    receipt = run_blind_cycle(**inputs)
    evidence = load_cycle_evidence(
        receipt.evidence_path,
        receipt.evidence_file_sha256,
    )

    assert receipt.controlled_negative is True
    assert receipt.trial_advanced is False
    assert "transition identity differs" in evidence["failure"]


def test_cycle_rejects_isolation_report_from_another_manifest(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    report_path = inputs["reference_isolation_report_path"]
    artifact = json.loads(report_path.read_text(encoding="utf-8"))
    artifact["payload"]["manifest_sha256"] = "f" * 64
    artifact["sha256"] = _canonical_sha256(artifact["payload"])
    inputs["reference_isolation_report_sha256"] = _write_json(
        report_path,
        artifact,
    )
    binding_outer = json.loads(
        inputs["cycle_binding_path"].read_text(encoding="utf-8")
    )
    binding_payload = binding_outer["payload"]
    binding_payload["reference_isolation_report_file_sha256"] = inputs[
        "reference_isolation_report_sha256"
    ]
    inputs["cycle_binding_sha256"] = _rewrite_outer(
        inputs["cycle_binding_path"],
        blind_cycle.CYCLE_BINDING_SCHEMA,
        binding_payload,
    )

    receipt = run_blind_cycle(**inputs)
    evidence = load_cycle_evidence(
        receipt.evidence_path,
        receipt.evidence_file_sha256,
    )

    assert receipt.controlled_negative is True
    assert receipt.trial_advanced is False
    assert "identity or pass differs" in evidence["failure"]
    assert evidence["reference_isolation_manifest_sha256"] is not None
    assert evidence["reference_isolation_report_payload_sha256"] is None


def test_formal_cli_requires_reference_isolation_report() -> None:
    with pytest.raises(SystemExit) as caught:
        blind_cycle.main(
            [
                "--candidate-output",
                "candidate.json",
                "--candidate-output-sha256",
                "1" * 64,
                "--shadow-bundle",
                "shadow.json",
                "--shadow-bundle-sha256",
                "2" * 64,
                "--cycle-binding",
                "binding.json",
                "--cycle-binding-sha256",
                "3" * 64,
                "--evidence-output",
                "evidence.json",
                "--trial-state-output",
                "state.json",
            ]
        )

    assert caught.value.code == 2


def test_reload_rejects_file_tampering(tmp_path: Path) -> None:
    receipt = run_blind_cycle(**_inputs(tmp_path))
    receipt.evidence_path.write_text(
        receipt.evidence_path.read_text(encoding="utf-8") + " \n",
        encoding="utf-8",
    )

    with pytest.raises(BlindCycleArtifactError, match="file SHA-256 mismatch"):
        load_cycle_evidence(
            receipt.evidence_path,
            receipt.evidence_file_sha256,
        )


@pytest.mark.parametrize(
    ("name", "value", "message"),
    (
        ("mpi_size", 4, "requires MPI8"),
        ("cycle_index", 6, "exceeds five"),
    ),
)
def test_cycle_binding_enforces_mpi8_and_indices_zero_through_five(
    tmp_path: Path,
    name: str,
    value: int,
    message: str,
) -> None:
    inputs = _inputs(tmp_path)
    binding_outer = json.loads(
        inputs["cycle_binding_path"].read_text(encoding="utf-8")
    )
    binding_payload = binding_outer["payload"]
    binding_payload[name] = value
    inputs["cycle_binding_sha256"] = _rewrite_outer(
        inputs["cycle_binding_path"],
        blind_cycle.CYCLE_BINDING_SCHEMA,
        binding_payload,
    )

    with pytest.raises(BlindCycleArtifactError, match=message):
        run_blind_cycle(**inputs)


def test_cycle_binding_rejects_legacy_flat_internal_gates(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    binding_outer = json.loads(
        inputs["cycle_binding_path"].read_text(encoding="utf-8")
    )
    binding_payload = binding_outer["payload"]
    authority = binding_payload["internal_gates"]
    binding_payload["internal_gates"] = {
        "schema_version": "task035e.blind-internal-gates-input.v1",
        **dict(authority["gates"]),
    }
    inputs["cycle_binding_sha256"] = _rewrite_outer(
        inputs["cycle_binding_path"],
        blind_cycle.CYCLE_BINDING_SCHEMA,
        binding_payload,
    )

    with pytest.raises(BlindCycleArtifactError, match="closed schema"):
        run_blind_cycle(**inputs)


def test_reference_derived_shadow_bundle_cannot_advance(
    tmp_path: Path,
) -> None:
    inputs = _inputs(tmp_path)
    shadow_outer = json.loads(
        inputs["shadow_bundle_path"].read_text(encoding="utf-8")
    )
    shadow_payload = shadow_outer["payload"]
    shadow_payload["reference_derived"] = True
    _rebind_shadow(inputs, shadow_payload)

    receipt = run_blind_cycle(**inputs)

    assert receipt.controlled_negative is True
    assert receipt.trial_advanced is False
    evidence = load_cycle_evidence(
        receipt.evidence_path,
        receipt.evidence_file_sha256,
    )
    assert "external-evidence role differs" in evidence["failure"]


def test_import_and_path_layer_isolation(tmp_path: Path) -> None:
    source_path = Path(blind_cycle.__file__).resolve()
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    forbidden = (
        "ref" + "erence_certifier",
        "hid" + "den_auditor",
        "sealed_" + "reference",
    )
    assert not any(
        token in module
        for token in forbidden
        for module in imported
    )
    assert not any(token in source for token in forbidden)

    inputs = _inputs(tmp_path)
    blocked = tmp_path / forbidden[1] / "cycle-evidence.json"
    inputs["evidence_output_path"] = blocked
    with pytest.raises(BlindCycleArtifactError, match="forbidden layer"):
        run_blind_cycle(**inputs)
