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

RECOVERY_SOURCE = '3ce11b9ae7e1aa590f3084c49f7b3e412650f5a2'
RECOVERY_HASHES = {
    'run_manifest.json': '76c1cf5c62bea1bd1acb30ea421933ce031acb9ddf406cb086bf28d9a8282508',
    'physical_intermediate_summary.json': '50b071602abf07af9a73d4b7694574f26344de2fde9754e35f6072a5f7122260',
    'watchdog/summary.json': '3aba08f7b04925324f9c4b446bd276585741fcb9810741c44f2f3a4ff1e5ff64',
}


def verify_cache_recovery(directory, attempts):
    """One specifically reviewed pre-measurement failure, never a retry policy."""
    directory = Path(directory).resolve()
    old = [a for a in attempts if a.get('kind') == 'R0_profile']
    if (len(old) != 1 or old[0]['status'] != 'WORKER_FAILED' or
            Path(old[0].get('run_directory', '')).resolve() != directory):
        raise InputError('cache recovery does not match the preserved R0 budget entry')
    if any(a.get('kind') == 'R0_profile_cache_recovery_once' for a in attempts):
        raise InputError('one cache recovery already reserved; no further recovery')
    try:
        records = {}
        for name, expected in RECOVERY_HASHES.items():
            content = (directory/name).read_bytes()
            if hashlib.sha256(content).hexdigest() != expected:
                raise ValueError('reviewed failure hash mismatch: '+name)
            records[name] = json.loads(content)
        worker = records['physical_intermediate_summary.json']
        watchdog = records['watchdog/summary.json']
        if (worker['source_sha'] != RECOVERY_SOURCE or worker['status'] != 'FAILED' or
                worker['exception_type'] != 'TimeoutError' or worker['failed_phase'] != 'setup' or
                worker['failed_stage'] != 'fine_physical_started' or
                watchdog['classification'] != 'WORKER_FAILED' or not watchdog['descendants_cleared']):
            raise ValueError('reviewed failure is not the authorized cache failure')
        if (directory/'pc_profile').exists() or any(
                p.exists() and p.stat().st_size for p in
                (directory/'pc_applies.jsonl', directory/'profile_applies.jsonl')):
            raise ValueError('cache recovery requires zero measured PC applications')
    except (OSError, ValueError, KeyError) as exc:
        raise InputError(str(exc)) from exc
    return dict(run_directory=str(directory), source_sha=RECOVERY_SOURCE,
                raw_hashes=dict(RECOVERY_HASHES), completed_pc=0)


def launch_profile(specification, checkpoint, budget_path, *, cache_recovery_from=None):
    from .task038_launcher import launch_specification

    if (specification.solver.get('preconditioner') != REFERENCE_PROFILE or
            specification.input_sha256 != INPUT_SHA):
        raise InputError('PC profile requires the unchanged A2R reference profile')
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
        recovery = (verify_cache_recovery(cache_recovery_from, budget['attempts'])
                    if cache_recovery_from is not None else None)
        if recovery is None and any(a.get('kind') == 'R0_profile' for a in budget['attempts']):
            raise InputError('R0 profile attempt already reserved; no automatic rebuild/retry')
        if sum(a['elapsed_seconds'] for a in budget['attempts'])+1830 > 36000:
            raise InputError('insufficient batch budget for setup-inclusive profile and cleanup')
        started = time.monotonic()
        attempt = dict(kind='R0_profile_cache_recovery_once' if recovery else 'R0_profile',
                       status='RESERVED', elapsed_seconds=1830,
                       reserved_seconds=1830, full_pc_limit=7, started_timestamp_ns=time.time_ns())
        if recovery is not None:
            attempt['cache_recovery_from'] = recovery
        budget['attempts'].append(attempt)
        _atomic_json(budget_path, budget)
        try:
            config = dict(checkpoint=str(Path(checkpoint).resolve()), budget_ledger=str(budget_path),
                          variant='R0', complete_pc_limit=7, batch_limit_seconds=1800,
                          deadline_monotonic=started+1800)
            if recovery is not None:
                config['cache_recovery_from'] = recovery
            result = launch_specification(specification, pc_profile=config)
            attempt.update(status=result['result_classification'], run_directory=result['run_directory'])
            return result
        except BaseException as exc:
            attempt.update(status='FAILED', exception_type=type(exc).__name__, exception_message=str(exc))
            raise
        finally:
            attempt['elapsed_seconds'] = time.monotonic()-started
            _atomic_json(budget_path, budget)
