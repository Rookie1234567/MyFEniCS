"""Compare native output to the tracked, complete V5 modal observations."""
import hashlib
import json
from pathlib import Path

from .physical_balanced_output import compare_modal_files


def compare_wsl_observables(fine, outputs, directory, payload):
    if payload['incidence']['wavelength_nm'] != 13.5:
        return {'status': 'REFERENCE_AUTHORITY_LIMITED',
                'reason': 'shortwave discrete capacity test; no matched fine reference'}
    compact = Path('docs/task039_extra_physical_multilevel/outcomes/records/balanced_coupling_v5.json')
    data = json.loads(compact.read_text())
    old = data['models'][int(bool(payload['geometry'].get('cell_notch')))]
    if (old['physical_sha'] != payload['provenance']['physical_model_sha256'] or
            old['mode_sha'] != fine['mode_sha256']):
        raise ValueError('WSL/native physical or ordered mode identity mismatch')
    reference = Path(directory)/'tracked_wsl_observables'
    reference.mkdir()
    rows = old['all_mode_observables']
    (reference/'dtn_port_diffraction_orders_3d.json').write_text(json.dumps({'orders': rows}))
    (reference/'dtn_auxiliary_amplitudes_3d.json').write_text(json.dumps(rows))
    comparison = compare_modal_files(Path(directory)/'numerical_output', reference)
    port = outputs['port_metrics']
    current = {'R': port['R_total'], 'T': port['T_total'], 'A': port['A_balance'],
               'A_volume': outputs['volume_metrics']['A_volume_total']}
    differences = {key: abs(value-old['physics'][key]) for key, value in current.items()}
    passed = (comparison['mode_count'] == 80 and
              comparison['amplitude_relative_difference'] <= 1e-4 and
              comparison['power_max_absolute_difference'] <= 1e-6 and
              max(differences.values()) <= 1e-5)
    return {'status': 'REFERENCE_AUTHORITY_LIMITED' if passed else 'MATCHED_REFERENCE_FAIL',
            'wsl_modal_power_passed': passed, 'total_absolute_differences': differences,
            'full_field_comparison': 'WSL_FULL_FIELD_COMPARISON_PARTIAL',
            'reason': 'separate native matched reference required for full field qualification',
            'tracked_reference_sha256': hashlib.sha256(compact.read_bytes()).hexdigest(),
            **comparison}
