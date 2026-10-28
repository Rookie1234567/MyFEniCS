"""Small, saved-data fixtures for the V20 R10 response diagnostic.

The fixtures exercise the real JSON/CSV/NPZ readers, numerical helpers, and
atomic output path. They do not construct a mesh or call a solver.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from benchmarks.task43_hp_adaptivity import analyze_saved_hp_response as v19
from benchmarks.task43_hp_adaptivity import analyze_saved_r10_response as v20


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


@pytest.fixture(scope="session", autouse=True)
def _bound_worker_identity():
    stage = os.environ.get("TASK43_V20_STAGE", "")
    if stage in ("T1", "T2"):
        v19.write_runtime_identity(stage, "start")
        yield
        v19.write_runtime_identity(stage, "end")
        return
    if stage == "D2":
        root = Path(os.environ["TASK43_V20_RUN_ROOT"])
        start = v19._json_file(root / "runtime_start.json")
        assert int(start["identity"]["pid"]) == os.getpid()
        assert start["stage"] == "D2"
        yield
        return
    yield


def _cells() -> list[dict[str, Any]]:
    return [
        {
            "global_cell_id": 0, "forest_root": 4,
            "lower": [0.0, 0.0, -10.0], "upper": [1.0, 1.0, 0.0],
            "r9_p": 5, "r10_p": 6, "raised": True,
        },
        {
            "global_cell_id": 1, "forest_root": 34,
            "lower": [0.0, 0.0, 0.0], "upper": [1.0, 1.0, 130.0],
            "r9_p": 6, "r10_p": 6, "raised": False,
        },
    ]


def _sample_arrays(order: int) -> dict[str, np.ndarray]:
    points: list[list[float]] = []
    weights: list[float] = []
    for z0, z1 in ((-10.0, 0.0), (0.0, 130.0)):
        cell_volume = z1 - z0
        for ix in range(order):
            for iy in range(order):
                for iz in range(order):
                    points.append([
                        (ix + 0.5) / order,
                        (iy + 0.5) / order,
                        z0 + (iz + 0.5) * cell_volume / order,
                    ])
                    weights.append(cell_volume / (order ** 3))
    pts = np.asarray(points, dtype=np.float64)
    count = len(points)
    y = np.zeros((count, 3), dtype=np.complex128)
    r9 = np.zeros((count, 3), dtype=np.complex128)
    r10 = np.zeros((count, 3), dtype=np.complex128)
    r9[:, 0] = 1.0 + 0.0j
    r10[:, 0] = 0.5 + 0.0j
    zcurl = np.zeros((count, 3), dtype=np.complex128)
    return {
        "points_nm": pts,
        "weights_nm3": np.asarray(weights, dtype=np.float64),
        "round9_p_up_E": r9,
        "round9_p_up_curl_E": zcurl.copy(),
        "round10_p_up_E": r10,
        "round10_p_up_curl_E": zcurl.copy(),
        "Y6_1_E": y,
        "Y6_1_curl_E": zcurl.copy(),
    }


def _save_npz(path: Path, arrays: dict[str, np.ndarray]) -> None:
    payload = dict(arrays)
    for name in sorted(v20.FORBIDDEN_ARRAYS):
        payload[name] = np.zeros((1,), dtype=np.float64)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez(path, **payload)


def _field_metrics(arrays: dict[str, np.ndarray], action: str) -> dict[str, Any]:
    prefix = "round9_p_up" if action == "R9" else "round10_p_up"
    weights = arrays["weights_nm3"]
    y = arrays["Y6_1_E"]
    ycurl = arrays["Y6_1_curl_E"]
    e_delta = arrays[f"{prefix}_E"] - y
    curl_delta = (arrays[f"{prefix}_curl_E"] - ycurl)

    def norm(values: np.ndarray) -> float:
        return float(np.sqrt(np.dot(weights, np.sum(np.abs(values) ** 2, axis=1))))

    e = norm(e_delta)
    curl = norm(curl_delta)
    h = curl
    g = float(np.sqrt(np.dot(
        weights,
        np.sum(np.abs(e_delta) ** 2 + np.abs(curl_delta) ** 2, axis=1),
    )))
    metrics = {}
    for name, value in (
        ("E_total_code", e), ("E_scattered_code", e),
        ("curl_E_over_k0_code", curl),
        ("H_total_A_per_m", h), ("H_scattered_A_per_m", h),
    ):
        metrics[name] = {
            "difference_l2": value, "reference_l2": 0.0,
            "reference_norm_floor": 1.0,
            "relative_to_reference_or_floor": value,
        }
    metrics["G"] = {
        "difference_g_norm": g, "reference_g_norm": 0.0,
        "incident_g_norm_floor": 1.0, "relative_with_incident_floor": g,
    }
    return metrics


def _modal_rows() -> list[dict[str, Any]]:
    rows = []
    for key in v19.CHANNEL_KEYS:
        side, m, n, pol = key
        evanescent = key == ("top", 3, 5, "s")
        amp = [2.0, -0.5] if evanescent else [0.0, 0.0]
        rows.append({
            "side": side, "order_m": m, "order_n": n, "polarization": pol,
            "outgoing_amplitude_at_boundary": amp,
            "outgoing_amplitude": amp,
            "power_ratio": 0.0, "modal_power_code_units": 0.0,
            "R": 0.0, "T": 0.0, "propagating": not evanescent,
        })
    return rows


def _j_anchor(field_metrics: dict[str, Any]) -> dict[str, Any]:
    ratios = {
        "E_total_code": field_metrics["E_total_code"]["relative_to_reference_or_floor"],
        "E_scattered_code": field_metrics["E_scattered_code"]["relative_to_reference_or_floor"],
        "H_total_A_per_m": field_metrics["H_total_A_per_m"]["relative_to_reference_or_floor"],
        "H_scattered_A_per_m": field_metrics["H_scattered_A_per_m"]["relative_to_reference_or_floor"],
        "G": field_metrics["G"]["relative_with_incident_floor"],
    }
    components = {f"power.{name}": 0.0 for name in (
        "R_total", "T_total", "R00_s", "R00_p", "R00_total", "A_volume",
    )}
    components["power.max_individual_channel"] = 0.0
    for group in ("top_s", "top_p", "bottom_s", "bottom_p"):
        components[f"amplitude.{group}"] = 0.0
    for name, value in ratios.items():
        components[f"field.{name}"] = float(value) / 1.0e-4
    witness = max(components, key=components.__getitem__)
    return {"components": components, "value": components[witness], "witness": witness}


def _modal_metrics() -> dict[str, Any]:
    return {
        "power_absolute_differences": {
            "R_total": 0.0, "T_total": 0.0, "R00_s": 0.0,
            "R00_p": 0.0, "R00_total": 0.0, "A_volume": 0.0,
        },
        "maximum_individual_channel_power_ratio_absolute_difference": 0.0,
    }


def _source_fixture(tmp_path: Path) -> tuple[dict[str, Any], dict[str, Path]]:
    cells = _cells()
    r9_plan_rows = [
        {"lower": row["lower"], "upper": row["upper"], "degree": row["r9_p"]}
        for row in cells
    ]
    r10_plan_rows = [
        {"lower": row["lower"], "upper": row["upper"], "degree": row["r10_p"]}
        for row in reversed(cells)
    ]
    r9_plan = {"cell_interior_degrees": r9_plan_rows}
    r10_plan = {
        "cell_interior_degrees": r10_plan_rows,
        "base_config": {
            "grating_bounds": [0.0, 0.0, 0.0, 1.0, 1.0, 120.0],
            "interface_z": 0.0,
        },
    }
    arrays = _sample_arrays(2)
    field9 = _field_metrics(arrays, "R9")
    field10 = _field_metrics(arrays, "R10")
    modal_rows = _modal_rows()
    modal_anchor = _modal_metrics()
    r9_anchor = {
        "field_metrics": field9,
        "J_infinity": _j_anchor(field9),
        "modal_and_power_metrics": modal_anchor,
    }
    r10_anchor = {
        "field_metrics": field10,
        "J_infinity": _j_anchor(field10),
        "modal_and_power_metrics": modal_anchor,
    }
    records = {
        "r9_plan": r9_plan,
        "r10_plan": r10_plan,
        "r9_modal": {"orders": modal_rows},
        "r10_modal": {"orders": modal_rows},
        "y6_modal": {"orders": modal_rows},
        "r9_absorption": {"A_volume_total": 0.0},
        "r10_absorption": {"A_volume_total": 0.0},
        "y6_summary": {"official_result": {"volume_metrics": {"A_volume_total": 0.0}}},
        "r9_comparison": {
            "candidate_id": "R9", "selection_reference": "Y6_1",
            "field_metrics_vs_selection_reference": {"candidate": field9},
            "J_infinity": {"candidate": r9_anchor["J_infinity"]},
            "modal_and_power_metrics_vs_selection_reference": {"candidate": modal_anchor},
        },
        "r10_comparison": {
            "candidate_id": "R10", "parent_candidate_id": "R9", "selection_reference": "Y6_1",
            "field_metrics_vs_selection_reference": {"parent": field9, "candidate": field10},
            "J_infinity": {"parent": r9_anchor["J_infinity"], "candidate": r10_anchor["J_infinity"]},
            "modal_and_power_metrics_vs_selection_reference": {
                "parent": modal_anchor, "candidate": modal_anchor,
            },
        },
    }
    source_paths: dict[str, Path] = {}
    sources: dict[str, dict[str, str]] = {}
    for role, record in records.items():
        path = _write_json(tmp_path / "sources" / f"{role}.json", record)
        source_paths[role] = path
        sources[role] = {"path": str(path), "sha256": _sha(path)}
    manifest = {
        "schema": "task43.v20.test_fixture.v1",
        "sources": sources,
        "quadrature": {}, "cells": cells,
        "physics": {
            "k0_per_nm": 1.0,
            "magnetic_field_scale_a_per_m": 1.0,
            "incident_g_norm_floor": 1.0,
        },
        "epsilon_J": 0.1, "epsilon_G": 0.1, "delta_FE_historical": 8328,
    }
    return manifest, source_paths


def _archive_fixture(tmp_path: Path, order: int, label: str) -> dict[str, Any]:
    arrays = _sample_arrays(order)
    path = tmp_path / "quadrature" / f"{label}.npz"
    _save_npz(path, arrays)
    return {
        "path": str(path), "sha256": _sha(path),
        "sample_count": len(arrays["weights_nm3"]), "partition_boxes": 2,
        "axis_breakpoints_nm": [[0.0, 1.0], [0.0, 1.0], [-10.0, 0.0, 130.0]],
    }


def _main_fixture(tmp_path: Path) -> dict[str, Any]:
    manifest, _ = _source_fixture(tmp_path)
    manifest["quadrature"] = {
        "q8": _archive_fixture(tmp_path, 2, "q8"),
        "q10": _archive_fixture(tmp_path, 3, "q10"),
    }
    return {
        "manifest": manifest,
        "manifest_path": tmp_path / "contract.json",
        "output_root": tmp_path / "output",
        "orders": {"q8": 2, "q10": 3},
        "expected_volume_nm3": 140.0,
    }


def test_contract_loader_and_static_bundle_bind_actual_sources():
    path = v20.REPO_ROOT / v20.CONTRACT_RELATIVE_PATH
    manifest, digest, lock = v20._load_manifest(path)
    bundle = v20._load_source_bundle(
        manifest, v20._source_paths(manifest), lock,
    )
    assert len(digest) == 64
    assert len(bundle["cells"]) == 180
    assert len(bundle["modal"]["R10"]) == 612
    assert bundle["by_id"][8]["forest_root"] == 4
    assert bundle["by_id"][14]["forest_root"] == 34


def test_contract_rejects_duplicate_source_hash():
    manifest = v20._json_file(v20.REPO_ROOT / v20.CONTRACT_RELATIVE_PATH)
    altered = copy.deepcopy(manifest)
    roles = sorted(altered["sources"])
    altered["sources"][roles[1]]["sha256"] = altered["sources"][roles[0]]["sha256"]
    with pytest.raises(v20.EvidenceError, match="duplicate source hash"):
        v20._validate_contract(altered)


def test_contract_rejects_slot_and_launch_conflicts():
    manifest = v20._json_file(v20.REPO_ROOT / v20.CONTRACT_RELATIVE_PATH)
    bad_slot = copy.deepcopy(manifest)
    bad_slot["slots"]["D1"]["root"] = bad_slot["slots"]["D2"]["root"]
    with pytest.raises(v20.EvidenceError, match="fixed path/condition/budget"):
        v20._validate_contract(bad_slot)
    bad_launch = copy.deepcopy(manifest)
    bad_launch["launch_files"][0] = copy.deepcopy(bad_launch["launch_files"][1])
    with pytest.raises(v20.EvidenceError, match="launch path inventory"):
        v20._validate_contract(bad_launch)


def test_npz_loader_reads_only_allowlisted_members(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    record = _archive_fixture(tmp_path, 2, "reader")
    order3 = _archive_fixture(tmp_path, 3, "reader_order3")
    opened: list[str] = []
    original_open = zipfile.ZipFile.open

    def recording_open(archive: zipfile.ZipFile, name: Any, *args: Any, **kwargs: Any):
        member = name.filename if isinstance(name, zipfile.ZipInfo) else str(name)
        if member in {f"{x}.npy" for x in v20.FORBIDDEN_ARRAYS}:
            raise AssertionError(f"forbidden member was opened: {member}")
        opened.append(member)
        return original_open(archive, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "open", recording_open)
    arrays, metadata = v20.read_saved_archive(record, fixture=True)
    assert set(arrays) == v20.ALLOWED_ARRAYS
    assert set(opened) == {f"{name}.npy" for name in v20.ALLOWED_ARRAYS}
    assert metadata["unread_control_members"] == sorted(v20.FORBIDDEN_ARRAYS)
    assert all(name not in opened for name in (f"{x}.npy" for x in v20.FORBIDDEN_ARRAYS))
    rebound_wrong_order = dict(record, path=order3["path"], sha256=order3["sha256"])
    with pytest.raises(v20.EvidenceError, match="dtype/shape mismatch"):
        v20.read_saved_archive(rebound_wrong_order, fixture=True)
    arrays3, _ = v20.read_saved_archive(order3, fixture=True)
    with pytest.raises(v20.EvidenceError, match=r"exactly q\^3 points per box"):
        v20._partition_owner(
            arrays3["points_nm"], order3["axis_breakpoints_nm"], 2,
            order3["partition_boxes"],
        )


def test_half_open_owner_mapping_and_weight_checks():
    cells = [
        {"global_cell_id": 8, "lower": [0.0, 0.0, 0.0], "upper": [1.0, 1.0, 1.0]},
        {"global_cell_id": 0, "lower": [1.0, 0.0, 0.0], "upper": [2.0, 1.0, 1.0]},
    ]
    points = np.asarray([[0.5, 0.5, 0.5], [1.0, 0.5, 0.5], [1.5, 0.5, 0.5], [2.0, 0.5, 0.5]])
    weights = np.asarray([1.0, 0.2, 0.3, 0.5])
    slots, record = v20.map_points_to_cells(points, weights, cells, expected_volume=2.0)
    assert record["point_owner_global_ids"].tolist() == [8, 0, 0, 0]
    assert slots.tolist() == [0, 1, 1, 1]
    partition_points = np.asarray([[0.5, 0.5, 0.5], [1.0, 0.5, 0.5]])
    partition = v20._partition_owner(partition_points, [[0.0, 1.0, 2.0], [0.0, 1.0], [0.0, 1.0]], 1, 2)
    assert partition["box_indices"].tolist() == [0, 1]
    assert partition["boundary_coordinate_hits"] == 1


def test_owner_rejects_duplicate_hole_and_wrong_weight():
    cells = [
        {"global_cell_id": 0, "lower": [0.0, 0.0, 0.0], "upper": [1.0, 1.0, 1.0]},
        {"global_cell_id": 1, "lower": [1.0, 0.0, 0.0], "upper": [2.0, 1.0, 1.0]},
    ]
    points = np.asarray([[0.5, 0.5, 0.5], [1.5, 0.5, 0.5]])
    weights = np.asarray([1.0, 1.0])
    with pytest.raises(v20.EvidenceError, match="duplicate cell box"):
        v20.map_points_to_cells(points, weights, [cells[0], cells[0]], expected_volume=2.0)
    hole = [cells[0], {**cells[1], "lower": [1.25, 0.0, 0.0]}]
    with pytest.raises(v20.EvidenceError, match="complete nonoverlapping Cartesian partition"):
        v20.map_points_to_cells(points, weights, hole, expected_volume=2.0)
    with pytest.raises(v20.EvidenceError, match="volume differs"):
        v20.map_points_to_cells(points, np.asarray([2.0, 2.0]), cells, expected_volume=4.0)


def test_cells_bind_geometry_not_plan_row_and_freeze_degree_counts():
    cells = _cells()
    r9 = {"cell_interior_degrees": [
        {"lower": cell["lower"], "upper": cell["upper"], "degree": cell["r9_p"]}
        for cell in cells
    ]}
    r10 = {"cell_interior_degrees": [
        {"lower": cell["lower"], "upper": cell["upper"], "degree": cell["r10_p"]}
        for cell in reversed(cells)
    ]}
    mapped, by_id, _ = v20._validate_plan_cells(cells, r9, r10, fixture=True)
    assert [row["global_cell_id"] for row in mapped] == [0, 1]
    assert by_id[0]["r10_p"] == 6 and by_id[1]["r10_p"] == 6
    wrong = copy.deepcopy(r10)
    wrong["cell_interior_degrees"][0]["lower"] = [0.25, 0.0, 0.0]
    with pytest.raises(v20.EvidenceError, match="geometry box"):
        v20._validate_plan_cells(cells, r9, wrong, fixture=True)


def test_response_decomposition_identity_and_location_rule(tmp_path: Path):
    arrays = _sample_arrays(1)
    cells = _cells()
    slots, _ = v20.map_points_to_cells(
        arrays["points_nm"], arrays["weights_nm3"], cells, expected_volume=140.0,
    )
    terms = v20._response_decomposition(arrays, arrays["weights_nm3"], slots, 2, 1.0)
    maxima = v20._assert_response_identities(terms)
    assert terms["R9"]["G"]["B10"].tolist() == terms["R9"]["G"]["B"].tolist()
    assert terms["R10"]["G"]["B10"].tolist() == pytest.approx([2.5, 32.5])
    assert max(maxima.values()) <= v20.IDENTITY_REL_TOL
    tie_rank = v20._rank_cells([9, 3], np.asarray([1.0, 1.0]), np.asarray([1.0, 1.0]), [9, 3])
    assert tie_rank["complete_ranking"][0]["global_cell_id"] == 3
    assert tie_rank["q8_q10_location_stability"]["location_stable"] is True
    zero = v20._rank_cells([0, 1], np.zeros(2), None, None)
    assert zero["complete_ranking"] == []
    one_zero = v20._rank_cells([0, 1], np.asarray([1.0, 1.0]), np.zeros(2), [0, 1])
    assert one_zero["q8_q10_location_stability"]["status"] == "UNRESOLVED_ZERO_Q8_TOTAL"

    location_rank = v20._rank_cells([0, 1], np.asarray([1.0, 1.0]), np.asarray([1.0, 1.0]), [0, 1])
    q8 = {"remaining_error_location": location_rank}
    q10 = {"remaining_error_location": location_rank}
    plan = {"base_config": {"grating_bounds": [0, 0, 0, 1, 1, 120], "interface_z": 0}}
    proposal = v20._location_proposal(q8, q10, cells, 1.0, plan)
    assert proposal["proposed_cell"]["global_cell_id"] == 0
    assert proposal["proposed_cell"]["geometry_relation"]["interface_z_nm"] == 0.0


def test_modal_j_replay_reproduces_612_channel_anchor(tmp_path: Path):
    manifest, paths = _source_fixture(tmp_path)
    bundle = v20._load_source_bundle(manifest, paths, None, fixture=True)
    arrays = _sample_arrays(2)
    field = v20._field_and_j_replay(arrays, bundle, arrays["weights_nm3"], manifest["physics"])
    for action in ("R9", "R10"):
        assert field[action]["J_replay"]["value"] == pytest.approx(bundle["anchors"][action]["J_infinity"]["value"])
        assert len(field[action]["J_replay"]["components"]) == 16
    rows, replay = v20._modal_rows(bundle["modal"], bundle["anchors"], bundle["absorption"])
    assert len(rows) == 612
    evanescent = next(row for row in rows if (row["side"], row["m"], row["n"], row["polarization"]) == ("top", 3, 5, "s"))
    assert (evanescent["R10_amplitude_real"] ** 2 + evanescent["R10_amplitude_imag"] ** 2) ** 0.5 > 0.0
    assert evanescent["R10_power_ratio"] == 0.0

    altered = copy.deepcopy(bundle["modal"])
    key = ("top", 3, 5, "s")
    altered["R9"][key]["power_ratio"] = 2.0e-6
    altered["R10"][key]["power_ratio"] = 3.0e-6
    anchors = copy.deepcopy(bundle["anchors"])
    for action, value in (("R9", 2.0e-6), ("R10", 3.0e-6)):
        anchors[action]["modal_and_power_metrics"]["maximum_individual_channel_power_ratio_absolute_difference"] = value
    _, changed = v20._modal_rows(altered, anchors, bundle["absorption"])
    assert changed["R9"]["channel_exceedance_count"] == 1
    assert changed["R10"]["channel_exceedance_count"] == 1
    assert changed["R9"]["channels_exceeding_threshold"][0]["absolute_difference"] == pytest.approx(2.0e-6)

    wrong_reference = copy.deepcopy(manifest)
    wrong_source = copy.deepcopy(v20._json_file(paths["r10_comparison"]))
    wrong_source["selection_reference"] = "R9"
    wrong_path = _write_json(tmp_path / "sources" / "wrong_direction.json", wrong_source)
    wrong_reference["sources"]["r10_comparison"] = {
        "path": str(wrong_path), "sha256": _sha(wrong_path),
    }
    with pytest.raises(v20.EvidenceError, match="reference is not Y6_1"):
        v20._load_source_bundle(
            wrong_reference, v20._source_paths(wrong_reference, fixture=True), None, fixture=True,
        )


def test_main_microfixture_writes_q8_q10_and_terminal(tmp_path: Path):
    fixture = _main_fixture(tmp_path)
    final = v20.main(_test_fixture=fixture)
    root = fixture["output_root"]
    run = v20._json_file(root / "run_manifest.json")
    terminal = v20._json_file(root / "terminal.json")
    assert final["status"] == run["status"] == terminal["status"] == "COMPLETE"
    assert set(run["orders"]) == {"q8", "q10"}
    assert len(final["orders"]["q8"]["modal_power_replay"]) == 2
    assert len(final["orders"]["q8"]["z_layer_summaries"]) == 2
    assert "positive_negative_I" in final["orders"]["q10"]["degree_summaries"]["p5_to_p6"]
    assert (root / "q8" / "cells.csv").is_file()
    assert (root / "q10" / "modes_612.csv").is_file()
    science = run["science_summary"]["delta_J_G_per_historical_delta_FE"]
    assert science["J_improvement_exceeds_epsilon"] is True
    assert science["delta_G_resolution_by_saved_q"]["q8"]["improvement_exceeds_epsilon"] is True
    assert len(science["J_per_historical_delta_FE_interval_from_epsilon"]) == 2
    assert final["terminal_sha256"] == _sha(root / "terminal.json")


def test_main_mid_write_failure_preserves_q8_and_marks_incomplete(tmp_path: Path):
    fixture = _main_fixture(tmp_path)
    before: dict[str, Any] = {}

    def fail_after_q10_cells(label: str, stage: str, root: Path) -> None:
        if (label, stage) == ("q8", "after_persist"):
            before["q8"] = {
                relative: _sha(root / relative)
                for relative in (
                    "q8/diagnostic.json", "q8/cells.csv", "q8/modes_612.csv",
                )
            }
            before["inputs"] = v20._capture_inputs(
                fixture["manifest_path"], fixture["manifest"],
                v20._source_paths(fixture["manifest"], fixture=True), fixture=True,
            )
        if (label, stage) == ("q10", "after_cells_csv"):
            after_inputs = v20._capture_inputs(
                fixture["manifest_path"], fixture["manifest"],
                v20._source_paths(fixture["manifest"], fixture=True), fixture=True,
            )
            assert after_inputs == before["inputs"]
            assert {relative: _sha(root / relative) for relative in before["q8"]} == before["q8"]
            raise OSError("injected mid-write failure")

    fixture["failure_hook"] = fail_after_q10_cells
    with pytest.raises(OSError, match="injected mid-write failure"):
        v20.main(_test_fixture=fixture)
    root = fixture["output_root"]
    run = v20._json_file(root / "run_manifest.json")
    assert run["status"] == "FAILED_INCOMPLETE"
    assert run["orders"]["q8"]["status"] == "COMPLETE"
    assert (root / "q8" / "modes_612.csv").is_file()
    assert (root / "q10" / "cells.csv").is_file()
    assert not (root / "q10" / "modes_612.csv").exists()
    assert not (root / "terminal.json").exists()


def test_terminal_refuses_incomplete_order(tmp_path: Path):
    with pytest.raises(v20.EvidenceError, match="both q8 and q10"):
        v20._terminal_payload({"orders": {"q8": {}}}, tmp_path)

