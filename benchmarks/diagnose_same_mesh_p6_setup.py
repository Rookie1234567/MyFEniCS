"""Two-cell development timing probe; never returns a solver diagonal.

Existing setup runners construct the entire S6 bundle and cannot bound the
cell loop. This research entry only prepares data and calls existing helpers.
Run once under benchmarks.subreaper_watchdog with a new empty XDG cache.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    args = parser.parse_args()
    directory = args.directory.resolve()
    directory.mkdir(exist_ok=False)
    cache = Path(os.environ['XDG_CACHE_HOME'])
    if not cache.is_dir() or any(cache.iterdir()):
        raise RuntimeError('a new empty cache is required before FE imports')
    root = Path(__file__).resolve().parents[1]
    source = subprocess.check_output(
        ['git', '--git-dir=.git-codex', '--work-tree=.', 'rev-parse', 'HEAD'],
        text=True, cwd=root).strip()
    assert source == '39448e6a0e5705ad2c40b4bf7733ce2249e35a84'
    dirty = subprocess.check_output(
        ['git', '--git-dir=.git-codex', '--work-tree=.', 'status', '--porcelain'],
        text=True, cwd=root)
    started = time.perf_counter()
    stream = (directory / 'stages.jsonl').open('x')

    def emit(event, **facts):
        stream.write(json.dumps(dict(event=event, elapsed=time.perf_counter()-started,
                                     **facts), allow_nan=False) + '\n')
        stream.flush()
        os.fsync(stream.fileno())

    @contextmanager
    def timed(name, **facts):
        emit('start', name=name, **facts)
        before = time.perf_counter()
        try:
            yield
        finally:
            emit('end', name=name, seconds=time.perf_counter()-before, **facts)

    def digest(array):
        return hashlib.sha256(array.tobytes()).hexdigest()

    input_path = root / 'input/task39extra/original_13p5nm_p6h10.dat'
    emit('identity', classification='development_diagnostic', source_sha=source,
         dirty_state=dirty, script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
         input_sha256=hashlib.sha256(input_path.read_bytes()).hexdigest(),
         cache=str(cache), cache_initially_empty=True, pid=os.getpid(),
         command=sys.argv, threads={k: os.environ.get(k) for k in
         ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS')})
    with timed('imports_and_input'):
        import numpy as np
        from dolfinx import fem
        from mpi4py import MPI
        from petsc4py import PETSc
        from src.io import load_and_resolve
        from src.io.input_validation import simulation_config_3d_from_normalized
        from src.solvers import fullspace_mpc_action as action_module
        from src.solvers import fullspace_same_mesh_hcurl_pmg_p6 as diag
        from src.solvers.fullspace_same_mesh_hcurl_pmg_global import (
            _build_same_mesh_levels, same_mesh_positive_form,
        )
        from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
        assert os.environ['_MYFENICS_WSL_QUALIFIED_ACTIVATION'] == '1'
        assert Path(sys.prefix).resolve() == (root / '.venv').resolve()
        assert PETSc.ScalarType is np.complex128 and MPI.COMM_WORLD.size == 1
        specification = load_and_resolve(input_path)
        payload = specification.as_jsonable()
        cfg = simulation_config_3d_from_normalized(payload)
        (directory / 'resolved_config.json').write_text(json.dumps(payload, allow_nan=False))
        emit('physical_identity', physical_model_sha256=specification.physical_model_sha256)
    with timed('shared_mesh_spaces_mpc'):
        levels = _build_same_mesh_levels(cfg, MPI.COMM_WORLD, (6, 4, 3, 2, 1))
    space, mpc = levels['spaces'][6], levels['floquets'][6].mpc
    form = same_mesh_positive_form(space, curl_coefficient=levels['mu'],
                                  mass_coefficient=levels['mass'])
    original_compile = action_module._compile_action_form

    def measured_compile(*args, **kwargs):
        with timed('action_compile'):
            return original_compile(*args, **kwargs)

    action_module._compile_action_form = measured_compile
    try:
        with timed('action_constructor_total'):
            action = action_module.build_fullspace_mpc_form_action(
                form, space, mpc=mpc, jit_options=SAME_MESH_JIT_OPTIONS)
    finally:
        action_module._compile_action_form = original_compile
    with timed('bilinear_compile'):
        compiled = fem.form(form, jit_options=dict(SAME_MESH_JIT_OPTIONS))
    with timed('diagonal_common_preparation'):
        work_space = mpc.function_space
        mesh = work_space.mesh
        index_map = work_space.dofmap.index_map
        storage = int(index_map.size_local + index_map.num_ghosts)
        element0, element1 = [s.element for s in compiled.function_spaces]
        dimension = int(element0.space_dimension)
        slaves, mask, targets, expansion = diag._cell_expansion_workspace(mpc, storage, dimension)
        mesh.topology.create_entity_permutations()
        permutations = np.asarray(mesh.topology.get_cell_permutation_info(), dtype=np.uint32)
        count = int(mesh.topology.index_map(mesh.topology.dim).size_local)
        geometry_map = np.asarray(mesh.geometry.dofmap)
        geometry = np.asarray(mesh.geometry.x)
        kernel = diag._cell_kernel(compiled, count)
        packed = fem.pack_coefficients(compiled)
        constants = np.ascontiguousarray(np.asarray(fem.pack_constants(compiled), dtype=np.complex128)).reshape(-1)
        tensor = np.zeros((dimension, dimension), dtype=np.complex128)
        scratch = np.empty(tensor.size, dtype=np.float64)
        coordinates = np.empty(int(geometry_map.shape[1])*3, dtype=np.float64)
        local_diagonal = np.zeros(storage, dtype=np.complex128)
    with timed('select_cells_metadata'):
        selected = {}
        for cell in range(count):
            dofs = np.asarray(work_space.dofmap.cell_dofs(cell), dtype=np.int32)
            kind = 'periodic_slave' if np.any(mask[dofs]) else 'ordinary'
            selected.setdefault(kind, cell)
        if set(selected) != {'ordinary', 'periodic_slave'}:
            raise RuntimeError(f'missing requested cell category: {selected}')
    emit('mesh_identity', owned_cells=count, dimension=dimension, storage=storage,
         slave_count=int(slaves.size), geometry_sha256=digest(geometry),
         geometry_dofmap_sha256=digest(geometry_map), constants_sha256=digest(constants))
    for kind in ('ordinary', 'periodic_slave'):
        cell = selected[kind]
        facts = dict(cell=cell, kind=kind)
        with timed('cell_data', **facts):
            dofs = np.asarray(work_space.dofmap.cell_dofs(cell), dtype=np.int32)
            coordinates[:] = np.asarray(geometry[geometry_map[cell]], dtype=np.float64).reshape(-1)
            coefficients = diag._packed_cell_coefficients(packed, cell, count)
        emit('cell_identity', **facts, permutation=int(permutations[cell]),
             dimension=dimension, slave_count=int(np.count_nonzero(mask[dofs])),
             geometry_sha256=digest(coordinates), coefficients_sha256=digest(coefficients),
             coefficients=[[float(v.real), float(v.imag)] for v in coefficients],
             needs_orientation=bool(element0.needs_dof_transformations))
        with timed('cell_tensor', **facts):
            diag._kernel_cell_tensor(compiled, kernel, coordinates, coefficients, constants, tensor)
        with timed('orientation_row', **facts):
            diag._apply_standard_row_transform(element0, tensor, int(permutations[cell]), scratch)
        with timed('orientation_right', **facts):
            diag._apply_transpose_right_transform(element1, tensor, int(permutations[cell]), scratch)
        with timed('mpc_expansion', **facts):
            diag._fill_cell_expansion(dofs, mpc, storage, mask, targets, expansion)
        local_diagonal.fill(0)
        with timed('diagonal_accumulation', **facts):
            diag.accumulate_constrained_local_diagonal(tensor, targets, expansion, local_diagonal)
        finite = bool(np.all(np.isfinite(tensor)) and np.all(np.isfinite(local_diagonal)))
        emit('cell_result', **facts, finite=finite, links=int(np.count_nonzero(targets >= 0)),
             max_links=int(np.max(np.count_nonzero(targets >= 0, axis=1))),
             tensor_sha256=digest(tensor), partial_diagonal_sha256=digest(local_diagonal))
        if not finite:
            raise RuntimeError('nonfinite local diagnostic result')
    action.destroy()
    emit('completed', classification='MEASURED_DIAGNOSTIC_ONLY', official_result=None)
    stream.close()


if __name__ == '__main__':
    main()
