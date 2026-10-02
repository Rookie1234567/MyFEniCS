"""Recompute the shared local admission from sealed, hash-bound evidence.

The local certificate is written only after original/class64 S and SH tests.
Composite failure does not revoke an independently complete local certificate.
This reader never constructs a factor, reads a field, or changes accounting.
"""
import hashlib
import json
import math

from src.solvers.local_block_coarse import ROWS

FIELDS=('partition','assembly','factor_safety','block_inventory','local_checks','old_new_S_SH_pairs')


def evidence_hash(result):
    raw={key:result[key] for key in FIELDS}
    return hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def local_readiness(result,*,rows=ROWS,expected_map=None,require_seal=True):
    """A true flag or a completed process is insufficient for admission."""
    failures=[]
    def check(value,reason):
        if not value:failures.append(reason)
    def bounded(value,limit):
        return isinstance(value,(int,float)) and math.isfinite(value) and 0<=value<=limit
    try:
        p=result['partition'];n=sum(rows)
        check(p['canonical_rows']==n and tuple(p['block_rows'])==tuple(rows),'partition counts')
        check(p['all_member_hashes_checked'] and p['all_rows_exactly_once'] and p['slave_added']==0 and p['physical_center_rule_recomputed'],'partition/member identity')
        check(p['entity_count']==2448 if n==18144 else p['entity_count']>0,'complete entity inventory')
        if expected_map is not None:check(p['map']==expected_map,'frozen map/member hashes')
        assembly=result['assembly']
        check(assembly['shared_contributions_merged'] and assembly['owner_cells_not_used'] and assembly['all_ports']==40,'shared/Floquet/port assembly')
        check(not assembly['global_fine_K_or_A_constructed'] and not assembly['F_is_C_adjoint_assumed'] and not assembly['separate_curl_mass_condensation'],'original principal assembly')
        factors=result['factor_safety'];inventory=result['block_inventory']
        check(len(factors)==len(inventory)==8,'eight factors/inventory')
        for b,(s,item) in enumerate(zip(factors,inventory,strict=True)):
            check(s['block']==item['block']==b and len(item['rows'])==rows[b],'factor block/order')
            rc=s['rcond1_estimate']
            check(isinstance(rc,(int,float)) and math.isfinite(rc) and rc>=1e-12 and s['gecon_info']==0,'local rcond')
            check(s['partial_pivoting'] and s['shift'] is None and s['drop'] is None and s['refinement']==0,'fixed LU specification')
            check(s['LU_sha256']==item['LU']['array_sha256'] and s['pivot_sha256']==item['pivots']['array_sha256'],'factor member identity')
            check(assembly['blocks'][b]['matrix_sha256']==item['matrix']['array_sha256'],'principal matrix member identity')
            check(item['matrix']['shape']==item['LU']['shape']==[rows[b],rows[b]] and item['pivots']['shape']==[rows[b]],'factor shapes')
        flat=[r for item in inventory for r in item['rows']]
        check(sorted(flat)==list(range(n)),'canonical partition inventory')
        local=result['local_checks'];witnesses=local['witnesses']
        check(len(witnesses)==16,'sixteen principal/solve witnesses')
        for i,w in enumerate(witnesses):
            check(w['block']==i//2 and w['seed']==422401+i,'fixed witness inventory')
            check(bounded(w['original_principal_action']['operation_relative'],1e-10),'principal original action')
            check(bounded(w['solve_relative'],1e-8) and bounded(w['solve_operation_relative'],1e-12),'local solve')
        check(local['zero_exact'] and bounded(local['repeat']['operation_relative'],1e-10) and bounded(local['complex_linearity']['operation_relative'],1e-10),'zero/repeat/complex linearity')
        pairs=result['old_new_S_SH_pairs']
        check(len(pairs)==2 and {v['adjoint'] for v in pairs}=={False,True},'original/class64 S and SH inventory')
        check(all(bounded(v['operation_relative'],1e-10) for v in pairs),'original/class64 S and SH agreement')
        digest=evidence_hash(result)
        if require_seal:
            cert=result.get('local_ready_evidence',{})
            check(cert.get('schema')=='task042.local-ready.v1' and cert.get('evidence_sha256')==digest,'local-ready sealed evidence absent/mismatch')
        return dict(qualified=not failures,failures=failures,evidence_sha256=digest,
                    raw_boolean_flags_not_trusted=True,composite_failure_independent=True)
    except (KeyError,TypeError,ValueError,OverflowError) as error:
        return dict(qualified=False,failures=failures+['incomplete public evidence: '+str(error)],
                    raw_boolean_flags_not_trusted=True)


def seal_local_ready(result,*,rows=ROWS,expected_map=None):
    ready=local_readiness(result,rows=rows,expected_map=expected_map,require_seal=False)
    if not ready['qualified']:raise ValueError('local-ready evidence: '+repr(ready['failures']))
    result['local_ready_evidence']=dict(schema='task042.local-ready.v1',evidence_sha256=ready['evidence_sha256'])
    result['local_qualified']=True
    return local_readiness(result,rows=rows,expected_map=expected_map)
