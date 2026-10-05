"""Fresh finite two-cell assembly adapter for the published all-four-q inverse.

Physical modes are generated once on the original period. Their already MPC
processed sparse C/D functionals are folded with the published native dual and
functional transports. No quotient-period mode generator, full-period Schur or
reference scientific state is read. Only two local 40-cell condensed systems
and all four bounded branch factors are built.
"""
from dataclasses import replace
from types import SimpleNamespace
import gc
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import splu

from .scattering_y_orbit_reuse import (collect_y_orbit_entities,build_y_orbit_layout,
    trace_layout_coordinates,TwoCellNativeTransport,FullOriginalAction)


class PhaseConfiguration:
    """Explicit local MPC wrap; original physical ky is unchanged."""
    def __init__(self,cfg,phase):self.cfg,self.phase=cfg,complex(phase)
    def __getattr__(self,name):
        return self.phase if name=='floquet_phase_y' else getattr(self.cfg,name)


def quotient_setup(cfg,axes,tau):
    from mpi4py import MPI
    from dolfinx import fem,default_real_type
    from basix.ufl import element
    from src.geometry.mesh_builder_3d import _structured_hexa_mesh,_mark_boundary_facets,_mark_cells
    from src.constraints.floquet_3d import build_double_floquet_mpc
    mesh=_structured_hexa_mesh(MPI.COMM_SELF,axes['x'],axes['y'],axes['z'],
                              preserve_input_partition=cfg.stage4_preserve_structured_input_partition)
    facets,_=_mark_boundary_facets(mesh,cfg);cells=_mark_cells(mesh,cfg)
    V=fem.functionspace(mesh,element('N1curl',mesh.basix_cell(),4,dtype=default_real_type))
    data=SimpleNamespace(mesh=mesh,facet_tags=facets,cell_tags=cells)
    floquet=build_double_floquet_mpc(V,data,PhaseConfiguration(cfg,tau))
    return {'mesh':mesh,'mesh_data':data,'spaces':{4:V},'floquets':{4:floquet}}


def folded_bundle(original,setup,cfg,transport,ids):
    from .fullspace_dtn_action import FullspaceDtnModeFunctional,FullspaceDtnCarrier,build_fullspace_dtn_action
    from .fullspace_same_mesh_hcurl_pmg_physical import _build_split_volume_action
    from .fullspace_physical_action import FullspacePhysicalAction
    full=transport.full;local=transport.local;entries=[]
    for index,mode_id in enumerate(ids):
        entry=original['dtn_action'].carrier.entries[mode_id]
        c=np.zeros(full.full_rows,complex);c[entry.coupling_rows]=entry.coupling_values
        d=np.zeros(full.full_rows,complex);d[entry.projection_rows]=entry.projection_values
        lc=transport.fold_raw_coupling(c[full.independent]);ld=transport.fold_raw_projection(d[full.independent])
        cr=local.independent[np.flatnonzero(lc!=0)];dr=local.independent[np.flatnonzero(ld!=0)]
        identity={**entry.mode_identity,'mode_index':index,'projection_denominator':entry.normalization_h/2}
        entries.append(FullspaceDtnModeFunctional(entry.mode_key,cr,lc[lc!=0],dr,ld[ld!=0],
                                                entry.normalization_h/2,identity))
    carrier=FullspaceDtnCarrier(entries,global_rows=local.full_rows,ownership_range=(0,local.full_rows),
                                slave_rows=setup['floquets'][4].mpc.slaves,comm=setup['mesh'].comm)
    dtn=build_fullspace_dtn_action(carrier,comm=setup['mesh'].comm)
    volume=_build_split_volume_action(setup['mesh_data'],cfg,setup['spaces'][4],setup['floquets'][4],jit_options={})
    action=FullspacePhysicalAction(volume,dtn)
    return {'setup':setup,'cfg':cfg,'degree':4,'action':action,'physical_action':action,
            'volume_action':volume,'dtn_action':dtn,'modes':tuple(original['modes'][i] for i in ids),
            'mode_rows':tuple(e.mode_identity for e in entries),'mode_sha256':carrier.mode_manifest_sha256,
            'dtn_quadrature_degree':original['dtn_quadrature_degree'],
            'incident_projections':tuple(original['incident_projections'][i] for i in ids)}


class ModalFactor:
    def __init__(self,maps,factors,journal,ports):
        self.maps,self.factors,self.journal=maps,factors,journal
        self.port_rhs=np.zeros(ports,complex)
    def solve_repeated(self,b,x):
        rhs=b.array.copy();rhs[-len(self.port_rhs):]+=self.port_rhs
        x.array[:]=sum(q@f.solve(np.asarray(q.conj().T@rhs)) for q,f in zip(self.maps,self.factors,strict=True))
        self.journal.calls['factor']+=len(self.factors)


class TwoCellInverse:
    def __init__(self,original,journal):
        from .scattering_anchor import condense,relative
        from .scattering_anchor_scope import plan_record
        self.original,self.journal=original,journal;self.sectors=[];self.calls=0
        cfg=original['cfg'];axes=plan_record()['physical_descriptor']['geometry']['axes_nm']
        self.entities=collect_y_orbit_entities(original['setup']['spaces'][4],original['setup']['floquets'][4],cfg,axes)
        self.layout=SimpleNamespace(independent=self.entities.independent,full_rows=self.entities.full_rows)
        local_axes={**axes,'y':axes['y'][:3]}
        local_cfg=replace(cfg,period_y=cfg.period_y/2,grating_width_y=cfg.grating_width_y/2,
                          mesh_axis_y_values=tuple(local_axes['y']),mesh_axis_cell_counts=(4,2,5))
        self.checks=[]
        try:
            for b in (0,1):
                eta=np.exp(1j*(cfg.ky.real*cfg.period_y+2*np.pi*b)/4);tau=eta**2
                with journal.measured(f'two_cell_{b}_setup_carrier'):
                    setup=quotient_setup(local_cfg,local_axes,tau)
                    entities=collect_y_orbit_entities(setup['spaces'][4],setup['floquets'][4],local_cfg,local_axes)
                    transport=TwoCellNativeTransport(self.entities,entities,twist_index=b,eta=eta,
                        global_phase=cfg.floquet_phase_y,global_ky=cfg.ky,global_period_y=cfg.period_y)
                    ids=np.array([i for i,m in enumerate(original['modes']) if int(m.n)%2==b],dtype=int)
                    bundle=folded_bundle(original,setup,local_cfg,transport,ids)
                    sector={'transport':transport,'bundle':bundle,'ids':ids,'inverse':None,'factors':[],'maps':[]}
                    self.sectors.append(sector)
                system,inverse=condense(bundle,journal,expected=(8940,3616,4320))
                sector['inverse']=inverse
                with journal.measured(f'two_cell_{b}_mapping_and_q_factors'):
                    layout=build_y_orbit_layout(setup['spaces'][4],setup['floquets'][4],local_cfg,local_axes,
                                                wrap_phase_y=tau,cell_phase_y=eta)
                    trace=trace_layout_coordinates(layout,system,allocation_gate=journal.allocation)
                    qt=(trace['R_t']@trace['F_t']).tocsr()
                    ip,ix,vd=system.matrix.getValuesCSR();csr=sparse.csr_matrix((vd,ix,ip),shape=system.matrix.getSize())
                    h=np.array([e.normalization_h for e in bundle['dtn_action'].carrier.entries])
                    for branch in (0,1):
                        local_ids=np.array([i for i,m in enumerate(bundle['modes']) if ((int(m.n)-b)//2)%2==branch])
                        pm=sparse.csr_matrix((1/np.sqrt(h[local_ids]),(local_ids,np.arange(len(local_ids)))),shape=(len(ids),len(local_ids)))
                        qm=sparse.block_diag((qt[:,branch*1808:(branch+1)*1808],pm),format='csr')
                        matrix=(qm.conj().T@csr@qm).tocsc();q=b+2*branch
                        if matrix.shape!=(1884 if q==0 else 1960,)*2:raise ValueError('complete q dimension/port inventory')
                        journal.allocation('q_'+str(q)+'_factor',{'matrix_payload_bytes':sum(a.nbytes for a in (matrix.data,matrix.indices,matrix.indptr)), 'workspace_bytes':128*2**20})
                        factor=splu(matrix,permc_spec='COLAMD');w=np.cos(np.arange(matrix.shape[0])*.37)+1j*np.sin(np.arange(matrix.shape[0])*.23)
                        x=factor.solve(w);err=relative(matrix@x-w,w)
                        if err>1e-10:raise ValueError('two-cell actual q factor original residual')
                        sector['factors'].append(factor);sector['maps'].append(qm)
                        self.checks.append({'q':q,'rows':matrix.shape[0],'aliases':len(local_ids),'residual':err,'nnz':matrix.nnz})
                    inverse.factor=ModalFactor(sector['maps'],sector['factors'],journal,len(ids))
                    del csr,qt,trace,layout,matrix,vd,ix,ip
                    # Only local recovery and q factors persist, no local global matrix.
                    system.matrix.destroy();system.matrix=None
                    journal.event('two_cell_matrix_released',twist=b,ports=len(ids),transport=transport.audit)
            if sorted(i for s in self.sectors for i in s['ids'])!=list(range(532)):raise ValueError('two sectors must cover all532 aliases once')
        except BaseException:
            self.destroy();raise

    def apply_augmented(self,rhs,port_rhs=None):
        from petsc4py import PETSc
        rhs=np.asarray(rhs,complex);g=np.zeros(532,complex) if port_rhs is None else np.asarray(port_rhs,complex)
        if rhs.shape!=(15872,) or g.shape!=(532,) or not np.isfinite(rhs).all() or not np.isfinite(g).all():raise ValueError('all original FE and port RHS required')
        u=np.zeros(15872,complex);alpha=np.empty(532,complex)
        for s in self.sectors:
            tr,inv=s['transport'],s['inverse'];ids=s['ids']
            r=PETSc.Vec().createSeq(tr.local.full_rows,comm=PETSc.COMM_SELF);r.set(0);r.array[tr.local.independent]=tr.fold_dual(rhs)
            inv.factor.port_rhs[:]=g[ids]/np.sqrt(2)
            if r.norm()==0 and np.any(g[ids]):
                r.destroy();raise NotImplementedError('zero volume nonzero auxiliary RHS is only a small algebra witness; not a physical RHS')
            try:
                x=inv.apply(r)
                try:u+=tr.lift_primal(x.array[tr.local.independent]);alpha[ids]=inv.last_port_solution/np.sqrt(2)
                finally:x.destroy()
            finally:r.destroy()
        self.calls+=1
        return u,alpha
    def apply_array(self,rhs):return self.apply_augmented(rhs)[0]
    def apply(self,_pc,b,x):x.array[:]=self.apply_array(b.array)
    def destroy(self):
        from .fullspace_same_mesh_hcurl_pmg_physical import destroy_same_mesh_physical_action
        for s in self.sectors:
            if s['inverse'] is not None:s['inverse'].factor=None;s['inverse'].destroy();s['inverse']=None
            s['factors'].clear();s['maps'].clear();destroy_same_mesh_physical_action(s['bundle'])
        self.sectors.clear();gc.collect()

    def qualify(self,folder):
        from .scattering_anchor import relative,save_arrays
        from petsc4py import PETSc
        rng=np.random.default_rng(49003)
        manufactured=rng.standard_normal(15872)+1j*rng.standard_normal(15872)
        h=np.array([e.normalization_h for e in self.original['dtn_action'].carrier.entries])
        # All modes retained. Unit normalized port coordinates have bounded
        # physical boundary amplitude, unlike unit raw g on tiny evanescent H.
        manufactured_alpha=(rng.standard_normal(532)+1j*rng.standard_normal(532))/np.sqrt(h)
        v0=PETSc.Vec().createSeq(self.layout.full_rows,comm=PETSc.COMM_SELF);v0.set(0);v0.array[self.layout.independent]=manufactured
        try:
            volume0=self.original['volume_action'].apply(v0).array.copy();coupling0=np.zeros_like(volume0);p0=[]
            for entry,alpha0 in zip(self.original['dtn_action'].carrier.entries,manufactured_alpha,strict=True):
                np.add.at(coupling0,entry.coupling_rows,entry.coupling_values*alpha0)
                p0.append(np.dot(entry.projection_values,v0.array[entry.projection_rows]))
            b=(volume0+coupling0)[self.layout.independent]
            g=-np.array(p0)+h*manufactured_alpha
        finally:v0.destroy()
        action=FullOriginalAction(self.original['physical_action'],self.layout)
        try:
            u,alpha=self.apply_augmented(b,g)
            v=PETSc.Vec().createSeq(self.layout.full_rows,comm=PETSc.COMM_SELF);v.set(0);v.array[self.layout.independent]=u
            try:
                volume=self.original['volume_action'].apply(v).array.copy();coupling=np.zeros_like(volume);p=[];h=[]
                for e,a in zip(self.original['dtn_action'].carrier.entries,alpha,strict=True):
                    np.add.at(coupling,e.coupling_rows,e.coupling_values*a);p.append(np.dot(e.projection_values,v.array[e.projection_rows]));h.append(e.normalization_h)
                residual=b-(volume+coupling)[self.layout.independent];port_residual=g+np.asarray(p)-np.asarray(h)*alpha
            finally:v.destroy()
            x=self.apply_array(b);defect=relative(action.apply(x)-b,b)
            arrays=save_arrays(folder/'all4q_witness.npz',FE_rhs=b,port_rhs=g,u=u,port=alpha,
                              augmented_residual=residual,port_residual=port_residual,eliminated_u=x,
                              manufactured_u=manufactured,manufactured_port=manufactured_alpha,port_H=h)
            norms={'original_FE':relative(residual,b),'original_port':relative(port_residual,g+np.asarray(p)),
                   'eliminated_inverse':defect,'manufactured_FE_solution':relative(u-manufactured,manufactured),
                   'normalized_port_solution':relative(np.sqrt(h)*(alpha-manufactured_alpha),np.sqrt(h)*manufactured_alpha)}
            self.journal.event('all4q_manufactured_actual_norms',norms=norms,port_H_min=float(h.min()),port_H_max=float(h.max()))
            self.journal.calls['A']+=action.calls
            if not all(np.isfinite(v) for v in norms.values()) or max(norms.values())>1e-10:raise ValueError('all4q real native nonzero interior/port inverse qualification')
            return {'norms':norms,'arrays':arrays,'branches':self.checks,'all_q':[0,1,2,3],
                    'native_full_rows':17204,'complete_independent':15872,'two_local_FE_rows':7936}
        finally:action.close()
