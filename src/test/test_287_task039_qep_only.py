from pathlib import Path
from types import SimpleNamespace

from benchmarks import task039_qep_only
from benchmarks.task039_v3_7_watchdog import (
    V3_7_QEP_ONLY_WORKER_MODULE,
    V3_7_ABSOLUTE_HARD_BYTES,
    build_v3_7_execution_plan,
)


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "input/official/task039/5nm_p6h5_v3_1deg_hybrid_direct_m480_mpi8.dat"


def test_qep_only_plan_routes_authenticated_mpi8_worker(tmp_path: Path):
    plan = build_v3_7_execution_plan(
        INPUT,
        tmp_path / "qep-only",
        source_sha="a" * 40,
        python_executable="/qualified/bin/python",
        mpiexec_command="/usr/bin/mpiexec",
        qep_only=True,
    )
    assert plan["argv"][1:3] == ["-n", "8"]
    assert plan["argv"][5] == V3_7_QEP_ONLY_WORKER_MODULE
    assert "--launched-by-task038-watchdog" in plan["argv"]
    assert plan["worker_contract"]["method"] == "positive_branch_qep_only"
    assert plan["watchdog"]["critical_action"] == "record_checkpoint_only"
    assert plan["watchdog"]["absolute_terminate_memory_bytes"] == (
        V3_7_ABSOLUTE_HARD_BYTES
    )
    default_plan = build_v3_7_execution_plan(
        INPUT,
        tmp_path / "iterative",
        source_sha="a" * 40,
        python_executable="/qualified/bin/python",
        mpiexec_command="/usr/bin/mpiexec",
        qep_only=False,
    )
    assert default_plan["argv"][5] == "benchmarks.task039_v3_7_orchestration"
    assert default_plan["worker_contract"]["method"] == (
        "hybrid_iterative_v3_7_diagnostic"
    )


def test_qep_only_contract_freezes_profile_and_evidence_schema():
    contract = task039_qep_only.qep_only_contract()
    assert contract["physical"] == {
        "wavelength_nm": 5.0,
        "grazing_angle_deg": 1.0,
        "azimuth_deg": 0.0,
        "polarization": "s",
        "mesh_target_nm": 5.0,
        "degree": 6,
    }
    assert contract["selection"] == {
        "requested_modes": 480,
        "candidate_modes": 960,
        "cutoff_numerator": 1.0e4,
    }
    assert contract["qep"]["tolerance"] == 1.0e-13
    assert contract["qep"]["near_degenerate_tolerance"] == 1.0e-6
    assert contract["qep"]["block_rotation_tolerance"] == 1.0e-6
    assert contract["qep"]["near_degenerate_candidate_envelope_factor"] == 10.0
    assert contract["qep"]["retained_subspace_dual_rotation"] is True
    assert contract["qep"]["runtime_readback"] == "not_available"
    assert contract["provenance_fields"] == [
        "input_sha256",
        "resolved_config_sha256",
        "physical_model_sha256",
    ]
    assert set(contract["forbidden_stages"]) == {
        "endcap",
        "P/T coupling",
        "side factor",
        "modal Schur",
        "outer solve",
        "recovery",
    }


def test_qep_only_does_not_route_forbidden_full_setup_calls():
    source = (ROOT / "benchmarks/task039_qep_only.py").read_text(encoding="utf-8")
    assert "build_hybrid_local_dtn_action_system" not in source
    assert "create_hybrid_assembled_block_action" not in source
    assert "run_frozen_m10_physics" not in source


def test_qep_only_provenance_binds_parent_resolved_config(tmp_path: Path):
    run = tmp_path / "run"
    output = run / "numerical_output" / "qep.json"
    resolved = run / "resolved_config.json"
    resolved.parent.mkdir()
    resolved.write_text("resolved", encoding="utf-8")
    payload = {
        "provenance": {
            "input_sha256": "i" * 64,
            "physical_model_sha256": "p" * 64,
        }
    }
    provenance = task039_qep_only._provenance(payload, output, "s" * 40)
    assert provenance["input_sha256"] == "i" * 64
    assert provenance["physical_model_sha256"] == "p" * 64
    assert len(provenance["resolved_config_sha256"]) == 64


def test_mode_rows_use_selected_basis_rows_not_raw_candidate_indices():
    selected = tuple(9000 + index for index in range(480))
    right = SimpleNamespace(polynomial_relative_residual=1.0e-14)
    mode = SimpleNamespace(
        beta=complex(2.0, 0.25),
        right=right,
        left_polynomial_relative_residual=2.0e-14,
    )
    basis = SimpleNamespace(
        modes=[mode for _ in range(480)],
        left_pair_relative_errors=[3.0e-14 for _ in range(480)],
        groups=(SimpleNamespace(indices=tuple(range(413, 418))),),
    )

    rows = task039_qep_only._mode_rows(basis, selected)

    assert [row["basis_mode_index"] for row in rows] == [413, 414, 415, 416, 417]
    assert [row["selected_candidate_index"] for row in rows] == list(selected[413:418])
    assert rows[0]["group_basis_mode_indices"] == [413, 414, 415, 416, 417]
    assert rows[0]["group_selected_candidate_indices"] == list(selected[413:418])
