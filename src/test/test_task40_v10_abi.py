from __future__ import annotations

import os

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
