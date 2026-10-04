"""Task40 keeps native Linux strict and gates its explicitly approved local WSL2 profile."""

from __future__ import annotations

import pytest

from benchmarks import run_fresh_c1_p6_component as runner
from benchmarks.task40_runtime_profile import (
    LOCAL_WSL2_PROFILE,
    NATIVE_LINUX_PROFILE,
    current_runtime_identity,
    validate_runtime_receipt,
)


def test_native_profile_accepts_linux_and_rejects_wsl():
    identity = current_runtime_identity(
        NATIVE_LINUX_PROFILE,
        platform_system="Linux",
        platform_release="6.1.0-generic",
        proc_version="Linux version 6.1.0-generic",
        boot_id="native-boot",
    )
    assert identity["execution_platform"] == "native_linux"
    with pytest.raises(RuntimeError, match="rejects WSL"):
        current_runtime_identity(
            NATIVE_LINUX_PROFILE,
            platform_system="Linux",
            platform_release="6.6.114.1-microsoft-standard-WSL2",
            proc_version="Linux version 6.6.114.1-microsoft-standard-WSL2",
            boot_id="wsl-boot",
        )


def test_local_profile_requires_wsl2_and_never_calls_it_native():
    identity = current_runtime_identity(
        LOCAL_WSL2_PROFILE,
        platform_system="Linux",
        platform_release="6.6.114.1-microsoft-standard-WSL2",
        proc_version="Linux version 6.6.114.1-microsoft-standard-WSL2",
        boot_id="wsl-boot",
    )
    assert identity["execution_platform"] == "wsl2_local"
    assert identity["runtime_profile"] == LOCAL_WSL2_PROFILE
    with pytest.raises(RuntimeError, match="requires a real WSL2"):
        current_runtime_identity(
            LOCAL_WSL2_PROFILE,
            platform_system="Linux",
            platform_release="4.4.0-Microsoft",
            proc_version="Linux version 4.4.0-Microsoft",
            boot_id="wsl1-boot",
        )
    with pytest.raises(RuntimeError, match="requires a real WSL2"):
        current_runtime_identity(
            LOCAL_WSL2_PROFILE,
            platform_system="Linux",
            platform_release="6.1.0-generic",
            proc_version="Linux version 6.1.0-generic",
            boot_id="native-boot",
        )


def test_receipt_is_bound_to_same_profile_and_boot():
    identity = current_runtime_identity(
        LOCAL_WSL2_PROFILE,
        platform_system="Linux",
        platform_release="6.6.114.1-microsoft-standard-WSL2",
        proc_version="Linux version 6.6.114.1-microsoft-standard-WSL2",
        boot_id="wsl-boot",
    )
    receipt = {"runtime_profile": LOCAL_WSL2_PROFILE, "runtime_host": identity}
    validated = validate_runtime_receipt(receipt, current_identity=identity)
    assert all(validated[key] == value for key, value in identity.items())
    assert validated["receipt_host_binding"] == "exact_profile_host_and_boot"
    other_boot = {**identity, "boot_id": "new-wsl-boot"}
    with pytest.raises(RuntimeError, match="different runtime profile, host, or boot"):
        validate_runtime_receipt(receipt, current_identity=other_boot)
    with pytest.raises(RuntimeError, match="fresh profile- and boot-bound"):
        validate_runtime_receipt(
            {"status": "IMPORT_SCALAR_MPI_API_PASS_NO_FE_ACTION"},
            requested_profile=LOCAL_WSL2_PROFILE,
            current_identity=identity,
        )


def test_legacy_receipt_stays_native_only_without_claiming_a_boot_binding():
    native = current_runtime_identity(
        NATIVE_LINUX_PROFILE,
        platform_system="Linux",
        platform_release="6.1.0-generic",
        proc_version="Linux version 6.1.0-generic",
        boot_id="native-boot",
    )
    legacy = validate_runtime_receipt(
        {"status": "IMPORT_SCALAR_MPI_API_PASS_NO_FE_ACTION"},
        requested_profile=NATIVE_LINUX_PROFILE,
        current_identity=native,
    )
    assert legacy["receipt_host_binding"] == "legacy_native_only_without_boot_binding"
    wsl = current_runtime_identity(
        LOCAL_WSL2_PROFILE,
        platform_system="Linux",
        platform_release="6.6.114.1-microsoft-standard-WSL2",
        proc_version="Linux version 6.6.114.1-microsoft-standard-WSL2",
        boot_id="wsl-boot",
    )
    with pytest.raises(RuntimeError, match="native_linux profile rejects WSL"):
        validate_runtime_receipt(
            {"status": "IMPORT_SCALAR_MPI_API_PASS_NO_FE_ACTION"},
            requested_profile=NATIVE_LINUX_PROFILE,
            current_identity=wsl,
        )


def test_native_admission_keeps_original_public_schema(monkeypatch):
    identity = {"runtime_profile": NATIVE_LINUX_PROFILE, "fixture": "native"}
    monkeypatch.setattr(
        runner, "_qualified_runtime",
        lambda receipt: (None, None, identity if str(receipt).startswith("receipt") else
                         {"runtime_profile": LOCAL_WSL2_PROFILE}),
    )
    monkeypatch.setattr(runner, "frozen_budget_identity", lambda: {"fixture": "budget"})

    admission = runner.validate_native_runtime("receipt.json")

    assert admission["schema"] == "task40extra.fresh-c1-p6-native-admission.v1"
    assert admission["status"] == "NATIVE_ABI_AND_SOURCE_ADMISSION_PASS_NO_FE_ACTION"
    assert admission["native_abi_identity"] is identity
    assert admission["FE_action"] == "NOT_RUN"
    assert admission["PDE_solved"] is False
    with pytest.raises(RuntimeError, match="only the native_linux profile"):
        runner.validate_native_runtime("local-wsl-receipt.json")


def test_local_admission_has_separate_schema_and_no_native_identity(monkeypatch):
    identity = {"runtime_profile": LOCAL_WSL2_PROFILE, "fixture": "wsl2"}
    monkeypatch.setattr(runner, "_qualified_runtime", lambda _receipt: (None, None, identity))
    monkeypatch.setattr(runner, "frozen_budget_identity", lambda: {"fixture": "budget"})

    admission = runner.validate_fresh_runtime("receipt.json")

    assert admission["schema"] == "task40extra.fresh-c1-p6-local-wsl2-admission.v1"
    assert admission["status"] == "LOCAL_WSL2_ABI_AND_SOURCE_ADMISSION_PASS_NO_FE_ACTION"
    assert admission["runtime_abi_identity"] is identity
    assert "native_abi_identity" not in admission
    assert admission["FE_action"] == "NOT_RUN"
    assert admission["PDE_solved"] is False
