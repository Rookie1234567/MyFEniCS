"""Hash-bound live same-trace nested-p DWR evidence for Task035d.

This module is an explicit research path.  It never changes the ordinary
solver configuration and never persists a dense local Schur matrix.  A coarse
endpoint stores only owned reduced-vector slices plus, for every owned cell,
``t_B``, ``S_B t_B``, and the cell-interior RHS correction.  An enriched
endpoint replays ``t_B`` through its retained local Schur classes, audits the
complete residual partition, and streams one actual DtN unit adjoint per
physical diffraction channel.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping, Sequence
from uuid import uuid4

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from .dtn_goal_adjoint import (
    DtnChannelGoal,
    dtn_channel_goal_value,
    evaluate_actual_dtn_unit_channel_adjoint_basis,
)
from .high_order_resource_audit import (
    partition_independent_linear_mesh_identity,
)
from .nested_p_dwr import (
    cell_schur_action_delta_residual,
    scaled_unit_adjoint_pairing,
    unit_channel_goal_scalar,
)
from ..solvers.hcurl_variable_p_assembly import (
    retained_variable_p_owned_cell_schur_actions,
)


_SNAPSHOT_SCHEMA = "task035d.variable-p-nested-coarse-snapshot.v1"
_SHARD_SCHEMA = "task035d.variable-p-nested-coarse-shard.v1"
_DWR_SCHEMA = "task035d.variable-p-nested-live-dwr.v1"
_SIGNIFICANT_AUTHORITY_SCHEMA = (
    "task035b.significant-channel-reference.v1"
)
_QUALIFIED_SCALAR = np.dtype("<c16")
_QUALIFIED_INTEGER = np.dtype("<i8")


@dataclass(frozen=True)
class SignificantChannelAuthority:
    """Frozen ordered physical channels and their unchanged-v0 tolerances."""

    path: Path
    file_sha256: str
    channels: tuple[dict[str, Any], ...]
    goals: tuple[DtnChannelGoal, ...]


@dataclass(frozen=True)
class CoarseCellSnapshot:
    """One owned coarse cell payload loaded without pickle."""

    canonical_leaf: int
    canonical_leaf_key: tuple[int, int, int, int, int]
    box: tuple[float, float, float, float, float, float]
    material_tag: int
    local_cell: int
    global_cell: int
    cell_info: int
    degree_signature: str
    class_key_sha256: str
    trace_rows: np.ndarray
    independent_rows: np.ndarray
    expansion_sha256: str
    trace_layout_sha256: str
    local_trace_values: np.ndarray
    local_condensed_action: np.ndarray
    interior_rhs_correction: np.ndarray


@dataclass(frozen=True)
class CoarseSnapshot:
    """Current-rank view plus replicated small global reduced vectors."""

    manifest: dict[str, Any]
    manifest_path: Path
    state_b: np.ndarray
    rhs_b: np.ndarray
    matrix_action_b_on_b: np.ndarray
    residual_b: np.ndarray
    auxiliary_values_b: np.ndarray
    incident_projections: np.ndarray
    coordinate_scales: np.ndarray
    cells: tuple[CoarseCellSnapshot, ...]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_array(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values)
    if np.issubdtype(array.dtype, np.complexfloating):
        return np.ascontiguousarray(array, dtype=_QUALIFIED_SCALAR)
    if np.issubdtype(array.dtype, np.integer):
        return np.ascontiguousarray(array, dtype=_QUALIFIED_INTEGER)
    if np.issubdtype(array.dtype, np.floating):
        return np.ascontiguousarray(array, dtype=np.dtype("<f8"))
    if np.issubdtype(array.dtype, np.bool_):
        return np.ascontiguousarray(array, dtype=np.dtype("u1"))
    return np.ascontiguousarray(array)


def _array_sha256(values: np.ndarray, *, namespace: str) -> str:
    array = _canonical_array(values)
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(b"\0")
    digest.update(
        np.asarray(array.shape, dtype=_QUALIFIED_INTEGER).tobytes()
    )
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return _jsonable(asdict(value))
    if isinstance(value, Mapping):
        return {
            str(key): _jsonable(item)
            for key, item in sorted(
                value.items(), key=lambda pair: str(pair[0])
            )
        }
    if isinstance(value, (tuple, list)):
        return [_jsonable(item) for item in value]
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _json_sha256(value: Any, *, namespace: str) -> str:
    encoded = json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    digest.update(encoded)
    return digest.hexdigest()


def _atomic_npz(path: Path, arrays: Mapping[str, np.ndarray]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite snapshot shard {path}")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            np.savez(stream, **arrays)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite evidence file {path}")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    encoded = (
        json.dumps(
            _jsonable(payload),
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    )
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _collective_publish_json(
    communicator: MPI.Intracomm,
    path: Path,
    payload: Mapping[str, Any],
) -> str:
    local_error = None
    if communicator.rank == 0:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_json(path, payload)
        except Exception as exc:
            local_error = f"{type(exc).__name__}: {exc}"
    errors = communicator.allgather(local_error)
    if any(error is not None for error in errors):
        raise RuntimeError(
            f"collective JSON publication failed for {path}: {errors}"
        )
    communicator.barrier()

    def verify_publication() -> str:
        if not path.is_file():
            raise RuntimeError(
                f"collective JSON publication lost {path}"
            )
        return _file_sha256(path)

    observed_sha = _collective_local_call(
        communicator,
        "collective JSON publication verification",
        verify_publication,
    )
    observed_shas = communicator.allgather(observed_sha)
    if len(set(observed_shas)) != 1:
        raise RuntimeError(
            f"collective JSON publication differs across ranks: {path}"
        )
    return str(observed_sha)


def _collective_local_call(
    communicator: MPI.Intracomm,
    phase: str,
    operation: Any,
) -> Any:
    """Turn a rank-local stage into an all-rank pass/fail decision."""

    result = None
    local_error = None
    try:
        result = operation()
    except Exception as exc:
        local_error = {
            "rank": int(communicator.rank),
            "phase": str(phase),
            "exception_type": type(exc).__name__,
            "message": str(exc),
        }
    errors = [
        error
        for error in communicator.allgather(local_error)
        if error is not None
    ]
    if errors:
        raise RuntimeError(
            f"{phase} failed collectively: {errors}"
        )
    return result


def _global_petsc_values(
    vector: PETSc.Vec,
    communicator: MPI.Intracomm,
) -> tuple[np.ndarray, tuple[tuple[int, int], ...]]:
    def local_packet() -> tuple[int, int, np.ndarray, int]:
        object_comm = vector.getComm().tompi4py()
        if MPI.Comm.Compare(communicator, object_comm) not in {
            MPI.IDENT,
            MPI.CONGRUENT,
        }:
            raise ValueError(
                "PETSc vector and snapshot use different communicators"
            )
        start, end = map(int, vector.getOwnershipRange())
        local = np.asarray(
            vector.getArray(readonly=True),
            dtype=np.complex128,
        ).copy()
        return start, end, local, int(vector.getSize())

    packet = _collective_local_call(
        communicator,
        "PETSc vector local extraction",
        local_packet,
    )
    if packet is None:
        raise RuntimeError("PETSc vector local extraction lost its packet")
    start, end, local, global_size = packet
    packets = communicator.allgather((start, end, local))
    global_sizes = communicator.allgather(global_size)
    if len(set(global_sizes)) != 1:
        raise RuntimeError("PETSc vector sizes differ across ranks")
    ordered = tuple(sorted(packets, key=lambda packet: int(packet[0])))
    cursor = 0
    ranges: list[tuple[int, int]] = []
    values: list[np.ndarray] = []
    for owned_start, owned_end, owned in ordered:
        owned_start = int(owned_start)
        owned_end = int(owned_end)
        if (
            owned_start != cursor
            or owned_end < owned_start
            or np.asarray(owned).shape
            != (owned_end - owned_start,)
        ):
            raise RuntimeError("PETSc vector ownership packets do not close")
        ranges.append((owned_start, owned_end))
        values.append(np.asarray(owned, dtype=np.complex128))
        cursor = owned_end
    if cursor != int(global_sizes[0]):
        raise RuntimeError("PETSc vector ownership misses global rows")
    result = np.ascontiguousarray(np.concatenate(values))
    if not np.all(np.isfinite(result)):
        raise ValueError("PETSc vector contains non-finite values")
    return result, tuple(ranges)


def _temporary_vector_from_global(
    template: PETSc.Vec,
    values: np.ndarray,
) -> PETSc.Vec:
    global_values = np.asarray(values, dtype=np.complex128)
    if global_values.shape != (template.getSize(),):
        raise ValueError("snapshot vector has the wrong global size")
    result = template.duplicate()
    start, end = map(int, result.getOwnershipRange())
    result.getArray()[:] = np.asarray(
        global_values[start:end],
        dtype=PETSc.ScalarType,
    )
    result.assemble()
    return result


def _coordinate_scales(goal_context: Mapping[str, Any]) -> np.ndarray:
    modes = tuple(goal_context["modes"])
    raw = goal_context.get("auxiliary_coordinate_scales")
    scales = (
        np.ones(len(modes), dtype=np.complex128)
        if raw is None
        else np.asarray(raw, dtype=np.complex128).copy()
    )
    if (
        scales.shape != (len(modes),)
        or not np.all(np.isfinite(scales))
        or np.any(np.abs(scales) <= 0.0)
    ):
        raise ValueError("invalid DtN auxiliary-coordinate scales")
    return scales


def _primal_residual_gate(
    *,
    full_active_residual: Mapping[str, Any],
    reduced_relative_residual: float,
) -> dict[str, Any]:
    """Require both reduced and full-explicit primal residuals."""

    raw_full = full_active_residual.get(
        "linear_system_relative_residual"
    )
    try:
        full_relative = float(raw_full)
        reduced_relative = float(reduced_relative_residual)
    except (TypeError, ValueError) as exc:
        raise ValueError("primal residual telemetry is not numeric") from exc
    finite = bool(
        np.isfinite(full_relative) and np.isfinite(reduced_relative)
    )
    nonnegative = bool(
        finite and full_relative >= 0.0 and reduced_relative >= 0.0
    )
    limit = 1.0e-9
    checks = {
        "finite": finite,
        "nonnegative": nonnegative,
        "reduced_trace_dtn_relative_residual_le_1e-9": (
            nonnegative and reduced_relative <= limit
        ),
        "full_explicit_true_relative_residual_le_1e-9": (
            nonnegative and full_relative <= limit
        ),
    }
    return {
        "schema_version": "task035d.primal-residual-gate.v1",
        "pass": all(checks.values()),
        "checks": checks,
        "limit": limit,
        "reduced_trace_dtn_relative_residual": reduced_relative,
        "full_explicit_true_relative_residual": full_relative,
        "full_explicit_residual_method": full_active_residual.get(
            "full_operator_residual_method"
        ),
    }


def _same_trace_port_operator_gate(
    enriched: Mapping[str, Any],
    coarse: Mapping[str, Any],
) -> dict[str, Any]:
    """Require independently hashed trace-only external operators/RHS."""

    invariant_fields = (
        "schema_version",
        "trace_functional_count",
        "auxiliary_interior_columns_allocated",
        "interior_degree_may_affect_port_operator",
        "external_operator_content_sha256",
        "external_rhs_content_sha256",
        "content_identity_is_partition_bound",
        "content_identity_requires_same_mpi_ownership",
    )

    def qualified_roundoff(audit: Mapping[str, Any]) -> bool:
        ratio = audit.get(
            "removed_active_interior_over_threshold_max"
        )
        threshold = audit.get("acceptance_threshold_max_abs")
        return bool(
            isinstance(audit.get("checks"), Mapping)
            and audit["checks"]
            and all(audit["checks"].values())
            and isinstance(ratio, (int, float))
            and np.isfinite(float(ratio))
            and 0.0 <= float(ratio) <= 1.0
            and isinstance(threshold, (int, float))
            and np.isfinite(float(threshold))
            and float(threshold) > 0.0
        )

    checks = {
        "enriched_pass": enriched.get("pass") is True,
        "coarse_pass": coarse.get("pass") is True,
        "enriched_scale_aware_trace_roundoff": (
            qualified_roundoff(enriched)
        ),
        "coarse_scale_aware_trace_roundoff": (
            qualified_roundoff(coarse)
        ),
        **{
            f"same_{field}": (
                enriched.get(field) == coarse.get(field)
            )
            for field in invariant_fields
        },
    }
    return {
        "schema_version": (
            "task035d.same-trace-port-operator-identity-gate.v1"
        ),
        "pass": all(checks.values()),
        "checks": checks,
        "compared_fields": list(invariant_fields),
        "external_delta_is_zero_only_if_pass": True,
    }


def load_significant_channel_authority(
    path: str | Path,
    *,
    expected_sha256: str,
) -> SignificantChannelAuthority:
    """Load the frozen ordered 12-channel authority fail closed."""

    authority_path = Path(path).resolve()
    observed_sha256 = _file_sha256(authority_path)
    if observed_sha256 != str(expected_sha256).lower():
        raise ValueError(
            "significant-channel authority SHA mismatch: "
            f"{observed_sha256} != {expected_sha256}"
        )
    payload = json.loads(authority_path.read_text(encoding="utf-8"))
    if (
        payload.get("schema_version") != _SIGNIFICANT_AUTHORITY_SCHEMA
        or payload.get("pass") is not True
        or payload.get("significant_channel_selection", {}).get(
            "channel_count"
        )
        != 12
    ):
        raise ValueError("significant-channel authority did not pass")
    rows = tuple(payload.get("channels", ()))
    if len(rows) != 12:
        raise ValueError("significant-channel authority is not 12-channel")
    channels: list[dict[str, Any]] = []
    goals: list[DtnChannelGoal] = []
    identities: set[tuple[str, int, int, str]] = set()
    for row in rows:
        channel = dict(row["channel"])
        key = (
            str(channel["side"]),
            int(channel["m"]),
            int(channel["n"]),
            str(channel["polarization"]),
        )
        if key in identities:
            raise ValueError("significant-channel authority has duplicates")
        identities.add(key)
        gate = dict(row["unchanged_v0_acceptance_gate"])
        power_tolerance = float(gate["power_absolute_tolerance"])
        amplitude_tolerance = float(
            gate["complex_amplitude_absolute_tolerance"]
        )
        if (
            not np.isfinite(power_tolerance)
            or power_tolerance <= 0.0
            or not np.isfinite(amplitude_tolerance)
            or amplitude_tolerance <= 0.0
        ):
            raise ValueError("significant-channel tolerances are invalid")
        channels.append(
            {
                "identity": {
                    "side": key[0],
                    "m": key[1],
                    "n": key[2],
                    "polarization": key[3],
                },
                "label": str(channel["label"]),
                "power_absolute_tolerance": power_tolerance,
                "complex_amplitude_absolute_tolerance": (
                    amplitude_tolerance
                ),
                "reference_center": dict(row["reference_center"]),
            }
        )
        goals.extend(
            DtnChannelGoal(*key, quantity)
            for quantity in (
                "power",
                "amplitude_real",
                "amplitude_imag",
            )
        )
    return SignificantChannelAuthority(
        path=authority_path,
        file_sha256=observed_sha256,
        channels=tuple(channels),
        goals=tuple(goals),
    )


def _mode_identity(goal_context: Mapping[str, Any]) -> dict[str, Any]:
    modes = tuple(goal_context["modes"])
    payload = [_jsonable(mode) for mode in modes]
    return {
        "mode_count": len(modes),
        "ordered_modes_sha256": _json_sha256(
            payload,
            namespace="task035d.ordered-dtn-modes.v1",
        ),
        "ordered_modes": payload,
    }


def _normalized_config_identity(config: Any) -> dict[str, Any]:
    payload = dict(config.as_jsonable())
    payload["stage4_variable_p_cell_degree_plan"] = None
    payload["stage4_local_h_refinement_plan"] = None
    return {
        "normalized_config_sha256": _json_sha256(
            payload,
            namespace="task035d.same-trace-physics-config.v1",
        ),
        "normalized_config": _jsonable(payload),
    }


def _canonical_leaf_payload(
    view: Any,
    canonical_leaf: int,
) -> tuple[
    tuple[int, int, int, int, int],
    tuple[float, float, float, float, float, float],
    int,
]:
    context = getattr(view.mesh_data, "local_h_context", None)
    if context is None:
        raise RuntimeError(
            "formal same-trace snapshot requires a local-h context"
        )
    leaf = context.forest.leaves[int(canonical_leaf)]
    key = leaf.key
    return (
        (
            int(key.root),
            int(key.level),
            int(key.i),
            int(key.j),
            int(key.k),
        ),
        tuple(float(value) for value in leaf.box),
        int(leaf.material_tag),
    )


def _constraint_cell_by_global(system: Any) -> dict[int, Any]:
    constraints = system.trace_constraints
    if constraints is None:
        raise RuntimeError(
            "formal same-trace snapshot requires physical trace constraints"
        )
    cells = {
        int(cell.global_cell): cell for cell in constraints.owned_cells
    }
    if len(cells) != len(system.cell_recovery):
        raise RuntimeError("trace constraints do not cover every owned cell")
    if not all(hasattr(cell, "canonical_leaf") for cell in cells.values()):
        raise RuntimeError(
            "formal same-trace snapshot requires canonical leaf identities"
        )
    return cells


def _trace_layout_record(
    *,
    view: Any,
    recovery: Any,
    constrained: Any,
) -> dict[str, Any]:
    cell = recovery.cell
    trace_rows = np.asarray(cell.trace_rows, dtype=np.int64)
    independent_rows = np.asarray(
        constrained.independent_rows,
        dtype=np.int64,
    )
    expansion = np.asarray(
        constrained.full_trace_from_independent,
        dtype=np.complex128,
    )
    if expansion.shape != (len(trace_rows), len(independent_rows)):
        raise RuntimeError("cell trace expansion shape is inconsistent")
    canonical_leaf = int(constrained.canonical_leaf)
    key, box, material_tag = _canonical_leaf_payload(
        view,
        canonical_leaf,
    )
    expansion_sha256 = _array_sha256(
        expansion,
        namespace="task035d.cell-trace-expansion.v1",
    )
    identity = {
        "canonical_leaf": canonical_leaf,
        "canonical_leaf_key": list(key),
        "box": list(box),
        "material_tag": material_tag,
        "local_cell": int(cell.local_cell),
        "global_cell": int(cell.global_cell),
        "cell_info": int(cell.cell_info),
        "trace_rows_sha256": _array_sha256(
            trace_rows,
            namespace="task035d.cell-raw-trace-rows.v1",
        ),
        "independent_rows_sha256": _array_sha256(
            independent_rows,
            namespace="task035d.cell-independent-trace-rows.v1",
        ),
        "expansion_shape": list(expansion.shape),
        "expansion_sha256": expansion_sha256,
    }
    return {
        **identity,
        "trace_layout_sha256": _json_sha256(
            identity,
            namespace="task035d.cell-trace-layout.v1",
        ),
        "trace_rows": trace_rows,
        "independent_rows": independent_rows,
        "expansion": expansion,
    }


def _same_trace_identity(
    view: Any,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    system = view.reduction.system
    comm = view.mesh_data.mesh.comm
    local_layout = None
    local_layout_error = None
    try:
        constraints_by_global = _constraint_cell_by_global(system)
        local_layout = tuple(
            _trace_layout_record(
                view=view,
                recovery=recovery,
                constrained=constraints_by_global[
                    int(recovery.cell.global_cell)
                ],
            )
            for recovery in system.cell_recovery
        )
    except Exception as exc:
        local_layout_error = {
            "rank": int(comm.rank),
            "exception_type": type(exc).__name__,
            "message": str(exc),
        }
    layout_errors = [
        error
        for error in comm.allgather(local_layout_error)
        if error is not None
    ]
    if layout_errors:
        raise RuntimeError(
            "same-trace rank-local layout failed collectively: "
            f"{layout_errors}"
        )
    if local_layout is None:
        raise RuntimeError("same-trace local layout is absent")
    local_public = [
        {
            key: value
            for key, value in row.items()
            if key not in {"trace_rows", "independent_rows", "expansion"}
        }
        for row in local_layout
    ]
    gathered = [
        row
        for packet in comm.allgather(local_public)
        for row in packet
    ]
    gathered.sort(key=lambda row: int(row["canonical_leaf"]))
    canonical_leaves = [int(row["canonical_leaf"]) for row in gathered]
    if canonical_leaves != list(range(len(gathered))):
        raise RuntimeError(
            "canonical leaves are not a unique contiguous global catalog"
        )
    config_identity = _normalized_config_identity(view.config)
    modes = _mode_identity(view.goal_context)
    incident = np.asarray(
        view.goal_context["incident_projections"],
        dtype=np.complex128,
    )
    scales = _coordinate_scales(view.goal_context)
    phase_identity = {
        "phase_x": _jsonable(complex(view.floquet_data.phase_x)),
        "phase_y": _jsonable(complex(view.floquet_data.phase_y)),
        "phase_corner": _jsonable(
            complex(view.floquet_data.phase_x)
            * complex(view.floquet_data.phase_y)
        ),
    }
    matrix_rows = int(view.A.getSize()[0])
    _, ownership_ranges = _global_petsc_values(view.x, comm)
    common = {
        "schema_version": "task035d.same-trace-live-identity.v1",
        "mesh_identity": partition_independent_linear_mesh_identity(
            view.mesh_data
        ),
        "config_identity": config_identity,
        "trace_layout_sha256": _json_sha256(
            gathered,
            namespace="task035d.global-cell-trace-layout.v1",
        ),
        "trace_layout_by_canonical_leaf": gathered,
        "trace_constraint_audit_sha256": _json_sha256(
            system.trace_constraints.audit,
            namespace="task035d.trace-constraint-audit.v1",
        ),
        "raw_active_trace_rows": int(
            system.entity_map.active_trace_rows
        ),
        "independent_trace_rows": int(system.active_trace_rows),
        "auxiliary_rows": int(system.appended_rows),
        "matrix_rows": matrix_rows,
        "matrix_columns": int(view.A.getSize()[1]),
        "matrix_vector_ownership_ranges": [
            list(values) for values in ownership_ranges
        ],
        "mpi_size": int(comm.size),
        "mode_identity": modes,
        "incident_projection_sha256": _array_sha256(
            incident,
            namespace="task035d.incident-projections.v1",
        ),
        "coordinate_scale_sha256": _array_sha256(
            scales,
            namespace="task035d.aux-coordinate-scales.v1",
        ),
        "coordinate_scale_source": (
            "explicit_goal_context"
            if "auxiliary_coordinate_scales" in view.goal_context
            else "implicit_default_ones_materialized"
        ),
        "normalization": str(view.goal_context["normalization"]),
        "floquet_phases": phase_identity,
    }
    if (
        common["independent_trace_rows"]
        + common["auxiliary_rows"]
        != matrix_rows
    ):
        raise RuntimeError("trace plus auxiliary row counts do not close")
    common["same_trace_identity_sha256"] = _json_sha256(
        common,
        namespace="task035d.same-trace-live-identity.v1",
    )
    return common, local_layout


def _candidate_identity(
    view: Any,
    *,
    candidate_id: str,
    expected_plan_sha256: str,
    source_sha: str,
) -> dict[str, Any]:
    context = getattr(view.mesh_data, "local_h_context", None)
    if context is None:
        raise RuntimeError("nested-p candidate lost its local-h context")
    actual_plan_sha256 = str(context.plan_file_sha256).lower()
    if actual_plan_sha256 != str(expected_plan_sha256).lower():
        raise ValueError(
            "nested-p candidate plan SHA mismatch: "
            f"{actual_plan_sha256} != {expected_plan_sha256}"
        )
    cell_degrees = np.asarray(
        view.reduction.system.entity_map.global_degrees[3],
        dtype=np.int64,
    )
    return {
        "candidate_id": str(candidate_id),
        "source_sha": str(source_sha),
        "plan_path": str(context.plan_path),
        "plan_file_sha256": actual_plan_sha256,
        "degree_plan_audit_sha256": _json_sha256(
            view.reduction.degree_plan.audit,
            namespace="task035d.candidate-degree-plan-audit.v1",
        ),
        "cell_interior_degree_sha256": _array_sha256(
            cell_degrees,
            namespace="task035d.global-cell-interior-degrees.v1",
        ),
        "cell_interior_degree_counts": {
            str(degree): int(np.count_nonzero(cell_degrees == degree))
            for degree in sorted(set(map(int, cell_degrees)))
        },
        "actual_full3d_equivalent_active_fe_dofs": int(
            view.reduction.build_audit[
                "actual_full3d_equivalent_active_fe_dofs"
            ]
        ),
    }


def _cell_rhs_corrections(
    view: Any,
) -> dict[int, np.ndarray]:
    comm = view.mesh_data.mesh.comm

    def local_preflight() -> Any:
        recovered = view.recovered
        if recovered.active_auxiliary_interior_action is not None:
            raise RuntimeError(
                "nested-p snapshot does not permit "
                "auxiliary-to-interior action"
            )
        if recovered.active_full_rhs is None:
            raise RuntimeError(
                "nested-p snapshot lost its active full RHS"
            )
        return recovered.active_full_rhs

    active_rhs = _collective_local_call(
        comm,
        "cell interior RHS preflight",
        local_preflight,
    )
    if active_rhs is None:
        raise RuntimeError("cell interior active RHS is absent")
    values, _ = _global_petsc_values(
        active_rhs,
        comm,
    )
    system = view.reduction.system
    def local_corrections() -> dict[int, np.ndarray]:
        corrections: dict[int, np.ndarray] = {}
        for recovery in system.cell_recovery:
            interior = values[recovery.cell.interior_rows]
            correction = np.ascontiguousarray(
                system.trace_from_interior_rhs_by_class[
                    recovery.class_key
                ]
                @ interior
            )
            if not np.all(np.isfinite(correction)):
                raise RuntimeError(
                    "cell interior RHS correction contains non-finite "
                    "values"
                )
            corrections[int(recovery.cell.global_cell)] = correction
        return corrections

    corrections = _collective_local_call(
        comm,
        "cell interior RHS correction",
        local_corrections,
    )
    if corrections is None:
        raise RuntimeError("cell interior RHS corrections are absent")
    return corrections


def _flatten_cell_payloads(
    *,
    layouts: Sequence[dict[str, Any]],
    actions: Sequence[Any],
    rhs_corrections: Mapping[int, np.ndarray],
    recoveries: Sequence[Any],
) -> tuple[dict[str, np.ndarray], list[dict[str, Any]]]:
    layout_by_global = {
        int(layout["global_cell"]): layout for layout in layouts
    }
    action_by_global = {
        int(action.global_cell): action for action in actions
    }
    recovery_by_global = {
        int(recovery.cell.global_cell): recovery
        for recovery in recoveries
    }
    if not (
        set(layout_by_global)
        == set(action_by_global)
        == set(rhs_corrections)
        == set(recovery_by_global)
    ):
        raise RuntimeError("nested-p cell payload identities do not align")
    ordered = sorted(
        layout_by_global,
        key=lambda global_cell: int(
            layout_by_global[global_cell]["canonical_leaf"]
        ),
    )
    trace_offsets = [0]
    independent_offsets = [0]
    trace_rows: list[np.ndarray] = []
    independent_rows: list[np.ndarray] = []
    traces: list[np.ndarray] = []
    actions_flat: list[np.ndarray] = []
    rhs_flat: list[np.ndarray] = []
    metadata: list[dict[str, Any]] = []
    class_hashes: list[str] = []
    for global_cell in ordered:
        layout = layout_by_global[global_cell]
        action = action_by_global[global_cell]
        recovery = recovery_by_global[global_cell]
        trace = np.asarray(
            action.local_trace_values,
            dtype=np.complex128,
        )
        condensed_action = np.asarray(
            action.local_condensed_action,
            dtype=np.complex128,
        )
        correction = np.asarray(
            rhs_corrections[global_cell],
            dtype=np.complex128,
        )
        raw_rows = np.asarray(layout["trace_rows"], dtype=np.int64)
        independent = np.asarray(
            layout["independent_rows"],
            dtype=np.int64,
        )
        if any(
            vector.shape != (len(raw_rows),)
            for vector in (trace, condensed_action, correction)
        ):
            raise RuntimeError("nested-p local action payload has wrong shape")
        trace_rows.append(raw_rows)
        independent_rows.append(independent)
        traces.append(trace)
        actions_flat.append(condensed_action)
        rhs_flat.append(correction)
        trace_offsets.append(trace_offsets[-1] + len(raw_rows))
        independent_offsets.append(
            independent_offsets[-1] + len(independent)
        )
        class_sha = _json_sha256(
            recovery.class_key,
            namespace="task035d.local-operator-class.v1",
        )
        class_hashes.append(class_sha)
        metadata.append(
            {
                key: layout[key]
                for key in (
                    "canonical_leaf",
                    "canonical_leaf_key",
                    "box",
                    "material_tag",
                    "local_cell",
                    "global_cell",
                    "cell_info",
                    "expansion_sha256",
                    "trace_layout_sha256",
                )
            }
            | {
                "degree_signature": str(
                    recovery.cell.degree_map.signature
                ),
                "class_key_sha256": class_sha,
            }
        )
    arrays = {
        "canonical_leaves": np.asarray(
            [row["canonical_leaf"] for row in metadata],
            dtype=np.int64,
        ),
        "canonical_leaf_keys": np.asarray(
            [row["canonical_leaf_key"] for row in metadata],
            dtype=np.int64,
        ),
        "boxes": np.asarray(
            [row["box"] for row in metadata],
            dtype=np.float64,
        ),
        "material_tags": np.asarray(
            [row["material_tag"] for row in metadata],
            dtype=np.int64,
        ),
        "local_cells": np.asarray(
            [row["local_cell"] for row in metadata],
            dtype=np.int64,
        ),
        "global_cells": np.asarray(
            [row["global_cell"] for row in metadata],
            dtype=np.int64,
        ),
        "cell_info": np.asarray(
            [row["cell_info"] for row in metadata],
            dtype=np.int64,
        ),
        "degree_signatures": np.asarray(
            [row["degree_signature"] for row in metadata],
            dtype=np.str_,
        ),
        "class_key_sha256": np.asarray(class_hashes, dtype="U64"),
        "expansion_sha256": np.asarray(
            [row["expansion_sha256"] for row in metadata],
            dtype="U64",
        ),
        "trace_layout_sha256": np.asarray(
            [row["trace_layout_sha256"] for row in metadata],
            dtype="U64",
        ),
        "trace_offsets": np.asarray(trace_offsets, dtype=np.int64),
        "independent_offsets": np.asarray(
            independent_offsets,
            dtype=np.int64,
        ),
        "trace_rows": np.concatenate(trace_rows).astype(
            np.int64,
            copy=False,
        ),
        "independent_rows": np.concatenate(independent_rows).astype(
            np.int64,
            copy=False,
        ),
        "local_trace_values": np.concatenate(traces).astype(
            np.complex128,
            copy=False,
        ),
        "local_condensed_actions": np.concatenate(actions_flat).astype(
            np.complex128,
            copy=False,
        ),
        "interior_rhs_corrections": np.concatenate(rhs_flat).astype(
            np.complex128,
            copy=False,
        ),
    }
    return arrays, metadata


def write_variable_p_nested_coarse_snapshot(
    view: Any,
    *,
    artifact_directory: str | Path,
    candidate_id: str,
    expected_plan_sha256: str,
    source_sha: str,
    significant_channel_authority_path: str | Path,
    significant_channel_authority_sha256: str,
) -> dict[str, Any]:
    """Publish one immutable MPI-sharded coarse-B live snapshot."""

    comm = view.mesh_data.mesh.comm
    authority = _collective_local_call(
        comm,
        "coarse significant-channel authority load",
        lambda: load_significant_channel_authority(
            significant_channel_authority_path,
            expected_sha256=significant_channel_authority_sha256,
        ),
    )
    if authority is None:
        raise RuntimeError(
            "coarse significant-channel authority is absent"
        )
    common_identity, layouts = _same_trace_identity(view)
    candidate = _collective_local_call(
        comm,
        "coarse candidate identity",
        lambda: _candidate_identity(
            view,
            candidate_id=candidate_id,
            expected_plan_sha256=expected_plan_sha256,
            source_sha=source_sha,
        ),
    )
    if candidate is None:
        raise RuntimeError("coarse candidate identity is absent")
    port_audit_passes = comm.allgather(
        view.port_operator_audit.get("pass") is True
    )
    if not all(port_audit_passes):
        raise RuntimeError(
            "coarse B lacks the trace-only DtN/port operator Gate"
        )
    action_payload = _collective_local_call(
        comm,
        "coarse retained Schur action",
        lambda: retained_variable_p_owned_cell_schur_actions(
            view.reduction.system,
            reduced_trace_values=view.x,
        ),
    )
    if action_payload is None:
        raise RuntimeError("coarse retained Schur action is absent")
    actions, action_audit = action_payload
    rhs_corrections = _cell_rhs_corrections(view)
    cell_payload = _collective_local_call(
        comm,
        "coarse cell snapshot flatten",
        lambda: _flatten_cell_payloads(
            layouts=layouts,
            actions=actions,
            rhs_corrections=rhs_corrections,
            recoveries=view.reduction.system.cell_recovery,
        ),
    )
    if cell_payload is None:
        raise RuntimeError("coarse cell snapshot payload is absent")
    cell_arrays, cell_metadata = cell_payload

    matrix_action = view.x.duplicate()
    try:
        view.A.mult(view.x, matrix_action)
        state, ownership_ranges = _global_petsc_values(view.x, comm)
        rhs, rhs_ranges = _global_petsc_values(view.b, comm)
        action, action_ranges = _global_petsc_values(
            matrix_action,
            comm,
        )
    finally:
        matrix_action.destroy()
    if ownership_ranges != rhs_ranges or ownership_ranges != action_ranges:
        raise RuntimeError("coarse reduced vectors have different ownership")
    residual = np.ascontiguousarray(rhs - action)
    reduced_relative_residual = float(
        np.linalg.norm(residual)
        / max(np.linalg.norm(rhs), np.finfo(float).tiny)
    )
    primal_residual_gate = _primal_residual_gate(
        full_active_residual=view.full_active_residual,
        reduced_relative_residual=reduced_relative_residual,
    )
    if not primal_residual_gate["pass"]:
        raise RuntimeError(
            "coarse B failed the primal residual Gate: "
            f"{primal_residual_gate}"
        )
    auxiliary = np.asarray(
        view.goal_context["auxiliary_values"],
        dtype=np.complex128,
    ).copy()
    incident = np.asarray(
        view.goal_context["incident_projections"],
        dtype=np.complex128,
    ).copy()
    scales = _coordinate_scales(view.goal_context)
    n_fe = int(view.goal_context["num_fem_dofs_after_mpc"])
    if not np.allclose(
        auxiliary,
        state[n_fe:] / scales,
        rtol=2.0e-12,
        atol=2.0e-13,
    ):
        raise RuntimeError(
            "coarse goal-context auxiliaries differ from solver coordinates"
        )

    output = Path(artifact_directory).resolve()
    local_prepare_error = None
    if comm.rank == 0:
        try:
            output.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            local_prepare_error = f"{type(exc).__name__}: {exc}"
    prepare_errors = comm.allgather(local_prepare_error)
    if any(error is not None for error in prepare_errors):
        raise RuntimeError(
            "coarse snapshot directory preparation failed: "
            f"{prepare_errors}"
        )
    comm.barrier()
    shard_path = output / f"rank{comm.rank:04d}.npz"
    start, end = ownership_ranges[comm.rank]
    shard_arrays = {
        "schema_version": np.asarray([_SHARD_SCHEMA], dtype=np.str_),
        "rank": np.asarray([comm.rank], dtype=np.int64),
        "mpi_size": np.asarray([comm.size], dtype=np.int64),
        "ownership_range": np.asarray([start, end], dtype=np.int64),
        "state_b_owned": state[start:end],
        "rhs_b_owned": rhs[start:end],
        "matrix_action_b_on_b_owned": action[start:end],
        "residual_b_owned": residual[start:end],
        "auxiliary_values_b": auxiliary,
        "incident_projections": incident,
        "coordinate_scales": scales,
        **cell_arrays,
    }
    local_shard_error = None
    shard_metadata = None
    try:
        _atomic_npz(shard_path, shard_arrays)
        shard_metadata = {
            "rank": int(comm.rank),
            "path": shard_path.name,
            "sha256": _file_sha256(shard_path),
            "bytes": int(shard_path.stat().st_size),
            "ownership_range": [start, end],
            "owned_value_count": end - start,
            "canonical_leaves": [
                int(row["canonical_leaf"]) for row in cell_metadata
            ],
            "owned_cell_count": len(cell_metadata),
        }
    except Exception as exc:
        local_shard_error = f"{type(exc).__name__}: {exc}"
    shard_errors = comm.allgather(local_shard_error)
    if any(error is not None for error in shard_errors):
        raise RuntimeError(
            "coarse snapshot shard publication failed: "
            f"{shard_errors}"
        )
    if shard_metadata is None:
        raise RuntimeError("coarse snapshot shard metadata is absent")
    shards = list(comm.allgather(shard_metadata))
    shards.sort(key=lambda row: int(row["rank"]))
    if [int(row["rank"]) for row in shards] != list(range(comm.size)):
        raise RuntimeError("coarse snapshot shards do not cover MPI ranks")

    manifest_path = output / "manifest.json"
    manifest = {
        "schema_version": _SNAPSHOT_SCHEMA,
        "status": "coarse_nested_p_snapshot_pass",
        "pass": True,
        "canonical": False,
        "production_qualified": False,
        "ordinary_default_changed": False,
        "role": "coarse_B",
        "candidate": candidate,
        "same_trace_identity": common_identity,
        "significant_channel_authority": {
            "path": str(authority.path),
            "sha256": authority.file_sha256,
            "ordered_channel_count": len(authority.channels),
            "ordered_channels": [
                channel["identity"] for channel in authority.channels
            ],
        },
        "scalar_type": str(PETSc.ScalarType),
        "integer_type": str(PETSc.IntType),
        "full_active_residual": _jsonable(view.full_active_residual),
        "primal_residual_gate": primal_residual_gate,
        "primal_solver_telemetry": _jsonable(
            view.primal_solver_telemetry
        ),
        "port_metrics": _jsonable(view.port_metrics),
        "port_operator_audit": _jsonable(view.port_operator_audit),
        "vector_identity": {
            "global_size": len(state),
            "state_b_sha256": _array_sha256(
                state,
                namespace="task035d.coarse-state-b.v1",
            ),
            "rhs_b_sha256": _array_sha256(
                rhs,
                namespace="task035d.coarse-rhs-b.v1",
            ),
            "matrix_action_b_on_b_sha256": _array_sha256(
                action,
                namespace="task035d.coarse-matrix-action-b.v1",
            ),
            "residual_b_sha256": _array_sha256(
                residual,
                namespace="task035d.coarse-residual-b-minus-kx.v1",
            ),
            "residual_sign": "b_B-K_B*x_B",
            "residual_l2_norm": float(np.linalg.norm(residual)),
            "rhs_l2_norm": float(np.linalg.norm(rhs)),
            "relative_residual": float(
                reduced_relative_residual
            ),
            "ownership_ranges": [
                list(values) for values in ownership_ranges
            ],
        },
        "goal_endpoint": {
            "auxiliary_values_sha256": _array_sha256(
                auxiliary,
                namespace="task035d.coarse-physical-auxiliary.v1",
            ),
            "incident_projections_sha256": _array_sha256(
                incident,
                namespace="task035d.incident-projections.v1",
            ),
            "coordinate_scales_sha256": _array_sha256(
                scales,
                namespace="task035d.aux-coordinate-scales.v1",
            ),
            "auxiliary_values_match_solver_coordinates": True,
        },
        "cell_action_audit": _jsonable(action_audit),
        "cell_snapshot": {
            "global_cell_count": int(
                comm.allreduce(len(cell_metadata), op=MPI.SUM)
            ),
            "dense_schur_persisted": False,
            "stored_payloads": [
                "local_trace_t_B",
                "local_S_B_t_B",
                "local_interior_rhs_correction_B",
            ],
            "interior_rhs_correction_sign": (
                "-A_ti*A_ii^-1*f_i"
            ),
            "auxiliary_to_cell_interior_action_absent": True,
            "canonical_leaf_pairing": True,
        },
        "shards": shards,
        "publication": (
            "atomic_rank_shards_then_rank0_manifest; npz_allow_pickle_false"
        ),
    }
    manifest_sha = _collective_publish_json(
        comm,
        manifest_path,
        manifest,
    )
    return {
        "schema_version": _SNAPSHOT_SCHEMA,
        "status": "coarse_nested_p_snapshot_published",
        "pass": True,
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha,
        "same_trace_identity_sha256": common_identity[
            "same_trace_identity_sha256"
        ],
        "candidate": candidate,
        "shard_count": len(shards),
        "ordinary_default_changed": False,
    }


def _load_rank_shard(
    path: Path,
    *,
    expected_sha256: str,
    rank: int,
    mpi_size: int,
) -> tuple[dict[str, np.ndarray], tuple[CoarseCellSnapshot, ...]]:
    if _file_sha256(path) != str(expected_sha256).lower():
        raise ValueError(f"coarse snapshot shard SHA mismatch: {path}")
    with np.load(path, allow_pickle=False) as archive:
        arrays = {
            name: np.asarray(archive[name]).copy()
            for name in archive.files
        }
    if (
        str(arrays["schema_version"][0]) != _SHARD_SCHEMA
        or int(arrays["rank"][0]) != int(rank)
        or int(arrays["mpi_size"][0]) != int(mpi_size)
    ):
        raise ValueError("coarse snapshot shard identity is invalid")
    count = len(arrays["canonical_leaves"])
    one_per_cell = (
        "canonical_leaf_keys",
        "boxes",
        "material_tags",
        "local_cells",
        "global_cells",
        "cell_info",
        "degree_signatures",
        "class_key_sha256",
        "expansion_sha256",
        "trace_layout_sha256",
    )
    if any(len(arrays[name]) != count for name in one_per_cell):
        raise ValueError("coarse snapshot cell metadata is misaligned")
    trace_offsets = np.asarray(arrays["trace_offsets"], dtype=np.int64)
    independent_offsets = np.asarray(
        arrays["independent_offsets"],
        dtype=np.int64,
    )
    if (
        trace_offsets.shape != (count + 1,)
        or independent_offsets.shape != (count + 1,)
        or trace_offsets[0] != 0
        or independent_offsets[0] != 0
        or np.any(np.diff(trace_offsets) < 0)
        or np.any(np.diff(independent_offsets) < 0)
    ):
        raise ValueError("coarse snapshot cell offsets are invalid")
    if (
        trace_offsets[-1] != len(arrays["trace_rows"])
        or trace_offsets[-1] != len(arrays["local_trace_values"])
        or trace_offsets[-1]
        != len(arrays["local_condensed_actions"])
        or trace_offsets[-1]
        != len(arrays["interior_rhs_corrections"])
        or independent_offsets[-1] != len(arrays["independent_rows"])
    ):
        raise ValueError("coarse snapshot flattened payloads do not close")
    cells: list[CoarseCellSnapshot] = []
    for index in range(count):
        trace_start, trace_end = map(
            int,
            trace_offsets[index : index + 2],
        )
        independent_start, independent_end = map(
            int,
            independent_offsets[index : index + 2],
        )
        cell = CoarseCellSnapshot(
            canonical_leaf=int(arrays["canonical_leaves"][index]),
            canonical_leaf_key=tuple(
                map(int, arrays["canonical_leaf_keys"][index])
            ),
            box=tuple(map(float, arrays["boxes"][index])),
            material_tag=int(arrays["material_tags"][index]),
            local_cell=int(arrays["local_cells"][index]),
            global_cell=int(arrays["global_cells"][index]),
            cell_info=int(arrays["cell_info"][index]),
            degree_signature=str(arrays["degree_signatures"][index]),
            class_key_sha256=str(arrays["class_key_sha256"][index]),
            trace_rows=np.asarray(
                arrays["trace_rows"][trace_start:trace_end],
                dtype=np.int64,
            ),
            independent_rows=np.asarray(
                arrays["independent_rows"][
                    independent_start:independent_end
                ],
                dtype=np.int64,
            ),
            expansion_sha256=str(
                arrays["expansion_sha256"][index]
            ),
            trace_layout_sha256=str(
                arrays["trace_layout_sha256"][index]
            ),
            local_trace_values=np.asarray(
                arrays["local_trace_values"][trace_start:trace_end],
                dtype=np.complex128,
            ),
            local_condensed_action=np.asarray(
                arrays["local_condensed_actions"][
                    trace_start:trace_end
                ],
                dtype=np.complex128,
            ),
            interior_rhs_correction=np.asarray(
                arrays["interior_rhs_corrections"][
                    trace_start:trace_end
                ],
                dtype=np.complex128,
            ),
        )
        if len(cell.canonical_leaf_key) != 5 or len(cell.box) != 6:
            raise ValueError("coarse canonical leaf payload is invalid")
        cells.append(cell)
    canonical = [cell.canonical_leaf for cell in cells]
    if canonical != sorted(canonical) or len(set(canonical)) != len(canonical):
        raise ValueError("coarse rank shard canonical leaves are invalid")
    return arrays, tuple(cells)


def load_variable_p_nested_coarse_snapshot(
    manifest_path: str | Path,
    *,
    communicator: MPI.Intracomm,
    expected_manifest_sha256: str,
    expected_source_sha: str,
    expected_significant_channel_authority_sha256: str,
) -> CoarseSnapshot:
    """Load and independently re-hash one current-rank coarse snapshot."""

    def load_local_manifest_header() -> tuple[
        Path,
        dict[str, Any],
        dict[str, Any],
    ]:
        path = Path(manifest_path).resolve()
        observed_manifest_sha = _file_sha256(path)
        if observed_manifest_sha != str(
            expected_manifest_sha256
        ).lower():
            raise ValueError(
                "coarse snapshot manifest SHA mismatch: "
                f"{observed_manifest_sha} != {expected_manifest_sha256}"
            )
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if (
            manifest.get("schema_version") != _SNAPSHOT_SCHEMA
            or manifest.get("pass") is not True
            or manifest.get("role") != "coarse_B"
            or int(
                manifest["same_trace_identity"]["mpi_size"]
            )
            != communicator.size
            or manifest["candidate"]["source_sha"]
            != str(expected_source_sha)
            or manifest["significant_channel_authority"]["sha256"]
            != str(
                expected_significant_channel_authority_sha256
            ).lower()
        ):
            raise ValueError(
                "coarse snapshot manifest identity is invalid"
            )
        shards = tuple(manifest["shards"])
        if len(shards) != communicator.size:
            raise ValueError(
                "coarse snapshot shard count differs from MPI size"
            )
        shard_metadata = next(
            (
                shard
                for shard in shards
                if int(shard["rank"]) == communicator.rank
            ),
            None,
        )
        if not isinstance(shard_metadata, dict):
            raise ValueError(
                "coarse snapshot lacks the current-rank shard"
            )
        return path, manifest, shard_metadata

    header = _collective_local_call(
        communicator,
        "coarse snapshot manifest header load",
        load_local_manifest_header,
    )
    if header is None:
        raise RuntimeError(
            "coarse snapshot manifest header is absent"
        )
    path, manifest, shard_metadata = header
    local_payload = None
    local_error = None
    try:
        arrays, cells = _load_rank_shard(
            path.parent / str(shard_metadata["path"]),
            expected_sha256=str(shard_metadata["sha256"]),
            rank=communicator.rank,
            mpi_size=communicator.size,
        )
        ownership = tuple(map(int, arrays["ownership_range"]))
        if list(ownership) != list(shard_metadata["ownership_range"]):
            raise ValueError(
                "coarse shard ownership differs from its manifest"
            )
        owned_packet = (
            ownership[0],
            ownership[1],
            np.asarray(arrays["state_b_owned"], dtype=np.complex128),
            np.asarray(arrays["rhs_b_owned"], dtype=np.complex128),
            np.asarray(
                arrays["matrix_action_b_on_b_owned"],
                dtype=np.complex128,
            ),
            np.asarray(
                arrays["residual_b_owned"],
                dtype=np.complex128,
            ),
        )
        local_payload = (arrays, cells, owned_packet)
    except Exception as exc:
        local_error = {
            "rank": int(communicator.rank),
            "exception_type": type(exc).__name__,
            "message": str(exc),
        }
    errors = [
        error
        for error in communicator.allgather(local_error)
        if error is not None
    ]
    if errors:
        raise RuntimeError(
            "coarse rank-shard load failed collectively: "
            f"{errors}"
        )
    if local_payload is None:
        raise RuntimeError("coarse rank-shard load lost its payload")
    arrays, cells, owned_packet = local_payload
    packets = communicator.allgather(owned_packet)
    packets.sort(key=lambda packet: int(packet[0]))
    cursor = 0
    assembled: list[list[np.ndarray]] = [[], [], [], []]
    for packet in packets:
        start, end = map(int, packet[:2])
        if start != cursor or end < start:
            raise ValueError("coarse vector ownership is not contiguous")
        for slot, values in enumerate(packet[2:]):
            vector = np.asarray(values, dtype=np.complex128)
            if vector.shape != (end - start,):
                raise ValueError("coarse owned vector has the wrong length")
            assembled[slot].append(vector)
        cursor = end
    vectors = [
        np.ascontiguousarray(np.concatenate(parts))
        for parts in assembled
    ]
    state, rhs, action, residual = vectors
    expected_vector = manifest["vector_identity"]
    vector_hashes = (
        (
            state,
            "state_b_sha256",
            "task035d.coarse-state-b.v1",
        ),
        (
            rhs,
            "rhs_b_sha256",
            "task035d.coarse-rhs-b.v1",
        ),
        (
            action,
            "matrix_action_b_on_b_sha256",
            "task035d.coarse-matrix-action-b.v1",
        ),
        (
            residual,
            "residual_b_sha256",
            "task035d.coarse-residual-b-minus-kx.v1",
        ),
    )
    for values, key, namespace in vector_hashes:
        if _array_sha256(values, namespace=namespace) != expected_vector[key]:
            raise ValueError(f"coarse snapshot vector hash mismatch: {key}")
    if not np.allclose(
        residual,
        rhs - action,
        rtol=2.0e-13,
        atol=2.0e-13,
    ):
        raise ValueError("coarse snapshot residual is not b_B-K_B*x_B")
    auxiliary_packets = communicator.allgather(
        np.asarray(arrays["auxiliary_values_b"], dtype=np.complex128)
    )
    incident_packets = communicator.allgather(
        np.asarray(arrays["incident_projections"], dtype=np.complex128)
    )
    scale_packets = communicator.allgather(
        np.asarray(arrays["coordinate_scales"], dtype=np.complex128)
    )
    for name, values in (
        ("auxiliary", auxiliary_packets),
        ("incident", incident_packets),
        ("coordinate scale", scale_packets),
    ):
        reference = values[0]
        if any(not np.array_equal(reference, packet) for packet in values[1:]):
            raise ValueError(
                f"coarse {name} payload differs across rank shards"
            )
    return CoarseSnapshot(
        manifest=manifest,
        manifest_path=path,
        state_b=state,
        rhs_b=rhs,
        matrix_action_b_on_b=action,
        residual_b=residual,
        auxiliary_values_b=auxiliary_packets[0],
        incident_projections=incident_packets[0],
        coordinate_scales=scale_packets[0],
        cells=cells,
    )


def _channel_label(identity: Mapping[str, Any]) -> str:
    prefix = "R" if str(identity["side"]) == "top" else "T"
    return (
        f"{prefix}({int(identity['m'])},{int(identity['n'])})_"
        f"{str(identity['polarization'])}"
    )


def _complex_pair(value: complex) -> list[float]:
    number = complex(value)
    return [float(number.real), float(number.imag)]


def _current_layout_by_leaf(
    layouts: Sequence[dict[str, Any]],
) -> dict[int, dict[str, Any]]:
    result = {
        int(layout["canonical_leaf"]): layout for layout in layouts
    }
    if len(result) != len(layouts):
        raise RuntimeError("current trace layout repeats canonical leaves")
    return result


def _validate_and_pair_cells_local(
    *,
    view: Any,
    snapshot: CoarseSnapshot,
    layouts: Sequence[dict[str, Any]],
    actions_a: Sequence[Any],
    rhs_corrections_a: Mapping[int, np.ndarray],
) -> tuple[
    list[dict[str, Any]],
    np.ndarray,
    dict[int, dict[str, Any]],
]:
    system = view.reduction.system
    size = int(view.A.getSize()[0])
    current_layout = _current_layout_by_leaf(layouts)
    coarse_by_leaf = {
        cell.canonical_leaf: cell for cell in snapshot.cells
    }
    if set(current_layout) != set(coarse_by_leaf):
        raise ValueError(
            "current-rank canonical leaf ownership differs from coarse B"
        )
    constraint_by_global = _constraint_cell_by_global(system)
    current_leaf_by_global = {
        int(cell.global_cell): int(cell.canonical_leaf)
        for cell in constraint_by_global.values()
    }
    action_by_leaf = {
        current_leaf_by_global[int(action.global_cell)]: action
        for action in actions_a
    }
    recovery_by_global = {
        int(recovery.cell.global_cell): recovery
        for recovery in system.cell_recovery
    }
    local_cell_sum = np.zeros(size, dtype=np.complex128)
    local_records: list[dict[str, Any]] = []
    live_pairing: dict[int, dict[str, Any]] = {}
    for canonical_leaf in sorted(current_layout):
        layout = current_layout[canonical_leaf]
        coarse = coarse_by_leaf[canonical_leaf]
        current_global_cell = int(layout["global_cell"])
        action_a = action_by_leaf[canonical_leaf]
        recovery = recovery_by_global[current_global_cell]
        expansion = np.asarray(
            layout["expansion"],
            dtype=np.complex128,
        )
        independent_rows = np.asarray(
            layout["independent_rows"],
            dtype=np.int64,
        )
        trace_rows = np.asarray(layout["trace_rows"], dtype=np.int64)
        replayed_trace_from_state = np.asarray(
            expansion @ snapshot.state_b[independent_rows],
            dtype=np.complex128,
        )
        degree_signature_a = str(recovery.cell.degree_map.signature)
        interior_degree_changed = (
            degree_signature_a != coarse.degree_signature
        )
        class_key_sha256_a = _json_sha256(
            recovery.class_key,
            namespace="task035d.local-operator-class.v1",
        )
        identity_checks = {
            "canonical_leaf_key": (
                tuple(layout["canonical_leaf_key"])
                == coarse.canonical_leaf_key
            ),
            "box": tuple(layout["box"]) == coarse.box,
            "material_tag": (
                int(layout["material_tag"]) == coarse.material_tag
            ),
            "cell_info": int(layout["cell_info"]) == coarse.cell_info,
            "trace_rows": np.array_equal(
                trace_rows,
                coarse.trace_rows,
            ),
            "independent_rows": np.array_equal(
                independent_rows,
                coarse.independent_rows,
            ),
            "expansion_sha256": (
                str(layout["expansion_sha256"])
                == coarse.expansion_sha256
            ),
            "trace_layout_sha256": (
                str(layout["trace_layout_sha256"])
                == coarse.trace_layout_sha256
            ),
            "coarse_trace_from_state": np.allclose(
                coarse.local_trace_values,
                replayed_trace_from_state,
                rtol=2.0e-13,
                atol=2.0e-13,
            ),
            "enriched_action_trace_from_state": np.allclose(
                action_a.local_trace_values,
                replayed_trace_from_state,
                rtol=2.0e-13,
                atol=2.0e-13,
            ),
            "unchanged_operator_class": (
                interior_degree_changed
                or class_key_sha256_a == coarse.class_key_sha256
            ),
        }
        if not all(identity_checks.values()):
            failures = [
                name
                for name, passed in identity_checks.items()
                if not passed
            ]
            raise ValueError(
                "same-trace cell identity mismatch for canonical leaf "
                f"{canonical_leaf}: {failures}"
            )
        result = cell_schur_action_delta_residual(
            global_size=size,
            rows=independent_rows,
            expansion=expansion,
            action_a_on_trace_b=np.asarray(
                action_a.local_condensed_action,
                dtype=np.complex128,
            ),
            action_b_on_trace_b=coarse.local_condensed_action,
            interior_rhs_correction_a=rhs_corrections_a[
                current_global_cell
            ],
            interior_rhs_correction_b=(
                coarse.interior_rhs_correction
            ),
        )
        local_cell_sum += result.global_residual
        unchanged_scale = max(
            float(np.linalg.norm(action_a.local_condensed_action)),
            float(np.linalg.norm(coarse.local_condensed_action)),
            float(
                np.linalg.norm(
                    rhs_corrections_a[current_global_cell]
                )
            ),
            float(np.linalg.norm(coarse.interior_rhs_correction)),
            1.0e-30,
        )
        unchanged_limit = 5.0e-12 + 5.0e-11 * unchanged_scale
        unchanged_zero_delta_pass = bool(
            interior_degree_changed
            or np.linalg.norm(result.local_residual)
            <= unchanged_limit
        )
        if not unchanged_zero_delta_pass:
            raise ValueError(
                "unchanged nested-p cell has a nonzero local residual "
                f"for canonical leaf {canonical_leaf}"
            )
        record = {
            "canonical_leaf": canonical_leaf,
            "canonical_leaf_key": list(coarse.canonical_leaf_key),
            "box": list(coarse.box),
            "material_tag": coarse.material_tag,
            "global_cell_a": current_global_cell,
            "global_cell_b": coarse.global_cell,
            "cell_info": coarse.cell_info,
            "degree_signature_a": degree_signature_a,
            "degree_signature_b": coarse.degree_signature,
            "interior_degree_changed": interior_degree_changed,
            "class_key_sha256_a": class_key_sha256_a,
            "class_key_sha256_b": coarse.class_key_sha256,
            "trace_layout_sha256": coarse.trace_layout_sha256,
            "local_trace_l2_norm": float(
                np.linalg.norm(coarse.local_trace_values)
            ),
            "local_cell_residual_l2_norm": float(
                np.linalg.norm(result.local_residual)
            ),
            "local_cell_residual_sha256": _array_sha256(
                result.local_residual,
                namespace="task035d.local-cell-delta-residual.v1",
            ),
            "unchanged_cell_zero_delta_limit": unchanged_limit,
            "unchanged_cell_zero_delta_pass": (
                unchanged_zero_delta_pass
            ),
            "identity_checks": identity_checks,
        }
        local_records.append(record)
        live_pairing[canonical_leaf] = {
            "independent_rows": independent_rows,
            "expansion": expansion,
            "local_residual": result.local_residual,
        }
    return local_records, local_cell_sum, live_pairing


def _validate_and_pair_cells(
    *,
    view: Any,
    snapshot: CoarseSnapshot,
    layouts: Sequence[dict[str, Any]],
    actions_a: Sequence[Any],
    rhs_corrections_a: Mapping[int, np.ndarray],
) -> tuple[
    list[dict[str, Any]],
    np.ndarray,
    dict[int, dict[str, Any]],
]:
    """Synchronize rank-local cell validation before global reductions."""

    comm = view.mesh_data.mesh.comm
    local_result = None
    local_error = None
    try:
        local_result = _validate_and_pair_cells_local(
            view=view,
            snapshot=snapshot,
            layouts=layouts,
            actions_a=actions_a,
            rhs_corrections_a=rhs_corrections_a,
        )
    except Exception as exc:
        local_error = {
            "rank": int(comm.rank),
            "exception_type": type(exc).__name__,
            "message": str(exc),
        }
    errors = [
        error
        for error in comm.allgather(local_error)
        if error is not None
    ]
    if errors:
        raise RuntimeError(
            "nested-p rank-local cell validation failed collectively: "
            f"{errors}"
        )
    if local_result is None:
        raise RuntimeError("nested-p local cell validation lost its result")
    local_records, local_cell_sum, live_pairing = local_result
    global_cell_count = int(
        comm.allreduce(len(local_records), op=MPI.SUM)
    )
    changed_cell_count = int(
        comm.allreduce(
            sum(
                bool(record["interior_degree_changed"])
                for record in local_records
            ),
            op=MPI.SUM,
        )
    )
    formal_pair = (
        snapshot.manifest.get("candidate", {}).get("candidate_id")
        == "h15_top_air_remote_p5_interior_bridge_v1"
    )
    if formal_pair and (
        global_cell_count != 134 or changed_cell_count != 32
    ):
        raise RuntimeError(
            "formal nested-p pair must cover 134 cells with exactly "
            f"32 changed interiors, observed {global_cell_count}/"
            f"{changed_cell_count}"
        )
    comm.Allreduce(MPI.IN_PLACE, local_cell_sum, op=MPI.SUM)
    return local_records, local_cell_sum, live_pairing


def _vector_partition_audit(
    *,
    effective: np.ndarray,
    components: Mapping[str, np.ndarray],
) -> tuple[dict[str, Any], np.ndarray]:
    component_sum = np.sum(
        np.stack(tuple(components.values())),
        axis=0,
    )
    unexplained = np.ascontiguousarray(effective - component_sum)
    effective_norm = float(np.linalg.norm(effective))
    component_norm_sum = float(
        sum(np.linalg.norm(values) for values in components.values())
    )
    scale = max(effective_norm, component_norm_sum, 1.0e-30)
    limit = 5.0e-12 + 5.0e-11 * scale
    unexplained_norm = float(np.linalg.norm(unexplained))
    return (
        {
            "schema_version": (
                "task035d.same-trace-live-residual-partition.v1"
            ),
            "status": (
                "same_trace_live_residual_partition_pass"
                if unexplained_norm <= limit
                else "same_trace_live_residual_partition_fail"
            ),
            "pass": unexplained_norm <= limit,
            "effective_residual_definition": (
                "K_A*(x_A-x_B)=r_A(x_B)-r_A(x_A)"
            ),
            "component_formula": (
                "r_B + sum_K rho_K + rho_port + rho_aux - r_A"
            ),
            "component_names": list(components),
            "effective_residual_l2_norm": effective_norm,
            "component_residual_l2_norm_sum": component_norm_sum,
            "component_l2_norms": {
                name: float(np.linalg.norm(values))
                for name, values in components.items()
            },
            "unexplained_residual_l2_norm": unexplained_norm,
            "unexplained_residual_relative": unexplained_norm / scale,
            "unexplained_residual_limit": limit,
            "unexplained_residual_added_back_as_component": False,
            "absolute_cell_marking_used_for_closure": False,
        },
        unexplained,
    )


def _goal_context_for_coarse(
    view: Any,
    snapshot: CoarseSnapshot,
) -> dict[str, Any]:
    context = dict(view.goal_context)
    context["auxiliary_values"] = snapshot.auxiliary_values_b
    context["incident_projections"] = snapshot.incident_projections
    context["auxiliary_coordinate_scales"] = snapshot.coordinate_scales
    return context


def _goal_tolerance_by_label(
    authority: SignificantChannelAuthority,
) -> dict[str, float]:
    result: dict[str, float] = {}
    for channel in authority.channels:
        identity = channel["identity"]
        for quantity in (
            "power",
            "amplitude_real",
            "amplitude_imag",
        ):
            goal = DtnChannelGoal(
                str(identity["side"]),
                int(identity["m"]),
                int(identity["n"]),
                str(identity["polarization"]),
                quantity,
            )
            result[goal.label] = float(
                channel[
                    "power_absolute_tolerance"
                    if quantity == "power"
                    else "complex_amplitude_absolute_tolerance"
                ]
            )
    return result


def _goal_reports_from_unit_pairings(
    *,
    view: Any,
    snapshot: CoarseSnapshot,
    authority: SignificantChannelAuthority,
    basis_report: Mapping[str, Any],
    unit_pairings: Mapping[str, Mapping[str, Any]],
    state_delta_norm: float,
) -> tuple[dict[str, Any], dict[int, dict[str, Any]]]:
    context_a = dict(view.goal_context)
    context_b = _goal_context_for_coarse(view, snapshot)
    modes = tuple(context_a["modes"])
    tolerances = _goal_tolerance_by_label(authority)
    cell_accumulator: dict[int, dict[str, Any]] = {}
    reports: dict[str, Any] = {}
    passed = 0
    power_passed = 0
    amplitude_passed = 0
    for goal in authority.goals:
        goal_metadata = dict(basis_report["goals"][goal.label])
        channel_identity = goal_metadata["canonical_channel_identity"]
        channel_label = _channel_label(channel_identity)
        unit = unit_pairings[channel_label]
        value_a = dtn_channel_goal_value(
            view.config,
            modes,
            np.asarray(context_a["auxiliary_values"]),
            np.asarray(context_a["incident_projections"]),
            goal=goal,
        )
        value_b = dtn_channel_goal_value(
            view.config,
            modes,
            np.asarray(context_b["auxiliary_values"]),
            np.asarray(context_b["incident_projections"]),
            goal=goal,
        )
        if goal.quantity == "power":
            mode_index = int(goal_metadata["auxiliary_mode_index"])
            mode = modes[mode_index]
            outgoing_b = complex(snapshot.auxiliary_values_b[mode_index])
            if mode.side == "top":
                outgoing_b -= complex(
                    snapshot.incident_projections[mode_index]
                )
            outgoing_a_pair = goal_metadata["outgoing_amplitude"]
            outgoing_a = complex(
                float(outgoing_a_pair[0]),
                float(outgoing_a_pair[1]),
            )
            scale_pair = goal_metadata["auxiliary_coordinate_scale"]
            coordinate_scale = complex(
                float(scale_pair[0]),
                float(scale_pair[1]),
            )
            gamma = unit_channel_goal_scalar(
                quantity="power",
                coordinate_scale=coordinate_scale,
                power_weight=float(goal_metadata["power_weight"]),
                outgoing_a=outgoing_a,
                outgoing_b=outgoing_b,
            )
            scaling_semantics = (
                "exact_A_B_midpoint_power_gradient"
            )
        else:
            scalar_pair = goal_metadata[
                "gradient_scalar_solver_coordinate"
            ]
            gamma = complex(
                float(scalar_pair[0]),
                float(scalar_pair[1]),
            )
            scaling_semantics = "exact_affine_amplitude_gradient"
        actual_delta = float(value_a - value_b)
        global_pairing = scaled_unit_adjoint_pairing(
            complex(unit["effective"]),
            gamma,
        )
        estimate = float(global_pairing.real)
        component_reports: dict[str, Any] = {}
        component_sum = 0.0 + 0.0j
        signed_sum = 0.0
        absolute_sum = 0.0
        for name, unit_pairing in unit["components"].items():
            pairing = scaled_unit_adjoint_pairing(
                complex(unit_pairing),
                gamma,
            )
            signed = float(pairing.real)
            component_reports[name] = {
                "complex_pairing": _complex_pair(pairing),
                "signed_real_contribution": signed,
                "absolute_marking_weight": abs(signed),
            }
            component_sum += pairing
            signed_sum += signed
            absolute_sum += abs(signed)
        unexplained_pairing = scaled_unit_adjoint_pairing(
            complex(unit["unexplained"]),
            gamma,
        )
        closure_error = float(estimate - actual_delta)
        channel_report = basis_report["channels"][channel_label]
        unit_residual_norm = float(
            channel_report["adjoint_residual"]["residual_norm"]
        )
        residual_bound = (
            abs(gamma) * unit_residual_norm * float(state_delta_norm)
        )
        roundoff = (
            512.0
            * np.finfo(np.float64).eps
            * max(
                abs(value_a),
                abs(value_b),
                abs(actual_delta),
                abs(estimate),
                1.0,
            )
        )
        closure_limit = float(
            8.0
            * (
                residual_bound
                + abs(unexplained_pairing)
                + roundoff
            )
        )
        preliminary_goal_pass = bool(
            channel_report["pass"]
            and goal_metadata["pass"]
            and abs(closure_error) <= closure_limit
        )
        tolerance = tolerances[goal.label]
        cell_reports: list[dict[str, Any]] = []
        cell_pairing_sum = 0.0 + 0.0j
        cell_pairing_absolute_sum = 0.0
        for cell in unit["cells"]:
            pairing = scaled_unit_adjoint_pairing(
                complex(cell["unit_pairing"]),
                gamma,
            )
            signed = float(pairing.real)
            canonical_leaf = int(cell["canonical_leaf"])
            normalized = abs(signed) / tolerance
            accumulator = cell_accumulator.setdefault(
                canonical_leaf,
                {
                    "canonical_leaf": canonical_leaf,
                    "canonical_leaf_key": cell[
                        "canonical_leaf_key"
                    ],
                    "box": cell["box"],
                    "material_tag": int(cell["material_tag"]),
                    "interior_degree_changed": bool(
                        cell["interior_degree_changed"]
                    ),
                    "goal_contributions": {},
                    "maximum_normalized_absolute_contribution": 0.0,
                    "sum_normalized_absolute_contribution": 0.0,
                    "l2_normalized_absolute_contribution_squared": 0.0,
                },
            )
            accumulator["goal_contributions"][goal.label] = signed
            accumulator[
                "maximum_normalized_absolute_contribution"
            ] = max(
                float(
                    accumulator[
                        "maximum_normalized_absolute_contribution"
                    ]
                ),
                normalized,
            )
            accumulator[
                "sum_normalized_absolute_contribution"
            ] += normalized
            accumulator[
                "l2_normalized_absolute_contribution_squared"
            ] += normalized**2
            cell_reports.append(
                {
                    "canonical_leaf": canonical_leaf,
                    "complex_pairing": _complex_pair(pairing),
                    "signed_real_contribution": signed,
                    "absolute_marking_weight": abs(signed),
                    "normalized_absolute_contribution": normalized,
                }
            )
            cell_pairing_sum += pairing
            cell_pairing_absolute_sum += abs(pairing)
        cell_component = component_reports["cell_total"]
        cell_pairing_error = complex(
            cell_pairing_sum
            - complex(
                float(cell_component["complex_pairing"][0]),
                float(cell_component["complex_pairing"][1]),
            )
        )
        cell_pairing_scale = max(
            abs(cell_pairing_sum),
            cell_pairing_absolute_sum,
            abs(
                complex(
                    float(cell_component["complex_pairing"][0]),
                    float(cell_component["complex_pairing"][1]),
                )
            ),
            1.0e-30,
        )
        cell_pairing_limit = (
            2.0e-13 + 5.0e-11 * cell_pairing_scale
        )
        cell_pairing_pass = abs(cell_pairing_error) <= cell_pairing_limit
        goal_pass = bool(preliminary_goal_pass and cell_pairing_pass)
        passed += int(goal_pass)
        power_passed += int(goal.quantity == "power" and goal_pass)
        amplitude_passed += int(
            goal.quantity
            in {"amplitude_real", "amplitude_imag"}
            and goal_pass
        )
        reports[goal.label] = {
            "goal": goal.as_dict(),
            "pass": goal_pass,
            "value_a": value_a,
            "value_b": value_b,
            "actual_goal_delta_a_minus_b": actual_delta,
            "signed_dwr_estimate": estimate,
            "signed_goal_closure_error": closure_error,
            "goal_closure_limit": closure_limit,
            "unit_adjoint_residual_error_bound": residual_bound,
            "unexplained_residual_pairing_bound": abs(
                unexplained_pairing
            ),
            "unexplained_residual_complex_pairing": _complex_pair(
                unexplained_pairing
            ),
            "scaling_semantics": scaling_semantics,
            "unit_adjoint_goal_scalar": _complex_pair(gamma),
            "global_complex_pairing": _complex_pair(global_pairing),
            "component_complex_pairing_sum": _complex_pair(
                component_sum
            ),
            "component_pairing_closure_error": _complex_pair(
                global_pairing - component_sum
            ),
            "component_signed_sum": signed_sum,
            "component_absolute_marking_sum": absolute_sum,
            "absolute_sum_used_for_closure": False,
            "components": component_reports,
            "cell_pairing_sum": _complex_pair(cell_pairing_sum),
            "cell_pairing_to_cell_total_error": _complex_pair(
                cell_pairing_error
            ),
            "cell_pairing_to_cell_total_limit": cell_pairing_limit,
            "cell_pairing_to_cell_total_pass": cell_pairing_pass,
            "cell_contributions": cell_reports,
            "unchanged_v0_absolute_tolerance": tolerance,
        }
    for cell in cell_accumulator.values():
        cell["l2_normalized_absolute_contribution"] = float(
            np.sqrt(
                cell.pop(
                    "l2_normalized_absolute_contribution_squared"
                )
            )
        )
    summary = {
        "schema_version": "task035d.same-trace-live-goal-dwr.v1",
        "status": (
            "same_trace_live_36_goal_dwr_pass"
            if passed == len(authority.goals)
            else "same_trace_live_36_goal_dwr_fail"
        ),
        "pass": passed == len(authority.goals),
        "requested_real_goal_count": len(authority.goals),
        "passed_real_goal_count": passed,
        "power_goal_count": 12,
        "power_goal_pass_count": power_passed,
        "complex_amplitude_component_goal_count": 24,
        "complex_amplitude_component_goal_pass_count": amplitude_passed,
        "physical_channel_count": 12,
        "complete_complex_amplitude_channel_count": 12,
        "power_uses_exact_midpoint_gradient": True,
        "signed_sum_used_for_closure": True,
        "absolute_sum_used_for_marking_only": True,
        "goals": reports,
    }
    return summary, cell_accumulator


def evaluate_variable_p_nested_enriched_snapshot(
    view: Any,
    *,
    coarse_manifest_path: str | Path,
    coarse_manifest_sha256: str,
    artifact_path: str | Path,
    candidate_id: str,
    expected_plan_sha256: str,
    source_sha: str,
    significant_channel_authority_path: str | Path,
    significant_channel_authority_sha256: str,
) -> dict[str, Any]:
    """Evaluate enriched A against one immutable same-trace coarse B."""

    comm = view.mesh_data.mesh.comm
    output = Path(artifact_path).resolve()
    authority = _collective_local_call(
        comm,
        "enriched significant-channel authority load",
        lambda: load_significant_channel_authority(
            significant_channel_authority_path,
            expected_sha256=significant_channel_authority_sha256,
        ),
    )
    if authority is None:
        raise RuntimeError(
            "enriched significant-channel authority is absent"
        )
    snapshot = load_variable_p_nested_coarse_snapshot(
        coarse_manifest_path,
        communicator=comm,
        expected_manifest_sha256=coarse_manifest_sha256,
        expected_source_sha=source_sha,
        expected_significant_channel_authority_sha256=(
            significant_channel_authority_sha256
        ),
    )
    same_trace_identity, layouts = _same_trace_identity(view)
    coarse_trace_identity = snapshot.manifest["same_trace_identity"]
    if (
        same_trace_identity["same_trace_identity_sha256"]
        != coarse_trace_identity["same_trace_identity_sha256"]
    ):
        raise ValueError(
            "enriched A and coarse B do not have the same live trace identity"
        )
    candidate = _collective_local_call(
        comm,
        "enriched candidate identity",
        lambda: _candidate_identity(
            view,
            candidate_id=candidate_id,
            expected_plan_sha256=expected_plan_sha256,
            source_sha=source_sha,
        ),
    )
    if candidate is None:
        raise RuntimeError("enriched candidate identity is absent")
    coarse_candidate = snapshot.manifest["candidate"]
    port_operator_a = _jsonable(view.port_operator_audit)
    port_operator_b = snapshot.manifest.get(
        "port_operator_audit", {}
    )
    port_operator_identity_gate = _same_trace_port_operator_gate(
        port_operator_a,
        port_operator_b,
    )
    port_operator_gates = comm.allgather(
        port_operator_identity_gate
    )
    if any(not gate["pass"] for gate in port_operator_gates):
        raise ValueError(
            "enriched A and coarse B lack the same qualified trace-only "
            "DtN/port operator identity: "
            f"{port_operator_gates}"
        )
    if (
        candidate["cell_interior_degree_sha256"]
        == coarse_candidate["cell_interior_degree_sha256"]
    ):
        raise ValueError(
            "nested-p A/B candidates have identical interior degree maps"
        )
    if len(snapshot.state_b) != view.A.getSize()[0]:
        raise ValueError("coarse snapshot vector size differs from enriched A")
    current_ranges = _global_petsc_values(view.x, comm)[1]
    expected_ranges = tuple(
        tuple(map(int, values))
        for values in coarse_trace_identity[
            "matrix_vector_ownership_ranges"
        ]
    )
    if current_ranges != expected_ranges:
        raise ValueError("enriched PETSc ownership differs from coarse B")
    if not np.array_equal(
        np.asarray(view.goal_context["incident_projections"]),
        snapshot.incident_projections,
    ) or not np.array_equal(
        _coordinate_scales(view.goal_context),
        snapshot.coordinate_scales,
    ):
        raise ValueError("enriched and coarse port coordinates differ")

    current_layout_by_leaf = _current_layout_by_leaf(layouts)
    trace_replay_by_global: dict[int, np.ndarray] = {}
    coarse_by_leaf = {
        cell.canonical_leaf: cell for cell in snapshot.cells
    }
    local_trace_error = None
    try:
        for canonical_leaf, layout in current_layout_by_leaf.items():
            coarse_cell = coarse_by_leaf.get(canonical_leaf)
            if coarse_cell is None:
                raise ValueError(
                    "coarse snapshot misses a current-rank canonical leaf"
                )
            expansion = np.asarray(
                layout["expansion"],
                dtype=np.complex128,
            )
            independent_rows = np.asarray(
                layout["independent_rows"],
                dtype=np.int64,
            )
            replayed = np.asarray(
                expansion @ snapshot.state_b[independent_rows],
                dtype=np.complex128,
            )
            if not np.allclose(
                replayed,
                coarse_cell.local_trace_values,
                rtol=2.0e-13,
                atol=2.0e-13,
            ):
                raise ValueError(
                    "coarse local trace does not equal C_K*x_B for "
                    f"canonical leaf {canonical_leaf}"
                )
            trace_replay_by_global[int(layout["global_cell"])] = replayed
    except Exception as exc:
        local_trace_error = {
            "rank": int(comm.rank),
            "exception_type": type(exc).__name__,
            "message": str(exc),
        }
    trace_errors = [
        error
        for error in comm.allgather(local_trace_error)
        if error is not None
    ]
    if trace_errors:
        raise RuntimeError(
            "coarse trace replay failed collectively: "
            f"{trace_errors}"
        )
    action_payload_a = _collective_local_call(
        comm,
        "enriched retained Schur action",
        lambda: retained_variable_p_owned_cell_schur_actions(
            view.reduction.system,
            local_trace_values_by_global_cell=trace_replay_by_global,
        ),
    )
    if action_payload_a is None:
        raise RuntimeError("enriched retained Schur action is absent")
    actions_a, action_audit = action_payload_a
    rhs_corrections_a = _cell_rhs_corrections(view)
    local_cell_records, cell_total, live_cell_pairing = (
        _validate_and_pair_cells(
            view=view,
            snapshot=snapshot,
            layouts=layouts,
            actions_a=actions_a,
            rhs_corrections_a=rhs_corrections_a,
        )
    )
    all_local_cell_records = [
        row
        for packet in comm.allgather(local_cell_records)
        for row in packet
    ]
    all_local_cell_records.sort(
        key=lambda row: int(row["canonical_leaf"])
    )

    x_b = _temporary_vector_from_global(view.x, snapshot.state_b)
    action_a_on_b = view.x.duplicate()
    action_a_on_a = view.x.duplicate()
    try:
        view.A.mult(x_b, action_a_on_b)
        view.A.mult(view.x, action_a_on_a)
        state_a, _ = _global_petsc_values(view.x, comm)
        rhs_a, _ = _global_petsc_values(view.b, comm)
        matrix_action_a_on_b, _ = _global_petsc_values(
            action_a_on_b,
            comm,
        )
        matrix_action_a_on_a, _ = _global_petsc_values(
            action_a_on_a,
            comm,
        )
    finally:
        action_a_on_a.destroy()
        action_a_on_b.destroy()
        x_b.destroy()
    residual_a = np.ascontiguousarray(
        rhs_a - matrix_action_a_on_a
    )
    enriched_relative_residual = float(
        np.linalg.norm(residual_a)
        / max(np.linalg.norm(rhs_a), np.finfo(float).tiny)
    )
    coarse_primal_residual_gate = _primal_residual_gate(
        full_active_residual=snapshot.manifest[
            "full_active_residual"
        ],
        reduced_relative_residual=snapshot.manifest[
            "vector_identity"
        ]["relative_residual"],
    )
    enriched_primal_residual_gate = _primal_residual_gate(
        full_active_residual=view.full_active_residual,
        reduced_relative_residual=enriched_relative_residual,
    )
    if not (
        coarse_primal_residual_gate["pass"]
        and enriched_primal_residual_gate["pass"]
    ):
        raise RuntimeError(
            "nested-p primal endpoint residual Gate failed: "
            f"coarse={coarse_primal_residual_gate}, "
            f"enriched={enriched_primal_residual_gate}"
        )
    rhs_delta = np.ascontiguousarray(rhs_a - snapshot.rhs_b)
    rhs_delta_norm = float(np.linalg.norm(rhs_delta))
    rhs_a_norm = float(np.linalg.norm(rhs_a))
    rhs_b_norm = float(np.linalg.norm(snapshot.rhs_b))
    rhs_delta_scale = max(
        rhs_a_norm,
        rhs_b_norm,
        1.0e-30,
    )
    rhs_delta_limit = 5.0e-12 + 5.0e-11 * rhs_delta_scale
    if rhs_delta_norm > rhs_delta_limit:
        raise RuntimeError(
            "same-trace A/B external RHS identity failed: "
            f"{rhs_delta_norm} > {rhs_delta_limit}"
        )
    effective = np.ascontiguousarray(
        matrix_action_a_on_a - matrix_action_a_on_b
    )
    complete_delta = np.ascontiguousarray(
        (rhs_a - snapshot.rhs_b)
        - (
            matrix_action_a_on_b
            - snapshot.matrix_action_b_on_b
        )
    )
    derived_external_candidate = np.ascontiguousarray(
        complete_delta - cell_total
    )
    n_fe = int(view.goal_context["num_fem_dofs_after_mpc"])
    port = np.zeros_like(derived_external_candidate)
    auxiliary = np.zeros_like(derived_external_candidate)
    components = {
        "coarse_solver_residual": snapshot.residual_b,
        "cell_total": cell_total,
        "port": port,
        "auxiliary": auxiliary,
        "enriched_solver_correction": -residual_a,
    }
    partition_audit, unexplained = _vector_partition_audit(
        effective=effective,
        components=components,
    )
    if not partition_audit["pass"]:
        failure_report = {
            "schema_version": _DWR_SCHEMA,
            "status": "controlled_negative_residual_partition",
            "pass": False,
            "controlled_negative": True,
            "failure_stage": "residual_partition_before_adjoints",
            "canonical": False,
            "production_qualified": False,
            "ordinary_default_changed": False,
            "same_trace_only": True,
            "coarse_snapshot": {
                "manifest_path": str(snapshot.manifest_path),
                "manifest_sha256": str(coarse_manifest_sha256),
                "candidate": coarse_candidate,
            },
            "enriched_candidate": candidate,
            "same_trace_identity": same_trace_identity,
            "port_operator_identity_gate": (
                port_operator_identity_gate
            ),
            "primal_endpoints": {
                "coarse_residual_gate": (
                    coarse_primal_residual_gate
                ),
                "enriched_residual_gate": (
                    enriched_primal_residual_gate
                ),
            },
            "residual_partition": partition_audit,
            "unexplained_residual_sha256": _array_sha256(
                unexplained,
                namespace=(
                    "task035d.nested-p-controlled-negative-"
                    "unexplained.v1"
                ),
            ),
            "derived_external_candidate_l2_norm": float(
                np.linalg.norm(derived_external_candidate)
            ),
            "cell_residuals": {
                "global_cell_count": len(all_local_cell_records),
                "interior_degree_changed_cell_count": sum(
                    bool(row["interior_degree_changed"])
                    for row in all_local_cell_records
                ),
                "dense_schur_persisted": False,
                "records": all_local_cell_records,
            },
        }
        _collective_publish_json(comm, output, failure_report)
        raise RuntimeError(
            "same-trace live residual partition failed before adjoints: "
            f"{partition_audit}"
        )

    record_by_leaf = {
        int(record["canonical_leaf"]): record
        for record in local_cell_records
    }
    unit_pairings: dict[str, dict[str, Any]] = {}

    def capture_unit_adjoint(
        identity: dict[str, Any],
        unit_adjoint: PETSc.Vec,
    ) -> None:
        channel_label = _channel_label(identity)
        z, _ = _global_petsc_values(unit_adjoint, comm)
        local_cells: list[dict[str, Any]] = []
        local_error = None
        try:
            for canonical_leaf in sorted(live_cell_pairing):
                payload = live_cell_pairing[canonical_leaf]
                local_adjoint = (
                    payload["expansion"]
                    @ z[payload["independent_rows"]]
                )
                unit_pairing = complex(
                    np.vdot(
                        local_adjoint,
                        payload["local_residual"],
                    )
                )
                record = record_by_leaf[canonical_leaf]
                local_cells.append(
                    {
                        "canonical_leaf": canonical_leaf,
                        "canonical_leaf_key": record[
                            "canonical_leaf_key"
                        ],
                        "box": record["box"],
                        "material_tag": record["material_tag"],
                        "interior_degree_changed": record[
                            "interior_degree_changed"
                        ],
                        "unit_pairing": unit_pairing,
                    }
                )
        except Exception as exc:
            local_error = {
                "rank": int(comm.rank),
                "exception_type": type(exc).__name__,
                "message": str(exc),
            }
        local_errors = [
            error
            for error in comm.allgather(local_error)
            if error is not None
        ]
        if local_errors:
            raise RuntimeError(
                "unit-adjoint local cell pairing failed collectively: "
                f"{local_errors}"
            )
        cells = [
            row
            for packet in comm.allgather(local_cells)
            for row in packet
        ]
        cells.sort(key=lambda row: int(row["canonical_leaf"]))
        if [int(row["canonical_leaf"]) for row in cells] != list(
            range(len(cells))
        ):
            raise RuntimeError(
                "unit-adjoint cell pairings do not cover canonical leaves"
            )
        unit_pairings[channel_label] = {
            "effective": complex(np.vdot(z, effective)),
            "components": {
                name: complex(np.vdot(z, values))
                for name, values in components.items()
            },
            "unexplained": complex(np.vdot(z, unexplained)),
            "adjoint_l2_norm": float(np.linalg.norm(z)),
            "cells": cells,
        }

    basis_report = None
    local_basis_error = None
    try:
        basis_report = evaluate_actual_dtn_unit_channel_adjoint_basis(
            linear_system={
                "A": view.A,
                "b": view.b,
                "x": view.x,
                "ksp": view.ksp,
            },
            dtn_result={"goal_context": dict(view.goal_context)},
            config=view.config,
            communicator=comm,
            goals=authority.goals,
            unit_adjoint_observer=capture_unit_adjoint,
        )
    except Exception as exc:
        local_basis_error = {
            "rank": int(comm.rank),
            "exception_type": type(exc).__name__,
            "message": str(exc),
        }
    basis_errors = [
        error
        for error in comm.allgather(local_basis_error)
        if error is not None
    ]
    if basis_errors:
        failure_report = {
            "schema_version": _DWR_SCHEMA,
            "status": "controlled_negative_unit_adjoint_exception",
            "pass": False,
            "controlled_negative": True,
            "failure_stage": "unit_channel_adjoint_basis",
            "canonical": False,
            "production_qualified": False,
            "ordinary_default_changed": False,
            "same_trace_only": True,
            "errors": basis_errors,
            "coarse_snapshot": {
                "manifest_path": str(snapshot.manifest_path),
                "manifest_sha256": str(coarse_manifest_sha256),
                "candidate": coarse_candidate,
            },
            "enriched_candidate": candidate,
            "same_trace_identity": same_trace_identity,
            "port_operator_identity_gate": (
                port_operator_identity_gate
            ),
            "primal_endpoints": {
                "coarse_residual_gate": (
                    coarse_primal_residual_gate
                ),
                "enriched_residual_gate": (
                    enriched_primal_residual_gate
                ),
            },
            "residual_partition": partition_audit,
            "completed_unit_channel_pairing_count": len(unit_pairings),
            "cell_residuals": {
                "global_cell_count": len(all_local_cell_records),
                "interior_degree_changed_cell_count": sum(
                    bool(row["interior_degree_changed"])
                    for row in all_local_cell_records
                ),
                "dense_schur_persisted": False,
            },
        }
        _collective_publish_json(comm, output, failure_report)
        raise RuntimeError(
            "actual unit-channel adjoint basis failed collectively: "
            f"{basis_errors}"
        )
    if basis_report is None:
        raise RuntimeError("unit-channel adjoint basis lost its report")
    expected_channel_labels = {
        str(channel["label"]) for channel in authority.channels
    }
    if (
        not basis_report["pass"]
        or set(unit_pairings) != expected_channel_labels
        or int(basis_report["unit_adjoint_solve_count"]) != 12
    ):
        failure_report = {
            "schema_version": _DWR_SCHEMA,
            "status": "controlled_negative_unit_adjoint_incomplete",
            "pass": False,
            "controlled_negative": True,
            "failure_stage": "unit_channel_adjoint_basis_gate",
            "canonical": False,
            "production_qualified": False,
            "ordinary_default_changed": False,
            "same_trace_only": True,
            "coarse_snapshot": {
                "manifest_path": str(snapshot.manifest_path),
                "manifest_sha256": str(coarse_manifest_sha256),
                "candidate": coarse_candidate,
            },
            "enriched_candidate": candidate,
            "same_trace_identity": same_trace_identity,
            "port_operator_identity_gate": (
                port_operator_identity_gate
            ),
            "primal_endpoints": {
                "coarse_residual_gate": (
                    coarse_primal_residual_gate
                ),
                "enriched_residual_gate": (
                    enriched_primal_residual_gate
                ),
            },
            "residual_partition": partition_audit,
            "unit_channel_adjoint_basis": basis_report,
            "observed_unit_pairing_labels": sorted(unit_pairings),
            "expected_unit_pairing_labels": sorted(
                expected_channel_labels
            ),
        }
        _collective_publish_json(comm, output, failure_report)
        raise RuntimeError(
            "actual 12-channel unit-adjoint basis failed or is incomplete"
        )
    goal_dwr, cell_indicators = _goal_reports_from_unit_pairings(
        view=view,
        snapshot=snapshot,
        authority=authority,
        basis_report=basis_report,
        unit_pairings=unit_pairings,
        state_delta_norm=float(
            np.linalg.norm(state_a - snapshot.state_b)
        ),
    )

    ranked_cells = sorted(
        cell_indicators.values(),
        key=lambda row: (
            -float(row["maximum_normalized_absolute_contribution"]),
            int(row["canonical_leaf"]),
        ),
    )
    report = {
        "schema_version": _DWR_SCHEMA,
        "status": (
            "same_trace_nested_p_live_dwr_pass"
            if goal_dwr["pass"]
            else "same_trace_nested_p_live_dwr_fail"
        ),
        "pass": bool(
            coarse_primal_residual_gate["pass"]
            and enriched_primal_residual_gate["pass"]
            and partition_audit["pass"]
            and basis_report["pass"]
            and goal_dwr["pass"]
        ),
        "canonical": False,
        "production_qualified": False,
        "ordinary_default_changed": False,
        "same_trace_only": True,
        "cross_trace_primal_prolongation_used": False,
        "coarse_snapshot": {
            "manifest_path": str(snapshot.manifest_path),
            "manifest_sha256": str(coarse_manifest_sha256),
            "candidate": coarse_candidate,
        },
        "enriched_candidate": candidate,
        "same_trace_identity": same_trace_identity,
        "significant_channel_authority": {
            "path": str(authority.path),
            "sha256": authority.file_sha256,
            "ordered_channel_count": len(authority.channels),
            "selected_goal_set_complete_by_frozen_authority": True,
            "physical_channel_count": 12,
            "real_goal_count": 36,
        },
        "primal_endpoints": {
            "coarse_residual_gate": coarse_primal_residual_gate,
            "enriched_residual_gate": enriched_primal_residual_gate,
            "coarse_relative_residual": snapshot.manifest[
                "vector_identity"
            ]["relative_residual"],
            "enriched_relative_residual": enriched_relative_residual,
            "coarse_full_active_residual": snapshot.manifest[
                "full_active_residual"
            ],
            "enriched_full_active_residual": _jsonable(
                view.full_active_residual
            ),
            "state_delta_l2_norm": float(
                np.linalg.norm(state_a - snapshot.state_b)
            ),
        },
        "residual_partition": partition_audit,
        "external_partition": {
            "definition": (
                "DtN/port/aux delta is independently fixed to zero by "
                "the same-trace, trace-only port-operator identity; "
                "(bA-bB)-(KA-KB)xB-sum_K rho_K remains unexplained and "
                "must pass the strict vector partition Gate"
            ),
            "port_trace_rows": [0, n_fe],
            "auxiliary_rows": [
                n_fe,
                len(derived_external_candidate),
            ],
            "port_l2_norm": float(np.linalg.norm(port)),
            "auxiliary_l2_norm": float(np.linalg.norm(auxiliary)),
            "derived_external_candidate_l2_norm": float(
                np.linalg.norm(derived_external_candidate)
            ),
            "direct_rhs_a_minus_b_l2_norm": rhs_delta_norm,
            "rhs_a_l2_norm": rhs_a_norm,
            "rhs_b_l2_norm": rhs_b_norm,
            "direct_rhs_a_minus_b_scale": rhs_delta_scale,
            "direct_rhs_a_minus_b_limit": rhs_delta_limit,
            "direct_rhs_a_minus_b_pass": (
                rhs_delta_norm <= rhs_delta_limit
            ),
            "direct_rhs_a_minus_b_sha256": _array_sha256(
                rhs_delta,
                namespace="task035d.nested-p-rhs-a-minus-b.v1",
            ),
            "derived_external_candidate_sha256": _array_sha256(
                derived_external_candidate,
                namespace=(
                    "task035d.nested-p-derived-external-candidate.v1"
                ),
            ),
            "port_sha256": _array_sha256(
                port,
                namespace="task035d.nested-p-port-residual.v1",
            ),
            "auxiliary_sha256": _array_sha256(
                auxiliary,
                namespace="task035d.nested-p-aux-residual.v1",
            ),
            "zero_delta_derived_from_independent_port_identity": True,
            "port_operator_identity_gate": (
                port_operator_identity_gate
            ),
            "coarse_port_operator_audit": port_operator_b,
            "enriched_port_operator_audit": port_operator_a,
            "unexplained_residual_relabelled_as_external": False,
        },
        "cell_action_audit": _jsonable(action_audit),
        "cell_residuals": {
            "global_cell_count": len(all_local_cell_records),
            "interior_degree_changed_cell_count": sum(
                bool(row["interior_degree_changed"])
                for row in all_local_cell_records
            ),
            "dense_schur_persisted": False,
            "records": all_local_cell_records,
        },
        "unit_channel_adjoint_basis": basis_report,
        "goal_dwr": goal_dwr,
        "cell_multigoal_marking": {
            "normalization": (
                "absolute signed contribution divided by each frozen "
                "unchanged-v0 channel tolerance"
            ),
            "signed_contributions_used_for_goal_closure": True,
            "absolute_contributions_used_for_marking_only": True,
            "cell_count": len(ranked_cells),
            "ranked_cells": ranked_cells,
            "top_20": ranked_cells[:20],
        },
    }
    report_sha = _collective_publish_json(comm, output, report)
    if not report["pass"]:
        raise RuntimeError(
            "same-trace nested-p DWR completed but failed a formal Gate"
        )
    return {
        "schema_version": _DWR_SCHEMA,
        "status": "same_trace_nested_p_live_dwr_published",
        "pass": True,
        "report_path": str(output),
        "report_sha256": report_sha,
        "same_trace_identity_sha256": same_trace_identity[
            "same_trace_identity_sha256"
        ],
        "unit_adjoint_solve_count": int(
            basis_report["unit_adjoint_solve_count"]
        ),
        "passed_real_goal_count": int(
            goal_dwr["passed_real_goal_count"]
        ),
        "ordinary_default_changed": False,
    }


def build_variable_p_nested_coarse_snapshot_observer(
    **kwargs: Any,
):
    """Return the default-off live callback for coarse snapshot publication."""

    def observer(view: Any) -> None:
        write_variable_p_nested_coarse_snapshot(view, **kwargs)

    return observer


def build_variable_p_nested_enriched_evaluator_observer(
    **kwargs: Any,
):
    """Return the default-off live callback for enriched DWR evaluation."""

    def observer(view: Any) -> None:
        evaluate_variable_p_nested_enriched_snapshot(view, **kwargs)

    return observer


__all__ = [
    "CoarseCellSnapshot",
    "CoarseSnapshot",
    "SignificantChannelAuthority",
    "build_variable_p_nested_coarse_snapshot_observer",
    "build_variable_p_nested_enriched_evaluator_observer",
    "evaluate_variable_p_nested_enriched_snapshot",
    "load_significant_channel_authority",
    "load_variable_p_nested_coarse_snapshot",
    "write_variable_p_nested_coarse_snapshot",
]
