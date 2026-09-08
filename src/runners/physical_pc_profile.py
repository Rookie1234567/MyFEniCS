"""Seven bounded diagnostic PC applications using the existing reference setup."""

from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from .physical_intermediate import _atomic_json

CHECKPOINT_MANIFEST_SHA = '2aea396923773a07f6b51e9cd044bbf511eb28627d7c87fb9cb72cc50e9aa6df'
CHECKPOINT_SOLUTION_SHA = '4158d89c90bc949a23b9383f7531dd915fd705d6970367a8371757d66a5caec5'
PHYSICAL_SHA = '9142440056196b0c6d4c579f0a1e17e79c1fad7cf0b626206fbd343837804a0f'
MODE_SHA = 'dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2'
INPUT_SHA = '7b0d90dc18e222d5d01e52deb06c12b41f37862fda5cf8e3a4e1565f3f7af999'
PACKED_CHECKPOINT_MANIFEST_SHA = 'ecd87729bd7126f7fcaa3a7e99cfb336e2178649ccbda759369851f49e1bc2b2'
PACKED_CHECKPOINT_SOLUTION_SHA = '3c6ecb49f2a397ddccd4c75305fe4d1870928de144bca76bd8d53e515e1d4b5b'
SCHEDULE = [('physical_rhs', True)] + [(name, False) for name in
    ('physical_rhs', 'checkpoint160_residual', 'random_complex') for _ in range(2)]


def verified_checkpoint(path, physical_sha, *, packed=False):
    path = Path(path)
    manifest_bytes = (path/'manifest.json').read_bytes()
    solution_path = path/'solution_rank0.npy'
    if (hashlib.sha256(manifest_bytes).hexdigest() != (PACKED_CHECKPOINT_MANIFEST_SHA if packed else CHECKPOINT_MANIFEST_SHA) or
            hashlib.sha256(solution_path.read_bytes()).hexdigest() != (PACKED_CHECKPOINT_SOLUTION_SHA if packed else CHECKPOINT_SOLUTION_SHA)):
        raise ValueError('checkpoint hash mismatch')
    manifest = json.loads(manifest_bytes)
    if physical_sha != PHYSICAL_SHA or manifest['physical_model_sha256'] != physical_sha:
        raise ValueError('profile physical identity mismatch')
    return manifest, solution_path


def paired_schedule(checkpoint_available=True):
    names = ['physical_rhs'] + (['checkpoint576_residual'] if checkpoint_available else []) + ['random_complex']
    calls = [('physical_rhs', True)] + [(name, False) for name in names for _ in range(2)]
    return [(name, warm, backend) for name, warm in calls for backend in ('original', 'packed')]


def run_pc_profile(bundle, rhs, payload, directory, ledger, source_sha, config):
    """No outer KSP or recovery. Every complete/partial call is durable evidence."""
    from src.solvers.fullspace_physical_intermediate import apply_owned
    from src.solvers.physical_pc_timing import PCTiming, instrument_reference_pc
    from src.io.physical_intermediate_profile import PACKED_PROFILE

    directory = Path(directory)/'pc_profile'
    directory.mkdir()
    timing = PCTiming()
    state = dict(schema='physical-pc-profile.v1', status='STARTED', source_sha=source_sha,
                 config=config, completed=0, active_apply=None, last_safe=None,
                 schedule=SCHEDULE, inputs={}, captures=[], timing_scope='post-setup diagnostic calls only')
    current = [None]
    serials = {}
    first_repeat = {}
    packed = config.get('variant', 'R0') == PACKED_PROFILE
    checkpoint_name = 'checkpoint576_residual' if packed else 'checkpoint160_residual'
    schedule = paired_schedule(config.get('checkpoint_available', True)) if packed else [(n, w, None) for n, w in SCHEDULE]
    state['schedule'] = schedule if packed else SCHEDULE

    def save(name, vector):
        with timing.scope('artifact_io'):
            path = (current[0] or directory)/f'{name}.npy'
            temporary = path.with_suffix('.npy.tmp')
            with temporary.open('wb') as output:
                np.save(output, vector.getArray(readonly=True), allow_pickle=False)
                output.flush()
            temporary.replace(path)
            facts = dict(path=str(path.relative_to(directory)), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         shape=[vector.getLocalSize()], dtype='complex128',
                         ownership_range=list(vector.getOwnershipRange()))
            state['captures'].append(facts)
            return facts

    def capture(role, vector):
        with timing.scope('artifact_io'):
            serials[role] = serials.get(role, 0)+1
            facts = save(f'{role}_{serials[role]:02d}', vector)
            facts.update(finite=bool(np.all(np.isfinite(vector.array))),
                         slave_zero=bool(np.all(vector.array[slaves] == 0)))
            if not (facts['finite'] and facts['slave_zero']):
                raise ValueError('captured S6/A6 output is not finite slave-zero')

    def safe():
        if ledger.stop_signal is not None or time.monotonic() >= config['deadline_monotonic']:
            raise InterruptedError('profile performance stop at safe point')

    try:
        manifest, path = (verified_checkpoint(config['checkpoint'], payload['provenance']['physical_model_sha256'], **({'packed': True} if packed else {}))
                          if config.get('checkpoint_available', True) else (None, None))
        if (bundle['fine']['mode_sha256'] != MODE_SHA or rhs.getSize() != 173802 or
                payload['provenance']['physical_model_sha256'] != PHYSICAL_SHA or
                list(rhs.getOwnershipRange()) != (manifest['ranks'][0]['ownership']['ownership_range'] if manifest else [0, 173802])):
            raise ValueError('profile original size/mode/ownership mismatch')
        slaves = np.asarray(bundle['levels']['floquets'][6].mpc.slaves, dtype=np.int64)
        slaves = slaves[(slaves >= 0) & (slaves < rhs.getLocalSize())]
        with ExitStack() as owned:
            def own(vector):
                owned.callback(vector.destroy)
                return vector

            inputs = {'physical_rhs': own(rhs.copy())}
            x = own(rhs.duplicate())
            values = np.load(path, allow_pickle=False) if path else np.zeros(rhs.getLocalSize(), dtype=np.complex128)
            if values.dtype != np.complex128 or values.shape != (rhs.getLocalSize(),):
                raise ValueError('checkpoint vector layout mismatch')
            x.array[:] = values
            del values
            if np.any(x.array[slaves] != 0):
                raise ValueError('checkpoint solution is not algebraic slave-zero')
            safe()
            applied = own(apply_owned(bundle['fine']['physical_action'], x))
            residual = own(rhs.copy())
            residual.axpy(-1, applied)
            relative = float(residual.norm()/rhs.norm())
            if manifest is not None:
                if abs(relative-manifest['explicit_true_residual']) > 1e-10:
                    raise ValueError('checkpoint reconstructed original A6 residual mismatch')
                state[checkpoint_name+'_recomputed'] = relative
                if not packed:
                    state['checkpoint160_recomputed_residual'] = relative
                inputs[checkpoint_name] = residual
            else:
                state['checkpoint576'] = 'not_available; two other inputs only'
            random = own(rhs.duplicate())
            rng = np.random.default_rng(3902 if packed else 20260907)
            random.array[:] = rng.standard_normal(rhs.getLocalSize())+1j*rng.standard_normal(rhs.getLocalSize())
            random.array[slaves] = 0
            inputs['random_complex'] = random
            for name, vector in inputs.items():
                norm = float(vector.norm())
                if not np.isfinite(norm) or norm == 0 or np.any(vector.array[slaves] != 0):
                    raise ValueError('profile input must be finite nonzero slave-zero')
                vector.scale(1/norm)
                state['inputs'][name] = dict(save(name, vector), original_norm=norm)
            if 'equivalent_fast' in bundle:
                from .physical_pc_comparison import verify_r0_profile
                fast = bundle['equivalent_fast']
                binding = None if packed else verify_r0_profile(config['r0_reference']['root'])
                state['equivalent_fast'] = fast['facts']
                state['same_input_checks'] = []
                old_components = bundle['fine']['volume_action'].component_actions
                new_components = fast['volume_action'].component_actions
                pairs = [('B6', fast['original_b6'], fast['b6'])] + [
                    (name, old_components[name], new_components[name]) for name in ('curl', 'material_mass')]
                pairs.append(('A6', bundle['fine']['physical_action'], fast['physical_action']))
                for input_name, vector in inputs.items():
                    old_input = (vector.array.copy() if packed else
                        np.load(Path(binding['root'])/'pc_profile'/f'{input_name}.npy', allow_pickle=False))
                    if not np.array_equal(old_input, vector.array):
                        raise ValueError('R1 normalized input differs from saved R0 input')
                    for role, old_action, new_action in pairs:
                        safe()
                        row = dict(name=input_name+'_'+role)
                        for label, action in (('original', old_action), ('fast', new_action)):
                            value = apply_owned(action, vector) if role == 'A6' else action.apply(vector)
                            try:
                                row[label] = save('same_input_'+row['name']+'_'+label, value)
                            finally:
                                if role == 'A6':
                                    value.destroy()
                        state['same_input_checks'].append(row)
                        _atomic_json(directory/'state.json', state)
                        from .physical_pc_comparison import array_difference
                        old_value, new_value = (np.load(directory/row[label]['path'], allow_pickle=False)
                                                for label in ('original', 'fast'))
                        if (not array_difference(old_value, new_value, 1e-11)['passed']
                                or np.any(old_value[slaves] != 0) or np.any(new_value[slaves] != 0)
                                or not np.array_equal(vector.array, old_input)):
                            raise ValueError('same-input component equivalence or input/slave gate failed')
            if not packed:
                instrument_reference_pc(bundle, timing, capture)
                timing.wrap(ledger, 'marker', 'log_marker')
                timing.wrap(ledger, 'append', 'log_append')
            for index, (name, warmup, backend) in enumerate(schedule, 1):
                safe()
                if packed:
                    from src.solvers.physical_equivalent_fast import select_equivalent_backend
                    timing.close()
                    select_equivalent_backend(bundle, packed=backend == 'packed')
                    instrument_reference_pc(bundle, timing, capture)
                    timing.wrap(ledger, 'marker', 'log_marker')
                    timing.wrap(ledger, 'append', 'log_append')
                current[0] = directory/f'apply_{index:02d}'
                current[0].mkdir()
                serials.clear()
                state['active_apply'] = dict(index=index, input=name, warmup=warmup)
                if packed:
                    state['active_apply'].update(backend=backend, resource_before=ledger.resource_sample())
                _atomic_json(directory/'state.json', state)
                ledger.marker('profile_pc_started', state['active_apply'])
                before = timing.snapshot()
                solution = None
                try:
                    with timing.scope('PC'):
                        solution = bundle['pc'].apply(inputs[name])
                    original = np.load(directory/state['inputs'][name]['path'], mmap_mode='r', allow_pickle=False)
                    input_unchanged = bool(np.array_equal(inputs[name].array, original))
                    output_finite = bool(np.all(np.isfinite(solution.array)))
                    output_slave_zero = bool(np.all(solution.array[slaves] == 0))
                    del original
                    if not (input_unchanged and output_finite and output_slave_zero):
                        raise ValueError('profile input mutation or invalid PC output')
                    pc_output = save('PC_output', solution)
                    with timing.scope('PC_output_check'):
                        checked = apply_owned(bundle['fine']['physical_action'], solution)
                    try:
                        action_output = save('PC_A6_output', checked)
                    finally:
                        checked.destroy()
                    ledger.record_pc(bundle['pc'].last_apply_facts)
                    state['completed'] = index
                    state['last_safe'] = dict(state['active_apply'], output=pc_output, action=action_output)
                    state['last_safe'].update(input_unchanged=input_unchanged,
                        output_finite=output_finite, output_slave_zero=output_slave_zero)
                    if not warmup:
                        repeat_key = (backend, name) if packed else name
                        if repeat_key in first_repeat:
                            errors = {}
                            for current_path in sorted(current[0].glob('*.npy')):
                                old = np.load(first_repeat[repeat_key]/current_path.name, mmap_mode='r', allow_pickle=False)
                                new = np.load(current_path, mmap_mode='r', allow_pickle=False)
                                absolute = float(np.linalg.norm(new-old))
                                norm = float(np.linalg.norm(old))
                                errors[current_path.name] = dict(absolute=absolute,
                                    relative=None if norm == 0 else absolute/norm,
                                    passed=absolute <= 1e-11*(norm if norm else 1))
                                del old, new
                            state['last_safe']['repeat_comparison'] = errors
                            if not all(row['passed'] for row in errors.values()):
                                raise ValueError('same-input repeated profile outputs differ')
                        else:
                            first_repeat[repeat_key] = current[0]
                    if packed:
                        state['last_safe']['resource_after'] = ledger.resource_sample()
                    state['active_apply'] = None
                    state['timings'] = timing.snapshot()
                    delta = {key: {field: value-before.get(key, {}).get(field, 0)
                                   for field, value in row.items()}
                             for key, row in state['timings'].items()}
                    # Subtract only maximal IO/log subtrees, never nested children twice.
                    excluded = sum(row['inclusive_seconds'] for key, row in delta.items()
                        if key.startswith('PC/') and key.split('/')[-1] in
                        ('artifact_io', 'log_marker', 'log_append') and not any(
                            part in ('artifact_io', 'log_marker', 'log_append') for part in key.split('/')[1:-1]))
                    state['last_safe']['pc_compute_seconds'] = delta['PC']['inclusive_seconds']-excluded
                    capture_only = sum(row['inclusive_seconds'] for key, row in delta.items()
                        if key.startswith('PC/') and key.split('/')[-1] == 'artifact_io'
                        and 'artifact_io' not in key.split('/')[1:-1])
                    state['last_safe']['pc_wall_excluding_diagnostic_capture_seconds'] = (
                        delta['PC']['inclusive_seconds']-capture_only)
                    state['last_safe']['pc_inclusive_seconds'] = delta['PC']['inclusive_seconds']
                    state['last_safe']['pc_excluded_io_log_seconds'] = excluded
                    _atomic_json(directory/'state.json', state)
                    # Append first even if a performance signal arrived during the PC.
                    ledger.append('profile_applies.jsonl', dict(state['last_safe'], timing_delta=delta))
                    ledger.marker('profile_pc_complete', state['last_safe'], allow_stop=True)
                finally:
                    if packed:
                        timing.close()
                    if solution is not None:
                        solution.destroy()
            safe()
            state['status'] = 'PROFILE_COMPLETED'
            if 'equivalent_fast' in bundle:
                from .physical_pc_comparison import compare_profiles, compare_paired_profile
                _atomic_json(directory/'state.json', state)
                comparison = (compare_paired_profile(directory.parent) if packed else
                    compare_profiles(config['r0_reference']['root'], directory.parent))
                _atomic_json(directory.parent/'pc_comparison.json', comparison)
                if not comparison['passed']:
                    raise ValueError('R1 numerical equivalence gate failed')
            return dict(passed=True, errors=[], summary=str(directory/'state.json'),
                        numerical_output_directory=None, diagnostic_only=True)
    except BaseException as exc:
        state.update(status='CONTROLLED_STOP' if isinstance(exc, InterruptedError) else 'FAILED',
                     exception_type=type(exc).__name__, exception_message=str(exc))
        raise
    finally:
        timing.close()
        state['timings'] = timing.snapshot()
        state['stop_signal'] = ledger.stop_signal
        state['elapsed_since_worker_start'] = time.monotonic()-ledger.started
        _atomic_json(directory/'state.json', state)


def cleanup_profile(summary, directory, callbacks):
    """Persist primary evidence before cleanup; preserve all secondary errors."""
    path = Path(directory)/'physical_intermediate_summary.json'
    _atomic_json(path, summary)
    first_error = None
    for name, callback in callbacks:
        try:
            callback()
        except BaseException as exc:
            first_error = first_error or exc
            summary.setdefault('cleanup_errors', []).append(dict(
                stage=name, exception_type=type(exc).__name__, exception_message=str(exc)))
            if summary['status'] not in ('FAILED', 'CONTROLLED_STOP', 'PERFORMANCE_CONTROLLED_STOP', 'REFERENCE_RESOURCE_BLOCKED'):
                summary['status'] = 'FAILED'
            _atomic_json(path, summary)
    return first_error
