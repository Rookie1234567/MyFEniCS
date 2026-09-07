"""Single-run R0 profile reservation and cumulative task computation ledger."""

import fcntl
import hashlib
import json
from pathlib import Path
import time

from src.io.input_loader import InputError
from src.io.physical_intermediate_profile import REFERENCE_PROFILE
from .physical_intermediate import _atomic_json
from .physical_pc_profile import INPUT_SHA, verified_checkpoint

FAST_INPUT_SHA = '52004b3d9fa3de5d39297074efd0ba6bb3312037209162599317f8dfb3c42593'


def launch_light_workflow(specification, budget_path):
    """Reserve one explicit R3 input in the existing cumulative task ledger."""
    from src.io.physical_intermediate_profile import LIGHT_PROFILE, profile_facts
    from .task038_launcher import launch_specification
    if specification.solver.get('preconditioner') != LIGHT_PROFILE or budget_path is None:
        raise InputError('light workflow requires its explicit profile and batch budget ledger')
    path = Path(budget_path).resolve()
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        budget = json.loads(path.read_text())
        if budget['limit_seconds'] != 36000:
            raise InputError('batch limit must remain 36000 seconds')
        if any(a.get('kind') == 'R3_full_workflow' and a.get('input_sha256') == specification.input_sha256
               for a in budget['attempts']):
            raise InputError('this light input already reserved; no repeat formal')
        resource = profile_facts(LIGHT_PROFILE)['resources']
        reservation = resource['workflow_seconds'] + resource['performance_grace_seconds']
        if sum(a['elapsed_seconds'] for a in budget['attempts'])+reservation > budget['limit_seconds']:
            raise InputError('insufficient cumulative budget for complete light workflow')
        attempt = dict(kind='R3_full_workflow', input_sha256=specification.input_sha256,
            status='RESERVED', elapsed_seconds=reservation, reserved_seconds=reservation)
        budget['attempts'].append(attempt)
        _atomic_json(path, budget)
        started = time.monotonic()
        try:
            result = launch_specification(specification)
            attempt.update(status=result['result_classification'], run_directory=result['run_directory'])
            return result
        except BaseException as exc:
            attempt.update(status='FAILED', exception_type=type(exc).__name__, exception_message=str(exc))
            raise
        finally:
            attempt['elapsed_seconds'] = time.monotonic()-started
            _atomic_json(path, budget)

RECOVERY_SOURCE = '3ce11b9ae7e1aa590f3084c49f7b3e412650f5a2'
RECOVERY_HASHES = {
    'run_manifest.json': '76c1cf5c62bea1bd1acb30ea421933ce031acb9ddf406cb086bf28d9a8282508',
    'physical_intermediate_summary.json': '50b071602abf07af9a73d4b7694574f26344de2fde9754e35f6072a5f7122260',
    'watchdog/summary.json': '3aba08f7b04925324f9c4b446bd276585741fcb9810741c44f2f3a4ff1e5ff64',
}
REVIEWED_FAILURES = {
    'R0_profile': dict(source_sha=RECOVERY_SOURCE, hashes=RECOVERY_HASHES,
        exception_type='TimeoutError', phase='setup', stage='fine_physical_started',
        reservation_kind='R0_profile_cache_recovery_once', recovery_field='cache_recovery_from'),
    'R0_profile_cache_recovery_once': dict(
        source_sha='a9dec104b450f7ac4f5adc38ed2b4b05c9592a3e',
        hashes={
            'run_manifest.json': 'edc59580e800ca1a038a7beea26da51428d9a626a566081d4c5e876857fec370',
            'physical_intermediate_summary.json': '7ada061f71357c0e847aff398ca6188014eaa9a08b1bbb2ce4f158d2feaa925e',
            'watchdog/summary.json': '2237c60e86947f495a458d878e25623b41a674e976090fa36b9adad800254eab',
            'pc_profile/state.json': '3a40541a6cb1c1a6f2c2f22c4ff2bf31e8205571cfe12a1a0f9fe05019ea9ef5',
        }, exception_type='TypeError', phase='profile', stage='profile_started',
        reservation_kind='R0_profile_instrumentation_requalification_once', recovery_field='recovery_from'),
}


def verify_profile_recovery(directory, attempts):
    """Resolve only the explicitly reviewed failures; never an automatic retry."""
    directory = Path(directory).resolve()
    old = [a for a in attempts if 'run_directory' in a and Path(a['run_directory']).resolve() == directory]
    if (len(old) != 1 or old[0]['status'] != 'WORKER_FAILED' or
            old[0]['kind'] not in REVIEWED_FAILURES):
        raise InputError('recovery does not match a reviewed failed budget entry')
    permission = REVIEWED_FAILURES[old[0]['kind']]
    if any(a['kind'] == permission['reservation_kind'] for a in attempts):
        raise InputError('this recovery already reserved; no further recovery')
    try:
        records = {}
        for name, expected in permission['hashes'].items():
            content = (directory/name).read_bytes()
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError('reviewed failure hash mismatch: '+name)
            records[name] = json.loads(content)
        worker = records['physical_intermediate_summary.json']
        watchdog = records['watchdog/summary.json']
        if (worker['source_sha'] != permission['source_sha'] or worker['status'] != 'FAILED' or
                worker['exception_type'] != permission['exception_type'] or worker['failed_phase'] != permission['phase'] or
                worker['failed_stage'] != permission['stage'] or
                watchdog['classification'] != 'WORKER_FAILED' or not watchdog['descendants_cleared']):
            raise ValueError('reviewed failure does not match the explicit permission')
        if 'pc_profile/state.json' in records:
            state = records['pc_profile/state.json']
            if state['completed'] != 0 or state['active_apply'] is not None:
                raise ValueError('recovery requires zero started or completed PC applications')
        elif (directory/'pc_profile').exists():
            raise ValueError('unexpected profile state for the reviewed cache failure')
        if any(
                p.exists() and p.stat().st_size for p in
                (directory/'pc_applies.jsonl', directory/'profile_applies.jsonl')):
            raise ValueError('recovery requires zero measured PC applications')
    except (OSError, ValueError, KeyError) as exc:
        raise InputError(str(exc)) from exc
    return dict(run_directory=str(directory), source_sha=permission['source_sha'],
                raw_hashes=dict(permission['hashes']), completed_pc=0,
                failed_attempt_kind=old[0]['kind'])


def launch_profile(specification, checkpoint, budget_path, *, recovery_from=None,
                   variant='R0', r0_reference=None):
    from .task038_launcher import launch_specification
    from .physical_pc_comparison import FAST_VARIANT, verify_r0_profile

    if variant not in ('R0', FAST_VARIANT):
        raise InputError('unknown PC profile variant')
    fast = variant == FAST_VARIANT
    if fast and (recovery_from is not None or r0_reference is None):
        raise InputError('R1 requires the successful R0 reference and no recovery')
    if not fast and r0_reference is not None:
        raise InputError('R0 does not accept an R1 comparison reference')
    try:
        binding = verify_r0_profile(r0_reference) if fast else None
    except (OSError, ValueError) as exc:
        raise InputError(str(exc)) from exc

    if (specification.solver.get('preconditioner') != (FAST_VARIANT if fast else REFERENCE_PROFILE) or
            specification.input_sha256 != (FAST_INPUT_SHA if fast else INPUT_SHA)):
        raise InputError('PC profile dat identity does not match the selected variant')
    try:
        verified_checkpoint(checkpoint, specification.physical_model_sha256)
    except (OSError, ValueError) as exc:
        raise InputError(str(exc)) from exc
    budget_path = Path(budget_path).resolve()
    budget_path.parent.mkdir(parents=True, exist_ok=True)
    with budget_path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        budget = json.loads(budget_path.read_text()) if budget_path.exists() else dict(
            schema='task39extra.review-v1-compute-budget.v1', limit_seconds=36000, attempts=[])
        if budget['limit_seconds'] != 36000:
            raise InputError('batch limit must be 36000 seconds')
        recovery = (verify_profile_recovery(recovery_from, budget['attempts'])
                    if recovery_from is not None else None)
        permission = REVIEWED_FAILURES[recovery['failed_attempt_kind']] if recovery is not None else None
        if fast and any(a.get('kind') == 'R1_profile' for a in budget['attempts']):
            raise InputError('R1 profile already reserved; no rebuild/retry')
        if not fast and recovery is None and any(a.get('kind') == 'R0_profile' for a in budget['attempts']):
            raise InputError('R0 profile attempt already reserved; no automatic rebuild/retry')
        if sum(a['elapsed_seconds'] for a in budget['attempts'])+1830 > 36000:
            raise InputError('insufficient batch budget for setup-inclusive profile and cleanup')
        started = time.monotonic()
        attempt = dict(kind='R1_profile' if fast else (permission['reservation_kind'] if recovery else 'R0_profile'),
                       status='RESERVED', elapsed_seconds=1830,
                       reserved_seconds=1830, full_pc_limit=7, started_timestamp_ns=time.time_ns())
        if recovery is not None:
            attempt[permission['recovery_field']] = recovery
        budget['attempts'].append(attempt)
        _atomic_json(budget_path, budget)
        try:
            config = dict(checkpoint=str(Path(checkpoint).resolve()), budget_ledger=str(budget_path),
                          variant=variant, complete_pc_limit=7, batch_limit_seconds=1800,
                          deadline_monotonic=started+1800)
            if binding is not None:
                config['r0_reference'] = binding
            if recovery is not None:
                config[permission['recovery_field']] = recovery
            result = launch_specification(specification, pc_profile=config)
            attempt.update(status=result['result_classification'], run_directory=result['run_directory'])
            return result
        except BaseException as exc:
            attempt.update(status='FAILED', exception_type=type(exc).__name__, exception_message=str(exc))
            raise
        finally:
            attempt['elapsed_seconds'] = time.monotonic()-started
            _atomic_json(budget_path, budget)
