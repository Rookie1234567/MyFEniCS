from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.run_case import _parser as run_case_parser
from src.runners import task038_input_worker
from src.io.input_validation import InputError
from src.runners.task038_launcher import (
    _task40_v10_postprocess_worker_argv,
    _validate_task40_v10_postprocess_request,
)
from src.runners.task40_v10_saved_output_recovery import _saved_scalar_gate_checks


def test_run_case_accepts_saved_output_and_campaign_arguments():
    args = run_case_parser().parse_args(
        [
            "candidate.dat",
            "--task40-v10-campaign-window",
            "campaign.json",
            "--task40-v10-postprocess-from",
            "failed-run",
        ]
    )
    assert args.task40_v10_campaign_window == Path("campaign.json")
    assert args.task40_v10_postprocess_from == Path("failed-run")


def test_launcher_only_appends_saved_output_arg_when_requested(tmp_path):
    base = ("mpiexec", "-n", "1", "python", "-m", "worker")
    assert _task40_v10_postprocess_worker_argv(base, None) == list(base)
    result = _task40_v10_postprocess_worker_argv(base, tmp_path / "saved")
    assert result[:-2] == list(base)
    assert result[-2:] == [
        "--task40-v10-postprocess-from",
        str((tmp_path / "saved").resolve()),
    ]


def test_saved_scalar_gates_reject_nan():
    packet = {
        "relative_residual": 1.0e-8,
        "native_witness_relative_residual": 1.0e-8,
        "actual_port_residual_relative": 1.0e-12,
        "actual_internal_residual_relative": 1.0e-12,
        "actual_native_identity_relative": 1.0e-12,
        "actual_schur_port_identity_relative": 1.0e-12,
        "solver_reported_true_residual": 1.0e-8,
    }
    assert all(_saved_scalar_gate_checks(packet).values())
    packet["actual_port_residual_relative"] = float("nan")
    assert not _saved_scalar_gate_checks(packet)["port"]


def test_saved_output_entry_rejects_wrong_candidate_campaign_and_probe():
    with pytest.raises(InputError, match="frozen B0 candidate"):
        _validate_task40_v10_postprocess_request(
            candidate_identity=False,
            campaign_window="campaign.json",
            saved_run_directory="old-run",
        )
    with pytest.raises(InputError, match="fixed campaign window"):
        _validate_task40_v10_postprocess_request(
            candidate_identity=True,
            campaign_window=None,
            saved_run_directory="old-run",
        )
    with pytest.raises(InputError, match="contract probe"):
        _validate_task40_v10_postprocess_request(
            candidate_identity=True,
            campaign_window="campaign.json",
            saved_run_directory="old-run",
            contract_probe=True,
        )


def test_worker_saved_output_path_short_circuits_numerical_adapter(monkeypatch):
    class FakeComm:
        size = 1
        rank = 0

        @staticmethod
        def allreduce(value, op=None):
            return value

    fake_mpi = SimpleNamespace(COMM_WORLD=FakeComm(), LOR=object())
    monkeypatch.setitem(sys.modules, "mpi4py", SimpleNamespace(MPI=fake_mpi))
    monkeypatch.setattr(
        task038_input_worker,
        "_load_and_validate_worker_payload",
        lambda **_kwargs: ({"run_id": "task40extra_0p7nm_b0_p6_y_orbit_candidate_v10"}, []),
    )
    calls = []

    def recover(payload, run_directory, saved_run_directory, *, source_sha):
        calls.append((payload, run_directory, saved_run_directory, source_sha))
        return {"passed": True, "summary": {"status": "PASS"}}

    from src.runners import task40_v10_saved_output_recovery

    monkeypatch.setattr(
        task40_v10_saved_output_recovery,
        "recover_task40_v10_saved_output",
        recover,
    )
    monkeypatch.setattr(
        task038_input_worker,
        "_dispatch_resolved_payload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("numeric adapter ran")),
    )

    worker_argv = [
            "--resolved-config",
            "resolved.json",
            "--manifest",
            "manifest.json",
            "--expected-input-sha256",
            "a" * 64,
            "--expected-physical-model-sha256",
            "b" * 64,
            "--expected-source-sha",
            "c" * 40,
            "--expected-mpi-size",
            "1",
            "--expected-method",
            "full3d_iterative",
            "--expected-adapter",
            "adapter",
            "--expected-output-directory",
            "new-run",
            "--resolved-config-sha256",
            "d" * 64,
            "--task40-v10-postprocess-from",
            "old-run",
        ]
    result = task038_input_worker.main(worker_argv)
    assert result == 0
    assert calls == [
        (
            {"run_id": "task40extra_0p7nm_b0_p6_y_orbit_candidate_v10"},
            Path("new-run"),
            Path("old-run"),
            "c" * 40,
        )
    ]
    assert task038_input_worker.main([*worker_argv, "--contract-probe"]) == 2
    assert len(calls) == 1
