"""Independent scalar accounting for the bounded recursive formal route."""
import math


def recompute_recursive(pcs, inner, exits, summary):
    errors=[]
    def require(ok,message):
        if not ok:errors.append(message)
    target=summary['profile']['intermediate']['relative_tolerance']
    require(len(inner)==2*len(pcs),'two I4 calls per completed PC required')
    reached=0
    for row in inner:
        require(row['target']==target,'inner target differs from profile')
        g,eps=row['rhs_norm'],row['eps_norm']
        relative=eps/g if g else (0. if eps==0 else float('inf'))
        require(math.isfinite(relative) and g>=0 and eps>=0,'nonfinite or negative inner norms')
        require(abs(relative-row['final_true_residual'])<=1e-12*max(1.,relative),'inner residual differs from raw norms')
        require(row['restart']==16 and row['max_it']==64 and row['iterations']<=64 and row['zero_start'], 'inner frozen contract changed')
        reached+=int(relative<=target)
        require(row['status']==('INNER_TARGET_REACHED' if relative<=target else 'INNER_INEXACT_AT_CAP'),'inner status differs from actual residual')
        require(row['ksp_create_count']==row['ksp_solve_count']==row['ksp_destroy_count']==1,'inner KSP lifecycle differs')
        require(row['identity']==summary['recursive_identity'],'inner source/physical/mode/RHS identity differs')
    audit_rows=[]
    for index,row in enumerate(pcs,1):
        require(row['apply_count']==index,'PC ordinal mismatch')
        require(row['identity']==summary['recursive_identity'],'PC identity differs')
        pair=row['inexact_balance']['calls']
        require(len(pair)==2,'missing eps pair')
        scale=sum(c['rhs_norm']+c['applied_norm'] for c in pair)
        require(abs(scale-row['inexact_balance']['operation_scale'])<=1e-12*max(1.,scale),'operation scale differs')
        for j,c in enumerate(pair):
            if 2*(index-1)+j<len(inner):
                require(c['inner']=={k:v for k,v in inner[2*(index-1)+j].items() if k!='identity'},'PC inner ledger differs')
        audit=row['inexact_balance'].get('audit')
        if index==1 or index%32==0:require(audit is not None,'scheduled balance audit missing')
        if audit is not None:audit_rows.append(audit)
    require(len(exits)==1,'one terminal balance audit required')
    if exits and pcs:
        require(exits[0]['last_PC']==len(pcs),'exit audited wrong PC')
        require(exits[0]['audit'] is not None,'terminal audit absent')
        if exits[0]['audit'] is not None:audit_rows.append(exits[0]['audit'])
    for row in audit_rows:
        scale=row['operation_scale'];numerator=row['closure_norm']
        relative=numerator/scale if scale else (0. if numerator==0 else float('inf'))
        require(math.isfinite(relative) and 0<=relative<=1e-8,'inexact balance failed closure')
        require(abs(relative-row['closure_relative'])<=1e-12,'closure raw/reported mismatch')
    actual=summary['recursive_solve'];totals=actual['inexact_audit']
    solve=summary['solve']
    require(solve['pc_apply_count']==len(pcs),'outer PC count mismatch')
    require(solve['restart']==32 and solve['max_it']==2048 and solve['zero_start'],'outer frozen contract changed')
    def equal(a,b):return math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-12)
    for key,value in actual['counts'].items():
        require(equal(value,sum(row['recursive_counts'].get(key,0) for row in pcs)),
                'PC increment total mismatch: '+key)
    for key,inner_key in (('A4_matvec','A4_matvec'),('explicit_A4','explicit_A4'),('B4','B4_calls')):
        require(actual['counts'][key]==sum(row[inner_key] for row in inner),'inner total mismatch: '+key)
    for key,value in actual['p2_counts'].items():
        require(value==sum(row['p2_counts'].get(key,0) for row in pcs),'p2 PC total mismatch: '+key)
        require(value==sum(row['p2_counts'].get(key,0) for row in inner),'p2 inner total mismatch: '+key)
    require(actual['counts']['H4']==actual['counts']['B4'] and
            actual['counts']['H4_positive']==2*actual['counts']['H4'],'H4 count mismatch')
    require(actual['counts']['H6']==len(pcs) and actual['counts']['H6_positive']==2*len(pcs),'H6 count mismatch')
    for key in ('audits','extra_A6','extra_PH','extra_A6_seconds','extra_PH_seconds','audit_seconds'):
        require(equal(totals[key],sum(row['audit_costs'][key] for row in pcs)+
            sum(row['costs'][key] for row in exits)),'audit total mismatch: '+key)
    require(totals['audits']==totals['extra_A6']==totals['extra_PH']==len(audit_rows),'extra audit action accounting mismatch')
    require(actual['counts']['I4']==len(inner),'I4 total mismatch')
    require(actual['p2_counts']['logical']==sum(r['p2_counts']['logical'] for r in pcs),'p2 logical total mismatch')
    require(actual['storage']==summary['profile']['storage'],'recursive storage contract differs')
    bottom=actual['bottom']
    require(bottom['rows']<=8192 and bottom['derived_matrix_plus_reported_factor_budget_bytes']<=512*1024**2,'p2 bottom limit exceeded')
    return dict(passed=not errors,errors=errors,inner_target_reached=reached,inner_calls=len(inner),
                complete_PC=len(pcs),audits=len(audit_rows),target_miss_is_correctness_failure=False)
