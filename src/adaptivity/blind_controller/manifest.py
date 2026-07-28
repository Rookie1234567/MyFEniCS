"""Closed current-cycle input manifest for external isolation checks."""

from __future__ import annotations

import hashlib
import json
from typing import Any


BLIND_INPUT_MANIFEST_SCHEMA = "task035e.blind-input-manifest.v1"
_STATES = frozenset(
    {
        "initialized",
        "solve",
        "estimate",
        "mark",
        "verify",
        "freeze_ready",
        "frozen",
    }
)


def _sha(value: str | None, *, nullable: bool) -> str | None:
    if value is None and nullable:
        return None
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise ValueError("cycle artifact identity must be SHA-256")
    return value


def build_cycle_manifest(
    *,
    trial_id: str,
    algorithm_id: str,
    source_sha: str,
    initial_path_id: str,
    maximum_cycles: int,
    cycle_index: int,
    state: str,
    mesh_forest_sha256: str,
    degree_map_sha256: str,
    solution_snapshot_sha256: str,
    goal_inventory_sha256: str,
    full_residual_sha256: str,
    adjoint_bundle_sha256: str,
    p_shadow_bundle_sha256: str | None,
    h_shadow_bundle_sha256: str | None,
    resource_inventory_sha256: str,
) -> dict[str, Any]:
    """Build the exact additional-properties-false manifest shape."""

    if not 1 <= int(maximum_cycles) <= 6:
        raise ValueError("maximum_cycles must be in [1, 6]")
    if not 0 <= int(cycle_index) < int(maximum_cycles):
        raise ValueError("cycle_index lies outside the trial")
    if state not in _STATES:
        raise ValueError("unsupported blind-cycle state")
    if (
        len(source_sha) not in {40, 64}
        or any(character not in "0123456789abcdef" for character in source_sha)
    ):
        raise ValueError("source_sha must be lowercase Git or SHA-256 identity")
    return {
        "schema": BLIND_INPUT_MANIFEST_SCHEMA,
        "trial": {
            "trial_id": str(trial_id),
            "algorithm_id": str(algorithm_id),
            "source_sha": source_sha,
            "initial_path_id": str(initial_path_id),
            "maximum_cycles": int(maximum_cycles),
        },
        "cycle": {
            "cycle_index": int(cycle_index),
            "state": state,
            "mesh_forest_sha256": _sha(
                mesh_forest_sha256,
                nullable=False,
            ),
            "degree_map_sha256": _sha(
                degree_map_sha256,
                nullable=False,
            ),
            "solution_snapshot_sha256": _sha(
                solution_snapshot_sha256,
                nullable=False,
            ),
            "goal_inventory_sha256": _sha(
                goal_inventory_sha256,
                nullable=False,
            ),
            "full_residual_sha256": _sha(
                full_residual_sha256,
                nullable=False,
            ),
            "adjoint_bundle_sha256": _sha(
                adjoint_bundle_sha256,
                nullable=False,
            ),
            "p_shadow_bundle_sha256": _sha(
                p_shadow_bundle_sha256,
                nullable=True,
            ),
            "h_shadow_bundle_sha256": _sha(
                h_shadow_bundle_sha256,
                nullable=True,
            ),
            "resource_inventory_sha256": _sha(
                resource_inventory_sha256,
                nullable=False,
            ),
        },
    }


def cycle_manifest_sha256(manifest: dict[str, Any]) -> str:
    """Return the canonical content identity consumed by the isolation gate."""

    if manifest.get("schema") != BLIND_INPUT_MANIFEST_SCHEMA:
        raise ValueError("blind input manifest schema differs")
    return hashlib.sha256(
        json.dumps(
            manifest,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    ).hexdigest()


__all__ = [
    "BLIND_INPUT_MANIFEST_SCHEMA",
    "build_cycle_manifest",
    "cycle_manifest_sha256",
]
