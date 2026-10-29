"""Thin, opt-in entry point for the fixed V21 R10_H67 research diagnostic.

This module only validates the frozen diagnostic contract and dispatches to
the existing Task43 plan, solve, and comparison entry points.  It never
selects or writes an accepted candidate.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
CONTRACT_REL = Path(
    "docs/task43_hp_adaptivity/outcomes/records/v21_r10_h67_contract.json"
)
SCHEMA = "task43.v21.r10_h67_contract.v1"
REQUIRED_INPUT_ROLES = {
    "accepted9_selection",
    "accepted9_plan",
    "accepted9_record",
    "accepted9_storage",
    "accepted9_comparison",
    "r10_rejection",
    "r10_plan",
    "r10_record",
    "r10_storage",
    "r10_comparison",
    "r10_modal",
    "r10_absorption",
    "round1_acceptance_contract",
    "y6_inventory",
    "y6_restore_identity",
    "y6_resolved_config",
    "y6_recovered_bundle",
    "y6_modal",
    "y6_absorption",
    "v20_proposal",
}
EXPECTED_INPUT_PATHS = {
    "accepted9_selection": "docs/task43_hp_adaptivity/outcomes/records/round9_selection_transition9_v1.json",
    "accepted9_plan": "benchmarks/artifacts/task43/round9_p_only_authority_attempt1/plan_output/plans/round9_p_up.json",
    "accepted9_record": "benchmarks/artifacts/task43/round9_p_up_attempt1/run/task43_round1_candidate_record.json",
    "accepted9_storage": "benchmarks/artifacts/task43/round9_p_up_attempt1/run/candidate_recovered_solution_storage.npz",
    "accepted9_comparison": "benchmarks/artifacts/task43/round1_candidates/comparisons/round9_p_up_attempt1/candidate_comparison_v2.json",
    "r10_rejection": "docs/task43_hp_adaptivity/outcomes/records/round10_rejected_candidate_v1.json",
    "r10_plan": "benchmarks/artifacts/task43/round10_p_up_attempt1/run/candidate_plan.json",
    "r10_record": "benchmarks/artifacts/task43/round10_p_up_attempt1/run/task43_round1_candidate_record.json",
    "r10_storage": "benchmarks/artifacts/task43/round10_p_up_attempt1/run/candidate_recovered_solution_storage.npz",
    "r10_comparison": "benchmarks/artifacts/task43/round1_candidates/comparisons/round10_p_up_attempt1/candidate_comparison_v2.json",
    "r10_modal": "benchmarks/artifacts/task43/round10_p_up_attempt1/run/solve/dtn_port_diffraction_orders_3d.json",
    "r10_absorption": "benchmarks/artifacts/task43/round10_p_up_attempt1/run/solve/volume_absorption.json",
    "round1_acceptance_contract": "docs/task43_hp_adaptivity/outcomes/records/round1_acceptance_contract_v1.json",
    "y6_inventory": "docs/task43_hp_adaptivity/outcomes/records/existing_validation_fields_v1.json",
    "y6_restore_identity": "benchmarks/artifacts/task43/reference_imports/attempt2/Y6_1/restore_identity_record.json",
    "y6_resolved_config": "benchmarks/artifacts/task43/reference_imports/attempt2/Y6_1/resolved_config.json",
    "y6_recovered_bundle": "benchmarks/artifacts/task43/reference_imports/attempt2/Y6_1/recovered_reference_bundle.npz",
    "y6_modal": "benchmarks/artifacts/task43/reference_imports/attempt2/Y6_1/numerical_output/dtn_port_diffraction_orders_3d.json",
    "y6_absorption": "benchmarks/artifacts/task43/reference_imports/attempt2/Y6_1/p6_condensed_direct_summary.json",
    "v20_proposal": "docs/task43_hp_adaptivity/outcomes/records/v20_user_recovery_sources/U1/data/terminal.json",
}
EXPECTED_SLOT_ROOTS = {
    "T1": "support/targeted_attempt1",
    "T2": "support/targeted_recovery1",
    "T3": "support/targeted_recovery2",
    "S": "support/space_attempt1",
    "F1": "formal/R10_H67_attempt1",
    "F2": "formal/R10_H67_attempt2",
    "C": "support/comparison_attempt1",
    "E1": "support/engineering_recovery1",
    "E2": "support/engineering_recovery2",
}
EXPECTED_SLOT_LIMITS = {
    "T1": (270, 300, 8589934592),
    "T2": (270, 300, 8589934592),
    "T3": (270, 300, 8589934592),
    "S": (1740, 1800, 8589934592),
    "F1": (6900, 7200, 34359738368),
    "F2": (6900, 7200, 34359738368),
    "C": (2340, 2400, 8589934592),
    "E1": (1740, 1800, 8589934592),
    "E2": (1740, 1800, 8589934592),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _reject_symlink_components(path: Path, label: str) -> None:
    """Reject a lexical symlink before resolving repository paths."""
    absolute = path if path.is_absolute() else ROOT / path
    absolute = Path(absolute)
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        if current.is_symlink():
            raise ValueError(f"{label} traverses a symlink: {current}")


def _repo_path(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a nonempty repository-relative path")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"{label} must not escape the repository")
    joined = ROOT / path
    _reject_symlink_components(joined, label)
    resolved = joined.resolve()
    if resolved != ROOT and ROOT not in resolved.parents:
        raise ValueError(f"{label} resolves outside the repository")
    return resolved


def load_contract(
    contract_path: Path,
    *,
    stage: str | None = None,
    stage_root: Path | None = None,
    verify_inputs: bool = True,
) -> tuple[dict[str, Any], str]:
    """Load V21's single contract and enforce its immutable diagnostic roles."""

    raw_contract_path = Path(contract_path)
    _reject_symlink_components(raw_contract_path, "V21 diagnostic contract")
    expected_path = (ROOT / CONTRACT_REL).resolve()
    actual_path = raw_contract_path.resolve()
    if actual_path != expected_path:
        raise ValueError("V21 diagnostic accepts only the tracked R10_H67 contract")
    if not actual_path.is_file():
        raise FileNotFoundError("V21 diagnostic contract is missing or symlinked")
    raw = actual_path.read_bytes()
    contract_sha256 = hashlib.sha256(raw).hexdigest()
    contract = json.loads(raw)
    if not isinstance(contract, dict) or contract.get("schema") != SCHEMA:
        raise ValueError("V21 diagnostic contract schema is invalid")
    if contract.get("authorization_review") != "0dd5555f8795a68c7c9b1dc58387337d98fd76a5":
        raise ValueError("V21 contract is not bound to the authorized review")
    if "contract_sha256" in contract or "commit_sha" in contract or "head" in contract:
        raise ValueError("V21 rule contract must not contain self-referential run identity")
    if contract.get("artifact_prefix") != "benchmarks/artifacts/task43/v21_r10_h67":
        raise ValueError("V21 artifact prefix differs from its fixed namespace")
    if (
        contract.get("accepted_state") != "round9_p_up"
        or contract.get("diagnostic_parent_selection_status") != "REJECTED"
        or contract.get("candidate_id") != "v21_r10_h67"
        or contract.get("selection_enabled") is not False
        or contract.get("transition_written") is not False
    ):
        raise ValueError("V21 top-level state must preserve accepted9 and rejected R10")

    accepted = contract.get("accepted_parent")
    diagnostic = contract.get("diagnostic_parent")
    candidate = contract.get("candidate")
    physics = contract.get("physics")
    slots = contract.get("slots")
    inputs = contract.get("inputs")
    source_paths = contract.get("source_paths")
    tests = contract.get("tests")
    if not isinstance(accepted, Mapping) or not isinstance(diagnostic, Mapping):
        raise ValueError("V21 contract must keep accepted and diagnostic parents distinct")
    if (
        accepted.get("candidate_id") != "round9_p_up"
        or accepted.get("selection_status") != "ACCEPTED"
        or diagnostic.get("candidate_id") != "round10_p_up"
        or diagnostic.get("selection_status") != "REJECTED"
    ):
        raise ValueError("V21 contract changes the frozen accepted9/R10 rejected roles")
    if not isinstance(candidate, Mapping) or (
        candidate.get("candidate_id") != "v21_r10_h67"
        or candidate.get("action") != "h_refine"
        or candidate.get("global_cell_id") != 67
        or candidate.get("forest_root") != 127
        or candidate.get("lower_nm") != [16.5, 10.0, 90.0]
        or candidate.get("upper_nm") != [33.5, 15.0, 120.0]
        or candidate.get("requested_splits") != 1
        or candidate.get("maximum_level") != 1
        or candidate.get("inherited_degree") != 6
        or candidate.get("selection_enabled") is not False
        or candidate.get("transition_written") is not False
    ):
        raise ValueError("V21 contract candidate differs from the single frozen H67 action")
    if not isinstance(physics, Mapping) or (
        physics.get("operator_quadrature") != 15
        or physics.get("incident_port_quadrature") != 28
        or physics.get("volume_absorption_quadrature") != 15
        or physics.get("modal_rectangle") != "R13"
        or physics.get("modal_count") != 612
        or physics.get("normal_correction_count") != 1
        or physics.get("extra_correction_count") != 0
        or physics.get("direct_factor_backend") != "mumps"
    ):
        raise ValueError("V21 contract changes the frozen quadrature, modal or solve controls")
    if not isinstance(inputs, Mapping) or set(inputs) != REQUIRED_INPUT_ROLES:
        raise ValueError("V21 contract input role inventory is incomplete or has extras")
    seen_inputs: set[str] = set()
    for role, item in inputs.items():
        if not isinstance(item, Mapping) or set(item) != {"path", "sha256"}:
            raise ValueError(f"V21 input {role} must bind exactly path and SHA256")
        path = _repo_path(item["path"], f"inputs.{role}.path")
        if item["path"] != EXPECTED_INPUT_PATHS[role]:
            raise ValueError(f"V21 input {role} does not use its fixed reviewed source path")
        if str(path) in seen_inputs:
            raise ValueError("V21 contract reuses one input path under multiple roles")
        seen_inputs.add(str(path))
        if not isinstance(item["sha256"], str) or len(item["sha256"]) != 64:
            raise ValueError(f"V21 input {role} has an invalid SHA256")
        if verify_inputs:
            if path.is_symlink() or not path.is_file():
                raise FileNotFoundError(f"V21 input {role} is missing or symlinked: {path}")
            if sha256_file(path) != item["sha256"]:
                raise ValueError(f"V21 input {role} bytes differ from the contract")
    role_links = (
        ("accepted_parent", "selection_input_role", "accepted9_selection"),
        ("accepted_parent", "plan_input_role", "accepted9_plan"),
        ("accepted_parent", "record_input_role", "accepted9_record"),
        ("accepted_parent", "storage_input_role", "accepted9_storage"),
        ("accepted_parent", "comparison_input_role", "accepted9_comparison"),
        ("diagnostic_parent", "plan_input_role", "r10_plan"),
        ("diagnostic_parent", "record_input_role", "r10_record"),
        ("diagnostic_parent", "storage_input_role", "r10_storage"),
        ("diagnostic_parent", "comparison_input_role", "r10_comparison"),
        ("diagnostic_parent", "rejection_input_role", "r10_rejection"),
    )
    for section_name, field, expected_role in role_links:
        section = accepted if section_name == "accepted_parent" else diagnostic
        role = section.get(field)
        if role != expected_role or role not in inputs:
            raise ValueError(f"V21 {section_name}.{field} must bind {expected_role}")
    if not isinstance(source_paths, list) or not source_paths:
        raise ValueError("V21 contract source_paths must be a nonempty list")
    if len(set(source_paths)) != len(source_paths):
        raise ValueError("V21 contract repeats source paths")
    for source in source_paths:
        _repo_path(source, "source_paths item")
    if not isinstance(slots, Mapping) or set(slots) != set(EXPECTED_SLOT_ROOTS):
        raise ValueError("V21 slot inventory differs from the reviewed finite workflow")
    for name, relative_root in EXPECTED_SLOT_ROOTS.items():
        slot = slots[name]
        expected_work, expected_whole, expected_rss = EXPECTED_SLOT_LIMITS[name]
        if (
            not isinstance(slot, Mapping)
            or slot.get("root") != relative_root
            or slot.get("work_seconds") != expected_work
            or slot.get("whole_seconds") != expected_whole
            or slot.get("rss_limit_bytes") != expected_rss
        ):
            raise ValueError(f"V21 slot {name} root differs from its unique reviewed root")
    if not isinstance(tests, Mapping) or not isinstance(tests.get("selectors"), list):
        raise ValueError("V21 contract lacks its frozen targeted selector list")
    if (
        not tests["selectors"]
        or any(not isinstance(value, str) or "::" not in value for value in tests["selectors"])
        or len(tests["selectors"]) > 20
        or len(set(tests["selectors"])) != len(tests["selectors"])
    ):
        raise ValueError("V21 T1 selector inventory exceeds or repeats the reviewed limit")

    if stage is not None:
        if stage not in EXPECTED_SLOT_ROOTS:
            raise ValueError(f"unsupported V21 stage {stage!r}")
        if stage_root is None:
            raise ValueError("V21 stage requires its explicit unique root")
        expected_root = (ROOT / contract["artifact_prefix"] / slots[stage]["root"]).resolve()
        raw_stage_root = Path(stage_root)
        _reject_symlink_components(raw_stage_root, "V21 stage root")
        actual_root = raw_stage_root.resolve()
        if actual_root != expected_root:
            raise ValueError("V21 stage root differs from its unique contract root")
    return contract, contract_sha256


def source_snapshot(contract: Mapping[str, Any]) -> dict[str, str]:
    paths = set(contract["source_paths"])
    paths.add(str(CONTRACT_REL))
    return {
        relative: sha256_file(_repo_path(relative, "source path"))
        for relative in sorted(paths)
    }


def input_snapshot(contract: Mapping[str, Any]) -> dict[str, str]:
    return {
        role: sha256_file(_repo_path(item["path"], f"inputs.{role}.path"))
        for role, item in contract["inputs"].items()
    }


def slot_root(contract: Mapping[str, Any], stage: str) -> Path:
    if stage not in EXPECTED_SLOT_ROOTS:
        raise ValueError(f"unsupported V21 stage {stage!r}")
    return _repo_path(
        f"{contract['artifact_prefix']}/{contract['slots'][stage]['root']}",
        f"slots.{stage}.root",
    )


def require_snapshot_equal(
    contract: Mapping[str, Any],
    *,
    source_before: Mapping[str, str],
    input_before: Mapping[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    source_after = source_snapshot(contract)
    input_after = input_snapshot(contract)
    if dict(source_after) != dict(source_before):
        raise RuntimeError("V21 source bytes changed during the stage")
    if dict(input_after) != dict(input_before):
        raise RuntimeError("V21 frozen input bytes changed during the stage")
    for role, item in contract["inputs"].items():
        if input_after.get(role) != item["sha256"]:
            raise RuntimeError(f"V21 frozen input {role} changed from its contract hash")
    return source_after, input_after


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--stage", choices=("S", "F1", "F2", "C"), required=True)
    parser.add_argument("--stage-root", type=Path, required=True)
    args = parser.parse_args(argv)
    contract, _ = load_contract(
        args.contract, stage=args.stage, stage_root=args.stage_root
    )
    if args.stage == "S":
        from benchmarks.task43_hp_adaptivity.round1_candidates import main as plan_main

        return plan_main(
            [
                "--r10-h67-contract", str(args.contract),
                "--output-root", str(args.stage_root / "plan_output"),
            ]
        )
    if args.stage in {"F1", "F2"}:
        from benchmarks.task43_hp_adaptivity.h100_anchor import main as solve_main

        plan = slot_root(contract, "S") / "plan_output/plans/v21_r10_h67.json"
        return solve_main(
            [
                "--case", "round1_candidate_mpi1",
                "--run-root", str(args.stage_root / "run"),
                "--candidate-plan", str(plan),
                "--candidate-id", "v21_r10_h67",
                "--candidate-acceptance-contract",
                str(_repo_path(
                    contract["inputs"]["round1_acceptance_contract"]["path"],
                    "inputs.round1_acceptance_contract.path",
                )),
                "--v21-r10-h67-contract", str(args.contract),
                "--v21-r10-h67-stage", args.stage,
                "--same-lu-solve-residual-correction",
                "--direct-factor-backend", "mumps",
            ]
        )
    from benchmarks.task43_hp_adaptivity.compare_round1_candidate import main as compare_main

    formal_root = slot_root(contract, "F1") / "run"
    return compare_main(
        [
            "--candidate-run-root", str(formal_root),
            "--attempt-id", "v21_r10_h67_comparison_attempt1",
            "--v21-r10-h67-contract", str(args.contract),
            "--output-root", str(args.stage_root / "comparison"),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
