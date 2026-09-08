"""One V5 output-only recovery from the hash-bound successful terminal field."""
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

import numpy as np

from .physical_intermediate import WorkflowLedger, _atomic_json
from .workflow_timebase import ClockBudget, clock_sample, CONSERVATIVE_REALTIME

ORIGINAL_SOURCE = '2bb6770ad00b35881558c576e7296e250656e571'
PROBES = {'top_probe_z_nm': 127.5, 'bottom_probe_z_nm': -7.5}


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def validate_output_only(old, new):
    """Only the two reviewed external probe coordinates may differ."""
    for key in old.keys() | new.keys():
        if key == 'provenance':
            continue
        a, b = copy.deepcopy(old.get(key)), copy.deepcopy(new.get(key))
        if key == 'output':
            for name, value in PROBES.items():
                if b.get(name) != value:
                    raise ValueError('recovery probe differs from reviewed geometry rule')
                a[name] = value
        if a != b:
            raise ValueError('recovery changed non-output identity: ' + key)
    if old['provenance']['physical_model_sha256'] != new['provenance']['physical_model_sha256']:
        raise ValueError('recovery physical identity changed')


def validate_origin(root, audit_path, audit_sha, payload):
    if digest(audit_path) != audit_sha:
        raise ValueError('terminal audit hash mismatch')
    audit = json.loads(Path(audit_path).read_text())
    if Path(audit['run_directory']).resolve() != root.resolve() or audit['source_sha'] != ORIGINAL_SOURCE:
        raise ValueError('original run/source mismatch')
    for name, expected in audit['artifact_sha256'].items():
        path = (root/name).resolve()
        if not path.is_relative_to(root.resolve()) or digest(path) != expected:
            raise ValueError('original raw evidence changed: ' + name)
    old = json.loads((root/'resolved_config.json').read_text())
    validate_output_only(old, payload)
    summary = json.loads((root/'physical_intermediate_summary.json').read_text())
    manifest = json.loads((root/'run_manifest.json').read_text())
    parent = json.loads((root/'run_summary.json').read_text())
    if (manifest['source_sha'] != ORIGINAL_SOURCE or summary['source_sha'] != ORIGINAL_SOURCE or
            manifest['resolved_config_sha256'] != digest(root/'resolved_config.json') or
            manifest['input_sha256'] != digest(root/'input_original.dat') or
            manifest['physical_model_sha256'] != payload['provenance']['physical_model_sha256'] or
            manifest['mpi_size'] != 1 or not parent['resource_authority']['descendants_cleared'] or
            parent['resource_authority']['remaining_child_pids']):
        raise ValueError('original manifest or cleanup identity mismatch')
    solve = summary['solve']
    if (summary['failed_phase'] != 'recovery' or solve['status'] != 'TRUE_RESIDUAL_PASS' or
            solve['iterations'] != 564 or not solve['zero_start'] or
            not 0 <= solve['final_true_residual'] <= 1e-6 or
            any(solve[k] != 1 for k in ('ksp_create_count','ksp_solve_count','ksp_destroy_count'))):
        raise ValueError('not the reviewed successful terminal solve')
    return summary, audit


def fresh_root(directory, original):
    directory, original = Path(directory).resolve(), Path(original).resolve()
    if directory.is_relative_to(original) or original.is_relative_to(directory):
        raise ValueError('recovery root must be disjoint from original raw')
    directory.mkdir(parents=True, exist_ok=False)


def restore_field(fine, rhs, original, summary, quadrature, comm):
    from src.solvers.fullspace_memory_first_krylov import read_solution_checkpoint
    from src.solvers.fullspace_physical_intermediate import apply_owned
    raw = summary['residual_arrays']
    operator = hashlib.sha256(json.dumps(dict(source_sha=ORIGINAL_SOURCE,
        physical=raw['physical_model_sha256'], modes=fine['mode_sha256'],
        quadrature=quadrature), sort_keys=True).encode()).hexdigest()
    if operator != raw['operator_identity_sha256'] or fine['mode_sha256'] != summary['mode_sha256']:
        raise ValueError('rebuilt A/mode/quadrature identity mismatch')
    checkpoint = summary['last_safe_checkpoint']['checkpoint']
    path = original/'checkpoints/iteration_000564'
    if Path(checkpoint['manifest_path']).resolve() != (path/'manifest.json').resolve():
        raise ValueError('terminal checkpoint path mismatch')
    expected = dict(iteration=564, explicit_true_residual=checkpoint['explicit_true_residual'],
        input_identity_sha256=raw['input_sha256'], operator_identity_sha256=operator,
        physical_model_sha256=raw['physical_model_sha256'], source_sha=ORIGINAL_SOURCE,
        mpi_size=1, manifest_sha256=checkpoint['manifest_sha256'])
    solution, action = rhs.duplicate(), None
    try:
        read_solution_checkpoint(path, solution, expected=expected, comm=comm,
            ownership=dict(rank=0, ownership_range=list(solution.getOwnershipRange()),
                           local_size=solution.getLocalSize(), global_size=solution.getSize()))
        if hashlib.sha256(solution.array.tobytes()).hexdigest() != summary['final_solution_sha256']:
            raise ValueError('terminal solution hash mismatch')
        action = apply_owned(fine['physical_action'], solution)
        with np.load(original/raw['filename'], allow_pickle=False) as arrays:
            if not np.array_equal(solution.array, arrays['solution']):
                raise ValueError('terminal checkpoint/raw solution mismatch')
            checks = {name:float(np.linalg.norm(value-arrays[name])/max(np.linalg.norm(arrays[name]),np.finfo(float).tiny))
                      for name,value in [('rhs',rhs.array),('action',action.array)]}
        residual = float(np.linalg.norm(rhs.array-action.array)/np.linalg.norm(rhs.array))
        if not np.isfinite([*checks.values(),residual]).all() or max(checks.values()) > 1e-10 or residual > 1e-6:
            raise ValueError('recovery original A/b/true residual gate failed')
        return solution, action, dict(checks=checks,full_explicit_true_residual=residual,
                                     operator_identity_sha256=operator)
    except BaseException:
        solution.destroy()
        if action is not None:
            action.destroy()
        raise


def run_worker(args):
    from mpi4py import MPI
    from benchmarks.subreaper_watchdog import memory_envelope
    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
    from src.io import load_and_resolve
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.fullspace_same_mesh_hcurl_pmg_global import _build_same_mesh_levels
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import (
        build_same_mesh_physical_action, destroy_same_mesh_physical_action, build_physical_rhs, recover_p0_outputs)
    from src.solvers.fullspace_physical_intermediate_runtime import fine_volume_quadrature_metadata
    from .fine_reference_preflight import qualified_abi
    from .physical_balanced_output import compare_balanced_output
    qualified_abi()
    if os.environ.get('PHYSICAL_TIMEBASE_GUARD') != '1':
        raise RuntimeError('dedicated watchdog required')
    payload = load_and_resolve(args.input).as_jsonable()
    old, _ = validate_origin(args.original, args.audit, args.audit_sha, payload)
    summary = copy.deepcopy(old)
    for key in ('exception_type','exception_message','failed_phase','failed_stage'):
        summary.pop(key, None)
    summary.update(status='RECOVERY_STARTED', official_result=None,
        recovery=dict(original_directory=str(args.original), original_source_sha=ORIGINAL_SOURCE,
            recovery_source_sha=args.expected_sha, original_audit_sha256=args.audit_sha,
            original_audit_path=str(args.audit),
            new_factor_count=0,new_pc_count=0,new_ksp_count=0))
    ledger = WorkflowLedger(args.directory,Path(os.environ['PHYSICAL_WATCHDOG_PHASE_PATH']))
    parent = int(os.environ['PHYSICAL_WATCHDOG_PARENT_PID'])
    cap = int(os.environ['PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES'])
    def sample():
        value = process_tree_snapshot(parent,ledger.phase,None); envelope = memory_envelope()
        if (ledger.stop_signal is not None or not value['all_status_readable'] or value['swap_bytes'] != 0 or
                value['rss_bytes'] >= cap or envelope['effective_available_bytes'] < envelope['reserve_bytes']):
            raise RuntimeError('recovery resource/stop gate failed')
        return value
    ledger.resource_sample = sample
    handlers = {s:signal.signal(s,lambda value,_frame:setattr(ledger,'stop_signal',value))
                for s in (signal.SIGTERM,signal.SIGINT)}
    fine = rhs = solution = action = None
    try:
        cfg = simulation_config_3d_from_normalized(payload)
        from src.postprocessing.diffraction_3d import _probe_z_locations
        _probe_z_locations(cfg)
        ledger.marker('recovery_fine_only_started',{})
        levels = _build_same_mesh_levels(cfg,MPI.COMM_WORLD,(6,),include_positive_coefficients=False)
        quadrature,_ = fine_volume_quadrature_metadata(levels,cfg)
        fine = build_same_mesh_physical_action(levels,cfg,6,volume_quadrature_metadata=quadrature)
        rhs,_ = build_physical_rhs(fine)
        solution,action,identity = restore_field(fine,rhs,args.original,old,quadrature,MPI.COMM_WORLD)
        summary['recovery']['identity'] = identity
        raw = args.directory/'final_residual_arrays.npz'
        np.savez(raw,rhs=rhs.array,action=action.array,solution=solution.array)
        summary['residual_arrays']['sha256'] = digest(raw)
        # These are immutable copies of the original solve evidence, not new calls.
        for name in ('pc_applies.jsonl','p4_decisions.jsonl','monitor_residuals.jsonl'):
            shutil.copyfile(args.original/name,args.directory/name)
        _atomic_json(args.directory/'resolved_config.json',payload)
        ledger.set_phase('recovery')
        def canonical(field,out_dir):
            from benchmarks.canonical_vector_artifacts import write_canonical_packet_shard
            from src.solvers.hcurl_canonical_vector_dolfinx import iter_canonical_full_fe_packets
            return write_canonical_packet_shard(out_dir/'canonical_solution.rank0000.jsonl',
                iter_canonical_full_fe_packets(field.function_space,field,levels['floquets'][6]),audit_packets=True)
        outputs = recover_p0_outputs(fine,solution,args.directory/'numerical_output',
                                     canonical_export=canonical,export_all_port_modes=True)
        summary['official_result'] = outputs
        summary['matched_reference'] = compare_balanced_output(fine,solution,outputs,args.directory,payload,
            marker=ledger.marker,sample=sample)
        summary['status'] = 'RESIDUAL_PASS'
        ledger.set_phase('checker')
        summary['elapsed_conservative_seconds'] = args.prior_seconds+ledger.workflow_clock_budget.update(clock_sample())['budget_seconds']
        _atomic_json(args.directory/'physical_intermediate_summary.json',summary)
        from benchmarks.physical_intermediate_checker import check
        checker = check(args.directory)
        _atomic_json(args.directory/'checker.json',checker)
        summary.update(checker=checker,status=checker['classification'])
        if checker['classification'] != 'BALANCED_OUTPUT_PASS':
            raise ValueError('recovery output checker failed: '+str(checker['gate_failures']))
    except BaseException as exc:
        summary.update(status='RECOVERY_FAILED',exception_type=type(exc).__name__,exception_message=str(exc))
        raise
    finally:
        primary_error = sys.exc_info()[1]
        from .physical_pc_profile import cleanup_profile
        callbacks = [(name,vector.destroy) for name,vector in
                     [('action',action),('solution',solution),('rhs',rhs)] if vector is not None]
        if fine is not None:
            callbacks.append(('fine_action',lambda:destroy_same_mesh_physical_action(fine)))
        cleanup_error = cleanup_profile(summary,args.directory,callbacks)
        for sig,handler in handlers.items():
            signal.signal(sig,handler)
        summary['recovery']['elapsed_seconds'] = ledger.workflow_clock_budget.update(clock_sample())['budget_seconds']
        _atomic_json(args.directory/'physical_intermediate_summary.json',summary)
        if cleanup_error is not None and primary_error is None:
            raise cleanup_error



def main():
    from .physical_balanced_budget import SCHEMA
    from .physical_diagnosis import supervise_diagnosis
    from .task038_launcher import _physical_source_gate
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('input','directory','original','audit','budget'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--audit-sha',required=True)
    parser.add_argument('--expected-sha',required=True)
    parser.add_argument('--worker',action='store_true')
    parser.add_argument('--prior-seconds',type=float)
    args = parser.parse_args()
    for name in ('input','directory','original','audit','budget'):
        setattr(args,name,getattr(args,name).resolve())
    _physical_source_gate(Path.cwd(),args.expected_sha)
    if args.worker:
        run_worker(args)
        return 0
    with args.budget.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX | fcntl.LOCK_NB)
        budget = json.loads(args.budget.read_text())
        originals = [a for a in budget['attempts'] if a['kind']=='original']
        if (budget['schema'] != SCHEMA or budget['limit_seconds'] != 43200 or len(originals) != 1 or
                Path(originals[0]['run_directory']).resolve() != args.original or
                any(a['kind'] in ('original_recovery','notch') for a in budget['attempts'])):
            raise ValueError('recovery requires the unique original and no previous recovery/notch')
        prior = originals[0]['elapsed_seconds']
        remaining = min(10800-prior,43200-sum(a['elapsed_seconds'] for a in budget['attempts']))
        if remaining <= 0:
            raise ValueError('no original workflow recovery budget remains')
        fresh_root(args.directory,args.original)
        entry = dict(kind='original_recovery',status='RESERVED',elapsed_seconds=remaining,
                     original_directory=str(args.original),run_directory=str(args.directory),prior_seconds=prior)
        budget['attempts'].append(entry); _atomic_json(args.budget,budget)
        clock = ClockBudget(clock_sample(),policy=CONSERVATIVE_REALTIME)
        try:
            # Standalone ABI subprocess exits before the watchdog parent begins.
            entry['abi'] = json.loads(subprocess.check_output(
                [sys.executable,'-m','src.runners.fine_reference_preflight','--abi'],text=True))
            cache = args.directory/'jit_cache'
            shutil.copytree(args.original/'jit_cache',cache)
            command = ['mpiexec','-n','1',sys.executable,'-m',__spec__.name,'--worker']
            for name in ('input','directory','original','audit','budget','audit_sha','expected_sha'):
                command += ['--'+name.replace('_','-'),str(getattr(args,name))]
            command += ['--prior-seconds',str(prior)]
            entry['command'] = command
            _atomic_json(args.budget,budget)
            result = supervise_diagnosis(command,args.directory/'watchdog',phase_path=args.directory/'phase.json',
                expected_sha=args.expected_sha,kind='balanced_v5',
                remaining_seconds=remaining-clock.update(clock_sample())['budget_seconds'],cache_path=cache)
            entry.update(status=result['classification'],supervision=result)
            worker_path = args.directory/'physical_intermediate_summary.json'
            worker = json.loads(worker_path.read_text()) if worker_path.exists() else {}
            entry['qualified'] = (result['classification']=='COMPLETED' and
                worker.get('status')=='BALANCED_OUTPUT_PASS' and
                worker.get('checker',{}).get('independent_output_gates_passed',False))
        except BaseException as exc:
            entry.update(status='RECOVERY_FAILED',exception_type=type(exc).__name__,exception_message=str(exc))
            raise
        finally:
            entry['clock_interval'] = clock.update(clock_sample())
            entry['elapsed_seconds'] = entry['clock_interval']['budget_seconds']
            entry['original_plus_recovery_seconds'] = prior+entry['elapsed_seconds']
            if entry['original_plus_recovery_seconds'] > 10800:
                entry.update(status='PERFORMANCE_CONTROLLED_STOP',qualified=False)
            _atomic_json(args.directory/'launch.json',entry)
            _atomic_json(args.budget,budget)
        if entry.get('qualified'):
            from .physical_balanced_budget import launch_notch_after_recovery
            entry['conditional_notch'] = launch_notch_after_recovery(budget,args.budget,entry)
            _atomic_json(args.directory/'launch.json',entry)
            _atomic_json(args.budget,budget)
        return 0 if entry.get('qualified') else 2


if __name__ == '__main__':
    raise SystemExit(main())
