"""Thin physical-subdomain strategy on the existing controlled FGMRES tail."""
import gc
import json
import time
from pathlib import Path

import numpy as np

from src.runners.task042_shared import write_json
from . import impedance_trace_scope as scope
from . import bounded_trace_study as common
from .scattering_anchor import Journal, relative, save_arrays
from .scattering_anchor_checks import checked_arrays
from .bounded_trace_pc import csr_load, csr_save, BoundedTwoLevelPC
from .physical_impedance_patch import TriangleImpedance, halo_matrix, independent_patch_action


def parents():
    prep=scope.parent_preparation()
    qualification=scope.checked_json(scope.plan_record()['reuse_qualification'])
    if not qualification['preparation_checks']['mathematics_pass']:
        raise ValueError('immutable original coarse/owner qualification')
    arrays=checked_arrays(prep['patch_arrays'])
    patches=[{k:arrays[f'{j}_{k}'] for k in ('ids','core','core_cells','halo_cells','low','high')}
             for j in range(prep['patch_inventory']['patches'])]
    if len(patches)!=38 or max(len(p['ids']) for p in patches)>80000:
        raise ValueError('V77 exact original partition')
    return prep,patches


def identity(prep):
    p=scope.plan_record()
    return dict(packet_sha256=p['prepared_parent']['local_packet']['sha256'],
        map_sha256=prep['patch_arrays']['sha256'],Z_sha256=prep['Z']['sha256'],
        body='HALO_CELLS_ONLY',impedance=p['impedance'],physical_sha256=__import__('hashlib').sha256(json.dumps(scope.physical_for('PRECHECK'),sort_keys=True,separators=(',',':')).encode()).hexdigest())


def build_patch(j,patch,prep,a,faces,folder,journal):
    checkpoint=folder/f'patch_{j:02d}.json'
    expected=identity(prep)
    if checkpoint.exists():
        record=json.loads(checkpoint.read_text())
        if record['identity']!=expected: raise ValueError('V77 saved patch identity')
        return record
    with journal.measured('halo_body_and_actual_triangle_mass_patch_'+str(j)):
        matrix,details=halo_matrix(a,patch,faces)
    receipt=csr_save(folder/f'patch_{j:02d}.npz',matrix)
    record=dict(index=j,identity=expected,matrix=receipt,details=details,
        producer=journal.source_state,raw_face_structure=faces.structure_rows.copy())
    write_json(checkpoint,record)
    del matrix; gc.collect()
    return record


def precheck(folder,journal):
    prep,patches=parents()
    s,b,oracle,a,rhs,left,right=common.setup_service('PRECHECK',journal,scope=scope)
    faces=TriangleImpedance(s)
    largest=max(range(38),key=lambda j:len(patches[j]['ids']))
    tags=s['data'].cell_tags.values
    interface=[j for j,p in enumerate(patches) if any(tags[c]!=tags[d]
        for _,_,c,d in faces.boundary(p)[1])]
    if not interface: raise ValueError('saved partition contains no material interface patch')
    chosen=[largest,next(j for j in interface if j!=largest)]
    write_json(folder/'preregistered_patch_pair.json',dict(maximum_patch=largest,
        smallest_material_interface_patch=chosen[1],selection='row maximum then smallest ID containing internal material interface; distinct'))
    rows=[];saved={}
    for j in chosen:
        record=build_patch(j,patches[j],prep,a,faces,folder,journal)
        matrix=csr_load(record['matrix']); rng=np.random.default_rng(7700+j)
        vector=rng.normal(size=matrix.shape[0])+1j*rng.normal(size=matrix.shape[0])
        with journal.measured('PUBLIC_BASIX_halo_body_and_triangle_q15_patch_'+str(j)):
            out,volume,surface,qerror=independent_patch_action(s,a,patches[j],faces,vector)
        actual=matrix@vector; error=relative(actual-out,out)
        # A read-only packet-only witness distinguishes the subdomain from a
        # full-operator principal block. No old big patch CSR is read.
        mapping=np.full(a.nt,-1,np.int64); mapping[patches[j]['ids']]=np.arange(len(vector))
        halo=set(map(int,patches[j]['halo_cells'])); outside=np.zeros_like(vector); touched=0
        for c,_,active,E,key in a.cell_records:
            if c in halo: continue
            good=np.flatnonzero(mapping[active]>=0)
            if not len(good): continue
            local=E[:,good]; v=local@vector[mapping[active[good]]]
            np.add.at(outside,mapping[active[good]],local.conj().T@(a.cache[key]['schur']@v)); touched+=1
        arrays=save_arrays(folder/f'patch_action_{j:02d}.npz',input=vector,
            matrix_action=actual,independent=out,body=volume,surface=surface,excluded_outside_body=outside)
        row=dict(index=j,operation_relative=error,q13_q15_maximum=qerror,
            excluded_cells_touching_ids=touched,excluded_body_norm=float(np.linalg.norm(outside)),
            arrays=arrays,pass_gate=error<=1e-10 and qerror<=1e-10,
            new_local_matrix_is_not_old_principal_plus_mass=touched>0 and np.linalg.norm(outside)>0)
        rows.append(row); saved[str(j)]=record
        write_json(folder/'actual_patch_pair_progress.json',dict(rows=rows,saved_patches=saved))
        del matrix,out,volume,surface;gc.collect()
    result=dict(status='COMPLETED',pass_gate=all(r['pass_gate'] for r in rows),
        patch_checks=rows,saved_patches=saved,patch_parent=prep['patch_arrays'],
        periodic_mate_pairs=len(faces.mates)//2,facet_cache_bytes=faces.cache_bytes,
        unique_core_qualification=scope.plan_record()['reuse_qualification'],
        source=journal.source_state,timings=journal.timings,new_numeric_factors=0,new_complete_solves=0,
        global_fine_K_reads=0,global_fine_S_reads=0,old_principal_matrix_reads=0)
    write_json(folder/'impedance_precheck.json',result);a.release_hot()
    if not result['pass_gate']: raise ValueError('V77 actual patch original action gate')
    return result


def prepare(folder,journal):
    scope.require_stage('PREPARE');prep,patches=parents()
    s,b,oracle,a,rhs,left,right=common.setup_service('PREPARE',journal,scope=scope)
    faces=TriangleImpedance(s);check=scope.stage('PRECHECK');saved=check['saved_patches']
    matrices=[];analysis=[];records=[]
    for j,patch in enumerate(patches):
        scope.window.require_live(margin=4500)
        record=saved[str(j)] if str(j) in saved else build_patch(j,patch,prep,a,faces,folder,journal)
        if record['identity']!=identity(prep): raise ValueError('V77 mathematical checkpoint')
        A=csr_load(record['matrix'])
        symfile=folder/f'symbolic_{j:02d}.json'
        if symfile.exists():
            sym=json.loads(symfile.read_text())
            if sym['input_sha256']!=record['matrix']['sha256']: raise ValueError('symbolic input identity')
            sym=sym['analysis']
        else:
            sym=common.symbolic(A,journal,'impedance_patch_'+str(j))
            write_json(symfile,dict(input_sha256=record['matrix']['sha256'],analysis=sym))
        matrices.append(record['matrix']);analysis.append(sym);records.append(record)
        del A;gc.collect()
        write_json(folder/'new_patch_progress.json',dict(completed=len(matrices),matrices=matrices,
            analysis=analysis,records=records,qualified_reused=len([k for k in range(j+1) if str(k) in saved])))
    total=sum(x['double_bytes'] for x in analysis)+prep['coarse_symbolic']['double_bytes']
    result=dict(status='COMPLETED',pass_gate=total<=80*2**30,matrices=matrices,analysis=analysis,
        patch_arrays=prep['patch_arrays'],patch_inventory=prep['patch_inventory'],Z=prep['Z'],
        coarse_matrix=prep['coarse_matrix'],coarse_symbolic=prep['coarse_symbolic'],
        double_symbolic_total_bytes=total,new_patch_matrix_count=38,prechecked_patch_reuse_count=2,
        original_coarse_reused=True,new_numeric_factors=0,new_complete_solves=0,
        global_fine_K_reads=0,global_fine_S_reads=0,old_principal_matrix_reads=0,
        facet_cache_bytes=faces.cache_bytes,source=journal.source_state,timings=journal.timings,
        records=records)
    write_json(folder/'impedance_preparation.json',result);a.release_hot()
    return result


def pc_factory(*,folder,journal,state,setup,boundary,packet,full_rhs,left,right,scaled_rhs,original):
    from .reused_trace_admission import future_workspace
    prep=scope.stage('PREPARE');Z=csr_load(prep['Z']);pa=checked_arrays(prep['patch_arrays'])
    patches=[{k:pa[f'{j}_{k}'] for k in ('ids','core')} for j in range(38)]
    workspace=future_workspace(len(scaled_rhs),len(full_rhs),setup['P'].shape[0],
        max(r['rows'] for r in prep['analysis']),max(r['nnz'] for r in prep['analysis']),
        restart=128,minimum_bytes=12*2**30)
    remaining=scope.window.snapshot()['heavy_remaining_seconds'];needed=3600+1800+4500
    write_json(folder/'pre_PC_numeric_forecast.json',dict(remaining_seconds=remaining,
        numeric_upper_seconds=3600,first_block_upper_seconds=1800,acceptance_reserve_seconds=4500,
        admitted=remaining>=needed,workspace=workspace))
    if remaining<needed: raise RuntimeError('V77 real factor + first effect + full acceptance reserve')
    local,coarse=common.numeric_factors(prep,journal,scope=scope,folder=folder,workspace=workspace,clock_root=folder)
    pc=BoundedTwoLevelPC(Z,patches,local,coarse,lambda v:original('I_PC_original',v))
    try:
        with journal.measured('actual_impedance_PC_complex_linearity'):
            first=pc(scaled_rhs);alpha=.31+.73j;second=pc(alpha*scaled_rhs)
        error=relative(second-alpha*first,alpha*first)
        write_json(folder/'live_PC_qualification.json',dict(pass_gate=error<=1e-10,complex_linearity=error,
            variant='original coarse-first, only halo impedance factors changed',
            arrays=save_arrays(folder/'PC_linearity.npz',rhs=scaled_rhs,first=first,second=second,alpha=np.asarray(alpha))))
        if error>1e-10: raise ValueError('V77 actual linear PC witness')
        return pc,39
    except BaseException: pc.destroy();raise


def execute(role,folder,state):
    if state.get('memory_budget')!=scope.memory_budget(role): raise ValueError('V77 resolved/live budget')
    journal=Journal(folder,window_scope=scope.window,planning_limit_bytes=scope.memory_budget(role)['planning_gib']*2**30)
    journal.source_state=state
    if role=='PRECHECK': return precheck(folder,journal)
    if role=='PREPARE': return prepare(folder,journal)
    if role=='ITERATE':
        from .controlled_trace_study import iterate,consume_returned
        if state.get('postprocessing_resume'): return consume_returned(role,folder,journal,state,scope=scope)
        return iterate(role,folder,journal,state,scope=scope,pc_factory=pc_factory,strategy='PHYSICAL_IMPEDANCE')
    if role=='VERIFY_COST':
        from benchmarks.collect_controlled_trace import verify
        return verify(folder,journal,scope=scope)
    raise ValueError('V77 one-run role')
