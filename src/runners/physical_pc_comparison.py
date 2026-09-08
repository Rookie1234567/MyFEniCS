"""Independent raw-array R0/R1 comparison; no solver or additional PC calls."""
import hashlib
import json
from pathlib import Path

import numpy as np

from src.io.physical_intermediate_profile import FAST_PROFILE as FAST_VARIANT
R0_SOURCE = '1e10d80cdb446e23001d01d3886e20bc9a33a263'
R0_RUN = '20260907T160802.006336Z'
R0_HASHES = {
    'pc_profile/state.json': 'd227fa259cda4754bc75cd186c51ea56ca03308012ca0a53481501a91856a6fb',
    'profile_applies.jsonl': '8323ce054714d0de1f139d821211c5c4797c25804c71f571910b50ab5333ee16',
    'pc_applies.jsonl': '8dcf924bf3029b9e23d0f56ce46348d79c4910c9777a3b88f86adbd3bf37c6c0',
}


def verify_r0_profile(root):
    root = Path(root).resolve()
    if root.name != R0_RUN:
        raise ValueError('R1 requires the reviewed successful R0 root')
    for name, expected in R0_HASHES.items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest() != expected:
            raise ValueError('R0 raw hash mismatch: '+name)
    return dict(root=str(root), source_sha=R0_SOURCE, raw_hashes=R0_HASHES)


def array_difference(old, new, limit=None):
    if old.shape != new.shape or old.dtype != np.complex128 or new.dtype != np.complex128:
        raise ValueError('comparison array layout/dtype mismatch')
    if not (np.all(np.isfinite(old)) and np.all(np.isfinite(new))):
        raise ValueError('nonfinite comparison array')
    absolute = float(np.linalg.norm(new-old))
    old_norm, new_norm = float(np.linalg.norm(old)), float(np.linalg.norm(new))
    return dict(absolute=absolute, old_norm=old_norm, new_norm=new_norm,
        relative=absolute/old_norm if old_norm else None, limit=limit,
        passed=None if limit is None else absolute <= limit*(old_norm if old_norm else 1))


def primary_pc_seconds(delta):
    excluded = sum(row['inclusive_seconds'] for key, row in delta.items()
        if key.startswith('PC/') and key.split('/')[-1] == 'artifact_io'
        and 'artifact_io' not in key.split('/')[1:-1])
    value = delta['PC']['inclusive_seconds']-excluded
    if not np.isfinite(value) or value <= 0:
        raise ValueError('primary full-PC time must be finite and positive')
    return value


def validate_pc_records(rows, pcs, *, schedule=None):
    from .physical_pc_profile import SCHEDULE
    schedule = SCHEDULE if schedule is None else schedule
    if len(rows) != len(schedule) or len(pcs) != len(schedule):
        raise ValueError('seven timing and actual PC records required')
    residuals = []
    for i, ((name, warmup), row, pc) in enumerate(zip(schedule, rows, pcs, strict=True), 1):
        if (row['index'], row['input'], row['warmup']) != (i, name, warmup):
            raise ValueError('fixed seven-PC schedule/warmup mismatch')
        primary_pc_seconds(row['timing_delta'])
        middle = pc['intermediate']
        if middle['factor_solve_calls'] != 1 or middle['explicit_action_count'] != 1:
            raise ValueError('each PC must use one A4 backsolve/check')
        rhs_norm, residual_norm = middle['rhs_norm'], middle['true_residual_norm']
        if not np.isfinite(rhs_norm) or rhs_norm <= 0 or not np.isfinite(residual_norm) or residual_norm < 0:
            raise ValueError('invalid original A4 raw norms')
        relative = residual_norm/rhs_norm
        if relative > 1e-10:
            raise ValueError('original A4 true residual gate failed')
        residuals.append(relative)
    return residuals


def compare_paired_profile(root):
    """Read only one shared-setup run; historical R0/R1 are never denominators."""
    from .physical_pc_profile import paired_schedule
    from src.io.physical_intermediate_profile import PACKED_PROFILE
    root = Path(root)
    state = json.loads((root/'pc_profile/state.json').read_text())
    schedule = paired_schedule(state['config'].get('checkpoint_available', True))
    rows = [json.loads(line) for line in (root/'profile_applies.jsonl').read_text().splitlines()]
    pcs = [json.loads(line) for line in (root/'pc_applies.jsonl').read_text().splitlines()]
    if (state['config']['variant'] != PACKED_PROFILE or state['completed'] != len(schedule)
            or state['active_apply'] is not None or len(rows) != len(schedule) or len(pcs) != len(schedule)):
        raise ValueError('incomplete paired profile')
    for i, (row, expected) in enumerate(zip(rows, schedule, strict=True), 1):
        if (row['input'], row['warmup'], row['backend']) != expected or row['index'] != i:
            raise ValueError('paired schedule mismatch')
    arrays = {}
    for item in state['captures']:
        p = root/'pc_profile'/item['path']
        if item['path'] in arrays or hashlib.sha256(p.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('paired capture hash/duplicate mismatch')
        array = np.load(p, mmap_mode='r', allow_pickle=False)
        if (list(array.shape) != item['shape'] or array.dtype != np.complex128 or
                item['ownership_range'] != [0, array.size]):
            raise ValueError('paired capture layout mismatch')
        arrays[item['path']] = array
    errors = {}
    names = {name for name, _, _ in schedule}
    checks = state['same_input_checks']
    expected = {name+'_'+role for name in names for role in ('B6', 'curl', 'material_mass', 'A6')}
    if len(checks) != len(expected) or {c['name'] for c in checks} != expected:
        raise ValueError('paired same-input inventory missing or duplicated')
    for c in checks:
        errors[c['name']] = array_difference(arrays[c['original']['path']], arrays[c['fast']['path']], 1e-11)
    for i in range(0, len(rows), 2):
        for role in ('S6_01.npy', 'S6_02.npy', 'PC_output.npy', 'PC_A6_output.npy'):
            errors[f'pair_{i//2+1}/{role}'] = array_difference(
                arrays[f'apply_{i+1:02d}/{role}'], arrays[f'apply_{i+2:02d}/{role}'],
                None if role == 'PC_A6_output.npy' else 1e-8)
    times, residuals, repeat_errors = {}, {}, {}
    for offset, backend in enumerate(('original', 'packed')):
        selected = rows[offset::2]
        residuals[backend] = validate_pc_records(
            [dict(r, index=i) for i, r in enumerate(selected, 1)], pcs[offset::2],
            schedule=[(n,w) for n,w,_ in schedule[offset::2]])
        if not all(r['input_unchanged'] and r['output_finite'] and r['output_slave_zero'] for r in selected):
            raise ValueError('paired stability gate failed')
        first, repeats = {}, {}
        for row in selected:
            if row['warmup']:
                continue
            prefix = f"apply_{row['index']:02d}/"
            captures = {key.removeprefix(prefix):value for key,value in arrays.items() if key.startswith(prefix)}
            required = {'S6_01.npy','S6_02.npy','PC_output.npy','PC_A6_output.npy',
                        *(f'A6_{i:02d}.npy' for i in range(1,5))}
            if not required.issubset(captures):
                raise ValueError('paired repeat raw inventory incomplete')
            name = row['input']
            if name not in first:
                first[name] = captures
                continue
            if name in repeats or first[name].keys() != captures.keys():
                raise ValueError('paired repeat raw inventory mismatch')
            repeats[name] = {key:array_difference(first[name][key],value,1e-11) for key,value in captures.items()}
        if set(repeats) != names or not all(e['passed'] for c in repeats.values() for e in c.values()):
            raise ValueError('paired repeat raw gate failed')
        repeat_errors[backend] = repeats
        times[backend] = [primary_pc_seconds(r['timing_delta']) for r in selected if not r['warmup']]
    medians = {k:float(np.median(v)) for k,v in times.items()}
    paired_ratios = [b/a for a,b in zip(times['original'],times['packed'],strict=True)]
    ratio = float(np.median(paired_ratios))
    passed = all(e['passed'] is not False for e in errors.values())
    return dict(passed=passed, comparisons=errors, primary_samples_seconds=times,
        primary_medians_seconds=medians, ratio=ratio, speed_gate_passed=passed and ratio<=.75,
        classification='PACKED_EQUIVALENCE_SPEED_PASS' if passed and ratio<=.75 else 'INSUFFICIENT',
        paired_sample_ratios=paired_ratios, gate_statistic='median(paired packed/original times)',
        ratio_of_medians_diagnostic=medians['packed']/medians['original'],
        p4_recomputed_relative_residuals=residuals, repeat_comparisons_recomputed=repeat_errors,
        timing_scope='same-run paired medians; mandatory logs included; diagnostic capture excluded',
        original_A6_on_PC_outputs='different PC outputs, diagnostic; same-input A6 gate separately enforced')


def validate_same_input_inventory(items):
    expected = {name+'_'+role for name in ('physical_rhs', 'checkpoint160_residual', 'random_complex')
                for role in ('B6', 'curl', 'material_mass', 'A6')}
    if len(items) != 12 or {item['name'] for item in items} != expected:
        raise ValueError('missing, duplicated or mismatched same-input component qualification')
    for item in items:
        for label in ('original', 'fast'):
            if item[label]['path'] != 'same_input_'+item['name']+'_'+label+'.npy':
                raise ValueError('same-input role/path mismatch')


def compare_profiles(r0_root, r1_root):
    """Recompute numerical gates and full-PC timing from hash-bound raw data."""
    binding = verify_r0_profile(r0_root)
    roots = [Path(binding['root']), Path(r1_root)]
    states = [json.loads((p/'pc_profile/state.json').read_text()) for p in roots]
    if states[1]['source_sha'] == R0_SOURCE or states[1]['config']['variant'] != FAST_VARIANT:
        raise ValueError('R1 requires its own new source and explicit fast variant')
    arrays = []
    for root, state in zip(roots, states, strict=True):
        if state['completed'] != 7 or state['active_apply'] is not None:
            raise ValueError('exactly seven complete PC applications required')
        captures = {}
        for record in state['captures']:
            path = root/'pc_profile'/record['path']
            if hashlib.sha256(path.read_bytes()).hexdigest() != record['sha256']:
                raise ValueError('capture hash mismatch: '+str(path))
            array = np.load(path, mmap_mode='r', allow_pickle=False)
            if list(array.shape) != record['shape'] or record['ownership_range'] != [0, array.size]:
                raise ValueError('capture ownership mismatch')
            captures[record['path']] = array
        arrays.append(captures)
    results = {}
    for name in ('physical_rhs', 'checkpoint160_residual', 'random_complex'):
        old, new = (a[name+'.npy'] for a in arrays)
        if not np.array_equal(old, new):
            raise ValueError('R0/R1 actual normalized input differs: '+name)
    for index in range(1, 8):
        prefix = f'apply_{index:02d}/'
        for name in ('S6_01.npy', 'S6_02.npy', 'PC_output.npy', 'PC_A6_output.npy',
                     'A6_01.npy', 'A6_02.npy', 'A6_03.npy', 'A6_04.npy'):
            limit = 1e-8 if name.startswith('S6') or name == 'PC_output.npy' else None
            results[prefix+name] = array_difference(arrays[0][prefix+name], arrays[1][prefix+name], limit)
        if not np.array_equal(arrays[1][prefix+'A6_04.npy'], arrays[1][prefix+'PC_A6_output.npy']):
            raise ValueError('external original A6 capture identity differs')
    for second, first in ((3, 2), (5, 4), (7, 6)):
        for key, value in arrays[1].items():
            if key.startswith(f'apply_{second:02d}/'):
                old = arrays[1][key.replace(f'apply_{second:02d}/', f'apply_{first:02d}/')]
                results['repeat/'+key] = array_difference(old, value, 1e-11)
    validate_same_input_inventory(states[1]['same_input_checks'])
    for item in states[1]['same_input_checks']:
        results['same_input/'+item['name']] = array_difference(
            arrays[1][item['original']['path']], arrays[1][item['fast']['path']], 1e-11)
    facts = states[1]['equivalent_fast']
    if facts['original_setup_before'] != facts['installed_after']:
        raise ValueError('original same-setup diagonal/window hashes changed')
    times = []
    p4_residuals = []
    for root in roots:
        rows = [json.loads(line) for line in (root/'profile_applies.jsonl').read_text().splitlines()]
        times.append([primary_pc_seconds(row['timing_delta']) for row in rows[1:]])
        pcs = [json.loads(line) for line in (root/'pc_applies.jsonl').read_text().splitlines()]
        residuals = validate_pc_records(rows, pcs)
        p4_residuals.append(residuals)
        if root == roots[1]:
            for row in rows:
                delta = row['timing_delta']
                for path, calls in {'PC/S6': 2, 'PC/S6/B6': 12, 'PC/S6/B6/assemble': 12,
                                    'PC/MR/A6': 3, 'PC_output_check/A6': 1}.items():
                    if delta.get(path, {}).get('calls') != calls:
                        raise ValueError('R1 actual timed calls differ: '+path)
    old_median, new_median = (float(np.median(t)) for t in times)
    if abs(old_median-22.021386729524238) > 1e-10:
        raise ValueError('R0 primary timing does not match reviewed median')
    ratio = new_median/old_median
    passed = all(row['passed'] is not False for row in results.values())
    return dict(passed=passed, comparisons=results, r0_binding=binding,
        p4_recomputed_relative_residuals=dict(R0=p4_residuals[0], R1=p4_residuals[1]),
        primary_medians_seconds=dict(R0=old_median, R1=new_median), ratio=ratio,
        speed_gate_passed=ratio <= .75, numerical_gate_passed=passed,
        different_input_a6_comparison='reported norms/absolute/relative only; not same-input action identity',
        original_window_reference='R1 same setup before/after; R0 arrays not recorded')


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('r0_root')
    parser.add_argument('r1_root')
    args = parser.parse_args()
    result = compare_profiles(args.r0_root, args.r1_root)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
