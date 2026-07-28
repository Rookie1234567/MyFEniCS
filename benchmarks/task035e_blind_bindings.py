#!/usr/bin/env python3
"""Publish immutable Task035e shadow, manifest, and cycle bindings.

This module fills the file-orchestration gap between the already qualified
Task035e current/shadow adapters and the pure blind-cycle controller.  It does
not solve a PDE, select an h/p action, evaluate a DWR estimate, or read an
evaluator-side authority.  Every referenced file is opened locally and its
byte hash is recomputed; callers never supply a trusted artifact hash.

Four independent subcommands are provided:

``shadow-request``
    Bind one current watchdog record to at least one actual p-shadow and one
    actual h-shadow endpoint.  The request is replayed through the existing
    shadow-bundle builder before publication.

``blind-manifest``
    Build the exact additional-properties-false input manifest consumed by
    the reference-isolation checker.

``verification-prediction``
    Bind one positive 59-goal marking to its canonical transition action and
    publish the ordered signed prediction packet used on the next cycle.

``cycle-binding``
    Bind the current candidate, live snapshot, actual shadow bundle,
    isolation report, resource inventory, internal Gates, and (after cycle
    zero) the replayed previous trial/action verification.

All published artifacts are mode 0600, immutable, and written atomically.
Paths that cross the evaluator/reference layer are rejected.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Callable, Mapping, Sequence

from benchmarks import task035e_blind_cycle as blind_cycle
from benchmarks.task035e_candidate_output import (
    AdaptedCandidateOutput,
    CandidateOutputError,
    CandidateWatchdogInput,
    adapt_candidate_output,
)
from benchmarks.task035e_internal_gate_authority import (
    AUTHORITY_SCHEMA as INTERNAL_GATE_AUTHORITY_SCHEMA,
    InternalGateAuthorityError,
    validate_internal_gate_authority,
)
from benchmarks.task035e_shadow_bundle import (
    REQUEST_SCHEMA,
    BoundJSONInput,
    ShadowBundleError,
    build_shadow_bundle,
)
from benchmarks.task035e_trial_metadata import (
    TRIAL_METADATA_SCHEMA,
    TrialMetadataError,
    load_trial_metadata,
)
from src.adaptivity.blind_controller import (
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
    InternalGates,
    ShadowVerification,
    StabilityRepeatVerification,
    stability_repeat_verification_payload,
)
from src.adaptivity.blind_controller.manifest import (
    BLIND_INPUT_MANIFEST_SCHEMA,
    build_cycle_manifest,
    cycle_manifest_sha256,
)
from src.adaptivity.blind_controller.state_machine import (
    StructuralInventory,
)
from src.adaptivity.task035e_hp_transition import (
    HP_TRANSITION_ACTION_SCHEMA,
)
from src.adaptivity.task035e_initial_space import (
    build_task035e_initial_space_plan,
)
from src.adaptivity.task035e_plan_transition import (
    PLAN_TRANSITION_SCHEMA,
    canonical_solver_content_sha256,
    rebuild_hp_transition_state_from_solver_plan,
)
from src.common.config_3d import target_stage4_config


VERIFICATION_PREDICTION_SCHEMA = (
    "task035e.shadow-verification-prediction.v1"
)
GOAL_MARKING_SCHEMA = "task035e.reference-blind-goal-marking.v1"
BINDING_RECEIPT_SCHEMA = "task035e.blind-binding-write-receipt.v1"
CHECKER_SCHEMA = "task035e.reference-leak-check.v1"
CHECKER_ARTIFACT_SCHEMA = "task035e.reference-leak-check-artifact.v1"
SNAPSHOT_SCHEMA = "task035e.multigoal-current-live-snapshot.v1"
SNAPSHOT_MANIFEST_NAMESPACE = "task035e.multigoal-current-manifest.v1"
SNAPSHOT_RESIDUAL_NAMESPACE = "task035e.current-full-active-residual.v1"
SNAPSHOT_PLAN_NAMESPACE = "task035e.executed-plan-payload.v1"
SNAPSHOT_COMMON_NAMESPACE = "task035e.current-common-identity.v1"
SNAPSHOT_GATE_NAMESPACE = "task035e.current-qualified-primal-gate.v1"
STRUCTURAL_INVENTORY_SCHEMA = blind_cycle.STRUCTURAL_INVENTORY_SCHEMA
MANIFEST_STATE = blind_cycle.REFERENCE_ISOLATION_MANIFEST_STATE

_SOURCE_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_OPAQUE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z")
_FORBIDDEN_PATH_PARTS = frozenset(
    {
        "ref" + "erence_certifier",
        "hid" + "den_auditor",
        "sealed_" + "reference",
        "sealed-" + "reference",
        "golden_" + "reference",
        "golden-" + "reference",
    }
)
_FORBIDDEN_SPEC_TOKENS = (
    "ref" + "erence_certifier",
    "hid" + "den_auditor",
    "sealed_" + "reference",
    "sealed-" + "reference",
    "hidden_" + "reference",
    "hidden-" + "reference",
    "golden_" + "reference",
    "golden-" + "reference",
    "reference_" + "authority",
    "reference-" + "authority",
)
_SNAPSHOT_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "pass",
        "role",
        "source_sha",
        "trial_id",
        "cycle_index",
        "mpi_size",
        "formal_mpi8_qualified",
        "diagnostic_serial_fixture",
        "plan_identity",
        "common_identity",
        "common_identity_sha256",
        "qualified_primal_gate",
        "qualified_primal_gate_sha256",
        "partitions",
        "matrix_operator",
        "rank_bound_identity_sha256",
        "shards",
        "publication",
        "no_full_vector_python_allgather",
        "full_matrix_persisted",
        "capability_credit",
        "ordinary_default_changed",
        "manifest_payload_sha256",
    }
)
_SNAPSHOT_PLAN_KEYS = frozenset(
    {
        "path",
        "file_sha256",
        "payload_sha256",
        "provenance_sha256",
        "provenance_schema_version",
        "forest_leaf_catalog_sha256",
        "cell_degree_plan_sha256",
    }
)
_SNAPSHOT_GATE_KEYS = frozenset(
    {
        "full_active_residual",
        "full_active_residual_sha256",
        "port_operator_audit_sha256",
        "port_metrics_sha256",
        "primal_solver_telemetry",
        "primal_solver_telemetry_sha256",
    }
)
_PREDICTION_KEYS = frozenset(
    {
        "schema_version",
        "source_sha",
        "cycle_index",
        "marking_cycle_index",
        "action_id",
        "action_kind",
        "action_sha256",
        "action_identity_sha256",
        "marking_file_sha256",
        "marking_payload_sha256",
        "formal_goal_count",
        "formal_goal_inventory_sha256",
        "ordered_goal_ids",
        "predicted_deltas",
        "prediction_sha256",
    }
)
_MARKING_EVALUATOR_CONSUMED_KEY = "hid" + "den_auditor_consumed"
_POSITIVE_MARKING_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "classification",
        "pass",
        "source_sha",
        "mpi_size",
        "cycle_index",
        "action_kind",
        "doerfler_theta",
        "minimum_global_normalized_signal",
        "minimum_eligible_equal_weight_benefit",
        "algorithm_id",
        "formal_goal_count",
        "formal_goal_inventory_sha256",
        "fixed_equal_goal_weights",
        "current_plan_file_sha256",
        "current_plan_content_sha256",
        "current_state_sha256",
        "current_leaf_catalog_sha256",
        "current_degree_plan_sha256",
        "dwr_authority_file_sha256",
        "dwr_authority_schema",
        "dwr_authority_sha256",
        "structural_cost_model_sha256",
        "global_actual_dwr_report_sha256",
        "current_goal_sha256",
        "shadow_goal_sha256",
        "global_maximum_normalized_signed_dwr",
        "signed_cellwise_closure_verified",
        "signed_closure_used_for_ranking",
        "absolute_contributions_used_only_for_ranking",
        "eligible_normalized_benefit",
        "required_doerfler_benefit",
        "selected_doerfler_benefit",
        "selected_ranking_order",
        "ranking",
        "canonical_target_ids",
        "selected_signed_dwr_delta",
        "selected_signed_dwr_delta_sha256",
        "transition_preflight",
        "transition_producer_arguments",
        "blocker",
        "reference_derived",
        _MARKING_EVALUATOR_CONSUMED_KEY,
        "ordinary_default_changed",
        "marking_sha256",
    }
)
_CURRENT_PLAN_FIELDS = frozenset(
    {
        "base_config",
        "cell_interior_degree",
        "cell_interior_degree_plan_sha256",
        "cell_interior_degrees",
        "expected_forest",
        "maximum_level",
        "multilevel_audit",
        "ordinary_default_changed",
        "periodic_axes",
        "protect_material_interfaces",
        "provenance",
        "refinement_stage_count",
        "refinement_stages",
        "root_cell_box_catalog_sha256",
        "schema_version",
        "status",
        "trace_degree",
        "variable_trace_from_cell_degrees",
    }
)
_INITIAL_PROVENANCE_FIELDS = frozenset(
    {
        "accuracy_credit",
        "algorithm_id",
        "algorithm_sha256",
        "config_identity_sha256",
        "dwr_inputs_consumed",
        "error_map_inputs_consumed",
        "goal_value_inputs_consumed",
        "initial_state_sha256",
        "input_classes",
        "ordinary_default_changed",
        "path_id",
        "provenance_sha256",
        "schema_version",
        "selection_sha256",
        "solved_field_inputs_consumed",
        "source_sha",
        "stage_action_sha256s",
        "stage_prefix_sha256",
        "status",
    }
)
_TRANSITION_PROVENANCE_FIELDS = frozenset(
    {
        "algorithm_sha256",
        "cycle_index",
        "dwr_values_embedded",
        "evaluator_inputs_consumed",
        "from_cell_degree_plan_sha256",
        "from_leaf_catalog_sha256",
        "from_state_sha256",
        "goal_values_embedded",
        "next_cell_degree_plan_sha256",
        "next_leaf_catalog_sha256",
        "next_plan_canonical_solver_content_sha256",
        "next_stage_prefix_sha256",
        "next_state_sha256",
        "ordinary_default_changed",
        "previous_plan_canonical_solver_content_sha256",
        "previous_plan_content_sha256",
        "schema_version",
        "source_sha",
        "stage_action_sha256s",
        "status",
        "transition_action_cycle_index",
        "transition_action_id",
        "transition_action_kind",
        "transition_action_sha256",
        "transition_action_source_sha",
        "transition_action_target_ids",
        "transition_provenance_sha256",
    }
)
_FALSE_PLAN_FLAGS = frozenset(
    {
        "accuracy_credit",
        "dwr_inputs_consumed",
        "dwr_values_embedded",
        "error_map_inputs_consumed",
        "evaluator_inputs_consumed",
        "goal_value_inputs_consumed",
        "goal_values_embedded",
        "ordinary_default_changed",
        "solved_field_inputs_consumed",
    }
)
_TRANSITION_ACTION_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "action_id",
        "kind",
        "cycle_index",
        "source_sha",
        "algorithm_sha256",
        "from_state_sha256",
        "root_catalog_sha256",
        "from_leaf_catalog_sha256",
        "from_cell_degree_plan_sha256",
        "from_forest_geometry_sha256",
        "from_degree_plan_sha256",
        "stage_prefix_length",
        "stage_prefix_sha256",
        "requested_split_keys",
        "degree_deltas",
        "canonical_target_ids",
        "maximum_level",
        "expected_removed_leaf_keys",
        "expected_added_leaf_keys",
        "expected_net_added_leaf_count",
        "expected_next_leaf_catalog_sha256",
        "expected_next_cell_degree_plan_sha256",
        "expected_next_forest_geometry_sha256",
        "expected_next_degree_plan_sha256",
        "action_identity_sha256",
        "action_sha256",
    }
)


class BlindBindingError(ValueError):
    """Raised when a Task035e binding cannot be published safely."""


@dataclass(frozen=True, slots=True)
class BindingWriteReceipt:
    """Non-physical receipt for one immutable binding artifact."""

    kind: str
    path: Path
    file_sha256: str
    payload_sha256: str
    source_sha: str
    trial_id: str
    cycle_index: int


@dataclass(frozen=True, slots=True)
class VerificationPredictionWriteReceipt:
    """Receipt for one marking-derived signed prediction packet."""

    kind: str
    path: Path
    file_sha256: str
    payload_sha256: str
    source_sha: str
    cycle_index: int
    action_id: str


@dataclass(frozen=True, slots=True)
class ShadowEndpointInput:
    """Five files required for one selected solved shadow endpoint."""

    transition_action_path: Path
    goal_marking_path: Path
    verification_prediction_path: Path
    shadow_record_path: Path
    dwr_evidence_path: Path


@dataclass(frozen=True, slots=True)
class VerificationPredictionInput:
    """Transition action and signed prediction packet for one prior action."""

    transition_action_path: Path
    goal_marking_path: Path
    prediction_path: Path


@dataclass(frozen=True, slots=True)
class _SnapshotBinding:
    file_sha256: str
    payload_sha256: str
    residual_sha256: str
    residual_value: float


@dataclass(frozen=True, slots=True)
class _PlanBinding:
    payload: Mapping[str, Any]
    provenance: Mapping[str, Any]
    file_sha256: str
    content_sha256: str
    solver_content_sha256: str
    state_sha256: str


@dataclass(frozen=True, slots=True)
class _MarkingBinding:
    payload: Mapping[str, Any]
    file_sha256: str
    payload_sha256: str
    source_sha: str
    cycle_index: int
    action_kind: str
    canonical_target_ids: tuple[str, ...]
    predicted_deltas: tuple[tuple[str, float], ...]


@dataclass(frozen=True, slots=True)
class _PredictionBinding:
    source_sha: str
    cycle_index: int
    marking_cycle_index: int
    action_id: str
    action_kind: str
    action_sha256: str
    action_identity_sha256: str
    marking_file_sha256: str
    marking_payload_sha256: str
    predicted_deltas: tuple[tuple[str, float], ...]
    prediction_sha256: str


@dataclass(frozen=True, slots=True)
class _CycleContext:
    current: AdaptedCandidateOutput
    candidate: Mapping[str, Any]
    candidate_file_sha256: str
    candidate_payload_sha256: str
    plan: _PlanBinding
    snapshot: _SnapshotBinding
    shadow_payload: Mapping[str, Any]
    shadow_file_sha256: str
    p_action_count: int
    h_action_count: int
    trial: Mapping[str, Any]
    inventory: Mapping[str, int]
    resource_inventory_sha256: str


def _reject_nonfinite(value: str) -> None:
    raise BlindBindingError(f"non-finite JSON constant is forbidden: {value}")


def _reject_duplicate_object(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BlindBindingError(
                f"duplicate JSON object key is forbidden: {key}"
            )
        result[key] = value
    return result


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
        }
    if isinstance(value, (list, tuple)):
        return [_canonical(item) for item in value]
    return value


def _json_sha256(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            _canonical(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def _namespaced_json_sha256(value: Any, *, namespace: str) -> str:
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    digest.update(
        json.dumps(
            _canonical(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    )
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256(value: Any, *, label: str) -> str:
    digest = str(value)
    if _SHA256_RE.fullmatch(digest) is None:
        raise BlindBindingError(f"{label} must be a lowercase SHA-256")
    return digest


def _source_sha(value: Any) -> str:
    source = str(value)
    if _SOURCE_SHA_RE.fullmatch(source) is None:
        raise BlindBindingError(
            "source_sha must be one lowercase full Git SHA"
        )
    return source


def _opaque_id(value: Any, *, label: str) -> str:
    identifier = str(value)
    if _OPAQUE_ID_RE.fullmatch(identifier) is None:
        raise BlindBindingError(f"{label} is not a safe opaque identifier")
    return identifier


def _exact(
    value: Any,
    keys: frozenset[str] | set[str],
    *,
    label: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise BlindBindingError(f"{label} must be one JSON object")
    if set(value) != set(keys):
        raise BlindBindingError(
            f"{label} does not use its closed schema; "
            f"missing={sorted(set(keys) - set(value))}, "
            f"extra={sorted(set(value) - set(keys))}"
        )
    return value


def _safe_path(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise BlindBindingError(f"{label} must not be a symlink")
    resolved = path.expanduser().resolve()
    lowered = {part.lower() for part in resolved.parts}
    if lowered.intersection(_FORBIDDEN_PATH_PARTS):
        raise BlindBindingError(
            f"{label} crosses a protected evaluator/reference layer"
        )
    return resolved


def _regular_file(
    path: Path,
    *,
    label: str,
    private: bool = False,
) -> Path:
    resolved = _safe_path(path, label=label)
    try:
        metadata = resolved.stat()
    except OSError as exc:
        raise BlindBindingError(f"{label} is absent: {resolved}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise BlindBindingError(f"{label} is not a regular file")
    if private and stat.S_IMODE(metadata.st_mode) != 0o600:
        raise BlindBindingError(f"{label} must use mode 0600")
    return resolved


def _strict_json_object(
    path: Path,
    *,
    label: str,
    private: bool = False,
) -> tuple[Path, Mapping[str, Any], str]:
    resolved = _regular_file(path, label=label, private=private)
    try:
        payload = json.loads(
            resolved.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_reject_duplicate_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BlindBindingError(
            f"cannot read strict {label} JSON: {resolved}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise BlindBindingError(f"{label} must be one JSON object")
    return resolved, payload, _file_sha256(resolved)


def _reject_spec_leak(value: Any, *, label: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_spec_leak(str(key), label=label)
            _reject_spec_leak(item, label=label)
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _reject_spec_leak(item, label=label)
        return
    if isinstance(value, str):
        lowered = value.lower()
        if any(token in lowered for token in _FORBIDDEN_SPEC_TOKENS):
            raise BlindBindingError(
                f"{label} contains protected evaluator/reference data"
            )


def _encoded_json(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            _canonical(payload),
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _atomic_private_json(
    path: Path,
    payload: Mapping[str, Any],
    *,
    validator: Callable[[Path, str], None] | None = None,
) -> tuple[Path, str]:
    destination = _safe_path(path, label="binding output")
    if destination.exists():
        raise FileExistsError(
            f"refusing to overwrite immutable binding: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = _encoded_json(payload)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        temporary_sha = _file_sha256(temporary)
        if validator is not None:
            validator(temporary, temporary_sha)
        os.link(temporary, destination)
        temporary.unlink()
        directory_descriptor = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)
    if stat.S_IMODE(destination.stat().st_mode) != 0o600:
        raise BlindBindingError("published binding is not mode 0600")
    return destination, _file_sha256(destination)


def _adapt_current_record(path: Path) -> AdaptedCandidateOutput:
    resolved, _record_payload, observed_sha = _strict_json_object(
        path,
        label="current watchdog record",
    )
    try:
        current = adapt_candidate_output(
            CandidateWatchdogInput(resolved, observed_sha),
            output_role="current",
        )
    except CandidateOutputError as exc:
        raise BlindBindingError(str(exc)) from exc
    if current.record_sha256 != observed_sha:
        raise BlindBindingError("current watchdog record changed while read")
    return current


def _bound_reference(path: Path, *, label: str) -> dict[str, str]:
    resolved, _payload, file_sha = _strict_json_object(
        path,
        label=label,
    )
    return {
        "path": str(resolved),
        "sha256": file_sha,
    }


def _shadow_endpoint_row(
    endpoint: ShadowEndpointInput,
    *,
    lane: str,
    current: AdaptedCandidateOutput,
    current_plan_content_sha256: str,
    current_goal_sha256: str,
) -> dict[str, Any]:
    action, action_file_sha = _load_transition_action(
        endpoint.transition_action_path,
        private=False,
    )
    marking = _load_goal_marking(endpoint.goal_marking_path)
    _validate_action_against_marking(action, marking)
    prediction = _prediction_packet(
        endpoint.verification_prediction_path
    )
    expected_kind = "p-up" if lane == "p" else "h-refine"
    if (
        action["kind"] != expected_kind
        or action["source_sha"] != current.source_sha
        or action["cycle_index"] != current.cycle_index + 1
        or marking.source_sha != current.source_sha
        or marking.cycle_index != current.cycle_index
        or marking.payload["current_plan_file_sha256"]
        != current.plan_file_sha256
        or marking.payload["current_plan_content_sha256"]
        != current_plan_content_sha256
        or marking.payload["current_leaf_catalog_sha256"]
        != current.forest_leaf_catalog_sha256
        or marking.payload["current_degree_plan_sha256"]
        != current.cell_degree_plan_sha256
        or marking.payload["current_goal_sha256"]
        != current_goal_sha256
    ):
        raise BlindBindingError(
            f"{lane} selected shadow action/marking/current identity differs"
        )
    if (
        prediction.source_sha != current.source_sha
        or prediction.cycle_index != action["cycle_index"]
        or prediction.marking_cycle_index != marking.cycle_index
        or prediction.action_id != action["action_id"]
        or prediction.action_kind != action["kind"]
        or prediction.action_sha256 != action["action_sha256"]
        or prediction.action_identity_sha256
        != action["action_identity_sha256"]
        or prediction.marking_file_sha256 != marking.file_sha256
        or prediction.marking_payload_sha256 != marking.payload_sha256
        or prediction.predicted_deltas != marking.predicted_deltas
    ):
        raise BlindBindingError(
            f"{lane} selected shadow marking/prediction/action identity differs"
        )
    transition_path = _regular_file(
        endpoint.transition_action_path,
        label="shadow transition action",
    )
    marking_path = _regular_file(
        endpoint.goal_marking_path,
        label="shadow goal marking",
        private=True,
    )
    prediction_path = _regular_file(
        endpoint.verification_prediction_path,
        label="shadow verification prediction",
        private=True,
    )
    return {
        "transition_action": {
            "path": str(transition_path),
            "sha256": action_file_sha,
        },
        "goal_marking": {
            "path": str(marking_path),
            "sha256": marking.file_sha256,
        },
        "verification_prediction": {
            "path": str(prediction_path),
            "sha256": _file_sha256(prediction_path),
        },
        "shadow_record": _bound_reference(
            endpoint.shadow_record_path,
            label="shadow watchdog record",
        ),
        "dwr_evidence": _bound_reference(
            endpoint.dwr_evidence_path,
            label="shadow DWR evidence",
        ),
    }


def write_shadow_request(
    output_path: Path,
    *,
    current_record_path: Path,
    p_actions: Sequence[ShadowEndpointInput],
    h_actions: Sequence[ShadowEndpointInput],
) -> BindingWriteReceipt:
    """Write and independently replay one actual-shadow request."""

    current = _adapt_current_record(current_record_path)
    current_plan_path, current_plan_payload, current_plan_file_sha = (
        _strict_json_object(
            current.plan_path,
            label="current blind solver plan",
        )
    )
    if (
        current_plan_path != current.plan_path.resolve()
        or current_plan_file_sha != current.plan_file_sha256
    ):
        raise BlindBindingError(
            "current watchdog and on-disk solver plan identity differ"
        )
    current_plan_content_sha = _canonical_compact_sha256(
        current_plan_payload
    )
    current_goal_sha = blind_cycle.goal_vector_from_candidate_output(
        current.payload
    ).sha256
    payload = {
        "schema_version": REQUEST_SCHEMA,
        "current_record": _bound_reference(
            current_record_path,
            label="current watchdog record",
        ),
        "p_actions": [
            _shadow_endpoint_row(
                endpoint,
                lane="p",
                current=current,
                current_plan_content_sha256=current_plan_content_sha,
                current_goal_sha256=current_goal_sha,
            )
            for endpoint in p_actions
        ],
        "h_actions": [
            _shadow_endpoint_row(
                endpoint,
                lane="h",
                current=current,
                current_plan_content_sha256=current_plan_content_sha,
                current_goal_sha256=current_goal_sha,
            )
            for endpoint in h_actions
        ],
    }

    def validate(path: Path, file_sha: str) -> None:
        try:
            built = build_shadow_bundle(BoundJSONInput(path, file_sha))
        except (ShadowBundleError, CandidateOutputError) as exc:
            raise BlindBindingError(str(exc)) from exc
        if (
            built.source_sha != current.source_sha
            or built.trial_id != current.trial_id
            or built.cycle_index != current.cycle_index
            or built.current_output_sha256 != current.output_sha256
        ):
            raise BlindBindingError(
                "replayed shadow request differs from current identity"
            )

    destination, file_sha = _atomic_private_json(
        output_path,
        payload,
        validator=validate,
    )
    return BindingWriteReceipt(
        kind="shadow_request",
        path=destination,
        file_sha256=file_sha,
        payload_sha256=_json_sha256(payload),
        source_sha=current.source_sha,
        trial_id=current.trial_id,
        cycle_index=current.cycle_index,
    )


def _trial_metadata(
    path: Path,
    *,
    current: AdaptedCandidateOutput,
    current_plan: _PlanBinding,
) -> Mapping[str, Any]:
    resolved, _raw, _file_sha = _strict_json_object(
        path,
        label="blind trial metadata",
        private=True,
    )
    try:
        row = load_trial_metadata(resolved)
    except (TrialMetadataError, OSError, ValueError) as exc:
        raise BlindBindingError(str(exc)) from exc
    _reject_spec_leak(row, label="blind trial metadata")
    trial_id = _opaque_id(row["trial_id"], label="trial_id")
    algorithm_id = _opaque_id(row["algorithm_id"], label="algorithm_id")
    initial_path_id = _opaque_id(
        row["initial_path_id"],
        label="initial_path_id",
    )
    if trial_id != current.trial_id:
        raise BlindBindingError(
            "blind trial metadata and current record trial_id differ"
        )
    maximum_cycles = row["maximum_cycles"]
    if (
        type(maximum_cycles) is not int
        or not 1 <= maximum_cycles <= 6
        or current.cycle_index >= maximum_cycles
    ):
        raise BlindBindingError("maximum_cycles does not contain this cycle")
    initial_mesh = _sha256(
        row["initial_mesh_forest_sha256"],
        label="initial mesh forest SHA-256",
    )
    if row["source_sha"] != current.source_sha:
        raise BlindBindingError(
            "blind trial metadata source differs from the current record"
        )
    if current.cycle_index == 0 and (
        initial_mesh != current.forest_leaf_catalog_sha256
        or row["initial_degree_map_sha256"]
        != current.cell_degree_plan_sha256
        or row["initial_plan_file_sha256"]
        != current_plan.file_sha256
        or row["initial_plan_payload_sha256"]
        != current_plan.content_sha256
        or row["initial_state_sha256"] != current_plan.state_sha256
    ):
        raise BlindBindingError(
            "cycle-zero current forest/degree/plan/state differs from "
            "qualified trial metadata"
        )
    return {
        "trial_id": trial_id,
        "algorithm_id": algorithm_id,
        "initial_path_id": initial_path_id,
        "initial_mesh_forest_sha256": initial_mesh,
        "physical_identity_sha256": _sha256(
            row["physical_identity_sha256"],
            label="physical identity SHA-256",
        ),
        "maximum_cycles": int(maximum_cycles),
    }


def _load_candidate_output(
    path: Path,
    *,
    current: AdaptedCandidateOutput,
) -> tuple[Mapping[str, Any], str, str]:
    _resolved, payload, file_sha = _strict_json_object(
        path,
        label="candidate output",
        private=True,
    )
    if dict(payload) != dict(current.payload):
        raise BlindBindingError(
            "candidate output does not replay from the current watchdog record"
        )
    payload_sha = _json_sha256(payload)
    if payload_sha != current.output_sha256:
        raise BlindBindingError("candidate output content SHA-256 differs")
    blind_cycle.goal_vector_from_candidate_output(payload)
    return payload, file_sha, payload_sha


def _canonical_compact_sha256(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _assert_closed_blind_plan(
    payload: Mapping[str, Any],
) -> Mapping[str, Any]:
    if set(payload) != _CURRENT_PLAN_FIELDS:
        raise BlindBindingError(
            "current solver plan does not use the closed Task035e schema"
        )
    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise BlindBindingError(
            "current solver plan has no provenance object"
        )
    schema = provenance.get("schema_version")
    if schema == "task035e.blind-initial-provenance.v1":
        expected_fields = _INITIAL_PROVENANCE_FIELDS
    elif schema == PLAN_TRANSITION_SCHEMA:
        expected_fields = _TRANSITION_PROVENANCE_FIELDS
    else:
        raise BlindBindingError(
            "current solver plan provenance is not a blind transition schema"
        )
    if set(provenance) != expected_fields:
        raise BlindBindingError(
            "current solver plan provenance contains unknown or missing data"
        )
    for name in _FALSE_PLAN_FLAGS.intersection(provenance):
        if provenance[name] is not False:
            raise BlindBindingError(
                f"current solver plan violates blind flag {name}=false"
            )
    if payload.get("ordinary_default_changed") is not False:
        raise BlindBindingError(
            "current solver plan changes the ordinary default"
        )
    return provenance


def _config_from_plan(
    payload: Mapping[str, Any],
    *,
    source_sha: str,
) -> tuple[Any, str, Mapping[str, Any]]:
    base_config = payload.get("base_config")
    if not isinstance(base_config, Mapping):
        raise BlindBindingError("current plan has no base_config object")
    raw_h = base_config.get("mesh_target_size")
    if isinstance(raw_h, bool) or not isinstance(raw_h, (int, float)):
        raise BlindBindingError(
            "current plan mesh_target_size is not numeric"
        )
    h_nm = float(raw_h)
    path_id = next(
        (
            candidate
            for expected_h, candidate in {20.0: "A", 15.0: "B"}.items()
            if abs(h_nm - expected_h) <= 1.0e-12
        ),
        None,
    )
    if path_id is None:
        raise BlindBindingError(
            "current plan is not a formal Task035e Path A/B base mesh"
        )
    config = target_stage4_config(degree=6, h_nm=h_nm)
    canonical_initial = build_task035e_initial_space_plan(
        config,
        path_id=path_id,
        source_sha=source_sha,
        comm_size=8,
    ).plan_payload()
    if base_config != canonical_initial["base_config"]:
        raise BlindBindingError(
            "current plan base_config differs from its deterministic "
            f"Task035e Path {path_id} authority"
        )
    return config, path_id, canonical_initial


def _load_current_plan(
    current: AdaptedCandidateOutput,
) -> _PlanBinding:
    plan_path, payload, observed_file_sha = _strict_json_object(
        current.plan_path,
        label="current blind solver plan",
        private=True,
    )
    if (
        plan_path != current.plan_path.resolve()
        or observed_file_sha != current.plan_file_sha256
    ):
        raise BlindBindingError(
            "candidate-output and on-disk current plan file differ"
        )
    try:
        provenance = _assert_closed_blind_plan(payload)
        config, _path_id, canonical_initial = _config_from_plan(
            payload,
            source_sha=current.source_sha,
        )
        if (
            provenance.get("schema_version")
            == "task035e.blind-initial-provenance.v1"
            and payload != canonical_initial
        ):
            raise BlindBindingError(
                "initial current plan differs from its deterministic "
                "Task035e authority"
            )
        state = rebuild_hp_transition_state_from_solver_plan(
            config,
            current_plan=payload,
            comm_size=8,
        )
    except (TypeError, ValueError) as exc:
        if isinstance(exc, BlindBindingError):
            raise
        raise BlindBindingError(str(exc)) from exc
    provenance_cycle = provenance.get("cycle_index")
    if (
        provenance.get("source_sha") != current.source_sha
        or state.source_sha != current.source_sha
        or state.cycle_index != current.cycle_index
        or (
            current.cycle_index == 0
            and (
                provenance_cycle is not None
                or provenance.get("schema_version")
                != "task035e.blind-initial-provenance.v1"
            )
        )
        or (
            current.cycle_index > 0
            and (
                provenance_cycle != current.cycle_index
                or provenance.get("schema_version")
                != PLAN_TRANSITION_SCHEMA
            )
        )
        or state.audit["leaf_catalog_sha256"]
        != current.forest_leaf_catalog_sha256
        or state.audit["cell_degree_plan_sha256"]
        != current.cell_degree_plan_sha256
    ):
        raise BlindBindingError(
            "current plan provenance/state differs from candidate output"
        )
    return _PlanBinding(
        payload=dict(payload),
        provenance=dict(provenance),
        file_sha256=observed_file_sha,
        content_sha256=_canonical_compact_sha256(payload),
        solver_content_sha256=canonical_solver_content_sha256(payload),
        state_sha256=state.state_sha256,
    )


def _load_snapshot(
    path: Path,
    *,
    current: AdaptedCandidateOutput,
    current_plan: _PlanBinding,
    candidate: Mapping[str, Any],
) -> _SnapshotBinding:
    resolved, raw, file_sha = _strict_json_object(
        path,
        label="current live snapshot",
        private=True,
    )
    manifest = _exact(raw, _SNAPSHOT_KEYS, label="current live snapshot")
    if (
        manifest["schema_version"] != SNAPSHOT_SCHEMA
        or manifest["status"] != "multigoal_current_live_snapshot_pass"
        or manifest["pass"] is not True
        or manifest["role"] != "current_blind_state"
        or manifest["source_sha"] != current.source_sha
        or manifest["trial_id"] != current.trial_id
        or manifest["cycle_index"] != current.cycle_index
        or manifest["mpi_size"] != 8
        or manifest["formal_mpi8_qualified"] is not True
        or manifest["diagnostic_serial_fixture"] is not False
        or manifest["ordinary_default_changed"] is not False
        or manifest["no_full_vector_python_allgather"] is not True
        or manifest["full_matrix_persisted"] is not False
    ):
        raise BlindBindingError(
            "current live snapshot role/source/trial/MPI identity differs"
        )
    stored_payload_sha = _sha256(
        manifest["manifest_payload_sha256"],
        label="snapshot manifest payload SHA-256",
    )
    unsigned = dict(manifest)
    unsigned.pop("manifest_payload_sha256")
    if (
        _namespaced_json_sha256(
            unsigned,
            namespace=SNAPSHOT_MANIFEST_NAMESPACE,
        )
        != stored_payload_sha
    ):
        raise BlindBindingError("snapshot manifest self-hash differs")

    plan = _exact(
        manifest["plan_identity"],
        _SNAPSHOT_PLAN_KEYS,
        label="snapshot plan identity",
    )
    plan_path = _regular_file(
        Path(str(plan["path"])),
        label="snapshot current plan",
    )
    if (
        plan_path != current.plan_path.resolve()
        or _file_sha256(plan_path)
        != _sha256(plan["file_sha256"], label="snapshot plan file SHA-256")
        or str(plan["file_sha256"]) != current.plan_file_sha256
        or plan["forest_leaf_catalog_sha256"]
        != current.forest_leaf_catalog_sha256
        or plan["cell_degree_plan_sha256"]
        != current.cell_degree_plan_sha256
    ):
        raise BlindBindingError(
            "snapshot plan/forest/degree identity differs from current"
        )
    _plan_resolved, plan_payload, _plan_file_sha = _strict_json_object(
        plan_path,
        label="snapshot current plan",
        private=True,
    )
    if (
        dict(plan_payload) != dict(current_plan.payload)
        or
        _namespaced_json_sha256(
            plan_payload,
            namespace=SNAPSHOT_PLAN_NAMESPACE,
        )
        != _sha256(
            plan["payload_sha256"],
            label="snapshot plan payload SHA-256",
        )
    ):
        raise BlindBindingError("snapshot executed-plan payload hash differs")

    gate = _exact(
        manifest["qualified_primal_gate"],
        _SNAPSHOT_GATE_KEYS,
        label="snapshot qualified primal Gate",
    )
    common_identity = manifest["common_identity"]
    if (
        not isinstance(common_identity, Mapping)
        or _namespaced_json_sha256(
            common_identity,
            namespace=SNAPSHOT_COMMON_NAMESPACE,
        )
        != _sha256(
            manifest["common_identity_sha256"],
            label="snapshot common identity SHA-256",
        )
        or _namespaced_json_sha256(
            gate,
            namespace=SNAPSHOT_GATE_NAMESPACE,
        )
        != _sha256(
            manifest["qualified_primal_gate_sha256"],
            label="snapshot qualified primal Gate SHA-256",
        )
    ):
        raise BlindBindingError(
            "snapshot common or qualified-Gate identity differs"
        )
    capability = manifest["capability_credit"]
    if (
        not isinstance(capability, Mapping)
        or capability.get("current_primal_snapshot_complete") is not True
        or capability.get("accuracy_credit") is not False
    ):
        raise BlindBindingError("snapshot capability boundary differs")
    residual = gate["full_active_residual"]
    if not isinstance(residual, Mapping):
        raise BlindBindingError("snapshot full active residual is absent")
    residual_sha = _sha256(
        gate["full_active_residual_sha256"],
        label="snapshot full residual SHA-256",
    )
    if (
        _namespaced_json_sha256(
            residual,
            namespace=SNAPSHOT_RESIDUAL_NAMESPACE,
        )
        != residual_sha
    ):
        raise BlindBindingError("snapshot full residual self-hash differs")
    residual_value = residual.get("linear_system_relative_residual")
    if (
        isinstance(residual_value, bool)
        or not isinstance(residual_value, (int, float))
        or not math.isfinite(float(residual_value))
        or float(residual_value) < 0.0
        or not math.isclose(
            float(residual_value),
            float(candidate["full_explicit_true_residual"]),
            rel_tol=0.0,
            abs_tol=1.0e-18,
        )
    ):
        raise BlindBindingError(
            "snapshot and candidate full residual values differ"
        )

    shards = manifest["shards"]
    if not isinstance(shards, list) or len(shards) != 8:
        raise BlindBindingError("formal snapshot must bind eight rank shards")
    ranks: list[int] = []
    for index, item in enumerate(shards):
        if not isinstance(item, Mapping):
            raise BlindBindingError("snapshot shard row is not an object")
        rank = item.get("rank")
        path_value = item.get("path")
        expected_sha = item.get("file_sha256")
        if (
            type(rank) is not int
            or not isinstance(path_value, str)
            or not path_value
        ):
            raise BlindBindingError("snapshot shard identity is malformed")
        shard_path = Path(path_value)
        if not shard_path.is_absolute():
            shard_path = resolved.parent / shard_path
        shard_path = _regular_file(
            shard_path,
            label=f"snapshot rank-{rank} shard",
            private=True,
        )
        if _file_sha256(shard_path) != _sha256(
            expected_sha,
            label=f"snapshot rank-{rank} shard SHA-256",
        ):
            raise BlindBindingError(
                f"snapshot rank-{rank} shard file SHA-256 differs"
            )
        ranks.append(rank)
    if ranks != list(range(8)):
        raise BlindBindingError("snapshot shard ranks are not canonical MPI8")
    return _SnapshotBinding(
        file_sha256=file_sha,
        payload_sha256=stored_payload_sha,
        residual_sha256=residual_sha,
        residual_value=float(residual_value),
    )


def _load_shadow_bundle(
    path: Path,
    *,
    current: AdaptedCandidateOutput,
    candidate: Mapping[str, Any],
    candidate_payload_sha256: str,
) -> tuple[Mapping[str, Any], str, int, int]:
    _resolved, raw, file_sha = _strict_json_object(
        path,
        label="actual shadow bundle",
        private=True,
    )
    outer = _exact(
        raw,
        {"schema_version", "sha256", "payload"},
        label="actual shadow bundle outer",
    )
    payload = outer["payload"]
    if not isinstance(payload, Mapping):
        raise BlindBindingError("actual shadow bundle payload is absent")
    if (
        outer["schema_version"] != blind_cycle.SHADOW_BUNDLE_SCHEMA
        or payload.get("schema_version")
        != blind_cycle.SHADOW_BUNDLE_SCHEMA
        or _sha256(
            outer["sha256"],
            label="actual shadow bundle payload SHA-256",
        )
        != _json_sha256(payload)
    ):
        raise BlindBindingError("actual shadow bundle self-hash differs")
    goals = blind_cycle.goal_vector_from_candidate_output(candidate)
    try:
        catalog = blind_cycle._shadow_catalog(
            payload,
            current=goals,
            source_sha=current.source_sha,
            trial_id=current.trial_id,
            cycle_index=current.cycle_index,
            mesh_forest_sha256=current.forest_leaf_catalog_sha256,
            degree_map_sha256=current.cell_degree_plan_sha256,
            plan_file_sha256=current.plan_file_sha256,
            complete_output_sha256=candidate_payload_sha256,
        )
    except (TypeError, ValueError) as exc:
        raise BlindBindingError(str(exc)) from exc
    return (
        payload,
        file_sha,
        len(catalog.p_actions),
        len(catalog.h_actions),
    )


def _cycle_context(
    *,
    trial_metadata_path: Path,
    current_record_path: Path,
    candidate_output_path: Path,
    current_snapshot_path: Path,
    shadow_bundle_path: Path,
) -> _CycleContext:
    current = _adapt_current_record(current_record_path)
    candidate, candidate_file_sha, candidate_payload_sha = (
        _load_candidate_output(candidate_output_path, current=current)
    )
    plan = _load_current_plan(current)
    trial = _trial_metadata(
        trial_metadata_path,
        current=current,
        current_plan=plan,
    )
    snapshot = _load_snapshot(
        current_snapshot_path,
        current=current,
        current_plan=plan,
        candidate=candidate,
    )
    shadow_payload, shadow_file_sha, p_count, h_count = (
        _load_shadow_bundle(
            shadow_bundle_path,
            current=current,
            candidate=candidate,
            candidate_payload_sha256=candidate_payload_sha,
        )
    )
    structural = current.structural_inventory
    inventory = {
        "active_dofs": int(structural["active_fe_dofs"]),
        "rows": int(structural["matrix_rows"]),
        "matrix_nnz": int(structural["matrix_nnz"]),
        "factor_nnz": int(structural["factor_nnz"]),
        "solver_peak_bytes": int(structural["solver_peak_bytes"]),
    }
    StructuralInventory(**inventory)
    inventory_payload = {
        "schema_version": "task035e.resource-authority.v1",
        **inventory,
        "swap_peak_bytes": 0,
        "mpi_size": 8,
        "same_solver_lifecycle_telemetry": True,
    }
    return _CycleContext(
        current=current,
        candidate=candidate,
        candidate_file_sha256=candidate_file_sha,
        candidate_payload_sha256=candidate_payload_sha,
        plan=plan,
        snapshot=snapshot,
        shadow_payload=shadow_payload,
        shadow_file_sha256=shadow_file_sha,
        p_action_count=p_count,
        h_action_count=h_count,
        trial=trial,
        inventory=inventory,
        resource_inventory_sha256=_json_sha256(inventory_payload),
    )


def _manifest_payload(context: _CycleContext) -> dict[str, Any]:
    manifest = build_cycle_manifest(
        trial_id=str(context.trial["trial_id"]),
        algorithm_id=str(context.trial["algorithm_id"]),
        source_sha=context.current.source_sha,
        initial_path_id=str(context.trial["initial_path_id"]),
        maximum_cycles=int(context.trial["maximum_cycles"]),
        cycle_index=context.current.cycle_index,
        state=MANIFEST_STATE,
        mesh_forest_sha256=context.current.forest_leaf_catalog_sha256,
        degree_map_sha256=context.current.cell_degree_plan_sha256,
        solution_snapshot_sha256=context.snapshot.payload_sha256,
        goal_inventory_sha256=FORMAL_GOAL_INVENTORY_SHA256,
        full_residual_sha256=context.snapshot.residual_sha256,
        adjoint_bundle_sha256=context.shadow_file_sha256,
        p_shadow_bundle_sha256=(
            context.shadow_file_sha256
            if context.p_action_count
            else None
        ),
        h_shadow_bundle_sha256=(
            context.shadow_file_sha256
            if context.h_action_count
            else None
        ),
        resource_inventory_sha256=(
            context.resource_inventory_sha256
        ),
    )
    _reject_spec_leak(manifest, label="generated blind input manifest")
    if (
        set(manifest) != {"schema", "trial", "cycle"}
        or manifest["schema"] != BLIND_INPUT_MANIFEST_SCHEMA
    ):
        raise BlindBindingError(
            "generated blind input manifest does not use the closed schema"
        )
    return manifest


def write_blind_input_manifest(
    output_path: Path,
    *,
    trial_metadata_path: Path,
    current_record_path: Path,
    candidate_output_path: Path,
    current_snapshot_path: Path,
    shadow_bundle_path: Path,
) -> BindingWriteReceipt:
    """Publish the exact path-free manifest accepted by the leak checker."""

    context = _cycle_context(
        trial_metadata_path=trial_metadata_path,
        current_record_path=current_record_path,
        candidate_output_path=candidate_output_path,
        current_snapshot_path=current_snapshot_path,
        shadow_bundle_path=shadow_bundle_path,
    )
    payload = _manifest_payload(context)
    destination, file_sha = _atomic_private_json(output_path, payload)
    return BindingWriteReceipt(
        kind="blind_input_manifest",
        path=destination,
        file_sha256=file_sha,
        payload_sha256=cycle_manifest_sha256(payload),
        source_sha=context.current.source_sha,
        trial_id=context.current.trial_id,
        cycle_index=context.current.cycle_index,
    )


def _scalar(candidate: Mapping[str, Any], name: str) -> float:
    rows = candidate.get("scalar_observations")
    if not isinstance(rows, list):
        raise BlindBindingError("candidate scalar observations are absent")
    found = [
        row.get("value")
        for row in rows
        if isinstance(row, Mapping) and row.get("name") == name
    ]
    if (
        len(found) != 1
        or isinstance(found[0], bool)
        or not isinstance(found[0], (int, float))
        or not math.isfinite(float(found[0]))
    ):
        raise BlindBindingError(f"candidate scalar {name} is invalid")
    return float(found[0])


def _internal_gates(
    path: Path,
    *,
    context: _CycleContext,
) -> Mapping[str, Any]:
    _resolved, raw, _file_sha = _strict_json_object(
        path,
        label="blind internal-Gate authority",
        private=True,
    )
    _reject_spec_leak(raw, label="blind internal-Gate authority")
    try:
        row = validate_internal_gate_authority(
            raw,
            expected_source_sha=context.current.source_sha,
            expected_trial_id=context.current.trial_id,
            expected_cycle_index=context.current.cycle_index,
            expected_candidate_record_file_sha256=(
                context.current.record_sha256
            ),
            expected_candidate_output_file_sha256=(
                context.candidate_file_sha256
            ),
            expected_candidate_output_payload_sha256=(
                context.candidate_payload_sha256
            ),
            expected_plan_file_sha256=context.plan.file_sha256,
            expected_plan_payload_sha256=context.plan.content_sha256,
            expected_mesh_forest_sha256=(
                context.current.forest_leaf_catalog_sha256
            ),
            expected_degree_map_sha256=(
                context.current.cell_degree_plan_sha256
            ),
            expected_snapshot_file_sha256=context.snapshot.file_sha256,
            expected_snapshot_payload_sha256=(
                context.snapshot.payload_sha256
            ),
            expected_snapshot_full_residual_sha256=(
                context.snapshot.residual_sha256
            ),
        )
        gates = InternalGates(**dict(row["gates"]))
    except (InternalGateAuthorityError, TypeError, ValueError) as exc:
        raise BlindBindingError(str(exc)) from exc
    if row["schema_version"] != INTERNAL_GATE_AUTHORITY_SCHEMA:
        raise BlindBindingError("blind internal-Gate authority schema differs")
    energy_closure_error = abs(
        _scalar(context.candidate, "energy_closure") - 1.0
    )
    absorption = _scalar(context.candidate, "A_volume")
    if (
        not math.isclose(
            gates.full_explicit_residual,
            context.snapshot.residual_value,
            rel_tol=0.0,
            abs_tol=1.0e-18,
        )
        or not math.isclose(
            gates.energy_closure_error,
            energy_closure_error,
            rel_tol=0.0,
            abs_tol=1.0e-18,
        )
        or not math.isclose(
            gates.absorption_volume,
            absorption,
            rel_tol=0.0,
            abs_tol=1.0e-18,
        )
    ):
        raise BlindBindingError(
            "internal Gates do not match current residual/energy/absorption"
        )
    return row


def _load_isolation_report(
    path: Path,
    *,
    context: _CycleContext,
    manifest_sha256: str,
) -> str:
    _resolved, raw, file_sha = _strict_json_object(
        path,
        label="reference-isolation report",
        private=True,
    )
    outer = _exact(
        raw,
        {"schema_version", "producer", "sha256", "payload"},
        label="reference-isolation report outer",
    )
    producer = _exact(
        outer["producer"],
        {"source", "file_sha256"},
        label="reference-isolation report producer",
    )
    root = Path(__file__).resolve().parents[1]
    checker_relative = "benchmarks/task035e_reference_leak_checker.py"
    checker_path = (root / checker_relative).resolve()
    payload = outer["payload"]
    if not isinstance(payload, Mapping):
        raise BlindBindingError(
            "reference-isolation report payload is absent"
        )
    if (
        outer["schema_version"] != CHECKER_ARTIFACT_SCHEMA
        or producer["source"] != checker_relative
        or producer["file_sha256"] != _file_sha256(checker_path)
        or _sha256(
            outer["sha256"],
            label="reference-isolation report payload SHA-256",
        )
        != _json_sha256(payload)
        or payload.get("schema") != CHECKER_SCHEMA
        or payload.get("schema_version") != CHECKER_SCHEMA
        or payload.get("source_sha") != context.current.source_sha
        or payload.get("manifest_sha256") != manifest_sha256
        or payload.get("pass") is not True
        or payload.get("status") != "reference_isolation_pass"
        or payload.get("exit_code") != 0
    ):
        raise BlindBindingError(
            "reference-isolation report identity/pass differs"
        )
    return file_sha


def _load_transition_action(
    path: Path,
    *,
    private: bool = True,
) -> tuple[Mapping[str, Any], str]:
    _resolved, raw, file_sha = _strict_json_object(
        path,
        label="executed transition action",
        private=private,
    )
    if set(raw) == {"schema_version", "sha256", "payload"}:
        payload = raw["payload"]
        if (
            raw["schema_version"] != HP_TRANSITION_ACTION_SCHEMA
            or not isinstance(payload, Mapping)
            or _sha256(
                raw["sha256"],
                label="transition outer payload SHA-256",
            )
            != _json_sha256(payload)
        ):
            raise BlindBindingError("transition action outer hash differs")
    else:
        payload = raw
    action = _exact(
        payload,
        _TRANSITION_ACTION_KEYS,
        label="executed transition action",
    )
    unhashed = dict(action)
    observed_action_sha = _sha256(
        unhashed.pop("action_sha256"),
        label="transition action SHA-256",
    )
    identity = {
        "action_id": action["action_id"],
        "kind": action["kind"],
        "cycle_index": action["cycle_index"],
        "source_sha": action["source_sha"],
        "algorithm_sha256": action["algorithm_sha256"],
        "canonical_target_ids": action["canonical_target_ids"],
    }
    if (
        action["schema_version"] != HP_TRANSITION_ACTION_SCHEMA
        or action["status"] != "hp_transition_action_closed"
        or _json_sha256(unhashed) != observed_action_sha
        or _json_sha256(identity)
        != _sha256(
            action["action_identity_sha256"],
            label="transition action identity SHA-256",
        )
    ):
        raise BlindBindingError("transition action self-identity differs")
    return action, file_sha


def _ordered_goal_packet(
    values: Any,
    *,
    label: str,
    mapping_input: bool,
) -> tuple[tuple[str, float], ...]:
    if mapping_input:
        if not isinstance(values, Mapping) or set(values) != set(
            FORMAL_GOAL_IDS
        ):
            raise BlindBindingError(
                f"{label} misses the complete 59-goal inventory"
            )
        rows: Sequence[Any] = tuple(
            (goal_id, values[goal_id]) for goal_id in FORMAL_GOAL_IDS
        )
    else:
        if (
            isinstance(values, (str, bytes))
            or not isinstance(values, Sequence)
            or len(values) != len(FORMAL_GOAL_IDS)
        ):
            raise BlindBindingError(
                f"{label} must be the ordered 59-goal packet"
            )
        rows = values
    packet: list[tuple[str, float]] = []
    for index, row in enumerate(rows):
        if (
            isinstance(row, (str, bytes))
            or not isinstance(row, Sequence)
            or len(row) != 2
            or row[0] != FORMAL_GOAL_IDS[index]
        ):
            raise BlindBindingError(
                f"{label} goal order differs at index {index}"
            )
        value = row[1]
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
        ):
            raise BlindBindingError(
                f"{label} {FORMAL_GOAL_IDS[index]} is not finite"
            )
        packet.append((FORMAL_GOAL_IDS[index], float(value)))
    return tuple(packet)


def _load_goal_marking(path: Path) -> _MarkingBinding:
    _resolved, raw, file_sha = _strict_json_object(
        path,
        label="goal marking",
        private=True,
    )
    row = _exact(
        raw,
        _POSITIVE_MARKING_KEYS,
        label="positive goal marking",
    )
    leak_checked = dict(row)
    leak_checked.pop(_MARKING_EVALUATOR_CONSUMED_KEY)
    _reject_spec_leak(leak_checked, label="goal marking")
    unsigned = dict(row)
    stored_payload_sha = _sha256(
        unsigned.pop("marking_sha256"),
        label="goal marking payload SHA-256",
    )
    accepted_marking_roles = {
        (
            "goal_marking_targets_selected",
            "REFERENCE_BLIND_LOCAL_MARKING_PASS",
        ),
        (
            "goal_marking_verification_only_selected",
            "REFERENCE_BLIND_VERIFICATION_ONLY",
        ),
    }
    if (
        row["schema_version"] != GOAL_MARKING_SCHEMA
        or (row["status"], row["classification"])
        not in accepted_marking_roles
        or row["pass"] is not True
        or row["mpi_size"] != 8
        or row["formal_goal_count"] != len(FORMAL_GOAL_IDS)
        or row["formal_goal_inventory_sha256"]
        != FORMAL_GOAL_INVENTORY_SHA256
        or row["signed_cellwise_closure_verified"] is not True
        or row["reference_derived"] is not False
        or row[_MARKING_EVALUATOR_CONSUMED_KEY] is not False
        or row["ordinary_default_changed"] is not False
        or _namespaced_json_sha256(
            unsigned,
            namespace=GOAL_MARKING_SCHEMA,
        )
        != stored_payload_sha
    ):
        raise BlindBindingError(
            "goal marking pass/identity/self-hash differs"
        )
    source = _source_sha(row["source_sha"])
    cycle_index = row["cycle_index"]
    if type(cycle_index) is not int or not 0 <= cycle_index <= 4:
        raise BlindBindingError(
            "goal marking cycle must leave room for an executed transition"
        )
    action_kind = str(row["action_kind"])
    if action_kind not in {"p-up", "h-refine"}:
        raise BlindBindingError(
            "positive goal marking action must be p-up or h-refine"
        )
    targets = row["canonical_target_ids"]
    arguments = row["transition_producer_arguments"]
    if (
        not isinstance(targets, list)
        or not targets
        or any(not isinstance(value, str) or not value for value in targets)
        or len(set(targets)) != len(targets)
        or not isinstance(arguments, Mapping)
        or set(arguments) != {"action_kind", "canonical_target_ids"}
        or arguments["action_kind"] != action_kind
        or arguments["canonical_target_ids"] != targets
    ):
        raise BlindBindingError(
            "goal marking transition targets/arguments differ"
        )
    packet = _ordered_goal_packet(
        row["selected_signed_dwr_delta"],
        label="goal marking selected signed DWR",
        mapping_input=True,
    )
    expected_packet_sha = _namespaced_json_sha256(
        {
            "formal_goal_inventory_sha256": (
                FORMAL_GOAL_INVENTORY_SHA256
            ),
            "ordered_goal_ids": list(FORMAL_GOAL_IDS),
            "canonical_target_ids": list(targets),
            "signed_dwr_delta": dict(packet),
        },
        namespace="task035e.goal-marking-selected-signed-dwr.v1",
    )
    if (
        _sha256(
            row["selected_signed_dwr_delta_sha256"],
            label="selected signed DWR SHA-256",
        )
        != expected_packet_sha
    ):
        raise BlindBindingError(
            "goal marking selected signed DWR self-hash differs"
        )
    for name in (
        "current_plan_file_sha256",
        "current_plan_content_sha256",
        "current_state_sha256",
        "current_leaf_catalog_sha256",
        "current_degree_plan_sha256",
    ):
        _sha256(row[name], label=f"goal marking {name}")
    return _MarkingBinding(
        payload=dict(row),
        file_sha256=file_sha,
        payload_sha256=stored_payload_sha,
        source_sha=source,
        cycle_index=int(cycle_index),
        action_kind=action_kind,
        canonical_target_ids=tuple(str(value) for value in targets),
        predicted_deltas=packet,
    )


def _validate_action_against_marking(
    action: Mapping[str, Any],
    marking: _MarkingBinding,
) -> None:
    row = marking.payload
    if (
        action["source_sha"] != marking.source_sha
        or action["cycle_index"] != marking.cycle_index + 1
        or action["kind"] != marking.action_kind
        or tuple(action["canonical_target_ids"])
        != marking.canonical_target_ids
        or action["from_state_sha256"] != row["current_state_sha256"]
        or action["from_leaf_catalog_sha256"]
        != row["current_leaf_catalog_sha256"]
        or action["from_cell_degree_plan_sha256"]
        != row["current_degree_plan_sha256"]
    ):
        raise BlindBindingError(
            "transition action source/cycle/kind/targets/current state "
            "differ from the goal marking"
        )


def write_verification_prediction(
    output_path: Path,
    *,
    goal_marking_path: Path,
    transition_action_path: Path,
) -> VerificationPredictionWriteReceipt:
    """Publish a closed 59-goal prediction derived only from one marking."""

    marking = _load_goal_marking(goal_marking_path)
    action, _action_file_sha = _load_transition_action(
        transition_action_path
    )
    _validate_action_against_marking(action, marking)
    unsigned = {
        "schema_version": VERIFICATION_PREDICTION_SCHEMA,
        "source_sha": marking.source_sha,
        "cycle_index": int(action["cycle_index"]),
        "marking_cycle_index": marking.cycle_index,
        "action_id": str(action["action_id"]),
        "action_kind": str(action["kind"]),
        "action_sha256": str(action["action_sha256"]),
        "action_identity_sha256": str(
            action["action_identity_sha256"]
        ),
        "marking_file_sha256": marking.file_sha256,
        "marking_payload_sha256": marking.payload_sha256,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
        "ordered_goal_ids": list(FORMAL_GOAL_IDS),
        "predicted_deltas": [
            [goal_id, value]
            for goal_id, value in marking.predicted_deltas
        ],
    }
    prediction_sha = _namespaced_json_sha256(
        unsigned,
        namespace=VERIFICATION_PREDICTION_SCHEMA,
    )
    payload = {**unsigned, "prediction_sha256": prediction_sha}
    destination, file_sha = _atomic_private_json(output_path, payload)
    return VerificationPredictionWriteReceipt(
        kind="verification_prediction",
        path=destination,
        file_sha256=file_sha,
        payload_sha256=prediction_sha,
        source_sha=marking.source_sha,
        cycle_index=int(action["cycle_index"]),
        action_id=str(action["action_id"]),
    )


def _prediction_packet(
    path: Path,
) -> _PredictionBinding:
    _resolved, raw, _file_sha = _strict_json_object(
        path,
        label="shadow verification prediction",
        private=True,
    )
    row = _exact(
        raw,
        _PREDICTION_KEYS,
        label="shadow verification prediction",
    )
    _reject_spec_leak(row, label="shadow verification prediction")
    if row["schema_version"] != VERIFICATION_PREDICTION_SCHEMA:
        raise BlindBindingError(
            "shadow verification prediction schema differs"
        )
    unsigned = dict(row)
    prediction_sha = _sha256(
        unsigned.pop("prediction_sha256"),
        label="shadow verification prediction SHA-256",
    )
    if (
        _namespaced_json_sha256(
            unsigned,
            namespace=VERIFICATION_PREDICTION_SCHEMA,
        )
        != prediction_sha
    ):
        raise BlindBindingError(
            "shadow verification prediction self-hash differs"
        )
    source = _source_sha(row["source_sha"])
    cycle = row["cycle_index"]
    marking_cycle = row["marking_cycle_index"]
    if (
        type(cycle) is not int
        or type(marking_cycle) is not int
        or not 1 <= cycle <= 5
        or marking_cycle != cycle - 1
    ):
        raise BlindBindingError(
            "shadow verification prediction cycle identity differs"
        )
    action_id = _opaque_id(row["action_id"], label="prediction action_id")
    action_kind = str(row["action_kind"])
    if action_kind not in {"p-up", "h-refine"}:
        raise BlindBindingError(
            "prediction action_kind must be p-up or h-refine"
        )
    if (
        row["formal_goal_count"] != len(FORMAL_GOAL_IDS)
        or row["formal_goal_inventory_sha256"]
        != FORMAL_GOAL_INVENTORY_SHA256
        or row["ordered_goal_ids"] != list(FORMAL_GOAL_IDS)
    ):
        raise BlindBindingError(
            "prediction packet formal goal identity/order differs"
        )
    packet = _ordered_goal_packet(
        row["predicted_deltas"],
        label="prediction packet",
        mapping_input=False,
    )
    return _PredictionBinding(
        source_sha=source,
        cycle_index=int(cycle),
        marking_cycle_index=int(marking_cycle),
        action_id=action_id,
        action_kind=action_kind,
        action_sha256=_sha256(
            row["action_sha256"],
            label="prediction action SHA-256",
        ),
        action_identity_sha256=_sha256(
            row["action_identity_sha256"],
            label="prediction action identity SHA-256",
        ),
        marking_file_sha256=_sha256(
            row["marking_file_sha256"],
            label="prediction marking file SHA-256",
        ),
        marking_payload_sha256=_sha256(
            row["marking_payload_sha256"],
            label="prediction marking payload SHA-256",
        ),
        predicted_deltas=packet,
        prediction_sha256=prediction_sha,
    )


def _stability_repeat_binding(
    *,
    context: _CycleContext,
    previous: Any,
    transition_action_path: Path,
) -> Mapping[str, Any]:
    """Recompute the identity-only proof for one executed ``p-keep``."""

    action, action_file_sha = _load_transition_action(
        transition_action_path
    )
    provenance = context.plan.provenance
    if (
        action["kind"] != "p-keep"
        or action["source_sha"] != context.current.source_sha
        or action["cycle_index"] != context.current.cycle_index
        or action["from_state_sha256"] != previous.state_sha256
        or action["canonical_target_ids"] != []
        or action["requested_split_keys"] != []
        or action["degree_deltas"] != []
        or action["maximum_level"] is not None
        or action["expected_removed_leaf_keys"] != []
        or action["expected_added_leaf_keys"] != []
        or action["expected_net_added_leaf_count"] != 0
        or action["from_leaf_catalog_sha256"]
        != previous.mesh_forest_sha256
        or action["expected_next_leaf_catalog_sha256"]
        != previous.mesh_forest_sha256
        or action["from_cell_degree_plan_sha256"]
        != previous.degree_map_sha256
        or action["expected_next_cell_degree_plan_sha256"]
        != previous.degree_map_sha256
        or context.current.forest_leaf_catalog_sha256
        != previous.mesh_forest_sha256
        or context.current.cell_degree_plan_sha256
        != previous.degree_map_sha256
        or context.plan.solver_content_sha256
        != previous.plan_solver_content_sha256
        or provenance.get("schema_version") != PLAN_TRANSITION_SCHEMA
        or provenance.get("source_sha") != context.current.source_sha
        or provenance.get("cycle_index") != context.current.cycle_index
        or provenance.get("previous_plan_content_sha256")
        != previous.plan_content_sha256
        or provenance.get(
            "previous_plan_canonical_solver_content_sha256"
        )
        != previous.plan_solver_content_sha256
        or provenance.get("from_state_sha256") != previous.state_sha256
        or provenance.get("transition_action_sha256")
        != action["action_sha256"]
        or provenance.get("transition_action_id") != action["action_id"]
        or provenance.get("transition_action_kind") != "p-keep"
        or provenance.get("transition_action_cycle_index")
        != action["cycle_index"]
        or provenance.get("transition_action_source_sha")
        != action["source_sha"]
        or provenance.get("transition_action_target_ids") != []
        or provenance.get("next_state_sha256")
        != context.plan.state_sha256
        or provenance.get("from_leaf_catalog_sha256")
        != previous.mesh_forest_sha256
        or provenance.get("next_leaf_catalog_sha256")
        != context.current.forest_leaf_catalog_sha256
        or provenance.get("from_cell_degree_plan_sha256")
        != previous.degree_map_sha256
        or provenance.get("next_cell_degree_plan_sha256")
        != context.current.cell_degree_plan_sha256
        or provenance.get("next_plan_canonical_solver_content_sha256")
        != context.plan.solver_content_sha256
    ):
        raise BlindBindingError(
            "p-keep action/current plan does not replay the prior solver state"
        )
    if (
        context.plan.file_sha256 == previous.plan_file_sha256
        or context.plan.content_sha256 == previous.plan_content_sha256
        or context.plan.state_sha256 == previous.state_sha256
        or context.snapshot.payload_sha256
        == previous.solution_snapshot_sha256
        or context.current.record_sha256
        == previous.watchdog_record_file_sha256
    ):
        raise BlindBindingError(
            "p-keep reused a prior full-plan/state/snapshot/watchdog identity"
        )
    verification = StabilityRepeatVerification(
        action_id=str(action["action_id"]),
        action_kind="p-keep",
        action_sha256=str(action["action_sha256"]),
        action_file_sha256=action_file_sha,
        action_identity_sha256=str(action["action_identity_sha256"]),
        from_state_sha256=previous.state_sha256,
        next_state_sha256=context.plan.state_sha256,
        previous_plan_file_sha256=previous.plan_file_sha256,
        previous_plan_content_sha256=previous.plan_content_sha256,
        previous_plan_solver_content_sha256=(
            previous.plan_solver_content_sha256
        ),
        next_plan_file_sha256=context.plan.file_sha256,
        next_plan_content_sha256=context.plan.content_sha256,
        next_plan_solver_content_sha256=(
            context.plan.solver_content_sha256
        ),
        previous_mesh_forest_sha256=previous.mesh_forest_sha256,
        next_mesh_forest_sha256=(
            context.current.forest_leaf_catalog_sha256
        ),
        previous_degree_map_sha256=previous.degree_map_sha256,
        next_degree_map_sha256=(
            context.current.cell_degree_plan_sha256
        ),
        before_solution_snapshot_sha256=(
            previous.solution_snapshot_sha256
        ),
        after_solution_snapshot_sha256=context.snapshot.payload_sha256,
        before_watchdog_record_file_sha256=(
            previous.watchdog_record_file_sha256
        ),
        after_watchdog_record_file_sha256=context.current.record_sha256,
    )
    return stability_repeat_verification_payload(verification)


def _transition_binding(
    *,
    context: _CycleContext,
    prior_trial_state_path: Path | None,
    verification_inputs: Sequence[VerificationPredictionInput],
    stability_repeat_action_path: Path | None,
) -> Mapping[str, Any]:
    cycle = context.current.cycle_index
    if cycle == 0:
        if (
            prior_trial_state_path is not None
            or verification_inputs
            or stability_repeat_action_path is not None
        ):
            raise BlindBindingError(
                "cycle zero cannot consume prior transition evidence"
            )
        return {
            "previous_trial_state_file_sha256": None,
            "previous_cycle_certificate_sha256": None,
            "executed_action_verifications": [],
            "stability_repeat_verification": None,
        }
    if prior_trial_state_path is None:
        raise BlindBindingError(
            "nonzero cycle requires a prior replayable trial state"
        )
    prior_path, _raw, prior_file_sha = _strict_json_object(
        prior_trial_state_path,
        label="prior blind trial state",
        private=True,
    )
    try:
        trial = blind_cycle.load_trial_state(prior_path, prior_file_sha)
    except (TypeError, ValueError) as exc:
        raise BlindBindingError(str(exc)) from exc
    expected_trial = {
        "trial_id": trial.trial_id,
        "algorithm_id": trial.algorithm_id,
        "initial_path_id": trial.initial_path_id,
        "initial_mesh_forest_sha256": trial.initial_mesh_forest_sha256,
        "physical_identity_sha256": trial.physical_identity_sha256,
        "maximum_cycles": trial.maximum_cycles,
    }
    if (
        expected_trial != dict(context.trial)
        or trial.source_sha != context.current.source_sha
        or len(trial.results) != cycle
    ):
        raise BlindBindingError(
            "prior trial state is not contiguous with current identity"
        )
    previous = trial.results[-1]
    expected = {
        row[0]: row[1:] for row in previous.selected_action_bindings
    }
    if expected and stability_repeat_action_path is not None:
        raise BlindBindingError(
            "selected action verification and stability repeat are mutually "
            "exclusive"
        )
    if not expected:
        if verification_inputs:
            raise BlindBindingError(
                "stability-repeat cycle cannot consume shadow verification"
            )
        repeat_required = (
            previous.accepted_current_state and not previous.freeze_ready
        )
        if repeat_required and stability_repeat_action_path is None:
            raise BlindBindingError(
                "accepted no-action cycle requires --stability-repeat-action"
            )
        if not repeat_required and stability_repeat_action_path is not None:
            raise BlindBindingError(
                "stability-repeat action is unexpected for this prior cycle"
            )
        repeat_payload = (
            None
            if stability_repeat_action_path is None
            else _stability_repeat_binding(
                context=context,
                previous=previous,
                transition_action_path=stability_repeat_action_path,
            )
        )
        return {
            "previous_trial_state_file_sha256": prior_file_sha,
            "previous_cycle_certificate_sha256": (
                previous.internal_certificate_sha256
            ),
            "executed_action_verifications": [],
            "stability_repeat_verification": repeat_payload,
        }
    supplied: dict[
        str,
        tuple[
            Mapping[str, Any],
            str,
            _MarkingBinding,
            _PredictionBinding,
        ],
    ] = {}
    for item in verification_inputs:
        action, action_file_sha = _load_transition_action(
            item.transition_action_path
        )
        marking = _load_goal_marking(item.goal_marking_path)
        _validate_action_against_marking(action, marking)
        prediction = _prediction_packet(item.prediction_path)
        action_id = str(action["action_id"])
        if (
            prediction.action_id != action_id
            or action_id in supplied
            or prediction.source_sha != action["source_sha"]
            or prediction.cycle_index != action["cycle_index"]
            or prediction.marking_cycle_index != marking.cycle_index
            or prediction.action_kind != action["kind"]
            or prediction.action_sha256 != action["action_sha256"]
            or prediction.action_identity_sha256
            != action["action_identity_sha256"]
            or prediction.marking_file_sha256
            != marking.file_sha256
            or prediction.marking_payload_sha256
            != marking.payload_sha256
            or prediction.predicted_deltas != marking.predicted_deltas
        ):
            raise BlindBindingError(
                "verification action/marking/prediction inventory is "
                "duplicated or mismatched"
            )
        supplied[action_id] = (
            action,
            action_file_sha,
            marking,
            prediction,
        )
    if set(supplied) != set(expected):
        raise BlindBindingError(
            "verification inventory differs from the prior selected action"
        )

    current_goals = blind_cycle.goal_vector_from_candidate_output(
        context.candidate
    )
    actual = tuple(
        (
            goal_id,
            current_goals.by_id[goal_id]
            - previous.goals.by_id[goal_id],
        )
        for goal_id in FORMAL_GOAL_IDS
    )
    rows = []
    for action_id in sorted(expected):
        (
            shadow_action_sha,
            predicted_sha,
            transition_sha,
            transition_file_sha,
            transition_identity_sha,
            next_mesh_sha,
            next_degree_sha,
        ) = expected[action_id]
        action, observed_file_sha, marking, prediction = supplied[
            action_id
        ]
        predicted = prediction.predicted_deltas
        verification = ShadowVerification(
            action_id=action_id,
            action_sha256=shadow_action_sha,
            transition_action_sha256=transition_sha,
            transition_action_file_sha256=observed_file_sha,
            transition_action_identity_sha256=transition_identity_sha,
            next_mesh_forest_sha256=context.current.forest_leaf_catalog_sha256,
            next_degree_map_sha256=context.current.cell_degree_plan_sha256,
            next_plan_file_sha256=context.plan.file_sha256,
            next_plan_content_sha256=context.plan.content_sha256,
            next_state_sha256=context.plan.state_sha256,
            before_output_sha256=previous.complete_output_sha256,
            after_output_sha256=context.candidate_payload_sha256,
            predicted_deltas=predicted,
            actual_deltas=actual,
        )
        provenance = context.plan.provenance
        if (
            predicted_sha != verification.predicted_delta_sha256
            or transition_file_sha != observed_file_sha
            or transition_sha != action["action_sha256"]
            or transition_identity_sha != action["action_identity_sha256"]
            or next_mesh_sha
            != context.current.forest_leaf_catalog_sha256
            or next_degree_sha != context.current.cell_degree_plan_sha256
            or action["source_sha"] != context.current.source_sha
            or action["cycle_index"] != cycle
            or action["expected_next_leaf_catalog_sha256"]
            != context.current.forest_leaf_catalog_sha256
            or action["expected_next_cell_degree_plan_sha256"]
            != context.current.cell_degree_plan_sha256
            or marking.payload["current_plan_file_sha256"]
            != previous.plan_file_sha256
            or marking.payload["current_plan_content_sha256"]
            != previous.plan_content_sha256
            or marking.payload["current_state_sha256"]
            != previous.state_sha256
            or marking.payload["current_leaf_catalog_sha256"]
            != previous.mesh_forest_sha256
            or marking.payload["current_degree_plan_sha256"]
            != previous.degree_map_sha256
            or provenance.get("schema_version")
            != PLAN_TRANSITION_SCHEMA
            or provenance.get("source_sha") != context.current.source_sha
            or provenance.get("cycle_index") != cycle
            or provenance.get("previous_plan_content_sha256")
            != previous.plan_content_sha256
            or provenance.get("from_state_sha256")
            != previous.state_sha256
            or provenance.get("transition_action_sha256")
            != action["action_sha256"]
            or provenance.get("transition_action_id")
            != action["action_id"]
            or provenance.get("transition_action_kind")
            != action["kind"]
            or provenance.get("transition_action_cycle_index")
            != action["cycle_index"]
            or provenance.get("transition_action_source_sha")
            != action["source_sha"]
            or provenance.get("transition_action_target_ids")
            != action["canonical_target_ids"]
            or provenance.get("next_state_sha256")
            != context.plan.state_sha256
            or provenance.get("from_leaf_catalog_sha256")
            != previous.mesh_forest_sha256
            or provenance.get("from_cell_degree_plan_sha256")
            != previous.degree_map_sha256
            or provenance.get("next_leaf_catalog_sha256")
            != context.current.forest_leaf_catalog_sha256
            or provenance.get("next_cell_degree_plan_sha256")
            != context.current.cell_degree_plan_sha256
        ):
            raise BlindBindingError(
                "verification transition/prediction/next-plan identity differs"
            )
        rows.append(
            {
                "action_id": verification.action_id,
                "action_sha256": verification.action_sha256,
                "transition_action_sha256": (
                    verification.transition_action_sha256
                ),
                "transition_action_file_sha256": (
                    verification.transition_action_file_sha256
                ),
                "transition_action_identity_sha256": (
                    verification.transition_action_identity_sha256
                ),
                "next_mesh_forest_sha256": (
                    verification.next_mesh_forest_sha256
                ),
                "next_degree_map_sha256": (
                    verification.next_degree_map_sha256
                ),
                "next_plan_file_sha256": (
                    verification.next_plan_file_sha256
                ),
                "next_plan_content_sha256": (
                    verification.next_plan_content_sha256
                ),
                "next_state_sha256": verification.next_state_sha256,
                "before_output_sha256": (
                    verification.before_output_sha256
                ),
                "after_output_sha256": (
                    verification.after_output_sha256
                ),
                "predicted_deltas": dict(verification.predicted_deltas),
                "actual_deltas": dict(verification.actual_deltas),
            }
        )
    return {
        "previous_trial_state_file_sha256": prior_file_sha,
        "previous_cycle_certificate_sha256": (
            previous.internal_certificate_sha256
        ),
        "executed_action_verifications": rows,
        "stability_repeat_verification": None,
    }


def write_cycle_binding(
    output_path: Path,
    *,
    trial_metadata_path: Path,
    current_record_path: Path,
    candidate_output_path: Path,
    current_snapshot_path: Path,
    shadow_bundle_path: Path,
    internal_gates_path: Path,
    isolation_report_path: Path,
    prior_trial_state_path: Path | None = None,
    verification_inputs: Sequence[VerificationPredictionInput] = (),
    stability_repeat_action_path: Path | None = None,
) -> BindingWriteReceipt:
    """Publish the exact self-hashed binding consumed by ``blind_cycle``."""

    context = _cycle_context(
        trial_metadata_path=trial_metadata_path,
        current_record_path=current_record_path,
        candidate_output_path=candidate_output_path,
        current_snapshot_path=current_snapshot_path,
        shadow_bundle_path=shadow_bundle_path,
    )
    manifest = _manifest_payload(context)
    manifest_sha = cycle_manifest_sha256(manifest)
    isolation_file_sha = _load_isolation_report(
        isolation_report_path,
        context=context,
        manifest_sha256=manifest_sha,
    )
    gates = _internal_gates(internal_gates_path, context=context)
    transition = _transition_binding(
        context=context,
        prior_trial_state_path=prior_trial_state_path,
        verification_inputs=verification_inputs,
        stability_repeat_action_path=stability_repeat_action_path,
    )
    payload: dict[str, Any] = {
        "schema_version": blind_cycle.CYCLE_BINDING_SCHEMA,
        "trial": dict(context.trial),
        "source_sha": context.current.source_sha,
        "mpi_size": 8,
        "cycle_index": context.current.cycle_index,
        "mesh_forest_sha256": (
            context.current.forest_leaf_catalog_sha256
        ),
        "degree_map_sha256": context.current.cell_degree_plan_sha256,
        "plan_file_sha256": context.plan.file_sha256,
        "plan_content_sha256": context.plan.content_sha256,
        "plan_solver_content_sha256": (
            context.plan.solver_content_sha256
        ),
        "state_sha256": context.plan.state_sha256,
        "solution_snapshot_sha256": context.snapshot.payload_sha256,
        "complete_output_sha256": context.candidate_payload_sha256,
        "full_residual_sha256": context.snapshot.residual_sha256,
        "candidate_record_file_sha256": context.current.record_sha256,
        "candidate_output_file_sha256": (
            context.candidate_file_sha256
        ),
        "current_snapshot_file_sha256": context.snapshot.file_sha256,
        "shadow_bundle_file_sha256": context.shadow_file_sha256,
        "reference_isolation_report_file_sha256": isolation_file_sha,
        "resource_inventory": dict(context.inventory),
        "resource_inventory_sha256": (
            context.resource_inventory_sha256
        ),
        "internal_gates": dict(gates),
        "transition": dict(transition),
    }
    payload_sha = _json_sha256(payload)
    outer = {
        "schema_version": blind_cycle.CYCLE_BINDING_SCHEMA,
        "sha256": payload_sha,
        "payload": payload,
    }

    def validate(path: Path, file_sha: str) -> None:
        try:
            loaded, observed_payload_sha, observed_file_sha = (
                blind_cycle._load_cycle_binding(path, file_sha)
            )
        except (TypeError, ValueError) as exc:
            raise BlindBindingError(str(exc)) from exc
        if (
            dict(loaded) != payload
            or observed_payload_sha != payload_sha
            or observed_file_sha != file_sha
        ):
            raise BlindBindingError(
                "published cycle binding does not replay exactly"
            )

    destination, file_sha = _atomic_private_json(
        output_path,
        outer,
        validator=validate,
    )
    return BindingWriteReceipt(
        kind="cycle_binding",
        path=destination,
        file_sha256=file_sha,
        payload_sha256=payload_sha,
        source_sha=context.current.source_sha,
        trial_id=context.current.trial_id,
        cycle_index=context.current.cycle_index,
    )


def _shadow_inputs(
    values: Sequence[Sequence[str]] | None,
) -> tuple[ShadowEndpointInput, ...]:
    return tuple(
        ShadowEndpointInput(
            transition_action_path=Path(row[0]),
            goal_marking_path=Path(row[1]),
            verification_prediction_path=Path(row[2]),
            shadow_record_path=Path(row[3]),
            dwr_evidence_path=Path(row[4]),
        )
        for row in (values or ())
    )


def _verification_inputs(
    values: Sequence[Sequence[str]] | None,
) -> tuple[VerificationPredictionInput, ...]:
    return tuple(
        VerificationPredictionInput(
            transition_action_path=Path(row[0]),
            goal_marking_path=Path(row[1]),
            prediction_path=Path(row[2]),
        )
        for row in (values or ())
    )


def _add_cycle_context_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--trial-metadata", type=Path, required=True)
    parser.add_argument("--current-record", type=Path, required=True)
    parser.add_argument("--candidate-output", type=Path, required=True)
    parser.add_argument("--current-snapshot", type=Path, required=True)
    parser.add_argument("--shadow-bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    shadow = commands.add_parser("shadow-request")
    shadow.add_argument("--current-record", type=Path, required=True)
    shadow.add_argument(
        "--p-action",
        nargs=5,
        action="append",
        metavar=(
            "TRANSITION",
            "GOAL_MARKING",
            "VERIFICATION_PREDICTION",
            "SHADOW_RECORD",
            "DWR_EVIDENCE",
        ),
        required=True,
    )
    shadow.add_argument(
        "--h-action",
        nargs=5,
        action="append",
        metavar=(
            "TRANSITION",
            "GOAL_MARKING",
            "VERIFICATION_PREDICTION",
            "SHADOW_RECORD",
            "DWR_EVIDENCE",
        ),
        required=True,
    )
    shadow.add_argument("--output", type=Path, required=True)

    manifest = commands.add_parser("blind-manifest")
    _add_cycle_context_arguments(manifest)

    prediction = commands.add_parser("verification-prediction")
    prediction.add_argument("--goal-marking", type=Path, required=True)
    prediction.add_argument(
        "--transition-action",
        type=Path,
        required=True,
    )
    prediction.add_argument("--output", type=Path, required=True)

    binding = commands.add_parser("cycle-binding")
    _add_cycle_context_arguments(binding)
    binding.add_argument("--internal-gates", type=Path, required=True)
    binding.add_argument("--isolation-report", type=Path, required=True)
    binding.add_argument("--prior-trial-state", type=Path)
    transition_group = binding.add_mutually_exclusive_group()
    transition_group.add_argument(
        "--verification",
        nargs=3,
        action="append",
        metavar=("TRANSITION", "GOAL_MARKING", "PREDICTION"),
    )
    transition_group.add_argument(
        "--stability-repeat-action",
        type=Path,
    )
    return parser


def _receipt_json(
    receipt: BindingWriteReceipt | VerificationPredictionWriteReceipt,
) -> dict[str, Any]:
    payload = {
        "schema_version": BINDING_RECEIPT_SCHEMA,
        "status": "completed",
        "kind": receipt.kind,
        "path": str(receipt.path),
        "file_sha256": receipt.file_sha256,
        "payload_sha256": receipt.payload_sha256,
        "source_sha": receipt.source_sha,
        "cycle_index": receipt.cycle_index,
    }
    if isinstance(receipt, VerificationPredictionWriteReceipt):
        payload["action_id"] = receipt.action_id
    else:
        payload["trial_id"] = receipt.trial_id
    return payload


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "shadow-request":
            receipt = write_shadow_request(
                args.output,
                current_record_path=args.current_record,
                p_actions=_shadow_inputs(args.p_action),
                h_actions=_shadow_inputs(args.h_action),
            )
        elif args.command == "blind-manifest":
            receipt = write_blind_input_manifest(
                args.output,
                trial_metadata_path=args.trial_metadata,
                current_record_path=args.current_record,
                candidate_output_path=args.candidate_output,
                current_snapshot_path=args.current_snapshot,
                shadow_bundle_path=args.shadow_bundle,
            )
        elif args.command == "verification-prediction":
            receipt = write_verification_prediction(
                args.output,
                goal_marking_path=args.goal_marking,
                transition_action_path=args.transition_action,
            )
        else:
            receipt = write_cycle_binding(
                args.output,
                trial_metadata_path=args.trial_metadata,
                current_record_path=args.current_record,
                candidate_output_path=args.candidate_output,
                current_snapshot_path=args.current_snapshot,
                shadow_bundle_path=args.shadow_bundle,
                internal_gates_path=args.internal_gates,
                isolation_report_path=args.isolation_report,
                prior_trial_state_path=args.prior_trial_state,
                verification_inputs=_verification_inputs(
                    args.verification
                ),
                stability_repeat_action_path=(
                    args.stability_repeat_action
                ),
            )
    except (
        BlindBindingError,
        CandidateOutputError,
        ShadowBundleError,
        FileExistsError,
        OSError,
    ) as exc:
        print(
            json.dumps(
                {
                    "schema_version": BINDING_RECEIPT_SCHEMA,
                    "status": "failed",
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        return 2
    print(json.dumps(_receipt_json(receipt), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "BINDING_RECEIPT_SCHEMA",
    "TRIAL_METADATA_SCHEMA",
    "VERIFICATION_PREDICTION_SCHEMA",
    "BindingWriteReceipt",
    "BlindBindingError",
    "ShadowEndpointInput",
    "VerificationPredictionInput",
    "VerificationPredictionWriteReceipt",
    "main",
    "write_blind_input_manifest",
    "write_cycle_binding",
    "write_shadow_request",
    "write_verification_prediction",
]
