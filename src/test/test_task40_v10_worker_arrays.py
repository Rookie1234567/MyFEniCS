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


def test_regular_inverse_gate_failures_are_reported_independently():
    cases = (
        ("original_regular_equation", "equation_relative", None, 1.01e-10),
        ("independent_sector_action_consistency", "action_relative", None, 1.01e-11),
        ("full_internal_recovery", "recovery", "internal_residual_relative", 1.01e-11),
        ("two_local_original_equations", "local_equation_relative", None, 1.01e-10),
        ("all_532_port_equations", "recovery", "port_residual_relative", 1.01e-8),
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
