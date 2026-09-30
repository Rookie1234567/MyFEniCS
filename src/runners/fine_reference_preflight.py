"""1800s fine-reference workflow; default symbolic-only, explicit solve opt-in."""
import argparse
import hashlib
import json
import os
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


def _task40_matched_physical_identity(direct_payload, g0_payload):
    """Allow only the reviewed assembly backend change between G0 and direct."""
    from src.io import canonical_json_bytes

    sections=('geometry','materials','incidence','discretization','boundary')
    direct={name:dict(direct_payload[name]) for name in sections}
    g0={name:dict(g0_payload[name]) for name in sections}
    if direct['discretization'].get('assembly_backend')!='assembly_time_static_condensed':
        raise ValueError('Task40 direct reference must use assembly-time static condensation')
    if g0['discretization'].get('assembly_backend')!='standard_full':
        raise ValueError('Task40 G0 witness must use the standard full assembly backend')
    direct['discretization']['assembly_backend']='standard_full'
    if direct!=g0:
        raise ValueError('Task40 direct/G0 physical sections differ beyond assembly backend')
    normalized_sha=hashlib.sha256(canonical_json_bytes(direct)).hexdigest()
    direct_physical_sha=direct_payload.get('provenance',{}).get('physical_model_sha256')
    g0_physical_sha=g0_payload.get('provenance',{}).get('physical_model_sha256')
    if not direct_physical_sha or not g0_physical_sha or normalized_sha!=g0_physical_sha:
        raise ValueError('Task40 normalized direct sections do not match the G0 physical identity')
    return dict(physical_sha256=direct_physical_sha,
        original_physical_sha256=normalized_sha,
        g0_physical_model_sha256=g0_physical_sha,
        normalized_physical_sections_sha256=normalized_sha,
        identity_difference={'discretization.assembly_backend':
            ['standard_full','assembly_time_static_condensed']})


def validate_task40_reference_inputs(input_path, payload, g0_run_directory):
    """Bind a Task40 direct input to the completed G0 run and saved A6 packet."""
    from src.io import load_and_resolve
    root=Path.cwd().resolve()
    g0=Path(g0_run_directory).resolve()
    results_root=(root/'results/task40extra_nonseparable_0p7nm').resolve()
    if not g0.is_relative_to(results_root):
        raise ValueError('Task40 G0 witness must be inside the frozen results root')
    manifest_path=g0/'run_manifest.json'
    summary_path=g0/'task40extra_nonseparable_0p7nm_p6q4_summary.json'
    final_path=g0/'final_residual/q4_final.json'
    archive_path=g0/'final_residual/q4_final.npz'
    for path in (manifest_path,summary_path,final_path,archive_path,g0/'input_original.dat'):
        if not path.is_file():raise ValueError('Task40 G0 witness artifact is missing: '+str(path))
    manifest=json.loads(manifest_path.read_text())
    summary=json.loads(summary_path.read_text())
    final=json.loads(final_path.read_text())
    final_identity=final.get('identity',{})
    g0_input=load_and_resolve(g0/'input_original.dat').as_jsonable()
    direct_sha=hashlib.sha256(Path(input_path).read_bytes()).hexdigest()
    g0_sha=hashlib.sha256((g0/'input_original.dat').read_bytes()).hexdigest()
    if manifest.get('run_id')!='task40extra_0p7nm_nonseparable_g0_iterative_review_v1':
        raise ValueError('Task40 G0 witness run_id mismatch')
    if manifest.get('source_sha')!='b8a20bd24848a83f2f4fa50b1ccaaa4ec9be9672':
        raise ValueError('Task40 G0 witness source identity mismatch')
    if manifest.get('input_sha256')!=g0_sha or final_identity.get('input_sha256')!=g0_sha:
        raise ValueError('Task40 G0 witness input hash mismatch')
    direct_physical_sha=payload.get('provenance',{}).get('physical_model_sha256')
    g0_physical_sha=g0_input.get('provenance',{}).get('physical_model_sha256')
    if (g0_physical_sha!='51854af3fb60c7ffebb166e1f06ff0a89e2e184dcbd9ba06ab4beb321b920661'
            or manifest.get('physical_model_sha256')!=g0_physical_sha
            or final_identity.get('physical_model_sha256')!=g0_physical_sha):
        raise ValueError('Task40 direct/G0 physical model identity mismatch')
    physical_identity=_task40_matched_physical_identity(payload,g0_input)
    if physical_identity['original_physical_sha256']!=g0_physical_sha:
        raise ValueError('Task40 normalized direct identity differs from the G0 physical SHA')
    if (payload.get('method',{}).get('kind')!='full3d_direct'
            or payload.get('solver',{}).get('linear_solver')!='direct'):
        raise ValueError('Task40 reference input must use full3d_direct')
    if summary.get('source_sha')!=manifest.get('source_sha') or summary.get('official_result') is not True:
        raise ValueError('Task40 G0 witness is not a completed authority-limited result')
    if summary.get('output_role')!='official_authority_limited':
        raise ValueError('Task40 G0 output role mismatch')
    archived_sha=hashlib.sha256(archive_path.read_bytes()).hexdigest()
    if (final.get('arrays',{}).get('sha256')!=archived_sha
            or summary.get('final_residual',{}).get('arrays',{}).get('sha256')!=archived_sha):
        raise ValueError('Task40 G0 final residual archive hash mismatch')
    expected_mode_sha=final_identity.get('ordered_mode_sha256')
    operator_identity=summary.get('operator_identity',{})
    mode_sha=operator_identity.get('ordered_mode_sha256')
    if not mode_sha or mode_sha!=expected_mode_sha:
        raise ValueError('Task40 G0 ordered mode identity mismatch')
    space=final_identity.get('retained_p6',{}).get('expected_space_facts',{})
    dimensions=(space.get('full_rows'),space.get('active_rows'),space.get('appended_rows'))
    if dimensions!=(229680,68256,80):
        raise ValueError('Task40 G0 p6 witness dimensions mismatch')
    map_sha=operator_identity.get('p6_native_map_sha256')
    if not map_sha:
        raise ValueError('Task40 G0 native-map identity is missing')
    if (final.get('explicit_relative_residual')!=summary.get('final_explicit_relative_residual')
            or final.get('explicit_relative_residual')>1e-6):
        raise ValueError('Task40 G0 full A6 residual witness is inconsistent')
    return dict(g0_run_directory=str(g0),g0_source_sha=manifest['source_sha'],
        g0_input_sha256=g0_sha,direct_input_sha256=direct_sha,
        physical_model_sha256=direct_physical_sha,
        g0_physical_model_sha256=g0_physical_sha,
        original_physical_sha256=physical_identity['original_physical_sha256'],
        normalized_physical_sections_sha256=physical_identity['normalized_physical_sections_sha256'],
        identity_difference=physical_identity['identity_difference'],
        ordered_mode_sha256=mode_sha,
        p6_native_map_sha256=map_sha,expected_dimensions=list(dimensions),
        final_residual_npz=str(archive_path),final_residual_npz_sha256=archived_sha,
        direct_physical_sections_match=True)


def load_task40_reference_witness(input_path, payload, g0_run_directory):
    """Load the G0 RHS, solution and independent A6 action as the witness."""
    import numpy as np
    identity=validate_task40_reference_inputs(input_path,payload,g0_run_directory)
    final_path=Path(identity['g0_run_directory'])/'final_residual/q4_final.json'
    archive_path=Path(identity['final_residual_npz'])
    final=json.loads(final_path.read_text())
    arrays={}
    with np.load(archive_path,allow_pickle=False) as archive:
        for name in ('rhs','solution','applied','residual'):
            descriptor=final.get(name,{})
            key=descriptor.get('array_key')
            if not key or key not in archive:
                raise ValueError('Task40 G0 residual archive lacks '+name)
            arrays[name]=np.array(archive[key],copy=True)
    full_rows=identity['expected_dimensions'][0]
    if any(value.shape!=(full_rows,) or value.dtype!=np.complex128
           or not np.isfinite(value).all() for value in arrays.values()):
        raise ValueError('Task40 G0 residual witness has invalid vector shape or values')
    residual_check=arrays['rhs']-arrays['applied']
    residual_difference=float(np.linalg.norm(residual_check-arrays['residual']) /
        max(np.linalg.norm(arrays['rhs']),np.finfo(float).tiny))
    measured=float(np.linalg.norm(arrays['residual']) /
        max(np.linalg.norm(arrays['rhs']),np.finfo(float).tiny))
    if residual_difference>1e-12 or abs(measured-final['explicit_relative_residual'])>1e-12:
        raise ValueError('Task40 G0 saved full A6 witness vectors fail packet arithmetic')
    witness=dict(map=None,map_identity_sha256=identity['p6_native_map_sha256'],
        rhs={'b':arrays['rhs']},control={'x':arrays['solution'],'ax':arrays['applied']},
        directory=identity['g0_run_directory'],
        evidence={key:value for key,value in identity.items()
                  if key in ('g0_source_sha','g0_input_sha256','g0_physical_model_sha256',
                      'ordered_mode_sha256','p6_native_map_sha256','expected_dimensions',
                      'final_residual_npz_sha256')},
        direct_input_identity={key:value for key,value in identity.items()
                  if key in ('direct_input_sha256','physical_model_sha256',
                      'original_physical_sha256','normalized_physical_sections_sha256',
                      'identity_difference','ordered_mode_sha256','expected_dimensions')})
    identity['g0_full_A6_residual_relative']=measured
    identity['g0_rhs_action_packet_arithmetic_relative']=residual_difference
    return witness,identity

def qualified_abi():
    import numpy as np
    from petsc4py import PETSc
    from mpi4py import MPI
    import petsc4py,slepc4py,dolfinx,mpi4py,basix
    if (os.environ.get('_MYFENICS_WSL_QUALIFIED_ACTIVATION')!='1' or
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


def _reference_process_tree_snapshot(snapshot, parent, phase, *, task40_reference):
    policy='disabled_by_profile' if task40_reference else 'sampled'
    return snapshot(parent,phase,None,pss_sampling_policy=policy)


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
    task40_reference=args.task40_witness_run_dir is not None
    witness_identity=None
    if task40_reference:
        witness,witness_identity=load_task40_reference_witness(
            args.input,payload,args.task40_witness_run_dir)
        physical_identity=dict(physical_sha256=witness_identity['physical_model_sha256'],
            original_physical_sha256=witness_identity['original_physical_sha256'],
            normalized_physical_sections_sha256=witness_identity['normalized_physical_sections_sha256'],
            identity_difference=witness_identity['identity_difference'],
            g0_witness=witness_identity)
    else:
        witness=load_reference_witness(args.witness_audit,args.witness_audit_sha) if args.solve_reference else None
        matched=witness.get('physical_model_sha256') if witness else None
        physical_identity=input_identity(payload,matched_physical_sha=matched)
    solve_reference=args.solve_reference or task40_reference
    cfg=simulation_config_3d_from_normalized(payload)
    if cfg.stage4_full3d_assembly_backend!='assembly_time_static_condensed':
        raise ValueError('existing exact-class assembly-time condensation required')
    _,mode_bytes,mode_sha=build_ordered_mode_manifest(outgoing_port_modes_3d(cfg),cfg)
    expected_mode_sha=(witness_identity['ordered_mode_sha256'] if task40_reference else
        'dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2')
    if mode_sha!=expected_mode_sha:
        raise ValueError('fine reference mode inventory differs')
    ledger=WorkflowLedger(args.directory,Path(os.environ['PHYSICAL_WATCHDOG_PHASE_PATH']))
    parent=int(os.environ['PHYSICAL_WATCHDOG_PARENT_PID'])
    launch_cap=int(os.environ['PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES'])
    memory_policy=('PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23' if task40_reference else None)
    def sample():
        if ledger.stop_signal is not None:raise InterruptedError('watchdog stop requested')
        value=_reference_process_tree_snapshot(process_tree_snapshot,parent,ledger.phase,
            task40_reference=task40_reference)
        envelope=memory_envelope(memory_policy) if memory_policy else memory_envelope()
        dynamic_cap=value['rss_bytes']+envelope['effective_available_bytes']-envelope['reserve_bytes']
        caps=[launch_cap,dynamic_cap]
        if not task40_reference:caps.append(12_000_000_000)
        value['launch_cap_bytes']=min(caps)
        value['memory_envelope']=envelope
        if (not value['all_status_readable'] or value['swap_bytes']!=0 or
                value['rss_bytes']>=value['launch_cap_bytes'] or
                envelope['effective_available_bytes']<envelope['reserve_bytes']):
            raise RuntimeError('fine reference process-tree resource gate failed')
        return value
    handlers={sig:signal.signal(sig,lambda value,_frame:setattr(ledger,'stop_signal',value))
              for sig in (signal.SIGTERM,signal.SIGINT)}
    identity=dict(source_sha=args.expected_sha,**physical_identity,mode_sha256=mode_sha,
                  input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),abi=abi,
                  task40_reference=task40_reference)
    if task40_reference:
        identity['expected_dimensions']=witness_identity['expected_dimensions']
        witness['direct_input_identity']['source_sha']=args.expected_sha
    record=dict(status='PREFLIGHT_STARTED',identity=identity,numeric_called=False,solve_called=False)
    def save(name,value):_atomic_json(args.directory/(name+'.json'),value)
    try:
        if solve_reference:
            from .physical_diagnosis_worker import save_packet
            from src.solvers.condensed_fine_reference import MatchedFineReference
            if not task40_reference:
                witness=load_reference_witness(args.witness_audit,args.witness_audit_sha)
            def canonical(field,floquet):
                from benchmarks.canonical_vector_artifacts import write_canonical_packet_shard
                from src.solvers.hcurl_canonical_vector_dolfinx import iter_canonical_full_fe_packets
                return write_canonical_packet_shard(args.directory/'canonical_reference.rank0000.jsonl',
                    iter_canonical_full_fe_packets(field.function_space,field,floquet),audit_packets=True)
            if task40_reference:
                from .physical_balanced_output import compare_task40_direct_reference
                callback=lambda native,x: compare_task40_direct_reference(
                    native,x,witness,args.directory,identity)
                expected_dimensions=tuple(witness_identity['expected_dimensions'])
            else:
                from .physical_balanced_output import compare_notch_reference
                callback=(lambda native,x: compare_notch_reference(native,x,witness,args.directory)) if physical_identity else None
                expected_dimensions=None
            observer=MatchedFineReference(sample=sample,marker=ledger.marker,identity=identity,witness=witness,
                save=lambda name,value:save_packet(args.directory,name,value),canonical_export=canonical,
                output_callback=callback,expected_dimensions=expected_dimensions)
        else:
            observer=CondensedSymbolicPreflight(sample=sample,save=save,marker=ledger.marker,identity=identity)
        _atomic_json(args.directory/'input_resolved.json',payload)
        (args.directory/'mode_manifest.json').write_bytes(mode_bytes)
        initial_resource=sample()
        if task40_reference:
            envelope=initial_resource['memory_envelope']
            _atomic_json(args.directory/'resource_policy.json',dict(
                schema='task40extra.direct-reference-resource-policy.v1',
                policy='PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23',
                pss='DISABLED_BY_PROFILE',process_tree_swap_limit_bytes=0,
                memory_cap='live effective available memory minus 128 MiB evidence reserve',
                initial_effective_total_bytes=envelope['effective_total_bytes'],
                initial_effective_available_bytes=envelope['effective_available_bytes'],
                initial_reserve_bytes=envelope['reserve_bytes'],
                initial_dynamic_launch_cap_bytes=initial_resource['launch_cap_bytes'],
                initial_process_tree_rss_bytes=initial_resource['rss_bytes'],
                initial_process_tree_swap_bytes=initial_resource['swap_bytes'],
                cgroup_limits=envelope['cgroup_limits'],time_policy='observe_only'))
        ledger.marker('fine_reference_assembly_started',identity)
        run_stage4b_block_grating_3d_case(cfg,args.directory/'assembly',
            linear_solver_port=observer,
            diagnostic_reference_incident_quadrature=solve_reference)
        raise RuntimeError('reference observer unexpectedly returned a solver snapshot')
    except CondensedPreflightExit as stop:
        record=stop.record
        if stop.error is not None:raise stop.error
        if record.get('cleanup_errors'):raise RuntimeError('symbolic preflight cleanup failed')
        record_post_release(record,sample,failure_status='REFERENCE_FAILED' if solve_reference else 'SYMBOLIC_PREFLIGHT_FAILED')
    except BaseException as exc:
        record.update(status='REFERENCE_FAILED' if solve_reference else 'SYMBOLIC_PREFLIGHT_FAILED',primary_error=dict(
            type=type(exc).__name__,message=str(exc)))
        raise
    finally:
        try:save('reference_summary' if solve_reference else 'preflight_summary',record)
        finally:
            for sig,handler in handlers.items():signal.signal(sig,handler)


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
    parser.add_argument('--task40-witness-run-dir',type=Path)
    parser.add_argument('--workflow-seconds',type=float,default=1800)
    args=parser.parse_args(argv)
    task40_reference=args.task40_witness_run_dir is not None
    solve_reference=args.solve_reference or task40_reference
    maximum=43200 if task40_reference else 3600
    if not 0<args.workflow_seconds<=maximum:
        parser.error(f'reference budget must be positive and at most {maximum}')
    if args.workflow_seconds>1800 and not solve_reference:
        parser.error('extended budget only for conditional reference solve')
    if args.solve_reference and task40_reference:
        parser.error('choose either the legacy audit or the Task40 G0 witness')
    if args.solve_reference and (args.witness_audit is None or args.witness_audit_sha is None):
        parser.error('reference solve requires hash-bound frozen witness audit')
    _physical_source_gate(Path.cwd(),args.expected_sha)
    if args.worker:run_worker(args);return 0
    args.directory.mkdir(parents=True,exist_ok=False)
    start=clock_sample();before=ClockBudget(start,policy=CONSERVATIVE_REALTIME)
    manifest=dict(source_sha=args.expected_sha,clock_start=start,workflow_limit_seconds=args.workflow_seconds,
        numeric_called=None if solve_reference else False,solve_called=None if solve_reference else False,
        time_policy='observe_only' if task40_reference else 'enforce',
        kind='task40_reference' if task40_reference else
             ('fine_reference_solve' if solve_reference else 'fine_reference_symbolic_only'))
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
        if args.solve_reference:
            command.extend(['--solve-reference','--witness-audit',str(args.witness_audit),
                            '--witness-audit-sha',args.witness_audit_sha])
        if task40_reference:
            command.extend(['--task40-witness-run-dir',str(args.task40_witness_run_dir)])
        manifest['command']=command;_atomic_json(args.directory/'launch.json',manifest)
        result=supervise_diagnosis(command,args.directory/'watchdog',
            phase_path=args.directory/'phase.json',expected_sha=args.expected_sha,
            kind='task40_reference' if task40_reference else
                 ('reference' if solve_reference else 'reference_symbolic'),
            remaining_seconds=args.workflow_seconds-before.update(clock_sample())['budget_seconds'],
            cache_path=args.cache_path,
            memory_policy='PHYSICAL_MEMORY_PRESSURE_LOCAL_MUMPS_V23' if task40_reference else None,
            pss_sampling_policy='disabled_by_profile' if task40_reference else 'sampled',
            time_policy='observe_only' if task40_reference else None)
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
        if solve_reference:
            summary_path=args.directory/'reference_summary.json'
            if summary_path.exists():
                terminal=json.loads(summary_path.read_text())
                manifest.update(worker_status=terminal['status'],numeric_called=terminal.get('numeric_called'),
                                solve_called=terminal.get('solve_called'))
                if manifest['classification']=='COMPLETED' and terminal['status']!='REFERENCE_PASS':
                    manifest['classification']='REFERENCE_NOT_QUALIFIED'
            elif manifest['classification']=='COMPLETED':manifest['classification']='REFERENCE_EVIDENCE_MISSING'
        if (not task40_reference and manifest['charged_seconds']>args.workflow_seconds
                and manifest['classification']=='COMPLETED'):
            manifest['classification']='PERFORMANCE_CONTROLLED_STOP'
        _atomic_json(args.directory/'launch.json',manifest)
    return 0 if manifest['classification']=='COMPLETED' else 2


if __name__=='__main__':raise SystemExit(main())
