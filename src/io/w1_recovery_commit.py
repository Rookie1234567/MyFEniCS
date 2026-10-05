"""Finish a cleared, correct R candidate without ever calling its generator."""

import json
import os
from pathlib import Path

from src.io.finite_json import atomic_json
from src.io.w1_evidence import file_receipt, seal_stage
from src.io.w1_receiver_contract import MATH_COMMIT, digest, validate_originals


def commit_recovery(run, spec, window, receiver_result):
    run = Path(run)
    summary = json.loads((run / "supervisor_summary.json").read_text())
    candidate = json.loads((run / "recovery_candidate.json").read_text())
    if (
        candidate.get("status") != "BITWISE_REPRODUCED_INPUT_PENDING_RECEIPT"
        or summary.get("classification") != "COMPLETED"
        or summary.get("leader_exit_code") != 0
        or not summary.get("descendants_cleared")
        or summary.get("remaining_child_pids") != []
        or summary.get("sampled_process_tree_swap_peak_bytes") != 0
    ):
        raise ValueError("W1_R_CLEARED_CORRECT_CANDIDATE_REQUIRED")
    marker = Path(
        window.get(
            "input_binding_file",
            Path(spec["window_path"]).parent / "P0_R_B_inputs.json",
        )
    )
    if marker.exists() or Path(spec["ledger_path"]).exists():
        raise ValueError("W1_R_FINAL_INPUT_ALREADY_FROZEN")
    component = json.loads((run / "component_result.json").read_text())
    component["status"] = "BITWISE_REPRODUCED_INPUT"
    atomic_json(run / "component_result.json", component)
    # Seal all actual artifacts and check all fixed Git blobs BEFORE publishing.
    atomic_json(run / "evidence.json", seal_stage(run))
    receiver_result["component_status"] = component["status"]
    receiver_result["evidence_sha256"] = digest(run / "evidence.json")
    atomic_json(run / "receiver_result.json", receiver_result)
    receipt = {
        **component,
        "schema": "w1-reproduced-input-receipt.v2",
        "math_commit": MATH_COMMIT,
        "binding": file_receipt(run / "binding.json"),
        "supervision": file_receipt(run / "supervisor_summary.json"),
        "candidate": file_receipt(run / "recovery_candidate.json"),
        "sealed_evidence": file_receipt(run / "evidence.json"),
        "receiver_result": file_receipt(run / "receiver_result.json"),
    }
    partial = Path(spec["ledger_path"]).with_suffix(".partial.json")
    atomic_json(partial, receipt)
    # The real consumer checks the sealed candidate, not just a PASS dictionary.
    validate_originals({**spec, "ledger_path": str(partial)})
    os.replace(partial, spec["ledger_path"])
    fd = os.open(Path(spec["ledger_path"]).parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    reproduced = validate_originals(spec)
    atomic_json(
        marker,
        {
            "window_sha256": digest(spec["window_path"]),
            "original_inputs": reproduced,
            "A_qualification_sha256": digest(spec["A_qualification_path"]),
            "recovery_evidence_sha256": digest(run / "evidence.json"),
        },
    )
    return receiver_result
