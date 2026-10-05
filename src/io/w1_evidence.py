"""Hash-bound W1 prerequisite receipts: completed supervision is mandatory."""

import hashlib
import json
import math
from pathlib import Path
import subprocess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def file_receipt(path):
    path = Path(path).resolve()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}


def check_file(row, parent):
    original = Path(row["path"])
    path = original.resolve()
    if not path.is_relative_to(Path(parent).resolve()) or original.is_symlink():
        raise ValueError("W1_EVIDENCE_PATH_SCOPE")
    if (
        not path.is_file()
        or path.stat().st_size != row["bytes"]
        or sha(path) != row["sha256"]
    ):
        raise ValueError("W1_EVIDENCE_BYTES_HASH")
    return path


def scientific_identity(binding):
    original = binding["original_inputs"]
    return {
        "contract": {
            k: v
            for k, v in binding["contract"].items()
            if k not in ("input_sha256", "output_root")
        },
        "original_inputs": original,
        "receiver_files": binding["receiver_files"],
        "math_source_sha": binding["math_source_sha"],
        "source_manifest_sha256": binding["source_manifest_sha256"],
        "window_sha256": binding["window_sha256"],
    }


def seal_stage(run):
    run = Path(run)
    binding = json.loads((run / "binding.json").read_text())
    result = json.loads((run / "component_result.json").read_text())
    # Every raw/oracle receipt published by the worker/checker is sealed.
    files = {}
    git_sources = []

    def collect(value, field=None):
        if isinstance(value, dict):
            if {"path", "bytes", "sha256"} <= set(value):
                path = check_file(
                    value, Path(binding["contract"]["output_root"]).parent
                )
                files[str(path)] = value
            for key, child in value.items():
                collect(child, key)
        elif isinstance(value, list):
            for child in value:
                if field == "git_sources":
                    check_git_blob(child, binding["math_source_sha"])
                    git_sources.append(child)
                else:
                    collect(child)

    collect(result)
    return {
        "schema": "w1-stage-evidence.v2",
        "stage": binding["stage"],
        "input_sha256": binding["contract"]["input_sha256"],
        "scientific_identity": scientific_identity(binding),
        "binding": file_receipt(run / "binding.json"),
        "component": file_receipt(run / "component_result.json"),
        "supervision": file_receipt(run / "supervisor_summary.json"),
        "raw_files": list(files.values()),
        "git_sources": git_sources,
    }


def check_git_blob(row, commit):
    """Git identities never pass through the filesystem artifact validator."""
    if row.get("kind") != "git_blob" or row.get("commit") != commit:
        raise ValueError("W1_GIT_BLOB_TYPED_IDENTITY")
    root = Path(__file__).resolve().parents[2]
    raw = subprocess.check_output(["git", "show", commit + ":" + row["path"]], cwd=root)
    if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
        raise ValueError("W1_GIT_BLOB_BYTES_HASH")


def validate_stage(run, *, identity, statuses, expected_stage=None):
    run = Path(run)
    receipt = json.loads((run / "evidence.json").read_text())
    if (
        receipt.get("schema") != "w1-stage-evidence.v2"
        or receipt.get("scientific_identity") != identity
    ):
        raise ValueError("W1_PREREQUISITE_SCIENTIFIC_IDENTITY")
    paths = {
        name: check_file(receipt[name], run)
        for name in ("binding", "component", "supervision")
    }
    binding, component, summary = [
        json.loads(paths[k].read_text())
        for k in ("binding", "component", "supervision")
    ]
    receiver = json.loads((run / "receiver_result.json").read_text())
    if (
        summary.get("classification") != "COMPLETED"
        or summary.get("leader_exit_code") != 0
        or summary.get("descendants_cleared") is not True
        or summary.get("remaining_child_pids") != []
        or summary.get("sampled_process_tree_swap_peak_bytes") != 0
        or receiver.get("receiver_classification") != "COMPLETED"
        or receiver.get("receiver_exit_code") != 0
        or receiver.get("cleared") is not True
        or receiver.get("worker_started") is not True
        or receiver.get("evidence_sha256") != sha(run / "evidence.json")
        or receiver.get("binding_sha256") != sha(paths["binding"])
    ):
        raise ValueError("W1_PREREQUISITE_SUCCESSFUL_CLEARED_SUPERVISION")
    if (
        scientific_identity(binding) != identity
        or not isinstance(binding.get("receiver_source_sha"), str)
        or len(binding["receiver_source_sha"]) != 40
        or any(c not in "0123456789abcdef" for c in binding["receiver_source_sha"])
        or binding["stage"] != receipt["stage"]
        or (expected_stage is not None and binding["stage"] != expected_stage)
        or binding["contract"]["input_sha256"] != receipt["input_sha256"]
        or sha(binding["spec"]["path"]) != receipt["input_sha256"]
        or component.get("binding_sha256") != sha(paths["binding"])
        or component.get("status") not in statuses
        or component.get("receiver_source_sha") != binding.get("receiver_source_sha")
        or receiver.get("receiver_source_sha") != binding.get("receiver_source_sha")
    ):
        raise ValueError("W1_PREREQUISITE_STAGE_RESULT_BINDING")
    for file in receipt["raw_files"]:
        check_file(file, Path(binding["contract"]["output_root"]).parent)
    for row in receipt.get("git_sources", []):
        check_git_blob(row, binding["math_source_sha"])
    if not receipt["raw_files"]:
        raise ValueError("W1_PREREQUISITE_RAW_EVIDENCE_REQUIRED")
    return component


def validate_P1_summary(component):
    """Check saved numeric gate fields too; never authorize from a PASS tag."""
    if (
        component.get("coverage") != {"4": 32060, "6": 32060}
        or component.get("coverage_complete") is not True
        or component.get("failed_mode_count") != 0
        or component.get("physical_incident_rhs_qualified") is not True
        or component.get("coordinate_physics_qualified") is not True
    ):
        raise ValueError("W1_P1_FULL_NUMERIC_COVERAGE_REQUIRED")
    value = component.get("maximum_original_relative", math.inf)
    if not math.isfinite(value) or value > 1e-10:
        raise ValueError("W1_P1_NUMERIC_MODE_GATE")
    actions = component.get("actual_action_RHS_adjoint_metrics", {})
    incident = component.get("physical_incident_metrics", [])
    oracle = component.get("oracle_numeric_recomputed", [])
    if (
        set(actions) != {"4", "6"}
        or any(not row for row in actions.values())
        or len(incident) != 2
        or any(not row for row in incident)
        or len(oracle) != 2
    ):
        raise ValueError("W1_P1_NUMERIC_EVIDENCE_MISSING")
    for row in list(actions.values()) + incident:
        if any(
            not math.isfinite(m["relative"]) or m["relative"] > 1e-10
            for m in row.values()
        ):
            raise ValueError("W1_P1_ACTUAL_ACTION_RHS_GATE")
    if any(
        g["checks"] < 1
        or not math.isfinite(g["maximum_absolute"])
        or g["maximum_absolute"] > 1e-12
        for g in oracle
    ):
        raise ValueError("W1_P1_ORACLE_NUMERIC_GATE")


def validate_A(path, receiver_files):
    import xml.etree.ElementTree as ET

    path = Path(path)
    value = json.loads(path.read_text())
    if value.get("schema") in {
        "w1-RB-delta-qualification.v1",
        "w1-P0-delta-qualification.v27",
    }:
        if (
            value.get("scope") != "PURE_LOGIC_DELTA_ONLY"
            or value.get("receiver_files") != receiver_files
        ):
            raise ValueError("W1_RB_DELTA_SOURCE")
        inherited_parent = (
            Path(__file__).resolve().parents[2] / "tmp/task42extra/w1_receiver/v26"
            if value["schema"] == "w1-P0-delta-qualification.v27"
            else path.parent
        )
        inherited_path = check_file(value["inherited_A"], inherited_parent)
        inherited = json.loads(inherited_path.read_text())
        if inherited.get("schema") != "w1-A-qualification.v1":
            raise ValueError("W1_RB_INHERITED_ORIGINAL_A_REQUIRED")
        validate_A(inherited_path, inherited["receiver_files"])
        changed = {
            k: v
            for k, v in receiver_files.items()
            if inherited["receiver_files"].get(k) != v
        }
        if value.get("changed_receiver_files") != changed:
            raise ValueError("W1_RB_DELTA_COVERAGE")
        parent = path.parent
        summary = json.loads(check_file(value["supervision"], parent).read_text())
        junit = ET.parse(check_file(value["junit"], parent)).getroot()
        if (
            summary.get("classification") != "COMPLETED"
            or summary.get("leader_exit_code") != 0
            or summary.get("descendants_cleared") is not True
            or summary.get("remaining_child_pids") != []
            or summary.get("sampled_process_tree_swap_peak_bytes") != 0
            or summary.get("rss_hard_limit_bytes") != 2 * 2**30
        ):
            raise ValueError("W1_RB_DELTA_SUPERVISION")
        tests = list(junit.iter("testcase"))
        required = {
            "test_recovery_origin_disjoint_from_legacy",
            "test_reproduced_receipt_rejects_false_supervision",
            "test_reproduced_receipt_rejects_identity_and_source",
            "test_RB_window_does_not_reset",
            "test_complete_frequency_coverage",
            "test_recovery_pending_cannot_start_B",
        }
        if value["schema"] == "w1-P0-delta-qualification.v27":
            required |= {
                "test_current_scope_preserves_protection",
                "test_scope_identity_and_cpuset_reject",
                "test_actual_R_writer_seal_reopen_consumer",
                "test_R_seal_failure_never_publishes_inputs",
                "test_P0_and_R_clocks_are_separate",
            }
        if not required <= {t.get("name", "").split("[")[0] for t in tests} or any(
            list(t.iter("failure")) or list(t.iter("error")) or list(t.iter("skipped"))
            for t in tests
        ):
            raise ValueError("W1_RB_DELTA_REQUIRED_TESTS")
        for row in value["test_source_files"]:
            check_file(row, Path(__file__).resolve().parents[2])
        return value
    if (
        value.get("schema") != "w1-A-qualification.v1"
        or value.get("scope") != "PURE_LOGIC_ONLY"
        or value.get("receiver_files") != receiver_files
    ):
        raise ValueError("W1_A_TESTED_SOURCE_QUALIFICATION_REQUIRED")
    parent = path.parent
    summary = json.loads(check_file(value["supervision"], parent).read_text())
    junit = ET.parse(check_file(value["junit"], parent)).getroot()
    if (
        summary.get("classification") != "COMPLETED"
        or summary.get("leader_exit_code") != 0
        or summary.get("descendants_cleared") is not True
        or summary.get("remaining_child_pids") != []
        or summary.get("sampled_process_tree_swap_peak_bytes") != 0
        or summary.get("rss_hard_limit_bytes") != 2 * 2**30
        or summary.get("sampled_process_tree_rss_peak_bytes", 2**63) > 2 * 2**30
    ):
        raise ValueError("W1_A_CLEARED_QUALIFICATION_REQUIRED")
    tests = list(junit.iter("testcase"))
    if not tests or any(
        list(t.iter("failure")) or list(t.iter("error")) or list(t.iter("skipped"))
        for t in tests
    ):
        raise ValueError("W1_A_TARGETED_TESTS_FAILED")
    required = {
        "test_actual_checker_writer_reopen_prerequisite",
        "test_updated_hash_broken_consumer_rejected",
        "test_failed_supervision_pass_tag_refused",
        "test_oracle_numeric_damage_not_tag",
        "test_coordinate_sign_origin_and_incident_rhs",
        "test_numpy_scalar_writer_and_nonfinite_rollback",
        "test_export_patch_reuses_original_solves",
        "test_B_window_and_control_budget",
    }
    if not required <= {t.get("name", "").split("[")[0] for t in tests}:
        raise ValueError("W1_A_REQUIRED_COUNTEREXAMPLES_NOT_TESTED")
    if not value.get("test_source_files"):
        raise ValueError("W1_A_BOUND_TEST_SOURCE_REQUIRED")
    for row in value["test_source_files"]:
        check_file(row, Path(__file__).resolve().parents[2])
    return value
