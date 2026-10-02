"""Fixed same80/two40 full3D Q0--Q2 operator audit; no q factor or solve.

Candidate assembly uses only the two-cell FE spaces, exact local condensation
and streamed contributions. Saved full-period arrays are validation controls.
All polynomial channels, two branches per twist and all physical aliases stay.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy import sparse

from .task40extra_y_orbit_reference import pilot_config, collect_y_orbit_entities, build_y_orbit_layout
from .y_orbit_sparse_reference import _gate, integer_admission, csr_audit
from .y_orbit_two_cell_transport import TwoCellNativeTransport
from .y_orbit_two_cell_block_audit import TwoCellBranchCoordinates, TwoCellBlockProvider

PHYSICAL = "4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951"


def _sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()


def _csr(authority,prefix,shape,*,csc=False):
    cls=sparse.csc_matrix if csc else sparse.csr_matrix
    return cls((authority.load(prefix+'_data'),authority.load(prefix+'_indices'),
                authority.load(prefix+'_indptr')),shape=shape,copy=False)


def _save_csr(save_array,prefix,matrix):
    for key in ('data','indices','indptr'):save_array(prefix+'_'+key,getattr(matrix,key))


def _max(matrix):
    return float(np.max(np.abs(matrix.data),initial=0))


def _compare(matrix,reference,*,limit,label):
    delta=matrix-reference
    norm=float(sparse.linalg.norm(reference));maximum=_max(reference)
    dn=float(sparse.linalg.norm(delta));dm=_max(delta)
    result={'label':label,'absolute_Frobenius_error':dn,'absolute_max_error':dm,
            'reference_Frobenius_norm':norm,'reference_maximum':maximum,
            'relative_Frobenius_error':dn/max(norm,np.finfo(float).tiny),
            'relative_max_error':dm/max(maximum,np.finfo(float).tiny),'limit':limit}
    result['passed']=result['relative_Frobenius_error']<=limit and result['relative_max_error']<=limit
    return result


def _dense_packet(packet,key,n):
    if key in packet:return np.asarray(packet[key])
    rows,values=packet[key+'_sparse']
    value=np.zeros(n,dtype=complex);value[np.asarray(rows,dtype=np.int64)]=values
    return value


def _column_bridge(transport,local_layout,old_Q,*,save_array,gate,event):
    """Every native FE column, including all interiors; no complete new Q."""
    results=[]
    for branch in (0,1):
        q=transport.b+2*branch
        errors=np.empty(3968);norms=np.empty(3968)
        for start in range(0,3968,32):
            stop=min(start+32,3968);w=stop-start
            _gate(gate,'complete_FE_map_column_panel',payload=(7936*5+15872*5)*w*16,
                  workspace=8<<20,validation_only_saved_full_Q=True)
            local=local_layout.q[:,branch*3968+start:branch*3968+stop].toarray()
            lifted=transport.lift_primal(local)
            old=old_Q[:,q*3968+start:q*3968+stop].toarray()
            errors[start:stop]=np.linalg.norm(lifted-old,axis=0)
            norms[start:stop]=np.linalg.norm(old,axis=0)
            recovered=transport.extract_primal(lifted)
            if np.linalg.norm(recovered-local)>1e-12*max(np.linalg.norm(local),np.finfo(float).tiny):
                raise ValueError('complete native primal lift/extraction failed')
        save_array(f'q_{q}_map_column_error_norms',errors)
        save_array(f'q_{q}_map_reference_column_norms',norms)
        maximum=float(np.max(errors/np.maximum(norms,np.finfo(float).tiny)))
        item={'q':q,'columns':3968,'maximum_column_relative_error':maximum,
              'all_interior_channels_retained':True,'new_full_Q_created':False}
        event('complete_native_FE_map_bridge',item);results.append(item)
        if not np.isfinite(maximum) or maximum>1e-12:raise ValueError('all-column full-Q bridge failed')
    return results


def _actual_cells(global_setup,local_setup,*,event):
    """Compare actual translated vertex metrics and tags, without rounded keys."""
    gm,lm=global_setup['mesh'],local_setup['mesh']
    ga,la=gm.geometry.x,lm.geometry.x
    gd,ld=gm.geometry.dofmap,lm.geometry.dofmap
    gt=global_setup['mesh_data'].cell_tags.values
    lt=local_setup['mesh_data'].cell_tags.values
    h=float(np.max(la[:,1])-np.min(la[:,1]))
    centers=np.asarray([np.mean(ga[gd[c]],axis=0) for c in range(80)])
    used=[];maximum=0.0
    for c in range(40):
        xyz=la[ld[c]]
        for s in range(2):
            shift=np.array([0.,s*h,0.]);center=np.mean(xyz+shift,axis=0)
            distance=np.max(np.abs(centers-center),axis=1)
            matches=np.flatnonzero(distance<=1e-12)
            if len(matches)!=1:raise ValueError('actual quotient cell lacks unique full-period cell')
            original=int(matches[0]);used.append(original)
            old=ga[gd[original]];new=xyz+shift
            old=old[np.lexsort((old[:,2],old[:,1],old[:,0]))]
            new=new[np.lexsort((new[:,2],new[:,1],new[:,0]))]
            difference=float(np.max(np.abs(old-new)));maximum=max(maximum,difference)
            if difference>1e-12 or lt[c]!=gt[original]:
                raise ValueError('actual full3D cell metric/material identity fails')
    if sorted(used)!=list(range(80)):raise ValueError('full80 actual cells not covered exactly once')
    facts={'actual_cell_material_tags_equal':True,'actual_cell_metric_equal':True,
           'maximum_actual_vertex_difference':maximum,'metric_gate':1e-12,
           'cell_cover_exactly_once':True,'no_rounded_coordinate_keys':True}
    event('actual_full3D_material_metric_identity',facts);return facts


def _functional_folding(global_spool,local_spool,transport,global_rows,local_rows,context,
                        *,save_array,gate,event):
    """Fresh raw comparison and lift of actually masked local coefficients."""
    columns_C=[];rows_D=[];ledger=[]
    for local_index,original in enumerate(context.original_mode_indices):
        _gate(gate,'current_raw_and_masked_fold',payload=16*(17204*16+8940*16),
              workspace=4<<20,no_all_mode_dense_packet=True)
        gp=global_spool.packet(original);lp=local_spool.packet(local_index)
        row={'original_mode_index':int(original)}
        for name in ('C','D'):
            gs=_dense_packet(gp,'raw_'+name,17204);ls=_dense_packet(lp,'raw_'+name,8940)
            gslaves=np.setdiff1d(np.arange(17204),global_rows);lslaves=np.setdiff1d(np.arange(8940),local_rows)
            if np.any(gs[gslaves]!=0) or np.any(ls[lslaves]!=0):
                raise ValueError('raw native MPC slave storage must be exactly zero before restriction')
            g=gs[global_rows];local=ls[local_rows]
            folded=(transport.fold_raw_coupling(g) if name=='C' else transport.fold_raw_projection(g))
            scale=float(np.linalg.norm(folded)+np.linalg.norm(local))
            error=float(np.linalg.norm(folded-local))
            row[f'raw_{name}_fold_error_norm']=error
            row[f'raw_{name}_fold_operation_scale']=scale
            lifted_raw=(transport.lift_raw_coupling(local) if name=='C'
                        else transport.lift_raw_projection(local))
            lift_error=float(np.linalg.norm(lifted_raw-g))
            lift_scale=float(np.linalg.norm(lifted_raw)+np.linalg.norm(g))
            row[f'raw_{name}_lift_error_norm']=lift_error
            row[f'raw_{name}_lift_operation_scale']=lift_scale
            # Save before a possible gate failure; no lost raw evidence.
            if (not np.isfinite(error+scale+lift_error+lift_scale) or min(scale,lift_scale)<=0
                    or error>1e-10*scale or lift_error>1e-10*lift_scale):
                save_array(f'failed_raw_{name}_{original}_global',g)
                save_array(f'failed_raw_{name}_{original}_local',local)
                save_array(f'failed_raw_{name}_{original}_folded',folded)
                event('raw_fold_failure',row)
                raise ValueError('raw before-mask quotient fold failed')
            ids,values=lp['stored_'+name+'_sparse']
            storage=np.zeros(8940,complex);storage[np.asarray(ids,dtype=np.int64)]=values
            if np.any(storage[lslaves]!=0):raise ValueError('stored local carrier has nonzero slave support')
            independent=storage[local_rows]
            lifted=(transport.lift_raw_coupling(independent) if name=='C'
                    else transport.lift_raw_projection(independent))
            full=np.zeros(17204,complex);full[global_rows]=lifted
            support=np.flatnonzero(full!=0) # exact zero only, both original cutoffs unchanged
            _gate(gate,'retain_current_masked_functional',payload=support.size*24,
                  workspace=1<<20,no_magnitude_sparsification=True)
            item=(int(original),support,full[support].copy())
            (columns_C if name=='C' else rows_D).append(item)
        ledger.append(row)
    return columns_C,rows_D,ledger


def _assemble_functionals(items,*,kind,gate,index_dtype):
    nnz=sum(len(row) for _,row,_ in items)
    integer_admission((17204,532) if kind=='C' else (532,17204),nnz,index_dtype=index_dtype)
    _gate(gate,'complete532_folded_masked_'+kind,payload=nnz*(16+2*np.dtype(index_dtype).itemsize),
          workspace=nnz*48+(17205+533)*np.dtype(index_dtype).itemsize)
    first=np.concatenate([r for _,r,_ in items]);second=np.concatenate(
        [np.full(len(r),i,dtype=index_dtype) for i,r,_ in items])
    values=np.concatenate([v for _,_,v in items])
    if kind=='C':return sparse.coo_matrix((values,(first,second)),shape=(17204,532)).tocsc()
    return sparse.coo_matrix((values,(second,first)),shape=(532,17204)).tocsr()


def _full_action_witness(global_base,local_base,transport,*,save_array,gate,event):
    from petsc4py import PETSc
    rng=np.random.default_rng(20261001+transport.b)
    _gate(gate,'full_original_action_interior_witness',payload=2*(17204+8940)*16,
          workspace=16<<20)
    x=rng.standard_normal(7936)+1j*rng.standard_normal(7936)
    gx=transport.lift_primal(x)
    save_array(f'twist_{transport.b}_original_action_local_state',x)
    save_array(f'twist_{transport.b}_original_action_global_state',gx)
    gv=PETSc.Vec().createSeq(17204,comm=PETSc.COMM_SELF)
    lv=PETSc.Vec().createSeq(8940,comm=PETSc.COMM_SELF)
    go=gv.duplicate();lo=lv.duplicate()
    try:
        gv.set(0);lv.set(0)
        gv.array[transport.full.independent]=gx;lv.array[transport.local.independent]=x
        global_base['physical_action'].apply(gv,go)
        local_base['physical_action'].apply(lv,lo)
        actual=lo.array[transport.local.independent].copy()
        expected=transport.fold_dual(go.array[transport.full.independent])
        defect=float(np.linalg.norm(actual-expected)/max(np.linalg.norm(expected),np.finfo(float).tiny))
        save_array(f'twist_{transport.b}_original_action_local',actual)
        save_array(f'twist_{transport.b}_original_action_folded',expected)
        fact={'twist':transport.b,'relative_original_FE_action_defect':defect,
              'local_FE_rows':7936,'all_local_interior_rows':4320,'global_FE_rows':15872,
              'q_factors_used':False,'volume_and_DtN_original_action':True}
        event('fresh_full_original_action_witness',fact)
        if not np.isfinite(defect) or defect>1e-10:raise ValueError('original full3D lift/dual action fails')
        return fact
    finally:
        for v in (go,lo,gv,lv):v.destroy()


def _complete_recovery_witness(condensed,local_layout,*,save_array,gate,event):
    """Manufactured augmented state; only inherited cell-interior LU applies.

    The FE and port right hand sides come from the original live volume and
    carrier, independently of the condensed contribution iterator. Arbitrary
    nonzero interior and port loads survive reduction and original recovery.
    """
    from petsc4py import PETSc
    base=condensed.action_bundle;carrier=base['dtn_action'].carrier
    n=8940;m=len(carrier.entries);b=condensed.qbase
    _gate(gate,'complete_interior_port_rhs_recovery_witness',payload=(10*n+10*m)*16,
          workspace=16<<20,global_and_q_factors=0,inherited_cell_LU_only=True)
    rng=np.random.default_rng(20261003+b)
    state=np.zeros(n,complex)
    state[local_layout.independent]=rng.standard_normal(7936)+1j*rng.standard_normal(7936)
    alpha=rng.standard_normal(m)+1j*rng.standard_normal(m)
    source=PETSc.Vec().createSeq(n,comm=PETSc.COMM_SELF)
    try:
        source.array[:]=state
        # Consume the borrowed reusable volume output before another apply.
        top=base['volume_action'].apply(source).array.copy()
        projection=np.empty(m,complex);H=np.empty(m)
        for i,e in enumerate(carrier.entries):
            np.add.at(top,e.coupling_rows,e.coupling_values*alpha[i])
            projection[i]=np.dot(e.projection_values,state[e.projection_rows]);H[i]=e.normalization_h
        bottom=H*alpha-projection
        reduced_rhs=condensed.reduce_rhs(top,port_rhs=bottom,rhs_is_mpc_dual=True)
        reduced_state=np.concatenate((state[condensed.trace_original_rows],alpha))
        reduced_action=condensed.action.apply(reduced_state)
        recovered=condensed.recover_storage(reduced_state,full_rhs=top,expand_trace=False)
        reduce_error=float(np.linalg.norm(reduced_action-reduced_rhs)/max(np.linalg.norm(reduced_rhs),np.finfo(float).tiny))
        recovery_error=float(np.linalg.norm(recovered-state)/max(np.linalg.norm(state),np.finfo(float).tiny))
        slaves=np.asarray(base['setup']['floquets'][4].mpc.slaves,dtype=np.int64)
        fact={'twist':b,'reduced_original_augmented_action_defect':reduce_error,
              'full_original_storage_recovery_defect':recovery_error,
              'arbitrary_interior_rhs_nonzero_count':int(np.count_nonzero(top[condensed.interior_original_rows])),
              'all_interior_rows':4320,'port_rhs_norm':float(np.linalg.norm(bottom)),
              'strict_slave_zero':bool(np.all(recovered[slaves]==0)),'global_and_q_factors':0,
              'inherited_cell_interior_LU_used':True}
        for name,value in (('state',state),('alpha',alpha),('FE_rhs',top),('port_rhs',bottom),
                           ('reduced_rhs',reduced_rhs),('reduced_action',reduced_action),('recovered',recovered)):
            save_array(f'twist_{b}_complete_recovery_'+name,value)
        event('complete_original_interior_port_recovery_witness',fact)
        if (not np.isfinite(reduce_error+recovery_error) or max(reduce_error,recovery_error)>1e-10
                or fact['arbitrary_interior_rhs_nonzero_count']!=4320 or fact['port_rhs_norm']<=0
                or not fact['strict_slave_zero']):
            raise ValueError('complete original arbitrary interior/port recovery witness failed')
        return fact
    finally:source.destroy()


def _old_validation_q_map(authority,q,gate):
    """Validation only; never used by candidate contribution construction."""
    rt=_csr(authority,'trace_R_t',(7232,7232));f=_csr(authority,'trace_F_t',(7232,7232))
    _gate(gate,'saved_validation_only_q_map',payload=32<<20,workspace=32<<20)
    qt=rt@f[:,q*1808:(q+1)*1808]
    labels=authority.load('port_q_labels');h=authority.load('port_original_H')
    ids=np.flatnonzero(labels==q)
    ports=sparse.csr_matrix((1/np.sqrt(h[ids]),(ids,np.arange(len(ids)))),shape=(532,len(ids)))
    return sparse.block_diag((qt,ports),format='csr')


def run_two_cell_operator_audit(input_path,*,authority,event,save_array,allocation_gate,run_directory):
    from mpi4py import MPI
    from petsc4py import PETSc
    from .fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from .fullspace_same_mesh_hcurl_pmg_physical import build_same_mesh_physical_action,destroy_same_mesh_physical_action
    from .fullspace_dtn_action import build_ordered_mode_manifest,_jsonable
    from .y_orbit_quotient_context import build_two_cell_assembly_config,build_two_cell_quotient_context
    from .y_orbit_quotient_condensed import build_quotient_condensed
    from .y_orbit_quotient_raw_qualification import qualify_quotient_raw_bundle
    from .y_orbit_raw_packet_spool import RawModeSpool
    from .y_orbit_condensed_adapter import trace_layout_coordinates

    root=Path(run_directory);cfg,axes,input_sha=pilot_config(input_path,azimuth_deg=5.)
    cfg=replace(cfg,nedelec_degree=4,visualization_degree=4,case_name='y_orbit_p4_algebra_regular')
    if input_sha!=authority.report['input_sha256']:raise ValueError('immutable authority input differs')
    if {name:list(values) for name,values in axes.items()}!=authority.report['axes_nm']:
        raise ValueError('all original full-period actual axes must match the frozen authority')
    integer_admission((17204,17204),0,index_dtype=PETSc.IntType)
    original=local=condensed=None
    twists=[];cross=[];raw=[];all_C=[];all_D=[];diagonal_norm={};diagonal_max={}
    # All paths belong to this fresh ignored run; descriptor paths stay bound.
    def spool(name):return RawModeSpool(root/name,save_array=save_array,
                         allocation_gate=allocation_gate,root_directory=root)
    global_spool=spool('raw_global')
    try:
        _gate(allocation_gate,'original80_full3D_setup',workspace=128<<20,global_S_F_Q_created=False)
        setup=_build_same_mesh_levels(cfg,MPI.COMM_SELF,(4,),include_positive_coefficients=False)
        original=build_same_mesh_physical_action(setup,cfg,4,dtn_phase_gauge='boundary_plane',
                                                raw_mode_observer=global_spool.observe)
        modes=tuple(original['modes']);mode_rows,_,sha=build_ordered_mode_manifest(modes,cfg)
        inventory=(modes,tuple(mode_rows),sha)
        keys=[[str(m.side),int(m.m),int(m.n),str(m.polarization)] for m in modes]
        if sha!=PHYSICAL or keys!=authority.report['mode_keys']:raise ValueError('all532 unchanged physical inventory required')
        _gate(allocation_gate,'full_native_entity_records_without_F_Q',payload=2*15872*108*16,
              workspace=128<<20,full_F_Q_materialization=False)
        full_entities=collect_y_orbit_entities(setup['spaces'][4],setup['floquets'][4],cfg,axes)
        if not np.array_equal(full_entities.independent,authority.load('independent_storage_rows')):
            raise ValueError('actual full native independent inventory differs')
        old_Q=_csr(authority,'full_Q',(15872,15872))
        old_H=authority.load('port_original_H');local_cfg=build_two_cell_assembly_config(cfg)
        for b in (0,1):
            context=build_two_cell_quotient_context(cfg,local_cfg,inventory,twist_index=b)
            local_axes=dict(zip(('x','y','z'),context.local_axes,strict=True))
            local_spool=spool('raw_twist_'+str(b))
            _gate(allocation_gate,'two40_explicit_MPC_setup',workspace=128<<20,
                  explicit_eta_not_principal_tau_root=True)
            local_setup=_build_same_mesh_levels(local_cfg,MPI.COMM_SELF,(4,),
                include_positive_coefficients=False,research_phase_override=context.phase_override)
            cell_facts=_actual_cells(setup,local_setup,event=event)
            local=build_same_mesh_physical_action(local_setup,local_cfg,4,mode_inventory=inventory,
                physical_cfg=cfg,quotient_context=context,dtn_phase_gauge='boundary_plane',
                raw_mode_observer=local_spool.observe)
            _gate(allocation_gate,'local2_Hcurl_maps_all_channels',payload=64<<20,workspace=192<<20)
            local_layout=build_y_orbit_layout(local_setup['spaces'][4],local_setup['floquets'][4],
                local_cfg,local_axes,wrap_phase_y=context.tau,cell_phase_y=context.eta)
            local_entities=collect_y_orbit_entities(local_setup['spaces'][4],local_setup['floquets'][4],local_cfg,local_axes)
            transport=TwoCellNativeTransport(full_entities,local_entities,twist_index=b,eta=context.eta,
                global_phase=cfg.floquet_phase_y,global_ky=cfg.ky,global_period_y=cfg.period_y)
            maps=_column_bridge(transport,local_layout,old_Q,save_array=save_array,gate=allocation_gate,event=event)
            c,d,rows=_functional_folding(global_spool,local_spool,transport,full_entities.independent,
                 local_entities.independent,context,save_array=save_array,gate=allocation_gate,event=event)
            all_C.extend(c);all_D.extend(d);raw.extend(rows)
            action_fact=_full_action_witness(original,local,transport,save_array=save_array,gate=allocation_gate,event=event)
            record=root/f'raw_twist_{b}'/'raw_port_receipt.json'
            _gate(allocation_gate,'local_live_literal_raw_oracle',payload=16<<20,workspace=128<<20,
                  q_factors_forbidden=True,literal_compiler_allowance_not_guarantee=True)
            receipt=qualify_quotient_raw_bundle(local,raw_mode_packets=local_spool.packets(),record_path=record,
                expected_physical_manifest=PHYSICAL,expected_global_ordered_keys=[(i,*key) for i,key in enumerate(keys)])
            event('same_live_quotient_raw_port_audit_complete',{'b':b,'status':receipt['status'],'path':str(record),'sha256':_sha(record)})
            condensed=build_quotient_condensed(local,global_mode_inventory=inventory,
                 global_mode_indices=context.original_mode_indices,qbase=b,allocation_gate=allocation_gate)
            for name,values in (('independent_storage_rows',condensed.independent_original_rows),
                    ('trace_original_rows',condensed.trace_original_rows),
                    ('interior_original_rows',condensed.interior_original_rows),
                    ('slave_storage_rows',np.asarray(local_setup['floquets'][4].mpc.slaves))):
                save_array(f'twist_{b}_'+name,values)
            recovery_fact=_complete_recovery_witness(condensed,local_layout,save_array=save_array,
                                                    gate=allocation_gate,event=event)
            trace=trace_layout_coordinates(local_layout,condensed.system,allocation_gate=allocation_gate)
            coords=TwoCellBranchCoordinates(trace,condensed,context,global_original_H=old_H,
                                            allocation_gate=allocation_gate,index_dtype=PETSc.IntType)
            provider=TwoCellBlockProvider(condensed,coords,allocation_gate=allocation_gate)
            branches=[];local_cross=[]
            for qlocal in (0,1):
                q=b+2*qlocal
                matrix=provider.block(qlocal,qlocal);csr_audit(matrix,petsc_index_dtype=PETSc.IntType)
                _save_csr(save_array,f'q_{q}_S',matrix)
                compare=_compare(matrix,authority.q_block(q),limit=1e-11,label=f'q_{q}_full_p4_authority')
                event('two_cell_branch_original_authority_comparison',compare)
                if not compare['passed']:raise ValueError('masked quotient block does not commute; preserved, no cutoff relaxation')
                diagonal_norm[q]=float(sparse.linalg.norm(matrix));diagonal_max[q]=_max(matrix)
                if (not np.isfinite(diagonal_norm[q]+diagonal_max[q])
                        or min(diagonal_norm[q],diagonal_max[q])<=0):
                    raise ValueError('zero or nonfinite diagonal block cannot normalize leakage')
                branches.append({'local_branch':qlocal,'q':q,'shape':list(matrix.shape),'csr_prefix':f'q_{q}_S',
                    'original_mode_indices':[i for i,branch in zip(context.original_mode_indices,context.local_branch_indices,strict=True) if branch==qlocal]})
                del matrix
            for p,q in ((0,1),(1,0)):
                matrix=provider.block(p,q);gp,gq=b+2*p,b+2*q;prefix=f'cross_{gp}_{gq}'
                _save_csr(save_array,prefix,matrix)
                fact={'p':gp,'q':gq,'shape':list(matrix.shape),'csr_prefix':prefix,'scope':'local_twist',
                      'absolute_Frobenius_norm':float(sparse.linalg.norm(matrix)),'absolute_maximum':_max(matrix)}
                local_cross.append(fact);cross.append(fact);del matrix
            h=np.asarray([e.normalization_h for e in local['dtn_action'].carrier.entries])
            save_array(f'twist_{b}_original_H',h)
            twists.append({'b':b,'theta':_jsonable(context.theta),'eta':_jsonable(context.eta),'tau':_jsonable(context.tau),
                'sector_original_indices':list(context.original_mode_indices),'local_original_H_artifact':f'twist_{b}_original_H',
                'raw_port_receipt':{'path':str(record.relative_to(root)),'sha256':_sha(record)},'branches':branches,
                'maps':maps,'topology':local_layout.audit,'transport':transport.audit,'cell_metric_material':cell_facts,
                'original_action_witness':action_fact,'condensation':_jsonable(condensed.audit),
                'complete_interior_port_recovery_witness':recovery_fact,
                'local_interior_LU_used':True,'global_or_q_factors_used':False})
            condensed.destroy();condensed=None
            destroy_same_mesh_physical_action(local);local=None
            del provider,coords,trace,local_layout,local_entities,transport,local_setup
        # Saved full-period S/maps are validation only, after every FE column
        # has passed the complete independently built two-cell lift bridge.
        S=_csr(authority,'reference_S',(7764,7764))
        for q in range(4):
            right=_old_validation_q_map(authority,q,allocation_gate)
            _gate(allocation_gate,'old_original_S_validation_product',payload=96<<20,workspace=96<<20)
            action=S@right
            for p in range(4):
                if p%2==q%2:continue
                left=_old_validation_q_map(authority,p,allocation_gate)
                matrix=(left.conj().T@action).tocsr();prefix=f'cross_{p}_{q}'
                _save_csr(save_array,prefix,matrix)
                cross.append({'p':p,'q':q,'shape':list(matrix.shape),'csr_prefix':prefix,'scope':'full_original_action',
                    'validation_basis':'immutable original S plus full-Q columns proven equal to implicit candidate',
                    'absolute_Frobenius_norm':float(sparse.linalg.norm(matrix)),'absolute_maximum':_max(matrix)})
                del left,matrix
            del right,action
        for row in cross:
            p,q=row['p'],row['q'];row['relative_Frobenius_norm']=row['absolute_Frobenius_norm']/min(diagonal_norm[p],diagonal_norm[q])
            row['relative_maximum']=row['absolute_maximum']/min(diagonal_max[p],diagonal_max[q])
            event('complete_cross_branch_audit',row)
            if row['relative_Frobenius_norm']>1e-11 or row['relative_maximum']>1e-11:
                raise ValueError('cross-branch leakage gate fails; no small-entry deletion')
        C=_assemble_functionals(all_C,kind='C',gate=allocation_gate,index_dtype=PETSc.IntType)
        D=_assemble_functionals(all_D,kind='D',gate=allocation_gate,index_dtype=PETSc.IntType)
        _save_csr(save_array,'folded_masked_port_C',C);_save_csr(save_array,'folded_masked_port_D',D)
        old_C=_csr(authority,'original_port_C',(17204,532),csc=True)
        old_D=_csr(authority,'original_port_D',(532,17204))
        for i in range(532):
            for name,value,old in (('C',C[:,i],old_C[:,i]),('D',D[i:i+1],old_D[i:i+1])):
                fact=_compare(value,old,limit=1e-10,label=f'mode_{i}_masked_{name}')
                if not fact['passed']:
                    event('masked_cutoff_noncommutation',fact)
                    raise ValueError('actual production mask does not commute with quotient; no cutoff change')
        return {'status':'QUOTIENT_OPERATOR_AUDIT_PASS','audit_only':True,'degree':4,'factor_count':0,
            'factor_count_scope':'global_and_q_numeric_factors','local_interior_LU_used':True,
            'PDE_solved':False,'official_results':False,'physical_generator_manifest_sha256':sha,
            'global_mode_keys':keys,'twists':twists,'cross_branch_blocks':sorted(cross,key=lambda r:(r['p'],r['q'])),
            'raw_fold_per_mode':sorted(raw,key=lambda r:r['original_mode_index']),'input_sha256':input_sha,
            'structural_audit':{**{k:True for k in ('complete_trace_interior_closure','all_independent_rows_once',
                'slave_storage_zero','actual_cell_material_tags_equal','actual_cell_metric_equal','full_original_axes_retained',
                'original_mode_objects_retained','full_original_cutoffs_unchanged','local_maps_built_independently','old_full_maps_validation_only')},
                **{k:False for k in ('candidate_full_Ny_CSR_created','candidate_full_F_created','candidate_full_Q_created')}},
            'qualification_scope':'Q0-Q2 full3D operator architecture only; physical RHS/output and quotient inverse/notch Q3-Q5 deferred'}
    finally:
        if condensed is not None:condensed.destroy()
        if local is not None:destroy_same_mesh_physical_action(local)
        if original is not None:destroy_same_mesh_physical_action(original)
