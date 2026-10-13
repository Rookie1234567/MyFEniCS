from __future__ import annotations

import json
import hashlib

import numpy as np
import pytest

from src.io.v7_balanced_diagnostic_contract import (
    V7_DIAGNOSTIC_ENV,
    V7_PROFILE,
    diagnostic_requested,
    launch_contract,
    validate_worker_binding,
)
from src.solvers.fullspace_physical_intermediate import apply_owned
from src.solvers.physical_balanced_coupling import (
    BalancedConstraintRejected,
    PhysicalBalancedCoupling,
)
from src.solvers.v7_balanced_failure_diagnostic import (
    V7BalancedFailureDiagnostic,
    with_shared_dtn_owner,
)


class FakeVec:
    def __init__(self, values):
        self.array = np.ascontiguousarray(values, dtype=np.complex128)
        self.destroy_count = 0

    def duplicate(self):
        return FakeVec(np.zeros_like(self.array))

    def copy(self, target):
        target.array[:] = self.array

    def set(self, value):
        self.array.fill(value)

    def getArray(self, readonly=False):
        return self.array

    def getSize(self):
        return self.array.size

    def getLocalSize(self):
        return self.array.size

    def norm(self):
        return float(np.linalg.norm(self.array))

    def axpy(self, alpha, other):
        self.array[:] += alpha * other.array

    def destroy(self):
        self.destroy_count += 1
        if self.destroy_count > 1:
            raise AssertionError("fake Vec destroyed more than once")


class MatrixAction:
    def __init__(self, matrix, seen=None):
        self.matrix = np.asarray(matrix, dtype=np.complex128)
        self.seen = seen

    def apply_into(self, source, target):
        if self.seen is not None:
            self.seen.append(source)
        target.array[:] = self.matrix @ source.array


class BorrowedVolume:
    def __init__(self, matrix):
        self.matrix = np.asarray(matrix, dtype=np.complex128)
        self.outputs = []

    def apply(self, source):
        # Deliberately returns a caller-borrowed Vec, as the production volume
        # action does; the adapter must copy it but never destroy it.
        value = FakeVec(self.matrix @ source.array)
        self.outputs.append(value)
        return value


def _bundle(volume, dtn, *, seen=None):
    volume = np.asarray(volume, dtype=np.complex128)
    dtn = np.asarray(dtn, dtype=np.complex128)
    return {
        "physical_action": MatrixAction(volume + dtn, seen),
        "volume_action": BorrowedVolume(volume),
        "dtn_action": MatrixAction(dtn),
    }


def test_packed_action_key_shape_uses_explicit_shared_dtn_owner():
    packed = {"physical_action": object(), "volume_action": object()}
    dtn = object()
    native = {"physical_action": object(), "volume_action": object(), "dtn_action": dtn}

    selected = with_shared_dtn_owner(packed, native)

    assert selected["physical_action"] is packed["physical_action"]
    assert selected["volume_action"] is packed["volume_action"]
    assert selected["dtn_action"] is dtn
    assert "dtn_action" not in packed
    with pytest.raises(KeyError, match="dtn_action"):
        with_shared_dtn_owner(packed, {"physical_action": object(), "volume_action": object()})


def test_failure_capture_uses_unmutated_phg_and_exact_live_pc(tmp_path):
    g_values = np.array([1.0 + 0.5j, 2.0 - 0.25j, 3.0 + 1.5j], dtype=np.complex128)
    restriction_matrix = np.array(
        [[1.0, 0.0, 0.8 + 0.2j], [0.0, 1.0 - 0.1j, 0.0]],
        dtype=np.complex128,
    )
    prolongation_matrix = np.array([[1.0, 0.0], [0.0, 1.0], [0.0, 0.0]])
    a4_fast = _bundle(
        np.diag([1.5 + 0.1j, 2.5 - 0.1j]), np.diag([0.5, 0.5])
    )
    a4_native = _bundle(
        np.diag([1.4 + 0.1j, 2.6 - 0.1j]), np.diag([0.5, 0.5])
    )
    pc_seen = []
    a6_fast = _bundle(np.diag([0.5, 0.5, 1.0]), np.diag([0.5, 0.5, 1.0]), seen=pc_seen)
    native_pc_seen = []
    a6_native = _bundle(
        np.diag([0.51 + 0.05j, 0.49 - 0.04j, 1.02 + 0.03j]),
        np.diag([0.49, 0.51, 0.98]),
        seen=native_pc_seen,
    )
    ph_inputs = []

    def restrict(vector):
        ph_inputs.append(vector)
        return FakeVec(restriction_matrix @ vector.array)

    diag = V7BalancedFailureDiagnostic(
        tmp_path, identity={"fake": True}, p4_rows=2, p6_rows=3
    )
    diag.configure(
        restriction=restrict,
        a4_fast=a4_fast,
        a4_native=a4_native,
        a6_fast=a6_fast,
        a6_native=a6_native,
    )
    diag.activate(context={
        "activation_stage": "after_setup_qa_before_outer_fgmres",
        "setup_qa_calls_excluded": True,
    })
    diag.set_apply_context({
        "scope": "outer_pc",
        "outer_pc_callback_ordinal": 1,
        "fgmres_iteration": "NOT_EXPOSED_AT_PRECONDITIONER_CALLBACK",
    })

    primal_calls = []

    def coarse(_source):
        c = FakeVec([1.0, 2.0])
        assert diag.hold_coarse(c)
        pc = FakeVec(prolongation_matrix @ c.array)
        primal_calls.append((c, pc))
        return pc

    coupling = PhysicalBalancedCoupling(
        lambda x: apply_owned(a6_fast["physical_action"], x),
        coarse,
        lambda x: FakeVec(x.array),
        restrict,
        route="BAL_H",
        failure_diagnostic=diag,
    )
    source = FakeVec(g_values)

    with pytest.raises(BalancedConstraintRejected) as rejected:
        coupling.apply(source)

    # The original numerical gate facts remain the same values calculated
    # before the observer ran. The observer did not replace that expression.
    c_values = np.array([1.0, 2.0], dtype=np.complex128)
    pc_values = prolongation_matrix @ c_values
    u_values = a6_fast["physical_action"].matrix @ pc_values
    residual_values = g_values - u_values
    ph_g_values = restriction_matrix @ g_values
    ph_residual_values = restriction_matrix @ residual_values
    expected_relative = np.linalg.norm(ph_residual_values) / (
        np.linalg.norm(ph_g_values) + np.linalg.norm(ph_g_values - ph_residual_values)
    )
    assert rejected.value.facts["relative"] == pytest.approx(expected_relative)
    assert rejected.value.facts["limit"] == 1e-8

    baseline_source = FakeVec(g_values)
    baseline_coarse = FakeVec(c_values)
    baseline_pc = FakeVec(prolongation_matrix @ baseline_coarse.array)
    baseline_coarse.destroy()
    baseline_restriction = lambda vector: FakeVec(restriction_matrix @ vector.array)
    baseline_coupling = PhysicalBalancedCoupling(
        lambda x: apply_owned(a6_fast["physical_action"], x),
        lambda _x: FakeVec(baseline_pc.array),
        lambda x: FakeVec(x.array),
        baseline_restriction,
        route="BAL_H",
    )
    with pytest.raises(BalancedConstraintRejected) as baseline_rejected:
        baseline_coupling.apply(baseline_source)
    assert rejected.value.facts == baseline_rejected.value.facts

    # Gate PH(leading) was mutated for its scale term. The observer therefore
    # must make a third restriction call on the original g, rather than reuse
    # that mutated temporary. P(c) was computed once by coarse() and the same
    # object is used by both the original fast A6 and the diagnostic native A6.
    assert len(ph_inputs) >= 3
    assert ph_inputs[0] is source
    assert ph_inputs[2] is source
    assert len(primal_calls) == 1
    coarse, live_pc = primal_calls[0]
    assert len(pc_seen) == 2 and pc_seen[0] is live_pc and pc_seen[1] is not live_pc
    assert len(native_pc_seen) == 1 and native_pc_seen[0] is live_pc
    assert diag.pending_coarse is None
    assert coarse.destroy_count == 1
    assert live_pc.destroy_count == 1
    assert not diag.facts.get("diagnostic_error")

    capture_dir = tmp_path / "v7_balanced_failure_diagnostic"
    captured_g = np.load(capture_dir / "failed_full_p6_source_g.npy", allow_pickle=False)
    captured_c = np.load(capture_dir / "failed_full_p4_coarse_c.npy", allow_pickle=False)
    assert np.array_equal(captured_g, g_values)
    assert np.array_equal(captured_c, np.array([1.0, 2.0], dtype=np.complex128))
    assert not (capture_dir / "failed_full_p6_primal_pc.npy").exists()

    record = json.loads((tmp_path / "v7_balanced_failure_diagnostic.json").read_text())
    decomposition = record["decomposition"]
    expected_r4 = ph_g_values - a4_fast["physical_action"].matrix @ c_values
    assert decomposition["vector_norms"]["PH_g"] == pytest.approx(np.linalg.norm(ph_g_values))
    assert decomposition["term_norms"]["r4_PH_g_minus_A4_fast_c"] == pytest.approx(
        np.linalg.norm(expected_r4)
    )
    expected_closure = ph_residual_values - (
        ph_g_values - restriction_matrix @ u_values
    )
    assert decomposition[
        "restriction_distributivity_PH_g_minus_u_vs_PHg_minus_PHu_norm"
    ] == pytest.approx(np.linalg.norm(expected_closure))
    a4f_c = a4_fast["physical_action"].matrix @ c_values
    a4n_c = a4_native["physical_action"].matrix @ c_values
    a6n_pc = a6_native["physical_action"].matrix @ pc_values
    expected_terms = (
        ph_g_values - a4f_c,
        a4f_c - a4n_c,
        a4n_c - restriction_matrix @ a6n_pc,
        restriction_matrix @ (a6n_pc - u_values),
    )
    expected_actual = ph_residual_values
    assert decomposition["term_norms"]["r4_PH_g_minus_A4_fast_c"] == pytest.approx(
        np.linalg.norm(expected_terms[0])
    )
    assert decomposition["term_norms"]["delta4_A4_fast_minus_A4_native_c"] == pytest.approx(
        np.linalg.norm(expected_terms[1])
    )
    assert decomposition["term_norms"]["cross_A4_native_c_minus_PH_A6_native_Pc"] == pytest.approx(
        np.linalg.norm(expected_terms[2])
    )
    assert decomposition["term_norms"]["delta6_PH_A6_native_minus_fast_Pc"] == pytest.approx(
        np.linalg.norm(expected_terms[3])
    )
    assert all(np.linalg.norm(term) > 0 for term in expected_terms[1:])
    expected_telescope = sum(expected_terms, np.zeros_like(expected_actual))
    assert np.linalg.norm(expected_telescope - expected_actual) < 1e-12
    assert decomposition["formula_minus_actual_norm"] < 1e-12
    assert decomposition["gate_expression_replaced"] is False
    assert record["status"] == "BAL_H_FIRST_BALANCE_REJECTION_CAPTURED"
    assert record["root_cause_proven"] is False
    assert record["observer_report_is_solver_qualification"] is False
    assert "one_run_diagnostic_only" not in record
    assert record["actual_failed_apply_context"]["activation"]["activation_stage"] == (
        "after_setup_qa_before_outer_fgmres"
    )
    assert record["actual_failed_apply_context"]["outer_apply"][
        "outer_pc_callback_ordinal"
    ] == 1
    borrowed = [
        action["volume_action"].outputs
        for action in (a4_fast, a4_native, a6_fast, a6_native)
    ]
    assert all(value.destroy_count == 0 for outputs in borrowed for value in outputs)


def test_restriction_cancellation_defect_is_reported_separately(tmp_path):
    g_values = np.array([1e16, 1.0, 0.0, 0.0], dtype=np.complex128)
    p_matrix = np.array([[1.0, 0.0], [0.0, 1.0], [0.0, 0.0], [0.0, 0.0]])
    fast_a6_matrix = np.zeros((4, 4), dtype=np.complex128)
    fast_a6_matrix[0, 0] = 1e16
    fast_a6_matrix[2, 0] = -1e9
    zero_a6 = np.zeros((4, 4), dtype=np.complex128)
    a4 = _bundle(np.eye(2), np.zeros((2, 2)))
    a6_fast = _bundle(fast_a6_matrix, zero_a6)
    a6_native = _bundle(fast_a6_matrix, zero_a6)

    def restrict(vector):
        values = vector.array
        # Fixed left-to-right summation exposes the floating cancellation case.
        return FakeVec([values[0] + values[1], values[2]])

    diag = V7BalancedFailureDiagnostic(
        tmp_path, identity={"cancellation_case": True}, p4_rows=2, p6_rows=4
    )
    diag.configure(
        restriction=restrict,
        a4_fast=a4,
        a4_native=a4,
        a6_fast=a6_fast,
        a6_native=a6_native,
    )
    diag.activate()

    def coarse(_source):
        c = FakeVec([1.0, 0.0])
        assert diag.hold_coarse(c)
        return FakeVec(p_matrix @ c.array)

    coupling = PhysicalBalancedCoupling(
        lambda x: apply_owned(a6_fast["physical_action"], x), coarse,
        lambda x: FakeVec(x.array), restrict, route="BAL_H", failure_diagnostic=diag,
    )
    with pytest.raises(BalancedConstraintRejected):
        coupling.apply(FakeVec(g_values))

    decomposition = diag.facts["decomposition"]
    assert decomposition["restriction_distributivity_PH_g_minus_u_vs_PHg_minus_PHu_norm"] == 1.0
    assert decomposition["delta6_projection_distributivity_norm"] == 0.0


def test_balance_pass_releases_initial_and_feedback_coarse_on_repeat_apply(tmp_path):
    restriction_matrix = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    p4_identity = _bundle(np.eye(2), np.zeros((2, 2)))
    p6_identity = _bundle(np.eye(3), np.zeros((3, 3)))

    def restrict(vector):
        return FakeVec(restriction_matrix @ vector.array)

    diag = V7BalancedFailureDiagnostic(
        tmp_path, identity={"normal_pass_lifecycle": True}, p4_rows=2, p6_rows=3
    )
    diag.configure(
        restriction=restrict,
        a4_fast=p4_identity,
        a4_native=p4_identity,
        a6_fast=p6_identity,
        a6_native=p6_identity,
    )
    diag.activate()
    coarse_vectors = []
    coarse_calls = 0

    def coarse(_source):
        nonlocal coarse_calls
        coarse_calls += 1
        if coarse_calls % 2:
            c = FakeVec([1.0, 2.0])
            pc = FakeVec([1.0, 2.0, 0.0])
        else:
            c = FakeVec([float(coarse_calls), 0.0])
            pc = FakeVec([0.0, 0.0, 0.0])
        assert diag.hold_coarse(c)
        coarse_vectors.append(c)
        return pc

    coupling = PhysicalBalancedCoupling(
        lambda x: apply_owned(p6_identity["physical_action"], x),
        coarse,
        lambda _x: FakeVec([0.0, 0.0, 0.0]),
        restrict,
        route="BAL_H",
        failure_diagnostic=diag,
    )
    for _ in range(2):
        result = coupling.apply(FakeVec([1.0, 2.0, 0.0]))
        result.destroy()
        assert diag.pending_coarse is None

    assert coarse_calls == 4
    assert [vector.destroy_count for vector in coarse_vectors] == [1, 1, 1, 1]
    assert diag.snapshot()["status"] == "ARMED_FIRST_BALANCE_REJECTION_OBSERVER"
    report = diag.finish_without_rejection(reason="full_v7_workflow_completed")
    assert report["status"] == "DIAGNOSTIC_NOT_REPRODUCED"
    assert report["full_v7_solve_was_not_stopped_by_observer"] is True
    assert "one_run_diagnostic_only" not in report


def test_v7_diagnostic_launch_contract_is_explicit_and_identity_bound(tmp_path):
    source = "a" * 40
    input_sha = "b" * 64
    resolved_sha = "c" * 64
    physical_sha = "d" * 64
    assert diagnostic_requested(V7_PROFILE, None) is False
    with pytest.raises(ValueError, match="exactly '1'"):
        diagnostic_requested(V7_PROFILE, "true")
    with pytest.raises(ValueError, match="restricted"):
        diagnostic_requested("some_other_profile", "1")

    contract = launch_contract(
        profile=V7_PROFILE,
        execution_mode="full_solve",
        environment_value="1",
        source_sha=source,
        input_sha256=input_sha,
        resolved_config_sha256=resolved_sha,
        physical_model_sha256=physical_sha,
        output_directory=tmp_path,
    )
    assert contract["environment_binding"] == {"name": V7_DIAGNOSTIC_ENV, "value": "1"}
    assert contract["diagnostic_implementation_source_sha"] == source
    assert contract["numerical_baseline_source_sha"] != source
    assert contract["activation_stage"] == "after_setup_qa_before_outer_fgmres"
    assert contract["on_balance_pass"] == "continue_full_v7_solve"
    assert contract["solver_iteration_or_call_limit_added"] is False
    assert contract["observer_report_is_solver_qualification"] is False
    assert contract["numerical_gate_or_arithmetic_changed"] is False
    with pytest.raises(ValueError, match="full_solve"):
        launch_contract(
            profile=V7_PROFILE,
            execution_mode="pilot_16",
            environment_value="1",
            source_sha=source,
            input_sha256=input_sha,
            resolved_config_sha256=resolved_sha,
            physical_model_sha256=physical_sha,
            output_directory=tmp_path,
        )

    manifest = {
        "execution_mode": "full_solve",
        "v7_balanced_failure_diagnostic": contract,
    }
    assert validate_worker_binding(
        manifest,
        environment_value="1",
        profile=V7_PROFILE,
        source_sha=source,
        input_sha256=input_sha,
        resolved_config_sha256=resolved_sha,
        physical_model_sha256=physical_sha,
        output_directory=tmp_path,
    ) == contract
    with pytest.raises(ValueError, match="does not match"):
        validate_worker_binding(
            manifest,
            environment_value="1",
            profile=V7_PROFILE,
            source_sha="e" * 40,
            input_sha256=input_sha,
            resolved_config_sha256=resolved_sha,
            physical_model_sha256=physical_sha,
            output_directory=tmp_path,
        )
    with pytest.raises(ValueError, match="absent from the worker environment"):
        validate_worker_binding(
            manifest,
            environment_value=None,
            profile=V7_PROFILE,
            source_sha=source,
            input_sha256=input_sha,
            resolved_config_sha256=resolved_sha,
            physical_model_sha256=physical_sha,
            output_directory=tmp_path,
        )


def test_observer_exception_preserves_balance_rejection_and_releases_coarse():
    class FailingObserver:
        def __init__(self):
            self.coarse = None
            self.errors = []

        def hold_coarse(self, vector):
            self.coarse = vector
            return True

        def on_balance_rejection(self, **_kwargs):
            raise OSError("diagnostic write failed")

        def record_unexpected_error(self, error):
            self.errors.append(error)

        def release_pending_coarse(self):
            if self.coarse is not None:
                self.coarse.destroy()
                self.coarse = None

    observer = FailingObserver()
    source = FakeVec([1.0, 2.0, 3.0])
    restriction = lambda value: FakeVec(np.array([value.array[0] + value.array[2], value.array[1]]))

    def coarse(_source):
        c = FakeVec([1.0, 2.0])
        observer.hold_coarse(c)
        return FakeVec([1.0, 2.0, 0.0])

    coupling = PhysicalBalancedCoupling(
        lambda x: FakeVec(x.array), coarse, lambda x: FakeVec(x.array), restriction,
        route="BAL_H", failure_diagnostic=observer,
    )
    with pytest.raises(BalancedConstraintRejected) as rejected:
        coupling.apply(source)
    assert rejected.value.facts["limit"] == 1e-8
    assert observer.errors and isinstance(observer.errors[0], OSError)
    assert observer.coarse is None


def test_default_inert_hook_does_not_capture_or_hold_coarse(tmp_path):
    diag = V7BalancedFailureDiagnostic(
        tmp_path,
        identity={"fake": True},
        p4_rows=2,
        p6_rows=3,
        diagnostic_implementation_source_sha="e" * 40,
    )
    coarse = FakeVec([1.0, 2.0])
    assert diag.hold_coarse(coarse) is False
    assert diag.pending_coarse is None
    assert diag.snapshot()["status"] == "PREPARED_NOT_ACTIVE"
    assert diag.snapshot()["diagnostic_implementation_source_sha"] == "e" * 40
    assert "diagnostic_implementation_source_sha256" not in diag.snapshot()
    assert not hasattr(diag, "begin_outer_pc_attempt")


@pytest.mark.parametrize(
    ("environment_value", "manifest_has_observer", "expected_error"),
    (
        (None, False, None),
        ("1", True, None),
        (
            None,
            True,
            "V7 observer binding failed: run manifest enables an observer absent from the worker environment",
        ),
        (
            "1",
            False,
            "V7 observer binding failed: worker observer request does not match the run manifest identity",
        ),
    ),
)
def test_real_worker_payload_entry_checks_both_observer_binding_directions(
    tmp_path, monkeypatch, environment_value, manifest_has_observer, expected_error
):
    """The actual pre-FE worker gate rejects either side of a lost binding."""

    from src.io.execution_plan import METHOD_ADAPTERS
    from src.io.native_capacity_profile import native_profile_facts
    from src.runners.task038_input_worker import _load_and_validate_worker_payload

    if environment_value is None:
        monkeypatch.delenv(V7_DIAGNOSTIC_ENV, raising=False)
    else:
        monkeypatch.setenv(V7_DIAGNOSTIC_ENV, environment_value)
    source_sha = "c" * 40
    physical_sha = "b" * 64
    input_bytes = b"minimal V7 worker contract input\n"
    input_sha = hashlib.sha256(input_bytes).hexdigest()
    output_directory = tmp_path.resolve()
    (output_directory / "input_original.dat").write_bytes(input_bytes)

    resolved = {
        "provenance": {
            "source_path": "input/v7_fake.dat",
            "input_sha256": input_sha,
            "physical_model_sha256": physical_sha,
        },
        "method": {"kind": "hybrid_iterative", "requested_modes_per_direction": 1},
        "execution": {"mpi_size": 1},
        "solver": {"preconditioner": V7_PROFILE},
        "model_id": "fake-v7-model",
        "run_id": "fake-v7-run",
        "comparison_group": "fake-v7-group",
    }
    resolved_bytes = json.dumps(resolved, sort_keys=True, separators=(",", ":")).encode()
    resolved_sha = hashlib.sha256(resolved_bytes).hexdigest()
    resolved_path = output_directory / "resolved.json"
    resolved_path.write_bytes(resolved_bytes)
    observer_contract = launch_contract(
        profile=V7_PROFILE,
        execution_mode="full_solve",
        environment_value="1",
        source_sha=source_sha,
        input_sha256=input_sha,
        resolved_config_sha256=resolved_sha,
        physical_model_sha256=physical_sha,
        output_directory=output_directory,
    )
    manifest = {
        "input_path": resolved["provenance"]["source_path"],
        "mpi_size": 1,
        "method": "hybrid_iterative",
        "resolved_method_adapter": METHOD_ADAPTERS["hybrid_iterative"],
        "input_sha256": input_sha,
        "physical_model_sha256": physical_sha,
        "source_sha": source_sha,
        "resolved_config_sha256": resolved_sha,
        "output_directory": str(output_directory),
        "numerical_output_directory": str(output_directory / "numerical_output"),
        "model_id": resolved["model_id"],
        "run_id": resolved["run_id"],
        "comparison_group": resolved["comparison_group"],
        "solver": resolved["solver"],
        "requested_modes": 1,
        "execution_mode": "full_solve",
        "component_options": native_profile_facts(V7_PROFILE)["component_options"],
    }
    if manifest_has_observer:
        manifest["v7_balanced_failure_diagnostic"] = observer_contract
    manifest_path = output_directory / "run_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    loaded, errors = _load_and_validate_worker_payload(
        resolved_config=resolved_path,
        manifest=manifest_path,
        expected_input_sha256=input_sha,
        expected_physical_model_sha256=physical_sha,
        expected_source_sha=source_sha,
        expected_mpi_size=1,
        expected_method="hybrid_iterative",
        expected_adapter=METHOD_ADAPTERS["hybrid_iterative"],
        expected_output_directory=output_directory,
        expected_resolved_config_sha256=resolved_sha,
        actual_mpi_size=1,
    )

    assert loaded == resolved
    if expected_error is None:
        assert errors == []
    else:
        assert errors == [expected_error]
