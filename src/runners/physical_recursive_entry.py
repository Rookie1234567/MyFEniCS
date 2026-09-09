"""Single supervised G1 component invocation; no outer solve or campaign routing."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def p4_bridge_status(path):
    from math import isfinite
    from .physical_diagnostic_completion import load_packet
    if not Path(path).exists():return 'NOT_REACHED'
    errors=load_packet(Path(path))['errors']
    return 'PASS' if len(errors)==3 and all(isfinite(v) and v<=1e-10 for v in errors.values()) else 'FAIL'


def component_contract(target):
    if target not in ('lo','hi'):
        raise ValueError('only frozen LO/HI component targets')
    return dict(identity='balanced_h6_recursive_p4_'+target+'_v6', scope='G1_components_only',
        physical_degrees=[6,4,2], I4=dict(method='right_FGMRES',restart=16,max_it=64,
        target=1e-4 if target=='lo' else 1e-6,zero_start=True,seconds=60,explicit_interval=16),
        B4='C42+(I-C42 A4)H4(I-A4 C42)',H4=dict(degree=3,power_steps=10),
        bottom=dict(physical_degree=2,total_rows_cap=8192,bytes_cap=512*1024**2,
            native_residual=1e-10,max_refinements=2),fixed_I4_calls=6,full_PC_calls=3,
        new_reference_factor=False,p4_global_matrix=False,p4_global_factor=False,
        full_outer_solve=False,global_swap_stop=True)


def p4_failure_contract():
    return dict(identity='p4_p2_failure_diagnostic_v6',scope='one_saved_A2R160_g1',
        physical_degrees=[6,4,2],I4_calls=0,outer_calls=0,
        projection=dict(count=1,metric='unweighted constrained M0',method='diagonal_CG',
            max_it=256,equation_limit=1e-10,pythagorean_limit=1e-9,seconds=600),
        A4_limit=40,p2_logical_limit=12,H4_standalone=1,B4_calls=2,
        component_calls=dict(curl=1,material_mass=1,dtn=1),workflow_seconds=1800,
        p2_rows_cap=8192,p2_budget_bytes=512*1024**2,p2_true_limit=1e-10,
        new_reference_factor=False,global_swap_stop=True)


def git_state(expected):
    def git(*args):return subprocess.check_output(['git',*args],text=True).strip()
    head=git('rev-parse','HEAD')
    if head!=expected or git('branch','--show-current')!='task39extra' or git('status','--porcelain'):
        raise RuntimeError('clean expected task39extra source required')
    return dict(head=head,branch='task39extra',git_dir=git('rev-parse','--absolute-git-dir'),
        upstream=git('rev-parse','--abbrev-ref','@{upstream}'),ahead_behind=git('rev-list','--left-right','--count','HEAD...@{upstream}'))


def atomic(path,data):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n');temporary.replace(path)


def worker(args):
    cache_home=(Path(args.output)/'jit_cache').resolve()
    if os.environ.get('XDG_CACHE_HOME')!=str(cache_home):
        raise RuntimeError('isolated JIT cache must be inherited before worker imports')
    import numpy as np
    from petsc4py import PETSc
    from mpi4py import MPI
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from benchmarks.subreaper_watchdog import memory_envelope
    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
    from .physical_recursive_controls import run_recursive_components
    from .workflow_timebase import clock_sample
    if (os.environ.get('_MYFENICS_WSL_QUALIFIED_ACTIVATION')!='1' or
        os.environ.get('PHYSICAL_TIMEBASE_GUARD')!='1' or not os.path.samefile(sys.executable,'.venv/bin/python') or
        MPI.COMM_WORLD.size!=1 or PETSc.ScalarType is not np.complex128 or PETSc.IntType is not np.int32):
        raise RuntimeError('qualified complex128/int32 MPI1 worker required')
    threads={k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')}
    if set(threads.values())!={'1'}:raise RuntimeError('threads must be one')
    source=git_state(args.source_sha)
    parent=int(os.environ['PHYSICAL_WATCHDOG_PARENT_PID']);cap=int(os.environ['PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES'])
    if parent==os.getpid() or not Path(f'/proc/{parent}').exists():raise RuntimeError('dedicated parent missing')
    payload=load_and_resolve(args.input).as_jsonable()
    if (payload['provenance']['physical_model_sha256']!='9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f'
        or payload['geometry'].get('cell_notch')):raise ValueError('G1 requires frozen original physical model')
    cfg=simulation_config_3d_from_normalized(payload)
    diagnostic=args.p4_failure_diagnostic
    contract=p4_failure_contract() if diagnostic else component_contract(args.target);root=Path(args.output)
    (root/'input_original.dat').write_bytes(Path(args.input).read_bytes())
    atomic(root/'resolved_config.json',dict(physical_input=payload,component_profile=contract,
        original_dat_solver_role='physical template only; old V5 PC is not invoked'))
    import petsc4py,slepc4py,dolfinx,basix,mpi4py
    from dolfinx.jit import get_options
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import SAME_MESH_JIT_OPTIONS
    cache_options=get_options(SAME_MESH_JIT_OPTIONS)
    if Path(cache_options['cache_dir']).resolve()!=cache_home/'fenics':
        raise RuntimeError('effective form JIT cache escaped isolated run root')
    inventory=json.loads(Path(args.inventory).read_text())
    if diagnostic:
        native_maps={'4':inventory['packets']['map']}
        mode_sha=inventory['mode_sha256']
    else:
        evidence_root=Path(inventory['six_calibration_rhs'][0]['input_json']).parent
        native_maps={str(level):dict(path=str(evidence_root/f'native_constraint_map_p{level}.json'),
            sha256=hashlib.sha256((evidence_root/f'native_constraint_map_p{level}.json').read_bytes()).hexdigest()) for level in (6,4)}
        mode_sha=inventory['models'][0]['mode_sha']
    manifest=dict(source=source,input_sha256=hashlib.sha256(Path(args.input).read_bytes()).hexdigest(),
        resolved_sha256=hashlib.sha256((root/'resolved_config.json').read_bytes()).hexdigest(),
        command=[sys.executable,'-m','src.runners.physical_recursive_entry',*sys.argv[1:]],
        cwd=str(Path.cwd()),physical_sha256=payload['provenance']['physical_model_sha256'],
        mode_sha256=mode_sha,native_maps=native_maps,
        native_map_bridge='exact fieldwise comparison to saved maps before component calls',
        jit_cache=dict(xdg_cache_home=str(cache_home),effective_cache_dir=str(cache_options['cache_dir']),
            timeout=cache_options['timeout'],cold=True),
        profile=contract,abi=dict(python=sys.executable,scalar='complex128',integer='int32',threads=threads,
            modules={m.__name__:m.__file__ for m in (petsc4py,slepc4py,dolfinx,basix,mpi4py)}),
        inventory_sha256=hashlib.sha256(Path(args.inventory).read_bytes()).hexdigest())
    atomic(root/'run_manifest.json',manifest)
    def sample():
        value=process_tree_snapshot(parent,'G1_components',None);envelope=memory_envelope()
        value['launch_cap_bytes']=min(cap,value['rss_bytes']+envelope['effective_available_bytes']-envelope['reserve_bytes'])
        if (not value['all_status_readable'] or value['swap_bytes'] or value['rss_bytes']>=value['launch_cap_bytes']
            or envelope['effective_available_bytes']<envelope['reserve_bytes']):
            raise RuntimeError('whole-tree resource gate failed')
        return value
    def marker(name,facts):
        stamp=clock_sample()
        atomic(root/'phase.json',dict(phase='components',stage=name,clock=stamp))
        with (root/'stages.jsonl').open('a') as stream:stream.write(json.dumps(dict(stage=name,clock=stamp,facts=facts))+'\n')
    try:
        if diagnostic:
            from .physical_recursive_controls import run_p4_failure_diagnostic
            run_p4_failure_diagnostic(cfg,MPI.COMM_WORLD,args.inventory,root/'records',sample=sample,marker=marker)
        else:
            run_recursive_components(cfg,MPI.COMM_WORLD,args.inventory,root/'records',
                target=contract['I4']['target'],sample=sample,marker=marker)
    finally:
        identity=root/'records'/('input_bridge.json' if diagnostic else 'fresh_identity.json')
        manifest['native_map_bridge_status']='PASS' if identity.exists() else 'NOT_REACHED'
        if diagnostic and identity.exists():
            manifest['native_map_bridge_status']=p4_bridge_status(identity)
        if identity.exists():
            manifest['fresh_identity']=dict(path=str(identity),sha256=hashlib.sha256(identity.read_bytes()).hexdigest())
        atomic(root/'run_manifest.json',manifest)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('input','inventory','output','budget','source-sha'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--target',choices=('lo',),default='lo')
    parser.add_argument('--p4-failure-diagnostic',action='store_true')
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    args=parser.parse_args()
    if args.worker:return worker(args)
    source=git_state(args.source_sha)
    from benchmarks.subreaper_watchdog import supervise
    from .workflow_timebase import CONSERVATIVE_REALTIME
    budget_path=Path(args.budget);budget=json.loads(budget_path.read_text())
    diagnostic=args.p4_failure_diagnostic
    if diagnostic and Path(args.output).parts[-3:]!=('v6_p4_failure_diagnostic',args.source_sha,'a2r160_g1'):
        raise ValueError('diagnostic requires fresh v6_p4_failure_diagnostic/source/a2r160_g1 root')
    if diagnostic and budget.get('p4_failure_diagnostic_attempts'):
        raise ValueError('unique p4 failure diagnostic already attempted')
    remaining=min(1800,budget['batch_remaining']) if diagnostic else min(budget['G0_G1_remaining'],budget['batch_remaining'])
    if remaining<=0:raise RuntimeError('G1 compute budget exhausted')
    lock=budget_path.parent/('p4_failure_active.lock' if diagnostic else 'g1_active.lock')
    descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(descriptor)
    root=Path(args.output)
    result=None
    try:
        root.mkdir(parents=True,exist_ok=False)
        cache_home=(root/'jit_cache').resolve()
        cache_home.mkdir(exist_ok=False)
        atomic(root/'launch_plan.json',dict(source=source,contract=p4_failure_contract() if diagnostic else component_contract(args.target),
            wall_seconds=remaining,budget_before=budget,jit_cache_home=str(cache_home),
            jit_cache_initially_empty=not any(cache_home.iterdir())))
        command=[sys.executable,'-m','src.runners.physical_recursive_entry',*sys.argv[1:],'--worker']
        result=supervise(command,root/'watchdog',wall_seconds=remaining,phase_path=root/'phase.json',
            hard_stop_immediate=True,timebase_guard=True,timebase_policy=CONSERVATIVE_REALTIME,
            stop_on_global_swap=True,source_state=source,
            worker_environment={'XDG_CACHE_HOME':str(cache_home)})
        charge=result['workflow_clock_interval']['budget_seconds']
        budget.setdefault('p4_failure_diagnostic_attempts' if diagnostic else 'g1_component_attempts',[]).append(dict(root=str(root),target=args.target,
            source=args.source_sha,classification=result['classification'],conservative_seconds=charge))
        for key in (('batch_remaining',) if diagnostic else ('G0_G1_remaining','batch_remaining')):budget[key]-=charge
        budget['charged_including_reserve']+=charge
        atomic(budget_path,budget)
        atomic(root/'terminal.json',result)
        if diagnostic:
            atomic(root/'source_after.json',git_state(args.source_sha))
        if result['classification']!='COMPLETED':raise SystemExit(1)
    finally:
        # An uncertain launch keeps the lock for review instead of enabling duplicate work.
        if result is not None and result.get('descendants_cleared'):lock.unlink()


if __name__=='__main__':main()
