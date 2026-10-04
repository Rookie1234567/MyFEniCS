"""Explicit platform profiles for the frozen Task40 W0 runtime."""

from __future__ import annotations

from pathlib import Path
import platform


NATIVE_LINUX_PROFILE = "native_linux"
LOCAL_WSL2_PROFILE = "local_wsl2_authorized"
RUNTIME_PROFILES = (NATIVE_LINUX_PROFILE, LOCAL_WSL2_PROFILE)


def current_runtime_identity(
    profile: str,
    *,
    platform_system: str | None = None,
    platform_release: str | None = None,
    proc_version: str | None = None,
    boot_id: str | None = None,
) -> dict[str, object]:
    """Return host facts only when the requested profile matches this host."""
    system = platform.system() if platform_system is None else platform_system
    release = platform.release() if platform_release is None else platform_release
    if proc_version is None:
        try:
            proc_version = Path("/proc/version").read_text()
        except OSError:
            proc_version = ""
    if boot_id is None:
        try:
            boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        except OSError:
            boot_id = ""

    combined = f"{release}\n{proc_version}".lower()
    microsoft = "microsoft" in combined
    wsl2 = microsoft and ("wsl2" in combined or "microsoft-standard" in combined)
    if system != "Linux":
        raise RuntimeError(f"Task40 runtime profiles require Linux, found {system!r}")
    if not boot_id:
        raise RuntimeError("Task40 runtime host boot ID is unavailable")
    if profile == NATIVE_LINUX_PROFILE:
        if microsoft:
            raise RuntimeError("native_linux profile rejects WSL; use the explicitly authorized local WSL2 profile")
        execution_platform = "native_linux"
    elif profile == LOCAL_WSL2_PROFILE:
        if not wsl2:
            raise RuntimeError("local_wsl2_authorized profile requires a real WSL2 kernel")
        execution_platform = "wsl2_local"
    else:
        raise RuntimeError(f"unsupported Task40 runtime profile: {profile!r}")

    return {
        "runtime_profile": profile,
        "execution_platform": execution_platform,
        "platform_system": system,
        "platform_release": release,
        "wsl2_detected": wsl2,
        "boot_id": boot_id,
    }


def validate_runtime_receipt(
    receipt: dict[str, object],
    *,
    requested_profile: str | None = None,
    current_identity: dict[str, object] | None = None,
) -> dict[str, object]:
    """Validate a new profile/boot-bound receipt or a historical native-only receipt."""
    recorded_profile = receipt.get("runtime_profile")
    if recorded_profile is None:
        if "runtime_host" in receipt:
            raise RuntimeError("ABI receipt has a host identity but no runtime profile")
        profile = requested_profile or NATIVE_LINUX_PROFILE
        if profile != NATIVE_LINUX_PROFILE:
            raise RuntimeError("local_wsl2_authorized requires a fresh profile- and boot-bound ABI receipt")
        current = (current_runtime_identity(profile) if current_identity is None
                   else current_identity)
        if (current.get("execution_platform") != "native_linux"
                or current.get("wsl2_detected") is True):
            raise RuntimeError("native_linux profile rejects WSL and non-native hosts")
        if current.get("runtime_profile") != profile:
            raise RuntimeError("current host does not match the selected native-only legacy profile")
        return {**current, "receipt_host_binding": "legacy_native_only_without_boot_binding"}
    if not isinstance(recorded_profile, str):
        raise RuntimeError("run-local ABI receipt has an invalid runtime profile")
    if requested_profile is not None and recorded_profile != requested_profile:
        raise RuntimeError("ABI receipt runtime profile differs from the selected launcher profile")
    profile = recorded_profile
    current = (current_runtime_identity(profile) if current_identity is None
               else current_identity)
    if current.get("runtime_profile") != profile:
        raise RuntimeError("current host does not match the ABI receipt runtime profile")
    recorded = receipt.get("runtime_host")
    if not isinstance(recorded, dict):
        raise RuntimeError("run-local ABI receipt has no host/boot identity")
    keys = ("runtime_profile", "execution_platform", "platform_system",
            "platform_release", "wsl2_detected", "boot_id")
    if any(recorded.get(key) != current.get(key) for key in keys):
        raise RuntimeError("run-local ABI receipt belongs to a different runtime profile, host, or boot")
    return {**current, "receipt_host_binding": "exact_profile_host_and_boot"}
