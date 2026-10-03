"""Cached certificates only: never load factors or call the physical action."""
import numpy as np
from src.solvers.neural_fe_action_packet import array_hash

EXPECTED = dict(actions=36, factor_readers=7, joint_lu_solve=4,
    outer_lu_solve=24, explicit_triangular_pass=56, thin_decompositions=2,
    port_factors=1, port_solves=35, port_rhs_columns=35,
    new_assemblies=0, new_LU_attempts=0, new_gecon=0)
BLOCKS = ('J', 0, 1, 2, 3, 4, 6)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def finite(value, label):
    require(type(value) in (int, float) and np.isfinite(value) and value >= 0,
            'finite nonnegative certificate: '+label)
    return float(value)


def error_ratio(error, scale):
    return error/scale if scale else (0. if error == 0 else float('inf'))


def scalar(actual, reported, label, limit=1e-11):
    reported = finite(reported, label)
    require(abs(actual-reported) <= limit*max(1., abs(actual)), label+' differs')


def pair_certificate(cert, label, left=None, right=None, limit=1e-10):
    for key in ('error_norm', 'operation_scale', 'operation_relative'):
        finite(cert[key], label+'.'+key)
    relative = error_ratio(cert['error_norm'], cert['operation_scale'])
    scalar(relative, cert['operation_relative'], label+'.ratio')
    require(relative <= limit, label+' unsafe')
    if left is not None:
        scalar(float(np.linalg.norm(left-right)), cert['error_norm'], label+'.error')
        scalar(float(np.linalg.norm(left)+np.linalg.norm(right)), cert['operation_scale'], label+'.scale')


def factor_sources(setup, prior, plan):
    out = {}
    for b in BLOCKS:
        item = (dict(matrix=prior['matrix'], **prior['factor_inventory']) if b == 'J'
                else setup['block_inventory'][b])
        rows = (sorted(set(setup['block_inventory'][5]['rows']+
                           setup['block_inventory'][7]['rows'])) if b == 'J' else item['rows'])
        require(rows == sorted(set(rows)) and bool(rows), 'factor canonical row inventory')
        out[str(b)] = dict(source_sha=plan['v26_source_sha'] if b == 'J' else plan['upstream_source_sha'],
            rows_sha256=array_hash(np.asarray(rows, np.int64)), row_count=len(rows),
            files={k: item[k] for k in ('matrix', 'LU', 'pivots')})
    return out


def complete_consumption(result, plan, sources, ledger, manifest):
    require(result['budget_counts'] == EXPECTED, 'complete fixed consumption differs')
    require(result['action_counts'] == dict(S=34, SH=2, audit=0), 'complete S/SH inventory')
    records = result['factor_reloads']
    require(len(records) == 7 and {x['block'] for x in records} == set(BLOCKS),
            'missing/duplicate/wrong factor bundle')
    for row in records:
        b = row['block']; expected = sources[str(b)]
        factor_reload_certificate(row, expected)
    ports = result['port_rhs_inventory']
    require(len(ports) == 35 and sum(x['adjoint'] is True for x in ports) == 2,
            'port solve/adjoint inventory')
    require(all(type(x['adjoint']) is bool and x['shape'] == [40] and
                x['RHS_columns'] == 1 for x in ports), 'complete 40-port single RHS shape')
    require(ledger is not None and manifest is not None, 'missing durable ledger/manifest')
    require(ledger['active'] is None and len(ledger['runs']) == 1, 'unsettled/ambiguous ledger')
    run = ledger['runs'][0]
    require(run['exact_counts'] is True and run['classification'] == 'COMPLETED' and
            run['directory'] == result['run_directory'] and run['source_sha'] == result['source_sha'],
            'durable run/source identity')
    require(all(x == EXPECTED for x in (run['counts'],run['completed'],run['upper'],ledger['charged'],
                                        manifest['completed_budget_counts'])), 'durable counts disagree')
    require(manifest['completed_action_counts'] == result['action_counts'] and
            manifest['source_sha'] == result['source_sha'] and
            manifest['input_sha256'] == result['input_sha256'] and
            manifest['plan_sha256'] == result['plan_sha256'], 'manifest source/input/consumption identity')


def flow_certificates(row, a, r, qj, ids, W9):
    n = len(r); inside = np.zeros(n, bool); inside[ids] = True
    require(qj.shape == (n,) and np.isfinite(qj).all(), 'qJ inventory')
    require(not np.count_nonzero(qj[~inside]) and not np.count_nonzero(a['w'][inside]) and
            not np.count_nonzero(a['feedback'][~inside]), 'J/outer support differs')
    scalar(float(np.linalg.norm(r)), row['residual_norm'], 'actual input residual norm')
    identity=row['identity']
    require(identity['exact_trace_port_z_concat'] is True and identity['homogeneous_direction'] is True and
            identity['internal_particular_added'] is False, 'state identity/recovery claim')
    for k,limit in [('saved_trace_residual_full_b_relative',1e-11),('saved_full_residual_full_b_relative',1e-11),
                    ('port_reclosure_operation_relative',1e-10),('port_residual_full_b_relative',1e-10)]:
        require(finite(identity[k],k)<=limit,'state identity threshold '+k)
    err = float(np.linalg.norm(a['return_direction']-qj-a['direction']))
    scale = float(np.linalg.norm(qj)+np.linalg.norm(a['direction']))
    require(error_ratio(err,scale) <= 1e-10, 'qret != hash-bound qJ+d')
    scales = row['action_operation_scales']
    require(set(scales) == {'w','d','feedback','qret'}, 'action operand scale inventory')
    for key, value in scales.items(): finite(value, 'action scale '+key)
    require(row['scale_provenance']['method'] == 'cell_S_expand_plus_C_port_bound' and
            row['scale_provenance']['scales'] == scales and
            row['scale_provenance']['old_scales'] == row['old_operation_scales'] and
            row['scale_provenance']['action_sha256'] == row['operator_action_sha256'],
            'operation scale provenance differs')
    operands=row['scale_provenance']['operands']
    require(set(operands)==set(scales),'bound operand certificate inventory')
    for key,member in [('w','w'),('d','direction'),('feedback','feedback'),('qret','return_direction'),('qj',None)]:
        cert=row['scale_provenance']['qj'] if key=='qj' else operands[key]
        vector=qj if member is None else a[member]
        require(cert['input_array_sha256']==array_hash(vector),'scale input vector hash '+key)
        weights=np.asarray(cert['weights']);norms=np.asarray(cert['expanded_cell_norms'])
        require(weights.ndim==norms.ndim==1 and weights.shape==norms.shape and len(weights)>0 and
                np.isfinite(weights).all() and np.isfinite(norms).all() and np.all(weights>=0) and np.all(norms>=0),
                'finite cell operand bound '+key)
        value=float(weights@norms+finite(cert['C_norm'],'C norm')*finite(cert['closed_port_norm'],'closed port norm'))
        scalar(value,cert['value'],'bound operand value '+key)
        scalar(value,row['old_operation_scales'][-1] if key=='qj' else scales[key],'action bound '+key)
    scalar(max(scales['d'],scales['w']+scales['feedback']),row['h_operation_scale'],'innovation scale')
    cert = row['cancellation']; cancel = float(np.linalg.norm(a['image'][ids]))
    scalar(cancel, cert['error_norm'], 'cancellation error')
    scalar(scales['w']+scales['feedback'],cert['operation_scale'],'cancellation operand scale')
    scalar(error_ratio(cancel,cert['operation_scale']),cert['operation_relative'],'cancellation ratio')
    require(cert['operation_relative'] <= 1e-10, 'cancellation unsafe')
    pair_certificate(cert['original_rhs_inner_pair'],'inner RHS',a['return_image'][ids],r[ids])
    pair_certificate(cert['d_linearity'],'d linearity',a['image'],a['feedback_image']-a['aw'])
    pair_certificate(cert['return_linearity'],'return linearity',a['return_image'],W9[:,-1]+a['image'])
    scalar(float(np.linalg.norm(a['aw'][ids])),cert['pre_cancel_Aw_inner_norm'],'pre-cancel aw')
    scalar(float(np.linalg.norm(a['feedback_image'][ids])),cert['pre_cancel_feedback_inner_norm'],'pre-cancel feedback')
    require(a['cached_joint_image'].shape==(n,) and a['cached_joint_inner_image'].shape==(len(ids),) and
            np.isfinite(a['cached_joint_image']).all() and np.isfinite(a['cached_joint_inner_image']).all(),
            'cached original/J witness array inventory')
    pair_certificate(row['cached_original_pair'],'cached qJ original',a['cached_joint_image'],W9[:,-1])
    pair_certificate(row['cached_joint_inner_pair'],'cached J principal',a['cached_joint_inner_image'],r[ids])
    recomb = row['independent_recombination']
    thin = r-W9@a['coefficients'][:9]-a['coefficients'][9]*a['image']
    re = float(np.linalg.norm(a['original_combination_image']-(r-thin)))
    op = float(abs(a['coefficients'][:9])@np.asarray(row['old_operation_scales'])+
               abs(a['coefficients'][9])*row['h_operation_scale'])
    for key,value in [('full_b_relative',re/row['full_b_norm']),('current_r_relative',re/np.linalg.norm(r)),
                      ('operation_relative',error_ratio(re,op))]:scalar(value,recomb[key],'recombination '+key)
    require(recomb['full_b_relative'] <= 1e-11 and recomb['operation_relative'] <= 1e-10, 'recombination unsafe')


def state_certificate(row, a, state, nt):
    bn = row['full_b_norm']; identity = row['identity']
    for k in ('trace','port','z','residual'):
        require(np.isfinite(state[k]).all(), 'state nonfinite '+k)
    require(state['trace'].shape == (nt,) and state['port'].shape == (40,) and
            state['z'].shape == state['residual'].shape == (nt+40,), 'complete state/port shape')
    require(np.array_equal(state['z'],np.r_[state['trace'],state['port']]) and
            identity['exact_trace_port_z_concat'] is True and identity['homogeneous_direction'] is True and
            identity['internal_particular_added'] is False, 'state concat/homogeneous recovery')
    require(a['audited_full_residual'].shape == (nt+40,) and a['reclosed_port'].shape == (40,) and
            np.isfinite(a['audited_full_residual']).all() and np.isfinite(a['reclosed_port']).all(), 'saved state audit certificate shape')
    checks = [('saved_trace_residual_full_b_relative',float(np.linalg.norm(a['input_residual']-state['residual'][:nt])/bn),1e-11),
              ('saved_full_residual_full_b_relative',float(np.linalg.norm(a['audited_full_residual']-state['residual'])/bn),1e-11),
              ('port_reclosure_operation_relative',float(np.linalg.norm(a['reclosed_port']-state['port'])/(1+np.linalg.norm(state['port']))),1e-10),
              ('port_residual_full_b_relative',float(np.linalg.norm(a['audited_full_residual'][nt:])/bn),1e-10)]
    for k,value,limit in checks:
        scalar(value,identity[k],'state '+k); require(value <= limit,'state audit unsafe '+k)


def factor_reload_certificate(row, expected):
    b=row["block"]
    require(row['source_sha'] == expected['source_sha'] and
            row['rows_sha256'] == expected['rows_sha256'] and
            row['row_count'] == expected['row_count'], 'factor source/rows identity')
    require(row['qualified'] is True and row['refactored'] is False and
            row['solve_calls'] == row['RHS_columns'] == 4 and row['triangular_passes'] == 8,
            'unqualified factor or solve/RHS/pass inventory')
    files = row['files']
    require(len(files) == 3 and {x['key'] for x in files} == {'matrix','LU','pivots'},
            'factor file inventory')
    for f in files:
        ref = expected['files'][f['key']]
        require(f['path'] == ref['path'] and f['container_sha256'] == ref['sha256'] and
                f['array_sha256'] == ref['array_sha256'] and f['readonly'] is True and
                f['full_hash_copy'] is False and f['container_stream_hash_reads'] ==
                f['numeric_mmap_loads'] == f['array_hash_scans'] == 1, 'factor hash/reader seal')
    seeds = (422601,422602) if b == 'J' else (422401+2*b,422402+2*b)
    witnesses = row['witnesses']
    require(len(witnesses) == 2 and [x['seed'] for x in witnesses] == list(seeds), 'factor witness seeds')
    for w in witnesses:
        err = finite(w['solve_error_norm'], 'solve error')
        rn = finite(w['rhs_norm'], 'solve RHS norm'); op = finite(w['solve_operand_scale'], 'solve scale')
        require(rn > 0 and op > 0, 'nonzero witness scale')
        scalar(err/rn, w['solve_relative'], 'solve relative')
        scalar(err/op, w['solve_operation_relative'], 'solve operation relative')
        require(err/rn <= 1e-8 and err/op <= 1e-12, 'failed raw factor solve witness')
        pair_certificate(w['original_principal_action'], 'factor original principal')
        if b == 'J':
            pair_certificate(w['original_adjoint_action'], 'factor original adjoint')
