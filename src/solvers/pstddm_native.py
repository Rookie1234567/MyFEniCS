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


def global_system(out, degree, gate, *, model_spec=None):
    import ufl
    from dolfinx import fem
    from dolfinx.fem import petsc as fp
    from dolfinx_mpc.utils import gather_transformation_matrix
    from petsc4py import PETSc
    from .pstddm_model import build_problem
    from .pstddm_dtn_coupling import assemble_dtn_blocks
    start = time.monotonic()
    p = build_problem('dtn', out, degree, model_spec=model_spec)
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


def build_partition(system, count, gate, *, factor_factory=None):
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
    from src.constraints.floquet_3d import build_double_floquet_mpc
    from src.geometry.hybrid_local_mesh import _local_boundary_tags
    from src.geometry.mesh_builder_3d import _structured_hexa_mesh

    if count not in (2, 4, 8):
        raise ValueError('The workstation profile admits only N=2, N=4, or readmitted N=8')
    p6_resource_gates = factor_factory is not None and bool(
        getattr(system, "require_raw_port_map", False)
    )
    if p6_resource_gates:
        from petsc4py import PETSc
    p, cfg, cache = system.p, system.p.cfg, system.cache
    model = p.model_spec
    x_values = np.asarray(model.x_axis_nm, dtype=np.float64)
    y_values = np.asarray(model.y_axis_nm, dtype=np.float64)
    z_values = np.asarray(model.z_axis_nm, dtype=np.float64)
    nz = z_values.size - 1
    start_time = time.monotonic()
    explicit_bounds = getattr(system, 'partition_bounds', None)
    if explicit_bounds is None:
        if nz % count:
            raise ValueError(f'{nz} physical z layers cannot be divided into N={count} partitions')
        bounds = np.linspace(0, nz, count + 1, dtype=np.int64)
    else:
        bounds = np.asarray(explicit_bounds, dtype=np.int64)
        if (bounds.shape != (count + 1,) or bounds[0] != 0 or bounds[-1] != nz
                or np.any(np.diff(bounds) < 1)):
            raise ValueError('explicit partition bounds must cover every physical layer once')
    n = system.M.shape[0]
    full_rows = int(system.T.shape[0])
    if factor_factory is None:
        gate('mass_factor', 4*n*n*16)
        mass_factor = splu(system.M.tocsc())
    else:
        mass_matrix = system.M.tocsr()
        gate('mass_factor_sparse_input', int(mass_matrix.nnz)*32 + (n+1)*8)
        mass_factor = factor_factory(mass_matrix, 'global_full_fe_mass')
    cells, mid = _cell_midpoint_data(p.V.mesh)
    part = np.searchsorted(z_values[bounds], mid[:, 2], side='right') - 1
    tags = mesh.meshtags(p.V.mesh, 3, cells, np.asarray(part+1, dtype=np.int32))
    dx = ufl.Measure('dx', domain=p.V.mesh, subdomain_data=tags)
    u, v = ufl.TrialFunction(p.V), ufl.TestFunction(p.V)
    z = ufl.SpatialCoordinate(p.V.mesh)[2]
    Mi, Bi = [], []
    if p6_resource_gates:
        layer_raw_nnz_upper = getattr(system, "layer_mass_raw_nnz_upper", None)
        if not isinstance(layer_raw_nnz_upper, (tuple, list)) or len(layer_raw_nnz_upper) != count:
            raise ValueError("N4 layer mass admission requires four cell-support bounds")
        layer_mass_max_expansion = int(getattr(system, "layer_mass_max_expansion", 0))
        if layer_mass_max_expansion < 1:
            raise ValueError("N4 layer mass admission requires the verified Floquet row expansion")

    def admit_layer_mass(index, matrix_name, phase, actual_raw_nnz=None):
        raw_nnz = int(layer_raw_nnz_upper[index])
        csr_bytes = lambda rows, nnz: int(nnz) * 24 + (int(rows) + 1) * 8
        petsc_bytes = lambda rows, nnz: (
            int(nnz) * (16 + np.dtype(PETSc.IntType).itemsize)
            + (int(rows) + 1) * np.dtype(PETSc.IntType).itemsize
        )
        if phase == "assembly":
            future = petsc_bytes(full_rows, raw_nnz) + csr_bytes(full_rows, raw_nnz) + (256 << 20)
            intermediate_nnz = reduced_nnz = None
        elif phase == "transform":
            if actual_raw_nnz is None:
                raise ValueError("layer transform gate requires the actual raw CSR nnz")
            intermediate_nnz = min(full_rows * n, int(actual_raw_nnz) * layer_mass_max_expansion)
            reduced_nnz = min(n * n, intermediate_nnz * layer_mass_max_expansion)
            future = csr_bytes(full_rows, intermediate_nnz) + csr_bytes(n, reduced_nnz) + (512 << 20)
        else:
            raise ValueError(f"unknown layer mass allocation phase: {phase}")
        gate(
            f"p6_full_fe_layer_mass_{index}_{matrix_name}_{phase}",
            future,
            estimate_basis={
                "layer": int(index),
                "matrix": matrix_name,
                "phase": phase,
                "raw_cell_support_nnz_upper_bound": raw_nnz,
                "floquet_max_row_expansion": layer_mass_max_expansion,
                "actual_raw_csr_nnz": actual_raw_nnz,
                "transformed_intermediate_nnz_upper_bound": intermediate_nnz,
                "transformed_result_nnz_upper_bound": reduced_nnz,
                "already_resident_layer_matrices_recounted": False,
                "incremental_future_bytes": future,
                "future_includes": (
                    ["one PETSc matrix", "one raw CSR copy", "256 MiB assembly workspace"]
                    if phase == "assembly" else
                    ["transform intermediate", "result CSR", "512 MiB sparse transform workspace"]
                ),
            },
        )

    for i in range(count):
        a, b = z_values[bounds[i]], z_values[bounds[i+1]]
        t = (z-a)/(b-a)
        beta = 1 - 3*t*t + 2*t*t*t
        if p6_resource_gates:
            admit_layer_mass(i, "M", "assembly")
            raw_layer_mass = assemble(ufl.inner(u, v)*dx(i+1), cache)
            admit_layer_mass(i, "M", "transform", int(raw_layer_mass.nnz))
            Mi.append((system.T.conj().T @ raw_layer_mass @ system.T).tocsr())
            del raw_layer_mass
        else:
            Mi.append((system.T.conj().T @ assemble(ufl.inner(u, v)*dx(i+1), cache) @ system.T).tocsr())
        if p6_resource_gates:
            admit_layer_mass(i, "B", "assembly")
            raw_beta_mass = assemble(beta*ufl.inner(u, v)*dx(i+1), cache)
            admit_layer_mass(i, "B", "transform", int(raw_beta_mass.nnz))
            Bi.append((system.T.conj().T @ raw_beta_mass @ system.T).tocsr())
            del raw_beta_mass
        else:
            Bi.append((system.T.conj().T @ assemble(beta*ufl.inner(u, v)*dx(i+1), cache) @ system.T).tocsr())
    split_defect = sparse.linalg.norm(sum(Mi[1:], Mi[0].copy())-system.M)/sparse.linalg.norm(system.M)
    if split_defect > 1e-12:
        raise RuntimeError('Physical layer mass partition is not exact')
    sigma = 3*np.log(100)/(cfg.k0*np.sin(np.deg2rad(1.0))*10.0)
    pairs = []
    assembly_seconds = factor_seconds = 0.0
    tolerance = 1e-9 * max(np.ptp(x_values), np.ptp(y_values), np.ptp(z_values), 1.)
    for i in range(count-1):
        t0 = time.monotonic()
        lo, hi = int(bounds[i]), int(bounds[i+2])
        physical_z = z_values[lo:hi+1]
        depths = 10*np.cumsum(np.asarray([1., 1.25]))/2.25
        lz = np.r_[physical_z[0]-depths[::-1] if lo else [], physical_z,
                   physical_z[-1]+depths if hi < nz else []]
        left_count = 2 if lo else 0
        local = _structured_hexa_mesh(p.V.mesh.comm, x_values, y_values, lz,
                                      preserve_input_partition=False)
        local.topology.create_connectivity(2, 3)
        lcell, lmid = _cell_midpoint_data(local)
        layer = np.searchsorted(lz, lmid[:, 2], side='right')-1
        physical = lcell[(layer >= left_count) & (layer < left_count+hi-lo)]
        material, _, pml_cells, _, _, _ = _copy_local_material_tags(
            p.V.mesh, p.mesh_data, local, z_values, lz, lo, hi,
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
        S = sparse.csr_matrix((np.ones(len(grows), dtype=np.complex128), (lrows, gcols)), shape=(Tl.shape[1], n))
        global_by_key = {_grid_key(midpoint, tolerance): int(cell) for cell, midpoint in zip(cells, mid)}
        p.V.mesh.topology.create_entity_permutations()
        local.topology.create_entity_permutations()
        global_permutations = np.asarray(p.V.mesh.topology.get_cell_permutation_info(), dtype=np.uint32)
        local_permutations = np.asarray(local.topology.get_cell_permutation_info(), dtype=np.uint32)
        phase_error = 0.
        for cell in physical:
            source_cell = global_by_key[_grid_key(lmid[int(cell)], tolerance)]
            gdof = p.V.dofmap.cell_dofs(source_cell)
            ldof = V.dofmap.cell_dofs(int(cell))
            phase_error = max(phase_error, float(sparse.linalg.norm(Tl[ldof]@S-system.T[gdof])))
        if phase_error > 1e-11:
            raise RuntimeError(f'Local/global primal Floquet mapping defect {phase_error}')
        mapped_global_active = np.unique(S.indices)
        S_mapped = S[:, mapped_global_active]
        dual_map_defect = float(sparse.linalg.norm(
            S_mapped.getH() @ S_mapped - sparse.eye(len(mapped_global_active), format='csr')))
        if not np.isfinite(dual_map_defect) or dual_map_defect > 1e-11:
            raise RuntimeError(f'Local/global independent dual restriction defect {dual_map_defect}')
        raw_global_to_local = {}
        if getattr(system, 'require_raw_port_map', False):
            global_full_rows = int(p.V.dofmap.index_map.size_global*p.V.dofmap.index_map_bs)
            for cell in physical:
                source_cell = global_by_key[_grid_key(lmid[int(cell)], tolerance)]
                if int(global_permutations[source_cell]) != int(local_permutations[int(cell)]):
                    raise RuntimeError('physical/local p6 cell orientation differs')
                global_local_dofs = np.asarray(p.V.dofmap.cell_dofs(source_cell), dtype=np.int32)
                local_local_dofs = np.asarray(V.dofmap.cell_dofs(int(cell)), dtype=np.int32)
                global_raw_dofs = np.asarray(
                    p.V.dofmap.index_map.local_to_global(global_local_dofs), dtype=np.int64)
                if global_raw_dofs.shape != local_local_dofs.shape:
                    raise RuntimeError('physical/local raw p6 cell dof dimensions differ')
                for global_row, local_row in zip(global_raw_dofs, local_local_dofs, strict=True):
                    global_row, local_row = int(global_row), int(local_row)
                    if not 0 <= global_row < global_full_rows:
                        raise RuntimeError('physical/local raw p6 row exceeds the global FE space')
                    previous = raw_global_to_local.setdefault(global_row, local_row)
                    if previous != local_row:
                        raise RuntimeError('physical/local raw p6 row map is not one-to-one')
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
        dr = ufl.conditional(ufl.gt(x[2], physical_z[-1]), (x[2]-physical_z[-1])/10, 0.) if hi < nz else 0.
        stretch = 1 + 1j*sigma*(dl*dl+dr*dr)
        muinv = ufl.diag(ufl.as_vector([1/stretch, 1/stretch, stretch]))
        epst = ufl.diag(ufl.as_vector([eps*stretch, eps*stretch, eps/stretch]))
        lu, lv = ufl.TrialFunction(V), ufl.TestFunction(V)
        form = (ufl.inner(muinv*ufl.curl(lu), ufl.curl(lv))
                - cfg.k0**2*ufl.inner(epst*lu, lv))*ufl.dx
        if p6_resource_gates:
            local_raw_rows = int(Tl.shape[0])
            local_dof_lengths = [len(V.dofmap.cell_dofs(int(cell))) for cell in lcell]
            max_local_cell_dofs = max(local_dof_lengths, default=0)
            local_occurrences = np.zeros(local_raw_rows, dtype=np.int64)
            for cell in lcell:
                np.add.at(
                    local_occurrences,
                    np.asarray(V.dofmap.cell_dofs(int(cell)), dtype=np.int64),
                    1,
                )
            local_raw_nnz_upper = min(
                local_raw_rows * local_raw_rows,
                int(np.minimum(local_occurrences * max_local_cell_dofs, local_raw_rows).sum()),
            )
            local_expansion = max(1, int(np.diff(Tl.indptr).max(initial=0)))
            local_csr_bytes = lambda rows, nnz: int(nnz) * 24 + (int(rows) + 1) * 8
            local_petsc_bytes = lambda rows, nnz: (
                int(nnz) * (16 + np.dtype(PETSc.IntType).itemsize)
                + (int(rows) + 1) * np.dtype(PETSc.IntType).itemsize
            )
            gate(
                f'local_assembly_pair_{i}_cell_support_preflight',
                local_petsc_bytes(local_raw_rows, local_raw_nnz_upper)
                + local_csr_bytes(local_raw_rows, local_raw_nnz_upper)
                + (256 << 20),
                estimate_basis={
                    'local_raw_rows': local_raw_rows,
                    'local_cell_count': int(len(lcell)),
                    'max_local_cell_dofs': max_local_cell_dofs,
                    'cell_support_raw_nnz_upper_bound': local_raw_nnz_upper,
                    'incremental_future_bytes': True,
                    'future_includes': ['one local PETSc operator', 'one raw CSR copy', '256 MiB assembly workspace'],
                },
            )
            raw_local_operator = assemble(form, cache)
            local_intermediate_nnz_upper = min(
                local_raw_rows * Tl.shape[1], int(raw_local_operator.nnz) * local_expansion
            )
            local_reduced_nnz_upper = min(
                Tl.shape[1] * Tl.shape[1], local_intermediate_nnz_upper * local_expansion
            )
            local_transform_future = (
                local_csr_bytes(local_raw_rows, local_intermediate_nnz_upper)
                + local_csr_bytes(Tl.shape[1], local_reduced_nnz_upper)
                + (512 << 20)
            )
            gate(
                f'local_assembly_pair_{i}_floquet_transform',
                local_transform_future,
                estimate_basis={
                    'actual_raw_local_operator_nnz': int(raw_local_operator.nnz),
                    'already_resident_raw_local_CSR_recounted': False,
                    'floquet_max_row_expansion': local_expansion,
                    'transformed_intermediate_nnz_upper_bound': int(local_intermediate_nnz_upper),
                    'transformed_result_nnz_upper_bound': int(local_reduced_nnz_upper),
                    'incremental_future_bytes': local_transform_future,
                },
            )
            local_intermediate = raw_local_operator @ Tl
            L = (Tl.conj().T @ local_intermediate).tocsr()
            del raw_local_operator, local_intermediate
        else:
            gate(f'local_assembly_pair_{i}', 256 << 20)
            L = (Tl.conj().T @ assemble(form, cache) @ Tl).tocsr()
        raw_port_map_audit = None
        if getattr(system, 'require_raw_port_map', False):
            raw_port_map_audit = []
            for mode_index, column in enumerate(system.raw_port_columns):
                if not ((column.side == 'bottom' and lo == 0)
                        or (column.side == 'top' and hi == nz)):
                    continue
                if complex(column.raw_H) != 1.0 + 0.0j:
                    raise RuntimeError('raw Stage-4 terminal H must remain the exact identity')
                mapped_c = 0
                mapped_d = 0
                for rows, values, name in (
                    (column.raw_C_rows, column.raw_C_values, 'C'),
                    (column.raw_D_rows, column.raw_D_values, 'D'),
                ):
                    for row, value in zip(rows, values, strict=True):
                        if value == 0.0:
                            continue
                        if int(row) not in raw_global_to_local:
                            raise RuntimeError(
                                f'nonzero raw terminal {name} row {int(row)} has no local physical-row image')
                        if name == 'C':
                            mapped_c += 1
                        else:
                            mapped_d += 1
                raw_port_map_audit.append({
                    'mode_index': mode_index,
                    'side': column.side,
                    'raw_C_nnz': mapped_c,
                    'raw_D_nnz': mapped_d,
                })
            if ((lo == 0 or hi == nz) and not raw_port_map_audit):
                raise RuntimeError('local pair containing a global terminal has no raw port columns')
        for side, include in [('bottom', lo == 0), ('top', hi == nz)]:
            if include:
                ids = np.asarray(
                    [j for j, mode in enumerate(system.dtn.modes) if mode.side == side],
                    dtype=np.int64,
                )
                if p6_resource_gates:
                    ids.sort()
                    mapped_global = np.unique(S.indices).astype(np.int64, copy=False)
                    c_counts = np.zeros(len(ids), dtype=np.int64)
                    for global_row in mapped_global:
                        start, end = system.C.indptr[int(global_row):int(global_row) + 2]
                        row_modes = system.C.indices[start:end]
                        selected = np.isin(row_modes, ids, assume_unique=True)
                        if np.any(selected):
                            c_counts += np.bincount(
                                np.searchsorted(ids, row_modes[selected]), minlength=len(ids)
                            )
                    d_global_counts = system.D.indptr[ids + 1] - system.D.indptr[ids]
                    d_mapped_counts = np.zeros(len(ids), dtype=np.int64)
                    for local_mode, global_mode in enumerate(ids):
                        start, end = system.D.indptr[int(global_mode):int(global_mode) + 2]
                        d_mapped_counts[local_mode] = np.count_nonzero(
                            np.isin(system.D.indices[start:end], mapped_global, assume_unique=True)
                        )
                    c_mode_nnz = int(c_counts.sum())
                    c_slice_nnz = int(np.isin(system.C.indices, ids).sum())
                    d_slice_nnz = int(d_global_counts.sum())
                    scd_global_nnz = min(
                        S.shape[0] * system.C.shape[0],
                        int(np.dot(c_counts, d_global_counts)),
                    )
                    terminal_nnz_upper = min(
                        S.shape[0] * S.shape[0], int(np.dot(c_counts, d_mapped_counts))
                    )
                    result_nnz_upper = min(S.shape[0] * S.shape[0], int(L.nnz) + terminal_nnz_upper)
                    csr_bytes = lambda rows, nnz: int(nnz) * 24 + (int(rows) + 1) * 8
                    c_slice_bytes = csr_bytes(S.shape[1], c_slice_nnz)
                    sc_bytes = csr_bytes(S.shape[0], c_mode_nnz)
                    d_slice_bytes = csr_bytes(len(ids), d_slice_nnz)
                    scd_bytes = csr_bytes(S.shape[0], scd_global_nnz)
                    sh_bytes = csr_bytes(S.shape[1], int(S.nnz))
                    terminal_bytes = csr_bytes(S.shape[0], terminal_nnz_upper)
                    result_bytes = csr_bytes(S.shape[0], result_nnz_upper)
                    product_future = max(
                        c_slice_bytes + sc_bytes,
                        sc_bytes + d_slice_bytes + scd_bytes,
                        scd_bytes + sh_bytes + terminal_bytes,
                        terminal_bytes + result_bytes,
                    ) + (512 << 20)
                    gate(
                        f'local_terminal_{side}_SCDSH_product_pair_{i}',
                        product_future,
                        estimate_basis={
                            'local_rows': int(S.shape[0]),
                            'mapped_global_active_rows': int(len(mapped_global)),
                            'terminal_mode_count': int(len(ids)),
                            'C_terminal_slice_nnz_upper_bound': c_slice_nnz,
                            'C_mapped_support_nnz': c_mode_nnz,
                            'D_terminal_support_nnz': d_slice_nnz,
                            'SC_D_intermediate_nnz_upper_bound': scd_global_nnz,
                            'SCDSH_terminal_nnz_upper_bound': terminal_nnz_upper,
                            'existing_L_nnz_live_baseline': int(L.nnz),
                            'final_L_nnz_upper_bound': result_nnz_upper,
                            'dense_local_square_bound_used': False,
                            'incremental_future_bytes': product_future,
                        },
                    )
                    C_modes = system.C[:, ids].tocsr()
                    SC = (S @ C_modes).tocsr()
                    del C_modes
                    D_modes = system.D[ids, :].tocsr()
                    SCD = (SC @ D_modes).tocsr()
                    del SC, D_modes
                    S_H = S.getH().tocsr()
                    terminal = (SCD @ S_H).tocsr()
                    del SCD, S_H
                    reduced_L = L - terminal
                    del L, terminal
                    L = reduced_L
                else:
                    L = L - S @ system.C[:, ids] @ system.D[ids, :] @ S.getH()
        n2_operator_relative = None
        if count == 2:
            exact = system.A-system.C@system.D
            n2_operator_relative = float(sparse.linalg.norm(S.getH()@L@S-exact)/sparse.linalg.norm(exact))
            if n2_operator_relative > 1e-12:
                raise RuntimeError(f'N2 original operator mismatch {n2_operator_relative}')
        boundary = []
        for endpoint, include in [(lz[0], lo > 0), (lz[-1], hi < nz)]:
            if include:
                facets = mesh.locate_entities_boundary(local, 2, lambda xx, zz=endpoint: np.isclose(xx[2], zz, atol=tolerance, rtol=0))
                boundary.extend(fem.locate_dofs_topological(V, 2, facets).tolist())
        bc = np.flatnonzero(np.asarray(abs(Tl[np.unique(boundary).astype(int)]).sum(axis=0)).ravel() > 0) if boundary else np.asarray([], int)
        free = np.setdiff1d(np.arange(Tl.shape[1]), bc)
        # Layer-local commutator support is integrated, including grad(beta).
        lp = np.searchsorted(z_values[bounds], lmid[:, 2], side='right')-1
        ltags = mesh.meshtags(local, 3, physical, np.asarray(lp[physical]+1, np.int32))
        ldx = ufl.Measure('dx', domain=local, subdomain_data=ltags)
        commutators = []
        weak_product_errors = []
        for target, decreasing in [(i+1, True), (i, False)]:
            a, b = z_values[bounds[target]], z_values[bounds[target+1]]
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
            commutators.append((S.getH() @ Tl.conj().T @ cb_raw @ Tl).tocsr())
        assembly_seconds += time.monotonic()-t0
        progress={'partition_count':count,'pair_index':i,'raw_rows':Tl.shape[0],
                  'independent_rows':Tl.shape[1],'free_rows':len(free),'pml_rows':Tl.shape[1]-len(grows),
                  'factors_already_resident':len(pairs),'phase_map_error':phase_error,
                  'weak_product_errors':weak_product_errors,'n2_operator_relative':n2_operator_relative,
                  'dual_map_defect':dual_map_defect,
                  'planned_factor_extra_bytes':(4*len(free)*len(free)*16 if factor_factory is None
                                                else int(L.nnz)*32 + (len(free)+1)*8)}
        (cache.parent/'partition_build_progress.json').write_text(json.dumps(progress,indent=2))
        if factor_factory is None:
            gate(f'local_factor_pair_{i}_free_{len(free)}', 4*len(free)*len(free)*16)
        else:
            gate(f'local_factor_pair_{i}_free_slice_preflight',
                 int(L.nnz)*32 + (len(free)+1)*8,
                 estimate_basis={'operator_stored_nnz': int(L.nnz),
                                 'free_rows': int(len(free)),
                                 'incremental_future_bytes': True,
                                 'bound': 'new free-matrix CSR is bounded by the live full local operator nnz'})
        free_matrix = L[free][:, free].tocsr()
        if factor_factory is not None:
            free_matrix_bytes = int(
                free_matrix.data.nbytes + free_matrix.indices.nbytes + free_matrix.indptr.nbytes
            )
            gate(f'local_factor_pair_{i}_free_{len(free)}',
                 free_matrix_bytes,
                 estimate_basis={'actual_free_operator_stored_nnz': int(free_matrix.nnz),
                                 'free_rows': int(len(free)),
                                 'already_resident_free_matrix_recounted': False,
                                 'future_bytes': 'one canonical CSR copy supplied to bounded MUMPS owner'})
        t0 = time.monotonic()
        factor = (splu(free_matrix.tocsc()) if factor_factory is None
                  else factor_factory(free_matrix, f'local_pair_{i}'))
        factor_seconds += time.monotonic()-t0
        test = np.sin(np.arange(len(free))+1)+1j*np.cos(np.arange(len(free))+1)
        local_error = np.linalg.norm(free_matrix@factor.solve(test)-test)/np.linalg.norm(test)
        if local_error > 1e-9:
            raise RuntimeError(f'Local inverse residual {local_error}')
        if factor_factory is None:
            factor_inventory_nnz = int(factor.L.nnz + factor.U.nnz)
            factor_inventory_source = 'scipy_splu_L_plus_U_stored_entries'
            factor_inventory = None
        else:
            factor_inventory = getattr(factor, 'audit', {}).get('numeric_owner_factor_inventory', {})
            factor_inventory_nnz = factor_inventory.get('factor_nnz_corrected')
            factor_inventory_source = factor_inventory.get('factor_nnz_corrected_source')
        raw_map_global_rows = np.asarray(sorted(raw_global_to_local), dtype=np.int64)
        raw_map_local_rows = np.asarray(
            [raw_global_to_local[int(row)] for row in raw_map_global_rows], dtype=np.int64)
        raw_map_global_rows.setflags(write=False)
        raw_map_local_rows.setflags(write=False)
        pairs.append(SimpleNamespace(S=S, free=free, factor=factor, L=L, plus=commutators[0],
                                     minus=commutators[1], rows=Tl.shape[1], raw_rows=Tl.shape[0],
                                     pml_cells=len(pml_cells), physical_rows=len(grows),
                                     pml_rows=Tl.shape[1]-len(grows), local_residual=local_error,
                                     phase_map_error=phase_error, weak_product_errors=weak_product_errors,
                                     free_rows=len(free), n2_operator_relative=n2_operator_relative,
                                     solve_count=0, solve_seconds=0.,
                                     factor_nnz=factor_inventory_nnz,
                                     factor_input_matrix_nnz=int(free_matrix.nnz),
                                     factor_inventory_nnz=factor_inventory_nnz,
                                     factor_inventory_source=factor_inventory_source,
                                     factor_inventory_unit=(
                                         'stored_entries_of_L_plus_U'
                                         if factor_factory is None
                                         else 'MUMPS_INFOG(9)_corrected_count'
                                     ),
                                     factor_inventory=factor_inventory,
                                     raw_map_global_rows=raw_map_global_rows,
                                     raw_map_local_rows=raw_map_local_rows,
                                     Tl=Tl,
                                     dual_map_defect=dual_map_defect,
                                     raw_port_map_audit=raw_port_map_audit))
        del floquet, V, md, local, Tl, eps
        gc.collect()

    def solve_pair(i, rhs):
        pair = pairs[i]
        if getattr(system, 'require_raw_port_map', False):
            # S was verified as the exact isometric primal map. With unitary
            # Floquet phases, S @ rhs is its corresponding dual restriction.
            b = np.asarray(pair.S @ rhs, dtype=np.complex128).ravel()
        else:
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
            field += pairs[i-1].S.getH() @ up
        if down is not None:
            field += pairs[i].S.getH() @ down
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
        load += Mi[i] @ (pairs[j].S.getH() @ (pairs[j].S @ probe))
    reproduction = np.linalg.norm(mass_factor.solve(load)-probe)/np.linalg.norm(probe)
    if reproduction > 1e-10:
        raise RuntimeError(f'Conforming reconstruction map defect {reproduction}')
    metadata = {'partition_count': count, 'bounds_cell_indices': bounds.tolist(),
                'bounds_z_nm': z_values[bounds].tolist(),
                'physical_z_axis_nm': z_values.tolist(),
                'geometry_identity': model.geometry_identity,
                'wavelength_nm': float(model.wavelength_nm),
                'local_pml_profile': 'two_cells_per_internal_side_10nm_ratio1p25_quadratic_v1',
                'pml_thickness_nm': 10., 'pml_cells_per_side': 2, 'pml_grading_ratio': 1.25,
                'sigma_max': float(sigma), 'mass_partition_relative': float(split_defect),
                'reconstruction_relative': float(reproduction), 'local_assembly_seconds': assembly_seconds,
                'local_factor_seconds': factor_seconds, 'setup_seconds': time.monotonic()-start_time,
                'cache_strategy': 'all_local_factors_and_one_global_mass_factor_resident',
                'global_mass_factor_input_matrix_nnz': int(system.M.nnz),
                'global_mass_factor_inventory': (
                    {'source': 'scipy_splu_L_plus_U_stored_entries',
                     'nnz': int(mass_factor.L.nnz + mass_factor.U.nnz)}
                    if factor_factory is None
                    else getattr(mass_factor, 'audit', {}).get('numeric_owner_factor_inventory', {})
                ),
                'global_mass_factor_inventory_nnz': (
                    int(mass_factor.L.nnz + mass_factor.U.nnz)
                    if factor_factory is None
                    else getattr(mass_factor, 'audit', {}).get(
                        'numeric_owner_factor_inventory', {}).get('factor_nnz_corrected')
                ),
                'pairs': [{k: getattr(pair, k) for k in ['rows', 'raw_rows', 'pml_rows', 'physical_rows',
                           'pml_cells', 'free_rows', 'local_residual', 'factor_nnz', 'phase_map_error',
                           'weak_product_errors', 'n2_operator_relative', 'dual_map_defect',
                           'factor_input_matrix_nnz', 'factor_inventory_nnz',
                           'factor_inventory_source', 'factor_inventory_unit', 'factor_inventory',
                           'raw_port_map_audit']} for pair in pairs]}
    return core, pairs, metadata


def build_stage4_p6_source_transfer(
    request,
    *,
    output_directory,
    admit,
    observe,
    available_floor_bytes,
    task_limit_bytes,
    compiler_command,
):
    """Apply the existing full-FE source-transfer core behind the condensed Stage-4 bridge.

    The source-transfer mass and its four physical-layer pieces use every
    independent physical FE row. Only the incoming condensed trace dual is
    master-row lifted, and only the resulting full-FE primal is restricted
    back to trace masters for the original port bridge.
    """
    import hashlib
    import os
    from pathlib import Path

    import ufl
    from dolfinx import fem
    from dolfinx.fem import petsc as fem_petsc
    from dolfinx_mpc.utils import gather_transformation_matrix
    from petsc4py import PETSc
    from scipy import sparse

    from ..common.strict_json import atomic_json
    from .bounded_mumps import load_public_shim
    from .pstddm_bounded_aux_factor import (
        FAILED_AUXILIARY_OWNERS,
        ExactBoundedAuxiliaryFactor,
        _RuntimePorts,
        _default_runtime,
    )
    from .pstddm_comparison import flexible_gmres, true_residual
    from .pstddm_condensed_adapter import (
        balanced_partition_bounds,
        apply_full_fe_port_bridge,
        prepare_trace_master_adapter,
    )
    from .pstddm_stage4_hook import PstddmRawPortColumn
    from types import SimpleNamespace

    output = Path(output_directory)
    output.mkdir(parents=True, exist_ok=True)
    cache = Path(os.environ.get("XDG_CACHE_HOME", str(output / "cache"))) / "pstddm_p6_full_fe_source_transfer"
    cache.mkdir(parents=True, exist_ok=True)
    owners = []
    owner_closed: set[int] = set()
    owner_errors: dict[int, list[str]] = {}
    started = time.monotonic()
    active_error = None
    record = {
        "schema": "pstddm.p6.h10.stage4_source_transfer_diagnostic.v2",
        "status": "running",
        "official_result": False,
        "diagnostic_only": True,
        "method": "existing_full_FE_PureSourceTransfer_plus_existing_condensed_port_bridge",
        "initial_iterate": "one source-transfer sweep from zero; direct solution is not imported",
        "partition_count": 4,
        "task_cap_bytes": int(task_limit_bytes),
        "available_floor_bytes": int(available_floor_bytes),
        "global_target_maxwell_factor_count": 0,
        "full_FE_mass_factor_count": 1,
        "local_pair_factor_count": 3,
        "auxiliary_rows_in_source_transfer": False,
    }

    def jsonable(value):
        if isinstance(value, np.ndarray):
            return value.tolist()
        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(key): jsonable(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)):
            return [jsonable(item) for item in value]
        return value

    def persist(status, error=None):
        record["status"] = status
        record["elapsed_seconds"] = float(time.monotonic() - started)
        record["factor_owner_state"] = [
            {
                "directory": str(getattr(owner, "_directory", "")),
                "closed": id(owner) in owner_closed,
                "cleanup_errors": owner_errors.get(id(owner), []),
                "audit": jsonable(getattr(owner, "audit", {})),
            }
            for owner in owners
        ]
        if error is not None:
            record["failure"] = {"type": type(error).__name__, "message": str(error)}
        atomic_json(output / "pstddm_stage4_diagnostic.json", jsonable(record))

    def close_owners():
        failures = []
        for owner in reversed(owners):
            identity = id(owner)
            if identity in owner_closed:
                continue
            try:
                owner.close()
            except BaseException as error:
                owner_errors.setdefault(identity, []).append(repr(error))
                failures.append(error)
            else:
                owner_closed.add(identity)
        return failures

    def stage_admit(name, future_bytes, basis=None):
        return admit(
            str(name),
            int(future_bytes),
            estimate_basis=(
                {"description": "explicit Stage-4 PSTDDM allocation"}
                if basis is None else basis
            ),
        )

    def canonical_csr(matrix):
        result = sparse.csr_matrix(matrix, dtype=np.complex128)
        result.sum_duplicates()
        result.eliminate_zeros()
        result.sort_indices()
        if not np.isfinite(result.data).all():
            raise ValueError("p6 PSTDDM sparse operator contains non-finite entries")
        return result

    def vector_norm(value):
        return float(np.linalg.norm(np.asarray(value, dtype=np.complex128)))

    try:
        comm = request.mesh_data.mesh.comm
        if (
            comm.size != 1
            or np.dtype(PETSc.ScalarType) != np.dtype("complex128")
            or int(request.n_aux) != 612
            or request.static_condensed_system is None
            or request.pstddm_raw_port_columns is None
            or len(request.pstddm_raw_port_columns) != int(request.n_aux)
            or request.A.getSize()[0] != int(request.n_fe) + int(request.n_aux)
        ):
            raise ValueError("p6 Stage-4 source transfer requires the qualified MPI1 complex128 612-mode request")
        V = request.function_space
        cfg = request.config
        mesh_data = request.mesh_data
        trace_constraints = request.static_condensed_system.trace_constraints
        n_trace = int(request.n_fe)
        n_aux = int(request.n_aux)
        full_rows = int(V.dofmap.index_map.size_global * V.dofmap.index_map_bs)
        if trace_constraints.active_rows != n_trace:
            raise ValueError("Stage-4 condensed FE dimension does not match the trace master map")
        if request.static_condensed_system.full_rows != full_rows:
            raise ValueError("Stage-4 static-condensation row count differs from the FE space")

        raw_columns = tuple(request.pstddm_raw_port_columns)
        if any(not isinstance(column, PstddmRawPortColumn) for column in raw_columns):
            raise TypeError("p6 Stage-4 raw port columns must use the exact sparse typed payload")
        if tuple(column.index for column in raw_columns) != tuple(range(n_aux)):
            raise ValueError("p6 Stage-4 raw port columns are not in exact modal order")
        if any(
            np.any(column.raw_C_rows >= full_rows) or np.any(column.raw_D_rows >= full_rows)
            for column in raw_columns
        ):
            raise ValueError("p6 Stage-4 raw C/D row lies outside the original full FE space")

        coordinates = np.asarray(mesh_data.mesh.geometry.x, dtype=np.float64)
        axes = {}
        for name, dim in zip(("x", "y", "z"), range(3), strict=True):
            ordered = np.sort(coordinates[:, dim])
            values = [float(ordered[0])]
            for value in ordered[1:]:
                if float(value) - values[-1] > 1.0e-10:
                    values.append(float(value))
            axes[name] = np.asarray(values, dtype=np.float64)
        if len(axes["z"]) - 1 != 14:
            raise ValueError("p6 Stage-4 diagnostic requires the frozen 14 physical z layers")
        expected_axes = {
            "x": np.asarray(cfg.mesh_axis_x_values, dtype=np.float64),
            "y": np.asarray(cfg.mesh_axis_y_values, dtype=np.float64),
            "z": np.asarray(cfg.mesh_axis_z_values, dtype=np.float64),
        }
        if any(
            axes[name].shape != expected_axes[name].shape
            or not np.allclose(axes[name], expected_axes[name], rtol=0.0, atol=1.0e-10)
            for name in ("x", "y", "z")
        ):
            raise ValueError("actual Stage-4 coordinate axes differ from the frozen h10 config axes")
        actual_counts = tuple(len(axes[name]) - 1 for name in ("x", "y", "z"))
        if actual_counts != (6, 6, 14):
            raise ValueError(f"actual p6 h10 coordinate cell counts differ from (6,6,14): {actual_counts}")
        bounds = balanced_partition_bounds(len(axes["z"]) - 1, 4)
        if bounds != (0, 3, 7, 10, 14):
            raise RuntimeError("floor-balanced N4 bounds no longer match the h10 contract")

        T = canonical_csr(gather_transformation_matrix(request.floquet_data.mpc))
        if T.shape[0] != full_rows:
            raise ValueError("full FE Floquet transformation has the wrong raw row count")
        active = np.setdiff1d(
            np.arange(full_rows, dtype=np.int64),
            np.asarray(request.floquet_data.mpc.slaves, dtype=np.int64),
        )
        if active.size != T.shape[1]:
            raise ValueError("full FE Floquet active rows do not match transformation columns")
        active_identity_error = float(
            sparse.linalg.norm(T[active] - sparse.eye(T.shape[1], dtype=np.complex128, format="csr"))
        )
        if not np.isfinite(active_identity_error) or active_identity_error > 1.0e-13:
            raise RuntimeError(f"full FE active-master identity defect {active_identity_error}")
        n_full = int(T.shape[1])

        raw_c_rows, raw_c_cols, raw_c_values = [], [], []
        raw_d_rows, raw_d_cols, raw_d_values = [], [], []
        reduced_c_rows, reduced_c_cols, reduced_c_values = [], [], []
        reduced_d_rows, reduced_d_cols, reduced_d_values = [], [], []
        raw_digest = hashlib.sha256()
        for column in raw_columns:
            raw_digest.update(
                f"{column.index}:{column.side}:{column.m}:{column.n}:{column.polarization}:{column.normalization:.17g}\n".encode()
            )
            for rows_name, values_name, out_rows, out_cols, out_values, col_index in (
                ("raw_C_rows", "raw_C_values", raw_c_rows, raw_c_cols, raw_c_values, column.index),
                ("raw_D_rows", "raw_D_values", raw_d_cols, raw_d_rows, raw_d_values, column.index),
                ("reduced_C_rows", "reduced_C_values", reduced_c_rows, reduced_c_cols, reduced_c_values, column.index),
                ("reduced_D_rows", "reduced_D_values", reduced_d_cols, reduced_d_rows, reduced_d_values, column.index),
            ):
                rows = np.asarray(getattr(column, rows_name), dtype=np.int64)
                values = np.asarray(getattr(column, values_name), dtype=np.complex128)
                if rows.shape != values.shape or not np.isfinite(values).all():
                    raise ValueError("p6 raw/reduced C/D sparse column is malformed")
                raw_digest.update(rows_name.encode() + b"\0" + rows.astype("<i8", copy=False).tobytes())
                raw_digest.update(values.astype("<c16", copy=False).tobytes())
                out_rows.extend(rows.tolist())
                out_cols.extend([int(col_index)] * len(rows))
                out_values.extend(values.tolist())
            raw_digest.update(np.asarray([column.raw_H, column.reduced_H], dtype="<c16").tobytes())

        C_raw = sparse.csr_matrix(
            (np.asarray(raw_c_values, dtype=np.complex128),
             (np.asarray(raw_c_rows, dtype=np.int64), np.asarray(raw_c_cols, dtype=np.int64))),
            shape=(full_rows, n_aux),
        )
        D_raw = sparse.csr_matrix(
            (np.asarray(raw_d_values, dtype=np.complex128),
             (np.asarray(raw_d_rows, dtype=np.int64), np.asarray(raw_d_cols, dtype=np.int64))),
            shape=(n_aux, full_rows),
        )
        C_full = canonical_csr(T.getH() @ C_raw)
        D_full = canonical_csr(D_raw @ T)
        C_trace = canonical_csr(sparse.csr_matrix(
            (np.asarray(reduced_c_values, dtype=np.complex128),
             (np.asarray(reduced_c_rows, dtype=np.int64), np.asarray(reduced_c_cols, dtype=np.int64))),
            shape=(n_trace, n_aux),
        ))
        D_trace = canonical_csr(sparse.csr_matrix(
            (np.asarray(reduced_d_values, dtype=np.complex128),
             (np.asarray(reduced_d_rows, dtype=np.int64), np.asarray(reduced_d_cols, dtype=np.int64))),
            shape=(n_aux, n_trace),
        ))
        raw_port_nnz_audit = {
            "C": int(C_raw.nnz),
            "D": int(D_raw.nnz),
            "reduced_C": int(C_trace.nnz),
            "reduced_D": int(D_trace.nnz),
        }
        del C_raw, D_raw
        del raw_c_rows, raw_c_cols, raw_c_values
        del raw_d_rows, raw_d_cols, raw_d_values
        del reduced_c_rows, reduced_c_cols, reduced_c_values
        del reduced_d_rows, reduced_d_cols, reduced_d_values
        if any(complex(column.raw_H) != 1.0 + 0.0j for column in raw_columns):
            raise ValueError("the p6 diagnostic requires raw terminal H=I before interior elimination")
        trace_adapter = prepare_trace_master_adapter(trace_constraints, full_rows, owned_only=True)

        cells, midpoints = __import__(
            "src.solvers.fullspace_pml_double_sweep", fromlist=["_cell_midpoint_data"]
        )._cell_midpoint_data(mesh_data.mesh)
        physical_partition = np.searchsorted(axes["z"][np.asarray(bounds)], midpoints[:, 2], side="right") - 1
        if np.any(physical_partition < 0) or np.any(physical_partition >= 4):
            raise RuntimeError("a physical FE cell lies outside the four N4 partitions")

        local_dof_counts = np.asarray(
            [len(V.dofmap.cell_dofs(int(cell))) for cell in cells], dtype=np.int64
        )
        max_local_dofs = int(local_dof_counts.max(initial=0))

        def support_nnz_upper(cell_ids):
            occurrences = np.zeros(full_rows, dtype=np.int64)
            for cell in cell_ids:
                local_dofs = np.asarray(V.dofmap.cell_dofs(int(cell)), dtype=np.int32)
                global_dofs = np.asarray(V.dofmap.index_map.local_to_global(local_dofs), dtype=np.int64)
                np.add.at(occurrences, global_dofs, 1)
            return int(np.minimum(full_rows, occurrences * max_local_dofs).sum())

        full_nnz_upper = support_nnz_upper(cells)
        part_nnz_upper = [
            support_nnz_upper(cells[physical_partition == index]) for index in range(4)
        ]
        max_expansion = int(np.diff(T.indptr).max(initial=0))
        reduced_nnz_upper = min(n_full * n_full, full_nnz_upper * max(1, max_expansion) ** 2)
        csr_bytes = lambda rows, nnz: int(nnz) * 24 + (int(rows) + 1) * 8
        petsc_sparse_bytes = lambda rows, nnz: int(nnz) * (16 + np.dtype(PETSc.IntType).itemsize) + (int(rows) + 1) * np.dtype(PETSc.IntType).itemsize
        mass_assembly_preflight = petsc_sparse_bytes(full_rows, full_nnz_upper) + (512 << 20)
        stage_admit(
            "p6_full_fe_global_mass_cell_support_preflight",
            mass_assembly_preflight,
            {
                "raw_full_FE_rows": full_rows,
                "full_independent_FE_rows": n_full,
                "physical_cells": int(len(cells)),
                "max_cell_raw_dofs": max_local_dofs,
                "cell_support_raw_nnz_upper_bound": full_nnz_upper,
                "floquet_max_row_expansion": max_expansion,
                "transformed_nnz_upper_bound": int(reduced_nnz_upper),
                "incremental_future_bytes": mass_assembly_preflight,
                "estimate_scope": "only the new PETSc matrix and assembly workspace; exact PETSc nz_used gates later CSR/transform allocations",
            },
        )

        u, v = ufl.TrialFunction(V), ufl.TestFunction(V)
        mass_form = fem.form(
            ufl.inner(u, v) * ufl.dx,
            jit_options={"cache_dir": str(cache), "timeout": 300},
            form_compiler_options={"quadrature_degree": 28},
        )
        raw_mass_petsc = fem_petsc.assemble_matrix(mass_form)
        raw_mass_petsc.assemble()
        try:
            inventory = raw_mass_petsc.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
            actual_raw_nnz_float = float(inventory["nz_used"])
            if not np.isfinite(actual_raw_nnz_float) or not actual_raw_nnz_float.is_integer():
                raise RuntimeError("PETSc global mass nnz inventory is not an exact integer")
            actual_raw_nnz = int(actual_raw_nnz_float)
            actual_reduced_nnz_upper = min(
                n_full * n_full, actual_raw_nnz * max(1, max_expansion) ** 2
            )
            actual_conversion_transform = csr_bytes(full_rows, actual_raw_nnz)
            stage_admit(
                "p6_full_fe_global_mass_actual_petsc_inventory_before_copy",
                actual_conversion_transform,
                {
                    "actual_PETSc_nz_used": actual_raw_nnz,
                    "actual_PETSc_matrix_size": list(raw_mass_petsc.getSize()),
                    "raw_CSR_copy_bytes_upper": csr_bytes(full_rows, actual_raw_nnz),
                    "already_resident_PETSc_matrix_recounted": False,
                    "incremental_future_bytes": actual_conversion_transform,
                    "estimate_scope": "one new raw CSR copy only; PETSc matrix is the live cgroup baseline",
                },
            )
            ptr, columns, values = raw_mass_petsc.getValuesCSR()
            raw_mass = sparse.csr_matrix(
                (np.asarray(values).copy(), np.asarray(columns).copy(), np.asarray(ptr).copy()),
                shape=raw_mass_petsc.getSize(),
            )
        finally:
            raw_mass_petsc.destroy()
        raw_mass.sum_duplicates()
        raw_mass.sort_indices()
        actual_intermediate_nnz_upper = min(
            full_rows * n_full, actual_raw_nnz * max(1, max_expansion)
        )
        actual_reduced_nnz_upper = min(
            n_full * n_full, actual_intermediate_nnz_upper * max(1, max_expansion)
        )
        mass_transform_future = (
            csr_bytes(full_rows, actual_intermediate_nnz_upper)
            + csr_bytes(n_full, actual_reduced_nnz_upper)
            + (512 << 20)
        )
        stage_admit(
            "p6_full_fe_global_mass_transform",
            mass_transform_future,
            {
                "actual_raw_CSR_nnz": int(raw_mass.nnz),
                "actual_raw_CSR_bytes": int(raw_mass.data.nbytes + raw_mass.indices.nbytes + raw_mass.indptr.nbytes),
                "already_resident_raw_CSR_recounted": False,
                "incremental_future_bytes": mass_transform_future,
                "transformed_intermediate_nnz_upper_bound": int(actual_intermediate_nnz_upper),
                "transformed_nnz_upper_bound": int(actual_reduced_nnz_upper),
                "estimate_scope": "new intermediate and result CSR plus sparse multiplication workspace; raw CSR is the live cgroup baseline",
            },
        )
        M_full = canonical_csr(T.getH() @ raw_mass @ T)
        del raw_mass
        gc.collect()

        model_spec = SimpleNamespace(
            x_axis_nm=axes["x"],
            y_axis_nm=axes["y"],
            z_axis_nm=axes["z"],
            wavelength_nm=float(getattr(cfg, "wavelength_nm", 13.5)),
            geometry_identity=str(getattr(cfg, "geometry_identity", "stationary_centered_17x20x120_period50x50_zm10_130_v1")),
        )
        p = SimpleNamespace(
            V=V,
            cfg=cfg,
            mesh_data=mesh_data,
            floquet=request.floquet_data,
            model_spec=model_spec,
        )
        system = SimpleNamespace(
            p=p,
            M=M_full,
            T=T,
            active=active,
            C=C_full,
            D=D_full,
            A=None,
            dtn=SimpleNamespace(modes=raw_columns),
            cache=cache,
            full_rows=full_rows,
            raw_port_columns=raw_columns,
            require_raw_port_map=True,
            partition_bounds=bounds,
            layer_mass_raw_nnz_upper=part_nnz_upper,
            layer_mass_max_expansion=max_expansion,
        )

        base_runtime = _default_runtime()
        shared_api, shim_identity = load_public_shim(
            output / "mumps_symbolic", compiler_command=compiler_command
        )

        def shared_load_shim(_directory, *, compiler_command):
            del compiler_command
            return shared_api, shim_identity

        runtime = _RuntimePorts(
            matrix_from_csr=base_runtime.matrix_from_csr,
            index_dtype=base_runtime.index_dtype,
            load_shim=shared_load_shim,
            factor_factory=base_runtime.factor_factory,
            budget_function=base_runtime.budget_function,
            compiler_command=lambda: compiler_command,
        )

        def make_factor(matrix, label):
            factor_directory = output / "pstddm_factors" / str(label)
            try:
                owner = ExactBoundedAuxiliaryFactor(
                    canonical_csr(matrix),
                    observe=observe,
                    admit=lambda name, future, *, estimate_basis: stage_admit(name, future, estimate_basis),
                    directory=factor_directory,
                    available_floor_bytes=int(available_floor_bytes),
                    comm=PETSc.COMM_SELF,
                    mumps_task_limit_bytes=int(task_limit_bytes),
                    future_co_resident_reserve_bytes=4 << 30,
                    probe_relative_limit=1.0e-9,
                    runtime=runtime,
                )
            except BaseException:
                for failed in FAILED_AUXILIARY_OWNERS:
                    if getattr(failed, "_directory", None) == factor_directory and failed not in owners:
                        owners.append(failed)
                raise
            owners.append(owner)
            return owner

        def partition_gate(name, future_bytes, *, estimate_basis=None):
            return stage_admit(
                name,
                future_bytes,
                estimate_basis if estimate_basis is not None else {
                    "source": "existing pstddm_native.build_partition explicit p6 gate"
                },
            )

        from .pstddm_condensed_adapter import balanced_partition_bounds as _balanced_bounds
        if tuple(bounds) != _balanced_bounds(14, 4):
            raise RuntimeError("Stage-4 adapter and native partition bounds disagree")
        core, pairs, partition_metadata = build_partition(
            system, 4, partition_gate, factor_factory=make_factor
        )
        del system
        del raw_columns
        if len(pairs) != 3 or len(owners) != 4:
            raise RuntimeError("p6 N4 requires exactly one global mass factor and three local factors")
        if float(partition_metadata["mass_partition_relative"]) > 1.0e-12:
            raise RuntimeError("full-FE layer mass partition exceeds the original 1e-12 limit")
        if float(partition_metadata["reconstruction_relative"]) > 1.0e-10:
            raise RuntimeError("full-FE conforming reconstruction exceeds its original 1e-10 limit")
        if not all(
            max((float(value) for value in pair.weak_product_errors), default=0.0) <= 1.0e-11
            for pair in pairs
        ):
            raise RuntimeError("an independent weak curl-product identity exceeded 1e-11")

        def petsc_csr(matrix):
            info = matrix.getInfo(PETSc.Mat.InfoType.GLOBAL_SUM)
            nnz = int(round(float(info["nz_used"])))
            copy_bytes = nnz * (16 + np.dtype(PETSc.IntType).itemsize) + (matrix.getSize()[0] + 1) * np.dtype(PETSc.IntType).itemsize
            stage_admit(
                "p6_condensed_augmented_operator_to_scipy",
                copy_bytes + (256 << 20),
                {
                    "actual_PETSc_nz_used": nnz,
                    "matrix_shape": list(matrix.getSize()),
                    "estimate_scope": "actual Stage-4 augmented CSR inventory before NumPy/SciPy copy",
                },
            )
            ptr, columns, values = matrix.getValuesCSR()
            return canonical_csr(sparse.csr_matrix(
                (np.asarray(values).copy(), np.asarray(columns).copy(), np.asarray(ptr).copy()),
                shape=matrix.getSize(),
            ))

        operator = petsc_csr(request.A)
        expected_C = operator[:n_trace, n_trace:]
        expected_D = operator[n_trace:, :n_trace]
        def relative_sparse_difference(left, right):
            return float(sparse.linalg.norm(left - right) / max(float(sparse.linalg.norm(right)), 1.0))

        C_bridge_defect = relative_sparse_difference(expected_C, C_trace)
        D_bridge_defect = relative_sparse_difference(expected_D, D_trace)
        if max(C_bridge_defect, D_bridge_defect) > 1.0e-12:
            raise RuntimeError(
                f"typed raw/reduced port blocks differ from Stage-4 augmented operator: "
                f"C={C_bridge_defect}, D={D_bridge_defect}"
            )
        del C_trace, D_trace
        rhs = np.asarray(request.b.getArray(readonly=True), dtype=np.complex128).copy()
        if rhs.shape != (n_trace + n_aux,) or not np.isfinite(rhs).all():
            raise ValueError("Stage-4 augmented right-hand side is invalid")

        bridge_statistics = []

        def lift_trace_to_full_independent(trace_dual):
            lift_rows, lift_values = trace_adapter.lift_dual(trace_dual)
            raw_full_dual = np.zeros(full_rows, dtype=np.complex128)
            np.add.at(raw_full_dual, lift_rows, lift_values)
            return np.asarray(T.getH() @ raw_full_dual, dtype=np.complex128).ravel()

        def restrict_full_independent_primal(full_primal):
            raw_full_primal = np.asarray(T @ full_primal, dtype=np.complex128).ravel()
            return trace_adapter.restrict_primal(raw_full_primal)

        last_transfer = {}

        def source_transfer(full_rhs):
            transfer = core.apply(full_rhs)
            last_transfer["result"] = transfer
            return transfer.field

        def condensed_port_bridge(residual):
            values = np.asarray(residual, dtype=np.complex128)
            if values.shape != (n_trace + n_aux,) or not np.isfinite(values).all():
                raise ValueError("condensed Stage-4 port residual has the wrong finite layout")
            trace_primal, auxiliary_dual, full_primal = apply_full_fe_port_bridge(
                values[:n_trace],
                values[n_trace:],
                full_C=C_full,
                full_D=D_full,
                lift_trace_dual=lift_trace_to_full_independent,
                source_transfer=source_transfer,
                restrict_trace_primal=restrict_full_independent_primal,
            )
            transfer = last_transfer.pop("result")
            bridge_statistics.append({
                "apply_index": len(bridge_statistics) + 1,
                "full_FE_source_transfer": transfer.statistics,
                "condensed_trace_dual_master_lift_nnz": int(len(trace_adapter.owned_original_rows)),
                "full_FE_C_times_auxiliary_subtracted_before_transfer": True,
                "full_FE_D_times_full_primal_subtracted_after_transfer": True,
                "raw_FE_dual_interior_rows_are_zero_before_full_C": True,
                "auxiliary_block_enters_mass_layers": False,
                "trace_primal_recovered_from_full_FE": True,
                "full_FE_primal_norm": vector_norm(full_primal),
            })
            return np.concatenate((trace_primal, auxiliary_dual))

        initial_solution = condensed_port_bridge(rhs)
        initial_residual = true_residual(operator, initial_solution, rhs)

        def right_preconditioner(residual):
            return condensed_port_bridge(residual)

        solution, fgmres_audit = flexible_gmres(
            operator,
            rhs,
            right_preconditioner,
            initial_solution,
            restart=30,
            max_iterations=100,
            tolerance=1.0e-8,
        )
        final_residual = true_residual(operator, solution, rhs)
        fgmres_audit.update({
            "initial_source_transfer_condensed_relative_residual": initial_residual,
            "final_original_condensed_augmented_relative_residual": final_residual,
            "final_original_condensed_augmented_gate_limit": 1.0e-8,
            "final_original_condensed_augmented_gate_pass": bool(
                np.isfinite(final_residual) and final_residual <= 1.0e-8
            ),
            "outer_rhs_and_nonzero_initial_follow_existing_candidate_call": True,
            "initial_iterate_is_one_source_transfer_apply_from_zero": True,
            "source_transfer_FE_dimension": n_full,
            "condensed_trace_FE_dimension": n_trace,
            "auxiliary_dimension": n_aux,
        })
        atomic_json(output / "pstddm_source_transfer_and_fgmres.json", jsonable(fgmres_audit))
        atomic_json(output / "pstddm_source_transfer_applies.json", jsonable(bridge_statistics))

        x = request.b.duplicate()
        x.setValues(
            np.arange(n_trace + n_aux, dtype=PETSc.IntType),
            np.asarray(solution, dtype=PETSc.ScalarType),
            addv=PETSc.InsertMode.INSERT_VALUES,
        )
        x.assemble()

        cleanup_failures = close_owners()
        if cleanup_failures:
            raise RuntimeError("one or more exact MUMPS factor owners failed to close") from cleanup_failures[0]
        factor_audits = [jsonable(owner.audit) for owner in owners]
        record.update({
            "status": "solver_returned_candidate",
            "actual_axis_cell_counts": [len(axes[name]) - 1 for name in ("x", "y", "z")],
            "actual_z_planes_nm": axes["z"].tolist(),
            "partition_bounds_cell_indices": list(bounds),
            "partition_bounds_z_nm": axes["z"][list(bounds)].tolist(),
            "full_FE_raw_rows": full_rows,
            "full_FE_independent_rows": n_full,
            "condensed_trace_rows": n_trace,
            "mode_count": n_aux,
            "global_full_FE_mass_raw_cell_support_nnz_upper": full_nnz_upper,
            "global_full_FE_mass_actual_PETSc_nz_used": actual_raw_nnz,
            "global_full_FE_mass_independent_nnz": int(M_full.nnz),
            "partition_mass_cell_support_nnz_upper": part_nnz_upper,
            "full_FE_active_master_identity_relative_defect": active_identity_error,
            "partition_metadata": partition_metadata,
            "raw_port_columns_sha256": raw_digest.hexdigest(),
            "raw_port_nnz": {
                **raw_port_nnz_audit,
            },
            "condensed_port_bridge_block_defects": {
                "reduced_C_capture_vs_stage4_inserted_block_relative": C_bridge_defect,
                "reduced_D_capture_vs_stage4_inserted_block_relative": D_bridge_defect,
                "full_FE_bridge_uses_raw_C_D": True,
                "raw_H_identity_checked_before_interior_elimination": True,
                "reduced_H_identity_assumed": False,
            },
            "fgmres": fgmres_audit,
            "source_transfer_apply_count": len(bridge_statistics),
            "factor_count": len(owners),
            "factor_owners_closed_before_native_full_residual": True,
            "factor_audits": factor_audits,
            "global_target_maxwell_factor_count": 0,
            "global_full_FE_mass_factor_count": 1,
            "local_pair_factor_count": 3,
            "no_direct_solution_warm_start": True,
            "official_result": False,
        })
        persist("solver_returned_candidate")

        from .dtn_port_3d import Stage4ExternalLinearSolverSnapshot
        return Stage4ExternalLinearSolverSnapshot(
            x=x,
            converged_reason=2 if fgmres_audit["passed"] else -3,
            iterations=int(fgmres_audit["iterations"]),
            reported_relative_residual=float(final_residual),
            condensed_true_residual=float(final_residual),
            full_augmented_true_residual=None,
            ksp_type="FGMRES",
            pc_type="PSTDDM_FullFE_PureSourceTransfer_N4",
            residual_limit=1.0e-8,
            no_global_factor=False,
            solver_profile="pstddm_p6_h10_source_transfer_diagnostic_v1",
            assembled_matrix_released_before_solve=False,
            reduced_residual_norm=vector_norm(rhs - operator @ solution),
            no_global_target_maxwell_factor=True,
            global_mass_factor_count=1,
            local_auxiliary_factor_count=3,
            diagnostic_only=True,
        )
    except BaseException as error:
        active_error = error
        try:
            persist("failed", error)
        except BaseException as persist_error:
            error.add_note("PSTDDM diagnostic record could not be written: " + repr(persist_error))
        raise
    finally:
        cleanup_failures = close_owners()
        if cleanup_failures:
            for failure in cleanup_failures[1:]:
                cleanup_failures[0].add_note("additional factor cleanup failure: " + repr(failure))
            record["factor_cleanup_failures"] = [repr(error) for error in cleanup_failures]
            record["factor_owners_closed_before_native_full_residual"] = False
            try:
                persist("cleanup_failed", cleanup_failures[0])
            except BaseException as persist_error:
                cleanup_failures[0].add_note("cleanup failure record could not be written: " + repr(persist_error))
            if active_error is not None:
                active_error.add_note("additional factor cleanup failure: " + repr(cleanup_failures[0]))
            else:
                raise cleanup_failures[0]
        else:
            try:
                persist(record.get("status", "failed"))
            except BaseException as persist_error:
                if active_error is not None:
                    active_error.add_note("final factor owner state could not be persisted: " + repr(persist_error))
                else:
                    raise
