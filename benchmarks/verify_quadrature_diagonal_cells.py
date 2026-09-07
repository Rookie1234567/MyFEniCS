"""Three original-mesh cells against the unchanged dense oracle, watchdog only."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', type=Path, required=True)
    directory = parser.parse_args().directory
    directory.mkdir(exist_ok=False)
    stream = (directory/'cells.jsonl').open('x')

    def emit(**record):
        stream.write(json.dumps(record, allow_nan=False)+'\n'); stream.flush(); os.fsync(stream.fileno())

    @contextmanager
    def timed(name, **facts):
        emit(event='start', name=name, **facts)
        start = time.perf_counter()
        yield
        emit(event='end', name=name, seconds=time.perf_counter()-start, **facts)

    root = Path(__file__).resolve().parents[1]
    files = ['src/solvers/fullspace_quadrature_diagonal.py', str(Path(__file__).relative_to(root))]
    emit(event='identity', head=subprocess.check_output(['git','--git-dir=.git-codex','--work-tree=.',
        'rev-parse','HEAD'],text=True).strip(), dirty=subprocess.check_output(['git','--git-dir=.git-codex',
        '--work-tree=.','status','--porcelain'],text=True), files={p:hashlib.sha256((root/p).read_bytes()).hexdigest()
        for p in files}, cache=os.environ['XDG_CACHE_HOME'], cache_initially_empty=not any(Path(os.environ['XDG_CACHE_HOME']).iterdir()))
    import numpy as np
    from dolfinx import fem
    from mpi4py import MPI
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels, same_mesh_positive_form
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    from src.solvers import fullspace_same_mesh_hcurl_pmg_p6 as old
    from src.solvers.fullspace_quadrature_diagonal import PositiveCellBasis, accumulate_basis_energy
    spec = load_and_resolve(root/'input/task39extra/original_13p5nm_p6h10.dat')
    emit(event='input', input_sha=spec.input_sha256, physical_sha=spec.physical_model_sha256)
    assert MPI.COMM_WORLD.size == 1
    with timed('mesh_space_mpc'):
        levels = _build_same_mesh_levels(simulation_config_3d_from_normalized(spec.as_jsonable()), MPI.COMM_WORLD, (6,))
    space, mpc = levels['spaces'][6], levels['floquets'][6].mpc
    mu, mass = levels['mu'], levels['mass']
    with timed('new_basis_preparation'):
        basis = PositiveCellBasis(space, mu, mass)
    emit(event='quadrature', **basis.audit)
    with timed('old_bilinear_compile'):
        compiled = fem.form(same_mesh_positive_form(space, curl_coefficient=mu, mass_coefficient=mass),
                            jit_options=dict(SAME_MESH_JIT_OPTIONS))
    mesh, work = space.mesh, mpc.function_space
    count = int(mesh.topology.index_map(3).size_local)
    storage = int(work.dofmap.index_map.size_local + work.dofmap.index_map.num_ghosts)
    dimension = int(space.element.space_dimension)
    _, mask, targets, expansion = old._cell_expansion_workspace(mpc, storage, dimension)
    mesh.topology.create_entity_permutations()
    permutations = mesh.topology.get_cell_permutation_info()
    packed = fem.pack_coefficients(compiled)
    constants = np.ascontiguousarray(fem.pack_constants(compiled), dtype=np.complex128)
    kernel = old._cell_kernel(compiled, count)
    selected = {}
    for cell in range(count):
        kind = 'periodic' if np.any(mask[work.dofmap.cell_dofs(cell)]) else 'ordinary'
        selected.setdefault(kind, cell)
    first_mass = mass.x.array[mass.function_space.dofmap.cell_dofs(selected['ordinary'])[0]]
    selected['other_material'] = next(c for c in range(count)
        if mass.x.array[mass.function_space.dofmap.cell_dofs(c)[0]] != first_mass)
    assert len(set(selected.values())) == 3
    for kind, cell in selected.items():
        dofs = np.asarray(work.dofmap.cell_dofs(cell), dtype=np.int32)
        old._fill_cell_expansion(dofs, mpc, storage, mask, targets, expansion)
        coordinates = np.ascontiguousarray(mesh.geometry.x[mesh.geometry.dofmap[cell]].reshape(-1))
        coefficients = old._packed_cell_coefficients(packed, cell, count)
        emit(event='cell_identity', cell=cell, kind=kind, permutation=int(permutations[cell]),
             slaves=int(np.count_nonzero(mask[dofs])), dimension=dimension,
             coefficients=[[v.real, v.imag] for v in coefficients],
             geometry_sha=hashlib.sha256(coordinates.tobytes()).hexdigest())
        reference = np.zeros(storage, complex)
        with timed('old_cell_total', cell=cell):
            tensor = np.zeros((dimension, dimension), complex)
            scratch = np.empty(tensor.size)
            old._kernel_cell_tensor(compiled, kernel, coordinates, coefficients, constants, tensor)
            old._apply_standard_row_transform(space.element, tensor, int(permutations[cell]), scratch)
            old._apply_transpose_right_transform(space.element, tensor, int(permutations[cell]), scratch)
            old.accumulate_constrained_local_diagonal(tensor, targets, expansion, reference)
            del tensor, scratch
        result = np.zeros(storage, complex)
        with timed('new_cell_total', cell=cell):
            values, curls, weights, (mc, ac) = basis.cell(cell, int(permutations[cell]))
            accumulate_basis_energy(values, curls, weights, targets, expansion, result,
                                    curl_coefficient=mc, mass_coefficient=ac)
            del values, curls, weights
        relative = float(np.linalg.norm(result-reference)/np.linalg.norm(reference))
        emit(event='comparison', cell=cell, relative_error=relative, finite=bool(np.all(np.isfinite(result))),
             reference_sha=hashlib.sha256(reference.tobytes()).hexdigest(), result_sha=hashlib.sha256(result.tobytes()).hexdigest())
        assert relative <= 1e-11 and np.all(np.isfinite(result))
        del result, reference
    emit(event='completed', status='COMPONENT_ONLY', formal_pde=False)


if __name__ == '__main__':
    main()
