"""Shared JSON/hash identity reader for accepted Task43 candidate artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected a JSON object at {path}")
    return value


def _artifact_path(value: str, root: Path) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (root / path).resolve()


def load_accepted_parent_artifacts(
    selection_path: Path,
    *,
    artifact_root: Path,
    acceptance_contract_path: Path,
) -> dict[str, Any]:
    """Read and hash-check one accepted selection and its selected candidate.

    The returned JSON is identity evidence only. Callers still validate their
    own forest/degree plan, candidate provenance, physics, and raw numerical
    gates; this function does not recompute a solver or checker result.
    """

    selection_path = Path(selection_path).resolve()
    selection = _read_json(selection_path)
    if (
        selection.get("schema") != "task43.selection-decision.v1"
        or selection.get("status") != "accepted"
    ):
        raise ValueError("parent selection must be a frozen accepted decision")
    selected = selection.get("selected_candidate")
    if not isinstance(selected, dict):
        raise TypeError("accepted selection lacks its selected_candidate object")
    candidate_id = str(selected["candidate_id"])
    run_root = _artifact_path(str(selected["run_root"]), artifact_root)
    comparison_path = _artifact_path(
        str(selected["comparison_record_path"]), artifact_root
    )
    record_path = run_root / "task43_round1_candidate_record.json"
    storage_path = run_root / "candidate_recovered_solution_storage.npz"
    plan_path = run_root / "candidate_plan.json"
    hashes = {
        "record_sha256": _sha256_file(record_path),
        "storage_sha256": _sha256_file(storage_path),
        "plan_sha256": _sha256_file(plan_path),
        "comparison_record_sha256": _sha256_file(comparison_path),
    }
    if any(selected.get(key) != value for key, value in hashes.items()):
        raise ValueError("accepted selection hashes differ from candidate artifacts")

    acceptance_contract_path = Path(acceptance_contract_path).resolve()
    acceptance = _read_json(acceptance_contract_path)
    acceptance_sha = _sha256_file(acceptance_contract_path)
    selection_sha = _sha256_file(selection_path)
    comparison = _read_json(comparison_path)
    verified = comparison.get("verified_source_contracts", {})
    if (
        comparison.get("candidate_id") != candidate_id
        or comparison.get("selection", {}).get("gates", {}).get("pass") is not True
        or verified.get("candidate_raw_hard_gate_recalculation", {}).get("pass")
        is not True
        or comparison.get("selection_reference") != "Y6_1"
        or comparison.get("holdout_read") is not False
        or comparison.get("final_p6_control_read") is not False
        or verified.get("round1_acceptance_contract_sha256") != acceptance_sha
        or verified.get("comparison_contract_sha256")
        != acceptance["evidence"]["comparison_contract"]["sha256"]
        or verified.get("reference_calibration_sha256")
        != acceptance["evidence"]["reference_and_quadrature"]["sha256"]
        or selected.get("acceptance_contract_sha256") != acceptance_sha
        or comparison.get("candidate_record_sha256") != hashes["record_sha256"]
        or comparison.get("candidate_storage_sha256") != hashes["storage_sha256"]
        or comparison.get("candidate_plan_sha256") != hashes["plan_sha256"]
    ):
        raise ValueError("accepted comparison does not match frozen candidate contracts")

    record = _read_json(record_path)
    plan = _read_json(plan_path)
    storage_identity = record.get("recovered_solution_storage", {})
    if (
        record.get("candidate_identity", {}).get("candidate_id") != candidate_id
        or record.get("gates", {}).get("pass") is not True
        or record.get("solver", {}).get("official_result") is not True
        or record.get("solver", {}).get("case_status") != "completed"
        or plan.get("task43_candidate", {}).get("candidate_id") != candidate_id
        or storage_identity.get("sha256") != hashes["storage_sha256"]
    ):
        raise ValueError("selected parent record, storage, or plan identity is invalid")
    actual_dofs = int(storage_identity["independent_active_fe_dofs"])
    if selected.get("independent_FE_dofs") is not None and int(
        selected["independent_FE_dofs"]
    ) != actual_dofs:
        raise ValueError("accepted selection DoF differs from parent storage record")

    return {
        "selection_path": selection_path,
        "selection_sha256": selection_sha,
        "selection": selection,
        "selected": selected,
        "candidate_id": candidate_id,
        "run_root": run_root,
        "comparison_path": comparison_path,
        "record_path": record_path,
        "storage_path": storage_path,
        "plan_path": plan_path,
        "comparison": comparison,
        "record": record,
        "plan": plan,
        "acceptance": acceptance,
        "acceptance_contract_sha256": acceptance_sha,
        "hashes": hashes,
        "independent_FE_dofs": actual_dofs,
    }
