import hashlib
import json
from pathlib import Path

from src.io.input_validation import load_and_resolve
from src.runners.exact_cache_contract import load_exact_cache_contract
from src.runners.p6_condensed_direct import (
    _direct_run_contract,
    _validate_resolved_profile,
)


def test_actual_gate_cd_loader_payload_binds_execution_contract_without_fe(tmp_path):
    source_root = Path(__file__).resolve().parents[2]
    spec = load_and_resolve(
        source_root / "input/task40_gate_cd/gate_cd_0p7_mapped_m8n64_p6_direct.dat"
    )
    payload = spec.as_jsonable()
    profile = _validate_resolved_profile(payload)
    assert _direct_run_contract(profile["identity"])["gate_cd_case"] is True
    # Same JSON round trip used by the standard worker bootstrap.
    resolved = json.loads(json.dumps(payload))
    canonical = json.dumps(
        resolved, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    document = {
        "schema": "exact-cache-execution.v1",
        "source_sha": "a" * 40,
        "resolved_payload_sha256": hashlib.sha256(canonical.encode()).hexdigest(),
        "worker_cpus": [0, 2, 4, 6],
        "tensor_root": str(tmp_path / "tensor"),
        "carrier_root": str(tmp_path / "carrier"),
    }
    path = tmp_path / "contract.json"
    path.write_text(json.dumps(document))
    options = load_exact_cache_contract(
        path,
        hashlib.sha256(path.read_bytes()).hexdigest(),
        source_sha="a" * 40,
        resolved_payload=resolved,
    )
    assert (
        options["raw"]["operator_identity"]["numerical_source_sha256"]
        == (options["carrier"]["numerical_source_sha256"])
    )
    assert options["raw"]["cpus"] == [0, 2, 4, 6]
