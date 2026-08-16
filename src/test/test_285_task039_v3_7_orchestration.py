"""Pure contracts for the pre-heavy Task39 V3-7 orchestration."""

from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

import benchmarks.task039_v3_7_orchestration as orchestration
import benchmarks.task039_v3_7_watchdog as watchdog
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
    _write_v3_7_side_survey_checkpoint,
    load_v3_7_official_payload,
    load_v3_7_direct_inventory,
    run_v3_7_stage_sequence,
    v3_7_execution_dry_run,
    v3_7_profile_from_resolved,
    v3_7_watchdog_policy,
    validate_v3_7_resolved_identity,
)
from benchmarks.task039_hybrid_direct_identity import (
    _parse_orders,
    _same_external_key_set,
)
from src.io.input_validation import task039_dynamic_external_mode_inventory
from src.modes.mode_classification import _near_degenerate_partition_audit


INPUT = Path("input/official/task039/5nm_p6h5_v3_1deg_hybrid_direct_m480_mpi8.dat")


def _tiny_side_system(rhs_values=(0.0, 0.0)):
    matrix = PETSc.Mat().createAIJ(size=(2, 2), nnz=1, comm=PETSc.COMM_SELF)
    matrix.setValue(0, 0, 1.0)
    matrix.setValue(1, 1, 1.0)
    matrix.assemble()
    rhs = matrix.createVecRight()
    for index, value in enumerate(rhs_values):
        rhs.setValue(index, PETSc.ScalarType(value))
    rhs.assemble()
    return SimpleNamespace(A=matrix, b=rhs), matrix, rhs


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


def test_v3_7_external_key_gate_compares_sets_not_enumeration_order() -> None:
    keys = (
        ("bottom", 0, 0, "s"),
        ("top", 1, 0, "s"),
    )
    assert _same_external_key_set(keys, tuple(reversed(keys))) is True
    assert _same_external_key_set(keys, (keys[0], ("top", 2, 0, "s"))) is False
    assert _same_external_key_set(keys, keys[:1]) is False


def test_v3_7_ledger_is_atomic_noncollective_and_tracks_cleanup_boundary(
    tmp_path,
) -> None:
    class NoBarrierComm:
        rank = 0

        def barrier(self):
            raise AssertionError("marker checkpoint must not enter a barrier")

    ledger = _v3_7_object_ledger()
    _record_v3_7_marker(ledger, "qep_matrices_ready", {})
    _record_v3_7_marker(
        ledger,
        "modal_qep_temporaries_released",
        {"release_pass": True},
    )
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
    assert loaded["objects"]["qep_matrices"]["created"] is True
    assert loaded["objects"]["qep_matrices"]["destroyed"] is True
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


def test_v3_8_candidate_e_dry_run_and_route_exclusivity(tmp_path) -> None:
    plan = watchdog.v3_7_execution_dry_run(
        INPUT,
        tmp_path / "candidate-e",
        source_sha="a" * 40,
        candidate_e_side_only=True,
    )
    assert "--candidate-e-side-only" in plan["argv"]
    assert plan["worker_contract"]["method"] == (
        "hybrid_iterative_candidate_e_side_only"
    )
    with pytest.raises(ValueError, match="QEP-only"):
        watchdog.v3_7_execution_dry_run(
            INPUT,
            tmp_path / "candidate-e-conflict",
            source_sha="a" * 40,
            candidate_b_only=True,
            candidate_e_side_only=True,
        )


@pytest.mark.parametrize(
    ("median", "worst", "complete", "expected"),
    (
        (0.1, 0.3, True, True),
        (0.100001, 0.3, True, False),
        (0.1, 0.300001, True, False),
        (0.1, 0.3, False, False),
    ),
)
def test_v3_8_candidate_e_side_gate(median, worst, complete, expected) -> None:
    assert (
        orchestration._candidate_e_side_gate(
            {
                "pass": complete,
                "rho_summary": {"median": median, "worst": worst},
            }
        )
        is expected
    )


def test_v3_8_candidate_e_branch_skips_global_stages_and_closes_ledger(
    tmp_path, monkeypatch
) -> None:
    payload = load_v3_7_official_payload(INPUT)
    called: list[str] = []

    class Layout:
        comm = MPI.COMM_SELF

        @classmethod
        def build(cls, *_args):
            return cls()

    class Rhs:
        def destroy(self):
            called.append("rhs_destroy")

    setup = SimpleNamespace(
        bottom=SimpleNamespace(),
        top=SimpleNamespace(),
        coupling=SimpleNamespace(internal_unknown_count=0),
    )
    run_directory = tmp_path / "candidate-e"
    run_directory.mkdir()
    (run_directory / "resolved_config.json").write_text("{}\n", encoding="utf-8")
    checkpoint = (
        run_directory / "numerical_output" / "v3_8_candidate_e_side_checkpoint.json"
    )

    def campaign(*_args, **kwargs):
        called.append("candidate_e")
        marker_callback = kwargs["marker_callback"]
        marker_callback("candidate_e_side_fixed_setup_end", {})
        marker_callback("candidate_e_correction_actions_ready", {"live": 2})
        marker_callback("candidate_e_side_fixed_cleanup_end", {})
        return {
            "status": "measured",
            "pass": False,
            "training": {
                side: {"seed_ids": list(orchestration.V3_8_CANDIDATE_E_TRAINING_SEEDS)}
                for side in ("bottom", "top")
            },
            "side_reports": {
                side: {"rho_summary": {"median": 0.2, "worst": 0.4}}
                for side in ("bottom", "top")
            },
            "factor_inventory": {
                "per_side": {
                    side: {
                        "base_factor_count": 1,
                        "local_direct_factor_count": 0,
                        "global_hybrid_direct_factor_count": 0,
                    }
                    for side in ("bottom", "top")
                }
            },
        }, checkpoint

    def forbidden(*_args, **_kwargs):
        raise AssertionError("identity/oracle/recovery path was entered")

    monkeypatch.setattr(orchestration, "HybridAugmentedLayout", Layout)
    monkeypatch.setattr(orchestration, "_default_rhs", lambda *_args: Rhs())
    monkeypatch.setattr(
        orchestration, "release_frozen_m10_objects", lambda *_args: None
    )
    monkeypatch.setattr(orchestration, "_run_v3_8_candidate_e_side_campaign", campaign)
    result = orchestration.run_task039_v3_7_diagnostic(
        payload,
        run_directory,
        source_sha="a" * 40,
        comm=MPI.COMM_SELF,
        setup_builder=lambda *_args, **_kwargs: setup,
        inventory_loader=lambda *_args, **_kwargs: (
            {
                "producer_source_sha": "p" * 40,
                "physical_model_sha256": "m" * 64,
                "model_id": "task039-test",
                "requested_modes": 480,
                "mpi_size": 8,
                "external_keys_exact": True,
                "inventory": {},
            },
            np.zeros(960, dtype=np.complex128),
        ),
        reference_builder=forbidden,
        identity_runner=forbidden,
        oracle_runner=forbidden,
        recovery_runner=None,
        candidate_e_side_only=True,
    )
    assert called == ["candidate_e", "rhs_destroy"]
    assert result["schema"] == "task039.v3-8-candidate-e-side-only.v1"
    assert result["direct_reference_payload_loaded"] is True
    assert result["candidate_e"]["training"]["bottom"]["seed_ids"] == list(
        orchestration.V3_8_CANDIDATE_E_TRAINING_SEEDS
    )
    for side in ("bottom", "top"):
        inventory = result["candidate_e"]["factor_inventory"]["per_side"][side]
        assert inventory["local_direct_factor_count"] == 0
        assert inventory["global_hybrid_direct_factor_count"] == 0
    ledger = json.loads(
        (run_directory / "numerical_output" / "memory_object_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    assert ledger["objects"]["side_base_ilu"]["destroyed"] is True
    assert ledger["objects"]["correction_wrappers"]["destroyed"] is True


@pytest.mark.parametrize(
    ("pass_budget", "expected_budgets"),
    ((8, [8]), (16, [8, 16]), (None, [8, 16, 32])),
)
def test_v3_8_candidate_b_budget_order_and_single_wrapper(
    monkeypatch, pass_budget, expected_budgets
) -> None:
    created: list[int] = []
    destroyed: list[int] = []

    class Fixed:
        diagnostics = {
            "base_factor_count": 1,
            "local_direct_factor_count": 0,
            "global_hybrid_direct_factor_count": 0,
        }

    class Action:
        def __init__(self, _operator, fixed, *, budget):
            self.budget = budget
            self.right_preconditioner = fixed
            created.append(budget)

        @property
        def diagnostics(self):
            return {
                "direct_factor_count": 0,
                "global_hybrid_direct_factor_count": 0,
                "right_preconditioner_identity": "fake_fixed",
            }

        def destroy(self):
            destroyed.append(self.budget)

    def probe(_system, action, budget, _vectors, _metadata):
        passed = pass_budget is not None and budget >= pass_budget
        return {"rho_summary": {"candidate_B_pass": passed}}

    monkeypatch.setattr(
        orchestration, "HybridLocalDtnWoodburyFixedBudgetKrylovAction", Action
    )
    monkeypatch.setattr(orchestration, "_candidate_b_side_probe", probe)
    systems = {
        "bottom": SimpleNamespace(A=object()),
        "top": SimpleNamespace(A=object()),
    }
    fixed = {"bottom": Fixed(), "top": Fixed()}
    events: list[str] = []
    report = orchestration.run_v3_8_candidate_b_budget_sequence(
        systems,
        fixed,
        {"bottom": {}, "top": {}},
        {"bottom": {}, "top": {}},
        marker_callback=lambda marker, _detail: events.append(marker),
    )
    assert report["budgets_run"] == expected_budgets
    assert created == [budget for budget in expected_budgets for _ in (0, 1)]
    assert destroyed == created
    assert report["selected_budget"] == pass_budget
    assert report["factor_inventory"]["per_budget"]
    assert report["factor_inventory"]["simultaneous_total_base_factor_count"] == 2
    assert report["factor_inventory"]["simultaneous_total_direct_factor_count"] == 0
    assert (
        report["factor_inventory"][
            "simultaneous_total_global_hybrid_direct_factor_count"
        ]
        == 0
    )
    assert any(marker.endswith("_bottom_begin") for marker in events)
    assert any(marker.endswith("_top_end") for marker in events)


def test_v3_8_candidate_b_zero_probe_is_excluded_before_action() -> None:
    system, matrix, source = _tiny_side_system()

    class NoApply:
        diagnostics = {}

        def apply(self, *_args):
            raise AssertionError("zero Candidate-B probe must not call the action")

    try:
        report = orchestration._candidate_b_side_probe(
            system,
            NoApply(),
            8,
            {"physical_side_rhs": source},
            {},
        )
        item = report["vectors"]["physical_side_rhs"]
        assert item["status"] == "degenerate_uninformative"
        assert item["informative"] is False
        assert item["rho"] is None
        assert report["rho_summary"]["median"] is None
        assert report["rho_summary"]["worst"] is None
    finally:
        source.destroy()
        matrix.destroy()


def test_v3_8_candidate_b_plan_is_opt_in_and_checkpoint_is_hash_bound(tmp_path) -> None:
    default = watchdog.v3_7_execution_dry_run(
        INPUT,
        tmp_path / "default",
        source_sha="a" * 40,
        python_executable=sys.executable,
    )
    candidate = watchdog.v3_7_execution_dry_run(
        INPUT,
        tmp_path / "candidate",
        source_sha="a" * 40,
        python_executable=sys.executable,
        candidate_b_only=True,
    )
    assert "--candidate-b-only" not in default["argv"]
    assert "--candidate-b-only" in candidate["argv"]
    assert candidate["worker_contract"]["method"] == (
        "hybrid_iterative_candidate_b_only"
    )
    candidate_c = watchdog.v3_7_execution_dry_run(
        INPUT,
        tmp_path / "candidate-c",
        source_sha="a" * 40,
        python_executable=sys.executable,
        candidate_c_only=True,
    )
    assert "--candidate-c-only" in candidate_c["argv"]
    assert candidate_c["worker_contract"]["method"] == (
        "hybrid_iterative_candidate_c1_only"
    )
    candidate_d = watchdog.v3_7_execution_dry_run(
        INPUT,
        tmp_path / "candidate-d",
        source_sha="a" * 40,
        python_executable=sys.executable,
        candidate_d_only=True,
    )
    assert "--candidate-d-only" in candidate_d["argv"]
    assert candidate_d["worker_contract"]["method"] == (
        "USER_AUTHORIZED_EXPERIMENTAL_HYBRIDIZED_DIRECT_SIDE_CANDIDATE_D"
    )
    with pytest.raises(ValueError, match="routes are exclusive"):
        watchdog.v3_7_execution_dry_run(
            INPUT,
            tmp_path / "candidate-bc",
            source_sha="a" * 40,
            python_executable=sys.executable,
            candidate_b_only=True,
            candidate_c_only=True,
        )
    with pytest.raises(ValueError, match="routes are exclusive"):
        watchdog.v3_7_execution_dry_run(
            INPUT,
            tmp_path / "candidate-bd",
            source_sha="a" * 40,
            python_executable=sys.executable,
            candidate_b_only=True,
            candidate_d_only=True,
        )
    payload = load_v3_7_official_payload(INPUT)
    checkpoint_root = tmp_path / "checkpoint"
    checkpoint_root.mkdir()
    resolved_config = checkpoint_root / "resolved_config.json"
    resolved_config.write_text("{}\n", encoding="utf-8")
    producer = {
        "producer_source_sha": "p" * 40,
        "physical_model_sha256": "m" * 64,
        "model_id": "task039-test",
        "requested_modes": 480,
        "mpi_size": 8,
        "external_keys_exact": True,
        "verified_shard_count": 32,
        "inventory": {
            "source_sha": "p" * 40,
            "input_sha256": "i" * 64,
            "resolved_config_sha256": "r" * 64,
            "physical_model_sha256": "m" * 64,
            "verified_shard_count": 32,
            "payload": {"artifact": {"sha256": "d" * 64}},
        },
    }
    report = {
        "status": "measured",
        "pass": False,
        "selected_budget": None,
        "budgets_run": [8, 16, 32],
        "gate": {"median_limit": 0.1, "worst_limit": 0.3},
        "factor_inventory": {"per_budget": []},
        "budget_reports": [],
    }
    path = orchestration._write_v3_8_candidate_b_checkpoint(
        checkpoint_root,
        source_sha="c" * 40,
        resolved_payload=payload,
        producer=producer,
        report=report,
        comm=MPI.COMM_SELF,
    )
    checkpoint = json.loads(path.read_text(encoding="utf-8"))
    assert (
        checkpoint["physical_identity"]["consumer_input_sha256"]
        == payload["provenance"]["input_sha256"]
    )
    assert checkpoint["physical_identity"]["producer_input_sha256"] == "i" * 64
    assert checkpoint["physical_identity"]["direct_payload_sha256"] == "d" * 64
    assert checkpoint["budgets_run"] == [8, 16, 32]

    failure = ValueError("array must not contain infs or NaNs")
    failure.candidate_b_progress = {"budget": 8, "side": "bottom"}
    failure.finite_audit = {
        "stage": "woodbury_apply_lu_solve",
        "vector": "lu_solve_input",
        "finite": False,
    }
    failure_path = orchestration._write_v3_8_candidate_b_failure_checkpoint(
        checkpoint_root,
        source_sha="c" * 40,
        resolved_payload=payload,
        producer=producer,
        error=failure,
        comm=MPI.COMM_SELF,
    )
    failure_checkpoint = json.loads(failure_path.read_text(encoding="utf-8"))
    assert failure_checkpoint["status"] == "candidate_b_implementation_failure"
    assert failure_checkpoint["pass"] is None
    assert failure_checkpoint["budgets_run"] == []
    assert failure_checkpoint["failure"]["attempted_budget"] == 8
    assert failure_checkpoint["failure"]["attempted_side"] == "bottom"
    assert failure_checkpoint["failure"]["finite_audit"]["stage"] == (
        "woodbury_apply_lu_solve"
    )
    assert "rho" in failure_checkpoint["failure"]["unmeasured"]
    failure.candidate_c_progress = {"side": "bottom"}
    c_failure_path = orchestration._write_v3_8_candidate_c_failure_checkpoint(
        checkpoint_root,
        source_sha="c" * 40,
        resolved_payload=payload,
        producer=producer,
        error=failure,
        comm=MPI.COMM_SELF,
    )
    c_failure_checkpoint = json.loads(c_failure_path.read_text(encoding="utf-8"))
    assert c_failure_checkpoint["status"] == "candidate_c1_implementation_failure"
    assert c_failure_checkpoint["pass"] is None
    assert c_failure_checkpoint["failure"]["attempted_side"] == "bottom"


def test_v3_8_candidate_c_side_gate_uses_frozen_limits() -> None:
    passed = {"pass": True, "rho_summary": {"median": 0.05, "worst": 0.2}}
    failed = {"pass": True, "rho_summary": {"median": 0.15, "worst": 0.2}}
    assert orchestration._candidate_c_side_gate(passed) is True
    assert orchestration._candidate_c_side_gate(failed) is False


def test_v3_8_candidate_d_releases_side_components_before_recovery(
    tmp_path, monkeypatch
) -> None:
    payload = load_v3_7_official_payload(INPUT)
    events: list[str] = []

    class Components:
        def __init__(self):
            self.bottom = object()
            self.top = object()
            self._destroyed = False

        @property
        def destroyed(self):
            return self._destroyed

        def destroy(self):
            events.append("components_destroy")
            self._destroyed = True

    components = Components()
    active_components = [components]
    monkeypatch.setattr(
        orchestration,
        "build_research_explicit_side_components",
        lambda *_args: active_components[0],
    )

    def heap_cleanup(_comm):
        events.append("collective_cleanup")
        return {"collective_call_completed": True}

    monkeypatch.setattr(orchestration, "collective_heap_cleanup", heap_cleanup)

    class Vec:
        def duplicate(self):
            events.append("snapshot_duplicate")
            return Vec()

        def copy(self, _destination):
            events.append("snapshot_copy")

        def destroy(self):
            events.append("snapshot_destroy")

    def oracle_runner(*_args, **kwargs):
        assert kwargs["reference"] is None
        assert kwargs["explicit_components"] is active_components[0]
        kwargs["solution_consumer"](Vec(), {})
        events.append("oracle_cleanup")
        return {
            "pass": True,
            "numerical_pass": True,
            "inventory_pass": True,
            "inventory": {
                "bottom_direct_factor_count": 1,
                "top_direct_factor_count": 1,
                "global_hybrid_direct_factor_count": 0,
            },
            "lifecycle": {
                "bottom_action_destroyed": True,
                "top_action_destroyed": True,
                "bottom_direct_factor_count_after_cleanup": 0,
                "top_direct_factor_count_after_cleanup": 0,
                "explicit_components_destroyed_by_oracle": False,
            },
        }

    def recovery_runner(*_args):
        assert components.destroyed is True
        events.append("recovery")
        return {"pass": True, "physics": "measured"}

    run_directory = tmp_path / "candidate-d"
    (run_directory / "numerical_output").mkdir(parents=True)
    (run_directory / "resolved_config.json").write_text("{}\n", encoding="utf-8")
    producer = orchestration._candidate_d_producer_metadata(
        payload, "c" * 40, lambda *_args: None
    )
    report, checkpoint = orchestration._run_v3_8_candidate_d_campaign(
        SimpleNamespace(
            bottom=SimpleNamespace(),
            top=SimpleNamespace(),
            coupling=SimpleNamespace(),
        ),
        SimpleNamespace(),
        None,
        resolved_payload=payload,
        producer=producer,
        run_directory=run_directory,
        source_sha="c" * 40,
        comm=MPI.COMM_SELF,
        marker_callback=lambda *_args: None,
        oracle_runner=oracle_runner,
        recovery_runner=recovery_runner,
    )
    assert report["pass"] is True
    assert events.index("oracle_cleanup") < events.index("components_destroy")
    assert events.index("components_destroy") < events.index("collective_cleanup")
    assert events.index("collective_cleanup") < events.index("recovery")
    assert events.index("recovery") < events.index("snapshot_destroy")
    saved = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert saved["direct_reference_payload_loaded"] is False
    assert saved["exact_side_components_materialized"] is True
    assert saved["release_contract"]["exact_side_cleanup_before_recovery"] is True
    assert (
        saved["release_contract"]["cleanup"]["collective_heap_cleanup"][
            "collective_call_completed"
        ]
        is True
    )

    failed_components = Components()
    active_components[0] = failed_components
    monkeypatch.setattr(
        orchestration,
        "collective_heap_cleanup",
        lambda _comm: {"collective_call_completed": False},
    )
    failed_directory = tmp_path / "candidate-d-cleanup-failure"
    (failed_directory / "numerical_output").mkdir(parents=True)
    (failed_directory / "resolved_config.json").write_text("{}\n", encoding="utf-8")
    recovery_count_before = events.count("recovery")
    with pytest.raises(ValueError, match="exact-side cleanup failed"):
        orchestration._run_v3_8_candidate_d_campaign(
            SimpleNamespace(
                bottom=SimpleNamespace(),
                top=SimpleNamespace(),
                coupling=SimpleNamespace(),
            ),
            SimpleNamespace(),
            None,
            resolved_payload=payload,
            producer=producer,
            run_directory=failed_directory,
            source_sha="c" * 40,
            comm=MPI.COMM_SELF,
            marker_callback=lambda *_args: None,
            oracle_runner=oracle_runner,
            recovery_runner=recovery_runner,
        )
    assert events.count("recovery") == recovery_count_before
    assert not (
        failed_directory / "numerical_output" / "v3_8_candidate_d_checkpoint.json"
    ).exists()


def test_v3_8_candidate_b_branch_skips_v3_7_reference_oracle_recovery(
    tmp_path, monkeypatch
) -> None:
    payload = load_v3_7_official_payload(INPUT)
    called: list[str] = []

    class Layout:
        comm = MPI.COMM_SELF

        @classmethod
        def build(cls, *_args):
            return cls()

    class Rhs:
        def destroy(self):
            called.append("rhs_destroy")

    setup = SimpleNamespace(
        bottom=SimpleNamespace(),
        top=SimpleNamespace(),
        coupling=SimpleNamespace(internal_unknown_count=0),
    )
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    (run_directory / "resolved_config.json").write_text("{}\n", encoding="utf-8")
    checkpoint = run_directory / "numerical_output" / "v3_8_candidate_b_checkpoint.json"

    def campaign(*_args, **kwargs):
        called.append("candidate_b")
        marker_callback = kwargs["marker_callback"]
        marker_callback("candidate_b_side_fixed_setup_end", {})
        for side in ("bottom", "top"):
            marker_callback(f"candidate_b_budget_8_{side}_ready", {})
            marker_callback(f"candidate_b_budget_8_{side}_end", {})
        marker_callback("candidate_b_side_fixed_cleanup_end", {})
        return {"status": "measured", "pass": False}, checkpoint

    monkeypatch.setattr(orchestration, "HybridAugmentedLayout", Layout)
    monkeypatch.setattr(orchestration, "_default_rhs", lambda *_args: Rhs())
    monkeypatch.setattr(
        orchestration, "release_frozen_m10_objects", lambda *_args: None
    )
    monkeypatch.setattr(orchestration, "_run_v3_8_candidate_b_campaign", campaign)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("V3-7 identity/oracle/recovery path was entered")

    result = orchestration.run_task039_v3_7_diagnostic(
        payload,
        run_directory,
        source_sha="a" * 40,
        comm=MPI.COMM_SELF,
        setup_builder=lambda *_args, **_kwargs: setup,
        inventory_loader=lambda *_args, **_kwargs: (
            {
                "producer_source_sha": "p" * 40,
                "physical_model_sha256": "m" * 64,
                "model_id": "task039-test",
                "requested_modes": 480,
                "mpi_size": 8,
                "external_keys_exact": True,
                "inventory": {
                    "source_sha": "p" * 40,
                    "input_sha256": "i" * 64,
                    "resolved_config_sha256": "r" * 64,
                    "physical_model_sha256": "m" * 64,
                    "payload": {"artifact": {"sha256": "d" * 64}},
                },
            },
            np.zeros(960, dtype=np.complex128),
        ),
        reference_builder=forbidden,
        identity_runner=forbidden,
        oracle_runner=forbidden,
        recovery_runner=None,
        candidate_b_only=True,
    )
    assert called == ["candidate_b", "rhs_destroy"]
    assert result["schema"] == "task039.v3-8-candidate-b-only.v1"
    assert result["formal_run"]["oracle"] == "not_run_by_candidate_b_contract"
    ledger = json.loads(
        (run_directory / "numerical_output" / "memory_object_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    assert ledger["objects"]["side_base_ilu"]["created"] is True
    assert ledger["objects"]["side_base_ilu"]["completed"] is True
    assert ledger["objects"]["side_base_ilu"]["destroyed"] is True
    assert ledger["objects"]["correction_wrappers"]["created"] is True
    assert ledger["objects"]["correction_wrappers"]["completed"] is True
    assert ledger["objects"]["correction_wrappers"]["destroyed"] is True


def test_v3_8_candidate_d_branch_skips_direct_reference_and_identity(
    tmp_path, monkeypatch
) -> None:
    payload = load_v3_7_official_payload(INPUT)
    called: list[str] = []

    class Layout:
        comm = MPI.COMM_SELF

        @classmethod
        def build(cls, *_args):
            return cls()

    class Rhs:
        def destroy(self):
            called.append("rhs_destroy")

    setup = SimpleNamespace(
        bottom=SimpleNamespace(),
        top=SimpleNamespace(),
        coupling=SimpleNamespace(internal_unknown_count=0),
    )
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    (run_directory / "resolved_config.json").write_text("{}\n", encoding="utf-8")
    checkpoint = run_directory / "numerical_output" / "v3_8_candidate_d_checkpoint.json"

    def campaign(*_args, **kwargs):
        called.append("candidate_d")
        marker_callback = kwargs["marker_callback"]
        marker_callback("candidate_d_explicit_components_ready", {})
        marker_callback("candidate_d_explicit_components_destroyed", {})
        return {"status": "measured", "pass": False}, checkpoint

    def forbidden(name):
        def fail(*_args, **_kwargs):
            raise AssertionError(f"{name} was called")

        return fail

    monkeypatch.setattr(orchestration, "HybridAugmentedLayout", Layout)
    monkeypatch.setattr(orchestration, "_default_rhs", lambda *_args: Rhs())
    monkeypatch.setattr(
        orchestration, "release_frozen_m10_objects", lambda *_args: None
    )
    monkeypatch.setattr(orchestration, "_run_v3_8_candidate_d_campaign", campaign)

    result = orchestration.run_task039_v3_7_diagnostic(
        payload,
        run_directory,
        source_sha="a" * 40,
        comm=MPI.COMM_SELF,
        setup_builder=lambda *_args, **_kwargs: setup,
        inventory_loader=forbidden("inventory_loader"),
        reference_builder=forbidden("reference_builder"),
        identity_runner=forbidden("identity_runner"),
        oracle_runner=forbidden("oracle_runner"),
        recovery_runner=None,
        candidate_d_only=True,
    )
    assert called == ["candidate_d", "rhs_destroy"]
    assert result["schema"] == "task039.v3-8-candidate-d-only.v1"
    assert result["direct_reference_payload_loaded"] is False
    assert result["candidate_d"]["pass"] is False
    ledger = json.loads(
        (run_directory / "numerical_output" / "memory_object_ledger.json").read_text(
            encoding="utf-8"
        )
    )
    assert ledger["status"] == "completed"
    assert ledger["objects"]["setup"]["destroyed"] is True
    assert ledger["objects"]["candidate_d_explicit_components"]["destroyed"] is True
    assert ledger["objects"]["independent_reference"]["created"] is False


def test_v3_8_candidate_c_normal_return_finalizes_ledger(tmp_path, monkeypatch) -> None:
    payload = load_v3_7_official_payload(INPUT)
    called: list[str] = []

    class Layout:
        comm = MPI.COMM_SELF

        @classmethod
        def build(cls, *_args):
            return cls()

    class Rhs:
        def destroy(self):
            called.append("rhs_destroy")

    setup = SimpleNamespace(
        bottom=SimpleNamespace(),
        top=SimpleNamespace(),
        coupling=SimpleNamespace(internal_unknown_count=0),
    )
    run_directory = tmp_path / "run"
    run_directory.mkdir()
    (run_directory / "resolved_config.json").write_text("{}\n", encoding="utf-8")
    checkpoint = (
        run_directory / "numerical_output" / "v3_8_candidate_c1_checkpoint.json"
    )

    def campaign(*_args, **kwargs):
        called.append("candidate_c")
        marker_callback = kwargs["marker_callback"]
        marker_callback("candidate_c_side_fixed_setup_end", {})
        marker_callback("candidate_c_side_fixed_cleanup_end", {})
        return {"status": "measured", "pass": False}, checkpoint

    monkeypatch.setattr(orchestration, "HybridAugmentedLayout", Layout)
    monkeypatch.setattr(orchestration, "_default_rhs", lambda *_args: Rhs())
    monkeypatch.setattr(
        orchestration, "release_frozen_m10_objects", lambda *_args: None
    )
    monkeypatch.setattr(orchestration, "_run_v3_8_candidate_c_campaign", campaign)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("V3-7 identity/oracle/recovery path was entered")

    result = orchestration.run_task039_v3_7_diagnostic(
        payload,
        run_directory,
        source_sha="a" * 40,
        comm=MPI.COMM_SELF,
        setup_builder=lambda *_args, **_kwargs: setup,
        inventory_loader=lambda *_args, **_kwargs: (
            {
                "producer_source_sha": "p" * 40,
                "physical_model_sha256": "m" * 64,
                "model_id": "task039-test",
                "requested_modes": 480,
                "mpi_size": 8,
                "external_keys_exact": True,
                "inventory": {
                    "source_sha": "p" * 40,
                    "input_sha256": "i" * 64,
                    "resolved_config_sha256": "r" * 64,
                    "physical_model_sha256": "m" * 64,
                    "payload": {"artifact": {"sha256": "d" * 64}},
                },
            },
            np.zeros(960, dtype=np.complex128),
        ),
        reference_builder=forbidden,
        identity_runner=forbidden,
        oracle_runner=forbidden,
        recovery_runner=None,
        candidate_c_only=True,
    )
    assert called == ["candidate_c", "rhs_destroy"]
    assert result["schema"] == "task039.v3-8-candidate-c1-only.v1"
    ledger_ref = result["telemetry"]["memory_object_ledger"]
    assert ledger_ref["path"] == "numerical_output/memory_object_ledger.json"
    assert ledger_ref["schema"] == "task039.v3-7-memory-object-ledger.v1"
    assert ledger_ref["status"] == "completed"
    ledger = json.loads(
        (run_directory / ledger_ref["path"]).read_text(encoding="utf-8")
    )
    assert ledger["objects"]["side_base_ilu"]["destroyed"] is True
    assert ledger["objects"]["correction_wrappers"]["created"] is True
    assert ledger["objects"]["correction_wrappers"]["completed"] is True
    assert ledger["objects"]["correction_wrappers"]["destroyed"] is True


def test_v3_8_candidate_c_cleanup_fields_use_nested_lifecycle() -> None:
    fields = orchestration._candidate_c_cleanup_fields(
        {"destroyed": True},
        {
            "destroyed": True,
            "lifecycle": {"factor_count_after_destroy": 0, "factors_released": True},
        },
    )
    assert fields["fixed_destroyed"] is True
    assert fields["base_destroyed"] is True
    assert fields["base_factor_count_after_destroy"] == 0
    assert fields["base_factors_released"] is True


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


def test_v3_7_side_probe_uses_nonzero_seed_and_preserves_probe_identity() -> None:
    system, matrix, rhs = _tiny_side_system()
    probe = matrix.createVecRight()
    try:
        probe.setValue(0, PETSc.ScalarType(1.0 + 0.5j))
        probe.setValue(1, PETSc.ScalarType(-0.25 + 0.75j))
        probe.assemble()
        before = orchestration._side_vector_identity(probe, "probe")
        residual, metadata = orchestration._short_side_ksp_residual(
            system,
            probe,
            max_it=1,
            source="side_unpreconditioned_gmres_it1",
        )
        try:
            after = orchestration._side_vector_identity(probe, "probe")
            assert before["global_sha256"] == after["global_sha256"]
            assert before["source_norm"] == pytest.approx(after["source_norm"])
            assert metadata["rhs_norm"] > 1.0e-30
            assert metadata["residual_source"] == "explicit_b_minus_Ax"
            assert metadata["explicit_residual_relative"] == pytest.approx(0.0)
        finally:
            residual.destroy()

        vectors, owned, vector_metadata = orchestration._side_survey_vectors(
            system, "bottom", None
        )
        try:
            assert vectors["physical_side_rhs"].norm() == pytest.approx(0.0)
            for label in ("early_krylov_residual_it1", "early_krylov_residual_it3"):
                assert vector_metadata[label]["probe_source"] == (
                    "global_index_seed_739"
                )
                assert vector_metadata[label]["probe_identity"]["source_norm"] > 1.0e-30
                assert vector_metadata[label]["residual_source"] == (
                    "explicit_b_minus_Ax"
                )
        finally:
            for vector in owned:
                vector.destroy()
    finally:
        probe.destroy()
        rhs.destroy()
        matrix.destroy()


def test_v3_7_zero_iteration_side_probe_fails_closed() -> None:
    system, matrix, rhs = _tiny_side_system()
    probe = matrix.createVecRight()
    try:
        probe.setValue(0, PETSc.ScalarType(1.0))
        probe.setValue(1, PETSc.ScalarType(2.0))
        probe.assemble()
        with pytest.raises(RuntimeError, match="no residual iteration"):
            orchestration._short_side_ksp_residual(
                system,
                probe,
                max_it=0,
                source="side_unpreconditioned_gmres_it0",
            )
    finally:
        probe.destroy()
        rhs.destroy()
        matrix.destroy()


def test_v3_7_side_probe_excludes_zero_rhs_from_rho_aggregate() -> None:
    system, matrix, rhs = _tiny_side_system()
    nonzero = matrix.createVecRight()
    try:
        nonzero.setValue(0, PETSc.ScalarType(1.0))
        nonzero.setValue(1, PETSc.ScalarType(-1.0))
        nonzero.assemble()

        class CopyAction:
            def apply(self, source, target) -> None:
                source.copy(target)

        report = orchestration._side_correction_probe(
            system,
            CopyAction(),
            1,
            {"physical_side_rhs": rhs, "seed": nonzero},
            {},
        )
        zero = report["vectors"]["physical_side_rhs"]
        assert zero["rho"] is None
        assert zero["status"] == "degenerate_uninformative"
        assert zero["informative"] is False
        assert report["vector_inventory"]["excluded_count"] == 1
        assert report["vector_inventory"]["informative_count"] == 1
        assert report["rho_summary"]["median"] == pytest.approx(0.0)
        assert report["rho_summary"]["worst"] == pytest.approx(0.0)
    finally:
        nonzero.destroy()
        rhs.destroy()
        matrix.destroy()


def test_v3_7_identity_checkpoint_survives_correction_exception(tmp_path) -> None:
    run_directory = tmp_path / "identity-checkpoint"
    producer = {
        "producer_source_sha": "p" * 40,
        "physical_model_sha256": "m" * 64,
        "model_id": "task039-test",
        "requested_modes": 480,
        "mpi_size": 8,
        "external_keys_exact": True,
    }
    identity = {
        "pass": True,
        "vector_count": 1,
        "vectors": {
            "seed": {
                "relative_error": 2.0e-12,
                "limit": 1.0e-10,
                "blocks": {"bottom": {"relative_error": 1.0e-12, "limit": 1.0e-10}},
            }
        },
        "rhs_equality": {"pass": True},
        "coupling_isolation": {"pass": True},
        "direct_solution_residual": {
            "relative_error": 7.5e-10,
            "denominator": "max(norm(physical_rhs),1e-30)",
        },
    }
    marker_events: list[tuple[str, dict]] = []

    def identity_stage():
        checkpoint = orchestration._write_v3_7_identity_checkpoint(
            run_directory,
            source_sha="c" * 40,
            producer=producer,
            identity=identity,
            comm=MPI.COMM_SELF,
        )
        orchestration._emit_marker(
            lambda marker, detail: marker_events.append((marker, dict(detail))),
            "identity_audit_complete",
            path="numerical_output/v3_7_identity_checkpoint.json",
            **{"pass": True},
        )
        assert checkpoint.is_file()
        return identity

    with pytest.raises(RuntimeError, match="correction sentinel"):
        run_v3_7_stage_sequence(
            identity_stage=identity_stage,
            correction_stage=lambda: (_ for _ in ()).throw(
                RuntimeError("correction sentinel")
            ),
            oracle_stage=lambda _consume: {"pass": False},
        )

    checkpoint = json.loads(
        (
            run_directory / "numerical_output" / "v3_7_identity_checkpoint.json"
        ).read_text(encoding="utf-8")
    )
    assert checkpoint["source_sha"] == "c" * 40
    assert checkpoint["pass"] is True
    assert checkpoint["direct_solution_residual"]["relative_error"] == pytest.approx(
        7.5e-10
    )
    assert marker_events == [
        (
            "identity_audit_complete",
            {
                "path": "numerical_output/v3_7_identity_checkpoint.json",
                "pass": True,
            },
        )
    ]


def test_v3_7_side_survey_checkpoint_survives_oracle_exception(tmp_path) -> None:
    run_directory = tmp_path / "side-checkpoint"
    producer = {
        "producer_source_sha": "p" * 40,
        "consumer_source_sha": "c" * 40,
        "physical_model_sha256": "m" * 64,
        "model_id": "task039-test",
        "requested_modes": 480,
        "mpi_size": 8,
        "external_keys_exact": True,
    }
    passes = []
    for correction_passes in (1, 2, 4, 8):
        passes.append(
            {
                "correction_passes": correction_passes,
                "pass": True,
                "bottom": {
                    "vector_inventory": {
                        "informative_labels": ["seed"],
                        "excluded_labels": ["physical_side_rhs"],
                        "informative_count": 1,
                        "excluded_count": 1,
                    },
                    "rho_summary": {
                        "median": 0.1,
                        "worst": 0.2,
                        "candidate_A_pass": True,
                    },
                },
                "top": {
                    "vector_inventory": {
                        "informative_labels": ["seed"],
                        "excluded_labels": [],
                        "informative_count": 1,
                        "excluded_count": 0,
                    },
                    "rho_summary": {
                        "median": 0.11,
                        "worst": 0.21,
                        "candidate_A_pass": True,
                    },
                },
            }
        )
    correction = {"status": "measured", "pass": True, "passes": passes}
    checkpoint_holder = {}

    def correction_stage():
        checkpoint_holder["path"] = _write_v3_7_side_survey_checkpoint(
            run_directory,
            source_sha="s" * 40,
            producer=producer,
            correction=correction,
            comm=MPI.COMM_SELF,
        )
        return correction

    with pytest.raises(RuntimeError, match="oracle sentinel"):
        run_v3_7_stage_sequence(
            identity_stage=lambda: {"pass": True},
            correction_stage=correction_stage,
            oracle_stage=lambda _consume: (_ for _ in ()).throw(
                RuntimeError("oracle sentinel")
            ),
        )
    checkpoint = checkpoint_holder["path"]
    assert checkpoint.is_file()
    saved = json.loads(checkpoint.read_text(encoding="utf-8"))
    assert saved["source_sha"] == "s" * 40
    assert saved["physical_identity"] == {
        "producer_source_sha": "p" * 40,
        "consumer_source_sha": "c" * 40,
        "physical_model_sha256": "m" * 64,
        "model_id": "task039-test",
        "requested_modes": 480,
        "mpi_size": 8,
        "external_keys_exact": True,
    }
    assert saved["survey_pass"] is True
    assert [item["correction_passes"] for item in saved["passes"]] == [1, 2, 4, 8]
    for item in saved["passes"]:
        assert item["bottom"]["informative_labels"] == ["seed"]
        assert item["bottom"]["excluded_labels"] == ["physical_side_rhs"]
        assert item["bottom"]["median"] == pytest.approx(0.1)
        assert item["bottom"]["worst"] == pytest.approx(0.2)
        assert item["bottom"]["candidate_A_pass"] is True
        assert item["top"]["informative_labels"] == ["seed"]
        assert item["top"]["median"] == pytest.approx(0.11)
        assert item["top"]["worst"] == pytest.approx(0.21)
        assert item["top"]["candidate_A_pass"] is True
