"""Tiny independent checks of the V14 control residuals and reference audit."""

from contextlib import contextmanager
import hashlib
from types import SimpleNamespace

import numpy as np
from petsc4py import PETSc

from src.runners import physical_p4_schur_v14 as controls
from src.test.test_390_physical_interface_schur import _core, _matrix


@contextmanager
def _control_fixture():
    core, volume, values, B, D, H = _core()
    A = values + B @ np.linalg.solve(H, D)
    physical = _matrix(A)
    volume_output = volume.createVecLeft()
    def volume_apply(source):
        volume.mult(source, volume_output)
        return volume_output
    entries = tuple(SimpleNamespace(
        coupling_rows=np.flatnonzero(B[:, j]), coupling_values=B[np.flatnonzero(B[:, j]), j],
        projection_rows=np.flatnonzero(D[j]), projection_values=D[j, np.flatnonzero(D[j])],
        normalization_h=H[j, j],
    ) for j in range(B.shape[1]))
    common = {'p4': {'volume_action': SimpleNamespace(apply=volume_apply),
                     'physical_action': SimpleNamespace(apply=physical.mult),
                     'dtn_action': SimpleNamespace(carrier=SimpleNamespace(entries=entries))},
              'levels': {'spaces': {4: None}}}
    try:
        yield core, common, A, B, D, H
    finally:
        core.destroy()
        volume_output.destroy()
        physical.destroy()
        volume.destroy()


def _vector(values):
    result = PETSc.Vec().createSeq(len(values), comm=PETSc.COMM_SELF)
    result.array[:] = values
    return result


def test_native_A4_is_distinct_from_volume_and_augmented_port_residuals():
    with _control_fixture() as (_, common, A, B, D, H):
        x = np.arange(1, 8, dtype=complex) + 0.4j
        g = A @ x
        alpha = np.linalg.solve(H, D @ x)
        rhs, solution = _vector(g), _vector(x)
        try:
            facts, native, volume, top, port = controls._augmented_residual_arrays(
                common['p4']['volume_action'], common['p4']['physical_action'],
                common['p4']['dtn_action'].carrier, rhs, solution, alpha)
            assert facts['native_A4_relative'] < 1e-14
            assert facts['native_volume_top_relative'] > 1e-3
            np.testing.assert_allclose(volume, -B @ alpha, atol=2e-14)
            assert max(np.linalg.norm(native), np.linalg.norm(top), np.linalg.norm(port)) < 1e-13
            # Altering only the augmented port unknown must not alter native A4x-g.
            changed, *_ = controls._augmented_residual_arrays(
                common['p4']['volume_action'], common['p4']['physical_action'],
                common['p4']['dtn_action'].carrier, rhs, solution, alpha + 1)
            assert changed['native_A4_relative'] == facts['native_A4_relative']
            assert changed['augmented_total_relative'] > 1e-3
        finally:
            rhs.destroy()
            solution.destroy()


def test_q2_port_slice_uses_gamma_rows_not_full_storage_rows(monkeypatch):
    monkeypatch.setattr(controls, '_storage_rhs', lambda _space, values: _vector(values))
    with _control_fixture() as (core, common, A, _B, D, H):
        x = np.arange(1, 8, dtype=complex) + 0.4j
        alpha = np.linalg.solve(H, D @ x)
        interface = np.r_[x[core.partition.gamma_full_indices], alpha]
        solution = _vector(x)
        try:
            facts, *_ = controls._q2_residual_arrays(
                common, {'rhs': A @ x}, solution, interface, core.partition.gamma_rows)
            assert facts['augmented_total_relative'] < 1e-14
            assert facts['native_A4_relative'] < 1e-14
        finally:
            solution.destroy()


def test_reference_elimination_does_not_gate_tiny_block_relative_field_error(tmp_path, monkeypatch):
    saved = []
    monkeypatch.setattr(controls, '_save_packet', lambda _directory, _name, facts, **_kwargs: saved.append(facts))
    with _control_fixture() as (core, common, A, _B, _D, _H):
        y = np.array([1e-20, -1e-20, 2, 3j, 4, 5j, 6], dtype=complex)
        g = A @ y
        reviewed = dict(stem='synthetic', logical_rhs=1, rhs=g, reference_solution=y,
                        reference_A4y=A @ y, g_sha256=hashlib.sha256(g.tobytes()).hexdigest())
        template = _vector(np.zeros(7, dtype=complex))
        try:
            result = controls._q2_reference_elimination_checks(
                SimpleNamespace(directory=tmp_path), core, common, [reviewed], template)
        finally:
            template.destroy()
        assert result['passed']
        facts = result['records'][0]
        assert facts['full_identity_relative'] < 1e-13
        assert facts['max_reference_internal_difference'] > 1e-8
        assert facts['factor_solve_call_delta_elimination']['internal_total'] == 2
        assert facts['factor_solve_call_delta_recovery']['internal_total'] == 2
        assert len(saved) == 1
        assert np.linalg.norm(saved[0]['identity_difference']) / np.linalg.norm(g) < 1e-13
