"""Independent frozen V71 arrays; a resource rejection is not a solve pass."""
import gc
import json
from pathlib import Path

import numpy as np

from src.runners.task042_shared import write_json
from src.solvers import bounded_trace_scope as scope
from src.solvers.scattering_anchor import relative
from src.solvers.scattering_anchor_checks import checked_arrays
from src.solvers.tetra_body_checkpoint import file_digest


def symbolic_gate(analysis, coarse, *, limit_bytes=64*2**30):
    """Recompute the fixed sum from backend fields, never its saved decision."""
    if limit_bytes != 64*2**30:
        raise ValueError('V71 fixed total double-symbolic limit')
    rows=[]
    for r in [*analysis, coarse]:
        info=r['info']['infog'];estimate=max(int(info[str(k)]) for k in (16,17))
        if estimate<=0 or r['controls']['icntl']['22']!=0 or int(info['1'])!=0:
            raise ValueError('reliable in-core successful symbolic inventory')
        double=2*estimate*1_000_000
        if (r['estimate_mb'],r['double_bytes'],r['numeric_calls'])!=(estimate,double,0):
            raise ValueError('raw symbolic fields or numeric inventory mismatch')
        rows.append(dict(rows=r['rows'],nnz=r['nnz'],estimate_decimal_MB=estimate,double_bytes=double))
    local=sum(r['double_bytes'] for r in rows[:-1]);total=local+rows[-1]['double_bytes']
    return dict(local_double_bytes=local,coarse_double_bytes=rows[-1]['double_bytes'],
        double_symbolic_sum_bytes=total,limit_bytes=limit_bytes,admitted=total<=limit_bytes,
        excess_bytes=max(0,total-limit_bytes),factors=rows)


def owner_gate(arrays, nt, count):
    keys={'ids','core','core_cells','halo_cells','low','high'}
    if set(arrays)!={f'{j}_{k}' for j in range(count) for k in keys} or not 32<=count<=64:
        raise ValueError('fixed complete geometric patch inventory')
    owners=np.zeros(nt,np.int16);maximum=total=0
    for j in range(count):
        ids=arrays[f'{j}_ids'];core=arrays[f'{j}_core']
        if (ids.ndim!=1 or core.ndim!=1 or np.any(ids<0) or np.any(ids>=nt)
                or np.any(np.diff(ids)<=0) or np.any(core<0) or np.any(core>=nt)
                or len(np.unique(core))!=len(core) or not np.isin(core,ids).all()):
            raise ValueError('patch principal rows and unique core inventory')
        if not np.isin(arrays[f'{j}_core_cells'],arrays[f'{j}_halo_cells']).all():
            raise ValueError('patch halo excludes its own core cells')
        np.add.at(owners,core,1);maximum=max(maximum,len(ids));total+=len(ids)
    if not np.all(owners==1) or maximum>80000:
        raise ValueError('fixed core writeback or row limit')
    return dict(trace_rows=nt,patches=count,all_trace_writeback_once=True,
                maximum_rows=maximum,overlap_row_sum=total)


def csr_inventory(arrays):
    data,cols,ptr,shape=(arrays[k] for k in ('data','indices','indptr','shape'))
    if (data.dtype!=np.complex128 or cols.dtype!=np.int64 or ptr.dtype!=np.int64
            or shape.shape!=(2,) or min(shape)<1 or len(ptr)!=int(shape[0])+1
            or ptr[0]!=0 or ptr[-1]!=len(data) or len(cols)!=len(data)
            or np.any(np.diff(ptr)<0) or np.any(cols<0) or np.any(cols>=shape[1])
            or not np.isfinite(data).all()):
        raise ValueError('saved complete complex128/int64 CSR inventory')
    return dict(shape=list(map(int,shape)),stored_entries=len(data),
                exact_nonzero=int(np.count_nonzero(data)),explicit_bytes=data.nbytes+cols.nbytes+ptr.nbytes)


def galerkin_gate(Z,E0,a):
    n0=Z.shape[1];nt=Z.shape[0]
    w=a['w'];v=np.r_[Z@w[:n0],w[n0:]]
    pulled=np.r_[Z.conj().T@a['original'][:nt],a['original'][nt:]]
    target=E0@w
    scores=dict(prolong=relative(v-a['Zw'],v),pullback=relative(pulled-a['pulled'],pulled),
        saved_coarse_action=relative(target-a['coarse_action'],target),
        FE=relative(pulled[:n0]-target[:n0],target[:n0]),
        port=relative(pulled[n0:]-target[n0:],target[n0:]),full=relative(pulled-target,target),
        dual=float(abs(np.vdot(v,a['original'])-np.vdot(w,pulled))/max(np.linalg.norm(v)*np.linalg.norm(a['original']),1e-30)))
    return dict(scores=scores,pass_gate=all(np.isfinite(v) and 0<=v<=1e-10 for v in scores.values()))


def saved_preparation_check(O,P):
    """Stream only new preparation arrays and the allowed arbitrary RHS witness."""
    errors=[]
    if len(O['arrays'])!=2 or len(P['galerkin'])!=2:
        raise ValueError('two fixed action and Galerkin witnesses required')
    references=checked_arrays(scope.plan_record()['prepared_parent']['retained_action_witness'])
    for j,r in enumerate(O['arrays']):
        a=checked_arrays(r);nt=len(a['output'])-828
        if not np.array_equal(a['input'],references['inputs'][:,j]) or not np.array_equal(a['reference'],references['outputs'][:,j]):
            raise ValueError('original V70 fixed input/output witness identity')
        errors.append({k:relative((a['output']-a['reference'])[s],a['reference'][s])
                       for k,s in [('FE',slice(None,nt)),('port',slice(nt,None)),('full',slice(None))]})
    del a,references;gc.collect()
    w=checked_arrays(O['nonzero_rhs_witness']['original_witness_source'])
    a=checked_arrays(O['nonzero_rhs_witness']['arrays'])
    if not np.array_equal(a['rhs'],w['rhs']) or not np.array_equal(a['trace'],w['retained'][:,0]):
        raise ValueError('arbitrary RHS and retained witness pairing')
    from src.solvers.tetra_assembly_packet import _read_manifest
    from src.solvers.scattering_anchor import array_hash
    root,manifest=_read_manifest(scope.plan_record()['prepared_parent']['local_packet'])
    meta=manifest['members']['retained'];path=root/meta['file']
    if file_digest(path)!=meta['sha256']:raise ValueError('actual retained inventory file identity')
    retained=np.load(path,allow_pickle=False)
    if list(retained.shape)!=meta['shape'] or array_hash(retained)!=meta['member_sha256']:
        raise ValueError('actual retained inventory member identity')
    interior=np.setdiff1d(np.arange(1943745,dtype=np.int64),retained[retained<1943745])
    rhs=dict(recovery=relative(a['recovered']-w['full'][:,0],w['full'][:,0]),
             original_operation=relative(a['lifted']-w['original_residual'][:,0],w['original_action'][:,0]),
             internal_rows=len(interior),
             nonzero_internal_and_port=bool(len(interior)==767280 and np.any(a['rhs'][interior]) and np.any(a['rhs'][1943745:])))
    del a,w,retained,interior;gc.collect()
    pa=checked_arrays(P['patch_arrays']);owner=owner_gate(pa,1176465,len(P['matrices']))
    matrices=[]
    for j,(r,info) in enumerate(zip(P['matrices'],P['analysis'],strict=True)):
        a=checked_arrays(r);v=csr_inventory(a)
        if v['shape']!=[len(pa[f'{j}_ids'])]*2 or (info['rows'],info['nnz'])!=(v['shape'][0],v['stored_entries']):
            raise ValueError('patch CSR/owner/backend inventory mismatch')
        matrices.append(v);del a;gc.collect()
    del pa;gc.collect()
    from scipy import sparse
    a=checked_arrays(P['Z']);Z=sparse.csr_matrix((a['data'],a['indices'],a['indptr']),shape=tuple(a['shape']))
    z=csr_inventory(a)
    if z['shape']!=[1176465,6240] or P['coarse_inventory']['with_ports']!=7068 or P['coarse_symbolic']['rows']!=7068:
        raise ValueError('actual fixed p2/828 inventory')
    b=checked_arrays(P['coarse_matrix']);e0=csr_inventory(b)
    E0=sparse.csr_matrix((b['data'],b['indices'],b['indptr']),shape=tuple(b['shape']))
    if e0['shape']!=[7068,7068] or e0['stored_entries']!=P['coarse_symbolic']['nnz']:
        raise ValueError('coarse CSR/backend inventory mismatch')
    galerkin=[galerkin_gate(Z,E0,checked_arrays(r['arrays'])) for r in P['galerkin']]
    del a,b,Z,E0;gc.collect()
    capacity=symbolic_gate(P['analysis'],P['coarse_symbolic'])
    if P['double_symbolic_sum_bytes']!=capacity['double_symbolic_sum_bytes'] or P['symbolic_sum_admitted']!=capacity['admitted']:
        raise ValueError('producer capacity arithmetic/decision mismatch')
    mathematical=all(r['pass_gate'] for r in galerkin)
    if P['pass_gate']!=(mathematical and capacity['admitted']):
        raise ValueError('producer combined PC qualification mismatch')
    O_values=[v for r in errors for v in r.values()]+[rhs['recovery'],rhs['original_operation']]
    O_pass=all(np.isfinite(v) and 0<=v<=1e-10 for v in O_values) and rhs['nonzero_internal_and_port']
    if O_pass!=O['pass_gate']:raise ValueError('producer original action decision mismatch')
    if not capacity['admitted'] and any(P[k] for k in ('local_numeric_count','coarse_numeric_count','global_fine_numeric_count')):
        raise ValueError('numeric attempted after rejected fixed total memory gate')
    return dict(original_action=dict(errors=errors,nonzero_rhs=rhs,pass_gate=O_pass),
        owner=owner,patch_matrices=matrices,Z=z,coarse_matrix=e0,galerkin=galerkin,
        mathematics_pass=mathematical,capacity=capacity,PC_pass=mathematical and capacity['admitted'],
        total_patch_stored_entries=sum(v['stored_entries'] for v in matrices),
        numeric_counts={k:P[k] for k in ('local_numeric_count','coarse_numeric_count','global_fine_numeric_count')},
        independent_array_consumption=True,new_original_actions=0,new_factors=0,new_KSP_solves=0)


def verify(folder,journal):
    O=scope.stage('PREFLIGHT');P=scope.stage('PC_SETUP')
    with journal.measured('independent_saved_original_owner_symbolic_Galerkin'):
        preparation=saved_preparation_check(O,P)
    frozen=scope.verification_inventory_for('VERIFY_COST')
    if frozen is None or journal.source_state.get('verification_inventory',{}).get('sha256')!=file_digest(frozen):
        raise ValueError('V71 frozen unique consumer inventory')
    freeze=json.loads(frozen.read_text())
    for role in ('PREFLIGHT','PC_SETUP'):
        pointer=json.loads((scope.ARTIFACT/(role+'.json')).read_text())
        if 'states' in freeze and freeze['states'].get(role)!=pointer:
            raise ValueError('frozen producer pointer identity')
    if not freeze.get('candidate_count',int('retained' in freeze)):
        if preparation['PC_pass']:
            raise ValueError('no candidate requires a proved dependency rejection')
        result=dict(status='COMPLETED',pass_gate=False,consumer_pass=True,preparation=preparation,
            main_result='NOT_RUN_CAPACITY_BLOCKED',reason='all local+coarse double symbolic exceeds fixed64GiB',
            candidate_count=0,full_equation=dict(status='NOT_RUN',reason='KSP was not started'),
            complete_fields=dict(status='NOT_RUN',reason='no returned physical candidate'),
            official_RTA=dict(status='NOT_RUN',reason='no equation-qualified candidate'),
            source=journal.source_state,timings=journal.timings,calls=journal.calls,
            new_numeric_factors=0,new_complete_solves=0,new_original_actions=0,
            continuum_accuracy=False,target_qualified=False,NN20=False)
        write_json(folder/'verification_scientific_result.json',result);return result
    from src.solvers import assembly_tetra_scope as prior
    from src.solvers.tetra_polynomial_difference import comparison
    from src.solvers.independent_tetra_fields import selected_points
    from benchmarks.collect_frozen_local_h import saved_original
    from benchmarks.check_independent_tetra import saved_pair
    from benchmarks.collect_exact_tetra import strict_reproduction
    r=scope.stage('ITERATE')
    if freeze['retained']['sha256']!=r['retained_returned']['sha256']:raise ValueError('V71 frozen retained identity')
    own=folder/'new';own.mkdir(exist_ok=True)
    from src.solvers.bounded_trace_study import action_charge
    check=action_charge('V_saved_public_original',lambda:saved_original(r,own,journal,body_q=15))
    parent=prior.stage('SOLVE');pair=comparison(parent,r,folder/'V70_V71',journal,coefficient_first=True)
    independent=saved_pair(pair,parent,r,expected_points=selected_points(r['physical']));strict=strict_reproduction(pair)
    if not independent['published_gate_matches_recalculation']:raise ValueError('V71 saved independent comparison decision')
    result=dict(status='COMPLETED',pass_gate=check['pass_gate'] and strict['pass_gate'] and r['scientific_solve_pass'],
        preparation=preparation,independent_original=check,comparison=pair,strict_scores=strict,independent_pair=independent,
        frozen_inventory=dict(path=str(frozen),sha256=file_digest(frozen)),source=journal.source_state,
        timings=journal.timings,calls=journal.calls,new_numeric_factors=0,new_complete_solves=0,
        continuum_accuracy=False,target_qualified=False,NN20=False)
    write_json(folder/'verification_scientific_result.json',result);return result


def verify_reused(folder,journal):
    """V72 new capacity/factors/candidate; V71 math remains bound and immutable."""
    from src.solvers import reused_trace_scope as active
    from src.solvers.reused_trace_admission import reuse_gate, numeric_gate
    from src.solvers import assembly_tetra_scope as reference
    from src.solvers.bounded_trace_study import action_charge
    from benchmarks.collect_frozen_local_h import saved_original
    from benchmarks.check_independent_tetra import saved_pair
    from benchmarks.collect_exact_tetra import strict_reproduction
    from src.solvers.tetra_polynomial_difference import comparison
    from src.solvers.independent_tetra_fields import selected_points
    admission=active.stage('REUSE_ADMIT');P=active.parent_preparation()
    decision=reuse_gate(admission['preparation_checks'],P)
    if not decision['pass_gate']:raise ValueError('V72 independent reuse qualification')
    frozen=active.verification_inventory_for('VERIFY_COST')
    if frozen is None or journal.source_state.get('verification_inventory',{}).get('sha256')!=file_digest(frozen):
        raise ValueError('V72 frozen unique consumer inventory')
    freeze=json.loads(frozen.read_text())
    if not freeze.get('retained'):
        result=dict(status='COMPLETED',pass_gate=False,consumer_pass=True,admission=decision,
            main_result='NO_RETURNED_CANDIDATE',reason=freeze.get('reason'),source=journal.source_state,
            new_original_actions=0,new_numeric_factors=0,new_complete_solves=0)
        write_json(folder/'verification_scientific_result.json',result);return result
    r=active.stage('ITERATE')
    if freeze['retained']['sha256']!=r['retained_returned']['sha256']:raise ValueError('V72 retained freeze identity')
    root=Path(json.loads((active.ARTIFACT/'ITERATE.json').read_text())['path']).parent
    numeric=json.loads((root/'numeric_factor_progress.json').read_text());factor_scores=[]
    for row in numeric['rows']:
        a=checked_arrays(row['arrays'])
        error=relative(a['residual'],a['input'])
        # Recompute residual using the original local CSR, one block at a time.
        from src.solvers.bounded_trace_pc import csr_load
        A=csr_load(row['input']);original=A@a['output']-a['input']
        mismatch=relative(original-a['residual'],a['input'])
        gate=numeric_gate(row['admission']['tree'],row['admission']['remaining_double_symbolic_bytes'],row['admission']['future_workspace'])
        controls=row['controls']['icntl'];expected=row['expected']['estimate_mb']
        passed=gate['admitted'] and error<=1e-8 and mismatch<=1e-12 and np.isfinite(a['output']).all()
        passed=bool(passed and controls['22']==0 and controls['23']==2*expected and row['info_after_numeric']['infog']['1']==0)
        factor_scores.append(dict(index=row['index'],residual=error,recomputed_residual=relative(original,a['input']),
            saved_residual_mismatch=mismatch,pass_gate=passed,numeric_admission=gate))
        del a,A,original;gc.collect()
    if len(factor_scores)!=39 or not all(row['pass_gate'] for row in factor_scores):
        raise ValueError('V72 complete39 numeric/solve and memory qualification')
    pc=json.loads((root/'live_PC_qualification.json').read_text());a,b=(checked_arrays(row['arrays']) for row in pc['rows'])
    alpha=.3+.7j;pc_error=relative(b['output']-alpha*a['output'],alpha*a['output'])
    pc_pass=pc_error<=1e-10 and np.isfinite(a['output']).all() and np.isfinite(b['output']).all()
    if not pc_pass:raise ValueError('V72 saved actual PC finite/complex homogeneity')
    del a,b;gc.collect()
    own=folder/'new';own.mkdir(exist_ok=True)
    check=action_charge('V_saved_public_original',lambda:saved_original(r,own,journal,body_q=15),scope=active)
    # Reference permission starts only here, after candidate freeze and actor exit.
    parent=reference.stage('SOLVE');pair=comparison(parent,r,folder/'V70_V72',journal,coefficient_first=True)
    independent=saved_pair(pair,parent,r,expected_points=selected_points(r['physical']));strict=strict_reproduction(pair)
    if not independent['published_gate_matches_recalculation']:raise ValueError('V72 saved comparison decision')
    result=dict(status='COMPLETED',pass_gate=check['pass_gate'] and strict['pass_gate'] and r['scientific_solve_pass'],
        consumer_pass=True,admission=decision,factor_scores=factor_scores,PC_saved_error=pc_error,
        independent_original=check,comparison=pair,strict_scores=strict,independent_pair=independent,
        frozen_inventory=dict(path=str(frozen),sha256=file_digest(frozen)),source=journal.source_state,
        timings=journal.timings,calls=journal.calls,new_numeric_factors=0,new_complete_solves=0,
        continuum_accuracy=False,target_qualified=False,NN20=False)
    write_json(folder/'verification_scientific_result.json',result);return result
