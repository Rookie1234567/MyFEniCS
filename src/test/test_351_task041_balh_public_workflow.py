"""Focused public-contract tests for the Task041 side-BAL_H profiles."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

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
    _merge_representative_parts,
    _task041_case_contract,
    _task041_common_failure_details,
    _task041_stream_array_metadata,
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
    _validate_common_layout_equivalence_result,
    _validate_representative_rhs_result,
    _validate_specification,
    run_task041_public_supervisor,
)
from src.solvers.physical_balanced_coupling import BalancedConstraintRejected
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
    ]
    assert run_case.main(opt_in_argv) == 0
    assert captured[-1][1]["performance_profile"] == (
        TASK041_SCHUR_SPEED_V2_PROFILE
    )
    assert captured[-1][1]["task041_rhs_probe_manifest"] == probe_manifest
    assert captured[-1][1]["task041_side_setup_schedule"] == (
        TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
    )

    contract = task041_schur_speed_v2_contract(
        candidate_model,
        scope=TASK041_REPRESENTATIVE_RHS_SCOPE,
        side_setup_schedule=TASK041_SEQUENTIAL_COMPONENT_SCHEDULE,
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
    )
    worker_args = command[command.index("--worker") :]
    parsed = task041_balh_workflow._parser().parse_args(worker_args)
    assert parsed.task041_performance_profile == TASK041_SCHUR_SPEED_V2_PROFILE
    assert parsed.task041_rhs_probe == str(probe_manifest)
    assert parsed.task041_side_setup_schedule == (
        TASK041_SEQUENTIAL_COMPONENT_SCHEDULE
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
    path = REPOSITORY_ROOT / "input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_exact.dat"
    captured = {}

    def fake_launch(specification, **kwargs):
        captured["model_id"] = specification.identity["model_id"]
        captured["kwargs"] = kwargs
        return {"result_classification": "worker_exit0"}

    monkeypatch.setattr("src.runners.task038_launcher.launch_specification", fake_launch)
    assert run_case.main([str(path)]) == 0
    assert captured["model_id"] == "task041_13p5nm_exact_side_hybrid_iterative_p6h10_m120_mpi8"
    assert captured["kwargs"]["producer_packet_root"] is None


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


def test_task041_balh_reused_public_producer_starts_only_one_consumer(
    tmp_path: Path, monkeypatch
):
    exact = _specification(
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_exact.dat"
    )
    candidate = _specification(
        REPOSITORY_ROOT
        / "input/official/task041/side_balh/13p5nm_p6h10_m120_mpi8_balh.dat"
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
    (producer_root / "packet_identity.json").write_text(
        json.dumps(producer_identity, sort_keys=True) + "\n", encoding="utf-8"
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
    observed_schedules = []

    def fake_consumer_result(
        consumer_root, process_group_gone, expected_side_setup_schedule=None
    ):
        observed_schedules.append(expected_side_setup_schedule)
        assert expected_side_setup_schedule is None
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

    candidate_run = tmp_path / "candidate_public_run"
    candidate_run.mkdir()
    ledger_path = tmp_path / "compute_wall_ledger.json"
    ledger_path.write_text(
        json.dumps(
            {
                "schema": "task041.compute_wall_ledger.v1",
                "limit_seconds": 172800.0,
                "used_compute_wall_seconds": 0.0,
                "used_status": "measured",
                "basis": "test-local BALH mock ledger",
                "measured": {"status": "measured", "seconds": 0.0, "records": []},
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
        compute_wall_ledger_path=ledger_path,
        python_executable="python",
        producer_packet_root=producer_root,
        popen_factory=fake_popen,
        sample_factory=fake_sample,
        process_group_gone=lambda _pid: True,
        sleep=lambda _: None,
    )
    assert result["result_classification"] == "worker_exit0"
    assert len(popen_calls) == 1
    assert observed_schedules == [None]
    assert popen_calls[0][popen_calls[0].index("--phase") + 1] == "candidate-consumer"
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
