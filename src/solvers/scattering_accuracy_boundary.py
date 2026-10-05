"""Complete finite-port quadrature without high-q native UFL expansion.

The original native assembler remains the low-q oracle. Every cell basis
function and literal Floquet dual is retained; exactly zero entries alone may
be omitted from storage. The two-dimensional Basix integral is independent
of the bounded polynomial/separable production integral.
"""
from types import SimpleNamespace
from time import perf_counter
import numpy as np

from src.solvers.scattering_anchor import relative, save_arrays


class SurfaceComponents:
    def __init__(self, space, mpc, cfg, q, *, method='basix2d', phase_carrier=None):
        from src.solvers.target_boundary_witness import NativeFacetTiles
        from src.solvers.directional_boundary import FacetPolynomial
        self.tiles = NativeFacetTiles(space,mpc,cfg,(),q,'V50_EXACT_FULL_FACE')
        self.polynomial = FacetPolynomial(space.element.basix_element) if method=='separable' else None
        self.space,self.mpc,self.cfg,self.q,self.method=space,mpc,cfg,q,method
        self.phase_carrier = np.zeros(3) if phase_carrier is None else np.asarray(phase_carrier, dtype=float)
        if self.phase_carrier.shape != (3,) or not np.all(np.isfinite(self.phase_carrier)):
            raise ValueError('fixed real phase carrier')
        self.cache={}; self.seconds=0.; self.calls=0

    def components(self, mode):
        key=(mode.side,complex(mode.alpha),complex(mode.gamma),complex(mode.k_vector[2]))
        if key in self.cache:return self.cache[key]
        began=perf_counter(); n=self.space.dofmap.index_map.size_local
        out=np.zeros((n,2),np.complex128)
        source=self.tiles; k=np.asarray(mode.k_vector,dtype=np.complex128)-self.phase_carrier
        for _,(cell,J,origin,z) in source.faces.items():
            side='bottom' if z==0 else 'top'
            if side!=mode.side:continue
            if self.polynomial is None:
                if z not in source.tabulation:
                    pts=np.column_stack((source.rule,np.full(len(source.rule),z)))
                    source.tabulation[z]=source.element.tabulate(0,pts)[0]
                pts=np.column_stack((source.rule,np.full(len(source.rule),z)))
                physical=pts@J.T+origin
                basis=source.tabulation[z]@np.linalg.inv(J)
                area=np.linalg.norm(np.cross(J[:,0],J[:,1]))
                local=np.einsum('q,qjc->jc',source.weights*np.exp(1j*(physical@k))*area,basis)[:,:2].astype(np.complex128)
            else:local=self.polynomial.integral(side,k,J,origin,self.q)
            local=np.ascontiguousarray(local)
            self.space.element.T_apply(local.view(np.float64).ravel(),source.permutations[cell:cell+1],4)
            for j,row in enumerate(self.space.dofmap.cell_dofs(cell)):
                masters,coeff=source.maps[int(row)]
                np.add.at(out,masters,coeff[:,None]*local[j])
        rows=np.flatnonzero(np.any(out!=0,axis=1)).astype(np.int64)
        values=np.ascontiguousarray(out[rows]);rows.flags.writeable=False;values.flags.writeable=False
        self.cache[key]=(rows,values);self.seconds+=perf_counter()-began;self.calls+=1
        return rows,values

    def assemblers(self):
        provider=self
        class Component:
            def __init__(self, j):self.j=j
            def assemble_entries(self,mode,mpc):
                if mpc is not provider.mpc:raise ValueError('literal MPC identity changed')
                rows,values=provider.components(mode)
                return rows,values[:,self.j]
        return {(side,j):Component(j) for side in ('top','bottom') for j in (0,1)}

    def incident_traction(self):
        cfg=self.cfg
        mode=SimpleNamespace(side='top',alpha=cfg.kx,gamma=cfg.ky,k_vector=cfg.wavevector)
        rows,values=self.components(mode)
        ein=cfg.incident_amplitude*np.asarray(cfg.polarization_vector)
        traction=np.cross(1j*np.cross(np.asarray(cfg.wavevector),ein),np.array([0.,0.,1.]))
        result=np.zeros(self.space.dofmap.index_map.size_local,np.complex128)
        np.add.at(result,rows,values@traction[:2])
        return result


def carrier(space,mpc,cfg,q,*,method='basix2d'):
    from src.solvers.fullspace_dtn_action import build_dynamic_mode_inventory,build_fullspace_dtn_carrier_from_surface
    modes,identities,mode_sha=build_dynamic_mode_inventory(cfg)
    source=SurfaceComponents(space,mpc,cfg,q,method=method)
    result=build_fullspace_dtn_carrier_from_surface(modes,source.assemblers(),mpc,cfg,retain_all_nonzero=True)
    return result,source,modes,identities,mode_sha


def pack_carrier(c):
    offsets=[0];rows=[];cv=[];dv=[]
    for item in c.entries:
        rr=np.union1d(item.coupling_rows,item.projection_rows)
        cc=np.zeros(len(rr),complex);dd=np.zeros(len(rr),complex)
        cc[np.searchsorted(rr,item.coupling_rows)]=item.coupling_values
        dd[np.searchsorted(rr,item.projection_rows)]=item.projection_values
        rows.append(rr);cv.append(cc);dv.append(dd);offsets.append(offsets[-1]+len(rr))
    return dict(offsets=np.asarray(offsets,np.int64),rows=np.concatenate(rows),
                C=np.concatenate(cv),D=np.concatenate(dv),H=np.array([e.normalization_h for e in c.entries]))


def carrier_pair(first,second,identities):
    if len(first.entries)!=532 or len(second.entries)!=532:raise ValueError('complete532 inventory')
    result=[]
    for a,b,identity in zip(first.entries,second.entries,identities,strict=True):
        rr=np.union1d(np.union1d(a.coupling_rows,a.projection_rows),np.union1d(b.coupling_rows,b.projection_rows))
        row={k:identity[k] for k in ('mode_index','side','m','n','polarization')}
        for label in ('coupling','projection'):
            x=np.zeros(len(rr),complex);y=np.zeros(len(rr),complex)
            x[np.searchsorted(rr,getattr(a,label+'_rows'))]=getattr(a,label+'_values')
            y[np.searchsorted(rr,getattr(b,label+'_rows'))]=getattr(b,label+'_values')
            row[label+'_relative']=relative(x-y,y)
            # This scale uses the full absolute contributions of both assembled
            # vectors; no clipping or near-zero coefficient normalization.
            scale=max(float(np.linalg.norm(x)),float(np.linalg.norm(y)),1e-300)
            row[label+'_operation_scaled']=float(np.linalg.norm(x-y)/scale)
            row[label+'_difference_norm']=float(np.linalg.norm(x-y))
            row[label+'_reference_norm']=float(np.linalg.norm(y))
        row['H_equal']=bool(a.normalization_h==b.normalization_h)
        row['pass']=all(row[k]<=limit for k,limit in [('coupling_relative',1e-11),('projection_relative',1e-11),('coupling_operation_scaled',1e-10),('projection_operation_scaled',1e-10)]) and row['H_equal']
        result.append(row)
    return {'mode_count':532,'per_mode':result,'pass':all(r['pass'] for r in result),
            'max_relative':max(r[k] for r in result for k in ('coupling_relative','projection_relative')),
            'max_operation_scaled':max(r[k] for r in result for k in ('coupling_operation_scaled','projection_operation_scaled'))}


def boundary_stage(folder,journal,make_setup):
    from dolfinx import fem
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import _surface_assemblers
    from src.solvers.fullspace_dtn_action import build_fullspace_dtn_carrier_from_surface,FullspaceDtnAction
    from src.solvers.dtn_port_3d import _assemble_mpc_vector,_incident_top_traction_form,_assemble_mpc_form_vector,_set_scalar_constant
    rows=[]; rng=np.random.default_rng(50047)
    for degree,oldq in ((4,23),(5,25)):
        cfg,setup,geometry=make_setup('NOTCH',degree,'ORIGINAL',journal)
        space=setup['spaces'][degree];mpc=setup['floquets'][degree].mpc
        with journal.measured(f'p{degree}_full532_q47_separable'):
            c47,s47,modes,ids,digest=carrier(space,mpc,cfg,47,method='separable')
        with journal.measured(f'p{degree}_full532_q63_independent_basix2d'):
            c63,s63,_,_,_=carrier(space,mpc,cfg,63)
        with journal.measured(f'p{degree}_full532_original_native_q{oldq}'):
            assemblers=_surface_assemblers(space,setup['mesh_data'],cfg,oldq,jit_options={})
            old=build_fullspace_dtn_carrier_from_surface(modes,assemblers,mpc,cfg)
            class UntrimmedNative:
                def __init__(self,a):self.a=a
                def assemble_entries(self,mode,mpc):
                    for name,value in (('alpha',mode.alpha),('gamma',mode.gamma),('kz',mode.k_vector[2])):
                        _set_scalar_constant(getattr(self.a,name),value)
                    vec=_assemble_mpc_form_vector(self.a.form,mpc)
                    try:
                        a=vec.array;rows=np.flatnonzero(a!=0).astype(np.int64)
                        return rows+vec.getOwnershipRange()[0],a[rows].copy()
                    finally:vec.destroy()
            old_full=build_fullspace_dtn_carrier_from_surface(modes,{k:UntrimmedNative(a) for k,a in assemblers.items()},mpc,cfg,retain_all_nonzero=True)
            del assemblers
        high=carrier_pair(c47,c63,ids); low=carrier_pair(old,c63,ids);untrimmed=carrier_pair(old_full,c63,ids)
        n=space.dofmap.index_map.size_local
        v=fem.Function(space);v.x.array[:]=rng.normal(size=n)+1j*rng.normal(size=n);v.x.array[mpc.slaves]=0
        x=v.x.petsc_vec
        actions=[]
        for cc in (c47,c63,old,old_full):
            action=FullspaceDtnAction(cc,comm=space.mesh.comm)
            target=x.duplicate();action.apply(x,target);forward=target.array.copy()
            # The old action has no public AH method. Its literal sparse
            # functionals give (CD/H)^H=D^H C^H/conj(H), independently.
            adjoint=np.zeros(n,complex)
            for e in cc.entries:
                a=np.vdot(e.coupling_values,x.array[e.coupling_rows])/np.conj(e.normalization_h)
                np.add.at(adjoint,e.projection_rows,np.conj(e.projection_values)*a)
            actions.append((forward,adjoint));target.destroy();action.destroy()
        paired={name:relative(actions[i][j]-actions[1][j],actions[1][j]) for name,i,j in
                [('q47_forward',0,0),('q47_adjoint',0,1),('original_forward',2,0),('original_adjoint',2,1),('original_untrimmed_forward',3,0),('original_untrimmed_adjoint',3,1)]}
        journal.calls['A']+=4;journal.calls['AH']+=4
        inc47=s47.incident_traction();inc63=s63.incident_traction()
        native=_assemble_mpc_vector(_incident_top_traction_form(space,setup['mesh_data'],cfg),mpc,quadrature_degree=oldq,jit_options={})
        inc_old=native.array.copy();native.destroy()
        incident={'q47_q63_relative':relative(inc47-inc63,inc63),'old_q63_relative':relative(inc_old-inc63,inc63)}
        inventories={}
        for label,cc in (('q47',c47),('q63',c63),('original',old),('original_untrimmed',old_full)):
            inventories[label]=save_arrays(folder/f'p{degree}_{label}_all532.npz',**pack_carrier(cc),
                incident_traction=inc47 if label=='q47' else inc63 if label=='q63' else inc_old)
        witness=save_arrays(folder/f'p{degree}_action_pair.npz',input=v.x.array,forward47=actions[0][0],forward63=actions[1][0],forward_old=actions[2][0],
            adjoint47=actions[0][1],adjoint63=actions[1][1],adjoint_old=actions[2][1])
        passed=high['pass'] and incident['q47_q63_relative']<=1e-11 and max(paired['q47_forward'],paired['q47_adjoint'])<=1e-10
        rows.append(dict(degree=degree,original_q=oldq,mode_sha256=digest,high_pair=high,original_pair=low,original_untrimmed_pair=untrimmed,
            preserve_all_nonzero_rows=True,legacy_pruning_separate_from_quadrature=True,
            bidirectional_action=paired,incident=incident,arrays=inventories,witness=witness,
            q47_q63_pass=passed,production_q=47,oracle_q=63,high_q_native_JIT=False,
            q47_cost_seconds=s47.seconds,q63_cost_seconds=s63.seconds))
        journal.event('full532_boundary_pair_saved',degree=degree,high_pass=passed,old_pass=low['pass'])
    return {'status':'COMPLETED','rows':rows,'q47_q63_pass':all(r['q47_q63_pass'] for r in rows),
            'timings':journal.timings,'calls':journal.calls,'no_mode_truncation':True}
