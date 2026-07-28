"""Signed p/h enrichment packets consumed by the pure controller."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from types import MappingProxyType
from typing import Mapping

from .contracts import (
    FORMAL_GOAL_IDS,
    GoalVector,
    blind_tolerance,
)


_ACTION_KINDS = frozenset(
    {"p-up", "h-refine", "p-down", "h-coarsen", "keep"}
)
_SIGNED_EFFECTIVITY_NEAR_ZERO = 1.0e-30
P6_SATURATION_AUTHORITY_SCHEMA = (
    "task035e.p6-saturation-authority.v1"
)
P6_SATURATION_PLAN_SCAN_EVIDENCE_SCHEMA = (
    "task035e.p6-saturation-plan-scan-evidence.v1"
)
P6_SATURATION_MEASURED_EVIDENCE_SCHEMA = (
    "task035e.p7-shadow-saturation-evidence.v1"
)
_P6_SATURATION_STATUSES = frozenset(
    {"measured_pass", "measured_fail", "unknown"}
)
_P6_SATURATION_EVIDENCE_KINDS = frozenset(
    {
        "zero_p6_targets_vacuous",
        "no_p7_shadow_evidence",
        "independent_p7_shadow",
    }
)
H_LEVEL3_SATURATION_AUTHORITY_SCHEMA = (
    "task035e.h-level3-saturation-authority.v1"
)
H_LEVEL3_SATURATION_PLAN_SCAN_EVIDENCE_SCHEMA = (
    "task035e.h-level3-saturation-plan-scan-evidence.v1"
)
H_LEVEL3_SATURATION_MEASURED_EVIDENCE_SCHEMA = (
    "task035e.level3-h-saturation-coverage.v1"
)
_H_LEVEL3_SATURATION_STATUSES = frozenset(
    {"measured_pass", "measured_fail", "unknown"}
)
_H_LEVEL3_SATURATION_EVIDENCE_KINDS = frozenset(
    {
        "zero_level2_targets_vacuous",
        "no_independent_global_level3_evidence",
        "independent_global_level3_shadow",
    }
)
_H_LEVEL3_PRODUCTION_MAXIMUM_LEVEL = 2
_H_LEVEL3_SHADOW_MAXIMUM_LEVEL = 3
_H_LEVEL3_NORMALIZED_LIMIT = 0.5


def dwr_endpoint_sign_consistent(
    predicted: Mapping[str, float],
    *,
    current: GoalVector,
    shadow: GoalVector,
) -> bool:
    """Return whether signed DWR predictions avoid endpoint sign reversals.

    DWR is an estimator, so its magnitude is not required to equal the actual
    one-step shadow delta.  A pair whose two magnitudes are both at most
    ``1e-30`` is neutral.  A one-sided near-zero pair remains neutral at this
    packet-construction layer; the stricter post-PDE effectivity bridge
    classifies a near-zero actual endpoint with non-negligible prediction as a
    controlled negative.  Any pair with two non-negligible opposite signs is
    inconsistent.
    """

    if set(predicted) != set(FORMAL_GOAL_IDS):
        raise ValueError(
            "signed DWR mapping must contain the complete formal inventory"
        )
    current_values = current.by_id
    shadow_values = shadow.by_id
    for goal_id in FORMAL_GOAL_IDS:
        prediction = float(predicted[goal_id])
        endpoint_delta = shadow_values[goal_id] - current_values[goal_id]
        if not math.isfinite(prediction):
            raise ValueError(f"DWR delta for {goal_id} must be finite")
        prediction_zero = (
            abs(prediction) <= _SIGNED_EFFECTIVITY_NEAR_ZERO
        )
        endpoint_zero = (
            abs(endpoint_delta) <= _SIGNED_EFFECTIVITY_NEAR_ZERO
        )
        if prediction_zero and endpoint_zero:
            continue
        if (
            not prediction_zero
            and not endpoint_zero
            and math.copysign(1.0, prediction)
            != math.copysign(1.0, endpoint_delta)
        ):
            return False
    return True


def _opaque_id(value: str, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 160
        or any(character not in "abcdefghijklmnopqrstuvwxyz"
               "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.:-" for character in value)
    ):
        raise ValueError(f"{label} is not an opaque identifier")
    return value


def _sha256(value: str, *, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError(f"{label} must be a lowercase SHA-256")
    return value


def _canonical_json_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def _canonical_target_ids(
    values: tuple[str, ...],
    *,
    label: str,
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise ValueError(f"{label} must be a tuple")
    for value in values:
        _opaque_id(value, label=label)
        if not value.startswith("cell:r"):
            raise ValueError(
                f"{label} must use canonical Task035e cell target IDs"
            )
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} must be unique and canonically sorted")
    return values


def p6_target_ids_sha256(target_ids: tuple[str, ...]) -> str:
    """Hash one canonical p6 leaf inventory without losing its zero case."""

    canonical = _canonical_target_ids(
        target_ids,
        label="p6 target ID",
    )
    return _canonical_json_sha256(
        {"canonical_target_ids": list(canonical)}
    )


def _canonical_h_level3_orbit_ids(
    values: tuple[str, ...],
    *,
    label: str,
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise ValueError(f"{label} must be a tuple")
    for value in values:
        _opaque_id(value, label=label)
        if not value.startswith("h3-orbit-"):
            raise ValueError(
                f"{label} must use canonical level3 periodic orbit IDs"
            )
    if values != tuple(sorted(set(values))):
        raise ValueError(f"{label} must be unique and canonically sorted")
    return values


def h_level3_orbit_ids_sha256(orbit_ids: tuple[str, ...]) -> str:
    """Hash one canonical level-three periodic-orbit inventory."""

    canonical = _canonical_h_level3_orbit_ids(
        orbit_ids,
        label="level3 periodic orbit ID",
    )
    return _canonical_json_sha256(
        {"canonical_orbit_ids": list(canonical)}
    )


@dataclass(frozen=True, slots=True)
class P6SaturationAuthority:
    """Closed p6 saturation evidence used only by the freeze decision.

    A production p6 leaf has no in-family ``p-up`` action.  It may therefore
    look quiet even though no higher-order shadow has measured its remaining
    error.  This authority distinguishes a real p7-shadow measurement from
    that absence of evidence.  It never makes p7 selectable as a production
    degree.
    """

    status: str
    current_plan_file_sha256: str
    current_mesh_forest_sha256: str
    current_degree_map_sha256: str
    p6_target_ids: tuple[str, ...]
    p6_target_ids_sha256: str
    covered_target_ids: tuple[str, ...]
    covered_target_ids_sha256: str
    coverage_complete: bool
    shadow_only: bool
    selectable_as_production: bool
    normalized_max: float | None
    evidence_kind: str
    evidence_sha256: str
    authority_sha256: str

    def __post_init__(self) -> None:
        if self.status not in _P6_SATURATION_STATUSES:
            raise ValueError("unsupported p6 saturation status")
        if self.evidence_kind not in _P6_SATURATION_EVIDENCE_KINDS:
            raise ValueError("unsupported p6 saturation evidence kind")
        for name in (
            "current_plan_file_sha256",
            "current_mesh_forest_sha256",
            "current_degree_map_sha256",
            "p6_target_ids_sha256",
            "covered_target_ids_sha256",
            "evidence_sha256",
            "authority_sha256",
        ):
            _sha256(getattr(self, name), label=name)
        targets = _canonical_target_ids(
            self.p6_target_ids,
            label="p6 target ID",
        )
        covered = _canonical_target_ids(
            self.covered_target_ids,
            label="covered p6 target ID",
        )
        if self.p6_target_ids_sha256 != p6_target_ids_sha256(targets):
            raise ValueError("p6 target inventory SHA-256 differs")
        if self.covered_target_ids_sha256 != p6_target_ids_sha256(covered):
            raise ValueError("covered p6 target inventory SHA-256 differs")
        if not set(covered).issubset(targets):
            raise ValueError("p6 saturation coverage contains non-target leaves")
        expected_complete = covered == targets
        if self.coverage_complete is not expected_complete:
            raise ValueError("p6 saturation coverage flag differs from targets")
        if self.shadow_only is not True:
            raise ValueError("p6 saturation evidence must remain shadow-only")
        if self.selectable_as_production is not False:
            raise ValueError(
                "p7 saturation evidence cannot select production degree 7"
            )
        if self.normalized_max is not None:
            value = float(self.normalized_max)
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(
                    "p6 saturation normalized maximum must be nonnegative"
                )
            object.__setattr__(self, "normalized_max", value)
        if not targets:
            if (
                self.status != "measured_pass"
                or not self.coverage_complete
                or covered
                or self.normalized_max != 0.0
                or self.evidence_kind != "zero_p6_targets_vacuous"
            ):
                raise ValueError(
                    "zero-target p6 saturation must be an explicit vacuous pass"
                )
        elif self.status == "unknown":
            if (
                covered
                or self.coverage_complete
                or self.normalized_max is not None
                or self.evidence_kind != "no_p7_shadow_evidence"
            ):
                raise ValueError(
                    "unmeasured p6 targets cannot receive saturation credit"
                )
        else:
            if (
                not self.coverage_complete
                or self.normalized_max is None
                or self.evidence_kind != "independent_p7_shadow"
            ):
                raise ValueError(
                    "measured p6 saturation requires complete independent "
                    "p7-shadow evidence"
                )
            expected_status = (
                "measured_pass"
                if self.normalized_max <= 0.5
                else "measured_fail"
            )
            if self.status != expected_status:
                raise ValueError(
                    "p6 saturation status differs from normalized maximum"
                )
        expected_sha = _p6_saturation_authority_sha256(self)
        if self.authority_sha256 != expected_sha:
            raise ValueError("p6 saturation authority SHA-256 differs")

    @property
    def p6_target_count(self) -> int:
        return len(self.p6_target_ids)

    @property
    def covered_target_count(self) -> int:
        return len(self.covered_target_ids)

    @property
    def freeze_passed(self) -> bool:
        return (
            self.status == "measured_pass"
            and self.coverage_complete
        )


def _p6_saturation_unsigned_payload(
    authority: P6SaturationAuthority,
) -> dict[str, object]:
    return {
        "schema_version": P6_SATURATION_AUTHORITY_SCHEMA,
        "status": authority.status,
        "current_plan_file_sha256": authority.current_plan_file_sha256,
        "current_mesh_forest_sha256": (
            authority.current_mesh_forest_sha256
        ),
        "current_degree_map_sha256": authority.current_degree_map_sha256,
        "p6_target_count": authority.p6_target_count,
        "p6_target_ids": list(authority.p6_target_ids),
        "p6_target_ids_sha256": authority.p6_target_ids_sha256,
        "covered_target_count": authority.covered_target_count,
        "covered_target_ids": list(authority.covered_target_ids),
        "covered_target_ids_sha256": (
            authority.covered_target_ids_sha256
        ),
        "coverage_complete": authority.coverage_complete,
        "shadow_only": authority.shadow_only,
        "selectable_as_production": authority.selectable_as_production,
        "normalized_max": authority.normalized_max,
        "evidence_kind": authority.evidence_kind,
        "evidence_sha256": authority.evidence_sha256,
    }


def _p6_saturation_authority_sha256(
    authority: P6SaturationAuthority,
) -> str:
    return _canonical_json_sha256(
        _p6_saturation_unsigned_payload(authority)
    )


def p6_saturation_authority_payload(
    authority: P6SaturationAuthority,
) -> dict[str, object]:
    """Serialize one authority using a closed, independently replayable schema."""

    return {
        **_p6_saturation_unsigned_payload(authority),
        "authority_sha256": authority.authority_sha256,
    }


def build_unmeasured_p6_saturation_authority(
    *,
    p6_target_ids: tuple[str, ...],
    current_plan_file_sha256: str,
    current_mesh_forest_sha256: str,
    current_degree_map_sha256: str,
) -> P6SaturationAuthority:
    """Build the only authority available before an independent p7 shadow.

    A zero-target plan receives an explicit vacuous pass.  Any actual p6 leaf
    remains ``unknown`` and receives neither zero-error nor weak-lane credit.
    """

    targets = _canonical_target_ids(
        p6_target_ids,
        label="p6 target ID",
    )
    for name, value in (
        ("current_plan_file_sha256", current_plan_file_sha256),
        ("current_mesh_forest_sha256", current_mesh_forest_sha256),
        ("current_degree_map_sha256", current_degree_map_sha256),
    ):
        _sha256(value, label=name)
    target_sha = p6_target_ids_sha256(targets)
    covered: tuple[str, ...] = ()
    covered_sha = p6_target_ids_sha256(covered)
    zero_targets = not targets
    evidence = {
        "schema_version": P6_SATURATION_PLAN_SCAN_EVIDENCE_SCHEMA,
        "status": (
            "zero_p6_targets_vacuous"
            if zero_targets
            else "no_p7_shadow_evidence"
        ),
        "current_plan_file_sha256": current_plan_file_sha256,
        "current_mesh_forest_sha256": current_mesh_forest_sha256,
        "current_degree_map_sha256": current_degree_map_sha256,
        "p6_target_count": len(targets),
        "p6_target_ids_sha256": target_sha,
        "p7_shadow_solve_performed": False,
        "accuracy_credit": zero_targets,
    }
    provisional = object.__new__(P6SaturationAuthority)
    values = {
        "status": "measured_pass" if zero_targets else "unknown",
        "current_plan_file_sha256": current_plan_file_sha256,
        "current_mesh_forest_sha256": current_mesh_forest_sha256,
        "current_degree_map_sha256": current_degree_map_sha256,
        "p6_target_ids": targets,
        "p6_target_ids_sha256": target_sha,
        "covered_target_ids": covered,
        "covered_target_ids_sha256": covered_sha,
        "coverage_complete": zero_targets,
        "shadow_only": True,
        "selectable_as_production": False,
        "normalized_max": 0.0 if zero_targets else None,
        "evidence_kind": (
            "zero_p6_targets_vacuous"
            if zero_targets
            else "no_p7_shadow_evidence"
        ),
        "evidence_sha256": _canonical_json_sha256(evidence),
        "authority_sha256": "",
    }
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    values["authority_sha256"] = _p6_saturation_authority_sha256(
        provisional
    )
    return P6SaturationAuthority(**values)


_P6_SATURATION_PAYLOAD_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "current_plan_file_sha256",
        "current_mesh_forest_sha256",
        "current_degree_map_sha256",
        "p6_target_count",
        "p6_target_ids",
        "p6_target_ids_sha256",
        "covered_target_count",
        "covered_target_ids",
        "covered_target_ids_sha256",
        "coverage_complete",
        "shadow_only",
        "selectable_as_production",
        "normalized_max",
        "evidence_kind",
        "evidence_sha256",
        "authority_sha256",
    }
)


def _p6_saturation_authority_from_payload(
    payload: Mapping[str, object],
    *,
    expected_plan_file_sha256: str | None = None,
    expected_mesh_forest_sha256: str | None = None,
    expected_degree_map_sha256: str | None = None,
    independent_measured_evidence_sha256: str | None = None,
    require_independent_measured_evidence: bool,
) -> P6SaturationAuthority:
    if not isinstance(payload, Mapping) or set(payload) != set(
        _P6_SATURATION_PAYLOAD_KEYS
    ):
        raise ValueError("p6 saturation authority uses an open schema")
    if payload["schema_version"] != P6_SATURATION_AUTHORITY_SCHEMA:
        raise ValueError("unsupported p6 saturation authority schema")
    for name in ("p6_target_ids", "covered_target_ids"):
        value = payload[name]
        if not isinstance(value, list) or any(
            not isinstance(item, str) for item in value
        ):
            raise ValueError(f"{name} must be a string array")
    if (
        type(payload["p6_target_count"]) is not int
        or type(payload["covered_target_count"]) is not int
    ):
        raise ValueError("p6 saturation counts must be integers")
    authority = P6SaturationAuthority(
        status=str(payload["status"]),
        current_plan_file_sha256=str(
            payload["current_plan_file_sha256"]
        ),
        current_mesh_forest_sha256=str(
            payload["current_mesh_forest_sha256"]
        ),
        current_degree_map_sha256=str(
            payload["current_degree_map_sha256"]
        ),
        p6_target_ids=tuple(payload["p6_target_ids"]),
        p6_target_ids_sha256=str(payload["p6_target_ids_sha256"]),
        covered_target_ids=tuple(payload["covered_target_ids"]),
        covered_target_ids_sha256=str(
            payload["covered_target_ids_sha256"]
        ),
        coverage_complete=payload["coverage_complete"],
        shadow_only=payload["shadow_only"],
        selectable_as_production=payload["selectable_as_production"],
        normalized_max=(
            None
            if payload["normalized_max"] is None
            else float(payload["normalized_max"])
        ),
        evidence_kind=str(payload["evidence_kind"]),
        evidence_sha256=str(payload["evidence_sha256"]),
        authority_sha256=str(payload["authority_sha256"]),
    )
    if payload["p6_target_count"] != authority.p6_target_count:
        raise ValueError("p6 saturation target count differs from its list")
    if payload["covered_target_count"] != authority.covered_target_count:
        raise ValueError("p6 saturation covered count differs from its list")
    for expected, observed, label in (
        (
            expected_plan_file_sha256,
            authority.current_plan_file_sha256,
            "p6 saturation plan file",
        ),
        (
            expected_mesh_forest_sha256,
            authority.current_mesh_forest_sha256,
            "p6 saturation mesh forest",
        ),
        (
            expected_degree_map_sha256,
            authority.current_degree_map_sha256,
            "p6 saturation degree map",
        ),
    ):
        if expected is not None and expected != observed:
            raise ValueError(f"{label} SHA-256 differs")
    if (
        authority.p6_target_count
        and authority.status in {"measured_pass", "measured_fail"}
        and require_independent_measured_evidence
    ):
        if (
            independent_measured_evidence_sha256 is None
            or _sha256(
                independent_measured_evidence_sha256,
                label="independent p7-shadow evidence SHA-256",
            )
            != authority.evidence_sha256
        ):
            raise ValueError(
                "non-vacuous measured p6 saturation is not bound to an "
                "independently loaded p7-shadow evidence artifact"
            )
    return authority


def p6_saturation_authority_from_payload(
    payload: Mapping[str, object],
    *,
    expected_plan_file_sha256: str | None = None,
    expected_mesh_forest_sha256: str | None = None,
    expected_degree_map_sha256: str | None = None,
    independent_measured_evidence_sha256: str | None = None,
) -> P6SaturationAuthority:
    """Strictly load p6 saturation without accepting a caller-supplied bool.

    Future non-vacuous measured results must supply the independently loaded
    p7-shadow artifact SHA through ``independent_measured_evidence_sha256``.
    Current producers intentionally emit only ``unknown`` or a zero-target
    vacuous pass.
    """

    return _p6_saturation_authority_from_payload(
        payload,
        expected_plan_file_sha256=expected_plan_file_sha256,
        expected_mesh_forest_sha256=expected_mesh_forest_sha256,
        expected_degree_map_sha256=expected_degree_map_sha256,
        independent_measured_evidence_sha256=(
            independent_measured_evidence_sha256
        ),
        require_independent_measured_evidence=True,
    )


def _replay_p6_saturation_authority_from_payload(
    payload: Mapping[str, object],
) -> P6SaturationAuthority:
    """Replay an authority whose evidence binding was checked at ingestion."""

    return _p6_saturation_authority_from_payload(
        payload,
        require_independent_measured_evidence=False,
    )


@dataclass(frozen=True, slots=True)
class HLevel3SaturationAuthority:
    """Closed level2-to-level3 h-saturation evidence for the freeze gate.

    Production Task035e meshes stop at dyadic level two.  Consequently, a
    level-two leaf has no ordinary ``h-refine`` action even when unresolved
    h-error remains.  This authority inventories every such leaf and every
    complete x/y periodic orbit, then distinguishes a real global level-three
    shadow measurement from the absence of evidence.  It never makes level
    three selectable or numberable in the production system.
    """

    status: str
    current_plan_file_sha256: str
    current_mesh_forest_sha256: str
    current_degree_map_sha256: str
    level_two_target_ids: tuple[str, ...]
    level_two_target_ids_sha256: str
    periodic_orbit_ids: tuple[str, ...]
    periodic_orbit_ids_sha256: str
    orbit_catalog_sha256: str
    covered_target_ids: tuple[str, ...]
    covered_target_ids_sha256: str
    covered_orbit_ids: tuple[str, ...]
    covered_orbit_ids_sha256: str
    coverage_complete: bool
    production_maximum_level: int
    shadow_maximum_level: int
    shadow_only: bool
    selectable_as_production: bool
    normalized_max: float | None
    normalized_limit: float
    evidence_kind: str
    evidence_sha256: str
    authority_sha256: str

    def __post_init__(self) -> None:
        if self.status not in _H_LEVEL3_SATURATION_STATUSES:
            raise ValueError("unsupported level3 h-saturation status")
        if self.evidence_kind not in _H_LEVEL3_SATURATION_EVIDENCE_KINDS:
            raise ValueError("unsupported level3 h-saturation evidence kind")
        for name in (
            "current_plan_file_sha256",
            "current_mesh_forest_sha256",
            "current_degree_map_sha256",
            "level_two_target_ids_sha256",
            "periodic_orbit_ids_sha256",
            "orbit_catalog_sha256",
            "covered_target_ids_sha256",
            "covered_orbit_ids_sha256",
            "evidence_sha256",
            "authority_sha256",
        ):
            _sha256(getattr(self, name), label=name)
        targets = _canonical_target_ids(
            self.level_two_target_ids,
            label="level-two h-saturation target ID",
        )
        covered_targets = _canonical_target_ids(
            self.covered_target_ids,
            label="covered level-two h-saturation target ID",
        )
        orbits = _canonical_h_level3_orbit_ids(
            self.periodic_orbit_ids,
            label="level-three h-saturation orbit ID",
        )
        covered_orbits = _canonical_h_level3_orbit_ids(
            self.covered_orbit_ids,
            label="covered level-three h-saturation orbit ID",
        )
        if self.level_two_target_ids_sha256 != p6_target_ids_sha256(
            targets
        ):
            raise ValueError("level-two h-saturation target SHA-256 differs")
        if self.covered_target_ids_sha256 != p6_target_ids_sha256(
            covered_targets
        ):
            raise ValueError(
                "covered level-two h-saturation target SHA-256 differs"
            )
        if self.periodic_orbit_ids_sha256 != h_level3_orbit_ids_sha256(
            orbits
        ):
            raise ValueError("level-three h-saturation orbit SHA-256 differs")
        if self.covered_orbit_ids_sha256 != h_level3_orbit_ids_sha256(
            covered_orbits
        ):
            raise ValueError(
                "covered level-three h-saturation orbit SHA-256 differs"
            )
        if not set(covered_targets).issubset(targets):
            raise ValueError(
                "level3 h-saturation coverage contains non-target leaves"
            )
        if not set(covered_orbits).issubset(orbits):
            raise ValueError(
                "level3 h-saturation coverage contains unknown orbits"
            )
        expected_complete = (
            covered_targets == targets and covered_orbits == orbits
        )
        if self.coverage_complete is not expected_complete:
            raise ValueError(
                "level3 h-saturation coverage flag differs from inventories"
            )
        if (
            self.production_maximum_level
            != _H_LEVEL3_PRODUCTION_MAXIMUM_LEVEL
            or self.shadow_maximum_level != _H_LEVEL3_SHADOW_MAXIMUM_LEVEL
        ):
            raise ValueError(
                "level3 h-saturation changed the production/shadow level cap"
            )
        if self.shadow_only is not True:
            raise ValueError(
                "level3 h-saturation evidence must remain shadow-only"
            )
        if self.selectable_as_production is not False:
            raise ValueError(
                "level3 h-saturation cannot select a production level3 mesh"
            )
        normalized_limit = float(self.normalized_limit)
        if (
            not math.isfinite(normalized_limit)
            or normalized_limit != _H_LEVEL3_NORMALIZED_LIMIT
        ):
            raise ValueError(
                "level3 h-saturation normalized limit must remain 0.5"
            )
        object.__setattr__(self, "normalized_limit", normalized_limit)
        if self.normalized_max is not None:
            normalized_max = float(self.normalized_max)
            if not math.isfinite(normalized_max) or normalized_max < 0.0:
                raise ValueError(
                    "level3 h-saturation normalized maximum must be "
                    "nonnegative"
                )
            object.__setattr__(self, "normalized_max", normalized_max)
        if not targets:
            if (
                orbits
                or covered_targets
                or covered_orbits
                or self.status != "measured_pass"
                or not self.coverage_complete
                or self.normalized_max != 0.0
                or self.evidence_kind
                != "zero_level2_targets_vacuous"
            ):
                raise ValueError(
                    "zero-target level3 h-saturation must be an explicit "
                    "vacuous pass"
                )
        elif not orbits:
            raise ValueError(
                "nonempty level-two targets require periodic orbit coverage"
            )
        elif self.status == "unknown":
            if (
                covered_targets
                or covered_orbits
                or self.coverage_complete
                or self.normalized_max is not None
                or self.evidence_kind
                != "no_independent_global_level3_evidence"
            ):
                raise ValueError(
                    "unmeasured level-two targets cannot receive "
                    "h-saturation credit"
                )
        else:
            if (
                not self.coverage_complete
                or self.normalized_max is None
                or self.evidence_kind
                != "independent_global_level3_shadow"
            ):
                raise ValueError(
                    "measured h-saturation requires complete independent "
                    "target and orbit coverage"
                )
            expected_status = (
                "measured_pass"
                if self.normalized_max <= self.normalized_limit
                else "measured_fail"
            )
            if self.status != expected_status:
                raise ValueError(
                    "level3 h-saturation status differs from normalized "
                    "maximum"
                )
        if self.authority_sha256 != _h_level3_saturation_authority_sha256(
            self
        ):
            raise ValueError("level3 h-saturation authority SHA-256 differs")

    @property
    def level_two_target_count(self) -> int:
        return len(self.level_two_target_ids)

    @property
    def periodic_orbit_count(self) -> int:
        return len(self.periodic_orbit_ids)

    @property
    def covered_target_count(self) -> int:
        return len(self.covered_target_ids)

    @property
    def covered_orbit_count(self) -> int:
        return len(self.covered_orbit_ids)

    @property
    def freeze_passed(self) -> bool:
        return self.status == "measured_pass" and self.coverage_complete


def _h_level3_saturation_unsigned_payload(
    authority: HLevel3SaturationAuthority,
) -> dict[str, object]:
    return {
        "schema_version": H_LEVEL3_SATURATION_AUTHORITY_SCHEMA,
        "status": authority.status,
        "current_plan_file_sha256": authority.current_plan_file_sha256,
        "current_mesh_forest_sha256": (
            authority.current_mesh_forest_sha256
        ),
        "current_degree_map_sha256": authority.current_degree_map_sha256,
        "level_two_target_count": authority.level_two_target_count,
        "level_two_target_ids": list(authority.level_two_target_ids),
        "level_two_target_ids_sha256": (
            authority.level_two_target_ids_sha256
        ),
        "periodic_orbit_count": authority.periodic_orbit_count,
        "periodic_orbit_ids": list(authority.periodic_orbit_ids),
        "periodic_orbit_ids_sha256": authority.periodic_orbit_ids_sha256,
        "orbit_catalog_sha256": authority.orbit_catalog_sha256,
        "covered_target_count": authority.covered_target_count,
        "covered_target_ids": list(authority.covered_target_ids),
        "covered_target_ids_sha256": (
            authority.covered_target_ids_sha256
        ),
        "covered_orbit_count": authority.covered_orbit_count,
        "covered_orbit_ids": list(authority.covered_orbit_ids),
        "covered_orbit_ids_sha256": authority.covered_orbit_ids_sha256,
        "coverage_complete": authority.coverage_complete,
        "production_maximum_level": authority.production_maximum_level,
        "shadow_maximum_level": authority.shadow_maximum_level,
        "shadow_only": authority.shadow_only,
        "selectable_as_production": authority.selectable_as_production,
        "normalized_max": authority.normalized_max,
        "normalized_limit": authority.normalized_limit,
        "evidence_kind": authority.evidence_kind,
        "evidence_sha256": authority.evidence_sha256,
    }


def _h_level3_saturation_authority_sha256(
    authority: HLevel3SaturationAuthority,
) -> str:
    return _canonical_json_sha256(
        _h_level3_saturation_unsigned_payload(authority)
    )


def h_level3_saturation_authority_payload(
    authority: HLevel3SaturationAuthority,
) -> dict[str, object]:
    """Serialize one closed level3 h-saturation authority."""

    return {
        **_h_level3_saturation_unsigned_payload(authority),
        "authority_sha256": authority.authority_sha256,
    }


def _new_h_level3_saturation_authority(
    values: dict[str, object],
) -> HLevel3SaturationAuthority:
    provisional = object.__new__(HLevel3SaturationAuthority)
    for name, value in values.items():
        object.__setattr__(provisional, name, value)
    object.__setattr__(
        provisional,
        "authority_sha256",
        _h_level3_saturation_authority_sha256(provisional),
    )
    return HLevel3SaturationAuthority(
        **{
            name: getattr(provisional, name)
            for name in HLevel3SaturationAuthority.__dataclass_fields__
        }
    )


def build_unmeasured_h_level3_saturation_authority(
    *,
    level_two_target_ids: tuple[str, ...],
    periodic_orbit_ids: tuple[str, ...],
    orbit_catalog_sha256: str,
    current_plan_file_sha256: str,
    current_mesh_forest_sha256: str,
    current_degree_map_sha256: str,
) -> HLevel3SaturationAuthority:
    """Build the fail-closed plan-scan authority before a global shadow."""

    targets = _canonical_target_ids(
        level_two_target_ids,
        label="level-two h-saturation target ID",
    )
    orbits = _canonical_h_level3_orbit_ids(
        periodic_orbit_ids,
        label="level-three h-saturation orbit ID",
    )
    if bool(targets) is not bool(orbits):
        raise ValueError(
            "level-two targets and periodic h-saturation orbits must both "
            "be empty or both be nonempty"
        )
    for name, value in (
        ("orbit_catalog_sha256", orbit_catalog_sha256),
        ("current_plan_file_sha256", current_plan_file_sha256),
        ("current_mesh_forest_sha256", current_mesh_forest_sha256),
        ("current_degree_map_sha256", current_degree_map_sha256),
    ):
        _sha256(value, label=name)
    target_sha = p6_target_ids_sha256(targets)
    orbit_sha = h_level3_orbit_ids_sha256(orbits)
    empty_target_sha = p6_target_ids_sha256(())
    empty_orbit_sha = h_level3_orbit_ids_sha256(())
    zero_targets = not targets
    evidence = {
        "schema_version": H_LEVEL3_SATURATION_PLAN_SCAN_EVIDENCE_SCHEMA,
        "status": (
            "zero_level2_targets_vacuous"
            if zero_targets
            else "no_independent_global_level3_evidence"
        ),
        "current_plan_file_sha256": current_plan_file_sha256,
        "current_mesh_forest_sha256": current_mesh_forest_sha256,
        "current_degree_map_sha256": current_degree_map_sha256,
        "level_two_target_count": len(targets),
        "level_two_target_ids_sha256": target_sha,
        "periodic_orbit_count": len(orbits),
        "periodic_orbit_ids_sha256": orbit_sha,
        "orbit_catalog_sha256": orbit_catalog_sha256,
        "global_level3_shadow_performed": False,
        "production_maximum_level": _H_LEVEL3_PRODUCTION_MAXIMUM_LEVEL,
        "shadow_maximum_level": _H_LEVEL3_SHADOW_MAXIMUM_LEVEL,
        "accuracy_credit": zero_targets,
    }
    return _new_h_level3_saturation_authority(
        {
            "status": "measured_pass" if zero_targets else "unknown",
            "current_plan_file_sha256": current_plan_file_sha256,
            "current_mesh_forest_sha256": current_mesh_forest_sha256,
            "current_degree_map_sha256": current_degree_map_sha256,
            "level_two_target_ids": targets,
            "level_two_target_ids_sha256": target_sha,
            "periodic_orbit_ids": orbits,
            "periodic_orbit_ids_sha256": orbit_sha,
            "orbit_catalog_sha256": orbit_catalog_sha256,
            "covered_target_ids": (),
            "covered_target_ids_sha256": empty_target_sha,
            "covered_orbit_ids": (),
            "covered_orbit_ids_sha256": empty_orbit_sha,
            "coverage_complete": zero_targets,
            "production_maximum_level": _H_LEVEL3_PRODUCTION_MAXIMUM_LEVEL,
            "shadow_maximum_level": _H_LEVEL3_SHADOW_MAXIMUM_LEVEL,
            "shadow_only": True,
            "selectable_as_production": False,
            "normalized_max": 0.0 if zero_targets else None,
            "normalized_limit": _H_LEVEL3_NORMALIZED_LIMIT,
            "evidence_kind": (
                "zero_level2_targets_vacuous"
                if zero_targets
                else "no_independent_global_level3_evidence"
            ),
            "evidence_sha256": _canonical_json_sha256(evidence),
            "authority_sha256": "",
        }
    )


def build_measured_h_level3_saturation_authority(
    *,
    coverage_payload: Mapping[str, object],
    independent_measured_evidence_sha256: str,
    current_plan_file_sha256: str,
    current_mesh_forest_sha256: str,
    current_degree_map_sha256: str,
) -> HLevel3SaturationAuthority:
    """Close a measured authority from one independent all-orbit artifact."""

    if not isinstance(coverage_payload, Mapping):
        raise ValueError("level3 h-saturation coverage must be a mapping")
    coverage = dict(coverage_payload)
    if (
        coverage.get("schema_version")
        != H_LEVEL3_SATURATION_MEASURED_EVIDENCE_SCHEMA
    ):
        raise ValueError("unsupported level3 h-saturation evidence schema")
    coverage_sha = coverage.pop("coverage_sha256", None)
    if (
        _sha256(
            coverage_sha,
            label="level3 h-saturation coverage SHA-256",
        )
        != _canonical_json_sha256(coverage)
    ):
        raise ValueError("level3 h-saturation coverage self-hash differs")
    if (
        _sha256(
            independent_measured_evidence_sha256,
            label="independent level3 h-saturation evidence SHA-256",
        )
        != coverage_sha
    ):
        raise ValueError(
            "level3 h-saturation authority is not bound to the independently "
            "loaded coverage artifact"
        )
    required = (
        "level_two_target_ids",
        "level_two_target_ids_sha256",
        "expected_orbit_ids",
        "expected_orbit_ids_sha256",
        "covered_target_ids",
        "covered_target_ids_sha256",
        "covered_orbit_ids",
        "covered_orbit_ids_sha256",
        "orbit_catalog_sha256",
        "normalized_max",
        "saturation_normalized_limit",
    )
    if any(name not in coverage for name in required):
        raise ValueError(
            "level3 h-saturation coverage lacks target/orbit evidence"
        )
    for name in (
        "level_two_target_ids",
        "expected_orbit_ids",
        "covered_target_ids",
        "covered_orbit_ids",
    ):
        if not isinstance(coverage[name], list) or any(
            not isinstance(value, str) for value in coverage[name]
        ):
            raise ValueError(f"coverage {name} must be a string array")
    targets = _canonical_target_ids(
        tuple(coverage["level_two_target_ids"]),
        label="level-two h-saturation target ID",
    )
    orbits = _canonical_h_level3_orbit_ids(
        tuple(coverage["expected_orbit_ids"]),
        label="level-three h-saturation orbit ID",
    )
    covered_targets = _canonical_target_ids(
        tuple(coverage["covered_target_ids"]),
        label="covered level-two h-saturation target ID",
    )
    covered_orbits = _canonical_h_level3_orbit_ids(
        tuple(coverage["covered_orbit_ids"]),
        label="covered level-three h-saturation orbit ID",
    )
    normalized_max = float(coverage["normalized_max"])
    normalized_limit = float(coverage["saturation_normalized_limit"])
    formal_status = coverage.get("formal_h_saturation_status")
    expected_status = (
        "measured_pass"
        if normalized_max <= _H_LEVEL3_NORMALIZED_LIMIT
        else "measured_fail"
    )
    semantic_checks = (
        bool(targets),
        bool(orbits),
        covered_targets == targets,
        covered_orbits == orbits,
        coverage["level_two_target_ids_sha256"]
        == p6_target_ids_sha256(targets),
        coverage["expected_orbit_ids_sha256"]
        == h_level3_orbit_ids_sha256(orbits),
        coverage["covered_target_ids_sha256"]
        == p6_target_ids_sha256(covered_targets),
        coverage["covered_orbit_ids_sha256"]
        == h_level3_orbit_ids_sha256(covered_orbits),
        coverage.get("all_level_two_orbits_covered") is True,
        coverage.get("all_orbit_evidence_formally_complete") is True,
        coverage.get("controller_consumption_eligible") is True,
        coverage.get("production_plan_mutated") is False,
        coverage.get("production_level_three_selectable") is False,
        coverage.get("production_level_three_rows_numbered") is False,
        normalized_limit == _H_LEVEL3_NORMALIZED_LIMIT,
        formal_status == expected_status,
        coverage.get(expected_status) is True,
    )
    if not all(semantic_checks):
        raise ValueError(
            "level3 h-saturation coverage is incomplete or semantically "
            "inconsistent"
        )
    for name, value in (
        ("orbit_catalog_sha256", coverage["orbit_catalog_sha256"]),
        ("current_plan_file_sha256", current_plan_file_sha256),
        ("current_mesh_forest_sha256", current_mesh_forest_sha256),
        ("current_degree_map_sha256", current_degree_map_sha256),
    ):
        _sha256(value, label=name)
    return _new_h_level3_saturation_authority(
        {
            "status": expected_status,
            "current_plan_file_sha256": current_plan_file_sha256,
            "current_mesh_forest_sha256": current_mesh_forest_sha256,
            "current_degree_map_sha256": current_degree_map_sha256,
            "level_two_target_ids": targets,
            "level_two_target_ids_sha256": p6_target_ids_sha256(targets),
            "periodic_orbit_ids": orbits,
            "periodic_orbit_ids_sha256": h_level3_orbit_ids_sha256(
                orbits
            ),
            "orbit_catalog_sha256": str(
                coverage["orbit_catalog_sha256"]
            ),
            "covered_target_ids": covered_targets,
            "covered_target_ids_sha256": p6_target_ids_sha256(
                covered_targets
            ),
            "covered_orbit_ids": covered_orbits,
            "covered_orbit_ids_sha256": h_level3_orbit_ids_sha256(
                covered_orbits
            ),
            "coverage_complete": True,
            "production_maximum_level": _H_LEVEL3_PRODUCTION_MAXIMUM_LEVEL,
            "shadow_maximum_level": _H_LEVEL3_SHADOW_MAXIMUM_LEVEL,
            "shadow_only": True,
            "selectable_as_production": False,
            "normalized_max": normalized_max,
            "normalized_limit": _H_LEVEL3_NORMALIZED_LIMIT,
            "evidence_kind": "independent_global_level3_shadow",
            "evidence_sha256": independent_measured_evidence_sha256,
            "authority_sha256": "",
        }
    )


_H_LEVEL3_SATURATION_PAYLOAD_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "current_plan_file_sha256",
        "current_mesh_forest_sha256",
        "current_degree_map_sha256",
        "level_two_target_count",
        "level_two_target_ids",
        "level_two_target_ids_sha256",
        "periodic_orbit_count",
        "periodic_orbit_ids",
        "periodic_orbit_ids_sha256",
        "orbit_catalog_sha256",
        "covered_target_count",
        "covered_target_ids",
        "covered_target_ids_sha256",
        "covered_orbit_count",
        "covered_orbit_ids",
        "covered_orbit_ids_sha256",
        "coverage_complete",
        "production_maximum_level",
        "shadow_maximum_level",
        "shadow_only",
        "selectable_as_production",
        "normalized_max",
        "normalized_limit",
        "evidence_kind",
        "evidence_sha256",
        "authority_sha256",
    }
)


def _h_level3_saturation_authority_from_payload(
    payload: Mapping[str, object],
    *,
    expected_plan_file_sha256: str | None = None,
    expected_mesh_forest_sha256: str | None = None,
    expected_degree_map_sha256: str | None = None,
    independent_measured_evidence_sha256: str | None = None,
    require_independent_measured_evidence: bool,
) -> HLevel3SaturationAuthority:
    if not isinstance(payload, Mapping) or set(payload) != set(
        _H_LEVEL3_SATURATION_PAYLOAD_KEYS
    ):
        raise ValueError("level3 h-saturation authority uses an open schema")
    if (
        payload["schema_version"]
        != H_LEVEL3_SATURATION_AUTHORITY_SCHEMA
    ):
        raise ValueError("unsupported level3 h-saturation authority schema")
    for name in (
        "level_two_target_ids",
        "periodic_orbit_ids",
        "covered_target_ids",
        "covered_orbit_ids",
    ):
        if not isinstance(payload[name], list) or any(
            not isinstance(value, str) for value in payload[name]
        ):
            raise ValueError(f"{name} must be a string array")
    for name in (
        "level_two_target_count",
        "periodic_orbit_count",
        "covered_target_count",
        "covered_orbit_count",
        "production_maximum_level",
        "shadow_maximum_level",
    ):
        if type(payload[name]) is not int:
            raise ValueError(f"{name} must be an integer")
    authority = HLevel3SaturationAuthority(
        status=str(payload["status"]),
        current_plan_file_sha256=str(
            payload["current_plan_file_sha256"]
        ),
        current_mesh_forest_sha256=str(
            payload["current_mesh_forest_sha256"]
        ),
        current_degree_map_sha256=str(
            payload["current_degree_map_sha256"]
        ),
        level_two_target_ids=tuple(payload["level_two_target_ids"]),
        level_two_target_ids_sha256=str(
            payload["level_two_target_ids_sha256"]
        ),
        periodic_orbit_ids=tuple(payload["periodic_orbit_ids"]),
        periodic_orbit_ids_sha256=str(
            payload["periodic_orbit_ids_sha256"]
        ),
        orbit_catalog_sha256=str(payload["orbit_catalog_sha256"]),
        covered_target_ids=tuple(payload["covered_target_ids"]),
        covered_target_ids_sha256=str(
            payload["covered_target_ids_sha256"]
        ),
        covered_orbit_ids=tuple(payload["covered_orbit_ids"]),
        covered_orbit_ids_sha256=str(
            payload["covered_orbit_ids_sha256"]
        ),
        coverage_complete=payload["coverage_complete"],
        production_maximum_level=payload["production_maximum_level"],
        shadow_maximum_level=payload["shadow_maximum_level"],
        shadow_only=payload["shadow_only"],
        selectable_as_production=payload["selectable_as_production"],
        normalized_max=(
            None
            if payload["normalized_max"] is None
            else float(payload["normalized_max"])
        ),
        normalized_limit=float(payload["normalized_limit"]),
        evidence_kind=str(payload["evidence_kind"]),
        evidence_sha256=str(payload["evidence_sha256"]),
        authority_sha256=str(payload["authority_sha256"]),
    )
    for name, expected in (
        ("level_two_target_count", authority.level_two_target_count),
        ("periodic_orbit_count", authority.periodic_orbit_count),
        ("covered_target_count", authority.covered_target_count),
        ("covered_orbit_count", authority.covered_orbit_count),
    ):
        if payload[name] != expected:
            raise ValueError(f"{name} differs from its inventory")
    for expected, observed, label in (
        (
            expected_plan_file_sha256,
            authority.current_plan_file_sha256,
            "level3 h-saturation plan file",
        ),
        (
            expected_mesh_forest_sha256,
            authority.current_mesh_forest_sha256,
            "level3 h-saturation mesh forest",
        ),
        (
            expected_degree_map_sha256,
            authority.current_degree_map_sha256,
            "level3 h-saturation degree map",
        ),
    ):
        if expected is not None and expected != observed:
            raise ValueError(f"{label} SHA-256 differs")
    if (
        authority.level_two_target_count
        and authority.status in {"measured_pass", "measured_fail"}
        and require_independent_measured_evidence
    ):
        if (
            independent_measured_evidence_sha256 is None
            or _sha256(
                independent_measured_evidence_sha256,
                label="independent level3 h-saturation evidence SHA-256",
            )
            != authority.evidence_sha256
        ):
            raise ValueError(
                "non-vacuous measured h-saturation is not bound to an "
                "independently loaded global level3 evidence artifact"
            )
    return authority


def h_level3_saturation_authority_from_payload(
    payload: Mapping[str, object],
    *,
    expected_plan_file_sha256: str | None = None,
    expected_mesh_forest_sha256: str | None = None,
    expected_degree_map_sha256: str | None = None,
    independent_measured_evidence_sha256: str | None = None,
) -> HLevel3SaturationAuthority:
    """Load level3 h-saturation without accepting a caller pass boolean."""

    return _h_level3_saturation_authority_from_payload(
        payload,
        expected_plan_file_sha256=expected_plan_file_sha256,
        expected_mesh_forest_sha256=expected_mesh_forest_sha256,
        expected_degree_map_sha256=expected_degree_map_sha256,
        independent_measured_evidence_sha256=(
            independent_measured_evidence_sha256
        ),
        require_independent_measured_evidence=True,
    )


def _replay_h_level3_saturation_authority_from_payload(
    payload: Mapping[str, object],
) -> HLevel3SaturationAuthority:
    """Replay an authority whose independent binding passed at ingestion."""

    return _h_level3_saturation_authority_from_payload(
        payload,
        require_independent_measured_evidence=False,
    )


@dataclass(frozen=True, slots=True)
class ShadowCost:
    """Measured or predicted structural increment for one local action."""

    added_active_dofs: int
    added_rows: int
    added_matrix_nnz: int
    added_factor_nnz: int
    added_solver_peak_bytes: int

    def __post_init__(self) -> None:
        for name in (
            "added_active_dofs",
            "added_rows",
            "added_matrix_nnz",
            "added_factor_nnz",
            "added_solver_peak_bytes",
        ):
            value = getattr(self, name)
            if type(value) is not int:
                raise ValueError(f"{name} must be an integer")


@dataclass(frozen=True, slots=True)
class ShadowAction:
    """One signed, geometry-bound p/h action proposal."""

    action_id: str
    kind: str
    target_ids: tuple[str, ...]
    current: GoalVector
    shadow: GoalVector
    signed_dwr_delta: tuple[tuple[str, float], ...]
    cost: ShadowCost
    sign_consistent: bool
    actual_added_leaf_count: int
    transition_action_sha256: str
    transition_action_file_sha256: str
    transition_action_identity_sha256: str
    next_mesh_forest_sha256: str
    next_degree_map_sha256: str
    action_sha256: str

    def __post_init__(self) -> None:
        _opaque_id(self.action_id, label="action_id")
        if self.kind not in _ACTION_KINDS:
            raise ValueError(f"unsupported action kind: {self.kind}")
        if not self.target_ids or len(set(self.target_ids)) != len(self.target_ids):
            raise ValueError("shadow action targets must be nonempty and unique")
        for target in self.target_ids:
            _opaque_id(target, label="target_id")
        if not isinstance(self.current, GoalVector) or not isinstance(
            self.shadow,
            GoalVector,
        ):
            raise ValueError("shadow endpoints must use GoalVector")
        if (
            tuple(goal_id for goal_id, _ in self.signed_dwr_delta)
            != FORMAL_GOAL_IDS
        ):
            raise ValueError(
                "signed DWR packet must contain the complete formal inventory "
                "in canonical order"
            )
        for goal_id, value in self.signed_dwr_delta:
            if not math.isfinite(float(value)):
                raise ValueError(f"DWR delta for {goal_id} must be finite")
        if not isinstance(self.cost, ShadowCost):
            raise ValueError("shadow action cost must use ShadowCost")
        costs = tuple(
            getattr(self.cost, name)
            for name in self.cost.__dataclass_fields__
        )
        if self.kind in {"p-up", "h-refine"} and any(
            value < 0 for value in costs
        ):
            raise ValueError("enrichment costs cannot be negative")
        if self.kind in {"p-down", "h-coarsen"} and any(
            value > 0 for value in costs
        ):
            raise ValueError("coarsening costs cannot be positive")
        if self.kind == "keep" and any(costs):
            raise ValueError("keep action must have zero structural cost")
        if not isinstance(self.sign_consistent, bool):
            raise ValueError("sign_consistent must be boolean")
        predicted = dict(self.signed_dwr_delta)
        expected_sign_consistent = dwr_endpoint_sign_consistent(
            predicted,
            current=self.current,
            shadow=self.shadow,
        )
        if self.sign_consistent is not expected_sign_consistent:
            raise ValueError(
                "sign_consistent differs from the signed DWR/endpoint content"
            )
        if type(self.actual_added_leaf_count) is not int:
            raise ValueError("actual_added_leaf_count must be integral")
        if self.kind == "h-refine" and self.actual_added_leaf_count <= 0:
            raise ValueError("h-refine must report actual added leaves")
        if self.kind != "h-refine" and self.actual_added_leaf_count != 0:
            raise ValueError("only h-refine may add leaves")
        for name in (
            "transition_action_sha256",
            "transition_action_file_sha256",
            "transition_action_identity_sha256",
            "next_mesh_forest_sha256",
            "next_degree_map_sha256",
        ):
            _sha256(getattr(self, name), label=name)
        expected = _action_sha(self, include_sha=False)
        if self.action_sha256 != expected:
            raise ValueError("shadow action SHA does not match its content")

    @property
    def normalized_signed_dwr_deltas(self) -> Mapping[str, float]:
        """Return the signed-DWR prediction in blind tolerance units."""

        current = self.current.by_id
        shadow = self.shadow.by_id
        return MappingProxyType(
            {
                goal_id: float(delta)
                / blind_tolerance(
                    goal_id,
                    current,
                    shadow,
                )
                for goal_id, delta in self.signed_dwr_delta
            }
        )

    @property
    def normalized_endpoint_deltas(self) -> Mapping[str, float]:
        """Return the independently solved shadow-endpoint change in blind units."""

        current = self.current.by_id
        shadow = self.shadow.by_id
        return MappingProxyType(
            {
                goal_id: (
                    float(shadow[goal_id]) - float(current[goal_id])
                )
                / blind_tolerance(
                    goal_id,
                    current,
                    shadow,
                )
                for goal_id in FORMAL_GOAL_IDS
            }
        )

    @property
    def normalized_deltas(self) -> Mapping[str, float]:
        """Backward-compatible name for the signed-DWR prediction."""

        return self.normalized_signed_dwr_deltas

    @property
    def maximum_normalized_signed_dwr_delta(self) -> float:
        return max(
            (
                abs(value)
                for value in self.normalized_signed_dwr_deltas.values()
            ),
            default=0.0,
        )

    @property
    def maximum_normalized_endpoint_delta(self) -> float:
        return max(
            (
                abs(value)
                for value in self.normalized_endpoint_deltas.values()
            ),
            default=0.0,
        )

    @property
    def maximum_normalized_delta(self) -> float:
        """Conservative stopping metric from prediction and solved endpoint."""

        return max(
            self.maximum_normalized_signed_dwr_delta,
            self.maximum_normalized_endpoint_delta,
        )

    @property
    def aggregate_normalized_delta(self) -> float:
        """Signed-DWR aggregate retained for the established action ranking."""

        values = tuple(self.normalized_signed_dwr_deltas.values())
        return math.sqrt(sum(value * value for value in values))

    def benefit_per_cost(self, metric: str) -> float:
        denominator = {
            "rows": self.cost.added_rows,
            "matrix_nnz": self.cost.added_matrix_nnz,
            "factor_nnz": self.cost.added_factor_nnz,
            "solver_peak": self.cost.added_solver_peak_bytes,
        }.get(metric)
        if denominator is None:
            raise ValueError(f"unknown cost metric: {metric}")
        return self.aggregate_normalized_delta / max(abs(int(denominator)), 1)


def _action_sha(
    action: ShadowAction,
    *,
    include_sha: bool,
) -> str:
    payload = {
        "action_id": action.action_id,
        "kind": action.kind,
        "target_ids": list(action.target_ids),
        "current_sha256": action.current.sha256,
        "shadow_sha256": action.shadow.sha256,
        "signed_dwr_delta": [
            [goal_id, float(value)]
            for goal_id, value in action.signed_dwr_delta
        ],
        "cost": {
            name: getattr(action.cost, name)
            for name in action.cost.__dataclass_fields__
        },
        "sign_consistent": action.sign_consistent,
        "actual_added_leaf_count": action.actual_added_leaf_count,
        "transition_action_sha256": action.transition_action_sha256,
        "transition_action_file_sha256": (
            action.transition_action_file_sha256
        ),
        "transition_action_identity_sha256": (
            action.transition_action_identity_sha256
        ),
        "next_mesh_forest_sha256": action.next_mesh_forest_sha256,
        "next_degree_map_sha256": action.next_degree_map_sha256,
    }
    if include_sha:
        payload["action_sha256"] = action.action_sha256
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("ascii")
    ).hexdigest()


def build_shadow_action(
    *,
    action_id: str,
    kind: str,
    target_ids: tuple[str, ...],
    current: GoalVector,
    shadow: GoalVector,
    signed_dwr_delta: Mapping[str, float],
    cost: ShadowCost,
    sign_consistent: bool,
    transition_action_sha256: str,
    transition_action_file_sha256: str,
    transition_action_identity_sha256: str,
    next_mesh_forest_sha256: str,
    next_degree_map_sha256: str,
    actual_added_leaf_count: int = 0,
) -> ShadowAction:
    """Construct and content-bind one action."""

    if set(signed_dwr_delta) != set(FORMAL_GOAL_IDS):
        missing = sorted(set(FORMAL_GOAL_IDS) - set(signed_dwr_delta))
        extra = sorted(set(signed_dwr_delta) - set(FORMAL_GOAL_IDS))
        raise ValueError(
            "signed DWR mapping must contain the complete formal inventory; "
            f"missing={missing}, extra={extra}"
        )
    if type(sign_consistent) is not bool:
        raise ValueError("sign_consistent must be boolean")
    ordered = tuple(
        (goal_id, float(signed_dwr_delta[goal_id]))
        for goal_id in FORMAL_GOAL_IDS
    )
    provisional = object.__new__(ShadowAction)
    for name, value in (
        ("action_id", action_id),
        ("kind", kind),
        ("target_ids", tuple(target_ids)),
        ("current", current),
        ("shadow", shadow),
        ("signed_dwr_delta", ordered),
        ("cost", cost),
        ("sign_consistent", sign_consistent),
        ("actual_added_leaf_count", int(actual_added_leaf_count)),
        ("transition_action_sha256", transition_action_sha256),
        ("transition_action_file_sha256", transition_action_file_sha256),
        (
            "transition_action_identity_sha256",
            transition_action_identity_sha256,
        ),
        ("next_mesh_forest_sha256", next_mesh_forest_sha256),
        ("next_degree_map_sha256", next_degree_map_sha256),
        ("action_sha256", ""),
    ):
        object.__setattr__(provisional, name, value)
    sha = _action_sha(provisional, include_sha=False)
    return ShadowAction(
        action_id=action_id,
        kind=kind,
        target_ids=tuple(target_ids),
        current=current,
        shadow=shadow,
        signed_dwr_delta=ordered,
        cost=cost,
        sign_consistent=sign_consistent,
        actual_added_leaf_count=int(actual_added_leaf_count),
        transition_action_sha256=transition_action_sha256,
        transition_action_file_sha256=transition_action_file_sha256,
        transition_action_identity_sha256=(
            transition_action_identity_sha256
        ),
        next_mesh_forest_sha256=next_mesh_forest_sha256,
        next_degree_map_sha256=next_degree_map_sha256,
        action_sha256=sha,
    )


@dataclass(frozen=True, slots=True)
class ShadowCatalog:
    """Complete set of local actions for one current solved state."""

    current_goal_sha256: str
    p_actions: tuple[ShadowAction, ...]
    h_actions: tuple[ShadowAction, ...]
    p6_saturation: P6SaturationAuthority
    h_level3_saturation: HLevel3SaturationAuthority

    def __post_init__(self) -> None:
        actions = (*self.p_actions, *self.h_actions)
        if not actions:
            raise ValueError("shadow catalog must contain at least one action")
        if not isinstance(self.p6_saturation, P6SaturationAuthority):
            raise ValueError(
                "shadow catalog requires closed p6 saturation authority"
            )
        if not isinstance(
            self.h_level3_saturation,
            HLevel3SaturationAuthority,
        ):
            raise ValueError(
                "shadow catalog requires closed level3 h-saturation authority"
            )
        if (
            not any(row.kind == "p-up" for row in self.p_actions)
            and self.p6_saturation.p6_target_count == 0
        ):
            raise ValueError(
                "a catalog without p6 leaves requires a real p-up lane"
            )
        if (
            not any(row.kind == "h-refine" for row in self.h_actions)
            and self.h_level3_saturation.level_two_target_count == 0
        ):
            raise ValueError(
                "a catalog without level-two leaves requires a real "
                "h-refine lane"
            )
        if len({row.action_id for row in actions}) != len(actions):
            raise ValueError("shadow action IDs must be unique")
        if any(row.current.sha256 != self.current_goal_sha256 for row in actions):
            raise ValueError("shadow actions do not share one current endpoint")
        if any(row.kind not in {"p-up", "p-down", "keep"} for row in self.p_actions):
            raise ValueError("p catalog contains a non-p action")
        if any(row.kind not in {"h-refine", "h-coarsen", "keep"} for row in self.h_actions):
            raise ValueError("h catalog contains a non-h action")

    @property
    def sha256(self) -> str:
        return hashlib.sha256(
            json.dumps(
                {
                    "current_goal_sha256": self.current_goal_sha256,
                    "p": [row.action_sha256 for row in self.p_actions],
                    "h": [row.action_sha256 for row in self.h_actions],
                    "p6_saturation_authority_sha256": (
                        self.p6_saturation.authority_sha256
                    ),
                    "h_level3_saturation_authority_sha256": (
                        self.h_level3_saturation.authority_sha256
                    ),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("ascii")
        ).hexdigest()

    def _enrichment_actions(self, lane: str) -> tuple[ShadowAction, ...]:
        if lane not in {"p", "h"}:
            raise ValueError("lane must be p or h")
        enrichment_kind = "p-up" if lane == "p" else "h-refine"
        source = self.p_actions if lane == "p" else self.h_actions
        return tuple(row for row in source if row.kind == enrichment_kind)

    def maximum_normalized_signed_dwr_delta(self, lane: str) -> float:
        """Largest signed-DWR prediction in one enrichment lane."""

        actions = self._enrichment_actions(lane)
        return max(
            (row.maximum_normalized_signed_dwr_delta for row in actions),
            default=0.0,
        )

    def maximum_normalized_endpoint_delta(self, lane: str) -> float:
        """Largest independently solved endpoint change in one lane."""

        actions = self._enrichment_actions(lane)
        return max(
            (row.maximum_normalized_endpoint_delta for row in actions),
            default=0.0,
        )

    def maximum_normalized_delta(self, lane: str) -> float:
        """Conservative lane metric used for selection and freeze decisions."""

        return max(
            self.maximum_normalized_signed_dwr_delta(lane),
            self.maximum_normalized_endpoint_delta(lane),
        )


__all__ = [
    "ShadowAction",
    "ShadowCatalog",
    "ShadowCost",
    "HLevel3SaturationAuthority",
    "H_LEVEL3_SATURATION_AUTHORITY_SCHEMA",
    "H_LEVEL3_SATURATION_MEASURED_EVIDENCE_SCHEMA",
    "H_LEVEL3_SATURATION_PLAN_SCAN_EVIDENCE_SCHEMA",
    "P6SaturationAuthority",
    "P6_SATURATION_AUTHORITY_SCHEMA",
    "P6_SATURATION_MEASURED_EVIDENCE_SCHEMA",
    "P6_SATURATION_PLAN_SCAN_EVIDENCE_SCHEMA",
    "build_measured_h_level3_saturation_authority",
    "build_unmeasured_h_level3_saturation_authority",
    "build_unmeasured_p6_saturation_authority",
    "build_shadow_action",
    "dwr_endpoint_sign_consistent",
    "h_level3_orbit_ids_sha256",
    "h_level3_saturation_authority_from_payload",
    "h_level3_saturation_authority_payload",
    "p6_saturation_authority_from_payload",
    "p6_saturation_authority_payload",
    "p6_target_ids_sha256",
]
