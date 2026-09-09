"""Packet serialization must not retain arrays until cyclic GC runs."""
import gc
import hashlib
import json
import weakref

import numpy as np

from src.runners.physical_diagnosis_worker import save_packet
from src.runners.physical_diagnostic_completion import load_packet


def test_packet_roundtrip_releases_arrays_without_cyclic_gc(tmp_path):
    enabled = gc.isenabled()
    gc.disable()
    try:
        original = np.arange(12, dtype=float).reshape(3, 4).astype(complex)
        original[0, 0] = 1 - 2j
        expected = original.copy()
        ref = weakref.ref(original)
        save_packet(tmp_path, 'sample', {'nested': [{'D': original}], 'label': 'same'})
        del original
        retained_before_gc = ref() is not None
        gc.collect()
        assert ref() is None
        assert not retained_before_gc, 'save_packet retains array until cyclic GC'
        record = json.loads((tmp_path / 'sample.json').read_text())
        packet = tmp_path / 'sample.npz'
        assert record['arrays']['sha256'] == hashlib.sha256(packet.read_bytes()).hexdigest()
        assert record['nested'][0]['D'] == {
            'array_key': 'array_0', 'shape': [3, 4], 'dtype': 'complex128'}
        with np.load(packet, allow_pickle=False) as arrays:
            assert arrays['array_0'].tobytes() == expected.tobytes()
        assert record['label'] == 'same'
        save_packet(tmp_path, 'selection', {'P': expected, 'A': expected.copy()})
        loaded = load_packet(tmp_path / 'selection.json')
        selected = loaded['P']
        unused = weakref.ref(loaded['A'])
        del loaded
        retained_before_gc = unused() is not None
        gc.collect()
        assert unused() is None
        assert not retained_before_gc, 'load_packet retains unselected array until cyclic GC'
        assert selected.tobytes() == expected.tobytes()
    finally:
        if enabled:
            gc.enable()
