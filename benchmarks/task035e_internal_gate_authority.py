#!/usr/bin/env python3
"""Recompute the Task035e blind internal Gates from bound live artifacts.

The previous cycle-binding interface accepted a caller-authored collection of
booleans and budget fractions.  This producer intentionally has no CLI option
for any Gate value.  It replays the qualified current candidate, its executed
plan, the MPI8 current snapshot, and three independently solved numerical
perturbations:

* a repeated/tighter direct solve for the algebraic budget;
* a solve with a strict superset of DtN orders;
* a solve with a higher DtN/postprocess quadrature degree.

An optional MPI1 diagnostic record is compared with the MPI8 current record.
Without that record, the legacy ``serial_mpi_identity_pass`` field remains
false.  The MPI8 rank/plan/snapshot identity is still reported independently.

The output is a closed, self-hashed, mode-0600 authority.  It contains no input
paths and refuses evaluator/reference-layer inputs.
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
from typing import Any, Mapping, Sequence

import numpy as np

from benchmarks.task035e_candidate_output import (
    AdaptedCandidateOutput,
    CandidateOutputError,
    CandidateWatchdogInput,
    adapt_candidate_output,
)
from src.adaptivity.blind_controller import (
    FIXED_ORDER_KEYS,
    FORMAL_FIELD_COMPLEX_NAMES,
    FORMAL_FIELD_SCALAR_NAMES,
    FORMAL_GOAL_IDS,
    GoalVector,
)
from src.adaptivity.blind_controller.contracts import normalized_goal_distance
from src.adaptivity.blind_controller.state_machine import InternalGates


AUTHORITY_SCHEMA = "task035e.blind-internal-gate-authority.v1"
AUTHORITY_NAMESPACE = "task035e.blind-internal-gate-authority.v1"
FINAL_AUTHORITY_STATUS = "internal_gate_authority_recomputed"
FINAL_AUTHORITY_CLASSIFICATION = "final_probe_qualified"
DEFERRED_AUTHORITY_STATUS = "internal_gate_authority_deferred"
DEFERRED_AUTHORITY_CLASSIFICATION = "deferred_intermediate_cycle"
SNAPSHOT_SCHEMA = "task035e.multigoal-current-live-snapshot.v1"
SNAPSHOT_MANIFEST_NAMESPACE = "task035e.multigoal-current-manifest.v1"
SNAPSHOT_PLAN_NAMESPACE = "task035e.executed-plan-payload.v1"
SNAPSHOT_GATE_NAMESPACE = "task035e.current-qualified-primal-gate.v1"
SNAPSHOT_COMMON_NAMESPACE = "task035e.current-common-identity.v1"
SNAPSHOT_RESIDUAL_NAMESPACE = "task035e.current-full-active-residual.v1"
SNAPSHOT_RANK_NAMESPACE = "task035e.current-rank-bound-identity.v1"
RECEIPT_SCHEMA = "task035e.internal-gate-authority-receipt.v1"
PROBE_LAUNCH_SCHEMA = "task035e.internal-probe-launch.v1"
_PROBE_LAUNCH_KEYS = frozenset(
    {
        "schema_version",
        "selected",
        "kind",
        "mpi_size",
        "trial_id",
        "cycle_index",
        "output_role",
        "plan_file_sha256",
        "current_snapshot_file_sha256",
        "config_overrides",
        "ordinary_default_changed",
    }
)

FLOQUET_RESIDUAL_LIMIT = 5.0e-11
HANGING_RESIDUAL_LIMIT = 5.0e-11
BUDGET_FRACTION_LIMIT = 0.10
SERIAL_MPI_MAXIMUM_NORMALIZED_DISTANCE = 0.10

_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_SOURCE_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
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
_AUTHORITY_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "classification",
        "source_sha",
        "trial_id",
        "cycle_index",
        "mpi_size",
        "candidate_identity",
        "probe_identities",
        "measurements",
        "recomputed_checks",
        "gates",
        "producer",
        "authority_sha256",
    }
)
_CANDIDATE_IDENTITY_KEYS = frozenset(
    {
        "watchdog_record_file_sha256",
        "candidate_output_file_sha256",
        "candidate_output_payload_sha256",
        "plan_file_sha256",
        "plan_payload_sha256",
        "mesh_forest_sha256",
        "degree_map_sha256",
        "current_snapshot_file_sha256",
        "current_snapshot_payload_sha256",
        "snapshot_rank_bound_identity_sha256",
        "snapshot_full_residual_sha256",
        "raw_artifact_sha256",
        "raw_artifact_inventory_sha256",
        "structural_inventory",
    }
)
_PROBE_IDENTITY_KEYS = frozenset(
    {
        "kind",
        "watchdog_record_file_sha256",
        "candidate_output_payload_sha256",
        "config_sha256",
        "plan_file_sha256",
        "mesh_forest_sha256",
        "degree_map_sha256",
        "raw_artifact_sha256",
        "raw_artifact_inventory_sha256",
        "structural_inventory",
    }
)
_GATE_KEYS = frozenset(InternalGates.__dataclass_fields__)
_MEASUREMENT_KEYS = frozenset(
    {"floquet", "hanging", "mpi_identity", "multilevel", "budgets"}
)
_RECOMPUTED_CHECK_KEYS = frozenset(
    {
        "snapshot",
        "constraint",
        "multilevel",
        "budget_probe_qualified",
        "mpi8_candidate_plan_snapshot_identity",
        "serial_mpi1_same_plan_output_identity",
    }
)
_PRODUCER_KEYS = frozenset(
    {"source", "file_sha256", "algorithm_sha256"}
)
_DEFERRED_BUDGET_KEYS = frozenset(
    {
        "kind",
        "status",
        "formal_goal_count",
        "qualified_comparison",
        "budget_fraction",
        "probe_credit",
        "reason",
    }
)
_SNAPSHOT_CHECK_KEYS = frozenset(
    {
        "closed_self_hash",
        "formal_current_mpi8_role",
        "storage_contract",
        "candidate_plan_forest_degree_identity",
        "common_and_primal_gate_self_hashes",
        "candidate_residual_identity",
        "all_eight_rank_shards_hash_bound",
        "rank_bound_identity_recomputed",
        "partitioned_matrix_not_serialized",
        "snapshot_capability_not_overclaimed",
    }
)
_CONSTRAINT_CHECK_KEYS = frozenset(
    {
        "physical_trace_authority",
        "trace_constraint_authority",
        "floquet_constraints_present",
        "hanging_constraints_present",
        "periodic_cycle_residual_within_limit",
        "flattened_relation_residual_within_limit",
        "summary_floquet_residual_consistent_or_not_applicable",
    }
)
_MULTILEVEL_CHECK_KEYS = frozenset(
    {
        "qualified_multilevel_mesh_authority",
        "two_real_refinement_levels",
        "all_local_levels_present",
        "separated_user_patches",
        "strong_two_to_one_balance",
        "periodic_closure",
        "material_interface_protected",
    }
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


class InternalGateAuthorityError(ValueError):
    """Raised when live artifacts cannot produce a trustworthy authority."""


@dataclass(frozen=True, slots=True)
class BoundJSONInput:
    """One mode-0600 JSON input plus its independently supplied byte hash."""

    path: Path
    sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.path, Path):
            raise InternalGateAuthorityError("bound input path must use Path")
        _sha256(self.sha256, label="bound input SHA-256")


@dataclass(frozen=True, slots=True)
class InternalGateAuthorityReceipt:
    """Receipt for one immutable internal-Gate authority."""

    path: Path
    file_sha256: str
    authority_sha256: str
    source_sha: str
    trial_id: str
    cycle_index: int
    serial_mpi_identity_pass: bool
    classification: str


@dataclass(frozen=True, slots=True)
class _LoadedJSON:
    path: Path
    payload: Mapping[str, Any]
    file_sha256: str


@dataclass(frozen=True, slots=True)
class _CandidateContext:
    adapted: AdaptedCandidateOutput
    record: Mapping[str, Any]
    summary: Mapping[str, Any]
    config: Mapping[str, Any]
    record_file_sha256: str


@dataclass(frozen=True, slots=True)
class _CurrentAuthorityEvidence:
    current: _CandidateContext
    candidate_payload: Mapping[str, Any]
    candidate_file_sha256: str
    plan_payload_sha256: str
    snapshot: Mapping[str, Any]
    snapshot_checks: Mapping[str, bool]
    floquet: Mapping[str, Any]
    hanging: Mapping[str, Any]
    constraint_checks: Mapping[str, bool]
    multilevel: Mapping[str, Any]
    multilevel_checks: Mapping[str, bool]
    base_gates: Mapping[str, Any]
    candidate_identity: Mapping[str, Any]


def _reject_nonfinite(value: str) -> None:
    raise InternalGateAuthorityError(
        f"non-finite JSON constant is forbidden: {value}"
    )


def _reject_duplicate_object(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InternalGateAuthorityError(
                f"duplicate JSON object key is forbidden: {key}"
            )
        result[key] = value
    return result


def _canonical(value: Any) -> Any:
    if isinstance(value, np.generic):
        return _canonical(value.item())
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


def _json_sha256(value: Any, *, namespace: str | None = None) -> str:
    digest = hashlib.sha256()
    if namespace is not None:
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
        raise InternalGateAuthorityError(
            f"{label} must be a lowercase SHA-256"
        )
    return digest


def _source_sha(value: Any) -> str:
    source = str(value)
    if _SOURCE_SHA_RE.fullmatch(source) is None:
        raise InternalGateAuthorityError(
            "source SHA must be one lowercase full Git SHA"
        )
    return source


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise InternalGateAuthorityError(f"{label} must be one JSON object")
    return value


def _exact(
    value: Any,
    keys: frozenset[str] | set[str],
    *,
    label: str,
) -> Mapping[str, Any]:
    row = _mapping(value, label=label)
    if set(row) != set(keys):
        raise InternalGateAuthorityError(
            f"{label} does not use its closed schema; "
            f"missing={sorted(set(keys) - set(row))}, "
            f"extra={sorted(set(row) - set(keys))}"
        )
    return row


def _finite(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InternalGateAuthorityError(f"{label} must be finite")
    result = float(value)
    if not math.isfinite(result):
        raise InternalGateAuthorityError(f"{label} must be finite")
    return result


def _safe_path(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise InternalGateAuthorityError(f"{label} must not be a symlink")
    resolved = path.expanduser().resolve()
    if {part.lower() for part in resolved.parts}.intersection(
        _FORBIDDEN_PATH_PARTS
    ):
        raise InternalGateAuthorityError(
            f"{label} crosses an evaluator/reference layer"
        )
    return resolved


def _load_bound_json(
    bound: BoundJSONInput,
    *,
    label: str,
) -> _LoadedJSON:
    path = _safe_path(bound.path, label=label)
    try:
        metadata = path.stat()
    except OSError as exc:
        raise InternalGateAuthorityError(f"{label} is absent") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise InternalGateAuthorityError(
            f"{label} must be a regular mode-0600 file"
        )
    observed_sha = _file_sha256(path)
    if observed_sha != bound.sha256:
        raise InternalGateAuthorityError(f"{label} file SHA-256 differs")
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_reject_duplicate_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InternalGateAuthorityError(
            f"cannot read strict {label} JSON"
        ) from exc
    return _LoadedJSON(
        path=path,
        payload=_mapping(payload, label=label),
        file_sha256=observed_sha,
    )


def _load_candidate(bound: BoundJSONInput, *, label: str) -> _CandidateContext:
    loaded = _load_bound_json(bound, label=label)
    try:
        adapted = adapt_candidate_output(
            CandidateWatchdogInput(loaded.path, loaded.file_sha256),
            output_role="current",
        )
    except CandidateOutputError as exc:
        raise InternalGateAuthorityError(str(exc)) from exc
    record = loaded.payload
    summary = _mapping(record.get("solver_summary"), label=f"{label} summary")
    config = _mapping(summary.get("config"), label=f"{label} config")
    return _CandidateContext(
        adapted=adapted,
        record=record,
        summary=summary,
        config=config,
        record_file_sha256=loaded.file_sha256,
    )


def _load_candidate_output(
    bound: BoundJSONInput,
    *,
    current: _CandidateContext,
) -> tuple[Mapping[str, Any], str]:
    loaded = _load_bound_json(bound, label="candidate output")
    if dict(loaded.payload) != dict(current.adapted.payload):
        raise InternalGateAuthorityError(
            "candidate output does not replay from its watchdog record"
        )
    _goal_vector_from_candidate_output(loaded.payload)
    if _json_sha256(loaded.payload) != current.adapted.output_sha256:
        raise InternalGateAuthorityError(
            "candidate output payload SHA-256 differs"
        )
    return loaded.payload, loaded.file_sha256


def _complex_object(value: Any, *, label: str) -> complex:
    row = _exact(value, {"real", "imag"}, label=label)
    return complex(
        _finite(row["real"], label=f"{label}.real"),
        _finite(row["imag"], label=f"{label}.imag"),
    )


def _goal_vector_from_candidate_output(
    payload: Mapping[str, Any],
) -> GoalVector:
    """Extract the frozen 59 goals from an already qualified adapter payload."""

    _exact(
        payload,
        {
            "schema_version",
            "orders",
            "scalar_observations",
            "complex_observations",
            "full_explicit_true_residual",
        },
        label="candidate output",
    )
    orders = payload["orders"]
    if not isinstance(orders, list):
        raise InternalGateAuthorityError("candidate orders are absent")
    indexed: dict[tuple[str, int, int], Mapping[str, Any]] = {}
    for raw in orders:
        row = _mapping(raw, label="candidate order")
        identity = (
            str(row.get("port")),
            int(row.get("m")),
            int(row.get("n")),
        )
        if identity in indexed:
            raise InternalGateAuthorityError("candidate order is duplicated")
        indexed[identity] = row
    values: dict[str, float] = {}
    for port, m, n in FIXED_ORDER_KEYS:
        try:
            row = indexed[(port, m, n)]
        except KeyError as exc:
            raise InternalGateAuthorityError(
                f"candidate misses fixed order {(port, m, n)}"
            ) from exc
        propagating = row.get("propagating")
        if type(propagating) is not bool:
            raise InternalGateAuthorityError(
                "candidate order applicability is malformed"
            )
        if propagating:
            power = _finite(
                row.get("total_power"),
                label="candidate order power",
            )
            if power < 0.0:
                raise InternalGateAuthorityError(
                    "candidate order power is negative"
                )
        else:
            if row.get("total_power") is not None:
                raise InternalGateAuthorityError(
                    "evanescent candidate order carries far-field power"
                )
            power = 0.0
        amplitude = _complex_object(
            row.get("co_polarized_amplitude"),
            label="candidate co amplitude",
        )
        prefix = f"{port}:m{m}:n{n}"
        values[f"{prefix}:power"] = power
        values[f"{prefix}:co_amp_real"] = float(amplitude.real)
        values[f"{prefix}:co_amp_imag"] = float(amplitude.imag)
    scalar_rows = payload["scalar_observations"]
    complex_rows = payload["complex_observations"]
    if not isinstance(scalar_rows, list) or not isinstance(complex_rows, list):
        raise InternalGateAuthorityError(
            "candidate scalar/complex observations are absent"
        )
    scalars: dict[str, float] = {}
    for raw in scalar_rows:
        row = _mapping(raw, label="candidate scalar observation")
        name = str(row.get("name"))
        if name in scalars:
            raise InternalGateAuthorityError(
                "candidate scalar observation is duplicated"
            )
        scalars[name] = _finite(
            row.get("value"),
            label=f"candidate scalar {name}",
        )
    complexes: dict[str, complex] = {}
    for raw in complex_rows:
        row = _mapping(raw, label="candidate complex observation")
        name = str(row.get("name"))
        if name in complexes:
            raise InternalGateAuthorityError(
                "candidate complex observation is duplicated"
            )
        complexes[name] = _complex_object(
            row.get("value"),
            label=f"candidate complex {name}",
        )
    for name in (
        "R00_total",
        "R_total",
        "T_total",
        "A_closure",
        "A_volume",
        *FORMAL_FIELD_SCALAR_NAMES,
    ):
        try:
            values[f"scalar/{name}"] = scalars[name]
        except KeyError as exc:
            raise InternalGateAuthorityError(
                f"candidate misses formal scalar {name}"
            ) from exc
    for name in FORMAL_FIELD_COMPLEX_NAMES:
        try:
            value = complexes[name]
        except KeyError as exc:
            raise InternalGateAuthorityError(
                f"candidate misses formal complex probe {name}"
            ) from exc
        values[f"complex/{name}/real"] = float(value.real)
        values[f"complex/{name}/imag"] = float(value.imag)
    return GoalVector.from_mapping(values)


def _load_plan(
    bound: BoundJSONInput,
    *,
    current: _CandidateContext,
) -> tuple[Mapping[str, Any], str]:
    loaded = _load_bound_json(bound, label="executed blind plan")
    if (
        loaded.path != current.adapted.plan_path.resolve()
        or loaded.file_sha256 != current.adapted.plan_file_sha256
    ):
        raise InternalGateAuthorityError(
            "explicit plan differs from the candidate launch authority"
        )
    return loaded.payload, _json_sha256(loaded.payload)


def _snapshot_identity(
    bound: BoundJSONInput,
    *,
    current: _CandidateContext,
    plan_payload: Mapping[str, Any],
    candidate_payload: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, bool]]:
    loaded = _load_bound_json(bound, label="current MPI8 snapshot")
    manifest = _exact(
        loaded.payload,
        _SNAPSHOT_KEYS,
        label="current MPI8 snapshot",
    )
    unsigned = dict(manifest)
    stored_manifest_sha = _sha256(
        unsigned.pop("manifest_payload_sha256"),
        label="snapshot payload SHA-256",
    )
    checks: dict[str, bool] = {
        "closed_self_hash": (
            _json_sha256(
                unsigned,
                namespace=SNAPSHOT_MANIFEST_NAMESPACE,
            )
            == stored_manifest_sha
        ),
        "formal_current_mpi8_role": (
            manifest["schema_version"] == SNAPSHOT_SCHEMA
            and manifest["status"]
            == "multigoal_current_live_snapshot_pass"
            and manifest["pass"] is True
            and manifest["role"] == "current_blind_state"
            and manifest["source_sha"] == current.adapted.source_sha
            and manifest["trial_id"] == current.adapted.trial_id
            and manifest["cycle_index"] == current.adapted.cycle_index
            and manifest["mpi_size"] == 8
            and manifest["formal_mpi8_qualified"] is True
            and manifest["diagnostic_serial_fixture"] is False
        ),
        "storage_contract": (
            manifest["no_full_vector_python_allgather"] is True
            and manifest["full_matrix_persisted"] is False
            and manifest["ordinary_default_changed"] is False
        ),
    }
    plan = _mapping(
        manifest["plan_identity"],
        label="snapshot plan identity",
    )
    checks["candidate_plan_forest_degree_identity"] = (
        plan.get("file_sha256") == current.adapted.plan_file_sha256
        and plan.get("payload_sha256")
        == _json_sha256(
            plan_payload,
            namespace=SNAPSHOT_PLAN_NAMESPACE,
        )
        and plan.get("forest_leaf_catalog_sha256")
        == current.adapted.forest_leaf_catalog_sha256
        and plan.get("cell_degree_plan_sha256")
        == current.adapted.cell_degree_plan_sha256
    )
    common = _mapping(
        manifest["common_identity"],
        label="snapshot common identity",
    )
    gate = _mapping(
        manifest["qualified_primal_gate"],
        label="snapshot qualified primal Gate",
    )
    checks["common_and_primal_gate_self_hashes"] = (
        manifest["common_identity_sha256"]
        == _json_sha256(common, namespace=SNAPSHOT_COMMON_NAMESPACE)
        and manifest["qualified_primal_gate_sha256"]
        == _json_sha256(gate, namespace=SNAPSHOT_GATE_NAMESPACE)
    )
    residual = _mapping(
        gate.get("full_active_residual"),
        label="snapshot full active residual",
    )
    residual_sha = _json_sha256(
        residual,
        namespace=SNAPSHOT_RESIDUAL_NAMESPACE,
    )
    residual_value = _finite(
        residual.get("linear_system_relative_residual"),
        label="snapshot full explicit residual",
    )
    checks["candidate_residual_identity"] = (
        gate.get("full_active_residual_sha256") == residual_sha
        and math.isclose(
            residual_value,
            float(candidate_payload["full_explicit_true_residual"]),
            rel_tol=0.0,
            abs_tol=1.0e-18,
        )
    )
    shards_raw = manifest["shards"]
    shards = shards_raw if isinstance(shards_raw, list) else []
    shard_rows: list[dict[str, Any]] = []
    shard_files_pass = len(shards) == 8
    for rank, raw in enumerate(shards):
        if not isinstance(raw, Mapping) or raw.get("rank") != rank:
            shard_files_pass = False
            continue
        path_value = raw.get("path")
        local_identity = raw.get("local_identity_sha256")
        try:
            local_identity_sha = _sha256(
                local_identity,
                label=f"snapshot rank-{rank} local identity",
            )
        except InternalGateAuthorityError:
            shard_files_pass = False
            continue
        if not isinstance(path_value, str) or not path_value:
            shard_files_pass = False
            continue
        shard_path = Path(path_value)
        if not shard_path.is_absolute():
            shard_path = loaded.path.parent / shard_path
        try:
            shard_path = _safe_path(
                shard_path,
                label=f"snapshot rank-{rank} shard",
            )
            metadata = shard_path.stat()
            expected_sha = _sha256(
                raw.get("file_sha256"),
                label=f"snapshot rank-{rank} shard SHA-256",
            )
            shard_files_pass = bool(
                shard_files_pass
                and stat.S_ISREG(metadata.st_mode)
                and stat.S_IMODE(metadata.st_mode) == 0o600
                and _file_sha256(shard_path) == expected_sha
            )
        except (OSError, InternalGateAuthorityError):
            shard_files_pass = False
        shard_rows.append(
            {
                "rank": rank,
                "local_identity_sha256": local_identity_sha,
            }
        )
    rank_bound_sha = _json_sha256(
        shard_rows,
        namespace=SNAPSHOT_RANK_NAMESPACE,
    )
    checks["all_eight_rank_shards_hash_bound"] = shard_files_pass
    checks["rank_bound_identity_recomputed"] = (
        len(shard_rows) == 8
        and manifest["rank_bound_identity_sha256"] == rank_bound_sha
    )
    matrix = manifest.get("matrix_operator")
    checks["partitioned_matrix_not_serialized"] = (
        isinstance(matrix, Mapping)
        and matrix.get("full_matrix_serialized") is False
    )
    capability = manifest.get("capability_credit")
    checks["snapshot_capability_not_overclaimed"] = (
        isinstance(capability, Mapping)
        and capability.get("current_primal_snapshot_complete") is True
        and capability.get("accuracy_credit") is False
    )
    return (
        {
            "file_sha256": loaded.file_sha256,
            "payload_sha256": stored_manifest_sha,
            "rank_bound_identity_sha256": rank_bound_sha,
            "full_residual_sha256": residual_sha,
            "full_explicit_residual": residual_value,
        },
        checks,
    )


def _all_true_checks(value: Any) -> bool:
    return (
        isinstance(value, Mapping)
        and bool(value)
        and all(item is True for item in value.values())
    )


def _floquet_and_hanging_measurements(
    current: _CandidateContext,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, bool]]:
    summary = current.summary
    local = summary.get("stage4_local_h_constraint_audit")
    local = local if isinstance(local, Mapping) else {}
    physical = local.get("physical_trace")
    physical = physical if isinstance(physical, Mapping) else {}
    trace = local.get("trace_constraints")
    trace = trace if isinstance(trace, Mapping) else {}
    periodic_cycle = physical.get("periodic_cycle_error")
    relation_residual = physical.get("maximum_relation_residual")
    cycle_value = (
        1.0
        if isinstance(periodic_cycle, bool)
        or not isinstance(periodic_cycle, (int, float))
        or not math.isfinite(float(periodic_cycle))
        else abs(float(periodic_cycle))
    )
    relation_value = (
        1.0
        if isinstance(relation_residual, bool)
        or not isinstance(relation_residual, (int, float))
        or not math.isfinite(float(relation_residual))
        else abs(float(relation_residual))
    )
    summary_residual_names = (
        "floquet_max_face_transform_fit_residual",
        "floquet_edge_corner_constraint_phase_mismatch",
    )
    summary_values = {
        name: summary.get(name) for name in summary_residual_names
    }
    finite_summary_values = [
        abs(float(value))
        for value in summary_values.values()
        if not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    ]
    maximum_summary_residual: float | None = (
        max(finite_summary_values) if finite_summary_values else None
    )
    constraint_kinds = trace.get("constraint_kinds")
    kinds = (
        set(map(str, constraint_kinds))
        if isinstance(constraint_kinds, list)
        else set()
    )
    checks = {
        "physical_trace_authority": (
            physical.get("schema_version")
            == "task035e.broken-hexa-variable-trace-authority.v1"
            and physical.get("status")
            == "broken_hexa_variable_trace_constraint_component_pass"
            and physical.get("pass") is True
            and physical.get("mpi_size") == 8
            and physical.get("failures") == []
            and _all_true_checks(physical.get("checks"))
        ),
        "trace_constraint_authority": (
            trace.get("schema_version")
            == "task035d.broken-hexa-cell-trace-map.v2"
            and trace.get("status") == "broken_hexa_cell_trace_binding_pass"
            and trace.get("pass") is True
            and trace.get("mpi_size") == 8
            and trace.get("failures") == []
            and _all_true_checks(trace.get("checks"))
            and trace.get("pde_launch_ownership_gate") is True
            and trace.get(
                "hanging_or_floquet_slave_rows_globally_numbered"
            )
            is False
        ),
        "floquet_constraints_present": (
            "floquet" in kinds
            and trace.get("contains_floquet_constraints") is True
            and int(trace.get("periodic_slave_rows", 0)) > 0
        ),
        "hanging_constraints_present": (
            "hanging" in kinds
            and trace.get("contains_hanging_constraints") is True
            and int(trace.get("hanging_slave_rows", 0)) > 0
        ),
        "periodic_cycle_residual_within_limit": (
            cycle_value <= FLOQUET_RESIDUAL_LIMIT
        ),
        "flattened_relation_residual_within_limit": (
            relation_value <= HANGING_RESIDUAL_LIMIT
        ),
        "summary_floquet_residual_consistent_or_not_applicable": (
            maximum_summary_residual is None
            or maximum_summary_residual <= FLOQUET_RESIDUAL_LIMIT
        ),
    }
    floquet = {
        "limit": FLOQUET_RESIDUAL_LIMIT,
        "periodic_cycle_error": cycle_value,
        "summary_residuals": summary_values,
        "maximum_summary_residual": maximum_summary_residual,
        "constraint_kinds": sorted(kinds),
    }
    hanging = {
        "limit": HANGING_RESIDUAL_LIMIT,
        "maximum_relation_residual": relation_value,
        "hanging_slave_rows": trace.get("hanging_slave_rows"),
        "cross_rank_hanging_patch_count": trace.get(
            "cross_rank_hanging_patch_count"
        ),
        "remote_resolution_sha256": trace.get("remote_resolution_sha256"),
    }
    return floquet, hanging, checks


def _multilevel_measurements(
    current: _CandidateContext,
) -> tuple[dict[str, Any], dict[str, bool]]:
    local = current.summary.get("stage4_local_h_constraint_audit")
    local = local if isinstance(local, Mapping) else {}
    mesh = local.get("mesh")
    mesh = mesh if isinstance(mesh, Mapping) else {}
    forest = mesh.get("forest")
    forest = forest if isinstance(forest, Mapping) else {}
    level_counts_raw = forest.get("leaf_level_counts")
    level_counts = (
        dict(level_counts_raw)
        if isinstance(level_counts_raw, Mapping)
        else {}
    )
    separated_count = mesh.get("user_mark_component_count")
    separated_count = (
        int(separated_count)
        if type(separated_count) is int and separated_count >= 0
        else 0
    )
    all_levels = all(
        type(level_counts.get(str(level))) is int
        and int(level_counts[str(level)]) > 0
        for level in range(3)
    )
    periodic = forest.get("periodic_boundary_audit")
    periodic = periodic if isinstance(periodic, Mapping) else {}
    checks = {
        "qualified_multilevel_mesh_authority": (
            mesh.get("schema_version")
            == "task035e.stage4-multilevel-local-h-mesh.v1"
            and mesh.get("status")
            == "stage4_balanced_multilevel_local_h_mesh_pass"
            and mesh.get("pass") is True
        ),
        "two_real_refinement_levels": (
            mesh.get("maximum_level") == 2
            and mesh.get("refinement_stage_count") == 2
            and mesh.get("true_multilevel") is True
        ),
        "all_local_levels_present": all_levels,
        "separated_user_patches": (
            separated_count >= 2
            and mesh.get("spatially_separated_user_patches") is True
        ),
        "strong_two_to_one_balance": (
            forest.get("strong_2_to_1_balance") is True
            and forest.get("maximum_adjacent_level_jump") in {0, 1}
        ),
        "periodic_closure": (
            periodic.get("pass") is True
            and (
                not isinstance(periodic.get("checks"), Mapping)
                or _all_true_checks(periodic["checks"])
            )
        ),
        "material_interface_protected": (
            forest.get("material_interface_hanging_face_count") == 0
        ),
    }
    return (
        {
            "maximum_level": mesh.get("maximum_level"),
            "refinement_stage_count": mesh.get("refinement_stage_count"),
            "leaf_level_counts": level_counts,
            "separated_patch_count": separated_count,
            "hanging_patch_count": mesh.get("hanging_patch_count"),
            "maximum_adjacent_level_jump": forest.get(
                "maximum_adjacent_level_jump"
            ),
            "material_interface_hanging_face_count": forest.get(
                "material_interface_hanging_face_count"
            ),
        },
        checks,
    )


def _normalized_config(
    config: Mapping[str, Any],
    *,
    ignore: frozenset[str],
) -> dict[str, Any]:
    return {
        str(key): _canonical(value)
        for key, value in config.items()
        if key not in ignore
    }


def _probe_launch_contract(
    probe: _CandidateContext,
    *,
    kind: str,
    baseline: _CandidateContext,
    current_snapshot_file_sha256: str,
) -> tuple[bool, dict[str, Any]]:
    row = probe.record.get("task035e_internal_probe")
    contract = row if isinstance(row, Mapping) else {}
    expected_overrides: dict[str, Any]
    if kind == "dtn":
        expected_overrides = {
            "stage4_dtn_order_policy": "manual",
            "diffraction_order_max_m": probe.config.get(
                "diffraction_order_max_m"
            ),
            "diffraction_order_max_n": probe.config.get(
                "diffraction_order_max_n"
            ),
        }
    elif kind == "postprocess":
        expected_overrides = {
            "stage4_dtn_quadrature_degree": probe.config.get(
                "stage4_dtn_quadrature_degree"
            )
        }
    else:
        expected_overrides = {}
    override_values_well_formed = (
        (
            type(expected_overrides["diffraction_order_max_m"]) is int
            and expected_overrides["diffraction_order_max_m"] >= 0
            and type(expected_overrides["diffraction_order_max_n"]) is int
            and expected_overrides["diffraction_order_max_n"] >= 0
        )
        if kind == "dtn"
        else (
            type(
                expected_overrides["stage4_dtn_quadrature_degree"]
            )
            is int
            and expected_overrides["stage4_dtn_quadrature_degree"] >= 1
        )
        if kind == "postprocess"
        else True
    )
    checks = {
        "baseline_is_not_a_probe": (
            baseline.record.get("task035e_internal_probe") is None
        ),
        "schema_and_kind": (
            set(contract) == _PROBE_LAUNCH_KEYS
            and
            contract.get("schema_version") == PROBE_LAUNCH_SCHEMA
            and contract.get("selected") is True
            and contract.get("kind") == kind
        ),
        "formal_mpi8_scope": contract.get("mpi_size") == 8,
        "same_trial_cycle_current_role": (
            contract.get("trial_id") == baseline.adapted.trial_id
            and contract.get("cycle_index") == baseline.adapted.cycle_index
            and contract.get("output_role") == "current"
        ),
        "same_plan_and_snapshot": (
            contract.get("plan_file_sha256")
            == baseline.adapted.plan_file_sha256
            and contract.get("current_snapshot_file_sha256")
            == current_snapshot_file_sha256
        ),
        "only_kind_specific_overrides": (
            override_values_well_formed
            and contract.get("config_overrides") == expected_overrides
        ),
        "ordinary_default_unchanged": (
            contract.get("ordinary_default_changed") is False
        ),
    }
    return all(checks.values()), {
        "schema_version": contract.get("schema_version"),
        "kind": contract.get("kind"),
        "checks": checks,
        "contract_sha256": (
            _json_sha256(contract) if isinstance(row, Mapping) else None
        ),
    }


def _candidate_identity_matches(
    baseline: _CandidateContext,
    probe: _CandidateContext,
) -> bool:
    return all(
        (
            probe.adapted.source_sha == baseline.adapted.source_sha,
            probe.adapted.trial_id == baseline.adapted.trial_id,
            probe.adapted.cycle_index == baseline.adapted.cycle_index,
            probe.adapted.plan_file_sha256
            == baseline.adapted.plan_file_sha256,
            probe.adapted.forest_leaf_catalog_sha256
            == baseline.adapted.forest_leaf_catalog_sha256,
            probe.adapted.cell_degree_plan_sha256
            == baseline.adapted.cell_degree_plan_sha256,
            probe.adapted.carrier_connectivity_sha256
            == baseline.adapted.carrier_connectivity_sha256,
            probe.adapted.mesh_cell_box_catalog_sha256
            == baseline.adapted.mesh_cell_box_catalog_sha256,
            probe.adapted.geometry_canonical_entity_degree_sha256
            == baseline.adapted.geometry_canonical_entity_degree_sha256,
        )
    )


def _dtn_inventory(context: _CandidateContext) -> set[tuple[str, int, int, str]]:
    raw = _mapping(context.record.get("raw_evidence"), label="raw evidence")
    path = _safe_path(
        Path(str(raw.get("dtn_orders"))),
        label="DtN order artifact",
    )
    expected = _sha256(
        context.record.get("dtn_orders_sha256"),
        label="DtN order artifact SHA-256",
    )
    if not path.is_file() or _file_sha256(path) != expected:
        raise InternalGateAuthorityError("DtN order artifact hash differs")
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_reject_duplicate_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise InternalGateAuthorityError("DtN order artifact is invalid") from exc
    rows = _mapping(payload, label="DtN artifact").get("orders")
    if not isinstance(rows, list):
        raise InternalGateAuthorityError("DtN order inventory is absent")
    result: set[tuple[str, int, int, str]] = set()
    for row in rows:
        item = _mapping(row, label="DtN order")
        identity = (
            str(item.get("side")),
            int(item.get("m")),
            int(item.get("n")),
            str(item.get("polarization")),
        )
        if identity in result:
            raise InternalGateAuthorityError("DtN order inventory is duplicated")
        result.add(identity)
    return result


def _probe_identity(
    context: _CandidateContext,
    *,
    kind: str,
) -> dict[str, Any]:
    artifacts = {
        str(key): str(value)
        for key, value in context.adapted.artifact_sha256.items()
    }
    return {
        "kind": kind,
        "watchdog_record_file_sha256": context.record_file_sha256,
        "candidate_output_payload_sha256": context.adapted.output_sha256,
        "config_sha256": context.adapted.config_sha256,
        "plan_file_sha256": context.adapted.plan_file_sha256,
        "mesh_forest_sha256": context.adapted.forest_leaf_catalog_sha256,
        "degree_map_sha256": context.adapted.cell_degree_plan_sha256,
        "raw_artifact_sha256": artifacts,
        "raw_artifact_inventory_sha256": _json_sha256(artifacts),
        "structural_inventory": dict(context.adapted.structural_inventory),
    }


def _budget_measurement(
    baseline: _CandidateContext,
    probe: _CandidateContext,
    *,
    kind: str,
    current_snapshot_file_sha256: str,
) -> tuple[dict[str, Any], bool]:
    baseline_goals = _goal_vector_from_candidate_output(
        baseline.adapted.payload
    )
    probe_goals = _goal_vector_from_candidate_output(probe.adapted.payload)
    distances = dict(normalized_goal_distance(baseline_goals, probe_goals))
    maximum_goal = max(
        FORMAL_GOAL_IDS,
        key=lambda goal_id: distances[goal_id],
    )
    maximum = float(distances[maximum_goal])
    identity = _candidate_identity_matches(baseline, probe)
    ignored_config_fields = {"case_name"}
    if kind == "dtn":
        ignored_config_fields.update(
            {
                "stage4_dtn_order_policy",
                "diffraction_order_max_m",
                "diffraction_order_max_n",
            }
        )
    elif kind == "postprocess":
        ignored_config_fields.add("stage4_dtn_quadrature_degree")
    base_config = _normalized_config(
        baseline.config,
        ignore=frozenset(ignored_config_fields),
    )
    probe_config = _normalized_config(
        probe.config,
        ignore=frozenset(ignored_config_fields),
    )
    same_physics = base_config == probe_config
    probe_contract, probe_contract_detail = _probe_launch_contract(
        probe,
        kind=kind,
        baseline=baseline,
        current_snapshot_file_sha256=current_snapshot_file_sha256,
    )
    baseline_residual = float(
        baseline.adapted.payload["full_explicit_true_residual"]
    )
    probe_residual = float(
        probe.adapted.payload["full_explicit_true_residual"]
    )
    structural_equal = (
        dict(baseline.adapted.structural_inventory)
        == dict(probe.adapted.structural_inventory)
    )
    detail: dict[str, Any] = {
        "kind": kind,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "maximum_normalized_goal_distance": maximum,
        "maximum_goal_id": maximum_goal,
        "per_goal_normalized_distance_sha256": _json_sha256(distances),
        "same_source_trial_cycle_plan_mesh_degree": identity,
        "same_physics_config": same_physics,
        "formal_probe_launch_replayed": probe_contract,
        "formal_probe_launch": probe_contract_detail,
        "baseline_residual": baseline_residual,
        "probe_residual": probe_residual,
    }
    qualified = identity and same_physics and probe_contract
    if kind == "algebraic":
        direct_repeat = (
            structural_equal
            and probe_residual <= max(baseline_residual, 1.0e-15)
            and probe.record_file_sha256 != baseline.record_file_sha256
        )
        detail["same_structural_operator_inventory"] = structural_equal
        detail["probe_not_weaker_residual"] = (
            probe_residual <= max(baseline_residual, 1.0e-15)
        )
        detail["independent_record"] = (
            probe.record_file_sha256 != baseline.record_file_sha256
        )
        qualified = qualified and direct_repeat
    elif kind == "dtn":
        base_inventory = _dtn_inventory(baseline)
        probe_inventory = _dtn_inventory(probe)
        strict_superset = (
            base_inventory < probe_inventory
            and all(
                row in probe_inventory for row in base_inventory
            )
        )
        detail["baseline_order_count"] = len(base_inventory)
        detail["probe_order_count"] = len(probe_inventory)
        detail["strict_order_superset"] = strict_superset
        detail["baseline_order_inventory_sha256"] = _json_sha256(
            [list(row) for row in sorted(base_inventory)]
        )
        detail["probe_order_inventory_sha256"] = _json_sha256(
            [list(row) for row in sorted(probe_inventory)]
        )
        qualified = qualified and strict_superset
    elif kind == "postprocess":
        baseline_degree = baseline.summary.get(
            "stage4_dtn_surface_quadrature_degree"
        )
        probe_degree = probe.summary.get(
            "stage4_dtn_surface_quadrature_degree"
        )
        tighter = (
            type(baseline_degree) is int
            and type(probe_degree) is int
            and probe_degree > baseline_degree
        )
        detail["baseline_quadrature_degree"] = baseline_degree
        detail["probe_quadrature_degree"] = probe_degree
        detail["tighter_quadrature"] = tighter
        detail["same_structural_operator_inventory"] = structural_equal
        qualified = qualified and tighter and structural_equal
    else:
        raise AssertionError(f"unsupported budget kind: {kind}")
    detail["qualified_comparison"] = qualified
    detail["budget_fraction"] = maximum if qualified else max(1.0, maximum)
    return detail, qualified


def _complex_pair(value: Any, *, label: str) -> complex:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise InternalGateAuthorityError(f"{label} is not one complex pair")
    return complex(
        _finite(value[0], label=f"{label}.real"),
        _finite(value[1], label=f"{label}.imag"),
    )


def _serial_goal_vector(
    loaded: _LoadedJSON,
    *,
    baseline: _CandidateContext,
    current_snapshot_file_sha256: str,
) -> tuple[
    GoalVector,
    Mapping[str, Any],
    Mapping[str, Any],
    Mapping[str, str],
]:
    record = loaded.payload
    summary = _mapping(record.get("solver_summary"), label="MPI1 summary")
    raw = _mapping(record.get("raw_evidence"), label="MPI1 raw evidence")
    summary_path = _safe_path(
        Path(str(raw.get("solver_summary"))),
        label="MPI1 solver summary",
    )
    if (
        not summary_path.is_file()
        or _file_sha256(summary_path)
        != _sha256(
            record.get("solver_summary_sha256"),
            label="MPI1 solver summary SHA-256",
        )
    ):
        raise InternalGateAuthorityError("MPI1 solver summary hash differs")
    on_disk_summary = json.loads(
        summary_path.read_text(encoding="utf-8"),
        parse_constant=_reject_nonfinite,
        object_pairs_hook=_reject_duplicate_object,
    )
    if on_disk_summary != summary:
        raise InternalGateAuthorityError(
            "MPI1 embedded and on-disk solver summaries differ"
        )
    config = _mapping(summary.get("config"), label="MPI1 config")
    source = _mapping(record.get("source"), label="MPI1 source")
    local = _mapping(
        summary.get("stage4_local_h_constraint_audit"),
        label="MPI1 local-h authority",
    )
    mesh = _mapping(local.get("mesh"), label="MPI1 local-h mesh")
    degree = _mapping(local.get("degree_plan"), label="MPI1 degree plan")
    forest = _mapping(mesh.get("forest"), label="MPI1 forest")
    structural = {
        "matrix_rows": int(
            _mapping(summary.get("matrix_stats"), label="MPI1 matrix").get(
                "matrix_rows"
            )
        ),
        "matrix_nnz": int(
            _mapping(summary.get("matrix_stats"), label="MPI1 matrix").get(
                "matrix_nnz_used"
            )
        ),
        "factor_nnz": int(
            _mapping(
                _mapping(
                    summary.get("stage4_dtn_factor_inventory"),
                    label="MPI1 factor inventory",
                ).get("matrix_stats"),
                label="MPI1 factor matrix",
            ).get("matrix_nnz_used")
        ),
    }
    baseline_structural = baseline.adapted.structural_inventory
    probe_contract = record.get("task035e_internal_probe")
    probe_contract = (
        probe_contract if isinstance(probe_contract, Mapping) else {}
    )
    identity_checks = {
        "formal_serial_probe_contract": (
            set(probe_contract) == _PROBE_LAUNCH_KEYS
            and probe_contract.get("schema_version") == PROBE_LAUNCH_SCHEMA
            and probe_contract.get("selected") is True
            and probe_contract.get("kind") == "serial_mpi1"
            and probe_contract.get("mpi_size") == 1
            and probe_contract.get("trial_id")
            == baseline.adapted.trial_id
            and probe_contract.get("cycle_index")
            == baseline.adapted.cycle_index
            and probe_contract.get("output_role") == "current"
            and probe_contract.get("plan_file_sha256")
            == baseline.adapted.plan_file_sha256
            and probe_contract.get("current_snapshot_file_sha256")
            == current_snapshot_file_sha256
            and probe_contract.get("config_overrides") == {}
            and probe_contract.get("ordinary_default_changed") is False
        ),
        "completed_direct_mumps_mpi1": (
            record.get("mpi_size") == 1
            and summary.get("mpi_size") == 1
            and record.get(
                "task035e_" + "ref" + "erence_certifier"
            )
            is None
            and summary.get("case_status") == "completed"
            and summary.get("official_result") is True
            and summary.get("linear_solve_method") == "direct_lu"
            and summary.get("selected_parallel_lu_solver_type") == "mumps"
            and summary.get("ksp_converged") is True
            and record.get("no_swap") is True
        ),
        "same_clean_source": (
            source.get("commit_sha") == baseline.adapted.source_sha
            and source.get("head_after_sha") == baseline.adapted.source_sha
            and source.get("tracked_source_dirty") is False
            and source.get("stable_and_clean_after") is True
        ),
        "same_plan_mesh_degree": (
            mesh.get("plan_file_sha256")
            == baseline.adapted.plan_file_sha256
            and forest.get("leaf_catalog_sha256")
            == baseline.adapted.forest_leaf_catalog_sha256
            and degree.get("cell_degree_plan_sha256")
            == baseline.adapted.cell_degree_plan_sha256
        ),
        "same_physics_config": (
            _normalized_config(
                config,
                ignore=frozenset({"case_name"}),
            )
            == _normalized_config(
                baseline.config,
                ignore=frozenset({"case_name"}),
            )
        ),
        "same_global_matrix_and_factor_inventory": (
            structural["matrix_rows"]
            == int(baseline_structural["matrix_rows"])
            and structural["matrix_nnz"]
            == int(baseline_structural["matrix_nnz"])
            and structural["factor_nnz"]
            == int(baseline_structural["factor_nnz"])
        ),
    }
    dtn_path = _safe_path(
        Path(str(raw.get("dtn_orders"))),
        label="MPI1 DtN artifact",
    )
    if (
        not dtn_path.is_file()
        or _file_sha256(dtn_path)
        != _sha256(
            record.get("dtn_orders_sha256"),
            label="MPI1 DtN artifact SHA-256",
        )
    ):
        raise InternalGateAuthorityError("MPI1 DtN artifact hash differs")
    dtn = json.loads(
        dtn_path.read_text(encoding="utf-8"),
        parse_constant=_reject_nonfinite,
        object_pairs_hook=_reject_duplicate_object,
    )
    rows = _mapping(dtn, label="MPI1 DtN artifact").get("orders")
    if not isinstance(rows, list):
        raise InternalGateAuthorityError("MPI1 DtN orders are absent")
    indexed: dict[tuple[str, int, int, str], Mapping[str, Any]] = {}
    for raw_row in rows:
        row = _mapping(raw_row, label="MPI1 DtN order")
        key = (
            str(row.get("side")),
            int(row.get("m")),
            int(row.get("n")),
            str(row.get("polarization")),
        )
        if key in indexed:
            raise InternalGateAuthorityError("MPI1 DtN order is duplicated")
        indexed[key] = row
    values: dict[str, float] = {}
    for port, m, n in FIXED_ORDER_KEYS:
        s = indexed.get((port, m, n, "s"))
        p = indexed.get((port, m, n, "p"))
        if s is None or p is None:
            raise InternalGateAuthorityError("MPI1 misses one fixed order")
        propagating = s.get("propagating")
        if type(propagating) is not bool or p.get("propagating") is not propagating:
            raise InternalGateAuthorityError("MPI1 order applicability differs")
        if propagating:
            power = _finite(
                s.get("power_ratio"),
                label="MPI1 S power",
            ) + _finite(p.get("power_ratio"), label="MPI1 P power")
        else:
            power = 0.0
        amplitude = _complex_pair(
            s.get("outgoing_amplitude_at_boundary"),
            label="MPI1 co amplitude",
        )
        prefix = f"{port}:m{m}:n{n}"
        values[f"{prefix}:power"] = power
        values[f"{prefix}:co_amp_real"] = float(amplitude.real)
        values[f"{prefix}:co_amp_imag"] = float(amplitude.imag)
    totals = {
        "R00_total": summary.get("R00_total"),
        "R_total": summary.get("R_total"),
        "T_total": summary.get("T_total"),
        "A_closure": summary.get("A_balance"),
        "A_volume": summary.get("A_volume_total"),
    }
    values.update(
        {
            f"scalar/{name}": _finite(value, label=f"MPI1 {name}")
            for name, value in totals.items()
        }
    )
    metadata_path = _safe_path(
        Path(str(raw.get("reference_metadata"))),
        label="MPI1 field metadata",
    )
    if (
        not metadata_path.is_file()
        or _file_sha256(metadata_path)
        != _sha256(
            record.get("reference_metadata_sha256"),
            label="MPI1 field metadata SHA-256",
        )
    ):
        raise InternalGateAuthorityError("MPI1 field metadata hash differs")
    metadata = json.loads(
        metadata_path.read_text(encoding="utf-8"),
        parse_constant=_reject_nonfinite,
        object_pairs_hook=_reject_duplicate_object,
    )
    metadata = _mapping(metadata, label="MPI1 field metadata")
    archive_path = (metadata_path.parent / str(metadata.get("archive"))).resolve()
    if (
        not archive_path.is_file()
        or _file_sha256(archive_path)
        != _sha256(
            metadata.get("archive_sha256"),
            label="MPI1 field archive SHA-256",
        )
    ):
        raise InternalGateAuthorityError("MPI1 field archive hash differs")
    with np.load(archive_path, allow_pickle=False) as archive:
        electric = np.asarray(archive["E_V_per_m"])
        interface = np.asarray(archive["E_t_interface_V_per_m"])
        middle_indices = np.asarray(
            metadata.get("middle_plane_indices"),
            dtype=np.int64,
        )
        middle = electric[middle_indices]
        values[
            f"scalar/{FORMAL_FIELD_SCALAR_NAMES[0]}"
        ] = float(np.linalg.norm(interface.ravel()))
        values[
            f"scalar/{FORMAL_FIELD_SCALAR_NAMES[1]}"
        ] = float(np.linalg.norm(middle.ravel()))
        interface_mean = complex(np.mean(interface))
        middle_mean = complex(np.mean(middle))
    for name, value in (
        (FORMAL_FIELD_COMPLEX_NAMES[0], interface_mean),
        (FORMAL_FIELD_COMPLEX_NAMES[1], middle_mean),
    ):
        values[f"complex/{name}/real"] = float(value.real)
        values[f"complex/{name}/imag"] = float(value.imag)
    volume_path = _safe_path(
        Path(str(raw.get("volume_absorption"))),
        label="MPI1 volume absorption",
    )
    volume_sha = _sha256(
        record.get("volume_absorption_sha256"),
        label="MPI1 volume absorption SHA-256",
    )
    if not volume_path.is_file() or _file_sha256(volume_path) != volume_sha:
        raise InternalGateAuthorityError(
            "MPI1 volume-absorption artifact hash differs"
        )
    volume = json.loads(
        volume_path.read_text(encoding="utf-8"),
        parse_constant=_reject_nonfinite,
        object_pairs_hook=_reject_duplicate_object,
    )
    if not math.isclose(
        _finite(
            _mapping(volume, label="MPI1 volume absorption").get(
                "A_volume_total"
            ),
            label="MPI1 volume A",
        ),
        float(values["scalar/A_volume"]),
        rel_tol=0.0,
        abs_tol=1.0e-15,
    ):
        raise InternalGateAuthorityError(
            "MPI1 volume artifact and summary differ"
        )
    artifacts = {
        "watchdog_record": loaded.file_sha256,
        "solver_summary": _file_sha256(summary_path),
        "dtn_orders": _file_sha256(dtn_path),
        "volume_absorption": volume_sha,
        "field_metadata": _file_sha256(metadata_path),
        "field_archive": _file_sha256(archive_path),
    }
    return (
        GoalVector.from_mapping(values),
        identity_checks,
        structural,
        artifacts,
    )


def _serial_identity_measurement(
    serial_bound: BoundJSONInput | None,
    *,
    baseline: _CandidateContext,
    current_snapshot_file_sha256: str,
) -> tuple[dict[str, Any], bool, dict[str, Any] | None]:
    if serial_bound is None:
        return (
            {
                "status": "not_run",
                "reason": (
                    "optional MPI1 same-plan diagnostic was not supplied; "
                    "MPI2 is neither required nor accepted"
                ),
                "mpi8_rank_plan_snapshot_identity_pass": True,
                "maximum_normalized_goal_distance": None,
                "limit": SERIAL_MPI_MAXIMUM_NORMALIZED_DISTANCE,
            },
            False,
            None,
        )
    loaded = _load_bound_json(serial_bound, label="optional MPI1 record")
    (
        serial_goals,
        identity_checks,
        structural,
        serial_artifacts,
    ) = _serial_goal_vector(
        loaded,
        baseline=baseline,
        current_snapshot_file_sha256=current_snapshot_file_sha256,
    )
    baseline_goals = _goal_vector_from_candidate_output(
        baseline.adapted.payload
    )
    distances = dict(normalized_goal_distance(baseline_goals, serial_goals))
    maximum_goal = max(
        FORMAL_GOAL_IDS,
        key=lambda goal_id: distances[goal_id],
    )
    maximum = float(distances[maximum_goal])
    residual = _finite(
        _mapping(
            loaded.payload.get("solver_summary"),
            label="MPI1 summary",
        ).get("linear_system_relative_residual"),
        label="MPI1 true residual",
    )
    passed = (
        all(identity_checks.values())
        and residual <= 1.0e-9
        and maximum <= SERIAL_MPI_MAXIMUM_NORMALIZED_DISTANCE
    )
    return (
        {
            "status": "qualified" if passed else "failed",
            "reason": None if passed else "MPI1 comparison Gate failed",
            "mpi8_rank_plan_snapshot_identity_pass": True,
            "maximum_normalized_goal_distance": maximum,
            "maximum_goal_id": maximum_goal,
            "limit": SERIAL_MPI_MAXIMUM_NORMALIZED_DISTANCE,
            "true_residual": residual,
            "identity_checks": identity_checks,
            "per_goal_normalized_distance_sha256": _json_sha256(distances),
            "structural_inventory": dict(structural),
        },
        passed,
        {
            "kind": "serial_mpi1",
            "watchdog_record_file_sha256": loaded.file_sha256,
            "candidate_output_payload_sha256": serial_goals.sha256,
            "config_sha256": _json_sha256(
                _mapping(
                    _mapping(
                        loaded.payload.get("solver_summary"),
                        label="MPI1 summary",
                    ).get("config"),
                    label="MPI1 config",
                )
            ),
            "plan_file_sha256": baseline.adapted.plan_file_sha256,
            "mesh_forest_sha256": (
                baseline.adapted.forest_leaf_catalog_sha256
            ),
            "degree_map_sha256": baseline.adapted.cell_degree_plan_sha256,
            "raw_artifact_sha256": dict(serial_artifacts),
            "raw_artifact_inventory_sha256": _json_sha256(
                serial_artifacts
            ),
            "structural_inventory": dict(structural),
        },
    )


def _scalar(candidate: Mapping[str, Any], name: str) -> float:
    rows = candidate.get("scalar_observations")
    if not isinstance(rows, list):
        raise InternalGateAuthorityError("candidate scalars are absent")
    values = [
        row.get("value")
        for row in rows
        if isinstance(row, Mapping) and row.get("name") == name
    ]
    if len(values) != 1:
        raise InternalGateAuthorityError(f"candidate scalar {name} differs")
    return _finite(values[0], label=f"candidate scalar {name}")


def _producer_identity() -> dict[str, Any]:
    path = Path(__file__).resolve()
    algorithm = {
        "schema_version": AUTHORITY_SCHEMA,
        "floquet_residual_limit": FLOQUET_RESIDUAL_LIMIT,
        "hanging_residual_limit": HANGING_RESIDUAL_LIMIT,
        "budget_fraction_limit": BUDGET_FRACTION_LIMIT,
        "serial_mpi_maximum_normalized_distance": (
            SERIAL_MPI_MAXIMUM_NORMALIZED_DISTANCE
        ),
        "budget_metric": (
            "maximum absolute 59-goal delta divided by the reference-blind "
            "goal tolerance"
        ),
    }
    return {
        "source": "benchmarks/task035e_internal_gate_authority.py",
        "file_sha256": _file_sha256(path),
        "algorithm_sha256": _json_sha256(algorithm),
    }


def _current_authority_evidence(
    *,
    candidate_record: BoundJSONInput,
    candidate_output: BoundJSONInput,
    current_plan: BoundJSONInput,
    current_snapshot: BoundJSONInput,
) -> _CurrentAuthorityEvidence:
    """Replay all current-state checks shared by final and deferred authority."""

    current = _load_candidate(candidate_record, label="current watchdog record")
    candidate_payload, candidate_file_sha = _load_candidate_output(
        candidate_output,
        current=current,
    )
    plan_payload, plan_payload_sha = _load_plan(
        current_plan,
        current=current,
    )
    snapshot, snapshot_checks = _snapshot_identity(
        current_snapshot,
        current=current,
        plan_payload=plan_payload,
        candidate_payload=candidate_payload,
    )
    if not all(snapshot_checks.values()):
        failed = [name for name, passed in snapshot_checks.items() if not passed]
        raise InternalGateAuthorityError(
            f"current snapshot identity failed: {failed}"
        )
    floquet, hanging, constraint_checks = (
        _floquet_and_hanging_measurements(current)
    )
    multilevel, multilevel_checks = _multilevel_measurements(current)
    floquet_pass = all(
        constraint_checks[name]
        for name in (
            "physical_trace_authority",
            "trace_constraint_authority",
            "floquet_constraints_present",
            "periodic_cycle_residual_within_limit",
            "summary_floquet_residual_consistent_or_not_applicable",
        )
    )
    hanging_pass = all(
        constraint_checks[name]
        for name in (
            "physical_trace_authority",
            "trace_constraint_authority",
            "hanging_constraints_present",
            "flattened_relation_residual_within_limit",
        )
    )
    multilevel_pass = all(multilevel_checks.values())
    energy_error = abs(_scalar(candidate_payload, "energy_closure") - 1.0)
    absorption = _scalar(candidate_payload, "A_volume")
    base_gates = {
        "full_explicit_residual": snapshot["full_explicit_residual"],
        "energy_closure_error": energy_error,
        "absorption_volume": absorption,
        "floquet_residual_pass": floquet_pass,
        "hanging_residual_pass": hanging_pass,
        "multilevel_mesh_pass": multilevel_pass,
        "separated_patch_count": int(multilevel["separated_patch_count"]),
        "all_local_levels_present": (
            multilevel_checks["all_local_levels_present"]
        ),
    }
    current_artifacts = {
        str(key): str(value)
        for key, value in current.adapted.artifact_sha256.items()
    }
    candidate_identity = {
        "watchdog_record_file_sha256": current.record_file_sha256,
        "candidate_output_file_sha256": candidate_file_sha,
        "candidate_output_payload_sha256": current.adapted.output_sha256,
        "plan_file_sha256": current.adapted.plan_file_sha256,
        "plan_payload_sha256": plan_payload_sha,
        "mesh_forest_sha256": current.adapted.forest_leaf_catalog_sha256,
        "degree_map_sha256": current.adapted.cell_degree_plan_sha256,
        "current_snapshot_file_sha256": snapshot["file_sha256"],
        "current_snapshot_payload_sha256": snapshot["payload_sha256"],
        "snapshot_rank_bound_identity_sha256": snapshot[
            "rank_bound_identity_sha256"
        ],
        "snapshot_full_residual_sha256": snapshot[
            "full_residual_sha256"
        ],
        "raw_artifact_sha256": current_artifacts,
        "raw_artifact_inventory_sha256": _json_sha256(current_artifacts),
        "structural_inventory": dict(current.adapted.structural_inventory),
    }
    return _CurrentAuthorityEvidence(
        current=current,
        candidate_payload=candidate_payload,
        candidate_file_sha256=candidate_file_sha,
        plan_payload_sha256=plan_payload_sha,
        snapshot=snapshot,
        snapshot_checks=snapshot_checks,
        floquet=floquet,
        hanging=hanging,
        constraint_checks=constraint_checks,
        multilevel=multilevel,
        multilevel_checks=multilevel_checks,
        base_gates=base_gates,
        candidate_identity=candidate_identity,
    )


def build_internal_gate_authority(
    *,
    candidate_record: BoundJSONInput,
    candidate_output: BoundJSONInput,
    current_plan: BoundJSONInput,
    current_snapshot: BoundJSONInput,
    algebraic_probe_record: BoundJSONInput,
    dtn_probe_record: BoundJSONInput,
    postprocess_probe_record: BoundJSONInput,
    serial_mpi1_record: BoundJSONInput | None = None,
) -> dict[str, Any]:
    """Build one closed authority without accepting any caller Gate value."""

    evidence = _current_authority_evidence(
        candidate_record=candidate_record,
        candidate_output=candidate_output,
        current_plan=current_plan,
        current_snapshot=current_snapshot,
    )
    current = evidence.current
    snapshot_checks = evidence.snapshot_checks
    probes = {
        "algebraic": _load_candidate(
            algebraic_probe_record,
            label="algebraic probe watchdog record",
        ),
        "dtn": _load_candidate(
            dtn_probe_record,
            label="DtN probe watchdog record",
        ),
        "postprocess": _load_candidate(
            postprocess_probe_record,
            label="postprocess probe watchdog record",
        ),
    }
    record_hashes = {
        current.record_file_sha256,
        *(probe.record_file_sha256 for probe in probes.values()),
    }
    if len(record_hashes) != 4:
        raise InternalGateAuthorityError(
            "current and three probe records must be byte-distinct artifacts"
        )
    budget_measurements: dict[str, Any] = {}
    budget_qualified: dict[str, bool] = {}
    for kind, probe in probes.items():
        measurement, qualified = _budget_measurement(
            current,
            probe,
            kind=kind,
            current_snapshot_file_sha256=current_snapshot.sha256,
        )
        budget_measurements[kind] = measurement
        budget_qualified[kind] = qualified
    mpi8_identity_pass = all(snapshot_checks.values())
    serial_measurement, serial_pass, serial_identity = (
        _serial_identity_measurement(
            serial_mpi1_record,
            baseline=current,
            current_snapshot_file_sha256=current_snapshot.sha256,
        )
    )
    gates = {
        **evidence.base_gates,
        "serial_mpi_identity_pass": serial_pass,
        "algebraic_budget_fraction": float(
            budget_measurements["algebraic"]["budget_fraction"]
        ),
        "dtn_budget_fraction": float(
            budget_measurements["dtn"]["budget_fraction"]
        ),
        "postprocess_budget_fraction": float(
            budget_measurements["postprocess"]["budget_fraction"]
        ),
    }
    InternalGates(**gates)
    probe_identities = [
        _probe_identity(probes[kind], kind=kind)
        for kind in ("algebraic", "dtn", "postprocess")
    ]
    if serial_identity is not None:
        probe_identities.append(serial_identity)
    unsigned: dict[str, Any] = {
        "schema_version": AUTHORITY_SCHEMA,
        "status": FINAL_AUTHORITY_STATUS,
        "classification": FINAL_AUTHORITY_CLASSIFICATION,
        "source_sha": current.adapted.source_sha,
        "trial_id": current.adapted.trial_id,
        "cycle_index": current.adapted.cycle_index,
        "mpi_size": 8,
        "candidate_identity": dict(evidence.candidate_identity),
        "probe_identities": probe_identities,
        "measurements": {
            "floquet": dict(evidence.floquet),
            "hanging": dict(evidence.hanging),
            "mpi_identity": serial_measurement,
            "multilevel": dict(evidence.multilevel),
            "budgets": budget_measurements,
        },
        "recomputed_checks": {
            "snapshot": snapshot_checks,
            "constraint": dict(evidence.constraint_checks),
            "multilevel": dict(evidence.multilevel_checks),
            "budget_probe_qualified": budget_qualified,
            "mpi8_candidate_plan_snapshot_identity": mpi8_identity_pass,
            "serial_mpi1_same_plan_output_identity": serial_pass,
        },
        "gates": gates,
        "producer": _producer_identity(),
    }
    return {
        **unsigned,
        "authority_sha256": _json_sha256(
            unsigned,
            namespace=AUTHORITY_NAMESPACE,
        ),
    }


def build_deferred_internal_gate_authority(
    *,
    candidate_record: BoundJSONInput,
    candidate_output: BoundJSONInput,
    current_plan: BoundJSONInput,
    current_snapshot: BoundJSONInput,
) -> dict[str, Any]:
    """Build a conservative intermediate-cycle authority without probes.

    The current MPI8 solve, executed plan, snapshot, residual, energy balance,
    physical/cell trace constraints, and multilevel topology are replayed
    exactly as for the final authority.  Expensive algebraic, DtN, postprocess,
    and optional MPI1 comparisons are deliberately not credited: every budget
    fraction is fixed to one, every probe qualification is false, and the
    resulting :class:`InternalGates` can never satisfy ``freeze_passed``.
    """

    evidence = _current_authority_evidence(
        candidate_record=candidate_record,
        candidate_output=candidate_output,
        current_plan=current_plan,
        current_snapshot=current_snapshot,
    )
    current = evidence.current
    budget_measurements = {
        kind: {
            "kind": kind,
            "status": "deferred_not_run",
            "formal_goal_count": len(FORMAL_GOAL_IDS),
            "qualified_comparison": False,
            "budget_fraction": 1.0,
            "probe_credit": False,
            "reason": "intermediate_cycle_probe_not_run",
        }
        for kind in ("algebraic", "dtn", "postprocess")
    }
    budget_qualified = {
        kind: False for kind in ("algebraic", "dtn", "postprocess")
    }
    serial_measurement, serial_pass, serial_identity = (
        _serial_identity_measurement(
            None,
            baseline=current,
            current_snapshot_file_sha256=current_snapshot.sha256,
        )
    )
    if serial_pass or serial_identity is not None:
        raise AssertionError("deferred authority unexpectedly gained MPI1 credit")
    gates = {
        **evidence.base_gates,
        "serial_mpi_identity_pass": False,
        "algebraic_budget_fraction": 1.0,
        "dtn_budget_fraction": 1.0,
        "postprocess_budget_fraction": 1.0,
    }
    gate_state = InternalGates(**gates)
    if gate_state.freeze_passed:
        raise AssertionError("deferred authority must never pass the freeze Gate")
    unsigned: dict[str, Any] = {
        "schema_version": AUTHORITY_SCHEMA,
        "status": DEFERRED_AUTHORITY_STATUS,
        "classification": DEFERRED_AUTHORITY_CLASSIFICATION,
        "source_sha": current.adapted.source_sha,
        "trial_id": current.adapted.trial_id,
        "cycle_index": current.adapted.cycle_index,
        "mpi_size": 8,
        "candidate_identity": dict(evidence.candidate_identity),
        "probe_identities": [],
        "measurements": {
            "floquet": dict(evidence.floquet),
            "hanging": dict(evidence.hanging),
            "mpi_identity": serial_measurement,
            "multilevel": dict(evidence.multilevel),
            "budgets": budget_measurements,
        },
        "recomputed_checks": {
            "snapshot": dict(evidence.snapshot_checks),
            "constraint": dict(evidence.constraint_checks),
            "multilevel": dict(evidence.multilevel_checks),
            "budget_probe_qualified": budget_qualified,
            "mpi8_candidate_plan_snapshot_identity": all(
                evidence.snapshot_checks.values()
            ),
            "serial_mpi1_same_plan_output_identity": False,
        },
        "gates": gates,
        "producer": _producer_identity(),
    }
    return {
        **unsigned,
        "authority_sha256": _json_sha256(
            unsigned,
            namespace=AUTHORITY_NAMESPACE,
        ),
    }


def validate_internal_gate_authority(
    payload: Mapping[str, Any],
    *,
    expected_source_sha: str | None = None,
    expected_trial_id: str | None = None,
    expected_cycle_index: int | None = None,
    expected_candidate_record_file_sha256: str | None = None,
    expected_candidate_output_file_sha256: str | None = None,
    expected_candidate_output_payload_sha256: str | None = None,
    expected_plan_file_sha256: str | None = None,
    expected_plan_payload_sha256: str | None = None,
    expected_mesh_forest_sha256: str | None = None,
    expected_degree_map_sha256: str | None = None,
    expected_snapshot_file_sha256: str | None = None,
    expected_snapshot_payload_sha256: str | None = None,
    expected_snapshot_full_residual_sha256: str | None = None,
) -> Mapping[str, Any]:
    """Validate the closed authority for a later cycle-binding consumer."""

    row = _exact(
        payload,
        _AUTHORITY_KEYS,
        label="internal-Gate authority",
    )
    role = (row["status"], row["classification"])
    final_role = (
        FINAL_AUTHORITY_STATUS,
        FINAL_AUTHORITY_CLASSIFICATION,
    )
    deferred_role = (
        DEFERRED_AUTHORITY_STATUS,
        DEFERRED_AUTHORITY_CLASSIFICATION,
    )
    if (
        row["schema_version"] != AUTHORITY_SCHEMA
        or role not in {final_role, deferred_role}
        or row["mpi_size"] != 8
    ):
        raise InternalGateAuthorityError(
            "internal-Gate authority role/schema/MPI identity differs"
        )
    deferred = role == deferred_role
    unsigned = dict(row)
    stored_sha = _sha256(
        unsigned.pop("authority_sha256"),
        label="internal-Gate authority SHA-256",
    )
    if (
        _json_sha256(unsigned, namespace=AUTHORITY_NAMESPACE)
        != stored_sha
    ):
        raise InternalGateAuthorityError(
            "internal-Gate authority self-hash differs"
        )
    source = _source_sha(row["source_sha"])
    cycle = row["cycle_index"]
    if type(cycle) is not int or not 0 <= cycle <= 5:
        raise InternalGateAuthorityError(
            "internal-Gate authority cycle index differs"
        )
    candidate = _exact(
        row["candidate_identity"],
        _CANDIDATE_IDENTITY_KEYS,
        label="internal-Gate candidate identity",
    )
    for name in (
        "watchdog_record_file_sha256",
        "candidate_output_file_sha256",
        "candidate_output_payload_sha256",
        "plan_file_sha256",
        "plan_payload_sha256",
        "mesh_forest_sha256",
        "degree_map_sha256",
        "current_snapshot_file_sha256",
        "current_snapshot_payload_sha256",
        "snapshot_rank_bound_identity_sha256",
        "snapshot_full_residual_sha256",
        "raw_artifact_inventory_sha256",
    ):
        _sha256(candidate[name], label=name)
    probe_rows = row["probe_identities"]
    valid_probe_count = (
        isinstance(probe_rows, list)
        and (
            len(probe_rows) == 0
            if deferred
            else len(probe_rows) in {3, 4}
        )
    )
    if not valid_probe_count:
        raise InternalGateAuthorityError(
            "internal-Gate probe inventory differs from its classification"
        )
    expected_kinds = ["algebraic", "dtn", "postprocess"]
    if deferred:
        expected_kinds = []
    elif len(probe_rows) == 4:
        expected_kinds.append("serial_mpi1")
    for raw, kind in zip(probe_rows, expected_kinds, strict=True):
        probe = _exact(
            raw,
            _PROBE_IDENTITY_KEYS,
            label=f"{kind} probe identity",
        )
        if probe["kind"] != kind:
            raise InternalGateAuthorityError(
                "internal-Gate probe order differs"
            )
        for name in (
            "watchdog_record_file_sha256",
            "candidate_output_payload_sha256",
            "config_sha256",
            "plan_file_sha256",
            "mesh_forest_sha256",
            "degree_map_sha256",
            "raw_artifact_inventory_sha256",
        ):
            _sha256(probe[name], label=f"{kind}.{name}")
    gates = _exact(row["gates"], _GATE_KEYS, label="recomputed internal Gates")
    try:
        gate_state = InternalGates(**dict(gates))
    except (TypeError, ValueError) as exc:
        raise InternalGateAuthorityError(str(exc)) from exc
    measurements = _exact(
        row["measurements"],
        _MEASUREMENT_KEYS,
        label="internal-Gate measurements",
    )
    budgets = _exact(
        measurements["budgets"],
        {"algebraic", "dtn", "postprocess"},
        label="internal-Gate budget measurements",
    )
    checks = _exact(
        row["recomputed_checks"],
        _RECOMPUTED_CHECK_KEYS,
        label="internal-Gate recomputed checks",
    )
    snapshot_checks = _exact(
        checks["snapshot"],
        _SNAPSHOT_CHECK_KEYS,
        label="internal-Gate snapshot checks",
    )
    constraint_checks = _exact(
        checks["constraint"],
        _CONSTRAINT_CHECK_KEYS,
        label="internal-Gate constraint checks",
    )
    multilevel_checks = _exact(
        checks["multilevel"],
        _MULTILEVEL_CHECK_KEYS,
        label="internal-Gate multilevel checks",
    )
    budget_checks = _exact(
        checks["budget_probe_qualified"],
        {"algebraic", "dtn", "postprocess"},
        label="internal-Gate budget checks",
    )
    if (
        any(type(value) is not bool for value in snapshot_checks.values())
        or any(type(value) is not bool for value in constraint_checks.values())
        or any(type(value) is not bool for value in multilevel_checks.values())
        or any(type(value) is not bool for value in budget_checks.values())
        or checks["mpi8_candidate_plan_snapshot_identity"] is not True
        or type(checks["serial_mpi1_same_plan_output_identity"]) is not bool
    ):
        raise InternalGateAuthorityError(
            "internal-Gate recomputed checks are malformed"
        )
    if not all(snapshot_checks.values()):
        raise InternalGateAuthorityError(
            "internal-Gate authority lacks a qualified current snapshot"
        )
    expected_floquet = all(
        constraint_checks[name]
        for name in (
            "physical_trace_authority",
            "trace_constraint_authority",
            "floquet_constraints_present",
            "periodic_cycle_residual_within_limit",
            "summary_floquet_residual_consistent_or_not_applicable",
        )
    )
    expected_hanging = all(
        constraint_checks[name]
        for name in (
            "physical_trace_authority",
            "trace_constraint_authority",
            "hanging_constraints_present",
            "flattened_relation_residual_within_limit",
        )
    )
    if (
        gates["floquet_residual_pass"] is not expected_floquet
        or gates["hanging_residual_pass"] is not expected_hanging
        or gates["multilevel_mesh_pass"]
        is not all(multilevel_checks.values())
        or gates["all_local_levels_present"]
        is not multilevel_checks["all_local_levels_present"]
        or gates["separated_patch_count"]
        != _mapping(
            measurements["multilevel"],
            label="multilevel measurement",
        ).get("separated_patch_count")
    ):
        raise InternalGateAuthorityError(
            "internal-Gate booleans do not match recomputed checks"
        )
    for kind, gate_name in (
        ("algebraic", "algebraic_budget_fraction"),
        ("dtn", "dtn_budget_fraction"),
        ("postprocess", "postprocess_budget_fraction"),
    ):
        detail = (
            _exact(
                budgets[kind],
                _DEFERRED_BUDGET_KEYS,
                label=f"{kind} deferred budget measurement",
            )
            if deferred
            else _mapping(
                budgets[kind],
                label=f"{kind} budget measurement",
            )
        )
        fraction = _finite(
            detail.get("budget_fraction"),
            label=f"{kind} budget fraction",
        )
        common_budget_failure = (
            detail.get("kind") != kind
            or type(detail.get("qualified_comparison")) is not bool
            or detail["qualified_comparison"] is not budget_checks[kind]
            or not math.isclose(
                float(gates[gate_name]),
                fraction,
                rel_tol=0.0,
                abs_tol=0.0,
            )
            or (
                not budget_checks[kind]
                and fraction < 1.0
            )
        )
        deferred_budget_failure = deferred and (
            detail.get("status") != "deferred_not_run"
            or detail.get("formal_goal_count") != len(FORMAL_GOAL_IDS)
            or detail.get("qualified_comparison") is not False
            or detail.get("probe_credit") is not False
            or detail.get("reason") != "intermediate_cycle_probe_not_run"
            or budget_checks[kind] is not False
            or fraction < 1.0
        )
        if common_budget_failure or deferred_budget_failure:
            raise InternalGateAuthorityError(
                f"{kind} budget authority does not replay"
            )
    mpi_measurement = _mapping(
        measurements["mpi_identity"],
        label="MPI identity measurement",
    )
    serial_gate = bool(gates["serial_mpi_identity_pass"])
    has_serial_probe = len(probe_rows) == 4
    if (
        serial_gate
        is not checks["serial_mpi1_same_plan_output_identity"]
        or serial_gate is not (mpi_measurement.get("status") == "qualified")
        or serial_gate and not has_serial_probe
        or not has_serial_probe
        and (
            mpi_measurement.get("status") != "not_run"
            or serial_gate
        )
    ):
        raise InternalGateAuthorityError(
            "serial/MPI identity authority does not replay"
        )
    if deferred and (
        serial_gate
        or checks["serial_mpi1_same_plan_output_identity"]
        or mpi_measurement.get("status") != "not_run"
        or gate_state.freeze_passed
    ):
        raise InternalGateAuthorityError(
            "deferred authority gained final probe or freeze credit"
        )
    producer = _exact(
        row["producer"],
        _PRODUCER_KEYS,
        label="internal-Gate producer",
    )
    if dict(producer) != _producer_identity():
        raise InternalGateAuthorityError(
            "internal-Gate producer implementation identity differs"
        )
    if expected_source_sha is not None and source != _source_sha(
        expected_source_sha
    ):
        raise InternalGateAuthorityError("authority source SHA differs")
    if expected_trial_id is not None and row["trial_id"] != expected_trial_id:
        raise InternalGateAuthorityError("authority trial ID differs")
    if (
        expected_cycle_index is not None
        and cycle != expected_cycle_index
    ):
        raise InternalGateAuthorityError("authority cycle index differs")
    expected_bindings = (
        (
            expected_candidate_record_file_sha256,
            "watchdog_record_file_sha256",
        ),
        (
            expected_candidate_output_file_sha256,
            "candidate_output_file_sha256",
        ),
        (
            expected_candidate_output_payload_sha256,
            "candidate_output_payload_sha256",
        ),
        (expected_plan_file_sha256, "plan_file_sha256"),
        (expected_plan_payload_sha256, "plan_payload_sha256"),
        (expected_mesh_forest_sha256, "mesh_forest_sha256"),
        (expected_degree_map_sha256, "degree_map_sha256"),
        (
            expected_snapshot_file_sha256,
            "current_snapshot_file_sha256",
        ),
        (
            expected_snapshot_payload_sha256,
            "current_snapshot_payload_sha256",
        ),
        (
            expected_snapshot_full_residual_sha256,
            "snapshot_full_residual_sha256",
        ),
    )
    for expected, name in expected_bindings:
        if expected is not None and candidate[name] != _sha256(
            expected,
            label=f"expected {name}",
        ):
            raise InternalGateAuthorityError(
                f"authority {name} differs from cycle context"
            )
    return row


def _publish_internal_gate_authority(
    output_path: Path,
    payload: Mapping[str, Any],
) -> InternalGateAuthorityReceipt:
    """Atomically publish one already-built, validated authority."""

    validate_internal_gate_authority(payload)
    destination = _safe_path(output_path, label="authority output")
    if destination.exists():
        raise FileExistsError(
            f"refusing to overwrite internal-Gate authority: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            _canonical(payload),
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
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
        raise InternalGateAuthorityError(
            "published internal-Gate authority is not mode 0600"
        )
    return InternalGateAuthorityReceipt(
        path=destination,
        file_sha256=_file_sha256(destination),
        authority_sha256=str(payload["authority_sha256"]),
        source_sha=str(payload["source_sha"]),
        trial_id=str(payload["trial_id"]),
        cycle_index=int(payload["cycle_index"]),
        serial_mpi_identity_pass=bool(
            payload["gates"]["serial_mpi_identity_pass"]
        ),
        classification=str(payload["classification"]),
    )


def write_internal_gate_authority(
    output_path: Path,
    **inputs: BoundJSONInput | None,
) -> InternalGateAuthorityReceipt:
    """Atomically publish a final probe-qualified authority."""

    payload = build_internal_gate_authority(**inputs)  # type: ignore[arg-type]
    return _publish_internal_gate_authority(output_path, payload)


def write_deferred_internal_gate_authority(
    output_path: Path,
    **inputs: BoundJSONInput,
) -> InternalGateAuthorityReceipt:
    """Atomically publish a conservative intermediate-cycle authority."""

    payload = build_deferred_internal_gate_authority(**inputs)
    return _publish_internal_gate_authority(output_path, payload)


def _bound(path: Path, sha256: str) -> BoundJSONInput:
    return BoundJSONInput(path=path, sha256=sha256)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--deferred",
        action="store_true",
        help=(
            "replay only the current MPI8 authority and conservatively defer "
            "all three budget probes; this output cannot freeze a candidate"
        ),
    )
    parser.add_argument("--candidate-record", type=Path, required=True)
    parser.add_argument("--candidate-record-sha256", required=True)
    parser.add_argument("--candidate-output", type=Path, required=True)
    parser.add_argument("--candidate-output-sha256", required=True)
    parser.add_argument("--current-plan", type=Path, required=True)
    parser.add_argument("--current-plan-sha256", required=True)
    parser.add_argument("--current-snapshot", type=Path, required=True)
    parser.add_argument("--current-snapshot-sha256", required=True)
    for name in ("algebraic", "dtn", "postprocess"):
        parser.add_argument(
            f"--{name}-probe-record",
            type=Path,
        )
        parser.add_argument(
            f"--{name}-probe-record-sha256",
        )
    parser.add_argument("--serial-mpi1-record", type=Path)
    parser.add_argument("--serial-mpi1-record-sha256")
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if (args.serial_mpi1_record is None) is not (
        args.serial_mpi1_record_sha256 is None
    ):
        parser.error(
            "serial MPI1 record path and SHA-256 must be supplied together"
        )
    probe_pairs = {
        name: (
            getattr(args, f"{name}_probe_record"),
            getattr(args, f"{name}_probe_record_sha256"),
        )
        for name in ("algebraic", "dtn", "postprocess")
    }
    if any((path is None) is not (sha is None) for path, sha in probe_pairs.values()):
        parser.error("each probe record path and SHA-256 must be supplied together")
    if args.deferred:
        if any(path is not None for path, _sha in probe_pairs.values()):
            parser.error("deferred authority must not accept probe records")
        if args.serial_mpi1_record is not None:
            parser.error("deferred authority must not accept an MPI1 probe")
    elif any(path is None for path, _sha in probe_pairs.values()):
        parser.error("final authority requires all three probe records")
    common_inputs = {
        "candidate_record": _bound(
            args.candidate_record,
            args.candidate_record_sha256,
        ),
        "candidate_output": _bound(
            args.candidate_output,
            args.candidate_output_sha256,
        ),
        "current_plan": _bound(
            args.current_plan,
            args.current_plan_sha256,
        ),
        "current_snapshot": _bound(
            args.current_snapshot,
            args.current_snapshot_sha256,
        ),
    }
    try:
        if args.deferred:
            receipt = write_deferred_internal_gate_authority(
                args.output,
                **common_inputs,
            )
        else:
            receipt = write_internal_gate_authority(
                args.output,
                **common_inputs,
                algebraic_probe_record=_bound(
                    args.algebraic_probe_record,
                    args.algebraic_probe_record_sha256,
                ),
                dtn_probe_record=_bound(
                    args.dtn_probe_record,
                    args.dtn_probe_record_sha256,
                ),
                postprocess_probe_record=_bound(
                    args.postprocess_probe_record,
                    args.postprocess_probe_record_sha256,
                ),
                serial_mpi1_record=(
                    None
                    if args.serial_mpi1_record is None
                    else _bound(
                        args.serial_mpi1_record,
                        args.serial_mpi1_record_sha256,
                    )
                ),
            )
    except (
        CandidateOutputError,
        FileExistsError,
        InternalGateAuthorityError,
        OSError,
        TypeError,
        ValueError,
    ) as exc:
        print(
            json.dumps(
                {
                    "schema_version": RECEIPT_SCHEMA,
                    "status": "failed",
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        return 2
    print(
        json.dumps(
            {
                "schema_version": RECEIPT_SCHEMA,
                "status": "completed",
                "output": str(receipt.path),
                "file_sha256": receipt.file_sha256,
                "authority_sha256": receipt.authority_sha256,
                "source_sha": receipt.source_sha,
                "trial_id": receipt.trial_id,
                "cycle_index": receipt.cycle_index,
                "classification": receipt.classification,
                "serial_mpi_identity_pass": (
                    receipt.serial_mpi_identity_pass
                ),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AUTHORITY_NAMESPACE",
    "AUTHORITY_SCHEMA",
    "BUDGET_FRACTION_LIMIT",
    "BoundJSONInput",
    "InternalGateAuthorityError",
    "InternalGateAuthorityReceipt",
    "build_deferred_internal_gate_authority",
    "build_internal_gate_authority",
    "main",
    "validate_internal_gate_authority",
    "write_deferred_internal_gate_authority",
    "write_internal_gate_authority",
]
