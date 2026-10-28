"""Read-only response decomposition for the already saved R9/R10/Y6_1 fields.

This V20 diagnostic only reads the frozen JSON/CSV sources and the allowlisted
members in the two saved common-sample NPZ files.  It does not restore a FE
field, build a mesh, assemble or apply an operator, sample a field, or solve a
PDE.  The implementation reuses V19's small numerical and serialization
helpers while keeping this round's file identities and data allowlist local.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, BinaryIO

import numpy as np

from benchmarks.task43_hp_adaptivity import analyze_saved_hp_response as v19


REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_RELATIVE_PATH = Path(
    "docs/task43_hp_adaptivity/outcomes/records/v20_saved_r10_response_contract.json"
)
CONTRACT_SCHEMA = "task43.v20.saved_r10_response_contract.v1"
INPUT_LOCK_SCHEMA = "task43.v20.static_input_lock.v1"
INPUT_LOCK_ROLE = "input_lock"
EXPECTED_REVIEW = "0c6158cb96b3ba320d5bd3282a3c18f64c5a08c9"
EXPECTED_SOURCE_ROLES = frozenset({
    "r9_absorption", "r9_modal", "r9_plan", "y6_modal", "y6_summary",
    "r10_rejection", "r10_comparison", "r10_modal", "r10_plan",
    "r10_absorption", "r9_comparison", "post_selection_metadata",
    "v19_q8_cells", "v19_q10_cells",
})
ALLOWED_ARRAYS = frozenset({
    "points_nm", "weights_nm3",
    "round9_p_up_E", "round9_p_up_curl_E",
    "round10_p_up_E", "round10_p_up_curl_E",
    "Y6_1_E", "Y6_1_curl_E",
})
FORBIDDEN_ARRAYS = frozenset({
    "Y5_1_E", "Y5_1_curl_E", "Y3_E", "Y3_curl_E", "Y3_2_E", "Y3_2_curl_E",
})
ARCHIVE_MEMBERS = ALLOWED_ARRAYS | FORBIDDEN_ARRAYS
FIELD_MEMBERS = (
    "round9_p_up_E", "round9_p_up_curl_E",
    "round10_p_up_E", "round10_p_up_curl_E",
    "Y6_1_E", "Y6_1_curl_E",
)
EXPECTED_ROOTS = {
    "T1": "benchmarks/artifacts/task43/v20_saved_r10_response/support/targeted_attempt1",
    "T2": "benchmarks/artifacts/task43/v20_saved_r10_response/support/targeted_recovery1",
    "D1": "benchmarks/artifacts/task43/v20_saved_r10_response/support/decomposition_attempt1",
    "D2": "benchmarks/artifacts/task43/v20_saved_r10_response/support/decomposition_recovery1",
}
EXPECTED_SLOT = {
    "T1": (270, 300, "INITIAL_TARGETED"),
    "T2": (270, 300, "LOCATED_T1_BUG_ONLY"),
    "D1": (1140, 1200, "TARGETED_GATE_PASSED"),
    "D2": (1140, 1200, "LOCATED_D1_BUG_ONLY"),
}
EXPECTED_T1_SELECTORS = [
    "src/test/test_task43_saved_r10_response.py::test_contract_loader_and_static_bundle_bind_actual_sources",
    "src/test/test_task43_saved_r10_response.py::test_contract_rejects_duplicate_source_hash",
    "src/test/test_task43_saved_r10_response.py::test_contract_rejects_slot_and_launch_conflicts",
    "src/test/test_task43_saved_r10_response.py::test_npz_loader_reads_only_allowlisted_members",
    "src/test/test_task43_saved_r10_response.py::test_half_open_owner_mapping_and_weight_checks",
    "src/test/test_task43_saved_r10_response.py::test_owner_rejects_duplicate_hole_and_wrong_weight",
    "src/test/test_task43_saved_r10_response.py::test_cells_bind_geometry_not_plan_row_and_freeze_degree_counts",
    "src/test/test_task43_saved_r10_response.py::test_response_decomposition_identity_and_location_rule",
    "src/test/test_task43_saved_r10_response.py::test_modal_j_replay_reproduces_612_channel_anchor",
    "src/test/test_task43_saved_r10_response.py::test_main_microfixture_writes_q8_q10_and_terminal",
    "src/test/test_task43_saved_r10_response.py::test_main_mid_write_failure_preserves_q8_and_marks_incomplete",
    "src/test/test_task43_saved_r10_response.py::test_terminal_refuses_incomplete_order",
]
REPLAY_RTOL = v19.REPLAY_RTOL
REPLAY_ATOL = v19.REPLAY_ATOL
IDENTITY_REL_TOL = 1.0e-10
DOMAIN_VOLUME_NM3 = 350000.0
J_FIELD_SCALE = 1.0e-4
J_AMPLITUDE_TOL = v19.J_AMPLITUDE_TOLERANCE
J_CHANNEL_TOL = v19.J_CHANNEL_POWER_TOLERANCE
POWER_TOL = v19.J_POWER_TOLERANCES
REQUIRED_OUTPUTS = ("diagnostic", "cells_csv", "modes_612_csv")
BASE_CELL_FIELDS = (
    "global_cell_id", "forest_root", "lower_nm", "upper_nm", "r9_p", "r10_p",
    "raised", "region", "quadrature_order",
)
TERM_NAMES = ("B", "D", "X", "I", "B10", "I_independent", "identity_error")
COMPONENTS = ("E", "curl_over_k0", "G")


class EvidenceError(RuntimeError):
    """A frozen source, access, geometry, or arithmetic gate failed."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_file(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"expected JSON object at {path}")
    return value


def _relative_path(record: dict[str, Any], *, fixture: bool = False) -> Path:
    raw = Path(str(record.get("path", "")))
    if fixture:
        if not raw.is_absolute():
            raise EvidenceError("test-only fixture source paths must be absolute")
        return raw
    if raw.is_absolute() or ".." in raw.parts or not raw.parts:
        raise EvidenceError(f"source path must be repo-relative and contained: {raw}")
    return REPO_ROOT / raw


def _checked_file(record: dict[str, Any], *, fixture: bool = False) -> Path:
    path = _relative_path(record, fixture=fixture)
    if path.is_symlink() or not path.is_file():
        raise EvidenceError(f"missing, symlinked, or non-file frozen input: {path}")
    actual = _sha256_file(path)
    if actual != record.get("sha256"):
        raise EvidenceError(f"frozen input SHA256 mismatch: {path}")
    return path


def _same_json(left: Any, right: Any, label: str) -> None:
    if left != right:
        raise EvidenceError(f"frozen input-lock binding differs for {label}")


def _validate_contract(manifest: dict[str, Any], *, fixture: bool = False) -> None:
    """Validate one canonical contract; fixture mode is private to pytest."""
    if fixture:
        if manifest.get("schema") != "task43.v20.test_fixture.v1":
            raise EvidenceError("test-only contract marker is missing")
        if not {
            "r9_plan", "r10_plan", "r9_modal", "r10_modal", "y6_modal",
            "r9_absorption", "r10_absorption", "y6_summary",
            "r9_comparison", "r10_comparison",
        }.issubset(manifest.get("sources", {})):
            raise EvidenceError("test-only contract lacks actual reader inputs")
        if set(manifest.get("quadrature", {})) != {"q8", "q10"}:
            raise EvidenceError("test-only contract needs both order records")
        if not manifest.get("cells"):
            raise EvidenceError("test-only contract has no geometry cells")
        return

    if manifest.get("schema") != CONTRACT_SCHEMA or manifest.get("authorization_review") != EXPECTED_REVIEW:
        raise EvidenceError("unsupported V20 contract or review authorization")
    if set(manifest) != {
        "schema", "authorization_review", "sources", "quadrature", "cells", "physics",
        "anchors", "historical_V19", "epsilon_J", "epsilon_G", "delta_FE_historical",
        "forest_json_crosscheck", "slots", "launch_files", "tests", "input_lock", "scope",
    }:
        raise EvidenceError("V20 contract contains missing or conflicting top-level authority fields")
    if set(manifest.get("sources", {})) != EXPECTED_SOURCE_ROLES:
        raise EvidenceError("V20 source roles are not the exact frozen 14-file set")
    source_digests = [record.get("sha256") for record in manifest["sources"].values()]
    if any(not isinstance(value, str) or len(value) != 64 for value in source_digests):
        raise EvidenceError("source hash is missing or malformed")
    if len(set(source_digests)) != len(source_digests):
        raise EvidenceError("duplicate source hash is not allowed")

    lock_ref = manifest.get("input_lock")
    if not isinstance(lock_ref, dict):
        raise EvidenceError("contract lacks the static input lock")
    lock_path = _checked_file(lock_ref)
    lock = _json_file(lock_path)
    if lock.get("schema") != INPUT_LOCK_SCHEMA or lock.get("authorization_review") != EXPECTED_REVIEW:
        raise EvidenceError("static input lock schema or review identity differs")
    lock_path_record = lock_ref.get("path")
    if lock_path_record != "docs/task43_hp_adaptivity/outcomes/records/v20_saved_r10_response_sources/input_lock.json":
        raise EvidenceError("input-lock path is not the frozen V20 preparation record")
    for key in (
        "sources", "quadrature", "cells", "physics", "anchors", "historical_V19",
        "epsilon_J", "epsilon_G", "delta_FE_historical", "forest_json_crosscheck",
    ):
        _same_json(manifest.get(key), lock.get(key), key)

    quadrature = manifest.get("quadrature")
    if not isinstance(quadrature, dict) or set(quadrature) != {"q8", "q10"}:
        raise EvidenceError("quadrature must bind exactly q8 and q10")
    all_hashes = [*source_digests, str(lock_ref["sha256"])]
    for label, record in quadrature.items():
        order = int(label[1:])
        expected_path = (
            "benchmarks/artifacts/task43/round1_candidates/comparisons/"
            f"post_selection_joint_attempt1/post_selection_shared_{label}.npz"
        )
        if (record.get("path"), record.get("partition_boxes")) != (expected_path, 1008):
            raise EvidenceError(f"wrong frozen quadrature path or partition count for {label}")
        expected_count = 1008 * order ** 3
        if int(record.get("sample_count", -1)) != expected_count:
            raise EvidenceError(f"{label} point count differs from the frozen 1008-box rule")
        axes = record.get("axis_breakpoints_nm")
        if not isinstance(axes, list) or len(axes) != 3 or math.prod(len(x) - 1 for x in axes) != 1008:
            raise EvidenceError(f"{label} quadrature partition axes are malformed")
        for axis in axes:
            if len(axis) < 2 or any(float(b) <= float(a) for a, b in zip(axis, axis[1:])):
                raise EvidenceError(f"{label} quadrature axis is not strictly increasing")
        digest = record.get("sha256")
        if not isinstance(digest, str) or len(digest) != 64:
            raise EvidenceError(f"{label} outer SHA256 is malformed")
        all_hashes.append(digest)

    cells = manifest.get("cells")
    if not isinstance(cells, list) or len(cells) != 180:
        raise EvidenceError("V20 must bind exactly 180 original base cells")
    ids = [int(row["global_cell_id"]) for row in cells]
    roots = [int(row["forest_root"]) for row in cells]
    if ids != list(range(180)) or len(set(roots)) != 180:
        raise EvidenceError("frozen cells must have global IDs 0..179 and unique roots")
    raised = [row for row in cells if row.get("raised") is True]
    unchanged = [row for row in cells if row.get("raised") is False]
    if len(raised) != 28 or len(unchanged) != 152:
        raise EvidenceError("R9→R10 degree map must contain 28 raises and 152 p6 cells")
    if any((int(row["r9_p"]), int(row["r10_p"]), row["raised"]) != (5, 6, True) for row in raised):
        raise EvidenceError("raised-cell map is not p5→p6")
    if any((int(row["r9_p"]), int(row["r10_p"]), row["raised"]) != (6, 6, False) for row in unchanged):
        raise EvidenceError("unchanged-cell map is not p6→p6")
    by_id = {int(row["global_cell_id"]): row for row in cells}
    request, closure = by_id[8], by_id[14]
    if (request["forest_root"], request["lower"], request["upper"]) != (
        4, [16.5, 5.0, -10.0], [33.5, 10.0, 0.0]
    ):
        raise EvidenceError("global-8/root-4 frozen requested cell differs")
    if (closure["forest_root"], closure["lower"], closure["upper"]) != (
        34, [16.5, 5.0, 0.0], [33.5, 10.0, 30.0]
    ):
        raise EvidenceError("global-14/root-34 frozen closure cell differs")

    slots = manifest.get("slots")
    if not isinstance(slots, dict) or set(slots) != set(EXPECTED_SLOT):
        raise EvidenceError("V20 slots must be exactly T1/T2/D1/D2")
    slot_roots: list[str] = []
    for stage, (work, whole, condition) in EXPECTED_SLOT.items():
        slot = slots[stage]
        if set(slot) != {"root", "work_seconds", "whole_seconds", "condition"}:
            raise EvidenceError(f"slot {stage} has conflicting or repeated state fields")
        if (slot.get("root"), slot.get("work_seconds"), slot.get("whole_seconds"), slot.get("condition")) != (
            EXPECTED_ROOTS[stage], work, whole, condition
        ):
            raise EvidenceError(f"slot {stage} differs from its fixed path/condition/budget")
        slot_roots.append(str(slot["root"]))
    if len(set(slot_roots)) != 4:
        raise EvidenceError("V20 execution slots must have unique roots")

    tests = manifest.get("tests")
    if not isinstance(tests, dict) or set(tests) != {"selectors", "recovery_selectors", "d2_selectors"}:
        raise EvidenceError("V20 test selector state must be single-source and explicit")
    if tests.get("selectors") != EXPECTED_T1_SELECTORS or len(set(tests["selectors"])) != 12:
        raise EvidenceError("T1 selectors are not the exact 12-node frozen batch")
    allowed = set(EXPECTED_T1_SELECTORS)
    recovery = tests.get("recovery_selectors")
    d2 = tests.get("d2_selectors")
    if not isinstance(recovery, list) or len(recovery) > 12 or len(set(recovery)) != len(recovery):
        raise EvidenceError("recovery selectors must be a unique subset of the frozen T1 nodes")
    if not isinstance(d2, list) or len(d2) > 6 or len(set(d2)) != len(d2):
        raise EvidenceError("D2 selectors must be a unique subset of the frozen T1 nodes")
    if not set(recovery).issubset(allowed) or not set(d2).issubset(allowed):
        raise EvidenceError("recovery selectors may only reuse frozen T1 nodes")

    launch_files = manifest.get("launch_files")
    if not isinstance(launch_files, list) or len(launch_files) != 2:
        raise EvidenceError("contract must bind exactly the two V20 launch files")
    expected_launch_paths = {
        "benchmarks/artifacts/task43/v20_saved_r10_response/launch/snapshot.py",
        "benchmarks/artifacts/task43/v20_saved_r10_response/launch/stage_launch.sh",
    }
    found_paths: set[str] = set()
    for record in launch_files:
        path_text = record.get("path")
        copy_text = record.get("tracked_copy")
        if path_text not in expected_launch_paths or path_text in found_paths:
            raise EvidenceError("launch path inventory is not the exact two-file allowlist")
        found_paths.add(path_text)
        copy = Path(str(copy_text))
        if copy.is_absolute() or ".." in copy.parts:
            raise EvidenceError("tracked launch copy path escapes the repository")
        actual = _checked_file({"path": path_text, "sha256": record.get("sha256")})
        copied = _checked_file({"path": copy_text, "sha256": record.get("sha256")})
        if _sha256_file(actual) != _sha256_file(copied):
            raise EvidenceError(f"tracked launch copy is not byte-identical: {path_text}")
        all_hashes.append(str(record["sha256"]))
    if found_paths != expected_launch_paths or len(set(all_hashes)) != len(all_hashes):
        raise EvidenceError("duplicate or missing hash across the frozen input set")

    scope = manifest.get("scope", {})
    for key in ("new_PDE", "new_sampling", "field_restore", "new_background", "operator_application"):
        if scope.get(key) != 0:
            raise EvidenceError(f"V20 contract must freeze {key}=0")
    if scope.get("merge_allowed") is not False or scope.get("accepted_parent") != "R9":
        raise EvidenceError("V20 scope changes accepted-state or merge authority")


def _load_manifest(path: Path) -> tuple[dict[str, Any], str, dict[str, Any]]:
    if path.is_symlink() or not path.is_file():
        raise EvidenceError(f"manifest missing or symlinked: {path}")
    expected = REPO_ROOT / CONTRACT_RELATIVE_PATH
    if path.resolve(strict=True) != expected.resolve(strict=True):
        raise EvidenceError(f"V20 accepts only the fixed contract path: {expected}")
    manifest = _json_file(path)
    _validate_contract(manifest)
    lock_path = _checked_file(manifest["input_lock"])
    return manifest, _sha256_file(path), _json_file(lock_path)


def _geometry_key(lower: Any, upper: Any) -> tuple[float, ...]:
    if len(lower) != 3 or len(upper) != 3:
        raise EvidenceError("cell geometry bounds must have three coordinates")
    values = tuple(round(float(v), 12) for v in (*lower, *upper))
    if not all(math.isfinite(v) for v in values):
        raise EvidenceError("cell geometry contains nonfinite bounds")
    if any(values[i] >= values[i + 3] for i in range(3)):
        raise EvidenceError("cell geometry has nonpositive extent")
    return values


def _plan_geometry_map(plan: dict[str, Any], label: str) -> dict[tuple[float, ...], int]:
    rows = plan.get("cell_interior_degrees")
    if not isinstance(rows, list):
        raise EvidenceError(f"{label} plan lacks cell_interior_degrees")
    mapped: dict[tuple[float, ...], int] = {}
    for row in rows:
        if not isinstance(row, dict):
            raise EvidenceError(f"{label} plan contains malformed box")
        key = _geometry_key(row.get("lower", ()), row.get("upper", ()))
        if key in mapped:
            raise EvidenceError(f"{label} plan repeats a geometry box")
        degree = int(row.get("degree", -1))
        if degree < 1:
            raise EvidenceError(f"{label} plan contains an invalid polynomial degree")
        mapped[key] = degree
    return mapped


def _validate_plan_cells(
    cells: list[dict[str, Any]], r9_plan: dict[str, Any], r10_plan: dict[str, Any],
    *, fixture: bool = False,
) -> tuple[list[dict[str, Any]], dict[int, int], list[float]]:
    """Bind degrees by geometry, never by plan row index."""
    r9_map = _plan_geometry_map(r9_plan, "R9")
    r10_map = _plan_geometry_map(r10_plan, "R10")
    if len(r9_map) != len(cells) or len(r10_map) != len(cells):
        raise EvidenceError("R9/R10 plan boxes do not cover the frozen cells exactly")
    ids: set[int] = set()
    roots: set[int] = set()
    keys: set[tuple[float, ...]] = set()
    for cell in cells:
        gid, root = int(cell["global_cell_id"]), int(cell["forest_root"])
        key = _geometry_key(cell["lower"], cell["upper"])
        if gid in ids or root in roots or key in keys:
            raise EvidenceError("cell IDs, roots, and boxes must each be unique")
        ids.add(gid); roots.add(root); keys.add(key)
        p9, p10 = r9_map.get(key), r10_map.get(key)
        if p9 != int(cell["r9_p"]) or p10 != int(cell["r10_p"]):
            raise EvidenceError(f"global cell {gid} degree map disagrees with its geometric plan box")
        if bool(cell["raised"]) != (p10 > p9):
            raise EvidenceError(f"global cell {gid} raised flag disagrees with p map")
    if keys != set(r9_map) or keys != set(r10_map):
        raise EvidenceError("plan contains an extra or unbound geometry box")
    by_id = {int(row["global_cell_id"]): row for row in cells}
    if not fixture:
        if len(cells) != 180 or len(ids) != 180 or sorted(ids) != list(range(180)):
            raise EvidenceError("cell map must contain globals 0..179")
        if sum(bool(row["raised"]) for row in cells) != 28:
            raise EvidenceError("expected exactly 28 p5→p6 geometry-bound degree raises")
        if any(int(row["r10_p"]) != 6 for row in cells):
            raise EvidenceError("R10 must remain p6 in all 180 base cells")
        if (by_id[8]["forest_root"], by_id[8]["lower"], by_id[8]["upper"]) != (
            4, [16.5, 5.0, -10.0], [33.5, 10.0, 0.0]
        ):
            raise EvidenceError("global-8/root-4 requested geometry changed")
        if (by_id[14]["forest_root"], by_id[14]["lower"], by_id[14]["upper"]) != (
            34, [16.5, 5.0, 0.0], [33.5, 10.0, 30.0]
        ):
            raise EvidenceError("global-14/root-34 closure geometry changed")
    elif len(ids) != len(set(ids)):
        raise EvidenceError("fixture global cell IDs must be unique")
    z_edges = sorted({float(x) for row in cells for x in (row["lower"][2], row["upper"][2])})
    return sorted(cells, key=lambda row: int(row["global_cell_id"])), by_id, z_edges


def _csv_cell_geometry(path: Path) -> dict[int, tuple[float, ...]]:
    rows: dict[int, tuple[float, ...]] = {}
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.DictReader(stream)
            required = {"global_cell_id", "lower_nm", "upper_nm"}
            if not required.issubset(reader.fieldnames or []):
                raise EvidenceError(f"V19 cell CSV lacks geometry columns: {path}")
            for row in reader:
                gid = int(row["global_cell_id"])
                key = _geometry_key(json.loads(row["lower_nm"]), json.loads(row["upper_nm"]))
                if gid in rows:
                    raise EvidenceError(f"V19 cell CSV duplicates global cell {gid}")
                rows[gid] = key
    except (OSError, UnicodeError, csv.Error, ValueError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"cannot parse V19 geometry CSV {path}: {exc}") from exc
    return rows


def _verify_v19_geometry_sources(
    cells: list[dict[str, Any]], paths: dict[str, Path], historical: dict[str, Any],
) -> None:
    frozen = {int(row["global_cell_id"]): _geometry_key(row["lower"], row["upper"]) for row in cells}
    for role in ("v19_q8_cells", "v19_q10_cells"):
        if _csv_cell_geometry(paths[role]) != frozen:
            raise EvidenceError(f"{role} geometry/global map differs from the V20 frozen cells")
    with paths["v19_q10_cells"].open("r", encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        needed = {"global_cell_id", "P8.G.B", "H8.G.B"}
        if not needed.issubset(reader.fieldnames or []):
            raise EvidenceError("V19 q10 CSV lacks saved B9 ranking columns")
        rows = list(reader)
    p8_rank = sorted(rows, key=lambda row: (-float(row["P8.G.B"]), int(row["global_cell_id"])))
    h8_rank = sorted(rows, key=lambda row: (-float(row["H8.G.B"]), int(row["global_cell_id"])))
    expected = [int(x) for x in historical["top10_B9_globals"]]
    if [int(row["global_cell_id"]) for row in p8_rank[:10]] != expected:
        raise EvidenceError("V19 saved q10 P8 baseline top-10 cell map differs")
    if [int(row["global_cell_id"]) for row in h8_rank[:10]] != expected:
        raise EvidenceError("V19 saved q10 H8 baseline top-10 cell map differs")


def _source_paths(manifest: dict[str, Any], *, fixture: bool = False) -> dict[str, Path]:
    paths = {}
    for role, record in manifest["sources"].items():
        paths[role] = _checked_file(record, fixture=fixture)
    return paths


def _absorption(path: Path, *, reference: bool = False) -> float:
    value = _json_file(path)
    raw = (value.get("official_result", {}).get("volume_metrics", {}).get("A_volume_total")
           if reference else value.get("A_volume_total"))
    if not isinstance(raw, (int, float)) or not math.isfinite(float(raw)):
        raise EvidenceError(f"missing finite saved A_volume in {path}")
    return float(raw)


def _candidate_anchor(comparison: dict[str, Any], label: str) -> dict[str, Any]:
    if comparison.get("selection_reference") != "Y6_1":
        raise EvidenceError(f"{label} comparison reference is not Y6_1")
    field = comparison.get("field_metrics_vs_selection_reference", {}).get("candidate")
    jinfty = comparison.get("J_infinity", {}).get("candidate")
    modal = comparison.get("modal_and_power_metrics_vs_selection_reference", {}).get("candidate")
    if not all(isinstance(x, dict) for x in (field, jinfty, modal)):
        raise EvidenceError(f"{label} comparison lacks saved candidate anchors")
    return {"field_metrics": field, "J_infinity": jinfty, "modal_and_power_metrics": modal}


def _load_source_bundle(
    manifest: dict[str, Any], paths: dict[str, Path], lock: dict[str, Any] | None,
    *, fixture: bool = False,
) -> dict[str, Any]:
    roles = manifest["sources"]
    r9_plan = _json_file(paths["r9_plan"])
    r10_plan = _json_file(paths["r10_plan"])
    cells, by_id, z_edges = _validate_plan_cells(
        manifest["cells"], r9_plan, r10_plan, fixture=fixture
    )
    if not fixture:
        assert lock is not None
        _verify_v19_geometry_sources(cells, paths, manifest["historical_V19"])

    r9_comp = _json_file(paths["r9_comparison"])
    r10_comp = _json_file(paths["r10_comparison"])
    r9_anchor = _candidate_anchor(r9_comp, "R9")
    r10_anchor = _candidate_anchor(r10_comp, "R10")
    r10_parent = {
        "field_metrics": r10_comp.get("field_metrics_vs_selection_reference", {}).get("parent"),
        "J_infinity": r10_comp.get("J_infinity", {}).get("parent"),
        "modal_and_power_metrics": r10_comp.get("modal_and_power_metrics_vs_selection_reference", {}).get("parent"),
    }
    if r10_parent != r9_anchor:
        raise EvidenceError("R10 selection parent anchors are not byte-value identical to frozen R9 anchors")
    if not fixture:
        _same_json(manifest["anchors"]["R9"], r9_anchor, "R9 comparison anchor")
        _same_json(manifest["anchors"]["R10"], r10_anchor, "R10 comparison anchor")
    if r10_comp.get("parent_candidate_id") != r9_comp.get("candidate_id"):
        raise EvidenceError("R10 comparison parent is not the frozen R9 candidate")
    r9_modal = v19.modal_inventory(_json_file(paths["r9_modal"]).get("orders", []))
    r10_modal = v19.modal_inventory(_json_file(paths["r10_modal"]).get("orders", []))
    y6_modal = v19.modal_inventory(_json_file(paths["y6_modal"]).get("orders", []))
    if any(len(modal) != 612 for modal in (r9_modal, r10_modal, y6_modal)):
        raise EvidenceError("R9/R10/Y6_1 modal inventory must contain 612 channels")
    r9_abs = _absorption(paths["r9_absorption"])
    r10_abs = _absorption(paths["r10_absorption"])
    y6_abs = _absorption(paths["y6_summary"], reference=True)
    if not fixture:
        rejection = _json_file(paths["r10_rejection"])
        evidence = rejection.get("evidence", {})
        raw_ref = evidence.get("comparison_raw_record", {})
        modal_ref = evidence.get("PDE_modal_rows", {})
        if (raw_ref.get("path"), raw_ref.get("sha256")) != (
            roles["r10_comparison"]["path"], roles["r10_comparison"]["sha256"]
        ):
            raise EvidenceError("R10 rejection record does not bind the locked comparison")
        if (modal_ref.get("path"), modal_ref.get("sha256")) != (
            roles["r10_modal"]["path"], roles["r10_modal"]["sha256"]
        ):
            raise EvidenceError("R10 rejection record does not bind the locked modal rows")
        metadata = _json_file(paths["post_selection_metadata"])
        if metadata.get("selection_eligible") is not False:
            raise EvidenceError("post-selection history must remain ineligible")

    return {
        "paths": paths, "cells": cells, "by_id": by_id, "z_edges": z_edges,
        "plans": {"R9": r9_plan, "R10": r10_plan},
        "modal": {"R9": r9_modal, "R10": r10_modal, "Y6_1": y6_modal},
        "absorption": {"R9": r9_abs, "R10": r10_abs, "Y6_1": y6_abs},
        "anchors": {"R9": r9_anchor, "R10": r10_anchor},
    }


def _npy_header(stream: BinaryIO) -> tuple[tuple[int, ...], np.dtype[Any], bool]:
    try:
        version = np.lib.format.read_magic(stream)
        if version == (1, 0):
            shape, fortran_order, dtype = np.lib.format.read_array_header_1_0(stream)
        elif version == (2, 0):
            shape, fortran_order, dtype = np.lib.format.read_array_header_2_0(stream)
        else:
            raise EvidenceError(f"unsupported NPY header version {version}")
    except (ValueError, EOFError, OSError) as exc:
        raise EvidenceError(f"invalid allowlisted NPY header: {exc}") from exc
    return tuple(int(x) for x in shape), np.dtype(dtype), bool(fortran_order)


def _read_allowed_member(
    archive: zipfile.ZipFile, member: str, sample_count: int,
) -> tuple[np.ndarray, dict[str, Any]]:
    digest = hashlib.sha256()
    payload = bytearray()
    with archive.open(f"{member}.npy", "r") as stream:
        shape, dtype, fortran_order = _npy_header(stream)
        if fortran_order or dtype.hasobject:
            raise EvidenceError(f"forbidden Fortran/object array: {member}")
        expected_dtype = np.dtype("float64") if member in ("points_nm", "weights_nm3") else np.dtype("complex128")
        expected_shape = (sample_count, 3) if member == "points_nm" or member in FIELD_MEMBERS else (sample_count,)
        if dtype != expected_dtype or shape != expected_shape:
            raise EvidenceError(
                f"allowlisted member dtype/shape mismatch for {member}: {dtype.str} {shape}"
            )
        digest.update(dtype.str.encode("ascii"))
        digest.update(json.dumps(list(shape)).encode("ascii"))
        count = math.prod(shape)
        remaining = count * dtype.itemsize
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise EvidenceError(f"truncated allowlisted member {member}")
            payload.extend(chunk)
            digest.update(chunk)
            remaining -= len(chunk)
        if stream.read(1):
            raise EvidenceError(f"trailing bytes after allowlisted member {member}")
    array = np.frombuffer(bytes(payload), dtype=dtype).reshape(shape).copy()
    if not np.isfinite(array).all():
        raise EvidenceError(f"nonfinite data in allowlisted member {member}")
    array.flags.writeable = False
    return array, {
        "dtype": dtype.str, "shape": list(shape), "array_sha256": digest.hexdigest(),
        "finite": True, "read": True,
    }


def read_saved_archive(record: dict[str, Any], *, fixture: bool = False) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    """Open exact 14-name ZIP inventory; decompress only eight allowed members."""
    path = _checked_file(record, fixture=fixture)
    try:
        archive = zipfile.ZipFile(path, "r")
    except (OSError, zipfile.BadZipFile) as exc:
        raise EvidenceError(f"invalid saved NPZ archive {path}: {exc}") from exc
    with archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise EvidenceError("duplicate saved NPZ directory entry")
        expected = {f"{name}.npy" for name in ARCHIVE_MEMBERS}
        if set(names) != expected:
            raise EvidenceError(
                f"saved NPZ exact member inventory differs: missing={sorted(expected-set(names))}, "
                f"extra={sorted(set(names)-expected)}"
            )
        count = int(record["sample_count"])
        arrays: dict[str, np.ndarray] = {}
        metadata: dict[str, Any] = {
            "path": str(path), "outer_sha256": record["sha256"],
            "inventory": sorted(name.removesuffix(".npy") for name in names),
            "read_members": {}, "unread_control_members": sorted(FORBIDDEN_ARRAYS),
        }
        for name in sorted(ALLOWED_ARRAYS):
            arrays[name], metadata["read_members"][name] = _read_allowed_member(archive, name, count)
    if _sha256_file(path) != record["sha256"]:
        raise EvidenceError(f"saved NPZ changed while reading allowlisted arrays: {path}")
    return arrays, metadata


def _partition_owner(points: np.ndarray, edges: list[list[float]], order: int, expected_boxes: int) -> dict[str, Any]:
    if points.ndim != 2 or points.shape[1] != 3:
        raise EvidenceError("points_nm must be an N×3 array")
    indices = []
    counts_per_axis = [len(axis) - 1 for axis in edges]
    if math.prod(counts_per_axis) != expected_boxes:
        raise EvidenceError("quadrature axes do not describe the locked partition-box count")
    for dim, axis in enumerate(edges):
        limits = np.asarray(axis, dtype=np.float64)
        values = points[:, dim]
        if np.any(values < limits[0]) or np.any(values > limits[-1]):
            raise EvidenceError("quadrature point lies outside the locked integration domain")
        index = np.searchsorted(limits, values, side="right") - 1
        index = np.where(index == len(limits) - 1, len(limits) - 2, index)
        indices.append(index.astype(np.int64, copy=False))
    flat = (indices[0] * counts_per_axis[1] + indices[1]) * counts_per_axis[2] + indices[2]
    counts = np.bincount(flat, minlength=expected_boxes)
    if counts.size != expected_boxes or np.any(counts != order ** 3):
        raise EvidenceError("quadrature partition does not contain exactly q^3 points per box")
    boundary_hits = int(sum(np.count_nonzero(np.isin(points[:, i], edges[i][1:-1])) for i in range(3)))
    return {"box_indices": flat, "counts": counts, "boundary_coordinate_hits": boundary_hits,
            "points_per_box": order ** 3}


def map_points_to_cells(
    points: np.ndarray, weights: np.ndarray, cells: list[dict[str, Any]], *,
    expected_volume: float,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Map points to a rectilinear partition using half-open boxes."""
    if points.ndim != 2 or points.shape[1] != 3 or weights.shape != (points.shape[0],):
        raise EvidenceError("point/weight arrays have incompatible layout")
    if not np.isfinite(points).all() or not np.isfinite(weights).all() or np.any(weights <= 0):
        raise EvidenceError("quadrature points/weights must be finite and weights positive")
    keys = [_geometry_key(row["lower"], row["upper"]) for row in cells]
    if len(keys) != len(set(keys)):
        raise EvidenceError("duplicate cell box in owner partition")
    edges = [sorted({float(row[side][axis]) for row in cells for side in ("lower", "upper")}) for axis in range(3)]
    shape = tuple(len(axis) - 1 for axis in edges)
    if math.prod(shape) != len(cells):
        raise EvidenceError("cells do not form a complete nonoverlapping Cartesian partition")
    geom_to_gid: dict[tuple[int, int, int], int] = {}
    gid_to_row = {int(row["global_cell_id"]): i for i, row in enumerate(cells)}
    for row in cells:
        key = []
        for axis in range(3):
            lower, upper = float(row["lower"][axis]), float(row["upper"][axis])
            lo = int(np.searchsorted(edges[axis], lower))
            hi = int(np.searchsorted(edges[axis], upper))
            if hi != lo + 1:
                raise EvidenceError("cell box spans a missing or overlapping partition interval")
            key.append(lo)
        index = tuple(key)
        if index in geom_to_gid:
            raise EvidenceError("two cells own the same Cartesian geometry index")
        geom_to_gid[index] = int(row["global_cell_id"])
    if len(geom_to_gid) != len(cells) or set(gid_to_row) != {int(row["global_cell_id"]) for row in cells}:
        raise EvidenceError("global cell ownership is not one-to-one")
    coordinate_indices = []
    outer_hits = 0
    internal_hits = 0
    for axis_i, axis_edges in enumerate(edges):
        values = points[:, axis_i]
        if np.any(values < axis_edges[0]) or np.any(values > axis_edges[-1]):
            raise EvidenceError("quadrature point is outside the frozen cells")
        idx = np.searchsorted(axis_edges, values, side="right") - 1
        at_upper = idx == len(axis_edges) - 1
        outer_hits += int(np.count_nonzero(at_upper))
        idx = np.where(at_upper, len(axis_edges) - 2, idx)
        internal_hits += int(np.count_nonzero(np.isin(values, axis_edges[1:-1])))
        coordinate_indices.append(idx.astype(np.int64, copy=False))
    owner_gids = np.empty(points.shape[0], dtype=np.int64)
    for i in range(points.shape[0]):
        key = tuple(int(axis[i]) for axis in coordinate_indices)
        gid = geom_to_gid.get(key)
        if gid is None:
            raise EvidenceError(f"point {i} falls into an unowned half-open cell interval")
        owner_gids[i] = gid
    slots = np.asarray([gid_to_row[int(gid)] for gid in owner_gids], dtype=np.int64)
    per_cell_weight = np.bincount(slots, weights=weights, minlength=len(cells))
    if per_cell_weight.shape != (len(cells),) or np.any(per_cell_weight <= 0):
        raise EvidenceError("quadrature samples do not visit every frozen cell")
    for row_index, row in enumerate(cells):
        volume = math.prod(float(row["upper"][i]) - float(row["lower"][i]) for i in range(3))
        tolerance = max(1.0e-8, 1.0e-12 * volume)
        if abs(float(per_cell_weight[row_index]) - volume) > tolerance:
            raise EvidenceError(f"quadrature volume differs from box volume at global {row['global_cell_id']}")
    total = float(np.sum(weights, dtype=np.float64))
    if abs(total - expected_volume) > 1.0e-8:
        raise EvidenceError(f"quadrature total volume differs from frozen domain: {total}")
    return slots, {
        "global_cell_ids": [int(row["global_cell_id"]) for row in cells],
        "point_owner_global_ids": owner_gids, "cell_weight_nm3": per_cell_weight,
        "total_weight_nm3": total, "expected_volume_nm3": expected_volume,
        "internal_boundary_coordinate_hits": internal_hits,
        "outer_upper_boundary_coordinate_hits": outer_hits,
        "ownership_rule": "[lower, upper), global maximum included in last interval",
        "cell_grid_shape": list(shape),
    }


def _sum_terms(values: dict[str, np.ndarray]) -> dict[str, float]:
    return {name: float(np.sum(value, dtype=np.float64)) for name, value in values.items()}


def _group_cells(cells: list[dict[str, Any]]) -> dict[int, str]:
    groups = {}
    for row in cells:
        gid = int(row["global_cell_id"])
        if gid == 8 and int(row["forest_root"]) == 4:
            groups[gid] = "requested_root4_global8"
        elif gid == 14 and int(row["forest_root"]) == 34:
            groups[gid] = "H8_required_closure_root34"
        else:
            groups[gid] = "rest_of_domain"
    return groups


def _response_decomposition(
    arrays: dict[str, np.ndarray], weights: np.ndarray, slots: np.ndarray,
    cell_count: int, k0: float,
) -> dict[str, Any]:
    """Use V19's tested production accumulator for each response component."""
    y_e, y_curl = arrays["Y6_1_E"], arrays["Y6_1_curl_E"]
    r9_e, r9_curl = arrays["round9_p_up_E"], arrays["round9_p_up_curl_E"]
    response_error = {
        "E": y_e - r9_e,
        "curl_over_k0": (y_curl - r9_curl) / k0,
    }
    cases: dict[str, Any] = {}
    for name, prefix in (("R9", "round9_p_up"), ("R10", "round10_p_up")):
        action_e = arrays[f"{prefix}_E"]
        action_curl = arrays[f"{prefix}_curl_E"]
        action_delta = {
            "E": action_e - r9_e,
            "curl_over_k0": (action_curl - r9_curl) / k0,
        }
        terms: dict[str, Any] = {}
        for component in ("E", "curl_over_k0"):
            terms[component] = v19._accumulate_component(
                response_error[component], action_delta[component],
                weights, slots, cell_count, 1.0,
            )
        terms["G"] = {
            key: terms["E"][key] + terms["curl_over_k0"][key]
            for key in terms["E"]
        }
        direct_remaining: dict[str, dict[str, np.ndarray]] = {}
        for component in ("E", "curl_over_k0"):
            direct_remaining[component] = v19._accumulate_component(
                response_error[component] - action_delta[component],
                np.zeros_like(response_error[component]),
                weights, slots, cell_count, 1.0,
            )
        direct_remaining["G"] = {
            key: direct_remaining["E"][key] + direct_remaining["curl_over_k0"][key]
            for key in direct_remaining["E"]
        }
        for component, component_terms in terms.items():
            component_terms["B10"] = direct_remaining[component]["B"]
            component_terms["I_independent"] = component_terms["B"] - component_terms["B10"]
            component_terms["identity_error"] = component_terms["I"] - component_terms["I_independent"]
        cases[name] = terms
    return cases


def _assert_response_identities(cases: dict[str, Any]) -> dict[str, float]:
    maxima: dict[str, float] = {}
    for action, components in cases.items():
        for component, terms in components.items():
            error = np.abs(terms["identity_error"])
            scale = np.maximum.reduce((
                np.abs(terms["B"]), np.abs(terms["B10"]),
                np.abs(terms["X"]), np.abs(terms["D"]),
                np.full(error.shape, 1.0e-30),
            ))
            relative = error / scale
            maximum = float(np.max(relative, initial=0.0))
            maxima[f"{action}.{component}"] = maximum
            if np.any(relative > IDENTITY_REL_TOL):
                raise EvidenceError(
                    f"response identity exceeded {IDENTITY_REL_TOL:g}: {action}.{component}"
                )
            total_b = math.fsum(float(value) for value in terms["B"])
            total_b10 = math.fsum(float(value) for value in terms["B10"])
            total_x = math.fsum(float(value) for value in terms["X"])
            total_d = math.fsum(float(value) for value in terms["D"])
            total_i = math.fsum(float(value) for value in terms["I"])
            global_error = total_i - (total_b - total_b10)
            global_scale = max(abs(total_b), abs(total_b10), abs(total_x), abs(total_d), 1.0e-30)
            global_relative = abs(global_error) / global_scale
            maxima[f"{action}.{component}.global"] = global_relative
            if global_relative > IDENTITY_REL_TOL:
                raise EvidenceError(
                    f"global response identity exceeded {IDENTITY_REL_TOL:g}: {action}.{component}"
                )
    return maxima


def _rank_cells(
    ids: list[int], b10: np.ndarray, q8_b10: np.ndarray | None,
    q8_ids: list[int] | None,
) -> dict[str, Any]:
    if b10.shape != (len(ids),) or not np.isfinite(b10).all() or np.any(b10 < 0.0):
        raise EvidenceError("R10 remaining-error cell values are invalid")
    ordered = sorted(range(len(ids)), key=lambda i: (-float(b10[i]), int(ids[i])))
    total = float(np.sum(b10, dtype=np.float64))
    if total <= 0.0:
        return {
            "status": "BOTH_ZERO_NO_LOCATION" if q8_b10 is not None and not np.any(q8_b10) else "NO_LOCATION",
            "total_B10": total, "top": [], "prefix_to_50_percent": [],
            "complete_ranking": [], "top_k_globals": {"1": [], "5": [], "10": [], "20": []},
            "normalized_fractions": {str(gid): None for gid in ids},
        }
    fractions = {int(gid): float(value / total) for gid, value in zip(ids, b10)}
    prefix: list[int] = []
    accumulated = 0.0
    for index in ordered:
        prefix.append(int(ids[index]))
        accumulated += float(b10[index])
        if accumulated >= 0.5 * total:
            break
    result: dict[str, Any] = {
        "status": "RANKED",
        "total_B10": total,
        "top": [
            {"global_cell_id": int(ids[i]), "B10": float(b10[i]), "fraction": fractions[int(ids[i])]}
            for i in ordered[:20]
        ],
        "top_k_globals": {
            str(k): [int(ids[i]) for i in ordered[:k]] for k in (1, 5, 10, 20)
        },
        "complete_ranking": [
            {
                "rank": rank, "global_cell_id": int(ids[i]), "B10": float(b10[i]),
                "fraction": fractions[int(ids[i])],
                "cumulative_B10": float(sum(float(b10[j]) for j in ordered[:rank])),
                "cumulative_fraction": float(sum(float(b10[j]) for j in ordered[:rank]) / total),
            }
            for rank, i in enumerate(ordered, start=1)
        ],
        "prefix_to_50_percent": prefix,
        "prefix_to_50_percent_sum": float(sum(float(b10[i]) for i in ordered[:len(prefix)])),
        "normalized_fractions": {str(gid): fractions[gid] for gid in sorted(fractions)},
    }
    if q8_b10 is not None and q8_ids is not None:
        if set(q8_ids) != set(ids) or q8_b10.shape != (len(q8_ids),):
            raise EvidenceError("q8/q10 cell map differs while comparing location stability")
        q8_total = float(np.sum(q8_b10, dtype=np.float64))
        if q8_total <= 0.0:
            result["q8_q10_location_stability"] = {
                "status": "UNRESOLVED_ZERO_Q8_TOTAL", "location_stable": False,
            }
            return result
        q8_fraction = {int(gid): float(value / q8_total) for gid, value in zip(q8_ids, q8_b10)}
        l1 = math.fsum(abs(fractions[gid] - q8_fraction[gid]) for gid in fractions)
        result["q8_q10_location_stability"] = {
            "normalized_cell_B10_fraction_L1": l1,
            "max_cell_q8": max(q8_fraction, key=lambda gid: (q8_fraction[gid], -gid)),
            "max_cell_q10": max(fractions, key=lambda gid: (fractions[gid], -gid)),
            "same_max_cell": max(q8_fraction, key=lambda gid: (q8_fraction[gid], -gid))
            == max(fractions, key=lambda gid: (fractions[gid], -gid)),
            "L1_limit": 1.0e-6,
            "location_stable": (
                max(q8_fraction, key=lambda gid: (q8_fraction[gid], -gid))
                == max(fractions, key=lambda gid: (fractions[gid], -gid))
                and l1 <= 1.0e-6
            ),
        }
    return result


def _modal_rows(
    modal: dict[str, dict[tuple[str, int, int, str], dict[str, Any]]],
    anchors: dict[str, Any], absorption: dict[str, float],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    aggregate: dict[str, Any] = {}
    y6 = modal["Y6_1"]
    y6_power = v19._modal_aggregate(y6, absorption["Y6_1"])
    channel_exceedances: dict[str, list[dict[str, Any]]] = {}
    for action in ("R9", "R10"):
        current_power = v19._modal_aggregate(modal[action], absorption[action])
        signed = {key: current_power[key] - y6_power[key] for key in current_power}
        absolute_saved = anchors[action]["modal_and_power_metrics"].get("power_absolute_differences", {})
        if set(absolute_saved) != set(signed):
            raise EvidenceError(f"{action} saved modal aggregate inventory is not the fixed six fields")
        aggregate_errors = {
            key: v19._close(abs(signed[key]), float(absolute_saved[key]), f"{action}.modal_abs.{key}")
            for key in signed
        }
        channel_delta = {
            key: float(modal[action][key]["power_ratio"]) - float(y6[key]["power_ratio"])
            for key in v19.CHANNEL_KEYS
        }
        maximum_key = max(v19.CHANNEL_KEYS, key=lambda key: abs(channel_delta[key]))
        channel_exceedances[action] = [
            {
                "side": key[0], "m": key[1], "n": key[2], "polarization": key[3],
                "signed_difference": channel_delta[key],
                "absolute_difference": abs(channel_delta[key]),
                "threshold": v19.J_CHANNEL_POWER_TOLERANCE,
            }
            for key in v19.CHANNEL_KEYS
            if abs(channel_delta[key]) > v19.J_CHANNEL_POWER_TOLERANCE
        ]
        saved_max = anchors[action]["modal_and_power_metrics"].get(
            "maximum_individual_channel_power_ratio_absolute_difference"
        )
        if saved_max is None:
            raise EvidenceError(f"{action} anchor lacks maximum individual channel difference")
        maximum_replay = v19._close(
            abs(channel_delta[maximum_key]), float(saved_max), f"{action}.max_channel"
        )
        aggregate[action] = {
            "signed_power_delta_vs_Y6_1": signed,
            "absolute_power_delta_vs_saved_modal_anchor": {
                key: abs(value) for key, value in signed.items()
            },
            "absolute_aggregate_replay_errors": aggregate_errors,
            "max_individual_channel_power_ratio_absolute_difference": abs(channel_delta[maximum_key]),
            "max_individual_channel_key": list(maximum_key),
            "max_channel_replay_error": maximum_replay,
            "channel_exceedance_count": len(channel_exceedances[action]),
            "channels_exceeding_threshold": channel_exceedances[action],
        }

    for key in v19.CHANNEL_KEYS:
        side, m, n, pol = key
        base, raised, reference = modal["R9"][key], modal["R10"][key], y6[key]
        row: dict[str, Any] = {"side": side, "m": m, "n": n, "polarization": pol}
        for label, values in (("R9", base), ("R10", raised), ("Y6_1", reference)):
            amp = v19._complex_pair(values, "outgoing_amplitude_at_boundary")
            row[f"{label}_amplitude_real"] = amp.real
            row[f"{label}_amplitude_imag"] = amp.imag
            row[f"{label}_power_ratio"] = float(values["power_ratio"])
            row[f"{label}_R"] = float(values["R"])
            row[f"{label}_T"] = float(values["T"])
        amp9 = v19._complex_pair(base, "outgoing_amplitude_at_boundary")
        amp10 = v19._complex_pair(raised, "outgoing_amplitude_at_boundary")
        ampy = v19._complex_pair(reference, "outgoing_amplitude_at_boundary")
        row.update({
            "R9_minus_Y6_1_amplitude_real": (amp9 - ampy).real,
            "R9_minus_Y6_1_amplitude_imag": (amp9 - ampy).imag,
            "R9_minus_Y6_1_amplitude_absolute": abs(amp9 - ampy),
            "R10_minus_R9_amplitude_real": (amp10 - amp9).real,
            "R10_minus_R9_amplitude_imag": (amp10 - amp9).imag,
            "R10_minus_R9_amplitude_absolute": abs(amp10 - amp9),
            "R10_minus_Y6_1_amplitude_real": (amp10 - ampy).real,
            "R10_minus_Y6_1_amplitude_imag": (amp10 - ampy).imag,
            "R10_minus_Y6_1_amplitude_absolute": abs(amp10 - ampy),
            "R10_minus_R9_power_ratio_signed": float(raised["power_ratio"]) - float(base["power_ratio"]),
            "R10_minus_R9_power_ratio_absolute": abs(
                float(raised["power_ratio"]) - float(base["power_ratio"])
            ),
            "R9_minus_Y6_1_power_ratio_signed": float(base["power_ratio"]) - float(reference["power_ratio"]),
            "R9_minus_Y6_1_power_ratio_absolute": abs(
                float(base["power_ratio"]) - float(reference["power_ratio"])
            ),
            "R9_minus_Y6_1_power_exceeds_1e_6": abs(
                float(base["power_ratio"]) - float(reference["power_ratio"])
            ) > v19.J_CHANNEL_POWER_TOLERANCE,
            "R10_minus_Y6_1_power_ratio_signed": float(raised["power_ratio"]) - float(reference["power_ratio"]),
            "R10_minus_Y6_1_power_ratio_absolute": abs(
                float(raised["power_ratio"]) - float(reference["power_ratio"])
            ),
            "R10_minus_Y6_1_power_exceeds_1e_6": abs(
                float(raised["power_ratio"]) - float(reference["power_ratio"])
            ) > v19.J_CHANNEL_POWER_TOLERANCE,
            "R10_propagating": bool(raised.get("propagating", False)),
        })
        rows.append(row)
    return rows, aggregate


def _z_layer_summaries(
    cells: list[dict[str, Any]], results: dict[str, Any], *, expected_layers: int = 6,
) -> dict[str, Any]:
    z_edges = sorted({
        float(value) for row in cells for value in (row["lower"][2], row["upper"][2])
    })
    if len(z_edges) != expected_layers + 1:
        raise EvidenceError(
            f"frozen cell geometry must define {expected_layers} z layers, got {len(z_edges)-1}"
        )
    output: dict[str, Any] = {}
    for layer, (z0, z1) in enumerate(zip(z_edges, z_edges[1:]), start=1):
        indexes = [
            i for i, row in enumerate(cells)
            if float(row["lower"][2]) == z0 and float(row["upper"][2]) == z1
        ]
        if not indexes:
            raise EvidenceError(f"empty frozen z layer [{z0}, {z1}]")
        terms: dict[str, Any] = {}
        for action, components in results.items():
            terms[action] = {}
            for component, values in components.items():
                aggregate = {}
                for name in ("B", "D", "X", "I", "B10", "I_independent"):
                    aggregate[name] = float(np.sum(values[name][indexes], dtype=np.float64))
                impact = values["I"][indexes]
                aggregate["positive_I_sum"] = float(np.sum(np.maximum(impact, 0.0), dtype=np.float64))
                aggregate["negative_I_sum"] = float(np.sum(np.minimum(impact, 0.0), dtype=np.float64))
                aggregate["direction_correlation"] = (
                    aggregate["X"] / (2.0 * math.sqrt(aggregate["B"] * aggregate["D"]))
                    if aggregate["B"] > 0.0 and aggregate["D"] > 0.0 else "N/A"
                )
                terms[action][component] = aggregate
        output[f"z_layer_{layer}"] = {
            "z_interval_nm": [z0, z1], "cell_count": len(indexes), "terms": terms,
        }
    return output


def _cell_plan_geometry_relation(
    cell: dict[str, Any], plan: dict[str, Any], cells: list[dict[str, Any]],
) -> dict[str, Any]:
    config = plan.get("base_config", {})
    raw_grating = config.get("grating_bounds")
    interface = config.get("interface_z")
    if not isinstance(raw_grating, list) or len(raw_grating) != 6 or interface is None:
        raise EvidenceError("R10 base plan lacks frozen grating bounds or interface z")
    grating = [float(v) for v in raw_grating]
    interface_z = float(interface)
    if not all(math.isfinite(v) for v in grating) or not math.isfinite(interface_z):
        raise EvidenceError("R10 base plan geometry contains nonfinite values")
    grating_axes = ((grating[0], grating[3]), (grating[1], grating[4]), (grating[2], grating[5]))
    cell_axes = tuple(
        (float(cell["lower"][i]), float(cell["upper"][i])) for i in range(3)
    )
    axis_relations: dict[str, str] = {}
    for axis_name, (a0, a1), (b0, b1) in zip(("x", "y", "z"), cell_axes, grating_axes):
        overlap = min(a1, b1) - max(a0, b0)
        if overlap > 0.0:
            relation = "OVERLAPS"
        elif a1 == b0 or b1 == a0:
            relation = "TOUCHES"
        else:
            relation = "DISJOINT"
        axis_relations[axis_name] = relation

    lower_domain_z = min(float(row["lower"][2]) for row in cells)
    upper_domain_z = max(float(row["upper"][2]) for row in cells)
    if (lower_domain_z, upper_domain_z) != (-10.0, 130.0):
        raise EvidenceError("frozen base-cell domain no longer matches the saved z-port planes")
    z0, z1 = cell_axes[2]
    if z1 < interface_z:
        interface_relation = "BELOW_INTERFACE"
    elif z0 > interface_z:
        interface_relation = "ABOVE_INTERFACE"
    elif z0 == interface_z:
        interface_relation = "ABOVE_FROM_INTERFACE"
    elif z1 == interface_z:
        interface_relation = "BELOW_TO_INTERFACE"
    else:
        interface_relation = "CROSSES_INTERFACE"
    return {
        "cell_axis_bounds_nm": {axis: list(bounds) for axis, bounds in zip(("x", "y", "z"), cell_axes)},
        "grating_bounds_nm": grating,
        "grating_relation_by_axis": axis_relations,
        "overlaps_grating_volume": all(value == "OVERLAPS" for value in axis_relations.values()),
        "touches_any_grating_face": any(value == "TOUCHES" for value in axis_relations.values()),
        "interface_z_nm": interface_z,
        "interface_relation": interface_relation,
        "touches_interface": z0 == interface_z or z1 == interface_z,
        "z_port_surfaces_nm": [lower_domain_z, upper_domain_z],
        "touches_lower_z_port": z0 == lower_domain_z or z1 == lower_domain_z,
        "touches_upper_z_port": z0 == upper_domain_z or z1 == upper_domain_z,
        "within_z_port_slab": z0 >= lower_domain_z and z1 <= upper_domain_z,
        "source": "R10 plan base_config grating_bounds/interface_z and frozen cell-map z endpoints",
    }


def _location_proposal(
    q8: dict[str, Any], q10: dict[str, Any], cells: list[dict[str, Any]],
    public_g_denominator: float, r10_plan: dict[str, Any],
) -> dict[str, Any]:
    rank8 = q8["remaining_error_location"]
    rank10 = q10["remaining_error_location"]
    total8, total10 = float(rank8["total_B10"]), float(rank10["total_B10"])
    if total8 == 0.0 and total10 == 0.0:
        return {"status": "ZERO_REMAINDER_NO_LOCATION", "q8_total_B10": total8, "q10_total_B10": total10}
    stability = rank10.get("q8_q10_location_stability", {})
    if total8 <= 0.0 or total10 <= 0.0 or stability.get("location_stable") is not True:
        return {
            "status": "LOCATION_UNRESOLVED_AT_SAVED_Q",
            "q8_total_B10": total8, "q10_total_B10": total10,
            "q8_top20": rank8["complete_ranking"][:20],
            "q10_top20": rank10["complete_ranking"][:20],
            "q8_q10_location_stability": stability,
        }
    proposal_id = int(rank10["complete_ranking"][0]["global_cell_id"])
    cell = next(row for row in cells if int(row["global_cell_id"]) == proposal_id)
    b10 = float(rank10["complete_ranking"][0]["B10"])
    after = max(0.0, total10 - b10)
    gain_abs = math.sqrt(total10) - math.sqrt(after)
    return {
        "status": "STABLE_REMAINDER_LOCATION_PROPOSAL",
        "rule": "q10 B10 descending, exact ties by smaller global_cell_id; q8/q10 normalized B10 L1 <= 1e-6 and same maximum cell",
        "q8_q10_location_stability": stability,
        "proposed_cell": {
            "global_cell_id": proposal_id,
            "forest_root": int(cell["forest_root"]),
            "lower_nm": cell["lower"], "upper_nm": cell["upper"],
            "r9_p": int(cell["r9_p"]), "r10_p": int(cell["r10_p"]),
            "q8_B10_fraction": rank8["normalized_fractions"][str(proposal_id)],
            "q10_B10_fraction": rank10["normalized_fractions"][str(proposal_id)],
            "same_as_original_requested_global8": proposal_id == 8,
            "geometry_relation": _cell_plan_geometry_relation(cell, r10_plan, cells),
        },
        "conditional_remove_only_this_box_B10": {
            "q10_total_B10_before": total10,
            "selected_box_B10": b10,
            "q10_total_B10_after_if_box_alone_removed": after,
            "conditional_absolute_G_norm_gain": gain_abs,
            "conditional_G_relative_gain_over_frozen_reference_or_floor": gain_abs / public_g_denominator,
            "warning": "single-box removal condition only; not a prediction of globally coupled h refinement",
        },
    }


def _delta_summary(
    q8: dict[str, Any], q10: dict[str, Any], manifest: dict[str, Any],
) -> dict[str, Any]:
    r9_j = float(q10["field_and_J_replay"]["R9"]["J_replay"]["value"])
    r10_j = float(q10["field_and_J_replay"]["R10"]["J_replay"]["value"])
    delta_j = r9_j - r10_j
    g8_9 = float(q8["field_and_J_replay"]["R9"]["field_relative_metrics"]["G"])
    g8_10 = float(q8["field_and_J_replay"]["R10"]["field_relative_metrics"]["G"])
    g10_9 = float(q10["field_and_J_replay"]["R9"]["field_relative_metrics"]["G"])
    g10_10 = float(q10["field_and_J_replay"]["R10"]["field_relative_metrics"]["G"])
    improvements = {"q8": g8_9 - g8_10, "q10": g10_9 - g10_10}
    delta_fe = int(manifest["delta_FE_historical"])
    if delta_fe <= 0:
        raise EvidenceError("historical FE increment must be positive")
    epsilon_j = float(manifest["epsilon_J"])
    epsilon_g = float(manifest["epsilon_G"])

    def resolution(delta: float, epsilon: float) -> str:
        if delta > epsilon:
            return "IMPROVEMENT_RESOLVED_AT_FROZEN_SCALE"
        if delta < -epsilon:
            return "WORSENING_RESOLVED_AT_FROZEN_SCALE"
        return "WITHIN_FROZEN_UNRESOLVED_SCALE"

    g_resolution = {
        order: {
            "delta_G_improvement_R9_minus_R10": value,
            "epsilon_G_distinguishable_scale": epsilon_g,
            "direction_status": resolution(value, epsilon_g),
            "improvement_exceeds_epsilon": value > epsilon_g,
            "per_historical_delta_FE": value / delta_fe,
            "per_historical_delta_FE_interval_from_epsilon": [
                (value - epsilon_g) / delta_fe,
                (value + epsilon_g) / delta_fe,
            ],
        }
        for order, value in improvements.items()
    }
    return {
        "J_R9": r9_j, "J_R10": r10_j,
        "delta_J_improvement_R9_minus_R10": delta_j,
        "delta_J_improvement_per_historical_delta_FE": delta_j / delta_fe,
        "J_direction_status_at_frozen_scale": resolution(delta_j, epsilon_j),
        "J_improvement_exceeds_epsilon": delta_j > epsilon_j,
        "J_per_historical_delta_FE_interval_from_epsilon": [
            (delta_j - epsilon_j) / delta_fe,
            (delta_j + epsilon_j) / delta_fe,
        ],
        "G_R9_by_saved_q": {"q8": g8_9, "q10": g10_9},
        "G_R10_by_saved_q": {"q8": g8_10, "q10": g10_10},
        "delta_G_resolution_by_saved_q": g_resolution,
        "delta_G_improvement_interval_from_saved_q": [min(improvements.values()), max(improvements.values())],
        "historical_delta_FE": delta_fe,
        "epsilon_J_distinguishable_scale": epsilon_j,
        "epsilon_G_distinguishable_scale": epsilon_g,
        "interpretation": (
            "epsilon_J and epsilon_G are frozen distinguishable scales for the R9-to-R10 improvement; "
            "they are not absolute-error acceptance limits or new selection authority"
        ),
    }


def _field_and_j_replay(
    arrays: dict[str, np.ndarray], bundle: dict[str, Any], weights: np.ndarray,
    physics: dict[str, Any],
) -> dict[str, Any]:
    p5 = {
        "weights_nm3": weights,
        "Y6_1_E": arrays["Y6_1_E"],
        "Y6_1_curl_E": arrays["Y6_1_curl_E"],
    }
    output: dict[str, Any] = {}
    y6_modal = bundle["modal"]["Y6_1"]
    y6_abs = bundle["absorption"]["Y6_1"]
    reference_power = v19._modal_aggregate(y6_modal, y6_abs)
    for action, prefix in (("R9", "round9_p_up"), ("R10", "round10_p_up")):
        field_ratios, field_record = v19._field_replay(
            p5, arrays[f"{prefix}_E"], arrays[f"{prefix}_curl_E"],
            {"field_metrics": bundle["anchors"][action]["field_metrics"]},
            float(physics["k0_per_nm"]),
            float(physics["magnetic_field_scale_a_per_m"]),
            float(physics["incident_g_norm_floor"]),
        )
        candidate_modal = bundle["modal"][action]
        candidate_abs = bundle["absorption"][action]
        action_power = v19._modal_aggregate(candidate_modal, candidate_abs)
        signed = {key: action_power[key] - reference_power[key] for key in action_power}
        replay_case = {
            "signed_observables": {"aggregate_signed_candidate_minus_reference": signed},
            "J_infinity": bundle["anchors"][action]["J_infinity"],
        }
        j_record = v19._replay_j(
            p5, arrays[f"{prefix}_E"], arrays[f"{prefix}_curl_E"], candidate_modal,
            y6_modal, candidate_abs, y6_abs, replay_case, reference_power, field_ratios,
        )
        output[action] = {
            "field_relative_metrics": field_ratios,
            "field_replay": field_record,
            "J_replay": j_record,
        }
    return output


def _analyze_order(
    label: str, record: dict[str, Any], bundle: dict[str, Any], manifest: dict[str, Any],
    *, fixture: bool = False, fixture_order: int | None = None,
    q8_b10: np.ndarray | None = None, q8_ids: list[int] | None = None,
    expected_volume: float = DOMAIN_VOLUME_NM3,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], np.ndarray]:
    arrays, archive_meta = read_saved_archive(record, fixture=fixture)
    order = fixture_order if fixture_order is not None else int(label.removeprefix("q"))
    partition = _partition_owner(
        arrays["points_nm"], record["axis_breakpoints_nm"], order,
        int(record["partition_boxes"]),
    )
    cells = bundle["cells"]
    owner_slots, owner_record = map_points_to_cells(
        arrays["points_nm"], arrays["weights_nm3"], cells, expected_volume=expected_volume
    )
    if owner_slots.shape != partition["box_indices"].shape:
        raise EvidenceError("partition and cell ownership maps have different point counts")
    results = _response_decomposition(
        arrays, arrays["weights_nm3"], owner_slots, len(cells),
        float(manifest["physics"]["k0_per_nm"]),
    )
    identity_maxima = _assert_response_identities(results)
    ids = [int(row["global_cell_id"]) for row in cells]
    groups = _group_cells(cells)
    baseline_b10 = results["R9"]["G"]["B10"]
    final_b10 = results["R10"]["G"]["B10"]
    field_j = _field_and_j_replay(arrays, bundle, arrays["weights_nm3"], manifest["physics"])
    for action in ("R9", "R10"):
        norms = field_j[action]["field_replay"]["difference_norms"]
        direct_b10_checks = {
            "E": (float(np.sum(results[action]["E"]["B10"], dtype=np.float64)), norms["E_total_code"] ** 2),
            "curl_over_k0": (
                float(np.sum(results[action]["curl_over_k0"]["B10"], dtype=np.float64)),
                norms["curl_E_over_k0_code"] ** 2,
            ),
            "G": (float(np.sum(results[action]["G"]["B10"], dtype=np.float64)), norms["G"] ** 2),
        }
        for component, (direct_sum, field_square) in direct_b10_checks.items():
            v19._close(
                direct_sum, field_square,
                f"{label}.{action}.independent_B10.{component}_vs_field",
            )
    normalized_g_squared = max(
        float(bundle["anchors"]["R9"]["field_metrics"]["G"]["reference_g_norm"]),
        float(manifest["physics"]["incident_g_norm_floor"]),
    ) ** 2
    baseline_error_squared = float(np.sum(baseline_b10, dtype=np.float64))
    cell_rows = v19._cell_csv_rows(
        int(label.removeprefix("q")), cells, ids, groups, results,
        normalized_g_squared, baseline_error_squared,
    )
    for row_index, row in enumerate(cell_rows):
        cell = cells[row_index]
        row["forest_root"] = int(cell["forest_root"])
        row["r9_p"] = int(cell["r9_p"])
        row["r10_p"] = int(cell["r10_p"])
        row["raised"] = bool(cell["raised"])
        for action in ("R9", "R10"):
            for component in COMPONENTS:
                terms = results[action][component]
                prefix = f"{action}.{component}"
                row[f"{prefix}.B10"] = float(terms["B10"][row_index])
                row[f"{prefix}.B10.over_frozen_reference_or_floor_G2"] = (
                    float(terms["B10"][row_index]) / normalized_g_squared
                )
                row[f"{prefix}.B10.over_baseline_error_G2"] = (
                    float(terms["B10"][row_index]) / baseline_error_squared
                    if baseline_error_squared else None
                )
    block_summary = v19._block_summaries(ids, groups, results)
    raised_summary: dict[str, Any] = {}
    for raised, block_name in ((True, "p5_to_p6"), (False, "p6_to_p6")):
        indexes = [i for i, row in enumerate(cells) if bool(row["raised"]) is raised]
        raised_summary[block_name] = {
            "cell_count": len(indexes),
            "terms": {
                f"{action}.{component}.{term}": float(np.sum(values[term][indexes], dtype=np.float64))
                for action, components in results.items()
                for component, values in components.items()
                for term in ("B", "D", "X", "I", "B10", "I_independent")
            },
            "positive_negative_I": {
                f"{action}.{component}": {
                    "positive_I_sum": float(np.sum(np.maximum(values["I"][indexes], 0.0), dtype=np.float64)),
                    "negative_I_sum": float(np.sum(np.minimum(values["I"][indexes], 0.0), dtype=np.float64)),
                }
                for action, components in results.items()
                for component, values in components.items()
            },
        }
    modal_rows, modal_replay = _modal_rows(bundle["modal"], bundle["anchors"], bundle["absorption"])
    ranking = _rank_cells(ids, final_b10, q8_b10, q8_ids)
    owner_global_ids = np.asarray(owner_record.pop("point_owner_global_ids"), dtype=np.int64)
    owner_digest = hashlib.sha256(owner_global_ids.tobytes(order="C")).hexdigest()
    historical_rows = []
    if not fixture:
        b10_by_id = {gid: float(final_b10[i]) for i, gid in enumerate(ids)}
        for rank, gid in enumerate(manifest["historical_V19"]["top10_B9_globals"], start=1):
            row = next(cell for cell in cells if int(cell["global_cell_id"]) == int(gid))
            historical_rows.append({
                "historical_B9_rank": rank, "global_cell_id": int(gid),
                "forest_root": int(row["forest_root"]), "R9_p": int(row["r9_p"]),
                "R10_p": int(row["r10_p"]), "R10_B10": b10_by_id[int(gid)],
                "R10_B10_fraction": ranking["normalized_fractions"].get(str(int(gid))),
            })
    diagnostic = {
        "schema": "task43.v20.saved_r10_order_diagnostic.v1",
        "order": label,
        "sample_count": int(record["sample_count"]),
        "partition_box_count": int(record["partition_boxes"]),
        "array_identity": archive_meta,
        "ownership": {
            key: (value.tolist() if isinstance(value, np.ndarray) else value)
            for key, value in owner_record.items()
        },
        "point_owner_global_ids_sha256": owner_digest,
        "point_owner_count": int(owner_global_ids.size),
        "point_owner_unique_global_ids": sorted(int(value) for value in np.unique(owner_global_ids)),
        "partition": {
            "points_per_box": partition["points_per_box"],
            "boundary_coordinate_hits": partition["boundary_coordinate_hits"],
            "box_count": int(record["partition_boxes"]),
        },
        "domain_volume_nm3": expected_volume,
        "frozen_reference_or_floor_G_squared_nm3": normalized_g_squared,
        "baseline_R9_error_G_squared_nm3": baseline_error_squared,
        "response_global_terms": {
            action: {component: _sum_terms(terms) for component, terms in components.items()}
            for action, components in results.items()
        },
        "response_identity_max_relative_error": identity_maxima,
        "block_summaries": block_summary,
        "z_layer_summaries": _z_layer_summaries(
            cells, results, expected_layers=(len(bundle["z_edges"]) - 1 if fixture else 6)
        ),
        "degree_summaries": raised_summary,
        "historical_V19_top10_B9_positions_after_R10": historical_rows,
        "remaining_error_location": ranking,
        "field_and_J_replay": field_j,
        "modal_power_replay": modal_replay,
        "returned_cell_rows": len(cell_rows),
        "returned_modal_rows": len(modal_rows),
        "mode_power_interpretation": "saved power_ratio and physical R/T are retained; boundary amplitude squared is not treated as power",
    }
    return diagnostic, cell_rows, modal_rows, final_b10.copy()


def _capture_inputs(
    manifest_path: Path, manifest: dict[str, Any], source_paths: dict[str, Path], *, fixture: bool,
) -> dict[str, str]:
    values = {"manifest": _sha256_file(manifest_path)}
    if not fixture and isinstance(manifest.get("input_lock"), dict):
        values["input_lock"] = _sha256_file(_checked_file(manifest["input_lock"]))
    for role, path in source_paths.items():
        values[f"source:{role}"] = _sha256_file(path)
    for label, record in manifest["quadrature"].items():
        values[f"quadrature:{label}"] = _sha256_file(_checked_file(record, fixture=fixture))
    values["checker"] = _sha256_file(Path(__file__))
    values["v19_checker"] = _sha256_file(Path(v19.__file__))
    return values


def _persist_order(
    output_root: Path, label: str, diagnostic: dict[str, Any],
    cell_rows: list[dict[str, Any]], modal_rows: list[dict[str, Any]],
    failure_hook: Any = None,
) -> dict[str, Any]:
    order_root = output_root / label
    order_root.mkdir(exist_ok=False)
    diagnostic_path = order_root / "diagnostic.json"
    cells_path = order_root / "cells.csv"
    modal_path = order_root / "modes_612.csv"
    diagnostic_sha = v19.atomic_json(diagnostic_path, diagnostic)
    if not cell_rows or not modal_rows:
        raise EvidenceError(f"{label} output rows cannot be empty")
    cell_sha = v19.atomic_csv(cells_path, list(cell_rows[0]), cell_rows)
    if failure_hook is not None:
        failure_hook(label, "after_cells_csv", output_root)
    modal_sha = v19.atomic_csv(modal_path, list(modal_rows[0]), modal_rows)
    return {
        "status": "COMPLETE",
        "sample_count": diagnostic["sample_count"],
        "artifacts": {
            "diagnostic": {"path": str(diagnostic_path.relative_to(output_root)), "sha256": diagnostic_sha},
            "cells_csv": {"path": str(cells_path.relative_to(output_root)), "sha256": cell_sha},
            "modes_612_csv": {"path": str(modal_path.relative_to(output_root)), "sha256": modal_sha},
        },
    }


def _terminal_payload(run_manifest: dict[str, Any], output_root: Path) -> dict[str, Any]:
    orders = run_manifest.get("orders")
    if not isinstance(orders, dict) or set(orders) != {"q8", "q10"}:
        raise EvidenceError("cannot create terminal record without both q8 and q10")
    for label in ("q8", "q10"):
        order = orders[label]
        if order.get("status") != "COMPLETE" or set(order.get("artifacts", {})) != set(REQUIRED_OUTPUTS):
            raise EvidenceError(f"cannot finalize incomplete order {label}")
        for record in order["artifacts"].values():
            if len(str(record.get("sha256", ""))) != 64:
                raise EvidenceError(f"cannot finalize order {label} with an unbound artifact")
            relative = Path(str(record.get("path", "")))
            if relative.is_absolute() or ".." in relative.parts or not relative.parts:
                raise EvidenceError(f"cannot finalize order {label} with an escaping artifact path")
            artifact = output_root / relative
            if artifact.is_symlink() or not artifact.is_file() or _sha256_file(artifact) != record["sha256"]:
                raise EvidenceError(f"cannot finalize order {label} with a missing or changed artifact")
    return {
        "schema": "task43.v20.saved_r10_terminal.v1",
        "status": "COMPLETE",
        "orders": orders,
        "source_sha256_start": run_manifest["source_sha256_start"],
        "source_sha256_end": run_manifest["source_sha256_end"],
        "checker_sha256_start": run_manifest["checker_sha256_start"],
        "checker_sha256_end": run_manifest["checker_sha256_end"],
        "science_summary": run_manifest["science_summary"],
    }


def _run_diagnostic(
    manifest: dict[str, Any], manifest_sha: str, lock: dict[str, Any] | None,
    manifest_path: Path, output_root: Path, *, fixture: bool = False,
    fixture_orders: dict[str, int] | None = None, expected_volume: float = DOMAIN_VOLUME_NM3,
    failure_hook: Any = None, pre_analysis: Any = None,
) -> dict[str, Any]:
    if output_root.is_symlink() or output_root.exists():
        raise EvidenceError(f"output root must be a new unique directory: {output_root}")
    output_root.mkdir(parents=True, exist_ok=False)
    run_manifest: dict[str, Any] = {
        "schema": "task43.v20.saved_r10_run_manifest.v1",
        "status": "RUNNING",
        "contract_path": str(manifest_path),
        "contract_sha256": manifest_sha,
        "source_sha256_start": None,
        "source_sha256_end": None,
        "checker_sha256_start": None,
        "checker_sha256_end": None,
        "orders": {},
        "started_utc": datetime.now(timezone.utc).isoformat(),
    }
    run_path = output_root / "run_manifest.json"
    completed_diagnostics: dict[str, Any] = {}
    q8_b10: np.ndarray | None = None
    q8_ids: list[int] | None = None
    try:
        v19.atomic_json(run_path, run_manifest)
        paths = _source_paths(manifest, fixture=fixture)
        start_inputs = _capture_inputs(manifest_path, manifest, paths, fixture=fixture)
        if start_inputs["manifest"] != manifest_sha:
            raise EvidenceError("manifest changed between validation and run start")
        source_only = {key: value for key, value in start_inputs.items() if key not in ("checker", "v19_checker")}
        run_manifest["source_sha256_start"] = source_only
        run_manifest["checker_sha256_start"] = {
            "checker": start_inputs["checker"], "v19_checker": start_inputs["v19_checker"]
        }
        v19.atomic_json(run_path, run_manifest)
        bundle = _load_source_bundle(manifest, paths, lock, fixture=fixture)
        if pre_analysis is not None:
            pre_analysis()
        for label in ("q8", "q10"):
            record = manifest["quadrature"][label]
            diagnostic, cell_rows, modal_rows, current_b10 = _analyze_order(
                label, record, bundle, manifest, fixture=fixture,
                fixture_order=(fixture_orders or {}).get(label), expected_volume=expected_volume,
                q8_b10=q8_b10 if label == "q10" else None,
                q8_ids=q8_ids if label == "q10" else None,
            )
            if failure_hook is not None:
                failure_hook(label, "before_persist", output_root)
            run_manifest["orders"][label] = _persist_order(
                output_root, label, diagnostic, cell_rows, modal_rows, failure_hook
            )
            completed_diagnostics[label] = diagnostic
            if label == "q8":
                q8_b10 = current_b10
                q8_ids = [int(row["global_cell_id"]) for row in bundle["cells"]]
            v19.atomic_json(run_path, run_manifest)
            if failure_hook is not None:
                failure_hook(label, "after_persist", output_root)
        end_inputs = _capture_inputs(manifest_path, manifest, paths, fixture=fixture)
        source_end = {key: value for key, value in end_inputs.items() if key not in ("checker", "v19_checker")}
        checker_end = {"checker": end_inputs["checker"], "v19_checker": end_inputs["v19_checker"]}
        if source_end != run_manifest["source_sha256_start"]:
            raise EvidenceError("a frozen JSON/CSV/quadrature input changed during the run")
        if checker_end != run_manifest["checker_sha256_start"]:
            raise EvidenceError("checker source changed during the run")
        run_manifest["source_sha256_end"] = source_end
        run_manifest["checker_sha256_end"] = checker_end
        run_manifest["status"] = "COMPLETE"
        run_manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        delta_summary = _delta_summary(
            completed_diagnostics["q8"], completed_diagnostics["q10"], manifest
        )
        public_g_denominator = math.sqrt(
            completed_diagnostics["q10"]["frozen_reference_or_floor_G_squared_nm3"]
        )
        location = _location_proposal(
            completed_diagnostics["q8"], completed_diagnostics["q10"],
            bundle["cells"], public_g_denominator, bundle["plans"]["R10"],
        )
        run_manifest["diagnostic_summary"] = {
            label: {
                "remaining_error_location": completed_diagnostics[label]["remaining_error_location"],
                "response_identity_max_relative_error": completed_diagnostics[label]["response_identity_max_relative_error"],
            }
            for label in ("q8", "q10")
        }
        run_manifest["science_summary"] = {
            "location_proposal": location,
            "delta_J_G_per_historical_delta_FE": delta_summary,
        }
        v19.atomic_json(run_path, run_manifest)
        terminal = _terminal_payload(run_manifest, output_root)
        terminal_path = output_root / "terminal.json"
        v19.atomic_json(terminal_path, terminal)
        final = {
            "schema": "task43.v20.saved_r10_terminal.v1",
            "status": "COMPLETE",
            "contract_sha256": manifest_sha,
            "orders": completed_diagnostics,
            "run_manifest_sha256": _sha256_file(run_path),
            "terminal_sha256": _sha256_file(terminal_path),
        }
        return final
    except BaseException as exc:
        run_manifest["status"] = "FAILED_INCOMPLETE"
        run_manifest["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        run_manifest["finished_utc"] = datetime.now(timezone.utc).isoformat()
        try:
            v19.atomic_json(run_path, run_manifest)
        except BaseException:
            pass
        raise


def main(
    manifest_path: Path | None = None, output_root: Path | None = None, *,
    _test_fixture: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Run the fixed V20 saved-array diagnostic; fixture override is test-only."""
    if _test_fixture is not None:
        manifest = _test_fixture["manifest"]
        _validate_contract(manifest, fixture=True)
        if output_root is None:
            output_root = Path(_test_fixture["output_root"])
        fixture_manifest_path = Path(_test_fixture["manifest_path"])
        v19.atomic_json(fixture_manifest_path, manifest)
        manifest_sha = _sha256_file(fixture_manifest_path)
        return _run_diagnostic(
            manifest, manifest_sha, None, fixture_manifest_path, Path(output_root),
            fixture=True, fixture_orders=_test_fixture["orders"],
            expected_volume=float(_test_fixture["expected_volume_nm3"]),
            failure_hook=_test_fixture.get("failure_hook"),
        )
    fixed_manifest = manifest_path or REPO_ROOT / CONTRACT_RELATIVE_PATH
    manifest, manifest_sha, lock = _load_manifest(Path(fixed_manifest))
    stage = os.environ.get("TASK43_V20_STAGE", "")
    if stage not in ("D1", "D2"):
        raise EvidenceError("diagnostic main only runs under the frozen D1/D2 worker stage")
    root_text = os.environ.get("TASK43_V20_RUN_ROOT", "")
    if not root_text:
        raise EvidenceError("V20 run root environment is missing")
    expected_root = REPO_ROOT / manifest["slots"][stage]["root"]
    run_root = Path(root_text)
    if run_root.absolute() != expected_root.absolute():
        raise EvidenceError("V20 run root does not match the unique slot path")
    expected_output = expected_root / "data"
    if output_root is not None and Path(output_root).absolute() != expected_output.absolute():
        raise EvidenceError("V20 output root does not match the unique slot data directory")
    output_root = expected_output

    def run_stage_tests() -> None:
        if stage != "D2":
            return
        selectors = manifest["tests"]["d2_selectors"]
        if not selectors or len(selectors) > 6:
            raise EvidenceError("D2 requires a nonempty released subset of at most six T1 nodes")
        import pytest
        run_root.mkdir(parents=True, exist_ok=True)
        code = pytest.main([
            "-v", "-rA", "--maxfail=1",
            "--junitxml", str(run_root / "tests.xml"),
            "--basetemp", str(run_root / "fixtures"), *selectors,
        ])
        if int(code) != 0:
            raise EvidenceError(f"D2 targeted tests returned {int(code)}")

    v19.write_runtime_identity(stage, "start")
    try:
        return _run_diagnostic(
            manifest, manifest_sha, lock, Path(fixed_manifest), Path(output_root),
            pre_analysis=run_stage_tests,
        )
    finally:
        v19.write_runtime_identity(stage, "end")


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=REPO_ROOT / CONTRACT_RELATIVE_PATH)
    parser.add_argument("--output-root", type=Path, default=None)
    args = parser.parse_args()
    try:
        main(args.manifest, args.output_root)
    except BaseException as exc:
        print(f"V20 saved R10 response diagnostic failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

