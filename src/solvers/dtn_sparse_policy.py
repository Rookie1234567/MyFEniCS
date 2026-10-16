"""Explicit identities for sparse DtN functional extraction policies."""

from __future__ import annotations

LEGACY_DTN_SPARSE_CUTOFF_POLICY = "absolute_floor_relative_v1"
SCALE_HOMOGENEOUS_DTN_SPARSE_CUTOFF_POLICY = "scale_homogeneous_relative_only_v1"


def normalize_dtn_sparse_cutoff_policy(value: str | None) -> str:
    """Validate a named sparse-entry policy without changing old defaults."""

    policy = LEGACY_DTN_SPARSE_CUTOFF_POLICY if value is None else str(value)
    if policy not in {
        LEGACY_DTN_SPARSE_CUTOFF_POLICY,
        SCALE_HOMOGENEOUS_DTN_SPARSE_CUTOFF_POLICY,
    }:
        raise ValueError(f"unsupported DtN sparse cutoff policy: {policy!r}")
    return policy
