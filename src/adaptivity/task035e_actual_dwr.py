"""Actual live-shadow multi-goal DWR kernel for Task035e.

The caller supplies a qualified shadow ``Stage4VariablePLiveView``, a current
primal vector that has already been injected into the shadow reduced layout,
and one complex gradient vector for each of the 59 frozen real goals.  This
module then performs the actual algebra

``r = b_shadow - A_shadow x_current``

``A_shadow^H z_J = g_J``

``eta_J = Re(z_J^H r)``

using the borrowed shadow factorization.  It neither synthesizes gradients nor
uses an endpoint goal difference.  It also does not perform p/h transfer; that
is a prerequisite owned by the caller.

Distributed vectors and matrices remain distributed.  Content identities are
formed from owner-local arrays and fixed-size native MPI metadata reductions;
there is no Python full-vector gather or allgather.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
import math
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping

from mpi4py import MPI
import numpy as np
from petsc4py import PETSc

from .blind_controller.contracts import (
    FORMAL_GOAL_IDS,
    FORMAL_GOAL_INVENTORY_SHA256,
)
from .stage4_local_h import (
    stage4_multilevel_local_h_forest_catalog,
)
from .task035e_hp_transition import canonical_hp_cell_target_id


ACTUAL_DWR_SCHEMA = "task035e.actual-live-shadow-dwr.v1"
CELLWISE_DWR_PARTITION_SCHEMA = (
    "task035e.cellwise-signed-dwr-partition.v1"
)
_SOURCE_RE = re.compile(r"[0-9a-f]{40}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_COMPLEX_DTYPE = np.dtype("<c16")
_INTEGER_DTYPE = np.dtype("<i8")
_FLOAT_DTYPE = np.dtype("<f8")


class Task035eActualDWRError(RuntimeError):
    """Fail-closed actual shadow-DWR failure."""


@dataclass(frozen=True, slots=True)
class Task035eActualDWRResult:
    """Immutable self-hashed DWR report and ordered signed estimates."""

    report: Mapping[str, Any]
    report_sha256: str
    signed_eta: Mapping[str, float]
    cellwise_partition: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class _CellwiseRowPartition:
    """One exact reduced-row designation over the current leaf catalog."""

    target_ids: tuple[str, ...]
    current_leaf_keys: tuple[tuple[int, int, int, int, int], ...]
    current_leaf_boxes: tuple[tuple[float, ...], ...]
    current_leaf_degrees: tuple[int, ...]
    row_to_leaf: np.ndarray
    independent_trace_rows: int
    current_plan_identity: Mapping[str, Any]
    shadow_plan_identity: Mapping[str, Any]
    designation_identity: Mapping[str, Any]


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
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("DWR evidence contains a non-finite float")
        return value
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise TypeError(
        "DWR evidence contains a non-canonical object: "
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
    else:
        raise TypeError(f"unsupported DWR array dtype: {array.dtype}")
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


def _collective_local_validation(
    communicator: MPI.Intracomm,
    phase: str,
    operation: Any,
) -> Any:
    """Run local validation and reduce only a scalar failure count."""

    result = None
    local_message = None
    try:
        result = operation()
    except Exception as exc:
        local_message = f"{type(exc).__name__}: {exc}"
    failures = int(
        communicator.allreduce(
            int(local_message is not None),
            op=MPI.SUM,
        )
    )
    if failures:
        detail = (
            f"; this-rank={local_message}"
            if local_message is not None
            else "; failure occurred on another rank"
        )
        raise Task035eActualDWRError(
            f"{phase} failed on {failures} rank(s){detail}"
        )
    return result


def _require_collectively_identical_sha256(
    communicator: MPI.Intracomm,
    digest: str,
    *,
    label: str,
) -> None:
    raw = np.frombuffer(bytes.fromhex(digest), dtype=np.uint8)
    minimum = np.empty_like(raw)
    maximum = np.empty_like(raw)
    communicator.Allreduce(raw, minimum, op=MPI.MIN)
    communicator.Allreduce(raw, maximum, op=MPI.MAX)
    if not np.array_equal(minimum, maximum):
        raise Task035eActualDWRError(
            f"{label} differs across MPI ranks"
        )


def _native_rank_digest_catalog(
    communicator: MPI.Intracomm,
    local_digest: str,
) -> tuple[str, ...]:
    """Replicate one 32-byte digest per rank with a native buffer reduction."""

    _sha256(local_digest, label="rank-local content digest")
    send = np.zeros((communicator.size, 32), dtype=np.uint8)
    send[communicator.rank, :] = np.frombuffer(
        bytes.fromhex(local_digest), dtype=np.uint8
    )
    received = np.zeros_like(send)
    communicator.Allreduce(send, received, op=MPI.SUM)
    return tuple(bytes(row).hex() for row in received)


def _native_ownership_ranges(
    communicator: MPI.Intracomm,
    ownership_range: tuple[int, int],
    *,
    global_size: int,
) -> tuple[tuple[int, int], ...]:
    send = np.full((communicator.size, 2), -1, dtype=np.int64)
    send[communicator.rank, :] = ownership_range
    received = np.full_like(send, -1)
    communicator.Allreduce(send, received, op=MPI.MAX)
    ranges = tuple(tuple(map(int, row)) for row in received)
    cursor = 0
    for rank, (start, end) in enumerate(ranges):
        if start != cursor or end < start:
            raise Task035eActualDWRError(
                f"distributed ownership is invalid at rank {rank}"
            )
        cursor = end
    if cursor != int(global_size):
        raise Task035eActualDWRError(
            "distributed ownership does not close global size"
        )
    return ranges


def _owned_vector_values(
    vector: PETSc.Vec,
    *,
    label: str,
) -> tuple[np.ndarray, tuple[int, int], int]:
    start, end = map(int, vector.getOwnershipRange())
    values = np.asarray(
        vector.getArray(readonly=True), dtype=_COMPLEX_DTYPE
    ).copy()
    if values.ndim != 1 or len(values) != end - start:
        raise ValueError(f"{label} owned array and ownership differ")
    if not np.all(np.isfinite(values)):
        raise ValueError(f"{label} contains non-finite values")
    return np.ascontiguousarray(values), (start, end), int(vector.getSize())


def _vector_partition_identity(
    vector: PETSc.Vec,
    communicator: MPI.Intracomm,
    *,
    namespace: str,
) -> dict[str, Any]:
    values, ownership, global_size = _owned_vector_values(
        vector,
        label=namespace,
    )
    local_payload = {
        "rank": int(communicator.rank),
        "mpi_size": int(communicator.size),
        "global_size": global_size,
        "ownership_range": list(ownership),
        "owned_values_sha256": _array_sha256(
            values,
            namespace=f"{namespace}.owned-values",
        ),
    }
    local_digest = _json_sha256(
        local_payload,
        namespace=f"{namespace}.rank-partition",
    )
    rank_digests = _native_rank_digest_catalog(
        communicator, local_digest
    )
    ranges = _native_ownership_ranges(
        communicator,
        ownership,
        global_size=global_size,
    )
    return {
        "global_size": global_size,
        "ownership_ranges": [list(row) for row in ranges],
        "rank_local_content_sha256": list(rank_digests),
        "partition_bound_sha256": _json_sha256(
            {
                "global_size": global_size,
                "ownership_ranges": [list(row) for row in ranges],
                "rank_local_content_sha256": list(rank_digests),
            },
            namespace=f"{namespace}.global-partition",
        ),
    }


def _local_matrix_csr_payload(
    matrix: PETSc.Mat,
    *,
    rank: int,
) -> dict[str, Any]:
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
        raise ValueError("shadow operator local CSR is inconsistent")
    return {
        "rank": int(rank),
        "global_shape": list(map(int, matrix.getSize())),
        "row_ownership_range": [row_start, row_end],
        "column_ownership_range": [column_start, column_end],
        "local_nnz": len(values),
        "indptr_sha256": _array_sha256(
            indptr,
            namespace="task035e.actual-dwr.matrix-indptr.v1",
        ),
        "indices_sha256": _array_sha256(
            indices,
            namespace="task035e.actual-dwr.matrix-indices.v1",
        ),
        "values_sha256": _array_sha256(
            values,
            namespace="task035e.actual-dwr.matrix-values.v1",
        ),
    }


def _matrix_partition_identity(
    matrix: PETSc.Mat,
    communicator: MPI.Intracomm,
    *,
    local_payload: Mapping[str, Any],
) -> dict[str, Any]:
    local_digest = _json_sha256(
        local_payload,
        namespace="task035e.actual-dwr.matrix-local-csr.v1",
    )
    rank_digests = _native_rank_digest_catalog(
        communicator, local_digest
    )
    ranges = _native_ownership_ranges(
        communicator,
        tuple(map(int, local_payload["row_ownership_range"])),
        global_size=int(matrix.getSize()[0]),
    )
    local_nnz = np.asarray(
        [int(local_payload["local_nnz"])], dtype=np.int64
    )
    total_nnz = np.zeros(1, dtype=np.int64)
    communicator.Allreduce(local_nnz, total_nnz, op=MPI.SUM)
    identity = {
        "global_shape": list(map(int, matrix.getSize())),
        "row_ownership_ranges": [list(row) for row in ranges],
        "matrix_type": str(matrix.getType()),
        "global_nnz": int(total_nnz[0]),
        "rank_local_csr_sha256": list(rank_digests),
        "full_matrix_serialized": False,
    }
    identity["partition_bound_csr_sha256"] = _json_sha256(
        identity,
        namespace="task035e.actual-dwr.matrix-partition.v1",
    )
    return identity


def _plan_identity(
    view: Any,
    *,
    source_sha: str,
    expected_plan_sha256: str,
) -> dict[str, Any]:
    context = getattr(view.mesh_data, "local_h_context", None)
    if context is None:
        raise ValueError("actual DWR requires an executed shadow plan")
    path = Path(context.plan_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"shadow plan is absent: {path}")
    observed_sha = _file_sha256(path)
    if (
        observed_sha != expected_plan_sha256
        or str(context.plan_file_sha256).lower() != observed_sha
    ):
        raise ValueError(
            "expected, on-disk, and executed shadow plan hashes differ"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        payload.get("schema_version")
        != "task035e.stage4-multilevel-local-h-refinement-plan.v1"
        or payload.get("status")
        != "stage4_balanced_multilevel_local_h_plan"
        or payload.get("variable_trace_from_cell_degrees") is not True
    ):
        raise ValueError("shadow plan is not a Task035e h/p plan")
    provenance = payload.get("provenance")
    if (
        not isinstance(provenance, Mapping)
        or provenance.get("source_sha") != source_sha
    ):
        raise ValueError("shadow plan provenance source differs")
    expected_forest = payload.get("expected_forest")
    if not isinstance(expected_forest, Mapping):
        raise ValueError("shadow plan has no forest authority")
    plan_forest_sha = _sha256(
        expected_forest.get("leaf_catalog_sha256"),
        label="plan forest SHA-256",
    )
    plan_degree_sha = _sha256(
        payload.get("cell_interior_degree_plan_sha256"),
        label="plan degree SHA-256",
    )
    forest_audit = getattr(context.forest, "audit", None)
    degree_audit = getattr(view.reduction.degree_plan, "audit", None)
    if not isinstance(forest_audit, Mapping) or not isinstance(
        degree_audit, Mapping
    ):
        raise ValueError("shadow forest or degree audit is absent")
    forest_sha = _sha256(
        forest_audit.get("leaf_catalog_sha256"),
        label="executed forest SHA-256",
    )
    degree_sha = _sha256(
        degree_audit.get("cell_degree_plan_sha256"),
        label="executed degree SHA-256",
    )
    if forest_sha != plan_forest_sha or degree_sha != plan_degree_sha:
        raise ValueError(
            "shadow plan, forest, and degree-map identities differ"
        )
    return {
        "path": str(path),
        "file_sha256": observed_sha,
        "payload_sha256": _json_sha256(
            payload,
            namespace="task035e.actual-dwr.shadow-plan-payload.v1",
        ),
        "provenance_sha256": _json_sha256(
            provenance,
            namespace="task035e.actual-dwr.shadow-plan-provenance.v1",
        ),
        "provenance_schema_version": provenance.get("schema_version"),
        "provenance_cycle_index": provenance.get("cycle_index"),
        "forest_leaf_catalog_sha256": forest_sha,
        "cell_degree_plan_sha256": degree_sha,
    }


def _plan_refinement_stages(
    payload: Mapping[str, Any],
) -> tuple[tuple[tuple[float, ...], ...], ...]:
    raw_stages = payload.get("refinement_stages")
    if (
        not isinstance(raw_stages, list)
        or not 1 <= len(raw_stages) <= 6
    ):
        raise ValueError(
            "current plan has no complete Task035e refinement stages"
        )
    stages: list[tuple[tuple[float, ...], ...]] = []
    for stage_index, raw_stage in enumerate(raw_stages):
        if not isinstance(raw_stage, Mapping):
            raise ValueError(
                f"current plan refinement stage {stage_index} is malformed"
            )
        raw_marks = raw_stage.get("marked_leaves")
        if not isinstance(raw_marks, list) or not raw_marks:
            raise ValueError(
                f"current plan refinement stage {stage_index} has no marks"
            )
        marks: list[tuple[float, ...]] = []
        for mark_index, raw_mark in enumerate(raw_marks):
            if not isinstance(raw_mark, Mapping):
                raise ValueError(
                    "current plan refinement mark is malformed: "
                    f"stage={stage_index}, mark={mark_index}"
                )
            lower = raw_mark.get("lower")
            upper = raw_mark.get("upper")
            if (
                not isinstance(lower, list)
                or not isinstance(upper, list)
                or len(lower) != 3
                or len(upper) != 3
            ):
                raise ValueError(
                    "current plan refinement mark lacks two 3D corners"
                )
            box = tuple(
                round(float(value), 12)
                for value in (*lower, *upper)
            )
            if (
                not all(math.isfinite(value) for value in box)
                or any(box[axis] >= box[axis + 3] for axis in range(3))
            ):
                raise ValueError(
                    "current plan refinement mark has an invalid box"
                )
            marks.append(box)
        if len(set(marks)) != len(marks):
            raise ValueError(
                "current plan refinement stage repeats one leaf"
            )
        stages.append(tuple(marks))
    return tuple(stages)


def _plan_cell_degree_by_box(
    payload: Mapping[str, Any],
) -> dict[tuple[float, ...], int]:
    raw_rows = payload.get("cell_interior_degrees")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ValueError(
            "current plan lacks its complete p4/p5/p6 cell catalog"
        )
    result: dict[tuple[float, ...], int] = {}
    for row_index, raw_row in enumerate(raw_rows):
        if not isinstance(raw_row, Mapping):
            raise ValueError(
                f"current plan degree row {row_index} is malformed"
            )
        lower = raw_row.get("lower")
        upper = raw_row.get("upper")
        degree = raw_row.get("degree")
        if (
            not isinstance(lower, list)
            or not isinstance(upper, list)
            or len(lower) != 3
            or len(upper) != 3
            or type(degree) is not int
            or degree not in {4, 5, 6}
        ):
            raise ValueError(
                f"current plan degree row {row_index} is invalid"
            )
        box = tuple(
            round(float(value), 12) for value in (*lower, *upper)
        )
        if (
            not all(math.isfinite(value) for value in box)
            or any(box[axis] >= box[axis + 3] for axis in range(3))
            or box in result
        ):
            raise ValueError(
                f"current plan degree row {row_index} repeats/invalidates a box"
            )
        result[box] = int(degree)
    return result


def _current_leaf_authority(
    view: Any,
    *,
    source_sha: str,
    current_plan_path: str | Path,
    expected_current_plan_sha256: str,
) -> tuple[Any, tuple[int, ...], dict[str, Any]]:
    """Replay the current forest and bind every controller target ID."""

    path = Path(current_plan_path).expanduser().resolve()
    if not path.is_file():
        raise FileNotFoundError(f"current plan is absent: {path}")
    expected_sha = _sha256(
        expected_current_plan_sha256,
        label="expected current plan SHA-256",
    )
    observed_sha = _file_sha256(path)
    if observed_sha != expected_sha:
        raise ValueError(
            "current plan file SHA-256 differs from the immutable snapshot"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    if (
        not isinstance(payload, Mapping)
        or payload.get("schema_version")
        != "task035e.stage4-multilevel-local-h-refinement-plan.v1"
        or payload.get("status")
        != "stage4_balanced_multilevel_local_h_plan"
        or payload.get("variable_trace_from_cell_degrees") is not True
    ):
        raise ValueError("current plan is not a Task035e h/p solver plan")
    provenance = payload.get("provenance")
    if (
        not isinstance(provenance, Mapping)
        or provenance.get("source_sha") != source_sha
    ):
        raise ValueError("current plan provenance source differs")
    comm = view.mesh_data.mesh.comm
    forest = stage4_multilevel_local_h_forest_catalog(
        view.config,
        _plan_refinement_stages(payload),
        comm_size=int(comm.size),
    )
    expected_forest = payload.get("expected_forest")
    if not isinstance(expected_forest, Mapping):
        raise ValueError("current plan has no forest identity")
    leaf_catalog_sha = _sha256(
        expected_forest.get("leaf_catalog_sha256"),
        label="current plan leaf catalog SHA-256",
    )
    if forest.audit.get("leaf_catalog_sha256") != leaf_catalog_sha:
        raise ValueError(
            "replayed current forest differs from its plan identity"
        )
    degree_by_box = _plan_cell_degree_by_box(payload)
    forest_boxes = {
        tuple(round(float(value), 12) for value in cell.box)
        for cell in forest.leaves
    }
    if set(degree_by_box) != forest_boxes:
        raise ValueError(
            "current degree catalog does not cover the replayed forest"
        )
    degrees = tuple(
        degree_by_box[
            tuple(round(float(value), 12) for value in cell.box)
        ]
        for cell in forest.leaves
    )
    base_config = payload.get("base_config")
    if not isinstance(base_config, Mapping):
        raise ValueError("current plan has no base geometry identity")
    domain_z_min = float(base_config.get("domain_z_min"))
    domain_z_max = float(base_config.get("domain_z_max"))
    if (
        not math.isfinite(domain_z_min)
        or not math.isfinite(domain_z_max)
        or domain_z_min >= domain_z_max
    ):
        raise ValueError("current plan domain z bounds are invalid")
    identity = {
        "path": str(path),
        "file_sha256": observed_sha,
        "payload_sha256": _json_sha256(
            payload,
            namespace="task035e.actual-dwr.current-plan-payload.v1",
        ),
        "provenance_sha256": _json_sha256(
            provenance,
            namespace="task035e.actual-dwr.current-plan-provenance.v1",
        ),
        "forest_leaf_catalog_sha256": leaf_catalog_sha,
        "cell_degree_plan_sha256": _sha256(
            payload.get("cell_interior_degree_plan_sha256"),
            label="current cell-degree plan SHA-256",
        ),
        "leaf_count": len(forest.leaves),
        "domain_z_min": domain_z_min,
        "domain_z_max": domain_z_max,
    }
    return forest, degrees, identity


def _box_contains(
    outer: tuple[float, ...],
    inner: tuple[float, ...],
) -> bool:
    scale = max(
        1.0,
        *(abs(value) for value in outer),
        *(abs(value) for value in inner),
    )
    tolerance = 1.0e-11 * scale
    return all(
        outer[axis] <= inner[axis] + tolerance
        and inner[axis + 3] <= outer[axis + 3] + tolerance
        for axis in range(3)
    )


def _build_cellwise_row_partition(
    view: Any,
    *,
    source_sha: str,
    current_plan_path: str | Path,
    expected_current_plan_sha256: str,
    shadow_plan_identity: Mapping[str, Any],
) -> _CellwiseRowPartition:
    """Designate every actual reduced row to one incident current leaf."""

    comm = view.mesh_data.mesh.comm
    current_forest, current_degrees, current_identity = (
        _current_leaf_authority(
            view,
            source_sha=source_sha,
            current_plan_path=current_plan_path,
            expected_current_plan_sha256=(
                expected_current_plan_sha256
            ),
        )
    )
    context = getattr(view.mesh_data, "local_h_context", None)
    shadow_forest = None if context is None else context.forest
    if shadow_forest is None:
        raise ValueError("shadow local-h forest is unavailable")
    shadow_leaves = tuple(shadow_forest.leaves)
    current_leaves = tuple(current_forest.leaves)
    target_ids = tuple(
        canonical_hp_cell_target_id(cell.key) for cell in current_leaves
    )
    if len(set(target_ids)) != len(target_ids):
        raise RuntimeError("current controller target IDs are not unique")
    shadow_to_current: list[int] = []
    for shadow_index, shadow_leaf in enumerate(shadow_leaves):
        matches = [
            current_index
            for current_index, current_leaf in enumerate(current_leaves)
            if _box_contains(current_leaf.box, shadow_leaf.box)
        ]
        if len(matches) != 1:
            raise ValueError(
                "one shadow leaf does not have exactly one current ancestor: "
                f"shadow_leaf={shadow_index}, matches={matches[:3]}"
            )
        shadow_to_current.append(matches[0])
    descendant_counts = np.bincount(
        np.asarray(shadow_to_current, dtype=np.int64),
        minlength=len(current_leaves),
    )
    if np.any(descendant_counts <= 0):
        raise ValueError(
            "shadow forest does not cover every current leaf"
        )

    system = view.reduction.system
    constraints = system.trace_constraints
    if constraints is None:
        raise ValueError(
            "cellwise DWR requires physical Floquet/hanging constraints"
        )
    constrained_cells = tuple(constraints.owned_cells)
    if not all(
        hasattr(cell, "canonical_leaf")
        and hasattr(cell, "independent_rows")
        for cell in constrained_cells
    ):
        raise ValueError(
            "trace constraints lack canonical leaf/row incidence"
        )
    trace_rows = int(system.active_trace_rows)
    appended_rows = int(system.appended_rows)
    matrix_rows = int(view.A.getSize()[0])
    if trace_rows + appended_rows != matrix_rows:
        raise ValueError(
            "trace and auxiliary rows do not close the shadow matrix"
        )
    sentinel = np.iinfo(np.int64).max
    local_designation = np.full(
        trace_rows,
        sentinel,
        dtype=np.int64,
    )
    for cell in constrained_cells:
        shadow_leaf = int(cell.canonical_leaf)
        if not 0 <= shadow_leaf < len(shadow_to_current):
            raise ValueError(
                "constraint cell canonical leaf is outside the shadow forest"
            )
        rows = np.asarray(cell.independent_rows, dtype=np.int64)
        if (
            rows.ndim != 1
            or len(rows) == 0
            or np.any(rows < 0)
            or np.any(rows >= trace_rows)
        ):
            raise ValueError(
                "constraint cell has invalid independent trace rows"
            )
        np.minimum.at(
            local_designation,
            rows,
            np.int64(shadow_to_current[shadow_leaf]),
        )
    global_designation = np.empty_like(local_designation)
    comm.Allreduce(
        local_designation,
        global_designation,
        op=MPI.MIN,
    )
    if np.any(global_designation == sentinel):
        raise ValueError(
            "one independent trace row has no incident current leaf"
        )

    modes = tuple(view.goal_context.get("modes", ()))
    if len(modes) != appended_rows:
        raise ValueError(
            "DtN auxiliary rows and ordered mode inventory differ"
        )
    z_min = float(current_identity["domain_z_min"])
    z_max = float(current_identity["domain_z_max"])
    scale = max(abs(z_min), abs(z_max), 1.0)
    plane_tolerance = 1.0e-11 * scale
    support_by_side = {
        "top": sorted(
            {
                shadow_to_current[index]
                for index, leaf in enumerate(shadow_leaves)
                if abs(float(leaf.box[5]) - z_max) <= plane_tolerance
            }
        ),
        "bottom": sorted(
            {
                shadow_to_current[index]
                for index, leaf in enumerate(shadow_leaves)
                if abs(float(leaf.box[2]) - z_min) <= plane_tolerance
            }
        ),
    }
    if not support_by_side["top"] or not support_by_side["bottom"]:
        raise ValueError(
            "DtN top/bottom support leaves are incomplete"
        )
    auxiliary_designation = np.empty(appended_rows, dtype=np.int64)
    for index, mode in enumerate(modes):
        side = str(getattr(mode, "side", ""))
        if side not in support_by_side:
            raise ValueError(
                f"DtN mode {index} has an invalid side {side!r}"
            )
        # One auxiliary equation is an indivisible global reduced row.  It
        # is assigned once to the minimum canonical current leaf in its
        # actual top/bottom support, never spread over every support leaf.
        auxiliary_designation[index] = support_by_side[side][0]
    row_to_leaf = np.concatenate(
        (global_designation, auxiliary_designation)
    )
    if (
        row_to_leaf.shape != (matrix_rows,)
        or np.any(row_to_leaf < 0)
        or np.any(row_to_leaf >= len(current_leaves))
    ):
        raise RuntimeError("reduced-row leaf designation is incomplete")
    row_to_leaf = np.ascontiguousarray(row_to_leaf, dtype=np.int64)
    row_to_leaf.setflags(write=False)
    ownership_ranges = _native_ownership_ranges(
        comm,
        tuple(map(int, view.x.getOwnershipRange())),
        global_size=matrix_rows,
    )
    mapping_sha = _array_sha256(
        row_to_leaf,
        namespace="task035e.actual-dwr.row-to-current-leaf.v1",
    )
    designation_identity = {
        "schema_version": (
            "task035e.actual-dwr-current-leaf-row-designation.v1"
        ),
        "status": "actual_reduced_rows_designated_once",
        "pass": True,
        "current_leaf_count": len(current_leaves),
        "shadow_leaf_count": len(shadow_leaves),
        "independent_trace_rows": trace_rows,
        "appended_auxiliary_rows": appended_rows,
        "total_reduced_rows": matrix_rows,
        "reduced_row_ownership_ranges": [
            list(row) for row in ownership_ranges
        ],
        "row_to_current_leaf_sha256": mapping_sha,
        "trace_row_designation": (
            "minimum canonical current ancestor among actual incident "
            "Floquet/hanging-constrained shadow cells"
        ),
        "auxiliary_row_designation": (
            "minimum canonical current ancestor in the actual DtN side "
            "support; each global auxiliary equation remains indivisible"
        ),
        "global_eta_evenly_distributed": False,
        "endpoint_delta_consumed": False,
        "every_trace_row_incident": True,
        "every_auxiliary_row_side_supported": True,
        "every_shadow_leaf_has_one_current_ancestor": True,
        "every_current_leaf_has_shadow_descendants": True,
    }
    designation_identity["designation_sha256"] = _json_sha256(
        designation_identity,
        namespace="task035e.actual-dwr-row-designation.v1",
    )
    current_keys = tuple(
        (
            int(cell.key.root),
            int(cell.key.level),
            int(cell.key.i),
            int(cell.key.j),
            int(cell.key.k),
        )
        for cell in current_leaves
    )
    current_boxes = tuple(
        tuple(float(value) for value in cell.box)
        for cell in current_leaves
    )
    return _CellwiseRowPartition(
        target_ids=target_ids,
        current_leaf_keys=current_keys,
        current_leaf_boxes=current_boxes,
        current_leaf_degrees=tuple(map(int, current_degrees)),
        row_to_leaf=row_to_leaf,
        independent_trace_rows=trace_rows,
        current_plan_identity=MappingProxyType(current_identity),
        shadow_plan_identity=MappingProxyType(
            dict(shadow_plan_identity)
        ),
        designation_identity=MappingProxyType(designation_identity),
    )


def _native_leaf_rank_digest_catalog(
    communicator: MPI.Intracomm,
    local_digests: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    """Replicate only fixed-size per-leaf/per-rank SHA-256 metadata."""

    leaf_count = len(local_digests)
    send = np.zeros(
        (leaf_count, communicator.size, 32),
        dtype=np.uint8,
    )
    for leaf_index, digest in enumerate(local_digests):
        _sha256(digest, label="leaf rank-local digest")
        send[leaf_index, communicator.rank, :] = np.frombuffer(
            bytes.fromhex(digest),
            dtype=np.uint8,
        )
    received = np.zeros_like(send)
    communicator.Allreduce(send, received, op=MPI.SUM)
    return tuple(
        tuple(bytes(row).hex() for row in received[leaf_index])
        for leaf_index in range(leaf_count)
    )


class _CellwiseDWRAccumulator:
    """Accumulate true owner-row ``conj(z_i) r_i`` by current leaf."""

    def __init__(
        self,
        partition: _CellwiseRowPartition,
        residual: PETSc.Vec,
        communicator: MPI.Intracomm,
    ) -> None:
        self.partition = partition
        self.communicator = communicator
        values, ownership, global_size = _owned_vector_values(
            residual,
            label="cellwise enriched residual",
        )
        if global_size != len(partition.row_to_leaf):
            raise ValueError(
                "cellwise residual and row designation sizes differ"
            )
        self.residual_values = values
        self.ownership = ownership
        self.global_rows = np.arange(
            ownership[0],
            ownership[1],
            dtype=np.int64,
        )
        self.local_leaf = np.asarray(
            partition.row_to_leaf[ownership[0] : ownership[1]],
            dtype=np.int64,
        )
        leaf_count = len(partition.target_ids)
        self.positions = tuple(
            np.flatnonzero(self.local_leaf == leaf_index)
            for leaf_index in range(leaf_count)
        )
        self.local_signed = np.zeros(
            (leaf_count, len(FORMAL_GOAL_IDS)),
            dtype=np.float64,
        )
        self.adjoint_hashers: list[Any] = []
        residual_digests: list[str] = []
        for leaf_index, positions in enumerate(self.positions):
            target_id = partition.target_ids[leaf_index]
            rows = self.global_rows[positions]
            residual_values = self.residual_values[positions]
            residual_digests.append(
                _json_sha256(
                    {
                        "rank": int(communicator.rank),
                        "target_id": target_id,
                        "global_rows_sha256": _array_sha256(
                            rows,
                            namespace=(
                                "task035e.actual-dwr.local-residual-rows.v1"
                            ),
                        ),
                        "owned_residual_values_sha256": _array_sha256(
                            residual_values,
                            namespace=(
                                "task035e.actual-dwr.local-residual-values.v1"
                            ),
                        ),
                        "owned_row_count": len(rows),
                    },
                    namespace=(
                        "task035e.actual-dwr.local-residual-partition.v1"
                    ),
                )
            )
            hasher = hashlib.sha256()
            hasher.update(
                b"task035e.actual-dwr.local-adjoint-catalog.v1\0"
            )
            hasher.update(target_id.encode("ascii"))
            hasher.update(b"\0")
            self.adjoint_hashers.append(hasher)
        self.residual_rank_catalog = _native_leaf_rank_digest_catalog(
            communicator,
            tuple(residual_digests),
        )
        self.consumed_goals = 0

    def consume(self, goal_id: str, adjoint: PETSc.Vec) -> None:
        if (
            self.consumed_goals >= len(FORMAL_GOAL_IDS)
            or goal_id != FORMAL_GOAL_IDS[self.consumed_goals]
        ):
            raise RuntimeError(
                "cellwise adjoints were not consumed in formal goal order"
            )
        values, ownership, global_size = _owned_vector_values(
            adjoint,
            label=f"cellwise adjoint {goal_id}",
        )
        if (
            ownership != self.ownership
            or global_size != len(self.partition.row_to_leaf)
        ):
            raise ValueError(
                f"cellwise adjoint {goal_id} ownership differs"
            )
        products = np.asarray(
            np.conjugate(values) * self.residual_values,
            dtype=np.complex128,
        )
        np.add.at(
            self.local_signed[:, self.consumed_goals],
            self.local_leaf,
            products.real,
        )
        for leaf_index, positions in enumerate(self.positions):
            local_digest = _json_sha256(
                {
                    "rank": int(self.communicator.rank),
                    "goal_id": goal_id,
                    "global_rows_sha256": _array_sha256(
                        self.global_rows[positions],
                        namespace=(
                            "task035e.actual-dwr.local-adjoint-rows.v1"
                        ),
                    ),
                    "owned_adjoint_values_sha256": _array_sha256(
                        values[positions],
                        namespace=(
                            "task035e.actual-dwr.local-adjoint-values.v1"
                        ),
                    ),
                },
                namespace=(
                    "task035e.actual-dwr.local-goal-adjoint-partition.v1"
                ),
            )
            hasher = self.adjoint_hashers[leaf_index]
            hasher.update(goal_id.encode("utf-8"))
            hasher.update(b"\0")
            hasher.update(bytes.fromhex(local_digest))
        self.consumed_goals += 1

    def finalize(
        self,
        signed_eta: Mapping[str, float],
    ) -> Mapping[str, Any]:
        if (
            self.consumed_goals != len(FORMAL_GOAL_IDS)
            or tuple(signed_eta) != FORMAL_GOAL_IDS
        ):
            raise RuntimeError(
                "cellwise DWR did not consume all 59 ordered adjoints"
            )
        global_signed = np.zeros_like(self.local_signed)
        self.communicator.Allreduce(
            self.local_signed,
            global_signed,
            op=MPI.SUM,
        )
        adjoint_rank_catalog = _native_leaf_rank_digest_catalog(
            self.communicator,
            tuple(hasher.hexdigest() for hasher in self.adjoint_hashers),
        )
        leaf_count = len(self.partition.target_ids)
        local_counts = np.bincount(
            self.local_leaf,
            minlength=leaf_count,
        ).astype(np.int64)
        local_trace_counts = np.bincount(
            self.local_leaf[
                self.global_rows
                < self.partition.independent_trace_rows
            ],
            minlength=leaf_count,
        ).astype(np.int64)
        global_counts = np.zeros_like(local_counts)
        global_trace_counts = np.zeros_like(local_trace_counts)
        self.communicator.Allreduce(
            local_counts,
            global_counts,
            op=MPI.SUM,
        )
        self.communicator.Allreduce(
            local_trace_counts,
            global_trace_counts,
            op=MPI.SUM,
        )
        closure_errors: dict[str, float] = {}
        rows: list[dict[str, Any]] = []
        residual_hashes: list[str] = []
        adjoint_hashes: list[str] = []
        for leaf_index, target_id in enumerate(
            self.partition.target_ids
        ):
            residual_partition_sha = _json_sha256(
                {
                    "target_id": target_id,
                    "current_leaf_key": list(
                        self.partition.current_leaf_keys[leaf_index]
                    ),
                    "row_designation_sha256": (
                        self.partition.designation_identity[
                            "designation_sha256"
                        ]
                    ),
                    "rank_local_partition_sha256": list(
                        self.residual_rank_catalog[leaf_index]
                    ),
                },
                namespace=(
                    "task035e.actual-dwr.leaf-residual-partition.v1"
                ),
            )
            adjoint_partition_sha = _json_sha256(
                {
                    "target_id": target_id,
                    "current_leaf_key": list(
                        self.partition.current_leaf_keys[leaf_index]
                    ),
                    "formal_goal_inventory_sha256": (
                        FORMAL_GOAL_INVENTORY_SHA256
                    ),
                    "row_designation_sha256": (
                        self.partition.designation_identity[
                            "designation_sha256"
                        ]
                    ),
                    "rank_local_adjoint_catalog_sha256": list(
                        adjoint_rank_catalog[leaf_index]
                    ),
                },
                namespace=(
                    "task035e.actual-dwr.leaf-adjoint-partition.v1"
                ),
            )
            residual_hashes.append(residual_partition_sha)
            adjoint_hashes.append(adjoint_partition_sha)
            contribution = {
                goal_id: float(global_signed[leaf_index, goal_index])
                for goal_index, goal_id in enumerate(FORMAL_GOAL_IDS)
            }
            unsigned_row = {
                "target_id": target_id,
                "current_leaf_key": list(
                    self.partition.current_leaf_keys[leaf_index]
                ),
                "current_leaf_box": list(
                    self.partition.current_leaf_boxes[leaf_index]
                ),
                "current_leaf_degree": int(
                    self.partition.current_leaf_degrees[leaf_index]
                ),
                "assigned_reduced_row_count": int(
                    global_counts[leaf_index]
                ),
                "assigned_trace_row_count": int(
                    global_trace_counts[leaf_index]
                ),
                "assigned_auxiliary_row_count": int(
                    global_counts[leaf_index]
                    - global_trace_counts[leaf_index]
                ),
                "local_residual_partition_sha256": (
                    residual_partition_sha
                ),
                "local_adjoint_partition_sha256": (
                    adjoint_partition_sha
                ),
                "signed_dwr_contribution": contribution,
            }
            rows.append(
                {
                    **unsigned_row,
                    "row_sha256": _json_sha256(
                        unsigned_row,
                        namespace=(
                            "task035e.cellwise-signed-dwr-row.v1"
                        ),
                    ),
                }
            )
        for goal_index, goal_id in enumerate(FORMAL_GOAL_IDS):
            observed = float(np.sum(global_signed[:, goal_index]))
            expected = float(signed_eta[goal_id])
            error = abs(observed - expected)
            scale = max(
                abs(expected),
                float(np.sum(np.abs(global_signed[:, goal_index]))),
                1.0,
            )
            tolerance = max(1.0e-13, 1.0e-10 * scale)
            closure_errors[goal_id] = error
            if not math.isfinite(error) or error > tolerance:
                raise Task035eActualDWRError(
                    "cellwise signed contributions do not close global eta "
                    f"for {goal_id}: {error:.6e} > {tolerance:.6e}"
                )
        unsigned = {
            "schema_version": CELLWISE_DWR_PARTITION_SCHEMA,
            "status": "cellwise_signed_dwr_partition_pass",
            "pass": True,
            "method": "element_residual_adjoint_pairing",
            "method_detail": (
                "owner-local reduced-row Re(conj(z_i)*r_i), with each "
                "trace row designated once through actual incident cells "
                "and each DtN row designated once through its side support"
            ),
            "complete_current_leaf_partition": True,
            "global_signed_closure_verified": True,
            "actual_cellwise_residual_adjoint_pairing": True,
            "global_eta_evenly_distributed": False,
            "endpoint_delta_consumed": False,
            "formal_goal_count": len(FORMAL_GOAL_IDS),
            "formal_goal_inventory_sha256": (
                FORMAL_GOAL_INVENTORY_SHA256
            ),
            "ordered_goal_ids": list(FORMAL_GOAL_IDS),
            "current_plan_identity": dict(
                self.partition.current_plan_identity
            ),
            "shadow_plan_identity": dict(
                self.partition.shadow_plan_identity
            ),
            "row_designation_identity": dict(
                self.partition.designation_identity
            ),
            "residual_partition_catalog_sha256": _json_sha256(
                residual_hashes,
                namespace=(
                    "task035e.actual-dwr.residual-partition-catalog.v1"
                ),
            ),
            "adjoint_partition_catalog_sha256": _json_sha256(
                adjoint_hashes,
                namespace=(
                    "task035e.actual-dwr.adjoint-partition-catalog.v1"
                ),
            ),
            "maximum_global_signed_closure_error": max(
                closure_errors.values(),
                default=0.0,
            ),
            "rows": rows,
            "python_full_vector_gather_used": False,
            "native_fixed_size_hash_metadata_reduction": True,
            "native_leaf_goal_scalar_reduction": True,
        }
        partition_sha = _json_sha256(
            unsigned,
            namespace=CELLWISE_DWR_PARTITION_SCHEMA,
        )
        return MappingProxyType(
            {
                **unsigned,
                "partition_sha256": partition_sha,
            }
        )


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
        "used_full_boundary_gather",
        "created_dense_boundary_square",
    ):
        if hasattr(floquet, name):
            payload[name] = _jsonable(getattr(floquet, name))
    payload["identity_sha256"] = _json_sha256(
        payload,
        namespace="task035e.actual-dwr.floquet.v1",
    )
    return payload


def _layout_identity(
    view: Any,
    ownership_ranges: list[list[int]],
) -> dict[str, Any]:
    system = view.reduction.system
    entity_map = system.entity_map
    matrix_rows, matrix_columns = map(int, view.A.getSize())
    identity = {
        "matrix_rows": matrix_rows,
        "matrix_columns": matrix_columns,
        "reduced_ownership_ranges": ownership_ranges,
        "raw_active_full_rows": int(entity_map.active_rows),
        "raw_active_trace_rows": int(entity_map.active_trace_rows),
        "independent_trace_rows": int(system.active_trace_rows),
        "appended_auxiliary_rows": int(system.appended_rows),
        "inactive_p6_rows_globally_numbered": bool(
            view.reduction.build_audit.get(
                "inactive_p6_rows_globally_numbered", False
            )
        ),
    }
    if (
        matrix_rows != matrix_columns
        or identity["independent_trace_rows"]
        + identity["appended_auxiliary_rows"]
        != matrix_rows
    ):
        raise ValueError("shadow reduced layout does not close")
    identity["layout_sha256"] = _json_sha256(
        identity,
        namespace="task035e.actual-dwr.shadow-layout.v1",
    )
    return identity


def _qualified_shadow_gate(view: Any) -> dict[str, Any]:
    residual = view.full_active_residual
    relative = (
        residual.get("linear_system_relative_residual")
        if isinstance(residual, Mapping)
        else None
    )
    telemetry = view.primal_solver_telemetry
    port = view.port_operator_audit
    checks = port.get("checks") if isinstance(port, Mapping) else None
    if (
        not isinstance(relative, (int, float))
        or not math.isfinite(float(relative))
        or not 0.0 <= float(relative) <= 1.0e-9
        or not isinstance(telemetry, Mapping)
        or int(telemetry.get("converged_reason", 0)) <= 0
        or not isinstance(port, Mapping)
        or port.get("schema_version")
        != "task035d.variable-p-trace-only-port-operator.v1"
        or port.get("pass") is not True
        or not isinstance(checks, Mapping)
        or not checks
        or not all(value is True for value in checks.values())
        or port.get("auxiliary_interior_columns_allocated") is not False
    ):
        raise ValueError(
            "shadow live view lacks a qualified primal/port Gate"
        )
    return {
        "full_active_true_residual": _jsonable(residual),
        "full_active_true_residual_sha256": _json_sha256(
            residual,
            namespace="task035e.actual-dwr.shadow-primal-residual.v1",
        ),
        "primal_solver_telemetry": _jsonable(telemetry),
        "primal_solver_telemetry_sha256": _json_sha256(
            telemetry,
            namespace="task035e.actual-dwr.shadow-primal-telemetry.v1",
        ),
        "port_operator_audit_sha256": _json_sha256(
            port,
            namespace="task035e.actual-dwr.shadow-port-operator.v1",
        ),
    }


def _ksp_signature(ksp: PETSc.KSP) -> tuple[Any, ...]:
    operator, preconditioner = ksp.getOperators()
    pc = ksp.getPC()
    try:
        factor_type = pc.getFactorSolverType()
    except Exception:
        factor_type = None
    return (
        ksp.getType(),
        pc.getType(),
        factor_type,
        ksp.getOptionsPrefix(),
        tuple(ksp.getTolerances()),
        int(operator.handle),
        int(preconditioner.handle),
    )


def _validate_inputs(
    view: Any,
    current_primal_in_shadow: PETSc.Vec,
    goal_gradients: Mapping[str, PETSc.Vec],
    *,
    source_sha: str,
    expected_plan_sha256: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    scalar = np.dtype(PETSc.ScalarType)
    integer = np.dtype(PETSc.IntType)
    if scalar != np.dtype(np.complex128) or integer != np.dtype(np.int32):
        raise ValueError(
            f"actual DWR requires PETSc complex128/int32, got "
            f"{scalar}/{integer}"
        )
    matrix_size = tuple(map(int, view.A.getSize()))
    if (
        matrix_size[0] != matrix_size[1]
        or int(view.b.getSize()) != matrix_size[0]
        or int(view.x.getSize()) != matrix_size[0]
        or int(current_primal_in_shadow.getSize()) != matrix_size[0]
    ):
        raise ValueError("shadow matrix/vector layout is inconsistent")
    expected_range = tuple(map(int, view.x.getOwnershipRange()))
    if (
        tuple(map(int, view.b.getOwnershipRange())) != expected_range
        or tuple(
            map(int, current_primal_in_shadow.getOwnershipRange())
        )
        != expected_range
    ):
        raise ValueError("shadow matrix vectors have different ownership")
    _owned_vector_values(view.b, label="shadow RHS")
    _owned_vector_values(view.x, label="shadow solution")
    _owned_vector_values(
        current_primal_in_shadow,
        label="injected current primal",
    )
    if set(goal_gradients) != set(FORMAL_GOAL_IDS):
        missing = sorted(set(FORMAL_GOAL_IDS) - set(goal_gradients))
        extra = sorted(set(goal_gradients) - set(FORMAL_GOAL_IDS))
        raise ValueError(
            f"goal-gradient inventory differs: missing={missing}, "
            f"extra={extra}"
        )
    for goal_id in FORMAL_GOAL_IDS:
        gradient = goal_gradients[goal_id]
        if (
            int(gradient.getSize()) != matrix_size[0]
            or tuple(map(int, gradient.getOwnershipRange()))
            != expected_range
        ):
            raise ValueError(
                f"goal gradient {goal_id} has the wrong shadow layout"
            )
        _owned_vector_values(gradient, label=f"goal gradient {goal_id}")
    operator, preconditioner = view.ksp.getOperators()
    if (
        int(operator.handle) != int(view.A.handle)
        or int(preconditioner.handle) != int(view.A.handle)
    ):
        raise ValueError("borrowed KSP is not factored on the shadow operator")
    return (
        _plan_identity(
            view,
            source_sha=source_sha,
            expected_plan_sha256=expected_plan_sha256,
        ),
        _qualified_shadow_gate(view),
        _local_matrix_csr_payload(
            view.A,
            rank=int(view.mesh_data.mesh.comm.rank),
        ),
    )


def evaluate_task035e_actual_dwr(
    shadow_view: Any,
    current_primal_in_shadow: PETSc.Vec,
    goal_gradients: Mapping[str, PETSc.Vec],
    *,
    source_sha: str,
    expected_shadow_plan_sha256: str,
    shadow_kind: str,
    adjoint_relative_tolerance: float = 1.0e-9,
    current_plan_path: str | Path | None = None,
    expected_current_plan_sha256: str | None = None,
    require_cellwise_partition: bool = False,
) -> Task035eActualDWRResult:
    """Solve all 59 actual shadow adjoints and return signed DWR evidence."""

    view = shadow_view
    source = _source_sha(source_sha)
    plan_sha = _sha256(
        expected_shadow_plan_sha256,
        label="expected shadow plan SHA-256",
    )
    if shadow_kind not in {"p-shadow", "h-shadow"}:
        raise ValueError("shadow_kind must be p-shadow or h-shadow")
    tolerance = float(adjoint_relative_tolerance)
    if not math.isfinite(tolerance) or not 0.0 < tolerance <= 1.0e-8:
        raise ValueError(
            "adjoint_relative_tolerance must be in (0, 1e-8]"
        )
    if (current_plan_path is None) != (
        expected_current_plan_sha256 is None
    ):
        raise ValueError(
            "current plan path and SHA-256 must be supplied together"
        )
    if require_cellwise_partition and current_plan_path is None:
        raise ValueError(
            "required cellwise partition lacks the immutable current plan"
        )
    comm = view.mesh_data.mesh.comm
    current_plan_sha = (
        None
        if expected_current_plan_sha256 is None
        else _sha256(
            expected_current_plan_sha256,
            label="expected current plan SHA-256",
        )
    )
    request_identity = {
        "source_sha": source,
        "expected_shadow_plan_sha256": plan_sha,
        "expected_current_plan_sha256": current_plan_sha,
        "shadow_kind": shadow_kind,
        "adjoint_relative_tolerance": tolerance,
        "require_cellwise_partition": bool(
            require_cellwise_partition
        ),
        "formal_goal_inventory_sha256": FORMAL_GOAL_INVENTORY_SHA256,
    }
    request_sha = _json_sha256(
        request_identity,
        namespace="task035e.actual-dwr.request.v1",
    )
    _require_collectively_identical_sha256(
        comm,
        request_sha,
        label="actual DWR request",
    )
    validated = _collective_local_validation(
        comm,
        "actual DWR input validation",
        lambda: _validate_inputs(
            view,
            current_primal_in_shadow,
            goal_gradients,
            source_sha=source,
            expected_plan_sha256=plan_sha,
        ),
    )
    if validated is None:
        raise Task035eActualDWRError(
            "actual DWR validation returned no identities"
        )
    plan_identity, shadow_gate, local_matrix_payload = validated
    cellwise_row_partition = None
    if current_plan_path is not None and current_plan_sha is not None:
        cellwise_row_partition = _collective_local_validation(
            comm,
            "actual DWR cellwise row designation",
            lambda: _build_cellwise_row_partition(
                view,
                source_sha=source,
                current_plan_path=current_plan_path,
                expected_current_plan_sha256=current_plan_sha,
                shadow_plan_identity=plan_identity,
            ),
        )
        if not isinstance(
            cellwise_row_partition,
            _CellwiseRowPartition,
        ):
            raise Task035eActualDWRError(
                "cellwise row designation returned no authority"
            )
    elif require_cellwise_partition:
        raise Task035eActualDWRError(
            "required cellwise row designation was not built"
        )
    ksp_signature = _ksp_signature(view.ksp)
    protected_states = {
        "matrix": int(view.A.stateGet()),
        "shadow_rhs": int(view.b.stateGet()),
        "shadow_solution": int(view.x.stateGet()),
        "injected_current": int(current_primal_in_shadow.stateGet()),
        **{
            f"goal:{goal_id}": int(goal_gradients[goal_id].stateGet())
            for goal_id in FORMAL_GOAL_IDS
        },
    }

    current_identity = _vector_partition_identity(
        current_primal_in_shadow,
        comm,
        namespace="task035e.actual-dwr.injected-current.v1",
    )
    rhs_identity = _vector_partition_identity(
        view.b,
        comm,
        namespace="task035e.actual-dwr.shadow-rhs.v1",
    )
    matrix_identity = _matrix_partition_identity(
        view.A,
        comm,
        local_payload=local_matrix_payload,
    )
    layout_identity = _layout_identity(
        view,
        current_identity["ownership_ranges"],
    )
    operator_identity = {
        "matrix": matrix_identity,
        "port_operator_audit_sha256": shadow_gate[
            "port_operator_audit_sha256"
        ],
        "ksp_type": view.ksp.getType(),
        "pc_type": view.ksp.getPC().getType(),
        "floquet": _floquet_identity(view.floquet_data),
    }
    implementation_identity = {
        "schema_version": (
            "task035e.actual-dwr-implementation-identity.v1"
        ),
        "module_file_sha256": _file_sha256(
            Path(__file__).resolve()
        ),
        "actual_dwr_schema": ACTUAL_DWR_SCHEMA,
        "formal_goal_inventory_sha256": (
            FORMAL_GOAL_INVENTORY_SHA256
        ),
        "algebra": (
            "r=b-A*x; A^H*z=g; eta=Re(z^H*r)"
        ),
    }
    implementation_sha256 = _json_sha256(
        implementation_identity,
        namespace="task035e.actual-dwr-implementation.v1",
    )

    matrix_action = current_primal_in_shadow.duplicate()
    residual = view.b.copy()
    try:
        view.A.mult(current_primal_in_shadow, matrix_action)
        residual.axpy(PETSc.ScalarType(-1.0), matrix_action)
        residual_norm = float(residual.norm(PETSc.NormType.NORM_2))
        action_norm = float(
            matrix_action.norm(PETSc.NormType.NORM_2)
        )
        rhs_norm = float(view.b.norm(PETSc.NormType.NORM_2))
        relative_residual = residual_norm / max(
            rhs_norm,
            np.finfo(float).tiny,
        )
        if (
            not math.isfinite(residual_norm)
            or not math.isfinite(action_norm)
            or not math.isfinite(rhs_norm)
            or not math.isfinite(relative_residual)
        ):
            raise Task035eActualDWRError(
                "actual enriched residual contains a non-finite norm"
            )
        action_identity = _vector_partition_identity(
            matrix_action,
            comm,
            namespace="task035e.actual-dwr.shadow-action-on-current.v1",
        )
        residual_identity = _vector_partition_identity(
            residual,
            comm,
            namespace="task035e.actual-dwr.enriched-residual.v1",
        )
        cellwise_accumulator = (
            None
            if cellwise_row_partition is None
            else _CellwiseDWRAccumulator(
                cellwise_row_partition,
                residual,
                comm,
            )
        )

        goal_rows: list[dict[str, Any]] = []
        signed_eta: dict[str, float] = {}
        for goal_id in FORMAL_GOAL_IDS:
            gradient = goal_gradients[goal_id]
            gradient_norm = float(
                gradient.norm(PETSc.NormType.NORM_2)
            )
            if (
                not math.isfinite(gradient_norm)
                or gradient_norm <= np.finfo(float).tiny
            ):
                raise Task035eActualDWRError(
                    f"goal gradient {goal_id} is zero or invalid"
                )
            gradient_identity = _vector_partition_identity(
                gradient,
                comm,
                namespace=(
                    "task035e.actual-dwr.goal-gradient."
                    + hashlib.sha256(goal_id.encode("utf-8")).hexdigest()
                ),
            )
            conjugated_gradient = gradient.copy()
            adjoint = gradient.duplicate()
            adjoint_action = gradient.duplicate()
            try:
                conjugated_gradient.conjugate()
                view.ksp.solveTranspose(
                    conjugated_gradient,
                    adjoint,
                )
                converged_reason = int(
                    view.ksp.getConvergedReason()
                )
                if converged_reason <= 0:
                    raise Task035eActualDWRError(
                        f"adjoint solve failed for {goal_id}: "
                        f"reason={converged_reason}"
                    )
                # PETSc solveTranspose solves A^T y=conj(g).  Therefore
                # z=conj(y) is the solution of A^H z=g.
                adjoint.conjugate()
                view.A.multHermitian(adjoint, adjoint_action)
                adjoint_action.axpy(PETSc.ScalarType(-1.0), gradient)
                adjoint_residual_norm = float(
                    adjoint_action.norm(PETSc.NormType.NORM_2)
                )
                adjoint_norm = float(
                    adjoint.norm(PETSc.NormType.NORM_2)
                )
                adjoint_relative_residual = (
                    adjoint_residual_norm
                    / max(gradient_norm, np.finfo(float).tiny)
                )
                if (
                    not math.isfinite(adjoint_relative_residual)
                    or not math.isfinite(adjoint_norm)
                    or adjoint_relative_residual > tolerance
                ):
                    raise Task035eActualDWRError(
                        f"adjoint true residual failed for {goal_id}: "
                        f"{adjoint_relative_residual:.6e} > "
                        f"{tolerance:.6e}"
                    )
                pairing = complex(adjoint.dot(residual))
                eta = float(pairing.real)
                if not math.isfinite(eta) or not math.isfinite(
                    pairing.imag
                ):
                    raise Task035eActualDWRError(
                        f"DWR pairing is non-finite for {goal_id}"
                    )
                adjoint_identity = _vector_partition_identity(
                    adjoint,
                    comm,
                    namespace=(
                        "task035e.actual-dwr.adjoint."
                        + hashlib.sha256(
                            goal_id.encode("utf-8")
                        ).hexdigest()
                    ),
                )
                adjoint_residual_identity = (
                    _vector_partition_identity(
                        adjoint_action,
                        comm,
                        namespace=(
                            "task035e.actual-dwr.adjoint-residual."
                            + hashlib.sha256(
                                goal_id.encode("utf-8")
                            ).hexdigest()
                        ),
                    )
                )
                if cellwise_accumulator is not None:
                    cellwise_accumulator.consume(goal_id, adjoint)
                unsigned_goal = {
                    "goal_id": goal_id,
                    "goal_id_sha256": hashlib.sha256(
                        goal_id.encode("utf-8")
                    ).hexdigest(),
                    "gradient_partition_sha256": gradient_identity[
                        "partition_bound_sha256"
                    ],
                    "adjoint_partition_sha256": adjoint_identity[
                        "partition_bound_sha256"
                    ],
                    "adjoint_residual_partition_sha256": (
                        adjoint_residual_identity[
                            "partition_bound_sha256"
                        ]
                    ),
                    "gradient_l2_norm": gradient_norm,
                    "adjoint_l2_norm": adjoint_norm,
                    "adjoint_true_residual_l2_norm": (
                        adjoint_residual_norm
                    ),
                    "adjoint_true_relative_residual": (
                        adjoint_relative_residual
                    ),
                    "adjoint_relative_tolerance": tolerance,
                    "ksp_converged_reason": converged_reason,
                    "complex_pairing_zH_r": [
                        float(pairing.real),
                        float(pairing.imag),
                    ],
                    "signed_eta_real_zH_r": eta,
                    "endpoint_goal_delta_consumed": False,
                    "actual_adjoint_solve_complete": True,
                }
                row = {
                    **unsigned_goal,
                    "goal_evidence_sha256": _json_sha256(
                        unsigned_goal,
                        namespace="task035e.actual-dwr.per-goal.v1",
                    ),
                }
                goal_rows.append(row)
                signed_eta[goal_id] = eta
            finally:
                adjoint_action.destroy()
                adjoint.destroy()
                conjugated_gradient.destroy()
        cellwise_partition = (
            None
            if cellwise_accumulator is None
            else cellwise_accumulator.finalize(signed_eta)
        )
    finally:
        residual.destroy()
        matrix_action.destroy()

    if len(goal_rows) != len(FORMAL_GOAL_IDS) or tuple(
        row["goal_id"] for row in goal_rows
    ) != FORMAL_GOAL_IDS:
        raise Task035eActualDWRError(
            "actual DWR did not complete the ordered 59-goal inventory"
        )
    if _ksp_signature(view.ksp) != ksp_signature:
        raise Task035eActualDWRError(
            "actual DWR changed the borrowed KSP configuration"
        )
    observed_states = {
        "matrix": int(view.A.stateGet()),
        "shadow_rhs": int(view.b.stateGet()),
        "shadow_solution": int(view.x.stateGet()),
        "injected_current": int(current_primal_in_shadow.stateGet()),
        **{
            f"goal:{goal_id}": int(goal_gradients[goal_id].stateGet())
            for goal_id in FORMAL_GOAL_IDS
        },
    }
    if observed_states != protected_states:
        changed = sorted(
            name
            for name in protected_states
            if protected_states[name] != observed_states[name]
        )
        raise Task035eActualDWRError(
            f"actual DWR mutated borrowed inputs: {changed}"
        )

    unsigned_report = {
        "schema_version": ACTUAL_DWR_SCHEMA,
        "status": "actual_live_shadow_dwr_pass",
        "pass": True,
        "source_sha": source,
        "shadow_kind": shadow_kind,
        "request_sha256": request_sha,
        "shadow_plan_identity": plan_identity,
        "layout_identity": layout_identity,
        "operator_identity": operator_identity,
        "implementation_identity": {
            **implementation_identity,
            "implementation_sha256": implementation_sha256,
        },
        "shadow_primal_gate": shadow_gate,
        "current_primal_in_shadow": {
            "injection_performed_by_this_kernel": False,
            "already_in_shadow_layout": True,
            **current_identity,
        },
        "shadow_rhs": rhs_identity,
        "shadow_action_on_current": action_identity,
        "enriched_current_residual": {
            "definition": "b_shadow-A_shadow*x_current_in_shadow",
            "l2_norm": residual_norm,
            "rhs_l2_norm": rhs_norm,
            "relative_residual": relative_residual,
            **residual_identity,
        },
        "goal_inventory": {
            "formal_goal_count": len(FORMAL_GOAL_IDS),
            "formal_goal_inventory_sha256": (
                FORMAL_GOAL_INVENTORY_SHA256
            ),
            "ordered_goal_ids": list(FORMAL_GOAL_IDS),
        },
        "goals": goal_rows,
        "aggregate_identities": {
            "implementation_sha256": implementation_sha256,
            "primal_residual_sha256": residual_identity[
                "partition_bound_sha256"
            ],
            "adjoint_system_sha256": _json_sha256(
                {
                    "shadow_plan_identity": plan_identity,
                    "layout_identity": layout_identity,
                    "operator_identity": operator_identity,
                },
                namespace="task035e.actual-dwr-adjoint-system.v1",
            ),
        },
        "algebra": {
            "adjoint_equation": "A_shadow^H*z_J=g_J",
            "transpose_reuse": (
                "solve A^T*y=conj(g_J), then z_J=conj(y)"
            ),
            "signed_estimator": "eta_J=Re(z_J^H*r)",
            "residual_sign": "b_shadow-A_shadow*x_current",
            "owner_local_petsc_vectors": True,
            "python_full_vector_allgather": False,
            "native_fixed_size_hash_metadata_reduction": True,
            "endpoint_goal_delta_consumed": False,
            "reference_solution_consumed": False,
        },
        "capability_credit": {
            "actual_enriched_residual_complete": True,
            "actual_59_goal_adjoint_complete": True,
            "actual_signed_dwr_complete": True,
            "goal_gradient_construction_complete": False,
            "current_to_shadow_injection_complete": False,
            "local_h_transfer_complete": False,
            "shadow_endpoint_effectivity_complete": False,
            "accuracy_credit": False,
        },
        "ordinary_default_changed": False,
    }
    report_sha = _json_sha256(
        unsigned_report,
        namespace="task035e.actual-live-shadow-dwr-report.v1",
    )
    report = {
        **unsigned_report,
        "report_sha256": report_sha,
    }
    return Task035eActualDWRResult(
        report=MappingProxyType(report),
        report_sha256=report_sha,
        signed_eta=MappingProxyType(dict(signed_eta)),
        cellwise_partition=cellwise_partition,
    )


__all__ = [
    "ACTUAL_DWR_SCHEMA",
    "Task035eActualDWRError",
    "Task035eActualDWRResult",
    "evaluate_task035e_actual_dwr",
]
