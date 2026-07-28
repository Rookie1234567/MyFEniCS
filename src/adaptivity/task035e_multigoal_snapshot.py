"""Immutable live current-state snapshots for Task035e multi-goal DWR.

This module is deliberately narrower than a DWR evaluator.  It observes one
qualified :class:`~src.solvers.dtn_port_3d.Stage4VariablePLiveView` while the
borrowed PETSc objects are alive and persists the state needed by a later,
separately qualified adjoint/evaluator:

* owned reduced ``x``, ``b``, ``A*x`` and ``b-A*x`` slices;
* owned recovered active-full solution, right-hand side, and auxiliary action;
* owned coefficients of the recovered p6 carrier field.

No full distributed vector is gathered into Python.  The matrix is not
serialized: only each rank's local CSR content hash and structural metadata
are recorded.  A root manifest is published only after every rank has written
and independently replayed its mode-0600 NPZ shard.

The snapshot grants no adjoint, DWR, local-h transfer, or accuracy credit.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
from types import MappingProxyType
from typing import Any, Callable, Mapping
from uuid import uuid4

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from .blind_controller.contracts import (
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
)


SNAPSHOT_SCHEMA = "task035e.multigoal-current-live-snapshot.v1"
SHARD_SCHEMA = "task035e.multigoal-current-live-shard.v1"
_MANIFEST_HASH_NAMESPACE = "task035e.multigoal-current-manifest.v1"
_SHARD_HASH_NAMESPACE = "task035e.multigoal-current-shard.v1"
_SOURCE_RE = re.compile(r"[0-9a-f]{40}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_TRIAL_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
_COMPLEX_DTYPE = np.dtype("<c16")
_INTEGER_DTYPE = np.dtype("<i8")
_FLOAT_DTYPE = np.dtype("<f8")
_EXPECTED_SHARD_ARRAYS = frozenset(
    {
        "schema_version",
        "rank",
        "mpi_size",
        "reduced_ownership_range",
        "active_full_ownership_range",
        "p6_field_ownership_range",
        "active_auxiliary_action_present",
        "reduced_x_owned",
        "reduced_b_owned",
        "reduced_ax_owned",
        "reduced_residual_owned",
        "active_full_solution_owned",
        "active_full_rhs_owned",
        "active_full_auxiliary_action_owned",
        "p6_recovered_field_owned",
        "local_identity_sha256",
        "shard_payload_sha256",
    }
)
_PAYLOAD_ARRAY_NAMES = (
    "reduced_x_owned",
    "reduced_b_owned",
    "reduced_ax_owned",
    "reduced_residual_owned",
    "active_full_solution_owned",
    "active_full_rhs_owned",
    "active_full_auxiliary_action_owned",
    "p6_recovered_field_owned",
)


class Task035eSnapshotError(RuntimeError):
    """Fail-closed Task035e live-snapshot error."""


@dataclass(frozen=True, slots=True)
class Task035eSnapshotReceipt:
    """Non-field receipt returned after collective publication."""

    manifest_path: Path
    manifest_file_sha256: str
    manifest_payload_sha256: str
    source_sha: str
    trial_id: str
    cycle_index: int
    plan_file_sha256: str
    mpi_size: int
    formal_mpi8_qualified: bool


@dataclass(frozen=True, slots=True)
class LoadedTask035eSnapshot:
    """Independently verified current-rank shard and immutable manifest."""

    manifest_path: Path
    manifest_file_sha256: str
    shard_path: Path
    manifest: Mapping[str, Any]
    arrays: Mapping[str, np.ndarray]


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
    if isinstance(value, (set, frozenset)):
        return [_jsonable(item) for item in sorted(value, key=repr)]
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, complex):
        return [float(value.real), float(value.imag)]
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("snapshot identity contains a non-finite float")
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise TypeError(
        "snapshot identity contains a non-canonical object: "
        f"{type(value).__name__}"
    )


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _jsonable(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _json_sha256(value: Any, *, namespace: str) -> str:
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    digest.update(_canonical_json_bytes(value))
    return digest.hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_array(values: Any) -> np.ndarray:
    array = np.asarray(values)
    if np.issubdtype(array.dtype, np.complexfloating):
        result = np.asarray(array, dtype=_COMPLEX_DTYPE)
    elif np.issubdtype(array.dtype, np.integer):
        result = np.asarray(array, dtype=_INTEGER_DTYPE)
    elif np.issubdtype(array.dtype, np.floating):
        result = np.asarray(array, dtype=_FLOAT_DTYPE)
    elif np.issubdtype(array.dtype, np.bool_):
        result = np.asarray(array, dtype=np.dtype("u1"))
    else:
        raise TypeError(f"snapshot array dtype is unsupported: {array.dtype}")
    return np.ascontiguousarray(result)


def _array_sha256(values: Any, *, namespace: str) -> str:
    array = _canonical_array(values)
    digest = hashlib.sha256()
    digest.update(namespace.encode("ascii"))
    digest.update(b"\0")
    digest.update(str(array.dtype).encode("ascii"))
    digest.update(b"\0")
    digest.update(
        np.asarray(array.shape, dtype=_INTEGER_DTYPE).tobytes(order="C")
    )
    digest.update(array.tobytes(order="C"))
    return digest.hexdigest()


def _array_metadata(
    values: np.ndarray,
    *,
    name: str,
) -> dict[str, Any]:
    canonical = _canonical_array(values)
    return {
        "dtype": str(canonical.dtype),
        "shape": list(canonical.shape),
        "sha256": _array_sha256(
            canonical,
            namespace=f"task035e.snapshot-array.{name}.v1",
        ),
    }


def _atomic_mode_0600(path: Path, writer: Callable[[Any], None]) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to replace immutable artifact {path}")
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    descriptor = -1
    try:
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
        with os.fdopen(descriptor, "wb") as stream:
            descriptor = -1
            writer(stream)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _atomic_npz(path: Path, arrays: Mapping[str, np.ndarray]) -> None:
    _atomic_mode_0600(path, lambda stream: np.savez(stream, **arrays))


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    encoded = (
        json.dumps(
            _jsonable(payload),
            sort_keys=True,
            indent=2,
            ensure_ascii=True,
            allow_nan=False,
        )
        + "\n"
    ).encode("ascii")
    _atomic_mode_0600(path, lambda stream: stream.write(encoded))


def _require_mode_0600(path: Path, *, label: str) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode != 0o600:
        raise ValueError(f"{label} is mode {mode:o}, expected 600: {path}")


def _collective_local_call(
    communicator: MPI.Intracomm,
    phase: str,
    operation: Callable[[], Any],
) -> Any:
    result = None
    error = None
    try:
        result = operation()
    except Exception as exc:
        error = {
            "rank": int(communicator.rank),
            "phase": phase,
            "exception_type": type(exc).__name__,
            "message": str(exc),
        }
    errors = [
        row for row in communicator.allgather(error) if row is not None
    ]
    if errors:
        raise Task035eSnapshotError(
            f"{phase} failed collectively: "
            + json.dumps(errors, sort_keys=True)
        )
    return result


def _source_sha(value: Any) -> str:
    source = str(value)
    if _SOURCE_RE.fullmatch(source) is None:
        raise ValueError("source_sha must be one lowercase full Git SHA")
    return source


def _sha256(value: Any, *, label: str) -> str:
    digest = str(value)
    if _SHA256_RE.fullmatch(digest) is None:
        raise ValueError(f"{label} must be one lowercase SHA-256")
    return digest


def _trial_id(value: Any) -> str:
    trial = str(value)
    if _TRIAL_RE.fullmatch(trial) is None:
        raise ValueError("trial_id has an invalid or unsafe spelling")
    return trial


def _cycle_index(value: Any) -> int:
    if type(value) is not int or not 0 <= value <= 5:
        raise ValueError("cycle_index must be an integer in [0, 5]")
    return int(value)


def _load_plan_identity(
    view: Any,
    *,
    source_sha: str,
    cycle_index: int,
    expected_plan_sha256: str,
) -> dict[str, Any]:
    context = getattr(view.mesh_data, "local_h_context", None)
    if context is None:
        raise ValueError("live snapshot requires the executed local-h context")
    plan_path = Path(context.plan_path).expanduser().resolve()
    if not plan_path.is_file():
        raise FileNotFoundError(f"executed plan is absent: {plan_path}")
    observed_sha = _file_sha256(plan_path)
    context_sha = _sha256(
        context.plan_file_sha256,
        label="local-h context plan SHA-256",
    )
    if observed_sha != expected_plan_sha256 or context_sha != observed_sha:
        raise ValueError(
            "expected, on-disk, and executed plan SHA-256 identities differ"
        )
    payload = json.loads(plan_path.read_text(encoding="utf-8"))
    if (
        payload.get("schema_version")
        != "task035e.stage4-multilevel-local-h-refinement-plan.v1"
        or payload.get("status")
        != "stage4_balanced_multilevel_local_h_plan"
        or payload.get("variable_trace_from_cell_degrees") is not True
    ):
        raise ValueError("executed plan is not a Task035e variable-h/p plan")
    provenance = payload.get("provenance")
    if not isinstance(provenance, Mapping):
        raise ValueError("executed Task035e plan has no provenance")
    if provenance.get("source_sha") != source_sha:
        raise ValueError("executed plan source SHA differs from the request")
    provenance_cycle = provenance.get("cycle_index")
    if provenance_cycle is None:
        if (
            cycle_index != 0
            or provenance.get("schema_version")
            != "task035e.blind-initial-provenance.v1"
        ):
            raise ValueError(
                "only the blind initial plan may omit provenance cycle_index"
            )
    elif type(provenance_cycle) is not int or provenance_cycle != cycle_index:
        raise ValueError("executed plan cycle differs from the request")

    expected_forest = payload.get("expected_forest")
    if not isinstance(expected_forest, Mapping):
        raise ValueError("executed plan has no expected forest authority")
    plan_forest_sha = _sha256(
        expected_forest.get("leaf_catalog_sha256"),
        label="plan forest SHA-256",
    )
    plan_degree_sha = _sha256(
        payload.get("cell_interior_degree_plan_sha256"),
        label="plan cell-degree SHA-256",
    )
    forest_audit = getattr(context.forest, "audit", None)
    if not isinstance(forest_audit, Mapping):
        raise ValueError("executed local-h context has no forest audit")
    forest_sha = _sha256(
        forest_audit.get("leaf_catalog_sha256"),
        label="executed forest SHA-256",
    )
    degree_audit = getattr(view.reduction.degree_plan, "audit", None)
    if not isinstance(degree_audit, Mapping):
        raise ValueError("executed reduction has no degree-plan audit")
    degree_sha = _sha256(
        degree_audit.get("cell_degree_plan_sha256"),
        label="executed cell-degree SHA-256",
    )
    if plan_forest_sha != forest_sha or plan_degree_sha != degree_sha:
        raise ValueError(
            "plan, executed forest, and executed degree-map identities differ"
        )
    return {
        "path": str(plan_path),
        "file_sha256": observed_sha,
        "payload_sha256": _json_sha256(
            payload,
            namespace="task035e.executed-plan-payload.v1",
        ),
        "provenance_sha256": _json_sha256(
            provenance,
            namespace="task035e.executed-plan-provenance.v1",
        ),
        "provenance_schema_version": provenance.get("schema_version"),
        "forest_leaf_catalog_sha256": forest_sha,
        "cell_degree_plan_sha256": degree_sha,
    }


def _mode_payload(mode: Any) -> dict[str, Any]:
    names = (
        "side",
        "m",
        "n",
        "polarization",
        "alpha",
        "gamma",
        "beta",
        "refractive_index",
        "vertical_sign",
        "e_vector",
        "k_vector",
        "h_vector",
        "electric_tangential_norm_sq",
        "power_per_unit_amplitude",
        "propagating",
        "rayleigh_warning",
    )
    missing = [name for name in names if not hasattr(mode, name)]
    if missing:
        raise ValueError(f"goal-context mode is incomplete: {missing}")
    return {name: _jsonable(getattr(mode, name)) for name in names}


def _goal_context_identity(goal_context: Mapping[str, Any]) -> dict[str, Any]:
    modes = tuple(goal_context.get("modes", ()))
    if not modes:
        raise ValueError("goal context has no DtN modes")
    auxiliary = _canonical_array(goal_context.get("auxiliary_values"))
    incident = _canonical_array(goal_context.get("incident_projections"))
    if auxiliary.ndim != 1 or incident.shape != auxiliary.shape:
        raise ValueError("goal-context auxiliary arrays are inconsistent")
    raw_scales = goal_context.get("auxiliary_coordinate_scales")
    scales = (
        np.ones(len(modes), dtype=_COMPLEX_DTYPE)
        if raw_scales is None
        else _canonical_array(raw_scales)
    )
    if len(modes) != len(auxiliary) or scales.shape != auxiliary.shape:
        raise ValueError("goal-context mode and coordinate counts differ")
    mode_rows = [_mode_payload(mode) for mode in modes]
    return {
        "mode_count": len(mode_rows),
        "ordered_modes_sha256": _json_sha256(
            mode_rows,
            namespace="task035e.current-ordered-dtn-modes.v1",
        ),
        "auxiliary_values_sha256": _array_sha256(
            auxiliary,
            namespace="task035e.current-physical-auxiliary-values.v1",
        ),
        "incident_projections_sha256": _array_sha256(
            incident,
            namespace="task035e.current-incident-projections.v1",
        ),
        "coordinate_scales_sha256": _array_sha256(
            scales,
            namespace="task035e.current-auxiliary-coordinate-scales.v1",
        ),
        "coordinate_scale_source": (
            "explicit_goal_context"
            if raw_scales is not None
            else "implicit_ones_materialized"
        ),
        "num_fem_dofs_after_mpc": int(
            goal_context["num_fem_dofs_after_mpc"]
        ),
        "normalization": str(goal_context["normalization"]),
        "formal_goal_count": len(FORMAL_GOAL_IDS),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
    }


def _floquet_identity(floquet: Any) -> dict[str, Any]:
    payload = {
        "phase_x": _jsonable(complex(floquet.phase_x)),
        "phase_y": _jsonable(complex(floquet.phase_y)),
        "phase_corner": _jsonable(
            complex(
                getattr(
                    floquet,
                    "phase_corner",
                    complex(floquet.phase_x) * complex(floquet.phase_y),
                )
            )
        ),
    }
    for name in (
        "constraint_mode_resolved",
        "num_constraints",
        "num_x_constraints",
        "num_y_constraints",
        "num_corner_constraints",
        "num_edge_constraints",
        "num_face_constraints",
        "raw_map_nnz",
        "max_masters_per_slave",
        "used_full_boundary_gather",
        "created_dense_boundary_square",
    ):
        if hasattr(floquet, name):
            payload[name] = _jsonable(getattr(floquet, name))
    payload["identity_sha256"] = _json_sha256(
        payload,
        namespace="task035e.current-floquet-identity.v1",
    )
    return payload


def _config_identity(config: Any) -> dict[str, Any]:
    if not hasattr(config, "as_jsonable"):
        raise ValueError("live snapshot config lacks as_jsonable()")
    payload = _jsonable(config.as_jsonable())
    return {
        "payload_sha256": _json_sha256(
            payload,
            namespace="task035e.current-config-identity.v1",
        )
    }


def _abi_identity() -> dict[str, str]:
    scalar = np.dtype(PETSc.ScalarType)
    integer = np.dtype(PETSc.IntType)
    if scalar != np.dtype(np.complex128):
        raise ValueError(
            f"Task035e snapshot requires PETSc complex128, got {scalar}"
        )
    if integer != np.dtype(np.int32):
        raise ValueError(
            f"Task035e snapshot requires PETSc int32, got {integer}"
        )
    return {
        "petsc_scalar_type": str(scalar),
        "petsc_integer_type": str(integer),
    }


def _reduction_identity(view: Any) -> dict[str, Any]:
    reduction = view.reduction
    system = reduction.system
    degree_audit = _jsonable(reduction.degree_plan.audit)
    entity_map = system.entity_map
    return {
        "build_schema_version": reduction.build_audit.get(
            "schema_version"
        ),
        "build_status": reduction.build_audit.get("status"),
        "system_build_schema_version": system.build_audit.get(
            "schema_version"
        ),
        "system_build_status": system.build_audit.get("status"),
        "degree_audit_sha256": _json_sha256(
            degree_audit,
            namespace="task035e.current-degree-audit.v1",
        ),
        "active_full_rows": int(entity_map.active_rows),
        "active_trace_rows_raw": int(entity_map.active_trace_rows),
        "independent_trace_rows": int(system.active_trace_rows),
        "appended_auxiliary_rows": int(system.appended_rows),
        "actual_full3d_equivalent_active_fe_dofs": int(
            reduction.build_audit[
                "actual_full3d_equivalent_active_fe_dofs"
            ]
        ),
        "inactive_p6_rows_globally_numbered": bool(
            reduction.build_audit.get(
                "inactive_p6_rows_globally_numbered", False
            )
        ),
    }


def _rank_local_reduction_identity(view: Any) -> dict[str, str]:
    """Hash rank-varying setup telemetry without calling it common."""

    return {
        "reduction_build_audit_sha256": _json_sha256(
            view.reduction.build_audit,
            namespace="task035e.current-rank-reduction-build-audit.v1",
        ),
        "system_build_audit_sha256": _json_sha256(
            view.reduction.system.build_audit,
            namespace="task035e.current-rank-system-build-audit.v1",
        ),
    }


def _qualified_gate_identity(view: Any) -> dict[str, Any]:
    residual = view.full_active_residual
    if not isinstance(residual, Mapping):
        raise ValueError("full active residual evidence is absent")
    relative = residual.get("linear_system_relative_residual")
    if (
        not isinstance(relative, (int, float))
        or not math.isfinite(float(relative))
        or float(relative) > 1.0e-9
        or float(relative) < 0.0
    ):
        raise ValueError(
            "full explicit active residual is absent or exceeds 1e-9"
        )
    telemetry = view.primal_solver_telemetry
    if (
        not isinstance(telemetry, Mapping)
        or int(telemetry.get("converged_reason", 0)) <= 0
    ):
        raise ValueError("primal direct solver did not converge")
    port = view.port_operator_audit
    checks = port.get("checks") if isinstance(port, Mapping) else None
    if (
        not isinstance(port, Mapping)
        or port.get("schema_version")
        != "task035d.variable-p-trace-only-port-operator.v1"
        or port.get("pass") is not True
        or not isinstance(checks, Mapping)
        or not checks
        or not all(value is True for value in checks.values())
        or port.get("auxiliary_interior_columns_allocated") is not False
    ):
        raise ValueError("trace-only DtN/port operator audit is not qualified")
    return {
        "full_active_residual": _jsonable(residual),
        "full_active_residual_sha256": _json_sha256(
            residual,
            namespace="task035e.current-full-active-residual.v1",
        ),
        "port_operator_audit_sha256": _json_sha256(
            port,
            namespace="task035e.current-port-operator-audit.v1",
        ),
        "port_metrics_sha256": _json_sha256(
            view.port_metrics,
            namespace="task035e.current-port-metrics.v1",
        ),
        "primal_solver_telemetry": _jsonable(telemetry),
        "primal_solver_telemetry_sha256": _json_sha256(
            telemetry,
            namespace="task035e.current-primal-telemetry.v1",
        ),
    }


def _vector_owned(vector: PETSc.Vec, *, label: str) -> tuple[
    np.ndarray,
    tuple[int, int],
    int,
]:
    start, end = map(int, vector.getOwnershipRange())
    values = np.asarray(
        vector.getArray(readonly=True), dtype=_COMPLEX_DTYPE
    ).copy()
    if values.ndim != 1 or len(values) != end - start:
        raise ValueError(f"{label} owned array and ownership range differ")
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{label} contains non-finite values")
    return np.ascontiguousarray(values), (start, end), int(vector.getSize())


def _local_matrix_csr_identity(matrix: PETSc.Mat) -> dict[str, Any]:
    row_start, row_end = map(int, matrix.getOwnershipRange())
    column_start, column_end = map(
        int, matrix.getOwnershipRangeColumn()
    )
    indptr_raw, indices_raw, values_raw = matrix.getValuesCSR()
    indptr = _canonical_array(indptr_raw)
    indices = _canonical_array(indices_raw)
    values = _canonical_array(values_raw)
    if (
        indptr.shape != (row_end - row_start + 1,)
        or int(indptr[0]) != 0
        or int(indptr[-1]) != len(indices)
        or len(indices) != len(values)
        or np.any(np.diff(indptr) < 0)
    ):
        raise ValueError("PETSc local CSR structure is inconsistent")
    payload = {
        "global_shape": list(map(int, matrix.getSize())),
        "row_ownership_range": [row_start, row_end],
        "column_ownership_range": [column_start, column_end],
        "local_nnz": len(values),
        "indptr_sha256": _array_sha256(
            indptr,
            namespace="task035e.current-matrix-local-indptr.v1",
        ),
        "indices_sha256": _array_sha256(
            indices,
            namespace="task035e.current-matrix-local-indices.v1",
        ),
        "values_sha256": _array_sha256(
            values,
            namespace="task035e.current-matrix-local-values.v1",
        ),
        "matrix_type": str(matrix.getType()),
        "csr_serialized": False,
        "column_index_semantics": (
            "PETSc Mat.getValuesCSR rank-local representation; "
            "identity is MPI-partition-bound"
        ),
    }
    payload["local_csr_content_sha256"] = _json_sha256(
        payload,
        namespace="task035e.current-matrix-local-csr.v1",
    )
    return payload


def _ownership_catalog(
    rows: list[Mapping[str, Any]],
    *,
    family: str,
    global_size: int,
) -> list[list[int]]:
    ranges = [
        list(map(int, row["ownership_ranges"][family])) for row in rows
    ]
    cursor = 0
    for rank, (start, end) in enumerate(ranges):
        if start != cursor or end < start:
            raise ValueError(
                f"{family} ownership range is invalid at rank {rank}"
            )
        cursor = end
    if cursor != int(global_size):
        raise ValueError(
            f"{family} ownership ranges do not close global size"
        )
    return ranges


def _partition_array_hash(
    rows: list[Mapping[str, Any]],
    *,
    family: str,
    array_name: str,
) -> str:
    payload = [
        {
            "rank": int(row["rank"]),
            "ownership_range": list(row["ownership_ranges"][family]),
            "local_array_sha256": row["arrays"][array_name]["sha256"],
        }
        for row in rows
    ]
    return _json_sha256(
        payload,
        namespace=f"task035e.partition-bound.{array_name}.v1",
    )


def _validate_shard_arrays(
    arrays: Mapping[str, np.ndarray],
    *,
    rank: int,
    mpi_size: int,
    expected_metadata: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if set(arrays) != _EXPECTED_SHARD_ARRAYS:
        missing = sorted(_EXPECTED_SHARD_ARRAYS - set(arrays))
        extra = sorted(set(arrays) - _EXPECTED_SHARD_ARRAYS)
        raise ValueError(
            f"snapshot shard arrays differ: missing={missing}, extra={extra}"
        )
    if (
        str(np.asarray(arrays["schema_version"]).reshape(-1)[0])
        != SHARD_SCHEMA
        or int(np.asarray(arrays["rank"]).reshape(-1)[0]) != rank
        or int(np.asarray(arrays["mpi_size"]).reshape(-1)[0]) != mpi_size
    ):
        raise ValueError("snapshot shard rank/schema identity differs")
    ranges = {
        "reduced": list(
            map(
                int,
                np.asarray(arrays["reduced_ownership_range"]).tolist(),
            )
        ),
        "active_full": list(
            map(
                int,
                np.asarray(
                    arrays["active_full_ownership_range"]
                ).tolist(),
            )
        ),
        "p6_field": list(
            map(
                int,
                np.asarray(
                    arrays["p6_field_ownership_range"]
                ).tolist(),
            )
        ),
    }
    if any(len(values) != 2 for values in ranges.values()):
        raise ValueError("snapshot shard ownership range is malformed")
    canonical: dict[str, np.ndarray] = {}
    array_metadata: dict[str, dict[str, Any]] = {}
    for name in _PAYLOAD_ARRAY_NAMES:
        values = _canonical_array(arrays[name])
        if values.ndim != 1 or not np.all(np.isfinite(values)):
            raise ValueError(f"snapshot shard {name} is invalid")
        canonical[name] = values
        array_metadata[name] = _array_metadata(values, name=name)
    for family, names in {
        "reduced": (
            "reduced_x_owned",
            "reduced_b_owned",
            "reduced_ax_owned",
            "reduced_residual_owned",
        ),
        "active_full": (
            "active_full_solution_owned",
            "active_full_rhs_owned",
            "active_full_auxiliary_action_owned",
        ),
        "p6_field": ("p6_recovered_field_owned",),
    }.items():
        expected_length = ranges[family][1] - ranges[family][0]
        if any(len(canonical[name]) != expected_length for name in names):
            raise ValueError(
                f"snapshot shard {family} owned lengths are inconsistent"
            )
    if not np.array_equal(
        canonical["reduced_residual_owned"],
        canonical["reduced_b_owned"] - canonical["reduced_ax_owned"],
    ):
        raise ValueError("snapshot reduced residual is not exactly b-Ax")
    auxiliary_present = bool(
        int(
            np.asarray(
                arrays["active_auxiliary_action_present"]
            ).reshape(-1)[0]
        )
    )
    if (
        not auxiliary_present
        and np.any(canonical["active_full_auxiliary_action_owned"] != 0.0)
    ):
        raise ValueError("absent active auxiliary action is not zero")
    local_identity_sha = _sha256(
        str(np.asarray(arrays["local_identity_sha256"]).reshape(-1)[0]),
        label="shard local identity SHA-256",
    )
    unsigned = {
        "schema_version": SHARD_SCHEMA,
        "rank": rank,
        "mpi_size": mpi_size,
        "ownership_ranges": ranges,
        "active_auxiliary_action_present": auxiliary_present,
        "local_identity_sha256": local_identity_sha,
        "arrays": array_metadata,
    }
    payload_sha = _json_sha256(
        unsigned,
        namespace=_SHARD_HASH_NAMESPACE,
    )
    stored_payload_sha = _sha256(
        str(np.asarray(arrays["shard_payload_sha256"]).reshape(-1)[0]),
        label="shard payload SHA-256",
    )
    if stored_payload_sha != payload_sha:
        raise ValueError("snapshot shard payload self-hash differs")
    observed = {
        **unsigned,
        "shard_payload_sha256": payload_sha,
    }
    if expected_metadata is not None:
        for name in (
            "rank",
            "ownership_ranges",
            "active_auxiliary_action_present",
            "local_identity_sha256",
            "arrays",
            "shard_payload_sha256",
        ):
            if _jsonable(observed[name]) != _jsonable(
                expected_metadata[name]
            ):
                raise ValueError(
                    f"snapshot shard metadata differs at {name}"
                )
    return observed


def _read_shard(
    path: Path,
    *,
    rank: int,
    mpi_size: int,
    expected_file_sha256: str | None,
    expected_metadata: Mapping[str, Any] | None,
) -> tuple[dict[str, np.ndarray], dict[str, Any]]:
    if not path.is_file():
        raise FileNotFoundError(f"snapshot shard is absent: {path}")
    _require_mode_0600(path, label="snapshot shard")
    observed_file_sha = _file_sha256(path)
    if (
        expected_file_sha256 is not None
        and observed_file_sha != expected_file_sha256
    ):
        raise ValueError("snapshot shard file SHA-256 differs")
    with np.load(path, allow_pickle=False) as archive:
        arrays = {
            name: np.asarray(archive[name]).copy()
            for name in archive.files
        }
    metadata = _validate_shard_arrays(
        arrays,
        rank=rank,
        mpi_size=mpi_size,
        expected_metadata=expected_metadata,
    )
    metadata["path"] = path.name
    metadata["file_sha256"] = observed_file_sha
    metadata["bytes"] = int(path.stat().st_size)
    return arrays, metadata


def _manifest_payload(
    *,
    rows: list[Mapping[str, Any]],
    source_sha: str,
    trial_id: str,
    cycle_index: int,
    plan_identity: Mapping[str, Any],
    common_identity: Mapping[str, Any],
    gate_identity: Mapping[str, Any],
    reduced_global_size: int,
    active_global_size: int,
    p6_global_size: int,
    formal_mpi8_qualified: bool,
) -> dict[str, Any]:
    rows.sort(key=lambda row: int(row["rank"]))
    if [int(row["rank"]) for row in rows] != list(range(len(rows))):
        raise ValueError("snapshot shard metadata does not cover every rank")
    common_hashes = {str(row["common_identity_sha256"]) for row in rows}
    gate_hashes = {str(row["gate_identity_sha256"]) for row in rows}
    if len(common_hashes) != 1 or len(gate_hashes) != 1:
        raise ValueError("snapshot common or Gate identity differs by rank")
    reduced_ranges = _ownership_catalog(
        rows,
        family="reduced",
        global_size=reduced_global_size,
    )
    active_ranges = _ownership_catalog(
        rows,
        family="active_full",
        global_size=active_global_size,
    )
    p6_ranges = _ownership_catalog(
        rows,
        family="p6_field",
        global_size=p6_global_size,
    )
    matrix_rows = [dict(row["matrix_local_csr"]) for row in rows]
    if [
        list(row["row_ownership_range"]) for row in matrix_rows
    ] != reduced_ranges:
        raise ValueError("matrix and reduced-vector row partitions differ")
    matrix_shapes = {
        tuple(map(int, row["global_shape"])) for row in matrix_rows
    }
    if matrix_shapes != {(reduced_global_size, reduced_global_size)}:
        raise ValueError("snapshot matrix is not the reduced square operator")
    auxiliary_flags = {
        bool(row["active_auxiliary_action_present"]) for row in rows
    }
    if len(auxiliary_flags) != 1:
        raise ValueError("active auxiliary-action presence differs by rank")

    partitions = {
        "reduced": {
            "global_size": reduced_global_size,
            "ownership_ranges": reduced_ranges,
            "partition_bound_array_sha256": {
                name: _partition_array_hash(
                    rows,
                    family="reduced",
                    array_name=name,
                )
                for name in (
                    "reduced_x_owned",
                    "reduced_b_owned",
                    "reduced_ax_owned",
                    "reduced_residual_owned",
                )
            },
        },
        "active_full": {
            "global_size": active_global_size,
            "ownership_ranges": active_ranges,
            "auxiliary_action_present": auxiliary_flags.pop(),
            "partition_bound_array_sha256": {
                name: _partition_array_hash(
                    rows,
                    family="active_full",
                    array_name=name,
                )
                for name in (
                    "active_full_solution_owned",
                    "active_full_rhs_owned",
                    "active_full_auxiliary_action_owned",
                )
            },
        },
        "p6_recovered_field": {
            "global_size": p6_global_size,
            "ownership_ranges": p6_ranges,
            "partition_bound_array_sha256": {
                "p6_recovered_field_owned": _partition_array_hash(
                    rows,
                    family="p6_field",
                    array_name="p6_recovered_field_owned",
                )
            },
        },
    }
    matrix_partition_sha = _json_sha256(
        [
            {
                "rank": rank,
                **matrix_rows[rank],
            }
            for rank in range(len(rows))
        ],
        namespace="task035e.current-matrix-partition-bound-csr.v1",
    )
    shard_rows = [
        {
            key: _jsonable(row[key])
            for key in (
                "rank",
                "path",
                "file_sha256",
                "bytes",
                "ownership_ranges",
                "active_auxiliary_action_present",
                "local_identity_sha256",
                "arrays",
                "shard_payload_sha256",
            )
        }
        for row in rows
    ]
    unsigned = {
        "schema_version": SNAPSHOT_SCHEMA,
        "status": "multigoal_current_live_snapshot_pass",
        "pass": True,
        "role": "current_blind_state",
        "source_sha": source_sha,
        "trial_id": trial_id,
        "cycle_index": cycle_index,
        "mpi_size": len(rows),
        "formal_mpi8_qualified": formal_mpi8_qualified,
        "diagnostic_serial_fixture": not formal_mpi8_qualified,
        "plan_identity": _jsonable(plan_identity),
        "common_identity": _jsonable(common_identity),
        "common_identity_sha256": next(iter(common_hashes)),
        "qualified_primal_gate": _jsonable(gate_identity),
        "qualified_primal_gate_sha256": next(iter(gate_hashes)),
        "partitions": partitions,
        "matrix_operator": {
            "global_shape": [
                reduced_global_size,
                reduced_global_size,
            ],
            "local_csr_by_rank": matrix_rows,
            "partition_bound_csr_sha256": matrix_partition_sha,
            "full_matrix_serialized": False,
        },
        "rank_bound_identity_sha256": _json_sha256(
            [
                {
                    "rank": int(row["rank"]),
                    "local_identity_sha256": row[
                        "local_identity_sha256"
                    ],
                }
                for row in rows
            ],
            namespace="task035e.current-rank-bound-identity.v1",
        ),
        "shards": shard_rows,
        "publication": (
            "atomic mode-0600 rank shards; independent rank replay; "
            "rank0 atomic mode-0600 manifest after all-rank verification"
        ),
        "no_full_vector_python_allgather": True,
        "full_matrix_persisted": False,
        "capability_credit": {
            "current_primal_snapshot_complete": True,
            "multi_goal_adjoint_complete": False,
            "dwr_complete": False,
            "local_h_transfer_complete": False,
            "shadow_effectivity_complete": False,
            "accuracy_credit": False,
        },
        "ordinary_default_changed": False,
    }
    return {
        **unsigned,
        "manifest_payload_sha256": _json_sha256(
            unsigned,
            namespace=_MANIFEST_HASH_NAMESPACE,
        ),
    }


def write_task035e_multigoal_snapshot(
    view: Any,
    *,
    artifact_directory: str | Path,
    source_sha: str,
    trial_id: str,
    cycle_index: int,
    expected_plan_sha256: str,
    allow_serial_test_fixture: bool = False,
) -> Task035eSnapshotReceipt:
    """Persist one immutable, partition-bound current-state live snapshot.

    Formal publication is MPI8-only.  ``allow_serial_test_fixture`` exists
    solely for lightweight component qualification; a serial artifact is
    explicitly marked non-formal and cannot be confused with MPI8 authority.
    """

    comm = view.mesh_data.mesh.comm
    source = _source_sha(source_sha)
    trial = _trial_id(trial_id)
    cycle = _cycle_index(cycle_index)
    plan_sha = _sha256(
        expected_plan_sha256,
        label="expected plan SHA-256",
    )
    formal_mpi8 = int(comm.size) == 8
    if not formal_mpi8 and not (
        int(comm.size) == 1 and allow_serial_test_fixture is True
    ):
        raise Task035eSnapshotError(
            "formal Task035e live snapshots require MPI8; only an explicitly "
            "marked serial test fixture is accepted otherwise"
        )
    request = {
        "source_sha": source,
        "trial_id": trial,
        "cycle_index": cycle,
        "expected_plan_sha256": plan_sha,
        "mpi_size": int(comm.size),
        "formal_mpi8_qualified": formal_mpi8,
    }
    request_hash = _json_sha256(
        request,
        namespace="task035e.current-snapshot-request.v1",
    )
    request_hashes = comm.allgather(request_hash)
    if len(set(request_hashes)) != 1:
        raise Task035eSnapshotError(
            "Task035e snapshot request differs across MPI ranks"
        )

    identity_payload = _collective_local_call(
        comm,
        "live snapshot identity validation",
        lambda: (
            _load_plan_identity(
                view,
                source_sha=source,
                cycle_index=cycle,
                expected_plan_sha256=plan_sha,
            ),
            {
                "config": _config_identity(view.config),
                "floquet": _floquet_identity(view.floquet_data),
                "reduction": _reduction_identity(view),
                "goal_context": _goal_context_identity(view.goal_context),
                "abi": _abi_identity(),
            },
            _qualified_gate_identity(view),
        ),
    )
    if identity_payload is None:
        raise Task035eSnapshotError("live snapshot identity is absent")
    plan_identity, common_identity, gate_identity = identity_payload
    common_identity_sha = _json_sha256(
        common_identity,
        namespace="task035e.current-common-identity.v1",
    )
    gate_identity_sha = _json_sha256(
        gate_identity,
        namespace="task035e.current-qualified-primal-gate.v1",
    )

    vector_preflight = _collective_local_call(
        comm,
        "live snapshot vector preflight",
        lambda: _snapshot_vector_preflight(view),
    )
    if vector_preflight is None:
        raise Task035eSnapshotError("live snapshot vectors are absent")
    (
        reduced_x,
        reduced_b,
        active_solution,
        active_rhs,
        active_auxiliary,
        active_auxiliary_present,
        p6_field,
        ranges,
        sizes,
    ) = vector_preflight

    ax_vector = view.x.duplicate()
    try:
        view.A.mult(view.x, ax_vector)
        reduced_ax, ax_range, ax_size = _vector_owned(
            ax_vector,
            label="reduced A*x",
        )
    finally:
        ax_vector.destroy()
    if ax_range != ranges["reduced"] or ax_size != sizes["reduced"]:
        raise Task035eSnapshotError(
            "reduced A*x ownership differs from x and b"
        )
    reduced_residual = np.ascontiguousarray(reduced_b - reduced_ax)
    local_norm_packet = np.asarray(
        [
            float(np.vdot(reduced_residual, reduced_residual).real),
            float(np.vdot(reduced_b, reduced_b).real),
        ],
        dtype=np.float64,
    )
    global_norm_packet = np.zeros(2, dtype=np.float64)
    comm.Allreduce(local_norm_packet, global_norm_packet, op=MPI.SUM)
    direct_residual_norm = float(math.sqrt(global_norm_packet[0]))
    direct_rhs_norm = float(math.sqrt(global_norm_packet[1]))
    direct_relative_residual = direct_residual_norm / max(
        direct_rhs_norm,
        np.finfo(float).tiny,
    )
    if not math.isfinite(direct_relative_residual) or (
        direct_relative_residual > 1.0e-9
    ):
        raise Task035eSnapshotError(
            "direct reduced b-A*x residual exceeds 1e-9"
        )
    gate_identity = {
        **gate_identity,
        "direct_reduced_residual": {
            "residual_sign": "b-A*x",
            "residual_l2_norm": direct_residual_norm,
            "rhs_l2_norm": direct_rhs_norm,
            "relative_residual": direct_relative_residual,
            "pass": True,
        },
    }
    gate_identity_sha = _json_sha256(
        gate_identity,
        namespace="task035e.current-qualified-primal-gate.v1",
    )
    matrix_identity = _collective_local_call(
        comm,
        "live snapshot local CSR identity",
        lambda: _local_matrix_csr_identity(view.A),
    )
    if matrix_identity is None:
        raise Task035eSnapshotError("local matrix CSR identity is absent")

    local_identity = {
        "request_sha256": request_hash,
        "common_identity_sha256": common_identity_sha,
        "gate_identity_sha256": gate_identity_sha,
        "rank": int(comm.rank),
        "mpi_size": int(comm.size),
        "ownership_ranges": {
            name: list(values) for name, values in ranges.items()
        },
        "matrix_local_csr_content_sha256": matrix_identity[
            "local_csr_content_sha256"
        ],
        "rank_local_reduction_identity": (
            _rank_local_reduction_identity(view)
        ),
    }
    local_identity_sha = _json_sha256(
        local_identity,
        namespace="task035e.current-local-identity.v1",
    )
    payload_arrays = {
        "reduced_x_owned": reduced_x,
        "reduced_b_owned": reduced_b,
        "reduced_ax_owned": reduced_ax,
        "reduced_residual_owned": reduced_residual,
        "active_full_solution_owned": active_solution,
        "active_full_rhs_owned": active_rhs,
        "active_full_auxiliary_action_owned": active_auxiliary,
        "p6_recovered_field_owned": p6_field,
    }
    array_metadata = {
        name: _array_metadata(values, name=name)
        for name, values in payload_arrays.items()
    }
    shard_unsigned = {
        "schema_version": SHARD_SCHEMA,
        "rank": int(comm.rank),
        "mpi_size": int(comm.size),
        "ownership_ranges": {
            name: list(values) for name, values in ranges.items()
        },
        "active_auxiliary_action_present": active_auxiliary_present,
        "local_identity_sha256": local_identity_sha,
        "arrays": array_metadata,
    }
    shard_payload_sha = _json_sha256(
        shard_unsigned,
        namespace=_SHARD_HASH_NAMESPACE,
    )
    shard_arrays = {
        "schema_version": np.asarray([SHARD_SCHEMA], dtype=np.str_),
        "rank": np.asarray([comm.rank], dtype=np.int64),
        "mpi_size": np.asarray([comm.size], dtype=np.int64),
        "reduced_ownership_range": np.asarray(
            ranges["reduced"], dtype=np.int64
        ),
        "active_full_ownership_range": np.asarray(
            ranges["active_full"], dtype=np.int64
        ),
        "p6_field_ownership_range": np.asarray(
            ranges["p6_field"], dtype=np.int64
        ),
        "active_auxiliary_action_present": np.asarray(
            [int(active_auxiliary_present)], dtype=np.int8
        ),
        **payload_arrays,
        "local_identity_sha256": np.asarray(
            [local_identity_sha], dtype="U64"
        ),
        "shard_payload_sha256": np.asarray(
            [shard_payload_sha], dtype="U64"
        ),
    }

    output = Path(artifact_directory).expanduser().resolve()
    prepare_error = None
    if comm.rank == 0:
        try:
            output.mkdir(parents=True, exist_ok=False, mode=0o700)
        except Exception as exc:
            prepare_error = {
                "exception_type": type(exc).__name__,
                "message": str(exc),
            }
    prepare_error = comm.bcast(prepare_error, root=0)
    if prepare_error is not None:
        raise Task035eSnapshotError(
            f"snapshot directory preparation failed: {prepare_error}"
        )
    comm.Barrier()
    shard_path = output / f"rank{comm.rank:04d}.npz"

    def write_and_replay_local_shard() -> dict[str, Any]:
        _atomic_npz(shard_path, shard_arrays)
        _arrays, metadata = _read_shard(
            shard_path,
            rank=int(comm.rank),
            mpi_size=int(comm.size),
            expected_file_sha256=None,
            expected_metadata=None,
        )
        metadata["common_identity_sha256"] = common_identity_sha
        metadata["gate_identity_sha256"] = gate_identity_sha
        metadata["matrix_local_csr"] = matrix_identity
        metadata["global_sizes"] = dict(sizes)
        return metadata

    local_metadata = _collective_local_call(
        comm,
        "snapshot shard publication and independent replay",
        write_and_replay_local_shard,
    )
    if local_metadata is None:
        raise Task035eSnapshotError("snapshot shard metadata is absent")
    rows = comm.gather(local_metadata, root=0)
    publication = None
    publication_error = None
    if comm.rank == 0:
        try:
            if rows is None:
                raise RuntimeError("root did not receive shard metadata")
            size_packets = {
                (
                    int(row["global_sizes"]["reduced"]),
                    int(row["global_sizes"]["active_full"]),
                    int(row["global_sizes"]["p6_field"]),
                )
                for row in rows
            }
            if len(size_packets) != 1:
                raise ValueError("snapshot global vector sizes differ by rank")
            reduced_size, active_size, p6_size = size_packets.pop()
            manifest = _manifest_payload(
                rows=rows,
                source_sha=source,
                trial_id=trial,
                cycle_index=cycle,
                plan_identity=plan_identity,
                common_identity=common_identity,
                gate_identity=gate_identity,
                reduced_global_size=reduced_size,
                active_global_size=active_size,
                p6_global_size=p6_size,
                formal_mpi8_qualified=formal_mpi8,
            )
            manifest_path = output / "manifest.json"
            _atomic_json(manifest_path, manifest)
            publication = {
                "path": str(manifest_path),
                "file_sha256": _file_sha256(manifest_path),
                "payload_sha256": manifest["manifest_payload_sha256"],
            }
        except Exception as exc:
            publication_error = {
                "exception_type": type(exc).__name__,
                "message": str(exc),
            }
    publication_error = comm.bcast(publication_error, root=0)
    publication = comm.bcast(publication, root=0)
    if publication_error is not None or publication is None:
        raise Task035eSnapshotError(
            f"snapshot manifest publication failed: {publication_error}"
        )

    replay_error = None
    try:
        load_task035e_multigoal_snapshot(
            publication["path"],
            expected_manifest_file_sha256=publication["file_sha256"],
            communicator=comm,
        )
    except Exception as exc:
        replay_error = {
            "rank": int(comm.rank),
            "exception_type": type(exc).__name__,
            "message": str(exc),
        }
    replay_errors = [
        row for row in comm.allgather(replay_error) if row is not None
    ]
    if replay_errors:
        raise Task035eSnapshotError(
            "published snapshot failed independent all-rank replay: "
            + json.dumps(replay_errors, sort_keys=True)
        )
    return Task035eSnapshotReceipt(
        manifest_path=Path(publication["path"]),
        manifest_file_sha256=str(publication["file_sha256"]),
        manifest_payload_sha256=str(publication["payload_sha256"]),
        source_sha=source,
        trial_id=trial,
        cycle_index=cycle,
        plan_file_sha256=plan_sha,
        mpi_size=int(comm.size),
        formal_mpi8_qualified=formal_mpi8,
    )


def _snapshot_vector_preflight(view: Any) -> tuple[Any, ...]:
    if tuple(map(int, view.A.getSize())) != (
        int(view.x.getSize()),
        int(view.x.getSize()),
    ):
        raise ValueError("live reduced matrix and solution sizes differ")
    if int(view.b.getSize()) != int(view.x.getSize()):
        raise ValueError("live reduced RHS and solution sizes differ")
    recovered = view.recovered
    if (
        not isinstance(recovered.audit, Mapping)
        or recovered.audit.get("pass") is not True
    ):
        raise ValueError("recovered variable-p solution audit did not pass")
    if (
        recovered.active_full_solution is None
        or recovered.active_full_rhs is None
    ):
        raise ValueError("recovered active-full solution or RHS is absent")
    p6_vector = view.field.x.petsc_vec
    recovered_field = getattr(recovered, "field", None)
    if recovered_field is not view.field:
        raise ValueError("live and recovered p6 field objects differ")

    reduced_x, reduced_range, reduced_size = _vector_owned(
        view.x, label="reduced solution"
    )
    reduced_b, rhs_range, rhs_size = _vector_owned(
        view.b, label="reduced RHS"
    )
    if rhs_range != reduced_range or rhs_size != reduced_size:
        raise ValueError("reduced x and b ownership differs")
    active_solution, active_range, active_size = _vector_owned(
        recovered.active_full_solution,
        label="active-full solution",
    )
    active_rhs, active_rhs_range, active_rhs_size = _vector_owned(
        recovered.active_full_rhs,
        label="active-full RHS",
    )
    if (
        active_rhs_range != active_range
        or active_rhs_size != active_size
    ):
        raise ValueError("active-full solution and RHS ownership differs")
    expected_active_size = int(
        view.reduction.system.entity_map.active_rows
    )
    if active_size != expected_active_size:
        raise ValueError("active-full vectors and entity map sizes differ")
    active_auxiliary_present = (
        recovered.active_auxiliary_interior_action is not None
    )
    if active_auxiliary_present:
        active_auxiliary, auxiliary_range, auxiliary_size = _vector_owned(
            recovered.active_auxiliary_interior_action,
            label="active-full auxiliary action",
        )
        if auxiliary_range != active_range or auxiliary_size != active_size:
            raise ValueError(
                "active-full auxiliary action ownership differs"
            )
    else:
        active_auxiliary = np.zeros_like(active_solution)
    p6_field, p6_range, p6_size = _vector_owned(
        p6_vector,
        label="p6 recovered field",
    )
    return (
        reduced_x,
        reduced_b,
        active_solution,
        active_rhs,
        active_auxiliary,
        active_auxiliary_present,
        p6_field,
        {
            "reduced": reduced_range,
            "active_full": active_range,
            "p6_field": p6_range,
        },
        {
            "reduced": reduced_size,
            "active_full": active_size,
            "p6_field": p6_size,
        },
    )


def load_task035e_multigoal_snapshot(
    manifest_path: str | Path,
    *,
    expected_manifest_file_sha256: str,
    communicator: MPI.Intracomm = MPI.COMM_WORLD,
) -> LoadedTask035eSnapshot:
    """Independently verify the manifest and this rank's immutable shard.

    The loader performs no MPI collective.  Each rank can therefore validate
    its own evidence without trusting a root-computed pass flag.
    """

    path = Path(manifest_path).expanduser().resolve()
    expected_file_sha = _sha256(
        expected_manifest_file_sha256,
        label="expected manifest file SHA-256",
    )
    if not path.is_file():
        raise FileNotFoundError(f"snapshot manifest is absent: {path}")
    _require_mode_0600(path, label="snapshot manifest")
    observed_file_sha = _file_sha256(path)
    if observed_file_sha != expected_file_sha:
        raise ValueError("snapshot manifest file SHA-256 differs")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if (
        manifest.get("schema_version") != SNAPSHOT_SCHEMA
        or manifest.get("status")
        != "multigoal_current_live_snapshot_pass"
        or manifest.get("pass") is not True
        or manifest.get("role") != "current_blind_state"
    ):
        raise ValueError("snapshot manifest authority is invalid")
    stored_payload_sha = _sha256(
        manifest.get("manifest_payload_sha256"),
        label="manifest payload SHA-256",
    )
    unsigned = dict(manifest)
    unsigned.pop("manifest_payload_sha256")
    if (
        _json_sha256(unsigned, namespace=_MANIFEST_HASH_NAMESPACE)
        != stored_payload_sha
    ):
        raise ValueError("snapshot manifest payload self-hash differs")
    mpi_size = int(manifest.get("mpi_size", -1))
    if mpi_size != int(communicator.size):
        raise ValueError("snapshot manifest MPI size differs from the loader")
    if mpi_size == 8:
        if manifest.get("formal_mpi8_qualified") is not True:
            raise ValueError("MPI8 snapshot is not marked formally qualified")
    elif (
        mpi_size != 1
        or manifest.get("formal_mpi8_qualified") is not False
        or manifest.get("diagnostic_serial_fixture") is not True
    ):
        raise ValueError("non-MPI8 snapshot is not a serial test fixture")
    source = _source_sha(manifest.get("source_sha"))
    _trial_id(manifest.get("trial_id"))
    cycle = _cycle_index(manifest.get("cycle_index"))
    plan = manifest.get("plan_identity")
    plan_payload = None
    plan_path_value = None if not isinstance(plan, Mapping) else plan.get("path")
    if plan_path_value is not None:
        plan_path_value = Path(plan_path_value).expanduser().resolve()
        if plan_path_value.is_file():
            plan_payload = json.loads(
                plan_path_value.read_text(encoding="utf-8")
            )
    if (
        not isinstance(plan, Mapping)
        or plan_path_value is None
        or plan_payload is None
        or _sha256(
            plan.get("file_sha256"),
            label="manifest plan SHA-256",
        )
        != _file_sha256(plan_path_value)
        or _sha256(
            plan.get("payload_sha256"),
            label="manifest plan payload SHA-256",
        )
        != _json_sha256(
            plan_payload,
            namespace="task035e.executed-plan-payload.v1",
        )
    ):
        raise ValueError("snapshot manifest executed-plan binding differs")
    provenance = plan_payload.get("provenance")
    provenance_cycle = (
        None if not isinstance(provenance, Mapping) else provenance.get("cycle_index")
    )
    if (
        not isinstance(provenance, Mapping)
        or provenance.get("source_sha") != source
        or (
            provenance_cycle is None
            and (
                cycle != 0
                or provenance.get("schema_version")
                != "task035e.blind-initial-provenance.v1"
            )
        )
        or (
            provenance_cycle is not None
            and (
                type(provenance_cycle) is not int
                or provenance_cycle != cycle
            )
        )
    ):
        raise ValueError("snapshot manifest plan provenance differs")
    common_identity = manifest.get("common_identity")
    gate_identity = manifest.get("qualified_primal_gate")
    if (
        not isinstance(common_identity, Mapping)
        or not isinstance(gate_identity, Mapping)
        or _json_sha256(
            common_identity,
            namespace="task035e.current-common-identity.v1",
        )
        != _sha256(
            manifest.get("common_identity_sha256"),
            label="manifest common identity SHA-256",
        )
        or _json_sha256(
            gate_identity,
            namespace="task035e.current-qualified-primal-gate.v1",
        )
        != _sha256(
            manifest.get("qualified_primal_gate_sha256"),
            label="manifest primal Gate SHA-256",
        )
    ):
        raise ValueError("snapshot manifest common or primal identity differs")
    capability = manifest.get("capability_credit")
    if (
        not isinstance(capability, Mapping)
        or capability.get("current_primal_snapshot_complete") is not True
        or any(
            capability.get(name) is not False
            for name in (
                "multi_goal_adjoint_complete",
                "dwr_complete",
                "local_h_transfer_complete",
                "shadow_effectivity_complete",
                "accuracy_credit",
            )
        )
    ):
        raise ValueError("snapshot manifest overclaims capability")
    if (
        manifest.get("no_full_vector_python_allgather") is not True
        or manifest.get("full_matrix_persisted") is not False
        or manifest.get("matrix_operator", {}).get(
            "full_matrix_serialized"
        )
        is not False
    ):
        raise ValueError("snapshot storage contract is invalid")
    shards = manifest.get("shards")
    if not isinstance(shards, list) or len(shards) != mpi_size:
        raise ValueError("snapshot manifest shard catalog is incomplete")
    if [int(row.get("rank", -1)) for row in shards] != list(
        range(mpi_size)
    ):
        raise ValueError("snapshot manifest shard ranks are incomplete")
    partitions = manifest.get("partitions")
    if not isinstance(partitions, Mapping):
        raise ValueError("snapshot manifest has no partition authority")
    family_specs = {
        "reduced": (
            "reduced",
            (
                "reduced_x_owned",
                "reduced_b_owned",
                "reduced_ax_owned",
                "reduced_residual_owned",
            ),
        ),
        "active_full": (
            "active_full",
            (
                "active_full_solution_owned",
                "active_full_rhs_owned",
                "active_full_auxiliary_action_owned",
            ),
        ),
        "p6_recovered_field": (
            "p6_field",
            ("p6_recovered_field_owned",),
        ),
    }
    for partition_name, (family, array_names) in family_specs.items():
        partition = partitions.get(partition_name)
        if not isinstance(partition, Mapping):
            raise ValueError(
                f"snapshot partition {partition_name} is absent"
            )
        ranges = _ownership_catalog(
            shards,
            family=family,
            global_size=int(partition.get("global_size", -1)),
        )
        if ranges != partition.get("ownership_ranges"):
            raise ValueError(
                f"snapshot partition {partition_name} ranges differ"
            )
        hashes = partition.get("partition_bound_array_sha256")
        if not isinstance(hashes, Mapping):
            raise ValueError(
                f"snapshot partition {partition_name} hashes are absent"
            )
        for array_name in array_names:
            if (
                _partition_array_hash(
                    shards,
                    family=family,
                    array_name=array_name,
                )
                != _sha256(
                    hashes.get(array_name),
                    label=f"{array_name} partition SHA-256",
                )
            ):
                raise ValueError(
                    f"snapshot partition hash differs for {array_name}"
                )
    matrix_operator = manifest.get("matrix_operator")
    matrix_rows = (
        None
        if not isinstance(matrix_operator, Mapping)
        else matrix_operator.get("local_csr_by_rank")
    )
    if not isinstance(matrix_rows, list) or len(matrix_rows) != mpi_size:
        raise ValueError("snapshot matrix partition catalog is incomplete")
    matrix_partition_sha = _json_sha256(
        [
            {"rank": index, **dict(row)}
            for index, row in enumerate(matrix_rows)
        ],
        namespace="task035e.current-matrix-partition-bound-csr.v1",
    )
    if matrix_partition_sha != _sha256(
        matrix_operator.get("partition_bound_csr_sha256"),
        label="matrix partition CSR SHA-256",
    ):
        raise ValueError("snapshot matrix partition CSR hash differs")
    rank_bound_sha = _json_sha256(
        [
            {
                "rank": int(row["rank"]),
                "local_identity_sha256": row[
                    "local_identity_sha256"
                ],
            }
            for row in shards
        ],
        namespace="task035e.current-rank-bound-identity.v1",
    )
    if rank_bound_sha != _sha256(
        manifest.get("rank_bound_identity_sha256"),
        label="rank-bound identity SHA-256",
    ):
        raise ValueError("snapshot rank-bound identity hash differs")
    rank = int(communicator.rank)
    entry = shards[rank]
    if int(entry.get("rank", -1)) != rank:
        raise ValueError("snapshot manifest shard order differs from rank")
    expected_name = f"rank{rank:04d}.npz"
    if entry.get("path") != expected_name:
        raise ValueError("snapshot shard filename is not canonical")
    shard_path = (path.parent / expected_name).resolve()
    if shard_path.parent != path.parent:
        raise ValueError("snapshot shard escaped its manifest directory")
    arrays, _metadata = _read_shard(
        shard_path,
        rank=rank,
        mpi_size=mpi_size,
        expected_file_sha256=_sha256(
            entry.get("file_sha256"),
            label="manifest shard file SHA-256",
        ),
        expected_metadata=entry,
    )
    readonly_arrays: dict[str, np.ndarray] = {}
    for name, values in arrays.items():
        copied = np.asarray(values).copy()
        copied.setflags(write=False)
        readonly_arrays[name] = copied
    return LoadedTask035eSnapshot(
        manifest_path=path,
        manifest_file_sha256=observed_file_sha,
        shard_path=shard_path,
        manifest=MappingProxyType(manifest),
        arrays=MappingProxyType(readonly_arrays),
    )


def build_task035e_multigoal_snapshot_observer(
    **kwargs: Any,
) -> Callable[[Any], None]:
    """Return the explicit opt-in live callback for snapshot publication."""

    def observer(view: Any) -> None:
        write_task035e_multigoal_snapshot(view, **kwargs)

    return observer


__all__ = [
    "LoadedTask035eSnapshot",
    "SHARD_SCHEMA",
    "SNAPSHOT_SCHEMA",
    "Task035eSnapshotError",
    "Task035eSnapshotReceipt",
    "build_task035e_multigoal_snapshot_observer",
    "load_task035e_multigoal_snapshot",
    "write_task035e_multigoal_snapshot",
]
