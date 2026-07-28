#!/usr/bin/env python3
"""Read-only wiring audit for the Task035e blind campaign stages.

The campaign runner provides immutable receipts, crash recovery, source/ABI
locking, and the one-heavy-job lock.  This module answers a different
question: whether its stage DAG currently carries enough typed artifacts and
command credit to invoke the already implemented formal producers.

It deliberately does not execute a producer or a PDE.  A formal stage
preparer must not be enabled until this audit reports ``ready``.  Keeping the
audit separate prevents an incomplete adapter from turning placeholder stage
names into apparent numerical evidence.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
import hashlib
import json
import stat
from typing import Any, Mapping, Protocol, Sequence

from benchmarks.task035e_blind_cycle import (
    load_trial_state,
)
from benchmarks.task035e_candidate_output import (
    CandidateWatchdogInput,
    adapt_candidate_output,
)
from benchmarks.task035e_blind_campaign import (
    AttemptHandle,
    BlindCampaignError,
    BlindPathIdentity,
    CampaignStage,
    CommandExecutionReceipt,
    PreparedStage,
    StageArtifactBinding,
    StageExecutionContext,
    StageResult,
)
from benchmarks.task035e_trial_metadata import load_trial_metadata
from src.adaptivity.blind_controller import (
    compare_frozen_paths,
    freeze_candidate,
)
from src.adaptivity.blind_controller.contracts import FORMAL_GOAL_IDS

STAGE_WIRING_AUDIT_SCHEMA = "task035e.blind-campaign-stage-wiring-audit.v1"
STAGE_PRODUCER_CONTRACT_SCHEMA = (
    "task035e.blind-campaign-stage-producer-contract.v1"
)
TWO_START_COMPARISON_SCHEMA = (
    "task035e.two-path-comparison-receipt.v2"
)
CANDIDATE_FREEZE_SCHEMA = (
    "task035e.blind-candidate-freeze-receipt.v2"
)
CANDIDATE_BUNDLE_SCHEMA = "task035e.frozen-candidate-audit-bundle.v1"


@dataclass(frozen=True, slots=True)
class StageProducerContract:
    """Typed artifact contract for one campaign DAG stage name."""

    stage_name: str
    producer_entrypoints: tuple[str, ...]
    required_artifact_roles: tuple[str, ...]
    provided_artifact_roles: tuple[str, ...]
    heavy_command_count_minimum: int
    heavy_command_count_maximum: int

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": STAGE_PRODUCER_CONTRACT_SCHEMA,
            "stage_name": self.stage_name,
            "producer_entrypoints": list(self.producer_entrypoints),
            "required_artifact_roles": list(self.required_artifact_roles),
            "provided_artifact_roles": list(self.provided_artifact_roles),
            "heavy_command_count_minimum": self.heavy_command_count_minimum,
            "heavy_command_count_maximum": self.heavy_command_count_maximum,
        }


@dataclass(frozen=True, slots=True)
class StageWiringIssue:
    """One fail-closed gap between the DAG and a producer contract."""

    code: str
    affected_stages: tuple[str, ...]
    explanation: str
    required_change: str

    def payload(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": "hard_blocker",
            "affected_stages": list(self.affected_stages),
            "explanation": self.explanation,
            "required_change": self.required_change,
        }


def formal_stage_contracts() -> tuple[StageProducerContract, ...]:
    """Return the current producer-level dataflow without executing it."""

    return (
        StageProducerContract(
            stage_name="initial_plan",
            producer_entrypoints=(
                "benchmarks.task035e_initial_space:"
                "write_initial_space_bundle",
                "benchmarks.task035e_trial_metadata:"
                "write_qualified_solver_config",
                "benchmarks.task035e_trial_metadata:write_trial_metadata",
            ),
            required_artifact_roles=(
                "current_plan",
                "initial_space_authority",
                "qualified_solver_config",
            ),
            provided_artifact_roles=("trial_metadata",),
            heavy_command_count_minimum=0,
            heavy_command_count_maximum=0,
        ),
        StageProducerContract(
            stage_name="current_solve",
            producer_entrypoints=(
                "benchmarks.run_task033_full3d_watchdog:main",
                "benchmarks.task035e_candidate_output:"
                "write_candidate_output",
            ),
            required_artifact_roles=(
                "current_plan",
                "trial_metadata",
            ),
            provided_artifact_roles=(
                "current_watchdog_record",
                "current_candidate_output",
                "current_snapshot",
            ),
            heavy_command_count_minimum=1,
            heavy_command_count_maximum=1,
        ),
        StageProducerContract(
            stage_name="shadow_target_discovery",
            producer_entrypoints=(
                "src.adaptivity.task035e_local_shadows:"
                "build_local_shadow_catalog",
                "benchmarks.task035e_transition_producer:"
                "write_transition_bundle",
            ),
            required_artifact_roles=(
                "current_plan",
                "current_watchdog_record",
                "current_candidate_output",
                "current_snapshot",
            ),
            provided_artifact_roles=(
                "p_discovery_targets",
                "p_discovery_transition_action",
                "p_discovery_plan",
                "h_discovery_targets",
                "h_discovery_transition_action",
                "h_discovery_plan",
            ),
            heavy_command_count_minimum=0,
            heavy_command_count_maximum=0,
        ),
        StageProducerContract(
            stage_name="p_shadow_discovery",
            producer_entrypoints=(
                "benchmarks.task035e_transition_producer:"
                "write_transition_bundle",
                "benchmarks.run_task033_full3d_watchdog:main",
                "benchmarks.task035e_candidate_output:"
                "write_candidate_output",
                "benchmarks.task035e_live_shadow_bridge:"
                "write_live_shadow_bridge",
            ),
            required_artifact_roles=(
                "current_plan",
                "current_watchdog_record",
                "current_candidate_output",
                "current_snapshot",
                "p_discovery_targets",
                "p_discovery_transition_action",
                "p_discovery_plan",
            ),
            provided_artifact_roles=(
                "p_shadow_watchdog_record",
                "p_shadow_candidate_output",
                "p_live_dwr_evidence",
            ),
            # A fully p6 current space has no legal p-up target.  The formal
            # handler must publish an explicit saturation/skip packet in that
            # case instead of launching a dummy PDE.
            heavy_command_count_minimum=0,
            heavy_command_count_maximum=1,
        ),
        StageProducerContract(
            stage_name="h_shadow_discovery",
            producer_entrypoints=(
                "benchmarks.task035e_transition_producer:"
                "write_transition_bundle",
                "benchmarks.run_task033_full3d_watchdog:main",
                "benchmarks.task035e_candidate_output:"
                "write_candidate_output",
                "benchmarks.task035e_live_shadow_bridge:"
                "write_live_shadow_bridge",
            ),
            required_artifact_roles=(
                "current_plan",
                "current_watchdog_record",
                "current_candidate_output",
                "current_snapshot",
                "h_discovery_targets",
                "h_discovery_transition_action",
                "h_discovery_plan",
            ),
            provided_artifact_roles=(
                "h_shadow_watchdog_record",
                "h_shadow_candidate_output",
                "h_live_dwr_evidence",
            ),
            # A maximum-level forest may have no legal one-level split.  The
            # handler is allowed to publish a closed no-target packet, but it
            # may not invent a transition or claim shadow accuracy credit.
            heavy_command_count_minimum=0,
            heavy_command_count_maximum=1,
        ),
        StageProducerContract(
            stage_name="cellwise_partition",
            producer_entrypoints=(
                "benchmarks.task035e_cellwise_authority:"
                "write_cellwise_authority",
            ),
            required_artifact_roles=(
                "current_watchdog_record",
                "current_candidate_output",
                "p_shadow_watchdog_record",
                "p_shadow_candidate_output",
                "p_live_dwr_evidence",
                "h_shadow_watchdog_record",
                "h_shadow_candidate_output",
                "h_live_dwr_evidence",
            ),
            provided_artifact_roles=(
                "p_cellwise_authority",
                "h_cellwise_authority",
            ),
            heavy_command_count_minimum=0,
            heavy_command_count_maximum=0,
        ),
        StageProducerContract(
            stage_name="goal_marking",
            producer_entrypoints=(
                "benchmarks.task035e_goal_marking:produce_goal_marking",
                "benchmarks.task035e_transition_producer:"
                "write_transition_bundle",
                "benchmarks.task035e_blind_bindings:"
                "write_verification_prediction",
            ),
            required_artifact_roles=(
                "current_plan",
                "p_cellwise_authority",
                "h_cellwise_authority",
            ),
            provided_artifact_roles=(
                "p_goal_marking",
                "h_goal_marking",
                "p_selected_transition_action",
                "p_selected_plan",
                "p_verification_prediction",
                "h_selected_transition_action",
                "h_selected_plan",
                "h_verification_prediction",
            ),
            heavy_command_count_minimum=0,
            heavy_command_count_maximum=0,
        ),
        StageProducerContract(
            stage_name="p_selected_shadow_verification",
            producer_entrypoints=(
                "benchmarks.run_task033_full3d_watchdog:main",
                "benchmarks.task035e_candidate_output:"
                "write_candidate_output",
                "benchmarks.task035e_live_shadow_bridge:"
                "write_live_shadow_bridge",
            ),
            required_artifact_roles=(
                "current_snapshot",
                "p_selected_transition_action",
                "p_selected_plan",
            ),
            provided_artifact_roles=(
                "p_selected_shadow_watchdog_record",
                "p_selected_shadow_candidate_output",
                "p_selected_live_dwr_evidence",
            ),
            # Goal marking can legitimately select no p action.  In that
            # case the handler emits typed skip artifacts and executes no
            # watchdog command.
            heavy_command_count_minimum=0,
            heavy_command_count_maximum=1,
        ),
        StageProducerContract(
            stage_name="h_selected_shadow_verification",
            producer_entrypoints=(
                "benchmarks.run_task033_full3d_watchdog:main",
                "benchmarks.task035e_candidate_output:"
                "write_candidate_output",
                "benchmarks.task035e_live_shadow_bridge:"
                "write_live_shadow_bridge",
            ),
            required_artifact_roles=(
                "current_snapshot",
                "h_selected_transition_action",
                "h_selected_plan",
            ),
            provided_artifact_roles=(
                "h_selected_shadow_watchdog_record",
                "h_selected_shadow_candidate_output",
                "h_selected_live_dwr_evidence",
            ),
            # Goal marking can legitimately select no h action.
            heavy_command_count_minimum=0,
            heavy_command_count_maximum=1,
        ),
        StageProducerContract(
            stage_name="shadow_bundle",
            producer_entrypoints=(
                "benchmarks.task035e_blind_bindings:write_shadow_request",
                "benchmarks.task035e_shadow_bundle:write_shadow_bundle",
            ),
            required_artifact_roles=(
                "current_watchdog_record",
                "p_goal_marking",
                "p_selected_transition_action",
                "p_verification_prediction",
                "p_selected_shadow_watchdog_record",
                "p_selected_live_dwr_evidence",
                "h_goal_marking",
                "h_selected_transition_action",
                "h_verification_prediction",
                "h_selected_shadow_watchdog_record",
                "h_selected_live_dwr_evidence",
            ),
            provided_artifact_roles=(
                "shadow_request",
                "shadow_bundle",
            ),
            heavy_command_count_minimum=0,
            heavy_command_count_maximum=0,
        ),
        StageProducerContract(
            stage_name="internal_gate_deferred_or_final",
            producer_entrypoints=(
                "benchmarks.task035e_internal_gate_authority:"
                "write_deferred_internal_gate_authority",
                "benchmarks.task035e_internal_gate_authority:"
                "write_internal_gate_authority",
                "benchmarks.run_task033_full3d_watchdog:main",
            ),
            required_artifact_roles=(
                "current_watchdog_record",
                "current_candidate_output",
                "current_plan",
                "current_snapshot",
            ),
            provided_artifact_roles=("internal_gate_authority",),
            heavy_command_count_minimum=0,
            heavy_command_count_maximum=4,
        ),
        StageProducerContract(
            stage_name="isolation_audit",
            producer_entrypoints=(
                "benchmarks.task035e_blind_bindings:"
                "write_blind_input_manifest",
                "benchmarks.task035e_" + "reference_leak_checker:main",
            ),
            required_artifact_roles=(
                "trial_metadata",
                "current_watchdog_record",
                "current_candidate_output",
                "current_snapshot",
                "shadow_bundle",
            ),
            provided_artifact_roles=(
                "blind_input_manifest",
                "isolation_report",
            ),
            heavy_command_count_minimum=0,
            heavy_command_count_maximum=0,
        ),
        StageProducerContract(
            stage_name="cycle_binding",
            producer_entrypoints=(
                "benchmarks.task035e_blind_bindings:"
                "write_cycle_binding",
            ),
            required_artifact_roles=(
                "trial_metadata",
                "current_watchdog_record",
                "current_candidate_output",
                "current_snapshot",
                "shadow_bundle",
                "internal_gate_authority",
                "isolation_report",
            ),
            provided_artifact_roles=("cycle_binding",),
            heavy_command_count_minimum=0,
            heavy_command_count_maximum=0,
        ),
        StageProducerContract(
            stage_name="cycle_advance",
            producer_entrypoints=(
                "benchmarks.task035e_blind_cycle:main",
            ),
            required_artifact_roles=(
                "current_candidate_output",
                "shadow_bundle",
                "cycle_binding",
            ),
            provided_artifact_roles=(
                "cycle_evidence",
                "trial_state",
                "selected_action_binding_or_pkeep",
                "freeze_intent",
            ),
            heavy_command_count_minimum=0,
            heavy_command_count_maximum=0,
        ),
        StageProducerContract(
            stage_name="transition_or_pkeep",
            producer_entrypoints=(
                "benchmarks.task035e_transition_producer:"
                "write_transition_bundle",
            ),
            required_artifact_roles=(
                "current_plan",
                "trial_state",
                "selected_action_binding_or_pkeep",
                "p_goal_marking",
                "p_selected_transition_action",
                "p_verification_prediction",
                "h_goal_marking",
                "h_selected_transition_action",
                "h_verification_prediction",
            ),
            provided_artifact_roles=(
                "next_transition_action",
                "current_plan",
                # These stable cross-cycle roles preserve the exact marking
                # and prediction that selected the transition.  The ordinary
                # p/h roles are overwritten by the next cycle before its
                # cycle-binding stage and therefore cannot provide D4
                # verification authority on their own.
                "previous_transition_mode",
                "previous_selected_goal_marking",
                "previous_selected_verification_prediction",
            ),
            heavy_command_count_minimum=0,
            heavy_command_count_maximum=0,
        ),
        StageProducerContract(
            stage_name="two_start_comparison",
            producer_entrypoints=(
                "benchmarks.task035e_campaign_stages:"
                "prepare_two_start_comparison",
            ),
            required_artifact_roles=(
                "path_a_current_candidate_output",
                "path_b_current_candidate_output",
                "path_a_internal_gate_authority",
                "path_b_internal_gate_authority",
                "path_a_trial_state",
                "path_b_trial_state",
                "path_a_trial_metadata",
                "path_b_trial_metadata",
                "path_a_cycle_binding",
                "path_b_cycle_binding",
            ),
            provided_artifact_roles=("two_start_comparison",),
            heavy_command_count_minimum=0,
            heavy_command_count_maximum=0,
        ),
        StageProducerContract(
            stage_name="candidate_freeze",
            producer_entrypoints=(
                "benchmarks.task035e_campaign_stages:"
                "prepare_candidate_freeze",
            ),
            required_artifact_roles=(
                "two_start_comparison",
                "path_a_current_candidate_output",
                "path_b_current_candidate_output",
                "path_a_internal_gate_authority",
                "path_b_internal_gate_authority",
                "path_a_current_watchdog_record",
                "path_b_current_watchdog_record",
                "path_a_cycle_binding",
                "path_b_cycle_binding",
                "path_a_trial_state",
                "path_b_trial_state",
                "path_a_trial_metadata",
                "path_b_trial_metadata",
            ),
            provided_artifact_roles=(
                "candidate_freeze",
                "freeze_receipt",
                "frozen_candidate_bundle",
            ),
            heavy_command_count_minimum=0,
            heavy_command_count_maximum=0,
        ),
    )


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _bound_json(binding: Any, *, label: str) -> Mapping[str, Any]:
    path = binding.validate()
    if stat.S_IMODE(path.stat().st_mode) != 0o600:
        raise BlindCampaignError(f"{label} must use mode 0600")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BlindCampaignError(f"cannot parse {label}") from exc
    if not isinstance(value, Mapping):
        raise BlindCampaignError(f"{label} must be one JSON object")
    return value


def _cycle_resource(binding: Any, *, label: str) -> Mapping[str, int]:
    outer = _bound_json(binding, label=label)
    if set(outer) != {"schema_version", "sha256", "payload"}:
        raise BlindCampaignError(f"{label} wrapper differs")
    payload = outer["payload"]
    if (
        not isinstance(payload, Mapping)
        or outer["sha256"] != _canonical_sha256(payload)
    ):
        raise BlindCampaignError(f"{label} self-hash differs")
    resource = payload.get("resource_inventory")
    required = {
        "active_dofs",
        "rows",
        "matrix_nnz",
        "factor_nnz",
        "solver_peak_bytes",
    }
    if not isinstance(resource, Mapping) or set(resource) != required:
        raise BlindCampaignError(f"{label} resource inventory differs")
    result: dict[str, int] = {}
    for name in sorted(required):
        value = resource[name]
        if type(value) is not int or value < 0:
            raise BlindCampaignError(
                f"{label} resource {name} is invalid"
            )
        result[name] = int(value)
    return result


def _load_terminal_trial(
    context: StageExecutionContext,
    *,
    path_id: str,
):
    role = f"path_{path_id.lower()}_trial_state"
    binding = context.artifact(role)
    return load_trial_state(binding.validate(), binding.sha256)


def _load_terminal_metadata(
    context: StageExecutionContext,
    *,
    path_id: str,
    trial: Any,
) -> Mapping[str, Any]:
    role = f"path_{path_id.lower()}_trial_metadata"
    binding = context.artifact(role)
    metadata = load_trial_metadata(binding.validate())
    bindings = {
        "trial_id": trial.trial_id,
        "algorithm_id": trial.algorithm_id,
        "source_sha": trial.source_sha,
        "initial_path_id": trial.initial_path_id,
        "initial_mesh_forest_sha256": (
            trial.initial_mesh_forest_sha256
        ),
        "physical_identity_sha256": trial.physical_identity_sha256,
        "maximum_cycles": trial.maximum_cycles,
    }
    for name, expected in bindings.items():
        if metadata.get(name) != expected:
            raise BlindCampaignError(
                f"Path {path_id} trial metadata differs at {name}"
            )
    return metadata


def _terminal_output(
    context: StageExecutionContext,
    *,
    path_id: str,
    trial: Any,
) -> Mapping[str, Any]:
    binding = context.artifact(
        f"path_{path_id.lower()}_current_candidate_output"
    )
    output = _bound_json(binding, label=f"Path {path_id} output")
    if (
        not trial.results
        or _canonical_sha256(output)
        != trial.results[-1].complete_output_sha256
    ):
        raise BlindCampaignError(
            f"Path {path_id} endpoint does not bind its candidate output"
        )
    return output


def _resource_authority_from_cycle(
    context: StageExecutionContext,
    *,
    path_id: str,
    trial: Any,
) -> Mapping[str, Any]:
    resource = _cycle_resource(
        context.artifact(f"path_{path_id.lower()}_cycle_binding"),
        label=f"Path {path_id} cycle binding",
    )
    authority: dict[str, Any] = {
        "schema_version": "task035e.resource-authority.v1",
        **dict(resource),
        "swap_peak_bytes": 0,
        "mpi_size": 8,
        "same_solver_lifecycle_telemetry": True,
    }
    if (
        not trial.results
        or _canonical_sha256(authority)
        != trial.results[-1].resource_inventory_sha256
    ):
        raise BlindCampaignError(
            f"Path {path_id} resource authority differs from its endpoint"
        )
    return authority


def _resource_authority_from_adapted(
    adapted: Any,
) -> Mapping[str, Any]:
    inventory = adapted.structural_inventory
    required = {
        "active_fe_dofs",
        "matrix_rows",
        "matrix_nnz",
        "factor_nnz",
        "solver_peak_bytes",
    }
    if not isinstance(inventory, Mapping) or not required <= set(inventory):
        raise BlindCampaignError(
            "adapted candidate lacks the closed structural inventory"
        )
    return {
        "schema_version": "task035e.resource-authority.v1",
        "active_dofs": int(inventory["active_fe_dofs"]),
        "rows": int(inventory["matrix_rows"]),
        "matrix_nnz": int(inventory["matrix_nnz"]),
        "factor_nnz": int(inventory["factor_nnz"]),
        "solver_peak_bytes": int(inventory["solver_peak_bytes"]),
        "swap_peak_bytes": 0,
        "mpi_size": 8,
        "same_solver_lifecycle_telemetry": True,
    }


def _two_start_payload(
    context: StageExecutionContext,
) -> Mapping[str, Any]:
    trial_a = _load_terminal_trial(context, path_id="A")
    trial_b = _load_terminal_trial(context, path_id="B")
    _load_terminal_metadata(context, path_id="A", trial=trial_a)
    _load_terminal_metadata(context, path_id="B", trial=trial_b)
    _terminal_output(context, path_id="A", trial=trial_a)
    _terminal_output(context, path_id="B", trial=trial_b)
    gate = dict(compare_frozen_paths(trial_a, trial_b))
    resource_a = _resource_authority_from_cycle(
        context,
        path_id="A",
        trial=trial_a,
    )
    resource_b = _resource_authority_from_cycle(
        context,
        path_id="B",
        trial=trial_b,
    )
    chosen_path = min(
        ("A", "B"),
        key=lambda path_id: (
            (
                resource_a
                if path_id == "A"
                else resource_b
            )["solver_peak_bytes"],
            (
                resource_a
                if path_id == "A"
                else resource_b
            )["rows"],
            (
                resource_a
                if path_id == "A"
                else resource_b
            )["factor_nnz"],
            path_id,
        ),
    )
    unsigned: dict[str, Any] = {
        "schema_version": TWO_START_COMPARISON_SCHEMA,
        "status": (
            "two_start_comparison_pass"
            if gate["pass"] is True
            else "two_start_comparison_controlled_negative"
        ),
        "pass": gate["pass"] is True,
        "source_sha": context.source_sha,
        "two_path_gate": gate,
        "two_path_gate_sha256": _canonical_sha256(gate),
        "path_a_output_file_sha256": context.artifact(
            "path_a_current_candidate_output"
        ).sha256,
        "path_b_output_file_sha256": context.artifact(
            "path_b_current_candidate_output"
        ).sha256,
        "path_a_goal_sha256": trial_a.results[-1].goals.sha256,
        "path_b_goal_sha256": trial_b.results[-1].goals.sha256,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "maximum_normalized_difference": gate[
            "maximum_normalized_goal_distance"
        ],
        "path_a_resource_inventory": dict(resource_a),
        "path_b_resource_inventory": dict(resource_b),
        "chosen_path_id": chosen_path,
        "path_a_internal_gate_file_sha256": context.artifact(
            "path_a_internal_gate_authority"
        ).sha256,
        "path_b_internal_gate_file_sha256": context.artifact(
            "path_b_internal_gate_authority"
        ).sha256,
        "path_a_trial_state_file_sha256": context.artifact(
            "path_a_trial_state"
        ).sha256,
        "path_b_trial_state_file_sha256": context.artifact(
            "path_b_trial_state"
        ).sha256,
        "path_a_trial_metadata_file_sha256": context.artifact(
            "path_a_trial_metadata"
        ).sha256,
        "path_b_trial_metadata_file_sha256": context.artifact(
            "path_b_trial_metadata"
        ).sha256,
        "path_a_cycle_binding_file_sha256": context.artifact(
            "path_a_cycle_binding"
        ).sha256,
        "path_b_cycle_binding_file_sha256": context.artifact(
            "path_b_cycle_binding"
        ).sha256,
        "ordinary_default_changed": False,
    }
    return {
        **unsigned,
        "comparison_sha256": _canonical_sha256(unsigned),
    }


def prepare_two_start_comparison(
    context: StageExecutionContext,
    _attempt: AttemptHandle,
) -> PreparedStage:
    """Build the F3 two-start Gate without opening any external authority."""

    def execute(
        attempt: AttemptHandle,
        command_receipts: tuple[CommandExecutionReceipt, ...],
    ) -> StageResult:
        if command_receipts:
            raise BlindCampaignError(
                "two-start comparison must not execute a PDE"
            )
        payload = _two_start_payload(context)
        path = attempt.write_artifact(
            "two-start-comparison.json",
            payload,
        )
        passed = payload["pass"] is True
        return StageResult(
            status="completed" if passed else "controlled_negative",
            classification=(
                "two_start_comparison_pass"
                if passed
                else "two_start_outputs_differ"
            ),
            input_plan_sha256=context.input_plan_sha256,
            artifacts=(
                StageArtifactBinding.from_file(
                    "two_start_comparison",
                    path,
                ),
            ),
        )

    return PreparedStage(execute=execute)


def prepare_candidate_freeze(
    context: StageExecutionContext,
    _attempt: AttemptHandle,
) -> PreparedStage:
    """Bind the chosen endpoint, resource authority, and both internal Gates."""

    def execute(
        attempt: AttemptHandle,
        command_receipts: tuple[CommandExecutionReceipt, ...],
    ) -> StageResult:
        if command_receipts:
            raise BlindCampaignError(
                "candidate freeze must not execute a PDE"
            )
        comparison_binding = context.artifact("two_start_comparison")
        comparison = _bound_json(
            comparison_binding,
            label="two-start comparison",
        )
        comparison_unsigned = dict(comparison)
        comparison_sha = comparison_unsigned.pop(
            "comparison_sha256",
            None,
        )
        if (
            comparison.get("schema_version")
            != TWO_START_COMPARISON_SCHEMA
            or comparison.get("pass") is not True
            or comparison_sha != _canonical_sha256(comparison_unsigned)
        ):
            raise BlindCampaignError(
                "candidate freeze requires a passing two-start Gate"
            )
        stored_gate = comparison.get("two_path_gate")
        if not isinstance(stored_gate, Mapping):
            raise BlindCampaignError(
                "two-start comparison lacks the closed core Gate"
            )
        trial_a = _load_terminal_trial(context, path_id="A")
        trial_b = _load_terminal_trial(context, path_id="B")
        metadata_a = _load_terminal_metadata(
            context,
            path_id="A",
            trial=trial_a,
        )
        metadata_b = _load_terminal_metadata(
            context,
            path_id="B",
            trial=trial_b,
        )
        recomputed_gate = dict(compare_frozen_paths(trial_a, trial_b))
        if (
            dict(stored_gate) != recomputed_gate
            or comparison.get("two_path_gate_sha256")
            != _canonical_sha256(recomputed_gate)
        ):
            raise BlindCampaignError(
                "candidate freeze could not replay the two-start Gate"
            )
        chosen = str(comparison["chosen_path_id"])
        if chosen not in {"A", "B"}:
            raise BlindCampaignError("chosen path identity is invalid")
        prefix = f"path_{chosen.lower()}_"
        chosen_output = context.artifact(
            prefix + "current_candidate_output"
        )
        chosen_record = context.artifact(
            prefix + "current_watchdog_record"
        )
        chosen_internal = context.artifact(
            prefix + "internal_gate_authority"
        )
        chosen_cycle_binding = context.artifact(
            prefix + "cycle_binding"
        )
        chosen_trial_state = context.artifact(
            prefix + "trial_state"
        )
        chosen_trial = trial_a if chosen == "A" else trial_b
        chosen_metadata = metadata_a if chosen == "A" else metadata_b
        endpoint = chosen_trial.results[-1]
        chosen_output_payload = _terminal_output(
            context,
            path_id=chosen,
            trial=chosen_trial,
        )
        adapted = adapt_candidate_output(
            CandidateWatchdogInput(
                path=chosen_record.validate(),
                sha256=chosen_record.sha256,
            )
        )
        if (
            dict(adapted.payload) != dict(chosen_output_payload)
            or adapted.output_sha256 != endpoint.complete_output_sha256
            or adapted.record_sha256 != chosen_record.sha256
            or adapted.source_sha != chosen_trial.source_sha
            or adapted.trial_id != chosen_trial.trial_id
            or adapted.cycle_index != endpoint.cycle_index
            or adapted.output_role != "current"
            or adapted.plan_file_sha256 != endpoint.plan_file_sha256
            or adapted.forest_leaf_catalog_sha256
            != endpoint.mesh_forest_sha256
            or adapted.cell_degree_plan_sha256
            != endpoint.degree_map_sha256
        ):
            raise BlindCampaignError(
                "chosen watchdog record does not reconstruct the endpoint"
            )
        resource = _resource_authority_from_adapted(adapted)
        cycle_resource = _resource_authority_from_cycle(
            context,
            path_id=chosen,
            trial=chosen_trial,
        )
        if dict(resource) != dict(cycle_resource):
            raise BlindCampaignError(
                "adapted and cycle resource authorities differ"
            )
        identity = {
            "trial_id": chosen_trial.trial_id,
            "algorithm_id": chosen_trial.algorithm_id,
            "source_sha": chosen_trial.source_sha,
            "initial_path_id": chosen_trial.initial_path_id,
            "initial_mesh_forest_sha256": (
                chosen_trial.initial_mesh_forest_sha256
            ),
            "cycle_chain_root_sha256": (
                chosen_trial.cycle_chain_root_sha256
            ),
            "cycle_index": endpoint.cycle_index,
            "geometry_sha256": chosen_metadata["geometry_sha256"],
            "material_sha256": chosen_metadata["material_sha256"],
            "incident_sha256": chosen_metadata["incident_sha256"],
            "dtn_definition_sha256": (
                chosen_metadata["dtn_definition_sha256"]
            ),
            "postprocessing_sha256": (
                chosen_metadata["postprocessing_sha256"]
            ),
            "mesh_forest_sha256": endpoint.mesh_forest_sha256,
            "degree_map_sha256": endpoint.degree_map_sha256,
        }
        frozen = freeze_candidate(
            chosen_trial,
            two_path_gate=recomputed_gate,
            physical_identity_sha256=(
                chosen_metadata["physical_identity_sha256"]
            ),
            resource_authority=resource,
        )
        freeze_receipt = asdict(frozen)
        candidate_bundle = {
            "schema_version": CANDIDATE_BUNDLE_SCHEMA,
            "identity": identity,
            "outputs": dict(adapted.payload),
            "internal_certificate": dict(
                endpoint.internal_certificate
            ),
            "resource_authority": dict(resource),
            "two_path_gate": recomputed_gate,
        }
        freeze_receipt_path = attempt.write_artifact(
            "freeze-receipt.json",
            freeze_receipt,
        )
        candidate_bundle_path = attempt.write_artifact(
            "frozen-candidate-bundle.json",
            candidate_bundle,
        )
        freeze_receipt_binding = StageArtifactBinding.from_file(
            "freeze_receipt",
            freeze_receipt_path,
        )
        candidate_bundle_binding = StageArtifactBinding.from_file(
            "frozen_candidate_bundle",
            candidate_bundle_path,
        )
        unsigned: dict[str, Any] = {
            "schema_version": CANDIDATE_FREEZE_SCHEMA,
            "status": "candidate_freeze_pass",
            "pass": True,
            "source_sha": context.source_sha,
            "chosen_path_id": chosen,
            "chosen_output_file_sha256": chosen_output.sha256,
            "chosen_watchdog_record_file_sha256": (
                chosen_record.sha256
            ),
            "chosen_internal_gate_file_sha256": chosen_internal.sha256,
            "chosen_cycle_binding_file_sha256": (
                chosen_cycle_binding.sha256
            ),
            "chosen_trial_state_file_sha256": (
                chosen_trial_state.sha256
            ),
            "chosen_resource_inventory": dict(resource),
            "two_start_comparison_file_sha256": (
                comparison_binding.sha256
            ),
            "two_start_comparison_payload_sha256": comparison_sha,
            "two_path_gate_sha256": _canonical_sha256(recomputed_gate),
            "freeze_receipt_file_sha256": (
                freeze_receipt_binding.sha256
            ),
            "freeze_receipt_payload_sha256": (
                frozen.frozen_payload_sha256
            ),
            "frozen_candidate_bundle_file_sha256": (
                candidate_bundle_binding.sha256
            ),
            "frozen_candidate_bundle_payload_sha256": (
                _canonical_sha256(candidate_bundle)
            ),
            "evaluator_preflight_status": "deferred_until_blind_exit",
            "path_a_internal_gate_file_sha256": context.artifact(
                "path_a_internal_gate_authority"
            ).sha256,
            "path_b_internal_gate_file_sha256": context.artifact(
                "path_b_internal_gate_authority"
            ).sha256,
            "path_a_trial_state_file_sha256": context.artifact(
                "path_a_trial_state"
            ).sha256,
            "path_b_trial_state_file_sha256": context.artifact(
                "path_b_trial_state"
            ).sha256,
            "external_audit_run": False,
            "ordinary_default_changed": False,
        }
        payload = {
            **unsigned,
            "freeze_sha256": _canonical_sha256(unsigned),
        }
        path = attempt.write_artifact("candidate-freeze.json", payload)
        return StageResult(
            status="completed",
            classification="candidate_freeze_pass",
            input_plan_sha256=context.input_plan_sha256,
            artifacts=(
                StageArtifactBinding.from_file(
                    "candidate_freeze",
                    path,
                ),
                freeze_receipt_binding,
                candidate_bundle_binding,
            ),
        )

    return PreparedStage(execute=execute)


def campaign_final_stage_handlers() -> Mapping[str, FormalStageHandler]:
    """Return the two built-in light handlers after both paths freeze."""

    return {
        "two_start_comparison": prepare_two_start_comparison,
        "candidate_freeze": prepare_candidate_freeze,
    }


def _structural_issues(
    stages: Sequence[CampaignStage] | None,
) -> tuple[StageWiringIssue, ...]:
    context_fields = frozenset(
        field.name for field in fields(StageExecutionContext)
    )
    prepared_fields = frozenset(field.name for field in fields(PreparedStage))
    result_fields = frozenset(field.name for field in fields(StageResult))
    path_fields = frozenset(field.name for field in fields(BlindPathIdentity))
    contracts = formal_stage_contracts()
    path_contracts = tuple(
        contract
        for contract in contracts
        if contract.stage_name
        not in {"two_start_comparison", "candidate_freeze"}
    )
    final_contracts = tuple(
        contract
        for contract in contracts
        if contract.stage_name
        in {"two_start_comparison", "candidate_freeze"}
    )
    issues: list[StageWiringIssue] = []

    if "input_artifacts" not in context_fields:
        issues.append(
            StageWiringIssue(
                code="missing_typed_predecessor_artifacts",
                affected_stages=tuple(
                    contract.stage_name for contract in contracts
                ),
                explanation=(
                    "StageExecutionContext lacks typed predecessor artifacts."
                ),
                required_change=(
                    "Add role/path/hash/size bindings to the stage context."
                ),
            )
        )
    required_path_fields = {
        "initial_space_authority_path",
        "initial_space_authority_sha256",
        "qualified_solver_config_path",
        "qualified_solver_config_sha256",
    }
    if not required_path_fields <= path_fields:
        issues.append(
            StageWiringIssue(
                code="bootstrap_authorities_outside_identity",
                affected_stages=("initial_plan",),
                explanation=(
                    "Path identity does not bind every bootstrap authority."
                ),
                required_change=(
                    "Bind both authority path/hash pairs in path identity."
                ),
            )
        )
    if "artifacts" not in result_fields:
        issues.append(
            StageWiringIssue(
                code="untyped_stage_outputs",
                affected_stages=tuple(
                    contract.stage_name for contract in contracts
                ),
                explanation="StageResult lacks typed artifact bindings.",
                required_change=(
                    "Publish role/path/hash/size for every output."
                ),
            )
        )
    if "argvs" not in prepared_fields:
        issues.append(
            StageWiringIssue(
                code="single_command_receipt_cannot_credit_heavy_batches",
                affected_stages=(
                    "internal_gate_deferred_or_final",
                    "p_selected_shadow_verification",
                    "h_selected_shadow_verification",
                ),
                explanation=(
                    "PreparedStage cannot bind an ordered command inventory."
                ),
                required_change=(
                    "Add ordered argvs and hash every invocation."
                ),
            )
        )

    if stages is not None:
        contract_names = {contract.stage_name for contract in contracts}
        unknown = tuple(
            sorted(
                {
                    stage.stage_name
                    for stage in stages
                    if stage.stage_name not in contract_names
                }
            )
        )
        if unknown:
            issues.append(
                StageWiringIssue(
                    code="unmapped_campaign_stage",
                    affected_stages=unknown,
                    explanation="The campaign DAG has an unmapped stage.",
                    required_change="Add a closed producer contract.",
                )
            )
        first_path = stages[0].path_id if stages else None
        first_cycle = tuple(
            stage
            for stage in stages
            if stage.path_id == first_path
            and (
                stage.cycle_index is None
                or stage.cycle_index == 0
            )
        )
        expected_order = tuple(
            contract.stage_name for contract in path_contracts
        )
        observed_order = tuple(
            stage.stage_name for stage in first_cycle
        )
        if observed_order != expected_order:
            issues.append(
                StageWiringIssue(
                    code="formal_stage_order_differs",
                    affected_stages=observed_order,
                    explanation=(
                        "The DAG differs from the producer contract order."
                    ),
                    required_change=(
                        "Use target discovery, p/h discovery, marking, "
                        "separate selected p/h verification, then closure."
                    ),
                )
            )
        final_stages = tuple(
            stage for stage in stages if stage.path_id == "FINAL"
        )
        if tuple(stage.stage_name for stage in final_stages) != tuple(
            contract.stage_name for contract in final_contracts
        ):
            issues.append(
                StageWiringIssue(
                    code="campaign_final_stage_order_differs",
                    affected_stages=tuple(
                        stage.stage_name for stage in final_stages
                    ),
                    explanation=(
                        "Two-start comparison and freeze order differs."
                    ),
                    required_change=(
                        "Run comparison before candidate freeze."
                    ),
                )
            )
        by_name = {contract.stage_name: contract for contract in contracts}
        for stage in (*first_cycle, *final_stages):
            contract = by_name.get(stage.stage_name)
            if contract is None:
                continue
            should_be_heavy = contract.heavy_command_count_maximum > 0
            if stage.heavy != should_be_heavy:
                issues.append(
                    StageWiringIssue(
                        code="stage_heavy_policy_differs",
                        affected_stages=(stage.stage_name,),
                        explanation=(
                            "DAG locking differs from command requirements."
                        ),
                        required_change=(
                            "Make the heavy flag match the contract."
                        ),
                    )
                )
        available = {
            "current_plan",
            "initial_space_authority",
            "qualified_solver_config",
        }
        for contract in path_contracts:
            missing = tuple(
                role
                for role in contract.required_artifact_roles
                if role not in available
            )
            if missing:
                issues.append(
                    StageWiringIssue(
                        code="producer_input_role_unavailable",
                        affected_stages=(contract.stage_name,),
                        explanation=(
                            "Unavailable predecessor roles: "
                            + ", ".join(missing)
                        ),
                        required_change=(
                            "Publish every role from an earlier stage."
                        ),
                    )
                )
            available.update(contract.provided_artifact_roles)
        final_available = {
            f"path_{path_id}_{role}"
            for path_id in ("a", "b")
            for role in available
        }
        for contract in final_contracts:
            missing = tuple(
                role
                for role in contract.required_artifact_roles
                if role not in final_available
            )
            if missing:
                issues.append(
                    StageWiringIssue(
                        code="campaign_final_input_role_unavailable",
                        affected_stages=(contract.stage_name,),
                        explanation=(
                            "Unavailable final predecessor roles: "
                            + ", ".join(missing)
                        ),
                        required_change=(
                            "Bind both terminal paths before finalization."
                        ),
                    )
                )
            final_available.update(contract.provided_artifact_roles)
    return tuple(issues)


def audit_campaign_stage_wiring(
    stages: Sequence[CampaignStage] | None = None,
) -> Mapping[str, Any]:
    """Return a deterministic, machine-readable readiness audit."""

    contracts = formal_stage_contracts()
    contract_names = tuple(contract.stage_name for contract in contracts)
    if len(set(contract_names)) != len(contract_names):
        raise RuntimeError("formal stage contract names are not unique")
    issues = list(_structural_issues(stages))
    unsigned: dict[str, Any] = {
        "schema_version": STAGE_WIRING_AUDIT_SCHEMA,
        "status": "ready" if not issues else "not_executable",
        "formal_stage_count": len(contracts),
        "contracts": [contract.payload() for contract in contracts],
        "issues": [issue.payload() for issue in issues],
        "formal_preparer_enabled": not issues,
        "pde_executed": False,
        "ordinary_default_changed": False,
    }
    return {
        **unsigned,
        "audit_sha256": _canonical_sha256(unsigned),
    }


def require_executable_stage_wiring(
    stages: Sequence[CampaignStage] | None = None,
) -> None:
    """Fail closed until the runner and producer DAG are connected."""

    report = audit_campaign_stage_wiring(stages)
    if report["formal_preparer_enabled"] is not True:
        codes = ", ".join(
            str(row["code"]) for row in report["issues"]
        )
        raise RuntimeError(
            "Task035e formal StagePreparer is disabled by wiring audit: "
            + codes
        )


class FormalStageHandler(Protocol):
    """One producer-backed implementation of a mapped campaign stage."""

    def __call__(
        self,
        context: StageExecutionContext,
        attempt: AttemptHandle,
    ) -> PreparedStage: ...


class ContractStagePreparer:
    """Typed adapter from the campaign DAG to producer-backed handlers."""

    def __init__(
        self,
        handlers: Mapping[str, FormalStageHandler],
    ) -> None:
        contracts = formal_stage_contracts()
        expected = {contract.stage_name for contract in contracts}
        observed = set(handlers)
        if observed != expected:
            missing = sorted(expected - observed)
            extra = sorted(observed - expected)
            raise BlindCampaignError(
                "formal stage handler inventory differs; "
                f"missing={missing}, extra={extra}"
            )
        require_executable_stage_wiring()
        self._contracts = {
            contract.stage_name: contract for contract in contracts
        }
        self._handlers = dict(handlers)

    def __call__(
        self,
        context: StageExecutionContext,
        attempt: AttemptHandle,
    ) -> PreparedStage:
        contract = self._contracts.get(context.stage.stage_name)
        if contract is None:
            raise BlindCampaignError("campaign stage has no formal contract")
        available = {
            binding.role: binding for binding in context.input_artifacts
        }
        missing = tuple(
            role
            for role in contract.required_artifact_roles
            if role not in available
        )
        if missing:
            raise BlindCampaignError(
                f"{contract.stage_name} lacks typed inputs: {missing}"
            )
        prepared = self._handlers[contract.stage_name](context, attempt)
        if not isinstance(prepared, PreparedStage):
            raise BlindCampaignError(
                "formal stage handler did not return PreparedStage"
            )
        command_count = len(prepared.command_argvs)
        if not (
            contract.heavy_command_count_minimum
            <= command_count
            <= contract.heavy_command_count_maximum
        ):
            raise BlindCampaignError(
                f"{contract.stage_name} watchdog invocation count differs"
            )
        if (
            contract.stage_name == "internal_gate_deferred_or_final"
            and command_count not in {0, 4}
        ):
            raise BlindCampaignError(
                "internal Gate requires either deferred zero-command "
                "authority or the complete four-probe inventory"
            )
        raw_execute = prepared.execute

        def execute(
            checked_attempt: AttemptHandle,
            command_receipts: tuple[CommandExecutionReceipt, ...],
        ) -> StageResult:
            result = raw_execute(checked_attempt, command_receipts)
            if not isinstance(result, StageResult):
                raise BlindCampaignError(
                    "formal stage handler returned a non-StageResult"
                )
            if result.status == "completed":
                observed_roles = {
                    artifact.role for artifact in result.artifacts
                }
                expected_roles = set(contract.provided_artifact_roles)
                if observed_roles != expected_roles:
                    raise BlindCampaignError(
                        f"{contract.stage_name} output roles differ; "
                        f"expected={sorted(expected_roles)}, "
                        f"observed={sorted(observed_roles)}"
                    )
            expected_command_shas = tuple(
                receipt.receipt_file_sha256
                for receipt in command_receipts
            )
            if (
                result.command_receipt_file_sha256s
                != expected_command_shas
            ):
                raise BlindCampaignError(
                    f"{contract.stage_name} did not bind command receipts"
                )
            return result

        return PreparedStage(
            execute=execute,
            argvs=prepared.command_argvs,
            allow_controlled_resource_stop=(
                prepared.allow_controlled_resource_stop
            ),
        )


__all__ = [
    "CANDIDATE_FREEZE_SCHEMA",
    "ContractStagePreparer",
    "FormalStageHandler",
    "STAGE_PRODUCER_CONTRACT_SCHEMA",
    "STAGE_WIRING_AUDIT_SCHEMA",
    "StageProducerContract",
    "StageWiringIssue",
    "TWO_START_COMPARISON_SCHEMA",
    "audit_campaign_stage_wiring",
    "campaign_final_stage_handlers",
    "formal_stage_contracts",
    "prepare_candidate_freeze",
    "prepare_two_start_comparison",
    "require_executable_stage_wiring",
]
