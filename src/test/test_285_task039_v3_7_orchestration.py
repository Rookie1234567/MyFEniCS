"""Pure contracts for the pre-heavy Task39 V3-7 orchestration."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from mpi4py import MPI

import benchmarks.task039_v3_7_orchestration as orchestration
from benchmarks import run_task037b_hybrid_iterative as frozen_runner
from benchmarks.task037c_robustness import Task37cProfile
from benchmarks.task039_v3_7_orchestration import (
    V3_7_ABSOLUTE_HARD_BYTES,
    V3_7_PROFILE_ID,
    _json_safe,
    _record_v3_7_marker,
    _v3_7_cleanup_callback,
    _v3_7_object_ledger,
    _write_v3_7_candidate_authority,
    _write_v3_7_object_ledger,
    load_v3_7_official_payload,
    load_v3_7_direct_inventory,
    run_v3_7_stage_sequence,
    v3_7_execution_dry_run,
    v3_7_profile_from_resolved,
    v3_7_watchdog_policy,
    validate_v3_7_resolved_identity,
)
from benchmarks.task039_hybrid_direct_identity import _parse_orders
from src.io.input_validation import task039_dynamic_external_mode_inventory
from src.modes.mode_classification import _near_degenerate_partition_audit


INPUT = Path("input/official/task039/5nm_p6h5_v3_1deg_hybrid_direct_m480_mpi8.dat")


def test_v3_7_profile_is_derived_from_official_one_degree_s_input() -> None:
    payload = load_v3_7_official_payload(INPUT)
    profile = v3_7_profile_from_resolved(payload)
    assert profile.profile_id == V3_7_PROFILE_ID
    assert profile.incident_grazing_deg == 1.0
    assert profile.incident_phi_deg == 0.0
    assert profile.polarization_kind == "s"
    assert profile.h_nm == 5.0
    assert profile.modal_h_nm == 5.0
    assert profile.requested_modes == 480
    assert profile.candidate_modes == 960
    assert profile.max_it == 4000

    wrong_angle = dict(payload)
    wrong_angle["incidence"] = dict(payload["incidence"], grazing_angle_deg=10.0)
    with pytest.raises(ValueError, match="official physical/discrete identity"):
        validate_v3_7_resolved_identity(wrong_angle)

    wrong_polarization = dict(payload)
    wrong_polarization["incidence"] = dict(payload["incidence"], polarization="S")
    with pytest.raises(ValueError):
        validate_v3_7_resolved_identity(wrong_polarization)


def test_qep_tolerance_is_explicit_and_profile_selected() -> None:
    assert frozen_runner.FROZEN_M10.qep_solver_tolerance == 1.0e-10
    assert Task37cProfile().qep_solver_tolerance == 1.0e-10
    profile = v3_7_profile_from_resolved(load_v3_7_official_payload(INPUT))
    assert profile.qep_solver_tolerance == 1.0e-13
    assert profile.retained_subspace_dual_rotation is True
    assert (
        getattr(frozen_runner.FROZEN_M10, "retained_subspace_dual_rotation", False)
        is False
    )
    assert getattr(Task37cProfile(), "retained_subspace_dual_rotation", False) is False
    source = inspect.getsource(frozen_runner.build_frozen_m10_setup)
    assert source.count("\n        tolerance=profile.qep_solver_tolerance") == 2
    assert (
        source.count("\n        qep_solver_tolerance=profile.qep_solver_tolerance") == 2
    )
    assert (
        source.count(
            "\n        retained_subspace_dual_rotation=bool(\n"
            '            getattr(profile, "retained_subspace_dual_rotation", False)\n'
            "        ),"
        )
        == 2
    )


def test_task039_qep_basis_audit_is_compact_and_fail_closed() -> None:
    basis = SimpleNamespace(
        near_degenerate_partition_audit={
            "status": "near_degenerate_block_partition_pass",
            "pass": True,
            "biorthogonality_identity_row_norm": 1.0e-9,
            "biorthogonality_identity_max_entry": 1.0e-10,
            "max_cross_block_overlap": 1.0e-10,
            "near_degenerate_tolerance": 1.0e-6,
            "block_rotation_tolerance": 1.0e-6,
            "group_members": list(range(480)),
        },
        retained_subspace_dual_rotation_audit=None,
        modes=[SimpleNamespace(left_polynomial_relative_residual=2.0e-15)],
    )
    report = frozen_runner._task039_qep_basis_audit(basis, side="forward")
    assert report["overall_pass"] is True
    assert "group_members" not in report["partition_audit"]

    failing_rotation = SimpleNamespace(
        near_degenerate_partition_audit={"pass": True},
        retained_subspace_dual_rotation_audit={"overall_pass": False},
        modes=[SimpleNamespace(left_polynomial_relative_residual=2.0e-15)],
    )
    with pytest.raises(RuntimeError, match="backward QEP basis audit failed"):
        frozen_runner._task039_qep_basis_audit(failing_rotation, side="backward")

    failing_residual = SimpleNamespace(
        near_degenerate_partition_audit={"pass": True},
        retained_subspace_dual_rotation_audit=None,
        modes=[SimpleNamespace(left_polynomial_relative_residual=1.0e-7)],
    )
    with pytest.raises(RuntimeError, match="forward QEP basis audit failed"):
        frozen_runner._task039_qep_basis_audit(failing_residual, side="forward")


def test_v3_7_partition_fixture_stays_outside_near_degenerate_envelope() -> None:
    beta_distance = 4.116479e-5
    betas = (1.0 + 0.0j, 1.0 + beta_distance + 0.0j)
    overlap = np.eye(2, dtype=np.complex128)
    overlap[0, 1] = 8.443521e-6
    audit = _near_degenerate_partition_audit(
        betas,
        ((0,), (1,)),
        overlap,
        near_degenerate_tolerance=1.0e-6,
        block_rotation_tolerance=1.0e-6,
    )
    assert audit["pass"] is False
    assert audit["status"] == "cross_block_biorthogonality_failure"
    assert audit["worst_cross_block_is_near_degenerate_candidate"] is False
    assert audit["max_cross_block_overlap"] == pytest.approx(8.443521e-6)
    assert audit["worst_cross_block_relative_beta_distance"] > 1.0e-5


def test_v3_7_watchdog_keeps_195_as_checkpoint_and_224gb_as_byte_hard_stop() -> None:
    payload = load_v3_7_official_payload(INPUT)
    policy = v3_7_watchdog_policy(payload)
    assert policy["critical_action"] == "record_checkpoint_only"
    assert policy["absolute_terminate_memory_bytes"] == V3_7_ABSOLUTE_HARD_BYTES
    assert policy["poll_interval_seconds"] == 0.25
    with pytest.raises(ValueError):
        v3_7_watchdog_policy(payload, poll_interval_seconds=0.251)


def test_v3_7_direct_modal_loader_checks_hash_bound_payload(
    tmp_path, monkeypatch
) -> None:
    payload = load_v3_7_official_payload(INPUT)
    values = np.arange(960, dtype=np.float64) + 1j * np.arange(960, dtype=np.float64)
    artifact = tmp_path / "task039_direct_payload.npz"
    np.savez(artifact, modal_amplitudes=values)
    descriptor = {
        "shape": [960],
        "dtype": "complex128",
        "sha256": hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest(),
    }
    inventory = {
        "verified_shard_count": 32,
        "payload": {
            "artifact": {"path": str(artifact)},
            "arrays": {"modal_amplitudes": descriptor},
        },
    }
    monkeypatch.setattr(
        orchestration,
        "load_task039_direct_solution_inventory",
        lambda *args, **kwargs: inventory,
    )
    manifest = {
        "model_id": "task039_5nm_v3_1deg_s5_hybrid_direct_m480",
        "method": "hybrid_direct",
        "mpi_size": 8,
        "external_mode_inventory": task039_dynamic_external_mode_inventory(payload),
    }
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    producer, loaded = load_v3_7_direct_inventory(
        payload,
        run_dir,
        producer_source_sha="producer-sha",
    )
    assert producer["verified_shard_count"] == 32
    assert loaded.shape == (960,)


def test_v3_7_stage_sequence_requires_recovery_after_oracle_cleanup() -> None:
    events: list[str] = []

    class Solution:
        def duplicate(self) -> "Solution":
            events.append("duplicate")
            return Solution()

        def copy(self, other: "Solution") -> None:
            events.append("copy")

    def oracle(consume):
        events.append("oracle_start")
        consume(Solution(), {"pass": True})
        events.append("oracle_return")
        return {"pass": True}

    report = run_v3_7_stage_sequence(
        identity_stage=lambda: {"pass": True},
        correction_stage=lambda: {"pass": True},
        oracle_stage=oracle,
        snapshotter=lambda solution: solution.duplicate(),
        recovery_runner=lambda snapshot: events.append("recovery") or {"pass": True},
    )
    assert report["status"] == "completed"
    assert events.index("oracle_return") < events.index("recovery")
    assert report["solution_handoff"] == "recovery_after_oracle_cleanup"


def test_v3_7_stage_sequence_recovery_failure_is_not_completed() -> None:
    report = run_v3_7_stage_sequence(
        identity_stage=lambda: {"pass": True},
        correction_stage=lambda: {"pass": True},
        oracle_stage=lambda consume: (
            consume(object(), {"pass": True}) or {"pass": True}
        ),
        snapshotter=lambda solution: object(),
        recovery_runner=lambda snapshot: {"pass": False, "status": "physics_fail"},
    )
    assert report["status"] == "oracle_linear_pass_physics_fail"


def test_v3_7_candidate_authority_serializes_complex_orders_for_parser(
    tmp_path,
) -> None:
    class Physics:
        own_grid = {"path": "grid.npz"}
        external_orders = [
            {
                "side": "bottom",
                "m": 0,
                "n": 0,
                "polarization": "s",
                "power_ratio": np.float64(0.5),
                "outgoing_amplitude": 1.0 + 2.0j,
            }
        ]
        energy = {
            "R": 0.2,
            "T": 0.3,
            "A": 0.5,
            "A_volume": 0.5,
            "closure": 0.0,
        }
        traction = {"bottom": {"relative_dual": 0.0}, "top": {"relative_dual": 0.0}}
        interface_e_projection = {"combined_relative_residual": 0.0}

    run_directory = tmp_path / "run"
    _write_v3_7_candidate_authority(
        run_directory,
        Physics(),
        {
            "consumer_source_sha": "a" * 40,
            "physical_model_sha256": "b" * 64,
        },
        MPI.COMM_SELF,
    )
    authority = json.loads(
        (run_directory / "numerical_output" / "v3_7_hybrid_authority.json").read_text(
            encoding="utf-8"
        )
    )
    assert authority["external_orders"][0]["outgoing_amplitude"] == [1.0, 2.0]
    parsed = _parse_orders(authority["external_orders"], "candidate", expected_count=1)
    assert parsed[("bottom", 0, 0, "s")]["outgoing_amplitude"] == 1.0 + 2.0j
    assert _json_safe(np.asarray([1.0 + 2.0j])) == [[1.0, 2.0]]


def test_v3_7_ledger_is_atomic_noncollective_and_tracks_cleanup_boundary(
    tmp_path,
) -> None:
    class NoBarrierComm:
        rank = 0

        def barrier(self):
            raise AssertionError("marker checkpoint must not enter a barrier")

    ledger = _v3_7_object_ledger()
    for marker in (
        "lift_columns_begin",
        "apply_columns_begin",
        "bottom_projection_begin",
        "top_projection_begin",
    ):
        _record_v3_7_marker(ledger, marker, {})
    _record_v3_7_marker(ledger, "identity_reference_materialization_end", {})
    _record_v3_7_marker(ledger, "borrowed_reference_cleanup_end", {})
    _record_v3_7_marker(ledger, "side_fixed_components_setup_end", {})
    _record_v3_7_marker(ledger, "side_survey_cleanup_end", {})
    _record_v3_7_marker(ledger, "one_cell_factor_destroyed", {})
    path = tmp_path / "numerical_output" / "memory_object_ledger.json"
    _write_v3_7_object_ledger(path, ledger, NoBarrierComm(), synchronize=False)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded["objects"]["one_cell_factor"]["destroyed"] is True
    assert loaded["objects"]["side_base_ilu"]["destroyed"] is True
    assert loaded["objects"]["independent_reference"]["destroyed"] is True
    for name in (
        "lift_columns",
        "apply_columns",
        "bottom_projection",
        "top_projection",
    ):
        assert loaded["objects"][name]["destroyed"] is True


def test_v3_7_formal_worker_injects_collective_cleanup_callback(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        orchestration,
        "collective_heap_cleanup",
        lambda comm: calls.append(comm) or {"collective_call_completed": True},
    )
    cleanup = _v3_7_cleanup_callback(MPI.COMM_SELF, None)
    assert cleanup()["collective_call_completed"] is True
    assert calls == [MPI.COMM_SELF]


def test_v3_7_dry_run_freezes_mpi8_worker_and_byte_watchdog(tmp_path) -> None:
    qualified_like = tmp_path / "qualified-python"
    qualified_like.symlink_to("/usr/bin/python3.12")
    plan = v3_7_execution_dry_run(
        INPUT,
        tmp_path / "run",
        source_sha="a" * 40,
        python_executable=qualified_like,
    )
    assert plan["argv"][1:3] == ["-n", "8"]
    assert plan["argv"][3] == str(qualified_like)
    assert "--worker" in plan["argv"]
    assert "--launched-by-task038-watchdog" in plan["argv"]
    assert plan["watchdog"]["absolute_terminate_memory_bytes"] == 224000000000
    assert plan["watchdog"]["critical_action"] == "record_checkpoint_only"


def test_v3_7_boot_markers_bound_setup_sentinel_failure(tmp_path) -> None:
    payload = load_v3_7_official_payload(INPUT)
    run_directory = tmp_path / "setup-sentinel"

    def setup_sentinel(*_args, **_kwargs):
        raise RuntimeError("V3_7_SETUP_SENTINEL_REACHED")

    with pytest.raises(RuntimeError, match="V3_7_SETUP_SENTINEL_REACHED"):
        orchestration.run_task039_v3_7_diagnostic(
            payload,
            run_directory,
            source_sha="a" * 40,
            comm=MPI.COMM_SELF,
            setup_builder=setup_sentinel,
            inventory_loader=lambda *_args, **_kwargs: (
                {},
                np.zeros(960, dtype=complex),
            ),
            recovery_runner=lambda *_args, **_kwargs: {"pass": True},
        )

    marker_path = run_directory / "numerical_output" / "memory_stage_markers.raw.jsonl"
    markers = [
        json.loads(line)["stage"]
        for line in marker_path.read_text(encoding="utf-8").splitlines()
    ]
    assert markers == [
        "diagnostic_entry",
        "profile_ready",
        "watchdog_ready",
        "inventory_ready",
        "config_ready",
        "setup_begin",
    ]
    ledger = json.loads(
        (run_directory / "numerical_output" / "memory_object_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    assert ledger["status"] == "exception"


def test_v3_7_direct_authority_is_not_blocked_by_full3d_secondary_error(
    tmp_path, monkeypatch
) -> None:
    candidate = tmp_path / "candidate" / "numerical_output"
    candidate.mkdir(parents=True)
    (candidate / "v3_7_hybrid_authority.json").write_text("{}", encoding="utf-8")
    direct = tmp_path / "direct"
    full3d = tmp_path / "full3d"
    direct.mkdir()
    full3d.mkdir()
    monkeypatch.setattr(
        orchestration,
        "compare_v3_7_hybrid_candidate_to_direct",
        lambda *_args: {"pass": True, "classification": "direct_pass"},
    )
    monkeypatch.setattr(
        orchestration,
        "compare_v3_7_hybrid_candidate_to_full3d",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("secondary fixture")),
    )
    result = orchestration.check_v3_7_integrated_physics(
        candidate.parent, direct, full3d
    )
    assert result["pass"] is True
    assert result["full3d_secondary"]["status"] == "checker_error"

    monkeypatch.setattr(
        orchestration,
        "compare_v3_7_hybrid_candidate_to_direct",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("direct fixture")),
    )
    failed = orchestration.check_v3_7_integrated_physics(candidate.parent, direct)
    assert failed["pass"] is False
    assert failed["status"] == "checker_error"


def test_v3_7_one_cell_cleanup_does_not_invent_unseen_arrays() -> None:
    ledger = _v3_7_object_ledger()
    _record_v3_7_marker(ledger, "one_cell_factor_destroyed", {})
    for name in (
        "lift_columns",
        "apply_columns",
        "bottom_projection",
        "top_projection",
    ):
        assert ledger["objects"][name]["created"] is False
        assert ledger["objects"][name]["destroyed"] is False
        assert ledger["objects"][name]["status"] == "not_available"
