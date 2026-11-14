"""Boundary-plane normalized outgoing DtN blocks for a scattered unknown.

A_FE E + C q = b_contrast; D E + q = 0. No incident port injection.
Raw original-FE C/D are retained without threshold pruning for independent
residual checks. Condensing interiors must transform these blocks exactly or
prove their tangential trace is structurally zero before projection.
"""
from dataclasses import dataclass
import hashlib
import json
from math import floor, pi
import numpy as np

@dataclass
class DtnBlocks:
    C: object
    D: object
    auxiliary_identity: object
    auxiliary_rhs: np.ndarray
    modes: list
    metadata: dict

def normalized_columns(vx,vy,mode,cfg):
    """Pure algebra from native component loads. No small-entry cutoff."""
    normal=np.asarray((0.,0.,1. if mode.side=='top' else -1.))
    traction=np.cross(1j*np.cross(mode.k_vector,mode.e_vector),normal)
    c=-(traction[0]*vx+traction[1]*vy)
    ell=mode.e_vector[0]*vx+mode.e_vector[1]*vy
    area=(cfg.x_max-cfg.x_min)*(cfg.y_max-cfg.y_min)
    denominator=float(area*mode.electric_tangential_norm_sq)
    if not np.isfinite(denominator) or denominator<=0:raise ValueError('Invalid mode normalization')
    d=-np.conj(ell)/denominator
    if not np.isfinite(c).all() or not np.isfinite(d).all():raise FloatingPointError('Nonfinite surface block')
    return c,d


def _complex_pair(value):
    number = complex(value)
    return [float(number.real), float(number.imag)]


def _mode_record(index, mode):
    return {
        "index": int(index), "side": mode.side, "m": int(mode.m), "n": int(mode.n),
        "polarization": mode.polarization, "propagating": bool(mode.propagating),
        "rayleigh_warning": bool(mode.rayleigh_warning),
        "alpha": _complex_pair(mode.alpha), "gamma": _complex_pair(mode.gamma),
        "beta": _complex_pair(mode.beta), "refractive_index": _complex_pair(mode.refractive_index),
        "vertical_sign": int(mode.vertical_sign),
        "e_vector": [_complex_pair(value) for value in mode.e_vector],
        "k_vector": [_complex_pair(value) for value in mode.k_vector],
        "h_vector": [_complex_pair(value) for value in mode.h_vector],
        "electric_tangential_norm_sq": float(mode.electric_tangential_norm_sq),
        "power_per_unit_amplitude": float(mode.power_per_unit_amplitude),
    }


def _sparse_sha256(matrix):
    canonical = matrix.tocsr(copy=True)
    canonical.sort_indices()
    digest = hashlib.sha256()
    digest.update(np.asarray(canonical.shape, dtype=np.int64).tobytes())
    for value in (canonical.indptr, canonical.indices, canonical.data):
        digest.update(np.ascontiguousarray(value).tobytes())
    return digest.hexdigest()

def assemble_dtn_blocks(problem, *, log=print, per_mode=None):
    """Original unconstrained FE surface blocks, MPI1 only.

    Optional per_mode receives (j,mode,c,d) during assembly. The caller can
    build reduced blocks while still retaining raw blocks for the final full
    original-coordinate action. This function never imposes volume-source or
    FE boundary conditions and never calls a solver.
    """
    from scipy.sparse import csc_matrix,identity
    from src.common.modes_3d import outgoing_port_modes_3d
    from src.solvers.dtn_port_3d import _ReusableSurfaceComponentAssembler
    cfg,md,V=problem.cfg,problem.mesh_data,problem.V
    if cfg.use_pml or cfg.stage4_boundary_model!='dtn_port':raise ValueError('DtN only')
    if md.mesh.comm.size!=1:raise ValueError('MPI1 only')
    modes=list(outgoing_port_modes_3d(cfg))
    if not modes:raise ValueError('DtN inventory must contain at least one mode')
    mode_records = [_mode_record(index, mode) for index, mode in enumerate(modes)]
    assemblers={}
    for side,tag,z in [('top',cfg.tags.z_max,cfg.physical_z_max),('bottom',cfg.tags.z_min,cfg.physical_z_min)]:
        for component in (0,1):
            assemblers[side,component]=_ReusableSurfaceComponentAssembler(
                V,md,tag,component,quadrature_degree=28,boundary_reference_z=float(z))
    n=V.dofmap.index_map.size_global*V.dofmap.index_map_bs
    c_data=[];c_rows=[];c_ptr=[0];d_data=[];d_rows=[];d_ptr=[0]
    previous=None;components=None;count=0
    for j,mode in enumerate(modes):
        key=(mode.side,mode.m,mode.n,complex(mode.k_vector[2]))
        if key!=previous:
            values=[]
            for component in (0,1):
                vec=assemblers[mode.side,component].assemble_unconstrained_vector(mode)
                try:values.append(np.asarray(vec.array_r,dtype=np.complex128).copy())
                finally:vec.destroy()
            components=values;previous=key;count+=2
        c,d=normalized_columns(*components,mode,cfg)
        if c.shape!=(n,) or d.shape!=(n,):raise ValueError('Raw FE layout mismatch')
        ri=np.flatnonzero(c!=0);ci=np.flatnonzero(d!=0)
        c_rows.extend(ri);c_data.extend(c[ri]);c_ptr.append(len(c_data))
        d_rows.extend(ci);d_data.extend(d[ci]);d_ptr.append(len(d_data))
        if per_mode is not None:per_mode(j,mode,c,d)
        if log is not None and (j+1)%50==0:log(f'DtN raw boundary blocks {j+1}/{len(modes)}')
    C=csc_matrix((np.asarray(c_data),np.asarray(c_rows),np.asarray(c_ptr)),shape=(n,len(modes)))
    # d lists one modal row, stored as a column then transposed WITHOUT conj.
    D=csc_matrix((np.asarray(d_data),np.asarray(d_rows),np.asarray(d_ptr)),shape=(n,len(modes))).T.tocsr()
    serialized_modes=json.dumps(mode_records,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    side_counts={}
    for side in ('top','bottom'):
        selected=[mode for mode in modes if mode.side==side]
        side_counts[side]={
            'mode_count':len(selected),
            'propagating_mode_count':sum(bool(mode.propagating) for mode in selected),
            'evanescent_mode_count':sum(not bool(mode.propagating) for mode in selected),
            'rayleigh_warning_mode_count':sum(bool(mode.rayleigh_warning) for mode in selected),
        }
    m_max=max(abs(mode.m) for mode in modes)
    n_max=max(abs(mode.n) for mode in modes)
    index_max=max(abs(complex(cfg.n_air)),abs(complex(cfg.substrate_index)))
    auto_max_m=floor((index_max*cfg.k0+abs(cfg.kx))*cfg.period_x/(2*pi)+1e-12)
    auto_max_n=floor((index_max*cfg.k0+abs(cfg.ky))*cfg.period_y/(2*pi)+1e-12)
    model = getattr(problem, 'model_spec', None)
    return DtnBlocks(C,D,identity(len(modes),dtype=np.complex128,format='csr'),
        np.zeros(len(modes),dtype=np.complex128),modes,
        {'gauge':'boundary_plane','m_max':m_max,'n_max':n_max,'n_aux':len(modes),
         'mode_count':len(modes),
         'auto_max_m':auto_max_m,'auto_max_n':auto_max_n,
         'selected_m_max':m_max,'selected_n_max':n_max,
         'propagating_mode_count':sum(bool(mode.propagating) for mode in modes),
         'evanescent_mode_count':sum(not bool(mode.propagating) for mode in modes),
         'rayleigh_warning_mode_count':sum(bool(mode.rayleigh_warning) for mode in modes),
         'side_counts':side_counts,
         'order_padding':getattr(model,'dtn_order_padding',None),
         'ordered_modes_sha256':hashlib.sha256(serialized_modes).hexdigest(),
         'ordered_mode_records':mode_records,
         'C_sha256':_sparse_sha256(C),'D_sha256':_sparse_sha256(D),
         'C_shape':list(C.shape),'D_shape':list(D.shape),
         'C_nnz':int(C.nnz),'D_nnz':int(D.nnz),
         'surface_quadrature_degree':28,'component_assemblies':count,
         'incident_port_source':'zero','unknown':'scattered_against_analytic_flat_interface',
         'cutoff_policy':'exact_nonzero_only_no_numeric_threshold',
         'raw_original_fe_blocks':True,
         'compiled_surface_identities':{f'{side}_{k}':obj.compiled_gauss_identity
             for (side,k),obj in assemblers.items()}})
