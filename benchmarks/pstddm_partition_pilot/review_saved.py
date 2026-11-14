"""Read-only sparse/matvec review of saved PSTDDM outputs; no PDE or factorization."""
import argparse
import datetime
import gc
import hashlib
import json
import os
from pathlib import Path
import resource
import shutil
import sys
import time

import numpy as np
from scipy import sparse

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--repository',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--profile',choices=('cloud','workstation'),default='cloud')
parser.add_argument('--results-root',type=Path)
parser.add_argument('--scope-root',type=Path)
parser.add_argument('--case',action='append',dest='cases')
args=parser.parse_args()
ROOT = args.repository.resolve()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from benchmarks.pstddm_partition_pilot.workstation_review import review_saved_n2_pair

PROFILE = args.profile
SCOPE_ROOT = args.scope_root.resolve() if args.scope_root else None
BASE = (args.results_root.resolve() if PROFILE=='workstation' and args.results_root
        else ROOT/'benchmarks/artifacts/pstddm_partition_pilot')
OUT = args.output.resolve()
if PROFILE=='cloud':
    assert not OUT.is_relative_to(BASE), 'Review output must not modify frozen run artifacts'
else:
    if args.results_root is None or SCOPE_ROOT is None or not BASE.is_relative_to(SCOPE_ROOT):
        parser.error('workstation review requires results-root and scope-root below the task root')
    if not OUT.is_relative_to(SCOPE_ROOT) or OUT.is_relative_to(BASE):
        parser.error('workstation review output must be below scope-root and outside frozen runs')
    if not args.cases:
        parser.error('workstation review requires one or more --case IDs')
G = 1 << 30
START = time.monotonic()
GUARDS = []


def guard(label, extra=64 << 20):
    mem = {k: int(v.split()[0])*1024 for k, v in (x.split(':', 1) for x in Path('/proc/meminfo').read_text().splitlines())}
    status = dict(x.split(':', 1) for x in Path('/proc/self/status').read_text().splitlines() if ':' in x)
    rss = int(status['VmRSS'].split()[0])*1024
    entry = {'stage': label, 'rss': rss, 'extra': extra, 'available': mem['MemAvailable']}
    GUARDS.append(entry)
    if PROFILE=='cloud':
        assert rss+extra+(512 << 20)<2*G
        assert mem['MemAvailable']>max(2.5*G, extra+1.5*G)
        assert mem['MemTotal']-mem['MemAvailable']+extra+(512 << 20)<6*G
        assert mem['SwapTotal']-mem['SwapFree']==0 and int(status.get('VmSwap', '0 kB').split()[0])==0
        assert shutil.disk_usage(BASE).free>12*G
        assert time.monotonic()-START<300
    else:
        cgroup=Path('/sys/fs/cgroup')
        relative=next(line.split(':',2)[2] for line in Path('/proc/self/cgroup').read_text().splitlines()
                      if line.startswith('0::'))
        group=(cgroup/relative.lstrip('/')).resolve()
        current=int((group/'memory.current').read_text())
        maximum=int((group/'memory.max').read_text())
        swap_current=int((group/'memory.swap.current').read_text())
        swap_max=int((group/'memory.swap.max').read_text())
        assert rss+extra+(512<<20)<=8_000_000_000
        assert current+extra+(512<<20)<=maximum==8_000_000_000
        assert swap_current==swap_max==0 and int(status.get('VmSwap','0 kB').split()[0])==0
        assert mem['MemAvailable']>=400*G
        assert shutil.disk_usage(SCOPE_ROOT).free>=400_000_000_000
        assert time.monotonic()-START<1800


def read(path):
    return json.loads(path.read_text())


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def relative(value, reference):
    return float(np.linalg.norm(value-reference)/max(np.linalg.norm(reference), np.finfo(float).tiny))


def sparse_difference(actual, expected):
    delta = (actual-expected).tocsr()
    delta.eliminate_zeros()
    return {'relative_frobenius': float(np.linalg.norm(delta.data)/max(np.linalg.norm(expected.data), np.finfo(float).tiny)),
            'maximum_absolute': float(np.max(np.abs(delta.data), initial=0)), 'nonzero_difference': delta.nnz}


def sparse_identity(matrix):
    value=matrix.tocsr(copy=True)
    value.sum_duplicates()
    value.sort_indices()
    value.eliminate_zeros()
    h=hashlib.sha256(json.dumps(value.shape).encode())
    for data in [value.indptr.astype(np.int64),value.indices.astype(np.int64),value.data.astype(np.complex128)]:
        h.update(data.tobytes())
    return h.hexdigest()


def independent_transform(mpc, size):
    slaves = mpc['slaves']
    free = np.setdiff1d(np.arange(size), slaves)
    lookup = {int(row): col for col, row in enumerate(free)}
    rows, cols, vals = free.tolist(), list(range(len(free))), [1+0j]*len(free)
    for slave in slaves:
        a, b = mpc['coefficient_offsets'][slave:slave+2]
        j, k = mpc['master_offsets'][slave:slave+2]
        masters, coeffs = mpc['masters'][j:k], mpc['coefficients'][a:b]
        assert len(masters)==len(coeffs) and all(int(m) in lookup for m in masters)
        rows.extend([int(slave)]*len(masters))
        cols.extend(lookup[int(m)] for m in masters)
        vals.extend(coeffs)
    return sparse.csr_matrix((vals, (rows, cols)), shape=(size, len(free)))


def check_case(name):
    p = BASE/name
    guard(name+'_before_read', 256 << 20)
    summary, manifest, supervision = (read(p/x) for x in ['run_summary.json', 'run_manifest.json', 'supervision.json'])
    artifact_manifest = read(p/'artifact_hashes.json')
    for file, spec in artifact_manifest.items():
        assert digest(p/file)==spec['sha256'] and (p/file).stat().st_size==spec['bytes'], file
    modes = read(p/'mode_manifest.json')['modes']
    keys = [(m['side'], m['m'], m['n'], m['polarization']) for m in modes]
    expected = {(side, m, n, pol) for side in ['top','bottom'] for m in range(-5,6) for n in range(-9,10) for pol in ['s','p']}
    assert len(keys)==836 and set(keys)==expected
    cfg = read(p/'resolved_config.json')['global']
    assert cfg['lambda0']==.7 and cfg['nedelec_degree']==2 and cfg['mesh_axis_cell_counts']==[3,10,4]
    assert cfg['incident_theta_deg']==89 and cfg['incident_phi_deg']==90 and cfg['use_floquet_xy']
    matrices = {file: sparse.load_npz(p/(file+'.npz')).tocsr() for file in ['raw_A','raw_C','raw_D','A','C','D','T','full','mass','curl_gram']}
    T, full = matrices['T'], matrices['full']
    mpc = dict(np.load(p/'raw_mpc.npz', allow_pickle=False))
    Ti = independent_transform(mpc, T.shape[0])
    assert (Ti-T).nnz==0
    n = T.shape[1]
    assert T.shape==(3570,3120) and full.shape==(3956,3956) and len(mpc['slaves'])==450
    guard(name+'_operator_identity',128 << 20)
    operator_differences = {
        'A': sparse_difference(matrices['A'], Ti.conj().T@matrices['raw_A']@Ti),
        'C': sparse_difference(matrices['C'], Ti.conj().T@matrices['raw_C']),
        'D': sparse_difference(matrices['D'], matrices['raw_D']@Ti),
        'full': sparse_difference(full, sparse.bmat([[matrices['A'],matrices['C']],
                     [matrices['D'],sparse.eye(836,dtype=complex)]],format='csr'))}
    assert all(x['relative_frobenius']<1e-13 for x in operator_differences.values())
    rhs, f, g = (np.load(p/file,allow_pickle=False) for file in ['rhs.npy','raw_f.npy','raw_aux_rhs.npy'])
    rhs_identity = relative(np.r_[Ti.conj().T@f,g],rhs)
    assert rhs_identity<1e-12
    ref_path = p if (p/'reference_solution.npz').exists() else BASE/'direct_p2_v1'
    reference = np.load(ref_path/'reference_solution.npz',allow_pickle=False)['z']
    payload = dict(np.load(ref_path/'reference_fields.npz',allow_pickle=False))
    e_ref = reference[:n]
    m, k = matrices['mass'], matrices['curl_gram']
    divisor = float(payload['H_curl_norm_divisor'])
    ref_enorm = float(np.real(np.vdot(e_ref,m@e_ref)+2*np.vdot(e_ref,payload['m_bg']).real+payload['background_E_l2_squared']))
    ref_hnorm = float(np.real(np.vdot(e_ref,k@e_ref)+2*np.vdot(e_ref,payload['k_bg']).real+payload['background_curl_l2_squared']))/divisor
    ref_scattered_enorm=float(np.vdot(e_ref,m@e_ref).real)
    ref_scattered_hnorm=float(np.vdot(e_ref,k@e_ref).real)/divisor
    assert min(ref_enorm,ref_hnorm)>0
    ref_diag=read(ref_path/'reference_diagnostics.json')
    assert np.isclose(ref_enorm,ref_diag['E_total_l2_squared'],rtol=1e-10)
    assert np.isclose(ref_hnorm,ref_diag['H_total_l2_squared'],rtol=1e-10)
    assert np.array_equal(payload['scattered_E_independent'],e_ref)
    assert np.array_equal(payload['scattered_E_original'],Ti@e_ref)
    def solution(z):
        e, q = z[:n], z[n:]
        u = Ti@e
        raw_res = matrices['raw_A']@u+matrices['raw_C']@q-f
        aux_res = matrices['raw_D']@u+q-g
        full_res = float(np.linalg.norm(full@z-rhs)/np.linalg.norm(rhs))
        original_res = float(np.linalg.norm(np.r_[Ti.conj().T@raw_res,aux_res])/np.linalg.norm(rhs))
        constraint = 0.
        for slave in mpc['slaves']:
            a,b=mpc['coefficient_offsets'][slave:slave+2]
            j,l=mpc['master_offsets'][slave:slave+2]
            constraint=max(constraint,float(abs(u[slave]-np.dot(mpc['coefficients'][a:b],u[mpc['masters'][j:l]]))))
        delta=e-e_ref
        e2=float(np.vdot(delta,m@delta).real)
        h2=float(np.vdot(delta,k@delta).real)/divisor
        assert min(e2,h2)>-1e-20
        return {'full_true_residual':full_res,'original_projected_true_residual':original_res,
                'auxiliary_absolute_residual':float(np.linalg.norm(aux_res)), 'MPC_maximum_absolute':constraint,
                'E_total_relative_L2':float(np.sqrt(max(e2,0)/ref_enorm)),
                'H_total_relative_L2':float(np.sqrt(max(h2,0)/ref_hnorm)),
                'E_scattered_relative_L2':float(np.sqrt(max(e2,0)/ref_scattered_enorm)),
                'H_scattered_relative_L2':float(np.sqrt(max(h2,0)/ref_scattered_hnorm)),
                'full_coefficient_relative_difference':relative(z,reference)}
    results={'reference':solution(reference)}
    assert results['reference']['full_true_residual']<=1e-10
    assert results['reference']['original_projected_true_residual']<=1e-10
    if (p/'candidate_solution.npz').exists():
        solutions=dict(np.load(p/'candidate_solution.npz',allow_pickle=False))
        saved_fields=np.load(p/'candidate_fields.npz',allow_pickle=False)
        assert np.array_equal(saved_fields['scattered_E_independent'],solutions['z'][:n])
        assert np.array_equal(saved_fields['scattered_E_original'],Ti@solutions['z'][:n])
        saved_fields.close()
        results['initial']=solution(solutions['x0'])
        results['final']=solution(solutions['z'])
        for label in ['initial','final']:
            assert results[label]['MPC_maximum_absolute']<1e-10
        expected_pass=(results['final']['original_projected_true_residual']<=1e-8 and
                       results['final']['full_true_residual']<=1e-8 and
                       results['final']['E_total_relative_L2']<=1e-4 and
                       results['final']['H_total_relative_L2']<=1e-3)
        assert bool(summary['result']['same_discrete_solver_pass'])==expected_pass
        results['same_discrete_pass']=expected_pass
        assert np.isclose(summary['result']['final_true_residual'],results['final']['full_true_residual'],rtol=1e-10,atol=1e-15)
        if (p/'manufactured_expected.npy').exists():
            exact=np.load(p/'manufactured_expected.npy',allow_pickle=False)
            results['manufactured_reference_difference']=relative(reference,exact)
            results['manufactured_final_difference']=relative(solutions['z'],exact)
            assert results['manufactured_reference_difference']<1e-9
        del solutions
    samples, stages = read(p/'resource_samples.json'),read(p/'phase_gates.json')
    def facts_ok(s):
        return (s['available']>2.5*G and s['system_used']+(512<<20)<6*G and
                s['swap_used']==s['pswpin']==s['pswpout']==0 and s['disk_free']>12*G+(256<<20))
    resource_ok=all(facts_ok(s) and s['rss']+(512<<20)<2*G and all(r['swap']==0 for r in s['processes']) for s in samples)
    assert resource_ok and facts_ok(supervision['initial']) and facts_ok(supervision['final'])
    total_memory=supervision['initial']['available']+supervision['initial']['system_used']
    assert all(s['rss_bytes']+s['planned_extra_bytes']+(512<<20)<2*G and
               s['available_bytes']>max(2.5*G,s['planned_extra_bytes']+1.5*G) and
               total_memory-s['available_bytes']+s['planned_extra_bytes']+(512<<20)<6*G for s in stages)
    assert supervision['returncode']==0 and supervision['stop_reason'] is None and supervision['remaining']==[]
    assert supervision['wall_seconds']<1800
    peak=max(s['rss'] for s in samples)
    assert peak==supervision['peak_sampled_tree_rss']
    output=sum(f.stat().st_size for f in p.rglob('*') if f.is_file())
    assert output==supervision['output_bytes'] and output<256<<20
    partition=read(p/'partition_audit.json') if (p/'partition_audit.json').exists() else None
    if partition:
        assert partition['mass_partition_relative']<1e-12 and partition['reconstruction_relative']<1e-10
        for pair in partition['pairs']:
            assert pair['phase_map_error']<1e-11 and pair['local_residual']<1e-9
            assert all(x<1e-11 for x in pair['weak_product_errors'])
        if partition['partition_count']==2:
            pair_map=sparse.load_npz(p/'pair0_map.npz')
            local=sparse.load_npz(p/'pair0_L.npz')
            compare=sparse_difference(pair_map.T@local@pair_map,matrices['A']-matrices['C']@matrices['D'])
            assert compare['relative_frobenius']<1e-12
            results['independent_N2_original_operator']=compare
            del pair_map,local
        applications=summary['result']['pc_applications']
        assert len(applications)==summary['result']['FGMRES']['iterations']+1
        assert all(x['partition_lifting_relative_residual']<1e-10 for x in applications)
        assert all(x>0 for x in applications[0]['original_layer_source_norms'])
        results['first_original_layer_source_norms']=applications[0]['original_layer_source_norms']
        results['iterations']=summary['result']['FGMRES']['iterations']
        results['initial_pc_seconds']=summary['result']['first_double_sweep_seconds']
        results['factor_inventory']=partition
    item={'case':name,'source_sha':manifest['source_sha'],'physical_sha256':manifest['physical_sha256'],
          'mode_order_sha256':hashlib.sha256(json.dumps(keys,separators=(',',':')).encode()).hexdigest(),
          'artifact_hashes_verified':len(artifact_manifest),'operator_differences':operator_differences,
          'RHS_projection_relative_difference':rhs_identity,'independent_MPC_transform_exact':True,
          'reference_squared_norms':{'E_total':ref_enorm,'H_total':ref_hnorm,
             'E_scattered':ref_scattered_enorm,'H_scattered':ref_scattered_hnorm},
          'solutions':results,'whole_case_wall_seconds':supervision['wall_seconds'],'peak_sampled_tree_rss':peak,
          'samples':len(samples),'output_bytes':output,'all_resource_samples_and_stage_gates_pass':True,
          'diagnostics':summary['result'].get('diagnostic_absolute_differences'),
          'array_hashes':{name:sparse_identity(matrices[name]) for name in ['A','C','D','T','mass','curl_gram','full']},
          'rhs_sha256':digest(p/'rhs.npy')}
    del matrices,T,Ti,full,mpc,reference,payload,m,k,samples,stages
    gc.collect()
    guard(name+'_complete')
    return item


def check_workstation_case(name):
    p=BASE/name
    guard(name+'_before_read',256<<20)
    summary,manifest,supervision=(read(p/x) for x in ('run_summary.json','run_manifest.json','supervision.json'))
    artifact_manifest=read(p/'artifact_hashes.json')
    for filename,spec in artifact_manifest.items():
        file=p/filename
        assert file.is_file() and file.stat().st_size==spec['bytes'] and digest(file)==spec['sha256'],filename
    assert manifest['runtime_profile']=='native_linux'
    assert supervision['status']=='COMPLETED_PROCESS_REVIEW_PENDING'
    assert supervision['returncode']==0 and supervision['stop_reason'] is None
    assert supervision['remaining_descendants']==[] and supervision['final_cgroup_swap_current_bytes']==0
    assert supervision['wall_seconds']<=1800
    runtime=read(p/'runtime_receipt.json')
    identity=read(p/'supervisor_identity.json')
    assert runtime['runtime_profile']=='native_linux'
    assert identity['cgroup_path']==runtime['active_cgroup_path']
    assert identity['cgroup_path']!=runtime['preparation_cgroup']['path']
    metadata=read(p/'mode_manifest.json')
    modes=metadata['ordered_mode_records']
    mode_keys=[(m['side'],int(m['m']),int(m['n']),m['polarization']) for m in modes]
    assert len(mode_keys)==manifest['auxiliary_rows']==metadata['mode_count']
    assert len(set(mode_keys))==len(mode_keys)
    mmax,nmax=metadata['selected_m_max'],metadata['selected_n_max']
    expected={(side,m,n,pol) for side in ('top','bottom') for m in range(-mmax,mmax+1)
              for n in range(-nmax,nmax+1) for pol in ('s','p')}
    assert set(mode_keys)==expected
    assert metadata['propagating_mode_count']+metadata['evanescent_mode_count']==len(modes)
    assert metadata['rayleigh_warning_mode_count']==sum(bool(m['rayleigh_warning']) for m in modes)
    assert metadata['auto_max_m']+metadata['order_padding']==mmax
    assert metadata['auto_max_n']+metadata['order_padding']==nmax
    assert metadata['C_sha256']==manifest['C_sha256'] and metadata['D_sha256']==manifest['D_sha256']
    cfg=read(p/'global_config.json')
    assert cfg['lambda0']==manifest['wavelength_nm'] and cfg['nedelec_degree']==2
    assert cfg['period_x']==cfg['period_y']==50.0 and cfg['mesh_axis_cell_counts']==[4,4,16]
    z_axis=cfg.get('mesh_axis_z_values')
    if z_axis is None:z_axis=cfg.get('mesh_axis_z_values_requested')
    assert z_axis is not None and len(z_axis)==17
    assert np.isclose(z_axis[0],-10.0) and np.isclose(z_axis[1],0.0)
    assert np.isclose(z_axis[-2],120.0) and np.isclose(z_axis[-1],130.0)
    assert not cfg['use_pml'] and cfg['incident_theta_deg']==89.0 and cfg['incident_phi_deg']==90.0
    arrays={key:sparse.load_npz(p/f'{key}.npz').tocsr() for key in
            ('raw_A','raw_C','raw_D','A','C','D','T','full','mass','curl_gram')}
    T,full=arrays['T'],arrays['full'];n=T.shape[1];m=len(modes)
    mpc=dict(np.load(p/'raw_mpc.npz',allow_pickle=False))
    Ti=independent_transform(mpc,T.shape[0])
    assert (Ti-T).nnz==0 and full.shape==(n+m,n+m)
    assert n==manifest['independent_FE_rows'] and T.shape[0]==manifest['raw_FE_rows']
    guard(name+'_operator_identity',128<<20)
    operator_differences={
        'A':sparse_difference(arrays['A'],Ti.conj().T@arrays['raw_A']@Ti),
        'C':sparse_difference(arrays['C'],Ti.conj().T@arrays['raw_C']),
        'D':sparse_difference(arrays['D'],arrays['raw_D']@Ti),
        'full':sparse_difference(full,sparse.bmat([[arrays['A'],arrays['C']],
                       [arrays['D'],sparse.eye(m,dtype=complex)]],format='csr'))}
    assert all(item['relative_frobenius']<1e-13 for item in operator_differences.values())
    rhs,f,g=(np.load(p/file,allow_pickle=False) for file in ('rhs.npy','raw_f.npy','raw_aux_rhs.npy'))
    rhs_defect=relative(np.r_[Ti.conj().T@f,g],rhs)
    assert rhs_defect<1e-12
    if manifest['mode']=='direct':
        ref_dir=p
    else:
        ref_dir=BASE/manifest['reference_case_id']
        ref_manifest=read(ref_dir/'run_manifest.json')
        assert ref_manifest['status']=='DIRECT_REFERENCE_PASS'
        assert ref_manifest['wavelength_nm']==manifest['wavelength_nm']
        assert ref_manifest['physical_sha256']==manifest['physical_sha256']
        for key in ('A','C','D','T','mass','curl_gram','rhs'):
            if key=='rhs':
                assert np.array_equal(np.load(p/'rhs.npy'),np.load(ref_dir/'rhs.npy'))
            else:
                left=sparse.load_npz(p/f'{key}.npz').tocsr();right=sparse.load_npz(ref_dir/f'{key}.npz').tocsr()
                delta=left-right;delta.eliminate_zeros();assert delta.nnz==0,key
    reference=np.load(ref_dir/'reference_solution.npz',allow_pickle=False)['z']
    ref_fields=dict(np.load(ref_dir/'reference_fields.npz',allow_pickle=False))
    e_ref=reference[:n];mass,curl=arrays['mass'],arrays['curl_gram']
    divisor=float(ref_fields['H_curl_norm_divisor'])
    e_norm=float(np.real(np.vdot(e_ref,mass@e_ref)+2*np.vdot(e_ref,ref_fields['m_bg']).real+
                           ref_fields['background_E_l2_squared']))
    h_norm=float(np.real(np.vdot(e_ref,curl@e_ref)+2*np.vdot(e_ref,ref_fields['k_bg']).real+
                           ref_fields['background_curl_l2_squared']))/divisor
    assert e_norm>0 and h_norm>0
    ref_diag=read(ref_dir/'reference_diagnostics.json')
    assert ref_diag['qualification']=='diagnostic_unqualified_for_physical_convergence'
    assert np.isclose(e_norm,ref_diag['E_total_l2_squared'],rtol=1e-10)
    assert np.isclose(h_norm,ref_diag['H_total_l2_squared'],rtol=1e-10)

    def evaluate(z):
        e,q=z[:n],z[n:]
        u=Ti@e
        raw_res=arrays['raw_A']@u+arrays['raw_C']@q-f
        aux_res=arrays['raw_D']@u+q-g
        denominator=max(float(np.linalg.norm(rhs)),np.finfo(float).tiny)
        full_res=float(np.linalg.norm(full@z-rhs)/denominator)
        projected=float(np.linalg.norm(np.r_[Ti.conj().T@raw_res,aux_res])/denominator)
        constraint=0.
        for slave in mpc['slaves']:
            a,b=mpc['coefficient_offsets'][slave:slave+2];j,k=mpc['master_offsets'][slave:slave+2]
            constraint=max(constraint,float(abs(u[slave]-np.dot(mpc['coefficients'][a:b],u[mpc['masters'][j:k]]))))
        delta=e-e_ref
        e2=float(np.vdot(delta,mass@delta).real)
        h2=float(np.vdot(delta,curl@delta).real)/divisor
        assert e2>=-1e-18 and h2>=-1e-18
        return {'full_true_residual':full_res,'original_projected_true_residual':projected,
                'MPC_maximum_absolute':constraint,
                'E_total_relative_L2':float(np.sqrt(max(e2,0.)/e_norm)),
                'H_total_relative_L2':float(np.sqrt(max(h2,0.)/h_norm))}
    results={'reference':evaluate(reference)}
    assert results['reference']['full_true_residual']<=1e-10
    assert results['reference']['original_projected_true_residual']<=1e-10
    if manifest['mode']=='direct':
        assert manifest['status']=='DIRECT_REFERENCE_PASS'
        assert float(summary['result']['true_residual'])<=1e-10
    else:
        solutions=dict(np.load(p/'candidate_solution.npz',allow_pickle=False))
        results['initial']=evaluate(solutions['x0']);results['final']=evaluate(solutions['z'])
        assert results['initial']['MPC_maximum_absolute']<1e-10
        assert results['final']['MPC_maximum_absolute']<1e-10
        solver_pass=(results['final']['full_true_residual']<=1e-8
                     and results['final']['original_projected_true_residual']<=1e-8
                     and results['final']['E_total_relative_L2']<=1e-4
                     and results['final']['H_total_relative_L2']<=1e-3)
        qualified=manifest['qualified_total_power_gate']
        assert bool(summary['result']['same_discrete_solver_pass'])==solver_pass
        if qualified['qualification']=='qualified':
            assert qualified['status'] in {'pass','fail'}
            assert set(qualified['absolute_differences'])=={'R_total','T_total','A_flux','A_volume'}
            assert (qualified['status']=='pass')==(max(qualified['absolute_differences'].values(),default=0.)<=1e-4)
        else:
            assert qualified['status']=='not_applicable_unqualified_postprocessing'
            assert 'diagnostic_absolute_differences' in qualified
        overall_pass=solver_pass and qualified['status']!='fail'
        assert (manifest['status']=='CANDIDATE_SAME_DISCRETE_PASS')==overall_pass
        if not overall_pass:assert manifest['status']!='CANDIDATE_SAME_DISCRETE_PASS'
        assert np.isclose(summary['result']['final_true_residual'],results['final']['full_true_residual'],rtol=1e-10,atol=1e-15)
        del solutions
    samples,stages=read(p/'resource_samples.json'),read(p/'phase_gates.json')
    assert samples and stages
    resource_ok=all(s['process_tree_rss_bytes']+(512<<20)<=8_000_000_000
                    and s['process_tree_swap_bytes']==0 and s['MemAvailable_bytes']>=400*G
                    and s['disk_free_bytes']>=400_000_000_000
                    and s['cgroup']['memory_current_bytes']+(512<<20)<=8_000_000_000
                    and s['cgroup']['memory_max_bytes']==8_000_000_000
                    and s['cgroup']['swap_current_bytes']==s['cgroup']['swap_max_bytes']==0 for s in samples)
    assert resource_ok
    assert all(s['process_rss_bytes']+s['planned_extra_bytes']+s['staging_reserve_bytes']<=8_000_000_000
               and s['host_available_bytes']>=400*G
               and s['cgroup_memory_max_bytes']==8_000_000_000
               and s['cgroup_swap_max_bytes']==s['cgroup_swap_current_bytes']==0
               and s['cgroup_memory_current_bytes']+s['planned_extra_bytes']+s['staging_reserve_bytes']<=8_000_000_000
               for s in stages)
    assert supervision['peak_sampled_process_tree_rss_bytes']==max(s['process_tree_rss_bytes'] for s in samples)
    partition=read(p/'partition_audit.json') if (p/'partition_audit.json').exists() else None
    if partition:
        assert partition['mass_partition_relative']<1e-12 and partition['reconstruction_relative']<1e-10
        for pair in partition['pairs']:
            assert pair['phase_map_error']<1e-11 and pair['local_residual']<1e-9
            assert all(value<1e-11 for value in pair['weak_product_errors'])
        if partition['partition_count']==2:
            results['N2_local_matrix_review']=review_saved_n2_pair(
                p/'pair0_map.npz',p/'pair0_L.npz',arrays['A']-arrays['C']@arrays['D'],
                in_process_relative=partition['pairs'][0].get('n2_operator_relative'),
            )
    item={'case':name,'source_sha':manifest['source_sha'],'physical_sha256':manifest['physical_sha256'],
          'wavelength_nm':manifest['wavelength_nm'],'mode_count':len(modes),
          'mode_order_sha256':metadata['ordered_modes_sha256'],
          'auto_bounds':{'m':metadata['auto_max_m'],'n':metadata['auto_max_n']},
          'selected_bounds':{'m':mmax,'n':nmax},'propagating_modes':metadata['propagating_mode_count'],
          'evanescent_modes':metadata['evanescent_mode_count'],
          'artifact_hashes_verified':len(artifact_manifest),'operator_differences':operator_differences,
          'RHS_projection_relative_difference':rhs_defect,'solutions':results,
          'case_status':manifest['status'],
          'same_discrete_solver_pass':summary['result'].get('same_discrete_solver_pass'),
          'resource_status':'pass','samples':len(samples),'wall_seconds':supervision['wall_seconds'],
          'peak_process_tree_rss_bytes':supervision['peak_sampled_process_tree_rss_bytes'],
          'qualified_total_power_gate':manifest.get('qualified_total_power_gate'),
          'postprocessing_qualification':manifest.get('postprocessing_qualification'),
          'array_hashes':{key:sparse_identity(arrays[key]) for key in ('A','C','D','T','mass','curl_gram','full')},
          'rhs_sha256':digest(p/'rhs.npy')}
    del arrays,T,Ti,full,mpc,reference,ref_fields,mass,curl,samples,stages
    gc.collect();guard(name+'_complete')
    return item


def _workstation_review():
    if not __debug__:
        raise RuntimeError('Do not run optimized')
    assert all(os.environ.get(k)=='1' for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'])
    ledger_path=SCOPE_ROOT/'budget_ledger.json'
    ledger=read(ledger_path) if ledger_path.exists() else []
    statuses={str(row.get('status','')) for row in ledger}
    assert 'running' not in statuses and 'RUNNING' not in statuses, 'Do not overlap review with an active formal case'
    assert statuses.issubset({'COMPLETED_PROCESS_REVIEW_PENDING','FAILED','CONTROLLED_STOP'}), statuses
    assert len(ledger)<=10 and sum(float(row.get('wall_seconds',0.)) for row in ledger)<=21600
    assert len(args.cases)==len(set(args.cases)), 'Duplicate --case IDs are not allowed'
    cases=[check_workstation_case(name) for name in args.cases]
    by_wavelength={}
    for item in cases:
        group=by_wavelength.setdefault(item['wavelength_nm'],[])
        group.append(item)
    for group in by_wavelength.values():
        assert len({item['physical_sha256'] for item in group})==1
        assert len({item['mode_order_sha256'] for item in group})==1
        assert all(item['array_hashes']==group[0]['array_hashes'] for item in group)
        assert len({item['rhs_sha256'] for item in group})==1
    local_matrix_limitations=[
        {'case':item['case'],'status':review['status'],'missing_files':review['missing_files'],
         'in_process_n2_operator_relative':review['in_process_n2_operator_relative']}
        for item in cases
        for review in [item['solutions'].get('N2_local_matrix_review',{})]
        if review.get('status')=='NOT_RECOMPUTABLE_MISSING_SAVED_LOCAL_MATRICES'
    ]
    review_status=('SAVED_WORKSTATION_CASE_REVIEW_COMPLETE_WITH_LIMITATIONS'
                   if local_matrix_limitations else 'SAVED_WORKSTATION_CASE_REVIEW_COMPLETE')
    limits=['Only explicitly selected saved cases were reviewed; earlier FAILED and CONTROLLED_STOP ledger entries remain visible and do not block review.',
            'Same-discrete solver/field status and qualified total-power status are reported separately.',
            'The review recomputes saved original-system residuals, MPC defects, E/H errors, matrix identities, and resource gates; it does not rerun PDE cases.',
            'A same-discrete pass is not mesh/modal convergence or physical/target-scale qualification.']
    if local_matrix_limitations:
        limits.append('Independent N=2 local-matrix recomputation is unavailable for listed cases; their saved in-process n2_operator_relative values are reported separately and are not independent recomputations.')
    guard('final')
    result={'status':review_status,
            'review_script_sha256':digest(Path(__file__)),
            'reviewed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'profile':'workstation','reviewed_case_ids':list(args.cases),'cases':cases,
            'ledger_attempt_count':len(ledger),
            'ledger_status_counts':{status:sum(row.get('status')==status for row in ledger) for status in sorted(statuses)},
            'ledger_cumulative_wall_seconds':sum(float(row.get('wall_seconds',0.)) for row in ledger),
            'independent_local_matrix_limitations':local_matrix_limitations,
            'review_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
            'review_wall_seconds':time.monotonic()-START,'review_guards':GUARDS,
            'limits':limits}
    OUT.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({'status':result['status'],'report':str(OUT),
                      'reviewed_case_ids':list(args.cases),
                      'peak_rss':result['review_peak_rss_bytes']}))


if __name__=='__main__':
    if not __debug__:
        raise RuntimeError('Do not run optimized')
    if PROFILE=='cloud':
        assert all(os.environ.get(k)=='1' for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS'])
        ledger=read(BASE/'budget_ledger.json')
        assert all(x['status']=='finished' for x in ledger), 'Do not overlap review with formal cases'
        assert len(ledger)<=10 and sum(x['wall_seconds'] for x in ledger)<21600
        cases=[check_case(name) for name in ['check_p2_v1','direct_p2_v1','candidate_p2_n2_v1','candidate_p2_n4_v1']]
        assert len({x['physical_sha256'] for x in cases})==1 and len({x['source_sha'] for x in cases})==1
        assert len({x['mode_order_sha256'] for x in cases})==1
        assert all(x['array_hashes']==cases[0]['array_hashes'] for x in cases)
        assert all(x['rhs_sha256']==cases[1]['rhs_sha256'] for x in cases[1:])
        guard('final')
        result={'status':'SAVED_ORIGINAL_SYSTEM_FIELDS_AND_RESOURCE_REVIEW_PASS',
                'review_script_sha256':digest(Path(__file__)),
                'reviewed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'cases':cases,
                'formal_case_count':len(ledger),'formal_cumulative_wall_seconds':sum(x['wall_seconds'] for x in ledger),
                'review_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024,
                'review_wall_seconds':time.monotonic()-START,'review_guards':GUARDS,
                'limits':['No native assembly, PDE solve, factorization, or new experiment was run.',
                          'Mass partition, weak-product and local mapping numeric audit values were read and code-reviewed, not independently reassembled.',
                          'Original-system residuals, MPC, E/H errors and the N2 operator were independently recomputed from saved arrays.',
                          'Resource limits are sampled supervision, not a verified kernel hard quota.',
                          'Same-discrete pass is not mesh/modal convergence or physical/target-scale qualification.']}
        OUT.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
        print(json.dumps({'status':result['status'],'report':str(OUT),'peak_rss':result['review_peak_rss_bytes']}))
    else:
        _workstation_review()
