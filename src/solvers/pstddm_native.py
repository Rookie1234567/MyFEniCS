"""Opt-in, uncondensed small Maxwell PSTDDM experiment; no production defaults.

All cutoffs are integrated as fields/weak commutators, never edge multipliers.
The global L2 Riesz factor and conforming L2 reconstruction are explicit costs.
"""
from __future__ import annotations

import gc
import json
import time
from types import SimpleNamespace

import numpy as np
from scipy import sparse
from scipy.sparse.linalg import splu


def csr(matrix):
    ptr, cols, vals = matrix.getValuesCSR()
    return sparse.csr_matrix((vals.copy(), cols.copy(), ptr.copy()), shape=matrix.getSize())


def assemble(form, cache, degree=18):
    from dolfinx import fem
    from dolfinx.fem import petsc as fp
    compiled = fem.form(form, jit_options={'cache_dir': str(cache), 'timeout': 300},
                        form_compiler_options={'quadrature_degree': degree})
    matrix = fp.assemble_matrix(compiled)
    matrix.assemble()
    result = csr(matrix)
    matrix.destroy()
    return result


def scalar(form, cache, degree=28):
    from dolfinx import fem
    return fem.assemble_scalar(fem.form(form, jit_options={'cache_dir': str(cache), 'timeout': 300},
                                      form_compiler_options={'quadrature_degree': degree}))


def global_system(out, degree, gate):
    import ufl
    from dolfinx import fem
    from dolfinx.fem import petsc as fp
    from dolfinx_mpc.utils import gather_transformation_matrix
    from petsc4py import PETSc
    from .pstddm_model import build_problem
    from .pstddm_dtn_coupling import assemble_dtn_blocks
    start = time.monotonic()
    p = build_problem('dtn', out, degree)
    assert PETSc.COMM_WORLD.size == 1 and np.dtype(PETSc.ScalarType).name == 'complex128'
    cache = out / 'cache'
    gate('global_volume_assembly', 256 << 20)
    A = assemble(p.a, cache)
    lf = fem.form(p.L, jit_options={'cache_dir': str(cache), 'timeout': 300},
                  form_compiler_options={'quadrature_degree': 28})
    b = fp.assemble_vector(lf)
    b.ghostUpdate(addv=PETSc.InsertMode.ADD, mode=PETSc.ScatterMode.REVERSE)
    f = b.array_r.copy()
    raw_f = f.copy()
    b.destroy()
    T = gather_transformation_matrix(p.floquet.mpc).tocsr()
    active = np.setdiff1d(np.arange(T.shape[0]), p.floquet.mpc.slaves)
    assert np.max(abs((T[active] - sparse.eye(T.shape[1])).data), initial=0) < 1e-13
    gate('global_dtn_assembly', 256 << 20)
    dtn = assemble_dtn_blocks(p)
    C, D = (T.conj().T @ dtn.C).tocsr(), (dtn.D @ T).tocsr()
    Ar = (T.conj().T @ A @ T).tocsr()
    f = np.asarray(T.conj().T @ f)
    u, v = ufl.TrialFunction(p.V), ufl.TestFunction(p.V)
    M = (T.conj().T @ assemble(ufl.inner(u, v) * ufl.dx, cache) @ T).tocsr()
    K = (T.conj().T @ assemble(ufl.inner(ufl.curl(u), ufl.curl(v)) * ufl.dx, cache) @ T).tocsr()
    full = sparse.bmat([[Ar, C], [D, sparse.eye(C.shape[1])]], format='csc')
    rhs = np.r_[f, dtn.auxiliary_rhs]
    return SimpleNamespace(p=p, A=Ar, raw_A=A, raw_f=raw_f, C=C, D=D, M=M, K=K, T=T, active=active,
                           full=full, rhs=rhs, dtn=dtn, cache=cache,
                           setup_seconds=time.monotonic()-start)


def build_partition(system, count, gate):
    """Build neighboring two-layer inverses, fixed PML and weak transfers.

PML: 10 nm each internal side, 2 cells, ratio 1.25, quadratic stretch
with sigma chosen from the fixed nominal 1% attenuation formula. Terminal
global boundaries retain exactly their original Fourier-DtN blocks.
"""
    import ufl
    from basix.ufl import element
    from dolfinx import default_real_type, fem, mesh
    from dolfinx_mpc.utils import gather_transformation_matrix
    from .pstddm_source_transfer import PureSourceTransfer
    from .fullspace_pml_double_sweep import (
        _physical_local_row_map, _copy_local_material_tags, _cell_midpoint_data, _grid_key,
    )
    from .pstddm_model import X, Y, Z
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.hybrid_local_mesh import _local_boundary_tags
    from src.geometry.mesh_builder_3d import _structured_hexa_mesh

    if count not in (2, 4):
        raise ValueError('The frozen four-z-cell mesh admits only N=2 or N=4 here')
    p, cfg, cache = system.p, system.p.cfg, system.cache
    start_time = time.monotonic()
    bounds = np.arange(0, 5, 4 // count)
    n = system.M.shape[0]
    gate('mass_factor', 4*n*n*16)
    mass_factor = splu(system.M.tocsc())
    cells, mid = _cell_midpoint_data(p.V.mesh)
    part = np.searchsorted(np.asarray(Z)[bounds], mid[:, 2], side='right') - 1
    tags = mesh.meshtags(p.V.mesh, 3, cells, np.asarray(part+1, dtype=np.int32))
    dx = ufl.Measure('dx', domain=p.V.mesh, subdomain_data=tags)
    u, v = ufl.TrialFunction(p.V), ufl.TestFunction(p.V)
    z = ufl.SpatialCoordinate(p.V.mesh)[2]
    Mi, Bi = [], []
    for i in range(count):
        a, b = Z[bounds[i]], Z[bounds[i+1]]
        t = (z-a)/(b-a)
        beta = 1 - 3*t*t + 2*t*t*t
        Mi.append((system.T.conj().T @ assemble(ufl.inner(u, v)*dx(i+1), cache) @ system.T).tocsr())
        Bi.append((system.T.conj().T @ assemble(beta*ufl.inner(u, v)*dx(i+1), cache) @ system.T).tocsr())
    split_defect = sparse.linalg.norm(sum(Mi[1:], Mi[0].copy())-system.M)/sparse.linalg.norm(system.M)
    if split_defect > 1e-12:
        raise RuntimeError('Physical layer mass partition is not exact')
    sigma = 3*np.log(100)/(cfg.k0*np.sin(np.deg2rad(1.0))*10.0)
    pairs = []
    assembly_seconds = factor_seconds = 0.0
    tolerance = 1e-9 * max(np.ptp(X), np.ptp(Y), np.ptp(Z), 1.)
    for i in range(count-1):
        t0 = time.monotonic()
        lo, hi = int(bounds[i]), int(bounds[i+2])
        physical_z = np.asarray(Z[lo:hi+1])
        depths = 10*np.cumsum(np.asarray([1., 1.25]))/2.25
        lz = np.r_[physical_z[0]-depths[::-1] if lo else [], physical_z,
                   physical_z[-1]+depths if hi < 4 else []]
        left_count = 2 if lo else 0
        local = _structured_hexa_mesh(p.V.mesh.comm, np.asarray(X), np.asarray(Y), lz,
                                      preserve_input_partition=False)
        local.topology.create_connectivity(2, 3)
        lcell, lmid = _cell_midpoint_data(local)
        layer = np.searchsorted(lz, lmid[:, 2], side='right')-1
        physical = lcell[(layer >= left_count) & (layer < left_count+hi-lo)]
        material, _, pml_cells, _, _, _ = _copy_local_material_tags(
            p.V.mesh, p.mesh_data, local, np.asarray(Z), lz, lo, hi,
            left_count, hi-lo, tolerance, 100)
        facet, _ = _local_boundary_tags(local, cfg, z_min=float(lz[0]), z_max=float(lz[-1]))
        md = SimpleNamespace(mesh=local, cell_tags=material, facet_tags=facet)
        V = fem.functionspace(local, element('N1curl', local.basix_cell(), cfg.nedelec_degree,
                                            dtype=default_real_type))
        floquet = build_double_floquet_mpc(V, md, cfg, lambda *_: None)
        Tl = gather_transformation_matrix(floquet.mpc).tocsr()
        active_l = np.setdiff1d(np.arange(Tl.shape[0]), floquet.mpc.slaves)
        grows, lrows = _physical_local_row_map(p.V, p.floquet, V, floquet,
                                               p.V.mesh, local, physical, tolerance)
        gcols = np.searchsorted(system.active, grows)
        assert np.array_equal(system.active[gcols], grows)
        S = sparse.csr_matrix((np.ones(len(grows)), (lrows, gcols)), shape=(Tl.shape[1], n))
        global_by_key = {_grid_key(midpoint, tolerance): int(cell) for cell, midpoint in zip(cells, mid)}
        phase_error = 0.
        for cell in physical:
            source_cell = global_by_key[_grid_key(lmid[int(cell)], tolerance)]
            gdof = p.V.dofmap.cell_dofs(source_cell)
            ldof = V.dofmap.cell_dofs(int(cell))
            phase_error = max(phase_error, float(sparse.linalg.norm(Tl[ldof]@S-system.T[gdof])))
        if phase_error > 1e-11:
            raise RuntimeError(f'Local/global primal Floquet mapping defect {phase_error}')
        # Sparse maps are between independent coordinates. Same orientation is
        # checked cell-by-cell above, and both primal phase maps are native MPC.
        Q = fem.functionspace(local, ('DG', 0))
        eps = fem.Function(Q)
        values = {int(cfg.tags.air): complex(cfg.eps_r), int(cfg.tags.substrate): cfg.substrate_index**2,
                  int(cfg.tags.grating): cfg.grating_index**2}
        for c, tag in zip(material.indices, material.values):
            eps.x.array[Q.dofmap.cell_dofs(int(c))] = values[int(tag)]
        x = ufl.SpatialCoordinate(local)
        dl = ufl.conditional(ufl.lt(x[2], physical_z[0]), (physical_z[0]-x[2])/10, 0.) if lo else 0.
        dr = ufl.conditional(ufl.gt(x[2], physical_z[-1]), (x[2]-physical_z[-1])/10, 0.) if hi < 4 else 0.
        stretch = 1 + 1j*sigma*(dl*dl+dr*dr)
        muinv = ufl.diag(ufl.as_vector([1/stretch, 1/stretch, stretch]))
        epst = ufl.diag(ufl.as_vector([eps*stretch, eps*stretch, eps/stretch]))
        lu, lv = ufl.TrialFunction(V), ufl.TestFunction(V)
        form = (ufl.inner(muinv*ufl.curl(lu), ufl.curl(lv))
                - cfg.k0**2*ufl.inner(epst*lu, lv))*ufl.dx
        gate(f'local_assembly_pair_{i}', 256 << 20)
        L = (Tl.conj().T @ assemble(form, cache) @ Tl).tocsr()
        for side, include in [('bottom', lo == 0), ('top', hi == 4)]:
            if include:
                ids = np.asarray([j for j, mode in enumerate(system.dtn.modes) if mode.side == side])
                L = L - S @ system.C[:, ids] @ system.D[ids, :] @ S.T
        n2_operator_relative = None
        if count == 2:
            exact = system.A-system.C@system.D
            n2_operator_relative = float(sparse.linalg.norm(S.T@L@S-exact)/sparse.linalg.norm(exact))
            if n2_operator_relative > 1e-12:
                raise RuntimeError(f'N2 original operator mismatch {n2_operator_relative}')
        boundary = []
        for endpoint, include in [(lz[0], lo > 0), (lz[-1], hi < 4)]:
            if include:
                facets = mesh.locate_entities_boundary(local, 2, lambda xx, zz=endpoint: np.isclose(xx[2], zz, atol=tolerance, rtol=0))
                boundary.extend(fem.locate_dofs_topological(V, 2, facets).tolist())
        bc = np.flatnonzero(np.asarray(abs(Tl[np.unique(boundary).astype(int)]).sum(axis=0)).ravel() > 0) if boundary else np.asarray([], int)
        free = np.setdiff1d(np.arange(Tl.shape[1]), bc)
        # Layer-local commutator support is integrated, including grad(beta).
        lp = np.searchsorted(np.asarray(Z)[bounds], lmid[:, 2], side='right')-1
        ltags = mesh.meshtags(local, 3, physical, np.asarray(lp[physical]+1, np.int32))
        ldx = ufl.Measure('dx', domain=local, subdomain_data=ltags)
        commutators = []
        weak_product_errors = []
        for target, decreasing in [(i+1, True), (i, False)]:
            a, b = Z[bounds[target]], Z[bounds[target+1]]
            t = (x[2]-a)/(b-a)
            beta = 1-3*t*t+2*t*t*t if decreasing else 3*t*t-2*t*t*t
            cb = (ufl.inner(ufl.cross(ufl.grad(beta), lu), ufl.curl(lv))
                  - ufl.inner(ufl.curl(lu), ufl.cross(ufl.grad(beta), lv)))*ldx(target+1)
            cb_raw = assemble(cb, cache)
            if i == 0:
                # Independent UFL product construction, not a masked DOF vector.
                direct_product = (ufl.inner(ufl.curl(beta*lu), ufl.curl(lv))
                                  - ufl.inner(ufl.curl(lu), ufl.curl(beta*lv)))*ldx(target+1)
                product_matrix = assemble(direct_product, cache)
                defect = sparse.linalg.norm(product_matrix-cb_raw)/max(sparse.linalg.norm(cb_raw), 1e-300)
                weak_product_errors.append(float(defect))
                if defect > 1e-11:
                    raise RuntimeError(f'Native weak curl product defect {defect}')
            commutators.append((S.T @ Tl.conj().T @ cb_raw @ Tl).tocsr())
        assembly_seconds += time.monotonic()-t0
        progress={'partition_count':count,'pair_index':i,'raw_rows':Tl.shape[0],
                  'independent_rows':Tl.shape[1],'free_rows':len(free),'pml_rows':Tl.shape[1]-len(grows),
                  'factors_already_resident':len(pairs),'phase_map_error':phase_error,
                  'weak_product_errors':weak_product_errors,'n2_operator_relative':n2_operator_relative,
                  'planned_factor_extra_bytes':4*len(free)*len(free)*16}
        (cache.parent/'partition_build_progress.json').write_text(json.dumps(progress,indent=2))
        gate(f'local_factor_pair_{i}_free_{len(free)}', 4*len(free)*len(free)*16)
        t0 = time.monotonic()
        factor = splu(L[free][:, free].tocsc())
        factor_seconds += time.monotonic()-t0
        test = np.sin(np.arange(len(free))+1)+1j*np.cos(np.arange(len(free))+1)
        local_error = np.linalg.norm(L[free][:, free]@factor.solve(test)-test)/np.linalg.norm(test)
        if local_error > 1e-9:
            raise RuntimeError(f'Local inverse residual {local_error}')
        pairs.append(SimpleNamespace(S=S, free=free, factor=factor, L=L, plus=commutators[0],
                                     minus=commutators[1], rows=Tl.shape[1], raw_rows=Tl.shape[0],
                                     pml_cells=len(pml_cells), physical_rows=len(grows),
                                     pml_rows=Tl.shape[1]-len(grows), local_residual=local_error,
                                     phase_map_error=phase_error, weak_product_errors=weak_product_errors,
                                     free_rows=len(free), n2_operator_relative=n2_operator_relative,
                                     solve_count=0, solve_seconds=0., factor_nnz=factor.L.nnz+factor.U.nnz))
        del floquet, V, md, local, Tl, eps
        gc.collect()

    def solve_pair(i, rhs):
        pair = pairs[i]
        b = pair.S @ rhs
        t0 = time.monotonic()
        out = np.zeros(pair.rows, complex)
        out[pair.free] = pair.factor.solve(b[pair.free])
        pair.solve_count += 1
        pair.solve_seconds += time.monotonic()-t0
        return out

    def reconstruct_load(i, up, down):
        field = np.zeros(n, complex)
        if up is not None:
            field += pairs[i-1].S.T @ up
        if down is not None:
            field += pairs[i].S.T @ down
        return Mi[i] @ field

    core = PureSourceTransfer(partition_mass=Mi, forward_beta_mass=Bi,
                              mass_solve=mass_factor.solve, solve_pair=solve_pair,
                              forward_commutator=lambda i, value: pairs[i].plus @ value,
                              reverse_commutator=lambda i, value: pairs[i].minus @ value,
                              reconstruct_load=reconstruct_load)
    # A representable field must survive restrict/reconstruction with layer
    # masses; this is a map test, not a PSTDDM convergence claim.
    probe = np.sin(np.arange(n)+.3)+1j*np.cos(np.arange(n)+.7)
    load = np.zeros(n, complex)
    for i in range(count):
        j = min(i, count-2)
        load += Mi[i] @ (pairs[j].S.T @ (pairs[j].S @ probe))
    reproduction = np.linalg.norm(mass_factor.solve(load)-probe)/np.linalg.norm(probe)
    if reproduction > 1e-10:
        raise RuntimeError(f'Conforming reconstruction map defect {reproduction}')
    metadata = {'partition_count': count, 'bounds_cell_indices': bounds.tolist(),
                'pml_thickness_nm': 10., 'pml_cells_per_side': 2, 'pml_grading_ratio': 1.25,
                'sigma_max': float(sigma), 'mass_partition_relative': float(split_defect),
                'reconstruction_relative': float(reproduction), 'local_assembly_seconds': assembly_seconds,
                'local_factor_seconds': factor_seconds, 'setup_seconds': time.monotonic()-start_time,
                'cache_strategy': 'all_local_factors_and_one_global_mass_factor_resident',
                'global_mass_factor_nnz': mass_factor.L.nnz+mass_factor.U.nnz,
                'pairs': [{k: getattr(pair, k) for k in ['rows', 'raw_rows', 'pml_rows', 'physical_rows',
                           'pml_cells', 'free_rows', 'local_residual', 'factor_nnz', 'phase_map_error',
                           'weak_product_errors', 'n2_operator_relative']} for pair in pairs]}
    return core, pairs, metadata
