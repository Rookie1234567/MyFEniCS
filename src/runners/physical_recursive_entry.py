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


def projected_component_contract():
    return dict(identity='projected_p4_complement_v1',scope='one_saved_A2R160_g1',
        workflow_seconds=900,physical_degrees=[6,4,2],I4_calls=1,old_I4_calls=0,outer_calls=0,
        projection_calls=0,B4_baseline_calls=0,A4_inner_limit=150,A4_identity_calls=1,
        p2_logical_limit=65,H4_limit=64,H4_positive_limit=128,
        I4=dict(method='right_FGMRES',restart=16,max_it=64,seconds=60,target=1e-4,
            residual_normalization='original ||g||',delta_zero_start=True),
        p2_rows_cap=8192,p2_budget_bytes=512*1024**2,p2_true_limit=1e-10,
        new_reference_factor=False,global_swap_stop=True)


def bubble_local_contract():
    return dict(identity='bubble_local_tensor_v1',scope='one_frozen_original_air_cell',workflow_seconds=300,
        local_p4=300,local_p2=54,interior_p4=108,retained_p2_bubble=6,Q_columns=102,
        I4_calls=0,outer_calls=0,p2_factor=0,p4_global_matrix=0,H6=0,
        tensor_limit=1e-10,basis_limit=1e-12,harmonic_limit=1e-11,trace_limit=1e-12,
        factorization='complex LU',shift=0,refinements=0,global_swap_stop=True)


def selected_contract(args):
    return (bubble_local_contract() if args.bubble_local_tensor else
            projected_component_contract() if args.projected_p4_component else
            p4_failure_contract() if args.p4_failure_diagnostic else component_contract(args.target))


def dispatch_components(args,cfg,comm,directory,*,sample,marker):
    from . import physical_recursive_controls as controls
    if args.bubble_local_tensor:
        from .physical_bubble_local_controls import run_bubble_local_tensor
        return run_bubble_local_tensor(cfg,comm,args.inventory,directory,sample=sample,marker=marker)
    if args.projected_p4_component:
        return controls.run_projected_p4_component(cfg,comm,args.inventory,directory,sample=sample,marker=marker)
    if args.p4_failure_diagnostic:
        return controls.run_p4_failure_diagnostic(cfg,comm,args.inventory,directory,sample=sample,marker=marker)
    return controls.run_recursive_components(cfg,comm,args.inventory,directory,
        target=component_contract(args.target)['I4']['target'],sample=sample,marker=marker)


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
    diagnostic=args.p4_failure_diagnostic;projected=args.projected_p4_component;bubble=args.bubble_local_tensor
    contract=selected_contract(args);root=Path(args.output)
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
    if bubble:
        native_maps={};mode_sha=inventory['mode_sha256']
    elif diagnostic or projected:
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
        dispatch_components(args,cfg,MPI.COMM_WORLD,root/'records',sample=sample,marker=marker)
    finally:
        identity=root/'records'/('bubble_cell_frozen.json' if bubble else 'projected_source_bridge.json' if projected else 'input_bridge.json' if diagnostic else 'fresh_identity.json')
        manifest['native_map_bridge_status']='PASS' if identity.exists() else 'NOT_REACHED'
        if diagnostic and identity.exists():
            manifest['native_map_bridge_status']=p4_bridge_status(identity)
        if projected and identity.exists():
            from math import isfinite
            error=json.loads(identity.read_text())['relative_error']
            manifest['native_map_bridge_status']='PASS' if isfinite(error) and error<=1e-10 else 'FAIL'
        if bubble:manifest['native_map_bridge_status']='NOT_APPLICABLE_LOCAL_TENSOR_ONLY'
        if identity.exists():
            manifest['fresh_identity']=dict(path=str(identity),sha256=hashlib.sha256(identity.read_bytes()).hexdigest())
        atomic(root/'run_manifest.json',manifest)


def build_parser():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('input','inventory','output','budget','source-sha'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--target',choices=('lo',),default='lo')
    group=parser.add_mutually_exclusive_group()
    group.add_argument('--p4-failure-diagnostic',action='store_true')
    group.add_argument('--projected-p4-component',action='store_true')
    group.add_argument('--bubble-local-tensor',action='store_true')
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    return parser


def main():
    args=build_parser().parse_args()
    if args.worker:return worker(args)
    source=git_state(args.source_sha)
    from benchmarks.subreaper_watchdog import supervise
    from .workflow_timebase import CONSERVATIVE_REALTIME
    budget_path=Path(args.budget);budget=json.loads(budget_path.read_text())
    diagnostic=args.p4_failure_diagnostic;projected=args.projected_p4_component;bubble=args.bubble_local_tensor
    if diagnostic and Path(args.output).parts[-3:]!=('v6_p4_failure_diagnostic',args.source_sha,'a2r160_g1'):
        raise ValueError('diagnostic requires fresh v6_p4_failure_diagnostic/source/a2r160_g1 root')
    if diagnostic and budget.get('p4_failure_diagnostic_attempts'):
        raise ValueError('unique p4 failure diagnostic already attempted')
    if projected and Path(args.output).parts[-3:]!=('v6_projected_p4_component',args.source_sha,'a2r160_g1'):
        raise ValueError('projected component requires fresh source/a2r160_g1 root')
    if projected and budget.get('projected_p4_component_attempts'):
        raise ValueError('unique projected p4 component already attempted')
    if bubble and Path(args.output).parts[-3:]!=('v6_bubble_local_tensor',args.source_sha,'air_fixed'):
        raise ValueError('bubble local tensor requires fresh source/air_fixed root')
    if bubble and budget.get('bubble_local_tensor_attempts'):
        raise ValueError('unique bubble local tensor already attempted')
    remaining=min(selected_contract(args)['workflow_seconds'],budget['batch_remaining']) if diagnostic or projected or bubble else min(budget['G0_G1_remaining'],budget['batch_remaining'])
    if remaining<=0:raise RuntimeError('G1 compute budget exhausted')
    lock=budget_path.parent/('bubble_local_active.lock' if bubble else 'projected_p4_active.lock' if projected else 'p4_failure_active.lock' if diagnostic else 'g1_active.lock')
    descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(descriptor)
    root=Path(args.output)
    result=None
    try:
        root.mkdir(parents=True,exist_ok=False)
        cache_home=(root/'jit_cache').resolve()
        cache_home.mkdir(exist_ok=False)
        atomic(root/'launch_plan.json',dict(source=source,contract=selected_contract(args),
            wall_seconds=remaining,budget_before=budget,jit_cache_home=str(cache_home),
            jit_cache_initially_empty=not any(cache_home.iterdir())))
        command=[sys.executable,'-m','src.runners.physical_recursive_entry',*sys.argv[1:],'--worker']
        result=supervise(command,root/'watchdog',wall_seconds=remaining,phase_path=root/'phase.json',
            hard_stop_immediate=True,timebase_guard=True,timebase_policy=CONSERVATIVE_REALTIME,
            stop_on_global_swap=True,source_state=source,
            worker_environment={'XDG_CACHE_HOME':str(cache_home)})
        charge=result['workflow_clock_interval']['budget_seconds']
        budget.setdefault('bubble_local_tensor_attempts' if bubble else 'projected_p4_component_attempts' if projected else 'p4_failure_diagnostic_attempts' if diagnostic else 'g1_component_attempts',[]).append(dict(root=str(root),target=args.target,
            source=args.source_sha,classification=result['classification'],conservative_seconds=charge))
        for key in (('batch_remaining',) if diagnostic or projected or bubble else ('G0_G1_remaining','batch_remaining')):budget[key]-=charge
        budget['charged_including_reserve']+=charge
        atomic(budget_path,budget)
        atomic(root/'terminal.json',result)
        if diagnostic or projected or bubble:
            atomic(root/'source_after.json',git_state(args.source_sha))
        if result['classification']!='COMPLETED':raise SystemExit(1)
    finally:
        # An uncertain launch keeps the lock for review instead of enabling duplicate work.
        if result is not None and result.get('descendants_cleared'):lock.unlink()


if __name__=='__main__':main()
