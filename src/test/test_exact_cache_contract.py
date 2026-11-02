import hashlib
import json

import pytest

from src.runners.exact_cache_contract import (
    load_exact_cache_contract,
    numerical_source_digest,
)


def fixture(tmp_path, cpus):
    payload = {"test": 1}
    doc = {
        "schema": "exact-cache-execution.v1",
        "source_sha": "a" * 40,
        "resolved_payload_sha256": hashlib.sha256(b'{"test":1}').hexdigest(),
        "worker_cpus": cpus,
        "tensor_root": str(tmp_path / "tensor"),
        "carrier_root": str(tmp_path / "carrier"),
    }
    p = tmp_path / "contract.json"
    p.write_text(json.dumps(doc))
    h = hashlib.sha256(p.read_bytes()).hexdigest()
    return p, h, payload


@pytest.mark.parametrize("workers", [1, 4, 8, 16, 32])
def test_supported_explicit_worker_counts(tmp_path, workers):
    p, h, payload = fixture(tmp_path, list(range(workers)))
    d = load_exact_cache_contract(p, h, source_sha="a" * 40, resolved_payload=payload)
    assert len(d["raw"]["cpus"]) == workers


@pytest.mark.parametrize(
    "negative", ["hash", "source", "resolved", "cpus", "missing_source"]
)
def test_rejects_unbound_contract(tmp_path, negative):
    p, h, payload = fixture(tmp_path, [0, 1, 2, 2] if negative == "cpus" else [0])
    with pytest.raises(ValueError):
        load_exact_cache_contract(
            p,
            "0" * 64 if negative == "hash" else h,
            source_sha=None
            if negative == "missing_source"
            else "b" * 40
            if negative == "source"
            else "a" * 40,
            resolved_payload={} if negative == "resolved" else payload,
        )


def test_numerical_source_identity_survives_test_only_change_but_not_code(tmp_path):
    production = tmp_path / "solver.py"
    production.write_text("value = 1\n")
    before = numerical_source_digest(tmp_path)
    tests = tmp_path / "test"
    tests.mkdir()
    (tests / "test_solver.py").write_text("assert True\n")
    assert numerical_source_digest(tmp_path) == before
    production.write_text("value = 2\n")
    assert numerical_source_digest(tmp_path) != before
