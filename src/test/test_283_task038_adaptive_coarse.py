"""Focused algebra tests for the D2 adaptive coarse data core."""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest
from mpi4py import MPI
from petsc4py import PETSc

from src.solvers.fullspace_adaptive_coarse import FullspaceAdaptiveCoarse


class _MockBasis:
    def __init__(self, values: np.ndarray):
        self._z = np.asarray(values, dtype=np.complex128)
        self._z.flags.writeable = False
        self.comm = MPI.COMM_WORLD
        self._audit = {"construction_workspace_released": True}
        self.build_calls = 0

    def build(self):
        self.build_calls += 1
        raise AssertionError("adaptive coarse must not rebuild the basis")

    @property
    def columns(self) -> np.ndarray:
        view = self._z.view()
        view.flags.writeable = False
        return view

    @property
    def audit(self):
        return self._audit


class _ArrayPhysicalAction:
    def __init__(self, array: np.ndarray):
        self.array = np.asarray(array, dtype=np.complex128)
        self.apply_count = 0

    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        target.getArray()[:] = self.array @ source.getArray(readonly=True)
        self.apply_count += 1


class _NonDeterministicPhysicalAction(_ArrayPhysicalAction):
    def apply(self, source: PETSc.Vec, target: PETSc.Vec) -> None:
        super().apply(source, target)
        target.getArray()[:] += self.apply_count * 1.0e-15


def _template_factory(size: int):
    template = PETSc.Vec().createSeq(size, comm=MPI.COMM_WORLD)
    return template, template.duplicate


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="synthetic coarse algebra uses one local PETSc ownership range",
)
def test_adaptive_coarse_action_repeat_eigen_algebra_and_lifecycle():
    z = np.eye(4, dtype=np.complex128)
    action_array = np.asarray(
        [
            [2.0 + 0.3j, 1.0 + 0.2j, 0.1, 0.0],
            [0.4, 3.0 - 0.1j, 0.5j, 0.2],
            [0.0, 0.6, 1.5 + 0.4j, 0.3],
            [0.2j, 0.0, 0.7, 2.2],
        ],
        dtype=np.complex128,
    )
    basis = _MockBasis(z)
    action = _ArrayPhysicalAction(action_array)
    template, factory = _template_factory(4)
    coarse = FullspaceAdaptiveCoarse(basis, action, factory)
    try:
        coarse.build()
        assert np.shares_memory(coarse.z, basis.columns)
        assert np.shares_memory(coarse.z, basis._z)
        assert np.array_equal(coarse.az, action_array @ z)
        expected_e = z.conj().T @ action_array @ z
        assert np.array_equal(coarse.e, expected_e)
        assert action.apply_count == 2 * z.shape[1] + 1
        audit = coarse.audit
        assert audit["az_repeat_exact"] is True
        assert all(audit["az_repeat_exact_by_column"])
        assert audit["z_orthogonality_defect"] <= 1.0e-10
        assert audit["az_repeat_relative_frobenius"] <= 1.0e-11
        assert audit["physical_consistency_relative"] <= 1.0e-11
        assert audit["e_condition_number"] < 1.0e12
        assert audit["e_hermitian_relative_defect"] > 0.0
        assert audit["numeric_allgather"] is False
        assert (
            audit["small_numeric_collective"]
            == "scalars_and_r_by_r_allreduce_only"
        )
        for name in (
            "retained_z_bytes",
            "retained_az_bytes",
            "retained_e_bytes",
            "retained_metadata_bytes",
            "work_vector_bytes",
        ):
            stats = audit[name]
            assert stats["local"] == stats["global_sum"]
            assert stats["local"] == stats["global_max"]
        retained = sum(
            audit[name]["global_sum"]
            for name in (
                "retained_z_bytes",
                "retained_az_bytes",
                "retained_e_bytes",
                "retained_metadata_bytes",
                "work_vector_bytes",
            )
        )
        assert retained == audit["retained_coarse_bytes_global_sum"]
        prefixes = coarse._prefix_audits_for((1, 2, 3))
        assert tuple(item["prefix"] for item in prefixes) == (1, 2, 3)
        assert action.apply_count == 2 * z.shape[1] + 1 + 3
        assert audit["physical_action_apply_count"] == action.apply_count
        assert basis.build_calls == 0
        assert tuple(item["prefix"] for item in audit["prefix_audits"]) == (
            1,
            2,
            3,
            4,
        )
        for item in prefixes:
            assert item["finite"] is True
            assert item["az_repeat_exact"] is True
            assert item["az_repeat_relative_frobenius"] <= 1.0e-11
            assert item["e_prefix_leading_relative"] <= 1.0e-12
            assert item["e_prefix_leading_exact"] is True
            assert item["e_condition_number"] < 1.0e12
            assert item["physical_consistency_relative"] <= 1.0e-11
            prefix = item["prefix"]
            assert item["logical_prefix_bytes_provenance"] == (
                "derived_exact_array_size"
            )
            assert item["logical_prefix_z_bytes"]["local"] == 4 * prefix * 16
            assert item["logical_prefix_az_bytes"]["local"] == 4 * prefix * 16
            assert item["logical_prefix_e_bytes"]["local"] == prefix * prefix * 16
            assert item["resident_z_bytes"]["local"] == 4 * 4 * 16
            assert item["resident_az_bytes"]["local"] == 4 * 4 * 16
            assert item["resident_e_bytes"]["local"] == 4 * 4 * 16
            assert item["resident_metadata_bytes"]["local"] == 16
            assert item["resident_work_vector_bytes"]["local"] == 3 * 4 * 16
            assert item["resident_bytes_provenance"] == (
                "exact_current_retained_objects"
            )
            resident_prefix = sum(
                item[name]["global_sum"]
                for name in (
                    "resident_z_bytes",
                    "resident_az_bytes",
                    "resident_e_bytes",
                    "resident_metadata_bytes",
                    "resident_work_vector_bytes",
                )
            )
            assert resident_prefix == item[
                "resident_coarse_total_global_sum"
            ]
            assert resident_prefix == item["retained_coarse_bytes_global_sum"]
            assert item["retained_z_bytes"] == item["resident_z_bytes"]
            assert item["retained_az_bytes"] == item["resident_az_bytes"]
        assert coarse.prefix_audit() == ()
    finally:
        coarse.destroy()
        coarse.destroy()
        template.destroy()


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="synthetic coarse repeat test uses one local PETSc ownership range",
)
def test_adaptive_coarse_repeat_gate_rejects_nondeterministic_action():
    template, factory = _template_factory(2)
    coarse = FullspaceAdaptiveCoarse(
        _MockBasis(np.eye(2, dtype=np.complex128)),
        _NonDeterministicPhysicalAction(np.eye(2, dtype=np.complex128)),
        factory,
    )
    try:
        with pytest.raises(RuntimeError, match="repeat exact gate"):
            coarse.build()
    finally:
        coarse.destroy()
        template.destroy()


def test_adaptive_coarse_requires_released_basis_workspace():
    basis = _MockBasis(np.eye(2, dtype=np.complex128))
    basis._audit["construction_workspace_released"] = False
    with pytest.raises(RuntimeError, match="released basis workspace"):
        FullspaceAdaptiveCoarse(basis, object(), lambda: None)


@pytest.mark.skipif(
    MPI.COMM_WORLD.size != 1,
    reason="synthetic coarse condition test uses one local PETSc ownership range",
)
def test_adaptive_coarse_condition_gate_fails_without_regularization():
    z = np.eye(2, dtype=np.complex128)
    action = _ArrayPhysicalAction(np.diag([1.0, 0.0]).astype(np.complex128))
    template, factory = _template_factory(2)
    coarse = FullspaceAdaptiveCoarse(_MockBasis(z), action, factory)
    try:
        with pytest.raises(RuntimeError, match="condition gate.*value=.*limit"):
            coarse.build()
    finally:
        coarse.destroy()
        template.destroy()


def test_adaptive_coarse_ast_forbids_full_matrix_and_basis_copies():
    path = Path(__file__).parents[1] / "solvers/fullspace_adaptive_coarse.py"
    text = path.read_text(encoding="utf-8")
    tree = ast.parse(text)
    forbidden = {"createAIJ", "assemble_matrix", "allgather", "column_stack"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            assert node.func.attr not in forbidden
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in forbidden
    assert "small_numeric_collective" in text
    assert "numeric_allgather" in text
    assert "np.empty_like(self._z" in text
    assert ".copy(" not in text
