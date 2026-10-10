"""Bounded metadata consumer; no FE imports, assembly or numerical solve."""
import numpy as np
import pytest

from benchmarks.collect_assembly_tetra import stored_value_inventory


def test_inventory_streams_exact_complex_values_without_mmap(tmp_path, monkeypatch):
    values = np.array([0, 2+3j, 0, -1j, np.nan+0j, np.inf+1j], np.complex128)
    path = tmp_path/'values.npy'
    np.save(path, values)
    monkeypatch.setattr(np, 'load', lambda *a, **k: pytest.fail('no mmap or full np.load'))
    r = stored_value_inventory(path, dict(dtype='complex128', shape=[6]), chunk_entries=2)
    assert (r['stored_entries'], r['exact_nonzero_entries'], r['explicit_zero_entries']) == (6, 4, 2)
    assert r['nonfinite_entries'] == 2
    assert r['bytes_scanned'] == values.nbytes and r['maximum_block_bytes'] == 32
    assert r['memory_mapped'] is False


def test_inventory_rejects_wrong_identity_and_partial_payload(tmp_path):
    path = tmp_path/'values.npy'
    np.save(path, np.arange(7, dtype=np.float64))
    with pytest.raises(ValueError, match='identity'):
        stored_value_inventory(path, dict(dtype='complex128', shape=[7]))
    payload = path.read_bytes()
    path.write_bytes(payload[:-3])
    with pytest.raises(ValueError, match='truncated'):
        stored_value_inventory(path, dict(dtype='float64', shape=[7]), chunk_entries=2)
