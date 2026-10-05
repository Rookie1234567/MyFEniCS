"""New input/clock/coverage logic only; no mode generation or FE execution."""

import datetime
import hashlib
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import numpy as np
import pytest

from src.io.finite_json import atomic_json
from src.io.w1_evidence import file_receipt
from src.io.w1_receiver_contract import (
    LEDGERS,
    MATH_COMMIT,
    load_w1,
    validate_originals,
)
from src.io.w1_reproduced_input import (
    ANCHOR_PATH,
    SOURCE_INPUT,
    anchor_bodies,
    canonical_sha,
    validate_receipt,
)
from src.runners.w1_component_receiver import prepare_B_window, remaining
from src.runners.w1_component_payload import required_oracle_frequencies
from src.runners.w1_input_recovery import selected_functions

ROOT = Path(__file__).resolve().parents[2]


def receipt_fixture(tmp_path):
    folder = tmp_path / "benchmarks/artifacts/task42extra/w1_receiver"
    folder.mkdir(parents=True)
    manifest = folder / "manifest.json"
    manifest.write_text('{"fixture_only":true}\n')
    anchor = subprocess.check_output(
        ["git", "show", MATH_COMMIT + ":" + ANCHOR_PATH], cwd=ROOT
    )
    physical, inventory = anchor_bodies(json.loads(anchor))
    required = [
        SOURCE_INPUT,
        ANCHOR_PATH,
        "src/common/modes_3d.py",
        "src/solvers/fullspace_dtn_action.py",
        "src/solvers/dtn_port_3d.py",
        "benchmarks/run_task40_v5_target_ledger.py",
    ]
    files = []
    originals = {}
    for name in required:
        raw = subprocess.check_output(
            ["git", "show", MATH_COMMIT + ":" + name], cwd=ROOT
        )
        originals[name] = raw
        files.append(
            {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        )
    candidate = {
        "status": "BITWISE_REPRODUCED_INPUT_PENDING_RECEIPT",
        "generation_count": 1,
        "target_mode_physical_identity": physical,
        "original_size_ordered_mode_inventory_identity": inventory,
    }
    atomic_json(folder / "candidate.json", candidate)
    atomic_json(
        folder / "binding.json",
        {"stage": "input_recovery", "receiver_source_sha": "a" * 40},
    )
    supervision = {
        "classification": "COMPLETED",
        "leader_exit_code": 0,
        "descendants_cleared": True,
        "remaining_child_pids": [],
        "sampled_process_tree_swap_peak_bytes": 0,
        "rss_hard_limit_bytes": 2 * 2**30,
    }
    atomic_json(folder / "supervision.json", supervision)
    value = {
        **candidate,
        "schema": "w1-reproduced-input-receipt.v1",
        "status": "BITWISE_REPRODUCED_INPUT",
        "math_commit": MATH_COMMIT,
        "historical_ledger_recovered": False,
        "PDE_solved": False,
        "generated_utc": "2026-10-05T00:00:00+00:00",
        "receiver_source_sha": "a" * 40,
        "manifest": file_receipt(manifest),
        "binding": file_receipt(folder / "binding.json"),
        "candidate": file_receipt(folder / "candidate.json"),
        "supervision": file_receipt(folder / "supervision.json"),
        "git_sources": files,
    }
    path = folder / "receipt.json"
    atomic_json(path, value)
    expected = {
        "manifest": value["manifest"]["sha256"],
        "bytes": manifest.stat().st_size,
        "physical": canonical_sha(physical),
        "inventory": canonical_sha(inventory),
    }
    return path, manifest, value, expected, originals


def validate_fixture(mp, tmp_path, path, manifest, expected, originals):
    def original_blob(args, **kwargs):
        return originals[args[2].split(":", 1)[1]]

    mp.setattr("src.io.w1_reproduced_input.subprocess.check_output", original_blob)
    return validate_receipt(
        path, manifest, root=tmp_path, math_commit=MATH_COMMIT, expected=expected
    )


def test_recovery_origin_disjoint_from_legacy():
    original = dict(LEDGERS)
    for stage in ("input_recovery", "control", "boundary", "boundary_check"):
        spec = load_w1(ROOT / f"input/task042extra_feinn_5nm/v26_rb_{stage}.dat")
        assert spec["input_origin"] == "bitwise_reproduced_v26"
        assert "reproduced_input_receipt" in spec["ledger_path"]
    assert LEDGERS == original and len(LEDGERS) == 2


@pytest.mark.parametrize(
    "field,value",
    [
        ("classification", "RSS_HARD_STOP"),
        ("leader_exit_code", 137),
        ("descendants_cleared", False),
        ("remaining_child_pids", [99]),
        ("sampled_process_tree_swap_peak_bytes", 1),
    ],
)
def test_reproduced_receipt_rejects_false_supervision(
    tmp_path, monkeypatch, field, value
):
    path, manifest, receipt, expected, originals = receipt_fixture(tmp_path)
    assert (
        validate_fixture(monkeypatch, tmp_path, path, manifest, expected, originals)[
            "status"
        ]
        == "BITWISE_REPRODUCED_INPUT"
    )
    supervision_path = Path(receipt["supervision"]["path"])
    summary = json.loads(supervision_path.read_text())
    summary[field] = value
    atomic_json(supervision_path, summary)
    receipt["supervision"] = file_receipt(supervision_path)
    atomic_json(path, receipt)
    with pytest.raises(ValueError, match="CLEARED_SUPERVISION"):
        validate_fixture(monkeypatch, tmp_path, path, manifest, expected, originals)


@pytest.mark.parametrize(
    "damage",
    ["physical", "source", "false_legacy", "candidate", "manifest", "missing_source"],
)
def test_reproduced_receipt_rejects_identity_and_source(tmp_path, monkeypatch, damage):
    path, manifest, value, expected, originals = receipt_fixture(tmp_path)
    if damage == "physical":
        value["target_mode_physical_identity"]["wavelength_nm"] = 0.8
    elif damage == "source":
        value["git_sources"][0]["sha256"] = "0" * 64
    elif damage == "false_legacy":
        value["historical_ledger_recovered"] = True
    elif damage == "candidate":
        p = Path(value["candidate"]["path"])
        doc = json.loads(p.read_text())
        doc["generation_count"] = 2
        atomic_json(p, doc)
        value["candidate"] = file_receipt(p)
    elif damage == "manifest":
        manifest.write_text('{"fixture_only":false}')
        value["manifest"] = file_receipt(manifest)
    else:
        value["git_sources"] = []
    atomic_json(path, value)
    with pytest.raises(ValueError):
        validate_fixture(monkeypatch, tmp_path, path, manifest, expected, originals)


def test_RB_window_does_not_reset(tmp_path):
    utc = datetime.datetime.now(datetime.timezone.utc)
    window = {
        "schema": "task42extra.w1-receiver-RB-window.v26",
        "budget_seconds": 10800,
        "numerical_and_checker_budget_seconds": 7200,
        "delivery_reserve_seconds": 1800,
        "old_windows_not_reset": True,
        "deadline_monotonic": 12000,
        "deadline_utc": (utc + datetime.timedelta(seconds=1000)).isoformat(),
        "input_binding_file": str(tmp_path / "inputs.json"),
    }
    path = tmp_path / "window.json"
    atomic_json(path, window)
    qualification = tmp_path / "qualification.json"
    qualification.write_text("{}")
    from src.io.w1_receiver_contract import digest

    original = {"received": True, "manifest_sha256": "fixed"}
    atomic_json(
        window["input_binding_file"],
        {
            "window_sha256": digest(path),
            "original_inputs": original,
            "A_qualification_sha256": digest(qualification),
        },
    )
    before = path.read_bytes()
    import unittest.mock

    with unittest.mock.patch(
        "src.runners.w1_component_receiver.remaining", return_value=1000
    ):
        prepare_B_window(
            {
                "window_path": str(path),
                "stage": "control",
                "A_qualification_path": str(qualification),
            },
            original,
        )
    assert before == path.read_bytes()
    assert remaining(window, now=11000, utc_now=utc) == pytest.approx(1000)
    with pytest.raises(ValueError, match="IMMUTABLE_INPUT"):
        with unittest.mock.patch(
            "src.runners.w1_component_receiver.remaining", return_value=1000
        ):
            prepare_B_window(
                {
                    "window_path": str(path),
                    "stage": "control",
                    "A_qualification_path": str(qualification),
                },
                {"received": True},
            )


def test_complete_frequency_coverage(tmp_path, monkeypatch):
    import sys
    from collections.abc import Mapping

    source = subprocess.check_output(
        ["git", "show", MATH_COMMIT + ":src/solvers/directional_boundary.py"], cwd=ROOT
    )
    p = tmp_path / "fixed_directional_boundary.py"
    p.write_bytes(source)
    namespace = {"Mapping": Mapping}
    selected_functions(p, ["zvalue"], namespace)
    monkeypatch.setitem(
        sys.modules,
        "src.solvers.directional_boundary",
        SimpleNamespace(zvalue=namespace["zvalue"]),
    )
    layout = SimpleNamespace(x=np.linspace(0, 2, 273), y=np.linspace(0, 1, 5))
    modes = [
        {
            "k_vector": [
                {"real": float(i), "imag": 0},
                {"real": float(3 * i + 1), "imag": 0},
                {"real": 0, "imag": 0},
            ]
        }
        for i in range(11)
    ]
    expected = {0.0}
    for row in modes:
        for axis, width in (
            (0, layout.x[101] - layout.x[100]),
            (1, layout.y[2] - layout.y[1]),
        ):
            expected.add(row["k_vector"][axis]["real"] * width)
    assert required_oracle_frequencies(modes, layout) == sorted(expected)
    assert len(expected) > 6


def test_recovery_pending_cannot_start_B(tmp_path):
    spec = load_w1(ROOT / "input/task042extra_feinn_5nm/v26_rb_control.dat")
    spec.update(
        manifest_path=str(tmp_path / "missing_manifest"),
        ledger_path=str(tmp_path / "missing_receipt"),
    )
    assert validate_originals(spec)["received"] is False
    assert validate_originals(spec)["status"] == "NOT_RUN_INPUT_UNAVAILABLE"


def test_frozen_named_metadata_exports_no_top_level_campaign(tmp_path):
    path = tmp_path / "original.py"
    path.write_text('raise RuntimeError("CAMPAIGN")\ndef f(x):\n    return x + 2\n')
    namespace = {}
    selected_functions(path, ["f"], namespace)
    assert namespace["f"](3) == 5
    with pytest.raises(ValueError):
        selected_functions(path, ["missing"], {})
