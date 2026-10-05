"""Review V25 §8 opt-in provenance; never extend the historical ledger list."""

import hashlib
import json
from pathlib import Path
import subprocess

ANCHOR_PATH = "docs/task40extra_0p7nm_engineering/outcomes/records/review_v8_w1_identity_audit_v1.json"
ANCHOR_SHA = "03b5c44136f132d203237211ea1499faec1c25d3c1f47225e0c662d00aca4ea0"
SOURCE_INPUT = (
    "input/task40extra_0p7nm_engineering/nonseparable_gx784_p6_q4_review_v5.dat"
)
SOURCE_INPUT_SHA = "12f2e0dbed831f56c6e41133cdad292d0b70bea828087348ca8ede13142da422"


def canonical_sha(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode()
    ).hexdigest()


def anchor_bodies(document):
    if "target_physical_identity" in document:
        section = document["target_physical_identity"]
        return section["identity"], section["ordered_inventory_identity"]
    found = {"physical": [], "inventory": []}

    def visit(obj):
        if isinstance(obj, dict):
            for key, value in obj.items():
                if key == "target_mode_physical_identity" and isinstance(value, dict):
                    found["physical"].append(value)
                if (
                    key == "original_size_ordered_mode_inventory_identity"
                    and isinstance(value, dict)
                ):
                    found["inventory"].append(value)
                visit(value)
        elif isinstance(obj, list):
            for value in obj:
                visit(value)

    visit(document)
    if any(
        not values or any(v != values[0] for v in values) for values in found.values()
    ):
        raise ValueError("W1_FIXED_ANCHOR_BODIES_REQUIRED")
    return found["physical"][0], found["inventory"][0]


def validate_receipt(path, manifest_path, *, root, math_commit, expected):
    import importlib.util

    module_path = Path(__file__).with_name("w1_evidence.py")
    module_spec = importlib.util.spec_from_file_location(
        "_reproduced_evidence", module_path
    )
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    check_file = module.check_file

    path, root = Path(path), Path(root)
    value = json.loads(path.read_text())
    if (
        value.get("schema") != "w1-reproduced-input-receipt.v1"
        or value.get("status") != "BITWISE_REPRODUCED_INPUT"
        or value.get("historical_ledger_recovered") is not False
        or value.get("math_commit") != math_commit
        or value.get("generation_count") != 1
        or value.get("PDE_solved") is not False
        or not value.get("generated_utc")
        or not isinstance(value.get("receiver_source_sha"), str)
        or len(value["receiver_source_sha"]) != 40
    ):
        raise ValueError("W1_REPRODUCED_SOURCE_SCHEMA")
    parent = root / "benchmarks/artifacts/task42extra/w1_receiver"
    manifest = check_file(value["manifest"], parent)
    if manifest.resolve() != Path(manifest_path).resolve():
        raise ValueError("W1_REPRODUCED_MANIFEST_PATH")
    binding = json.loads(check_file(value["binding"], parent).read_text())
    summary = json.loads(check_file(value["supervision"], parent).read_text())
    candidate = json.loads(check_file(value["candidate"], parent).read_text())
    if (
        summary.get("classification") != "COMPLETED"
        or summary.get("leader_exit_code") != 0
        or summary.get("descendants_cleared") is not True
        or summary.get("remaining_child_pids") != []
        or summary.get("sampled_process_tree_swap_peak_bytes") != 0
        or summary.get("rss_hard_limit_bytes") != 2 * 2**30
        or binding.get("stage") != "input_recovery"
        or binding.get("receiver_source_sha") != value["receiver_source_sha"]
        or candidate.get("status") != "BITWISE_REPRODUCED_INPUT_PENDING_RECEIPT"
        or candidate.get("generation_count") != 1
    ):
        raise ValueError("W1_REPRODUCED_CLEARED_SUPERVISION")
    anchor = subprocess.check_output(
        ["git", "show", math_commit + ":" + ANCHOR_PATH], cwd=root
    )
    if len(anchor) != 16783 or hashlib.sha256(anchor).hexdigest() != ANCHOR_SHA:
        raise ValueError("W1_FIXED_GIT_ANCHOR_BYTES")
    physical, inventory = anchor_bodies(json.loads(anchor))
    if (
        canonical_sha(physical) != expected["physical"]
        or canonical_sha(inventory) != expected["inventory"]
        or value.get("target_mode_physical_identity") != physical
        or value.get("original_size_ordered_mode_inventory_identity") != inventory
        or candidate.get("target_mode_physical_identity") != physical
        or candidate.get("original_size_ordered_mode_inventory_identity") != inventory
    ):
        raise ValueError("W1_REPRODUCED_FULL_IDENTITY_BODY")
    for row in value["git_sources"]:
        raw = subprocess.check_output(
            ["git", "show", math_commit + ":" + row["path"]], cwd=root
        )
        if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != row["sha256"]:
            raise ValueError("W1_REPRODUCED_GIT_SOURCE")
    required = {
        SOURCE_INPUT,
        ANCHOR_PATH,
        "src/common/modes_3d.py",
        "src/solvers/fullspace_dtn_action.py",
        "src/solvers/dtn_port_3d.py",
        "benchmarks/run_task40_v5_target_ledger.py",
    }
    if not required <= {r["path"] for r in value["git_sources"]}:
        raise ValueError("W1_REPRODUCED_REQUIRED_GIT_SOURCES")
    if value["manifest"]["sha256"] != expected["manifest"] or value["manifest"][
        "bytes"
    ] != expected.get("bytes", 36244923):
        raise ValueError("W1_REPRODUCED_EXACT_MANIFEST")
    return value
