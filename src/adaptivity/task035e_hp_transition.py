"""Hash-bound parent/child transition authority for Task035e local h/p.

This module closes only the discrete topology and degree-map transition.  It
does not assemble a finite-element tensor, solve a PDE, evaluate DWR, or grant
accuracy credit.  A transition is accepted only when it is the deterministic
result of either

* one same-forest ``p -> p +/- 1`` action,
* one same-forest, same-degree ``p-keep`` stability action, or
* one real balanced dyadic split followed by parent-degree inheritance and
  optional one-level degree changes on newly created children.

The state, stage prefix, action, root catalog, leaf catalog, degree catalog,
source identity, algorithm identity, and cycle index are content-bound.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import string
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .dyadic_hexa_refinement import (
    BalancedDyadicHexForest,
    DyadicHexKey,
    refine_balanced_dyadic_hexa_forest,
)


HP_TRANSITION_ACTION_SCHEMA = "task035e.hp-transition-action.v2"
HP_TRANSITION_STATE_SCHEMA = "task035e.hp-transition-state.v2"
_P_DEGREES = frozenset({4, 5, 6})
_ACTION_KINDS = frozenset({"p-up", "p-down", "p-keep", "h-refine"})
_STRUCTURAL_COST_FIELDS = (
    "active_dofs",
    "rows",
    "matrix_nnz",
    "factor_nnz",
    "solver_peak_bytes",
)
_ACTION_FIELDS = frozenset(
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


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _require_digest(
    value: str,
    *,
    label: str,
    lengths: tuple[int, ...] = (64,),
) -> str:
    if (
        not isinstance(value, str)
        or len(value) not in lengths
        or any(character not in string.hexdigits for character in value)
    ):
        expected = "/".join(map(str, lengths))
        raise ValueError(f"{label} must be a {expected}-character hex digest")
    return value.lower()


def _opaque_id(value: str, *, label: str) -> str:
    allowed = (
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789_.:-"
    )
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 160
        or any(character not in allowed for character in value)
    ):
        raise ValueError(f"{label} is not an opaque identifier")
    return value


def _key_row(key: DyadicHexKey) -> dict[str, int]:
    return key.to_dict()


def canonical_hp_cell_target_id(key: DyadicHexKey) -> str:
    """Return the sole Task035e controller ID for one dyadic leaf.

    The ID contains the complete dyadic key.  It therefore cannot silently
    refer to a different root, level, or child when the forest changes.
    """

    if not isinstance(key, DyadicHexKey):
        raise ValueError("canonical hp target requires a DyadicHexKey")
    return (
        f"cell:r{key.root}:l{key.level}:"
        f"i{key.i}:j{key.j}:k{key.k}"
    )


def _canonical_target_ids(
    *,
    kind: str,
    requested: Sequence[DyadicHexKey],
    degree_deltas: Mapping[DyadicHexKey, int],
) -> tuple[str, ...]:
    if kind == "p-keep":
        if requested or degree_deltas:
            raise ValueError("p-keep action must not contain targets")
        return ()
    target_keys = (
        tuple(sorted(requested))
        if kind == "h-refine"
        else tuple(sorted(degree_deltas))
    )
    if not target_keys:
        raise ValueError("hp transition has no canonical action targets")
    return tuple(canonical_hp_cell_target_id(key) for key in target_keys)


def _parse_key(row: Any, *, label: str) -> DyadicHexKey:
    if not isinstance(row, Mapping) or set(row) != {
        "root",
        "level",
        "i",
        "j",
        "k",
    }:
        raise ValueError(f"{label} is not one canonical dyadic key")
    if any(type(row[name]) is not int for name in row):
        raise ValueError(f"{label} contains a non-integral dyadic coordinate")
    return DyadicHexKey(
        row["root"],
        row["level"],
        row["i"],
        row["j"],
        row["k"],
    )


def _parse_key_rows(rows: Any, *, label: str) -> tuple[DyadicHexKey, ...]:
    if not isinstance(rows, list):
        raise ValueError(f"{label} must be a JSON array")
    result = tuple(
        _parse_key(row, label=f"{label}[{index}]")
        for index, row in enumerate(rows)
    )
    if len(set(result)) != len(result):
        raise ValueError(f"{label} contains duplicate dyadic keys")
    if result != tuple(sorted(result)):
        raise ValueError(f"{label} is not in canonical order")
    return result


def _parent_key(key: DyadicHexKey) -> DyadicHexKey:
    if key.level == 0:
        raise ValueError("a root leaf has no dyadic parent")
    return DyadicHexKey(
        key.root,
        key.level - 1,
        key.i // 2,
        key.j // 2,
        key.k // 2,
    )


def _root_catalog_sha256(forest: BalancedDyadicHexForest) -> str:
    return _json_sha256(
        {
            "roots": [
                {
                    "root": index,
                    "box": list(box),
                    "material_tag": int(tag),
                }
                for index, (box, tag) in enumerate(
                    zip(
                        forest.root_boxes,
                        forest.root_material_tags,
                        strict=True,
                    )
                )
            ],
            "periodic_axes": list(forest.periodic_axes),
            "protect_material_interfaces": bool(
                forest.protect_material_interfaces
            ),
            "domain_bounds": list(forest.domain_bounds),
        }
    )


def _forest_geometry_sha256(forest: BalancedDyadicHexForest) -> str:
    return _json_sha256(
        {
            "root_catalog_sha256": _root_catalog_sha256(forest),
            "leaf_catalog_sha256": forest.audit["leaf_catalog_sha256"],
            "hanging_face_catalog_sha256": forest.audit[
                "hanging_face_catalog_sha256"
            ],
            "leaf_level_counts": dict(forest.audit["leaf_level_counts"]),
            "periodic_boundary_audit": dict(
                forest.audit["periodic_boundary_audit"]
            ),
            "material_interface_hanging_face_count": int(
                forest.audit["material_interface_hanging_face_count"]
            ),
        }
    )


def _degree_plan_sha256(
    forest: BalancedDyadicHexForest,
    degrees: Mapping[DyadicHexKey, int],
) -> str:
    return _json_sha256(
        {
            "forest_geometry_sha256": _forest_geometry_sha256(forest),
            "degrees": [
                {
                    "key": _key_row(cell.key),
                    "degree": int(degrees[cell.key]),
                }
                for cell in forest.leaves
            ],
        }
    )


def _cell_degree_plan_sha256(
    forest: BalancedDyadicHexForest,
    degrees: Mapping[DyadicHexKey, int],
) -> str:
    """Hash the exact box/degree rows emitted to the Stage-4 solver plan."""

    return _json_sha256(
        [
            {
                "box": list(cell.box),
                "degree": int(degrees[cell.key]),
            }
            for cell in sorted(forest.leaves, key=lambda item: item.box)
        ]
    )


def _execution_identity(
    forest: BalancedDyadicHexForest,
    degrees: Mapping[DyadicHexKey, int],
) -> dict[str, str]:
    return {
        "leaf_catalog_sha256": str(
            forest.audit["leaf_catalog_sha256"]
        ),
        "cell_degree_plan_sha256": _cell_degree_plan_sha256(
            forest,
            degrees,
        ),
    }


def _stage_prefix_sha256(action_sha256s: Sequence[str]) -> str:
    return _json_sha256({"action_sha256s": list(action_sha256s)})


def _structural_cost_not_measured() -> dict[str, Any]:
    return {
        name: {
            "measurement_status": "not_measured",
            "value": None,
            "reason": (
                "topology/degree transition component has not assembled "
                "or factored a solver matrix"
            ),
        }
        for name in _STRUCTURAL_COST_FIELDS
    }


def _validate_forest(forest: BalancedDyadicHexForest) -> None:
    if forest.audit.get("pass") is not True:
        raise ValueError("hp transition requires a passing dyadic forest")
    if tuple(forest.periodic_axes) != ("x", "y"):
        raise ValueError("Task035e hp transition requires x/y periodic closure")
    if forest.protect_material_interfaces is not True:
        raise ValueError("Task035e hp transition requires material protection")
    if forest.audit.get("strong_2_to_1_balance") is not True:
        raise ValueError("hp transition forest is not strongly 2:1 balanced")
    periodic = forest.audit.get("periodic_boundary_audit")
    if not isinstance(periodic, Mapping) or not periodic:
        raise ValueError("hp transition forest has no periodic audit")
    if any(row.get("matching") is not True for row in periodic.values()):
        raise ValueError("hp transition forest has unmatched periodic faces")
    if int(forest.audit.get("material_interface_hanging_face_count", -1)) != 0:
        raise ValueError("hp transition forest has a material hanging face")


def _normalized_degrees(
    forest: BalancedDyadicHexForest,
    values: Mapping[DyadicHexKey, int],
) -> dict[DyadicHexKey, int]:
    if not isinstance(values, Mapping):
        raise ValueError("cell degree map must be a mapping")
    normalized: dict[DyadicHexKey, int] = {}
    for raw_key, raw_degree in values.items():
        if not isinstance(raw_key, DyadicHexKey):
            raise ValueError("cell degree map keys must be DyadicHexKey")
        degree = int(raw_degree)
        if degree not in _P_DEGREES:
            raise ValueError("cell degrees must be p4, p5, or p6")
        normalized[raw_key] = degree
    expected = set(forest.leaf_by_key)
    observed = set(normalized)
    if expected != observed:
        raise ValueError(
            "cell degree map must cover the current leaf catalog exactly: "
            f"missing={sorted(expected - observed)[:2]}, "
            f"extra={sorted(observed - expected)[:2]}"
        )
    return {key: normalized[key] for key in sorted(normalized)}


def _positive_overlap(
    left: tuple[float, float],
    right: tuple[float, float],
) -> bool:
    extent = max(
        abs(left[0]),
        abs(left[1]),
        abs(right[0]),
        abs(right[1]),
        1.0,
    )
    tolerance = extent * 1.0e-11
    return min(left[1], right[1]) - max(left[0], right[0]) > tolerance


def _face_neighbor_pairs(
    forest: BalancedDyadicHexForest,
) -> tuple[tuple[DyadicHexKey, DyadicHexKey], ...]:
    by_plane: dict[
        tuple[int, float],
        list[
            tuple[
                int,
                DyadicHexKey,
                tuple[float, float],
                tuple[float, float],
            ]
        ],
    ] = {}
    for cell in forest.leaves:
        for axis in range(3):
            tangential = tuple(
                candidate for candidate in range(3) if candidate != axis
            )
            intervals = (
                (cell.box[tangential[0]], cell.box[tangential[0] + 3]),
                (cell.box[tangential[1]], cell.box[tangential[1] + 3]),
            )
            for side, coordinate in (
                (0, cell.box[axis]),
                (1, cell.box[axis + 3]),
            ):
                by_plane.setdefault(
                    (axis, round(float(coordinate), 12)),
                    [],
                ).append((side, cell.key, *intervals))

    pairs: set[tuple[DyadicHexKey, DyadicHexKey]] = set()

    def add_overlaps(
        left_rows: Sequence[
            tuple[
                int,
                DyadicHexKey,
                tuple[float, float],
                tuple[float, float],
            ]
        ],
        right_rows: Sequence[
            tuple[
                int,
                DyadicHexKey,
                tuple[float, float],
                tuple[float, float],
            ]
        ],
    ) -> None:
        for _left_side, left_key, left_u, left_v in left_rows:
            for _right_side, right_key, right_u, right_v in right_rows:
                if (
                    left_key != right_key
                    and _positive_overlap(left_u, right_u)
                    and _positive_overlap(left_v, right_v)
                ):
                    pairs.add(tuple(sorted((left_key, right_key))))

    for rows in by_plane.values():
        add_overlaps(
            [row for row in rows if row[0] == 1],
            [row for row in rows if row[0] == 0],
        )

    axis_by_name = {"x": 0, "y": 1, "z": 2}
    for axis_name in forest.periodic_axes:
        axis = axis_by_name[axis_name]
        lower = round(float(forest.domain_bounds[axis]), 12)
        upper = round(float(forest.domain_bounds[axis + 3]), 12)
        add_overlaps(
            [
                row
                for row in by_plane.get((axis, upper), ())
                if row[0] == 1
            ],
            [
                row
                for row in by_plane.get((axis, lower), ())
                if row[0] == 0
            ],
        )
    return tuple(sorted(pairs))


def _degree_jump_audit(
    forest: BalancedDyadicHexForest,
    degrees: Mapping[DyadicHexKey, int],
) -> dict[str, Any]:
    pairs = _face_neighbor_pairs(forest)
    rows = [
        (left, right, abs(int(degrees[left]) - int(degrees[right])))
        for left, right in pairs
    ]
    maximum = max((row[2] for row in rows), default=0)
    if maximum > 1:
        offenders = [
            {
                "left": _key_row(left),
                "right": _key_row(right),
                "jump": jump,
            }
            for left, right, jump in rows
            if jump > 1
        ]
        raise ValueError(
            "adjacent or periodic cell p jump exceeds one: "
            f"{offenders[:2]}"
        )
    return {
        "face_or_periodic_neighbor_pair_count": len(pairs),
        "maximum_adjacent_or_periodic_cell_p_jump": maximum,
        "adjacent_or_periodic_cell_p_jump_at_most_one": True,
    }


def _leaf_transition_explanation(
    current: BalancedDyadicHexForest,
    next_forest: BalancedDyadicHexForest,
    requested: Sequence[DyadicHexKey],
) -> dict[str, Any]:
    current_cells = dict(current.leaf_by_key)
    next_cells = dict(next_forest.leaf_by_key)
    current_keys = set(current_cells)
    next_keys = set(next_cells)
    removed = tuple(sorted(current_keys - next_keys))
    added = tuple(sorted(next_keys - current_keys))
    requested_set = set(requested)
    if not requested_set.issubset(removed):
        raise ValueError("requested h-refine leaves were not split")
    if not removed:
        raise ValueError("h-refine action removed no current leaves")

    child_rows: list[dict[str, Any]] = []
    explained_added: set[DyadicHexKey] = set()
    for parent in removed:
        expected_children = set(parent.children())
        children = tuple(sorted(expected_children.intersection(added)))
        if set(children) != expected_children:
            raise ValueError(
                "one removed leaf is not explained by exactly eight "
                f"direct children: {parent}"
            )
        parent_cell = current_cells[parent]
        for child in children:
            if next_cells[child].material_tag != parent_cell.material_tag:
                raise ValueError("one child did not inherit parent material")
        explained_added.update(children)
        child_rows.append(
            {
                "parent": _key_row(parent),
                "children": [_key_row(child) for child in children],
                "reason": (
                    "requested_split"
                    if parent in requested_set
                    else "closure_split"
                ),
            }
        )
    if explained_added != set(added):
        raise ValueError("one added leaf has no removed direct parent")
    if len(added) - len(removed) != 7 * len(removed):
        raise ValueError("dyadic leaf delta is not eight-for-one")
    return {
        "requested_split_keys": [_key_row(key) for key in sorted(requested)],
        "closure_split_keys": [
            _key_row(key) for key in sorted(set(removed) - requested_set)
        ],
        "removed_leaf_keys": [_key_row(key) for key in removed],
        "added_leaf_keys": [_key_row(key) for key in added],
        "parent_child_explanations": child_rows,
        "pre_leaf_count": len(current_keys),
        "post_leaf_count": len(next_keys),
        "net_added_leaf_count": len(added) - len(removed),
        "every_removed_leaf_explained": True,
        "every_added_leaf_explained": True,
        "parent_material_inheritance": True,
    }


def _state_identity_payload(
    *,
    forest: BalancedDyadicHexForest,
    degrees: Mapping[DyadicHexKey, int],
    source_sha: str,
    algorithm_sha256: str,
    cycle_index: int,
    action_sha256s: Sequence[str],
) -> dict[str, Any]:
    execution_identity = _execution_identity(forest, degrees)
    return {
        "root_catalog_sha256": _root_catalog_sha256(forest),
        **execution_identity,
        "forest_geometry_sha256": _forest_geometry_sha256(forest),
        "degree_plan_sha256": _degree_plan_sha256(forest, degrees),
        "source_sha": source_sha,
        "algorithm_sha256": algorithm_sha256,
        "cycle_index": int(cycle_index),
        "stage_action_sha256s": list(action_sha256s),
        "stage_prefix_sha256": _stage_prefix_sha256(action_sha256s),
    }


@dataclass(frozen=True, slots=True)
class HPTransitionState:
    """One closed component-only forest/degree state."""

    forest: BalancedDyadicHexForest
    cell_degree_by_key: Mapping[DyadicHexKey, int]
    source_sha: str
    algorithm_sha256: str
    cycle_index: int
    stage_action_sha256s: tuple[str, ...]
    audit: Mapping[str, Any]

    @property
    def state_sha256(self) -> str:
        return str(self.audit["state_sha256"])


def _build_state(
    forest: BalancedDyadicHexForest,
    degrees: Mapping[DyadicHexKey, int],
    *,
    source_sha: str,
    algorithm_sha256: str,
    cycle_index: int,
    action_sha256s: Sequence[str],
    transition: Mapping[str, Any] | None,
) -> HPTransitionState:
    _validate_forest(forest)
    normalized = _normalized_degrees(forest, degrees)
    jump_audit = _degree_jump_audit(forest, normalized)
    source = _require_digest(
        source_sha,
        label="source SHA",
        lengths=(40, 64),
    )
    algorithm = _require_digest(
        algorithm_sha256,
        label="algorithm SHA-256",
    )
    cycle = int(cycle_index)
    chain = tuple(
        _require_digest(value, label="stage action SHA-256")
        for value in action_sha256s
    )
    if not 0 <= cycle <= 5:
        raise ValueError("Task035e cycle index must be in [0, 5]")
    if len(chain) != cycle:
        raise ValueError("stage prefix length must equal the cycle index")
    identity = _state_identity_payload(
        forest=forest,
        degrees=normalized,
        source_sha=source,
        algorithm_sha256=algorithm,
        cycle_index=cycle,
        action_sha256s=chain,
    )
    state_sha256 = _json_sha256(identity)
    audit_payload = {
        "schema_version": HP_TRANSITION_STATE_SCHEMA,
        "status": (
            "hp_transition_initial_component_state"
            if transition is None and cycle == 0
            else "hp_transition_rebuilt_component_state"
            if transition is None
            else "hp_transition_closed_component_only"
        ),
        "pass": True,
        "capability_scope": "topology_and_degree_transition_component_only",
        **identity,
        "state_sha256": state_sha256,
        "cell_degree_counts": {
            f"p{degree}": sum(value == degree for value in normalized.values())
            for degree in sorted(_P_DEGREES)
        },
        "degree_jump_audit": jump_audit,
        "forest_checks": {
            "strong_2_to_1_balance": True,
            "periodic_closure": True,
            "material_interface_protection": True,
        },
        "transition": None if transition is None else dict(transition),
        "structural_cost": _structural_cost_not_measured(),
        "compiled_tensor_binding_complete": False,
        "petsc_matrix_constructed": False,
        "pde_solve_complete": False,
        "d4_shadow_verification_complete": False,
        "pde_accuracy_credit": False,
        "ordinary_default_changed": False,
    }
    return HPTransitionState(
        forest=forest,
        cell_degree_by_key=MappingProxyType(normalized),
        source_sha=source,
        algorithm_sha256=algorithm,
        cycle_index=cycle,
        stage_action_sha256s=chain,
        audit=MappingProxyType(audit_payload),
    )


def build_initial_hp_transition_state(
    forest: BalancedDyadicHexForest,
    cell_degree_by_key: Mapping[DyadicHexKey, int],
    *,
    source_sha: str,
    algorithm_sha256: str,
) -> HPTransitionState:
    """Close the root state from which transition actions may start."""

    return _build_state(
        forest,
        cell_degree_by_key,
        source_sha=source_sha,
        algorithm_sha256=algorithm_sha256,
        cycle_index=0,
        action_sha256s=(),
        transition=None,
    )


def rebuild_hp_transition_state(
    forest: BalancedDyadicHexForest,
    cell_degree_by_key: Mapping[DyadicHexKey, int],
    *,
    source_sha: str,
    algorithm_sha256: str,
    cycle_index: int,
    stage_action_sha256s: Sequence[str],
    expected_state_sha256: str,
    expected_stage_prefix_sha256: str,
) -> HPTransitionState:
    """Fail closed while rebuilding one persisted current h/p state.

    ``HPTransitionState`` deliberately contains the live dyadic forest rather
    than a JSON serialization of it.  A resumed blind cycle can therefore
    rebuild the object from its executed solver plan, forest, and complete
    degree map, provided the plan also carries the *entire* ordered action
    chain.  Both the resulting state identity and the chain-prefix identity
    must match the independently persisted authorities supplied here.

    This function does not replay or infer missing actions.  Supplying only
    the most recent action is rejected by the cycle/chain length invariant.
    """

    if type(cycle_index) is not int:
        raise ValueError("rebuilt hp transition cycle index must be integral")
    if isinstance(stage_action_sha256s, (str, bytes)) or not isinstance(
        stage_action_sha256s,
        Sequence,
    ):
        raise ValueError(
            "rebuilt hp transition action chain must be a sequence"
        )
    expected_state = _require_digest(
        expected_state_sha256,
        label="expected rebuilt state SHA-256",
    )
    expected_prefix = _require_digest(
        expected_stage_prefix_sha256,
        label="expected rebuilt stage-prefix SHA-256",
    )
    rebuilt = _build_state(
        forest,
        cell_degree_by_key,
        source_sha=source_sha,
        algorithm_sha256=algorithm_sha256,
        cycle_index=cycle_index,
        action_sha256s=tuple(stage_action_sha256s),
        transition=None,
    )
    observed_prefix = str(rebuilt.audit["stage_prefix_sha256"])
    if observed_prefix != expected_prefix:
        raise ValueError("rebuilt hp transition stage prefix drifted")
    if rebuilt.state_sha256 != expected_state:
        raise ValueError("rebuilt hp transition state identity drifted")
    _validate_state_identity(rebuilt)
    return rebuilt


def _validate_state_identity(state: HPTransitionState) -> None:
    if not isinstance(state, HPTransitionState):
        raise ValueError("current state must use HPTransitionState")
    identity = _state_identity_payload(
        forest=state.forest,
        degrees=state.cell_degree_by_key,
        source_sha=state.source_sha,
        algorithm_sha256=state.algorithm_sha256,
        cycle_index=state.cycle_index,
        action_sha256s=state.stage_action_sha256s,
    )
    if state.audit.get("state_sha256") != _json_sha256(identity):
        raise ValueError("current hp transition state identity drifted")
    if state.audit.get("stage_prefix_sha256") != _stage_prefix_sha256(
        state.stage_action_sha256s
    ):
        raise ValueError("current hp transition stage prefix drifted")


def _normalize_delta_rows(
    rows: Any,
) -> dict[DyadicHexKey, int]:
    if not isinstance(rows, list):
        raise ValueError("degree_deltas must be a JSON array")
    result: dict[DyadicHexKey, int] = {}
    previous: DyadicHexKey | None = None
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping) or set(row) != {"key", "delta"}:
            raise ValueError(f"degree_deltas[{index}] is malformed")
        key = _parse_key(row["key"], label=f"degree_deltas[{index}].key")
        if previous is not None and key <= previous:
            raise ValueError("degree_deltas are duplicated or not canonical")
        delta = row["delta"]
        if type(delta) is not int or delta not in {-1, 1}:
            raise ValueError("one p action may only change a degree by +/-1")
        result[key] = delta
        previous = key
    return result


def _preview_transition(
    state: HPTransitionState,
    *,
    kind: str,
    requested: Sequence[DyadicHexKey],
    degree_deltas: Mapping[DyadicHexKey, int],
    maximum_level: int | None,
) -> tuple[
    BalancedDyadicHexForest,
    dict[DyadicHexKey, int],
    dict[str, Any],
]:
    current_forest = state.forest
    current_degrees = dict(state.cell_degree_by_key)
    if kind == "p-keep":
        if requested or degree_deltas or maximum_level is not None:
            raise ValueError(
                "p-keep requires empty splits/deltas and null maximum_level"
            )
        next_degrees = dict(current_degrees)
        next_forest = current_forest
        explanation = {
            "requested_split_keys": [],
            "closure_split_keys": [],
            "removed_leaf_keys": [],
            "added_leaf_keys": [],
            "parent_child_explanations": [],
            "pre_leaf_count": len(current_forest.leaves),
            "post_leaf_count": len(current_forest.leaves),
            "net_added_leaf_count": 0,
            "every_removed_leaf_explained": True,
            "every_added_leaf_explained": True,
            "parent_material_inheritance": True,
        }
    elif kind in {"p-up", "p-down"}:
        if requested or maximum_level is not None:
            raise ValueError("same-forest p action cannot contain h-refinement")
        if not degree_deltas:
            raise ValueError("same-forest p action requires degree targets")
        expected_delta = 1 if kind == "p-up" else -1
        if any(delta != expected_delta for delta in degree_deltas.values()):
            raise ValueError(f"{kind} contains a degree delta with wrong sign")
        missing = sorted(set(degree_deltas) - set(current_degrees))
        if missing:
            raise ValueError(f"p action targets non-leaf keys: {missing[:2]}")
        next_degrees = dict(current_degrees)
        for key, delta in degree_deltas.items():
            next_degrees[key] += delta
        explanation = {
            "requested_split_keys": [],
            "closure_split_keys": [],
            "removed_leaf_keys": [],
            "added_leaf_keys": [],
            "parent_child_explanations": [],
            "pre_leaf_count": len(current_forest.leaves),
            "post_leaf_count": len(current_forest.leaves),
            "net_added_leaf_count": 0,
            "every_removed_leaf_explained": True,
            "every_added_leaf_explained": True,
            "parent_material_inheritance": True,
        }
        next_forest = current_forest
    else:
        if kind != "h-refine":
            raise ValueError(f"unsupported hp transition action: {kind!r}")
        if not requested:
            raise ValueError("h-refine action requires requested leaf keys")
        if maximum_level is None:
            raise ValueError("h-refine action requires maximum_level")
        if type(maximum_level) is not int or maximum_level != 2:
            raise ValueError(
                "Task035e h-refine actions require maximum_level=2"
            )
        next_forest = refine_balanced_dyadic_hexa_forest(
            current_forest,
            requested,
            maximum_level=int(maximum_level),
        )
        explanation = _leaf_transition_explanation(
            current_forest,
            next_forest,
            requested,
        )
        added = {
            _parse_key(row, label="added_leaf_keys")
            for row in explanation["added_leaf_keys"]
        }
        if set(degree_deltas) - added:
            raise ValueError(
                "post-split p changes may target only newly inherited children"
            )
        next_degrees = {}
        for cell in next_forest.leaves:
            if cell.key in current_degrees:
                inherited = current_degrees[cell.key]
            else:
                parent = _parent_key(cell.key)
                try:
                    inherited = current_degrees[parent]
                except KeyError as exc:
                    raise ValueError(
                        "one new child has no current parent degree"
                    ) from exc
            next_degrees[cell.key] = inherited + degree_deltas.get(cell.key, 0)

    invalid = sorted(
        {
            degree
            for degree in next_degrees.values()
            if degree not in _P_DEGREES
        }
    )
    if invalid:
        raise ValueError(
            "hp transition leaves the qualified p4/p5/p6 range: "
            f"{invalid}"
        )
    _normalized_degrees(next_forest, next_degrees)
    _degree_jump_audit(next_forest, next_degrees)
    return next_forest, next_degrees, explanation


def hp_transition_action_payload(
    state: HPTransitionState,
    *,
    action_id: str,
    kind: str,
    degree_deltas: Mapping[DyadicHexKey, int],
    requested_split_keys: Sequence[DyadicHexKey] = (),
    maximum_level: int | None = None,
) -> dict[str, Any]:
    """Build one canonical action and bind its deterministic next identity."""

    _validate_state_identity(state)
    if state.cycle_index >= 5:
        raise ValueError("Task035e transition would exceed six cycle states")
    action_kind = str(kind)
    if action_kind not in _ACTION_KINDS:
        raise ValueError(f"unsupported hp transition action: {action_kind!r}")
    identifier = _opaque_id(action_id, label="action_id")
    requested = tuple(sorted(set(requested_split_keys)))
    if len(requested) != len(tuple(requested_split_keys)):
        raise ValueError("requested h-refine leaf keys are duplicated")
    normalized_deltas: dict[DyadicHexKey, int] = {}
    for key, raw_delta in degree_deltas.items():
        if not isinstance(key, DyadicHexKey):
            raise ValueError("degree delta keys must be DyadicHexKey")
        if type(raw_delta) is not int or raw_delta not in {-1, 1}:
            raise ValueError("one p action may only change a degree by +/-1")
        normalized_deltas[key] = raw_delta
    next_forest, next_degrees, explanation = _preview_transition(
        state,
        kind=action_kind,
        requested=requested,
        degree_deltas=normalized_deltas,
        maximum_level=maximum_level,
    )
    canonical_target_ids = _canonical_target_ids(
        kind=action_kind,
        requested=requested,
        degree_deltas=normalized_deltas,
    )
    from_execution_identity = _execution_identity(
        state.forest,
        state.cell_degree_by_key,
    )
    next_execution_identity = _execution_identity(
        next_forest,
        next_degrees,
    )
    payload: dict[str, Any] = {
        "schema_version": HP_TRANSITION_ACTION_SCHEMA,
        "status": "hp_transition_action_closed",
        "action_id": identifier,
        "kind": action_kind,
        "cycle_index": state.cycle_index + 1,
        "source_sha": state.source_sha,
        "algorithm_sha256": state.algorithm_sha256,
        "from_state_sha256": state.state_sha256,
        "root_catalog_sha256": _root_catalog_sha256(state.forest),
        "from_leaf_catalog_sha256": from_execution_identity[
            "leaf_catalog_sha256"
        ],
        "from_cell_degree_plan_sha256": from_execution_identity[
            "cell_degree_plan_sha256"
        ],
        "from_forest_geometry_sha256": _forest_geometry_sha256(
            state.forest
        ),
        "from_degree_plan_sha256": _degree_plan_sha256(
            state.forest,
            state.cell_degree_by_key,
        ),
        "stage_prefix_length": len(state.stage_action_sha256s),
        "stage_prefix_sha256": _stage_prefix_sha256(
            state.stage_action_sha256s
        ),
        "requested_split_keys": [
            _key_row(key) for key in requested
        ],
        "degree_deltas": [
            {"key": _key_row(key), "delta": normalized_deltas[key]}
            for key in sorted(normalized_deltas)
        ],
        "canonical_target_ids": list(canonical_target_ids),
        "maximum_level": (
            None if maximum_level is None else int(maximum_level)
        ),
        "expected_removed_leaf_keys": list(
            explanation["removed_leaf_keys"]
        ),
        "expected_added_leaf_keys": list(explanation["added_leaf_keys"]),
        "expected_net_added_leaf_count": int(
            explanation["net_added_leaf_count"]
        ),
        "expected_next_leaf_catalog_sha256": next_execution_identity[
            "leaf_catalog_sha256"
        ],
        "expected_next_cell_degree_plan_sha256": (
            next_execution_identity["cell_degree_plan_sha256"]
        ),
        "expected_next_forest_geometry_sha256": (
            _forest_geometry_sha256(next_forest)
        ),
        "expected_next_degree_plan_sha256": _degree_plan_sha256(
            next_forest,
            next_degrees,
        ),
    }
    payload["action_identity_sha256"] = _json_sha256(
        {
            "action_id": payload["action_id"],
            "kind": payload["kind"],
            "cycle_index": payload["cycle_index"],
            "source_sha": payload["source_sha"],
            "algorithm_sha256": payload["algorithm_sha256"],
            "canonical_target_ids": payload["canonical_target_ids"],
        }
    )
    payload["action_sha256"] = _json_sha256(payload)
    return payload


def close_hp_transition(
    state: HPTransitionState,
    action: Mapping[str, Any],
    *,
    proposed_forest: BalancedDyadicHexForest | None = None,
    proposed_cell_degree_by_key: Mapping[DyadicHexKey, int] | None = None,
) -> HPTransitionState:
    """Replay and close one action, optionally validating a proposed result."""

    _validate_state_identity(state)
    if not isinstance(action, Mapping) or set(action) != _ACTION_FIELDS:
        raise ValueError("hp transition action fields are incomplete or unknown")
    payload = dict(action)
    observed_action_sha = _require_digest(
        payload["action_sha256"],
        label="action SHA-256",
    )
    unhashed = dict(payload)
    unhashed.pop("action_sha256")
    if observed_action_sha != _json_sha256(unhashed):
        raise ValueError("hp transition action SHA-256 is invalid")
    if payload["schema_version"] != HP_TRANSITION_ACTION_SCHEMA:
        raise ValueError("hp transition action schema is invalid")
    if payload["status"] != "hp_transition_action_closed":
        raise ValueError("hp transition action status is invalid")
    _opaque_id(payload["action_id"], label="action_id")
    kind = str(payload["kind"])
    if kind not in _ACTION_KINDS:
        raise ValueError("hp transition action kind is invalid")
    if (
        payload["source_sha"] != state.source_sha
        or payload["algorithm_sha256"] != state.algorithm_sha256
        or payload["from_state_sha256"] != state.state_sha256
        or payload["root_catalog_sha256"]
        != _root_catalog_sha256(state.forest)
        or payload["from_leaf_catalog_sha256"]
        != state.audit["leaf_catalog_sha256"]
        or payload["from_cell_degree_plan_sha256"]
        != state.audit["cell_degree_plan_sha256"]
        or payload["from_forest_geometry_sha256"]
        != _forest_geometry_sha256(state.forest)
        or payload["from_degree_plan_sha256"]
        != _degree_plan_sha256(state.forest, state.cell_degree_by_key)
        or payload["cycle_index"] != state.cycle_index + 1
    ):
        raise ValueError("hp transition source/root/geometry/cycle binding failed")
    if (
        payload["stage_prefix_length"] != len(state.stage_action_sha256s)
        or payload["stage_prefix_sha256"]
        != _stage_prefix_sha256(state.stage_action_sha256s)
    ):
        raise ValueError("hp transition stage prefix does not match current state")

    requested = _parse_key_rows(
        payload["requested_split_keys"],
        label="requested_split_keys",
    )
    degree_deltas = _normalize_delta_rows(payload["degree_deltas"])
    canonical_target_ids = _canonical_target_ids(
        kind=kind,
        requested=requested,
        degree_deltas=degree_deltas,
    )
    if payload["canonical_target_ids"] != list(canonical_target_ids):
        raise ValueError("hp transition canonical target IDs drifted")
    expected_action_identity_sha256 = _json_sha256(
        {
            "action_id": payload["action_id"],
            "kind": kind,
            "cycle_index": payload["cycle_index"],
            "source_sha": payload["source_sha"],
            "algorithm_sha256": payload["algorithm_sha256"],
            "canonical_target_ids": list(canonical_target_ids),
        }
    )
    if (
        payload["action_identity_sha256"]
        != expected_action_identity_sha256
    ):
        raise ValueError("hp transition action identity drifted")
    maximum_level = payload["maximum_level"]
    if maximum_level is not None and type(maximum_level) is not int:
        raise ValueError("maximum_level must be integral or null")
    expected_forest, expected_degrees, explanation = _preview_transition(
        state,
        kind=kind,
        requested=requested,
        degree_deltas=degree_deltas,
        maximum_level=maximum_level,
    )
    expected_bindings = {
        "expected_removed_leaf_keys": explanation["removed_leaf_keys"],
        "expected_added_leaf_keys": explanation["added_leaf_keys"],
        "expected_net_added_leaf_count": explanation[
            "net_added_leaf_count"
        ],
        "expected_next_leaf_catalog_sha256": expected_forest.audit[
            "leaf_catalog_sha256"
        ],
        "expected_next_cell_degree_plan_sha256": (
            _cell_degree_plan_sha256(expected_forest, expected_degrees)
        ),
        "expected_next_forest_geometry_sha256": (
            _forest_geometry_sha256(expected_forest)
        ),
        "expected_next_degree_plan_sha256": _degree_plan_sha256(
            expected_forest,
            expected_degrees,
        ),
    }
    for name, expected in expected_bindings.items():
        if payload[name] != expected:
            raise ValueError(f"hp transition action {name} drifted")

    candidate_forest = (
        expected_forest if proposed_forest is None else proposed_forest
    )
    _validate_forest(candidate_forest)
    if _root_catalog_sha256(candidate_forest) != _root_catalog_sha256(
        state.forest
    ):
        raise ValueError("proposed hp transition uses different roots")
    if _forest_geometry_sha256(candidate_forest) != _forest_geometry_sha256(
        expected_forest
    ):
        raise ValueError("proposed hp transition is not the replayed forest")
    candidate_degrees = (
        expected_degrees
        if proposed_cell_degree_by_key is None
        else _normalized_degrees(
            candidate_forest,
            proposed_cell_degree_by_key,
        )
    )
    if dict(candidate_degrees) != dict(expected_degrees):
        raise ValueError(
            "proposed child degree map is not inherited/action-explained"
        )

    transition_audit = {
        "schema_version": "task035e.hp-transition-closure.v2",
        "status": "hp_transition_component_only_pass",
        "pass": True,
        "action_id": payload["action_id"],
        "action_kind": kind,
        "action_sha256": observed_action_sha,
        "action_identity_sha256": expected_action_identity_sha256,
        "canonical_target_ids": list(canonical_target_ids),
        "from_state_sha256": state.state_sha256,
        "from_leaf_catalog_sha256": payload[
            "from_leaf_catalog_sha256"
        ],
        "from_cell_degree_plan_sha256": payload[
            "from_cell_degree_plan_sha256"
        ],
        "next_leaf_catalog_sha256": payload[
            "expected_next_leaf_catalog_sha256"
        ],
        "next_cell_degree_plan_sha256": payload[
            "expected_next_cell_degree_plan_sha256"
        ],
        "stage_prefix_sha256": payload["stage_prefix_sha256"],
        "leaf_transition": explanation,
        "checks": {
            "source_algorithm_cycle_bound": True,
            "root_and_geometry_bound": True,
            "stage_prefix_valid": True,
            "action_sha256_valid": True,
            "canonical_target_ids_valid": True,
            "executed_candidate_identities_bound": True,
            "same_forest_or_one_replayed_h_stage": True,
            "all_leaf_changes_explained": True,
            "parent_degree_inheritance": True,
            "one_level_p_change_only": True,
            "p_jump_at_most_one": True,
            "strong_2_to_1_balance": True,
            "periodic_closure": True,
            "material_interface_protection": True,
        },
        "structural_cost": _structural_cost_not_measured(),
        "compiled_tensor_binding_complete": False,
        "petsc_matrix_constructed": False,
        "pde_solve_complete": False,
        "d4_shadow_verification_complete": False,
        "pde_accuracy_credit": False,
    }
    return _build_state(
        candidate_forest,
        candidate_degrees,
        source_sha=state.source_sha,
        algorithm_sha256=state.algorithm_sha256,
        cycle_index=state.cycle_index + 1,
        action_sha256s=(
            *state.stage_action_sha256s,
            observed_action_sha,
        ),
        transition=transition_audit,
    )


__all__ = [
    "HP_TRANSITION_ACTION_SCHEMA",
    "HP_TRANSITION_STATE_SCHEMA",
    "HPTransitionState",
    "build_initial_hp_transition_state",
    "canonical_hp_cell_target_id",
    "close_hp_transition",
    "hp_transition_action_payload",
    "rebuild_hp_transition_state",
]
