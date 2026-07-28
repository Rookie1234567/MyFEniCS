#!/usr/bin/env python3
"""Build one immutable Task035e cellwise DWR marking authority.

The live shadow observer already publishes the actual owner-local
``Re(conj(z_i) * r_i)`` partition.  This adapter does not relocalize, smooth,
or distribute that estimator.  It preserves every cellwise DWR row byte-for-
byte at the JSON value level and binds the partition to:

* independently rebuilt current and shadow candidate outputs;
* the embedded global actual-DWR report; and
* a transparent structural-cost proxy calibrated by the two measured solver
  endpoints.

Only attributable structural costs are apportioned.  Process allocator, MPI,
JIT, mesh, and other common job-peak bytes remain visible as measured endpoint
telemetry but are never assigned to leaves.  The per-leaf peak proxy is
derived solely from apportioned matrix/factor CSR and live-vector bytes.
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

from benchmarks.task035e_blind_cycle import (
    goal_vector_from_candidate_output,
)
from benchmarks.task035e_candidate_output import (
    AdaptedCandidateOutput,
    CandidateWatchdogInput,
    adapt_candidate_output,
)
from benchmarks.task035e_live_shadow_bridge import (
    _validate_actual_dwr_report,
)
from src.adaptivity.blind_controller.contracts import (
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
)
from src.adaptivity.task035e_actual_dwr import (
    CELLWISE_DWR_PARTITION_SCHEMA,
)
from src.adaptivity.task035e_hp_transition import (
    _face_neighbor_pairs,
    canonical_hp_cell_target_id,
    hp_transition_action_payload,
)
from src.adaptivity.task035e_plan_transition import (
    rebuild_hp_transition_state_from_solver_plan,
)
from src.adaptivity.task035e_shadow_observer import (
    SHADOW_EVALUATION_SCHEMA,
)
from src.common.config_3d import target_stage4_config


CELLWISE_DWR_AUTHORITY_SCHEMA = (
    "task035e.cellwise-59-goal-dwr-authority.v2"
)
STRUCTURAL_COST_MODEL_SCHEMA = (
    "task035e.action-specific-structural-cost-model.v1"
)
STRUCTURAL_COST_ROW_SCHEMA = (
    "task035e.action-specific-structural-cost-row.v1"
)
CELLWISE_AUTHORITY_FAILURE_SCHEMA = (
    "task035e.cellwise-authority-controlled-negative.v1"
)
CELLWISE_AUTHORITY_RECEIPT_SCHEMA = (
    "task035e.cellwise-authority-write-receipt.v1"
)

_SOURCE_SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
_SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
_ACTION_KINDS = frozenset({"p-up", "h-refine"})
_SHADOW_ROLE = {"p-up": "p-shadow", "h-refine": "h-shadow"}
_FORMAL_H = frozenset({15.0, 20.0})
_FORBIDDEN_PATH_PARTS = frozenset(
    {
        "reference_certifier",
        "hidden_auditor",
        "sealed_reference",
        "sealed-reference",
    }
)
_COST_FIELDS = (
    "estimated_added_active_dofs",
    "estimated_added_rows",
    "estimated_added_matrix_nnz",
    "estimated_added_factor_nnz",
    "estimated_added_solver_peak_bytes",
)
_INVENTORY_TO_COST = {
    "active_fe_dofs": "estimated_added_active_dofs",
    "matrix_rows": "estimated_added_rows",
    "matrix_nnz": "estimated_added_matrix_nnz",
    "factor_nnz": "estimated_added_factor_nnz",
}
_PETSC_SCALAR_BYTES = 16
_PETSC_INT_BYTES = 4
_SIMULTANEOUS_ATTRIBUTABLE_VECTOR_COUNT = 4


class CellwiseAuthorityError(ValueError):
    """Raised when a cellwise authority cannot be built or replayed."""


@dataclass(frozen=True, slots=True)
class CellwiseAuthorityWriteReceipt:
    """Identity of one immutable positive or controlled-negative artifact."""

    path: Path
    file_sha256: str
    payload_sha256: str
    status: str
    classification: str
    byte_count: int


def _reject_nonfinite(value: str) -> None:
    raise CellwiseAuthorityError(
        f"non-finite JSON constant is forbidden: {value}"
    )


def _reject_duplicate_object(
    pairs: Sequence[tuple[str, Any]],
) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise CellwiseAuthorityError(
                f"duplicate JSON object key is forbidden: {key}"
            )
        result[key] = value
    return result


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _json_sha256(value: Any, *, namespace: str | None = None) -> str:
    digest = hashlib.sha256()
    if namespace is not None:
        digest.update(namespace.encode("ascii"))
        digest.update(b"\0")
    digest.update(_canonical_bytes(value))
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _mapping(value: Any, *, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CellwiseAuthorityError(f"{label} must be a JSON object")
    return value


def _sequence(value: Any, *, label: str) -> Sequence[Any]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise CellwiseAuthorityError(f"{label} must be a JSON array")
    return value


def _sha256(value: Any, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256_RE.fullmatch(value) is None:
        raise CellwiseAuthorityError(f"{label} must be one lowercase SHA-256")
    return value


def _source_sha(value: Any) -> str:
    if not isinstance(value, str) or _SOURCE_SHA_RE.fullmatch(value) is None:
        raise CellwiseAuthorityError(
            "source SHA must be one lowercase 40-character Git SHA"
        )
    return value


def _finite(value: Any, *, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CellwiseAuthorityError(f"{label} must be a real number")
    result = float(value)
    if not math.isfinite(result):
        raise CellwiseAuthorityError(f"{label} must be finite")
    return result


def _nonnegative_integer(value: Any, *, label: str) -> int:
    if type(value) is not int or value < 0:
        raise CellwiseAuthorityError(f"{label} must be a nonnegative integer")
    return value


def _safe_path(path: Path, *, label: str) -> Path:
    resolved = path.expanduser().resolve()
    if {part.lower() for part in resolved.parts} & _FORBIDDEN_PATH_PARTS:
        raise CellwiseAuthorityError(f"{label} crosses a forbidden layer")
    return resolved


def _private_regular_file(path: Path, *, label: str) -> Path:
    if path.is_symlink():
        raise CellwiseAuthorityError(f"{label} must not be a symlink")
    resolved = _safe_path(path, label=label)
    try:
        metadata = resolved.stat()
    except OSError as exc:
        raise CellwiseAuthorityError(f"{label} is not readable") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_IMODE(metadata.st_mode) != 0o600
    ):
        raise CellwiseAuthorityError(
            f"{label} must be a regular mode-0600 file"
        )
    return resolved


def _strict_json(path: Path, *, label: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8"),
            parse_constant=_reject_nonfinite,
            object_pairs_hook=_reject_duplicate_object,
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CellwiseAuthorityError(
            f"cannot read strict {label}: {path}"
        ) from exc
    return _mapping(payload, label=label)


def _load_bound_private_json(
    path: Path,
    expected_sha256: str,
    *,
    label: str,
) -> tuple[Mapping[str, Any], Path, str]:
    expected = _sha256(expected_sha256, label=f"{label} file SHA-256")
    resolved = _private_regular_file(path, label=label)
    observed = _file_sha256(resolved)
    if observed != expected:
        raise CellwiseAuthorityError(f"{label} file SHA-256 mismatch")
    return _strict_json(resolved, label=label), resolved, observed


def _current_state(
    plan: Mapping[str, Any],
    *,
    source_sha: str,
) -> Any:
    base = _mapping(plan.get("base_config"), label="current plan base_config")
    raw_h = base.get("mesh_target_size")
    h_nm = _finite(raw_h, label="current plan mesh_target_size")
    if not any(abs(h_nm - value) <= 1.0e-12 for value in _FORMAL_H):
        raise CellwiseAuthorityError(
            "current plan is not a formal Task035e Path A/B base family"
        )
    try:
        state = rebuild_hp_transition_state_from_solver_plan(
            target_stage4_config(degree=6, h_nm=h_nm),
            current_plan=plan,
            comm_size=8,
        )
    except (RuntimeError, TypeError, ValueError) as exc:
        raise CellwiseAuthorityError(
            f"current solver plan cannot be replayed: {exc}"
        ) from exc
    if state.source_sha != source_sha:
        raise CellwiseAuthorityError(
            "current plan source differs from the verified clean SHA"
        )
    return state


def _candidate(
    record_path: Path,
    record_sha256: str,
    output_path: Path,
    output_sha256: str,
    *,
    role: str,
    label: str,
) -> tuple[AdaptedCandidateOutput, str, str]:
    _record, resolved_record, record_file_sha = _load_bound_private_json(
        record_path,
        record_sha256,
        label=f"{label} watchdog record",
    )
    raw_output, _resolved_output, output_file_sha = (
        _load_bound_private_json(
            output_path,
            output_sha256,
            label=f"{label} candidate output",
        )
    )
    adapted = adapt_candidate_output(
        CandidateWatchdogInput(resolved_record, record_file_sha),
        output_role=role,
    )
    if (
        raw_output != adapted.payload
        or _json_sha256(raw_output) != adapted.output_sha256
    ):
        raise CellwiseAuthorityError(
            f"{label} candidate output differs from its watchdog replay"
        )
    return adapted, record_file_sha, output_file_sha


def _validate_live_evidence(
    raw: Mapping[str, Any],
    *,
    file_sha256: str,
    current: AdaptedCandidateOutput,
    shadow: AdaptedCandidateOutput,
    action_kind: str,
    live_path: Path,
) -> tuple[
    Mapping[str, Any],
    Mapping[str, Any],
    dict[str, float],
    str,
]:
    reference = shadow.live_role_evidence
    if not isinstance(reference, Mapping):
        raise CellwiseAuthorityError(
            "shadow watchdog has no live-role evidence authority"
        )
    unsigned = dict(raw)
    payload_sha = _sha256(
        unsigned.pop("payload_sha256", None),
        label="live shadow payload SHA-256",
    )
    expected_payload_sha = _json_sha256(
        unsigned,
        namespace="task035e.live-shadow-evaluation-payload.v1",
    )
    shadow_role = _SHADOW_ROLE[action_kind]
    if (
        file_sha256 != reference.get("sha256")
        or live_path.resolve()
        != Path(str(reference.get("path"))).expanduser().resolve()
        or payload_sha != expected_payload_sha
        or payload_sha != reference.get("payload_sha256")
        or raw.get("schema_version") != SHADOW_EVALUATION_SCHEMA
        or raw.get("status") != "live_shadow_59_goal_actual_dwr_pass"
        or raw.get("pass") is not True
        or raw.get("source_sha") != current.source_sha
        or raw.get("source_sha") != shadow.source_sha
        or raw.get("trial_id") != current.trial_id
        or raw.get("trial_id") != shadow.trial_id
        or raw.get("cycle_index") != current.cycle_index
        or raw.get("cycle_index") != shadow.cycle_index
        or raw.get("shadow_kind") != shadow_role
        or raw.get("mpi_size") != 8
        or raw.get("formal_mpi8_qualified") is not True
        or raw.get("diagnostic_serial_fixture") is not False
        or raw.get("shadow_plan_file_sha256")
        != shadow.plan_file_sha256
        or raw.get("formal_goal_count") != len(FORMAL_GOAL_IDS)
        or raw.get("formal_goal_inventory_sha256")
        != FORMAL_GOAL_INVENTORY_SHA256
        or raw.get("hidden_reference_consumed") is not False
        or raw.get("endpoint_delta_used_as_dwr") is not False
        or raw.get("ordinary_default_changed") is not False
    ):
        raise CellwiseAuthorityError(
            "live shadow identity, role, MPI8, or self-hash differs"
        )
    report, signed, _evaluator = _validate_actual_dwr_report(
        raw.get("actual_dwr"),
        shadow=shadow,
        shadow_kind=shadow_role,
    )
    outer_signed = _mapping(
        raw.get("signed_dwr_delta"),
        label="live shadow signed DWR",
    )
    if set(outer_signed) != set(FORMAL_GOAL_IDS) or any(
        _finite(outer_signed[goal_id], label=f"signed eta {goal_id}")
        != signed[goal_id]
        for goal_id in FORMAL_GOAL_IDS
    ):
        raise CellwiseAuthorityError(
            "live shadow signed DWR differs from global actual DWR"
        )
    return (
        report,
        _mapping(
            raw.get("cellwise_dwr_partition"),
            label="live cellwise DWR partition",
        ),
        signed,
        payload_sha,
    )


def _validate_partition(
    raw: Mapping[str, Any],
    *,
    state: Any,
    current: AdaptedCandidateOutput,
    shadow: AdaptedCandidateOutput,
    global_signed: Mapping[str, float],
) -> dict[str, Mapping[str, Any]]:
    unsigned = dict(raw)
    partition_sha = _sha256(
        unsigned.pop("partition_sha256", None),
        label="cellwise DWR partition SHA-256",
    )
    if partition_sha != _json_sha256(
        unsigned,
        namespace=CELLWISE_DWR_PARTITION_SCHEMA,
    ):
        raise CellwiseAuthorityError(
            "cellwise DWR partition SHA-256 mismatch"
        )
    current_identity = _mapping(
        raw.get("current_plan_identity"),
        label="cellwise current plan identity",
    )
    shadow_identity = _mapping(
        raw.get("shadow_plan_identity"),
        label="cellwise shadow plan identity",
    )
    designation = _mapping(
        raw.get("row_designation_identity"),
        label="cellwise row designation",
    )
    designation_unsigned = dict(designation)
    designation_sha = _sha256(
        designation_unsigned.pop("designation_sha256", None),
        label="row designation SHA-256",
    )
    affine_partition = (
        raw.get("active_interior_affine_complement_present") is True
    )
    if (
        designation_sha
        != _json_sha256(
            designation_unsigned,
            namespace="task035e.actual-dwr-row-designation.v1",
        )
        or raw.get("schema_version") != CELLWISE_DWR_PARTITION_SCHEMA
        or raw.get("status") != "cellwise_signed_dwr_partition_pass"
        or raw.get("pass") is not True
        or raw.get("method")
        not in {
            "element_residual_adjoint_pairing",
            (
                "reduced_residual_adjoint_plus_active_interior_"
                "affine_complement"
            ),
        }
        or raw.get("complete_current_leaf_partition") is not True
        or raw.get("global_signed_closure_verified") is not True
        or raw.get("actual_cellwise_residual_adjoint_pairing") is not True
        or (
            affine_partition
            and (
                type(raw.get("active_full_gradient_goal_count")) is not int
                or raw["active_full_gradient_goal_count"] <= 0
            )
        )
        or raw.get("global_eta_evenly_distributed") is not False
        or raw.get("endpoint_delta_consumed") is not False
        or raw.get("formal_goal_count") != len(FORMAL_GOAL_IDS)
        or raw.get("formal_goal_inventory_sha256")
        != FORMAL_GOAL_INVENTORY_SHA256
        or tuple(raw.get("ordered_goal_ids", ())) != FORMAL_GOAL_IDS
        or raw.get("python_full_vector_gather_used") is not False
        or current_identity.get("file_sha256")
        != current.plan_file_sha256
        or current_identity.get("forest_leaf_catalog_sha256")
        != current.forest_leaf_catalog_sha256
        or current_identity.get("cell_degree_plan_sha256")
        != current.cell_degree_plan_sha256
        or shadow_identity.get("file_sha256")
        != shadow.plan_file_sha256
        or shadow_identity.get("forest_leaf_catalog_sha256")
        != shadow.forest_leaf_catalog_sha256
        or shadow_identity.get("cell_degree_plan_sha256")
        != shadow.cell_degree_plan_sha256
        or designation.get("total_reduced_rows")
        != shadow.structural_inventory["matrix_rows"]
    ):
        raise CellwiseAuthorityError(
            "cellwise partition role, plan, or row designation differs"
        )
    expected = {
        canonical_hp_cell_target_id(cell.key): cell
        for cell in state.forest.leaves
    }
    raw_rows = _sequence(raw.get("rows"), label="cellwise DWR rows")
    if len(raw_rows) != len(expected):
        raise CellwiseAuthorityError(
            "cellwise DWR rows do not cover every current leaf"
        )
    rows: dict[str, Mapping[str, Any]] = {}
    signed_sums = {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    absolute_sums = {goal_id: 0.0 for goal_id in FORMAL_GOAL_IDS}
    residual_hashes: list[str] = []
    adjoint_hashes: list[str] = []
    assigned_rows = 0
    assigned_trace = 0
    assigned_auxiliary = 0
    assigned_active_interior = 0
    for index, raw_row in enumerate(raw_rows):
        row = _mapping(raw_row, label=f"cellwise DWR row {index}")
        unsigned_row = dict(row)
        row_sha = _sha256(
            unsigned_row.pop("row_sha256", None),
            label=f"cellwise DWR row {index} SHA-256",
        )
        if row_sha != _json_sha256(
            unsigned_row,
            namespace="task035e.cellwise-signed-dwr-row.v1",
        ):
            raise CellwiseAuthorityError(
                f"cellwise DWR row {index} SHA-256 mismatch"
            )
        target_id = row.get("target_id")
        if not isinstance(target_id, str) or target_id not in expected:
            raise CellwiseAuthorityError(
                f"cellwise DWR row {index} targets a non-current leaf"
            )
        if target_id in rows:
            raise CellwiseAuthorityError(
                f"cellwise DWR row {index} duplicates {target_id}"
            )
        cell = expected[target_id]
        expected_key = [
            int(cell.key.root),
            int(cell.key.level),
            int(cell.key.i),
            int(cell.key.j),
            int(cell.key.k),
        ]
        expected_box = [float(value) for value in cell.box]
        if (
            row.get("current_leaf_key") != expected_key
            or row.get("current_leaf_box") != expected_box
            or row.get("current_leaf_degree")
            != int(state.cell_degree_by_key[cell.key])
        ):
            raise CellwiseAuthorityError(
                f"cellwise DWR row {index} leaf identity differs"
            )
        residual_hashes.append(
            _sha256(
                row.get("local_residual_partition_sha256"),
                label=f"cellwise row {index} residual partition",
            )
        )
        adjoint_hashes.append(
            _sha256(
                row.get("local_adjoint_partition_sha256"),
                label=f"cellwise row {index} adjoint partition",
            )
        )
        if affine_partition:
            _sha256(
                row.get("local_affine_complement_partition_sha256"),
                label=f"cellwise row {index} affine partition",
            )
        total = _nonnegative_integer(
            row.get("assigned_reduced_row_count"),
            label=f"cellwise row {index} assigned reduced rows",
        )
        trace = _nonnegative_integer(
            row.get("assigned_trace_row_count"),
            label=f"cellwise row {index} assigned trace rows",
        )
        auxiliary = _nonnegative_integer(
            row.get("assigned_auxiliary_row_count"),
            label=f"cellwise row {index} assigned auxiliary rows",
        )
        if trace + auxiliary != total:
            raise CellwiseAuthorityError(
                f"cellwise DWR row {index} row counts do not close"
            )
        assigned_rows += total
        assigned_trace += trace
        assigned_auxiliary += auxiliary
        contribution = _mapping(
            row.get("signed_dwr_contribution"),
            label=f"cellwise row {index} signed DWR",
        )
        if set(contribution) != set(FORMAL_GOAL_IDS):
            raise CellwiseAuthorityError(
                f"cellwise DWR row {index} lacks the 59 goals"
            )
        if affine_partition:
            assigned_active_interior += _nonnegative_integer(
                row.get("assigned_active_interior_row_count"),
                label=(
                    f"cellwise row {index} assigned active-interior rows"
                ),
            )
            reduced = _mapping(
                row.get("reduced_trace_auxiliary_contribution"),
                label=f"cellwise row {index} reduced DWR",
            )
            affine = _mapping(
                row.get(
                    "active_interior_affine_complement_contribution"
                ),
                label=f"cellwise row {index} affine DWR",
            )
            if (
                set(reduced) != set(FORMAL_GOAL_IDS)
                or set(affine) != set(FORMAL_GOAL_IDS)
            ):
                raise CellwiseAuthorityError(
                    f"cellwise DWR row {index} affine split is incomplete"
                )
        for goal_id in FORMAL_GOAL_IDS:
            value = _finite(
                contribution[goal_id],
                label=f"cellwise row {index} contribution {goal_id}",
            )
            if affine_partition:
                component_sum = _finite(
                    reduced[goal_id],
                    label=(
                        f"cellwise row {index} reduced component {goal_id}"
                    ),
                ) + _finite(
                    affine[goal_id],
                    label=(
                        f"cellwise row {index} affine component {goal_id}"
                    ),
                )
                if abs(value - component_sum) > (
                    1.0e-12
                    * max(abs(value), abs(component_sum), 1.0)
                ):
                    raise CellwiseAuthorityError(
                        "cellwise reduced plus affine contribution does not "
                        f"close for {goal_id}"
                    )
            signed_sums[goal_id] += value
            absolute_sums[goal_id] += abs(value)
        rows[target_id] = row
    if set(rows) != set(expected):
        raise CellwiseAuthorityError(
            "cellwise DWR target catalog differs from current plan"
        )
    if (
        assigned_rows != designation.get("total_reduced_rows")
        or assigned_trace != designation.get("independent_trace_rows")
        or assigned_auxiliary != designation.get("appended_auxiliary_rows")
        or (
            affine_partition
            and assigned_active_interior
            != designation.get("active_interior_rows")
        )
        or raw.get("residual_partition_catalog_sha256")
        != _json_sha256(
            residual_hashes,
            namespace=(
                "task035e.actual-dwr.residual-partition-catalog.v1"
            ),
        )
        or raw.get("adjoint_partition_catalog_sha256")
        != _json_sha256(
            adjoint_hashes,
            namespace=(
                "task035e.actual-dwr.adjoint-partition-catalog.v1"
            ),
        )
    ):
        raise CellwiseAuthorityError(
            "cellwise row counts or partition catalogs do not close"
        )
    for goal_id in FORMAL_GOAL_IDS:
        scale = max(
            abs(global_signed[goal_id]),
            absolute_sums[goal_id],
            1.0,
        )
        if abs(signed_sums[goal_id] - global_signed[goal_id]) > max(
            1.0e-13,
            1.0e-10 * scale,
        ):
            raise CellwiseAuthorityError(
                f"cellwise DWR does not close global eta for {goal_id}"
            )
    return rows


def _n1curl_hex_dimension(degree: int) -> int:
    if degree not in {4, 5, 6}:
        raise CellwiseAuthorityError("cell degree is outside p4/p5/p6")
    return 3 * degree * (degree + 1) ** 2


def _dyadic_key_from_row(row: Mapping[str, Any], state: Any) -> Any:
    wanted = (
        row.get("root"),
        row.get("level"),
        row.get("i"),
        row.get("j"),
        row.get("k"),
    )
    for key in state.cell_degree_by_key:
        observed = (key.root, key.level, key.i, key.j, key.k)
        if observed == wanted:
            return key
    raise CellwiseAuthorityError("transition topology names a non-current leaf")


def _candidate_topology_rows(
    *,
    state: Any,
    dwr_rows: Mapping[str, Mapping[str, Any]],
    action_kind: str,
) -> list[dict[str, Any]]:
    neighbor_count = {key: 0 for key in state.cell_degree_by_key}
    for left, right in _face_neighbor_pairs(state.forest):
        neighbor_count[left] += 1
        neighbor_count[right] += 1
    rows: list[dict[str, Any]] = []
    for index, cell in enumerate(state.forest.leaves):
        key = cell.key
        target_id = canonical_hp_cell_target_id(key)
        degree = int(state.cell_degree_by_key[key])
        try:
            if action_kind == "p-up":
                action = hp_transition_action_payload(
                    state,
                    action_id=f"cost.p-up.{index}",
                    kind="p-up",
                    degree_deltas={key: 1},
                )
                raw_active_delta = (
                    _n1curl_hex_dimension(degree + 1)
                    - _n1curl_hex_dimension(degree)
                )
            else:
                action = hp_transition_action_payload(
                    state,
                    action_id=f"cost.h-refine.{index}",
                    kind="h-refine",
                    degree_deltas={},
                    requested_split_keys=(key,),
                    maximum_level=2,
                )
                removed = [
                    _dyadic_key_from_row(item, state)
                    for item in action["expected_removed_leaf_keys"]
                ]
                raw_active_delta = sum(
                    7
                    * _n1curl_hex_dimension(
                        int(state.cell_degree_by_key[parent])
                    )
                    for parent in removed
                )
        except ValueError:
            rows.append(
                {
                    "target_id": target_id,
                    "eligible": False,
                    "ineligibility": (
                        "qualified p/level/2:1/periodic transition rejected"
                    ),
                    "topology": None,
                    "weights": {
                        "active": 0,
                        "rows": 0,
                        "matrix_nnz": 0,
                        "factor_nnz": 0,
                    },
                }
            )
            continue
        dwr_row = dwr_rows[target_id]
        assigned = _nonnegative_integer(
            dwr_row.get("assigned_reduced_row_count"),
            label=f"{target_id} assigned reduced rows",
        )
        if assigned <= 0 or raw_active_delta <= 0:
            raise CellwiseAuthorityError(
                f"{target_id} lacks attributable topology/row support"
            )
        graph_width = 1 + neighbor_count[key]
        closure_parent_count = max(
            len(action["expected_removed_leaf_keys"]),
            1,
        )
        row_weight = (
            raw_active_delta
            + assigned * graph_width * closure_parent_count
        )
        matrix_weight = row_weight * (assigned + graph_width)
        factor_weight = row_weight * (assigned + graph_width) ** 2
        rows.append(
            {
                "target_id": target_id,
                "eligible": True,
                "ineligibility": None,
                "topology": {
                    "action_sha256": action["action_sha256"],
                    "action_identity_sha256": action[
                        "action_identity_sha256"
                    ],
                    "current_degree": degree,
                    "n1curl_raw_broken_active_delta": raw_active_delta,
                    "expected_removed_leaf_count": len(
                        action["expected_removed_leaf_keys"]
                    ),
                    "expected_added_leaf_count": len(
                        action["expected_added_leaf_keys"]
                    ),
                    "expected_net_added_leaf_count": action[
                        "expected_net_added_leaf_count"
                    ],
                    "face_or_periodic_neighbor_count": neighbor_count[key],
                    "assigned_shadow_reduced_row_count": assigned,
                },
                "weights": {
                    "active": raw_active_delta,
                    "rows": row_weight,
                    "matrix_nnz": matrix_weight,
                    "factor_nnz": factor_weight,
                },
            }
        )
    if not any(row["eligible"] for row in rows):
        raise CellwiseAuthorityError(
            "no current leaf admits the requested qualified local action"
        )
    return rows


def _apportion(
    total: int,
    weighted_rows: Sequence[tuple[str, int]],
) -> dict[str, int]:
    if type(total) is not int or total <= 0:
        raise CellwiseAuthorityError(
            "measured structural delta must be a positive integer"
        )
    if not weighted_rows or any(weight <= 0 for _, weight in weighted_rows):
        raise CellwiseAuthorityError(
            "integer apportionment requires positive structural weights"
        )
    denominator = sum(weight for _, weight in weighted_rows)
    floors = {
        target_id: total * weight // denominator
        for target_id, weight in weighted_rows
    }
    remainder = total - sum(floors.values())
    order = sorted(
        weighted_rows,
        key=lambda item: (
            -(total * item[1] % denominator),
            item[0],
        ),
    )
    for target_id, _weight in order[:remainder]:
        floors[target_id] += 1
    if sum(floors.values()) != total:
        raise AssertionError("Hamilton integer apportionment did not close")
    return floors


def _structural_cost_model(
    *,
    current: AdaptedCandidateOutput,
    shadow: AdaptedCandidateOutput,
    state: Any,
    dwr_rows: Mapping[str, Mapping[str, Any]],
    action_kind: str,
) -> Mapping[str, Any]:
    current_inventory = {
        name: _nonnegative_integer(
            current.structural_inventory.get(name),
            label=f"current structural inventory {name}",
        )
        for name in (
            "raw_active_fe_dofs",
            "active_fe_dofs",
            "matrix_rows",
            "matrix_nnz",
            "factor_nnz",
            "solver_peak_bytes",
        )
    }
    shadow_inventory = {
        name: _nonnegative_integer(
            shadow.structural_inventory.get(name),
            label=f"shadow structural inventory {name}",
        )
        for name in current_inventory
    }
    delta = {
        name: shadow_inventory[name] - current_inventory[name]
        for name in current_inventory
    }
    if any(
        delta[name] <= 0
        for name in ("active_fe_dofs", "matrix_rows", "matrix_nnz", "factor_nnz")
    ):
        raise CellwiseAuthorityError(
            "current/shadow endpoints lack a positive active/row/NNZ/factor "
            "structural delta"
        )
    topology = _candidate_topology_rows(
        state=state,
        dwr_rows=dwr_rows,
        action_kind=action_kind,
    )
    eligible = [row for row in topology if row["eligible"]]
    allocations: dict[str, dict[str, int]] = {
        row["target_id"]: {} for row in topology
    }
    for inventory_name, cost_name in _INVENTORY_TO_COST.items():
        weight_name = {
            "active_fe_dofs": "active",
            "matrix_rows": "rows",
            "matrix_nnz": "matrix_nnz",
            "factor_nnz": "factor_nnz",
        }[inventory_name]
        apportioned = _apportion(
            delta[inventory_name],
            [
                (row["target_id"], row["weights"][weight_name])
                for row in eligible
            ],
        )
        for row in topology:
            allocations[row["target_id"]][cost_name] = apportioned.get(
                row["target_id"],
                0,
            )
    matrix_bytes = (
        delta["matrix_nnz"] * (_PETSC_SCALAR_BYTES + _PETSC_INT_BYTES)
        + (delta["matrix_rows"] + 1) * _PETSC_INT_BYTES
    )
    factor_bytes = (
        delta["factor_nnz"] * (_PETSC_SCALAR_BYTES + _PETSC_INT_BYTES)
        + (delta["matrix_rows"] + 1) * _PETSC_INT_BYTES
    )
    vector_bytes = (
        delta["matrix_rows"]
        * _SIMULTANEOUS_ATTRIBUTABLE_VECTOR_COUNT
        * _PETSC_SCALAR_BYTES
    )
    peak_proxy = matrix_bytes + factor_bytes + vector_bytes
    for row in topology:
        costs = allocations[row["target_id"]]
        costs["estimated_added_solver_peak_bytes"] = (
            costs["estimated_added_matrix_nnz"]
            * (_PETSC_SCALAR_BYTES + _PETSC_INT_BYTES)
            + costs["estimated_added_factor_nnz"]
            * (_PETSC_SCALAR_BYTES + _PETSC_INT_BYTES)
            + costs["estimated_added_rows"]
            * (
                2 * _PETSC_INT_BYTES
                + _SIMULTANEOUS_ATTRIBUTABLE_VECTOR_COUNT
                * _PETSC_SCALAR_BYTES
            )
        )
    # Two global CSR row-pointer terminal integers are indivisible metadata,
    # not attributable to any leaf.  Keep them outside the leaf allocation.
    unallocated_terminal_bytes = 2 * _PETSC_INT_BYTES
    attributed_peak = sum(
        costs["estimated_added_solver_peak_bytes"]
        for costs in allocations.values()
    )
    if attributed_peak + unallocated_terminal_bytes != peak_proxy:
        raise AssertionError("attributable peak proxy did not close")
    model_rows = []
    for topology_row in topology:
        target_id = topology_row["target_id"]
        unsigned_row = {
            "schema_version": STRUCTURAL_COST_ROW_SCHEMA,
            **topology_row,
            "dwr_row_sha256": dwr_rows[target_id]["row_sha256"],
            "apportioned_cost": allocations[target_id],
        }
        model_rows.append(
            {
                **unsigned_row,
                "row_sha256": _json_sha256(
                    unsigned_row,
                    namespace=STRUCTURAL_COST_ROW_SCHEMA,
                ),
            }
        )
    global_cost = {
        "estimated_added_active_dofs": delta["active_fe_dofs"],
        "estimated_added_rows": delta["matrix_rows"],
        "estimated_added_matrix_nnz": delta["matrix_nnz"],
        "estimated_added_factor_nnz": delta["factor_nnz"],
        "estimated_added_solver_peak_bytes": peak_proxy,
    }
    closure = {
        name: {
            "expected": global_cost[name],
            "apportioned": sum(
                row["apportioned_cost"][name] for row in model_rows
            ),
            "unallocated": (
                unallocated_terminal_bytes
                if name == "estimated_added_solver_peak_bytes"
                else 0
            ),
            "closed": (
                sum(row["apportioned_cost"][name] for row in model_rows)
                + (
                    unallocated_terminal_bytes
                    if name == "estimated_added_solver_peak_bytes"
                    else 0
                )
                == global_cost[name]
            ),
        }
        for name in _COST_FIELDS
    }
    unsigned = {
        "schema_version": STRUCTURAL_COST_MODEL_SCHEMA,
        "status": "action_specific_structural_cost_model_pass",
        "pass": True,
        "action_kind": action_kind,
        "measurement_classification": {
            "endpoint_inventories": "measured",
            "global_active_rows_matrix_factor_delta": "measured_difference",
            "per_leaf_active_weight": (
                "exact_action_topology_n1curl_raw_broken_dimension"
            ),
            "per_leaf_row_weight": (
                "predicted_from_exact_action_topology_and_actual_shadow_"
                "reduced_row_attribution"
            ),
            "per_leaf_matrix_nnz_weight": (
                "predicted_from_row_support_and_exact_face_periodic_graph"
            ),
            "per_leaf_factor_nnz_weight": (
                "predicted_elimination_complexity_row_degree_squared"
            ),
            "per_leaf_peak": (
                "derived_only_from_apportioned_matrix_factor_vector_bytes"
            ),
        },
        "current_inventory": current_inventory,
        "shadow_inventory": shadow_inventory,
        "measured_global_delta": delta,
        "measured_factor_fill": {
            "current_factor_over_matrix_nnz": (
                current_inventory["factor_nnz"]
                / current_inventory["matrix_nnz"]
            ),
            "shadow_factor_over_matrix_nnz": (
                shadow_inventory["factor_nnz"]
                / shadow_inventory["matrix_nnz"]
            ),
            "incremental_factor_over_matrix_nnz": (
                delta["factor_nnz"] / delta["matrix_nnz"]
            ),
        },
        "global_apportioned_cost": global_cost,
        "peak_proxy_components": {
            "matrix_csr_bytes": matrix_bytes,
            "factor_csr_bytes": factor_bytes,
            "simultaneous_vector_bytes": vector_bytes,
            "petsc_scalar_bytes": _PETSC_SCALAR_BYTES,
            "petsc_int_bytes": _PETSC_INT_BYTES,
            "simultaneous_attributable_vector_count": (
                _SIMULTANEOUS_ATTRIBUTABLE_VECTOR_COUNT
            ),
            "unallocated_csr_terminal_pointer_bytes": (
                unallocated_terminal_bytes
            ),
        },
        "integer_apportionment": {
            "algorithm": (
                "Hamilton largest remainder with target-id tie break"
            ),
            "weights_are_leaf_count": False,
            "weights_are_eta": False,
            "eligible_only": True,
            "all_integer_costs_nonnegative": True,
        },
        "common_cost_exclusion": {
            "measured_solver_job_peak_delta_bytes": (
                delta["solver_peak_bytes"]
            ),
            "solver_job_peak_distributed_to_leaves": False,
            "excluded_classes": [
                "MPI runtime and per-rank duplication",
                "native allocator arenas",
                "JIT/import/compiler state",
                "mesh and immutable geometry",
                "common PETSc/MUMPS control objects",
                "watchdog and postprocess lifecycle overlap",
            ],
        },
        "rows": model_rows,
        "row_catalog_sha256": _json_sha256(
            [row["row_sha256"] for row in model_rows],
            namespace="task035e.structural-cost-row-catalog.v1",
        ),
        "closure": closure,
    }
    if not all(item["closed"] for item in closure.values()):
        raise AssertionError("structural-cost closure failed")
    return {
        **unsigned,
        "model_sha256": _json_sha256(
            unsigned,
            namespace=STRUCTURAL_COST_MODEL_SCHEMA,
        ),
    }


def validate_structural_cost_model(
    raw: Mapping[str, Any],
    *,
    action_kind: str,
    dwr_rows: Mapping[str, Mapping[str, Any]],
) -> dict[str, dict[str, int]]:
    """Replay a cost model and return the goal-marker cost rows."""

    unsigned = dict(raw)
    model_sha = _sha256(
        unsigned.pop("model_sha256", None),
        label="structural cost model SHA-256",
    )
    if (
        model_sha
        != _json_sha256(
            unsigned,
            namespace=STRUCTURAL_COST_MODEL_SCHEMA,
        )
        or raw.get("schema_version") != STRUCTURAL_COST_MODEL_SCHEMA
        or raw.get("status")
        != "action_specific_structural_cost_model_pass"
        or raw.get("pass") is not True
        or raw.get("action_kind") != action_kind
    ):
        raise CellwiseAuthorityError(
            "structural cost model identity or action kind differs"
        )
    apportionment = _mapping(
        raw.get("integer_apportionment"),
        label="structural cost apportionment",
    )
    exclusion = _mapping(
        raw.get("common_cost_exclusion"),
        label="structural cost exclusion",
    )
    classification = _mapping(
        raw.get("measurement_classification"),
        label="structural cost measurement classification",
    )
    if (
        apportionment.get("weights_are_leaf_count") is not False
        or apportionment.get("weights_are_eta") is not False
        or apportionment.get("eligible_only") is not True
        or exclusion.get("solver_job_peak_distributed_to_leaves") is not False
        or classification.get("endpoint_inventories") != "measured"
        or classification.get("per_leaf_peak")
        != "derived_only_from_apportioned_matrix_factor_vector_bytes"
    ):
        raise CellwiseAuthorityError(
            "structural cost model uses a forbidden weight or peak basis"
        )
    inventory_names = (
        "raw_active_fe_dofs",
        "active_fe_dofs",
        "matrix_rows",
        "matrix_nnz",
        "factor_nnz",
        "solver_peak_bytes",
    )
    current_inventory_raw = _mapping(
        raw.get("current_inventory"),
        label="current structural inventory",
    )
    shadow_inventory_raw = _mapping(
        raw.get("shadow_inventory"),
        label="shadow structural inventory",
    )
    delta_raw = _mapping(
        raw.get("measured_global_delta"),
        label="measured structural delta",
    )
    if (
        set(current_inventory_raw) != set(inventory_names)
        or set(shadow_inventory_raw) != set(inventory_names)
        or set(delta_raw) != set(inventory_names)
    ):
        raise CellwiseAuthorityError(
            "structural endpoint inventory fields differ"
        )
    current_inventory = {
        name: _nonnegative_integer(
            current_inventory_raw[name],
            label=f"current inventory {name}",
        )
        for name in inventory_names
    }
    shadow_inventory = {
        name: _nonnegative_integer(
            shadow_inventory_raw[name],
            label=f"shadow inventory {name}",
        )
        for name in inventory_names
    }
    measured_delta = {}
    for name in inventory_names:
        value = delta_raw[name]
        if type(value) is not int:
            raise CellwiseAuthorityError(
                f"measured structural delta {name} must be integral"
            )
        measured_delta[name] = value
        if value != shadow_inventory[name] - current_inventory[name]:
            raise CellwiseAuthorityError(
                f"measured structural delta {name} does not close endpoints"
            )
    if any(
        measured_delta[name] <= 0
        for name in ("active_fe_dofs", "matrix_rows", "matrix_nnz", "factor_nnz")
    ):
        raise CellwiseAuthorityError(
            "structural enrichment delta is not positive"
        )
    raw_rows = _sequence(raw.get("rows"), label="structural cost rows")
    rows: dict[str, dict[str, int]] = {}
    row_hashes = []
    for index, raw_row in enumerate(raw_rows):
        row = _mapping(raw_row, label=f"structural cost row {index}")
        unsigned_row = dict(row)
        row_sha = _sha256(
            unsigned_row.pop("row_sha256", None),
            label=f"structural cost row {index} SHA-256",
        )
        target_id = row.get("target_id")
        if (
            row_sha
            != _json_sha256(
                unsigned_row,
                namespace=STRUCTURAL_COST_ROW_SCHEMA,
            )
            or row.get("schema_version") != STRUCTURAL_COST_ROW_SCHEMA
            or not isinstance(target_id, str)
            or target_id not in dwr_rows
            or row.get("dwr_row_sha256")
            != dwr_rows[target_id].get("row_sha256")
            or target_id in rows
        ):
            raise CellwiseAuthorityError(
                f"structural cost row {index} identity differs"
            )
        costs = _mapping(
            row.get("apportioned_cost"),
            label=f"structural cost row {index} apportioned cost",
        )
        if set(costs) != set(_COST_FIELDS):
            raise CellwiseAuthorityError(
                f"structural cost row {index} fields differ"
            )
        rows[target_id] = {
            name: _nonnegative_integer(
                costs[name],
                label=f"structural cost row {index} {name}",
            )
            for name in _COST_FIELDS
        }
        row_hashes.append(row_sha)
    if (
        set(rows) != set(dwr_rows)
        or raw.get("row_catalog_sha256")
        != _json_sha256(
            row_hashes,
            namespace="task035e.structural-cost-row-catalog.v1",
        )
    ):
        raise CellwiseAuthorityError(
            "structural cost row catalog differs from DWR leaves"
        )
    global_cost = _mapping(
        raw.get("global_apportioned_cost"),
        label="global apportioned cost",
    )
    closure = _mapping(raw.get("closure"), label="cost closure")
    if set(global_cost) != set(_COST_FIELDS) or set(closure) != set(
        _COST_FIELDS
    ):
        raise CellwiseAuthorityError("structural cost closure fields differ")
    expected_measured_cost = {
        "estimated_added_active_dofs": measured_delta["active_fe_dofs"],
        "estimated_added_rows": measured_delta["matrix_rows"],
        "estimated_added_matrix_nnz": measured_delta["matrix_nnz"],
        "estimated_added_factor_nnz": measured_delta["factor_nnz"],
    }
    if any(
        global_cost.get(name) != value
        for name, value in expected_measured_cost.items()
    ):
        raise CellwiseAuthorityError(
            "global apportioned cost differs from measured endpoint deltas"
        )
    peak = _mapping(
        raw.get("peak_proxy_components"),
        label="peak proxy components",
    )
    required_peak_fields = {
        "matrix_csr_bytes",
        "factor_csr_bytes",
        "simultaneous_vector_bytes",
        "petsc_scalar_bytes",
        "petsc_int_bytes",
        "simultaneous_attributable_vector_count",
        "unallocated_csr_terminal_pointer_bytes",
    }
    if set(peak) != required_peak_fields:
        raise CellwiseAuthorityError("peak proxy component fields differ")
    if (
        peak.get("petsc_scalar_bytes") != _PETSC_SCALAR_BYTES
        or peak.get("petsc_int_bytes") != _PETSC_INT_BYTES
        or peak.get("simultaneous_attributable_vector_count")
        != _SIMULTANEOUS_ATTRIBUTABLE_VECTOR_COUNT
    ):
        raise CellwiseAuthorityError(
            "peak proxy PETSc scalar/int/vector identity differs"
        )
    expected_matrix_bytes = (
        measured_delta["matrix_nnz"]
        * (_PETSC_SCALAR_BYTES + _PETSC_INT_BYTES)
        + (measured_delta["matrix_rows"] + 1) * _PETSC_INT_BYTES
    )
    expected_factor_bytes = (
        measured_delta["factor_nnz"]
        * (_PETSC_SCALAR_BYTES + _PETSC_INT_BYTES)
        + (measured_delta["matrix_rows"] + 1) * _PETSC_INT_BYTES
    )
    expected_vector_bytes = (
        measured_delta["matrix_rows"]
        * _SIMULTANEOUS_ATTRIBUTABLE_VECTOR_COUNT
        * _PETSC_SCALAR_BYTES
    )
    expected_peak = (
        expected_matrix_bytes + expected_factor_bytes + expected_vector_bytes
    )
    if (
        peak.get("matrix_csr_bytes") != expected_matrix_bytes
        or peak.get("factor_csr_bytes") != expected_factor_bytes
        or peak.get("simultaneous_vector_bytes") != expected_vector_bytes
        or peak.get("unallocated_csr_terminal_pointer_bytes")
        != 2 * _PETSC_INT_BYTES
        or global_cost.get("estimated_added_solver_peak_bytes")
        != expected_peak
        or exclusion.get("measured_solver_job_peak_delta_bytes")
        != measured_delta["solver_peak_bytes"]
    ):
        raise CellwiseAuthorityError(
            "peak proxy is not derived solely from structural bytes"
        )
    for name in _COST_FIELDS:
        expected = _nonnegative_integer(
            global_cost[name],
            label=f"global cost {name}",
        )
        row = _mapping(closure[name], label=f"cost closure {name}")
        apportioned = sum(cost[name] for cost in rows.values())
        unallocated = _nonnegative_integer(
            row.get("unallocated"),
            label=f"cost closure {name} unallocated",
        )
        if (
            row.get("expected") != expected
            or row.get("apportioned") != apportioned
            or row.get("closed") is not True
            or apportioned + unallocated != expected
        ):
            raise CellwiseAuthorityError(
                f"structural cost closure failed for {name}"
            )
    return rows


def build_cellwise_authority(
    *,
    current_record_path: Path,
    current_record_file_sha256: str,
    shadow_record_path: Path,
    shadow_record_file_sha256: str,
    current_output_path: Path,
    current_output_file_sha256: str,
    shadow_output_path: Path,
    shadow_output_file_sha256: str,
    live_shadow_evidence_path: Path,
    live_shadow_evidence_file_sha256: str,
    source_sha: str,
    action_kind: str,
) -> Mapping[str, Any]:
    """Build one positive authority or raise on identity drift."""

    source = _source_sha(source_sha)
    kind = str(action_kind)
    if kind not in _ACTION_KINDS:
        raise CellwiseAuthorityError("action kind must be p-up or h-refine")
    current, current_record_sha, current_output_file_sha = _candidate(
        current_record_path,
        current_record_file_sha256,
        current_output_path,
        current_output_file_sha256,
        role="current",
        label="current",
    )
    shadow, shadow_record_sha, shadow_output_file_sha = _candidate(
        shadow_record_path,
        shadow_record_file_sha256,
        shadow_output_path,
        shadow_output_file_sha256,
        role=_SHADOW_ROLE[kind],
        label="shadow",
    )
    if (
        current.source_sha != source
        or shadow.source_sha != source
        or current.trial_id != shadow.trial_id
        or current.cycle_index != shadow.cycle_index
    ):
        raise CellwiseAuthorityError(
            "current/shadow source, trial, or cycle differs"
        )
    current_plan, current_plan_path, current_plan_sha = (
        _load_bound_private_json(
            current.plan_path,
            current.plan_file_sha256,
            label="current solver plan",
        )
    )
    state = _current_state(current_plan, source_sha=source)
    if state.cycle_index != current.cycle_index:
        raise CellwiseAuthorityError(
            "current candidate cycle differs from the replayed solver plan"
        )
    live, live_path, live_file_sha = _load_bound_private_json(
        live_shadow_evidence_path,
        live_shadow_evidence_file_sha256,
        label="live shadow evidence",
    )
    report, partition, global_signed, live_payload_sha = (
        _validate_live_evidence(
            live,
            file_sha256=live_file_sha,
            current=current,
            shadow=shadow,
            action_kind=kind,
            live_path=live_path,
        )
    )
    dwr_rows = _validate_partition(
        partition,
        state=state,
        current=current,
        shadow=shadow,
        global_signed=global_signed,
    )
    operator = _mapping(
        report.get("operator_identity"),
        label="actual DWR operator identity",
    )
    matrix = _mapping(
        operator.get("matrix"),
        label="actual DWR matrix identity",
    )
    if (
        matrix.get("global_shape")
        != [
            shadow.structural_inventory["matrix_rows"],
            shadow.structural_inventory["matrix_rows"],
        ]
        or matrix.get("global_nnz")
        != shadow.structural_inventory["matrix_nnz"]
    ):
        raise CellwiseAuthorityError(
            "actual DWR CSR identity differs from the shadow endpoint"
        )
    costs = _structural_cost_model(
        current=current,
        shadow=shadow,
        state=state,
        dwr_rows=dwr_rows,
        action_kind=kind,
    )
    # Replay once before publication so the embedded row/cost binding is not
    # merely asserted by the producer.
    validate_structural_cost_model(
        costs,
        action_kind=kind,
        dwr_rows=dwr_rows,
    )
    current_goals = goal_vector_from_candidate_output(current.payload)
    shadow_goals = goal_vector_from_candidate_output(shadow.payload)
    unsigned = {
        "schema_version": CELLWISE_DWR_AUTHORITY_SCHEMA,
        "status": "cellwise_59_goal_dwr_pass",
        "pass": True,
        "producer_role": "live_cellwise_residual_adjoint_localizer",
        "source_sha": source,
        "mpi_size": 8,
        "trial_id": current.trial_id,
        "cycle_index": state.cycle_index,
        "action_kind": kind,
        "current_plan_file_sha256": current_plan_sha,
        "current_plan_content_sha256": _json_sha256(current_plan),
        "current_state_sha256": state.state_sha256,
        "current_leaf_catalog_sha256": state.audit[
            "leaf_catalog_sha256"
        ],
        "current_degree_plan_sha256": state.audit[
            "cell_degree_plan_sha256"
        ],
        "current_watchdog_record_sha256": current_record_sha,
        "shadow_watchdog_record_sha256": shadow_record_sha,
        "current_output_file_sha256": current_output_file_sha,
        "shadow_output_file_sha256": shadow_output_file_sha,
        "current_output_sha256": current.output_sha256,
        "shadow_output_sha256": shadow.output_sha256,
        "live_shadow_evidence_file_sha256": live_file_sha,
        "live_shadow_evidence_payload_sha256": live_payload_sha,
        "current_goal_values": dict(current_goals.by_id),
        "current_goal_sha256": current_goals.sha256,
        "shadow_goal_values": dict(shadow_goals.by_id),
        "shadow_goal_sha256": shadow_goals.sha256,
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
        "ordered_goal_ids": list(FORMAL_GOAL_IDS),
        "global_actual_dwr_report": dict(report),
        "localization": dict(partition),
        "structural_cost_model": dict(costs),
        "actual_cellwise_residual_adjoint_pairing": True,
        "signed_not_absolute": True,
        "synthetic": False,
        "reference_derived": False,
        "hidden_auditor_consumed": False,
        "ordinary_default_changed": False,
    }
    return {
        **unsigned,
        "authority_sha256": _json_sha256(
            unsigned,
            namespace=CELLWISE_DWR_AUTHORITY_SCHEMA,
        ),
    }


def _controlled_negative(
    *,
    source_sha: str,
    action_kind: str,
    message: str,
) -> Mapping[str, Any]:
    unsigned = {
        "schema_version": CELLWISE_AUTHORITY_FAILURE_SCHEMA,
        "status": "cellwise_authority_controlled_negative",
        "classification": "STRUCTURAL_COST_EVIDENCE_INCOMPLETE",
        "pass": False,
        "source_sha": source_sha,
        "action_kind": action_kind,
        "error": message,
        "global_eta_evenly_distributed": False,
        "leaf_count_cost_distribution_used": False,
        "eta_cost_distribution_used": False,
        "accuracy_credit": False,
    }
    return {
        **unsigned,
        "payload_sha256": _json_sha256(
            unsigned,
            namespace=CELLWISE_AUTHORITY_FAILURE_SCHEMA,
        ),
    }


def _atomic_mode_0600(path: Path, payload: Mapping[str, Any]) -> str:
    output = _safe_path(path, label="cellwise authority output")
    if os.path.lexists(output):
        raise FileExistsError(
            f"refusing to overwrite immutable output: {output}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    encoded = (
        json.dumps(
            payload,
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    descriptor, temporary_name = tempfile.mkstemp(
        dir=output.parent,
        prefix=f".{output.name}.",
        suffix=".tmp",
    )
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, output)
        temporary.unlink()
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        temporary.unlink(missing_ok=True)
        raise
    return hashlib.sha256(encoded).hexdigest()


def write_cellwise_authority(
    path: Path,
    payload: Mapping[str, Any],
) -> CellwiseAuthorityWriteReceipt:
    """Write one immutable positive or controlled-negative authority."""

    file_sha = _atomic_mode_0600(path, payload)
    status = str(payload.get("status"))
    classification = (
        "REFERENCE_BLIND_CELLWISE_AUTHORITY_PASS"
        if payload.get("pass") is True
        else str(payload.get("classification"))
    )
    payload_sha = str(
        payload.get("authority_sha256", payload.get("payload_sha256"))
    )
    return CellwiseAuthorityWriteReceipt(
        path=path.resolve(),
        file_sha256=file_sha,
        payload_sha256=payload_sha,
        status=status,
        classification=classification,
        byte_count=path.stat().st_size,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--current-record", type=Path, required=True)
    parser.add_argument("--current-record-sha256", required=True)
    parser.add_argument("--shadow-record", type=Path, required=True)
    parser.add_argument("--shadow-record-sha256", required=True)
    parser.add_argument("--current-output", type=Path, required=True)
    parser.add_argument("--current-output-sha256", required=True)
    parser.add_argument("--shadow-output", type=Path, required=True)
    parser.add_argument("--shadow-output-sha256", required=True)
    parser.add_argument("--live-shadow-evidence", type=Path, required=True)
    parser.add_argument("--live-shadow-evidence-sha256", required=True)
    parser.add_argument("--verified-clean-sha", required=True)
    parser.add_argument(
        "--action-kind",
        choices=tuple(sorted(_ACTION_KINDS)),
        required=True,
    )
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        source = _source_sha(args.verified_clean_sha)
        payload = build_cellwise_authority(
            current_record_path=args.current_record,
            current_record_file_sha256=args.current_record_sha256,
            shadow_record_path=args.shadow_record,
            shadow_record_file_sha256=args.shadow_record_sha256,
            current_output_path=args.current_output,
            current_output_file_sha256=args.current_output_sha256,
            shadow_output_path=args.shadow_output,
            shadow_output_file_sha256=args.shadow_output_sha256,
            live_shadow_evidence_path=args.live_shadow_evidence,
            live_shadow_evidence_file_sha256=(
                args.live_shadow_evidence_sha256
            ),
            source_sha=source,
            action_kind=args.action_kind,
        )
    except (
        CellwiseAuthorityError,
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
    ) as error:
        payload = _controlled_negative(
            source_sha=str(args.verified_clean_sha),
            action_kind=str(args.action_kind),
            message=str(error),
        )
    try:
        receipt = write_cellwise_authority(args.output, payload)
    except (CellwiseAuthorityError, FileExistsError, OSError) as error:
        print(
            json.dumps(
                {
                    "schema_version": CELLWISE_AUTHORITY_RECEIPT_SCHEMA,
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
                "schema_version": CELLWISE_AUTHORITY_RECEIPT_SCHEMA,
                "status": "completed",
                "artifact_status": receipt.status,
                "classification": receipt.classification,
                "path": str(receipt.path),
                "file_sha256": receipt.file_sha256,
                "payload_sha256": receipt.payload_sha256,
                "byte_count": receipt.byte_count,
            },
            sort_keys=True,
        )
    )
    return 0 if payload.get("pass") is True else 3


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "CELLWISE_AUTHORITY_FAILURE_SCHEMA",
    "CELLWISE_AUTHORITY_RECEIPT_SCHEMA",
    "CELLWISE_DWR_AUTHORITY_SCHEMA",
    "STRUCTURAL_COST_MODEL_SCHEMA",
    "STRUCTURAL_COST_ROW_SCHEMA",
    "CellwiseAuthorityError",
    "CellwiseAuthorityWriteReceipt",
    "build_cellwise_authority",
    "main",
    "validate_structural_cost_model",
    "write_cellwise_authority",
]
