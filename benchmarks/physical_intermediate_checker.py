"""Independent raw-output checks; never construct or invoke a PDE solver."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np


def check(directory: Path) -> dict:
    started = time.monotonic()
    summary = json.loads((directory / 'physical_intermediate_summary.json').read_text())
    errors, facts = [], {}

    def require(condition, message):
        if not condition:
            errors.append(message)

    def hashed_file(filename, digest):
        path = directory / filename
        require(path.is_relative_to(directory) and path.is_file(), f'missing artifact: {filename}')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == digest, f'artifact hash mismatch: {filename}')
        return path

    raw = summary['residual_arrays']
    with np.load(hashed_file(raw['filename'], raw['sha256']), allow_pickle=False) as arrays:
        rhs, action, solution = arrays['rhs'], arrays['action'], arrays['solution']
        require(rhs.shape == action.shape == solution.shape, 'incompatible raw vector shapes')
        require(all(np.isfinite(v).all() for v in (rhs, action, solution)), 'nonfinite raw vectors')
        residual = np.linalg.norm(rhs-action)/max(np.linalg.norm(rhs), np.finfo(float).tiny)
        facts['full_explicit_true_relative_residual'] = float(residual)
        require(np.isfinite(residual) and residual <= 1e-6, f'fine residual {residual} exceeds 1e-6')
        solve = summary['solve']
        require(abs(residual-solve['final_true_residual']) <= max(1e-12, .001*residual), 'raw/reported true residual mismatch')
        require(solve['reason'] >= 0 or solve['reason'] == -3, f'KSP breakdown reason {solve["reason"]}')
        for cycle in solve['cycles']:
            reported = cycle['reported_final_residual']/max(np.linalg.norm(rhs), np.finfo(float).tiny)
            difference = abs(reported-cycle['explicit_true_residual'])
            require(np.isfinite(difference) and difference <= max(1e-10, .01*cycle['explicit_true_residual']),
                    f'reported/true norm mismatch at iteration {cycle["end_iteration"]}: {difference}')
    require(summary['solve_monotonic_seconds'] <= 3600, 'solve budget exceeded')
    require(summary['elapsed_monotonic_seconds'] <= 7200, 'workflow budget exceeded before checker')
    require(summary['auxiliary_stack_released_before_recovery'] is True, 'auxiliary stack not released')
    output = summary.get('official_result')
    if output is None:
        errors.append('official outputs unavailable')
    else:
        port, volume = output['port_metrics'], output['volume_metrics']
        r, t, a, av = port['R_total'], port['T_total'], port['A_balance'], volume['A_volume_total']
        facts['physics'] = dict(R=r, T=t, A=a, A_volume=av,
                               volume_energy_error=abs(r+t+av-1), absorption_difference=abs(a-av))
        require(np.isfinite([r, t, a, av]).all(), 'nonfinite R/T/A/A_volume')
        require(abs(r+t+av-1) <= 1e-5, f'independent volume energy error {abs(r+t+av-1)} exceeds 1e-5')
        require(abs(a-av) <= 1e-5, f'absorption difference {abs(a-av)} exceeds 1e-5')
        require(min(r, t, a, av) >= -1e-12, f'passivity sign error: {r,t,a,av}')
        modal = json.loads((directory / 'numerical_output/dtn_port_diffraction_orders_3d.json').read_text())
        rows = modal['orders']
        require(len(rows) == port['dtn_port_mode_count'], 'incomplete mode output')
        keys = [(row['side'], row['m'], row['n'], row['polarization']) for row in rows]
        require(len(keys) == len(set(keys)), 'duplicate mode keys')
        require(abs(sum(row['R'] for row in rows)-r) <= 1e-12, 'reflection channel sum mismatch')
        require(abs(sum(row['T'] for row in rows)-t) <= 1e-12, 'transmission channel sum mismatch')
        require(all(np.isfinite([row['R'], row['T'], row['power_ratio']]).all() and
                    min(row['R'], row['T']) >= -1e-12 for row in rows), 'nonfinite or negative channel power')
        amplitudes = json.loads((directory / 'numerical_output/dtn_auxiliary_amplitudes_3d.json').read_text())
        require(len(amplitudes) == len(rows), 'incomplete complex modal amplitudes')
        def finite_numbers(value):
            if isinstance(value, dict):
                return all(finite_numbers(v) for v in value.values())
            if isinstance(value, list):
                return all(finite_numbers(v) for v in value)
            return not isinstance(value, (int, float)) or bool(np.isfinite(value))
        require(finite_numbers(amplitudes), 'nonfinite complex modal amplitudes')
        exported = output['field_export']
        samples = Path(exported['full3d_reference_archive'])
        require(hashlib.sha256(samples.read_bytes()).hexdigest() == exported['full3d_reference_archive_sha256'],
                'E/H sample hash mismatch')
        with np.load(samples, allow_pickle=False) as arrays:
            e, h = arrays['E_V_per_m'], arrays['H_A_per_m']
            require(e.shape == h.shape and e.ndim == 4 and e.shape[-1] == 3, 'E/H sample shape mismatch')
            require(np.iscomplexobj(e) and np.iscomplexobj(h) and np.isfinite(e).all() and np.isfinite(h).all(),
                    'invalid complex E/H samples')
            require(all(np.isfinite(arrays[k]).all() for k in ('x_nm', 'y_nm', 'z_nm')), 'nonfinite sample coordinates')
        canonical = output['canonical_vector']
        hashed_file('numerical_output/' + canonical['filename'], canonical['file_sha256'])
        from benchmarks.canonical_vector_artifacts import read_canonical_packet_shard

        packets = read_canonical_packet_shard(directory / 'numerical_output' / canonical['filename'])
        require(len(packets) == canonical['packet_count'] > 0, 'canonical packet count mismatch')
        require(all(np.isfinite(value) for _, value in packets), 'nonfinite canonical coefficients')
    return dict(classification='DISCRETE_SOLVER_OUTPUT_PASS' if not errors else 'NUMERICAL_OR_OUTPUT_FAIL',
                reference_authority='PENDING_A4_not_compared',
                gate_failures=errors, raw_facts=facts, checker_seconds=time.monotonic()-started,
                resource_authority='separate enclosing parent verdict required')


def main() -> int:
    directory = Path(sys.argv[1]).resolve()
    try:
        result = check(directory)
    except Exception as exc:
        result = dict(classification='EVIDENCE_INCOMPLETE', reference_authority='PENDING_A4_not_compared',
                      gate_failures=[f'{type(exc).__name__}: {exc}'])
    (directory / 'checker.json').write_text(json.dumps(result, indent=2, allow_nan=False) + '\n')
    return 0 if result['classification'] == 'DISCRETE_SOLVER_OUTPUT_PASS' else 2


if __name__ == '__main__':
    raise SystemExit(main())
