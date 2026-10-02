"""Staged contract definitions; not a live p4/MPC/quotient qualification.

The small algebra tests are scheduled only after source/ABI admission. They
use the existing V19 dense-cell fixture and preserve complete non-Hermitian
ports/interior RHS. No test has been run in the external staging turn.
"""
from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from petsc4py import PETSc

from src.solvers.p6_cell_condensed_action import P6CellCondensedAction, P6DirectTracePortTerms, P6CellPortTerms
from src.solvers.y_orbit_quotient_condensed import (
    PHYSICAL_MANIFEST, QuotientCondensedBundle, _indices, _sector_inventory,
)
from src.test.test_task39extra_v19_p6_cell_condensed_action import _FakeCondensed, _problem


def _gate_log():
    calls = []
    def gate(name, facts):
        assert facts["matrix_payload_bytes"] >= 0 and facts["workspace_bytes"] >= 0
        calls.append((name, facts))
    return calls, gate


def _sum_contributions(action, gate):
    result = np.zeros((action.reduced_size, action.reduced_size), dtype=np.complex128)
    labels = []
    for rows, columns, values, label in action.iter_reduced_contributions(allocation_gate=gate):
        assert not rows.flags.writeable and not columns.flags.writeable and not values.flags.writeable
        result[np.ix_(rows, columns)] += values
        labels.append(label)
    return result, labels


def test_complete_contributions_match_independent_raw_elimination_and_action():
    condensed, raw, action = _problem()
    condensed._destroyed = False
    calls, gate = _gate_log()
    try:
        actual, labels = _sum_contributions(action, gate)
        inverse = np.linalg.inv(raw["Vii"])
        expected = np.block([
            [raw["Vtt"] - raw["Vti"] @ inverse @ raw["Vit"],
             raw["Bt"] - raw["Vti"] @ inverse @ raw["Bi"]],
            [-(raw["Dt"] - raw["Di"] @ inverse @ raw["Vit"]),
             action._H_p + raw["Di"] @ inverse @ raw["Bi"]],
        ])
        np.testing.assert_allclose(actual, expected, rtol=2e-13, atol=2e-13)
        for vector in (np.array([1+2j, -3+1j, .2-4j, 2-.8j]), np.eye(4, dtype=complex)[:, 1]):
            np.testing.assert_allclose(actual @ vector, action.apply(vector), rtol=2e-13, atol=2e-13)
        assert labels.count("ports/H_original") == 1
        assert labels.count("cell/Hhat_correction/0") == 1
        assert not any(label.endswith("Hhat") for label in labels)
        assert calls and all(facts["global_q_factor_count"] == 0 for _, facts in calls)
    finally:
        action.destroy()


def test_direct_trace_carrier_entries_once_and_dual_sign_without_extra_conjugation():
    condensed, raw, old_action = _problem()
    condensed._destroyed = False
    old_action.destroy()
    direct_C = np.array([2+3j, -1+4j], dtype=complex)
    direct_D = np.array([5-2j, .7+1.2j], dtype=complex)
    action = P6CellCondensedAction(condensed, H_p=np.eye(2, dtype=complex),
        port_terms={0: P6CellPortTerms(raw["Bi"], raw["Di"], np.array([0,1], dtype=PETSc.IntType))},
        direct_trace_terms=(P6DirectTracePortTerms(1, np.array([2,3], dtype=PETSc.IntType), direct_C,
                                                   np.array([2,3], dtype=PETSc.IntType), direct_D),))
    _, gate = _gate_log()
    try:
        matrix, labels = _sum_contributions(action, gate)
        inverse = np.linalg.inv(raw["Vii"])
        expected_C = -raw["Vti"] @ inverse @ raw["Bi"]
        expected_D = -(-raw["Di"] @ inverse @ raw["Vit"])
        expected_C[:, 1] += direct_C
        expected_D[1, :] -= direct_D
        np.testing.assert_allclose(matrix[:2, 2:], expected_C)
        np.testing.assert_allclose(matrix[2:, :2], expected_D)
        assert labels.count("direct/C/port/1") == 1 and labels.count("direct/-D/port/1") == 1
    finally:
        action.destroy()


def test_complex_nonunitary_local_expansion_uses_primal_and_dual():
    condensed, raw, old_action = _problem()
    old_action.destroy()
    condensed._destroyed = False
    # Algebra-only expansion witness, not a qualified geometry/MPC factory.
    E = np.array([[1+1j, .3-.2j], [-.4+.7j, 2-.3j]])
    condensed.trace_constraints.expansion_by_original = {
        original: (np.array([0,1], dtype=PETSc.IntType), E[row])
        for row, original in enumerate((2,3))}
    action = P6CellCondensedAction(condensed, H_p=np.eye(2, dtype=complex),
        port_terms={0: P6CellPortTerms(raw["Bi"], raw["Di"], np.array([0,1], dtype=PETSc.IntType),
                                     Bt=raw["Bt"], Dt=raw["Dt"])})
    _, gate = _gate_log()
    try:
        matrix, _ = _sum_contributions(action, gate)
        inverse = np.linalg.inv(raw["Vii"])
        C = raw["Bt"] - raw["Vti"] @ inverse @ raw["Bi"]
        D = raw["Dt"] - raw["Di"] @ inverse @ raw["Vit"]
        np.testing.assert_allclose(matrix[:2, 2:], E.conj().T @ C)
        np.testing.assert_allclose(matrix[2:, :2], -D @ E)
        assert np.linalg.norm(E.conj().T @ E - np.eye(2)) > .1
    finally:
        action.destroy()


def test_complete_interior_and_nonzero_port_rhs_recovery_remains_existing_path():
    condensed, raw, action = _problem()
    condensed._destroyed = False
    _, gate = _gate_log()
    try:
        S, _ = _sum_contributions(action, gate)
        full_rhs = np.array([1+3j, -2+.7j, .8-1j, 2+.5j])
        port_rhs = np.array([3-2j, -1+.6j])
        reduced_rhs = action.reduce_rhs(full_rhs, port_rhs=port_rhs, rhs_is_mpc_dual=True)
        reduced = np.linalg.solve(S, reduced_rhs)
        recovered = action.recover_storage(reduced, full_rhs=full_rhs)
        full_aug = np.block([[raw["Vii"], raw["Vit"], raw["Bi"]],
                             [raw["Vti"], raw["Vtt"], raw["Bt"]],
                             [-raw["Di"], -raw["Dt"], action._H_p]])
        complete = np.concatenate((recovered, reduced[2:]))
        np.testing.assert_allclose(full_aug @ complete, np.concatenate((full_rhs,port_rhs)),
                                   rtol=2e-12, atol=2e-12)
    finally:
        action.destroy()


def test_gate_denial_stops_before_numeric_contribution():
    condensed, _raw, action = _problem()
    condensed._destroyed = False
    def reject(_name, _facts):
        raise MemoryError("test denial")
    try:
        with pytest.raises(MemoryError, match="test denial"):
            next(action.iter_reduced_contributions(allocation_gate=reject))
    finally:
        action.destroy()


def test_streamed_port_mode_and_destroyed_owner_rejected():
    condensed, _raw, action = _problem()
    condensed._destroyed = False
    _, gate = _gate_log()
    action.port_coupling_mode = "streamed"
    with pytest.raises(ValueError, match="cached"):
        next(action.iter_reduced_contributions(allocation_gate=gate))
    action.destroy()
    with pytest.raises(RuntimeError, match="destroyed"):
        next(action.iter_reduced_contributions(allocation_gate=gate))


@pytest.mark.parametrize("int_type", [np.int32, np.int64])
def test_indices_validate_actual_integer_width_before_cast(int_type):
    result = _indices(np.array([0,2,4], dtype=np.int64), 5, int_type)
    assert result.dtype == np.dtype(int_type) and not result.flags.writeable
    with pytest.raises(ValueError, match="before narrowing"):
        _indices(np.array([0, np.iinfo(int_type).max], dtype=np.uint64), 5, int_type)


@pytest.mark.parametrize("values", [[0,0], [-1,2], [0.,2.], [True,False]])
def test_invalid_indices_rejected(values):
    with pytest.raises(ValueError):
        _indices(values, 5, np.int32)


def _sector(qbase):
    modes = tuple(SimpleNamespace(side=side, m=m, n=n, polarization=p)
                  for side in ("top","bottom") for m in range(-9,10)
                  for n in range(-3,4) for p in ("s","p"))
    indices = np.array([i for i,m in enumerate(modes) if m.n % 2 == qbase])
    local = tuple(modes[i] for i in indices)
    entries = tuple(SimpleNamespace(mode_key=(j,m.side,m.m,m.n,m.polarization), mode_identity={"mode_index":j})
                    for j,m in enumerate(local))
    carrier = SimpleNamespace(entries=entries, physical_generator_manifest_sha256=PHYSICAL_MANIFEST,
                              phase_gauge="boundary_plane")
    bundle = {"modes": local, "mode_sha256": PHYSICAL_MANIFEST,
              "dtn_action": SimpleNamespace(carrier=carrier)}
    return bundle, (modes, tuple({} for _ in modes), PHYSICAL_MANIFEST), indices


@pytest.mark.parametrize("qbase,count", [(0,228),(1,304)])
def test_sector_preserves_original_objects_indices_and_all_aliases(qbase,count):
    bundle, inventory, ids = _sector(qbase)
    got = _sector_inventory(bundle,inventory,ids,qbase,np.int32)
    assert len(got) == count and np.array_equal(got,ids)
    assert np.all([(inventory[0][i].n-qbase)%2 == 0 for i in got])


def test_sector_wrong_order_missing_alias_and_regenerated_object_rejected():
    bundle, inventory, ids = _sector(1)
    for wrong in (ids[::-1], ids[:-1]):
        with pytest.raises(ValueError, match="original order"):
            _sector_inventory(bundle,inventory,wrong,1,np.int32)
    bundle["modes"] = (SimpleNamespace(**vars(bundle["modes"][0])), *bundle["modes"][1:])
    with pytest.raises(ValueError, match="objects"):
        _sector_inventory(bundle,inventory,ids,1,np.int32)


def test_ownership_cleans_action_and_system_once_and_keeps_borrowed_bundle():
    calls=[]
    action=SimpleNamespace(destroy=lambda:calls.append("action"))
    system=SimpleNamespace(destroy=lambda:calls.append("system"))
    borrowed={"owner":"caller"}
    empty=np.array([],dtype=np.int32)
    bundle=QuotientCondensedBundle(borrowed,system,action,empty,empty,empty,empty,empty,0,{})
    bundle.destroy();bundle.destroy()
    assert calls == ["action","system"] and borrowed == {"owner":"caller"}
    with pytest.raises(RuntimeError):bundle.reduce_rhs(empty)


def test_iterator_and_constructor_contain_no_global_matrix_or_factor_calls():
    root=Path(__file__).resolve().parents[1]/"solvers"
    tree=ast.parse((root/"p6_cell_condensed_action.py").read_text())
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=="P6CellCondensedAction")
    method=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=="iter_reduced_contributions")
    calls=[n.func.attr if isinstance(n.func,ast.Attribute) else n.func.id if isinstance(n.func,ast.Name) else ""
           for n in ast.walk(method) if isinstance(n,ast.Call)]
    assert not set(calls).intersection({"lu_solve","lu_factor","splu","solve","create_matrix","createAIJ"})
    adapter=ast.parse((root/"y_orbit_quotient_condensed.py").read_text())
    build=next(n for n in adapter.body if isinstance(n,ast.FunctionDef) and n.name=="build_quotient_condensed")
    call=next(n for n in ast.walk(build) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)
              and n.func.id=="build_unconstrained_assembly_time_condensation")
    flags={k.arg:ast.literal_eval(k.value) for k in call.keywords
           if k.arg in {"materialize_global_matrix","retain_local_schur_for_matrix_free"}}
    assert flags == {"materialize_global_matrix":False,"retain_local_schur_for_matrix_free":True}
