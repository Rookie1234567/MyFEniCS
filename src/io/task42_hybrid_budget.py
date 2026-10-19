"""Hash-bound, fail-closed phase budgets for the Task42 Hybrid direct profile."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from src.common.task42_phase_admission import TASK42_HYBRID_A2_PHASE_OBJECTS

TASK42_HYBRID_PHASE_BUDGET_SCHEMA = "task42.hybrid-direct-phase-budget.v2"
_BUDGET_REFERENCE_FIELDS = frozenset(
    {"phase_budget_manifest", "phase_budget_manifest_sha256"}
)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported phase-budget basis value {type(value).__name__}")


def task42_phase_budget_basis_sha256(input_document: Mapping[str, Any]) -> str:
    """Hash the parsed dat contract with only its two manifest references removed.

    This is deliberately distinct from the byte-exact ``input_sha256`` retained
    by the run and output records. It makes the dat -> manifest -> dat binding
    acyclic while still binding every parsed input field other than the manifest
    path and manifest SHA themselves.
    """

    document = _jsonable(input_document)
    execution = document.get("execution")
    if not isinstance(execution, dict):
        raise TypeError("Task42 phase-budget basis requires an execution table")
    for key in _BUDGET_REFERENCE_FIELDS:
        execution.pop(key, None)
    return hashlib.sha256(
        json.dumps(
            document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


def load_task42_hybrid_phase_budget(
    execution: Mapping[str, Any],
    *,
    model_id: str,
    run_id: str,
    comparison_group: str,
    budget_basis_sha256: str | None,
    physical_model_sha256: str,
    material_identity_sha256: str,
    source_sha: str,
    mpi_size: int,
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Load one identity-bound budget manifest; absence is explicit pending sizing."""

    path_text = execution.get("phase_budget_manifest")
    expected_sha = execution.get("phase_budget_manifest_sha256")
    if path_text is None and expected_sha is None:
        return None, None, None
    if not isinstance(path_text, str) or not isinstance(expected_sha, str):
        return None, None, "phase budget manifest path/SHA must be supplied together"
    if (
        not isinstance(budget_basis_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", budget_basis_sha256)
    ):
        return None, None, "phase budget basis SHA256 is missing or invalid"
    path = Path(path_text)
    if not path.is_absolute():
        return None, None, "phase budget manifest path must be absolute"
    if (
        len(expected_sha) != 64
        or expected_sha != expected_sha.lower()
        or any(ch not in "0123456789abcdef" for ch in expected_sha)
    ):
        return None, None, "phase budget manifest SHA must be lowercase SHA256"
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, None, f"phase budget manifest is unreadable: {exc}"
    actual_sha = hashlib.sha256(raw).hexdigest()
    if actual_sha != expected_sha:
        return None, actual_sha, "phase budget manifest SHA mismatch"
    try:
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return None, actual_sha, f"phase budget manifest JSON is invalid: {exc}"
    if not isinstance(manifest, dict):
        return None, actual_sha, "phase budget manifest must be a JSON object"
    expected = {
        "schema": TASK42_HYBRID_PHASE_BUDGET_SCHEMA,
        "model_id": model_id,
        "run_id": run_id,
        "comparison_group": comparison_group,
        "budget_basis_sha256": budget_basis_sha256,
        "physical_model_sha256": physical_model_sha256,
        "material_identity_sha256": material_identity_sha256,
        "source_sha": source_sha,
        "mpi_size": mpi_size,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            return None, actual_sha, f"phase budget manifest {key} mismatch"
    phases = manifest.get("phases")
    expected_phases = set(TASK42_HYBRID_A2_PHASE_OBJECTS)
    if not isinstance(phases, dict) or set(phases) != expected_phases:
        return None, actual_sha, "phase budget manifest does not cover the complete A2 phase set"
    manifest["manifest_file_sha256"] = actual_sha
    return manifest, actual_sha, None


def _matched_phase_components(
    manifest: Mapping[str, Any] | None,
    *,
    stage: str,
    expected_inventory: Mapping[str, Any],
    mpi_size: int,
    rank: int | None = None,
) -> tuple[list[Mapping[str, Any]] | None, list[str]]:
    if manifest is None:
        return None, ["phase_budget_manifest_missing_pending_sizing"]
    phases = manifest.get("phases")
    phase_record = phases.get(stage) if isinstance(phases, Mapping) else None
    expected_components = expected_inventory.get("components")
    budget_components = (
        phase_record.get("components") if isinstance(phase_record, Mapping) else None
    )
    if not isinstance(expected_components, list) or not isinstance(budget_components, list):
        return None, [f"phase_budget_components_missing:{stage}"]
    by_name = {
        item.get("name"): item
        for item in budget_components
        if isinstance(item, Mapping) and isinstance(item.get("name"), str)
    }
    expected_names = {
        item.get("name") for item in expected_components if isinstance(item, Mapping)
    }
    if len(by_name) != len(budget_components) or set(by_name) != expected_names:
        return None, [f"phase_budget_component_names_mismatch:{stage}"]
    errors: list[str] = []
    for expected in expected_components:
        if not isinstance(expected, Mapping):
            errors.append("phase_inventory_component_is_not_a_mapping")
            continue
        budget = by_name[str(expected.get("name"))]
        for key in ("scope", "unit", "formula", "lifetime", "allocation_boundary"):
            if budget.get(key) != expected.get(key):
                errors.append(
                    f"phase_budget_component_{expected.get('name')}_{key}_mismatch"
                )
        sizing_basis_by_rank = budget.get("sizing_basis_by_rank")
        uncertainty = budget.get("uncertainty")
        if (
            not isinstance(sizing_basis_by_rank, list)
            or len(sizing_basis_by_rank) != mpi_size
            or any(not isinstance(item, Mapping) or not item for item in sizing_basis_by_rank)
        ):
            errors.append(
                f"phase_budget_component_{expected.get('name')}_rank_sizing_basis_invalid"
            )
        else:
            expected_basis = expected.get("sizing_basis")
            inventory_status = expected_inventory.get("status")
            if inventory_status == "pending-sizing":
                # The inventory's sizing_basis is explanatory text, not an
                # observed basis.  The manifest carries the hash-bound
                # per-rank predicted basis and byte estimate for this pending
                # boundary; do not compare a mapping to the description.
                if not isinstance(expected_basis, str) or not expected_basis.strip():
                    errors.append(
                        f"phase_inventory_component_{expected.get('name')}_pending_basis_description_invalid"
                    )
            elif inventory_status == "source-derived-prediction":
                # Dynamic assembly inventories contain the actual source basis
                # from this rank.  A job-level aggregate cannot prove that
                # basis for every rank, so require the rank-local gate.
                if not isinstance(expected_basis, Mapping) or not expected_basis:
                    errors.append(
                        f"phase_inventory_component_{expected.get('name')}_actual_basis_invalid"
                    )
                elif rank is None:
                    errors.append(
                        f"phase_budget_component_{expected.get('name')}_actual_sizing_basis_requires_rank"
                    )
                elif expected_basis != sizing_basis_by_rank[rank]:
                    errors.append(
                        f"phase_budget_component_{expected.get('name')}_sizing_basis_mismatch_rank_{rank}"
                    )
            else:
                errors.append(
                    f"phase_inventory_component_{expected.get('name')}_status_invalid_for_sizing_basis"
                )
        if not isinstance(uncertainty, str) or not uncertainty.strip():
            errors.append(
                f"phase_budget_component_{expected.get('name')}_uncertainty_missing"
            )
        values = budget.get("delta_bytes_by_rank")
        if (
            not isinstance(values, list)
            or len(values) != mpi_size
            or any(type(value) is not int or value < 0 for value in values)
        ):
            errors.append(
                f"phase_budget_component_{expected.get('name')}_rank_bytes_invalid"
            )
        elif budget.get("scope") == "rank_local" and sum(values) <= 0:
            errors.append(
                f"phase_budget_component_{expected.get('name')}_all_rank_Delta_is_zero"
            )
        elif budget.get("scope") == "global_replicated" and len(set(values)) == 1 and values[0] <= 0:
            errors.append(
                f"phase_budget_component_{expected.get('name')}_replicated_Delta_is_zero"
            )
    return (None if errors else [by_name[str(name)] for name in sorted(expected_names)]), errors


def phase_budget_for_job(
    manifest: Mapping[str, Any] | None,
    *,
    stage: str,
    expected_inventory: Mapping[str, Any],
    mpi_size: int,
) -> tuple[int | None, dict[str, Any], list[str]]:
    """Validate and aggregate one whole-job phase before a public worker spawn."""

    components, errors = _matched_phase_components(
        manifest,
        stage=stage,
        expected_inventory=expected_inventory,
        mpi_size=mpi_size,
    )
    if errors or components is None:
        return None, dict(expected_inventory), errors
    total = 0
    result_components: list[dict[str, Any]] = []
    for item in components:
        values = item["delta_bytes_by_rank"]
        scope = item.get("scope")
        if scope == "rank_local":
            amount = sum(values)
        elif scope == "global_replicated":
            # This scope is one global-total repeated in rank reports. It is
            # counted once; actual per-rank copies belong under rank_local.
            if len(set(values)) != 1:
                errors.append(f"phase_budget_{item.get('name')}_replicated_value_differs")
                continue
            amount = values[0]
        else:
            errors.append(f"phase_budget_{item.get('name')}_scope_invalid")
            continue
        total += amount
        result_components.append({**dict(item), "delta_bytes": amount})
    if errors:
        return None, dict(expected_inventory), errors
    if total <= 0:
        return None, dict(expected_inventory), ["phase_budget_total_Delta_must_be_positive"]
    return total, {
        **dict(expected_inventory),
        "status": "budget-bound",
        "components": result_components,
        "manifest_file_sha256": manifest.get("manifest_file_sha256")
        if isinstance(manifest, Mapping)
        else None,
    }, []


def phase_budget_for_rank(
    manifest: Mapping[str, Any] | None,
    *,
    stage: str,
    inventory: Mapping[str, Any],
    rank: int,
    mpi_size: int,
) -> tuple[int | None, dict[str, Any], list[str]]:
    """Read rank-local component bytes only after exact descriptor matching."""

    if manifest is None:
        return None, dict(inventory), ["phase_budget_manifest_missing_pending_sizing"]
    if type(rank) is not int or type(mpi_size) is not int or not 0 <= rank < mpi_size:
        return None, dict(inventory), ["phase_budget_rank_or_mpi_size_is_invalid"]
    components, errors = _matched_phase_components(
        manifest,
        stage=stage,
        expected_inventory=inventory,
        mpi_size=mpi_size,
        rank=rank,
    )
    if errors or components is None:
        return None, dict(inventory), errors
    by_name = {item.get("name"): item for item in components}
    expected_components = inventory.get("components")
    selected: list[dict[str, Any]] = []
    local_delta = 0
    errors = []
    for expected in expected_components:
        if not isinstance(expected, Mapping):
            errors.append("phase_inventory_component_is_not_a_mapping")
            continue
        budget = by_name.get(expected.get("name"))
        if not isinstance(budget, Mapping):
            errors.append(f"phase_budget_component_missing:{expected.get('name')}")
            continue
        values = budget.get("delta_bytes_by_rank")
        assert isinstance(values, list)
        amount = values[rank]
        expected_amount = expected.get("delta_bytes")
        if (
            expected_amount is None
            and inventory.get("status") == "pending-sizing"
        ):
            # A separate, hash-bound sizing manifest may supply a prediction for
            # this statically declared phase. The current source inventory still
            # marks the amount pending; no implicit zero or A1 peak is substituted.
            pass
        elif type(expected_amount) is not int or expected_amount < 0:
            errors.append(
                f"phase_inventory_component_{expected.get('name')}_Delta_is_pending_or_invalid"
            )
            continue
        elif amount != expected_amount:
            errors.append(
                f"phase_budget_component_{expected.get('name')}_actual_Delta_mismatch"
            )
            continue
        if expected.get("scope") not in {"rank_local", "global_replicated"}:
            errors.append(
                f"phase_inventory_component_{expected.get('name')}_scope_is_unresolved"
            )
            continue
        selected.append(
            {
                **dict(expected),
                "delta_bytes": amount,
            }
        )
        if expected.get("scope") == "rank_local":
            local_delta += amount
    if errors:
        return None, dict(inventory), errors
    result = {
        **dict(inventory),
        "status": "budget-bound",
        "budget_manifest_sha256": manifest.get("manifest_file_sha256"),
        "components": selected,
    }
    return local_delta, result, []


def whole_job_phase_delta(phase: Mapping[str, Any], mpi_size: int) -> tuple[int | None, list[str]]:
    """Aggregate one phase's rank byte vectors without multiplying replicated data."""

    components = phase.get("components")
    if not isinstance(components, list) or not components:
        return None, ["phase_budget_components_missing"]
    total = 0
    errors: list[str] = []
    for component in components:
        if not isinstance(component, Mapping):
            errors.append("phase_budget_component_invalid")
            continue
        values = component.get("delta_bytes_by_rank")
        scope = component.get("scope")
        if (
            not isinstance(values, list)
            or len(values) != mpi_size
            or any(type(value) is not int or value < 0 for value in values)
        ):
            errors.append(f"phase_budget_{component.get('name')}_rank_bytes_invalid")
            continue
        if scope == "rank_local":
            total += sum(values)
        elif scope == "global_replicated":
            # Repeated reporting of one global-total is counted once. A real
            # rank-private copy must be represented as rank_local instead.
            if len(set(values)) != 1:
                errors.append(f"phase_budget_{component.get('name')}_replicated_value_differs")
            else:
                total += values[0]
        else:
            errors.append(f"phase_budget_{component.get('name')}_scope_invalid")
    return (None if errors else total), errors


__all__ = [
    "TASK42_HYBRID_PHASE_BUDGET_SCHEMA",
    "load_task42_hybrid_phase_budget",
    "phase_budget_for_job",
    "phase_budget_for_rank",
    "task42_phase_budget_basis_sha256",
    "whole_job_phase_delta",
]
