"""Frozen B0 mode/q inventory capture before any finite-element allocation."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np

from src.common.modes_3d import outgoing_port_modes_3d
from src.geometry.task41_phi90_profile import (
    TASK41_B0_CELL_COUNTS,
    TASK41_B0_PRECONDITIONER,
)
from src.solvers.fullspace_dtn_action import build_ordered_mode_manifest
from src.solvers.task40_v10_p6_periodic_profile import task41_b0_periodic_profile
from src.solvers.task40_v10_p6_yorbit import build_task40_v10_sector_contexts


# The original C1 inventory was generated under the qualified local WSL2 ABI.
# A cross-runtime comparison observed last-bit differences in two derived
# `np.vdot` reduction fields. It does not establish a cause. Keep both complete
# manifest identities exact and bind each to its qualified ABI.
TASK41_B0_MODE_COUNT = 64_120
TASK41_B0_MODE_IDENTITY_EVIDENCE_PATH = (
    "docs/task41extra_phi90_p50x50_g17x20/outcomes/"
    "b0_mode_identity_comparison_v1.json"
)
TASK41_B0_MODE_IDENTITY_EVIDENCE_SHA256 = (
    "12c1ecb4decadfd88f5439a2df209dd29e67a8dc5978ba1155d86f393fb5be06"
)
TASK41_B0_MODE_MANIFEST_IDENTITIES = (
    MappingProxyType(
        {
            "identity": "task41_b0_local_c1_mode_manifest_v1",
            "profile_identity": TASK41_B0_PRECONDITIONER,
            "runtime_profile": "local_wsl2_authorized",
            "abi_qualification": "task40_v10_exact_profile_receipt_bound",
            "abi_receipt_sha256": (
                "ac3a1120d8061fc91c818150177977e619de2fccb27fed1262cea45d90268426"
            ),
            "scalar": "complex128",
            "integer": "int32",
            "mpi_size": 1,
            "mode_count": TASK41_B0_MODE_COUNT,
            "manifest_sha256": (
                "201e5d1675511dff30340596d60f78718f9cef812ddf939a56d81e12410dbcd7"
            ),
            "manifest_bytes": 72_648_642,
            "comparison_evidence_path": TASK41_B0_MODE_IDENTITY_EVIDENCE_PATH,
            "comparison_evidence_sha256": TASK41_B0_MODE_IDENTITY_EVIDENCE_SHA256,
        }
    ),
    MappingProxyType(
        {
            "identity": "task41_b0_native_linux_mode_manifest_v1",
            "profile_identity": TASK41_B0_PRECONDITIONER,
            "runtime_profile": "native_linux",
            "abi_qualification": "task41_p0_contract_receipt_bound",
            "abi_receipt_sha256": (
                "1c4277c83a0ac6daf02197086264b9e5b337caee1b33d7cc1dd22a7dfcefe57d"
            ),
            "scalar": "complex128",
            "integer": "int32",
            "mpi_size": 1,
            "mode_count": TASK41_B0_MODE_COUNT,
            "manifest_sha256": (
                "80527cc4770abe0bc47db20c8d1f0ae8e13b75b5e090498f78cbfa75c120d0e0"
            ),
            "manifest_bytes": 72_687_587,
            "comparison_evidence_path": TASK41_B0_MODE_IDENTITY_EVIDENCE_PATH,
            "comparison_evidence_sha256": TASK41_B0_MODE_IDENTITY_EVIDENCE_SHA256,
        }
    ),
)
# Legacy names remain aliases for the original C1 inventory. Runtime code must
# resolve an identity from the qualified ABI facts instead of using these.
TASK41_B0_MODE_MANIFEST_SHA256 = str(
    TASK41_B0_MODE_MANIFEST_IDENTITIES[0]["manifest_sha256"]
)
TASK41_B0_MODE_MANIFEST_BYTES = int(
    TASK41_B0_MODE_MANIFEST_IDENTITIES[0]["manifest_bytes"]
)


def resolve_task41_b0_mode_manifest_identity(
    abi_facts: Mapping[str, Any],
) -> dict[str, Any]:
    """Select one exact B0 manifest identity from a qualified ABI receipt."""

    if not isinstance(abi_facts, Mapping):
        raise ValueError("Task41 B0 mode identity requires qualified ABI facts")
    matches = []
    for candidate in TASK41_B0_MODE_MANIFEST_IDENTITIES:
        if (
            abi_facts.get("profile_identity") == candidate["profile_identity"]
            and abi_facts.get("runtime_profile") == candidate["runtime_profile"]
            and abi_facts.get("qualification") == candidate["abi_qualification"]
            and abi_facts.get("receipt_sha256") == candidate["abi_receipt_sha256"]
            and abi_facts.get("scalar") == candidate["scalar"]
            and abi_facts.get("integer") == candidate["integer"]
            and type(abi_facts.get("mpi_size")) is int
            and abi_facts.get("mpi_size") == candidate["mpi_size"]
        ):
            matches.append(candidate)
    if len(matches) != 1:
        raise ValueError(
            "Task41 B0 mode manifest has no registered identity for this profile/runtime/ABI receipt"
        )
    return dict(matches[0])


def validate_registered_task41_b0_mode_manifest_identity(
    identity: Mapping[str, Any],
) -> dict[str, Any]:
    """Reject missing, altered, or unregistered B0 manifest identity records."""

    if not isinstance(identity, Mapping):
        raise ValueError("Task41 B0 mode manifest identity is missing")
    for candidate in TASK41_B0_MODE_MANIFEST_IDENTITIES:
        if dict(identity) == dict(candidate):
            return dict(candidate)
    raise ValueError("Task41 B0 mode manifest identity is not registered")
TASK41_B0_EXPECTED_Q_PORT_COUNTS = (
    8,
    *((0,) * 57),
    430,
    *((380,) * 41),
    516,
    572,
    *((549,) * 22),
    *((550,) * 34),
    386,
    *((387,) * 24),
    *((386,) * 17),
)
TASK41_B0_EXPECTED_SECTOR_PORT_COUNTS = tuple(
    TASK41_B0_EXPECTED_Q_PORT_COUNTS[sector]
    + TASK41_B0_EXPECTED_Q_PORT_COUNTS[sector + 100]
    for sector in range(100)
)


def build_task41_b0_mode_inventory(
    cfg: Any,
    axes: Mapping[str, tuple[float, ...]],
    *,
    abi_facts: Mapping[str, Any],
) -> tuple[
    tuple[tuple[Any, ...], tuple[Mapping[str, Any], ...], str],
    tuple[Any, ...],
    np.ndarray,
    Any,
    bytes,
    dict[str, Any],
]:
    """Generate the production mode list once and assign it across all 200 q."""

    mode_identity = resolve_task41_b0_mode_manifest_identity(abi_facts)
    actual_axes = tuple(len(axes[name]) - 1 for name in ("x", "y", "z"))
    if actual_axes != TASK41_B0_CELL_COUNTS:
        raise ValueError(f"Task41 B0 axis plan differs from its registered candidate: {actual_axes}")
    modes = tuple(outgoing_port_modes_3d(cfg))
    mode_rows, manifest_bytes, manifest_sha256 = build_ordered_mode_manifest(modes, cfg)
    if (
        len(modes) != mode_identity["mode_count"]
        or manifest_sha256 != mode_identity["manifest_sha256"]
        or len(manifest_bytes) != mode_identity["manifest_bytes"]
    ):
        raise ValueError(
            "Task41 B0 live production mode manifest differs from its registered ABI-bound identity"
        )
    contexts = build_task40_v10_sector_contexts(modes, cfg, axes)
    q_count = TASK41_B0_CELL_COUNTS[1]
    assignments = np.full(len(modes), -1, dtype=np.int16)
    for context in contexts:
        for branch, q_index in enumerate(context.global_q_indices):
            selected = context.local_branch_indices == branch
            assignments[context.original_mode_indices[selected]] = int(q_index)
    if assignments.size != len(modes) or np.any(assignments < 0) or np.any(assignments >= q_count):
        raise ValueError("Task41 B0 q assignment did not cover every ordered mode exactly once")
    q_counts = tuple(
        int(value) for value in np.bincount(assignments.astype(np.int64), minlength=q_count)
    )
    sector_counts = tuple(int(len(context.original_mode_indices)) for context in contexts)
    if (
        len(contexts) != 100
        or q_counts != TASK41_B0_EXPECTED_Q_PORT_COUNTS
        or sector_counts != TASK41_B0_EXPECTED_SECTOR_PORT_COUNTS
        or q_counts[0] != 8
        or any(q_counts[q] != 0 for q in range(1, 58))
        or any(q_counts[q] <= 0 for q in range(58, q_count))
        or min(value for value in q_counts if value) != 8
        or max(q_counts) != 572
        or min(sector_counts) != 524
        or max(sector_counts) != 816
        or sum(q_counts) != TASK41_B0_MODE_COUNT
        or sum(sector_counts) != TASK41_B0_MODE_COUNT
    ):
        raise ValueError("Task41 B0 live q/sector map differs from its prior canonical inventory")
    profile = task41_b0_periodic_profile(q_counts, sector_counts)
    inventory = (modes, mode_rows, manifest_sha256)
    facts = {
        "schema": "task41.b0.mode_q_inventory.v1",
        "status": "LIVE_PRODUCTION_MODE_MANIFEST_MATCH",
        "mode_count": len(modes),
        "mode_manifest_sha256": manifest_sha256,
        "mode_manifest_bytes": len(manifest_bytes),
        "mode_manifest_identity": mode_identity,
        "q_count": q_count,
        "q_port_counts": list(q_counts),
        "empty_q_indices": [q for q, count in enumerate(q_counts) if count == 0],
        "sector_count": len(contexts),
        "sector_port_counts": list(sector_counts),
        "profile_identity": profile.name,
        "all_q_required": True,
        "all_sectors_nonempty": all(value > 0 for value in sector_counts),
        "fe_mesh_or_dofmap_built": False,
    }
    return inventory, contexts, assignments, profile, manifest_bytes, facts


def _write_once(path: Path, content: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
    finally:
        os.close(descriptor)
    return hashlib.sha256(content).hexdigest()


def persist_task41_b0_mode_inventory(
    run_directory: str | Path,
    *,
    source_sha: str,
    input_sha256: str,
    mode_manifest_bytes: bytes,
    assignments: np.ndarray,
    facts: Mapping[str, Any],
) -> dict[str, Any]:
    """Persist the canonical manifest and assignment vector without replacement."""

    mode_identity = validate_registered_task41_b0_mode_manifest_identity(
        facts.get("mode_manifest_identity")
    )
    if (
        len(mode_manifest_bytes) != mode_identity["manifest_bytes"]
        or hashlib.sha256(mode_manifest_bytes).hexdigest()
        != mode_identity["manifest_sha256"]
        or facts.get("mode_count") != mode_identity["mode_count"]
        or facts.get("mode_manifest_sha256") != mode_identity["manifest_sha256"]
        or facts.get("mode_manifest_bytes") != mode_identity["manifest_bytes"]
    ):
        raise ValueError("Task41 B0 mode manifest bytes do not match their registered ABI-bound identity")
    q_vector = np.asarray(assignments)
    if (
        q_vector.ndim != 1
        or q_vector.size != TASK41_B0_MODE_COUNT
        or not np.issubdtype(q_vector.dtype, np.integer)
        or np.any(q_vector < 0)
        or np.any(q_vector >= TASK41_B0_CELL_COUNTS[1])
    ):
        raise ValueError("Task41 B0 persisted q assignment vector is incomplete")
    root = Path(run_directory).resolve()
    manifest_path = root / "task41_b0_mode_manifest.json"
    assignment_path = root / "task41_b0_q_assignment.json"
    assignment_payload = {
        "schema": "task41.b0.q_assignment.v1",
        "source_sha": source_sha,
        "input_sha256": input_sha256,
        "mode_manifest_sha256": mode_identity["manifest_sha256"],
        "mode_manifest_bytes": mode_identity["manifest_bytes"],
        "mode_manifest_identity": mode_identity,
        "mode_count": mode_identity["mode_count"],
        "q_count": TASK41_B0_CELL_COUNTS[1],
        "assignments": [int(value) for value in q_vector],
    }
    assignment_bytes = (
        json.dumps(assignment_payload, sort_keys=True, separators=(",", ":"), allow_nan=False)
        + "\n"
    ).encode("utf-8")
    manifest_file_sha256 = _write_once(manifest_path, mode_manifest_bytes)
    assignment_file_sha256 = _write_once(assignment_path, assignment_bytes)
    return {
        **dict(facts),
        "source_sha": source_sha,
        "input_sha256": input_sha256,
        "mode_manifest_identity": mode_identity,
        "registered_abi_bound_identity_match": True,
        "mode_manifest_path": str(manifest_path),
        "mode_manifest_file_sha256": manifest_file_sha256,
        "q_assignment_path": str(assignment_path),
        "q_assignment_file_sha256": assignment_file_sha256,
        "q_assignment_bytes": len(assignment_bytes),
        "persistence": "exclusive_create_no_replacement",
    }


def recheck_task41_b0_mode_inventory(
    run_directory: str | Path,
    inventory: Mapping[str, Any],
    *,
    source_sha: str,
    input_sha256: str,
    abi_facts: Mapping[str, Any],
) -> dict[str, Any]:
    """Reopen B0's immutable mode/q files and derive a fresh profile capability.

    Counts in the worker summary are treated as claims.  This function selects
    the registered identity for the qualified ABI, reads every persisted q label,
    recomputes q and paired-sector counts, and only then returns the profile
    inventory consumed by the V15 selector/checker.
    """

    if not isinstance(inventory, Mapping):
        raise TypeError("Task41 B0 inventory receipt must be a mapping")
    mode_identity = resolve_task41_b0_mode_manifest_identity(abi_facts)
    root = Path(run_directory).resolve()
    manifest_path = root / "task41_b0_mode_manifest.json"
    assignment_path = root / "task41_b0_q_assignment.json"
    if (
        Path(str(inventory.get("mode_manifest_path", ""))).resolve() != manifest_path
        or Path(str(inventory.get("q_assignment_path", ""))).resolve() != assignment_path
        or inventory.get("schema") != "task41.b0.mode_q_inventory.v1"
        or inventory.get("status") != "LIVE_PRODUCTION_MODE_MANIFEST_MATCH"
        or inventory.get("source_sha") != source_sha
        or inventory.get("input_sha256") != input_sha256
        or inventory.get("mode_count") != mode_identity["mode_count"]
        or inventory.get("mode_manifest_sha256") != mode_identity["manifest_sha256"]
        or inventory.get("mode_manifest_bytes") != mode_identity["manifest_bytes"]
        or inventory.get("mode_manifest_identity") != mode_identity
        or inventory.get("mode_manifest_file_sha256") != mode_identity["manifest_sha256"]
        or inventory.get("registered_abi_bound_identity_match") is not True
        or inventory.get("persistence") != "exclusive_create_no_replacement"
    ):
        raise ValueError("Task41 B0 inventory receipt differs from its fixed mode/source identity")

    manifest_bytes = manifest_path.read_bytes()
    if (
        len(manifest_bytes) != mode_identity["manifest_bytes"]
        or hashlib.sha256(manifest_bytes).hexdigest()
        != mode_identity["manifest_sha256"]
    ):
        raise ValueError("Task41 B0 canonical mode manifest hash or byte count changed")

    assignment_bytes = assignment_path.read_bytes()
    if (
        len(assignment_bytes) != inventory.get("q_assignment_bytes")
        or hashlib.sha256(assignment_bytes).hexdigest()
        != inventory.get("q_assignment_file_sha256")
    ):
        raise ValueError("Task41 B0 q-assignment artifact hash or byte count changed")
    payload = json.loads(assignment_bytes)
    if not isinstance(payload, Mapping):
        raise ValueError("Task41 B0 q-assignment artifact is not a JSON object")
    assignments = payload.get("assignments")
    if (
        payload.get("schema") != "task41.b0.q_assignment.v1"
        or payload.get("source_sha") != source_sha
        or payload.get("input_sha256") != input_sha256
        or payload.get("mode_manifest_sha256") != mode_identity["manifest_sha256"]
        or payload.get("mode_manifest_bytes") != mode_identity["manifest_bytes"]
        or payload.get("mode_manifest_identity") != mode_identity
        or payload.get("mode_count") != mode_identity["mode_count"]
        or payload.get("q_count") != TASK41_B0_CELL_COUNTS[1]
        or not isinstance(assignments, list)
        or len(assignments) != TASK41_B0_MODE_COUNT
        or any(
            type(value) is not int
            or value < 0
            or value >= TASK41_B0_CELL_COUNTS[1]
            for value in assignments
        )
    ):
        raise ValueError("Task41 B0 q-assignment artifact has an invalid mode/q identity")
    q_count = TASK41_B0_CELL_COUNTS[1]
    q_port_counts = tuple(
        int(value)
        for value in np.bincount(
            np.asarray(assignments, dtype=np.int64), minlength=q_count
        )
    )
    sector_port_counts = tuple(
        q_port_counts[sector] + q_port_counts[sector + q_count // 2]
        for sector in range(q_count // 2)
    )
    if (
        sum(q_port_counts) != mode_identity["mode_count"]
        or q_port_counts != TASK41_B0_EXPECTED_Q_PORT_COUNTS
        or sector_port_counts != TASK41_B0_EXPECTED_SECTOR_PORT_COUNTS
        or q_port_counts[0] != 8
        or tuple(q for q, count in enumerate(q_port_counts) if count == 0)
        != tuple(range(1, 58))
        or any(q_port_counts[q] < 8 for q in range(58, q_count))
        or min(value for value in q_port_counts if value) != 8
        or max(q_port_counts) != 572
        or min(sector_port_counts) != 524
        or max(sector_port_counts) != 816
        or sum(sector_port_counts) != TASK41_B0_MODE_COUNT
        or list(q_port_counts) != inventory.get("q_port_counts")
        or list(sector_port_counts) != inventory.get("sector_port_counts")
        or inventory.get("q_count") != q_count
        or inventory.get("sector_count") != q_count // 2
        or inventory.get("mode_count") != mode_identity["mode_count"]
    ):
        raise ValueError("Task41 B0 q/sector allocation differs from its fixed envelope")

    profile = task41_b0_periodic_profile(q_port_counts, sector_port_counts)
    if (
        inventory.get("profile_identity") != profile.name
        or inventory.get("profile_identity") != TASK41_B0_PRECONDITIONER
    ):
        raise ValueError("Task41 B0 profile identity differs from the verified q allocation")
    return {
        "schema": "task41.b0.verified_profile_capability.v1",
        "verified": True,
        "identity": profile.name,
        "mode_manifest_sha256": mode_identity["manifest_sha256"],
        "mode_manifest_bytes": mode_identity["manifest_bytes"],
        "mode_manifest_identity": mode_identity,
        "mode_count": mode_identity["mode_count"],
        "q_assignment_sha256": hashlib.sha256(assignment_bytes).hexdigest(),
        "q_assignment_bytes": len(assignment_bytes),
        "q_count": profile.q_count,
        "q_port_counts": list(q_port_counts),
        "twist_count": profile.replication_count,
        "sector_port_counts": list(sector_port_counts),
        "global_cell_axes": list(profile.global_cell_axes),
        "global_cell_count": profile.global_cell_count,
        "global_interior_rows": profile.global_interior_rows,
        "global_independent_rows": profile.global_independent_rows,
        "global_storage_rows": profile.global_storage_rows,
        "local_interior_rows": profile.local_interior_rows,
    }
