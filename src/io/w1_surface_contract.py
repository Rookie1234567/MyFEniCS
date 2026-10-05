"""Fixed full-surface opt-in; the V28 input instance and schema1 stay unchanged."""

import json
from pathlib import Path
import xml.etree.ElementTree as ET

SURFACE_STAGES = {
    "input_contract_checks",
    "surface_p4",
    "surface_p6",
    "surface_check",
    "surface_handoff",
}
EXTRA_FIELDS = {
    "surface_scope",
    "degree",
    "generic_seed",
    "seam_seed",
    "v28_reference_root",
}


def is_surface(spec):
    return spec.get("component") == "original_size_full_surface_w1"


def validate_surface_fields(value):
    stage = value.get("stage")
    expected_degree = {"surface_p4": 4, "surface_p6": 6}.get(stage, 0)
    if (
        stage not in SURFACE_STAGES
        or value.get("surface_scope") != "original_2176_facets"
        or type(value.get("degree")) is not int
        or value["degree"] != expected_degree
        or value.get("generic_seed") != 4212801
        or value.get("seam_seed") != 4212901
        or value.get("integration_profile") != "q60_native"
    ):
        raise ValueError("W29_FIXED_FULL_SURFACE_SCOPE_SEEDS_DEGREE")


def validate_qualification(path, files):
    from src.io.w1_evidence import check_file

    root = Path(__file__).resolve().parents[2]
    value = json.loads(Path(path).read_text())
    if (
        value.get("schema") != "w1-P0-delta-qualification.v29"
        or value.get("receiver_files") != files
        or value.get("scope") != "PURE_FULL_SURFACE_STARTUP_DELTA"
    ):
        raise ValueError("W29_QUALIFIED_EXACT_SOURCE_REQUIRED")
    summary = json.loads(check_file(value["supervision"], root).read_text())
    if (
        summary.get("classification") != "COMPLETED"
        or summary.get("leader_exit_code") != 0
        or summary.get("descendants_cleared") is not True
        or summary.get("remaining_child_pids") != []
        or summary.get("sampled_process_tree_swap_peak_bytes") != 0
        or summary.get("rss_hard_limit_bytes") != 2 * 2**30
    ):
        raise ValueError("W29_P0_SUCCESSFUL_CLEARED_LIGHT_SUPERVISION")
    freshness = json.loads(check_file(value["startup_freshness"], root).read_text())
    if (
        freshness.get("passed") is not True
        or not 0 <= freshness.get("age_seconds", 16) <= 15
    ):
        raise ValueError("W29_P0_FRESH_START_PROOF_REQUIRED")
    tests = list(ET.parse(check_file(value["junit"], root)).getroot().iter("testcase"))
    required = {
        "test_start_freshness_and_identity",
        "test_last_grant_read_new_25_rejected",
        "test_full_surface_contract_is_opt_in",
        "test_real_api_adapter_all_facets",
        "test_saved_array_damage_is_rejected",
        "test_periodic_geometry_mapping",
    }
    names = {t.get("name", "").split("[")[0] for t in tests}
    if not required <= names or any(list(t) for t in tests):
        raise ValueError("W29_P0_REQUIRED_TARGETED_GATES")
    for row in value["test_source_files"]:
        check_file(row, root)
    return value
