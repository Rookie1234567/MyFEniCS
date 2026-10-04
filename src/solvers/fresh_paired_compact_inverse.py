"""Fresh same80 paired live compact all-q inverse; validation reference only."""
from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path
import hashlib,json
import numpy as np
from scipy import sparse
from .task40extra_y_orbit_reference import pilot_config,collect_y_orbit_entities,build_y_orbit_layout,FullOriginalAction,solve_notched_fgmres,SEED,LIMITS
from .y_orbit_two_cell_inverse import StreamedFullYLayout,FourBranchFactors,CompleteTwoCellInverse
from .y_orbit_two_cell_transport import TwoCellNativeTransport
from .y_orbit_two_cell_block_audit import TwoCellBranchCoordinates,TwoCellBlockProvider
from .y_orbit_sparse_reference import _gate,sparse_hash,csr_audit,sampled_right_pc_defect
from .y_orbit_two_cell_audit import _compare,_save_csr,_actual_cells,_column_bridge,_complete_recovery_witness
from .y_orbit_two_cell_inverse_probe import _original_augmented_packet,_check_original


Q_SHAPES=(1884,1960,1960,1960)


def require_paired_prefactor_inventory(blocks,cross,sector_indices):
    """Require every exact diagonal, cross direction and physical alias before LU."""
    if len(blocks)!=4 or [x.get('q') for x in blocks]!=list(range(4)):
        raise ValueError('all four ordered diagonal controls are required')
    for q,item in enumerate(blocks):
        check=item.get('comparison',{})
        if item.get('shape')!=[Q_SHAPES[q],Q_SHAPES[q]] or check.get('passed') is not True:
            raise ValueError('complete diagonal/control gate required')
        for key in ('relative_Frobenius_error','relative_max_error'):
            value=check.get(key)
            if not isinstance(value,(int,float)) or not np.isfinite(value) or value>1e-11 or value<0:
                raise ValueError('diagonal numerical equivalence must pass unchanged limit')
    if len(cross)!=4 or {(x.get('p'),x.get('q')) for x in cross}!={(0,2),(2,0),(1,3),(3,1)}:
        raise ValueError('both cross directions in both twists required')
    for item in cross:
        norm=item.get('absolute_Frobenius_norm');diag=item.get('diagonal_norms',())
        if len(diag)!=2 or any(not np.isfinite(x) or x<=0 for x in diag) or norm is None or not np.isfinite(norm) or norm<0:
            raise ValueError('positive actual diagonal scales required')
        if max(norm/diag[0],norm/diag[1])>1e-11 or item.get('passed') is not True:
            raise ValueError('cross leakage must pass both diagonal scales')
    if (len(sector_indices)!=2 or tuple(map(len,sector_indices))!=(228,304)
            or sorted(i for ids in sector_indices for i in ids)!=list(range(532))):
        raise ValueError('exact disjoint228/304 physical532 inventory required')


def compact_cache_numeric_identity(condensed):
    """Hash immutable cache ingredients without creating port-square storage."""
    from .fresh_c1_p6_component import _sha
    if condensed.action._H_p is not None or condensed.action._Hhat is not None:
        raise ValueError('compact cache must not retain port squares')
    result=[]
    for cell in condensed.action._cells:
        item=[]
        for name in ('original_interiors','original_trace','active_ids','S_V','Bhat','Dhat','recovery','trace_from_interior','ports','Di','XiB'):
            value=getattr(cell,name)
            item.append((name,None if value is None else _sha(value)))
        item.extend((name,_sha(value)) for name,value in
            (('expansion_data',cell.expansion.data),('expansion_indices',cell.expansion.indices),('expansion_indptr',cell.expansion.indptr),
             ('LU',cell.interior_lu[0]),('pivots',cell.interior_lu[1])))
        result.append(item)
    for name in ('_direct_B_active','_direct_D_active'):
        result.append((name,[(int(index),[_sha(a) for a in pair]) for index,pair in sorted(getattr(condensed.action,name).items())]))
    result.append(('original_H',[_sha(a) for a in condensed.action._original_port_block.numeric_arrays]))
    return hashlib.sha256(json.dumps(result,separators=(',',':')).encode()).hexdigest()


def _save_local_compact_witness(sector, *, snapshot, root, save_array, gate):
    """Bind both live compact caches to independently replayable local algebra."""
    from petsc4py import PETSc
    from .original_port_blocks import DiagonalOriginalPortBlock,CachedPortCorrection
    from .fullspace_dtn_action import _jsonable
    b=sector['context'].twist_index;bundle=sector['bundle'];condensed=sector['condensed'];coords=sector['coordinates']
    role=f'compact_twist_{b}'
    def arr(name,value):return snapshot.array(role+'/'+name,value)
    def csr(name,matrix):return {'shape':list(matrix.shape),**{k:arr(name+'/'+k,getattr(matrix,k)) for k in ('data','indices','indptr')}}
    part={name:arr('partition/'+name,value) for name,value in
        (('independent',condensed.independent_original_rows),('trace',condensed.trace_original_rows),
         ('interior',condensed.interior_original_rows),('slaves',np.asarray(sector['setup']['floquets'][4].mpc.slaves)))}
    state=np.load(root/f'arrays/twist_{b}_complete_recovery_recovered.npy',allow_pickle=False,mmap_mode='r')
    alpha=np.load(root/f'arrays/twist_{b}_complete_recovery_alpha.npy',allow_pickle=False,mmap_mode='r')
    rhs=np.load(root/f'arrays/twist_{b}_complete_recovery_FE_rhs.npy',allow_pickle=False,mmap_mode='r')
    g=np.load(root/f'arrays/twist_{b}_complete_recovery_port_rhs.npy',allow_pickle=False,mmap_mode='r')
    _gate(gate,'local_original_live_FFCx_witness',payload=6*8940*16,workspace=16<<20)
    vec=PETSc.Vec().createSeq(8940,comm=PETSc.COMM_SELF)
    try:
        vec.array[:]=state;volume=bundle['volume_action'].apply(vec).array.copy()
    finally:vec.destroy()
    entries=bundle['dtn_action'].carrier.entries;coupling=np.zeros(8940,complex);projection=np.empty(len(entries),complex);h=np.empty(len(entries))
    records=[]
    for i,e in enumerate(entries):
        np.add.at(coupling,e.coupling_rows,e.coupling_values*alpha[i])
        projection[i]=np.dot(e.projection_values,state[e.projection_rows]);h[i]=e.normalization_h
        records.append({k:arr(f'carrier/{i}/{k}',v) for k,v in
            (('C_rows',e.coupling_rows),('C_values',e.coupling_values),('D_rows',e.projection_rows),('D_values',e.projection_values))})
    fe=rhs-volume-coupling;port=g+projection-h*alpha
    scales=(float(np.linalg.norm(rhs)),float(np.linalg.norm(g)))
    errors=(float(np.linalg.norm(fe)),float(np.linalg.norm(port)))
    if any(s<=0 or not np.isfinite(e+s) or e/s>1e-10 for e,s in zip(errors,scales,strict=True)):
        raise ValueError('complete local original FE/nonzero-port RHS witness fails')
    witness={k:arr('original_witness/'+k,v) for k,v in
        (('volume_action',volume),('coupling_action',coupling),('projection',projection),('H',h),('FE_residual',fe),('port_residual',port))}
    recipes=[]
    for i,(row,col,value,label) in enumerate(condensed.iter_contributions(allocation_gate=gate)):
        item={'label':label,'rows':arr(f'contributions/{i}/rows',row),'cols':arr(f'contributions/{i}/cols',col)}
        if isinstance(value,DiagonalOriginalPortBlock):item.update(kind='diagonal',values=arr(f'contributions/{i}/H',value.diagonal))
        elif isinstance(value,CachedPortCorrection):item.update(kind='correction',Di=arr(f'contributions/{i}/Di',value.Di),XiB=arr(f'contributions/{i}/XiB',value.XiB))
        else:item.update(kind='dense',values=arr(f'contributions/{i}/values',value))
        recipes.append(item)
    cells=[]
    for i,cell in enumerate(condensed.action._cells):
        item={name:arr(f'cells/{i}/{name}',getattr(cell,name)) for name in
            ('original_interiors','original_trace','active_ids','recovery','trace_from_interior','ports','Di','XiB') if getattr(cell,name) is not None}
        item['expansion']=csr(f'cells/{i}/expansion',cell.expansion)
        item['LU']=arr(f'cells/{i}/LU',cell.interior_lu[0]);item['pivots']=arr(f'cells/{i}/pivots',cell.interior_lu[1]);cells.append(item)
    if len(cells)!=40 or condensed.action._H_p is not None or condensed.action._Hhat is not None:
        raise ValueError('all40 live compact cache owners required without H/Hhat')
    return {'twist':b,'q_indices':list(sector['context'].global_q_indices),'port_count':len(entries),
            'partition':part,'qmaps':[csr(f'qmap{j}',coords.q_map(j)) for j in (0,1)],'recipes':recipes,'cells':cells,
            'carrier_records':records,'original_witness':witness,'condensation':_jsonable(condensed.audit),
            'original_witness_scope':'saved live FFCx volume action; checker reconstructs carrier/residual, not FFCx',
            'resident_dense_H_bytes':0,'original_H_diagonal_bytes':int(condensed.action.buffer_inventory['resident_H_p_bytes']),'resident_Hhat_bytes':0}


def run_paired_compact_inverse(input_path,*,full_period_authority,event,save_array,allocation_gate,run_directory,stage):
    from mpi4py import MPI
    from petsc4py import PETSc
    from .fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from .fullspace_same_mesh_hcurl_pmg_physical import _build_split_volume_action,build_physical_rhs,destroy_same_mesh_physical_action,build_same_mesh_physical_action
    from .fullspace_physical_action import FullspacePhysicalAction
    from .fullspace_dtn_action import build_dynamic_mode_inventory,_jsonable
    from .y_orbit_quotient_context import build_two_cell_assembly_config,build_two_cell_quotient_context
    from .y_orbit_quotient_condensed import build_quotient_condensed
    from .y_orbit_condensed_adapter import trace_layout_coordinates
    from .y_orbit_centered_evidence import original_packet,recovered_field_and_modes,require_output_packet,interior_only_rhs,fixture_interior_positions,save_mpc_inventory,save_centered_port_inventory,compare_mode_evidence,SOURCES
    from .y_orbit_sparse_probe import _notch_supported_rhs
    from .y_orbit_quotient_raw_qualification import qualify_quotient_raw_bundle
    from .y_orbit_raw_packet_spool import RawModeSpool
    from .y_orbit_live_boundary_contract import qualify_live_identity,require_live_carrier_unchanged
    from .original_port_blocks import DiagonalOriginalPortBlock
    from .retained_port_block_layout import RESEARCH_PORT_LAYOUT
    from .dtn_boundary_plane_qualification import carrier_numeric_identity
    from .y_orbit_transform_bank import RunLocalTransformBank
    from .fresh_c1_p6_component import _Snapshot
    from src.geometry.mesh_builder_3d import _mark_cells,_rectangular_air_void_audit
    if stage not in ('prefactor','solve'):raise ValueError('explicit bounded paired stage required')
    root=Path(run_directory)
    def load_output(name):
        _gate(allocation_gate,'candidate_output_comparison_readonly',workspace=64<<10)
        return np.load(root/'arrays'/(name+'.npy'),allow_pickle=False,mmap_mode='r')
    def output_comparison(prefix):
        checks=compare_mode_evidence(load_output,full_period_authority.load,prefix)
        event('full532_output_against_fresh_C1b',{'prefix':prefix,'checks':checks})
        if not all(c['passed'] for c in checks.values()):raise ValueError('required full532 mode outputs differ from fresh C1b')
        return checks
    cfg,axes,input_sha=pilot_config(input_path,azimuth_deg=5.)
    cfg=replace(cfg,nedelec_degree=4,visualization_degree=4,case_name='y_orbit_p4_algebra_regular')
    if input_sha!=full_period_authority.report['input_sha256'] or {k:list(v) for k,v in axes.items()}!=full_period_authority.report['axes_nm']:
        raise ValueError('same80 actual full fixture differs from current C1b')
    modes,rows,sha=build_dynamic_mode_inventory(cfg);inventory=(tuple(modes),tuple(rows),sha)
    keys=[[str(m.side),int(m.m),int(m.n),str(m.polarization)] for m in modes]
    if keys!=full_period_authority.report['mode_keys'] or sha!=full_period_authority.report['mode_manifest_sha256']:
        raise ValueError('all532 physical mode inventory differs')
    bank=RunLocalTransformBank(mapping_limit=LIMITS['mapping'])
    snapshot=_Snapshot(save_array,allocation_gate,event,512<<20);local_snapshots=[]
    _gate(allocation_gate,'paired_full80_original_setup',workspace=128<<20)
    full_setup=_build_same_mesh_levels(cfg,MPI.COMM_SELF,(4,),include_positive_coefficients=False)
    original=notched=None;action0=action1=None;factors=None;sectors=[];matrices={};blocks=[];cross=[];raw_receipts=[];recovery=[]
    def output_save(name,value):
        if isinstance(value,(list,tuple)):
            if not name.endswith('_direct_plane_outgoing_power_diagnostic') or len(value)!=532:raise TypeError('unknown output list')
            _gate(allocation_gate,'known_mode_power_conversion',payload=532*8,workspace=1<<20)
            value=np.asarray(value,dtype=np.float64)
        return save_array(name,value)
    try:
        # Full original action is matrix-free and supplies final equation gates.
        # It is not a candidate full-Ny reference S/F/Q.
        _gate(allocation_gate,'fresh_full_original_primary_carrier',payload=64<<20,workspace=256<<20)
        original=build_same_mesh_physical_action(full_setup,cfg,4,dtn_phase_gauge='boundary_plane')
        global_proof=qualify_live_identity(original,record_path=root/'global_live_component_receipt.json',
            allocation_gate=allocation_gate,event=event,fresh_fixture_c1=True)
        _gate(allocation_gate,'full_native_shared_entity_records',payload=2*15872*108*16,workspace=128<<20)
        full_entities=collect_y_orbit_entities(full_setup['spaces'][4],full_setup['floquets'][4],cfg,axes,transform_bank=bank)
        layout=StreamedFullYLayout(full_entities,cfg)
        if not np.array_equal(layout.independent,full_period_authority.load('independent_storage_rows')):raise ValueError('fullnative independent rows differ')
        save_array('independent_storage_rows',layout.independent);save_mpc_inventory(original,layout,save_array)
        save_array('actual_interior_positions',fixture_interior_positions(full_setup['spaces'][4],layout))
        save_centered_port_inventory(original,layout,save_array,allocation_gate=allocation_gate)
        original_H=np.asarray([e.normalization_h for e in original['dtn_action'].carrier.entries])
        if not np.array_equal(original_H,full_period_authority.load('port_original_H')):raise ValueError('global original H changed')
        save_array('port_original_H',original_H);save_array('port_q_labels',np.asarray([int(m.n)%4 for m in inventory[0]],dtype=PETSc.IntType));save_array('port_factor_coordinate_scale',1/np.sqrt(original_H))
        local_cfg=build_two_cell_assembly_config(cfg);old_Q=full_period_authority.load_csr('full_Q',(15872,15872))
        for b in (0,1):
            context=build_two_cell_quotient_context(cfg,local_cfg,inventory,twist_index=b)
            _gate(allocation_gate,'paired_local40_setup',payload=16<<20,workspace=128<<20)
            setup=_build_same_mesh_levels(local_cfg,MPI.COMM_SELF,(4,),include_positive_coefficients=False,research_phase_override=context.phase_override)
            metric=_actual_cells(full_setup,setup,event=event)
            spool=RawModeSpool(root/f'raw_twist_{b}',save_array=save_array,allocation_gate=allocation_gate,root_directory=root)
            bundle=build_same_mesh_physical_action(setup,local_cfg,4,physical_cfg=cfg,mode_inventory=inventory,
                quotient_context=context,dtn_phase_gauge='boundary_plane',raw_mode_observer=spool.observe)
            sector={'context':context,'setup':setup,'bundle':bundle,'condensed':None};sectors.append(sector)
            local_axes=dict(zip(('x','y','z'),context.local_axes,strict=True))
            _gate(allocation_gate,'paired_local_shared_maps',payload=64<<20,workspace=192<<20)
            entities=collect_y_orbit_entities(setup['spaces'][4],setup['floquets'][4],local_cfg,local_axes,transform_bank=bank)
            local_layout=build_y_orbit_layout(setup['spaces'][4],setup['floquets'][4],local_cfg,local_axes,
                wrap_phase_y=context.tau,cell_phase_y=context.eta,entities=entities,transform_bank=bank)
            transport=TwoCellNativeTransport(full_entities,entities,twist_index=b,eta=context.eta,
                global_phase=cfg.floquet_phase_y,global_ky=cfg.ky,global_period_y=cfg.period_y)
            maps=_column_bridge(transport,local_layout,old_Q,save_array=save_array,gate=allocation_gate,event=event)
            raw_path=root/f'raw_twist_{b}/raw_port_receipt.json'
            _gate(allocation_gate,'paired_local_literal_raw_oracle',payload=16<<20,workspace=128<<20)
            raw=qualify_quotient_raw_bundle(bundle,raw_mode_packets=spool.packets(),record_path=raw_path,
                expected_physical_manifest=sha,expected_global_ordered_keys=[(i,*k) for i,k in enumerate(keys)])
            raw_receipts.append({'b':b,'path':str(raw_path.relative_to(root)),'sha256':hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                'sector_original_indices':list(context.original_mode_indices),'theta':_jsonable(context.theta),'eta':_jsonable(context.eta),'tau':_jsonable(context.tau)})
            condensed=build_quotient_condensed(bundle,global_mode_inventory=inventory,global_mode_indices=context.original_mode_indices,
                qbase=b,allocation_gate=allocation_gate,port_block_layout=RESEARCH_PORT_LAYOUT,
                original_port_block=DiagonalOriginalPortBlock.from_carrier(bundle['dtn_action'].carrier.entries))
            sector['condensed']=condensed;sector['raw_carrier_identity']=raw['carrier_identity_after']
            recovery.append(_complete_recovery_witness(condensed,local_layout,save_array=save_array,gate=allocation_gate,event=event))
            trace=trace_layout_coordinates(local_layout,condensed.system,allocation_gate=allocation_gate)
            coords=TwoCellBranchCoordinates(trace,condensed,context,global_original_H=original_H,allocation_gate=allocation_gate,index_dtype=PETSc.IntType)
            sector.update(layout=local_layout,transport=transport,coordinates=coords)
            provider=TwoCellBlockProvider(condensed,coords,allocation_gate=allocation_gate,
                compact_projection_max_owned_bytes=128<<20,compact_projection_tile_width=128)
            for branch in (0,1):
                q=context.global_q_indices[branch];matrix=provider.block(branch,branch);csr_audit(matrix,petsc_index_dtype=PETSc.IntType)
                control=full_period_authority.q_block(q)
                compare_payload=sum(a.nbytes for m in (matrix,control) for a in (m.data,m.indices,m.indptr))
                _gate(allocation_gate,'paired_diagonal_difference_and_norm',workspace=3*compare_payload+(1<<20))
                comparison=_compare(matrix,control,limit=1e-11,label=f'paired_q{q}_fresh_C1b')
                _save_csr(save_array,f'q_{q}_S',matrix)
                item={'q':q,'shape':list(matrix.shape),'nnz':int(matrix.nnz),'CSR_sha256':sparse_hash(matrix),
                    'csr_prefix':f'q_{q}_S','comparison':comparison,'physical_alias_count':len(coords.aliases[branch])}
                blocks.append(item);event('paired_diagonal_checked_before_factor',item)
                if not comparison['passed']:raise ValueError('compact diagonal mismatch before any factor')
                matrices[q]=matrix;del control
            for p,q in ((0,1),(1,0)):
                gp,gq=context.global_q_indices[p],context.global_q_indices[q];matrix=provider.block(p,q)
                _gate(allocation_gate,'paired_cross_and_diagonal_norm_workspaces',workspace=3*sum(a.nbytes for a in (matrix.data,matrix.indices,matrix.indptr))+(32<<20))
                norm=float(sparse.linalg.norm(matrix));diag=[float(sparse.linalg.norm(matrices[g])) for g in (gp,gq)]
                maximum=float(np.max(np.abs(matrix.data),initial=0))
                if min(diag)<=0 or not np.isfinite(norm+maximum):raise ValueError('invalid cross/diagonal norms')
                relative=max(norm/diag[0],norm/diag[1]);item={'p':gp,'q':gq,'absolute_Frobenius_norm':norm,'absolute_maximum':maximum,
                    'diagonal_norms':diag,'relative_to_both_diagonals':relative,'passed':relative<=1e-11,'csr_prefix':f'cross_{gp}_{gq}'}
                _save_csr(save_array,item['csr_prefix'],matrix);cross.append(item);event('paired_cross_checked_before_factor',item)
                if not item['passed']:raise ValueError('compact cross leakage before any factor')
                del matrix
            for name,value in (('independent_storage_rows',condensed.independent_original_rows),('trace_original_rows',condensed.trace_original_rows),
                ('interior_original_rows',condensed.interior_original_rows),('slave_storage_rows',np.asarray(setup['floquets'][4].mpc.slaves))):save_array(f'twist_{b}_'+name,value)
            save_array(f'twist_{b}_original_H',np.asarray([e.normalization_h for e in bundle['dtn_action'].carrier.entries]))
            if condensed.action._H_p is not None or condensed.action._Hhat is not None:raise ValueError('compact owner retains H/Hhat')
            sector['cache_owner_token']=(id(condensed.action),tuple(id(cell) for cell in condensed.action._cells))
            local_snapshots.append(_save_local_compact_witness(sector,snapshot=snapshot,root=root,save_array=save_array,gate=allocation_gate))
        del old_Q
        blocks.sort(key=lambda x:x['q']);bank.seal()
        shared_before=bank.receipt(stage='paired_before_factors')
        if sorted(matrices)!=list(range(4)) or len(cross)!=4 or sorted(i for s in sectors for i in s['context'].original_mode_indices)!=list(range(532)):
            raise ValueError('complete allq/532 partition absent before factors')
        require_paired_prefactor_inventory(blocks,cross,[list(s['context'].original_mode_indices) for s in sectors])
        cache_digests=[compact_cache_numeric_identity(s['condensed']) for s in sectors]
        event('paired_live_cache_numeric_digests_before_factor',{'sha256':cache_digests})
        require_live_carrier_unchanged(original,global_proof,event=event,boundary='before_all4_factors',expected_carrier=original['dtn_action'].carrier)
        report={'schema':'task40extra.fresh-paired-live-compact-inverse.v1','stage':stage,'prefactor_only':stage=='prefactor',
            'degree':4,'physical_mode_count':532,'input_sha256':input_sha,'global_mode_keys':keys,'physical_generator_manifest_sha256':sha,
            'fresh_global_identity':global_proof,'raw_sector_receipts':raw_receipts,'reformed_blocks':blocks,'cross_blocks':cross,
            'layout':layout.audit,'factor_count':0,'factor_count_scope':'global/q only; inherited cell-interior LU used',
            'shared_transform_owner_before':shared_before,'live_cache_numeric_sha256_before':cache_digests,'live_cache_recipe_before':[_jsonable(s['condensed'].action.cache_identity) for s in sectors],'recovery_witnesses':recovery,'local_compact_snapshots':local_snapshots,'snapshot':snapshot.identity(),'authority':full_period_authority.identity(),'candidate_full_Ny_CSR_created':False,
            'candidate_full_F_created':False,'candidate_full_Q_created':False,'resident_Hhat_bytes':0,
            'actual_cache_retained_numeric_bytes':[s['condensed'].audit['condensation'].get('retained_numeric_cache_bytes') for s in sectors],
            'same80_scaled_fixture':True,'all_prefactor_gates_before_factors':True,'no_2TB_or_48h_claim':True}
        if stage=='prefactor':return {**report,'status':'FRESH_PAIRED_ALLQ_PREFACTOR_PASS'}
        for q in range(4):
            if sparse_hash(matrices[q])!=blocks[q]['CSR_sha256']:raise ValueError('bound fresh CSR changed before factor')
        cache_tokens=[(id(s['condensed'].action),tuple(id(c) for c in s['condensed'].action._cells)) for s in sectors]
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
            require_output_packet(packet['outputs'],label=prefix,event=event);packet['same_C1b_mode_comparisons']=output_comparison(prefix);regular[label]=packet
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
            require_output_packet(packet['outputs'],label=prefix,event=event);packet['same_C1b_mode_comparisons']=output_comparison(prefix);notch[label]=packet
        actual_tokens=[(id(s['condensed'].action),tuple(id(c) for c in s['condensed'].action._cells)) for s in sectors]
        for s in sectors:
            if carrier_numeric_identity(s['bundle']['dtn_action'].carrier)!=s['raw_carrier_identity']:
                raise ValueError('live local carrier changed during original solves')
        cache_after=[compact_cache_numeric_identity(s['condensed']) for s in sectors]
        if cache_after!=cache_digests:raise ValueError('numeric local caches changed during original full solves')
        if actual_tokens!=cache_tokens or len(factors.factors)!=4:raise ValueError('cache/factor owner changed during original solves')
        require_live_carrier_unchanged(original,global_proof,event=event,boundary='after_all_original_solves',expected_carrier=original['dtn_action'].carrier)
        return {**report,'status':'FRESH_PAIRED_COMPACT_FULL3D_INVERSE_PASS','factor_count':4,'PDE_solved':True,
                'factor':factors.audit,'augmented_controls':[{'q':q,**manufactured[f'aug_q_{q}']} for q in range(4)],
                'regular_sources':regular,'notched_sources':notch,'physical_rhs_facts':physical_facts,
                'changed_cells':changed.tolist(),'notch_supported_RHS':support_facts,
                'sampled_notch_q_coupling':samples,'sampled_notch_off_q_delta_relative':coupling,
                'sampled_right_PC_defect':defects,'sampled_delta_is_operator_norm':False,
                'PC_defect_is_norm_bound':False,
                'all_full_recovery_calls':inverse.calls,'all_q_factor_calls':factors.calls,
                'target_geometry_accuracy':False,'no_2TB_or_48h_claim':True,'shared_transform_owner_after':bank.receipt(stage='paired_after_all_original_solves'),'same_live_cache_owners_through_apply':True,'cache_rebuilt_per_PC_apply':False,'live_cache_numeric_sha256_after':cache_after,'live_cache_recipe_after':[_jsonable(s['condensed'].action.cache_identity) for s in sectors]}
    finally:
        if action1 is not None:action1.close()
        if action0 is not None:action0.close()
        if factors is not None:factors.destroy()
        for sector in reversed(sectors):
            if sector.get('condensed') is not None:sector['condensed'].destroy()
            destroy_same_mesh_physical_action(sector['bundle'])
        if notched is not None:notched.destroy()
        if original is not None:destroy_same_mesh_physical_action(original)
        sectors.clear()
        full_entities=local_layout=entities=transport=layout=coords=provider=inverse=None
        bank.close()
