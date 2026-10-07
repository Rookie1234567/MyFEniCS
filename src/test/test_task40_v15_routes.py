from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.io import load_and_resolve


ROOT = Path(__file__).resolve().parents[2]
INPUT_ROOT = ROOT / "input/task40extra_0p7nm_engineering"
CASES = (
    (
        "b0_p6_reference_v15.dat",
        "b0_p6_reference_v13.dat",
        "task40extra_v15_p6_y_orbit_b0_reference_v1",
        "task40extra_0p7nm_b0_p6_reference_v15",
        "B0_CANDIDATE",
        (80, 36000, 532, (76, 152, 152, 152), (228, 304)),
    ),
    (
        "nonseparable_gx560_p6_reference_v15.dat",
        "nonseparable_gx560_p6_reference_v13.dat",
        "task40extra_v15_p6_y_orbit_gx560_reference_v1",
        "task40extra_0p7nm_nonseparable_gx560_p6_reference_v15",
        "Q4_ORIGINAL",
        (560, 252000, 340, (68, 68, 136, 68), (204, 136)),
    ),
    (
        "nonseparable_e1_p6_reference_v15.dat",
        "nonseparable_e1_p6_q4_manual_m2_growth.dat",
        "task40extra_v15_p6_y_orbit_e1_reference_v1",
        "task40extra_0p7nm_nonseparable_e1_p6_reference_v15",
        "Q4_ORIGINAL",
        (760, 342000, 588, (84, 168, 168, 168), (252, 336)),
    ),
)


class _FakePETScVector:
    def __init__(self, values=None):
        self.array_r = np.asarray(
            np.empty(0, dtype=np.complex128) if values is None else values,
            dtype=np.complex128,
        ).copy()

    def createSeq(self, rows, *, comm):
        del comm
        self.array_r = np.zeros(int(rows), dtype=np.complex128)
        return self

    def duplicate(self):
        return _FakePETScVector(np.zeros_like(self.array_r))

    def set(self, value):
        self.array_r.fill(value)

    def getArray(self, *, readonly=False):
        del readonly
        return self.array_r

    def destroy(self):
        pass


def _make_v15_pc_fixture(monkeypatch, *, first_call_needs_correction):
    from src.runners import task40_v10_worker
    from src.solvers.augmented_reference_correction import (
        NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
        evaluate_v15_non_cancelling_budget,
    )

    q_rows = [
        {
            "q": q,
            "rhs_norm": 1.0,
            "true_residual_norm": 0.0,
            "true_residual_relative": 0.0,
        }
        for q in range(4)
    ]

    class FakeInverse:
        def __init__(self):
            self.factors = SimpleNamespace(calls=0)
            self.last_solve_audit = []
            self.reference_pc_strategy = NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15
            self.q_solve_limit = 1.0e-8
            self.solve_count = 0

        def apply_augmented(self, fe_rhs, *, port_rhs):
            self.solve_count += 1
            self.factors.calls += 4
            self.last_solve_audit = [{"q_true_residuals": list(q_rows)}]
            if self.solve_count in (1, 3):
                return (
                    np.asarray([0.25 + 0.1j, 0.5 - 0.2j], dtype=np.complex128),
                    np.asarray([0.3 + 0.2j, -0.1 + 0.4j], dtype=np.complex128),
                )
            return (
                np.asarray(fe_rhs, dtype=np.complex128).copy(),
                np.asarray(port_rhs, dtype=np.complex128).copy(),
            )

    inverse = FakeInverse()
    owner = {"regular_inverse_checks": {"passed": True}}
    pc = object.__new__(task40_v10_worker._P6ReferencePreconditioner)
    pc.owner = owner
    pc.reference = {}
    pc.layout = SimpleNamespace(full_rows=2, independent=np.asarray([0, 1], dtype=np.int64))
    pc.profile = SimpleNamespace(
        name="task40extra_v15_fixture_profile", q_count=4, mode_count=2
    )
    pc.inverse = inverse
    pc.PETSc = SimpleNamespace(Vec=_FakePETScVector, COMM_SELF="self")
    pc.target_condensed = SimpleNamespace(
        full_rows=2,
        active_rows=1,
        appended_rows=2,
        trace_constraints=SimpleNamespace(
            owned_active_original_dofs=(0,), original_to_active={0: 0}
        ),
    )
    pc.target_action = SimpleNamespace(
        reduced_size=3,
        condensed=pc.target_condensed,
        inject_trace_port=lambda _values: np.asarray([1.0, 0.0], dtype=np.complex128),
    )
    pc.reference_row = {0: 0, 1: 1}
    pc.independent = np.asarray([0, 1], dtype=np.int64)
    pc.allocation_gate = lambda *_args, **_kwargs: None
    pc.runtime = SimpleNamespace(
        markers=[], samples=[],
        marker=lambda name, facts: pc.runtime.markers.append((name, facts)),
        sample=lambda label: pc.runtime.samples.append(label),
    )
    pc.calls = 0
    pc._v15_native_evaluation_count = 0
    pc._v15_first_packet = None
    pc._v15_last_state_arrays = None
    pc.last_facts = {}
    pc._save_v15_pc_packet = lambda label, *_args, **_kwargs: {"label": label}

    def evaluate_complete(
        finite_element, port_amplitudes, fe_rhs, port_rhs, *, label, **_kwargs
    ):
        needs_correction = (
            first_call_needs_correction and label == "initial_pc_1"
        )
        residual = np.asarray(
            [1.0e-9, 0.0] if needs_correction else [0.0, 0.0],
            dtype=np.complex128,
        )
        return {
            "physical_action_storage": np.asarray(fe_rhs, dtype=np.complex128) - residual,
            "finite_element_residual": residual,
            "port_residual": np.zeros_like(port_rhs, dtype=np.complex128),
            "alpha_closure_residual_norm": 0.0,
            "alpha_closure_raw_scale": 1.0,
            "augmented_residual_norm": float(np.linalg.norm(residual)),
            "augmented_rhs_norm": 1.0,
        }

    pc._evaluate_complete_augmented_state = evaluate_complete

    budget_calls = 0
    epsilon = 1.0e-9
    delta = 1.0e-7

    def native_budget(
        _reference,
        _template,
        fe_rhs,
        _port_rhs,
        _alpha,
        _solution_values,
        global_action_storage,
        complete_fe,
        _petsc,
        *,
        allocation_gate,
        retain_lifted_errors,
        retained_candidate_state_count,
    ):
        nonlocal budget_calls
        budget_calls += 1
        use_bad_budget = first_call_needs_correction and budget_calls == 1
        effective = np.asarray(fe_rhs, dtype=np.complex128)
        zero = np.zeros(2, dtype=np.complex128)
        lift_to_first_row = lambda values: np.asarray([values[0], 0.0j], dtype=np.complex128)
        if use_bad_budget:
            sectors = (
                {
                    "rhs": np.asarray([0.5 + 0.0j]),
                    "action": np.asarray([0.5 - delta + 0.0j]),
                    "lift_dual": lift_to_first_row,
                },
                {
                    "rhs": np.asarray([0.5 + 0.0j]),
                    "action": np.asarray([0.5 + delta - epsilon + 0.0j]),
                    "lift_dual": lift_to_first_row,
                },
            )
        else:
            sectors = (
                {
                    "rhs": np.asarray([0.5 + 0.0j]),
                    "action": np.asarray([0.5 + 0.0j]),
                    "lift_dual": lift_to_first_row,
                },
                {
                    "rhs": np.asarray([0.5 + 0.0j]),
                    "action": np.asarray([0.5 + 0.0j]),
                    "lift_dual": lift_to_first_row,
                },
            )
        budget = evaluate_v15_non_cancelling_budget(
            effective_rhs=effective,
            global_eliminated_action=np.asarray(
                global_action_storage, dtype=np.complex128
            ),
            original_fe_rhs=effective,
            port_elimination_action=zero,
            complete_augmented_fe_residual=np.asarray(
                complete_fe, dtype=np.complex128
            ),
            modal_alpha_defect_action=zero,
            sectors=sectors,
            retain_lifted_errors=retain_lifted_errors,
        )
        budget["sector_facts"] = [
            {"twist_index": 0, "mode_indices": [0]},
            {"twist_index": 1, "mode_indices": [1]},
        ]
        budget["all_modes_covered_once"] = True
        return budget

    monkeypatch.setattr(task40_v10_worker, "_v15_native_budget_facts", native_budget)
    return pc, _FakePETScVector(np.zeros(3, dtype=np.complex128)), inverse


@pytest.mark.parametrize(
    ("filename", "physical_filename", "profile_name", "run_id", "stage", "expected"),
    CASES,
)
def test_v15_input_profile_and_physical_identity_are_bound(
    filename, physical_filename, profile_name, run_id, stage, expected
):
    selected = load_and_resolve(INPUT_ROOT / filename).as_jsonable()
    physical = load_and_resolve(INPUT_ROOT / physical_filename).as_jsonable()
    profile = selected["derived"]["physical_intermediate_profile"]
    from src.solvers.task40_v10_p6_periodic_profile import TASK40_P6_PERIODIC_PROFILES

    periodic = TASK40_P6_PERIODIC_PROFILES[profile_name]
    cells, interiors, modes, q_ports, sector_ports = expected

    assert selected["run_id"] == run_id
    assert selected["solver"]["stage"] == stage
    assert selected["solver"]["preconditioner"] == profile_name
    assert selected["solver"]["task40_reference_pc_strategy"] == (
        "NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15"
    )
    assert selected["solver"]["task40_q_assembly_strategy"] == "LEGACY_GLOBAL_CSR_SUM"
    assert selected["execution"]["memory_limit_gb"] == 16.0
    assert selected["execution"]["warning_memory_gib"] == 14.0
    assert selected["execution"]["terminate_memory_gib"] == 16.0
    assert selected["execution"]["timeout_seconds"] == 86400
    assert selected["execution"]["require_zero_swap"] is True
    for section in ("geometry", "materials", "incidence", "boundary"):
        assert selected[section] == physical[section]

    assert periodic.global_cell_count == cells
    assert periodic.global_interior_rows == interiors
    assert periodic.mode_count == modes == sum(q_ports)
    assert periodic.q_port_counts == q_ports
    assert periodic.sector_port_counts == sector_ports
    assert profile["identity"] == profile_name
    assert profile["gates"]["global_cells"] == cells
    assert profile["gates"]["global_interior_rows"] == interiors
    assert profile["gates"]["all_original_modes_retained"] == modes
    assert profile["gates"]["all_original_modes_covered"] is True
    assert profile["stage"] == stage
    assert profile["run_id"] == run_id

    runtime_inventory = {
        "degree": periodic.degree,
        "global_cell_count": periodic.global_cell_count,
        "global_storage_rows": periodic.global_storage_rows,
        "global_independent_rows": periodic.global_independent_rows,
        "global_interior_rows": periodic.global_interior_rows,
        "global_trace_rows": periodic.global_trace_rows,
        "q_count": periodic.q_count,
        "rows_per_q": periodic.rows_per_q,
        "trace_rows_per_q": periodic.trace_rows_per_q,
        "local_cell_count": periodic.local_cell_count,
        "local_storage_rows": periodic.local_storage_rows,
        "local_independent_rows": periodic.local_independent_rows,
        "local_interior_rows": periodic.local_interior_rows,
        "local_trace_rows": periodic.local_trace_rows,
        "local_width_per_q": periodic.local_width_per_q,
        **{f"q_port_count_{q}": count for q, count in enumerate(q_ports)},
    }
    assert periodic.validate_runtime_inventory(runtime_inventory)["status"] == (
        "RUNTIME_INVENTORY_MATCH"
    )


@pytest.mark.parametrize(
    ("filename", "physical_filename", "profile_name", "run_id", "stage", "_expected"),
    CASES,
)
def test_v15_worker_contract_accepts_only_exact_case_route(
    filename, physical_filename, profile_name, run_id, stage, _expected
):
    del physical_filename, run_id
    from src.io.physical_intermediate_profile import profile_facts
    from src.runners import task40_v10_worker
    from src.runners.physical_v14_budget import V14_TIME_POLICY_ENFORCE

    payload = load_and_resolve(INPUT_ROOT / filename).as_jsonable()
    window_sha = "a" * 64
    runtime = SimpleNamespace(
        stage=stage,
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

    result = task40_v10_worker._candidate_contract(
        payload,
        profile_facts(profile_name),
        runtime,
        profile_identity=profile_name,
    )
    assert result["schema"] == "task40extra.review_v15_p6_reference_worker_contract.v1"
    assert all(result["checks"].values())


@pytest.mark.parametrize(
    ("filename", "physical_filename", "profile_name", "run_id", "stage", "_expected"),
    CASES,
)
def test_v15_dispatcher_calls_worker_with_registered_profile(
    monkeypatch, tmp_path: Path, filename, physical_filename, profile_name, run_id, stage, _expected
):
    from src.runners import task038_full3d_iterative, task40_v10_worker

    del physical_filename, run_id, stage
    payload = load_and_resolve(INPUT_ROOT / filename).as_jsonable()
    captured = {}

    def fake_worker(resolved, run_directory, **kwargs):
        captured["run_id"] = resolved["run_id"]
        captured["profile_identity"] = kwargs["profile_identity"]
        captured["q_assembly_strategy"] = resolved["solver"][
            "task40_q_assembly_strategy"
        ]
        return {"status": "dispatch_fixture_pass"}

    monkeypatch.setattr(
        task40_v10_worker, "run_task40_v10_p6_reference_worker", fake_worker
    )
    result = task038_full3d_iterative.run_full3d_iterative(
        payload, tmp_path, source_sha="f" * 40
    )
    assert result == {"status": "dispatch_fixture_pass"}
    assert captured == {
        "run_id": payload["run_id"],
        "profile_identity": profile_name,
        "q_assembly_strategy": "LEGACY_GLOBAL_CSR_SUM",
    }


def test_v15_dispatcher_rejects_unknown_run_id_before_worker(monkeypatch, tmp_path: Path):
    from src.runners import task038_full3d_iterative, task40_v10_worker

    payload = load_and_resolve(INPUT_ROOT / CASES[2][0]).as_jsonable()
    payload["run_id"] = "task40extra_0p7nm_nonseparable_unknown"
    monkeypatch.setattr(
        task40_v10_worker,
        "run_task40_v10_p6_reference_worker",
        lambda *_args, **_kwargs: pytest.fail("unknown case reached worker"),
    )
    with pytest.raises(ValueError, match="exact registered case identity"):
        task038_full3d_iterative.run_full3d_iterative(
            payload, tmp_path, source_sha="f" * 40
        )


@pytest.mark.parametrize("case", CASES)
def test_run_case_validate_only_accepts_v15_case_without_spending_campaign_time(case, capsys):
    from scripts import run_case

    filename, _physical, _profile, run_id, _stage, _expected = case
    result = run_case.main(
        [
            str(INPUT_ROOT / filename),
            "--validate-only",
        ]
    )
    captured = capsys.readouterr()
    assert result == 0, captured.err or captured.out
    assert __import__("json").loads(captured.out)["run_id"] == run_id


def test_v15_strategy_keeps_only_legacy_q_assembly():
    from src.geometry.task40_nonseparable_plan import (
        TASK40_Q_ASSEMBLY_LEGACY,
        TASK40_Q_ASSEMBLY_PREALLOCATED_V13,
        TASK40_V15_REFERENCE_PC_STRATEGY,
        task40_q_assembly_strategy_is_allowed,
    )

    assert task40_q_assembly_strategy_is_allowed(
        TASK40_V15_REFERENCE_PC_STRATEGY, TASK40_Q_ASSEMBLY_LEGACY
    )
    assert not task40_q_assembly_strategy_is_allowed(
        TASK40_V15_REFERENCE_PC_STRATEGY, TASK40_Q_ASSEMBLY_PREALLOCATED_V13
    )


def test_v15_budget_gate_does_not_count_resident_candidate_twice():
    from src.runners.task40_v10_worker import _v15_native_budget_allocation_facts

    common = {
        "full_rows": 100,
        "independent_rows": 80,
        "mode_count": 12,
        "max_local_rows": 60,
        "max_local_independent": 48,
    }
    no_prior_candidate = _v15_native_budget_allocation_facts(
        **common, retained_candidate_state_count=0
    )
    one_live_candidate = _v15_native_budget_allocation_facts(
        **common, retained_candidate_state_count=1
    )
    packet_candidate = _v15_native_budget_allocation_facts(
        **common,
        retained_candidate_state_count=1,
        retain_lifted_errors=True,
    )
    assert one_live_candidate["additional_payload_bytes"] == (
        no_prior_candidate["additional_payload_bytes"]
    )
    assert one_live_candidate["resident_candidate_state_bytes"] == 16 * (
        8 * common["independent_rows"] + 3 * common["mode_count"]
    )
    assert one_live_candidate["resident_candidate_state_not_added_to_projected_allocation"]
    assert one_live_candidate["additional_payload_bytes"] == sum(
        one_live_candidate[key]
        for key in (
            "additional_array_copy_bytes",
            "additional_compressed_temporary_bytes",
            "additional_other_native_budget_array_bytes",
        )
    )
    assert packet_candidate["additional_retained_residual_evidence_bytes"] == 16 * (
        6 * common["independent_rows"] + 2 * common["max_local_independent"]
    )
    assert packet_candidate["additional_payload_bytes"] > one_live_candidate[
        "additional_payload_bytes"
    ]
    assert one_live_candidate["workspace_bytes"] == 16 * (
        2 * common["full_rows"] + 2 * common["max_local_rows"]
    )


def test_v15_pc_native_budget_receives_full_owner_and_uses_startup_checks(monkeypatch):
    from src.runners import task40_v10_worker

    class FakeVector:
        def createSeq(self, _rows, *, comm):
            assert comm == "self"
            return self

        def destroy(self):
            pass

    owner = {"regular_inverse_checks": {"passed": True}}
    pc = object.__new__(task40_v10_worker._P6ReferencePreconditioner)
    pc.owner = owner
    pc.layout = SimpleNamespace(full_rows=2)
    pc.profile = SimpleNamespace(q_count=4, mode_count=2)
    pc.PETSc = SimpleNamespace(Vec=FakeVector, COMM_SELF="self")
    pc.allocation_gate = lambda *_args, **_kwargs: None
    pc._evaluate_complete_augmented_state = lambda *_args, **_kwargs: {
        "physical_action_storage": np.zeros(2, dtype=np.complex128),
        "finite_element_residual": np.zeros(1, dtype=np.complex128),
        "alpha_closure_residual_norm": 0.0,
        "alpha_closure_raw_scale": 1.0,
    }
    seen = []

    def budget(reference, *_args, **_kwargs):
        assert reference is owner
        seen.append(reference)
        return {
            "effective_rhs_scale": 1.0,
            "eliminated_fe_residual_norm": 0.0,
            "eliminated_fe_relative": 0.0,
            "complete_augmented_fe_residual_norm": 0.0,
            "complete_augmented_fe_relative": 0.0,
            "noncancelling_budget_relative": 0.0,
            "budget_numerator": 0.0,
            "budget_terms": {
                "d_b": 0.0,
                "lifted_sector_errors": [0.0, 0.0],
                "d_A": 0.0,
                "B_delta_alpha": 0.0,
            },
            "decomposition_closure_relative": 0.0,
            "decomposition_closure_norm": 0.0,
            "decomposition_closure_scale": 1.0,
            "effective_rhs_identity_error_norm": 0.0,
            "sector_facts": [
                {"twist_index": 0, "mode_indices": [0]},
                {"twist_index": 1, "mode_indices": [1]},
            ],
            "all_modes_covered_once": True,
        }

    monkeypatch.setattr(task40_v10_worker, "_v15_native_budget_facts", budget)
    q_rows = [
        {
            "q": q,
            "rhs_norm": 1.0,
            "true_residual_norm": 0.0,
            "true_residual_relative": 0.0,
        }
        for q in range(4)
    ]
    evaluated = pc._evaluate_v15_state(
        np.zeros(1, dtype=np.complex128),
        np.zeros(2, dtype=np.complex128),
        np.zeros(1, dtype=np.complex128),
        np.zeros(2, dtype=np.complex128),
        q_rows,
        label="fixture",
    )
    assert seen == [owner]
    assert evaluated["selection"]["admitted"] is True


def test_v15_native_budget_uses_original_h_local_g_over_sqrt_two_and_signed_b_delta():
    from src.runners.task40_v10_worker import _v15_native_budget_facts

    class ModalAction:
        def __init__(self, entries=(), scale=1.0):
            self.carrier = SimpleNamespace(entries=entries)
            self.calls = []
            self.scale = scale

        def recover_auxiliary(self, _solution):
            return np.asarray([1.0, 2.0], dtype=np.complex128)

        def apply_modal_rhs(self, values, vector):
            values = np.asarray(values, dtype=np.complex128)
            self.calls.append(values.copy())
            vector.array_r[:] = values * self.scale

    global_action = ModalAction(
        [SimpleNamespace(normalization_h=2.0), SimpleNamespace(normalization_h=4.0)]
    )
    local_actions = [ModalAction(scale=1.0 / np.sqrt(2.0)) for _ in range(2)]
    local_effective_rhs = np.asarray([17.0, 28.0], dtype=np.complex128)
    sectors = []
    local_action_vectors = {}
    for twist in (0, 1):
        mode = twist
        local_independent = np.asarray([0], dtype=np.int64)

        def fold_dual(rhs, *, selected=twist):
            return np.asarray([rhs[selected]], dtype=np.complex128)

        def lift_dual(values, *, selected=twist):
            lifted = np.zeros(2, dtype=np.complex128)
            lifted[selected] = values[0]
            return lifted

        sectors.append(
            {
                "context": SimpleNamespace(
                    twist_index=twist,
                    original_mode_indices=np.asarray([mode], dtype=np.int64),
                ),
                "transport": SimpleNamespace(
                    local=SimpleNamespace(independent=local_independent),
                    fold_dual=fold_dual,
                    lift_dual=lift_dual,
                ),
                "entities": SimpleNamespace(
                    full_rows=1, independent=np.asarray([0], dtype=np.int64)
                ),
                "bundle": {"dtn_action": local_actions[twist]},
            }
        )
        local_action_vectors[twist] = {
            "independent": np.asarray([local_effective_rhs[twist]], dtype=np.complex128)
        }

    reference = {
        "full_layout": SimpleNamespace(
            independent=np.asarray([0, 1], dtype=np.int64), full_rows=2
        ),
        "profile": SimpleNamespace(mode_count=2),
        "global_bundle": {"dtn_action": global_action},
        "sectors": sectors,
    }
    captured_allocation = []
    result = _v15_native_budget_facts(
        reference,
        _FakePETScVector(np.zeros(2, dtype=np.complex128)),
        np.asarray([20.0, 30.0], dtype=np.complex128),
        np.asarray([6.0, 8.0], dtype=np.complex128),
        np.asarray([5.0, 5.0], dtype=np.complex128),
        np.zeros(2, dtype=np.complex128),
        local_effective_rhs,
        np.asarray([-1.0, -1.0], dtype=np.complex128),
        SimpleNamespace(Vec=_FakePETScVector, COMM_SELF="self"),
        allocation_gate=lambda _label, facts: captured_allocation.append(facts),
        full_solution_vector=_FakePETScVector(np.zeros(2, dtype=np.complex128)),
        sector_action_data=(
            None,
            local_action_vectors,
            {"all_modes_covered_once": True},
        ),
    )

    np.testing.assert_array_equal(global_action.calls[0], [3.0, 2.0])
    np.testing.assert_array_equal(global_action.calls[1], [1.0, 1.0])
    np.testing.assert_allclose(local_actions[0].calls[0], [6.0 / np.sqrt(2.0)])
    np.testing.assert_allclose(local_actions[1].calls[0], [8.0 / (2.0 * np.sqrt(2.0))])
    np.testing.assert_allclose(result["port_elimination_action"], [3.0, 2.0])
    np.testing.assert_allclose(result["effective_rhs"], [17.0, 28.0])
    np.testing.assert_allclose(result["modal_alpha_defect_action"], [1.0, 1.0])
    assert result["budget_terms"]["B_delta_alpha"] == pytest.approx(np.sqrt(2.0))
    assert result["decomposition_closure_relative"] < 1e-14
    assert captured_allocation[0]["uses_original_global_H"] is True
    assert captured_allocation[0]["uses_sector_H_equal_global_H_over_two"] is True
    assert captured_allocation[0]["uses_actual_primal_extract_and_dual_lift"] is True


def test_v15_apply_initial_pass_returns_one_whole_state_without_correction(monkeypatch):
    from src.solvers.augmented_reference_correction import (
        NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
        recheck_reference_pc_final_admission,
    )

    pc, source, inverse = _make_v15_pc_fixture(
        monkeypatch, first_call_needs_correction=False
    )
    expected_fe = np.asarray([0.25 + 0.1j, 0.5 - 0.2j], dtype=np.complex128)
    expected_alpha = np.asarray([0.3 + 0.2j, -0.1 + 0.4j], dtype=np.complex128)

    result = pc.apply(source)

    np.testing.assert_array_equal(result.array_r, np.concatenate(([expected_fe[0]], expected_alpha)))
    assert pc.calls == 1
    assert inverse.solve_count == 1
    assert pc.last_facts["initial_candidate_passed"] is True
    assert pc.last_facts["correction_factor_calls"] is None
    assert pc.last_facts["selected_candidate_index"] == 0
    parent = recheck_reference_pc_final_admission(
        pc.last_facts, NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15
    )
    assert parent["passed"] is True
    assert parent["selection_recomputed_from_candidate_metrics"] is True


def test_v15_apply_corrects_once_then_next_pc_invocation_continues(monkeypatch):
    from src.solvers.augmented_reference_correction import (
        NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
        recheck_reference_pc_final_admission,
    )

    pc, source, inverse = _make_v15_pc_fixture(
        monkeypatch, first_call_needs_correction=True
    )
    initial_fe = np.asarray([0.25 + 0.1j, 0.5 - 0.2j], dtype=np.complex128)
    initial_alpha = np.asarray([0.3 + 0.2j, -0.1 + 0.4j], dtype=np.complex128)

    corrected_output = pc.apply(source)

    np.testing.assert_array_equal(
        corrected_output.array_r,
        np.concatenate(([initial_fe[0] + 1.0e-9], initial_alpha)),
    )
    assert pc.calls == 1
    assert inverse.solve_count == 2
    assert pc.last_facts["initial_candidate_passed"] is False
    assert pc.last_facts["selected_candidate_index"] == 1
    assert pc.last_facts["correction_factor_calls"]["delta"] == 4
    assert len(pc.last_facts["candidate_metrics"]) == 2
    parent_after_correction = recheck_reference_pc_final_admission(
        pc.last_facts, NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15
    )
    assert parent_after_correction["passed"] is True
    assert parent_after_correction["selected_candidate_index"] == 1

    continued_output = pc.apply(corrected_output)

    np.testing.assert_array_equal(
        continued_output.array_r,
        np.concatenate(([initial_fe[0]], initial_alpha)),
    )
    assert pc.calls == 2
    assert inverse.solve_count == 3
    assert pc.last_facts["call"] == 2
    assert pc.last_facts["initial_candidate_passed"] is True
    assert pc.last_facts["correction_factor_calls"] is None
    parent_after_next_pc = recheck_reference_pc_final_admission(
        pc.last_facts, NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15
    )
    assert parent_after_next_pc["passed"] is True


def test_v15_csr_preflight_rejects_bad_bounds_before_pet_sc_integer_cast():
    from src.solvers.augmented_reference_correction import (
        NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15,
    )
    from src.solvers.task40_v10_p6_mumps import (
        _factor_probe_residual_limit,
        _petsc_csr_int_preflight,
    )

    facts = _petsc_csr_int_preflight(
        (2, 3),
        2,
        np.asarray([0, 1, 2], dtype=np.int64),
        np.asarray([0, 2], dtype=np.int64),
        np.int32,
    )
    assert facts["rows"] == 2 and facts["columns"] == 3 and facts["nnz"] == 2
    with pytest.raises(ValueError, match="monotone"):
        _petsc_csr_int_preflight(
            (3, 3),
            2,
            np.asarray([0, 2, 1, 2], dtype=np.int64),
            np.asarray([0, 2], dtype=np.int64),
            np.int32,
        )
    with pytest.raises(ValueError, match="outside"):
        _petsc_csr_int_preflight(
            (2, 3),
            1,
            np.asarray([0, 1, 1], dtype=np.int64),
            np.asarray([3], dtype=np.int64),
            np.int32,
        )
    with pytest.raises(OverflowError, match="PetscInt range"):
        _petsc_csr_int_preflight(
            (2**31, 1),
            0,
            np.asarray([0], dtype=np.int64),
            np.asarray([], dtype=np.int64),
            np.int32,
        )
    assert _factor_probe_residual_limit(
        NATIVE_AUGMENTED_RESIDUAL_QUALIFIED_V15, 1.0e-8
    ) == 1.0e-10


def test_v15_fixed_campaign_runtime_accepts_registered_profiles_only(
    tmp_path, monkeypatch
):
    from src.geometry.task40_nonseparable_plan import TASK40_V15_REFERENCE_PC_STRATEGY
    from src.io.physical_intermediate_profile import (
        TASK40_V15_P6_B0_PROFILE,
        TASK40_V15_P6_E1_PROFILE,
        TASK40_V15_P6_GX560_PROFILE,
        profile_facts,
    )
    from src.runners.physical_p4_schur_v14 import _V14Runtime
    from src.runners.task40_v10_campaign import (
        CAMPAIGN_ACCOUNTING_NAME,
        load_fixed_campaign_window,
        read_campaign_state,
    )

    window_path = (
        ROOT
        / "benchmarks/artifacts/task40extra_0p7nm_engineering/local_w13_wsl/campaign_window_v13.json"
    )
    if not window_path.is_file():
        pytest.skip("the active fixed Task40 campaign window is unavailable")
    window = load_fixed_campaign_window(window_path)
    accounting_path = window.path.parent / CAMPAIGN_ACCOUNTING_NAME
    if not accounting_path.is_file():
        pytest.skip("the active fixed Task40 campaign accounting ledger is unavailable")
    campaign_state = read_campaign_state(window, accounting_path)
    if campaign_state["remaining_numerical_seconds"] <= 0.0:
        pytest.skip("the fixed Task40 campaign window has reached its closeout reserve")

    monkeypatch.setenv("TASK40_V10_CAMPAIGN_WINDOW", str(window.path))
    monkeypatch.setenv("TASK40_V10_CAMPAIGN_WINDOW_SHA256", window.sha256)
    monkeypatch.setenv("TASK40_V10_CAMPAIGN_ACCOUNTING", str(accounting_path))
    expected = {
        TASK40_V15_P6_B0_PROFILE: (
            "B0_CANDIDATE",
            "review_v15_b0_full_p6_y_orbit_reference_inverse",
        ),
        TASK40_V15_P6_GX560_PROFILE: (
            "Q4_ORIGINAL",
            "review_v15_gx560_full_p6_y_orbit_reference_inverse",
        ),
        TASK40_V15_P6_E1_PROFILE: (
            "Q4_ORIGINAL",
            "review_v15_e1_full_p6_y_orbit_reference_inverse",
        ),
    }
    for index, profile in enumerate(expected):
        contract = profile_facts(profile)
        assert (contract["stage"], contract["scope"]) == expected[profile]
        assert contract["reference_pc_strategy"] == TASK40_V15_REFERENCE_PC_STRATEGY
        monkeypatch.setenv(
            "PHYSICAL_WATCHDOG_MEMORY_POLICY",
            contract["resources"]["watchdog_memory_policy"],
        )
        monkeypatch.setenv(
            "PHYSICAL_WATCHDOG_PSS_POLICY",
            contract["resources"]["pss_sampling_policy"],
        )
        monkeypatch.setenv(
            "PHYSICAL_WATCHDOG_PHASE_PATH",
            str(tmp_path / f"accepted_{index}_phase.json"),
        )
        run_directory = tmp_path / f"accepted_{index}"
        run_directory.mkdir()
        runtime = _V14Runtime(
            run_directory,
            contract["stage"],
            contract,
            root=ROOT,
            source_sha="a" * 40,
            batch_identity=f"v15_runtime_no_fe_{index}",
            evidence_prefix=f"v15_runtime_no_fe_{index}",
            require_zero_swap=True,
        )
        assert runtime.campaign_context["window_sha256"] == window.sha256
        assert runtime.campaign_context["read_only"] is True
        assert runtime.workflow_reserved_seconds > 0.0
        assert runtime.shared_budget["writer_while_worker_active"] == (
            "subreaper_watchdog_only"
        )

    rejected = profile_facts(TASK40_V15_P6_B0_PROFILE)
    rejected["scope"] = f"{rejected['scope']}_unregistered"
    monkeypatch.setenv(
        "PHYSICAL_WATCHDOG_MEMORY_POLICY",
        rejected["resources"]["watchdog_memory_policy"],
    )
    monkeypatch.setenv(
        "PHYSICAL_WATCHDOG_PSS_POLICY",
        rejected["resources"]["pss_sampling_policy"],
    )
    monkeypatch.setenv(
        "PHYSICAL_WATCHDOG_PHASE_PATH", str(tmp_path / "rejected_phase.json")
    )
    with pytest.raises(RuntimeError, match="rejected this exact stage/profile/scope"):
        _V14Runtime(
            tmp_path / "rejected",
            rejected["stage"],
            rejected,
            root=ROOT,
            source_sha="a" * 40,
            batch_identity="v15_runtime_unregistered_scope",
            evidence_prefix="v15_runtime_unregistered_scope",
            require_zero_swap=True,
        )
    assert not (tmp_path / "rejected" / "v15_runtime_unregistered_scope_inventory.json").exists()
