"""Selected b0/q0 actual compact quotient witness; no q/global factors."""
from dataclasses import replace
from pathlib import Path
import json
import numpy as np
from scipy import sparse

from .fresh_c1_p6_component import _Snapshot
from .y_orbit_sparse_reference import _gate, csr_audit
from .y_orbit_two_cell_audit import _actual_cells, _column_bridge, _complete_recovery_witness, _compare, _sha

STATUS='FRESH_C1c_B0_Q0_COMPACT_PREFACTOR_WORKER_PASS'


def save_csr(snapshot,prefix,matrix):
    return {'shape':list(matrix.shape),**{key:snapshot.array(prefix+'/'+key,getattr(matrix,key))
                                         for key in ('data','indices','indptr')}}


def run_prefactor(input_path,*,authority,event,save_array,allocation_gate,run_directory):
    from mpi4py import MPI
    from petsc4py import PETSc
    from .task40extra_y_orbit_reference import pilot_config,collect_y_orbit_entities,build_y_orbit_layout
    from .fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from .fullspace_same_mesh_hcurl_pmg_physical import build_same_mesh_physical_action,destroy_same_mesh_physical_action
    from .fullspace_dtn_action import build_dynamic_mode_inventory,_jsonable
    from .y_orbit_quotient_context import build_two_cell_assembly_config,build_two_cell_quotient_context
    from .y_orbit_quotient_raw_qualification import qualify_quotient_raw_bundle
    from .y_orbit_raw_packet_spool import RawModeSpool
    from .y_orbit_quotient_condensed import build_quotient_condensed
    from .y_orbit_two_cell_transport import TwoCellNativeTransport
    from .y_orbit_two_cell_block_audit import TwoCellBranchCoordinates,TwoCellBlockProvider
    from .y_orbit_condensed_adapter import trace_layout_coordinates
    from .original_port_blocks import DiagonalOriginalPortBlock,CachedPortCorrection
    from .retained_port_block_layout import RESEARCH_PORT_LAYOUT
    root=Path(run_directory);snapshot=_Snapshot(save_array,allocation_gate,event,512*1024**2)
    cfg,axes,input_sha=pilot_config(input_path,azimuth_deg=5.)
    cfg=replace(cfg,nedelec_degree=4,visualization_degree=4,case_name='y_orbit_p4_algebra_regular')
    if input_sha!=authority.report['input_sha256'] or {k:list(v) for k,v in axes.items()}!=authority.report['axes_nm']:
        raise ValueError('fresh reference full fixture differs')
    modes,rows,sha=build_dynamic_mode_inventory(cfg);inventory=(tuple(modes),tuple(rows),sha)
    keys=[[str(m.side),int(m.m),int(m.n),str(m.polarization)] for m in modes]
    if sha!=authority.report['mode_manifest_sha256'] or keys!=authority.report['mode_keys']:
        raise ValueError('complete physical generator differs')
    local=None;condensed=None
    try:
        _gate(allocation_gate,'full80_ENTITY_SETUP_ONLY',workspace=128<<20,global_action_created=False)
        full=_build_same_mesh_levels(cfg,MPI.COMM_SELF,(4,),include_positive_coefficients=False)
        full_entities=collect_y_orbit_entities(full['spaces'][4],full['floquets'][4],cfg,axes)
        if not np.array_equal(full_entities.independent,authority.load('independent_storage_rows')):
            raise ValueError('actual full native rows differ from saved reference')
        local_cfg=build_two_cell_assembly_config(cfg)
        context=build_two_cell_quotient_context(cfg,local_cfg,inventory,twist_index=0)
        _gate(allocation_gate,'local40_MPC_and_maps',payload=64<<20,workspace=256<<20)
        setup=_build_same_mesh_levels(local_cfg,MPI.COMM_SELF,(4,),include_positive_coefficients=False,
                                      research_phase_override=context.phase_override)
        metric=_actual_cells(full,setup,event=event)
        spool=RawModeSpool(root/'raw_twist_0',save_array=save_array,allocation_gate=allocation_gate,root_directory=root)
        local=build_same_mesh_physical_action(setup,local_cfg,4,mode_inventory=inventory,physical_cfg=cfg,
            quotient_context=context,dtn_phase_gauge='boundary_plane',raw_mode_observer=spool.observe)
        local_axes=dict(zip(('x','y','z'),context.local_axes,strict=True))
        layout=build_y_orbit_layout(setup['spaces'][4],setup['floquets'][4],local_cfg,local_axes,
                                   wrap_phase_y=context.tau,cell_phase_y=context.eta)
        entities=collect_y_orbit_entities(setup['spaces'][4],setup['floquets'][4],local_cfg,local_axes)
        transport=TwoCellNativeTransport(full_entities,entities,twist_index=0,eta=context.eta,
            global_phase=cfg.floquet_phase_y,global_ky=cfg.ky,global_period_y=cfg.period_y)
        maps=_column_bridge(transport,layout,authority.load_csr('full_Q',(15872,15872)),
                            save_array=save_array,gate=allocation_gate,event=event)
        raw_path=root/'raw_twist_0/raw_port_receipt.json'
        _gate(allocation_gate,'local_primary_literal_raw_oracle',payload=16<<20,workspace=128<<20)
        raw=qualify_quotient_raw_bundle(local,raw_mode_packets=spool.packets(),record_path=raw_path,
            expected_physical_manifest=sha,expected_global_ordered_keys=[(i,*k) for i,k in enumerate(keys)])
        event('fresh_local_raw_literal_PASS',{'status':raw['status'],'modes':228})
        original=DiagonalOriginalPortBlock.from_carrier(local['dtn_action'].carrier.entries)
        condensed=build_quotient_condensed(local,global_mode_inventory=inventory,
            global_mode_indices=context.original_mode_indices,qbase=0,allocation_gate=allocation_gate,
            port_block_layout=RESEARCH_PORT_LAYOUT,original_port_block=original)
        partition={name:snapshot.array('partition/'+name,value) for name,value in
            (('independent',condensed.independent_original_rows),('trace',condensed.trace_original_rows),
             ('interior',condensed.interior_original_rows),('slaves',np.asarray(setup['floquets'][4].mpc.slaves)))}
        witness=_complete_recovery_witness(condensed,layout,save_array=save_array,gate=allocation_gate,event=event)
        # Original live FFCx volume plus complete original carrier, not the
        # condensed action, supplies this independently saved native witness.
        state_data=np.load(root/'arrays/twist_0_complete_recovery_recovered.npy',allow_pickle=False)
        alpha_data=np.load(root/'arrays/twist_0_complete_recovery_alpha.npy',allow_pickle=False)
        full_rhs=np.load(root/'arrays/twist_0_complete_recovery_FE_rhs.npy',allow_pickle=False)
        port_rhs=np.load(root/'arrays/twist_0_complete_recovery_port_rhs.npy',allow_pickle=False)
        vec=PETSc.Vec().createSeq(8940,comm=PETSc.COMM_SELF)
        try:
            vec.array[:]=state_data;volume=local['volume_action'].apply(vec).array.copy()
        finally:vec.destroy()
        coupling=np.zeros(8940,complex);projection=np.empty(228,complex);h=np.empty(228)
        carrier_records=[]
        for i,entry in enumerate(local['dtn_action'].carrier.entries):
            np.add.at(coupling,entry.coupling_rows,entry.coupling_values*alpha_data[i])
            projection[i]=np.dot(entry.projection_values,state_data[entry.projection_rows]);h[i]=entry.normalization_h
            carrier_records.append({key:snapshot.array(f'carrier/{i}/{key}',value) for key,value in
                (('C_rows',entry.coupling_rows),('C_values',entry.coupling_values),
                 ('D_rows',entry.projection_rows),('D_values',entry.projection_values))})
        fe_res=full_rhs-volume-coupling;port_res=port_rhs+projection-h*alpha_data
        native_defect=float(np.linalg.norm(fe_res)/np.linalg.norm(full_rhs))
        port_defect=float(np.linalg.norm(port_res)/np.linalg.norm(port_rhs))
        original_witness={key:snapshot.array('original_witness/'+key,value) for key,value in
            (('volume_action',volume),('coupling_action',coupling),('projection',projection),('H',h),
             ('FE_residual',fe_res),('port_residual',port_res))}
        event('original_live_FFCx_FE_port_residual',{'FE_relative':native_defect,'port_relative':port_defect})
        if not np.isfinite(native_defect+port_defect) or max(native_defect,port_defect)>1e-10:
            raise ValueError('original live FE/port residual gate failed')
        trace=trace_layout_coordinates(layout,condensed.system,allocation_gate=allocation_gate)
        coords=TwoCellBranchCoordinates(trace,condensed,context,global_original_H=authority.load('port_original_H'),
                                        allocation_gate=allocation_gate,index_dtype=PETSc.IntType)
        qmap=coords.q_map(0);saved_qmap=save_csr(snapshot,'qmap0',qmap)
        provider=TwoCellBlockProvider(condensed,coords,allocation_gate=allocation_gate,
            compact_projection_max_owned_bytes=128<<20,compact_projection_tile_width=128)
        event('compact_q0_projection_begin',{'tile_width':128,'owned_projection_limit_bytes':128<<20})
        matrix=provider.block(0,0);csr_audit(matrix,petsc_index_dtype=PETSc.IntType)
        comparison=_compare(matrix,authority.q_block(0),limit=1e-11,label='fresh_C1b_q0_complete_CSR')
        event('compact_q0_reference_comparison',comparison)
        if not comparison['passed']:raise ValueError('compact q0 does not match actual fullNy reference')
        saved_matrix=save_csr(snapshot,'q0',matrix)
        recipes=[]
        for i,(row,col,value,label) in enumerate(condensed.iter_contributions(allocation_gate=allocation_gate)):
            entry={'label':label,'rows':snapshot.array(f'contributions/{i}/rows',row),
                   'cols':snapshot.array(f'contributions/{i}/cols',col)}
            if isinstance(value,DiagonalOriginalPortBlock):
                entry.update(kind='diagonal',values=snapshot.array(f'contributions/{i}/H',value.diagonal))
            elif isinstance(value,CachedPortCorrection):
                entry.update(kind='correction',Di=snapshot.array(f'contributions/{i}/Di',value.Di),
                             XiB=snapshot.array(f'contributions/{i}/XiB',value.XiB))
            else:entry.update(kind='dense',values=snapshot.array(f'contributions/{i}/values',value))
            recipes.append(entry)
        cells=[]
        for i,cell in enumerate(condensed.action._cells):
            entry={name:snapshot.array(f'cells/{i}/{name}',getattr(cell,name)) for name in
                ('original_interiors','original_trace','active_ids','recovery','trace_from_interior','ports','Di','XiB')
                if getattr(cell,name) is not None}
            entry['expansion']=save_csr(snapshot,f'cells/{i}/expansion',cell.expansion)
            entry['LU']=snapshot.array(f'cells/{i}/LU',cell.interior_lu[0]);entry['pivots']=snapshot.array(f'cells/{i}/pivots',cell.interior_lu[1]);cells.append(entry)
        if len(cells)!=40 or condensed.action._H_p is not None or condensed.action._Hhat is not None:
            raise ValueError('compact owner retains a forbidden H/Hhat or loses cells')
        return {'status':STATUS,'scope':'selected b0/q0 compact prefactor only','degree':4,'twist':0,'q':0,
            'global_q_factor_count':0,'inherited_cell_interior_LU_used':True,'PDE_solved':False,'full_C1c_qualified':False,'all532_quotient_qualified':False,
            'global_mode_keys':keys,'physical_generator_manifest_sha256':sha,
            'twist_identity':{'b':0,'theta':_jsonable(context.theta),'eta':_jsonable(context.eta),'tau':_jsonable(context.tau),
                              'sector_original_indices':list(context.original_mode_indices)},
            'authority':authority.identity(),'raw_receipt':{'path':str(raw_path.relative_to(root)),'sha256':_sha(raw_path)},
            'cell_metrics':metric,'native_column_bridge':maps,'recovery_witness':witness,
            'original_witness':original_witness,'carrier_records':carrier_records,
            'original_witness_scope':'saved live FFCx volume action; independent checker reconstructs carrier and residual, not FFCx',
            'partition':partition,'qmap':saved_qmap,'candidate':saved_matrix,'comparison':comparison,
            'recipes':recipes,'cells':cells,'condensation':_jsonable(condensed.audit),
            'port_owner':_jsonable(condensed.action.buffer_inventory),'snapshot':snapshot.identity(),
            'projection_owned_limit_bytes':128<<20,'projection_tile_width':128,
            'no_candidate_fullNy_S_F_Q':True,'source_authority_scope':'fresh current C1b; no lost historical artifact'}
    finally:
        if condensed is not None:condensed.destroy()
        if local is not None:destroy_same_mesh_physical_action(local)


def check_prefactor(report,load,*,reference,allocation_gate):
    """Saved-only independent sparse congruence and cached-RHS reconstruction."""
    from scipy.linalg import lu_solve
    from benchmarks.check_y_orbit_two_cell_audit import validate_local_row_partition
    if (report.get('status')!=STATUS or report.get('q')!=0 or report.get('twist')!=0
            or report.get('global_q_factor_count')!=0 or report.get('full_C1c_qualified') is not False
            or len(report.get('cells',[]))!=40 or report.get('no_candidate_fullNy_S_F_Q') is not True):
        raise ValueError('selected compact witness inventory differs')
    def csr(record):
        data,indices,indptr=(load(record[k]) for k in ('data','indices','indptr'))
        _gate(allocation_gate,'candidate_CSR_construction',payload=0,workspace=3*(data.nbytes+indices.nbytes+indptr.nbytes))
        return sparse.csr_matrix((data,indices,indptr),shape=record['shape'])
    part={k:load(v) for k,v in report['partition'].items()}
    validate_local_row_partition(*(part[k].tolist() for k in ('independent','trace','interior','slaves')))
    qmap=csr(report['qmap']);candidate=csr(report['candidate']);csr_audit(candidate,petsc_index_dtype=np.int32)
    if qmap.shape!=(3844,1884) or candidate.shape!=(1884,1884):raise ValueError('complete q0 rows differ')
    result=sparse.csr_matrix(candidate.shape,dtype=complex);seen=set()
    state=load({'name':'twist_0_complete_recovery_state'});alpha=load({'name':'twist_0_complete_recovery_alpha'})
    native_state=np.concatenate((state[part['trace']],alpha));native_action=np.zeros(3844,complex)
    for item in report['recipes']:
        label=item['label']
        if label in seen:raise ValueError('duplicate compact contribution')
        seen.add(label);rows=load(item['rows']);cols=load(item['cols'])
        if item['kind']=='diagonal':native_action[rows]+=load(item['values'])*native_state[cols]
        elif item['kind']=='correction':native_action[rows]+=load(item['Di'])@(load(item['XiB'])@native_state[cols])
        elif item['kind']=='dense':native_action[rows]+=load(item['values'])@native_state[cols]
        else:raise ValueError('unknown compact recipe')
        if rows.ndim!=1 or cols.ndim!=1 or rows.dtype.kind not in 'iu' or cols.dtype.kind not in 'iu' or len(np.unique(rows))!=len(rows) or len(np.unique(cols))!=len(cols) or np.any(rows<0) or np.any(rows>=3844) or np.any(cols<0) or np.any(cols>=3844):
            raise ValueError('invalid native contribution indices')
        left=qmap[rows];right=qmap[cols]
        lp,rp=np.unique(left.indices),np.unique(right.indices)
        if not len(lp) or not len(rp):continue
        _gate(allocation_gate,'independent_projected_rectangle',payload=16*(len(rows)*len(lp)+len(cols)*len(rp)+2*len(lp)*len(rp)),workspace=3*(result.nnz+len(lp)*len(rp))*24+(1<<20))
        l=left[:,lp].toarray();r=right[:,rp].toarray()
        if item['kind']=='diagonal':projected=l.conj().T@(load(item['values'])[:,None]*r)
        elif item['kind']=='correction':projected=(l.conj().T@load(item['Di']))@(load(item['XiB'])@r)
        elif item['kind']=='dense':projected=l.conj().T@load(item['values'])@r
        else:raise ValueError('unknown compact recipe')
        ii,jj=np.nonzero(projected);result=(result+sparse.coo_matrix((projected[ii,jj],(lp[ii],rp[jj])),shape=result.shape).tocsr()).tocsr()
    expected={'ports/H_original'}|{f'volume/cell/{i}' for i in range(40)}
    for i,cell in enumerate(report['cells']):
        if len(load(cell['ports'])):expected|={f'cell/{name}/{i}' for name in ('C_hat','-D_hat','Hhat_correction')}
    # Direct trace labels are explicitly retained in the producer inventory;
    # enforce both C and D for every one of the228 actual nonempty modes.
    expected|={f'direct/{name}/port/{i}' for name in ('C','-D') for i in range(228)}
    if seen!=expected:raise ValueError('complete compact contribution inventory differs')
    checks=[_compare(candidate,reference,limit=1e-11,label='saved_reference'),
            _compare(result,candidate,limit=1e-11,label='independent_recipe_projection')]
    rhs=load({'name':'twist_0_complete_recovery_FE_rhs'});alpha=load({'name':'twist_0_complete_recovery_alpha'})
    state=load({'name':'twist_0_complete_recovery_state'});bottom=load({'name':'twist_0_complete_recovery_port_rhs'})
    reduced=np.concatenate((rhs[part['trace']],bottom)).copy();recovered=np.zeros(8940,complex)
    active=state[part['trace']];recovered[part['trace']]=active;covered=[]
    for cell in report['cells']:
        ids=load(cell['original_interiors']);aid=load(cell['active_ids']);ports=load(cell['ports']);exp=csr(cell['expansion'])
        piv=load(cell['pivots'])
        if piv.shape!=(108,) or piv.dtype.kind not in 'iu' or np.any(piv<np.arange(108)) or np.any(piv>=108):raise ValueError('invalid LU pivots')
        _gate(allocation_gate,'writable_LAPACK_pivots_and_rhs',payload=108*4+108*16,workspace=64<<10)
        solved=lu_solve((load(cell['LU']),np.array(piv,dtype=np.int32,copy=True)),rhs[ids])
        reduced[aid]+=exp.conj().T@(load(cell['trace_from_interior'])@rhs[ids])
        recovered[ids]=solved+load(cell['recovery'])@(exp@active[aid]);covered.extend(ids.tolist())
        if len(ports):
            reduced[3616+ports]+=load(cell['Di'])@solved
            recovered[ids]-=load(cell['XiB'])@alpha[ports]
    if sorted(covered)!=sorted(part['interior'].tolist()) or np.count_nonzero(rhs[part['interior']])!=4320 or np.linalg.norm(bottom)<=0:
        raise ValueError('arbitrary complete interior/port RHS witness absent')
    for name,a,b in [('independent_reduced_rhs',reduced,load({'name':'twist_0_complete_recovery_reduced_rhs'})),
                     ('independent_recovery',recovered,load({'name':'twist_0_complete_recovery_recovered'})),
                     ('manufactured_state',recovered,state),
                     ('complete_native_reduced_action',native_action,load({'name':'twist_0_complete_recovery_reduced_action'}))]:
        error=float(np.linalg.norm(a-b)/np.linalg.norm(b));checks.append({'label':name,'relative':error,'passed':np.isfinite(error) and error<=1e-11})
    residual=float(np.linalg.norm(native_action-reduced)/np.linalg.norm(reduced))
    checks.append({'label':'manufactured_reduced_augmented_equation','relative':residual,'passed':np.isfinite(residual) and residual<=1e-10})
    for q in (0,2):
        error=load({'name':f'q_{q}_map_column_error_norms'});norm=load({'name':f'q_{q}_map_reference_column_norms'})
        if error.shape!=(3968,) or norm.shape!=(3968,) or np.any(norm<=0):raise ValueError('complete native column bridge absent')
        maximum=float(np.max(error/norm));checks.append({'label':f'complete_q{q}_native_column_bridge','relative':maximum,'passed':np.isfinite(maximum) and maximum<=1e-12})
    if not np.all(recovered[part['slaves']]==0):raise ValueError('recovered slave entries are nonzero')
    original=report['original_witness'];coupling=np.zeros(8940,complex);projection=np.empty(228,complex)
    if len(report.get('carrier_records',[]))!=228:raise ValueError('complete228 original carrier absent')
    for i,item in enumerate(report['carrier_records']):
        cr,cv,dr,dv=(load(item[k]) for k in ('C_rows','C_values','D_rows','D_values'))
        if cr.ndim!=1 or dr.ndim!=1 or cr.shape!=cv.shape or dr.shape!=dv.shape or np.any(cr<0) or np.any(cr>=8940) or np.any(dr<0) or np.any(dr>=8940):
            raise ValueError('original carrier support differs')
        np.add.at(coupling,cr,cv*alpha[i]);projection[i]=np.dot(dv,recovered[dr])
    fe=rhs-load(original['volume_action'])-coupling;port=bottom+projection-load(original['H'])*alpha
    for name,value,expected,denominator,limit in (
        ('original_carrier_C',coupling,load(original['coupling_action']),coupling,1e-11),
        ('original_carrier_D',projection,load(original['projection']),projection,1e-11),
        ('full_original_FE_residual',fe,np.zeros(8940,complex),rhs,1e-10),
        ('original_port_residual',port,np.zeros(228,complex),bottom,1e-10)):
        scale=float(np.linalg.norm(denominator));error=float(np.linalg.norm(value-expected))
        passed=bool(np.isfinite(error+scale) and (error<=limit*scale if scale>0 else error==0))
        checks.append({'label':name,'error_norm':error,'operation_scale':scale,'limit':limit,'passed':passed})
    if not all(x['passed'] for x in checks):raise ValueError('independent compact prefactor gates failed')
    return {'gate_pass':True,'checks':checks,'global_q_factor_count':0,'inherited_cell_interior_LU_used':True,'full_C1c_qualified':False,
            'scope':'selected b0/q0 compact projection/RHS/recovery only','all4320_interiors_checked':True}
