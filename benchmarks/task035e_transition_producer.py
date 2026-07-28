#!/usr/bin/env python3
"""Publish one immutable reference-blind Task035e h/p transition bundle.

The producer is deliberately narrower than the blind marker/controller.  It
accepts an already selected action kind and canonical dyadic leaf IDs, replays
the current solver plan into its exact h/p state, and writes:

* the canonical transition action consumed by the formal watchdog; and
* the deterministic next Stage-4 solver plan.

No solution, goal, DWR, error-map, evaluator, or hidden-reference artifact is
an input to this module.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
from typing import Any, Mapping, Sequence

from src.adaptivity.task035e_hp_transition import (
    HP_TRANSITION_ACTION_SCHEMA,
    canonical_hp_cell_target_id,
    hp_transition_action_payload,
)
from src.adaptivity.task035e_initial_space import (
    build_task035e_initial_space_plan,
)
from src.adaptivity.task035e_plan_transition import (
    PLAN_TRANSITION_SCHEMA,
    build_next_solver_plan,
    rebuild_hp_transition_state_from_solver_plan,
)
from src.common.config_3d import target_stage4_config


TRANSITION_WRITE_RECEIPT_SCHEMA = (
    "task035e.blind-transition-write-receipt.v1"
)
_SOURCE_SHA_RE = re.compile(r"[0-9a-f]{40}")
_ACTION_KINDS = frozenset({"p-up", "p-down", "p-keep", "h-refine"})
_FORMAL_H_TO_PATH = {20.0: "A", 15.0: "B"}
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
_FALSE_BLIND_FLAGS = frozenset(
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
_FORBIDDEN_PATH_PARTS = frozenset(
    {
        "reference_certifier",
        "hidden_auditor",
        "sealed_reference",
        "sealed-reference",
    }
)


class TransitionProducerError(ValueError):
    """Raised when a transition bundle cannot be produced fail-closed."""


@dataclass(frozen=True, slots=True)
class TransitionWriteReceipt:
    """File and content identities for one immutable transition bundle."""

    source_sha: str
    cycle_index: int
    action_id: str
    action_kind: str
    canonical_target_ids: tuple[str, ...]
    from_state_sha256: str
    next_state_sha256: str
    action_path: Path
    action_file_sha256: str
    action_sha256: str
    plan_path: Path
    plan_file_sha256: str
    plan_content_sha256: str


def _reject_nonfinite(value: str) -> None:
    raise TransitionProducerError(
        f"non-finite JSON constant is forbidden: {value}"
    )


def _reject_duplicate_object(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise TransitionProducerError(
                f"duplicate JSON object key is forbidden: {key}"
            )
        result[key] = value
    return result


def _strict_json_object(path: Path) -> Mapping[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_reject_duplicate_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise TransitionProducerError(
            f"cannot read strict current-plan JSON: {path}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise TransitionProducerError(
            "current solver plan must be one JSON object"
        )
    return payload


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


def _canonical_file_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(
            payload,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _source_sha(value: str) -> str:
    if _SOURCE_SHA_RE.fullmatch(str(value)) is None:
        raise TransitionProducerError(
            "source_sha must be one 40-character lowercase Git SHA"
        )
    return str(value)


def _sha256(value: str, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise TransitionProducerError(f"{label} must be a lowercase SHA-256")
    return value


def _safe_path(path: Path, *, label: str) -> Path:
    resolved = path.resolve()
    lowered = {part.lower() for part in resolved.parts}
    if lowered.intersection(_FORBIDDEN_PATH_PARTS):
        raise TransitionProducerError(
            f"{label} crosses a forbidden reference/evaluator layer"
        )
    return resolved


def _require_private_regular_file(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise TransitionProducerError(f"{label} must not be a symlink")
    resolved = _safe_path(path, label=label)
    try:
        metadata = resolved.stat()
    except OSError as exc:
        raise TransitionProducerError(f"{label} is not readable: {resolved}") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise TransitionProducerError(f"{label} is not a regular file")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise TransitionProducerError(f"{label} must use mode 0600")
    return resolved


def _assert_closed_blind_plan(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    if set(payload) != _CURRENT_PLAN_FIELDS:
        raise TransitionProducerError(
            "current solver plan does not use the closed Task035e schema"
        )
    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise TransitionProducerError(
            "current solver plan has no provenance object"
        )
    schema = provenance.get("schema_version")
    if schema == "task035e.blind-initial-provenance.v1":
        expected_fields = _INITIAL_PROVENANCE_FIELDS
    elif schema == PLAN_TRANSITION_SCHEMA:
        expected_fields = _TRANSITION_PROVENANCE_FIELDS
    else:
        raise TransitionProducerError(
            "current solver plan provenance is not a blind transition schema"
        )
    if set(provenance) != expected_fields:
        raise TransitionProducerError(
            "current solver plan provenance contains unknown or missing data"
        )
    for name in _FALSE_BLIND_FLAGS.intersection(provenance):
        if provenance[name] is not False:
            raise TransitionProducerError(
                f"current solver plan violates blind flag {name}=false"
            )
    if payload.get("ordinary_default_changed") is not False:
        raise TransitionProducerError(
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
        raise TransitionProducerError("current plan has no base_config object")
    raw_h = base_config.get("mesh_target_size")
    if isinstance(raw_h, bool) or not isinstance(raw_h, (int, float)):
        raise TransitionProducerError(
            "current plan mesh_target_size is not numeric"
        )
    h_nm = float(raw_h)
    path_id = next(
        (
            candidate
            for expected_h, candidate in _FORMAL_H_TO_PATH.items()
            if abs(h_nm - expected_h) <= 1.0e-12
        ),
        None,
    )
    if path_id is None:
        raise TransitionProducerError(
            "current plan is not a formal Task035e Path A/B base mesh"
        )
    cfg = target_stage4_config(degree=6, h_nm=h_nm)
    canonical_initial = build_task035e_initial_space_plan(
        cfg,
        path_id=path_id,
        source_sha=source_sha,
        comm_size=8,
    ).plan_payload()
    if base_config != canonical_initial["base_config"]:
        raise TransitionProducerError(
            "current plan base_config differs from the deterministic "
            f"Task035e Path {path_id} authority"
        )
    return cfg, path_id, canonical_initial


def _canonical_targets(
    state: Any,
    raw_target_ids: Sequence[str],
    *,
    allow_empty: bool = False,
) -> tuple[tuple[Any, ...], tuple[str, ...]]:
    if isinstance(raw_target_ids, (str, bytes)) or not isinstance(
        raw_target_ids,
        Sequence,
    ):
        raise TransitionProducerError(
            "canonical_target_ids must be a sequence"
        )
    supplied = tuple(raw_target_ids)
    if not supplied:
        if allow_empty:
            return (), ()
        raise TransitionProducerError(
            "at least one canonical target ID is required"
        )
    if allow_empty:
        raise TransitionProducerError(
            "p-keep must not contain canonical target IDs"
        )
    if any(not isinstance(value, str) for value in supplied):
        raise TransitionProducerError(
            "every canonical target ID must be a string"
        )
    key_by_id = {
        canonical_hp_cell_target_id(cell.key): cell.key
        for cell in state.forest.leaves
    }
    unknown = tuple(value for value in supplied if value not in key_by_id)
    if unknown:
        raise TransitionProducerError(
            f"transition targets non-current leaves: {unknown[:2]}"
        )
    keys = tuple(key_by_id[value] for value in supplied)
    canonical_keys = tuple(sorted(set(keys)))
    canonical_ids = tuple(
        canonical_hp_cell_target_id(key) for key in canonical_keys
    )
    if supplied != canonical_ids:
        raise TransitionProducerError(
            "canonical target IDs are duplicated or not in canonical order"
        )
    return canonical_keys, canonical_ids


def _deterministic_action_id(
    *,
    source_sha: str,
    cycle_index: int,
    kind: str,
    canonical_target_ids: Sequence[str],
) -> str:
    selector = {
        "schema_version": "task035e.blind-transition-selector.v1",
        "source_sha": source_sha,
        "cycle_index": int(cycle_index),
        "kind": kind,
        "canonical_target_ids": list(canonical_target_ids),
    }
    digest = _canonical_compact_sha256(selector)
    return f"cycle{cycle_index}.{kind}.{digest[:16]}"


def _atomic_mode_0600(path: Path, payload: bytes) -> str:
    if os.path.lexists(path):
        raise FileExistsError(f"refusing to overwrite immutable output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        temporary.unlink()
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_descriptor)
        finally:
            os.close(directory_descriptor)
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise
    return _sha256_bytes(payload)


def write_transition_bundle(
    *,
    current_plan_path: Path,
    current_plan_file_sha256: str,
    source_sha: str,
    action_kind: str,
    canonical_target_ids: Sequence[str],
    action_path: Path,
    next_plan_path: Path,
) -> TransitionWriteReceipt:
    """Replay and atomically publish one immutable h/p transition bundle."""

    source = _source_sha(source_sha)
    expected_current_file_sha = _sha256(
        current_plan_file_sha256,
        label="current plan file SHA-256",
    )
    kind = str(action_kind)
    if kind not in _ACTION_KINDS:
        raise TransitionProducerError(
            "action_kind must be p-up, p-down, p-keep, or h-refine"
        )
    current_path = _require_private_regular_file(
        current_plan_path,
        label="current plan",
    )
    if os.path.lexists(action_path) or os.path.lexists(next_plan_path):
        raise FileExistsError(
            "refusing to overwrite an immutable transition output"
        )
    action_output = _safe_path(action_path, label="action output")
    plan_output = _safe_path(next_plan_path, label="next-plan output")
    if len({current_path, action_output, plan_output}) != 3:
        raise TransitionProducerError(
            "current plan, action, and next plan paths must differ"
        )
    if os.path.lexists(action_output) or os.path.lexists(plan_output):
        raise FileExistsError(
            "refusing to overwrite an immutable transition output"
        )
    observed_current_file_sha = _file_sha256(current_path)
    if observed_current_file_sha != expected_current_file_sha:
        raise TransitionProducerError("current plan file SHA-256 mismatch")
    current_plan = _strict_json_object(current_path)
    provenance = _assert_closed_blind_plan(current_plan)
    if provenance.get("source_sha") != source:
        raise TransitionProducerError(
            "verified source SHA differs from current-plan provenance"
        )
    cfg, _path_id, canonical_initial = _config_from_plan(
        current_plan,
        source_sha=source,
    )
    if (
        provenance.get("schema_version")
        == "task035e.blind-initial-provenance.v1"
        and current_plan != canonical_initial
    ):
        raise TransitionProducerError(
            "initial current plan differs from its deterministic authority"
        )
    state = rebuild_hp_transition_state_from_solver_plan(
        cfg,
        current_plan=current_plan,
        comm_size=8,
    )
    if state.source_sha != source:
        raise TransitionProducerError(
            "rebuilt state differs from the verified source SHA"
        )
    targets, canonical_ids = _canonical_targets(
        state,
        canonical_target_ids,
        allow_empty=kind == "p-keep",
    )
    if kind == "p-down" and state.cycle_index < 2:
        raise TransitionProducerError(
            "Task035e forbids p-down during the first two blind cycles"
        )
    next_cycle = state.cycle_index + 1
    action_id = _deterministic_action_id(
        source_sha=source,
        cycle_index=next_cycle,
        kind=kind,
        canonical_target_ids=canonical_ids,
    )
    action = hp_transition_action_payload(
        state,
        action_id=action_id,
        kind=kind,
        degree_deltas=(
            {}
            if kind in {"h-refine", "p-keep"}
            else {
                key: 1 if kind == "p-up" else -1
                for key in targets
            }
        ),
        requested_split_keys=targets if kind == "h-refine" else (),
        maximum_level=2 if kind == "h-refine" else None,
    )
    if (
        action.get("schema_version") != HP_TRANSITION_ACTION_SCHEMA
        or tuple(action.get("canonical_target_ids", ())) != canonical_ids
        or action.get("source_sha") != source
        or action.get("from_state_sha256") != state.state_sha256
    ):
        raise RuntimeError("canonical transition action identity drifted")
    transition = build_next_solver_plan(
        cfg,
        current_plan=current_plan,
        state=state,
        action=action,
        comm_size=8,
    )
    next_plan = dict(transition.plan_payload)
    replayed_next = rebuild_hp_transition_state_from_solver_plan(
        cfg,
        current_plan=next_plan,
        comm_size=8,
    )
    if (
        replayed_next.state_sha256 != transition.next_state.state_sha256
        or replayed_next.stage_action_sha256s
        != transition.next_state.stage_action_sha256s
        or transition.audit.get("action_sha256") != action["action_sha256"]
    ):
        raise RuntimeError("next solver plan does not replay its action")
    action_bytes = _canonical_file_bytes(action)
    plan_bytes = _canonical_file_bytes(next_plan)
    plan_content_sha = _canonical_compact_sha256(next_plan)
    if plan_content_sha != transition.audit["next_plan_content_sha256"]:
        raise RuntimeError("next solver-plan content SHA-256 drifted")
    action_file_sha = _atomic_mode_0600(action_output, action_bytes)
    try:
        plan_file_sha = _atomic_mode_0600(plan_output, plan_bytes)
    except BaseException:
        # The already-published action is immutable evidence.  Keep it rather
        # than deleting evidence after a partial publication; a retry must use
        # a fresh pair of destinations.
        raise
    return TransitionWriteReceipt(
        source_sha=source,
        cycle_index=next_cycle,
        action_id=action_id,
        action_kind=kind,
        canonical_target_ids=canonical_ids,
        from_state_sha256=state.state_sha256,
        next_state_sha256=transition.next_state.state_sha256,
        action_path=action_output,
        action_file_sha256=action_file_sha,
        action_sha256=str(action["action_sha256"]),
        plan_path=plan_output,
        plan_file_sha256=plan_file_sha,
        plan_content_sha256=plan_content_sha,
    )


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-plan", type=Path, required=True)
    parser.add_argument("--current-plan-sha256", required=True)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument(
        "--action-kind",
        choices=tuple(sorted(_ACTION_KINDS)),
        required=True,
    )
    parser.add_argument(
        "--target-id",
        action="append",
        dest="canonical_target_ids",
        help="canonical current-leaf ID; repeat in canonical key order",
    )
    parser.add_argument("--action", type=Path, required=True)
    parser.add_argument("--next-plan", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        receipt = write_transition_bundle(
            current_plan_path=args.current_plan,
            current_plan_file_sha256=args.current_plan_sha256,
            source_sha=args.verified_clean_sha,
            action_kind=args.action_kind,
            canonical_target_ids=args.canonical_target_ids or (),
            action_path=args.action,
            next_plan_path=args.next_plan,
        )
    except (
        FileExistsError,
        OSError,
        RuntimeError,
        TransitionProducerError,
        ValueError,
    ) as error:
        print(
            json.dumps(
                {
                    "schema_version": TRANSITION_WRITE_RECEIPT_SCHEMA,
                    "status": "failed",
                    "error": str(error),
                },
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "schema_version": TRANSITION_WRITE_RECEIPT_SCHEMA,
                "status": "completed",
                "source_sha": receipt.source_sha,
                "cycle_index": receipt.cycle_index,
                "action_id": receipt.action_id,
                "action_kind": receipt.action_kind,
                "canonical_target_ids": list(
                    receipt.canonical_target_ids
                ),
                "from_state_sha256": receipt.from_state_sha256,
                "next_state_sha256": receipt.next_state_sha256,
                "action_path": str(receipt.action_path),
                "action_file_sha256": receipt.action_file_sha256,
                "action_sha256": receipt.action_sha256,
                "next_plan_path": str(receipt.plan_path),
                "next_plan_file_sha256": receipt.plan_file_sha256,
                "next_plan_content_sha256": receipt.plan_content_sha256,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "TRANSITION_WRITE_RECEIPT_SCHEMA",
    "TransitionProducerError",
    "TransitionWriteReceipt",
    "write_transition_bundle",
]
