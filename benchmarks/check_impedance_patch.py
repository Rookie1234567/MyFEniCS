"""Recompute saved patch/PC claims without a factor or another PDE."""
import numpy as np

from src.solvers.scattering_anchor import relative
from src.solvers.scattering_anchor_checks import checked_arrays
from src.solvers.bounded_trace_pc import csr_load


def patch_witness(values, matrix):
    required=('input','matrix_action','independent','body','surface','excluded_outside_body')
    if any(k not in values for k in required): raise ValueError('patch witness inventory')
    n=matrix.shape[0]
    if matrix.shape!=(n,n) or any(values[k].shape!=(n,) for k in required):
        raise ValueError('patch witness shape')
    if any(not np.isfinite(values[k]).all() for k in required): raise ValueError('patch witness finite')
    actual=matrix@values['input']
    r=dict(matrix_saved_action=relative(actual-values['matrix_action'],actual),
        independent_operation=relative(actual-values['independent'],values['independent']),
        body_surface_sum=relative(values['body']+values['surface']-values['independent'],values['independent']),
        excluded_outside_norm=float(np.linalg.norm(values['excluded_outside_body'])))
    r['pass_gate']=max(r[k] for k in ('matrix_saved_action','independent_operation','body_surface_sum'))<=1e-10 and r['excluded_outside_norm']>0
    return r


def saved_preparation_check(scope):
    prep=scope.stage('PREPARE');old=scope.parent_preparation();q=scope.stage('PRECHECK')
    maps=checked_arrays(old['patch_arrays']);rows=[]
    if len(prep['records'])!=38 or prep['patch_arrays']['sha256']!=old['patch_arrays']['sha256']:
        raise ValueError('new impedance partition inventory')
    for j,r in enumerate(prep['records']):
        cells=np.asarray(r['details']['body_cell_ids'])
        if (r['index']!=j or not np.array_equal(cells,maps[f'{j}_halo_cells'])
                or r['details']['body_cells_outside_halo']!=0
                or r['details']['rows']!=len(maps[f'{j}_ids'])):
            raise ValueError('halo-only exact saved body inventory')
        rows.append(dict(index=j,halo_cells=len(cells),rows=r['details']['rows'],nnz=r['details']['nnz']))
    pair=[]
    for r in q['patch_checks']:
        j=r['index'];vals=checked_arrays(r['arrays']);A=csr_load(prep['matrices'][j])
        check=patch_witness(vals,A)
        if not check['pass_gate']: raise ValueError('saved independent impedance matrix action')
        pair.append(dict(index=j,**check,q13_q15_per_face_producer_maximum=r['q13_q15_maximum'],
            q13_q15_independent_check='whole new q13 CSR against saved PUBLIC_BASIX/q15 body and surface'))
    total=sum(r['double_bytes'] for r in prep['analysis'])+prep['coarse_symbolic']['double_bytes']
    if total!=prep['double_symbolic_total_bytes'] or total>80*2**30:
        raise ValueError('new impedance symbolic inventory cap')
    return dict(pass_gate=True,patches=rows,independent_patch_pairs=pair,
        new_double_symbolic_total_bytes=total,global_fine_matrix_reads=0,new_numeric_factors=0)
