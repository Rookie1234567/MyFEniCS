"""Real FE arithmetic equivalence and low-overhead resource sampling."""
import json
import os
import subprocess
import sys
from types import SimpleNamespace

import numpy as np
import pytest


def test_native_supervisor_keeps_rss_when_pss_is_not_sampled(tmp_path):
    script = """
import sys
from pathlib import Path
from benchmarks.subreaper_watchdog import supervise
result = supervise([sys.executable, '-c', 'import time; time.sleep(.2)'],
                   Path(sys.argv[1]), wall_seconds=10, interval=.05)
assert result['classification'] == 'COMPLETED'
assert result['descendants_cleared']
"""
    subprocess.run([sys.executable, '-c', script, str(tmp_path/'watchdog')], check=True,
                   env=dict(os.environ, PHYSICAL_NATIVE_CAPACITY='balanced_h6_p4_native_13p5'))
    samples = [json.loads(line) for line in (tmp_path/'watchdog/resources.jsonl').read_text().splitlines()]
    assert samples[0]['pss_sampled']
    skipped = [sample for sample in samples if not sample['pss_sampled']]
    assert skipped
    assert all(sample['all_status_readable'] and sample['rss_bytes'] > 0 for sample in samples)
    assert all(sample['pss_bytes'] is None for sample in skipped)


def test_rss_sampling_does_not_require_pss(monkeypatch):
    from benchmarks import task038_full3d_jit_staging as staging
    def forbidden(_pid):
        raise AssertionError('RSS-only sample must not read smaps')
    monkeypatch.setattr(staging, '_pss_bytes', forbidden)
    sample = staging.process_tree_snapshot(os.getpid(), 'test', include_pss=False)
    assert sample['all_status_readable']
    assert sample['rss_bytes'] == sum(p['rss_bytes'] for p in sample['members'])
    assert sample['swap_bytes'] == sum(p['swap_bytes'] for p in sample['members'])
    assert sample['pss_bytes'] is None
    assert not sample['pss_sampled']
    assert not sample['pss_all_readable']


def test_codegen_hook_restored_after_rejection(monkeypatch):
    from ffcx.codegeneration import codegeneration

    from src.solvers.native_p4_jit import row_loop_codegen
    original = lambda *_: ('declaration', 'unexpected implementation')
    monkeypatch.setattr(codegeneration, 'integral_generator', original)
    ir = SimpleNamespace(expression=SimpleNamespace(tensor_shape=[300, 300]))
    with pytest.raises(ValueError, match='loop structure'), row_loop_codegen():
        codegeneration.integral_generator(ir, SimpleNamespace(name='hexahedron'), {})
    assert codegeneration.integral_generator is original


def test_native_p4_matrix_and_warm_cache_are_bitwise_equal(tmp_path):
    import basix.ufl
    import ufl
    from dolfinx import fem, mesh
    from dolfinx.fem import petsc
    from mpi4py import MPI

    from src.solvers.native_p4_jit import compile_rowwise_p4
    domain = mesh.create_unit_cube(MPI.COMM_SELF, 1, 1, 1, cell_type=mesh.CellType.hexahedron)
    domain.geometry.x[:] = domain.geometry.x @ np.array([[8.5, .2, 0], [0, 25/3, .1], [.3, 0, 10.]])
    space = fem.functionspace(domain, basix.ufl.element('N1curl', 'hexahedron', 4))
    u, v = ufl.TrialFunction(space), ufl.TestFunction(space)
    form = (ufl.inner(ufl.curl(u), ufl.curl(v)) -
            (.999002304859 + .00182649365j)**2 * ufl.inner(u, v)) * ufl.dx(metadata={'quadrature_degree': 15})
    options = {'cache_dir': tmp_path, 'cffi_extra_compile_args': ['-O2', '-g0']}
    baseline = fem.form(form, jit_options=options)
    native, audit = compile_rowwise_p4(form, options)
    assert len(audit['generated_integrals']) == 1
    assert not audit['fast_math']
    warm, warm_audit = compile_rowwise_p4(form, options)
    assert warm_audit['cache_reused']
    arrays = []
    for compiled in (baseline, native, warm):
        matrix = petsc.assemble_matrix(compiled)
        try:
            matrix.assemble()
            arrays.append(tuple(a.copy() for a in matrix.getValuesCSR()))
        finally:
            matrix.destroy()
    for candidate in arrays[1:]:
        for old, new in zip(arrays[0], candidate, strict=True):
            np.testing.assert_array_equal(old, new)


@pytest.mark.parametrize('degree', [4, 6])
def test_only_curl_uses_native_codegen_and_preserves_action(tmp_path, degree):
    import basix.ufl
    import ufl
    from dolfinx import fem, mesh
    from mpi4py import MPI

    from src.solvers.fullspace_physical_action import FullspaceSplitVolumeAction
    domain = mesh.create_unit_cube(MPI.COMM_SELF, 1, 1, 1, cell_type=mesh.CellType.hexahedron)
    space = fem.functionspace(domain, basix.ufl.element('N1curl', 'hexahedron', degree))
    u, v = ufl.TrialFunction(space), ufl.TestFunction(space)
    dx = ufl.dx(metadata={'quadrature_degree': 15})
    curl = ufl.inner(ufl.curl(u), ufl.curl(v))*dx
    mass = -(1+.01j)*ufl.inner(u, v)*dx
    options = {'cache_dir': tmp_path, 'cffi_extra_compile_args': ['-O2', '-g0']}
    actions = []
    source = None
    try:
        actions.append(FullspaceSplitVolumeAction(curl, mass, space, jit_options=options))
        actions.append(FullspaceSplitVolumeAction(curl, mass, space, jit_options=options,
            native_curl_codegen=True))
        from dolfinx.la.petsc import create_vector
        source = create_vector([(space.dofmap.index_map, space.dofmap.index_map_bs)])
        rng = np.random.default_rng(3901)
        for _ in range(3):
            source.array[:] = rng.normal(size=source.getLocalSize()) + 1j*rng.normal(size=source.getLocalSize())
            old = actions[0].apply(source).array.copy()
            new = actions[1].apply(source).array.copy()
            np.testing.assert_array_equal(old, new)
        assert actions[1]._mass_action._jit_options == options
    finally:
        if source is not None:
            source.destroy()
        for action in reversed(actions):
            action.destroy()
