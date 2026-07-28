"""Replay one blind h/p action into a solver-ready Task035e plan.

This bridge contains no marking logic and consumes no goal values.  It turns
an already selected, hash-bound :mod:`task035e_hp_transition` action into the
next canonical Stage-4 multilevel local-h/variable-p plan.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .dyadic_hexa_refinement import DyadicHexKey
from .stage4_local_h import (
    stage4_multilevel_local_h_forest_catalog,
    stage4_multilevel_local_h_refinement_plan_payload,
)
from .task035e_hp_transition import (
    HPTransitionState,
    close_hp_transition,
    rebuild_hp_transition_state,
)


PLAN_TRANSITION_SCHEMA = "task035e.blind-solver-plan-transition.v2"


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _canonical_plan_sha256(payload: Mapping[str, Any]) -> str:
    return _json_sha256(dict(payload))


def canonical_solver_content_sha256(
    payload: Mapping[str, Any],
) -> str:
    """Hash numerical solver inputs while excluding transition provenance.

    A ``p-keep`` transition advances the immutable action/provenance chain but
    must preserve this identity exactly.  The public helper gives the
    watchdog and binding producers one canonical definition of that boundary.
    """

    if not isinstance(payload, Mapping):
        raise ValueError("solver plan must be a mapping")
    solver_content = dict(payload)
    solver_content.pop("provenance", None)
    return _json_sha256(solver_content)


def _box(
    lower: Sequence[Any],
    upper: Sequence[Any],
    *,
    label: str,
) -> tuple[float, float, float, float, float, float]:
    if len(lower) != 3 or len(upper) != 3:
        raise ValueError(f"{label} must contain two 3D corners")
    result = tuple(round(float(value), 12) for value in (*lower, *upper))
    if any(result[axis] >= result[axis + 3] for axis in range(3)):
        raise ValueError(f"{label} is degenerate")
    return result


def _stages(
    plan: Mapping[str, Any],
) -> tuple[tuple[tuple[float, ...], ...], ...]:
    rows = plan.get("refinement_stages")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 6:
        raise ValueError("current plan must contain one to six h stages")
    result = []
    for stage_index, stage in enumerate(rows):
        if not isinstance(stage, Mapping):
            raise ValueError(f"refinement stage {stage_index} is malformed")
        marks = stage.get("marked_leaves")
        if not isinstance(marks, list) or not marks:
            raise ValueError(f"refinement stage {stage_index} has no marks")
        result.append(
            tuple(
                _box(
                    row["lower"],
                    row["upper"],
                    label=f"stage {stage_index} mark",
                )
                for row in marks
            )
        )
    return tuple(result)


def _degree_by_box(
    plan: Mapping[str, Any],
) -> dict[tuple[float, ...], int]:
    rows = plan.get("cell_interior_degrees")
    if not isinstance(rows, list) or not rows:
        raise ValueError("current plan has no complete cell-degree map")
    result: dict[tuple[float, ...], int] = {}
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise ValueError(f"cell-degree row {index} is malformed")
        box = _box(
            row["lower"],
            row["upper"],
            label=f"cell-degree row {index}",
        )
        degree = row.get("degree")
        if type(degree) is not int or degree not in {4, 5, 6}:
            raise ValueError("cell-degree map left p4/p5/p6")
        if box in result:
            raise ValueError("cell-degree map contains a duplicate leaf")
        result[box] = degree
    return result


def _dyadic_key(row: Any, *, label: str) -> DyadicHexKey:
    if not isinstance(row, Mapping) or set(row) != {
        "root",
        "level",
        "i",
        "j",
        "k",
    }:
        raise ValueError(f"{label} is not a canonical dyadic key")
    if any(type(row[name]) is not int for name in row):
        raise ValueError(f"{label} contains a non-integral coordinate")
    return DyadicHexKey(
        row["root"],
        row["level"],
        row["i"],
        row["j"],
        row["k"],
    )


def _state_degree_by_box(
    state: HPTransitionState,
) -> dict[tuple[float, ...], int]:
    return {
        tuple(round(float(value), 12) for value in cell.box): int(
            state.cell_degree_by_key[cell.key]
        )
        for cell in state.forest.leaves
    }


def _plan_forest_and_degrees(
    config: Any,
    current_plan: Mapping[str, Any],
    *,
    comm_size: int,
) -> tuple[
    tuple[tuple[tuple[float, ...], ...], ...],
    Any,
    dict[DyadicHexKey, int],
]:
    if current_plan.get("schema_version") != (
        "task035e.stage4-multilevel-local-h-refinement-plan.v1"
    ):
        raise ValueError("current plan is not a Task035e multilevel plan")
    if current_plan.get("variable_trace_from_cell_degrees") is not True:
        raise ValueError("current plan is not cell-driven variable trace")
    if (
        current_plan.get("trace_degree") != 4
        or current_plan.get("cell_interior_degree") != 6
    ):
        raise ValueError("current plan lost its p4 trace/p6 container contract")
    stages = _stages(current_plan)
    forest = stage4_multilevel_local_h_forest_catalog(
        config,
        stages,
        comm_size=comm_size,
    )
    degree_by_box = _degree_by_box(current_plan)
    leaf_by_box = {
        tuple(round(float(value), 12) for value in cell.box): cell.key
        for cell in forest.leaves
    }
    if set(degree_by_box) != set(leaf_by_box):
        raise ValueError(
            "current plan degree map does not cover its rebuilt forest"
        )
    degree_by_key = {
        leaf_by_box[box]: degree_by_box[box] for box in sorted(degree_by_box)
    }
    return stages, forest, degree_by_key


def _closed_provenance(
    plan: Mapping[str, Any],
) -> tuple[Mapping[str, Any], str]:
    provenance = plan.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("current plan has no transition provenance")
    payload = dict(provenance)
    schema = payload.get("schema_version")
    if schema == "task035e.blind-initial-provenance.v1":
        if payload.get("status") != "blind_initial_provenance_closed":
            raise ValueError("initial solver-plan provenance is not closed")
        digest_field = "provenance_sha256"
    elif schema == PLAN_TRANSITION_SCHEMA:
        if payload.get("status") != "blind_solver_plan_transition_closed":
            raise ValueError("transition solver-plan provenance is not closed")
        digest_field = "transition_provenance_sha256"
    else:
        raise ValueError("current plan provenance schema is not replayable")
    observed = payload.pop(digest_field, None)
    if (
        not isinstance(observed, str)
        or len(observed) != 64
        or observed != _json_sha256(payload)
    ):
        raise ValueError("current solver-plan provenance SHA-256 is invalid")
    return provenance, str(schema)


def rebuild_hp_transition_state_from_solver_plan(
    config: Any,
    *,
    current_plan: Mapping[str, Any],
    comm_size: int = 8,
) -> HPTransitionState:
    """Rebuild the current state solely from one closed solver plan.

    The plan is replayed into its dyadic forest and complete p4/p5/p6 map.
    Initial plans must bind the empty action chain; later plans must carry the
    complete ordered chain, its prefix hash, and the resulting state hash.
    Every persisted identity is checked before the live state is returned.
    """

    if int(comm_size) != 8:
        raise ValueError("formal Task035e state replay requires MPI8")
    _stages_value, forest, degree_by_key = _plan_forest_and_degrees(
        config,
        current_plan,
        comm_size=8,
    )
    provenance, schema = _closed_provenance(current_plan)
    source_sha = provenance.get("source_sha")
    algorithm_sha256 = provenance.get("algorithm_sha256")
    action_chain = provenance.get("stage_action_sha256s")
    if not isinstance(action_chain, list):
        raise ValueError(
            "solver-plan provenance has no complete stage action chain"
        )
    if schema == "task035e.blind-initial-provenance.v1":
        if action_chain:
            raise ValueError("initial solver plan has a nonempty action chain")
        cycle_index = 0
        expected_state_sha256 = provenance.get("initial_state_sha256")
        expected_stage_prefix_sha256 = provenance.get(
            "stage_prefix_sha256"
        )
    else:
        cycle_index = provenance.get("cycle_index")
        if type(cycle_index) is not int or not 1 <= cycle_index <= 5:
            raise ValueError("transition plan cycle index is invalid")
        if len(action_chain) != cycle_index:
            raise ValueError(
                "transition plan action chain length differs from cycle"
            )
        if (
            not action_chain
            or action_chain[-1]
            != provenance.get("transition_action_sha256")
            or provenance.get("transition_action_cycle_index")
            != cycle_index
        ):
            raise ValueError(
                "transition plan action chain does not end at its action"
            )
        expected_state_sha256 = provenance.get("next_state_sha256")
        expected_stage_prefix_sha256 = provenance.get(
            "next_stage_prefix_sha256"
        )
        if provenance.get("transition_action_source_sha") != source_sha:
            raise ValueError("transition plan action/source binding drifted")
        if (
            provenance.get(
                "next_plan_canonical_solver_content_sha256"
            )
            != canonical_solver_content_sha256(current_plan)
        ):
            raise ValueError(
                "transition plan canonical solver-content binding drifted"
            )
    state = rebuild_hp_transition_state(
        forest,
        degree_by_key,
        source_sha=source_sha,
        algorithm_sha256=algorithm_sha256,
        cycle_index=cycle_index,
        stage_action_sha256s=action_chain,
        expected_state_sha256=expected_state_sha256,
        expected_stage_prefix_sha256=expected_stage_prefix_sha256,
    )
    expected_forest = current_plan.get("expected_forest")
    if (
        not isinstance(expected_forest, Mapping)
        or expected_forest.get("leaf_catalog_sha256")
        != state.audit["leaf_catalog_sha256"]
    ):
        raise ValueError(
            "current plan leaf-catalog authority differs from rebuilt state"
        )
    if (
        current_plan.get("cell_interior_degree_plan_sha256")
        != state.audit["cell_degree_plan_sha256"]
    ):
        raise ValueError(
            "current plan cell-degree authority differs from rebuilt state"
        )
    return state


def _validate_current_plan(
    config: Any,
    current_plan: Mapping[str, Any],
    state: HPTransitionState,
    *,
    comm_size: int,
) -> tuple[tuple[tuple[float, ...], ...], ...]:
    stages, rebuilt_forest, _degree_by_key_value = (
        _plan_forest_and_degrees(
            config,
            current_plan,
            comm_size=comm_size,
        )
    )
    for name in ("leaf_catalog_sha256", "hanging_face_catalog_sha256"):
        if rebuilt_forest.audit[name] != state.forest.audit[name]:
            raise ValueError(f"current plan and hp state differ at {name}")
    if _degree_by_box(current_plan) != _state_degree_by_box(state):
        raise ValueError("current plan and hp state degree maps differ")
    rebuilt_state = rebuild_hp_transition_state_from_solver_plan(
        config,
        current_plan=current_plan,
        comm_size=comm_size,
    )
    if (
        rebuilt_state.state_sha256 != state.state_sha256
        or rebuilt_state.stage_action_sha256s
        != state.stage_action_sha256s
    ):
        raise ValueError("current plan and hp state replay identities differ")
    expected_forest = current_plan.get("expected_forest")
    if (
        not isinstance(expected_forest, Mapping)
        or expected_forest.get("leaf_catalog_sha256")
        != state.audit["leaf_catalog_sha256"]
    ):
        raise ValueError(
            "current plan leaf-catalog authority differs from hp state"
        )
    if (
        current_plan.get("cell_interior_degree_plan_sha256")
        != state.audit["cell_degree_plan_sha256"]
    ):
        raise ValueError(
            "current plan cell-degree authority differs from hp state"
        )
    return stages


@dataclass(frozen=True, slots=True)
class SolverPlanTransition:
    """One replayed next state and its canonical solver plan."""

    next_state: HPTransitionState
    plan_payload: Mapping[str, Any]
    audit: Mapping[str, Any]


def build_next_solver_plan(
    config: Any,
    *,
    current_plan: Mapping[str, Any],
    state: HPTransitionState,
    action: Mapping[str, Any],
    comm_size: int = 8,
) -> SolverPlanTransition:
    """Close ``action`` and produce the next solver-ready JSON payload."""

    if int(comm_size) != 8:
        raise ValueError("formal Task035e plan transitions require MPI8")
    stages = list(
        _validate_current_plan(
            config,
            current_plan,
            state,
            comm_size=8,
        )
    )
    next_state = close_hp_transition(state, action)
    action_kind = action.get("kind")
    if action_kind == "h-refine":
        requested_rows = action.get("requested_split_keys")
        if not isinstance(requested_rows, list) or not requested_rows:
            raise ValueError("h transition has no requested split keys")
        current_cells = state.forest.leaf_by_key
        marks = []
        for index, row in enumerate(requested_rows):
            key = _dyadic_key(row, label=f"requested_split_keys[{index}]")
            try:
                marks.append(current_cells[key].box)
            except KeyError as exc:
                raise ValueError("h transition targets a non-current leaf") from exc
        stages.append(tuple(marks))
    elif action_kind not in {"p-up", "p-down", "p-keep"}:
        raise ValueError(
            "solver-plan bridge accepts only "
            "p-up/p-down/p-keep/h-refine"
        )
    if len(stages) > 6:
        raise ValueError("solver plan would exceed six h stages")

    previous_content_sha = _canonical_plan_sha256(current_plan)
    previous_solver_content_sha = canonical_solver_content_sha256(
        current_plan
    )
    provenance = {
        "schema_version": PLAN_TRANSITION_SCHEMA,
        "status": "blind_solver_plan_transition_closed",
        "source_sha": state.source_sha,
        "algorithm_sha256": state.algorithm_sha256,
        "cycle_index": next_state.cycle_index,
        "previous_plan_content_sha256": previous_content_sha,
        "previous_plan_canonical_solver_content_sha256": (
            previous_solver_content_sha
        ),
        "from_state_sha256": state.state_sha256,
        "transition_action_sha256": action["action_sha256"],
        "transition_action_id": action["action_id"],
        "transition_action_kind": action_kind,
        "transition_action_cycle_index": action["cycle_index"],
        "transition_action_source_sha": action["source_sha"],
        "transition_action_target_ids": list(
            action["canonical_target_ids"]
        ),
        "next_state_sha256": next_state.state_sha256,
        "stage_action_sha256s": list(
            next_state.stage_action_sha256s
        ),
        "next_stage_prefix_sha256": next_state.audit[
            "stage_prefix_sha256"
        ],
        "from_leaf_catalog_sha256": state.audit[
            "leaf_catalog_sha256"
        ],
        "from_cell_degree_plan_sha256": state.audit[
            "cell_degree_plan_sha256"
        ],
        "next_leaf_catalog_sha256": next_state.audit[
            "leaf_catalog_sha256"
        ],
        "next_cell_degree_plan_sha256": next_state.audit[
            "cell_degree_plan_sha256"
        ],
        "goal_values_embedded": False,
        "dwr_values_embedded": False,
        "evaluator_inputs_consumed": False,
        "ordinary_default_changed": False,
    }
    degree_overrides = {
        cell.box: int(next_state.cell_degree_by_key[cell.key])
        for cell in next_state.forest.leaves
    }
    preliminary_plan = stage4_multilevel_local_h_refinement_plan_payload(
        config,
        tuple(stages),
        comm_size=8,
        trace_degree=4,
        cell_interior_degree=6,
        provenance=provenance,
        cell_interior_degree_overrides=degree_overrides,
        variable_trace_from_cell_degrees=True,
    )
    next_solver_content_sha = canonical_solver_content_sha256(
        preliminary_plan
    )
    if (
        action_kind == "p-keep"
        and next_solver_content_sha != previous_solver_content_sha
    ):
        raise RuntimeError("p-keep changed canonical solver content")
    provenance["next_plan_canonical_solver_content_sha256"] = (
        next_solver_content_sha
    )
    provenance["transition_provenance_sha256"] = _json_sha256(provenance)
    plan_payload = stage4_multilevel_local_h_refinement_plan_payload(
        config,
        tuple(stages),
        comm_size=8,
        trace_degree=4,
        cell_interior_degree=6,
        provenance=provenance,
        cell_interior_degree_overrides=degree_overrides,
        variable_trace_from_cell_degrees=True,
    )
    if (
        canonical_solver_content_sha256(plan_payload)
        != next_solver_content_sha
    ):
        raise RuntimeError("next solver-plan canonical content drifted")
    planned_forest = stage4_multilevel_local_h_forest_catalog(
        config,
        tuple(stages),
        comm_size=8,
    )
    for name in ("leaf_catalog_sha256", "hanging_face_catalog_sha256"):
        if planned_forest.audit[name] != next_state.forest.audit[name]:
            raise RuntimeError(f"next solver plan drifted at {name}")
    if _degree_by_box(plan_payload) != _state_degree_by_box(next_state):
        raise RuntimeError("next solver plan degree map drifted")
    expected_forest = plan_payload.get("expected_forest")
    if (
        not isinstance(expected_forest, Mapping)
        or expected_forest.get("leaf_catalog_sha256")
        != next_state.audit["leaf_catalog_sha256"]
        or plan_payload.get("cell_interior_degree_plan_sha256")
        != next_state.audit["cell_degree_plan_sha256"]
    ):
        raise RuntimeError(
            "next solver plan lacks executed-candidate identity binding"
        )
    multilevel = plan_payload["multilevel_audit"]
    audit_payload = {
        "schema_version": PLAN_TRANSITION_SCHEMA,
        "status": "blind_solver_plan_transition_pass",
        "pass": True,
        "source_sha": state.source_sha,
        "cycle_index": next_state.cycle_index,
        "action_id": action["action_id"],
        "action_kind": action_kind,
        "action_sha256": action["action_sha256"],
        "action_identity_sha256": action["action_identity_sha256"],
        "canonical_target_ids": list(action["canonical_target_ids"]),
        "from_state_sha256": state.state_sha256,
        "next_state_sha256": next_state.state_sha256,
        "stage_action_sha256s": list(
            next_state.stage_action_sha256s
        ),
        "next_stage_prefix_sha256": next_state.audit[
            "stage_prefix_sha256"
        ],
        "from_leaf_catalog_sha256": state.audit[
            "leaf_catalog_sha256"
        ],
        "from_cell_degree_plan_sha256": state.audit[
            "cell_degree_plan_sha256"
        ],
        "next_leaf_catalog_sha256": next_state.audit[
            "leaf_catalog_sha256"
        ],
        "next_cell_degree_plan_sha256": next_state.audit[
            "cell_degree_plan_sha256"
        ],
        "previous_plan_content_sha256": previous_content_sha,
        "previous_plan_canonical_solver_content_sha256": (
            previous_solver_content_sha
        ),
        "next_plan_content_sha256": _canonical_plan_sha256(plan_payload),
        "next_plan_canonical_solver_content_sha256": (
            next_solver_content_sha
        ),
        "transition_provenance_sha256": provenance[
            "transition_provenance_sha256"
        ],
        "refinement_stage_count": plan_payload["refinement_stage_count"],
        "actual_maximum_level": multilevel["actual_maximum_level"],
        "leaf_level_counts": dict(multilevel["leaf_level_counts"]),
        "cell_degree_counts": dict(next_state.audit["cell_degree_counts"]),
        "checks": {
            "current_plan_state_identity": True,
            "action_replayed": True,
            "action_id_kind_cycle_source_bound": True,
            "forest_identity": True,
            "degree_map_identity": True,
            "executed_candidate_identities_bound": True,
            "canonical_plan_content_bound": True,
            "p_keep_solver_content_unchanged": (
                action_kind != "p-keep"
                or next_solver_content_sha == previous_solver_content_sha
            ),
            "periodic_closure": True,
            "material_interface_protection": True,
            "strong_2_to_1_balance": True,
            "variable_trace_from_cell_degrees": True,
            "ordinary_default_unchanged": True,
        },
        "pde_solve_complete": False,
        "accuracy_credit": False,
    }
    audit_payload["authority_sha256"] = _json_sha256(audit_payload)
    return SolverPlanTransition(
        next_state=next_state,
        plan_payload=MappingProxyType(plan_payload),
        audit=MappingProxyType(audit_payload),
    )


__all__ = [
    "PLAN_TRANSITION_SCHEMA",
    "SolverPlanTransition",
    "build_next_solver_plan",
    "canonical_solver_content_sha256",
    "rebuild_hp_transition_state_from_solver_plan",
]
