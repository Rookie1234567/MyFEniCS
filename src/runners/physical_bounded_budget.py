"""V7 route-A ordering and one conservative whole-workflow budget.

The worker already owns its setup/solve/recovery phase clocks.  This wrapper
charges one outer interval around the launch, so nested worker and watchdog
intervals are evidence but are not added a second time to the batch ledger.
"""

from __future__ import annotations

import fcntl
import json
from pathlib import Path

from src.io.input_loader import InputError
from src.io.physical_balanced_profile import (
    BOUNDED_ENTITY_PROFILE,
    BOUNDED_ENTITY_GCROT8_PROFILE,
    BOUNDED_PROFILES,
    BOUNDED_PROJECTED_PROFILE,
    BOUNDED_ROUTES,
)
from .physical_intermediate import _atomic_json
from .workflow_timebase import ClockBudget, CONSERVATIVE_REALTIME, clock_sample


SCHEMA = 'task39extra.review-v7-bounded-budget.v1'
LIMIT_SECONDS = 43200
ORIGINAL_PHYSICAL_SHA = '9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f'
WORKFLOW_RESERVATION_SECONDS = 14400
V8_SCHEMA = 'task39extra.review-v8-recycled-budget.v1'
V8_LIMIT_SECONDS = 36000
V8_WORKFLOW_RESERVATION_SECONDS = 14400


def _charged_seconds(budget: dict) -> float:
    """Return actual charges, treating an abandoned reservation conservatively."""
    total = 0.0
    for item in budget.get('attempts', []):
        if item.get('status') == 'RESERVED':
            total += float(item.get('reserved_seconds', item.get('elapsed_seconds', 0.0)))
        else:
            total += float(item.get('elapsed_seconds', 0.0))
    return total


def _record_worker_result(entry: dict, result: dict) -> None:
    """Copy scalar result/checker facts without charging nested clocks again."""
    entry.update(
        status=result.get('result_classification', 'not_run'),
        run_directory=result.get('run_directory'),
        parent_classification=result.get('resource_authority', {}).get('classification'),
    )
    run_directory = result.get('run_directory')
    if not run_directory:
        entry['qualified'] = False
        return
    summary_path = Path(run_directory) / 'physical_intermediate_summary.json'
    if not summary_path.exists():
        entry['qualified'] = False
        return
    summary = json.loads(summary_path.read_text())
    checker = summary.get('checker', {})
    entry.update(
        worker_status=summary.get('status'),
        checker_classification=checker.get('classification'),
        independent_output_gates_passed=bool(
            checker.get('independent_output_gates_passed', False)),
    )
    # A route-A original may open the conditional notch only after a complete
    # physical/output pass.  A resource-limited authority is not enough for
    # this ordering gate, even though its result remains preserved in the log.
    entry['qualified'] = bool(
        entry['status'] == 'worker_exit0'
        and entry['parent_classification'] == 'COMPLETED'
        and entry['worker_status'] == 'BALANCED_OUTPUT_PASS'
        and entry['checker_classification'] == 'BALANCED_OUTPUT_PASS'
        and entry['independent_output_gates_passed']
    )


def _validate_route_and_order(specification, budget: dict) -> str:
    identity = specification.solver.get('preconditioner')
    if identity not in BOUNDED_PROFILES:
        raise InputError('bounded V7 ledger received a non-bounded profile')
    route = BOUNDED_ROUTES[identity]
    attempts = budget.get('attempts', [])
    original_attempts = [item for item in attempts if item.get('kind') == 'original']
    notch_attempts = [item for item in attempts if item.get('kind') == 'notch']
    projected_attempts = [item for item in attempts if item.get('kind') == 'projected']

    if route == 'PROJECTED_SEQ2_16':
        if identity != BOUNDED_PROJECTED_PROFILE:
            raise InputError('V7 route-B control order requires bounded_projected_seq2_16_v7')
        if specification.geometry.get('cell_notch'):
            raise InputError('V7 projected route is qualified only for the original physical model')
        if specification.physical_model_sha256 != ORIGINAL_PHYSICAL_SHA:
            raise InputError('route-B original physical identity differs')
        if not original_attempts or original_attempts[-1].get('status') == 'RESERVED':
            raise InputError('route B requires a completed route-A original first')
        if original_attempts[-1].get('qualified'):
            raise InputError('route B is conditional and is not opened after a qualified route-A original')
        if projected_attempts or notch_attempts:
            raise InputError('route-B projected attempt already reserved; no repeat formal')
        return 'projected'

    if route not in ('ENTITY16', 'ENTITY_GCROT8'):
        raise InputError(f'unsupported bounded route: {route}')
    expected_entity = (BOUNDED_ENTITY_GCROT8_PROFILE
                       if route == 'ENTITY_GCROT8' else BOUNDED_ENTITY_PROFILE)
    if identity != expected_entity:
        raise InputError('route-A control order does not match the selected entity profile')
    if specification.geometry.get('cell_notch'):
        if not original_attempts or not original_attempts[-1].get('qualified'):
            raise InputError('V7 notch requires a qualified route-A original first')
        # The actual route-A builder currently rejects notch materials rather
        # than reusing original owner packets.  Keep J1 fail-closed until J4.
        raise InputError('V7 notch route is not implemented; original route-A only')
    if specification.physical_model_sha256 != ORIGINAL_PHYSICAL_SHA:
        raise InputError('route-A original physical identity differs')
    if original_attempts or notch_attempts:
        raise InputError('route-A original already reserved; no repeat formal')
    return 'original'


def launch_bounded_workflow(specification, budget_path):
    """Reserve and launch one bounded V7 route-A or conditional route-B workflow.

    The reservation prevents two workers from consuming the same batch slot;
    the final ``elapsed_seconds`` is replaced by the qualified conservative
    dual-clock measurement.  Setup, controls, failed launches, and any later
    recovery records are ordinary ledger entries and therefore count exactly
    once through the same aggregate.
    """

    if budget_path is None:
        raise InputError('bounded V7 profile requires its batch ledger')
    path = Path(budget_path).resolve()
    with path.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        budget = json.loads(path.read_text())
        v8 = specification.solver.get('preconditioner') == BOUNDED_ENTITY_GCROT8_PROFILE
        schema = V8_SCHEMA if v8 else SCHEMA
        limit_seconds = V8_LIMIT_SECONDS if v8 else LIMIT_SECONDS
        reservation_seconds = (V8_WORKFLOW_RESERVATION_SECONDS if v8
                               else WORKFLOW_RESERVATION_SECONDS)
        if (budget.get('schema') != schema or
                budget.get('limit_seconds') != limit_seconds):
            raise InputError('selected bounded profile requires its exact ledger')
        kind = _validate_route_and_order(specification, budget)
        used = _charged_seconds(budget)
        if used + reservation_seconds > limit_seconds:
            raise InputError('insufficient selected bounded batch budget for one workflow')
        entry = dict(
            kind=kind,
            profile=specification.solver['preconditioner'],
            input_sha256=specification.input_sha256,
            status='RESERVED',
            elapsed_seconds=0.0,
            reserved_seconds=reservation_seconds,
            ledger_schema=schema,
            charge_policy='conservative_realtime_outer_interval',
            nested_intervals_not_added=True,
        )
        budget.setdefault('attempts', []).append(entry)
        budget['charged_seconds'] = _charged_seconds(budget)
        budget['remaining_seconds'] = limit_seconds - budget['charged_seconds']
        _atomic_json(path, budget)
        clock = ClockBudget(clock_sample(), policy=CONSERVATIVE_REALTIME)
        try:
            from .task038_launcher import launch_specification
            result = launch_specification(specification)
            _record_worker_result(entry, result)
            return result
        except BaseException as exc:
            entry.update(
                status='FAILED', exception_type=type(exc).__name__,
                exception_message=str(exc), qualified=False,
            )
            raise
        finally:
            try:
                interval = clock.update(clock_sample())
                entry['clock_interval'] = interval
                entry['elapsed_seconds'] = float(interval['budget_seconds'])
            except BaseException as exc:
                entry.update(
                    status='TIMEBASE_INCONSISTENCY',
                    clock_error=f'{type(exc).__name__}: {exc}',
                    qualified=False,
                )
                if not entry.get('exception_type'):
                    raise
            finally:
                budget['charged_seconds'] = _charged_seconds(budget)
                budget['remaining_seconds'] = limit_seconds - budget['charged_seconds']
                _atomic_json(path, budget)
