"""Fieldwise native/WSL mode identity; preserve both original byte hashes."""
import hashlib
import json
import math
from pathlib import Path

WSL_MODE_SHA = 'dee5c3ac0e5fccb8745fcef29ad0e17c8bc31717ea901c098ea1fdd5dee37bf2'
REFERENCE = (Path(__file__).resolve().parents[2] / 'docs' /
             'task39extra_para_workstation_capacity/outcomes/records/wsl_mode_manifest.json')


def compare_mode_manifest(native_bytes):
    """Exact schema/order/discrete fields; original 1e-10 numerical tolerance."""
    original = REFERENCE.read_bytes()
    if hashlib.sha256(original).hexdigest() != WSL_MODE_SHA:
        raise ValueError('historical mode manifest byte identity mismatch')
    differences = []

    def compare(old, new, path):
        if type(old) is not type(new):
            raise ValueError(f'mode field type mismatch: {path}')
        if isinstance(old, dict):
            if old.keys() != new.keys():
                raise ValueError(f'mode fields mismatch: {path}')
            for key in old:
                compare(old[key], new[key], f'{path}/{key}')
        elif isinstance(old, list):
            if len(old) != len(new):
                raise ValueError(f'mode inventory length mismatch: {path}')
            for index, (left, right) in enumerate(zip(old, new)):
                compare(left, right, f'{path}/{index}')
        elif isinstance(old, float):
            scale = max(abs(old), abs(new), 1e-30)
            relative = abs(old-new)/scale
            if not math.isfinite(new) or relative > 1e-10:
                raise ValueError(f'mode numerical identity mismatch: {path}')
            if old != new:
                differences.append({'path': path, 'wsl': old, 'native': new,
                                    'absolute_difference': abs(old-new), 'relative_difference': relative})
        elif old != new:
            raise ValueError(f'mode discrete identity mismatch: {path}')

    compare(json.loads(original), json.loads(native_bytes), '')
    return {'status': 'FIELDWISE_MODE_IDENTITY_PASS', 'reference_sha256': WSL_MODE_SHA,
            'native_sha256': hashlib.sha256(native_bytes).hexdigest(), 'tolerance': 1e-10,
            'changed_numeric_fields': differences,
            'maximum_relative_difference': max((d['relative_difference'] for d in differences), default=0.0)}


def qualify_native_modes(cfg):
    from src.common.modes_3d import outgoing_port_modes_3d

    from .fullspace_dtn_action import build_ordered_mode_manifest
    _, encoded, _ = build_ordered_mode_manifest(outgoing_port_modes_3d(cfg), cfg)
    return compare_mode_manifest(encoded), encoded
