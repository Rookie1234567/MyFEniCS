"""V6 entry and evidence metadata; no numerical operator is constructed."""
from pathlib import Path

import pytest

from benchmarks.physical_intermediate_checker import _retained_full_reference_required
from scripts.run_case import main
from src.io import load_and_resolve
from src.io.native_capacity_profile import native_profile_facts
from src.runners.task038_launcher import _base_manifest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("case", ["5nm_full", "2nm_h6_only", "2nm_pilot16"])
def test_v6_manifest_matches_interleave_policy_and_disabled_screen(case, tmp_path):
    specification = load_and_resolve(
        ROOT / f"input/task39extra_para_workstation_capacity/v6_{case}.dat"
    )
    facts = native_profile_facts(specification.solver["preconditioner"])
    execution = facts["native_execution"]
    assert execution["memory_policy"] == execution["native_memory_policy"] == "interleave_nodes0_1"
    manifest = _base_manifest(
        specification,
        run_directory=tmp_path,
        source_sha="1" * 40,
        adapter_identity="task038.full3d_iterative",
        start_time="2026-10-02T00:00:00Z",
        resolved_sha="2" * 64,
    )
    contract = manifest["native_capacity_contract"]
    assert contract["screen"]["enabled"] is False
    assert contract["screen"]["notch_policy"] == "disabled_by_profile"
    assert contract["native_execution"]["native_memory_policy"] == "interleave_nodes0_1"


@pytest.mark.parametrize(
    "classification, exit_status, expected",
    [
        ("h6_only", 0, 0),
        ("pilot_16", 0, 0),
        ("worker_exit0", 0, 0),
        ("h6_only", 137, 3),
        ("pilot_16", 1, 3),
        ("worker_exit0", 137, 3),
        ("h6_only", None, 3),
        ("EVIDENCE_INCOMPLETE", 0, 3),
    ],
)
def test_native_public_entry_requires_successful_scope_and_real_exit0(
    classification, exit_status, expected, monkeypatch, capsys
):
    import src.runners.native_capacity as native

    monkeypatch.setattr(
        native,
        "launch_native_capacity",
        lambda _spec: {"result_classification": classification, "exit_status": exit_status},
    )
    assert main([str(ROOT / "input/task39extra_para_workstation_capacity/v6_2nm_h6_only.dat")]) == expected
    assert classification in capsys.readouterr().out


@pytest.mark.parametrize(
    "identity, required",
    [
        ("dual_condensed_balh_native_5nm_v3", True),
        ("dual_condensed_balh_native_5nm_v5", True),
        ("dual_condensed_balh_native_5nm_v6", True),
        ("dual_condensed_balh_native_2nm_pilot16_v6", False),
        ("dual_condensed_balh_native_13p5_q4_v5", False),
        ("unknown", False),
    ],
)
def test_v6_5nm_keeps_full_reference_authority(identity, required):
    assert _retained_full_reference_required(identity) is required
