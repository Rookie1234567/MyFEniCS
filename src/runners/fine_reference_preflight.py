"""1800s fine-reference workflow; default symbolic-only, explicit solve opt-in."""
import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import signal
import subprocess
import sys

from .physical_intermediate import WorkflowLedger, _atomic_json
from .workflow_timebase import ClockBudget, clock_sample, CONSERVATIVE_REALTIME


def input_identity(payload, *, matched_physical_sha=None):
    """Keep the real input hash; compare the sole reviewed backend difference."""
    from src.io import canonical_json_bytes
    physical=payload['provenance']['physical_model_sha256']
    if matched_physical_sha is None and physical!='2d9fed2466c96f0db124ceb229eb937df0e49654a3bae17772ab70d4441a061d':
        raise ValueError('fine reference input identity differs')
    sections={name:dict(payload[name]) for name in
              ('geometry','materials','incidence','discretization','boundary')}
    if sections['discretization']['assembly_backend']!='assembly_time_static_condensed':
        raise ValueError('assembly-time condensation required')
    sections['discretization']['assembly_backend']='standard_full'
    original=hashlib.sha256(canonical_json_bytes(sections)).hexdigest()
    if original!=(matched_physical_sha or '9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f'):
        raise ValueError('original physical fields differ beyond assembly backend')
    return dict(physical_sha256=physical,original_physical_sha256=original,
                identity_difference={'discretization.assembly_backend':
                    ['standard_full','assembly_time_static_condensed']})


def qualified_abi():
    import numpy as np
    from petsc4py import PETSc
    from mpi4py import MPI
    import petsc4py,slepc4py,dolfinx,mpi4py,basix
    if ((os.environ.get('_MYFENICS_WSL_QUALIFIED_ACTIVATION')!='1' and
         os.environ.get('_MYFENICS_NATIVE_QUALIFIED_ACTIVATION')!='1') or
            not os.path.samefile(sys.executable,'.venv/bin/python') or
            PETSc.ScalarType is not np.complex128 or PETSc.IntType is not np.int32 or
            MPI.COMM_WORLD.size!=1 or 'Open MPI' not in MPI.Get_library_version()):
        raise RuntimeError('qualified MPI1 complex128/int32 ABI required')
    threads={k:os.environ.get(k) for k in ('OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')}
    if set(threads.values())!={'1'}:raise RuntimeError('all thread limits must be one')
    return dict(python=sys.executable,scalar='complex128',integer='int32',threads=threads,
        modules={m.__name__:dict(path=m.__file__,version=getattr(m,'__version__',None))
                 for m in (petsc4py,slepc4py,dolfinx,mpi4py,basix)})


def record_post_release(record, sample, *, failure_status='SYMBOLIC_PREFLIGHT_FAILED'):
    """A failed final resource sample must not leave a successful summary."""
    try:
        record['after_release_resource']=sample()
    except Exception as exc:
        record.update(status=failure_status,primary_error=dict(
            type=type(exc).__name__,message=str(exc)))
        raise


def load_reference_witness(audit_path,expected_hash):
    """Bind the one frozen A2R160 action/RHS/native map through its old audit."""
    from .physical_diagnostic_completion import load_packet
    if hashlib.sha256(audit_path.read_bytes()).hexdigest()!=expected_hash:
        raise ValueError('reference witness audit hash mismatch')
    audit=json.loads(audit_path.read_text())
    if audit.get('schema') == 'balanced-notch-reference-witness.v1':
        witness = Path(audit['packet'])
        if hashlib.sha256(witness.read_bytes()).hexdigest() != audit['packet_sha256']:
            raise ValueError('notch witness hash mismatch')
        result = load_packet(witness)
        result['evidence'] = dict(audit_path=str(audit_path),audit_sha256=expected_hash)
        return result
    indexed={entry['path']:entry['sha256'] for entry in audit['evidence']}
    root=Path(audit['root']);result={};evidence=[]
    for key,name in (('map','native_constraint_map_p6'),('rhs','rhs'),('control','A2R160_identity')):
        path=root/(name+'.json');digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if indexed.get(str(path))!=digest:raise ValueError('reference witness packet mismatch: '+name)
        result[key]=load_packet(path)
        evidence.append(dict(path=str(path),sha256=digest))
    result['evidence']=dict(audit_path=str(audit_path),audit_sha256=expected_hash,packets=evidence)
    return result


def run_worker(args):
    from benchmarks.subreaper_watchdog import memory_envelope
    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.condensed_reference_preflight import CondensedSymbolicPreflight, CondensedPreflightExit
    from src.solvers.solve_maxwell_3d_stage_4b_block_grating import run_stage4b_block_grating_3d_case
    from src.solvers.fullspace_dtn_action import build_ordered_mode_manifest
    from src.common.modes_3d import outgoing_port_modes_3d
    abi=qualified_abi()
    if os.environ.get('PHYSICAL_TIMEBASE_GUARD')!='1':raise RuntimeError('watchdog clock guard required')
    payload=load_and_resolve(args.input).as_jsonable()
    witness = load_reference_witness(args.witness_audit,args.witness_audit_sha) if args.solve_reference else None
    matched = witness.get('physical_model_sha256') if witness else None
    physical_identity=input_identity(payload,matched_physical_sha=matched)
    cfg=simulation_config_3d_from_normalized(payload)
    if cfg.stage4_full3d_assembly_backend!='assembly_time_static_condensed':
        raise ValueError('existing exact-class assembly-time condensation required')
    _,mode_bytes,mode_sha=build_ordered_mode_manifest(outgoing_port_modes_3d(cfg),cfg)
    mode_bridge = None
    if args.native_matched_reference:
        from src.solvers.native_mode_identity import compare_mode_manifest
        mode_bridge = compare_mode_manifest(mode_bytes)
    elif mode_sha!='dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2':
        raise ValueError('fine reference mode inventory differs')
    ledger=WorkflowLedger(args.directory,Path(os.environ['PHYSICAL_WATCHDOG_PHASE_PATH']))
    parent=int(os.environ['PHYSICAL_WATCHDOG_PARENT_PID'])
    launch_cap=int(os.environ['PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES'])
    def sample():
        if ledger.stop_signal is not None:raise InterruptedError('watchdog stop requested')
        value=process_tree_snapshot(parent,ledger.phase,None);envelope=memory_envelope()
        profile_cap = launch_cap if args.native_matched_reference else min(launch_cap,12_000_000_000)
        value['launch_cap_bytes']=min(profile_cap, envelope.get('launch_cap_bytes',profile_cap),
            value['rss_bytes']+envelope['effective_available_bytes']-envelope['reserve_bytes'])
        if args.native_matched_reference:
            value['numeric_planning_cap_bytes']=int(envelope['planning_cap_bytes'])
        value['memory_envelope']=envelope
        if (not value['all_status_readable'] or value['swap_bytes']!=0 or
                value['rss_bytes']>=value['launch_cap_bytes'] or
                envelope['effective_available_bytes']<envelope['reserve_bytes']):
            raise RuntimeError('fine reference process-tree resource gate failed')
        return value
    handlers={sig:signal.signal(sig,lambda value,_frame:setattr(ledger,'stop_signal',value))
              for sig in (signal.SIGTERM,signal.SIGINT)}
    identity=dict(source_sha=args.expected_sha,**physical_identity,mode_sha256=mode_sha,
                  input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),abi=abi)
    if mode_bridge is not None:
        identity['native_mode_bridge'] = mode_bridge
    record=dict(status='PREFLIGHT_STARTED',identity=identity,numeric_called=False,solve_called=False)
    def save(name,value):_atomic_json(args.directory/(name+'.json'),value)
    try:
        if args.solve_reference:
            from .physical_diagnosis_worker import save_packet
            from src.solvers.condensed_fine_reference import MatchedFineReference
            witness=load_reference_witness(args.witness_audit,args.witness_audit_sha)
            def canonical(field,floquet):
                from benchmarks.canonical_vector_artifacts import write_canonical_packet_shard
                from src.solvers.hcurl_canonical_vector_dolfinx import iter_canonical_full_fe_packets
                return write_canonical_packet_shard(args.directory/'canonical_reference.rank0000.jsonl',
                    iter_canonical_full_fe_packets(field.function_space,field,floquet),audit_packets=True)
            from .physical_balanced_output import compare_notch_reference
            observer=MatchedFineReference(sample=sample,marker=ledger.marker,identity=identity,witness=witness,
                save=lambda name,value:save_packet(args.directory,name,value),canonical_export=canonical,
                output_callback=(lambda native,x: compare_notch_reference(native,x,witness,args.directory,
                    native_opt_in=args.native_matched_reference))
                    if matched else None)
        else:
            observer=CondensedSymbolicPreflight(sample=sample,save=save,marker=ledger.marker,identity=identity)
        _atomic_json(args.directory/'input_resolved.json',payload)
        (args.directory/'mode_manifest.json').write_bytes(mode_bytes)
        sample();ledger.marker('fine_reference_assembly_started',identity)
        run_stage4b_block_grating_3d_case(cfg,args.directory/'assembly',
            linear_solver_port=observer,
            diagnostic_reference_incident_quadrature=args.solve_reference)
        raise RuntimeError('reference observer unexpectedly returned a solver snapshot')
    except CondensedPreflightExit as stop:
        record=stop.record
        if stop.error is not None:raise stop.error
        if record.get('cleanup_errors'):raise RuntimeError('symbolic preflight cleanup failed')
        record_post_release(record,sample,failure_status='REFERENCE_FAILED' if args.solve_reference else 'SYMBOLIC_PREFLIGHT_FAILED')
    except BaseException as exc:
        record.update(status='REFERENCE_FAILED' if args.solve_reference else 'SYMBOLIC_PREFLIGHT_FAILED',primary_error=dict(
            type=type(exc).__name__,message=str(exc)))
        raise
    finally:
        try:save('reference_summary' if args.solve_reference else 'preflight_summary',record)
        finally:
            for sig,handler in handlers.items():signal.signal(sig,handler)


def launch_native_matched_reference(specification):
    """Run the existing fine-reference workflow under the native guard."""
    from .native_capacity import native_capacity_guard
    from .task038_launcher import _physical_source_gate, _source_sha

    root = Path(__file__).resolve().parents[2]
    source = _source_sha(root)
    _physical_source_gate(root, source)
    witness = Path(specification.solver['reference_witness_path'])
    if not witness.is_absolute():
        witness = root / witness
    if not witness.is_file():
        raise ValueError(f'reference witness audit is missing: {witness}')
    witness_sha = specification.solver['reference_witness_sha256']
    if hashlib.sha256(witness.read_bytes()).hexdigest() != witness_sha:
        raise ValueError('reference witness audit hash mismatch before launch')
    parent = Path(specification.expected_output_parent).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    directory = parent / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    if directory.exists():
        raise ValueError(f'reference output collision: {directory}')
    cache = directory / 'reference_cache'
    argv = [
        '--input', str(specification.source_path),
        '--directory', str(directory),
        '--expected-sha', source,
        '--cache-path', str(cache),
        '--solve-reference',
        '--witness-audit', str(witness),
        '--witness-audit-sha', witness_sha,
        '--workflow-seconds', str(specification.execution['timeout_seconds']),
        '--native-matched-reference',
    ]
    with native_capacity_guard('balanced_h6_p4_native_13p5') as (_root, isolation):
        exit_code = main(argv)
        isolation['reference_profile'] = specification.solver['direct_solver_profile']
        _atomic_json(directory / 'workstation_isolation.json', isolation)
    launch_path = directory / 'launch.json'
    launch = json.loads(launch_path.read_text())
    summary_path = directory / 'reference_summary.json'
    terminal = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    qualified = launch.get('classification') == 'COMPLETED' and terminal.get('status') == 'REFERENCE_PASS'
    result_classification = 'worker_exit0' if qualified and exit_code == 0 else launch.get('classification', 'reference_launch_failed')
    result = {
        'run_directory': str(directory),
        'manifest': str(directory / 'run_manifest.json'),
        'summary': str(directory / 'run_summary.json'),
        'exit_status': 0 if result_classification == 'worker_exit0' else exit_code,
        'result_classification': result_classification,
        'resource_authority': launch.get('supervision', {}),
        'reference_status': terminal.get('status'),
    }
    _atomic_json(directory / 'run_manifest.json', {
        'schema': 'native-matched-reference.launch.v1',
        'source_sha': source,
        'input_path': str(specification.source_path),
        'input_sha256': specification.input_sha256,
        'resolved_physical_model_sha256': specification.physical_model_sha256,
        'direct_solver_profile': specification.solver['direct_solver_profile'],
        'workflow_seconds': specification.execution['timeout_seconds'],
        'native_capacity_profile': 'balanced_h6_p4_native_13p5',
        'supervisor_cpu': 9,
        'worker_cpu': 23,
        'identity_package': 'input_original.dat, resolved_config.json, source_sha.txt, input_sha256.txt, physical_model_sha256.txt',
        'resolved_config_sha256': hashlib.sha256((directory/'resolved_config.json').read_bytes()).hexdigest(),
        'global_swap_supervision': True,
        'witness_audit_path': str(witness),
        'witness_audit_sha256': witness_sha,
        'launch_manifest_sha256': hashlib.sha256(launch_path.read_bytes()).hexdigest(),
        'result_classification': result_classification,
    })
    _atomic_json(directory / 'run_summary.json', result)
    return result


def main(argv=None):
    if sys.argv[1:]==['--abi']:
        print(json.dumps(qualified_abi()));return 0
    from .physical_diagnosis import supervise_diagnosis
    from .task038_launcher import _physical_source_gate
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--directory',type=Path,required=True)
    parser.add_argument('--expected-sha',required=True)
    parser.add_argument('--cache-path',type=Path)
    parser.add_argument('--worker',action='store_true')
    parser.add_argument('--solve-reference',action='store_true')
    parser.add_argument('--witness-audit',type=Path)
    parser.add_argument('--witness-audit-sha')
    parser.add_argument('--native-matched-reference',action='store_true')
    parser.add_argument('--workflow-seconds',type=float,default=1800)
    args=parser.parse_args(argv)
    maximum = 21600 if args.native_matched_reference else 3600
    if not 0<args.workflow_seconds<=maximum:
        parser.error(f'reference budget must be positive and at most{maximum}')
    if args.workflow_seconds>1800 and not args.solve_reference:
        parser.error('extended budget only for conditional reference solve')
    if args.native_matched_reference and not args.solve_reference:
        parser.error('native_matched_reference requires --solve-reference')
    if args.solve_reference and (args.witness_audit is None or args.witness_audit_sha is None):
        parser.error('reference solve requires hash-bound frozen witness audit')
    _physical_source_gate(Path.cwd(),args.expected_sha)
    if args.worker:run_worker(args);return 0
    args.directory.mkdir(parents=True,exist_ok=False)
    if args.cache_path is not None:
        args.cache_path.mkdir(parents=True,exist_ok=True)
    native_identity = None
    if args.native_matched_reference:
        from src.io import load_and_resolve
        from src.io.resolved_config import write_resolved_config
        native_identity = load_and_resolve(args.input)
        resolved_sha = write_resolved_config(native_identity,args.directory/'resolved_config.json')
        (args.directory/'input_original.dat').write_bytes(native_identity.raw_input_bytes)
        (args.directory/'input_sha256.txt').write_text(native_identity.input_sha256+'\n',encoding='ascii')
        (args.directory/'source_sha.txt').write_text(args.expected_sha+'\n',encoding='ascii')
        (args.directory/'physical_model_sha256.txt').write_text(native_identity.physical_model_sha256+'\n',encoding='ascii')
    else:
        resolved_sha = None
    start=clock_sample();before=ClockBudget(start,policy=CONSERVATIVE_REALTIME)
    manifest=dict(source_sha=args.expected_sha,clock_start=start,workflow_limit_seconds=args.workflow_seconds,
        numeric_called=None if args.solve_reference else False,solve_called=None if args.solve_reference else False,
        kind='native_matched_reference' if args.native_matched_reference else
             ('fine_reference_solve' if args.solve_reference else 'fine_reference_symbolic_only'),
        native_mode_opt_in=args.native_matched_reference)
    result=None;after=None
    try:
        # MPI is imported only in this subprocess, which exits before watchdog starts.
        manifest['abi']=json.loads(subprocess.check_output(
            [sys.executable,'-m','src.runners.fine_reference_preflight','--abi'],text=True))
        manifest['input_sha256']=hashlib.sha256(args.input.read_bytes()).hexdigest()
        manifest['cache_before']=[]
        if args.cache_path is not None:
            for path in sorted(args.cache_path.rglob('*')):
                if path.is_file():manifest['cache_before'].append(dict(path=str(path),
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size))
        command=['mpiexec','-n','1',sys.executable,'-m','src.runners.fine_reference_preflight',
            '--worker','--input',str(args.input),'--directory',str(args.directory),
            '--expected-sha',args.expected_sha,'--workflow-seconds',str(args.workflow_seconds)]
        if args.native_matched_reference:
            command=['/usr/bin/taskset','-c','23',*command]
        if args.solve_reference:
            command.extend(['--solve-reference','--witness-audit',str(args.witness_audit),
                            '--witness-audit-sha',args.witness_audit_sha])
        if args.native_matched_reference:
            command.append('--native-matched-reference')
        manifest['command']=command
        if native_identity is not None:
            manifest.update(input_sha256=native_identity.input_sha256,
                            physical_model_sha256=native_identity.physical_model_sha256,
                            resolved_config_sha256=resolved_sha,
                            identity_package='input_original.dat, resolved_config.json, source_sha.txt, input_sha256.txt, physical_model_sha256.txt',
                            native_capacity_profile='balanced_h6_p4_native_13p5',
                            supervisor_cpu=9,worker_cpu=23,
                            global_swap_supervision=True)
            _atomic_json(args.directory/'run_manifest.json',dict(
                schema='native-matched-reference.launch.v1',status='launching',**manifest))
        _atomic_json(args.directory/'launch.json',manifest)
        result=supervise_diagnosis(command,args.directory/'watchdog',
            phase_path=args.directory/'phase.json',expected_sha=args.expected_sha,
            kind='native_matched_reference' if args.native_matched_reference else
                 ('reference' if args.solve_reference else 'reference_symbolic'),
            remaining_seconds=args.workflow_seconds-before.update(clock_sample())['budget_seconds'],
            cache_path=args.cache_path)
        manifest['supervision']=result;manifest['pre_interval']=before.update(result['clock_start'])
        after=ClockBudget(result['clock_end'],policy=CONSERVATIVE_REALTIME)
    except BaseException as exc:
        manifest.update(classification='PREFLIGHT_LAUNCH_FAILED',exception=dict(type=type(exc).__name__,message=str(exc)))
        raise
    finally:
        end=clock_sample();manifest['clock_end']=end
        if result is not None and after is not None:
            manifest['post_interval']=after.update(end)
            manifest['charged_seconds']=before.seconds+result['workflow_clock_interval']['budget_seconds']+after.seconds
        else:manifest['charged_seconds']=before.update(end)['budget_seconds']
        manifest.setdefault('classification',result['classification'] if result else 'PREFLIGHT_LAUNCH_FAILED')
        if args.solve_reference:
            summary_path=args.directory/'reference_summary.json'
            if summary_path.exists():
                terminal=json.loads(summary_path.read_text())
                manifest.update(worker_status=terminal['status'],numeric_called=terminal.get('numeric_called'),
                                solve_called=terminal.get('solve_called'))
                if manifest['classification']=='COMPLETED' and terminal['status']!='REFERENCE_PASS':
                    manifest['classification']='REFERENCE_NOT_QUALIFIED'
            elif manifest['classification']=='COMPLETED':manifest['classification']='REFERENCE_EVIDENCE_MISSING'
        if manifest['charged_seconds']>args.workflow_seconds and manifest['classification']=='COMPLETED':
            manifest['classification']='PERFORMANCE_CONTROLLED_STOP'
        _atomic_json(args.directory/'launch.json',manifest)
    return 0 if manifest['classification']=='COMPLETED' else 2


if __name__=='__main__':raise SystemExit(main())
