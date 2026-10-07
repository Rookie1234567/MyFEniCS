import json
from types import MappingProxyType, SimpleNamespace

import numpy as np
import pytest
from petsc4py import PETSc

from src.runners import task40_v10_worker
from src.runners.physical_p4_schur_v14 import _V14Runtime, _write_json
from src.runners.task40_v10_worker import (
    _assign_vector_storage,
    _packet_array_bytes,
    _regular_inverse_gate_facts,
    _save_packet,
)
from src.solvers.task40_v10_p6_periodic_profile import (
    TASK40_V10_P6_PROFILE,
    TASK40_V11_P6_GX560_PROFILE,
    TASK40_V11_P6_GX784_PROFILE,
)


def _regular_inverse_gate_inputs():
    return {
        "equation_relative": 1.5e-11,
        "action_relative": 5.0e-12,
        "recovery": {
            "internal_row_count": 36_000,
            "internal_residual_relative": 5.0e-12,
            "port_mode_count": 532,
            "port_residual_relative": 5.0e-9,
            "native_identity_relative": 5.0e-11,
            "schur_port_identity_relative": 5.0e-11,
            "projected_saved_field_recovery_relative": 5.0e-12,
        },
        "profile": TASK40_V10_P6_PROFILE,
        "local_equation_relative": 5.0e-11,
        "port_closure_relative": 5.0e-12,
        "q_residual_relative": 5.0e-11,
        "q_coverage_passed": True,
    }


def test_assign_vector_storage_uses_public_writable_petsc_array_api():
    vector = PETSc.Vec().createSeq(3, comm=PETSc.COMM_SELF)
    try:
        _assign_vector_storage(vector, np.array([1 + 2j, 3 + 4j, 5 + 6j]))
        _assign_vector_storage(
            vector, np.array([9 + 1j, 8 + 2j]), rows=np.array([0, 2], dtype=np.int64)
        )
        np.testing.assert_array_equal(
            np.asarray(vector.array_r),
            np.array([9 + 1j, 3 + 4j, 8 + 2j], dtype=np.complex128),
        )
    finally:
        vector.destroy()


def test_regular_inverse_equation_gate_is_distinct_from_action_gate():
    facts = _regular_inverse_gate_facts(**_regular_inverse_gate_inputs())

    assert facts["passed"]
    assert facts["gates"]["original_regular_equation"]
    assert facts["gates"]["independent_sector_action_consistency"]


@pytest.mark.parametrize(
    ("profile", "expected_schema"),
    (
        (
            TASK40_V10_P6_PROFILE,
            "task40extra.review_v10_p6_regular_inverse_checks.v1",
        ),
        (
            TASK40_V11_P6_GX560_PROFILE,
            "task40extra.review_v11_p6_regular_inverse_checks.v1",
        ),
        (
            TASK40_V11_P6_GX784_PROFILE,
            "task40extra.review_v11_p6_regular_inverse_checks.v1",
        ),
    ),
)
def test_regular_inverse_metadata_schema_preserves_b0_and_gx_profiles(
    profile, expected_schema
):
    assert task40_v10_worker._regular_inverse_checks_schema(profile) == expected_schema


def test_regular_inverse_gate_failures_are_reported_independently():
    cases = (
        ("original_regular_equation", "equation_relative", None, 1.01e-10),
        ("independent_sector_action_consistency", "action_relative", None, 1.01e-11),
        ("full_internal_recovery", "recovery", "internal_residual_relative", 1.01e-11),
        ("two_local_original_equations", "local_equation_relative", None, 1.01e-10),
        ("all_port_equations", "recovery", "port_residual_relative", 1.01e-8),
        ("native_action_recovery_identity", "recovery", "native_identity_relative", 1.01e-10),
        ("schur_port_recovery_identity", "recovery", "schur_port_identity_relative", 1.01e-10),
        (
            "saved_field_local_recovery_identity",
            "recovery",
            "projected_saved_field_recovery_relative",
            1.01e-11,
        ),
        ("global_alpha_port_closure", "port_closure_relative", None, 1.01e-11),
        ("all_four_q_true_residuals", "q_residual_relative", None, 1.01e-10),
        ("all_four_q_true_residuals", "q_coverage_passed", None, False),
    )

    for expected_failure, input_name, recovery_key, value in cases:
        inputs = _regular_inverse_gate_inputs()
        if recovery_key is None:
            inputs[input_name] = value
        else:
            inputs["recovery"] = dict(inputs["recovery"])
            inputs["recovery"][recovery_key] = value
        facts = _regular_inverse_gate_facts(**inputs)
        assert facts["failed_gates"] == [expected_failure]


def test_regular_inverse_passes_sector_action_map_and_petsc_to_recovery(
    monkeypatch,
):
    class _ReachedRecovery(Exception):
        pass

    captured = {}
    sector_action_vectors = {
        0: {"full_storage": np.zeros(3)},
        1: {"full_storage": np.zeros(3)},
    }

    class _Inverse:
        def apply_augmented(self, _rhs, *, port_rhs):
            return np.zeros(2, dtype=np.complex128), np.zeros(532, dtype=np.complex128)

    class _PhysicalAction:
        def apply(self, _source, target):
            target.set(0.0)

    class _DtnAction:
        carrier = SimpleNamespace(
            entries=tuple(SimpleNamespace(normalization_h=1.0) for _ in range(532))
        )

        def recover_auxiliary(self, _solution):
            return np.zeros(532, dtype=np.complex128)

    def sector_forward(*_args, **_kwargs):
        return np.zeros(2, dtype=np.complex128), sector_action_vectors, {}

    def recovery(
        reference_arg,
        _solution,
        _alpha,
        _fe_rhs,
        _port_rhs,
        local_action_vectors,
        petsc,
        *,
        allocation_gate,
        operation_relative,
    ):
        captured.update(
            reference=reference_arg,
            local_action_vectors=local_action_vectors,
            petsc=petsc,
            allocation_gate=allocation_gate,
            operation_relative=operation_relative,
        )
        raise _ReachedRecovery

    monkeypatch.setattr(
        task40_v10_worker,
        "_runtime_interior_rows",
        lambda _ref: np.empty(0, dtype=np.int64),
    )
    monkeypatch.setattr(task40_v10_worker, "_sector_native_forward_action", sector_forward)
    monkeypatch.setattr(task40_v10_worker, "_regular_local_recovery_facts", recovery)
    runtime = SimpleNamespace(sample=lambda _label: None)
    layout = SimpleNamespace(independent=np.array([0, 1], dtype=np.int64), full_rows=3)
    reference = {
        "profile": TASK40_V10_P6_PROFILE,
        "inverse": _Inverse(),
        "full_layout": layout,
        "global_bundle": {
            "modes": tuple(range(532)),
            "physical_action": _PhysicalAction(),
            "dtn_action": _DtnAction(),
        },
    }
    physical_rhs = PETSc.Vec().createSeq(3, comm=PETSc.COMM_SELF)
    physical_rhs.set(0.0)
    allocation_gate = lambda _label, _facts: None
    try:
        with pytest.raises(_ReachedRecovery):
            task40_v10_worker._verify_regular_inverse(
                runtime,
                reference,
                physical_rhs,
                {},
                allocation_gate=allocation_gate,
            )
    finally:
        physical_rhs.destroy()

    assert captured["reference"] is reference
    assert captured["local_action_vectors"] is sector_action_vectors
    assert captured["petsc"] is PETSc
    assert captured["allocation_gate"] is allocation_gate
    assert callable(captured["operation_relative"])


def test_v13_regular_inverse_continues_all_four_witnesses_after_bounded_first_state(
    monkeypatch,
):
    from src.solvers.augmented_reference_correction import (
        STRICT_THEN_BOUNDED_INEXACT_V13,
    )

    profile = TASK40_V10_P6_PROFILE
    n = 2
    mode_count = profile.mode_count
    recovery_calls = []
    marked = []
    q_rows = [
        {"q": q, "true_residual_relative": 1e-12, "rhs_norm": 1.0}
        for q in range(4)
    ]

    class _Factors:
        calls = 0
        factor_probe_limit = 1.0e-10

    class _Inverse:
        factors = _Factors()
        last_solve_audit = []
        call_initial = True

        def apply_augmented(self, fe_rhs, *, port_rhs):
            self.factors.calls += 4
            self.last_solve_audit = [{"q_true_residuals": list(q_rows)}]
            if self.call_initial:
                self.call_initial = False
                fe_rhs = np.asarray(fe_rhs, dtype=np.complex128)
                port_rhs = np.asarray(port_rhs, dtype=np.complex128)
                fe_delta = (
                    2e-9 * fe_rhs / np.linalg.norm(fe_rhs)
                    if np.linalg.norm(fe_rhs) > 0.0
                    else np.zeros_like(fe_rhs)
                )
                alpha = port_rhs.copy()
                if np.linalg.norm(port_rhs) > 0.0:
                    alpha = port_rhs + 4e-10 * port_rhs / np.linalg.norm(port_rhs)
                return fe_rhs + fe_delta, alpha
            self.call_initial = True
            return (
                np.asarray(fe_rhs, dtype=np.complex128).copy(),
                np.asarray(port_rhs, dtype=np.complex128).copy(),
            )

    class _PhysicalAction:
        def apply(self, source, target):
            _assign_vector_storage(target, np.asarray(source.array_r))

    class _DtnAction:
        carrier = SimpleNamespace(
            entries=tuple(
                SimpleNamespace(normalization_h=1.0) for _ in range(mode_count)
            )
        )

        def recover_auxiliary(self, _solution):
            return np.zeros(mode_count, dtype=np.complex128)

        def apply_modal_rhs(self, _amplitudes, target):
            target.set(0.0)

    def recovery(*_args, **_kwargs):
        recovery_calls.append(1)
        zeros_n = np.zeros(n, dtype=np.complex128)
        zeros_full = np.zeros(2 * n, dtype=np.complex128)
        return {
            "sector_facts": [
                {
                    "twist_index": 0,
                    "native_residual_relative": 0.0,
                    "native_rhs_operation_scale": 1.0,
                },
                {
                    "twist_index": 1,
                    "native_residual_relative": 0.0,
                    "native_rhs_operation_scale": 1.0,
                },
            ],
            "arrays": {
                "internal_residuals": zeros_full,
                "internal_effective_rhs": zeros_full,
                "internal_saved_field_action": zeros_full,
                "internal_original_rows": np.arange(2 * n, dtype=np.int64),
                "internal_twist_indices": np.zeros(2 * n, dtype=np.int8),
                "native_residuals": zeros_n,
                "port_residuals": np.zeros(mode_count, dtype=np.complex128),
                "native_identity_differences": zeros_n,
                "schur_port_identity_differences": np.zeros(mode_count, dtype=np.complex128),
                "projected_saved_field_differences": zeros_n,
            },
            "internal_residual_relative": 0.0,
            "internal_operation_scale": 1.0,
            "internal_row_count": 2 * n,
            "local_native_residual_relative": 0.0,
            "local_native_rhs_operation_scale": 1.0,
            "port_residual_relative": 0.0,
            "port_operation_scale": 1.0,
            "port_mode_count": mode_count,
            "native_identity_relative": 0.0,
            "native_identity_operation_scale": 1.0,
            "schur_port_identity_relative": 0.0,
            "schur_port_identity_operation_scale": 1.0,
            "projected_saved_field_recovery_relative": 0.0,
            "recovered_field_ffcx_apply_count": 0,
            "recovered_field_ffcx_apply_seconds": 0.0,
        }

    def gate_facts(**facts):
        numeric_pass = facts["equation_relative"] <= 1e-10
        gates = {
            "original_regular_equation": numeric_pass,
            "independent_sector_action_consistency": True,
            "full_internal_recovery": True,
            "two_local_original_equations": True,
            "all_port_equations": True,
            "native_action_recovery_identity": True,
            "schur_port_recovery_identity": True,
            "saved_field_local_recovery_identity": True,
            "global_alpha_port_closure": facts["port_closure_relative"] <= 1e-11,
            "all_four_q_true_residuals": facts["q_coverage_passed"]
            and facts["q_residual_relative"] <= 1e-10,
        }
        return {
            "gates": gates,
            "failed_gates": [name for name, passed in gates.items() if not passed],
            "passed": all(gates.values()),
            "limits": {name: 1e-10 for name in gates},
        }

    monkeypatch.setattr(task40_v10_worker, "_runtime_interior_rows", lambda _ref: np.empty(0, dtype=np.int64))
    monkeypatch.setattr(
        task40_v10_worker,
        "_sector_native_forward_action",
        lambda _ref, values, *_args, **_kwargs: (
            np.asarray(values, dtype=np.complex128).copy(),
            {
                0: {"full_storage": np.zeros(2 * n, dtype=np.complex128)},
                1: {"full_storage": np.zeros(2 * n, dtype=np.complex128)},
            },
            {},
        ),
    )
    monkeypatch.setattr(task40_v10_worker, "_regular_local_recovery_facts", recovery)
    monkeypatch.setattr(task40_v10_worker, "_regular_inverse_gate_facts", gate_facts)
    monkeypatch.setattr(
        task40_v10_worker, "_save_packet", lambda _runtime, label, _payload: {"path": label}
    )
    runtime = SimpleNamespace(
        sample=lambda _label: None,
        marker=lambda label, facts: marked.append((label, facts)),
    )
    layout = SimpleNamespace(independent=np.arange(n, dtype=np.int64), full_rows=n)
    reference = {
        "profile": profile,
        "inverse": _Inverse(),
        "full_layout": layout,
        "global_bundle": {
            "modes": tuple(range(mode_count)),
            "physical_action": _PhysicalAction(),
            "dtn_action": _DtnAction(),
        },
    }
    physical_rhs = PETSc.Vec().createSeq(n, comm=PETSc.COMM_SELF)
    _assign_vector_storage(
        physical_rhs, np.asarray([1.0 + 0.25j, -0.5 + 0.75j])
    )
    try:
        result = task40_v10_worker._verify_regular_inverse(
            runtime,
            reference,
            physical_rhs,
            {},
            allocation_gate=lambda _label, _facts: None,
            reference_pc_strategy=STRICT_THEN_BOUNDED_INEXACT_V13,
        )
    finally:
        physical_rhs.destroy()

    assert [row["name"] for row in result["cases"]] == [
        "generic_full_independent",
        f"interior_only_all_{profile.global_interior_rows}",
        "nonzero_all_mode_port_rhs",
        "physical_regular_incident_rhs",
    ]
    assert len(recovery_calls) > len(result["cases"])
    assert all(row["passed"] for row in result["cases"])
    assert result["cases"][0]["reference_pc_initial_strict_gate_passed"] is False
    assert all(
        row["reference_pc_admission"] == "STRICT_REFERENCE_PASS"
        for row in result["cases"]
    )
    assert any(row["reference_pc_initial_strict_gate_passed"] is False for row in result["cases"])


def test_candidate_identity_packet_marker_and_summary_accept_readonly_audits(
    tmp_path,
):
    matrix = np.arange(6, dtype=np.complex128).reshape(2, 3)
    payload = MappingProxyType(
        {
            "schema": "task40extra.review_v10_b0_candidate_identity.v1",
            "target_backend": MappingProxyType(
                {
                    "audit": MappingProxyType(
                        {
                            "schema": "physical-action-audit.v1",
                            "components": ("curl", "material_mass"),
                            "matrix": matrix,
                        }
                    )
                }
            ),
            "target_mesh": MappingProxyType(
                {
                    "air_void_audit": MappingProxyType(
                        {"status": "PASS", "checked_cells": 12}
                    )
                }
            ),
        }
    )
    assert _packet_array_bytes(payload) == matrix.nbytes

    runtime = object.__new__(_V14Runtime)
    runtime.directory = tmp_path
    runtime.stage = "B0_CANDIDATE"
    runtime.events_path = tmp_path / "v10_candidate_events.jsonl"
    runtime._pc_clock = object()
    runtime.reserve_workspace = lambda _label, _amount: None
    runtime.release_workspace = lambda _label: None

    packet = _save_packet(runtime, "v10_candidate_operator_identity", payload)
    packet_path = tmp_path / "v10_candidate_operator_identity.json"
    packet_record = json.loads(packet_path.read_text(encoding="utf-8"))
    audit_record = packet_record["target_backend"]["audit"]
    assert audit_record["components"] == ["curl", "material_mass"]
    assert audit_record["schema"] == "physical-action-audit.v1"
    assert packet_record["target_mesh"]["air_void_audit"] == {
        "status": "PASS",
        "checked_cells": 12,
    }
    assert packet == packet_record
    with np.load(packet_record["arrays"]["path"], allow_pickle=False) as arrays:
        np.testing.assert_array_equal(
            arrays[audit_record["matrix"]["array_key"]], matrix
        )

    runtime.marker("v10_candidate_operator_identity", payload)
    marker_rows = [
        json.loads(line)
        for line in runtime.events_path.read_text(encoding="utf-8").splitlines()
    ]
    identity_marker = next(
        row for row in marker_rows if row["event"] == "v10_candidate_operator_identity"
    )
    marker_audit = identity_marker["facts"]["target_backend"]["audit"]
    assert marker_audit["components"] == ["curl", "material_mass"]
    assert marker_audit["matrix"]["shape"] == [2, 3]
    assert marker_audit["matrix"]["dtype"] == "complex128"
    assert marker_audit["matrix"]["sha256"]

    summary_path = tmp_path / "task40_v10_p6_candidate_summary.json"
    _write_json(summary_path, {"candidate_identity": payload})
    summary_record = json.loads(summary_path.read_text(encoding="utf-8"))
    summary_audit = summary_record["candidate_identity"]["target_backend"]["audit"]
    assert summary_audit["components"] == ["curl", "material_mass"]
    assert summary_audit["matrix"]["shape"] == [2, 3]
    assert summary_audit["matrix"]["dtype"] == "complex128"
    assert summary_audit["matrix"]["sha256"]
