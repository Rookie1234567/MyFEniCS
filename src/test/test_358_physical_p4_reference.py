"""A2R block algebra, fail-closed budgets, real MPC/action and reuse checks."""
import os
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
from petsc4py import PETSc
from mpi4py import MPI
from src.solvers.fullspace_p4_reference import (
    augment_physical_volume, PhysicalP4Reference, ReferenceResourceBlocked, build_reference_matrix,
    reference_budget,
)


def matrix(a):
    m = PETSc.Mat().createAIJ(a.shape, nnz=a.shape[1], comm=PETSc.COMM_SELF)
    m.setValues(range(a.shape[0]), range(a.shape[1]), a); m.assemble()
    return m


def test_complex_augmentation_and_symbolic_budget_blocks_numeric():
    v = np.array([[3, 1j], [.2, 2]], complex)
    b, d, h = np.array([1+2j, .3j]), np.array([.2-.5j, 1j]), 2.
    carrier = SimpleNamespace(global_rows=2, entries=[SimpleNamespace(
        coupling_rows=np.array([0,1],np.int32), coupling_values=b,
        projection_rows=np.array([0,1],np.int32), projection_values=d, normalization_h=h)])
    volume = matrix(v)
    aug, facts = augment_physical_volume(volume, carrier)
    try:
        a = aug.getValues(range(3), range(3))
        rhs = np.array([1j, 2+1j])
        observed = np.linalg.solve(a, np.r_[rhs, 0])[:2]
        np.testing.assert_allclose(observed, np.linalg.solve(v+np.outer(b,d)/h, rhs), atol=1e-13)
        events = []
        markers = []
        class Factor:
            def __init__(self, _): pass
            def symbolic(self, _): events.append('symbolic')
            def info(self, _): return {'infog': {'16': 100}}
            def numeric(self, _): events.append('numeric')
            def destroy(self): events.append('destroy')
        with pytest.raises(ReferenceResourceBlocked):
            PhysicalP4Reference(aug, None, [], fine_rows=2,
                sample=lambda:dict(rss_bytes=100, launch_cap_bytes=1000,
                                   all_status_readable=True, swap_bytes=0),
                marker=lambda name, facts: markers.append((name,facts)), factor_factory=Factor)
        assert events == ['symbolic','destroy']
        budget = next(f for n,f in markers if n=='reference_budget_evaluated')
        assert budget['numeric_called'] is False and budget['predicted_peak_bytes'] > budget['launch_cap_bytes']
    finally:
        aug.destroy(); volume.destroy()


def test_reference_dat_is_opt_in_and_physics_unchanged():
    from src.io import load_and_resolve
    from src.io.physical_intermediate_profile import REFERENCE_PROFILE, profile_facts
    original = load_and_resolve('input/task39extra/original_13p5nm_p6h10.dat')
    reference = load_and_resolve('input/task39extra/original_13p5nm_p6h10_p4_reference.dat')
    assert reference.physical_model_sha256 == original.physical_model_sha256
    assert reference.input_sha256 != original.input_sha256
    assert reference.as_jsonable()['derived']['physical_intermediate_profile'] == profile_facts(REFERENCE_PROFILE)
    assert profile_facts(REFERENCE_PROFILE)['outer'] == profile_facts()['outer']


def test_measured_admission_reaches_real_mumps_numeric_despite_large_forecast():
    from src.solvers.fullspace_v17_p3_oracle import _MumpsFactor

    class LargeForecastFactor(_MumpsFactor):
        def info(self, *args, **kwargs):
            info = super().info(*args, **kwargs)
            # Reproduce the stopped run's forecast without a large allocation.
            info['infog']['16'] = 1_222_577
            return info

        def set_memory_limit_mb(self, megabytes):
            raise AssertionError('measured mode must not install a forecast-derived MUMPS limit')

    a = np.array([[3, 1j], [.2, 2]], complex)
    mat = matrix(a)
    factor = b = x = None
    resources = dict(rss_bytes=1_000_000, launch_cap_bytes=1024**3,
                     planning_cap_bytes=500_000, all_status_readable=True,
                     swap_bytes=0, reference_memory_admission='measured_rss')
    try:
        factor = PhysicalP4Reference(mat, None, [], fine_rows=2,
            sample=lambda: resources, marker=lambda *_: None, factor_factory=LargeForecastFactor)
        budget = factor.audit['budget']
        assert budget['predicted_peak_bytes'] > budget['launch_cap_bytes']
        assert budget['launch_cap_bytes'] == resources['launch_cap_bytes']
        assert budget['predicted_peak_is_diagnostic_only']
        assert factor.audit['numeric_calls'] == 1
        assert factor.factor.symbolic_memory_settings()['icntl']['23'] == 0
        b, x = mat.createVecRight(), mat.createVecRight()
        b.array[:] = [1j, 2+1j]
        factor.factor.solve_repeated(b, x)
        assert np.linalg.norm(a @ x.array - b.array) / np.linalg.norm(b.array) < 1e-12
    finally:
        if x is not None: x.destroy()
        if b is not None: b.destroy()
        if factor is not None: factor.destroy()
        mat.destroy()


def test_measured_admission_records_unavailable_infog16_without_blocking():
    resources = dict(rss_bytes=222_001_508_352, launch_cap_bytes=1_300_000_000_000,
                     planning_cap_bytes=1_300_000_000_000, all_status_readable=True,
                     swap_bytes=0, swap_policy='observe_only',
                     resource_stop_policy='measured_tree_rss_only_v3',
                     reference_memory_admission='measured_rss')
    markers = []
    facts = reference_budget(
        resources, {'infog': {'16': 0}}, 48_545_448_448,
        marker=lambda name, payload: markers.append((name, payload)))
    assert facts['prediction_status'] == 'unavailable'
    assert facts['predicted_peak_bytes'] is None
    assert facts['classification'] == 'measured_rss_admission_prediction_unavailable'
    assert next(payload for name, payload in markers if name == 'reference_budget_evaluated')['numeric_called'] is False


def test_legacy_measured_admission_still_blocks_unavailable_infog16():
    resources = dict(rss_bytes=222_001_508_352, launch_cap_bytes=1_300_000_000_000,
                     planning_cap_bytes=1_300_000_000_000, all_status_readable=True,
                     swap_bytes=0, reference_memory_admission='measured_rss')
    with pytest.raises(ReferenceResourceBlocked, match='nonpositive/unavailable'):
        reference_budget(resources, {'infog': {'16': 0}}, 48_545_448_448)


@pytest.mark.parametrize('override', [
    {'rss_bytes': 1_537_500_000_000},
    {'rss_bytes': 1_537_500_000_001},
    {'swap_bytes': 4096},
    {'all_status_readable': False},
])
def test_measured_admission_keeps_real_resource_stops(override):
    resources = dict(rss_bytes=222_001_508_352, launch_cap_bytes=1_537_500_000_000,
                     all_status_readable=True, swap_bytes=0,
                     reference_memory_admission='measured_rss')
    resources.update(override)
    with pytest.raises(ReferenceResourceBlocked):
        reference_budget(resources, {'infog': {'16': 1_222_577}}, 48_545_448_448)


def test_reference_release_and_pc_provenance():
    from src.solvers.fullspace_physical_intermediate_runtime import release_physical_intermediate_solver_stack
    from src.solvers.fullspace_physical_intermediate import PhysicalIntermediatePreconditioner
    events = []
    middle = SimpleNamespace(solver_identity='exact_augmented_A4_reference',
                             destroy=lambda: events.append('factor'))
    pc = PhysicalIntermediatePreconditioner(None, None, None, middle)
    assert pc.audit['method'] == 'exact_augmented_A4_reference'
    assert 'sigma' not in pc.audit
    fine = object()
    bundle = dict(pc=pc, middle=middle, reference_factor=middle, fine=fine,
                  reference_matrix=SimpleNamespace(destroy=lambda:events.append('matrix')))
    release_physical_intermediate_solver_stack(bundle)
    release_physical_intermediate_solver_stack(bundle)
    assert events == ['factor','matrix'] and bundle['fine'] is fine


def test_tiny_p4_mpc_augmented_action_and_repeated_reference():
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import build_same_mesh_physical_action, destroy_same_mesh_physical_action
    from src.solvers.fullspace_physical_intermediate_runtime import fine_volume_quadrature_metadata, level_vector
    from src.solvers.fullspace_physical_intermediate import apply_owned
    from benchmarks.subreaper_watchdog import memory_envelope
    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
    cfg = simulation_config_3d_from_normalized(load_and_resolve('input/task39extra/original_13p5nm_p6h10.dat').as_jsonable())
    cfg.mesh_target_size = 50.
    levels = _build_same_mesh_levels(cfg, MPI.COMM_WORLD, (6,4))
    quadrature, _ = fine_volume_quadrature_metadata(levels, cfg)
    native = build_same_mesh_physical_action(levels, cfg, 4, volume_quadrature_metadata=quadrature)
    def sample():
        result = process_tree_snapshot(os.getppid(), 'component', None)
        result['launch_cap_bytes'] = memory_envelope()['launch_cap_bytes']
        return result
    events = []
    marker = lambda name, facts: events.append((name, facts))
    aug = factor = rhs = None
    try:
        aug, facts = build_reference_matrix(levels, cfg, native, quadrature, marker=marker, sample=sample)
        rhs = level_vector(levels, 4)
        slaves = np.asarray(levels['floquets'][4].mpc.slaves, dtype=np.int32)
        rhs.array[:] = np.random.default_rng(358).normal(size=rhs.getSize()) + 1j
        rhs.array[slaves] = 0
        saved = rhs.array.copy()
        carrier = native['dtn_action'].carrier
        x, y = aug.createVecRight(), aug.createVecRight()
        try:
            x.set(0); x.array[:rhs.getSize()] = rhs.array
            for j,e in enumerate(carrier.entries):
                x.array[rhs.getSize()+j] = np.dot(e.projection_values, rhs.array[e.projection_rows])/e.normalization_h
            aug.mult(x,y)
            action = apply_owned(native['physical_action'], rhs)
            try:
                error = np.linalg.norm(y.array[:rhs.getSize()]-action.array)/action.norm()
                assert error < 1e-11
                assert np.linalg.norm(y.array[rhs.getSize():]) < 1e-10
            finally: action.destroy()
        finally: x.destroy(); y.destroy()
        factor = PhysicalP4Reference(aug, native['physical_action'], slaves,
            fine_rows=levels['spaces'][6].dofmap.index_map.size_global, sample=sample, marker=marker)
        first_solution = None
        repeat_relative = None
        for scale in (1., 1., 1j):
            rhs.array[:] = scale*saved
            result = factor.solve_intermediate(rhs)
            assert result['final_true_residual'] <= 1e-10
            assert np.all(np.isfinite(result['final_solution'].array))
            np.testing.assert_array_equal(result['final_solution'].array[slaves],0)
            np.testing.assert_array_equal(rhs.array, scale*saved)
            if first_solution is None:
                first_solution = result['final_solution'].array.copy()
            elif scale == 1.:
                repeat_relative = np.linalg.norm(result['final_solution'].array-first_solution)/np.linalg.norm(first_solution)
                assert repeat_relative <= 1e-12
            result['final_solution'].destroy()
        class WrongAction:
            def apply_into(self, source, target): target.set(0)
        factor.action = WrongAction()
        with pytest.raises(RuntimeError, match='original A4'):
            factor.solve_intermediate(rhs)
        rhs.array[slaves[0]] = 1
        with pytest.raises(ValueError, match='legal'):
            factor.solve_intermediate(rhs)
        assert factor.audit['symbolic_calls'] == factor.audit['numeric_calls'] == 1
        assert factor.audit['solve_calls'] == 4
        failed = [f for n,f in events if n=='reference_residual_evaluated'][-1]
        assert failed['residual_gate_passed'] is False and failed['final_true_residual'] > 1e-10
        assert failed['factor_solve_calls'] == failed['explicit_action_count'] == 1
        print('tiny p4 augmented/native relative',error,'same RHS repeat relative',repeat_relative,
              'reference repeated PASS',flush=True)
    finally:
        if factor is not None: factor.destroy()
        if rhs is not None: rhs.destroy()
        if aug is not None: aug.destroy()
        destroy_same_mesh_physical_action(native)
