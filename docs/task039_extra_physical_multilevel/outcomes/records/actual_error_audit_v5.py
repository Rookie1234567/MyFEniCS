"""Saved-only audit: no FE construction, MPI, matrix action or solve."""
import hashlib,json
from pathlib import Path
import numpy as np
from src.runners.physical_diagnostic_completion import load_packet,reuse_v3
from src.runners.actual_error_diagnosis import load_actual_evidence
base=Path('benchmarks/artifacts/task39extra/fine_reference_followup')
root=base/'2251d7d0d3d3e8498ee34d38f8ec70f70d2f0d98';p=root/'actual_errors_v1'
raw=lambda name:json.loads((p/name).read_text())
packet=lambda name:load_packet(p/(name+'.json'))
s=raw('diagnostic_summary.json');w=raw('watchdog/summary.json');launch=raw('launch.json')
inv=Path('docs/task039_extra_physical_multilevel/outcomes/records/nonconvergence_diagnosis_v3.json')
inputs=load_actual_evidence('input/task39extra/actual_error_evidence.json',inv,reuse_v3(json.loads(inv.read_text())))
ref=inputs['reference'];old=inputs['packets'];labels=('A2R160','LIGHT448','JOINT448')
close=lambda x,y:np.testing.assert_allclose(x,y,rtol=1e-12,atol=1e-13)
tables={}
for label in labels:
    e=packet(label+'_actual_error');m=packet(label+'_primal_metrics');proj=packet(label+'_projection')
    close(e['e'],ref['x']-old[label+'_identity']['x'])
    close(e['residual_difference'],old[label+'_identity']['r']-ref['r'])
    diff=e['q']-e['residual_difference'];close(diff,e['closure_vector'])
    relative=float(np.linalg.norm(diff)/e['operation_scale']);close(relative,e['closure_relative_to_operations'])
    close(e['e'],proj['parallel']+proj['perpendicular'])
    close(proj['eta_space'],np.sqrt(proj['perpendicular_energy']/proj['error_energy']))
    close(proj['pythagorean_relative_defect'],abs(proj['error_energy']-proj['parallel_energy']-proj['perpendicular_energy'])/proj['error_energy'])
    cells=packet(label+'_cell_energies')
    close(cells['mass'].sum(),m['energies']['L2_squared']);close(cells['curl'].sum(),m['energies']['scaled_curl_squared'])
    saved={};complements={}
    for name in ('S6','LIGHT','JOINT'):
        v=packet(label+'_saved_'+name);source=old[label+'_'+name];scale=v['normalization_scale']
        close(v['normalized_error'],e['e']/scale);close(v['normalized_old_residual'],old[label+'_identity']['r']/scale)
        close(v['reference_residual_gap'],ref['r']/scale)
        result=next(iter(v['profiles'].values()));z=next(iter(source['profiles'].values()))['correction'];az=result['applied_direction'];q=v['normalized_old_residual']
        alpha=np.vdot(az,q)/np.vdot(az,az) if np.linalg.norm(az) else 0j
        stored_alpha=result['alpha'];stored_alpha=complex(*stored_alpha) if isinstance(stored_alpha,list) else stored_alpha
        if isinstance(stored_alpha,dict):stored_alpha=complex(stored_alpha['real'],stored_alpha['imag'])
        close(alpha,stored_alpha)
        close(result['unit_true_residual_ratio'],np.linalg.norm(q-az)/np.linalg.norm(q))
        close(result['mr_true_residual_ratio'],np.linalg.norm(q-alpha*az)/np.linalg.norm(q))
        close(result['unit_field_ratio'],np.sqrt(result['unit_remaining_energy']/result['original_error_energy']))
        close(result['mr_field_ratio'],np.sqrt(result['mr_remaining_energy']/result['original_error_energy']))
        saved[name]={k:result[k] for k in ('unit_field_ratio','mr_field_ratio','unit_true_residual_ratio','mr_true_residual_ratio','alpha')}
    for name in ('H6','S6_complement'):
        file=p/(label+'_complement_'+name+'.json')
        if file.exists():
            v=packet(file.stem);result=v['profiles'][name];q=v['normalized_q'];az=result['applied_direction']
            close(result['unit_true_residual_ratio'],np.linalg.norm(q-az)/np.linalg.norm(q))
            complements[name]=dict(result={k:result[k] for k in ('unit_field_ratio','mr_field_ratio','unit_true_residual_ratio','mr_true_residual_ratio','alpha')},cost=v['cost'])
    coarse=packet(label+'_coarse') if (p/(label+'_coarse.json')).exists() else {'status':'not_run'}
    gap=None
    if (p/(label+'_coarse_gap.json')).exists():
        gap=packet(label+'_coarse_gap');close(gap['closure_vector'],gap['A4_coarse_difference']+gap['g_perp'])
        close(gap['closure_relative_to_operations'],np.linalg.norm(gap['closure_vector'])/gap['operation_scale'])
        c=coarse['result'];close(c['decomposition_relative_defect'],abs(c['decomposition_left']-c['decomposition_right'])/proj['error_energy'])
    tables[label]=dict(error_identity_relative=relative,relative_primal=m['relative_to_reference'],
        reference_sensitivity=m['reference_correction_over_error'],projection={k:proj[k] for k in ('status','iterations','eta_space','equation_relative_residual','pythagorean_relative_defect')},
        saved_PC=saved,complements=complements,coarse_status=coarse['status'],
        coarse=None if 'result' not in coarse else {k:coarse['result'][k] for k in ('unit_field_ratio','mr_field_ratio','unit_true_residual_ratio','mr_true_residual_ratio','decomposition_relative_defect')},
        gap=None if gap is None else {k:gap[k] for k in ('closure_relative_to_operations','gap_over_complement_field_ratio','closure_checks')})
p4_residuals=[]
for i,label in enumerate((*labels,'actual_range_identity'),1):
    prefix=(label+'_coarse' if i<4 else label)+f'_p4_{i:02d}'
    rhs=packet(prefix+'_input');action=packet(prefix+'_actions_0')
    residual=rhs['g']-action['A4y']
    relative=float(np.linalg.norm(residual)/np.linalg.norm(rhs['g']))
    close(relative,s['reference_records'][i-1]['final_true_residual'])
    assert relative<=1e-10
    p4_residuals.append(dict(label=label,relative=relative,limit=1e-10,refinements=0))
samples=[json.loads(line) for line in (p/'watchdog/resources.jsonl').read_text().splitlines()]
violations=[]
for i,r in enumerate(samples):
    env=r['memory_envelope']
    if not r['all_status_readable'] or r['swap_bytes'] or r['rss_bytes']>=r['launch_cap_bytes'] or env['effective_available_bytes']<env['reserve_bytes'] or env['reserve_bytes']<4294967296 or r['launch_cap_bytes']>12_000_000_000:violations.append(i)
assert not violations
assert len(samples)==w['samples']
assert max(r['rss_bytes'] for r in samples)==w['sampled_process_tree_rss_peak_bytes']
assert not s['cleanup_errors'] and not w['remaining_child_pids'] and w['descendants_cleared']
pids=sorted(set([json.loads((root/'parent_pid.json').read_text())['parent_pid']]+w['observed_child_pids']))
assert not [pid for pid in pids if Path('/proc',str(pid)).exists()]
assert s['complete_pc_calls']==0 and s['independent_smoother_attempted']<=6 and s['independent_smoother_calls']<=s['independent_smoother_attempted']
assert s['logical_p4_rhs']<=4 and s['external_MatSolve_calls']<=12 and s['projection_seconds']<=1801
assert launch['interval']['budget_seconds']<=5400 and not launch['cache_before']
hashes=[dict(path=str(f),bytes=f.stat().st_size,sha256=hashlib.sha256(f.read_bytes()).hexdigest()) for f in sorted(root.rglob('*')) if f.is_file()]
result=dict(audit_status='SAVED_ONLY_AUDIT_PASSED',worker_status=s['status'],launch_classification=launch['classification'],
    source_sha=root.name,tables=tables,closure_checks=s['closure_checks'],reference_records=s.get('reference_records'),
    p4_native_residuals=p4_residuals,counts={k:s[k] for k in ('complete_pc_calls','independent_smoother_attempted','independent_smoother_calls','logical_p4_rhs','external_MatSolve_calls')},
    projection_seconds=s['projection_seconds'],timings=s['timings'],charged_seconds=launch['interval']['budget_seconds'],
    samples=len(samples),resource_violations=violations,peak_rss_bytes=w['sampled_process_tree_rss_peak_bytes'],
    minimum_available_bytes=min(r['memory_envelope']['effective_available_bytes'] for r in samples),global_swap_activity=w['global_swap_activity'],
    checked_pids=pids,present_pids=[],artifact_hashes=hashes,
    audit_scope='Saved q/Az/vector differences and scalar identities independently recomputed; e L2/curl totals checked against owned-cell integrals. Projection and remaining-field M0 values are measured hash-bound scalars, no fresh M0/A6 actions. No continuum or strict forward error bound.')
(base/'actual_errors_v1_formal_audit.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k not in ('artifact_hashes','timings','reference_records')},indent=2))
print('hashed artifacts',len(hashes))
