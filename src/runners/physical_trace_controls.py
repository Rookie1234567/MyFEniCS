"""One fixed p4 trace-entity component with existing BAL_H and I4 orchestration."""
import hashlib
import json
import time
from pathlib import Path
import numpy as np

TRACE_INVENTORY=Path('benchmarks/artifacts/task39extra/v6_recursive/higher_trace_entity_inventory.json')
TRACE_INVENTORY_HASH='9dee01eadae5fe78d4855cff412f1c18bcee55563e3373609d44a06184c064b6'
RECOVERY_READOUT=Path('benchmarks/artifacts/task39extra/v6_recursive/bubble_amplification_retry_readout.json')
RECOVERY_HASH='403eb348a62802f7f0018a149922541b49a6fd3049c262d71c6b9a8a3bf05a97'
RECOVERY_ROOT=Path('benchmarks/artifacts/task39extra/v6_bubble_amplification_diagnostic/450255f4575792d052c1bac29837d39955ee1039/a2r160_g1')
NATIVE_TRACE_ROOT=Path('benchmarks/artifacts/task39extra/v6_high_trace_component/564e42b43391f1857934ef064778636aff06894b/a2r160_g1')
NATIVE_TRACE_READOUT=Path('benchmarks/artifacts/task39extra/v6_recursive/high_trace_readout.json')
NATIVE_TRACE_HASH='8b43b5448b497a5d56e8f3372284f448c4d9460618f6048eab54b3b91cbe616f'


def run_trace_component(cfg,comm,binding_path,directory,*,sample,marker,cached_exact=False):
    from petsc4py import PETSc
    from .physical_diagnosis_worker import save_packet
    from .physical_recursive_controls import load_p4_failure_input,verify_recursive_map
    from src.solvers.physical_bubble_particular import saved_packet_reader,ROOT,READOUT,READOUT_SHA
    from src.solvers.physical_bubble_amplification import SavedBubbleSpace,PARTICULAR_ROOT,PARTICULAR_READOUT,PARTICULAR_HASH
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import build_same_mesh_physical_action,destroy_same_mesh_physical_action
    from src.solvers.fullspace_same_mesh_hcurl_pmg import _n1e
    from src.solvers.fullspace_dtn_action import FullspaceDtnCarrier,FullspaceDtnModeFunctional,build_fullspace_dtn_action
    from src.solvers.fullspace_physical_intermediate_runtime import level_vector
    from src.solvers.fullspace_physical_intermediate import apply_owned
    from src.solvers.condensed_fine_reference import native_map_arrays
    from src.solvers.physical_recursive_coarse import PhysicalP2Inverse,solve_physical_i4
    from src.solvers.physical_trace_entity import PhysicalTraceEntities,complete_pq,relative_defect,CachedPhysicalTraceAction
    from src.solvers.physical_balanced_coupling import PhysicalBalancedCoupling
    from src.solvers.physical_error_metric import LosslessFEMetric
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=False)
    save=lambda n,f:save_packet(directory,n,f)
    native=dtn=space=matrix=bottom=metric=trace=result=cached=None;vectors=[]
    counts=dict(A4=0,CU=0,B4=0,I4=0,H6=0,old_H4=0,outer=0,
        native_A4_qualification=0,native_A4_explicit=0,native_A4_output=0,cached_qualification=0);elapsed={};operations={}
    def timed(name,fn):
        start=time.perf_counter()
        try:return fn()
        finally:elapsed[name]=elapsed.get(name,0.)+time.perf_counter()-start
    def keep(v):vectors.append(v);return v
    def check(name,actual,expected,limit=1e-10):
        error=float(np.linalg.norm(actual-expected)/max(np.linalg.norm(expected),np.finfo(float).tiny))
        save(name,dict(actual=actual,expected=expected,relative_error=error,limit=limit))
        if not np.isfinite(error) or error>limit:raise ValueError(name+' identity failed')
    try:
        if comm.size!=1:raise ValueError('trace component requires MPI1')
        if hashlib.sha256(TRACE_INVENTORY.read_bytes()).hexdigest()!=TRACE_INVENTORY_HASH:raise ValueError('entity inventory changed')
        inventory=json.loads(TRACE_INVENTORY.read_text())
        if len(inventory['entities'])!=1566 or inventory['high_trace_dimension']!=17064:raise ValueError('frozen entity counts differ')
        data=load_p4_failure_input(binding_path)
        old=saved_packet_reader(ROOT,READOUT,READOUT_SHA);part=saved_packet_reader(PARTICULAR_ROOT,PARTICULAR_READOUT,PARTICULAR_HASH)
        recovered=saved_packet_reader(RECOVERY_ROOT,RECOVERY_READOUT,RECOVERY_HASH)
        levels=_build_same_mesh_levels(cfg,comm,(4,2),include_positive_coefficients=False)
        mapping=verify_recursive_map(dict(levels=levels),4,data['map'])
        p2map=native_map_arrays(levels['spaces'][2],levels['floquets'][2]);saved_p2=recovered('amplification_p2_map')
        for key,value in p2map.items():
            if not np.array_equal(value,saved_p2[key]):raise ValueError('restored p2 map differs')
        save('trace_map_bridge',dict(relative_error=0.,p4=mapping,p2=p2map,inventory_hash=TRACE_INVENTORY_HASH))
        cm=part('particular_class_map');cells=cm['cell_classes'];classes={};orientations={};quadrature=None
        for i in range(18):
            sample();prefix=f'bubble_class_{i:03d}';ident=old(prefix+'_identity');key=ident['sha256'];h=old(prefix+'_bubble_harmonic');ret=old(prefix+'_retained')
            if ident['key']!=cm['identities'][key]:raise ValueError('class identity differs')
            q=ident['key']['quadrature']
            if quadrature is None:quadrature=q
            if q!=quadrature or q!=[dict(quadrature_degree=15,quadrature_rule='default')]*2:raise ValueError('fine quadrature bridge failed')
            orientation=ident['key']['orientation']
            if orientation in orientations:
                if not np.array_equal(orientations[orientation],h['Q']):raise ValueError('Q cache is not byte-exact')
            else:orientations[orientation]=h['Q']
            classes[key]=dict(A=h['A'],R=h['R'],Q=orientations[orientation],D=h['D'],S=h['S'],W=ret['W'],delta=ret['delta'],cell_info=orientation)
            del h,ret
        p=recovered('amplification_carrier')
        entries=[FullspaceDtnModeFunctional(**{**e,'mode_key':tuple(e['mode_key'])}) for e in p['entries']]
        carrier=FullspaceDtnCarrier(entries,global_rows=p['global_rows'],ownership_range=(0,p['global_rows']),slave_rows=p2map['slaves'],comm=comm)
        dtn=build_fullspace_dtn_action(carrier,comm=comm)
        space=SavedBubbleSpace(levels,classes,cells,p2map,dtn,sample=sample,save=save)
        stored=recovered('amplification_S_CSR')
        matrix=PETSc.Mat().createAIJ(size=stored['shape'],csr=(stored['indptr'],stored['indices'],stored['values']),comm=comm)
        if matrix.getSize()!=(7326,7326):raise ValueError('restored S size differs')
        save('trace_S_restored',dict(source=RECOVERY_ROOT.as_posix(),source_readout_hash=RECOVERY_HASH,
            shape=matrix.getSize(),nnz=matrix.getInfo()['nz_used'],payload=sum(stored[k].nbytes for k in ('indptr','indices','values'))))
        del stored,p,entries
        marker('trace_native_p4_started',{})
        native=build_same_mesh_physical_action(levels,cfg,4,volume_quadrature_metadata=quadrature)
        if native['mode_sha256']!=data['binding']['mode_sha256']:raise ValueError('p4 mode SHA differs')
        p4carrier=native['dtn_action'].carrier
        save('trace_p4_carrier',dict(mode_sha256=native['mode_sha256'],entries=[dict(mode_key=e.mode_key,
            coupling_rows=e.coupling_rows,coupling_values=e.coupling_values,projection_rows=e.projection_rows,
            projection_values=e.projection_values,normalization_h=e.normalization_h) for e in p4carrier.entries]))
        rhs=keep(level_vector(levels,4));rhs.set(0);rhs.array[mapping['independent_indices']]=data['arrays']['g']
        reference=keep(rhs.duplicate());reference.set(0);reference.array[mapping['independent_indices']]=data['arrays']['y']
        cached=CachedPhysicalTraceAction(mapping,cells,classes,native['dtn_action']) if cached_exact else None
        def native_A4(x,role):
            sample();counts['native_A4_'+role]+=1
            if sum(counts[k] for k in ('native_A4_qualification','native_A4_explicit','native_A4_output'))>75:
                raise RuntimeError('fixed native authority/qualification cap')
            return timed('native_A4_'+role,lambda:apply_owned(native['physical_action'],x))
        def A(x):
            sample();counts['A4']+=1
            if counts['A4']>350:raise RuntimeError('fixed trace A4 call cap')
            return timed('cached_A4' if cached_exact else 'A4',lambda:apply_owned(cached if cached_exact else native['physical_action'],x))
        ay=native_A4(reference,'qualification') if cached_exact else A(reference)
        try:check('trace_source_bridge',ay.array[mapping['independent_indices']],data['arrays']['A4y'])
        finally:ay.destroy()
        previous=None
        if cached_exact:
            previous=saved_packet_reader(NATIVE_TRACE_ROOT,NATIVE_TRACE_READOUT,NATIVE_TRACE_HASH)
            first_saved=previous('trace_B4_g');last_saved=previous('trace_I4_result')
            for label,value in (('reference',reference.array),('first_B4',first_saved['solution']),('I4',last_saved['solution'])):
                q=rhs.duplicate();q.array[:]=value;direct=fast=None
                try:
                    direct=native_A4(q,'qualification');counts['cached_qualification']+=1
                    fast=timed('cached_qualification',lambda:apply_owned(cached,q))
                    check('trace_cached_'+label+'_bridge',fast.array,direct.array,1e-11)
                    unchanged=bool(np.array_equal(q.array,value))
                    save('trace_cached_'+label+'_input',dict(value=q.array.copy(),source_readout_hash=NATIVE_TRACE_HASH,input_unchanged=unchanged))
                    if not unchanged:raise ValueError('cached/native qualification mutated input')
                finally:
                    for v in (q,direct,fast):
                        if v is not None:v.destroy()
            del first_saved,last_saved,value
        # Preallocation policy includes both original A and Q-D (not just retained W).
        # Count deduplicated arrays before factor construction and reserve the fixed
        # entity/J/factor/storage maxima; parent RSS remains the physical authority.
        array_roots={}
        for item in classes.values():
            for a in item.values():
                if isinstance(a,np.ndarray):array_roots[id(a)]=a.nbytes
        maps_bytes=sum(v.nbytes for m in (mapping,p2map) for v in m.values() if isinstance(v,np.ndarray))
        extra=sum(array_roots.values())+maps_bytes+2448000+3003696+10076832+6045696+1050624+8*849344+32*1024**2
        extra+=sum(e.coupling_rows.nbytes+e.coupling_values.nbytes+e.projection_rows.nbytes+e.projection_values.nbytes for c in (carrier,p4carrier) for e in c.entries)
        if cached_exact:extra+=3*849344
        marker('trace_fixed_storage_preflight',dict(extra_local_bytes=extra,policy_cap=512*1024**2,
            Krylov_V_Z_bound_bytes=33*849344,BAL_new_vector_bound_bytes=32*849344,
            scope='PC extra enters common bottom budget; KSP/BAL live vectors separately in whole-tree RSS'))
        bottom=PhysicalP2Inverse(matrix,space,space.transfer.coarse_slaves,sample=sample,marker=marker,save=save,
            action_identity='saved_S_cell_plus_p2_DtN',extra_local_bytes=extra)
        # The factor gate precedes entity allocations; no call made to the factor yet.
        trace=timed('trace_setup',lambda:PhysicalTraceEntities(mapping,cells,classes,inventory['entities'],_n1e(4).entity_dofs,
            p4carrier,sample=sample,save=save,marker=marker))
        payload=trace.payload_bytes()
        if payload>extra:raise MemoryError('trace named allocations exceed reserved bottom local payload')
        save('trace_storage',dict(named_array_bytes=payload,reserved_extra_bytes=extra,bottom=bottom.bottom.audit,
            old_H4_positive=0,p6_objects=0,global_trace_matrix=0))
        def Cw_array(value):
            v=rhs.duplicate();v.array[:]=value;q=z=w=None
            try:
                q=space.transfer.apply_adjoint(v);z=bottom.apply(q);w=space.transfer.apply_primal(z)
                return w.array.copy()
            finally:
                for x in (v,q,z,w):
                    if x is not None:x.destroy()
        def CU(x):
            sample();counts['CU']+=1
            if counts['CU']>131:raise RuntimeError('fixed CU logical cap')
            value=timed('CU',lambda:complete_pq(x.array,trace.E,trace.volume,Cw_array))
            out=x.duplicate();out.array[:]=value;return out
        def HT(x):
            out=x.duplicate()
            try:out.array[:]=trace.apply(x.array);return out
            except BaseException:out.destroy();raise
        def restriction(x):
            q=space.transfer.apply_adjoint(x)
            try:
                internal=np.concatenate([classes[key]['Q'].conj().T@x.array[mapping['dofmap'][c]] for c,key in enumerate(cells)])
                return np.concatenate([q.array.copy(),internal])
            finally:q.destroy()
        # One fixed real-array adjoint witness, without new calibration inputs.
        rng=np.random.default_rng(386);z=rng.normal(size=rhs.getLocalSize())+1j*rng.normal(size=rhs.getLocalSize());z[mapping['slaves']]=0
        coefficients=[rng.normal(size=b['J'].shape[1])+1j*rng.normal(size=b['J'].shape[1]) for b in trace.blocks]
        f=trace.F(coefficients);fh=trace.FH(z)
        left=np.vdot(f,z);right=sum(np.vdot(c,v) for c,v in zip(coefficients,fh,strict=True))
        check('trace_F_adjoint',np.asarray([left]),np.asarray([right]),1e-11)
        save('trace_F_witness',dict(z=z,Fc=f,coefficients=coefficients,FHz=fh))
        cu=CU(rhs)
        try:check('trace_CUg_bridge',cu.array,recovered('amplification_result_vectors')['CUg'])
        finally:cu.destroy()
        coupling=PhysicalBalancedCoupling(A,CU,HT,restriction,route='BAL_H',checkpoint=sample,
            level_identity='research p4 complete PQ + fixed high trace entities')
        def B(x):
            counts['B4']+=1
            if counts['B4']>65:raise RuntimeError('fixed B4_T call cap')
            try:return coupling.apply(x)
            finally:
                for k,v in coupling.last_apply_facts['counts'].items():operations[k]=operations.get(k,0)+v
                save(f"trace_B4_{counts['B4']:03d}",dict(facts=coupling.last_apply_facts,counts=counts,
                    cumulative=operations,trace_counts=trace.counts,trace_seconds=trace.elapsed,bottom_counts=bottom.counts))
        metric=LosslessFEMetric(levels,4,cfg.k0,quadrature)
        def fields(solution,name):
            error=data['arrays']['y']-solution.array[mapping['independent_indices']];values={}
            for key,action in (('M0',metric.mass),('scaled_curl',metric.curl)):
                sample();image=action(error);energy=float(np.vdot(error,image).real)
                baseline=old('bubble_Cg_fields')['fields'][key]['reference_energy']
                values[key]=dict(error=error,metric_image=image,energy=energy,baseline=baseline,ratio=float(np.sqrt(energy/baseline)))
            save(name,values)
        first=B(rhs);applied=native_A4(first,'output') if cached_exact else A(first)
        try:
            if cached_exact:check('trace_cached_B4_output_bridge',first.array,previous('trace_B4_g')['solution'])
            residual=rhs.array-applied.array;coarse=restriction(rhs);defect=restriction(applied);remaining=coarse-defect
            balance=relative_defect(remaining,coarse,defect)
            split=len(p2map['offsets'])-1
            separate=dict(W=relative_defect(remaining[:split],coarse[:split],defect[:split]),
                Q=relative_defect(remaining[split:],coarse[split:],defect[split:]))
            save('trace_B4_g',dict(rhs=rhs.array.copy(),solution=first.array.copy(),applied=applied.array.copy(),residual=residual,
                true_relative=float(np.linalg.norm(residual)/rhs.norm()),coarse_WQ_rhs=coarse,coarse_WQ_applied=defect,balance=balance,separate_balance=separate))
            if not all(np.isfinite(v) and v<=1e-11 for v in (balance,*separate.values())):raise ValueError('full B4_T W/Q balance failed')
            fields(first,'trace_B4_g_fields')
        finally:first.destroy();applied.destroy()
        counts['I4']+=1
        result=solve_physical_i4(rhs,A,B,target=1e-4,sample=sample,save=save,
            residual_action=(lambda x:native_A4(x,'explicit')) if cached_exact else None)
        save('trace_I4_result',dict(facts=result['facts'],rhs=rhs.array.copy(),solution=result['solution'].array.copy(),
            applied=result['applied'].array.copy(),residual=result['residual'].array.copy()))
        fields(result['solution'],'trace_I4_fields')
        save('trace_component_summary',dict(status='COMPONENT_COMPLETED',I4=result['facts'],counts=counts,
            solver_target_reached=result['facts']['final_true_residual']<=1e-4,G5_closed=False,outer=0))
    finally:
        save('trace_component_costs',dict(counts=counts,elapsed_seconds=elapsed,operations=operations,
            cached_exact=cached_exact,cached_counts=cached.counts if cached else {},cached_seconds=cached.seconds if cached else {},
            A4_counter_semantics='Krylov/BAL cached; native authority and qualifications separately counted' if cached_exact else 'original native action all calls',
            trace_counts=trace.counts if trace else {},trace_seconds=trace.elapsed if trace else {},
            bottom_counts=bottom.counts if bottom else {},S_action_seconds=space.action_seconds if space else 0.,
            S_actions=space.action_count if space else 0,payload_bytes=trace.payload_bytes() if trace else None))
        if result is not None:
            for k in ('solution','applied','residual'):result[k].destroy()
        if metric is not None:metric.destroy()
        for v in reversed(vectors):v.destroy()
        if bottom is not None:bottom.destroy()
        if matrix is not None:matrix.destroy()
        if space is not None:space.destroy()
        if dtn is not None:dtn.destroy()
        if native is not None:destroy_same_mesh_physical_action(native)
