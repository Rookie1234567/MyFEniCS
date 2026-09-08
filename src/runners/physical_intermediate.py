"""Explicit physical-intermediate workflow; numerical work stays in solvers."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import numpy as np

from src.io.physical_intermediate_profile import PROFILE, PROFILES, REFERENCE_PROFILE, profile_facts


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, np.ndarray)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (complex, np.complexfloating)):
        return [float(value.real), float(value.imag)]
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, Path):
        return str(value)
    return value


def _atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(_jsonable(value), allow_nan=False, sort_keys=True) + '\n')
    temporary.replace(path)


class WorkflowLedger:
    """Incremental scalar records, with phase deadlines readable by the parent."""

    def __init__(self, directory: Path, phase_path: Path, *, cooperative_performance_stop: bool = False):
        self.directory, self.phase_path = directory, phase_path
        self.application_worker = None
        if cooperative_performance_stop:
            pid = os.getpid()
            ticks = int(Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[19])
            self.application_worker = dict(pid=pid, start_ticks=ticks)
        self.phase = 'setup'
        self.started = time.monotonic()
        self.phase_started = self.started
        self.pc_counts = Counter()
        self.last_safe = None
        self.stop_signal = None
        self.last_stage = None
        self.defer_performance_stop = False
        self.marker('workflow_started', {})

    def set_phase(self, phase: str) -> None:
        self.phase, self.phase_started = phase, time.monotonic()
        self.marker(phase + '_started', {})

    def marker(self, stage: str, facts: dict, *, allow_stop: bool = False) -> None:
        if (self.stop_signal is not None and not allow_stop
                and not (self.defer_performance_stop and self.phase == 'solve')):
            raise InterruptedError(f'parent stop signal {self.stop_signal}')
        self.last_stage = stage
        record = dict(phase=self.phase,
            phase_started_monotonic=self.phase_started, stage=stage,
            updated_monotonic=time.monotonic(), facts=facts)
        if self.application_worker is not None:
            record['application_worker'] = self.application_worker
        self.append('stages.jsonl', record)
        _atomic_json(self.phase_path, record)

    def append(self, name: str, facts: dict) -> None:
        with (self.directory / name).open('a') as output:
            output.write(json.dumps(_jsonable(facts), allow_nan=False, sort_keys=True) + '\n')
            output.flush()

    def record_pc(self, facts: dict) -> None:
        inner = facts['intermediate']
        self.pc_counts['outer_pc_applies'] += 1
        self.pc_counts['inner_iterations'] += inner.get('iterations', 0)
        self.pc_counts['inner_matvecs'] += inner.get('matvec_count', 0)
        self.pc_counts['inner_explicit_actions'] += inner.get('explicit_action_count', 0)
        if inner.get('diagnostic_only'):
            self.pc_counts['reference_factor_solves'] += inner['factor_solve_calls']
        self.pc_counts['inner_shifted_applies'] += inner.get('pc_apply_count', 0)
        self.pc_counts['outer_pc_wall_seconds'] += facts['wall_seconds']
        self.pc_counts['inner_wall_seconds'] += inner.get('elapsed_seconds', 0)
        for direction in facts['direction_facts']:
            name = direction['stage']
            self.pc_counts[name + '_wall_seconds'] += direction['wall_seconds']
            positive = direction.get('positive_cycle_facts', {})
            if positive and facts.get('positive_identity') == 'H6':
                self.pc_counts['h6_apply_count'] += 1
                self.pc_counts['b6_action_count'] += positive['matrix_mult_count']
                for key in ('s6_apply_count', 's3_apply_count', 'positive_p1_apply_count'):
                    self.pc_counts[key] += 0
                continue
            for prefix, entries in (('s6_', positive), ('s3_', positive.get('lower_cycle_facts', {}))):
                for key, value in entries.items():
                    if key.endswith('_count') and isinstance(value, int):
                        # apply_count is a lifetime ordinal; other counts are per call.
                        self.pc_counts[prefix + key] += 1 if key == 'apply_count' else value
            bottom = positive.get('lower_cycle_facts', {}).get('p1_solver_facts', {})
            self.pc_counts['positive_p1_wall_seconds'] += bottom.get('wall_seconds_exclusive', 0)
        for key, value in inner.get('shifted_cost_totals', {}).items():
            self.pc_counts['shifted_' + key] += value
        # Write scalar inner detail immediately; retain no per-apply history in RAM.
        self.append('pc_applies.jsonl', facts)

    def cycle(self, facts: dict) -> None:
        self.append('cycles.jsonl', {**facts, 'pc_costs': dict(self.pc_counts),
            'global_elapsed_monotonic_seconds': time.monotonic()-self.started,
            'timing_semantics': 'cycle/inner/smoothing walls are nested; never sum as workflow time'})
        self.pc_counts.clear()


def run_physical_intermediate(payload: dict, directory: Path, *, source_sha: str) -> dict:
    """Run only under the dedicated parent; save safe states before recovery."""
    from mpi4py import MPI
    from petsc4py import PETSc
    from benchmarks.subreaper_watchdog import memory_envelope
    from benchmarks.task038_full3d_jit_staging import process_tree_snapshot
    from src.io.input_validation import simulation_config_3d_from_normalized
    from src.solvers.fullspace_memory_first_krylov import (
        destroy_krylov_result, run_fixed_restart_cycles, write_solution_checkpoint,
    )
    from src.solvers.fullspace_physical_intermediate import apply_owned
    from src.solvers.fullspace_physical_intermediate_runtime import (
        build_physical_intermediate_solver, destroy_physical_intermediate_solver,
        release_physical_intermediate_solver_stack,
        qualify_physical_intermediate_setup,
    )
    from src.solvers.fullspace_same_mesh_hcurl_pmg_physical import build_physical_rhs, recover_p0_outputs
    from src.solvers.fullspace_same_mesh_hcurl_pmg_setup import audit_p6_same_mesh_setup

    identity = payload['solver']['preconditioner']
    from src.io.physical_intermediate_profile import FAST_PROFILE, LIGHT_PROFILE
    light = identity == LIGHT_PROFILE
    reference = identity in (REFERENCE_PROFILE, FAST_PROFILE, LIGHT_PROFILE)
    pc_profile = json.loads(os.environ['PHYSICAL_PC_PROFILE']) if 'PHYSICAL_PC_PROFILE' in os.environ else None
    if identity == FAST_PROFILE and (pc_profile is None or pc_profile['variant'] != FAST_PROFILE):
        raise ValueError('fast profile currently requires the explicit seven-PC diagnostic mode')
    if pc_profile is not None and pc_profile['variant'] == FAST_PROFILE and identity != FAST_PROFILE:
        raise ValueError('fast diagnostic requires its own dat/resolved identity')
    if pc_profile is not None and not reference:
        raise ValueError('PC timing mode requires the unchanged reference profile')
    if pc_profile is not None and (pc_profile['variant'] not in ('R0', 'a2r_equivalent_fast_v1') or
            pc_profile['complete_pc_limit'] != 7 or pc_profile['batch_limit_seconds'] != 1800):
        raise ValueError('PC timing mode differs from the frozen R0 contract')
    if identity not in PROFILES or payload['derived'].get('physical_intermediate_profile') != profile_facts(identity):
        raise ValueError('resolved physical-intermediate profile differs from the frozen contract')
    parent = int(os.environ['PHYSICAL_WATCHDOG_PARENT_PID'])
    cap = int(os.environ['PHYSICAL_WATCHDOG_LAUNCH_CAP_BYTES'])
    phase_path = Path(os.environ['PHYSICAL_WATCHDOG_PHASE_PATH'])
    if parent == os.getpid() or not Path(f'/proc/{parent}').is_dir():
        raise RuntimeError('dedicated parent watchdog is required')
    if MPI.COMM_WORLD.size != 1 or PETSc.ScalarType is not np.complex128:
        raise RuntimeError('physical intermediate requires complex128 MPI1')
    if os.environ.get('_MYFENICS_WSL_QUALIFIED_ACTIVATION') != '1':
        raise RuntimeError('qualified activation is required')
    directory = Path(directory)
    ledger = WorkflowLedger(directory, phase_path, cooperative_performance_stop=light)
    ledger.defer_performance_stop = light
    cfg = simulation_config_3d_from_normalized(payload)
    bundle, result, rhs, outcome = {}, None, None, None
    monitor = None
    contract = profile_facts(identity)
    workflow_limit, solve_limit = contract['resources']['workflow_seconds'], contract['resources']['solve_seconds']
    summary = {'profile': profile_facts(identity), 'source_sha': source_sha,
               'official_result': None, 'status': 'STARTED'}
    import petsc4py
    import slepc4py
    import dolfinx
    import mpi4py

    summary['abi'] = dict(python=sys.executable, scalar=str(np.dtype(PETSc.ScalarType)),
        integer=str(np.dtype(PETSc.IntType)), petsc_version=list(PETSc.Sys.getVersion()),
        mpi_version=MPI.Get_library_version(),
        module_paths={m.__name__: m.__file__ for m in (petsc4py, slepc4py, dolfinx, mpi4py)},
        threads={key: os.environ.get(key) for key in
                 ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS')})
    previous_handlers = {}

    def interrupted(signum, _frame):
        ledger.stop_signal = signum

    def sample():
        if ledger.stop_signal is not None and not (light and ledger.phase == 'solve'):
            raise InterruptedError(f'parent stop signal {ledger.stop_signal}')
        facts = process_tree_snapshot(parent, ledger.phase, None)
        facts['launch_cap_bytes'] = cap
        envelope = memory_envelope()
        facts['launch_cap_bytes'] = min(cap, facts['rss_bytes'] +
            envelope['effective_available_bytes']-envelope['reserve_bytes'])
        if (not facts['all_status_readable'] or facts['rss_bytes'] >= cap
                or facts['swap_bytes'] != 0 or envelope['effective_available_bytes'] < envelope['reserve_bytes']):
            raise RuntimeError('whole-workflow resource gate failed')
        return facts

    try:
        for signum in (signal.SIGTERM, signal.SIGINT):
            previous_handlers[signum] = signal.signal(signum, interrupted)
        bundle = build_physical_intermediate_solver(cfg, MPI.COMM_WORLD,
            resource_sample=sample, marker=ledger.marker, **({'reference': True} if reference else {}),
            **({'light': True} if light else {}))
        fine = bundle['fine']
        summary['positive_setup'] = bundle['positive']['light_facts'] if light else audit_p6_same_mesh_setup(bundle['positive'])
        if reference:
            summary['reference_p4'] = dict(bundle['reference_factor'].audit)
            summary['reference_matrix'] = bundle['reference_matrix_facts']
            summary['shifted_inverse'] = {'constructed': False}
        else:
            summary['shifted_p1'] = dict(bundle['shifted_p1_factor'].audit)
            summary['shifted_p1_matrix'] = bundle['shifted_p1_matrix_facts']
        summary['positive_diagonals'] = bundle['jacobi_facts']
        summary['mode_sha256'] = fine['mode_sha256']
        summary['setup_qualification'] = qualify_physical_intermediate_setup(
            bundle, marker=ledger.marker, resource_sample=sample)
        rhs, summary['rhs'] = build_physical_rhs(fine)
        if pc_profile is not None:
            from .physical_pc_profile import run_pc_profile
            if pc_profile['variant'] == 'a2r_equivalent_fast_v1':
                from src.solvers.physical_equivalent_fast import install_equivalent_fast
                ledger.marker('equivalent_fast_install_started', {})
                summary['equivalent_fast'] = install_equivalent_fast(bundle, cfg)
                ledger.marker('equivalent_fast_install_complete', summary['equivalent_fast'])

            _atomic_json(directory / 'setup.json', summary)
            ledger.set_phase('profile')
            outcome = run_pc_profile(bundle, rhs, payload, directory, ledger, source_sha, pc_profile)
            summary.update(status='PROFILE_COMPLETED', diagnostic_only=True,
                           profile_evidence=outcome['summary'])
            return outcome
        provenance = payload['provenance']
        operator_identity = hashlib.sha256(json.dumps(dict(source_sha=source_sha,
            physical=provenance['physical_model_sha256'], modes=fine['mode_sha256'],
            quadrature=bundle['actions']['volume_quadrature_metadata']), sort_keys=True).encode()).hexdigest()
        checkpoints = directory / 'checkpoints'
        checkpoints.mkdir()

        def checkpoint(iteration, solution, residual):
            if light and ledger.last_safe is not None and ledger.last_safe['iteration'] == iteration:
                return
            # Completed-cycle snapshots also cover interruption before the next
            # 128 boundary; no live Arnoldi basis or residual is saved.
            facts = write_solution_checkpoint(checkpoints / f'iteration_{iteration:06d}', solution,
                iteration=iteration, explicit_true_residual=residual,
                input_identity_sha256=provenance['input_sha256'], operator_identity_sha256=operator_identity,
                physical_model_sha256=provenance['physical_model_sha256'], source_sha=source_sha,
                ownership=dict(rank=0, ownership_range=list(solution.getOwnershipRange()),
                    local_size=solution.getLocalSize(), global_size=solution.getSize()), comm=MPI.COMM_WORLD)
            ledger.last_safe = {'iteration': iteration, 'explicit_true_residual': residual,
                                'checkpoint': facts, 'regular_128_boundary': iteration > 0 and iteration % 128 == 0}
            _atomic_json(directory / 'last_safe_checkpoint.json', ledger.last_safe)

        initial = rhs.duplicate()
        try:
            initial.set(0)
            checkpoint(0, initial, 0.0 if rhs.norm() == 0 else 1.0)
        finally:
            initial.destroy()
        _atomic_json(directory / 'setup.json', summary)
        ledger.set_phase('solve')
        if light:
            from src.solvers.physical_safe_monitor import PhysicalSafeMonitor, conservative_stagnation as _light_stagnation
            def append_monitor(name, row):
                ledger.append(name, dict(row, completed_pc_count=bundle['pc'].apply_count,
                                         h6_apply_count=bundle['positive']['h6'].apply_count))
            monitor = PhysicalSafeMonitor(rhs, lambda source: apply_owned(fine['physical_action'], source),
                checkpoint, append_monitor, lambda: ledger.stop_signal is not None)

        def apply_pc(source):
            solution = bundle['pc'].apply(source)
            try:
                ledger.record_pc(bundle['pc'].last_apply_facts)
                return solution
            except BaseException:
                solution.destroy()
                raise

        def observe(iteration, solution, cycle):
            normalized_reported = cycle['reported_final_residual']/max(rhs.norm(), np.finfo(float).tiny)
            difference = abs(normalized_reported-cycle['explicit_true_residual'])
            limit = max(1e-10, .01*cycle['explicit_true_residual'])
            cycle.update(reported_relative_residual=normalized_reported,
                         reported_true_difference=difference, reported_true_difference_limit=limit)
            checkpoint(iteration, solution, cycle['explicit_true_residual'])
            ledger.cycle(cycle)
            if not np.isfinite(difference) or difference > limit:
                raise RuntimeError('KSP reported/explicit residual mismatch at equal normalization')

        result = run_fixed_restart_cycles(rhs, lambda source: apply_owned(fine['physical_action'], source),
            apply_pc, max_it=contract['outer']['max_iterations'], residual_limit=1e-6, resource_sample=sample, start_iteration=0,
            first_checkpoint_iteration=None, checkpoint_interval=128, cycle_observer=observe,
            ksp_type='fgmres', restart=32, **(dict(iteration_observer=monitor,
                stop_after_cycle=lambda cycle, cycles: _light_stagnation(cycles)) if light else {}))
        action = apply_owned(fine['physical_action'], result['final_solution'])
        try:
            raw_path = directory / 'final_residual_arrays.npz'
            np.savez(raw_path, rhs=rhs.array, action=action.array,
                     solution=result['final_solution'].array)
            summary['residual_arrays'] = {'filename': raw_path.name,
                'sha256': hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                'operator_identity_sha256': operator_identity, **provenance}
        finally:
            action.destroy()
        summary['solve'] = {k: v for k, v in result.items() if k != 'final_solution'}
        summary['final_solution_sha256'] = hashlib.sha256(result['final_solution'].array.tobytes()).hexdigest()
        if monitor is not None:
            summary['monitor_original_A6_action_count'] = monitor.action_count
            monitor.destroy()
        summary['solve_monotonic_seconds'] = time.monotonic()-ledger.phase_started
        summary['rss_before_release'] = sample()['rss_bytes']
        if reference:
            summary['reference_p4'] = dict(bundle['reference_factor'].audit)
            pc_path = directory / 'pc_applies.jsonl'
            summary['reference_pc_ledger'] = dict(filename=pc_path.name,
                sha256=hashlib.sha256(pc_path.read_bytes()).hexdigest())
        ledger.set_phase('release')
        release_physical_intermediate_solver_stack(bundle)
        summary['rss_after_release'] = sample()['rss_bytes']
        summary['auxiliary_stack_released_before_recovery'] = bundle['auxiliary_stack_released']
        passed = (np.isfinite(result['final_true_residual']) and result['final_true_residual'] <= 1e-6
                  and (result['reason'] >= 0 or result['reason'] == -3)
                  and summary['solve_monotonic_seconds'] <= solve_limit and ledger.stop_signal is None)
        if passed:
            ledger.set_phase('recovery')
            def canonical_export(field, out_dir):
                from benchmarks.canonical_vector_artifacts import write_canonical_packet_shard
                from src.solvers.hcurl_canonical_vector_dolfinx import iter_canonical_full_fe_packets

                return write_canonical_packet_shard(out_dir / 'canonical_solution.rank0000.jsonl',
                    iter_canonical_full_fe_packets(field.function_space, field, fine['setup']['floquets'][6]),
                    audit_packets=True)

            outputs = recover_p0_outputs(fine, result['final_solution'], directory / 'numerical_output',
                canonical_export=canonical_export, export_all_port_modes=True)
            summary['official_result'] = outputs
            summary['status'] = 'RESIDUAL_PASS'
        else:
            summary['status'] = ('STAGNATION_CONTROLLED_STOP' if light and _light_stagnation(result['cycles'])
                                 else 'ITERATION_BUDGET_EXHAUSTED' if light and result['iterations'] >= contract['outer']['max_iterations']
                                 else 'RESIDUAL_FAILED')
        ledger.set_phase('checker')
        summary['elapsed_monotonic_seconds'] = time.monotonic()-ledger.started
        _atomic_json(directory / 'physical_intermediate_summary.json', summary)
        check = subprocess.run([sys.executable, '-m', 'benchmarks.physical_intermediate_checker',
                                str(directory)], check=False)
        checker = json.loads((directory / 'checker.json').read_text())
        summary['checker'] = checker
        summary['status'] = checker['classification']
        summary['reference_authority'] = checker['reference_authority']
        passed = (check.returncode == 0 and checker['classification'] in ('DISCRETE_SOLVER_OUTPUT_PASS', 'REFERENCE_ONLY_PASS')
                  and time.monotonic()-ledger.started <= workflow_limit and ledger.stop_signal is None)
        outcome = {'passed': bool(passed), 'errors': [] if passed else checker['gate_failures'] or [summary['status']],
                'summary': str(directory / 'physical_intermediate_summary.json'),
                'numerical_output_directory': str(directory / 'numerical_output')}
        return outcome
    except BaseException as exc:
        from src.solvers.fullspace_p4_reference import ReferenceResourceBlocked
        summary.update(status='CONTROLLED_STOP' if isinstance(exc, InterruptedError) else 'FAILED',
                       exception_type=type(exc).__name__, exception_message=str(exc),
                       failed_stage=ledger.last_stage, failed_phase=ledger.phase)
        if isinstance(exc, ReferenceResourceBlocked):
            summary['status'] = 'REFERENCE_RESOURCE_BLOCKED'
        raise
    finally:
        primary_error = sys.exc_info()[1]
        cleanup_error = None
        summary['last_safe_checkpoint'] = ledger.last_safe
        if pc_profile is not None or light:
            from .physical_pc_profile import cleanup_profile

            callbacks = []
            if monitor is not None:
                summary['monitor_original_A6_action_count'] = monitor.action_count
                callbacks.append(('monitor', monitor.destroy))
            if result is not None:
                callbacks.append(('krylov_result', lambda: destroy_krylov_result(result)))
            if rhs is not None:
                callbacks.append(('rhs', rhs.destroy))
            callbacks.append(('solver_stack', lambda: destroy_physical_intermediate_solver(bundle)))
            cleanup_error = cleanup_profile(summary, directory, callbacks)
        else:
            if result is not None:
                destroy_krylov_result(result)
            if rhs is not None:
                rhs.destroy()
            destroy_physical_intermediate_solver(bundle)
        summary['elapsed_monotonic_seconds'] = time.monotonic()-ledger.started
        if summary['elapsed_monotonic_seconds'] > workflow_limit or ledger.stop_signal is not None:
            summary['status'] = 'PERFORMANCE_CONTROLLED_STOP' if ledger.stop_signal is None else 'CONTROLLED_STOP'
            summary.setdefault('failed_stage', ledger.last_stage)
            if outcome is not None:
                outcome.update(passed=False, errors=[summary['status']])
        _atomic_json(directory / 'physical_intermediate_summary.json', summary)
        if summary['status'] not in ('FAILED', 'CONTROLLED_STOP', 'PERFORMANCE_CONTROLLED_STOP', 'REFERENCE_RESOURCE_BLOCKED'):
            ledger.set_phase('complete')
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
        if cleanup_error is not None and primary_error is None:
            raise cleanup_error
