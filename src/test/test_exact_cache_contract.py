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


def test_production_contract_and_raw_key_match_frozen_z10_cache_without_fe(tmp_path):
    """Exercise the real contract/key builders against one old raw-cache key."""
    from src.solvers.parallel_tensor_cache import key_for

    source_commit = "a" * 40
    payload = {"run_id": "task40_gate_cd_fin0_sti_z10_m8n2_p6_direct_v1"}
    document = {
        "schema": "exact-cache-execution.v1",
        "source_sha": source_commit,
        "resolved_payload_sha256": hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
        "worker_cpus": [0],
        "tensor_root": str(tmp_path / "tensor"),
        "carrier_root": str(tmp_path / "carrier"),
    }
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(document), encoding="utf-8")
    loaded = load_exact_cache_contract(
        contract_path,
        hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        source_sha=source_commit,
        resolved_payload=payload,
    )

    frozen_source_sha = "4a2e2bc5efb4625bda296701ecfbd4dd326d274266f7a1bd823f60142e1a59d1"
    assert numerical_source_digest() == frozen_source_sha
    assert loaded["raw"]["operator_identity"] == {
        "numerical_source_sha256": frozen_source_sha,
        "scalar": "complex128",
        "q": 21,
        "degree": 6,
    }
    assert loaded["carrier"]["numerical_source_sha256"] == frozen_source_sha

    # These fields are copied from the frozen 2026-11-04 request record.  No
    # DOLFINx mesh, PETSc matrix, or finite-element assembly is imported here.
    job = {
        "coordinates": [
            [0.0, 0.0, 0.0],
            [16.5, 0.0, 0.0],
            [0.0, 0.20624999999999982, 0.0],
            [16.5, 0.20624999999999982, 0.0],
            [0.0, 0.10000000000000009, 5.0],
            [16.5, 0.10000000000000009, 5.0],
            [0.0, 0.3125, 5.0],
            [16.5, 0.3125, 5.0],
        ],
        "dimension": 882,
        "form_symbol": "form_f4ee9bd1b0ab6bebc9390e1ad56091892a8e29a5",
        "module_sha256": "ac4b7ab8a70ac85df5de2d49fc84a84cb20b9298f889ed1d179b814726ccf56b",
        "operator_identity": {
            **loaded["raw"]["operator_identity"],
            "element_hash": 16913352432823651554,
            "form_signature": "db5b74a906a3920966f8b4c145ff7a508f8c95e68198f42e4f99c7e8cc4d2e29dc91182e59ef4da77a7056dee25c143f5d116ce30d2b7cdb325b9c2875d91313",
            "kernel_ids": list(range(101, 124)),
        },
        "tag": 104,
    }
    assert key_for(job) == "ae35294bd09f28e484074309f55aaac2a0afc0fe8cd3f746304211dc0663df6e"
