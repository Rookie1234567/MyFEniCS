"""Focused public-contract tests for the Task041 side-BAL_H profiles."""

from __future__ import annotations

import ast
import copy
import hashlib
import inspect
import json
import math
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from benchmarks import task041_balh_workflow
from benchmarks.task041_balh_workflow import (
    TASK041_BALH_2NM_CANDIDATE_MODEL_ID,
    TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
    TASK041_REPRESENTATIVE_RHS_SCOPE,
    TASK041_SCHUR_SPEED_V2_PROFILE,
    TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
    build_task041_balh_candidate_consumer_command,
    build_task041_balh_exact_consumer_command,
    build_task041_balh_mode_prep_command,
    task041_balh_consumer_identity_binding,
    task041_balh_cpu_list,
    task041_balh_transfer_optimization_profile,
    task041_schur_speed_v2_contract,
    validate_balh_producer_packet,
)
from benchmarks.task041_exact_side_workflow import (
    Task041ModePrepError,
    _merge_representative_parts,
    _task041_backend_pair_layout_identity,
    _task041_case_contract,
    _task041_common_failure_details,
    _task041_form_p4_residual_identity,
    _task041_p4_backend_matrix_source,
    _task041_p4_backend_release_audit,
    _task041_p4_correction_callback_stage,
    _task041_p4_cross_run_component_hashes_match,
    _task041_rank_numa_observed_backend,
    _task041_rank_numa_pair_sample_stage,
    _task041_stream_array_metadata,
    _task041_top_causal_node_gate_status,
    _task041_top_causal_packet_budget,
    _task041_top_causal_pc_indices,
    _task041_worker_time_stop_enforced,
    _Task041TopCausalPacketCapture,
)
from benchmarks.task041_rank_numa import append_stage_jsonl
from scripts import run_case
from src.io.execution_plan import (
    TASK041_PUBLIC_SUPERVISOR_ADAPTER,
    build_execution_plan,
    method_adapter_available,
    method_adapter_identity,
)
from src.io.input_loader import InputError
from src.io.input_validation import (
    TASK041_BALH_13P5NM_CELL_CONDENSED_MODEL_ID,
    load_and_resolve,
    task041_balh_diagnostic_output_enabled,
    task041_balh_phase_limits_for_model,
    task041_balh_profile_errors,
    task041_balh_service_contract,
)
from src.io.resolved_config import resolved_config_bytes, resolved_config_sha256
from src.runners import task041_supervisor as supervisor
from src.runners.task041_supervisor import (
    _task041_p4_backend_pair_numeric_gate,
    _validate_common_layout_equivalence_result,
    _validate_representative_rhs_result,
    _validate_specification,
    run_task041_public_supervisor,
)
from src.solvers.full3d_lifecycle_packet import load_packet
from src.solvers.physical_balanced_coupling import BalancedConstraintRejected
from src.solvers.physical_balanced_physical_operator import (
    P4CondensedExactFactor,
    P4ExactFactor,
)
from src.solvers.physical_balanced_side_inverse import P4PhysicalResidualGateError

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BALH_INPUTS = sorted(
    (REPOSITORY_ROOT / "input/official/task041/side_balh").glob("*.dat")
)


class _RankNumaTestComm:
    def __init__(self, rank: int, outcome=None):
        self.rank = rank
        self.outcome = outcome
        self.barrier_calls = 0

    def bcast(self, value, root: int):
        assert root == 0
        if self.rank == 0:
            self.outcome = value
        else:
            assert value is None
        return self.outcome

    def Barrier(self):
        self.barrier_calls += 1


def _specification(path: Path):
    specification = load_and_resolve(path)
    assert task041_balh_profile_errors(specification.as_jsonable()) == []
    return specification


def test_task041_balh_dat_contracts_and_public_identity():
    assert len(BALH_INPUTS) == 7
    for path in BALH_INPUTS:
        specification = _specification(path)
        model_id = str(specification.identity["model_id"])
        assert method_adapter_identity("hybrid_iterative", model_id) == (
            TASK041_PUBLIC_SUPERVISOR_ADAPTER
        )
        assert method_adapter_available("hybrid_iterative", model_id)
        plan = build_execution_plan(
            specification,
            REPOSITORY_ROOT / "results" / "ignored_test351_plan",
            source_sha="a" * 40,
        )
        assert plan.adapter_identity == TASK041_PUBLIC_SUPERVISOR_ADAPTER
        identity = _validate_specification(specification, REPOSITORY_ROOT)
        assert identity["requested_modes"] in {120, 480, 1200}
        assert identity["mpi_size"] == 8
        contract = _task041_case_contract(
            specification.as_jsonable(), 8, phase="consumer"
        )
        assert contract["balh"] is True
        assert contract["shortwave"] is False
        assert contract["limits"]["swap_limit_bytes"] == 0
        if "cell_condensed" in model_id:
            assert contract["p4_inverse_backend"] == "cell_condensed"
            assert contract["support_policy"] == "entity_closure"
            assert contract["construction_audit"] == "reference_entity_trace_v1"
            service_contract = task041_balh_service_contract(model_id)
            assert service_contract is not None
            assert service_contract["producer"] == {
                "mode": "reuse",
                "invocation": "required",
                "time_stop_enforced": True,
                "qep": "not_run",
            }
            assert service_contract["time_stop"]["consumer_enforced"] is False
            assert service_contract["ledger"]["schema"] == (
                "task041.review_v5.r1_load_ledger.v1"
            )
            assert service_contract["ledger"]["path"].endswith(
                "results/task041_review_v5_cpu_numa_condensed_speed/"
                "r0_r1_20260920/r1_load_ledger_20260920.json"
            )
            assert service_contract["planning_ceiling_source"] == (
                "strict_hard_cap_admission_upper_bound_not_model_peak"
            )


def test_task041_rank_numa_jsonl_is_written_by_rank_zero(tmp_path):
    path = tmp_path / "rank_numa_evidence.jsonl"
    comm = _RankNumaTestComm(rank=0)
    record = {"stage": "startup", "qualification": {"status": "failed"}}

    append_stage_jsonl(comm, path, record)

    assert json.loads(path.read_text(encoding="utf-8")) == record
    assert comm.barrier_calls == 0


def test_task041_rank_numa_jsonl_nonroot_does_not_serialize_or_write(tmp_path):
    path = tmp_path / "must-not-be-written.jsonl"
    comm = _RankNumaTestComm(rank=1)

    append_stage_jsonl(comm, path, {"unserializable": object()})

    assert not path.exists()
    assert comm.barrier_calls == 0


def test_task041_rank_numa_jsonl_write_error_is_broadcast_to_all_ranks(
    tmp_path,
):
    directory = tmp_path / "not-a-file"
    directory.mkdir()
    root_comm = _RankNumaTestComm(rank=0)

    with pytest.raises(OSError) as root_error:
        append_stage_jsonl(root_comm, directory, {"stage": "startup"})

    nonroot_comm = _RankNumaTestComm(rank=1, outcome=root_comm.outcome)
    with pytest.raises(OSError) as nonroot_error:
        append_stage_jsonl(
            nonroot_comm,
            tmp_path / "must-not-be-written.jsonl",
            {"stage": "startup"},
        )

    assert str(nonroot_error.value) == str(root_error.value)
    assert root_comm.barrier_calls == nonroot_comm.barrier_calls == 0
    assert not (tmp_path / "must-not-be-written.jsonl").exists()


def test_task041_cell_condensed_contract_survives_resolved_serialization():
    cell_cases = [
        _specification(path)
        for path in BALH_INPUTS
        if 'cell_condensed' in path.stem
    ]
    assert len(cell_cases) == 2
    for specification in cell_cases:
        payload = json.loads(resolved_config_bytes(specification))
        serialized = payload['derived']['task041_solver_contract']
        assert serialized['p4_inverse_backend'] == 'cell_condensed'
        assert serialized['support_policy'] == 'entity_closure'
        assert serialized['construction_version'] == (
            'reference_entity_trace_v1'
        )
        execution = serialized['execution_contract']
        assert execution == {
            'mpi_size': 8,
            'cpu_set': '1-8',
            'membind_node': 0,
            'consumer_time_stop_enforced': False,
            'runtime_reserve_bytes': 412316860416,
        }


def test_task041_2nm_balh_case_uses_low_level_profile_without_v2_contract(tmp_path):
    path = (
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/"
        "2nm_p6h1p5_m1200_mpi8_balh.dat"
    )
    specification = _specification(path)
    model_id = str(specification.identity["model_id"])
    assert model_id == TASK041_BALH_2NM_CANDIDATE_MODEL_ID
    assert specification.as_jsonable()["output"]["diffraction_order_max_m"] == 60
    contract = _task041_case_contract(
        specification.as_jsonable(), 8, phase="consumer"
    )
    assert contract["transfer_optimization_profile"] == TASK041_SCHUR_SPEED_V2_PROFILE
    assert task041_balh_transfer_optimization_profile(model_id) == (
        TASK041_SCHUR_SPEED_V2_PROFILE
    )
    assert task041_balh_cpu_list(model_id) == "1-8"
    command = build_task041_balh_candidate_consumer_command(
        "python",
        specification,
        tmp_path / "manifest.json",
        tmp_path / "identity.json",
        "b" * 64,
        tmp_path / "consumer",
        "c" * 40,
        "a" * 40,
    )
    assert command[command.index("--cpu-list") + 1] == "1-8"
    assert "--task041-performance-profile" not in command
    with pytest.raises(
        ValueError, match="registered only for the two BAL_H candidates"
    ):
        task041_schur_speed_v2_contract(model_id)

    old_path = (
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/5nm_p6h4_m480_mpi8_balh.dat"
    )
    old_model_id = str(_specification(old_path).identity["model_id"])
    assert task041_balh_transfer_optimization_profile(old_model_id) is None
    assert task041_balh_cpu_list(old_model_id) == "0-7"
    assert (
        _specification(old_path).as_jsonable()["output"]["diffraction_order_max_m"]
        == 25
    )


@pytest.mark.parametrize(
    ("size", "rank", "size_marker", "rank_marker"),
    (
        (1, 0, None, None),
        (2, 0, None, None),
        (1, 1, None, None),
        (1, 0, "1", None),
    ),
    ids=("native-ok", "wrong-size", "wrong-rank", "outer-ompi"),
)
def test_task041_2nm_native_outer_identity_is_registered_and_fail_closed(
    monkeypatch, size, rank, size_marker, rank_marker
):
    monkeypatch.setattr(supervisor, "_outer_mpi_size", lambda: size)
    monkeypatch.setattr(supervisor, "_outer_mpi_rank", lambda: rank)
    if size_marker is None:
        monkeypatch.delenv("OMPI_COMM_WORLD_SIZE", raising=False)
    else:
        monkeypatch.setenv("OMPI_COMM_WORLD_SIZE", size_marker)
    if rank_marker is None:
        monkeypatch.delenv("OMPI_COMM_WORLD_RANK", raising=False)
    else:
        monkeypatch.setenv("OMPI_COMM_WORLD_RANK", rank_marker)

    if size == 1 and rank == 0 and size_marker is None and rank_marker is None:
        identity = supervisor._outer_mpi_launch_identity(
            registered_model_id=TASK041_BALH_2NM_CANDIDATE_MODEL_ID
        )
        assert identity["native_public_singleton"] is True
        assert identity["launched_via_mpiexec"] is False
    else:
        with pytest.raises(supervisor.Task041SupervisorError) as error:
            supervisor._outer_mpi_launch_identity(
                registered_model_id=TASK041_BALH_2NM_CANDIDATE_MODEL_ID
            )
        assert error.value.classification == "task041_identity_failure"
        assert error.value.stage == "outer_mpi_identity"


def test_task041_legacy_native_without_outer_mpi_is_rejected(monkeypatch):
    monkeypatch.setattr(supervisor, "_outer_mpi_size", lambda: 1)
    monkeypatch.setattr(supervisor, "_outer_mpi_rank", lambda: 0)
    monkeypatch.delenv("OMPI_COMM_WORLD_SIZE", raising=False)
    monkeypatch.delenv("OMPI_COMM_WORLD_RANK", raising=False)

    with pytest.raises(supervisor.Task041SupervisorError) as error:
        supervisor._outer_mpi_launch_identity()
    assert error.value.classification == "task041_identity_failure"
    assert error.value.stage == "outer_mpi_identity"


@pytest.mark.parametrize(
    ("section", "key", "value"),
    (
        ("materials", "n_substrate", (0.99880148307, 0.000213688648)),
        ("method", "requested_modes_per_direction", 1800),
        ("discretization", "mesh_target_nm", 2.0),
    ),
)
def test_task041_2nm_balh_rejects_physics_or_resolution_mutation(
    section, key, value
):
    path = (
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/"
        "2nm_p6h1p5_m1200_mpi8_balh.dat"
    )
    config = copy.deepcopy(_specification(path).as_jsonable())
    config[section][key] = value
    assert task041_balh_profile_errors(config)


def test_task041_balh_public_commands_select_one_consumer():
    for path in BALH_INPUTS:
        specification = _specification(path)
        mode_prep = build_task041_balh_mode_prep_command(
            "python",
            specification,
            REPOSITORY_ROOT / "results" / "ignored_test351_mode_prep",
            "a" * 40,
        )
        assert mode_prep.count("--phase") == 1
        assert mode_prep[mode_prep.index("--phase") + 1] == "mode-prep"
        route = str(specification.identity["model_id"]).split("_")[2]
        packet_manifest = REPOSITORY_ROOT / "results" / "producer" / "manifest.json"
        packet_identity = REPOSITORY_ROOT / "results" / "producer" / "identity.json"
        if "exact" in path.name:
            command = build_task041_balh_exact_consumer_command(
                "python",
                specification,
                packet_manifest,
                packet_identity,
                "b" * 64,
                REPOSITORY_ROOT / "results" / "ignored_test351_consumer",
                "c" * 40,
                "a" * 40,
            )
            assert route == "exact"
            assert command[command.index("--phase") + 1] == "consumer"
        else:
            command = build_task041_balh_candidate_consumer_command(
                "python",
                specification,
                packet_manifest,
                packet_identity,
                "b" * 64,
                REPOSITORY_ROOT / "results" / "ignored_test351_consumer",
                "c" * 40,
                "a" * 40,
            )
            assert route == "balh"
            assert command[command.index("--phase") + 1] == "candidate-consumer"
        assert command.count("--phase") == 1
        assert "--phase" in command
        assert not ("consumer" in command and "candidate-consumer" in command)


def test_task041_schur_speed_v2_profile_is_explicit_and_candidate_only(
    tmp_path: Path, monkeypatch
):
    from benchmarks import task041_balh_workflow

    candidate_path = (
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_balh.dat"
    )
    candidate = _specification(candidate_path)
    candidate_model = str(candidate.identity["model_id"])
    contract = task041_schur_speed_v2_contract(candidate_model)
    assert contract["profile_id"] == TASK041_SCHUR_SPEED_V2_PROFILE
    assert contract["phase_budgets_seconds"] == {
        "shared_S0_S1_S3": 21600.0,
        "S2": 7200.0,
        "S4": 172800.0,
    }
    assert contract["batch_budget_seconds"] == 201600.0
    assert contract["active_consumer_phase"] == "S2"
    assert contract["memory_cap_bytes"] == 9159106560
    assert contract["warning_memory_bytes"] == int(9159106560 * 0.9)
    assert contract["memory_gate_source"] == "simultaneous_process_tree_rss"
    assert contract["producer"] == {
        "mode": "reused",
        "invocation": "not_run",
        "time_stop_enforced": True,
        "qep": "not_run",
    }

    supervision_record = (tmp_path / "launch_manifest.json").resolve()
    captured = {}

    def fake_launch(specification, **kwargs):
        captured["model_id"] = specification.identity["model_id"]
        captured["kwargs"] = kwargs
        return {"result_classification": "worker_exit0"}

    monkeypatch.setattr("src.runners.task038_launcher.launch_specification", fake_launch)
    assert run_case.main(
        [
            str(candidate_path),
            "--producer-packet-root",
            str(tmp_path / "producer"),
            "--task041-performance-profile",
            TASK041_SCHUR_SPEED_V2_PROFILE,
            "--task041-supervision-record",
            str(supervision_record),
        ]
    ) == 0
    assert captured["model_id"] == candidate_model
    assert captured["kwargs"]["performance_profile"] == (
        TASK041_SCHUR_SPEED_V2_PROFILE
    )
    assert captured["kwargs"]["disable_time_stop"] is False
    assert captured["kwargs"]["task041_supervision_record"] == supervision_record

    command = build_task041_balh_candidate_consumer_command(
        "python",
        candidate,
        tmp_path / "manifest.json",
        tmp_path / "identity.json",
        "b" * 64,
        tmp_path / "worker",
        "c" * 40,
        "a" * 40,
        performance_profile=TASK041_SCHUR_SPEED_V2_PROFILE,
    )
    assert "--task041-performance-profile" in command
    worker_args = command[command.index("--worker") :]
    parsed_worker_args = task041_balh_workflow._parser().parse_args(worker_args)
    assert parsed_worker_args.task041_performance_profile == (
        TASK041_SCHUR_SPEED_V2_PROFILE
    )

    exact = _specification(
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_exact.dat"
    )
    with pytest.raises(ValueError, match="BAL_H candidate"):
        task041_schur_speed_v2_contract(str(exact.identity["model_id"]))
    with pytest.raises(ValueError, match="unsupported Task041 performance profile"):
        build_task041_balh_candidate_consumer_command(
            "python",
            candidate,
            tmp_path / "manifest.json",
            tmp_path / "identity.json",
            "b" * 64,
            tmp_path / "worker",
            "c" * 40,
            "a" * 40,
            performance_profile="not-a-profile",
        )


def test_task041_sequential_component_opt_in_is_bound_and_formal_rejected(
    tmp_path: Path, monkeypatch
):
    candidate_path = (
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/5nm_p6h4_m480_mpi8_balh.dat"
    )
    candidate = _specification(candidate_path)
    candidate_model = str(candidate.identity["model_id"])
    probe_manifest = (
        REPOSITORY_ROOT
        / "docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/records/"
        "task041_representative_rhs_v1.json"
    )
    legacy_descriptor = (
        REPOSITORY_ROOT
        / "results/task041_side_balh_component_audit/"
        "task041_h3b_legacy_native_packet_descriptor.json"
    )
    captured = []

    def fake_launch(specification, **kwargs):
        captured.append((specification, kwargs))
        return {"result_classification": "worker_exit0"}

    monkeypatch.setattr(
        "src.runners.task038_launcher.launch_specification", fake_launch
    )
    opt_in_argv = [
        str(candidate_path),
        "--legacy-native-packet-descriptor",
        str(legacy_descriptor),
        "--task041-performance-profile",
        TASK041_SCHUR_SPEED_V2_PROFILE,
        "--task041-rhs-probe",
        str(probe_manifest),
        "--task041-side-setup-schedule",
        TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        "--task041-comparison-mode",
        task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
        "--task041-top-causal-replay",
    ]
    assert run_case.main(opt_in_argv) == 0
    assert captured[-1][1]["performance_profile"] == (
        TASK041_SCHUR_SPEED_V2_PROFILE
    )
    assert captured[-1][1]["task041_rhs_probe_manifest"] == probe_manifest
    assert captured[-1][1]["task041_side_setup_schedule"] == (
        TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
    )
    assert captured[-1][1]["task041_comparison_mode"] == (
        task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE
    )
    assert captured[-1][1]["task041_top_causal_replay"] is True

    contract = task041_schur_speed_v2_contract(
        candidate_model,
        scope=TASK041_REPRESENTATIVE_RHS_SCOPE,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        comparison_mode=task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
        top_causal_replay=True,
    )
    assert contract["scope"] == TASK041_REPRESENTATIVE_RHS_SCOPE
    assert contract["side_setup_schedule"] == (
        TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
    )
    assert contract["budget_group"] == "shared_S0_S1_S3"
    command = build_task041_balh_candidate_consumer_command(
        str(Path(sys.executable)),
        candidate,
        tmp_path / "packet_manifest.json",
        tmp_path / "packet_identity.json",
        "b" * 64,
        tmp_path / "worker",
        "c" * 40,
        "a" * 40,
        performance_profile=TASK041_SCHUR_SPEED_V2_PROFILE,
        task041_rhs_probe_manifest=probe_manifest,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        comparison_mode=task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
        top_causal_replay=True,
    )
    worker_args = command[command.index("--worker") :]
    parsed = task041_balh_workflow._parser().parse_args(worker_args)
    assert parsed.task041_performance_profile == TASK041_SCHUR_SPEED_V2_PROFILE
    assert parsed.task041_rhs_probe == str(probe_manifest)
    assert parsed.task041_side_setup_schedule == (
        TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
    )
    assert parsed.task041_comparison_mode == (
        task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE
    )
    assert parsed.task041_top_causal_replay is True

    worker_calls = []

    def fake_consumer(**kwargs):
        worker_calls.append(kwargs)
        return {"status": "captured"}

    monkeypatch.setattr(
        "benchmarks.task041_exact_side_workflow.run_task041_consumer",
        fake_consumer,
    )
    assert task041_balh_workflow.main(
        [
            "--worker",
            "--phase",
            task041_balh_workflow.TASK041_BALH_CANDIDATE_PHASE,
            "--input",
            str(candidate_path),
            "--run-directory",
            str(tmp_path / "worker_run"),
            "--source-sha",
            "c" * 40,
            "--packet-manifest",
            str(tmp_path / "packet_manifest.json"),
            "--packet-identity",
            str(tmp_path / "packet_identity.json"),
            "--packet-manifest-sha256",
            "b" * 64,
            "--task041-performance-profile",
            TASK041_SCHUR_SPEED_V2_PROFILE,
            "--task041-rhs-probe",
            str(probe_manifest),
            "--task041-side-setup-schedule",
            TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
            "--task041-comparison-mode",
            task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
            "--task041-top-causal-replay",
        ]
    ) == {"status": "captured"}
    assert len(worker_calls) == 1
    assert worker_calls[0]["top_causal_replay"] is True
    assert worker_calls[0]["comparison_mode"] == (
        task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE
    )

    captured.clear()
    formal_argv = [
        str(candidate_path),
        "--legacy-native-packet-descriptor",
        str(legacy_descriptor),
        "--task041-performance-profile",
        TASK041_SCHUR_SPEED_V2_PROFILE,
    ]
    assert run_case.main(formal_argv) == 0
    assert captured[-1][1]["task041_side_setup_schedule"] is None
    assert run_case.main(
        [
            *formal_argv,
            "--task041-side-setup-schedule",
            TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        ]
    ) == 2
    assert run_case.main(
        [
            str(candidate_path),
            "--legacy-native-packet-descriptor",
            str(legacy_descriptor),
            "--task041-rhs-probe",
            str(probe_manifest),
            "--task041-side-setup-schedule",
            TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        ]
    ) == 2


def test_task041_common_layout_mode_binds_fixed_scope_and_cpu_range(
    tmp_path: Path, monkeypatch
):
    candidate_path = (
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/5nm_p6h4_m480_mpi8_balh.dat"
    )
    candidate = _specification(candidate_path)
    probe_manifest = (
        REPOSITORY_ROOT
        / "docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/records/"
        "task041_representative_rhs_v1.json"
    )
    legacy_descriptor = (
        REPOSITORY_ROOT
        / "results/task041_side_balh_component_audit/"
        "task041_h3b_legacy_native_packet_descriptor.json"
    )
    captured: list[dict[str, object]] = []

    def fake_launch(_specification, **kwargs):
        captured.append(kwargs)
        return {"result_classification": "worker_exit0"}

    monkeypatch.setattr(
        "src.runners.task038_launcher.launch_specification", fake_launch
    )
    argv = [
        str(candidate_path),
        "--legacy-native-packet-descriptor",
        str(legacy_descriptor),
        "--task041-performance-profile",
        TASK041_SCHUR_SPEED_V2_PROFILE,
        "--task041-rhs-probe",
        str(probe_manifest),
        "--task041-side-setup-schedule",
        TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        "--task041-comparison-mode",
        task041_balh_workflow.TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE,
    ]
    assert run_case.main(argv) == 0
    assert captured[-1]["task041_comparison_mode"] == (
        task041_balh_workflow.TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE
    )

    command = build_task041_balh_candidate_consumer_command(
        str(Path(sys.executable)),
        candidate,
        tmp_path / "packet_manifest.json",
        tmp_path / "packet_identity.json",
        "b" * 64,
        tmp_path / "worker",
        "c" * 40,
        "a" * 40,
        performance_profile=TASK041_SCHUR_SPEED_V2_PROFILE,
        task041_rhs_probe_manifest=probe_manifest,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        comparison_mode=task041_balh_workflow.TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE,
    )
    assert command[command.index("--cpu-list") + 1] == "1-8"
    assert "numactl" not in command
    worker_args = command[command.index("--worker") :]
    parsed = task041_balh_workflow._parser().parse_args(worker_args)
    assert parsed.task041_comparison_mode == (
        task041_balh_workflow.TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE
    )
    assert parsed.task041_side_setup_schedule == (
        TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
    )
    contract = task041_schur_speed_v2_contract(
        str(candidate.identity["model_id"]),
        scope=TASK041_REPRESENTATIVE_RHS_SCOPE,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        comparison_mode=task041_balh_workflow.TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE,
    )
    assert contract["scope"] == TASK041_REPRESENTATIVE_RHS_SCOPE
    assert contract["comparison_mode"] == (
        task041_balh_workflow.TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE
    )
    assert contract["budget_group"] == "shared_S0_S1_S3"


def _write_task041_fixed_pair_manifest(
    tmp_path: Path,
    *,
    packet_manifest_sha256: str,
    packet_identity_path: Path,
    source_sha: str,
) -> Path:
    expected = task041_balh_workflow._TASK041_REPRESENTATIVE_RHS_EXPECTED
    contract = task041_schur_speed_v2_contract(
        TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
        scope=TASK041_REPRESENTATIVE_RHS_SCOPE,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        comparison_mode=task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
    )
    audit_path = tmp_path / "fixed_rhs_source_audit.jsonl"
    audit_path.write_text('{"fixture":"fixed RHS source"}\n', encoding="utf-8")
    payload = {
        "schema": task041_balh_workflow.TASK041_REPRESENTATIVE_RHS_SCHEMA,
        "scope": TASK041_REPRESENTATIVE_RHS_SCOPE,
        "model_id": TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
        "profile_id": TASK041_SCHUR_SPEED_V2_PROFILE,
        "mode_count": task041_balh_workflow.TASK041_REPRESENTATIVE_RHS_MODE_COUNT,
        "mpi_size": task041_balh_workflow.TASK041_BALH_MPI_SIZE,
        "budget": {
            "group": "shared_S0_S1_S3",
            "phase_limit_seconds": task041_balh_workflow.TASK041_SCHUR_SPEED_V2_S0_S1_S3_BUDGET_SECONDS,
            "batch_limit_seconds": task041_balh_workflow.TASK041_SCHUR_SPEED_V2_BATCH_BUDGET_SECONDS,
            "memory_cap_bytes": contract["registered_memory_cap_bytes"],
            "swap_limit_bytes": 0,
            "time_stop_override": False,
        },
        "entries": [
            {
                "ordinal": ordinal,
                "side": values[0],
                "branch": values[1],
                "audit_index": values[2],
                "formal_column": values[3],
                "branch_ordinal": values[4],
            }
            for ordinal, values in enumerate(expected)
        ],
        "packet_binding": {
            "packet_manifest_sha256": packet_manifest_sha256,
            "packet_identity": str(packet_identity_path),
            "packet_identity_sha256": hashlib.sha256(
                packet_identity_path.read_bytes()
            ).hexdigest(),
        },
        "source_audit": {
            "rhs_audit_path": str(audit_path),
            "rhs_audit_sha256": hashlib.sha256(audit_path.read_bytes()).hexdigest(),
            "source_git_sha": source_sha,
        },
        "purpose": "fixed-eight-RHS backend equivalence test",
    }
    path = tmp_path / "task041_fixed_eight_rhs_manifest.json"
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    return path


def test_task041_fixed_p4_backend_pair_is_explicit_and_5nm_scoped():
    candidate_path = (
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/5nm_p6h4_m480_mpi8_balh.dat"
    )
    candidate = _specification(candidate_path)
    manifest = (
        REPOSITORY_ROOT
        / "docs/task041_mpi1_shortwave_hybrid_capacity/outcomes/records/"
        "task041_representative_rhs_v1.json"
    )
    pair_mode = task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE

    parsed_public = run_case._parser().parse_args(
        [
            str(candidate_path),
            "--task041-comparison-mode",
            pair_mode,
            "--task041-top-causal-replay",
        ]
    )
    assert parsed_public.task041_comparison_mode == pair_mode
    assert parsed_public.task041_top_causal_replay is True

    command = build_task041_balh_candidate_consumer_command(
        str(Path(sys.executable)),
        candidate,
        "packet_manifest.json",
        "packet_identity.json",
        "b" * 64,
        "worker",
        "c" * 40,
        "a" * 40,
        performance_profile=TASK041_SCHUR_SPEED_V2_PROFILE,
        task041_rhs_probe_manifest=manifest,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        comparison_mode=pair_mode,
        top_causal_replay=True,
    )
    assert command[command.index("--cpu-list") + 1] == "1-8"
    python_index = command.index(str(Path(sys.executable)))
    assert command[python_index - 2 : python_index + 1] == [
        "numactl",
        "--membind=0",
        str(Path(sys.executable)),
    ]
    worker_args = command[command.index("--worker") :]
    assert task041_balh_workflow._parser().parse_args(
        worker_args
    ).task041_comparison_mode == pair_mode
    assert task041_balh_workflow._parser().parse_args(
        worker_args
    ).task041_top_causal_replay is True
    pair_contract = task041_schur_speed_v2_contract(
        TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
        scope=TASK041_REPRESENTATIVE_RHS_SCOPE,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        comparison_mode=pair_mode,
        top_causal_replay=True,
    )
    assert pair_contract["comparison_mode"] == pair_mode
    assert pair_contract["top_causal_replay"] is True
    assert pair_contract["compute_wall_unlimited"] is True
    assert pair_contract["producer"]["mode"] == "reused"
    assert pair_contract["producer"]["invocation"] == "not_run"
    assert pair_contract["producer"]["time_stop_enforced"] is True
    assert pair_contract["time_stop"]["consumer_enforced"] is False
    assert pair_contract["time_stop"]["consumer_timeout_seconds"] is None
    assert pair_contract["active_consumer_budget_seconds"] == 21600.0
    assert pair_contract["batch_budget_seconds"] == 201600.0
    assert pair_contract["registered_memory_cap_bytes"] == 53_221_163_008
    assert pair_contract["registered_memory_cap_source"] == (
        "review_report_v2_section_5_explicit_cap"
    )
    assert pair_contract["memory_cap_bytes"] == 53_221_163_008
    assert pair_contract["warning_memory_bytes"] == 47_899_046_707
    assert pair_contract["memory_cap_source"] == (
        "review_report_v2_section_5_explicit_cap"
    )
    assert pair_contract["ledger"]["schema"] == (
        "task041.review_v5.r1_load_ledger.v1"
    )
    assert pair_contract["ledger"]["path"].endswith(
        "results/task041_review_v5_cpu_numa_condensed_speed/"
        "r0_r1_20260920/r1_load_ledger_20260920.json"
    )
    correction_contract = task041_schur_speed_v2_contract(
        TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
        scope=TASK041_REPRESENTATIVE_RHS_SCOPE,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        comparison_mode=pair_mode,
        p4_correction_replay=True,
    )
    assert correction_contract["p4_correction_replay"]["pc_action"] == "not_run"
    correction_command = build_task041_balh_candidate_consumer_command(
        str(Path(sys.executable)), candidate, "packet.json", "identity.json",
        "b" * 64, "worker", "c" * 40, "a" * 40,
        performance_profile=TASK041_SCHUR_SPEED_V2_PROFILE,
        task041_rhs_probe_manifest=manifest,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        comparison_mode=pair_mode,
        p4_correction_replay_from=REPOSITORY_ROOT / "results/g1",
    )
    assert "--task041-p4-correction-replay-from" in correction_command
    assert "--task041-top-causal-replay" not in correction_command

    unchanged_contract = task041_schur_speed_v2_contract(
        TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
        scope=TASK041_REPRESENTATIVE_RHS_SCOPE,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
    )
    assert unchanged_contract["comparison_mode"] is None
    assert unchanged_contract["time_stop"]["consumer_enforced"] is True
    assert unchanged_contract["active_consumer_budget_seconds"] == 21600.0
    assert unchanged_contract["memory_cap_bytes"] == 53_221_163_008
    assert unchanged_contract["warning_memory_bytes"] == 47_899_046_707
    assert unchanged_contract["memory_cap_source"] == (
        "review_report_v2_section_5_explicit_cap"
    )
    assert unchanged_contract["ledger"]["schema"] == "task041.compute_wall_ledger.v2"
    formal_cell_contract = task041_balh_service_contract(
        TASK041_BALH_13P5NM_CELL_CONDENSED_MODEL_ID
    )
    assert formal_cell_contract["memory_cap_bytes"] == 53_221_163_008
    assert formal_cell_contract["memory_cap_source"] == (
        "task041_v6_cell_condensed_resource_contract"
    )
    default_command = build_task041_balh_candidate_consumer_command(
        str(Path(sys.executable)),
        candidate,
        "packet_manifest.json",
        "packet_identity.json",
        "b" * 64,
        "worker",
        "c" * 40,
        "a" * 40,
    )
    assert default_command[default_command.index("--cpu-list") + 1] == "0-7"
    assert "numactl" not in default_command
    with pytest.raises(ValueError, match="5 nm representative_rhs"):
        task041_schur_speed_v2_contract(
            TASK041_BALH_2NM_CANDIDATE_MODEL_ID,
            scope=TASK041_REPRESENTATIVE_RHS_SCOPE,
            side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
            comparison_mode=pair_mode,
        )
    assert _task041_worker_time_stop_enforced(
        balh=True,
        disable_time_stop=False,
        case_time_stop_disabled=False,
        p4_backend_pair=True,
    ) is False
    assert _task041_worker_time_stop_enforced(
        balh=True,
        disable_time_stop=False,
        case_time_stop_disabled=False,
        p4_backend_pair=False,
    ) is True


def _write_p4_correction_result_fixture(tmp_path):
    root = tmp_path / "consumer"
    result_path = root / "numerical_output/top_causal_replay/p4_correction_replay/result.json"
    result_path.parent.mkdir(parents=True)
    a4 = {
        "physical_relative_residual": 1.0e-12,
        "augmented_relative_residual": 1.0e-12,
        "physical_pass": True,
        "augmented_pass": True,
        "pass": True,
    }
    stages = [
        {
            "operation": q,
            "step": step,
            "same_frozen_input_bytes": True,
            "same_q_input_bytes": True,
            "same_fe_ownership": True,
            "stage_gates_pass": True,
            "q_output_difference": {
                "finite": True,
                "numerator_norm": 1.0e-12,
                "denominator_norm": 1.0,
                "relative": 1.0e-12,
                "limit": 1.0e-11,
                "pass": True,
            },
            "original_a4_gates": {backend: dict(a4) for backend in ("full", "cell_condensed")},
        }
        for q in ("q1", "q2")
        for step in (0, 1, 2)
    ]
    source = {
        "producer_source_sha": "e2965ee25e56220d1623afe4dd221612542c2764",
        "consumer_source_sha": "c" * 40,
        "qep_source_sha": "b01a5932e4dfaf895e81e0424e0dd88c276fb0d3",
        "g1_root": str((tmp_path / "g1").resolve()),
    }
    producer_identity = {"source_sha": source["qep_source_sha"], "schema": "packet"}
    producer_identity_path = root / "producer_identity.json"
    producer_identity_path.parent.mkdir(parents=True, exist_ok=True)
    producer_identity_path.write_text(json.dumps(producer_identity) + "\n")
    source.update(
        {
            "producer_identity_sha256": hashlib.sha256(
                json.dumps(producer_identity, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
            "producer_packet_identity_path": str(producer_identity_path),
            "producer_packet_identity_sha256": hashlib.sha256(
                producer_identity_path.read_bytes()
            ).hexdigest(),
        }
    )
    record = {
        "schema": "task041.p4_correction_replay.result.v1",
        "scope": "top_pc1_frozen_independent_q1_q2",
        "status": "completed_action_gates_pass",
        "qualification_pass": False,
        "source": source,
        "selected_formal_columns": [12],
        "pc_index": 1,
        "pc_action": "not_run",
        "backend_release_pass": True,
        "cross_run_layout_pass": True,
        "evidence_complete": True,
        "action_safety_pass": True,
        "stage_comparisons": stages,
        "port_direction": {
            "source": "existing_external_PortMode_and_physical_action_path",
            "mode_generation_source": (
                "src/common/modes_3d.py::outgoing_port_modes_3d"
            ),
            "mode_key_sha256": "a" * 64,
            "normalization_sha256": "b" * 64,
            "port_layout_same": True,
            "pass": True,
        },
        "artifact_path": str(result_path),
    }
    result_path.write_text(json.dumps(record, sort_keys=True) + "\n")
    record["artifact_sha256"] = hashlib.sha256(result_path.read_bytes()).hexdigest()
    reference = {
        key: record[key]
        for key in (
            "schema", "scope", "status", "qualification_pass",
            "evidence_complete", "action_safety_pass", "artifact_path",
            "artifact_sha256",
        )
    }
    sidecar = root / "numerical_output/p4_correction_replay_top.json"
    sidecar.write_text(json.dumps(reference, sort_keys=True) + "\n")
    summary = {
        "schema": "task041.side_balh.candidate_consumer.v1",
        "status": "task041_p4_correction_replay_completed",
        "classification": "TASK041_P4_CORRECTION_REPLAY_COMPLETED",
        "source_sha": "c" * 40,
        "identity": {"mode_count": 480},
        "producer_identity": producer_identity,
        "packet": {"identity": str(producer_identity_path)},
        "p4_correction_replay": reference,
        "side_setup": {
            "side_completion": {
                "top": {
                    "status": "destroyed",
                    "backend_order": ["full", "cell_condensed"],
                }
            }
        },
        "markers": {"observed": ["final_cleanup_complete"]},
        "lifecycle": {
            "setup_released": True,
            "representative_rhs_cleanup_pass": True,
            "rss_marker_emitted": True,
        },
        "cleanup": {"pass": True},
        "gates": {"pass": False},
    }
    root.mkdir(exist_ok=True)
    (root / "consumer_summary.json").write_text(
        json.dumps(summary, sort_keys=True) + "\n"
    )
    return root


def _rewrite_p4_correction_fixture_result(root, update):
    result_path = root / "numerical_output/top_causal_replay/p4_correction_replay/result.json"
    record = json.loads(result_path.read_text())
    update(record)
    result_path.write_text(json.dumps(record, sort_keys=True) + "\n")
    reference = {
        key: record[key]
        for key in (
            "schema", "scope", "status", "qualification_pass",
            "evidence_complete", "action_safety_pass", "artifact_path",
        )
    }
    reference["artifact_sha256"] = hashlib.sha256(result_path.read_bytes()).hexdigest()
    summary_path = root / "consumer_summary.json"
    summary = json.loads(summary_path.read_text())
    summary["p4_correction_replay"] = reference
    summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n")
    sidecar = root / "numerical_output/p4_correction_replay_top.json"
    sidecar.write_text(json.dumps(reference, sort_keys=True) + "\n")


def test_task041_p4_correction_result_has_separate_public_scope(tmp_path):
    root = _write_p4_correction_result_fixture(tmp_path)

    result = supervisor._consumer_result(
        root,
        process_group_gone=True,
        expected_p4_correction_replay_from=tmp_path / "g1",
    )
    assert result["complete"] is True
    assert result["classification"] == "task041_p4_correction_replay_complete"
    assert result["completion_scope"] == "p4_correction_replay"
    assert result["p4_correction_replay_validation"]["pass"] is True

    old_scope = supervisor._consumer_result(root, process_group_gone=True)
    assert old_scope["complete"] is False


def test_task041_p4_correction_callback_reads_nested_side_inverse_audit():
    # This matches the outer record emitted by observe_p4_correction in side_inverse.
    callback_record = {
        "backend": "full",
        "q_call_index": 1,
        "p4_audit": {
            "diagnostic_step_index": 2,
            "diagnostic_correction_count": 2,
        },
        "port_state": {"port_correction": [[0.25, -0.5]]},
    }
    step, p4_audit = _task041_p4_correction_callback_stage(callback_record)
    assert step == 2
    assert p4_audit["diagnostic_correction_count"] == 2
    with pytest.raises(Task041ModePrepError, match="omitted its core audit"):
        _task041_p4_correction_callback_stage({"q_call_index": 1})


def test_task041_p4_correction_allows_early_negative_stages_if_final_passes(tmp_path):
    root = _write_p4_correction_result_fixture(tmp_path)

    def mark_early_steps_negative(record):
        for row in record["stage_comparisons"]:
            if row["step"] not in (0, 1):
                continue
            row["q_output_difference"].update(
                {
                    "numerator_norm": 5.0e-11,
                    "relative": 5.0e-11,
                    "pass": False,
                }
            )
            row["stage_gates_pass"] = False
            for audit in row["original_a4_gates"].values():
                audit.update(
                    {
                        "physical_relative_residual": 2.0e-10,
                        "physical_pass": False,
                        "pass": False,
                    }
                )

    _rewrite_p4_correction_fixture_result(root, mark_early_steps_negative)
    result = supervisor._consumer_result(
        root,
        process_group_gone=True,
        expected_p4_correction_replay_from=root.parent / "g1",
    )
    assert result["complete"] is True
    assert result["p4_correction_replay_validation"]["pass"] is True
    assert result["p4_correction_replay_validation"]["qualification_pass"] is False


@pytest.mark.parametrize(
    "failure",
    ("missing_step", "nonfinite_step", "final_q_over_limit", "final_a4_over_limit"),
)
def test_task041_p4_correction_rejects_incomplete_nonfinite_or_final_failure(
    tmp_path, failure
):
    root = _write_p4_correction_result_fixture(tmp_path)

    def introduce_failure(record):
        if failure == "missing_step":
            record["stage_comparisons"] = [
                row
                for row in record["stage_comparisons"]
                if (row["operation"], row["step"]) != ("q2", 1)
            ]
            return
        row = next(
            item
            for item in record["stage_comparisons"]
            if item["operation"] == "q2" and item["step"] == 2
        )
        row["stage_gates_pass"] = False
        if failure == "nonfinite_step":
            row["q_output_difference"]["relative"] = float("nan")
        elif failure == "final_q_over_limit":
            row["q_output_difference"].update(
                {
                    "numerator_norm": 2.0e-11,
                    "relative": 2.0e-11,
                    "pass": False,
                }
            )
        else:
            row["original_a4_gates"]["cell_condensed"].update(
                {
                    "physical_relative_residual": 2.0e-10,
                    "physical_pass": False,
                    "pass": False,
                }
            )

    _rewrite_p4_correction_fixture_result(root, introduce_failure)
    result = supervisor._consumer_result(
        root,
        process_group_gone=True,
        expected_p4_correction_replay_from=root.parent / "g1",
    )
    assert result["complete"] is False
    assert (
        result["p4_correction_replay_validation"]["checks"][
            "required_q_stages_and_original_gates"
        ]
        is False
    )


def test_task041_causal_and_correction_worker_routes_preserve_lifecycle_order(monkeypatch):
    from benchmarks import task041_exact_side_workflow as worker

    calls = []

    def fake_consumer(**kwargs):
        calls.append(kwargs)
        return {"status": "captured"}

    monkeypatch.setattr(worker, "run_task041_consumer", fake_consumer)
    args = [
        "--worker",
        "--phase",
        task041_balh_workflow.TASK041_BALH_CANDIDATE_PHASE,
        "--input",
        "input.dat",
        "--run-directory",
        "runroot",
        "--source-sha",
        "c" * 40,
        "--packet-manifest",
        "manifest.json",
        "--packet-identity",
        "identity.json",
        "--packet-manifest-sha256",
        "d" * 64,
        "--task041-performance-profile",
        TASK041_SCHUR_SPEED_V2_PROFILE,
        "--task041-rhs-probe",
        "probe.json",
        "--task041-side-setup-schedule",
        TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        "--task041-comparison-mode",
        task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
        "--task041-top-causal-replay",
    ]
    assert task041_balh_workflow.main(args) == {"status": "captured"}
    assert len(calls) == 1
    assert calls[0]["top_causal_replay"] is True
    assert calls[0]["comparison_mode"] == (
        task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE
    )
    correction_args = args[:-1] + [
        "--task041-p4-correction-replay-from", "g1-consumer-root"
    ]
    assert task041_balh_workflow.main(correction_args) == {"status": "captured"}
    assert calls[1]["p4_correction_replay_from"] == "g1-consumer-root"
    assert calls[1]["top_causal_replay"] is False

    tree = ast.parse(inspect.getsource(worker._run_task041_balh_candidate_setup))
    apply_backend = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "apply_backend"
    )
    apply_calls = sorted(
        (
            node.lineno,
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else "",
        )
        for node in ast.walk(apply_backend)
        if isinstance(node, ast.Call)
    )
    replay_line = next(
        line for line, name in apply_calls if name == "run_independent_causal_replays"
    )
    free_rhs_line = next(
        line for line, name in apply_calls if name == "run_representative_rhs_probe"
    )
    assert replay_line < free_rhs_line

    backend_loop = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.For)
        and isinstance(node.target, ast.Name)
        and node.target.id == "backend"
        and isinstance(node.iter, ast.Tuple)
        and [item.value for item in node.iter.elts if isinstance(item, ast.Constant)]
        == ["full", "cell_condensed"]
    )
    ordered_backend_calls = sorted(
        (
            node.lineno,
            node.func.id
            if isinstance(node.func, ast.Name)
            else node.func.attr
            if isinstance(node.func, ast.Attribute)
            else "",
        )
        for node in ast.walk(backend_loop)
        if isinstance(node, ast.Call)
    )
    lifecycle_lines = {
        name: next(
            line for line, call_name in ordered_backend_calls if call_name == name
        )
        for name in ("build_backend", "apply_backend", "release_backend")
    }
    assert (
        lifecycle_lines["build_backend"]
        < lifecycle_lines["apply_backend"]
        < lifecycle_lines["release_backend"]
    )


def test_task041_worker_forwards_top_causal_flag_to_candidate_setup(
    tmp_path: Path, monkeypatch
):
    from benchmarks import run_task037b_hybrid_iterative as recovery
    from benchmarks import task041_exact_side_workflow as worker
    from src.solvers import hybrid_fem_modal_augmented_direct as layout_module

    class FakeComm:
        rank = 0
        size = 8

    class SetupReached(Exception):
        pass

    candidate_path = (
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/5nm_p6h4_m480_mpi8_balh.dat"
    )
    specification = _specification(candidate_path)
    source_sha = "c" * 40
    resolved_sha = worker.resolved_config_sha256(specification)
    normalized = specification.as_jsonable()
    packet_identity = task041_balh_workflow.build_task041_balh_packet_identity(
        specification, normalized, source_sha, resolved_sha
    )
    packet_identity_path = tmp_path / "packet_identity.json"
    packet_identity_path.write_text(
        json.dumps(packet_identity, sort_keys=True) + "\n", encoding="utf-8"
    )
    packet_manifest_path = tmp_path / "packet_manifest.json"
    packet_manifest_path.write_text("{}\n", encoding="utf-8")
    packet_manifest_sha = "d" * 64
    probe_manifest = _write_task041_fixed_pair_manifest(
        tmp_path,
        packet_manifest_sha256=packet_manifest_sha,
        packet_identity_path=packet_identity_path,
        source_sha=source_sha,
    )
    captured = {}

    def fresh_root(path, _comm):
        root = Path(path)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def fake_setup_builder(**_kwargs):
        return SimpleNamespace(
            qep_release={"qep_calls": 0, "consumer_qep_required": False},
            coupling=SimpleNamespace(
                internal_unknown_count=1,
                propagation_axial_target_h_nm=1.0,
                propagation_axial_h_nm=1.0,
                propagation_axial_cell_count=1,
            ),
            bottom=object(),
            top=object(),
        )

    def intercept_candidate_setup(*_args, **kwargs):
        captured.update(kwargs)
        raise SetupReached

    monkeypatch.setattr(worker, "_collective_fresh_root", fresh_root)
    monkeypatch.setattr(worker, "_environment_snapshot", lambda: {"test": True})
    monkeypatch.setattr(worker, "_write_rank_pid_affinity", lambda *_a, **_k: None)
    monkeypatch.setattr(worker, "_memavailable_bytes", lambda: 10**15)
    monkeypatch.setattr(worker, "_check_resource", lambda *_a, **_k: None)
    monkeypatch.setattr(worker, "_write_rank0_json", lambda *_a, **_k: None)
    monkeypatch.setattr(
        worker,
        "_write_marker",
        lambda _root, _start, stage, **_kwargs: {"stage": stage, "resource": {}},
    )
    monkeypatch.setattr(worker, "_task041_rank_numa_observed_backend", lambda **_k: None)
    monkeypatch.setattr(
        worker,
        "_task041_consumer_sampled_column_contract",
        lambda *_a, **_k: {"sha256": "e" * 64},
    )
    monkeypatch.setattr(recovery, "build_frozen_m10_setup", fake_setup_builder)
    monkeypatch.setattr(
        recovery,
        "release_frozen_m10_objects",
        lambda *_a, **_k: {"pass": True},
    )
    monkeypatch.setattr(
        layout_module.HybridAugmentedLayout,
        "build",
        staticmethod(lambda *_a, **_k: SimpleNamespace()),
    )
    monkeypatch.setattr(
        worker, "_run_task041_balh_candidate_setup", intercept_candidate_setup
    )

    with pytest.raises(SetupReached):
        worker.run_task041_consumer(
            input_path=candidate_path,
            packet_manifest=packet_manifest_path,
            packet_identity=packet_identity_path,
            packet_manifest_sha256=packet_manifest_sha,
            run_directory=tmp_path / "worker_run",
            source_sha=source_sha,
            candidate=True,
            comm=FakeComm(),
            performance_profile=TASK041_SCHUR_SPEED_V2_PROFILE,
            task041_rhs_probe_manifest=probe_manifest,
            side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
            comparison_mode=task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
            top_causal_replay=True,
        )
    assert captured["top_causal_replay"] is True
    assert captured["top_causal_memory_cap_bytes"] == 53_221_163_008


def test_task041_backend_pair_release_reads_post_destroy_diagnostics_cache():
    release_record = {
        "side": "bottom",
        "status": "destroyed",
        "p4_backend": "full",
        "release_gate": {
            "destroyed": True,
            "p4_factor_count": 0,
            "nested_iterative_ksp_count": 0,
            "pass": True,
        },
        "heap_cleanup": {"pass": True},
        "lifecycle_boundary": {"event": "released"},
    }
    assert "diagnostics" not in release_record
    diagnostics_after_destroy = {
        "destroyed": True,
        "nested_ksp_destroy_count": 1,
        "p4_factor_destroy_count": 1,
        "p4_factor": {
            "schema": "task041.h1c.p4_exact_factor.v1",
            "factor_destroy_count": 1,
        },
        "p4_factor_count": 0,
        "nested_iterative_ksp_count": 0,
        "ksp_destroyed": True,
    }

    release = _task041_p4_backend_release_audit(
        side="bottom",
        release_record=release_record,
        side_diagnostics_after={"bottom": diagnostics_after_destroy},
    )
    assert release["pass"] is True
    assert release["destroy_counts"] == {
        "side_inverse_destroyed": True,
        "side_ksp_destroy_count": 1,
        "p4_factor_destroy_count": 1,
        "p4_factor_owner_destroy_count": 1,
        "p4_factor_count_after_destroy": 0,
        "nested_ksp_count_after_destroy": 0,
        "side_ksp_destroyed": True,
    }

    missing_cache = _task041_p4_backend_release_audit(
        side="bottom",
        release_record=release_record,
        side_diagnostics_after={"top": diagnostics_after_destroy},
    )
    assert missing_cache["pass"] is False
    assert (
        missing_cache["destroy_counts"]["p4_factor_count_after_destroy"] is None
    )

    mismatched_diagnostics = copy.deepcopy(diagnostics_after_destroy)
    mismatched_diagnostics["p4_factor_count"] = 1
    count_mismatch = _task041_p4_backend_release_audit(
        side="bottom",
        release_record=release_record,
        side_diagnostics_after={"bottom": mismatched_diagnostics},
    )
    assert count_mismatch["pass"] is False


def test_task041_pair_numa_tracks_condensed_backend_in_five_stages():
    pair_target = _task041_rank_numa_observed_backend(
        candidate=True,
        model_id=TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
        registered_backend="full",
        construction_audit=None,
        performance_profile=TASK041_SCHUR_SPEED_V2_PROFILE,
        representative_rhs_scope=TASK041_REPRESENTATIVE_RHS_SCOPE,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        comparison_mode=task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
    )
    assert pair_target == "cell_condensed"

    condensed_specification = next(
        specification
        for specification in (_specification(path) for path in BALH_INPUTS)
        if str(specification.identity["model_id"])
        == TASK041_BALH_13P5NM_CELL_CONDENSED_MODEL_ID
    )
    condensed_contract = _task041_case_contract(
        condensed_specification.as_jsonable(), 8, phase="consumer"
    )
    formal_command = build_task041_balh_candidate_consumer_command(
        str(Path(sys.executable)),
        condensed_specification,
        "packet_manifest.json",
        "packet_identity.json",
        "b" * 64,
        "worker",
        "c" * 40,
        "a" * 40,
    )
    assert formal_command[formal_command.index("--cpu-list") + 1] == "1-8"
    formal_python_index = formal_command.index(str(Path(sys.executable)))
    assert formal_command[formal_python_index - 2 : formal_python_index + 1] == [
        "numactl",
        "--membind=0",
        str(Path(sys.executable)),
    ]
    assert _task041_rank_numa_observed_backend(
        candidate=True,
        model_id=TASK041_BALH_13P5NM_CELL_CONDENSED_MODEL_ID,
        registered_backend=condensed_contract["p4_inverse_backend"],
        construction_audit=condensed_contract["construction_audit"],
        performance_profile=None,
        representative_rhs_scope=None,
        side_setup_schedule=None,
        comparison_mode=None,
    ) == "cell_condensed"
    assert _task041_rank_numa_observed_backend(
        candidate=True,
        model_id=TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
        registered_backend="full",
        construction_audit=None,
        performance_profile=None,
        representative_rhs_scope=None,
        side_setup_schedule=None,
        comparison_mode=None,
    ) is None
    assert _task041_rank_numa_observed_backend(
        candidate=True,
        model_id=TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
        registered_backend="full",
        construction_audit=None,
        performance_profile=TASK041_SCHUR_SPEED_V2_PROFILE,
        representative_rhs_scope=TASK041_REPRESENTATIVE_RHS_SCOPE,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        comparison_mode=task041_balh_workflow.TASK041_COMMON_LAYOUT_EQUIVALENCE_MODE,
    ) is None

    stages = ["startup"]
    first_response_sides: set[str] = set()
    for side in ("bottom", "top"):
        for backend in ("full", "cell_condensed"):
            stage = _task041_rank_numa_pair_sample_stage(
                "p4_ready",
                backend,
                pair_target,
                side,
                first_response_sides,
            )
            if stage is not None:
                stages.append(f"{side}:{stage}")
            for branch in ("positive", "positive", "negative", "negative"):
                if branch == "positive":
                    stage = _task041_rank_numa_pair_sample_stage(
                        "first_response",
                        backend,
                        pair_target,
                        side,
                        first_response_sides,
                    )
                    if stage is not None:
                        stages.append(f"{side}:{stage}")
    assert stages == [
        "startup",
        "bottom:p4_ready",
        "bottom:first_response",
        "top:p4_ready",
        "top:first_response",
    ]


def test_task041_pair_layout_identity_excludes_space_object_addresses(tmp_path):
    space_names = ("side_p6", "transfer_fine_p6", "transfer_coarse_p4")
    rank_records = []
    for rank in range(2):
        spaces = {}
        for index, name in enumerate(space_names):
            spaces[name] = {
                "space": {
                    "name": name,
                    "kind": "FunctionSpace",
                    "python_id": 100 + index + rank * 10,
                    "cpp_object": {
                        "kind": "FunctionSpace",
                        "python_id": 200 + index + rank * 10,
                    },
                    "cpp_kind": "FunctionSpace",
                    "cpp_python_id": 300 + index + rank * 10,
                },
                "dofmap": {
                    "map": {
                        "shape": [2, 3],
                        "dtype": "int32",
                        "nbytes": 24,
                        "sha256": f"{rank}{index}" * 32,
                        "hash_status": "measured_contiguous",
                    },
                    "global_size": 12,
                    "local_size": 6,
                    "num_ghosts": 1,
                    "block_size": 2,
                },
            }
        rank_records.append(
            {
                "rank": rank,
                "operator_global_shape": [24, 24],
                "communicators": {"size": 2, "rank": rank},
                "ownership": {"operator": [rank * 12, (rank + 1) * 12]},
                "transfer_identity": {"fine_global_rows": 24},
                "dofmaps": {
                    "fine": {"global_size": 24, "local_size": 12},
                    "coarse": {"global_size": 12, "local_size": 6},
                    "spaces": spaces,
                    "cell_records": {"record_count": 2, "sha256": "d" * 64},
                },
                "mesh_layout": {"geometry": {"sha256": "e" * 64}},
                "mpc_layout": {
                    "fine": {"slaves": {"sha256": "f" * 64}},
                    "coarse": {"slaves": {"sha256": "a" * 64}},
                    "objects": {"python_id": 900 + rank},
                },
                "layout_arrays": [{"sha256": "b" * 64}],
                "held_objects": {
                    "p4_matrix": {
                        "kind": "PETSc.Mat",
                        "python_id": 500 + rank,
                        "petsc_handle": 600 + rank,
                    },
                    "p4_factor": {"python_id": 700 + rank},
                },
            }
        )
    layout_record = {"by_rank": rank_records}

    original_identity = _task041_backend_pair_layout_identity(layout_record)
    address_changed = copy.deepcopy(layout_record)
    for record in address_changed["by_rank"]:
        for space in record["dofmaps"]["spaces"].values():
            space["space"]["python_id"] += 10000
            space["space"]["cpp_object"]["python_id"] += 10000
            space["space"]["cpp_python_id"] += 10000
        record["held_objects"]["p4_matrix"]["python_id"] += 10000
        record["held_objects"]["p4_matrix"]["petsc_handle"] += 10000
        record["held_objects"]["p4_factor"]["python_id"] += 10000
    address_changed_identity = _task041_backend_pair_layout_identity(
        address_changed
    )
    assert address_changed_identity["identity_sha256"] == original_identity[
        "identity_sha256"
    ]
    assert _task041_p4_cross_run_component_hashes_match(
        original_identity["component_sha256"],
        address_changed_identity["component_sha256"],
    )
    assert address_changed_identity["space_object_diagnostics"] != (
        original_identity["space_object_diagnostics"]
    )

    map_changed = copy.deepcopy(address_changed)
    map_changed["by_rank"][0]["dofmaps"]["spaces"]["transfer_fine_p6"][
        "dofmap"
    ]["map"]["sha256"] = "c" * 64
    map_changed_identity = _task041_backend_pair_layout_identity(map_changed)
    assert map_changed_identity["identity_sha256"] != original_identity[
        "identity_sha256"
    ]
    assert not _task041_p4_cross_run_component_hashes_match(
        original_identity["component_sha256"],
        map_changed_identity["component_sha256"],
    )

    frozen_components = copy.deepcopy(original_identity["component_sha256"])
    from benchmarks import task041_exact_side_workflow as worker

    comm = MPI.COMM_WORLD
    root_text = str(tmp_path / "layout-evidence") if comm.rank == 0 else None
    evidence_root = Path(comm.bcast(root_text, root=0))
    capture = worker._Task041TopCausalPacketCapture(
        comm=comm,
        root=evidence_root,
        source_sha="c" * 64,
        probe_manifest_sha256="m" * 64,
        parent_packet_sha256="p" * 64,
        memory_cap_bytes=53_221_163_008,
    )
    capture._prepare_directory(evidence_root)

    consumer_tree = ast.parse(
        inspect.getsource(worker._run_task041_balh_candidate_setup)
    )
    build_backend = next(
        node
        for node in ast.walk(consumer_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "build_backend"
    )
    persist_layout_branch = next(
        node
        for node in ast.walk(build_backend)
        if isinstance(node, ast.If)
        and "g1_component_comparisons" in ast.dump(node)
    )
    branch_module = ast.Module(
        body=[copy.deepcopy(persist_layout_branch)], type_ignores=[]
    )
    ast.fix_missing_locations(branch_module)
    namespace = vars(worker).copy()
    namespace.update(
        {
            "backend": "full",
            "layout_record": map_changed,
            "layout_identity": map_changed_identity,
            "p4_correction_replay_from": Path("g1-consumer"),
            "p4_correction_reference": {
                "component_sha256": frozen_components
            },
            "p4_correction_capture": capture,
            "cross_run_component_hash_pass": None,
        }
    )
    exec(  # noqa: S102 - execute the captured production evidence branch
        compile(branch_module, "<p4_layout_evidence_branch>", "exec"),
        namespace,
        namespace,
    )

    assert namespace["cross_run_component_hash_pass"] is False
    artifact_path = evidence_root / "layout_identity_full.json"
    artifact = json.loads(artifact_path.read_text()) if comm.rank == 0 else None
    artifact = comm.bcast(artifact, root=0)
    assert artifact["layout_record"] == map_changed
    assert artifact["layout_identity"]["component_sha256"] == (
        map_changed_identity["component_sha256"]
    )
    comparisons = artifact["g1_component_comparisons"]
    assert [name for name, row in comparisons.items() if row["equal"] is False] == [
        "dofmaps"
    ]
    assert comparisons["dofmaps"]["g1_sha256"] == (
        frozen_components["dofmaps"]
    )
    assert comparisons["dofmaps"]["current_sha256"] == (
        map_changed_identity["component_sha256"]["dofmaps"]
    )
    assert original_identity["component_sha256"] == frozen_components


def test_task041_pair_layout_matrix_source_uses_actual_backend_interfaces():
    full_matrix = object()
    full = P4ExactFactor(
        physical_action=None,
        matrix=full_matrix,
        factor=object(),
        factor_events=[],
    )
    condensed_matrix = object()
    condensed = P4CondensedExactFactor(
        physical_action=None,
        inverse=SimpleNamespace(
            condensed=SimpleNamespace(matrix=condensed_matrix)
        ),
        factor_events=[],
    )

    assert not hasattr(condensed, "matrix")
    assert _task041_p4_backend_matrix_source(full, "full") == (
        full_matrix,
        "p4.matrix",
        "full_augmented_p4_matrix",
    )
    assert _task041_p4_backend_matrix_source(condensed, "cell_condensed") == (
        condensed_matrix,
        "p4.condensed.matrix",
        "cell_condensed_retained_matrix",
    )


def test_task041_pair_layout_matrix_source_rejects_unknown_or_missing_evidence():
    with pytest.raises(Task041ModePrepError, match="unsupported p4 backend"):
        _task041_p4_backend_matrix_source(object(), "unknown")

    missing_full_matrix = object.__new__(P4ExactFactor)
    with pytest.raises(Task041ModePrepError, match="missing its augmented matrix"):
        _task041_p4_backend_matrix_source(missing_full_matrix, "full")

    missing_condensed_matrix = P4CondensedExactFactor(
        physical_action=None,
        inverse=SimpleNamespace(condensed=SimpleNamespace()),
        factor_events=[],
    )
    with pytest.raises(
        Task041ModePrepError,
        match="missing its retained matrix",
    ):
        _task041_p4_backend_matrix_source(
            missing_condensed_matrix,
            "cell_condensed",
        )


class _Task041TopCausalTinyVec:
    def __init__(self, values, ownership=None):
        self.values = np.asarray(values, dtype=np.complex128).copy()
        self.ownership = ownership or (0, int(self.values.size))

    def getArray(self, readonly=False):
        return self.values

    def getOwnershipRange(self):
        return self.ownership

    def assemble(self):
        return None

    def destroy(self):
        return None


class _Task041TopCausalTinyP4:
    def __init__(self, comm):
        self.comm = comm
        self.audit_rhs = []

    def create_fe_vector(self):
        start, end = (0, 2) if self.comm.rank == 0 else (2, 2)
        return _Task041TopCausalTinyVec(np.zeros(end - start), (start, end))

    def audit_solution(self, rhs, solution, *, port_rhs, port_solution):
        self.audit_rhs.append(
            np.array(rhs.getArray(readonly=True), dtype=np.complex128, copy=True)
        )
        return {
            "physical_relative_residual": 1.0e-13,
            "relative_residual": 2.0e-13,
        }


class _Task041TopCausalGatherAuditComm:
    def __init__(self, comm):
        self.comm = comm
        self.gather_values = []

    def __getattr__(self, name):
        return getattr(self.comm, name)

    def gather(self, value, root=0):
        self.gather_values.append(value)
        return self.comm.gather(value, root=root)


def test_task041_top_causal_capture_tail_packets_and_replay_gates(
    tmp_path_factory,
):
    for count in (2, 17, 32, 57):
        selected = _task041_top_causal_pc_indices(count)
        assert selected[-2:] == [count - 1, count]
        assert len(selected) <= 8

    comm = MPI.COMM_WORLD
    if comm.size > 2:
        pytest.skip("micro-fixture is scoped to serial or MPI2")
    capture_comm = _Task041TopCausalGatherAuditComm(comm)
    root_text = (
        str(tmp_path_factory.mktemp("task041-top-causal"))
        if comm.rank == 0
        else None
    )
    root = Path(comm.bcast(root_text, root=0)) / "top_causal"

    def owned_range(global_size, rank):
        return (0, global_size) if rank == 0 else (global_size, global_size)

    def local_size(global_size, rank):
        start, end = owned_range(global_size, rank)
        return end - start

    def rank_layout(rank):
        active_start, active_end = owned_range(3, rank)
        p4_start, p4_end = owned_range(2, rank)
        active_local = active_end - active_start
        p4_local = p4_end - p4_start
        local_map_sha = hashlib.sha256(
            np.arange(active_start, active_end, dtype=np.int32).tobytes()
        ).hexdigest()
        return {
            "rank": rank,
            "operator_global_shape": [3, 3],
            "communicators": {"size": comm.size, "rank": rank},
            "ownership": {"operator": [active_start, active_end]},
            "transfer_identity": {"fine_global_rows": 3, "coarse_global_rows": 2},
            "dofmaps": {
                "fine": {"global_size": 3, "local_size": active_local},
                "coarse": {"global_size": 2, "local_size": p4_local},
                "spaces": {
                    "side_p6": {
                        "space": {"kind": "FunctionSpace", "python_id": 101 + rank},
                        "dofmap": {
                            "map": {
                                "shape": [active_local],
                                "dtype": "int32",
                                "nbytes": 4 * active_local,
                                "sha256": local_map_sha,
                                "hash_status": "measured_contiguous",
                            },
                            "global_size": 3,
                            "local_size": active_local,
                            "num_ghosts": 0,
                            "block_size": 1,
                        },
                    }
                },
                "cell_records": {"record_count": 1, "sha256": "5" * 64},
            },
            "mesh_layout": {"geometry": {"sha256": "6" * 64}},
            "mpc_layout": {
                "fine": {"slaves": {"sha256": "7" * 64}},
                "coarse": {"slaves": {"sha256": "8" * 64}},
            },
            "layout_arrays": [{"sha256": "9" * 64}],
            "vector_layouts": {
                "active_p6": {
                    "local_owned_entries": active_local,
                    "ownership_range": [active_start, active_end],
                },
                "full_p6": {
                    "local_owned_entries": active_local,
                    "ownership_range": [active_start, active_end],
                },
                "p4_full_fe": {
                    "local_owned_entries": p4_local,
                    "ownership_range": [p4_start, p4_end],
                },
            },
            "port_layout": {
                "replicated_entries": 0,
                "mode_keys_sha256": "a" * 64,
                "normalization_sha256": "b" * 64,
            },
        }

    from benchmarks import task041_exact_side_workflow as worker

    setup_tree = ast.parse(
        inspect.getsource(worker._run_task041_balh_candidate_setup)
    )
    capture_layout_node = next(
        node
        for node in ast.walk(setup_tree)
        if isinstance(node, ast.FunctionDef) and node.name == "capture_layout"
    )
    p4_capture_branch = next(
        node
        for node in ast.walk(capture_layout_node)
        if isinstance(node, ast.If)
        and "p4_physical_fe" in ast.dump(node)
        and any(
            isinstance(child, ast.Assign)
            and any(
                isinstance(target, ast.Name)
                and target.id == "vector_layouts"
                for target in child.targets
            )
            for child in ast.walk(node)
        )
    )
    condition_node = ast.Expression(body=copy.deepcopy(p4_capture_branch.test))
    ast.fix_missing_locations(condition_node)
    condition_code = compile(condition_node, "<capture_layout_condition>", "eval")
    branch_module = ast.Module(
        body=copy.deepcopy(p4_capture_branch.body), type_ignores=[]
    )
    ast.fix_missing_locations(branch_module)
    branch_code = compile(branch_module, "<capture_layout_p4_fields>", "exec")

    def run_capture_layout_fields():
        created_vectors = []

        def make_vector(global_size):
            local_size = (
                owned_range(global_size, comm.rank)[1]
                - owned_range(global_size, comm.rank)[0]
            )
            vector = PETSc.Vec().createMPI(
                (local_size, global_size), comm=comm
            )
            created_vectors.append(vector)
            return vector

        p4_space = SimpleNamespace(
            global_size=2,
            local_size=owned_range(2, comm.rank)[1]
            - owned_range(2, comm.rank)[0],
        )
        mode = SimpleNamespace(
            side="top",
            m=0,
            n=0,
            polarization="s",
            electric_tangential_norm_sq=1.0,
            power_per_unit_amplitude=1.0,
        )
        p4 = SimpleNamespace(
            physical_action=SimpleNamespace(
                V=p4_space,
                action=SimpleNamespace(
                    modes=[SimpleNamespace(mode=mode, denominator=1.0)]
                ),
            ),
            create_fe_vector=lambda: make_vector(2),
        )

        def space_layout_metadata(_name, space):
            ownership = owned_range(space.global_size, comm.rank)
            local_map = np.arange(*ownership, dtype=np.int32)
            return {
                "space": {"kind": "FunctionSpace", "python_id": 100 + comm.rank},
                "dofmap": {
                    "map": {
                        "shape": [int(local_map.size)],
                        "dtype": str(local_map.dtype),
                        "nbytes": int(local_map.nbytes),
                        "sha256": hashlib.sha256(local_map.tobytes()).hexdigest(),
                        "hash_status": "measured_contiguous",
                    },
                    "global_size": int(space.global_size),
                    "local_size": int(space.local_size),
                    "num_ghosts": 0,
                    "block_size": 1,
                },
            }

        namespace = vars(worker).copy()
        operator = SimpleNamespace(createVecRight=lambda: make_vector(3))
        inverse = SimpleNamespace(
            _full_action=SimpleNamespace(
                matrix=SimpleNamespace(createVecRight=lambda: make_vector(3))
            )
        )
        namespace.update(
            {
                "p4": p4,
                "operator": operator,
                "inverse": inverse,
                "spaces": dict(rank_layout(comm.rank)["dofmaps"]["spaces"]),
                "vector_layouts": None,
                "port_layout": None,
                "_task041_space_layout_metadata": space_layout_metadata,
            }
        )
        exec(branch_code, namespace, namespace)  # noqa: S102 - execute the captured production AST branch
        assert all(int(vector.handle) == 0 for vector in created_vectors)
        return {
            "vector_layouts": namespace["vector_layouts"],
            "port_layout": namespace["port_layout"],
            "p4_space": namespace["spaces"]["p4_physical_fe"],
        }

    for top_causal_replay, correction_root, expected_capture in (
        (True, None, True),
        (False, Path("g1"), True),
        (False, None, False),
    ):
        capture_requested = bool(
            eval(
                condition_code,
                {"__builtins__": {}},
                {
                    "top_causal_replay": top_causal_replay,
                    "p4_correction_replay_from": correction_root,
                },
            )
        )
        assert capture_requested is expected_capture
        local_fields = (
            run_capture_layout_fields() if capture_requested else None
        )
        fields_by_rank = comm.allgather(local_fields)
        by_rank = []
        for rank, fields in enumerate(fields_by_rank):
            record = rank_layout(rank)
            if fields is not None:
                record["vector_layouts"] = fields["vector_layouts"]
                record["port_layout"] = fields["port_layout"]
                record["dofmaps"]["spaces"]["p4_physical_fe"] = fields[
                    "p4_space"
                ]
            else:
                record.pop("vector_layouts")
                record.pop("port_layout")
            by_rank.append(record)
        layout_identity = _task041_backend_pair_layout_identity(
            {"by_rank": by_rank}
        )
        if capture_requested:
            assert all(
                isinstance(record, dict)
                for record in layout_identity["vector_layouts_by_rank"]
            )
            assert all(
                isinstance(record, dict)
                for record in layout_identity["port_layouts_by_rank"]
            )
            budget = _task041_top_causal_packet_budget(
                layout_identity["vector_layouts_by_rank"],
                port_layouts_by_rank=layout_identity["port_layouts_by_rank"],
                comm_size=comm.size,
                memory_cap_bytes=53_221_163_008,
            )
            assert budget["pass"] is True
        else:
            assert layout_identity["vector_layouts_by_rank"] == [
                None
            ] * comm.size
            assert layout_identity["port_layouts_by_rank"] == [None] * comm.size

    capture = _Task041TopCausalPacketCapture(
        comm=capture_comm,
        root=root,
        source_sha="1" * 40,
        probe_manifest_sha256="2" * 64,
        parent_packet_sha256="3" * 64,
        memory_cap_bytes=53_221_163_008,
    )
    capture._prepare_directory(root)
    layout = {"by_rank": [rank_layout(rank) for rank in range(comm.size)]}
    capture.configure_layout(layout)
    p4 = _Task041TopCausalTinyP4(comm)
    inverse = SimpleNamespace(
        diagnostics={"last_apply": {}, "independent_p4_call_history": []},
        _p4_factor=p4,
    )
    context = {"formal_column": 12, "representative_ordinal": 1}

    def emit(
        owner,
        event,
        *,
        q_index=None,
        source=None,
        result=None,
        target=None,
        pc_index=2,
        **fields,
    ):
        borrowed = {}
        global_size = 2 if event in {"PH_Q_output", "p4_recovered_solution"} else 3
        start, end = owned_range(global_size, comm.rank)

        def local_vec(values):
            local_values = np.asarray(values, dtype=np.complex128)[start:end]
            return _Task041TopCausalTinyVec(local_values, (start, end))

        if source is not None:
            borrowed["source"] = local_vec(source)
        if result is not None:
            borrowed["result"] = local_vec(result)
        if target is not None:
            borrowed["target"] = local_vec(target)
            borrowed["solution"] = borrowed["target"]
        record = {
            "event": event,
            "representative_context": context,
            "pc_apply_index": pc_index,
            "borrowed_vectors": borrowed,
            **fields,
        }
        if q_index is not None:
            record["q_call_index"] = q_index
        return owner.callback(record)

    q_values = {
        1: {
            "input": [1.0, 2.0, 3.0],
            "ph_rhs": [10.0, 11.0],
            "p4_solution": [12.0, 13.0],
            "output": [0.1, 0.2, 0.3],
        },
        2: {
            "input": [4.0, 5.0, 6.0],
            "ph_rhs": [14.0, 15.0],
            "p4_solution": [16.0, 17.0],
            "output": [0.4, 0.5, 0.6],
        },
    }
    port_record = {
        "port_values_available": True,
        "port_rhs_complex": [],
        "port_solution_complex": [],
        "port_projection_complex": [],
    }

    def emit_q(owner, q_index, values, *, q_input=None, q_output=None):
        emit(owner, "Q_input", q_index=q_index, source=values["input"] if q_input is None else q_input)
        emit(owner, "PH_Q_output", q_index=q_index, result=values["ph_rhs"])
        emit(owner, "p4_rhs", q_index=q_index)
        emit(owner, "p4_port_solution", q_index=q_index, **port_record)
        emit(owner, "p4_recovered_solution", q_index=q_index, target=values["p4_solution"])
        emit(owner, "P_output", q_index=q_index, result=values["output"] if q_output is None else q_output)

    capture.activate(
        mode="capture",
        backend="full",
        trajectory="full_reference",
        inverse=inverse,
        representative_ordinal=1,
    )
    emit(capture, "PC_input", source=[0.7, 0.8, 0.9])
    emit_q(capture, 1, q_values[1])
    emit_q(capture, 2, q_values[2])
    emit(capture, "PC_output", target=[0.2, 0.3, 0.4])
    capture.finish_apply(inverse)

    reference_dir = capture.root / "full_reference" / "pc_00002"
    assert reference_dir.is_dir()
    assert not (capture.root / "full_reference" / "pending_tail_slot_0").exists()
    q1_manifest = reference_dir / "q_01_input_output" / "manifest.json"
    q2_manifest = reference_dir / "q_02_input_output" / "manifest.json"
    assert q1_manifest.is_file() and q2_manifest.is_file()
    assert q1_manifest.read_bytes() != q2_manifest.read_bytes()
    node_audit = json.loads((reference_dir / "node_audit.json").read_text())
    for artifact in node_audit["by_rank"][0]["artifacts"]:
        relative = artifact.get("manifest_relative_to_node")
        if relative:
            assert (reference_dir / relative).is_file()

    reference_node = {"pc_index": 2, "reference_directory": reference_dir}
    assert capture._packet(reference_node, "q_02_input_output")["rhs"].size == local_size(
        3, comm.rank
    )

    def packet_vec(global_size, values):
        start, end = owned_range(global_size, comm.rank)
        vector = PETSc.Vec().createMPI(
            (end - start, global_size), comm=comm
        )
        if end > start:
            vector.getArray()[:] = np.asarray(values, dtype=np.complex128)[
                start:end
            ]
        vector.assemble()
        return vector

    stage_solution = packet_vec(2, [2.0 + 0.5j, -1.0 + 0.25j])
    stage_rhs = packet_vec(2, [3.0 + 0.75j, 4.0 - 0.5j])
    stage_residual = packet_vec(2, [0.125 - 0.25j, -0.375 + 0.5j])
    stage_p6 = packet_vec(3, [0.5 + 0.25j, 1.5 - 0.5j, -2.0 + 0.75j])
    stage_q_input = packet_vec(3, [1.0 - 0.25j, -0.5 + 0.5j, 2.5 + 0.125j])
    port_state = {
        "port_rhs_complex": [[0.25, -0.125]],
        "port_solution_complex": [[0.5, 0.25]],
    }
    borrowed_stage_vectors = {
        "solution": stage_solution,
        "coarse_rhs": stage_rhs,
        "fe_residual": stage_residual,
        "p_output": stage_p6,
        "q_input": stage_q_input,
    }
    audit_rhs_count = len(p4.audit_rhs)
    try:
        stage_record = capture.write_p4_correction_stage(
            backend="cell_condensed",
            operation="q1",
            q_call_index=1,
            step=0,
            vectors=borrowed_stage_vectors,
            audit={"diagnostic_step_index": 0, "relative_residual": 1.0e-13},
            port_state=port_state,
            layout_identity_sha256=capture.layout_identity_sha256,
        )
        state_artifact = next(
            item
            for item in stage_record["artifacts"]
            if item["role"] == "p4_state"
        )
        state_packet = load_packet(
            Path(state_artifact["manifest"]),
            identity=state_artifact["identity"],
            expected_manifest_sha256=state_artifact["manifest_sha256"],
            comm=comm,
        )
        expected_owned_rhs = np.asarray(
            stage_rhs.getArray(readonly=True), dtype=np.complex128
        ).copy()
        np.testing.assert_array_equal(state_packet["rhs"], expected_owned_rhs)
        if expected_owned_rhs.size:
            assert not np.array_equal(
                state_packet["rhs"], stage_residual.getArray()
            )
        assert state_packet["metadata"]["p4_audit"][
            "diagnostic_step_index"
        ] == 0
        assert state_packet["metadata"]["port_state"] == port_state

        # Match the production condensed callback's temporary live-inverse binding.
        capture.inverse = inverse
        shared_node = {"shared_a4_checks": []}
        shared_check = capture._shared_a4_check(
            node=shared_node,
            q_index=1,
            reference_packet=state_packet,
            current_solution=stage_solution,
            current_rhs=expected_owned_rhs,
            current_port=port_state,
        )
        capture.inverse = None
        assert shared_check["pass"] is True
        assert shared_node["shared_a4_checks"][0]["q_call_index"] == 1
        assert len(p4.audit_rhs) == audit_rhs_count + 2
        np.testing.assert_array_equal(
            p4.audit_rhs[audit_rhs_count], expected_owned_rhs
        )
        np.testing.assert_array_equal(
            p4.audit_rhs[audit_rhs_count + 1], expected_owned_rhs
        )
        assert int(stage_solution.handle) != 0
        assert int(stage_rhs.handle) != 0
        assert int(stage_residual.handle) != 0
    finally:
        capture.inverse = None
        stage_q_input.destroy()
        stage_p6.destroy()
        stage_residual.destroy()
        stage_rhs.destroy()
        stage_solution.destroy()

    binding_key = (2, "q_02_input_output")
    saved_binding = capture.packet_bindings[binding_key]
    wrong_binding = copy.deepcopy(saved_binding)
    wrong_binding["identity"]["layout_identity_sha256"] = "c" * 64
    if comm.rank == comm.size - 1:
        capture.packet_bindings[binding_key] = wrong_binding
    with pytest.raises(Task041ModePrepError, match="identity mismatch"):
        capture._packet(reference_node, "q_02_input_output")
    capture.packet_bindings[binding_key] = saved_binding
    nonfinite_values = (
        [complex(float("nan"), 0.0)] if comm.rank == comm.size - 1 else [1.0]
    )
    with pytest.raises(Task041ModePrepError, match="non-finite"):
        capture._array_norm(np.asarray(nonfinite_values), comm)

    for q_index in (1, 2):
        trajectory = f"independent_q{q_index}"
        capture.activate(
            mode="replay",
            backend="cell_condensed",
            trajectory=trajectory,
            inverse=inverse,
            pc_index=2,
            q_replay_index=q_index,
            representative_ordinal=1,
        )
        emit_q(capture, q_index, q_values[q_index])
        capture.finish_apply(inverse)
        assert capture.node_summaries[-1]["replay_kind"] == "independent_q"
        assert capture.node_summaries[-1]["gate_status"] == "passed_independent_q_replay_gates"

    capture.activate(
        mode="replay",
        backend="cell_condensed",
        trajectory="independent_q1_action_failure",
        inverse=inverse,
        pc_index=2,
        q_replay_index=1,
        representative_ordinal=1,
    )
    emit_q(
        capture,
        1,
        q_values[1],
        q_output=[0.6, 0.2, 0.3],
    )
    capture.finish_apply(inverse)
    action_failure = capture.node_summaries[-1]
    assert action_failure["gate_status"] == "failed_action_gate"
    action_failure_audit = json.loads(
        (
            capture.root
            / "replay"
            / "independent_q1_action_failure"
            / "pc_00002"
            / "independent_q1_action_failure_node_audit.json"
        ).read_text()
    )
    assert any(
        item["gate_name"] == "Q"
        and item["gate_applicable"] is True
        and item["gate_pass"] is False
        for item in action_failure_audit["by_rank"][comm.rank]["comparisons"]
    )

    capture.activate(
        mode="replay",
        backend="cell_condensed",
        trajectory="independent_pc",
        inverse=inverse,
        pc_index=2,
        representative_ordinal=1,
    )
    emit(capture, "PC_input", source=[0.7, 0.8, 0.9])
    emit_q(capture, 1, q_values[1])
    emit_q(
        capture,
        2,
        q_values[2],
        q_input=[4.25, 5.0, 6.0],
        q_output=[0.45, 0.5, 0.6],
    )
    emit(capture, "PC_output", target=[0.2, 0.3, 0.4])
    capture.finish_apply(inverse)
    pc_summary = capture.node_summaries[-1]
    assert pc_summary["replay_kind"] == "independent_pc"
    assert pc_summary["gate_status"] == "passed_independent_pc_replay_gates"
    pc_audit_path = (
        capture.root
        / "replay"
        / "independent_pc"
        / "pc_00002"
        / "independent_pc_node_audit.json"
    )
    pc_audit = json.loads(pc_audit_path.read_text())
    pc_local_audit = pc_audit["by_rank"][comm.rank]
    pc_comparisons = pc_local_audit["comparisons"]
    assert pc_local_audit["actual_pc_apply_index"] == 2
    assert pc_local_audit["ksp_iteration"] is None
    assert pc_local_audit["q_calls"]["1"]["actual_q_call_index"] == 1
    assert pc_local_audit["q_calls"]["1"]["reference_q_index"] == 1
    assert pc_local_audit["q_calls"]["2"]["actual_q_call_index"] == 2
    assert pc_local_audit["q_calls"]["2"]["reference_q_index"] == 2
    missing_q2_node = {
        "complete": pc_local_audit["complete"],
        "q_calls": copy.deepcopy(pc_local_audit["q_calls"]),
        "comparisons": pc_comparisons,
        "shared_a4_checks": pc_local_audit["shared_a4_checks"],
    }
    missing_q2_node["q_calls"].pop("2")
    assert (
        _task041_top_causal_node_gate_status(
            missing_q2_node,
            replay_kind="independent_pc",
            q_replay_index=None,
            apply_error=False,
        )
        == "not_applicable_required_q_checks_missing"
    )
    q2_input_comparison = next(
        item
        for item in pc_comparisons
        if item["event"] == "Q_input" and item["q_call_index"] == 2
    )
    assert q2_input_comparison["exact_owned_bytes_equal"] is False
    assert q2_input_comparison["gate_applicable"] is False
    assert q2_input_comparison["gate_status"] == "not_applicable"
    assert any(
        item["gate_name"] == "PC" and item["gate_pass"] is True
        for item in pc_comparisons
    )

    capture.activate(
        mode="replay",
        backend="cell_condensed",
        trajectory="free_diverged",
        inverse=inverse,
        representative_ordinal=1,
    )
    emit(capture, "PC_input", source=[0.71, 0.8, 0.9])
    emit_q(capture, 1, q_values[1])
    emit_q(capture, 2, q_values[2])
    emit(capture, "PC_output", target=[0.2, 0.3, 0.4])
    capture.finish_apply(inverse)
    free_summary = capture.node_summaries[-1]
    assert free_summary["replay_kind"] == "free_trajectory"
    assert free_summary["gate_status"] == "diagnostic_only_free_trajectory"
    free_audit_path = (
        capture.root
        / "replay"
        / "free_diverged"
        / "pc_00002"
        / "free_diverged_node_audit.json"
    )
    free_audit = json.loads(free_audit_path.read_text())
    free_pc_input = next(
        item
        for item in free_audit["by_rank"][0]["comparisons"]
        if item["event"] == "PC_input"
    )
    assert free_pc_input["exact_owned_bytes_equal"] is False
    assert free_summary["gate_status"] != "passed_independent_pc_replay_gates"

    partial_capture = _Task041TopCausalPacketCapture(
        comm=capture_comm,
        root=root.parent / "partial_failure",
        source_sha="1" * 40,
        probe_manifest_sha256="2" * 64,
        parent_packet_sha256="3" * 64,
        memory_cap_bytes=53_221_163_008,
    )
    partial_capture._prepare_directory(partial_capture.root)
    partial_capture.configure_layout(layout)
    partial_capture.activate(
        mode="capture",
        backend="full",
        trajectory="partial_failure",
        inverse=inverse,
        representative_ordinal=1,
    )
    emit(partial_capture, "PC_input", source=[0.7, 0.8, 0.9])
    partial_capture.finish_apply(
        inverse,
        error=RuntimeError("micro-fixture interrupted after PC input"),
    )
    partial_dir = partial_capture.root / "full_reference" / "pc_00002"
    partial_audit = json.loads((partial_dir / "node_audit.json").read_text())
    assert partial_audit["status"] == "partial_failure_evidence"
    failure_snapshot = partial_audit["by_rank"][0]["failure_snapshot"]
    assert failure_snapshot["owner_shards_only"] is True
    failure_manifest = json.loads(Path(failure_snapshot["manifest"]).read_text())
    assert failure_manifest["rank_count"] == comm.size
    assert sum(shard["size"] for shard in failure_manifest["shards"]) == 3
    assert all(
        shard["size"] == local_size(3, shard["rank"])
        for shard in failure_manifest["shards"]
    )

    def contains_array(value):
        if isinstance(value, np.ndarray):
            return True
        if isinstance(value, dict):
            return any(contains_array(item) for item in value.values())
        if isinstance(value, (list, tuple)):
            return any(contains_array(item) for item in value)
        return False

    assert capture_comm.gather_values
    assert all(not contains_array(value) for value in capture_comm.gather_values)


@pytest.mark.parametrize(
    "port_rhs",
    (
        np.asarray([0.0 + 0.0j]),
        np.asarray([0.3 - 0.2j]),
    ),
    ids=("zero-port-rhs", "nonzero-port-rhs"),
)
def test_task041_full_p4_augmented_residual_matches_original_block_matrix(
    port_rhs: np.ndarray,
):
    # Tiny complex block fixture for M = [[A0, -T], [-D, I]].  The physical
    # action is its Schur complement A0 - T D; compare the diagnostic formula
    # against an independent dense multiplication of the original block.
    a0 = np.asarray(
        [[2.0 + 0.5j, -0.2 + 0.1j], [0.4 - 0.3j, 1.7 + 0.2j]],
        dtype=np.complex128,
    )
    traction = np.asarray([[0.7 - 0.1j], [-0.3 + 0.25j]], dtype=np.complex128)
    projection = np.asarray([[0.2 + 0.15j, -0.1 + 0.3j]], dtype=np.complex128)
    fe_rhs = np.asarray([0.8 + 0.2j, -0.4 + 0.7j], dtype=np.complex128)
    fe_solution = np.asarray([0.6 - 0.2j, 0.1 + 0.5j], dtype=np.complex128)
    port_solution = np.asarray([-0.25 + 0.4j], dtype=np.complex128)

    physical_action = a0 - traction @ projection
    bare_full_residual = fe_rhs - physical_action @ fe_solution
    effective_condensed_residual = (
        fe_rhs + traction @ port_rhs - physical_action @ fe_solution
    )
    port_residual = port_rhs + projection @ fe_solution - port_solution
    full_diagnostic_fe_residual = bare_full_residual + traction @ (
        port_rhs - port_residual
    )
    condensed_diagnostic_fe_residual = (
        effective_condensed_residual - traction @ port_residual
    )

    augmented_matrix = np.block(
        [
            [a0, -traction],
            [-projection, np.eye(1, dtype=np.complex128)],
        ]
    )
    augmented_rhs = np.concatenate((fe_rhs, port_rhs))
    augmented_solution = np.concatenate((fe_solution, port_solution))
    block_residual = augmented_rhs - augmented_matrix @ augmented_solution

    np.testing.assert_allclose(full_diagnostic_fe_residual, block_residual[:2])
    np.testing.assert_allclose(
        condensed_diagnostic_fe_residual,
        block_residual[:2],
    )
    np.testing.assert_allclose(port_residual, block_residual[2:])


@pytest.mark.parametrize(
    "port_solution_perturbation",
    (0.0 + 0.0j, 0.12 - 0.07j),
    ids=("exact-port-solution", "perturbed-port-solution"),
)
def test_task041_full_p4_solve_audit_matches_original_block_matrix_zero_port_rhs(
    monkeypatch,
    port_solution_perturbation: complex,
):
    from src.solvers import physical_balanced_physical_operator as p4_operator

    class TinyVec:
        def __init__(self, values):
            self.values = np.asarray(values, dtype=np.complex128).copy()

        def duplicate(self):
            return TinyVec(np.zeros_like(self.values))

        def copy(self, target):
            target.values[:] = self.values

        def axpy(self, alpha, other):
            self.values += alpha * other.values

        def norm(self):
            return float(np.linalg.norm(self.values))

        def getArray(self, readonly=False):
            return self.values

        def getOwnershipRange(self):
            return (0, int(self.values.size))

        def getSize(self):
            return int(self.values.size)

        def getLocalSize(self):
            return int(self.values.size)

        def getComm(self):
            return TinyComm()

        def setValues(self, rows, values, *, addv):
            assert addv == p4_operator.PETSc.InsertMode.ADD_VALUES
            self.values[np.asarray(rows, dtype=np.int64)] += values

        def assemble(self):
            pass

        def destroy(self):
            pass

    class TinyMPIComm:
        def Allreduce(self, source, target, op=None):
            target[:] = source

    class TinyComm:
        def tompi4py(self):
            return TinyMPIComm()

    class TinyMatrix:
        def __init__(self, values=None):
            self.values = values
            self.comm = TinyComm()

        def getComm(self):
            return self.comm

        def mult(self, source, target):
            target.values[:] = self.values @ source.values

    class TinyFactor:
        def __init__(self, solution_values):
            self.solution_values = solution_values

        def solve(self, rhs, solution):
            solution.values[:] = self.solution_values

    a0 = np.asarray(
        [[2.0 + 0.5j, -0.2 + 0.1j], [0.4 - 0.3j, 1.7 + 0.2j]],
        dtype=np.complex128,
    )
    traction = np.asarray(
        [[0.7 - 0.1j], [-0.3 + 0.25j]], dtype=np.complex128
    )
    projection = np.asarray(
        [[0.2 + 0.15j, -0.1 + 0.3j]], dtype=np.complex128
    )
    fe_solution = np.asarray([0.6 - 0.2j, 0.1 + 0.5j], dtype=np.complex128)
    port_solution = projection @ fe_solution
    augmented_matrix = np.block(
        [
            [a0, -traction],
            [-projection, np.eye(1, dtype=np.complex128)],
        ]
    )
    augmented_solution = np.concatenate((fe_solution, port_solution))
    augmented_rhs = augmented_matrix @ augmented_solution
    assert augmented_rhs[-1] == pytest.approx(0.0j)
    solved_augmented_solution = augmented_solution.copy()
    solved_augmented_solution[-1] += port_solution_perturbation

    mode = SimpleNamespace(
        projection_rows=np.asarray([0, 1], dtype=np.int64),
        projection_values=np.conjugate(projection[0]),
        denominator=1.0 + 0.0j,
        traction_rows=np.asarray([0, 1], dtype=np.int64),
        traction_values=traction[:, 0],
    )
    physical_action = SimpleNamespace(
        full_rows=2,
        modes=[mode],
        action=SimpleNamespace(modes=[mode]),
        matrix=TinyMatrix(a0 - traction @ projection),
    )
    matrix = TinyMatrix()

    def extract_fe_solution(self, vector):
        return TinyVec(vector.values[: self.full_rows])

    monkeypatch.setattr(P4ExactFactor, "extract_fe_solution", extract_fe_solution)
    p4 = P4ExactFactor(
        physical_action=physical_action,
        matrix=matrix,
        factor=TinyFactor(solved_augmented_solution),
        factor_events=[],
    )
    audit = p4.solve_with_refinement(
        TinyVec(augmented_rhs),
        TinyVec(np.zeros_like(augmented_solution)),
        diagnostic_audit=True,
    )

    direct_residual = (
        augmented_rhs - augmented_matrix @ solved_augmented_solution
    )
    np.testing.assert_allclose(
        audit["augmented_fe_residual_norm"],
        np.linalg.norm(direct_residual[:2]),
        atol=1.0e-14,
    )
    np.testing.assert_allclose(
        audit["port_residual_norm"],
        np.linalg.norm(direct_residual[2:]),
        atol=1.0e-14,
    )
    np.testing.assert_allclose(
        audit["augmented_residual_norm"],
        np.linalg.norm(direct_residual),
        atol=1.0e-14,
    )
    assert audit["augmented_gate_passed"] is (port_solution_perturbation == 0.0j)


def test_task041_pair_supervisor_recomputes_numeric_ratios_from_norms():
    comparison = {
        "pass": True,
        "comparison": {
            "finite": True,
            "pass": True,
            "response_norms": {
                "full": 2.0,
                "cell_condensed": 4.0,
                "denominator": 4.0,
            },
            "response_delta_norm": 2.0e-8,
            "action_delta_norm": 1.0e-8,
            "rhs_norm": 2.0,
            "side_residuals": {
                "full_norm": 2.0e-3,
                "full_relative": 1.0e-3,
                "cell_condensed_norm": 4.0e-3,
                "cell_condensed_relative": 2.0e-3,
            },
            "e_x": 5.0e-9,
            "e_A": 5.0e-9,
            "limits": {
                "e_x": 1.0e-8,
                "e_A": 1.0e-8,
                "side_relative_residual": 1.0e-2,
            },
        },
    }
    checked = _task041_p4_backend_pair_numeric_gate(comparison)
    assert checked["pass"] is True
    assert checked["recomputed"] == {
        "e_x": 5.0e-9,
        "e_A": 5.0e-9,
        "full_relative": 1.0e-3,
        "cell_condensed_relative": 2.0e-3,
    }

    declared = copy.deepcopy(comparison)
    declared["comparison"]["strong_pair_gate_pass"] = False
    declared["comparison"]["side_residual_gate_pass"] = True
    assert _task041_p4_backend_pair_numeric_gate(declared)["pass"] is False

    comparison["comparison"]["e_x"] = 1.0e-9
    assert _task041_p4_backend_pair_numeric_gate(comparison)["pass"] is False


def test_task041_p4_residual_identity_uses_nonzero_full_and_condensed_residuals():
    vectors = []
    try:
        for values in (
            [3.0 + 4.0j, 2.0 + 0.0j],
            [2.0 + 1.0j, -3.0 + 0.0j],
            [1.0 - 2.0j, 4.0 + 0.0j],
        ):
            vector = PETSc.Vec().createSeq(2, comm=MPI.COMM_SELF)
            vector.getArray()[:] = np.asarray(values, dtype=np.complex128)
            vector.assemble()
            vectors.append(vector)
        action_delta, full_residual, condensed_residual = vectors
        residual_identity = PETSc.Vec().createSeq(2, comm=MPI.COMM_SELF)
        vectors.append(residual_identity)

        _task041_form_p4_residual_identity(
            action_delta,
            full_residual,
            condensed_residual,
            residual_identity,
        )

        expected = (
            np.asarray(action_delta.getArray(readonly=True))
            - np.asarray(full_residual.getArray(readonly=True))
            + np.asarray(condensed_residual.getArray(readonly=True))
        )
        np.testing.assert_array_equal(
            residual_identity.getArray(readonly=True), expected
        )
        assert np.linalg.norm(expected) > 0.0
    finally:
        for vector in vectors:
            vector.destroy()


class _CommonFailureInverse:
    _last_coupling_failure = None


@pytest.mark.parametrize(
    ("exception", "expected_evidence"),
    (
        (
            P4PhysicalResidualGateError(
                {"residual_norm": 2.0e-2, "residual_tolerance": 1.0e-10}
            ),
            "p4_solve_audit",
        ),
        (
            BalancedConstraintRejected(
                {"norm": 2.0e-8, "operation_scale": 1.0, "limit": 1.0e-8}
            ),
            "balance_audit",
        ),
    ),
    ids=("real-p4-gate", "real-balance-gate"),
)
def test_task041_common_failure_class_keeps_real_gate_audit(
    exception: BaseException, expected_evidence: str
):
    classification, evidence = _task041_common_failure_details(
        exception, _CommonFailureInverse()
    )
    assert classification == "NUMERICAL_GATE_FAIL"
    assert evidence[expected_evidence]
    assert evidence["cause"]["exception_type"] == type(exception).__name__


def test_task041_common_failure_without_real_gate_cause_is_setup_failure():
    classification, evidence = _task041_common_failure_details(
        RuntimeError("live KSP contract mismatch"), _CommonFailureInverse()
    )
    assert classification == "PAIRING_SETUP_FAILURE"
    assert evidence["cause"]["exception"] == "live KSP contract mismatch"


@pytest.mark.parametrize("shape", [(0,), (0, 5)])
def test_task041_layout_stream_hash_measures_empty_arrays(shape):
    value = np.empty(shape, dtype=np.complex128)
    metadata = _task041_stream_array_metadata("empty", value)
    assert metadata["shape"] == list(shape)
    assert metadata["nbytes"] == 0
    assert metadata["storage_nbytes"] == 0
    assert metadata["hash_status"] == "measured_empty"
    assert metadata["sha256"] == hashlib.sha256(b"").hexdigest()


def test_task041_layout_stream_hash_measures_strided_empty_view():
    value = np.empty((2, 3, 4), dtype=np.complex128)[:0, :, ::-1]
    assert value.size == 0
    assert value.strides[-1] < 0
    metadata = _task041_stream_array_metadata("strided_empty", value)
    assert metadata["shape"] == [0, 3, 4]
    assert metadata["dtype"] == "complex128"
    assert metadata["nbytes"] == 0
    assert metadata["storage_nbytes"] == 0
    assert metadata["hash_status"] == "measured_empty"
    assert metadata["sha256"] == hashlib.sha256(b"").hexdigest()


def test_task041_balh_module_help_executes_public_worker_entrypoint():
    result = subprocess.run(
        [sys.executable, "-m", "benchmarks.task041_balh_workflow", "--help"],
        cwd=REPOSITORY_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0
    assert "usage:" in output
    assert "--worker" in output
    assert "--phase" in output


def test_task041_balh_identity_keeps_producer_and_consumer_distinct():
    exact = _specification(
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_exact.dat"
    )
    candidate = _specification(
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_balh.dat"
    )
    from benchmarks.task041_balh_workflow import build_task041_balh_packet_identity

    producer_identity = build_task041_balh_packet_identity(
        exact, exact.as_jsonable(), "a" * 40, resolved_config_sha256(exact)
    )
    binding = task041_balh_consumer_identity_binding(
        producer_identity, candidate, "b" * 40
    )
    assert binding["pass"] is True
    assert binding["producer_identity"] == producer_identity
    assert binding["consumer_identity"]["source_sha"] == "b" * 40
    assert binding["consumer_identity"]["input_sha256"] == candidate.input_sha256
    assert binding["consumer_identity"]["resolved_sha256"] == resolved_config_sha256(
        candidate
    )
    assert binding["consumer_identity"]["physical_sha256"] == (
        candidate.physical_model_sha256
    )
    assert binding["producer_identity"]["input_sha256"] != binding[
        "consumer_identity"
    ]["input_sha256"]

    bad_external = copy.deepcopy(producer_identity)
    bad_external["external_keys"]["count"] += 1
    with pytest.raises(ValueError, match="external_keys"):
        task041_balh_consumer_identity_binding(bad_external, candidate, "b" * 40)

    bad_physics = copy.deepcopy(producer_identity)
    bad_physics["physical_contract"]["discretization"]["mesh_target_nm"] = 4.0
    with pytest.raises(ValueError, match="physical_contract"):
        task041_balh_consumer_identity_binding(bad_physics, candidate, "b" * 40)

    bad_mpi = copy.deepcopy(producer_identity)
    bad_mpi["mpi_size"] = 1
    with pytest.raises(ValueError, match="mpi_size"):
        task041_balh_consumer_identity_binding(bad_mpi, candidate, "b" * 40)

    with pytest.raises(ValueError, match="source SHA"):
        task041_balh_consumer_identity_binding(producer_identity, candidate, "bad")


def test_task041_balh_ordinary_hybrid_cannot_opt_into_balh_pc(tmp_path: Path):
    legacy_input = REPOSITORY_ROOT / "input/official/grazing1_phi0_hybrid_iterative_m120_mpi8.dat"
    from src.runners.task038_launcher import launch_specification

    ordinary = load_and_resolve(legacy_input)
    with pytest.raises(InputError, match="producer-packet-root"):
        launch_specification(
            ordinary,
            source_sha="a" * 40,
            producer_packet_root=tmp_path / "not_allowed",
        )
    text = legacy_input.read_text(encoding="utf-8")
    modified = tmp_path / legacy_input.name
    modified.write_text(
        text.replace(
            "hybrid_block_ldu_ilu0_dtn_woodbury",
            "hybrid_block_ldu_balh_side_inverse",
        ),
        encoding="utf-8",
    )
    with pytest.raises(InputError, match=r"solver\.preconditioner"):
        load_and_resolve(modified)


def test_task041_balh_scripts_run_case_reaches_public_launcher(monkeypatch):
    path = REPOSITORY_ROOT / "input/official/task041/side_balh/5nm_p6h4_m480_mpi8_balh.dat"
    captured = {}

    def fake_launch(specification, **kwargs):
        captured["model_id"] = specification.identity["model_id"]
        captured["kwargs"] = kwargs
        return {"result_classification": "worker_exit0"}

    monkeypatch.setattr("src.runners.task038_launcher.launch_specification", fake_launch)
    packet_root = REPOSITORY_ROOT / "results/producer"
    probe = REPOSITORY_ROOT / "results/representative_rhs.json"
    correction_root = REPOSITORY_ROOT / "results/g1"
    assert run_case.main(
        [
            str(path), "--producer-packet-root", str(packet_root),
            "--task041-performance-profile", TASK041_SCHUR_SPEED_V2_PROFILE,
            "--task041-rhs-probe", str(probe),
            "--task041-side-setup-schedule", TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
            "--task041-comparison-mode", task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
            "--task041-p4-correction-replay-from", str(correction_root),
        ]
    ) == 0
    assert captured["model_id"] == TASK041_BALH_5NM_CANDIDATE_MODEL_ID
    assert captured["kwargs"]["task041_p4_correction_replay_from"] == correction_root

    captured.clear()
    assert run_case.main(
        [
            str(path), "--legacy-native-packet-descriptor", str(packet_root),
            "--task041-performance-profile", TASK041_SCHUR_SPEED_V2_PROFILE,
            "--task041-rhs-probe", str(probe),
            "--task041-side-setup-schedule", TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
            "--task041-comparison-mode", task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
            "--task041-p4-correction-replay-from", str(correction_root),
        ]
    ) == 0
    assert captured["model_id"] == TASK041_BALH_5NM_CANDIDATE_MODEL_ID
    assert captured["kwargs"]["legacy_native_packet_descriptor"] == packet_root
    assert captured["kwargs"]["producer_packet_root"] is None
    assert captured["kwargs"]["task041_p4_correction_replay_from"] == correction_root


def test_task041_balh_time_stop_override_is_forwarded_only_to_5nm_candidate(
    tmp_path, monkeypatch
):
    captured = {}
    from benchmarks import task041_balh_workflow

    def fake_launch(specification, **kwargs):
        captured["model_id"] = specification.identity["model_id"]
        captured["kwargs"] = kwargs
        return {"result_classification": "worker_exit0"}

    monkeypatch.setattr("src.runners.task038_launcher.launch_specification", fake_launch)
    five_nm_candidate = (
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/5nm_p6h4_m480_mpi8_balh.dat"
    )
    packet_root = tmp_path / "producer"
    assert run_case.main(
        [
            str(five_nm_candidate),
            "--producer-packet-root",
            str(packet_root),
            "--task041-balh-candidate-disable-time-stop",
        ]
    ) == 0
    assert captured["model_id"] == "task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8"
    assert captured["kwargs"]["disable_time_stop"] is True
    assert captured["kwargs"]["producer_packet_root"] == packet_root
    worker_command = build_task041_balh_candidate_consumer_command(
        "python",
        _specification(five_nm_candidate),
        tmp_path / "manifest.json",
        tmp_path / "identity.json",
        "d" * 64,
        tmp_path / "worker",
        "c" * 40,
        "a" * 40,
        disable_time_stop=True,
    )
    assert "--task041-balh-candidate-disable-time-stop" in worker_command
    worker_args = worker_command[worker_command.index("--worker") :]
    parsed_worker_args = task041_balh_workflow._parser().parse_args(worker_args)
    assert parsed_worker_args.task041_balh_candidate_disable_time_stop is True

    shortwave_candidate = next(
        path for path in BALH_INPUTS if "13p5nm" in path.name and "balh" in path.name
    )
    assert run_case.main(
        [
            str(shortwave_candidate),
            "--producer-packet-root",
            str(packet_root),
            "--task041-balh-candidate-disable-time-stop",
        ]
    ) == 2


def test_task041_consumer_time_stop_combines_override_and_case_policy():
    five_nm_limits = task041_balh_phase_limits_for_model(
        TASK041_BALH_5NM_CANDIDATE_MODEL_ID, "consumer"
    )
    two_nm_limits = task041_balh_phase_limits_for_model(
        TASK041_BALH_2NM_CANDIDATE_MODEL_ID, "consumer"
    )

    assert supervisor._task041_consumer_time_stop_enforced(
        balh=True,
        disable_time_stop=True,
        phase_limits={"consumer": five_nm_limits},
    ) is False
    assert supervisor._task041_consumer_time_stop_enforced(
        balh=True,
        disable_time_stop=False,
        phase_limits={"consumer": five_nm_limits},
    ) is True
    assert supervisor._task041_consumer_time_stop_enforced(
        balh=True,
        disable_time_stop=False,
        phase_limits={"consumer": two_nm_limits},
    ) is False
    assert supervisor._task041_consumer_time_stop_enforced(
        balh=False,
        disable_time_stop=False,
        phase_limits={},
    ) is True


def test_task041_pair_worker_time_stop_policy_keeps_producer_fact(
    tmp_path: Path, monkeypatch
):
    from benchmarks import run_task037b_hybrid_iterative as recovery
    from benchmarks import task041_exact_side_workflow as worker

    class FakeComm:
        rank = 0
        size = 8

        @staticmethod
        def bcast(value, root):
            assert root == 0
            return value

        @staticmethod
        def Barrier():
            return None

    candidate_path = (
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/5nm_p6h4_m480_mpi8_balh.dat"
    )
    packet_identity_path = tmp_path / "unused_packet_identity.json"
    packet_identity_path.write_text("{}\n", encoding="utf-8")
    probe_manifest = _write_task041_fixed_pair_manifest(
        tmp_path,
        packet_manifest_sha256="d" * 64,
        packet_identity_path=packet_identity_path,
        source_sha="c" * 40,
    )
    monkeypatch.setattr(worker, "_environment_snapshot", lambda: {"marker": "test"})
    monkeypatch.setattr(worker, "_write_rank_pid_affinity", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker, "_memavailable_bytes", lambda: 0)
    monkeypatch.setattr(
        worker,
        "_resource_snapshot",
        lambda: {
            "memory_authority_bytes": 100,
            "job_no_swap": True,
            "process_tree": {
                "all_status_readable": True,
                "rss_bytes": 100,
                "swap_bytes": 0,
            },
        },
    )
    monkeypatch.setattr(
        recovery,
        "release_frozen_m10_objects",
        lambda setup, comm, communicator: {"pass": True},
    )

    run_directory = tmp_path / "pair_worker_preflight"
    with pytest.raises(worker.Task041ModePrepError, match="MemAvailable"):
        worker.run_task041_consumer(
            input_path=candidate_path,
            packet_manifest=tmp_path / "unused_packet_manifest.json",
            packet_identity=packet_identity_path,
            packet_manifest_sha256="d" * 64,
            run_directory=run_directory,
            source_sha="b" * 40,
            candidate=True,
            comm=FakeComm(),
            performance_profile=TASK041_SCHUR_SPEED_V2_PROFILE,
            task041_rhs_probe_manifest=probe_manifest,
            side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
            comparison_mode=task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
        )

    summary = json.loads(
        (run_directory / "consumer_summary.json").read_text(encoding="utf-8")
    )
    assert summary["time_stop_policy"]["producer_enforced"] is True
    assert summary["time_stop_policy"]["producer_invocation"] == "not_run"
    assert summary["time_stop_policy"]["consumer_enforced"] is False
    assert summary["limits"]["timeout_seconds"] is None


def test_task041_balh_worker_time_override_keeps_memory_and_swap_gates(monkeypatch):
    from benchmarks import task041_exact_side_workflow as worker

    limits = {"hard_memory_bytes": 1000, "timeout_seconds": 43200}
    monkeypatch.setattr(worker.time, "monotonic", lambda: 43201.0)
    worker._check_resource(
        {"memory_authority_bytes": 100, "job_no_swap": True},
        0.0,
        limits,
        enforce_time_stop=False,
    )
    with pytest.raises(worker.Task041ModePrepError, match="hard RSS"):
        worker._check_resource(
            {"memory_authority_bytes": 1000, "job_no_swap": True},
            0.0,
            limits,
            enforce_time_stop=False,
        )
    with pytest.raises(worker.Task041ModePrepError, match="swap"):
        worker._check_resource(
            {"memory_authority_bytes": 100, "job_no_swap": False},
            0.0,
            limits,
            enforce_time_stop=False,
        )


def test_task041_balh_early_identity_failure_keeps_error_classification(tmp_path):
    specification = _specification(
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_exact.dat"
    )
    run_root = tmp_path / "early_identity_failure"
    run_root.mkdir()
    result = run_task041_public_supervisor(
        specification,
        source_sha="bad",
        run_directory=run_root,
        compute_wall_ledger_path=tmp_path / "unused_ledger.json",
    )
    assert result["result_classification"] == "task041_identity_failure"
    assert result["error"]["type"] == "Task041SupervisorError"
    assert "UnboundLocalError" not in result["error"]["message"]


@pytest.mark.parametrize(
    ("candidate_filename", "registered_case"),
    (
        ("13p5nm_p6h10_m120_mpi8_balh.dat", False),
        ("2nm_p6h1p5_m1200_mpi8_balh.dat", True),
    ),
    ids=("legacy-balh", "registered-2nm"),
)
def test_task041_balh_public_fresh_phases_share_cumulative_budget(
    tmp_path: Path, monkeypatch, candidate_filename, registered_case
):
    candidate = _specification(
        REPOSITORY_ROOT
        / "input/official/task041/side_balh"
        / candidate_filename
    )
    from benchmarks import task041_balh_workflow
    from src.runners import task041_supervisor as supervisor

    candidate_model = str(candidate.identity["model_id"])
    case_contract = (
        task041_balh_service_contract(candidate_model)
        if registered_case
        else None
    )
    ledger_path = tmp_path / (
        case_contract["ledger"]["filename"]
        if case_contract is not None
        else "compute_wall_ledger.json"
    )
    ledger_payload = {
        "schema": "task041.compute_wall_ledger.v1",
        "limit_seconds": 172800.0,
        "used_compute_wall_seconds": 10.0,
        "used_status": "measured",
        "basis": "test-local BALH fresh-phase ledger",
        "measured": {"status": "measured", "seconds": 10.0, "records": []},
        "derived": {"status": "not_measured", "seconds": None},
    }
    if case_contract is not None:
        ledger_payload.update(
            {
                "case_id": candidate_model,
                "profile_id": None,
                "limit_seconds": None,
                "budget_semantics": case_contract["budget_semantics"],
            }
        )
    ledger_path.write_text(
        json.dumps(ledger_payload, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    phase_calls = []
    popen_calls = []
    real_run_phase = supervisor._run_phase

    class FakeProcess:
        next_pid = 532000

        def __init__(self):
            self.pid = FakeProcess.next_pid
            FakeProcess.next_pid += 1
            self.poll_count = 0

        def poll(self):
            self.poll_count += 1
            return None if self.poll_count == 1 else 0

        def wait(self):
            return 0

    def fake_popen(argv, **kwargs):
        del kwargs
        popen_calls.append(list(argv))
        return FakeProcess()

    def fake_sample(_pid):
        return {
            "memory_authority_bytes": 100,
            "job_no_swap": True,
            "host_memory": {"mem_available_bytes": 2**40},
            "process_tree": {
                "rss_bytes": 100,
                "swap_bytes": 0,
                "all_status_readable": True,
                "smaps": {"pss_bytes": 80, "uss_bytes": 60},
            },
            "job_cgroup": {
                "dedicated_job_cgroup": False,
                "swap_current_bytes": 0,
                "ancestor_hard_limit_state": "max_or_unlimited",
                "ancestor_memory": [
                    {"memory_limit_state": "max_or_unlimited"}
                ],
            },
        }

    def fake_run_phase(phase, argv, phase_root, **kwargs):
        phase_calls.append(
            {
                "phase": phase,
                "cumulative_compute_used_seconds": kwargs[
                    "cumulative_compute_used_seconds"
                ],
                "enforce_time_stops": kwargs["enforce_time_stops"],
            }
        )
        return real_run_phase(
            phase,
            argv,
            phase_root,
            **kwargs,
        )

    identity = candidate.as_jsonable()

    def fake_validate(producer_root, specification, source_sha):
        del specification
        manifest = producer_root / "selected_mode_packet" / "manifest.json"
        return {
            "summary": {"environment": {}},
            "identity": identity,
            "identity_path": str(producer_root / "packet_identity.json"),
            "manifest": str(manifest),
            "manifest_sha256": "c" * 64,
            "compact_manifest": {
                "path": str(manifest),
                "sha256": "c" * 64,
                "identity": identity,
            },
            "producer_source_sha": source_sha,
        }

    monkeypatch.setattr(supervisor, "_run_phase", fake_run_phase)
    if registered_case:
        monkeypatch.setattr(supervisor, "_outer_mpi_size", lambda: 1)
        monkeypatch.setattr(supervisor, "_outer_mpi_rank", lambda: 0)
        monkeypatch.delenv("OMPI_COMM_WORLD_SIZE", raising=False)
        monkeypatch.delenv("OMPI_COMM_WORLD_RANK", raising=False)
    else:
        monkeypatch.setattr(
            supervisor,
            "_outer_mpi_launch_identity",
            lambda: {
                "mpi_size": 1,
                "mpi_rank": 0,
                "markers": {"OMPI_COMM_WORLD_SIZE": "1", "OMPI_COMM_WORLD_RANK": "0"},
            },
        )
    monkeypatch.setattr(
        supervisor,
        "_git_identity",
        lambda repository_root, source_sha: {
            "head": source_sha,
            "branch": supervisor.TASK041_BRANCH,
            "source_sha": source_sha,
            "worktree_clean": True,
        },
    )
    monkeypatch.setattr(
        supervisor,
        "_environment_snapshot",
        lambda repository_root: {"native_marker": "1", "platform": "test"},
    )
    monkeypatch.setattr(
        supervisor,
        "_child_environment",
        lambda: {name: "1" for name in supervisor.TASK041_REQUIRED_THREADS},
    )
    monkeypatch.setattr(
        supervisor,
        "_task041_builders",
        lambda: {
            "balh_mode_prep": lambda *_args: ["mode-prep"],
            "balh_candidate_consumer": lambda *_args, **_kwargs: [
                "candidate-consumer"
            ],
        },
    )
    monkeypatch.setattr(task041_balh_workflow, "validate_balh_producer_packet", fake_validate)
    observed_schedules = []

    def fake_consumer_result(
        consumer_root,
        process_group_gone,
        expected_side_setup_schedule=None,
        **kwargs,
    ):
        observed_schedules.append(expected_side_setup_schedule)
        assert expected_side_setup_schedule is None
        if registered_case:
            assert kwargs["expected_diagnostic_output"] is True
            assert kwargs["expected_diagnostic_model_id"] == candidate_model
            return {
                "complete": True,
                "classification": "DIAGNOSTIC_RESULT_AVAILABLE",
                "worker_classification": "DIAGNOSTIC_RESULT_AVAILABLE",
                "diagnostic_result_available": True,
                "completion_scope": "formal",
                "qualification_status": "unqualified",
                "diagnostic_output": {"result_available": True},
                "process_group_gone": process_group_gone,
                "factor_inventory": {},
            }
        return {
            "complete": True,
            "classification": "worker_exit0",
            "worker_classification": "TASK041_CONSUMER_PASS",
            "process_group_gone": process_group_gone,
            "factor_inventory": {},
        }

    monkeypatch.setattr(
        supervisor,
        "_consumer_result",
        fake_consumer_result,
    )

    source_sha = "e" * 40
    fresh_run = tmp_path / "fresh_public_run"
    fresh_run.mkdir()
    result = supervisor.run_task041_public_supervisor(
        candidate,
        source_sha=source_sha,
        run_directory=fresh_run,
        compute_wall_ledger_path=ledger_path,
        python_executable="python",
        popen_factory=fake_popen,
        sample_factory=fake_sample,
        process_group_gone=lambda _pid: True,
        sleep=lambda _seconds: None,
    )
    assert result["result_classification"] == "worker_exit0"
    assert len(popen_calls) == 2
    assert observed_schedules == [None]
    assert [call["enforce_time_stops"] for call in phase_calls] == [
        True,
        not registered_case,
    ]
    assert phase_calls[0]["cumulative_compute_used_seconds"] == pytest.approx(10.0)
    producer_seconds = result["phase_results"]["producer"]["phase_wall_seconds"]
    budget = result["compute_wall_budget"]
    if registered_case:
        assert phase_calls[1]["cumulative_compute_used_seconds"] == pytest.approx(
            10.0
        )
        assert result["phase_results"]["producer"]["limits"][
            "timeout_seconds"
        ] == 345600
        assert result["phase_results"]["producer"]["time_stop_enforced"] is True
        assert result["phase_results"]["consumer"]["limits"][
            "timeout_seconds"
        ] is None
        assert result["phase_results"]["consumer"]["limits"][
            "cumulative_compute_limit_seconds"
        ] is None
        assert result["phase_results"]["consumer"]["time_stop_enforced"] is False
        assert result["time_stop_policy"]["consumer_enforced"] is False
        assert result["status"] == "completed_with_diagnostics"
        assert result["qualification_status"] == "unqualified"
        assert budget["limit_seconds"] is None
        assert budget["remaining_after_seconds"] is None
        updated = supervisor._read_json(ledger_path)
        assert updated["case_id"] == candidate_model
        assert updated["profile_id"] is None
        assert updated["limit_seconds"] is None
        assert updated["used_compute_wall_seconds"] == pytest.approx(
            10.0 + result["compute_wall_seconds"]
        )
    else:
        assert phase_calls[1]["cumulative_compute_used_seconds"] == pytest.approx(
            10.0 + producer_seconds
        )
        assert budget["used_before_seconds"] == pytest.approx(10.0)
        assert budget["used_after_seconds"] == pytest.approx(
            10.0 + result["compute_wall_seconds"]
        )
    assert result["phase_results"]["producer"].get("reused") is not True


@pytest.mark.parametrize("p4_pair", [False, True], ids=["public", "fixed-pair"])
def test_task041_balh_reused_public_producer_starts_only_one_consumer(
    tmp_path: Path, monkeypatch, p4_pair: bool
):
    input_prefix = "5nm_p6h4_m480_mpi8" if p4_pair else "13p5nm_p6h10_m120_mpi8"
    exact = _specification(
        REPOSITORY_ROOT
        / f"input/official/task041/side_balh/{input_prefix}_exact.dat"
    )
    candidate = _specification(
        REPOSITORY_ROOT
        / f"input/official/task041/side_balh/{input_prefix}_balh.dat"
    )
    from benchmarks.task041_balh_workflow import build_task041_balh_packet_identity
    from src.runners import task041_supervisor as supervisor

    producer_source_sha = "a" * 40
    consumer_source_sha = "b" * 40
    producer_identity = build_task041_balh_packet_identity(
        exact, exact.as_jsonable(), producer_source_sha, resolved_config_sha256(exact)
    )
    old_run = tmp_path / "producer_public_run"
    producer_root = old_run / "producer"
    packet_root = producer_root / "selected_mode_packet"
    packet_root.mkdir(parents=True)
    manifest_path = packet_root / "manifest.json"
    manifest_path.write_text("{\"manifest\":true}\n", encoding="utf-8")
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    packet_identity_path = producer_root / "packet_identity.json"
    packet_identity_path.write_text(
        json.dumps(producer_identity, sort_keys=True) + "\n", encoding="utf-8"
    )
    probe_manifest = (
        _write_task041_fixed_pair_manifest(
            tmp_path,
            packet_manifest_sha256=manifest_sha,
            packet_identity_path=packet_identity_path,
            source_sha=consumer_source_sha,
        )
        if p4_pair
        else None
    )
    (producer_root / "mode_prep_summary.json").write_text(
        json.dumps(
            {
                "classification": "TASK041_MODE_PREP_PACKET_READY",
                "source_sha": producer_source_sha,
                "cleanup": {"producer_scope_released": True},
                "packet": {"manifest_sha256": manifest_sha},
                "environment": {"platform": "test"},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    producer_phase = {
        "returncode": 0,
        "process_group_gone": True,
        "termination_reason": None,
        "rss_drop": {"pass": True, "before_process_tree_rss_bytes": 123},
        "sample_count": 2,
        "limits": {"timeout_seconds": 10},
        "timeout_scope": "phase",
        "phase_wall_seconds": 2.0,
        "workflow_wall_seconds": 2.0,
        "peak_memory_authority_bytes": 300,
        "peak_process_tree_rss_bytes": 290,
        "peak_process_tree_swap_bytes": 0,
        "peak_dedicated_cgroup_swap_bytes": 0,
        "peak_swap_bytes": 0,
    }
    supervisor_identity = {
        "model_id": producer_identity["model_id"],
        "run_id": producer_identity["run_id"],
        "input_sha256": producer_identity["input_sha256"],
        "resolved_config_sha256": producer_identity["resolved_sha256"],
        "physical_model_sha256": producer_identity["physical_sha256"],
        "requested_modes": producer_identity["mode_count"],
        "mpi_size": producer_identity["mpi_size"],
    }
    (old_run / "supervisor_summary.json").write_text(
        json.dumps(
            {
                "status": "failed",
                "result_classification": "task041_consumer_stage_failure",
                "source_sha": producer_source_sha,
                "identity": supervisor_identity,
                "phase_results": {"producer": producer_phase},
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    (old_run / "selected_mode_manifest.json").write_text(
        json.dumps(
            {
                "path": str(manifest_path.resolve()),
                "sha256": manifest_sha,
                "identity": producer_identity,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    packet = validate_balh_producer_packet(
        producer_root,
        candidate,
        consumer_source_sha,
        require_public_supervisor_summary=True,
    )
    assert packet["producer_resource_qualified"] is True
    assert Path(packet["compact_manifest"]["path"]).is_absolute()
    assert Path(packet["producer_supervisor_summary"]).resolve() == (
        old_run / "supervisor_summary.json"
    ).resolve()

    popen_calls: list[list[str]] = []

    class FakeProcess:
        pid = 531351

        def __init__(self):
            self._poll_count = 0

        def poll(self):
            self._poll_count += 1
            return None if self._poll_count == 1 else 0

        def wait(self):
            return 0

    def fake_popen(argv, **kwargs):
        del kwargs
        popen_calls.append(list(argv))
        return FakeProcess()

    def fake_sample(_pid):
        return {
            "memory_authority_bytes": 200,
            "job_no_swap": True,
            "host_memory": {"mem_available_bytes": 2**40},
            "process_tree": {
                "all_status_readable": True,
                "rss_bytes": 190,
                "swap_bytes": 0,
                "smaps": {"pss_bytes": 170, "uss_bytes": 160},
            },
            "job_cgroup": {
                "dedicated_job_cgroup": True,
                "readable": True,
                "memory_current_bytes": 200,
                "swap_current_bytes": 0,
                "ancestor_hard_limit_state": "max_or_unlimited",
                "ancestor_memory_headroom_bytes": None,
                "ancestor_memory": [
                    {
                        "memory_limit_state": "max_or_unlimited",
                        "memory_current_bytes": 200,
                        "memory_headroom_bytes": None,
                    }
                ],
            },
        }

    def fake_outer_mpi_launch_identity(*args, **kwargs):
        del args, kwargs
        return {
            "mpi_size": 1,
            "mpi_rank": 0,
            "markers": {"OMPI_COMM_WORLD_SIZE": "1", "OMPI_COMM_WORLD_RANK": "0"},
        }

    monkeypatch.setattr(
        supervisor,
        "_outer_mpi_launch_identity",
        fake_outer_mpi_launch_identity,
    )
    monkeypatch.setattr(
        supervisor,
        "_git_identity",
        lambda repository_root, source_sha: {
            "head": source_sha,
            "branch": supervisor.TASK041_BRANCH,
            "source_sha": source_sha,
            "worktree_clean": True,
        },
    )
    monkeypatch.setattr(
        supervisor,
        "_environment_snapshot",
        lambda repository_root: {"native_marker": "1", "platform": "test"},
    )
    monkeypatch.setattr(
        supervisor,
        "_child_environment",
        lambda: {name: "1" for name in supervisor.TASK041_REQUIRED_THREADS},
    )
    observed_schedules = []
    expected_pair_mode = task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE
    expected_schedule = (
        TASK041_SEQUENTIAL_COMPONENT_SCHEDULE if p4_pair else None
    )
    expected_comparison = expected_pair_mode if p4_pair else None

    def fake_consumer_result(
        consumer_root,
        process_group_gone,
        expected_side_setup_schedule=None,
        expected_comparison_mode=None,
        representative_rhs_binding=None,
    ):
        observed_schedules.append(expected_side_setup_schedule)
        assert expected_side_setup_schedule == expected_schedule
        assert expected_comparison_mode == expected_comparison
        if p4_pair:
            assert representative_rhs_binding["path"] == str(probe_manifest)
        return {
            "complete": True,
            "classification": "worker_exit0",
            "worker_classification": (
                "TASK041_REPRESENTATIVE_RHS_COMPLETED"
                if p4_pair
                else "TASK041_CONSUMER_PASS"
            ),
            "completion_scope": "representative_rhs" if p4_pair else "formal",
            "process_group_gone": process_group_gone,
            "factor_inventory": {},
        }

    monkeypatch.setattr(
        supervisor,
        "_consumer_result",
        fake_consumer_result,
    )

    candidate_run = tmp_path / "candidate_public_run"
    candidate_run.mkdir()
    supervision_record_path = None
    v5_ledger_before = None
    if p4_pair:
        ledger_path = tmp_path / "review_v5_ledger.json"
        ledger_path.write_text(
            json.dumps(
                {
                    "schema": "task041.review_v5.r1_load_ledger.v1",
                    "charged_seconds": 8061.882139588,
                    "ledger_status": "derived",
                    "scope": "test V5 compatibility view",
                    "entries": [{"id": "prior_f2", "charged_seconds": 393}],
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        v5_ledger_before = ledger_path.read_bytes()
        monkeypatch.setattr(
            task041_balh_workflow,
            "task041_review_v5_ledger_path",
            lambda _repository_root: ledger_path.resolve(),
        )
        monkeypatch.setenv("INVOCATION_ID", "task041-f3c4-public-pair-test")
        probe_sha = hashlib.sha256(probe_manifest.read_bytes()).hexdigest()
        supervision_record_path = tmp_path / "service_supervision_record.json"
        supervision_record_path.write_text(
            json.dumps(
                {
                    "profile_id": TASK041_SCHUR_SPEED_V2_PROFILE,
                    "model_id": candidate.identity["model_id"],
                    "source_sha": consumer_source_sha,
                    "scope": TASK041_REPRESENTATIVE_RHS_SCOPE,
                    "ledger_owner": "service_finalizer",
                    "parent_pid": os.getppid(),
                    "invocation_id": "task041-f3c4-public-pair-test",
                    "side_setup_schedule": TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
                    "comparison_mode": expected_pair_mode,
                    "representative_rhs_probe": {
                        "path": str(probe_manifest),
                        "sha256": probe_sha,
                    },
                    "ledger_path": str(ledger_path.resolve()),
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        def reject_duplicate_ledger_write(*args, **kwargs):
            del args, kwargs
            raise AssertionError("public supervisor must defer V5 append to finalizer")

        monkeypatch.setattr(
            supervisor,
            "_write_task041_compute_wall_ledger",
            reject_duplicate_ledger_write,
        )
    else:
        ledger_path = tmp_path / "compute_wall_ledger.json"
        ledger_path.write_text(
            json.dumps(
                {
                    "schema": "task041.compute_wall_ledger.v1",
                    "limit_seconds": 172800.0,
                    "used_compute_wall_seconds": 0.0,
                    "used_status": "measured",
                    "basis": "test-local BALH mock ledger",
                    "measured": {
                        "status": "measured",
                        "seconds": 0.0,
                        "records": [],
                    },
                    "derived": {"status": "not_measured", "seconds": None},
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
    result = supervisor.run_task041_public_supervisor(
        candidate,
        source_sha=consumer_source_sha,
        run_directory=candidate_run,
        compute_wall_ledger_path=None if p4_pair else ledger_path,
        python_executable="python",
        producer_packet_root=producer_root,
        performance_profile=TASK041_SCHUR_SPEED_V2_PROFILE if p4_pair else None,
        task041_rhs_probe_manifest=probe_manifest,
        task041_side_setup_schedule=(
            TASK041_SEQUENTIAL_COMPONENT_SCHEDULE if p4_pair else None
        ),
        task041_comparison_mode=expected_pair_mode if p4_pair else None,
        task041_supervision_record=supervision_record_path,
        popen_factory=fake_popen,
        sample_factory=fake_sample,
        process_group_gone=lambda _pid: True,
        sleep=lambda _: None,
    )
    assert result["result_classification"] == "worker_exit0"
    assert len(popen_calls) == 1
    assert observed_schedules == [expected_schedule]
    assert popen_calls[0][popen_calls[0].index("--phase") + 1] == "candidate-consumer"
    if p4_pair:
        command = popen_calls[0]
        assert command[command.index("--cpu-list") + 1] == "1-8"
        resolved_python = str((REPOSITORY_ROOT / "python").resolve())
        python_index = command.index(resolved_python)
        assert command[python_index - 2 : python_index + 1] == [
            "numactl",
            "--membind=0",
            resolved_python,
        ]
        assert command[command.index("--task041-comparison-mode") + 1] == (
            expected_pair_mode
        )
        phase = result["phase_results"]["consumer"]
        assert phase["limits"]["timeout_seconds"] is None
        assert phase["limits"]["cumulative_compute_limit_seconds"] is None
        assert phase["time_stop_enforced"] is False
        assert result["time_stop_policy"]["producer_enforced"] is True
        assert result["time_stop_policy"]["producer_invocation"] == "not_run"
        assert result["time_stop_policy"]["consumer_enforced"] is False
        assert result["ledger_owner"] == "service_finalizer"
        assert result["compute_wall_budget"]["ledger_update"] == (
            "deferred_to_service_finalizer"
        )
        assert ledger_path.read_bytes() == v5_ledger_before
    else:
        assert result["phase_results"]["consumer"]["time_stop_enforced"] is True
    assert result["phase_results"]["producer"]["reused"] is True
    assert result["phase_results"]["producer"]["returncode"] == 0
    assert result["phase_results"]["producer"]["process_group_gone"] is True
    assert result["resource_authority"]["status"] == "measured_with_inherited_producer"
    envelope = result["resource_authority"]["derived_common_producer_envelope"]
    assert envelope["status"] == "derived"
    assert envelope["peak"]["memory_authority_bytes"] == 300
    assert envelope["peak"]["pss_bytes"] is None
    assert envelope["peak"]["uss_bytes"] is None
    assert envelope["measurement_status"]["pss_bytes"] == "not_measured"
    assert envelope["measurement_status"]["uss_bytes"] == "not_measured"
    assert envelope["producer"]["values"]["memory_authority_bytes"] == 300
    assert result["resource_authority"]["workflow_peak"]["memory_authority_bytes"] == 200
    assert envelope["producer"]["supervisor_summary_sha256"] == hashlib.sha256(
        (old_run / "supervisor_summary.json").read_bytes()
    ).hexdigest()
    summary = json.loads(
        (tmp_path / "candidate_public_run" / "supervisor_summary.json").read_text(
            encoding="utf-8"
        )
    )
    assert summary["resource_authority"]["workflow_peak"]["memory_authority_bytes"] == 200
    reused_budget = result["compute_wall_budget"]
    consumer_wall = result["phase_results"]["consumer"]["phase_wall_seconds"]
    if p4_pair:
        assert reused_budget["used_before_seconds"] == pytest.approx(
            8061.882139588
        )
        assert reused_budget["current_invocation_seconds"] == pytest.approx(
            consumer_wall
        )
        assert reused_budget["used_after_seconds"] is None
    else:
        assert reused_budget["used_before_seconds"] == pytest.approx(0.0)
        assert reused_budget["current_invocation_seconds"] == pytest.approx(
            consumer_wall
        )
        assert reused_budget["used_after_seconds"] == pytest.approx(consumer_wall)
        assert reused_budget["used_after_seconds"] < producer_phase["phase_wall_seconds"]

    incomplete_summary = json.loads(
        (old_run / "supervisor_summary.json").read_text(encoding="utf-8")
    )
    del incomplete_summary["phase_results"]["producer"][
        "peak_process_tree_rss_bytes"
    ]
    (old_run / "supervisor_summary.json").write_text(
        json.dumps(incomplete_summary, sort_keys=True) + "\n", encoding="utf-8"
    )
    incomplete_packet = validate_balh_producer_packet(
        producer_root,
        candidate,
        consumer_source_sha,
        require_public_supervisor_summary=True,
    )
    assert incomplete_packet["producer_resource_qualified"] is False
    assert incomplete_packet["producer_phase"]["peak_process_tree_rss_bytes"] is None


def _write_representative_result_fixture(tmp_path: Path):
    from benchmarks.task041_balh_workflow import (
        _TASK041_REPRESENTATIVE_RHS_EXPECTED,
        TASK041_REPRESENTATIVE_RHS_SCOPE,
    )

    root = tmp_path / "representative_consumer"
    output = root / "numerical_output"
    output.mkdir(parents=True)
    source_sha = "c" * 40
    probe_path = tmp_path / "representative_rhs.json"
    probe_path.write_text('{"fixed":true}\n', encoding="utf-8")
    probe_sha = hashlib.sha256(probe_path.read_bytes()).hexdigest()
    packet_manifest_sha = "d" * 64
    packet_identity_path = tmp_path / "packet_identity.json"
    packet_identity_path.write_text('{"packet":"fixed"}\n', encoding="utf-8")
    packet_identity_sha = hashlib.sha256(packet_identity_path.read_bytes()).hexdigest()
    entries = [
        dict(zip(("ordinal", "side", "branch", "audit_index", "formal_column", "branch_ordinal"), (ordinal, *values)))
        for ordinal, values in enumerate(_TASK041_REPRESENTATIVE_RHS_EXPECTED)
    ]
    count_delta = dict.fromkeys(
        ("pc", "Q", "H6", "A6", "P", "PH_audit", "p4_backsolve"), 1
    )
    raw_rows, result_entries = [], []
    for entry in entries:
        ordinal = entry["ordinal"]
        audit = {
            **{key: entry[value] for key, value in {
                "representative_ordinal": "ordinal",
                "source_audit_index": "audit_index",
                "formal_column": "formal_column",
                "branch_ordinal": "branch_ordinal",
            }.items()},
            "status": "KSP_CONVERGED",
            "reason": 2,
            "ksp_positive": True,
            "explicit_true_target_reached": True,
            "relative_residual": 1.0e-3,
            "rhs_norm": 1.0,
            "residual_norm": 1.0e-3,
            "ksp_max_it": 128,
            "ksp_rtol": 1.0e-2,
            "counts": {"delta": count_delta},
        }
        raw_rows.append({"phase": "representative_rhs", "side": entry["side"], "audit": audit})
        response_dir = root / "response" / str(ordinal)
        response_dir.mkdir(parents=True)
        shards = []
        for rank in range(8):
            name = f"rank{rank:04d}.npz"
            payload = f"response-{ordinal}-{rank}".encode()
            path = response_dir / name
            path.write_bytes(payload)
            shards.append({
                "rank": rank, "path": name,
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": 1, "ownership_range": [rank, rank + 1],
            })
        response_identity = {
            "schema": "task041.representative_rhs.response_identity.v1",
            "source_sha": source_sha,
            "probe_manifest_sha256": probe_sha,
            "packet_manifest_sha256": packet_manifest_sha,
            "ordinal": ordinal, "side": entry["side"],
            "formal_column": entry["formal_column"],
            "branch_ordinal": entry["branch_ordinal"],
        }
        identity_sha = hashlib.sha256(
            json.dumps(response_identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        response_manifest_path = response_dir / "manifest.json"
        response_manifest_path.write_text(
            json.dumps({
                "schema": "myfenics.full3d.pre_recovery_packet.v1",
                "identity": response_identity, "identity_sha256": identity_sha,
                "rank_count": 8, "global_size": 8, "shards": shards,
                "metadata": {},
            }, sort_keys=True) + "\n", encoding="utf-8"
        )
        response_manifest_sha = hashlib.sha256(response_manifest_path.read_bytes()).hexdigest()
        result_entries.append({
            **entry, "status": "completed", "audit": audit,
            "artifact": {
                "manifest": str(response_manifest_path),
                "manifest_sha256": response_manifest_sha,
                "identity_sha256": identity_sha,
            },
            "rank_shards": [
                {
                    "rank": shard["rank"], "ownership_range": shard["ownership_range"],
                    "local_size": 1, "dtype": "complex128",
                    "owned_rhs_sha256": hashlib.sha256(
                        f"rhs-{ordinal}-{shard['rank']}".encode()
                    ).hexdigest(),
                    "owned_response_sha256": shard["sha256"],
                    "packet_manifest_sha256": packet_manifest_sha,
                    "packet_shard_path": shard["path"],
                    "packet_shard_sha256": shard["sha256"],
                    "response_packet_manifest_sha256": response_manifest_sha,
                }
                for shard in shards
            ],
        })
    raw_path = output / "representative_rhs_audits.jsonl"
    raw_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in raw_rows),
        encoding="utf-8",
    )
    binding = {
        "path": str(probe_path), "sha256": probe_sha,
        "scope": TASK041_REPRESENTATIVE_RHS_SCOPE,
        "budget": {"group": "shared_S0_S1_S3"}, "entries": entries,
        "source_audit": {
            "rhs_audit_path": str(raw_path),
            "rhs_audit_sha256": hashlib.sha256(raw_path.read_bytes()).hexdigest(),
        },
        "packet_binding": {
            "packet_manifest_sha256": packet_manifest_sha,
            "packet_identity": str(packet_identity_path),
            "packet_identity_sha256": packet_identity_sha,
        },
    }
    summary = {
        "schema": "task041.side_balh.candidate_consumer.v1",
        "source_sha": source_sha,
        "status": "task041_representative_rhs_completed",
        "classification": "TASK041_REPRESENTATIVE_RHS_COMPLETED",
        "representative_rhs_probe": {
            "path": str(probe_path), "sha256": probe_sha,
            "scope": TASK041_REPRESENTATIVE_RHS_SCOPE,
            "budget_group": "shared_S0_S1_S3",
        },
        "identity": {
            "source_sha": source_sha,
            "model_id": "task041_5nm_balh_hybrid_iterative_p6h4_m480_mpi8",
            "mode_count": 480, "mpi_size": 8,
        },
        "packet": {"manifest_sha256": packet_manifest_sha, "identity": str(packet_identity_path)},
        "setup": {"admission_audit": {"pass": True, "global_operator_identity": {"pass": True}}},
        "representative_rhs": {"entries": result_entries},
        "matrix_inventory": {
            "qep_calls": 0, "consumer_qep_required": False,
            "p4_factor_count_at_setup": 2, "nested_iterative_ksp_count_at_setup": 2,
            "p6_factor_count": 0, "global_direct_factor_count": 0,
            "p4_factor_count_after_cleanup": {"bottom": 0, "top": 0},
            "nested_iterative_ksp_count_after_cleanup": {"bottom": 0, "top": 0},
        },
        "lifecycle": {
            "setup_released": True, "representative_rhs_cleanup_pass": True,
            "rss_marker_emitted": True,
        },
        "markers": {"observed": [
            "bottom_construction_cleanup", "top_construction_cleanup", "final_cleanup_complete"
        ]},
        "gates": {"pass": False}, "official_rta": {"status": "not_run"},
        "formal": {"status": "not_run"},
    }
    return root, summary, binding, raw_path


def _sequential_live(side: str, p4: int, nested: int) -> dict[str, object]:
    by_side = (
        {side: {"p4_factor_count": p4, "nested_iterative_ksp_count": nested}}
        if p4 or nested
        else {}
    )
    return {
        "by_side": by_side,
        "live_side_count": int(bool(p4 or nested)),
        "live_component_counts": {
            "p4_factor": p4,
            "nested_iterative_ksp": nested,
        },
        "live_component_count_sum": p4 + nested,
    }


def _add_sequential_lifecycle_fixture(
    root: Path, summary: dict[str, object]
) -> Path:
    boundaries: list[dict[str, object]] = []
    identity_checks: dict[str, dict[str, object]] = {}
    marker_rows: list[dict[str, object]] = []
    elapsed = 0.0

    for side in ("bottom", "top"):
        diagnostics = {
            "destroyed": True,
            "p4_factor_count": 0,
            "nested_iterative_ksp_count": 0,
        }
        events = (
            ("identity", "before_build", "system_setup_stage", 0, 0),
            ("boundary", "before_build", "system_setup_stage", 0, 0),
            ("boundary", "ready", f"{side}_factor_ready", 1, 1),
            ("identity", "after_admission", "system_setup_stage", 0, 0),
            ("identity", "before_release", "system_setup_stage", 0, 0),
            ("boundary", "before_release", "system_setup_stage", 1, 1),
            (
                "boundary",
                "released",
                f"{side}_construction_cleanup",
                0,
                0,
            ),
            ("identity", "after_release", "system_setup_stage", 0, 0),
        )
        for kind, event, stage, p4, nested in events:
            elapsed += 0.1
            if kind == "identity":
                label = f"{side}_{event}"
                check = {
                    "label": label,
                    "action_relative": 0.0,
                    "rhs_relative": 0.0,
                    "source_unchanged_relative": 0.0,
                    "pass": True,
                }
                identity_checks[label] = check
                marker_rows.append(
                    {
                        "stage": stage,
                        "wall_seconds": elapsed,
                        "detail": {
                            "side": side,
                            "substage": "global_identity",
                            "identity_check": check,
                        },
                    }
                )
                continue
            boundary: dict[str, object] = {
                "side": side,
                "event": event,
                "schedule": TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
                "clock": "CLOCK_MONOTONIC",
                "live": _sequential_live(side, p4, nested),
            }
            if event == "ready":
                boundary["created_at_boundary"] = {
                    "side_inverse": 1,
                    "p4_factor": 1,
                    "nested_iterative_ksp": 1,
                }
            detail: dict[str, object] = {
                "side": side,
                "substage": "side_lifecycle",
                "lifecycle_boundary": boundary,
            }
            if event == "released":
                detail["diagnostics"] = diagnostics
            boundaries.append(boundary)
            marker_rows.append(
                {"stage": stage, "wall_seconds": elapsed, "detail": detail}
            )

    marker_path = root / "markers.jsonl"
    marker_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in marker_rows),
        encoding="utf-8",
    )
    setup_counts = {
        "p4_factor_created_total": 2,
        "nested_iterative_ksp_created_total": 2,
        "total_created": 2,
        "p4_factor_simultaneously_live_peak": 1,
        "nested_iterative_ksp_simultaneously_live_peak": 1,
        "simultaneously_live_peak": 1,
        "simultaneously_live_component_peak": 2,
        "component_cleanup_pass": True,
    }
    setup = summary["setup"]
    assert isinstance(setup, dict)
    setup["side_setup_schedule"] = TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
    setup["side_setup"] = {
        "side_setup_schedule": TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        "order": ["bottom", "top"],
        "lifecycle_boundaries": boundaries,
        "global_identity_checks": identity_checks,
        **setup_counts,
    }
    setup["candidate_inventory"] = dict(setup_counts)
    setup["side_diagnostics_after_destroy"] = {
        "bottom": {
            "destroyed": True,
            "p4_factor_count": 0,
            "nested_iterative_ksp_count": 0,
        },
        "top": {
            "destroyed": True,
            "p4_factor_count": 0,
            "nested_iterative_ksp_count": 0,
        },
    }
    summary["side_setup_schedule"] = TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
    matrix = summary["matrix_inventory"]
    assert isinstance(matrix, dict)
    matrix["p4_factor_count_at_setup"] = None
    matrix["nested_iterative_ksp_count_at_setup"] = None
    summary["markers"] = {
        "observed": [
            "bottom_construction_cleanup",
            "top_construction_cleanup",
            "final_cleanup_complete",
        ]
    }
    return marker_path


def _common_layout_metadata(rank: int, name: str, shape: list[int]) -> dict[str, object]:
    payload = f"common-layout:{rank}:{name}".encode()
    return {
        "name": name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "hash_status": "measured",
        "shape": shape,
        "nbytes": 8 * max(1, int(np.prod(shape, dtype=int))),
    }


def _common_held_object(kind: str, handle: int) -> dict[str, object]:
    return {"kind": kind, "handle": handle}


def _write_common_packet(
    root: Path,
    label: str,
    identity: dict[str, object],
    rank_arrays: list[tuple[np.ndarray, np.ndarray]],
    *,
    with_rank_records: bool,
) -> tuple[dict[str, object], list[dict[str, object]]]:
    packet_dir = root / "common_packets" / label
    packet_dir.mkdir(parents=True)
    identity_sha = hashlib.sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    shards = []
    rank_records = []
    for rank, (solution, rhs) in enumerate(rank_arrays):
        solution = np.asarray(solution, dtype=np.complex128)
        rhs = np.asarray(rhs, dtype=np.complex128)
        shard_path = packet_dir / f"rank{rank:04d}.npz"
        np.savez(shard_path, solution=solution, rhs=rhs)
        shard_sha = hashlib.sha256(shard_path.read_bytes()).hexdigest()
        shards.append(
            {
                "rank": rank,
                "path": shard_path.name,
                "size": int(solution.size),
                "ownership_range": [rank, rank + int(solution.size)],
                "sha256": shard_sha,
            }
        )
        rank_records.append(
            {
                "rank": rank,
                "ownership_range": [rank, rank + int(solution.size)],
                "local_size": int(solution.size),
                "dtype": "complex128",
                "owned_rhs_sha256": hashlib.sha256(
                    memoryview(rhs).cast("B")
                ).hexdigest(),
                "owned_response_sha256": hashlib.sha256(
                    memoryview(solution).cast("B")
                ).hexdigest(),
                "packet_manifest_sha256": identity["packet_manifest_sha256"],
                "packet_shard_path": shard_path.name,
                "packet_shard_sha256": shard_sha,
                "rhs_before_sha256": hashlib.sha256(
                    memoryview(rhs).cast("B")
                ).hexdigest(),
                "rhs_after_sha256": hashlib.sha256(
                    memoryview(rhs).cast("B")
                ).hexdigest(),
                "rhs_unchanged": True,
            }
        )
    manifest_path = packet_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema": "myfenics.full3d.pre_recovery_packet.v1",
                "identity": identity,
                "identity_sha256": identity_sha,
                "rank_count": 8,
                "global_size": 8,
                "shards": shards,
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if with_rank_records:
        for record in rank_records:
            record["response_packet_manifest_sha256"] = manifest_sha
    artifact = {
        "manifest": str(manifest_path),
        "manifest_sha256": manifest_sha,
        "identity_sha256": identity_sha,
    }
    return artifact, rank_records if with_rank_records else []


def _write_top_causal_protocol_fixture(
    tmp_path: Path,
    *,
    mode: str = "healthy",
):
    """Write a tiny on-disk top-only result using the production packet schema."""

    root, summary, binding, _raw_path = _write_representative_result_fixture(tmp_path)
    source_sha = str(summary["source_sha"])
    probe = summary["representative_rhs_probe"]
    packet_sha = binding["packet_binding"]["packet_manifest_sha256"]
    top_entries = [
        entry
        for entry in binding["entries"]
        if entry["side"] == "top"
    ]
    assert [entry["formal_column"] for entry in top_entries] == [310, 12, 666, 493]
    selected_entries = {
        column: next(
            entry for entry in top_entries if entry["formal_column"] == column
        )
        for column in (12, 493, 666)
    }
    audit_rank_arrays = [
        (np.asarray([0.0j], dtype=np.complex128), np.asarray([1.0j], dtype=np.complex128))
        for _rank in range(8)
    ]
    audit_identity = {
        "schema": "task041.top_causal_test.audit_packet.v1",
        "source_sha": source_sha,
        "packet_manifest_sha256": packet_sha,
    }
    audit_packet, _ = _write_common_packet(
        root,
        "top_causal/audit",
        audit_identity,
        audit_rank_arrays,
        with_rank_records=False,
    )
    audit_packet["identity"] = audit_identity

    def write_p4_history(backend: str, trajectory: str) -> dict[str, str]:
        history_path = (
            root
            / "numerical_output"
            / "top_causal_replay"
            / "p4_history"
            / f"{backend}_{trajectory}.json"
        )
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history = {
            "schema": "task041.top_causal_replay.p4_call_history.v1",
            "source_sha": source_sha,
            "trajectory": trajectory,
            "backend": backend,
            "formal_column": 12,
            "by_rank": [{"rank": rank, "calls": []} for rank in range(8)],
        }
        history_path.write_text(
            json.dumps(history, sort_keys=True) + "\n", encoding="utf-8"
        )
        return {
            "path": str(history_path),
            "sha256": hashlib.sha256(history_path.read_bytes()).hexdigest(),
        }

    def residual_record(q_index: int) -> dict[str, object]:
        value = (
            2.0e-10
            if mode == "a4_gate_failure" and q_index == 1
            else 1.0e-12
        )
        gates = {
            name: {
                "limit": 1.0e-10,
                "value": value,
                "pass": value <= 1.0e-10,
            }
            for name in ("physical_relative_residual", "relative_residual")
        }
        return {
            "q_call_index": q_index,
            "full_reference": {
                "physical_relative_residual": value,
                "relative_residual": value,
            },
            "cell_condensed_replay": {
                "physical_relative_residual": value,
                "relative_residual": value,
            },
            "residual_gates": {
                "full_reference": copy.deepcopy(gates),
                "cell_condensed_replay": copy.deepcopy(gates),
            },
            "pass": value <= 1.0e-10,
        }

    def comparison_gate(
        gate_name: str,
        *,
        q_index: int | None = None,
    ) -> dict[str, object]:
        relative = (
            2.0e-11
            if mode == "q_gate_failure" and gate_name == "Q" and q_index == 1
            else 2.0e-8
            if mode == "pc_gate_failure" and gate_name == "PC"
            else 0.0
        )
        limit = 1.0e-11 if gate_name == "Q" else 1.0e-8
        result: dict[str, object] = {
            "gate_name": gate_name,
            "numerator_norm": relative,
            "denominator_norm": 1.0,
            "relative_difference": relative,
            "gate_limit": limit,
            "gate_applicable": True,
            "gate_pass": relative <= limit,
            "gate_status": "passed" if relative <= limit else "failed",
        }
        if q_index is not None:
            result["q_call_index"] = q_index
        return result

    audits: list[dict[str, object]] = []
    audit_specs = [
        ("reference", "full", "full_reference", None),
        ("independent_q", "cell_condensed", "independent_q1", 1),
        ("independent_q", "cell_condensed", "independent_q2", 2),
        ("independent_pc", "cell_condensed", "independent_pc", None),
    ]
    for replay_kind, backend, trajectory, q_index in audit_specs:
        history_ref = write_p4_history(backend, trajectory)
        rank_rows: list[dict[str, object]] = []
        for rank in range(8):
            q_calls: dict[str, object] = {}
            comparisons: list[dict[str, object]] = []
            shared_a4: list[dict[str, object]] = []
            if replay_kind == "independent_q":
                assert q_index in (1, 2)
                q_calls[str(q_index)] = {
                    "completed": True,
                    "input_matches_full": True,
                }
                comparisons.extend(
                    [
                        {
                            "event": "Q_input",
                            "q_call_index": q_index,
                            "exact_owned_bytes_equal": True,
                        },
                        comparison_gate("Q", q_index=q_index),
                    ]
                )
                shared_a4.append(residual_record(q_index))
            elif replay_kind == "independent_pc":
                q_calls = {
                    "1": {"completed": True, "input_matches_full": True},
                    "2": {"completed": True, "input_matches_full": True},
                }
                comparisons.extend(
                    [
                        {"event": "PC_input", "exact_owned_bytes_equal": True},
                        comparison_gate("PC"),
                    ]
                )
                shared_a4.extend(residual_record(q) for q in (1, 2))
            rank_rows.append(
                {
                    "rank": rank,
                    "pc_index": 1,
                    "q_calls": q_calls,
                    "comparisons": comparisons,
                    "shared_a4_checks": shared_a4,
                    "p4_call_history": history_ref,
                    "artifacts": [audit_packet],
                }
            )
        audit: dict[str, object] = {
            "pc_index": 1,
            "backend": backend,
            "replay_kind": replay_kind,
            "trajectory": trajectory,
            "formal_column": 12,
            "by_rank": rank_rows,
        }
        if replay_kind == "reference":
            audit["actual_pc_count"] = 1
        if replay_kind == "independent_q":
            audit["q_replay_index"] = q_index
        audit_path = (
            root
            / "numerical_output"
            / "top_causal_replay"
            / "audits"
            / f"{trajectory}.json"
        )
        audit_path.parent.mkdir(parents=True, exist_ok=True)
        audit_path.write_text(
            json.dumps(audit, sort_keys=True) + "\n", encoding="utf-8"
        )
        audit["audit_path"] = str(audit_path)
        audit["audit_sha256"] = hashlib.sha256(audit_path.read_bytes()).hexdigest()
        audits.append(audit)

    response_records: dict[str, list[dict[str, object]]] = {
        "full": [],
        "cell_condensed": [],
    }
    response_comparisons: list[dict[str, object]] = []
    strong_pair_passes: list[bool] = []
    action_delta_fraction = (
        2.0e-8 if mode == "strong_pair_failure" else 1.0e-12
    )

    def packet_vectors(artifact: dict[str, object]):
        manifest_path = Path(str(artifact["manifest"]))
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        solutions = []
        right_hand_sides = []
        for shard in manifest["shards"]:
            with np.load(manifest_path.parent / shard["path"], allow_pickle=False) as arrays:
                solutions.append(np.array(arrays["solution"], copy=True))
                right_hand_sides.append(np.array(arrays["rhs"], copy=True))
        return np.concatenate(solutions), np.concatenate(right_hand_sides)

    for backend in ("full", "cell_condensed"):
        for formal_column in (12, 493, 666):
            entry = selected_entries[formal_column]
            ordinal = int(entry["ordinal"])
            identity = {
                "schema": "task041.representative_rhs.response_identity.v1",
                "source_sha": source_sha,
                "probe_manifest_sha256": probe["sha256"],
                "packet_manifest_sha256": packet_sha,
                "ordinal": ordinal,
                "side": "top",
                "formal_column": formal_column,
                "branch_ordinal": entry["branch_ordinal"],
                "p4_backend": backend,
            }
            delta = (
                2.0e-8
                if mode == "strong_pair_failure" and backend == "cell_condensed"
                else 1.0e-12
                if backend == "cell_condensed"
                else 0.0
            )
            rank_arrays = [
                (
                    np.asarray([1.0 + delta], dtype=np.complex128),
                    np.asarray([1.0], dtype=np.complex128),
                )
                for _rank in range(8)
            ]
            artifact, rank_shards = _write_common_packet(
                root,
                f"top_causal/response/{backend}/{ordinal}",
                identity,
                rank_arrays,
                with_rank_records=True,
            )
            if backend == "full":
                full_artifact = artifact
                response_records[backend].append(
                    {
                        "ordinal": ordinal,
                        "artifact": artifact,
                        "rank_shards": rank_shards,
                        "audit": {
                            "true_residual_samples": [
                                {
                                    "sample_label": label,
                                    "iteration": iteration,
                                    "true_residual_norm": 1.0e-3,
                                    "rhs_norm": 1.0,
                                    "true_relative_residual": 1.0e-3,
                                    "finite": True,
                                }
                                for label, iteration in (
                                    ("first_iteration", 1),
                                    ("final_iteration", 1),
                                )
                            ]
                        },
                    }
                )
                continue
            full_call = next(
                item
                for item in response_records["full"]
                if item["ordinal"] == ordinal
            )
            full_artifact = full_call["artifact"]
            full_solution, full_rhs = packet_vectors(full_artifact)
            condensed_solution, condensed_rhs = packet_vectors(artifact)
            rhs_norm = float(np.linalg.norm(full_rhs))
            response_norm_full = float(np.linalg.norm(full_solution))
            response_norm_condensed = float(np.linalg.norm(condensed_solution))
            response_delta_norm = float(
                np.linalg.norm(condensed_solution - full_solution)
            )
            assert np.array_equal(full_rhs, condensed_rhs)
            denominator = max(response_norm_full, response_norm_condensed)
            e_x = response_delta_norm / denominator
            action_delta_norm = action_delta_fraction * rhs_norm
            e_a = action_delta_norm / rhs_norm
            full_residual_norm = 1.0e-3 * rhs_norm
            condensed_residual_norm = 1.0e-3 * rhs_norm
            side_residual_pass = True
            strong_pair_pass = e_x <= 1.0e-8 and e_a <= 1.0e-8
            gate_pass = strong_pair_pass and side_residual_pass
            strong_pair_passes.append(strong_pair_pass)
            projection = {
                "source": "same_live_coupling_top_projection",
                "global_size": 1,
                "full_sha256": "1" * 64,
                "cell_condensed_sha256": "2" * 64,
                "difference_sha256": "3" * 64,
                "full_norm": 1.0,
                "cell_condensed_norm": 1.0,
                "numerator_norm": 0.0,
                "denominator_norm": 1.0,
                "difference_norm": 0.0,
                "relative_difference": 0.0,
                "finite": True,
            }
            comparison = {
                "rhs_norm": rhs_norm,
                "response_norms": {
                    "full": response_norm_full,
                    "cell_condensed": response_norm_condensed,
                    "denominator": denominator,
                },
                "response_delta_norm": response_delta_norm,
                "action_delta_norm": action_delta_norm,
                "side_residuals": {
                    "full_norm": full_residual_norm,
                    "cell_condensed_norm": condensed_residual_norm,
                    "full_relative": full_residual_norm / rhs_norm,
                    "cell_condensed_relative": condensed_residual_norm / rhs_norm,
                },
                "e_x": e_x,
                "e_A": e_a,
                "limits": {
                    "e_x": 1.0e-8,
                    "e_A": 1.0e-8,
                    "side_relative_residual": 1.0e-2,
                },
                "strong_pair_gate_pass": strong_pair_pass,
                "side_residual_gate_pass": side_residual_pass,
                "finite": True,
                "pass": gate_pass,
                "top_modal_projection": projection,
            }
            response_records[backend].append(
                {
                    "ordinal": ordinal,
                    "artifact": artifact,
                    "rank_shards": rank_shards,
                    "audit": {
                        "true_residual_samples": [
                            {
                                "sample_label": label,
                                "iteration": iteration,
                                "true_residual_norm": 1.0e-3,
                                "rhs_norm": 1.0,
                                "true_relative_residual": 1.0e-3,
                                "finite": True,
                            }
                            for label, iteration in (
                                ("first_iteration", 1),
                                ("final_iteration", 1),
                            )
                        ]
                    },
                }
            )
            response_comparisons.append(
                {
                    "ordinal": ordinal,
                    "formal_column": formal_column,
                    "rhs_identity_pass": True,
                    "pass": gate_pass,
                    "comparison": comparison,
                }
            )

    if mode == "missing_q2":
        audits = [
            audit
            for audit in audits
            if not (
                audit.get("replay_kind") == "independent_q"
                and audit.get("q_replay_index") == 2
            )
        ]

    layout_sha = "4" * 64
    backend_phases = {
        backend: {
            "layout_identity": {"identity_sha256": layout_sha},
            "release": {"pass": True},
            "resources": [],
        }
        for backend in ("full", "cell_condensed")
    }
    evidence_complete = mode not in {"missing_q2", "bad_packet_hash"}
    action_safety_pass = mode in {"healthy", "strong_pair_failure"}
    response_pair_pass = all(strong_pair_passes)
    side_residual_gate_pass = True
    diagnostic_pass = evidence_complete and action_safety_pass
    top_record: dict[str, object] = {
        "schema": "task041.top_causal_replay.result.v1",
        "source_sha": source_sha,
        "scope": "top_only_fixed_manifest_replay",
        "qualification": "diagnostic_only",
        "selected_formal_columns": [12, 493, 666],
        "bottom_scope": "not_run",
        "fixed_eight_completion": False,
        "qualification_pass": False,
        "manifest": {
            "path": probe["path"],
            "sha256": probe["sha256"],
            "parent_packet_manifest_sha256": packet_sha,
        },
        "full_reference_response_count": 3,
        "condensed_free_response_count": 3,
        "frozen_pc_nodes": [1],
        "frozen_pc_node_count": 1,
        "full_capture_and_condensed_replay_audits": audits,
        "response_probe_records_by_backend": response_records,
        "response_comparisons": response_comparisons,
        "backend_order": ["full", "cell_condensed"],
        "backend_phases": backend_phases,
        "gates": {
            "same_layout_identity": True,
            "full_released_before_condensed": True,
            "both_backend_releases": True,
        },
        "response_pair_pass": response_pair_pass,
        "side_residual_gate_pass": side_residual_gate_pass,
        "evidence_complete": evidence_complete,
        "action_safety_pass": action_safety_pass,
        "diagnostic_pass": diagnostic_pass,
        "status": "diagnostic_complete" if diagnostic_pass else "failed_required_gate",
    }
    if mode == "bad_packet_hash":
        full_ordinal = int(selected_entries[12]["ordinal"])
        call = next(
            item
            for item in response_records["full"]
            if item["ordinal"] == full_ordinal
        )
        manifest = json.loads(Path(call["artifact"]["manifest"]).read_text())
        shard = manifest["shards"][0]
        shard_path = Path(call["artifact"]["manifest"]).parent / shard["path"]
        shard_path.write_bytes(shard_path.read_bytes() + b"damage")
    summary["status"] = (
        "task041_top_causal_replay_completed"
        if diagnostic_pass
        else "task041_top_causal_replay_failed_required_gate"
    )
    summary["classification"] = (
        "TASK041_TOP_CAUSAL_REPLAY_COMPLETED"
        if diagnostic_pass
        else "TASK041_TOP_CAUSAL_REPLAY_REQUIRED_GATE_FAILURE"
    )
    summary["lifecycle"].update(
        {
            "setup_released": True,
            "representative_rhs_cleanup_pass": True,
            "rss_marker_emitted": True,
        }
    )
    summary["cleanup"] = {"pass": True}
    summary["top_causal_replay"] = top_record
    sidecar = root / "numerical_output" / "top_causal_replay_top.json"
    sidecar.write_text(
        json.dumps(top_record, sort_keys=True) + "\n", encoding="utf-8"
    )
    (root / "consumer_summary.json").write_text(
        json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8"
    )
    return root, summary, binding


def test_task041_top_causal_result_protocol_healthy_positive(tmp_path):
    root, _summary, binding = _write_top_causal_protocol_fixture(tmp_path)
    summary = json.loads((root / "consumer_summary.json").read_text())
    record = summary["top_causal_replay"]
    sidecar = json.loads(
        (root / "numerical_output" / "top_causal_replay_top.json").read_text()
    )

    assert [
        entry["formal_column"]
        for entry in binding["entries"]
        if entry["side"] == "top"
    ] == [310, 12, 666, 493]
    assert record["backend_order"] == ["full", "cell_condensed"]
    assert list(record["backend_phases"]) == ["cell_condensed", "full"]
    assert sidecar == record
    assert record["qualification_pass"] is False
    assert record["fixed_eight_completion"] is False
    assert all(
        set(call["artifact"]) == {"manifest", "manifest_sha256", "identity_sha256"}
        for backend in ("full", "cell_condensed")
        for call in record["response_probe_records_by_backend"][backend]
    )

    validation = supervisor._validate_task041_top_causal_replay_result(
        root,
        summary,
        binding,
        process_group_gone=True,
        expected_side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        expected_comparison_mode=task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
    )
    assert validation["checks"] and all(validation["checks"].values())
    assert validation["pass"] is True
    assert validation["qualification_pass"] is False

    consumer = supervisor._consumer_result(
        root,
        process_group_gone=True,
        representative_rhs_binding=binding,
        expected_side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        expected_comparison_mode=task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
        expected_top_causal_replay=True,
    )
    assert consumer["complete"] is True
    assert consumer["top_causal_replay_validation"]["pass"] is True
    assert consumer["top_causal_replay_validation"]["qualification_pass"] is False


def test_task041_top_causal_strong_pair_failure_remains_diagnostic_complete(
    tmp_path,
):
    root, _summary, binding = _write_top_causal_protocol_fixture(
        tmp_path, mode="strong_pair_failure"
    )
    summary = json.loads((root / "consumer_summary.json").read_text())
    comparisons = summary["top_causal_replay"]["response_comparisons"]
    assert len(comparisons) == 3
    assert all(
        item["comparison"]["e_x"] > 1.0e-8
        and item["comparison"]["e_A"] > 1.0e-8
        and item["comparison"]["pass"] is False
        for item in comparisons
    )
    validation = supervisor._validate_task041_top_causal_replay_result(
        root,
        summary,
        binding,
        process_group_gone=True,
        expected_side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        expected_comparison_mode=task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
    )
    assert validation["pass"] is True
    assert validation["response_pair_pass"] is False
    assert validation["qualification_pass"] is False
    consumer = supervisor._consumer_result(
        root,
        process_group_gone=True,
        representative_rhs_binding=binding,
        expected_side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        expected_comparison_mode=task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
        expected_top_causal_replay=True,
    )
    assert consumer["complete"] is True
    assert consumer["top_causal_replay_validation"]["response_pair_pass"] is False


@pytest.mark.parametrize(
    ("mode", "action_check"),
    [
        ("q_gate_failure", "top_causal_q_pc_and_shared_a4_numeric_gates"),
        ("pc_gate_failure", "top_causal_q_pc_and_shared_a4_numeric_gates"),
        ("a4_gate_failure", "top_causal_q_pc_and_shared_a4_numeric_gates"),
    ],
)
def test_task041_top_causal_real_action_gate_failures_reject_completion(
    tmp_path, mode, action_check
):
    root, summary, binding = _write_top_causal_protocol_fixture(tmp_path, mode=mode)
    audits = summary["top_causal_replay"]["full_capture_and_condensed_replay_audits"]
    if mode == "q_gate_failure":
        q1 = next(
            audit
            for audit in audits
            if audit["replay_kind"] == "independent_q"
            and audit["q_replay_index"] == 1
        )
        q_gate = next(
            check
            for check in q1["by_rank"][0]["comparisons"]
            if check.get("gate_name") == "Q"
        )
        assert q_gate["relative_difference"] > q_gate["gate_limit"]
        assert q_gate["gate_pass"] is False
    elif mode == "pc_gate_failure":
        pc = next(audit for audit in audits if audit["replay_kind"] == "independent_pc")
        pc_gate = next(
            check
            for check in pc["by_rank"][0]["comparisons"]
            if check.get("gate_name") == "PC"
        )
        assert pc_gate["relative_difference"] > pc_gate["gate_limit"]
        assert pc_gate["gate_pass"] is False
    else:
        q1 = next(
            audit
            for audit in audits
            if audit["replay_kind"] == "independent_q"
            and audit["q_replay_index"] == 1
        )
        a4 = q1["by_rank"][0]["shared_a4_checks"][0]
        assert a4["full_reference"]["relative_residual"] > 1.0e-10
        assert a4["residual_gates"]["full_reference"]["relative_residual"]["pass"] is False
    validation = supervisor._validate_task041_top_causal_replay_result(
        root,
        summary,
        binding,
        process_group_gone=True,
        expected_side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        expected_comparison_mode=task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
    )
    assert validation["checks"]["top_causal_independent_q1_q2_pc_and_shared_a4_complete"] is True
    assert validation["checks"][action_check] is False
    assert validation["pass"] is False
    consumer = supervisor._consumer_result(
        root,
        process_group_gone=True,
        representative_rhs_binding=binding,
        expected_side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        expected_comparison_mode=task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
        expected_top_causal_replay=True,
    )
    assert consumer["complete"] is False


@pytest.mark.parametrize("mode", ["missing_q2", "bad_packet_hash"])
def test_task041_top_causal_missing_or_corrupt_evidence_is_rejected(tmp_path, mode):
    root, summary, binding = _write_top_causal_protocol_fixture(tmp_path, mode=mode)
    validation = supervisor._validate_task041_top_causal_replay_result(
        root,
        summary,
        binding,
        process_group_gone=True,
        expected_side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        expected_comparison_mode=task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
    )
    assert validation["pass"] is False
    assert validation["qualification_pass"] is False
    if mode == "missing_q2":
        assert validation["checks"]["top_causal_independent_q1_q2_pc_and_shared_a4_complete"] is False
    else:
        assert validation["checks"]["top_causal_response_artifact_hashes_and_norm_reports"] is False
    consumer = supervisor._consumer_result(
        root,
        process_group_gone=True,
        representative_rhs_binding=binding,
        expected_side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        expected_comparison_mode=task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
        expected_top_causal_replay=True,
    )
    assert consumer["complete"] is False


def test_task041_fixed_eight_completion_enum_cannot_complete_top_replay(tmp_path):
    root, _summary, binding = _write_top_causal_protocol_fixture(tmp_path)
    summary_path = root / "consumer_summary.json"
    summary = json.loads(summary_path.read_text())
    summary["status"] = "task041_representative_rhs_completed"
    summary["classification"] = "TASK041_REPRESENTATIVE_RHS_COMPLETED"
    summary_path.write_text(json.dumps(summary, sort_keys=True) + "\n")
    consumer = supervisor._consumer_result(
        root,
        process_group_gone=True,
        representative_rhs_binding=binding,
        expected_side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
        expected_comparison_mode=task041_balh_workflow.TASK041_P4_BACKEND_PAIR_MODE,
        expected_top_causal_replay=True,
    )
    assert consumer["top_causal_replay_validation"]["pass"] is True
    assert consumer["complete"] is False


def _write_common_layout_fixture(tmp_path: Path, mode: str = "normal"):
    root, summary, binding, _raw_path = _write_representative_result_fixture(tmp_path)
    _add_sequential_lifecycle_fixture(root, summary)
    setup = summary["setup"]
    assert isinstance(setup, dict)
    setup["candidate_inventory"].update(
        {
            "p6_factor_count": 0,
            "global_direct_factor_count": 0,
            "modal_block": "representative_rhs_only",
            "approximate_preconditioner_only": True,
        }
    )
    setup["variant_binding"] = {
        "bottom": {
            "source_module": "src.solvers.physical_balanced_same_mesh_transfer",
            "source_sha": summary["source_sha"],
            "variants": {
                "legacy": {
                    "owner_resolution": (
                        "src.solvers.physical_balanced_same_mesh_transfer."
                        "_resolve_owner_candidates"
                    ),
                    "cell_adjoint": (
                        "src.solvers.physical_balanced_same_mesh_transfer."
                        "SameMeshHcurlOwnerTransfer._apply_adjoint_into_impl"
                    ),
                    "adjoint_kernel": "explicit_matrix_conjugate_transpose",
                },
                "optimized": {
                    "owner_resolution": (
                        "src.solvers.physical_balanced_same_mesh_transfer."
                        "_resolve_owner_candidates_batched"
                    ),
                    "cell_adjoint": (
                        "src.solvers.physical_balanced_same_mesh_transfer."
                        "_apply_conjugate_transpose_vector"
                    ),
                    "adjoint_kernel": "conjugate_transpose_identity",
                },
            },
        },
        "top": {},
    }
    setup["variant_binding"]["top"] = copy.deepcopy(
        setup["variant_binding"]["bottom"]
    )

    identity_checks = setup["side_setup"]["global_identity_checks"]
    setup["admission_audit"]["global_operator_identity"] = {
        "threshold": 1.0e-12,
        "pass": True,
        "checks": copy.deepcopy(identity_checks),
    }

    def c3_input_facts():
        facts = {
            "coupling_last_apply_facts": {
                "initial": {
                    "balance": {
                        "norm": 0.0,
                        "operation_scale": 1.0,
                        "relative": 0.0,
                        "limit": 1.0e-8,
                    }
                }
            },
            "p4_last_solve": {
                "status": "passed",
                "rhs_norm": 1.0,
                "residual_norm": 1.0e-12,
                "physical_residual_norm": 1.0e-12,
                "residual_tolerance": 1.0e-10,
                "relative_residual": 1.0e-12,
                "physical_relative_residual": 1.0e-12,
                "backsolve_count": 1,
                "refinement_count": 0,
                "same_factor_refinement": False,
            },
        }
        return {
            "before": {"rhs": "b", "p4_source": "p4"},
            "after": {"rhs": "b", "p4_source": "p4"},
            "unchanged": True,
            "last_action_facts": facts,
        }

    sides = {}
    for side in ("bottom", "top"):
        input_hashes = {
            "legacy": c3_input_facts(),
            "optimized": c3_input_facts(),
        }
        sides[side] = {
            "admission": {"pass": True},
            "balanced_pc": {
                "P": {
                    "threshold": 1.0e-11,
                    "absolute": 0.0,
                    "legacy_norm": 1.0,
                    "optimized_norm": 1.0,
                    "relative": 0.0,
                    "finite": True,
                    "input_unchanged": True,
                    "input_hashes": copy.deepcopy(input_hashes),
                    "pass": True,
                },
                "PH": {
                    "threshold": 1.0e-11,
                    "absolute": 0.0,
                    "legacy_norm": 1.0,
                    "optimized_norm": 1.0,
                    "relative": 0.0,
                    "finite": True,
                    "input_unchanged": True,
                    "input_hashes": copy.deepcopy(input_hashes),
                    "pass": True,
                },
                "PC": {
                    "threshold": 1.0e-8,
                    "absolute": 0.0,
                    "legacy_norm": 1.0,
                    "optimized_norm": 1.0,
                    "relative": 0.0,
                    "finite": True,
                    "input_unchanged": True,
                    "input_hashes": input_hashes,
                    "pass": True,
                },
            },
        }
    setup["admission_audit"]["sides"] = sides

    audit_path = root / "numerical_output" / "common_layout_equivalence_audits.jsonl"
    expected_entries = binding["entries"]
    audit_rows = []
    values = {}
    for entry in expected_entries:
        ordinal = entry["ordinal"]
        value = 0.0 if mode == "zero" else 1.0e-36 if mode.startswith("tiny") else 1.0
        rhs = np.array([complex(value)], dtype=np.complex128)
        legacy = rhs.copy()
        optimized = (
            rhs * (1.0 + 1.0e-6) if mode == "tiny_sensitivity" else rhs.copy()
        )
        legacy_residual = rhs - legacy
        optimized_residual = rhs - optimized
        values[ordinal] = (legacy, optimized, rhs)
        rhs_norm = math.sqrt(8.0) * value
        zero = value == 0.0
        audit_counts = {
            name: (0 if zero else 1)
            for name in ("pc", "Q", "H6", "A6", "P", "PH_audit", "p4_backsolve")
        }
        audit = {
            "representative_ordinal": ordinal,
            "source_audit_index": entry["audit_index"],
            "formal_column": entry["formal_column"],
            "branch_ordinal": entry["branch_ordinal"],
            "comparison_variant": "legacy",
            "execution_variant": "legacy",
            "status": "ZERO_RHS_EXACT" if zero else "KSP_CONVERGED",
            "reason": None if zero else 2,
            "iterations": 0 if zero else 1,
            "ksp_positive": not zero,
            "explicit_true_target_reached": True,
            "rhs_norm": rhs_norm,
            "residual_norm": 0.0,
            "relative_residual": 0.0,
            "ksp_rtol": 1.0e-2,
            "ksp_max_it": 128,
            "ksp_contract": {
                "collective_pass": True,
                "actual": {
                    "type": "fgmres",
                    "pc_type": "python",
                    "pc_side": 1,
                    "pc_side_label": "RIGHT",
                    "norm_type": 2,
                    "norm_type_label": "UNPRECONDITIONED",
                    "restart": 32,
                    "rtol": 1.0e-2,
                    "atol": 0.0,
                    "max_it": 128,
                    "initial_guess_nonzero": False,
                },
                "expected": {"pc_side": 1, "norm_type": 2},
                "checks": {
                    field: True
                    for field in (
                        "type",
                        "pc_type",
                        "pc_side",
                        "norm_type",
                        "restart",
                        "rtol",
                        "atol",
                        "max_it",
                        "initial_guess_nonzero",
                    )
                },
            },
            "iteration_history": [] if zero else [{"iteration": 1, "reported_residual": 0.0}],
            "counts": {"delta": audit_counts},
        }
        for variant in ("legacy", "optimized"):
            variant_audit = copy.deepcopy(audit)
            variant_audit["comparison_variant"] = variant
            variant_audit["execution_variant"] = variant
            residual = (
                legacy_residual if variant == "legacy" else optimized_residual
            )
            residual_norm = math.sqrt(
                float(8.0 * np.vdot(residual, residual).real)
            )
            variant_audit["residual_norm"] = residual_norm
            variant_audit["relative_residual"] = (
                0.0 if rhs_norm == 0.0 else residual_norm / rhs_norm
            )
            audit_rows.append(
                {
                    "phase": "common_layout_equivalence",
                    "side": entry["side"],
                    "status": variant_audit["status"],
                    "reason": variant_audit["reason"],
                    "audit": variant_audit,
                }
            )
    audit_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in audit_rows),
        encoding="utf-8",
    )

    layout_payloads = {}
    for side in ("bottom", "top"):
        instance = hashlib.sha256(
            f"{audit_path.resolve()}|{side}|task041.common_layout_equivalence.layout.v1".encode()
        ).hexdigest()
        by_rank = []
        for rank in range(8):
            arrays = {
                name: _common_layout_metadata(rank, name, [1])
                for name in ("geometry", "geometry_dofmap", "cell_permutation_info")
            }
            mpc = {
                name: _common_layout_metadata(rank, f"fine_{name}", [1])
                for name in ("slaves", "coefficients", "offsets")
            }
            coarse_mpc = {
                name: _common_layout_metadata(rank, f"coarse_{name}", [1])
                for name in ("slaves", "coefficients", "offsets")
            }
            held = {
                "side_A": _common_held_object("side_operator", 500 + rank),
                "side_inverse": _common_held_object("side_inverse", 600 + rank),
                "p4_factor": _common_held_object("p4_factor", 700 + rank),
                "research_factor": _common_held_object("research_factor", 800 + rank),
                "p4_matrix": _common_held_object("p4_matrix", 900 + rank),
                "p4_factor_ksp": {
                    "live": False,
                    "reason": "factor_only_storage",
                    "python_id": None,
                    "handle": None,
                    "petsc_handle": None,
                    "cpp_object": None,
                },
                "p4_factor_matrix": _common_held_object("factor_matrix", 1000 + rank),
                "nested_ksp": {"kind": "nested_ksp", "handle": 1100 + rank, "live": True},
                "h6": _common_held_object("h6", 1200 + rank),
                "h6_matrix": _common_held_object("h6_matrix", 1300 + rank),
                "mesh": _common_held_object("mesh", 1400 + rank),
                "side_system": _common_held_object("side_system", 1500 + rank),
            }
            comm = {
                "rank": rank,
                "size": 8,
                "fortran_handle": 100 + rank,
            }
            by_rank.append(
                {
                    "rank": rank,
                    "layout_instance_id": instance,
                    "communicator": comm,
                    "communicators": {
                        "outer": comm.copy(),
                        "transfer": comm.copy(),
                        "side_operator": comm.copy(),
                        "inverse": comm.copy(),
                        "compare": {
                            "outer_transfer": 1,
                            "transfer_side_operator": 1,
                            "side_operator_inverse": 1,
                        },
                    },
                    "ownership_range": [rank, rank + 1],
                    "ownership": {"start": rank, "end": rank + 1},
                    "dofmaps": {"fine": {"rank": rank}, "coarse": {"rank": rank}},
                    "held_objects": held,
                    "mesh_layout": arrays,
                    "mpc_layout": {
                        "fine": {
                            **mpc,
                            "masters_links_sha256": hashlib.sha256(
                                f"fine-masters:{rank}".encode()
                            ).hexdigest(),
                        },
                        "coarse": {
                            **coarse_mpc,
                            "masters_links_sha256": hashlib.sha256(
                                f"coarse-masters:{rank}".encode()
                            ).hexdigest(),
                        },
                    },
                    "layout_arrays": [
                        _common_layout_metadata(rank, "owned_active_original_dofs", [1])
                    ],
                    "transfer_identity": {
                        "owner_row_authority": hashlib.sha256(
                            f"owner-row:{side}:{rank}".encode()
                        ).hexdigest()
                    },
                    "operator_identity": {"kind": "side_A", "handle": 1600 + rank},
                }
            )
        layout_sha = hashlib.sha256(
            json.dumps(by_rank, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        payload = {
            "schema": "task041.common_layout_equivalence.layout.v1",
            "side": side,
            "comm_size": 8,
            "layout_instance_id": instance,
            "layout_identity_sha256": layout_sha,
            "by_rank": by_rank,
        }
        layout_path = root / "numerical_output" / "common_layout_equivalence" / f"{side}_layout.json"
        layout_path.parent.mkdir(parents=True, exist_ok=True)
        layout_path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        layout_payloads[side] = (instance, layout_sha, layout_path)

    pairs = []
    for entry in expected_entries:
        ordinal = entry["ordinal"]
        side = entry["side"]
        instance, layout_sha, layout_path = layout_payloads[side]
        legacy, optimized, rhs = values[ordinal]
        base_identity = {
            "schema": "task041.common_layout_equivalence.response_identity.v1",
            "scope": TASK041_REPRESENTATIVE_RHS_SCOPE,
            "comparison_mode": "common_layout_equivalence",
            "pairing_scope": "same_live_layout",
            "run_layout_epoch": instance,
            "layout_instance_id": instance,
            "source_sha": summary["source_sha"],
            "probe_manifest_sha256": binding["sha256"],
            "packet_manifest_sha256": binding["packet_binding"]["packet_manifest_sha256"],
            "layout_identity_sha256": layout_sha,
            "ordinal": ordinal,
            "side": side,
            "formal_column": entry["formal_column"],
            "branch_ordinal": entry["branch_ordinal"],
        }
        artifacts = {}
        rank_records = {}
        for variant, solution in (("legacy", legacy), ("optimized", optimized)):
            identity = {**base_identity, "variant": variant}
            artifact, records = _write_common_packet(
                root,
                f"{ordinal}_{variant}_response",
                identity,
                [(solution, rhs) for _rank in range(8)],
                with_rank_records=True,
            )
            artifacts[variant] = artifact
            rank_records[variant] = records
        delta = optimized - legacy
        legacy_residual = rhs - legacy
        optimized_residual = rhs - optimized
        action_identity = {
            "schema": "task041.common_layout_equivalence.comparison_diagnostic.v1",
            **{key: value for key, value in base_identity.items() if key != "schema"},
            "kind": "response_and_action_delta",
        }
        residual_identity = {
            "schema": "task041.common_layout_equivalence.comparison_diagnostic.v1",
            **{key: value for key, value in base_identity.items() if key != "schema"},
            "kind": "legacy_and_optimized_residual",
        }
        action_artifact, _ = _write_common_packet(
            root,
            f"{ordinal}_action",
            action_identity,
            [(delta, delta) for _rank in range(8)],
            with_rank_records=False,
        )
        residual_artifact, _ = _write_common_packet(
            root,
            f"{ordinal}_residual",
            residual_identity,
            [
                (legacy_residual, optimized_residual)
                for _rank in range(8)
            ],
            with_rank_records=False,
        )
        rhs_norm = math.sqrt(float(8.0 * np.vdot(rhs, rhs).real))
        legacy_norm = math.sqrt(float(8.0 * np.vdot(legacy, legacy).real))
        optimized_norm = math.sqrt(float(8.0 * np.vdot(optimized, optimized).real))
        delta_norm = math.sqrt(float(8.0 * np.vdot(delta, delta).real))
        legacy_residual_norm = math.sqrt(
            float(8.0 * np.vdot(legacy_residual, legacy_residual).real)
        )
        optimized_residual_norm = math.sqrt(
            float(8.0 * np.vdot(optimized_residual, optimized_residual).real)
        )
        residual_difference = optimized_residual - legacy_residual
        residual_difference_norm = math.sqrt(
            float(8.0 * np.vdot(residual_difference, residual_difference).real)
        )
        residual_difference_relative = (
            0.0
            if max(legacy_residual_norm, optimized_residual_norm) == 0.0
            else residual_difference_norm
            / max(legacy_residual_norm, optimized_residual_norm)
        )
        e_x = 0.0 if max(legacy_norm, optimized_norm) == 0.0 else delta_norm / max(legacy_norm, optimized_norm)
        e_a = 0.0 if rhs_norm == 0.0 else delta_norm / rhs_norm
        comparison = {
            "operator_scope": "side_A",
            "threshold_e_x": 1.0e-8,
            "threshold_e_A": 1.0e-8,
            "e_x_absolute": delta_norm,
            "e_x": e_x,
            "e_A_absolute": delta_norm,
            "e_A": e_a,
            "rhs_norm": rhs_norm,
            "response_norms": {
                "legacy": legacy_norm,
                "optimized": optimized_norm,
                "denominator": max(legacy_norm, optimized_norm),
            },
            "residual_norms": {
                "legacy": legacy_residual_norm,
                "optimized": optimized_residual_norm,
                "denominator": max(legacy_residual_norm, optimized_residual_norm),
            },
            "residual_difference_norm": residual_difference_norm,
            "residual_difference_relative": residual_difference_relative,
            "finite": True,
            "input_unchanged": True,
            "pass": e_x <= 1.0e-8 and e_a <= 1.0e-8,
            "diagnostic_packets": {
                "response_and_action": action_artifact,
                "residual_pair": residual_artifact,
            },
        }
        audits = {}
        for row in audit_rows:
            audit = row["audit"]
            if audit["representative_ordinal"] == ordinal:
                audits[audit["comparison_variant"]] = audit
        first_variant = "legacy" if ordinal % 2 == 0 else "optimized"
        pair = {
            **{key: entry[key] for key in ("ordinal", "side", "branch", "audit_index", "formal_column", "branch_ordinal")},
            "status": "completed",
            "scope": TASK041_REPRESENTATIVE_RHS_SCOPE,
            "comparison_mode": "common_layout_equivalence",
            "pairing_scope": "same_live_layout",
            "run_layout_epoch": instance,
            "layout_instance_id": instance,
            "layout_identity_sha256": layout_sha,
            "before_layout": {"path": str(layout_path), "layout_identity_sha256": layout_sha},
            "after_layout": {"path": str(layout_path), "layout_identity_sha256": layout_sha},
            "variant_order": [
                first_variant,
                "optimized" if first_variant == "legacy" else "legacy",
            ],
            "variants": {
                variant: {
                    "artifact": artifacts[variant],
                    "rank_shards": rank_records[variant],
                    "audit": audits[variant],
                }
                for variant in ("legacy", "optimized")
            },
            "audits": audits,
            "comparison": comparison,
        }
        pairs.append(pair)

    pair_path = root / "numerical_output" / "common_layout_equivalence_pairs.jsonl"
    pair_path.write_text(
        "".join(json.dumps(pair, sort_keys=True) + "\n" for pair in pairs),
        encoding="utf-8",
    )
    summary["scope"] = TASK041_REPRESENTATIVE_RHS_SCOPE
    summary["comparison_mode"] = "common_layout_equivalence"
    summary["status"] = "task041_common_layout_equivalence_completed"
    summary["classification"] = "COMMON_LAYOUT_EQUIVALENCE_PASS"
    summary["packet"] = {
        "manifest_sha256": binding["packet_binding"]["packet_manifest_sha256"],
        "identity": binding["packet_binding"]["packet_identity"],
    }
    summary_entries = [
        {
            **{key: pair[key] for key in ("ordinal", "side", "branch", "audit_index", "formal_column", "branch_ordinal", "status", "scope", "comparison_mode", "pairing_scope", "run_layout_epoch", "layout_instance_id", "layout_identity_sha256")},
            "variants": {"legacy": {}, "optimized": {}},
        }
        for pair in pairs
    ]
    common_parts = []
    for side in ("bottom", "top"):
        side_entries = [
            entry for entry in summary_entries if entry["side"] == side
        ]
        common_parts.append(
            {
                "scope": TASK041_REPRESENTATIVE_RHS_SCOPE,
                "comparison_mode": "common_layout_equivalence",
                "pairing_scope": "same_live_layout",
                "status": "completed",
                "source_manifest": {
                    "path": binding["path"],
                    "sha256": binding["sha256"],
                    "scope": TASK041_REPRESENTATIVE_RHS_SCOPE,
                },
                "packet_binding": copy.deepcopy(binding["packet_binding"]),
                "entries": side_entries,
                "apply_count": 2 * len(side_entries),
            }
        )
    summary["common_layout_equivalence"] = _merge_representative_parts(
        common_parts, expected_entries
    )
    (root / "consumer_summary.json").write_text(
        json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8"
    )
    return root, summary, binding


def test_common_layout_equivalence_artifact_positive_and_recomputes(tmp_path):
    root, summary, binding = _write_common_layout_fixture(tmp_path)
    result = _validate_common_layout_equivalence_result(
        root,
        summary,
        binding,
        expected_side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
    )
    assert result["pass"] is True
    assert result["scope"] == TASK041_REPRESENTATIVE_RHS_SCOPE
    assert result["checks"]["pair_records"] == {
        "path": str(root / "numerical_output" / "common_layout_equivalence_pairs.jsonl"),
        "count": 8,
        "expected": 8,
    }
    computed = result["checks"]["computed_pairs"]
    assert len(computed) == 8
    assert all(pair["e_x"] == 0.0 and pair["e_A"] == 0.0 for pair in computed)
    assert all(
        pair["legacy_residual_norm"] <= pair["rhs_norm"] * 1.0e-2
        and pair["optimized_residual_norm"] <= pair["rhs_norm"] * 1.0e-2
        for pair in computed
    )


@pytest.mark.parametrize("common_mode", [True, False])
def test_common_layout_side_results_merge_apply_count(common_mode):
    entries = [{"ordinal": ordinal} for ordinal in range(8)]
    parts = []
    for side_entries in (entries[:4], entries[4:]):
        part = {"entries": side_entries}
        if common_mode:
            part.update(
                {
                    "comparison_mode": "common_layout_equivalence",
                    "apply_count": 8,
                }
            )
        parts.append(part)

    merged = _merge_representative_parts(parts, entries)

    assert [entry["ordinal"] for entry in merged["entries"]] == list(range(8))
    assert merged["expected_count"] == 8
    assert merged["completed_count"] == 8
    if common_mode:
        assert merged["apply_count"] == 16
    else:
        assert "apply_count" not in merged


@pytest.mark.parametrize("mode", ["tiny", "zero"])
def test_common_layout_equivalence_artifact_healthy_small_rhs(tmp_path, mode):
    root, summary, binding = _write_common_layout_fixture(tmp_path, mode)
    result = _validate_common_layout_equivalence_result(
        root,
        summary,
        binding,
        expected_side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
    )
    assert result["pass"] is True
    assert all(
        pair["e_x"] == 0.0 and pair["e_A"] == 0.0
        for pair in result["checks"]["computed_pairs"]
    )


def _common_pairs_rows(root: Path) -> list[dict[str, object]]:
    path = root / "numerical_output" / "common_layout_equivalence_pairs.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _rewrite_common_pairs(root: Path, rows: list[dict[str, object]]) -> None:
    path = root / "numerical_output" / "common_layout_equivalence_pairs.jsonl"
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _rewrite_common_audits(root: Path, rows: list[dict[str, object]]) -> None:
    path = root / "numerical_output" / "common_layout_equivalence_audits.jsonl"
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _replace_common_rank_rhs(pair: dict[str, object], rank: int) -> None:
    record = pair["variants"]["optimized"]["rank_shards"][rank]
    artifact = pair["variants"]["optimized"]["artifact"]
    manifest_path = Path(artifact["manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    shard = manifest["shards"][rank]
    shard_path = manifest_path.parent / shard["path"]
    with np.load(shard_path, allow_pickle=False) as arrays:
        solution = np.asarray(arrays["solution"], dtype=np.complex128)
    changed_rhs = np.array([2.0 + 0.0j], dtype=np.complex128)
    np.savez(shard_path, solution=solution, rhs=changed_rhs)
    shard["sha256"] = hashlib.sha256(shard_path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8")
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    shard_sha = shard["sha256"]
    artifact["manifest_sha256"] = manifest_sha
    rhs_sha = hashlib.sha256(memoryview(changed_rhs).cast("B")).hexdigest()
    for rank_record in pair["variants"]["optimized"]["rank_shards"]:
        rank_record["response_packet_manifest_sha256"] = manifest_sha
    record = pair["variants"]["optimized"]["rank_shards"][rank]
    record["owned_rhs_sha256"] = rhs_sha
    record["rhs_before_sha256"] = rhs_sha
    record["rhs_after_sha256"] = rhs_sha
    record["packet_shard_sha256"] = shard_sha


def _rewrite_common_packet_arrays(
    artifact: dict[str, object],
    rank_arrays: list[tuple[np.ndarray, np.ndarray]],
    rank_records: list[dict[str, object]] | None,
) -> None:
    manifest_path = Path(artifact["manifest"])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for rank, (solution, rhs) in enumerate(rank_arrays):
        shard = manifest["shards"][rank]
        shard_path = manifest_path.parent / shard["path"]
        solution = np.asarray(solution, dtype=np.complex128)
        rhs = np.asarray(rhs, dtype=np.complex128)
        np.savez(shard_path, solution=solution, rhs=rhs)
        shard["sha256"] = hashlib.sha256(shard_path.read_bytes()).hexdigest()
        shard["size"] = int(solution.size)
        shard["ownership_range"] = [rank, rank + int(solution.size)]
        if rank_records is not None:
            record = rank_records[rank]
            rhs_sha = hashlib.sha256(memoryview(rhs).cast("B")).hexdigest()
            solution_sha = hashlib.sha256(
                memoryview(solution).cast("B")
            ).hexdigest()
            record["owned_rhs_sha256"] = rhs_sha
            record["owned_response_sha256"] = solution_sha
            record["rhs_before_sha256"] = rhs_sha
            record["rhs_after_sha256"] = rhs_sha
            record["packet_shard_sha256"] = shard["sha256"]
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest_sha = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    artifact["manifest_sha256"] = manifest_sha
    if rank_records is not None:
        for record in rank_records:
            record["response_packet_manifest_sha256"] = manifest_sha


@pytest.mark.parametrize(
    "mutation,expected_category",
    [
        ("layout", "PAIRING_SETUP_FAILURE"),
        ("rhs", "PAIRING_SETUP_FAILURE"),
        ("missing_variant", "PAIRING_SETUP_FAILURE"),
        ("duplicate_variant", "PAIRING_SETUP_FAILURE"),
        ("wrong_apply_count", "PAIRING_SETUP_FAILURE"),
        ("residual", "NUMERICAL_GATE_FAIL"),
        ("action", "ACTION_EQUIVALENCE_FAIL"),
    ],
)
def test_common_layout_equivalence_artifact_rejects_contract_mutations(
    tmp_path, mutation, expected_category
):
    root, summary, binding = _write_common_layout_fixture(tmp_path)
    if mutation == "layout":
        path = root / "numerical_output" / "common_layout_equivalence" / "bottom_layout.json"
        payload = json.loads(path.read_text())
        payload["by_rank"][0]["layout_arrays"][0]["sha256"] = "f" * 64
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    elif mutation == "rhs":
        rows = _common_pairs_rows(root)
        _replace_common_rank_rhs(rows[0], 0)
        _rewrite_common_pairs(root, rows)
    elif mutation == "missing_variant":
        rows = _common_pairs_rows(root)
        del rows[0]["variants"]["optimized"]
        _rewrite_common_pairs(root, rows)
    elif mutation == "duplicate_variant":
        audit_path = root / "numerical_output" / "common_layout_equivalence_audits.jsonl"
        rows = [json.loads(line) for line in audit_path.read_text().splitlines()]
        rows.append(copy.deepcopy(rows[0]))
        _rewrite_common_audits(root, rows)
    elif mutation == "wrong_apply_count":
        summary["common_layout_equivalence"]["apply_count"] = 8
    elif mutation == "residual":
        pair_rows = _common_pairs_rows(root)
        pair = pair_rows[0]
        response_artifacts = {
            variant: pair["variants"][variant]["artifact"]
            for variant in ("legacy", "optimized")
        }
        with np.load(
            Path(response_artifacts["legacy"]["manifest"])
            .parent
            / "rank0000.npz",
            allow_pickle=False,
        ) as arrays:
            rhs = np.asarray(arrays["rhs"], dtype=np.complex128)
        failed_solution = 0.9 * rhs
        for variant in ("legacy", "optimized"):
            _rewrite_common_packet_arrays(
                response_artifacts[variant],
                [(failed_solution, rhs) for _rank in range(8)],
                pair["variants"][variant]["rank_shards"],
            )
        residual_artifact = pair["comparison"]["diagnostic_packets"][
            "residual_pair"
        ]
        failed_residual = 0.1 * rhs
        _rewrite_common_packet_arrays(
            residual_artifact,
            [(failed_residual, failed_residual) for _rank in range(8)],
            None,
        )
        rhs_norm = math.sqrt(float(8.0 * np.vdot(rhs, rhs).real))
        failed_residual_norm = 0.1 * rhs_norm
        for variant in ("legacy", "optimized"):
            for audit in (
                pair["audits"][variant],
                pair["variants"][variant]["audit"],
            ):
                audit["residual_norm"] = failed_residual_norm
                audit["relative_residual"] = 0.1
        audit_path = root / "numerical_output" / "common_layout_equivalence_audits.jsonl"
        rows = [json.loads(line) for line in audit_path.read_text().splitlines()]
        for row in rows:
            audit = row.get("audit", {})
            if audit.get("representative_ordinal") == 0:
                audit["residual_norm"] = failed_residual_norm
                audit["relative_residual"] = 0.1
        _rewrite_common_audits(root, rows)
        comparison = pair["comparison"]
        comparison["response_norms"]["legacy"] = 0.9 * rhs_norm
        comparison["response_norms"]["optimized"] = 0.9 * rhs_norm
        comparison["residual_norms"]["legacy"] = failed_residual_norm
        comparison["residual_norms"]["optimized"] = failed_residual_norm
        comparison["residual_norms"]["denominator"] = failed_residual_norm
        comparison["residual_difference_norm"] = 0.0
        comparison["residual_difference_relative"] = 0.0
        _rewrite_common_pairs(root, pair_rows)
    elif mutation == "action":
        action = summary["setup"]["admission_audit"]["sides"]["bottom"]["balanced_pc"]["P"]
        action["absolute"] = 2.0e-11
        action["relative"] = 2.0e-11
        action["pass"] = False
    result = _validate_common_layout_equivalence_result(
        root,
        summary,
        binding,
        expected_side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
    )
    assert result["pass"] is False
    assert result["failure_classification"] == expected_category
    assert result["category_failures"][expected_category]
    if mutation == "rhs":
        assert any("rhs_layout" in failure for failure in result["failures"])


def test_common_layout_equivalence_tiny_response_sensitivity_is_not_floored(tmp_path):
    root, summary, binding = _write_common_layout_fixture(tmp_path, "tiny_sensitivity")
    result = _validate_common_layout_equivalence_result(
        root,
        summary,
        binding,
        expected_side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
    )
    assert result["pass"] is False
    assert result["failure_classification"] == "RESPONSE_SENSITIVITY_UNRESOLVED"
    assert any(
        pair["e_x"] > 1.0e-8 for pair in result["checks"]["computed_pairs"]
    )


@pytest.mark.parametrize(
    "mutation", [None, "residual", "nan", "key", "shard", "cleanup"]
)
def test_representative_rhs_result_requires_fixed_raw_and_shard_binding(
    tmp_path, mutation
):
    root, summary, binding, raw_path = _write_representative_result_fixture(tmp_path)
    if mutation == "residual":
        rows = [json.loads(line) for line in raw_path.read_text().splitlines()]
        rows[0]["audit"]["residual_norm"] = 0.1
        rows[0]["audit"]["pass"] = True
        raw_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        binding["source_audit"]["rhs_audit_sha256"] = hashlib.sha256(
            raw_path.read_bytes()
        ).hexdigest()
    elif mutation == "nan":
        rows = [json.loads(line) for line in raw_path.read_text().splitlines()]
        rows[0]["audit"]["residual_norm"] = float("nan")
        rows[0]["audit"]["pass"] = True
        raw_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        binding["source_audit"]["rhs_audit_sha256"] = hashlib.sha256(
            raw_path.read_bytes()
        ).hexdigest()
    elif mutation == "key":
        rows = [json.loads(line) for line in raw_path.read_text().splitlines()]
        rows[0]["audit"]["formal_column"] += 1
        raw_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        binding["source_audit"]["rhs_audit_sha256"] = hashlib.sha256(
            raw_path.read_bytes()
        ).hexdigest()
    elif mutation == "shard":
        artifact = summary["representative_rhs"]["entries"][0]["artifact"]
        Path(artifact["manifest"]).with_name("rank0000.npz").write_bytes(b"tampered")
    elif mutation == "cleanup":
        summary["lifecycle"]["representative_rhs_cleanup_pass"] = False
    result = _validate_representative_rhs_result(
        root, summary, binding, process_group_gone=True
    )
    assert result["pass"] is (mutation is None)
    if mutation == "residual":
        assert any(
            "recomputed_relative_residual" in failure
            for failure in result["failures"]
        )
    elif mutation == "nan":
        assert any(
            failure.endswith("residual_norm") for failure in result["failures"]
        )


@pytest.mark.parametrize(
    "mutation",
    [
        None,
        "release",
        "overlap",
        "order",
        "summary_counts",
        "schedule",
        "identity",
        "identity_order",
    ],
)
def test_representative_sequential_lifecycle_is_raw_and_bound(tmp_path, mutation):
    root, summary, binding, _raw_path = _write_representative_result_fixture(tmp_path)
    marker_path = _add_sequential_lifecycle_fixture(root, summary)
    if mutation in {"release", "overlap"}:
        rows = [json.loads(line) for line in marker_path.read_text().splitlines()]
        for row in rows:
            boundary = row.get("detail", {}).get("lifecycle_boundary")
            if not isinstance(boundary, dict):
                continue
            if mutation == "release" and (
                boundary.get("side"), boundary.get("event")
            ) == ("bottom", "released"):
                boundary["live"] = _sequential_live("bottom", 1, 1)
            if mutation == "overlap" and (
                boundary.get("side"), boundary.get("event")
            ) == ("top", "ready"):
                boundary["live"] = {
                    "by_side": {
                        "bottom": {
                            "p4_factor_count": 1,
                            "nested_iterative_ksp_count": 1,
                        },
                        "top": {
                            "p4_factor_count": 1,
                            "nested_iterative_ksp_count": 1,
                        },
                    },
                    "live_side_count": 2,
                    "live_component_counts": {
                        "p4_factor": 2,
                        "nested_iterative_ksp": 2,
                    },
                    "live_component_count_sum": 4,
                }
        marker_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        for row in rows:
            boundary = row.get("detail", {}).get("lifecycle_boundary")
            if not isinstance(boundary, dict):
                continue
            for expected in summary["setup"]["side_setup"]["lifecycle_boundaries"]:
                if (
                    expected["side"], expected["event"]
                ) == (boundary.get("side"), boundary.get("event")):
                    expected["live"] = copy.deepcopy(boundary["live"])
    elif mutation == "order":
        rows = [json.loads(line) for line in marker_path.read_text().splitlines()]
        rows[1], rows[2] = rows[2], rows[1]
        marker_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
    elif mutation == "summary_counts":
        summary["setup"]["side_setup"]["simultaneously_live_peak"] = 2
    elif mutation == "identity":
        rows = [json.loads(line) for line in marker_path.read_text().splitlines()]
        for row in rows:
            check = row.get("detail", {}).get("identity_check")
            if isinstance(check, dict) and check.get("label") == (
                "bottom_after_admission"
            ):
                check["action_relative"] = 2.0e-12
        marker_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )
        summary_check = summary["setup"]["side_setup"]["global_identity_checks"][
            "bottom_after_admission"
        ]
        summary_check["action_relative"] = 2.0e-12
    elif mutation == "identity_order":
        rows = [json.loads(line) for line in marker_path.read_text().splitlines()]
        after_release = next(
            index
            for index, row in enumerate(rows)
            if row.get("detail", {}).get("identity_check", {}).get("label")
            == "bottom_after_release"
        )
        rows.insert(
            next(
                index
                for index, row in enumerate(rows)
                if row.get("stage") == "bottom_construction_cleanup"
            ),
            rows.pop(after_release),
        )
        marker_path.write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
            encoding="utf-8",
        )

    expected_schedule = (
        None if mutation == "schedule" else TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
    )
    result = _validate_representative_rhs_result(
        root,
        summary,
        binding,
        process_group_gone=True,
        expected_side_setup_schedule=expected_schedule,
    )
    assert result["pass"] is (mutation is None)
    if mutation is None:
        assert result["checks"]["sequential_lifecycle"] is True
    elif mutation == "identity":
        assert result["checks"]["sequential_markers"][
            "identity_values_and_order"
        ] is False
    elif mutation == "identity_order":
        assert result["checks"]["sequential_markers"][
            "identity_lifecycle_order"
        ] is False


def test_formal_mode_does_not_accept_representative_summary(tmp_path):
    root, summary, binding, _raw_path = _write_representative_result_fixture(tmp_path)
    (root / "consumer_summary.json").write_text(
        json.dumps(summary, sort_keys=True) + "\n", encoding="utf-8"
    )
    representative_result = supervisor._consumer_result(
        root, process_group_gone=True, representative_rhs_binding=binding
    )
    assert representative_result["complete"] is True
    result = supervisor._consumer_result(root, process_group_gone=True)
    assert result["complete"] is False
    assert result["completion_scope"] == "formal"


def test_public_diagnostic_completion_requires_registered_identity_and_cleanup(
    tmp_path,
):
    model_id = TASK041_BALH_2NM_CANDIDATE_MODEL_ID
    root = tmp_path / "diagnostic_consumer"
    root.mkdir()
    summary = {
        "schema": "task041.side_balh.exact_side.v1",
        "status": "completed_with_diagnostics",
        "classification": "DIAGNOSTIC_RESULT_AVAILABLE",
        "identity": {"model_id": model_id},
        "diagnostic_output_policy": {
            "enabled": True,
            "model_id": model_id,
        },
        "diagnostic_output": {"result_available": True},
        "qualification_status": "unqualified",
        "qualification": {"pass": False},
        "formal": {
            "solve": {"pass": True},
            "recovery": {"pass": True, "physics_pass": True},
            "physics": {"pass": True},
        },
        "official_rta": {
            "status": "measured_diagnostic",
            "qualified": False,
            "R": 0.1,
            "T": 0.8,
            "A": 0.1,
            "A_volume": 0.1,
        },
        "lifecycle": {
            "setup_released": True,
            "rss_marker_emitted": True,
        },
        "cleanup": {"pass": True},
        "markers": {"observed": ["final_cleanup_complete"]},
        "gates": {
            "pass": False,
            "authority_identity": {"pass": True},
            "grid_E_H_evidence_pass": True,
            "external_diffraction_channels_pass": True,
            "external_key_binding_pass": True,
            "external_orders_key_binding_pass": True,
            "interface_projection": 1.0e-6,
            "interface_projection_pass": False,
        },
    }
    supervisor._write_json(root / "consumer_summary.json", summary)

    assert task041_balh_diagnostic_output_enabled(model_id) is True
    result = supervisor._consumer_result(
        root,
        process_group_gone=True,
        expected_diagnostic_output=True,
        expected_diagnostic_model_id=model_id,
    )
    assert result["complete"] is True
    assert result["classification"] == "DIAGNOSTIC_RESULT_AVAILABLE"
    assert result["completion_scope"] == "formal"
    assert result["official_rta"]["qualified"] is False
    assert result["gates"]["interface_projection"] == 1.0e-6

    summary["gates"]["external_key_binding_pass"] = False
    supervisor._write_json(root / "consumer_summary.json", summary)
    wrong_key = supervisor._consumer_result(
        root,
        process_group_gone=True,
        expected_diagnostic_output=True,
        expected_diagnostic_model_id=model_id,
    )
    assert wrong_key["complete"] is False
    assert wrong_key["gates"]["external_key_binding_pass"] is False
    summary["gates"]["external_key_binding_pass"] = True

    summary["identity"]["model_id"] = TASK041_BALH_5NM_CANDIDATE_MODEL_ID
    summary["diagnostic_output_policy"]["model_id"] = (
        TASK041_BALH_5NM_CANDIDATE_MODEL_ID
    )
    supervisor._write_json(root / "consumer_summary.json", summary)
    impostor = supervisor._consumer_result(
        root,
        process_group_gone=True,
        expected_diagnostic_output=True,
        expected_diagnostic_model_id=TASK041_BALH_5NM_CANDIDATE_MODEL_ID,
    )
    assert impostor["complete"] is False
    summary["identity"]["model_id"] = model_id
    summary["diagnostic_output_policy"]["model_id"] = model_id
    supervisor._write_json(root / "consumer_summary.json", summary)

    summary["official_rta"]["R"] = float("nan")
    supervisor._write_json(root / "consumer_summary.json", summary)
    nonfinite = supervisor._consumer_result(
        root,
        process_group_gone=True,
        expected_diagnostic_output=True,
        expected_diagnostic_model_id=model_id,
    )
    assert nonfinite["complete"] is False

    summary["official_rta"]["R"] = 0.1
    summary["cleanup"]["pass"] = False
    supervisor._write_json(root / "consumer_summary.json", summary)
    uncleared = supervisor._consumer_result(
        root,
        process_group_gone=True,
        expected_diagnostic_output=True,
        expected_diagnostic_model_id=model_id,
    )
    assert uncleared["complete"] is False

    assert task041_balh_diagnostic_output_enabled(
        TASK041_BALH_5NM_CANDIDATE_MODEL_ID
    ) is False


def test_task041_cell_condensed_v5_service_ledger_uses_compat_view(
    tmp_path: Path, monkeypatch
):
    from src.runners import task041_service as service

    model_id = TASK041_BALH_13P5NM_CELL_CONDENSED_MODEL_ID
    canonical_ledger = (
        REPOSITORY_ROOT
        / "results/task041_review_v5_cpu_numa_condensed_speed/"
        "r0_r1_20260920/r1_load_ledger_20260920.json"
    )
    contract = service._service_contract(
        {
            "model_id": model_id,
            "scope": "formal_consumer",
            "ledger_path": canonical_ledger,
        },
        side_setup_schedule=None,
        comparison_mode=None,
    )
    assert contract["ledger"]["schema"] == "task041.review_v5.r1_load_ledger.v1"

    ledger_path = tmp_path / "r1_load_ledger_20260920.json"
    ledger_path.write_text(
        json.dumps(
            {
                "schema": "task041.review_v5.r1_load_ledger.v1",
                "scope": "test",
                "ledger_status": "measured_plus_conservative_upper_bound",
                "charged_seconds": 10.0,
                "entries": [{"id": "old", "seconds": 10.0}],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    path, loaded = supervisor._load_task041_compute_wall_ledger(ledger_path)
    assert path == ledger_path
    assert loaded["used_compute_wall_seconds"] == pytest.approx(10.0)
    assert loaded["source_records"] == loaded["entries"]
    updated = supervisor._write_task041_compute_wall_ledger(
        ledger_path,
        used_before=loaded,
        current_seconds=2.5,
        run_directory=tmp_path / "run",
        case_id=model_id,
    )
    on_disk = supervisor._read_json(ledger_path)
    assert on_disk["schema"] == "task041.review_v5.r1_load_ledger.v1"
    assert on_disk["charged_seconds"] == pytest.approx(12.5)
    assert len(on_disk["entries"]) == 2
    assert "used_compute_wall_seconds" not in on_disk
    assert updated["used_compute_wall_seconds"] == pytest.approx(12.5)

    observed = {}

    def fake_load(path):
        observed["load_path"] = path
        return path, loaded

    def fake_write(path, **kwargs):
        observed["write"] = kwargs
        return {"used_compute_wall_seconds": 12.5}

    monkeypatch.setattr(
        service.supervisor, "_load_task041_compute_wall_ledger", fake_load
    )
    monkeypatch.setattr(
        service.supervisor, "_write_task041_compute_wall_ledger", fake_write
    )
    result, error = service._record_unit_wall(
        {"ledger_path": ledger_path},
        contract,
        tmp_path / "service-run",
        2.5,
    )
    assert error is None
    assert result["used_compute_wall_seconds"] == pytest.approx(12.5)
    assert observed["write"]["case_id"] == model_id
