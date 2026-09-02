"""Thin Task039 V4 adapter for the generic selected-mode packet core.

The adapter binds the generic mode-major packet to the explicit h4/M480
qualification scope. It creates only the two independent downstream bases;
it never creates a QEP object or persists QEP workspace.
"""

from __future__ import annotations

import resource
import time
from dataclasses import asdict, is_dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable, Mapping

import numpy as np
from mpi4py import MPI
from petsc4py import PETSc

from src.modes.selected_mode_packet import (
    load_selected_mode_packet,
    write_selected_mode_packet,
)


TASK039_V4_SELECTED_MODE_SCOPE = "task039_v4_h4_m480"
TASK039_V5_H5_SELECTED_MODE_SCOPE = "task039_v5_h5_m480"
TASK039_V4_SELECTED_MODE_COUNT = 480
TASK041_SELECTED_MODE_IDENTITY_SCHEMA = "task041.selected_mode_packet.identity.v1"
_BRANCHES = ("positive", "negative")
_BRANCH_AUTHORITY = ("gram_authority", "qep_diagnostics", "selection_diagnostics")


class Task039V4SelectedModeMmapContext:
    """Hold one validated read-only packet mapping for a streamed producer."""

    def __init__(
        self,
        manifest_path: Path,
        *,
        identity: Mapping[str, Any],
        expected_manifest_sha256: str,
        comm: MPI.Intracomm = MPI.COMM_WORLD,
    ) -> None:
        self.manifest_path = Path(manifest_path)
        self.packet = load_task039_v4_selected_mode_packet(
            self.manifest_path,
            identity=identity,
            expected_manifest_sha256=expected_manifest_sha256,
            comm=comm,
        )
        self._comm = comm
        self._released = False
        self._arrays = {
            (branch, role): self.packet[branch][role]
            for branch in _BRANCHES
            for role in ("right_full", "left_full")
        }

    @property
    def mode_count(self) -> int:
        if self._released:
            raise RuntimeError("Selected-mode mmap context is released")
        return int(self.packet["mode_count"])

    @property
    def diagnostics(self) -> dict[str, Any]:
        return {
            "released": bool(self._released),
            "mmap_mapping_count": 0 if self._released else 4,
            "arrays_retained": not self._released,
            "full_vec_count": 0,
            "mode_count": int(self.packet["mode_count"])
            if not self._released
            else None,
        }

    def mode_pair(self, branch: str, index: int) -> dict[str, Any]:
        if self._released:
            raise RuntimeError("Selected-mode mmap context is released")
        if branch not in _BRANCHES:
            raise ValueError("selected-mode branch is invalid")
        mode_index = int(index)
        if mode_index < 0 or mode_index >= self.mode_count:
            raise ValueError("selected-mode index is out of range")
        descriptor = self.packet["selection"][branch]
        return {
            "branch": branch,
            "index": mode_index,
            "right_local": np.array(
                self._arrays[(branch, "right_full")][mode_index, :],
                dtype=np.complex128,
                copy=True,
            ),
            "left_local": np.array(
                self._arrays[(branch, "left_full")][mode_index, :],
                dtype=np.complex128,
                copy=True,
            ),
            "beta": complex(descriptor["beta"][mode_index]),
            "mode_key": descriptor["mode_keys"][mode_index],
            "ownership_range": list(self.packet["ownership_range"]),
            "global_size": int(self.packet["global_size"]),
            "passive_branch_valid": bool(
                descriptor["passive_branch_valid"][mode_index]
            ),
        }

    def release(self) -> None:
        if self._released:
            return
        self._arrays.clear()
        self.packet = None
        self._released = True
        import gc

        gc.collect()

    def __enter__(self) -> "Task039V4SelectedModeMmapContext":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()


def _authority_json(value: Any) -> Any:
    if is_dataclass(value):
        return _authority_json(asdict(value))
    if hasattr(value, "__dict__"):
        return _authority_json(vars(value))
    if isinstance(value, Mapping):
        return {str(key): _authority_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_authority_json(item) for item in value]
    if isinstance(value, np.ndarray):
        return _authority_json(value.tolist())
    if isinstance(value, np.generic):
        return _authority_json(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    return value


def _basis_gram_authority(basis: Any) -> dict[str, Any]:
    return {
        "mode_count": len(basis.modes),
        "max_identity_error": float(basis.max_identity_error),
        "max_entry_identity_error": float(basis.max_entry_identity_error),
        "left_pair_relative_errors": [
            float(value) for value in basis.left_pair_relative_errors
        ],
        "groups": [
            {
                "indices": list(group.indices),
                "beta_center": _authority_json(group.beta_center),
                "max_relative_beta_spread": float(group.max_relative_beta_spread),
                "overlap_condition": float(group.overlap_condition),
                "normalization_method": group.normalization_method,
                "post_normalization_identity_error": float(
                    group.post_normalization_identity_error
                ),
            }
            for group in basis.groups
        ],
    }


def _basis_mode_diagnostics(basis: Any) -> list[dict[str, Any]]:
    return [
        {
            "index": index,
            "beta": _authority_json(mode.beta),
            "direction": str(mode.direction),
            "kind": str(mode.kind),
            "passive_branch_valid": bool(mode.passive_branch_valid),
            "right_polynomial_relative_residual": float(
                mode.right.polynomial_relative_residual
            ),
            "left_polynomial_relative_residual": float(
                mode.left_polynomial_relative_residual
            ),
        }
        for index, mode in enumerate(basis.modes)
    ]


def build_task039_v4_packet_metadata(
    *,
    positive_basis: Any,
    negative_basis: Any,
    positive_qep_report: Any,
    negative_qep_report: Any,
    positive_selection: Any,
    negative_selection: Any,
    reciprocal_pairs: Any | None = None,
    target_beta_per_nm: complex | None = None,
    operator_authority: Mapping[str, Any] | None = None,
    external_mode_counts: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact the real QEP authority needed by packet consumers."""

    branches = {
        "positive": positive_basis,
        "negative": negative_basis,
    }
    reports = {
        "positive": positive_qep_report,
        "negative": negative_qep_report,
    }
    selections = {
        "positive": positive_selection,
        "negative": negative_selection,
    }
    pair_rows = (
        [
            {
                "positive_index": int(pair.positive_index),
                "negative_index": int(pair.negative_index),
                "relative_beta_error": float(pair.relative_beta_error),
                "electric_mass_overlap": _authority_json(pair.electric_mass_overlap),
                "opposite_direction": bool(pair.opposite_direction),
                "passive_branches_valid": bool(pair.passive_branches_valid),
            }
            for pair in reciprocal_pairs
        ]
        if reciprocal_pairs is not None
        else []
    )
    pair_rows = list(pair_rows)
    reciprocal_pairing = {
        "complete": bool(
            reciprocal_pairs is not None
            and len(pair_rows) == len(positive_basis.modes)
            and all(
                row["opposite_direction"] and row["passive_branches_valid"]
                for row in pair_rows
            )
        ),
        "count": len(pair_rows),
        "pairs": pair_rows,
    }
    return {
        "trace_mapping": {
            "source": "ModalTraceProjection.from_right_full",
            "persisted": False,
            "consumer_reconstructs": True,
        },
        "canonical_mapping": {
            "source": (
                "ModalTraceProjection/build_hybrid_internal_mode_coupling "
                "reconstructed from right_full and left_full"
            ),
            "persisted": False,
            "consumer_reconstructs": True,
        },
        "gram_authority": {
            name: _basis_gram_authority(basis) for name, basis in branches.items()
        },
        "qep_diagnostics": {
            name: _authority_json(report) for name, report in reports.items()
        },
        "selection_diagnostics": {
            name: _authority_json(report) for name, report in selections.items()
        },
        "basis_audits": {
            name: {
                "near_degenerate_partition_audit": _authority_json(
                    getattr(basis, "near_degenerate_partition_audit", None)
                ),
                "retained_subspace_dual_rotation_audit": _authority_json(
                    getattr(basis, "retained_subspace_dual_rotation_audit", None)
                ),
                "max_left_polynomial_relative_residual": max(
                    (
                        float(mode.left_polynomial_relative_residual)
                        for mode in basis.modes
                    ),
                    default=0.0,
                ),
            }
            for name, basis in branches.items()
        },
        "mode_diagnostics": {
            name: _basis_mode_diagnostics(basis) for name, basis in branches.items()
        },
        "reciprocal_pairing": reciprocal_pairing,
        "target_beta_per_nm": _authority_json(target_beta_per_nm),
        "operator_authority": _authority_json(operator_authority),
        **(
            {"external_mode_counts": _authority_json(external_mode_counts)}
            if external_mode_counts is not None
            else {}
        ),
    }


def _require_task039_identity(identity: Mapping[str, Any]) -> None:
    if int(identity.get("mode_count", -1)) != TASK039_V4_SELECTED_MODE_COUNT:
        raise ValueError("Task039 selected-mode packet requires mode_count=480")
    scope = identity.get("scope", TASK039_V4_SELECTED_MODE_SCOPE)
    if scope not in {
        TASK039_V4_SELECTED_MODE_SCOPE,
        TASK039_V5_H5_SELECTED_MODE_SCOPE,
    }:
        raise ValueError("Task039 selected-mode packet scope is not approved")


def _valid_hex_digest(value: Any, length: int) -> bool:
    return (
        isinstance(value, str)
        and len(value) == length
        and value == value.lower()
        and all(char in "0123456789abcdef" for char in value)
    )


def task041_selected_mode_scope(mode_count: int, mpi_size: int = 1) -> str:
    if type(mode_count) is not int or mode_count < 2:
        raise ValueError("Task41 selected-mode mode count must be an int >= 2")
    if type(mpi_size) is not int or mpi_size <= 0:
        raise ValueError("Task41 selected-mode MPI size must be a positive int")
    return f"task041_5nm_p6h4_m{mode_count}_mpi{mpi_size}"


def _require_task041_identity(identity: Mapping[str, Any]) -> None:
    required = (
        "schema",
        "scope",
        "source_sha",
        "input_sha256",
        "resolved_sha256",
        "physical_sha256",
        "wavelength_nm",
        "model_id",
        "run_id",
        "mesh",
        "mode_count",
        "mpi_size",
        "external_keys",
    )
    missing = [key for key in required if key not in identity]
    if missing:
        raise ValueError(f"Task41 selected-mode identity missing: {missing}")
    if identity["schema"] != TASK041_SELECTED_MODE_IDENTITY_SCHEMA:
        raise ValueError("Task41 selected-mode identity schema mismatch")
    wavelength = identity["wavelength_nm"]
    if (
        isinstance(wavelength, bool)
        or not isinstance(wavelength, (int, float))
        or float(wavelength) != 5.0
    ):
        raise ValueError("Task41 selected-mode wavelength identity mismatch")
    if not _valid_hex_digest(identity["source_sha"], 40):
        raise ValueError("Task41 selected-mode source SHA is invalid")
    for field in ("input_sha256", "resolved_sha256", "physical_sha256"):
        if not _valid_hex_digest(identity[field], 64):
            raise ValueError(f"Task41 selected-mode {field} is invalid")
    mesh = identity["mesh"]
    if not isinstance(mesh, Mapping) or mesh != {
        "cell_type": "hexahedron",
        "kind": "full3d_uniform_cg",
        "mesh_target_nm": 4.0,
        "nedelec_degree": 6,
        "spacing_mode": "boundary_fitted",
    }:
        raise ValueError("Task41 selected-mode mesh identity mismatch")
    mode_count = identity["mode_count"]
    if type(mode_count) is not int or mode_count < 2:
        raise ValueError("Task41 selected-mode mode count must be >= 2")
    mpi_size = identity["mpi_size"]
    if type(mpi_size) is not int or mpi_size != 1:
        raise ValueError("Task41 selected-mode packet requires MPI1")
    expected_scope = task041_selected_mode_scope(mode_count, mpi_size)
    expected_model = (
        f"task041_5nm_exact_side_hybrid_iterative_p6h4_m{mode_count}"
    )
    expected_run = f"task041_5nm_p6h4_m{mode_count}_mpi{mpi_size}"
    if identity["scope"] != expected_scope:
        raise ValueError("Task41 selected-mode identity scope mismatch")
    if identity["model_id"] != expected_model:
        raise ValueError("Task41 selected-mode identity model mismatch")
    if identity["run_id"] != expected_run:
        raise ValueError("Task41 selected-mode identity run mismatch")
    external_keys = identity["external_keys"]
    if not isinstance(external_keys, Mapping) or set(external_keys) != {
        "count",
        "sha256",
    }:
        raise ValueError("Task41 selected-mode external key identity is invalid")
    if type(external_keys["count"]) is not int or external_keys["count"] <= 0:
        raise ValueError("Task41 selected-mode external key count is invalid")
    if not _valid_hex_digest(external_keys["sha256"], 64):
        raise ValueError("Task41 selected-mode external key SHA is invalid")


def _is_task041_identity(identity: Mapping[str, Any] | None) -> bool:
    return bool(
        isinstance(identity, Mapping)
        and identity.get("schema") == TASK041_SELECTED_MODE_IDENTITY_SCHEMA
    )


def _identity_mode_count(identity: Mapping[str, Any] | None) -> int:
    if _is_task041_identity(identity):
        _require_task041_identity(identity)
        return int(identity["mode_count"])
    if identity is None:
        return TASK039_V4_SELECTED_MODE_COUNT
    _require_task039_identity(identity)
    return TASK039_V4_SELECTED_MODE_COUNT


def _identity_scope(identity: Mapping[str, Any] | None) -> str:
    if identity is None:
        return TASK039_V4_SELECTED_MODE_SCOPE
    if _is_task041_identity(identity):
        _require_task041_identity(identity)
        return str(identity["scope"])
    _require_task039_identity(identity)
    return str(identity.get("scope", TASK039_V4_SELECTED_MODE_SCOPE))


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

    scope = _identity_scope(identity)
    _require_branch_authority(metadata)
    return write_selected_mode_packet(
        directory,
        {"positive": positive_basis, "negative": negative_basis},
        identity=identity,
        metadata=metadata,
        scope=scope,
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

    scope = _identity_scope(identity)
    expected_mode_count = _identity_mode_count(identity)
    packet = load_selected_mode_packet(
        manifest_path,
        identity=identity,
        expected_manifest_sha256=expected_manifest_sha256,
        scope=scope,
        comm=comm,
    )
    packet_identity = packet["identity"]
    if _is_task041_identity(packet_identity):
        _require_task041_identity(packet_identity)
    else:
        _require_task039_identity(packet_identity)
    if packet["mode_count"] != expected_mode_count:
        raise ValueError("selected-mode packet mode count mismatch")
    if packet["scope"] != scope:
        raise ValueError("selected-mode packet identity scope mismatch")
    local_size = packet["ownership_range"][1] - packet["ownership_range"][0]
    for branch in _BRANCHES:
        for side in ("right_full", "left_full"):
            if packet[branch][side].shape != (
                expected_mode_count,
                local_size,
            ):
                raise ValueError("selected-mode packet layout mismatch")
    _require_branch_authority(packet["metadata"])
    return packet


def stream_task039_v4_selected_mode_columns(
    manifest_path: Path,
    *,
    identity: Mapping[str, Any],
    expected_manifest_sha256: str,
    branch: str,
    indices: list[int] | tuple[int, ...],
    callback: Callable[[int, np.ndarray, np.ndarray, Mapping[str, Any]], None],
    comm: MPI.Intracomm = MPI.COMM_WORLD,
    batch_size: int = 1,
) -> dict[str, Any]:
    """Deliver selected right/left rows one batch at a time from read-only mmap.

    Unlike ``consume_task039_v4_selected_mode_packet``, this adapter never
    creates PETSc Vecs or mode objects.  The callback owns each copied pair
    only for the duration of its call; the mmap-backed packet is released on
    return.
    """

    if branch not in _BRANCHES:
        raise ValueError("selected-mode stream branch is invalid")
    if int(batch_size) != 1:
        raise ValueError("V7 streamed packet batch size is frozen at one")
    with Task039V4SelectedModeMmapContext(
        manifest_path,
        identity=identity,
        expected_manifest_sha256=expected_manifest_sha256,
        comm=comm,
    ) as context:
        mode_count = context.mode_count
        selected = [int(index) for index in indices]
        if any(index < 0 or index >= mode_count for index in selected):
            raise ValueError("selected-mode stream index is out of range")
        for index in selected:
            pair = context.mode_pair(branch, index)
            callback(
                index,
                pair["right_local"],
                pair["left_local"],
                {
                    "branch": branch,
                    "mode_key": pair["mode_key"],
                    "beta": pair["beta"],
                    "ownership_range": pair["ownership_range"],
                    "global_size": pair["global_size"],
                    "passive_branch_valid": bool(pair["passive_branch_valid"]),
                    "batch_size": 1,
                },
            )
        return {
            "branch": branch,
            "mode_count": mode_count,
            "selected_count": len(selected),
            "batch_size": 1,
            "arrays_retained": False,
            "consumer_qep_required": False,
        }


def hydrate_task039_v4_selected_mode_packet(
    packet: Mapping[str, Any],
    *,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> SimpleNamespace:
    """Hydrate the ordinary selected-mode bases with both adjoint sides."""

    packet_identity = packet.get("identity")
    if _is_task041_identity(packet_identity):
        _require_task041_identity(packet_identity)
        expected_mode_count = int(packet_identity["mode_count"])
        expected_scope = task041_selected_mode_scope(
            expected_mode_count, int(packet_identity["mpi_size"])
        )
    else:
        if packet["scope"] not in {
            TASK039_V4_SELECTED_MODE_SCOPE,
            TASK039_V5_H5_SELECTED_MODE_SCOPE,
        }:
            raise ValueError("Task039 selected-mode scope mismatch")
        _require_task039_identity(packet_identity)
        expected_scope = str(packet["scope"])
        expected_mode_count = TASK039_V4_SELECTED_MODE_COUNT
    if (
        packet["scope"] != expected_scope
        or int(packet["mode_count"]) != expected_mode_count
    ):
        raise ValueError("selected-mode packet identity/mode count mismatch")
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
        "scope": packet["scope"],
        "mode_count": expected_mode_count,
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
        authority["basis_audit"] = (
            packet["metadata"].get("basis_audits", {}).get(branch_name, {})
        )
        authority["mode_diagnostics"] = (
            packet["metadata"].get("mode_diagnostics", {}).get(branch_name, [])
        )
        authority["reciprocal_pairing"] = packet["metadata"].get(
            "reciprocal_pairing", {"complete": False, "count": 0, "pairs": []}
        )
        authority["target_beta_per_nm"] = packet["metadata"].get("target_beta_per_nm")
        authority["operator_authority"] = packet["metadata"].get("operator_authority")
        if "external_mode_counts" in packet["metadata"]:
            authority["external_mode_counts"] = packet["metadata"][
                "external_mode_counts"
            ]
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


def consume_task039_v4_selected_mode_packet(
    manifest_path: Path,
    *,
    identity: Mapping[str, Any],
    expected_manifest_sha256: str | None = None,
    consumer_kind: str,
    comm: MPI.Intracomm = MPI.COMM_WORLD,
) -> SimpleNamespace:
    """Load one ordinary packet and hydrate both right and left mode vectors."""

    if consumer_kind not in {"direct", "iterative"}:
        raise ValueError(
            "selected-mode packet consumer_kind must be direct or iterative"
        )
    packet = load_task039_v4_selected_mode_packet(
        manifest_path,
        identity=identity,
        expected_manifest_sha256=expected_manifest_sha256,
        comm=comm,
    )
    if set(packet["metadata"].get("basis_audits", {})) != set(_BRANCHES):
        raise ValueError("Task039 V4 packet lacks per-branch basis audits")
    reciprocal_pairing = packet["metadata"].get("reciprocal_pairing")
    if reciprocal_pairing is None or len(reciprocal_pairing["pairs"]) != int(
        reciprocal_pairing["count"]
    ):
        raise ValueError("Task039 V4 packet reciprocal authority count mismatch")
    read_seconds = packet["read_seconds_max_rank"]
    bundle = hydrate_task039_v4_selected_mode_packet(packet, comm=comm)
    diagnostics = bundle.packet_consumer_diagnostics
    diagnostics["consumer_kind"] = consumer_kind
    diagnostics["qep_calls"] = 0
    diagnostics["consumer_qep_required"] = False
    diagnostics["manifest_path"] = str(Path(manifest_path))
    diagnostics["manifest_sha256"] = packet["manifest_sha256"]
    diagnostics["identity_sha256"] = packet["identity_sha256"]
    diagnostics["read_seconds_max_rank"] = read_seconds
    del packet["positive"]
    del packet["negative"]
    del packet
    import gc

    gc.collect()
    diagnostics["packet_mmap_released"] = True
    diagnostics["packet_references_released"] = True
    return bundle
