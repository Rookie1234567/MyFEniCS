import copy
from pathlib import Path

import numpy as np
import pytest

from src.solvers import parallel_tensor_cache as cache


@pytest.fixture
def job(tmp_path):
    binary = tmp_path / "identity-only-module"
    binary.write_bytes(b"module-v1")
    return {
        "module_path": str(binary),
        "module_sha256": cache.digest(binary),
        "module_name": "fixture",
        "form_symbol": "fixture_form",
        "tag": 101,
        "dimension": 2,
        "coordinates": [
            [x, y, z] for z in (0.0, 1.0) for y in (0.0, 1.0) for x in (0.0, 1.0)
        ],
        "operator_identity": {"q": 21, "degree": 6, "scalar": "complex128"},
    }


def test_exact_roundtrip_and_reuse_without_worker(tmp_path, job):
    root = tmp_path / "cache"
    tensor = np.array([[1 + 2j, 3 - 4j], [5 + 6j, -7j]], dtype=np.complex128)
    cache.commit_shard(root, job, tensor, {"test": True})
    loaded = cache.load_shard(root, job)
    assert np.array_equal(np.load(loaded["path"], allow_pickle=False), tensor)
    # The fixture is not an executable kernel; this succeeds only on a cache hit.
    result = cache.run_batch([job, job], root, [0])
    assert len(result) == 1
    assert next(iter(result.values()))["cache_hit"]


@pytest.mark.parametrize(
    "field", ["coordinates", "tag", "operator_identity", "module_sha256"]
)
def test_identity_separates_exact_changes(job, field):
    other = copy.deepcopy(job)
    if field == "coordinates":
        other[field][0][0] = np.nextafter(0.0, 1.0)
    elif field == "tag":
        other[field] += 1
    elif field == "operator_identity":
        other[field]["q"] = 27
    else:
        other[field] = "0" * 64
    assert cache.key_for(job) != cache.key_for(other)


def test_corrupt_payload_fails_closed(tmp_path, job):
    cache.commit_shard(tmp_path, job, np.eye(2, dtype=np.complex128), {})
    payload = tmp_path / cache.key_for(job) / "tensor.npy"
    with payload.open("r+b") as f:
        f.seek(-1, 2)
        f.write(b"\x7f")
    with pytest.raises(ValueError, match="payload hash"):
        cache.load_shard(tmp_path, job)


def test_incomplete_write_is_not_hit(tmp_path, job):
    folder = tmp_path / cache.key_for(job)
    folder.mkdir()
    np.save(folder / "tensor.npy", np.eye(2, dtype=np.complex128))
    assert cache.load_shard(tmp_path, job) is None


@pytest.mark.parametrize(
    "tensor",
    [np.zeros((3, 3), dtype=np.complex128), np.eye(2), np.full((2, 2), np.nan + 0j)],
)
def test_invalid_tensor_not_committed(tmp_path, job, tensor):
    with pytest.raises(ValueError, match="invalid tensor"):
        cache.commit_shard(tmp_path, job, tensor, {})
    assert cache.load_shard(tmp_path, job) is None


def test_modified_binary_rejected_even_with_existing_shard(tmp_path, job):
    root = tmp_path / "cache"
    cache.commit_shard(root, job, np.eye(2, dtype=np.complex128), {})
    Path(job["module_path"]).write_bytes(b"module-v2")
    with pytest.raises(ValueError, match="module changed"):
        cache.run_batch([job], root, [0])


def test_corrupt_identity_and_duplicate_cpu_rejected(tmp_path, job):
    with pytest.raises(ValueError, match="distinct admitted CPUs"):
        cache.run_batch([job], tmp_path, [0, 0])
    cache.commit_shard(tmp_path, job, np.eye(2, dtype=np.complex128), {})
    marker = tmp_path / cache.key_for(job) / "complete.json"
    record = cache.json.loads(marker.read_text())
    record["identity"]["tag"] = 999
    cache.atomic_json(marker, record)
    with pytest.raises(ValueError, match="identity mismatch"):
        cache.load_shard(tmp_path, job)
