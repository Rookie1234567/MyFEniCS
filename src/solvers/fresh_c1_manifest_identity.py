"""Exact profile-scoped identity for the Task40 literal532 mode manifest."""

from __future__ import annotations


NATIVE_LINUX_PROFILE = "native_linux"
LOCAL_WSL2_PROFILE = "local_wsl2_authorized"

NATIVE_LITERAL532_MANIFEST_SHA256 = "4ace13f47bc6edf8a08e1a1df24309f6326294b6bf9d5ca4ada07208bd50c951"
LOCAL_WSL2_LITERAL532_MANIFEST_SHA256 = "afc439d8969463d3c3d46076382ec30c7a8fe3c9b1150955dc2d228a483e7f6b"


def literal532_manifest_sha256(runtime_profile: str) -> str:
    """Return the only frozen full-manifest digest admitted for a profile."""
    expected = {
        NATIVE_LINUX_PROFILE: NATIVE_LITERAL532_MANIFEST_SHA256,
        LOCAL_WSL2_PROFILE: LOCAL_WSL2_LITERAL532_MANIFEST_SHA256,
    }.get(runtime_profile)
    if expected is None:
        raise ValueError("fresh C1 mode identity requires a qualified Task40 runtime profile")
    return expected


def require_literal532_manifest_identity(
    mode_count: int, mode_sha256: str, runtime_profile: str
) -> None:
    """Reject incomplete manifests and any digest outside the exact profile map."""
    if mode_count != 532:
        raise ValueError("fresh C1 requires exactly 532 ordered physical modes")
    expected = literal532_manifest_sha256(runtime_profile)
    if mode_sha256 != expected:
        raise ValueError(
            f"fresh C1 {runtime_profile} full literal532 manifest identity mismatch"
        )
