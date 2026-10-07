from __future__ import annotations

import hashlib
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.io import load_and_resolve


ROOT = Path(__file__).resolve().parents[2]
INPUT_ROOT = ROOT / "input/task40extra_0p7nm_engineering"
CASES = (
    (
        "nonseparable_gx560_p6_reference_v16.dat",
        "nonseparable_gx560_p6_reference_v15.dat",
        "task40extra_v16_p6_y_orbit_gx560_reference_v1",
        "task40extra_0p7nm_nonseparable_gx560_p6_reference_v16",
        "GX560",
        (560, 252000, 340, (68, 68, 136, 68), (204, 136)),
    ),
    (
        "nonseparable_e1_p6_reference_v16.dat",
        "nonseparable_e1_p6_reference_v15.dat",
        "task40extra_v16_p6_y_orbit_e1_reference_v1",
        "task40extra_0p7nm_nonseparable_e1_p6_reference_v16",
        "E1",
        (760, 342000, 588, (84, 168, 168, 168), (252, 336)),
    ),
)


@pytest.mark.parametrize("filename,physical_filename,profile_name,run_id,grid,expected", CASES)
def test_v16_profile_facts_input_validation_and_checker_inventory(
    filename, physical_filename, profile_name, run_id, grid, expected
):
    selected = load_and_resolve(INPUT_ROOT / filename).as_jsonable()
    reference = load_and_resolve(INPUT_ROOT / physical_filename).as_jsonable()
    from src.geometry.task40_nonseparable_plan import TASK40_Q_ASSEMBLY_BOUNDED_V16
    from src.io.physical_intermediate_profile import profile_facts
    from src.runners.task40_v10_output_checker import _registered_v15_profile_inventory
    from src.solvers.task40_v10_p6_periodic_profile import TASK40_P6_PERIODIC_PROFILES

    facts = profile_facts(profile_name)
    assert selected["run_id"] == run_id
    assert selected["solver"]["preconditioner"] == profile_name
    assert selected["solver"]["task40_q_assembly_strategy"] == TASK40_Q_ASSEMBLY_BOUNDED_V16
    assert selected["solver"]["task40_reference_pc_strategy"] == (
        "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15"
    )
    assert selected["derived"]["physical_intermediate_profile"] == facts
    assert facts["input_path"] == f"input/task40extra_0p7nm_engineering/{filename}"
    assert facts["q_assembly_strategy"] == TASK40_Q_ASSEMBLY_BOUNDED_V16
    assert facts["stage"] == "Q4_ORIGINAL"
    for section in ("geometry", "materials", "incidence", "boundary"):
        assert selected[section] == reference[section]

    cells, interiors, modes, q_ports, sector_ports = expected
    periodic = TASK40_P6_PERIODIC_PROFILES[profile_name]
    assert periodic.global_cell_count == cells
    assert periodic.global_interior_rows == interiors
    assert periodic.mode_count == modes == sum(q_ports)
    assert periodic.q_port_counts == q_ports
    assert periodic.sector_port_counts == sector_ports
    inventory = _registered_v15_profile_inventory(profile_name)
    assert inventory["global_interior_rows"] == interiors
    assert inventory["mode_count"] == modes
    assert inventory["q_port_counts"] == q_ports
    assert inventory["sector_port_counts"] == sector_ports


@pytest.mark.parametrize("filename,physical_filename,profile_name,run_id,grid,expected", CASES)
def test_v16_worker_contract_accepts_only_the_registered_bounded_route(
    filename, physical_filename, profile_name, run_id, grid, expected
):
    del physical_filename, run_id, grid, expected
    from src.io.physical_intermediate_profile import profile_facts
    from src.runners import task40_v10_worker
    from src.runners.physical_v14_budget import V14_TIME_POLICY_ENFORCE

    payload = load_and_resolve(INPUT_ROOT / filename).as_jsonable()
    window_sha = "a" * 64
    runtime = SimpleNamespace(
        stage="Q4_ORIGINAL",
        campaign_context={
            "read_only": True,
            "window_path": "fixed-window.json",
            "window_sha256": window_sha,
            "accounting_path": "accounting.json",
        },
        shared_budget={"campaign_window_sha256": window_sha},
        workflow_reserved_seconds=1000.0,
        require_zero_swap=True,
        _ledger_path=None,
        time_policy=V14_TIME_POLICY_ENFORCE,
    )
    contract = task40_v10_worker._candidate_contract(
        payload,
        profile_facts(profile_name),
        runtime,
        profile_identity=profile_name,
    )
    assert contract["schema"] == "task40extra.review_v16_p6_reference_worker_contract.v1"
    assert all(contract["checks"].values())

    payload["solver"]["task40_q_assembly_strategy"] = "LEGACY_GLOBAL_CSR_SUM"
    with pytest.raises(ValueError, match="does not support"):
        task40_v10_worker._candidate_contract(
            payload,
            profile_facts(profile_name),
            runtime,
            profile_identity=profile_name,
        )


@pytest.mark.parametrize("filename,physical_filename,profile_name,run_id,grid,expected", CASES)
def test_v16_dispatcher_calls_worker_with_exact_identity(
    monkeypatch, tmp_path: Path, filename, physical_filename, profile_name, run_id, grid, expected
):
    from src.runners import task038_full3d_iterative, task40_v10_worker
    from src.geometry.task40_nonseparable_plan import TASK40_Q_ASSEMBLY_BOUNDED_V16

    del physical_filename, grid, expected
    payload = load_and_resolve(INPUT_ROOT / filename).as_jsonable()
    captured = {}

    def fake_worker(resolved, run_directory, **kwargs):
        del run_directory
        captured["run_id"] = resolved["run_id"]
        captured["profile_identity"] = kwargs["profile_identity"]
        captured["q_assembly_strategy"] = resolved["solver"]["task40_q_assembly_strategy"]
        return {"status": "dispatch_fixture_pass"}

    monkeypatch.setattr(task40_v10_worker, "run_task40_v10_p6_reference_worker", fake_worker)
    result = task038_full3d_iterative.run_full3d_iterative(
        payload, tmp_path, source_sha="f" * 40
    )
    assert result == {"status": "dispatch_fixture_pass"}
    assert captured == {
        "run_id": run_id,
        "profile_identity": profile_name,
        "q_assembly_strategy": TASK40_Q_ASSEMBLY_BOUNDED_V16,
    }


@pytest.mark.parametrize("filename,physical_filename,profile_name,run_id,grid,expected", CASES)
def test_v16_qualified_abi_helper_accepts_only_registered_profiles(
    filename, physical_filename, profile_name, run_id, grid, expected
):
    del filename, physical_filename, run_id, grid, expected
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        pytest.skip("requires the existing qualified local Task40 ABI activation")
    from src.runners.task40_v10_abi import qualified_task40_v10_abi

    facts = qualified_task40_v10_abi(profile_identity=profile_name)
    assert facts["qualification"] == "task40_v10_exact_profile_receipt_bound"
    assert facts["profile_identity"] == profile_name
    assert facts["scalar"] == "complex128"
    assert facts["integer"] == "int32"
    assert facts["mpi_size"] == 1


@pytest.mark.parametrize("filename,physical_filename,profile_name,run_id,grid,expected", CASES)
def test_v16_run_case_main_reaches_launcher_with_fixed_window(
    monkeypatch, tmp_path: Path, capsys,
    filename, physical_filename, profile_name, run_id, grid, expected,
):
    from scripts import run_case
    from src.runners import task038_launcher

    del physical_filename, grid, expected
    captured = {}

    def fake_launcher(specification, **kwargs):
        captured["run_id"] = specification.identity["run_id"]
        captured["profile"] = specification.solver["preconditioner"]
        captured["reference_pc_strategy"] = specification.solver[
            "task40_reference_pc_strategy"
        ]
        captured["q_assembly_strategy"] = specification.solver[
            "task40_q_assembly_strategy"
        ]
        captured["campaign_window"] = kwargs["task40_v10_campaign_window"]
        return {"result_classification": "worker_exit0"}

    monkeypatch.setattr(task038_launcher, "launch_specification", fake_launcher)
    window = tmp_path / "fixed-window.json"
    result = run_case.main([
        str(INPUT_ROOT / filename),
        "--task40-v10-campaign-window",
        str(window),
    ])
    capsys.readouterr()
    assert result == 0
    assert captured == {
        "run_id": run_id,
        "profile": profile_name,
        "reference_pc_strategy": "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15",
        "q_assembly_strategy": "BOUNDED_STAGING_CSR_V16",
        "campaign_window": window,
    }


def _v16_allocation_ledger_fixture(tmp_path: Path, lines: bytes):
    from src.runners.task40_v10_output_checker import (
        _verify_v16_allocation_admission_ledger,
    )

    path = tmp_path / "v16_events.jsonl"
    path.write_bytes(lines)
    records = lines.splitlines(keepends=True)
    admission_count = sum(
        b'"event":"v10_strict_allocation_admission"' in line
        for line in records
    )
    completion_count = sum(
        b'"event":"v10_strict_allocation_admission_complete"' in line
        for line in records
    )
    summary = {
        "allocation_admission_raw": {
            "path": path.name,
            "size_bytes": len(lines),
            "sha256": hashlib.sha256(lines).hexdigest(),
            "record_count": len(records),
            "allocation_admission_event_count": admission_count,
            "allocation_admission_complete_event_count": completion_count,
        },
        "allocation_gate_invocation_count": admission_count,
        "status": "PASS",
        # The checker must derive the decision from the raw file even if this
        # cached worker flag claims success.
        "allocation_admission_raw_validation": {"passed": True},
    }
    return path, summary, _verify_v16_allocation_admission_ledger


def test_v16_raw_ledger_checker_rejects_missing_file_and_count_mismatch(
    tmp_path: Path,
):
    good = (
        b'{"event":"v10_strict_allocation_admission"}\n'
        b'{"event":"v10_strict_allocation_admission_complete"}\n'
    )
    path, summary, verify = _v16_allocation_ledger_fixture(tmp_path, good)
    assert verify(tmp_path, summary)["passed"] is True

    path.unlink()
    with pytest.raises(FileNotFoundError):
        verify(tmp_path, summary)

    incomplete = b'{"event":"v10_strict_allocation_admission"}\n'
    _, summary, verify = _v16_allocation_ledger_fixture(tmp_path, incomplete)
    with pytest.raises(ValueError, match="counts do not match"):
        verify(tmp_path, summary)
