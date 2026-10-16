from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from src.io.physical_intermediate_profile import (
    TASK40_V15_P6_PROFILES,
    TASK40_V18_P6_PROFILES,
    TASK40_V20_P6_PROFILES,
)
from src.runners import fine_reference_preflight
from src.runners.physical_p4_schur_v14 import _abi_facts
from src.runners.task40_v10_abi import qualified_task40_v10_abi


def test_abi_facts_keeps_legacy_default_and_rejects_non_v10_profile(monkeypatch):
    monkeypatch.setattr(fine_reference_preflight, "qualified_abi", lambda: {"legacy": True})
    assert _abi_facts() == {"legacy": True}
    with pytest.raises(RuntimeError, match="only an exact reviewed p4/p6 profile"):
        _abi_facts(profile_identity="legacy_profile")


@pytest.mark.parametrize(
    "profile_identity",
    (*TASK40_V15_P6_PROFILES, *TASK40_V18_P6_PROFILES, *TASK40_V20_P6_PROFILES),
)
def test_v15_v18_v20_profiles_reuse_qualified_abi_without_fe(profile_identity):
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        pytest.skip("requires the existing qualified local Task40 ABI activation")

    facts = qualified_task40_v10_abi(profile_identity=profile_identity)

    assert facts["qualification"] == "task40_v10_exact_profile_receipt_bound"
    assert facts["profile_identity"] == profile_identity
    assert facts["scalar"] == "complex128"
    assert facts["integer"] == "int32"
    assert facts["mpi_size"] == 1
    assert facts["receipt_sha256"] == (
        "ac3a1120d8061fc91c818150177977e619de2fccb27fed1262cea45d90268426"
    )
    assert len(str(facts["receipt_source_sha256"])) == 64
    assert set(facts["threads"].values()) == {"1"}


def test_v15_abi_gate_still_rejects_unknown_profile_before_environment_access():
    with pytest.raises(RuntimeError, match="only an exact reviewed p4/p6 profile"):
        qualified_task40_v10_abi(profile_identity="unregistered_task40_profile")


def test_v15_abi_gate_still_rejects_wrong_thread_limit(monkeypatch):
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        pytest.skip("requires the existing qualified local Task40 ABI activation")

    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "2")
    with pytest.raises(RuntimeError, match="thread limits to equal one"):
        qualified_task40_v10_abi(
            profile_identity="task40extra_v15_p6_y_orbit_b0_reference_v1"
        )


def test_v15_abi_gate_still_binds_the_existing_receipt(monkeypatch):
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        pytest.skip("requires the existing qualified local Task40 ABI activation")

    monkeypatch.setenv("_MYFENICS_CLOUD_ABI_MANIFEST_SHA256", "0" * 64)
    with pytest.raises(RuntimeError, match="activation or receipt binding differs"):
        qualified_task40_v10_abi(
            profile_identity="task40extra_v15_p6_y_orbit_b0_reference_v1"
        )


def test_task41_a2_abi_uses_native_contract_route_and_rejects_local_receipt(
    monkeypatch, tmp_path
):
    if os.environ.get("_MYFENICS_WSL_QUALIFIED_ACTIVATION") != "1":
        pytest.skip("requires the existing qualified local Task40 ABI activation")

    import src.runners.task41_p0_contract as task41_contract_module
    from src.geometry.task41_phi90_profile import (
        TASK41_G13_A2_PRECONDITIONER,
        TASK41_G13_A2_RUN_ID,
    )
    from src.io.physical_intermediate_profile import TASK40_V15_P6_PROFILES
    from src.runners.physical_p4_schur_v14 import _abi_facts

    receipt_path = Path(os.environ["_MYFENICS_CLOUD_ABI_MANIFEST"]).resolve()
    receipt_bytes = receipt_path.read_bytes()
    receipt = json.loads(receipt_bytes)
    runtime = {
        "profile": os.environ["_MYFENICS_CLOUD_RUNTIME_PROFILE"],
        "runtime_prefix": receipt["prefix"],
        "abi_receipt_path": str(receipt_path),
        "abi_receipt_sha256": hashlib.sha256(receipt_bytes).hexdigest(),
    }
    task_contract = {
        "case": {"run_id": TASK41_G13_A2_RUN_ID},
        "runtime": runtime,
    }
    contract_path = tmp_path / "task41_a2_contract_fixture.json"
    contract_path.write_text(
        json.dumps(task_contract, sort_keys=True) + "\n", encoding="utf-8"
    )
    contract_sha256 = hashlib.sha256(contract_path.read_bytes()).hexdigest()
    monkeypatch.setenv("TASK41_P0_STRICT_EXECUTION", "1")
    monkeypatch.setenv("TASK41_P0_CONTRACT_PATH", str(contract_path))
    monkeypatch.setenv("TASK41_P0_CONTRACT_SHA256", contract_sha256)
    monkeypatch.delenv("TASK40_V30_STRICT_EXECUTION", raising=False)
    monkeypatch.delenv("TASK40_V31_STRICT_EXECUTION", raising=False)
    contract_calls = []

    def fixture_contract(path, **kwargs):
        contract_calls.append((Path(path).resolve(), kwargs))
        return task_contract, contract_sha256

    monkeypatch.setattr(
        task41_contract_module, "require_task41_p0_contract", fixture_contract
    )
    with pytest.raises(RuntimeError, match="contract-bound native_linux runtime"):
        _abi_facts(profile_identity=TASK41_G13_A2_PRECONDITIONER)
    assert contract_calls[0][0] == contract_path.resolve()
    assert contract_calls[0][1]["case_id"] == "A2"
    assert contract_calls[0][1]["expected_sha256"] == contract_sha256

    monkeypatch.setenv("TASK40_V30_STRICT_EXECUTION", "1")
    with pytest.raises(RuntimeError, match="cannot be combined"):
        _abi_facts(profile_identity=TASK41_G13_A2_PRECONDITIONER)
    monkeypatch.delenv("TASK40_V30_STRICT_EXECUTION")
    monkeypatch.delenv("TASK41_P0_STRICT_EXECUTION")

    local_abi = qualified_task40_v10_abi(
        profile_identity=TASK40_V15_P6_PROFILES[0]
    )
    assert local_abi["runtime_profile"] == "local_wsl2_authorized"
    assert local_abi["scalar"] == "complex128"
    assert local_abi["integer"] == "int32"
    assert local_abi["mpi_size"] == 1
    assert set(local_abi["threads"].values()) == {"1"}
