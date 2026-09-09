"""Opt-in saved-data projected trace store and one frozen p4 component."""
import hashlib
import time
import weakref
import numpy as np
from src.solvers.physical_projected_trace import (
    ProjectedPatchCross,ProjectedTraceFactorStore,projected_local_oracle)
from src.solvers.physical_trace_entity import complete_pq,relative_defect
from src.solvers.physical_balanced_coupling import PhysicalBalancedCoupling
from src.solvers.physical_recursive_coarse import solve_physical_i4
from src.solvers.fullspace_physical_intermediate_runtime import level_vector


def run_projected_store_component(context):
    """Borrow qualified restore objects; caller owns their cleanup and 2400s parent."""
    g=context;save,sample,get=g['save'],g['sample'],g['get']
    classes,trace,space,bottom,levels=(g[k] for k in ('classes','trace','space','bottom','levels'))
    mapping,p2,cells,patch=(g[k] for k in ('mapping','p2','cells','patch'))
    started=time.perf_counter();counts=dict(store_S=0,CU=0,B4=0,I4=0);result=rhs=None;qualification_count_reset=False
    try:
        if len(cells)!=252 or patch['indices'].shape!=(252,144):raise ValueError('frozen252/144 changed')
        for h in classes.values():h.pop('R',None);h.pop('delta',None)
        # Same exact Q sharing as the established owner route, not approximate clustering.
        unique={}
        for class_key,h in classes.items():
            key=hashlib.sha256(h['Q'].tobytes()).hexdigest()
            if key in unique and not np.array_equal(unique[key],h['Q']):raise ValueError('Q hash collision')
            h['Q']=unique.setdefault(key,h['Q']);h['factor']=g['factors'][class_key]
        del unique,h
        space.retained_bytes=sum(h[k].nbytes for h in classes.values() for k in ('W','S'))+16*1024**2
        store=ProjectedTraceFactorStore(patch['indices'],patch['weights'],patch['offsets'])
        trace.joint=store
        # Do not retain old class IDs/multiplicity or construct any old local D/LU factors.
        original_class_ids=patch['class_ids'].copy()
        patch.clear()
        ports4=get('joint/trace_p4_carrier')['entries'];ports2=get('recovery/amplification_carrier')['entries']
        identities={get(f'bubble/bubble_class_{i:03d}_identity')['sha256']:i for i in range(18)}
        packet_peak=0
        map_bytes=sum(a.nbytes for a in (store.indices,store.weights,store.offsets))
        if map_bytes>444056:raise MemoryError('fixed map allocation budget')
        def memory_record(current=()):
            # Keep the established 32MiB general plus 16MiB local scratch reserves.
            groups=dict(maps=g['maps'],classes={k:{name:v for name,v in h.items() if name!='P'} for k,h in classes.items()},Q_factors=g['factors'],J=trace.blocks,
                members=trace.members,store=store.storage(),owner=vars(space.owner),
                owner_work=[space.owner._coarse_work.x.array,space.owner._fine_work.x.array],
                carriers=[vars(e) for carrier in (g['c2'],g['c4']) for e in carrier.entries])
            named=g['retained_bytes'](groups)
            transient=g['retained_bytes'](current)
            P_bytes=sum(h['P'].nbytes for h in classes.values() if 'P' in h)
            # Current patch P/packet/R/X/D/LU-check temporaries share the unchanged16MiB reserve.
            scratch_required=transient+P_bytes+packet_peak+2*927488+18432+4*331776+4*144*16
            if scratch_required>16*1024**2:raise MemoryError('current patch exceeds unchanged16MiB scratch')
            reserves=32*1024**2+16*1024**2+8*849344+3*849344+4117888
            fixed_extra=202120960
            # Raw port packets duplicate carrier storage during setup, and P is transient.
            setup_extra=g['retained_bytes']([ports4,ports2,original_class_ids])
            value=named+reserves+setup_extra
            unbuilt_factor_bytes=(len(store.indices)-len(store.factors))*(144*144*16+144*4)
            full_prediction=value+unbuilt_factor_bytes
            save('latest_named_live_set',dict(named_bytes=named,temporary_bytes=transient,
                named_groups={k:g['retained_bytes'](v) for k,v in groups.items()},
                named_group_scope='individual roots may overlap; named_bytes is union',
                saved_CSR_bytes=g['retained_bytes'](g['csr']),
                saved_CSR_scope='retained global csr charged to existing second-CSR reserve in bottom matrix budget, not hidden in extra',
                max_decoded_packet_bytes=packet_peak,packet_transient_scope='within preserved16MiB local scratch; parent covers read/compression buffers',
                current_P_bytes=P_bytes,local_scratch_required_bytes=scratch_required,local_scratch_reserved_bytes=16*1024**2,
                maximum_all18_P_bytes=4665600,
                unbuilt_LU_pivot_bytes=unbuilt_factor_bytes,full_store_extra_prediction_bytes=full_prediction,
                full_store_policy_deficit_bytes=max(0,full_prediction-fixed_extra),
                raw_ports_and_class_ids_bytes=setup_extra,reserves_bytes=reserves,
                extra_bound_bytes=value,extra_limit_bytes=fixed_extra,policy_bytes=533190648,
                conservative_factor_bytes=260000000,map_bytes=map_bytes,
                completed_factors=len(store.factors),classification='named_array_accounting_with_policy_reserves_not_measured_RSS',runtime_original_D_residual='not_measured'))
            if full_prediction>fixed_extra:
                raise MemoryError(f'full252 named policy deficit {full_prediction-fixed_extra} bytes before further S columns')
            sample()
        memory_record()
        for cell in range(252):
            begin=time.perf_counter();prefix=f'projected_patch_{cell:03d}'
            write=lambda name,row:save(prefix+'_'+name,row)
            cross=ProjectedPatchCross(mapping,p2,cells,classes,trace.blocks,g['patch_entities'][cell],ports4,ports2,
                sample=sample,save=write)
            needed={key for _,key,_ in cross.local}
            for key in needed:
                packet=get(f'bubble/bubble_class_{identities[key]:03d}_bubble_harmonic')
                packet_peak=max(packet_peak,g['retained_bytes'](packet));classes[key]['P']=packet['P'];del packet
                if packet_peak>16*1024**2:raise MemoryError('packet exceeds preserved local scratch')
            # Original D is frozen patch data; no original factor/class inference is built here.
            original=get(f'joint/trace_patch_class_{int(original_class_ids[cell]):03d}')['D']
            memory_record([original,cross.offsets,[v for _,_,J in cross.local for v in (J.data,J.indices,J.indptr)],
                [(left,right) for left,right,_ in cross.ports]])
            def solve_one(value):
                if counts['store_S']>=36288:raise RuntimeError('store logical S cap')
                counts['store_S']+=1;x=level_vector(levels,2);z=None;t=time.perf_counter()
                try:
                    x.array[:]=value;z=bottom.apply(x);facts=dict(bottom.last_facts)
                    facts['seconds']=time.perf_counter()-t
                    return z.array.copy(),facts
                finally:
                    x.destroy()
                    if z is not None:z.destroy()
            effective,Rc,facts=projected_local_oracle(cross,original,solve_one,save=write,sample=sample,save_success_arrays=False)
            ref=weakref.ref(effective);factor_facts=store.append(effective,save=write)
            memory_record([original,effective,Rc,cross.offsets,
                [v for _,_,J in cross.local for v in (J.data,J.indices,J.indptr)]])
            del effective,original,Rc,cross
            for h in classes.values():h.pop('P',None)
            if ref() is not None:raise RuntimeError('projected D retained after setup')
            write('complete',dict(cell=cell,construction=facts,factor=factor_facts,D_released=True,
                seconds=time.perf_counter()-begin,counts=dict(bottom.counts)))
        if counts['store_S']!=36288 or bottom.counts['MatSolve']>108864 or bottom.counts['refinement']>72576:
            raise RuntimeError('store counts differ')
        del ports4,ports2,original_class_ids
        save('projected_store_complete',dict(factors=len(store.factors),counts=dict(bottom.counts),
            seconds=time.perf_counter()-started,policy_bytes=533190648,runtime_original_D_residual='not_measured'))
        save('projected_component_start_snapshot',dict(bottom_counts=dict(bottom.counts),trace_counts=dict(trace.counts),
            cached_counts=dict(g['cached'].counts),cached_seconds=dict(g['cached'].seconds),
            S_actions=space.action_count,S_seconds=space.action_seconds,routing=dict(space.owner.routing_costs)))
        rhs=level_vector(levels,4);fixed=get('component/frozen_B4_rhs');rhs.array[:]=fixed['rhs'];del fixed
        if np.any(rhs.array[mapping['slaves']]!=0):raise ValueError('frozen RHS slave contamination')
        def A(x):
            y=x.duplicate()
            try:g['cached'].apply_into(x,y);return y
            except BaseException:y.destroy();raise
        def Cw(value):
            x=rhs.duplicate();x.array[:]=value;q=z=w=None
            try:
                q=space.transfer.apply_adjoint(x);z=bottom.apply(q);w=space.transfer.apply_primal(z);return w.array.copy()
            finally:
                for v in (x,q,z,w):
                    if v is not None:v.destroy()
        def CU(x):
            counts['CU']+=1
            if counts['CU']>131:raise RuntimeError('CU cap')
            y=x.duplicate()
            try:y.array[:]=complete_pq(x.array,trace.E,trace.volume,Cw);return y
            except BaseException:y.destroy();raise
        def HT(x):
            y=x.duplicate()
            try:y.array[:]=trace.apply(x.array);return y
            except BaseException:y.destroy();raise
        def restriction(x):
            q=space.transfer.apply_adjoint(x)
            try:return np.concatenate([q.array.copy(),np.concatenate([classes[k]['Q'].conj().T@x.array[mapping['dofmap'][i]] for i,k in enumerate(cells)])])
            finally:q.destroy()
        qualification_start=time.perf_counter();trace_before=dict(trace.counts);store_before=dict(store.counts);trace_time_before=dict(trace.elapsed)
        qualified=False;defect=None
        try:
            before=rhs.array.copy();a=trace.apply(rhs.array);repeat=trace.apply(rhs.array);scaled=trace.apply((.7+.2j)*rhs.array)
            if not np.array_equal(before,rhs.array) or not np.isfinite(a).all() or not np.array_equal(a,repeat):raise ValueError('HT finite/input/repeat')
            defect=relative_defect(scaled-(.7+.2j)*a,scaled,(.7+.2j)*a)
            if not np.isfinite(defect) or defect>1e-11:raise ValueError('HT linearity')
            qualified=True
        finally:
            save('projected_HT_qualification',dict(passed=qualified,relative=defect,counts={k:v-trace_before.get(k,0) for k,v in trace.counts.items()},
                store_counts={k:v-store_before.get(k,0) for k,v in store.counts.items()},
                trace_seconds={k:v-trace_time_before.get(k,0) for k,v in trace.elapsed.items()},elapsed_seconds=time.perf_counter()-qualification_start,
                counter_scope='qualification kept separately; on success trace caps reset for one B4 witness plus I4; store totals include qualification'))
        for key in trace.counts:trace.counts[key]=0
        qualification_count_reset=True
        del before,a,repeat,scaled
        cu=CU(rhs)
        try:
            expected=get('component/frozen_CU')['CUg'];error=relative_defect(cu.array-expected,expected)
            if error>1e-10:raise ValueError('frozen full CU identity')
            save('projected_CU_identity',dict(relative=error))
        finally:cu.destroy()
        coupling=PhysicalBalancedCoupling(A,CU,HT,restriction,route='BAL_H',checkpoint=sample,level_identity='projected252 fixed p4 trace')
        def B(x):
            counts['B4']+=1
            if counts['B4']>65:raise RuntimeError('B4 cap')
            before_bottom=dict(bottom.counts);before_trace=dict(trace.counts);before_store=dict(store.counts)
            before_counts=dict(counts);before_counts['B4']-=1;begin=time.perf_counter();completed=False
            coupling.last_apply_facts={}
            try:
                value=coupling.apply(x);completed=True;return value
            finally:
                save(f"projected_B4_{counts['B4']:03d}",dict(completed=completed,elapsed_seconds=time.perf_counter()-begin,
                    coupling=dict(coupling.last_apply_facts),counts_delta={k:v-before_counts.get(k,0) for k,v in counts.items()},
                    S_counts_delta={k:v-before_bottom.get(k,0) for k,v in bottom.counts.items()},
                    trace_counts_delta={k:v-before_trace.get(k,0) for k,v in trace.counts.items()},
                    store_counts_delta={k:v-before_store.get(k,0) for k,v in store.counts.items()}))
        first=B(rhs);applied=None
        try:
            applied=A(first);coarse=restriction(rhs);image=restriction(applied);remaining=coarse-image;split=len(p2['offsets'])-1
            errors=dict(all=relative_defect(remaining,coarse,image),W=relative_defect(remaining[:split],coarse[:split],image[:split]),
                Q=relative_defect(remaining[split:],coarse[split:],image[split:]))
            save('projected_B4_rhs',dict(rhs=rhs.array.copy(),solution=first.array.copy(),applied=applied.array.copy(),balance=errors))
            if not all(np.isfinite(x) and x<=1e-11 for x in errors.values()):raise ValueError('full W/Q balance')
        finally:
            first.destroy()
            if applied is not None:applied.destroy()
        counts['I4']=1;result=solve_physical_i4(rhs,A,B,target=1e-4,sample=sample,save=save)
        save('projected_I4_result',dict(facts=result['facts'],rhs=rhs.array.copy(),solution=result['solution'].array.copy(),
            applied=result['applied'].array.copy(),residual=result['residual'].array.copy(),
            explicit_authority='qualified unchanged exact cached A4',source=g['execution_sha']))
        save('projected_component_complete',dict(status='COMPONENT_COMPLETED' if result['facts']['final_true_residual']<=1e-4 else 'COMPONENT_NUMERICAL_NEGATIVE',
            counts=counts,bottom_counts=dict(bottom.counts),I4=result['facts'],G5_closed=False,outer=0))
    finally:
        save('projected_component_counts',dict(counts=counts,bottom_counts=dict(bottom.counts),trace_counts=dict(trace.counts),
            store_counts=dict(trace.joint.counts) if trace.joint else {},trace_elapsed_total=dict(trace.elapsed),
            cached_counts=dict(g['cached'].counts),cached_seconds=dict(g['cached'].seconds),
            S_actions=space.action_count,S_action_seconds=space.action_seconds,routing=dict(space.owner.routing_costs),
            qualification_cost_record='projected_HT_qualification; store counts and trace elapsed include it',
            trace_counts_exclude_qualification=qualification_count_reset,elapsed=time.perf_counter()-started))
        if result:
            for key in ('solution','applied','residual'):result[key].destroy()
        if rhs is not None:rhs.destroy()
