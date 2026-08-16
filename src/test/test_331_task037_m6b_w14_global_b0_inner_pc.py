from __future__ import annotations

import json

import numpy as np
import pytest
from petsc4py import PETSc

from src.solvers.hcurl_h2b_m5_coercive import (
    M5M4YPCContext,
    build_m5_b0_mat,
)
from src.solvers.hcurl_m6b_w14_global_b0_inner_pc import W14GlobalB0InnerPC


class _DiagonalAction:
    def __init__(self, diagonal: np.ndarray) -> None:
        self.diagonal = np.asarray(diagonal, dtype=np.complex128)
        self.output = PETSc.Vec().createSeq(self.diagonal.size, comm=PETSc.COMM_SELF)

    def mult(self, source: PETSc.Vec) -> PETSc.Vec:
        self.output.getArray()[:] = self.diagonal * source.getArray(readonly=True)
        return self.output

    def destroy(self) -> None:
        self.output.destroy()


def _vec(values: np.ndarray) -> PETSc.Vec:
    result = PETSc.Vec().createSeq(values.size, comm=PETSc.COMM_SELF)
    result.getArray()[:] = np.asarray(values, dtype=np.complex128)
    return result


def _build(diagonal: np.ndarray, pc_apply):
    action = _DiagonalAction(diagonal)
    matrix, matrix_context = build_m5_b0_mat(
        action,
        owned_rows=diagonal.size,
        global_rows=diagonal.size,
        comm=PETSc.COMM_SELF,
    )
    pc_context = M5M4YPCContext(
        type("PC", (), {"apply": pc_apply})(), global_rows=diagonal.size
    )
    wrapper = W14GlobalB0InnerPC(matrix, pc_context, matrix_context)
    return action, matrix, pc_context, matrix_context, wrapper


def test_w14_fixed_inner_pc_applies_and_keeps_only_scalar_hash_audit():
    diagonal = np.asarray([1.0 + 0.2j, 2.0 - 0.1j, 0.75 + 0.3j])
    action, matrix, pc_context, matrix_context, wrapper = _build(
        diagonal, lambda _self, values: values / diagonal
    )
    rhs = np.asarray([1.0 - 0.5j, -0.25 + 0.75j, 0.5 + 0.25j], dtype=np.complex128)
    try:
        result = wrapper.apply(rhs)
        audit = wrapper.audit
        assert result.dtype == np.dtype(np.complex128)
        assert result.shape == rhs.shape
        assert audit["algorithm"] == {
            "solver": "fgmres",
            "restart": 20,
            "max_it": 20,
            "zero_start": True,
            "rtol": 0.0,
            "atol": 0.0,
            "pc_side": "right",
            "mpi_size": 1,
        }
        assert audit["applications"][0]["algorithm"] == "fgmres_right_b0_fixed20"
        assert audit["applications"][0]["finite"] is True
        assert audit["applications"][0]["gate_pass"] is True
        assert audit["applications"][0]["true_residual"] <= 1.0e-2
        assert audit["applications"][0]["operator_apply_count_delta"] > 0
        assert audit["applications"][0]["pc_apply_count_delta"] > 0
        expected_rhs_bytes = rhs.size * np.dtype(np.complex128).itemsize
        assert audit["rhs_vec_owned"] is True
        assert audit["rhs_vec_destroyed"] is False
        assert audit["wrapper_owned_full_vector_count"] == 1
        assert audit["wrapper_owned_full_vector_bytes"] == expected_rhs_bytes
        assert audit["retained_full_vector_count"] == 1
        assert audit["retained_full_vector_bytes"] == expected_rhs_bytes
        assert audit["application_records_full_vector_count"] == 0
        assert audit["application_records_full_vector_bytes"] == 0
        assert audit["ownership"] == {
            "rhs_work_vec": "owned",
            "operator": "borrowed",
            "contexts": "borrowed",
            "factor_store": "borrowed",
        }
        assert not any(
            isinstance(value, np.ndarray)
            for value in audit["applications"][0].values()
        )
        assert audit["architecture"] == {
            "fine_space": "uncondensed_fullspace",
            "global_matrix": False,
            "static_condensation": False,
            "trace_slab": False,
            "slab_factors": 0,
        }
        json.dumps(audit, allow_nan=False)
    finally:
        wrapper.destroy()
        destroyed_audit = wrapper.audit
        assert destroyed_audit["rhs_vec_owned"] is False
        assert destroyed_audit["rhs_vec_destroyed"] is True
        assert destroyed_audit["wrapper_owned_full_vector_count"] == 0
        assert destroyed_audit["wrapper_owned_full_vector_bytes"] == 0
        assert destroyed_audit["retained_full_vector_count"] == 0
        assert destroyed_audit["retained_full_vector_bytes"] == 0
        assert matrix_context.audit["global_matrix_materialized"] is False
        matrix.destroy()
        action.destroy()


def test_w14_same_rhs_is_deterministic_and_records_two_audits():
    diagonal = np.asarray([1.0 + 0.2j, 2.0 - 0.1j, 0.75 + 0.3j])
    action, matrix, _pc_context, _matrix_context, wrapper = _build(
        diagonal, lambda _self, values: values / diagonal
    )
    rhs = np.asarray([0.5 + 0.25j, -1.0 + 0.5j, 0.75 - 0.25j], dtype=np.complex128)
    try:
        first = wrapper.apply(rhs)
        second = wrapper.apply(rhs)
        records = wrapper.audit["applications"]
        np.testing.assert_array_equal(first, second)
        assert len(records) == 2
        assert records[0]["rhs_sha256"] == records[1]["rhs_sha256"]
        assert records[0]["solution_sha256"] == records[1]["solution_sha256"]
        assert records[0]["gate_pass"] is True
    finally:
        wrapper.destroy()
        matrix.destroy()
        action.destroy()


def test_w14_failed_true_residual_is_audited_before_fail_closed():
    diagonal = np.asarray([1.0 + 0.0j, 2.0 + 0.0j])
    action, matrix, _pc_context, _matrix_context, wrapper = _build(
        diagonal, lambda _self, values: np.asarray([values[0], 0.0j])
    )
    rhs = np.asarray([1.0 + 0.0j, 1.0 + 0.0j], dtype=np.complex128)
    try:
        with pytest.raises(RuntimeError, match="true-residual gate"):
            wrapper.apply(rhs)
        record = wrapper.audit["applications"][-1]
        assert record["finite"] is True
        assert record["gate_pass"] is False
        assert record["true_residual"] > 1.0e-2
        assert record["rhs_sha256"]
        assert record["solution_sha256"]
    finally:
        wrapper.destroy()
        matrix.destroy()
        action.destroy()


def test_w14_destroy_only_releases_owned_rhs_vec():
    diagonal = np.asarray([1.0 + 0.0j, 2.0 + 0.0j])
    action, matrix, _pc_context, matrix_context, wrapper = _build(
        diagonal, lambda _self, values: values / diagonal
    )
    try:
        wrapper.destroy()
        wrapper.destroy()
        audit = wrapper.audit
        assert audit["rhs_vec_owned"] is False
        assert audit["rhs_vec_destroyed"] is True
        assert audit["wrapper_owned_full_vector_count"] == 0
        assert audit["wrapper_owned_full_vector_bytes"] == 0
        assert audit["retained_full_vector_count"] == 0
        assert audit["retained_full_vector_bytes"] == 0
        assert matrix_context.audit["apply_count"] == 0
        source = _vec(np.asarray([1.0 + 0.0j, 0.5 + 0.0j]))
        target = source.duplicate()
        try:
            matrix.mult(source, target)
            np.testing.assert_array_equal(
                target.getArray(readonly=True), diagonal * source.getArray(readonly=True)
            )
        finally:
            target.destroy()
            source.destroy()
    finally:
        wrapper.destroy()
        matrix.destroy()
        action.destroy()
