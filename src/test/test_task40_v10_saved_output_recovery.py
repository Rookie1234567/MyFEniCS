from __future__ import annotations

import copy
import hashlib
import json
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
from src.runners.task40_v10_saved_output_recovery import (
    _CARRIER_PAYLOAD_SHA256,
    _FROZEN_CURRENT_ASSEMBLY_SOURCE_SHA256,
    _MODE_COUNT,
    _MODE_SHA256,
    _MPC_SHA256,
    _SAVED_ASSEMBLY_SOURCE_SHA256,
    _canonical_identity_bytes,
    _saved_carrier_identity_recheck,
    _saved_scalar_gate_checks,
)


def _saved_carrier_identity_fixture():
    context = {
        "schema": "task40extra.dtn-plane-discrete-context.v1",
        "source_sha256": dict(_FROZEN_CURRENT_ASSEMBLY_SOURCE_SHA256),
        "mesh": {"geometry_x_sha256": "mesh-fixed"},
        "MPC": {"sha256": "mpc-fixed"},
        "gauss": {"degree": 17, "rule": "fixed-test-rule"},
        "ABI": {"scalar": "complex128", "integer": "int32"},
    }
    current_context_sha = hashlib.sha256(_canonical_identity_bytes(context)).hexdigest()
    rows = [
        {
            "mode_index": index,
            "assembly_context_sha256": current_context_sha,
            "physical_mode_fixture": [index, "unchanged"],
        }
        for index in range(_MODE_COUNT)
    ]
    manifest = {
        "schema": "fullspace-dtn.mode-manifest.v1",
        "profile": "full3d_scalable_v1",
        "mode_count": _MODE_COUNT,
        "modes": rows,
    }
    raw_manifest = _canonical_identity_bytes(manifest)
    saved_context = copy.deepcopy(context)
    saved_context["source_sha256"] = dict(_SAVED_ASSEMBLY_SOURCE_SHA256)
    saved_context_sha = hashlib.sha256(_canonical_identity_bytes(saved_context)).hexdigest()
    saved_manifest = copy.deepcopy(manifest)
    for row in saved_manifest["modes"]:
        row["assembly_context_sha256"] = saved_context_sha
    expected_saved_sha = hashlib.sha256(_canonical_identity_bytes(saved_manifest)).hexdigest()
    return {
        "assembly_context": context,
        "mode_manifest_bytes": raw_manifest,
        "carrier_context_sha256": current_context_sha,
        "carrier_manifest_sha256": hashlib.sha256(raw_manifest).hexdigest(),
        "ordered_mode_count": _MODE_COUNT,
        "ordered_mode_sha256": _MODE_SHA256,
        "bundle_mode_sha256": _MODE_SHA256,
        "carrier_payload_sha256": _CARRIER_PAYLOAD_SHA256,
        "mpc_sha256": _MPC_SHA256,
        "saved_packet_mpc_sha256": _MPC_SHA256,
        "expected_saved_assembly_sha256": expected_saved_sha,
    }


def _refresh_current_context_and_manifest_hashes(inputs):
    context_sha = hashlib.sha256(_canonical_identity_bytes(inputs["assembly_context"])).hexdigest()
    manifest = json.loads(inputs["mode_manifest_bytes"])
    for row in manifest["modes"]:
        row["assembly_context_sha256"] = context_sha
    raw_manifest = _canonical_identity_bytes(manifest)
    inputs["carrier_context_sha256"] = context_sha
    inputs["mode_manifest_bytes"] = raw_manifest
    inputs["carrier_manifest_sha256"] = hashlib.sha256(raw_manifest).hexdigest()


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


def test_saved_carrier_rebind_replays_only_the_reviewed_source_hashes():
    result = _saved_carrier_identity_recheck(**_saved_carrier_identity_fixture())

    assert result["passed"]
    assert all(result["checks"].values())
    assert result["actual"]["rebuilt_saved_manifest_sha256"] == result["expected"][
        "saved_carrier_assembly_sha256"
    ]
    assert result["actual"]["source_sha256"] == result["expected"][
        "frozen_current_source_sha256"
    ]


def test_saved_carrier_rebind_rejects_an_unreviewed_source_change():
    inputs = _saved_carrier_identity_fixture()
    inputs["assembly_context"]["source_sha256"]["dtn_boundary_phase_gauge.py"] = "f" * 64
    _refresh_current_context_and_manifest_hashes(inputs)

    result = _saved_carrier_identity_recheck(**inputs)

    assert not result["passed"]
    assert not result["checks"]["source_sha256_matches_frozen_review"]
    assert result["checks"]["rebuilt_saved_manifest_matches_frozen_sha"]


def test_saved_carrier_rebind_rejects_non_source_discrete_context_change():
    inputs = _saved_carrier_identity_fixture()
    inputs["assembly_context"]["mesh"]["geometry_x_sha256"] = "changed-mesh"
    _refresh_current_context_and_manifest_hashes(inputs)

    result = _saved_carrier_identity_recheck(**inputs)

    assert not result["passed"]
    assert result["checks"]["source_sha256_matches_frozen_review"]
    assert not result["checks"]["rebuilt_saved_manifest_matches_frozen_sha"]


@pytest.mark.parametrize(
    ("field", "wrong_sha"),
    [
        ("carrier_payload_sha256", "0" * 64),
        ("mpc_sha256", "1" * 64),
        ("saved_packet_mpc_sha256", "2" * 64),
    ],
)
def test_saved_carrier_rebind_keeps_payload_and_mpc_guards_strict(field, wrong_sha):
    inputs = _saved_carrier_identity_fixture()
    inputs[field] = wrong_sha

    result = _saved_carrier_identity_recheck(**inputs)

    assert not result["passed"]
    assert result["checks"]["rebuilt_saved_manifest_matches_frozen_sha"]
    if field == "carrier_payload_sha256":
        assert not result["checks"]["carrier_payload_sha_matches_saved_packet"]
    else:
        assert not result["checks"]["rebuilt_mpc_sha_matches_frozen_and_saved"]


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
