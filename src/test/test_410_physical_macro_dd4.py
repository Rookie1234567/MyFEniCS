"""Focused production-path contracts for the Review V10 macro candidate."""

import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest
from petsc4py import PETSc

from src.solvers.physical_balanced_coupling import PhysicalBalancedCoupling
from src.solvers.physical_inexact_balance import InexactBalanceLedger
from src.solvers.physical_macro_dd4 import (
    MacroClass,
    MacroLocalVolume,
    _identity_hash_arrays,
    make_macro_pc,
    output_partition_weights,
)
from src.solvers.physical_recursive_coarse import solve_physical_i4


def _resource():
    return {
        "rss_bytes": 0,
        "launch_cap_bytes": 16 * 1024**3,
        "all_status_readable": True,
        "swap_bytes": 0,
    }


def _bind_fixture_identities(local):
    """Bind the same immutable identities required by the production builder."""
    local.mapping_identity_sha256 = _identity_hash_arrays({
        key: local.mapping[key]
        for key in ("dofmap", "slaves", "masters", "coefficients",
                    "offsets", "independent_indices")
    })
    local.cell_class_identity_sha256 = hashlib.sha256(
        json.dumps(list(local.cell_classes), separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def test_macro_local_inventory_cap_is_explicit_per_profile():
    local = MacroLocalVolume.__new__(MacroLocalVolume)
    local.memory_policy = "SYMBOLIC_SIZED_LOCAL_MUMPS_V11"
    local.save = None
    local._resident_bytes = lambda: 2_250_000_000
    local.local_inventory_cap_bytes = 2_684_354_560
    assert local._check_resident_gate("v12_fixture")["resident_cap_bytes"] == 2_684_354_560
    local.local_inventory_cap_bytes = 2 * 1024**3
    with pytest.raises(MemoryError, match="exceeds cap"):
        local._check_resident_gate("old_profile_fixture")


def test_macro_output_weights_are_partition_of_unity_and_reject_incomplete_coverage():
    with pytest.raises(ValueError, match="do not cover"):
        output_partition_weights([np.array([0, 2]), np.array([2, 3])], 4)
    blocks = [np.array([0, 1]), np.array([1, 2]), np.array([2, 3])]
    weights = output_partition_weights(blocks, 4)
    multiplicity = np.array([1, 2, 2, 1])
    assert np.array_equal(weights, 1.0 / multiplicity)
    assembled = np.zeros(4)
    for indices in blocks:
        assembled[indices] += weights[indices]
    assert np.array_equal(assembled, np.ones(4))


def test_macro_representative_selection_uses_nonzero_dtn_rows_and_no_dtn_internal_support():
    local = MacroLocalVolume.__new__(MacroLocalVolume)
    local.local_inventory_cap_bytes = 2 * 1024**3
    local.cell_tags = np.array([1, 1, 2], dtype=np.int32)
    local.blocks = [
        {"seed": (0, 0, 0), "indices": np.array([0]), "support_cells": np.array([0, 2])},
        {"seed": (1, 0, 0), "indices": np.array([1]), "support_cells": np.array([1, 2])},
    ]
    entry = SimpleNamespace(
        coupling_rows=np.array([0, 1]), coupling_values=np.array([0.0 + 0.0j, 1.0 + 0.0j]),
        projection_rows=np.array([0, 1]), projection_values=np.array([0.0 + 0.0j, 2.0 + 0.0j]),
    )
    selected = local._select_representative_blocks(SimpleNamespace(entries=(entry,)))
    assert selected == {
        "material_interface": 0,
        "port_DtN": 1,
        "interior_no_DtN": 0,
    }
    assert local.representative_selection_notes["active_port_row_count"] == 1


def test_macro_block_uses_all_support_rows_and_mpc_master_phase_without_input_mutation():
    phase = np.exp(0.37j)
    local = MacroLocalVolume.__new__(MacroLocalVolume)
    local.local_inventory_cap_bytes = 2 * 1024**3
    local.sample = _resource
    local.marker = lambda *_: None
    local.save = None
    local.levels = {"mesh": SimpleNamespace(comm=PETSc.COMM_SELF)}
    local._new_p4_vector = lambda: PETSc.Vec().createSeq(4, comm=PETSc.COMM_SELF)
    local.dofmap = np.array([[0, 1, 2], [0, 3, 2]], dtype=np.int32)
    local.mapping = {
        "dofmap": local.dofmap,
        "offsets": np.array([0, 0, 1, 1, 1], dtype=np.int64),
        "slaves": np.array([1], dtype=np.int64),
        "masters": np.array([0], dtype=np.int64),
        "coefficients": np.array([phase], dtype=np.complex128),
        "independent_indices": np.array([0, 2, 3], dtype=np.int64),
    }
    matrix0 = np.array(
        [[4 + 0.3j, 1 - 0.2j, 0.7],
         [0.2 + 0.1j, 3.5 - 0.4j, -0.3j],
         [0.5, 0.4j, 2.2 + 0.2j]],
        dtype=np.complex128,
    )
    matrix1 = np.array(
        [[2.5 + 0.2j, -0.4j, 0.3],
         [0.1, 3.1 - 0.1j, 0.6 + 0.2j],
         [-0.2j, 0.5, 1.8 + 0.4j]],
        dtype=np.complex128,
    )
    embedded0_global = np.array(
        [[1.0, 0.0, 0.0, 0.0], [phase, 0.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]],
        dtype=np.complex128,
    )
    embedded1_global = np.array(
        [[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 1.0, 0.0]],
        dtype=np.complex128,
    )
    local.classes = {
        "cell0": MacroClass(
            "cell0", matrix0, np.empty((3, 0), complex), np.empty((3, 0), complex),
            np.empty((3, 0), complex), np.empty((0, 0), complex),
            np.empty((0, 0), complex),
            (np.empty((0, 0), complex), np.empty(0, np.int32)), {},
        ),
        "cell1": MacroClass(
            "cell1", matrix1, np.empty((3, 0), complex), np.empty((3, 0), complex),
            np.empty((3, 0), complex), np.empty((0, 0), complex),
            np.empty((0, 0), complex),
            (np.empty((0, 0), complex), np.empty(0, np.int32)), {},
        ),
    }
    local.cell_classes = ("cell0", "cell1")
    _bind_fixture_identities(local)
    local.cell_expansions = [[
        (np.array([0]), np.array([1.0 + 0j])),
        (np.array([0]), np.array([phase])),
        (np.array([2]), np.array([1.0 + 0j])),
    ], [
        (np.array([0]), np.array([1.0 + 0j])),
        (np.array([3]), np.array([1.0 + 0j])),
        (np.array([2]), np.array([1.0 + 0j])),
    ]]
    local.blocks = [{
        "seed": (0, 0, 0), "seed_cells": (0,), "indices": np.array([0, 2]),
        "support_cells": np.array([0, 1], dtype=np.int32), "volume_terms": 2,
        "dtn_terms": 0,
    }, {
        "seed": (1, 0, 0), "seed_cells": (1,), "indices": np.array([3]),
        "support_cells": np.array([1], dtype=np.int32), "volume_terms": 1,
        "dtn_terms": 0,
    }]
    entry = SimpleNamespace(
        coupling_rows=np.array([0, 2, 3]),
        coupling_values=np.array([0.5 + 0.2j, -0.1j, 0.2]),
        projection_rows=np.array([0, 2, 3]),
        projection_values=np.array([0.3 - 0.1j, 0.4, -0.2j]),
        normalization_h=1.7,
    )
    global_matrix = embedded0_global.conj().T @ matrix0 @ embedded0_global
    global_matrix += embedded1_global.conj().T @ matrix1 @ embedded1_global
    c_global = np.array([0.5 + 0.2j, 0.0, -0.1j, 0.2])
    p_global = np.array([0.3 - 0.1j, 0.0, 0.4, -0.2j])
    global_matrix += np.outer(c_global, p_global) / 1.7

    class FixtureNativeA4:
        def apply(self, source, target):
            target.array[:] = global_matrix @ source.array

    local.add_dtn_terms(SimpleNamespace(entries=(entry,)), native_a4=FixtureNativeA4())

    source = np.array([1.2 + 0.1j, 8.0 - 3j, -0.4 + 0.8j, 0.7 - 0.5j])
    original = source.copy()
    result = local.md_array(source)
    np.testing.assert_array_equal(source, original)
    np.testing.assert_equal(result[1], 0.0)

    embedded0 = np.array([[1.0, 0.0], [phase, 0.0], [0.0, 1.0]], dtype=np.complex128)
    expected0 = embedded0.conj().T @ matrix0 @ embedded0
    embedded1 = np.array([[1.0, 0.0], [0.0, 0.0], [0.0, 1.0]], dtype=np.complex128)
    expected0 += embedded1.conj().T @ matrix1 @ embedded1
    expected0 += np.outer(np.array([0.5 + 0.2j, -0.1j]), np.array([0.3 - 0.1j, 0.4])) / 1.7
    expected1 = np.array([[matrix1[1, 1]]], dtype=np.complex128)
    expected1 += np.array([[-0.2j * 0.2 / 1.7]])
    expected = np.zeros(4, dtype=np.complex128)
    expected[[0, 2]] = np.linalg.solve(expected0, source[[0, 2]])
    expected[3] = np.linalg.solve(expected1, source[[3]])[0]
    try:
        np.testing.assert_allclose(result, expected, rtol=2e-13, atol=2e-13)
        assert local.coverage["input_weighting"] == "none"
        assert np.isfinite(local.output_weights).all()
    finally:
        local.destroy()


def test_balanced_b4_path_is_the_reviewed_formula_and_preserves_input():
    rng = np.random.default_rng(410)
    n, coarse_dim = 8, 3
    A = rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n)) + 7 * np.eye(n)
    P = rng.normal(size=(n, coarse_dim)) + 1j * rng.normal(size=(n, coarse_dim))
    PH = P.conj().T
    coarse_matrix = np.linalg.inv(PH @ A @ P)

    def action(x):
        return A @ x

    def coarse(x):
        return P @ (coarse_matrix @ (PH @ x))

    M = rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n))
    M *= 0.01
    pc = PhysicalBalancedCoupling(action, coarse, lambda x: M @ x, lambda x: PH @ x, route="BAL_H")
    source = rng.normal(size=n) + 1j * rng.normal(size=n)
    original = source.copy()
    result = pc.apply(source)
    coarse_value = coarse(source)
    local = M @ (source - action(coarse_value))
    expected = coarse_value + local - coarse(action(local))
    np.testing.assert_allclose(result, expected, rtol=1e-12, atol=1e-12)
    np.testing.assert_array_equal(source, original)
    assert pc.last_apply_facts["status"] == "BALANCED_ACTION_COMPLETED"


def test_one_c_uses_ledger_eps1_minus_g2_with_independent_operation_scale():
    rng = np.random.default_rng(411)
    n, coarse_dim = 7, 2
    A = rng.normal(size=(n, n)) + 1j * rng.normal(size=(n, n)) + 5 * np.eye(n)
    P = rng.normal(size=(n, coarse_dim)) + 1j * rng.normal(size=(n, coarse_dim))
    PH = P.conj().T
    coarse_matrix = np.linalg.inv(PH @ A @ P)
    packets = []
    ledger = InexactBalanceLedger(
        A.__matmul__, PH.__matmul__, save=lambda *item: packets.append(item),
        every=1, mode="ONE_C",
    )

    def coarse(x):
        g = PH @ x
        y = 0.95 * (coarse_matrix @ g)
        applied = PH @ (A @ (P @ y))
        residual = g - applied
        ledger.record(g, applied, residual, {"status": "finite"})
        return P @ y

    pc = PhysicalBalancedCoupling(
        A.__matmul__, coarse, lambda x: 0.02 * x, PH.__matmul__,
        route="ONE_C", inexact_ledger=ledger,
    )
    source = rng.normal(size=n) + 1j * rng.normal(size=n)
    original = source.copy()
    result = pc.apply(source)
    np.testing.assert_array_equal(source, original)
    facts = pc.last_apply_facts["inexact_balance"]
    assert facts["identity"] == "eps1-g2"
    assert facts["operation_scale"] > 0
    assert facts["actual_audit"] == "PASS"
    assert np.isfinite(result).all()
    assert not packets
    ledger.destroy()


def test_macro_i4_zero_start_and_bounded_truncation_preserve_rhs():
    n = 24
    zero = PETSc.Vec().createSeq(n, comm=PETSc.COMM_SELF)
    zero.set(0)
    try:
        called = []
        result = solve_physical_i4(
            zero,
            lambda value: called.append(True),
            lambda value: called.append(True),
            target=1.0e-4, sample=lambda: None, save=lambda *_: None,
            max_it=4, restart=4, soft_seconds=25.0, hard_seconds=30.0,
            macro_policy=True,
        )
        try:
            assert result["facts"]["status"] == "INNER_ZERO_RHS"
            assert not called
        finally:
            for key in ("solution", "applied", "residual"):
                result[key].destroy()
    finally:
        zero.destroy()

    rhs = PETSc.Vec().createSeq(n, comm=PETSc.COMM_SELF)
    rhs.set(1 + 0.5j)
    original = rhs.array.copy()

    diagonal = np.geomspace(1.0e-2, 3.0, n) * (1.0 + 0.2j)

    def diagonal_action(value):
        result = value.copy()
        result.array[:] = diagonal * value.array
        return result

    def small_pc(value):
        result = value.copy()
        result.scale(0.001)
        return result

    try:
        result = solve_physical_i4(
            rhs, diagonal_action, lambda value: value.copy(),
            target=1.0e-4, sample=lambda: None, save=lambda *_: None,
            max_it=4, restart=4, soft_seconds=25.0, hard_seconds=30.0,
            macro_policy=True,
        )
        try:
            assert result["facts"]["status"] == "INNER_APPROXIMATE_RETURN"
            assert result["facts"]["B4_calls"] <= 4
            assert result["facts"]["final_true_residual"] > 1.0e-4
            np.testing.assert_array_equal(rhs.array, original)
        finally:
            for key in ("solution", "applied", "residual"):
                result[key].destroy()
    finally:
        rhs.destroy()


def test_make_macro_pc_runs_owned_outer_bal_h_with_separate_native_residual_action():
    class IdentityAction:
        def apply(self, source, target):
            target.array[:] = source.array

    class IdentityTransfer:
        coarse_slaves = np.empty(0, dtype=np.int32)

        @staticmethod
        def apply_adjoint(source):
            return source.copy()

        @staticmethod
        def apply_primal(source):
            return source.copy()

    class IdentityPC:
        def __init__(self):
            self.calls = 0

        def apply(self, source):
            self.calls += 1
            return source.copy()

    transfer = IdentityTransfer()
    identity = IdentityAction()
    b4 = IdentityPC()
    h6 = IdentityPC()
    stack = {
        "actions": {"transfers": {(6, 4): transfer}},
        "a4": identity,
        "a4_native": identity,
        "B4": b4,
        "a6": identity,
        "positive": {"h6": h6},
    }
    pc = make_macro_pc(stack, framework="BAL_H", sample=lambda: None, save=lambda *_: None)
    zero = PETSc.Vec().createSeq(12, comm=PETSc.COMM_SELF)
    zero.set(0)
    source = PETSc.Vec().createSeq(12, comm=PETSc.COMM_SELF)
    source.set(1.0 + 0.5j)
    original = source.array.copy()
    try:
        zero_result = pc.apply(zero)
        try:
            assert zero_result.norm() == 0.0
            assert b4.calls == 0
        finally:
            zero_result.destroy()
        result = pc.apply(source)
        try:
            np.testing.assert_allclose(result.array, original, rtol=2e-14, atol=2e-14)
            np.testing.assert_array_equal(source.array, original)
            assert stack["I4"].records[-1]["explicit_uses_separate_action"] is True
            stack["outer_ledger"].audit_last()
            assert stack["outer_ledger"].last["summary"]["actual_audit"] == "PASS"
        finally:
            result.destroy()
    finally:
        zero.destroy()
        source.destroy()
        stack["outer_ledger"].destroy()


def test_macro_add_dtn_single_singular_block_releases_petsc_objects():
    local = MacroLocalVolume.__new__(MacroLocalVolume)
    local.local_inventory_cap_bytes = 2 * 1024**3
    local.sample = _resource
    events = []
    local.marker = lambda name, facts: events.append((name, facts))
    local.save = None
    local.levels = {"mesh": SimpleNamespace(comm=PETSc.COMM_SELF)}
    local.dofmap = np.array([[0]], dtype=np.int32)
    local.mapping = {
        "dofmap": local.dofmap,
        "offsets": np.array([0, 0], dtype=np.int64),
        "slaves": np.empty(0, dtype=np.int64),
        "masters": np.empty(0, dtype=np.int64),
        "coefficients": np.empty(0, dtype=np.complex128),
        "independent_indices": np.array([0], dtype=np.int64),
    }
    local.cell_classes = ("singular",)
    _bind_fixture_identities(local)
    local.cell_expansions = [[
        (np.array([0], dtype=np.int64), np.array([1.0 + 0j], dtype=np.complex128)),
    ]]
    local.classes = {
        "singular": MacroClass(
            "singular", np.zeros((1, 1), dtype=np.complex128),
            np.empty((1, 0), complex), np.empty((1, 0), complex),
            np.empty((1, 0), complex), np.empty((0, 0), complex),
            np.empty((0, 0), complex),
            (np.empty((0, 0), complex), np.empty(0, np.int32)), {},
        ),
    }
    local.blocks = [{
        "seed": (0, 0, 0), "seed_cells": (0,), "indices": np.array([0], dtype=np.int64),
        "support_cells": np.array([0], dtype=np.int32), "volume_terms": 1, "dtn_terms": 0,
    }]
    class ZeroNative:
        @staticmethod
        def apply(source, target):
            target.set(0)

    try:
        with pytest.raises((RuntimeError, ValueError, PETSc.Error), match="(?i)singular|backsolve|zero pivot|factor|nonfinite"):
            local.add_dtn_terms(SimpleNamespace(entries=()), native_a4=ZeroNative())
        assert any(name == "p1_symbolic_complete" for name, _facts in events)
        assert "matrix" not in local.blocks[0]
        assert "factor" not in local.blocks[0]
    finally:
        local.destroy()


def test_make_macro_pc_keeps_finite_legal_i4_truncation():
    class DiagonalAction:
        diagonal = np.geomspace(1.0e-2, 3.0, 12) * (1.0 + 0.2j)

        def apply(self, source, target):
            target.array[:] = self.diagonal * source.array

    class SmallPC:
        def apply(self, source):
            result = source.copy()
            result.scale(1.0e-3)
            return result

    class IdentityTransfer:
        coarse_slaves = np.empty(0, dtype=np.int32)

        @staticmethod
        def apply_adjoint(source):
            return source.copy()

        @staticmethod
        def apply_primal(source):
            return source.copy()

    class IdentitySmoother:
        @staticmethod
        def apply(source):
            return source.copy()

    transfer = IdentityTransfer()
    diagonal = DiagonalAction()
    stack = {
        "actions": {"transfers": {(6, 4): transfer}},
        "a4": diagonal,
        "a4_native": diagonal,
        "B4": SmallPC(),
        "a6": diagonal,
        "positive": {"h6": IdentitySmoother()},
    }
    pc = make_macro_pc(stack, framework="BAL_H", sample=lambda: None, save=lambda *_: None)
    rhs = PETSc.Vec().createSeq(12, comm=PETSc.COMM_SELF)
    rhs.set(1.0 + 0.5j)
    try:
        result = pc.apply(rhs)
        try:
            facts = stack["I4"].records[-1]
            assert facts["status"] == "INNER_APPROXIMATE_RETURN"
            assert facts["legal_direction_count"] > 0
            assert facts["B4_calls"] == 4
            assert np.isfinite(result.norm())
            assert stack["outer_ledger"].last["summary"]["actual_audit"] == "PASS"
        finally:
            result.destroy()
    finally:
        rhs.destroy()
        stack["outer_ledger"].destroy()
