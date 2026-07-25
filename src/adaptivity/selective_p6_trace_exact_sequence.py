"""Exact-sequence closure for periodic missing-p6 trace orbits.

This module is deliberately between two existing Task035b layers:

* :mod:`src.adaptivity.selective_p6_trace_orbits` discovers complete periodic
  edge/face orbits and can number a caller-selected set without inactive rows;
* a later physical integration layer will provide channel-DWR seeds and an
  actual mesh-bound discrete-gradient map.

The code here does not invent sensitivities or inspect a DOLFINx mesh.  It
accepts caller-qualified, directed scalar-to-H(curl) gradient-incidence rules.
If the H(curl) orbit anchoring one scalar orbit is selected, every H(curl)
orbit in that scalar gradient's support is added.  Closure and the
Full3D-equivalent budget are checked before the existing numbering layer is
allowed to allocate selected rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

import numpy as np

from .selective_p6_trace_orbits import (
    MissingP6TraceEntity,
    PeriodicMissingTraceRelation,
    PeriodicP6TraceOrbit,
    SelectiveP6TraceNumbering,
    build_selective_p6_trace_numbering,
)


_EXPECTED_MISSING_HCURL_MODES = {"edge": 1, "face": 20}
_EXPECTED_MISSING_SCALAR_MODES = {"edge": 1, "face": 9}


def _validated_sha256(value: str, *, label: str) -> str:
    normalized = str(value).lower()
    try:
        valid = len(normalized) == 64 and len(bytes.fromhex(normalized)) == 32
    except ValueError:
        valid = False
    if not valid:
        raise ValueError(f"{label} must contain 64 hexadecimal characters")
    return normalized


@dataclass(frozen=True)
class DiscreteGradientOrbitRule:
    """One caller-qualified scalar-orbit gradient support.

    ``anchor_trace_representative_id`` is the H(curl) trace orbit carrying the
    same physical entity as the scalar orbit.  Selection of that anchor
    activates the scalar orbit and therefore requires every orbit listed in
    ``required_trace_representative_ids``.

    The three hashes are intentionally separate.  The caller remains
    responsible for computing ``gradient_map_sha256`` from the ordered scalar
    basis identity, ordered H(curl) trace basis identity, discrete-gradient
    coefficients, support threshold, and periodic/Floquet pullbacks.  This
    pure layer can validate the identities but cannot reconstruct that digest
    without the physical coefficient map.
    """

    scalar_orbit_id: str
    anchor_trace_representative_id: int
    required_trace_representative_ids: tuple[int, ...]
    scalar_mode_count: int
    discrete_gradient_rank: int
    ordered_scalar_basis_sha256: str
    ordered_trace_basis_sha256: str
    gradient_map_sha256: str
    periodic_orbit_closed: bool
    discrete_gradient_verified: bool
    gradient_map_binds_ordered_basis_identity: bool

    def __post_init__(self) -> None:
        scalar_orbit_id = str(self.scalar_orbit_id)
        if not scalar_orbit_id:
            raise ValueError("scalar orbit id must be non-empty")
        anchor = int(self.anchor_trace_representative_id)
        if anchor < 0:
            raise ValueError("trace orbit representative id must be nonnegative")
        required = tuple(
            sorted(map(int, self.required_trace_representative_ids))
        )
        if not required or len(set(required)) != len(required):
            raise ValueError(
                "gradient support trace representatives must be nonempty "
                "and unique"
            )
        if min(required) < 0:
            raise ValueError(
                "gradient support trace representatives must be nonnegative"
            )
        if anchor not in required:
            raise ValueError(
                "a scalar gradient support must include its H(curl) anchor"
            )
        scalar_mode_count = int(self.scalar_mode_count)
        discrete_gradient_rank = int(self.discrete_gradient_rank)
        if scalar_mode_count <= 0:
            raise ValueError("scalar orbit mode count must be positive")
        if discrete_gradient_rank != scalar_mode_count:
            raise ValueError(
                "discrete gradient must have full scalar-orbit column rank"
            )
        if self.periodic_orbit_closed is not True:
            raise RuntimeError("scalar gradient orbit is not periodic closed")
        if self.discrete_gradient_verified is not True:
            raise RuntimeError("discrete gradient orbit map is not verified")
        if self.gradient_map_binds_ordered_basis_identity is not True:
            raise RuntimeError(
                "gradient map digest does not bind ordered basis identities"
            )
        object.__setattr__(self, "scalar_orbit_id", scalar_orbit_id)
        object.__setattr__(
            self,
            "anchor_trace_representative_id",
            anchor,
        )
        object.__setattr__(
            self,
            "required_trace_representative_ids",
            required,
        )
        object.__setattr__(self, "scalar_mode_count", scalar_mode_count)
        object.__setattr__(
            self,
            "discrete_gradient_rank",
            discrete_gradient_rank,
        )
        for field_name in (
            "ordered_scalar_basis_sha256",
            "ordered_trace_basis_sha256",
            "gradient_map_sha256",
        ):
            object.__setattr__(
                self,
                field_name,
                _validated_sha256(
                    getattr(self, field_name),
                    label=field_name.replace("_", " "),
                ),
            )


@dataclass(frozen=True)
class ExactSequenceTraceSelection:
    """A periodic and exact-sequence-closed trace selection before assembly."""

    seed_trace_representative_ids: tuple[int, ...]
    selected_trace_representative_ids: tuple[int, ...]
    closure_added_trace_representative_ids: tuple[int, ...]
    selected_physical_entity_ids: tuple[int, ...]
    activated_scalar_orbit_ids: tuple[str, ...]
    closure_trigger_scalar_rules: Mapping[int, tuple[str, ...]]
    full3d_base_dofs: int
    full3d_equivalent_increment: int
    full3d_equivalent_dofs: int
    full3d_dof_limit: int | None
    full3d_headroom: int | None
    active_row_increment: int
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.audit.get("pass") is not True:
            raise ValueError("exact-sequence trace closure audit did not pass")
        triggers = {
            int(representative): tuple(map(str, scalar_orbits))
            for representative, scalar_orbits in (
                self.closure_trigger_scalar_rules.items()
            )
        }
        object.__setattr__(
            self,
            "closure_trigger_scalar_rules",
            MappingProxyType(triggers),
        )


@dataclass(frozen=True)
class ExactSequenceClosedP6TraceNumbering:
    """Closed selection plus inactive-row-free numbering."""

    closure: ExactSequenceTraceSelection
    numbering: SelectiveP6TraceNumbering
    audit: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.audit.get("pass") is not True:
            raise ValueError(
                "exact-sequence closed trace numbering audit did not pass"
            )


class ExactSequenceTraceBudgetExceeded(ValueError):
    """The exact-sequence closure cannot fit the caller's Full3D budget."""


def _validated_orbit_catalog(
    orbits: Sequence[PeriodicP6TraceOrbit],
) -> tuple[
    tuple[PeriodicP6TraceOrbit, ...],
    dict[int, PeriodicP6TraceOrbit],
]:
    catalog = tuple(orbits)
    if not catalog:
        raise ValueError("periodic trace orbit catalog must be nonempty")
    by_representative: dict[int, PeriodicP6TraceOrbit] = {}
    physical_members: set[int] = set()
    for orbit in catalog:
        representative = int(orbit.representative_entity_id)
        members = tuple(map(int, orbit.member_entity_ids))
        dimension = int(orbit.missing_mode_count)
        expected = _EXPECTED_MISSING_HCURL_MODES.get(orbit.entity_kind)
        if representative < 0 or not members or min(members) < 0:
            raise ValueError("periodic trace orbit has invalid physical ids")
        if representative not in members:
            raise ValueError(
                "periodic trace orbit representative is not a member"
            )
        if representative in by_representative:
            raise ValueError(
                f"duplicate periodic trace representative {representative}"
            )
        if len(set(members)) != len(members):
            raise ValueError("periodic trace orbit members are duplicated")
        overlap = physical_members.intersection(members)
        if overlap:
            raise ValueError(
                "periodic trace orbit physical members overlap: "
                f"{sorted(overlap)}"
            )
        if expected is None or dimension != expected:
            raise ValueError(
                "periodic trace orbit has the wrong p5-to-p6 shell dimension"
            )
        if (
            orbit.selected
            or orbit.active_row_start is not None
            or orbit.active_row_stop is not None
        ):
            raise RuntimeError(
                "exact-sequence closure requires an unnumbered zero-selected "
                "orbit catalog"
            )
        pullbacks = orbit.representative_to_member_pullbacks
        if set(map(int, pullbacks)) != set(members):
            raise ValueError(
                "periodic trace orbit pullbacks do not cover every member"
            )
        for pullback in pullbacks.values():
            matrix = np.asarray(pullback)
            if matrix.shape != (dimension, dimension):
                raise ValueError(
                    "periodic trace orbit pullback has the wrong shape"
                )
            if not np.all(np.isfinite(matrix)):
                raise FloatingPointError(
                    "periodic trace orbit pullback contains NaN or Inf"
                )
        by_representative[representative] = orbit
        physical_members.update(members)
    ordered = tuple(
        by_representative[key] for key in sorted(by_representative)
    )
    return ordered, by_representative


def _validated_gradient_rules(
    rules: Sequence[DiscreteGradientOrbitRule],
    *,
    orbits_by_representative: Mapping[int, PeriodicP6TraceOrbit],
) -> tuple[DiscreteGradientOrbitRule, ...]:
    rules_tuple = tuple(rules)
    known_representatives = set(orbits_by_representative)
    scalar_ids: set[str] = set()
    anchors: set[int] = set()
    for rule in rules_tuple:
        if rule.scalar_orbit_id in scalar_ids:
            raise ValueError(
                f"duplicate scalar gradient orbit {rule.scalar_orbit_id}"
            )
        anchor = int(rule.anchor_trace_representative_id)
        if anchor in anchors:
            raise ValueError(
                f"multiple scalar gradient rules anchor trace orbit {anchor}"
            )
        if anchor not in known_representatives:
            raise ValueError(
                f"scalar gradient anchor trace orbit is unknown: {anchor}"
            )
        unknown_support = (
            set(rule.required_trace_representative_ids)
            - known_representatives
        )
        if unknown_support:
            raise ValueError(
                "scalar gradient support contains unknown trace orbits: "
                f"{sorted(unknown_support)}"
            )
        anchor_kind = orbits_by_representative[anchor].entity_kind
        expected_scalar_modes = _EXPECTED_MISSING_SCALAR_MODES[anchor_kind]
        if rule.scalar_mode_count != expected_scalar_modes:
            raise ValueError(
                f"p5-to-p6 scalar {anchor_kind} orbit must have "
                f"{expected_scalar_modes} missing modes"
            )
        scalar_ids.add(rule.scalar_orbit_id)
        anchors.add(anchor)
    missing_anchors = known_representatives - anchors
    extra_anchors = anchors - known_representatives
    if missing_anchors or extra_anchors:
        raise RuntimeError(
            "gradient rules do not cover the complete trace orbit catalog: "
            f"missing={sorted(missing_anchors)}, "
            f"extra={sorted(extra_anchors)}"
        )
    return tuple(
        sorted(
            rules_tuple,
            key=lambda rule: (
                rule.anchor_trace_representative_id,
                rule.scalar_orbit_id,
            ),
        )
    )


def close_p6_trace_orbits_under_exact_sequence(
    *,
    orbits: Sequence[PeriodicP6TraceOrbit],
    gradient_rules: Sequence[DiscreteGradientOrbitRule],
    seed_trace_representative_ids: Sequence[int],
    full3d_base_dofs: int,
    full3d_dof_limit: int | None,
) -> ExactSequenceTraceSelection:
    """Close caller-selected periodic trace orbits under discrete gradients.

    Seeds are trace-orbit representative IDs supplied by a separate physical
    selector, normally actual channel DWR.  This function assigns no scores and
    does not reorder or truncate seeds to force a budget pass.
    """

    catalog, by_representative = _validated_orbit_catalog(orbits)
    rules = _validated_gradient_rules(
        gradient_rules,
        orbits_by_representative=by_representative,
    )
    seeds = tuple(sorted(map(int, seed_trace_representative_ids)))
    if len(set(seeds)) != len(seeds):
        raise ValueError("trace orbit seeds are duplicated")
    unknown_seeds = set(seeds) - set(by_representative)
    if unknown_seeds:
        raise ValueError(f"trace orbit seeds are unknown: {sorted(unknown_seeds)}")

    full3d_base_dofs = int(full3d_base_dofs)
    if full3d_base_dofs < 0:
        raise ValueError("Full3D base DoFs must be nonnegative")
    if full3d_dof_limit is not None:
        full3d_dof_limit = int(full3d_dof_limit)
        if full3d_dof_limit < full3d_base_dofs:
            raise ValueError("Full3D DoF limit is below the base space")

    selected = set(seeds)
    closure_added: set[int] = set()
    activated_scalar_orbits: set[str] = set()
    trigger_rules: dict[int, set[str]] = {}
    while True:
        pending: dict[int, set[str]] = {}
        for rule in rules:
            if rule.anchor_trace_representative_id not in selected:
                continue
            activated_scalar_orbits.add(rule.scalar_orbit_id)
            for required in rule.required_trace_representative_ids:
                if required not in selected:
                    pending.setdefault(required, set()).add(
                        rule.scalar_orbit_id
                    )
        if not pending:
            break
        for required, scalar_orbits in pending.items():
            selected.add(required)
            closure_added.add(required)
            trigger_rules.setdefault(required, set()).update(scalar_orbits)

    selected_orbits = tuple(
        by_representative[representative]
        for representative in sorted(selected)
    )
    full3d_increment = int(
        sum(orbit.full3d_equivalent_dof_cost for orbit in selected_orbits)
    )
    active_increment = int(
        sum(orbit.missing_mode_count for orbit in selected_orbits)
    )
    full3d_total = full3d_base_dofs + full3d_increment
    if (
        full3d_dof_limit is not None
        and full3d_total > full3d_dof_limit
    ):
        raise ExactSequenceTraceBudgetExceeded(
            "exact-sequence trace closure exceeds the Full3D DoF limit: "
            f"base={full3d_base_dofs}, increment={full3d_increment}, "
            f"total={full3d_total}, limit={full3d_dof_limit}, "
            f"seeds={list(seeds)}, "
            f"closure_added={sorted(closure_added)}"
        )
    selected_physical = tuple(
        sorted(
            member
            for orbit in selected_orbits
            for member in orbit.member_entity_ids
        )
    )
    headroom = (
        None
        if full3d_dof_limit is None
        else int(full3d_dof_limit - full3d_total)
    )
    frozen_triggers = MappingProxyType(
        {
            representative: tuple(sorted(trigger_rules[representative]))
            for representative in sorted(closure_added)
        }
    )
    checks = MappingProxyType(
        {
            "orbit_catalog_is_periodic_closed_and_unnumbered": True,
            "gradient_rule_catalog_is_complete": True,
            "gradient_rules_are_periodic_closed": True,
            "gradient_maps_are_caller_verified": True,
            "gradient_maps_bind_ordered_basis_identities": True,
            "closure_reached_fixed_point": all(
                set(rule.required_trace_representative_ids).issubset(selected)
                for rule in rules
                if rule.anchor_trace_representative_id in selected
            ),
            "every_closure_added_orbit_has_trigger_rule": (
                set(frozen_triggers) == closure_added
                and all(frozen_triggers.values())
            ),
            "selected_physical_entities_are_unique": (
                len(selected_physical) == len(set(selected_physical))
            ),
            "full3d_budget_pass": (
                full3d_dof_limit is None
                or full3d_total <= full3d_dof_limit
            ),
            "active_rows_not_numbered_by_closure_layer": True,
            "inactive_rows_not_numbered_by_closure_layer": True,
            "sensitivity_or_dwr_scores_not_computed": True,
        }
    )
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "exact-sequence trace closure audit failed: "
            + ", ".join(failed)
        )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.selective-p6-trace-exact-sequence-closure.v1"
            ),
            "status": "periodic_exact_sequence_trace_closure_pass",
            "pass": True,
            "catalog_provenance": "caller_supplied",
            "actual_mesh_verified_by_this_layer": False,
            "actual_dwr_used_by_this_layer": False,
            "seed_selection_authority": (
                "caller_only_no_internal_scoring_or_truncation"
            ),
            "seed_orbit_count": len(seeds),
            "selected_orbit_count": len(selected_orbits),
            "closure_added_orbit_count": len(closure_added),
            "activated_scalar_orbit_count": len(activated_scalar_orbits),
            "catalog_full3d_equivalent_increment": int(
                sum(orbit.full3d_equivalent_dof_cost for orbit in catalog)
            ),
            "catalog_active_row_increment": int(
                sum(orbit.missing_mode_count for orbit in catalog)
            ),
            "selected_full3d_equivalent_increment": full3d_increment,
            "selected_active_row_increment": active_increment,
            "gradient_map_sha256_caller_contract": (
                "each digest binds ordered scalar basis identity, ordered "
                "Hcurl trace basis identity, discrete-gradient coefficients, "
                "support threshold, and periodic/Floquet pullbacks"
            ),
            "gradient_map_digest_binding_is_caller_responsibility": True,
            "gradient_rule_identities": [
                {
                    "scalar_orbit_id": rule.scalar_orbit_id,
                    "anchor_trace_representative_id": (
                        rule.anchor_trace_representative_id
                    ),
                    "required_trace_representative_ids": list(
                        rule.required_trace_representative_ids
                    ),
                    "scalar_mode_count": rule.scalar_mode_count,
                    "discrete_gradient_rank": rule.discrete_gradient_rank,
                    "ordered_scalar_basis_sha256": (
                        rule.ordered_scalar_basis_sha256
                    ),
                    "ordered_trace_basis_sha256": (
                        rule.ordered_trace_basis_sha256
                    ),
                    "gradient_map_sha256": rule.gradient_map_sha256,
                }
                for rule in rules
            ],
            "closure_trigger_scalar_rules": {
                str(representative): list(scalar_orbits)
                for representative, scalar_orbits in frozen_triggers.items()
            },
            "matrix_constructed": False,
            "active_rows_numbered": False,
            "inactive_p6_rows_numbered": False,
            "ordinary_default_changed": False,
            "checks": checks,
        }
    )
    return ExactSequenceTraceSelection(
        seed_trace_representative_ids=seeds,
        selected_trace_representative_ids=tuple(sorted(selected)),
        closure_added_trace_representative_ids=tuple(
            sorted(closure_added)
        ),
        selected_physical_entity_ids=selected_physical,
        activated_scalar_orbit_ids=tuple(
            sorted(activated_scalar_orbits)
        ),
        closure_trigger_scalar_rules=frozen_triggers,
        full3d_base_dofs=full3d_base_dofs,
        full3d_equivalent_increment=full3d_increment,
        full3d_equivalent_dofs=full3d_total,
        full3d_dof_limit=full3d_dof_limit,
        full3d_headroom=headroom,
        active_row_increment=active_increment,
        audit=audit,
    )


def build_exact_sequence_closed_p6_trace_numbering(
    *,
    entities: Sequence[MissingP6TraceEntity],
    periodic_relations: Sequence[PeriodicMissingTraceRelation],
    gradient_rules: Sequence[DiscreteGradientOrbitRule],
    seed_trace_representative_ids: Sequence[int],
    full3d_base_dofs: int,
    active_base_rows: int,
    full3d_dof_limit: int | None,
    tolerance: float = 5.0e-12,
) -> ExactSequenceClosedP6TraceNumbering:
    """Close and budget a selection before assigning any selected rows."""

    catalog = build_selective_p6_trace_numbering(
        entities=entities,
        periodic_relations=periodic_relations,
        selected_entity_ids=(),
        full3d_base_dofs=full3d_base_dofs,
        active_base_rows=active_base_rows,
        full3d_dof_limit=full3d_dof_limit,
        tolerance=tolerance,
    )
    if catalog.entity_active_row_ranges:
        raise RuntimeError("zero-selected orbit catalog allocated active rows")
    closure = close_p6_trace_orbits_under_exact_sequence(
        orbits=catalog.orbits,
        gradient_rules=gradient_rules,
        seed_trace_representative_ids=seed_trace_representative_ids,
        full3d_base_dofs=full3d_base_dofs,
        full3d_dof_limit=full3d_dof_limit,
    )
    numbering = build_selective_p6_trace_numbering(
        entities=entities,
        periodic_relations=periodic_relations,
        selected_entity_ids=closure.selected_physical_entity_ids,
        full3d_base_dofs=full3d_base_dofs,
        active_base_rows=active_base_rows,
        full3d_dof_limit=full3d_dof_limit,
        tolerance=tolerance,
    )
    selected_numbered_representatives = {
        orbit.representative_entity_id
        for orbit in numbering.orbits
        if orbit.selected
    }
    checks = MappingProxyType(
        {
            "closure_selection_matches_numbered_orbits": (
                selected_numbered_representatives
                == set(closure.selected_trace_representative_ids)
            ),
            "full3d_increment_matches_closure": (
                numbering.full3d_equivalent_increment
                == closure.full3d_equivalent_increment
            ),
            "active_row_increment_matches_closure": (
                numbering.active_row_increment
                == closure.active_row_increment
            ),
            "selected_physical_entities_have_rows": (
                set(numbering.entity_active_row_ranges)
                == set(closure.selected_physical_entity_ids)
            ),
            "inactive_physical_entities_have_no_rows": (
                not set(numbering.entity_active_row_ranges).intersection(
                    numbering.inactive_entity_ids
                )
            ),
            "budget_checked_before_selected_numbering": True,
            "full_p6_matrix_not_constructed": True,
            "inactive_p6_rows_not_numbered": True,
        }
    )
    if not all(checks.values()):
        failed = [name for name, passed in checks.items() if not passed]
        raise RuntimeError(
            "exact-sequence closed trace numbering failed: "
            + ", ".join(failed)
        )
    audit = MappingProxyType(
        {
            "schema_version": (
                "task035b.exact-sequence-closed-p6-trace-numbering.v1"
            ),
            "status": (
                "periodic_exact_sequence_closed_inactive_row_free_numbering_pass"
            ),
            "pass": True,
            "closure_schema": closure.audit["schema_version"],
            "numbering_schema": numbering.audit["schema_version"],
            "matrix_constructed": False,
            "inactive_p6_rows_numbered": False,
            "ordinary_default_changed": False,
            "checks": checks,
        }
    )
    return ExactSequenceClosedP6TraceNumbering(
        closure=closure,
        numbering=numbering,
        audit=audit,
    )


__all__ = [
    "DiscreteGradientOrbitRule",
    "ExactSequenceClosedP6TraceNumbering",
    "ExactSequenceTraceBudgetExceeded",
    "ExactSequenceTraceSelection",
    "build_exact_sequence_closed_p6_trace_numbering",
    "close_p6_trace_orbits_under_exact_sequence",
]
