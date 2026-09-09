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


def bubble_component_contract():
    return dict(identity='bubble_enriched_p2_component_v1',scope='one_saved_A2R160_g1',workflow_seconds=900,
        physical_degrees=[6,4,2],retained_p2_bubble=6,local_Q_columns=102,
        class_key='exact affine J/width/material/quadrature/orientation; no rounding',
        adjoint_limit=1e-11,S_assembly_limit=1e-10,range_identity_limit=1e-10,trace_limit=1e-12,
        bottom=dict(rows_cap=8192,unified_bytes_cap=512*1024**2,action='WH A4 W',true_limit=1e-10,max_refinements=2),
        I4=dict(method='original_V6_right_FGMRES',restart=16,max_it=64,seconds=60,target=1e-4,zero_start=True),
        I4_calls=1,Cg_calls=1,range_checks=1,B4_limit=64,H4_positive_limit=128,
        p2_logical_limit=130,MatSolve_limit=390,composed_A4_limit=392,external_A4_limit=220,B4_structure_A4_limit=128,
        old_p2_factor=0,p4_global_matrix=0,p4_global_factor=0,outer_calls=0,global_swap_stop=True)


def particular_contract():
    return dict(identity='bubble_particular_diagnostic_v1',scope='same_g_three_errors_two_E_inputs',workflow_seconds=300,
        source_component='d9462e486360a86e9635b504f37a0b762c2bf896',mesh=1,functionspace=0,
        error_decompositions=3,E_inputs=['g','Cg_residual'],local_LU=18,local_rhs=504,cached_A4=2,
        SVD=0,T_54_rhs=0,class_qualification_repeated=False,global_factor=0,H6=0,H4=0,I4=0,outer=0,
        payload_policy_bytes=128*1024**2,energy_bridge_limit=1e-10,identity_limit=1e-11,global_swap_stop=True)


def selected_contract(args):
    if getattr(args,'cell_joint_trace_component',False):
        owner_args=argparse.Namespace(**vars(args));owner_args.cell_joint_trace_component=False
        owner_args.owner_route_trace_component=True
        contract=selected_contract(owner_args)
        contract.update(identity='physical_cell_joint_trace_component_v1',cell_joint_trace=True,
            entity_LU=0,entity_setup_rhs=0,entity_apply_rhs_limit=0,patch_LU=84,patch_setup_rhs=84,
            patch_count=252,patch_dimension=144,patch_apply_rhs_limit=65*252,
            patch_qualification=dict(physical_F_bridges=2,HT_calls=3),
            old_HT_B4_equality_required=False)
        return contract
    if getattr(args,'owner_route_trace_component',False):
        cached_args=argparse.Namespace(**vars(args))
        cached_args.owner_route_trace_component=False;cached_args.cached_trace_component=True
        contract=selected_contract(cached_args)
        contract.update(identity='physical_owner_route_trace_component_v1',
            fixed_serial_owner_route=True,owner_primal_qualification=3,
            owner_primal_limit=1e-11,owner_B4_bridge_limit=1e-10,
            owner_extra_budget_bytes=4117888)
        return contract
    return (dict(identity='physical_cached_trace_component_v1' if getattr(args,'cached_trace_component',False) else 'physical_high_trace_component_v1',workflow_seconds=600,
            physical_degrees=[4,2],scope='one_CUg_bridge_one_B4T_one_I4',B4_limit=65,CU_limit=131,
            S_logical_limit=131,MatSolve_limit=393,A4_limit=350,HT_limit=65,E_EH_limit=263,
            Q_LU=18,Q_setup_rhs=3456,entity_LU=1566,entity_setup_rhs=1566,entity_apply_rhs_limit=101790,
            bottom_rows_cap=8192,bottom_local_bytes_cap=512*1024**2,S_true_limit=1e-10,max_refinements=2,
            I4=dict(count=1,restart=16,max_it=64,seconds=60,target=1e-4,zero_start=True),
            H6=0,old_H4=0,outer=0,global_swap_stop=True,
            cached_exact=getattr(args,'cached_trace_component',False),native_authority_cap=75,
            cached_qualification=3 if getattr(args,'cached_trace_component',False) else 0,
            explicit_authority='native_A4') if getattr(args,'high_trace_component',False) or getattr(args,'cached_trace_component',False) else
            dict(identity='bubble_amplification_diagnostic_v1',workflow_seconds=300,
            scope='one_saved_delta_CUg',metadata_degrees=[4,2],A4=0,H4=0,H6=0,I4=0,outer=0,local_LU=0,
            p2_factor=1,p2_logical=1,max_refinements=2,p2_rows_cap=8192,p2_budget_bytes=512*1024**2,
            S_true_limit=1e-10,global_swap_stop=True) if getattr(args,'bubble_amplification_diagnostic',False) else
            particular_contract() if getattr(args,'bubble_particular_diagnostic',False) else
            bubble_component_contract() if getattr(args,'bubble_enriched_component',False) else
            bubble_local_contract() if args.bubble_local_tensor else
            projected_component_contract() if args.projected_p4_component else
            p4_failure_contract() if args.p4_failure_diagnostic else component_contract(args.target))


def dispatch_components(args,cfg,comm,directory,*,sample,marker):
    from . import physical_recursive_controls as controls
    if getattr(args,'high_trace_component',False) or getattr(args,'cached_trace_component',False) or getattr(args,'owner_route_trace_component',False) or getattr(args,'cell_joint_trace_component',False):
        from .physical_trace_controls import run_trace_component
        return run_trace_component(cfg,comm,args.inventory,directory,sample=sample,marker=marker,
            cached_exact=getattr(args,'cached_trace_component',False) or getattr(args,'owner_route_trace_component',False) or getattr(args,'cell_joint_trace_component',False),
            fixed_serial_owner_route=getattr(args,'owner_route_trace_component',False) or getattr(args,'cell_joint_trace_component',False),
            cell_joint_trace=getattr(args,'cell_joint_trace_component',False))
    if getattr(args,'bubble_amplification_diagnostic',False):
        from src.solvers.physical_bubble_amplification import run_amplification_diagnostic
        return run_amplification_diagnostic(cfg,comm,args.inventory,directory,sample=sample,marker=marker)
    if getattr(args,'bubble_particular_diagnostic',False):
        from src.solvers.physical_bubble_particular import run_particular_diagnostic
        return run_particular_diagnostic(cfg,comm,args.inventory,directory,sample=sample,marker=marker)
    if getattr(args,'bubble_enriched_component',False):
        from .physical_bubble_controls import run_bubble_component
        return run_bubble_component(cfg,comm,args.inventory,directory,sample=sample,marker=marker)
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
    diagnostic=args.p4_failure_diagnostic;projected=args.projected_p4_component;bubble=args.bubble_local_tensor;enriched=args.bubble_enriched_component;particular=args.bubble_particular_diagnostic
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
    elif diagnostic or projected or enriched or particular or args.bubble_amplification_diagnostic or args.high_trace_component or args.cached_trace_component or args.owner_route_trace_component or args.cell_joint_trace_component:
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
    if particular:manifest['native_map_bridge']='frozen p4 DOF/MPC reused; rebuilt geometry/permutations exactly compared'
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
        identity=root/'records'/('trace_source_bridge.json' if args.high_trace_component or args.cached_trace_component or args.owner_route_trace_component or args.cell_joint_trace_component else 'amplification_map_bridge.json' if args.bubble_amplification_diagnostic else 'particular_map_bridge.json' if particular else 'bubble_source_bridge.json' if enriched else 'bubble_cell_frozen.json' if bubble else 'projected_source_bridge.json' if projected else 'input_bridge.json' if diagnostic else 'fresh_identity.json')
        manifest['native_map_bridge_status']='PASS' if identity.exists() else 'NOT_REACHED'
        if diagnostic and identity.exists():
            manifest['native_map_bridge_status']=p4_bridge_status(identity)
        if (projected or enriched or particular or args.bubble_amplification_diagnostic or args.high_trace_component or args.cached_trace_component or args.owner_route_trace_component or args.cell_joint_trace_component) and identity.exists():
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
    group.add_argument('--bubble-enriched-component',action='store_true')
    group.add_argument('--bubble-particular-diagnostic',action='store_true')
    group.add_argument('--bubble-amplification-diagnostic',action='store_true')
    group.add_argument('--high-trace-component',action='store_true')
    group.add_argument('--cached-trace-component',action='store_true')
    group.add_argument('--owner-route-trace-component',action='store_true')
    group.add_argument('--cell-joint-trace-component',action='store_true')
    parser.add_argument('--amplification-recording-retry',action='store_true',
        help='one reviewed retry of the frozen pre-factor mappingproxy recording failure')
    parser.add_argument('--worker',action='store_true',help=argparse.SUPPRESS)
    return parser


def amplification_recording_retry(args,budget):
    """Admit only the audited dd9b pre-factor recording failure, once."""
    attempts=budget.get('bubble_amplification_diagnostic_attempts',[])
    if not args.amplification_recording_retry:
        if args.bubble_amplification_diagnostic and attempts:
            raise ValueError('unique amplification diagnosis already attempted')
        return None
    failed_sha='dd9b6fae5cc5509459d837a99197f9be34007e18'
    root=Path('benchmarks/artifacts/task39extra/v6_bubble_amplification_diagnostic')/failed_sha/'a2r160_g1'
    if (not args.bubble_amplification_diagnostic or args.source_sha==failed_sha or len(attempts)!=1
        or attempts[0]['source']!=failed_sha or attempts[0]['root']!=str(root)
        or attempts[0]['classification']!='WORKER_FAILED'):
        raise ValueError('recording retry requires the unique frozen failed attempt')
    path=Path('benchmarks/artifacts/task39extra/v6_recursive/bubble_amplification_readout.json')
    digest=hashlib.sha256(path.read_bytes()).hexdigest()
    if digest!='11e04fd284f5aa75a6b35a251320730f065c6b43e7276ef6a193cc951299c9be':
        raise ValueError('reviewed failure readout changed')
    readout=json.loads(path.read_text());hashes={e['path']:e['sha256'] for e in readout['evidence']}
    for p in (root/'terminal.json',root/'records/amplification_costs.json',root/'watchdog/worker.log'):
        if hashlib.sha256(p.read_bytes()).hexdigest()!=hashes[str(p)]:
            raise ValueError('frozen failure evidence changed')
    terminal=json.loads((root/'terminal.json').read_text())
    costs=json.loads((root/'records/amplification_costs.json').read_text())
    log=(root/'watchdog/worker.log').read_text()
    if (not terminal['descendants_cleared'] or terminal['remaining_child_pids']
        or costs['counts']['factor']!=0 or costs['bottom']
        or 'TypeError: Object of type mappingproxy is not JSON serializable' not in log
        or "save('amplification_coarse_rhs'" not in log
        or not readout['all_checks_passed'] or not readout['resources']['host_ps_confirmed_absent']):
        raise ValueError('not the approved pre-factor serialization failure')
    return dict(failed_root=str(root),readout_sha256=digest,allowed_retries=1,
        reason='mappingproxy recording failure before factor; old attempt and charge preserved')


def main():
    args=build_parser().parse_args()
    if args.worker:return worker(args)
    source=git_state(args.source_sha)
    from benchmarks.subreaper_watchdog import supervise
    from .workflow_timebase import CONSERVATIVE_REALTIME
    budget_path=Path(args.budget);budget=json.loads(budget_path.read_text())
    diagnostic=args.p4_failure_diagnostic;projected=args.projected_p4_component;bubble=args.bubble_local_tensor;enriched=args.bubble_enriched_component;particular=args.bubble_particular_diagnostic
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
    if enriched and Path(args.output).parts[-3:]!=('v6_bubble_enriched_component',args.source_sha,'a2r160_g1'):
        raise ValueError('bubble enriched component requires fresh source/a2r160_g1 root')
    if enriched and budget.get('bubble_enriched_component_attempts'):
        raise ValueError('unique bubble enriched component already attempted')
    if particular and Path(args.output).parts[-3:]!=('v6_bubble_particular_diagnostic',args.source_sha,'a2r160_g1'):
        raise ValueError('particular diagnostic requires fresh source/a2r160_g1 root')
    if particular and budget.get('bubble_particular_diagnostic_attempts'):
        raise ValueError('unique particular diagnostic already attempted')
    amplification=args.bubble_amplification_diagnostic
    joint_trace=args.cell_joint_trace_component
    owner_trace=args.owner_route_trace_component or joint_trace
    cached_trace=args.cached_trace_component;trace=args.high_trace_component or cached_trace or owner_trace
    if trace and Path(args.output).parts[-3:]!=('v6_cell_joint_trace_component' if joint_trace else 'v6_owner_route_trace_component' if owner_trace else 'v6_cached_trace_component' if cached_trace else 'v6_high_trace_component',args.source_sha,'a2r160_g1'):
        raise ValueError('trace component requires fresh source/a2r160_g1 root')
    if trace and budget.get('cell_joint_trace_component_attempts' if joint_trace else 'owner_route_trace_component_attempts' if owner_trace else 'cached_trace_component_attempts' if cached_trace else 'high_trace_component_attempts'):
        raise ValueError('unique high trace component already attempted')
    if amplification and Path(args.output).parts[-3:]!=('v6_bubble_amplification_diagnostic',args.source_sha,'a2r160_g1'):
        raise ValueError('amplification requires fresh source/a2r160_g1 root')
    retry=amplification_recording_retry(args,budget)
    remaining=min(selected_contract(args)['workflow_seconds'],budget['batch_remaining']) if diagnostic or projected or bubble or enriched or particular or amplification or trace else min(budget['G0_G1_remaining'],budget['batch_remaining'])
    if remaining<=0:raise RuntimeError('G1 compute budget exhausted')
    lock=budget_path.parent/('cell_joint_trace_active.lock' if joint_trace else 'owner_route_trace_active.lock' if owner_trace else 'cached_trace_active.lock' if cached_trace else 'high_trace_active.lock' if trace else 'bubble_amplification_active.lock' if amplification else 'bubble_particular_active.lock' if particular else 'bubble_enriched_active.lock' if enriched else 'bubble_local_active.lock' if bubble else 'projected_p4_active.lock' if projected else 'p4_failure_active.lock' if diagnostic else 'g1_active.lock')
    descriptor=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(descriptor)
    root=Path(args.output)
    result=None
    try:
        root.mkdir(parents=True,exist_ok=False)
        cache_home=(root/'jit_cache').resolve()
        cache_home.mkdir(exist_ok=False)
        atomic(root/'launch_plan.json',dict(source=source,contract=selected_contract(args),
            wall_seconds=remaining,budget_before=budget,recording_retry=retry,jit_cache_home=str(cache_home),
            jit_cache_initially_empty=not any(cache_home.iterdir())))
        command=[sys.executable,'-m','src.runners.physical_recursive_entry',*sys.argv[1:],'--worker']
        result=supervise(command,root/'watchdog',wall_seconds=remaining,phase_path=root/'phase.json',
            hard_stop_immediate=True,timebase_guard=True,timebase_policy=CONSERVATIVE_REALTIME,
            stop_on_global_swap=True,source_state=source,
            worker_environment={'XDG_CACHE_HOME':str(cache_home)})
        charge=result['workflow_clock_interval']['budget_seconds']
        budget.setdefault('cell_joint_trace_component_attempts' if joint_trace else 'owner_route_trace_component_attempts' if owner_trace else 'cached_trace_component_attempts' if cached_trace else 'high_trace_component_attempts' if trace else 'bubble_amplification_diagnostic_attempts' if amplification else 'bubble_particular_diagnostic_attempts' if particular else 'bubble_enriched_component_attempts' if enriched else 'bubble_local_tensor_attempts' if bubble else 'projected_p4_component_attempts' if projected else 'p4_failure_diagnostic_attempts' if diagnostic else 'g1_component_attempts',[]).append(dict(root=str(root),target=args.target,
            source=args.source_sha,classification=result['classification'],conservative_seconds=charge))
        for key in (('batch_remaining',) if diagnostic or projected or bubble or enriched or particular or amplification or trace else ('G0_G1_remaining','batch_remaining')):budget[key]-=charge
        budget['charged_including_reserve']+=charge
        atomic(budget_path,budget)
        atomic(root/'terminal.json',result)
        if diagnostic or projected or bubble or enriched or particular or amplification or trace:
            atomic(root/'source_after.json',git_state(args.source_sha))
        if result['classification']!='COMPLETED':raise SystemExit(1)
    finally:
        # An uncertain launch keeps the lock for review instead of enabling duplicate work.
        if result is not None and result.get('descendants_cleared'):lock.unlink()


if __name__=='__main__':main()
