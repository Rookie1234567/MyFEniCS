"""Thin Task039 V4 adapter for the generic selected-mode packet core.

The adapter binds the generic mode-major packet to the explicit h4/M480
qualification scope. It creates only the two independent downstream bases;
it never creates a QEP object or persists QEP workspace.
"""

from __future__ import annotations

import resource
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Mapping

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.modes.selected_mode_packet import (
    load_selected_mode_packet,
    write_selected_mode_packet,
)


TASK039_V4_SELECTED_MODE_SCOPE = "task039_v4_h4_m480"
TASK039_V4_SELECTED_MODE_COUNT = 480
_BRANCHES = ("positive", "negative")
_BRANCH_AUTHORITY = ("gram_authority", "qep_diagnostics", "selection_diagnostics")


def _require_task039_identity(identity: Mapping[str, Any]) -> None:
    if int(identity.get("mode_count", -1)) != TASK039_V4_SELECTED_MODE_COUNT:
        raise ValueError("Task039 V4 selected-mode packet requires mode_count=480")


def _require_branch_authority(metadata: Mapping[str, Any]) -> None:
    for name in _BRANCH_AUTHORITY:
        value = metadata[name]
        if not isinstance(value, Mapping) or set(value) != set(_BRANCHES):
            raise ValueError(f"Task039 V4 metadata requires {name} per branch")


def write_task039_v4_selected_mode_packet(
    directory: Path,
    *,
    positive_basis: Any,
    negative_basis: Any,
    identity: Mapping[str, Any],
    metadata: Mapping[str, Any],
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> dict[str, Any]:
    """Write the explicit V4 h4/M480 packet from live selected mode bases."""

    _require_task039_identity(identity)
    _require_branch_authority(metadata)
    return write_selected_mode_packet(
        directory,
        {"positive": positive_basis, "negative": negative_basis},
        identity=identity,
        metadata=metadata,
        scope=TASK039_V4_SELECTED_MODE_SCOPE,
        comm=comm,
    )


def load_task039_v4_selected_mode_packet(
    manifest_path: Path,
    *,
    identity: Mapping[str, Any] | None = None,
    expected_manifest_sha256: str | None = None,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> dict[str, Any]:
    """Load the V4 packet as read-only mode-major mmap arrays."""

    if identity is not None:
        _require_task039_identity(identity)
    packet = load_selected_mode_packet(
        manifest_path,
        identity=identity,
        expected_manifest_sha256=expected_manifest_sha256,
        scope=TASK039_V4_SELECTED_MODE_SCOPE,
        comm=comm,
    )
    if packet["mode_count"] != TASK039_V4_SELECTED_MODE_COUNT:
        raise ValueError("Task039 V4 selected-mode packet mode count mismatch")
    local_size = packet["ownership_range"][1] - packet["ownership_range"][0]
    for branch in _BRANCHES:
        for side in ("right_full", "left_full"):
            if packet[branch][side].shape != (
                TASK039_V4_SELECTED_MODE_COUNT,
                local_size,
            ):
                raise ValueError("Task039 V4 selected-mode packet layout mismatch")
    _require_branch_authority(packet["metadata"])
    return packet


def hydrate_task039_v4_selected_mode_packet(
    packet: Mapping[str, Any],
    *,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> SimpleNamespace:
    """Hydrate two independent lightweight bases from mode-major mmap arrays."""

    if packet["scope"] != TASK039_V4_SELECTED_MODE_SCOPE:
        raise ValueError("Task039 V4 selected-mode scope mismatch")
    if int(packet["mode_count"]) != TASK039_V4_SELECTED_MODE_COUNT:
        raise ValueError("Task039 V4 selected-mode packet mode count mismatch")
    _require_branch_authority(packet["metadata"])
    start, end = (int(value) for value in packet["ownership_range"])
    local_size = end - start
    global_size = int(packet["global_size"])
    started = time.perf_counter()
    owned_vectors: list[PETSc.Vec] = []
    branch_modes: dict[str, list[SimpleNamespace]] = {name: [] for name in _BRANCHES}

    def make_vector(values: np.ndarray) -> PETSc.Vec:
        vector = PETSc.Vec().createMPI((local_size, global_size), comm=comm)
        if tuple(int(value) for value in vector.getOwnershipRange()) != (start, end):
            vector.destroy()
            raise ValueError("Task039 V4 hydrated Vec ownership mismatch")
        vector.getArray()[:] = values
        owned_vectors.append(vector)
        return vector

    try:
        for branch_name in _BRANCHES:
            descriptor = packet["selection"][branch_name]
            right_array = packet[branch_name]["right_full"]
            left_array = packet[branch_name]["left_full"]
            for index, beta in enumerate(descriptor["beta"]):
                right = make_vector(right_array[index, :])
                left = make_vector(left_array[index, :])
                mode_key = descriptor["mode_keys"][index]
                branch_modes[branch_name].append(
                    SimpleNamespace(
                        beta=complex(beta),
                        direction=descriptor["direction"],
                        group_id=descriptor["groups"][index],
                        kind=mode_key["kind"],
                        passive_branch_valid=bool(
                            descriptor["passive_branch_valid"][index]
                        ),
                        right=SimpleNamespace(right_full=right),
                        left_full=left,
                    )
                )
    except Exception:
        for vector in owned_vectors:
            vector.destroy()
        raise

    shared_diagnostics = {
        "scope": TASK039_V4_SELECTED_MODE_SCOPE,
        "mode_count": TASK039_V4_SELECTED_MODE_COUNT,
        "ownership_range": (start, end),
        "global_size": global_size,
        "qep_calls": 0,
        "consumer_qep_required": False,
        "hydrate_seconds_max_rank": float(
            comm.allreduce(time.perf_counter() - started, op=MPI.MAX)
        ),
        "rank_historical_peak_rss_after_hydrate": float(
            comm.allreduce(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0,
                op=MPI.MAX,
            )
        ),
        "hydrate_rss_delta_mib": "not_measured",
        "vector_count_before_destroy": len(owned_vectors),
        "vector_count_after_destroy": None,
        "destroyed": False,
    }
    bases = {}
    for branch_name in _BRANCHES:
        group_indices: dict[int, list[int]] = {}
        for index, group_id in enumerate(packet["selection"][branch_name]["groups"]):
            group_indices.setdefault(int(group_id), []).append(index)
        authority = {
            name: packet["metadata"][name][branch_name] for name in _BRANCH_AUTHORITY
        }
        bases[branch_name] = SimpleNamespace(
            modes=branch_modes[branch_name],
            groups=[
                SimpleNamespace(indices=tuple(indices))
                for _, indices in sorted(group_indices.items())
            ],
            gram_authority=authority["gram_authority"],
            adjoint_solver_report=authority["qep_diagnostics"],
            selection_diagnostics=authority["selection_diagnostics"],
            packet_authority=authority,
            packet_consumer_diagnostics=shared_diagnostics,
        )
    destroyed = False

    def destroy() -> None:
        nonlocal destroyed
        if destroyed:
            return
        for vector in owned_vectors:
            vector.destroy()
        owned_vectors.clear()
        destroyed = True
        shared_diagnostics["destroyed"] = True
        shared_diagnostics["vector_count_after_destroy"] = 0

    return SimpleNamespace(
        positive_basis=bases["positive"],
        negative_basis=bases["negative"],
        packet_consumer_diagnostics=shared_diagnostics,
        destroy=destroy,
    )
