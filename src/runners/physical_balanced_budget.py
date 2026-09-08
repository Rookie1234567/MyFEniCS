"""V5 single-attempt ordering and conservative whole-workflow accounting."""
import fcntl
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

from src.io.input_loader import InputError
from src.io.physical_balanced_profile import BALANCED_PROFILES
from .physical_intermediate import _atomic_json
from .workflow_timebase import ClockBudget, clock_sample, CONSERVATIVE_REALTIME

SCHEMA = 'task39extra.review-v5-compute-budget.v1'


def launch_balanced_workflow(specification, budget_path):
    from src.io import load_and_resolve
    from .task038_launcher import launch_specification
    if budget_path is None:
        raise InputError('balanced workflow requires its V5 batch ledger')
    path = Path(budget_path).resolve()
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        budget = json.loads(path.read_text())
        if budget.get('schema') != SCHEMA or budget.get('limit_seconds') != 43200:
            raise InputError('balanced profiles require the separate 43200s V5 ledger')
        if specification.geometry.get('cell_notch'):
            raise InputError('notch runs only immediately after the first qualified original')
        if specification.physical_model_sha256 != '9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f':
            raise InputError('original balanced physical identity differs')
        previous = [a for a in budget['attempts'] if a['kind'] == 'original']
        for prior in [a for a in budget['attempts'] if a['kind'] in ('original','notch')]:
            if prior.get('parent_classification') not in ('COMPLETED','PERFORMANCE_CONTROLLED_STOP','WORKER_FAILED'):
                raise InputError('parent resource/correctness blocker requires review')
        if previous and previous[-1].get('worker_status') not in (
                'SCREEN_BUDGET_NO_QUALIFIED_PROGRESS','PERFORMANCE_CONTROLLED_STOP',
                'ITERATION_BUDGET_EXHAUSTED','BALANCED_OUTPUT_PASS','BALANCED_NUMERICAL_REJECTED'):
            raise InputError('previous correctness/resource/engineering blocker requires review')
        notches=[a for a in budget['attempts'] if a['kind']=='notch']
        if notches and notches[-1].get('worker_status') not in (
                'BALANCED_OUTPUT_PASS','BALANCED_OUTPUT_AUTHORITY_LIMITED','ITERATION_BUDGET_EXHAUSTED',
                'PERFORMANCE_CONTROLLED_STOP','BALANCED_NUMERICAL_REJECTED'):
            raise InputError('notch correctness/resource/engineering blocker requires review')
        if len(previous) >= 3 or specification.solver['preconditioner'] != BALANCED_PROFILES[len(previous)]:
            raise InputError('original order is BAL_H, BAL_S, PROJ_K6, once each')
        if any(a['kind'] == 'notch' and a.get('qualified') for a in budget['attempts']):
            raise InputError('original and notch already qualified; campaign complete')

        def once(spec, kind):
            if any(a.get('input_sha256') == spec.input_sha256 for a in budget['attempts']):
                raise InputError('this balanced input already reserved')
            used = sum(a['elapsed_seconds'] for a in budget['attempts'])
            if used + 10800 > 43200:
                raise InputError('insufficient batch budget for one complete workflow')
            entry = dict(kind=kind, profile=spec.solver['preconditioner'],
                input_sha256=spec.input_sha256, status='RESERVED', elapsed_seconds=10800,
                reserved_seconds=10800, qualified=False)
            budget['attempts'].append(entry)
            _atomic_json(path, budget)
            clock = ClockBudget(clock_sample(), policy=CONSERVATIVE_REALTIME)
            try:
                result = launch_specification(spec)
                entry.update(status=result['result_classification'], run_directory=result['run_directory'])
                worker_path = Path(result['run_directory'])/'physical_intermediate_summary.json'
                if worker_path.exists():
                    worker = json.loads(worker_path.read_text())
                    entry['worker_status'] = worker['status']
                    entry['parent_classification'] = result.get('resource_authority',{}).get('classification')
                    entry['independent_output_gates_passed'] = worker.get('checker', {}).get('independent_output_gates_passed',False)
                    classification=worker.get('checker',{}).get('classification')
                    entry['qualified'] = bool(result['result_classification']=='worker_exit0' and
                        entry['parent_classification']=='COMPLETED' and entry['independent_output_gates_passed'] and
                        classification in ('BALANCED_OUTPUT_PASS','BALANCED_OUTPUT_AUTHORITY_LIMITED'))
                    entry['reference_qualified'] = entry['qualified'] and classification=='BALANCED_OUTPUT_PASS'
                    entry['reference_authority'] = 'MATCHED' if entry['reference_qualified'] else 'LIMITED'
                return result, entry
            except BaseException as exc:
                entry.update(status='FAILED', exception_type=type(exc).__name__, reason=str(exc))
                raise
            finally:
                entry['clock_interval'] = clock.update(clock_sample())
                entry['elapsed_seconds'] = entry['clock_interval']['budget_seconds']
                _atomic_json(path, budget)

        result, original = once(specification, 'original')
        if original['qualified'] and not any(a['kind'] == 'notch' for a in budget['attempts']):
            identity = specification.solver['preconditioner']
            notch = load_and_resolve(Path('input/task39extra')/f'nonseparable_13p5nm_p6h10_{identity}.dat')
            notch_result, notch_entry = once(notch, 'notch')
            result['conditional_notch'] = notch_result
            if notch_result['result_classification']=='worker_exit0' and notch_entry['independent_output_gates_passed']:
                result['conditional_reference'] = conditional_reference(budget, path, notch_entry)
        return result


def conditional_reference(budget, path, notch):
    """One existing symbolic/capacity-gated reference, after the worker exits."""
    if any(a['kind']=='notch_reference' for a in budget['attempts']):
        raise InputError('notch reference already reserved')
    if sum(a['elapsed_seconds'] for a in budget['attempts'])+3600 > 43200:
        return dict(status='REFERENCE_AUTHORITY_LIMITED',reason='insufficient remaining batch budget')
    directory = Path(notch['run_directory'])
    parent = json.loads((directory/'run_summary.json').read_text())['resource_authority']
    if not parent['descendants_cleared'] or parent['remaining_child_pids']:
        raise InputError('notch worker must be fully cleared before conditional reference')
    source = json.loads((directory/'physical_intermediate_summary.json').read_text())['source_sha']
    entry = dict(kind='notch_reference',status='RESERVED',elapsed_seconds=3600,reserved_seconds=3600)
    budget['attempts'].append(entry); _atomic_json(path,budget)
    clock = ClockBudget(clock_sample(),policy=CONSERVATIVE_REALTIME)
    try:
        packet = directory/'notch_reference_witness.json'
        witness = directory/'conditional_reference_witness.json'
        _atomic_json(witness,dict(schema='balanced-notch-reference-witness.v1',packet=str(packet.resolve()),
            packet_sha256=hashlib.sha256(packet.read_bytes()).hexdigest()))
        root = directory/'conditional_reference'
        cache = directory/'conditional_reference_cache'
        shutil.copytree(directory/'jit_cache',cache)
        command = [sys.executable,'-m','src.runners.fine_reference_preflight',
            '--input','input/task39extra/nonseparable_13p5nm_p6h10_fine_reference.dat',
            '--directory',str(root),'--expected-sha',source,'--cache-path',str(cache),
            '--solve-reference','--witness-audit',str(witness),
            '--witness-audit-sha',hashlib.sha256(witness.read_bytes()).hexdigest(),
            '--workflow-seconds',str(max(1.,3600-clock.update(clock_sample())['budget_seconds']))]
        entry['command']=command; _atomic_json(path,budget)
        completed = subprocess.run(command,check=False)
        entry.update(exit_code=completed.returncode,run_directory=str(root))
        launch = json.loads((root/'launch.json').read_text())
        entry['status'] = launch['classification']
        notch['reference_attempt_status']=launch['classification']
        match = root/'matched_reference.json'
        if completed.returncode == 0 and match.exists():
            facts=json.loads(match.read_text())
            notch['reference_qualified']=facts['status']=='MATCHED_REFERENCE_PASS'
            notch['reference_authority']=facts['status']
            entry['matched_output']=facts
        return dict(entry)
    finally:
        entry['clock_interval']=clock.update(clock_sample())
        entry['elapsed_seconds']=entry['clock_interval']['budget_seconds']
        _atomic_json(path,budget)
