"""Bounded full3D quotient-reference inverse and original notch experiment.

The prefactor stage restores frozen coefficients and compares newly formed
local blocks only. The solve stage is an explicit separate admission.
"""
from __future__ import annotations
from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path
import sys
import numpy as np
from scipy import sparse

from .task40extra_y_orbit_reference import pilot_config,collect_y_orbit_entities,build_y_orbit_layout,FullOriginalAction,solve_notched_fgmres,SEED,LIMITS
from .y_orbit_two_cell_inverse import StreamedFullYLayout,FourBranchFactors,CompleteTwoCellInverse
from .y_orbit_two_cell_transport import TwoCellNativeTransport
from .y_orbit_two_cell_block_audit import TwoCellBranchCoordinates,TwoCellBlockProvider
from .y_orbit_sparse_reference import _gate,sparse_hash,csr_audit,sampled_right_pc_defect
from .y_orbit_two_cell_audit import _compare,_save_csr,_actual_cells


def _original_augmented_packet(bundle,layout,f,g,x,alpha,*,label,save,event):
    from petsc4py import PETSc
    from .fullspace_p4_blr import augmented_residual_identity
    n=layout.full_rows;carrier=bundle['dtn_action'].carrier
    source=PETSc.Vec().createSeq(n,comm=PETSc.COMM_SELF);target=source.duplicate()
    try:
        source.set(0);source.array[layout.independent]=x
        bundle['physical_action'].apply(source,target);action=target.array.copy()
        volume=bundle['volume_action'].apply(source).array.copy()
        coupling=np.zeros(n,complex);correction=np.zeros(n,complex)
        projection=np.empty(532,complex);h=np.empty(532);scale=np.empty(532)
        for i,e in enumerate(carrier.entries):
            np.add.at(coupling,e.coupling_rows,e.coupling_values*alpha[i])
            np.add.at(correction,e.coupling_rows,e.coupling_values*g[i]/e.normalization_h)
            projection[i]=np.dot(e.projection_values,source.array[e.projection_rows]);h[i]=e.normalization_h
            scale[i]=np.linalg.norm(e.projection_values)*np.linalg.norm(x)+abs(h[i]*alpha[i])+abs(g[i])
        rhs_storage=np.zeros(n,complex);rhs_storage[layout.independent]=f
        effective=rhs_storage-correction
        native=effective-action;top=rhs_storage-volume-coupling;port=projection-h*alpha+g
        identity=augmented_residual_identity(native,top,port,carrier,
            rhs_norm=float(np.linalg.norm(effective)),native_action_norm=float(np.linalg.norm(action)))
        values={'rhs_storage':rhs_storage,'solution_storage':source.array.copy(),'original_action':action,
                'volume_action':volume,'coupling_action':coupling,'auxiliary_ports':alpha,'projection':projection,
                'normalization_h':h,'native_residual':native,'augmented_FE_residual':top,'augmented_port_residual':port}
        for name,value in values.items():save(label+'_'+name,value)
        save(label+'_effective_rhs',effective[layout.independent]);save(label+'_port_operation_scale',scale)
        residual=float(np.linalg.norm(native)/max(np.linalg.norm(effective),np.finfo(float).tiny))
        fe=float(np.linalg.norm(top)/max(np.linalg.norm(rhs_storage),np.finfo(float).tiny))
        closure=float(np.linalg.norm(port)/max(np.linalg.norm(projection)+np.linalg.norm(h*alpha)+np.linalg.norm(g),np.finfo(float).tiny))
        operation=float(np.max(np.divide(np.abs(port),scale,out=np.zeros_like(scale),where=scale>0)))
        if np.any((scale==0)&(port!=0)):operation=float('inf')
        packet={'full_original_true_residual':residual,'augmented_FE_true_residual':fe,
                'augmented_port_closure_relative':closure,'per_mode_port_operation_scaled_max':operation,
                'augmented_residual_identity':identity,'full_native_slave_zero':bool(np.all(source.array[np.asarray(bundle['setup']['floquets'][4].mpc.slaves)]==0)),
                'nonzero_port_RHS_count':int(np.count_nonzero(g)),'all_q_primal_norms':layout.modal_norms(x,dual=False)}
        from .dtn_boundary_plane_qualification import _failure_diagnostic
        event('original_augmented_manufactured_control',_failure_diagnostic({'label':label,**packet}))
        if (not all(np.isfinite(v) and v<=1e-10 for v in (residual,fe,closure,operation))
                or not packet['full_native_slave_zero'] or identity.get('passed') is not True):
            raise ValueError('full original arbitrary FE/port RHS inverse gate failed')
        return packet
    finally:target.destroy();source.destroy()


def _check_original(packet):
    keys=('full_original_true_residual','augmented_FE_true_residual','augmented_port_closure_relative')
    if any(not np.isfinite(packet[k]) or packet[k]>1e-10 for k in keys):raise ValueError('original full3D residual failed')
    if packet.get('full_native_slave_zero') is not True:raise ValueError('native MPC slave-zero gate failed')
    if packet['augmented_residual_identity'].get('passed') is not True:raise ValueError('original augmented/native identity failed')


def _recovery_identity_gate(condensed,setup,authority,b,*,event):
    """Bind every recovery row and the actual numeric cell tensors pre-factor.

    New compiler signatures are recorded separately. Exact numeric tensors
    and unchanged cache recipe inputs provide the bridge to old recovery math.
    """
    from .fullspace_dtn_action import _jsonable
    rows={'independent_storage_rows':condensed.independent_original_rows,
          'trace_original_rows':condensed.trace_original_rows,'interior_original_rows':condensed.interior_original_rows,
          'slave_storage_rows':np.asarray(setup['floquets'][4].mpc.slaves)}
    row_facts={}
    for name,value in rows.items():
        old=authority.load(f'twist_{b}_'+name)
        row_facts[name]=bool(value.dtype==old.dtype and np.array_equal(value,old))
    actual=_jsonable(condensed.audit['condensation'])
    old=_jsonable(authority.report['twists'][b]['condensation']['condensation'])
    tensors=actual['action_only_complete_tensor_identities'];old_tensors=old['action_only_complete_tensor_identities']
    numeric_equal=tensors==old_tensors
    policy=actual['operator_cache_identity'];old_policy=old['operator_cache_identity']
    recipe_equal=(policy['key_dependencies']==old_policy['key_dependencies'] and policy['scope']==old_policy['scope'])
    signatures={}
    if set(policy['policy_signatures'])!=set(old_policy['policy_signatures']):recipe_equal=False
    for name,new in policy['policy_signatures'].items():
        previous=old_policy['policy_signatures'].get(name,{})
        fields=set(new)-{'ufcx_form_signature'}
        if fields!=set(previous)-{'ufcx_form_signature'} or any(new[k]!=previous[k] for k in fields):recipe_equal=False
        signatures[name]={'historical':previous.get('ufcx_form_signature'),'new':new.get('ufcx_form_signature')}
        if any(not isinstance(v,str) or not v for v in signatures[name].values()):recipe_equal=False
    result={'twist':b,'native_row_inventory_equal':row_facts,'raw_oriented_tensor_inventory':tensors,
            'raw_oriented_tensor_exact_equal':numeric_equal,'tensor_count':len(tensors),
            'cache_recipe_equal':recipe_equal,'new_cache_recipe':policy,'historical_cache_recipe':old_policy,
            'compiler_signatures':signatures,'new_volume_identity_claimed_equal_to_old_JIT':False}
    event('complete_recovery_identity_before_factor',result)
    if not all(row_facts.values()) or not numeric_equal or len(tensors)!=20 or not recipe_equal:
        raise ValueError('new volume/recovery row/tensor/cache identity bridge failed before factor')
    return result


def run_quotient_inverse_probe(input_path,*,authority,full_period_authority,event,save_array,allocation_gate,run_directory,stage,shared_transforms=False):
    from mpi4py import MPI
    from petsc4py import PETSc
    from .fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from .fullspace_same_mesh_hcurl_pmg_physical import _build_split_volume_action,build_physical_rhs,destroy_same_mesh_physical_action
    from .fullspace_physical_action import FullspacePhysicalAction
    from .fullspace_dtn_action import build_dynamic_mode_inventory
    from .y_orbit_quotient_context import build_two_cell_assembly_config,build_two_cell_quotient_context
    from .y_orbit_quotient_condensed import build_quotient_condensed
    from .y_orbit_condensed_adapter import trace_layout_coordinates
    from .y_orbit_centered_evidence import original_packet,recovered_field_and_modes,require_output_packet,interior_only_rhs,fixture_interior_positions,save_mpc_inventory,save_centered_port_inventory,SOURCES
    from .y_orbit_sparse_probe import _notch_supported_rhs
    from src.geometry.mesh_builder_3d import _mark_cells,_rectangular_air_void_audit
    if stage not in ('prefactor','solve'):raise ValueError('explicit bounded stage required')
    if type(shared_transforms) is not bool:raise ValueError('shared transforms must be an explicit boolean opt-in')
    if shared_transforms and getattr(authority,'storage_source_bridge',None) is None:
        raise ValueError('shared live setup requires the actual new storage-only source bridge')
    cfg,axes,input_sha=pilot_config(input_path,azimuth_deg=5.)
    cfg=replace(cfg,nedelec_degree=4,visualization_degree=4,case_name='y_orbit_p4_algebra_regular')
    if input_sha!=authority.report['input_sha256']:raise ValueError('frozen input identity differs')
    inventory=build_dynamic_mode_inventory(cfg)
    bank=evidence=None
    if shared_transforms:
        if tuple(len(axes[name])-1 for name in ('x','y','z'))!=(4,4,5):
            raise ValueError('shared transforms are qualified only for the existing same80 p4 profile')
        from .y_orbit_transform_bank import RunLocalTransformBank
        from .y_orbit_shared_transform_evidence import SharedTransformEvidence
        bank=RunLocalTransformBank(mapping_limit=LIMITS['mapping'])
        evidence=SharedTransformEvidence(bank,save_array=save_array,event=event,
            allocation_gate=allocation_gate,mapping_limit=LIMITS['mapping'])
        evidence.snapshot('before_collect')
    _gate(allocation_gate,'full80_actual_mesh_space_MPC_constructor',payload=16<<20,workspace=128<<20)
    full_setup=_build_same_mesh_levels(cfg,MPI.COMM_SELF,(4,),include_positive_coefficients=False)
    original=notched=None;action0=action1=None;factors=None;sectors=[]
    restorations=[];blocks=[];matrices={};report={};recovery_bindings=[]
    layout=full_entities=local_entities=local_layout=transport=coords=trace=inverse=provider=matrix=old=setup=bundle=value=condensed=ids=default_entities=None
    def output_save(name,value):
        if isinstance(value,(list,tuple)):
            if not name.endswith('_direct_plane_outgoing_power_diagnostic') or len(value)!=532:
                raise TypeError('only the known532 real power diagnostic list may be converted')
            _gate(allocation_gate,'known_mode_power_list_conversion',payload=532*8,workspace=1<<20)
            value=np.asarray(value,dtype=np.float64)
        return save_array(name,value)
    try:
        original,restored=authority.restore_bundle(full_setup,cfg,4,global_mode_inventory=inventory)
        restorations.append(restored)
        _gate(allocation_gate,'full_native_entity_records_and_inverse',payload=2*15872*108*16,
              workspace=128<<20,full_Ny_F_Q_created=False)
        if shared_transforms:
            full_entities=collect_y_orbit_entities(full_setup['spaces'][4],full_setup['floquets'][4],cfg,axes,transform_bank=bank)
            evidence.named.update(full_entities.named_backing_arrays('full'))
            evidence.snapshot('full_after_collect')
            _gate(allocation_gate,'shared_full_default_complete_control',payload=2*15872*108*16,workspace=128<<20)
            default_entities=collect_y_orbit_entities(full_setup['spaces'][4],full_setup['floquets'][4],cfg,axes)
            evidence.compare('full',full_entities,default_entities,
                cell_info=full_setup['mesh'].topology.get_cell_permutation_info(),
                geometry_x=full_setup['mesh'].geometry.x,frozen_context=authority.snapshot_context(None))
            default_entities=None
            evidence.snapshot('full_after_default_release')
        else:
            full_entities=collect_y_orbit_entities(full_setup['spaces'][4],full_setup['floquets'][4],cfg,axes)
        layout=StreamedFullYLayout(full_entities,cfg)
        if shared_transforms:evidence.named['full.cell_dft']=layout.cell_dft
        if not np.array_equal(layout.independent,full_period_authority.load('independent_storage_rows')):
            raise ValueError('complete full original native row inventory differs')
        save_array('independent_storage_rows',layout.independent)
        save_mpc_inventory(original,layout,save_array)
        save_array('actual_interior_positions',fixture_interior_positions(full_setup['spaces'][4],layout))
        save_centered_port_inventory(original,layout,save_array,allocation_gate=allocation_gate)
        original_H=np.asarray([e.normalization_h for e in original['dtn_action'].carrier.entries])
        save_array('port_original_H',original_H)
        save_array('port_q_labels',np.asarray([int(m.n)%4 for m in inventory[0]],dtype=PETSc.IntType))
        save_array('port_factor_coordinate_scale',1/np.sqrt(original_H))
        local_cfg=build_two_cell_assembly_config(cfg)
        for b in (0,1):
            context=build_two_cell_quotient_context(cfg,local_cfg,inventory,twist_index=b)
            _gate(allocation_gate,'local40_actual_mesh_space_MPC_constructor',payload=16<<20,workspace=128<<20)
            setup=_build_same_mesh_levels(local_cfg,MPI.COMM_SELF,(4,),include_positive_coefficients=False,
                                         research_phase_override=context.phase_override)
            _actual_cells(full_setup,setup,event=event)
            bundle,receipt=authority.restore_bundle(setup,local_cfg,4,physical_cfg=cfg,quotient_context=context,global_mode_inventory=inventory)
            sector={'context':context,'setup':setup,'bundle':bundle,'condensed':None}
            sectors.append(sector)
            restorations.append(receipt)
            _gate(allocation_gate,'retained_local2_complete_maps',payload=64<<20,workspace=192<<20)
            local_axes=dict(zip(('x','y','z'),context.local_axes,strict=True))
            if shared_transforms:
                role=f'twist_{b}'
                local_entities=collect_y_orbit_entities(setup['spaces'][4],setup['floquets'][4],local_cfg,local_axes,transform_bank=bank)
                evidence.named.update(local_entities.named_backing_arrays(role))
                evidence.snapshot(role+'_after_collect')
                _gate(allocation_gate,'shared_local_default_complete_control',payload=2*7936*108*16,workspace=128<<20)
                default_entities=collect_y_orbit_entities(setup['spaces'][4],setup['floquets'][4],local_cfg,local_axes)
                evidence.compare(role,local_entities,default_entities,
                    cell_info=setup['mesh'].topology.get_cell_permutation_info(),
                    geometry_x=setup['mesh'].geometry.x,frozen_context=authority.snapshot_context(b))
                default_entities=None
                evidence.snapshot(role+'_layout_before_build')
                local_layout=build_y_orbit_layout(setup['spaces'][4],setup['floquets'][4],local_cfg,local_axes,
                    wrap_phase_y=context.tau,cell_phase_y=context.eta,entities=local_entities,transform_bank=bank)
                evidence.add_layout(role,local_layout,local_entities)
            else:
                local_layout=build_y_orbit_layout(setup['spaces'][4],setup['floquets'][4],local_cfg,local_axes,
                                                 wrap_phase_y=context.tau,cell_phase_y=context.eta)
                local_entities=collect_y_orbit_entities(setup['spaces'][4],setup['floquets'][4],local_cfg,local_axes)
            transport=TwoCellNativeTransport(full_entities,local_entities,twist_index=b,eta=context.eta,
                global_phase=cfg.floquet_phase_y,global_ky=cfg.ky,global_period_y=cfg.period_y)
            condensed=build_quotient_condensed(bundle,global_mode_inventory=inventory,
                global_mode_indices=context.original_mode_indices,qbase=b,allocation_gate=allocation_gate)
            sector['condensed']=condensed
            recovery_bindings.append(_recovery_identity_gate(condensed,setup,authority,b,event=event))
            trace=trace_layout_coordinates(local_layout,condensed.system,allocation_gate=allocation_gate)
            coords=TwoCellBranchCoordinates(trace,condensed,context,global_original_H=full_period_authority.load('port_original_H'),
                                            allocation_gate=allocation_gate,index_dtype=PETSc.IntType)
            sector.update(layout=local_layout,transport=transport,condensed=condensed,coordinates=coords)
            if shared_transforms:
                for member in ('data','indices','indptr'):evidence.named[f'twist_{b}_Qt.{member}']=getattr(coords.qt,member)
                for name,value in trace.items():
                    if isinstance(value,np.ndarray):evidence.named[f'twist_{b}_trace.{name}']=value
                    elif sparse.issparse(value):
                        for member in ('data','indices','indptr'):evidence.named[f'twist_{b}_trace.{name}.{member}']=getattr(value,member)
                for name in ('independent_original_rows','trace_original_rows','interior_original_rows'):
                    evidence.named[f'twist_{b}_recovery.{name}']=getattr(condensed,name)
                evidence.named[f'twist_{b}_ports.scale']=coords.scale
                for branch,ids in enumerate(coords.aliases):evidence.named[f'twist_{b}_ports.alias_{branch}']=ids
            provider=TwoCellBlockProvider(condensed,coords,allocation_gate=allocation_gate)
            for branch in (0,1):
                q=context.global_q_indices[branch];matrix=provider.block(branch,branch)
                old=authority.q_block(q);comparison=_compare(matrix,old,limit=1e-11,label=f'q_{q}_rebuilt_volume_recovery')
                _save_csr(save_array,f'q_{q}_S',matrix)
                item={'q':q,'shape':list(matrix.shape),'nnz':int(matrix.nnz),'CSR_sha256':sparse_hash(matrix),
                      'csr_prefix':f'q_{q}_S',
                      'relative_frobenius_difference':comparison['relative_Frobenius_error'],
                      'relative_max_difference':comparison['relative_max_error'],
                      'new_volume_recovery_identity':condensed.audit['condensation']['operator_cache_identity']}
                blocks.append(item);event('rebuilt_q_block_compared_before_any_factor',item)
                if not comparison['passed']:raise ValueError('restored ports/new volume q block differs before factor')
                matrices[q]=matrix
                if shared_transforms:
                    for member in ('data','indices','indptr'):evidence.named[f'q_{q}_S.{member}']=getattr(matrix,member)
            for name,value in (('independent_storage_rows',condensed.independent_original_rows),
                               ('trace_original_rows',condensed.trace_original_rows),('interior_original_rows',condensed.interior_original_rows),
                               ('slave_storage_rows',np.asarray(setup['floquets'][4].mpc.slaves))):save_array(f'twist_{b}_'+name,value)
            save_array(f'twist_{b}_original_H',np.asarray([e.normalization_h for e in bundle['dtn_action'].carrier.entries]))
        blocks.sort(key=lambda x:x['q'])
        if shared_transforms:
            bank.seal()
            evidence.snapshot('all_sectors_retained_before_factor')
            shared_receipt=evidence.result()
            event('shared_complete_equivalence_before_any_factor',shared_receipt)
        report={'schema':'task40extra.y-orbit-two-cell-quotient-probe.v1',
                'stage':stage,'prefactor_only':stage=='prefactor','degree':4,'physical_mode_count':532,'input_sha256':input_sha,
                'physical_generator_manifest_sha256':inventory[2],
                'restoration':restorations,'reformed_blocks':blocks,'layout':layout.audit,'factor_count':0,
                'recovery_identity_bindings':recovery_bindings,
                'official_results':False,'PDE_solved':False,'scope_flags':{'full_layout_entity_stream':True,
                'candidate_full_Ny_CSR_created':False,'candidate_full_F_created':False,'candidate_full_Q_created':False,
                'candidate_global_FE_square_matrix_created':False,'raw_port_reassembled':False,
                'raw_literal_qualification_rerun':False,'performance_or_target_capacity_claim':False}}
        if shared_transforms:
            report['shared_transforms']=True
            report['shared_transform_equivalence']=shared_receipt
        if stage=='prefactor':return {**report,'status':'QUOTIENT_PREFACTOR_COMPARE_PASS'}
        # All restore/rebuild/q comparison gates completed before any factor.
        for q in range(4):
            if sparse_hash(matrices[q])!=blocks[q]['CSR_sha256']:raise ValueError('bound fresh CSR changed before factor')
        factors=FourBranchFactors(matrices,allocation_gate=allocation_gate,event=event,save_array=save_array)
        inverse=CompleteTwoCellInverse(sectors,layout,factors,allocation_gate=allocation_gate)
        action0=FullOriginalAction(original['physical_action'],layout)
        manufactured={}
        for q in range(4):
            modal=np.zeros(15872,complex);j=np.arange(3968)
            modal[q*3968:(q+1)*3968]=np.cos(.31*j)+1j*np.sin(.47*j)
            # Inverse dual map Q^{-H}=R^{-H} F, including the moment transform.
            f=full_entities.transform(layout._dft(modal,adjoint=False),direction='dual_from_canonical')
            g=np.zeros(532,complex);ids=np.asarray([i for i,m in enumerate(inventory[0]) if int(m.n)%4==q])
            k=np.arange(len(ids));g[ids]=np.sqrt(original_H[ids])*(np.cos(.17*k)+1j*np.sin(.43*k))
            x,alpha=inverse.apply_augmented(f,g);label=f'aug_q_{q}'
            for name,value in (('FE_rhs',f),('port_rhs',g),('solution',x)):save_array(label+'_'+name,value)
            manufactured[label]=_original_augmented_packet(original,layout,f,g,x,alpha,label=label,save=save_array,event=event)
        rng=np.random.default_rng(SEED);generic=rng.standard_normal(15872)+1j*rng.standard_normal(15872)
        excitation=np.asarray(layout.modal_norms(generic,dual=True))
        if np.min(excitation)/np.linalg.norm(excitation)<LIMITS['excitation']:raise ValueError('generic RHS must excite all four q')
        _gate(allocation_gate,'full_original_incident_RHS_constructor',payload=4*17204*16,workspace=128<<20)
        physical_storage,physical_facts=build_physical_rhs(original)
        try:physical=physical_storage.array[layout.independent].copy()
        finally:physical_storage.destroy()
        box=tuple(v*(7/135) for v in (25,33.5,6.25,18.75,40,80))
        notch_cfg=replace(cfg,case_name='y_orbit_p4_algebra_notch',air_void_box_nm=box,geometry_identity=cfg.geometry_identity+'.notch')
        tags=_mark_cells(full_setup['mesh'],notch_cfg)
        changed=np.flatnonzero(tags.values!=full_setup['mesh_data'].cell_tags.values)
        if len(changed)!=2:raise ValueError('original full3D notch must alter exactly the same two cells')
        supported,support_facts=_notch_supported_rhs(full_setup['spaces'][4],layout,changed)
        loads={'generic':generic,'interior_only':interior_only_rhs(full_setup['spaces'][4],layout),
               'physical':physical,'notch_supported':supported}
        loads={k:loads[k] for k in SOURCES};regular={}
        for label,rhs in loads.items():
            if not np.array_equal(rhs,full_period_authority.load(label+'_rhs')):raise ValueError('same four full original RHS arrays required')
            save_array(label+'_rhs',rhs);x=inverse.apply_array(rhs);prefix='regular_'+label
            save_array(prefix+'_solution',x)
            packet=original_packet(original,layout,rhs,x,label=prefix,save=save_array,alpha=inverse.last_port_solution.copy())
            _check_original(packet)
            control=full_period_authority.load(prefix+'_solution')
            packet['saved_full_period_solution_difference']=float(np.linalg.norm(x-control)/max(np.linalg.norm(control),np.finfo(float).tiny))
            if packet['saved_full_period_solution_difference']>1e-9:raise ValueError('regular field differs from saved full-period control')
            packet['outputs']=recovered_field_and_modes(original,layout,x,physical=label=='physical',label=prefix,save=output_save)
            require_output_packet(packet['outputs'],label=prefix,event=event);regular[label]=packet
        mesh_data=SimpleNamespace(**vars(full_setup['mesh_data']));mesh_data.cell_tags=tags
        mesh_data.rectangular_air_void_audit=_rectangular_air_void_audit(full_setup['mesh'],tags,notch_cfg)
        _gate(allocation_gate,'notched_full_original_volume_action_constructor',payload=16<<20,workspace=128<<20)
        volume1=_build_split_volume_action(mesh_data,notch_cfg,full_setup['spaces'][4],full_setup['floquets'][4],jit_options={})
        notched=FullspacePhysicalAction(volume1,original['dtn_action'],owns_dtn=False)
        action1=FullOriginalAction(notched,layout)
        notch_bundle={**original,'cfg':notch_cfg,'volume_action':volume1,'physical_action':notched,'action':notched}
        samples=[]
        for q in range(4):
            modal=np.zeros(15872,complex);j=np.arange(3968);modal[q*3968:(q+1)*3968]=np.cos(.37*j)+1j*np.sin(.23*j)
            x=layout.primal_from_modal(modal);delta=layout.dual_to_modal(action1.apply(x)-action0.apply(x))
            total=float(np.linalg.norm(delta));delta[q*3968:(q+1)*3968]=0
            samples.append({'source_q':q,'delta_dual_norm':total,'off_q_delta_dual_norm':float(np.linalg.norm(delta))})
        coupling=float(np.sqrt(sum(v['off_q_delta_dual_norm']**2 for v in samples)/sum(v['delta_dual_norm']**2 for v in samples)))
        if not np.isfinite(coupling) or coupling<1e-8:raise ValueError('actual nonseparable notch must couple y blocks')
        notch={};defects={}
        for label,rhs in loads.items():
            defects[label]=sampled_right_pc_defect(action0,action1,inverse,rhs)
            _gate(allocation_gate,'original_full3D_FGMRES_Krylov_vectors',payload=96*15872*16,workspace=32<<20,
                  restart=32,max_iterations=128,all_full_original_FE_rows=15872)
            x,krylov=solve_notched_fgmres(action1,inverse,rhs);prefix='notch_'+label
            save_array(prefix+'_solution',x)
            packet=original_packet(notch_bundle,layout,rhs,x,label=prefix,save=save_array)
            _check_original(packet);packet.update(krylov)
            control=full_period_authority.load(prefix+'_solution')
            packet['saved_full_period_solution_difference']=float(np.linalg.norm(x-control)/max(np.linalg.norm(control),np.finfo(float).tiny))
            if packet['reason']<=0 or packet['saved_full_period_solution_difference']>1e-9:raise ValueError('notch original solve/control failed')
            norms=np.asarray(layout.modal_norms(x,dual=False));packet['nonzero_q_primal_relative']=float(np.linalg.norm(norms[1:])/np.linalg.norm(norms))
            if label=='physical' and packet['nonzero_q_primal_relative']<=1e-12:raise ValueError('physical notch must produce nonzero transverse q content')
            packet['outputs']=recovered_field_and_modes(notch_bundle,layout,x,physical=label=='physical',label=prefix,save=output_save)
            require_output_packet(packet['outputs'],label=prefix,event=event);notch[label]=packet
        if shared_transforms:evidence.snapshot('apply_recovery_complete')
        return {**report,'status':'QUOTIENT_FULL3D_INVERSE_PROBE_PASS','factor_count':4,'PDE_solved':True,
                'factor':factors.audit,'augmented_controls':[{'q':q,**manufactured[f'aug_q_{q}']} for q in range(4)],
                'regular_sources':regular,'notched_sources':notch,'physical_rhs_facts':physical_facts,
                'changed_cells':changed.tolist(),'notch_supported_RHS':support_facts,
                'sampled_notch_q_coupling':samples,'sampled_notch_off_q_delta_relative':coupling,
                'sampled_right_PC_defect':defects,'sampled_delta_is_operator_norm':False,
                'PC_defect_is_norm_bound':False,
                'all_full_recovery_calls':inverse.calls,'all_q_factor_calls':factors.calls,
                'target_geometry_accuracy':False,'no_2TB_or_48h_claim':True}
    finally:
        if action1 is not None:action1.close()
        if action0 is not None:action0.close()
        if factors is not None:factors.destroy()
        for sector in reversed(sectors):
            if sector.get('condensed') is not None:sector['condensed'].destroy()
            destroy_same_mesh_physical_action(sector['bundle'])
        if notched is not None:notched.destroy()
        if original is not None:destroy_same_mesh_physical_action(original)
        if evidence is not None:
            # Clear named borrower references after the entire solve/recovery stage.
            # Payload accounting does not assert allocator or RSS reclamation.
            anchors=evidence.owner_weak_anchors(default_entities.named_backing_arrays("cleanup_default") if default_entities is not None else None)
            evidence.named.clear()
            for retained_sector in sectors:retained_sector.clear()
            sectors.clear();matrices.clear()
            sector=retained_sector=None
            layout=full_entities=local_entities=local_layout=transport=coords=trace=inverse=provider=matrix=old=setup=bundle=value=condensed=ids=default_entities=None
            factors=action0=action1=None
            active_error=sys.exc_info()[0]
            if active_error is None:evidence.cleanup(anchors)
            else:evidence.failure_cleanup(anchors,active_error.__name__)
